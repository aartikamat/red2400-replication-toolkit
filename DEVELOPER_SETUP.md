# Developer Setup

Prerequisites: Python 3.10, 3.11, or 3.12 (recommended 3.12).

## 1. Clone

```bash
git clone https://github.com/aartikamat/red2400-replication-toolkit.git
cd red2400-replication-toolkit
```

## 2. Create a virtualenv

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows Git Bash:
source .venv/Scripts/activate
# macOS / Linux:
source .venv/bin/activate
```

## 3. Install in editable mode with test + figures extras

```bash
pip install --upgrade pip
pip install -e ".[test,figures]"
```

## 4. Run the test suite

```bash
pytest -v
```

Expected: the full suite defines 72 tests. Without the real deposit
`pytest -v` collects 72 and reports **71 passed, 1 skipped** (the
real-deposit legacy-witness test skips unless the deposit is
available). With `RED2400_DEPOSIT_DIR` set, all 72 pass.

## 5. Run the real-deposit tests (optional)

Download the RED-2400 deposit from Zenodo
(<https://doi.org/10.5281/zenodo.19989074>) into a local directory, then:

```bash
export RED2400_DEPOSIT_DIR=/path/to/RED-2400-v2
pytest -v
```

Now all 72 tests run, including
`test_legacy_mode_reproduces_v1_defective_numbers_on_real_deposit`
(the regression witness for the v1 defect).

## 6. Regenerate reference outputs

Corrected v2 (event-keyed) outputs:

```bash
python scripts/generate_corrected_v2_outputs.py $RED2400_DEPOSIT_DIR
```

Legacy v1 witness (defective mint-pooled outputs):

```bash
python scripts/generate_expected_outputs.py $RED2400_DEPOSIT_DIR
```

Never commit `tests/corrected_v2_outputs.json` as a test oracle — it is
a diagnostic snapshot, not a fixture.

## 7. Build the package (release candidates only)

```bash
pip install build
python -m build
```

This produces `dist/red2400_toolkit-2.0.1-*.whl` and `.tar.gz`. Do NOT
`twine upload` from a developer machine — releases go through the
`RELEASE_CHECKLIST.md` steps and are cut by the maintainer only.

## Troubleshooting

- **`ImportError: No module named 'numpy'`**: numpy is a transitive
  dependency of pandas; `pip install -e ".[test]"` should have pulled
  it in. Reinstall pandas explicitly if needed.
- **Windows: `datetime.fromisoformat` errors on Python < 3.11**: the
  toolkit requires 3.10+, but the timestamp parser uses the modern
  overload. Upgrade to 3.10.4 or newer if you see cryptic parse
  errors.
- **Real-deposit tests skipped** despite `RED2400_DEPOSIT_DIR` being
  set: check that the path resolves to a directory containing
  `rejections.csv`, `rejection_outcomes.csv`, and
  `graveyard_lifecycle.csv`.
