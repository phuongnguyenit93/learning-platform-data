# FILTER on Aggregate Functions and Conditional Statistics in PostgreSQL

A sales dashboard often displays multiple metrics at once: total orders, paid orders, cancelled orders, revenue from successful orders, average paid order value, and conversion rate by channel. These figures come from the **same dataset**, yet each metric cares about **a different subset of rows**.

With PostgreSQL, you do not need a separate query for each metric or nested subqueries everywhere. The **`FILTER (WHERE ...)` clause on aggregate functions** expresses this directly: *include only rows satisfying this condition in the corresponding aggregate*.

For example:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM orders;
~~~

In a single output row, `COUNT(*)` counts every row, while each `FILTER` expression selects its own row subset for a specific `COUNT` or `SUM`. **A FILTER condition does not remove rows from the entire query** like an outer `WHERE` does; it affects only the aggregate function it is attached to.

This lesson builds a small orders dataset and walks through `FILTER` syntax with `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `DISTINCT`, `ARRAY_AGG`, grouped and monthly statistics, percentages, `HAVING`, `OVER` windows, `NULL` handling, comparisons with `CASE`, and performance considerations. Examples use modern PostgreSQL syntax.

## 1. Review of How Aggregate Functions Work

Aggregate functions take multiple rows and return a single result for a row set or **per group**.

| Function | Basic Behavior | Key Point to Remember |
| --- | --- | --- |
| `COUNT(*)` | Counts rows | Includes rows with null columns |
| `COUNT(expression)` | Counts **non-NULL** values of the expression | Differs from `COUNT(*)` when nulls exist |
| `SUM(expression)` | Sums non-null values | Returns `NULL` if there are no input values |
| `AVG(expression)` | Averages non-null values | Denominator is the number of non-null inputs |
| `MIN(expression)` | Minimum value | Ignores nulls |
| `MAX(expression)` | Maximum value | Ignores nulls |
| `BOOL_AND` / `BOOL_OR` | Aggregates boolean values | Ignores nulls per aggregate semantics |
| `ARRAY_AGG` / `JSONB_AGG` | Collects values into an array/JSON | Watch element ordering and empty row sets |
| `STDDEV_SAMP` | Sample standard deviation | Requires sufficient input values |

Typical example:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS sum_amount,
    AVG(amount) AS avg_amount
FROM sales_orders;
~~~

Without `GROUP BY`, these functions operate over the same overall row set fed into aggregation. With `GROUP BY channel_code`, they evaluate independently for each sales channel group.

### Question: What if we need three different filter conditions?

A common approach is writing three separate queries:

~~~sql
SELECT COUNT(*) FROM sales_orders
WHERE status = 'paid';

SELECT COUNT(*) FROM sales_orders
WHERE status = 'pending';

SELECT COUNT(*) FROM sales_orders
WHERE status = 'cancelled';
~~~

These queries are all valid, but if you want **one summary row** or multiple metrics side by side per channel or month, PostgreSQL offers a cleaner, clearer syntax: `FILTER`.

## 2. FILTER Syntax in PostgreSQL

General form:

~~~sql
aggregate_function(arguments)
    FILTER (WHERE boolean_expression)
~~~

Some examples:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')

SUM(amount) FILTER (WHERE status = 'paid')

AVG(amount) FILTER (WHERE status = 'paid')

COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

Meaning:

1. PostgreSQL inspects the input rows supplied to the aggregate by the current query.
2. For **this specific aggregate function**, only rows where the `FILTER` condition evaluates to `TRUE` enter the aggregation.
3. Rows where the filter evaluates to `FALSE` or `NULL/UNKNOWN` are excluded for that aggregate.
4. **Other** aggregate functions in the same `SELECT` still apply their own filters or use the full input set.

### Visual Diagram

~~~text
                 Rows after FROM / WHERE
                             |
                  +----------+----------+
                  |          |          |
                  v          v          v
               COUNT(*)    status     status
                all       = 'paid'   = 'cancelled'
                  |          |          |
                  v          v          v
               16 orders  COUNT(*)   COUNT(*)
                           FILTER     FILTER
                             |          |
                             v          v
                          8 orders   3 orders
                  |          |          |
                  +----------+----------+
                             |
                             v
                       One summary row
~~~

The numbers in the diagram match the practice dataset in the next section.

### Where Does FILTER Go in an Expression?

`FILTER` appears **after the aggregate function call**:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
~~~

Do not write:

~~~sql
-- Syntax error:
SUM(FILTER (WHERE status = 'paid') amount)
~~~

When an aggregate is used as a **window function**, `FILTER` precedes `OVER`:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Not every function accepts `FILTER`: for instance, `ROW_NUMBER()` is a dedicated window function, **not an aggregate window function**, so it does not accept `FILTER` the way `COUNT()` or `SUM()` does.

## 3. Preparing the Practice Data

Examples use a dedicated `filter_lab` schema on a PostgreSQL database where you are allowed to create objects. Never run these DDL or data-cleanup statements on a production database.

### 3.1. Creating the Schema and Channels Catalog

~~~sql
CREATE SCHEMA filter_lab;

CREATE TABLE filter_lab.channels (
    channel_code text PRIMARY KEY,
    channel_name text NOT NULL
);

INSERT INTO filter_lab.channels (channel_code, channel_name)
VALUES
    ('web', 'Website'),
    ('store', 'Store'),
    ('partner', 'Partner'),
    ('affiliate', 'Affiliate Marketing');
~~~

The `affiliate` channel intentionally **has no orders yet** so we can verify how `COUNT`, `SUM`, and `LEFT JOIN` handle empty groups.

### 3.2. Creating the Orders Table

~~~sql
CREATE TABLE filter_lab.sales_orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_code text NOT NULL
        REFERENCES filter_lab.channels(channel_code),
    customer_id bigint NOT NULL,
    order_date date NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'paid', 'pending', 'cancelled', 'refunded'
        )),
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0)
);
~~~

Data semantics in this lesson:

- `paid`: successfully paid order.
- `pending`: order awaiting completion.
- `cancelled`: cancelled order.
- `refunded`: order marked as refunded.
- `amount`: **recorded order value in the sample**, not automatically net revenue or cash flow.

This is a simulated table for learning `FILTER`. In real accounting systems, payments and refunds must be modeled explicitly through transactions and reconciliation rules.

### 3.3. Inserting 16 Sample Orders

~~~sql
INSERT INTO filter_lab.sales_orders
    (channel_code, customer_id, order_date, status, amount)
VALUES
    ('web',     1, DATE '2026-01-02', 'paid',      120.00),
    ('web',     2, DATE '2026-01-03', 'paid',       80.00),
    ('web',     1, DATE '2026-01-05', 'pending',    50.00),
    ('store',   3, DATE '2026-01-06', 'paid',      200.00),
    ('store',   4, DATE '2026-01-10', 'cancelled',   0.00),
    ('partner', 5, DATE '2026-01-12', 'paid',      150.00),
    ('partner', 2, DATE '2026-01-14', 'refunded',   70.00),
    ('web',     1, DATE '2026-02-02', 'paid',       90.00),
    ('web',     3, DATE '2026-02-03', 'cancelled',   0.00),
    ('store',   4, DATE '2026-02-04', 'paid',      110.00),
    ('store',   5, DATE '2026-02-05', 'pending',    40.00),
    ('partner', 6, DATE '2026-02-06', 'paid',      180.00),
    ('partner', 7, DATE '2026-02-09', 'pending',    60.00),
    ('web',     2, DATE '2026-02-12', 'refunded',   30.00),
    ('store',   1, DATE '2026-02-15', 'paid',      130.00),
    ('partner', 6, DATE '2026-02-16', 'cancelled',   0.00);
~~~

Check the total row count and status breakdown:

~~~sql
SELECT status, COUNT(*) AS n
FROM filter_lab.sales_orders
GROUP BY status
ORDER BY status;
~~~

Expected output:

| status | n |
| --- | ---: |
| `cancelled` | 3 |
| `paid` | 8 |
| `pending` | 3 |
| `refunded` | 2 |

Total is **16 orders**. All examples below assume these freshly created tables without additional inserts or modifications.

## 4. Counting Multiple Statuses with COUNT(*) FILTER

One query computing multiple metrics:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    COUNT(*) FILTER (
        WHERE status = 'refunded'
    ) AS refunded_orders
FROM filter_lab.sales_orders;
~~~

Result:

| total_orders | paid_orders | pending_orders | cancelled_orders | refunded_orders |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 8 | 3 | 3 | 2 |

Key observations:

- `COUNT(*)` without `FILTER` counts all 16 rows.
- `COUNT(*) FILTER (WHERE status = 'paid')` counts only the 8 rows with status `paid`.
- `pending` rows stay in the dataset for the other aggregates.
- PostgreSQL does not create four temporary tables when you write four `FILTER` clauses; these are conditional aggregates evaluated within the same query.

### A FILTER with Multiple Conditions

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid' AND amount > 100
    ) AS paid_above_100
FROM filter_lab.sales_orders;
~~~

On the sample data, the result is **6**: paid orders with amounts 120, 200, 150, 110, 180, and 130. The two paid orders with amounts 80 and 90 do not qualify.

The condition inside `FILTER` can be any valid boolean expression using `AND`, `OR`, `IN`, date ranges, comparisons, or other boolean-returning expressions. For complex conditions, use clear parentheses and pay attention to `NULL` behavior.

## 5. SUM, AVG, MIN, and MAX with FILTER

`FILTER` is not restricted to `COUNT`. Other aggregate functions can take their own conditions too.

~~~sql
SELECT
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount,
    AVG(amount) FILTER (
        WHERE status = 'paid'
    ) AS avg_paid_order,
    MIN(amount) FILTER (
        WHERE status = 'paid'
    ) AS smallest_paid_order,
    MAX(amount) FILTER (
        WHERE status = 'paid'
    ) AS largest_paid_order
FROM filter_lab.sales_orders;
~~~

With the sample data:

| Metric | Value |
| --- | ---: |
| Total `paid` order value | 1060.00 |
| Average `paid` order value | 132.50 |
| Smallest `paid` order value | 80.00 |
| Largest `paid` order value | 200.00 |

Average calculation: `1060 / 8 = 132.50`. `cancelled` orders with `amount = 0` are **not in the denominator** because they do not satisfy `status = 'paid'`.

### "Revenue" Labels Must Be Defined Precisely

In this lesson, `SUM(amount) FILTER (WHERE status = 'paid')` is described as **total value of orders currently in paid status**. Do not automatically equate it with **accounting revenue** or **net revenue**:

- A paid order may be partially refunded.
- Current order status may change later, altering recomputed totals.
- Refunds, discounts, taxes, fees, and exchange rates may require separate modeling.

`FILTER` helps compute statistics accurately according to the **chosen predicate**, but it does not decide on behalf of the business analyst whether that predicate matches the formal revenue definition.

## 6. FILTER vs. Query-Level WHERE

Both queries below count `paid` orders:

~~~sql
SELECT COUNT(*) AS paid_orders
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders;
~~~

Here, both return **8**. The difference appears when computing **multiple metrics**.

### WHERE Drops Rows Before All Aggregates

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

Result:

~~~text
total_orders      = 8
cancelled_orders  = 0
~~~

Because `WHERE status = 'paid'` already removed all cancelled orders from the **input row set**, `FILTER (WHERE status = 'cancelled')` cannot count them again.

### FILTER Preserves Multiple Metric Subsets in One Query

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

The result is `16, 8, 3`.

| Component | Effect |
| --- | --- |
| Outer `WHERE` | Selects the row set entering **all aggregates** in the query |
| `FILTER (WHERE ...)` | Selects the row set for **one specific aggregate** |
| `GROUP BY` | Partitions remaining rows into groups |
| `HAVING` | Selects groups based on group/aggregate expressions |
| Outermost `ORDER BY` | Sorts the final result rows |

There is no rule saying you should always replace `WHERE` with `FILTER`. If a report only examines February orders, `WHERE order_date >= ...` remains the best way to restrict the overall dataset, while `FILTER` separates statuses **within that selected month**.

## 7. Combining GROUP BY and FILTER: Channel Statistics

To inspect multiple metrics by sales channel:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Expected output:

| channel_code | total_orders | paid_orders | pending_orders | cancelled_orders | paid_amount |
| --- | ---: | ---: | ---: | ---: | ---: |
| partner | 5 | 2 | 1 | 1 | 330.00 |
| store | 5 | 3 | 1 | 1 | 440.00 |
| web | 6 | 3 | 1 | 1 | 290.00 |

The `affiliate` group does not appear because **the orders table has no rows** with `channel_code = 'affiliate'`. `GROUP BY` does not invent groups for values sitting in another lookup table.

### GROUP BY Sets Group Boundaries, FILTER Picks Rows Inside Each Group

Each channel has its own rows:

~~~text
web:       6 rows ---> paid = 3, paid_amount = 290
store:     5 rows ---> paid = 3, paid_amount = 440
partner:   5 rows ---> paid = 2, paid_amount = 330
~~~

`FILTER` does not merge channels into one group; it applies **within each group** created by `GROUP BY`.

### Combining Shared Filters and Per-Aggregate Filters

For example, analyzing only February orders:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS feb_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS feb_paid_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS feb_paid_amount
FROM filter_lab.sales_orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
GROUP BY channel_code
ORDER BY channel_code;
~~~

`WHERE` selects only February orders; each `FILTER` then selects matching statuses **within each channel's February group**.

## 8. Monthly Statistics with FILTER

When a dashboard wants one row per month:

~~~sql
WITH orders_by_month AS (
    SELECT
        date_trunc('month', order_date::timestamp)::date
            AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM orders_by_month
GROUP BY month_start
ORDER BY month_start;
~~~

Result:

| month_start | all_orders | paid_orders | cancelled_orders | paid_amount |
| --- | ---: | ---: | ---: | ---: |
| 2026-01-01 | 7 | 4 | 1 | 550.00 |
| 2026-02-01 | 9 | 4 | 2 | 510.00 |

Here `date_trunc('month', order_date::timestamp)::date` maps dates to the **first day of the month**. With a `date` column in the sample dataset, casting to `timestamp` is straightforward. When using `timestamptz`, month boundaries also depend on the **business time zone**, which must be defined clearly before grouping over time.

### Multiple Months on a Single Row

Sometimes a report requires fixed columns:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-01-01'
          AND order_date < DATE '2026-02-01'
    ) AS jan_paid_count,
    SUM(amount) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-01-01'
          AND order_date < DATE '2026-02-01'
    ) AS jan_paid_amount,
    COUNT(*) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-02-01'
          AND order_date < DATE '2026-03-01'
    ) AS feb_paid_count,
    SUM(amount) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-02-01'
          AND order_date < DATE '2026-03-01'
    ) AS feb_paid_amount
FROM filter_lab.sales_orders;
~~~

Results: `jan_paid_count = 4`, `jan_paid_amount = 550.00`, `feb_paid_count = 4`, `feb_paid_amount = 510.00`.

**The two report layouts serve different goals:** `GROUP BY month_start` naturally extends as new months arrive; fixed `jan_*` and `feb_*` columns work well when comparing **a small fixed set of periods**. Do not write hundreds of `FILTER` columns when a row-per-month table is a better fit.

## 9. COUNT(*) vs. COUNT(expression): Handling NULL Properly

These two expressions:

~~~sql
COUNT(*)
COUNT(amount)
~~~

do not always yield the same result. `COUNT(*)` counts rows; `COUNT(amount)` counts only non-`NULL` `amount` values.

In `sales_orders`, `amount` is `NOT NULL`, so they match on the sample table. To see the difference, use a test set:

~~~sql
WITH measurements(value) AS (
    VALUES
        (10::numeric),
        (NULL::numeric),
        (20::numeric)
)
SELECT
    COUNT(*) AS number_of_rows,
    COUNT(value) AS nonnull_values,
    SUM(value) AS value_sum,
    AVG(value) AS value_average
FROM measurements;
~~~

Result:

| number_of_rows | nonnull_values | value_sum | value_average |
| ---: | ---: | ---: | ---: |
| 3 | 2 | 30 | 15 |

Combined with FILTER:

~~~sql
WITH values_to_check(label, value) AS (
    VALUES
        ('accept', 10::numeric),
        ('accept', NULL::numeric),
        ('reject', 20::numeric)
)
SELECT
    COUNT(*) FILTER (
        WHERE label = 'accept'
    ) AS accept_rows,
    COUNT(value) FILTER (
        WHERE label = 'accept'
    ) AS accept_nonnull_values,
    SUM(value) FILTER (
        WHERE label = 'accept'
    ) AS accept_sum
FROM values_to_check;
~~~

Result: `accept_rows = 2`, `accept_nonnull_values = 1`, and `accept_sum = 10`.

### FILTER with NULL Conditions

The condition:

~~~sql
FILTER (WHERE value > 0)
~~~

excludes rows where `value = NULL`, because `NULL > 0` evaluates to **UNKNOWN**, not `TRUE`.

To count rows with null values:

~~~sql
COUNT(*) FILTER (WHERE value IS NULL)
~~~

To count rows with non-null values:

~~~sql
COUNT(*) FILTER (WHERE value IS NOT NULL)
~~~

`COUNT(value)` and `COUNT(*) FILTER (WHERE value IS NOT NULL)` match in **count** on the same row set, while expressing the check slightly differently.

## 10. COUNT vs. SUM When No Rows Match FILTER

This is a common pitfall when reporting on sparse channels, months, or groups.

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'unknown_status'
    ) AS count_unknown,
    SUM(amount) FILTER (
        WHERE status = 'unknown_status'
    ) AS sum_unknown,
    AVG(amount) FILTER (
        WHERE status = 'unknown_status'
    ) AS avg_unknown
FROM filter_lab.sales_orders;
~~~

Result:

~~~text
count_unknown = 0
sum_unknown   = NULL
avg_unknown   = NULL
~~~

**`COUNT` returns 0** when no rows match. However, **`SUM` and `AVG` return `NULL`** when there are no input values. That is standard aggregate semantics, not a `FILTER` bug.

If the report should show a total of 0 when no orders match:

~~~sql
SELECT
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'unknown_status'),
        0::numeric
    ) AS sum_unknown
FROM filter_lab.sales_orders;
~~~

Result: `0`.

### Don't Overuse COALESCE on Every Metric

For `SUM`, having no rows can reasonably be presented as 0 if business rules define "no revenue generated."

For `AVG`, a value of 0 usually **means something very different** from "no orders available to average." Replacing `NULL` with 0 can mislead readers into thinking the true average of existing orders was 0.

| Metric on Empty Filtered Set | PostgreSQL Value | Presentation Option to Consider |
| --- | --- | --- |
| `COUNT(*)` | 0 | 0 |
| `SUM(amount)` | `NULL` | `COALESCE(..., 0)` if appropriate |
| `AVG(amount)` | `NULL` | Usually keep `NULL` or display "N/A" |
| `MIN(amount)` / `MAX(amount)` | `NULL` | Usually "N/A" |
| `ARRAY_AGG(...)` | `NULL` | Can convert to an empty array |

## 11. LEFT JOIN: Including Channels Without Orders

When grouping directly on `sales_orders`, the `affiliate` channel disappeared because it had no rows. If the dashboard must show **all channels**, start from the lookup table:

~~~sql
SELECT
    c.channel_code,
    c.channel_name,
    COUNT(o.order_id) AS all_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code, c.channel_name
ORDER BY c.channel_code;
~~~

Result:

| channel_code | all_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| affiliate | 0 | 0 | 0 |
| partner | 5 | 2 | 330.00 |
| store | 5 | 3 | 440.00 |
| web | 6 | 3 | 290.00 |

### Why Use COUNT(o.order_id) Instead of COUNT(*)?

When `LEFT JOIN` finds no orders for `affiliate`, PostgreSQL still emits **one row on the left** with all `o` columns set to `NULL`.

If you write:

~~~sql
COUNT(*)
~~~

then the `affiliate` group receives **1**, because a joined row exists even though the order columns are null.

Meanwhile:

~~~sql
COUNT(o.order_id)
~~~

counts only matched rows where `order_id` is non-null, returning **0**.

This is an essential lesson: `FILTER` does not replace understanding `JOIN` **cardinality**. When summarizing child records across a `LEFT JOIN`, count a non-null key of the child entity.

### Placing the Condition in ON, WHERE, or FILTER?

Each placement has different semantics:

~~~sql
-- A. Keep all channels, join only paid orders.
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
   AND o.status = 'paid'
~~~

~~~sql
-- B. May drop channels without paid orders from the result:
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
WHERE o.status = 'paid'
~~~

~~~sql
-- C. Keep all joined orders for other metrics,
-- filter only the paid order count:
COUNT(o.order_id) FILTER (WHERE o.status = 'paid')
~~~

In case B, `WHERE o.status = 'paid'` eliminates left-side rows where `o` is null, effectively turning the `LEFT JOIN` into an inner join with respect to that condition.

The right placement depends on whether the report must **keep empty groups** and **report multiple statuses simultaneously**.

## 12. Computing Ratios with COUNT FILTER

A frequent KPI is the percentage of orders that are paid out of total orders.

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders;
~~~

Result:

~~~text
total_orders  = 16
paid_orders   = 8
paid_rate_pct = 50.00
~~~

### Two Reminders: Integer Division and Division by Zero

1. Write `100.0` or cast to `numeric` so the calculation preserves decimal precision; do not rely on integer-by-integer division.
2. Wrap the denominator in `NULLIF(denominator, 0)` to convert 0 into `NULL`, preventing division-by-zero errors.

When no rows exist, `COUNT(*) = 0`, so the rate becomes `NULL`. That is usually much better than forcing 0% when there is no sample data.

### Ratios per Channel

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Result:

| channel_code | total_orders | paid_orders | paid_rate_pct |
| --- | ---: | ---: | ---: |
| partner | 5 | 2 | 40.00 |
| store | 5 | 3 | 60.00 |
| web | 6 | 3 | 50.00 |

**Never compute the overall ratio by taking a simple average of group ratios** when group sizes differ. The overall ratio must use the **sum of numerators over the sum of denominators** (or an appropriately weighted average).

### Ratios When LEFT JOINing a Channel Without Orders

~~~sql
SELECT
    c.channel_code,
    COUNT(o.order_id) AS total_orders,
    ROUND(
        100.0
        * COUNT(o.order_id) FILTER (WHERE o.status = 'paid')
        / NULLIF(COUNT(o.order_id), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

The `affiliate` channel has `total_orders = 0` and `paid_rate_pct = NULL`—indicating **there are no orders to compute a rate from**, unlike having 100 orders with 0 paid (where the rate is 0%).

## 13. COUNT DISTINCT Combined with FILTER

A report may need **how many distinct customers** paid, rather than how many paid orders occurred.

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(DISTINCT customer_id) FILTER (
        WHERE status = 'paid'
    ) AS unique_paying_customers
FROM filter_lab.sales_orders;
~~~

Result:

~~~text
paid_orders             = 8
unique_paying_customers = 6
~~~

Because `customer_id = 1` has multiple paid orders, **the order count and unique customer count are not equal**.

### DISTINCT Applies After Selecting Rows

~~~sql
COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

can be read as:

1. Consider only rows with `status = 'paid'`.
2. Extract `customer_id` from those rows.
3. Deduplicate values and ignore `NULL` per `COUNT(DISTINCT ...)` semantics.
4. Count the distinct values remaining.

In this lesson's data, `customer_id` is `NOT NULL`, so nulls do not occur, though real tables may allow nullable customer IDs.

### DISTINCT Over Multiple Values

PostgreSQL can count distinct key tuples using a row expression; however, clarify whether "unique" means **one customer**, **one customer–channel pair**, or **one order**.

If a query has `JOIN`s that repeat each order across multiple rows, `COUNT(DISTINCT order_id) FILTER (...)` can prevent double-counting objects. However, that alone will not fix a `SUM(amount)` inflated by the join; inspect the relationships and grain of the input dataset.

## 14. FILTER vs. SUM(CASE WHEN ...)

Before `FILTER` existed, SQL authors commonly used `CASE`:

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'paid' THEN 1
            ELSE 0
        END
    ) AS paid_orders
FROM filter_lab.sales_orders;
~~~

On this non-empty dataset, the result is also **8**, matching:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders;
~~~

### Equivalent-Looking Expressions

| Form | Meaning |
| --- | --- |
| `COUNT(*) FILTER (WHERE p)` | Counts rows satisfying `p` |
| `COUNT(CASE WHEN p THEN 1 END)` | Counts non-null 1s when `p` is true |
| `SUM(CASE WHEN p THEN 1 ELSE 0 END)` | Adds 1 for matching rows, 0 otherwise |
| `SUM(value) FILTER (WHERE p)` | Sums non-null `value` for matching rows |
| `SUM(CASE WHEN p THEN value END)` | Sums `value` when `p` holds, ignoring nulls elsewhere |

These forms yield the same output in many queries, **but are not completely equivalent in all empty or null cases**.

### When No Rows Match

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'not_a_real_status')
        AS count_filter,
    COUNT(CASE WHEN status = 'not_a_real_status' THEN 1 END)
        AS count_case,
    SUM(CASE
            WHEN status = 'not_a_real_status' THEN 1
            ELSE 0
        END) AS sum_case_else_zero,
    SUM(CASE
            WHEN status = 'not_a_real_status' THEN 1
        END) AS sum_case_no_else
FROM filter_lab.sales_orders;
~~~

With 16 input rows:

~~~text
count_filter        = 0
count_case          = 0
sum_case_else_zero  = 0
sum_case_no_else    = NULL
~~~

Reason:

- `COUNT` returns 0 when no rows or values match.
- `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` receives sixteen 0s to add, returning 0.
- `SUM(CASE WHEN ... THEN 1 END)` sees only `NULL`s, returning `NULL`.

If the **entire input set is empty**, even `SUM(CASE ... ELSE 0 END)` returns `NULL`, because there are no rows to emit 0. That is why you should never adopt a `CASE` formula without checking empty-set behavior.

### When Is CASE Better Suited Than FILTER?

`CASE` is flexible when you need to **transform input values**, not merely exclude rows.

For example, a hypothetical status-based calculation:

~~~sql
SELECT
    SUM(
        CASE status
            WHEN 'paid' THEN amount
            WHEN 'refunded' THEN -amount
            ELSE 0
        END
    ) AS illustrative_balance
FROM filter_lab.sales_orders;
~~~

This is merely a **hypothetical formula illustrating CASE**, not a real accounting formula for net revenue. In production systems, you need accurate refund transaction records before deciding what to add or subtract.

If you only need "total value of paid orders," the following syntax is generally clearer:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
~~~

## 15. AVG FILTER Differs from AVG(CASE ... ELSE 0)

This is a subtle mistake that can corrupt a report while the SQL runs cleanly.

Compare:

~~~sql
SELECT
    AVG(amount) FILTER (
        WHERE status = 'paid'
    ) AS avg_paid_only,
    AVG(
        CASE
            WHEN status = 'paid' THEN amount
            ELSE 0
        END
    ) AS avg_over_all_orders,
    AVG(
        CASE
            WHEN status = 'paid' THEN amount
        END
    ) AS avg_case_without_else
FROM filter_lab.sales_orders;
~~~

Result:

| avg_paid_only | avg_over_all_orders | avg_case_without_else |
| ---: | ---: | ---: |
| 132.50 | 66.25 | 132.50 |

Explanation:

~~~text
8 paid orders, total amount = 1060
16 orders total

AVG FILTER                   = 1060 / 8  = 132.50
AVG CASE WHEN paid ELSE 0    = 1060 / 16 = 66.25
AVG CASE WHEN paid THEN ...  = 1060 / 8  = 132.50
~~~

**ELSE 0 is not wrong in every scenario.** If you actually want "average paid value per total order," a denominator of 16 is valid. However, it is **not** the average value of paid orders alone.

Metric column names should reflect their denominators clearly: `avg_paid_order_amount`, `paid_value_per_all_orders`, or equivalent.

## 16. FILTER with ARRAY_AGG and JSONB_AGG

Aggregations do not always return a single number. Sometimes a dashboard needs a list of order IDs or a JSON array.

### 16.1. Collecting Paid Order IDs per Channel

~~~sql
SELECT
    channel_code,
    ARRAY_AGG(
        order_id ORDER BY order_date, order_id
    ) FILTER (
        WHERE status = 'paid'
    ) AS paid_order_ids
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`FILTER` places only paid order IDs into the array. `ORDER BY` **sits inside the aggregate call** to control element order.

Do not rely on table scan order or the outermost `ORDER BY` to order elements inside `ARRAY_AGG`. `ORDER BY channel_code` sorts only the **grouped output rows**, not the elements inside each array.

### 16.2. Aggregating Data into JSON

~~~sql
SELECT
    channel_code,
    JSONB_AGG(
        JSONB_BUILD_OBJECT(
            'order_id', order_id,
            'amount', amount
        )
        ORDER BY order_date, order_id
    ) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders_json
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Each group contains a JSON array of paid order objects. Note that each element holds only the **selected fields**, not the entire table row.

### 16.3. Returning an Empty Array Instead of NULL

If a channel has no paid orders:

~~~sql
SELECT
    c.channel_code,
    COALESCE(
        ARRAY_AGG(
            o.order_id ORDER BY o.order_id
        ) FILTER (
            WHERE o.status = 'paid'
        ),
        ARRAY[]::bigint[]
    ) AS paid_order_ids
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

For `affiliate`, the output is an empty `bigint[]` array. Writing `ARRAY[]::bigint[]` avoids type-resolution errors because an empty array requires an explicit element type.

Similarly, you can use `COALESCE(JSONB_AGG(...) FILTER (...), '[]'::jsonb)` when an API expects an empty JSON array.

## 17. FILTER with DISTINCT or ORDER BY Inside an Aggregate

`FILTER` combines cleanly with aggregate options:

~~~sql
COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

~~~sql
ARRAY_AGG(order_id ORDER BY order_date DESC, order_id DESC)
    FILTER (WHERE status = 'paid')
~~~

In the first example, `DISTINCT` operates on the **values entering the aggregate after the filter**. In the second, the array includes only paid orders, sorted by the specified key.

### Ordered-Set Aggregates and FILTER

Statistical functions such as percentile/median use `WITHIN GROUP`:

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        FILTER (WHERE status = 'paid')
            AS median_paid_amount
FROM filter_lab.sales_orders;
~~~

Given paid amounts `80, 90, 110, 120, 130, 150, 180, 200`, the continuous median is **125**.

`PERCENTILE_CONT(0.5)` is an ordered-set aggregate; `FILTER` goes **after the entire `WITHIN GROUP (...)` clause**. Never place `FILTER` inside the `ORDER BY` of `WITHIN GROUP`.

Percentile behavior depends on the function and input type. This example casts `amount` to `double precision` to use continuous numeric interpolation.

## 18. FILTER and Boolean Aggregates

Some reports check whether "all" or "at least one" row meets a condition.

~~~sql
SELECT
    channel_code,
    BOOL_OR(status = 'cancelled') AS has_cancelled_order,
    BOOL_AND(amount >= 0) AS all_amount_nonnegative,
    BOOL_AND(status = 'paid') FILTER (
        WHERE status <> 'cancelled'
    ) AS all_noncancelled_orders_paid
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

With `BOOL_AND(status = 'paid') FILTER (WHERE status <> 'cancelled')`, the aggregate considers only **non-cancelled** orders, then checks whether **every remaining order** is paid. If any pending or refunded order remains, it returns false.

### Empty Filtered Sets

`BOOL_AND` and `BOOL_OR` are aggregate functions, so when no input values qualify they typically return `NULL` rather than true or false. If business rules treat "no violating orders" as true, express that rule explicitly, for example by checking whether the violating count equals 0:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) = 0 AS has_no_cancelled_orders
FROM filter_lab.sales_orders;
~~~

This returns a boolean per the **chosen rule**; it does not mean `BOOL_AND` and `COUNT` are universally interchangeable.

## 19. FILTER Inside HAVING: Selecting Groups by Conditional Metrics

`HAVING` filters groups after aggregation, and its aggregate expressions can use `FILTER`:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders
FROM filter_lab.sales_orders
GROUP BY channel_code
HAVING COUNT(*) FILTER (
    WHERE status = 'paid'
) >= 3
ORDER BY channel_code;
~~~

The result contains `store` and `web` because each has **3 paid orders**; `partner` has 2 paid orders and is excluded.

### WHERE and HAVING Are Not Equivalent

~~~sql
WHERE status = 'paid'
~~~

filters **rows before GROUP BY**. Then `COUNT(*)` becomes the count of paid orders, no longer all orders.

Meanwhile:

~~~sql
HAVING COUNT(*) FILTER (WHERE status = 'paid') >= 3
~~~

keeps all rows when computing group metrics, and only then **selects groups** with at least 3 paid orders.

An aggregate expression cannot be placed directly in a standard `WHERE` clause:

~~~sql
-- Invalid aggregate placement:
SELECT channel_code
FROM filter_lab.sales_orders
WHERE COUNT(*) FILTER (WHERE status = 'paid') >= 3
GROUP BY channel_code;
~~~

To filter on an aggregate result, use `HAVING` or wrap the aggregated query in a subquery/CTE.

## 20. FILTER with Window Aggregates and OVER

An aggregate can act as a **window function** by adding `OVER (...)`. It then avoids collapsing each group into a single row; instead, the summary value appears **alongside every order row**.

Example:

~~~sql
SELECT
    order_id,
    channel_code,
    status,
    amount,
    COUNT(*) OVER (
        PARTITION BY channel_code
    ) AS total_orders_in_channel,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY channel_code
    ) AS paid_orders_in_channel
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

Every `web` row will show:

~~~text
total_orders_in_channel = 6
paid_orders_in_channel  = 3
~~~

while every `store` row shows `5` and `3`; every `partner` row shows `5` and `2`.

**Distinguish the two patterns:**

- `GROUP BY channel_code` returns **one row per channel**.
- `COUNT(...) OVER (PARTITION BY channel_code)` keeps **every order row** and attaches channel metrics.

### FILTER Precedes OVER

Correct syntax:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Incorrect:

~~~sql
-- Syntax error:
COUNT(*) OVER (PARTITION BY channel_code)
    FILTER (WHERE status = 'paid')
~~~

### FILTER Does Not Apply to Every Window Function

~~~sql
-- Invalid because ROW_NUMBER is a window function,
-- not an aggregate window function:
ROW_NUMBER() FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

If you need sequence numbers for **only paid orders**, filter rows in a CTE first and then apply `ROW_NUMBER()`:

~~~sql
WITH paid_orders AS (
    SELECT *
    FROM filter_lab.sales_orders
    WHERE status = 'paid'
)
SELECT
    channel_code,
    order_id,
    ROW_NUMBER() OVER (
        PARTITION BY channel_code
        ORDER BY order_date, order_id
    ) AS paid_sequence
FROM paid_orders
ORDER BY channel_code, paid_sequence;
~~~

That is a different task from **counting total paid orders per partition**.

## 21. Conditional Running Totals with FILTER OVER

A window with `ORDER BY` and a frame computes a running total of paid orders over time.

~~~sql
SELECT
    channel_code,
    order_id,
    order_date,
    status,
    amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY channel_code
            ORDER BY order_date, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

How it works:

1. Partitions orders by `channel_code`.
2. For each row, the window covers rows **from the start of the channel up to the current row** ordered by `order_date, order_id`.
3. Only `status = 'paid'` rows inside the frame contribute `amount` to `SUM`.
4. Before any paid order occurs, `SUM` is null and `COALESCE` displays 0.

Example for the `web` channel over time:

| Date | status | amount | running_paid_amount |
| --- | --- | ---: | ---: |
| 2026-01-02 | paid | 120 | 120 |
| 2026-01-03 | paid | 80 | 200 |
| 2026-01-05 | pending | 50 | 200 |
| 2026-02-02 | paid | 90 | 290 |
| 2026-02-03 | cancelled | 0 | 290 |
| 2026-02-12 | refunded | 30 | 290 |

Pending, cancelled, and refunded orders still **appear in the output**, without increasing the paid running total.

### Why Specify ROWS Explicitly?

For window aggregates with `ORDER BY`, PostgreSQL's default frame rule can include **peer rows** (rows tied on the `ORDER BY` key). In this example we write:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

to make **row-by-row accumulation** explicit. Adding `order_id` as a tie-breaker keeps ordering deterministic when multiple orders fall on the same `order_date`.

### An Outer WHERE Still Filters the Window Input

If the same query includes:

~~~sql
WHERE status = 'paid'
~~~

then pending/refunded/cancelled rows are removed from the window's input and disappear from the running-total output. To **preserve all rows** while summing only paid orders, use `FILTER` inside the window aggregate as shown above.

## 22. FILTER with GROUPING SETS and Summary Rows

Sometimes you want channel breakdowns alongside a grand total row:

~~~sql
SELECT
    CASE
        WHEN GROUPING(channel_code) = 1 THEN 'ALL_CHANNELS'
        ELSE channel_code
    END AS channel_group,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders
GROUP BY GROUPING SETS (
    (channel_code),
    ()
)
ORDER BY GROUPING(channel_code), channel_group;
~~~

The result returns `partner`, `store`, `web`, and one `ALL_CHANNELS` row with 16 orders, 8 paid orders, and 1060.00 paid amount.

`GROUPING(channel_code)` distinguishes the total row from a genuine null channel value if the schema allows nulls. Avoid relying solely on `COALESCE(channel_code, 'ALL')` if you need to preserve a real null group's identity.

`GROUPING SETS`, `ROLLUP`, or `CUBE` define **which grouping levels are returned**; `FILTER` still controls which rows contribute to **a specific aggregate** at every level.

## 23. Conditional Statistics Across Multiple Dimensions

A dashboard wants metrics by **channel and month**:

~~~sql
WITH orders_by_month AS (
    SELECT
        channel_code,
        date_trunc('month', order_date::timestamp)::date
            AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    channel_code,
    month_start,
    COUNT(*) AS orders_count,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_count,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM orders_by_month
GROUP BY channel_code, month_start
ORDER BY channel_code, month_start;
~~~

This is a **multi-dimensional report** where each row corresponds to a `channel_code`–`month_start` pair.

If the dashboard prefers statuses as rows instead of columns:

~~~sql
SELECT
    channel_code,
    status,
    COUNT(*) AS n
FROM filter_lab.sales_orders
GROUP BY channel_code, status
ORDER BY channel_code, status;
~~~

This design works better when status values change frequently, because you do not need to edit the SQL whenever a new status label is introduced.

### Choosing GROUP BY status vs. FILTER per Status

| UI Requirement | Typically Suitable Approach |
| --- | --- |
| One row per channel with paid/pending/cancelled columns | `GROUP BY channel_code` with multiple `FILTER`s |
| One row per channel–status pair | `GROUP BY channel_code, status` |
| Statuses change dynamically without changing columns | `GROUP BY status`, pivot in the application if needed |
| Need overall totals and multiple subsets in the same row | Aggregates with distinct `FILTER` clauses |

`FILTER` is very convenient for **conditional aggregation**, though it does not replace choosing the right result shape.

## 24. Do Not Let a JOIN Double-Count Amounts

A mistake unrelated to `FILTER` syntax itself—yet very common in reporting—is a **one-to-many JOIN duplicating rows before aggregation**.

Suppose:

~~~text
sales_orders
  order_id = 101, amount = 200, status = 'paid'

order_items
  order_id = 101, item A
  order_id = 101, item B
  order_id = 101, item C
~~~

If you run:

~~~sql
SELECT
    SUM(o.amount) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_amount
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
~~~

then order 101 can appear **three times** after the join and get summed as `200 + 200 + 200 = 600`.

`FILTER` merely checks `o.status = 'paid'` on **each post-join row**; it does not know those three rows represent one business order.

### How to Handle It

When aggregating **order-level** amounts, aggregate at **one-row-per-order** grain:

~~~sql
SELECT
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders;
~~~

If you need a condition on line items, use `EXISTS` to select qualifying orders without multiplying rows:

~~~sql
-- Hypothetical example assuming an order_items table and sku column.
SELECT
    COUNT(*) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders_with_sku
FROM filter_lab.sales_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM filter_lab.order_items AS i
    WHERE i.order_id = o.order_id
      AND i.sku = 'SKU-001'
);
~~~

This is a **design example**, not runnable verbatim on the current lab since setup did not create `filter_lab.order_items`. It illustrates how `EXISTS` checks child existence without turning one order into multiple rows in the aggregate source.

With `COUNT(DISTINCT order_id)`, duplicate order counts can sometimes be avoided, whereas **`SUM(DISTINCT amount)` is not a general solution**: two distinct orders with the same amount will be wrongly collapsed if you apply DISTINCT to `amount`.

## 25. Is FILTER Faster Than CASE or Multiple Subqueries?

There is no absolute rule that `FILTER` is always faster than `CASE`. PostgreSQL can execute both efficiently, and performance depends on dataset size, predicates, indexes, group count, aggregate count, and the execution plan.

### Where FILTER Helps Readability and Structure

When you need 10 metrics from the same row set, a single query:

~~~sql
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
FROM filter_lab.sales_orders;
~~~

is typically **easier to read and maintain** than four independent subqueries. It also lets the planner compute all aggregates over a single shared source scan instead of forcing multiple scans of the same table.

### However, FILTER Does Not Automatically Become a Dedicated Index Scan

For example:

~~~sql
SELECT
    SUM(amount) FILTER (WHERE status = 'paid')
FROM filter_lab.sales_orders;
~~~

differs from:

~~~sql
SELECT SUM(amount)
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

In the second query, `WHERE` is a relation-level predicate, giving the planner an opportunity to choose access paths scanning only paid rows. In the first query, because the source stream may feed other aggregates too, do not assume a `FILTER` predicate will be **pushed down like an indexed WHERE clause**.

### Inspect EXPLAIN in Context

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

Compare against `WHERE` or `CASE` queries with **identical output semantics** on representative data. `EXPLAIN ANALYZE` executes the query; it is fine for read-only `SELECT` examples, but never run it casually on state-changing DML.

On very large production tables, check:

- Are there shared tenant, date, or region filters that belong in `WHERE` first?
- Do indexes or partition pruning shrink the source row set?
- Are `FILTER` predicates CPU-heavy per row?
- Is `GROUP BY` cardinality large enough to require heavy hash/sort memory?
- Does the report truly need real-time queries, or should it use summary tables or materialized views?

**Never optimize based on syntax assumptions without measuring the query plan and latency.**

## 26. Common Mistakes with FILTER

### Mistake 1. Using FILTER on a Non-Aggregate Function

Invalid:

~~~sql
-- Invalid:
SELECT
    ROW_NUMBER() FILTER (WHERE status = 'paid')
        OVER (PARTITION BY channel_code)
FROM filter_lab.sales_orders;
~~~

`FILTER` attaches to aggregates (including window aggregates). To number paid rows only, filter rows in a CTE first and then apply `ROW_NUMBER()` as shown earlier.

### Mistake 2. Putting FILTER After OVER

Correct:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Incorrect:

~~~sql
-- Invalid:
SUM(amount) OVER (PARTITION BY channel_code)
    FILTER (WHERE status = 'paid')
~~~

### Mistake 3. Thinking FILTER Removes Rows from SELECT

`COUNT(*) FILTER (WHERE status = 'paid')` does not remove pending rows from a `SELECT` using window aggregates, nor does it drop groups whose paid count is 0. To drop groups, use `HAVING`; to drop rows before aggregation, use `WHERE`.

### Mistake 4. Using COUNT(*) in a LEFT JOIN and Overcounting

For a group with no orders, `LEFT JOIN` still emits a row with nulls on the right side. Count `COUNT(o.order_id)` instead of `COUNT(*)` when you want the actual number of orders.

### Mistake 5. Expecting SUM to Return 0 on an Empty Filtered Set

`SUM(...) FILTER (...)` returns `NULL` when there are no matching values to sum. Use `COALESCE` when business logic wants 0, but consider keeping null for averages, minimums, and maximums.

### Mistake 6. Using AVG with ELSE 0 and Calling It the Paid Average

`AVG(CASE WHEN paid THEN amount ELSE 0 END)` divides by **all orders**, not just paid orders. Use `AVG(amount) FILTER (WHERE status = 'paid')` or a `CASE` without `ELSE 0` when you want the average of paid orders alone.

### Mistake 7. Division by Zero in Ratios

When a group has zero rows:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')
    / COUNT(*)
~~~

can fail with division by zero or truncate via integer division. Use decimal arithmetic and `NULLIF`, and agree on what "no sample" means.

### Mistake 8. Applying FILTER to Data Multiplied by a JOIN

If an order has three detail lines, `SUM(order.amount) FILTER (...)` after joining can add the order amount three times. Verify **granularity** before aggregating.

### Mistake 9. Using WHERE to Filter Out Statuses Needed by Other Metrics

Putting `WHERE status = 'paid'` and then computing `COUNT(*) FILTER (WHERE status = 'cancelled')` returns 0 for cancelled because those rows were filtered out beforehand.

### Mistake 10. Assuming FILTER Knows Business Definitions

Filtering `status = 'paid'` is not necessarily net revenue; paying customers do not automatically equal first-time buyers; paid order rate is not necessarily visit conversion rate. Define numerators, denominators, timestamps, and statuses explicitly.

## 27. Practice Exercises

Exercises use the 16 sample orders in `filter_lab.sales_orders` unless otherwise specified. Write your SQL first, then compare with the reference solutions.

### Exercise 1. Counting Statuses

Write a single `SELECT` returning four columns: total orders, paid, pending, and cancelled counts. Do not use subqueries.

### Exercise 2. Paid Order Totals and Averages

Compute `SUM(amount)`, `AVG(amount)`, `MIN(amount)`, and `MAX(amount)` for paid orders only. State the expected total and average on the sample dataset.

### Exercise 3. Channel Breakdown

Return one row per channel with orders, including `channel_code`, total orders, paid orders, refunded orders, and total paid amount. Use `GROUP BY` and multiple `FILTER`s.

### Exercise 4. Keeping Channels Without Orders

Write a `LEFT JOIN` from `channels` to `sales_orders` so the `affiliate` channel still appears. How do you ensure `affiliate`'s order count is 0 rather than 1?

### Exercise 5. Comparing Two AVG Formulas

Where do these two expressions:

~~~sql
AVG(amount) FILTER (WHERE status = 'paid')

AVG(CASE WHEN status = 'paid' THEN amount ELSE 0 END)
~~~

differ in their denominators? Predict both results on the 16 sample orders.

### Exercise 6. Paid Rate by Channel

Write SQL computing the paid order percentage per channel, rounded to two decimal places. What error must you avoid if a channel has zero orders?

### Exercise 7. Counting Paying Customers

How many **distinct customers** have at least one paid order? Write a `COUNT(DISTINCT ...) FILTER` expression.

### Exercise 8. Monthly Query

Return one row per month with total orders, paid orders, and paid amount. Why is `GROUP BY` by month preferable when months 3, 4, and beyond arrive?

### Exercise 9. HAVING with FILTER

Select channels with at least 3 paid orders. Keep `COUNT(*)` showing total orders across all statuses for each channel.

### Exercise 10. Distinguishing NULL and 0

If no orders have `status = 'unknown'`, what do `COUNT(*) FILTER (...)` and `SUM(amount) FILTER (...)` return? When should you use `COALESCE`?

### Exercise 11. Collecting Paid IDs into an Array

Write SQL returning an array of paid order IDs per channel, sorted by `order_date, order_id`. Why isn't `ORDER BY channel_code` at the end of the query enough?

### Exercise 12. Channel Window

Return each order alongside its channel's paid order count using `COUNT(*) FILTER (...) OVER (PARTITION BY ...)`. How does this differ from `GROUP BY` in output row count?

### Exercise 13. Paid Running Total

Compute the running total of `amount` for paid orders only, ordered by `order_date, order_id` within each channel. How do you keep pending/cancelled/refunded orders visible without adding their amounts?

### Exercise 14. CASE and FILTER

Rewrite `COUNT(*) FILTER (WHERE status='paid')` using `COUNT(CASE WHEN ... THEN 1 END)`. When can `SUM(CASE WHEN ... THEN 1 END)` return null?

### Exercise 15. One-to-Many JOIN

A `paid` order has `amount=200` and three `order_items` rows. After joining orders with items and running `SUM(o.amount) FILTER (WHERE o.status='paid')`, why might you get 600 instead of 200? Propose a proper fix.

### Exercise 16. FILTER on ROW_NUMBER

Can you write `ROW_NUMBER() FILTER (WHERE status='paid') OVER (...)`? If you want to number only paid orders within each channel, how would you structure the query?

### Exercise 17. Performance Evaluation

A 100-million-row table has an index on `(status, order_date)`. You need to count **only paid orders from last month**, with no other metrics. Should you favor `WHERE` or `FILTER` to restrict rows? What tool confirms your choice?

### Exercise 18. Median of Paid Orders

Write SQL computing the median `amount` for paid orders using `PERCENTILE_CONT(0.5) WITHIN GROUP ... FILTER`. What is the expected value?

## 28. Reference Solutions

### Solution 1. Counting Statuses

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

Result: `16, 8, 3, 3`.

### Solution 2. Paid Order Values

~~~sql
SELECT
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount,
    AVG(amount) FILTER (WHERE status = 'paid') AS avg_paid,
    MIN(amount) FILTER (WHERE status = 'paid') AS min_paid,
    MAX(amount) FILTER (WHERE status = 'paid') AS max_paid
FROM filter_lab.sales_orders;
~~~

Total `1060.00`, average `132.50`, min `80.00`, max `200.00`.

### Solution 3. By Channel

~~~sql
SELECT
    channel_code,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'refunded') AS refunded_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

### Solution 4. Keeping Groups Without Orders

~~~sql
SELECT
    c.channel_code,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

The `affiliate` channel gets `0` because `COUNT(o.order_id)` skips nulls on the child table side.

### Solution 5. Averages

`AVG(...) FILTER (...)` averages only the 8 paid orders, giving `132.50`. `AVG(CASE ... ELSE 0 END)` averages across all 16 orders, giving `66.25`.

### Solution 6. Ratios

~~~sql
SELECT
    channel_code,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`partner = 40.00`, `store = 60.00`, `web = 50.00`. With a `LEFT JOIN` to the channels table, replace the denominator with `COUNT(o.order_id)` and use `NULLIF` for zero-order groups.

### Solution 7. Distinct Customers

~~~sql
SELECT
    COUNT(DISTINCT customer_id) FILTER (
        WHERE status = 'paid'
    ) AS unique_paying_customers
FROM filter_lab.sales_orders;
~~~

Result: **6**.

### Solution 8. Monthly

~~~sql
WITH src AS (
    SELECT
        date_trunc('month', order_date::timestamp)::date AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    month_start,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM src
GROUP BY month_start
ORDER BY month_start;
~~~

`GROUP BY` lets new months appear automatically as data arrives without adding new `FILTER` columns for each month.

### Solution 9. Selecting Groups with Enough Paid Orders

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders
GROUP BY channel_code
HAVING COUNT(*) FILTER (WHERE status = 'paid') >= 3
ORDER BY channel_code;
~~~

Result: `store` and `web`.

### Solution 10. NULL and 0

`COUNT(*) FILTER (...) = 0`, whereas `SUM(amount) FILTER (...) = NULL` when no rows match. `COALESCE` is appropriate if business rules treat no activity as 0 total; do not blindly coerce an empty-sample average to 0.

### Solution 11. Ordered ARRAY_AGG

~~~sql
SELECT
    channel_code,
    ARRAY_AGG(order_id ORDER BY order_date, order_id)
        FILTER (WHERE status = 'paid') AS paid_order_ids
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`ORDER BY` inside `ARRAY_AGG` sorts **array elements**; the outer `ORDER BY` sorts only the channel rows.

### Solution 12. Window Aggregate

~~~sql
SELECT
    order_id,
    channel_code,
    status,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY channel_code
    ) AS channel_paid_orders
FROM filter_lab.sales_orders
ORDER BY channel_code, order_id;
~~~

Returns individual order rows instead of collapsing to one row per channel.

### Solution 13. Paid Running Total

~~~sql
SELECT
    channel_code,
    order_id,
    order_date,
    status,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY channel_code
            ORDER BY order_date, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

### Solution 14. Equivalent CASE for Counting

~~~sql
COUNT(CASE WHEN status = 'paid' THEN 1 END)
~~~

`SUM(CASE WHEN ... THEN 1 END)` returns `NULL` when all inputs evaluate to null or the input set is empty.

### Solution 15. JOIN Row Duplication

An order appears three times after the `JOIN`, so `amount` is summed three times. Pre-aggregate to order grain before joining, or use `EXISTS` if you only need to filter orders whose details satisfy a condition. Do not rely on `SUM(DISTINCT amount)` as a general fix.

### Solution 16. ROW_NUMBER

No. `ROW_NUMBER()` does not accept `FILTER`. Filter paid orders in a CTE/subquery first, then compute `ROW_NUMBER() OVER (PARTITION BY channel_code ORDER BY order_date, order_id)`.

### Solution 17. Optimization

If you only need last month's paid orders, `WHERE status = 'paid' AND order_date >= ... AND order_date < ...` lets the planner restrict rows at the relation level, potentially leveraging the index. Use `EXPLAIN (ANALYZE, BUFFERS)` and real measurements to compare; never draw conclusions from syntax alone.

### Solution 18. Median

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        FILTER (WHERE status = 'paid') AS median_paid
FROM filter_lab.sales_orders;
~~~

Result: **125**.

## 29. Quick Reference Cheatsheet

| Goal | Expression |
| --- | --- |
| Count all rows | `COUNT(*)` |
| Count rows matching a condition | `COUNT(*) FILTER (WHERE condition)` |
| Count non-null values matching a condition | `COUNT(column) FILTER (WHERE condition)` |
| Conditional sum | `SUM(value) FILTER (WHERE condition)` |
| Conditional average | `AVG(value) FILTER (WHERE condition)` |
| Conditional minimum/maximum | `MIN(value) FILTER (...)` / `MAX(value) FILTER (...)` |
| Conditional distinct count | `COUNT(DISTINCT value) FILTER (...)` |
| Conditional ordered array | `ARRAY_AGG(value ORDER BY key) FILTER (...)` |
| Conditional JSON array | `JSONB_AGG(value ORDER BY key) FILTER (...)` |
| Conditional percentage | `100.0 * COUNT(*) FILTER (...) / NULLIF(COUNT(*), 0)` |
| Filter groups by conditional count | `HAVING COUNT(*) FILTER (...) >= n` |
| Conditional window aggregate | `SUM(value) FILTER (...) OVER (PARTITION BY key)` |
| Conditional running total | `SUM(value) FILTER (...) OVER (ORDER BY key ROWS ...)` |
| Replace NULL SUM with 0 | `COALESCE(SUM(value) FILTER (...), 0)` |

## 30. Summary

`FILTER (WHERE ...)` is a direct, readable tool for **conditional statistics in PostgreSQL**. It allows multiple aggregates to scan a shared data source while each computes over only the rows matching its own condition—such as paid order count, cancelled order count, paid order value, and paid rate out of all orders.

Key principles:

1. **`WHERE` and `FILTER` differ in scope.** `WHERE` excludes rows from the overall input; `FILTER` selects rows for a single aggregate.
2. **`COUNT` differs from `SUM`/`AVG` on empty filtered sets.** `COUNT` returns 0, whereas most other aggregates return `NULL`; apply `COALESCE` intentionally.
3. **The denominator determines statistical meaning.** `AVG(amount) FILTER (WHERE paid)` differs from `AVG(CASE WHEN paid THEN amount ELSE 0 END)`.
4. **`GROUP BY`, `HAVING`, and `OVER` keep their own scopes.** `FILTER` works with grouped aggregates or window aggregates, though not with non-aggregate window functions.
5. **Input data quality still governs results.** `FILTER` does not fix `JOIN`-induced row duplication, define accounting revenue for you, or guarantee superior speed over `CASE` or `WHERE`.

When building reports, determine **the unit being counted/summed**, **each metric's condition**, **the denominator**, **NULL interpretation**, and **the grouping level** before writing SQL. Then use `FILTER` to express those definitions in a clear query that is easy to verify and extend as reporting needs grow.
