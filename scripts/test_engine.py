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
    results = await run_pipeline(diff)

    print("\n" + "=" * 60)
    print("REVIEW RESULTS PREVIEW (CALM / NON-CRINGE FORMAT)")
    print("=" * 60)

    total_findings = 0
    for res in results:
        print(f"\n--- Specialist Overview: {res.output.summary} ---")
        for finding in res.output.finding:
            total_findings += 1
            print(f"\n[File: {finding.file_path} | Line: {finding.line_number}]")
            print("-" * 50)
            print(format_review_comment(finding))
            print("-" * 50)

    print(f"\n✅ Completed: Total findings across specialists: {total_findings}")


if __name__ == "__main__":
    asyncio.run(main())
