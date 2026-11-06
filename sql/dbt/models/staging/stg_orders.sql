{{ config(materialized='view') }}
SELECT * FROM read_parquet('{{ var('data_dir') }}/orders/*.parquet')
{% if var('delta_dir', '') != '' %}
UNION ALL
SELECT * FROM read_parquet('{{ var('delta_dir') }}/orders_delta.parquet')
{% endif %}
