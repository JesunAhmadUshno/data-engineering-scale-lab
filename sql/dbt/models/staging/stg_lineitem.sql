{{ config(materialized='view') }}
SELECT * FROM read_parquet('{{ var('data_dir') }}/lineitem/*.parquet')
{% if var('delta_dir', '') != '' %}
WHERE (l_orderkey, l_linenumber) NOT IN (
    SELECT l_orderkey, l_linenumber
    FROM read_parquet('{{ var('delta_dir') }}/lineitem_update.parquet')
)
UNION ALL
SELECT * FROM read_parquet('{{ var('delta_dir') }}/lineitem_delta.parquet')
UNION ALL
SELECT * FROM read_parquet('{{ var('delta_dir') }}/lineitem_update.parquet')
{% endif %}
