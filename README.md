# RED-2400 Replication Toolkit

[![CI](https://github.com/aartikamat/red2400-replication-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/aartikamat/red2400-replication-toolkit/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dataset DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19989074.svg)](https://doi.org/10.5281/zenodo.19989074)

> [!NOTE]
> **Version note (v2, September 2026).**
>
> A later audit (21 August 2026) found that
> `red2400_toolkit.prfs_classifier.classify_dataset`, up to and including
> the `v1.0.0` release, grouped outcome rows by **mint** (token) and gave
> every rejection event on that mint the same token-level outcome path.
> Because 6,359 of 6,660 events in the RED-2400 v2 deposit (95.5 %) are
> on repeat mints, the v1.0.0 per-filter tables, tier attributions and
> `save_to_miss_conservative` / `save_to_miss_combined` ratios are
> token-pooled, not per-event results.
>
> v2 attaches outcomes to each rejection event through the P11 canonical
> event model (`event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms +
> "|" + rejectReason)`). On the same 6,660 events:
>
> | metric | v1.0.0 (token-pooled) | v2 (per event) |
> |---|---:|---:|
> | overall saved_windowed % | 53.35 | 9.07 |
> | overall missed %  | 25.62 | 2.12 |
> | overall unclassifiable % | 0.02  | 43.83 |
> | save_to_miss (combined)  | 2.19  | 9.00 |
>
> The v2.0.1 default also sets aside the 297 events whose 24-hour window
> runs past the end of the deposit (overall saved_windowed 9.16 % of
> 6,363 events; see [`CHANGELOG.md`](CHANGELOG.md)).
>
> Please cite v2 results. The dataset (Zenodo `10.5281/zenodo.19989074`)
> is unchanged; only the classifier's dispatch step changed. v1.0.0 is
> kept as a git tag so v1-era outputs can be reproduced, and the
> `MODE_LEGACY_MINT_POOLED` estimand reproduces them on demand with a
> `DeprecationWarning`. What changed, in full:
> [`CHANGELOG.md`](CHANGELOG.md).

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
- Keeps the event-level comparison against the lifecycle file that the
  companion paper reported in Section V. That comparison is withdrawn: it
  was found to reflect repeated rejections of the same tokens. Version 2 of
  the companion paper (arXiv:2607.02830, 8 October 2026) carries a
  correction notice. The code is kept only so the earlier result can be
  reproduced; it should not be cited as a validation.
- Regenerates Figures 1 and 2 of the companion paper.

## Install

The toolkit is not published on PyPI. Install from source:

```bash
# Install directly from GitHub (release v2.0.2):
pip install "git+https://github.com/aartikamat/red2400-replication-toolkit.git@v2.0.2"

# Or clone + editable install:
git clone https://github.com/aartikamat/red2400-replication-toolkit.git
cd red2400-replication-toolkit
pip install -e ".[figures]"
```

## Quickstart

```python
from red2400_toolkit import load_deposit, run_audit

deposit = load_deposit("/path/to/RED-2400-v2/")
result  = run_audit(deposit, on_missing='quarantine')  # mode='event'; see the note below

print(result.per_filter)
print(f"save-to-miss (conservative): {result.save_to_miss_conservative:.2f}")
print(f"save-to-miss (combined):  {result.save_to_miss_combined:.2f}")
print(f"linkage: {result.linkage_diagnostic}")
```

**Note on `on_missing`.** The default `on_missing='raise'` hard-fails if any
rejection row lacks a matching outcome row for its canonical `event_id`. On
the published RED-2400 deposit (`10.5281/zenodo.19989074`) about half of the
rejection events have no attachable outcome row, so the default raises
`EventLinkageError`. Pass `on_missing='quarantine'` to audit the linked
events (as in the example above); quarantined events are surfaced in
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
  [Computer software]. GitHub.
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

## Reporting issues

- Scientific-correctness bugs: open a GitHub issue with the
  `scientific-correctness` label.
- Security-relevant issues: see [`SECURITY.md`](SECURITY.md).
- Anything else: see [`CONTRIBUTING.md`](CONTRIBUTING.md).
