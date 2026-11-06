"""Canonical ordered checksum for a transformation output.

The checksum is SHA256 over the output rows ordered by all output columns,
exported through one fixed writer (DuckDB COPY to CSV with fixed options),
so the same logical output gives the same bytes whichever arm produced it.
Reading every arm's output through this one tool is what makes the
cross-arm comparison in H3 a comparison of data, not of file formats.

Usage:
    python src/checksum.py --path 'outputs/duckdb/sf0.1/run1/t2/*.parquet' --transformation t2
    python src/checksum.py --path ... --transformation t2 --limit 100000
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, duckdb_connect  # noqa: E402
from spec import BY_KEY  # noqa: E402


def canonical_checksum(path_glob, transformation, limit=None, tmp_dir=None):
    spec = BY_KEY[transformation]
    cols = spec["columns"]
    col_list = ", ".join(cols)
    tmp = Path(tmp_dir or (ROOT / "results" / ".checksum_tmp"))
    tmp.mkdir(parents=True, exist_ok=True)
    csv_file = tmp / f"checksum_{transformation}.csv"
    con = duckdb_connect(tmp_dir=tmp)
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    con.execute(
        f"""
        COPY (
            SELECT {col_list} FROM read_parquet('{path_glob}')
            ORDER BY {col_list}{limit_sql}
        ) TO '{csv_file}' (FORMAT CSV, HEADER false, DELIMITER '|')
        """
    )
    rows = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{path_glob}')"
    ).fetchone()[0]
    if limit:
        rows = min(rows, int(limit))
    con.close()
    h = hashlib.sha256()
    with csv_file.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    csv_file.unlink()
    return h.hexdigest(), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--transformation", required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    digest, rows = canonical_checksum(args.path, args.transformation, args.limit)
    print(json.dumps({"sha256": digest, "rows": rows}))


if __name__ == "__main__":
    main()
