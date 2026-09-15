"""Post-Rejection Follow-up Sampling (PRFS) five-tier classifier.

Implements the classification rule from §III.B of Kamat (2026), including
the missed-over-saved tie-break precedence.

Event-keyed dispatch (v2 correction)
------------------------------------
`classify_dataset` in v1.0.0 grouped outcome rows by `mint` alone. Because
95.5% of RED-2400 v2 events live on mints that were rejected more than once,
that dispatch silently pooled overlapping per-mint trajectories into every
event. The v2 dispatch attaches outcomes by the P11 canonical
``event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" +
rejectReason).hexdigest()[:16]`` so each event sees only its own forward
samples. See `event_model.py` for the spec.

Schema notes (RED-2400 v2.1 deposit)
------------------------------------
- Rejections key columns: ``mint`` (string SPL mint address) plus
  ``timestamp`` (ISO-8601 rejection time) plus ``reason`` (filter label).
- Outcomes key columns: ``mint`` plus ``rejectTs`` plus ``rejectReason``
  (both present in the deposit schema per `red2400_loader`). These are
  what event_id is computed from.
- Reference price: NOT stored in rejections. By default we take the earliest
  forward sample's ``priceUsd`` (smallest ``ageMin``) as the reference for
  the ratio computation. Pass ``reference_price_mode="liquidity_proxy"`` to
  use liquidity instead (for the §V.D robustness check).
- Outcome window column: ``ageMin`` (MINUTES). 24h window = 1440.
- Lifecycle terminal state: row with ``to == "gone"``. Early-death gate uses
  ``ageDays <= 60/1440``.

Tier definitions
----------------
saved_windowed
    Forward sample stream contains at least one observation with price ratio
    (sample_price / reference_price) at or below SAVED_THRESHOLD within the
    24h observation window, and no observation triggers the missed tier
    by the tie-break precedence.

saved_early_death
    The mint reached the ``gone`` terminal state at an age below
    EARLY_DEATH_AGE_MAX_MIN minutes, and no saved_windowed or missed
    observation triggered before termination.

missed
    Forward sample stream contains at least one observation with price ratio
    at or above MISSED_THRESHOLD within the 24h window. This tier dominates
    saved_windowed under the documented tie-break precedence.

flat
    No saved/missed/early_death conditions met but the event has at least
    one valid forward sample within the window.

unclassifiable
    The event has no valid forward samples within the window and no terminal
    lifecycle transition to apply the early-death tier.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .event_model import (
    EventLinkageError,
    LinkageDiagnostic,
    LEGACY_MINT_POOLED_MODE,
    MODE_EVENT,
    MODE_FIRST_EVENT_PER_MINT,
    MODE_LATEST_EVENT_PER_MINT,
    MODE_MINT_SUMMARY,
    MODE_LEGACY_MINT_POOLED,
    VALID_MODES,
    attach_event_ids,
    attach_outcomes_by_event,
    select_rejections_by_mode,
)


# Tier string constants
TIER_SAVED_WINDOWED = "saved_windowed"
TIER_SAVED_EARLY_DEATH = "saved_early_death"
TIER_FLAT = "flat"
TIER_MISSED = "missed"
TIER_UNCLASSIFIABLE = "unclassifiable"

# Classification thresholds (locked to deposited audit script)
EARLY_DEATH_AGE_MAX_MIN = 60       # minutes
SAVED_THRESHOLD = 0.5              # forward / reference <= 0.5 => saved
MISSED_THRESHOLD = 2.0             # forward / reference >= 2.0 => missed
OBSERVATION_WINDOW_MIN = 24 * 60   # 24h in minutes (deposit's ``ageMin`` units)

ALL_TIERS = (
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_FLAT,
    TIER_MISSED,
    TIER_UNCLASSIFIABLE,
)


@dataclass(frozen=True)
class ClassificationDetail:
    """Diagnostic payload for one event's classification decision.

    Notes on the new v2.0.1 disclosure fields:

    - ``first_sample_lag_min``: the ageMin of the earliest usable forward
      sample the extractor caught for this event. This is the S1
      scope-out disclosure: the reference price is the price at this
      lag, NOT the price at the rejection instant, so a non-zero lag
      is an upper bound on the reference-price bias affecting
      ``min_ratio`` and ``max_ratio``. Populated only when a reference
      price could be extracted; ``None`` for unclassifiable events.
    - ``early_death_age_min_note``: the semantics of
      ``early_death_age_min``. Currently the only populated value is
      ``"upper_bound"`` (S3 scope-out): the recorded ``ageDays`` is the
      age at which the transition to ``gone`` was **observed** by the
      tracker, which is an upper bound on the true age at death. The
      interval bracketing the true event is not reconstructable from
      the deposit alone. ``None`` when no ``gone`` transition was
      recorded for the mint.
    """

    tier: str
    n_samples_in_window: int
    reference_price: Optional[float]
    min_ratio: Optional[float]
    max_ratio: Optional[float]
    early_death_age_min: Optional[float]
    early_death_terminal: Optional[str]
    # v2.0.1 scope-out disclosures (S1, S3)
    first_sample_lag_min: Optional[float] = None
    early_death_age_min_note: Optional[str] = None


def _extract_reference(samples: pd.DataFrame, mode: str) -> Optional[float]:
    """Return the reference baseline for the ratio computation.

    mode = "first_sample_price"  -> priceUsd at smallest ageMin
    mode = "liquidity_proxy"     -> liquidity at smallest ageMin (robustness)

    Note (S1 scope-out): the reference is anchored at the earliest
    forward sample the extractor caught, not at the rejection instant.
    Any non-zero ``ageMin`` on that first row is a lag that biases the
    downstream ratio toward 1 by an unknown amount. The
    ``_first_sample_lag_min`` helper surfaces that lag so callers can
    quantify a lower bound on the bias.
    """
    if len(samples) == 0:
        return None
    col = "priceUsd" if mode == "first_sample_price" else "liquidity"
    if col not in samples.columns:
        return None
    s = samples.dropna(subset=["ageMin", col])
    if len(s) == 0:
        return None
    first_row = s.loc[s["ageMin"].idxmin()]
    val = first_row[col]
    if val is None or pd.isna(val) or float(val) <= 0:
        return None
    return float(val)


def _first_sample_lag_min(samples: pd.DataFrame, mode: str) -> Optional[float]:
    """Return the ``ageMin`` of the reference-price row (S1 disclosure).

    Returns ``None`` when no valid reference row exists (matches the
    ``None``-return contract of ``_extract_reference``). Otherwise
    returns the same ``ageMin`` value the classifier used to anchor
    ratios. The scientific interpretation: this is the earliest lag at
    which the extractor caught the event; anything above ~5 minutes
    materially biases the reference on fast-moving tokens.
    """
    if len(samples) == 0:
        return None
    col = "priceUsd" if mode == "first_sample_price" else "liquidity"
    if col not in samples.columns:
        return None
    s = samples.dropna(subset=["ageMin", col])
    if len(s) == 0:
        return None
    first_row = s.loc[s["ageMin"].idxmin()]
    val = first_row[col]
    if val is None or pd.isna(val) or float(val) <= 0:
        return None
    return float(first_row["ageMin"])


def classify_event(
    samples: pd.DataFrame,
    lifecycle_rows: Optional[pd.DataFrame] = None,
    reference_price_mode: str = "first_sample_price",
) -> ClassificationDetail:
    """Classify a single rejection event's outcome.

    Parameters
    ----------
    samples : pd.DataFrame
        Forward sample rows for this *event* (not this mint). Required
        columns: ``ageMin``, ``priceUsd``. Empty / no-baseline falls through
        to early-death (if lifecycle rows provided) or unclassifiable.
    lifecycle_rows : pd.DataFrame or None
        Lifecycle rows for the mint. The earliest row with ``to == "gone"``
        is used for the early-death gate.
    reference_price_mode : {"first_sample_price", "liquidity_proxy"}
    """
    reference = _extract_reference(samples, reference_price_mode)

    # restrict samples to the 24h observation window
    in_window = pd.DataFrame()
    if reference is not None and len(samples) > 0:
        col = "priceUsd" if reference_price_mode == "first_sample_price" else "liquidity"
        in_window = samples[
            (samples["ageMin"] <= OBSERVATION_WINDOW_MIN)
            & samples[col].notna()
            & (samples[col].astype(float) > 0)
        ]
    n = len(in_window)

    min_ratio: Optional[float] = None
    max_ratio: Optional[float] = None
    if n > 0 and reference is not None:
        col = "priceUsd" if reference_price_mode == "first_sample_price" else "liquidity"
        ratios = in_window[col].astype(float) / reference
        min_ratio = float(ratios.min())
        max_ratio = float(ratios.max())

    # early-death check from lifecycle: earliest "gone" transition.
    #
    # S3 disclosure: ed_age_min is the age at which the transition to
    # "gone" was OBSERVED by the tracker, which is an upper bound on the
    # true age at death (probe cadence and interval left-endpoints are
    # not carried by the deposit). The ``early_death_age_min_note``
    # field labels this semantics on the returned ClassificationDetail.
    ed_age_min: Optional[float] = None
    ed_terminal: Optional[str] = None
    ed_note: Optional[str] = None
    if lifecycle_rows is not None and len(lifecycle_rows) > 0:
        gone = lifecycle_rows[lifecycle_rows["to"] == "gone"]
        if len(gone) > 0:
            earliest_gone = gone.loc[gone["ageDays"].idxmin()]
            ed_age_min = float(earliest_gone["ageDays"]) * 1440.0  # days -> min
            ed_terminal = "gone"
            ed_note = "upper_bound"

    # tie-break precedence: missed > saved_windowed
    missed_triggered = max_ratio is not None and max_ratio >= MISSED_THRESHOLD
    saved_w_triggered = min_ratio is not None and min_ratio <= SAVED_THRESHOLD

    if missed_triggered:
        tier = TIER_MISSED
    elif saved_w_triggered:
        tier = TIER_SAVED_WINDOWED
    elif ed_terminal == "gone" and ed_age_min is not None and ed_age_min <= EARLY_DEATH_AGE_MAX_MIN:
        tier = TIER_SAVED_EARLY_DEATH
    elif n > 0:
        tier = TIER_FLAT
    else:
        tier = TIER_UNCLASSIFIABLE

    lag_min = _first_sample_lag_min(samples, reference_price_mode)

    return ClassificationDetail(
        tier=tier,
        n_samples_in_window=n,
        reference_price=reference,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
        early_death_age_min=ed_age_min,
        early_death_terminal=ed_terminal,
        first_sample_lag_min=lag_min,
        early_death_age_min_note=ed_note,
    )


# ---------------------------------------------------------------------------
# Event-keyed dataset-level dispatch (v2 correction)
# ---------------------------------------------------------------------------

def _prepare_event_frames(
    rejections: pd.DataFrame,
    rejection_outcomes: pd.DataFrame,
    on_rejection_parse_error: str = "raise",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (rejections_with_event_id, outcomes_with_event_id).

    Column names are inherited from the RED-2400 v2.1 deposit
    (``rejections.timestamp/reason`` and ``outcomes.rejectTs/rejectReason``).

    Policy:
      - Rejection rows that fail to parse are a hard schema error by
        default (``on_rejection_parse_error='raise'``); pass 'quarantine'
        only for exploratory analysis of malformed inputs.
      - Outcome rows that fail to parse are ALWAYS quarantined (they
        become orphan-outcome rows with ``event_id=None`` and are
        excluded from event linkage). A production deposit ships with
        clean outcome timestamps; NaN outcome rejectTs signals an
        upstream extractor bug, not a per-event classification failure.
    """
    rej = attach_event_ids(
        rejections,
        mint_col="mint",
        ts_col="timestamp",
        reason_col="reason",
        on_error=on_rejection_parse_error,
    )
    out = attach_event_ids(
        rejection_outcomes,
        mint_col="mint",
        ts_col="rejectTs",
        reason_col="rejectReason",
        on_error="quarantine",
    )
    return rej, out


