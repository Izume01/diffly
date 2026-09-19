import asyncio

from diffly.agents.pipeline import run_pipeline
from diffly.github.client import (
    format_review_comment,
    get_installation_token,
    get_pr_diff,
)


async def main() -> None:
    repo = "Izume01/test"
    pull_number = 4
    installation_id = 161416905

    print(f"🔑 Fetching installation token for {repo}...")
    token = await get_installation_token(installation_id)

    print(f"📄 Fetching diff for PR #{pull_number}...")
    diff = await get_pr_diff(repo, pull_number, token)
    print(f"   Diff size: {len(diff)} characters\n")

    print("🤖 Running Multi-Agent Pipeline with updated prompts...")
    review = await run_pipeline(diff)

    print("\n" + "=" * 60)
    print("DEDUPLICATED AGGREGATOR REVIEW PREVIEW")
    print("=" * 60)

    print(f"\n--- Executive Summary: {review.summary} ---")
    for finding in review.findings:
        print(f"\n[File: {finding.file_path} | Line: {finding.line_number}]")
        print("-" * 50)
        print(format_review_comment(finding))
        print("-" * 50)

    print(f"\n✅ Completed: Total deduplicated findings: {len(review.findings)}")


if __name__ == "__main__":
    asyncio.run(main())
