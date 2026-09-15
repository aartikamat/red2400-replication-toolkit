"""Property / invariance tests for the event-keyed classifier.

Covered invariants (per Phase B of the P5 audit):

- Row-order invariance: permuting the row order of rejections or outcomes
  must not change the per-event tier attribution.
- Duplicate-row idempotence: duplicating outcome rows must not change tier
  attribution (unless duplication itself moves the reference sample, which
  is documented behavior — the test exercises the safe case).
- Event isolation: an outcome row bound to event A must never influence
  event B's classification.
- Deterministic seeds: no seeded randomness is used in classification, so
  repeated runs must produce byte-identical outputs.
- Timestamp normalization idempotence: parsing an ISO string, formatting
  it, and re-parsing must round-trip.
- Timestamp equivalence: multiple ISO representations of the same instant
  must produce the same event_id.
- Schema validation: missing columns fail loudly, not silently.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pandas as pd
import pytest

from red2400_toolkit import (
    classify_dataset,
    compute_event_id,
    load_deposit,
    parse_timestamp_to_ms,
)


RNG = random.Random(20260821)


def _load(fixture_dir):
    return load_deposit(fixture_dir)


def _clean_classify(fixture_dir):
    d = _load(fixture_dir)
    return classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )


def test_row_order_invariance_on_adversarial(adversarial_deposit):
    d = _load(adversarial_deposit)
    baseline = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Shuffle rejections and outcomes independently.
    rej_shuf = d.rejections.sample(frac=1.0, random_state=42).reset_index(drop=True)
    out_shuf = d.rejection_outcomes.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuffled = classify_dataset(
        rejections=rej_shuf,
        rejection_outcomes=out_shuf,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Same event_id set and same tier per event.
    assert set(baseline.index) == set(shuffled.index)
    for eid in baseline.index:
        assert baseline.loc[eid, "tier"] == shuffled.loc[eid, "tier"], (
            f"row-order invariance violated for event {eid}"
        )


def test_deterministic_repeated_runs(adversarial_deposit):
    a = _clean_classify(adversarial_deposit)
    b = _clean_classify(adversarial_deposit)
    # Sort by index because pandas may not guarantee a global row order.
    a_sorted = a.sort_index()
    b_sorted = b.sort_index()
    pd.testing.assert_frame_equal(a_sorted, b_sorted)


def test_duplicate_outcome_rows_do_not_change_tier(adversarial_deposit):
    d = _load(adversarial_deposit)
    baseline = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Duplicate every outcome row exactly once. Since duplication is
    # symmetric across events (each event's samples double), the min/max
    # ratio and tier decision cannot change.
    dup = pd.concat([d.rejection_outcomes, d.rejection_outcomes], ignore_index=True)
    duped = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=dup,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    for eid in baseline.index:
        assert baseline.loc[eid, "tier"] == duped.loc[eid, "tier"], (
            f"tier changed for event {eid} when outcome rows were duplicated"
        )


def test_event_isolation_extra_row_for_other_event_does_not_perturb(adversarial_deposit):
    """Inject an outcome row bound to M_ORPHAN's event; the tiers of every
    OTHER event must be unchanged. Only the orphan is affected.
    """
    d = _load(adversarial_deposit)
    baseline = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    orphan_row = pd.DataFrame([{
        "sampleTs": "2026-04-11T13:01:00.000Z",
        "mint": "M_ORPHAN",
        "symbol": "Z",
        "rejectReason": "filter_J",
        "rejectTs": "2026-04-11T13:00:00.000Z",
        "ageMin": 1,
        "priceUsd": 1.0,
        "liquidity": 100.0,
        "volume24h": 1000.0,
        "dexId": "pumpswap",
        "pairAddress": "PJ",
    }])
    augmented_out = pd.concat([d.rejection_outcomes, orphan_row], ignore_index=True)
    augmented = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=augmented_out,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    orphan_eid = compute_event_id(
        "M_ORPHAN",
        parse_timestamp_to_ms("2026-04-11T13:00:00.000Z"),
        "filter_J",
    )
    # Every other event's tier is unchanged.
    for eid in baseline.index:
        if eid == orphan_eid:
            continue
        assert baseline.loc[eid, "tier"] == augmented.loc[eid, "tier"], (
            f"event {eid} tier moved when a row was added for a DIFFERENT event"
        )
    # The orphan now has a sample and, given no missed/saved trigger in
    # its single sample, flips from unclassifiable to flat.
    assert baseline.loc[orphan_eid, "tier"] == "unclassifiable"
    assert augmented.loc[orphan_eid, "tier"] == "flat"


def test_timestamp_representation_equivalence():
    """Multiple ISO representations of the same instant produce the same
    event_id. This is the P11 timestamp-normalization invariant.
    """
    forms = [
        "2026-04-10T21:10:13.000Z",
        "2026-04-10T21:10:13.000+00:00",
        "2026-04-10T23:10:13.000+02:00",  # +02:00 == 21:10 UTC
    ]
    ids = {compute_event_id("M", parse_timestamp_to_ms(f), "r") for f in forms}
    assert len(ids) == 1, f"timestamp forms produced different event_ids: {ids}"


def test_timestamp_normalization_roundtrip():
    """ISO -> ms -> ISO -> ms round-trip must be stable at millisecond
    granularity.
    """
    a = parse_timestamp_to_ms("2026-04-10T21:10:13.123Z")
    iso = datetime.fromtimestamp(a / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")
    b = parse_timestamp_to_ms(iso)
    assert a == b


def test_schema_missing_column_fails_loudly():
    from red2400_toolkit.red2400_loader import SchemaError, load_deposit
    # Build a tmp dir with a bad rejections.csv missing 'timestamp'.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        pd.DataFrame({
            "source": ["s"], "mint": ["M"], "symbol": ["S"],
            "reason": ["r"], "timeSlot": ["n"],
        }).to_csv(p / "rejections.csv", index=False)
        pd.DataFrame({
            "sampleTs": [], "mint": [], "symbol": [], "rejectReason": [],
            "rejectTs": [], "ageMin": [], "priceUsd": [], "liquidity": [],
            "volume24h": [], "dexId": [], "pairAddress": [],
        }).to_csv(p / "rejection_outcomes.csv", index=False)
        pd.DataFrame({
            "ts": [], "mint": [], "symbol": [], "from": [], "to": [],
            "liquidity": [], "ageDays": [],
        }).to_csv(p / "graveyard_lifecycle.csv", index=False)
        with pytest.raises(SchemaError):
            load_deposit(p)


def test_outcome_bound_to_wrong_event_id_is_ignored(adversarial_deposit):
    """If an outcome row's (rejectTs, rejectReason) don't match any
    rejection, its event_id has no rejection counterpart — the row
    becomes an *orphan outcome* and is reported by the diagnostic,
    but does not silently pool into any event.
    """
    d = _load(adversarial_deposit)
    ghost_row = pd.DataFrame([{
        "sampleTs": "2026-05-01T00:00:00.000Z",
        "mint": "M_REPEAT",
        "symbol": "R",
        "rejectReason": "filter_ZZZ_NONEXISTENT",
        "rejectTs": "2026-05-01T00:00:00.000Z",
        "ageMin": 1,
        "priceUsd": 999.0,  # would be catastrophic if pooled into M_REPEAT
        "liquidity": 100.0,
        "volume24h": 1000.0,
        "dexId": "pumpswap",
        "pairAddress": "PGHOST",
    }])
    augmented_out = pd.concat([d.rejection_outcomes, ghost_row], ignore_index=True)
    baseline = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=d.rejection_outcomes,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    augmented = classify_dataset(
        rejections=d.rejections,
        rejection_outcomes=augmented_out,
        graveyard_lifecycle=d.graveyard_lifecycle,
        on_missing="quarantine",
    )
    # Ghost row bound to a nonexistent event_id must not pool into
    # M_REPEAT — every M_REPEAT event's tier must be unchanged.
    for eid, row in baseline.iterrows():
        if row["mint"] != "M_REPEAT":
            continue
        assert baseline.loc[eid, "tier"] == augmented.loc[eid, "tier"], (
            "orphan outcome pooled silently into M_REPEAT"
        )
