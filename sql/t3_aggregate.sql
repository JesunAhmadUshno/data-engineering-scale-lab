SELECT o.o_orderdate AS order_date, COUNT(DISTINCT l.l_orderkey) AS orders_count, COUNT(*) AS line_count, SUM(l.l_extendedprice * (1 - l.l_discount)) AS gross_revenue, SUM(l.l_extendedprice * (1 - l.l_discount) * (1 + l.l_tax)) AS net_revenue
FROM lineitem l
JOIN orders o ON l.l_orderkey = o.o_orderkey
GROUP BY o.o_orderdate