def classify_dataset(
    rejections: pd.DataFrame,
    rejection_outcomes: pd.DataFrame,
    graveyard_lifecycle: Optional[pd.DataFrame] = None,
    reference_price_mode: str = "first_sample_price",
    mode: str = MODE_EVENT,
    on_missing: str = "raise",
) -> pd.DataFrame:
    """Classify every rejection event in the deposit.

    Parameters
    ----------
    rejections, rejection_outcomes, graveyard_lifecycle
        Loaded deposit dataframes.
    reference_price_mode : {"first_sample_price", "liquidity_proxy"}
    mode : {"event", "first_event_per_mint", "latest_event_per_mint",
            "mint_summary", "mint_summary_LEGACY_defective"}
        Estimand selector. See `event_model.VALID_MODES`. The default is
        the correct per-event estimand; the LEGACY mode reproduces v1.0.0
        mint-pooled behavior for auditing v1-era artifacts and emits a
        loud warning.
    on_missing : {"raise", "quarantine"}
        Behavior when a rejection has no attachable outcome rows. Default
        "raise" — silent mint-pooling is what caused the v1.0.0 defect.

    Returns
    -------
    DataFrame indexed by ``event_id`` with columns:
        mint, filter_id, rejectTs_utc_ms, tier, n_samples_in_window,
        reference_price, min_ratio, max_ratio, early_death_age_min,
        early_death_terminal, mode.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}. Valid: {sorted(VALID_MODES)}")

    # Legacy mint-pooled path — preserved for auditing v1 artifacts only.
    if mode == MODE_LEGACY_MINT_POOLED:
        warnings.warn(
            "classify_dataset(mode='mint_summary_LEGACY_defective') reproduces "
            "the v1.0.0 mint-pooled dispatch. 95.5%% of RED-2400 v2 events live "
            "on repeat mints; outputs from this mode conflate per-event "
            "trajectories and MUST NOT be cited as event-level results. Use "
            "mode='event' for the corrected per-event estimand.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _classify_dataset_legacy_mint_pooled(
            rejections, rejection_outcomes, graveyard_lifecycle, reference_price_mode
        )

    rej, out = _prepare_event_frames(rejections, rejection_outcomes)
    rej_subset = select_rejections_by_mode(rej, mode)

    out_by_event, diag = attach_outcomes_by_event(
        rej_subset, out, on_missing=on_missing, warn_on_orphans=False,
    )
    # Prebuild lifecycle-by-mint. Lifecycle is naturally per-mint (a mint has
    # one death trajectory); we scope it to the events in the subset.
    if graveyard_lifecycle is not None and len(graveyard_lifecycle) > 0:
        lc_by_mint = {m: g for m, g in graveyard_lifecycle.groupby("mint")}
    else:
        lc_by_mint = {}

    records = []
    empty_samples = pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"])
    for _, row in rej_subset.iterrows():
        eid = row["event_id"]
        mint = row["mint"]
        samples = out_by_event.get(eid, empty_samples)
        lc = lc_by_mint.get(mint)
        det = classify_event(samples, lc, reference_price_mode=reference_price_mode)
        records.append({
            "event_id": eid,
            "mint": mint,
            "filter_id": row["reason"],
            "rejectTs_utc_ms": row["rejectTs_utc_ms"],
            "tier": det.tier,
            "n_samples_in_window": det.n_samples_in_window,
            "reference_price": det.reference_price,
            "min_ratio": det.min_ratio,
            "max_ratio": det.max_ratio,
            "early_death_age_min": det.early_death_age_min,
            "early_death_terminal": det.early_death_terminal,
            # v2.0.1 scope-out disclosures (S1, S3)
            "first_sample_lag_min": det.first_sample_lag_min,
            "early_death_age_min_note": det.early_death_age_min_note,
            "mode": mode,
        })

    df = pd.DataFrame.from_records(records).set_index("event_id")
    df.attrs["linkage_diagnostic"] = diag
    df.attrs["mode"] = mode
    return df


def _classify_dataset_legacy_mint_pooled(
    rejections: pd.DataFrame,
    rejection_outcomes: pd.DataFrame,
    graveyard_lifecycle: Optional[pd.DataFrame],
    reference_price_mode: str,
) -> pd.DataFrame:
    """Reproduce the v1.0.0 mint-keyed dispatch exactly.

    Retained ONLY so v1-era artifacts remain reproducible. Never call in
    scientific work — use ``mode='event'``.
    """
    out_by_mint = {m: g for m, g in rejection_outcomes.groupby("mint")}
    if graveyard_lifecycle is not None and len(graveyard_lifecycle) > 0:
        lc_by_mint = {m: g for m, g in graveyard_lifecycle.groupby("mint")}
    else:
        lc_by_mint = {}
    records = []
    for _, row in rejections.iterrows():
        mint = row["mint"]
        samples = out_by_mint.get(mint, pd.DataFrame(columns=["ageMin", "priceUsd", "liquidity"]))
        lc = lc_by_mint.get(mint)
        det = classify_event(samples, lc, reference_price_mode=reference_price_mode)
        records.append({
            "mint": mint,
            "filter_id": row["reason"],
            "tier": det.tier,
            "n_samples_in_window": det.n_samples_in_window,
            "reference_price": det.reference_price,
            "min_ratio": det.min_ratio,
            "max_ratio": det.max_ratio,
            "early_death_age_min": det.early_death_age_min,
            "early_death_terminal": det.early_death_terminal,
            # v2.0.1 scope-out disclosures (S1, S3)
            "first_sample_lag_min": det.first_sample_lag_min,
            "early_death_age_min_note": det.early_death_age_min_note,
            "mode": MODE_LEGACY_MINT_POOLED,
        })
    df = pd.DataFrame.from_records(records).set_index("mint")
    df.attrs["mode"] = MODE_LEGACY_MINT_POOLED
    return df
