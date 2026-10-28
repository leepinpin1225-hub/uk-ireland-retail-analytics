/* =====================================================================================
   03  Clean the staging data and build the STAR SCHEMA (schema dw)

        dim_date ─┐
       dim_store ─┼── fact_sales ── dim_product        fact_returns joins the same dimensions
    dim_customer ─┘

   Why a star schema? Each fact row (one product on one order) points to small, descriptive
   dimension tables. Power BI is designed for this shape: filters flow from dimensions to the fact
   table, DAX stays simple, and the model is fast. (A SNOWFLAKE schema would split dimensions further,
   e.g. dim_product -> dim_category. I keep category inside dim_product because it is small.)
   ===================================================================================== */
USE HearthlineRetail;
GO
DROP TABLE IF EXISTS dw.fact_returns, dw.fact_sales, dw.dim_customer, dw.dim_product, dw.dim_store, dw.dim_date, dw.dim_city;
GO

/* ---------- dim_date: one row per day, built with a recursive CTE -------------------- */
WITH d AS (
    SELECT CAST('2024-01-01' AS DATE) AS dt
    UNION ALL
    SELECT DATEADD(DAY, 1, dt) FROM d WHERE dt < '2026-12-31'
)
SELECT
    YEAR(dt) * 10000 + MONTH(dt) * 100 + DAY(dt)   AS date_key,      -- e.g. 20260131
    dt                                             AS [date],
    YEAR(dt)                                       AS [year],
    DATEPART(QUARTER, dt)                          AS quarter_no,
    CONCAT(YEAR(dt), ' Q', DATEPART(QUARTER, dt))  AS year_quarter,
    MONTH(dt)                                      AS month_no,
    FORMAT(dt, 'MMM')                              AS month_name,
    FORMAT(dt, 'yyyy-MM')                          AS year_month,
    DATENAME(WEEKDAY, dt)                          AS weekday_name,
    CASE WHEN DATEPART(WEEKDAY, dt) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend   -- assumes DATEFIRST 7 (US/UK default)
INTO dw.dim_date
FROM d
OPTION (MAXRECURSION 0);
ALTER TABLE dw.dim_date ALTER COLUMN date_key INT NOT NULL;     -- SELECT INTO creates nullable columns; a primary key needs NOT NULL
ALTER TABLE dw.dim_date ADD CONSTRAINT pk_dim_date PRIMARY KEY (date_key);

/* ---------- dim_city: the REAL official statistics, one row per city ------------------ */
SELECT city, nation, population, gdhi_per_head, median_pay, retail_gva_gbp_m, spending_power_gbp_m,
       CASE WHEN retail_gva_is_estimate = 'True' THEN 1 ELSE 0 END AS retail_gva_is_estimate,
       retail_gva_per_head, retail_pull_index
INTO dw.dim_city
FROM stg.city_profile;
ALTER TABLE dw.dim_city ALTER COLUMN city VARCHAR(50) NOT NULL;
ALTER TABLE dw.dim_city ADD CONSTRAINT pk_dim_city PRIMARY KEY (city);

/* ---------- dim_store ------------------------------------------------------------------- */
SELECT store_id, store_name, city, nation, country, channel, opened_date, floor_area_sqft, manager_email
INTO dw.dim_store
FROM stg.stores;
ALTER TABLE dw.dim_store ALTER COLUMN store_id VARCHAR(10) NOT NULL;
ALTER TABLE dw.dim_store ADD CONSTRAINT pk_dim_store PRIMARY KEY (store_id);

/* ---------- dim_product ------------------------------------------------------------------ */
SELECT product_id, sku, product_name, subcategory, category, unit_price AS list_price, unit_cost
INTO dw.dim_product
FROM stg.products;
ALTER TABLE dw.dim_product ALTER COLUMN product_id VARCHAR(10) NOT NULL;
ALTER TABLE dw.dim_product ADD CONSTRAINT pk_dim_product PRIMARY KEY (product_id);

/* ---------- dim_customer: fix inconsistent city text ------------------------------------
   Problems found in stg.customers.home_city: extra spaces, UPPER/lower case, and the nickname 'Mcr'.
   TRIM removes spaces; matching on LOWER() makes the comparison case-insensitive; the join to
   dim_city returns the official spelling. A guest row (-1) is added for orders with no customer. */
