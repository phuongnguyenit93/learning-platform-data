# Writing Reports with CTEs, Window Functions, Ranking, and Subtotals

An operational report often needs to combine multiple transformations: filtering data by date, aggregating revenue by month and region, ranking top-selling categories, comparing against the previous month, computing running totals, and displaying subtotals. Writing all of that inside a deeply nested query makes SQL hard to read and hard to verify. MySQL 8.0 provides Common Table Expressions (CTEs) and window functions to break the problem into named steps while preserving row-level context when computing ranks and windowed metrics.

This lab builds a revenue report by month, region, and product category. We will use CTEs to filter and aggregate, a recursive CTE to generate every month in the period including months with no transactions, window functions for ranking and period-over-period changes, and `WITH ROLLUP` with `GROUPING()` to produce subtotals. Examples target MySQL 8.0 or later; CTEs and window functions require a supported version.

## 1. Problem Statement and Calculation Rules

An e-commerce team needs a monthly report broken down by region and product category. The report must answer:

- For each month and region, which category generated the highest revenue?
- Did current-month revenue increase or decrease compared to the immediately preceding month?
- What is the cumulative revenue since the beginning of the period?
- What is the average revenue over the last three months?
- What is the total revenue per region, and what is the grand total across the system?
- Are months without orders displayed with zero revenue?

Business conventions used in this example:

1. Include only orders with `status = 'COMPLETED'`.
2. Line-item revenue equals `quantity * unit_price * (1 - discount_percent / 100)`.
3. Revenue is aggregated by the month of `ordered_at`, the customer's region, and the product's category.
4. `from_date` is inclusive and `to_date` is an exclusive upper bound: `ordered_at >= from_date AND ordered_at < to_date`.
5. Months without transactions are included in the month series with 0 revenue so `LAG()` and rolling averages reflect consecutive calendar months accurately.
6. Rankings are computed within each month/region pair. On ties, `RANK()` assigns the same rank; `ROW_NUMBER()` uses the category code as a tiebreaker for deterministic ordering.

## 2. Creating the Sample Schema

We use tables for regions, customers, categories, products, orders, and order items. All transactional tables use InnoDB to support transactions and foreign keys.

```sql
CREATE DATABASE IF NOT EXISTS sales_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE sales_lab;

CREATE TABLE regions (
    region_code VARCHAR(10) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (region_code)
) ENGINE = InnoDB;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY ix_customers_region (region_code),
    CONSTRAINT fk_customers_region
      FOREIGN KEY (region_code) REFERENCES regions (region_code)
) ENGINE = InnoDB;

CREATE TABLE product_categories (
    category_code VARCHAR(30) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (category_code)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    category_code VARCHAR(30) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_id),
    KEY ix_products_category (category_code),
    CONSTRAINT fk_products_category
      FOREIGN KEY (category_code) REFERENCES product_categories (category_code)
) ENGINE = InnoDB;

CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    ordered_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_status_date_customer (status, ordered_at, customer_id),
    CONSTRAINT fk_orders_customer
      FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order_items (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_item_id),
    KEY ix_order_items_order_product (order_id, product_id),
    KEY ix_order_items_product (product_id),
    CONSTRAINT chk_order_items_discount
      CHECK (discount_percent >= 0 AND discount_percent <= 100),
    CONSTRAINT fk_order_items_order
      FOREIGN KEY (order_id) REFERENCES sales_orders (order_id),
    CONSTRAINT fk_order_items_product
      FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE = InnoDB;
```

`CHECK` constraints are enforced by MySQL starting in 8.0.16. On older versions, verify server limitations and ensure valid discounts at the application layer or via a compatible mechanism. The `utf8mb4_0900_ai_ci` collation requires MySQL 8.0; in older environments, pick a supported collation and re-evaluate comparison rules.

The sample indexes support the main join paths and filters. The index `(status, ordered_at, customer_id)` can help filter orders by status and date range, though effectiveness still depends on cardinality, status distribution, and query plans. Do not treat sample indexes as optimal for every workload.

## 3. Loading Sample Data

