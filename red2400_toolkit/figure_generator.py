"""Regenerate Figures 1 and 2 of the companion audit paper.

Figure 1: Age distribution of early-death-classified mints (histogram).
Figure 2: Sample cadence distribution (ageMin histogram over 24h window).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

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


def figure_1_age_distribution(
    classifications: pd.DataFrame,
    out_path: str | Path,
    bins: int = 30,
) -> Path:
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