SELECT
    c.customer_id,
    c.signup_date,
    COALESCE(dc.city, 'Unknown')                         AS home_city,
    CASE WHEN c.loyalty_member = 'True' THEN 1 ELSE 0 END AS is_loyalty_member,
    c.age_band,
    CASE WHEN c.marketing_opt_in = 'True' THEN 1 ELSE 0 END AS marketing_opt_in
INTO dw.dim_customer
FROM stg.customers AS c
LEFT JOIN dw.dim_city AS dc
       ON LOWER(dc.city) = CASE WHEN LOWER(TRIM(c.home_city)) = 'mcr' THEN 'manchester'
                                ELSE LOWER(TRIM(c.home_city)) END;

INSERT INTO dw.dim_customer (customer_id, signup_date, home_city, is_loyalty_member, age_band, marketing_opt_in)
VALUES ('GUEST', NULL, 'Unknown', 0, 'Unknown', 0);
ALTER TABLE dw.dim_customer ALTER COLUMN customer_id VARCHAR(10) NOT NULL;
ALTER TABLE dw.dim_customer ADD CONSTRAINT pk_dim_customer PRIMARY KEY (customer_id);

/* ---------- fact_sales: one row per order line ------------------------------------------
   Cleaning rules:
     1. Duplicate order lines (same order_line_id sent twice) -> keep one with ROW_NUMBER().
     2. Staff test orders with unit_price = 0 -> excluded.
     3. Guest checkouts (no customer_id) -> mapped to 'GUEST' so every row joins to dim_customer. */
WITH dedup AS (
    SELECT ol.*,
           ROW_NUMBER() OVER (PARTITION BY ol.order_line_id ORDER BY ol.order_line_id) AS rn
    FROM stg.order_lines AS ol
)
SELECT
    d.order_line_id,
    d.order_id,
    YEAR(o.order_datetime) * 10000 + MONTH(o.order_datetime) * 100 + DAY(o.order_datetime) AS date_key,   -- faster than FORMAT() on 800k rows
    o.order_datetime,
    o.store_id,
    COALESCE(NULLIF(o.customer_id, ''), 'GUEST')            AS customer_id,
    d.product_id,
    o.channel,
    o.promo_code,
    o.payment_method,
    d.quantity,
    d.unit_price,
    d.discount_pct,
    CAST(d.quantity * d.unit_price                      AS DECIMAL(12,2)) AS gross_sales,
    CAST(d.quantity * d.unit_price * d.discount_pct     AS DECIMAL(12,2)) AS discount_amount,
    CAST(d.quantity * d.unit_price * (1 - d.discount_pct) AS DECIMAL(12,2)) AS net_sales,
    CAST(d.quantity * p.unit_cost                       AS DECIMAL(12,2)) AS cost_of_goods
INTO dw.fact_sales
FROM dedup AS d
JOIN stg.orders   AS o ON o.order_id = d.order_id
JOIN stg.products AS p ON p.product_id = d.product_id
WHERE d.rn = 1
  AND d.unit_price > 0;

ALTER TABLE dw.fact_sales ALTER COLUMN order_line_id VARCHAR(10) NOT NULL;
ALTER TABLE dw.fact_sales ADD CONSTRAINT pk_fact_sales PRIMARY KEY (order_line_id);
CREATE INDEX ix_fact_sales_date  ON dw.fact_sales (date_key);
CREATE INDEX ix_fact_sales_store ON dw.fact_sales (store_id);

/* ---------- fact_returns: refund value at the price actually paid ------------------------ */
SELECT
    r.return_id,
    r.order_line_id,
    YEAR(r.return_date) * 10000 + MONTH(r.return_date) * 100 + DAY(r.return_date) AS date_key,
    f.store_id, f.customer_id, f.product_id, f.channel,
    r.quantity_returned,
    r.reason,
    CAST(r.quantity_returned * f.unit_price * (1 - f.discount_pct) AS DECIMAL(12,2)) AS refund_amount
INTO dw.fact_returns
FROM stg.returns AS r
JOIN dw.fact_sales AS f ON f.order_line_id = r.order_line_id;

/* ---------- checks -------------------------------------------------------------------- */
SELECT 'staging lines' AS step, COUNT(*) AS n FROM stg.order_lines
UNION ALL SELECT 'fact_sales (after cleaning)', COUNT(*) FROM dw.fact_sales
UNION ALL SELECT 'customers with unknown city', COUNT(*) FROM dw.dim_customer WHERE home_city = 'Unknown' AND customer_id <> 'GUEST'
UNION ALL SELECT 'fact_returns', COUNT(*) FROM dw.fact_returns;
GO