```sql
INSERT INTO regions (region_code, region_name) VALUES
('NORTH', 'North'),
('CENTRAL', 'Central'),
('SOUTH', 'South');

INSERT INTO customers (customer_id, region_code, email) VALUES
(1, 'NORTH', 'an@example.test'),
(2, 'NORTH', 'binh@example.test'),
(3, 'CENTRAL', 'chi@example.test'),
(4, 'SOUTH', 'dung@example.test');

INSERT INTO product_categories (category_code, category_name) VALUES
('BOOK', 'Books'),
('HOME', 'Home Goods'),
('TECH', 'Tech Devices');

INSERT INTO products (product_id, category_code, product_name) VALUES
(101, 'BOOK', 'Practical MySQL'),
(102, 'HOME', 'Desk Lamp'),
(103, 'TECH', 'Mechanical Keyboard');

INSERT INTO sales_orders (order_id, customer_id, ordered_at, status) VALUES
(1001, 1, '2026-01-05 09:15:00', 'COMPLETED'),
(1002, 1, '2026-01-20 14:30:00', 'COMPLETED'),
(1003, 2, '2026-02-03 10:00:00', 'COMPLETED'),
(1004, 3, '2026-02-14 11:20:00', 'COMPLETED'),
(1005, 4, '2026-03-01 08:00:00', 'COMPLETED'),
(1006, 4, '2026-03-15 16:45:00', 'CANCELLED');

INSERT INTO sales_order_items
    (order_item_id, order_id, product_id, quantity, unit_price, discount_percent)
VALUES
(1, 1001, 101, 2, 100.00, 0.00),
(2, 1001, 103, 1, 500.00, 10.00),
(3, 1002, 102, 1, 300.00, 0.00),
(4, 1003, 101, 1, 100.00, 0.00),
(5, 1003, 103, 1, 500.00, 0.00),
(6, 1004, 102, 2, 300.00, 0.00),
(7, 1005, 103, 1, 500.00, 20.00),
(8, 1006, 101, 10, 100.00, 0.00);
```

In the sample dataset, order `1006` is cancelled and excluded. Order `1001` has two items belonging to two different categories. When counting orders per category, use `COUNT(DISTINCT order_id)` because one order can contain multiple items in the same category.

For the period `2026-01-01` up to `2026-04-01`, expected total revenue from the sample data is `2550.00`: January is `950.00`, February is `1200.00`, and March is `400.00`. By region, NORTH has `1550.00`, CENTRAL has `600.00`, and SOUTH has `400.00`. These numbers help reconcile aggregation and `WITH ROLLUP` results in later sections.

Verify the initial data:

```sql
SELECT status, COUNT(*) AS order_count
FROM sales_orders
GROUP BY status;

SELECT
    oi.order_id,
    p.category_code,
    SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100)) AS line_revenue
FROM sales_order_items AS oi
JOIN products AS p ON p.product_id = oi.product_id
GROUP BY oi.order_id, p.category_code
ORDER BY oi.order_id, p.category_code;
```

## 4. First Step: Aggregating Revenue with GROUP BY

Before adding CTEs and window functions, build the basic aggregation query:

```sql
SELECT
    CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
    c.region_code,
    p.category_code,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS units_sold,
    CAST(
        SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100))
        AS DECIMAL(20, 2)
    ) AS revenue
FROM sales_orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id
JOIN sales_order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
WHERE o.status = 'COMPLETED'
  AND o.ordered_at >= '2026-01-01'
  AND o.ordered_at <  '2026-04-01'
GROUP BY
    CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
    c.region_code,
    p.category_code
ORDER BY month_start, c.region_code, p.category_code;
```

The date filter uses a half-open interval (`>=` and `<`) to include every timestamp on the final day without constructing `23:59:59.999999`. Avoid wrapping `ordered_at` inside `DATE()` in the `WHERE` clause if you want the optimizer to use range access on a date index.

The result only contains month/region/category combinations that had revenue. If a category had no sales in February, its row is omitted. This causes `LAG()` over sparse results to compare against the nearest prior month with data instead of the immediately preceding calendar month. We will build a date spine and full grid to solve this.

## 5. Using CTEs to Split the Report into Steps

A CTE is declared using `WITH` and exists only for the scope of a single statement. Each CTE has a name and can be queried like a logical table:

```sql
WITH monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        SUM(oi.quantity * oi.unit_price) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
    GROUP BY month_start, c.region_code, p.category_code
)
SELECT *
FROM monthly_sales
ORDER BY month_start, region_code, category_code;
```

