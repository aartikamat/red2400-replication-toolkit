---
title: 'RED-2400 Replication Toolkit: Event-Level Auditing of Algorithmic Trading Rejection Filters'
tags:
  - Python
  - decentralized finance
  - algorithmic trading
  - reproducibility
  - reject inference
  - benchmark dataset
  - event identity
authors:
  - name: Arati Uday Kamat
    orcid: 0009-0000-4781-312X
    affiliation: 1
affiliations:
  - name: Independent Researcher, McKinney, Texas, USA
    index: 1
date: 23 August 2026
bibliography: paper.bib
archive: https://archive.softwareheritage.org/swh:1:rev:a85bf1ff1eb4af345752555a3a1844e5b172bf3e
---

# Summary

The RED-2400 Replication Toolkit is a Python software package that
attaches observed forward outcomes to individual
algorithmically-rejected trading events and reports per-filter
outcome distributions. It operates on the public RED-2400 benchmark
dataset [@kamat2026red2400], which contains 6,660 rejection events
observed on a live Solana decentralised-exchange filter stack over
a 22-calendar-day window (2026-04-10 to 2026-05-02), together with
169,123 forward-outcome observations and 1,837 lifecycle snapshots.

The toolkit reads the three deposit files, validates their schema,
attaches each rejection event to its own forward-outcome trajectory
through a canonical event-identity primitive, applies a documented
five-tier outcome-classification rule, and reports per-filter
observed outcome distributions and descriptive save-to-miss ratios.
It exposes an independent reference implementation of the rule as
a test oracle, an adversarial fixture with hand-computed expected
tiers, and a legacy compatibility mode that reproduces the
defective mint-pooled dispatch of the v1.0.0 release for audit
purposes.

The v2 release corrects a scientific-correctness defect present
through v1.0.0 (see "Correction disclosure"). Observed event-level
results reported by v2 therefore differ substantially from v1
outputs on the same deposit.

# Statement of need

Filter-gated algorithmic trading systems on decentralised exchanges
reject most candidate tokens they see. Whether a rejection
criterion is *associated with* subsequently adverse observed
forward outcomes, relative to favourable ones, is answerable only
if the specific rejected event is followed and the resulting
outcome is attached to that event rather than to its mint
aggregate. This observational reject-inference question is the
classical challenge of credit-scoring evaluation
[@hand1997statistical; @crook2004reject]. In an on-chain
filter setting the same problem re-appears with three additional
obstacles that are absent from prior tooling: (1) a canonical event
identity so two rejections of the same asset at different times are
not conflated, (2) explicit propagation of missing outcome linkage
so counts of included and excluded events are auditable, and (3)
an independent reference implementation against which the primary
classifier can be checked. Published research-software practice
[@sandve2013ten; @taschuk2017ten] recommends exactly this
triangulation of dispatch, oracle, and hand-worked fixture as a
durable reproducibility contract.

The RED-2400 Replication Toolkit supplies all three. The event
identity primitive follows the frozen P11 canonicalisation spec
[@kamat2026p11] as a deterministic SHA-256 truncation, a
content-addressable identifier compatible with the FAIR principles
[@wilkinson2016fair] and with software-and-data citation guidance
[@dicosmo2020referencing]. Event linkage produces a diagnostic that
names how many registry rejection events link back to outcome rows,
how many are orphaned, how many outcome-side `event_id` values do
not appear on the registry side, and how many outcome rows carry a
malformed key. A companion oracle (`tests/oracle.py`) is written
from the paper spec without importing the production classifier and
is compared to the production classifier on every event of an
adversarial fixture.

# State of the field

Peer-reviewed treatments of decentralised-exchange microstructure
focus on price and liquidity mechanics of automated market makers
[@xu2023sok; @angeris2020improved] rather than on outcome
distributions of *rejected* candidates. Empirical work on
adversarial short-lived tokens [@cernera2023token] documents the
population most often rejected but does not classify each
rejection's observed outcome. Reject inference is well developed
in credit scoring [@hand1997statistical; @crook2004reject], but its
methods assume a supervised loss on the retained side of the
selection boundary. The RED-2400 Replication Toolkit occupies the
adjacent niche: it does not fit a reject-inference model; it makes
the per-event linkage between rejection and observed forward
outcome auditable so that any subsequent modelling or descriptive
analysis is conducted on a fixture with documented linkage
properties.

# Software design

The package comprises six modules exposed through `red2400_toolkit`, each
addressing one design constraint of on-chain filter auditing:

- `red2400_loader` reads the three CSV files, validates them against
  a documented schema, and raises `SchemaError` on drift.
