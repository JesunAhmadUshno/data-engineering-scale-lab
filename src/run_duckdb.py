"""Arm A: DuckDB single-node over the shared Parquet files.

Runs the canonical SQL from sql/ unchanged. Each timed run executes all six
transformations in dependency order and writes each output to Parquet.
Setup (connect and input views) is timed separately, per the protocol.

Usage:
    python src/run_duckdb.py --sf 0.1 --runs 5
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, data_dir, duckdb_connect, log_run, sf_label  # noqa: E402
from spec import TRANSFORMATIONS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out-root", default="outputs")
    args = ap.parse_args()

    base = data_dir(args.sf)
    out_root = ROOT / args.out_root / "duckdb" / f"sf{sf_label(args.sf)}"

    t0 = time.perf_counter()
    con = duckdb_connect(tmp_dir=ROOT / "outputs" / ".duckdb_tmp")
    for table in ("lineitem", "orders"):
        con.execute(
            f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{(base / table).as_posix()}/*.parquet')"
        )
    setup = time.perf_counter() - t0
    log_run({"arm": "duckdb", "sf": args.sf, "transformation": "setup",
             "run": 0, "seconds": round(setup, 4), "rows_out": None})
    print(f"setup {setup:.3f}s", flush=True)

    # One uncounted warm-up pass (protocol refinement, see PREREG.md
    # deviations): steady-state measurement, cold-start cost is reported
    # separately as setup overhead.
    warm_dir = out_root / "warmup"
    warm_dir.mkdir(parents=True, exist_ok=True)
    for spec in TRANSFORMATIONS:
        sql = (ROOT / spec["sql"]).read_text().strip().rstrip(";")
        out_file = warm_dir / f"{spec['key']}.parquet"
        con.execute(f"COPY ({sql}) TO '{out_file}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        if spec["output"] in ("lineitem_orders", "daily_sales", "ranked_sales"):
            con.execute(
                f"CREATE OR REPLACE VIEW {spec['output']} AS SELECT * FROM read_parquet('{out_file}')"
            )
    print("warm-up pass done (uncounted)", flush=True)

    for run in range(1, args.runs + 1):
        run_dir = out_root / f"run{run}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for spec in TRANSFORMATIONS:
            sql = (ROOT / spec["sql"]).read_text().strip().rstrip(";")
            out_file = run_dir / f"{spec['key']}.parquet"
            t0 = time.perf_counter()
            con.execute(
                f"COPY ({sql}) TO '{out_file}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            seconds = time.perf_counter() - t0
            rows = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{out_file}')"
            ).fetchone()[0]
            if spec["output"] in ("lineitem_orders", "daily_sales", "ranked_sales"):
                con.execute(
                    f"CREATE OR REPLACE VIEW {spec['output']} AS SELECT * FROM read_parquet('{out_file}')"
                )
            log_run({"arm": "duckdb", "sf": args.sf,
                     "transformation": spec["key"], "run": run,
                     "seconds": round(seconds, 4), "rows_out": rows})
            print(f"run{run} {spec['key']} {seconds:.3f}s rows={rows}", flush=True)
    con.close()


if __name__ == "__main__":
    main()
