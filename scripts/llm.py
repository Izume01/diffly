import asyncio
import json
import os

import httpx2 as httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "https://api.hcnsec.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "auto")


async def _sanitize(resp: httpx.Response) -> None:
    if "application/json" in resp.headers.get("content-type", ""):
        await resp.aread()
        try:
            d = json.loads(resp.text)
            if isinstance(d.get("metadata"), dict):
                for k, v in d["metadata"].items():
                    if not isinstance(v, str):
                        d["metadata"][k] = json.dumps(v)
            resp._content = json.dumps(d).encode()
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass


http_client = httpx.AsyncClient(timeout=60.0, event_hooks={"response": [_sanitize]})
openai_client = AsyncOpenAI(
    base_url=LLM_ENDPOINT, api_key=LLM_API_KEY, http_client=http_client
)
provider = OpenAIProvider(openai_client=openai_client)
model = OpenAIChatModel(LLM_MODEL, provider=provider)

agent = Agent(model=model)


async def main() -> None:
    result = await agent.run(
        user_prompt="Hi, How are you?",
    )
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
