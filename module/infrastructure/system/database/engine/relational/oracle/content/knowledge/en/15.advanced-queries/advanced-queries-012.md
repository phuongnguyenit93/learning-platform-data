# Designing Reporting Queries with Subtotals, Ranking, and Time-Series Data in Oracle

A sales report often has to answer several questions at once: revenue by region, subtotals per region, company-wide grand total, top three best-selling products per month, month-over-month growth, and year-to-date cumulative revenue. Writing each metric as a separate query forces the application to stitch together multiple result sets and risks inconsistent data scopes across numbers. Oracle SQL provides tools to build multi-level reports: `GROUPING SETS`/`ROLLUP`/`CUBE` produce aggregation tiers, analytic functions compute rankings and windowed metrics, and time-series queries define reporting periods and handle periods without transactions.

The key is designing the right **grain** (level of detail) for each step. You must know whether a source row represents an order or a line item; whether an aggregated row represents a month, a region, or a month/region pair; and whether a ranked row represents a product within a month or a product across the entire report. Only when the grain is clear can you combine subtotals, ranking, and time series without double-counting or ranking subtotal rows by mistake.

This lesson belongs to the **Advanced Queries** section of Database Engine Relational Oracle. Examples use Oracle Database 19c syntax, focusing on sales reporting while remaining applicable to finance, inventory, operations, and event analytics.

After this lesson, you will be able to:

- Design multi-level reports using `GROUPING SETS`, `ROLLUP`, and `CUBE`.
- Distinguish detail rows, subtotals, and grand totals using `GROUPING`/`GROUPING_ID`.
- Use `ROW_NUMBER`, `RANK`, and `DENSE_RANK` to rank and extract Top-N per group.
- Combine monthly aggregation with ranking without letting subtotal rows enter rankings.
- Generate continuous month series, fill in zero-transaction periods, and compute running totals/moving averages.
- Compare current periods with prior periods using `LAG`/`LEAD`.
- Handle time boundaries, `DATE`/`TIMESTAMP` types, and time zones per business calendars.
- Read execution plans and evaluate indexes, cardinality, and report costs.

> **Example scope:** Practice tables carry the `_LAB` suffix and should be created only in a lab schema/PDB you manage. Queries assume Oracle Database 19c. If using another release, verify corresponding syntax and features. Never run DDL or heavy data-scanning reports on a production schema without an operational plan.

## 1. Starting from the Report Grain

Before writing SQL, answer: **what does each output row represent?**

| Grain | One row represents | Typical identifying key |
| --- | --- | --- |
| Transaction data | An order or an order line item | `SALE_ID` or `ORDER_ID, LINE_ID` |
| Month/region summary | One region's revenue in one month | `MONTH_START, REGION` |
| Month/region/product summary | One product's revenue in one region in one month | `MONTH_START, REGION, PRODUCT_ID` |
| Product ranking | A product's rank within a reporting group | `MONTH_START, REGION, PRODUCT_ID` plus rank |
| Region subtotal | Total revenue across all products in a region/period | `MONTH_START, REGION` |
| Period grand total | Total revenue across all regions/products in a period | `MONTH_START` or a single grand total row |

Aggregations and analytic functions operate at different grains:

~~~text
TRANSACTIONS / LINE ITEMS
        |
        | GROUP BY month, region, product
        v
DETAIL SUMMARY: 1 row / month / region / product
        |
        +------------------------------+
        |                              |
        | analytic ranking             | GROUPING SETS / ROLLUP
        v                              v
PRODUCT RANKING                 SUBTOTALS / GRAND TOTAL
        |                              |
        +---------------+--------------+
                        v
                 REPORT DISPLAY
~~~

Never apply ranking directly to a transactions table when the requirement is ranking products by monthly revenue: first sum each product's revenue for the month, then rank those sums afterward.

## 2. Preparing Practice Data

### 2.1. Creating the lab table

The following table stores one row per product transaction:

~~~sql
CREATE TABLE report_sales_lab (
    sale_id      NUMBER PRIMARY KEY,
    sold_at      DATE NOT NULL,
    region       VARCHAR2(20 CHAR) NOT NULL,
    product_id   NUMBER NOT NULL,
    product_name VARCHAR2(40 CHAR) NOT NULL,
    channel      VARCHAR2(15 CHAR) NOT NULL,
    quantity     NUMBER(8,2) NOT NULL,
    unit_price   NUMBER(10,2) NOT NULL,
    status       VARCHAR2(12 CHAR) NOT NULL
);
~~~

In this example, line revenue equals `quantity` multiplied by `unit_price`. This is a simplified model for learning SQL; production systems may need discounts, taxes, currencies, returns, and specific revenue recognition rules.

### 2.2. Inserting data across multiple months and regions

