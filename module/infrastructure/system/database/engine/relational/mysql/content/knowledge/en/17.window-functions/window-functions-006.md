# ROWS/RANGE Frames, Default Frames, and Peer Rows

Window functions compute over a set of rows related to the current row while still keeping every individual row in the result. For aggregate window functions such as `SUM() OVER (...)`, the *window frame* determines which rows within the partition are included in the calculation for each row. Choosing the wrong frame can cause running totals to jump by group, rolling averages to count days instead of records, or `LAST_VALUE()` to return the current row's value instead of the partition's final value.

MySQL supports two main frame units: `ROWS` and `RANGE`. `ROWS` defines the frame by row position within the window order; `RANGE` defines the frame by the value of the sort expression and includes tied rows (*peers*). When the frame clause is omitted, MySQL applies a default frame. Without understanding this default, rows sharing the same `ORDER BY` value can receive the same aggregate result even when you intended a row-by-row calculation.

This lesson belongs to the `DATABASE_MYSQL` module, covering table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and query optimization. The content focuses on defining frames accurately to match business requirements: by row count, by value interval, by calendar date, or across the entire partition.

After this lesson, you will be able to:

- Explain partitions, window ordering, frames, and peer rows.
- Distinguish `ROWS` from `RANGE`.
- Predict the default frame when `ORDER BY` is present or absent.
- Write explicit frames using `UNBOUNDED`, `PRECEDING`, `CURRENT ROW`, and `FOLLOWING`.
- Compute running totals and rolling aggregates by row count or time interval.
- Handle tied rows and choose tie-breaker keys when deterministic ordering is required.
- Avoid common mistakes with `LAST_VALUE()` and frame-sensitive functions.
- Verify window frame syntax, results, and performance in MySQL.

## 1. Partition, ORDER BY, and frame

A window specification can consist of three parts:

```sql
function_name(expression) OVER (
    PARTITION BY partition_expression
    ORDER BY order_expression
    frame_clause
)
```

- `PARTITION BY` divides data into independent groups. The window function is evaluated separately within each partition. If `PARTITION BY` is omitted, the entire row set forms a single partition.
- `ORDER BY` defines the logical order of rows within the partition. This order is used by ranking, navigation, and frame evaluation.
- `frame_clause` specifies which slice of the partition around the current row is used for window functions that support frames.

Example:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total
```

This expression computes a separate running total per account, from the first row in the partition up to the current row. `sale_id` acts as a tie-breaker so transactions on the same date have a deterministic order.

Do not confuse `ORDER BY` inside `OVER()` with the outer query's `ORDER BY`. `OVER(ORDER BY ...)` governs how the window function is computed; the outer `ORDER BY` governs the order in which rows are returned to the client. If ordered output is required, you still need an outer `ORDER BY`.

## 2. Fixture for comparing ROWS and RANGE

Create a temporary table with transactions having duplicate dates and equal amounts. The fixture is designed to clearly demonstrate the effect of peer rows.

```sql
DROP TEMPORARY TABLE IF EXISTS window_sales;

CREATE TEMPORARY TABLE window_sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    account_id INT UNSIGNED NOT NULL,
    sold_on DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (sale_id),
    KEY idx_window_sales_account_date (account_id, sold_on, sale_id)
) ENGINE = InnoDB;

INSERT INTO window_sales (sale_id, account_id, sold_on, amount) VALUES
(101, 1, '2026-11-01', 100.00),
(102, 1, '2026-11-02',  50.00),
(103, 1, '2026-11-02',  50.00),
(104, 1, '2026-11-04',  20.00),
(105, 1, '2026-11-07',  30.00),
(201, 2, '2026-11-02', 200.00);
```

Data for account 1:

| sale_id | sold_on | amount |
| ---: | --- | ---: |
| 101 | 2026-11-01 | 100.00 |
| 102 | 2026-11-02 | 50.00 |
| 103 | 2026-11-02 | 50.00 |
| 104 | 2026-11-04 | 20.00 |
| 105 | 2026-11-07 | 30.00 |

Transactions 102 and 103 share the same `sold_on`, so they are peer rows if the window only has `ORDER BY sold_on`. They are not the same transaction: `sale_id` differs. When `sale_id` is added to the window ordering, the two rows are no longer tied because the full `ORDER BY` expression list differs.

## 3. ROWS: frame by row position

`ROWS` defines the frame by the number of rows before/after the current row in window order. It ignores the numeric or temporal distance between sort key values.

### 3.1. Row-by-row running total

```sql
SELECT
    sale_id,
    account_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM window_sales
