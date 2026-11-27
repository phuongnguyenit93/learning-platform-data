# Structure of OVER, PARTITION BY, and ORDER BY

A window function performs a calculation across a set of rows related to the current row while still keeping each individual row in the result. This is the key difference from GROUP BY: GROUP BY collapses multiple rows into one row per group, whereas a window function attaches a computed value to each row without losing detail.

In MySQL, the OVER clause defines the window that the function observes. PARTITION BY splits data into independent groups; ORDER BY defines row ordering within each window; the frame clause (if present) restricts the specific subset of rows used for certain calculations.

This lesson is part of DATABASE_MYSQL: mastering analytical queries, ranking, running totals, and comparing related rows; understanding window scope, evaluation order, and performance impact to organize relational database reports and queries accurately.

## 1. Window functions and the role of OVER

A window function typically has the form:

~~~sql
window_function(expression) OVER (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY order_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
~~~

Components:

| Component | Role |
|---|---|
| Window function | Calculation such as ROW_NUMBER, RANK, SUM, AVG, LAG, or LEAD |
| OVER | Declares the window used for calculation |
| PARTITION BY | Splits rows into independent partitions |
| ORDER BY | Defines row ordering inside the window |
| Frame clause | Limits the rows participating in the calculation around the current row |

Example calculating total revenue per salesperson:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS salesperson_total
FROM sales_demo;
~~~

Each row still represents one transaction. The `salesperson_total` column repeats the corresponding salesperson's total revenue across every row for that salesperson.

The OVER clause is what specifies how the function views related rows. If OVER is omitted, SUM(amount) is a regular aggregate function and typically returns one row for the entire dataset (or one row per group if GROUP BY is used). With SUM(amount) OVER (...), the result is computed over a window while remaining attached to each row.

MySQL has supported window functions since MySQL 8.0. If an application still runs on MySQL 5.7, queries using OVER, PARTITION BY, or window functions will not work; you must upgrade or rewrite them using subqueries, self-joins, or other techniques.

## 2. Sample dataset for examples

Create the sales table:

~~~sql
CREATE TABLE sales_demo (
    sale_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    salesperson_id BIGINT UNSIGNED NOT NULL,
    region VARCHAR(30) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    KEY idx_sales_person_date (salesperson_id, sale_date, sale_id),
    KEY idx_sales_region_date (region, sale_date)
) ENGINE = InnoDB;

INSERT INTO sales_demo
    (sale_id, salesperson_id, region, sale_date, amount)
VALUES
    (1, 101, 'North', '2025-01-05', 100.00),
    (2, 101, 'North', '2025-01-06', 150.00),
    (3, 101, 'North', '2025-01-06', 150.00),
    (4, 101, 'North', '2025-01-09', 200.00),
    (5, 102, 'South', '2025-01-05',  80.00),
    (6, 102, 'South', '2025-01-07', 120.00),
    (7, 102, 'South', '2025-01-08', 120.00),
    (8, 102, 'South', '2025-01-10', 180.00),
    (9, 103, 'North', '2025-01-06', 150.00);
~~~

Two noteworthy points in the dataset:

- Salesperson 101 has two transactions on the same date, 2025-01-06, with the same amount of 150.
- The amount 150 also appears for salesperson 103.

These rows with duplicate sort values help illustrate the differences between PARTITION BY, ORDER BY, and RANGE/ROWS frames.

## 3. PARTITION BY: dividing the window into partitions

PARTITION BY divides the row set into partitions. The window function is evaluated separately within each partition and does not mix data across partitions.

Example calculating total revenue per salesperson:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS salesperson_total
FROM sales_demo
ORDER BY salesperson_id, sale_id;
~~~

Logical result:

| sale_id | salesperson_id | amount | salesperson_total |
|---:|---:|---:|---:|
| 1 | 101 | 100 | 600 |
| 2 | 101 | 150 | 600 |
| 3 | 101 | 150 | 600 |
| 4 | 101 | 200 | 600 |
| 5 | 102 | 80 | 500 |
| 6 | 102 | 120 | 500 |
| 7 | 102 | 120 | 500 |
| 8 | 102 | 180 | 500 |
| 9 | 103 | 150 | 150 |

Each salesperson_id forms a partition. The SUM function looks at all rows in that partition and returns the same total for every row belonging to that salesperson.

### 3.1. Without PARTITION BY

If PARTITION BY is omitted:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER () AS grand_total
FROM sales_demo
ORDER BY sale_id;
~~~

The entire result set is a single partition. Every row receives the total revenue across all transactions in the table, which equals 1,250.

An empty OVER() is still a valid window specification: no partitioning, no sorting, and no explicit frame restriction. For window aggregate functions, each row receives the aggregate across the entire row set of the query block.

### 3.2. Multi-column PARTITION BY

You can partition by multiple attributes:

~~~sql
SELECT
    sale_id,
    region,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY region, salesperson_id
    ) AS region_person_total
