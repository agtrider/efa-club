"""Meeting vote persistence tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efa_club_persistence as persist
from efa_club_services import persist_member_vote, persist_create_vote


@pytest.fixture(autouse=True)
def reset_supabase_error():
    persist._LAST_SUPABASE_ERROR = ""
    yield


def _seed_meeting(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    meeting = {
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "note_entries": [],
        "attachments": [],
        "votes": [],
    }
    persist.save_finalized_meetings([meeting])
    return meeting


def test_persist_member_vote_round_trip(tmp_path, monkeypatch):
    _seed_meeting(tmp_path, monkeypatch)
    with patch.object(persist, "supabase", None):
        ok, msg, created = persist_create_vote(1, "Buy PLTR?")
    assert ok is True, msg
    assert created is not None

    vote_id = created[0]["votes"][0]["id"]
    with patch.object(persist, "supabase", None):
        ok, msg, refreshed = persist_member_vote(1, vote_id, "Jadyn Tafoya", "Yes")

    assert ok is True, msg
    assert refreshed is not None
    ballot = refreshed[0]["votes"][0]["votes"]
    assert ballot.get("Jadyn Tafoya") == "Yes"

    reloaded = persist.load_finalized_meetings()
    assert reloaded[0]["votes"][0]["votes"].get("Jadyn Tafoya") == "Yes"


def test_persist_member_vote_reports_save_failure(tmp_path, monkeypatch):
    _seed_meeting(tmp_path, monkeypatch)
    with patch.object(persist, "supabase", None):
        ok, _, created = persist_create_vote(1, "Buy PLTR?")
    vote_id = created[0]["votes"][0]["id"]

    with patch("efa_club_meetings.save_finalized_meetings", return_value=False):
        ok, err, refreshed = persist_member_vote(1, vote_id, "Jadyn Tafoya", "Yes")

    assert ok is False
    assert refreshed is None
    assert err