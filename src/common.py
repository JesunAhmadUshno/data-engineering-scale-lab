"""Shared helpers: paths, machine record, run log, DuckDB connections."""

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RUN_LOG = RESULTS / "run_log.jsonl"

DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "2.2GB")
DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))


def sf_label(sf):
    return "%g" % sf


def data_dir(sf):
    return ROOT / "data" / f"sf{sf_label(sf)}"


def git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return "unknown"


def machine():
    mem_gib = 0.0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_gib = round(int(line.split()[1]) / 1024 / 1024, 1)
    except Exception:
        pass
    return {"cores": os.cpu_count(), "ram_gib": mem_gib}


def log_run(row):
    row = dict(row)
    row.setdefault("commit", git_commit())
    row.setdefault("machine", machine())
    row.setdefault("cost_usd", 0)
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def duckdb_connect(db_path=":memory:", memory_limit=None, threads=None, tmp_dir=None):
    import duckdb

    con = duckdb.connect(str(db_path))
    con.execute(f"SET memory_limit='{memory_limit or DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"SET threads={threads or DUCKDB_THREADS}")
    if tmp_dir:
        Path(tmp_dir).mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory='{tmp_dir}'")
        con.execute(f"SET max_temp_directory_size='60GB'")
    con.execute("SET preserve_insertion_order=false")
    return con
