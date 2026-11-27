# DISTINCT, DISTINCT ON, and Representative Row Selection in PostgreSQL

When querying relational data, results often contain multiple rows sharing values in **some columns** while still being distinct records. For example, a customer places multiple orders, a product appears in multiple orders, or an account logs in multiple times. Common goals include:

- Retrieving a **list of distinct values**, such as distinct order statuses that have occurred.
- Retrieving **unique value combinations**, such as city–status pairs.
- Picking **exactly one representative row per group**, such as each customer's latest order.
- Removing duplicate rows introduced by a `JOIN` without accidentally dropping needed information.

PostgreSQL supports both standard SQL **`DISTINCT`** and PostgreSQL's own **`DISTINCT ON (...)`** extension. Their names look similar, yet they solve two different problems:

> **`DISTINCT` deduplicates across the entire list of selected expressions; `DISTINCT ON` keeps one representative row for each value or tuple of values listed in parentheses.**

The key to `DISTINCT ON` is **defining what makes a row "best" via `ORDER BY`**. Asking for "one row per customer" without specifying "newest", "highest value", or another rule gives PostgreSQL no basis for deciding which row to keep.

This lesson builds a sample dataset and walks step by step through `DISTINCT`, `DISTINCT ON`, `ROW_NUMBER()`, `GROUP BY`, `NULL` handling, `JOIN` scenarios, and index/performance implications.

## 1. Distinguishing Duplicate Rows from Duplicate Values

Consider an orders table:

| order_id | customer_id | status | total |
| ---: | ---: | --- | ---: |
| 1001 | 1 | paid | 120.00 |
| 1002 | 1 | pending | 80.00 |
| 1003 | 1 | paid | 150.00 |
| 1004 | 2 | paid | 200.00 |

Here:

- There are **four distinct orders** because `order_id` differs.
- There are **two distinct customers** because `customer_id` is only 1 and 2.
- There are **two distinct statuses**: `paid` and `pending`.
- There are **three distinct customer_id–status pairs**: (1, paid), (1, pending), (2, paid).

Therefore, "deduplicating" always requires answering: **duplicate across which columns?**

~~~mermaid
flowchart TD
    A["A query returns multiple rows"] --> B{"What is the real goal?"}
    B -->|"Unique values or combinations"| C["SELECT DISTINCT"]
    B -->|"One full-detail row per group"| D["DISTINCT ON + ORDER BY"]
    B -->|"Top N or rank per group"| E["ROW_NUMBER / RANK"]
    B -->|"Counts, sums, MAX, MIN per group"| F["GROUP BY + aggregate"]
    B -->|"Unexpected duplicate rows after JOIN"| G["Review keys and JOIN conditions"]
~~~

**`DISTINCT` cannot tell bad duplicate data apart from multiple valid records.** Two orders from the same customer are completely valid distinct orders; selecting only `DISTINCT customer_id` discards order details if you actually need a per-order report.

## 2. Preparing Reproducible Practice Data

To keep outputs predictable, use a **dedicated lab database**, such as `pg_distinct_lab`. Warning: the script below drops the `distinct_lab` schema if it already exists. **Run it only when you are sure you are in a practice database and that schema holds no data worth keeping.**

### Creating the Schema and Tables

~~~sql
-- RUN ONLY IN A PRACTICE DATABASE.
DROP SCHEMA IF EXISTS distinct_lab CASCADE;
CREATE SCHEMA distinct_lab;

CREATE TABLE distinct_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE distinct_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES distinct_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL
        CHECK (total >= 0)
);

CREATE TABLE distinct_lab.order_tags (
    order_id integer NOT NULL
        REFERENCES distinct_lab.orders(order_id),
    tag text NOT NULL,
    PRIMARY KEY (order_id, tag)
);
~~~

Table roles:

- `customers`: each customer has a unique ID, city, and name.
- `orders`: a customer can have many orders; `order_id` is unique.
- `order_tags`: an order can have many tags, used to illustrate how `JOIN` increases row counts.

### Loading Sample Data

~~~sql
INSERT INTO distinct_lab.customers
    (customer_id, full_name, city)
VALUES
    (1, 'An',   'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi',  'HCM'),
    (4, 'Dung', 'DNG');

INSERT INTO distinct_lab.orders
    (order_id, customer_id, ordered_at, status, total)
VALUES
    (1001, 1, '2026-11-03 09:00:00+00', 'paid',      120.00),
    (1002, 1, '2026-11-06 10:00:00+00', 'pending',    80.00),
    (1003, 1, '2026-11-06 10:00:00+00', 'paid',      150.00),
    (1004, 2, '2026-11-01 08:00:00+00', 'paid',      200.00),
    (1005, 2, '2026-11-04 08:00:00+00', 'cancelled', 300.00),
    (1006, 3, '2026-11-02 12:00:00+00', 'paid',       50.00),
    (1007, 3, '2026-11-07 18:00:00+00', 'paid',       75.00);

INSERT INTO distinct_lab.order_tags (order_id, tag)
VALUES
    (1001, 'gift'),
    (1001, 'web'),
    (1002, 'app'),
    (1003, 'web'),
    (1004, 'web'),
    (1005, 'app'),
    (1006, 'gift'),
    (1007, 'web');
~~~

Intentional scenarios built into the data:

1. An (ID 1) has **three orders**.
2. Orders **1002 and 1003 share the exact same timestamp**. Picking An's newest order requires a tie-breaker rule.
3. Binh (ID 2) has two orders; the newest one has status `cancelled`.
4. Chi (ID 3) has two orders, with 1007 being newest.
5. Dung (ID 4) **has no orders yet**.
6. Order 1001 has **two tags**, producing two rows when joined with `order_tags`.

All timestamps use offset `+00`. You can set the session time zone for consistent timestamp display:

~~~sql
SET TIME ZONE 'UTC';
~~~

