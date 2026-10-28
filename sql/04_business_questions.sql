/* =====================================================================================
   04  Business questions answered in SQL
   Techniques shown: multi-table JOINs, CTEs, window functions (LAG, RANK, ROW_NUMBER,
   running totals, moving averages), CASE, self-join for market basket, cohort analysis.
   Revenue = net_sales (after discounts) minus refunds unless stated.
   ===================================================================================== */
USE HearthlineRetail;
GO

/* Q1. Monthly revenue and year-on-year growth (LAG over 12 months) ------------------------ */
WITH monthly AS (
    SELECT d.year_month, d.[year], d.month_no, SUM(f.net_sales) AS revenue
    FROM dw.fact_sales f
    JOIN dw.dim_date d ON d.date_key = f.date_key
    GROUP BY d.year_month, d.[year], d.month_no
)
SELECT year_month,
       revenue,
       LAG(revenue, 12) OVER (ORDER BY year_month)                                         AS revenue_same_month_last_year,
       CAST(100.0 * (revenue / NULLIF(LAG(revenue, 12) OVER (ORDER BY year_month), 0) - 1) AS DECIMAL(6,1)) AS yoy_growth_pct,
       AVG(revenue) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)     AS moving_avg_3m
FROM monthly
ORDER BY year_month;

/* Q2. Store league table for the last 12 months: revenue, rank overall and within its nation */
WITH last12 AS (
    SELECT f.store_id, SUM(f.net_sales) AS revenue, COUNT(DISTINCT f.order_id) AS orders
    FROM dw.fact_sales f
    WHERE f.order_datetime >= '2025-10-01' AND f.order_datetime < '2026-10-01'
      AND f.channel = 'Store'
    GROUP BY f.store_id
)
SELECT s.store_name, s.nation, l.revenue, l.orders,
       CAST(l.revenue / l.orders AS DECIMAL(8,2))                       AS avg_order_value,
       CAST(l.revenue / s.floor_area_sqft AS DECIMAL(8,2))              AS revenue_per_sqft,
       RANK() OVER (ORDER BY l.revenue DESC)                            AS rank_overall,
       RANK() OVER (PARTITION BY s.nation ORDER BY l.revenue DESC)      AS rank_in_nation
FROM last12 l
JOIN dw.dim_store s ON s.store_id = l.store_id
ORDER BY rank_overall;

/* Q3. Store performance vs the city's REAL market size ---------------------------------
   Revenue share vs share of spending power (official data). An index above 1 means the store
   captures more than its "fair share" of the local market; below 1 = untapped potential. */
WITH store_rev AS (
    SELECT s.city, SUM(f.net_sales) AS revenue
    FROM dw.fact_sales f JOIN dw.dim_store s ON s.store_id = f.store_id
    WHERE f.channel = 'Store' AND f.order_datetime >= '2025-10-01'
    GROUP BY s.city
)
SELECT c.city, c.population, c.gdhi_per_head, c.retail_pull_index,
       r.revenue,
       CAST(r.revenue / SUM(r.revenue) OVER () * 100 AS DECIMAL(5,1))                              AS revenue_share_pct,
       CAST(c.spending_power_gbp_m / SUM(c.spending_power_gbp_m) OVER () * 100 AS DECIMAL(5,1))    AS spending_power_share_pct,
       CAST((r.revenue / SUM(r.revenue) OVER ()) /
            (c.spending_power_gbp_m / SUM(c.spending_power_gbp_m) OVER ()) AS DECIMAL(5,2))       AS market_capture_index
FROM store_rev r
JOIN dw.dim_city c ON c.city = r.city
ORDER BY market_capture_index;

/* Q4. Online vs store: where do online customers live? (online demand by home city) ------ */
SELECT cu.home_city,
       SUM(CASE WHEN f.channel = 'Online' THEN f.net_sales ELSE 0 END)                 AS online_revenue,
       SUM(CASE WHEN f.channel = 'Store'  THEN f.net_sales ELSE 0 END)                 AS store_revenue,
       CAST(100.0 * SUM(CASE WHEN f.channel = 'Online' THEN f.net_sales ELSE 0 END)
                  / SUM(f.net_sales) AS DECIMAL(5,1))                                    AS online_share_pct
FROM dw.fact_sales f
JOIN dw.dim_customer cu ON cu.customer_id = f.customer_id
WHERE cu.customer_id <> 'GUEST'
GROUP BY cu.home_city
ORDER BY online_share_pct DESC;

/* Q5. Top 3 products in each category (ROW_NUMBER inside a CTE) -------------------------- */
WITH product_sales AS (
    SELECT p.category, p.product_name, SUM(f.net_sales) AS revenue, SUM(f.quantity) AS units,
           ROW_NUMBER() OVER (PARTITION BY p.category ORDER BY SUM(f.net_sales) DESC) AS rn
    FROM dw.fact_sales f JOIN dw.dim_product p ON p.product_id = f.product_id
    GROUP BY p.category, p.product_name
)
SELECT category, rn AS rank_in_category, product_name, revenue, units
FROM product_sales
WHERE rn <= 3
ORDER BY category, rn;

