"""S1 scope-out disclosure tests — first-observed-sample lag.

The S1 defect is that the reference-price the classifier anchors ratios at
is the earliest forward sample the extractor caught, not the price at the
rejection instant. Because the RED-2400 deposit carries no rejection-time
price, the fix is a scope-out disclosure: a lag-summary on the audit
result, a warning when the median lag is materially large, and a
per-event ``first_sample_lag_min`` field on the classification frame so
downstream analysis can bound the bias.

These tests exercise the defensive check itself — the scope-out is
permitted precisely because the underlying signal is not in the deposit
(see ``S1_DECISION.md`` for the permitted-reason 1 argument). What must
not silently regress is the disclosure surface.

Adversarial fixture: a two-event synthetic deposit where the first
extractor sample lags the rejection by 30 minutes on one event and by 1
minute on the other. Median lag = 15.5 min ⇒ above the default 5-min
warning threshold ⇒ warning fires.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

from red2400_toolkit import classify_dataset, run_audit
from red2400_toolkit.red2400_loader import load_deposit


def _write_deposit(tmp_path: Path, first_sample_lags_min: list[float]) -> Path:
    """Build a minimal deposit whose events have controlled first-sample lags.

    One rejection per lag value; every event's earliest sample sits at
    ``lag`` minutes past the rejection. A trailing "sentinel-late" row on
    the last event pushes deposit_end past the 24 h horizon so the S4
    right-truncation filter drops no events under default settings.
    """
    n = len(first_sample_lags_min)
    mints = [f"M{i}" for i in range(n)]
    reject_ts = "2026-04-10T00:00:00.000Z"

    rejections = pd.DataFrame({
        "timestamp": [reject_ts] * n,
        "source":    ["s"] * n,
        "mint":      mints,
        "symbol":    mints,
        "reason":    [f"filter_{i}" for i in range(n)],
        "timeSlot":  ["normal"] * n,
    })

    outcome_rows = []
    for i, lag in enumerate(first_sample_lags_min):
        # Compose sampleTs from integer minutes/seconds to sidestep
        # pandas' generic-unit Timedelta deprecation on some builds.
        total_secs = int(round(float(lag) * 60.0))
        hh, rem = divmod(total_secs, 3600)
        mm, ss = divmod(rem, 60)
        ts_first_str = f"2026-04-10T{hh:02d}:{mm:02d}:{ss:02d}.000Z"
        outcome_rows.append({
            "sampleTs":     ts_first_str,
            "mint":         mints[i],
            "symbol":       mints[i],
            "rejectReason": f"filter_{i}",
            "rejectTs":     reject_ts,
            "ageMin":       float(lag),
            "priceUsd":     1.0,
            "liquidity":    100.0,
            "volume24h":    1000.0,
            "dexId":        "pumpswap",
            "pairAddress":  f"P{i}",
        })

    # Sentinel-late row (out of any 24 h window; pushes deposit_end well
    # past every rejection's horizon so S4 does not truncate).
    outcome_rows.append({
        "sampleTs":     "2026-04-12T00:00:00.000Z",
        "mint":         mints[-1],
        "symbol":       mints[-1],
        "rejectReason": f"filter_{n-1}",
        "rejectTs":     reject_ts,
        "ageMin":       2880.0,
        "priceUsd":     1.0,
        "liquidity":    100.0,
        "volume24h":    1000.0,
        "dexId":        "pumpswap",
        "pairAddress":  f"P{n-1}",
    })
    rejection_outcomes = pd.DataFrame(outcome_rows)

    graveyard_lifecycle = pd.DataFrame(columns=[
        "ts", "mint", "symbol", "from", "to", "liquidity", "ageDays",
    ])

    rejections.to_csv(tmp_path / "rejections.csv", index=False)
    rejection_outcomes.to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    graveyard_lifecycle.to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Required tests per S1_DECISION.md §7
# ---------------------------------------------------------------------------

def test_lag_warning_fires_when_median_lag_high(tmp_path):
    """Adversarial fixture — median first-sample lag > 5 min triggers the S1 warning."""
    # 30-min lag on event 0; 30-min lag on event 1 → median = 30 min > 5 min.
    _write_deposit(tmp_path, [30.0, 30.0])
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_audit(deposit, on_missing="quarantine")
    s1_msgs = [w for w in caught
               if issubclass(w.category, UserWarning)
               and "S1 disclosure" in str(w.message)]
    assert len(s1_msgs) == 1, f"expected exactly one S1 warning; got {len(s1_msgs)}"
    msg = str(s1_msgs[0].message)
    assert "median first-sample lag" in msg
    assert "P90" in msg
    assert "P99" in msg


def test_lag_warning_silent_when_lag_low(tmp_path):
    """A deposit whose median first-sample lag is under 5 min must not
    trigger the S1 warning. This anchors the warning threshold — a
    silent regression that raises the warning gate above the default
    would masquerade an inflating extractor lag as clean.
    """
    _write_deposit(tmp_path, [1.0, 2.0, 1.0, 2.0])  # median = 1.5 min
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_audit(deposit, on_missing="quarantine")
    s1_msgs = [w for w in caught
               if issubclass(w.category, UserWarning)
               and "S1 disclosure" in str(w.message)]
    assert len(s1_msgs) == 0, (
        f"S1 warning fired at median-lag < 5 min: {[str(w.message) for w in s1_msgs]}"
    )


def test_first_sample_lag_min_populated_on_classification_detail(tmp_path):
    """The per-event ``first_sample_lag_min`` column must be present and
    populated. Every event with a usable reference-price sample must
    carry its earliest-sample lag; events without any usable sample
    (unclassifiable) may be NaN.
    """
    _write_deposit(tmp_path, [7.0, 12.0])
    deposit = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        res = run_audit(deposit, on_missing="quarantine")
    df = res.classifications
    assert "first_sample_lag_min" in df.columns
    # Every classified event with a reference price carries a lag.
    classified = df[df["reference_price"].notna()]
    assert len(classified) == 2
    assert set(classified["first_sample_lag_min"].tolist()) == {7.0, 12.0}
    # Result-level summary present.
    assert res.first_sample_lag_median_min is not None
    assert res.first_sample_lag_p90_min is not None
    assert res.first_sample_lag_p99_min is not None
    # to_dict payload also surfaces the summary.
    payload = res.to_dict()
    assert "first_sample_lag_median_min" in payload
    assert payload["first_sample_lag_median_min"] is not None
