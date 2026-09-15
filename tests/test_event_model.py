"""Unit tests for the canonical event-model module."""

from __future__ import annotations

import pandas as pd
import pytest

from red2400_toolkit.event_model import (
    EventLinkageError,
    LEGACY_MINT_POOLED_MODE,
    MODE_EVENT,
    MODE_FIRST_EVENT_PER_MINT,
    MODE_LATEST_EVENT_PER_MINT,
    MODE_MINT_SUMMARY,
    VALID_MODES,
    attach_event_ids,
    attach_outcomes_by_event,
    compute_event_id,
    compute_sample_id,
    normalize_reason,
    parse_timestamp_to_ms,
    select_rejections_by_mode,
)


# ---------- parse_timestamp_to_ms ----------

def test_parse_iso_with_z_suffix():
    # 2026-04-10T21:10:13Z = epoch ms 1_775_855_413_000
    assert parse_timestamp_to_ms("2026-04-10T21:10:13.000Z") == 1_775_855_413_000


def test_parse_iso_with_offset():
    # +00:00 explicit
    assert parse_timestamp_to_ms("2026-04-10T21:10:13.000+00:00") == 1_775_855_413_000


def test_parse_iso_sub_millisecond_truncates():
    # 2026-04-10T21:10:13.123456Z -> 123 ms (truncate not round)
    assert parse_timestamp_to_ms("2026-04-10T21:10:13.123456Z") == 1_775_855_413_123
    assert parse_timestamp_to_ms("2026-04-10T21:10:13.123999Z") == 1_775_855_413_123


def test_parse_int_passthrough():
    assert parse_timestamp_to_ms(1_775_855_413_000) == 1_775_855_413_000


def test_parse_none_and_empty_and_nan():
    assert parse_timestamp_to_ms(None) is None
    assert parse_timestamp_to_ms("") is None
    assert parse_timestamp_to_ms(float("nan")) is None


def test_parse_naive_timestamp_raises():
    with pytest.raises(ValueError, match="naive"):
        parse_timestamp_to_ms("2026-04-10T21:10:13.000")


def test_parse_junk_string_raises():
    with pytest.raises(ValueError):
        parse_timestamp_to_ms("not a timestamp")


def test_parse_offset_normalizes_to_utc():
    # 2026-04-10T21:10:13+02:00 == 2026-04-10T19:10:13Z
    a = parse_timestamp_to_ms("2026-04-10T21:10:13.000+02:00")
    b = parse_timestamp_to_ms("2026-04-10T19:10:13.000Z")
    assert a == b


# ---------- normalize_reason ----------

def test_normalize_reason_strips_whitespace_preserves_case():
    assert normalize_reason("  Filter_1  ") == "Filter_1"


def test_normalize_reason_none_and_nan():
    assert normalize_reason(None) is None
    assert normalize_reason(float("nan")) is None
    assert normalize_reason("") is None
    assert normalize_reason("   ") is None


# ---------- compute_event_id ----------

def test_event_id_is_deterministic():
    a = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    b = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    assert a == b


def test_event_id_differs_across_reason():
    a = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    b = compute_event_id("M1", 1_775_855_413_000, "filter_2")
    assert a != b


def test_event_id_differs_across_time():
    a = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    b = compute_event_id("M1", 1_775_855_413_001, "filter_1")
    assert a != b


def test_event_id_differs_across_mint():
    a = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    b = compute_event_id("M2", 1_775_855_413_000, "filter_1")
    assert a != b


def test_event_id_is_16_hex_chars():
    e = compute_event_id("M1", 1_775_855_413_000, "filter_1")
    assert len(e) == 16
    assert all(c in "0123456789abcdef" for c in e)


def test_event_id_matches_p11_spec_frozen_vector():
    # Regression vector: if this changes, the P11 spec has drifted.
    # This is NOT a spec value published in P11 — it is a snapshot of the
    # correct sha256 truncation applied to (mint="M1", ts=1_775_855_413_000,
    # reason="filter_1"). Any change here breaks the P5-P11 event key.
    expected = "7fd9821012f8a82a"
    assert compute_event_id("M1", 1_775_855_413_000, "filter_1") == expected


def test_event_id_rejects_none_inputs():
    with pytest.raises(ValueError):
        compute_event_id(None, 1, "r")
    with pytest.raises(ValueError):
        compute_event_id("m", None, "r")
    with pytest.raises(ValueError):
        compute_event_id("m", 1, None)


# ---------- compute_sample_id ----------

def test_sample_id_dex_and_pair_null_stringified():
    eid = "abcdefabcdefabcd"
    a = compute_sample_id(eid, 1_775_855_413_000, None, None)
    # replacing None with "null" should give the same id
    b = compute_sample_id(eid, 1_775_855_413_000, "null", "null")
    assert a == b


