"""Defensive gates for v2.0.0 — verify ordinary users cannot land on the
defective v1 mint-pooled path by accident, and that downstream consumers
refuse a legacy-tagged classifications frame.

These tests sit next to the correctness gate; they intentionally use only
the public API so an accidental default change would trip them immediately.
"""

from __future__ import annotations

import inspect
import warnings

import pandas as pd
import pytest

from red2400_toolkit import (
    LEGACY_MINT_POOLED_MODE,
    MODE_EVENT,
    MODE_LEGACY_MINT_POOLED,
    classify_dataset,
    matched_comparison,
    run_audit,
)
from red2400_toolkit.figure_generator import figure_1_age_distribution
from red2400_toolkit.red2400_loader import RED2400Deposit


def test_classify_dataset_default_mode_is_event():
    """A caller who passes no ``mode`` must land on the corrected path."""
    sig = inspect.signature(classify_dataset)
    default = sig.parameters["mode"].default
    assert default == MODE_EVENT
    assert default != MODE_LEGACY_MINT_POOLED


def test_run_audit_default_mode_is_event():
    sig = inspect.signature(run_audit)
    default = sig.parameters["mode"].default
    assert default == MODE_EVENT
    assert default != MODE_LEGACY_MINT_POOLED


def test_legacy_mode_name_is_self_labelling():
    """The literal legacy mode name must carry a scary-enough token that
    an ordinary user cannot pass it without noticing what it means."""
    assert "LEGACY" in LEGACY_MINT_POOLED_MODE
    assert "defective" in LEGACY_MINT_POOLED_MODE


def _tiny_deposit(tmp_path):
    """One rejection, one outcome, one lifecycle row. Enough to exercise
    the classify → downstream-guard pipeline without a real deposit."""
    rejections = pd.DataFrame([{
        "timestamp": "2026-04-10T21:10:13.000Z",
        "source": "s", "mint": "M1", "symbol": "S", "reason": "f",
        "timeSlot": "normal",
    }])
    rejection_outcomes = pd.DataFrame([{
        "sampleTs": "2026-04-10T21:11:13.000Z", "mint": "M1", "symbol": "S",
        "rejectReason": "f", "rejectTs": "2026-04-10T21:10:13.000Z",
        "ageMin": 1, "priceUsd": 1.0, "liquidity": 100.0, "volume24h": 1000.0,
        "dexId": "pumpswap", "pairAddress": "P",
    }])
    graveyard = pd.DataFrame([{
        "ts": "2026-04-10T21:40:13.000Z", "mint": "M1", "symbol": "S",
        "from": "alive_active", "to": "gone", "liquidity": 0.0, "ageDays": 0.02,
    }])
    return rejections, rejection_outcomes, graveyard


def test_matched_comparison_refuses_legacy_frame(tmp_path):
    rej, out, gy = _tiny_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = classify_dataset(rej, out, gy, mode=MODE_LEGACY_MINT_POOLED)
    assert legacy.attrs["mode"] == MODE_LEGACY_MINT_POOLED
    with pytest.raises(ValueError, match="legacy mint-pooled"):
        matched_comparison(legacy, gy)
    # opt-in must work
    result = matched_comparison(legacy, gy, allow_legacy=True)
    assert result is not None


def test_figure_1_refuses_legacy_frame(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    rej, out, gy = _tiny_deposit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = classify_dataset(rej, out, gy, mode=MODE_LEGACY_MINT_POOLED)
    out_path = tmp_path / "fig1.svg"
    with pytest.raises(ValueError, match="legacy mint-pooled"):
        figure_1_age_distribution(legacy, out_path)
    # opt-in must work
    figure_1_age_distribution(legacy, out_path, allow_legacy=True)
    assert out_path.is_file()
