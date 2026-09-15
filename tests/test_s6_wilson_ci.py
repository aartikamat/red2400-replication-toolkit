"""S6 regression tests — Wilson score CI on small-n filter statistics.

S6: v2.0.0 reported per-filter tier percentages as raw point estimates
with no uncertainty bound. filter_8 (n=19) in the RED-2400 v2 deposit
carries a wide Wilson interval that must be surfaced. v2.0.1 attaches
`<tier>_ci_lo` and `<tier>_ci_hi` columns to every per-filter and
overall row and warns for filters with n<30.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pandas as pd
import pytest

from red2400_toolkit.audit_runner import _wilson_ci, run_audit
from red2400_toolkit import load_deposit


# ---------------------------------------------------------------------------
# S6 T1 — Wilson CI matches textbook values (Newcombe 1998 Table)
# ---------------------------------------------------------------------------

def test_wilson_ci_matches_textbook_values():
    """Wilson score 95% CI for k=1, n=19 = approximately (0.94%, 24.55%)."""
    lo, hi = _wilson_ci(1, 19, alpha=0.05)
    # Newcombe 1998 Table II, method 3, k=1, n=19: interval ~0.9% to 24.6%.
    assert 0.7 <= lo <= 1.2, f"Wilson lo out of range: {lo}"
    assert 24.0 <= hi <= 25.0, f"Wilson hi out of range: {hi}"


def test_wilson_ci_edge_cases():
    # n = 0 → NaN
    lo, hi = _wilson_ci(0, 0)
    assert math.isnan(lo) and math.isnan(hi)
    # k = 0, n > 0 → lo pinned near 0 (float rounding tolerance)
    lo, hi = _wilson_ci(0, 100)
    assert lo == pytest.approx(0.0, abs=1e-10)
    assert 0.0 < hi < 5.0  # 95% upper for 0/100 is ~3.6%
    # k = n → hi pinned near 100
    lo, hi = _wilson_ci(100, 100)
    assert hi == pytest.approx(100.0, abs=1e-10)
    assert 90.0 < lo <= 100.0


# ---------------------------------------------------------------------------
# S6 T2 — per_filter and overall tables carry CI columns
# ---------------------------------------------------------------------------

def test_per_filter_table_carries_ci_columns(tmp_path):
    # minimal fixture — 3 events on 3 filters
    pd.DataFrame([
        {"timestamp": "2026-04-10T00:00:00.000Z", "source": "s", "mint": "M1",
         "symbol": "M1", "reason": "filter_1", "timeSlot": "normal"},
        {"timestamp": "2026-04-10T00:00:00.000Z", "source": "s", "mint": "M2",
         "symbol": "M2", "reason": "filter_2", "timeSlot": "normal"},
        {"timestamp": "2026-04-10T00:00:00.000Z", "source": "s", "mint": "M3",
         "symbol": "M3", "reason": "filter_3", "timeSlot": "normal"},
    ]).to_csv(tmp_path / "rejections.csv", index=False)
    pd.DataFrame([
        {"sampleTs": "2026-04-10T00:01:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_1", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        # Sentinel late sample so deposit_end is past the 24h windows
        {"sampleTs": "2026-04-11T22:00:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_1", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 2760, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
    ]).to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    pd.DataFrame([], columns=["ts", "mint", "symbol", "from", "to",
                              "liquidity", "ageDays"]
                 ).to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        res = run_audit(d, on_missing="quarantine")
    for tier in ("saved_windowed", "saved_early_death", "flat",
                 "missed", "unclassifiable"):
        assert f"{tier}_ci_lo" in res.per_filter.columns
        assert f"{tier}_ci_hi" in res.per_filter.columns
        assert f"{tier}_ci_lo" in res.overall.index
        assert f"{tier}_ci_hi" in res.overall.index


# ---------------------------------------------------------------------------
# S6 T3 — small-n warning fires for filter with n < warn_small_n_below
# ---------------------------------------------------------------------------

def test_small_n_warning_fires_for_filter_below_threshold(tmp_path):
    pd.DataFrame([
        {"timestamp": "2026-04-10T00:00:00.000Z", "source": "s", "mint": "M1",
         "symbol": "M1", "reason": "filter_8", "timeSlot": "normal"},
    ]).to_csv(tmp_path / "rejections.csv", index=False)
    pd.DataFrame([
        {"sampleTs": "2026-04-10T00:01:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_8", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        {"sampleTs": "2026-04-11T22:00:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_8", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 2760, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
    ]).to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    pd.DataFrame([], columns=["ts", "mint", "symbol", "from", "to",
                              "liquidity", "ageDays"]
                 ).to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_audit(d, on_missing="quarantine")
    small_n = [w for w in caught if issubclass(w.category, UserWarning)
               and "Small-n" in str(w.message) and "filter_8" in str(w.message)]
    assert small_n, "expected UserWarning naming filter_8 for small n"


# ---------------------------------------------------------------------------
# S6 T4 — small-n warning suppressed when warn_small_n_below=0
# ---------------------------------------------------------------------------

def test_small_n_warning_suppressed_with_zero_threshold(tmp_path):
    pd.DataFrame([
        {"timestamp": "2026-04-10T00:00:00.000Z", "source": "s", "mint": "M1",
         "symbol": "M1", "reason": "filter_9", "timeSlot": "normal"},
    ]).to_csv(tmp_path / "rejections.csv", index=False)
    pd.DataFrame([
        {"sampleTs": "2026-04-10T00:01:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_9", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        {"sampleTs": "2026-04-11T22:00:00.000Z", "mint": "M1", "symbol": "M1",
         "rejectReason": "filter_9", "rejectTs": "2026-04-10T00:00:00.000Z",
         "ageMin": 2760, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
    ]).to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    pd.DataFrame([], columns=["ts", "mint", "symbol", "from", "to",
                              "liquidity", "ageDays"]
                 ).to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    d = load_deposit(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_audit(d, on_missing="quarantine", warn_small_n_below=0)
    small_n = [w for w in caught if issubclass(w.category, UserWarning)
               and "Small-n" in str(w.message)]
    assert not small_n, "warn_small_n_below=0 must suppress small-n warning"
