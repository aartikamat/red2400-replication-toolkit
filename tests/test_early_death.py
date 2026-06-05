"""§V.C matched-comparison tests."""

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
    )
    res = matched_comparison(cls, d.graveyard_lifecycle)
    # synthetic: 1 early-death (M3, ever gone) vs 4 non-early-death (M1,M2,M4,M5; none gone)
    assert res.early_death_n == 1
    assert res.non_early_death_n == 4
    assert res.early_death_gone_rate == 100.0
    assert res.non_early_death_gone_rate == 0.0


def test_matched_comparison_handles_no_lifecycle_match():
    cls = pd.DataFrame(
        {"tier": ["saved_early_death", "missed"]},
        index=pd.Index(["A", "B"], name="mint"),
    )
    gl = pd.DataFrame({
        "mint": ["C"],
        "to":   ["gone"],
    })
    res = matched_comparison(cls, gl)
    # A is tier early_death but no lifecycle row → ever_gone defaults to not_gone
    # B is non-early-death, similarly not_gone
    assert res.early_death_n == 1
    assert res.non_early_death_n == 1
    assert res.early_death_gone_rate == 0.0
    assert res.non_early_death_gone_rate == 0.0
