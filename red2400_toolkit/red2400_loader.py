"""RED-2400 deposit loader and schema validator.

Loads the three CSV files from a local copy of the RED-2400 Zenodo deposit
(concept DOI 10.5281/zenodo.19989074) and validates the documented schema.

Expected files in the deposit directory:
    rejections.csv          one row per rejected event       (6 columns)
    rejection_outcomes.csv  forward sample stream per event  (12 columns)
    graveyard_lifecycle.csv lifecycle state-transitions      (7 columns)

Schemas are taken from the v2.1 deposit released April-May 2026.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


# --- documented column sets per RED-2400 v2.1 deposit ---
REJECTIONS_REQUIRED = (
    "timestamp",   # ISO8601 rejection timestamp
    "source",      # capture source (e.g. source_a, source_b)
    "mint",        # SPL mint address (primary key)
    "symbol",      # token symbol at rejection
    "reason",      # filter_1 .. filter_8
    "timeSlot",    # capture time-slot label (e.g. normal)
)

REJECTION_OUTCOMES_REQUIRED = (
    "sampleTs",      # ISO8601 sample timestamp
    "mint",          # foreign key to rejections.mint
    "symbol",
    "rejectReason",  # mirrors rejections.reason
    "rejectTs",      # ISO8601 rejection timestamp (denormalized)
    "ageMin",        # minutes elapsed from rejection to sample
    "priceUsd",      # spot price at sample
    "liquidity",     # pool liquidity at sample
    "volume24h",
    "dexId",         # pumpswap / meteora / raydium / pumpfun / ...
    "pairAddress",
)
# `source` column also appears at the end of outcomes but is frequently empty
# in the v2.1 deposit; treated as optional.

GRAVEYARD_LIFECYCLE_REQUIRED = (
    "ts",         # ISO8601 transition timestamp
    "mint",       # foreign key to rejections.mint
    "symbol",
    "from",       # prior state (blank for initial transition)
    "to",         # new state: alive_active / alive_dormant / gone
    "liquidity",  # liquidity at transition
    "ageDays",    # age (in days) at transition
)

TERMINAL_STATE = "gone"  # the terminal lifecycle state


class SchemaError(ValueError):
    """Raised when a deposit file is missing required columns."""


@dataclass(frozen=True)
class RED2400Deposit:
    """In-memory handle to the three RED-2400 deposit files."""

    rejections: pd.DataFrame
    rejection_outcomes: pd.DataFrame
    graveyard_lifecycle: pd.DataFrame
    source_dir: Path

    @property
    def n_rejections(self) -> int:
        return len(self.rejections)

    @property
    def n_samples(self) -> int:
        return len(self.rejection_outcomes)

    @property
    def n_lifecycle(self) -> int:
        return len(self.graveyard_lifecycle)


def _require_columns(df: pd.DataFrame, required: Iterable[str], filename: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(
            f"{filename} is missing required columns: {missing}. "
            f"Present columns: {list(df.columns)}"
        )


def load_deposit(deposit_dir: str | Path) -> RED2400Deposit:
    """Load and validate the three deposit files.

    Parameters
    ----------
    deposit_dir : str or Path
        Path to a directory containing rejections.csv, rejection_outcomes.csv,
        and graveyard_lifecycle.csv.

    Returns
    -------
    RED2400Deposit
        Loaded deposit with all three dataframes attached.

    Raises
    ------
    FileNotFoundError
        If any of the three required files is missing.
    SchemaError
        If any required column is missing from any of the three files.
    """
    deposit_dir = Path(deposit_dir)
    if not deposit_dir.is_dir():
        raise FileNotFoundError(f"deposit_dir does not exist: {deposit_dir}")

    files = {
        "rejections.csv": REJECTIONS_REQUIRED,
        "rejection_outcomes.csv": REJECTION_OUTCOMES_REQUIRED,
        "graveyard_lifecycle.csv": GRAVEYARD_LIFECYCLE_REQUIRED,
    }
    frames: dict[str, pd.DataFrame] = {}
    for fname, required in files.items():
        fpath = deposit_dir / fname
        if not fpath.is_file():
            raise FileNotFoundError(f"missing required file: {fpath}")
        df = pd.read_csv(fpath, low_memory=False)
        _require_columns(df, required, fname)
        frames[fname] = df

    return RED2400Deposit(
        rejections=frames["rejections.csv"],
        rejection_outcomes=frames["rejection_outcomes.csv"],
        graveyard_lifecycle=frames["graveyard_lifecycle.csv"],
        source_dir=deposit_dir,
    )
