# AI Usage Disclosure -- RED-2400 Replication Toolkit v2.0.1

This document enumerates the AI tools and models used during
preparation of this software release and the accompanying JOSS
manuscript. It exists to satisfy the JOSS "AI usage disclosure"
policy and to give reviewers concrete information about scope of
assistance, review, and authorial responsibility.

## Author confirmation

The sole author is Arati Uday Kamat (ORCID 0009-0000-4781-312X).
The author confirms that:

- All core design decisions for the software (event-identity
  primitive, five-tier classification rule, oracle contract,
  legacy mode gating) were made by the author, not by any AI.
- All scientific claims in the paper (linkage counts,
  save-to-miss definitions, correction disclosure, tier tables)
  were verified against the deposit and the independent oracle
  before publication.
- The author reviewed every AI-assisted line of code and prose
  before it entered the repository or paper.
- The author is responsible for the software and paper as
  published.

## Tools and models

The table below is filled in by the author before JOSS submission.
It is not filled in speculatively by any AI or automation. If a
row is left blank the author confirms that no AI assistance of
that kind was used for this release.

| Artifact | AI tool / model + version (author fills) | Nature and scope of assistance (author fills) | Human review by author | Author-made core design decisions |
|---|---|---|---|---|
| Package Python source (`red2400_toolkit/*.py`) | | code refactoring / test scaffolding / linting only | yes | yes |
| Test suite (`tests/*.py`) | | test scaffolding / adversarial-fixture drafting | yes | yes |
| Independent oracle (`tests/oracle.py`) | | written by hand from the paper spec; no AI code generation | yes | yes |
| Repository documentation (`README.md`, `DEVELOPER_SETUP.md`, `API_REFERENCE.md`, `CONTRIBUTING.md`, `GOVERNANCE.md`, `SUPPORT.md`, `SECURITY.md`, `CHANGELOG.md`, `SEMVER_POLICY.md`) | | prose editing / structure suggestions | yes | yes |
| JOSS paper (`paper/paper.md`) | | prose editing / section-length trimming | yes | yes |
| BibTeX bibliography (`paper/paper.bib`) | | reference formatting; every entry verified against Crossref / arXiv by hand | yes | yes |
| Internal release-audit notes (not shipped in this package) | | audit-report drafting / cross-check narrative | yes | yes |
| Citation verification | | Crossref / arXiv lookup automation | yes (manual re-check) | yes |

## What was NOT AI-generated

- The mathematical event-identity primitive definition, the
  five-tier classification rule, the correction disclosure of the
  v1.0.0 mint-pooling defect, and the linkage-diagnostic contract.
- The adversarial hand-worked fixture in
  `tests/conftest.py::ADVERSARIAL_HAND_TABLE` (hand-computed by
  the author).
- The independent oracle implementation in `tests/oracle.py`
  (written from the paper spec without importing the production
  classifier).
- Any scientific number reported in the paper (all reconciled
  against the deposit and the oracle).

## Update policy

If any AI tool or model changes materially between now and
submission, this document is updated in the same commit as the
change; the update is recorded in `CHANGELOG.md` under the
current release. If the release is already tagged, a new patch
release is cut per `SEMVER_POLICY.md`.
