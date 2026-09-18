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
  - name: Independent Researcher, United States
    index: 1
date: 17 September 2026
bibliography: paper.bib
archive: https://archive.softwareheritage.org/swh:1:rev:05b0daffd1785d38aabea11989dd824755691e99
---

# Summary

The RED-2400 Replication Toolkit is a Python package that attaches
observed forward outcomes to individual algorithmically-rejected
trading events and reports per-filter outcome distributions. It
operates on the public RED-2400 benchmark dataset [@kamat2026red2400]:
6,660 rejection events observed on a live Solana decentralised-exchange
filter stack over 22 calendar days (2026-04-10 to 2026-05-02), plus
169,123 forward-outcome observations and 1,837 lifecycle snapshots.

The toolkit validates the deposit schema, attaches each rejection
event to its own forward-outcome trajectory through a canonical
event-identity primitive, applies a documented five-tier outcome
classification, and reports per-filter distributions and descriptive
save-to-miss ratios. It ships an independent reference implementation
of the rule as a test oracle, an adversarial fixture with
hand-computed expected tiers, and a legacy compatibility mode that
reproduces the defective mint-pooled dispatch of the v1.0.0 release
for audit purposes.

The v2 release corrects a scientific-correctness defect present
through v1.0.0 (see "Correction disclosure"). Observed event-level
results reported by v2 therefore differ substantially from v1 outputs
on the same deposit.

# Statement of need

Filter-gated algorithmic trading systems on decentralised exchanges
reject most candidate tokens they see. Whether a rejection criterion
is *associated with* subsequently adverse observed forward outcomes is
answerable only if the specific rejected event is followed and the
outcome attached to that event, not to its mint aggregate. This is the
classical reject-inference challenge of credit-scoring evaluation
[@hand1997statistical; @crook2004reject]. In an on-chain filter
setting it re-appears with three additional obstacles absent from
prior tooling: (1) a canonical event identity so two rejections of the
same asset at different times are not conflated, (2) explicit
propagation of missing outcome linkage so counts of included and
excluded events are auditable, and (3) an independent reference
implementation against which the primary classifier can be checked.
Research-software practice [@sandve2013ten; @taschuk2017ten] recommends
exactly this triangulation of dispatch, oracle, and hand-worked fixture
as a durable reproducibility contract.

The toolkit supplies all three. The event-identity primitive follows
the frozen P11 canonicalisation spec [@kamat2026p11] as a
deterministic SHA-256 truncation, a content-addressable identifier
compatible with the FAIR principles [@wilkinson2016fair] and with
software-and-data citation guidance [@dicosmo2020referencing]. A
companion oracle (`tests/oracle.py`) is written from the paper spec
without importing the production classifier and is compared to it on
every event of an adversarial fixture.

# State of the field

Peer-reviewed treatments of decentralised-exchange microstructure focus
on price and liquidity mechanics of automated market makers
[@xu2023sok; @angeris2020improved] rather than on outcome distributions
of *rejected* candidates. Empirical work on adversarial short-lived
tokens [@cernera2023token] documents the population most often rejected
but does not classify each rejection's observed outcome. Reject
inference is well developed in credit scoring
[@hand1997statistical; @crook2004reject], but its methods assume a
supervised loss on the retained side of the selection boundary. The
RED-2400 Replication Toolkit occupies the adjacent niche: it does not
fit a reject-inference model; it makes the per-event linkage between
rejection and observed forward outcome auditable so that any subsequent
modelling or descriptive analysis is conducted on a fixture with
documented linkage properties.

# Software design

The package comprises six modules exposed through `red2400_toolkit`:

- `red2400_loader` reads the three CSV files, validates them against a
  documented schema, and raises `SchemaError` on drift.
- `event_model` implements canonical event and sample identity
  primitives, timestamp normalisation to UTC epoch-ms, the estimand
  mode enumeration (including `MODE_LEGACY_MINT_POOLED`), and the
  linkage diagnostic with loud-fail orphan handling.
- `prfs_classifier` implements the five-tier outcome-classification
  rule [@kamat2026audit] at the single-event level and refuses to
  silently mint-pool.
