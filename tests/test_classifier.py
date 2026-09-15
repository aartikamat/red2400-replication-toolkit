"""Deterministic five-tier classification tests (single-event unit tests
plus the v1-era dataset smoke test, updated for the event-keyed dispatch)."""

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


# ---------- single-event unit tests (unchanged by v2) ----------

def _samples(prices, age_mins=None, liquidity=None):
    if age_mins is None:
        age_mins = [60 * (i + 1) for i in range(len(prices))]
    if liquidity is None:
        liquidity = [100.0] * len(prices)
    return pd.DataFrame({"ageMin": age_mins, "priceUsd": prices, "liquidity": liquidity})


def test_missed_dominates_saved_windowed_per_tie_break():
    s = _samples(prices=[1.0, 0.3, 3.0], age_mins=[1, 60, 120])
    det = classify_event(s)
    assert det.tier == TIER_MISSED


def test_saved_windowed_alone():
    s = _samples(prices=[1.0, 0.4, 0.6], age_mins=[1, 60, 120])
    det = classify_event(s)
    assert det.tier == TIER_SAVED_WINDOWED


def test_saved_early_death_when_no_windowed_samples():
    s = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    lc = pd.DataFrame({"to": ["gone"], "ageDays": [0.02]})
    det = classify_event(s, lifecycle_rows=lc)
    assert det.tier == TIER_SAVED_EARLY_DEATH


def test_early_death_not_applied_above_age_threshold():
    s = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    lc = pd.DataFrame({"to": ["gone"], "ageDays": [0.05]})
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
        "liquidity": [100.0, 30.0, 200.0],
    })
    det = classify_event(s, reference_price_mode="liquidity_proxy")
    assert det.tier == TIER_MISSED


# ---------- dataset-level test via v1-era synthetic deposit ----------

def test_dataset_classification_matches_synthetic_design(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    # M3 (early-death path) and M5 (unclassifiable path) have no outcome
    # rows in the v1-era synthetic fixture; that is deliberate for the
    # lifecycle/unclassifiable branches. Pass on_missing='quarantine' so
    # the classifier tolerates event-linkage orphans instead of raising.
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # v2 output is indexed by event_id and carries mint as a column.
    # One event per mint in this fixture, so we can lookup by mint.
    by_mint = cls.reset_index().set_index("mint")
    expected = {
        "M1": TIER_MISSED,
        "M2": TIER_SAVED_WINDOWED,
        "M3": TIER_SAVED_EARLY_DEATH,
        "M4": TIER_FLAT,
        "M5": TIER_UNCLASSIFIABLE,
    }
    for mint, tier in expected.items():
        actual = by_mint.loc[mint, "tier"]
        assert actual == tier, f"{mint}: expected {tier}, got {actual}"
