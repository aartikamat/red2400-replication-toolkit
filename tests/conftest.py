"""Shared test fixtures.

Provides:

- ``synthetic_deposit``: the v1-era one-event-per-mint fixture, retained
  as a smoke test.
- ``adversarial_deposit``: hand-crafted fixture exercising the mint-collapse
  defect. See ``ADVERSARIAL_HAND_TABLE`` for the expected per-event tier.
- ``real_deposit_dir``: env-var-gated path to the canonical RED-2400 deposit.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest


REAL_DEPOSIT_ENV = "RED2400_DEPOSIT_DIR"


# ---------------------------------------------------------------------------
# v1-era synthetic deposit (one event per mint) — retained smoke fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_deposit(tmp_path: Path) -> Path:
    """Build a tiny three-file deposit with known classifications.

    Mints designed (one event per mint — v1-era simple case):
      M1: missed         (first sample price 1.0; later sample price 3.0)
      M2: saved_windowed (first sample price 1.0; later sample price 0.3)
      M3: saved_early_death (lifecycle has gone @ ageDays 0.02 ~= 29 min;
                             no in-window samples)
      M4: flat           (samples cluster near 1.0)
      M5: unclassifiable (no samples, no lifecycle row)
    """
    rejections = pd.DataFrame({
        "timestamp": ["2026-04-10T21:10:13.000Z"] * 5,
        "source":    ["source_a"] * 5,
        "mint":      ["M1", "M2", "M3", "M4", "M5"],
        "symbol":    ["S1", "S2", "S3", "S4", "S5"],
        "reason":    ["filter_1", "filter_1", "filter_2", "filter_2", "filter_3"],
        "timeSlot":  ["normal"] * 5,
    })

    # Note: sampleTs is per-sample, not shared, so exact-key S5
    # deduplication does not spuriously merge distinct probes.
    # The last row is a sentinel-late sample on M4 with sampleTs beyond
    # 24h after every rejection so S4 right-truncation does not flag any
    # event in this synthetic fixture (deposit_end_ms is safely past
    # every rejectTs + 24h). Its ageMin > 1440 keeps it out of the
    # classification window; it exists solely to set deposit_end_ms.
    rejection_outcomes = pd.DataFrame({
        "sampleTs":    [
            "2026-04-10T21:11:13.000Z",  # M1 sample at ageMin=1
            "2026-04-10T22:10:13.000Z",  # M1 sample at ageMin=60
            "2026-04-10T21:11:13.000Z",  # M2 sample at ageMin=1
            "2026-04-10T22:10:13.000Z",  # M2 sample at ageMin=60
            "2026-04-10T21:11:13.000Z",  # M4 sample at ageMin=1
            "2026-04-10T21:40:13.000Z",  # M4 sample at ageMin=30
            "2026-04-10T22:10:13.000Z",  # M4 sample at ageMin=60
            "2026-04-11T22:10:13.000Z",  # M4 sentinel-late sample (ageMin=1500, out of window)
        ],
        "mint":        ["M1", "M1", "M2", "M2", "M4", "M4", "M4", "M4"],
        "symbol":      ["S1", "S1", "S2", "S2", "S4", "S4", "S4", "S4"],
        "rejectReason":["filter_1"] * 4 + ["filter_2"] * 4,
        "rejectTs":    ["2026-04-10T21:10:13.000Z"] * 8,
        "ageMin":      [1, 60, 1, 60, 1, 30, 60, 1500],
        "priceUsd":    [1.0, 3.0, 1.0, 0.3, 1.0, 1.05, 0.95, 1.0],
        "liquidity":   [100.0] * 8,
        "volume24h":   [1000.0] * 8,
        "dexId":       ["pumpswap"] * 8,
        "pairAddress": ["P"] * 8,
    })

    graveyard_lifecycle = pd.DataFrame({
        "ts":        ["2026-04-10T21:40:13.000Z", "2026-04-11T21:10:13.000Z"],
        "mint":      ["M3", "M3"],
        "symbol":    ["S3", "S3"],
        "from":      ["", "alive_active"],
        "to":        ["alive_active", "gone"],
        "liquidity": [100.0, 0.0],
        "ageDays":   [0.0, 0.02],   # 0.02 days ~= 28.8 min -> early death
    })

    rejections.to_csv(tmp_path / "rejections.csv", index=False)
    rejection_outcomes.to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    graveyard_lifecycle.to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Adversarial deposit — the load-bearing fixture for the mint-collapse fix
# ---------------------------------------------------------------------------

# Hand-computed expected tier for every event in the adversarial fixture.
# Keys are (mint, timestamp, reason) tuples so the test can look them up
# without depending on event_id derivation.
#
# See the docstring below for the reasoning behind each cell.
ADVERSARIAL_HAND_TABLE = {
    # M_REPEAT: same mint rejected under two different filters at two
    # different times; each has its own disjoint trajectory.
    ("M_REPEAT", "2026-04-10T21:10:13.000Z", "filter_A"): "missed",           # 1.0 -> 3.0 hits missed
    ("M_REPEAT", "2026-04-10T22:10:13.000Z", "filter_B"): "saved_windowed",   # 1.0 -> 0.3 hits saved_w

    # M_SAME_FILTER_TWICE: same mint, same filter, two separate rejections
    # at different timestamps. Each event still has its own trajectory.
    ("M_SAME_FILTER_TWICE", "2026-04-10T21:00:00.000Z", "filter_C"): "flat",     # cluster near 1.0
    ("M_SAME_FILTER_TWICE", "2026-04-10T23:00:00.000Z", "filter_C"): "missed",   # 1.0 -> 4.0

    # M_OVERLAP: two events on the same mint 4h apart. Their observation
    # windows overlap (12+ hours of shared calendar time). Each event's
    # forward samples are separately provided and each classification is
    # made only from that event's own outcome rows.
    ("M_OVERLAP", "2026-04-11T00:00:00.000Z", "filter_D"): "saved_windowed",  # 1.0 -> 0.4
    ("M_OVERLAP", "2026-04-11T04:00:00.000Z", "filter_D"): "flat",            # 1.0 -> 1.1

    # M_IDENTICAL_TS: two events on the same mint at the EXACT same time
    # but under different filters. Event_id includes the reason so they
    # must remain distinct.
    ("M_IDENTICAL_TS", "2026-04-11T09:00:00.000Z", "filter_E"): "missed",         # 1.0 -> 2.5
    ("M_IDENTICAL_TS", "2026-04-11T09:00:00.000Z", "filter_F"): "saved_windowed", # 1.0 -> 0.2

    # M_MISSING_PRICE: outcome rows exist but priceUsd is NaN -> falls
    # through to lifecycle -> unclassifiable (no lifecycle for this mint).
    ("M_MISSING_PRICE", "2026-04-11T10:00:00.000Z", "filter_G"): "unclassifiable",

    # M_NO_HORIZON: outcome rows exist but ageMin > 1440 (out of window)
    # AND no lifecycle. Falls through to unclassifiable.
    ("M_NO_HORIZON", "2026-04-11T11:00:00.000Z", "filter_H"): "unclassifiable",

    # M_EARLY_DEATH: no samples, lifecycle has gone @ 30 min -> saved_early_death.
    ("M_EARLY_DEATH", "2026-04-11T12:00:00.000Z", "filter_I"): "saved_early_death",

    # M_ORPHAN: rejection has NO matching outcome rows AND no lifecycle.
    # Under on_missing='quarantine' the event still gets a row with
    # tier=unclassifiable (empty samples). Under on_missing='raise' the
    # call fails — tested separately.
    ("M_ORPHAN", "2026-04-11T13:00:00.000Z", "filter_J"): "unclassifiable",
}


@pytest.fixture
def adversarial_deposit(tmp_path: Path) -> Path:
    """Adversarial three-file deposit covering the mint-collapse defect.

    Every cell of ``ADVERSARIAL_HAND_TABLE`` is realized here.
    """
    rejections = pd.DataFrame([
        # M_REPEAT: two events at different times, different filters.
        {"timestamp": "2026-04-10T21:10:13.000Z", "source": "s", "mint": "M_REPEAT",
         "symbol": "R", "reason": "filter_A", "timeSlot": "normal"},
        {"timestamp": "2026-04-10T22:10:13.000Z", "source": "s", "mint": "M_REPEAT",
         "symbol": "R", "reason": "filter_B", "timeSlot": "normal"},
        # M_SAME_FILTER_TWICE.
        {"timestamp": "2026-04-10T21:00:00.000Z", "source": "s", "mint": "M_SAME_FILTER_TWICE",
         "symbol": "T", "reason": "filter_C", "timeSlot": "normal"},
        {"timestamp": "2026-04-10T23:00:00.000Z", "source": "s", "mint": "M_SAME_FILTER_TWICE",
         "symbol": "T", "reason": "filter_C", "timeSlot": "normal"},
        # M_OVERLAP.
        {"timestamp": "2026-04-11T00:00:00.000Z", "source": "s", "mint": "M_OVERLAP",
         "symbol": "O", "reason": "filter_D", "timeSlot": "normal"},
        {"timestamp": "2026-04-11T04:00:00.000Z", "source": "s", "mint": "M_OVERLAP",
         "symbol": "O", "reason": "filter_D", "timeSlot": "normal"},
        # M_IDENTICAL_TS.
        {"timestamp": "2026-04-11T09:00:00.000Z", "source": "s", "mint": "M_IDENTICAL_TS",
         "symbol": "I", "reason": "filter_E", "timeSlot": "normal"},
        {"timestamp": "2026-04-11T09:00:00.000Z", "source": "s", "mint": "M_IDENTICAL_TS",
         "symbol": "I", "reason": "filter_F", "timeSlot": "normal"},
        # M_MISSING_PRICE.
        {"timestamp": "2026-04-11T10:00:00.000Z", "source": "s", "mint": "M_MISSING_PRICE",
         "symbol": "P", "reason": "filter_G", "timeSlot": "normal"},
        # M_NO_HORIZON.
        {"timestamp": "2026-04-11T11:00:00.000Z", "source": "s", "mint": "M_NO_HORIZON",
         "symbol": "H", "reason": "filter_H", "timeSlot": "normal"},
        # M_EARLY_DEATH.
        {"timestamp": "2026-04-11T12:00:00.000Z", "source": "s", "mint": "M_EARLY_DEATH",
         "symbol": "E", "reason": "filter_I", "timeSlot": "normal"},
        # M_ORPHAN.
        {"timestamp": "2026-04-11T13:00:00.000Z", "source": "s", "mint": "M_ORPHAN",
         "symbol": "Z", "reason": "filter_J", "timeSlot": "normal"},
    ])

    rejection_outcomes = pd.DataFrame([
        # M_REPEAT, event A: 1.0 -> 3.0 -> 0.4 (missed wins)
        {"sampleTs": "2026-04-10T21:11:13.000Z", "mint": "M_REPEAT", "symbol": "R",
         "rejectReason": "filter_A", "rejectTs": "2026-04-10T21:10:13.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        {"sampleTs": "2026-04-10T22:10:13.000Z", "mint": "M_REPEAT", "symbol": "R",
         "rejectReason": "filter_A", "rejectTs": "2026-04-10T21:10:13.000Z",
         "ageMin": 60, "priceUsd": 3.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        {"sampleTs": "2026-04-10T23:10:13.000Z", "mint": "M_REPEAT", "symbol": "R",
         "rejectReason": "filter_A", "rejectTs": "2026-04-10T21:10:13.000Z",
         "ageMin": 120, "priceUsd": 0.4, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        # M_REPEAT, event B: 1.0 -> 0.3 (saved_windowed)
        {"sampleTs": "2026-04-10T22:11:13.000Z", "mint": "M_REPEAT", "symbol": "R",
         "rejectReason": "filter_B", "rejectTs": "2026-04-10T22:10:13.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},
        {"sampleTs": "2026-04-10T23:10:13.000Z", "mint": "M_REPEAT", "symbol": "R",
         "rejectReason": "filter_B", "rejectTs": "2026-04-10T22:10:13.000Z",
         "ageMin": 60, "priceUsd": 0.3, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P1"},

        # M_SAME_FILTER_TWICE, event 1 (21:00): 1.0 -> 1.05 (flat)
        {"sampleTs": "2026-04-10T21:01:00.000Z", "mint": "M_SAME_FILTER_TWICE", "symbol": "T",
         "rejectReason": "filter_C", "rejectTs": "2026-04-10T21:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P2"},
        {"sampleTs": "2026-04-10T22:00:00.000Z", "mint": "M_SAME_FILTER_TWICE", "symbol": "T",
         "rejectReason": "filter_C", "rejectTs": "2026-04-10T21:00:00.000Z",
         "ageMin": 60, "priceUsd": 1.05, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P2"},
        # M_SAME_FILTER_TWICE, event 2 (23:00): 1.0 -> 4.0 (missed)
        {"sampleTs": "2026-04-10T23:01:00.000Z", "mint": "M_SAME_FILTER_TWICE", "symbol": "T",
         "rejectReason": "filter_C", "rejectTs": "2026-04-10T23:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P2"},
        {"sampleTs": "2026-04-11T00:00:00.000Z", "mint": "M_SAME_FILTER_TWICE", "symbol": "T",
         "rejectReason": "filter_C", "rejectTs": "2026-04-10T23:00:00.000Z",
         "ageMin": 60, "priceUsd": 4.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P2"},

        # M_OVERLAP, event 1 (00:00): 1.0 -> 0.4 (saved_windowed)
        {"sampleTs": "2026-04-11T00:01:00.000Z", "mint": "M_OVERLAP", "symbol": "O",
         "rejectReason": "filter_D", "rejectTs": "2026-04-11T00:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P3"},
        {"sampleTs": "2026-04-11T01:00:00.000Z", "mint": "M_OVERLAP", "symbol": "O",
         "rejectReason": "filter_D", "rejectTs": "2026-04-11T00:00:00.000Z",
         "ageMin": 60, "priceUsd": 0.4, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P3"},
        # M_OVERLAP, event 2 (04:00): 1.0 -> 1.1 (flat)
        {"sampleTs": "2026-04-11T04:01:00.000Z", "mint": "M_OVERLAP", "symbol": "O",
         "rejectReason": "filter_D", "rejectTs": "2026-04-11T04:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P3"},
        {"sampleTs": "2026-04-11T05:00:00.000Z", "mint": "M_OVERLAP", "symbol": "O",
         "rejectReason": "filter_D", "rejectTs": "2026-04-11T04:00:00.000Z",
         "ageMin": 60, "priceUsd": 1.1, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P3"},

        # M_IDENTICAL_TS, event E: 1.0 -> 2.5 (missed)
        {"sampleTs": "2026-04-11T09:01:00.000Z", "mint": "M_IDENTICAL_TS", "symbol": "I",
         "rejectReason": "filter_E", "rejectTs": "2026-04-11T09:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P4"},
        {"sampleTs": "2026-04-11T10:00:00.000Z", "mint": "M_IDENTICAL_TS", "symbol": "I",
         "rejectReason": "filter_E", "rejectTs": "2026-04-11T09:00:00.000Z",
         "ageMin": 60, "priceUsd": 2.5, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P4"},
        # M_IDENTICAL_TS, event F: 1.0 -> 0.2 (saved_windowed)
        {"sampleTs": "2026-04-11T09:01:00.000Z", "mint": "M_IDENTICAL_TS", "symbol": "I",
         "rejectReason": "filter_F", "rejectTs": "2026-04-11T09:00:00.000Z",
         "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P4"},
        {"sampleTs": "2026-04-11T10:00:00.000Z", "mint": "M_IDENTICAL_TS", "symbol": "I",
         "rejectReason": "filter_F", "rejectTs": "2026-04-11T09:00:00.000Z",
         "ageMin": 60, "priceUsd": 0.2, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P4"},

        # M_MISSING_PRICE: two samples but priceUsd is NaN.
        {"sampleTs": "2026-04-11T10:01:00.000Z", "mint": "M_MISSING_PRICE", "symbol": "P",
         "rejectReason": "filter_G", "rejectTs": "2026-04-11T10:00:00.000Z",
         "ageMin": 1, "priceUsd": float("nan"), "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P5"},
        {"sampleTs": "2026-04-11T11:00:00.000Z", "mint": "M_MISSING_PRICE", "symbol": "P",
         "rejectReason": "filter_G", "rejectTs": "2026-04-11T10:00:00.000Z",
         "ageMin": 60, "priceUsd": float("nan"), "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P5"},

        # M_NO_HORIZON: samples exist but out of 24h window.
        {"sampleTs": "2026-04-13T11:00:00.000Z", "mint": "M_NO_HORIZON", "symbol": "H",
         "rejectReason": "filter_H", "rejectTs": "2026-04-11T11:00:00.000Z",
         "ageMin": 2880, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
         "dexId": "pumpswap", "pairAddress": "P6"},

        # M_EARLY_DEATH has no outcome rows at all.
        # M_ORPHAN has no outcome rows at all.
    ])

    graveyard_lifecycle = pd.DataFrame([
        {"ts": "2026-04-11T12:30:00.000Z", "mint": "M_EARLY_DEATH", "symbol": "E",
         "from": "alive_active", "to": "gone", "liquidity": 0.0, "ageDays": 0.02},  # ~29 min
    ])

    rejections.to_csv(tmp_path / "rejections.csv", index=False)
    rejection_outcomes.to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    graveyard_lifecycle.to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


@pytest.fixture
def adversarial_expected_table():
    """Frozen hand-worked expected classification table.

    Keys: (mint, rejection_timestamp, filter). Values: expected tier string.
    Tests iterate this table and assert both the toolkit and the oracle
    match every cell.
    """
    return dict(ADVERSARIAL_HAND_TABLE)


# ---------------------------------------------------------------------------
# Real deposit — env-var-gated
# ---------------------------------------------------------------------------

@pytest.fixture
def real_deposit_dir():
    """Path to a local copy of the RED-2400 deposit, if available.

    Skipped if RED2400_DEPOSIT_DIR env var is not set.
    """
    p = os.environ.get(REAL_DEPOSIT_ENV)
    if not p or not Path(p).is_dir():
        pytest.skip(f"set {REAL_DEPOSIT_ENV} to a local RED-2400 deposit dir to run this test")
    return Path(p)
