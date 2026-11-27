# LAG, LEAD, and Comparing with the Previous or Next Row

## Objectives

After this lesson, you will be able to:

- Use `LAG()` to read values from a preceding row and `LEAD()` to read values from a following row within a window.
- Define the comparison scope using `PARTITION BY` and row order using `ORDER BY`.
- Ensure deterministic results by adding a unique key as a tie-breaker.
- Use offsets and default values when no preceding/following row exists.
- Distinguish a non-existent row from an existing row that holds a `NULL` value.
- Compute deltas, percentage changes, state transitions, and time gaps between events.
- Recognize the limitation when time-series data has missing days/months and choose how to build a continuous time series.
- Filter window function results using a CTE/derived table and check performance using `EXPLAIN`.

## 1. What problem do LAG and LEAD solve?

In reporting, many calculations require comparing a row against the row immediately before or after it in a defined order. For example:

- Comparing this month's revenue with last month's.
- Computing how much an order amount increased or decreased compared to the same customer's previous order.
- Detecting the timestamp when an order's status changed.
- Computing the elapsed time between two consecutive events.
- Finding the next value in a price or inventory history.

These comparisons can be written using self-joins or correlated subqueries, but the SQL is often more complex. `LAG()` and `LEAD()` are window functions that read values from neighboring rows within the same window.

- `LAG(expr)` retrieves the value of expression `expr` from a row preceding the current row.
- `LEAD(expr)` retrieves the value of expression `expr` from a row following the current row.

Neither function collapses rows like `GROUP BY` does. Every input row can still appear in the output, enriched with a reference value from a preceding or following row.

## 2. LAG and LEAD syntax in MySQL

MySQL 8.0 supports window functions, including `LAG()` and `LEAD()`.

General syntax:

```sql
LAG(expr [, N [, default]]) OVER (window_specification)

LEAD(expr [, N [, default]]) OVER (window_specification)
```

Where:

- `expr`: the expression to retrieve from the neighboring row.
- `N`: the number of rows to offset from the current row; defaults to `1`.
- `default`: the value returned if the row at the requested position does not exist; defaults to `NULL`.
- `OVER (...)`: the window specification, typically containing `PARTITION BY` and `ORDER BY`.

Simple example:

```sql
SELECT
    order_id,
    customer_id,
    total_amount,
    LAG(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS previous_amount,
    LEAD(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS next_amount
FROM orders
ORDER BY created_at, order_id;
```

`previous_amount` retrieves the amount from the preceding row; `next_amount` retrieves the amount from the following row ordered by `created_at, order_id`.

Note the two `ORDER BY` positions:

- `ORDER BY` inside `OVER(...)` determines which preceding/following row the function references.
- `ORDER BY` at the end of the statement determines the order of rows returned to the client.

These two orderings may match, yet they serve distinct roles. If output must be displayed in a specific order, include `ORDER BY` in the outer query.

## 3. How does ORDER BY define previous and next rows?

`LAG()` and `LEAD()` have no built-in knowledge of chronological order, ascending IDs, or physical table order. They rely solely on the ordering declared inside `OVER(...)`.

Example retrieving point-in-time balances:

```sql
SELECT
    account_id,
    transaction_id,
    occurred_at,
    balance,
    LAG(balance) OVER (
        PARTITION BY account_id
        ORDER BY occurred_at, transaction_id
    ) AS balance_before
FROM account_transactions
ORDER BY account_id, occurred_at, transaction_id;
```

Within each account, transactions are ordered by `occurred_at`, then by `transaction_id`. `LAG(balance)` retrieves the balance of the immediately preceding transaction in that order.

### 3.1. Adding a tie-breaker for deterministic ordering

Suppose two orders share the same `created_at`. If you only write:

```sql
LAG(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY created_at
)
```

the order among orders with identical timestamps is not fully determined. Comparison results may vary depending on the execution plan or data layout.

Add a unique column:

```sql
LAG(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
```

