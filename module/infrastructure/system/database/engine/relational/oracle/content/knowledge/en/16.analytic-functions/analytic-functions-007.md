# Running SUM/AVG and Moving Averages in Oracle

## 1. From Group Aggregation to Row-by-Row Calculation

A revenue report often needs multiple views of the same data:

- Cumulative revenue from the start of the period up to each day.
- Running balance for each account after every transaction.
- Average revenue over the last three months.
- Seven-day moving average to smooth out fluctuations.
- Running average from the beginning of the year to the current point in time.

With `GROUP BY` alone, Oracle collapses multiple rows into one row per group. However, for running calculations or moving averages, we usually want to **preserve every original row** and attach a calculated column computed over a window of rows or values around the current row. This is the role of **analytic functions**.

Two core functions:

- `SUM(...) OVER (...)`: computes a sum over a window of rows, typically used for running totals or rolling sums.
- `AVG(...) OVER (...)`: computes an average over that window, typically used for running averages or moving averages.

Example of daily revenue data:

| Date | Revenue |
|---|---:|
| 01/11 | 100 |
| 02/11 | 150 |
| 03/11 | 50 |
| 04/11 | 200 |

The running totals are `100`, `250`, `300`, `500` respectively. The three-day moving average on 03/11 is `(100 + 150 + 50) / 3 = 100`; on 04/11 it is `(150 + 50 + 200) / 3 = 133.33`.

This lesson belongs to the **Analytic Functions** chapter and covers `OVER` syntax, partitioning and ordering, `ROWS`/`RANGE` window frames, computing running totals/averages, moving averages by observation count or by time interval, the impact of NULLs and missing periods, and query patterns applicable in Oracle reports.

## 2. Structure of an Analytic Function

General syntax:

```sql
aggregate_function(expression)
OVER (
    [PARTITION BY partition_expression]
    [ORDER BY sort_expression]
    [windowing_clause]
)
```

For `SUM` and `AVG`, the `OVER` clause defines the set of rows that the function evaluates for each output row.

| Component | Role |
|---|---|
| `SUM(amount)` | Computes the sum of expression `amount` within the window |
| `AVG(amount)` | Computes the average of expression `amount` within the window |
| `PARTITION BY account_id` | Divides data into independent groups; each account has its own window |
| `ORDER BY transaction_date` | Defines row ordering for running or sliding calculations |
| `ROWS` / `RANGE` | Defines window boundaries around the current row |

### 2.1. Difference Between GROUP BY and OVER

`GROUP BY`:

```sql
SELECT account_id,
       SUM(amount) AS account_total
FROM transactions
GROUP BY account_id;
```

The query returns one row per account.

Analytic function:

```sql
SELECT transaction_id,
       account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
       ) AS account_total
FROM transactions;
```

The query still returns every transaction while repeating the account total across all rows belonging to the same account.

**Analytic functions do not collapse rows into a single group row.** They compute over a window and attach the result to each row in the result set.

### 2.2. Without PARTITION BY

If `PARTITION BY` is omitted, the window operates over the entire result set of the query block:

```sql
SELECT transaction_id,
       amount,
       SUM(amount) OVER () AS grand_total
FROM transactions;
```

`GRAND_TOTAL` is the sum of all rows entering the analytic function. Each row still appears individually.

### 2.3. PARTITION BY Separates Independent Series

```sql
SELECT account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
       ) AS account_total
FROM transactions;
```

Account 10's total does not mix with account 20's transactions. For account balances, running revenue, or per-customer averages, `PARTITION BY` is usually indispensable.

## 3. Running SUM (Running Total)

A **running total** is the sum from the start of a sequence up to the current row. In Oracle, the explicit syntax is:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Meaning:

- `PARTITION BY account_id`: resets the sum when moving to another account.
- `ORDER BY transaction_date, transaction_id`: defines transaction ordering.
- `UNBOUNDED PRECEDING`: starts from the first row in the partition.
- `CURRENT ROW`: ends at the current row.
- `ROWS`: the frame is defined by physical row count in the chosen order.

### 3.1. Running Revenue Total Example

Suppose table `daily_sales` has one row per day:

| sale_day | revenue |
|---|---:|
| 01/11/2026 | 100 |
| 02/11/2026 | 150 |
| 03/11/2026 | 50 |
| 04/11/2026 | 200 |

Query:

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_revenue
FROM daily_sales
ORDER BY sale_day;
```

Result:

| sale_day | revenue | running_revenue |
|---|---:|---:|
| 01/11 | 100 | 100 |
| 02/11 | 150 | 250 |
| 03/11 | 50 | 300 |
| 04/11 | 200 | 500 |

### 3.2. Running Total per Account

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

When switching to another account, the sum resets. If `transaction_date` can repeat, add a tie-breaker key such as `transaction_id` so per-row results are deterministic.

### 3.3. Calculating a Running Balance

If `amount` is the transaction amount, credits can be represented as positive and debits as negative:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS movement_balance
FROM account_transactions
ORDER BY account_id, transaction_date, transaction_id;
```

If the account has an opening balance, add that balance:

```sql
SELECT t.account_id,
       t.transaction_id,
       t.transaction_date,
       t.amount,
       b.opening_balance
       + SUM(t.amount) OVER (
             PARTITION BY t.account_id
             ORDER BY t.transaction_date, t.transaction_id
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS closing_balance
FROM account_transactions t
JOIN account_opening_balance b
  ON b.account_id = t.account_id
ORDER BY t.account_id, t.transaction_date, t.transaction_id;
```

This example assumes each account has exactly one opening balance row. If the balance table has multiple records per account, normalize or aggregate before joining so transactions are not duplicated.

### 3.4. Monthly Running Total

If a table has multiple transactions per month and you want one row per month:

```sql
WITH monthly_revenue AS (
    SELECT TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS revenue
    FROM sales
    GROUP BY TRUNC(sale_date, 'MM')
)
SELECT month_start,
       revenue,
       SUM(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_revenue
FROM monthly_revenue
ORDER BY month_start;
```

`GROUP BY` creates the monthly grain first; the analytic function then computes the running total over those monthly rows. If a month has no transactions, that month will not appear in `monthly_revenue` automatically; the calendar section below addresses this situation.

## 4. Running AVG (Running Average)

A **running average** is the average of all values from the beginning of the series up to the current row:

```sql
AVG(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Example with values `100, 150, 50, 200`:

| Row | Value | Running total | Running average |
|---:|---:|---:|---:|
| 1 | 100 | 100 | 100 |
| 2 | 150 | 250 | 125 |
| 3 | 50 | 300 | 100 |
| 4 | 200 | 500 | 125 |

Query:

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_average
FROM daily_sales
ORDER BY sale_day;
```

`AVG` automatically ignores NULL values in the expression. Therefore, the denominator is the count of non-NULL values encountered, not necessarily the row count.

