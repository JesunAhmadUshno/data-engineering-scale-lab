"""CI gate (U-10): SF0.1 run-1 checksums must match the committed expected
values in results/expected_checksums.json, across all three arms.

Exit code 0 means every transformation matches on every arm.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    expected = json.loads((ROOT / "results" / "expected_checksums.json").read_text())
    doc = json.loads((ROOT / "results" / "checksums.json").read_text())
    failures = []
    for rec in doc["records"]:
        if rec["sf"] != 0.1 or rec["run"] != 1 or rec["partial"]:
            continue
        want = expected.get(rec["transformation"])
        if want is None or rec["sha256"] != want:
            failures.append((rec["arm"], rec["transformation"], rec["sha256"], want))
    if failures:
        for f in failures:
            print("MISMATCH", f)
        raise SystemExit(1)
    print("all SF0.1 run-1 checksums match the committed expected values")


if __name__ == "__main__":
    main()
