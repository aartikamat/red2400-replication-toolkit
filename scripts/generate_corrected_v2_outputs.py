"""Generate the corrected v2 event-level outputs from a real deposit.

This is the scientifically correct estimand (mode='event'). The output
is written next to the legacy witness so a diff makes the v1 -> v2
correction visible.

Usage:
    python scripts/generate_corrected_v2_outputs.py /path/to/RED-2400-v2/
"""

import json
import sys
from pathlib import Path

from red2400_toolkit import MODE_EVENT, load_deposit, run_audit


def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/generate_corrected_v2_outputs.py <deposit-dir>")
        sys.exit(1)

    deposit_dir = Path(sys.argv[1])
    out_path = (
        Path(__file__).resolve().parents[1]
        / "tests" / "corrected_v2_outputs.json"
    )
    d = load_deposit(deposit_dir)
    res = run_audit(
        d,
        reference_price_mode="first_sample_price",
        mode=MODE_EVENT,
        on_missing="quarantine",
    )
    payload = res.to_dict()
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote (CORRECTED v2) {out_path}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
