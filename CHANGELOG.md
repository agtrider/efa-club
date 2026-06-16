# EFA Investment Club — Changelog

## 2026-06-16 (b) — Meeting notes v2, attachments, access tracker

**Files changed:** `efa_club_app.py`

### Problems fixed
- Saving meeting notes failed when large AI transcripts were pasted inline (bloated Supabase `club_data` JSON).
- Attachments were embedded in the notes text area instead of being downloadable files.
- Single shared notes field — no per-member notes or edit permissions.

### Solutions
- **Multiple notes:** Each meeting has `note_entries` (author, text, timestamps). Members add notes; edit/delete own notes only; admin can edit any note.
- **Attachments:** Files stored in separate Supabase key `meeting_attachment_store` (base64, max 3 MB). Meeting keeps download links only — not shown inline in notes.
- **Save reliability:** `save_to_supabase` retries 3×, validates `club_data` row exists, surfaces error message in UI; local JSON fallback for meetings.
- **Access tracker:** Admin sidebar **Member Access Tracker** — logs login/logout events per member (`access_log` in Supabase).

### After deploy
1. If an old meeting has a huge "Legacy Import" note, admin can delete it and re-upload the file as an attachment.
2. Use **Add Note** for commentary; use **Upload Attachment** for AI transcripts.

---

## 2026-06-16 — Auth persistence, scheduler fixes, Tab 6/9 overhaul (v1.1)

**Commit:** Fix login refresh, meeting notes save, Tab 6 table errors, Tab 9 agent data quality  
**Files changed:** `efa_club_app.py`, `efa-trading-agent/agents/research.py`, `efa-trading-agent/agents/orchestrator.py`

### Problems fixed
- **Meeting Scheduler (Tab 7):** Saving meeting notes could reset the page and return users to the login screen; no feedback when Supabase writes failed.
- **Login:** Browser refresh logged users out because auth lived only in ephemeral Streamlit `session_state`.
- **Tab 6:** Portfolio and watchlist fundamentals tables errored when yfinance failed — `NumberColumn` received `"N/A"` strings and mixed numeric/text types in `Forward P/E`, `Analysts`, and EPS fields.
- **Tab 9:** Exit targets, confidence, RSI, and MACD showed stale or synthetic values; multiple timestamped tables cluttered the UI; reasons were too brief.

### Solutions
- **Persistent login:** Supabase-backed `member_sessions` with 30-day tokens; `sid` query param restores session on refresh. Logout revokes the token. Auto-login on password typing removed (Login button only).
- **Meeting notes:** Notes save inside a `st.form` with explicit Supabase success/error handling. Added file upload for AI meeting minutes (TXT, MD, JSON, CSV) from Otter, Fireflies, Zoom AI Companion, etc.
- **Tab 6:** All fundamentals columns use `TextColumn` with consistent string formatting; Grok analyze checks for API key before running.
- **Tab 9 (v1.1):**
  - `build_agent_context()` passes live club prices + daily close history into agents (same sources as Tab 2).
  - Research agent v8 and orchestrator v1.1 compute real RSI/MACD from history; richer plain-language reasons.
  - UI shows **latest run only** for portfolio and watchlist (full history still stored in Supabase).
  - Added **Field Definitions** expander below the analysis tables.

### After deploy on Render
1. Wait for Render to finish building from `main` (auto-deploy when GitHub hook is connected).
2. Log in once — URL will include `?sid=...` for refresh persistence.
3. **Tab 9:** Run **Analyze Full Portfolio** and **Run Watchlist Review** to refresh with live data.
4. **Tab 7:** Test saving notes and uploading AI meeting minutes.
5. **Tab 2 (optional):** Force Refresh Live Prices if any quotes look stale.

### Validation (local, 2026-06-16)
- `python -m py_compile` passed on `efa_club_app.py`, `research.py`, `orchestrator.py`.

---

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