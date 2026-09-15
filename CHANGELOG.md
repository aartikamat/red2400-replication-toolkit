# Changelog

All notable changes to `red2400-toolkit` are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
semantic-versioning policy in `SEMVER_POLICY.md`.

## [Unreleased] -- v2.0.1 draft (not yet tagged)

### Scientific-correctness closures (S1, S2, S3, S4, S5, S6)

- **S2 (right-censoring in matched_comparison; CLOSE).**
  `early_death_validator.matched_comparison` now distinguishes
  observed `gone` / observed `alive_observed` / `unobserved` (right-
  censored) rather than treating lifecycle-absent mints as observed
  survivors. The gone-rate uses the observed denominator by default;
  `include_censored=True` reproduces the pre-S2 estimator and emits
  `DeprecationWarning`. `MatchedComparisonResult` gains
  `early_death_censored_n`, `non_early_death_censored_n`,
  `censoring_note`, and `include_censored` fields.
- **S4 (right-truncation at deposit end; CLOSE).** `run_audit` computes
  `deposit_end_ms = max(sampleTs_utc_ms)` and flags every event whose
  24-hour forward window extends past that end. Right-truncated events
  are excluded from the primary per-filter denominator by default;
  their tier distribution is surfaced separately through
  `AuditResult.truncated_tier_distribution` and their count through
  `AuditResult.truncated_events_n`. On the RED-2400 v2 deposit 297
  events are so truncated. Pass `include_truncated=True` to reproduce
  v2.0.0 pre-S4 numbers; emits `DeprecationWarning`.
- **S5 (exact-key duplicate outcome-row dedup; CLOSE).**
  `event_model.attach_outcomes_by_event` now collapses outcome rows on
  `(event_id, sampleTs, dexId, pairAddress)` before grouping and
  reports the collapsed count as
  `LinkageDiagnostic.n_duplicate_outcome_rows`. On the RED-2400 v2
  deposit 51 rows are so collapsed. Pass `allow_duplicate_samples=True`
  to preserve duplicates; emits `DeprecationWarning`.
- **S6 (Wilson-CI on per-filter percentages; CLOSE).** `_tier_table`
  now attaches 95 % Wilson score intervals as `<tier>_ci_lo` and
  `<tier>_ci_hi` companion columns to every per-filter and overall
  row. Filters with `n < warn_small_n_below` (default 30) trigger a
  `UserWarning` naming the filter and its `n`. filter_8 (n = 19)
  reports `saved_windowed = 5.26 %` with a 95 % Wilson interval of
  [0.94 %, 24.64 %].

### Scientific-correctness scope-outs (S1, S3; disclosure surface implemented)

- **S1 (first-sample reference-price bias; SCOPE OUT — permitted
  reason 1: rejection-time price is not recorded in the RED-2400
  deposit).** The reference against which ratios are computed is the
  earliest forward sample the extractor captured. The bias is
  disclosed in `paper/paper.md::Limitations`, and a defensive
  disclosure surface is now implemented:
  - `ClassificationDetail.first_sample_lag_min` — the earliest sample
    ageMin the classifier used as reference-price anchor. Propagated
    to the classifications frame column of the same name.
  - `AuditResult.first_sample_lag_median_min` /
    `first_sample_lag_p90_min` / `first_sample_lag_p99_min` — a
    deposit-wide lag summary.
  - `run_audit(lag_warn_median_min=5.0)` emits a `UserWarning` when
    the median lag exceeds the threshold; the summary is always
    recorded on the result regardless. Pass `0` to silence the
    warning. See `tests/test_s1_reference_price_lag.py`.
- **S3 (interval-censoring of `ageDays` at `gone`; SCOPE OUT —
  permitted reasons 1 & 3: probe cadence is not in the deposit AND
  midpoint-imputation would impose an unsupported assumption).** The
  recorded `ageDays` is an upper bound on the true age at death. The
  bias is disclosed in `paper/paper.md::Limitations`, and a
  defensive disclosure surface is now implemented:
  - `ClassificationDetail.early_death_age_min_note` = `"upper_bound"`
    on every event that has a `gone` transition. Propagated to the
    classifications frame column of the same name.
  - `AuditResult.boundary_sensitive_early_death_count` counts events
    whose recorded age sits within
    `boundary_sensitive_window_min` (default ±10 min) of the 60-min
    threshold. `run_audit` emits a `UserWarning` naming the count.
  - New `sensitivity_early_death_threshold(deposit, lower=45,
    upper=90, step=5)` helper reruns the audit across a threshold
    range and returns a DataFrame with per-threshold tier shares so
    users can bracket the boundary sensitivity numerically.
  - See `tests/test_s3_early_death_interval_censoring.py`.

