# Running SUM/AVG and Moving Averages

Window functions let you compute sums, averages, or other metrics over a set of related rows while preserving each individual row in the result. With `SUM() OVER (...)` and `AVG() OVER (...)`, you can calculate running totals over time, running averages, or moving averages over the most recent transactions. Unlike `GROUP BY`, window calculations do not collapse multiple rows into one representative row.

Results depend on three key components: `PARTITION BY` splits data into independent groups, `ORDER BY` defines the processing order, and the frame defines which rows are included in the calculation for the current row. Understanding `ROWS` and `RANGE` prevents bugs when multiple records share the same timestamp or when averages must span calendar days.

In the `DATABASE_MYSQL` module, these techniques are widely used for account balances, cumulative revenue, goal progress, periodic metrics, and operational dashboards. This lesson uses MySQL 8.0 or higher.

## Objectives

After this lesson, you will be able to:

- Distinguish standard aggregates from aggregate window functions.
- Use `PARTITION BY` and `ORDER BY` to compute metrics separately per account or group.
- Write running totals using `SUM() OVER (...)`.
- Write running averages and moving averages using `AVG() OVER (...)`.
- Choose `ROWS` or `RANGE` frames matching business requirements.
- Handle rows with identical sort values, `NULL`s, and non-contiguous time intervals.
- Understand the impact of filtering before vs. after window evaluation.
- Inspect execution plans and choose suitable indexes for window queries.

## 1. Standard aggregates vs. aggregate window functions

`SUM(amount)` in a standard aggregate query returns a single value for the entire set or for each `GROUP BY` group:

```sql
SELECT account_id, SUM(amount) AS total_amount
FROM account_txn
GROUP BY account_id;
```

The result has only one row per account. If you want to keep each transaction and display the cumulative total after every transaction, use a window function:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn;
```

Each transaction remains a row in the result; `running_total` is computed over a frame that changes with the current row's position.

### 1.1. Basic structure

```sql
aggregate_function(expression) OVER (
    PARTITION BY partition_expression
    ORDER BY sort_expression
    frame_clause
)
```

- `PARTITION BY`: splits rows into independent partitions. When the partition value changes, the calculation restarts.
- `ORDER BY`: defines row ordering within each partition.
- `frame_clause`: defines the subset of the partition used to compute for the current row.

`PARTITION BY` and `ORDER BY` can take one or more expressions. If `PARTITION BY` is omitted, the entire result belongs to a single partition. If `ORDER BY` is omitted, a window aggregate without an explicit frame computes over the entire partition.

### 1.2. ORDER BY inside OVER vs. query-level ORDER BY

`ORDER BY` inside `OVER(...)` controls calculation order, not the order of rows returned to the client. To display output chronologically, add an `ORDER BY` at the end of the statement:

```sql
SELECT
    account_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

## 2. Sample dataset for practice

The transaction table stores account ID, timestamp, and amount. `amount` allows `NULL` to represent a transaction whose monetary value has not yet been recorded.

```sql
CREATE TABLE account_txn (
    txn_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    txn_at DATETIME(6) NOT NULL,
    amount DECIMAL(12, 2) NULL,
    txn_note VARCHAR(100) NULL,
    PRIMARY KEY (txn_id),
    KEY idx_account_txn_time (account_id, txn_at, txn_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO account_txn (account_id, txn_at, amount, txn_note)
VALUES
    (10, '2026-01-01 09:00:00', 100.00, 'Opening'),
    (10, '2026-01-02 09:00:00',  50.00, 'Deposit A'),
    (10, '2026-01-02 09:00:00',  25.00, 'Deposit B'),
    (10, '2026-01-03 09:00:00',   NULL, 'Pending amount'),
    (10, '2026-01-04 09:00:00', -20.00, 'Adjustment'),
    (20, '2026-01-01 10:00:00', 200.00, 'Opening'),
    (20, '2026-01-03 10:00:00', 100.00, 'Deposit'),
    (20, '2026-01-04 10:00:00',  50.00, 'Deposit'),
    (20, '2026-01-05 10:00:00',   0.00, 'Zero-value event');
```

