# RED-2400 Replication Toolkit

[![CI](https://github.com/aartikamat/red2400-replication-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/aartikamat/red2400-replication-toolkit/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
<!-- Dataset DOI, distinct from the software DOI: -->
[![Dataset DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19989074.svg)](https://doi.org/10.5281/zenodo.19989074)
<!-- Software DOI badge: DO NOT ENABLE until the v2.0.1 Zenodo software
  concept DOI is minted. Placeholder -- the maintainer will replace
  `SOFTWARE_DOI` with the actual value at release time (see
  MANUAL_RELEASE_INSTRUCTIONS_FOR_ARATI.md). -->
<!-- [![Software DOI](https://zenodo.org/badge/DOI/SOFTWARE_DOI.svg)](https://doi.org/SOFTWARE_DOI) -->

> [!CAUTION]
> ## Scientific correctness notice -- v1.0.0 results should not be trusted for per-event attribution
>
> An independent audit (2026-08-21) confirmed that
> `red2400_toolkit.prfs_classifier.classify_dataset` up to and including
> the `v1.0.0` release grouped outcome rows by **mint** and passed the
> same mint-level trajectory to every rejection event on that mint.
> Because 6,359 of 6,660 events in the RED-2400 v2 deposit (95.5 %) live
> on repeat mints, the per-filter distributions, tier attributions, and
> `save_to_miss_conservative` / `save_to_miss_combined` ratios produced by
> v1.0.0 **do not measure per-event outcomes**.
>
> The v2 release adopts the P11 canonical event model
> (`event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms +
> "|" + rejectReason)`) so outcomes are attached per event rather than
> per mint. Numerical impact on the RED-2400 v2 corpus (6,660 events):
>
> | metric | v1 (mint-pooled) | v2 (event-keyed) |
> |---|---:|---:|
> | overall saved_windowed % | 53.35 | 9.07 |
> | overall missed %  | 25.62 | 2.12 |
> | overall unclassifiable % | 0.02  | 43.83 |
> | save_to_miss (combined)  | 2.19  | 9.00 |
>
> **Do not cite v1.0.0 per-filter tables or save-to-miss ratios as
> event-level scientific findings.** The dataset itself
> (Zenodo `10.5281/zenodo.19989074`) is unaffected -- only the
> classifier's dispatch layer was defective.
>
> v1.0.0 is preserved as a git tag for reproducibility of v1-era
> artifacts; the v2 API exposes a `MODE_LEGACY_MINT_POOLED` estimand
> that reproduces v1 outputs on demand and emits a `DeprecationWarning`.

Reproducible filter-precision auditing of algorithmic decentralized-exchange
(DEX) trading systems against the **RED-2400 public benchmark**.

## What this is

The toolkit packages the audit workflow from
[Kamat (2026, SSRN 6638259)](https://ssrn.com/abstract=6638259) as an
installable Python library. It:

- Loads the three RED-2400 deposit files (`rejections.csv`,
  `rejection_outcomes.csv`, `graveyard_lifecycle.csv`).
- Validates the documented eleven-field schema.
- Applies the five-tier outcome-classification rule deterministically,
  with the documented missed-over-saved tie-break precedence, at the
  **per-event** level using the P11 canonical `event_id`.
- Produces per-filter outcome distributions and aggregate save-to-miss
  ratios under conservative (windowed only) and combined
  (windowed + early-death) interpretations.
- Exposes four estimand modes so mint- and event-level results are
  never conflated: `event` (default), `first_event_per_mint`,
  `latest_event_per_mint`, `mint_summary`.
- Performs the §V.C matched-comparison validation against the lifecycle
  file at the event level.
- Regenerates Figures 1 and 2 of the companion paper.

## Install

The `v2.0.1` release will be published to PyPI once the release
checklist completes. Until then, install from source at the v2 tag or
from the `main` branch:

```bash
# Install directly from GitHub (once the v2 tag is cut):
pip install "git+https://github.com/aartikamat/red2400-replication-toolkit.git@v2.0.1"

# Or clone + editable install:
git clone https://github.com/aartikamat/red2400-replication-toolkit.git
cd red2400-replication-toolkit
pip install -e ".[figures]"
```

<!-- Restore this once the v2 PyPI upload is verified (see
  RELEASE_CHECKLIST.md item 7):
```bash
pip install red2400-toolkit
# or, with figure-regeneration support:
pip install "red2400-toolkit[figures]"
```
-->

## Quickstart

```python
from red2400_toolkit import load_deposit, run_audit

deposit = load_deposit("/path/to/RED-2400-v2/")
result  = run_audit(deposit)  # default: mode='event', on_missing='raise'

print(result.per_filter)
print(f"save-to-miss (conservative): {result.save_to_miss_conservative:.2f}")
print(f"save-to-miss (combined):  {result.save_to_miss_combined:.2f}")
print(f"linkage: {result.linkage_diagnostic}")
```

**Note on `on_missing`.** The default `on_missing='raise'` hard-fails if any
rejection row lacks a matching outcome row for its canonical `event_id`. On
the published RED-2400 v2 deposit (`10.5281/zenodo.19989074`) this default
succeeds because every rejection is either linked (event-keyed) or has an
absent-outcome (unclassifiable) counterpart under the P11 spec. Pass
`on_missing='quarantine'` to tolerate orphan rejections in ad-hoc or
partial deposits; quarantined events are surfaced in
`result.linkage_diagnostic` rather than silently dropped.

To reproduce v1.0.0 numbers exactly (for auditing v1-era artifacts):

```python
from red2400_toolkit import MODE_LEGACY_MINT_POOLED
result = run_audit(deposit, mode=MODE_LEGACY_MINT_POOLED)  # DeprecationWarning
```

## How to cite

If you use this toolkit in research, please cite both the software and
the companion paper. See [`CITATION.cff`](CITATION.cff) for
machine-readable metadata.

```
Kamat, A. U. (2026). RED-2400 Replication Toolkit (Version 2.0.1)
  [Computer software]. Zenodo.
  DOI: replace with the software concept DOI once minted (see
  MANUAL_RELEASE_INSTRUCTIONS_FOR_ARATI.md Block 6).
  https://github.com/aartikamat/red2400-replication-toolkit

Kamat, A. U. (2026). Outcome-Classified Precision Auditing of Filter Rules
  in Algorithmic DEX Trading: Evidence from 2,400 Rejection Events.
  SSRN 6638259.
```

## License

The toolkit (this software) is licensed under **MIT** (OSI-approved).
The companion RED-2400 dataset is licensed under **CC-BY-4.0** -- see the
dataset deposit page for dataset-license terms. See
[`LICENSE`](LICENSE).

## Companion materials

- Audit paper: [SSRN 6638259](https://ssrn.com/abstract=6638259)
- Benchmark dataset: [Zenodo 10.5281/zenodo.19989074](https://doi.org/10.5281/zenodo.19989074),
  also at [Hugging Face](https://huggingface.co/datasets/AratiKamat/RED-2400)
- Methodology paper (PRFS): [SSRN 6607301](https://ssrn.com/abstract=6607301)
- Canonical event model spec: the P11 canonicalization spec is
  archived on Zenodo (see `paper/paper.bib` entry `kamat2026p11`
  for the concept DOI once minted).

## Reporting issues

- Scientific-correctness bugs: open a GitHub issue with the
  `scientific-correctness` label.
- Security-relevant issues: see [`SECURITY.md`](SECURITY.md).
- Anything else: see [`CONTRIBUTING.md`](CONTRIBUTING.md).
