import os
from supabase import create_client
from supabase._async.client import create_client as async_create_client
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

_async_client = None

async def get_async_supabase():
    global _async_client
    if _async_client is None:
        _async_client = await async_create_client(SUPABASE_URL, SUPABASE_KEY)
    return _async_client