- `event_model` implements canonical event and sample identity
  primitives, timestamp normalisation to UTC epoch-ms, the estimand
  mode enumeration (including `MODE_LEGACY_MINT_POOLED`), and the
  linkage diagnostic with loud-fail orphan handling.
- `prfs_classifier` implements the five-tier outcome-classification
  rule [@kamat2026audit] at the single-event level and refuses to
  silently mint-pool; supports `on_missing='raise'|'quarantine'`.
- `audit_runner` composes per-filter distributions and aggregate
  save-to-miss ratios and attaches the linkage diagnostic to the
  result.
- `early_death_validator` performs the matched-comparison lifecycle
  check at the event level and refuses legacy mint-indexed frames.
- `figure_generator` regenerates two audit figures when
  `matplotlib` is available.

Every module ships with hand-worked adversarial fixtures under
`tests/`. Property-invariance tests exercise the dispatch contract,
and a legacy regression test (gated on `RED2400_DEPOSIT_DIR`)
verifies that `MODE_LEGACY_MINT_POOLED` still reproduces v1.0.0
numbers exactly.

**Architectural trade-offs.** Two dispatch modes are offered because
audit continuity requires that the defective v1.0.0 pooled dispatch
remains reproducible on demand, but scientific correctness requires
that the corrected event-keyed dispatch is the default and cannot be
selected silently. The corrected event-keyed mode was chosen as the
scientific default because on the RED-2400 v2 deposit 95.5 % of events
sit on repeat mints, so mint-pooled dispatch conflates outcome
trajectories at the population scale (not only at the edge). The
legacy mode is retained as an explicit named enum
(`MODE_LEGACY_MINT_POOLED`), gated by a `DeprecationWarning`, and
covered by a dedicated regression test so it cannot silently
substitute for the corrected dispatch.

**Oracle independence.** `tests/oracle.py` is a from-scratch
implementation of the five-tier rule that does not import
`red2400_toolkit`. Every adversarial event is classified independently
by (1) the production classifier, (2) the oracle, and (3) a
hand-tabulated expected outcome in `tests/conftest.py`; the three must
agree.

**Safeguards preventing legacy-mode misuse.** Selecting
`MODE_LEGACY_MINT_POOLED` emits `DeprecationWarning` at call time,
raises `LegacyModeError` when composed with `early_death_validator`,
and is excluded from the default `run_audit` code path.

**Reproducibility design.** The toolkit ships pinned dependency
versions in `requirements.txt`, a `SEMVER_POLICY.md` that binds
scientific-behaviour changes to a major-version bump, a
release-manifest with sha256 sums of the wheel/sdist/source-release
ZIP, and per-event provenance in `AuditResult.linkage_diagnostic` so
any downstream reanalysis can be joined back to the deposit rows it
consumed.

# Definitions

To keep observational and counterfactual claims separate, the
toolkit exposes only descriptive quantities:

- **Adverse-outcome observed rate (per filter)**: for events linked
  to outcome rows, the share whose earliest in-window forward
  sample crosses `MISSED_THRESHOLD = 2.0`.
- **Save-to-miss ratio (conservative)**: for linked events,
  `saved_windowed / missed`, where `saved_windowed` is the share
  crossing `SAVED_THRESHOLD = 0.5` inside the 24-hour window and
  `missed` follows the tie-break precedence in `prfs_classifier`.
- **Save-to-miss ratio (combined)**: `(saved_windowed +
  saved_early_death) / missed` on the same denominator.
- **Unclassifiable share**: events with no forward sample inside
  the window and no terminal lifecycle transition, reported so the
  classifiable denominator is auditable.

The toolkit does **not** identify the outcome a rejected event
would have had if accepted; that requires a counterfactual model
out of scope for this release.

# Correction disclosure -- v1.0.0 defect

`red2400_toolkit.prfs_classifier.classify_dataset` in v1.0.0
grouped outcome rows by `mint` alone, so every rejection event on
a repeat mint received the same pooled per-mint forward trajectory
rather than the trajectory of its own event. On the RED-2400 v2
deposit, 6,359 of 6,660 events (95.5 %) live on repeat mints, so
the defect touched nearly every event and materially changed the
per-filter observed distributions and the descriptive save-to-miss
ratios.

v2 attaches outcomes per event through the canonical
`event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" +
rejectReason).hexdigest()[:16]` and refuses to mint-pool by
default. v1.0.0 is preserved as a git tag for audit continuity;
v2 exposes `MODE_LEGACY_MINT_POOLED` that reproduces v1 numbers on
demand and emits a `DeprecationWarning`. **v1.0.0 per-filter tables
and save-to-miss ratios are not v2 scientific truth and must not
be cited as event-level results.**

