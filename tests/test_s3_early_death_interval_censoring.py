"""S3 scope-out disclosure tests — interval-censoring of age at ``gone``.

The S3 defect is that the recorded ``ageDays`` at a lifecycle transition
to ``gone`` is the age at which the tracker OBSERVED the transition,
i.e. an upper bound on the true age at death. The interval bracketing
the true event is not carried by the deposit, so an interval-censored
estimator cannot be run inside the toolkit. The scope-out fix is
disclosure:

- Every ClassificationDetail carries ``early_death_age_min_note`` =
  ``"upper_bound"`` when a ``gone`` transition was recorded.
- Every audit result carries a ``boundary_sensitive_early_death_count``
  that counts events whose recorded age sits within ±10 min of the
  60-min threshold, and a ``UserWarning`` fires when that count is
  non-zero.
- ``sensitivity_early_death_threshold`` exposes the point-estimator's
  sensitivity to the cutoff so users can bracket the effect.

Adversarial fixture: three events at 59, 60, 61 min (each exactly on
or adjacent to the boundary) and one event at 30 min (comfortably
inside early-death). All four should count as populated. Three should
land in the boundary band.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

from red2400_toolkit import (
    classify_dataset,
    run_audit,
    sensitivity_early_death_threshold,
)
from red2400_toolkit.red2400_loader import load_deposit


def _write_boundary_deposit(tmp_path: Path, ages_min: list[float]) -> Path:
    """Build a minimal deposit whose events have controlled early-death
    ages. Each event's mint has exactly one lifecycle ``gone`` row at
    the specified age. No forward outcome samples are provided.
    """
    n = len(ages_min)
    mints = [f"M_{i}" for i in range(n)]
    reject_ts = "2026-04-10T00:00:00.000Z"

    rejections = pd.DataFrame({
        "timestamp": [reject_ts] * n,
        "source":    ["s"] * n,
        "mint":      mints,
        "symbol":    mints,
        "reason":    [f"filter_{i}" for i in range(n)],
        "timeSlot":  ["normal"] * n,
    })

    # Sentinel-late outcome row so deposit_end sits well past every 24h
    # horizon and no S4 truncation occurs.
    outcomes = pd.DataFrame([{
        "sampleTs":     "2026-04-12T00:00:00.000Z",
        "mint":         mints[0],
        "symbol":       mints[0],
        "rejectReason": "filter_0",
        "rejectTs":     reject_ts,
        "ageMin":       2880.0,
        "priceUsd":     1.0,
        "liquidity":    100.0,
        "volume24h":    1000.0,
        "dexId":        "pumpswap",
        "pairAddress":  "P_sentinel",
    }])

    lifecycle_rows = []
    for i, age_min in enumerate(ages_min):
        lifecycle_rows.append({
            "ts":        "2026-04-10T00:30:00.000Z",
            "mint":      mints[i],
            "symbol":    mints[i],
            "from":      "alive_active",
            "to":        "gone",
            "liquidity": 0.0,
            "ageDays":   float(age_min) / 1440.0,
        })
    graveyard_lifecycle = pd.DataFrame(lifecycle_rows)

    rejections.to_csv(tmp_path / "rejections.csv", index=False)
    outcomes.to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    graveyard_lifecycle.to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Required tests per S3_DECISION.md §7
# ---------------------------------------------------------------------------

def test_upper_bound_note_populated(tmp_path):
    """Every event that has a ``gone`` transition must carry
    ``early_death_age_min_note = 'upper_bound'`` on the classification
    frame. Events with no ``gone`` transition carry ``None`` (or NaN).
    """
    _write_boundary_deposit(tmp_path, [59.0, 60.0, 61.0, 30.0])
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = classify_dataset(
            deposit.rejections,
            deposit.rejection_outcomes,
            deposit.graveyard_lifecycle,
            on_missing="quarantine",
        )
    # All four fixture events have a `gone` transition.
    assert "early_death_age_min_note" in df.columns
    notes = df["early_death_age_min_note"].tolist()
    assert notes.count("upper_bound") == 4, (
        f"expected 4 upper_bound notes, got: {notes}"
    )


def test_boundary_sensitive_warning_fires(tmp_path):
    """Adversarial fixture — an event at exactly 60 min, one at 59, and
    one at 61 min all sit within +/- 10 min of the 60-min threshold.
    ``run_audit`` must emit an S3 UserWarning naming the count.
    """
    # 59, 60, 61 in band; 30 out of band; 200 out of band -> 3 boundary-sensitive.
    _write_boundary_deposit(tmp_path, [59.0, 60.0, 61.0, 30.0, 200.0])
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = run_audit(deposit, on_missing="quarantine")

    assert res.boundary_sensitive_early_death_count == 3
    s3_msgs = [w for w in caught
               if issubclass(w.category, UserWarning)
               and "S3 disclosure" in str(w.message)]
    assert len(s3_msgs) == 1, (
        f"expected exactly one S3 warning; got {len(s3_msgs)}: "
        f"{[str(w.message) for w in caught]}"
    )
    assert "3 event(s)" in str(s3_msgs[0].message)


def test_sensitivity_helper_returns_expected_column_shape(tmp_path):
    """``sensitivity_early_death_threshold`` returns a DataFrame with
    one row per threshold in ``range(lower, upper+step, step)`` and the
    documented column shape.
    """
    _write_boundary_deposit(tmp_path, [59.0, 60.0, 61.0])
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = sensitivity_early_death_threshold(
            deposit, lower=45.0, upper=90.0, step=5.0,
            on_missing="quarantine",
        )
    expected_thresholds = [45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0]
    assert list(df["threshold_min"]) == expected_thresholds
    expected_cols = {
        "threshold_min",
        "n_events",
        "saved_early_death_pct",
        "saved_windowed_pct",
        "missed_pct",
        "flat_pct",
        "unclassifiable_pct",
        "boundary_sensitive_count",
    }
    assert expected_cols.issubset(set(df.columns)), (
        f"missing columns: {expected_cols - set(df.columns)}"
    )
    # At threshold=45 no event is early-death; at threshold=90 all three are.
    row_45 = df[df["threshold_min"] == 45.0].iloc[0]
    row_90 = df[df["threshold_min"] == 90.0].iloc[0]
    assert row_45["saved_early_death_pct"] < row_90["saved_early_death_pct"]
