"""Frozen transformation registry. Mirrors PREREG.md Section 6 exactly.

Each entry: key, canonical SQL file, output relation name, canonical output
columns in order (the checksum orders by all of them), and dependencies.
"""

LINEITEM_COLS = [
    "l_orderkey", "l_partkey", "l_suppkey", "l_linenumber", "l_quantity",
    "l_extendedprice", "l_discount", "l_tax", "l_returnflag", "l_linestatus",
    "l_shipdate", "l_commitdate", "l_receiptdate", "l_shipinstruct",
    "l_shipmode", "l_comment",
]

TRANSFORMATIONS = [
    {
        "key": "t1",
        "sql": "sql/t1_filter.sql",
        "output": "filtered_lineitem",
        "columns": LINEITEM_COLS,
        "depends": ["lineitem"],
    },
    {
        "key": "t2",
        "sql": "sql/t2_join.sql",
        "output": "lineitem_orders",
        "columns": LINEITEM_COLS + [
            "o_custkey", "o_orderstatus", "o_totalprice", "o_orderdate",
            "o_orderpriority",
        ],
        "depends": ["lineitem", "orders"],
    },
    {
        "key": "t3",
        "sql": "sql/t3_aggregate.sql",
        "output": "daily_sales",
        "columns": ["order_date", "orders_count", "line_count", "gross_revenue", "net_revenue"],
        "depends": ["lineitem", "orders"],
    },
    {
        "key": "t4",
        "sql": "sql/t4_window.sql",
        "output": "ranked_sales",
        "columns": ["order_date", "l_orderkey", "l_linenumber", "line_amount", "rnk"],
        "depends": ["lineitem_orders"],
    },
    {
        "key": "t5",
        "sql": "sql/t5_conversion.sql",
        "output": "converted",
        "columns": [
            "l_orderkey", "l_linenumber", "quantity_int", "extended_price",
            "total_price", "shipdate_text", "orderdate_text", "discount_pct",
        ],
        "depends": ["lineitem", "orders"],
    },
    {
        "key": "t6",
        "sql": "sql/t6_sort_limit.sql",
        "output": "top_10_daily",
        "columns": ["order_date", "orders_count", "gross_revenue", "top_line_amount"],
        "depends": ["daily_sales", "ranked_sales"],
    },
]

BY_KEY = {t["key"]: t for t in TRANSFORMATIONS}
BY_OUTPUT = {t["output"]: t for t in TRANSFORMATIONS}

# dbt model name per transformation output (Arm C).
DBT_MODELS = {
    "filtered_lineitem": ("intermediate", "int_filtered_lineitem"),
    "lineitem_orders": ("intermediate", "int_lineitem_orders"),
    "daily_sales": ("marts", "daily_sales"),
    "ranked_sales": ("marts", "ranked_sales"),
    "converted": ("intermediate", "int_converted"),
    "top_10_daily": ("marts", "top_10_daily"),
}