### Numerical impact of the S2 / S4 / S5 / S6 closures on the corrected
### v2 outputs (RED-2400 v2 deposit)

- Primary denominator: 6,660 → 6,363 (297 right-truncated events
  excluded).
- overall `saved_windowed`: 9.07 % → 9.16 %
- overall `saved_early_death`: 9.98 % → 10.45 %
- overall `flat`: 35.00 % → 34.78 %
- overall `missed`: 2.12 % → 2.15 %
- overall `unclassifiable`: 43.83 % → 43.45 %
- `save_to_miss_conservative`: 4.2837 → 4.2555
- `save_to_miss_combined`: 9.0000 → 9.1095
- `n_duplicate_outcome_rows`: — → 51
- `truncated_events_n`: — → 297
- Every per-filter row now carries `<tier>_ci_lo` / `<tier>_ci_hi`.

The corrected outputs are regenerated in
`tests/corrected_v2_outputs.json` (v2.0.1 refresh).

### Documentation and diagnostics

- `LinkageDiagnostic` docstring rewritten to distinguish
  registry-side and outcome-side counts. Three new companion fields:
  `n_linked_registry_events`, `n_distinct_outcome_event_ids`,
  `n_orphan_outcome_event_ids`. The pre-existing
  `n_events_with_outcomes` field is retained (payload compatibility)
  and is equal to `n_distinct_outcome_event_ids`.
