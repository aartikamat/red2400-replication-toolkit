"""Figure-generation smoke tests."""

import pytest

pytest.importorskip("matplotlib")

from red2400_toolkit.figure_generator import (
    figure_1_age_distribution,
    figure_2_sample_cadence,
)
from red2400_toolkit.prfs_classifier import classify_dataset
from red2400_toolkit.red2400_loader import load_deposit


def test_fig1_writes_svg(synthetic_deposit, tmp_path):
    d = load_deposit(synthetic_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
    )
    out = figure_1_age_distribution(cls, tmp_path / "fig1.svg")
    assert out.is_file()
    assert out.read_text().startswith("<?xml")


def test_fig2_writes_svg(synthetic_deposit, tmp_path):
    d = load_deposit(synthetic_deposit)
    out = figure_2_sample_cadence(d.rejection_outcomes, tmp_path / "fig2.svg")
    assert out.is_file()
    assert out.read_text().startswith("<?xml")
