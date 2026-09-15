"""Canonical event/sample identity model.

Adopts the frozen P11 canonicalization spec for rejection-outcome corpora
(SHA-256 `14aed2189bfd2ba1...`; a bundled copy of the spec ships with the
release and is also archived on Zenodo).

Rationale
---------
`red2400_toolkit v1.0.0`'s `classify_dataset` grouped outcome rows by `mint`
alone. 95.5% of RED-2400 v2 events live on repeat mints, so nearly every
event received a pooled per-mint trajectory rather than its own event's
forward samples. This module supplies the correct identity primitives so
outcomes are attached per-event, not per-mint.

Event identity (frozen — P11 §5)
--------------------------------
``event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" +
             rejectReason_normalized).hexdigest()[:16]``

- ``mint``                    Solana mint public key, preserved verbatim.
- ``rejectTs_utc_ms``         Integer UTC epoch milliseconds. See
                              `parse_timestamp_to_ms` for the parse rules.
- ``rejectReason_normalized`` Whitespace-trimmed string. Case preserved.
- ``source`` / ``source_pseudonym`` is **not** part of the event key.
  Two source streams observing the same rejection = one event.

Sample identity (frozen — P11 §5, family_2 nulls preserved)
-----------------------------------------------------------
``sample_id = sha256("sample|" + event_id + "|" + sampleTs_utc_ms + "|" +
              (dexId or "null") + "|" + (pairAddress or "null"))
              .hexdigest()[:16]``

Missing / linkage policy
------------------------
- A rejection whose event_id matches zero outcome rows is an *orphan*.
  Callers choose between hard-fail (``on_missing='raise'``) and quarantine
  (``on_missing='quarantine'``); silent mint-pooling is not offered.
- An outcome row whose ``rejectTs``/``rejectReason`` cannot be parsed is
  itself quarantined with a diagnostic; it never falls through to a
  mint-only match.
- Duplicate exact-key rows are preserved (no collapsing) — the caller may
  choose downstream deduplication policy per estimand.

Timestamp policy
----------------
- ISO-8601 strings with trailing ``Z`` are treated as ``+00:00``.
- Sub-millisecond digits are truncated (not rounded).
- Integer inputs are assumed to be epoch milliseconds and copied verbatim.
- A string that fails to parse is quarantined with ``timestamp_parse_error``.

Reason policy
-------------
- Whitespace-trimmed; case is preserved.
- No enum coercion in this module — enum validation lives in the loader
  (``red2400_loader.REJECTIONS_REQUIRED``).
- Alias unification for family_2 (``reason`` → ``rejectReason``,
  ``rejectionTimestamp`` → ``rejectTs``) is applied by loaders; this
  module never sees the raw aliases.

This module is intentionally *dependency-free* beyond the standard library
plus pandas so it can be reused by the independent test oracle.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Union

import pandas as pd


# ---------------------------------------------------------------------------
# Frozen constants — do not modify without a new dated spec version.
# ---------------------------------------------------------------------------

EVENT_ID_PREFIX = "event|"
SAMPLE_ID_PREFIX = "sample|"
ID_HEX_LEN = 16                        # sha256 truncation, per P11 §5

TS_ISO_TRUE = "%Y-%m-%dT%H:%M:%S.%f"   # used only for tests

QUARANTINE_TIMESTAMP_PARSE_ERROR = "timestamp_parse_error"
QUARANTINE_MINT_ABSENT = "mint_absent"
QUARANTINE_REASON_ABSENT = "reason_absent"
QUARANTINE_ORPHAN_REJECTION = "orphan_rejection"
QUARANTINE_ORPHAN_OUTCOME = "orphan_outcome"

# The v1 mode name that is intentionally preserved so callers can reproduce
# defective outputs when auditing v1-era artifacts. Emits a loud warning.
LEGACY_MINT_POOLED_MODE = "mint_summary_LEGACY_defective"


# ---------------------------------------------------------------------------
# Errors and diagnostics
# ---------------------------------------------------------------------------

class EventLinkageError(ValueError):
    """Raised when required event linkage is unavailable and ``on_missing='raise'``."""


@dataclass(frozen=True)
class LinkageDiagnostic:
    """Summary of an ``attach_outcomes_by_event`` pass.

    Fields
    ------
    n_rejection_events : int
        Total registry-side rejection events supplied to the linker
        (rows of ``rejections`` with a non-null ``event_id``).
    n_outcome_rows : int
        Total outcome rows retained by the linker AFTER exact-key
        deduplication (see ``n_duplicate_outcome_rows``). Rows with a
        null ``event_id`` are excluded from this count and counted in
        ``n_orphan_outcomes`` instead.
    n_distinct_outcome_event_ids : int
        Number of distinct ``event_id`` values on the outcome side
        after parsing. On RED-2400 v2 this includes outcome
        event_ids that never appear on the registry side (see
        ``n_orphan_outcome_event_ids``); it is *not* a registry-side
        linked count.
    n_events_with_outcomes : int
        Backwards-compatible alias equal to
        ``n_distinct_outcome_event_ids``. **Deprecated label** —
        prefer ``n_distinct_outcome_event_ids`` (outcome-side) or
        ``n_linked_registry_events`` (registry-side). Retained for
        payload compatibility with v2.0.0 pre-release JSON.
    n_linked_registry_events : int
        Number of registry-side rejection events whose ``event_id``
        matches at least one outcome ``event_id``. This is the true
        registry-side linkage count and satisfies
        ``n_linked_registry_events + n_orphan_rejections ==
        n_rejection_events``.
    n_orphan_rejections : int
        Registry events with no matching outcome ``event_id``.
    n_orphan_outcome_event_ids : int
        Distinct outcome ``event_id`` values that do not match any
        registry event. ``n_distinct_outcome_event_ids -
        n_orphan_outcome_event_ids == n_linked_registry_events``.
    n_orphan_outcomes : int
        Outcome rows whose ``event_id`` could not be computed
        (missing/malformed ``rejectTs`` or ``rejectReason``).
        Row-level count, distinct from
        ``n_orphan_outcome_event_ids``.
    n_duplicate_outcome_rows : int
        Outcome rows collapsed by exact-key deduplication (S5).
        Exact-key = (``event_id``, ``sampleTs_utc_ms``, ``dexId``,
        ``pairAddress``). Populated when
        ``attach_outcomes_by_event(allow_duplicate_samples=False)``
        (the default). ``None`` when duplicates are preserved.
    """

    n_rejection_events: int
    n_outcome_rows: int
    n_events_with_outcomes: int
    n_orphan_rejections: int
    n_orphan_outcomes: int
    # v2.0.1 unambiguous companion fields (default None for payload
    # backward compat with dicts loaded from v2.0.0 pre-release JSON).
    n_distinct_outcome_event_ids: Optional[int] = None
    n_linked_registry_events: Optional[int] = None
    n_orphan_outcome_event_ids: Optional[int] = None
    # v2.0.1 S5 field
    n_duplicate_outcome_rows: Optional[int] = None


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

def parse_timestamp_to_ms(value: Union[str, int, float, None]) -> Optional[int]:
    """Return a UTC epoch-millisecond int, or None for null/missing input.

    Rules
    -----
    - ``None`` / ``NaN`` / empty string → ``None``.
    - Integer / float → int(value). Assumed to already be epoch milliseconds
      (P11 family_2 producers). Fractional part is truncated.
    - ISO-8601 string:
        * trailing ``Z`` is replaced with ``+00:00``;
        * parsed with ``datetime.fromisoformat``;
        * converted to UTC then to epoch ms;
        * sub-millisecond digits are truncated (not rounded).
    - Any other input raises ``ValueError`` with a diagnostic — callers can
      route the row to quarantine.
    """
    if value is None:
        return None
    # NaN check for floats without importing numpy explicitly
    if isinstance(value, float) and value != value:  # NaN
        return None
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Trailing Z → +00:00
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise ValueError(f"{QUARANTINE_TIMESTAMP_PARSE_ERROR}: {value!r} ({e})") from e
        if dt.tzinfo is None:
            # Naive datetimes are rejected — every RED-2400 timestamp carries a tz.
            raise ValueError(
                f"{QUARANTINE_TIMESTAMP_PARSE_ERROR}: naive timestamp {value!r}"
            )
        dt_utc = dt.astimezone(timezone.utc)
        # Compute epoch seconds from a whole-second-truncated copy, then add
        # milliseconds from the microsecond field with floor division so we
        # truncate rather than round any sub-millisecond precision.
        whole = dt_utc.replace(microsecond=0)
        secs = int(whole.timestamp())
        ms = secs * 1000 + (dt_utc.microsecond // 1000)
        return int(ms)
    raise ValueError(
        f"{QUARANTINE_TIMESTAMP_PARSE_ERROR}: unsupported type {type(value).__name__}"
    )


def normalize_reason(value: Union[str, None]) -> Optional[str]:
    """Whitespace-trim the reason; preserve case; return None for missing."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    if not isinstance(value, str):
        value = str(value)
    v = value.strip()
    return v if v else None


