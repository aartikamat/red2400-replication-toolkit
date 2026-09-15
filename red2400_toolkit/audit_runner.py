"""Audit runner — per-filter and aggregate save-to-miss reporting.

v2 semantics
------------
Aggregation is per-event by default. ``classify_dataset`` returns a frame
indexed by ``event_id`` with a ``filter_id`` column, so ``groupby(filter_id)``
counts *events*, not *mints*. The v1.0.0 mint-pooled path is preserved
under ``mode='mint_summary_LEGACY_defective'`` for auditing v1-era
artifacts only; it emits a DeprecationWarning.

v2.0.1 additions
----------------
- S1 (scope-out disclosure): the reference price the classifier
  anchors ratios at is the earliest forward sample the extractor
  caught, not the price at the rejection instant. Non-zero lag on
  the first sample biases ``min_ratio`` and ``max_ratio`` toward 1
  by an unknown amount. ``run_audit`` emits a ``UserWarning`` when
  the deposit-wide median first-sample lag exceeds
  ``lag_warn_median_min`` (default 5 min), listing median, P90 and
  P99 lag so users can quantify a lower bound on the bias.
- S3 (scope-out disclosure): the recorded ``ageDays`` at the ``gone``
  transition is an upper bound on the true age at death (probe
  cadence is not carried by the deposit). ``run_audit`` emits a
  ``UserWarning`` naming the count of events within ±10 minutes of
  ``EARLY_DEATH_AGE_MAX_MIN`` — those events are boundary-sensitive
  to the tier assignment. ``sensitivity_early_death_threshold``
  reruns the audit across a threshold range so the boundary
  sensitivity can be quantified numerically.
- S4: right-truncated events (rejection ``t_r`` + 24h > deposit-end
  sample timestamp) are flagged and, by default, excluded from the
  primary per-filter denominator. Pass ``include_truncated=True`` to
  reproduce v2.0.0 pre-S4 numbers and emit ``DeprecationWarning``.
- S6: per-tier 95% Wilson score confidence intervals are attached to
  every per-filter and overall row so small-n filters (e.g. filter_8
  with n=19) surface their uncertainty. Filters with n<30 also emit a
  ``UserWarning`` naming the width of the interval.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from . import prfs_classifier as _prfs_mod
from .event_model import LinkageDiagnostic, MODE_EVENT, VALID_MODES, parse_timestamp_to_ms
from .prfs_classifier import (
    ALL_TIERS,
    TIER_SAVED_WINDOWED,
    TIER_SAVED_EARLY_DEATH,
    TIER_MISSED,
    classify_dataset,
)
from .red2400_loader import RED2400Deposit


# 24h observation window in epoch-ms (matches OBSERVATION_WINDOW_MIN * 60_000).
OBSERVATION_WINDOW_MS = 24 * 60 * 60 * 1000

# Wilson-CI 97.5 pctile of standard normal (2-sided 95% CI).
_Z_95 = 1.959963984540054


def _wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Return the 100*(1-alpha)% Wilson score interval as (lo_pct, hi_pct).

    Closed-form; dependency-free beyond ``math``. Bounded to [0, 100].
    Returns (nan, nan) when ``n == 0``. Handles ``k==0`` and ``k==n``
    edge cases via the standard formula (lo pins at 0, hi pins at 100).
    """
    if n == 0:
        return (float("nan"), float("nan"))
    if alpha == 0.05:
        z = _Z_95
    else:
        # Use scipy if available; else fall back to 95% z-score with a warning.
        try:
            from scipy.stats import norm
            z = float(norm.ppf(1.0 - alpha / 2.0))
        except ImportError:
            warnings.warn(
                "scipy not installed; using 95% z-score for Wilson CI regardless of alpha",
                stacklevel=2,
            )
            z = _Z_95
    p_hat = k / n
    denom = 1.0 + z * z / n
    center = p_hat + z * z / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    lo = max(0.0, (center - margin) / denom)
    hi = min(1.0, (center + margin) / denom)
    return (100.0 * lo, 100.0 * hi)


