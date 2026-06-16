# EFA Multi-Agent Trading System

Embedded agents used by **Tab 9** of the main EFA Investment Club Streamlit app (`efa_club_app.py`).

## Version history

### v1.1 (2026-06-16)
- **Research agent v8:** Accepts `live_price`, `close_prices`, and `analyst_target` from the main app via `build_agent_context()` — same Yahoo chart / Finnhub price path as Tab 2.
- **Orchestrator v1.1:** Richer recommendation reasons (RSI zone, MACD momentum, trend, analyst upside, goal type, data quality).
- Indicators computed from real daily close history when available; confidence score weights data quality.
- Tab 9 UI shows latest portfolio/watchlist run only; field definitions documented in-app.

### v1.0 Beta
- Initial goal-aware portfolio and watchlist analysis.
- RSI, MACD, trend, entry/exit heuristics with yfinance fallbacks.

## Key files
| File | Role |
|------|------|
| `agents/research.py` | Price fetch, RSI/MACD/SMA, confidence scoring |
| `agents/orchestrator.py` | Goal-aware buy/hold/trim decisions and reason text |
| `agents/signal.py` | Signal generation (future use) |

## Guardrails
See [GUARDRAILS.md](./GUARDRAILS.md) for trading safety rules (human-in-the-loop, no margin, position limits).