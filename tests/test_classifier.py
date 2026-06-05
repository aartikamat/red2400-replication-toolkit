"""Deterministic five-tier classification tests."""

import pandas as pd

from red2400_toolkit.prfs_classifier import (
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_FLAT,
    TIER_MISSED,
    TIER_UNCLASSIFIABLE,
    classify_event,
    classify_dataset,
)
from red2400_toolkit.red2400_loader import load_deposit


# ---------- single-event unit tests ----------

def _samples(prices, age_mins=None, liquidity=None):
    if age_mins is None:
        age_mins = [60 * (i + 1) for i in range(len(prices))]
    if liquidity is None:
        liquidity = [100.0] * len(prices)
    return pd.DataFrame({"ageMin": age_mins, "priceUsd": prices, "liquidity": liquidity})


def test_missed_dominates_saved_windowed_per_tie_break():
    # First sample (smallest ageMin) sets reference. Later samples include
    # both a saved-triggering low and a missed-triggering high → MISSED wins.
    s = _samples(prices=[1.0, 0.3, 3.0], age_mins=[1, 60, 120])
    det = classify_event(s)
    assert det.tier == TIER_MISSED


def test_saved_windowed_alone():
    s = _samples(prices=[1.0, 0.4, 0.6], age_mins=[1, 60, 120])
    det = classify_event(s)
    assert det.tier == TIER_SAVED_WINDOWED


def test_saved_early_death_when_no_windowed_samples():
    s = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    lc = pd.DataFrame({
        "to":      ["gone"],
        "ageDays": [0.02],   # ≈ 29 min
    })
    det = classify_event(s, lifecycle_rows=lc)
    assert det.tier == TIER_SAVED_EARLY_DEATH


def test_early_death_not_applied_above_age_threshold():
    s = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    lc = pd.DataFrame({
        "to":      ["gone"],
        "ageDays": [0.05],   # 72 min > 60 min cutoff
    })
    det = classify_event(s, lifecycle_rows=lc)
    assert det.tier == TIER_UNCLASSIFIABLE


def test_flat_when_in_range():
    s = _samples(prices=[1.0, 1.05, 0.95], age_mins=[1, 60, 120])
    det = classify_event(s)
    assert det.tier == TIER_FLAT


def test_unclassifiable_no_samples_no_lifecycle():
    s = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    det = classify_event(s)
    assert det.tier == TIER_UNCLASSIFIABLE


def test_liquidity_proxy_mode_uses_liquidity_column():
    s = pd.DataFrame({
        "ageMin": [1, 60, 120],
        "priceUsd": [1.0, 1.0, 1.0],
        "liquidity": [100.0, 30.0, 200.0],   # ratio: 1, 0.3, 2.0
    })
    det = classify_event(s, reference_price_mode="liquidity_proxy")
    # liquidity goes from 100 → 30 (saved) AND 100 → 200 (missed) → MISSED
    assert det.tier == TIER_MISSED


# ---------- dataset-level test via synthetic deposit ----------

def test_dataset_classification_matches_synthetic_design(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
    )
    expected = {
        "M1": TIER_MISSED,
        "M2": TIER_SAVED_WINDOWED,
        "M3": TIER_SAVED_EARLY_DEATH,
        "M4": TIER_FLAT,
        "M5": TIER_UNCLASSIFIABLE,
    }
    for mint, tier in expected.items():
        actual = cls.loc[mint, "tier"]
        assert actual == tier, f"{mint}: expected {tier}, got {actual}"