The primary benefit of CTEs is naming intermediate steps such as `filtered_orders`, `monthly_sales`, `dense_sales`, or `ranked_sales`. This allows complex aggregation queries to be read and audited layer by layer. CTEs do not automatically execute faster than subqueries or temporary tables; MySQL may merge a CTE into the outer query or materialize it depending on structure and optimizer decisions. Check the execution plan rather than adopting CTEs purely for syntax.

## 6. Generating a Month Series with a Recursive CTE

To compute month-over-month changes, every month in the reporting period needs a row. A recursive CTE generates months from the starting month through the month containing the day prior to `to_date`.

Set parameters for the example:

```sql
SET @from_date = '2026-01-01';
SET @to_date = '2026-04-01'; -- exclusive
SET @top_n = 3;
```

Verify `from_date < to_date` before running the report. Month series CTE:

```sql
WITH RECURSIVE
params AS (
    SELECT
        CAST(@from_date AS DATE) AS from_date,
        CAST(@to_date AS DATE) AS to_date
),
month_series (month_start) AS (
    SELECT CAST(DATE_FORMAT(p.from_date, '%Y-%m-01') AS DATE)
    FROM params AS p
    WHERE p.from_date < p.to_date

    UNION ALL

    SELECT DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
    FROM month_series AS ms
    CROSS JOIN params AS p
    WHERE DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
          <= CAST(
              DATE_FORMAT(DATE_SUB(p.to_date, INTERVAL 1 DAY), '%Y-%m-01')
              AS DATE
          )
)
SELECT month_start
FROM month_series
ORDER BY month_start;
```

With `@from_date = '2026-01-01'` and `@to_date = '2026-04-01'`, the output yields three months: January, February, and March. If `to_date` were `2026-03-15`, March is still included because the interval covers days within March.

If `from_date` or `to_date` falls mid-month, the first or last month in the report is a partial month. When comparing MoM metrics, consider comparing equal numbers of days or publishing numbers only after the month finishes; `LAG()` only ensures comparing consecutive month buckets without adjusting for partial-period length.

Recursive CTEs are constrained by `cte_max_recursion_depth` (typically defaulting to 1000). If a report spans decades or complex calendars, use a pre-populated calendar dimension table instead of generating long sequences per request. Never raise the recursion limit indefinitely.

## 7. Complete Report with CTEs and Window Functions

The query below combines the following steps:

1. `params`: normalize the date range.
2. `month_series`: generate consecutive months.
3. `region_dim`, `category_dim`: load reporting dimensions.
4. `monthly_sales`: compute revenue, order count, and units sold.
5. `report_grid`: generate all month/region/category combinations.
6. `dense_sales`: assign 0 to combinations without transactions.
7. `windowed_sales`: rank, compare against the previous month, and compute cumulative totals and trailing averages.

