import os

import valkey.asyncio as valkey_async
from dotenv import load_dotenv

load_dotenv()

VALKEY_URI = os.getenv("VALKEY_URI", "valkey://localhost:6379")

client = valkey_async.Valkey.from_url(VALKEY_URI, decode_responses=True)
