# Distinguishing Aggregate Functions and Window Functions

This lesson is part of the **Window Functions** chapter of the `DATABASE_MYSQL` module. The module aims to help you master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Both aggregate functions and window functions can compute totals, averages, counts, or rankings, but they produce results at different levels of granularity.

After this lesson, you will be able to distinguish how `GROUP BY` collapses rows versus how `OVER()` preserves individual rows, understand `PARTITION BY`, `ORDER BY`, and window frames, use functions such as `ROW_NUMBER()`, `RANK()`, `LAG()`, and `LEAD()`, and filter window results using CTEs or subqueries.

## 1. Two ways to aggregate, two result shapes

Aggregate functions such as `SUM()`, `AVG()`, `COUNT()`, `MIN()`, and `MAX()` are commonly used with `GROUP BY`. MySQL groups rows that share the same grouping key into a single group and returns one row per group.

For example:

~~~sql
SELECT
    salesperson,
    SUM(amount) AS sales_total
FROM sales
GROUP BY salesperson;
~~~

If the table has 100,000 transactions across 20 salespeople, the result has at most 20 rows, with each row representing one salesperson.

Window functions can also use aggregate functions, but by placing the function before an `OVER()` clause:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_total
FROM sales;
~~~

This query still returns one row per transaction. The `salesperson_total` column is the total for the corresponding salesperson and is repeated across that salesperson's rows.

| Characteristic | Aggregate Function with GROUP BY | Window Function with OVER |
|---|---|---|
| Processing unit | Group of rows | Window of rows related to the current row |
| Result row count | Typically reduced to one row per group | Preserves the row count of the result set after FROM/WHERE/GROUP BY/HAVING |
| Grouping capability | GROUP BY | PARTITION BY |
| Ordering within calculation | Not a core function of GROUP BY | ORDER BY inside OVER |
| Running totals or sliding windows | Not directly on individual collapsed rows | Yes, via window frames |
| Typical example | Total revenue per salesperson | Salesperson's total revenue displayed on each transaction |

Key takeaway: `GROUP BY` produces one representative row per group; `OVER()` computes over a set of related rows while retaining the current row in the result set passed to the window function. If the query already used `GROUP BY`, those rows are the grouped rows.

## 2. Dataset used in this lesson

We use a `sales` table where each row represents one sales transaction.

| Column | Type | Meaning |
|---|---|---|
| `sale_id` | INT | Unique transaction ID |
| `salesperson` | VARCHAR(50) | Salesperson name |
| `sale_date` | DATE | Transaction date |
| `amount` | DECIMAL(12,2) | Transaction amount |

Create the table and sample data:

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_window_functions_lab;
USE mysql_window_functions_lab;