# Data linkage

Not every registry rejection event has an attachable
forward-outcome trajectory, and outcome rows can carry `event_id`
values that do not match any registry event. The toolkit reports
both sides of the join explicitly through `AuditResult.linkage_diagnostic`.

Two counts must be read as distinct:

- **`n_linked_registry_events = 3,333`**: registry rejection
  events with at least one attachable outcome row. This is the
  scientific denominator for per-filter shares.
- **`n_distinct_outcome_event_ids = 3,878`**: distinct
  outcome-side `event_id` values, of which
  `n_orphan_outcome_event_ids = 545` do not match any registry
  event after normalisation and are surfaced rather than silently
  attached. The registry-side partition is
  `3,333 + n_orphan_rejections (3,327) = 6,660`.

Exact-key duplicate outcome rows (identical `event_id`, `sampleTs`,
`dexId`, `pairAddress`) are collapsed prior to classification and
their count is surfaced through
`LinkageDiagnostic.n_duplicate_outcome_rows`; the RED-2400 v2 deposit
carries 51 such extractor-side duplicates.

Right-truncated events (those whose 24-hour forward-observation
window extends past the deposit's latest sample timestamp) are
excluded from the primary per-filter denominator by default and
surfaced separately through `AuditResult.truncated_events_n`. The
RED-2400 v2 deposit carries 297 such events; the corrected primary
denominator is therefore 6,363. Users who require the pre-S4
estimator can pass `include_truncated=True`, which emits a
`DeprecationWarning` and reproduces v2.0.0 pre-S4 numbers.

Downstream, 43.4 % of the 6,363 primary events fall to the
`unclassifiable` tier because they have no in-window forward sample
or terminal lifecycle transition. The toolkit does not silently
discard these events; per-filter counts of included events are
auditable. Every per-filter and overall row also carries 95 %
Wilson score intervals as `<tier>_ci_lo` / `<tier>_ci_hi` companion
columns; for example filter_8 (n = 19) reports
`saved_windowed = 5.26 %` with a 95 % Wilson interval of
[0.94 %, 24.64 %]. Cluster-robust inference on repeated mints
[@cameron2015practitioner] remains out of scope for this release.

The complete linkage arithmetic and the full 6,660-event partition
are documented in `docs/DATA_LINKAGE.md` and reproducible from
`red2400_toolkit.audit_runner.run_audit`.

# Testing

The v2.0.1 test suite defines 96 tests. On a clean Python 3.12
release-candidate environment, `pytest tests/` collects all 96 and
reports **95 passed, 1 skipped** in about 1.95 s. The skipped test
is gated on `RED2400_DEPOSIT_DIR` pointing at a local copy of the
RED-2400 v2 deposit; enabling that env-var (and, separately,
installing `matplotlib` for the figure tests) causes 96 of 96 to
pass. The Python 3.10 and 3.11 legs of the verification matrix
are documented in `DEVELOPER_SETUP.md`.

The suite covers unit tests for the event-identity primitives
(with a frozen regression vector against the P11 spec), a
three-way comparison on every adversarial event between the
production classifier, the independent oracle
(`tests/oracle.py`, written without importing `red2400_toolkit`),
and a hand table in `tests/conftest.py`, plus property-invariance
tests (row-order, timestamp representation, duplicate-outcome
idempotence, event isolation, schema hard-fail),
defaults-and-guards tests, dedicated S2 (right-censoring),
S4 (right-truncation), S5 (exact-key dedup), and S6 (Wilson-CI)
regression suites, and a real-deposit legacy regression witness
that confirms `MODE_LEGACY_MINT_POOLED` still reproduces v1.0.0
numbers exactly.

# Research impact statement

## A. Realised research use

The toolkit is a first public release under the corrected event-keyed
dispatch. External adoption (independent users, downstream citations,
public contributions, integrations into other software) has not yet
accrued. The realised research use to date is therefore limited to
author-side use: reproducing the linkage counts and per-filter tables
of the companion audit paper [@kamat2026audit] against the public
RED-2400 v2 deposit [@kamat2026red2400]. This statement is factual
and is not to be read as a claim of external adoption.

## B. Credible near-term significance

The toolkit is positioned to support observational follow-up work on
filter-gated algorithmic-trading systems where forward outcomes of
rejected events are recoverable, on the following concrete grounds:

- The event-identity primitive follows a frozen canonical
  specification [@kamat2026p11] and is deterministic and
  content-addressable, so any dataset that emits `event_id` under the
  same rule can be audited by the same toolkit without adapter code.
- The three-way triangulation (production classifier, independent
  oracle, hand-worked adversarial fixture) is a reproducibility
  contract [@sandve2013ten; @taschuk2017ten] that documents the
  classifier's semantics precisely enough for replication by a third
  party without recourse to the maintainer.
- The per-filter observed distributions, the save-to-miss ratios, and
  the linkage diagnostic form the primary inputs that downstream
  statistical work (for example clustered inference over repeated
  mints [@cameron2015practitioner]) requires at event level; those
  inputs were not previously available in reusable form.
- Auditing per-filter observed-outcome distributions on additional
  datasets that adopt the event-identity contract is a direct
  extension of the shipped `audit_runner` interface.
- Sensitivity analysis on the classification thresholds or
  observation window is exposed through the `AuditConfig` interface.

The toolkit does not produce trading recommendations and does not
support live-market decision-making.

# Limitations

- The classifier is calibrated to the RED-2400 v2 deposit schemas;
  adapters for other datasets need to preserve the event-identity
  contract in `event_model.py`.
- Roughly 43 % of RED-2400 v2 primary events (post-truncation)
  classify as `unclassifiable`; downstream inference must decide how
  to treat this share.
- The audit is observational and does not identify counterfactual
  outcomes of accepted events. Reject inference
  [@hand1997statistical; @crook2004reject] is compatible with the
  toolkit's outputs but is not implemented here.
- **Reference-price bias (S1, scoped-out disclosure).** The
  reference against which ratios are computed is the earliest
  forward sample the extractor captured, not the price at the
  rejection instant itself. The rejection-time price is not recorded
  in the RED-2400 deposit; anchoring the ratio at the first
  captured sample compresses both `min_ratio` and `max_ratio`
  toward 1 by an unknown amount whose sign and magnitude are
  asset-specific. Users who need the true rejection-time price must
  reconstruct it from an external on-chain price archive.
- **Interval-censoring of lifecycle age at `gone` (S3, scoped-out
  disclosure).** The lifecycle deposit records the `ageDays` at
  which a transition to `gone` was **observed** by the tracker,
  which is an upper bound on the true age at death. Per-mint probe
  cadence is not part of the deposit, so the interval bracketing
  the true event cannot be reconstructed inside the toolkit. The
  `saved_early_death` tier is assigned against the upper bound;
  events near the 60-minute cap are boundary-sensitive. Users who
  require an interval-censored survival estimator should obtain the
  tracker's raw probe log.
- **Right-censoring in matched comparison (S2, corrected).** Mints
  absent from the lifecycle file are treated as right-censored
  (`unobserved`) rather than as observed survivors; the
  matched-comparison gone-rate uses the observed denominator. The
  pre-S2 estimator is available via `include_censored=True`.
- **Right-truncation at deposit end (S4, corrected).** Events whose
  24-hour forward window extends past `max(sampleTs)` are excluded
  from the primary per-filter denominator; on the RED-2400 v2
  deposit 297 of 6,660 events are so truncated. The pre-S4
  estimator is available via `include_truncated=True`.
- The v2 release is a first public release under the corrected
  dispatch; community adoption evidence is limited.

# AI usage disclosure

AI assistance was used during v2 preparation across code
refactoring, test scaffolding, documentation drafting, prose
editing, and citation formatting. The full enumeration of vendor,
tool or model name, version identifier, usage window, and per-artifact
scope is recorded by the author in `docs/AI_USAGE_DISCLOSURE.md`. That
document is filled by the author (not by any AI) before the release
commit and JOSS submission; the row-level table is the authoritative
record.

The following scientific content was verified independently of any
AI assistance and is treated as scientific authority only after that
verification: the linkage counts, the classifier definitions, the
five-tier rule and its edge cases, the tier tables, the correction
disclosure of the v1.0.0 mint-pooling defect, and the reproducibility
claims in this paper. Verification proceeded through hand-computed
adversarial fixtures in `tests/conftest.py`, the independent
oracle implementation in `tests/oracle.py` (written from the paper
spec without importing `red2400_toolkit`), and direct arithmetic
reconciliation against the public deposit. The author made all core
architectural and scientific-design decisions and reviewed all
AI-assisted output before it entered the repository or this paper.

# Acknowledgements

Thanks to reviewers of the companion audit paper for feedback on
the event-identity contract, and to the OpenJournals JOSS
documentation maintainers for a clear submission template that
this paper follows.

# References
