# ROWS/RANGE Frames, Default Frames, and Peer Rows

In Oracle SQL, analytic functions can calculate running totals, moving averages, maximum values over an interval, or the first/last value of a data window while preserving every detail row. The component that determines **which rows are included in the calculation for the current row** is the *window frame*.

Oracle provides two common ways to define a frame:

- **`ROWS`**: defines the frame by the physical number of rows before/after the current row in the analytic order.
- **`RANGE`**: defines the frame by the value of the sort key; rows sharing the same sort key (peer rows) are processed together.

A very common source of confusion is that if an analytic function includes `ORDER BY` without specifying a frame, Oracle defaults to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Because this is `RANGE`, rows tied with the current row are also included in the frame. Therefore, `SUM(...) OVER (ORDER BY ...)` can jump by **sort key value groups** instead of incrementing row by row as the author might expect.

This lesson explains how to choose between `ROWS` and `RANGE`, how the default frame works, peer rows, determinism with duplicate keys, time-based frames, and how frames affect `LAST_VALUE`.

## 1. Analytic Functions and Window Frames

A regular aggregate function like `SUM(amount)` typically collapses multiple rows into one result. When using `SUM` in analytic form:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

Oracle still returns every input row. For each row, the function computes the sum over the set of rows belonging to the corresponding partition and window frame.

Three concepts to separate:

1. **Partition**: an independent group of rows defined by `PARTITION BY`. Each partition has its own window.
2. **Analytic ordering**: the logical order defined by `ORDER BY` inside `OVER(...)`.
3. **Window frame**: the subset of rows selected within the partition for the current row's calculation.

Example:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

For each transaction, Oracle sums over at most three rows: the two preceding rows and the current row in the analytic order. When moving to another partition, the window resets.

**`ORDER BY` inside `OVER` does not guarantee the final display order.** If the client requires results returned by date or frame order, the outermost SELECT statement still needs an `ORDER BY`.

## 2. Lab Data with Peer Rows

Create a transactions table in a dedicated practice schema with `CREATE TABLE` privilege and tablespace quota:

~~~sql
CREATE TABLE lab_window_sales (
    sale_id       NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    sale_date     DATE NOT NULL,
    amount        NUMBER(12, 2)
);
~~~

Insert data:

~~~sql
INSERT INTO lab_window_sales VALUES
    (1, 10, DATE '2024-01-01', 100);
INSERT INTO lab_window_sales VALUES
    (2, 10, DATE '2024-01-01', 50);
INSERT INTO lab_window_sales VALUES
    (3, 10, DATE '2024-01-02', 200);
INSERT INTO lab_window_sales VALUES
    (4, 10, DATE '2024-01-05', 100);
INSERT INTO lab_window_sales VALUES
    (5, 10, DATE '2024-01-08', 300);
INSERT INTO lab_window_sales VALUES
    (6, 10, DATE '2024-01-08', 100);
INSERT INTO lab_window_sales VALUES
    (7, 20, DATE '2024-01-01', 500);
INSERT INTO lab_window_sales VALUES
    (8, 20, DATE '2024-01-04', 200);
INSERT INTO lab_window_sales VALUES
    (9, 20, DATE '2024-01-10', 100);

COMMIT;
~~~

Observe:

| SALE_ID | DEPARTMENT_ID | SALE_DATE | AMOUNT |
| ---: | ---: | --- | ---: |
| 1 | 10 | 2024-01-01 | 100 |
| 2 | 10 | 2024-01-01 | 50 |
| 3 | 10 | 2024-01-02 | 200 |
| 4 | 10 | 2024-01-05 | 100 |
| 5 | 10 | 2024-01-08 | 300 |
| 6 | 10 | 2024-01-08 | 100 |
| 7 | 20 | 2024-01-01 | 500 |
| 8 | 20 | 2024-01-04 | 200 |
| 9 | 20 | 2024-01-10 | 100 |

In department 10, two transactions share 2024-01-01 and two share 2024-01-08. If we only use `ORDER BY sale_date`, transactions on the same date are **peer rows** because they have identical values across all sort expressions.

## 3. ROWS: Frame by Physical Row Count

`ROWS` defines the frame relative to the current row's position in the analytic order.

### 3.1. Syntax

~~~sql
ROWS BETWEEN frame_start AND frame_end
~~~

