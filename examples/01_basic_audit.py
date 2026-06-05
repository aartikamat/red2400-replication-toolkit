"""Example 1: Basic audit reproducing the per-filter table and save-to-miss ratios.

Run from a clone of the toolkit repo:

    python examples/01_basic_audit.py /path/to/RED-2400-v2/

Or set the deposit path via environment variable:

    export RED2400_DEPOSIT_DIR=/path/to/RED-2400-v2
    python examples/01_basic_audit.py
"""

import os
import sys

from red2400_toolkit import load_deposit, run_audit


def main():
    deposit_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RED2400_DEPOSIT_DIR")
    if not deposit_dir:
        print("usage: python 01_basic_audit.py <path-to-deposit>", file=sys.stderr)
        sys.exit(1)

    deposit = load_deposit(deposit_dir)
    print(f"loaded deposit: {deposit.n_rejections} rejections, "
          f"{deposit.n_samples} samples, {deposit.n_lifecycle} lifecycle rows")

    result = run_audit(deposit)

    print("\n=== Per-filter table (percentages) ===")
    print(result.per_filter.round(1))

    print("\n=== Overall distribution ===")
    print(result.overall.round(1))

    print(f"\nsave-to-miss (conservative, windowed only): {result.save_to_miss_conservative:.3f}")
    print(f"save-to-miss (combined, w + early-death):    {result.save_to_miss_combined:.3f}")


if __name__ == "__main__":
    main()