ORDER BY account_id, sold_on, sale_id;
```

Expected output:

| sale_id | account_id | sold_on | amount | running_total |
| ---: | ---: | --- | ---: | ---: |
| 101 | 1 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 1 | 2026-11-02 | 50.00 | 150.00 |
| 103 | 1 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 1 | 2026-11-04 | 20.00 | 220.00 |
| 105 | 1 | 2026-11-07 | 30.00 | 250.00 |
| 201 | 2 | 2026-11-02 | 200.00 | 200.00 |

For account 1, each row adds exactly its own amount to the previous total. The two same-day rows are processed sequentially by `sale_id`, yielding 150 and 200 respectively.

### 3.2. Three-row rolling window

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_rows_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | amount | rolling_3_rows_total |
| ---: | ---: | ---: |
| 101 | 100.00 | 100.00 |
| 102 | 50.00 | 150.00 |
| 103 | 50.00 | 200.00 |
| 104 | 20.00 | 120.00 |
| 105 | 30.00 | 100.00 |

The frame `2 PRECEDING` to `CURRENT ROW` holds at most three rows: the two preceding rows and the current row. At sale 104, the frame contains sales 102, 103, and 104, totaling 120. At sale 105, the frame contains sales 103, 104, and 105, totaling 100.

This is a record-count rolling window. If a day has no transactions, that day does not occupy a row in the frame. If business rules call for a three-calendar-day rolling window, use date-based `RANGE` or join against a calendar table.

### 3.3. ROWS requires deterministic ordering when ties exist

If you only write:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

sales 102 and 103 share the same sort key. SQL does not specify which row comes before the other within the tied group. The running totals on those two rows could be assigned in different orders across execution plans.

When a frame uses `ROWS` and results depend on individual row position, add a unique key to `ORDER BY`, such as `ORDER BY sold_on, sale_id`. If the domain has no natural tie-breaker among tied rows, define an explicit tie-breaking rule before writing the query.

## 4. RANGE: frame by ORDER BY value

`RANGE` defines the frame based on the value of the sort expression. Rows sharing identical values across all window `ORDER BY` expressions are peers. When the frame ends at `CURRENT ROW`, peers of the current row are also included in the frame.

### 4.1. Default RANGE with ORDER BY

For an aggregate window function with `ORDER BY` and no explicit frame, MySQL uses a default frame equivalent to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Run the query:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
    ) AS default_running_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Expected output:

| sale_id | sold_on | amount | default_running_total |
| ---: | --- | ---: | ---: |
| 101 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 2026-11-02 | 50.00 | 200.00 |
| 103 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 2026-11-04 | 20.00 | 220.00 |
| 105 | 2026-11-07 | 30.00 | 250.00 |

Both rows on `2026-11-02` receive a total of 200.00 because `RANGE ... CURRENT ROW` includes both peer rows. This is a key difference from `ROWS` with a tie-breaker key.

### 4.2. RANGE with numeric value intervals

With a numeric `ORDER BY` expression, a RANGE offset represents a value interval rather than a row count:

```sql
RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
```

If the current sort key is 100, the frame includes rows whose sort key lies between 90 and 100 in ascending order, including boundary peers. It might contain 1, 3, or hundreds of records depending on the data.

Example on a numeric column:

```sql
SELECT
    score,
    SUM(points) OVER (
        ORDER BY score
        RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
    ) AS points_in_score_band
