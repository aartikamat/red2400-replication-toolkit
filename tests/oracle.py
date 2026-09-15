"""Independent oracle for the five-tier classifier.

Deliberately written from the paper's textual spec (§III.B of Kamat 2026)
without importing anything from ``red2400_toolkit``. This is the reference
comparison target for the adversarial-fixture tests — if this file and
``red2400_toolkit`` agree on the tier for a hand-crafted event, that is
independent evidence of correctness. If they disagree, one of the two is
wrong (and the debate can be adjudicated against the hand-worked expected
tables in ``test_oracle_hand_tables.py``).

Design constraints
------------------
- Zero imports from ``red2400_toolkit``. Only stdlib + pandas.
- Written in plain Python, no vectorization tricks — the goal is
  auditability, not speed.
- The event key is recomputed here from mint/rejectTs/rejectReason so the
  oracle would catch a bug where the toolkit's event_id derivation drifts.

Not exported
------------
This module is a test-support module. It is not shipped in the installable
package (``pyproject.toml`` only includes ``red2400_toolkit*``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple

import pandas as pd


# Locked spec constants — deliberately duplicated so a drift in the
# toolkit constants doesn't silently pass through here.
_ORACLE_EARLY_DEATH_AGE_MAX_MIN = 60
_ORACLE_SAVED_THRESHOLD = 0.5
_ORACLE_MISSED_THRESHOLD = 2.0
_ORACLE_OBSERVATION_WINDOW_MIN = 24 * 60

TIER_SAVED_WINDOWED = "saved_windowed"
TIER_SAVED_EARLY_DEATH = "saved_early_death"
TIER_FLAT = "flat"
TIER_MISSED = "missed"
TIER_UNCLASSIFIABLE = "unclassifiable"


def _oracle_parse_ts_to_ms(value) -> Optional[int]:
    """Independent ISO/int -> epoch-ms parser."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, bool):
        raise TypeError("boolean timestamp not supported")
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError("naive timestamp")
    dt = dt.astimezone(timezone.utc)
    whole = dt.replace(microsecond=0)
    return int(whole.timestamp()) * 1000 + (dt.microsecond // 1000)


def _oracle_event_id(mint: str, ts_ms: int, reason: str) -> str:
    payload = "event|" + str(mint) + "|" + str(int(ts_ms)) + "|" + str(reason).strip()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _oracle_classify_one(
    samples_for_event: pd.DataFrame,
    lifecycle_for_mint: Optional[pd.DataFrame],
) -> str:
    """Textual-spec classifier for one event's samples + lifecycle rows.

    Rules (paraphrased from §III.B):
      1. Reference price = priceUsd of the earliest in-window sample
         (smallest ageMin) that has a positive priceUsd.
      2. Restrict to samples with ageMin <= 1440 and priceUsd > 0.
      3. If any sample has priceUsd / reference >= MISSED_THRESHOLD -> missed.
         (missed tie-breaks over saved_windowed.)
      4. Else if any sample has priceUsd / reference <= SAVED_THRESHOLD ->
         saved_windowed.
      5. Else if lifecycle has a `to == "gone"` row with ageDays*1440 <= 60
         -> saved_early_death.
      6. Else if there is at least one valid in-window sample -> flat.
      7. Else -> unclassifiable.
    """
    if samples_for_event is None or len(samples_for_event) == 0:
        # No samples; only lifecycle-based classification is possible.
        return _oracle_lifecycle_only(lifecycle_for_mint)

    df = samples_for_event.dropna(subset=["ageMin", "priceUsd"]).copy()
    df = df[df["priceUsd"] > 0]
    df = df[df["ageMin"] <= _ORACLE_OBSERVATION_WINDOW_MIN]
    if len(df) == 0:
        return _oracle_lifecycle_only(lifecycle_for_mint)

    first = df.loc[df["ageMin"].idxmin()]
    ref = float(first["priceUsd"])
    if ref <= 0:
        return _oracle_lifecycle_only(lifecycle_for_mint)

    ratios = df["priceUsd"].astype(float) / ref
    if (ratios >= _ORACLE_MISSED_THRESHOLD).any():
        return TIER_MISSED
    if (ratios <= _ORACLE_SAVED_THRESHOLD).any():
        return TIER_SAVED_WINDOWED
    # No missed / saved trigger; check early-death then fall through.
    ed_tier = _oracle_lifecycle_only(lifecycle_for_mint)
    if ed_tier == TIER_SAVED_EARLY_DEATH:
        return TIER_SAVED_EARLY_DEATH
    return TIER_FLAT


def _oracle_lifecycle_only(lifecycle_for_mint: Optional[pd.DataFrame]) -> str:
    if lifecycle_for_mint is None or len(lifecycle_for_mint) == 0:
        return TIER_UNCLASSIFIABLE
    gone = lifecycle_for_mint[lifecycle_for_mint["to"] == "gone"]
    if len(gone) == 0:
        return TIER_UNCLASSIFIABLE
    earliest = gone.loc[gone["ageDays"].idxmin()]
    age_min = float(earliest["ageDays"]) * 1440.0
    if age_min <= _ORACLE_EARLY_DEATH_AGE_MAX_MIN:
        return TIER_SAVED_EARLY_DEATH
    return TIER_UNCLASSIFIABLE


def oracle_classify_dataset(
    rejections: pd.DataFrame,
    rejection_outcomes: pd.DataFrame,
    graveyard_lifecycle: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Event-keyed reference classification.

    Returns a DataFrame indexed by ``event_id`` with columns
    ``mint``, ``filter_id``, ``tier``. This is intentionally minimal — it
    exists to certify the tier decision, not to reproduce the full
    diagnostic payload of ``red2400_toolkit.classify_dataset``.
    """
    # Attach event_ids by hand.
    rej_events: list[Tuple[str, str, str]] = []
    for _, row in rejections.iterrows():
        ts_ms = _oracle_parse_ts_to_ms(row["timestamp"])
        reason = str(row["reason"]).strip()
        eid = _oracle_event_id(row["mint"], ts_ms, reason)
        rej_events.append((eid, row["mint"], reason, ts_ms))

    # Group outcomes by (mint, rejectTs_ms, rejectReason) -> event_id.
    outcome_records = []
    for _, row in rejection_outcomes.iterrows():
        try:
            ts_ms = _oracle_parse_ts_to_ms(row["rejectTs"])
            reason = str(row["rejectReason"]).strip()
        except Exception:
            continue
        eid = _oracle_event_id(row["mint"], ts_ms, reason)
        outcome_records.append({
            "event_id": eid,
            "ageMin": row.get("ageMin"),
            "priceUsd": row.get("priceUsd"),
            "liquidity": row.get("liquidity"),
        })
    out_df = pd.DataFrame(outcome_records)
    if len(out_df):
        out_by_event = {eid: g for eid, g in out_df.groupby("event_id")}
    else:
        out_by_event = {}

    if graveyard_lifecycle is not None and len(graveyard_lifecycle):
        lc_by_mint = {m: g for m, g in graveyard_lifecycle.groupby("mint")}
    else:
        lc_by_mint = {}

    rows = []
    for eid, mint, reason, ts_ms in rej_events:
        samples = out_by_event.get(eid)
        lc = lc_by_mint.get(mint)
        tier = _oracle_classify_one(samples, lc)
        rows.append({
            "event_id": eid,
            "mint": mint,
            "filter_id": reason,
            "tier": tier,
        })
    return pd.DataFrame.from_records(rows).set_index("event_id")


__all__ = [
    "TIER_SAVED_WINDOWED",
    "TIER_SAVED_EARLY_DEATH",
    "TIER_FLAT",
    "TIER_MISSED",
    "TIER_UNCLASSIFIABLE",
    "oracle_classify_dataset",
]
