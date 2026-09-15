"""Regenerate Figures 1 and 2 of the companion audit paper.

Figure 1: Age distribution of early-death-classified mints (histogram).
Figure 2: Sample cadence distribution (ageMin histogram over 24h window).

v2 downstream guard
-------------------
`figure_1_age_distribution` and `figure_2_sample_cadence` refuse to render
a legacy-mint-pooled classifications frame as if it were a corrected
event-level analysis. Pass ``allow_legacy=True`` to override — but never
label the resulting figure as a v2 event-level result.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .event_model import LEGACY_MINT_POOLED_MODE
from .prfs_classifier import TIER_SAVED_EARLY_DEATH, OBSERVATION_WINDOW_MIN


def _import_mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError as e:
        raise ImportError(
            "figure_generator requires matplotlib; install with "
            "`pip install red2400-toolkit[figures]`"
        ) from e


def _reject_legacy_frame(classifications: pd.DataFrame, allow_legacy: bool) -> None:
    """Refuse to render legacy-mint-pooled outputs as corrected figures."""
    frame_mode = classifications.attrs.get("mode")
    if frame_mode == LEGACY_MINT_POOLED_MODE and not allow_legacy:
        raise ValueError(
            "figure_generator refuses to render a legacy mint-pooled "
            "classifications frame as a v2 event-level figure. That frame "
            "reproduces the v1.0.0 mint-collapse defect (95.5% of RED-2400 "
            "v2 events live on repeat mints). If you must plot it for "
            "auditing v1-era artifacts, pass allow_legacy=True and label "
            "the figure explicitly as 'v1 defective (mint-pooled)'."
        )


def figure_1_age_distribution(
    classifications: pd.DataFrame,
    out_path: str | Path,
    bins: int = 30,
    allow_legacy: bool = False,
) -> Path:
    _reject_legacy_frame(classifications, allow_legacy)
    plt = _import_mpl()
    ed = classifications[classifications["tier"] == TIER_SAVED_EARLY_DEATH]
    ages = ed["early_death_age_min"].dropna()

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(ages, bins=bins, edgecolor="black", linewidth=0.5)
    ax.set_xlabel("Age at terminal state (minutes)")
    ax.set_ylabel("Count of early-death-classified mints")
    ax.set_title(f"Figure 1. Early-death age distribution (n={len(ages)})")
    fig.tight_layout()

    out_path = Path(out_path)
    fig.savefig(out_path, format="svg")
    plt.close(fig)
    return out_path


def figure_2_sample_cadence(
    rejection_outcomes: pd.DataFrame,
    out_path: str | Path,
    bins: int = 48,
) -> Path:
    # figure_2 operates on the raw outcome cadence table, not on a
    # classifications frame; there is no legacy-vs-event distinction at
    # this layer so no allow_legacy guard is needed.
    plt = _import_mpl()
    in_window = rejection_outcomes[rejection_outcomes["ageMin"] <= OBSERVATION_WINDOW_MIN]
    offsets = in_window["ageMin"].astype(float)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(offsets, bins=bins, edgecolor="black", linewidth=0.5)
    ax.set_xlabel("Sample offset from rejection (minutes)")
    ax.set_ylabel("Count of samples")
    ax.set_title(f"Figure 2. Sample cadence over 24h window (n={len(in_window)})")
    fig.tight_layout()

    out_path = Path(out_path)
    fig.savefig(out_path, format="svg")
    plt.close(fig)
    return out_path
