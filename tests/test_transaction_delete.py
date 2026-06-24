"""Admin single-row transaction delete helpers."""
from __future__ import annotations

import pytest

from efa_club_services import delete_transaction_at, format_transaction_option_label


def test_format_transaction_option_label():
    txn = {
        "date": "2026-04-15",
        "type": "Club Buy",
        "ticker": "FSLR",
        "amount": -2750.0,
    }
    assert format_transaction_option_label(txn, 46) == (
        "#47 · 2026-04-15 · Club Buy · FSLR · $2,750.00"
    )


def test_delete_transaction_at_removes_one_row():
    txns = [
        {"date": "2026-01-01", "ticker": "SPY", "amount": -100},
        {"date": "2026-02-01", "ticker": "FSLR", "amount": -200},
        {"date": "2026-03-01", "ticker": "TSLA", "amount": -300},
    ]
    remaining, removed = delete_transaction_at(txns, 1)
    assert len(remaining) == 2
    assert removed["ticker"] == "FSLR"
    assert [t["ticker"] for t in remaining] == ["SPY", "TSLA"]
    assert len(txns) == 3


def test_delete_transaction_at_invalid_index():
    with pytest.raises(IndexError):
        delete_transaction_at([{"ticker": "A"}], 3)
    with pytest.raises(IndexError):
        delete_transaction_at([{"ticker": "A"}], -1)