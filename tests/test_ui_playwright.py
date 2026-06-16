"""
Playwright UI smoke tests for Streamlit app.
Starts streamlit in a subprocess, verifies login and key UI elements.
Skip locally with: EFA_SKIP_UI_TESTS=1
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.ci_fixtures import seed_ci_fixtures

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "efa_club_app.py"
BASE_URL = os.environ.get("EFA_TEST_URL", "http://127.0.0.1:8501")
TEST_USER = os.environ.get("EFA_TEST_USER", "Antonio Calderon")
TEST_PASSWORD = os.environ.get("EFA_TEST_PASSWORD", "EFAIC2026001CA")
DEFAULT_SELECTBOX_USER = "Antonio Calderon"
STARTUP_TIMEOUT_S = 90
TAB_LOAD_TIMEOUT_MS = 60_000

pytestmark = pytest.mark.ui


def _streamlit_env():
    return {
        **os.environ,
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "GROK_API_KEY": "",
        "FINNHUB_API_KEY": "",
        "EFA_CI_MODE": "1",
    }


@pytest.fixture(scope="module")
def streamlit_server():
    if os.environ.get("EFA_SKIP_UI_TESTS") == "1":
        pytest.skip("UI tests skipped (EFA_SKIP_UI_TESTS=1)")

    seed_ci_fixtures()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(APP),
            "--server.headless", "true",
            "--server.port", "8501",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_streamlit_env(),
    )
    deadline = time.time() + STARTUP_TIMEOUT_S
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(BASE_URL, timeout=2)
            break
        except Exception:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                pytest.fail(f"Streamlit failed to start.\nstdout:\n{out}\nstderr:\n{err}")
            time.sleep(1)
    else:
        proc.terminate()
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        pytest.fail(f"Streamlit server did not become ready in {STARTUP_TIMEOUT_S}s.\nstderr:\n{err}")
    yield BASE_URL
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser_page(streamlit_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(30000)
        yield page
        browser.close()


def _select_member(page, username):
    """Streamlit selectbox defaults to first member — must pick the test user."""
    select = page.locator('[data-testid="stSelectbox"]').first
    select.click()
    page.locator('[data-baseweb="popover"]').get_by_text(username, exact=True).click()


def _click_tab(page, label_pattern):
    """Streamlit tabs are buttons, not always exposed as role=tab."""
    tab = page.get_by_role("tab", name=label_pattern)
    if tab.count() > 0:
        tab.first.click()
        return
    page.locator('[data-baseweb="tab"]').filter(has_text=label_pattern).first.click()


def _login(page, base_url):
    page.goto(base_url, wait_until="domcontentloaded")
    page.get_by_text("Member Login").wait_for()
    if TEST_USER != DEFAULT_SELECTBOX_USER:
        _select_member(page, TEST_USER)
    page.locator('input[type="password"]').first.fill(TEST_PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.get_by_text(re.compile(rf"Welcome,\s*{re.escape(TEST_USER)}")).wait_for(timeout=45000)


def test_login_shows_welcome(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)


def test_tab6_fundamentals_section_loads(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)
    _click_tab(browser_page, re.compile(r"Advanced Technical", re.I))
    browser_page.get_by_text("Advanced Technical Analysis", exact=False).wait_for(timeout=30000)
    browser_page.get_by_text("Fundamentals & Technicals").wait_for(timeout=TAB_LOAD_TIMEOUT_MS)
    content = browser_page.content()
    assert "Watchlist" in content or "Portfolio Holdings" in content
    assert "FSLR" in content
    assert "Ticker" in content


def test_scheduler_tab_loads(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)
    _click_tab(browser_page, re.compile(r"Meeting Scheduler", re.I))
    browser_page.get_by_text("Scheduled Meetings").wait_for(timeout=30000)