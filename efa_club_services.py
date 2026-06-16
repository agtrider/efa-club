"""
Pure service helpers for EFA Club — no Streamlit dependency.
Used by efa_club_app.py and tests/site_test_agent.py to prevent UI regressions.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import requests
import yfinance as yf

_YAHOO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_CORE_INFO_FIELDS = (
    "industry",
    "marketCap",
    "targetMeanPrice",
    "fiftyDayAverage",
    "forwardPE",
    "trailingEps",
)
_CACHE_TTL_HOURS = 168  # 7 days


def safe_float(val):
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def safe_int(val):
    f = safe_float(val)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _merge_info(base, extra):
    """Merge extra into base without overwriting non-empty values."""
    out = dict(base or {})
    for key, val in (extra or {}).items():
        if str(key).startswith("_"):
            continue
        if val is None or val == "":
            continue
        if key not in out or out.get(key) in (None, "", 0):
            out[key] = val
    return out


def _info_completeness(info):
    if not info:
        return 0
    return sum(1 for k in _CORE_INFO_FIELDS if info.get(k) not in (None, "", 0))


def _yahoo_chart_request(tkr, params):
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
            print(f"[yahoo chart info] {tkr} via {host}: {e}")
    return None


def _load_cached_fundamentals(tkr):
    try:
        from efa_club_persistence import load_from_supabase
        cache = load_from_supabase("fundamentals_cache", {}) or {}
        entry = cache.get(tkr)
        if not entry or not isinstance(entry, dict):
            return {}
        fetched_at = entry.get("fetched_at")
        data = entry.get("data", {})
        if fetched_at and data:
            try:
                age = datetime.now() - datetime.fromisoformat(fetched_at)
                if age <= timedelta(hours=_CACHE_TTL_HOURS):
                    data = dict(data)
                    data["_source"] = "supabase_cache"
                    return data
            except Exception:
                pass
        return {}
    except Exception:
        return {}


def _save_cached_fundamentals(tkr, info):
    if _info_completeness(info) < 2:
        return
    try:
        from efa_club_persistence import load_from_supabase, save_to_supabase
        cache = load_from_supabase("fundamentals_cache", {}) or {}
        cache[tkr] = {
            "data": {k: v for k, v in info.items() if not str(k).startswith("_")},
            "fetched_at": datetime.now().isoformat(),
        }
        save_to_supabase("fundamentals_cache", cache)
    except Exception as e:
        print(f"[fundamentals_cache] save {tkr}: {e}")


def _fetch_yfinance_info(tkr):
    merged = {}
    try:
        stock = yf.Ticker(tkr)
        merged = _merge_info(merged, stock.info or {})
    except Exception as e:
        print(f"[fetch_ticker_info] yfinance info {tkr}: {e}")

    try:
        fi = getattr(yf.Ticker(tkr), "fast_info", {}) or {}
        getter = getattr(fi, "get", None)

        def _fi(*keys):
            for key in keys:
                val = getter(key) if getter else getattr(fi, key, None)
                if val is not None:
                    return val
            return None

        fast = {
            "marketCap": _fi("market_cap", "marketCap"),
            "fiftyDayAverage": _fi("fifty_day_average", "fiftyDayAverage"),
            "twoHundredDayAverage": _fi("two_hundred_day_average", "twoHundredDayAverage"),
        }
        merged = _merge_info(merged, {k: v for k, v in fast.items() if v is not None})
    except Exception as e:
        print(f"[fetch_ticker_info] fast_info {tkr}: {e}")

    if merged:
        merged["_source"] = merged.get("_source", "yfinance")
    return merged


def _fetch_yahoo_chart_meta(tkr):
    res = _yahoo_chart_request(tkr, {"interval": "1d", "range": "1mo"})
    if not res:
        return {}
    meta = res.get("meta") or {}
    return {
        "longName": meta.get("longName") or meta.get("shortName"),
        "shortName": meta.get("shortName"),
        "regularMarketPrice": meta.get("regularMarketPrice"),
        "_source": "yahoo_chart_meta",
    }


def _fetch_finnhub_info(tkr, client):
    if client is None:
        return {}
    out = {}
    try:
        profile = client.company_profile2(symbol=tkr)
        if profile:
            out = _merge_info(out, {
                "longName": profile.get("name"),
                "industry": profile.get("finnhubIndustry"),
            })
            mc = safe_float(profile.get("marketCapitalization"))
            if mc and mc > 0:
                out["marketCap"] = mc * 1_000_000
    except Exception as e:
        print(f"[fetch_ticker_info] finnhub profile {tkr}: {e}")

    try:
        metrics = client.company_basic_financials(tkr, "all")
        metric = (metrics or {}).get("metric", {}) or {}
        mc_metric = safe_float(metric.get("marketCapitalization"))
        out = _merge_info(out, {
            "trailingEps": metric.get("epsBasicExclExtraItemsTTM") or metric.get("epsTTM"),
            "forwardPE": metric.get("peBasicExclExtraTTM") or metric.get("peTTM"),
            "ebitda": metric.get("ebitdaTTM") or metric.get("ebitda"),
            "totalCash": metric.get("totalCash"),
            "freeCashflow": metric.get("freeCashFlow") or metric.get("fcfTTM"),
        })
        if mc_metric and mc_metric > 0 and not out.get("marketCap"):
            out["marketCap"] = mc_metric * 1_000_000
    except Exception as e:
        print(f"[fetch_ticker_info] finnhub metrics {tkr}: {e}")

    try:
        pt = client.price_target(tkr)
        if pt:
            out = _merge_info(out, {
                "targetMeanPrice": pt.get("targetMean") or pt.get("targetMedian"),
                "numberOfAnalystOpinions": pt.get("targetNumber") or pt.get("numberOfAnalysts"),
            })
    except Exception as e:
        print(f"[fetch_ticker_info] finnhub price_target {tkr}: {e}")

    if out:
        out["_source"] = "finnhub"
    return out


def _compute_smas_from_history(tkr):
    try:
        df = yf.download(tkr, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return {}
        close = df["Close"]
        if isinstance(close, __import__("pandas").DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            return {}
        out = {}
        if len(close) >= 50:
            out["fiftyDayAverage"] = float(close.rolling(50).mean().iloc[-1])
        if len(close) >= 200:
            out["twoHundredDayAverage"] = float(close.rolling(200).mean().iloc[-1])
        if out:
            out["_source"] = "computed_history"
        return out
    except Exception as e:
        print(f"[fetch_ticker_info] history SMA {tkr}: {e}")
        return {}


def _get_finnhub_client(explicit_client=None):
    if explicit_client is not None:
        return explicit_client
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    try:
        import finnhub
        return finnhub.Client(api_key=key)
    except Exception:
        return None


def fetch_ticker_info(ticker, finnhub_client=None, use_cache=True):
    """
    Multi-source fundamentals merge. Never returns early on partial yfinance data.
    On Render, yfinance often returns only longName — we layer Finnhub, cache, and history.
    """
    tkr = str(ticker).upper().strip()
    if not tkr or tkr in ("CASH", "-"):
        return {}

    merged = {}
    if use_cache:
        merged = _merge_info(merged, _load_cached_fundamentals(tkr))

    merged = _merge_info(merged, _fetch_yfinance_info(tkr))
    merged = _merge_info(merged, _fetch_finnhub_info(tkr, _get_finnhub_client(finnhub_client)))
    merged = _merge_info(merged, _fetch_yahoo_chart_meta(tkr))
    merged = _merge_info(merged, _compute_smas_from_history(tkr))

    if not merged.get("longName") and not merged.get("shortName"):
        merged["longName"] = tkr
        merged["_source"] = "ticker_fallback"

    if _info_completeness(merged) >= 2:
        _save_cached_fundamentals(tkr, merged)

    return merged


def build_fundamentals_row(ticker, info, price=0.0, price_source=""):
    """Build Tab 6 fundamentals dict — never all-N/A unless data is truly missing."""
    tkr = str(ticker).upper().strip()
    info = info or {}
    company = info.get("longName") or info.get("shortName") or tkr
    industry = info.get("industry") or "N/A"

    market_cap = safe_float(info.get("marketCap"))
    sma50 = safe_float(info.get("fiftyDayAverage"))
    sma200 = safe_float(info.get("twoHundredDayAverage"))
    forward_pe = safe_float(info.get("forwardPE"))
    target = safe_float(info.get("targetMeanPrice"))
    analysts = safe_int(info.get("numberOfAnalystOpinions"))
    ebitda = safe_float(info.get("ebitda"))
    trailing_eps = safe_float(info.get("trailingEps"))
    forward_eps = safe_float(info.get("forwardEps"))
    total_cash = safe_float(info.get("totalCash"))
    fcf = safe_float(info.get("freeCashflow"))
    px = safe_float(price) or 0.0

    return {
        "Ticker": tkr,
        "Company": company,
        "Industry": industry,
        "Current Price": f"${px:.2f}" if px > 0 else "N/A",
        "Price Source": price_source if px > 0 else "unavailable — click Force Refresh on Tab 2",
        "Market Cap": f"${market_cap / 1e9:.2f}B" if market_cap and market_cap > 0 else "N/A",
        "50d SMA": f"${sma50:.2f}" if sma50 and sma50 > 0 else "N/A",
        "200d SMA": f"${sma200:.2f}" if sma200 and sma200 > 0 else "N/A",
        "Forward P/E": f"{forward_pe:.2f}" if forward_pe else "N/A",
        "Analyst Target": f"${target:.2f}" if target and target > 0 else "N/A",
        "Analysts": str(analysts) if analysts is not None else "N/A",
        "3MMT EBIT": f"${ebitda / 1e9:.2f}B" if ebitda and ebitda > 0 else "N/A",
        "12MMT EPS": f"{trailing_eps:.2f}" if trailing_eps is not None else "N/A",
        "Forward EPS": f"{forward_eps:.2f}" if forward_eps is not None else "N/A",
        "Cash (B)": f"${total_cash / 1e9:.2f}B" if total_cash and total_cash > 0 else "N/A",
        "FCF (B)": f"${fcf / 1e9:.2f}B" if fcf and fcf > 0 else "N/A",
    }


def fundamentals_row_is_healthy(row):
    """True when row has real company identity (not a poisoned all-N/A cache entry)."""
    if not row:
        return False
    company = row.get("Company", "")
    return company not in ("", "N/A", None) and row.get("Ticker") not in ("", None)


def fundamentals_row_has_core_data(row):
    """True when at least one key fundamental beyond price is populated."""
    if not row:
        return False
    core_cols = ("Industry", "Market Cap", "Analyst Target", "50d SMA", "Forward P/E")
    return any(row.get(c) not in (None, "", "N/A") for c in core_cols)


def _probe_fields(data, fields):
    """Return comma-separated field names that have non-empty values."""
    found = []
    for field in fields:
        val = (data or {}).get(field)
        if val not in (None, "", 0):
            found.append(field)
    return found


def _check_row(source, ok, detail, fields=None):
    return {
        "source": source,
        "status": "ok" if ok else "fail",
        "detail": detail,
        "fields": fields or [],
    }


def validate_data_sources(ticker="FSLR", finnhub_client=None):
    """
    Probe each fundamentals/price layer independently (admin diagnostics).
    Returns list of {source, status, detail, fields} where status is ok|warn|fail|skip.
    """
    tkr = str(ticker).upper().strip() or "FSLR"
    checks = []
    fh_key = os.environ.get("FINNHUB_API_KEY", "")
    client = _get_finnhub_client(finnhub_client)

    if fh_key:
        checks.append(_check_row("FINNHUB_API_KEY", True, f"set ({len(fh_key)} chars)", ["configured"]))
    else:
        checks.append(_check_row("FINNHUB_API_KEY", False, "not set — Tab 6/8 cloud fallbacks limited"))

    if client is None:
        checks.append({
            "source": "finnhub_quote",
            "status": "skip",
            "detail": "no client",
            "fields": [],
        })
        checks.append({
            "source": "finnhub_fundamentals",
            "status": "skip",
            "detail": "no client",
            "fields": [],
        })
    else:
        try:
            q = client.quote(tkr)
            price = safe_float((q or {}).get("c"))
            if price and price > 0:
                checks.append(_check_row("finnhub_quote", True, f"${price:.2f}", ["c"]))
            else:
                checks.append(_check_row("finnhub_quote", False, "empty or zero quote"))
        except Exception as e:
            checks.append(_check_row("finnhub_quote", False, str(e)[:120]))

        fh_info = _fetch_finnhub_info(tkr, client)
        fh_fields = _probe_fields(
            fh_info,
            ("longName", "industry", "marketCap", "targetMeanPrice", "trailingEps", "forwardPE"),
        )
        if fh_fields:
            checks.append(_check_row("finnhub_fundamentals", True, f"{len(fh_fields)} fields", fh_fields))
        else:
            checks.append(_check_row("finnhub_fundamentals", False, "no profile/metrics/target data"))

    yf_info = _fetch_yfinance_info(tkr)
    yf_fields = _probe_fields(
        yf_info,
        ("longName", "industry", "marketCap", "targetMeanPrice", "fiftyDayAverage", "forwardPE"),
    )
    if len(yf_fields) >= 2:
        checks.append(_check_row("yfinance_info", True, f"{len(yf_fields)} fields", yf_fields))
    elif yf_fields:
        checks.append({
            "source": "yfinance_info",
            "status": "warn",
            "detail": f"partial ({len(yf_fields)} fields) — common on Render",
            "fields": yf_fields,
        })
    else:
        checks.append(_check_row("yfinance_info", False, "no usable fields"))

    chart = _fetch_yahoo_chart_meta(tkr)
    chart_fields = _probe_fields(chart, ("longName", "regularMarketPrice"))
    if chart_fields:
        checks.append(_check_row("yahoo_chart", True, f"{len(chart_fields)} fields", chart_fields))
    else:
        checks.append(_check_row("yahoo_chart", False, "chart meta unavailable"))

    cached = _load_cached_fundamentals(tkr)
    cache_fields = _probe_fields(cached, _CORE_INFO_FIELDS)
    if cache_fields:
        checks.append(_check_row("supabase_fundamentals_cache", True, f"{len(cache_fields)} cached fields", cache_fields))
    else:
        checks.append({
            "source": "supabase_fundamentals_cache",
            "status": "warn",
            "detail": "no fresh cache entry (will warm on first Tab 6 load)",
            "fields": [],
        })

    hist = _compute_smas_from_history(tkr)
    hist_fields = _probe_fields(hist, ("fiftyDayAverage", "twoHundredDayAverage"))
    if hist_fields:
        checks.append(_check_row("history_sma", True, f"{len(hist_fields)} SMAs", hist_fields))
    else:
        checks.append(_check_row("history_sma", False, "could not compute SMAs from history"))

    merged = fetch_ticker_info(tkr, finnhub_client=client, use_cache=False)
    merged_fields = _probe_fields(merged, _CORE_INFO_FIELDS)
    row = build_fundamentals_row(tkr, merged, price=100.0, price_source="validation_probe")
    core_ok = fundamentals_row_has_core_data(row)
    merge_ok = len(merged_fields) >= 2 and core_ok
    checks.append({
        "source": "merged_tab6_row",
        "status": "ok" if merge_ok else ("warn" if core_ok else "fail"),
        "detail": (
            f"completeness={_info_completeness(merged)} core_cols={'yes' if core_ok else 'no'}"
            if merged_fields or core_ok
            else "merge produced no core fundamentals"
        ),
        "fields": merged_fields,
    })

    try:
        from efa_club_persistence import supabase
        if supabase:
            supabase.table("club_data").select("id").limit(1).execute()
            checks.append(_check_row("supabase_connection", True, "club_data reachable"))
        else:
            checks.append({
                "source": "supabase_connection",
                "status": "warn",
                "detail": "local only (no Supabase client)",
                "fields": [],
            })
    except Exception as e:
        checks.append(_check_row("supabase_connection", False, str(e)[:120]))

    return checks


def normalize_meeting_record(meeting):
    if not isinstance(meeting, dict):
        return meeting
    meeting = dict(meeting)
    if "note_entries" not in meeting:
        meeting["note_entries"] = []
        legacy_notes = meeting.get("notes", "")
        if isinstance(legacy_notes, str) and legacy_notes.strip():
            meeting["note_entries"].append({
                "id": 1,
                "author": "Legacy Import",
                "text": legacy_notes.strip(),
                "created": meeting.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
                "updated": meeting.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
            })
    if "attachments" not in meeting:
        meeting["attachments"] = []
    if "votes" not in meeting:
        meeting["votes"] = []
    meeting.pop("notes", None)
    return meeting


def can_edit_note(note, username, is_admin):
    if not note or not username:
        return False
    if is_admin:
        return True
    return note.get("author") == username


def normalize_availability_responses(responses, proposals):
    """Migrate old flat {username: [slots]} format to per-poll structure."""
    if not responses or not isinstance(responses, dict):
        return {}
    sample = next(iter(responses.values()), None)
    if isinstance(sample, (list, tuple)):
        legacy_slots = []
        for lst in responses.values():
            if isinstance(lst, (list, tuple)):
                legacy_slots.extend(lst)
        legacy_text = " ".join(str(s) for s in legacy_slots)
        target_key = None
        if proposals:
            for poll in proposals:
                ws = poll.get("week_start", "")
                we = poll.get("week_end", "")
                if (ws and ws in legacy_text) or (we and we in legacy_text):
                    target_key = str(poll.get("id", proposals.index(poll) + 1))
                    break
            if target_key is None:
                first_poll = proposals[0]
                target_key = str(first_poll.get("id", 1))
            return {target_key: responses}
        return {}
    return responses