@dataclass
class AuditResult:
    per_filter: pd.DataFrame
    overall: pd.Series
    save_to_miss_conservative: float
    save_to_miss_combined: float
    classifications: pd.DataFrame
    reference_price_mode: str
    mode: str
    linkage_diagnostic: Optional[LinkageDiagnostic] = None
    # S4 fields
    truncated_events_n: int = 0
    truncated_tier_distribution: Optional[pd.Series] = None
    deposit_end_ts_utc_ms: Optional[int] = None
    include_truncated: bool = False
    # S6 confidence-interval alpha
    wilson_alpha: float = 0.05
    # S1 scope-out disclosure — first-sample lag summary (minutes)
    first_sample_lag_median_min: Optional[float] = None
    first_sample_lag_p90_min: Optional[float] = None
    first_sample_lag_p99_min: Optional[float] = None
    # S3 scope-out disclosure — early-death boundary-sensitive count
    boundary_sensitive_early_death_count: int = 0
    boundary_sensitive_window_min: float = 10.0

    def to_dict(self, include_ci: bool = True) -> dict:
        payload = {
            "n_events": int(self.overall["n"]),
            # v1 alias — retained temporarily for downstream code that reads
            # "n_rejections". Corrected v2 name is n_events. Both are equal.
            "n_rejections": int(self.overall["n"]),
            "reference_price_mode": self.reference_price_mode,
            "mode": self.mode,
            "per_filter": self.per_filter.round(2).to_dict(orient="index"),
            "overall": {
                k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in self.overall.to_dict().items()
            },
            "save_to_miss_conservative": round(self.save_to_miss_conservative, 4),
            "save_to_miss_combined": round(self.save_to_miss_combined, 4),
            # S4 disclosures
            "truncated_events_n": int(self.truncated_events_n),
            "include_truncated": bool(self.include_truncated),
            "deposit_end_ts_utc_ms": (
                int(self.deposit_end_ts_utc_ms)
                if self.deposit_end_ts_utc_ms is not None else None
            ),
            # S6 disclosure
            "wilson_alpha": float(self.wilson_alpha),
            # S1 disclosure — first-sample lag summary (may be None if
            # no event carried a usable reference-price sample)
            "first_sample_lag_median_min": (
                float(self.first_sample_lag_median_min)
                if self.first_sample_lag_median_min is not None else None
            ),
            "first_sample_lag_p90_min": (
                float(self.first_sample_lag_p90_min)
                if self.first_sample_lag_p90_min is not None else None
            ),
            "first_sample_lag_p99_min": (
                float(self.first_sample_lag_p99_min)
                if self.first_sample_lag_p99_min is not None else None
            ),
            # S3 disclosure — count of events sitting within ±10 min of
            # the early-death threshold (boundary-sensitive under
            # interval-censoring). Never larger than n_events.
            "boundary_sensitive_early_death_count": int(
                self.boundary_sensitive_early_death_count
            ),
            "boundary_sensitive_window_min": float(
                self.boundary_sensitive_window_min
            ),
        }
        if include_ci:
            # Per-filter CIs are already columns of per_filter; keep the
            # explicit "include_ci" marker so downstream consumers know
            # which schema to expect.
            payload["ci_columns_present"] = True
        if self.linkage_diagnostic is not None:
            d = self.linkage_diagnostic
            payload["linkage_diagnostic"] = {
                "n_rejection_events": d.n_rejection_events,
                "n_outcome_rows": d.n_outcome_rows,
                # Retained for payload compatibility with v2.0.0
                # pre-release JSON; equivalent to
                # `n_distinct_outcome_event_ids` below.
                "n_events_with_outcomes": d.n_events_with_outcomes,
                "n_orphan_rejections": d.n_orphan_rejections,
                "n_orphan_outcomes": d.n_orphan_outcomes,
                # v2.0.1 unambiguous companion fields:
                "n_distinct_outcome_event_ids": d.n_distinct_outcome_event_ids,
                "n_linked_registry_events": d.n_linked_registry_events,
                "n_orphan_outcome_event_ids": d.n_orphan_outcome_event_ids,
                # S5 field
                "n_duplicate_outcome_rows": d.n_duplicate_outcome_rows,
            }
        return payload


