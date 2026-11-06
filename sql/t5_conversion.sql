SELECT l.l_orderkey, l.l_linenumber, CAST(l.l_quantity AS INTEGER) AS quantity_int, CAST(l.l_extendedprice AS DECIMAL(18,2)) AS extended_price, CAST(o.o_totalprice AS DECIMAL(18,2)) AS total_price, CAST(l.l_shipdate AS STRING) AS shipdate_text, CAST(o.o_orderdate AS STRING) AS orderdate_text, CAST(l.l_discount * 100 AS INTEGER) AS discount_pct
FROM lineitem l
JOIN orders o ON l.l_orderkey = o.o_orderkey