# ---------------------------------------------------------------------------
# Event ID computation
# ---------------------------------------------------------------------------

def compute_event_id(mint: str, reject_ts_ms: int, reject_reason: str) -> str:
    """Return the 16-hex-char event_id for the (mint, rejectTs, reason) tuple.

    Per P11 spec §5. Not salted; deterministic across runs and languages.
    """
    if mint is None:
        raise ValueError(f"{QUARANTINE_MINT_ABSENT}: mint is None")
    if reject_ts_ms is None:
        raise ValueError(f"{QUARANTINE_TIMESTAMP_PARSE_ERROR}: reject_ts_ms is None")
    if reject_reason is None:
        raise ValueError(f"{QUARANTINE_REASON_ABSENT}: reject_reason is None")
    payload = EVENT_ID_PREFIX + str(mint) + "|" + str(int(reject_ts_ms)) + "|" + str(reject_reason)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:ID_HEX_LEN]


def compute_sample_id(
    event_id: str,
    sample_ts_ms: Optional[int],
    dex_id: Optional[str],
    pair_address: Optional[str],
) -> str:
    """Return the 16-hex-char sample_id per P11 spec §5.

    ``dex_id`` and ``pair_address`` fall back to the literal string ``"null"``
    when absent so family_2 (alias-schema) samples of the same event at the
    same instant never collide with family_1 samples.
    """
    dex = "null" if dex_id is None or (isinstance(dex_id, float) and dex_id != dex_id) else str(dex_id)
    pair = "null" if pair_address is None or (isinstance(pair_address, float) and pair_address != pair_address) else str(pair_address)
    ts = "null" if sample_ts_ms is None else str(int(sample_ts_ms))
    payload = SAMPLE_ID_PREFIX + str(event_id) + "|" + ts + "|" + dex + "|" + pair
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:ID_HEX_LEN]


