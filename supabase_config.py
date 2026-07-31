import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
for env_path in [ROOT_DIR / ".env", ROOT_DIR / ".env.local", ROOT_DIR / ".env.example"]:
    if env_path.exists():
        load_dotenv(env_path, override=False)


def get_supabase_credentials() -> Tuple[Optional[str], Optional[str]]:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    return (url or None), (key or None)


def create_supabase_client():
    from supabase import create_client

    url, key = get_supabase_credentials()
    if not url or not key:
        return None
    return create_client(url, key)