Account 10 has two transactions at the exact same timestamp on 2026-01-02. This is a critical case for distinguishing row-based frames from sort-value-based frames. Account 20 has a day with no transactions; this helps distinguish averages over existing rows from calendar-day averages.

## 3. Running total

The running total at a row is the sum of values from the beginning of the partition up to the current row in the chosen order.

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

Expected output:

| account_id | txn_id | amount | running_total |
|---:|---:|---:|---:|
| 10 | 1 | 100.00 | 100.00 |
| 10 | 2 | 50.00 | 150.00 |
| 10 | 3 | 25.00 | 175.00 |
| 10 | 4 | `NULL` | 175.00 |
| 10 | 5 | -20.00 | 155.00 |
| 20 | 6 | 200.00 | 200.00 |
| 20 | 7 | 100.00 | 300.00 |
| 20 | 8 | 50.00 | 350.00 |
| 20 | 9 | 0.00 | 350.00 |

### 3.1. Meaning of the UNBOUNDED PRECEDING frame

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

The frame starts at the first row of the partition and ends at the current row. Moving to the next row expands the frame to include that row. When `account_id` changes, a new partition begins and the running total resets.

If you need a system-wide running total, omit `PARTITION BY account_id`:

```sql
SUM(amount) OVER (
    ORDER BY txn_at, txn_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Without partitioning, transactions from all accounts are summed into a single chronological sequence. Do this only if that is the intended report semantics.

### 3.2. Ordering must be deterministic

If multiple transactions share the same `txn_at`, sorting solely by `txn_at` leaves the relative order among same-timestamp transactions undefined. With `ROWS`, that order affects the running total at each row. Add a unique key such as `txn_id` as a tie-breaker:

```sql
ORDER BY txn_at, txn_id
```

This ordering does not claim which transaction occurred first in real life when timestamps match; it simply establishes a stable ordering for calculation. If the domain has an explicit sequence number or event order column, use that column.

## 4. Running average

`AVG()` with the same cumulative frame calculates the average of values from the start of the partition to the current row:

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_average
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

For account 10, the running averages are 100.00, 75.00, approximately 58.3333, 58.3333, and 38.75. The row with `amount IS NULL` does not contribute to either the numerator or the denominator of `AVG()`, so the average on the fourth row stays unchanged.

### 4.1. AVG ignores NULLs while the frame still contains the row

`ROWS` determines how many rows are in the frame, not that every row contributes to the denominator. `AVG(amount)` skips `NULL`s; you can display the count of actually included values using `COUNT(amount)`:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_seen,
    COUNT(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS known_amounts,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_average
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

`rows_seen` counts all rows in the frame; `known_amounts` counts only non-`NULL` amounts. If every value in the frame is `NULL`, `AVG()` returns `NULL`.

## 5. Moving average by row count

A moving average computes an average over a bounded window. For example, the average of the current transaction and the two immediately preceding transactions:

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_txns
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

The frame contains at most three rows: the two preceding rows and the current row. At the beginning of a partition, the frame has fewer than three rows because there is not enough history.

Expected output:

| account_id | txn_id | amount | moving_avg_3_txns |
|---:|---:|---:|---:|
| 10 | 1 | 100.00 | 100.00 |
| 10 | 2 | 50.00 | 75.00 |
| 10 | 3 | 25.00 | 58.33 |
| 10 | 4 | `NULL` | 37.50 |
| 10 | 5 | -20.00 | 2.50 |
| 20 | 6 | 200.00 | 200.00 |
| 20 | 7 | 100.00 | 150.00 |
| 20 | 8 | 50.00 | 116.67 |
| 20 | 9 | 0.00 | 50.00 |

### 5.1. Frame by transaction count, not day count

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` means three rows in order, not three days. If an account has 20 transactions on the same day, the window may consist of three transactions from that single day. If an account has no transactions for a week, the window still grabs the three nearest rows, even if they are days apart.

