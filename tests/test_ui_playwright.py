"""
Streamlit UI smoke tests using AppTest (no browser — reliable in GitHub Actions).

Playwright was replaced because Streamlit tab/login selectors are brittle in headless CI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.ci_fixtures import seed_ci_fixtures

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "efa_club_app.py"
TEST_USER = os.environ.get("EFA_TEST_USER", "Antonio Calderon")
TEST_PASSWORD = os.environ.get("EFA_TEST_PASSWORD", "EFAIC2026001CA")
DEFAULT_SELECTBOX_USER = "Antonio Calderon"

pytestmark = pytest.mark.ui


def _ci_env():
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
    os.environ["GROK_API_KEY"] = ""
    os.environ["FINNHUB_API_KEY"] = ""
    os.environ["EFA_CI_MODE"] = "1"


@pytest.fixture(scope="module")
def logged_in_app():
    seed_ci_fixtures()
    _ci_env()
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run(timeout=120)
    assert any("Member Login" in s.value for s in at.subheader), "login page not shown"

    if TEST_USER != DEFAULT_SELECTBOX_USER:
        at.selectbox[0].set_value(TEST_USER).run()

    password = next(t for t in at.text_input if (t.label or "") == "Password")
    password.set_value(TEST_PASSWORD).run()
    login_btn = next(b for b in at.button if b.label == "Login")
    login_btn.click().run()

    titles = [t.value for t in at.title]
    assert any(TEST_USER in t for t in titles), f"login failed; titles={titles}"
    return at


def test_login_shows_welcome(logged_in_app):
    assert any(TEST_USER in t.value for t in logged_in_app.title)


def test_tab6_fundamentals_section_loads(logged_in_app):
    at = logged_in_app
    tab6 = next((t for t in at.tabs if "Advanced Technical" in t.label), None)
    assert tab6 is not None, f"tab6 missing; tabs={[t.label for t in at.tabs]}"

    markdown_text = " ".join(m.value for m in at.markdown if m.value)
    assert "Fundamentals" in markdown_text

    load_btn = next((b for b in at.button if "Load Fundamentals" in (b.label or "")), None)
    assert load_btn is not None, f"Load Fundamentals button missing; buttons={[b.label for b in at.button]}"
    load_btn.click().run()

    assert "FSLR" in markdown_text or any(
        "FSLR" in str(df.value) for df in at.dataframe if getattr(df, "value", None) is not None
    )


def test_scheduler_tab_loads(logged_in_app):
    at = logged_in_app
    scheduler = next((t for t in at.tabs if "Meeting Scheduler" in t.label), None)
    assert scheduler is not None

    subheaders = [s.value for s in at.subheader]
    assert any("Meeting Scheduler" in s for s in subheaders)

    markdown_text = " ".join(m.value for m in at.markdown if m.value)
    assert "Finalize" in markdown_text or "Availability" in markdown_text