def test_sample_id_changes_with_dex():
    eid = "abcdefabcdefabcd"
    a = compute_sample_id(eid, 1_775_855_413_000, "pumpswap", "P")
    b = compute_sample_id(eid, 1_775_855_413_000, "raydium", "P")
    assert a != b


# ---------- attach_event_ids ----------

def test_attach_event_ids_populates_columns():
    df = pd.DataFrame({
        "mint": ["M1", "M2"],
        "timestamp": ["2026-04-10T21:10:13.000Z", "2026-04-10T22:10:13.000Z"],
        "reason": ["filter_1", "filter_2"],
    })
    out = attach_event_ids(df, mint_col="mint", ts_col="timestamp", reason_col="reason")
    assert "event_id" in out.columns
    assert "rejectTs_utc_ms" in out.columns
    assert out["event_id"].notna().all()
    # Deterministic
    assert out.loc[0, "event_id"] == compute_event_id("M1", 1_775_855_413_000, "filter_1")


def test_attach_event_ids_raise_on_bad_ts():
    df = pd.DataFrame({
        "mint": ["M1"],
        "timestamp": ["not a timestamp"],
        "reason": ["filter_1"],
    })
    with pytest.raises(ValueError):
        attach_event_ids(df, mint_col="mint", ts_col="timestamp", reason_col="reason")


def test_attach_event_ids_quarantine_on_bad_ts():
    df = pd.DataFrame({
        "mint": ["M1", "M2"],
        "timestamp": ["not a timestamp", "2026-04-10T22:10:13.000Z"],
        "reason": ["filter_1", "filter_2"],
    })
    out = attach_event_ids(
        df, mint_col="mint", ts_col="timestamp", reason_col="reason",
        on_error="quarantine",
    )
    assert out.loc[0, "event_id"] is None
    assert out.loc[1, "event_id"] is not None
    assert "quarantine_reason" in out.columns


# ---------- attach_outcomes_by_event ----------

def test_attach_outcomes_by_event_hard_fail_on_orphan():
    rej = pd.DataFrame({
        "event_id": ["abc", "def"],
        "mint": ["M1", "M2"],
    })
    out = pd.DataFrame({
        "event_id": ["abc", "abc"],
    })
    with pytest.raises(EventLinkageError):
        attach_outcomes_by_event(rej, out, on_missing="raise")


def test_attach_outcomes_by_event_quarantine():
    rej = pd.DataFrame({
        "event_id": ["abc", "def"],
        "mint": ["M1", "M2"],
    })
    out = pd.DataFrame({"event_id": ["abc", "abc"]})
    by_event, diag = attach_outcomes_by_event(
        rej, out, on_missing="quarantine", warn_on_orphans=False,
    )
    assert list(by_event.keys()) == ["abc"]
    assert diag.n_orphan_rejections == 1
    assert diag.n_events_with_outcomes == 1


def test_attach_outcomes_by_event_requires_event_id_column():
    rej = pd.DataFrame({"mint": ["M1"]})
    out = pd.DataFrame({"event_id": ["abc"]})
    with pytest.raises(KeyError, match="event_id"):
        attach_outcomes_by_event(rej, out)


# ---------- select_rejections_by_mode ----------

def _mode_frame():
    return pd.DataFrame({
        "mint":            ["A", "A", "B", "C"],
        "event_id":        ["e1", "e2", "e3", "e4"],
        "rejectTs_utc_ms": [100,  200,  50,   999],
        "reason":          ["f", "g", "h", "i"],
    })


def test_mode_event_returns_all_rows():
    df = _mode_frame()
    out = select_rejections_by_mode(df, MODE_EVENT)
    assert len(out) == 4


def test_mode_first_event_per_mint():
    df = _mode_frame()
    out = select_rejections_by_mode(df, MODE_FIRST_EVENT_PER_MINT)
    # A: earliest is ts=100 (e1); B: ts=50 (e3); C: ts=999 (e4)
    assert set(out["event_id"]) == {"e1", "e3", "e4"}


def test_mode_latest_event_per_mint():
    df = _mode_frame()
    out = select_rejections_by_mode(df, MODE_LATEST_EVENT_PER_MINT)
    # A: latest is ts=200 (e2)
    assert set(out["event_id"]) == {"e2", "e3", "e4"}


def test_mode_mint_summary_matches_first():
    df = _mode_frame()
    a = select_rejections_by_mode(df, MODE_MINT_SUMMARY)
    b = select_rejections_by_mode(df, MODE_FIRST_EVENT_PER_MINT)
    assert set(a["event_id"]) == set(b["event_id"])


def test_mode_legacy_is_a_valid_mode():
    assert LEGACY_MINT_POOLED_MODE in VALID_MODES


def test_unknown_mode_raises():
    df = _mode_frame()
    with pytest.raises(ValueError):
        select_rejections_by_mode(df, "not_a_mode")
