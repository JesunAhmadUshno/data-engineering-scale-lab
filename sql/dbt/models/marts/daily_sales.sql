{{ config(materialized='incremental', unique_key='order_date') }}
SELECT o.o_orderdate AS order_date, COUNT(DISTINCT l.l_orderkey) AS orders_count, COUNT(*) AS line_count, SUM(l.l_extendedprice * (1 - l.l_discount)) AS gross_revenue, SUM(l.l_extendedprice * (1 - l.l_discount) * (1 + l.l_tax)) AS net_revenue
FROM {{ ref('stg_lineitem') }} l
JOIN {{ ref('stg_orders') }} o ON l.l_orderkey = o.o_orderkey
{% if is_incremental() %}
WHERE o.o_orderdate IN (SELECT order_date FROM {{ ref('delta_dates') }})
{% endif %}
GROUP BY o.o_orderdate