Name the metric clearly, such as `moving_avg_3_txns`, so readers do not mistake it for a three-day average.

### 5.2. Moving average with a symmetric frame

You can compute an average using one preceding row and one following row:

```sql
AVG(amount) OVER (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
) AS centered_avg_3_rows
```

This is a centered moving average. Because it uses future data relative to the current row, it fits historical analysis or smoothing completed series. For real-time dashboards or point-in-time forecasting, using `FOLLOWING` can introduce future data leakage; a frame ending at `CURRENT ROW` is usually appropriate.

## 6. ROWS and RANGE: two ways to define a frame

`ROWS` defines the frame by row position. `RANGE` defines the frame by the value of the sort expression and includes peer rows sharing the same sort key value.

| Criterion | `ROWS` | `RANGE` |
|---|---|---|
| Definition | Number of rows before/after current row | Value interval of `ORDER BY` expression |
| Example | `2 PRECEDING` is two rows back | `INTERVAL 6 DAY PRECEDING` is a six-day lookback interval |
| Rows with equal sort keys | Treated as distinct row positions; needs a tie-breaker for stability | Treated as peers and grouped together at `CURRENT ROW` boundary |
| Typical use | Last 3 transactions, last 7 records | Totals/averages over a time span or value range |

### 6.1. Default RANGE can make running totals differ from expectations

In MySQL, when an aggregate window has `ORDER BY` without an explicit frame, the default frame is:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

With `RANGE`, rows sharing the same `ORDER BY` value are peers. In our sample data, transactions 2 and 3 of account 10 share the same `txn_at`. The query:

```sql
SELECT
    txn_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at
    ) AS default_range_total
FROM account_txn
WHERE account_id = 10
ORDER BY txn_at, txn_id;
```

gives both ID 2 and ID 3 the same total `175.00`, because each row's frame includes all peers at the 2026-01-02 timestamp. This is not a bug; it is `RANGE` semantics.

If you want the total to increment per transaction, specify `ROWS` and a tie-breaker:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

The results for ID 2 and ID 3 are 150.00 and 175.00 respectively. Do not rely on the default frame when business logic requires row-by-row ordering.

### 6.2. RANGE with time intervals

For date/datetime data, `RANGE` can use `INTERVAL` offsets when `ORDER BY` has a single temporal expression:

```sql
RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW
```

This frame gathers rows whose date falls within the six days prior to the current row's date up through the current date, based on the sort key. For a `RANGE` frame with an offset, use a single suitable `ORDER BY` expression; do not add a secondary key like `txn_id` to this time-window ordering. If row-by-row transaction ordering is needed, that is a different requirement and should use `ROWS`.

## 7. Seven-calendar-day moving average

To compute a daily average, first aggregate transactions to one row per account per day, then apply date-based `RANGE`:

```sql
WITH daily_amount AS (
    SELECT
        account_id,
        DATE(txn_at) AS txn_day,
        SUM(amount) AS day_total
    FROM account_txn
    GROUP BY account_id, DATE(txn_at)
)
SELECT
    account_id,
    txn_day,
    day_total,
    AVG(day_total) OVER (
        PARTITION BY account_id
        ORDER BY txn_day
        RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW
    ) AS avg_daily_total_7d
FROM daily_amount
ORDER BY account_id, txn_day;
```

Because `daily_amount` has at most one row per account per day, the time frame has a clear meaning. `AVG(day_total)` averages the days present in the CTE and skips `day_total IS NULL`.

### 7.1. A missing row does not automatically mean zero

The query above only returns days that had transactions. If an account had no transactions on 2026-01-02, that day does not appear in `daily_amount` and is not automatically counted as a day with a sum of 0. Thus, `AVG(day_total)` here averages over active days present in the data within a seven-calendar-day span.

