"""Meeting notes, attachments, and access logging."""
from __future__ import annotations

import base64
from datetime import datetime

from efa_club_persistence import (
    get_last_supabase_error,
    load_access_log,
    load_analysis_history,
    load_availability_responses,
    load_finalized_meetings,
    load_meeting_attachment_store,
    load_polls,
    save_access_log,
    save_analysis_history,
    save_availability_responses,
    save_finalized_meetings,
    save_meeting_attachment_store,
    save_polls,
)

MAX_MEETING_ATTACHMENT_BYTES = 3 * 1024 * 1024


def log_site_access(username, action="visit"):
    if not username:
        return
    try:
        entries = load_access_log() or []
        entries.insert(0, {
            "username": username,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
        })
        save_access_log(entries[:500])
    except Exception as e:
        print(f"[access_log] {e}")


def _next_attachment_id(attachments):
    return max((a.get("id", 0) for a in (attachments or [])), default=0) + 1


def _build_attachment_entry(meeting_id, uploaded_file, username, raw, att_id):
    file_key = f"m{meeting_id}_a{att_id}"
    uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return file_key, {
        "meeting_id": meeting_id,
        "filename": uploaded_file.name,
        "uploaded_by": username,
        "uploaded_at": uploaded_at,
        "mime_type": uploaded_file.type or "application/octet-stream",
        "size": len(raw),
        "content_b64": base64.b64encode(raw).decode("ascii"),
    }, {
        "id": att_id,
        "file_key": file_key,
        "filename": uploaded_file.name,
        "uploaded_by": username,
        "uploaded_at": uploaded_at,
        "size": len(raw),
    }


def add_meeting_attachment(meeting, uploaded_file, username):
    if uploaded_file is None:
        return False, "No file selected."
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_MEETING_ATTACHMENT_BYTES:
        return False, f"File too large ({len(raw) // 1024} KB). Max is {MAX_MEETING_ATTACHMENT_BYTES // 1024} KB."
    meeting_id = meeting.get("id")
    if not meeting_id:
        return False, "Meeting is missing an id."
    store = load_meeting_attachment_store() or {}
    att_id = _next_attachment_id(meeting.get("attachments", []))
    file_key, store_entry, attachment_meta = _build_attachment_entry(
        meeting_id, uploaded_file, username, raw, att_id
    )
    store[file_key] = store_entry
    if not save_meeting_attachment_store(store):
        return False, get_last_supabase_error() or "Failed to save attachment."
    meeting.setdefault("attachments", []).append(attachment_meta)
    return True, ""


def persist_meeting_update(meeting_id, updater):
    """
    Reload meetings from storage, apply updater(meeting) -> (ok, message), then save.
    Returns (ok, message, refreshed_meetings_or_none).
    """
    if not meeting_id:
        return False, "Meeting is missing an id.", None

    meetings = load_finalized_meetings()
    meeting_idx = next((i for i, m in enumerate(meetings) if m.get("id") == meeting_id), None)
    if meeting_idx is None:
        return False, "Meeting not found.", None

    meeting = meetings[meeting_idx]
    ok, msg = updater(meeting)
    if not ok:
        return False, msg, None

    meetings[meeting_idx] = meeting
    if not save_finalized_meetings(meetings):
        return False, get_last_supabase_error() or "Failed to save meeting.", None

    return True, msg, load_finalized_meetings()


def persist_meeting_attachment(meeting_id, uploaded_file, username):
    """Save attachment bytes and meeting metadata from fresh persisted state."""
    if uploaded_file is None:
        return False, "No file selected.", None
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_MEETING_ATTACHMENT_BYTES:
        return False, f"File too large ({len(raw) // 1024} KB). Max is {MAX_MEETING_ATTACHMENT_BYTES // 1024} KB.", None
    if not meeting_id:
        return False, "Meeting is missing an id.", None

    meetings = load_finalized_meetings()
    meeting_idx = next((i for i, m in enumerate(meetings) if m.get("id") == meeting_id), None)
    if meeting_idx is None:
        return False, "Meeting not found.", None

    meeting = meetings[meeting_idx]
    store = load_meeting_attachment_store() or {}
    att_id = _next_attachment_id(meeting.get("attachments", []))
    file_key, store_entry, attachment_meta = _build_attachment_entry(
        meeting_id, uploaded_file, username, raw, att_id
    )
    store[file_key] = store_entry
    if not save_meeting_attachment_store(store):
        return False, get_last_supabase_error() or "Failed to save attachment.", None

    meeting.setdefault("attachments", []).append(attachment_meta)
    meetings[meeting_idx] = meeting
    if not save_finalized_meetings(meetings):
        return False, get_last_supabase_error() or "Failed to save meeting metadata.", None

    return True, "", load_finalized_meetings()


