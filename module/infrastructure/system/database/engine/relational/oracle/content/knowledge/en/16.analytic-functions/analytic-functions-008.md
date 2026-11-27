# Analytic COUNT, RATIO_TO_REPORT, and Group Share in Oracle

In reporting, you sometimes need to keep every detail row while still knowing how many records exist in each row's group, what percentage of the total that group represents, or what share of a region's revenue a particular amount contributes. If you use `GROUP BY` directly, Oracle collapses multiple rows into one row per group and you can lose detail columns. **Analytic functions** solve this problem: they compute over a window of related rows while preserving the rows of the query.

Two useful tools are:

- **Analytic COUNT**: counts rows or non-NULL values across the entire result, within each partition, or across a running window.
- **RATIO_TO_REPORT**: computes the ratio of a value to the sum of values in its partition, making it well suited for expressing shares of revenue, cost, quantity, or budget within a group.

For example, a sales report can display each transaction, the region's transaction count, the region's total revenue, and that transaction's contribution percentage. An HR report can keep every employee while adding the department headcount and a running sequence/count by hire date.

After this lesson, you will be able to:

- Distinguish aggregate COUNT from analytic COUNT.
- Use `COUNT(*)`, `COUNT(expr)`, and `COUNT(DISTINCT expr)` inside an `OVER` clause.
- Count across the full result, count by `PARTITION BY`, and build running counts using `ORDER BY`/window frames.
- Understand how NULLs are handled and why row counts after a JOIN affect count results.
- Use `RATIO_TO_REPORT` to calculate share across the entire dataset or within each group.
- Convert decimal ratios to percentages, round, and format for display.
- Handle groups whose total is 0 or where all measures are NULL.
- Combine `GROUP BY`, CTEs, and analytic functions without confusing the grain.
- Filter analytic results using an outer query block and inspect execution plans when needed.

> Examples use tables prefixed with `LAB_` and are suitable for practicing in a dedicated schema. `COUNT` and `RATIO_TO_REPORT` compute over the row set supplied by the query block after `FROM/WHERE/JOIN/GROUP BY/HAVING`; if a `JOIN` has multiplied rows, count and share results will be affected as well. Identify clearly what each input row represents before computing.

## 1. Aggregate vs. Analytic: Difference in Returned Results

### 1.1. Aggregate COUNT Collapses Rows

Suppose the `SALES` table has transactions:

| SALE_ID | REGION_ID | AMOUNT |
| ---: | --- | ---: |
| 1 | NORTH | 100 |
| 2 | NORTH | 200 |
| 3 | NORTH | 300 |
| 4 | SOUTH | 150 |
| 5 | SOUTH | 250 |

`COUNT` combined with `GROUP BY` produces one row per region:

```sql
SELECT region_id, COUNT(*) AS sale_count
FROM lab_sales
GROUP BY region_id;
```

Result:

| REGION_ID | SALE_COUNT |
| --- | ---: |
| NORTH | 3 |
| SOUTH | 2 |

Detail transaction rows have been collapsed. This is the right choice when the output needs **one row per region**.

### 1.2. Analytic COUNT Preserves Detail Rows

Add `OVER`:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_sale_count
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Conceptual result:

| SALE_ID | REGION_ID | AMOUNT | REGION_SALE_COUNT |
| ---: | --- | ---: | ---: |
| 1 | NORTH | 100 | 3 |
| 2 | NORTH | 200 | 3 |
| 3 | NORTH | 300 | 3 |
| 4 | SOUTH | 150 | 2 |
| 5 | SOUTH | 250 | 2 |

Oracle still returns five transaction rows; each row is enriched with the transaction count of its corresponding region. This is the core distinction: **`GROUP BY` changes the output grain, whereas analytic functions attach results onto the rows of the current grain**.

### 1.3. Processing Model

```text
Rows after FROM / JOIN / WHERE
               │
               ▼
       Query block row set
               │
        ┌──────┴─────────┐
        ▼                ▼
   GROUP BY          OVER (...)
        │                │
        ▼                ▼
 Collapse into      Keep each row
 groups and        and attach window
 compute COUNT         result
        │                │
        ▼                ▼
 One row/group    One input row/position
```

A single `SELECT` can use both aggregate and analytic functions, but you must understand that analytic functions see **the rows after `GROUP BY`** if the query block includes `GROUP BY`. Section 8 covers this case.

## 2. Analytic COUNT: Syntax and Three Counting Forms

General syntax:

```sql
COUNT({* | [DISTINCT | ALL] expr})
OVER (
    [PARTITION BY partition_expression, ...]
    [ORDER BY order_expression ...]
    [windowing_clause]
)
```

`OVER` defines the data window that the analytic function inspects:

- Without `PARTITION BY`: the window can be the entire row set of the query block.
- With `PARTITION BY`: divides the row set into independent logical groups.
- With `ORDER BY`: defines processing order within the partition; for analytic aggregates such as `COUNT`, it also brings in the default window frame.
- With a windowing clause: restricts the rows in the window, for example from the start of the partition to the current row.

### 2.1. COUNT(*) OVER(): Counting All Rows in the Result

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER () AS total_rows
FROM lab_sales
ORDER BY sale_id;
```

Every row receives the same `TOTAL_ROWS` value of 5. With no `PARTITION BY`, the window covers all rows of the query block.

This is how you attach the total row count to each detail row, commonly used in paginated reports, displaying record counts, or computing ratios across the full result.

### 2.2. COUNT(*) OVER(PARTITION BY ...): Counting Within Each Group

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS rows_in_region
FROM lab_sales
ORDER BY region_id, sale_id;
```

Each region is counted separately. All rows with the same `REGION_ID` belong to the same partition; partitions do not affect one another.

If `PARTITION BY` lists multiple columns, groups are determined by the combination of column values:

