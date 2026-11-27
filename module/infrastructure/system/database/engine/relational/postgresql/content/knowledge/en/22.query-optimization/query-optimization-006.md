# Optimizing Aggregations, Conditional Filtering, and Reporting Queries in PostgreSQL

Reporting queries are often written after a system has already accumulated data: daily revenue, orders by status, payment conversion rate, unique customers, top products, revenue by region, and multi-metric dashboards. At first glance they look like simple `SELECT`s with `SUM` and `GROUP BY`, yet at scale they can become the heaviest consumers of CPU, RAM, I/O, and wall-clock time.

A simple example:

```sql
SELECT
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS revenue
FROM orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND status = 'PAID'
GROUP BY region;
```

This is a reasonable query, yet to know whether it is both optimal and **business-accurate**, you must also answer:

- Is there an index supporting the time and status filters?
- How many rows does the query read before `GROUP BY`?
- If `order_items` and `payments` are joined in, will totals be multiplied by one-to-many joins?
- Does the report need **order value**, **captured payments**, **refunds**, or **net cash flow**?
- When should you use `WHERE`, `HAVING`, `FILTER (WHERE ...)`, or `CASE`?
- How expensive is `COUNT(DISTINCT customer_id)`?
- Did PostgreSQL pick `HashAggregate`, `GroupAggregate`, or parallel aggregation? Is it spilling to temp files?
- When a dashboard runs repeatedly, should you use a summary table or materialized view?
- Does filtering dates in a user's time zone still use indexes well?
- Is result accuracy preserved under concurrent updates or replica lag?

This lesson focuses on **optimizing aggregations, conditional filtering, and reporting queries in PostgreSQL** along two inseparable axes: **correctness** and **appropriate execution cost**. A fast report that doubles revenue due to a broken JOIN is far more dangerous than a slow report.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Precisely define both input and output **grain** before writing `GROUP BY`.
2. Distinguish `WHERE`, `HAVING`, and `FILTER (WHERE ...)`, using each for its proper purpose.
3. Write **conditional aggregations** with `COUNT(*) FILTER`, `SUM(...) FILTER`, and `CASE`.
4. Understand `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)`, and `NULL` behavior.
5. Prevent **join fan-out** that inflates `SUM` and `COUNT` across multiple one-to-many tables.
6. Optimize reports via **pre-aggregation**, early grouping, early filtering, and reducing intermediate rows.
7. Write **half-open interval** time filters to stay index-friendly and avoid boundary errors.
8. Use `date_trunc`, `GROUPING SETS`, `ROLLUP`, and `CUBE` for multi-level reports.
9. Read `EXPLAIN (ANALYZE, BUFFERS)` for `HashAggregate`, `GroupAggregate`, `Sort`, `Bitmap Heap Scan`, `Gather`, and temp I/O.
10. Evaluate B-trees, partial indexes, covering indexes, BRIN, partition pruning, and planner statistics.
11. Reason about `COUNT(DISTINCT)`, high-cardinality grouping, `work_mem`, and disk spills.
12. Understand benefits and risks of `MATERIALIZED VIEW`, summary tables, and incremental aggregation.
13. Distinguish report snapshots, concurrent mutations, and replica lag.
14. Design before/after measurements and monitor reports with appropriate tools.

> **Scope:** Modern PostgreSQL. Exact planner behavior varies by version, data, statistics, and configuration. DDL/DML statements here are strictly for a **resettable practice database**, never run directly on production.

---

## 2. Before Optimizing: Define Grain and Metric Semantics

**Grain** is the unit of detail represented by each row:

| Relation | What Is Each Row? | Typical Key |
| --- | --- | --- |
| `orders` | One order | `order_id` |
| `order_items` | One product line item in an order | `item_id` |
| `payment_events` | One capture or refund event | `payment_id` |
| Daily–region report | One day in one region | `report_day, region` |
| Daily–region–status report | One day, region, and status | `report_day, region, status` |

An “orders per day” report has an output grain of **day**, yet joining `order_items` turns the intermediate grain into **line item**, no longer order. Counting right after that JOIN turns a three-item order into three orders.

### 2.1. Every Metric Needs a Business Definition

Often-confused concepts:

- **Order count:** total orders.
- **Paid order count:** orders with status `PAID` per convention.
- **Gross captured payments:** sum of capture payment events.
- **Refunds:** sum of refund events.
- **Net payment flow:** captured minus refunded within the selected scope.
- **Order value:** order-level amount on the order record; may differ from actual cash captured.
- **Unique customers:** distinct `customer_id` count.
- **Average order value:** total amount of qualifying orders divided by the count of those orders.

Never label a column `revenue` and sum all `orders.total_amount` without agreeing on which statuses count and how refunds, taxes, cancellations, and returns are treated.

### 2.2. Three-Step Correctness Check

Before writing any report query:

1. Specify output grain: e.g., one row per `(UTC day, region)`.
2. Specify the **qualifying record set**: e.g., `PAID` orders; filtered by `ordered_at` or `paid_at`?
3. Specify units and formulas: `NUMERIC(14,2)`, currency, distinct customers, gross vs net of refunds.

**Query optimization must never alter metric definitions.** Two SQL queries returning different numbers because they use different business conditions are not “the same query, faster.”

---

## 3. Lab: Orders, Order Items, and Payment Events

This lab demonstrates `GROUP BY`, JOIN fan-out, and conditional aggregates.

> **Warning:** `DROP TABLE IF EXISTS` removes existing lab tables with the same names. Run only in a **dedicated test database** or resettable schema.

### 3.1. Create Schema

```sql
CREATE SCHEMA IF NOT EXISTS report_opt_lab;

DROP TABLE IF EXISTS report_opt_lab.payment_events;
DROP TABLE IF EXISTS report_opt_lab.order_items;
DROP TABLE IF EXISTS report_opt_lab.orders;

CREATE TABLE report_opt_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region TEXT NOT NULL
        CHECK (region IN ('NORTH', 'CENTRAL', 'SOUTH')),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'REFUNDED', 'CANCELED', 'PENDING')),
    ordered_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE report_opt_lab.order_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES report_opt_lab.orders(order_id),
    sku TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_amount NUMERIC(14,2) NOT NULL
        CHECK (line_amount >= 0)
);

CREATE TABLE report_opt_lab.payment_events (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES report_opt_lab.orders(order_id),
    event_type TEXT NOT NULL
        CHECK (event_type IN ('CAPTURE', 'REFUND')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    event_at TIMESTAMPTZ NOT NULL
);
```

Each order can have multiple items and multiple payment events—the exact relationship that risks **row multiplication** when joined.

### 3.2. Load 15,000 Orders

```sql
INSERT INTO report_opt_lab.orders (
    order_id, customer_id, region, status, ordered_at, total_amount
)
SELECT
    g.n::BIGINT,
    (g.n % 1000) + 1,
    CASE (g.n % 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'CENTRAL'
        ELSE 'SOUTH'
    END,
    CASE (g.n % 10)
        WHEN 0 THEN 'REFUNDED'
        WHEN 1 THEN 'CANCELED'
        WHEN 2 THEN 'PENDING'
        ELSE 'PAID'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 120) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    ROUND(20::NUMERIC + (g.n % 49999)::NUMERIC / 100, 2)
FROM generate_series(1, 15000) AS g(n);
```

Order timestamps span early 2026 in UTC; `status` and `region` distribute evenly across groups.

### 3.3. Three Line Items per Order

```sql
INSERT INTO report_opt_lab.order_items (
    order_id, sku, category, quantity, line_amount
)
SELECT
    o.order_id,
    'SKU-' || LPAD(
        (1 + (o.order_id + x.i) % 50)::TEXT, 3, '0'
    ),
    CASE x.i
        WHEN 1 THEN 'ACCESSORY'
        WHEN 2 THEN 'MAIN'
        ELSE 'SERVICE'
    END,
    1,
    CASE x.i
        WHEN 1 THEN ROUND(o.total_amount * 0.20, 2)
        WHEN 2 THEN ROUND(o.total_amount * 0.30, 2)
        ELSE o.total_amount
           - ROUND(o.total_amount * 0.20, 2)
           - ROUND(o.total_amount * 0.30, 2)
    END
FROM report_opt_lab.orders AS o
CROSS JOIN generate_series(1, 3) AS x(i);
```

In the lab, the three items sum exactly to `orders.total_amount`. This is **intentional** to give us a reconciliation reference, not an automatic rule of real-world `orders` tables.

### 3.4. Simulate Capture and Refund Events

```sql
-- Every PAID or REFUNDED order had one CAPTURE event.
INSERT INTO report_opt_lab.payment_events (
    order_id, event_type, amount, event_at
)
SELECT
    order_id, 'CAPTURE', total_amount,
    ordered_at + INTERVAL '10 minutes'
FROM report_opt_lab.orders
WHERE status IN ('PAID', 'REFUNDED');

-- REFUNDED orders also have a half-amount REFUND event.
INSERT INTO report_opt_lab.payment_events (
    order_id, event_type, amount, event_at
)
SELECT
    order_id, 'REFUND',
    ROUND(total_amount * 0.50, 2),
    ordered_at + INTERVAL '1 day'
FROM report_opt_lab.orders
WHERE status = 'REFUNDED';

ANALYZE report_opt_lab.orders;
ANALYZE report_opt_lab.order_items;
ANALYZE report_opt_lab.payment_events;
```

`payment_events` has **two events for each refunded order**, while each order has three items. Joining all three raw tables yields **six intermediate rows for one `REFUNDED` order**.

### 3.5. Verify Baseline Data

```sql
SELECT
    (SELECT COUNT(*) FROM report_opt_lab.orders)
        AS order_count,
    (SELECT COUNT(*) FROM report_opt_lab.order_items)
        AS item_count,
    (SELECT COUNT(*) FROM report_opt_lab.payment_events)
        AS payment_event_count;
```

Qualitative expectations:

- 15,000 `orders` rows.
- 45,000 `order_items` rows.
- `payment_events` matching the `PAID`/`REFUNDED` and `REFUND` counts in the sample.

Verify item sums equal order amounts:

```sql
SELECT COUNT(*) AS orders_with_mismatch
FROM (
    SELECT
        o.order_id,
        o.total_amount,
        SUM(i.line_amount) AS item_total
    FROM report_opt_lab.orders AS o
    JOIN report_opt_lab.order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.order_id, o.total_amount
) AS s
WHERE s.item_total IS DISTINCT FROM s.total_amount;
```

Expected result is **0**. This checks lab correctness, not performance.

---

## 4. `WHERE`, `HAVING`, and `FILTER`: Three Different Questions

These three filtering locations are frequently confused.

