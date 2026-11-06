{{ config(tags=['gate']) }}
-- F07: a fully duplicated lineitem row must block promotion.
SELECT l_orderkey, l_partkey, l_suppkey, l_linenumber, l_quantity,
       l_extendedprice, l_discount, l_tax, l_returnflag, l_linestatus,
       l_shipdate, l_commitdate, l_receiptdate, l_shipinstruct, l_shipmode,
       COUNT(*) AS copies
FROM {{ ref('stg_lineitem') }}
GROUP BY ALL
HAVING COUNT(*) > 1