To inspect the data:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    status,
    total
FROM distinct_lab.orders
ORDER BY order_id;
~~~

This dataset forms the basis for all subsequent examples. No further updates or deletes are needed to practice `DISTINCT`.

## 3. SELECT DISTINCT: Deduplicating Across Selected Expressions

Basic syntax:

~~~sql
SELECT DISTINCT expression_1, expression_2, ...
FROM some_table;
~~~

PostgreSQL produces a result set where **no two rows match across all selected expressions**.

### Example 1: List of Cities

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city;
~~~

Result:

| city |
| --- |
| DNG |
| HAN |
| HCM |

Customers An and Chi both live in HCM, so `HCM` appears only once.

### Example 2: List of Order Statuses

~~~sql
SELECT DISTINCT status
FROM distinct_lab.orders
ORDER BY status;
~~~

Result:

| status |
| --- |
| cancelled |
| paid |
| pending |

Even though `paid` appears multiple times, `DISTINCT` returns a single `paid` value.

### Example 3: DISTINCT Over Two Columns

~~~sql
SELECT DISTINCT
    customer_id,
    status
FROM distinct_lab.orders
ORDER BY customer_id, status;
~~~

Result:

| customer_id | status |
| ---: | --- |
| 1 | paid |
| 1 | pending |
| 2 | cancelled |
| 2 | paid |
| 3 | paid |

For `customer_id = 1`, two `paid` orders collapse into **one `(1, paid)` pair**, while `(1, pending)` remains separate. Customer 2 has two distinct statuses, yielding two rows.

**`DISTINCT` applies to the entire expression list, not just the first column.** This query:

~~~sql
SELECT DISTINCT customer_id, order_id
FROM distinct_lab.orders;
~~~

still returns **seven rows**, because `order_id` is the primary key and every `(customer_id, order_id)` pair is unique.

## 4. DISTINCT Differs from Schema-Level UNIQUE

These two concepts are easy to conflate, yet they operate at different layers:

- **`SELECT DISTINCT`:** transforms the result set **of a single query** by removing duplicate rows.
- **`UNIQUE` constraint / unique index:** prevents invalid duplicate data **from being stored in the table** according to defined rules.

Example:

