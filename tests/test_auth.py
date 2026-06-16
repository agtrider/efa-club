"""Auth module tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from efa_club_auth import (
    create_member_session,
    is_admin,
    resolve_session_user,
    revoke_member_session,
    verify_password,
)


def test_verify_password():
    assert verify_password("Chris Koo", "EFAIC2026002KC") is True
    assert verify_password("Chris Koo", "wrong") is False


def test_is_admin():
    assert is_admin("Antonio Calderon") is True
    assert is_admin("Chris Koo") is False


def test_session_create_resolve_revoke():
    store = {}

    def _save(sessions):
        store.clear()
        store.update(sessions)
        return True

    with patch("efa_club_auth.load_member_sessions", side_effect=lambda: dict(store)):
        with patch("efa_club_auth.save_member_sessions", side_effect=_save):
            sid = create_member_session("Chris Koo")
            assert resolve_session_user(sid) == "Chris Koo"
            revoke_member_session(sid)
            assert resolve_session_user(sid) is None