"""Audit runner integration tests.

The v1.0.0 byte-identical CI gate has been retired. Its fixture,
``tests/legacy/expected_outputs_v1_defective.json``, is retained as a
regression witness of the v1.0.0 mint-pooled dispatch and is verified
via ``mode='mint_summary_LEGACY_defective'`` only. Corrected v2 outputs
will not match it (that mismatch is the intended correction, not a
regression). See RELEASE_HYGIENE_DRAFTS/CHANGELOG.md.
"""

import json
import warnings
from pathlib import Path

import pytest

from red2400_toolkit import (
    MODE_EVENT,
    MODE_LEGACY_MINT_POOLED,
    run_audit,
    load_deposit,
)


LEGACY_EXPECTED_OUTPUTS_PATH = (
    Path(__file__).parent / "legacy" / "expected_outputs_v1_defective.json"
)


def test_audit_runs_on_synthetic_deposit(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    res = run_audit(d, on_missing="quarantine")
    # synthetic deposit has 5 events (one per mint), 3 filter_ids
    assert int(res.overall["n"]) == 5
    assert set(res.per_filter.index) == {"filter_1", "filter_2", "filter_3"}
    # synthetic: 1 missed (M1) vs 1 saved_windowed (M2) -> ratio 1.0
    assert res.save_to_miss_conservative == pytest.approx(1.0)
    # combined adds 1 saved_early_death (M3) -> ratio 2.0
    assert res.save_to_miss_combined == pytest.approx(2.0)
    # Corrected default is per-event mode.
    assert res.mode == MODE_EVENT
    # Linkage diagnostic present.
    d_diag = res.linkage_diagnostic
    assert d_diag is not None
    assert d_diag.n_rejection_events == 5
    # M3 and M5 have no outcome rows -> 2 orphan rejections.
    assert d_diag.n_orphan_rejections == 2


def test_audit_runs_on_adversarial_deposit(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    res = run_audit(d, on_missing="quarantine")
    # 12 rejection events across 8 mints.
    assert int(res.overall["n"]) == 12
    # Filter labels align.
    expected_filters = {f"filter_{c}" for c in "ABCDEFGHIJ"}
    assert set(res.per_filter.index) == expected_filters


def test_legacy_mode_pools_by_mint_and_warns(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = run_audit(d, mode=MODE_LEGACY_MINT_POOLED, on_missing="quarantine")
    dep_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warns) >= 1, "legacy mode must emit a DeprecationWarning"
    # In legacy mode the classifications frame is indexed by mint, which
    # collapses M_REPEAT (2 events) and M_IDENTICAL_TS (2 events) so the
    # overall n drops from 12 events to <= 10 mint-events.
    assert res.mode == MODE_LEGACY_MINT_POOLED
    # legacy mode aggregates n = number of rejection rows, but each mint's
    # pooled tier is duplicated per rejection, so len == 12 remains.
    assert int(res.overall["n"]) == 12


@pytest.mark.skipif(
    not LEGACY_EXPECTED_OUTPUTS_PATH.is_file(),
    reason=(
        "legacy expected_outputs_v1_defective.json not present; "
        "this test only runs when the v1 regression witness is available"
    ),
)
def test_legacy_mode_reproduces_v1_defective_numbers_on_real_deposit(real_deposit_dir):
    """Reproduce the v1.0.0 numbers using LEGACY mode on the real deposit.

    This is a regression witness for the v1 mint-pooled dispatch — it
    confirms that ``mode='mint_summary_LEGACY_defective'`` faithfully
    reproduces the historical (defective) output. It is NOT a scientific
    correctness test.
    """
    expected = json.loads(LEGACY_EXPECTED_OUTPUTS_PATH.read_text())
    d = load_deposit(real_deposit_dir)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        res = run_audit(
            d,
            reference_price_mode=expected["reference_price_mode"],
            mode=MODE_LEGACY_MINT_POOLED,
        )
    actual = res.to_dict()
    assert actual["n_events"] == expected["n_rejections"]
    for filter_id, row in expected["per_filter"].items():
        for tier, expected_pct in row.items():
            actual_pct = actual["per_filter"][filter_id][tier]
            assert actual_pct == pytest.approx(expected_pct, abs=0.05), (
                f"filter {filter_id} tier {tier}: expected {expected_pct}, got {actual_pct}"
            )
    assert actual["save_to_miss_conservative"] == pytest.approx(
        expected["save_to_miss_conservative"], abs=0.005
    )
    assert actual["save_to_miss_combined"] == pytest.approx(
        expected["save_to_miss_combined"], abs=0.005
    )
