"""U-07 receipt: the dbt models carry the same logic as the canonical SQL.

Each dbt model is normalized back to canonical form (jinja config removed,
ref() calls mapped back to the canonical relation names, and the
registered is_incremental() wrapper block removed for T3 and T4), then
compared with sql/*.sql after collapsing whitespace. Arms A and B run the
canonical files directly, so parity here means all three arms run the
same logic.

Usage:
    python src/check_sql_parity.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REF_MAP = {
    "stg_lineitem": "lineitem",
    "stg_orders": "orders",
    "int_lineitem_orders": "lineitem_orders",
    "daily_sales": "daily_sales",
    "ranked_sales": "ranked_sales",
}

MODELS = {
    "t1": "sql/dbt/models/intermediate/int_filtered_lineitem.sql",
    "t2": "sql/dbt/models/intermediate/int_lineitem_orders.sql",
    "t3": "sql/dbt/models/marts/daily_sales.sql",
    "t4": "sql/dbt/models/marts/ranked_sales.sql",
    "t5": "sql/dbt/models/intermediate/int_converted.sql",
    "t6": "sql/dbt/models/marts/top_10_daily.sql",
}

CANONICAL = {
    "t1": "sql/t1_filter.sql",
    "t2": "sql/t2_join.sql",
    "t3": "sql/t3_aggregate.sql",
    "t4": "sql/t4_window.sql",
    "t5": "sql/t5_conversion.sql",
    "t6": "sql/t6_sort_limit.sql",
}


def norm(text):
    return re.sub(r"\s+", " ", text).strip().rstrip(";").strip()


def normalize_model(text):
    text = re.sub(r"--\s*depends_on:[^\n]*", " ", text)
    text = re.sub(r"\{\{\s*config\([^}]*\)\s*\}\}", " ", text)
    text = re.sub(
        r"\{%\s*if is_incremental\(\)\s*%\}.*?\{%\s*endif\s*%\}", " ", text, flags=re.S
    )
    def sub_ref(m):
        return REF_MAP[m.group(1)]
    text = re.sub(r"\{\{\s*ref\('([a-z_0-9]+)'\)\s*\}\}", sub_ref, text)
    return norm(text)


def main():
    bad = []
    for key in MODELS:
        model = normalize_model((ROOT / MODELS[key]).read_text())
        canon = norm((ROOT / CANONICAL[key]).read_text())
        status = "OK" if model == canon else "DIFF"
        print(f"{key}: {status}")
        if model != canon:
            bad.append(key)
            print("  model   :", model)
            print("  canonical:", canon)
    if bad:
        raise SystemExit(f"SQL parity failed for {bad}")
    print("all six dbt models match the canonical SQL logic")


if __name__ == "__main__":
    main()