If `order_id` is the primary key, this ordering pair uniquely determines each row's position. For audit/history tables, you might use `event_time, event_id`; for ledger/transaction tables, `posted_at, transaction_id`.

### 3.2. ASC vs. DESC changes the meaning

With:

```sql
LAG(status) OVER (
    PARTITION BY order_id
    ORDER BY changed_at ASC, history_id ASC
)
```

`LAG()` retrieves the status of the most recent older event.

If changed to `ORDER BY changed_at DESC, history_id DESC`, the preceding row in window order is a newer event. The function still obeys the specified order, yet the business meaning flips.

Choose the sort direction based on the question being answered: "the previous status in history" typically uses ascending time; "the next newer record in a newest-first list" may use descending order.

### 3.3. NULL in sort columns

If an `ORDER BY` column allows `NULL`, MySQL applies its NULL sorting rules: in ascending order, NULLs sort before non-NULL values; in descending order, NULLs sort after. This can affect which row `LAG()` or `LEAD()` picks.

If chronological order must be unambiguous, prefer a `NOT NULL` timestamp column. If NULL is valid, define the placement of NULL rows explicitly and include a unique key to break ties.

## 4. PARTITION BY creates independent comparison scopes

`PARTITION BY` splits the result set into independent groups. `LAG()` and `LEAD()` never cross partition boundaries.

For example, comparing the previous order amount for the same customer:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_order_amount
FROM orders
ORDER BY customer_id, created_at, order_id;
```

When moving to a new customer, `LAG()` resets. The first row of each customer has no preceding row in its partition and receives `NULL` unless a default is provided.

### 4.1. Without PARTITION BY

If `PARTITION BY` is omitted, the entire row set belongs to a single partition:

```sql
SELECT
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

In this case, a customer's first order may pull the previous row from a different customer. That might be desired if comparing across the entire order stream, but it is usually wrong when business rules require per-customer comparisons.

### 4.2. Multiple columns in PARTITION BY

You can partition by multiple attributes:

```sql
LAG(stock_quantity) OVER (
    PARTITION BY warehouse_id, product_id
    ORDER BY snapshot_at, snapshot_id
)
```

Each warehouse/product pair has its own sequence. Use multi-column partitioning when rows are only comparable within that exact combined scope.

## 5. LAG: reading the previous row's value

### 5.1. Retrieving the previous value

Suppose `monthly_sales` stores revenue by month:

```sql
SELECT
    store_id,
    sales_month,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sales_month
    ) AS previous_revenue
FROM monthly_sales
ORDER BY store_id, sales_month;
```

For each store, `previous_revenue` is the revenue from the preceding month row present in the dataset.

### 5.2. Computing the absolute change

```sql
WITH sales_with_previous AS (
    SELECT
        store_id,
        sales_month,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sales_month
        ) AS previous_revenue
    FROM monthly_sales
)
SELECT
    store_id,
    sales_month,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_change
FROM sales_with_previous
ORDER BY store_id, sales_month;
```

If current revenue is higher than the prior period, `revenue_change` is positive; if lower, it is negative. The first row for each store has `previous_revenue = NULL`, so the subtraction also evaluates to NULL.

### 5.3. Computing percentage change

Formula:

\[
\text{change\_percent} =
\frac{\text{current} - \text{previous}}{\text{previous}} \times 100
\]

SQL must guard against a previous value of 0 to avoid division by zero:

```sql
WITH sales_with_previous AS (
    SELECT
        store_id,
        sales_month,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sales_month
        ) AS previous_revenue
    FROM monthly_sales
)
SELECT
    store_id,
    sales_month,
    revenue,
    previous_revenue,
    100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0) AS change_percent
FROM sales_with_previous
ORDER BY store_id, sales_month;
```

`NULLIF(previous_revenue, 0)` returns NULL when the previous value is 0. In that case, percentage change is undefined under this formula and yields NULL. If business rules want a label such as "newly active" when growing from 0 to a positive number, handle it with `CASE` rather than inventing an arbitrary percentage.

## 6. LEAD: reading the next row's value

