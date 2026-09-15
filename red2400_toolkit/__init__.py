"""RED-2400 Replication Toolkit.

Reproducible filter-precision auditing of algorithmic DEX trading systems
against the RED-2400 public benchmark dataset.

Companion to:
    Kamat, A. U. (2026). Outcome-Classified Precision Auditing of Filter
    Rules in Algorithmic DEX Trading. SSRN 6638259.

v2 correction — event-keyed dispatch
------------------------------------
``classify_dataset`` in v1.0.0 pooled outcome rows by ``mint`` alone. See
``event_model.py`` and ``CHANGELOG.md`` (``[Unreleased] -- v2.0.0``
entry, "Scientific-correctness impact") for the corrected per-event
dispatch and migration notes.
"""

__version__ = "2.0.1"
__author__ = "Arati Uday Kamat"
__license__ = "MIT"

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
    compute_event_id,
    compute_sample_id,
    normalize_reason,
    parse_timestamp_to_ms,
    select_rejections_by_mode,
)
from .prfs_classifier import (
    ALL_TIERS,
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_FLAT,
    TIER_MISSED,
    TIER_UNCLASSIFIABLE,
    EARLY_DEATH_AGE_MAX_MIN,
    SAVED_THRESHOLD,
    MISSED_THRESHOLD,
    classify_event,
    classify_dataset,
)
from .red2400_loader import load_deposit, RED2400Deposit
from .audit_runner import run_audit, AuditResult, sensitivity_early_death_threshold
from .early_death_validator import matched_comparison

__all__ = [
    # event model
    "EventLinkageError",
    "LinkageDiagnostic",
    "LEGACY_MINT_POOLED_MODE",
    "MODE_EVENT",
    "MODE_FIRST_EVENT_PER_MINT",
    "MODE_LATEST_EVENT_PER_MINT",
    "MODE_MINT_SUMMARY",
    "MODE_LEGACY_MINT_POOLED",
    "VALID_MODES",
    "attach_event_ids",
    "attach_outcomes_by_event",
    "compute_event_id",
    "compute_sample_id",
    "normalize_reason",
    "parse_timestamp_to_ms",
    "select_rejections_by_mode",
    # tiers + thresholds
    "TIER_SAVED_WINDOWED",
    "TIER_SAVED_EARLY_DEATH",
    "TIER_FLAT",
    "TIER_MISSED",
    "TIER_UNCLASSIFIABLE",
    "EARLY_DEATH_AGE_MAX_MIN",
    "SAVED_THRESHOLD",
    "MISSED_THRESHOLD",
    "ALL_TIERS",
    # classifier + audit
    "classify_event",
    "classify_dataset",
    "load_deposit",
    "RED2400Deposit",
    "run_audit",
    "AuditResult",
    "sensitivity_early_death_threshold",
    "matched_comparison",
]
