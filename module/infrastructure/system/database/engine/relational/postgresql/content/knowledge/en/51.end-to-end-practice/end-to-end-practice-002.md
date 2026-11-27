# Writing Reporting Queries with JOINs, CTEs, Aggregations, and Window Functions

A PostgreSQL report often needs to combine data from multiple tables, compute metrics by group, and enrich rows with period-over-period comparisons or rankings. `JOIN` brings related records into a single result set; aggregate functions collapse multiple rows into summary metrics; CTEs break a query into named steps; and window functions compute values across a group of rows while preserving each individual detail row.

When combining these techniques, the most critical concern is maintaining the correct data granularity. If you join two one-to-many tables before aggregating, row counts can multiply and distort revenue, order counts, or payment totals. This lesson uses a unified sales model to demonstrate how to design reporting queries, verify numbers, and improve performance.

## 1. Data Model Used in This Practice

Suppose a sales system has the following tables:

- `customers`: customers.
- `orders`: orders, each belonging to one customer.
- `order_items`: product line items within an order.
- `products`: product catalog.
- `payments`: payment attempts for an order. An order may be paid across multiple attempts.

Core relationships:

~~~text
customers 1 ───── n orders
orders    1 ───── n order_items
products  1 ───── n order_items
orders    1 ───── n payments
~~~

A simplified schema can be represented as follows:

~~~sql
CREATE TABLE customers (
    customer_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    region        text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
    product_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name text NOT NULL,
    category     text NOT NULL
);

CREATE TABLE orders (
    order_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    order_date  timestamptz NOT NULL DEFAULT now(),
    status      text NOT NULL,
    channel     text NOT NULL
);

