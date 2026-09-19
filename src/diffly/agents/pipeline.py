import asyncio
from typing import Any

from diffly.agents.specialist import logic_agent, performance_agent, security_agent


async def run_pipeline(diff: str) -> list[Any]:
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
                print(f"✅ {name} Agent completed ({len(res.output.finding)} findings).")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 0:
                    print(f"🔄 {name} Agent encountered transient error ({e}), retrying in 2s...")
                    await asyncio.sleep(2.0)
                else:
                    print(f"⚠️ {name} Agent failed after retry: {e}")

        # Pace calls by 1s to prevent router queue congestion
        await asyncio.sleep(1.0)

    return results