FROM player_scores;
```

This is the sum of rows whose `score` falls within the 10-point band ending at the current score, not the sum of the 10 preceding rows.

### 4.3. RANGE with date intervals

With a temporal sort key, you can use `INTERVAL` to specify a time span:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
        RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW
    ) AS rolling_3_calendar_days_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | sold_on | amount | rolling_3_calendar_days_total |
| ---: | --- | ---: | ---: |
| 101 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 2026-11-02 | 50.00 | 200.00 |
| 103 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 2026-11-04 | 20.00 | 120.00 |
| 105 | 2026-11-07 | 30.00 | 30.00 |

For `2026-11-04`, the frame covers rows from `2026-11-02` to `2026-11-04`, comprising sales 102, 103, and 104. For `2026-11-07`, the frame covers `2026-11-05` to `2026-11-07`; only sale 105 falls in that range, so the total is 30.00.

`RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW` is a rolling window over three calendar days including the current day. It does not generate extra rows for days without transactions. If empty days must also appear in output, combine a calendar table/CTE with the transaction data before applying the window function.

### 4.4. Limitation of RANGE offsets in MySQL

For a `RANGE` frame with an `expr PRECEDING` or `expr FOLLOWING` offset, MySQL requires the window `ORDER BY` to contain only a single expression. That expression must be numeric or temporal matching the offset type; for temporal values, use the `INTERVAL` form. You cannot add `sale_id` as a tie-breaker to the same `ORDER BY` in the `RANGE INTERVAL` example while keeping an offset frame.

If you need both deterministic per-row ordering and date-based rolling ranges at the same time, distinguish the two objectives:

- Date-based `RANGE` naturally groups same-day rows as peers.
- Date-and-ID `ROWS` determines individual row positions, but the window counts rows rather than days.

You cannot substitute one of these semantics for the other merely by adding or removing a column in `ORDER BY`.

## 5. Peer rows and ties

Peer rows are rows that share identical values across every expression in the window's `ORDER BY`. For instance, under `ORDER BY sold_on`, all transactions on the same day are peers. Under `ORDER BY sold_on, sale_id`, only rows matching both date and ID are peers; if `sale_id` is unique, each row is its own peer group of one.

Peers affect:

- `RANGE ... CURRENT ROW`: the ending boundary includes the entire peer group.
- Ranking functions such as `RANK()` and `DENSE_RANK()`: rows with equal sort keys receive the same rank per their respective rules.
- Aggregate window results using the default `RANGE` frame: tied rows can receive the same cumulative result.

Example:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    RANK() OVER (PARTITION BY account_id ORDER BY sold_on) AS date_rank,
    DENSE_RANK() OVER (PARTITION BY account_id ORDER BY sold_on) AS dense_date_rank
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

The two transactions on `2026-11-02` receive the same `date_rank` and `dense_date_rank`. `RANK()` leaves a gap after the tied group; `DENSE_RANK()` leaves no gap. Adding `sale_id` to the window ordering would break the tie group and give each row a separate rank, so only add that key if the business wants row-level sequence rather than date-level ranking.

### 5.1. Outer ORDER BY does not change peer groups

You can keep window `ORDER BY sold_on` so peers are determined by date, while using `ORDER BY sold_on, sale_id` in the outer query for deterministic display:

```sql
SELECT
    sale_id,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
    ) AS daily_peer_running_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

The outer `ORDER BY` only sorts the already-computed rows. It does not inject `sale_id` into the window ordering and does not alter the frame or peer group.

## 6. Default frames in MySQL

For window functions that use frames:

| Window specification | Equivalent default frame |
| --- | --- |
| `ORDER BY` present, no frame specified | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` |
| No `ORDER BY`, no frame specified | Entire partition, equivalent to `RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |

