"""Post-Rejection Follow-up Sampling (PRFS) five-tier classifier.

Implements the classification rule from §III.B of Kamat (2026), including
the missed-over-saved tie-break precedence.

Schema notes (RED-2400 v2.1 deposit)
------------------------------------
- Rejections key column: `mint` (string SPL mint address)
- Reference price: NOT stored in rejections. By default we take the earliest
  forward sample's `priceUsd` (smallest `ageMin`) as the reference for the
  ratio computation. Pass `reference_price_mode="liquidity_proxy"` to use
  the liquidity at smallest `ageMin` instead (for the §V.D robustness check).
- Outcome window column: `ageMin` (MINUTES, not seconds). 24h window = 1440.
- Lifecycle terminal state: row with `to == "gone"`. Early-death gate uses
  `ageDays <= 60/1440` (60 min in days).

Tier definitions
----------------
saved_windowed
    Forward sample stream contains at least one observation with price ratio
    (sample_price / reference_price) at or below SAVED_THRESHOLD within the
    24h observation window, and no observation triggers the missed tier
    by the tie-break precedence.

saved_early_death
    The mint reached the `gone` terminal state at an age below
    EARLY_DEATH_AGE_MAX_MIN minutes, and no saved_windowed or missed
    observation triggered before termination.

missed
    Forward sample stream contains at least one observation with price ratio
    at or above MISSED_THRESHOLD within the 24h window. This tier dominates
    saved_windowed under the documented tie-break precedence.

flat
    No saved/missed/early_death conditions met but the mint has at least
    one valid forward sample within the window.

unclassifiable
    The mint has no valid forward samples within the window and no terminal
    lifecycle transition to apply the early-death tier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


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
OBSERVATION_WINDOW_MIN = 24 * 60   # 24h in minutes (deposit's `ageMin` units)

ALL_TIERS = (
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_FLAT,
    TIER_MISSED,
    TIER_UNCLASSIFIABLE,
)


@dataclass(frozen=True)
class ClassificationDetail:
    """Diagnostic payload for one event's classification decision."""

    tier: str
    n_samples_in_window: int
    reference_price: Optional[float]
    min_ratio: Optional[float]
    max_ratio: Optional[float]
    early_death_age_min: Optional[float]
    early_death_terminal: Optional[str]


def _extract_reference(samples: pd.DataFrame, mode: str) -> Optional[float]:
    """Return the reference baseline for the ratio computation.

    mode = "first_sample_price"  → priceUsd at smallest ageMin
    mode = "liquidity_proxy"     → liquidity at smallest ageMin (robustness)
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


def classify_event(
    samples: pd.DataFrame,
    lifecycle_rows: Optional[pd.DataFrame] = None,
    reference_price_mode: str = "first_sample_price",
) -> ClassificationDetail:
    """Classify a single rejected mint's outcome.

    Parameters
    ----------
    samples : pd.DataFrame
        Forward sample rows for one mint. Required columns: ageMin, priceUsd.
        Empty / no-baseline → falls through to early-death (if lifecycle rows
        provided) or unclassifiable.
    lifecycle_rows : pd.DataFrame or None
        Lifecycle rows for the same mint (may be multiple state transitions).
        The earliest row with `to == "gone"` is used for early-death.
    reference_price_mode : str
        Either "first_sample_price" (canonical) or "liquidity_proxy" (§V.D
        robustness).
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

    # early-death check from lifecycle: earliest "gone" transition
    ed_age_min: Optional[float] = None
    ed_terminal: Optional[str] = None
    if lifecycle_rows is not None and len(lifecycle_rows) > 0:
        gone = lifecycle_rows[lifecycle_rows["to"] == "gone"]
        if len(gone) > 0:
            earliest_gone = gone.loc[gone["ageDays"].idxmin()]
            ed_age_min = float(earliest_gone["ageDays"]) * 1440.0  # days → min
            ed_terminal = "gone"

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

    return ClassificationDetail(
        tier=tier,
        n_samples_in_window=n,
        reference_price=reference,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
        early_death_age_min=ed_age_min,
        early_death_terminal=ed_terminal,
    )


def classify_dataset(
    rejections: pd.DataFrame,
    rejection_outcomes: pd.DataFrame,
    graveyard_lifecycle: Optional[pd.DataFrame] = None,
    reference_price_mode: str = "first_sample_price",
) -> pd.DataFrame:
    """Classify every rejected event in the deposit.

    Returns a dataframe indexed by `mint` with columns:
        filter_id, tier, n_samples_in_window, reference_price,
        min_ratio, max_ratio, early_death_age_min, early_death_terminal
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
        })

    return pd.DataFrame.from_records(records).set_index("mint")
