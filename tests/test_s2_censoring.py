"""S2 regression tests — right-censoring in matched_comparison.

S2: mints not observed by the lifecycle tracker were treated as
"not_gone" (observed survivors) in v2.0.0, biasing the gone-rate
downward. v2.0.1 labels them ``unobserved`` and excludes them from
the observed denominator; ``include_censored=True`` reproduces the
pre-S2 estimator.
"""

from __future__ import annotations

import math
import warnings

import pandas as pd
import pytest

from red2400_toolkit.early_death_validator import matched_comparison


def _make_cls_frame(rows):
    """Build a v2 event-keyed classifications frame."""
    return pd.DataFrame(rows).set_index("event_id")


# ---------------------------------------------------------------------------
# S2 T1 — censored counts reported
# ---------------------------------------------------------------------------

def test_matched_comparison_reports_censored_counts():
    cls = _make_cls_frame([
        {"event_id": "e1", "mint": "M_GONE",    "tier": "saved_early_death"},
        {"event_id": "e2", "mint": "M_ALIVE",   "tier": "saved_early_death"},
        {"event_id": "e3", "mint": "M_MISSING", "tier": "saved_early_death"},
        {"event_id": "e4", "mint": "M_MISSING", "tier": "missed"},
    ])
    lifecycle = pd.DataFrame([
        {"mint": "M_GONE",  "to": "gone",         "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "G", "from": "alive_active", "liquidity": 0.0, "ageDays": 0.02},
        {"mint": "M_ALIVE", "to": "alive_active", "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "A", "from": "", "liquidity": 100.0, "ageDays": 0.0},
    ])
    res = matched_comparison(cls, lifecycle)
    # M_GONE and M_ALIVE observed; M_MISSING has 2 events, both censored.
    # Early-death cohort: e1 (gone), e2 (alive_observed), e3 (unobserved).
    #   observed denom = 2, gone = 1 → 50 %
    #   censored_n = 1
    assert res.early_death_n == 3
    assert res.early_death_censored_n == 1
    assert res.early_death_gone_rate == pytest.approx(50.0)
    # Non-early-death cohort: e4 (unobserved).
    #   observed denom = 0 → NaN
    #   censored_n = 1
    assert res.non_early_death_n == 1
    assert res.non_early_death_censored_n == 1
    assert math.isnan(res.non_early_death_gone_rate)


# ---------------------------------------------------------------------------
# S2 T2 — observed denominator excludes unobserved mints
# ---------------------------------------------------------------------------

def test_matched_comparison_gone_rate_uses_observed_denominator():
    """Fixture where the old (pre-S2) code reports 25 % and the new code
    reports 50 % because half the events are right-censored.
    """
    cls = _make_cls_frame([
        {"event_id": f"e{i}", "mint": f"MG{i}", "tier": "missed"} for i in range(1, 3)
    ] + [
        {"event_id": f"e{i}", "mint": f"MU{i}", "tier": "missed"} for i in range(3, 5)
    ])
    lifecycle = pd.DataFrame([
        {"mint": "MG1", "to": "gone",         "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "G", "from": "alive_active", "liquidity": 0.0, "ageDays": 0.02},
        {"mint": "MG2", "to": "alive_active", "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "A", "from": "", "liquidity": 100.0, "ageDays": 0.0},
        # MU1, MU2 are absent from lifecycle (unobserved).
    ])
    # New (S2) estimator: observed = 2 events (MG1 gone, MG2 alive) → 50 %
    res_new = matched_comparison(cls, lifecycle)
    assert res_new.non_early_death_gone_rate == pytest.approx(50.0)
    # Old (pre-S2) estimator via include_censored=True: 1 gone / 4 total = 25 %
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        res_old = matched_comparison(cls, lifecycle, include_censored=True)
    assert res_old.non_early_death_gone_rate == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# S2 T3 — include_censored=True emits DeprecationWarning
# ---------------------------------------------------------------------------

def test_matched_comparison_include_censored_emits_deprecation_warning():
    cls = _make_cls_frame([
        {"event_id": "e1", "mint": "M1", "tier": "missed"},
    ])
    lifecycle = pd.DataFrame([], columns=["mint", "to", "ts", "symbol", "from",
                                          "liquidity", "ageDays"])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        matched_comparison(cls, lifecycle, include_censored=True)
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "include_censored=True must emit DeprecationWarning"


# ---------------------------------------------------------------------------
# S2 T4 — adversarial fixture covering 3 states x 2 tiers
# ---------------------------------------------------------------------------

def test_matched_comparison_censoring_adversarial_fixture():
    """4 mints x 3 states x 2 tiers: verify censored/observed/gone counts."""
    cls = _make_cls_frame([
        # early-death cohort
        {"event_id": "e1", "mint": "M_ED_GONE",    "tier": "saved_early_death"},
        {"event_id": "e2", "mint": "M_ED_ALIVE",   "tier": "saved_early_death"},
        {"event_id": "e3", "mint": "M_ED_UNOBS",   "tier": "saved_early_death"},
        # non-early-death cohort
        {"event_id": "e4", "mint": "M_ND_GONE",    "tier": "missed"},
        {"event_id": "e5", "mint": "M_ND_ALIVE",   "tier": "flat"},
        {"event_id": "e6", "mint": "M_ND_UNOBS_A", "tier": "missed"},
        {"event_id": "e7", "mint": "M_ND_UNOBS_B", "tier": "unclassifiable"},
    ])
    lifecycle = pd.DataFrame([
        {"mint": "M_ED_GONE",  "to": "gone",         "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "X", "from": "alive_active", "liquidity": 0.0, "ageDays": 0.02},
        {"mint": "M_ED_ALIVE", "to": "alive_active", "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "X", "from": "", "liquidity": 100.0, "ageDays": 0.0},
        {"mint": "M_ND_GONE",  "to": "gone",         "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "X", "from": "alive_active", "liquidity": 0.0, "ageDays": 0.5},
        {"mint": "M_ND_ALIVE", "to": "alive_active", "ts": "2026-04-10T00:00:00.000Z",
         "symbol": "X", "from": "", "liquidity": 100.0, "ageDays": 0.0},
    ])
    res = matched_comparison(cls, lifecycle)
    # Early-death: 1 gone (e1), 1 alive (e2), 1 unobserved (e3)
    assert res.early_death_n == 3
    assert res.early_death_censored_n == 1
    assert res.early_death_gone_rate == pytest.approx(50.0)  # 1/2
    # Non-early-death: 1 gone (e4), 1 alive (e5), 2 unobserved (e6, e7)
    assert res.non_early_death_n == 4
    assert res.non_early_death_censored_n == 2
    assert res.non_early_death_gone_rate == pytest.approx(50.0)  # 1/2