Example with `ORDER BY`:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on
)
```

The frame ends at the current row and includes peers. If a row-by-row running total is needed, specify `ROWS` along with an ordering containing a tie-breaker key.

Example without `ORDER BY`:

```sql
SUM(amount) OVER (PARTITION BY account_id)
```

Every row for an account receives the total `amount` of that account's entire partition. With no row ordering, there is no notion of "before the current row" in the default frame.

Do not rely on default frames in critical queries. Writing frames explicitly clarifies intent and helps readers immediately see whether a calculation is a full-partition total, a peer-group running total, or a row-by-row running total.

## 7. Frame boundary types

Frames are written in the form:

```sql
ROWS | RANGE BETWEEN frame_start AND frame_end
```

Common boundaries:

| Boundary | Meaning |
| --- | --- |
| `UNBOUNDED PRECEDING` | Starts from the beginning of the partition |
| `n PRECEDING` | Starts/ends n rows back (ROWS) or n value units back (numeric RANGE) |
| `INTERVAL n unit PRECEDING` | Temporal offset for RANGE, e.g. 7 days back |
| `CURRENT ROW` | Current row with ROWS; current row and peers with RANGE |
| `n FOLLOWING` | n rows ahead with ROWS or n value units ahead with numeric RANGE |
| `INTERVAL n unit FOLLOWING` | Forward temporal offset for RANGE |
| `UNBOUNDED FOLLOWING` | Ends at the end of the partition |

Examples of frames:

```sql
-- From start of partition to current row
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Two rows before, current row, and one row after
ROWS BETWEEN 2 PRECEDING AND 1 FOLLOWING

-- Current row and next two rows
ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING

-- Entire partition
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING

-- Sort key values from 10 units before to current
RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
```

A frame start cannot be `UNBOUNDED FOLLOWING`; a frame end cannot be `UNBOUNDED PRECEDING`. The boundaries must form a valid ordered range. With `ROWS`, offsets are non-negative integer row counts. With `RANGE`, offsets must be compatible with the type and expression of `ORDER BY`.

## 8. LAST_VALUE() and the default frame

`LAST_VALUE()` is easy to misread because the default frame ends at the current row. The function returns the value from the last row of the current frame, not by default the last row of the entire partition.

Example:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
    ) AS last_value_default,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_value_partition
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Because the window ordering includes unique `sale_id`, the default frame ends at the current row. Thus `last_value_default` evaluates to 100, 50, 50, 20, and 30 respectively. The `last_value_partition` column is 30 on every row because the explicit frame extends to the end of the partition.

If the goal is to retrieve the partition's final value, use:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

At the same time, the window `ORDER BY` must accurately define which row is considered last. If ties exist without a tie-breaker key, "last" may be nondeterministic.

`FIRST_VALUE()` retrieves the first value in the frame; `NTH_VALUE()` retrieves the value at position n in the frame and can return `NULL` when the frame does not yet contain enough rows. Always verify frames explicitly when using these functions.

## 9. Which functions use frames?

Frames matter for aggregate window functions such as `SUM()`, `AVG()`, `COUNT()`, `MIN()`, `MAX()` and frame-sensitive value functions such as `FIRST_VALUE()`, `LAST_VALUE()`, and `NTH_VALUE()`.

Ranking functions such as `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `PERCENT_RANK()`, `CUME_DIST()`, and `NTILE()` depend on partition and window ordering; the frame clause does not determine their ranking results. `LAG()` and `LEAD()` fetch values from preceding/following rows in window order and do not use frames to constrain their offsets.

Therefore, do not attach a frame to every window function out of habit. Identify whether the function actually uses a frame, and declare one when it clarifies or alters the set of rows being evaluated.

## 10. NULLs and frames

Aggregates such as `SUM()` and `AVG()` ignore `NULL` values inside the frame; `COUNT(expr)` counts only non-`NULL` expressions; `COUNT(*)` counts rows in the frame. If the frame contains no non-NULL values to sum or average, `SUM()`/`AVG()` return `NULL`.

Example:

```sql
SELECT
    sale_id,
    amount,
    COUNT(*) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS frame_rows,
    COUNT(amount) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS non_null_amounts,
    SUM(amount) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS frame_sum
FROM window_sales
ORDER BY sale_id;
```

