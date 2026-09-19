import os
from typing import Any

from arq.connections import RedisSettings
from dotenv import load_dotenv

from diffly.agents.pipeline import run_pipeline
from diffly.github.client import (
    add_pr_reaction,
    create_check_run,
    create_pr_review,
    format_review_comment,
    get_installation_token,
    get_pr_diff,
    update_check_run,
)

load_dotenv()

VALKEY_URI = os.getenv("VALKEY_URI", "valkey://localhost:6379")
REDIS_DSN = VALKEY_URI.replace("valkeys://", "rediss://").replace(
    "valkey://", "redis://"
)
REDIS_SETTING = RedisSettings.from_dsn(REDIS_DSN)


async def review_pr(ctx: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
    repo = job_data.get("repo")
    pull_number = job_data.get("pull_number")
    installation_id = job_data.get("installation_id")
    head_sha = job_data.get("head_sha")

    print(f"🚀 Worker picked up PR job: {job_data}")

    if not (repo and pull_number and installation_id):
        print(
            f"⚠️ Missing PR review details in job payload (event={job_data.get('event')})"
        )
        return {"status": "missing_parameters"}

    token = await get_installation_token(installation_id)

    # 0. Instantly react with 👀 for zero-notification visual acknowledgement
    try:
        await add_pr_reaction(repo, pull_number, token, reaction="eyes")
        print(f"👀 Added eyes reaction to {repo} PR #{pull_number}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Failed to add reaction: {e}")

    # 1. Initialize Check Run (shows live spinner in PR)
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

    # 2. Fetch unified diff
    print(f"📥 Fetching diff for {repo} PR #{pull_number}...")
    diff = await get_pr_diff(repo, pull_number, token)
    print(f"📄 Full PR Diff retrieved ({len(diff)} characters)")

    # 3. Run Multi-Agent Review Pipeline (Specialists + Aggregator)
    print(f"🤖 Invoking Multi-Agent Review Pipeline for {repo} PR #{pull_number}...")
    review = await run_pipeline(diff)

    print(f"\n--- Executive Summary: {review.summary} ---")
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
            body=f"### 🤖 Diffly Code Review\n\n{review.summary}",
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
                    "summary": f"### Review Overview\n\n{review.summary}",
                },
            )
            print(f"✅ Updated check run (id={check_run_id}) to completed.")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Failed to update check run: {e}")

    return {
        "status": "completed",
        "findings_count": len(review.findings),
    }


class WorkerSettings:
    functions = (review_pr,)
    redis_settings = REDIS_SETTING