CREATE TABLE sales (
    sale_id INT NOT NULL PRIMARY KEY,
    salesperson VARCHAR(50) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales (sale_id, salesperson, sale_date, amount)
VALUES
    (1, 'An',   '2026-01-01', 100.00),
    (2, 'An',   '2026-01-02', 150.00),
    (3, 'An',   '2026-01-02',  50.00),
    (4, 'Binh', '2026-01-01', 200.00),
    (5, 'Binh', '2026-01-03', 100.00);
~~~

Expected totals per salesperson:

| Salesperson | Transaction Count | Total Revenue |
|---|---:|---:|
| An | 3 | 300.00 |
| Binh | 2 | 300.00 |

The dataset has two transactions for An on the same date, 2026-01-02. This is useful for observing the difference between `ROWS` and `RANGE` in a window frame.

## 3. Window function syntax

General structure:

~~~sql
window_function(expression)
OVER (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY sort_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
~~~

Main components:

- **Window function:** an aggregate function such as SUM/AVG/COUNT or a dedicated function such as ROW_NUMBER/RANK/LAG.
- **PARTITION BY:** divides the row set into independent partitions. The function is evaluated separately within each partition.
- **ORDER BY:** defines the row ordering used in the window calculation.
- **Window frame:** selects a specific range of rows around the current row within the partition. Frames are primarily meaningful for window aggregate functions and certain value functions.

Not every window function requires all parts. For instance, a grand total across the entire result set only needs:

~~~sql
SUM(amount) OVER ()
~~~

A per-salesperson total only needs PARTITION BY:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson
)
~~~

A running total requires adding ORDER BY and a frame:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

## 4. PARTITION BY: dividing the window into partitions

`PARTITION BY` splits rows into independent groups for the window function. It does not reduce the number of output rows like GROUP BY does.

Example:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_total,
    AVG(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_average,
    COUNT(*) OVER (
        PARTITION BY salesperson
    ) AS salesperson_sale_count
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Result:

| sale_id | salesperson | amount | salesperson_total | salesperson_average | salesperson_sale_count |
|---:|---|---:|---:|---:|---:|
| 1 | An | 100.00 | 300.00 | 100.00 | 3 |
| 2 | An | 150.00 | 300.00 | 100.00 | 3 |
| 3 | An | 50.00 | 300.00 | 100.00 | 3 |
| 4 | Binh | 200.00 | 300.00 | 150.00 | 2 |
| 5 | Binh | 100.00 | 300.00 | 150.00 | 2 |

Each salesperson is one partition:

- An has three rows, with a total of 300.
- Binh has two rows, with a total of 300.
- The total and average are repeated on each row belonging to that partition.

If you omit `PARTITION BY`, the entire row set becomes a single partition:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER () AS grand_total
FROM sales;
~~~

Every row will have `grand_total = 600.00`.

### Multiple columns in PARTITION BY

You can partition along multiple dimensions:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson, YEAR(sale_date)
)
~~~

Each partition corresponds to a combination of salesperson and year. Choose partitioning columns based on the business question—for example, total revenue per salesperson per year.

## 5. ORDER BY inside OVER vs. ORDER BY at the end of the query

There are two positions for ORDER BY, serving two different purposes:

- `ORDER BY` inside `OVER(...)` determines the ordering used by the window function for its calculation.
- `ORDER BY` at the end of the SELECT statement determines the display order of rows in the final result.

Example:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS sale_sequence
FROM sales
ORDER BY amount DESC, sale_id;
~~~

The ROW_NUMBER function numbers transactions by date and transaction ID within each salesperson. The final result, however, is displayed in descending order of amount.

Without an ORDER BY at the end of the query, MySQL does not guarantee the order of returned rows, even if OVER contains an ORDER BY.

### Using a tie-breaker key to handle duplicate values

If you only write:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson
    ORDER BY sale_date
)
~~~

An's two transactions on the same date may receive unstable ordering across executions. Add a tie-breaker column, usually the primary key:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
)
~~~

This rule is especially important when assigning sequence numbers, paginating, picking the first/last row, or computing running totals.

## 6. Aggregate functions can become window functions

Familiar aggregate functions can be used with OVER:

| Function | Without OVER | With OVER |
|---|---|---|
| `SUM()` | Sum of a group or entire set | Sum over the partition/frame for each row |
| `AVG()` | Average of a group or entire set | Average over the partition/frame for each row |
| `COUNT()` | Row count in a group or set | Row count in the partition/frame for each row |
| `MIN()` | Minimum value of a group/set | Minimum value over the partition/frame |
| `MAX()` | Maximum value of a group/set | Maximum value over the partition/frame |

Comparison examples:

~~~sql
-- One row per salesperson
SELECT
    salesperson,
    SUM(amount) AS total_amount
FROM sales
GROUP BY salesperson;
~~~

~~~sql
-- One row per transaction, along with the salesperson's total
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS total_amount
FROM sales;
~~~

Both forms can be combined in a multi-stage query. For example, first compute revenue per salesperson using GROUP BY, then use a window function to calculate total company revenue across those grouped rows:

~~~sql
WITH salesperson_totals AS (
    SELECT
        salesperson,
        SUM(amount) AS salesperson_total
    FROM sales
    GROUP BY salesperson
)
SELECT
    salesperson,
    salesperson_total,
    SUM(salesperson_total) OVER () AS company_total,
    salesperson_total
        / NULLIF(SUM(salesperson_total) OVER (), 0) AS revenue_share
FROM salesperson_totals;
~~~

The result has two rows, one per salesperson, along with the company's total revenue and each salesperson's revenue share.

## 7. Window frame: selecting the rows included in the calculation

A partition can contain many rows, but sometimes a function only needs to look at a subset of the partition around the current row. That subset is called a **window frame**.

A frame is defined using `ROWS` or `RANGE` along with start and end boundaries.

Commonly used boundaries:

