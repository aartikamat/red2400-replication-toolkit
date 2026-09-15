"""Event-level classification tests.

These tests are the load-bearing correctness gate for the v2 repair. Each
row in ``ADVERSARIAL_HAND_TABLE`` is a hand-computed expected tier for a
specific rejection event; the toolkit and the independent oracle must
both reproduce it. If either disagrees on any cell, the mint-collapse
defect (or a regression of it) is back.

The oracle lives at ``tests/oracle.py`` and is deliberately written
without importing ``red2400_toolkit`` — see that file's docstring.
"""

from __future__ import annotations

import pandas as pd
import pytest

from red2400_toolkit import (
    EventLinkageError,
    MODE_EVENT,
    MODE_LEGACY_MINT_POOLED,
    classify_dataset,
    compute_event_id,
    load_deposit,
    parse_timestamp_to_ms,
)

from .conftest import ADVERSARIAL_HAND_TABLE
from .oracle import oracle_classify_dataset


# ---------------------------------------------------------------------------
# 1. Toolkit vs hand-worked table on the adversarial deposit
# ---------------------------------------------------------------------------

def test_toolkit_matches_hand_table_on_adversarial_deposit(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Build (mint, timestamp, reason) -> event_id lookup so we compare
    # against the hand table without depending on internal indexing.
    rej = d.rejections
    for (mint, ts, reason), expected_tier in ADVERSARIAL_HAND_TABLE.items():
        ts_ms = parse_timestamp_to_ms(ts)
        eid = compute_event_id(mint, ts_ms, reason)
        assert eid in cls.index, (
            f"toolkit dropped event {(mint, ts, reason)} (eid={eid})"
        )
        actual = cls.loc[eid, "tier"]
        assert actual == expected_tier, (
            f"toolkit tier mismatch for {(mint, ts, reason)}: "
            f"expected {expected_tier}, got {actual}"
        )


def test_oracle_matches_hand_table_on_adversarial_deposit(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    cls = oracle_classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
    )
    for (mint, ts, reason), expected_tier in ADVERSARIAL_HAND_TABLE.items():
        ts_ms = parse_timestamp_to_ms(ts)
        eid = compute_event_id(mint, ts_ms, reason)
        assert eid in cls.index, f"oracle dropped event {(mint, ts, reason)}"
        actual = cls.loc[eid, "tier"]
        assert actual == expected_tier, (
            f"oracle tier mismatch for {(mint, ts, reason)}: "
            f"expected {expected_tier}, got {actual}"
        )


def test_toolkit_and_oracle_agree_on_every_event(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    toolkit_cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    oracle_cls = oracle_classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
    )
    common = toolkit_cls.index.intersection(oracle_cls.index)
    assert len(common) == len(toolkit_cls) == len(oracle_cls), (
        "toolkit and oracle produced different event_id sets"
    )
    for eid in common:
        a = toolkit_cls.loc[eid, "tier"]
        b = oracle_cls.loc[eid, "tier"]
        assert a == b, f"disagreement on {eid}: toolkit={a} oracle={b}"


# ---------------------------------------------------------------------------
# 2. Event isolation — the direct anti-defect test
# ---------------------------------------------------------------------------

def test_repeat_mint_gets_disjoint_tiers(adversarial_deposit):
    """M_REPEAT and M_IDENTICAL_TS both have two events with opposite
    trajectories. Under the v1 mint-pooled dispatch these would collapse.
    Under v2 event-keyed dispatch they must be distinct.
    """
    d = load_deposit(adversarial_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    for mint in ("M_REPEAT", "M_IDENTICAL_TS"):
        rows = cls[cls["mint"] == mint]
        assert len(rows) == 2, f"expected 2 events for {mint}, got {len(rows)}"
        tiers = set(rows["tier"])
        assert len(tiers) == 2, (
            f"{mint}: event-level dispatch collapsed to a single tier: {tiers}. "
            f"This is the mint-collapse defect."
        )


def test_legacy_mode_would_have_pooled(adversarial_deposit):
    """Sanity check: the legacy mint-pooled mode DOES collapse M_REPEAT to
    a single tier — this is the defect the v2 default fixes. If this
    assertion ever flips the legacy reproduction is broken.
    """
    import warnings
    d = load_deposit(adversarial_deposit)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        cls = classify_dataset(
            rejections=d.rejections,
            rejection_outcomes=d.rejection_outcomes,
            graveyard_lifecycle=d.graveyard_lifecycle,
            mode=MODE_LEGACY_MINT_POOLED,
        )
    # legacy frame is indexed by mint. M_REPEAT appears twice (once per
    # rejection row) with the same pooled tier.
    rep_rows = cls.loc[["M_REPEAT"]] if "M_REPEAT" in cls.index else pd.DataFrame()
    assert len(rep_rows) == 2, "legacy mode should keep both rejection rows"
    assert len(set(rep_rows["tier"])) == 1, (
        "legacy mode should produce a single pooled tier for both events "
        "of the same mint — that is the defect being preserved as a "
        "regression witness."
    )


# ---------------------------------------------------------------------------
# 3. Orphan handling — hard-fail path
# ---------------------------------------------------------------------------

def test_orphan_rejection_raises_when_on_missing_raise(adversarial_deposit):
    """M_ORPHAN has no matching outcome rows. Default on_missing='raise'
    must fail loudly; silent mint-pooling is what caused the defect.
    """
    d = load_deposit(adversarial_deposit)
    with pytest.raises(EventLinkageError):
        classify_dataset(
            rejections=d.rejections,
            rejection_outcomes=d.rejection_outcomes,
            graveyard_lifecycle=d.graveyard_lifecycle,
            on_missing="raise",
        )


def test_orphan_rejection_appears_as_unclassifiable_under_quarantine(adversarial_deposit):
    d = load_deposit(adversarial_deposit)
    cls = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    eid = compute_event_id(
        "M_ORPHAN",
        parse_timestamp_to_ms("2026-04-11T13:00:00.000Z"),
        "filter_J",
    )
    assert cls.loc[eid, "tier"] == "unclassifiable"


# ---------------------------------------------------------------------------
# 4. Estimand-mode determinism (event vs first vs latest vs mint_summary)
# ---------------------------------------------------------------------------

def test_estimand_modes_produce_expected_row_counts(adversarial_deposit):
    from red2400_toolkit import (
        MODE_FIRST_EVENT_PER_MINT,
        MODE_LATEST_EVENT_PER_MINT,
        MODE_MINT_SUMMARY,
    )
    d = load_deposit(adversarial_deposit)
    event = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    first = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        mode=MODE_FIRST_EVENT_PER_MINT,
        on_missing="quarantine",
    )
    latest = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        mode=MODE_LATEST_EVENT_PER_MINT,
        on_missing="quarantine",
    )
    summary = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        mode=MODE_MINT_SUMMARY,
        on_missing="quarantine",
    )
    # Event mode has 12 rejection events across 8 mints.
    assert len(event) == 12
    # Per-mint modes collapse to 8 rows (one per unique mint).
    assert len(first) == 8
    assert len(latest) == 8
    assert len(summary) == 8
    # First and latest must differ for at least one mint (M_REPEAT flips
    # from missed to saved_windowed between the two events).
    first_by_mint = first.set_index("mint")
    latest_by_mint = latest.set_index("mint")
    assert first_by_mint.loc["M_REPEAT", "tier"] != latest_by_mint.loc["M_REPEAT", "tier"]
