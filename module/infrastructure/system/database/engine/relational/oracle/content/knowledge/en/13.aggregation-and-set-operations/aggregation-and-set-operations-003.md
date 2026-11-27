# GROUP BY, Composite Grouping Keys, and Grouping Expressions in Oracle Database

A sales table can contain millions of order detail rows. When you need to know **revenue by region**, **order count by sales channel**, or **revenue by month and product**, you do not want every individual transaction row returned. You want Oracle to group rows sharing the same criteria and compute calculations per group. The **`GROUP BY`** clause performs this task.

The key point is that a group can be defined by **a single column**, **multiple columns combined into a composite grouping key**, or **an expression derived from the data**. For example, `GROUP BY region, channel` creates one group for each region-and-channel pair; `GROUP BY TRUNC(sold_at, 'MM')` creates groups by month; `GROUP BY UPPER(product_name)` collapses different letter casings into the same uppercase form according to the function's rules.

This lesson belongs to the **Aggregation and Set Operations** topic of Oracle Database, focusing on how groups are formed, how aggregate functions are used, filtering order, NULL handling, and common grouping expressions.

After studying this lesson, you will be able to:

- Explain how a group is formed with one or multiple grouping keys.
- Write `GROUP BY` with composite grouping keys such as `region, channel, product`.
- Use `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, and other aggregate functions per group.
- Distinguish between `WHERE` and `HAVING` in grouped queries.
- Group by month, year, numeric buckets, normalized forms, or `CASE` expressions.
- Understand how Oracle handles NULLs, duplicates, aliases, and result ordering.
- Recognize common errors such as `ORA-00979` and `ORA-00937`.

> **Example scope:** The SQL statements use standard Oracle syntax compatible with Oracle Database 19c. The practice table `GROUP_BY_LAB` is created in a lab schema/PDB you manage. Do not run DDL or sample data scripts on an active application schema.

## 1. What does GROUP BY do?

Suppose the `SALES` table stores each sales transaction as one row:

| Sale ID | Region | Channel | Product | Quantity | Unit price |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | North | Online | Laptop | 1 | 1,000 |
| 2 | North | Store | Laptop | 2 | 1,000 |
| 3 | North | Online | Mouse | 3 | 25 |
| 4 | South | Online | Laptop | 1 | 1,000 |
| 5 | South | Store | Mouse | 4 | 25 |

If you want to calculate revenue per region, group rows that share the same `REGION`:

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

Oracle forms one group for `North` and one group for `South`, then computes `SUM` over each group.

~~~text
SALES (transaction rows)
       |
       | GROUP BY region
       v
  +-----------+             +-----------+
  | North     |             | South     |
  | sale 1    |             | sale 4    |
  | sale 2    |             | sale 5    |
  | sale 3    |             |           |
  +-----+-----+             +-----+-----+
        |                         |
        v                         v
  SUM(quantity * price)     SUM(quantity * price)
        |                         |
        +------------+------------+
                     v
             Result: 1 row/group
~~~

**The result has one row per grouping key combination**, not one row per source record. Aggregate functions operate on the member rows of that group.

### 1.1. GROUP BY with a single column

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status;
~~~

The result has one row for each distinct status. If there are 500 `PAID` orders, 30 `PENDING` orders, and 5 `CANCELLED` orders, the result has three groups with the corresponding counts.

### 1.2. GROUP BY without an aggregate function

~~~sql
SELECT region
FROM sales
GROUP BY region;
~~~

This query is valid and returns distinct `REGION` values, similar to `SELECT DISTINCT region` in simple cases. However, when the goal is purely duplicate removal, `DISTINCT` usually expresses the intent more clearly:

~~~sql
SELECT DISTINCT region
FROM sales;
~~~

`GROUP BY` is useful when you want to compute aggregates or define groups for further calculations.

### 1.3. GROUP BY does not automatically sort results

Oracle does not guarantee row ordering just because you wrote `GROUP BY`:

~~~sql
SELECT region, COUNT(*) AS row_count
FROM sales
GROUP BY region;
~~~

If you need regions in alphabetical order:

~~~sql
SELECT region, COUNT(*) AS row_count
FROM sales
GROUP BY region
ORDER BY region;
~~~

**`GROUP BY` determines group membership; `ORDER BY` determines the display order of groups.** Do not rely on whatever incidental order your SQL tool happens to display.

## 2. Aggregate functions operate per group

Commonly used functions:

| Function | Meaning | Notes |
| --- | --- | --- |
| `COUNT(*)` | Counts all rows in the group | Does not skip a row just because a column is NULL |
| `COUNT(expression)` | Counts rows where expression is non-NULL | Does not count NULL values |
| `COUNT(DISTINCT expression)` | Counts distinct non-NULL values | Can be resource-intensive for large groups |
| `SUM(expression)` | Sum of non-NULL values | If all values are NULL, result is NULL |
| `AVG(expression)` | Average of non-NULL values | Equivalent to sum divided by count of evaluated values |
| `MIN(expression)` | Minimum value | Applicable to numbers, dates, strings per comparison rules |
| `MAX(expression)` | Maximum value | Applicable to numbers, dates, strings per comparison rules |
| `STDDEV(expression)` | Sample standard deviation | Used for dispersion analysis |
| `VARIANCE(expression)` | Sample variance | Used for dispersion analysis |

Example:

~~~sql
SELECT
    region,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold,
    AVG(unit_price) AS average_unit_price,
    MIN(unit_price) AS min_unit_price,
    MAX(unit_price) AS max_unit_price,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Oracle evaluates each function over the rows belonging to the same region. Aggregate expressions can differ; for instance, `AVG(unit_price)` is the row-level average unit price, whereas `SUM(quantity * unit_price)` is total revenue by quantity times unit price.

### 2.1. COUNT(*) and COUNT(column) differ

Suppose a group has 5 rows, of which only 3 rows have a non-NULL `EMAIL` column:

~~~sql
SELECT
    region,
    COUNT(*) AS all_rows,
    COUNT(email) AS rows_with_email,
    COUNT(DISTINCT email) AS distinct_emails
FROM customers
GROUP BY region;
~~~

- `COUNT(*)` returns 5 for that group.
- `COUNT(email)` returns 3 if exactly 3 email values are non-NULL.
- `COUNT(DISTINCT email)` returns the number of distinct emails, ignoring NULL.

Do not replace `COUNT(*)` with `COUNT(column)` if the business wants to count every row, as the result may be lower.

### 2.2. SUM and AVG ignore NULL

Suppose the values in a group are `10, 20, NULL`:

- `SUM(value)` is 30.
- `AVG(value)` is 15, not 10.
- `COUNT(value)` is 2.
- `COUNT(*)` is 3.

If every value in a group is NULL, `SUM` and `AVG` return NULL. To display 0 in that case:

~~~sql
SELECT
    region,
    NVL(SUM(discount_amount), 0) AS total_discount
FROM sales
GROUP BY region;
~~~

Here `NVL` only replaces a NULL aggregated result with 0 for presentation. Make sure 0 matches the business meaning; "no data" and "total equals 0" can be two different states.

### 2.3. Computed expressions inside aggregate functions

You do not need to create a physical revenue column just to compute a sum:

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS gross_revenue,
    SUM(quantity * unit_price * (1 - discount_pct / 100))
        AS net_revenue
FROM sales
GROUP BY region;
~~~

The expression inside `SUM` is evaluated for the rows in the group. Check data types, scale, NULLs, and rounding rules if the calculation involves currency. A calculation can evaluate to NULL if an operand is NULL; you can use `NVL`/`COALESCE` when the business specifies a fallback value.

## 3. Composite grouping keys: GROUP BY multiple columns

### 3.1. A grouping key can be a combination of multiple values

Suppose you want to see row counts and revenue by **region and sales channel**. Statement:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

Oracle forms groups by the **pair (`REGION`, `CHANNEL`)**:

~~~text
  (North, Online)       (North, Store)
       |                     |
       v                     v
  North/Online rows     North/Store rows
       |                     |
       v                     v
    COUNT, SUM             COUNT, SUM

  (South, Online)       (South, Store)
       |                     |
       v                     v
  South/Online rows     South/Store rows
       |                     |
       v                     v
    COUNT, SUM             COUNT, SUM
~~~

**Each distinct combination is a separate group.** Oracle does not group by `REGION` first and then independently by `CHANNEL`; the two values together define the grouping key.

### 3.2. Numeric example

Suppose the data is:

| Region | Channel | Sale rows | Revenue |
| --- | --- | ---: | ---: |
| North | Online | 2 | 1,075 |
| North | Store | 1 | 2,000 |
| South | Online | 1 | 1,000 |
| South | Store | 1 | 100 |

The query:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, channel;
~~~

produces only four groups if the table contains exactly the four combinations above. If `North / Partner` is added, Oracle creates a fifth group.

### 3.3. Adding grouping keys increases or preserves the number of groups

Compare:

~~~sql
-- Group by region:
SELECT region, COUNT(*) AS rows_per_region
FROM sales
GROUP BY region;

-- Group by region and channel:
SELECT region, channel, COUNT(*) AS rows_per_pair
FROM sales
GROUP BY region, channel;

-- Group by region, channel, and product:
SELECT region, channel, product, COUNT(*) AS rows_per_combination
FROM sales
GROUP BY region, channel, product;
~~~

When you add `CHANNEL` or `PRODUCT`, an existing group may be split further. The number of groups **cannot decrease** when adding a grouping key to the same dataset and filter conditions; it may stay the same if the new value does not subdivide any existing group.

If you add unnecessary keys, the report may become overly granular. For example, if a manager wants revenue by region and someone accidentally adds `ORDER_ID` to `GROUP BY`, each order may become its own group, making the report resemble detail-level data.

### 3.4. A composite grouping key is not string concatenation

Do not replace:

~~~sql
GROUP BY region, channel
~~~

with:

~~~sql
GROUP BY region || channel
~~~

The two are not equivalent. For example:

| Region | Channel | Direct concatenation |
| --- | --- | --- |
| `AB` | `C` | `ABC` |
| `A` | `BC` | `ABC` |

Two different combinations can produce the same concatenated string. Adding a delimiter is still not completely safe if the data itself might contain that delimiter. In addition, string concatenation has its own NULL rules and alters the type/meaning of the grouping key.

Write each component as its own expression:

~~~sql
SELECT region, channel, COUNT(*)
FROM sales
GROUP BY region, channel;
~~~

Oracle treats this as a two-component grouping key and compares each value according to its respective data type.

### 3.5. Composite grouping keys can contain NULL

Suppose a row has `REGION = 'North'` and `CHANNEL IS NULL`. Oracle still places that row into a group with key (`North`, `NULL`). Rows with the same combination of grouping values, including NULLs in the same positions, belong to the same group:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS row_count
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

To display the NULL group clearly, you can format the expression:

~~~sql
SELECT
    NVL(region, '(unknown region)') AS region_label,
    NVL(channel, '(unknown channel)') AS channel_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY
    NVL(region, '(unknown region)'),
    NVL(channel, '(unknown channel)')
ORDER BY region_label, channel_label;
~~~

Choose a replacement value that cannot be confused with real data if you need to preserve the distinction. If the data actually contains the literal label `'(unknown region)'`, the NVL above would merge real labels with NULL; you can instead use a separate flag or keep NULL and handle it at the presentation layer.

## 4. SELECT rules when using GROUP BY

### 4.1. Regular columns in SELECT must be grouped or aggregated

Valid query:

~~~sql
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

`REGION` is present in `GROUP BY`; `SUM(...)` is an aggregate function.

Invalid query:

~~~sql
SELECT region, product, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

`PRODUCT` is neither in `GROUP BY` nor inside an aggregate function. A `North` group can contain multiple products; Oracle does not know which product to display for a single summary revenue row of the whole group. In Oracle, the common error is `ORA-00979: not a GROUP BY expression`.

Fix according to the actual goal:

~~~sql
-- If you want revenue per product within each region:
SELECT region, product, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, product;

-- If you only want revenue by region:
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

Do not add columns to `GROUP BY` just to make the error disappear; doing so can change the aggregation level and corrupt the report's meaning.

### 4.2. SELECT expressions must match the grouping keys

Example:

~~~sql
SELECT
    UPPER(region) AS region_upper,
    COUNT(*) AS row_count
FROM sales
GROUP BY UPPER(region);
~~~

The non-aggregated expression in `SELECT` is the grouping expression itself. If you want to display `UPPER(region)` while grouping only by `region`, write the exact expression and understand that normalization may merge values differing in letter case into one group.

### 4.3. Aliases in GROUP BY

For compatibility with Oracle 19c, do not rely on a select-list alias in `GROUP BY` within the same query block:

~~~sql
-- Do not use this pattern in Oracle 19c:
SELECT TRUNC(sold_at, 'MM') AS sale_month,
       SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY sale_month;
~~~

Repeat the expression instead:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY sale_month;
~~~

Or place the expression in an inline view/CTE so the alias becomes an input column of the outer query block:

~~~sql
WITH sales_by_month_input AS (
    SELECT
        TRUNC(sold_at, 'MM') AS sale_month,
        quantity * unit_price AS line_revenue
    FROM sales
)
SELECT sale_month, SUM(line_revenue) AS revenue
FROM sales_by_month_input
GROUP BY sale_month
ORDER BY sale_month;
~~~

In the outer query, `SALE_MONTH` is a column of the inline view and can be used directly in `GROUP BY`. Aliases in `ORDER BY` within the same query block are supported under standard Oracle SQL rules.

## 5. WHERE and HAVING: filter rows first or filter groups after?

This is the core distinction when combining filtering with grouping:

| Clause | What does it filter? | Can group aggregate functions be used in the condition? |
| --- | --- | --- |
| `WHERE` | Source rows before grouping | Cannot directly use group aggregates like `SUM`/`COUNT` |
| `HAVING` | Groups after they are formed | Yes, e.g. `HAVING SUM(amount) > 1000` |

### 5.1. WHERE filters rows before GROUP BY

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region;
~~~

Oracle only feeds `PAID` rows into groups; `PENDING` or `CANCELLED` orders do not participate in the sum.

### 5.2. HAVING filters groups after aggregation

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING SUM(quantity * unit_price) >= 1000;
~~~

Oracle computes revenue for each region, then retains only groups with revenue of at least 1,000.

### 5.3. Combining WHERE and HAVING

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region, channel
HAVING SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

Mental sequence:

1. `WHERE` keeps only paid rows.
2. `GROUP BY` groups by region and channel.
3. `COUNT`/`SUM` compute over the remaining rows in each group.
4. `HAVING` drops groups with revenue below 500.
5. `ORDER BY` sorts the remaining groups.

### 5.4. Do not use HAVING instead of WHERE when early row filtering is possible

Example:

~~~sql
-- Syntactically valid, but does not express row-level filtering intent clearly:
SELECT region, COUNT(*)
FROM sales
GROUP BY region
HAVING region = 'North';
~~~

Prefer writing:

~~~sql
SELECT region, COUNT(*)
FROM sales
WHERE region = 'North'
GROUP BY region;
~~~

If a condition depends only on individual source rows, `WHERE` expresses the intent properly and can help Oracle reduce the volume of data that must be grouped. `HAVING` is meant for conditions depending on group results, such as total amounts or row counts.

## 6. GROUP BY with expressions

You do not have to group solely by a column's raw value. You can group by **an expression that defines the grouping key**. Common expressions include string functions, numeric arithmetic, date/time functions, and `CASE`.

### 6.1. Normalizing strings with UPPER/LOWER

Suppose the data contains `Laptop`, `LAPTOP`, and `laptop`. If the business wants them grouped together:

~~~sql
SELECT
    UPPER(product) AS normalized_product,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM sales
GROUP BY UPPER(product)
ORDER BY normalized_product;
~~~

Oracle groups by the result of `UPPER(product)`. This can merge casing variations into one group. However, `UPPER` is not a complete normalization mechanism for every language or diacritic difference; behavior also depends on character set, NLS/collation, and linguistic requirements. If you need accent-insensitive or linguistic comparison, design appropriate collation/normalization intentionally.

### 6.2. Grouping by prefix or substring

~~~sql
SELECT
    SUBSTR(product_code, 1, 3) AS product_family,
    COUNT(*) AS item_count
FROM products
GROUP BY SUBSTR(product_code, 1, 3)
ORDER BY product_family;
~~~

Codes sharing the same first three characters fall into the same group. Confirm that the first three characters truly represent a classification rule in the system; do not arbitrarily slice strings if codes vary in length or structure.

### 6.3. Grouping by numeric ranges

You can create groups by price buckets:

~~~sql
SELECT
    FLOOR(unit_price / 100) * 100 AS price_bucket,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM sales
GROUP BY FLOOR(unit_price / 100) * 100
ORDER BY price_bucket;
~~~

With unit prices 25, 50, 90, 125, and 210, the expression yields buckets 0, 100, and 200. These represent ranges starting at multiples of 100: `0–99.99...`, `100–199.99...`, `200–299.99...`. If the business needs display labels, use `CASE` to define the ranges explicitly.

### 6.4. Grouping by CASE

Example classifying order values:

~~~sql
SELECT
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS order_band,
    COUNT(*) AS order_count,
    SUM(quantity * unit_price) AS total_revenue
FROM sales
GROUP BY
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END
ORDER BY order_band;
~~~

Rows are placed into `LOW`, `MEDIUM`, or `HIGH` groups according to the expression. In Oracle 19c, to group by a select-list alias, repeat the expression or use an inline view/CTE as follows:

~~~sql
WITH classified_sales AS (
    SELECT
        CASE
            WHEN quantity * unit_price < 100 THEN 'LOW'
            WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
            ELSE 'HIGH'
        END AS order_band,
        quantity * unit_price AS line_amount
    FROM sales
)
SELECT
    order_band,
    COUNT(*) AS order_count,
    SUM(line_amount) AS total_revenue
FROM classified_sales
GROUP BY order_band
ORDER BY order_band;
~~~

A CTE lets you define the classification logic once and reuse it in the outer query, reducing the risk of writing a long expression twice inconsistently.

### 6.5. Grouping by month/quarter/year

If `SOLD_AT` is a `DATE`, group by month:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

`TRUNC(sold_at, 'MM')` truncates every date in the same month to the first day of that month at 00:00:00. Using that DATE value as the grouping key is usually clearer than grouping by a formatted string.

Displaying a `YYYY-MM` label:

~~~sql
SELECT
    TO_CHAR(TRUNC(sold_at, 'MM'), 'YYYY-MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY TRUNC(sold_at, 'MM');
~~~

Grouping by quarter:

~~~sql
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    TO_CHAR(sold_at, 'Q') AS sale_quarter,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    TO_CHAR(sold_at, 'Q')
ORDER BY sale_year, sale_quarter;
~~~

Or use a quarter-start expression matching your data type and business logic. Note that `TO_CHAR` produces strings; if a format includes month/day names, the output may depend on `NLS_DATE_LANGUAGE`. For grouping and chronological sorting, prefer DATE/TIMESTAMP keys such as `TRUNC(sold_at, 'MM')`.

### 6.6. Grouping by arithmetic/extracted components

~~~sql
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    EXTRACT(MONTH FROM sold_at) AS sale_month,
    COUNT(*) AS sale_rows
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    EXTRACT(MONTH FROM sold_at)
ORDER BY sale_year, sale_month;
~~~

Here the composite grouping key consists of year and month. Use both to distinguish January 2025 from January 2026; grouping only by `EXTRACT(MONTH...)` would merge January across all years.

## 7. Composite grouping keys combined with expressions

You can combine plain columns and expressions to define groups:

~~~sql
SELECT
    region,
    channel,
    TRUNC(sold_at, 'MM') AS sale_month,
    UPPER(product) AS product_key,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY
    region,
    channel,
    TRUNC(sold_at, 'MM'),
    UPPER(product)
ORDER BY
    region,
    channel,
    sale_month,
    product_key;
~~~

A group is defined by **four components simultaneously**:

1. Region.
2. Sales channel.
3. Transaction month.
4. Product name converted to uppercase.

Two rows belong to the same group only if all four grouping expressions evaluate to equal values under comparison rules. If even one component differs, they fall into different groups.

### 7.1. Grouping by year and month instead of a YYYYMM string

Two approaches:

~~~sql
-- Approach 1: two separate numeric keys.
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    EXTRACT(MONTH FROM sold_at) AS sale_month,
    COUNT(*) AS row_count
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    EXTRACT(MONTH FROM sold_at);

-- Approach 2: one DATE key representing the start of the month.
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    COUNT(*) AS row_count
FROM sales
GROUP BY TRUNC(sold_at, 'MM');
~~~

Both approaches represent monthly grouping. Using the month-start DATE is convenient for range filtering or joining to a calendar dimension; the two-key approach suits reports needing separate year and month columns.

### 7.2. Do not add unnecessarily granular keys

Suppose the goal is revenue by region and month:

~~~sql
SELECT region, TRUNC(sold_at, 'MM') AS sale_month,
       SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, TRUNC(sold_at, 'MM');
~~~

If you add `SALE_ID` to `GROUP BY`, each transaction becomes its own group:

~~~sql
-- No longer a revenue report by region/month:
SELECT region, TRUNC(sold_at, 'MM'), sale_id,
       SUM(quantity * unit_price)
FROM sales
GROUP BY region, TRUNC(sold_at, 'MM'), sale_id;
~~~

Ask yourself: **what entity does one result row represent?** Does each row represent a region, a region/channel pair, a month, or a transaction? The answer determines which grouping keys belong there.

## 8. Conditions and rules for NULL

### 8.1. NULLs are placed into a single group

In `GROUP BY`, NULL values of a grouping key are treated as belonging to the same group:

~~~sql
SELECT channel, COUNT(*) AS row_count
FROM sales
GROUP BY channel;
~~~

If 10 rows have `CHANNEL IS NULL`, the result contains one NULL group with `ROW_COUNT=10`. This differs from `channel = NULL` in `WHERE`; that comparison never returns TRUE.

To filter for the NULL group:

~~~sql
SELECT channel, COUNT(*) AS row_count
FROM sales
WHERE channel IS NULL
GROUP BY channel;
~~~

Or keep all groups and display a label:

~~~sql
SELECT
    NVL(channel, '(not assigned)') AS channel_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY NVL(channel, '(not assigned)');
~~~

### 8.2. NULL in aggregate functions

`COUNT(*)` counts rows even when all columns are NULL. `COUNT(column)` ignores NULLs in that column. `SUM(column)` and `AVG(column)` also ignore NULL values; if there are no numeric values, the result is NULL.

Example:

~~~sql
SELECT
    region,
    COUNT(*) AS all_sales,
    COUNT(discount_pct) AS rows_with_discount,
    AVG(discount_pct) AS average_discount
FROM sales
GROUP BY region;
~~~

If a region has no `DISCOUNT_PCT` values at all, `ROWS_WITH_DISCOUNT` is 0 and `AVERAGE_DISCOUNT` is NULL. This can mean "no discount data recorded," not necessarily "average discount equals 0%."

### 8.3. NVL/COALESCE can change grouping keys

~~~sql
SELECT
    NVL(region, 'UNKNOWN') AS region_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY NVL(region, 'UNKNOWN');
~~~

Every NULL is mapped to the string `'UNKNOWN'`. If the data also has a real region named `'UNKNOWN'`, both types of rows will be merged into one group. To distinguish them, keep the original column in the group and apply the label at an outer layer, or include a flag indicating a missing value.

## 9. HAVING with multiple keys and multiple aggregate functions

You can filter groups based on multiple criteria:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    COUNT(DISTINCT product) AS product_count,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region, channel
HAVING COUNT(*) >= 2
   AND SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

A group appears only if it has at least two paid rows and reaches the revenue threshold of 500. Conditions in `HAVING` are evaluated **per group**, not per individual row.

### 9.1. HAVING can reference grouping expressions

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
HAVING TRUNC(sold_at, 'MM') >= DATE '2026-01-01';
~~~

The condition retains groups from January 2026 onward. If you only need to filter source rows from that date, you can use `WHERE sold_at >= DATE '2026-01-01'` before grouping to reduce the rows to aggregate. Both approaches achieve the same goal when the boundary is aligned, but `HAVING` can also filter on aggregated results that `WHERE` cannot access.

### 9.2. HAVING and aliases

For Oracle 19c compatibility, do not rely on an aggregate function's select-list alias inside `HAVING` of the same query block:

~~~sql
-- Do not use the alias pattern in HAVING on Oracle 19c:
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING revenue > 1000;
~~~

Write:

~~~sql
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING SUM(quantity * unit_price) > 1000;
~~~

Or wrap the query:

~~~sql
WITH revenue_by_region AS (
    SELECT region, SUM(quantity * unit_price) AS revenue
    FROM sales
    GROUP BY region
)
SELECT region, revenue
FROM revenue_by_region
WHERE revenue > 1000;
~~~

In the outer query, `REVENUE` is a regular input column of the CTE, so using `WHERE` is appropriate. An alias is not a global variable available to every clause in the query block.

## 10. Conditional aggregation using CASE

You do not need to run separate queries for each status. You can compute multiple metrics within the same group:

~~~sql
SELECT
    region,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_rows,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_rows,
    SUM(CASE
            WHEN status = 'PAID'
            THEN quantity * unit_price
            ELSE 0
        END) AS paid_revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Each input row contributes only to the matching aggregated column according to the `CASE` condition. This technique is **conditional aggregation**, useful for reports with multiple metrics along the same grouping dimensions.

If you use `SUM(CASE WHEN ... THEN amount END)` without `ELSE 0`, rows not matching the condition return NULL and `SUM` ignores them. If no row in the group matches, the sum can be NULL. Add `ELSE 0` if you want to represent "no revenue" as 0.

### 10.1. Conditional counting

~~~sql
SELECT
    region,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_count
FROM sales
GROUP BY region;
~~~

`COUNT(expression)` counts only when expression is non-NULL. This is another way to count qualifying rows.

### 10.2. Aggregating across multiple groups and multiple conditions

~~~sql
SELECT
    region,
    channel,
    SUM(CASE WHEN status = 'PAID'
             THEN quantity * unit_price ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'PENDING'
             THEN quantity * unit_price ELSE 0 END) AS pending_value
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

The grouping key remains the region/channel pair; the CASE expressions produce distinct metrics within each group.

## 11. DISTINCT inside aggregate functions and key combinations

### 11.1. COUNT(DISTINCT ...)

~~~sql
SELECT
    region,
    COUNT(DISTINCT product) AS unique_products,
    COUNT(*) AS sale_rows
FROM sales
GROUP BY region;
~~~

`COUNT(DISTINCT product)` counts the number of distinct product values in each region, ignoring NULL. It does not alter the grouping key; `REGION` remains the grouping dimension.

### 11.2. Counting distinct multi-column combinations

When you want to count the number of distinct (`REGION`, `CHANNEL`) pairs in a dataset, do not concatenate the two columns and run `COUNT(DISTINCT region || channel)`, because collisions, NULL handling, and type conversions can behave unexpectedly.

Use an inline view:

~~~sql
SELECT COUNT(*) AS distinct_region_channel_pairs
FROM (
    SELECT DISTINCT region, channel
    FROM sales
);
~~~

Or if you need combination counts per region, use `GROUP BY region` combined with an appropriate distinct subquery. Using `SELECT DISTINCT col1, col2` keeps each component of the composite key separate.

## 12. Grouping expressions with dates, times, and time zones

### 12.1. DATE and TIMESTAMP

`TRUNC(date_value, 'MM')` is a familiar pattern for grouping by month. If the column is `TIMESTAMP`, Oracle may require explicit conversion or an appropriate timestamp expression. Check column data types and do not rely on implicit conversion in precision-sensitive systems.

With `TIMESTAMP WITH TIME ZONE` columns, before grouping by day/month, determine **which time zone's calendar day** you want:

~~~sql
SELECT
    TRUNC(CAST(event_time AT TIME ZONE '+07:00' AS DATE)) AS local_day,
    COUNT(*) AS event_count
FROM app_events
GROUP BY TRUNC(CAST(event_time AT TIME ZONE '+07:00' AS DATE))
ORDER BY local_day;
~~~

Meaning: convert the instant to its `+07:00` offset representation, then extract the date part for grouping. If the business uses a time zone region with DST, replace the fixed offset with the appropriate region name and test against specific transition dates. Do not group by server date if the report requires the user's local day in another region.

### 12.2. Do not group by NLS-dependent date strings

~~~sql
-- Can depend on NLS_DATE_LANGUAGE/format:
SELECT TO_CHAR(sold_at, 'MON') AS month_name,
       SUM(quantity * unit_price)
FROM sales
GROUP BY TO_CHAR(sold_at, 'MON');
~~~

The query above also merges months with the same name across **all years** and can return month names in the session's language. If you want monthly revenue chronologically over time:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

Format the display label after establishing the DATE key:

~~~sql
SELECT
    TO_CHAR(month_start, 'YYYY-MM') AS month_label,
    revenue
FROM (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM sales
    GROUP BY TRUNC(sold_at, 'MM')
)
ORDER BY month_start;
~~~

## 13. GROUP BY with subqueries and CTEs

CTEs help separate calculation steps, name grouping expressions, and avoid duplicating logic:

~~~sql
WITH normalized_sales AS (
    SELECT
        UPPER(TRIM(region)) AS region_key,
        UPPER(TRIM(channel)) AS channel_key,
        TRUNC(sold_at, 'MM') AS month_key,
        quantity * unit_price AS amount
    FROM sales
    WHERE status = 'PAID'
),
monthly_summary AS (
    SELECT
        region_key,
        channel_key,
        month_key,
        COUNT(*) AS sale_rows,
        SUM(amount) AS revenue
    FROM normalized_sales
    GROUP BY region_key, channel_key, month_key
)
SELECT
    region_key,
    channel_key,
    month_key,
    sale_rows,
    revenue
FROM monthly_summary
WHERE revenue >= 500
ORDER BY month_key, region_key, channel_key;
~~~

Steps:

1. `NORMALIZED_SALES` filters by status and creates normalized keys.
2. `MONTHLY_SUMMARY` groups by the three keys and computes metrics.
3. The outer query filters aggregated results with `WHERE` because `REVENUE` is already a column of the CTE.

CTEs are a readable way to structure SQL; do not assume every CTE is always materialized into a temporary table. The Oracle optimizer may inline or transform the query depending on the plan.

## 14. Limitations and considerations when choosing grouping expressions

### 14.1. Unsupported data types and expressions

Not every data type can be used as a `GROUP BY` key. LOB types such as `CLOB`/`BLOB` cannot be grouped directly in the normal way; certain complex types or expressions have specific rules. If you need to classify LOB content, design an appropriate surrogate key (such as metadata, an identifier, or a hash with collision handling), rather than taking a prefix of a CLOB and assuming it uniquely represents the entire content.

Grouping expressions must also evaluate deterministically from input data. Do not introduce an unnecessary transformation into `GROUP BY` if it loses distinguishing information or produces incorrect groups.

### 14.2. Numeric precision and rounding

Grouping by a numeric expression can differ from grouping by the original value:

~~~sql
SELECT ROUND(unit_price, 0) AS rounded_price,
       COUNT(*) AS row_count
FROM sales
GROUP BY ROUND(unit_price, 0);
~~~

Values 10.2 and 10.4 both round to 10 and are grouped together. If the business wants interval-based grouping, use an explicit bucket expression like `FLOOR(unit_price / 10)` rather than arbitrary rounding.

For currency, do not round at the row level before summing if business rules require summing exact values first and rounding afterward (or vice versa). Operation order can change the result.

### 14.3. String expressions and collation

Grouping by `UPPER(name)` can collapse letter cases, but does not automatically resolve all diacritic differences, Unicode normalization, or collation rules. If an application stores multilingual data, standardize normalization before storage or use an appropriate collation. Do not assume two strings that look alike on screen are always considered equal by Oracle.

### 14.4. Do not use GROUP BY to mask bad data

If a join duplicates rows, adding `GROUP BY`/`SUM(DISTINCT amount)` to make totals "look right" only hides the join bug. Check cardinality and key relationships first:

- One customer having many orders is a 1-to-n relationship.
- One order having many detail lines is another 1-to-n relationship.
- Joining two independent detail tables can create a Cartesian-like row multiplication if join conditions are missing.

`SUM(DISTINCT amount)` only removes duplicate amount values and **does not fix row multiplication from a join**; two different orders with the same amount would be erroneously collapsed when using DISTINCT. Always identify the true grain (level of detail) of the data before aggregating.

## 15. Common errors

| Error/Symptom | Cause | Resolution |
| --- | --- | --- |
| `ORA-00979: not a GROUP BY expression` | Non-aggregated column/expression in SELECT does not match grouping keys | Determine result grain; add the right grouping expression or aggregate the column |
| `ORA-00937: not a single-group group function` | Mixing aggregates with plain columns without an appropriate GROUP BY | Add GROUP BY for the dimensions to display |
| `ORA-00904` when using an alias in GROUP BY | Alias is not resolved under the query block syntax/version | Repeat the expression or wrap in a CTE/inline view |
| Too many grouped rows | Added an overly granular key, such as transaction ID | Identify what entity a single result row should represent |
| Missing NULL group | Filtered out NULL in WHERE or concatenated strings causing NULL loss | Check conditions and grouping expressions; use IS NULL when filtering |
| Abnormally large total revenue | JOIN duplicated source rows | Check grain, join keys, and cardinality before GROUP BY |
| Result order changes | No ORDER BY | Add an explicit ORDER BY |
| Name groups do not merge as expected | Differences in whitespace, letter case, diacritics, or normalization | Normalize intentionally with expressions and test against real data |
| Sum/AVG returns NULL | All values in group are NULL or no valid values exist | Distinguish NULL from 0; use NVL/COALESCE only when appropriate |
| Same-named months merged across years | Grouped only by month name/number without year | Use TRUNC(date,'MM') or group by both YEAR and MONTH |

### 15.1. Troubleshooting ORA-00979

Error example:

~~~sql
SELECT region, channel, product, SUM(quantity)
FROM sales
GROUP BY region, channel;
~~~

Analysis:

1. `REGION` is in GROUP BY.
2. `CHANNEL` is in GROUP BY.
3. `SUM(quantity)` is an aggregate.
4. `PRODUCT` is an ungrouped regular column.

If you want the report broken down by product, add `PRODUCT` to the grouping key:

~~~sql
GROUP BY region, channel, product;
~~~

If product is not needed, remove it from SELECT. Do not use `MAX(product)` just to bypass the error unless the business truly wants the maximum string value according to sort comparison order.

### 15.2. Verify grain before fixing

Write out the statement:

> Each result row represents one ________.

For example:

- One region.
- One region and one channel.
- One region, channel, and month.
- One customer in one month.

Then check every non-aggregated column in SELECT against this description. This is an effective way to avoid adding grouping keys by mistake.

## 16. Comprehensive hands-on lab

This section creates a lab table with multiple regions, channels, products, months, and NULL values. Run it in a dedicated schema; if the table already exists, rename the lab table instead of dropping a table whose ownership is unclear.

### Step 1 — Create the table

~~~sql
CREATE TABLE group_by_lab (
    sale_id     NUMBER PRIMARY KEY,
    region      VARCHAR2(20 CHAR),
    channel     VARCHAR2(20 CHAR),
    product     VARCHAR2(30 CHAR),
    sold_at     DATE NOT NULL,
    quantity    NUMBER(8,2) NOT NULL,
    unit_price  NUMBER(10,2) NOT NULL,
    status      VARCHAR2(12 CHAR) NOT NULL
);
~~~

### Step 2 — Insert sample data

~~~sql
INSERT INTO group_by_lab VALUES
    (1, 'North', 'Online', 'Laptop', DATE '2026-01-02', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (2, 'North', 'Store', 'Laptop', DATE '2026-01-03', 2, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (3, 'North', 'Online', 'Mouse', DATE '2026-01-05', 3, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (4, 'South', 'Online', 'Laptop', DATE '2026-01-07', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (5, 'South', 'Store', 'Mouse', DATE '2026-01-09', 4, 25, 'PENDING');

INSERT INTO group_by_lab VALUES
    (6, 'South', 'Online', 'Mouse', DATE '2026-01-15', 2, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (7, NULL, 'Online', 'Mouse', DATE '2026-02-02', 1, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (8, 'North', NULL, 'Laptop', DATE '2026-02-05', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (9, 'North', 'Online', 'Keyboard', DATE '2026-02-07', 2, 50, 'PAID');

INSERT INTO group_by_lab VALUES
    (10, 'north', 'ONLINE', 'laptop', DATE '2026-02-10', 1, 1000, 'PAID');

COMMIT;
~~~

The last two rows contain NULL values and casing differences so you can observe grouping behavior.

### Step 3 — Group by a single key

~~~sql
SELECT region, COUNT(*) AS row_count
FROM group_by_lab
GROUP BY region
ORDER BY region;
~~~

Counts rows by region. Rows where `REGION IS NULL` fall into a separate NULL group.

### Step 4 — Group by a composite key

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY region, channel
ORDER BY region, channel;
~~~

Observe the pairs `(North, Online)`, `(North, Store)`, `(North, NULL)`, and `(NULL, Online)`. Each distinct pair forms its own group.

### Step 5 — Filter rows before grouping

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_rows,
    SUM(quantity * unit_price) AS paid_revenue
FROM group_by_lab
WHERE status = 'PAID'
GROUP BY region, channel
ORDER BY region, channel;
~~~

The `PENDING` order is excluded from the aggregates.

### Step 6 — Filter groups with HAVING

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY region
HAVING SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

Only region groups with total revenue of at least 500 are returned.

### Step 7 — Group by month

~~~sql
SELECT
    TO_CHAR(TRUNC(sold_at, 'MM'), 'YYYY-MM') AS sale_month,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY TRUNC(sold_at, 'MM');
~~~

January and February form two separate groups.

### Step 8 — Group by a CASE expression

~~~sql
SELECT
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS amount_band,
    COUNT(*) AS sale_rows
FROM group_by_lab
GROUP BY
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END
ORDER BY amount_band;
~~~

Transactions are grouped by row-level amount band.

### Step 9 — Normalize strings before grouping

~~~sql
SELECT
    UPPER(product) AS product_key,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM group_by_lab
GROUP BY UPPER(product)
ORDER BY product_key;
~~~

`Laptop` and `laptop` are grouped into the same `LAPTOP` group; this holds specifically under the normalization rule you intentionally chose.

### Step 10 — Conditional aggregation

~~~sql
SELECT
    region,
    SUM(CASE WHEN status = 'PAID'
             THEN quantity * unit_price ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'PENDING'
             THEN quantity * unit_price ELSE 0 END) AS pending_revenue
FROM group_by_lab
GROUP BY region
ORDER BY region;
~~~

Each region group has two distinct metrics without running two separate queries.

### Step 11 — Clean up the lab table (optional)

~~~sql
-- Only run if you are sure this table is your lab table and the data is no longer needed.
DROP TABLE group_by_lab PURGE;
~~~

`PURGE` bypasses the recycle bin. Skip this step if you want to keep the table for further practice or if the table is outside your lab scope.

## 17. Self-check questions

1. Does `GROUP BY region, channel` group independently by region and by channel, or by each pair of values?
2. If you add `PRODUCT` to the grouping key, how can the number of groups change?
3. Why can `GROUP BY region || channel` accidentally merge two different combinations?
4. In a single group with 5 rows where only 3 emails are non-NULL, what do `COUNT(*)` and `COUNT(email)` return?
5. What does `SUM(amount)` return if every amount in the group is NULL?
6. Why does Oracle disallow selecting an unaggregated `PRODUCT` when only `GROUP BY REGION` is specified?
7. At what filtering stage do `WHERE` and `HAVING` differ?
8. To filter groups with revenue above 1,000, should you use `WHERE` or `HAVING`?
9. How does `GROUP BY TRUNC(sold_at, 'MM')` differ from grouping by `TO_CHAR(sold_at, 'MON')`?
10. When `CHANNEL` is NULL, how are those rows grouped?
11. Why should you avoid `NVL(region, 'UNKNOWN')` if real data might contain a region named UNKNOWN?
12. In Oracle 19c, how can you use an alias for a grouping expression without repeating the expression in GROUP BY?
13. Does `UPPER(product)` guarantee that all Vietnamese strings differing in diacritics are grouped together?
14. Why is `SUM(DISTINCT amount)` not the right fix for a total amount doubled by a JOIN?
15. If a report needs revenue by year and month, why is `GROUP BY EXTRACT(MONTH FROM sold_at)` alone insufficient?

**Answer hints:**

1. By each pair of region/channel values.
2. It can increase or remain the same, never decrease.
3. Because two different pairs can produce the same concatenated string; data can also contain delimiters.
4. 5 and 3.
5. NULL.
6. A single group can contain multiple products; Oracle does not know which value to pick.
7. WHERE filters rows before grouping; HAVING filters groups after aggregation.
8. HAVING.
9. TRUNC creates a month-start DATE key that includes the year; MON only produces a month name and can merge multiple years and depend on NLS.
10. Rows sharing the same key combination with NULL in the channel position go into one group.
11. Because it can merge NULL with a real UNKNOWN value.
12. Use an inline view/CTE so the alias becomes an input column of the outer query.
13. No; UPPER handles letter casing, not comprehensive diacritic stripping/normalization.
14. Because different transactions with the same amount would be erroneously deduplicated; fix the cardinality/join instead.
15. January across multiple years would be merged together without a year key.

## Oracle reference documentation

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `GROUP BY`, `HAVING`, and select-list rules.
- [Oracle Database SQL Language Reference — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): behavior of aggregate functions and NULL handling.
- [Oracle Database SQL Language Reference — COUNT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COUNT.html): `COUNT(*)`, `COUNT(expr)`, and `COUNT(DISTINCT ...)`.
- [Oracle Database SQL Language Reference — GROUPING](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING.html): functions related to advanced grouping extensions.
- [Oracle Database SQL Language Reference — TRUNC (date)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TRUNC-date.html): grouping and normalizing dates by month/year.
