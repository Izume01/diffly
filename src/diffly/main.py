import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager

from arq import create_pool
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from diffly.auth import (
    auth_backend,
    auth_settings,
    fastapi_users,
    github_oauth_client,
)
from diffly.database.db import init_db
from diffly.database.schema import UserRead, UserUpdate
from diffly.routers.repositories import router as repositories_router
from diffly.services.valkey_client import client
from diffly.workers.worker import REDIS_SETTING

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.arq_pool = await create_pool(REDIS_SETTING)
    yield

    await app.state.arq_pool.aclose()


app = FastAPI(title="Diffly API", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Auth & User Routers (FastAPI-Users)
# ---------------------------------------------------------------------------
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_oauth_router(
        oauth_client=github_oauth_client,
        backend=auth_backend,
        state_secret=auth_settings.auth_secret,
        associate_by_email=True,
        is_verified_by_default=True,
    ),
    prefix="/auth/github",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

app.include_router(repositories_router)


GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(...),
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
):
    body = await request.body()

    expected_signature = (
        "sha256=" + hmac.new(GITHUB_WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid Signature.")

    data = json.loads(body)

    action = data.get("action")

    acquired = await client.set(
        f"idempotency:github:{x_github_delivery}",
        "1",
        nx=True,
        ex=86400,
    )

    if not acquired:
        return {"status": "duplicate_ignored"}

    if x_github_event == "pull_request" and action in (
        "opened",
        "synchronize",
        "reopened",
    ):
        installation_id = data.get("installation", {}).get("id")
        repo = data.get("repository", {}).get("full_name")
        pull_number = data.get("pull_request", {}).get("number")
        head_sha = data.get("pull_request", {}).get("head", {}).get("sha")

        await request.app.state.arq_pool.enqueue_job(
            "review_pr",
            {
                "event": x_github_event,
                "delivery": x_github_delivery,
                "action": action,
                "repo": repo,
                "pull_number": pull_number,
                "head_sha": head_sha,
                "installation_id": installation_id,
            },
            _job_id=f"github:delivery:{x_github_delivery}",
        )

        print(
            f"Queued PR #{pull_number} on {repo} (action={action}, delivery={x_github_delivery})"
        )
        return {"status": "queued", "delivery": x_github_delivery}

    print(
        f"Ignored event={x_github_event} action={action} delivery={x_github_delivery}"
    )
    return {"status": "ignored", "event": x_github_event, "action": action}


@app.get("/health")
def health():
    return {"ok": True}
