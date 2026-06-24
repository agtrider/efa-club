"""Concurrent meeting vote ballot merge."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efa_club_persistence as persist
from efa_club_services import (
    merge_meeting_vote_ballots,
    persist_member_vote,
    persist_create_vote,
)


def _meeting_with_ballot(ballot):
    return {
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "note_entries": [],
        "attachments": [],
        "votes": [{
            "id": 1,
            "question": "Buy PLTR?",
            "votes": ballot,
            "created": "2026-06-01 19:00",
        }],
    }


def test_merge_combines_concurrent_ballots():
    fresh = _meeting_with_ballot({"Antonio Calderon": "Yes"})
    updated = _meeting_with_ballot({"Chris Koo": "Yes"})
    merged = merge_meeting_vote_ballots(fresh, updated)
    ballot = merged["votes"][0]["votes"]
    assert ballot["Antonio Calderon"] == "Yes"
    assert ballot["Chris Koo"] == "Yes"


def test_merge_patch_overrides_same_member():
    fresh = _meeting_with_ballot({"Chris Koo": "No"})
    updated = _meeting_with_ballot({"Chris Koo": "Yes"})
    merged = merge_meeting_vote_ballots(fresh, updated)
    assert merged["votes"][0]["votes"]["Chris Koo"] == "Yes"


def test_sequential_member_votes_persist_both(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    persist.save_finalized_meetings([{
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "note_entries": [],
        "attachments": [],
        "votes": [],
    }])

    with patch.object(persist, "supabase", None):
        ok, _, created = persist_create_vote(1, "Buy PLTR?")
        assert ok
        vote_id = created[0]["votes"][0]["id"]

        ok, _, _ = persist_member_vote(1, vote_id, "Antonio Calderon", "Yes")
        assert ok
        ok, _, refreshed = persist_member_vote(1, vote_id, "Chris Koo", "Yes")
        assert ok

    ballot = refreshed[0]["votes"][0]["votes"]
    assert ballot["Antonio Calderon"] == "Yes"
    assert ballot["Chris Koo"] == "Yes"


def test_second_voter_keeps_first_ballot_when_fresh_has_it(tmp_path, monkeypatch):
    """When fresh read already includes prior votes, merge keeps everyone."""
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    persist.save_finalized_meetings([_meeting_with_ballot({"Antonio Calderon": "Yes"})])

    with patch.object(persist, "supabase", None):
        ok, msg, refreshed = persist_member_vote(1, 1, "Chris Koo", "Yes")

    assert ok, msg
    ballot = refreshed[0]["votes"][0]["votes"]
    assert ballot["Antonio Calderon"] == "Yes"
    assert ballot["Chris Koo"] == "Yes"