import os
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("APP_ID") or os.getenv("GITHUB_APP_ID")
PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "difflybot.pem")

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


def get_private_key() -> str:
    """Load the RSA private key from the configured path."""
    key_file = Path(PRIVATE_KEY_PATH)
    if not key_file.is_absolute():
        key_file = Path.cwd() / key_file

    if not key_file.exists():
        raise FileNotFoundError(f"GitHub private key not found at: {key_file}")

    return key_file.read_text()


def get_app_jwt() -> str:
    """
    Generate an RS256-signed JWT for GitHub App authentication.
    Valid for 10 minutes (maximum permitted by GitHub).
    """
    if not APP_ID:
        raise ValueError("APP_ID or GITHUB_APP_ID environment variable is missing.")

    private_key = get_private_key()
    now = int(time.time())

    payload = {
        "iat": now - 60,  # 60s in the past to allow for clock drift
        "exp": now + (10 * 60),  # expires in 10 minutes
        "iss": APP_ID,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """
    Exchange the App JWT for a temporary installation access token.
    The resulting token is scoped to the installation and valid for 1 hour.
    """
    app_jwt = get_app_jwt()
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"

    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data["token"]


async def get_pr_diff(repo: str, pull_number: int, installation_token: str) -> str:
    """
    Fetch the raw unified git diff for a pull request.
    Example: repo='owner/repo_name', pull_number=42
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pull_number}"

    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


async def post_pr_comment(
    repo: str,
    pull_number: int,
    body: str,
    installation_token: str,
) -> dict[str, Any]:
    """
    Post a review comment to the pull request as the GitHub App bot.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pull_number}/comments"

    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }

    payload = {"body": body}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