Common boundary types:

| Boundary | Meaning |
| --- | --- |
| `UNBOUNDED PRECEDING` | Starts at the first row of the partition |
| `n PRECEDING` | Steps back `n` physical rows from the current row |
| `CURRENT ROW` | The current row itself |
| `n FOLLOWING` | Steps forward `n` physical rows from the current row |
| `UNBOUNDED FOLLOWING` | Ends at the last row of the partition |

Example:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

The frame contains up to three rows: the two preceding rows and the current row. At the start of the partition, if two preceding rows do not yet exist, the frame contains only the existing rows.

### 3.2. Row-by-Row Running Total

~~~sql
SELECT
    sale_id,
    department_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum_rows
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Result:

| SALE_ID | SALE_DATE | AMOUNT | RUNNING_SUM_ROWS |
| ---: | --- | ---: | ---: |
| 1 | 2024-01-01 | 100 | 100 |
| 2 | 2024-01-01 | 50 | 150 |
| 3 | 2024-01-02 | 200 | 350 |
| 4 | 2024-01-05 | 100 | 450 |
| 5 | 2024-01-08 | 300 | 750 |
| 6 | 2024-01-08 | 100 | 850 |

The frame starts from the first row and ends at the current row. Because `SALE_ID` is a unique key, the ordering between two transactions on the same date is clearly defined.

### 3.3. Three-Transaction Moving Average

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_rows
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

For each row:

- First row: average over one transaction.
- Second row: average over two transactions.
- From the third row onward: average over the current row and two preceding rows.

This is the average over **at most three records**, not the average of the last three days. If multiple transactions occur on one day, each transaction still occupies its own position in the `ROWS` frame.

### 3.4. ROWS Needs Deterministic Ordering When Keys Repeat

Insufficiently deterministic example:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

The two transactions on 2024-01-01 share the same `SALE_DATE`. Without a secondary key, Oracle has no business rule determining which transaction precedes the other in the physical frame. The running total attached to each `SALE_ID` can vary across valid processing orders.

Add a unique key or a set of keys that produces a unique order:

~~~sql
ORDER BY sale_date, sale_id
~~~

This rule is especially important for `ROWS`, because changing row positions can change frame membership.

## 4. RANGE: Frame by Sort Key Value

`RANGE` defines the frame based on the logical value of the `ORDER BY` expression, not by row position count.

### 4.1. Syntax

~~~sql
RANGE BETWEEN frame_start AND frame_end
~~~

Example:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Under ascending `SALE_DATE` order, the frame includes rows with dates from the beginning of the partition up to the current row's date, **including all rows sharing the current date**.

### 4.2. CURRENT ROW in RANGE Includes Peer Rows

Peer rows are rows that have identical values across **all expressions** in the analytic `ORDER BY`.

Example:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

For the two department 10 transactions on 2024-01-01:

- Transaction 1 has amount 100.
- Transaction 2 has amount 50.
- Both belong to the 2024-01-01 peer group.
- The `RANGE ... CURRENT ROW` frame for each transaction contains both 2024-01-01 rows.
- Therefore, both rows receive the cumulative sum 150.

Result:

| SALE_ID | SALE_DATE | AMOUNT | RUNNING_SUM_RANGE |
| ---: | --- | ---: | ---: |
| 1 | 2024-01-01 | 100 | 150 |
| 2 | 2024-01-01 | 50 | 150 |
| 3 | 2024-01-02 | 200 | 350 |
| 4 | 2024-01-05 | 100 | 450 |
| 5 | 2024-01-08 | 300 | 850 |
| 6 | 2024-01-08 | 100 | 850 |

Both rows on the same date receive the same result. This is the core difference between `RANGE` and `ROWS` frames.

### 4.3. Comparing ROWS and RANGE on the Same Data

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_rows,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_range
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

| SALE_ID | AMOUNT | SUM_BY_ROWS | SUM_BY_RANGE |
| ---: | ---: | ---: | ---: |
| 1 | 100 | 100 | 150 |
| 2 | 50 | 150 | 150 |
| 3 | 200 | 350 | 350 |
| 4 | 100 | 450 | 450 |
| 5 | 300 | 750 | 850 |
| 6 | 100 | 850 | 850 |

Notice that the two expressions intentionally have different analytic orderings:

- `ROWS` uses `SALE_DATE, SALE_ID` to establish physical ordering.
- `RANGE` uses `SALE_DATE` to treat all transactions on the same date as peers.

If you add `SALE_ID` to `RANGE`'s `ORDER BY`, rows are no longer peers when IDs differ. With an un-offset RANGE frame, rows with different IDs can receive different frames because their full sort key now differs.

## 5. Oracle's Default Frame

For analytic functions that support windowing, when `ORDER BY` is specified without a `windowing_clause`, Oracle defaults to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Thus, these two clauses have the same frame:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### 5.1. Why Can the Default Running Total Jump by Group?

If `ORDER BY` uses only `SALE_DATE`, all transactions on the same date are peers. The default frame is RANGE, so the entire peer group is included at once. The running total jumps from 150 to 350, then 450, then 850; two transactions on the same date always receive the same total.

If the goal is a **per-transaction** running total, use `ROWS` and a deterministic secondary key:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### 5.2. Without Analytic ORDER BY

When `ORDER BY` is omitted inside `OVER`, the analytic aggregate computes over the entire partition for each row:

~~~sql
SELECT
    sale_id,
    department_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM lab_window_sales
ORDER BY department_id, sale_id;
~~~

Every transaction in department 10 receives total 850; every transaction in department 20 receives total 800. This is the partition total, not a running total. If you need a result accumulating row by row, you must define an analytic `ORDER BY` and an appropriate frame.

### 5.3. The Default Frame Is Not Always What You Want

Do not assume that "with ORDER BY, each row only sums up to itself". With the default RANGE frame, peer rows are included as well. Write the frame explicitly whenever business requirements depend on:

- Individual records in a unique order.
- All transactions on the same date.
- A numeric value range.
- A time interval.
- The entire partition, regardless of row position.

An explicit frame helps readers understand the exact rule and avoids relying on defaults.

## 6. Peer Rows and Tied Rows

Two or more rows are peers when they share the same values across **the entire analytic ORDER BY list**. For example:

~~~sql
ORDER BY sale_date
~~~

makes two transactions on the same date peers. However:

~~~sql
ORDER BY sale_date, sale_id
~~~

means they are no longer peers if `SALE_ID` differs.

### 6.1. Peer Groups Affect RANGE

With:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

all rows in the current peer group share the same frame. This causes aggregates such as `SUM`, `AVG`, `COUNT`, `MIN`, and `MAX` to return the same result for peer rows if their aggregate expressions match.

### 6.2. Peer Groups Also Matter for Ranking Functions

`RANK` and `DENSE_RANK` use analytic ordering to determine tied rows:

~~~sql
SELECT
    sale_id,
    amount,
    RANK() OVER (ORDER BY amount DESC) AS amount_rank,
    DENSE_RANK() OVER (ORDER BY amount DESC) AS amount_dense_rank
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount DESC, sale_id;
~~~

The two transactions with amount 100 are peers under `ORDER BY amount DESC`, so they receive the same rank. `RANK` leaves a gap after the tied group; `DENSE_RANK` leaves no gap.

**`RANK/DENSE_RANK` do not use a ROWS/RANGE window frame.** The peer concept still matters, but it does not mean you can attach `ROWS BETWEEN ...` to every analytic function.

### 6.3. Adding a Secondary Key Can Break Peer Groups

If you add a unique key:

~~~sql
RANK() OVER (ORDER BY amount DESC, sale_id)
~~~

rows with equal amount but different `SALE_ID` are no longer peers. They receive separate ranks. Therefore, only add a tie-breaker when business rules intend to break ties; if you need to preserve identical ranks by amount, do not put a secondary key in RANK's analytic ordering.

You can still add a secondary key to the **outermost ORDER BY** to display tied rows in a stable order:

~~~sql
SELECT
    sale_id,
    amount,
    RANK() OVER (ORDER BY amount DESC) AS amount_rank
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount DESC, sale_id;
~~~

The display order is deterministic without changing the tie definition of the RANK function.

## 7. Frames by Numeric Value Interval

`RANGE` can use numeric offsets when the analytic ordering is a single numeric expression:

~~~sql
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

If `ORDER BY amount ASC`, the current row's frame contains rows with amounts between `current amount - 100` and `current amount`, inclusive.