- On the RED-2400 v2 deposit: the corrected registry-side linkage
  count is `n_linked_registry_events = 3,333` (matching the P4
  audit's exact-tuple linkage of 3,333 / 6,660 = 50.0 %); the
  outcome-side `event_id` collapse is `n_distinct_outcome_event_ids
  = 3,878 = 3,333 + 545 orphan outcome ids`. The v2.0.0 pre-release
  paper narrative that quoted 3,878 as "events with attachable
  outcome rows" is corrected in `paper/paper.md`.
- Third-party scholarly references added to `paper/paper.bib`
  (Hand & Henley 1997; Crook & Banasik 2004; Cameron & Miller 2015;
  Sandve et al. 2013; Wilkinson et al. 2016; Taschuk & Wilson 2017;
  Di Cosmo et al. 2020; Xu et al. 2023; Angeris & Chitra 2020;
  Cernera et al. 2023) placing the toolkit in the reject-inference,
  reproducibility-software, FAIR, DEX-microstructure, and
  on-chain-adversarial-token literature.
- `CITATION.cff` YAML indentation fixed (`given-names`, `orcid`,
  `affiliation` now nest under `authors[0]` correctly).
- Public source files scrubbed of internal audit-workspace path
  references so the release ZIP no longer echoes them.
- `paper.md` gains explicit sections **State of the field**,
  **Definitions** (numerator/denominator/linkage conditioning for
  every reported metric), and **AI usage disclosure**, per current
  JOSS submission requirements.

## [Unreleased] -- v2.0.0 draft (not yet tagged)

### Scientific-correctness impact

- **Fix event/mint conflation in `classify_dataset`.** v1.0.0 pooled
  outcome rows by `mint` alone, so every rejection event on a repeat
  mint received the same pooled trajectory. On the RED-2400 v2 deposit
  6,359 of 6,660 events (95.5 %) lived on repeat mints, so the defect
  touched nearly every event. The v2 dispatch attaches outcomes per
  event via the canonical
  `event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|"
  + rejectReason).hexdigest()[:16]`
  from the P11 canonicalization spec.
- **Numerical impact on the RED-2400 v2 corpus** (6,660 events;
  see `TEST_EVIDENCE/v1_vs_v2_side_by_side.txt`):
  - overall saved_windowed: 53.35 % → 9.07 %
  - overall missed:  25.62 % → 2.12 %
  - overall unclassifiable:  0.02 % → 43.83 %
  - save_to_miss (conservative): 2.08 → 4.28
  - save_to_miss (combined):  2.19 → 9.00
- **Users must not cite v1.0.0 numbers** as event-level scientific
  results. The v1.0.0 tag is preserved for reproducibility of v1-era
  artifacts only.

### Added

- `red2400_toolkit/event_model.py` -- canonical event/sample identity
  primitives: `parse_timestamp_to_ms`, `normalize_reason`,
  `compute_event_id`, `compute_sample_id`, `attach_event_ids`,
  `attach_outcomes_by_event`, `select_rejections_by_mode`. Adopts P11
  spec §5-6 verbatim (`event_id` truncation + timestamp normalization).
- Estimand-mode dispatch: `MODE_EVENT` (default), `MODE_FIRST_EVENT_PER_MINT`,
  `MODE_LATEST_EVENT_PER_MINT`, `MODE_MINT_SUMMARY`, and
  `MODE_LEGACY_MINT_POOLED` (v1 reproduction, emits `DeprecationWarning`).
- Loud-fail orphan handling: `classify_dataset(on_missing='raise')` is the
  new default; `on_missing='quarantine'` is opt-in. Silent mint-pooling is
  gone.
- `tests/oracle.py` -- independent oracle written without importing
  `red2400_toolkit`; used by the event-level test suite.
- `tests/conftest.py::ADVERSARIAL_HAND_TABLE` -- hand-computed expected
  tier for every event in the adversarial fixture (repeat-mint,
  same-filter-twice, overlapping windows, identical timestamps, missing
  prices, absent horizons, early death, orphan rejection).
- `tests/test_event_model.py` -- 31 unit tests for the event-model
  primitives (timestamp parsing, event_id determinism / uniqueness /
  P11-frozen-vector regression, orphan handling, estimand modes).
- `tests/test_classifier_event_level.py` -- load-bearing correctness gate
  (toolkit-vs-hand-table, oracle-vs-hand-table, toolkit-vs-oracle,
  event-isolation, orphan-raise / quarantine, mode row-count checks).
- `tests/test_property_invariants.py` -- row-order invariance,
  duplicate-row idempotence, event isolation under injected orphan
  outcomes, timestamp representation equivalence, timestamp round-trip,
  schema-missing hard-fail.
- `scripts/generate_corrected_v2_outputs.py` -- regenerator for the v2
  reference outputs (kept alongside the legacy generator for
  auditability; not used by any test as an oracle).

### Changed

- `classify_dataset` return frame is now indexed by `event_id` (was
  `mint`) and carries `mint`, `filter_id`, `rejectTs_utc_ms`, `mode`,
  plus the existing tier-diagnostic columns. Downstream code that
  looked up rows by mint should either use `MODE_FIRST_EVENT_PER_MINT`
  or reset the index.
- `AuditResult` gains `mode` and `linkage_diagnostic` fields. The
  `to_dict()` payload keeps a `n_rejections` alias equal to `n_events`
  for tool-chain compatibility during the migration.
- `early_death_validator.matched_comparison` handles both event-level
  (v2) and mint-indexed (legacy) classification frames by dispatching
  on the presence of a `mint` column.
- `scripts/generate_expected_outputs.py` now writes to
  `tests/legacy/expected_outputs_v1_defective.json` and runs under
  `MODE_LEGACY_MINT_POOLED` -- the file is a regression witness of the
  v1 defect, not an oracle.

### Retained (unchanged)

- `classify_event` single-event API -- the defect was in dispatch, not
  in per-event classification.
- Tier constants, thresholds, and observation-window semantics.
- Loader schema (`red2400_loader.py`).

### Removed

- The byte-identical CI test that locked production output to
  `tests/expected_outputs.json`. That test certified reproduction of
  the v1 defect. It has been replaced by the adversarial event-level
  correctness gate. The legacy fixture is retained under
  `tests/legacy/` for reproducing v1 numbers via
  `MODE_LEGACY_MINT_POOLED`.

### Deprecated

- `MODE_LEGACY_MINT_POOLED` is available only for auditing v1-era
  artifacts and emits `DeprecationWarning` on every call. It will be
  removed no earlier than v3.0.0.

### Migration notes

Users who consumed v1.0.0 outputs must expect the corrected v2 numbers
to differ. The v1 numbers over-attributed saved_windowed outcomes to
repeat-mint events (95.5 % of the corpus). The v2 numbers reveal the
substantial event population (43.83 %) with no attachable forward
trajectory -- an unclassifiable outcome, not a saved / missed one.

For an exact reproduction of v1 numbers on a v2 install, call:
```python
from red2400_toolkit import run_audit, load_deposit, MODE_LEGACY_MINT_POOLED
d = load_deposit("/path/to/RED-2400")
res = run_audit(d, mode=MODE_LEGACY_MINT_POOLED)
```
This emits a `DeprecationWarning` and reproduces v1.0.0's per-filter
table and save-to-miss ratios.

## [1.0.0] -- 2026-06-05

Initial release. **Contains the mint-collapse defect described above.**
Preserved as a git tag for auditability; not recommended for citation
of event-level results. See `README.md` correctness notice.
