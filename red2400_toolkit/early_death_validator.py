"""Early-death matched comparison validator (§V.C of Kamat 2026).

Compares the rate of terminal `gone` lifecycle states between (a) mints
classified as `saved_early_death` and (b) rejected mints NOT classified as
early-death. The published finding (on the 2,400-event subset) is:

    early-death cohort:      48.9% gone-state rate
    non-early-death cohort:  57.6% gone-state rate

This module reproduces that comparison on the cohort the toolkit was run on.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .prfs_classifier import TIER_SAVED_EARLY_DEATH


@dataclass(frozen=True)
class MatchedComparisonResult:
    early_death_n: int
    early_death_gone_rate: float       # percentage 0-100
    non_early_death_n: int
    non_early_death_gone_rate: float
    rate_difference_pp: float          # percentage points (ed - non_ed)


def _gone_rate(df: pd.DataFrame) -> float:
    if len(df) == 0:
        return float("nan")
    gone = (df["terminal_state_ever"] == "gone").sum()
    return float(gone) / float(len(df)) * 100.0


def matched_comparison(
    classifications: pd.DataFrame,
    graveyard_lifecycle: pd.DataFrame,
) -> MatchedComparisonResult:
    """Reproduce the §V.C matched comparison.

    Parameters
    ----------
    classifications : pd.DataFrame
        Output of `prfs_classifier.classify_dataset`. Indexed by `mint` with
        a `tier` column.
    graveyard_lifecycle : pd.DataFrame
        The lifecycle file. Must contain `mint` and `to` columns. A mint is
        considered "gone" if it has ANY row with `to == "gone"`.
    """
    # collapse to per-mint terminal indicator
    ever_gone = (
        graveyard_lifecycle.assign(_g=(graveyard_lifecycle["to"] == "gone").astype(int))
        .groupby("mint")["_g"].max()
        .map(lambda x: "gone" if x == 1 else "not_gone")
        .rename("terminal_state_ever")
    )

    merged = classifications.join(ever_gone, how="left")
    merged["terminal_state_ever"] = merged["terminal_state_ever"].fillna("not_gone")

    ed = merged[merged["tier"] == TIER_SAVED_EARLY_DEATH]
    non_ed = merged[merged["tier"] != TIER_SAVED_EARLY_DEATH]

    return MatchedComparisonResult(
        early_death_n=len(ed),
        early_death_gone_rate=_gone_rate(ed),
        non_early_death_n=len(non_ed),
        non_early_death_gone_rate=_gone_rate(non_ed),
        rate_difference_pp=_gone_rate(ed) - _gone_rate(non_ed),
    )