def _tier_table(
    classifications: pd.DataFrame,
    group_col: Optional[str],
    *,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Return a per-group tier table with Wilson-CI companion columns (S6).

    Columns per group:
      n, <tier>, <tier>_ci_lo, <tier>_ci_hi  for tier in ALL_TIERS.
    """
    if group_col is None:
        counts = classifications["tier"].value_counts()
        n = int(counts.sum())
        pct = (counts / n * 100.0 if n > 0 else counts * 0.0).reindex(
            ALL_TIERS, fill_value=0.0
        )
        s = pct.copy()
        s["n"] = n
        # Attach CI as additional row entries: `<tier>_ci_lo` / `<tier>_ci_hi`
        for tier in ALL_TIERS:
            k = int(counts.get(tier, 0))
            lo, hi = _wilson_ci(k, n, alpha=alpha)
            s[f"{tier}_ci_lo"] = lo
            s[f"{tier}_ci_hi"] = hi
        return s

    rows = []
    for group, sub in classifications.groupby(group_col):
        counts = sub["tier"].value_counts()
        n = int(counts.sum())
        pct = (counts / n * 100.0 if n > 0 else counts * 0.0).reindex(
            ALL_TIERS, fill_value=0.0
        )
        rec = {"n": n, **pct.to_dict()}
        for tier in ALL_TIERS:
            k = int(counts.get(tier, 0))
            lo, hi = _wilson_ci(k, n, alpha=alpha)
            rec[f"{tier}_ci_lo"] = lo
            rec[f"{tier}_ci_hi"] = hi
        rec[group_col] = group
        rows.append(rec)
    df = pd.DataFrame.from_records(rows).set_index(group_col)
    ordered_cols = ["n"]
    for tier in ALL_TIERS:
        ordered_cols.extend([tier, f"{tier}_ci_lo", f"{tier}_ci_hi"])
    return df[ordered_cols]


def _save_to_miss(overall: pd.Series, combined: bool) -> float:
    missed = float(overall.get(TIER_MISSED, 0.0))
    saved_w = float(overall.get(TIER_SAVED_WINDOWED, 0.0))
    saved_ed = float(overall.get(TIER_SAVED_EARLY_DEATH, 0.0))
    numerator = saved_w + saved_ed if combined else saved_w
    if missed <= 0:
        return float("inf") if numerator > 0 else float("nan")
    return numerator / missed


def _compute_deposit_end_ms(rejection_outcomes: pd.DataFrame) -> Optional[int]:
    """Return the latest sampleTs across all outcomes as epoch ms.

    Returns ``None`` if the outcomes frame is empty or lacks parseable
    sampleTs values.
    """
    if len(rejection_outcomes) == 0 or "sampleTs" not in rejection_outcomes.columns:
        return None
    ms_values = []
    for v in rejection_outcomes["sampleTs"]:
        try:
            ms = parse_timestamp_to_ms(v)
        except ValueError:
            ms = None
        if ms is not None:
            ms_values.append(int(ms))
    return max(ms_values) if ms_values else None


def _flag_right_truncated(
    classifications: pd.DataFrame, deposit_end_ms: Optional[int]
) -> pd.Series:
    """Return a boolean Series aligned to ``classifications.index``.

    True where the event's 24h forward window extends past the deposit's
    latest observed sample timestamp — i.e. the window is right-truncated
    within the deposit.
    """
    if deposit_end_ms is None or "rejectTs_utc_ms" not in classifications.columns:
        return pd.Series(False, index=classifications.index)
    reject_ms = classifications["rejectTs_utc_ms"].astype("Int64")
    truncated = (reject_ms.astype("Float64") + OBSERVATION_WINDOW_MS) > deposit_end_ms
    return truncated.fillna(False).astype(bool)


def run_audit(
    deposit: RED2400Deposit,
    reference_price_mode: str = "first_sample_price",
    mode: str = MODE_EVENT,
    on_missing: str = "raise",
    *,
    include_truncated: bool = False,
    wilson_alpha: float = 0.05,
    warn_small_n_below: int = 30,
    lag_warn_median_min: float = 5.0,
    boundary_sensitive_window_min: float = 10.0,
) -> AuditResult:
    """Run the full audit pipeline.

    Parameters
    ----------
    deposit : RED2400Deposit
        Loaded deposit (from `load_deposit`).
    reference_price_mode : {"first_sample_price", "liquidity_proxy"}
        Canonical or robustness (§V.D).
    mode : str
        Estimand mode. See `event_model.VALID_MODES`. Default is per-event.
    on_missing : {"raise", "quarantine"}
        Behavior for rejection events with no attachable outcome rows.
    include_truncated : bool, keyword-only
        (S4, v2.0.1.) When ``False`` (default), right-truncated events —
        those whose 24h forward window extends past
        ``max(outcomes.sampleTs)`` — are excluded from the primary
        per-filter denominator and their tier distribution is surfaced
        separately as ``AuditResult.truncated_tier_distribution``. Pass
        ``True`` to reproduce the v2.0.0 (pre-S4) unconditional estimator
        and emit ``DeprecationWarning``.
    wilson_alpha : float, keyword-only
        (S6, v2.0.1.) Confidence level for the per-tier Wilson score
        interval columns. Default 0.05 gives 95% CIs. Only alpha=0.05
        is fully dependency-free; other alphas prefer scipy.
    warn_small_n_below : int, keyword-only
        Emit a ``UserWarning`` naming any filter whose ``n <
        warn_small_n_below``. Default 30 aligns with the classical
        small-n proportion boundary. Pass 0 to disable.
    lag_warn_median_min : float, keyword-only
        (S1, v2.0.1.) Emit a ``UserWarning`` when the deposit-wide
        median first-sample lag exceeds this many minutes, listing
        median, P90 and P99 lag. Pass 0 to disable the warning; the
        lag summary is always recorded on the result regardless.
    boundary_sensitive_window_min : float, keyword-only
        (S3, v2.0.1.) Half-width of the boundary sensitivity band
        around ``EARLY_DEATH_AGE_MAX_MIN``. Events whose
        ``early_death_age_min`` sits within this many minutes of the
        threshold are counted as boundary-sensitive and surfaced on
        the result; a ``UserWarning`` fires when the count is
        non-zero. Pass 0 to disable the warning (the count is still
        recorded).
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}. Valid: {sorted(VALID_MODES)}")

    if include_truncated:
        warnings.warn(
            "run_audit(include_truncated=True) reproduces the v2.0.0 pre-S4 "
            "estimator; right-truncated events (24h window extends past "
            "max(sampleTs)) are counted alongside full-window events. Their "
            "tier assignment is not directly comparable and biases "
            "per-filter shares by an unknown amount. Use only for auditing "
            "pre-S4 artifacts.",
            DeprecationWarning,
            stacklevel=2,
        )

    classifications = classify_dataset(
        rejections=deposit.rejections,
        rejection_outcomes=deposit.rejection_outcomes,
        graveyard_lifecycle=deposit.graveyard_lifecycle,
        reference_price_mode=reference_price_mode,
        mode=mode,
        on_missing=on_missing,
    )

    # S4 right-truncation flagging
    deposit_end_ms = _compute_deposit_end_ms(deposit.rejection_outcomes)
    truncated_flag = _flag_right_truncated(classifications, deposit_end_ms)
    classifications = classifications.copy()
    classifications["right_truncated"] = truncated_flag.values
    truncated_events_n = int(truncated_flag.sum())

    if include_truncated:
        primary = classifications
    else:
        primary = classifications[~classifications["right_truncated"]]

    truncated_tier_distribution: Optional[pd.Series] = None
    if truncated_events_n > 0:
        trunc_only = classifications[classifications["right_truncated"]]
        trunc_counts = trunc_only["tier"].value_counts()
        trunc_pct = (trunc_counts / len(trunc_only) * 100.0).reindex(
            ALL_TIERS, fill_value=0.0
        )
        trunc_pct["n"] = int(len(trunc_only))
        truncated_tier_distribution = trunc_pct

    per_filter = _tier_table(primary, group_col="filter_id", alpha=wilson_alpha)
    overall = _tier_table(primary, group_col=None, alpha=wilson_alpha)

    # S6 small-n warning
    if warn_small_n_below and len(per_filter) > 0:
        small = per_filter[per_filter["n"] < warn_small_n_below]
        if len(small) > 0:
            small_ids = list(small.index)
            small_ns = [int(small.loc[fid, "n"]) for fid in small_ids]
            warnings.warn(
                f"Small-n filters (n<{warn_small_n_below}) present: "
                f"{list(zip(small_ids, small_ns))}. 95% Wilson score intervals "
                f"are attached as `<tier>_ci_lo` and `<tier>_ci_hi` columns.",
                UserWarning,
                stacklevel=2,
            )

    s2m_cons = _save_to_miss(overall, combined=False)
    s2m_comb = _save_to_miss(overall, combined=True)

    # S1 disclosure — first-sample lag summary
    lag_median: Optional[float] = None
    lag_p90: Optional[float] = None
    lag_p99: Optional[float] = None
    if "first_sample_lag_min" in primary.columns:
        lag_series = primary["first_sample_lag_min"].dropna().astype(float)
        if len(lag_series) > 0:
            lag_median = float(lag_series.median())
            lag_p90 = float(lag_series.quantile(0.90))
            lag_p99 = float(lag_series.quantile(0.99))
            if lag_warn_median_min > 0 and lag_median > lag_warn_median_min:
                warnings.warn(
                    f"S1 disclosure: median first-sample lag = "
                    f"{lag_median:.2f} min (P90 = {lag_p90:.2f}, "
                    f"P99 = {lag_p99:.2f}). Reference price is anchored at "
                    f"this lag, not at the rejection instant; `min_ratio` and "
                    f"`max_ratio` are biased toward 1 by an unknown "
                    f"asset-specific amount. Rejection-time price is not "
                    f"recorded in the RED-2400 deposit.",
                    UserWarning,
                    stacklevel=2,
                )

    # S3 disclosure — boundary-sensitive early-death count. Look up
    # the threshold via the module attribute so a sensitivity sweep
    # that mutates `_prfs_mod.EARLY_DEATH_AGE_MAX_MIN` is honored.
    boundary_count = 0
    if "early_death_age_min" in primary.columns:
        ed_threshold = float(_prfs_mod.EARLY_DEATH_AGE_MAX_MIN)
        ed_series = primary["early_death_age_min"].dropna().astype(float)
        if len(ed_series) > 0:
            band_lo = ed_threshold - boundary_sensitive_window_min
            band_hi = ed_threshold + boundary_sensitive_window_min
            in_band = (ed_series >= band_lo) & (ed_series <= band_hi)
            boundary_count = int(in_band.sum())
            if boundary_sensitive_window_min > 0 and boundary_count > 0:
                warnings.warn(
                    f"S3 disclosure: {boundary_count} event(s) with "
                    f"early_death_age_min within +/-{boundary_sensitive_window_min:g} min "
                    f"of the {ed_threshold:g}-min threshold. Recorded "
                    f"age is an upper bound (observed at tracker probe); "
                    f"boundary-sensitive tier assignments should be treated "
                    f"as such. See `sensitivity_early_death_threshold` for a "
                    f"numerical sensitivity analysis.",
                    UserWarning,
                    stacklevel=2,
                )

    return AuditResult(
        per_filter=per_filter,
        overall=overall,
        save_to_miss_conservative=s2m_cons,
        save_to_miss_combined=s2m_comb,
        classifications=classifications,
        reference_price_mode=reference_price_mode,
        mode=mode,
        linkage_diagnostic=classifications.attrs.get("linkage_diagnostic"),
        truncated_events_n=truncated_events_n,
        truncated_tier_distribution=truncated_tier_distribution,
        deposit_end_ts_utc_ms=deposit_end_ms,
        include_truncated=include_truncated,
        wilson_alpha=wilson_alpha,
        first_sample_lag_median_min=lag_median,
        first_sample_lag_p90_min=lag_p90,
        first_sample_lag_p99_min=lag_p99,
        boundary_sensitive_early_death_count=boundary_count,
        boundary_sensitive_window_min=float(boundary_sensitive_window_min),
    )