```sql
WITH RECURSIVE
params AS (
    SELECT
        CAST(@from_date AS DATE) AS from_date,
        CAST(@to_date AS DATE) AS to_date
),
month_series (month_start) AS (
    SELECT CAST(DATE_FORMAT(p.from_date, '%Y-%m-01') AS DATE)
    FROM params AS p
    WHERE p.from_date < p.to_date

    UNION ALL

    SELECT DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
    FROM month_series AS ms
    CROSS JOIN params AS p
    WHERE DATE_ADD(ms.month_start, INTERVAL 1 MONTH)
          <= CAST(
              DATE_FORMAT(DATE_SUB(p.to_date, INTERVAL 1 DAY), '%Y-%m-01')
              AS DATE
          )
),
region_dim AS (
    SELECT region_code
    FROM regions
),
category_dim AS (
    SELECT category_code
    FROM product_categories
),
monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        COUNT(DISTINCT o.order_id) AS order_count,
        SUM(oi.quantity) AS units_sold,
        CAST(
            SUM(
                oi.quantity * oi.unit_price
                * (1 - oi.discount_percent / 100)
            ) AS DECIMAL(20, 2)
        ) AS revenue
    FROM params AS prm
    JOIN sales_orders AS o
      ON o.ordered_at >= prm.from_date
     AND o.ordered_at < prm.to_date
     AND o.status = 'COMPLETED'
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    GROUP BY
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
        c.region_code,
        p.category_code
),
report_grid AS (
    SELECT
        ms.month_start,
        r.region_code,
        cat.category_code
    FROM month_series AS ms
    CROSS JOIN region_dim AS r
    CROSS JOIN category_dim AS cat
),
dense_sales AS (
    SELECT
        g.month_start,
        g.region_code,
        g.category_code,
        COALESCE(s.order_count, 0) AS order_count,
        COALESCE(s.units_sold, 0) AS units_sold,
        COALESCE(s.revenue, CAST(0 AS DECIMAL(20, 2))) AS revenue
    FROM report_grid AS g
    LEFT JOIN monthly_sales AS s
      ON s.month_start = g.month_start
     AND s.region_code = g.region_code
     AND s.category_code = g.category_code
),
windowed_sales AS (
    SELECT
        month_start,
        region_code,
        category_code,
        order_count,
        units_sold,
        revenue,
        RANK() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC
        ) AS category_rank,
        DENSE_RANK() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC
        ) AS category_dense_rank,
        ROW_NUMBER() OVER (
            PARTITION BY month_start, region_code
            ORDER BY revenue DESC, category_code
        ) AS category_row_number,
        LAG(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
        ) AS previous_month_revenue,
        SUM(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue,
        AVG(revenue) OVER (
            PARTITION BY region_code, category_code
            ORDER BY month_start
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS trailing_3_month_avg
    FROM dense_sales
)
SELECT
    month_start,
    region_code,
    category_code,
    order_count,
    units_sold,
    revenue,
    category_rank,
    category_dense_rank,
    category_row_number,
    previous_month_revenue,
    revenue - previous_month_revenue AS revenue_change,
    ROUND(
        100 * (revenue - previous_month_revenue)
        / NULLIF(previous_month_revenue, 0),
        2
    ) AS revenue_change_percent,
    cumulative_revenue,
    ROUND(trailing_3_month_avg, 2) AS trailing_3_month_avg
FROM windowed_sales
WHERE category_rank <= @top_n
ORDER BY month_start, region_code, category_rank, category_code;
```

### Reading the results

- `category_rank`: rank with gaps on ties, such as 1, 1, 3.
- `category_dense_rank`: rank without gaps on ties, such as 1, 1, 2.
- `category_row_number`: unique sequence number using `category_code` as tiebreaker.
- `previous_month_revenue`: revenue of the immediately preceding calendar month because `dense_sales` contains every month.
- `revenue_change`: revenue difference compared to the previous month.
- `revenue_change_percent`: percentage change; returns `NULL` when prior-month revenue is 0 to prevent division by zero.
- `cumulative_revenue`: cumulative revenue from the first month of the period through the current month per region/category.
- `trailing_3_month_avg`: average revenue of the current month and up to two preceding months.

In the first month, `LAG()` returns `NULL` since there is no prior row. When the previous month's revenue is 0, the percentage change is also `NULL`; the business UI can display a "new activity" label instead of an infinite percentage.

`RANK()` is filtered in the outer query because window functions are evaluated after `WHERE` within the same query block. Filtering by `category_rank <= @top_n` may return more than N rows if categories tie at the cutoff. If you need strictly at most N categories, replace the condition with `category_row_number <= @top_n`.

## 8. Understanding Window Function Evaluation Order

Window functions operate on the result set after `FROM`, `WHERE`, `GROUP BY`, and `HAVING` have been evaluated for that query block. They retain individual rows rather than collapsing multiple rows into one like `GROUP BY`.

| Component | Meaning |
|---|---|
| `PARTITION BY` | Splits the result set into independent groups for window evaluation. |
| `ORDER BY` inside `OVER` | Defines row ordering within each partition. |
| `ROWS`/`RANGE` frame | Defines which rows belong to the current row's window frame. |
| `RANK()` | Ranks rows, leaving gaps after ties. |
| `DENSE_RANK()` | Ranks rows without leaving gaps after ties. |
| `ROW_NUMBER()` | Assigns a unique sequential number based on the declared order. |
| `LAG()`/`LEAD()` | Reads a value from a preceding/following row in the partition. |
| `SUM() OVER` | Computes a windowed sum, suitable for running totals. |
| `AVG() OVER` | Computes a windowed average, such as a moving average. |

Without `ORDER BY` inside `OVER`, row ordering is undefined for order-sensitive functions. When deterministic repeatability is needed, include a tiebreaker column such as a primary key or category code. The final `ORDER BY` at the end of the statement only sorts the returned output; it does not replace `ORDER BY` inside the window specification.