If the requirement is a true seven-calendar-day average—including days with zero transactions—build a calendar (date table), `LEFT JOIN` daily totals onto the calendar, and fill missing days with 0 per business rules:

```sql
WITH RECURSIVE calendar AS (
    SELECT DATE('2026-01-01') AS calendar_day
    UNION ALL
    SELECT calendar_day + INTERVAL 1 DAY
    FROM calendar
    WHERE calendar_day < '2026-01-31'
),
daily_amount AS (
    SELECT
        account_id,
        DATE(txn_at) AS txn_day,
        SUM(amount) AS day_total
    FROM account_txn
    GROUP BY account_id, DATE(txn_at)
),
account_days AS (
    SELECT
        a.account_id,
        c.calendar_day,
        COALESCE(d.day_total, 0) AS day_total
    FROM (SELECT DISTINCT account_id FROM account_txn) AS a
    CROSS JOIN calendar AS c
    LEFT JOIN daily_amount AS d
        ON d.account_id = a.account_id
       AND d.txn_day = c.calendar_day
)
SELECT
    account_id,
    calendar_day,
    day_total,
    AVG(day_total) OVER (
        PARTITION BY account_id
        ORDER BY calendar_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS avg_calendar_7d
FROM account_days
ORDER BY account_id, calendar_day;
```

Here the calendar produces one row per day, so `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` spans up to seven consecutive days. This query assumes days without records represent a total of 0; if `NULL` means data was not loaded or is unknown, do not convert it to 0. For large reporting ranges, use a physical calendar table instead of generating dates with a recursive CTE on every run.

## 8. Common frames and boundaries

| Frame | Meaning |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From start of partition to current row; running sum/average |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Two preceding rows and current row; up to three rows |
| `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | Six preceding rows and current row; up to seven rows |
| `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | One preceding row, current row, and one following row |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | From current row to end of partition |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Entire partition for every row |

`PRECEDING` and `FOLLOWING` specify row counts with `ROWS`, or value/time offsets with `RANGE`. Start and end boundaries must be valid; never place the start boundary after the end boundary.

## 9. NULLs in running and moving calculations

`SUM()` and `AVG()` ignore `NULL` values inside the frame:

- If a frame contains both numbers and `NULL`s, only the numbers contribute to the sum/average.
- If a frame contains no non-`NULL` values, `SUM()` and `AVG()` return `NULL`.
- `COUNT(*) OVER (...)` counts all rows in the frame.
- `COUNT(amount) OVER (...)` counts non-`NULL` amounts in the frame.

Example inspecting a moving average alongside observation counts:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    COUNT(*) OVER w AS rows_in_frame,
    COUNT(amount) OVER w AS known_amounts,
    SUM(amount) OVER w AS frame_sum,
    AVG(amount) OVER w AS frame_average
FROM account_txn
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY account_id, txn_at, txn_id;
```

Named window `w` avoids repeating the same frame definition. You can write `COALESCE(AVG(amount) OVER w, 0)` if a report wants 0 when the frame has no values, though consider returning `known_amounts` as well so readers know the frame lacked valid data.

## 10. Filtering data before vs. after window functions

Window functions are evaluated on the row set produced after `FROM`, `WHERE`, `GROUP BY`, and `HAVING` in a query block. Thus, filter placement directly affects the result. You cannot filter directly on a window result inside `WHERE` or `HAVING` in the same query block; wrap the calculation in a CTE/derived table and filter in the outer query.

### 10.1. Filtering before window evaluation

```sql
SELECT
    account_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_in_filtered_set