| Boundary | Meaning |
|---|---|
| `UNBOUNDED PRECEDING` | From the start of the partition |
| `n PRECEDING` | Back n rows or values depending on frame type |
| `CURRENT ROW` | The current row and corresponding peers depending on frame type |
| `n FOLLOWING` | Forward n rows or values depending on frame type |
| `UNBOUNDED FOLLOWING` | To the end of the partition |

Example of a frame from the start of the partition to the current row:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Example of a window consisting of the current row and the two preceding rows:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Example of the entire partition:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

### How do ROWS and RANGE differ?

- `ROWS` defines the frame by physical row position in the window ordering.
- `RANGE` defines the frame by the value of the ORDER BY expression and groups peer rows that have the same sort value.

In our sample dataset, An has two transactions on the same date, 2026-01-02. If you use RANGE and only ORDER BY sale_date, the two same-day transactions are peers and can receive the same running total. If you use ROWS with an ordering that includes the tie-breaker `sale_id`, each transaction is calculated sequentially.

### Running total using ROWS

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Result:

| sale_id | salesperson | sale_date | amount | running_total |
|---:|---|---|---:|---:|
| 1 | An | 2026-01-01 | 100.00 | 100.00 |
| 2 | An | 2026-01-02 | 150.00 | 250.00 |
| 3 | An | 2026-01-02 | 50.00 | 300.00 |
| 4 | Binh | 2026-01-01 | 200.00 | 200.00 |
| 5 | Binh | 2026-01-03 | 100.00 | 300.00 |

### Difference from the default RANGE frame

When ORDER BY is specified without an explicit frame, MySQL uses a default frame equivalent to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

When ORDER BY is omitted from the window definition, the default frame covers the entire partition. Therefore, `SUM(amount) OVER (PARTITION BY salesperson)` returns the sum of all rows belonging to that salesperson.

With the default frame when ORDER BY is present, peer rows sharing the same ORDER BY value are included together. On the sample data, the query:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date
    ) AS default_running_total
FROM sales
WHERE salesperson = 'An'
ORDER BY sale_date, sale_id;
~~~

produces the result:

| sale_id | sale_date | amount | default_running_total |
|---:|---|---:|---:|
| 1 | 2026-01-01 | 100.00 | 100.00 |
| 2 | 2026-01-02 | 150.00 | 300.00 |
| 3 | 2026-01-02 | 50.00 | 300.00 |

The two transactions on the same day are summed together because they are peers under `ORDER BY sale_date`.

When you need a row-by-row running total, explicitly specify `ROWS` and add a unique tie-breaker key to ORDER BY. This makes both the frame and the processing order unambiguous.

## 8. Sliding windows: averaging the most recent rows

A window frame can restrict the calculation to a fixed number of rows before and after the current row.

Example calculating the average of the current transaction and the immediately preceding transaction for the same salesperson:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS moving_average_2_sales
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

For An:

- Transaction 1: average of 100 is 100.
- Transaction 2: average of 100 and 150 is 125.
- Transaction 3: average of 150 and 50 is 100.

For Binh:

- Transaction 4: 200.
- Transaction 5: average of 200 and 100 is 150.

The frame `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW` contains at most two rows. At the start of a partition, when there are not enough preceding rows, the frame contains only the available rows.

This is a useful pattern for moving averages, rolling sums, recent transaction counts, and many time-series calculations.

## 9. Dedicated window functions

Not all window functions are aggregate functions. MySQL provides dedicated functions for numbering, ranking, bucketing, or accessing neighboring rows.

### ROW_NUMBER(): numbering individual rows

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num
FROM sales
ORDER BY salesperson, row_num;
~~~

ROW_NUMBER assigns a unique sequential number within each partition. If two rows have the same ORDER BY value, add a tie-breaker key for deterministic ordering.

### RANK() and DENSE_RANK(): ranking with ties

Three functions are commonly compared:

| Function | When two rows are tied |
|---|---|
| `ROW_NUMBER()` | Still assigns distinct numbers to each row |
| `RANK()` | Assigns the same rank and skips subsequent rank numbers |
| `DENSE_RANK()` | Assigns the same rank without skipping subsequent rank numbers |

Example:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        amount,
        RANK() OVER (ORDER BY amount DESC) AS amount_rank,
        DENSE_RANK() OVER (ORDER BY amount DESC) AS dense_amount_rank,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT *
FROM ranked_sales
ORDER BY amount_rank, sale_id;
~~~

If two transactions both have an amount of 100:

- RANK returns ranks 3 and 3, with the next rank being 5.
- DENSE_RANK returns ranks 3 and 3, with the next rank being 4.
- ROW_NUMBER still assigns distinct numbers according to the specified order.

Do not add a tie-breaker key to the ORDER BY of RANK if you want equal amount values to tie. If you add `sale_id`, the rows will no longer be peers across the full sort list.

### NTILE(): dividing rows into roughly equal buckets

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    NTILE(3) OVER (
        ORDER BY amount DESC, sale_id
    ) AS sales_bucket
FROM sales;
~~~

NTILE(3) splits the rows into three buckets according to the ordering. If the row count is not evenly divisible by the number of buckets, the earlier buckets receive one extra row. This is a simple way to create quantiles, though you should specify the partition scope explicitly if you want to bucket separately per salesperson.

### LAG() and LEAD(): reading previous and next rows

`LAG()` retrieves a value from a preceding row in the window order; `LEAD()` retrieves a value from a following row.

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    LAG(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS next_amount
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

You can specify an offset and a default value:

~~~sql
LAG(amount, 1, 0) OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
)
~~~

If there is no preceding row, the expression above returns 0. If no default value is specified, the result is NULL.

Use LAG/LEAD to compute:

- Revenue change compared to the previous transaction.
- Ending balance comparison against the prior period.
- State change detection.
- Time-series data reconciliation.

Example of the difference from the previous transaction:

~~~sql
WITH sales_with_previous AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        LAG(amount) OVER (
            PARTITION BY salesperson
            ORDER BY sale_date, sale_id
        ) AS previous_amount
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    amount,
    previous_amount,
    amount - previous_amount AS amount_change
FROM sales_with_previous
ORDER BY salesperson, sale_date, sale_id;
~~~

The first row for each salesperson has `previous_amount = NULL` because there is no preceding transaction.

### FIRST_VALUE() and LAST_VALUE()

`FIRST_VALUE()` returns the value from the first row of the frame; `LAST_VALUE()` returns the value from the last row of the frame.

Example retrieving the first and last transaction across the entire partition:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_sale_amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_sale_amount
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Important note: if you use LAST_VALUE with the default frame ending at CURRENT ROW, the last value in the frame is typically the current row itself. Therefore, when you want the last value across the entire partition, extend the frame to `UNBOUNDED FOLLOWING`.

## 10. Named windows: reusing window definitions

If multiple functions share the same PARTITION BY and ORDER BY, you can name the window using the WINDOW clause:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER w AS running_total,
    AVG(amount) OVER w AS running_average,
    COUNT(*) OVER (
        PARTITION BY salesperson
    ) AS salesperson_count
FROM sales
WINDOW w AS (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY salesperson, sale_date, sale_id;
~~~

Named windows help avoid repeating definitions and reduce the chance of functions accidentally using different orderings or partitions.

In MySQL's SELECT syntax, the WINDOW clause appears after HAVING (if present) and before ORDER BY.

## 11. Combining GROUP BY and window functions

Window functions can operate on the row set produced by GROUP BY. This is useful when you need a grouped report and then want to compare groups against a grand total or rank the groups.

For example, compute totals per salesperson and then rank them:

~~~sql
WITH salesperson_totals AS (
    SELECT
        salesperson,
        SUM(amount) AS total_amount
    FROM sales
    GROUP BY salesperson
)
SELECT
    salesperson,
    total_amount,
    RANK() OVER (
        ORDER BY total_amount DESC
    ) AS revenue_rank,
    SUM(total_amount) OVER () AS company_total
FROM salesperson_totals
ORDER BY revenue_rank, salesperson;
~~~

The result has only one row per salesperson. The CTE produces the aggregated data; the window functions compute the rank and company total across those rows.

You can think of this as two layers:

1. GROUP BY defines the report grain and produces per-salesperson metrics.
2. Window functions add comparative metrics across the report rows.

Do not include ungrouped detail columns in SELECT if they are invalid under GROUP BY rules and the active SQL mode.

## 12. Why can't you filter directly by a window function in WHERE?

Window functions are evaluated after the FROM, WHERE, GROUP BY, and HAVING steps of a query. Therefore, window aliases or expressions are not yet available when WHERE is evaluated.

The following query is invalid:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num
FROM sales
WHERE row_num = 1;
~~~

To retrieve the highest-amount transaction per salesperson, wrap the window query in a CTE:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM ranked_sales
WHERE row_num = 1
ORDER BY salesperson;
~~~

Or use a derived table:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
) AS ranked_sales
WHERE row_num = 1;
~~~