### ROWS vs. RANGE

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` selects up to three physical rows in partition order. In our example, the grid guarantees one row per month/region/category, so three physical rows correspond to three consecutive months.

`RANGE` defines the frame by sort-key values and follows specific rules for peer rows. For monthly reports, using `ROWS` after normalizing to one row per month is usually easier to reason about. With sparse data or multiple rows sharing the same timestamp, explicitly define the desired frame semantics.

## 9. Generating Subtotals with WITH ROLLUP and GROUPING()

Window functions compute metrics on each detail row; `WITH ROLLUP` appends subtotal rows for grouping levels. With the grouping order `month_start, region_code, category_code`, MySQL generates:

1. Detail totals per month/region/category.
2. Subtotals per month/region.
3. Monthly totals.
4. Grand total for the entire period.

Standalone subtotal query:

```sql
WITH filtered_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        CAST(
            SUM(
                oi.quantity * oi.unit_price
                * (1 - oi.discount_percent / 100)
            ) AS DECIMAL(20, 2)
        ) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
      AND o.ordered_at >= @from_date
      AND o.ordered_at < @to_date
    GROUP BY
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE),
        c.region_code,
        p.category_code
),
subtotal_rows AS (
    SELECT
        month_start,
        region_code,
        category_code,
        SUM(revenue) AS revenue,
        GROUPING(month_start) AS g_month,
        GROUPING(region_code) AS g_region,
        GROUPING(category_code) AS g_category
    FROM filtered_sales
    GROUP BY month_start, region_code, category_code WITH ROLLUP
)
SELECT
    CASE
        WHEN g_month = 1 THEN 'GRAND TOTAL'
        WHEN g_region = 1 THEN 'MONTH TOTAL'
        WHEN g_category = 1 THEN 'REGION SUBTOTAL'
        ELSE 'DETAIL'
    END AS row_type,
    month_start,
    region_code,
    category_code,
    revenue
FROM subtotal_rows
ORDER BY
    g_month,
    month_start,
    g_region,
    region_code,
    g_category,
    category_code;
