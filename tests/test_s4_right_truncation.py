"""S4 regression tests — right-truncation at deposit-end.

S4: rejection events whose 24h forward window extends past the deposit's
latest sample timestamp were counted in the primary per-filter denominator
in v2.0.0. v2.0.1 flags them, excludes them from the primary denominator
by default, and surfaces their tier distribution separately.
``include_truncated=True`` reproduces the pre-S4 estimator.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

from red2400_toolkit import load_deposit, run_audit


_LIFECYCLE_COLS = ["ts", "mint", "symbol", "from", "to", "liquidity", "ageDays"]


def _write_deposit(tmp_path: Path, rejections, outcomes, lifecycle) -> Path:
    pd.DataFrame(rejections).to_csv(tmp_path / "rejections.csv", index=False)
    pd.DataFrame(outcomes).to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    if not lifecycle:
        pd.DataFrame(columns=_LIFECYCLE_COLS).to_csv(
            tmp_path / "graveyard_lifecycle.csv", index=False
        )
    else:
        pd.DataFrame(lifecycle).to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


def _rej(mint, ts, reason="filter_1"):
    return {"timestamp": ts, "source": "s", "mint": mint, "symbol": mint,
            "reason": reason, "timeSlot": "normal"}


def _out(mint, reject_ts, sample_ts, age_min, price, reason="filter_1"):
    return {"sampleTs": sample_ts, "mint": mint, "symbol": mint,
            "rejectReason": reason, "rejectTs": reject_ts,
            "ageMin": age_min, "priceUsd": price, "liquidity": 100.0,
            "volume24h": 1000.0, "dexId": "pumpswap", "pairAddress": "P1"}


# ---------------------------------------------------------------------------
# S4 T1 — right_truncated flag populated correctly
# ---------------------------------------------------------------------------

def test_right_truncated_flag_populated(tmp_path):
    """M_LATE's window extends past the latest sampleTs; M_EARLY's window is fully observed."""
    rejections = [
        _rej("M_EARLY", "2026-04-10T00:00:00.000Z"),  # window ends 2026-04-11 00:00
        _rej("M_LATE",  "2026-04-11T20:00:00.000Z"),  # window ends 2026-04-12 20:00
    ]
    outcomes = [
        _out("M_EARLY", "2026-04-10T00:00:00.000Z", "2026-04-10T00:01:00.000Z", 1, 1.0),
        # deposit_end_ms = 2026-04-11T22:00:00 — M_LATE window (2026-04-12 20:00) is past this.
        _out("M_LATE",  "2026-04-11T20:00:00.000Z", "2026-04-11T22:00:00.000Z", 120, 1.0),
    ]
    lifecycle = []
    _write_deposit(tmp_path, rejections, outcomes, lifecycle)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        # Use include_truncated=True to get ALL events in classifications
        res = run_audit(d, on_missing="quarantine", include_truncated=True)
    cls = res.classifications
    trunc_by_mint = {row["mint"]: row["right_truncated"]
                     for _, row in cls.iterrows()}
    assert trunc_by_mint["M_EARLY"] is False or trunc_by_mint["M_EARLY"] == False
    assert trunc_by_mint["M_LATE"] is True or trunc_by_mint["M_LATE"] == True
    assert res.truncated_events_n == 1


# ---------------------------------------------------------------------------
# S4 T2 — default primary denominator excludes right-truncated events
# ---------------------------------------------------------------------------

def test_right_truncated_excluded_from_primary_denominator(tmp_path):
    rejections = [
        _rej("M_EARLY", "2026-04-10T00:00:00.000Z"),
        _rej("M_LATE",  "2026-04-11T20:00:00.000Z"),
    ]
    outcomes = [
        _out("M_EARLY", "2026-04-10T00:00:00.000Z", "2026-04-10T00:01:00.000Z", 1, 1.0),
        _out("M_LATE",  "2026-04-11T20:00:00.000Z", "2026-04-11T22:00:00.000Z", 120, 1.0),
    ]
    lifecycle = []
    _write_deposit(tmp_path, rejections, outcomes, lifecycle)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        res = run_audit(d, on_missing="quarantine")  # default include_truncated=False
    # Primary denominator = 1 (only M_EARLY); M_LATE excluded.
    assert int(res.overall["n"]) == 1
    assert res.truncated_events_n == 1
    assert res.truncated_tier_distribution is not None


# ---------------------------------------------------------------------------
# S4 T3 — include_truncated=True reproduces pre-S4 estimator + warns
# ---------------------------------------------------------------------------

def test_include_truncated_reproduces_legacy_estimator_and_warns(tmp_path):
    rejections = [
        _rej("M_EARLY", "2026-04-10T00:00:00.000Z"),
        _rej("M_LATE",  "2026-04-11T20:00:00.000Z"),
    ]
    outcomes = [
        _out("M_EARLY", "2026-04-10T00:00:00.000Z", "2026-04-10T00:01:00.000Z", 1, 1.0),
        _out("M_LATE",  "2026-04-11T20:00:00.000Z", "2026-04-11T22:00:00.000Z", 120, 1.0),
    ]
    lifecycle = []
    _write_deposit(tmp_path, rejections, outcomes, lifecycle)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = run_audit(d, on_missing="quarantine", include_truncated=True)
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "include_truncated=True must emit DeprecationWarning"
    assert int(res.overall["n"]) == 2  # legacy pre-S4 count: both events


# ---------------------------------------------------------------------------
# S4 T4 — adversarial fixture: boundary events (exactly-at boundary vs past)
# ---------------------------------------------------------------------------

def test_right_truncation_adversarial_boundary(tmp_path):
    """Three events: one clearly full, one exactly-at boundary (window ends at deposit_end),
    one clearly past (window ends after deposit_end)."""
    rejections = [
        _rej("M_FULL",     "2026-04-10T00:00:00.000Z"),  # window 24h => 2026-04-11 00:00
        _rej("M_BOUNDARY", "2026-04-10T22:00:00.000Z"),  # window 24h => 2026-04-11 22:00 (== deposit_end)
        _rej("M_PAST",     "2026-04-11T20:00:00.000Z"),  # window 24h => 2026-04-12 20:00 (>> deposit_end)
    ]
    outcomes = [
        _out("M_FULL",     "2026-04-10T00:00:00.000Z", "2026-04-10T00:01:00.000Z", 1, 1.0),
        _out("M_BOUNDARY", "2026-04-10T22:00:00.000Z", "2026-04-10T22:01:00.000Z", 1, 1.0),
        _out("M_PAST",     "2026-04-11T20:00:00.000Z", "2026-04-11T22:00:00.000Z", 120, 1.0),
    ]
    lifecycle = []
    _write_deposit(tmp_path, rejections, outcomes, lifecycle)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        res = run_audit(d, on_missing="quarantine", include_truncated=True)
    cls = res.classifications.set_index("mint")
    # Deposit end = 2026-04-11T22:00:00, ms = 1744408800000
    # M_FULL: reject + 24h = 2026-04-11 00:00 → 1744329600000 <= 1744408800000 → NOT truncated
    # M_BOUNDARY: reject + 24h = 2026-04-11 22:00 → 1744408800000 <= 1744408800000 → NOT truncated (equality)
    # M_PAST: reject + 24h = 2026-04-12 20:00 → 1744495200000 > 1744408800000 → truncated
    assert cls.loc["M_FULL", "right_truncated"] == False
    assert cls.loc["M_BOUNDARY", "right_truncated"] == False  # exact boundary retained
    assert cls.loc["M_PAST", "right_truncated"] == True
