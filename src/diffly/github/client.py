import os
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
from dotenv import load_dotenv

from diffly.agents.schema import ReviewSchema

load_dotenv()

APP_ID = os.getenv("APP_ID") or os.getenv("GITHUB_APP_ID")
PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "difflybot.pem")

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


def get_private_key() -> str:
    """Load the RSA private key from the configured path."""
    key_file = Path(PRIVATE_KEY_PATH)
    if not key_file.exists():
        raise FileNotFoundError(f"GitHub private key not found at: {key_file.resolve()}")
    return key_file.read_text()


def get_app_jwt() -> str:
    """Generate an RS256-signed JWT for GitHub App authentication (valid for 10m)."""
    if not APP_ID:
        raise ValueError("APP_ID or GITHUB_APP_ID environment variable is missing.")

    private_key = get_private_key()
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": APP_ID,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def _gh_request(
    method: str,
    path: str,
    token: str,
    *,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an authenticated GitHub API request with standard headers and timeout."""
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if headers:
        req_headers.update(headers)

    url = f"{GITHUB_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.request(method, url, headers=req_headers, **kwargs)
        response.raise_for_status()
        return response


async def get_installation_token(installation_id: int) -> str:
    """Exchange the App JWT for a temporary installation access token (valid 1 hour)."""
    app_jwt = get_app_jwt()
    res = await _gh_request("POST", f"/app/installations/{installation_id}/access_tokens", app_jwt)
    data: dict[str, Any] = res.json()
    return data["token"]


async def get_pr_diff(repo: str, pull_number: int, installation_token: str) -> str:
    """Fetch the raw unified git diff for a pull request."""
    res = await _gh_request(
        "GET",
        f"/repos/{repo}/pulls/{pull_number}",
        installation_token,
        headers={"Accept": "application/vnd.github.v3.diff"},
    )
    return res.text


async def create_check_run(
    repo: str,
    installation_token: str,
    head_sha: str,
    name: str = "Diffly Code Review",
    status: str = "in_progress",
    conclusion: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a check run for the given repository and head SHA."""
    payload: dict[str, Any] = {
        "head_sha": head_sha,
        "name": name,
        "status": status,
    }
    if conclusion is not None:
        payload["conclusion"] = conclusion
    if output is not None:
        payload["output"] = output

    res = await _gh_request("POST", f"/repos/{repo}/check-runs", installation_token, json=payload)
    return res.json()


async def update_check_run(
    repo: str,
    installation_token: str,
    check_run_id: int,
    status: str = "completed",
    conclusion: str | None = "neutral",
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a check run for the given repository and check run ID."""
    payload: dict[str, Any] = {"status": status}
    if conclusion is not None:
        payload["conclusion"] = conclusion
    if output is not None:
        payload["output"] = output

    res = await _gh_request("PATCH", f"/repos/{repo}/check-runs/{check_run_id}", installation_token, json=payload)
    return res.json()


async def create_pr_review(
    repo: str,
    installation_token: str,
    pull_number: int,
    body: str,
    comments: list[dict[str, Any]] | None = None,
    event: str = "COMMENT",
) -> dict[str, Any]:
    """Create a PR review with summary body and atomic inline code comments."""
    payload: dict[str, Any] = {"event": event, "body": body}
    if comments:
        payload["comments"] = comments

    res = await _gh_request("POST", f"/repos/{repo}/pulls/{pull_number}/reviews", installation_token, json=payload)
    return res.json()


def format_review_comment(finding: ReviewSchema) -> str:
    """Format a finding into a crisp, professional GitHub review comment."""
    from diffly.guardrails import sanitize_review_output

    parts = [
        f"**Issue:** {finding.title}",
        f"**Severity:** `{finding.severity.value.upper()}`",
        "",
        sanitize_review_output(finding.description.strip()),
    ]

    if finding.suggestion:
        clean_code = finding.suggestion.strip()
        # Strip redundant markdown fences if the LLM wrapped it already
        if clean_code.startswith("```") and clean_code.endswith("```"):
            lines = clean_code.splitlines()
            clean_code = "\n".join(lines[1:-1]).strip()

        clean_code = sanitize_review_output(clean_code)

        parts.extend(
            [
                "",
                "#### Suggested Fix",
                "```suggestion",
                clean_code,
                "```",
            ]
        )

    return "\n".join(parts)


async def add_pr_reaction(
    repo: str,
    pull_number: int,
    installation_token: str,
    reaction: str = "rocket",
) -> dict[str, Any]:
    """Add an emoji reaction ('rocket', 'eyes') to PR description for instant visual UX."""
    res = await _gh_request(
        "POST",
        f"/repos/{repo}/issues/{pull_number}/reactions",
        installation_token,
        json={"content": reaction},
    )
    return res.json()