`LEAD()` is symmetric to `LAG()`: it retrieves an expression from a following row in the window order.

Example retrieving the timestamp of the next event for each order:

```sql
SELECT
    order_id,
    history_id,
    status,
    changed_at,
    LEAD(changed_at) OVER (
        PARTITION BY order_id
        ORDER BY changed_at, history_id
    ) AS next_changed_at
FROM order_status_history
ORDER BY order_id, changed_at, history_id;
```

The last row for each order has no next event and receives NULL.

### 6.1. Computing the duration until the next event

```sql
WITH event_sequence AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LEAD(changed_at) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS next_changed_at
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    status,
    changed_at,
    next_changed_at,
    TIMESTAMPDIFF(SECOND, changed_at, next_changed_at)
        AS seconds_until_next_event
FROM event_sequence
ORDER BY order_id, changed_at, history_id;
```

`TIMESTAMPDIFF()` returns NULL if `next_changed_at` is NULL. That is sensible for the final event since there is no subsequent timestamp to measure an interval against.

### 6.2. Determining how long a status remained active

You can use `LEAD()` to construct the validity interval for each status:

```sql
WITH status_intervals AS (
    SELECT
        order_id,
        status,
        changed_at AS valid_from,
        LEAD(changed_at) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS valid_to
    FROM order_status_history
)
SELECT
    order_id,
    status,
    valid_from,
    valid_to,
    TIMESTAMPDIFF(SECOND, valid_from, valid_to) AS duration_seconds
FROM status_intervals
ORDER BY order_id, valid_from;
```

`valid_to` is the timestamp when the next status begins. For the last row, the status can be treated as active up to the current time or another business cutoff; avoid injecting `NOW()` automatically if a report requires a fixed cutoff timestamp.

## 7. Offset and default value

Parameter `N` lets you look more than one row backward or forward.

### 7.1. Reading two rows backward or forward

```sql
SELECT
    order_id,
    total_amount,
    LAG(total_amount, 2) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS amount_two_orders_before,
    LEAD(total_amount, 2) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS amount_two_orders_after
FROM orders
ORDER BY customer_id, created_at, order_id;
```

`LAG(..., 2)` retrieves the value from the row two positions before the current row; `LEAD(..., 2)` retrieves the row two positions after. The offset counts rows in the ordered partition, not days or months.

### 7.2. Setting a default value when no neighbor exists

The third argument specifies the fallback value when the row at the requested offset does not exist:

```sql
SELECT
    order_id,
    total_amount,
    LAG(total_amount, 1, 0) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount_or_zero
FROM orders;
```

For each customer's first row, `LAG()` returns 0 because no previous row exists. Only use 0 if business rules define "no prior order" as 0.

### 7.3. Default argument vs. COALESCE

This is a key distinction:

```sql
SELECT
    order_id,
    LAG(total_amount, 1, 0) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS lag_default,
    COALESCE(
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ),
        0
    ) AS lag_coalesced
FROM orders;
```

- `LAG(total_amount, 1, 0)` uses 0 only when there is no preceding row. If a preceding row exists and its `total_amount` is NULL, the result is still NULL.
- `COALESCE(LAG(total_amount), 0)` replaces any NULL result with 0, covering both a missing preceding row and a preceding row whose value is NULL.

Choose the form that matches your data semantics. Do not turn NULL into 0 if NULL means "unknown" or "not recorded".

### 7.4. Offset of 0

An offset of 0 references the current row. For example, `LAG(amount, 0)` returns the current row's own value. This is rarely needed since you can select `amount` directly; use offset 0 only when expressions are built dynamically for a clear reason.

## 8. Distinguishing a missing row from a NULL value

A NULL returned by `LAG()` or `LEAD()` can mean two different things:

1. No row exists at the requested offset.
2. The row exists, but its expression `expr` evaluates to NULL.

Example:

```sql
CREATE TABLE measurements (
    sensor_id BIGINT NOT NULL,
    measured_at DATETIME NOT NULL,
    temperature DECIMAL(5,2) NULL,
    measurement_id BIGINT NOT NULL,
    PRIMARY KEY (measurement_id)
);
```

