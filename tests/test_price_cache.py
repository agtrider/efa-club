"""Cache-first price logic — no Streamlit, no live network."""
from __future__ import annotations

from datetime import datetime, timedelta

from efa_club_services import (
    PRICE_INTRADAY_TTL_MINUTES,
    acceptable_cached_price,
    cache_fresh_enough,
    parse_price_meta_timestamp,
)


def test_parse_price_meta_timestamp():
    assert parse_price_meta_timestamp("2026-06-24 10:30") == datetime(2026, 6, 24, 10, 30)
    assert parse_price_meta_timestamp("2026-06-24") == datetime(2026, 6, 24)
    assert parse_price_meta_timestamp("") is None


def test_acceptable_cached_price_rejects_csv_fill():
    meta = {"price": 250.0, "source": "csv_fill", "as_of": "2026-06-24"}
    assert acceptable_cached_price(
        meta, "open", today="2026-06-24", target_eod="2026-06-23", prior_eod="2026-06-20"
    ) == 0.0


def test_acceptable_cached_price_intraday_during_open():
    meta = {"price": 271.5, "source": "intraday", "as_of": "2026-06-24"}
    assert acceptable_cached_price(
        meta, "open", today="2026-06-24", target_eod="2026-06-24", prior_eod="2026-06-23"
    ) == 271.5


def test_acceptable_cached_price_prior_eod_fallback_when_open():
    meta = {"price": 265.0, "source": "eod_close", "as_of": "2026-06-23"}
    assert acceptable_cached_price(
        meta, "open", today="2026-06-24", target_eod="2026-06-24", prior_eod="2026-06-23"
    ) == 265.0


def test_acceptable_cached_price_eod_after_close():
    meta = {"price": 268.0, "source": "eod_close", "as_of": "2026-06-24"}
    assert acceptable_cached_price(
        meta, "afterhours", today="2026-06-24", target_eod="2026-06-24", prior_eod="2026-06-23"
    ) == 268.0


def test_cache_fresh_enough_intraday_within_ttl():
    recent = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    meta = {
        "price": 270.0,
        "source": "intraday",
        "as_of": "2026-06-24",
        "timestamp": recent + " (yahoo chart live)",
    }
    assert cache_fresh_enough(
        meta,
        "open",
        force_live=False,
        today="2026-06-24",
        target_eod="2026-06-24",
        prior_eod="2026-06-23",
    )


def test_cache_fresh_enough_intraday_expired():
    old = "2020-01-02 09:45"
    meta = {
        "price": 270.0,
        "source": "intraday",
        "as_of": "2026-06-24",
        "timestamp": old + " (yahoo chart live)",
    }
    assert not cache_fresh_enough(
        meta,
        "open",
        force_live=False,
        today="2026-06-24",
        target_eod="2026-06-24",
        prior_eod="2026-06-23",
    )


def test_cache_fresh_enough_force_live_bypasses():
    meta = {"price": 270.0, "source": "intraday", "as_of": "2026-06-24", "timestamp": "2026-06-24 10:00"}
    assert not cache_fresh_enough(
        meta,
        "open",
        force_live=True,
        today="2026-06-24",
        target_eod="2026-06-24",
        prior_eod="2026-06-23",
    )


def test_cache_fresh_enough_eod_closed_session():
    meta = {"price": 268.0, "source": "eod_close", "as_of": "2026-06-24", "timestamp": "2026-06-24 16:05"}
    assert cache_fresh_enough(
        meta,
        "afterhours",
        force_live=False,
        today="2026-06-24",
        target_eod="2026-06-24",
        prior_eod="2026-06-23",
    )