### 4.1. Running Average per Account

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       AVG(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg_amount
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Each account maintains its own average, updated after each transaction in the defined order.

### 4.2. Running Average Is Not Moving Average

| Type | Calculation scope | Characteristic |
|---|---|---|
| Running average | From start of partition to current row | Expanding window |
| Moving average | A bounded-width window around the current row | Sliding window across the series |

For example, with four values `100, 150, 50, 200`:

- Running average: `100`, `125`, `100`, `125`.
- Three-row moving average: `100`, `125`, `100`, `133.33`.

The two calculations can match on the first few rows while carrying different meanings.

## 5. Row-Based Moving Average with ROWS

A **moving average** computes the average over a window of finite size. For the three most recent observations, use:

```sql
AVG(amount) OVER (
    ORDER BY sale_day
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

`2 PRECEDING` means two rows before the current row; combined with `CURRENT ROW`, this creates up to three rows.

### 5.1. Three-Day Observation Moving Average Example

| Date | Revenue | 3-row moving average |
|---|---:|---:|
| 01/11 | 100 | 100 |
| 02/11 | 150 | 125 |
| 03/11 | 50 | 100 |
| 04/11 | 200 | 133.33 |

Query:

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_rows
FROM daily_sales
ORDER BY sale_day;
```

On the first two rows, the window does not yet have three rows, so Oracle averages over the available rows. This is the default frame behavior; it does not fabricate dummy rows to reach three.

### 5.2. Three-Row Moving Sum

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_sum_3_rows
FROM daily_sales
ORDER BY sale_day;
```

`SUM` and `AVG` use the same window definition; only the aggregation inside differs.

### 5.3. Window of the Seven Most Recent Observations

```sql
AVG(metric_value) OVER (
    PARTITION BY entity_id
    ORDER BY observation_date, observation_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS moving_avg_7_observations
```

This is the average over at most seven recent **observation rows** per entity. If one day has two rows, both occupy positions in the window; if one day has no rows, the window still spans seven existing rows.

Therefore, `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` **does not automatically mean seven calendar days**. It means at most seven rows in the ordering.

### 5.4. Symmetric Window Around the Current Row

You can average over two preceding rows, the current row, and two following rows:

```sql
AVG(metric_value) OVER (
    PARTITION BY entity_id
    ORDER BY observation_date, observation_id
    ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
) AS centered_avg_5_rows
```

This is a **centered moving average**. It uses future data relative to the current row, making it suitable for historical analysis and post-hoc series smoothing, but unsuitable when a metric must rely only on information known at that point in time.

## 6. ROWS vs. RANGE: Two Different Ways to Define a Window

This is the most important aspect when designing moving averages.

- `ROWS`: defines the window by **row count** before/after the current row.
- `RANGE`: defines the window by **value interval** of the sort expression; for dates/timestamps, time intervals can be used.

### 6.1. ROWS by Observation Count

```sql
AVG(amount) OVER (
    ORDER BY sale_date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

At most the seven most recent rows, regardless of the time gap between them.

If data has dates 01, 02, 10, 11:

- The row on day 10 still includes the two preceding rows from days 01 and 02 under a three-row frame.
- Calendar spacing between rows is ignored in ROWS.

### 6.2. RANGE by Date Interval

If you need the average of the last seven calendar days, you can use:

```sql
AVG(daily_amount) OVER (
    PARTITION BY account_id
    ORDER BY activity_day
    RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW
) AS moving_avg_7_calendar_days
```

With `activity_day` as a suitable DATE or TIMESTAMP, the frame starts at the current timestamp/date minus six days and ends at the current value. The window covers roughly seven days including the current day per the chosen bounds.

Interval-based RANGE frames use a datetime sort expression; Oracle has specific restrictions on RANGE offsets. When using an offset such as `INTERVAL '6' DAY PRECEDING`, keep a single compatible datetime sort key expression in the analytic `ORDER BY`.

### 6.3. Example Comparing ROWS and RANGE

Suppose the data is:

| Date | Value |
|---|---:|
| 01/11 | 10 |
| 02/11 | 20 |
| 10/11 | 30 |
| 11/11 | 40 |

On 10/11:

- `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` includes 01/11, 02/11, and 10/11 (the three available rows).
- `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` only includes rows from 04/11 through 10/11, which is solely the value 30.

The two results differ because one frame counts rows while the other evaluates a date span.

### 6.4. RANGE and Rows with Matching ORDER BY Values

With `RANGE`, rows with identical sort key values are **peers**. A RANGE frame ending at `CURRENT ROW` includes all peers sharing the same sort value. Consequently, rows on the same date can receive the same daily running total or moving average.

Example:

```sql
SELECT transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           ORDER BY transaction_date
           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS daily_running_total
FROM transactions;
```

If multiple transactions share `transaction_date`, that day's total appears identically on every row of that day because the RANGE window includes peers. If you want the total to increment after each transaction, use `ROWS` and add a unique ordering key:

```sql
SUM(amount) OVER (
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

### 6.5. RANGE with Datetimes vs. ROWS with Irregular Data

Choose according to the question:

| Question | Appropriate frame |
|---|---|
| Average of the last 7 measurements | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` |
| Average of the last 7 calendar days | `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` |
| Sum from series start to current transaction | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` + unique ordering |
| Daily total, all same-day transactions share the same total | `RANGE` by date |
| Average of the last 3 observed months | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` after ensuring one row per month |
| Average over the 90 days preceding the current time | `RANGE` with an appropriate time interval |

Do not choose ROWS or RANGE just because a sample SQL snippet uses it. Determine whether the window is defined by **number of observations** or **time span**.

## 7. Default Window Frame When ORDER BY Is Present

In Oracle, if an analytic function has `ORDER BY` without an explicit windowing clause, the default is usually:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Therefore:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date
)
```

is not necessarily equivalent to:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

When duplicate dates exist, default RANGE includes peers sharing the same sort key; row-by-row ROWS can yield different results. To avoid forcing readers to remember defaults, **write the window frame explicitly** when computing running or sliding metrics.

## 8. Calendar-Day Moving Averages and Missing Dates

A transaction table usually has no rows for days with zero transactions. If you use:

```sql
AVG(daily_revenue) OVER (
    ORDER BY activity_day
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

that is the average of at most seven **days that have rows**, not seven calendar days.

To compute a seven-calendar-day average, decide how missing days should be handled:

1. Should a day with no transactions be treated as zero revenue?
2. Or does a missing row mean data has not been loaded yet, requiring NULL?
3. Should weekends/holidays be included in the denominator?
4. Is one row per account/day needed in the calendar?

### 8.1. Generating a Date Calendar and Filling 0 When No Transactions Exist

Suppose business rules define a day with no transactions as 0 revenue:

```sql
WITH calendar_days AS (
    SELECT DATE '2026-11-01' + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <= 14
),
daily_revenue AS (
    SELECT TRUNC(sale_date) AS sale_day,
           SUM(amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE '2026-11-01'
      AND sale_date <  DATE '2026-11-15'
    GROUP BY TRUNC(sale_date)
),
complete_series AS (
    SELECT c.calendar_day,
           NVL(d.revenue, 0) AS revenue
    FROM calendar_days c
    LEFT JOIN daily_revenue d
      ON d.sale_day = c.calendar_day
)
SELECT calendar_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY calendar_day
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS moving_avg_7_days
FROM complete_series
ORDER BY calendar_day;
```

Because `complete_series` has exactly one row per day, seven rows correspond to seven calendar days. `NVL(d.revenue,0)` converts days with no transactions into 0 per the assumed business rule.

### 8.2. If a Missing Row Means Data Is Not Yet Loaded

If a day without records indicates missing data, do not automatically replace it with 0. Keep NULL:

```sql
complete_series AS (
    SELECT c.calendar_day,
           d.revenue
    FROM calendar_days c
    LEFT JOIN daily_revenue d
      ON d.sale_day = c.calendar_day
)
```

Then `AVG(revenue)` ignores NULL days, so the denominator is the number of days with non-NULL revenue in the window. If you must only publish the average when all seven days have data, also check `COUNT(revenue)` over the same window.

### 8.3. Shared Calendar Table

In long-term reporting systems, consider a calendar dimension containing:

- `calendar_date`.
- `is_business_day`.
- `is_holiday`.
- `week_start`, `month_start`, `quarter_start`.
- `fiscal_period_id`.
- `business_day_sequence`.

A calendar generates complete day/month series, standardizes holiday handling, and lets multiple reports share one period definition.

## 9. Monthly Moving Averages

If each month already has exactly one row, the last three months' average can be written as:

```sql
SELECT month_start,
       revenue,
       AVG(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_months
FROM monthly_revenue
ORDER BY month_start;
```

However, if February has no row, a three-row window at March may contain January, March, and another observed month rather than the last three consecutive calendar months. A monthly calendar is needed if business rules require three consecutive calendar periods.

### 9.1. Generating a Complete Monthly Series

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 12
),
monthly_revenue AS (
    SELECT TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE '2026-01-01'
      AND sale_date <  DATE '2027-01-01'
    GROUP BY TRUNC(sale_date, 'MM')
),
complete_months AS (
    SELECT c.month_start,
           NVL(m.revenue, 0) AS revenue
    FROM calendar_months c
    LEFT JOIN monthly_revenue m
      ON m.month_start = c.month_start
)
SELECT month_start,
       revenue,
       AVG(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_calendar_months
FROM complete_months
ORDER BY month_start;
```

This example treats months without transactions as 0 revenue. If missing rows mean missing source data, remove `NVL` and establish a policy for publishing averages based on the count of periods with data.

### 9.2. Comparison with RANGE Using a Month INTERVAL

With one row per month and the sort key as the first day of the month, you can consider a time-interval RANGE window:

```sql
AVG(revenue) OVER (
    ORDER BY month_start
    RANGE BETWEEN INTERVAL '2' MONTH PRECEDING AND CURRENT ROW
)
```

This frame considers sort key values from two months earlier up to the current month. However, it does not generate missing months; if a month is missing, the average only computes over existing non-NULL rows. If exactly three monthly periods are required, a calendar scaffold with ROWS is usually easier to control.

## 10. Handling NULLs in SUM and AVG

`SUM` and `AVG` ignore NULL values in the aggregated expression.

Suppose a window contains the values:

```text
10, 20, NULL, 30
```

Results:

- `SUM(value)` = 60.
- `AVG(value)` = 20.
- `COUNT(value)` = 3.
- `COUNT(*)` = 4.

### 10.1. Running Total When Amount Is NULL

```sql
SELECT transaction_id,
       amount,
       SUM(amount) OVER (
           ORDER BY transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions;
```

If a row has `amount IS NULL`, that row contributes nothing to the sum. The accumulated sum continues based on non-NULL values encountered.

If all values in the window are NULL, `SUM` returns NULL. If business rules require displaying 0 when no figures exist yet:

```sql
NVL(
    SUM(amount) OVER (
        ORDER BY transaction_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    0
) AS running_sum_display
```

This changes the display output. Distinguish "no values yet" from "sum is genuinely 0".

### 10.2. AVG Ignores NULLs and Does Not Treat NULL as 0

```sql
AVG(amount) OVER (
    ORDER BY transaction_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

If the window contains `10, NULL, 30`, the result is 20, not 13.33. The denominator includes only the two non-NULL values.

If business rules require treating NULL as 0:

```sql
AVG(NVL(amount, 0)) OVER (
    ORDER BY transaction_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

The result in this example is 13.33. This is a different metric; use it only when NULL is genuinely defined as zero.

### 10.3. Counting Observations in the Window

```sql
SELECT observation_date,
       metric_value,
       COUNT(*) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS row_count_7,
       COUNT(metric_value) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS non_null_count_7,
       AVG(metric_value) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS moving_average
FROM metrics;
```

The two counts clarify how many rows and how many actual non-NULL values contributed to the average.

### 10.4. Returning an Average Only When Three Valid Values Exist

Oracle does not have a direct `min_periods` parameter like some data analysis libraries. You can combine `COUNT` and `AVG` over the same frame:

```sql
SELECT observation_date,
       metric_value,
       CASE
           WHEN COUNT(metric_value) OVER (
                    ORDER BY observation_date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) = 3
           THEN AVG(metric_value) OVER (
                    ORDER BY observation_date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                )
       END AS full_3_value_average
FROM metrics
ORDER BY observation_date;
```

If fewer than three non-NULL values exist, `FULL_3_VALUE_AVERAGE` is NULL. If the requirement is three **rows** regardless of NULL measures, replace `COUNT(metric_value)` with `COUNT(*)`; these express two different policies.

## 11. Ordering: Tie-Breakers and Determinism

Running calculations depend on order. If multiple rows share the same date, writing only:

```sql
ORDER BY transaction_date
```

may be insufficient to determine which row precedes which when using `ROWS`.

Add a tie-breaker key:

```sql
ORDER BY transaction_date, transaction_id
```

Example:

| transaction_id | transaction_date | amount |
|---:|---|---:|
| 101 | 01/11 | 100 |
| 102 | 01/11 | 50 |
| 103 | 02/11 | 20 |

With `ROWS`, the running total ordered by `transaction_id` is 100, 150, 170. Without a tie-breaker, the two transactions on 01/11 could be processed in an unstable order, causing intermediate per-row values to shift.

With `RANGE` by date, two transactions on the same date are peers; the total on that date includes both. This fits daily reporting, but differs from a transaction ledger requiring a balance after every individual transaction.

`ORDER BY` inside `OVER` determines calculation order; it **does not automatically sort the final result set**. To display results in the right order, add `ORDER BY` in the outer query block.

## 12. Common Window Frame Patterns

| Window frame | Meaning |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From start of partition to current row |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Up to 3 rows: 2 preceding rows and current row |
| `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | Up to 7 most recent rows |
| `ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING` | Centered window of up to 5 rows |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | From current row to end of partition |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Entire partition as a ROWS frame |
| `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` | Six days back up to current datetime sort key value |
| `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From start of sort key domain to current value, including peers |

Boundary notes:

- `PRECEDING` looks backward in analytic order.
- `FOLLOWING` looks forward in analytic order.
- `CURRENT ROW` depends on frame type: for ROWS it is the current row; for RANGE it includes peers by sort key.
- If a frame extends past the start or end of a partition, Oracle uses only the rows actually present in the partition; it does not fabricate out-of-bounds rows.

## 13. Calculating Cumulative Percentage

From a running total, you can calculate the cumulative contribution share relative to the group total:

```sql
SELECT product_id,
       sales_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY product_id
           ORDER BY sales_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount,
       SUM(amount) OVER (
           PARTITION BY product_id
       ) AS total_amount,
       SUM(amount) OVER (
           PARTITION BY product_id
           ORDER BY sales_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       )
       / NULLIF(
           SUM(amount) OVER (PARTITION BY product_id),
           0
       ) AS cumulative_share
FROM product_sales
ORDER BY product_id, sales_date, sale_id;
```

`NULLIF(total_amount,0)` avoids division-by-zero errors by returning NULL when the group total is 0. If the total can be negative or offsetting values exist, cumulative share must be carefully defined by business rules; it is not always an intuitive contribution percentage.

To display as a percentage:

```sql
100 * cumulative_share AS cumulative_percent
```

or format in the presentation layer. If rounding is needed, decide whether to round per row or only the final display value.

## 14. Conditional Running Totals

You can place `CASE` inside `SUM` to accumulate only certain transaction types:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       transaction_type,
       amount,
       SUM(
           CASE
               WHEN transaction_type = 'CREDIT' THEN amount
               ELSE 0
           END
       ) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_credit
FROM account_transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Similarly, calculate running debit:

```sql
SUM(
    CASE
        WHEN transaction_type = 'DEBIT' THEN amount
        ELSE 0
    END
) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_debit
```

If `amount` can be NULL, the CREDIT branch returns NULL and `SUM` ignores it; the ELSE 0 branch contributes 0. If you must distinguish transactions with missing amounts from transactions of another type, track an additional data flag or NULL count.

## 15. Combining Running Totals with Other Analytic Functions

A report may need a running total, running average, and sequence rank at the same time:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum,
       AVG(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg,
       ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
       ) AS transaction_sequence
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Analytic functions in the SELECT list share the same partition/order/frame when they have identical definitions. Oracle can optimize shared sorting, though the actual plan depends on the query and version.

If you need to filter on analytic results, place the query in a CTE/inline view:

```sql
WITH calculated AS (
    SELECT account_id,
           transaction_id,
           transaction_date,
           amount,
           SUM(amount) OVER (
               PARTITION BY account_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_sum
    FROM transactions
)
SELECT *
FROM calculated
WHERE running_sum > 10000;
```

Analytic functions are evaluated after clauses such as WHERE/GROUP BY/HAVING in the same query block; therefore, analytic aliases cannot be used directly in the WHERE clause of the same SELECT block. A CTE creates an outer query block to filter the computed results.

## 16. Performance and Query Design

### 16.1. Restrict Data Before Analytic Calculation

If only reporting a single year, filter the range in the query block before analytic functions run:

```sql
SELECT account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2027-01-01';
```

This calculates the running total **within the scope of 2026**. If you need a running balance since account opening while displaying only 2026 transactions, you cannot filter out pre-2026 history before computing the running sum. Compute over all necessary history inside a CTE and filter displayed rows in the outer query block.

### 16.2. Indexes and Analytic Ordering

Queries commonly partition by `account_id` and sort by `transaction_date`, `transaction_id`. An index to consider:

```sql
CREATE INDEX ix_tx_account_date_id
ON transactions (account_id, transaction_date, transaction_id);
```

An index can assist access and ordering, yet the analytic function may still require a sort depending on the plan, data range, and statistics. Do not create indexes based solely on example syntax.

### 16.3. Avoid Computing at the Wrong Grain

If the table is at transaction grain but the metric is a monthly moving average, aggregate to one row per month first. If the table is a daily snapshot but a per-transaction average is needed, keep transaction grain. Window frames only make sense when the input data grain is right.

### 16.4. Avoid TRUNC on Columns in Filter Predicates When Ranges Work

Avoid:

```sql
WHERE TRUNC(transaction_date) = DATE '2026-11-14'
```

Prefer:

```sql
WHERE transaction_date >= DATE '2026-11-14'
  AND transaction_date <  DATE '2026-11-15'
```

A half-open interval condition can utilize standard indexes on datetime columns better. The final plan still depends on data and statistics.

### 16.5. Inspect the Execution Plan

In an environment with appropriate privileges:

```sql
EXPLAIN PLAN FOR
SELECT account_id,
       transaction_date,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2027-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan. When permitted, compare against the actual execution plan and runtime statistics on production-like data.

## 17. Comprehensive Hands-On Lab

The commands below use a dedicated table in a practice schema. Only run when you have table creation privileges and do not reuse a table name already holding existing data.

### Step 1. Create the Daily Sales Table

```sql
CREATE TABLE demo_daily_sales (
    sale_day DATE NOT NULL,
    revenue NUMBER(12, 2)
);
```

### Step 2. Insert Data

```sql
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-01', 100);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-02', 150);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-03', 50);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-04', 200);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-05', NULL);

COMMIT;
```

### Step 3. Compute Running Sum and Running Average

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg
FROM demo_daily_sales
ORDER BY sale_day;
```

Observe the row with NULL revenue: sum and average do not treat NULL as 0.

### Step 4. Compute a Three-Row Moving Average

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_rows,
       COUNT(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS valid_values_in_window
FROM demo_daily_sales
ORDER BY sale_day;
```

Compare the number of rows in the window against the count of valid values.

### Step 5. Publish Average Only When Three Valid Values Exist

```sql
SELECT sale_day,
       revenue,
       CASE
           WHEN COUNT(revenue) OVER (
                    ORDER BY sale_day
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) = 3
           THEN AVG(revenue) OVER (
                    ORDER BY sale_day
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                )
       END AS full_window_avg
FROM demo_daily_sales
ORDER BY sale_day;
```

### Step 6. Compare ROWS and RANGE

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS avg_3_rows,
       AVG(revenue) OVER (
           ORDER BY sale_day
           RANGE BETWEEN INTERVAL '2' DAY PRECEDING AND CURRENT ROW
       ) AS avg_3_calendar_days
FROM demo_daily_sales
ORDER BY sale_day;
```

In the sample data, each day has one row, so the two windows may yield identical results. Add a missing day or multiple rows on the same day to observe the difference.

### Step 7. Test Data with Multiple Rows on the Same Day

```sql
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-03', 25);
COMMIT;
```

Re-run the ROWS/RANGE query. `ROWS` computes row by row and requires deterministic ordering for stable results; date-based `RANGE` treats rows on the same day as peers.

### Step 8. Clean Up the Practice Table

Only when certain this is the table just created and the data is no longer needed:

```sql
DROP TABLE demo_daily_sales PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data, bypassing the recycle bin per command behavior; this is DDL with an implicit commit. Do not run on business tables or shared objects.

## 18. Common Misconceptions

| Misconception | Reality |
|---|---|
| `SUM(...) OVER (ORDER BY ...)` always increments row by row | Default RANGE can group peers; if row-by-row is needed, use ROWS and a tie-breaker |
| `ROWS 6 PRECEDING` means seven days | It means up to seven rows, not seven calendar days |
| `RANGE 6 DAY` automatically generates missing days | RANGE only selects existing rows within the interval; it does not fabricate rows |
| `AVG` treats NULL as 0 | AVG ignores NULL |
| No row in a month means revenue equals 0 | Only true if business rules define periods with no transactions as zero |
| A CTE with GROUP BY month automatically contains all 12 months | No; months without data do not appear without joining to a calendar |
| ORDER BY inside OVER sorts the final output | It only defines analytic calculation order; the outer query still needs ORDER BY |
| A running total in an annual report must always start from 0 | If a historical balance is needed, include opening/historical balances in the calculation |
| A ROWS frame at the start of a series automatically waits for enough rows | Oracle computes over existing rows; use COUNT if a minimum observation count is required |
| Centered moving averages can be used for real-time forecasting | A FOLLOWING window uses future data relative to the current row |
| Skipping missing months does not affect a three-month average | It turns a three-row window into three observed months, which may no longer be three calendar months |
| Every ID must be contiguous | Sequences/identity columns do not guarantee gap-free numbering |

## 19. Self-Check Questions

**Question 1.** What is the main difference between `GROUP BY` and `SUM(...) OVER (...)`?

**Answer:** `GROUP BY` collapses rows into one row per group; analytic functions keep each row and attach the result computed over a window.

**Question 2.** Which syntax calculates a running total from the start of the partition to the current row?

**Answer:** `SUM(x) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`.

**Question 3.** Why does a per-transaction running total need a tie-breaker?

**Answer:** Multiple transactions can share the same timestamp; adding a unique key determines row-by-row ordering and keeps ROWS results stable.

**Question 4.** How does `AVG` handle NULLs?

**Answer:** It ignores NULL values; the denominator is the number of non-NULL expression values in the window.

**Question 5.** How many rows at most does `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` include?

**Answer:** Seven rows, consisting of six preceding rows and the current row.

**Question 6.** How does `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` differ?

**Answer:** It selects rows whose datetime sort keys fall within six days prior up to the current value, rather than counting rows.

**Question 7.** To compute a seven-calendar-day average when source data is missing dates, what should you do?

**Answer:** Build a complete date series using a calendar or calendar dimension, join daily data onto it, and decide explicitly whether missing days count as 0 or NULL.

**Question 8.** Why shouldn't you assume a day with no rows has 0 revenue?

**Answer:** Missing rows can occur either because no transactions took place or because data has not been loaded yet; those two situations carry different meanings.

**Question 9.** What can the default window frame be when analytic ORDER BY is present?

**Answer:** `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Therefore, declare the frame explicitly when ROWS semantics are required.

**Question 10.** Why can `RANGE` give the same running total to transactions on the same day?

**Answer:** Rows with the same ORDER BY value are peers and are included together in a frame ending at CURRENT ROW.

**Question 11.** How do you return a moving average only when three non-NULL values exist?

**Answer:** Use `CASE WHEN COUNT(value) OVER (same frame) = 3 THEN AVG(value) OVER (same frame) END`.

**Question 12.** If a running total should display only this year's transactions while retaining balances from history, where do you filter the year?

**Answer:** Compute the analytic function over all required historical data inside a CTE first, then filter displayed rows in the outer query block.

## 20. Quick-Reference Rules

| Goal | Expression |
|---|---|
| Partition-wide total, repeated on each row | `SUM(x) OVER (PARTITION BY key)` |
| Running total | `SUM(x) OVER (PARTITION BY key ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Running average | `AVG(x) OVER (PARTITION BY key ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Sum/average of last three rows | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Sum/average of last seven rows | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` |
| Centered five-row window | `ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING` |
| Seven-calendar-day average | `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` |
| Three-calendar-month average | Complete monthly calendar + `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Count valid values in window | `COUNT(x) OVER (same frame)` |
| Publish only when N values exist | `CASE WHEN COUNT(x) OVER (same frame) = N THEN AVG(x) OVER (same frame) END` |

## 21. Conclusion

`SUM` and `AVG` combined with `OVER` allow calculating totals and averages over a window while keeping every row in the result. Using `UNBOUNDED PRECEDING` to `CURRENT ROW` gives a running total or running average. Using `ROWS BETWEEN N PRECEDING AND CURRENT ROW` gives a sliding window by observation row count. With `RANGE`, the window is defined by sort key value, which fits when bounding by a date/time span.

Clearly distinguish **row count** from **calendar days/months**. `ROWS` is unaware of missing periods; `RANGE` does not generate rows for periods without data. To compute calendar-period averages, generate a complete period series using a calendar or calendar dimension and decide whether missing days/months count as 0 or NULL. `AVG` ignores NULLs, so if a minimum valid observation count is required, also check `COUNT`.

Finally, make ordering deterministic with a tie-breaker when stable row-by-row results are needed, write the window frame explicitly instead of relying on default RANGE, and distinguish historical data needed for balances from the date range intended only for display. Those choices ensure running totals, running averages, and moving averages accurately reflect business meaning, even with duplicate dates, missing periods, or NULL measures.