| Clause | Level of Operation | Example |
| --- | --- | --- |
| `WHERE` | Filters **input rows** before aggregation | Consider only January orders |
| `HAVING` | Filters **output groups** using group expressions | Keep only regions with > 1,000 orders |
| `FILTER (WHERE ...)` | Feeds **only qualifying rows into one specific aggregate** | Count `PAID` and `CANCELED` in the same group |

### 4.1. `WHERE` Filters Before `GROUP BY`

```sql
SELECT region, COUNT(*) AS paid_orders
FROM report_opt_lab.orders
WHERE status = 'PAID'
GROUP BY region;
```

Here non-`PAID` orders **never enter any aggregate in the statement**.

### 4.2. `HAVING` Filters Formed Groups

```sql
SELECT
    region,
    COUNT(*) AS order_count
FROM report_opt_lab.orders
GROUP BY region
HAVING COUNT(*) > 4000;
```

`HAVING` tests the per-region aggregate. It does not replace `WHERE` when out-of-scope rows should be excluded early.

### 4.3. `FILTER` Filters Each Aggregate Individually

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELED')
        AS canceled_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING')
        AS pending_orders
FROM report_opt_lab.orders
GROUP BY region
ORDER BY region;
```

Each `FILTER` applies strictly to its immediately preceding aggregate; other aggregates still see the group's full `WHERE`-filtered input.

### 4.4. A Common Metric Definition Bug

Wrong if trying to count **all orders alongside `PAID` orders**:

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM report_opt_lab.orders
WHERE status = 'PAID'
GROUP BY region;
```

Because `WHERE status='PAID'` removed every other status, `all_orders` and `paid_orders` become identical. The SQL is valid, yet `all_orders` is semantically wrong.

**Rule:** use `WHERE` for the report's shared scope, and `FILTER` for conditions specific to individual metrics.

---

## 5. Conditional Aggregation with `FILTER` and `CASE`

PostgreSQL supports:

```sql
aggregate(expression) FILTER (WHERE condition)
```

Example `PAID` order revenue and counts per status:

```sql
SELECT
    DATE_TRUNC('day', ordered_at AT TIME ZONE 'UTC')::DATE
        AS order_day_utc,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    SUM(total_amount) FILTER (WHERE status = 'PAID')
        AS paid_order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
GROUP BY order_day_utc
ORDER BY order_day_utc;
```

Here `paid_order_value` means **total order value of orders currently in `PAID` status**, not captured cash or net revenue after refunds.

### 5.1. Same Logic with `CASE`

```sql
SELECT
    region,
    COUNT(*) AS orders,
    SUM(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS paid_orders_case,
    COUNT(*) FILTER (
        WHERE status = 'PAID'
    ) AS paid_orders_filter
FROM report_opt_lab.orders
GROUP BY region;
```

Both produce the exact same counts when `CASE` is written properly.

`FILTER` cleanly binds the condition to its aggregate, especially when a `SELECT` computes many metrics. However, **`FILTER` is not guaranteed to beat `CASE` in speed**: both still read the same input rows. Benchmark on real data to see if any difference is meaningful.

### 5.2. Watch Out for `COUNT` with `CASE`

These two expressions **differ**:

```sql
-- Correct: COUNT counts only rows where CASE returns a non-NULL value.
COUNT(CASE WHEN status = 'PAID' THEN 1 END)

-- Wrong if counting PAID only: every row returns 0 or 1,
-- so COUNT counts every row in the group.
COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

If using `CASE ... ELSE 0`, wrap it in `SUM(...)`. If using `COUNT`, let non-matching rows evaluate to `NULL`.

### 5.3. `NULL`: `COUNT` and `SUM` Behave Differently

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(total_amount) FILTER (
        WHERE status = 'PAID'
    ) AS paid_total
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00';
```

When zero rows match the scope:

- `COUNT(*)` returns **0**.
- `SUM(...)` returns **`NULL`**, not 0.

To default financial output to 0 when empty:

```sql
COALESCE(
    SUM(total_amount) FILTER (WHERE status = 'PAID'),
    0::NUMERIC
) AS paid_total
```

Choosing `0` vs `NULL` is a **semantic decision**: `0` means zero revenue, whereas `NULL` may mean no data or undefined. Never wrap every aggregate in `COALESCE(..., 0)` out of habit if the business distinguishes the two.

---

## 6. `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT)`

Three counting functions that look alike yet mean different things:

```sql
SELECT
    region,
    COUNT(*) AS row_count,
    COUNT(customer_id) AS non_null_customer_rows,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
GROUP BY region;
```

- `COUNT(*)` counts **every row** in the group regardless of `NULL`s.
- `COUNT(column)` counts rows where `column` is **not `NULL`**.
- `COUNT(DISTINCT column)` counts **distinct non-`NULL` values**.

In the lab, `customer_id` is `NOT NULL`, so `COUNT(*)` and `COUNT(customer_id)` match unless a JOIN multiplies rows. Once joined, input rows can exceed order count.

### 6.1. `DISTINCT` Carries Its Own Cost

An aggregate like:

```sql
COUNT(DISTINCT customer_id)
```

cannot simply increment a counter if the same `customer_id` appears repeatedly. The engine must deduplicate values, typically requiring memory, sorting/hashing, or a specialized plan. At very high distinct cardinality, cost climbs steeply.

### 6.2. `COUNT(DISTINCT)` Does Not Fix All `JOIN` Bugs

Under join fan-out, `COUNT(DISTINCT o.order_id)` fixes **order count**, yet:

```sql
SUM(o.total_amount)
```

remains inflated.

Meanwhile:

```sql
SUM(DISTINCT o.total_amount)
```

is not a fix: two distinct orders both totaling 100 must sum to 200, whereas `SUM(DISTINCT)` counts 100 only once.

**The true fix is restoring grain and JOIN structure**, not hiding bugs with `DISTINCT`.

### 6.3. `DISTINCT` on a Pre-Reduced Input Set

To count distinct customers by day and region, you can sometimes split the step:

```sql
WITH customer_days AS (
    SELECT DISTINCT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        region,
        customer_id
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT
    day_utc,
    region,
    COUNT(*) AS unique_paid_customers
FROM customer_days
GROUP BY day_utc, region
ORDER BY day_utc, region;
```

This makes the intermediate `(day, region, customer)` grain explicit before counting. It is not automatically faster than `COUNT(DISTINCT)`; benchmark with your data, group counts, and indexes.

---

## 7. Critical Bug: `JOIN` Fan-Out Multiplies Totals

Every order has three items. `REFUNDED` orders have two payment events. Joining directly:

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    SUM(o.total_amount) AS wrong_order_sum
FROM report_opt_lab.orders AS o
JOIN report_opt_lab.order_items AS i
  ON i.order_id = o.order_id
JOIN report_opt_lab.payment_events AS p
  ON p.order_id = o.order_id
WHERE o.status = 'REFUNDED'
GROUP BY o.order_id
ORDER BY o.order_id
LIMIT 5;
```

One `REFUNDED` order produces:

```text
1 order
  x 3 order_items
  x 2 payment_events
  = 6 rows in the JOIN result
```

Hence `SUM(o.total_amount)` for a single order becomes **6× the real amount**. This is **join fan-out**, **join multiplication**, or **row explosion**.

### 7.1. Why Doesn't `GROUP BY` After `JOIN` Fix It?

`GROUP BY` collapses intermediate rows by grouping key, yet if a value appears six times in the input, `SUM` still adds it six times.

```text
Wrong grain:
orders (1 row/order)
  JOIN items (3 rows/order)
  JOIN payments (2 rows/order)
    -> 6 rows/order
GROUP BY order_id
    -> 1 output row/order
    -> SUM(order_amount) was added 6 times
```

The output row count looks right, while the aggregated totals are wrong.

### 7.2. The Fix: Pre-Aggregate Each 1:N Relation to Order Grain Before Joining

```sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(line_amount) AS item_amount,
        SUM(quantity) AS item_quantity
    FROM report_opt_lab.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) FILTER (
            WHERE event_type = 'CAPTURE'
        ) AS captured_amount,
        SUM(amount) FILTER (
            WHERE event_type = 'REFUND'
        ) AS refunded_amount
    FROM report_opt_lab.payment_events
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.total_amount,
    i.item_amount,
    COALESCE(p.captured_amount, 0::NUMERIC)
        AS captured_amount,
    COALESCE(p.refunded_amount, 0::NUMERIC)
        AS refunded_amount
FROM report_opt_lab.orders AS o
LEFT JOIN item_totals AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
  ON p.order_id = o.order_id
