import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np
import json
from pathlib import Path
import os
import pytz
import requests

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="EFA Investment Club",
    layout="wide",
    page_icon="🔥",
    initial_sidebar_state="expanded"
)

# ====================== SUPABASE CONFIG ======================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
except Exception:
    supabase = None

# ====================== SUPABASE CONNECTION TEST (Detailed) ======================
if supabase:
    try:
        # Test 1: Can we even reach the project?
        test = supabase.table("club_data").select("id").limit(1).execute()
        st.sidebar.success("✅ Supabase Connected & Working")
        
        # Test 2: Does the club_data table exist?
        if test.data is not None:
            st.sidebar.info("✅ club_data table found")
        else:
            st.sidebar.warning("⚠️ club_data table does NOT exist — run the SQL script")
            
    except Exception as e:
        error_msg = str(e)
        st.sidebar.error(f"❌ Supabase Error: {error_msg[:120]}")
        print("FULL SUPABASE ERROR:", error_msg)   # This will show in terminal
else:
    st.sidebar.error("❌ Supabase NOT Connected (running local only)")

# ====================== FINNHUB CLIENT (for reliable current quotes - already used for news/filings in Tab 8) ======================
FINNHUB_CLIENT = None
try:
    _fh_key = os.environ.get("FINNHUB_API_KEY")
    if _fh_key:
        import finnhub
        FINNHUB_CLIENT = finnhub.Client(api_key=_fh_key)
except Exception:
    FINNHUB_CLIENT = None

# ====================== SUPABASE PERSISTENCE HELPERS ======================
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
    if supabase is None:
        return False
    try:
        current = supabase.table("club_data").select("data").eq("id", 1).execute()
        data_dict = current.data[0].get("data", {}) if current.data else {}
        data_dict[key] = value
        supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
        return True
    except Exception as e:
        print(f"Supabase save error for {key}: {e}")
        return False

# ====================== ALL DATA FUNCTIONS (Supabase) ======================
def load_members():
    return load_from_supabase("members", [{"name": name, "total_contributed": 0.0} for name in MEMBER_CREDENTIALS.keys()])

def save_members(members_list):
    save_to_supabase("members", members_list)

def load_transactions():
    return load_from_supabase("transactions", [])

def save_transactions(transactions_list):
    save_to_supabase("transactions", transactions_list)

def load_comments():
    return load_from_supabase("comments", [])

def save_comments(comments_list):
    save_to_supabase("comments", comments_list)

def post_deploy_comment_once(marker, text):
    """Post a one-time deployment notice to the Comments tab (Supabase)."""
    if supabase is None:
        return
    try:
        comments = load_comments() or []
        if any(marker in str(c.get("text", "")) for c in comments):
            return
        comments.insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "author": "System",
            "text": text,
            "resolved": False
        })
        save_comments(comments)
    except Exception as e:
        print(f"[deploy comment] Error: {e}")

def load_watchlist():
    return load_from_supabase("watchlist", [])

def save_watchlist(watchlist):
    save_to_supabase("watchlist", watchlist)

def load_investment_goals():
    return load_from_supabase("investment_goals", {})

def save_investment_goals(goals):
    save_to_supabase("investment_goals", goals)

def load_analysis_history():
    return load_from_supabase("analysis_history", [])

def save_analysis_history(history):
    save_to_supabase("analysis_history", history)

def load_polls():
    return load_from_supabase("polls", [])

def save_polls(polls_list):
    save_to_supabase("polls", polls_list)

def load_availability_responses():
    return load_from_supabase("availability_responses", {})

def save_availability_responses(responses_dict):
    save_to_supabase("availability_responses", responses_dict)

def normalize_availability_responses(responses, proposals):
    """Migrate old flat {username: [slots]} format to per-poll {poll_key: {username: [slots]}}.

    Smart attach: prefer the poll whose week dates appear in the legacy slot strings.
    Falls back to the oldest poll (proposals[0]). This ensures:
    - Existing proposals keep their historical availability data.
    - Any newly created polls (even if created right after deploy before migration runs) start at zero.
    """
    if not responses or not isinstance(responses, dict):
        return {}
    sample = next(iter(responses.values()), None)
    if isinstance(sample, (list, tuple)):
        # Old flat format detected. Collect all legacy slot strings.
        legacy_slots = []
        for lst in responses.values():
            if isinstance(lst, (list, tuple)):
                legacy_slots.extend(lst)
        legacy_text = " ".join(str(s) for s in legacy_slots)

        target_key = None
        if proposals:
            # 1. Try to find a poll whose week_start or week_end appears in the legacy slots.
            for poll in proposals:
                ws = poll.get("week_start", "")
                we = poll.get("week_end", "")
                if (ws and ws in legacy_text) or (we and we in legacy_text):
                    target_key = str(poll.get("id", proposals.index(poll) + 1))
                    break
            # 2. Fallback: attach legacy data to the oldest poll so previous proposals keep their data.
            if target_key is None:
                first_poll = proposals[0]
                target_key = str(first_poll.get("id", 1))
            # Build the migrated dict with legacy under the chosen key only.
            # Newer polls (higher ids) will not receive it → they start at zero responses.
            return {target_key: responses}
        return {}
    return responses

def load_finalized_meetings():
    return load_from_supabase("finalized_meetings", [])

def save_finalized_meetings(meetings):
    save_to_supabase("finalized_meetings", meetings)

def load_grok_analyses():
    return load_from_supabase("grok_analyses", [])

def save_grok_analyses(analyses):
    save_to_supabase("grok_analyses", analyses)

# ====================== LOCAL JSON HELPERS + SUPABASE SYNC FOR PRICE CACHE ======================
DATA_DIR = Path("local_data")
DATA_DIR.mkdir(exist_ok=True)

