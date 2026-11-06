SELECT o_orderdate AS order_date, l_orderkey, l_linenumber, l_extendedprice * (1 - l_discount) AS line_amount, RANK() OVER (PARTITION BY o_orderdate ORDER BY l_extendedprice * (1 - l_discount) DESC) AS rnk
FROM lineitem_orders