# ---------------------------------------------------------------------------
# DataFrame-level helpers
# ---------------------------------------------------------------------------

def attach_event_ids(
    df: pd.DataFrame,
    *,
    mint_col: str,
    ts_col: str,
    reason_col: str,
    out_col: str = "event_id",
    out_ts_ms_col: str = "rejectTs_utc_ms",
    on_error: str = "raise",
) -> pd.DataFrame:
    """Return a copy of ``df`` with ``event_id`` and ``rejectTs_utc_ms`` columns.

    Parameters
    ----------
    df : DataFrame
        Rows to compute event_ids for. Must contain ``mint_col``, ``ts_col``,
        ``reason_col``.
    on_error : {"raise", "quarantine"}
        - "raise": any parse failure raises ``ValueError``.
        - "quarantine": rows that fail parsing get ``event_id = None`` and
          ``rejectTs_utc_ms = pd.NA``; a ``quarantine_reason`` column is
          added and populated on the failing rows.
    """
    if on_error not in ("raise", "quarantine"):
        raise ValueError(f"on_error must be 'raise' or 'quarantine', got {on_error!r}")
    for col in (mint_col, ts_col, reason_col):
        if col not in df.columns:
            raise KeyError(f"attach_event_ids: column {col!r} missing from df")

    out = df.copy()
    ids: list[Optional[str]] = []
    ts_ms: list[Optional[int]] = []
    quarantine: list[Optional[str]] = []
    for _, row in out.iterrows():
        try:
            mint = row[mint_col]
            if mint is None or (isinstance(mint, float) and mint != mint):
                raise ValueError(f"{QUARANTINE_MINT_ABSENT}: row missing mint")
            ms = parse_timestamp_to_ms(row[ts_col])
            reason = normalize_reason(row[reason_col])
            if ms is None:
                raise ValueError(f"{QUARANTINE_TIMESTAMP_PARSE_ERROR}: {row[ts_col]!r} → None")
            if reason is None:
                raise ValueError(f"{QUARANTINE_REASON_ABSENT}: row missing/empty reason")
            eid = compute_event_id(str(mint), ms, reason)
            ids.append(eid)
            ts_ms.append(int(ms))
            quarantine.append(None)
        except ValueError as e:
            if on_error == "raise":
                raise
            ids.append(None)
            ts_ms.append(None)
            quarantine.append(str(e).split(":", 1)[0])
    out[out_col] = ids
    out[out_ts_ms_col] = pd.array(ts_ms, dtype="Int64")
    if on_error == "quarantine":
        out["quarantine_reason"] = quarantine
    return out


