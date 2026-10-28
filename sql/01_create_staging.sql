/* =====================================================================================
   01  Create the database and STAGING tables (raw CSV lands here unchanged)
   Run in SQL Server (SSMS or VS Code + mssql extension).
   ===================================================================================== */
IF DB_ID('HearthlineRetail') IS NULL CREATE DATABASE HearthlineRetail;
GO
USE HearthlineRetail;
GO
IF SCHEMA_ID('stg') IS NULL EXEC('CREATE SCHEMA stg');
IF SCHEMA_ID('dw')  IS NULL EXEC('CREATE SCHEMA dw');
GO

DROP TABLE IF EXISTS stg.stores, stg.customers, stg.products, stg.orders, stg.order_lines, stg.returns, stg.city_profile;

CREATE TABLE stg.stores (
    store_id VARCHAR(10), city VARCHAR(50), nation VARCHAR(30), store_name VARCHAR(80), country VARCHAR(30),
    channel VARCHAR(10), opened_date DATE, floor_area_sqft INT, manager_email VARCHAR(100));

CREATE TABLE stg.customers (
    customer_id VARCHAR(10), signup_date DATE, home_city VARCHAR(50), loyalty_member VARCHAR(5),
    age_band VARCHAR(10), marketing_opt_in VARCHAR(5));

CREATE TABLE stg.products (
    product_id VARCHAR(10), category VARCHAR(40), subcategory VARCHAR(40), product_name VARCHAR(80),
    unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2), sku VARCHAR(20));

CREATE TABLE stg.orders (
    store_id VARCHAR(10), channel VARCHAR(10), customer_id VARCHAR(10), order_datetime DATETIME2(0),
    order_id VARCHAR(10), promo_code VARCHAR(20), payment_method VARCHAR(20));

CREATE TABLE stg.order_lines (
    order_line_id VARCHAR(10), order_id VARCHAR(10), product_id VARCHAR(10),
    unit_price DECIMAL(10,2), quantity INT, discount_pct DECIMAL(4,2));

CREATE TABLE stg.returns (
    return_id VARCHAR(10), order_line_id VARCHAR(10), return_date DATE, quantity_returned INT, reason VARCHAR(40));

-- real official statistics (from notebook 01)
CREATE TABLE stg.city_profile (
    city VARCHAR(50), nation VARCHAR(30), code VARCHAR(12), population INT, gdhi_per_head DECIMAL(12,2),
    median_pay DECIMAL(12,2), retail_gva_gbp_m DECIMAL(12,2), spending_power_gbp_m DECIMAL(14,2),
    retail_gva_is_estimate VARCHAR(5), retail_gva_per_head DECIMAL(12,2), retail_pull_index DECIMAL(8,4));
GO