~~~sql
CREATE TABLE distinct_lab.accounts (
    account_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

`UNIQUE(email)` protects data at write time. It does not mean multi-table queries will never need `DISTINCT`, nor can `SELECT DISTINCT email` clean up existing duplicate records in an unconstrained table.

A query:

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders;
~~~

only returns the list of customers who have placed orders. It **does not delete any orders from the table**.

If a table has duplicate business records that need cleanup, run an audited inspection, controlled merge/delete workflow, and add constraints to prevent recurrence. Never treat `DISTINCT` as a "root-cause data fix."

## 5. COUNT(DISTINCT ...): Counting Distinct Values

Like `SELECT DISTINCT`, the `COUNT` aggregate function supports `DISTINCT`:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(DISTINCT customer_id) AS customers_with_orders,
    COUNT(DISTINCT status) AS distinct_statuses
FROM distinct_lab.orders;
~~~

Result:

| total_orders | customers_with_orders | distinct_statuses |
| ---: | ---: | ---: |
| 7 | 3 | 3 |

Here:

- `COUNT(*)` counts all orders.
- `COUNT(DISTINCT customer_id)` counts distinct customers who have orders (1, 2, 3).
- `COUNT(DISTINCT status)` counts distinct statuses present.

### Is NULL Counted in COUNT(DISTINCT ...)?

For a **single expression**, `COUNT(DISTINCT expression)` ignores SQL `NULL` values. Meanwhile, `SELECT DISTINCT expression` returns **one `NULL` row** if the input has one or more `NULL`s.

Self-contained example:

~~~sql
WITH sample(value) AS (
    VALUES
        (1),
        (1),
        (2),
        (NULL::integer),
        (NULL::integer)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(DISTINCT value) AS distinct_nonnull
FROM sample;
~~~

Results: `all_rows = 5`, `distinct_nonnull = 2`.

Whereas:

~~~sql
WITH sample(value) AS (
    VALUES
        (1),
        (1),
        (2),
        (NULL::integer),
        (NULL::integer)
)
SELECT DISTINCT value
FROM sample
ORDER BY value NULLS LAST;
~~~

returns three rows: `1`, `2`, and one `NULL` row.

This is a critical rule when aggregating nullable data; **never assume the row count of `SELECT DISTINCT nullable_column` always equals `COUNT(DISTINCT nullable_column)`**.

## 6. DISTINCT and ORDER BY: Two Separate Responsibilities

`DISTINCT` determines **which rows are treated as duplicates**. `ORDER BY` determines **the order of the final returned rows**.

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city DESC;
~~~

The result still has three cities, ordered `HCM`, `HAN`, `DNG`.

Without `ORDER BY`, SQL **does not guarantee row order**, even if the execution plan happens to sort internally to deduplicate.

### ORDER BY Restrictions with SELECT DISTINCT

In PostgreSQL, when using `SELECT DISTINCT`, `ORDER BY` expressions must appear in the `SELECT` output list.

This query is invalid:

~~~sql
-- Intentionally invalid example:
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY full_name;
~~~

The business reason is clear: city `HCM` has multiple people, so if only one `HCM` row is returned, whose `full_name` would decide its sort position?

A valid query:

~~~sql
SELECT DISTINCT city, full_name
FROM distinct_lab.customers
ORDER BY full_name;
~~~

However, this changes the **deduplication key**: each city–name pair becomes a distinct row. If you want strictly one row per city sorted by a **representative person's** name, define a representative selection rule using `DISTINCT ON` or aggregation.

## 7. DISTINCT ON: Keeping One Representative Row per Group

`DISTINCT ON` is a PostgreSQL-specific extension:

~~~sql
SELECT DISTINCT ON (group_expression_1, ...)
    column_1, column_2, ...
FROM some_table
ORDER BY
    group_expression_1, ...,
    preferred_order_expression, ...;
~~~

It keeps the **first row of each group** sharing the same `DISTINCT ON (...)` values, in the order determined by PostgreSQL after sorting.

On our orders dataset, a common requirement is:

> "Fetch one order per customer, preferring the newest order. If two orders share the same timestamp, pick the one with the larger ID."

We write:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status,
    total
FROM distinct_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
~~~

Result:

| customer_id | order_id | ordered_at (UTC) | status | total |
| ---: | ---: | --- | --- | ---: |
| 1 | 1003 | 2026-11-06 10:00:00+00 | paid | 150.00 |
| 2 | 1005 | 2026-11-04 08:00:00+00 | cancelled | 300.00 |
| 3 | 1007 | 2026-11-07 18:00:00+00 | paid | 75.00 |

Walkthrough:

1. `DISTINCT ON (customer_id)` partitions rows by customer.
2. `ORDER BY customer_id` groups rows for each customer together, satisfying `DISTINCT ON` syntax rules.
3. `ordered_at DESC` places newer orders first within each group.
4. `order_id DESC` breaks ties when timestamps match. For An, orders 1002 and 1003 share `ordered_at`, and **1003 wins**.
5. PostgreSQL retains the first row of each group in that sort order.

**`DISTINCT ON` does not inherently understand "newest."** Selecting the newest row comes entirely from the `ORDER BY` you specify.

## 8. Why ORDER BY Governs the Correctness of DISTINCT ON

Writing only:

~~~sql
-- No deterministic rule for picking a representative row:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, status
FROM distinct_lab.orders;
~~~

is accepted by PostgreSQL, yet **does not specify which row per customer is kept**. The choice is not guaranteed to follow timestamp, `order_id`, or insertion order.

It does not mean "pick the first row ever inserted"; relational tables have no guaranteed physical order. Execution plans, indexes, statistics, `VACUUM`, or version upgrades can pick a different representative row.

### Missing a Tie-Breaker Can Also Be Unstable

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC;
~~~

For An, orders 1002 and 1003 share the exact same timestamp. `ordered_at DESC` alone **does not specify whether 1002 or 1003 must be picked**.

When reproducible results matter, append a final expression that breaks ties uniquely:

~~~sql
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
~~~

Here `order_id` is the primary key, so together with customer and timestamp, the sort order always selects a deterministic row.

### What If You Need the Oldest Order?

Flip the priority sort direction:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    ordered_at ASC,
    order_id ASC;
~~~

Result:

| customer_id | oldest order_id |
| ---: | ---: |
| 1 | 1001 |
| 2 | 1004 |
| 3 | 1006 |

Changing `ORDER BY` changes what "representative row" means, even while the `customer_id` grouping stays identical.

## 9. The Leftmost ORDER BY Rule of DISTINCT ON

PostgreSQL requires the expressions in `DISTINCT ON (...)` to **match the leftmost expressions of `ORDER BY`**. Additional sort keys follow afterwards to pick the preferred row within each group.

Valid:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Invalid:

~~~sql
-- Intentionally invalid because ORDER BY does not start
-- with the grouping expression customer_id:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY ordered_at DESC, customer_id;
~~~

Typical error:

~~~text
SELECT DISTINCT ON expressions must match initial ORDER BY expressions
~~~

With multiple grouping columns:

~~~sql
SELECT DISTINCT ON (customer_id, status)
    customer_id,
    status,
    order_id,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    status,
    ordered_at DESC,
    order_id DESC;
~~~

This picks **one newest order per customer–status pair**, not one per customer. For example, An has both `paid` and `pending` groups, yielding **two rows**.

Rule of thumb: **grouping keys first, priority keys after**.

## 10. DISTINCT ON One Column Does Not Limit You to Selecting One Column

Unlike `DISTINCT`, `DISTINCT ON (customer_id)` does not use all `SELECT` columns to define group identity.

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    total
FROM distinct_lab.orders
ORDER BY customer_id, total DESC, order_id DESC;
~~~

It picks the **order with the largest `total`** per customer, even though orders have different `status` and `order_id` values.

Result on the sample data:

| customer_id | order_id | status | total |
| ---: | ---: | --- | ---: |
| 1 | 1003 | paid | 150.00 |
| 2 | 1005 | cancelled | 300.00 |
| 3 | 1007 | paid | 75.00 |

Notice Binh has a cancelled order with the highest amount of 300.00. **If business logic only wants paid orders**, filter status before picking the representative rather than just sorting by `total`.

### Filter First, Then Pick the Representative Row

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    total
FROM distinct_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Result:

| customer_id | newest paid order_id |
| ---: | ---: |
| 1 | 1003 |
| 2 | 1004 |
| 3 | 1007 |

Binh gets order 1004 because the newer order 1005 is `cancelled` and **was filtered out before `DISTINCT ON` ran**.

Compare two requirements:

- **"Each customer's newest order, shown only if it is paid"**: first pick the newest order of any status, then filter the representative rows. Binh **does not appear** because his newest order is cancelled.
- **"Each customer's newest paid order"**: filter `paid` first, then pick the newest. Binh **appears** with order 1004.

These two queries mean very different things even though both mention "newest" and "paid."

## 11. Filtering After Selecting Representatives with a Subquery

To pick the newest order regardless of status, and then keep only representatives whose status is `paid`:

~~~sql
SELECT
    latest.customer_id,
    latest.order_id,
    latest.status,
    latest.ordered_at
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        status,
        ordered_at
    FROM distinct_lab.orders
    ORDER BY
        customer_id,
        ordered_at DESC,
        order_id DESC
) AS latest
WHERE latest.status = 'paid'
ORDER BY latest.customer_id;
~~~

The result includes An (1003) and Chi (1007); **Binh is excluded** because his representative (1005) has status cancelled.

This differs from placing `WHERE status = 'paid'` **inside** the `DISTINCT ON` query. When writing SQL, ensure the logical order of filtering and representative selection matches the business question.

## 12. SELECT DISTINCT ON and Final Display Order

Because `ORDER BY` must begin with the grouping expressions, the direct output of `DISTINCT ON (customer_id)` comes out ordered by `customer_id`, not globally by newest timestamp.

Suppose you want "each customer's newest order, displayed globally from newest order timestamp to oldest." Wrap it in an outer query:

~~~sql
SELECT
    recent.customer_id,
    recent.order_id,
    recent.ordered_at,
    recent.status
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        ordered_at,
        status
    FROM distinct_lab.orders
    ORDER BY
        customer_id,
        ordered_at DESC,
        order_id DESC
) AS recent
ORDER BY
    recent.ordered_at DESC,
    recent.order_id DESC;