FROM sales_demo
ORDER BY region, salesperson_id, sale_id;
~~~

Each `(region, salesperson_id)` pair forms a partition. The order of expressions inside PARTITION BY does not change the equivalence grouping, though it should be ordered consistently with the schema for readability.

### 3.3. PARTITION BY with expressions

You can use expressions instead of bare columns:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY YEAR(sale_date)
    ) AS year_total
FROM sales_demo;
~~~

Rows sharing the same year are placed in the same partition. If an expression is complex or reused frequently, consider creating a generated column or precomputing the data to keep queries clearer.

### 3.4. NULL in PARTITION BY

If the partition expression evaluates to NULL, rows with NULL values are grouped together into a single partition. This aligns with partitioning semantics, though you should be careful if NULL represents multiple distinct business states.

If you need to separate NULLs from certain specific groups, you can use a CASE expression inside PARTITION BY to assign explicit partition labels. Only do this when business grouping rules genuinely require it.

## 4. ORDER BY inside OVER: calculation order

ORDER BY inside OVER determines the ordering of rows within each partition. This ordering matters for ranking functions, offset functions (previous/next row), and running aggregations.

Example numbering transactions by date within each salesperson:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS sale_sequence
FROM sales_demo
ORDER BY salesperson_id, sale_sequence;
~~~

For each salesperson_id, rows are ordered by sale_date ascending, then sale_id ascending. ROW_NUMBER assigns 1, 2, 3... within each partition.

### 4.1. Multi-column ORDER BY

When the first column has duplicate values, subsequent columns act as tie-breakers.

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date ASC, amount DESC, sale_id ASC
)
~~~

The ordering above means:
1. Earlier sale date comes first.
2. On the same date, larger amount comes first.
3. If still tied, smaller sale_id comes first.

If ORDER BY does not produce a unique ordering, tied rows may be numbered nondeterministically. When repeatable, stable results are needed, add a unique key or an appropriate tie-breaker.

### 4.2. ASC and DESC

By default, ORDER BY uses ASC. You can specify directions explicitly:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id ASC
    ) AS amount_position
FROM sales_demo;
~~~

Higher-amount orders are ranked first within each salesperson. `sale_id` distinguishes orders with the same amount.

### 4.3. ORDER BY inside OVER does not sort the final result

This is a critical distinction:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id
    ) AS amount_position
FROM sales_demo;
~~~

ORDER BY inside OVER only controls how ROW_NUMBER is computed. It does not guarantee the order of rows returned to the client.

To ensure the final output is sorted, you must add an outer ORDER BY:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id
    ) AS amount_position
FROM sales_demo
ORDER BY salesperson_id, amount_position;
~~~

A query can have both an ORDER BY inside OVER and an outer ORDER BY. The two clauses serve different purposes.

## 5. Distinguishing PARTITION BY from GROUP BY

PARTITION BY and GROUP BY both organize data by groups, but they produce different results.

### 5.1. GROUP BY collapses rows

~~~sql
SELECT
    salesperson_id,
    SUM(amount) AS total_amount
FROM sales_demo
GROUP BY salesperson_id;
~~~

The result has one row per salesperson_id. Individual transaction details no longer appear separately.

### 5.2. PARTITION BY preserves detail rows

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS total_amount
FROM sales_demo;
~~~

The result still has one row per transaction. The salesperson's total is appended to each row.

| Requirement | Approach |
|---|---|
| One row per group | GROUP BY |
| Keep row-level detail and add group metrics | Window function with PARTITION BY |
| Filter groups by aggregated values | HAVING or derived table/CTE |
| Filter rows by window function results | Derived table or CTE in an outer query block |

### 5.3. Combining GROUP BY and window functions

Window functions can run on the grouped result produced within the same query block:

