"""Arm B: Spark local mode (local[*]) over the shared Parquet files.

Runs the canonical SQL from sql/ unchanged. Setup (JVM start, session
creation, first action) is timed separately from query time, per the
protocol (U-11). Each timed run executes all six transformations in
dependency order and writes each output to Parquet.

Usage:
    python src/run_spark.py --sf 0.1 --runs 5
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("JAVA_HOME", str(Path.home() / "workspace" / "tools" / "jdk-21"))
os.environ.setdefault("TMPDIR", str(Path.home() / "workspace" / "tools" / "tmp"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import data_dir, log_run, sf_label  # noqa: E402
from spec import TRANSFORMATIONS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out-root", default="outputs")
    ap.add_argument("--driver-memory", default=os.environ.get("DESL_SPARK_DRIVER_MEMORY", "1600m"))
    args = ap.parse_args()

    from pyspark.sql import SparkSession

    base = data_dir(args.sf)
    out_root = ROOT / args.out_root / "spark" / f"sf{sf_label(args.sf)}"
    local_dir = ROOT / "outputs" / ".spark_local"
    local_dir.mkdir(parents=True, exist_ok=True)
    partitions = "16" if args.sf >= 10 else "8"

    t0 = time.perf_counter()
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("data-engineering-scale-lab")
        .config("spark.driver.memory", args.driver_memory)
        .config("spark.sql.shuffle.partitions", partitions)
        .config("spark.sql.adaptive.enabled", "true")
        # Environment fix, recorded in DECISIONS.md: with the default 1 MB
        # direct-result limit, task results on this VM are fetched through
        # the block manager, and that fetch stalls until the 120 s shuffle
        # connection timeout kills the job (thread-dump evidence on file in
        # the build record). Returning task results directly removes the
        # fetch from the path; the SQL and the timing definition do not
        # change.
        .config("spark.task.maxDirectResultSize", "512MB")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.local.dir", str(local_dir))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    spark.sql("SELECT 1").collect()
    setup = time.perf_counter() - t0
    log_run({"arm": "spark", "sf": args.sf, "transformation": "setup",
             "run": 0, "seconds": round(setup, 4), "rows_out": None,
             "spark_setup": "jvm_start_session_first_action",
             "driver_memory": args.driver_memory,
             "shuffle_partitions": int(partitions)})
    print(f"setup {setup:.3f}s (spark {spark.version})", flush=True)

    for table in ("lineitem", "orders"):
        spark.read.parquet(str(base / table)).createOrReplaceTempView(table)

    for run in range(1, args.runs + 1):
        run_dir = out_root / f"run{run}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for spec in TRANSFORMATIONS:
            sql = (ROOT / spec["sql"]).read_text().strip().rstrip(";")
            out_path = str(run_dir / f"{spec['key']}.parquet")
            t0 = time.perf_counter()
            spark.sql(sql).write.mode("overwrite").parquet(out_path)
            seconds = time.perf_counter() - t0
            rows = spark.read.parquet(out_path).count()
            if spec["output"] in ("lineitem_orders", "daily_sales", "ranked_sales"):
                spark.read.parquet(out_path).createOrReplaceTempView(spec["output"])
            log_run({"arm": "spark", "sf": args.sf,
                     "transformation": spec["key"], "run": run,
                     "seconds": round(seconds, 4), "rows_out": rows})
            print(f"run{run} {spec['key']} {seconds:.3f}s rows={rows}", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