- `audit_runner` composes per-filter distributions and aggregate
  save-to-miss ratios and attaches the linkage diagnostic to the
  result.
- `early_death_validator` performs the matched-comparison lifecycle
  check at the event level.
- `figure_generator` regenerates two audit figures when `matplotlib`
  is available.

**Architectural trade-offs.** Two dispatch modes are offered because
audit continuity requires the defective v1.0.0 pooled dispatch remain
reproducible on demand, but scientific correctness requires the
corrected event-keyed dispatch be the default and never be selected
silently. On the RED-2400 v2 deposit 95.5% of events sit on repeat
mints, so mint-pooled dispatch conflates outcome trajectories at
population scale. The legacy mode is retained as an explicit named
enum (`MODE_LEGACY_MINT_POOLED`), gated by a `DeprecationWarning`,
and raises `LegacyModeError` when composed with
`early_death_validator`.

**Oracle independence.** `tests/oracle.py` implements the five-tier
rule from scratch without importing `red2400_toolkit`. Every
adversarial event is classified independently by (1) the production
classifier, (2) the oracle, and (3) a hand-tabulated expected outcome
in `tests/conftest.py`; the three must agree.

**Reproducibility design.** Pinned dependency versions
(`requirements.txt`), a `SEMVER_POLICY.md` binding scientific-behaviour
changes to a major-version bump, a release-manifest with SHA-256 sums
of the wheel, sdist, and source-release ZIP, and per-event provenance
in `AuditResult.linkage_diagnostic` let any downstream reanalysis
join back to the deposit rows it consumed.

# Correction disclosure (v1.0.0 defect)

`prfs_classifier.classify_dataset` in v1.0.0 grouped outcome rows by
`mint` alone, so every rejection event on a repeat mint received the
same pooled per-mint forward trajectory. On the RED-2400 v2 deposit,
6,359 of 6,660 events (95.5%) live on repeat mints, so the defect
touched nearly every event. v2 attaches outcomes per event through the
canonical `event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms +
"|" + rejectReason).hexdigest()[:16]` and refuses to mint-pool by
default. v1.0.0 event-level results must not be cited as v2 scientific
truth. Full arithmetic in `V1_CORRECTION_NOTICE.md`.

# Data linkage

Not every registry rejection event has an attachable forward-outcome
trajectory, and outcome rows can carry `event_id` values that match no
registry event. The toolkit reports both sides through
`AuditResult.linkage_diagnostic`. Two counts are distinct:

- **`n_linked_registry_events = 3,333`**: registry rejection events
  with at least one attachable outcome row. This is the scientific
  denominator for per-filter shares.
- **`n_distinct_outcome_event_ids = 3,878`**: distinct outcome-side
  `event_id` values, of which `n_orphan_outcome_event_ids = 545` do
  not match any registry event after normalisation and are surfaced
  rather than silently attached. The registry-side partition is
  `3,333 + n_orphan_rejections (3,327) = 6,660`.

Exact-key duplicate outcome rows are collapsed prior to
classification; the deposit carries 51 such duplicates. Right-truncated
events (24-hour forward window extending past `max(sampleTs)`) are
excluded from the primary denominator by default and surfaced through
`AuditResult.truncated_events_n`; 297 events are so truncated, giving
a corrected primary denominator of 6,363. The pre-S4 estimator is
available via `include_truncated=True`, which emits a
`DeprecationWarning`.

Every per-filter and overall row carries 95% Wilson score intervals;
for example filter_8 (n = 19) reports `saved_windowed = 5.26%` with a
95% Wilson interval of [0.94%, 24.64%]. Cluster-robust inference on
repeated mints [@cameron2015practitioner] remains out of scope. The
complete linkage arithmetic is in `docs/DATA_LINKAGE.md`.

# Testing

The v2.0.1 test suite defines 96 tests. On a clean Python 3.12
environment `pytest tests/` collects all 96 and reports **95 passed,
1 skipped** in about 1.95 seconds; the skipped test is gated on
`RED2400_DEPOSIT_DIR` pointing at a local copy of the RED-2400 v2
deposit. Python 3.10 and 3.11 legs are documented in
`DEVELOPER_SETUP.md`.

