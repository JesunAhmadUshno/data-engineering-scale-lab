{{ config(tags=['gate']) }}
-- F09: a missing l_partkey column must block promotion. Schema check:
-- returns one row when the column is absent from the staging relation.
SELECT 1 AS missing_column
WHERE NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'stg_lineitem' AND column_name = 'l_partkey'
)