Example:

~~~sql
SELECT
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY amount
        RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
    ) AS sum_in_amount_band
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount, sale_id;
~~~

This is the sum of rows whose amount values fall within a logical band around the current value, not the sum of the 100 preceding rows. All rows with the same amount as the current row also belong to the peer group and are summed together.

### 7.1. RANGE Offsets Restrict the Number of Sort Keys

For `RANGE` frames using offsets such as `n PRECEDING`, `n FOLLOWING`, or intervals, Oracle requires the analytic `ORDER BY` to have **a single sort expression**. The reason is that the offset must apply along a single value domain.

Valid example:

~~~sql
ORDER BY amount
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

Example that violates RANGE offset rules:

~~~sql
ORDER BY amount, sale_id
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

If you need a secondary key to distinguish records while still needing a numeric band on amount, consider `RANGE` on amount alone or use `ROWS` with full ordering depending on business semantics. Certain `RANGE` frames using only `UNBOUNDED` and `CURRENT ROW` allow multiple sort expressions; check the Oracle syntax for your exact release when combining multiple keys.

## 8. Frames by Time Interval

A common requirement is "total revenue over the last seven days". This is a window by **time value**, so it typically fits `RANGE` with an interval.

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date
        RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW
    ) AS amount_last_7_days
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

The frame is defined by the current row's `SALE_DATE` and an interval reaching seven days back. All transactions on the current date belong to the same peer group and receive the same sum in that frame.

### 8.1. Time-Based RANGE vs. Row-Count ROWS

Compare:

~~~sql
-- Up to seven most recent records (current row + six preceding rows).
ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
~~~

~~~sql
-- Rows within a seven-day time span looking back from the current timestamp/date.
RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW
~~~

If a single day has 100 transactions:

- `ROWS` takes at most seven transactions by row position.
- `RANGE` can include all 100 transactions on that date, plus transactions on earlier dates within the interval.

If a day has no transactions:

- `ROWS` still counts actual preceding records and does not create rows for missing days.
- `RANGE` also does not generate rows for missing days; it only selects existing rows whose time values fall within the range.

To report one row for every day, including days with no transactions, build a calendar/date dimension and LEFT JOIN aggregated data onto the calendar.

### 8.2. Data Type of the Time Key

With `DATE` or `TIMESTAMP`, RANGE offsets should be expressed using an appropriate interval. For example, `INTERVAL '7' DAY` is a day/time interval; `INTERVAL '1' MONTH` is a year/month interval. Do not arbitrarily pass an integer as a day count when the sort expression is TIMESTAMP if exact datetime semantics are needed; choose an interval and verify data types.

## 9. Commonly Used Frames

| Goal | Frame | Meaning |
| --- | --- | --- |
| Row-by-row running total | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From start of partition to current row |
| Value-based running total, grouping peer rows | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From start of partition to current sort value, including all peers |
| Three-row average | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Current row and up to two preceding rows |
| Symmetric three-row window | `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | Preceding row, current row, following row |
| Entire partition | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Every row in the partition |
| From current to end of partition | `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Current row and following rows |
| Numeric value range | `RANGE BETWEEN 100 PRECEDING AND CURRENT ROW` | Sort values within a 100-unit span up to current |
| Time interval | `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW` | Rows within a seven-day lookback interval |

`ROWS` is the natural choice when the business speaks in terms of **N records**. `RANGE` is the natural choice when the business speaks in terms of **a value span** such as monetary amount or time.

## 10. LAST_VALUE and the Default Frame Trap

`LAST_VALUE` is the classic example showing how the default frame affects results.

### 10.1. LAST_VALUE Does Not Default to the Last Row of the Partition

Example:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
    ) AS last_value_default
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Because `ORDER BY` is present without an explicit frame, Oracle uses the default frame from `UNBOUNDED PRECEDING` to `CURRENT ROW` under `RANGE`. With unique ordering in this example, the last row in the current frame is the current row itself. Thus `LAST_VALUE` usually returns that row's own amount, not the amount of the last transaction in the entire partition.

### 10.2. Retrieving the Value at the Last Row of the Partition

If you want the value of the last row ordered by date and ID:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS partition_last_amount
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

The frame spans the entire partition, so every row in department 10 receives the amount of the final transaction by `SALE_DATE, SALE_ID`, which is 100 in the lab data.

