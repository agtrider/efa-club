"""Meeting attachment persistence tests."""
from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efa_club_meetings as meetings
import efa_club_persistence as persist


class FakeUploadedFile:
    def __init__(self, name, data, mime_type="text/plain"):
        self.name = name
        self.type = mime_type
        self._data = data

    def getvalue(self):
        return self._data


@pytest.fixture(autouse=True)
def reset_supabase_error():
    persist._LAST_SUPABASE_ERROR = ""
    yield


def test_load_finalized_meetings_falls_back_to_local_json(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    local_meetings = [{
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "attachments": [{"id": 1, "file_key": "m1_a1", "filename": "notes.txt"}],
    }]
    persist.save_json("finalized_meetings.json", local_meetings)

    with patch.object(persist, "supabase", None):
        loaded = persist.load_finalized_meetings()

    assert len(loaded) == 1
    assert loaded[0]["attachments"][0]["filename"] == "notes.txt"


def test_load_meeting_attachment_store_falls_back_to_local_json(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    store = {
        "m1_a1": {
            "meeting_id": 1,
            "filename": "notes.txt",
            "content_b64": base64.b64encode(b"hello").decode("ascii"),
        }
    }
    persist.save_json("meeting_attachment_store.json", store)

    with patch.object(persist, "supabase", None):
        loaded = persist.load_meeting_attachment_store()

    assert loaded["m1_a1"]["filename"] == "notes.txt"


def test_save_meeting_attachment_store_writes_local_json(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    with patch.object(persist, "supabase", None):
        ok = persist.save_meeting_attachment_store({"m1_a1": {"filename": "a.txt"}})
    assert ok is True
    assert (tmp_path / "meeting_attachment_store.json").exists()


def test_persist_meeting_attachment_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    seed = [{
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "note_entries": [],
        "attachments": [],
        "votes": [],
    }]
    persist.save_finalized_meetings(seed)

    uploaded = FakeUploadedFile("minutes.txt", b"Meeting transcript")
    with patch.object(persist, "supabase", None):
        ok, err, refreshed = meetings.persist_meeting_attachment(1, uploaded, "admin")

    assert ok is True, err
    assert refreshed is not None
    assert len(refreshed[0]["attachments"]) == 1
    assert refreshed[0]["attachments"][0]["filename"] == "minutes.txt"

    reloaded_meetings = persist.load_finalized_meetings()
    reloaded_store = persist.load_meeting_attachment_store()
    assert len(reloaded_meetings[0]["attachments"]) == 1
    file_key = reloaded_meetings[0]["attachments"][0]["file_key"]
    assert file_key in reloaded_store

    data, filename, _ = meetings.get_attachment_download(file_key)
    assert data == b"Meeting transcript"
    assert filename == "minutes.txt"


def test_persist_meeting_attachment_rolls_back_metadata_when_meeting_save_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path)
    persist.save_finalized_meetings([{
        "id": 1,
        "date": "2026-06-01",
        "time": "7:30 PM CST",
        "attachments": [],
    }])

    uploaded = FakeUploadedFile("minutes.txt", b"Meeting transcript")

    with patch.object(meetings, "save_meeting_attachment_store", return_value=True):
        with patch.object(meetings, "save_finalized_meetings", return_value=False):
            ok, err, refreshed = meetings.persist_meeting_attachment(1, uploaded, "admin")

    assert ok is False
    assert refreshed is None
    assert "metadata" in err.lower()