def load_json(filename, default=None):
    try:
        if (DATA_DIR / filename).exists():
            with open(DATA_DIR / filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return default or [] if isinstance(default, list) else (default or {})

def save_json(filename, data):
    try:
        with open(DATA_DIR / filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Failed to save {filename}: {e}")
        return False

def load_last_prices():
    """Load last known good prices. Tries Supabase first (shared), falls back to local JSON."""
    # Try Supabase shared cache
    supa_prices = load_from_supabase("last_prices", None)
    if supa_prices and isinstance(supa_prices, dict) and len(supa_prices) > 0:
        return supa_prices
    # Fallback to local file (works offline / first run)
    return load_json("last_prices.json", {})

def save_last_prices(prices_dict):
    """Save to BOTH local JSON (fast) and Supabase (shared across all members/sessions)."""
    save_json("last_prices.json", prices_dict)
    # Also persist to Supabase so new team members / cloud deploys see recent prices immediately
    try:
        save_to_supabase("last_prices", prices_dict)
    except Exception:
        pass  # Non-fatal; local copy is still good

def clear_price_cache(tickers=None):
    """Drop cached quotes so the next fetch must pull fresh data (used by Force Refresh)."""
    last_prices = load_last_prices()
    if tickers:
        for t in tickers:
            last_prices.pop(str(t).upper().strip(), None)
    else:
        last_prices = {}
    save_last_prices(last_prices)

def purge_invalid_price_cache():
    """Remove poisoned cache entries (e.g. csv_fill purchase prices saved as market quotes)."""
    last_prices = load_last_prices()
    dirty = [k for k, v in last_prices.items() if str(v.get("source", "")).lower() == "csv_fill"]
    if not dirty:
        return
    for k in dirty:
        last_prices.pop(k, None)
    save_last_prices(last_prices)
    print(f"[price cache] purged invalid csv_fill entries: {dirty}")

def _yf_history(stock, **kwargs):
    """yfinance 1.x removed progress= — strip it so history calls don't fail silently on Render."""
    kwargs.pop("progress", None)
    return stock.history(**kwargs)

def _yf_download(ticker, **kwargs):
    kwargs.pop("progress", None)
    return yf.download(ticker, **kwargs)

def _extract_close_series(df):
    """Normalize yf.download output to a single Close series."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        close_col = df["Close"]
        if isinstance(close_col, pd.DataFrame):
            return close_col.iloc[:, 0]
        return close_col
    return df["Close"]

def fetch_finnhub_quote(tkr):
    """Finnhub real-time quote — optional API when FINNHUB_API_KEY is set."""
    if FINNHUB_CLIENT is None:
        return 0.0, ""
    try:
        q = FINNHUB_CLIENT.quote(tkr)
        c = q.get("c") if q else None
        if c and float(c) > 0:
            return float(c), " (finnhub quote)"
    except Exception as e:
        print(f"[finnhub quote] {tkr}: {e}")
    return 0.0, ""


_YAHOO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _yahoo_chart_request(tkr, params):
    """Hit Yahoo chart API (query1, then query2). More reliable than yfinance scraping on cloud hosts."""
    for host in ("query1", "query2"):
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/{tkr}",
                params=params,
                headers={"User-Agent": _YAHOO_UA},
                timeout=12,
            )
            if r.status_code == 200:
                results = (r.json().get("chart") or {}).get("result") or []
                if results:
                    return results[0]
        except Exception as e:
            print(f"[yahoo chart] {tkr} via {host}: {e}")
    return None


def _chart_closes(res):
    """Extract (timestamps, close prices) from a Yahoo chart result."""
    timestamps = res.get("timestamp") or []
    closes = (res.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
    return timestamps, closes


def _meta_price(meta, *keys):
    """Return first positive float found in chart meta for the given keys."""
    for key in keys:
        val = meta.get(key)
        if val is not None:
            try:
                price = float(val)
                if price > 0:
                    return price
            except (TypeError, ValueError):
                pass
    return 0.0


def _close_on_date(timestamps, closes, target_date_str):
    """Return the daily close for target_date_str from chart bars."""
    if not timestamps or not closes:
        return 0.0
    et = pytz.timezone("US/Eastern")
    for ts, c in zip(reversed(timestamps), reversed(closes)):
        if c is None:
            continue
        try:
            price = float(c)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        day_str = datetime.fromtimestamp(ts, et).strftime("%Y-%m-%d")
        if day_str == target_date_str:
            return price
    return 0.0


def _last_bar_close(timestamps, closes):
    """Most recent non-null close in an intraday series."""
    for c in reversed(closes or []):
        if c is None:
            continue
        try:
            price = float(c)
        except (TypeError, ValueError):
            continue
        if price > 0:
            return price
    return 0.0


def get_market_session():
    """
    US equity session for price selection:
    - open: Mon-Fri 9:30-16:00 ET → latest intraday price
    - premarket: weekday before 9:30 → prior session close
    - afterhours: weekday after 16:00 → today's close
    - weekend: Sat/Sun → last trading day close (Friday)
    """
    try:
        et = pytz.timezone("US/Eastern")
        now = datetime.now(et)
        if now.weekday() >= 5:
            return "weekend"
        open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if now < open_time:
            return "premarket"
        if now < close_time:
            return "open"
        return "afterhours"
    except Exception:
        return "afterhours"


def fetch_yahoo_session_price(tkr, session=None, target_eod=None):
    """
    Session-aware price from Yahoo chart API (no yfinance dependency).
    This is the primary path — works locally and on Render where yfinance often rate-limits.
    """
    session = session or get_market_session()
    target_eod = target_eod or get_last_trading_day_str()

    if session == "open":
        res = _yahoo_chart_request(tkr, {"interval": "1m", "range": "1d"})
        if res:
            meta = res.get("meta") or {}
            price = _meta_price(meta, "regularMarketPrice", "previousClose", "chartPreviousClose")
            if price <= 0:
                ts, closes = _chart_closes(res)
                price = _last_bar_close(ts, closes)
            if price > 0:
                return price, " (yahoo chart live)"

    # Closed sessions: daily bars pinned to the target trading day
    res = _yahoo_chart_request(tkr, {"interval": "1d", "range": "1mo"})
    if res:
        meta = res.get("meta") or {}
        ts, closes = _chart_closes(res)
        price = _close_on_date(ts, closes, target_eod)

        if price <= 0 and session == "afterhours":
            price = _meta_price(meta, "regularMarketPrice")

        if price <= 0 and session in ("premarket", "weekend"):
            price = _meta_price(
                meta,
                "chartPreviousClose",
                "previousClose",
                "regularMarketPreviousClose",
            )

        if price <= 0:
            price = _meta_price(meta, "regularMarketPrice")

        if price <= 0 and closes:
            price = _last_bar_close(ts, closes)

        if price > 0:
            label = {
                "premarket": "prior close",
                "afterhours": "today close",
                "weekend": "last session close",
            }.get(session, "EOD")
            return price, f" (yahoo chart {label} / {target_eod})"

    return 0.0, ""


def fetch_yahoo_chart(tkr, target_date_str=None, live=False):
    """Backward-compatible wrapper around the session-aware Yahoo fetcher."""
    if live:
        return fetch_yahoo_session_price(tkr, session="open")
    if target_date_str:
        return fetch_yahoo_session_price(tkr, session="afterhours", target_eod=target_date_str)
    return fetch_yahoo_session_price(tkr)


def _fast_info_price(fi, *keys):
    """Read a positive price from yfinance fast_info (camelCase keys in yfinance 1.x)."""
    if not fi:
        return 0.0
    getter = getattr(fi, "get", None)
    for key in keys:
        val = getter(key) if getter else getattr(fi, key, None)
        if val is not None:
            try:
                price = float(val)
                if price > 0:
                    return price
            except (TypeError, ValueError):
                pass
    return 0.0


def _cached_market_price(tkr, prefer_eod=None):
    """Return last known good market price from Supabase/local cache (never csv_fill)."""
    cached = load_last_prices().get(tkr, {})
    price = float(cached.get("price", 0) or 0)
    if price <= 0:
        return 0.0, ""
    src = str(cached.get("source", "")).lower()
    if src == "csv_fill":
        return 0.0, ""
    note = cached.get("timestamp", "") or "cached"
    return price, f" (cached: {note})"

# ====================== FORCE FRESH LOAD (Now Safe) ======================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "investment_goals" not in st.session_state:
    st.session_state.investment_goals = load_investment_goals()
if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = load_analysis_history()

# ====================== GROK API CLIENT ======================
from openai import OpenAI

if os.environ.get("GROK_API_KEY"):
    client = OpenAI(
        api_key=os.environ.get("GROK_API_KEY"),
        base_url="https://api.x.ai/v1"
    )
    st.success("✅ Grok API client initialized")
else:
    client = None
    st.warning("⚠️ Grok API key not found. Grok analysis will not work.")

# ====================== MEMBER LOGIN SYSTEM ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.is_admin = False

MEMBER_CREDENTIALS = {
    "Antonio Calderon": {"email": "acal721@gmail.com", "password": "EFAIC2026001CA"},
    "Chris Koo": {"email": "Chris.b.koo@outlook.com", "password": "EFAIC2026002KC"},
    "Josh Tafoya": {"email": "Joshtafoya01@gmail.com", "password": "EFAIC2026003TJ"},
    "Jeff Gragert": {"email": "Jagragert@gmail.com", "password": "EFAIC2026004GJ"},
    "Nick Vigil": {"email": "Nbvigil24@hotmail.com", "password": "EFAIC2026005VN"},
    "Ray Gilkes": {"email": "Bison1867@gmail.com", "password": "EFAIC2026006GR"},
    "Jose Calderon": {"email": "Josecalderon036@gmail.com", "password": "EFAIC2026007CJ"},
    "Chad Speegle": {"email": "Chad.speegle@gmail.com", "password": "EFAIC2026008SC"},
    "Jadyn Tafoya": {"email": "Jadynty21@gmail.com", "password": "EFAIC2026009TJ"},
    "Matt Newbill": {"email": "Matthew.Newbill@gmail.com", "password": "EFAIC20260010NM"},
    "Mike Brooks": {"email": "Mikeb1120@gmail.com", "password": "EFAIC20260011BM"}
}

def login_page():
    st.title("🔥 EFA Investment Club")
    st.subheader("Member Login")
    username = st.selectbox("Select your name", options=list(MEMBER_CREDENTIALS.keys()))
    email_input = st.text_input("Email (Login ID)", value=MEMBER_CREDENTIALS[username]["email"], disabled=True)
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary") or password == MEMBER_CREDENTIALS[username]["password"]:
        if password == MEMBER_CREDENTIALS[username]["password"]:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.is_admin = (username == "Antonio Calderon")
            st.success(f"✅ Welcome back, {username}!")
            st.rerun()
        else:
            st.error("❌ Incorrect password.")

if not st.session_state.logged_in:
    login_page()
    st.stop()

# ====================== STYLING ======================
st.markdown("""
    <style>
    body { font-size: 1.1em; }
    .stDataFrame { font-size: 1.05em; }
    .total-row { font-weight: bold; font-size: 1.15em; background-color: #1e1e1e; }
    .stDataFrame th[data-field="total_contributed"],
    .stDataFrame th[data-field="total_invested"],
    .stDataFrame th[data-field="fees"],
    .stDataFrame th[data-field="current_balance"] {
        text-align: right !important;
    }
    .bible-box {
        background-color: #4B0082;
        color: white;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 25px;
        border-left: 6px solid #9370DB;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        max-width: 70%;
    }
    .portfolio-summary {
        background-color: #1e1e1e;
        padding: 18px;
        border-radius: 12px;
        border-left: 5px solid #9370DB;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title(f"🔥 EFA Investment Club - Welcome, {st.session_state.username}")
if st.session_state.is_admin:
    st.caption("👑 Admin Mode")

# ====================== HELPER: LAST KNOWN TRADE PRICE FROM TRANSACTIONS ======================
def get_last_trade_price(ticker):
    """Return the most recent fill price recorded in our transactions for this ticker.
    This is the safety net for newly added positions when live yfinance is down or rate-limited.
    """
    try:
        txns = []
        if "data" in globals() and isinstance(data, dict):
            txns = data.get("transactions", []) or []
        else:
            txns = load_transactions()
        relevant = []
        tkr = str(ticker).upper().strip()
        for t in txns:
            if str(t.get("ticker", "")).upper().strip() == tkr:
                p = float(t.get("price", 0) or 0)
                if p > 0:
                    relevant.append((str(t.get("date", "")), p))
        if not relevant:
            return 0.0
        relevant.sort(key=lambda x: x[0], reverse=True)
        return float(relevant[0][1])
    except Exception:
        return 0.0


def get_price_with_source(ticker):
    """Returns (price, source_label) for the diagnostics column in Tab 2.
    Clearly distinguishes live intraday (during market hours) vs final daily EOD close (after hours).
    Uses enhanced metadata when available (backward compatible with old cache entries).
    """
    tkr = str(ticker).upper().strip()
    if not tkr or tkr in ("CASH", "-"):
        return 0.0, "zero"

    token = st.session_state.get("price_refresh_token")
    price = get_price(tkr, _refresh_token=token)

    last_prices = load_last_prices()
    meta = last_prices.get(tkr, {})
    ts = meta.get("timestamp", "") or ""
    src = meta.get("source", "").lower()
    as_of = meta.get("as_of", "")

    # New structured source takes precedence
    if src == "eod_close" or "eod" in src:
        label = "Final Daily Close (EOD)"
        if as_of:
            label += f" — as of {as_of}"
        else:
            label += f" — as of {get_last_trading_day_str()}"
        return price, label
    if src == "intraday":
        label = "Live / Most Recent (Intraday)"
        if as_of:
            label += f" {as_of}"
        return price, label

    # Legacy timestamp string fallback (for old cached entries) + recognition of new sources
    if "CSV fill" in ts:
        return price, "CSV fill (first time - no yfinance data yet)"
    elif "yahoo chart" in ts.lower():
        if "live" in ts.lower():
            label = "Live (Yahoo chart)"
        elif "prior close" in ts.lower() or "premarket" in ts.lower():
            label = "Prior Close (Yahoo chart)"
        elif "today close" in ts.lower() or "afterhours" in ts.lower():
            label = "Today's Close (Yahoo chart)"
        else:
            label = "EOD Close (Yahoo chart)"
        if as_of:
            label += f" — {as_of}"
        return price, label
    elif "finnhub" in ts.lower():
        if "previous close" in ts.lower() or "EOD" in ts:
            label = "Final Daily Close (EOD, finnhub)"
        else:
            label = "Live (finnhub)"
        if as_of:
            label += f" {as_of}"
        return price, label
    elif "fast_info" in ts.lower():
        if "previous" in ts.lower() or "EOD" in ts:
            label = "Final Daily Close (EOD, fast_info)"
        else:
            label = "Live / Most Recent (fast_info)"
        if as_of:
            label += f" {as_of}"
        return price, label
    elif "previous close" in ts.lower() or "EOD" in ts or "daily close" in ts.lower():
        label = "Final Daily Close (EOD)"
        if as_of:
            label += f" {as_of}"
        return price, label
    elif "intraday" in ts.lower() or "current" in ts.lower():
        label = "Live / Most Recent (Intraday)"
        if as_of:
            label += f" {as_of}"
        return price, label
    elif "yfinance" in ts:
        return price, "Last yfinance price (check time)"
    elif price > 0:
        return price, "Cached (last good price)"
    else:
        return price, "zero"


# ====================== PRICE FETCHER - SESSION-AWARE MARKET PRICE ======================
@st.cache_data(ttl=180)
def get_price(ticker, _refresh_token=None):
    """
    Always returns the best available market price:
    - Before open (premarket): prior session close
    - During regular hours: latest intraday price
    - After close / weekend: that trading day's close
    - If live fetch fails: last cached market price (never a purchase fill)

    Primary source is Yahoo's chart API (direct HTTP). yfinance is backup only —
    it rate-limits heavily on cloud hosts and fast_info keys changed in 1.x (lastPrice).
    """
    tkr = str(ticker).upper().strip()
    if not tkr or tkr in ("CASH", "-"):
        return 0.0

    session = get_market_session()
    is_open = session == "open"
    target_eod = get_last_trading_day_str()
    final_price = 0.0
    source_note = ""

    try:
        # 1. Yahoo chart API — most reliable path (no yfinance scraping)
        final_price, source_note = fetch_yahoo_session_price(tkr, session=session, target_eod=target_eod)

        # 2. Finnhub (if API key configured)
        if final_price == 0:
            final_price, source_note = fetch_finnhub_quote(tkr)
            if final_price > 0 and is_open:
                source_note = source_note.replace("quote", "live")

        # 3. yfinance fallbacks (only when Yahoo/Finnhub miss)
        if final_price == 0:
            stock = yf.Ticker(tkr)
            fi = {}
            try:
                fi = getattr(stock, "fast_info", {}) or {}
            except Exception:
                fi = {}

            if is_open:
                final_price = _fast_info_price(fi, "lastPrice", "regularMarketPrice", "last_price")
                if final_price > 0:
                    source_note = " (yfinance fast_info lastPrice)"
                if final_price == 0:
                    try:
                        hist = _yf_history(stock, period="1d", interval="1m", prepost=False)
                        if not hist.empty:
                            price = float(hist["Close"].iloc[-1])
                            if price > 0:
                                final_price = price
                                source_note = " (yfinance intraday 1m)"
                    except Exception:
                        pass
            else:
                final_price, source_note = fetch_eod_close(stock, tkr, target_eod)

        if final_price > 0:
            last_prices = load_last_prices()
            src_type = "intraday" if is_open else "eod_close"
            as_of = datetime.now().strftime("%Y-%m-%d") if is_open else target_eod
            last_prices[tkr] = {
                "price": final_price,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M") + source_note,
                "source": src_type,
                "as_of": as_of,
            }
            save_last_prices(last_prices)
            return final_price

        cached_price, _ = _cached_market_price(tkr)
        if cached_price > 0:
            print(f"[get_price] {tkr}: live fetch failed, using cached ${cached_price:.2f}")
            return cached_price

        print(f"[get_price] {tkr}: all sources failed; no cached market price available")
        return 0.0

    except Exception as e:
        print(f"[get_price] {tkr} error: {e}")
        cached_price, _ = _cached_market_price(tkr)
        return cached_price if cached_price > 0 else 0.0


# ====================== MARKET HOURS + AUTO SNAPSHOT HELPERS ======================
def is_us_market_open():
    """Return True only during regular US equity trading hours (Mon-Fri 9:30-16:00 ET)."""
    return get_market_session() == "open"


def is_us_premarket():
    """Weekday before 9:30 ET — previous_close is the correct EOD reference."""
    return get_market_session() == "premarket"


def get_last_trading_day_str():
    """
    Returns the YYYY-MM-DD string for the most recent completed (or completing) trading day.
    Used for automatic daily portfolio snapshot recording so users don't have to remember.
    """
    try:
        et = pytz.timezone("US/Eastern")
        now = datetime.now(et)
        if now.weekday() >= 5:
            # Weekend → attribute to prior Friday
            offset = now.weekday() - 4
            target = now - timedelta(days=offset)
        elif now.hour >= 16:
            # After regular close on a weekday → today is the trading day
            target = now
        else:
            # Weekday before/during market hours → last completed trading day
            target = now - timedelta(days=1)
            while target.weekday() >= 5:
                target -= timedelta(days=1)
        return target.strftime("%Y-%m-%d")
    except Exception:
        # Safe fallback to calendar day
        return datetime.now().strftime("%Y-%m-%d")


def _history_close_on_date(hist, target_date_str):
    """Return the Close for target_date_str from a yfinance daily history DataFrame, or 0.0."""
    if hist is None or hist.empty:
        return 0.0
    try:
        et = pytz.timezone("US/Eastern")
        for idx in reversed(hist.index):
            if hasattr(idx, "tz_convert"):
                day_str = idx.tz_convert(et).strftime("%Y-%m-%d")
            elif hasattr(idx, "strftime"):
                day_str = idx.strftime("%Y-%m-%d")
            else:
                continue
            if day_str == target_date_str:
                price = float(hist.loc[idx, "Close"])
                return price if price > 0 else 0.0
        # Fallback: last row is usually the most recent session when target is last trading day
        price = float(hist["Close"].iloc[-1])
        return price if price > 0 else 0.0
    except Exception:
        return 0.0


def fetch_finnhub_eod_close(tkr, target_date_str):
    """Finnhub daily candle — reliable on Render where yfinance scraping often fails."""
    if FINNHUB_CLIENT is None:
        return 0.0, ""
    try:
        et = pytz.timezone("US/Eastern")
        day = datetime.strptime(target_date_str, "%Y-%m-%d")
        start = et.localize(day.replace(hour=0, minute=0, second=0, microsecond=0))
        end = start + timedelta(days=1)
        candles = FINNHUB_CLIENT.stock_candles(
            tkr, "D", int(start.timestamp()), int(end.timestamp())
        )
        if candles and candles.get("s") == "ok" and candles.get("c"):
            price = float(candles["c"][-1])
            if price > 0:
                return price, f" (finnhub daily candle / EOD {target_date_str})"
    except Exception:
        pass
    return 0.0, ""


def fetch_eod_close(stock, tkr, target_date_str):
    """
    Return (price, source_note) for the regular-session close on target_date_str.
    After hours on 6/11 we want 6/11's close — NOT previous_close/pc (which is 6/10).
    """
    # 1. Finnhub daily candle (best on cloud / Render — proper API, not scraped)
    price, note = fetch_finnhub_eod_close(tkr, target_date_str)
    if price > 0:
        return price, note

    # 2. Yahoo chart API (direct HTTP — reliable when yfinance fails on Render)
    price, note = fetch_yahoo_chart(tkr, target_date_str=target_date_str, live=False)
    if price > 0:
        return price, note

    # 3. yfinance daily history pinned to the target trading day
    try:
        end_dt = datetime.strptime(target_date_str, "%Y-%m-%d") + timedelta(days=1)
        hist = _yf_history(
            stock,
            start=target_date_str,
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
        )
        price = _history_close_on_date(hist, target_date_str)
        if price > 0:
            return price, f" (yfinance daily close {target_date_str})"
    except Exception:
        pass

    try:
        hist = _yf_history(stock, period="10d", interval="1d", auto_adjust=True)
        price = _history_close_on_date(hist, target_date_str)
        if price > 0:
            return price, f" (yfinance daily close {target_date_str})"
    except Exception:
        pass

    try:
        df = _yf_download(tkr, period="10d", auto_adjust=True)
        close_col = _extract_close_series(df)
        if not close_col.empty:
            price = _history_close_on_date(
                pd.DataFrame({"Close": close_col}, index=close_col.index),
                target_date_str,
            )
            if price > 0:
                return price, f" (yfinance download close {target_date_str})"
    except Exception:
        pass

    # 4. Finnhub quote (last traded / session price)
    price, note = fetch_finnhub_quote(tkr)
    if price > 0:
        return price, note + f" / EOD {target_date_str}"

    # 5. fast_info (yfinance 1.x uses camelCase: lastPrice, previousClose)
    if target_date_str == get_last_trading_day_str():
        try:
            fi = getattr(stock, "fast_info", {}) or {}
            price = _fast_info_price(fi, "lastPrice", "regularMarketPrice", "last_price")
            if price > 0:
                return price, f" (yfinance fast_info lastPrice / EOD {target_date_str})"
        except Exception:
            pass

    # 6. Pre-market / weekend: previousClose is the prior completed session
    if get_market_session() in ("premarket", "weekend"):
        try:
            fi = getattr(stock, "fast_info", {}) or {}
            price = _fast_info_price(
                fi, "previousClose", "regularMarketPreviousClose", "previous_close"
            )
            if price > 0:
                return price, f" (yfinance previousClose / EOD {target_date_str})"
        except Exception:
            pass

    return 0.0, ""


def auto_record_eod_snapshot_if_needed(current_portfolio_nav, current_securities_value,
                                       current_cash_balance, cumulative_invested,
                                       current_return_on_invested):
    """
    Automatically records a daily portfolio snapshot (for the two performance graphs)
    when the market is closed / after hours / on weekends, if a snapshot for the
    relevant trading day does not already exist.

    This prevents "forgotten days". The manual "Record" button is still available.
    Uses the (now EOD-aware) current prices so after-hours snapshots are final daily closes.
    """
    if supabase is None:
        return  # cannot persist reliably
    try:
        portfolio_history = load_from_supabase("portfolio_history", []) or []
        target_date = get_last_trading_day_str()

        existing_dates = [str(entry.get("date")) for entry in portfolio_history]
        if target_date in existing_dates:
            return

        # Only auto-record if we have real data
        if current_portfolio_nav is None or current_portfolio_nav <= 0:
            return

        new_snapshot = {
            "date": target_date,
            "portfolio_nav": round(current_portfolio_nav, 2),
            "securities_value": round(current_securities_value, 2),
            "cash_balance": round(current_cash_balance, 2),
            "cumulative_invested": round(cumulative_invested, 2),
            "return_on_invested": round(current_return_on_invested, 4),
            "auto_recorded": True
        }
        portfolio_history.append(new_snapshot)
        portfolio_history = sorted(portfolio_history, key=lambda x: x["date"])
        save_to_supabase("portfolio_history", portfolio_history)

        # One-time UI notification this run
        if "just_auto_recorded_date" not in st.session_state:
            st.session_state.just_auto_recorded_date = target_date
    except Exception as e:
        print(f"[auto snapshot] Error: {e}")


# ====================== TECHNICAL INDICATORS FOR TAB 6 ======================
@st.cache_data(ttl=300)
def get_technical_indicators(ticker, _refresh_token=None):
    try:
        df = _yf_download(ticker, period="1y", interval="1d")
        close = _extract_close_series(df)
        if close.empty:
            return None
        df = pd.DataFrame({"Close": close}).dropna()
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        sma50 = df['Close'].rolling(50).mean().iloc[-1] if len(df) > 50 else None
        sma200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) > 200 else None
        bb_mid = df['Close'].rolling(20).mean().iloc[-1] if len(df) > 20 else None
        bb_std = df['Close'].rolling(20).std().iloc[-1] if len(df) > 20 else None
        bb_upper = bb_mid + 2 * bb_std if bb_mid is not None and bb_std is not None else None
        bb_lower = bb_mid - 2 * bb_std if bb_mid is not None and bb_std is not None else None
        market_price = get_price(ticker, _refresh_token=_refresh_token)
        return {
            "price": market_price if market_price > 0 else float(df['Close'].iloc[-1]),
            "rsi": float(rsi.iloc[-1]) if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else None,
            "sma50": float(sma50) if sma50 is not None and not pd.isna(sma50) else None,
            "sma200": float(sma200) if sma200 is not None and not pd.isna(sma200) else None,
            "bb_upper": float(bb_upper) if bb_upper is not None and not pd.isna(bb_upper) else None,
            "bb_lower": float(bb_lower) if bb_lower is not None and not pd.isna(bb_lower) else None,
            "bb_mid": float(bb_mid) if bb_mid is not None and not pd.isna(bb_mid) else None
        }
    except Exception:
        return None

@st.cache_data(ttl=300)
def get_fundamentals(ticker, _refresh_token=None):
    """Tab 6 fundamentals — Current Price always from unified get_price (same as Tab 2)."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price, price_source = get_price_with_source(ticker)
        analysts = info.get("numberOfAnalystOpinions") or 0
        return {
            "Ticker": ticker,
            "Company": info.get("longName", ticker),
            "Industry": info.get("industry", "N/A"),
            "Current Price": f"${price:.2f}" if price else "N/A",
            "Price Source": price_source if price else "unavailable — click Force Refresh on Tab 2",
            "Market Cap": f"${info.get('marketCap',0)/1e9:.2f}B" if info.get('marketCap') else "N/A",
            "50d SMA": f"${info.get('fiftyDayAverage',0):.2f}" if info.get('fiftyDayAverage') else "N/A",
            "200d SMA": f"${info.get('twoHundredDayAverage',0):.2f}" if info.get('twoHundredDayAverage') else "N/A",
            "Forward P/E": info.get("forwardPE", "N/A"),
            "Analyst Target": f"${info.get('targetMeanPrice',0):.2f}" if info.get('targetMeanPrice') else "N/A",
            "Analysts": int(analysts),
            "3MMT EBIT": f"${info.get('ebitda',0)/1e9:.2f}B" if info.get('ebitda') else "N/A",
            "12MMT EPS": info.get("trailingEps", "N/A"),
            "Forward EPS": info.get("forwardEps", "N/A"),
            "Cash (B)": f"${info.get('totalCash',0)/1e9:.2f}B" if info.get('totalCash') else "N/A",
            "FCF (B)": f"${info.get('freeCashflow',0)/1e9:.2f}B" if info.get('freeCashflow') else "N/A",
        }
    except Exception:
        return {k: "N/A" for k in [
            "Ticker", "Company", "Industry", "Current Price", "Price Source",
            "Market Cap", "50d SMA", "200d SMA", "Forward P/E", "Analyst Target",
            "Analysts", "3MMT EBIT", "12MMT EPS", "Forward EPS", "Cash (B)", "FCF (B)",
        ]}

# ====================== INITIAL LOAD ======================
members = load_members()
transactions = load_transactions()
data = {
    "members": members,
    "transactions": transactions
}
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

st.success("✅ Data loaded from Supabase. Upload Seed Deposit.csv first (12/31/2025), then your main transactions CSV using Append.")

post_deploy_comment_once(
    "deploy_2026-06-11_tab2_price_fix_v3",
    "🚀 **Deploy 2026-06-11 v3 — unified market prices (all tickers)** "
    "FSLR $199 was your **purchase fill**, not market price ($271). When APIs failed on Render, app used transaction prices. "
    "Fix: Yahoo chart API + Finnhub fallbacks, Tab 6 now uses same `get_price` as Tab 2, never uses fill as market quote, purges bad cache. "
    "**Action:** redeploy Render → Tab 2 **Force Refresh Live Prices** once."
)

# ====================== AUTO-ALLOCATION ======================
def auto_allocate_transactions():
    """Clean allocation rules as requested:
    - Any deposit (including seed 'opening deposit'): 
        • 2025 or before 4/1/2026 → 10-way split (Ray = $0)
        • 4/1 to 4/14/2026 → special $27,500 split from spreadsheet
        • After 4/15/2026 → 1/11 equal
    - Buys, Sells, Withdrawals, or anything else → ALWAYS 1/11 equal split

    Manual allocations are protected and will never be overwritten.
    """
    members_list = [m["name"] for m in data["members"]]

    for txn in data["transactions"]:
        # === NEW: Skip manually edited transactions ===
        if txn.get("manual_allocation") == True:
            continue

        if txn.get("allocations"):  # Already allocated
            continue

        amount = abs(float(txn.get("amount", 0)))
        if amount == 0:
            continue

        txn_type = str(txn.get("type", "")).lower()
        date_str = str(txn.get("date", "")).strip()

        # Flexible date parsing
        try:
            if "/" in date_str:
                txn_date = datetime.strptime(date_str, "%m/%d/%Y")
            else:
                txn_date = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            txn_date = datetime(2026, 4, 15)  # safe fallback

        # ==================== 1. DEPOSITS ====================
        if any(word in txn_type for word in ["deposit", "opening", "electronic fund transfer"]):
            if txn_date.year == 2025 or txn_date < datetime(2026, 4, 1):
                # Seed deposit and any pre-4/1/2026 deposits: 10-way, Ray = $0
                alloc_amount = amount / 10
                txn["allocations"] = {name: alloc_amount if name != "Ray Gilkes" else 0.0 for name in members_list}
            elif datetime(2026, 4, 1) <= txn_date <= datetime(2026, 4, 14):
                # Special $27,500 deposit split
                txn["allocations"] = {
                    "Antonio Calderon": 0.0,
                    "Chris Koo": 0.0,
                    "Josh Tafoya": amount / 11,
                    "Jeff Gragert": amount / 11,
                    "Nick Vigil": amount * 2 / 11,
                    "Ray Gilkes": amount / 11,
                    "Jose Calderon": amount / 11,
                    "Chad Speegle": amount / 11,
                    "Jadyn Tafoya": amount / 11,
                    "Matt Newbill": amount * 2 / 11,
                    "Mike Brooks": amount / 11
                }
            else:
                # Future deposits after 4/15/2026: 1/11
                default = amount / 11
                txn["allocations"] = {name: default for name in members_list}
            continue

        # ==================== 2. EVERYTHING ELSE ====================
        default = amount / 11
        txn["allocations"] = {name: default for name in members_list}

    # Save the updated allocations
    save_transactions(data["transactions"])

# ====================== HOLDINGS (moved early for correct layout) ======================
df_txn = pd.DataFrame(data.get("transactions", []))
buys = df_txn[df_txn.get("type", pd.Series([])).str.contains("buy", case=False, na=False)]
holdings = defaultdict(lambda: {"qty": 0.0, "cost_basis": 0.0})
for _, row in buys.iterrows():
    ticker = str(row.get("ticker", "CASH")).upper()
    if ticker == "CASH":
        continue
    qty = float(row.get("quantity", 0))
    px = float(row.get("price", 0))
    comm = float(row.get("commission", 0))
    # Use explicit qty * price + commission. This avoids double-counting when "amount"
    # is already the Net Amount (which typically already includes commission effect).
    cost = abs(qty * px) + abs(comm)
    holdings[ticker]["qty"] += qty
    holdings[ticker]["cost_basis"] += cost

# Always keep these fresh for Tab 9 (and anywhere else that needs current portfolio)
if "portfolio_holdings" not in st.session_state or st.session_state.get("portfolio_holdings") != list(holdings.keys()):
    st.session_state.portfolio_holdings = list(holdings.keys())
    st.session_state.portfolio_quantities = {ticker: h["qty"] for ticker, h in holdings.items()}

def get_all_tracked_tickers():
    """Portfolio holdings + watchlist — every ticker that needs a market price."""
    port = [str(t).upper().strip() for t in holdings.keys()]
    wl = st.session_state.get("watchlist", []) or []
    combined = port + [str(t).upper().strip() for t in wl]
    return list(dict.fromkeys(t for t in combined if t and t not in ("CASH", "-")))

# ====================== DYNAMIC TOTALS ======================
def calculate_dynamic_totals():
    df_txn = pd.DataFrame(data["transactions"])
    member_totals = {m["name"]: {"invested": 0.0, "fees": 0.0, "contributed": 0.0} for m in data["members"]}
    for _, row in df_txn.iterrows():
        alloc = row.get("allocations", {})
        amount = float(row.get("amount", 0))
        commission = float(row.get("commission", 0))
        txn_type = str(row.get("type", "")).lower()
        ticker = str(row.get("ticker", "")).upper()
        is_stock_buy = "buy" in txn_type.lower() and ticker not in ["CASH", ""]
        is_stock_sell = "sell" in txn_type
        is_deposit = "deposit" in txn_type or "opening" in txn_type or "early" in txn_type
        is_withdrawal = "withdrawal" in txn_type
        for member_name, alloc_amount in alloc.items():
            if member_name in member_totals:
                alloc_abs = abs(alloc_amount)
                if is_stock_buy:
                    member_totals[member_name]["invested"] += alloc_abs
                elif is_stock_sell:
                    member_totals[member_name]["invested"] -= alloc_abs
                if is_deposit:
                    member_totals[member_name]["contributed"] += alloc_abs
                elif is_withdrawal:
                    member_totals[member_name]["contributed"] -= alloc_abs
                if commission != 0 and amount != 0:
                    fee_share = commission * (alloc_abs / abs(amount))
                    member_totals[member_name]["fees"] += abs(fee_share)
    return member_totals

dynamic_totals = calculate_dynamic_totals()
for m in data["members"]:
    name = m["name"]
    m["total_invested"] = dynamic_totals.get(name, {}).get("invested", 0.0)
    m["fees"] = dynamic_totals.get(name, {}).get("fees", 0.0)
    m["total_contributed"] = dynamic_totals.get(name, {}).get("contributed", m.get("total_contributed", 0.0))
save_members(data["members"])

# ====================== MARKET STATUS (for price strategy + UI badges) ======================
try:
    _session = get_market_session()
    st.session_state.market_is_open = _session == "open"
    _eod_day = get_last_trading_day_str()
    if _session == "open":
        st.session_state.market_status = "🟢 US Market Open — showing latest intraday prices"
    elif _session == "premarket":
        st.session_state.market_status = f"🟡 Pre-Market — showing prior close (**{_eod_day}**)"
    elif _session == "weekend":
        st.session_state.market_status = f"🔴 Market Closed (Weekend) — using close for **{_eod_day}**"
    else:
        st.session_state.market_status = f"🔴 After Hours — using today's close (**{_eod_day}**)"
except Exception:
    st.session_state.market_is_open = False
    st.session_state.market_status = "🔴 Market status unavailable — using best available prices"

# ====================== PORTFOLIO SUMMARY CALCULATIONS (safe version) ======================
purge_invalid_price_cache()
_refresh_token = st.session_state.get("price_refresh_token")
_tracked_tickers = get_all_tracked_tickers()
prices = {ticker: get_price(ticker, _refresh_token=_refresh_token) for ticker in _tracked_tickers}
total_market_value = sum(h["qty"] * prices.get(t, 0.0) for t, h in holdings.items())
total_cost_basis = sum(h["cost_basis"] for h in holdings.values())
overall_return = ((total_market_value / total_cost_basis) - 1) * 100 if total_cost_basis > 0 else 0.0
total_current_cash = sum(m.get("total_contributed", 0.0) - m.get("total_invested", 0.0) for m in data.get("members", []))

# ====================== LAYOUT: BIBLE + PORTFOLIO SUMMARY ======================
col_bible, col_summary = st.columns([3, 1])
with col_bible:
    st.markdown("""
    <div class="bible-box">
        <h3>🙌 Building Together</h3>
        <p><strong>2 Corinthians 9:6-8 (NIV)</strong></p>
        <p>“Remember this: Whoever sows sparingly will also reap sparingly, and whoever sows generously will also reap generously. Each of you should give what you have decided in your heart to give, not reluctantly or under compulsion, for God loves a cheerful giver. And God is able to bless you abundantly, so that in all things at all times, having all that you need, you will abound in every good work.”</p>
        <p style="font-size: 0.95em; opacity: 0.9;">Planting seeds as a family • Growing abundance to share with the world</p>
    </div>
    """, unsafe_allow_html=True)

with col_summary:
    st.markdown(f"""
    <div class="portfolio-summary">
        <strong>Portfolio Summary</strong><br><br>
        <span style="font-size: 1.15em;">Portfolio Value: <strong>${total_market_value:,.0f}</strong></span><br>
        <span style="font-size: 1.15em;">Portfolio Return: <strong>{overall_return:+.2f}%</strong></span><br>
        <span style="font-size: 0.95em; opacity: 0.85;">Current Cash Balance: ${total_current_cash:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

# ====================== NEGATIVE BALANCE ALERT ======================
negative_members = [m["name"] for m in data.get("members", [])
                    if (m.get("total_contributed", 0) - m.get("total_invested", 0.0)) < -0.01]
if negative_members:
    st.error(f"⚠️ **NEGATIVE BALANCE ALERT**: {', '.join(negative_members)} have gone negative.")

# ====================== SIDEBAR ======================
st.sidebar.header("📤 CSV Upload (IBKR)")
uploaded_file = st.sidebar.file_uploader("Upload new IBKR Transactions CSV", type=["csv"], key="csv_uploader")
if uploaded_file is not None:
    try:
        text = uploaded_file.getvalue().decode('utf-8')
        lines = text.splitlines()
        header_index = next((i for i, line in enumerate(lines) if "Transaction Type" in line and "Symbol" in line), None)
        if header_index is None:
            st.sidebar.error("Could not find transaction header.")
        else:
            df_pending = pd.read_csv(uploaded_file, skiprows=header_index)
            numeric_cols = ['Quantity', 'Price', 'Gross Amount', 'Commission', 'Net Amount']
            for col in numeric_cols:
                if col in df_pending.columns:
                    df_pending[col] = pd.to_numeric(df_pending[col], errors='coerce').fillna(0)
            st.session_state.pending_df = df_pending
            st.sidebar.success(f"Preview ready – {len(df_pending)} transactions loaded")
    except Exception as e:
        st.sidebar.error(f"Error reading CSV: {e}")

if "pending_df" in st.session_state:
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Append to Existing Data", key="append_btn"):
        new_txns = []
        for _, row in st.session_state.pending_df.iterrows():
            new_txns.append({
                "date": str(row.get("Date", datetime.today().date())),
                "type": str(row.get("Transaction Type", "Club Buy")),
                "ticker": str(row.get("Symbol", "CASH")),
                "quantity": float(row.get("Quantity", 0)),
                "price": float(row.get("Price", 0)),
                "amount": float(row.get("Net Amount", 0)),
                "commission": float(row.get("Commission", 0)),
                "notes": str(row.get("Description", "")),
                "allocations": {}
            })
        data["transactions"].extend(new_txns)
        save_transactions(data["transactions"])
        st.sidebar.success(f"✅ Appended {len(new_txns)} transactions. Running allocation...")
        auto_allocate_transactions()
        data["transactions"] = load_transactions()
        st.sidebar.success(f"✅ Total transactions now: {len(data['transactions'])}")
        del st.session_state.pending_df
        st.rerun()
    if col2.button("Replace All Data", type="primary", key="replace_btn"):
        new_txns = []
        for _, row in st.session_state.pending_df.iterrows():
            new_txns.append({
                "date": str(row.get("Date", datetime.today().date())),
                "type": str(row.get("Transaction Type", "Club Buy")),
                "ticker": str(row.get("Symbol", "CASH")),
                "quantity": float(row.get("Quantity", 0)),
                "price": float(row.get("Price", 0)),
                "amount": float(row.get("Net Amount", 0)),
                "commission": float(row.get("Commission", 0)),
                "notes": str(row.get("Description", "")),
                "allocations": {}
            })
        # Clear everything and only keep the new transactions (no seed protection for testing)
        data["transactions"] = new_txns
        save_transactions(data["transactions"])
        st.sidebar.success(f"✅ Replaced with {len(new_txns)} transactions. Running allocation...")
        auto_allocate_transactions()
        data["transactions"] = load_transactions()
        st.sidebar.success(f"✅ Total transactions now: {len(data['transactions'])}")
        del st.session_state.pending_df
        st.rerun()

if st.sidebar.button("🔄 Refresh Data from Local Storage", key="refresh_btn"):
    data["members"] = load_members()
    data["transactions"] = load_transactions()
    auto_allocate_transactions()
    st.success("✅ Data refreshed from local storage")
    st.rerun()

if st.sidebar.button("Logout", key="logout_btn"):
    st.session_state.logged_in = False
    st.rerun()

# ====================== TABS ======================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "👥 Member Cash Balances",
    "📊 Club Holdings (Live)",
    "📈 Member Performance",
    "📋 Transaction History",
    "⭐ Watchlist",
    "📉 Advanced Technical Analysis + Confluence",
    "📅 Meeting Scheduler",
    "🤖 AI Trading Agents",
    "🧠 EFA Multi-Agent System"
])

df_members = pd.DataFrame(data["members"])

# TAB 1: Member Cash Balances
with tab1:
    st.subheader("Member Cash Balances")
    df_display = df_members[["name", "total_contributed"]].copy()
    df_display["total_invested"] = [dynamic_totals.get(name, {}).get("invested", 0.0) for name in df_display["name"]]
    df_display["fees"] = [dynamic_totals.get(name, {}).get("fees", 0.0) for name in df_display["name"]]
    df_display["current_balance"] = df_display["total_contributed"] - df_display["total_invested"]
    total_data = {
        "name": "**TOTAL**",
        "total_contributed": round(df_display["total_contributed"].sum(), 2),
        "current_balance": round(df_display["current_balance"].sum(), 2),
        "total_invested": round(df_display["total_invested"].sum(), 2),
        "fees": round(df_display["fees"].sum(), 2)
    }
    df_with_total = pd.concat([df_display, pd.DataFrame([total_data])], ignore_index=True)
    edited_df = st.data_editor(
        df_with_total,
        column_config={
            "name": st.column_config.TextColumn("Member", disabled=True),
            "total_contributed": st.column_config.NumberColumn("Total Contributed $", format="$%.2f"),
            "current_balance": st.column_config.NumberColumn("Current Cash Balance $", format="$%.2f", disabled=True),
            "total_invested": st.column_config.NumberColumn("Total Invested $", format="$%.2f", disabled=True),
            "fees": st.column_config.NumberColumn("Fees $", format="$%.2f")
        },
        width="stretch",
        hide_index=True
    )
    if not edited_df.iloc[:-1].equals(df_display):
        for i, row in edited_df.iloc[:-1].iterrows():
            data["members"][i]["total_contributed"] = float(row["total_contributed"])
        save_members(data["members"])
        st.success("✅ Balances updated")
        st.rerun()
    st.subheader("💰 Funding Needs")
    needs = []
    for m in data["members"]:
        contributed = m.get("total_contributed", 0)
        invested = dynamic_totals.get(m["name"], {}).get("invested", 0.0)
        current_balance = contributed - invested
        if current_balance < 0:
            needs.append(f"**{m['name']}** must provide admin with **${abs(current_balance):.2f}** to get balance to $0.00")
    if needs:
        for need in needs:
            st.warning(need)
    else:
        st.success("✅ All member balances are non-negative.")
    st.subheader("💬 Comments")
    comments = load_comments()
    with st.form("add_comment"):
        new_comment = st.text_input("Add a comment")
        if st.form_submit_button("Post Comment"):
            if new_comment.strip():
                comments.append({
                    "date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                    "author": st.session_state.username,
                    "text": new_comment.strip(),
                    "resolved": False
                })
                save_comments(comments)
                st.success("Comment posted!")
                st.rerun()
    if comments:
        comments_df = pd.DataFrame(comments)
        csv = comments_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Comments as CSV",
            data=csv,
            file_name="efa_comments.csv",
            mime="text/csv"
        )
    if comments:
        for i, comment in enumerate(comments):
            with st.expander(f"{comment['date']} - {comment['author']}"):
                st.write(comment["text"])
                col_a, col_b = st.columns([1,1])
                with col_a:
                    if st.button("Mark Resolved", key=f"res_{i}"):
                        comments[i]["resolved"] = True
                        save_comments(comments)
                        st.rerun()
                with col_b:
                    if st.button("Delete", key=f"del_{i}"):
                        code = st.text_input("Admin Code (1998)", type="password", key=f"code_{i}")
                        if code == "1998":
                            del comments[i]
                            save_comments(comments)
                            st.success("Comment deleted")
                            st.rerun()
                        else:
                            st.error("Incorrect code")
    else:
        st.info("No comments yet.")

# TAB 2: Club Holdings with Live Prices + Historical Chart
with tab2:
    st.subheader("Club Holdings with Live Prices")

    # Market status badge (driven by ET hours + the smart get_price logic)
    status = st.session_state.get("market_status", "Prices loaded")
    if st.session_state.get("market_is_open"):
        st.success(status)
    else:
        st.info(status)

    # ====================== FORCE PRICE REFRESH (kept as requested) ======================
    col_refresh1, col_refresh2 = st.columns([1, 3])
    with col_refresh1:
        if st.button("🔄 Force Refresh Live Prices", type="primary", use_container_width=True, 
                     help="Clears Streamlit + Supabase price cache and forces fresh Yahoo/Finnhub API calls. Use after deploy or when prices look stale."):
            if "price_refresh_token" not in st.session_state:
                st.session_state.price_refresh_token = 0
            st.session_state.price_refresh_token += 1
            try:
                get_price.clear()
            except Exception:
                pass
            clear_price_cache(get_all_tracked_tickers())
            try:
                get_fundamentals.clear()
            except Exception:
                pass
            st.success("Cache cleared (Streamlit + Supabase) — fetching fresh prices...")
            st.rerun()
    # === Holdings Table with price source diagnostics ===
    rows = []
    total_qty = total_cost = total_market = total_unrealized = 0.0
    for ticker, h in holdings.items():
        qty = h["qty"]
        cost_basis = h["cost_basis"]
        avg_price = cost_basis / qty if qty > 0 else 0

        # Use diagnostic version so we can show the user exactly where the price came from
        live_price, price_source = get_price_with_source(ticker)

        market_value = qty * live_price
        unrealized = market_value - cost_basis
        pct_return = ((market_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0
        rows.append({
            "Ticker": ticker,
            "Quantity": round(qty, 4),
            "Avg Purchase Price": f"${avg_price:,.4f}",
            "Cost Basis": f"${cost_basis:,.2f}",
            "Live Price": f"${live_price:,.2f}",
            "Price Source": price_source,
            "Market Value": f"${market_value:,.2f}",
            "Unrealized Gain/Loss": f"${unrealized:,.2f}",
            "% Return": f"{pct_return:.2f}%"
        })
        total_qty += qty
        total_cost += cost_basis
        total_market += market_value
        total_unrealized += unrealized

    total_pct_return = ((total_market / total_cost) - 1) * 100 if total_cost > 0 else 0
    rows.append({
        "Ticker": "**TOTAL**",
        "Quantity": round(total_qty, 4),
        "Avg Purchase Price": "—",
        "Cost Basis": f"${total_cost:,.2f}",
        "Live Price": "—",
        "Price Source": "—",
        "Market Value": f"${total_market:,.2f}",
        "Unrealized Gain/Loss": f"${total_unrealized:,.2f}",
        "% Return": f"{total_pct_return:.2f}%"
    })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if total_market == 0:
        st.warning("⚠️ Prices showing $0.00. This usually means we have no yfinance data and no prior cached price for these tickers. Try Force Refresh. After hours / closed market we intentionally use the final daily (EOD) close.")

    # ====================== PORTFOLIO PERFORMANCE HISTORY (REAL DATA) ======================
    st.subheader("📈 Portfolio Performance History")
    st.caption("Daily snapshots • Portfolio NAV (securities + cash) + Return on every $1 invested")

    # Load existing history from Supabase
    portfolio_history = load_from_supabase("portfolio_history", [])

    # Calculate current values
    current_securities_value = total_market_value
    current_cash_balance = total_current_cash
    current_portfolio_nav = current_securities_value + current_cash_balance

    # Cumulative capital invested in securities (from dynamic totals)
    cumulative_invested = sum(dynamic_totals.get(m["name"], {}).get("invested", 0.0) for m in data.get("members", []))
    current_return_on_invested = (current_securities_value / cumulative_invested) if cumulative_invested > 0 else 1.0

    # --- AUTO daily snapshot (keeps the manual button below) ---
    # This runs on load / after price refresh. It records the final daily NAV for the most recent
    # completed trading day (using EOD prices after hours) if that date is missing.
    # You no longer have to remember to press the button every day.
    auto_record_eod_snapshot_if_needed(
        current_portfolio_nav, current_securities_value, current_cash_balance,
        cumulative_invested, current_return_on_invested
    )

    # --- Manual Snapshot Button (kept exactly as requested) ---
    col_btn1, col_btn2 = st.columns([2, 3])
    with col_btn1:
        if st.button("📅 Record Today's Portfolio Snapshot", type="primary", use_container_width=True):
            # Use the smart trading-day date (so pressing on weekend / Monday correctly attributes to Friday etc.)
            snap_date = get_last_trading_day_str()

            # Check if this trading day's snapshot already exists
            existing_dates = [entry.get("date") for entry in portfolio_history]
            if snap_date in existing_dates:
                st.warning(f"Snapshot for {snap_date} already exists. No duplicate recorded.")
            else:
                new_snapshot = {
                    "date": snap_date,
                    "portfolio_nav": round(current_portfolio_nav, 2),
                    "securities_value": round(current_securities_value, 2),
                    "cash_balance": round(current_cash_balance, 2),
                    "cumulative_invested": round(cumulative_invested, 2),
                    "return_on_invested": round(current_return_on_invested, 4)
                }
                portfolio_history.append(new_snapshot)
                # Sort by date just in case
                portfolio_history = sorted(portfolio_history, key=lambda x: x["date"])
                save_to_supabase("portfolio_history", portfolio_history)
                st.success(f"✅ Snapshot for {snap_date} recorded successfully!")
                st.rerun()

    with col_btn2:
        if portfolio_history:
            last_date = portfolio_history[-1]["date"]
            st.info(f"Last recorded snapshot: **{last_date}**")
        else:
            st.warning("No historical snapshots recorded yet. Press the button above to start tracking.")

    # One-time message if the auto-recorder just saved a missing day for you
    if st.session_state.get("just_auto_recorded_date"):
        auto_d = st.session_state.pop("just_auto_recorded_date")
        st.success(f"✅ Auto-recorded daily EOD snapshot for **{auto_d}** (final daily prices after close / weekend).")
        # No rerun needed — just informational for this run

    # --- Build DataFrame for Charts ---
    if portfolio_history:
        df_hist = pd.DataFrame(portfolio_history)
        df_hist["Date"] = pd.to_datetime(df_hist["date"])
        df_hist = df_hist.sort_values("Date")

        # Two charts side by side
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Portfolio NAV Over Time**")
            st.caption("Total value = Securities + Cash Balance")
            st.line_chart(df_hist.set_index("Date")["portfolio_nav"], width="stretch", height=380)
        
        with col2:
            st.markdown("**Return on Every $1 Invested**")
            st.caption("Growth on capital actually deployed into securities")
            st.line_chart(df_hist.set_index("Date")["return_on_invested"], width="stretch", height=380)

        # Summary metrics
        latest = portfolio_history[-1]
        st.metric(
            "Current Portfolio NAV", 
            f"${latest['portfolio_nav']:,.0f}",
            delta=f"${latest['portfolio_nav'] - portfolio_history[0]['portfolio_nav']:,.0f} since first snapshot"
        )
    else:
        st.info("No performance history yet. Click the button above to record your first snapshot.")

    # ====================== INVESTMENT GOALS & TARGETS (NOW WITH SUPABASE) ======================
    st.subheader("🎯 Investment Goals & Targets")
    st.caption("Define parameters per holding to guide agent suggestions in Tab 9. Saved for all members.")

    if "investment_goals" not in st.session_state:
        st.session_state.investment_goals = load_investment_goals()

    goals = st.session_state.investment_goals

    # Always show an expander for every current holding (so new tickers immediately get goal settings)
    current_portfolio_tickers = list(holdings.keys())
    for ticker in current_portfolio_tickers:
        with st.expander(f"🎯 {ticker} Goals", expanded=False):
            existing = goals.get(ticker, {})
            col_a, col_b = st.columns(2)
            with col_a:
                goal_type = st.selectbox("Investment Goal", 
                    ["Short Term Gain (<1 Yr)", "Long Term (>1 Yr)"], 
                    index=0 if existing.get("goal_type") == "Short Term Gain (<1 Yr)" else 1,
                    key=f"gt_{ticker}")
                inv_type = st.selectbox("Investment Type", 
                    ["Moonshot (≤10% of portfolio)", "Core (≤25% of portfolio)"], 
                    index=0 if existing.get("investment_type") == "Moonshot (≤10% of portfolio)" else 1,
                    key=f"it_{ticker}")
            with col_b:
                target_return = st.number_input("Expected 1-Year Return Target (%)", 
                    min_value=0.0, value=existing.get("expected_1yr_return", 50.0), step=5.0, key=f"er_{ticker}")
                strategy = st.selectbox("EFAIC Strategy", 
                    ["Accumulation", "Buy and Hold", "Ad-Hoc"], 
                    index=["Accumulation", "Buy and Hold", "Ad-Hoc"].index(existing.get("efaic_strategy", "Accumulation")) if existing.get("efaic_strategy") in ["Accumulation", "Buy and Hold", "Ad-Hoc"] else 0,
                    key=f"es_{ticker}")

            if st.button(f"Save Goals for {ticker}", key=f"save_{ticker}"):
                goals[ticker] = {
                    "goal_type": goal_type,
                    "investment_type": inv_type,
                    "expected_1yr_return": target_return,
                    "efaic_strategy": strategy,
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                save_investment_goals(goals)
                st.success(f"✅ Saved for {ticker} (shared with all members)")
                st.rerun()

    # Investment Goals Summary: Always show every current portfolio ticker
    st.markdown("**Investment Goals Summary**")
    summary_data = {}
    for ticker in current_portfolio_tickers:
        if ticker in goals:
            summary_data[ticker] = goals[ticker]
        else:
            summary_data[ticker] = {
                "goal_type": "Not set",
                "investment_type": "Not set",
                "expected_1yr_return": "Not set",
                "efaic_strategy": "Not set",
                "last_updated": "—"
            }
    st.dataframe(pd.DataFrame.from_dict(summary_data, orient='index'), width="stretch")

    st.caption("Goals defined here will influence agent recommendations in Tab 9")

# TAB 3: Member Performance
with tab3:
    st.subheader("Each Member’s Portfolio Performance")
    st.info("Portfolio Value = securities only (cash shown separately). Ownership based on Total Invested.")
    total_invested_per_member = [dynamic_totals.get(name, {}).get("invested", 0.0) for name in df_members["name"]]
    df_members["total_invested"] = total_invested_per_member
    total_invested_all = sum(total_invested_per_member)
    total_securities_value = sum(h["qty"] * prices.get(t, 0) for t, h in holdings.items())
    perf_rows = []
    grand_contributed = grand_invested = grand_cash = grand_portfolio = grand_unrealized = 0.0
    for i, m in df_members.iterrows():
        total_invested = m["total_invested"]
        ownership_pct = (total_invested / total_invested_all * 100) if total_invested_all > 0 else 0
        member_securities_value = total_securities_value * (total_invested / total_invested_all) if total_invested_all > 0 else 0
        unrealized_gain = member_securities_value - total_invested
        return_pct = (unrealized_gain / total_invested * 100) if total_invested > 0 else 0
        current_cash = m["total_contributed"] - total_invested
        perf_rows.append({
            "Member": m["name"],
            "Total Contributed": f"${m['total_contributed']:,.0f}",
            "Total Invested": f"${total_invested:,.0f}",
            "Current Cash": f"${current_cash:,.0f}",
            "% of Total Contribution": f"{ownership_pct:.2f}%",
            "Portfolio Value (Securities)": f"${member_securities_value:,.0f}",
            "Unrealized Gain": f"${unrealized_gain:,.0f}",
            "% Return": f"{return_pct:.2f}%"
        })
        grand_contributed += m['total_contributed']
        grand_invested += total_invested
        grand_cash += current_cash
        grand_portfolio += member_securities_value
        grand_unrealized += unrealized_gain
    perf_rows.append({
        "Member": "**TOTAL**",
        "Total Contributed": f"${grand_contributed:,.0f}",
        "Total Invested": f"${grand_invested:,.0f}",
        "Current Cash": f"${grand_cash:,.0f}",
        "% of Total Contribution": "100.00%",
        "Portfolio Value (Securities)": f"${grand_portfolio:,.0f}",
        "Unrealized Gain": f"${grand_unrealized:,.0f}",
        "% Return": "—"
    })
    st.dataframe(pd.DataFrame(perf_rows), width="stretch", hide_index=True)

# TAB 4: Transaction History
with tab4:
    st.subheader("Transaction History (Master Table)")

    txn_df = pd.DataFrame(data["transactions"])

    if not txn_df.empty:
        txn_df = txn_df.sort_values("date", ascending=False).reset_index(drop=True)
        txn_df_display = txn_df.copy()

        # Format amount for display
        txn_df_display["amount"] = txn_df_display.apply(
            lambda row: abs(row["amount"]) if str(row.get("type", "")).lower().startswith("buy") else row["amount"],
            axis=1
        )

        members_list = [m["name"] for m in data["members"]]

        # Show per-member allocations
        for member in members_list:
            txn_df_display[member] = txn_df["allocations"].apply(
                lambda x: x.get(member, 0) if isinstance(x, dict) else 0
            )

        # Clean up columns for display
        if "allocations" in txn_df_display.columns:
            txn_df_display = txn_df_display.drop(columns=["allocations", "id"], errors="ignore")

        st.dataframe(txn_df_display, width="stretch", hide_index=True)

        # ====================== MANUAL ALLOCATION EDITOR ======================
        st.markdown("---")
        st.subheader("✏️ Manual Allocation Editor")
        st.caption("Select a transaction below to manually adjust how the amount is split between members. Changes are saved permanently.")

        # Create a user-friendly list of transactions
        txn_options = []
        for i, txn in enumerate(data["transactions"]):
            label = f"{txn.get('date')} | {txn.get('type', 'Unknown')} | {txn.get('ticker', '')} | ${abs(txn.get('amount', 0)):,.2f}"
            txn_options.append((label, i))

        if txn_options:
            selected_label, real_idx = st.selectbox(
                "Select transaction to edit allocation",
                options=txn_options,
                format_func=lambda x: x[0]
            )

            selected_txn = data["transactions"][real_idx]
            current_alloc = selected_txn.get("allocations", {})

            st.write(f"**Editing:** {selected_label}")

            with st.form(key=f"edit_alloc_{real_idx}"):
                
                start_fresh = st.checkbox(
                    "Start with all members at $0 (recommended for full manual overrides)", 
                    value=False,
                    key=f"fresh_{real_idx}"
                )

                new_allocations = {}
                cols = st.columns(3)

                for i, member in enumerate(members_list):
                    with cols[i % 3]:
                        if start_fresh:
                            default_value = 0.0
                        else:
                            default_value = current_alloc.get(member, 0.0)

                        new_allocations[member] = st.number_input(
                            member,
                            value=float(default_value),
                            step=0.01,
                            format="%.2f",
                            key=f"alloc_{real_idx}_{member}"
                        )

                submitted = st.form_submit_button("💾 Save Manual Allocation", type="primary")

                if submitted:
                    # Save the manual allocation
                    data["transactions"][real_idx]["allocations"] = new_allocations
                    data["transactions"][real_idx]["manual_allocation"] = True
                    save_transactions(data["transactions"])

                    # === CRITICAL FIX: Reload fresh data from Supabase ===
                    data["transactions"] = load_transactions()

                    st.success("✅ Manual allocation saved successfully!")
                    st.rerun()
        else:
            st.info("No transactions available to edit.")
    else:
        st.info("No transactions yet.")

# TAB 5: WATCHLIST
with tab5:
    st.subheader("⭐ Watchlist")
    st.caption("Add or remove individual items. Changes are saved permanently for all members.")

    if "watchlist" not in st.session_state or st.session_state.watchlist is None:
        st.session_state.watchlist = load_watchlist()

    new_ticker = st.text_input("Add ticker to watchlist (e.g. AAPL)", key="add_watch")
    if st.button("Add to Watchlist", key="add_watch_btn"):
        ticker_upper = new_ticker.strip().upper()
        if ticker_upper and ticker_upper not in st.session_state.watchlist:
            st.session_state.watchlist.append(ticker_upper)
            save_watchlist(st.session_state.watchlist)
            st.success(f"✅ Added {ticker_upper}")
            st.rerun()

    if st.session_state.watchlist:
        st.write("**Current Watchlist**")
        for i, ticker in enumerate(st.session_state.watchlist[:]):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"• {ticker}")
            with col2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state.watchlist.pop(i)
                    save_watchlist(st.session_state.watchlist)
                    st.success(f"✅ Removed {ticker}")
                    st.rerun()
    else:
        st.info("Watchlist is empty.")

    if st.session_state.get("is_admin", False):
        if st.button("🗑️ ADMIN: Clear Watchlist (Supabase)", type="secondary"):
            st.session_state.watchlist = []
            save_watchlist([])
            st.success("✅ Watchlist cleared in Supabase")
            st.rerun()

# TAB 6: Advanced Technical Analysis & Grok Moonshot Insights (FINAL V9)
with tab6:
    st.subheader("📉 Advanced Technical Analysis & Grok Moonshot Insights")
    st.caption("Real-time fundamentals from yfinance • Persistent Grok qualitative analysis")

    # ====================== GET TICKERS (robust - always match Tab 2 + full watchlist) ======================
    # Use the reliably updated session_state from top-level if available, otherwise fall back to current holdings
    portfolio_tickers = st.session_state.get("portfolio_holdings") or [ticker for ticker in holdings.keys() if ticker != "CASH"]
    watchlist_tickers = st.session_state.get("watchlist", [])
    all_tickers = list(dict.fromkeys(portfolio_tickers + watchlist_tickers))

    # ====================== COLUMN CONFIG ======================
    fundamentals_column_config = {
        "Ticker": st.column_config.TextColumn("Ticker", width=70),
        "Company": st.column_config.TextColumn("Company", width=200),
        "Industry": st.column_config.TextColumn("Industry", width=160),
        "Current Price": st.column_config.TextColumn("Current Price", width=95),
        "Price Source": st.column_config.TextColumn("Price Source", width=180),
        "Market Cap": st.column_config.TextColumn("Market Cap", width=90),
        "50d SMA": st.column_config.TextColumn("50d SMA", width=85),
        "200d SMA": st.column_config.TextColumn("200d SMA", width=85),
        "Forward P/E": st.column_config.TextColumn("Forward P/E", width=85),
        "Analyst Target": st.column_config.TextColumn("Analyst Target", width=95),
        "Analysts": st.column_config.NumberColumn("Analysts", width=70),
        "3MMT EBIT": st.column_config.TextColumn("3MMT EBIT", width=90),
        "12MMT EPS": st.column_config.TextColumn("12MMT EPS", width=85),
        "Forward EPS": st.column_config.TextColumn("Forward EPS", width=85),
        "Cash (B)": st.column_config.TextColumn("Cash (B)", width=85),
        "FCF (B)": st.column_config.TextColumn("FCF (B)", width=85),
    }

    # ====================== FUNDAMENTALS TABLES ======================
    if all_tickers:
        st.markdown("### 📊 Fundamentals & Technicals (from yfinance)")
        if portfolio_tickers:
            st.markdown("#### Portfolio Holdings")
            _ftoken = st.session_state.get("price_refresh_token")
            st.dataframe(pd.DataFrame([get_fundamentals(t, _refresh_token=_ftoken) for t in portfolio_tickers]), column_config=fundamentals_column_config, width="stretch", hide_index=True)
        if watchlist_tickers:
            st.markdown("#### Watchlist")
            _ftoken = st.session_state.get("price_refresh_token")
            st.dataframe(pd.DataFrame([get_fundamentals(t, _refresh_token=_ftoken) for t in watchlist_tickers]), column_config=fundamentals_column_config, width="stretch", hide_index=True)

    # ====================== GROK ANALYSIS ======================
    st.markdown("### 🔍 Grok Qualitative Analysis Summary")

    # Load from Supabase using proper helper function
    if "grok_analyses" not in st.session_state:
        st.session_state.grok_analyses = load_grok_analyses()

    selected = st.multiselect("Select tickers to analyze/update", all_tickers, default=all_tickers[:5])

    if st.button("🔄 Analyze/Update Selected Tickers", type="primary") and selected:
        with st.spinner("Calling Grok for rich moonshot analysis..."):
            for ticker in selected:
                display_ticker = ticker
                if ticker.upper() == "TE":
                    display_ticker = "TE (T1 Energy Inc. - NYSE)"

                fund_data = get_fundamentals(ticker)
                company_name = fund_data.get("Company", ticker)

                # ====================== IMPROVED PROMPT ======================
                prompt = f"""You are a senior investment analyst for the Equity for All Investment Club (EFAIC).

We are looking for high-conviction moonshot opportunities with realistic 2X+ potential over 18-24 months. Be honest, data-driven, and balanced about both upside and risks.

IMPORTANT INSTRUCTIONS:
- Return ONLY valid JSON. Do not include any text before or after the JSON.
- Use clean, professional language. Avoid excessive markdown, emojis, or inconsistent formatting.
- Be specific with price levels.

Return your response in this exact JSON structure:

{{
  "company": "Full company name",
  "industry": "Main industry",
  "sub_industry": "Specific sub-industry",
  "best_of_breed": "Yes or No + one short sentence reason",
  "growth_outlook": "Brief 1-2 sentence outlook on the industry",
  "top_competitors": "List 2-4 main competitors",
  "current_revenue": "Latest annual revenue (example: $2.3B)",
  "gross_margin": "Gross margin percentage (example: 42%)",
  "op_margin": "Operating margin percentage",
  "catalysts": "Key upcoming catalysts or events (1-2 sentences)",
  "moat": "What gives this company a competitive advantage? (1-2 sentences)",
  "recommendation": "Buy, Hold, or Avoid",
  "recommendation_summary": "One clear sentence summarizing your overall stance and why",
  "entry_price": "Suggested entry price range (example: $18.50 - $22.00)",
  "exit_target": "12-24 month price target range (example: $45 - $55)",
  "risks": "Key risks to be aware of (1-2 sentences)"
}}

Now analyze: {ticker} ({company_name})"""

                try:
                    response = client.chat.completions.create(
                        model="grok-4-1-fast",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.5,
                        max_tokens=1600
                    )
                    content = response.choices[0].message.content.strip()

                    import json, re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    parsed = json.loads(json_match.group()) if json_match else {"raw": content}

                    new_entry = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "ticker": ticker,
                        "analysis": content,
                        "parsed": parsed,
                        "tokens": response.usage.total_tokens if hasattr(response, 'usage') else 0
                    }
                    st.session_state.grok_analyses.append(new_entry)

                except Exception as e:
                    st.error(f"Error analyzing {ticker}: {e}")

            # Save using proper helper function
            save_grok_analyses(st.session_state.grok_analyses)
            st.success("✅ Analysis saved to Supabase!")
            st.rerun()

    # ====================== GROK SUMMARY TABLE (always show current portfolio + watchlist) ======================
    # Build latest analyses if any exist
    latest = {}
    if st.session_state.grok_analyses:
        for entry in sorted(st.session_state.grok_analyses, key=lambda x: x.get("timestamp", ""), reverse=True):
            if entry["ticker"] not in latest:
                latest[entry["ticker"]] = entry

    st.markdown("### 📋 Grok Qualitative Analysis Summary (Latest)")

    def build_row(ticker):
        entry = latest.get(ticker)
        if not entry or "parsed" not in entry:
            return {
                "Ticker": ticker,
                "Company": "N/A",
                "Industry": "N/A",
                "Best of Breed": "N/A",
                "Recommendation": "Needs Analysis",
                "Entry Price": "N/A",
                "Exit Target": "N/A",
                "Last Updated": "Never",
                "Status": "⚠️ Needs Analysis"
            }
        p = entry["parsed"]
        return {
            "Ticker": ticker,
            "Company": p.get("company", "N/A"),
            "Industry": p.get("industry", "N/A"),
            "Best of Breed": p.get("best_of_breed", "N/A"),
            "Recommendation": p.get("recommendation", "N/A"),
            "Entry Price": p.get("entry_price", "N/A"),
            "Exit Target": p.get("exit_target", "N/A"),
            "Last Updated": entry["timestamp"],
            "Status": "✅ Analyzed"
        }

    # Always show tables using the exact current portfolio and watchlist (matching Tab 2)
    if portfolio_tickers:
        st.markdown("#### Portfolio Holdings")
        st.dataframe(pd.DataFrame([build_row(t) for t in portfolio_tickers]), width="stretch", hide_index=True)

    if watchlist_tickers:
        st.markdown("#### Watchlist")
        st.dataframe(pd.DataFrame([build_row(t) for t in watchlist_tickers]), width="stretch", hide_index=True)

    # ====================== FULL NARRATIVE WITH CLEAN RECOMMENDATION ======================
    if st.session_state.grok_analyses:
        st.markdown("### 📜 Grok Deep Analysis (Full Narrative)")

        for entry in sorted(st.session_state.grok_analyses, key=lambda x: x.get("timestamp", ""), reverse=True):
            token_info = f" ({entry.get('tokens', 'N/A')} tokens)" if entry.get('tokens') else ""
            ticker = entry['ticker']
            parsed = entry.get("parsed", {})

            with st.expander(f"🔍 {ticker} — {entry.get('timestamp', '')}{token_info}", expanded=False):
                
                # Clean Recommendation Box
                if parsed:
                    rec = parsed.get("recommendation", "N/A")
                    rec_summary = parsed.get("recommendation_summary", "")
                    entry_price = parsed.get("entry_price", "N/A")
                    exit_target = parsed.get("exit_target", "N/A")

                    if rec.lower() == "buy":
                        st.success(f"**Recommendation: BUY**  |  Entry: {entry_price}  →  Target: {exit_target}")
                    elif rec.lower() == "hold":
                        st.info(f"**Recommendation: HOLD**  |  Entry: {entry_price}  →  Target: {exit_target}")
                    elif rec.lower() == "avoid":
                        st.warning(f"**Recommendation: AVOID**  |  Entry: {entry_price}  →  Target: {exit_target}")
                    else:
                        st.write(f"**Recommendation:** {rec}  |  Entry: {entry_price}  →  Target: {exit_target}")

                    if rec_summary:
                        st.caption(rec_summary)

                # Full raw analysis from Grok
                st.markdown("**Full Analysis:**")
                st.markdown(entry.get("analysis", "No analysis available."))

    st.caption("v1.0 Beta • Proper Supabase helpers + Improved prompt • Persisted in Supabase • TE = T1 Energy (NYSE)")
    
# TAB 7: MEETING SCHEDULER – Full persistence for everything
with tab7:
    st.subheader("📅 Meeting Scheduler")
    st.caption("All data (polls, availability, finalized meetings) persists in Supabase")

    # Robust loading at the start of the tab
    if "meeting_proposals" not in st.session_state:
        st.session_state.meeting_proposals = load_polls()
    if "availability_responses" not in st.session_state:
        raw_av = load_availability_responses()
        st.session_state.availability_responses = normalize_availability_responses(
            raw_av, st.session_state.meeting_proposals
        )
        # Persist migration immediately so Supabase has the new per-poll structure
        sample = next(iter(raw_av.values()), None) if raw_av else None
        if raw_av and isinstance(sample, (list, tuple)):
            print("[MIGRATION] Old flat availability_responses detected. Migrated to per-poll format and saved to Supabase.")
            print("[MIGRATION] Proposals at migration time:", [p.get("id") for p in st.session_state.meeting_proposals])
            # Safety: also stash the original flat data under a legacy key in case recovery is ever needed.
            try:
                if supabase is not None:
                    current = supabase.table("club_data").select("data").eq("id", 1).execute()
                    data_dict = current.data[0].get("data", {}) if current.data else {}
                    data_dict["availability_responses_legacy"] = raw_av
                    data_dict["availability_responses"] = st.session_state.availability_responses
                    supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
                    print("[MIGRATION] Legacy flat copy saved under 'availability_responses_legacy' key.")
                else:
                    save_availability_responses(st.session_state.availability_responses)
            except Exception as e:
                print("[MIGRATION] Extra legacy backup failed, doing normal save:", e)
                save_availability_responses(st.session_state.availability_responses)
    if "finalized_meetings" not in st.session_state:
        st.session_state.finalized_meetings = load_finalized_meetings()

    # Safety: ensure availability_responses is always a dict (new per-poll shape)
    if not isinstance(st.session_state.get("availability_responses"), dict):
        st.session_state.availability_responses = {}

    if "poll_email_text" not in st.session_state:
        st.session_state.poll_email_text = ""
    if "final_email_text" not in st.session_state:
        st.session_state.final_email_text = ""
    if "change_email_text" not in st.session_state:
        st.session_state.change_email_text = ""
    if "cancel_email_text" not in st.session_state:
        st.session_state.cancel_email_text = ""

    if st.session_state.is_admin:
        st.markdown("### Admin: Create New Poll")
        week_start = st.date_input("Week starting date", datetime.today() + timedelta(days=7))
        week_end = week_start + timedelta(days=6)
        proposed_times = st.multiselect("Available times (7:30 PM CST default)",
                                      ["7:30 PM CST", "8:00 PM CST", "8:30 PM CST"],
                                      default=["7:30 PM CST"])
        if st.button("Create Poll & Generate Email"):
            poll_date = datetime.now().strftime("%Y-%m-%d")
            due_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
            new_poll = {
                "id": len(st.session_state.meeting_proposals) + 1,
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "times": proposed_times,
                "created": poll_date
            }
            st.session_state.meeting_proposals.append(new_poll)
            save_polls(st.session_state.meeting_proposals)
            poll_email = f"""Subject: EFA Investment Club - Availability Poll Open
Hello Team,
Antonio has initiated a poll to schedule our next 1-hour meeting the week of {week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')}.
This request was created on {poll_date}. Please log into the EFA Club site and provide your availability **by {due_date}**.
Thank you!
– EFA Investment Club"""
            st.session_state.poll_email_text = poll_email
            st.success("✅ Poll created and saved!")
            st.rerun()

    if st.session_state.poll_email_text:
        st.text_area("📧 Poll Email – Click inside, Ctrl+A, then Copy",
                     st.session_state.poll_email_text, height=180)

    if st.session_state.meeting_proposals:
        st.markdown("### Current Availability Polls")
        for i, poll in enumerate(st.session_state.meeting_proposals):
            with st.expander(f"📅 Week of {poll['week_start']} – {poll['week_end']} (created {poll.get('created', '')})", expanded=False):
                poll_key = str(poll.get("id", i))
                poll_responses = st.session_state.availability_responses.get(poll_key, {})
                date_options = [f"{date.strftime('%Y-%m-%d')} {time}" for date in pd.date_range(poll['week_start'], poll['week_end']) for time in poll.get('times', [])]
                user_selections = poll_responses.get(st.session_state.username, [])
                valid_user_selections = [s for s in user_selections if s in date_options]
                selected = st.multiselect(
                    f"Select your available dates & times for this poll",
                    date_options,
                    default=valid_user_selections,
                    key=f"poll_{i}_{poll.get('id', i)}"
                )
                if st.button("Submit / Update Availability", key=f"submit_{i}"):
                    if poll_key not in st.session_state.availability_responses:
                        st.session_state.availability_responses[poll_key] = {}
                    st.session_state.availability_responses[poll_key][st.session_state.username] = selected
                    save_availability_responses(st.session_state.availability_responses)
                    st.success("✅ Availability updated!")
                    st.rerun()
                st.markdown("**Availability Summary for this poll**")
                responded = list(poll_responses.keys())
                all_members = list(MEMBER_CREDENTIALS.keys())
                pending = [m for m in all_members if m not in responded]
                st.write(f"**Responded ({len(responded)})**: {', '.join(responded) if responded else 'None yet'}")
                if pending:
                    st.write(f"**Still pending ({len(pending)})**: {', '.join(pending)}")
                poll_selections = [s for selections in poll_responses.values() for s in selections]
                if poll_selections:
                    top_slots = Counter(poll_selections).most_common(3)
                    st.write("**Top 3 best slots for this poll**:")
                    for slot, count in top_slots:
                        st.write(f"• {slot} — **{count}** members available")
                else:
                    st.info("No availability submitted yet for this poll.")

    st.markdown("### Finalize / Change / Cancel Meeting")
    if st.session_state.is_admin:
        final_date = st.date_input("Meeting date", datetime.today() + timedelta(days=10), key="finalize_date")
        final_time = st.selectbox("Meeting time", ["7:30 PM CST", "8:00 PM CST", "8:30 PM CST"], key="finalize_time")
        if st.button("Set Meeting & Generate Email"):
            final_email = f"""Subject: EFA Investment Club Meeting Confirmed
Thank you everyone for providing availability.
The meeting that works for the most people is **{final_date.strftime('%A, %B %d, %Y')} at {final_time}**.
Top 2 alternatives:
• [Alternative 1] — X members available
• [Alternative 2] — Y members available
We will need nearly everyone for the first meeting of the quarter to reach consensus on investments.
See you then!
– EFA Investment Club"""
            st.session_state.final_email_text = final_email
            new_meeting = {
                "id": len(st.session_state.finalized_meetings) + 1,
                "date": final_date.strftime('%Y-%m-%d'),
                "time": final_time,
                "notes": "",
                "votes": []
            }
            st.session_state.finalized_meetings.append(new_meeting)
            save_finalized_meetings(st.session_state.finalized_meetings)
            st.success("✅ Meeting set and saved to Supabase!")
            st.rerun()

    if st.session_state.final_email_text:
        st.text_area("📧 Final Meeting Email – Click inside, Ctrl+A, then Copy",
                     st.session_state.final_email_text, height=200)

    if st.session_state.finalized_meetings:
        st.markdown("### Scheduled Meetings")
        for idx, meeting in enumerate(st.session_state.finalized_meetings[:]):
            with st.expander(f"✅ {meeting['date']} at {meeting['time']}", expanded=False):
                # --- Meeting Notes ---
                st.markdown("**Meeting Notes / Minutes**")
                current_notes = meeting.get("notes", "")
                new_notes = st.text_area(
                    "Add or edit commentary / meeting minutes",
                    value=current_notes,
                    key=f"meeting_notes_{idx}",
                    height=120,
                    placeholder="Paste meeting minutes, decisions, or discussion points here..."
                )
                if st.button("💾 Save Notes", key=f"save_notes_{idx}"):
                    st.session_state.finalized_meetings[idx]["notes"] = new_notes
                    save_finalized_meetings(st.session_state.finalized_meetings)
                    st.success("Notes saved and persisted!")
                    st.rerun()

                st.divider()

                # --- Voting Section ---
                st.markdown("**Votes & Group Decisions**")

                if "votes" not in meeting:
                    st.session_state.finalized_meetings[idx]["votes"] = []
                    meeting["votes"] = []

                votes = meeting.get("votes", [])

                # Admin: Create new vote
                if st.session_state.is_admin:
                    with st.form(key=f"create_vote_form_{idx}"):
                        vote_question = st.text_input(
                            "New vote question",
                            placeholder="e.g. Does the group agree to buy $500 of PLTR at market?"
                        )
                        if st.form_submit_button("Create Vote"):
                            if vote_question.strip():
                                new_vote = {
                                    "id": len(votes) + 1,
                                    "question": vote_question.strip(),
                                    "votes": {},
                                    "created": datetime.now().strftime("%Y-%m-%d %H:%M")
                                }
                                st.session_state.finalized_meetings[idx]["votes"].append(new_vote)
                                save_finalized_meetings(st.session_state.finalized_meetings)
                                st.success("Vote created!")
                                st.rerun()

                # Display existing votes
                if votes:
                    for v_idx, vote in enumerate(votes):
                        st.markdown(f"**Vote #{vote.get('id', v_idx+1)}:** {vote.get('question', 'No question')}")
                        
                        user = st.session_state.username
                        current_vote = vote.get("votes", {}).get(user)

                        # Voting UI
                        col_vote, col_tally = st.columns([1, 1])
                        with col_vote:
                            choice = st.radio(
                                "Your vote",
                                ["Yes", "No"],
                                index=0 if current_vote == "Yes" else (1 if current_vote == "No" else 0),
                                key=f"vote_choice_{idx}_{v_idx}",
                                horizontal=True
                            )
                            if st.button("Submit / Update Vote", key=f"submit_vote_{idx}_{v_idx}"):
                                if "votes" not in st.session_state.finalized_meetings[idx]["votes"][v_idx]:
                                    st.session_state.finalized_meetings[idx]["votes"][v_idx]["votes"] = {}
                                st.session_state.finalized_meetings[idx]["votes"][v_idx]["votes"][user] = choice
                                save_finalized_meetings(st.session_state.finalized_meetings)
                                st.success("Vote recorded!")
                                st.rerun()

                        with col_tally:
                            vote_dict = vote.get("votes", {})
                            yes = sum(1 for v in vote_dict.values() if v == "Yes")
                            no = sum(1 for v in vote_dict.values() if v == "No")
                            st.metric("Yes", yes)
                            st.metric("No", no)
                            st.write(f"**Pending**: {11 - (yes + no)}")

                            if yes >= 6:
                                st.success("✅ This vote has been **APPROVED** by majority (6 out of 11).")
                            elif yes + no >= 11:
                                st.warning("This vote did not reach majority approval.")

                        st.caption(f"Created: {vote.get('created', 'N/A')}")

                else:
                    st.info("No votes created for this meeting yet.")

                st.divider()

                # Change / Cancel buttons (keep existing)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Change this meeting", key=f"change_meet_{idx}"):
                        st.info("Use the date/time picker above and press 'Set Meeting' to update this meeting.")
                with col2:
                    if st.button("Cancel this meeting", key=f"cancel_meet_{idx}"):
                        st.session_state.finalized_meetings.pop(idx)
                        save_finalized_meetings(st.session_state.finalized_meetings)
                        st.success("✅ Meeting cancelled and removed!")
                        st.rerun()

    st.caption("✅ All scheduler data (polls + availability + finalized meetings) fully persists in Supabase")

# TAB 8: AI TRADING AGENTS + MARKET NEWS ======================
with tab8:
    st.subheader("🤖 EFA AI Trading Agents & Market News")
    st.caption("Real-time news via Finnhub • Grok-powered analysis & recommendations")

    news_tab, agents_tab = st.tabs(["📰 Market News", "🤖 AI Agents"])

    # ==================== MARKET NEWS TAB ====================
    with news_tab:
        st.subheader("📰 Latest Market & Portfolio News")
        st.caption("News & SEC Filings from the last 60 days • Portfolio prioritized")

        finnhub_key = os.environ.get("FINNHUB_API_KEY")

        if not finnhub_key:
            st.warning("Add `FINNHUB_API_KEY` to environment variables on Render")
            st.info("Get free key at: https://finnhub.io/register")
        else:
            try:
                import finnhub
                from datetime import datetime, timedelta
                finnhub_client = finnhub.Client(api_key=finnhub_key)

                portfolio_tickers = list(holdings.keys()) if holdings else []
                watchlist_tickers = st.session_state.get("watchlist", [])

                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

                # ====================== PORTFOLIO NEWS ======================
                st.markdown("### 📊 Portfolio Holdings News")

                portfolio_news = []
                with st.spinner("Fetching portfolio news..."):
                    for ticker in portfolio_tickers:
                        try:
                            news = finnhub_client.company_news(ticker, _from=start_date, to=end_date)
                            if isinstance(news, list):
                                portfolio_news.extend(news[:6])
                        except:
                            continue

                seen = set()
                unique_portfolio_news = []
                for item in portfolio_news:
                    headline = item.get('headline')
                    if headline and headline not in seen:
                        seen.add(headline)
                        unique_portfolio_news.append(item)

                if unique_portfolio_news:
                    st.success(f"Found {len(unique_portfolio_news)} recent articles")
                    for item in unique_portfolio_news[:12]:
                        with st.expander(f"**{item.get('headline', 'No Title')}**"):
                            st.caption(f"{item.get('source', 'Unknown')} • {item.get('datetime', '')}")
                            st.write(item.get('summary', 'No summary available.'))
                            if item.get('url'):
                                st.markdown(f"[Read full article →]({item['url']})")
                else:
                    st.info("No recent news found for your portfolio holdings.")

                # ====================== WATCHLIST NEWS ======================
                st.markdown("---")
                st.markdown("### ⭐ Watchlist News")

                if watchlist_tickers:
                    watchlist_news = []
                    with st.spinner("Fetching watchlist news..."):
                        for ticker in watchlist_tickers:
                            try:
                                news = finnhub_client.company_news(ticker, _from=start_date, to=end_date)
                                if isinstance(news, list):
                                    watchlist_news.extend(news[:5])
                            except:
                                continue

                    seen_watch = set()
                    unique_watchlist_news = []
                    for item in watchlist_news:
                        headline = item.get('headline')
                        if headline and headline not in seen_watch:
                            seen_watch.add(headline)
                            unique_watchlist_news.append(item)

                    if unique_watchlist_news:
                        st.success(f"Found {len(unique_watchlist_news)} recent articles")
                        for item in unique_watchlist_news[:10]:
                            with st.expander(f"**{item.get('headline', 'No Title')}**"):
                                st.caption(f"{item.get('source', 'Unknown')} • {item.get('datetime', '')}")
                                st.write(item.get('summary', 'No summary available.'))
                                if item.get('url'):
                                    st.markdown(f"[Read full article →]({item['url']})")
                    else:
                        st.info("No recent news found for your watchlist.")
                else:
                    st.info("Your watchlist is empty.")

                # ====================== NEW: SEC FILINGS ======================
                st.markdown("---")
                st.markdown("### 📄 Recent SEC Filings")

                # Portfolio SEC Filings
                st.markdown("**Portfolio Holdings**")
                portfolio_filings = []
                with st.spinner("Fetching portfolio SEC filings..."):
                    for ticker in portfolio_tickers:
                        try:
                            filings = finnhub_client.company_filings(ticker, _from=start_date, to=end_date)
                            if isinstance(filings, list):
                                portfolio_filings.extend(filings[:4])  # Limit per ticker
                        except:
                            continue

                if portfolio_filings:
                    for filing in portfolio_filings[:10]:
                        filing_date = filing.get('filedDate', 'N/A')
                        filing_type = filing.get('form', 'N/A')
                        ticker = filing.get('symbol', '')
                        description = filing.get('description', 'No description')

                        with st.expander(f"**{ticker}** — {filing_type} ({filing_date})"):
                            st.write(description)
                            if filing.get('url'):
                                st.markdown(f"[View Filing →]({filing['url']})")
                else:
                    st.info("No recent SEC filings found for your portfolio holdings.")

                # Watchlist SEC Filings
                if watchlist_tickers:
                    st.markdown("**Watchlist**")
                    watchlist_filings = []
                    with st.spinner("Fetching watchlist SEC filings..."):
                        for ticker in watchlist_tickers:
                            try:
                                filings = finnhub_client.company_filings(ticker, _from=start_date, to=end_date)
                                if isinstance(filings, list):
                                    watchlist_filings.extend(filings[:3])
                            except:
                                continue

                    if watchlist_filings:
                        for filing in watchlist_filings[:8]:
                            filing_date = filing.get('filedDate', 'N/A')
                            filing_type = filing.get('form', 'N/A')
                            ticker = filing.get('symbol', '')
                            description = filing.get('description', 'No description')

                            with st.expander(f"**{ticker}** — {filing_type} ({filing_date})"):
                                st.write(description)
                                if filing.get('url'):
                                    st.markdown(f"[View Filing →]({filing['url']})")
                    else:
                        st.info("No recent SEC filings found for your watchlist.")

                # Refresh button
                if st.button("🔄 Refresh Market News & Filings", key="refresh_news"):
                    st.cache_data.clear()
                    st.rerun()

            except Exception as e:
                st.error(f"Could not fetch data: {e}")

    # ==================== AI AGENTS TAB ====================
    with agents_tab:
        st.subheader("🤖 AI Trading Agents")
        st.caption("Grok-powered analysis • Portfolio suggestions • Moonshot scanner")

        if client is None:
            st.error("Grok API client not available. Add GROK_API_KEY to secrets.toml")
        else:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                agent_mode = st.radio("Agent Mode", 
                                    ["Portfolio Review", "Moonshot Scanner", "Risk Assessment", "Buy/Sell Recommendation"], 
                                    horizontal=True)
            
            ticker_input = st.text_input("Focus on specific ticker (optional)", 
                                       placeholder="e.g. NVDA, TSLA, or leave blank for full portfolio")

            if st.button("🚀 Run AI Agent Analysis", type="primary"):
                with st.spinner("Grok is thinking..."):
                    if agent_mode == "Portfolio Review":
                        prompt = f"""You are EFA Investment Club's Chief AI Strategist. 
Current portfolio holdings: {list(holdings.keys())}
Total portfolio value: ${total_market_value:,.0f}
Review our portfolio and give a concise strategic assessment with 2-3 key recommendations."""
                    elif agent_mode == "Moonshot Scanner":
                        prompt = f"""Scan for 2-3 high-conviction moonshot ideas (2x+ potential in 12-24 months) that would fit our aggressive EFA Investment Club style. 
Current watchlist: {st.session_state.get('watchlist', [])}"""
                    else:
                        prompt = f"Analyze {ticker_input or 'the current portfolio'} for {agent_mode.lower()}."

                    try:
                        response = client.chat.completions.create(
                            model="grok-4-1-fast",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.7,
                            max_tokens=1200
                        )
                        st.markdown(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"AI call failed: {e}")

# ====================== TAB 9: EFA MULTI-AGENT TRADING SYSTEM ======================
with tab9:
    st.subheader("🧠 EFA Multi-Agent Trading System  •  v1.0 Beta")
    st.caption("Goal-Aware Analysis • Real RSI + MACD • Differentiated Recommendations • Live from Yahoo Finance")

    import sys
    import os
    import pandas as pd
    import yfinance as yf
    from datetime import datetime

    current_dir = os.path.dirname(os.path.abspath(__file__))
    agent_root = os.path.join(current_dir, "efa-trading-agent")
    agents_folder = os.path.join(agent_root, "agents")
    
    if agent_root not in sys.path:
        sys.path.append(agent_root)
    if agents_folder not in sys.path:
        sys.path.append(agents_folder)

    # ====================== AUTO-INITIALIZE ORCHESTRATOR (FIX) ======================
    if "orchestrator" not in st.session_state:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("orchestrator", 
                                                         os.path.join(agents_folder, "orchestrator.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            st.session_state.orchestrator = module.Orchestrator()
            st.caption("✅ Multi-Agent System auto-initialized (v1.0 Beta)")
        except Exception as e:
            st.error(f"Failed to auto-initialize Orchestrator: {e}")
            st.stop()

    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = load_analysis_history()

    # ====================== MANUAL RE-INITIALIZE BUTTON ======================
    if st.button("🔄 Re-initialize Multi-Agent System", type="secondary"):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("orchestrator", 
                                                         os.path.join(agents_folder, "orchestrator.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            st.session_state.orchestrator = module.Orchestrator()
            st.success("✅ Multi-Agent System Re-initialized!")
        except Exception as e:
            st.error(f"Failed to re-initialize: {e}")

    # ====================== PORTFOLIO ANALYSIS ======================
    st.markdown("### 📊 Current Portfolio Analysis & Rebalancing")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("Analyze Full Portfolio", type="primary"):
            if "orchestrator" not in st.session_state:
                st.error("Orchestrator not initialized. Please re-initialize above.")
            else:
                with st.spinner("Analyzing your real portfolio holdings..."):
                    # Always prefer the most up-to-date list from Tab 2 / top-level holdings
                    portfolio_holdings = st.session_state.get("portfolio_holdings") or list(holdings.keys())
                    portfolio_quantities = st.session_state.get("portfolio_quantities") or {ticker: h["qty"] for ticker, h in holdings.items()}

                    results = []
                    for ticker in portfolio_holdings:
                        try:
                            # Pass live price + goals so the agents have good data even if their internal fetch is flaky
                            live_price = get_price(ticker)
                            context = {
                                "goals": st.session_state.get("investment_goals", {}).get(ticker, {}),
                                "live_price": live_price if live_price > 0 else None
                            }
                            result = st.session_state.orchestrator.run_cycle(ticker, context)
                            result["quantity"] = portfolio_quantities.get(ticker, 0)
                            results.append(result)
                        except Exception as e:
                            st.error(f"Error on {ticker}: {e}")
                    
                    st.session_state.analysis_history.insert(0, {
                        "type": "Portfolio", 
                        "results": results, 
                        "time": datetime.now().strftime("%H:%M")
                    })
                    save_analysis_history(st.session_state.analysis_history)
                    st.success("✅ Portfolio Analysis Complete!")

    with col2:
        if st.button("🔄 Refresh Price Cache (used by Holdings)", type="secondary"):
            with st.spinner("Clearing price caches and pre-warming..."):
                try:
                    get_price.clear()
                except Exception:
                    pass
                portfolio_holdings = st.session_state.get("portfolio_holdings") or list(holdings.keys())
                watchlist = st.session_state.get("watchlist", [])
                all_tickers = list(set(portfolio_holdings + watchlist))
                
                warmed = 0
                for t in all_tickers:
                    try:
                        p = get_price(t)  # will hit live path + update last_prices.json
                        if p > 0:
                            warmed += 1
                    except Exception as e:
                        print(f"Price warm-up failed for {t}: {e}")
                st.success(f"✅ Cleared Streamlit cache + warmed prices for {warmed}/{len(all_tickers)} tickers. Check Tab 2.")

    # Display Portfolio Table
    for item in st.session_state.analysis_history:
        if item.get("type") == "Portfolio" and "results" in item:
            with st.expander(f"📊 Portfolio — {item['time']}", expanded=True):
                data = [{
                    "Ticker": r.get("ticker"),
                    "Shares Owned": round(r.get("quantity", 0), 4),
                    "Recommended Action": r.get("recommended_action", "Hold"),
                    "Current Price": f"${r.get('current_price',0):.2f}",
                    "Entry Price": f"${r.get('entry_price',0):.2f}",
                    "Exit Target": f"${r.get('exit_target',0):.2f}",
                    "Confidence": f"{r.get('confidence',0):.0%}",
                    "RSI": r.get("rsi", "N/A"),
                    "MACD Hist": r.get("macd_hist", "N/A"),
                    "Trend": r.get("trend","neutral").title(),
                    "Reason": r.get("reason","")
                } for r in item["results"]]
                
                df = pd.DataFrame(data)
                st.dataframe(df, width="stretch", hide_index=True)

                with st.expander("🔍 Agent Trace (raw data)", expanded=False):
                    for r in item["results"]:
                        st.markdown(f"**{r['ticker']}**")
                        st.json({
                            "current_price": r.get("current_price"),
                            "rsi": r.get("rsi"),
                            "macd_hist": r.get("macd_hist"),
                            "trend": r.get("trend"),
                            "confidence": r.get("confidence"),
                            "entry_price": r.get("entry_price"),
                            "exit_target": r.get("exit_target"),
                            "recommended_action": r.get("recommended_action")
                        })

    # ====================== WATCHLIST ANALYSIS ======================
    st.markdown("### ⭐ Watchlist Goal-Aware Analysis")
    watchlist = st.session_state.get("watchlist", [])

    if watchlist:
        selected = st.multiselect("Select tickers from watchlist", watchlist, default=watchlist[:4])
    else:
        selected = st.multiselect("Enter tickers", ["ENPH","HOOD","UNH"], default=["ENPH","HOOD"])

    if st.button("🚀 Run Watchlist Review", type="primary"):
        if "orchestrator" not in st.session_state:
            st.error("Orchestrator not initialized. Please re-initialize above.")
        else:
            with st.spinner("Analyzing watchlist..."):
                for ticker in selected:
                    try:
                        context = {"goals": st.session_state.get("investment_goals", {}).get(ticker, {})}
                        result = st.session_state.orchestrator.run_cycle(ticker, context)
                        st.session_state.analysis_history.insert(0, {
                            "type": "Watchlist", 
                            "ticker": ticker, 
                            "result": result, 
                            "time": datetime.now().strftime("%H:%M")
                        })
                    except Exception as e:
                        st.error(f"Error on {ticker}: {e}")
                
                save_analysis_history(st.session_state.analysis_history)
                st.success("✅ Watchlist Analysis Complete!")

    watchlist_items = [item for item in st.session_state.analysis_history if item.get("type") == "Watchlist"]
    if watchlist_items:
        watch_data = [{
            "Ticker": item["ticker"],
            "Recommended Action": item["result"].get("recommended_action", "Hold"),
            "Current Price": f"${item['result'].get('current_price',0):.2f}",
            "Entry Price": f"${item['result'].get('entry_price',0):.2f}",
            "Exit Target": f"${item['result'].get('exit_target',0):.2f}",
            "Confidence": f"{item['result'].get('confidence',0):.0%}",
            "RSI": item["result"].get("rsi", "N/A"),
            "MACD Hist": item["result"].get("macd_hist", "N/A"),
            "Reason": item["result"].get("reason","")[:110]
        } for item in watchlist_items]
        
        st.dataframe(pd.DataFrame(watch_data), width="stretch", hide_index=True)

    st.caption("v1.0 Beta • Results now persist in Supabase for all members • Real prices + real indicators from Yahoo Finance")