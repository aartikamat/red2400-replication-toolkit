# Semantic Versioning Policy

Versions follow [SemVer 2.0.0](https://semver.org/): `MAJOR.MINOR.PATCH`.

## What counts as a MAJOR change

Any of the following bumps `MAJOR`:

- A change to the classification rule, thresholds
  (`SAVED_THRESHOLD`, `MISSED_THRESHOLD`, `EARLY_DEATH_AGE_MAX_MIN`,
  `OBSERVATION_WINDOW_MIN`) or tie-break precedence.
- A change to the canonical `event_id` derivation
  (`event_model.compute_event_id`), including the truncation length
  or hashing algorithm.
- A change to the default `mode` of `classify_dataset` or `run_audit`.
- Removal of any public API listed in `red2400_toolkit/__init__.py`
  `__all__`.
- A change to `load_deposit`'s expected schema that would fail on a
  previously-valid deposit.
- Removal of `MODE_LEGACY_MINT_POOLED` (planned no earlier than v3.0.0).

The **v1.0.0 → v2.0.0** bump is warranted because it changes the
default dispatch from mint-pooled to event-keyed. Prior outputs will
not match; that is the intended correction.

## What counts as a MINOR change

- Adding a new public function, class, or module without breaking
  existing signatures.
- Adding a new estimand mode.
- Adding a new adapter for a compatible dataset.
- Extending an existing DataFrame return with new columns while
  preserving old ones.
- Adding a new optional dependency behind an extra
  (e.g. `pip install red2400-toolkit[figures]`).

## What counts as a PATCH change

- Bug fixes that do not change public API or output values (except to
  correct a known defect).
- Documentation-only changes.
- Test-only changes.
- Performance improvements with no visible behavior change.

## Pre-releases

Development versions use SemVer pre-release suffixes:
`2.0.0-rc.1`, `2.0.0-rc.2`, then `2.0.0`. The
current in-tree draft is versioned `2.0.0-draft` until the release
candidate is cut.

## Publishing

Releases are:

1. Tagged as `vMAJOR.MINOR.PATCH` on `main`.
2. Archived to Zenodo under the software-DOI concept (distinct from
   the RED-2400 dataset DOI).
3. Published to PyPI under `red2400-toolkit`.

The Zenodo software DOI is included in `CITATION.cff` and in the
README badge (see the README correction draft). The dataset DOI badge
in `README.md` v1.0.0 was incorrect and is being replaced.

## Deprecation policy

- A public API marked `DeprecationWarning` remains functional for at
  least one full MAJOR cycle before removal.
- `MODE_LEGACY_MINT_POOLED` is grandfathered — it will remain until
  v3.0.0 at the earliest.

## Yanking

Releases containing scientific-correctness defects severe enough to
require withdrawal will be **not** deleted from PyPI (that breaks
reproducibility) but will be marked `Yanked` per PEP 592. The Zenodo
software-DOI archive is preserved so citations continue to resolve.