```sql
SELECT
    sensor_id,
    measurement_id,
    measured_at,
    temperature,
    LAG(temperature) OVER (
        PARTITION BY sensor_id
        ORDER BY measured_at, measurement_id
    ) AS previous_temperature,
    LAG(measurement_id) OVER (
        PARTITION BY sensor_id
        ORDER BY measured_at, measurement_id
    ) AS previous_measurement_id
FROM measurements;
```

If `previous_measurement_id` is NULL on the first row of the partition, there is no prior measurement. If `previous_measurement_id` is non-NULL while `previous_temperature` is NULL, the prior measurement exists, but no temperature was recorded.

To distinguish these two cases, retrieve a `NOT NULL` key column using the same LAG call or include a presence indicator. Do not rely solely on a nullable business column.

### 8.1. NULL treatment in MySQL

MySQL supports `RESPECT NULLS` handling for relevant window functions. This is also the default behavior: a NULL in a neighboring row is preserved and returned as-is. The `IGNORE NULLS` syntax is not supported for execution in MySQL; attempting to use it raises an error.

Consequently, `LAG(value)` inspects the strictly preceding row by position, even if that row's value is NULL. It does not automatically skip NULL rows to locate the nearest non-NULL value.

If business logic requires "the most recent preceding non-NULL value," you must build custom logic—such as numbering non-NULL rows, using auxiliary aggregate/window steps, or filtering into a subset before joining back. Any workaround must preserve row relationships and be thoroughly tested; never substitute `COALESCE()` for `RESPECT NULLS`, as the two operations have completely different semantics.

## 9. LAG/LEAD compare adjacent rows, not adjacent calendar periods

This is a very common pitfall in time-based reporting.

Suppose a revenue table contains:

| sales_month | revenue |
|---|---:|
| 2026-01 | 100 |
| 2026-02 | 120 |
| 2026-04 | 160 |

Query:

```sql
SELECT
    sales_month,
    revenue,
    LAG(revenue) OVER (ORDER BY sales_month) AS previous_revenue
FROM monthly_sales;
```

On the April row (`2026-04`), `LAG()` returns 120 from February because that is the immediately preceding row in the dataset. It does not return NULL, nor does it infer that March is missing.

If the question is "compare with the previous calendar month," you must generate every month in the reporting range and LEFT JOIN revenue onto that month series.

### 9.1. Generating a month series before using LAG

In MySQL 8.0, you can use a recursive CTE to generate the months:

```sql
WITH RECURSIVE months AS (
    SELECT CAST('2026-01-01' AS DATE) AS month_start
    UNION ALL
    SELECT month_start + INTERVAL 1 MONTH
    FROM months
    WHERE month_start < '2026-06-01'
), monthly_revenue AS (
    SELECT
        CAST(DATE_FORMAT(created_at, '%Y-%m-01') AS DATE) AS month_start,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE created_at >= '2026-01-01'
      AND created_at < '2026-07-01'
    GROUP BY CAST(DATE_FORMAT(created_at, '%Y-%m-01') AS DATE)
), complete_series AS (
    SELECT
        m.month_start,
        COALESCE(r.revenue, 0) AS revenue
    FROM months AS m
    LEFT JOIN monthly_revenue AS r
      ON r.month_start = m.month_start
), compared AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_month_revenue
    FROM complete_series
)
SELECT
    month_start,
    revenue,
    previous_month_revenue,
    revenue - previous_month_revenue AS month_change
FROM compared
ORDER BY month_start;
```

In this example, March with no orders becomes a row with revenue 0. `LAG()` on April then compares against the calendar month of March. Use `COALESCE(..., 0)` only if a month without records truly means zero revenue; if missing data could indicate a collection failure, keep NULL and distinguish data states.

### 9.2. Time intervals vs. row counts

`LAG(value, 7)` means the value seven rows back, not seven days back. If a single day has multiple rows, or if certain days are missing, those two concepts are completely different.

