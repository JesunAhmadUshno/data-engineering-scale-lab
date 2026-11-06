-- depends_on: {{ ref('delta_dates') }}
{{ config(materialized='incremental', unique_key=['order_date', 'l_orderkey', 'l_linenumber']) }}
SELECT o_orderdate AS order_date, l_orderkey, l_linenumber, l_extendedprice * (1 - l_discount) AS line_amount, RANK() OVER (PARTITION BY o_orderdate ORDER BY l_extendedprice * (1 - l_discount) DESC) AS rnk
FROM {{ ref('int_lineitem_orders') }}
{% if is_incremental() %}
WHERE o_orderdate IN (SELECT order_date FROM {{ ref('delta_dates') }})
{% endif %}
