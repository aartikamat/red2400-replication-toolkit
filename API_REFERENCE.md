# API Reference (v2.0.1)

All symbols below are exported from the top-level `red2400_toolkit`
package (see `red2400_toolkit/__init__.py`).

## Event model (`red2400_toolkit.event_model`)

### Constants

- `EVENT_ID_PREFIX = "event|"`
- `SAMPLE_ID_PREFIX = "sample|"`
- `ID_HEX_LEN = 16`  — truncation length for `event_id` / `sample_id`.
- `MODE_EVENT = "event"` — default estimand: classify every rejection event.
- `MODE_FIRST_EVENT_PER_MINT = "first_event_per_mint"`
- `MODE_LATEST_EVENT_PER_MINT = "latest_event_per_mint"`
- `MODE_MINT_SUMMARY = "mint_summary"` — one row per mint (earliest event).
- `MODE_LEGACY_MINT_POOLED = "mint_summary_LEGACY_defective"` — reproduces v1
  mint-pooled dispatch; emits `DeprecationWarning`.
- `VALID_MODES: frozenset[str]`

### Errors

- `EventLinkageError(ValueError)` — raised when a rejection has no
  attachable outcome rows and `on_missing='raise'`.

### Diagnostic dataclass

- `LinkageDiagnostic` — frozen fields:
  - `n_rejection_events` — total registry events supplied.
  - `n_outcome_rows` — total outcome sample rows supplied.
  - `n_events_with_outcomes` — **deprecated label**: equal to
    `n_distinct_outcome_event_ids` (below); retained for payload
    compatibility with v2.0.0 pre-release JSON.
  - `n_distinct_outcome_event_ids` — distinct outcome-side
    `event_id` values (includes outcome ids that never appear in
    the registry).
  - `n_linked_registry_events` — registry-side count of events
    with at least one matching outcome row
    (`n_rejection_events - n_orphan_rejections`). This is the
    correct denominator for registry-side linkage percentages.
  - `n_orphan_rejections` — registry events with no attachable
    outcome rows.
  - `n_orphan_outcome_event_ids` — distinct outcome `event_id`
    values that do not match any registry event.
  - `n_orphan_outcomes` — row-level count of outcome rows whose
    `event_id` could not be computed (missing/malformed
    `rejectTs` or `rejectReason`).
  Attached to `AuditResult` and to `classify_dataset` output
  frame's `.attrs['linkage_diagnostic']`.

### Functions

- `parse_timestamp_to_ms(value) -> Optional[int]` — ISO-8601 or epoch-ms
  input to UTC epoch ms. `None` on null/empty; raises on unparseable
  input. Sub-ms digits truncated (not rounded).
- `normalize_reason(value) -> Optional[str]` — whitespace-trim; case
  preserved.
- `compute_event_id(mint, reject_ts_ms, reject_reason) -> str` —
  `sha256("event|" + mint + "|" + str(int(ts_ms)) + "|" + reason)`
  truncated to 16 hex chars. Deterministic across runs / OSes / languages.
- `compute_sample_id(event_id, sample_ts_ms, dex_id, pair_address) -> str`
  — analogous per-sample hash.
- `attach_event_ids(df, *, mint_col, ts_col, reason_col, out_col="event_id",
   out_ts_ms_col="rejectTs_utc_ms", on_error="raise") -> pd.DataFrame` —
  copy of `df` with the two derived columns added.
- `attach_outcomes_by_event(rejections, outcomes, *, on_missing="raise",
   warn_on_orphans=True) -> tuple[dict[str, DataFrame], LinkageDiagnostic]`
  — group outcomes by event_id and validate linkage.
- `select_rejections_by_mode(rejections_with_event_id, mode) -> DataFrame`
  — apply the estimand mode to a rejections frame.

## Classification (`red2400_toolkit.prfs_classifier`)

### Tier constants

