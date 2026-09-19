import json
import os

import httpx2 as httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from diffly.agents.prompts import (
    AGGREGATOR_PROMPT,
    LOGIC_PROMPT,
    PERFORMANCE_PROMPT,
    SECURITY_PROMPT,
)
from diffly.agents.schema import AgentReviewResult

load_dotenv()

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT") or os.getenv(
    "NARA_ROUTER_ENDPOINT", "https://api.hcnsec.cn/v1"
)
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("NARA_ROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "auto")


async def _sanitize_response(response: httpx.Response) -> None:
    """Sanitize non-standard metadata from response before Pydantic SDK validation."""
    if "application/json" in response.headers.get("content-type", ""):
        await response.aread()
        try:
            data = json.loads(response.text)
            if (
                isinstance(data, dict)
                and "metadata" in data
                and isinstance(data["metadata"], dict)
            ):
                for k, v in data["metadata"].items():
                    if not isinstance(v, str):
                        data["metadata"][k] = json.dumps(v)
                response._content = json.dumps(data).encode("utf-8")
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass


http_client = httpx.AsyncClient(
    timeout=90.0,
    event_hooks={"response": [_sanitize_response]},
)

openai_client = AsyncOpenAI(
    base_url=LLM_ENDPOINT,
    api_key=LLM_API_KEY,
    max_retries=3,
    http_client=http_client,
)

provider = OpenAIProvider(
    openai_client=openai_client,
)

# Native tool calling enabled!
model = OpenAIChatModel(
    LLM_MODEL,
    provider=provider,
)

security_agent = Agent(
    model=model,
    system_prompt=SECURITY_PROMPT,
    output_type=AgentReviewResult,
)

logic_agent = Agent(
    model=model,
    system_prompt=LOGIC_PROMPT,
    output_type=AgentReviewResult,
)

performance_agent = Agent(
    model=model,
    system_prompt=PERFORMANCE_PROMPT,
    output_type=AgentReviewResult,
)

aggregator_agent = Agent(
    model=model,
    system_prompt=AGGREGATOR_PROMPT,
    output_type=AgentReviewResult,
)
