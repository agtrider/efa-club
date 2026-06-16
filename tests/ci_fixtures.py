"""Seed local_data from committed fixtures — used by CI and Playwright smoke tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LOCAL_DATA = ROOT / "local_data"


def seed_ci_fixtures() -> None:
    LOCAL_DATA.mkdir(exist_ok=True)
    src = FIXTURES / "watchlist.json"
    dst = LOCAL_DATA / "watchlist.json"
    if src.exists():
        shutil.copy2(src, dst)