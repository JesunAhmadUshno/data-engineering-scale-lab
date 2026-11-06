"""Promotion gate harness (PREREG.md Section 9).

For the clean input and for each injected fault: build the staging
models, run the gate tests, and build the downstream models only if every
error-severity gate test passes. A failed gate blocks promotion; that
block is what "caught" means for F01 to F07 and F09. For F10 (warn
severity), caught means the run is flagged stale while promotion proceeds.
F08 is scored by the incremental harness, not here.

Results are appended to results/gate_log.jsonl.

Usage:
    python src/gates.py --sf 0.1
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, RESULTS, data_dir, sf_label  # noqa: E402
from inject import FAULTS  # noqa: E402
from run_dbt import run_dbt  # noqa: E402

BLOCKING = ["F01", "F02", "F03", "F04", "F05", "F06", "F07", "F09"]


def test_statuses(results):
    import re

    out = {}
    for r in results.get("results", []):
        uid = r.get("unique_id", "")
        if uid.startswith("test."):
            parts = uid.split(".")
            if len(parts) >= 4 and re.fullmatch(r"[0-9a-f]{10}", parts[-1]):
                name = parts[-2]
            else:
                name = parts[-1]
            out[name] = r.get("status")
    return out


def run_scenario(name, data_path, work_dir):
    db_path = work_dir / f"{name}.duckdb"
    if db_path.exists():
        db_path.unlink()
    vars_dict = {"data_dir": data_path.as_posix(), "delta_dir": "",
                 "affected_dates_path": ""}

    proc, _ = run_dbt(["run", "--select", "stg_lineitem", "stg_orders"], db_path, vars_dict)
    staging_ok = proc.returncode == 0

    tests = {}
    if staging_ok:
        proc, results = run_dbt(
            ["test", "--select", "stg_lineitem", "stg_orders", "tag:gate"],
            db_path, vars_dict)
        tests = test_statuses(results)
    failed = {k: v for k, v in tests.items() if v in ("fail", "error")}
    warned = {k: v for k, v in tests.items() if v == "warn"}
    gate_pass = staging_ok and not failed

    promoted = False
    if gate_pass:
        proc, _ = run_dbt(["run"], db_path, vars_dict)
        promoted = proc.returncode == 0

    return {
        "scenario": name,
        "staging_ok": staging_ok,
        "tests": tests,
        "gate_failures": failed,
        "gate_warnings": warned,
        "gate_pass": gate_pass,
        "promoted": promoted,
        "flagged_stale": any("freshness" in k for k in warned),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, default=0.1)
    args = ap.parse_args()

    work = ROOT / "outputs" / ".gate_work"
    work.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    log_path = RESULTS / "gate_log.jsonl"

    scenarios = [("clean", data_dir(args.sf), None)]
    for fault, (table, desc, critical) in FAULTS.items():
        scenarios.append((fault, ROOT / "data" / "faults" / fault, critical))

    rows = []
    for name, path, critical in scenarios:
        row = run_scenario(name, path, work)
        row["critical"] = critical
        if name == "clean":
            row["caught"] = None
        elif name == "F10":
            row["caught"] = bool(row["flagged_stale"])
        else:
            row["caught"] = not row["promoted"]
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("scenario", "gate_pass", "promoted",
                                              "flagged_stale", "caught")}), flush=True)

    done = {r["scenario"] for r in rows}
    kept = []
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            old = json.loads(line)
            if old.get("scenario") not in done:
                kept.append(old)
    with log_path.open("w") as f:
        for row in kept + rows:
            f.write(json.dumps(row) + "\n")
    caught = sum(1 for r in rows if r["caught"])
    print(f"gate scenarios done; caught {caught} of {len(rows) - 1} faults (F08 scored separately)")


if __name__ == "__main__":
    main()
