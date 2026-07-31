import sys
sys.path.insert(0, '.')
import supabase_config
from THE_BACKEND import ibin

client = supabase_config.create_supabase_client()
print('CLIENT_OK=', client is not None)
if client is not None:
    try:
        res = client.table('cinemas').select('cinema_id').limit(1).execute()
        print('CINEMAS_OK=', bool(res.data))
    except Exception as e:
        print('CINEMAS_ERR=', repr(e))
    try:
        res = client.table('screens').select('screen_id').limit(1).execute()
        print('SCREENS_OK=', bool(res.data))
    except Exception as e:
        print('SCREENS_ERR=', repr(e))
    try:
        res = client.table('format_dictionary').select('format_name').limit(1).execute()
        print('FORMAT_DICT_OK=', bool(res.data))
    except Exception as e:
        print('FORMAT_DICT_ERR=', repr(e))
    try:
        provider = ibin.SupabaseDataProvider(supabase_config.get_supabase_credentials()[0], supabase_config.get_supabase_credentials()[1])
        print('PROVIDER_OK=', bool(provider.supabase))
        print('THEATERS=', provider.get_available_theaters())
    except Exception as e:
        print('PROVIDER_ERR=', repr(e))
