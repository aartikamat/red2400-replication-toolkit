# Governance

## Project scope

RED-2400 Replication Toolkit is a scientific reproducibility library
for outcome-classified filter auditing of algorithmic DEX trading
systems against the RED-2400 public benchmark and, over time, against
compatible datasets that adopt the canonical event model.

**In scope**:

- Correct, deterministic implementation of the five-tier PRFS
  classification rule.
- Canonical event identity (see `red2400_toolkit/event_model.py` and
  the P11 canonicalization spec).
- Adapters for datasets that carry the required event-key fields
  (`mint`, `rejectTs`, `rejectReason`).
- Statistical machinery (clustered / bootstrap CIs, multiple-testing
  control) around the classifier's per-event output.
- Reproducibility of prior releases via preserved tags and legacy
  modes (never overwriting history).

**Out of scope**:

- Live-market trading advice or automated execution.
- Custom private-dataset analyses.
- Dataset construction (that lives in the RED-2400 pipeline
  repositories, not here).

## Roles

- **Maintainer**: Arati Uday Kamat. Approves releases, adjudicates
  design decisions, and holds commit rights on `main`.
- **Contributors**: anyone opening issues or pull requests.

## Decision-making

- **Documentation-only changes** (typos, examples, docstring
  corrections): merged by the maintainer at their discretion.
- **Non-behavioural code changes** (refactors that preserve semantics
  and test outputs): require passing CI and one maintainer review.
- **Behavioural changes**: require an issue describing the motivation,
  a design proposal (usually in the issue thread), passing CI,
  updated documentation, and an entry in `CHANGELOG.md`. If the change
  affects scientific outputs, it also requires:
  - An updated adversarial fixture and hand-worked expected table.
  - Comparison against the independent oracle (`tests/oracle.py`).
  - A migration note explaining how prior outputs are affected.

## Release cadence

Releases are cut when a coherent set of changes reaches a stable
state, not on a fixed calendar. Semantic-versioning policy is
documented in `SEMVER_POLICY.md`.

Every release is:

- Tagged on `main`.
- Archived to Zenodo with a software-specific DOI (distinct from the
  RED-2400 dataset DOI).
- Announced in `CHANGELOG.md` with an "Impact on scientific outputs"
  section when relevant.

## Change of maintainer

If the current maintainer becomes unavailable, the maintainer role
transfers to a designated successor identified in the last-updated
version of this file. Absent a designation, the community may open a
pull request against `GOVERNANCE.md` proposing continuity; changes
require a two-week comment period.

## Non-goals for the project

- **No manufactured activity.** The maintainer will not open issues,
  PRs, or discussions to satisfy an external activity gate (for
  example, JOSS's active-development requirement). Every issue must
  correspond to a real task; every PR to a real change.
- **No history rewriting.** `main`'s history is append-only; tags are
  never deleted or moved. Corrections are added as new commits or new
  tags, not by amending or force-pushing.

## Amendments

This document is amended by pull request. Substantive changes are
open for community comment for at least seven calendar days before
merging.