~~~

Expected order is Chi (1007), An (1003), Binh (1005) per our seeded timestamps.

**Two distinct orderings:**

1. **Inner `ORDER BY`**: selects each group's representative row.
2. **Outer `ORDER BY`**: presents those representative rows in the order users want to view.

If pagination is needed:

~~~sql
SELECT *
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        ordered_at
    FROM distinct_lab.orders
    ORDER BY customer_id, ordered_at DESC, order_id DESC
) AS recent
ORDER BY ordered_at DESC, order_id DESC
LIMIT 2;
~~~

`LIMIT 2` applies **after** selecting one row per customer and sorting in the outer query—not taking any two orders first and deduplicating afterward.

## 13. DISTINCT ON with LEFT JOIN: Preserving Groups Without Child Records

Starting from `orders` omits customer Dung because she has no orders. Yet a requirement may ask:

> "Show all customers, along with their newest order if any."

Start with `customers` and use `LEFT JOIN`:

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at,
    o.status
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

Result:

| customer_id | full_name | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 1003 | paid |
| 2 | Binh | 1005 | cancelled |
| 3 | Chi | 1007 | paid |
| 4 | Dung | NULL | NULL |

`LEFT JOIN` produces one row with `NULL` in `orders` columns for Dung. Because group `customer_id = 4` still has one row, `DISTINCT ON` preserves that representative.

### Why Add NULLS LAST?

In PostgreSQL, when sorting `DESC`, `NULL` values sort **first** by default if unspecified. If `ordered_at` were nullable in a real orders table, `ORDER BY ordered_at DESC` could accidentally pick an order missing a timestamp ahead of valid orders.

Write:

~~~sql
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

to state "prefer newest known timestamp, push missing values to the bottom."

In our example schema, `orders.ordered_at` is `NOT NULL`; Dung's `NULL` comes from the **outer join**, not an order with a missing timestamp.

### Filtering Paid Orders While Keeping Customers Without Paid Orders

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

Binh gets 1004; Dung still gets a `NULL` row. Putting `o.status = 'paid'` in `WHERE` instead of `ON` would eliminate customers without paid orders, defeating the `LEFT JOIN`.

## 14. DISTINCT ON with NULL in the Grouping Key

`DISTINCT ON` groups rows sharing the same expression value. For deduplication purposes, SQL `NULL` values in the grouping expression belong to **the same group**.

Example:

~~~sql
WITH sample(customer_id, note, created_at) AS (
    VALUES
        (1, 'A', timestamp '2026-11-01 10:00'),
        (1, 'B', timestamp '2026-11-02 10:00'),
        (NULL::integer, 'Unassigned A', timestamp '2026-11-01 10:00'),
        (NULL::integer, 'Unassigned B', timestamp '2026-11-03 10:00')
)
SELECT DISTINCT ON (customer_id)
    customer_id, note, created_at
FROM sample
ORDER BY customer_id NULLS LAST, created_at DESC, note;
~~~

The result has two rows:

| customer_id | note |
| --- | --- |
| 1 | B |
| NULL | Unassigned B |

Both rows with `customer_id IS NULL` are treated as one group for `DISTINCT ON (customer_id)`; the one with the newer timestamp is retained.

Do not confuse deduplication's NULL grouping rule with `WHERE` comparisons: `customer_id = NULL` is **not** how you match NULL in `WHERE`; use `IS NULL`.

## 15. Picking Representatives Using Multiple Priority Rules

The "representative" does not have to be the newest row. Rules might include:

- Prefer `paid` orders first, then newest order.
- Prefer the record with the highest amount, then smallest ID.
- Prefer the default address, then most recently updated.
- Prefer rows with complete fields, then newer rows.

### Example: Prefer Paid Status First, Then Newest Timestamp

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    (status = 'paid') DESC,
    ordered_at DESC,
    order_id DESC;
~~~

The boolean expression `status = 'paid'` is either `true` or `false` since `status` is non-NULL. PostgreSQL sorts `true` after `false` in ascending order, so `DESC` puts `true` first within each group.

On the dataset:

- An: picks 1003 because it is `paid` and newer than paid order 1001.
- Binh: picks 1004 (`paid`) **even though** 1005 (`cancelled`) is newer.
- Chi: picks 1007.

That captures "prefer paid", **not** "pick the newest order regardless of status."

### Example: Prefer Highest Amount While Keeping a Tie-Breaker

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    total
FROM distinct_lab.orders
ORDER BY
    customer_id,
    total DESC,
    order_id DESC;
~~~

If two orders tie on `total`, the one with the larger ID wins. Including `order_id` makes the rule explicit rather than depending on physical storage or plan order.

### Example: Prioritizing with a CASE Expression

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    CASE status
        WHEN 'paid' THEN 1
        WHEN 'pending' THEN 2
        ELSE 3
    END,
    ordered_at DESC,
    order_id DESC;
~~~

`CASE` expresses custom business rankings that cannot be represented simply by `ASC`/`DESC` on a single column.