~~~sql
SELECT
    region,
    salesperson_id,
    SUM(amount) AS revenue,
    RANK() OVER (
        PARTITION BY region
        ORDER BY SUM(amount) DESC
    ) AS region_rank
FROM sales_demo
GROUP BY region, salesperson_id
ORDER BY region, region_rank;
~~~

The query first produces one row per `(region, salesperson_id)` pair, calculating revenue. Then RANK ranks those aggregated rows within each region.

## 6. Ranking functions and the role of ORDER BY

Three commonly used functions:

- ROW_NUMBER(): numbers each row sequentially.
- RANK(): tied rows receive the same rank; subsequent ranks are skipped.
- DENSE_RANK(): tied rows receive the same rank; subsequent ranks are not skipped.

Example ranking amounts per salesperson:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS row_num,
    RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS dense_amount_rank
FROM sales_demo
ORDER BY salesperson_id, amount DESC, sale_id;
~~~

For salesperson 101, the amounts in descending order are 200, 150, 150, 100:

| amount | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 200 | 1 | 1 | 1 |
| 150 | 2 or 3 | 2 | 2 |
| 150 | 2 or 3 | 2 | 2 |
| 100 | 4 | 4 | 3 |

ROW_NUMBER distinguishes individual rows, so the order between the two 150 rows is nondeterministic without a tie-breaker. RANK and DENSE_RANK treat them as tied because their ORDER BY only considers amount.

If you add `sale_id` to RANK's ORDER BY, the two 150 transactions are no longer peers because the full sort key differs. Only add a tie-breaker to ROW_NUMBER when deterministic numbering is needed; do not add one to RANK if you want ties by amount to remain tied.

## 7. ORDER BY and peer rows

Rows are peers if they share the same values across all ORDER BY expressions of the window. Peer rows matter for RANK, DENSE_RANK, and RANGE frames.

Example:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS amount_rank
FROM sales_demo;
~~~

Two rows with equal `amount` in the same partition are peers and receive the same rank.

If ORDER BY contains multiple expressions, rows are only peers when all sort expressions evaluate equal under their respective comparison rules.

Do not confuse peer rows with two rows sharing just any single column. You must consider the entire ORDER BY list in the window specification.

## 8. Frame clause: restricting rows used in a calculation

PARTITION BY defines the broad group; ORDER BY defines the order; the frame clause specifies the exact set of rows around the current row used by certain window functions.

Two primary frame types:

- ROWS: defined by the physical number of rows before/after the current row in the window ordering.
- RANGE: defined by the value of the ORDER BY expression and corresponding peer groups.

General syntax:

~~~sql
ROWS | RANGE
    BETWEEN frame_start AND frame_end
~~~

Common boundaries:

| Boundary | Meaning |
|---|---|
| UNBOUNDED PRECEDING | Starts from the beginning of the partition |
| n PRECEDING | n rows or value interval before the current row, depending on ROWS/RANGE |
| CURRENT ROW | Current row; with RANGE, also involves peer rows |
| n FOLLOWING | n rows or value interval after the current row, depending on ROWS/RANGE |
| UNBOUNDED FOLLOWING | Ends at the end of the partition |

Example frame from the start of the partition to the current row:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Example window spanning two rows before, the current row, and two rows after:

~~~sql
ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
~~~

Frames are especially useful for SUM, AVG, COUNT, FIRST_VALUE, LAST_VALUE, and NTH_VALUE. Ranking functions such as ROW_NUMBER, RANK, and DENSE_RANK rely on partition/order and do not use frames the way aggregate or value functions do.

## 9. Default frames and the impact of ORDER BY

When no explicit frame is specified, MySQL applies a default frame. For a window with ORDER BY, the default frame is:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

If the window has no ORDER BY, the default frame is the entire partition:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

This can produce unexpected results when ORDER BY contains duplicate values.

### 9.1. Example of a running total with the default RANGE frame

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date
    ) AS running_total_default
FROM sales_demo
WHERE salesperson_id = 101
ORDER BY sale_date, sale_id;
~~~

Salesperson 101 has two transactions on the same `sale_date` 2025-01-06. Because the default frame is RANGE up to CURRENT ROW, both same-day rows are peers and are included in the same frame. As a result, both rows on 2025-01-06 receive the same running total, which includes both transactions from that day.