def attach_outcomes_by_event(
    rejections: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    on_missing: str = "raise",
    warn_on_orphans: bool = True,
    allow_duplicate_samples: bool = False,
) -> tuple[dict[str, pd.DataFrame], LinkageDiagnostic]:
    """Return ``(outcomes_by_event_id, diagnostic)``.

    ``rejections`` must have an ``event_id`` column (populated by
    ``attach_event_ids``). ``outcomes`` likewise.

    Parameters
    ----------
    on_missing : {"raise", "quarantine"}
        - "raise": if any rejection has no matching outcome rows, raise
          ``EventLinkageError``. Fail-loud is the recommended default —
          silent mint-pooling is what caused the v1.0.0 defect.
        - "quarantine": orphan rejections are simply not present in the
          returned dict. Callers must handle the missing key explicitly.
    warn_on_orphans : bool
        Emit a UserWarning summarising orphan counts even in "quarantine"
        mode. Suppress only in test suites that deliberately exercise
        orphan behavior.
    allow_duplicate_samples : bool
        (S5, added v2.0.1.) When ``False`` (default), exact-key duplicate
        outcome rows are collapsed on
        ``(event_id, sampleTs_utc_ms, dexId, pairAddress)`` before
        grouping, and the collapsed count is reported on the diagnostic
        as ``n_duplicate_outcome_rows``. Any exact-tuple duplicate is
        an extractor-side double-write (the sample-identity spec makes
        it impossible for two independent probes to share all four
        fields), so removing them corrects a sample-count inflation
        without affecting tier extrema. Pass ``True`` only to audit
        raw deposit contents; emits ``DeprecationWarning`` and preserves
        pre-S5 row-count semantics.
    """
    if on_missing not in ("raise", "quarantine"):
        raise ValueError(f"on_missing must be 'raise' or 'quarantine', got {on_missing!r}")
    if "event_id" not in rejections.columns:
        raise KeyError("rejections is missing 'event_id' column — call attach_event_ids first")
    if "event_id" not in outcomes.columns:
        raise KeyError("outcomes is missing 'event_id' column — call attach_event_ids first")

    # ----- S5 exact-key deduplication of outcome rows -----
    # Only rows with a non-null event_id are candidates for linkage;
    # rows with a null event_id are quarantined orphans and counted
    # separately below.
    valid_outcomes = outcomes[outcomes["event_id"].notna()]
    orphan_outcome_count = len(outcomes) - len(valid_outcomes)

    n_duplicate_rows: Optional[int] = None
    if not allow_duplicate_samples:
        # Build the exact-key on a copy without mutating the caller's frame.
        dedup_key_cols = ["event_id"]
        # sampleTs_utc_ms is populated by attach_event_ids on outcomes when
        # ts_col=rejectTs is used, but the SAMPLE timestamp lives in
        # `sampleTs` (string). We derive the sample-side epoch-ms lazily to
        # avoid a heavy re-parse loop over deposits that already carry
        # a canonical sample column.
        if "sampleTs_utc_ms" in valid_outcomes.columns:
            dedup_key_cols.append("sampleTs_utc_ms")
        elif "sampleTs" in valid_outcomes.columns:
            dedup_key_cols.append("sampleTs")
        for candidate in ("dexId", "pairAddress"):
            if candidate in valid_outcomes.columns:
                dedup_key_cols.append(candidate)
        pre = len(valid_outcomes)
        valid_outcomes = valid_outcomes.drop_duplicates(
            subset=dedup_key_cols, keep="first"
        )
        n_duplicate_rows = int(pre - len(valid_outcomes))
    else:
        import warnings
        warnings.warn(
            "attach_outcomes_by_event(allow_duplicate_samples=True) preserves "
            "raw duplicate outcome rows; n_samples_in_window and "
            "n_outcome_rows will be inflated relative to the default S5 "
            "deduplicated estimator. Use only for auditing pre-S5 artifacts.",
            DeprecationWarning,
            stacklevel=2,
        )

    out_by_event = {eid: g for eid, g in valid_outcomes.groupby("event_id")}

    rej_events = rejections["event_id"].dropna().tolist()
    orphan_rejections = [eid for eid in rej_events if eid not in out_by_event]
    linked_registry_event_ids = set(rej_events) - set(orphan_rejections)
    orphan_outcome_event_ids = set(out_by_event.keys()) - set(rej_events)

    diag = LinkageDiagnostic(
        n_rejection_events=len(rej_events),
        # Post-dedup row count. Pre-S5 code passed the raw outcomes
        # length; post-S5 we report the linkable-and-unique count so the
        # diagnostic reflects what was actually used.
        n_outcome_rows=int(len(valid_outcomes)),
        # NOTE: `n_events_with_outcomes` retains its v2.0.0 pre-release
        # semantics (distinct outcome-side event_id count) for payload
        # compatibility; the unambiguous companion fields below are the
        # preferred names.
        n_events_with_outcomes=int(len(out_by_event)),
        n_orphan_rejections=int(len(orphan_rejections)),
        n_orphan_outcomes=int(orphan_outcome_count),
        n_distinct_outcome_event_ids=int(len(out_by_event)),
        n_linked_registry_events=int(len(linked_registry_event_ids)),
        n_orphan_outcome_event_ids=int(len(orphan_outcome_event_ids)),
        n_duplicate_outcome_rows=n_duplicate_rows,
    )

    if on_missing == "raise" and orphan_rejections:
        raise EventLinkageError(
            f"attach_outcomes_by_event: {len(orphan_rejections)} rejection events "
            f"have no attachable outcome rows. First 5: {orphan_rejections[:5]}. "
            f"Pass on_missing='quarantine' to allow orphan rejections."
        )
    if warn_on_orphans and (orphan_rejections or orphan_outcome_count):
        import warnings
        warnings.warn(
            f"Event linkage produced {len(orphan_rejections)} orphan rejections "
            f"and {orphan_outcome_count} orphan outcome rows. See LinkageDiagnostic.",
            stacklevel=2,
        )
    return out_by_event, diag


