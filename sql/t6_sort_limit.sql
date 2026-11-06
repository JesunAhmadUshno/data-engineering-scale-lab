SELECT d.order_date, d.orders_count, d.gross_revenue, MAX(r.line_amount) AS top_line_amount
FROM daily_sales d
JOIN ranked_sales r ON r.order_date = d.order_date AND r.rnk = 1
GROUP BY d.order_date, d.orders_count, d.gross_revenue
ORDER BY d.gross_revenue DESC, d.order_date ASC
LIMIT 10