The suite covers unit tests for the event-identity primitives (with a
frozen regression vector against the P11 spec), the three-way oracle
comparison on every adversarial event, property-invariance tests
(row-order, timestamp representation, duplicate-outcome idempotence,
event isolation, schema hard-fail), defaults-and-guards tests,
dedicated S2, S4, S5, and S6 regression suites, and a real-deposit
legacy regression witness confirming `MODE_LEGACY_MINT_POOLED`
reproduces v1.0.0 numbers exactly.

# Research impact statement

This is a first public release under the corrected event-keyed
dispatch; external adoption has not yet accrued. Realised research
use to date is limited to reproducing the linkage counts and
per-filter tables of the companion audit paper [@kamat2026audit]
against the public RED-2400 v2 deposit [@kamat2026red2400].

The toolkit is positioned to support observational follow-up work on
filter-gated algorithmic-trading systems where forward outcomes of
rejected events are recoverable. Any dataset that emits `event_id`
under the P11 rule [@kamat2026p11] can be audited by the same toolkit
without adapter code. The three-way triangulation documents the
classifier's semantics precisely enough for third-party replication
without recourse to the maintainer, and the per-filter distributions,
save-to-miss ratios, and linkage diagnostic form the primary inputs
that downstream statistical work (for example clustered inference
over repeated mints [@cameron2015practitioner]) requires at event
level. The toolkit does not produce trading recommendations and does
not support live-market decision-making.

# Limitations

- The classifier is calibrated to the RED-2400 v2 deposit schemas;
  adapters for other datasets must preserve the event-identity
  contract in `event_model.py`.
- Roughly 43% of RED-2400 v2 primary events classify as
  `unclassifiable`; downstream inference must decide how to treat
  this share.
- The audit is observational and does not identify counterfactual
  outcomes of accepted events. Reject inference is compatible with
  the toolkit's outputs but is not implemented here.
- **Reference-price bias (S1).** Ratios are anchored at the earliest
  captured forward sample, not the rejection-time price; the true
  rejection-time price must be reconstructed from an external
  on-chain price archive. Full scope disclosure in the companion
  audit paper [@kamat2026audit].
- **Interval-censoring at `gone` (S3).** Lifecycle `ageDays` at
  `gone` is an upper bound on the true age at death; events near the
  60-minute cap are boundary-sensitive.
- **Right-censoring (S2, corrected).** Mints absent from the
  lifecycle file are treated as right-censored rather than as
  observed survivors; the pre-S2 estimator is available via
  `include_censored=True`.
- **Right-truncation (S4, corrected).** Events whose 24-hour forward
  window extends past `max(sampleTs)` are excluded from the primary
  denominator (297 of 6,660 on RED-2400 v2); pre-S4 is available via
  `include_truncated=True`.
- Community adoption evidence is limited: v2 is a first public
  release under the corrected dispatch.

# AI usage disclosure

AI assistance was used during v2 preparation for code refactoring,
test scaffolding, documentation drafting, prose editing, and citation
formatting. The full enumeration of vendor, tool or model name,
version identifier, usage window, and per-artifact scope is recorded
by the sole author in `docs/AI_USAGE_DISCLOSURE.md`; that document is
the authoritative record.

The linkage counts, classifier definitions, five-tier rule and its
edge cases, correction disclosure of the v1.0.0 mint-pooling defect,
and reproducibility claims were verified independently of any AI
assistance through hand-computed adversarial fixtures in
`tests/conftest.py`, the independent oracle in `tests/oracle.py`, and
direct arithmetic reconciliation against the public deposit. The sole
author made all architectural and scientific-design decisions and
reviewed all AI-assisted output before it entered the repository or
this paper.

# Acknowledgements

Thanks to reviewers of the companion audit paper for feedback on the
event-identity contract, and to the OpenJournals JOSS documentation
maintainers for a clear submission template that this paper follows.

# References