# ---------------------------------------------------------------------------
# Estimand-mode dispatch (Phase A step 4)
# ---------------------------------------------------------------------------

MODE_EVENT = "event"
MODE_FIRST_EVENT_PER_MINT = "first_event_per_mint"
MODE_LATEST_EVENT_PER_MINT = "latest_event_per_mint"
MODE_MINT_SUMMARY = "mint_summary"
MODE_LEGACY_MINT_POOLED = LEGACY_MINT_POOLED_MODE

VALID_MODES = frozenset({
    MODE_EVENT,
    MODE_FIRST_EVENT_PER_MINT,
    MODE_LATEST_EVENT_PER_MINT,
    MODE_MINT_SUMMARY,
    MODE_LEGACY_MINT_POOLED,
})


def select_rejections_by_mode(
    rejections_with_event_id: pd.DataFrame,
    mode: str,
) -> pd.DataFrame:
    """Return the rejections subset appropriate for ``mode``.

    - ``event`` (default): all rejection events, unmodified.
    - ``first_event_per_mint``: keep only the earliest ``rejectTs_utc_ms``
      per mint. Ties broken by ``event_id`` lexicographic order.
    - ``latest_event_per_mint``: keep only the latest per mint. Same
      tie-break rule.
    - ``mint_summary``: keep one row per mint, chosen as the earliest
      event, with a ``mode`` flag indicating downstream code should sum
      per-mint statistics (semantics are the caller's responsibility;
      the toolkit exposes both event-level and mint-summary tables so
      neither is a hidden substitute for the other).
    - ``mint_summary_LEGACY_defective``: identical to ``mint_summary`` at
      the row-selection layer, but tagged so downstream code emits a
      loud warning and refuses to mint a "corrected" result under this
      mode.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"unknown mode {mode!r}. Valid: {sorted(VALID_MODES)}"
        )
    if mode == MODE_EVENT:
        return rejections_with_event_id.copy()
    df = rejections_with_event_id.copy()
    if "rejectTs_utc_ms" not in df.columns:
        raise KeyError(
            f"{mode!r} requires 'rejectTs_utc_ms' column; call attach_event_ids first"
        )
    if mode == MODE_FIRST_EVENT_PER_MINT:
        df = df.sort_values(["mint", "rejectTs_utc_ms", "event_id"]).drop_duplicates("mint", keep="first")
        return df.reset_index(drop=True)
    if mode == MODE_LATEST_EVENT_PER_MINT:
        df = df.sort_values(["mint", "rejectTs_utc_ms", "event_id"]).drop_duplicates("mint", keep="last")
        return df.reset_index(drop=True)
    # MODE_MINT_SUMMARY and MODE_LEGACY: pick the earliest event as the
    # per-mint representative; downstream code differentiates behavior.
    df = df.sort_values(["mint", "rejectTs_utc_ms", "event_id"]).drop_duplicates("mint", keep="first")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "EVENT_ID_PREFIX",
    "SAMPLE_ID_PREFIX",
    "ID_HEX_LEN",
    "LEGACY_MINT_POOLED_MODE",
    "MODE_EVENT",
    "MODE_FIRST_EVENT_PER_MINT",
    "MODE_LATEST_EVENT_PER_MINT",
    "MODE_MINT_SUMMARY",
    "MODE_LEGACY_MINT_POOLED",
    "VALID_MODES",
    "EventLinkageError",
    "LinkageDiagnostic",
    "parse_timestamp_to_ms",
    "normalize_reason",
    "compute_event_id",
    "compute_sample_id",
    "attach_event_ids",
    "attach_outcomes_by_event",
    "select_rejections_by_mode",
]