If you want to accumulate row by row in a distinct order, use ROWS and a deterministic ordering:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_rows
FROM sales_demo
WHERE salesperson_id = 101
ORDER BY sale_date, sale_id;
~~~

The row-by-row running totals for salesperson 101 are 100, 250, 400, and 600.

### 9.2. Why declare frames explicitly?

The default frame may match some reports, but it does not always align with business intent. If you need a row-by-row running total, specify ROWS explicitly. If you need to sum all peers sharing the same ORDER BY value, RANGE may be appropriate.

Declaring the frame explicitly helps:
- Readers see the exact set of rows included in the calculation.
- Prevent unintended result changes when columns are added to ORDER BY.
- Clarify how rows with duplicate sort values are handled.
- Reduce reliance on default frame behavior.

## 10. How do ROWS and RANGE differ?

Suppose we have transactions by date:

| sale_id | sale_date | amount |
|---:|---|---:|
| 1 | 2025-01-05 | 100 |
| 2 | 2025-01-06 | 150 |
| 3 | 2025-01-06 | 150 |
| 4 | 2025-01-09 | 200 |

Using ROWS:

~~~sql
SUM(amount) OVER (
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Each row is summed sequentially in a deterministic order. The second row has a total of 250, and the third row has a total of 400.

Using RANGE:

~~~sql
SUM(amount) OVER (
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Rows on the same date are peers. Both rows on 2025-01-06 see both transactions from that day, so both receive a total of 400.

| Frame Type | How it is defined | Impact on tied rows |
|---|---|---|
| ROWS | Physical row positions in window order | Each row has its own position if ORDER BY defines a deterministic order |
| RANGE | ORDER BY value and peer group | Peers can share the same frame |

With ROWS, add a unique tie-breaker if per-row results must be deterministic. With RANGE, do not add a tie-breaker column if the goal is to preserve peers by the business value being evaluated.

## 11. ORDER BY inside OVER with aggregate functions

Window aggregates allow computing sums, averages, counts, minimums, and maximums while keeping detail rows.

### 11.1. Full-partition total

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS person_total
FROM sales_demo;
~~~

Without ORDER BY, the default frame spans the entire partition. Each row receives the salesperson's total.

### 11.2. Running total

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

Each row receives the sum from the start of the partition up to the current row.

### 11.3. Three-transaction moving average

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_average_3_sales
FROM sales_demo;
~~~

The frame includes at most three rows: the two preceding transactions and the current transaction. At the start of the partition, the frame has fewer than three rows because there are not enough preceding rows.

### 11.4. Counting rows in a window

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    COUNT(*) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rows_in_window
FROM sales_demo;
~~~

`COUNT(*)` reports the actual number of rows in the frame. When counting a nullable column, `COUNT(column)` ignores NULL values within the frame.

## 12. FIRST_VALUE, LAST_VALUE, and NTH_VALUE

Value window functions retrieve a value from a specific position within the frame.

### 12.1. FIRST_VALUE

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS first_sale_amount
FROM sales_demo;
~~~

FIRST_VALUE returns the `amount` of the first row in the frame. With a frame starting at the beginning of the partition, the first value is the amount of the earliest transaction according to the declared order.

### 12.2. LAST_VALUE and the default frame trap

An easily misunderstood query:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS last_value_default
FROM sales_demo;
~~~

Because the default frame ends at CURRENT ROW, LAST_VALUE returns the `amount` of the current row (or the last row of the current frame), rather than the final transaction of the entire partition.

If you need the value from the last row of the entire partition, extend the frame to UNBOUNDED FOLLOWING:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_sale_amount
FROM sales_demo;
~~~

This is one of the major reasons to understand frames rather than looking only at PARTITION BY and ORDER BY.

### 12.3. NTH_VALUE

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    NTH_VALUE(amount, 2) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_sale_amount
FROM sales_demo;
~~~

NTH_VALUE retrieves the value at the Nth position within the frame. Positions are 1-based. If the frame does not contain enough rows, the result is NULL.

## 13. LAG and LEAD: accessing previous and next rows

LAG and LEAD use ORDER BY to locate the preceding or following row within the partition.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAG(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS next_amount
FROM sales_demo
ORDER BY salesperson_id, sale_date, sale_id;
~~~

- LAG(amount) retrieves the previous row's amount.
- LEAD(amount) retrieves the next row's amount.
- At the start or end of a partition, when no corresponding row exists, the default result is NULL.

You can specify an offset and a fallback value:

~~~sql
LAG(amount, 1, 0) OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
)
~~~

The second argument is the number of rows to look back; the third argument is the value returned when no preceding row exists. Do not use 0 if you need to preserve the distinction between "no prior transaction" (NULL) and an actual zero value.

LAG/LEAD depend on the ordering inside OVER. If ORDER BY is non-unique, determining the previous/next row may be nondeterministic. Add a tie-breaker if business logic requires a specific order.

## 14. Named windows: reusing OVER configurations

If multiple functions share the same PARTITION BY and ORDER BY, you can name the window in a WINDOW clause.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER w AS row_num,
    SUM(amount) OVER w AS running_total,
    AVG(amount) OVER w AS running_average
FROM sales_demo
WINDOW w AS (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY salesperson_id, sale_date, sale_id;
~~~

The configuration `w` is defined once and reused across multiple functions. This reduces duplication and ensures calculations share the same window specification.

The WINDOW clause appears after FROM/WHERE/GROUP BY/HAVING and before the final ORDER BY in MySQL's SELECT syntax.

A named window is neither a table nor a view; it is simply a name for a window specification scoped to a single SELECT statement. You cannot reference a window name in another statement.

## 15. Window functions and query evaluation order

Window functions are evaluated over the row set that has already passed the filtering and grouping steps of a query block. Therefore, they cannot be used directly inside WHERE, GROUP BY, or HAVING in the same query block.

Invalid example:

~~~sql
SELECT
    sale_id,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS row_num
FROM sales_demo
WHERE row_num <= 2;
~~~

The alias `row_num` does not exist when WHERE is evaluated, and window functions are not allowed directly in WHERE.

Wrap the result in a derived table:

~~~sql
SELECT
    ranked.sale_id,
    ranked.salesperson_id,
    ranked.sale_date,
    ranked.amount,
    ranked.row_num
FROM (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
        ) AS row_num
    FROM sales_demo
) AS ranked
WHERE ranked.row_num <= 2
ORDER BY ranked.salesperson_id, ranked.row_num;
~~~

Or use a CTE:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
        ) AS row_num
    FROM sales_demo
)
SELECT *
FROM ranked_sales
WHERE row_num <= 2
ORDER BY salesperson_id, row_num;
~~~

