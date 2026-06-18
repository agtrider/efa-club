"""Supabase + local JSON persistence — no Streamlit dependency."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from efa_club_services import normalize_meeting_record

DATA_DIR = Path("local_data")
DATA_DIR.mkdir(exist_ok=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = None
try:
    from supabase import create_client
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
except Exception:
    supabase = None

_LAST_SUPABASE_ERROR = ""


def get_last_supabase_error():
    return _LAST_SUPABASE_ERROR


def load_from_supabase(key, default=None):
    if supabase is None:
        return default
    try:
        response = supabase.table("club_data").select("data").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("data", {}).get(key, default)
        return default
    except Exception as e:
        print(f"Supabase load error for {key}: {e}")
        return default


def save_to_supabase(key, value):
    global _LAST_SUPABASE_ERROR
    if supabase is None:
        _LAST_SUPABASE_ERROR = "Supabase not connected (check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on Render)."
        return False
    _LAST_SUPABASE_ERROR = ""
    for attempt in range(3):
        try:
            current = supabase.table("club_data").select("data").eq("id", 1).execute()
            if not current.data:
                _LAST_SUPABASE_ERROR = "club_data table row missing (id=1). Run the Supabase schema setup."
                return False
            data_dict = current.data[0].get("data", {}) or {}
            if not isinstance(data_dict, dict):
                data_dict = {}
            data_dict[key] = value
            supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
            return True
        except Exception as e:
            _LAST_SUPABASE_ERROR = str(e)
            print(f"Supabase save error for {key} (attempt {attempt + 1}): {e}")
    return False


def load_json(filename, default=None):
    try:
        if (DATA_DIR / filename).exists():
            with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default or [] if isinstance(default, list) else (default or {})


def save_json(filename, data):
    try:
        with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Failed to save {filename}: {e}")
        return False


def load_last_prices():
    supa_prices = load_from_supabase("last_prices", None)
    if supa_prices and isinstance(supa_prices, dict) and len(supa_prices) > 0:
        return supa_prices
    return load_json("last_prices.json", {})


def save_last_prices(prices_dict):
    save_json("last_prices.json", prices_dict)
    try:
        save_to_supabase("last_prices", prices_dict)
    except Exception:
        pass


def clear_price_cache(tickers=None):
    last_prices = load_last_prices()
    if tickers:
        for t in tickers:
            last_prices.pop(str(t).upper().strip(), None)
    else:
        last_prices = {}
    save_last_prices(last_prices)


def purge_invalid_price_cache():
    last_prices = load_last_prices()
    dirty = [k for k, v in last_prices.items() if str(v.get("source", "")).lower() == "csv_fill"]
    if not dirty:
        return
    for k in dirty:
        last_prices.pop(k, None)
    save_last_prices(last_prices)


def load_members(default_names):
    return load_from_supabase("members", [{"name": name, "total_contributed": 0.0} for name in default_names])


def save_members(members_list):
    return save_to_supabase("members", members_list)


def load_transactions():
    return load_from_supabase("transactions", [])


def save_transactions(transactions_list):
    return save_to_supabase("transactions", transactions_list)


def load_comments():
    return load_from_supabase("comments", [])


def save_comments(comments_list):
    return save_to_supabase("comments", comments_list)


def load_watchlist():
    supa = load_from_supabase("watchlist", None)
    if supa and isinstance(supa, list) and len(supa) > 0:
        return supa
    local = load_json("watchlist.json", [])
    return local if isinstance(local, list) else []


def save_watchlist(watchlist):
    save_json("watchlist.json", watchlist)
    try:
        save_to_supabase("watchlist", watchlist)
    except Exception:
        pass
    return True


def load_investment_goals():
    return load_from_supabase("investment_goals", {})


def save_investment_goals(goals):
    return save_to_supabase("investment_goals", goals)


def load_analysis_history():
    return load_from_supabase("analysis_history", [])


def save_analysis_history(history):
    return save_to_supabase("analysis_history", history)


def load_polls():
    supa = load_from_supabase("polls", None)
    if supa and isinstance(supa, list) and len(supa) > 0:
        return supa
    local = load_json("polls.json", [])
    return local if isinstance(local, list) else []


def save_polls(polls_list):
    local_ok = save_json("polls.json", list(polls_list or []))
    if supabase is None:
        return local_ok
    return save_to_supabase("polls", polls_list)


def load_availability_responses():
    supa = load_from_supabase("availability_responses", None)
    if supa and isinstance(supa, dict) and len(supa) > 0:
        return supa
    local = load_json("availability_responses.json", {})
    return local if isinstance(local, dict) else {}


def save_availability_responses(responses_dict):
    payload = responses_dict if isinstance(responses_dict, dict) else {}
    local_ok = save_json("availability_responses.json", payload)
    if supabase is None:
        return local_ok
    return save_to_supabase("availability_responses", payload)


def load_finalized_meetings():
    supa = load_from_supabase("finalized_meetings", None)
    if supa and isinstance(supa, list) and len(supa) > 0:
        return [normalize_meeting_record(m) for m in supa]
    local = load_json("finalized_meetings.json", [])
    meetings = local if isinstance(local, list) else []
    return [normalize_meeting_record(m) for m in meetings]


def save_finalized_meetings(meetings):
    cleaned = [normalize_meeting_record(m) for m in meetings]
    local_ok = save_json("finalized_meetings.json", cleaned)
    if supabase is None:
        return local_ok
    return save_to_supabase("finalized_meetings", cleaned)


def load_meeting_attachment_store():
    supa = load_from_supabase("meeting_attachment_store", None)
    if supa and isinstance(supa, dict) and len(supa) > 0:
        return supa
    local = load_json("meeting_attachment_store.json", {})
    return local if isinstance(local, dict) else {}


def save_meeting_attachment_store(store):
    if not isinstance(store, dict):
        store = {}
    local_ok = save_json("meeting_attachment_store.json", store)
    if supabase is None:
        return local_ok
    return save_to_supabase("meeting_attachment_store", store)


def load_access_log():
    return load_from_supabase("access_log", [])


def save_access_log(entries):
    return save_to_supabase("access_log", entries)


def load_grok_analyses():
    return load_from_supabase("grok_analyses", [])


def save_grok_analyses(analyses):
    return save_to_supabase("grok_analyses", analyses)


def load_member_sessions():
    return load_from_supabase("member_sessions", {})


def save_member_sessions(sessions):
    return save_to_supabase("member_sessions", sessions)