# EFA Investment Club — Changelog

## 2026-06-18 — Persistence hardening + admin gating

**Full detail:** see [CHANGELOG-2026-06-18.md](CHANGELOG-2026-06-18.md)

**Commits:** `4ad583c`, `780bb3b`, `e7c4351`

### Summary
- **Attachments & votes** in Meeting Scheduler now reload fresh storage before save; local JSON mirrors added.
- **Scheduler polls, availability, meetings, notes** use the same persist pattern; save failures surface in UI.
- **Tab 1** no longer auto-saves members every page load; balance editor admin-only.
- **Tab 2/4/9** save-result checks and fresh reload where needed.
- **Admin UI** (CSV upload, access tracker, allocation editor, meeting admin actions, etc.) restricted to **Antonio Calderon** only.
- **Tests:** 21 pytest tests passing (8 new persistence tests).

**After deploy:** Re-upload lost attachments; have members re-submit votes if lost before fix.

---

## 2026-06-16 (h) — CI fix (test + ui-smoke jobs)

**Root cause:** `local_data/` gitignored → site test agent failed on missing watchlist; live yfinance/Finnhub calls flaky on GitHub Actions; Playwright used brittle Streamlit selectors and empty watchlist (no Tab 6 table).

**Fix:** Committed `tests/fixtures/watchlist.json` + `seed_ci_fixtures()`; CI skips live network tests; watchlist loads from local JSON when Supabase offline; UI smoke switched from flaky Playwright to **Streamlit AppTest** (no browser); `EFA_CI_MODE` fast fundamentals mock.

---

## 2026-06-16 (g) — Tab 6 extended fundamentals (target, cash, FCF, EBIT)

**Root cause:** Finnhub `company_basic_financials` does not expose `totalCash` / `freeCashFlow` / analyst count under the keys we used; `price_target` is often empty on free tier. Render's partial yfinance `.info` also skips those fields.

**Fix:** Layer additional sources:
- Finnhub `price_target` + `recommendation_trends` (analyst count)
- Finnhub `financials` (ic/bs/cf annual) for EBITDA, cash, FCF
- yfinance `get_analyst_price_targets()`, `recommendations_summary`, and financial statements as fallback

**Action:** Admin → Tab 6 → **Clear fundamentals cache** once after deploy, then reload Tab 6.

---

## 2026-06-16 (f) — Data source validation (admin)

**Added:** Sidebar Finnhub key status; Tab 6 **Admin → Validate data sources** probes Finnhub quote/fundamentals, Yahoo chart, yfinance, Supabase cache, history SMAs, and merged Tab 6 row for any ticker (default FSLR). **Clear fundamentals cache** button for stale partial entries.

**Validate on Render:** Log in as admin → Tab 6 → expand validator → Run validation. Expect `finnhub_quote` + `finnhub_fundamentals` ✅ when `FINNHUB_API_KEY` is set.

---

## 2026-06-16 (e) — Tab 6 fundamentals multi-source fix

**Root cause:** On Render, yfinance `.info` often returns **only company name** (partial dict). Old code returned early on any `longName`, skipping industry/targets. Yahoo chart fallback (used for prices) has **no** industry, market cap, or analyst targets.

**Fix:** `fetch_ticker_info()` now merges: yfinance info + fast_info + **Finnhub** (profile, metrics, price target) + computed SMAs from history + **7-day Supabase cache**. Tab 6 warns if `FINNHUB_API_KEY` is missing.

**Action:** Ensure `FINNHUB_API_KEY` is set on Render (same key as Tab 8 news). After deploy, visit Tab 6 once to warm cache.

---

## 2026-06-16 (d) — CI, test suite, module split

**Files added:** `.github/workflows/ci.yml`, `efa_club_persistence.py`, `efa_club_auth.py`, `efa_club_meetings.py`, `tests/test_auth.py`, `tests/test_supabase_persistence.py`, `tests/test_ui_playwright.py`, `requirements-dev.txt`, `pytest.ini`

### Infrastructure
- **GitHub Actions CI** on every push/PR to `main`: site test agent + pytest unit tests + Playwright UI smoke (Ubuntu).
- **Module split** from monolithic `efa_club_app.py`:
  - `efa_club_persistence.py` — Supabase + local JSON
  - `efa_club_auth.py` — credentials + session tokens
  - `efa_club_meetings.py` — attachments + access log
  - `efa_club_services.py` — fundamentals + meeting helpers
- **Supabase mock tests** — read-modify-write, disconnect handling, local JSON fallback.
- **Playwright UI tests** — login, Tab 6 fundamentals, scheduler tab.

### Run tests locally
```bash
python tests/site_test_agent.py          # 10/10 regression checks
pytest tests/ -v --ignore=tests/test_ui_playwright.py   # unit tests
pip install -r requirements-dev.txt && playwright install chromium
pytest tests/test_ui_playwright.py -v    # UI smoke (needs Streamlit)
```

---

## 2026-06-16 (c) — Tab 6 regression fix + site test agent

**Files changed:** `efa_club_services.py` (new), `efa_club_app.py`, `tests/site_test_agent.py` (new)

### Problem
- Tab 6 portfolio/watchlist fundamentals showed **all N/A** after prior changes.
- Root cause: `get_fundamentals()` used a broad `except` that returned a full N/A row on any error (bad `float()` on yfinance fields, or `get_price_with_source` failure), and cached that poisoned result for 5 minutes.

### Solution
- Extracted resilient helpers to `efa_club_services.py`: `fetch_ticker_info()` (yfinance + Yahoo chart fallback), `build_fundamentals_row()`, `safe_float()`.
- `get_fundamentals()` no longer swallows errors into all-N/A; company name always falls back to ticker.
- Added **`tests/site_test_agent.py`** — run before every deploy:
  ```bash
  python tests/site_test_agent.py
  ```

### Before next deploy (required)
1. Run `python tests/site_test_agent.py` — must show **9/9 passed**.
2. Deploy only if Tab 6 test passes for all portfolio + watchlist tickers.

---

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