This is the standard top-N per group pattern: compute the rank in an inner query block, then filter by rank in an outer query block.

### 15.1. WHERE before window functions

If you write:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo
WHERE sale_date >= '2025-01-07';
~~~

Rows before 2025-01-07 are filtered out before the window function is evaluated. The running total starts from the first remaining row, excluding history prior to that date.

If business requirements call for computing the running total over the full history and only displaying rows from 2025-01-07 onward, compute the window in an inner query block and filter by date outside:

~~~sql
WITH all_running_sales AS (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        SUM(amount) OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM sales_demo
)
SELECT *
FROM all_running_sales
WHERE sale_date >= '2025-01-07'
ORDER BY salesperson_id, sale_date, sale_id;
~~~

Where you place the filter changes the analytical meaning. Decide whether to compute over the full history or only over the filtered subset.

## 16. NULL, data types, and ordering in windows

### 16.1. NULL in ORDER BY

In MySQL, when sorting:
- ASC: NULLs sort before non-NULL values.
- DESC: NULLs sort after non-NULL values.

If you need a specific placement, you can add an expression:

~~~sql
ORDER BY
    (event_time IS NULL),
    event_time ASC
~~~

The leading boolean expression pushes rows with NULL `event_time` to the end when sorting ascending (FALSE before TRUE). Use the same technique in ORDER BY inside OVER if the calculation order requires it.

### 16.2. NULL in window aggregates

SUM, AVG, MIN, and MAX ignore NULL values following standard aggregate rules. COUNT(expression) ignores NULLs, whereas COUNT(*) counts rows in the frame.

If all values in a frame are NULL, SUM/AVG/MIN/MAX return NULL. Do not automatically convert NULL to 0 if the business needs to distinguish "no data" from "a sum of 0".

### 16.3. Data types and precision

For monetary data, use DECIMAL instead of FLOAT/DOUBLE when exact decimal arithmetic is needed. Window SUM over DECIMAL preserves decimal semantics according to MySQL data type rules.