```sql
COUNT(*) OVER (
    PARTITION BY region_id, product_id
) AS rows_per_region_product
```

This example counts transactions for each region-and-product combination.

### 2.3. COUNT(expr) Ignores NULL

Unlike `COUNT(*)`, `COUNT(expr)` counts only rows where the expression is not NULL:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS all_region_rows,
    COUNT(amount) OVER (
        PARTITION BY region_id
    ) AS nonnull_amount_rows
FROM lab_sales
ORDER BY region_id, sale_id;
```

If a region has four transactions but one transaction lacks an `AMOUNT`, `COUNT(*)` returns 4 while `COUNT(AMOUNT)` returns 3 on every row in that region.

Rules:

| Expression | Meaning |
| --- | --- |
| `COUNT(*)` | Counts all rows, including rows with NULL columns |
| `COUNT(expr)` | Counts rows where expr is non-NULL |
| `COUNT(DISTINCT expr)` | Counts distinct non-NULL values of expr |

`COUNT` returns 0 when the window has rows but every `expr` value is NULL. If the query block returns zero rows, there are no output rows on which to display an analytic `COUNT` value.

### 2.4. COUNT(DISTINCT expr) OVER(PARTITION BY ...)

You can count distinct values within each partition:

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    COUNT(DISTINCT product_id) OVER (
        PARTITION BY region_id
    ) AS distinct_products_in_region
FROM lab_sales
ORDER BY region_id, sale_id;
```

This example shows how many distinct product IDs exist in each region while keeping every transaction row.

