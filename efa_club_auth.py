"""Authentication helpers — no Streamlit dependency."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from efa_club_persistence import load_member_sessions, save_member_sessions

SESSION_TTL_DAYS = 30
ADMIN_USERNAME = "Antonio Calderon"

MEMBER_CREDENTIALS = {
    "Antonio Calderon": {"email": "acal721@gmail.com", "password": "EFAIC2026001CA"},
    "Chris Koo": {"email": "Chris.b.koo@outlook.com", "password": "EFAIC2026002KC"},
    "Josh Tafoya": {"email": "Joshtafoya01@gmail.com", "password": "EFAIC2026003TJ"},
    "Jeff Gragert": {"email": "Jagragert@gmail.com", "password": "EFAIC2026004GJ"},
    "Nick Vigil": {"email": "Nbvigil24@hotmail.com", "password": "EFAIC2026005VN"},
    "Ray Gilkes": {"email": "Bison1867@gmail.com", "password": "EFAIC2026006GR"},
    "Jose Calderon": {"email": "Josecalderon036@gmail.com", "password": "EFAIC2026007CJ"},
    "Chad Speegle": {"email": "Chad.speegle@gmail.com", "password": "EFAIC2026008SC"},
    "Jadyn Tafoya": {"email": "Jadynty21@gmail.com", "password": "EFAIC2026009TJ"},
    "Matt Newbill": {"email": "Matthew.Newbill@gmail.com", "password": "EFAIC20260010NM"},
    "Mike Brooks": {"email": "Mikeb1120@gmail.com", "password": "EFAIC20260011BM"},
}


def is_admin(username):
    return username == ADMIN_USERNAME


def verify_password(username, password):
    cred = MEMBER_CREDENTIALS.get(username)
    return bool(cred and password == cred["password"])


def create_member_session(username):
    session_id = secrets.token_urlsafe(32)
    sessions = load_member_sessions()
    sessions[session_id] = {
        "username": username,
        "created": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
    }
    expired = [
        sid for sid, meta in sessions.items()
        if datetime.fromisoformat(meta.get("expires", "2000-01-01")) < datetime.now()
    ]
    for sid in expired:
        sessions.pop(sid, None)
    save_member_sessions(sessions)
    return session_id


def revoke_member_session(session_id):
    if not session_id:
        return
    sessions = load_member_sessions()
    if session_id in sessions:
        sessions.pop(session_id, None)
        save_member_sessions(sessions)


def resolve_session_user(session_id):
    """Return username if session_id is valid, else None."""
    if not session_id:
        return None
    sessions = load_member_sessions()
    meta = sessions.get(session_id)
    if not meta:
        return None
    try:
        if datetime.fromisoformat(meta.get("expires", "2000-01-01")) < datetime.now():
            revoke_member_session(session_id)
            return None
    except Exception:
        return None
    username = meta.get("username")
    if username not in MEMBER_CREDENTIALS:
        return None
    return username