- `TIER_SAVED_WINDOWED`, `TIER_SAVED_EARLY_DEATH`, `TIER_FLAT`,
  `TIER_MISSED`, `TIER_UNCLASSIFIABLE` — string constants.
- `ALL_TIERS` — tuple of all tier names in canonical reporting order.

### Threshold constants

- `EARLY_DEATH_AGE_MAX_MIN = 60`
- `SAVED_THRESHOLD = 0.5`
- `MISSED_THRESHOLD = 2.0`
- `OBSERVATION_WINDOW_MIN = 1440`

### Dataclass

- `ClassificationDetail` — frozen fields
  `tier`, `n_samples_in_window`, `reference_price`, `min_ratio`,
  `max_ratio`, `early_death_age_min`, `early_death_terminal`.

### Functions

- `classify_event(samples, lifecycle_rows=None,
  reference_price_mode="first_sample_price") -> ClassificationDetail` —
  single-event classifier (unchanged from v1).
- `classify_dataset(rejections, rejection_outcomes,
  graveyard_lifecycle=None, reference_price_mode="first_sample_price",
  mode=MODE_EVENT, on_missing="raise") -> pd.DataFrame` —
  event-keyed dataset dispatch. Returns a DataFrame indexed by
  `event_id` with `mint`, `filter_id`, `rejectTs_utc_ms`, `tier`,
  `n_samples_in_window`, `reference_price`, `min_ratio`, `max_ratio`,
  `early_death_age_min`, `early_death_terminal`, `mode`.

## Loader (`red2400_toolkit.red2400_loader`)

- `SchemaError(ValueError)` — raised when a deposit file is missing
  required columns.
- `RED2400Deposit` — frozen dataclass holding the three loaded
  DataFrames and the deposit directory path. Exposes
  `n_rejections`, `n_samples`, `n_lifecycle` properties.
- `load_deposit(deposit_dir) -> RED2400Deposit` — schema-validating
  loader.

## Audit runner (`red2400_toolkit.audit_runner`)

- `AuditResult` — dataclass fields
  `per_filter`, `overall`, `save_to_miss_conservative`,
  `save_to_miss_combined`, `classifications`, `reference_price_mode`,
  `mode`, `linkage_diagnostic`. Method `to_dict()` returns a
  JSON-serialisable summary.
- `run_audit(deposit, reference_price_mode="first_sample_price",
  mode=MODE_EVENT, on_missing="raise") -> AuditResult`.

## Early-death matched comparison (`red2400_toolkit.early_death_validator`)

- `MatchedComparisonResult` — dataclass fields
  `early_death_n`, `early_death_gone_rate`,
  `non_early_death_n`, `non_early_death_gone_rate`,
  `rate_difference_pp`.
- `matched_comparison(classifications, graveyard_lifecycle) ->
  MatchedComparisonResult` — handles both event-keyed (v2) and
  mint-indexed (legacy) `classifications` frames.

## Figure generator (`red2400_toolkit.figure_generator`, optional)

Available only when `matplotlib` is installed (extra `[figures]`).

- `figure_1_age_distribution(classifications, out_path, bins=30) -> Path`
- `figure_2_sample_cadence(rejection_outcomes, out_path, bins=48) -> Path`

## Estimand mode quick reference

| Mode                            | Row count                | Use case                                                 |
|---------------------------------|--------------------------|----------------------------------------------------------|
| `MODE_EVENT`  (default)          | one row per rejection    | scientific default; per-event tier / filter attribution  |
| `MODE_FIRST_EVENT_PER_MINT`      | one row per unique mint  | first-observed-event view                                |
| `MODE_LATEST_EVENT_PER_MINT`     | one row per unique mint  | latest-observed-event view                               |
| `MODE_MINT_SUMMARY`              | one row per unique mint  | per-mint estimand (chooses earliest event as anchor)     |
| `MODE_LEGACY_MINT_POOLED`        | one row per rejection    | v1 mint-pooled dispatch (deprecated; regression witness) |