## 16. DISTINCT ON vs. GROUP BY and MAX()

A very common mistake when trying to "get the newest order" is writing:

~~~sql
SELECT
    customer_id,
    MAX(ordered_at) AS latest_time
FROM distinct_lab.orders
GROUP BY customer_id;
~~~

This SQL is **valid**, yet returns only **the newest timestamp**, not the full order row. To also retrieve `order_id`, `status`, or `total`, you need a row-selection strategy.

### You Cannot Arbitrarily SELECT Ungrouped Columns Outside GROUP BY

This query is invalid under standard grouping rules because `order_id` is neither aggregated nor functionally determined by the grouping key:

~~~sql
-- Intentionally invalid example:
SELECT
    customer_id,
    order_id,
    MAX(ordered_at)
FROM distinct_lab.orders
GROUP BY customer_id;
~~~

PostgreSQL cannot guess which `order_id` to show when a customer has multiple orders.

### Joining Back to MAX Can Return Multiple Rows

A common technique:

~~~sql
WITH latest_times AS (
    SELECT
        customer_id,
        MAX(ordered_at) AS latest_time
    FROM distinct_lab.orders
    GROUP BY customer_id
)
SELECT o.customer_id, o.order_id, o.ordered_at
FROM distinct_lab.orders AS o
JOIN latest_times AS lt
    ON lt.customer_id = o.customer_id
   AND lt.latest_time = o.ordered_at
ORDER BY o.customer_id, o.order_id;
~~~

For customer An, orders 1002 and 1003 **share the exact newest timestamp**, so this returns **both**. If the requirement calls for "a single row", joining back to `MAX` lacks a tie-breaker.

`DISTINCT ON` offers concise syntax:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at, status
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Conversely, if business rules want **all tied first-place rows**, joining with `MAX` or using a window function like `RANK()` fits better than `DISTINCT ON`.

## 17. DISTINCT ON vs. ROW_NUMBER()

`ROW_NUMBER()` is a *window function* that assigns sequential integers within each partition defined by `PARTITION BY` and `ORDER BY`.

The equivalent query for "each customer's newest order, breaking ties by largest ID":

~~~sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM distinct_lab.orders AS o
)
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    total
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

Result matches `DISTINCT ON`: orders 1003, 1005, and 1007.

### Why Is a CTE or Subquery Needed?

Window functions are evaluated at a query stage where they cannot be used directly in the same `SELECT`'s `WHERE` clause. Therefore:

~~~sql
-- Intentionally invalid example:
SELECT *
FROM distinct_lab.orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC
) = 1;
~~~

is invalid. You must compute `ROW_NUMBER()` in an inner query and filter `rn = 1` in the outer query.

### When to Use ROW_NUMBER Instead of DISTINCT ON?

- You need the **top 2, top 3, or top N** rows per group (`WHERE rn <= N`).
- You want to keep the rank column to explain results.
- You want SQL that is more portable across DBMSs supporting window functions.
- You want to combine multiple rankings in one query.

Example fetching the **two newest orders per customer**:

~~~sql
WITH ranked_orders AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

`DISTINCT ON` keeps only one representative row per group; you cannot use it directly to fetch two rows per group.

### RANK and DENSE_RANK Keep Tied Rows

If the requirement is "fetch **all orders sharing the newest timestamp** for each customer", use `RANK()`:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC
        ) AS time_rank
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked
WHERE time_rank = 1
ORDER BY customer_id, order_id;
~~~

For An, this returns both **1002 and 1003** because both tie for the newest `ordered_at`. Adding `order_id DESC` inside `RANK()`'s `ORDER BY` breaks the tie across the full criteria, so align the rank keys with the exact question.

## 18. DISTINCT ON and LATERAL: Picking the Latest Row per Parent

When you already have a list of customers and want the single latest order for **each customer**, another option is `LEFT JOIN LATERAL`:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.ordered_at,
    recent.status
FROM distinct_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at,
        o.status
    FROM distinct_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
~~~

The result includes all four customers, with `NULL` order columns for Dung.

`LATERAL` lets the inner query reference `c.customer_id` from the current customer row. With a suitable index, PostgreSQL can look up the latest order for **each** customer efficiently—especially when the outer customer set is small relative to a huge orders table.

However, it is not automatically faster than `DISTINCT ON`:

- When selecting nearly all customers, many index lookups may perform worse than one sequential scan/sort pass.
- When filtering down to just a few customers, `LATERAL ... LIMIT 1` can shine.
- Actual plans depend on indexes, statistics, and data skew.

Compare read-only queries with `EXPLAIN (ANALYZE, BUFFERS)` on representative data instead of picking syntax based on hearsay.

## 19. DISTINCT After JOIN: When Is It Right, and When Does It Hide Bugs?

Suppose you want a list of customers who have placed at least one order. One approach:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM distinct_lab.customers AS c
JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

This returns An, Binh, and Chi. Because `JOIN` emits one row per **order**, `DISTINCT` removes repeated customers.

However, "customers with at least one order" can be expressed more directly using `EXISTS`:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM distinct_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM distinct_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

`EXISTS` directly expresses an existence check; in many cases the planner can choose a semi-join plan without materializing all joined rows only to deduplicate them.

### When Joining order_tags Multiplies Rows

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    t.tag
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY t.tag;
~~~

Order 1001 appears on **two rows** because it has two tags: `gift` and `web`. This is **not corrupt duplicate data**: each row represents a distinct order–tag association.

If you only want orders that have at least one tag:

~~~sql
SELECT DISTINCT o.order_id
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
ORDER BY o.order_id;
~~~

or use `EXISTS`:

~~~sql
SELECT o.order_id
FROM distinct_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM distinct_lab.order_tags AS t
    WHERE t.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

