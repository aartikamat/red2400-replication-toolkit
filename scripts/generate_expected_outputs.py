"""Regenerate the LEGACY-mode reference fixture from a real deposit.

Retained ONLY as an auditability tool for the v1 mint-pooled dispatch.
The output file is a **regression witness of the defect**, not a
scientific oracle. Do not add it to the correctness gate.

Usage:
    python scripts/generate_expected_outputs.py /path/to/RED-2400-v2/
"""

import json
import sys
import warnings
from pathlib import Path

from red2400_toolkit import MODE_LEGACY_MINT_POOLED, load_deposit, run_audit


def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/generate_expected_outputs.py <deposit-dir>")
        sys.exit(1)

    deposit_dir = Path(sys.argv[1])
    out_path = (
        Path(__file__).resolve().parents[1]
        / "tests" / "legacy" / "expected_outputs_v1_defective.json"
    )
    d = load_deposit(deposit_dir)
    print(
        f"loaded: {d.n_rejections} rejections, {d.n_samples} samples, "
        f"{d.n_lifecycle} lifecycle rows"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        res = run_audit(
            d,
            reference_price_mode="first_sample_price",
            mode=MODE_LEGACY_MINT_POOLED,
        )
    payload = res.to_dict()
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote (LEGACY) {out_path}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
