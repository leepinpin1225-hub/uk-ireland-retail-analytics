/* =====================================================================================
   02  Load the CSV files into staging with BULK INSERT
   >>> Change @folder below to YOUR project folder (keep the trailing backslash) <<<
   BULK INSERT needs a literal path, so the statements are built as dynamic SQL.
   If you get "Operating system error 5 (Access is denied)": the SQL Server service cannot read your
   OneDrive folder. Copy the data folder to C:\HearthlineData\ and point @folder there.
   ===================================================================================== */
USE HearthlineRetail;
GO
DECLARE @folder NVARCHAR(400) = N'C:\path\to\uk-ireland-retail-analytics\data\';
DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql += N'
TRUNCATE TABLE stg.' + t.name + N';
BULK INSERT stg.' + t.name + N' FROM ''' + @folder + t.sub + t.name + N'.csv''
WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', ROWTERMINATOR = ''0x0a'', CODEPAGE = ''65001'', TABLOCK);'
FROM (VALUES ('stores', 'simulated\'), ('customers', 'simulated\'), ('products', 'simulated\'),
             ('orders', 'simulated\'), ('order_lines', 'simulated\'), ('returns', 'simulated\'),
             ('city_profile', 'clean\')) AS t(name, sub);

EXEC sp_executesql @sql;

-- check: row counts should match the CSV files
SELECT 'stores' AS tbl, COUNT(*) AS n FROM stg.stores UNION ALL
SELECT 'customers', COUNT(*) FROM stg.customers UNION ALL
SELECT 'products', COUNT(*) FROM stg.products UNION ALL
SELECT 'orders', COUNT(*) FROM stg.orders UNION ALL
SELECT 'order_lines', COUNT(*) FROM stg.order_lines UNION ALL
SELECT 'returns', COUNT(*) FROM stg.returns UNION ALL
SELECT 'city_profile', COUNT(*) FROM stg.city_profile;
GO