~~~sql
INSERT ALL
  INTO report_sales_lab VALUES
    (1, DATE '2026-01-03', 'North', 101, 'Laptop', 'Online', 2, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (2, DATE '2026-01-05', 'North', 102, 'Mouse', 'Store', 10, 25, 'PAID')
  INTO report_sales_lab VALUES
    (3, DATE '2026-01-12', 'North', 103, 'Keyboard', 'Online', 5, 50, 'PAID')
  INTO report_sales_lab VALUES
    (4, DATE '2026-01-20', 'South', 101, 'Laptop', 'Store', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (5, DATE '2026-01-24', 'South', 102, 'Mouse', 'Online', 8, 25, 'PAID')
  INTO report_sales_lab VALUES
    (6, DATE '2026-02-02', 'North', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (7, DATE '2026-02-08', 'North', 102, 'Mouse', 'Store', 20, 25, 'PAID')
  INTO report_sales_lab VALUES
    (8, DATE '2026-02-18', 'South', 103, 'Keyboard', 'Online', 10, 50, 'PAID')
  INTO report_sales_lab VALUES
    (9, DATE '2026-03-04', 'North', 103, 'Keyboard', 'Store', 8, 50, 'PAID')
  INTO report_sales_lab VALUES
    (10, DATE '2026-03-09', 'South', 101, 'Laptop', 'Online', 2, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (11, DATE '2026-03-16', 'South', 102, 'Mouse', 'Store', 12, 25, 'PAID')
  INTO report_sales_lab VALUES
    (12, DATE '2026-03-25', 'North', 101, 'Laptop', 'Store', 1, 1000, 'PENDING')
  INTO report_sales_lab VALUES
    (13, DATE '2026-04-02', 'North', 102, 'Mouse', 'Online', 15, 25, 'PAID')
  INTO report_sales_lab VALUES
    (14, DATE '2026-04-11', 'South', 103, 'Keyboard', 'Store', 12, 50, 'PAID')
  INTO report_sales_lab VALUES
    (15, DATE '2026-04-19', 'South', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (16, DATE '2026-06-06', 'North', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
SELECT 1 FROM dual;

COMMIT;
~~~

May has no transactions. This dataset highlights the difference between "a month with no row in the table" and "a month with revenue equal to 0". A PENDING transaction is also included to demonstrate status filtering prior to aggregation.

Inspect the source:

~~~sql
SELECT sale_id, sold_at, region, product_name,
       quantity, unit_price, status
FROM report_sales_lab
ORDER BY sold_at, sale_id;
~~~

### 2.3. Defining time range and status

In the PAID reporting examples, use a half-open range:

~~~sql
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
~~~

Greater-than-or-equal-to the period start and strictly-less-than the next period start covers every instant in the final month, including fractional seconds if a TIMESTAMP column is substituted in corresponding examples. Avoid BETWEEN with a midnight endpoint on the last day of the period, which can miss transactions occurring later that day.

## 3. Subtotal Reports Using ROLLUP

### 3.1. GROUP BY ROLLUP creates aggregation tiers

Suppose you need revenue by region and product, along with a subtotal per region and a company-wide grand total:

~~~sql
SELECT
    region,
    product_name,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY region, product_name;
~~~

With `ROLLUP(region, product_name)`, Oracle produces grouping sets equivalent to:

~~~sql
GROUPING SETS (
    (region, product_name),
    (region),
    ()
)
~~~

The output contains:

1. Detail revenue for each region/product pair.
2. Revenue subtotal for each region (`product_name` rolled up).
3. Grand total (both `region` and `product_name` rolled up).

ROLLUP is ideal when aggregation tiers follow a hierarchy: detail → parent subtotal → grand total.

### 3.2. Column order in ROLLUP matters greatly

~~~sql
GROUP BY ROLLUP(region, product_name)
~~~

creates detail `(region, product_name)`, subtotal `(region)`, and grand total `()`.

Whereas:

~~~sql
GROUP BY ROLLUP(product_name, region)
~~~

creates detail `(product_name, region)`, subtotal `(product_name)`, and grand total. Subtotals are now by product rather than by region.

ROLLUP does not generate every subset combination. Argument order dictates the sequence of generated aggregation tiers.

### 3.3. Identifying subtotal rows with GROUPING

In source data, `PRODUCT_NAME` might legitimately be NULL. When ROLLUP produces a subtotal, Oracle also displays NULL in the rolled-up column. Therefore you cannot look at NULL alone and conclude a row is a subtotal.

Use `GROUPING(expression)`:

~~~sql
SELECT
    region,
    product_name,
    GROUPING(region) AS g_region,
    GROUPING(product_name) AS g_product,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY GROUPING(region), region,
         GROUPING(product_name), product_name;
~~~

`GROUPING(expr)` returns:

- `0`: the expression retains its value from the detail group (even when the source value is truly NULL).
- `1`: the expression was excluded from the grouping set and NULL was generated to represent an aggregated tier.

This lets you distinguish genuine NULLs from subtotal NULLs.

### 3.4. Labeling subtotals and grand totals

~~~sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(product_name) = 1 THEN 'SUBTOTAL / ALL PRODUCTS'
        ELSE NVL(product_name, '(unknown product)')
    END AS product_label,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY GROUPING(region), region,
         GROUPING(product_name), product_name;
~~~

On the grand total row, `GROUPING(region)=1`, so the region label is `ALL REGIONS`. On a regional subtotal row, `GROUPING(product_name)=1`; on a detail row with an actually NULL product, `GROUPING(product_name)=0` and the label becomes `(unknown product)`.

Never use `NVL(product_name, 'TOTAL')` alone to detect subtotals, because it conflates genuine NULLs with aggregated NULLs.

## 4. GROUPING_ID: Encoding Aggregation Levels

### 4.1. GROUPING_ID for multiple columns

With `ROLLUP(region, product_name)`, you can write:

~~~sql
SELECT
    region,
    product_name,
    GROUPING_ID(region, product_name) AS grouping_level,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY grouping_level, region, product_name;
~~~

For argument order `GROUPING_ID(region, product_name)`, the last expression's bit is the least significant bit:

| Grouping set | GROUPING(region) | GROUPING(product_name) | GROUPING_ID |
| --- | ---: | ---: | ---: |
| `(region, product_name)` | 0 | 0 | 0 |
| `(region)` | 0 | 1 | 1 |
| `()` | 1 | 1 | 3 |

The `GROUPING_ID` value is a convenient code for distinguishing detail/subtotal/grand total rows and ordering report tiers. Changing argument order changes the bit meanings; keep the same order in both expressions and report documentation.

### 4.2. Using GROUPING_ID to filter one tier

For example, keeping only regional subtotals:

~~~sql
SELECT region, SUM(quantity * unit_price) AS region_revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
HAVING GROUPING_ID(region, product_name) = 1
ORDER BY region;
~~~

In practice, if only regional totals are needed, a simple `GROUP BY region` is cleaner. `GROUPING_ID` shines when a single query produces multiple tiers and you need to identify or filter a specific tier.

## 5. GROUPING SETS: Selecting Exact Reporting Tiers

ROLLUP creates a hierarchical prefix chain. When a report needs specific individual combinations, use `GROUPING SETS`:

~~~sql
SELECT
    region,
    channel,
    product_name,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel, product_name) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (region, channel, product_name),
    (region, channel),
    (region),
    ()
)
ORDER BY grouping_level, region, channel, product_name;
~~~

The query produces region/channel/product details, region/channel subtotals, region subtotals, and the grand total. Unlike ROLLUP, `GROUPING SETS` lets you choose exact tiers without forcing a prefix chain.

### 5.1. One query for multiple summary breakdowns

For example, needing revenue by region, by channel, by region/channel, and grand total:

~~~sql
SELECT
    region,
    channel,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    (channel),
    ()
);
~~~

No simple ROLLUP generates these exact four tiers without emitting extra unwanted tiers; `GROUPING SETS` states the required set precisely.

### 5.2. Standard GROUP BY vs. GROUPING SETS

Writing four separate queries combined with `UNION ALL` repeats the same filters and aggregations. `GROUPING SETS` is usually easier to maintain for these aggregation tiers. However, do not claim a single `GROUPING SETS` query is always faster than multiple `UNION ALL` queries; the optimizer and data determine the plan, and `UNION ALL` may be necessary when branches have different logic.

## 6. CUBE: Aggregating All Dimension Combinations

### 6.1. CUBE creates an aggregation grid

~~~sql
SELECT
    region,
    channel,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY CUBE(region, channel);
~~~

With two dimensions, CUBE equals `GROUPING SETS` of `(region, channel)`, `(region)`, `(channel)`, and `()`. It produces revenue for each region/channel pair, per region, per channel, and overall total.

### 6.2. Number of grouping sets grows exponentially

With n expressions in CUBE, the theoretical number of grouping sets is 2^n:

| Number of dimensions | Number of grouping sets |
| ---: | ---: |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 5 | 32 |
| 8 | 256 |

CUBE is useful for multi-dimensional analysis, but can generate huge output volumes. Use it only when a report genuinely requires all combinations. If only a few tiers are needed, `GROUPING SETS` is usually more exact and avoids superfluous tiers.

### 6.3. ROLLUP, CUBE, and GROUPING SETS

| Syntax | Goal | Resulting grouping sets |
| --- | --- | --- |
| `ROLLUP(a,b,c)` | Detail, prefix subtotals, grand total | `(a,b,c)`, `(a,b)`, `(a)`, `()` |
| `CUBE(a,b)` | All dimension combinations | `(a,b)`, `(a)`, `(b)`, `()` |
| `GROUPING SETS((a,b),(a),())` | Author-chosen tiers | Exact listed sets |

For a hierarchical region → channel → product report, ROLLUP is natural. For analyzing every region/channel combination, CUBE fits. For a predefined set of reporting metrics, `GROUPING SETS` is usually clearest.

## 7. Ranking with Analytic Functions

### 7.1. Three commonly used ranking functions

Suppose product revenue in a month is:

| Product | Revenue |
| --- | ---: |
| Laptop | 5,000 |
| Mouse | 2,000 |
| Keyboard | 2,000 |
| Monitor | 1,000 |

| Function | Rank result | When to use |
| --- | --- | --- |
| `ROW_NUMBER()` | 1, 2, 3, 4 | Need unique sequential numbers and exact N rows |
| `RANK()` | 1, 2, 2, 4 | Ties share a rank; subsequent positions have gaps |
| `DENSE_RANK()` | 1, 2, 2, 3 | Ties share a rank; subsequent positions have no gaps |

~~~sql
SELECT
    product_name,
    revenue,
    ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_rank
FROM (
    SELECT product_name,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY product_name
);
~~~

### 7.2. ORDER BY inside the analytic function determines the rank

`ORDER BY revenue DESC` places higher revenue first. Adding a unique column to `ROW_NUMBER`'s analytic ordering makes row ordering deterministic when revenue ties. For `RANK`/`DENSE_RANK`, however, adding `product_name` means products with equal revenue but different names are no longer tied across the full sort tuple.

If the goal is preserving ties on revenue, put only `ORDER BY revenue DESC` inside `RANK`/`DENSE_RANK`, and use the outer `ORDER BY` for deterministic display sorting:

~~~sql
SELECT product_name, revenue, revenue_rank
FROM (
    SELECT
        product_name,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM (
        SELECT product_name,
               SUM(quantity * unit_price) AS revenue
        FROM report_sales_lab
        WHERE status = 'PAID'
        GROUP BY product_name
    )
)
ORDER BY revenue DESC, product_name;
~~~

### 7.3. PARTITION BY: ranking independently within each group

Requirement: rank products within each region:

~~~sql
WITH product_revenue AS (
    SELECT
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
)
SELECT
    region,
    product_name,
    revenue,
    RANK() OVER (
        PARTITION BY region
        ORDER BY revenue DESC
    ) AS region_rank
FROM product_revenue
ORDER BY region, region_rank, product_name;
~~~

`PARTITION BY region` splits the aggregated set into independent partitions. Ranks restart at 1 in each region. Without `PARTITION BY`, all products across all regions compete in one global ranking.

### 7.4. Top-N per group

Top 2 products by revenue in each region, capped at two rows per region:

~~~sql
WITH product_revenue AS (
    SELECT region, product_id, product_name,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
),
ranked AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY revenue DESC, product_id
           ) AS rn
    FROM product_revenue p
)
SELECT region, product_id, product_name, revenue
FROM ranked
WHERE rn <= 2
ORDER BY region, rn;
~~~

`ROW_NUMBER` guarantees at most two rows per region; `product_id` is the tie-breaker assumed unique within the group. To include all products tied at second place, use `RANK`:

~~~sql
RANK() OVER (
    PARTITION BY region
    ORDER BY revenue DESC
) AS revenue_rank
~~~

and filter `revenue_rank <= 2`. Output may contain more than two products per region when ties occur.

### 7.5. Top-N by month and region

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked AS (
    SELECT
        m.*,
        DENSE_RANK() OVER (
            PARTITION BY month_start, region
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM monthly_product m
)
SELECT month_start, region, product_name, revenue, revenue_rank
FROM ranked
WHERE revenue_rank <= 3
ORDER BY month_start, region, revenue_rank, product_name;
~~~

Each partition is a month/region pair. Ranking happens only after revenue is aggregated at the month/region/product grain.

## 8. Combining Subtotals and Ranking at the Right Level

A report may need top products per region, regional revenue subtotals, and a grand total. Never feed `ROLLUP` rows directly into ranking so that subtotals compete against products. Instead, build detail + ranking separately, build subtotals separately, and combine them:

~~~sql
WITH detail AS (
    SELECT
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
),
ranked_detail AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM detail d
),
subtotals AS (
    SELECT
        region,
        CAST(NULL AS NUMBER) AS product_id,
        CAST(NULL AS VARCHAR2(40)) AS product_name,
        SUM(quantity * unit_price) AS revenue,
        CAST(NULL AS NUMBER) AS rn,
        GROUPING_ID(region) AS grouping_level
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY ROLLUP(region)
)
SELECT
    region,
    product_name,
    revenue,
    rn AS product_rank,
    0 AS grouping_level,
    'TOP PRODUCT' AS row_type
FROM ranked_detail
WHERE rn <= 3
UNION ALL
SELECT
    region,
    product_name,
    revenue,
    rn,
    grouping_level,
    CASE WHEN grouping_level = 1
         THEN 'GRAND TOTAL'
         ELSE 'REGION SUBTOTAL'
    END
FROM subtotals
ORDER BY grouping_level, region, product_rank;
~~~

This example demonstrates separating the two logical levels; in production reports, align column data types across `UNION ALL`, add a month column if reporting monthly, and use suitable labels/ordering. `UNION ALL` preserves all rows, even if a subtotal happens to match a detail row's value—which is normally desired in hierarchical reports. Using `UNION` forces deduplication and can drop or alter report rows.

Another option is using `GROUPING SETS` in the same query, then applying analytics solely to detail rows in a separate query block. The rule remains: **ranking must run at the product grain**, and subtotals must be identified separately.

## 9. Monthly Reports: Grouping Time Properly

### 9.1. Grouping by month with TRUNC

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    SUM(quantity * unit_price) AS revenue,
    COUNT(*) AS sale_count
FROM report_sales_lab
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

`TRUNC(date_value, 'MM')` maps dates to the first day of the month. This provides a clean `DATE` key for sorting, joining calendars, and computing month intervals.

Avoid grouping only by `TO_CHAR(sold_at, 'MON')`: January across multiple years collapses into one bucket, and month names depend on NLS language. For display labels, format the `DATE` key after grouping.

### 9.2. Filtering time with range predicates

Prefer:

~~~sql
WHERE sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
~~~

Be cautious with:

~~~sql
WHERE TO_CHAR(sold_at, 'YYYY-MM') = '2026-01'
~~~

Wrapping the column in a function prevents ordinary indexes on `SOLD_AT` from being used directly, unless a matching function-based index exists and the optimizer chooses it. Range predicates also express time boundaries unambiguously without string-format dependencies.

### 9.3. Grouping by month and region

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY TRUNC(sold_at, 'MM'), region
ORDER BY month_start, region;
~~~

The grouping key is the month/region pair. Each output row represents one region's revenue in one month.

## 10. Continuous Time Series and Zero-Transaction Months

### 10.1. GROUP BY returns only periods with data

In the lab dataset, May has no transactions, so the monthly `GROUP BY` query above emits no May row. This follows standard `GROUP BY` semantics: no source rows means no group.

Trend reports, however, usually want all months January through June, with May showing revenue 0. We need to generate a **calendar series** and `LEFT JOIN` aggregated metrics onto it.

### 10.2. Generating a month series with CONNECT BY

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue,
        COUNT(*) AS sale_count
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    m.month_start,
    NVL(s.revenue, 0) AS revenue,
    NVL(s.sale_count, 0) AS sale_count
FROM months m
LEFT JOIN monthly_sales s
    ON s.month_start = m.month_start
ORDER BY m.month_start;
~~~

The output contains all six months; May receives revenue 0 and sale count 0. The month series is the preserved side, and aggregated metrics are joined onto it.

### 10.3. Generating a dynamic number of months

If input parameters are start month and end month (first of month, start inclusive, end exclusive), compute the period count:

~~~sql
WITH params AS (
    SELECT DATE '2026-01-01' AS start_month,
           DATE '2026-07-01' AS end_month
    FROM dual
),
months AS (
    SELECT ADD_MONTHS(p.start_month, LEVEL - 1) AS month_start
    FROM params p
    CONNECT BY LEVEL <= MONTHS_BETWEEN(p.end_month, p.start_month)
)
SELECT month_start
FROM months
ORDER BY month_start;
~~~

This template assumes `start_month` and `end_month` are both first-of-month dates, `end_month` is greater than or equal to `start_month`, and the month span is an integer. Applications should validate parameters before sending SQL.

### 10.4. Calendar dimension in production systems

For multi-year reports, business days, fiscal periods, holidays, or custom weeks, consider a time dimension table:

| month_start | month_end_exclusive | fiscal_year | fiscal_period | is_working_day |
| --- | --- | --- | --- | --- |
| 2026-01-01 | 2026-02-01 | 2026 | 1 | ... |
| 2026-02-01 | 2026-03-01 | 2026 | 2 | ... |

A calendar dimension can store days, weeks, months, quarters, fiscal years, and holidays. It ensures multiple reports share one consistent period definition instead of generating date series with `CONNECT BY` everywhere.

## 11. Running Totals Over Time

### 11.1. Running total from the start of the series

Once there is one row per month:

~~~sql
WITH monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM monthly_sales
ORDER BY month_start;
~~~

`SUM(...) OVER(...)` is an analytic aggregate: it keeps each monthly row and adds a running total column. Unlike `GROUP BY`, analytic functions do not collapse monthly rows into a single row.

### 11.2. Running total per region

~~~sql
WITH monthly_region AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS region_running_revenue
FROM monthly_region
ORDER BY region, month_start;
~~~

`PARTITION BY region` resets the running total for each region. Without `PARTITION BY`, all regions accumulate together over time.

### 11.3. Why fill missing months before computing running totals?

If a month has no transactions, `GROUP BY` produces no row for that month. Running totals might still look right on active months, yet charts will miss the May data point and fail to render a continuous monthly series.

To ensure reports cover every period, generate the calendar series and `LEFT JOIN` first, apply `NVL(revenue, 0)`, and then compute analytic running totals over the complete series. This also ensures `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` genuinely represents three consecutive calendar months.

## 12. Rolling Windows: Moving Sums and Averages

### 12.1. Three-month moving average

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    AVG(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_avg_3_months,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_sum_3_months
FROM series
ORDER BY month_start;
~~~

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` takes up to three rows: the current row and the two preceding rows. Because `series` has exactly one row per month, a three-row window corresponds to three consecutive months.

### 12.2. ROWS vs. RANGE

In an analytic window:

- `ROWS` defines the window by physical row count in the analytic ordering.
- `RANGE` defines the window by sort value and logical interval; peer-row handling (rows sharing the same sort value) differs.

If data has one row per month with no gaps, three `ROWS` equals three months. If there are multiple transactions per day or multiple rows per date, `ROWS BETWEEN 2 PRECEDING` does not mean three days or three months. Either aggregate to the desired time grain first or use `RANGE` with matching expressions/data types.

### 12.3. Windows with fewer than three periods at the start of the series

The first month has only the current row; the second month has at most two rows; only from the third month onward are all three rows present. `AVG` divides by the number of non-NULL values present in the current frame rather than assuming prior periods had 0 revenue. If a full three-month window is required, check `COUNT(*) OVER(...)` and publish the rolling average only when three periods are present.

## 13. Month-over-Month Comparisons with LAG and LEAD

### 13.1. LAG retrieves the prior period's value

~~~sql
WITH monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    month_start,
    revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_month_revenue
FROM monthly_sales
ORDER BY month_start;
~~~

`LAG` reads the preceding row in the analytic order. If the `GROUP BY` series lacks May, June's row reads the previous active period (April) rather than treating May as 0 revenue.

### 13.2. Computing absolute and percentage change

~~~sql
WITH monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM')
),
comparison AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM monthly_sales
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS change_amount,
    ROUND(
        100 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS change_percent
FROM comparison
ORDER BY month_start;
~~~

`NULLIF(previous_revenue, 0)` avoids division by zero. If the prior period had zero revenue or no prior row exists, growth percentage is undefined and returns NULL; do not substitute 0% unless business rules define it that way.

### 13.3. Fill missing periods before using LAG

If June must be compared against May with 0 revenue, use a calendar series:

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
),
comparison AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM series
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS change_amount
FROM comparison
ORDER BY month_start;
~~~

May appears with revenue 0; June compares against 0. If you want a growth percentage from 0 to a positive number, define a separate business convention since division by zero is undefined.

### 13.4. LEAD looks at the next period

~~~sql
SELECT
    month_start,
    revenue,
    LEAD(revenue) OVER (ORDER BY month_start) AS next_month_revenue
FROM monthly_series
ORDER BY month_start;
~~~

`LEAD` is useful when comparing the current period against the next period, spotting declining periods, or pairing consecutive observations. Neither `LAG` nor `LEAD` fabricates missing periods; they only shift across rows present in the partition.

## 14. Reports Combining Month, Region, and Subtotals

### 14.1. Subtotals per month

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(TRUNC(sold_at, 'MM'), region)
ORDER BY month_start, GROUPING(region), region;
~~~

With `ROLLUP(month_start, region)`, the result includes month/region details, monthly subtotals (region rolled up), and the overall grand total. If you also want regional subtotals across all months rather than monthly subtotals, add a separate `(region)` grouping set; ROLLUP in its current order will not produce it.

### 14.2. Exact reporting tiers with GROUPING SETS

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (TRUNC(sold_at, 'MM'), region),
    (TRUNC(sold_at, 'MM')),
    (region),
    ()
)
ORDER BY grouping_level, month_start, region;
~~~

The report has four tiers: month/region, monthly total, regional total, and grand total. Use `GROUPING_ID` to distinguish data NULLs from aggregation-tier NULLs.

### 14.3. Do not rank subtotals as products

When needing top products per month alongside monthly subtotals, build two separate sets:

1. A detail CTE by month/product followed by analytic ranking.
2. A monthly subtotal CTE or separate `GROUPING SETS`.

Then `UNION ALL` both branches with a `row_type` or `grouping_level` column. If ranking runs on a set that already includes subtotals, monthly totals can place at the top and push real products out of Top-N, even though the report intends to rank products.

## 15. Ranking and Running Totals on a Monthly Series

A report may need each month's revenue, the month's rank within the year, and the running total:

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
FROM series
ORDER BY month_start;
~~~

All analytic functions operate together on the complete six-month series. Ranking by revenue handles ties; running total and `LAG` follow chronological order. To rank separately within each year, add `PARTITION BY calendar_year` to the ranking function.

## 16. Time, DATE/TIMESTAMP, and Reporting Time Zones

### 16.1. Using explicit time boundaries

For `DATE` columns:

~~~sql
WHERE sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-02-01'
~~~

For `TIMESTAMP` columns:

~~~sql
WHERE event_time >= TIMESTAMP '2026-01-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-02-01 00:00:00'
~~~

For `TIMESTAMP WITH TIME ZONE` columns, define the reporting period in the business time zone. Example January boundaries at offset +07:00:

~~~sql
WHERE event_time >= TO_TIMESTAMP_TZ(
          '2026-01-01 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND event_time < TO_TIMESTAMP_TZ(
          '2026-02-01 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
~~~

If business rules use a timezone region with DST, compute boundaries in that region rather than adding a fixed offset across all months. `TIMESTAMP WITH TIME ZONE` represents an instant with timezone/offset metadata; a local calendar period must be converted into two boundary instants in the proper timezone.

### 16.2. Converting to local date before grouping

If `EVENT_TIME` is `TIMESTAMP WITH TIME ZONE` and reporting is by day in Ho Chi Minh City:

~~~sql
SELECT
    TRUNC(
        CAST(event_time AT TIME ZONE 'Asia/Ho_Chi_Minh' AS DATE)
    ) AS local_day,
    COUNT(*) AS event_count
FROM app_events
GROUP BY TRUNC(
    CAST(event_time AT TIME ZONE 'Asia/Ho_Chi_Minh' AS DATE)
)
ORDER BY local_day;
~~~

The expression shifts the instant into the local timezone and casts to `DATE` to extract the day. For another timezone, substitute the appropriate region. On large tables, evaluate instant-range filtering and column/expression design to avoid unnecessary repeated computation.

### 16.3. Never convert time columns to strings for filtering

Avoid:

~~~sql
WHERE TO_CHAR(sold_at, 'YYYY-MM') = '2026-01'
~~~

for primary period filtering whenever a range predicate works. Functions on columns inhibit index range access and depend on formatting. `TO_CHAR` is suitable for display labels after data has been filtered/aggregated.

## 17. Performance of Aggregated and Analytic Reports

### 17.1. Filter before aggregating

If a report needs only PAID rows across six months, place those predicates at the source before `GROUP BY`:

~~~sql
WHERE status = 'PAID'
  AND sold_at >= :start_date
  AND sold_at <  :end_date
~~~

Reducing input row counts lowers aggregate, sort, and analytic costs. The optimizer can push predicates through some query blocks, yet writing conditions explicitly at the source clarifies data scope and usually unlocks better optimization.

### 17.2. Indexing for filters and time ranges

An index like:

~~~sql
CREATE INDEX ix_report_sales_status_date
ON report_sales_lab(status, sold_at);
~~~

can assist queries filtering by status and date range depending on selectivity/workload. However, if a report reads most of the table, a full table scan and hash/group aggregation may be more efficient. Indexes also increase DML and storage costs.

Never create an index merely because a column appears in `WHERE`. Evaluate matching row selectivity, index column order, columns read, clustering factor, execution plans, and report frequency versus write load.

### 17.3. Both GROUP BY and analytic functions may require sorts/hashes

`GROUP BY`, `ORDER BY`, `RANK`, `ROW_NUMBER`, `LAG`, and window frames can require intermediate processing, sorting, or memory. If data exceeds allocated memory, operations can spill to TEMP. You cannot judge resource consumption just by counting lines of SQL.

### 17.4. Avoid repeating identical aggregations

If multiple metrics derive from the same grain, create one aggregated CTE and reuse it:

~~~sql
WITH monthly_region AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        COUNT(*) AS sale_count,
        SUM(quantity * unit_price) AS revenue,
        SUM(quantity) AS units
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    sale_count,
    revenue,
    units,
    SUM(revenue) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM monthly_region;
~~~

CTEs promote logic reuse and express pipelines clearly. However, Oracle can inline/merge CTEs; do not assume every CTE automatically materializes. If materialization is needed, understand hints/features and evaluate via plans rather than adding hints by intuition.

### 17.5. Inspecting the execution plan and actual rows

View the estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT region, SUM(quantity * unit_price)
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY region;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

To gather runtime execution statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region, SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY region;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Metrics to inspect:

| Metric | Meaning |
| --- | --- |
| E-Rows | Optimizer estimated rows |
| A-Rows | Actual rows at the operation when runtime statistics are gathered |
| Starts | Number of times the operation executed |
| Buffers | Logical I/O |
| A-Time | Observed operation elapsed time |
| TempSpc | Estimated/used TEMP space depending on output format and operation |
| Predicate Information | Access and filter predicates |

If `E-Rows` diverges widely from `A-Rows`, check statistics, histograms, data skew, column correlations, and bind values. Never judge solely by `COST`; cost is an internal optimizer estimate, not milliseconds.

## 18. Common Report Design Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Total revenue is doubled | Joining two independent detail tables multiplies rows | Define grain and aggregate each source before joining |
| Subtotals get ranked like products | Analytic ranking runs over subtotal rows too | Separate detail ranking and subtotals into distinct query blocks/branches |
| Genuine NULLs mislabeled as TOTAL | Using NVL to detect subtotals | Use GROUPING/GROUPING_ID |
| May disappears | No transactions, so GROUP BY forms no group | Generate a calendar series and LEFT JOIN |
| June's LAG returns April | Data series skips May | Fill missing periods before calling LAG |
| Rolling 3 rows is not 3 months | Grain has multiple rows/month or missing months | Aggregate to one row/month and build a continuous series |
| Top 3 returns more than 3 rows | Using RANK/DENSE_RANK with ties | Use ROW_NUMBER if capped strictly at 3 rows |
| Top 3 returns 3 rows but drops ties | Using ROW_NUMBER | Use RANK/DENSE_RANK to keep ties |
| Same month across multiple years merges | Grouping only by MON or MONTH | Use TRUNC(date,'MM') or both year and month |
| End-of-day transactions lost | Using BETWEEN with midnight end boundary | Use `>= start` and `< next_period` |
| Division by zero in growth percentage | Prior period had zero revenue | Use NULLIF and a business convention for undefined cases |
| Report slows down after adding ranking | Sorting/windowing over too large a set or missing filters | Filter data before aggregating; inspect plan/TEMP |

## 19. Comprehensive Lab: Monthly Report with Subtotals, Top Products, and Running Totals

The steps below combine the core techniques. Table `REPORT_SALES_LAB` must already be created and populated from Section 2.

### Step 1 — Aggregate by month, region, and product

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue,
        SUM(quantity) AS units_sold
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
)
SELECT *
FROM monthly_product
ORDER BY month_start, region, revenue DESC;
~~~

Each row represents one product in one region during one month.

### Step 2 — Rank products within each month/region

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked AS (
    SELECT m.*,
           DENSE_RANK() OVER (
               PARTITION BY month_start, region
               ORDER BY revenue DESC
           ) AS revenue_rank
    FROM monthly_product m
)
SELECT *
FROM ranked
WHERE revenue_rank <= 3
ORDER BY month_start, region, revenue_rank, product_name;
~~~

This returns top 3 ranks, so more than three rows can appear if ties occur.

### Step 3 — Generate subtotals by month and region

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at < DATE '2026-07-01'
GROUP BY GROUPING SETS (
    (TRUNC(sold_at, 'MM'), region),
    (TRUNC(sold_at, 'MM')),
    (region),
    ()
)
ORDER BY grouping_level, month_start, region;
~~~

Output includes month/region details, monthly totals, regional totals, and grand total.

### Step 4 — Build a continuous month series and running metrics

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue,
    revenue - LAG(revenue) OVER (ORDER BY month_start) AS change_amount
FROM series
ORDER BY month_start;
~~~

May is present with revenue 0. Running totals stay unbroken; June's `LAG` is May.

### Step 5 — Combine into a unified report with Top-N and subtotals

The pattern below builds two separate sets: top products and subtotals. Both share the exact same time window and `PAID` filter:

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked_product AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY month_start, region
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM monthly_product m
),
monthly_region_total AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    product_name AS label,
    revenue,
    rn AS rank_no,
    'TOP_PRODUCT' AS row_type
FROM ranked_product
WHERE rn <= 3
UNION ALL
SELECT
    month_start,
    region,
    'REGION SUBTOTAL' AS label,
    revenue,
    CAST(NULL AS NUMBER) AS rank_no,
    'SUBTOTAL' AS row_type
FROM monthly_region_total
ORDER BY month_start, region, row_type, rank_no;
~~~

This is an illustrative report: each month/region has up to three product rows and one subtotal row. Because `ROW_NUMBER` is used, top products are capped at three rows; to preserve ties, switch to `RANK` and allow more than three rows.

In production reports, add `GROUPING_ID` or explicit `ROW_TYPE`, define subtotal/detail ordering per UI requirements, and ensure `UNION ALL` branches share identical column data types and semantics.

### Step 6 — Clean up lab table (optional)

~~~sql
-- Run only if you are certain this is your lab table and you no longer need the data.
DROP TABLE report_sales_lab PURGE;
~~~

`PURGE` bypasses the recycle bin. Skip this step if you want to keep the data for further practice.

## 20. Self-Check Questions

1. Why must grain be defined before writing a report?
2. Which grouping sets does `ROLLUP(region, product)` generate?
3. How do `ROLLUP(region, product)` and `ROLLUP(product, region)` differ?
4. When should you use `GROUPING` instead of checking `subtotal_col IS NULL`?
5. With `GROUPING_ID(region, product)`, which values represent detail, regional subtotal, and grand total?
6. How does `GROUPING SETS` differ from `ROLLUP` in selecting aggregation tiers?
7. Why can `CUBE` generate too many rows as the number of dimensions grows?
8. How do `ROW_NUMBER`, `RANK`, and `DENSE_RANK` handle ties differently?
9. To get the top 3 products per region, which column must `PARTITION BY` include?
10. Why must product revenue be aggregated before ranking products?
11. Why shouldn't you rank a combined set containing both subtotals and detail rows?
12. Why does monthly `GROUP BY` omit months that have no transactions?
13. What problem do a calendar series and `LEFT JOIN` solve?
14. Does `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` always mean three months?
15. Why must missing months be filled before using `LAG` if you want calendar-adjacent month comparisons?
16. What case does `NULLIF(previous_revenue, 0)` handle?
17. Why use `>= start` and `< next_period` instead of `BETWEEN` with an end-of-day timestamp?
18. Why avoid `TO_CHAR(date_col)` in the main filter predicate when a range works?
19. How should query blocks be separated in a report with multiple aggregation tiers and rankings?
20. When comparing performance, why inspect `A-Rows`, `Buffers`, and actual plans instead of just `COST`?

**Suggested answers:**

1. To know what entity each output row represents and avoid multiplying or dropping rows.
2. `(region, product)`, `(region)`, `()`.
3. Subtotals roll up by region or by product respectively.
4. To distinguish true NULLs in source data from NULLs generated by grouping sets omitting a column.
5. `0`, `1`, and `3` for that argument order.
6. `GROUPING SETS` lets you list exact desired combinations; `ROLLUP` produces a prefix chain.
7. `CUBE` produces 2^n grouping sets.
8. `ROW_NUMBER` is always unique; `RANK` shares ranks with gaps; `DENSE_RANK` shares ranks without gaps.
9. The columns defining each partition, e.g., `region`; if ranking separately per month/region, both `month_start` and `region`.
10. Ranking must sort total revenue at the product grain, not individual transactions.
11. Grand totals/subtotals can sit at the top and compete for rank positions against products.
12. No source rows means no group is formed.
13. Creates a row for every period and assigns 0/NULL per convention to missing periods.
14. Only when data already has one row per month in proper chronological order.
15. `LAG` reads the previous existing row and does not know about missing calendar periods.
16. Prevents division by zero; percentage growth in that case is undefined.
17. Covers every instant in the period, including fractional seconds.
18. Functions on columns can block index range scans and introduce format/NLS dependencies.
19. Aggregate detail first and rank on detail; compute subtotals separately with `GROUPING SETS`/`ROLLUP`, then combine.
20. `COST` is an estimate; actual rows and buffers/elapsed time reflect real execution behavior.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `GROUP BY`, `ROLLUP`, `CUBE`, `GROUPING SETS`, and analytic clauses.
- [Oracle Database SQL Language Reference — GROUPING](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING.html): distinguishing true NULLs from aggregated NULLs.
- [Oracle Database SQL Language Reference — GROUPING_ID](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING_ID.html): encoding grouping levels.
- [Oracle Database SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): analytic row numbering.
- [Oracle Database SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): ranking and ties.
- [Oracle Database SQL Language Reference — LAG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAG.html): accessing values in prior partition rows.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): partition, order, and window frame syntax.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plans, optimizer, indexes, and statistics.