def sensitivity_early_death_threshold(
    deposit: RED2400Deposit,
    lower: float = 45.0,
    upper: float = 90.0,
    step: float = 5.0,
    *,
    reference_price_mode: str = "first_sample_price",
    mode: str = MODE_EVENT,
    on_missing: str = "raise",
) -> pd.DataFrame:
    """S3 sensitivity helper — rerun the audit across a threshold range.

    Under the S3 scope-out disclosure, the recorded ``ageDays`` at
    ``gone`` is an upper bound on the true age at death; the
    ``saved_early_death`` tier is therefore sensitive to the exact
    cutoff. This helper reruns ``run_audit`` at each threshold in
    ``range(lower, upper + step, step)`` and returns a DataFrame with
    one row per threshold and columns

        threshold_min, n_events, saved_early_death_pct,
        saved_windowed_pct, missed_pct, flat_pct, unclassifiable_pct,
        boundary_sensitive_count

    so the caller can inspect how the tier distribution moves with the
    cutoff. Threshold changes are applied only for the duration of the
    sensitivity call; the module-level ``EARLY_DEATH_AGE_MAX_MIN`` is
    restored on exit.

    The helper does not itself impute a probability distribution over
    death intervals; it simply exposes the point-estimator's
    boundary-sensitivity numerically.
    """
    thresholds: list[float] = []
    val = float(lower)
    while val <= float(upper) + 1e-9:
        thresholds.append(round(val, 6))
        val += float(step)

    original = _prfs_mod.EARLY_DEATH_AGE_MAX_MIN
    rows = []
    try:
        for t in thresholds:
            _prfs_mod.EARLY_DEATH_AGE_MAX_MIN = float(t)
            with warnings.catch_warnings():
                # Suppress the S1/S3 warnings the sub-run itself would
                # otherwise emit at every step; the caller is inspecting
                # sensitivity, not re-running full disclosure.
                warnings.simplefilter("ignore", UserWarning)
                warnings.simplefilter("ignore", DeprecationWarning)
                res = run_audit(
                    deposit,
                    reference_price_mode=reference_price_mode,
                    mode=mode,
                    on_missing=on_missing,
                    lag_warn_median_min=0,
                    boundary_sensitive_window_min=0,
                )
            overall = res.overall
            rows.append({
                "threshold_min": float(t),
                "n_events": int(overall.get("n", 0)),
                "saved_early_death_pct": float(overall.get(TIER_SAVED_EARLY_DEATH, 0.0)),
                "saved_windowed_pct": float(overall.get(TIER_SAVED_WINDOWED, 0.0)),
                "missed_pct": float(overall.get(TIER_MISSED, 0.0)),
                "flat_pct": float(overall.get("flat", 0.0)),
                "unclassifiable_pct": float(overall.get("unclassifiable", 0.0)),
                "boundary_sensitive_count": int(res.boundary_sensitive_early_death_count),
            })
    finally:
        _prfs_mod.EARLY_DEATH_AGE_MAX_MIN = original

    return pd.DataFrame.from_records(rows)
