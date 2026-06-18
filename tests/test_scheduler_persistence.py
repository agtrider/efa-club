"""Meeting scheduler poll/availability persistence tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efa_club_meetings as meetings
import efa_club_persistence as persist


@pytest.fixture(autouse=True)
def reset_supabase_error():
    persist._LAST_SUPABASE_ERROR = ""
    yield


def test_persist_create_poll_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    with patch.object(persist, "supabase", None):
        ok, msg, polls = meetings.persist_create_poll("2026-06-10", "2026-06-16", ["7:30 PM CST"])
    assert ok is True, msg
    assert polls and polls[0]["week_start"] == "2026-06-10"


def test_persist_member_availability_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    with patch.object(persist, "supabase", None):
        ok, _, polls = meetings.persist_create_poll("2026-06-10", "2026-06-16", ["7:30 PM CST"])
    poll_key = str(polls[0]["id"])
    with patch.object(persist, "supabase", None):
        ok, msg, responses = meetings.persist_member_availability(
            poll_key, "Jadyn Tafoya", ["2026-06-10 7:30 PM CST"]
        )
    assert ok is True, msg
    assert responses[poll_key]["Jadyn Tafoya"] == ["2026-06-10 7:30 PM CST"]