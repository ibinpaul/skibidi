from supabase import create_client
import os, sys

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Set SUPABASE_URL and SUPABASE_KEY in your environment or .env file")
    sys.exit(1)

client = create_client(url, key)
try:
    res = client.table("format_dictionary").select("*").limit(3).execute()
    data = getattr(res, 'data', None)
    if data is None:
        # Some supabase clients return a tuple (data, count)
        try:
            data = res[0]
        except Exception:
            data = None
    print("OK, rows:", len(data) if data else 0)
    if data:
        print(data[:3])
    else:
        print(res)
except Exception as e:
    print("Supabase error:", e)
    sys.exit(2)
