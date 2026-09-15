# v1.0.0 Scientific Correction Notice

**Repository:** `red2400-replication-toolkit`
**Notice issued:** 2026-09-15
**Superseded by:** `v2.0.1`
**Sole author:** Arati Uday Kamat, ORCID [0009-0000-4781-312X](https://orcid.org/0009-0000-4781-312X)

---

## 1. Affected version

**`v1.0.0`** (git tag `v1.0.0`, commit
`9fb2b3ed3a718576a4f32f5faf8b6c92f80b4e46`, first published
2026-06-04). The v1.0.0 tag is preserved unchanged for historical
evidence.

## 2. Exact defect

Function
`red2400_toolkit.prfs_classifier.classify_dataset`
grouped outcome rows by **mint** alone and passed the same
mint-level trajectory to every rejection event on that mint. The
canonical event identity documented in the P11 spec
(`sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" + rejectReason)`)
was not used for dispatch.

On the RED-2400 v2 deposit (`10.5281/zenodo.19989074`), 6,359 of the
6,660 rejection events (**95.5 %**) live on mints that carry more
than one rejection event. Every one of those 6,359 events therefore
received a pooled outcome trajectory rather than its own.

## 3. Affected function / code path

| module | function | line range (v1.0.0) |
|---|---|---|
| `red2400_toolkit/prfs_classifier.py` | `classify_dataset` | dispatch keyed by `mint` |
| `red2400_toolkit/audit_runner.py`    | `run_audit`        | inherits the mint-pooled dispatch |
| `red2400_toolkit/early_death_validator.py` | `matched_comparison` | mint-indexed lookup (S2 co-defect) |

## 4. Scientific consequence

The following per-filter and overall quantities in v1.0.0 outputs
**do not measure per-event outcomes**:

- `saved_windowed` (per filter and overall)
- `missed` (per filter and overall)
- `unclassifiable` (per filter and overall)
- `save_to_miss_conservative`
- `save_to_miss_combined`
- Every derived tier attribution and per-filter table
- The `matched_comparison` right-censoring counts (S2)

Because pooling merges multiple events' outcomes into one, per-event
distributions and any ratio computed from them are systematically
biased. The direction and magnitude of the bias vary by filter
depending on how repeat mints are distributed within each filter.

## 5. Affected published / released numerical outputs

The following v1.0.0 artefacts contain per-event tables and
save-to-miss ratios that reproduce the defective mint-pooled
dispatch and **should not be cited as event-level scientific findings**:

- `tests/expected_outputs.json` in the v1.0.0 tag (now retired to
  `_LEGACY_v1_reference/expected_outputs_v1_defective.json` in
  `v2.0.1`);
- The paper-side per-filter tables in `paper/paper.md` at the v1.0.0
  tag (`bba505a` and earlier);
- Any downstream artefact derived from v1.0.0 outputs.

The **dataset itself** (Zenodo record `10.5281/zenodo.19989074`) is
unaffected — only the classifier's dispatch layer was defective. The
paper's linkage counts (6,660 events, 169,123 outcome rows, 1,837
lifecycle snapshots) are unaffected.

## 6. Corrected implementation

`v2.0.1` replaces mint-keyed dispatch with per-event dispatch keyed
by the P11 canonical event identity:

```
event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" + rejectReason)
```

Public API additions in `v2.0.1`:

- `red2400_toolkit.event_model` — event identity primitives, timestamp
  normalisation, estimand-mode enum, linkage diagnostic;
- `run_audit(..., mode='event' | 'first_event_per_mint' |
  'latest_event_per_mint' | 'mint_summary' | MODE_LEGACY_MINT_POOLED,
  on_missing='raise' | 'quarantine')`;
- `Result.per_filter` now carries 95 % Wilson score intervals on
  every tier (S6).

The v1 estimand is preserved behind `MODE_LEGACY_MINT_POOLED` (emits
`DeprecationWarning`, blocked from composing with
`early_death_validator`) so v1-era outputs remain reproducible for
audit purposes.

## 7. Corrected results (RED-2400 v2 corpus, 6,660 events)

Independently reproduced from a fresh clean-clone install of the
`v2.0.1` tree
(`PHASE5_CLEAN_CLONE_REPRODUCTION.md`, `PHASE5_NUMERICAL_REPRODUCIBILITY.md`).
Values reported to 4 decimal places.

| Overall metric              | v1.0.0 (mint-pooled) | v2.0.1 (event-keyed) |
|-----------------------------|---------------------:|---------------------:|
| saved_windowed %            | 53.3500              |  9.0700              |
| missed %                    | 25.6200              |  2.1200              |
| unclassifiable %            |  0.0200              | 43.8300              |
| save_to_miss_conservative   |  1.7500              |  3.7000              |
| save_to_miss_combined       |  2.1900              |  9.0000              |

Per-filter tables and Wilson intervals are in `CHANGELOG.md` and in
the v2 `paper/paper.md`. The filter_8 (n = 19) small-cell row is
reported with a 95 % Wilson interval of [0.94 %, 24.64 %] on
`saved_windowed = 5.26 %`.

## 8. Superseding version

**`v2.0.1`** — git tag `v2.0.1`, commit
`05b0daffd1785d38aabea11989dd824755691e99`, release archive SHA-256
`981e4a008e37b8cd46b340f612fada7905821d0fdf10e42abf5cbd27b38eeb62`
(`git archive --format=tar.gz v2.0.1`). Released 2026-09-15.

## 9. Digital object identifiers

Two SEPARATE DOIs cover this project. Do not conflate them:

- **Dataset DOI (unchanged, unaffected by this correction):**
  `10.5281/zenodo.19989074` — the RED-2400 v2 benchmark dataset
  (rejections, outcomes, lifecycle CSVs). The dataset content and
  license (CC-BY-4.0) are not modified.
- **Software concept DOI (v2.0.1):** PENDING at the time this notice
  is committed. Will be minted by the GitHub–Zenodo integration when
  the `v2.0.1` tag is picked up (see
  `PHASE6_ZENODO_LINKAGE_INSTRUCTIONS.md`). The badge in `README.md`
  and the `doi:` field in `CITATION.cff` are staged for update to the
  software DOI as soon as it is issued.

## 10. Downstream citations

At the 2026-09-15 audit, no external work has been located that
cites the v1.0.0 per-event tables or save-to-miss ratios. The
citation search will be repeated at the time of the JOSS
submission.

## 11. Availability of this notice

- File at the repository root of `v2.0.1`:
  [`V1_CORRECTION_NOTICE.md`](./V1_CORRECTION_NOTICE.md).
- Attached to the `v1.0.0` GitHub release description (release note).
- Referenced in the description of the corresponding Zenodo record
  for `v1.0.0` (author-side update on Zenodo).

---

This notice was written by the sole author of the RED-2400
Replication Toolkit. It supersedes any earlier per-event outcome
statement issued under the `v1.0.0` release. The `v1.0.0` git tag,
git history, and existing Zenodo v1 record are preserved unchanged.
