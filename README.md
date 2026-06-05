# RED-2400 Replication Toolkit

[![CI](https://github.com/aartikamat/red2400-replication-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/aartikamat/red2400-replication-toolkit/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19989074.svg)](https://doi.org/10.5281/zenodo.19989074)

Reproducible filter-precision auditing of algorithmic decentralized-exchange
(DEX) trading systems against the **RED-2400 public benchmark**.

## What this is

The toolkit packages the audit workflow from
[Kamat (2026, SSRN 6638259)](https://ssrn.com/abstract=6638259) as an
installable Python library. It:

- Loads the three RED-2400 deposit files (`rejections.csv`,
  `rejection_outcomes.csv`, `graveyard_lifecycle.csv`)
- Validates the documented eleven-field schema
- Applies the five-tier outcome-classification rule deterministically, with the
  documented missed-over-saved tie-break precedence
- Produces per-filter outcome distributions
- Computes aggregate save-to-miss ratios under conservative (windowed only)
  and combined (windowed + early-death) interpretations
- Performs the §V.C matched-comparison validation against the lifecycle file
- Regenerates Figures 1 and 2 of the companion paper

A continuous-integration test suite verifies the audit reproduces the
per-filter table from the paper byte-identically against deposited reference
outputs.

## Install

```bash
pip install red2400-toolkit
# or, with figure-regeneration support:
pip install "red2400-toolkit[figures]"
```

## Quickstart

```python
from red2400_toolkit import load_deposit, run_audit

deposit = load_deposit("/path/to/RED-2400-v2/")
result  = run_audit(deposit)

print(result.per_filter)
print(f"save-to-miss (conservative): {result.save_to_miss_conservative:.2f}")
print(f"save-to-miss (combined):     {result.save_to_miss_combined:.2f}")
```

## How to cite

If you use this toolkit in research, please cite both the software and the
companion paper. See [`CITATION.cff`](CITATION.cff) for machine-readable
metadata.

```
Kamat, A. U. (2026). RED-2400 Replication Toolkit (Version 1.0.0)
  [Computer software]. https://github.com/aartikamat/red2400-replication-toolkit

Kamat, A. U. (2026). Outcome-Classified Precision Auditing of Filter Rules
  in Algorithmic DEX Trading: Evidence from 2,400 Rejection Events.
  SSRN 6638259.
```

## License

The toolkit (this software) is licensed under **MIT** (OSI-approved). The
companion RED-2400 dataset is licensed under **CC-BY-4.0** — see the dataset
deposit page for dataset-license terms. See [`LICENSE`](LICENSE).

## Companion materials

- Audit paper: [SSRN 6638259](https://ssrn.com/abstract=6638259)
- Benchmark dataset: [Zenodo 10.5281/zenodo.19989074](https://doi.org/10.5281/zenodo.19989074),
  also at [Hugging Face](https://huggingface.co/datasets/AratiKamat/RED-2400)
- Methodology paper (PRFS): [SSRN 6607301](https://ssrn.com/abstract=6607301)
