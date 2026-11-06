"""Incremental and late-data harness (PREREG.md Section 8).

For each scale: a full-refresh comparator build on base plus delta, then
the three timing scenarios. In every scenario the T3 and T4 output
checksums must equal the full-refresh checksums (H4). The phase-2 model
times for T3 and T4 in scenario S3 give the incremental cost for H6;
the comparator build gives the full-refresh cost.

Scenarios:
- S1 control: delta present before the run.
- S2: delta arrives after staging ran, before the mart models.
- S3: delta arrives after a completed base run; a fresh run picks it up
  incrementally (this is the run that exercises the unique_key merge).
- S3b: like S3, but the late rows are appended to the staging input files
  themselves instead of arriving through the delta variables.

Results are appended to results/incremental_log.jsonl. mart checksums are
also written into results/checksums.json under arm "dbt_incremental".

Usage:
    python src/run_incremental.py --sf 0.1
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checksum import canonical_checksum  # noqa: E402
from common import ROOT, RESULTS, data_dir, duckdb_connect, sf_label  # noqa: E402
from run_dbt import model_times, run_dbt  # noqa: E402

MARTS = {"t3": "daily_sales", "t4": "ranked_sales"}


def export_marts(db_path, out_dir):
    con = duckdb_connect(db_path)
    paths = {}
    for key, model in MARTS.items():
        target = out_dir / f"{key}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM {model}) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        paths[key] = target
    con.close()
    return paths


def mart_checksums(db_path, out_dir):
    paths = export_marts(db_path, out_dir)
    return {key: canonical_checksum(str(p), key) for key, p in paths.items()}


def build_appended_dir(sf):
    """Materialize base plus delta as plain input files (S3b input)."""
    base = data_dir(sf)
    delta = base / "delta"
    dest = ROOT / "outputs" / ".appended" / f"sf{sf_label(sf)}"
    if dest.exists():
        shutil.rmtree(dest)
    con = duckdb_connect()
    li = f"read_parquet('{(base / 'lineitem').as_posix()}/*.parquet')"
    od = f"read_parquet('{(base / 'orders').as_posix()}/*.parquet')"
    upd = f"read_parquet('{(delta / 'lineitem_update.parquet').as_posix()}')"
    jobs = [
        (f"SELECT b.* FROM {li} b WHERE NOT EXISTS (SELECT 1 FROM {upd} u "
         f"WHERE u.l_orderkey = b.l_orderkey AND u.l_linenumber = b.l_linenumber) "
         f"UNION ALL SELECT * FROM read_parquet('{(delta / 'lineitem_delta.parquet').as_posix()}') "
         f"UNION ALL SELECT * FROM {upd}", dest / "lineitem" / "part-000.parquet"),
        (f"SELECT * FROM {od} UNION ALL SELECT * FROM read_parquet('{(delta / 'orders_delta.parquet').as_posix()}')",
         dest / "orders" / "part-000.parquet"),
    ]
    for sql, target in jobs:
        target.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    args = ap.parse_args()
    sf = args.sf
    base = data_dir(sf)
    delta = base / "delta"
    work = ROOT / "outputs" / ".incr_work" / f"sf{sf_label(sf)}"
    work.mkdir(parents=True, exist_ok=True)
    exp_root = ROOT / "outputs" / "dbt_incremental" / f"sf{sf_label(sf)}"
    RESULTS.mkdir(parents=True, exist_ok=True)

    vars_full = {"data_dir": base.as_posix(), "delta_dir": delta.as_posix(),
                 "affected_dates_path": (delta / "affected_dates.parquet").as_posix()}
    vars_base = {"data_dir": base.as_posix(), "delta_dir": "", "affected_dates_path": ""}
    vars_appended = {"data_dir": "", "delta_dir": "",
                     "affected_dates_path": (delta / "affected_dates.parquet").as_posix()}

    rows = []

    def record(scenario, sums, extra=None):
        row = {"sf": sf, "scenario": scenario,
               "checksums": {k: {"sha256": v[0], "rows": v[1]} for k, v in sums.items()}}
        if extra:
            row.update(extra)
        rows.append(row)
        print(json.dumps({"scenario": scenario,
                          "t3": sums["t3"][0][:12], "t4": sums["t4"][0][:12]}), flush=True)
        return row

    # Full-refresh comparator on base plus delta.
    db_full = work / "full_refresh.duckdb"
    if db_full.exists():
        db_full.unlink()
    proc, results = run_dbt(["build", "--full-refresh"], db_full, vars_full)
    assert proc.returncode == 0, proc.stdout[-2000:]
    full_times = model_times(results)
    full_sums = mart_checksums(db_full, exp_root / "full_refresh")
    record("full_refresh", full_sums,
           {"model_seconds": {MARTS[k]: full_times.get(MARTS[k]) for k in MARTS}})

    # S1: delta present before the run (control).
    db_s1 = work / "s1.duckdb"
    if db_s1.exists():
        db_s1.unlink()
    proc, _ = run_dbt(["build"], db_s1, vars_full)
    assert proc.returncode == 0, proc.stdout[-2000:]
    record("S1", mart_checksums(db_s1, exp_root / "s1"))

    # S2: staging runs on base; delta arrives; the rest of the build picks it up.
    db_s2 = work / "s2.duckdb"
    if db_s2.exists():
        db_s2.unlink()
    proc, _ = run_dbt(["run", "--select", "stg_lineitem", "stg_orders"], db_s2, vars_base)
    assert proc.returncode == 0, proc.stdout[-2000:]
    proc, _ = run_dbt(["build"], db_s2, vars_full)
    assert proc.returncode == 0, proc.stdout[-2000:]
    record("S2", mart_checksums(db_s2, exp_root / "s2"))

    # S3: full base run completes; delta arrives; a fresh run merges it.
    db_s3 = work / "s3.duckdb"
    if db_s3.exists():
        db_s3.unlink()
    proc, _ = run_dbt(["build"], db_s3, vars_base)
    assert proc.returncode == 0, proc.stdout[-2000:]
    pre_sums = mart_checksums(db_s3, exp_root / "s3_pre")
    proc, results = run_dbt(["run"], db_s3, vars_full)
    assert proc.returncode == 0, proc.stdout[-2000:]
    inc_times = model_times(results)
    record("S3", mart_checksums(db_s3, exp_root / "s3"),
           {"pre_delta_checksums": {k: v[0] for k, v in pre_sums.items()},
            "model_seconds": {MARTS[k]: inc_times.get(MARTS[k]) for k in MARTS}})

    # S3b: the late rows are appended to the input files themselves.
    appended = build_appended_dir(sf)
    vars_app = dict(vars_appended)
    vars_app["data_dir"] = appended.as_posix()
    db_s3b = work / "s3b.duckdb"
    if db_s3b.exists():
        db_s3b.unlink()
    proc, _ = run_dbt(["build"], db_s3b, vars_base)
    assert proc.returncode == 0, proc.stdout[-2000:]
    proc, results = run_dbt(["run"], db_s3b, vars_app)
    assert proc.returncode == 0, proc.stdout[-2000:]
    inc_times_b = model_times(results)
    record("S3b", mart_checksums(db_s3b, exp_root / "s3b"),
           {"model_seconds": {MARTS[k]: inc_times_b.get(MARTS[k]) for k in MARTS}})

    with (RESULTS / "incremental_log.jsonl").open("a") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print("incremental scenarios done for sf", sf)


if __name__ == "__main__":
    main()
