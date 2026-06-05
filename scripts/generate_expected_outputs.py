"""Generate tests/expected_outputs.json from a canonical audit run.

Usage:
    python scripts/generate_expected_outputs.py /path/to/RED-2400-v2.1/

The resulting JSON file is what the byte-identical CI test checks against on
every commit. Re-run this script (and commit the new JSON) whenever the
canonical deposit is versioned forward.
"""

import json
import sys
from pathlib import Path

from red2400_toolkit import load_deposit, run_audit


def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/generate_expected_outputs.py <deposit-dir>")
        sys.exit(1)

    deposit_dir = Path(sys.argv[1])
    out_path = Path(__file__).resolve().parents[1] / "tests" / "expected_outputs.json"

    d = load_deposit(deposit_dir)
    print(f"loaded: {d.n_rejections} rejections, {d.n_samples} samples, "
          f"{d.n_lifecycle} lifecycle rows")

    res = run_audit(d, reference_price_mode="first_sample_price")
    payload = res.to_dict()

    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {out_path}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
