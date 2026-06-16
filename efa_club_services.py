"""
Pure service helpers for EFA Club — no Streamlit dependency.
Used by efa_club_app.py and tests/site_test_agent.py to prevent UI regressions.
"""
from __future__ import annotations

import math
import requests
import yfinance as yf
from datetime import datetime

_YAHOO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


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


def fetch_ticker_info(ticker):
    """yfinance .info with Yahoo chart meta fallback (works when yfinance rate-limits)."""
    tkr = str(ticker).upper().strip()
    if not tkr or tkr in ("CASH", "-"):
        return {}

    try:
        info = yf.Ticker(tkr).info or {}
        if info.get("longName") or info.get("shortName") or info.get("marketCap"):
            return info
    except Exception as e:
        print(f"[fetch_ticker_info] yfinance {tkr}: {e}")

    res = _yahoo_chart_request(tkr, {"interval": "1d", "range": "1mo"})
    if res:
        meta = res.get("meta") or {}
        return {
            "longName": meta.get("longName") or meta.get("shortName") or tkr,
            "shortName": meta.get("shortName", tkr),
            "industry": meta.get("industry"),
            "marketCap": meta.get("marketCap"),
            "fiftyDayAverage": meta.get("fiftyDayAverage"),
            "twoHundredDayAverage": meta.get("twoHundredDayAverage"),
            "forwardPE": meta.get("forwardPE"),
            "targetMeanPrice": meta.get("targetMeanPrice"),
            "numberOfAnalystOpinions": meta.get("numberOfAnalystOpinions"),
            "ebitda": meta.get("ebitda"),
            "trailingEps": meta.get("trailingEps"),
            "forwardEps": meta.get("forwardEps"),
            "totalCash": meta.get("totalCash"),
            "freeCashflow": meta.get("freeCashflow"),
            "_source": "yahoo_chart_meta",
        }

    return {"longName": tkr, "shortName": tkr, "_source": "ticker_fallback"}


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