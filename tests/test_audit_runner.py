"""Audit runner integration tests + byte-identical reproducibility gate."""

import json
from pathlib import Path

import pytest

from red2400_toolkit.audit_runner import run_audit
from red2400_toolkit.red2400_loader import load_deposit


EXPECTED_OUTPUTS_PATH = Path(__file__).parent / "expected_outputs.json"


def test_audit_runs_on_synthetic_deposit(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    res = run_audit(d)
    # synthetic deposit has 5 mints, 3 filter_ids
    assert int(res.overall["n"]) == 5
    assert set(res.per_filter.index) == {"filter_1", "filter_2", "filter_3"}
    # synthetic: 1 missed (M1) vs 1 saved_windowed (M2) → ratio 1.0
    assert res.save_to_miss_conservative == pytest.approx(1.0)
    # combined adds 1 saved_early_death (M3) → ratio 2.0
    assert res.save_to_miss_combined == pytest.approx(2.0)


@pytest.mark.skipif(
    not EXPECTED_OUTPUTS_PATH.is_file(),
    reason=(
        "expected_outputs.json not provided — run "
        "scripts/generate_expected_outputs.py against the canonical deposit"
    ),
)
def test_audit_reproduces_kamat_2026_byte_identical(real_deposit_dir):
    """The audit run on the canonical RED-2400 deposit must produce
    the reference per-filter table and save-to-miss ratios.

    Reference outputs live in `tests/expected_outputs.json`, populated once
    from a canonical audit run via `scripts/generate_expected_outputs.py`.
    If this test ever fails, the audit results have drifted from the
    versioned reference — investigate before tagging a new release.
    """
    expected = json.loads(EXPECTED_OUTPUTS_PATH.read_text())
    d = load_deposit(real_deposit_dir)
    res = run_audit(d, reference_price_mode=expected["reference_price_mode"])
    actual = res.to_dict()

    assert actual["n_rejections"] == expected["n_rejections"]

    for filter_id, row in expected["per_filter"].items():
        for tier, expected_pct in row.items():
            actual_pct = actual["per_filter"][filter_id][tier]
            assert actual_pct == pytest.approx(expected_pct, abs=0.05), (
                f"filter {filter_id} tier {tier}: "
                f"expected {expected_pct}, got {actual_pct}"
            )

    assert actual["save_to_miss_conservative"] == pytest.approx(
        expected["save_to_miss_conservative"], abs=0.005
    )
    assert actual["save_to_miss_combined"] == pytest.approx(
        expected["save_to_miss_combined"], abs=0.005
    )