```

`WITH ROLLUP` produces `NULL` values in columns rolled up to a higher level. However, source data itself can also contain `NULL`; `GROUPING(column)` returns 1 if the `NULL` was generated by rollup and 0 if it comes from an actual data group. Use the flags `g_month`, `g_region`, and `g_category` to clearly distinguish detail rows, region subtotals, monthly totals, and the grand total.

The column order in `GROUP BY ... WITH ROLLUP` determines the subtotal hierarchy. Changing it to `GROUP BY region_code, month_start, category_code WITH ROLLUP` changes which summary levels are generated. Design the grouping sequence to match the report structure.

## 10. Combining Window Functions and Subtotals

You do not need to mix `WITH ROLLUP` and window functions in the same query block. A cleaner, more controllable approach is:

- The first CTE produces detail rows and window metrics.
- Another query or subsequent CTE aggregates the detail rows into subtotals.
- If a single unified dataset is required, `UNION ALL` the detail rows with the subtotal rows while adding a `row_type` column so consumers know how to render each row.

Never sum subtotal rows together with detail rows, as that double-counts revenue. When computing a grand total from a dataset containing subtotals, filter using `GROUPING` flags or aggregate from the detail CTE before rollup.

## 11. Query Tuning and Inspecting Execution Plans

CTEs help structure logic, yet reports can still be resource-intensive due to multi-table joins, `COUNT(DISTINCT)`, cross-join grids, sorting, and window partitioning.

### Checking indexes and filters

The query filters by `status` and `ordered_at` range, then joins on `customer_id`, `order_id`, and `product_id`. Sample indexes include:

| Table | Index | Role |
|---|---|---|
| `sales_orders` | `(status, ordered_at, customer_id)` | Filters by status and date range, covering `customer_id` for joins. |
| `sales_order_items` | `(order_id, product_id)` | Looks up order items by order and product. |
| `sales_order_items` | `(product_id)` | Supports joining from product if the optimizer chooses that direction. |
| `customers` | `(region_code)` | Supports querying/grouping by region when needed. |
| `products` | `(category_code)` | Supports querying by category. |

Indexes carry write and storage overhead. Base index decisions on `EXPLAIN`, estimated row counts, cardinality, and overall workload. A new index will not necessarily be chosen if the filter matches too many rows or if the optimizer estimates another plan is cheaper.

### Using EXPLAIN

```sql
EXPLAIN FORMAT=TREE
WITH monthly_sales AS (
    SELECT
        CAST(DATE_FORMAT(o.ordered_at, '%Y-%m-01') AS DATE) AS month_start,
        c.region_code,
        p.category_code,
        SUM(oi.quantity * oi.unit_price) AS revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    JOIN sales_order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE o.status = 'COMPLETED'
      AND o.ordered_at >= '2026-01-01'
      AND o.ordered_at < '2026-04-01'
    GROUP BY month_start, c.region_code, p.category_code
)
SELECT * FROM monthly_sales;
```

`EXPLAIN FORMAT=TREE` is available in supported MySQL 8.0 versions; if unsupported, use standard `EXPLAIN`. On supported versions, `EXPLAIN ANALYZE` executes the query to measure actual row counts and timings; run it only in test environments or after assessing query impact.

Check:

- Does `sales_orders` use range/index access for the date interval?
- Is there a full table scan on a large table, and is that actually problematic given current selectivity?
- Do joins use appropriate primary/foreign key indexes?
- Does the post-join row count spike unexpectedly due to one-to-many relationships?
- Do sorting, materialization, or windowing create large temporary tables?
- Which CTEs are materialized, and are any read repeatedly?

### Bounding the grid size

`report_grid` generates a number of rows equal to:

\[
N_{grid} = N_{months} \times N_{regions} \times N_{categories}
\]

For instance, 36 months × 20 regions × 50 categories yields 36,000 rows before window evaluation. With thousands of tenants or tens of thousands of categories, a cross join can grow too large. In such cases:

- Filter regions/categories to the report scope before building the grid.
- Use normalized calendar and dimension tables.
- Generate only relevant combinations, or use a snapshot/reporting mart table.
- Pre-compute in time-based batches and store aggregated results if the report runs frequently.
- Cap the maximum allowed date range on the reporting endpoint.

If months without revenue do not need to be shown, you can omit `month_series` and `report_grid` and use `monthly_sales` directly; however, `LAG()` will then compare against the previous row with data rather than necessarily the immediately preceding calendar month.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `GROUP BY` to compute running totals | Drops detail rows needed in the report. | Use `SUM() OVER (...)` with an explicit frame. |
| Using `LAG()` on sparse monthly data | Compares against the nearest prior month with data, skipping empty months. | Build a date spine and full grid, or clearly document semantics. |
| Using `RANK()` when expecting strictly N rows | Ties can return more than N rows. | Use `ROW_NUMBER()` with a deterministic tiebreaker. |
| Filtering a window alias in `WHERE` of the same query block | Window functions are not yet evaluated at the `WHERE` stage. | Put window results in a CTE/subquery and filter in the outer query. |
| Dividing by zero prior-month revenue | Division-by-zero error or meaningless output. | Use `NULLIF(previous_month_revenue, 0)`. |
| Omitting `COUNT(DISTINCT order_id)` | An order with multiple lines in one category gets counted repeatedly. | Define report grain before counting. |
| Treating `WITH ROLLUP` NULL as source data | Subtotal labels get confused with groups having a NULL key. | Use `GROUPING()` to distinguish them. |
| Summing detail and subtotal rows together | Total revenue is doubled. | Separate detail/subtotal datasets or filter by grouping flags. |
| Building an unbounded cross-join grid | Intermediate row count explodes quickly. | Bound date range/dimensions or use summary tables. |
| Assuming CTEs are always faster than subqueries | May materialize and increase I/O/temp space. | Check execution plans and benchmark on real data. |
| Using `DATE(ordered_at)` in filter conditions | Can prevent range access on a date index. | Use a half-open range directly on the raw column. |

## 13. Validating Report Accuracy

Do not merely verify that SQL runs without errors. Confirm the results match business rules:

1. `CANCELLED` orders are excluded.
2. An order with multiple lines in the same category is counted once in that category's `order_count`.
3. Discounts are applied before summing revenue.
4. `to_date` is excluded from the reporting interval.
5. Every month/region/category in the grid appears in exactly one row.
6. Combinations without transactions have `order_count = 0`, `units_sold = 0`, and `revenue = 0`.
7. `LAG()` points to the immediately preceding calendar month, even if that month had 0 revenue.
8. `RANK()` handles ties properly; `ROW_NUMBER()` produces deterministic ordering.
9. Running total equals the sum of months from the start of the period through the current row.
10. Regional subtotals and the grand total equal the sum of their corresponding detail rows.

### Reconciling with a direct total query

Calculate total period revenue directly:

```sql
SELECT
    CAST(
        SUM(
            oi.quantity * oi.unit_price
            * (1 - oi.discount_percent / 100)
        ) AS DECIMAL(20, 2)
    ) AS expected_total