**Never reflexively slap `DISTINCT` onto a query whenever row counts multiply.** First check the relationship cardinality (1:N, N:M), the `JOIN` conditions, and the intended result granularity. A broken `JOIN` condition can create a massive Cartesian product; `DISTINCT` does not turn wrong business logic into right logic.

## 20. DISTINCT ON with Normalized Expressions

Sometimes values to deduplicate differ only in letter case or whitespace. For example, `' An@Example.test '` and `'an@example.test'` may count as the same normalized key under application rules.

Self-contained demo:

~~~sql
WITH contacts(contact_id, email, created_at) AS (
    VALUES
        (1, ' An@Example.test ', timestamp '2026-11-01 08:00'),
        (2, 'an@example.test',   timestamp '2026-11-02 08:00'),
        (3, 'Binh@example.test', timestamp '2026-11-01 10:00')
)
SELECT DISTINCT ON (lower(trim(email)))
    contact_id,
    email,
    lower(trim(email)) AS normalized_email,
    created_at
FROM contacts
ORDER BY
    lower(trim(email)),
    created_at DESC,
    contact_id DESC;
~~~

The result picks `contact_id` 2 for An's email and `contact_id` 3 for Binh.

Key points:

- `DISTINCT ON` groups by the **expression `lower(trim(email))`**, not only the raw string.
- `ORDER BY` starts with that exact grouping expression.
- Timestamp and `contact_id` pick the representative when multiple rows share the normalized key.
- Output still preserves the **representative row's** original email without forcing every column to lowercase.

In real systems, duplicate-email rules can be more involved than `lower(trim())`: Unicode, collations, domain normalization, and identity policies must align. Never merge production accounts using a naive normalization expression without business sign-off.

## 21. DISTINCT, Collations, and Data Types

What counts as "two equal values" depends on **data type** and comparison rules.

For example:

- For integers, `1` and `1` are duplicates.
- For text, comparisons follow collation rules; *nondeterministic collations* can treat byte-distinct strings as equal.
- For timestamps, two `timestamptz` values representing the exact same instant are equal even if input text used different time zone offsets.
- For `NULL`, `DISTINCT` emits one `NULL` group in the result.

Be clear on whether your goal is **logical values** or **text representations**. For instance, when deduplicating timestamps, keep `timestamptz` rather than formatting to strings and deduplicating text, because formatting depends on `TimeZone` or `DateStyle`.

### Can Every Data Type Use DISTINCT?

`DISTINCT` requires an equality check across output expressions. Most standard types—`integer`, `text`, `date`, `timestamp`, `uuid`—have equality operators. Some types lack default equality operators; for instance, legacy `json` lacks standard equality unlike `jsonb`.

When JSON values need equality comparison, consider `jsonb` if semantically valid, keeping in mind `jsonb` normalizes representation (e.g., object key order is not preserved verbatim).

Do not cast types arbitrarily just to make `DISTINCT` compile if casting alters data meaning.

## 22. DISTINCT ON Is Not Random Row Selection

Sometimes a task says "pick any row per group." You can write `DISTINCT ON (group_key)` without `ORDER BY`, yet that is not reliable **random sampling**.

PostgreSQL picks whichever row happens to come first under its execution plan and internal scan order; it does not distribute picks randomly. If controlled random sampling is needed, define an explicit sampling method and store a seed/procedure when reproducibility matters.

Conversely, even when **any row is valid**, leaving the representative nondeterministic makes tests flaky and behavior fragile when requirements evolve. Document the output contract clearly and add a stable tie-breaker whenever possible.

## 23. DISTINCT and LIMIT: Not Interchangeable

`LIMIT` caps **row count**, whereas `DISTINCT` eliminates **duplicate values/tuples**.

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders
ORDER BY customer_id
LIMIT 2;
~~~

This returns the first two distinct `customer_id`s in order: `1` and `2`. It does **not** mean "two orders per customer."

For "two newest orders **per customer**", use `ROW_NUMBER()` with `PARTITION BY customer_id` as in section 17.

For "one newest order per customer, then take the two newest representatives overall", use `DISTINCT ON` inside a subquery and `LIMIT 2` outside as in section 12.

Separating these steps avoids a common bug: putting `LIMIT` inside a subquery **before grouping** drops candidates belonging to other customers.

## 24. Query Plans and Cost of DISTINCT

To deduplicate, PostgreSQL must identify rows sharing identical keys. Plans can use strategies such as:

- **Sort + Unique:** sort by the deduplication keys, then retain one row per group.
- **HashAggregate:** hash values into groups to deduplicate when plan and types allow.
- **Ordered Index Scan:** exploit pre-sorted index order to reduce sorting work.
- **Parallel/aggregate plans:** the planner picks variants based on data size and settings.

There is no single fixed plan for every `DISTINCT` query. Row counts, data types, memory budgets, and indexes all influence cost.

### Inspecting with EXPLAIN

~~~sql
EXPLAIN
SELECT DISTINCT customer_id
FROM distinct_lab.orders;
~~~

And:

~~~sql
EXPLAIN
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

The second plan typically aligns with sorting and retaining one row per group. If the source already provides matching order via an index, the planner can avoid part or all of the sort.

To inspect runtime metrics:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

For a `SELECT` on the lab dataset this is safe to observe. Still, `EXPLAIN ANALYZE` **executes the statement**, so never run it on `UPDATE`/`DELETE` against real data just to "peek at the plan" without transaction/rollback safeguards.

### Adding an Index for Latest-Order-per-Customer Queries

~~~sql
CREATE INDEX idx_orders_customer_recent
ON distinct_lab.orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
~~~

The index key order matches:

~~~sql
ORDER BY customer_id, ordered_at DESC, order_id DESC
~~~

This index layout can help fetch rows by `customer_id` in newest-first order. On large tables especially, the planner can leverage it to cut sort and access costs.