**Oracle syntax restriction:** when using `DISTINCT` inside analytic `COUNT`, the analytic clause may contain only `PARTITION BY`; do not use `ORDER BY` or a windowing clause alongside `DISTINCT` in the same `COUNT` call. If you need a running distinct count over time, you typically must design a multi-step query (for example identifying each value's first occurrence and summing a flag) instead of writing `COUNT(DISTINCT ...) OVER(ORDER BY ...)`.

## 3. PARTITION BY: Defining Groups for Analytic Functions

`PARTITION BY` divides the row set into logical partitions. It does not sort the final output and does not filter out rows.

### 3.1. Counting by Department

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_headcount
FROM lab_employees
ORDER BY department_id, employee_id;
```

Each employee still has one row. The department's employee count is repeated on each row of that department.

### 3.2. Multi-Level PARTITION BY

You can partition by region and month:

```sql
COUNT(*) OVER (
    PARTITION BY region_id, TRUNC(sold_at, 'MM')
) AS sales_in_region_month
```

Each combination of `REGION_ID` and month is a separate partition. If a partition expression contains a function such as `TRUNC`, consider data types and using consistent expressions across related queries.

### 3.3. NULL Values in Partition Keys

Rows with NULL partition keys are grouped into the same partition for analytic function purposes. For example, employees not yet assigned to a department (`DEPARTMENT_ID IS NULL`) are counted together in the NULL partition unless handled otherwise.

If you do not want to group rows with missing keys together, establish an explicit policy: filter them out, assign a dedicated group label with `CASE`/`NVL` as appropriate, or keep the NULL partition and document what it means.

### 3.4. PARTITION BY Is Not the Same as GROUP BY

| GROUP BY | PARTITION BY inside OVER |
| --- | --- |
| Collapses rows into result groups | Splits rows into logical windows |
| Usually reduces output row count | Does not reduce row count by itself |
| Non-aggregated columns must appear in GROUP BY | Can retain detail columns of each row |
| Used to produce one-row-per-group summaries | Used to attach group statistics onto detail rows |

## 4. COUNT with ORDER BY: Running Counts and Window Frames

Analytic `COUNT` can be combined with `ORDER BY` to produce a running count.

### 4.1. Running Count by Date

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at
    ) AS running_sales_count
FROM lab_sales
ORDER BY region_id, sold_at, sale_id;
```

When `ORDER BY` is present in an analytic aggregate without a specified window frame, Oracle uses a default `RANGE` frame from `UNBOUNDED PRECEDING` to `CURRENT ROW`. This means rows with the same `ORDER BY` value (peer rows) belong to each other's frames; they can receive the same running count at that point.

If you need to count sequentially row by row, establish a unique ordering and use `ROWS`:

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_by_row_count
FROM lab_sales
ORDER BY region_id, sold_at, sale_id;
```

Here `SALE_ID` acts as a tie-breaker so ordering is unambiguous when multiple transactions share the same `SOLD_AT`.

### 4.2. How Do RANGE and ROWS Differ?

- `ROWS` defines the window by physical row position in the analytic order.
- `RANGE` defines the window by logical value of the `ORDER BY` expression; peer rows with the same value are generally included together in the frame.

For example, if three transactions occur at 10:00, under `RANGE` to `CURRENT ROW`, all three receive a count that includes all three transactions. With `ROWS` and the tie-breaker `SALE_ID`, the rows receive counts 1, 2, 3 sequentially within the partition.

### 4.3. Sliding Window: Counting the Last N Rows

`COUNT` also works with bounded frames:

```sql
COUNT(*) OVER (
    PARTITION BY region_id
    ORDER BY sold_at, sale_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS sales_in_last_7_rows
```

This is the count of rows across at most the seven most recent positions up to the current row. It **does not automatically mean the last seven calendar days**; if data has multiple transactions on one day or missing days, `ROWS` still counts rows. For a time-span window, use `RANGE` with a date/numeric expression and syntax compatible with the `ORDER BY` type, or aggregate by day first.

### 4.4. Omit ORDER BY When You Only Need the Partition Total

If the goal is solely the total row count in the entire region, do not add `ORDER BY`:

```sql
COUNT(*) OVER (PARTITION BY region_id)
```

Unintentionally adding `ORDER BY` turns the result from a full-group total into a running count. This is an easy mistake when copying an analytic expression from a running-total report.

## 5. RATIO_TO_REPORT: Share Within a Group

### 5.1. Meaning and Syntax

`RATIO_TO_REPORT(expr)` computes the ratio of `expr`'s value to the sum of `expr` within the partition:

```sql
RATIO_TO_REPORT(expr)
OVER (
    [PARTITION BY partition_expression, ...]
)
```

Conceptually:

```text
Share of a row
= row value
  / sum of values in partition
```

For example, if a transaction's revenue is 200 and the region's total revenue is 1,000, the ratio is 0.2 (i.e., 20%).

`RATIO_TO_REPORT` is an analytic function: it **does not collapse rows**. Each row receives the ratio of its own value relative to the partition sum.

### 5.2. Share Across the Entire Result

Without `PARTITION BY`, the entire row set of the query block is one group:

```sql
SELECT
    sale_id,
    amount,
    RATIO_TO_REPORT(amount) OVER () AS total_share
FROM lab_sales
ORDER BY sale_id;
```

If total amount is 1,000, a transaction of 100 has ratio 0.1; a transaction of 200 has ratio 0.2. The ratios of all rows with non-NULL `AMOUNT` sum to 1 when the total is nonzero (subject to tiny display differences from rounding).

### 5.3. Share by Region

```sql
SELECT
    sale_id,
    region_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Each region has its own denominator. Ratios within NORTH sum to 1; ratios within SOUTH also sum to 1, provided each region's sum is nonzero and measures are valid.

### 5.4. Multi-Dimensional Share

You can compute shares within each region-month combination:

```sql
RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id, TRUNC(sold_at, 'MM')
) AS share_in_region_month
```

The denominator is the sum of `amount` for that exact region-month partition. Changing the partition key changes the business question: share of the entire company, of a region, of a region-month, or of a product-region are all different metrics.

### 5.5. RATIO_TO_REPORT vs. SUM OVER

You can express the ratio manually using:

```sql
amount / SUM(amount) OVER (PARTITION BY region_id)
```

When the sum is nonzero, this expression is semantically equivalent to:

```sql
RATIO_TO_REPORT(amount) OVER (PARTITION BY region_id)
```

`RATIO_TO_REPORT` is concise and clearly conveys share intent. `SUM OVER` is useful when you also need to display the denominator or handle special edge cases explicitly.

`RATIO_TO_REPORT` takes `OVER` with `PARTITION BY`; do not add `ORDER BY`/windowing clauses as with analytic `COUNT`. If you need a cumulative share in order, use analytic `SUM` with a window frame for the cumulative numerator and the partition sum as the denominator, rather than trying to put `ORDER BY` inside `RATIO_TO_REPORT`.

## 6. NULLs, Zero Totals, and Negative Values in Shares

### 6.1. NULL Measures

If `expr` is NULL, `RATIO_TO_REPORT` returns NULL for that row. The denominator sum is computed like `SUM`, so NULL values do not contribute to the total. This matches the meaning "no value available to calculate a share", though the report must distinguish NULL from a 0 share.

- Amount equals 0, partition total nonzero: share is 0.
- Amount is NULL: share is NULL.
- All amounts in partition are NULL: partition `SUM` is NULL, so there is no meaningful share.

Do not blindly replace NULL with 0 using `NVL` if business rules need to distinguish "not recorded" from "recorded value of 0".

### 6.2. Partition Total Equals 0

If the partition sum is 0, division is undefined. In Oracle, dividing a number by 0 can raise `ORA-01476: divisor is equal to zero`. Do not design reports assuming a zero total will automatically turn into a valid ratio.

If the total can be 0, compute the denominator and guard explicitly:

```sql
WITH sales_with_total AS (
    SELECT
        sale_id,
        region_id,
        amount,
        SUM(amount) OVER (
            PARTITION BY region_id
        ) AS region_total
    FROM lab_sales
)
SELECT
    sale_id,
    region_id,
    amount,
    region_total,
    CASE
        WHEN region_total = 0 THEN NULL
        ELSE amount / region_total
    END AS safe_region_share
FROM sales_with_total
ORDER BY region_id, sale_id;
```

When the total is NULL (for example, all amounts are NULL), the `ELSE` branch also yields NULL because dividing by NULL returns NULL. The `CASE` here states the policy explicitly: a 0 total makes the share undefined and represents it as NULL. If business rules want 0%, N/A, or a distinct status, adjust the policy deliberately.

### 6.3. Negative Totals or Mixed Positive/Negative Values

`RATIO_TO_REPORT` does not guarantee results lie between 0 and 1. If a measure contains negative numbers—such as refunds, adjustments, or losses—the sum can be smaller than individual values or change sign. Shares can then be negative, greater than 1, or difficult to interpret as ordinary contribution percentages.

If you need gross sales revenue share, decide whether refunds/adjustments should be excluded from the denominator. If analyzing net revenue, negative values may need to remain. The formula can still compute, but business interpretation must account for the signs and total.

## 7. Practice Dataset for COUNT and Share

Create a transactions table with data across multiple regions, multiple products, a few NULL values, and a partition summing to 0:

```sql
CREATE TABLE lab_sales (
    sale_id    NUMBER(10)
        CONSTRAINT pk_lab_sales PRIMARY KEY,
    region_id  VARCHAR2(20),
    product_id NUMBER(10),
    sold_at    DATE,
    amount     NUMBER(12, 2)
);

INSERT INTO lab_sales VALUES
    (1, 'NORTH', 10, DATE '2026-01-01', 100);
INSERT INTO lab_sales VALUES
    (2, 'NORTH', 20, DATE '2026-01-01', 200);
INSERT INTO lab_sales VALUES
    (3, 'NORTH', 10, DATE '2026-01-02', 300);
INSERT INTO lab_sales VALUES
    (4, 'SOUTH', 10, DATE '2026-01-01', 150);
INSERT INTO lab_sales VALUES
    (5, 'SOUTH', 20, DATE '2026-01-03', 250);
INSERT INTO lab_sales VALUES
    (6, 'SOUTH', 20, DATE '2026-01-03', NULL);
INSERT INTO lab_sales VALUES
    (7, 'WEST', 30, DATE '2026-01-04', NULL);
INSERT INTO lab_sales VALUES
    (8, 'ZERO', 40, DATE '2026-01-05', 100);
INSERT INTO lab_sales VALUES
    (9, 'ZERO', 41, DATE '2026-01-06', -100);

COMMIT;
```

Meaningful data overview:

| SALE_ID | REGION_ID | PRODUCT_ID | AMOUNT |
| ---: | --- | ---: | ---: |
| 1 | NORTH | 10 | 100 |
| 2 | NORTH | 20 | 200 |
| 3 | NORTH | 10 | 300 |
| 4 | SOUTH | 10 | 150 |
| 5 | SOUTH | 20 | 250 |
| 6 | SOUTH | 20 | NULL |
| 7 | WEST | 30 | NULL |
| 8 | ZERO | 40 | 100 |
| 9 | ZERO | 41 | -100 |

Totals by region:

| REGION_ID | ROWS | NONNULL_AMOUNTS | REGION_TOTAL |
| --- | ---: | ---: | ---: |
| NORTH | 3 | 3 | 600 |
| SOUTH | 3 | 2 | 400 |
| WEST | 1 | 0 | NULL |
| ZERO | 2 | 2 | 0 |

Group WEST illustrates a partition with all NULL measures; group ZERO illustrates non-NULL values summing to 0. Both cases require explicit policies when computing shares.

To illustrate `COUNT` by department and job title, also create a small HR table:

```sql
CREATE TABLE lab_analysts (
    employee_id   NUMBER(10) PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    department_id NUMBER(10),
    job_id        VARCHAR2(20),
    hire_date     DATE
);

INSERT INTO lab_analysts VALUES
    (1, 'An', 10, 'DEV', DATE '2022-01-10');
INSERT INTO lab_analysts VALUES
    (2, 'Binh', 10, 'QA', DATE '2022-02-15');
INSERT INTO lab_analysts VALUES
    (3, 'Chi', 10, 'DEV', DATE '2023-03-01');
INSERT INTO lab_analysts VALUES
    (4, 'Dung', 20, 'QA', DATE '2021-05-20');
INSERT INTO lab_analysts VALUES
    (5, 'Ha', 20, 'QA', DATE '2024-06-01');
INSERT INTO lab_analysts VALUES
    (6, 'Lam', NULL, 'HR', DATE '2024-07-01');

COMMIT;
```

Department 10 has two DEV and one QA; department 20 has two QA; employee Lam has no department assigned yet.

## 8. Combining Analytic COUNT and RATIO_TO_REPORT

### 8.1. Transaction Report with Row Counts and Region Share

For partitions with nonzero totals:

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_row_count,
    COUNT(amount) OVER (
        PARTITION BY region_id
    ) AS region_nonnull_amount_count,
    SUM(amount) OVER (
        PARTITION BY region_id
    ) AS region_total,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share,
    ROUND(
        100 * RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS region_share_pct
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Result:

| SALE_ID | REGION_ID | AMOUNT | ROW_COUNT | NONNULL_COUNT | REGION_TOTAL | REGION_SHARE | REGION_SHARE_PCT |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | NORTH | 100 | 3 | 3 | 600 | 0.166667 | 16.67 |
| 2 | NORTH | 200 | 3 | 3 | 600 | 0.333333 | 33.33 |
| 3 | NORTH | 300 | 3 | 3 | 600 | 0.500000 | 50.00 |
| 4 | SOUTH | 150 | 3 | 2 | 400 | 0.375000 | 37.50 |
| 5 | SOUTH | 250 | 3 | 2 | 400 | 0.625000 | 62.50 |
| 6 | SOUTH | NULL | 3 | 2 | 400 | NULL | NULL |

Notes:

- `REGION_ROW_COUNT` counts every row in the region.
- `REGION_NONNULL_AMOUNT_COUNT` counts transactions that have an amount.
- `REGION_TOTAL` repeats the region total on each row.
- `REGION_SHARE` is the decimal ratio; multiply by 100 to display percentage.
- The row with NULL amount is retained, while its share is NULL.

### 8.2. Formatting Percentages for UI Display

There is no need to convert ratios to text if the consumer can format numbers. Keeping `NUMBER` is usually more convenient for downstream calculations. If a display string is needed in SQL:

```sql
SELECT
    sale_id,
    region_id,
    TO_CHAR(
        ROUND(
            100 * RATIO_TO_REPORT(amount) OVER (
                PARTITION BY region_id
            ),
            2
        ),
        'FM990D00',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) || '%' AS region_share_display
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

`TO_CHAR` turns `NUMBER` into `VARCHAR2`. If an API or Java tier needs to sort, sum, or compare ratios, return `NUMBER` values and format in the presentation layer. Explicit format models and NLS parameters keep display strings consistent across sessions.

### 8.3. Product Share Within Region After Aggregation

If the requirement is the share of **each product** within a region, first aggregate revenue by region and product, then apply `RATIO_TO_REPORT` over the aggregated totals:

```sql
WITH product_totals AS (
    SELECT
        region_id,
        product_id,
        SUM(amount) AS product_amount
    FROM lab_sales
    WHERE region_id IN ('NORTH', 'SOUTH')
      AND amount IS NOT NULL
    GROUP BY region_id, product_id
)
SELECT
    region_id,
    product_id,
    product_amount,
    RATIO_TO_REPORT(product_amount) OVER (
        PARTITION BY region_id
    ) AS product_share_in_region,
    ROUND(
        100 * RATIO_TO_REPORT(product_amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS product_share_pct
FROM product_totals
ORDER BY region_id, product_id;
```

In NORTH, product 10 has total 400 (100 + 300), and product 20 has total 200. The corresponding shares are 66.67% and 33.33%. This is an important example of choosing the right grain before computing ratios.

### 8.4. Group Share After GROUP BY vs. Per-Transaction Share

If you apply `RATIO_TO_REPORT` directly on individual transactions, the denominator is the transaction sum within the partition. If you want the share of **departments by job**, **products by region**, or **branches by month**, `GROUP BY` to that exact unit first.

Example counting employees by department and job title, then adding job type count and total headcount:

```sql
WITH job_counts AS (
    SELECT department_id,
           job_id,
           COUNT(*) AS employees_in_job
    FROM lab_analysts
    GROUP BY department_id, job_id
)
SELECT
    department_id,
    job_id,
    employees_in_job,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS job_types_in_department,
    SUM(employees_in_job) OVER (
        PARTITION BY department_id
    ) AS department_headcount,
    RATIO_TO_REPORT(employees_in_job) OVER (
        PARTITION BY department_id
    ) AS job_share_in_department
FROM job_counts
ORDER BY department_id, job_id;
```

In the outer query block, each row is a department-job combination. Therefore, analytic `COUNT(*)` counts **the number of job groups** in the department, whereas analytic `SUM(employees_in_job)` computes the department's total headcount. `RATIO_TO_REPORT` calculates the job's headcount share within the department.

## 9. Filtering Data While Preserving the Share Denominator

A crucial point is that `WHERE` filters rows **before** analytic functions are evaluated in the same query block. Thus, if you filter to a single product in a query containing `RATIO_TO_REPORT`, the denominator becomes only that product's total, no longer the original region total.

### 9.1. Filtering Before Analytic: The Denominator Changes

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS share_after_filter
FROM lab_sales
WHERE region_id = 'NORTH'
  AND product_id = 10
ORDER BY sale_id;
```

Because `WHERE` removes product 20 before the analytic function runs, the NORTH denominator in this query block is only product 10's total (400). The two transactions for product 10 receive shares of 25% and 75% respectively. This is the share within the **filtered set**, not each transaction's share across the entire region (16.67% and 50%).

### 9.2. Compute Share First, Filter Display Afterward

If you want to display only product 10 while computing shares across the entire region, use an inner query block:

```sql
WITH sales_with_share AS (
    SELECT
        sale_id,
        region_id,
        product_id,
        amount,
        RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ) AS share_in_region
    FROM lab_sales
    WHERE region_id = 'NORTH'
)
SELECT *
FROM sales_with_share
WHERE product_id = 10
ORDER BY sale_id;
```

Here the analytic function runs over all NORTH transactions first; the outer query only filters to product 10 rows. Shares remain 16.67% and 50% of the region total 600.

### 9.3. Top N While Keeping Share Over the Entire Group

Similarly, if a report displays only the top three revenue-generating products while shares must be computed over the entire region total:

```sql
WITH product_totals AS (
    SELECT region_id,
           product_id,
           SUM(amount) AS product_amount
    FROM lab_sales
    WHERE region_id IN ('NORTH', 'SOUTH')
    GROUP BY region_id, product_id
),
shares AS (
    SELECT
        region_id,
        product_id,
        product_amount,
        RATIO_TO_REPORT(product_amount) OVER (
            PARTITION BY region_id
        ) AS region_share,
        ROW_NUMBER() OVER (
            PARTITION BY region_id
            ORDER BY product_amount DESC, product_id
        ) AS rn
    FROM product_totals
)
SELECT region_id, product_id, product_amount, region_share
FROM shares
WHERE rn <= 3
ORDER BY region_id, rn;
```

`RATIO_TO_REPORT` and `ROW_NUMBER` are computed in the `shares` CTE over all products in each region. Only the outer query filters `rn <= 3`. If you filter top 3 before computing the ratio, shares will be re-divided over the top 3 sum, producing a different metric.

### 9.4. Why Can't Analytic Functions Be Used Directly in WHERE of the Same Query Block?

Do not write:

```sql
SELECT sale_id, region_id,
       COUNT(*) OVER (PARTITION BY region_id) AS region_count
FROM lab_sales
WHERE COUNT(*) OVER (PARTITION BY region_id) > 2;
```

Oracle does not allow placing an analytic function directly in the `WHERE` clause of the same query block. Compute it in a CTE/subquery and filter in the outer query:

```sql
WITH counted_sales AS (
    SELECT
        sale_id,
        region_id,
        COUNT(*) OVER (
            PARTITION BY region_id
        ) AS region_count
    FROM lab_sales
)
SELECT *
FROM counted_sales
WHERE region_count > 2
ORDER BY region_id, sale_id;
```

### 9.5. COUNT OVER for Pagination

An application may need to return one page of data while still knowing the total number of rows matching the filter:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER () AS total_matching_rows
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY sale_id
OFFSET 0 ROWS FETCH NEXT 3 ROWS ONLY;
```

`COUNT OVER` is computed on the query block's `WHERE`-matched row set before pagination limits with `OFFSET/FETCH`. Therefore, each row on the page carries the total number of rows matching the filter, not just the number of rows returned on that page. This is a useful pattern, though if the result has zero rows there is no row to carry a total count of 0; when an API needs a total count even on an empty page, a separate count query or a different response structure may be needed.

## 10. COUNT and RATIO_TO_REPORT After JOIN: Beware Fan-Out

Analytic functions do not know that a row multiplication is a business-logic bug. They compute over the **actual row set** produced after `FROM/JOIN/WHERE/GROUP BY/HAVING`.

Suppose an order has two line items. If you join orders with detail lines, `COUNT(*)` per order will be 2, not 1:

```sql
SELECT
    o.order_id,
    l.line_id,
    COUNT(*) OVER (
        PARTITION BY o.order_id
    ) AS rows_per_order
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

If you need to count distinct orders per customer after a join:

```sql
SELECT
    o.customer_id,
    o.order_id,
    l.line_id,
    COUNT(DISTINCT o.order_id) OVER (
        PARTITION BY o.customer_id
    ) AS distinct_orders_per_customer
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

`COUNT(DISTINCT ...) OVER(PARTITION BY ...)` can count unique orders in the partition while keeping line-item detail. Remember the Oracle restriction: analytic `DISTINCT` calls cannot include `ORDER BY` or a window frame.

If you need each order's share of customer revenue, but the query has joined with order lines, verify whether `AMOUNT` is at order grain or line grain. Summing a header amount column across every line multiplies the order's revenue by its line count. Aggregate to order grain first, or use a measure that genuinely belongs at line grain.

Correct pattern when order share of customer total is needed:

```sql
WITH order_totals AS (
    SELECT order_id,
           customer_id,
           SUM(line_amount) AS order_amount
    FROM order_lines
    GROUP BY order_id, customer_id
)
SELECT
    order_id,
    customer_id,
    order_amount,
    RATIO_TO_REPORT(order_amount) OVER (
        PARTITION BY customer_id
    ) AS customer_order_share
FROM order_totals;
```

Here each input row to `RATIO_TO_REPORT` is one aggregated order, so denominator and numerator are both at order grain.

## 11. Query Block Processing Order and Combining with GROUP BY

To understand analytic results, know what row set the query block produces before analytic functions execute. Conceptual model in Oracle:

1. `FROM` and `JOIN` determine data sources and matched rows.
2. `WHERE` filters input rows.
3. `GROUP BY` and aggregates collapse rows if present.
4. `HAVING` filters groups.
5. Analytic functions evaluate over the remaining row set of the query block.
6. `SELECT` returns expressions; the final `ORDER BY` sorts the displayed output.

Consequently:

- Analytic `COUNT` after a `JOIN` counts joined rows, even when a record was multiplied by a 1:N relationship.
- Analytic `COUNT` in a query with `GROUP BY` counts **grouped rows** after `GROUP BY`, not the original source rows.
- `WHERE` in the same query block alters the row set and denominator before `RATIO_TO_REPORT` runs.
- The final `ORDER BY` of the SQL statement does not replace `ORDER BY` inside `OVER`.

### 11.1. Analytic COUNT After GROUP BY Counts Groups

Example:

```sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employees_in_job,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS job_groups_in_department
FROM lab_analysts
GROUP BY department_id, job_id
ORDER BY department_id, job_id;
```

After `GROUP BY`, each row is a department-job pair. Analytic `COUNT(*)` therefore counts the number of job-title groups in each department. It does not count the number of employees in the department.

If you want total headcount per department, you can use:

```sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employees_in_job,
    SUM(COUNT(*)) OVER (
        PARTITION BY department_id
    ) AS department_headcount
FROM lab_analysts
GROUP BY department_id, job_id
ORDER BY department_id, job_id;
```

Here the inner `COUNT(*)` is the aggregate per department-job; `SUM(...) OVER` is the analytic function running over those grouped rows. Oracle allows using an aggregate as input to an analytic function in a query block after `GROUP BY`. This differs from nesting one analytic function inside another analytic function.

### 11.2. If You Need Analytic Evaluation First, Then Aggregation

Place the analytic function in a CTE/subquery first, then `GROUP BY` in the outer query:

```sql
WITH detail_counts AS (
    SELECT
        employee_id,
        department_id,
        COUNT(*) OVER (
            PARTITION BY department_id
        ) AS department_headcount
    FROM lab_analysts
)
SELECT
    department_id,
    MAX(department_headcount) AS department_headcount
FROM detail_counts
GROUP BY department_id
ORDER BY department_id;
```

This example intentionally illustrates two query blocks: the analytic function is computed on detail employees; the outer query collapses to one row per department. In practice, if you only need headcount, a simple `GROUP BY` is usually sufficient; there is no need to compute an analytic function and re-aggregate.

### 11.3. Do Not Nest Analytic Functions Directly

Do not pass one analytic function directly as an argument to another analytic function in the same expression:

```sql
-- Do not nest analytic functions like this:
SELECT
    RATIO_TO_REPORT(
        COUNT(*) OVER (PARTITION BY region_id)
    ) OVER ()
FROM lab_sales;
```

Split into separate query blocks if an analytic calculation needs the result of a previous analytic calculation:

```sql
WITH detail_counts AS (
    SELECT
        sale_id,
        region_id,
        COUNT(*) OVER (
            PARTITION BY region_id
        ) AS region_count
    FROM lab_sales
),
region_counts AS (
    SELECT DISTINCT region_id, region_count
    FROM detail_counts
)
SELECT
    region_id,
    region_count,
    RATIO_TO_REPORT(region_count) OVER () AS share_of_region_count_values
FROM region_counts;
```

The final example uses two query blocks to transition from per-row analytic results to one row per region before computing shares. `DISTINCT` in the second CTE ensures each region contributes only once to the denominator. In production systems, if the goal from the start is counting rows per region, direct `GROUP BY` is usually simpler than analytic `COUNT` followed by `DISTINCT`.

## 12. Rounding, Precision, and Presenting Shares

### 12.1. Keep Ratios as NUMBER While Still Computing

`RATIO_TO_REPORT` returns a numeric ratio, such as 0.25 corresponding to 25%. If further calculations are needed, keep the ratio as `NUMBER`:

```sql
RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id
) AS share_ratio
```

Multiply by 100 only when you want to display percentages:

```sql
100 * RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id
) AS share_percent
```

If using `ROUND`, round at the presentation step:

```sql
ROUND(
    100 * RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ),
    2
) AS share_percent_2dp
```

Do not round individual amounts before summing if financial requirements demand precision on original data. Do not sum rounded percentages for exact reconciliation; the displayed sum can be 99.99% or 100.01% due to per-row rounding.

### 12.2. Formatted Strings Are Not Numeric Values

`TO_CHAR` turns `NUMBER` into a string. A percentage string suits UI display, but is no longer convenient for arithmetic operations:

```sql
TO_CHAR(
    ROUND(100 * region_share, 2),
    'FM990D00',
    'NLS_NUMERIC_CHARACTERS=''.,'''
) || '%'
```

If the consuming system reads data over JDBC/REST, consider returning `NUMBER` and letting the UI layer format according to locale. If returning text is mandatory, explicitly define the decimal separator, digit count, and percent sign.

### 12.3. Negative Shares and Shares Exceeding 100%

If the partition total is positive while one measure is negative, that measure's ratio is negative. If the total is smaller than a single measure because other rows are negative, a positive row's ratio can exceed 100%. This is not necessarily an arithmetic bug; it reflects a denominator that includes negative values.

Do not force all shares into the 0–100% range using `LEAST/GREATEST` if doing so hides refunds, adjustments, or negative figures. Define clearly whether the metric is gross, net, or a total with exclusion rules.

## 13. Performance and Common Pitfalls

### 13.1. Analytic COUNT Still Requires Partition/Order Processing

`COUNT OVER(PARTITION BY ...)` typically requires Oracle to organize data by partition and may require a sort or memory operations depending on the execution plan. Adding `ORDER BY`/window frames can increase cost because ordering and window state must be maintained. Do not add unnecessary `PARTITION BY`/`ORDER BY` clauses to every expression.

Things to check:

- Number of input rows after `JOIN/WHERE`.
- Size and number of partitions.
- Sort behavior, PGA/TEMP usage, and access order.
- Optimizer statistics and actual rows.
- Whether data can be legitimately filtered by business rules before analytic evaluation.

### 13.2. RATIO_TO_REPORT Does Not Reduce Row Count

`RATIO_TO_REPORT` computes the denominator over the partition and attaches the share to every row. If a partition has one million rows, the query still processes all of those rows. If you only need product-level shares, aggregate to one row per product first to reduce grain and data volume.

### 13.3. Common Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Analytic COUNT is larger than expected | JOIN multiplied rows or query block has finer detail than desired grain | Count by appropriate key; fix join or pre-aggregate |
| COUNT(expr) is smaller than COUNT(*) | Some expr values are NULL | Use the COUNT form matching the data definition |
| Analytic COUNT is cumulative instead of group total | ORDER BY inside OVER with default frame | Remove ORDER BY if full partition is needed; or declare frame explicitly |
| Rows with same timestamp get same running count | Default RANGE groups peer rows | Use ROWS with a unique tie-breaker if row-by-row counting is needed |
| Analytic COUNT(DISTINCT) gives syntax error | ORDER BY/window frame included with DISTINCT | Use only PARTITION BY in DISTINCT calls |
| Shares do not add up to 100% | Viewing a subset of the group, NULLs, negative numbers, or rounding | Verify denominator and row set before analytic evaluation |
| Share is NULL | Measure is NULL or partition total is NULL | Check input data and NULL policy |
| Division by zero error | Partition total equals 0 | Guard denominator with CASE in an outer query block |
| Share changes after adding WHERE | WHERE filters before analytic evaluation | Compute analytic in a CTE first, then filter outside |
| Share is wrong after JOIN | Header measure multiplied by child row count | Pre-aggregate to the proper grain |
| Cannot use analytic function in WHERE | Analytic functions are evaluated after WHERE | Use CTE/subquery and filter in outer query |
| Sum of displayed percentages is 99.99% | Per-row rounding | Keep precision; round only for display |

### 13.4. Viewing the Execution Plan

Example of viewing the estimated plan:

```sql
EXPLAIN PLAN FOR
SELECT
    sale_id,
    region_id,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_count,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share
FROM lab_sales;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan. When you need to compare estimated rows against actual rows, collect runtime statistics in an authorized environment and inspect the cursor via `DBMS_XPLAN.DISPLAY_CURSOR` with an appropriate format (such as `ALLSTATS LAST`). Do not enable hints or query dynamic performance views on production without understanding their impact and required privileges.

## 14. Comprehensive Hands-On Lab

Exercises use the `lab_sales` and `lab_analysts` tables created in section 7. Run in a practice schema; if the tables already exist, use existing data or choose new names according to lab procedures.

### Part A — Comparing Aggregate and Analytic COUNT

Run both queries:

```sql
SELECT region_id, COUNT(*) AS sale_count
FROM lab_sales
GROUP BY region_id
ORDER BY region_id;

SELECT sale_id, region_id,
       COUNT(*) OVER (PARTITION BY region_id) AS region_count
FROM lab_sales
ORDER BY region_id, sale_id;
```

Answer:

1. Which query returns one row per region?
2. Which query keeps every transaction?
3. Why does analytic `COUNT` display 3 on all three NORTH rows?
4. For region WEST, what do `COUNT(*)` and `COUNT(amount)` return respectively?

### Part B — COUNT DISTINCT Within a Partition

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    COUNT(DISTINCT product_id) OVER (
        PARTITION BY region_id
    ) AS distinct_products
FROM lab_sales
ORDER BY region_id, sale_id;
```

Determine the number of distinct products in NORTH and SOUTH. Try adding `ORDER BY` to the `COUNT DISTINCT` call and explain why the syntax is restricted.

### Part C — Running Count and Peer Rows

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at
    ) AS range_count,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_count
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sold_at, sale_id;
```

Observe the two NORTH transactions on 2026-01-01. Explain why default `RANGE` gives the same count to peer rows while `ROWS` increments row by row using the tie-breaker order.

### Part D — Transaction Share Within a Region

```sql
SELECT
    sale_id,
    region_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS share_ratio,
    ROUND(
        100 * RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS share_percent
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Verify that NORTH shares sum to 1 and SOUTH shares sum to 1 when ignoring the NULL row. Manually calculate 100/600, 200/600, 300/600 and 150/400, 250/400.

### Part E — Partition Total Equal to 0

Run the guarded ratio query in section 6.2. Confirm that region ZERO returns NULL per the chosen policy without fabricating a fake share. Try replacing `CASE` with direct division to observe the error in the lab environment; skip if the tool or database in use does not allow error testing.

### Part F — Computing Share by Product

Run the `PRODUCT_TOTALS` CTE in section 8.3. Recalculate product revenue per region by hand and explain why `GROUP BY` is required before calling `RATIO_TO_REPORT`.

### Part G — Filtering After Computing Share

Run the two queries in sections 9.1 and 9.2. Why do the shares for product 10 in NORTH differ? Which result should you choose if the report hides other products while the denominator must remain the entire region?

### Part H — Headcount by Job Title

Run the `JOB_COUNTS` query in section 8.4. Verify:

- Department 10: DEV has 2 people, QA has 1 person; headcount is 3.
- Department 20: QA has 2 people; headcount is 2.
- Department NULL: HR has 1 person.

Explain why `COUNT(*) OVER` in the outer query counts job groups, while `SUM(employees_in_job) OVER` yields the department's total employees.

### Part I — COUNT OVER for Pagination

Run the pagination query in section 9.5. Try `OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY`. Does the total count of filter-matching rows change? What happens if `OFFSET` is large enough to produce an empty page?

## 15. Best-Practice Principles

1. **Determine the grain before calculating.** Is one row a transaction, an order line, an aggregated product, or a department?
2. **Choose the right COUNT.** `COUNT(*)` counts rows; `COUNT(expr)` ignores NULLs; `COUNT(DISTINCT expr)` counts distinct values.
3. **Only PARTITION BY the business group being measured.** Changing the partition key changes the denominator and meaning of the result.
4. **Do not add ORDER BY when only a group total is needed.** With analytic `COUNT`, `ORDER BY` can create a running count under the default frame.
5. **Declare ROWS and a tie-breaker when row-by-row ordering is needed.** Do not rely on incidental ordering among peer rows.
6. **Apply RATIO_TO_REPORT on a measure at the right grain.** Pre-aggregate first if shares are needed by product, order, or branch.
7. **Guard zero totals.** Choose NULL, 0, or N/A status per business rules; do not leave division undefined.
8. **Distinguish NULL from 0.** NULL may mean unrecorded, whereas 0 is a recorded value.
9. **Understand WHERE before analytic functions.** If you need to filter display rows while keeping a full-group denominator, compute in a CTE first and filter in the outer query.
10. **Do not compute over fanned-out data.** Check joins and pre-aggregate child tables if exactly one row per parent key is needed.
11. **Keep ratios as NUMBER while computing.** Only use `TO_CHAR` at presentation; round at the end.
12. **Read execution plans and measure real data.** `COUNT`/`RATIO_TO_REPORT` do not reduce row count and can still require sorting/partitioning on large datasets.

## 16. Self-Check Questions

1. How do `COUNT(*)` and `COUNT(expr)` differ when `expr` contains NULL?
2. How do `COUNT(*) OVER()` and `COUNT(*) GROUP BY region_id` differ in returned row count?
3. Into which groups does `PARTITION BY region_id, product_id` divide the dataset?
4. Why can analytic `COUNT` in a query with `GROUP BY` count job groups instead of employees?
5. What restrictions does `COUNT(DISTINCT expr) OVER` have regarding `ORDER BY` and window frames in Oracle?
6. When analytic `COUNT` has `ORDER BY` without a declared frame, what default frame type does Oracle use?
7. How do `RANGE` and `ROWS` differ when multiple rows share the same `ORDER BY` value?
8. Which denominator does `RATIO_TO_REPORT(amount) OVER(PARTITION BY region_id)` use?
9. If `amount` is NULL, what is that row's share?
10. If a partition total equals 0, why is a guard needed before division?
11. Why might the sum of rounded shares not equal exactly 100%?
12. Why does `WHERE product_id = 10` in the same query block alter `RATIO_TO_REPORT`'s denominator?
13. How do you display only the top 3 products while keeping shares calculated across all products?
14. Why can `COUNT(*) OVER` after a `JOIN` count more rows than the number of orders?
15. When shares by product within a region are needed, why should you aggregate by `region_id` and `product_id` first?
16. How is `COUNT OVER` useful in pagination queries? What limitation exists on an empty page?

## 17. Memory Model

```text
ANALYTIC COUNT
    │
    ├── COUNT(*)       → all rows
    ├── COUNT(expr)    → ignores NULL
    ├── COUNT(DISTINCT expr) → distinct values
    │
    ├── OVER()         → entire query block
    ├── PARTITION BY   → count within each group
    └── ORDER BY/frame → running count or sliding window

RATIO_TO_REPORT(expr)
    │
    ├── expr / SUM(expr) within partition
    ├── OVER()         → share of entire set
    ├── PARTITION BY   → share within group
    ├── NULL expr      → NULL share
    └── zero total     → needs policy/guard

FOR ACCURATE SHARES
    │
    ├── Choose the right grain
    ├── Check JOIN/fan-out
    ├── Compute analytics before display filtering
    ├── Keep NUMBER, round at presentation
    └── Use CTE/subquery when multiple stages are needed
```

**Key takeaway:** Analytic `COUNT` attaches counts to every row without collapsing details; `RATIO_TO_REPORT` shows how much each value contributes to its partition total. Results are accurate only when the input set, partition key, grain, and denominator match the business question. Handle NULLs and zero totals deliberately, avoid post-JOIN fan-out, and use an outer query block when you need to filter analytic results while preserving group-wide shares.
