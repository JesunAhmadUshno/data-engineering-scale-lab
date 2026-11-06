"""Arm C: dbt on DuckDB, full builds.

Each timed run is a full dbt build into a fresh DuckDB file. Per-model
times come from dbt's own target/run_results.json, never from hand timing.
After each build, the six transformation outputs are exported to Parquet
so the shared checksum tool can compare them with Arms A and B.

Usage:
    python src/run_dbt.py --sf 0.1 --runs 5
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, data_dir, log_run, sf_label  # noqa: E402
from spec import DBT_MODELS, TRANSFORMATIONS  # noqa: E402

DBT_DIR = ROOT / "sql" / "dbt"
VENV_BIN = Path.home() / "workspace" / "gap-closure" / "venv-b2" / "bin"


def dbt_env(db_path):
    env = dict(os.environ)
    env["DBT_PROFILES_DIR"] = str(DBT_DIR)
    env["DBT_DUCKDB_PATH"] = str(db_path)
    return env


def run_dbt(args_list, db_path, vars_dict):
    cmd = [str(VENV_BIN / "dbt")] + args_list + ["--project-dir", str(DBT_DIR),
                                                "--vars", json.dumps(vars_dict)]
    proc = subprocess.run(cmd, env=dbt_env(db_path), capture_output=True, text=True)
    results_file = DBT_DIR / "target" / "run_results.json"
    results = json.loads(results_file.read_text()) if results_file.exists() else {"results": []}
    return proc, results


def model_times(results):
    out = {}
    for r in results.get("results", []):
        uid = r.get("unique_id", "")
        if uid.startswith("model."):
            name = uid.split(".")[-1]
            out[name] = round(float(r.get("execution_time", 0.0)), 4)
    return out


def export_outputs(db_path, out_dir):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import duckdb_connect

    con = duckdb_connect(db_path)
    counts = {}
    for spec in TRANSFORMATIONS:
        layer, model = DBT_MODELS[spec["output"]]
        target = out_dir / f"{spec['key']}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM {model}) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts[spec["key"]] = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{target}')"
        ).fetchone()[0]
    con.close()
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out-root", default="outputs")
    args = ap.parse_args()

    base = data_dir(args.sf)
    out_root = ROOT / args.out_root / "dbt" / f"sf{sf_label(args.sf)}"
    work = ROOT / "outputs" / ".dbt_work" / f"sf{sf_label(args.sf)}"
    work.mkdir(parents=True, exist_ok=True)
    vars_dict = {"data_dir": base.as_posix(), "delta_dir": "", "affected_dates_path": ""}

    for run in range(1, args.runs + 1):
        db_path = work / f"build_run{run}.duckdb"
        if db_path.exists():
            db_path.unlink()
        t0 = time.perf_counter()
        proc, results = run_dbt(["build"], db_path, vars_dict)
        wall = time.perf_counter() - t0
        if proc.returncode != 0:
            print(proc.stdout[-3000:])
            print(proc.stderr[-3000:])
            raise SystemExit(f"dbt build failed on run {run}")
        times = model_times(results)
        counts = export_outputs(db_path, out_root / f"run{run}")
        by_output = {spec["output"]: spec["key"] for spec in TRANSFORMATIONS}
        for output, key in by_output.items():
            layer, model = DBT_MODELS[output]
            log_run({"arm": "dbt", "sf": args.sf, "transformation": key,
                     "run": run, "seconds": times.get(model),
                     "rows_out": counts.get(key), "dbt_wall_seconds": round(wall, 4)})
            print(f"run{run} {key} model={model} {times.get(model)}s rows={counts.get(key)}", flush=True)
        log_run({"arm": "dbt", "sf": args.sf, "transformation": "build_wall",
                 "run": run, "seconds": round(wall, 4), "rows_out": None})
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
