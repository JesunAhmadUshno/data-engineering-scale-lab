"""Collect output checksums per the protocol in PREREG.md Section 7.

SF0.1 and SF1: full ordered checksums for all five runs of every arm.
SF10: full checksums for runs 1 and 5; runs 2 to 4 get a row count and an
ordered checksum of the first 100,000 output rows.

Writes results/checksums.json with per-record entries plus the H3 verdicts:
for every (scale, transformation), whether the three arms agree on run 1,
and whether each arm reproduces its own run 1 checksum on run 5.

Usage:
    python src/collect_checksums.py --sf 0.1
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checksum import canonical_checksum  # noqa: E402
from common import RESULTS, ROOT, duckdb_connect, sf_label  # noqa: E402
from spec import TRANSFORMATIONS  # noqa: E402

ARMS = ("duckdb", "spark", "dbt")
PARTIAL_LIMIT = 100000


def output_glob(arm, sf, run, key):
    run_dir = ROOT / "outputs" / arm / f"sf{sf_label(sf)}" / f"run{run}"
    if arm == "spark":
        return str(run_dir / f"{key}.parquet" / "*.parquet")
    return str(run_dir / f"{key}.parquet")


def total_rows(glob):
    con = duckdb_connect()
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{glob}')").fetchone()[0]
    con.close()
    return n


def persist(records, sf):
    """Merge records into checksums.json and refresh this scale's verdicts.

    Called after every arm (D18) so a host restart loses at most the arm
    in progress; the merge is by record key, so reruns compose.
    """
    path = RESULTS / "checksums.json"
    doc = {"records": [], "verdicts": {}}
    if path.exists():
        doc = json.loads(path.read_text())
    key = lambda r: (r["arm"], r["sf"], r["transformation"], r["run"])  # noqa: E731
    merged = {key(r): r for r in doc["records"]}
    for r in records:
        merged[key(r)] = r
    doc["records"] = sorted(merged.values(), key=key)

    # H3 and determinism verdicts per (sf, transformation), full records only.
    verdicts = doc.get("verdicts", {})
    for spec in TRANSFORMATIONS:
        t = spec["key"]
        run1 = {r["arm"]: r for r in doc["records"]
                if r["sf"] == sf and r["transformation"] == t and r["run"] == 1}
        run5 = {r["arm"]: r for r in doc["records"]
                if r["sf"] == sf and r["transformation"] == t and r["run"] == 5}
        if len(run1) == 3:
            digests = {a: r["sha256"] for a, r in run1.items()}
            verdicts[f"sf{sf_label(sf)}:{t}"] = {
                "arms_agree_run1": len(set(digests.values())) == 1,
                "digests_run1": digests,
                "rows_agree": len({r["rows"] for r in run1.values()}) == 1,
                "deterministic_run5": (
                    all(a in run5 and run5[a]["sha256"] == run1[a]["sha256"] for a in run1)
                    if len(run5) == 3 else None
                ),
            }
    doc["verdicts"] = verdicts
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--arms", default=",".join(ARMS),
                    help="comma-separated subset of arms to collect")
    args = ap.parse_args()
    sf = args.sf
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())

    records = []
    for arm in arms:
        for run in range(1, 6):
            for spec in TRANSFORMATIONS:
                glob = output_glob(arm, sf, run, spec["key"])
                if not Path(glob.replace("*.parquet", "")).exists() and not list(
                    Path(glob).parent.glob("*")
                ):
                    continue
                try:
                    rows_total = total_rows(glob)
                except Exception:
                    continue
                partial = sf >= 10 and run not in (1, 5)
                if partial:
                    digest, rows_checked = canonical_checksum(
                        glob, spec["key"], limit=PARTIAL_LIMIT)
                else:
                    digest, rows_checked = canonical_checksum(glob, spec["key"])
                records.append({
                    "arm": arm, "sf": sf, "transformation": spec["key"],
                    "run": run, "sha256": digest, "rows": rows_total,
                    "rows_checked": rows_checked, "partial": partial,
                })
                print(f"{arm} sf{sf_label(sf)} run{run} {spec['key']} "
                      f"{digest[:12]} rows={rows_total} partial={partial}", flush=True)
        persist(records, sf)

    verdicts = persist(records, sf)

    bad = [k for k, v in verdicts.items()
           if k.startswith(f"sf{sf_label(sf)}:") and not v["arms_agree_run1"]]
    if bad:
        print("H3 FAILURE: arms disagree at", bad)
        raise SystemExit(1)
    print(f"checksums collected for sf{sf_label(sf)}; H3 run-1 agreement holds")


if __name__ == "__main__":
    main()
