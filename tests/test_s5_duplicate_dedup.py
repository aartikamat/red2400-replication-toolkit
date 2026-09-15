"""S5 regression tests — exact-key duplicate outcome rows.

S5: duplicate outcome rows silently inflated ``n_samples_in_window``
and ``LinkageDiagnostic.n_outcome_rows`` in v2.0.0. v2.0.1 collapses
them on ``(event_id, sampleTs, dexId, pairAddress)`` before grouping
and surfaces the collapsed count on the diagnostic.

Coverage:
- Idempotent dedup on synthetic duplicated rows.
- ``n_duplicate_outcome_rows`` populated on the diagnostic.
- ``allow_duplicate_samples=True`` preserves duplicates and warns.
- Adversarial fixture with 3-fold exact-copies collapses to 1.
"""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from red2400_toolkit import (
    attach_event_ids,
    attach_outcomes_by_event,
    classify_dataset,
    load_deposit,
)


def _mkrej(mint: str, ts: str, reason: str) -> dict:
    return {
        "timestamp": ts, "source": "s", "mint": mint,
        "symbol": mint, "reason": reason, "timeSlot": "normal",
    }


def _mkout(mint: str, reject_ts: str, sample_ts: str, reason: str,
           age_min: float, price: float, dex: str = "pumpswap",
           pair: str = "P1") -> dict:
    return {
        "sampleTs": sample_ts, "mint": mint, "symbol": mint,
        "rejectReason": reason, "rejectTs": reject_ts,
        "ageMin": age_min, "priceUsd": price, "liquidity": 100.0,
        "volume24h": 1000.0, "dexId": dex, "pairAddress": pair,
    }


# ---------------------------------------------------------------------------
# S5 T1 — dedup collapses exact-key duplicates
# ---------------------------------------------------------------------------

def test_attach_outcomes_by_event_dedupes_exact_sample_key():
    rej = pd.DataFrame([_mkrej("M1", "2026-04-10T21:10:13.000Z", "filter_1")])
    out = pd.DataFrame([
        _mkout("M1", "2026-04-10T21:10:13.000Z",
               "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0),
        # exact duplicate (same event_id, sampleTs, dexId, pairAddress)
        _mkout("M1", "2026-04-10T21:10:13.000Z",
               "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0),
        # legit second sample at a different sampleTs
        _mkout("M1", "2026-04-10T21:10:13.000Z",
               "2026-04-10T22:10:13.000Z", "filter_1", 60, 3.0),
    ])
    rej = attach_event_ids(rej, mint_col="mint", ts_col="timestamp", reason_col="reason")
    out = attach_event_ids(out, mint_col="mint", ts_col="rejectTs",
                           reason_col="rejectReason", on_error="quarantine")
    grouped, diag = attach_outcomes_by_event(rej, out, on_missing="raise",
                                             warn_on_orphans=False)
    assert diag.n_duplicate_outcome_rows == 1, (
        f"expected 1 duplicate collapsed, got {diag.n_duplicate_outcome_rows}"
    )
    # Only 2 rows remain for the event (1 dropped, 2 kept)
    (event_id, samples), = grouped.items()
    assert len(samples) == 2


# ---------------------------------------------------------------------------
# S5 T2 — n_samples_in_window unchanged by duplicate rows
# ---------------------------------------------------------------------------

def test_duplicate_outcome_rows_do_not_change_n_samples_in_window():
    rej = pd.DataFrame([_mkrej("M2", "2026-04-10T21:10:13.000Z", "filter_1")])
    out_a = pd.DataFrame([
        _mkout("M2", "2026-04-10T21:10:13.000Z",
               "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0),
        _mkout("M2", "2026-04-10T21:10:13.000Z",
               "2026-04-10T22:10:13.000Z", "filter_1", 60, 0.3),
    ])
    out_b = pd.concat([out_a, out_a], ignore_index=True)  # exact dup each row
    cls_a = classify_dataset(rej, out_a, graveyard_lifecycle=None,
                             on_missing="quarantine")
    cls_b = classify_dataset(rej, out_b, graveyard_lifecycle=None,
                             on_missing="quarantine")
    assert cls_a.iloc[0]["n_samples_in_window"] == 2
    assert cls_b.iloc[0]["n_samples_in_window"] == 2, (
        "duplicate outcome rows must not inflate n_samples_in_window"
    )
    assert cls_a.iloc[0]["tier"] == cls_b.iloc[0]["tier"]


# ---------------------------------------------------------------------------
# S5 T3 — allow_duplicate_samples=True preserves duplicates and warns
# ---------------------------------------------------------------------------

def test_allow_duplicate_samples_reproduces_pre_s5_behavior_and_warns():
    rej = pd.DataFrame([_mkrej("M3", "2026-04-10T21:10:13.000Z", "filter_1")])
    out = pd.DataFrame([
        _mkout("M3", "2026-04-10T21:10:13.000Z",
               "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0),
        _mkout("M3", "2026-04-10T21:10:13.000Z",
               "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0),
    ])
    rej = attach_event_ids(rej, mint_col="mint", ts_col="timestamp", reason_col="reason")
    out = attach_event_ids(out, mint_col="mint", ts_col="rejectTs",
                           reason_col="rejectReason", on_error="quarantine")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        grouped, diag = attach_outcomes_by_event(
            rej, out, on_missing="raise", warn_on_orphans=False,
            allow_duplicate_samples=True,
        )
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "allow_duplicate_samples=True must emit DeprecationWarning"
    # Duplicates preserved
    (event_id, samples), = grouped.items()
    assert len(samples) == 2
    assert diag.n_duplicate_outcome_rows is None


# ---------------------------------------------------------------------------
# S5 T4 — adversarial 3-fold duplicate fixture
# ---------------------------------------------------------------------------

def test_adversarial_three_fold_exact_duplicate_collapses_to_one():
    rej = pd.DataFrame([_mkrej("MADV", "2026-04-10T21:10:13.000Z", "filter_1")])
    row = _mkout("MADV", "2026-04-10T21:10:13.000Z",
                 "2026-04-10T21:11:13.000Z", "filter_1", 1, 1.0)
    out = pd.DataFrame([row, row, row])
    rej = attach_event_ids(rej, mint_col="mint", ts_col="timestamp", reason_col="reason")
    out = attach_event_ids(out, mint_col="mint", ts_col="rejectTs",
                           reason_col="rejectReason", on_error="quarantine")
    grouped, diag = attach_outcomes_by_event(
        rej, out, on_missing="raise", warn_on_orphans=False,
    )
    assert diag.n_duplicate_outcome_rows == 2
    (event_id, samples), = grouped.items()
    assert len(samples) == 1