To compare against a specific time offset:

- Normalize data to the proper time granularity (day, week, month) before applying window functions.
- Build a calendar/date dimension to guarantee every period to be compared has a row.
- Or JOIN on a computed date key such as `DATE_SUB(current_date, INTERVAL 1 DAY)` when logic only requires a specific offset period.

## 10. Filtering LAG/LEAD results with a CTE or derived table

Window functions are evaluated after `WHERE`, `GROUP BY`, and `HAVING` within the same query block. Therefore, you cannot place `LAG()` directly in `WHERE` at the same level to filter by the computed window value.

For example, finding orders with a higher amount than the same customer's previous order:

```sql
WITH order_comparison AS (
    SELECT
        customer_id,
        order_id,
        created_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    previous_amount,
    total_amount - previous_amount AS amount_increase
FROM order_comparison
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount
ORDER BY customer_id, created_at, order_id;
```

The CTE computes `previous_amount` first; the outer query then filters on that alias.

You can also write this with a derived table:

```sql
SELECT *
FROM (
    SELECT
        customer_id,
        order_id,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
) AS order_comparison
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount;
```

CTEs are usually easier to read when a query has multiple steps or reuses results; derived tables work well when only a simple wrapper is needed.

## 11. Using LAG to detect status changes

Suppose `order_status_history` stores status transitions. You can compare the current status with the previous status:

```sql
WITH status_changes AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LAG(status) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_status
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    previous_status,
    status AS current_status,
    changed_at
FROM status_changes
WHERE previous_status IS NULL
   OR previous_status <> status
ORDER BY order_id, changed_at, history_id;
```

The condition above has one limitation: if `status` is nullable, `previous_status IS NULL` could mean either there is no previous row or the previous row had a NULL status. If you need to distinguish those cases, add `LAG(history_id)` to verify whether a preceding row exists. If `status` is `NOT NULL`, the condition above is simpler.

A cleaner approach when `status` is nullable:

```sql
WITH status_changes AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LAG(history_id) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_history_id,
        LAG(status) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_status
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    previous_status,
    status AS current_status,
    changed_at
FROM status_changes
WHERE previous_history_id IS NULL
   OR NOT (previous_status <=> status)
ORDER BY order_id, changed_at, history_id;
```

The `<=>` operator is MySQL's NULL-safe equality operator. `NOT (previous_status <=> status)` detects differences even when one side is NULL. The first row of each partition is still preserved via `previous_history_id IS NULL`.

## 12. Combining LAG and LEAD in the same window

You can use both functions to inspect previous, current, and next values together:

```sql
SELECT
    order_id,
    history_id,
    changed_at,
    status,
    LAG(status) OVER event_window AS previous_status,
    LEAD(status) OVER event_window AS next_status
FROM order_status_history
WINDOW event_window AS (
    PARTITION BY order_id
    ORDER BY changed_at, history_id
)
ORDER BY order_id, changed_at, history_id;
```

`WINDOW event_window AS (...)` names the window specification so multiple functions share the same partition and order. This avoids repeating identical window definitions in long SQL statements.

You can include multiple offset expressions:

```sql
SELECT
    account_id,
    transaction_id,
    amount,
    LAG(amount, 1) OVER w AS previous_amount,
    LAG(amount, 2) OVER w AS amount_two_rows_before,
    LEAD(amount, 1) OVER w AS next_amount
FROM account_transactions
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY occurred_at, transaction_id
)
ORDER BY account_id, occurred_at, transaction_id;
```

## 13. Practical use cases

### 13.1. Detecting gaps between events

```sql
WITH event_gaps AS (
    SELECT
        device_id,
        event_id,
        occurred_at,
        LAG(occurred_at) OVER (
            PARTITION BY device_id
            ORDER BY occurred_at, event_id
        ) AS previous_event_at
    FROM device_events
)
SELECT
    device_id,
    event_id,
    previous_event_at,
    occurred_at,
    TIMESTAMPDIFF(SECOND, previous_event_at, occurred_at) AS gap_seconds
FROM event_gaps
WHERE previous_event_at IS NOT NULL
  AND TIMESTAMPDIFF(SECOND, previous_event_at, occurred_at) > 3600
ORDER BY device_id, occurred_at, event_id;
```