**Yet an index does not guarantee reading only one row per group.** A `DISTINCT ON` plan may still scan many index/table entries to visit all groups. If you only need the latest order for a small filtered set of customers, `LATERAL ... LIMIT 1` can use index lookups more selectively.

Even after creating the index, a 7-row table may stick with `Seq Scan + Sort` because PostgreSQL estimates sequential scanning is cheaper. That does not mean the index is broken; benchmark with representative data volume and selectivity.

## 25. When to Use DISTINCT ON vs. ROW_NUMBER or GROUP BY?

| Need | Recommendation | Reason |
| --- | --- | --- |
| List of distinct cities | `SELECT DISTINCT city` | Only unique values needed |
| Count of customers with orders | `COUNT(DISTINCT customer_id)` | Single aggregate scalar needed |
| Total revenue per customer | `GROUP BY customer_id` + `SUM` | Calculation across the whole group needed |
| One newest order per customer | `DISTINCT ON (customer_id)` | Returns full representative row with concise syntax |
| Top three newest orders per customer | `ROW_NUMBER() ... rn <= 3` | Multiple ranked rows per group needed |
| All orders tied for newest timestamp | `RANK() = 1` or JOIN with `MAX` | Must not drop tied winners |
| Customers with at least one order | `EXISTS` | Expresses existence directly |
| Latest order for a small filtered set of parents | `LEFT JOIN LATERAL (... LIMIT 1)` | Can leverage per-parent index lookups |
| Newest order per customer–status pair | `DISTINCT ON (customer_id, status)` | Group by tuple |
| Remove duplicate rows stored in table | Cleanup migration + constraint | `DISTINCT` never modifies tables |

**Pick the tool based on the desired output shape**, not shortest character count. An aggregate is simpler when only counts/sums are needed; a window function fits when ranking multiple rows; `DISTINCT ON` shines when keeping all columns of a single representative row.

## 26. Common Mistakes

### Mistake 1: Thinking DISTINCT Applies Only to the First Column

~~~sql
SELECT DISTINCT customer_id, order_id
FROM distinct_lab.orders;
~~~

Since every `order_id` is unique, this still returns seven rows. If you want unique customers, select only `customer_id` or aggregate appropriately.

### Mistake 2: Using DISTINCT to Mask Row Multiplication in JOINs

If a customer has multiple orders or an order has multiple tags, multiple rows after a JOIN can be valid data. Check relationship cardinality and JOIN predicates before deduplicating.

### Mistake 3: Using DISTINCT ON Without ORDER BY and Calling It "Newest"

Without `ORDER BY`, there is no definition of newest. Always write `ORDER BY group_key, created_at DESC, unique_id DESC`.

### Mistake 4: Missing a Tie-Breaker Key

Two orders sharing `ordered_at` yield unstable representative selection. Append `order_id` or another unique key.

### Mistake 5: Violating the Leftmost ORDER BY Rule

`DISTINCT ON (customer_id)` with `ORDER BY ordered_at DESC, customer_id` fails with a syntax error. `ORDER BY` must start with the grouping expressions.

### Mistake 6: Filtering paid at the Wrong Level

`WHERE status = 'paid'` before `DISTINCT ON` means "newest paid order." Filtering after picking the representative means "newest order, only if it happens to be paid." Those are two different queries.

### Mistake 7: Using MAX(timestamp) and Picking an Arbitrary order_id

`MAX(ordered_at)` returns one timestamp, not a single associated `order_id`. If multiple orders share that timestamp, joining back to `MAX` returns multiple rows.

### Mistake 8: Thinking NULL Is Always Treated as Distinct

`SELECT DISTINCT` and `DISTINCT ON` group `NULL`s together for deduplication, whereas `COUNT(DISTINCT single_expression)` skips `NULL`s.

### Mistake 9: Omitting NULLS LAST with DESC on Nullable Columns

PostgreSQL defaults `DESC` to `NULLS FIRST`. A missing timestamp can beat valid recent timestamps unless you specify `NULLS LAST`.

### Mistake 10: Expecting Inner ORDER BY to Set Outer Display Order

Inner `ORDER BY` selects the group representative; it does not satisfy "display newest representatives globally." Wrap in an outer query with its own `ORDER BY`.

### Mistake 11: Using DISTINCT to Delete Duplicates from a Table

`SELECT DISTINCT` only transforms query output. Underlying table data remains untouched; fixing stored duplicates requires a cleanup workflow and unique constraints.

### Mistake 12: Assuming DISTINCT ON Is Standard SQL Everywhere

`DISTINCT ON` is PostgreSQL-specific syntax; porting to another DBMS typically requires `ROW_NUMBER()` or an equivalent pattern.

### Mistake 13: Assuming an Index Makes DISTINCT ON Always O(number of groups)

Not necessarily. PostgreSQL may still scan many rows or index entries; inspect `EXPLAIN` and actual row counts.

### Mistake 14: Picking Representatives and Assuming Data Stays Latest Forever

A query sees a snapshot matching its isolation level and execution instant. Concurrent transactions can insert newer orders right afterward; `DISTINCT ON` does not create a live client-side view.

## 27. Practice Exercises with Answers

The exercises below use section 2's dataset and require no data modifications.

### Exercise 1: Distinct Cities

Write a query returning distinct cities from the customers table.

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city;
~~~

**Answer:** DNG, HAN, HCM.

### Exercise 2: Which Customers Have Placed an Order?

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders
ORDER BY customer_id;
~~~

**Answer:** 1, 2, 3. Dung (ID 4) has no orders so does not appear.

### Exercise 3: Count Customers with Orders

~~~sql
SELECT COUNT(DISTINCT customer_id) AS customer_count
FROM distinct_lab.orders;
~~~

**Answer:** `3`.

### Exercise 4: Fetch Each Customer's Newest Order

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

**Answer:** `(1,1003)`, `(2,1005)`, `(3,1007)`.