### 10.3. FIRST_VALUE and NTH_VALUE

`FIRST_VALUE` and `NTH_VALUE` are also affected by the frame. If you want the first or partition-wide value in a deterministic order, explicitly declare an appropriate frame and tie-breaker. Do not confuse `FIRST_VALUE`/`LAST_VALUE` with `MIN`/`MAX`: value functions return values by ordered position, whereas MIN/MAX return the smallest/largest values by comparison.

## 11. Which Analytic Functions Use a Window Frame?

Not every analytic function accepts `ROWS` or `RANGE`.

| Function group | Examples | Window frame? |
| --- | --- | --- |
| Analytic aggregates | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` | Yes |
| Analytic value functions | `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | Yes |
| Ranking | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE` | Does not use ROWS/RANGE frame |
| Offset | `LAG`, `LEAD` | Does not use ROWS/RANGE frame |
| Distribution | `CUME_DIST`, `PERCENT_RANK`, `PERCENTILE_CONT` | Per each function's own syntax; do not add a frame arbitrarily |

Invalid example:

~~~sql
RANK() OVER (
    ORDER BY amount DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

`RANK` does not accept a windowing clause like analytic aggregates. To control ties, adjust `ORDER BY` inside RANK; do not try to fix it with ROWS/RANGE.

## 12. Boundary Rules and How to Read Frames

### 12.1. Boundaries Are Evaluated in Analytic Order

With:

~~~sql
ROWS BETWEEN 2 PRECEDING AND 1 FOLLOWING
~~~

Oracle includes at most:

- Two preceding rows.
- The current row.
- One following row.

At most four rows. At the start or end of a partition, rows beyond the partition boundaries do not exist, so the frame is smaller.

### 12.2. Start Cannot Come After End

A frame must have valid boundary ordering. For example, `BETWEEN CURRENT ROW AND 2 PRECEDING` is invalid because the end boundary precedes the start boundary in frame order. Check boundary directions carefully when combining PRECEDING/FOLLOWING.

### 12.3. UNBOUNDED FOLLOWING and PRECEDING

- `UNBOUNDED PRECEDING` can only be used as the start boundary.
- `UNBOUNDED FOLLOWING` can only be used as the end boundary.
- `CURRENT ROW` has different meanings: with ROWS it is the current physical row; with RANGE it is the current peer group.

### 12.4. NULLs in Analytic Ordering

If a sort key contains NULLs, NULL ordering depends on `NULLS FIRST`/`NULLS LAST` or the ASC/DESC default. Rows with the same sort value (including NULL values sorted under the same rule) can be peers. For order-sensitive calculations, explicitly specify NULL placement and any required secondary key.

Example:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date ASC NULLS LAST, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

## 13. Determinism and Output Ordering

Three orderings are easily confused:

1. **Physical storage order** of rows in a table: no guarantee for applications to rely on.
2. **Analytic ORDER BY** inside `OVER(...)`: defines the ordering used by the analytic function and frame.
3. **Outermost ORDER BY**: defines the order of rows returned to the client.

Example:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
    ) AS row_no
FROM lab_window_sales
WHERE department_id = 10
ORDER BY row_no;
~~~

`ROW_NUMBER` uses analytic ordering; the outer `ORDER BY row_no` controls display order. If the outer `ORDER BY` is omitted, the client is not guaranteed to receive rows ordered by `ROW_NO`.

With `ROWS`, analytic ordering should be unique if per-row results must be deterministic. With `RANGE`, peer rows intentionally share a frame; adding a unique key to analytic ordering changes the peer group definition.

## 14. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Running total jumps by date instead of per transaction | Default frame is RANGE and dates have peer rows | Use ROWS with a unique sort key if per-record totals are needed |
| Two rows on the same date receive the same total | RANGE CURRENT ROW includes the entire peer group | Expected behavior; keep RANGE if grouping by date |
| ROWS results vary across executions | ORDER BY has duplicate keys without deterministic physical order | Add a unique tie-breaker such as SALE_ID |
| RANGE offset errors with multiple ORDER BY columns | RANGE offset requires a single sort expression | Use only one logical key for RANGE or switch to ROWS as needed |
| Three-row average interpreted as three days | ROWS counts records, not time spans | Use RANGE interval for time windows |
| Seven-day average interpreted as seven transactions | Used ROWS instead of RANGE | Choose a frame based on date/interval values |
| LAST_VALUE returns current row's value | Default frame ends at CURRENT ROW | Use a frame ending at UNBOUNDED FOLLOWING if partition end is needed |
| RANK errors when adding ROWS | Ranking functions do not accept window frames | Use ORDER BY and RANK's peer rules |
| Query output is not in analytic order | Only ORDER BY inside OVER was specified | Add an outermost ORDER BY |
| Adding SALE_ID removes ties | Peer group is determined by all ORDER BY keys | Add a tie-breaker to a function only if ties should be broken |
| Report misses dates with no transactions | RANGE does not auto-generate missing date rows | Use a calendar/date dimension and LEFT JOIN |

## 15. Practice Exercises

Use `LAB_WINDOW_SALES` from section 2. Predict the results before running the queries.

### Exercise 1 — Comparing Default Frame and Explicit RANGE

Write two expressions:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

and:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Compare results for transactions on 2024-01-01 and 2024-01-08. Explain why each pair receives the same total.

### Exercise 2 — Row-by-Row Running Total

Use `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` and `ORDER BY sale_date, sale_id`. Verify the six results for department 10. Then remove `SALE_ID` and explain why order among same-day transactions is no longer guaranteed.

### Exercise 3 — Three-Record Moving Average

Use `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`. Record the frame for each `SALE_ID` and compute the average. Explain why the number of transactions in the frame at the start of the partition is less than three.

### Exercise 4 — Seven-Day Window

Use `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW`. For each date in department 10, list which transaction dates fall into the frame. Compare with `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`.

### Exercise 5 — Peer Rows and RANK

Run `RANK()` and `DENSE_RANK()` ordered by `AMOUNT DESC`. Observe the two transactions with amount 100. Add `SALE_ID` to the analytic ordering and explain why they are no longer tied.

### Exercise 6 — LAST_VALUE

Run `LAST_VALUE(amount)` with the default frame, then with:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Explain why the second result is the amount of the last transaction in the partition on every row.

### Exercise 7 — One Row per Day

Create a CTE aggregating revenue by `DEPARTMENT_ID, SALE_DATE`, then compute a running total over the daily results. Compare with computing directly over individual transactions using RANGE. Identify when you should pre-aggregate so each row represents one day.

### Exercise 8 — Designing KPIs

A dashboard needs two metrics:

- Cumulative amount incremented after each transaction in chronological order.
- Total amount over the last seven days.

Write the two corresponding analytic expressions. State the sort key, tie-breaker, and frame for each metric.

## 16. Lab Data Cleanup

Run only in the lab schema you created, after finishing the exercises:

~~~sql
DROP TABLE lab_window_sales PURGE;
~~~

`PURGE` bypasses the recycle bin. Do not run this command on business tables or tables you do not own.

## Summary

`ROWS` defines the frame by the **physical number of rows** before/after the current row; `RANGE` defines the frame by **sort key value** and includes peer rows. For analytic functions that have `ORDER BY` without a frame, Oracle defaults to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. This is why default running totals can update by peer group rather than record by record.

Choose `ROWS` when the requirement calls for N transactions or a specific row order; choose `RANGE` when the requirement calls for a numeric band or time interval. When using ROWS, add a tie-breaker key for stable results. When using RANGE, understand peer groups and the single-sort-expression limit for offsets. For `LAST_VALUE`, declare a frame extending to `UNBOUNDED FOLLOWING` if the partition's final value is needed. Finally, always distinguish analytic `ORDER BY` from the outermost `ORDER BY` so results are both computed accurately and displayed in the intended order.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — partitioning, analytic ordering, and windowing clause semantics.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — ROWS/RANGE syntax and frame restrictions.
- [Oracle Database SQL Language Reference — SUM (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SUM.html) — SUM in aggregate and analytic forms.
- [Oracle Database SQL Language Reference — LAST_VALUE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAST_VALUE.html) — window frame effects on LAST_VALUE.
- [Oracle Database SQL Language Reference — RANK (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html) — handling peer rows.

When using an Oracle release other than 19c, consult the SQL Language Reference for that specific version, especially for RANGE offset restrictions, interval types, and windowing clause syntax.
