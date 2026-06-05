"""Shared test fixtures: synthetic deposit matching RED-2400 v2.1 schema."""

import os
from pathlib import Path

import pandas as pd
import pytest


REAL_DEPOSIT_ENV = "RED2400_DEPOSIT_DIR"


@pytest.fixture
def synthetic_deposit(tmp_path: Path) -> Path:
    """Build a tiny three-file deposit with known classifications.

    Mints designed:
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

    rejection_outcomes = pd.DataFrame({
        "sampleTs":    ["2026-04-10T21:11:13.000Z"] * 7,
        "mint":        ["M1", "M1", "M2", "M2", "M4", "M4", "M4"],
        "symbol":      ["S1", "S1", "S2", "S2", "S4", "S4", "S4"],
        "rejectReason":["filter_1"] * 4 + ["filter_2"] * 3,
        "rejectTs":    ["2026-04-10T21:10:13.000Z"] * 7,
        "ageMin":      [1, 60, 1, 60, 1, 30, 60],
        "priceUsd":    [1.0, 3.0, 1.0, 0.3, 1.0, 1.05, 0.95],
        "liquidity":   [100.0] * 7,
        "volume24h":   [1000.0] * 7,
        "dexId":       ["pumpswap"] * 7,
        "pairAddress": ["P"] * 7,
    })

    graveyard_lifecycle = pd.DataFrame({
        "ts":        ["2026-04-10T21:40:13.000Z", "2026-04-11T21:10:13.000Z"],
        "mint":      ["M3", "M3"],
        "symbol":    ["S3", "S3"],
        "from":      ["", "alive_active"],
        "to":        ["alive_active", "gone"],
        "liquidity": [100.0, 0.0],
        "ageDays":   [0.0, 0.02],   # 0.02 days ≈ 28.8 min → early death
    })

    rejections.to_csv(tmp_path / "rejections.csv", index=False)
    rejection_outcomes.to_csv(tmp_path / "rejection_outcomes.csv", index=False)
    graveyard_lifecycle.to_csv(tmp_path / "graveyard_lifecycle.csv", index=False)
    return tmp_path


@pytest.fixture
def real_deposit_dir():
    """Path to a local copy of the RED-2400 deposit, if available.

    Skipped if RED2400_DEPOSIT_DIR env var is not set. Real-data tests use
    this to verify byte-identical reproducibility against published numbers.
    """
    p = os.environ.get(REAL_DEPOSIT_ENV)
    if not p or not Path(p).is_dir():
        pytest.skip(f"set {REAL_DEPOSIT_ENV} to a local RED-2400 deposit dir to run this test")
    return Path(p)
