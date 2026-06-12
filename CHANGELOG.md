# EFA Investment Club — Changelog

## 2026-06-12 — Session-aware live prices (Yahoo chart primary)

**Commit:** Session-aware Yahoo chart pricing; fix yfinance fast_info keys and cache fallback  
**Files changed:** `efa_club_app.py` only

### Problem
- yfinance rate-limits on Render/cloud IPs (unofficial Yahoo scraper, not a real API).
- Code looked up wrong `fast_info` keys (`last_price` / `regularMarketPrice`); yfinance 1.x uses `lastPrice` / `previousClose`.
- Cache fallback rejected legacy entries missing a `source` field → prices showed **$0.00** when APIs failed.

### Solution
- **Primary source:** Yahoo Chart API (`v8/finance/chart`) with `query1` → `query2` fallback.
- **Session-aware pricing:**
  - Pre-market → prior session close
  - Market open (9:30–16:00 ET) → latest intraday price
  - After hours → today's close
  - Weekend → last trading day close (Friday)
- **Fallback order:** Yahoo chart → Finnhub (if `FINNHUB_API_KEY` set) → yfinance → cached market price (never purchase fills).
- **UI:** Tab 2 market status badge (pre-market / after-hours / weekend); Force Refresh button label updated. Tab 6 uses same `get_price()` path via `get_fundamentals()`.

### After deploy on Render
1. Wait for Render to finish building from `main` (auto-deploy if GitHub hook is connected).
2. Open the app → **Tab 2** → click **Force Refresh Live Prices** once.
3. Confirm **Price Source** shows labels like `Live (Yahoo chart)` or `Prior Close (Yahoo chart)`.

### Validation (local, 2026-06-12)
- All 10 portfolio tickers returned live prices via Yahoo chart API.
- `python -m py_compile efa_club_app.py` passed.
- No other files modified in this change.

---

## 2026-06-11 — Unified market prices v3

- Yahoo chart API + Finnhub fallbacks; Tab 6 aligned with Tab 2 `get_price`.
- Stopped using transaction purchase fills as market quotes.
- Purged invalid `csv_fill` entries from price cache.