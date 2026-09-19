import asyncio
import json

from diffly.agents.schema import AgentReviewResult
from diffly.agents.specialist import (
    aggregator_agent,
    logic_agent,
    performance_agent,
    security_agent,
)


async def run_pipeline(diff: str) -> AgentReviewResult:
    """Runs specialized reviewer agents over the PR diff with error resilience and pacing."""
    specialists = [
        ("Security", security_agent),
        ("Logic", logic_agent),
        ("Performance", performance_agent),
    ]

    results = []
    for name, agent in specialists:
        print(f"🔍 Running {name} Specialist Agent...")
        for attempt in range(2):
            try:
                res = await agent.run(diff)
                results.append(res)
                print(f"{name} Agent completed ({len(res.output.finding)} findings).")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 0:
                    print(
                        f"{name} Agent encountered transient error ({e}), retrying in 2s..."
                    )
                    await asyncio.sleep(2.0)
                else:
                    print(f"{name} Agent failed after retry: {e}")

        await asyncio.sleep(1.0)

    all_findings = [
        finding.model_dump() for res in results for finding in res.output.findings
    ]

    if not all_findings:
        return AgentReviewResult(
            summary="No issues found across Security, Logic, or Performance.",
            findings=[],
        )

    prompt = (
        "Here are the raw findings from the specialist reviewer agents:\n\n"
        f"{json.dumps(all_findings, indent=2)}\n\n"
        "Deduplicate overlapping findings on the same lines, filter low-confidence "
        "items, "
        "and synthesize an executive PR summary."
    )

    print("📊 Running Aggregator Agent...")
    aggregator_run = await aggregator_agent.run(prompt)
    print(
        f"✅ Aggregator Agent completed ({len(aggregator_run.output.findings)} deduplicated findings)."
    )

    return aggregator_run.output
