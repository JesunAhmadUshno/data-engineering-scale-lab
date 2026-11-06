"""Generate the study data for one scale factor with DuckDB's tpch extension.

The data is derived from TPC-H. It is not official TPC-H benchmark data.
TPC Tools are not used. See LICENSES.md.

For SF above 1, generation runs in split chunks with the dbgen children and
step parameters: each step generates one slice into its own database file,
and the slice is exported to its own Parquet part file. Arms read the part
files as one table through a glob, so the input files are identical for all
three arms.

Usage:
    python data/gen/generate.py --sf 0.1
    python data/gen/generate.py --sf 1
    python data/gen/generate.py --sf 10 --children 10
"""

import argparse
import json
import time
from pathlib import Path

import duckdb

TABLES = ("lineitem", "orders")
EXPECTED_ROWS = {"lineitem": 6_000_000, "orders": 1_500_000}


def export_table(con, table, out_file):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT * FROM {table}) TO '{out_file}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_file}')").fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--children", type=int, default=1)
    ap.add_argument("--root", default="data")
    ap.add_argument("--memory-limit", default="2.2GB")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    sf_label = ("%g" % args.sf)
    out_dir = Path(args.root) / f"sf{sf_label}"
    tmp_dir = Path(args.root) / f".tmp_sf{sf_label}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    totals = {t: 0 for t in TABLES}
    started = time.time()
    for step in range(args.children):
        db_file = tmp_dir / f"gen_step{step}.duckdb"
        if db_file.exists():
            db_file.unlink()
        con = duckdb.connect(str(db_file))
        con.execute(f"SET memory_limit='{args.memory_limit}'")
        con.execute(f"SET threads={args.threads}")
        con.execute(f"SET temp_directory='{tmp_dir}'")
        con.execute("SET preserve_insertion_order=false")
        con.execute("LOAD tpch")
        if args.children > 1:
            con.execute(
                f"CALL dbgen(sf={args.sf}, children={args.children}, step={step})"
            )
        else:
            con.execute(f"CALL dbgen(sf={args.sf})")
        for table in TABLES:
            part = out_dir / table / f"part-{step:03d}.parquet"
            totals[table] += export_table(con, table, part)
        con.close()
        db_file.unlink()
        print(f"step {step} done; totals so far: {totals}", flush=True)

    expected = {t: int(round(EXPECTED_ROWS[t] * args.sf)) for t in TABLES}
    manifest = {
        "sf": args.sf,
        "children": args.children,
        "rows": totals,
        "expected_rows_dbgen_rule": expected,
        "generation_seconds": round(time.time() - started, 2),
        "label": "derived from TPC-H",
        "generator": "DuckDB tpch extension, call dbgen",
    }
    # DBGEN rounding: totals must be within 0.5 percent of the rule values.
    for t in TABLES:
        assert abs(totals[t] - expected[t]) <= 0.005 * expected[t], (t, totals, expected)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