### Exercise 5: Pick the Newest Paid Order

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, status
FROM distinct_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

**Answer:** `(1,1003,paid)`, `(2,1004,paid)`, `(3,1007,paid)`.

### Exercise 6: Retrieve All Customers, Including Those Without Orders

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

**Answer:** An 1003, Binh 1005, Chi 1007, Dung NULL.

### Exercise 7: Why Could An Get 1002 Without order_id DESC?

**Answer:** 1002 and 1003 share the same timestamp. `ORDER BY customer_id, ordered_at DESC` leaves those two rows tied; PostgreSQL makes no guarantee which one is picked. Add `order_id DESC` to deterministically pick 1003.

### Exercise 8: Pick Each Customer's Highest-Total Order

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, total
FROM distinct_lab.orders
ORDER BY customer_id, total DESC, order_id DESC;
~~~

**Answer:** An 1003 (150.00), Binh 1005 (300.00), Chi 1007 (75.00).

### Exercise 9: Newest Order per Customer and Status

~~~sql
SELECT DISTINCT ON (customer_id, status)
    customer_id, status, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    status,
    ordered_at DESC,
    order_id DESC;
~~~

**Answer:** Five groups: (1, paid) 1003; (1, pending) 1002; (2, cancelled) 1005; (2, paid) 1004; (3, paid) 1007.

### Exercise 10: Two Newest Orders per Customer

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

**Answer:** An 1003 and 1002; Binh 1005 and 1004; Chi 1007 and 1006.

### Exercise 11: Retrieve All Orders Tied for Newest Timestamp

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC
        ) AS rnk
    FROM distinct_lab.orders
)
SELECT customer_id, order_id
FROM ranked
WHERE rnk = 1
ORDER BY customer_id, order_id;
~~~

**Answer:** An has **1002 and 1003**; Binh has 1005; Chi has 1007. This is an **all-tied-rows** problem, not single-row `DISTINCT ON`.

### Exercise 12: Why Does JOIN Produce Two Rows for Order 1001?

~~~sql
SELECT o.order_id, t.tag
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY t.tag;
~~~

**Answer:** Because 1001 has two tags: `gift` and `web`. These are two distinct associations, not duplicate stored orders. To check whether an order has any tag, use `EXISTS`; to list all tags, keep both rows.

### Exercise 13: Pick Representatives, Then Sort Globally by Time

~~~sql
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id, order_id, ordered_at
    FROM distinct_lab.orders
    ORDER BY customer_id, ordered_at DESC, order_id DESC
) AS latest
ORDER BY ordered_at DESC, order_id DESC;
~~~

**Answer:** Representative order is Chi 1007, An 1003, Binh 1005.

## 28. Workflow for Choosing a Technique in Real Projects

When given a requirement to "deduplicate", "fetch the latest record", or "keep one row per group", follow these steps:

1. **Define the output unit:** customer, order, product, or a key pair?
2. **Define needed columns:** only grouping keys, or full columns of a representative record?
3. **Define the group:** single column or multi-column tuple, any text normalization or NULL grouping?
4. **Define priority rules:** newest, highest value, preferred status, or a multi-criteria chain?
5. **Add a unique tie-breaker:** ID or another key that resolves ties deterministically.
6. **Define filter stage:** filter candidates before selecting representatives, or filter representatives after selection?
7. **Decide on empty groups:** if needed, start from the parent table with `LEFT JOIN` or `LATERAL`.
8. **Decide rows per group:** one row uses `DISTINCT ON`/`ROW_NUMBER=1`; top-N uses window functions; all ties use `RANK`.
9. **Audit JOINs:** extra rows may come from valid 1:N relationships rather than duplicates to hide.
10. **Inspect query plans:** test matching index orderings and compare `EXPLAIN` on representative data.
11. **Test edge cases:** empty groups, tied timestamps, NULLs, single-row groups, multiple statuses.
12. **Document the output contract:** ensure readers understand how the "representative row" is chosen.

A short `DISTINCT ON` query lacking priority rules can return syntactically valid rows that are **business-wrong**. Reliability comes from clearly defining grouping and selection order.

## 29. Official References

- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): syntax for `DISTINCT`, `DISTINCT ON`, and `ORDER BY` rules.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): introduction to `ROW_NUMBER`, `RANK`, and `PARTITION BY`.
- [PostgreSQL — Window Function Reference](https://www.postgresql.org/docs/current/functions-window.html): full list and semantics of window functions.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): reading and measuring execution plans.
- [PostgreSQL — Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): relationship between B-tree indexes and query ordering.

When targeting a specific major version, consult the documentation for that server version, as syntax and optimizer capabilities evolve across releases.

## 30. Summary

| Tool | Result Type | Key Takeaways |
| --- | --- | --- |
| `SELECT DISTINCT` | Each unique tuple of selected expressions once | All columns/expressions in `SELECT` define uniqueness |
| `COUNT(DISTINCT x)` | Count of distinct values of `x` | Ignores NULL when `x` is a single expression |
| `DISTINCT ON (key)` | One **representative row** per group key | `ORDER BY` must start with group keys and specify priority |
| `GROUP BY` + aggregate | One summary row per group | Does not automatically retrieve full rows for `MAX`/`MIN` |
| `ROW_NUMBER()` | Sequential rank per row in group | Supports top-N as well as `rn = 1` |
| `RANK()` | Tied rows share the same rank | Ideal when keeping all first-place ties |
| `EXISTS` | Pure relationship existence check | Avoids multiplying rows with `JOIN` only to deduplicate |

**`DISTINCT` returns unique values; `DISTINCT ON` returns representative rows; `GROUP BY` returns aggregates; window functions return ranks.**

In PostgreSQL, to select representatives reliably, always clarify **what to group by, which row takes priority, how ties break, and whether filtering happens before or after selection**. Once those four points are explicit, your SQL becomes both easy to read and faithful to business requirements.