This pattern is commonly used to:

- Retrieve the top 1 or top N per group.
- Retrieve the latest record per customer.
- Deduplicate records according to priority rules.
- Filter rows whose rank or running total meets a condition.

MySQL does not provide a QUALIFY clause in standard SELECT syntax; use a CTE or subquery to filter window results.

## 13. MySQL limitations and caveats

Key points to remember when using window functions in MySQL:

- Window functions are available in MySQL starting in version 8.0. Check the server version if queries run on legacy systems.
- Window functions are allowed in the SELECT list and ORDER BY; they cannot be used directly in WHERE, GROUP BY, HAVING, or ON.
- Do not nest a window function directly inside another window function.
- MySQL does not support the DISTINCT keyword for aggregate functions used as window functions, such as `COUNT(DISTINCT customer_id) OVER (...)`.
- ORDER BY inside OVER does not replace the final query's ORDER BY.
- If the ordering is non-unique, the results of ROW_NUMBER and order-dependent calculations may be nondeterministic.
- The default window frame can affect results when ORDER BY contains duplicate values.
- A window function may require sorting or buffering many rows; do not assume it is always faster than GROUP BY or subqueries.

If you need to count distinct customers within a partition, consider pre-aggregating by customer key, using a subquery/CTE, or choosing another suitable design. Do not write `DISTINCT ... OVER` syntax, which MySQL does not support.

## 14. Performance checks

Window functions may require MySQL to sort data by PARTITION BY and ORDER BY. On large tables, the cost of sorting, memory, and temporary tables can be significant.

Checklist for verification:

1. Select only the necessary columns in the query.
2. Filter input data with WHERE before window evaluation if business logic allows it.
3. Specify PARTITION BY and ORDER BY cleanly, avoiding redundant sorts.
4. Consider indexes matching filter, partition, and sort columns.
5. Use EXPLAIN to inspect the execution plan.
6. On supported versions, use EXPLAIN ANALYZE to observe actual execution time and row counts.
7. Compare against GROUP BY or subqueries on the same data and under the same conditions.

Example:

~~~sql
EXPLAIN
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
WHERE sale_date >= '2026-01-01';
~~~

An index to consider for the query above:

~~~sql
CREATE INDEX idx_sales_date_person
ON sales (sale_date, salesperson, sale_id);
~~~

Or for queries that primarily partition by salesperson and sort by date:

~~~sql
CREATE INDEX idx_sales_person_date
ON sales (salesperson, sale_date, sale_id);
~~~

There is no single optimal index order for every query. The right index depends on filter predicates, access order, selectivity, and the optimizer's plan. Inspect EXPLAIN and benchmark on representative data before keeping an index.

## 15. Hands-on lab

Use the lab database created in section 2.

### Step 1: compare GROUP BY and OVER

Run:

~~~sql
SELECT
    salesperson,
    SUM(amount) AS total_amount
FROM sales
GROUP BY salesperson;
~~~

Then run:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS total_amount
FROM sales
ORDER BY salesperson, sale_id;
~~~

Note the row counts of both results and explain why one query returns two rows while the other returns five rows.

### Step 2: compute a running total

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Verify that An's running totals are 100, 250, and 300 respectively.

### Step 3: compare ROWS and RANGE

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_total,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_total
FROM sales
WHERE salesperson = 'An'
ORDER BY sale_date, sale_id;
~~~

Explain why two transactions on the same day can have the same `range_total` but different `rows_total`.

### Step 4: rank transactions

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC
    ) AS dense_amount_rank
FROM sales
ORDER BY salesperson, amount_rank, sale_id;
~~~

Compare the three rank columns and explain how ties are handled.

### Step 5: compare with the previous transaction

~~~sql
WITH sales_delta AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        LAG(amount) OVER (
            PARTITION BY salesperson
            ORDER BY sale_date, sale_id
        ) AS previous_amount
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    previous_amount,
    amount - previous_amount AS amount_change
FROM sales_delta
ORDER BY salesperson, sale_date, sale_id;
~~~

Identify the first transaction for each salesperson and explain why it has no previous value.

### Step 6: get the largest transaction per salesperson

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM ranked_sales
WHERE row_num = 1
ORDER BY salesperson;
~~~

