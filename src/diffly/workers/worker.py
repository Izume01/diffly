import os
from typing import Any

from arq.connections import RedisSettings
from dotenv import load_dotenv

from diffly.github.client import get_installation_token, get_pr_diff

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

    print(f"🚀 Worker picked up PR job: {job_data}")

    if repo and pull_number and installation_id:
        print(
            f"🔑 Generating installation token for installation_id={installation_id}..."
        )
        token = await get_installation_token(installation_id)

        print(f"📥 Fetching diff for {repo} PR #{pull_number}...")
        diff = await get_pr_diff(repo, pull_number, token)

        print(f"📄 Full PR Diff retrieved ({len(diff)} characters):")
        print(diff)

        # Next: Pass diff to AI reviewer agents
    else:
        print(
            f"⚠️ Missing PR review details in job payload (event={job_data.get('event')})"
        )

    return {"status": "completed"}


class WorkerSettings:
    functions = (review_pr,)
    redis_settings = REDIS_SETTING
