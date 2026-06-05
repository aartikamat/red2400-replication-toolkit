---
title: 'RED-2400 Replication Toolkit: A Software Package for Reproducible Filter-Precision Auditing of Algorithmic Decentralized-Exchange Trading Systems'
tags:
  - Python
  - decentralized finance
  - algorithmic trading
  - reproducibility
  - counterfactual evaluation
  - reject inference
  - benchmark dataset
authors:
  - name: Arati Uday Kamat
    orcid: 0009-0000-4781-312X
    affiliation: 1
affiliations:
  - name: Independent Researcher, McKinney, Texas, USA
    index: 1
date: 4 June 2026
bibliography: paper.bib
---

# Summary

The RED-2400 Replication Toolkit is a Python software package that enables
reproducible auditing of filter-precision in algorithmic decentralized-exchange
(DEX) trading systems. The toolkit operates on the public RED-2400 benchmark
dataset [@kamat2026red2400], a Solana-DEX rejection corpus of 6,660
algorithmically-rejected trading events with linked post-rejection outcome
trajectories captured continuously between 10 April and 2 May 2026.
The toolkit implements the five-tier outcome-classification
rule of @kamat2026audit, produces per-filter outcome distributions, computes
aggregate save-to-miss ratios under conservative and combined interpretations,
and performs the matched-comparison validation against the deposited
graveyard-lifecycle tracker. An automated continuous-integration test gate
(`test_audit_reproduces_kamat_2026_byte_identical`) is provisioned against a
versioned reference fixture committed alongside the v1.0.0 release; the gate
locks the per-filter outcome table to the values reported in the companion
paper, which is currently under peer review.

# Statement of need

Filter-gated algorithmic trading systems on decentralized exchanges reject most
candidate tokens they evaluate. Whether the rejection criteria save capital more
often than they forgo profit is testable only against observed post-rejection
outcomes of the specific rejected candidates. The RED-2400 public benchmark
provides such observations at scale, and a five-tier outcome-classification rule
operationalizes their interpretation [@kamat2026audit].

Reproducing the published precision-audit results, however, requires implementing
the classification rule consistently with the deposited audit script, applying
matched-comparison logic for the early-death tier, and joining rejection
outcomes to lifecycle ground truth from a separately-deposited Zenodo record.
Researchers wishing to verify, extend, or apply this audit methodology face
nontrivial implementation friction.

The RED-2400 Replication Toolkit removes this barrier. It packages the audit
workflow as an installable library with documented schemas, deterministic
classification, automated tests against the deposited reference outputs, and
end-to-end reproducibility of all tables and figures in the companion paper. The
toolkit supports four research uses: (1) verifying published audit results, (2)
extending the audit methodology to alternate datasets or chains, (3) testing
alternative classification rules against the same data, and (4) integrating
filter-precision evaluation into broader algorithmic-decision-system research
pipelines.

The toolkit complements the methodology paper [@kamat2026prfs] and the benchmark
dataset paper [@kamat2026red2400] by providing the implementation infrastructure
for reproducible empirical work in this area.

# Implementation

The toolkit comprises five modules:

- `red2400_loader` reads the three CSV files (`rejections`, `rejection_outcomes`,
  `graveyard_lifecycle`) from a local copy of the RED-2400 deposit and validates
  against the documented eleven-field schema.
- `prfs_classifier` implements the five-tier classification rule from
  @kamat2026audit with the missed-over-saved tie-break precedence.
- `audit_runner` computes per-filter outcome distributions and aggregate
  save-to-miss ratios under both conservative (windowed only) and combined
  (windowed plus early-death) interpretations.
- `early_death_validator` performs the §V.C matched-comparison validation
  against the graveyard lifecycle file.
- `figure_generator` regenerates Figures 1 and 2 of the companion audit paper.

A continuous-integration test suite verifies the audit against a versioned
reference fixture committed alongside the v1.0.0 release. The audit results
in @kamat2026audit Table V.A correspond to a published subset of the first
2,400 rejection events; this toolkit re-runs the same audit on the full
6,660-event deposit and commits its output as the v1.0.0 reference fixture
that the CI gate locks against. Filter-level statistics for filters with
*n* < 30 (filter_8 in the current deposit, *n* = 19) carry wide uncertainty
and should be interpreted with caution; the toolkit reports raw frequencies
without confidence intervals as the canonical audit format. The toolkit (this software) is licensed under
MIT (OSI-approved); the companion dataset remains under CC-BY-4.0. Continuous
integration runs the test suite on every commit to the main branch.

# Acknowledgments

The author acknowledges Prof. Anindya Goswami (IISER Pune) for arXiv endorsement
of the companion benchmark paper.

# References
