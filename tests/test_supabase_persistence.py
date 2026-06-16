"""Supabase persistence tests with mocks — no live database required."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efa_club_persistence as persist


@pytest.fixture(autouse=True)
def reset_supabase_error():
    persist._LAST_SUPABASE_ERROR = ""
    yield


def test_load_from_supabase_returns_default_when_disconnected():
    with patch.object(persist, "supabase", None):
        assert persist.load_from_supabase("watchlist", []) == []


def test_save_to_supabase_fails_when_disconnected():
    with patch.object(persist, "supabase", None):
        assert persist.save_to_supabase("watchlist", ["TSLA"]) is False
        assert "not connected" in persist.get_last_supabase_error().lower()


def test_save_to_supabase_read_modify_write():
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"data": {"watchlist": ["OLD"], "members": []}}]
    )
    mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{"id": 1}])

    with patch.object(persist, "supabase", mock_client):
        ok = persist.save_to_supabase("watchlist", ["FSLR", "TSLA"])
        assert ok is True
        upsert_arg = mock_table.upsert.call_args[0][0]
        assert upsert_arg["data"]["watchlist"] == ["FSLR", "TSLA"]
        assert upsert_arg["data"]["members"] == []


def test_save_to_supabase_missing_row():
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    with patch.object(persist, "supabase", mock_client):
        assert persist.save_to_supabase("watchlist", []) is False
        assert "missing" in persist.get_last_supabase_error().lower()


def test_save_finalized_meetings_writes_local_json(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    monkeypatch.setattr(persist, "save_to_supabase", lambda k, v: True)
    meetings = [{"id": 1, "date": "2026-06-01", "time": "7:30 PM CST", "votes": []}]
    assert persist.save_finalized_meetings(meetings) is True
    assert (tmp_path / "finalized_meetings.json").exists()