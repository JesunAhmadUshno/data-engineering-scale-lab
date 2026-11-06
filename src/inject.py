"""Fault injection for the gate matrix (PREREG.md Section 9).

Each fault is a copy of the SF0.1 staging inputs with one defect, written
under data/faults/<fault>/ in the same layout as a scale directory
(lineitem/*.parquet, orders/*.parquet). The mutation is applied to temp
tables first, then both tables are exported, so every fault directory
holds a complete, loadable pair of inputs.

F08 is not built here; it is the late update row from data/gen/synth.py
and is scored by the incremental harness. F10 keeps row content valid but
shifts every shipdate back six years, so only the freshness gate sees it.

Usage:
    python src/inject.py --sf 0.1
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, data_dir, duckdb_connect  # noqa: E402

FAULTS = {
    "F01": ("orders", "duplicate primary key (orderkey)", True),
    "F02": ("orders", "null primary key", True),
    "F03": ("lineitem", "orphan foreign key", True),
    "F04": ("lineitem", "negative quantity", True),
    "F05": ("lineitem", "bad date format (shipdate stored as text, 100 invalid values)", True),
    "F06": ("lineitem", "price stored as a string", True),
    "F07": ("lineitem", "duplicate whole row", False),
    "F09": ("lineitem", "missing column (partkey)", True),
    "F10": ("lineitem", "stale file (all shipdates six years older)", False),
}

MUTATIONS = {
    "F01": "INSERT INTO od_t SELECT * FROM od_t ORDER BY o_orderkey LIMIT 1",
    "F02": "UPDATE od_t SET o_orderkey = NULL WHERE o_orderkey = (SELECT MIN(o_orderkey) FROM od_t)",
    "F03": "INSERT INTO li_t SELECT * REPLACE (CAST(999999999 AS BIGINT) AS l_orderkey) FROM li_t ORDER BY l_orderkey, l_linenumber LIMIT 1",
    "F04": "UPDATE li_t SET l_quantity = CAST(-5 AS DECIMAL(15,2)) WHERE l_orderkey = (SELECT MIN(l_orderkey) FROM li_t) AND l_linenumber = 1",
    "F05a": "ALTER TABLE li_t ALTER COLUMN l_shipdate TYPE VARCHAR",
    "F05": "UPDATE li_t SET l_shipdate = '1995-02-30' WHERE (l_orderkey, l_linenumber) IN (SELECT l_orderkey, l_linenumber FROM li_t ORDER BY l_orderkey, l_linenumber LIMIT 100)",
    "F06": "ALTER TABLE li_t ALTER COLUMN l_extendedprice TYPE VARCHAR",
    "F07": "INSERT INTO li_t SELECT * FROM li_t ORDER BY l_orderkey, l_linenumber LIMIT 1",
    "F09": "ALTER TABLE li_t DROP COLUMN l_partkey",
    "F10": "UPDATE li_t SET l_shipdate = CAST(l_shipdate - INTERVAL 6 YEAR AS DATE)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, default=0.1)
    args = ap.parse_args()

    base = data_dir(args.sf)
    li = f"read_parquet('{(base / 'lineitem').as_posix()}/*.parquet')"
    od = f"read_parquet('{(base / 'orders').as_posix()}/*.parquet')"
    faults_root = ROOT / "data" / "faults"
    con = duckdb_connect()

    manifest = {}
    for fault, (table, desc, critical) in FAULTS.items():
        dest = faults_root / fault
        if dest.exists():
            shutil.rmtree(dest)
        con.execute("DROP TABLE IF EXISTS li_t")
        con.execute("DROP TABLE IF EXISTS od_t")
        con.execute(f"CREATE TEMP TABLE li_t AS SELECT * FROM {li}")
        con.execute(f"CREATE TEMP TABLE od_t AS SELECT * FROM {od}")
        if fault == "F05":
            con.execute(MUTATIONS["F05a"])
        con.execute(MUTATIONS[fault])
        for name, tbl in (("lineitem", "li_t"), ("orders", "od_t")):
            out = dest / name / "part-000.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY (SELECT * FROM {tbl}) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts = {
            "lineitem": con.execute("SELECT COUNT(*) FROM li_t").fetchone()[0],
            "orders": con.execute("SELECT COUNT(*) FROM od_t").fetchone()[0],
        }
        manifest[fault] = {"table": table, "description": desc, "critical": critical,
                           "rows": counts, "dir": str(dest.relative_to(ROOT))}
        print(f"{fault}: {desc} rows={counts}", flush=True)

    (faults_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    con.close()


if __name__ == "__main__":
    main()
