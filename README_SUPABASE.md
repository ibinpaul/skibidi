# Supabase setup

1. Copy .env.example to .env.
2. Fill in your Supabase project URL and anon/service role key.
3. Run the app normally.

The code uses Supabase when both SUPABASE_URL and SUPABASE_KEY are present. If they are missing, it falls back to the mock data provider so the workspace still runs.
