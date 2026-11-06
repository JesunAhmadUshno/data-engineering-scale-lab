"""Build the late-arriving delta for one generated scale. Synthetic, generated.

This file is labelled: synthetic, generated. The delta rows are invented by
this script with fixed arithmetic (no random number generator), so any
reviewer regenerates the identical delta from the identical base data.

The delta has three parts:
- orders_delta.parquet: new orders on order dates that already exist in the
  base data, so daily aggregates for those dates change.
- lineitem_delta.parquet: new lineitems for those orders.
- lineitem_update.parquet: one existing lineitem row with a changed
  l_extendedprice (the F08 shape). The staging merge lets the delta win on
  (l_orderkey, l_linenumber), so applying the delta replaces the old price.

It also writes affected_dates.parquet: the order dates whose T3 and T4
aggregates the delta changes. The dbt incremental models recompute exactly
those dates.

Usage:
    python data/gen/synth.py --sf 0.1
"""

import argparse
import json
from pathlib import Path

import duckdb

NEW_ORDERS = 40
LINES_PER_ORDER = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sf", type=float, required=True)
    ap.add_argument("--root", default="data")
    ap.add_argument("--memory-limit", default="2.2GB")
    args = ap.parse_args()

    sf_label = "%g" % args.sf
    base = Path(args.root) / f"sf{sf_label}"
    out = base / "delta"
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET preserve_insertion_order=false")

    li = f"read_parquet('{(base / 'lineitem').as_posix()}/*.parquet')"
    od = f"read_parquet('{(base / 'orders').as_posix()}/*.parquet')"

    # Three existing order dates, chosen deterministically: the earliest
    # order date, the median order date, and the latest order date.
    dates = [
        r[0]
        for r in con.execute(
            f"""
            SELECT o_orderdate FROM (
                SELECT o_orderdate, ROW_NUMBER() OVER (ORDER BY o_orderdate) AS rn,
                       COUNT(*) OVER () AS n
                FROM (SELECT DISTINCT o_orderdate FROM {od})
            ) WHERE rn IN (1, (n + 1) // 2, n) ORDER BY o_orderdate
            """
        ).fetchall()
    ]
    assert len(dates) == 3, dates
    date_list = ", ".join(f"DATE '{d}'" for d in dates)

    max_orderkey = con.execute(f"SELECT MAX(o_orderkey) FROM {od}").fetchone()[0]
    a_date, b_date = con.execute(
        f"SELECT MIN(o_orderdate), MAX(o_orderdate) FROM {od}"
    ).fetchone()

    # New orders: keys above the base maximum, spread over the three dates.
    con.execute(
        f"""
        CREATE TEMP TABLE new_orders AS
        SELECT
            {max_orderkey} + i AS o_orderkey,
            1 + (i * 37) % 1000 AS o_custkey,
            'O' AS o_orderstatus,
            CAST(0 AS DECIMAL(15,2)) AS o_totalprice,
            [{date_list}][1 + i % 3] AS o_orderdate,
            '5-LOW' AS o_orderpriority,
            'Clerk#000000001' AS o_clerk,
            0 AS o_shippriority,
            'synthetic late order' AS o_comment
        FROM range(1, {NEW_ORDERS} + 1) AS t(i)
        """
    )
    # New lineitems: arithmetic prices, discounts, taxes, dates inside range.
    con.execute(
        f"""
        CREATE TEMP TABLE new_lines AS
        SELECT
            o.o_orderkey AS l_orderkey,
            100 + j AS l_partkey,
            1 + (o.o_orderkey + j) % 20 AS l_suppkey,
            j AS l_linenumber,
            CAST(1 + (o.o_orderkey * 7 + j * 13) % 50 AS DECIMAL(15,2)) AS l_quantity,
            CAST(100 + (o.o_orderkey * 11 + j * 101) % 9000 + 0.99 AS DECIMAL(15,2)) AS l_extendedprice,
            CAST(((o.o_orderkey + j) % 11) * 0.01 AS DECIMAL(15,2)) AS l_discount,
            CAST(((o.o_orderkey + j) % 9) * 0.01 AS DECIMAL(15,2)) AS l_tax,
            'N' AS l_returnflag,
            'O' AS l_linestatus,
            o.o_orderdate + 1 AS l_shipdate,
            o.o_orderdate + 2 AS l_commitdate,
            o.o_orderdate + 3 AS l_receiptdate,
            'DELIVER IN PERSON' AS l_shipinstruct,
            'AIR' AS l_shipmode,
            'synthetic late line' AS l_comment
        FROM new_orders o, range(1, {LINES_PER_ORDER} + 1) AS t(j)
        """
    )
    # Fill o_totalprice from the new lines, the way the generator would.
    con.execute(
        """
        CREATE TEMP TABLE orders_delta AS
        SELECT o.o_orderkey, o.o_custkey, o.o_orderstatus,
               CAST(SUM(l.l_extendedprice * (1 - l.l_discount) * (1 + l.l_tax)) AS DECIMAL(15,2)) AS o_totalprice,
               o.o_orderdate, o.o_orderpriority, o.o_clerk, o.o_shippriority, o.o_comment
        FROM new_orders o JOIN new_lines l ON l.l_orderkey = o.o_orderkey
        GROUP BY ALL
        """
    )
    # The update row: the first lineitem (smallest key) on the middle date,
    # with its price multiplied by 1.5. Its order date joins the affected set.
    con.execute(
        f"""
        CREATE TEMP TABLE lineitem_update AS
        SELECT l.* REPLACE (CAST(ROUND(l.l_extendedprice * 1.5, 2) AS DECIMAL(15,2)) AS l_extendedprice)
        FROM {li} l JOIN {od} o ON l.l_orderkey = o.o_orderkey
        WHERE o.o_orderdate = DATE '{dates[1]}'
        ORDER BY l.l_orderkey, l.l_linenumber
        LIMIT 1
        """
    )
    upd = con.execute("SELECT COUNT(*), MIN(l_orderkey) FROM lineitem_update").fetchone()
    assert upd[0] == 1, upd

    for name, table in (
        ("orders_delta", "orders_delta"),
        ("lineitem_delta", "new_lines"),
        ("lineitem_update", "lineitem_update"),
    ):
        con.execute(f"COPY (SELECT * FROM {table}) TO '{out / (name + '.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    con.execute(
        f"""
        COPY (
            SELECT DISTINCT o_orderdate AS order_date FROM orders_delta
            UNION
            SELECT o.o_orderdate FROM lineitem_update u JOIN {od} o ON u.l_orderkey = o.o_orderkey
            ORDER BY 1
        ) TO '{out / 'affected_dates.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    counts = {
        "new_orders": con.execute("SELECT COUNT(*) FROM orders_delta").fetchone()[0],
        "new_lineitems": con.execute("SELECT COUNT(*) FROM new_lines").fetchone()[0],
        "update_rows": upd[0],
        "update_orderkey": upd[1],
        "affected_dates": [str(d) for d in dates],
        "label": "synthetic, generated",
        "rule": "fixed arithmetic, no random generator; delta wins on key in the staging merge",
    }
    (out / "delta_manifest.json").write_text(json.dumps(counts, indent=2, default=str) + "\n")
    print(json.dumps(counts, indent=2, default=str))


if __name__ == "__main__":
    main()
