# v1.0.0 legacy reference — retained for correction-notice verification

## What this directory holds

- `expected_outputs_v1_defective.json` — the byte-identical
  `expected_outputs.json` shipped with the v1.0.0 release. **These
  numbers reproduce the v1 scientific-correctness defect** (the
  mint-collapse in `classify_dataset`) and are retained only so that
  the correction notice in `README.md` and `paper/paper.md` remains
  independently verifiable: a reader can compute the v1 numbers on
  demand under `MODE_LEGACY_MINT_POOLED` and confirm they match the
  archived reference here, and can compute the v2 numbers under the
  default `MODE_EVENT` and confirm they differ as documented.

## What this directory is NOT

- Not a scientific reference for per-event outcomes. v1 numbers must
  not be cited as event-level scientific results — see the README's
  "Scientific correctness notice" and `CHANGELOG.md`'s v2.0.0
  entries.
- Not part of the pytest suite. The v2 test suite lives under
  `tests/` at the toolkit root and consumes only the v2 corrected
  outputs in `tests/corrected_v2_outputs.json`.
- Not maintained. Files here are frozen at v1.0.0 and will not be
  regenerated on later releases.

## How to reproduce these numbers under v2

```python
from red2400_toolkit import load_deposit, run_audit, MODE_LEGACY_MINT_POOLED
d = load_deposit("/path/to/RED-2400-v2/")
res = run_audit(d, mode=MODE_LEGACY_MINT_POOLED)  # emits DeprecationWarning
# Compare res.to_dict() to expected_outputs_v1_defective.json
```

The `DeprecationWarning` is intentional — the legacy dispatch is
retained only for auditability of v1-era artifacts and is never a
scientific default.