FROM sales_orders AS o
JOIN sales_order_items AS oi ON oi.order_id = o.order_id
WHERE o.status = 'COMPLETED'
  AND o.ordered_at >= @from_date
  AND o.ordered_at < @to_date;
```

Compare this against the grand total in the `WITH ROLLUP` output. If they differ, check whether joins multiplied rows, dimensions were missing, order statuses differed, or date bounds mismatched. Because `sales_order_items` is at line-item grain, the direct total query above does not need to join customers or products unless filtering by them.

### Checking grid row count

```sql
SELECT
    (SELECT COUNT(*) FROM regions)
    * (SELECT COUNT(*) FROM product_categories) AS dimension_combinations;
```

Multiply by the number of months in `month_series` to estimate row count before window evaluation. For production reports, document estimated row counts and execution times at the maximum allowed date range.

## 14. Extending the Practice

Once the base report works accurately, try these variations:

### A. Top 3 categories per region and month

Keep `WHERE category_rank <= 3` to allow tied categories to appear together. Then change it to `category_row_number <= 3` and compare row counts and results when revenues tie.

### B. Year-over-year comparison

Over `dense_sales`, add:

```sql
LAG(revenue, 12) OVER (
    PARTITION BY region_code, category_code
    ORDER BY month_start
) AS same_month_last_year
```

This requires the date spine to include at least 12 preceding months. If the report period starts only from the current month, expand the input data range by at least 12 months to compute year-over-year comparisons rather than merely generating 12 months in the output.

### C. Ranking customers by revenue

Change the report grain to `month_start, region_code, customer_id`, compute revenue per customer, and apply:

```sql
RANK() OVER (
    PARTITION BY month_start, region_code
    ORDER BY customer_revenue DESC
) AS customer_rank
```

### D. Adding regional revenue share

Inside `windowed_sales`, you can compute total revenue for the same month/region via a window:

```sql
SUM(revenue) OVER (
    PARTITION BY month_start, region_code
) AS region_month_revenue
```

Then compute the share:

```sql
ROUND(100 * revenue / NULLIF(region_month_revenue, 0), 2) AS revenue_share_percent
```

### E. Persisting periodic reports

If the report is queried frequently on large datasets, consider creating a summary table by month/region/category updated via batch or event-driven pipelines. Define how to handle order status changes, refunds, cancellations, and late-arriving data; summary tables must have a rebuild/reconciliation procedure.

## 15. Report Acceptance Checklist

- [ ] Defined report grain and revenue/order-counting rules.
- [ ] Date filters use half-open intervals without transforming indexed columns in `WHERE`.
- [ ] CTEs are named to clearly reflect filtering, aggregation, grid creation, and windowing steps.
- [ ] Recursive CTE terminates cleanly at the end month with an appropriate recursion limit.
- [ ] Empty months are zero-filled if the report requires comparison with the immediately preceding calendar month.
- [ ] `COUNT(DISTINCT)` is applied at the proper grain to avoid double-counting orders.
- [ ] `RANK`, `DENSE_RANK`, and `ROW_NUMBER` are selected according to tie-handling requirements.
- [ ] Window frames (`ROWS`/`RANGE`) are explicitly specified for running totals and moving averages.
- [ ] Percentage change handles zero denominators using `NULLIF`.
- [ ] `WITH ROLLUP` and `GROUPING()` distinguish detail rows, subtotals, and grand totals.
- [ ] Detail and subtotal rows are never summed together to double-count revenue.
- [ ] Grid size is bounded across months × regions × categories.
- [ ] Execution plan, temporary tables, sorts, indexes, and runtime have been verified.
- [ ] Results are reconciled against an independent total query and boundary test cases.

CTEs break reports into readable steps; recursive CTEs generate continuous monthly calendars; window functions preserve individual rows while computing rankings, changes, running totals, and moving averages; and `WITH ROLLUP` adds subtotal levels. By defining the grain properly, filling empty months, handling ties, and verifying execution plans, MySQL reports remain both easy to audit and scalable for real analytical workloads.