CREATE TABLE order_items (
    order_id        bigint NOT NULL REFERENCES orders(order_id),
    product_id      bigint NOT NULL REFERENCES products(product_id),
    quantity        numeric(12, 2) NOT NULL CHECK (quantity > 0),
    unit_price      numeric(14, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount numeric(14, 2) NOT NULL DEFAULT 0
                    CHECK (discount_amount >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   bigint NOT NULL REFERENCES orders(order_id),
    paid_at    timestamptz NOT NULL DEFAULT now(),
    amount     numeric(14, 2) NOT NULL CHECK (amount >= 0),
    status     text NOT NULL
);
~~~

In these examples, the post-discount merchandise value is calculated per line item:

~~~sql
quantity * unit_price - discount_amount
~~~

Suppose the report only counts payments with `status = 'succeeded'`. Actual business rules may differ: some systems use `'captured'`, `'settled'`, or must subtract refunds. Always align on metric definitions before writing SQL.

Primary and foreign keys tell you how to join tables, but they do not automatically dictate the report's level of detail. Before every `JOIN`, identify what a single row on each side represents:

| Table | One Row Represents |
|---|---|
| `customers` | One customer |
| `orders` | One order |
| `order_items` | One product within one order |
| `products` | One product in the catalog |
| `payments` | One payment attempt |

Establishing this grain helps predict how many rows a `JOIN` can produce.

## 2. Combining Tables with `JOIN`

### 2.1. `INNER JOIN`

`INNER JOIN` returns only rows with matching join keys on both sides.

For example, listing orders alongside customer names:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.customer_name,
    c.region
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Because `customer_id` in `orders` is a `NOT NULL` foreign key, every valid order has exactly one matching customer. This join does not increase the row count relative to `orders`.

When joining `order_items` with `products`, each item row gains the product name and category:

~~~sql
SELECT
    oi.order_id,
    p.product_id,
    p.product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.discount_amount,
    oi.quantity * oi.unit_price - oi.discount_amount AS line_total
FROM order_items AS oi
JOIN products AS p
    ON p.product_id = oi.product_id
ORDER BY oi.order_id, p.product_name;
~~~

Because `product_id` is the primary key of `products`, each `order_items` row matches at most one product row.

### 2.2. `LEFT JOIN` to Retain Unmatched Rows

`LEFT JOIN` preserves all rows from the left table. When no matching row exists in the right table, the right-side columns evaluate to `NULL`.

For example, listing every customer and their orders if any exist:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_date
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_date DESC NULLS LAST;
~~~

Customers without orders still appear once with `NULL` order columns. Customers with multiple orders appear in multiple rows, one per order.

If the goal is to find customers who have never placed an order, you can use an anti-join:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

An equivalent approach, often clearer in intent, is `NOT EXISTS`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

### 2.3. Filter Conditions in `ON` vs. `WHERE`

With `LEFT JOIN`, where you place a filter condition can change the result.

Suppose you need to list all customers and only join completed orders:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'completed';
~~~

The `status` condition sits in `ON`, so customers without completed orders are still retained.

If you write the condition in `WHERE`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'completed';
~~~

Rows without orders have a `NULL` status and get filtered out. The result effectively behaves like an `INNER JOIN` with respect to that condition.

Practical rule:

- Place conditions determining which right-side rows are eligible to match inside `ON` when you want to preserve all left-side rows.
- Place final result filters inside `WHERE`.
- For `INNER JOIN`, equivalent conditions can generally go in either `ON` or `WHERE`; choose whichever is more readable.

### 2.4. `FULL JOIN` and Other Join Types

`FULL OUTER JOIN` retains rows present only in the left table as well as rows present only in the right table. It is useful when reconciling two datasets, such as product lists from a sales system and a warehouse system.

~~~sql
SELECT
    COALESCE(s.product_id, w.product_id) AS product_id,
    s.sold_quantity,
    w.stock_quantity
FROM sales_summary AS s
FULL OUTER JOIN warehouse_summary AS w
    ON w.product_id = s.product_id;
~~~

The query above assumes both summaries are pre-aggregated and each `product_id` has at most one row on each side.

`CROSS JOIN` produces every combination between two row sets. It can be useful when generating a month × region matrix or a reporting calendar, though the row count grows as the product of both sides' sizes. Use it only when all combinations are genuinely needed.

## 3. Avoiding Metric Multiplication When Joining Multiple One-to-Many Tables

This is the most common bug when writing revenue reports.

An order has 3 `order_items` rows and 2 `payments` rows. If you join both tables directly to `orders`, the result produces 3 × 2 = 6 rows for that order. Each item row is repeated twice, and each payment row is repeated three times.

Example of an error-prone query:

~~~sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS order_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN payments AS p
    ON p.order_id = o.order_id
WHERE p.status = 'succeeded'
GROUP BY o.order_id;
~~~

Suppose the order contains:

- Item A: 100,000 VND.
- Item B: 200,000 VND.
- Payment 1: 150,000 VND.
- Payment 2: 150,000 VND.

The correct result should be 300,000 VND in merchandise revenue and 300,000 VND collected. The direct join produces 4 rows; total merchandise becomes 600,000 VND and total payments also become 600,000 VND.

Do not patch this bug by adding `SUM(DISTINCT amount)` or `SUM(DISTINCT line_total)`. Two items can share the same value, and two payments can have the exact same amount; `DISTINCT` would drop valid transactions.

### 3.1. Aggregate Each Child Table Before Joining

The safe pattern is to reduce each one-to-many child table to the `order_id` grain before joining:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total,
        COUNT(*) AS item_line_count
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total,
        COUNT(*) AS payment_count
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.order_total, 0) AS order_total,
    COALESCE(i.item_line_count, 0) AS item_line_count,
    COALESCE(p.paid_total, 0) AS paid_total,
    COALESCE(p.payment_count, 0) AS payment_count
FROM orders AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

After `GROUP BY`, each CTE has at most one row per `order_id`. Joining them to `orders` therefore never multiplies metrics. `LEFT JOIN` keeps orders that have no items or no payments yet; `COALESCE` converts `NULL` totals to 0 when that matches business representation rules.

### 3.2. Verify Grain After Every Step

Before adding the next `JOIN`, ask yourself:

1. Does one row of the current result represent a customer, an order, a line item, or a payment?
2. Is the join key unique on the side being joined?
3. Is the relationship one-to-one, one-to-many, or many-to-many?
4. Does the metric being computed belong at the order level or the line-item level?
5. Could this `JOIN` duplicate a value already computed at a higher grain?

If a report needs order-level metrics, reduce child tables to one row per order first. If it needs line-item metrics, define an explicit allocation rule for how payments map down to items; never blindly assign the entire order payment to every product line.

## 4. Aggregating Data with `GROUP BY`

Aggregate functions take multiple rows and produce a single value per group. Common functions include:

| Function | Meaning |
|---|---|
| `COUNT(*)` | Counts rows in the group |
| `COUNT(column)` | Counts rows where `column` is non-NULL |
| `COUNT(DISTINCT column)` | Counts distinct non-NULL values |
| `SUM(column)` | Sums non-NULL values |
| `AVG(column)` | Averages non-NULL values |
| `MIN(column)`, `MAX(column)` | Minimum and maximum values |
| `BOOL_AND(expression)` | `TRUE` if every value in the group is `TRUE` |
| `BOOL_OR(expression)` | `TRUE` if at least one value is `TRUE` |
| `STRING_AGG(value, delimiter)` | Concatenates strings in the group |

For example, order count and revenue by customer:

~~~sql
SELECT
    o.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY o.customer_id
ORDER BY revenue DESC NULLS LAST;
~~~

Here results are grouped by `customer_id`. However, inner-joining `order_items` drops orders without any item rows. To preserve customers or orders without items, use `LEFT JOIN` or pre-aggregate `order_items` before joining.

### 4.1. Multi-Dimensional `GROUP BY`

Reports can group by multiple attributes, such as region, sales channel, and status:

~~~sql
SELECT
    c.region,
    o.channel,
    o.status,
    COUNT(*) AS order_count
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
GROUP BY
    c.region,
    o.channel,
    o.status
ORDER BY
    c.region,
    o.channel,
    o.status;
~~~

Each combination of values forms a separate group. If a column contains `NULL`, all `NULL` rows for that column are grouped together.

### 4.2. `COUNT(*)` vs. `COUNT(column)`

These two expressions behave differently when `NULL` values exist:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(p.payment_id) AS rows_with_payment,
    COUNT(DISTINCT p.order_id) AS orders_with_payment
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

`LEFT JOIN` produces a row with `NULL` payment columns for unpaid orders. `COUNT(*)` still counts that row; `COUNT(p.payment_id)` does not because `payment_id` is `NULL`.

`COUNT(DISTINCT p.order_id)` counts orders with at least one payment row. It is useful for order-count metrics, though `DISTINCT` should not be used as a blanket fix for join fan-out issues.

### 4.3. `SUM`, `AVG`, and `NULL`

`SUM` and `AVG` ignore `NULL` values. If all values in a group are `NULL`, `SUM` returns `NULL` rather than 0. Example aggregating per order:

~~~sql
SELECT
    order_id,
    COALESCE(SUM(amount), 0) AS total_amount,
    AVG(amount) AS average_payment
FROM payments
WHERE status = 'succeeded'
GROUP BY order_id;
~~~

The sample schema does not include `customer_id` in `payments`. To aggregate by customer, join through `orders`:

~~~sql
SELECT
    o.customer_id,
    COALESCE(SUM(p.amount), 0) AS total_paid
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
   AND p.status = 'succeeded'
GROUP BY o.customer_id;
~~~

In this query, each payment belongs to exactly one order, while a customer has many orders and each order can have many payments. Because only `payments` is aggregated without joining `order_items`, payment totals are not multiplied by item counts.

Apply `COALESCE` at the right level. If you need to distinguish "no payments yet" from "payments exist totaling 0", also include `COUNT(payment_id)` instead of simply replacing `NULL` with 0.

### 4.4. `FILTER` for Computing Multiple Metrics in One Pass

`FILTER` allows each aggregate function to specify its own condition:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM orders
GROUP BY customer_id;
~~~

Example computing successful payment totals alongside failed attempt counts:

~~~sql
SELECT
    order_id,
    COALESCE(SUM(amount) FILTER (WHERE status = 'succeeded'), 0)
        AS successful_amount,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_attempts
FROM payments
GROUP BY order_id;
~~~

`FILTER` is often easier to read than nested `CASE` expressions. Use `CASE` when cross-database compatibility or more complex logic is required.

### 4.5. `HAVING` to Filter Groups After Aggregation

`WHERE` filters input rows before `GROUP BY`; `HAVING` filters groups after aggregates are computed.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id
HAVING COUNT(*) >= 5
ORDER BY order_count DESC;
~~~

The query above considers only orders from the selected timestamp onward, then retains only customers with at least 5 orders in that set.

Do not place conditions on aggregate results in a `WHERE` clause at the same level as `GROUP BY`. Use `HAVING` or wrap the query in a CTE/subquery and filter in the outer query.

## 5. Aggregating by Day, Month, and Time Intervals

Time-series reports typically group with `date_trunc`:

~~~sql
SELECT
    date_trunc('month', order_date) AS month_start,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY date_trunc('month', order_date)
ORDER BY month_start;
~~~

Use half-open intervals `[from, to)`: include the start boundary and exclude the end boundary. This avoids guessing "end-of-day" values like `23:59:59.999999` and allows consecutive periods to chain seamlessly without overlap.

For `timestamptz` columns, standardize on a reporting time zone. `date_trunc` on `timestamptz` depends on the session `TimeZone` unless a time zone is explicitly specified. To report in Vietnam time:

~~~sql
SELECT
    date_trunc('month', order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')
        AS local_month,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
GROUP BY local_month
ORDER BY local_month;
~~~

`AT TIME ZONE` converts `timestamptz` into local `timestamp` to bucket by Vietnam calendar months. The filter range still compares directly against the `timestamptz` column, allowing a B-tree index on `order_date` to be used more effectively than wrapping the column in a function inside `WHERE`.

Avoid writing:

~~~sql
WHERE date_trunc('day', order_date) = DATE '2026-05-01'
~~~

Applying a function to the column can prevent a standard index on `order_date` from being used. Write a range predicate instead:

~~~sql
WHERE order_date >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
  AND order_date <  TIMESTAMPTZ '2026-05-02 00:00:00+07'
~~~

If days with zero transactions must still appear as 0, `GROUP BY` on `orders` alone cannot generate missing dates. Generate a calendar with `generate_series` and `LEFT JOIN` the metrics:

~~~sql
WITH calendar AS (
    SELECT generate_series(
        DATE '2026-05-01',
        DATE '2026-05-07',
        INTERVAL '1 day'
    )::date AS report_date
),
daily_orders AS (
    SELECT
        (order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS report_date,
        COUNT(*) AS order_count
    FROM orders
    WHERE order_date >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
      AND order_date <  TIMESTAMPTZ '2026-05-08 00:00:00+07'
    GROUP BY (order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    c.report_date,
    COALESCE(d.order_count, 0) AS order_count
FROM calendar AS c
LEFT JOIN daily_orders AS d
    ON d.report_date = c.report_date
ORDER BY c.report_date;
~~~

`generate_series` produces one row per day. `LEFT JOIN` preserves days without orders; `COALESCE` displays 0 instead of `NULL`.

## 6. Using CTEs to Break Queries into Steps

A CTE (Common Table Expression) is declared with `WITH` and names an intermediate result set. It splits a report into meaningful stages, reduces duplicated logic, and clarifies the grain of each dataset.

Basic structure:

~~~sql
WITH
step_one AS (
    SELECT ...
),
step_two AS (
    SELECT ...
    FROM step_one
)
SELECT ...
FROM step_two;
~~~

A CTE can reference CTEs declared earlier in the same `WITH` clause. A CTE does not create a persistent physical table; its name scope exists only within that statement.

### 6.1. Building a Multi-Step Report

Suppose we need a monthly and regional report showing order count, customer count, merchandise revenue, and collected payments. The first step aggregates items and payments separately at the `order_id` level:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total,
        COUNT(*) AS item_line_count
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        c.region,
        o.channel,
        o.order_date,
        o.status,
        COALESCE(i.order_total, 0) AS order_total,
        COALESCE(p.paid_total, 0) AS paid_total
    FROM orders AS o
    JOIN customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    LEFT JOIN payment_totals AS p
        ON p.order_id = o.order_id
)
SELECT
    date_trunc('month', order_date) AS month_start,
    region,
    channel,
    COUNT(*) AS order_count,
    COUNT(DISTINCT customer_id) AS customer_count,
    SUM(order_total) AS merchandise_total,
    SUM(paid_total) AS collected_total,
    SUM(order_total - paid_total) AS difference_total
FROM order_facts
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
  AND status = 'completed'
GROUP BY
    date_trunc('month', order_date),
    region,
    channel
ORDER BY
    month_start,
    region,
    channel;
~~~

Purpose of each step:

1. `item_totals`: one row per `order_id`, calculating merchandise value and item line count.
2. `payment_totals`: one row per `order_id`, summing only succeeded payments.
3. `order_facts`: combines order and customer attributes with the two pre-aggregated sets.
4. Final query: filters the reporting period and status, then groups by month, region, and channel.

Because `item_totals` and `payment_totals` already have at most one row per `order_id`, the two `LEFT JOIN`s never multiply metrics. `order_facts` has one row per qualifying order. `COUNT(*)` therefore counts orders, and `COUNT(DISTINCT customer_id)` counts unique customers within each month/region/channel group.

The `difference_total` metric in this example is the difference between merchandise value and succeeded payments. It only represents an accounts-receivable balance if business rules involve no taxes, shipping fees, refunds, overpayments, cancellations, or other adjustments. In production systems, define explicit balance formulas and include all missing components.

### 6.2. CTEs Make Queries Easier to Inspect

When a query is long, you can test each CTE individually by temporarily replacing the final `SELECT` with:

~~~sql
SELECT *
FROM item_totals
ORDER BY order_id
LIMIT 20;
~~~

Then inspect `payment_totals`, and then `order_facts`. At each step, verify row counts and expected key uniqueness:

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM order_facts;
~~~

If `order_facts` is designed as one row per order, these two counts must match. If they do not, check which joined table introduced extra rows.

### 6.3. CTEs and Optimization

CTEs are a logical structuring tool, not automatically equivalent to materialized temporary tables on disk. Starting in PostgreSQL 12, many non-recursive, side-effect-free CTEs can be inlined into the main query when the optimizer deems it beneficial. A CTE referenced multiple times, or marked `MATERIALIZED`, may be evaluated and stored as an intermediate result; this can sometimes avoid repeated computation, but can also consume memory or disk and block predicate pushdown.

You can specify:

- `MATERIALIZED`: forces the CTE to be evaluated into an intermediate result.
- `NOT MATERIALIZED`: allows the planner to inline the CTE in supported cases.

Do not add these two keywords out of habit. Measure with `EXPLAIN (ANALYZE, BUFFERS)` before and after on representative data.

## 7. Window Functions

Aggregate functions with `GROUP BY` collapse multiple rows into one row per group. Window functions compute across a set of rows related to the current row while still returning one result per input row.

Syntax:

~~~sql
function_name(expression) OVER (
    PARTITION BY group_columns
    ORDER BY sort_columns
    frame_clause
)
~~~

Components:

- `PARTITION BY` divides data into independent partitions. Omitting `PARTITION BY` treats the entire result set as a single partition.
- `ORDER BY` defines row ordering within each partition.
- The frame clause defines the window of rows participating in the calculation around the current row.

For example, numbering orders per customer:

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
    ) AS order_sequence
FROM orders
ORDER BY customer_id, order_date, order_id;
~~~

Each customer gets an independent counter. `order_id` is added as a tie-breaker so ordering remains deterministic when multiple orders share the same `order_date`.

### 7.1. `ROW_NUMBER`, `RANK`, and `DENSE_RANK`

All three functions assign rankings, but they handle ties differently:

| Sort Value | `ROW_NUMBER` | `RANK` | `DENSE_RANK` |
|---|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 100 | 2 | 1 | 1 |
| 90 | 3 | 3 | 2 |
| 80 | 4 | 4 | 3 |

- `ROW_NUMBER` always assigns a unique sequential number to each row.
- `RANK` gives tied rows the same rank and skips the next rank number(s).
- `DENSE_RANK` gives tied rows the same rank without skipping numbers.

Ranking customers by revenue:

~~~sql
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_revenue_rank
FROM customer_revenue
ORDER BY revenue DESC, customer_id;
~~~

If ties in revenue should keep the same rank, do not include `customer_id` inside `ORDER BY` within `RANK`, because adding a unique key breaks ties. You can still use `customer_id` in the outer `ORDER BY` for deterministic display.

### 7.2. Selecting the Top N Rows per Group

For example, fetching the 3 most recent orders for each customer:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        order_date,
        status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY order_date DESC, order_id DESC
        ) AS row_num
    FROM orders
)
SELECT
    order_id,
    customer_id,
    order_date,
    status
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, order_date DESC, order_id DESC;
~~~

You cannot reference the alias `row_num` directly in a `WHERE` clause at the same level because `WHERE` is evaluated before `SELECT` expressions and window functions. Place the window function in a CTE or subquery and filter in the outer query.

If the requirement is to fetch the top 3 revenue tiers including ties, use `RANK` or `DENSE_RANK` according to business rules rather than `ROW_NUMBER`.

### 7.3. `LAG` and `LEAD` for Period-over-Period Comparisons

`LAG` retrieves a value from a preceding row in the same partition; `LEAD` retrieves a value from a following row. They are useful for computing month-over-month growth:

~~~sql
WITH monthly_revenue AS (
    SELECT
        date_trunc('month', o.order_date) AS month_start,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY date_trunc('month', o.order_date)
),
with_previous AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM monthly_revenue
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_change,
    ROUND(
        100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS growth_percent
FROM with_previous
ORDER BY month_start;
~~~

`NULLIF(previous_revenue, 0)` returns `NULL` when the prior period is 0, preventing division-by-zero errors. The first period also has a `NULL` `previous_revenue` because no preceding row exists. You can use `COALESCE` to display a default value, but avoid treating a missing prior period as zero revenue if the report needs to distinguish "no data" from "zero revenue generated".

This query only includes months with orders. To compare continuously across months without orders, generate a calendar with `generate_series`, `LEFT JOIN` monthly revenue, explicitly fill zeros, and then apply `LAG`.

### 7.4. Running Totals with `SUM OVER`

A running total sums values from the start of the partition up to the current row:

~~~sql
WITH daily_revenue AS (
    SELECT
        (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sales_day,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    sales_day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY sales_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_revenue
ORDER BY sales_day;
~~~

`ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` explicitly defines the window from the first row to the current row. This is the appropriate syntax for a row-by-row running total.

When multiple rows share the same `ORDER BY` value, the default frame (`RANGE`) groups peer rows together into the same frame. Add a unique tie-breaker to `ORDER BY` or specify a `ROWS` frame explicitly when per-row ordering is needed.

### 7.5. Group Totals While Preserving Individual Rows

You can use `SUM OVER` to show a customer's total lifetime spend alongside each individual order:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total
    FROM order_items
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        COALESCE(i.order_total, 0) AS order_total
    FROM orders AS o
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
)
SELECT
    order_id,
    customer_id,
    order_date,
    SUM(order_total) OVER (
        PARTITION BY customer_id
    ) AS customer_lifetime_total
FROM order_facts
ORDER BY customer_id, order_date, order_id;
~~~

Here `order_facts` is assumed to have one row per order. Unlike `GROUP BY customer_id`, the window function does not collapse orders into a single row; the customer total is repeated on every order belonging to that customer.

### 7.6. Moving Averages

`ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` computes over at most 7 rows, which is not necessarily 7 calendar days if days with no activity are missing:

~~~sql
WITH daily_revenue AS (
    SELECT
        (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sales_day,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS daily_revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY (o.order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    sales_day,
    daily_revenue,
    AVG(daily_revenue) OVER (
        ORDER BY sales_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_average_7_rows
FROM daily_revenue;
~~~

For a true 7-calendar-day moving average, first generate a complete calendar, `LEFT JOIN` daily revenue, and fill non-transaction days with 0. Only then do 7 consecutive rows correspond to 7 consecutive calendar days.

## 8. Combining `GROUP BY` and Window Functions

A very common pattern is to aggregate first, then compute rankings or shares over the aggregated result. PostgreSQL does not allow window functions directly on ungrouped columns alongside `GROUP BY` unless they operate on the grouped columns or aggregates; using a CTE or subquery keeps it clean.

Example: monthly revenue by category, category rank within each month, and share of total monthly revenue:

~~~sql
WITH category_month AS (
    SELECT
        date_trunc('month', o.order_date) AS month_start,
        p.category,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    JOIN products AS p
        ON p.product_id = oi.product_id
    WHERE o.status = 'completed'
    GROUP BY
        date_trunc('month', o.order_date),
        p.category
),
ranked AS (
    SELECT
        month_start,
        category,
        revenue,
        RANK() OVER (
            PARTITION BY month_start
            ORDER BY revenue DESC
        ) AS category_rank,
        SUM(revenue) OVER (
            PARTITION BY month_start
        ) AS month_revenue
    FROM category_month
)
SELECT
    month_start,
    category,
    revenue,
    category_rank,
    ROUND(100.0 * revenue / NULLIF(month_revenue, 0), 2)
        AS revenue_share_percent
FROM ranked
ORDER BY month_start, category_rank, category;
~~~

The `category_month` CTE has one row per month and category. The `ranked` CTE computes the rank and monthly total across those rows. The outer query calculates percentages and formats the output.

Monthly revenue in this example sums completed orders that have item rows. If you need to display categories with zero revenue, build a full list of months and categories and `LEFT JOIN` the figures.

## 9. `GROUPING SETS`, `ROLLUP`, and `CUBE`

When a report requires multiple levels of aggregation, PostgreSQL supports generating multiple grouping sets in a single query.

For example, computing total revenue by region and channel, by region alone, by channel alone, and the grand total:

~~~sql
SELECT
    c.region,
    o.channel,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue,
    GROUPING(c.region) AS region_is_total,
    GROUPING(o.channel) AS channel_is_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY GROUPING SETS (
    (c.region, o.channel),
    (c.region),
    (o.channel),
    ()
)
ORDER BY
    region_is_total,
    c.region,
    channel_is_total,
    o.channel;
~~~

`GROUPING(column)` returns `1` when the column is omitted from the current grouping set and `0` when it is included. This distinguishes a `NULL` produced by a subtotal row from an actual `NULL` in the underlying data.

`ROLLUP(region, channel)` generates detail totals by `(region, channel)`, subtotals by `region`, and a grand total. `CUBE(region, channel)` generates every possible grouping combination, including subtotals along each individual dimension. The number of grouping sets grows rapidly with the number of dimensions, so use `CUBE` only when every combination is truly needed.

## 10. Structuring a Complete Reporting Query

A maintainable reporting query typically follows these layers:

1. Filter the data scope and business statuses.
2. Aggregate child tables at the appropriate grain.
3. Join dimensions such as customer, product, and region.
4. Aggregate by reporting dimensions.
5. Compute rankings, running totals, differences, or shares using window functions.
6. Format and sort the final output.

Example: monthly revenue leaderboard by region:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total
    FROM order_items
    GROUP BY order_id
),
order_facts AS (
    SELECT
        o.order_id,
        o.order_date,
        c.region,
        COALESCE(i.order_total, 0) AS order_total
    FROM orders AS o
    JOIN customers AS c
        ON c.customer_id = o.customer_id
    LEFT JOIN item_totals AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
      AND o.order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
      AND o.order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
),
monthly_region AS (
    SELECT
        date_trunc('month', order_date) AS month_start,
        region,
        SUM(order_total) AS revenue,
        COUNT(*) AS order_count
    FROM order_facts
    GROUP BY date_trunc('month', order_date), region
),
ranked AS (
    SELECT
        month_start,
        region,
        revenue,
        order_count,
        RANK() OVER (
            PARTITION BY month_start
            ORDER BY revenue DESC
        ) AS region_rank,
        SUM(revenue) OVER (
            PARTITION BY month_start
        ) AS month_total
    FROM monthly_region
)
SELECT
    month_start,
    region,
    revenue,
    order_count,
    region_rank,
    ROUND(100.0 * revenue / NULLIF(month_total, 0), 2)
        AS revenue_share_percent
FROM ranked
ORDER BY month_start, region_rank, region;
~~~

This query clearly preserves each grain:

- `item_totals`: one row per order.
- `order_facts`: one row per completed order.
- `monthly_region`: one row per month and region.
- `ranked`: still one row per month and region, enriched with rank and share.

If only the top 3 regions per month are needed, add another CTE or outer query filtering `region_rank`. Use `RANK <= 3` to retain regions tied for third place; use `ROW_NUMBER <= 3` with a deterministic tie-breaker when strictly at most three rows are required.

## 11. Logical Processing Order of `SELECT` and Common Pitfalls

A useful mental model for general logical evaluation order:

~~~text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY
    ↓
HAVING
    ↓
SELECT (aggregate and window expressions)
    ↓
DISTINCT
    ↓
ORDER BY
    ↓
LIMIT / OFFSET
~~~

This is a logical order for understanding query semantics, not a guarantee that PostgreSQL physically executes steps strictly in that sequence.

Key consequences:

- `WHERE` cannot filter aggregate results at the same level; use `HAVING`.
- `WHERE` and `HAVING` at the same level cannot reference window function results; wrap the query and filter outside.
- Window functions operate on the row set produced after `FROM`, `WHERE`, `GROUP BY`, and `HAVING`.
- The outer `ORDER BY` controls output display order; `ORDER BY` inside `OVER` only controls window calculation order.
- `LIMIT` restricts the final output rows, not the rows feeding earlier sums or rankings.

Example filtering by rank:

~~~sql
WITH product_revenue AS (
    SELECT
        oi.product_id,
        SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue
    FROM order_items AS oi
    JOIN orders AS o
        ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
    GROUP BY oi.product_id
),
ranked_products AS (
    SELECT
        product_id,
        revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC, product_id) AS rn
    FROM product_revenue
)
SELECT
    product_id,
    revenue,
    rn
FROM ranked_products
WHERE rn <= 10
ORDER BY rn;
~~~

## 12. Verifying Data Accuracy

Before shipping a report to a dashboard or stakeholders, validate figures at every stage.

### 12.1. Reconciling Totals Before and After `JOIN`

If payments are aggregated at the `order_id` level, the total amount across the dataset before and after joining to `orders` should match (assuming no additional filters alter the order set):

~~~sql
WITH payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    WHERE status = 'succeeded'
    GROUP BY order_id
)
SELECT
    (SELECT COALESCE(SUM(amount), 0)
     FROM payments
     WHERE status = 'succeeded') AS source_total,
    (SELECT COALESCE(SUM(p.paid_total), 0)
     FROM orders AS o
     LEFT JOIN payment_totals AS p
        ON p.order_id = o.order_id) AS joined_total;
~~~

If payments reference non-existent orders (normally impossible when foreign keys are enabled and valid), or if the second query filters orders by date or status, the two totals will differ. Ensure both sides reconcile over the exact same scope.

### 12.2. Checking Grain Uniqueness

If `order_facts` is saved as a view or temporary table for standalone inspection, you can run:

~~~sql
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM order_facts
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

If `order_facts` is supposed to contain one row per order, this query must return zero rows. If `order_facts` is only a CTE inside a single statement, attach this check inside the same `WITH` statement since a CTE's scope ends with that statement.

### 12.3. Checking `NULL` and Missing Data

Ask:

- Should customers without a region appear in a `NULL` group or be excluded?
- Should orders without line items appear in the report?
- Are `pending`, `failed`, or `refunded` payments included?
- Does `NULL` mean unknown, not applicable, or zero?
- Do days without transactions need to be shown?

Do not automatically convert every `NULL` to 0. `NULL` typically represents missing or undefined; 0 is a concrete value. Use `COALESCE` only when reporting rules explicitly define the interpretation.

### 12.4. Testing Edge Cases

Test reports against:

- Zero rows in the reporting period.
- Only a single customer or single order.
- An order with multiple line items and multiple payments.
- Two line items or payments with identical amounts.
- A month with no transactions.
- One customer with multiple orders at the exact same timestamp.
- Transactions at the exact start and exact end boundaries of the period.
- Rows with `NULL` in dimensions such as `region` or `category`.

These cases commonly expose join fan-out bugs, miscounts, ranking errors, or missing calendar dates.

## 13. Improving Report Query Performance

A correct query that runs slowly still needs optimization. Start by inspecting the execution plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND order_date <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

`EXPLAIN ANALYZE` actually executes the SQL statement. For heavy reporting queries, weigh load and runtime before running in production. `BUFFERS` shows PostgreSQL page reads and cache hits across plan nodes; it does not replace storage-layer metrics.

Several optimization approaches:

### 13.1. Indexing Filter Predicates and `JOIN` Keys

Examples:

~~~sql
CREATE INDEX idx_orders_order_date
    ON orders (order_date);

CREATE INDEX idx_orders_customer_date
    ON orders (customer_id, order_date);

CREATE INDEX idx_order_items_order
    ON order_items (order_id);

CREATE INDEX idx_payments_success_order
    ON payments (order_id)
    WHERE status = 'succeeded';
~~~

Some indexes may already exist via `PRIMARY KEY` or `UNIQUE` constraints. For example, `order_items` has primary key `(order_id, product_id)`, which already creates a B-tree index leading with `order_id`; `idx_order_items_order` would be redundant in this sample schema and unnecessary. Always inspect existing indexes before adding new ones.

A partial index on `payments` can help when reports frequently read only succeeded payments. Query predicates must align with the index predicate for the planner to use it.

### 13.2. Filter Early and Select Only Needed Columns

Push time range, status, and tenant filters into the earliest appropriate stage to shrink the row volume flowing into `JOIN`s and aggregations. Avoid `SELECT *` in large reports when only a few columns are needed.

However, when using `LEFT JOIN`, place filters carefully so you do not inadvertently turn it into an `INNER JOIN`. Optimize by pushing conditions into `ON` or into the right-hand CTE when semantically appropriate.

### 13.3. Avoid Overusing `DISTINCT`

`DISTINCT` incurs sorting or hashing overhead and can mask duplicate rows caused by an improper `JOIN`. Before adding `DISTINCT`, determine why duplicates exist. If the goal is one row per `order_id`, aggregate or select one row using an explicit rule.

### 13.4. Check Statistics and Plans

`ANALYZE` updates table statistics so the planner can estimate row counts and choose join strategies. Frequently modified tables may need fresher statistics. Compare estimated rows vs. actual rows in `EXPLAIN ANALYZE`; large discrepancies can lead to poor `JOIN` or aggregation plans.

Never assume a hash join is always faster than a nested loop or merge join. The best choice depends on dataset size, indexes, sort order, and value distribution.

### 13.5. Avoid Creating Too Many Indexes

Every index consumes storage and adds overhead to `INSERT`, `UPDATE`, `DELETE`, `VACUUM`, and backups. Create indexes based on frequent queries and measured metrics; check index usage before adding more.

## 14. Recommended Practice Workflow

When given a reporting requirement, follow this sequence:

1. Write down the business definition of each metric: revenue, collected cash, order count, active customers.
2. Identify the grain of the final output: one row per day, per month/region, per customer, or per product.
3. List source tables, join keys, and one-to-one/one-to-many relationships.
4. Identify child tables that must be pre-aggregated to prevent fan-out.
5. Write the `JOIN` query and check row counts after each step.
6. Add `GROUP BY` and aggregate functions; define explicit `NULL` handling.
7. Use CTEs to name each business step.
8. Add window functions only after the dataset has the right grain.
9. Verify time ranges, time zones, tied rankings, and zero-activity dates.
10. Reconcile totals against source queries or verified reports.
11. Run `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment and tune based on observed measurements.
12. Document metric definitions and sample test data so others can re-verify.

## 15. Practice Exercises

Use the sales schema at the beginning of this lesson to write the following queries. Determine the grain before writing SQL for each exercise.

**Exercise 1 — Orders per Customer**

List each customer, their completed order count, and total merchandise value. Customers with no completed orders must still appear with an order count of 0.

Hint: start from `customers`, `LEFT JOIN` a pre-aggregated orders set, or use a CTE aggregating `orders` and `order_items` at the `customer_id` grain. Place the `status` condition so customers without orders are not filtered out.

**Exercise 2 — Monthly Sales Channels**

Calculate order count, merchandise revenue, and unique customers by month and `channel`. Count only `completed` orders in the reporting year.

Hint: pre-aggregate items at the `order_id` level before joining, then group by month and `channel`.

**Exercise 3 — Reconciling Revenue and Collected Payments**

Compute `order_total`, `paid_total`, and the difference for each order. Orders without payments must still appear in the output.

Hint: build `item_totals` and `payment_totals` separately, each CTE having one row per `order_id`.

**Exercise 4 — Top 5 Products per Category**

Compute revenue per product within each `category`, then rank products by revenue within their category. Display the top 5 products per category.

Hint: `GROUP BY` `category` and `product_id` in a CTE, then apply `ROW_NUMBER` or `RANK` in the outer query.

**Exercise 5 — Month-over-Month Revenue Comparison**

Calculate monthly revenue, prior-month revenue, and percentage growth rate. Safely handle prior months with 0 revenue or no data.

Hint: aggregate by month, generate a calendar if empty months are needed, then use `LAG` and `NULLIF`.

**Exercise 6 — Cumulative Revenue by Region**

Compute daily revenue and running totals within each region. Days with no orders must display 0 without breaking the date sequence.

Hint: generate a daily calendar and a region list, create the day × region combinations, `LEFT JOIN` daily aggregates, and apply `SUM OVER (PARTITION BY region ORDER BY day)` with an explicit `ROWS` frame.

**Exercise 7 — Detecting Fan-Out Bugs**

Create an order with at least two line items and two payments. Compare total revenue and total payments from a direct `JOIN` against the results when pre-aggregating each child table before joining.

Hint: count result rows at the `order_id` level and explain why the row count equals the product of the two child tables' row counts.

## Conclusion

`JOIN` combines related data; `GROUP BY` and aggregate functions calculate metrics by group; CTEs structure reports into named steps; window functions add rankings, period comparisons, shares, and running totals without collapsing individual rows.

Always determine the grain before joining tables. Pre-aggregate one-to-many branches before combining when metrics belong to a higher grain, place join filters carefully, handle `NULL`s and timestamps according to business rules, and only then add window functions. Finally, verify row counts and reconcile totals to guarantee report accuracy before optimizing performance.
