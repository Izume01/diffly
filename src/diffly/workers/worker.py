import os
from typing import Any

from arq.connections import RedisSettings
from dotenv import load_dotenv

load_dotenv()

VALKEY_URI = os.getenv("VALKEY_URI", "valkey://localhost:6379")
REDIS_DSN = VALKEY_URI.replace("valkeys://", "rediss://").replace(
    "valkey://", "redis://"
)
REDIS_SETTING = RedisSettings.from_dsn(REDIS_DSN)


async def review_pr(ctx: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
    print(f"🚀 Worker picked up PR job: {job_data}")
    return {"status": "completed"}


class WorkerSettings:
    functions = (review_pr,)
    redis_settings = REDIS_SETTING
