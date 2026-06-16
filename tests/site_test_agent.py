#!/usr/bin/env python3
"""
EFA Club Site Test Agent — end-to-end regression checks without launching Streamlit UI.

Run: python tests/site_test_agent.py
Exit code 0 = all checks passed, 1 = failures found.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Sample tickers from typical club portfolio + watchlist
PORTFOLIO_TICKERS = ["FSLR", "TSLA", "ACHR", "SMR", "TE", "PLTR", "SPY", "QQQ", "IWM", "NVDA"]
WATCHLIST_TICKERS = ["ENPH", "UNH", "HOOD"]


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.detail = ""

    def ok(self, detail=""):
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail=""):
        self.passed = False
        self.detail = detail
        return self


def run_test(name, fn):
    try:
        return fn()
    except Exception as e:
        return TestResult(name).fail(f"{e}\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# 1. Module / syntax
# ---------------------------------------------------------------------------
def test_syntax():
    import py_compile
    files = [
        ROOT / "efa_club_app.py",
        ROOT / "efa_club_services.py",
        ROOT / "efa-trading-agent" / "agents" / "research.py",
        ROOT / "efa-trading-agent" / "agents" / "orchestrator.py",
    ]
    for f in files:
        py_compile.compile(str(f), doraise=True)
    return TestResult("syntax_compile").ok(f"{len(files)} files compile")


# ---------------------------------------------------------------------------
# 2. Tab 6 fundamentals (core regression)
# ---------------------------------------------------------------------------
def test_fetch_ticker_info():
    from efa_club_services import fetch_ticker_info, fundamentals_row_is_healthy, build_fundamentals_row

    failures = []
    for t in PORTFOLIO_TICKERS[:5]:
        info = fetch_ticker_info(t)
        row = build_fundamentals_row(t, info, price=100.0, price_source="test")
        if not fundamentals_row_is_healthy(row):
            failures.append(f"{t}: company={row.get('Company')}")
        elif row.get("Company") == "N/A":
            failures.append(f"{t}: Company still N/A")
    if failures:
        return TestResult("tab6_fetch_ticker_info").fail("; ".join(failures))
    return TestResult("tab6_fetch_ticker_info").ok(f"5/{5} tickers have company names")


def test_fundamentals_all_portfolio_watchlist():
    from efa_club_services import fetch_ticker_info, build_fundamentals_row, fundamentals_row_is_healthy

    all_tickers = list(dict.fromkeys(PORTFOLIO_TICKERS + WATCHLIST_TICKERS))
    bad = []
    good = 0
    for t in all_tickers:
        info = fetch_ticker_info(t)
        row = build_fundamentals_row(t, info, price=50.0, price_source="test")
        if fundamentals_row_is_healthy(row) and row.get("Company") != "N/A":
            good += 1
        else:
            bad.append(f"{t}→{row.get('Company')}")
    if bad:
        return TestResult("tab6_all_tickers").fail(
            f"{good}/{len(all_tickers)} OK; failures: {', '.join(bad)}"
        )
    return TestResult("tab6_all_tickers").ok(f"{good}/{len(all_tickers)} tickers healthy")


def test_safe_float_edge_cases():
    from efa_club_services import safe_float, build_fundamentals_row

    row = build_fundamentals_row(
        "TEST",
        {"longName": "Test Co", "forwardPE": "not-a-number", "trailingEps": float("nan")},
        price=10.0,
        price_source="test",
    )
    if row.get("Company") != "Test Co":
        return TestResult("safe_float_edges").fail(f"Company={row.get('Company')}")
    if row.get("Forward P/E") != "N/A":
        return TestResult("safe_float_edges").fail(f"Forward P/E should be N/A, got {row.get('Forward P/E')}")
    return TestResult("safe_float_edges").ok("bad numerics do not crash row build")


# ---------------------------------------------------------------------------
# 3. Meeting notes / permissions
# ---------------------------------------------------------------------------
def test_meeting_notes_permissions():
    from efa_club_services import normalize_meeting_record, can_edit_note

    m = normalize_meeting_record({"id": 1, "date": "2026-01-01", "notes": "legacy text"})
    if len(m.get("note_entries", [])) != 1:
        return TestResult("meeting_migration").fail("legacy notes not migrated")
    if "notes" in m:
        return TestResult("meeting_migration").fail("legacy notes key not removed")

    own = {"author": "Chris Koo", "text": "hi"}
    other = {"author": "Jeff Gragert", "text": "hi"}
    if not can_edit_note(own, "Chris Koo", False):
        return TestResult("meeting_permissions").fail("member cannot edit own note")
    if can_edit_note(other, "Chris Koo", False):
        return TestResult("meeting_permissions").fail("member can edit other's note")
    if not can_edit_note(other, "Chris Koo", True):
        return TestResult("meeting_permissions").fail("admin cannot edit other's note")
    return TestResult("meeting_permissions").ok("migration + edit rules OK")


# ---------------------------------------------------------------------------
# 4. Multi-agent orchestrator (Tab 9)
# ---------------------------------------------------------------------------
def test_orchestrator_cycle():
    agents_dir = ROOT / "efa-trading-agent" / "agents"
    sys.path.insert(0, str(agents_dir.parent))
    sys.path.insert(0, str(agents_dir))

    spec = importlib.util.spec_from_file_location("orchestrator", agents_dir / "orchestrator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    orch = mod.Orchestrator()
    ctx = {
        "goals": {"investment_type": "Moonshot", "goal_type": "Long Term (>1 Yr)"},
        "live_price": 250.0,
        "close_prices": [240 + i * 0.5 for i in range(60)],
        "analyst_target": 300.0,
    }
    result = orch.run_cycle("TSLA", ctx)
    required = ["ticker", "current_price", "recommended_action", "reason", "rsi", "macd_hist", "confidence", "exit_target"]
    missing = [k for k in required if k not in result]
    if missing:
        return TestResult("tab9_orchestrator").fail(f"missing fields: {missing}")
    if result["current_price"] <= 0:
        return TestResult("tab9_orchestrator").fail("current_price is zero")
    if len(result.get("reason", "")) < 40:
        return TestResult("tab9_orchestrator").fail("reason too short")
    return TestResult("tab9_orchestrator").ok(
        f"TSLA → {result['recommended_action']} RSI={result['rsi']} conf={result['confidence']}"
    )


# ---------------------------------------------------------------------------
# 5. Local data / config files
# ---------------------------------------------------------------------------
def test_local_data_files():
    watchlist_path = ROOT / "local_data" / "watchlist.json"
    if not watchlist_path.exists():
        return TestResult("local_data").fail("watchlist.json missing")
    wl = json.loads(watchlist_path.read_text(encoding="utf-8"))
    if not isinstance(wl, list):
        return TestResult("local_data").fail("watchlist.json not a list")
    return TestResult("local_data").ok(f"watchlist has {len(wl)} tickers")


def test_requirements_imports():
    imports = ["streamlit", "pandas", "yfinance", "requests", "numpy"]
    missing = []
    for mod in imports:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return TestResult("requirements").fail(f"missing packages: {missing}")
    return TestResult("requirements").ok(f"{len(imports)} core packages importable")


# ---------------------------------------------------------------------------
# 6. Yahoo chart fallback (Render-critical path)
# ---------------------------------------------------------------------------
def test_yahoo_chart_fallback():
    from efa_club_services import fetch_ticker_info

    info = fetch_ticker_info("FSLR")
    source = info.get("_source", "yfinance")
    name = info.get("longName") or info.get("shortName")
    if not name or name == "N/A":
        return TestResult("yahoo_fallback").fail(f"no company name; source={source}")
    return TestResult("yahoo_fallback").ok(f"FSLR={name} (source={source})")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
ALL_TESTS = [
    test_syntax,
    test_requirements_imports,
    test_local_data_files,
    test_safe_float_edge_cases,
    test_fetch_ticker_info,
    test_fundamentals_all_portfolio_watchlist,
    test_yahoo_chart_fallback,
    test_meeting_notes_permissions,
    test_orchestrator_cycle,
]


def main():
    print("=" * 60)
    print("EFA CLUB SITE TEST AGENT")
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Root:   {ROOT}")
    print("=" * 60)

    results = []
    for fn in ALL_TESTS:
        r = run_test(fn.__name__, fn)
        r.name = fn.__name__
        results.append(r)
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name}")
        if r.detail:
            print(f"         {r.detail}")

    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    print("=" * 60)
    print(f"RESULT: {passed}/{len(results)} passed")
    if failed:
        print("\nFAILURES:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        print("\nRECOMMENDED CHANGES BEFORE NEXT DEPLOY:")
        print_recommendations(failed)
        return 1
    print("\nAll checks passed. Safe to deploy.")
    return 0


def print_recommendations(failed):
    names = {r.name for r in failed}
    if names & {"tab6_fetch_ticker_info", "tab6_all_tickers", "yahoo_fallback"}:
        print("  • Tab 6: verify yfinance + Yahoo chart API from Render IP; do not cache all-N/A rows.")
    if "tab9_orchestrator" in names:
        print("  • Tab 9: verify efa-trading-agent agents import and live_price context is passed.")
    if "meeting_permissions" in names or "meeting_migration" in names:
        print("  • Tab 7: review efa_club_services meeting helpers and Supabase save paths.")
    if "syntax_compile" in names:
        print("  • Fix Python syntax errors before any deploy.")
    if "requirements" in names:
        print("  • Run pip install -r requirements.txt on Render.")


if __name__ == "__main__":
    sys.exit(main())