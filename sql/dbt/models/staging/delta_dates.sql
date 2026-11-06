{{ config(materialized='ephemeral') }}
{% if var('affected_dates_path', '') != '' %}
SELECT CAST(order_date AS DATE) AS order_date
FROM read_parquet('{{ var('affected_dates_path') }}')
{% else %}
SELECT CAST(NULL AS DATE) AS order_date WHERE FALSE
{% endif %}
