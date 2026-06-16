"""Meeting notes, attachments, and access logging."""
from __future__ import annotations

import base64
from datetime import datetime

from efa_club_persistence import (
    get_last_supabase_error,
    load_access_log,
    load_meeting_attachment_store,
    save_access_log,
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
    att_id = len(meeting.get("attachments", [])) + 1
    file_key = f"m{meeting_id}_a{att_id}"
    store[file_key] = {
        "meeting_id": meeting_id,
        "filename": uploaded_file.name,
        "uploaded_by": username,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mime_type": uploaded_file.type or "application/octet-stream",
        "size": len(raw),
        "content_b64": base64.b64encode(raw).decode("ascii"),
    }
    if not save_meeting_attachment_store(store):
        return False, get_last_supabase_error() or "Failed to save attachment."
    meeting.setdefault("attachments", []).append({
        "id": att_id,
        "file_key": file_key,
        "filename": uploaded_file.name,
        "uploaded_by": username,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "size": len(raw),
    })
    return True, ""


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