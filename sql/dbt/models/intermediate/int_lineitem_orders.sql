SELECT l.l_orderkey, l.l_partkey, l.l_suppkey, l.l_linenumber, l.l_quantity, l.l_extendedprice, l.l_discount, l.l_tax, l.l_returnflag, l.l_linestatus, l.l_shipdate, l.l_commitdate, l.l_receiptdate, l.l_shipinstruct, l.l_shipmode, l.l_comment, o.o_custkey, o.o_orderstatus, o.o_totalprice, o.o_orderdate, o.o_orderpriority
FROM {{ ref('stg_lineitem') }} l
JOIN {{ ref('stg_orders') }} o ON l.l_orderkey = o.o_orderkey
