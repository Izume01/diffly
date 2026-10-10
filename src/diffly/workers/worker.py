import os
from typing import Any

from arq.connections import RedisSettings
from dotenv import load_dotenv
from sqlmodel import select

from diffly.agents.pipeline import run_pipeline
from diffly.database.db import async_session_maker
from diffly.database.models import Repository, Review, ReviewFinding
from diffly.github.client import (
    add_pr_reaction,
    create_check_run,
    create_pr_review,
    format_review_comment,
    get_installation_token,
    get_pr_diff,
    update_check_run,
)
from diffly.guardrails import filter_diff_content, sanitize_review_output

load_dotenv()

import redis.exceptions

VALKEY_URI = os.getenv("VALKEY_URI", "valkey://localhost:6379")
REDIS_DSN = VALKEY_URI.replace("valkeys://", "rediss://").replace(
    "valkey://", "redis://"
)
REDIS_SETTING = RedisSettings.from_dsn(REDIS_DSN)
REDIS_SETTING.retry_on_timeout = True
REDIS_SETTING.retry_on_error = [
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
]

REDIS_SETTING.conn_retries = 10
REDIS_SETTING.conn_retry_delay = 2


async def review_pr(ctx: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
    repo = job_data.get("repo")
    pull_number = job_data.get("pull_number")
    installation_id = job_data.get("installation_id")
    head_sha = job_data.get("head_sha")
    github_repo_id = job_data.get("github_repo_id")
    repo_name = job_data.get("repo_name")

    print(f"🚀 Worker picked up PR job: {job_data}")

    if not (repo and pull_number and installation_id):
        print(
            f"⚠️ Missing PR review details in job payload (event={job_data.get('event')})"
        )
        return {"status": "missing_parameters"}

    token = await get_installation_token(installation_id)

    try:
        await add_pr_reaction(repo, pull_number, token, reaction="rocket")
        print(f"🚀 Added rocket reaction to {repo} PR #{pull_number}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Failed to add reaction: {e}")

    check_run_id: int | None = None
    if head_sha:
        try:
            check_run = await create_check_run(
                repo=repo,
                head_sha=head_sha,
                installation_token=token,
            )
            check_run_id = int(check_run["id"])
            print(f"🔄 Check run initialized (id={check_run_id})")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Failed to create check run: {e}")

    print(f"Fetching diff for {repo} PR #{pull_number}...")
    raw_diff = await get_pr_diff(repo, pull_number, token)
    guard_res = filter_diff_content(raw_diff)
    diff = guard_res.clean_diff
    print(
        f"Diff sanitized ({len(diff)} chars, "
        f"filtered={guard_res.filtered_files}, truncated={guard_res.was_truncated})"
    )

    print(f"Invoking Multi-Agent Review Pipeline for {repo} PR #{pull_number}...")
    review = await run_pipeline(diff)

    clean_summary = sanitize_review_output(review.summary)
    if guard_res.filtered_files:
        files_list = ", ".join(f"`{f}`" for f in guard_res.filtered_files)
        clean_summary += f"\n\n> ℹ️ **Diffly Guardrails:** Filtered out non-reviewable files: {files_list}"
    if guard_res.was_truncated:
        clean_summary += "\n\n> ⚠️ **Diffly Guardrails:** Diff exceeded maximum line limit (1,500 lines). Deep review capped."

    print(f"\n--- Executive Summary: {clean_summary} ---")
    print(f"Deduplicated findings count: {len(review.findings)}")

    # 4. Post GitHub PR Review with inline comments
    comments: list[dict[str, Any]] = [
        {
            "path": f.file_path,
            "line": f.line_number,
            "side": "RIGHT",
            "body": format_review_comment(f),
        }
        for f in review.findings
    ]

    try:
        review_resp = await create_pr_review(
            repo=repo,
            installation_token=token,
            pull_number=pull_number,
            body=f"### 🤖 Diffly Code Review\n\n{clean_summary}",
            comments=comments if comments else None,
            event="COMMENT",
        )
        print(f"✅ Published PR Review: {review_resp.get('html_url')}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Failed to publish PR review: {e}")

    # 5. Complete the Check Run
    if check_run_id:
        try:
            conclusion = "neutral" if review.findings else "success"
            await update_check_run(
                repo=repo,
                installation_token=token,
                check_run_id=check_run_id,
                status="completed",
                conclusion=conclusion,
                output={
                    "title": f"Diffly Review ({len(review.findings)} issues found)",
                    "summary": f"### Review Overview\n\n{clean_summary}",
                },
            )
            print(f"✅ Updated check run (id={check_run_id}) to completed.")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Failed to update check run: {e}")

    # 6. Persist Review and Findings to Neon Postgres
    try:
        async with async_session_maker() as session:
            stmt = (
                select(Repository).where(
                    (Repository.github_repo_id == github_repo_id)
                    | (Repository.full_name == repo)
                )
                if github_repo_id
                else select(Repository).where(Repository.full_name == repo)
            )
            result = await session.exec(stmt)
            db_repo = result.first()

            if not db_repo and github_repo_id:
                db_repo = Repository(
                    github_repo_id=github_repo_id,
                    name=repo_name or repo.split("/")[-1],
                    full_name=repo,
                )
                session.add(db_repo)
                await session.commit()
                await session.refresh(db_repo)

            if db_repo:
                db_review = Review(
                    repository_id=db_repo.id,
                    pr_number=pull_number,
                    commit_sha=head_sha or "",
                    status="completed",
                    summary=clean_summary,
                )
                session.add(db_review)
                await session.commit()
                await session.refresh(db_review)

                db_findings = [
                    ReviewFinding(
                        review_id=db_review.id,
                        file_path=f.file_path,
                        line_start=f.line_number,
                        line_end=f.line_number,
                        severity=f.severity,
                        category="code_review",
                        title=f.title,
                        description=f.description,
                        suggestion=f.suggestion,
                    )
                    for f in review.findings
                ]
                if db_findings:
                    session.add_all(db_findings)
                    await session.commit()

                print(
                    f"💾 Persisted review #{db_review.id} with {len(db_findings)} findings for {repo} in database"
                )
            else:
                print(f"⚠️ Could not resolve repository record for {repo}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Failed to persist review to database: {e}")

    return {
        "status": "completed",
        "findings_count": len(review.findings),
    }


class WorkerSettings:
    functions = (review_pr,)
    redis_settings = REDIS_SETTING