A frame can contain two rows while `COUNT(amount)` is only 1 if one row has a NULL amount. `SUM()` does not turn NULL into 0; if you want 0 when a frame has no numeric values, use `COALESCE(SUM(amount) OVER (...), 0)` and confirm that matches the business rule.

## 11. Choosing ROWS or RANGE by requirement

| Requirement | Appropriate frame | Note |
| --- | --- | --- |
| Per-transaction running total | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Add a unique key to window ORDER BY |
| Average of last 7 transactions | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | May span multiple days |
| Total over last 7 calendar days | `RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW` | Requires a single temporal ORDER BY expression |
| Daily running total where same-day transactions share the same result | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` with date ORDER BY | Same-day peer rows are summed together |
| Full-partition total repeated on each row | No ORDER BY, or unbounded-to-unbounded frame | Does not produce a running total |
| Final value of partition | Frame ending in `UNBOUNDED FOLLOWING` with `LAST_VALUE()` | Define final ordering uniquely |

Before choosing a frame, state the window in business terms:

- "The last three transactions" is a row count: use `ROWS`.
- "The last seven calendar days" is a date value interval: use `RANGE`.
- "All same-day transactions get the same daily cumulative total": use `RANGE` peer semantics.
- "Each transaction gets its own running total in ID order": use `ROWS` with a tie-breaker.

## 12. MySQL-specific limitations and caveats

- MySQL supports `ROWS` and `RANGE` frame units; it does not support the `GROUPS` frame unit.
- `RANGE` with a `PRECEDING`/`FOLLOWING` offset requires a single `ORDER BY` expression; the expression type must be compatible with numeric or temporal offsets.
- For temporal `RANGE`, use the appropriate `INTERVAL`, such as `INTERVAL 7 DAY PRECEDING`.
- Recursive CTEs, aggregates, and window functions have distinct rules; do not place a window function inside the recursive member of a recursive CTE.
- Frame boundaries must be valid; never use `UNBOUNDED FOLLOWING` as the start or `UNBOUNDED PRECEDING` as the end.
- Window `ORDER BY` does not automatically sort final output; an outer query `ORDER BY` is still needed.
- Frames do not reduce the number of returned rows; they only alter the set of rows seen by the window function.

Check the documentation for your exact MySQL version when using temporal RANGE offsets or advanced syntax. Some other database systems support `GROUPS` and `EXCLUDE`, which cannot be copied verbatim into MySQL.

## 13. Verifying results and performance

### 13.1. Checking logic with a small fixture

For every framed query, determine upfront:

1. Which partition is computed separately.
2. Window ordering and tie-breaker keys.
3. Which peer groups share the same sort key.
4. Which rows fall inside the frame at each sample row.
5. Expected aggregate outputs.

The fixture in section 2 is enough to distinguish:

- Cumulative `ROWS`: 150 and 200 on the two same-day transactions.
- Default `RANGE`: both same-day transactions receive 200.
- `ROWS 2 PRECEDING`: the last three records.
- `RANGE INTERVAL 2 DAY PRECEDING`: the last three calendar days, not the last three records.

When testing, do not just compare the final partition total. Check intermediate rows too—especially the first row, tied rows, rows after a date gap, and the final row.

### 13.2. EXPLAIN and indexes

Window functions may require sorting rows by partition/order keys. Matching indexes can sometimes provide access in the desired order or reduce work, though the optimizer may still need to sort or materialize depending on the query and plan.

Example:

```sql
EXPLAIN
SELECT
    sale_id,
    account_id,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM window_sales;