This query finds gaps between consecutive events exceeding one hour. `event_id` acts as a tie-breaker when timestamps match. If a device logs multiple events at the same timestamp, the gap may be 0; that does not necessarily mean bad data.

### 13.2. Comparing inventory across two snapshots

```sql
SELECT
    warehouse_id,
    product_id,
    snapshot_at,
    quantity,
    LAG(quantity) OVER (
        PARTITION BY warehouse_id, product_id
        ORDER BY snapshot_at, snapshot_id
    ) AS previous_quantity,
    quantity - LAG(quantity) OVER (
        PARTITION BY warehouse_id, product_id
        ORDER BY snapshot_at, snapshot_id
    ) AS quantity_change
FROM inventory_snapshots
ORDER BY warehouse_id, product_id, snapshot_at, snapshot_id;
```

Each warehouse/product pair forms its own series. If you prefer computing `LAG(quantity)` only once, use a CTE to alias it and avoid duplicating the expression.

### 13.3. Finding the next price change

```sql
SELECT
    product_id,
    price,
    effective_from,
    LEAD(effective_from) OVER (
        PARTITION BY product_id
        ORDER BY effective_from, price_history_id
    ) AS next_effective_from
FROM product_price_history
ORDER BY product_id, effective_from, price_history_id;
```

The output can be used to construct validity intervals `[effective_from, next_effective_from)`. For the final row, `next_effective_from` is NULL; the application must define an open-ended boundary or a reporting cutoff.

### 13.4. Finding the previous login and time elapsed between logins

```sql
WITH login_sequence AS (
    SELECT
        user_id,
        login_id,
        logged_in_at,
        LAG(logged_in_at) OVER (
            PARTITION BY user_id
            ORDER BY logged_in_at, login_id
        ) AS previous_login_at
    FROM user_logins
)
SELECT
    user_id,
    login_id,
    logged_in_at,
    previous_login_at,
    TIMESTAMPDIFF(MINUTE, previous_login_at, logged_in_at)
        AS minutes_since_previous_login
FROM login_sequence
ORDER BY user_id, logged_in_at, login_id;
```

This is a helpful pattern for behavioral analytics, provided time zones and timestamp precision are stored consistently.

## 14. Performance and indexing

Window functions typically require rows to be ordered by partition and sort keys. On large tables, sorting can consume CPU, memory, and potentially temporary disk storage.

### 14.1. Indexing by partition and order

For the query:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

An index worth evaluating:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at, order_id);
```

The index places the partition column first, followed by the sort columns. However, whether MySQL uses the index to avoid or reduce sorting depends on the full query, predicates, sort directions, MySQL version, and execution plan.

### 14.2. Filtering rows before window evaluation

If only a specific time range is needed, a `WHERE` clause in the same query block is applied before the window function:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01';
```

This means the first row in 2026 cannot see the last order from 2025. If you need to compare the first row of the year against a prior row outside the reporting window, include earlier rows in the input set and filter dates in an outer query block.

For example, evaluate the window first and filter by date outside:

```sql
WITH sequenced_orders AS (
    SELECT
        customer_id,
        order_id,
        created_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT *
FROM sequenced_orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
ORDER BY customer_id, created_at, order_id;
```

In this version, LAG can see prior-year rows because the inner query does not filter to 2026 before computing the window. The trade-off is that the server may process more rows.

### 14.3. Using EXPLAIN