Try replacing ROW_NUMBER with RANK if you want to return all tied highest transactions.

### Step 7: cleanup

~~~sql
DROP DATABASE mysql_window_functions_lab;
~~~

Run this only on the lab database just created. This command deletes all practice tables and data.

## 16. Common issues and troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| Result has only one row per group | Used GROUP BY so rows were collapsed | Use a window function if row-level detail must be preserved |
| Running total jumps across multiple same-day rows | Default RANGE frame groups peer rows | Use ROWS and add a unique tie-breaker key to ORDER BY |
| ROW_NUMBER changes between executions | ORDER BY does not define a unique order | Add primary key or tie-breaker column |
| Window alias cannot be used in WHERE | Window functions are evaluated after WHERE | Wrap the query in a CTE or derived table |
| LAST_VALUE returns the current row's value | Default frame ends at CURRENT ROW | Extend frame to UNBOUNDED FOLLOWING if partition end is needed |
| RANK skips rank numbers | Multiple rows are tied | Use DENSE_RANK if consecutive ranks are desired |
| COUNT(DISTINCT ...) OVER fails with error | MySQL does not support DISTINCT in window aggregates | Aggregate separately or use an appropriate subquery |
| Window total repeats across all rows | Missing PARTITION BY or frame spans the partition | Verify the intended window scope |
| Query slows down after adding OVER | Sorting or frame processing on a large row set | Filter appropriately, check indexes and EXPLAIN |
| Display order does not match OVER ordering | ORDER BY inside OVER only controls calculation | Add ORDER BY at the end of SELECT |

## 17. Checklist before using window functions

- [ ] Determined whether one row per group or individual detail rows are needed.
- [ ] Chose GROUP BY or OVER according to the target result grain.
- [ ] Determined whether PARTITION BY is necessary.
- [ ] Specified ORDER BY inside OVER when the calculation depends on order.
- [ ] Added a tie-breaker key to handle duplicate ORDER BY values.
- [ ] Chosen ROWS or RANGE to match the intended frame semantics.
- [ ] Checked default frame behavior when using ORDER BY.
- [ ] Distinguished ORDER BY inside OVER from the final query's ORDER BY.
- [ ] Used a CTE or derived table if filtering on window results is needed.
- [ ] Checked NULL behavior for aggregate functions and LAG/LEAD.
- [ ] Avoided DISTINCT inside window aggregates in MySQL.
- [ ] Evaluated sort, temporary table, and index costs.
- [ ] Tested with duplicate values, empty partitions, or single-row partitions.

## 18. Key principles to remember

1. Aggregate functions with GROUP BY collapse rows to the group grain.
2. Window functions with OVER compute over related rows while keeping each input row entering the SELECT step.
3. PARTITION BY divides the window into independent partitions.
4. ORDER BY inside OVER defines calculation order, not guaranteed display order.
5. A window frame defines which rows participate in the calculation around the current row.
6. ROWS operates by row position; RANGE evaluates values and peers according to ORDER BY.
7. When a row-by-row running total is needed, specify ROWS and a unique ordering.
8. ROW_NUMBER numbers each row individually; RANK and DENSE_RANK handle ties differently.
9. LAG/LEAD access preceding/following rows without needing a self-join.
10. Use a CTE or subquery to filter window function results.
11. MySQL does not support DISTINCT in window aggregates.
12. Inspect execution plans and performance on representative data.

## Official references

The syntax and behavior in this lesson are verified against the **MySQL 9.7 Reference Manual** as of **2026-11-19**:

1. [Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/9.7/en/window-functions-usage.html): OVER, PARTITION BY, ORDER BY, and frame syntax.
2. [Window Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/window-function-descriptions.html): ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, FIRST_VALUE, and dedicated functions.
3. [Window Function Frame Specification](https://dev.mysql.com/doc/refman/9.7/en/window-functions-frames.html): ROWS, RANGE, default frames, and peer rows.
4. [Aggregate Functions](https://dev.mysql.com/doc/refman/9.7/en/aggregate-functions.html): how aggregate functions work and how to use them as window functions.
5. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): placement of WINDOW, ORDER BY, and query clauses.
6. [Common Table Expressions](https://dev.mysql.com/doc/refman/9.7/en/with.html): using CTEs to process window function results in outer queries.
7. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): inspecting execution plans and query performance.