/* Q6. Margin and returns by category ------------------------------------------------------ */
WITH s AS (
    SELECT p.category, SUM(f.net_sales) AS net_sales, SUM(f.cost_of_goods) AS cogs
    FROM dw.fact_sales f JOIN dw.dim_product p ON p.product_id = f.product_id
    GROUP BY p.category
), r AS (
    SELECT p.category, SUM(r.refund_amount) AS refunds
    FROM dw.fact_returns r JOIN dw.dim_product p ON p.product_id = r.product_id
    GROUP BY p.category
)
SELECT s.category, s.net_sales, r.refunds,
       CAST(100.0 * r.refunds / s.net_sales AS DECIMAL(5,1))                    AS refund_rate_pct,
       CAST(100.0 * (s.net_sales - s.cogs) / s.net_sales AS DECIMAL(5,1))       AS gross_margin_pct
FROM s LEFT JOIN r ON r.category = s.category
ORDER BY refund_rate_pct DESC;

/* Q7. Return rate by channel and reason ---------------------------------------------------- */
SELECT r.channel, r.reason, COUNT(*) AS returns,
       CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY r.channel) AS DECIMAL(5,1)) AS pct_of_channel_returns
FROM dw.fact_returns r
GROUP BY r.channel, r.reason
ORDER BY r.channel, returns DESC;

/* Q8. Customer cohorts: % of each first-purchase-quarter cohort still buying N quarters later */
WITH first_purchase AS (
    SELECT customer_id, MIN(order_datetime) AS first_dt
    FROM dw.fact_sales WHERE customer_id <> 'GUEST'
    GROUP BY customer_id
), activity AS (
    SELECT DISTINCT f.customer_id,
           DATEFROMPARTS(YEAR(fp.first_dt), (DATEPART(QUARTER, fp.first_dt) - 1) * 3 + 1, 1) AS cohort_quarter,
           (YEAR(f.order_datetime) - YEAR(fp.first_dt)) * 4
             + DATEPART(QUARTER, f.order_datetime) - DATEPART(QUARTER, fp.first_dt)        AS quarters_since_first
    FROM dw.fact_sales f JOIN first_purchase fp ON fp.customer_id = f.customer_id
), cohort_size AS (
    SELECT cohort_quarter, COUNT(*) AS customers FROM activity WHERE quarters_since_first = 0 GROUP BY cohort_quarter
)
SELECT a.cohort_quarter, cs.customers, a.quarters_since_first,
       CAST(100.0 * COUNT(*) / cs.customers AS DECIMAL(5,1)) AS retention_pct
FROM activity a JOIN cohort_size cs ON cs.cohort_quarter = a.cohort_quarter
WHERE a.cohort_quarter >= '2024-01-01'
GROUP BY a.cohort_quarter, cs.customers, a.quarters_since_first
ORDER BY a.cohort_quarter, a.quarters_since_first;

/* Q9. Days between purchases (LAG per customer) -------------------------------------------- */
WITH orders AS (
    SELECT DISTINCT customer_id, order_id, order_datetime
    FROM dw.fact_sales WHERE customer_id <> 'GUEST'
), gaps AS (
    SELECT customer_id,
           DATEDIFF(DAY, LAG(order_datetime) OVER (PARTITION BY customer_id ORDER BY order_datetime), order_datetime) AS days_since_previous
    FROM orders
)
SELECT COUNT(*) AS repeat_orders,
       AVG(CAST(days_since_previous AS FLOAT)) AS avg_days_between_orders
FROM gaps
WHERE days_since_previous IS NOT NULL;

/* Q10. Market basket: which subcategories are bought together? (self-join) ---------------
   support = share of orders containing both; confidence = P(B | A); lift > 1 = bought together
   more often than chance. */
WITH order_items AS (
    SELECT DISTINCT f.order_id, p.subcategory
    FROM dw.fact_sales f JOIN dw.dim_product p ON p.product_id = f.product_id
), totals AS (
    SELECT COUNT(DISTINCT order_id) AS n_orders FROM order_items
), item_counts AS (
    SELECT subcategory, COUNT(*) AS n_a FROM order_items GROUP BY subcategory
), pairs AS (
    SELECT a.subcategory AS item_a, b.subcategory AS item_b, COUNT(*) AS n_ab
    FROM order_items a
    JOIN order_items b ON a.order_id = b.order_id AND a.subcategory < b.subcategory
    GROUP BY a.subcategory, b.subcategory
)
SELECT TOP 10
       p.item_a, p.item_b, p.n_ab AS orders_with_both,
       CAST(100.0 * p.n_ab / t.n_orders AS DECIMAL(6,2))                                  AS support_pct,
       CAST(100.0 * p.n_ab / ca.n_a AS DECIMAL(6,1))                                      AS confidence_a_to_b_pct,
       CAST(1.0 * p.n_ab * t.n_orders / (ca.n_a * cb.n_a) AS DECIMAL(6,2))                AS lift
FROM pairs p
CROSS JOIN totals t
JOIN item_counts ca ON ca.subcategory = p.item_a
JOIN item_counts cb ON cb.subcategory = p.item_b
WHERE p.n_ab >= 200
ORDER BY lift DESC;
GO