```sql
EXPLAIN
SELECT
    customer_id,
    order_id,
    created_at,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

Inspect the access path, chosen index, estimated row counts, and any sort or materialize steps. MySQL 8.0.18 and higher support `EXPLAIN ANALYZE` for eligible queries; since it executes the query, assess load before running it on production.

Do not create an index solely because `LAG()` or `LEAD()` appears in a query. Base index decisions on workload, filter selectivity, and window order. Wide indexes increase storage footprint and write overhead.

## 15. Limitations and common mistakes

| Mistake / scenario | Consequence | Resolution |
|---|---|---|
| Omitting ORDER BY inside OVER | No deterministic previous/next order | Define clear business ordering |
| Duplicate ORDER BY values without tie-breaker | Chosen previous/next row may be unstable | Append primary key or unique key to the sort list |
| Forgetting PARTITION BY | LAG/LEAD may pull data from a different group | Partition by the business grouping key |
| Assuming LAG(..., 7) means seven days ago | Offset counts rows, not time units | Build a complete date/month series or JOIN by date key |
| Assuming default replaces every NULL | Default applies only when no row exists at the offset | Use COALESCE if NULLs in existing rows must also be replaced |
| Using COALESCE and losing NULL semantics | Cannot distinguish missing data from 0 | Keep NULL or add a presence-indicator column |
| Placing LAG in same-level WHERE | Window function is not yet computed at WHERE stage | Wrap in a CTE or derived table and filter outside |
| Using IGNORE NULLS | MySQL does not support executing this null treatment | Use an alternative tested query pattern |
| Filtering date range before window when prior row is needed | First report row gets NULL despite existing prior data | Evaluate window over a wider set, then filter in outer query block |
| Ignoring indexes/sorts | Large queries may sort excessive data | Use EXPLAIN and benchmark realistically |

## 16. Quick reference queries

```sql
-- Get previous and next row per customer
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER w AS previous_amount,
    LEAD(total_amount) OVER w AS next_amount
FROM orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
ORDER BY customer_id, created_at, order_id;

-- Difference from previous row, guarded against division by zero
WITH compared AS (
    SELECT
        customer_id,
        order_id,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT
    customer_id,
    order_id,
    total_amount - previous_amount AS amount_change,
    100.0 * (total_amount - previous_amount)
        / NULLIF(previous_amount, 0) AS change_percent
FROM compared;

-- Time until next event
SELECT
    order_id,
    changed_at,
    LEAD(changed_at) OVER (
        PARTITION BY order_id
        ORDER BY changed_at, history_id
    ) AS next_changed_at
FROM order_status_history;
```

Table and column names are illustrative. Before using them, adapt to your actual schema and confirm that the keys in `PARTITION BY`/`ORDER BY` produce the right business sequence.

## 17. Pre-production checklist

- [ ] Clearly defined "previous/next row" by timestamp, ID, or business order.
- [ ] `OVER(...)` includes an explicit `ORDER BY`.
- [ ] Added a unique tie-breaker when sort keys can collide.
- [ ] `PARTITION BY` reflects the exact comparison scope.
- [ ] Offset represents the intended row count, not days/months.
- [ ] Default value is used only for missing neighbor rows.
- [ ] Distinguished non-existent rows from columns containing NULL.
- [ ] Decided whether to preserve NULL or substitute 0/another marker.
- [ ] Built a complete calendar/time series if calendar-period comparisons are needed.
- [ ] Used a CTE/derived table in an outer query block when filtering window results.
- [ ] Checked the impact of pre-window WHERE filters on preceding rows.
- [ ] Evaluated indexes and execution plans using representative data.
- [ ] Tested edge cases: single-row partitions, duplicate timestamps, and first/last rows.

## 18. Conclusion

`LAG()` and `LEAD()` make it easy to access values from preceding or following rows in a window without self-joining the table. `PARTITION BY` defines the comparison scope, `ORDER BY` defines the row ordering, offset selects the distance in rows, and default applies only when no row exists at that position.

For reliable results, declare a deterministic order with a unique tie-breaker, distinguish NULL values from non-existent rows, and remember that offsets count rows rather than time units. When calendar-period comparisons are required, construct a complete time series before applying window functions. Use CTEs to filter results after computing LAG/LEAD, and inspect execution plans on realistic data before deploying.
