"""
Playwright UI smoke tests for Streamlit app.
Starts streamlit in a subprocess, verifies login and key UI elements.
Skip locally with: pytest tests/test_ui_playwright.py -m "not ui"
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "efa_club_app.py"
BASE_URL = os.environ.get("EFA_TEST_URL", "http://127.0.0.1:8501")
TEST_PASSWORD = os.environ.get("EFA_TEST_PASSWORD", "EFAIC2026002KC")
TEST_USER = "Chris Koo"

pytestmark = pytest.mark.ui


@pytest.fixture(scope="module")
def streamlit_server():
    if os.environ.get("EFA_SKIP_UI_TESTS") == "1":
        pytest.skip("UI tests skipped (EFA_SKIP_UI_TESTS=1)")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(APP),
            "--server.headless", "true",
            "--server.port", "8501",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env={**os.environ, "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""},
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(BASE_URL, timeout=2)
            break
        except Exception:
            if proc.poll() is not None:
                err = proc.stderr.read().decode() if proc.stderr else ""
                pytest.fail(f"Streamlit failed to start: {err}")
            time.sleep(1)
    else:
        proc.terminate()
        pytest.fail("Streamlit server did not become ready in 45s")
    yield BASE_URL
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser_page(streamlit_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)
        yield page
        browser.close()


def _login(page, base_url):
    page.goto(base_url)
    page.get_by_text("Member Login").wait_for()
    page.get_by_label("Password").fill(TEST_PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.get_by_text(f"Welcome, {TEST_USER}").wait_for(timeout=15000)


def test_login_shows_welcome(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)


def test_tab6_fundamentals_not_all_na(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)
    browser_page.get_by_text("Advanced Technical Analysis", exact=False).click()
    browser_page.get_by_text("Fundamentals & Technicals", exact=False).wait_for()
    content = browser_page.content()
    assert "Portfolio Holdings" in content or "Watchlist" in content
    assert content.count("N/A") < content.count("Ticker") * 5


def test_scheduler_tab_loads(browser_page, streamlit_server):
    _login(browser_page, streamlit_server)
    browser_page.get_by_text("Meeting Scheduler", exact=False).click()
    browser_page.get_by_text("Scheduled Meetings", exact=False).wait_for()