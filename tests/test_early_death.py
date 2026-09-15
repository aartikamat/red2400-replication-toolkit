"""§V.C matched-comparison tests (updated for the event-keyed frame).

S2 (v2.0.1): mints absent from lifecycle are right-censored (labelled
``unobserved``) and excluded from the gone-rate denominator. Legacy
pre-S2 behavior is available via ``include_censored=True``.
"""

import math
import warnings

import pandas as pd

from red2400_toolkit.early_death_validator import matched_comparison
from red2400_toolkit.prfs_classifier import classify_dataset
from red2400_toolkit.red2400_loader import load_deposit


def test_matched_comparison_runs_on_synthetic_deposit(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Under S2: only M3 has lifecycle rows; M1/M2/M4/M5 are right-censored.
    res = matched_comparison(cls, d.graveyard_lifecycle)
    assert res.early_death_n == 1  # M3
    assert res.non_early_death_n == 4  # M1,M2,M4,M5
    # M3 is observed and gone → 100%
    assert res.early_death_gone_rate == 100.0
    # M1/M2/M4/M5 are all unobserved → non-early-death observed denom = 0 → NaN
    assert math.isnan(res.non_early_death_gone_rate)
    # Censored counts reflect the unobserved population
    assert res.early_death_censored_n == 0
    assert res.non_early_death_censored_n == 4
    assert res.censoring_note == "observed_denominator"


def test_matched_comparison_legacy_include_censored_reproduces_pre_s2_estimator(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = matched_comparison(cls, d.graveyard_lifecycle, include_censored=True)
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "include_censored=True must emit DeprecationWarning"
    # Pre-S2 behavior: unobserved counted as not_gone → non-ED gone rate = 0%
    assert res.non_early_death_gone_rate == 0.0
    assert res.censoring_note == "legacy_pre_s2_include_unobserved_as_alive"


def test_matched_comparison_handles_no_lifecycle_match():
    # Build an event-keyed frame (v2 shape) with two rows, distinct mints.
    cls = pd.DataFrame(
        {
            "mint": ["A", "B"],
            "tier": ["saved_early_death", "missed"],
        },
        index=pd.Index(["ev1", "ev2"], name="event_id"),
    )
    gl = pd.DataFrame({
        "mint": ["C"],
        "to":   ["gone"],
    })
    res = matched_comparison(cls, gl)
    assert res.early_death_n == 1
    assert res.non_early_death_n == 1
    # Under S2: A and B are unobserved → both cohorts have 0 observed rows
    # → gone_rate is NaN. Censored counts reflect the two events.
    assert math.isnan(res.early_death_gone_rate)
    assert math.isnan(res.non_early_death_gone_rate)
    assert res.early_death_censored_n == 1
    assert res.non_early_death_censored_n == 1
