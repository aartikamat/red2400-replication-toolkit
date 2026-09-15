"""Early-death matched comparison validator (§V.C of Kamat 2026).

v2 semantics
------------
The v2 ``classify_dataset`` returns an event-keyed DataFrame indexed by
``event_id`` with a ``mint`` column. Terminal-state attachment is by
mint (a mint has one death trajectory), but the comparison denominators
are per *event* — an event on a repeat mint contributes independently
to its tier cohort.

v2.0.1 additions (S2 — right-censoring correction)
---------------------------------------------------
- Mints not present in the lifecycle file are labelled ``unobserved``,
  not ``not_gone``. Absence from the lifecycle is right-censoring, not
  observed survival.
- Gone rates are computed on the *observed* denominator by default
  (``gone`` + ``alive_observed``); ``unobserved`` events are surfaced
  separately through ``early_death_censored_n`` and
  ``non_early_death_censored_n``.
- ``include_censored=True`` reproduces the v2.0.0 pre-S2 estimator and
  emits ``DeprecationWarning``.

Compares the rate of terminal ``gone`` lifecycle states between
(a) events classified as ``saved_early_death`` and (b) events not
classified as early-death. The published finding on the 2,400-event
subset was:

    early-death cohort:      48.9% gone-state rate
    non-early-death cohort:  57.6% gone-state rate

The v1.0.0 mint-keyed output collapsed multiple events on the same mint,
so v2 event-level numbers will not match v1.0.0 numbers exactly — this
is the intended correction, not a regression.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import pandas as pd

from .event_model import LEGACY_MINT_POOLED_MODE
from .prfs_classifier import TIER_SAVED_EARLY_DEATH


TERMINAL_GONE = "gone"
TERMINAL_ALIVE_OBSERVED = "alive_observed"
TERMINAL_UNOBSERVED = "unobserved"


@dataclass(frozen=True)
class MatchedComparisonResult:
    early_death_n: int
    early_death_gone_rate: float       # percentage 0-100
    non_early_death_n: int
    non_early_death_gone_rate: float
    rate_difference_pp: float          # percentage points (ed - non_ed)
    # v2.0.1 S2 fields — right-censoring disclosure
    early_death_censored_n: int = 0
    non_early_death_censored_n: int = 0
    censoring_note: str = "observed_denominator"
    include_censored: bool = False


def _observed_gone_rate(df: pd.DataFrame, include_censored: bool) -> float:
    """Return the gone-rate as a percentage against the observed denominator.

    Under the default (``include_censored=False``) rows labelled
    ``unobserved`` are excluded from both numerator and denominator. Under
    ``include_censored=True`` (pre-S2 behavior) they are counted as
    ``not_gone`` and included in the denominator.
    """
    if len(df) == 0:
        return float("nan")
    if include_censored:
        # v2.0.0 pre-S2 behavior: `unobserved` treated as `alive`.
        gone = (df["terminal_state_ever"] == TERMINAL_GONE).sum()
        return float(gone) / float(len(df)) * 100.0
    observed_mask = df["terminal_state_ever"].isin(
        (TERMINAL_GONE, TERMINAL_ALIVE_OBSERVED)
    )
    observed = df[observed_mask]
    if len(observed) == 0:
        return float("nan")
    gone = (observed["terminal_state_ever"] == TERMINAL_GONE).sum()
    return float(gone) / float(len(observed)) * 100.0


def _censored_count(df: pd.DataFrame) -> int:
    return int((df["terminal_state_ever"] == TERMINAL_UNOBSERVED).sum())


def matched_comparison(
    classifications: pd.DataFrame,
    graveyard_lifecycle: pd.DataFrame,
    allow_legacy: bool = False,
    *,
    include_censored: bool = False,
) -> MatchedComparisonResult:
    """Reproduce the §V.C matched comparison at the event level.

    Parameters
    ----------
    classifications : pd.DataFrame
        Output of `prfs_classifier.classify_dataset`. In v2 the frame is
        indexed by ``event_id`` and carries a ``mint`` column; each row is
        one rejection event. In LEGACY mode the frame is indexed by mint;
        this function handles both by joining on ``mint``.
    graveyard_lifecycle : pd.DataFrame
        The lifecycle file. Must contain ``mint`` and ``to`` columns. A mint
        is considered "gone" if it has ANY row with ``to == "gone"``.
    allow_legacy : bool
        If False (default) and the classifications frame is tagged as
        legacy mint-pooled, refuse the call — the resulting comparison
        would reproduce the v1.0.0 mint-collapse defect. Pass True only
        for auditing v1-era artifacts, and never label the output as a
        v2 event-level result.
    include_censored : bool, keyword-only
        (S2, v2.0.1.) When ``False`` (default), mints absent from the
        lifecycle file are labelled ``unobserved`` and excluded from the
        gone-rate denominator. Pass ``True`` to reproduce the v2.0.0
        pre-S2 estimator that treated unobserved mints as observed
        survivors; emits ``DeprecationWarning``.
    """
    frame_mode = classifications.attrs.get("mode")
    if frame_mode == LEGACY_MINT_POOLED_MODE and not allow_legacy:
        raise ValueError(
            "matched_comparison refuses a legacy mint-pooled "
            "classifications frame as a v2 event-level input. That frame "
            "reproduces the v1.0.0 mint-collapse defect. Pass "
            "allow_legacy=True only for auditing v1-era artifacts."
        )
    if include_censored:
        warnings.warn(
            "matched_comparison(include_censored=True) reproduces the v2.0.0 "
            "pre-S2 estimator; mints absent from the lifecycle file are "
            "counted as observed survivors, biasing the gone-rate downward. "
            "Use only for auditing pre-S2 artifacts.",
            DeprecationWarning,
            stacklevel=2,
        )

    if len(graveyard_lifecycle) == 0:
        # No lifecycle rows at all — every event is right-censored.
        observed_state = pd.Series(
            dtype="object",
            name="terminal_state_ever",
            index=pd.Index([], name="mint"),
        )
    else:
        observed_state = (
            graveyard_lifecycle
            .assign(_g=(graveyard_lifecycle["to"] == "gone").astype(int))
            .groupby("mint")["_g"].max()
            .map(lambda x: TERMINAL_GONE if x == 1 else TERMINAL_ALIVE_OBSERVED)
            .rename("terminal_state_ever")
        )

    # Choose the join key. Event-level (v2) frames carry ``mint`` as a
    # column; legacy frames carry it as the index name.
    if "mint" in classifications.columns:
        merged = classifications.merge(
            observed_state.reset_index(), on="mint", how="left"
        )
    else:
        merged = classifications.join(observed_state, how="left")

    # v2.0.1 S2: never-observed mints are `unobserved`, not `not_gone`.
    merged["terminal_state_ever"] = merged["terminal_state_ever"].fillna(
        TERMINAL_UNOBSERVED
    )

    ed = merged[merged["tier"] == TIER_SAVED_EARLY_DEATH]
    non_ed = merged[merged["tier"] != TIER_SAVED_EARLY_DEATH]

    ed_gone = _observed_gone_rate(ed, include_censored=include_censored)
    non_ed_gone = _observed_gone_rate(non_ed, include_censored=include_censored)

    return MatchedComparisonResult(
        early_death_n=len(ed),
        early_death_gone_rate=ed_gone,
        non_early_death_n=len(non_ed),
        non_early_death_gone_rate=non_ed_gone,
        rate_difference_pp=ed_gone - non_ed_gone,
        early_death_censored_n=_censored_count(ed),
        non_early_death_censored_n=_censored_count(non_ed),
        censoring_note=(
            "legacy_pre_s2_include_unobserved_as_alive"
            if include_censored else "observed_denominator"
        ),
        include_censored=include_censored,
    )
