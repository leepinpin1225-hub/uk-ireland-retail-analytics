# Power BI build guide

The report reads the **star schema in SQL Server** (built by `sql/01`–`03`) plus a few small CSV files
of real statistics and analysis results. Allow about 60–90 minutes.

## 1. Get data

**Home → Get data → SQL Server**
- Server: `localhost` (or `localhost\SQLEXPRESS` if you use SQL Server Express) · Database: `HearthlineRetail` · Mode: **Import**
- Tick: `dw.dim_date`, `dw.dim_store`, `dw.dim_city`, `dw.dim_product`, `dw.dim_customer`, `dw.fact_sales`, `dw.fact_returns`
- Click **Transform Data** (Power Query), rename each query to drop the `dw ` prefix → `fact_sales`, `dim_date`, …

**Get data → Text/CSV** (folder `data/clean/`), also renamed without spaces:
`online_share_by_market.csv`, `taiwan_online_penetration_by_category.csv`, `rfm_segments.csv`, `cohort_retention.csv`, `basket_pairs.csv`

In Power Query, check the types: `online_share_by_market[date]` = Date, percentages = Decimal number. **Close & Apply.**

## 2. Model view: relationships (star schema)

| From (many) | To (one) | Notes |
|---|---|---|
| fact_sales[date_key] | dim_date[date_key] | |
| fact_sales[store_id] | dim_store[store_id] | |
| fact_sales[product_id] | dim_product[product_id] | |
| fact_sales[customer_id] | dim_customer[customer_id] | |
| fact_returns[date_key] | dim_date[date_key] | return date |
| fact_returns[store_id] | dim_store[store_id] | |
| fact_returns[product_id] | dim_product[product_id] | |
| dim_store[city] | dim_city[city] | **snowflake branch**: real city statistics hang off the store dimension |
| rfm_segments[customer_id] | dim_customer[customer_id] | one-to-one is fine |

All single direction (dimension → fact). Then select `dim_date` → **Table tools → Mark as date table** → column `date`.
Sort `dim_date[month_name]` by `month_no` (Column tools → Sort by column).

## 3. Measures

Open **DAX query view** → paste all of `measures.dax` → **Run** → click **Update model with changes**.
Set formats (Measure tools → Format): £ for Net Sales, Refunds, Net Revenue, Gross Margin, AOV, YTD, LY, 3M Avg;
percentage (1 decimal) for every “%” measure; `0.00` for Market Capture Index.

## 4. Row-level security (each city manager sees only their store)

**Modeling → Manage roles → New**
- Role `City Manager`, table `dim_store`, DAX filter: `[manager_email] = USERPRINCIPALNAME()`
- Role `Scotland`, table `dim_store`, DAX filter: `[nation] = "Scotland"`

Test: **Modeling → View as** → tick `City Manager` + *Other user* `glasgow.manager@hearthline.example`. Every page should show Glasgow only.

## 5. Report pages

Use one colour for Hearthline (blue), orange only to highlight the point the page is making.

**Page 1 · Overview**
- Cards: Net Sales, YoY Growth %, Orders, Avg Order Value, Gross Margin %, Online Share %, Return Rate %
- Line chart: `dim_date[year_month]` × Net Sales, legend `fact_sales[channel]`
- Bar chart: `dim_store[store_name]` × Net Sales, sorted descending; tooltip: Store Rank
- Slicers (one row, top): `dim_date[year]`, `dim_store[nation]`, `dim_product[category]`

**Page 2 · Cities vs real market**
- Map (or filled map): `dim_city[city]` location, bubble size = Net Sales, colour saturation = Market Capture Index
- Bar chart: `dim_city[city]` × Market Capture Index with a constant line at 1 (Analytics pane)
- Table: city, population, gdhi_per_head, median_pay, retail_pull_index, Net Sales, Market Capture Index
- Text box: "Population, income and retail output are official ONS/CSO statistics; sales are simulated."

**Page 3 · Customers**
- Bar: `rfm_segments[segment]` × count of customer_id and sum of monetary
- Matrix (heatmap): rows `cohort_retention[cohort]`, columns `quarters_since_first`, values `retention_pct`, conditional formatting → background colour scale
- Table: `basket_pairs` top 10 by lift (subcategory_x, subcategory_y, support_pct, confidence_pct, lift)

**Page 4 · Markets (UK · US · Taiwan)**
- Line chart: `online_share_by_market[date]` × `online_share_pct`, legend `market`
- Bar: `taiwan_online_penetration_by_category[category]` × `online_penetration_pct`

## 6. Save and share

- Save as `powerbi/Hearthline_Retail.pbix`.
- **File → Export → Export to PDF**, save as `powerbi/Hearthline_Retail.pdf`.
- Screenshot each page into `images/powerbi_page1.png` … for the README.
- *Publish to web* needs a work account with that setting allowed. If your university account blocks it, the PDF and screenshots are enough; recruiters rarely open .pbix files.
