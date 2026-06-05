"""RED-2400 Replication Toolkit.

Reproducible filter-precision auditing of algorithmic DEX trading systems
against the RED-2400 public benchmark dataset.

Companion to:
    Kamat, A. U. (2026). Outcome-Classified Precision Auditing of Filter
    Rules in Algorithmic DEX Trading. SSRN 6638259.
"""

__version__ = "1.0.0"
__author__ = "Arati Uday Kamat"
__license__ = "MIT"

from .prfs_classifier import (
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_FLAT,
    TIER_MISSED,
    TIER_UNCLASSIFIABLE,
    EARLY_DEATH_AGE_MAX_MIN,
    SAVED_THRESHOLD,
    MISSED_THRESHOLD,
    classify_event,
)
from .red2400_loader import load_deposit, RED2400Deposit
from .audit_runner import run_audit, AuditResult
from .early_death_validator import matched_comparison

__all__ = [
    "TIER_SAVED_WINDOWED",
    "TIER_SAVED_EARLY_DEATH",
    "TIER_FLAT",
    "TIER_MISSED",
    "TIER_UNCLASSIFIABLE",
    "EARLY_DEATH_AGE_MAX_MIN",
    "SAVED_THRESHOLD",
    "MISSED_THRESHOLD",
    "classify_event",
    "load_deposit",
    "RED2400Deposit",
    "run_audit",
    "AuditResult",
    "matched_comparison",
]