If ORDER BY operates on strings, collation determines comparison order. For Vietnamese or other localized text, choose a collation matching your requirements for case sensitivity, accents, and linguistic sorting.

## 17. Performance and indexes for window functions

Window functions may require MySQL to sort rows by PARTITION BY and ORDER BY. On large datasets, sorting or buffering intermediate results can consume significant CPU, memory, and I/O.

### 17.1. Indexing by partition and order

Example window:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

An index ordered as:

~~~sql
CREATE INDEX idx_sales_person_date
ON sales_demo (salesperson_id, sale_date, sale_id);
~~~

matches the structure of the partition key and order key. An index can help access data in a useful order, though it does not guarantee MySQL will eliminate every sort or materialization step. The optimizer also weighs filters, cardinality, covering indexes, joins, and overall cost.

### 17.2. Filtering data before window evaluation

If you only need to analyze a specific time range and business logic allows excluding history outside that range, place WHERE in the query block before the window function to reduce the row count.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS period_running_total
FROM sales_demo
WHERE sale_date >= '2025-01-01'
  AND sale_date <  '2025-02-01';
~~~

Do this only when the running total should be computed within that period alone. If you need a full-history running total filtered only for display, use a CTE/derived table as shown in the previous section.

### 17.3. Avoid creating indexes for every window combination

A single query may use multiple windows with different partition/order clauses. Creating an index for every combination can bloat storage and increase INSERT/UPDATE/DELETE overhead.

Instead:
- Identify frequently executed analytical queries.
- Find recurring PARTITION BY/ORDER BY combinations.
- Evaluate indexes for WHERE and JOIN predicates first.
- Use EXPLAIN to inspect access paths, sorts, and temporary operations.
- Benchmark using production-like data.

### 17.4. Inspecting execution plans

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

In MySQL 8.0+, you can use EXPLAIN ANALYZE to measure actual execution:

~~~sql
EXPLAIN ANALYZE
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

EXPLAIN ANALYZE actually executes the SELECT query. Run it in an appropriate environment, especially when the query scans large volumes of data.

## 18. Common mistakes

| Mistake or misconception | Cause | Resolution |
|---|---|---|
| Thinking PARTITION BY reduces row count | Confusing it with GROUP BY | Window functions preserve detail rows |
| Thinking ORDER BY in OVER sorts final output | Confusing calculation order with display order | Add an outer ORDER BY |
| ROW_NUMBER changes across runs | Non-unique ORDER BY | Add a deterministic tie-breaker |
| RANK no longer produces ties | Putting a unique key in RANK's ORDER BY | Sort only by the criteria defining ties |
| Running total jumps by peer group | Default RANGE frame with duplicate ORDER BY values | Use ROWS with deterministic ordering if row-by-row is needed |
| LAST_VALUE returns the current row's value | Default frame ends at CURRENT ROW | Extend frame to UNBOUNDED FOLLOWING |
| Window alias cannot be used in WHERE | Windows are evaluated after WHERE | Wrap in a derived table or CTE |
| Date filter resets the running total | WHERE removes history before window runs | Compute window in inner query block, filter outside |
| Query is slow due to large sort | Partition/order over many rows without suitable access path | Check EXPLAIN, filter validly, and evaluate indexes |
| Same function gives different results after adding ORDER BY | Default frame changes when ORDER BY is present | Declare the frame explicitly |
| OVER fails with syntax error on MySQL 5.7 | Version lacks window function support | Upgrade or rewrite the query |

## 19. Window specification design workflow

When writing a window function, answer these questions in sequence:

1. What entity does each output row represent?
2. Does the function need to see the entire result set or only a related group?
3. Which columns belong in PARTITION BY?
4. Should calculation order be ascending or descending?
5. Are there duplicate ORDER BY values?
6. Is a tie-breaker needed for deterministic row ordering?
7. Does the function need a frame? If so, ROWS or RANGE?
8. Does the default frame match the business intent?
9. Do you need to filter on the window result? If so, use an outer query block.
10. Should WHERE be placed before or after the window based on the calculation goal?
11. Can the specification be reused via a named window?
12. Do indexes and the execution plan meet data scale requirements?

## 20. Practice exercises

### Exercise 1: Total revenue per salesperson

Use `sales_demo` to compute `SUM(amount) OVER (PARTITION BY salesperson_id)`. Verify that the total repeats on each row without reducing the row count.

