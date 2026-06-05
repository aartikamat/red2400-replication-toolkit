"""Audit runner — per-filter and aggregate save-to-miss reporting.

Produces the per-filter table and the aggregate save-to-miss ratios under
both conservative (windowed only) and combined (windowed + early-death)
interpretations.

Filter-level statistics for filters with n<30 (filter_8 in the current
deposit, n=19) carry wide uncertainty and should be interpreted with
caution; the toolkit reports raw frequencies without confidence intervals
as the canonical audit format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .prfs_classifier import (
    ALL_TIERS,
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_MISSED,
    classify_dataset,
)
from .red2400_loader import RED2400Deposit


@dataclass
class AuditResult:
    per_filter: pd.DataFrame
    overall: pd.Series
    save_to_miss_conservative: float
    save_to_miss_combined: float
    classifications: pd.DataFrame
    reference_price_mode: str

    def to_dict(self) -> dict:
        return {
            "n_rejections": int(self.overall["n"]),
            "reference_price_mode": self.reference_price_mode,
            "per_filter": self.per_filter.round(2).to_dict(orient="index"),
            "overall": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.overall.to_dict().items()},
            "save_to_miss_conservative": round(self.save_to_miss_conservative, 4),
            "save_to_miss_combined": round(self.save_to_miss_combined, 4),
        }


def _tier_table(classifications: pd.DataFrame, group_col: Optional[str]) -> pd.DataFrame:
    if group_col is None:
        counts = classifications["tier"].value_counts()
        n = int(counts.sum())
        pct = (counts / n * 100.0).reindex(ALL_TIERS, fill_value=0.0)
        s = pct.copy()
        s["n"] = n
        return s

    rows = []
    for group, sub in classifications.groupby(group_col):
        counts = sub["tier"].value_counts()
        n = int(counts.sum())
        pct = (counts / n * 100.0).reindex(ALL_TIERS, fill_value=0.0)
        rec = {"n": n, **pct.to_dict()}
        rec[group_col] = group
        rows.append(rec)
    df = pd.DataFrame.from_records(rows).set_index(group_col)
    return df[["n", *ALL_TIERS]]


def _save_to_miss(overall: pd.Series, combined: bool) -> float:
    missed = float(overall.get(TIER_MISSED, 0.0))
    saved_w = float(overall.get(TIER_SAVED_WINDOWED, 0.0))
    saved_ed = float(overall.get(TIER_SAVED_EARLY_DEATH, 0.0))
    numerator = saved_w + saved_ed if combined else saved_w
    if missed <= 0:
        return float("inf") if numerator > 0 else float("nan")
    return numerator / missed


def run_audit(
    deposit: RED2400Deposit,
    reference_price_mode: str = "first_sample_price",
) -> AuditResult:
    """Run the full audit pipeline.

    Parameters
    ----------
    deposit : RED2400Deposit
        Loaded deposit (from `load_deposit`).
    reference_price_mode : str
        "first_sample_price" (canonical) or "liquidity_proxy" (robustness).
    """
    classifications = classify_dataset(
        rejections=deposit.rejections,
        rejection_outcomes=deposit.rejection_outcomes,
        graveyard_lifecycle=deposit.graveyard_lifecycle,
        reference_price_mode=reference_price_mode,
    )

    per_filter = _tier_table(classifications, group_col="filter_id")
    overall = _tier_table(classifications, group_col=None)

    s2m_cons = _save_to_miss(overall, combined=False)
    s2m_comb = _save_to_miss(overall, combined=True)

    return AuditResult(
        per_filter=per_filter,
        overall=overall,
        save_to_miss_conservative=s2m_cons,
        save_to_miss_combined=s2m_comb,
        classifications=classifications,
        reference_price_mode=reference_price_mode,
    )