FROM account_txn
WHERE txn_at >= '2026-01-03';
```

Transactions before 2026-01-03 are excluded prior to window evaluation. The running total starts from the remaining rows, omitting prior history.

### 10.2. Computing over history first, then filtering output

If you want to display rows from 2026-01-03 onward while still including prior history in the running total, compute the window in a CTE and filter in the outer query:

```sql
WITH running AS (
    SELECT
        account_id,
        txn_id,
        txn_at,
        amount,
        SUM(amount) OVER (
            PARTITION BY account_id
            ORDER BY txn_at, txn_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM account_txn
)
SELECT account_id, txn_id, txn_at, amount, running_total
FROM running
WHERE txn_at >= '2026-01-03'
ORDER BY account_id, txn_at, txn_id;
```

This is the standard pattern for reports with a narrow display window that require cumulative balances from the beginning of history.

### 10.3. Moving averages are also affected by WHERE

If you filter to transactions from 2026-01-03 onward before computing a three-transaction moving average, the first frame on 2026-01-03 cannot see the two prior transactions. If the moving average must include history preceding the display start date, compute the window in a CTE and filter outside. For large reports, consider fetching only the minimal historical lookback needed for the frame to avoid scanning the entire table.

## 11. Data types and precision

For monetary amounts, use `DECIMAL` rather than `FLOAT`/`DOUBLE` to avoid binary floating-point representation errors. `SUM()` and `AVG()` on exact numeric types such as `DECIMAL` preserve exact numeric semantics per MySQL rules; approximate types can introduce rounding drift.

Do not cast results to strings inside the window if further summation, averaging, or numeric comparison is needed. Format only in the outer query or application layer:

```sql
WITH metrics AS (
    SELECT
        account_id,
        txn_id,
        AVG(amount) OVER (
            PARTITION BY account_id
            ORDER BY txn_at, txn_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS moving_average
    FROM account_txn
)
SELECT
    account_id,
    txn_id,
    ROUND(moving_average, 2) AS moving_average_display
FROM metrics;
```

`ROUND()` here rounds only the displayed value. Using pre-rounded values as inputs to subsequent calculations can cause cumulative drift compared to preserving full precision.

## 12. Indexes and window query performance

Queries frequently partition by `account_id` and order by `txn_at`, `txn_id`. The index:

```sql
KEY idx_account_txn_time (account_id, txn_at, txn_id)
```

has a column order matching this access pattern: partition column first, followed by sort columns. Indexes can help read rows in the desired order or reduce sorting overhead, though the optimizer still chooses the plan based on statistics, predicates, and data size.

Inspect the plan:

```sql
EXPLAIN FORMAT=TREE
SELECT
    account_id,
    txn_id,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
WHERE account_id = 10;
```

Check table scan, sort, and window evaluation steps. `EXPLAIN ANALYZE` in MySQL 8.0.18+ executes the query and reports actual row counts and timings; use it on read queries with controlled scope.

Key notes:

- Indexes do not eliminate window computation cost; they only assist access and input ordering.
- Multiple partitions or differing `ORDER BY` clauses may require multiple sort passes.
- Wide frames and large row counts increase resource consumption.
- Select only needed columns; avoid carrying large BLOB/TEXT columns through intermediate buffers unnecessarily.
- Indexes increase storage size and `INSERT`/`UPDATE`/`DELETE` cost; weigh write workload impacts.

## 13. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Running total accumulates across other accounts | Missing `PARTITION BY account_id` | Partition by the business key |
| Totals on two same-timestamp rows are identical | Default frame is `RANGE` and the rows are peers | Use `ROWS` with a tie-breaker if row-by-row is required |
| Results vary across runs when timestamps collide | `ORDER BY` does not define a unique order for `ROWS` | Add a unique key or business sequence column |
| Moving average spans too many days | Used `ROWS` while assuming it counts days | Use temporal `RANGE` or a calendar table |
| Average is lower than expected | `AVG(COALESCE(amount, 0))` or denominator includes zero-substituted rows | Clarify NULL meaning and use `AVG(amount)` if NULL means missing |
| Days without transactions are missing from output | Window only computes over existing rows | Use a calendar table with LEFT JOIN if all days are required |
| Running total resets at start of reporting window | `WHERE` date filter applied before window | Compute window in a CTE and filter results outside |
| Moving average at start of range lacks history | Rows filtered before window runs | Load needed lookback history or filter after window |
| Query is slow despite having an index | Window still requires sort/materialization or scans many rows | Check `EXPLAIN`, partition/order, frame, and data volume |

## 14. Workflow for designing running totals and moving averages

Before writing SQL, answer these questions:

1. Is the metric computed per account, customer, product, or globally? That defines `PARTITION BY`.
2. Is business order based on timestamp, date, sequence, or ID? Choose `ORDER BY` and a tie-breaker.
3. Does the window span from the start of history, the last three transactions, seven calendar days, or another range? Choose the frame.
4. Does `NULL` represent missing data, inactivity, or zero? Decide how to compute and display it.
5. Must days with zero activity be included? If so, build a calendar/dense series before the window.
6. Should the report only display a slice while computing over full history, or compute only over the slice? Place filters before or after the window accordingly.
7. What monetary precision must be preserved? Use `DECIMAL` and round at the right layer.
8. How large is the dataset? Inspect indexes, `EXPLAIN`, and sort/materialization plans.

## 15. Practice exercises

Using the `account_txn` table from section 2:

1. Write a per-account running total with `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
2. Write a running average and compare it with the running total.
3. Compute `COUNT(*)` and `COUNT(amount)` over the same frame; explain the row with `amount IS NULL`.
4. Write a three-transaction moving average using `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
5. Remove `txn_id` from `ORDER BY` and omit the frame to observe the effect of the default `RANGE` frame on the two same-timestamp transactions.
6. Add `txn_id` and the `ROWS` frame to produce deterministic per-transaction ordering.
7. Write a centered frame `1 PRECEDING AND 1 FOLLOWING`; explain why this metric is unsuitable for real-time dashboards.
8. Aggregate amounts by day, then compute a seven-day moving average using `RANGE INTERVAL 6 DAY`.
9. Build a calendar and compute a seven-calendar-day average including days with no transactions; compare with the active-days-only average.
10. Compute the running total across all history and display only transactions from a chosen start date using a CTE.
11. Try placing `WHERE` inside the window query vs. outside the CTE; note how early-range results differ.
12. Use a named window to reuse the partition/order/frame definition across `SUM`, `AVG`, and `COUNT`.
13. Run `EXPLAIN FORMAT=TREE`; compare the query with and without index `(account_id, txn_at, txn_id)` on a sufficiently large lab dataset.

You have completed this lesson when you can explain why two transactions sharing the same timestamp can receive the same total under a `RANGE` frame, write moving averages by both row count and calendar days, and preserve history properly when filtering the display range.

## 16. Key principles to remember

- `SUM() OVER` and `AVG() OVER` preserve individual rows; `GROUP BY` collapses rows into groups.
- `PARTITION BY` restarts the calculation for each group.
- `ORDER BY` inside `OVER` controls calculation order; `ORDER BY` at the end of the query controls output order.
- Running totals typically use `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- Three-row moving averages typically use `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
- `ROWS` counts row positions; `RANGE` evaluates sort key values and peers.
- MySQL defaults to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` when an aggregate window has `ORDER BY` without an explicit frame.
- Add a unique tie-breaker when deterministic row-by-row ordering is needed.
- `AVG()` and `SUM()` skip `NULL`s; use `COUNT(amount)` to see how many valid observations are in the frame.
- A seven-transaction average differs from a seven-calendar-day average.
- Missing dates do not automatically become zero; use a calendar table when a full date series is needed.
- Filtering before the window changes the input data used for computation; filter in an outer query when prior history must be preserved.
- Use `DECIMAL` for currency and round only at presentation or per business rules.
- Indexes ordered as `(partition_key, order_key, tie_breaker)` can assist access; always verify the actual execution plan.
