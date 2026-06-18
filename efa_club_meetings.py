"""Meeting notes, attachments, and access logging."""
from __future__ import annotations

import base64
from datetime import datetime

from efa_club_persistence import (
    get_last_supabase_error,
    load_access_log,
    load_finalized_meetings,
    load_meeting_attachment_store,
    save_access_log,
    save_finalized_meetings,
    save_meeting_attachment_store,
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