def _persist_collection(key_name, loader, saver, updater):
    """Generic reload-update-save for list or dict club_data keys."""
    default = {} if key_name == "availability" else []
    collection = loader() or default
    if key_name == "availability" and not isinstance(collection, dict):
        collection = {}
    if key_name != "availability" and not isinstance(collection, list):
        collection = list(collection) if collection else []
    ok, msg = updater(collection)
    if not ok:
        return False, msg, None
    if not saver(collection):
        return False, get_last_supabase_error() or f"Failed to save {key_name}.", None
    return True, msg, loader() or default


def persist_create_poll(week_start, week_end, times):
    week_start = str(week_start or "").strip()
    week_end = str(week_end or "").strip()
    times = list(times or [])
    if not week_start or not week_end:
        return False, "Poll dates are required.", None

    new_poll = {
        "id": 0,
        "week_start": week_start,
        "week_end": week_end,
        "times": times,
        "created": datetime.now().strftime("%Y-%m-%d"),
    }

    def updater(polls):
        new_poll["id"] = max((p.get("id", 0) for p in polls), default=0) + 1
        polls.append(new_poll)
        return True, "Poll created!"

    return _persist_collection("polls", load_polls, save_polls, updater)


def persist_member_availability(poll_key, username, selections):
    poll_key = str(poll_key)
    if not username:
        return False, "Not logged in.", None

    def updater(responses):
        if not isinstance(responses, dict):
            responses = {}
        responses.setdefault(poll_key, {})[username] = list(selections or [])
        return True, "Availability updated!"

    return _persist_collection(
        "availability",
        load_availability_responses,
        save_availability_responses,
        updater,
    )


def persist_create_meeting(date_str, time_str):
    date_str = str(date_str or "").strip()
    time_str = str(time_str or "").strip()
    if not date_str or not time_str:
        return False, "Meeting date and time are required.", None

    def updater(meetings):
        meetings.append({
            "id": max((m.get("id", 0) for m in meetings), default=0) + 1,
            "date": date_str,
            "time": time_str,
            "note_entries": [],
            "attachments": [],
            "votes": [],
        })
        return True, "Meeting set and saved!"

    return _persist_collection(
        "finalized_meetings",
        load_finalized_meetings,
        save_finalized_meetings,
        updater,
    )


def persist_cancel_meeting(meeting_id):
    meeting_id = int(meeting_id)

    def updater(meetings):
        before = len(meetings)
        kept = [m for m in meetings if m.get("id") != meeting_id]
        if len(kept) == before:
            return False, "Meeting not found."
        meetings.clear()
        meetings.extend(kept)
        return True, "Meeting cancelled and removed!"

    return _persist_collection(
        "finalized_meetings",
        load_finalized_meetings,
        save_finalized_meetings,
        updater,
    )


def persist_add_meeting_note(meeting_id, author, text):
    text = str(text or "").strip()
    if not text:
        return False, "Note cannot be empty.", None
    if not author:
        return False, "Not logged in.", None

    def updater(meeting):
        notes = meeting.setdefault("note_entries", [])
        next_id = max((n.get("id", 0) for n in notes), default=0) + 1
        notes.append({
            "id": next_id,
            "author": author,
            "text": text,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        return True, "Note added!"

    return persist_meeting_update(meeting_id, updater)


def persist_update_meeting_note(meeting_id, note_id, new_text, username, is_admin):
    new_text = str(new_text or "").strip()
    if not new_text:
        return False, "Note cannot be empty.", None

    def updater(meeting):
        from efa_club_services import can_edit_note

        for note in meeting.get("note_entries", []):
            if note.get("id") == note_id:
                if not can_edit_note(note, username, is_admin):
                    return False, "You may not edit this note."
                note["text"] = new_text
                note["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                return True, "Note updated!"
        return False, "Note not found."

    return persist_meeting_update(meeting_id, updater)


def persist_delete_meeting_note(meeting_id, note_id, username, is_admin):
    def updater(meeting):
        from efa_club_services import can_edit_note

        notes = meeting.get("note_entries", [])
        for idx, note in enumerate(notes):
            if note.get("id") == note_id:
                if not can_edit_note(note, username, is_admin):
                    return False, "You may not delete this note."
                notes.pop(idx)
                return True, "Note deleted."
        return False, "Note not found."

    return persist_meeting_update(meeting_id, updater)


def persist_analysis_batch(run_type, results):
    history = load_analysis_history() or []
    history.insert(0, {
        "type": run_type,
        "results": list(results or []),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    if not save_analysis_history(history):
        return False, get_last_supabase_error() or "Failed to save analysis history.", None
    return True, "", load_analysis_history()


def get_attachment_download(file_key):
    store = load_meeting_attachment_store() or {}
    entry = store.get(file_key)
    if not entry:
        return None, None, None
    try:
        data = base64.b64decode(entry["content_b64"])
        return data, entry.get("filename", "download"), entry.get("mime_type", "application/octet-stream")
    except Exception:
        return None, None, None