### Exercise 2: Grand total across the table

Omit PARTITION BY and compute `SUM(amount) OVER ()`. Compare the result with a standard `SELECT SUM(amount)`.

### Exercise 3: Ordering transactions

Use `ROW_NUMBER() OVER (PARTITION BY salesperson_id ORDER BY sale_date, sale_id)`. Try removing `sale_id` and observe why the order of two same-day transactions becomes nondeterministic.

### Exercise 4: Comparing RANK and DENSE_RANK

Rank `amount` descending within each salesperson. Include duplicate `amount` values and compare the rank gaps between RANK and DENSE_RANK.

### Exercise 5: Running totals with ROWS and RANGE

Compute `SUM(amount)` with the default frame, with ROWS, and with RANGE. Use data with two same-day transactions to explain why the results differ.

### Exercise 6: Moving average

Compute `AVG(amount)` over the three most recent transactions per salesperson using `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`. Verify that early rows in each partition have a frame shorter than three rows.

### Exercise 7: LAST_VALUE

Use `LAST_VALUE(amount)` with the default frame and with `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. Explain why declaring the frame is necessary to get the last value of the entire partition.

### Exercise 8: LAG and LEAD

Compute the previous and next transaction amounts per salesperson. Use COALESCE or the default value argument of LAG/LEAD if business rules require displaying 0, while distinguishing "no row" from an actual value of 0.

### Exercise 9: Top 2 transactions per salesperson

Compute ROW_NUMBER in a CTE or derived table, then filter `row_num <= 2` in an outer query. Try adding a salesperson with no transactions to evaluate results when combined with a LEFT JOIN.

### Exercise 10: Performance check

Create and drop the index `(salesperson_id, sale_date, sale_id)`. Compare EXPLAIN and EXPLAIN ANALYZE for the running total query. Record sort operations, row counts, and execution time.

## 21. Checklist before shipping window functions to production

- [ ] Server runs MySQL 8.0 or higher.
- [ ] Identified the required function and analytical goal.
- [ ] PARTITION BY reflects the exact business grouping.
- [ ] ORDER BY reflects the exact calculation order.
- [ ] Tie-breaker included if deterministic row-by-row ordering is needed.
- [ ] Distinguished ORDER BY inside OVER from the outer ORDER BY.
- [ ] Distinguished PARTITION BY from GROUP BY.
- [ ] Specified the frame clause and chose ROWS/RANGE accurately.
- [ ] Checked default frame behavior with and without ORDER BY.
- [ ] Handled tied rows (peer rows) intentionally.
- [ ] Accounted for NULLs in partitioning, ordering, and aggregates.
- [ ] Filtered window results in a derived table or CTE.
- [ ] Placed WHERE before/after the window according to the required historical scope.
- [ ] Considered named windows if multiple functions share the same specification.
- [ ] Inspected EXPLAIN and benchmarked on representative data.
- [ ] Tested edge cases: empty partitions, single-row partitions, multiple tied rows, and NULLs.

## 22. Conclusion

OVER defines the window that a window function uses for calculation. PARTITION BY divides data into independent groups while keeping individual rows; ORDER BY defines the processing order within each group. ORDER BY inside OVER does not guarantee the final result order, so an outer ORDER BY is required when the UI or report expects a specific display order.

The frame clause specifies the exact subset of rows around the current row. The default frame with ORDER BY is RANGE from the start of the partition to CURRENT ROW, meaning peer rows can receive the same cumulative result. When row-by-row calculation is needed, use ROWS with a tie-breaker in the ordering. To filter on window results, use a derived table or CTE; when tuning, inspect indexes and execution plans rather than assuming a window specification will always be executed in a fixed way.

## Official references

- [MySQL 8.4 Reference Manual – Window Functions](https://dev.mysql.com/doc/refman/8.4/en/window-functions.html)
- [MySQL 8.4 Reference Manual – Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – Window Function Frame Specification](https://dev.mysql.com/doc/refman/8.4/en/window-functions-frames.html)
- [MySQL 8.4 Reference Manual – Named Windows](https://dev.mysql.com/doc/refman/8.4/en/window-named-windows.html)
- [MySQL 8.4 Reference Manual – SELECT Statement](https://dev.mysql.com/doc/refman/8.4/en/select.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizing Window Functions](https://dev.mysql.com/doc/refman/8.4/en/window-function-optimization.html)