WHERE o.order_id = 10;
```

The CTEs collapse `order_items` and `payment_events` down to **one row per `order_id`** before joining. Each order is never multiplied across two 1:N relationships.

### 7.3. Pre-Aggregate Only the Tables Actually Needed

If a report only asks for order counts and total order value by region, **do not join `order_items` or `payment_events` at all**. Every join adds work and risks distorting grain.

### 7.4. Don't Forget Orders Without Payments

`LEFT JOIN payment_totals` keeps unpaid orders. For orders with no payment events, right-side columns are `NULL`; apply `COALESCE` to 0 only when business rules interpret missing events as zero.

Using `INNER JOIN payment_totals` drops unpaid orders—valid for “orders with payment activity,” wrong for “all orders.”

---

## 8. Multi-Table Reports: Build from the Right Grain

Suppose we want a per-`region` report of:

- Order count.
- Total order value of `PAID` orders.
- Total `CAPTURE` amount.
- Total `REFUND` amount.
- Net payment flow = captured − refunded.
- Total item quantity across orders.

A grain-safe implementation:

```sql
WITH item_by_order AS (
    SELECT
        order_id,
        SUM(quantity) AS quantity
    FROM report_opt_lab.order_items
    GROUP BY order_id
),
payment_by_order AS (
    SELECT
        order_id,
        COALESCE(
            SUM(amount) FILTER (WHERE event_type = 'CAPTURE'),
            0::NUMERIC
        ) AS captured,
        COALESCE(
            SUM(amount) FILTER (WHERE event_type = 'REFUND'),
            0::NUMERIC
        ) AS refunded
    FROM report_opt_lab.payment_events
    GROUP BY order_id
)
SELECT
    o.region,
    COUNT(*) AS order_count,
    COALESCE(
        SUM(o.total_amount) FILTER (WHERE o.status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COALESCE(SUM(p.captured), 0::NUMERIC) AS captured,
    COALESCE(SUM(p.refunded), 0::NUMERIC) AS refunded,
    COALESCE(SUM(p.captured - p.refunded), 0::NUMERIC)
        AS net_payment_flow,
    COALESCE(SUM(i.quantity), 0::BIGINT)
        AS item_quantity
FROM report_opt_lab.orders AS o
LEFT JOIN item_by_order AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_by_order AS p
  ON p.order_id = o.order_id
GROUP BY o.region
ORDER BY o.region;
```

### 8.1. Why `COALESCE` Inside `payment_by_order`?

If an order has a `CAPTURE` event and no `REFUND` event:

```text
SUM(amount) FILTER (WHERE event_type='REFUND') = NULL
```

Without `COALESCE`, `captured - refunded` evaluates to `NULL` and is skipped by `SUM`, corrupting net payment flow. Coalesce `NULL` to `0` **per business definition** before subtracting.

### 8.2. Watch Time Scope

If reporting by **order date**, filter `o.ordered_at`. If reporting by **cash-flow date**, filter `p.event_at`. Those two numbers can differ because refunds occur on later days.

Never “optimize” by filtering `o.ordered_at` and labeling the output `cashflow_by_payment_day`. That changes the report's definition.

### 8.3. Narrow Scope Before Aggregating

The query above aggregates **every item and payment across all orders**, even if the report only needs a short date window. On large tables, that is wasteful.

A variant filtering `orders` first before aggregating child rows:

```sql
WITH selected_orders AS (
    SELECT *
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
),
item_by_order AS (
    SELECT
        i.order_id,
        SUM(i.quantity) AS quantity
    FROM report_opt_lab.order_items AS i
    JOIN selected_orders AS o
      ON o.order_id = i.order_id
    GROUP BY i.order_id
),
payment_by_order AS (
    SELECT
        p.order_id,
        COALESCE(
            SUM(p.amount) FILTER (WHERE p.event_type = 'CAPTURE'),
            0::NUMERIC
        ) AS captured,
        COALESCE(
            SUM(p.amount) FILTER (WHERE p.event_type = 'REFUND'),
            0::NUMERIC
        ) AS refunded
    FROM report_opt_lab.payment_events AS p
    JOIN selected_orders AS o
      ON o.order_id = p.order_id
    GROUP BY p.order_id
)
SELECT
    o.region,
    COUNT(*) AS orders,
    COALESCE(SUM(p.captured - p.refunded), 0::NUMERIC)
        AS net_payment_flow,
    COALESCE(SUM(i.quantity), 0::BIGINT) AS quantity
FROM selected_orders AS o
LEFT JOIN item_by_order AS i ON i.order_id = o.order_id
LEFT JOIN payment_by_order AS p ON p.order_id = o.order_id
GROUP BY o.region;
```

Idea: **push selective filters down early**, aggregating only child rows belonging to selected orders.

Still, PostgreSQL's optimizer can inline CTEs; writing CTEs does not guarantee speedup. Inspect `EXPLAIN`, intermediate row counts, and selectivity.

---

## 9. Time Filters: Half-Open Intervals

A report for “February 2026 in UTC” should filter:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

This is a **[start, end)** interval: inclusive start, exclusive end.

### 9.1. Avoid `BETWEEN` with Ambiguous End-of-Day Bounds

Writing:

```sql
WHERE ordered_at BETWEEN
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
    AND TIMESTAMPTZ '2026-02-28 23:59:59+00'
```

drops records with fractional seconds in the final second. Manually writing `.999999` is fragile across precisions and data types.

Using the start of the next month eliminates the bug:

```sql
ordered_at >= start_at AND ordered_at < end_exclusive
```

### 9.2. Why Not Wrap the Column in `DATE` Inside `WHERE`?

Writing:

```sql
WHERE ordered_at::DATE = DATE '2026-02-01'
```

prevents straightforward use of a standard B-tree index on `ordered_at`, because the cast wraps the column and makes `TIMESTAMPTZ`-to-`DATE` depend on session time zone.

Comparing the raw column against a range:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
```

is **sargable** for a B-tree on `ordered_at`.

### 9.3. What Is Sargability?

A predicate is commonly called **sargable** when PostgreSQL can use an appropriate index structure to narrow the search range rather than evaluating a function on every row before comparing.

Examples:

| Less Friendly to Standard Indexes | Usually More Index-Friendly |
| --- | --- |
| `ordered_at::DATE = DATE '2026-02-01'` | `ordered_at >= start AND ordered_at < end` |
| `LOWER(region) = 'north'` with index only on `region` | Compare normalized column or expression index `LOWER(region)` |
| `EXTRACT(YEAR FROM ordered_at) = 2026` | Half-open range for 2026 |
| `amount + 10 > 100` | `amount > 90`, if transformation preserves semantics |

Not every column function rules out indexes: PostgreSQL supports **expression indexes**. The question is whether an index matches the query expression.

### 9.4. Business Calendar Days by Time Zone

“Midnight February 1 in Vietnam” is not `2026-02-01 00:00:00+00`. For example:

```sql
-- Day range 2026-02-01 in Asia/Ho_Chi_Minh,
-- expressed using bounds with +07 offset.
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+07'
```

The predicate still compares raw `TIMESTAMPTZ` against absolute instants. In DST-observing zones, compute both start and end boundaries in the business time zone rather than assuming every day is 24 hours.

---

## 10. Grouping by Day, Week, and Month

### 10.1. By UTC Day

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
GROUP BY day_utc, region
ORDER BY day_utc, region;
```

`AT TIME ZONE 'UTC'` produces a UTC date independent of the session's display time zone. `day_utc` sets the grain to UTC calendar day.

### 10.2. By UTC Month

```sql
SELECT
    DATE_TRUNC('month', ordered_at AT TIME ZONE 'UTC')
        AS month_utc,
    region,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY month_utc, region
ORDER BY month_utc, region;
```

Here `DATE_TRUNC` returns `timestamp without time zone` because its input `ordered_at AT TIME ZONE 'UTC'` already stripped the offset.

### 10.3. Watch Out for ISO Weeks

When reporting by week:

```sql
SELECT
    DATE_TRUNC('week', ordered_at AT TIME ZONE 'UTC')::DATE
        AS week_start_utc,
    COUNT(*)
FROM report_opt_lab.orders
GROUP BY week_start_utc
ORDER BY week_start_utc;
```

This is much safer than grouping by `EXTRACT(WEEK)` alone without **ISO year**, especially around year-end/year-start boundaries where an ISO week can belong to a different ISO year than the calendar date.

### 10.4. Date Bucketing and Indexes

When `WHERE` filters raw `ordered_at`, a time index narrows rows before bucketing. If queries frequently look up pre-computed buckets directly, consider a generated column or expression index matching your time-zone contract.

Do not blindly index `date_trunc('day', ordered_at)`: many reporting queries still read large row slices and aggregate anyway, while the extra index costs writes and maintenance.

---

## 11. `COUNT(DISTINCT)` by Day: Avoid Summing Daily Unique Counts

Report:

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
GROUP BY day_utc
ORDER BY day_utc;
```

A customer can place multiple orders in one day, so `DISTINCT` is needed to count each customer once per day.

### 11.1. Never Sum Daily Distinct Counts to Get Monthly Distincts

Suppose customer #10 buys on both Day 1 and Day 2:

```text
Day 1: unique_customers = 1
Day 2: unique_customers = 1

Sum of 2 does not mean the month had 2 distinct customers.
The month had only 1 distinct customer in this example.
```

**Distinct counts are not additive across overlapping groups.**

If a dashboard needs monthly unique customers, compute `DISTINCT` across the full month or use a data structure/sketch supporting union distincts properly.

### 11.2. Pre-Aggregation Is No Magic Bullet Here

At huge scale, pre-aggregating to `(day, customer_id)` reduces duplicate orders within each day. Yet when rolling days up into a month, you still must deduplicate `customer_id` across days.

Never replace `COUNT(DISTINCT)` with `SUM(daily_unique_customers)` unless groups are proven strictly disjoint.

### 11.3. Approximate Distincts

Some ecosystems use HyperLogLog or sketch extensions/tools to estimate distinct counts and merge sketches across groups. This is **not a built-in drop-in equivalent to `COUNT(DISTINCT)` in PostgreSQL core**.

If using approximate distincts:

- Document the error tolerance.
- Verify installed extension/version.
- Distinguish financial reports needing exact counts from dashboards accepting approximations.
- Verify sketch merge semantics across intervals, tenants, and filters.

---

## 12. Averages, Ratios, and Safe Division

### 12.1. Average Order Value

Suppose AOV includes only `PAID` orders:

```sql
SELECT
    region,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_order_count,
    ROUND(
        SUM(total_amount) FILTER (WHERE status = 'PAID')
        / NULLIF(
            COUNT(*) FILTER (WHERE status = 'PAID'),
            0
        ),
        2
    ) AS avg_paid_order_value
FROM report_opt_lab.orders
GROUP BY region;
```

`NULLIF(..., 0)` prevents division by zero. When there are zero `PAID` orders, AOV returns `NULL` to indicate an empty denominator—usually more accurate than `0`.

### 12.2. Never Take an Unweighted Average of Averages

Example:

```text
Day A: 1 order, AOV = 1000
Day B: 99 orders, AOV = 10

(1000 + 10) / 2 = 505       <- wrong average per order
(1*1000 + 99*10)/100 = 19.9 <- true average per order
```

When rolling up summary groups, retain both **sum and count** to compute weighted averages—never store only the average.

### 12.3. Paid Rate

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    ROUND(
        100::NUMERIC
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percent
FROM report_opt_lab.orders
GROUP BY region;
```

`100::NUMERIC` ensures exact decimal division. The unit of `paid_percent` here is **percent** (0–100), not a 0–1 fraction.

### 12.4. Avoid `FLOAT` for Currency When Decimal Precision Matters

PostgreSQL `NUMERIC(p,s)` fits monetary values under explicit rounding rules. `REAL` and `DOUBLE PRECISION` use approximate binary floating point and can introduce rounding drift in comparisons and sums.

In multi-currency systems, group by currency or convert via an explicit exchange-rate policy. Never sum VND and USD directly and call the result `revenue`.

---

## 13. One-to-Many `JOIN` and `LEFT JOIN` When Zero-Count Groups Must Appear

Task: display **every region**, even regions with zero orders in the date range.

Grouping directly over `orders`:

```sql
SELECT region, COUNT(*)
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00'
GROUP BY region;
```

returns 0 rows, not three regions with count 0.

### 13.1. Use a Dimension Table or Explicit Region List

```sql
WITH regions(region) AS (
    VALUES ('NORTH'::TEXT), ('CENTRAL'), ('SOUTH')
)
SELECT
    r.region,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0::NUMERIC)
        AS order_value
FROM regions AS r
LEFT JOIN report_opt_lab.orders AS o
  ON o.region = r.region
 AND o.ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00'
 AND o.ordered_at <  TIMESTAMPTZ '2030-02-01 00:00:00+00'
GROUP BY r.region
ORDER BY r.region;
```

Output shows all three regions, each with `order_count=0` and `order_value=0`.

### 13.2. `COUNT(*)` After `LEFT JOIN` Easily Overcounts

With `LEFT JOIN`, an unmatched region still produces **one row** with NULL-extended order columns.

Hence:

```sql
COUNT(*)          -- may be 1 for a region with no orders
COUNT(o.order_id) -- equals 0 when no order matches
```

Count a **non-nullable key of the right-side table** when counting related rows after a `LEFT JOIN`.

### 13.3. Put Right-Table Filters in `ON`

Writing:

```sql
FROM regions r
LEFT JOIN orders o ON o.region = r.region
WHERE o.ordered_at >= ...
```

discards rows where `o.ordered_at IS NULL`, making `LEFT JOIN` behave like an `INNER JOIN` and dropping empty regions.

Place `orders` time conditions in `ON` when the goal is **keeping all regions**, or structure the query appropriately (e.g., pre-filtered CTE).

---

## 14. Reports Including Days with Zero Orders

A daily chart needs a continuous date axis, including days with no orders.

### 14.1. Generate the Date Axis with `generate_series`

```sql
WITH days AS (
    SELECT d::DATE AS day_utc
    FROM generate_series(
        DATE '2026-02-01',
        DATE '2026-02-10',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        COUNT(*) AS orders,
        SUM(total_amount) AS order_value
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00'
    GROUP BY day_utc
)
SELECT
    days.day_utc,
    COALESCE(daily.orders, 0::BIGINT) AS orders,
    COALESCE(daily.order_value, 0::NUMERIC)
        AS order_value
FROM days
LEFT JOIN daily USING (day_utc)
ORDER BY days.day_utc;
```

### 14.2. Why Aggregate Before `LEFT JOIN`?

Joining every raw order to the date series before aggregating creates unnecessary intermediate work. Pre-aggregating `orders` to daily grain shrinks the `JOIN`, especially when each day has many orders.

### 14.3. Generate Only the Requested Date Range

Do not generate millions of dates when a dashboard shows 30 days. Date generation must have explicit bounds, matching time zones, and capped output.

---

## 15. `GROUPING SETS`, `ROLLUP`, and `CUBE`

Executive reports often need multiple aggregation levels:

- By day and region.
- By day only.
- By region only.
- Grand total.

Writing four queries with `UNION ALL` can scan and aggregate repeatedly. PostgreSQL supports **`GROUPING SETS`** to compute multiple aggregation levels in one statement.

### 15.1. `GROUPING SETS`

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY GROUPING SETS (
    ((ordered_at AT TIME ZONE 'UTC')::DATE, region),
    ((ordered_at AT TIME ZONE 'UTC')::DATE),
    (region),
    ()
)
ORDER BY day_utc NULLS LAST, region NULLS LAST;
```

The four grouping sets correspond to:

1. `(day_utc, region)`: detail rows.
2. `(day_utc)`: daily totals.
3. `(region)`: regional totals.
4. `()`: grand total.

### 15.2. `ROLLUP`

```sql
SELECT
    region,
    status,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

`ROLLUP(region,status)` produces:

- `(region, status)`.
- `(region)`.
- Grand total `()`.

Column order inside `ROLLUP` dictates the subtotal hierarchy.

### 15.3. `CUBE`

```sql
SELECT
    region,
    status,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY CUBE (region, status);
```

`CUBE(region,status)` generates all subsets of grouping keys: `(region,status)`, `(region)`, `(status)`, and `()`.

With many dimensions, grouping sets grow exponentially. Never run `CUBE` across dozens of dimensions without strict limits and capacity planning.

### 15.4. Distinguishing Subtotal `NULL`s from Data `NULL`s

When a dimension column legitimately contains `NULL`s, checking `region IS NULL` cannot tell a “missing region” row apart from a “rolled-up subtotal” row.

Use `GROUPING(...)`:

```sql
SELECT
    region,
    status,
    GROUPING(region) AS region_rolled_up,
    GROUPING(status) AS status_rolled_up,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY ROLLUP (region, status)
ORDER BY region_rolled_up, status_rolled_up, region, status;
```

`GROUPING(column)` returns `1` when that column is omitted (rolled up) in the output row and `0` otherwise.

### 15.5. `GROUPING SETS` Is Not Guaranteed Faster in Every Case

Combining into one statement avoids repeated base scans, yet still computes many groups, manages memory, and sorts. With huge numbers of combinations, many grouping sets can become resource-heavy. Always check plans and costs.

---

## 16. Is Early Filtering Always Better?

A practical rule of thumb is **reducing cardinality before expensive `JOIN` / `GROUP BY` steps**.

For example, reporting only February:

```sql
SELECT region, COUNT(*), SUM(total_amount)
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY region;
```

The input shrinks substantially when the time range is selective.

However:

- The PostgreSQL optimizer may already push predicates down automatically.
- An unselective filter (90% of the table) makes `Seq Scan` better than `Index Scan`.
- An index scan doing scattered heap fetches can cost more than a sequential scan.
- `HAVING SUM(...) > ...` **cannot** be pushed into `WHERE` without changing semantics.

### 16.1. `WHERE` Cannot Replace `HAVING`

```sql
SELECT customer_id, SUM(total_amount) AS total
FROM report_opt_lab.orders
GROUP BY customer_id
HAVING SUM(total_amount) > 1000;
```

is not equivalent to:

```sql
WHERE total_amount > 1000
```

because a customer with several small orders summing over 1,000 would be wrongly excluded.

### 16.2. `HAVING` with Non-Aggregate Conditions

If a condition depends solely on a grouping key, PostgreSQL may optimize it, yet SQL is far clearer when row-level filters sit in `WHERE`:

```sql
SELECT region, COUNT(*)
FROM report_opt_lab.orders
WHERE region = 'NORTH'
GROUP BY region;
```

Do not put every filter into `HAVING` just because the query has `GROUP BY`.

---

## 17. Indexes for Reporting Filters: B-Tree

Suppose a query runs frequently:

```sql
SELECT region, SUM(total_amount)
FROM report_opt_lab.orders
WHERE ordered_at >= :from_time
  AND ordered_at <  :to_time
GROUP BY region;
```

An index worth benchmarking:

```sql
CREATE INDEX idx_report_orders_ordered_at
ON report_opt_lab.orders (ordered_at);

ANALYZE report_opt_lab.orders;
```

### 17.1. When Does a Time Index Help?

When querying a short window out of multi-year history, a B-tree on `ordered_at` cuts rows read dramatically. When reading 70–90% of the table, `Seq Scan` or parallel scan can be faster.

An index does not remove aggregation cost over qualifying rows; it helps **locate and read the candidate slice** efficiently when selective.

### 17.2. Composite Index on `status` and Time

Queries primarily filtering:

```sql
WHERE status = 'PAID'
  AND ordered_at >= ...
  AND ordered_at < ...
```

can consider:

```sql
CREATE INDEX idx_report_orders_status_date
ON report_opt_lab.orders (status, ordered_at);
```

In a B-tree, equality on the leading column followed by range on the next is a classic pattern. Yet if most rows are `PAID` (low `status` selectivity), column order and whether the index helps still require benchmarking.

### 17.3. Do Not Create Every Composite Permutation

Three indexes:

```text
(status, ordered_at)
(ordered_at, status)
(region, ordered_at, status)
```

are rarely all needed. Each index adds disk usage, WAL, and `INSERT`/`UPDATE`/`DELETE` overhead. Inspect `EXPLAIN` and real query patterns before adding indexes.

### 17.4. Can Indexes Support `GROUP BY`?

An index ordered on grouping keys can let some plans exploit pre-ordered input and avoid or shrink a `Sort` step; still, filtering, joins, and planner cost determine whether it is chosen.

Never look at `GROUP BY region` and assume an index on `region` makes summing millions of rows O(1). Aggregation still processes all qualifying rows unless a precomputed summary exists.

---

## 18. Partial Indexes for Conditional Reports

If most reports examine only `PAID` orders, consider a partial index:

```sql
CREATE INDEX idx_report_paid_date
ON report_opt_lab.orders (ordered_at)
WHERE status = 'PAID';
```

It indexes only `PAID` rows, making it smaller than a full-table index.

Query:

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    SUM(total_amount) AS paid_order_value
FROM report_opt_lab.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY day_utc;
```

has predicates matching the partial index.

### 18.1. Partial Indexes Do Not Cover Every Conditional Aggregation

Query:

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid,
    COUNT(*) FILTER (WHERE status = 'CANCELED') AS canceled
FROM report_opt_lab.orders
WHERE ordered_at >= ...
```

needs **both `PAID` and `CANCELED`** rows. A `PAID`-only index cannot cover the query's scope. Conditions inside `FILTER` do not narrow the whole statement's input the way `WHERE` does.

### 18.2. Prepared Statements and Generic Plans

PostgreSQL must prove the query predicate implies the partial index predicate. With parameterized queries (`status = $1`), a generic plan cannot assume `$1 = 'PAID'` across all executions and may skip the partial index even if literal tests used it.

Check plans under real parameter bindings, custom/generic modes, and your PostgreSQL version—not only literal `EXPLAIN`s.

---

## 19. Covering Indexes and Index-Only Scans

An index with `INCLUDE`:

```sql
CREATE INDEX idx_report_paid_date_cover
ON report_opt_lab.orders (ordered_at)
INCLUDE (region, total_amount)
WHERE status = 'PAID';
```

can allow queries reading `ordered_at`, `region`, and `total_amount` to avoid frequent heap accesses when conditions are met.

### 19.1. `INCLUDE` Columns Are Not Search/Sort Keys

`region` and `total_amount` in `INCLUDE` are **payload**, not B-tree key columns usable for range lookups or sorting.

If queries also filter selectively on `WHERE region = 'NORTH'`, an index with `region` as a key column may fit better.

### 19.2. Index-Only Scan Does Not Mean Zero Heap Reads

PostgreSQL MVCC must verify tuple visibility for the snapshot. Index-only scans rely on the **visibility map** to skip heap fetches on all-visible pages.

On tables with continuous `UPDATE`/`DELETE` activity, many pages are not all-visible, so heap fetches still occur even when all columns exist in the index.

Check:

```text
Index Only Scan ...
  Heap Fetches: ...
```

Never claim a covering index guarantees zero heap page reads.

### 19.3. Covering Indexes Also Add Write Cost

`INCLUDE` adds payload to index tuples. Updating an included column can break HOT update eligibility and increase write amplification. Weigh report speed against write throughput.

---

## 20. BRIN for Large Time-Ordered Event Tables

On **append-heavy** log/event tables where `ordered_at` or `event_at` correlates strongly with physical page order, BRIN can be a compact candidate:

```sql
CREATE INDEX idx_report_orders_ordered_at_brin
ON report_opt_lab.orders
USING BRIN (ordered_at);
```

### 20.1. BRIN vs B-Tree

- **B-tree:** indexes individual key values; great for selective equality/range lookups, with larger size and per-row maintenance.
- **BRIN:** stores min/max summaries per **page range**; tiny and fast to maintain when data has strong physical correlation.

BRIN returns candidate page ranges and relies on heap rechecks because summaries are coarse. If timestamps are scattered randomly across pages, BRIN loses selectivity.

### 20.2. Do Not Create BRIN Just Because a Column Is `TIMESTAMPTZ`

Check:

- How large is the table?
- Do values correlate tightly with physical insertion order?
- Do queries request wide time spans or very narrow slices?
- Are timestamps frequently updated?
- How heavy are heap rechecks and pages read?

On the 15,000-row lab, B-tree or `Seq Scan` is more sensible; BRIN targets much larger workloads.

---

## 21. Partition Pruning in Time-Series Reports

On tables with hundreds of millions or billions of rows, time-based partitioning bounds which partitions must be scanned.

Conceptual schema example:

```sql
CREATE TABLE analytics_events (
    event_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    value NUMERIC(14,2)
) PARTITION BY RANGE (event_at);

CREATE TABLE analytics_events_2026_01
PARTITION OF analytics_events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');
```

A `WHERE` directly on the partition key:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-01-20 00:00:00+00'
```

lets PostgreSQL skip unrelated partitions (**partition pruning**).

### 21.1. Partitioning Does Not Automatically Make Aggregates Cheap

If a report scans an entire year across 12 partitions, the engine still processes all rows across those partitions. Partitioning helps retention, maintenance, and pruning, not automatic pre-aggregation.

### 21.2. Avoid Wrapping Partition Keys in Hard-to-Prune Expressions

Using `event_at::DATE = ...` on a `TIMESTAMPTZ` partition key makes pruning and indexing less straightforward than a raw timestamp range. Always align time ranges with the partitioning scheme.

### 21.3. Partition-Wise Aggregation

PostgreSQL can use partition-wise aggregation under supported conditions and settings. It does not apply to every `GROUP BY`, especially when grouping keys do not match partition keys or aggregates cannot decompose that way.

Inspect the actual plan rather than toggling settings and expecting linear speedup with partition count.

---

## 22. `HashAggregate` and `GroupAggregate`: Reading Execution Plans

A query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    region, status, COUNT(*), SUM(total_amount)
FROM report_opt_lab.orders
GROUP BY region, status;
```

may choose `HashAggregate`, `GroupAggregate`, or a parallel plan depending on data and statistics.

### 22.1. `HashAggregate`

Model:

```text
Scan rows
   |
   v
Hash table:
  key=(region,status)
  state=(count,sum)
   |
   v
Emit one row per group
```

Works well when group count and aggregate states fit comfortably in memory or spill cleanly via supported batching.

When group count exceeds memory limits, PostgreSQL spills to batches on temp disk. Never assume `HashAggregate` always stays in RAM.

### 22.2. `GroupAggregate`

Model:

```text
Rows sorted by group keys
              |
              v
GroupAggregate processes each group
              |
              v
Result
```

If inputs aren't already ordered, the planner adds a `Sort` node. If an index supplies the right order, sorting can be skipped or reduced.

### 22.3. Group Cardinality Directly Drives Cost

`GROUP BY region` has 3 groups in the lab; `GROUP BY customer_id` has ~1,000 groups; `GROUP BY order_id` has 15,000 groups. Hash tables, sorting, and output size all grow with group count.

Do not add unnecessary columns to `GROUP BY`: inflating group count defeats aggregation and slows the query.

### 22.4. Reading Memory, Batches, and Temp I/O

Depending on PostgreSQL version, `EXPLAIN` may report details like:

```text
HashAggregate ...
  Batches: ...
  Memory Usage: ...
  Disk Usage: ...
```

or under `Sort`:

```text
Sort Method: external merge  Disk: ...
```

These lines show **output structure only**, not actual lab benchmark figures.

Disk spilling is a signal to investigate, not automatic proof that the query is broken or that `work_mem` must be raised immediately.

---

## 23. Parallel Aggregation

Large reports can leverage multiple workers:

```text
Parallel Seq Scan
        |
        v
  Partial Aggregate (per worker)
        |
        v
 Gather / Gather Merge
        |
        v
 Finalize Aggregate
        |
        v
      Output
```

Plans typically show `Partial HashAggregate` and `Finalize HashAggregate`.

### 23.1. When Does Parallel Aggregation Help?

When enough data is scanned and work parallelizes well, partial per-worker aggregation followed by finalization cuts wall-clock latency.

Still, parallelism carries overhead:

- Spawning/coordinating workers.
- Passing and merging partial states.
- Contending for shared I/O.
- Per-worker memory usage.
- Some aggregates, `DISTINCT`, ordered-set aggregates, or UDFs cannot parallelize equally well.

### 23.2. Never Tune `max_parallel_workers_per_gather` by Gut Feel

One query finishing faster with 4 workers does not mean 20 concurrent dashboard queries run faster when each grabs 4 workers. Total CPU, I/O, and worker contention can degrade throughput.

Measure both **single-query latency** and **concurrent throughput**.

### 23.3. Parallel Queries and `COUNT(DISTINCT)`

Aggregates with `DISTINCT` or `ORDER BY` have specific constraints for partial aggregation. Never assume `COUNT(DISTINCT ...)` parallelizes identically to `COUNT(*)`.

---

## 24. `work_mem`, `hash_mem_multiplier`, and Spilling

Aggregates and sorts require memory for:

- Hash tables.
- Sort runs.
- Distinct tracking.
- Hash joins.
- Intermediate states.

In PostgreSQL, `work_mem` bounds memory per operation, **not a single cap for the entire query**.

### 24.1. Why Raising `work_mem` Can Be Risky

One query can have multiple Sort/Hash nodes; many queries run concurrently; each parallel worker allocates its own memory per operation.

Hypothetical illustration:

```text
20 concurrent queries
  x 3 memory-heavy nodes
  x 4 workers/participants
  x memory budget
= potentially huge total consumption
```

This illustrates multiplicative memory risk, not an exact RAM formula. Actual allocation depends on version, node type, and data volume.

### 24.2. `hash_mem_multiplier`

Depending on version, hash-based nodes scale their memory limit using `work_mem * hash_mem_multiplier`. Do not assume every node uses exactly `work_mem`, and never raise cluster-wide settings just because a single report spilled.

### 24.3. `SET LOCAL` for Testing

With proper permissions in a test environment:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(total_amount)
FROM report_opt_lab.orders
GROUP BY customer_id;

ROLLBACK;
```

This scopes the setting to one transaction without changing global config. `64MB` is purely illustrative; benchmark under realistic load and concurrency.

### 24.4. Fix Query Shape Before Adding RAM

If a join is inflating rows 10×, raising `work_mem` hides symptoms while still computing wrong totals and wasting memory. Fix grain, `JOIN`s, and `WHERE` first, then tune memory.

---

## 25. CTEs: Clearer, Not Automatically Faster

CTEs break complex reporting logic into readable steps:

```sql
WITH filtered AS (
    SELECT order_id, region, total_amount
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
),
totals AS (
    SELECT region, SUM(total_amount) AS paid_amount
    FROM filtered
    GROUP BY region
)
SELECT * FROM totals;
```

CTEs improve readability, yet **do not force PostgreSQL to run faster**. On modern versions, simple `SELECT` CTEs can be inlined conditionally or materialized depending on usage.

### 25.1. `MATERIALIZED` and `NOT MATERIALIZED`

PostgreSQL lets you hint materialization behavior:

```sql
WITH filtered AS MATERIALIZED (
    SELECT *
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT region, COUNT(*)
FROM filtered
GROUP BY region;
```

and:

```sql
WITH filtered AS NOT MATERIALIZED (
    SELECT *
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT region, COUNT(*)
FROM filtered
GROUP BY region;
```

Both have conditions and caveats; do not treat either as a universal speedup trick.

- Materialization helps when an expensive intermediate result is referenced multiple times.
- Yet it can block predicate pushdown and add materialization cost.
- Inlining gives the optimizer cross-CTE flexibility, yet may recompute expressions if referenced multiple times.

### 25.2. Avoid Splitting CTEs in Ways That Multiply Scans

Writing five separate CTEs that each scan all of `orders` for one metric may prevent optimal sharing. Consider conditional aggregation computing multiple metrics in **one grouping pass**.

---

## 26. Computing Multiple Metrics in a Single Scan

A dashboard wants:

- Total orders.
- `PAID` count.
- `REFUNDED` count.
- Total `PAID` order value.
- Total `REFUNDED` order value.
- Unique customers.

One statement can compute all of them together:

```sql
SELECT
    region,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'REFUNDED'),
        0::NUMERIC
    ) AS refunded_order_value,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY region
ORDER BY region;
```

Potential win: all aggregates share a single scan.

Still, adding more aggregates—especially `DISTINCT` and ordered-set aggregates—increases memory and CPU work. “One scan” does not mean “free metrics.”

### 26.1. A Single Scan Also Improves Snapshot Consistency

In PostgreSQL, a single `SELECT` sees one consistent statement snapshot. Firing six separate queries under `READ COMMITTED` lets concurrent writes create mismatched numbers across widgets.

Combining metrics into one `SELECT` ensures they share **the exact same snapshot**, eliminating one source of inconsistency.

If a dashboard requires multiple queries to share one snapshot, consider a **short `REPEATABLE READ` read transaction** with clear boundaries—never leave read transactions open long enough to impede MVCC cleanup.

---

## 27. `LATERAL` and Correlated Subqueries: When Are They Appropriate?

Sometimes an application needs per-row aggregates **for a small selected page**, such as the 20 latest orders with their item counts.

`LATERAL` works well here:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    item_stats.item_count,
    item_stats.item_amount
FROM (
    SELECT order_id, ordered_at
    FROM report_opt_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
) AS o
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS item_count,
        COALESCE(SUM(line_amount), 0::NUMERIC)
            AS item_amount
    FROM report_opt_lab.order_items AS i
    WHERE i.order_id = o.order_id
) AS item_stats ON TRUE
ORDER BY o.ordered_at DESC, o.order_id DESC;
```

With an index on `order_items(order_id)`, this is clean and efficient when aggregating only a handful of selected orders.

### 27.1. Correlated Subqueries Can Be Expensive Across Millions of Orders

Without a narrow `LIMIT`, running a subquery per order can trigger millions of index probes or scans. The planner may optimize some cases, yet never assume it always rewrites into a grouped hash join.

For full-period daily reports across all orders, **aggregating items once and joining** is usually worth comparing.

### 27.2. Index Foreign Keys Used for Correlation

```sql
CREATE INDEX idx_report_items_order_id
ON report_opt_lab.order_items (order_id);

CREATE INDEX idx_report_payments_order_id
ON report_opt_lab.payment_events (order_id);
```

These indexes speed up child lookups per order, especially for `LATERAL`/Nested Loop over a small order subset. For full-table aggregations, `Seq Scan + HashAggregate` can still win.

---

## 28. Window Functions After `GROUP BY`

A report might need:

- Daily total.
- Cumulative running total.
- Day rank by revenue.
- Day share of monthly total.

Aggregate to daily grain first, then apply window functions:

```sql
WITH daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        SUM(total_amount) FILTER (
            WHERE status = 'PAID'
        ) AS paid_order_value
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
    GROUP BY day_utc
)
SELECT
    day_utc,
    COALESCE(paid_order_value, 0::NUMERIC)
        AS paid_order_value,
    SUM(COALESCE(paid_order_value, 0::NUMERIC))
        OVER (
            ORDER BY day_utc
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_paid_value,
    RANK() OVER (
        ORDER BY paid_order_value DESC NULLS LAST
    ) AS revenue_rank
FROM daily
ORDER BY day_utc;
```

### 28.1. Why Aggregate First?

Applying window functions over raw orders and then grouping mixes grains and forces windowing/sorting over far more rows. Pre-aggregating by day shrinks window input and keeps semantics clear.

### 28.2. `ROWS` vs `RANGE` in Running Frames

At daily grain (one row per day), `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` explicitly accumulates row by row. When duplicate `ORDER BY` keys exist, default `RANGE` processes peers together; understand window framing and deterministic ordering.

### 28.3. Running Totals and Missing Days

If running totals must span every calendar day including zero-order days, generate the date series and `LEFT JOIN daily` *before* computing the running `SUM` so empty days aren't omitted from the chart.

---

## 29. Materialized Views for Repeated Dashboards

When the exact same daily/region report runs hundreds of times against relatively slow-changing data, recomputing `GROUP BY` over the entire table every request wastes resources.

PostgreSQL supports `MATERIALIZED VIEW`:

```sql
CREATE MATERIALIZED VIEW report_opt_lab.daily_region_orders
AS
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_count,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value
FROM report_opt_lab.orders
GROUP BY day_utc, region
WITH DATA;
```

Dashboard query:

```sql
SELECT *
FROM report_opt_lab.daily_region_orders
WHERE day_utc >= DATE '2026-02-01'
  AND day_utc <  DATE '2026-03-01'
ORDER BY day_utc, region;
```

### 29.1. Materialized Views Do Not Auto-Update on `INSERT`/`UPDATE`

A PostgreSQL materialized view stores a **materialized snapshot** as of its last `REFRESH`, not a table updated row-by-row when base tables change.

```sql
REFRESH MATERIALIZED VIEW
    report_opt_lab.daily_region_orders;
```

Refreshing recomputes results per PostgreSQL's refresh rules. Staleness tolerance must be part of the dashboard design.

### 29.2. `REFRESH CONCURRENTLY`

When prerequisites are met—such as a **valid column-based unique index covering all rows** (not an expression or partial unique index) and the view already being populated—you can run:

```sql
CREATE UNIQUE INDEX idx_daily_region_orders_unique
ON report_opt_lab.daily_region_orders (day_utc, region);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    report_opt_lab.daily_region_orders;
```

Check privileges, version, and caveats for `REFRESH ... CONCURRENTLY`. Concurrent refresh avoids blocking `SELECT`s on the view, yet still incurs significant work and is neither free nor safe for overlapping concurrent refreshes on the same view.

### 29.3. Choosing Between Regular Views and Materialized Views

| Option | Data Freshness | Cost per Read |
| --- | --- | --- |
| Regular view | Queries base data at statement snapshot | Re-runs aggregation |
| Materialized view | Snapshot as of last `REFRESH` | Reads stored summary |
| Incremental summary table | Near real-time depending on pipeline | Reads updated summary |
| Application cache | Per TTL / invalidation | Very fast, easily stale |

Never pick a materialized view if the business requires up-to-the-second numbers without a refresh cadence that satisfies it.

### 29.4. Full `REFRESH` Can Be Expensive

Built-in PostgreSQL materialized views are not automatic **incremental materialized views** across arbitrary DML. On massive base tables with frequent refreshes, recompute cost can be heavy.

In that case, evaluate summary tables, incremental pipelines, or specialized tooling along with data-consistency safeguards.

---

## 30. Incremental Summary Tables: Design with Care

A daily summary table can be maintained per event:

```sql
CREATE TABLE report_opt_lab.daily_region_summary (
    day_utc DATE NOT NULL,
    region TEXT NOT NULL,
    order_count BIGINT NOT NULL DEFAULT 0,
    paid_order_count BIGINT NOT NULL DEFAULT 0,
    paid_order_value NUMERIC(18,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, region)
);
```

Example incrementing on a **newly created `PAID` order processed exactly once**:

```sql
INSERT INTO report_opt_lab.daily_region_summary (
    day_utc, region, order_count,
    paid_order_count, paid_order_value
)
VALUES (
    DATE '2026-02-01', 'NORTH', 1, 1, 100.00
)
ON CONFLICT (day_utc, region)
DO UPDATE SET
    order_count =
        report_opt_lab.daily_region_summary.order_count + 1,
    paid_order_count =
        report_opt_lab.daily_region_summary.paid_order_count + 1,
    paid_order_value =
        report_opt_lab.daily_region_summary.paid_order_value
        + EXCLUDED.paid_order_value;
```

**Warning:** this illustrates applying a delta for **one new order event**. Running the same statement again double-counts; it is **not idempotent**.

### 30.1. `UPDATE`s, Refunds, and Cancellations Complicate Matters

If an order transitions:

```text
PENDING -> PAID -> REFUNDED
```

the summary system must define:

- How `order_count` increments on creation.
- When `PAID` occurs, incrementing `paid_order_count` / `paid_order_value`.
- When `REFUNDED` occurs, whether `paid_order_count` decrements per definition and whether refunds are booked to the event day.
- If `region` changes, subtracting from the old region and adding to the new one.
- If `total_amount` changes, applying the **delta**, not adding the full new amount again.

You cannot simply run `ON CONFLICT DO UPDATE SET total = total + NEW.amount` on every `UPDATE` and expect accurate numbers.

### 30.2. Idempotency and Event Ordering

A reliable pipeline typically needs:

- Immutable, unique event IDs.
- Exactly-once state effect or deduplication on retries.
- Version/sequence tracking per aggregate.
- Handling out-of-order or late events.
- Recording processed event IDs in the same transaction as summary updates where applicable.
- Periodic reconciliation against source tables.

**A fast summary that holds wrong numbers is not an optimization.**

### 30.3. Incremental Distinct Counts Are Harder Than `SUM`/`COUNT`

To maintain daily distinct customers, increment only when a customer first appears in that bucket. If a customer has multiple orders and one cancels, you cannot blindly subtract 1 from the distinct count without knowing whether another qualifying order remains.

This often requires an intermediate table at `(day, region, customer_id)` grain tracking active order counts, or an appropriate distinct structure.

---

## 31. `EXPLAIN (ANALYZE, BUFFERS)`: Reading Measurements Correctly

First measure the baseline:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY day_utc, region;
```

### 31.1. Common Nodes to Recognize

| Node / Field | Meaning |
| --- | --- |
| `Seq Scan` | Sequential table scan |
| `Index Scan` | Index lookup, possibly visiting heap |
| `Index Only Scan` | Skips heap fetches when visibility permits |
| `Bitmap Index Scan` | Builds candidate tuple bitmap |
| `Bitmap Heap Scan` | Fetches heap pages matching bitmap |
| `Hash Join` | Joins via hash table |
| `Nested Loop` | Probes inner side for each outer row |
| `HashAggregate` | Groups rows in a hash table |
| `GroupAggregate` | Groups already-sorted input |
| `Sort` | Sorts rows |
| `Gather / Gather Merge` | Combines rows from parallel workers |
| `Partial/Finalize Aggregate` | Aggregates partially per worker, then finalizes |
| `Buffers: shared hit/read` | Activity in `shared_buffers` |
| `Buffers: temp read/written` | Temp disk I/O from spills/operations |
| `actual rows, loops` | Actual rows and execution loop counts |
| `Planning/Execution Time` | Measured planning and execution durations |

### 31.2. Bad Estimates Lead to Bad Plans

If PostgreSQL estimates a few dozen rows while actual execution reads millions, the planner may pick a `Nested Loop` or poor aggregation strategy.

Compare:

```text
rows=...        (estimated)
actual rows=... (actual)
loops=...
```

Large discrepancies stem from stale statistics, correlated columns, data skew, or complex predicates.

### 31.3. Measure Four Dimensions

For reports:

1. **Correctness:** right grain, metrics, `NULL`s, joins, and time zone?
2. **Logical work:** how many rows scanned, joined, and grouped?
3. **Physical work:** shared buffers, temp files, disk I/O.
4. **Latency/resources:** duration, CPU, memory, concurrent load.

Never treat a single warm-cache `Execution Time` as proof of production performance.

### 31.4. Do Not Mistake `EXPLAIN ANALYZE` for a Dry-Run Simulator

For `SELECT`, `EXPLAIN ANALYZE` runs the query and measures it. For `UPDATE`/`DELETE`/`INSERT`, it **executes the DML**. Measurement here focuses on `SELECT`; if testing DML in a lab, remember even rolled-back transactions generate WAL and I/O.

---

## 32. Statistics and Extended Statistics

The PostgreSQL optimizer relies on statistics to estimate:

- Rows surviving `WHERE`.
- Number of groups after `GROUP BY`.
- Combined predicate selectivity.
- Costs of `JOIN`, `HashAggregate`, and `Sort`.
- When `Index Scan` beats `Seq Scan`.

### 32.1. Run `ANALYZE` After Major Data Changes

```sql
ANALYZE report_opt_lab.orders;
ANALYZE report_opt_lab.order_items;
ANALYZE report_opt_lab.payment_events;
```

`ANALYZE` refreshes planner statistics; it **is not `VACUUM`** and does not reclaim dead tuples.

### 32.2. Correlated Columns

If `status` and `region` are strongly correlated, independence assumptions mislead planner estimates.

PostgreSQL supports **extended statistics** for multi-column correlations:

```sql
CREATE STATISTICS st_orders_region_status
    (dependencies, ndistinct, mcv)
ON region, status
FROM report_opt_lab.orders;

ANALYZE report_opt_lab.orders;
```

Common stats kinds:

- `dependencies`: functional dependencies between columns where supported.
- `ndistinct`: estimated distinct value combinations.
- `mcv`: most-common value combinations.

Extended stats do not fix every misestimate and do not replace indexes. Confirm a bad plan stems from correlation before creating them.

### 32.3. Per-Column Statistics Target

On massive tables, you can raise the statistics target on key columns. Higher targets make `ANALYZE` heavier and stats larger, so never crank all columns up indiscriminately.

### 32.4. Autovacuum / Autoanalyze

Under continuous writes, autovacuum and autoanalyze keep tables maintained and stats reasonably current. Tables with rapidly shifting distributions may still need explicit `ANALYZE` after major batch loads.

---

## 33. Monitoring Reporting Queries in Production

When `pg_stat_statements` is enabled and configured, it tracks normalized query execution statistics.

Illustrative query:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

**Note:** this view exists only when the extension is configured/installed; changing `shared_preload_libraries` requires a server restart. Never enable extensions on production without authorization.

### 33.1. What Metrics Should You Track?

- P50/P95/P99 latency of reporting endpoints.
- Execution counts and cumulative execution time.
- Rows scanned vs returned (via appropriate plan/log monitoring).
- Shared and temp I/O.
- Query cancellations and timeouts.
- Concurrent report executions.
- CPU and memory pressure.
- Refresh timestamps of views/summaries.
- Data freshness and reconciliation discrepancies.
- Read-replica lag if dashboards hit standbys.

### 33.2. Fast Queries Can Still Be Expensive When Called Very Often

An 80 ms report called 500 times/second burns more resources than a 5-second report run once an hour. Prioritize total workload using **`calls × cost`**, not single-run latency alone.

### 33.3. Caching Can Beat Adding Another Index

If a daily dashboard refreshes every 5 minutes, caching or a materialized view cuts database load. Ensure caches enforce proper TTLs, invalidation, permission scopes, and freshness labels—never use caching to hide broken metrics.

---

## 34. Consistency When Reading Reports Concurrently with DML

A multi-metric report can become inconsistent if the app runs separate `SELECT`s at different times:

```text
T1: SELECT COUNT(*)          -> 100 orders
T2: INSERT one order and COMMIT
T3: SELECT SUM(total_amount) -> total across 101 orders
```

If the UI merges metrics from two different snapshots as if from one instant, users see contradictory numbers.

### 34.1. One `SELECT` with Multiple Aggregates

Computing related metrics in a single `SELECT` makes them share the exact same statement snapshot in PostgreSQL.

### 34.2. Multiple `SELECT`s in One Transaction

When multiple queries must share one snapshot, use a **short `REPEATABLE READ` read transaction** with clear boundaries. Under `READ COMMITTED`, each statement can see a newer snapshot.

Never hold read transactions open for hours just to freeze a dashboard: long-lived snapshots block MVCC cleanup.

### 34.3. Reporting on Asynchronous Replicas

Replicas may lag behind recent commits. Reports on standbys can trail the primary—that is **replication lag**, not a `SUM` bug.

If immediate read-after-write accuracy is required, route affected reports to the primary or use appropriate replay-wait checks, and document freshness guarantees clearly.

### 34.4. RLS and Tenant Filters

Row-Level Security or tenant filters change report totals per caller. Never query global aggregates across all tenants and filter only in the frontend. Access policies must run server-side/in-database before returning results.

---

## 35. Three Typical Optimization Scenarios

### Scenario A — 30-Day Revenue Dashboard

**Problem:** every request runs a full scan over years of data.

Investigation:

1. Compute exact 30-day bounds in the business time zone.
2. Rewrite filter as a half-open range on the raw timestamp column.
3. Evaluate an `ordered_at` index or status-filtered partial index.
4. Evaluate a daily materialized view or summary table if heavily shared.
5. Verify plans and freshness after changes.

Do not create an index on `DATE(ordered_at)` when queries should use raw timestamp ranges; evaluate a range index first.

### Scenario B — Revenue Jumped 6× After Adding the `payments` Table

**Problem:** query joins `orders × 3 items × 2 payments`.

Investigation:

1. Run `COUNT(*)` per `order_id` after joining.
2. Identify each table's grain.
3. Pre-aggregate items and payments to one row per order before joining.
4. Reconcile totals before/after on a small known sample.
5. Never patch with `SUM(DISTINCT total_amount)`, which merges distinct orders having equal amounts.

This is primarily a **data-correctness bug**, not a missing-RAM issue.

### Scenario C — `COUNT(DISTINCT)` Consumes Excessive Memory

**Problem:** multi-dimensional report with millions of distinct customers spills `HashAggregate`/`Sort` to disk.

Investigation:

1. Verify required grain and whether dimensions can be trimmed.
2. Filter time/tenant early.
3. Eliminate row-multiplying joins before `DISTINCT`.
4. Compare pre-deduplication on the exact grouping keys.
5. Consider a `(day, region, customer)` summary grain if queried repeatedly.
6. Assess memory headroom and concurrency.
7. If approximate counts are acceptable, evaluate sketch extensions and error budgets.

Never sum daily distinct counts to produce a monthly distinct total.

---

## 36. Common Mistakes and Misconceptions

| Misconception | Reality |
| --- | --- |
| “A fast report is a correct report.” | Verify grain, metrics, joins, `NULL`s, and time zones |
| “`WHERE` and `HAVING` are interchangeable.” | `WHERE` filters input rows; `HAVING` filters groups |
| “`FILTER` acts as a query-wide `WHERE`.” | `FILTER` applies only to its single aggregate |
| “`COUNT(CASE WHEN ... THEN 1 ELSE 0 END)` counts conditionally.” | `COUNT` counts every non-`NULL` value, including `0` |
| “`SUM` over zero rows returns 0.” | `SUM` returns `NULL`; use `COALESCE` if 0 is intended |
| “`COUNT(*)` after `LEFT JOIN` counts right-side rows.” | Unmatched rows emit one NULL-extended row; use `COUNT(right.id)` |
| “`COUNT(DISTINCT order_id)` fixes all join bugs.” | Fixes order count only, not inflated `SUM`s |
| “`SUM(DISTINCT amount)` fixes fan-out.” | Wrongly collapses distinct orders with identical amounts |
| “Joining multiple 1:N tables doesn't alter row counts.” | Multiplies rows across child relations |
| “`GROUP BY` after `JOIN` removes duplicated amounts.” | `SUM` still adds each joined row |
| “`AVG(avg_per_day)` equals the monthly average.” | Requires weighting by row counts |
| “Summing daily uniques yields monthly uniques.” | Distinct sets overlap across days |
| “`BETWEEN ... 23:59:59` covers the whole day.” | Misses fractional seconds after `23:59:59` |
| “`ordered_at::DATE` always uses an `ordered_at` index.” | Casting wraps the column and can block standard B-trees |
| “UTC days equal Vietnam calendar days.” | Day boundaries depend on time zone |
| “`GROUP BY` week number works across years.” | Needs ISO year or explicit `week_start` |
| “Indexing every `GROUP BY` makes it instant.” | Still depends on row count, sorting/hashing cost |
| “A `PAID` partial index serves `PAID + CANCELED` metrics.” | Non-`PAID` rows are absent from that index |
| “`INCLUDE` supports range filters on included columns.” | `INCLUDE` stores payload only, not search keys |
| “Index-only scans never touch the heap.” | Visibility map dictates whether heap fetches occur |
| “BRIN is just a smaller B-tree.” | BRIN summarizes page ranges and requires physical correlation |
| “Partitioning precomputes summaries.” | Partition pruning narrows scope; aggregation still runs |
| “`HashAggregate` always stays in RAM.” | Can spill to disk and split into batches |
| “`GroupAggregate` always beats `HashAggregate`.” | Depends on input order, group count, and sort cost |
| “`work_mem` caps total query RAM.” | Applies per operation and per parallel worker |
| “Parallel queries are always faster.” | Worker startup and resource contention can hurt throughput |
| “CTEs always materialize.” | Modern versions can inline eligible CTEs |
| “`MATERIALIZED` is always faster.” | Can block predicate pushdown |
| “Materialized views stay live.” | Reflect data only as of the last `REFRESH` |
| “`REFRESH CONCURRENTLY` needs no unique index.” | Requires a valid column-based unique index and populated view |
| “Incremental summaries just add `NEW.amount`.” | Updates, refunds, and retries need deltas, dedupe, and ordering |
| “`COUNT(DISTINCT)` is always additive.” | Cannot sum overlapping distinct sets |
| “`EXPLAIN` cost means milliseconds.” | Cost is an arbitrary relative planner unit |
| “`Seq Scan` is always bad.” | Optimal on small tables or broad scans |
| “One benchmark settles everything.” | Cache, stats, load, spills, and concurrency vary |
| “Replica reports are always up to date.” | Asynchronous replication can lag |
| “Report caches don't need tenant scoping.” | Cache keys and auth checks must isolate tenants |

---

## 37. Practice Exercises

### Exercise 1 — Identify Grain

State the grain of `orders`, `order_items`, `payment_events`, a region–day report, and an order-level report. Why does `SUM(o.total_amount)` break after joining both items and payments?

### Exercise 2 — Counting Statuses with `FILTER`

Write a per-region `SELECT` returning total, paid, refunded, canceled, and pending counts in one query. Why does `WHERE status='PAID'` break the total count?

### Exercise 3 — `CASE` vs `FILTER`

Write the same `paid_count` metric using `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` and `COUNT(*) FILTER (...)`. Explain the bug in `COUNT(CASE ... ELSE 0 END)`.

### Exercise 4 — `NULL` and `SUM`

Query an empty date range. What does `COUNT` return, and what does `SUM` return? When should you `COALESCE(SUM, 0)` vs keep `NULL`?

### Exercise 5 — `WHERE` and `HAVING`

Find regions whose `PAID` order value exceeds a threshold during February only. Where does the month filter belong, and where does the `SUM` filter belong?

### Exercise 6 — `COUNT(DISTINCT)`

Count unique customers per region. If one customer places three orders in the same region, how do `COUNT(*)`, `COUNT(customer_id)`, and `COUNT(DISTINCT customer_id)` differ?

### Exercise 7 — Daily vs Monthly Distincts

A customer buys on two days in the same month. Why does `SUM(daily_unique_customers)` not equal `monthly_unique_customers`?

### Exercise 8 — Fan-Out Bug

Join `orders`, `order_items`, and `payment_events` for a `REFUNDED` order. Count the joined rows and show why `SUM(o.total_amount)` is multiplied.

### Exercise 9 — Fixing Fan-Out via Pre-Aggregation

Write `item_by_order` and `payment_by_order` CTEs and join them to `orders`. Reconcile `item_total`, `captured`, and `refunded` against a single order's raw rows.

### Exercise 10 — Can `SUM(DISTINCT)` Fix It?

Take two orders with the same `total_amount` and different `order_id`s. Explain why `SUM(DISTINCT total_amount)` produces the wrong sum if used to patch join multiplication.

### Exercise 11 — Half-Open Date Range

Write a `WHERE` filter for all of `2026-02-01` in UTC and in `Asia/Ho_Chi_Minh`, keeping `ordered_at` free of functions or casts.

### Exercise 12 — Timestamps with Fractional Seconds

Explain why `BETWEEN ... 23:59:59` drops timestamps with microseconds inside that last second, and write the safe replacement.

### Exercise 13 — Weekly Report

Write a report grouped by UTC `week_start`. Why can grouping by `EXTRACT(WEEK)` alone mix weeks from different years?

### Exercise 14 — Ratios and Zero Denominators

Compute `paid_percent` per region using `NUMERIC` and `NULLIF`. How should an empty group's ratio be represented?

### Exercise 15 — Weighted AOV

One day has 1 order with AOV=1000 and another has 99 orders with AOV=10. Compute the true two-day AOV using `SUM` and `COUNT`.

### Exercise 16 — Regions with Zero Orders

Use a `VALUES` CTE for the three regions and `LEFT JOIN orders` over an empty month. Compare `COUNT(*)` with `COUNT(o.order_id)`.

### Exercise 17 — Days with Zero Activity

Use `generate_series` for a 10-day range and `LEFT JOIN` a daily aggregation. Why aggregate per day before joining when `orders` is huge?

### Exercise 18 — `GROUPING SETS`

Write a report with `(day, region)`, `(day)`, and grand total. Use `GROUPING` to distinguish subtotals from real `NULL` values in nullable dimensions.

### Exercise 19 — `ROLLUP` and `CUBE`

Given `region` and `status`: which levels does `ROLLUP(region,status)` emit? What extra level does `CUBE` add? With 10 dimensions, how many grouping sets can `CUBE` generate?

### Exercise 20 — B-Tree and Partial Indexes

Propose an index for `PAID` queries over short time ranges. Explain when a partial index helps and why a query computing both `PAID` and `CANCELED` metrics cannot rely solely on it.

### Exercise 21 — Covering Indexes

With an index on `(ordered_at) INCLUDE (region, total_amount)`, when can the planner choose `Index Only Scan`, and why might `Heap Fetches` still be nonzero?

### Exercise 22 — BRIN

On an append-heavy event table ordered by `event_at`, when is BRIN worth testing over B-tree? How do randomly distributed timestamps affect BRIN?

### Exercise 23 — Partition Pruning

Given monthly range partitions on `event_at`, write a `WHERE` selecting 10 days in January. Why do raw timestamp bounds enable pruning better than wrapping expressions?

### Exercise 24 — `HashAggregate` vs `GroupAggregate`

Run `EXPLAIN` for `GROUP BY region` and then `GROUP BY order_id`. Compare estimated group counts, memory, and plan choice. Why does group count drive cost?

### Exercise 25 — Spills and `work_mem`

A plan shows `Sort Method: external merge Disk` and `HashAggregate Batches` > 1. Propose an investigation sequence before raising global `work_mem`.

### Exercise 26 — Parallel Aggregation

Explain `Partial Aggregate`, `Gather`, and `Finalize Aggregate`. Why doesn't `COUNT(DISTINCT)` automatically share the exact parallel behavior of `COUNT(*)`?

### Exercise 27 — CTE Materialization

Compare inlined vs materialized CTEs in a date-filtered report. When can materialization block pushdown, and when does it avoid recomputing expensive data?

### Exercise 28 — `LATERAL`

Write a query fetching the 20 newest orders with item counts via `LEFT JOIN LATERAL`. Why is this effective for 20 orders yet not necessarily ideal across all orders?

### Exercise 29 — Window Functions Over Aggregates

Compute daily revenue and then a running total using a window function. Why does aggregating before windowing cut row volume?

### Exercise 30 — Materialized Views

Create the `daily_region_orders` materialized view with a matching unique index. State the requirements for `REFRESH CONCURRENTLY` and why data can be stale.

### Exercise 31 — Incremental Summaries

Design summary update logic for `PENDING → PAID → REFUNDED`. Why must you not blindly add `total_amount` on every event? How do idempotency and deltas fit in?

### Exercise 32 — `ANALYZE` and Extended Statistics

Create extended stats on `(region, status)` and run `ANALYZE`. Why do statistics help the planner without replacing indexes?

### Exercise 33 — `EXPLAIN`

Run `EXPLAIN (ANALYZE, BUFFERS)` on a reporting query. Record `Seq Scan`/`Index Scan`, `HashAggregate`/`GroupAggregate`, `actual rows`, `loops`, temp I/O, and `Execution Time`.

### Exercise 34 — Snapshot Consistency

A dashboard runs `COUNT` and `SUM` as two separate `SELECT`s under `READ COMMITTED` while an `INSERT` commits in between. What happens? Propose two ways to align both metrics to the same snapshot.

### Exercise 35 — End-to-End Design Problem

A company has 300 million orders, 900 million items, and 400 million payment events; the dashboard needs daily/regional revenue, monthly unique customers, refund cash flow, product rankings, and 5-minute freshness. Outline:

- Grain and definition of each metric.
- Which joins must pre-aggregate.
- Indexes/partitions to benchmark.
- Summary tables / materialized views and refresh schedule.
- Mechanisms for `UPDATE`s, refunds, and duplicate events.
- How to measure correctness, lag, CPU, memory, temp I/O, and latency.
- Reconciliation plan between summaries and base tables.

---

## 38. PostgreSQL Reporting Optimization Checklist

| Question | How to Evaluate |
| --- | --- |
| What is each table's grain? | PKs and 1:1, 1:N, N:M relationships |
| What is the output grain? | Minimum required grouping keys |
| Are metrics strictly defined? | Paid order value, capture, refund, net |
| Is there join fan-out risk? | `COUNT(*)` per key after joining |
| Is `SUM` inflating money? | Reconcile against order-level totals |
| Is `DISTINCT` masking bad grain? | Never fix `SUM` with `SUM(DISTINCT amount)` |
| Can unneeded joins be dropped? | Cut scans and intermediate rows |
| Can child tables pre-aggregate? | One row per order before joining |
| Does `WHERE` define shared scope? | Filter rows before aggregating |
| Does `HAVING` filter groups only? | Don't move to `WHERE` if semantics shift |
| Are per-metric filters in `FILTER`? | Avoid `WHERE` dropping statuses needed elsewhere |
| Are `COUNT(*)` / `COUNT(col)` right? | Watch `NULL`s and `LEFT JOIN`s |
| Should `SUM` use `COALESCE`? | Distinguish no data vs 0 |
| Is AOV properly weighted? | Store both sum and count |
| Are distinct counts summed wrongly? | Never add overlapping distinct groups |
| Is the business time zone clear? | Compute boundaries in the exact time zone |
| Are date ranges half-open? | `>= start, < end` |
| Is `WHERE` sargable? | Compare raw indexed columns directly |
| Do indexes match filters? | B-tree, partial, covering |
| Do indexes hurt write paths? | Weigh HOT/WAL/disk trade-offs |
| Does BRIN fit? | Physical page correlation |
| Does partition pruning trigger? | Filter directly on partition key |
| `HashAggregate` or `GroupAggregate`? | Inspect `EXPLAIN` and group counts |
| Any disk spills? | Check temp I/O, batches, sort method |
| Does `work_mem` scale with concurrency? | Multiply across nodes/workers/queries |
| Are parallel workers helping? | Measure both throughput and latency |
| Are statistics fresh? | `ANALYZE`, extended stats where needed |
| Are CTEs blocking pushdown? | Materialized vs inlined |
| Does `LATERAL` loop too many times? | Check outer row count and inner index |
| Do window functions run post-aggregate? | Reduce rows sorted/windowed |
| Are empty days/regions handled? | `generate_series` + `LEFT JOIN` dimension |
| Does `GROUPING SETS` fit? | Watch multi-level cardinality |
| Is the report called repeatedly? | Materialized view / cache / summary |
| Is there a freshness contract? | Refresh schedule, lag, reconciliation |
| Are incremental summaries idempotent? | Event IDs, deltas, ordering |
| Is read-replica lag accounted for? | RPO/consistency and read routing |
| Are RLS/tenant filters enforced? | Enforce server-side authorization |
| Was before/after benchmarked? | Correctness, buffers, temp I/O, latency |
| Was it tested under real concurrency? | CPU, I/O, P95, and throughput |
| Are high-frequency reports tracked? | `calls × mean_exec_time` in `pg_stat_statements` |

## Conclusion

**Optimizing aggregations, conditional filtering, and reporting queries** in PostgreSQL goes far beyond adding indexes or swapping `SUM(CASE...)` for `FILTER`. The foundation is defining **the right grain and data scope**, then shrinking rows read, joined, and grouped so PostgreSQL can execute efficiently.

Core principles:

1. **Define metrics before tuning.** Order value, captured cash, and refunds come from distinct sources and timestamps.
2. **Distinguish `WHERE`, `HAVING`, and `FILTER`.** `WHERE` scopes input rows, `HAVING` filters groups, and `FILTER` scopes individual aggregates.
3. **Eliminate join fan-out.** Pre-aggregate child 1:N tables to the right grain before joining; never patch inflated totals with `SUM(DISTINCT amount)`.
4. **Handle `COUNT(DISTINCT)` and weighted averages carefully.** Distinct counts never add across overlapping groups.
5. **Filter time via half-open ranges in the right time zone** and keep predicates directly on indexed columns where possible.
6. **Choose indexes for the workload.** B-tree, partial, covering, BRIN, and partition pruning serve distinct purposes and must all be measured.
7. **Read real `EXPLAIN` output.** `HashAggregate`, `GroupAggregate`, `Sort`, parallel plans, temp I/O, and bad row estimates pinpoint bottlenecks.
8. **Don't treat extra RAM as the first fix.** Eliminating row explosion and filtering/grouping early usually matters far more than bumping `work_mem`.
9. **Materialized views and summaries suit repeated dashboards**, provided freshness contracts, refresh costs, idempotency, and reconciliation are designed in.
10. **Verify snapshot consistency, access control, and replication lag** before shipping any dashboard.

A well-optimized report is **accurate in business semantics, totals, time boundaries, and permissions**, while keeping CPU, memory, I/O, and latency predictable—allowing PostgreSQL to serve both operational workloads and analytical dashboards without trading correctness for speed.
