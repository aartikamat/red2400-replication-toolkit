"""Schema-validation tests for the deposit loader."""

import pandas as pd
import pytest

from red2400_toolkit.red2400_loader import (
    SchemaError,
    load_deposit,
    REJECTIONS_REQUIRED,
)


def test_load_synthetic_deposit_passes(synthetic_deposit):
    d = load_deposit(synthetic_deposit)
    assert d.n_rejections == 5
    assert d.n_samples == 7
    assert d.n_lifecycle == 2


def test_missing_file_raises(synthetic_deposit):
    (synthetic_deposit / "rejections.csv").unlink()
    with pytest.raises(FileNotFoundError):
        load_deposit(synthetic_deposit)


def test_missing_column_raises_schema_error(synthetic_deposit):
    rj = pd.read_csv(synthetic_deposit / "rejections.csv")
    rj = rj.drop(columns=[REJECTIONS_REQUIRED[0]])
    rj.to_csv(synthetic_deposit / "rejections.csv", index=False)
    with pytest.raises(SchemaError):
        load_deposit(synthetic_deposit)


def test_nonexistent_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_deposit(tmp_path / "does_not_exist")