```

The index `(account_id, sold_on, sale_id)` matches the partition/order keys of this example, though it does not guarantee MySQL will always avoid a sort step. Read the plan, check actual row counts, and benchmark on representative data. `EXPLAIN ANALYZE` executes the real query, so weigh the load before running it.

Factors to watch:

- Number of partitions and rows per partition.
- Cost of sorting by `PARTITION BY`/`ORDER BY` expressions.
- Frame size and how many rows must be buffered for frames with `FOLLOWING`.
- Whether multiple distinct window specifications force multiple sort passes.
- Memory and temporary table usage on large datasets.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Omitting the frame and assuming the default is ROWS | Peer rows receive the same aggregate | Declare `ROWS` explicitly when row-by-row semantics are needed |
| Using ROWS for date ranges | Frame counts records, not days | Use temporal RANGE or a calendar table |
| Using RANGE offset with multiple ORDER BY expressions | MySQL rejects the syntax | Use only a single sort expression for RANGE offsets |
| Omitting a tie-breaker for ROWS | Ordering among peer rows is nondeterministic | Add a unique key to window ORDER BY |
| Adding a unique key to RANGE when trying to keep peer groups | Peer group gets split apart | Keep ORDER BY on business keys and sort the outer query separately |
| Assuming CURRENT ROW is always one row | RANGE CURRENT ROW includes peers | Distinguish ROWS and RANGE semantics |
| Using LAST_VALUE with default frame to get partition end | Usually returns current row or last peer in frame | Extend frame to UNBOUNDED FOLLOWING |
| Assuming window ORDER BY sorts final output | Client receives rows in an unguaranteed order | Add ORDER BY to the outer query |
| Using SUM/AVG without checking NULLs | Totals/averages may behave unexpectedly | Check COUNT(*) vs. COUNT(expr) and define NULL meaning |

## 15. Practice exercises

1. Run the fixture in section 2. Compute the running total using the default frame and using `ROWS`; compare sales 102 and 103.
2. Remove `sale_id` from `ROWS`'s `ORDER BY`. Explain why the running total order within same-day rows is no longer guaranteed.
3. Write a three-row rolling sum using `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
4. Write a three-calendar-day rolling sum using `RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW`. Compare the `2026-11-07` sale against `ROWS`.
5. Create data with multiple rows sharing the same score. Compare `RANK()`, `DENSE_RANK()`, and an aggregate with the default `RANGE` frame.
6. Use `LAST_VALUE()` with the default frame, then extend the frame to `UNBOUNDED FOLLOWING`. Note the difference.
7. Test the frame `ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING` to sum three transactions from the current row onward.
8. Add a NULL amount to the fixture and compare `COUNT(*)`, `COUNT(amount)`, and `SUM(amount)` within the frame.
9. Test `RANGE BETWEEN 10 PRECEDING AND CURRENT ROW` on a numeric column. Identify which rows are included based on sort key values.
10. Run `EXPLAIN` for a window query before and after creating an index on partition/order keys. Explain the limitations of drawing conclusions from small tables.

## 16. Checklist before shipping window frames to production

- [ ] Defined partition and logical row order.
- [ ] Determined whether the window is based on row count or value/time interval.
- [ ] Written explicit frames whenever default behavior is not intended.
- [ ] Identified peer rows across the full window ORDER BY expression list.
- [ ] For ROWS, added a unique tie-breaker when results depend on individual row order.
- [ ] For RANGE offsets, used only one ORDER BY expression of a compatible type.
- [ ] For rolling date ranges, chosen the proper INTERVAL and handled dates without records.
- [ ] Configured `LAST_VALUE()`/`NTH_VALUE()` with frames matching requirements.
- [ ] Checked NULL handling and empty/valueless frames.
- [ ] Included an outer ORDER BY when deterministic output ordering is needed.
- [ ] Verified syntax against the deployed MySQL version.
- [ ] Checked EXPLAIN and performance on representative data.

## 17. Completion criteria

You have completed this lesson when you can explain why the default frame with `ORDER BY` is `RANGE ... CURRENT ROW`, distinguish `ROWS` vs. `RANGE` results when peer rows exist, write rolling windows by row count and by calendar day, pick proper boundaries, handle `LAST_VALUE()` to retrieve the partition's final value, guarantee deterministic ordering, and evaluate execution cost.

## References

- [MySQL 8.4 Reference Manual — Window Function Frame Specification](https://dev.mysql.com/doc/refman/8.4/en/window-functions-frames.html)
- [MySQL 8.4 Reference Manual — Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html)
- [MySQL 8.4 Reference Manual — Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
