# Controlling Row Multiplication When Joining Multiple Relations in PostgreSQL

A `JOIN` query can be syntactically valid, run fast, and still return **the wrong dollar amounts or counts**. For example, suppose an order has two product items and two payments. Joining both child tables to the orders table makes PostgreSQL generate four item–payment combinations. If you then apply `SUM` directly, both item totals and payment totals get counted twice.

This lesson belongs to the **Combining Data** chapter of the **Database Engine Relational PostgreSQL** module. The goal is to understand exactly why joins produce multiple rows, know when that behavior is valid, and pick the right SQL strategy to preserve the intended **data grain**.

After this lesson, you will be able to:

- Distinguish genuinely duplicate data from valid parent-row repetition in a one-to-many relationship.
- Predict row counts when joining multiple one-to-many or many-to-many tables.
- Spot fanout errors that corrupt `COUNT`, `SUM`, and JSON aggregations.
- Use `EXISTS` when you only need to check whether related rows exist.
- Pre-aggregate child tables independently before joining back to the parent grain.
- Select a single child row deterministically using `DISTINCT ON`, `ROW_NUMBER()`, or `LATERAL`.
- Audit composite keys, `LEFT JOIN` predicates, `UNIQUE` constraints, time-versioned records, and duplicate-key inputs.
- Reconcile figures against source tables and inspect `EXPLAIN` to aid analysis.

## 1. Is "Row Multiplication" Always a Bug?

Suppose customer 1 has two orders:

~~~text
customer                    sales_order
customer_id | name          order_id | customer_id
------------+--------       ---------+------------
1           | An            1001     | 1
                            1002     | 1
~~~

A join:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id;
~~~

produces two rows:

~~~text
1 | An | 1001
1 | An | 1002
~~~

Customer An appears twice, yet those two rows represent **two distinct orders**. That output is completely accurate if you want a list of orders with customer names.

If you omit `order_id` from `SELECT`, the two rows will look identical. Duplicate-looking displayed values do not prove PostgreSQL joined incorrectly.

**The single most important question is: what entity must one output row represent?** If you need one row per customer, you cannot take a raw one-to-many join and expect one row per customer.

## 2. Data Grain

Grain describes the meaning and level of detail of a single row.

| Dataset | Typical Grain |
|---|---|
| `customer` | One customer |
| `sales_order` | One order |
| `order_item` | One product line item in an order |
| `payment` | One payment transaction |
| `shipment` | One shipment |
| Order summary report | One row per `order_id` |
| Customer summary report | One row per `customer_id` |
| Order item list | One row per `item_id` |
| Pairing every item with every payment of an order | One row per item–payment pair |

Grain is not merely formatting. It governs **whether a metric can be summed safely**. Line-item totals live at the `item_id` grain; payment totals live at the `payment_id` grain. If a query turns one item into multiple combinations, you cannot treat every combination as a fresh item when summing money.

Before writing a query, state a sentence like:

> "I need exactly one row per order, including its total item amount and total payment amount."

Next, verify whether every joined source is unique by `order_id`.

## 3. Relationship Cardinality

| Relationship | Example | Effect on JOIN |
|---|---|---|
| One-to-one (1:1) | Each order has at most one summary record | Does not multiply rows when the right side is unique |
| One-to-many (1:N) | One order has multiple items | Order row repeats per item count |
| Many-to-one (N:1) | Multiple orders belong to one customer | Each order matches at most one customer if customer key is unique |
| Many-to-many (N:M) | Users belong to multiple groups | Produces multiple user–group pairs |
| Unmatched | Order with no payment yet | Dropped by INNER JOIN, kept with NULLs by LEFT JOIN |

A **foreign key** from item to order guarantees only that an item points to a valid order. It **does not guarantee each order has only one item**. You need `UNIQUE` or `PRIMARY KEY` on the child key if business logic truly enforces one-to-one.

## 4. Creating PostgreSQL Practice Data

The following examples use the `join_lab` schema. **Create it only in a dedicated learning database.** If a schema with that name already exists, use a fresh test environment or schema management workflow; never accidentally wipe real data.

~~~sql
CREATE SCHEMA join_lab;

CREATE TABLE join_lab.customer (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL
);

CREATE TABLE join_lab.sales_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES join_lab.customer(customer_id),
    placed_on DATE NOT NULL
);

CREATE TABLE join_lab.order_item (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE join_lab.payment (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    paid_on DATE NOT NULL
);

CREATE TABLE join_lab.shipment (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES join_lab.sales_order(order_id),
    tracking_code TEXT NOT NULL UNIQUE
);
~~~

Load fixed data:

~~~sql
INSERT INTO join_lab.customer
    (customer_id, full_name)
VALUES
    (1, 'Nguyễn An'),
    (2, 'Trần Bình'),
    (3, 'Lê Chi');

INSERT INTO join_lab.sales_order
    (order_id, customer_id, placed_on)
VALUES
    (1001, 1, DATE '2026-02-01'),
    (1002, 1, DATE '2026-02-02'),
    (1003, 2, DATE '2026-02-03'),
    (1004, 3, DATE '2026-02-04');

INSERT INTO join_lab.order_item
    (item_id, order_id, sku, quantity, unit_price)
VALUES
    (11, 1001, 'BOOK', 2, 100.00),
    (12, 1001, 'MOUSE', 1, 50.00),
    (13, 1002, 'KEYBOARD', 1, 200.00),
    (14, 1003, 'CABLE', 1, 90.00);

INSERT INTO join_lab.payment
    (payment_id, order_id, amount, paid_on)
VALUES
    (21, 1001, 120.00, DATE '2026-02-01'),
    (22, 1001, 130.00, DATE '2026-02-02'),
    (23, 1002, 200.00, DATE '2026-02-02'),
    (24, 1003, 90.00, DATE '2026-02-03');

INSERT INTO join_lab.shipment
    (shipment_id, order_id, tracking_code)
VALUES
    (31, 1001, 'SHIP-A'),
    (32, 1001, 'SHIP-B'),
    (33, 1002, 'SHIP-C');
~~~

Expected state:

| order_id | Item Count | Total Item Amount | Payment Count | Total Payment | Shipment Count |
|---:|---:|---:|---:|---:|---:|
| 1001 | 2 | 250.00 | 2 | 250.00 | 2 |
| 1002 | 1 | 200.00 | 1 | 200.00 | 1 |
| 1003 | 1 | 90.00 | 1 | 90.00 | 0 |
| 1004 | 0 | 0.00 | 0 | 0.00 | 0 |

Order 1001 has multiple rows in all three child tables. Order 1004 intentionally has zero child rows to demonstrate `LEFT JOIN` and `NULL`.

## 5. A Single One-to-Many JOIN Is Valid When the Grain Is the Child Row

~~~sql
SELECT
    o.order_id,
    i.item_id,
    i.sku,
    i.quantity * i.unit_price AS line_total
FROM join_lab.sales_order AS o
JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
~~~

Result:

| order_id | item_id | sku | line_total |
|---:|---:|---|---:|
| 1001 | 11 | BOOK | 200.00 |
| 1001 | 12 | MOUSE | 50.00 |
| 1002 | 13 | KEYBOARD | 200.00 |
| 1003 | 14 | CABLE | 90.00 |

Four result rows is correct because there are four items. Order 1001 appearing twice is expected. Order 1004 is omitted because `INNER JOIN` finds no matching items.

To also keep orders without items:

~~~sql
SELECT
    o.order_id,
    i.item_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
~~~

Result has **five rows**: two rows for 1001 and one row for each remaining order; for 1004, `item_id` is `NULL`.

**LEFT JOIN does not guarantee one row per left-side row.** It guarantees only that a left row is not dropped when no right row matches.

## 6. Common Trap: Joining Two Child Tables to the Same Parent Table

Look at this query:

~~~sql
SELECT
    o.order_id,
    i.item_id,
    i.quantity * i.unit_price AS line_total,
    p.payment_id,
    p.amount AS payment_amount
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY i.item_id, p.payment_id;
~~~

Result:

| order_id | item_id | line_total | payment_id | payment_amount |
|---:|---:|---:|---:|---:|
| 1001 | 11 | 200.00 | 21 | 120.00 |
| 1001 | 11 | 200.00 | 22 | 130.00 |
| 1001 | 12 | 50.00 | 21 | 120.00 |
| 1001 | 12 | 50.00 | 22 | 130.00 |

Visualize it:

~~~text
            order 1001
             /      \
       2 items      2 payments
          \          /
           2 x 2 = 4 combinations

 item 11 + payment 21
 item 11 + payment 22
 item 12 + payment 21
 item 12 + payment 22
~~~

PostgreSQL did not duplicate items or payments in the underlying tables. It simply returned **every combination satisfying the JOIN conditions**. Because items and payments have no direct link to each other here, every item pairs with every payment of the same order.

This is **join fanout**. In reporting/BI modeling, joining multiple one-to-many fact tables around a shared dimension is also known as a **chasm trap**.

## 7. Predicting Row Counts Across Multiple Child Relations

For an order with:

- `n_i` items;
- `n_p` payments;
- `n_s` shipments;

joining all three independent child tables on `order_id` without extra filters produces under `INNER JOIN`:

\[
n_i \times n_p \times n_s
\]

rows for that order.

With a `LEFT JOIN` chain like the example and independent child relations, the row count is:

\[
\max(1,n_i)\times\max(1,n_p)\times\max(1,n_s)
\]

Order 1001:

- Items × payments = 2 × 2 = **4** rows.
- Items × payments × shipments = 2 × 2 × 2 = **8** rows.

Order 1004 has 0 items, 0 payments, and 0 shipments, yet `LEFT JOIN` still returns **one row with NULL child columns**.

The formula above describes one specific join shape. If direct conditions exist between child tables, or extra filters/constraints apply, calculate row counts from the actual predicates.

## 8. Wrong SUM Example Despite Valid GROUP BY Syntax

~~~sql
SELECT
    o.order_id,
    COALESCE(
        SUM(i.quantity * i.unit_price), 0
    ) AS item_total,
    COALESCE(
        SUM(p.amount), 0
    ) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

For order 1001:

~~~text
item_total    = 200 + 200 + 50 + 50 = 500
payment_total = 120 + 130 + 120 + 130 = 500
~~~

The true total is **250.00** on each side.

`GROUP BY o.order_id` groups rows **only after the JOINs have multiplied them**. It does not know that two appearances of item 11 came from the same source item, so it cannot drop the repeated money.

Notably, orders 1002 and 1003 have only one item and one payment, so their results appear right by coincidence. Such bugs often surface in production only after a customer makes multiple partial payments.

## 9. Why SUM(DISTINCT amount) Is Not a Valid Fix

A common flawed patch:

~~~sql
-- NOT a reliable fix for fanout:
SUM(DISTINCT i.quantity * i.unit_price)
~~~

Suppose an order has two distinct items, each costing 100.00:

~~~text
item_id | line_total
--------+-----------
11      | 100.00
12      | 100.00
~~~

The true sum is **200.00**. Yet `SUM(DISTINCT line_total)` adds 100.00 only once, returning **100.00**.

`DISTINCT` on a monetary expression deduplicates by **value**, ignoring that the two items have different `item_id`s. Likewise, two separate payments can have the exact same dollar amount.

**Rule:** never use `SUM(DISTINCT amount)` as a substitute for controlling grain. Aggregate at the proper entity/event level prior to joining.

## 10. Primary Solution: Pre-Aggregate Each Child Relation Before JOIN

If the report needs **one row per order**, reduce each child table to **at most one row per `order_id`** first.

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS payment_total
    FROM join_lab.payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.payment_total, 0) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Expected result:

| order_id | item_count | item_total | payment_count | payment_total |
|---:|---:|---:|---:|---:|
| 1001 | 2 | 250.00 | 2 | 250.00 |
| 1002 | 1 | 200.00 | 1 | 200.00 |
| 1003 | 1 | 90.00 | 1 | 90.00 |
| 1004 | 0 | 0.00 | 0 | 0.00 |

Diagram:

~~~text
order_item (n items/order)
          |
       GROUP BY order_id
          v
item_totals (1 row/order) -----+
                               |
                               v
sales_order (1 row/order) ---> output 1 row/order
                               ^
                               |
payment_totals (1 row/order) --+
          ^
       GROUP BY order_id
          |
payment (n payments/order)
~~~

Key properties:

1. `item_totals` sums only item lines and never sees payments.
2. `payment_totals` sums only payments and never sees items.
3. Each CTE after `GROUP BY order_id` has at most one row per key.
4. `LEFT JOIN` keeps orders without child rows.
5. `COALESCE` turns NULL totals/counts for childless orders into 0 as required by the report.

### 10.1. CTEs Are Not Automatically Physical Tables

`WITH item_totals AS (...)` expresses the logic cleanly, though PostgreSQL may inline or transform CTEs during planning. What guarantees the grain here is **`GROUP BY order_id`**, not the `WITH` keyword itself.

## 11. Correlated Subqueries: One Separate Source per Metric

Another way to avoid the `item × payment` product:

~~~sql
SELECT
    o.order_id,
    COALESCE(
        (
            SELECT SUM(i.quantity * i.unit_price)
            FROM join_lab.order_item AS i
            WHERE i.order_id = o.order_id
        ), 0
    ) AS item_total,
    COALESCE(
        (
            SELECT SUM(p.amount)
            FROM join_lab.payment AS p
            WHERE p.order_id = o.order_id
        ), 0
    ) AS payment_total
FROM join_lab.sales_order AS o
ORDER BY o.order_id;
~~~

Each calculation inspects only child rows for **one order**.

This style is very readable when there are only a few metric columns and the outer order set is filtered small. However, for full-system reports, performance of correlated subqueries vs. pre-aggregation depends on plans, indexes, and data size.

Never assume one syntax is always faster. Ensure **correct results** first, then measure with `EXPLAIN`.

## 12. LEFT JOIN LATERAL: Per-Parent Aggregations

`LATERAL` allows a subquery in `FROM` to reference columns from preceding sources:

~~~sql
SELECT
    o.order_id,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_total, 0) AS payment_total
FROM join_lab.sales_order AS o
LEFT JOIN LATERAL (
    SELECT
        SUM(oi.quantity * oi.unit_price) AS item_total
    FROM join_lab.order_item AS oi
    WHERE oi.order_id = o.order_id
) AS i ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(pay.amount) AS payment_total
    FROM join_lab.payment AS pay
    WHERE pay.order_id = o.order_id
) AS p ON TRUE
ORDER BY o.order_id;
~~~

The ungrouped aggregate subqueries above (**without GROUP BY**) always return exactly one summary row, even with zero matching input rows (when `SUM` is NULL). Hence each LATERAL never multiplies order rows.

`LATERAL` is also helpful when selecting **one** latest child row, or a **capped number** of child rows matching specific criteria.

## 13. When You Only Need to Know Whether Child Rows Exist, Use EXISTS

Requirement:

> "List orders that have at least one payment, showing each order once."

Using `JOIN` directly:

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

emits order 1001 **twice** because it has two payments.

A grain-safe approach:

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
WHERE EXISTS (
    SELECT 1
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

Result: 1001, 1002, 1003, each order once.

`EXISTS` checks only **whether at least one matching row exists** without emitting a result row per payment. PostgreSQL can execute this using a **semi join** strategy in suitable plans.

### 13.1. NOT EXISTS: Finding Orders Without Payments

~~~sql
SELECT o.order_id
FROM join_lab.sales_order AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

Result: order **1004**.

You can use `LEFT JOIN ... WHERE p.payment_id IS NULL` when `payment_id` is a non-NULL key. However, `NOT EXISTS` directly models **"no related row exists"** and avoids `NOT IN` traps when subqueries might contain NULL.

## 14. DISTINCT: Valid When You Genuinely Want a Deduplicated Key Set

~~~sql
SELECT DISTINCT o.order_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

This returns one copy of each `order_id` with a payment, because only `order_id` is selected.

However:

~~~sql
SELECT DISTINCT
    o.order_id,
    p.payment_id
FROM join_lab.sales_order AS o
JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001;
~~~

still returns **two rows**, because the `(order_id, payment_id)` pairs differ.

**DISTINCT never fixes metrics already corrupted inside a JOIN.** It merely removes rows whose selected expressions are equal under PostgreSQL semantics.

If you only need "payment exists," `EXISTS` expresses the intent better. If you need total payment amount, sum directly from payments at the right grain.

## 15. DISTINCT ON: Picking One Representative Row Deterministically

PostgreSQL provides `DISTINCT ON` to pick the **first row in a defined sort order** per group.

Fetch the latest payment per order:

~~~sql
SELECT DISTINCT ON (p.order_id)
    p.order_id,
    p.payment_id,
    p.amount,
    p.paid_on
FROM join_lab.payment AS p
ORDER BY
    p.order_id,
    p.paid_on DESC,
    p.payment_id DESC;
~~~

For order 1001, payment 22 is chosen due to its newer payment date. When multiple payments share the same date, `payment_id DESC` serves as a deterministic tie-breaker.

**Note:** "latest payment" and "sum of all payments" are two different requirements. Using `DISTINCT ON` in a payment-total report silently drops earlier valid payments.

### 15.1. Picking One Row Before Joining

Create a CTE with at most one payment per order:

~~~sql
WITH latest_payment AS (
    SELECT DISTINCT ON (p.order_id)
        p.order_id,
        p.payment_id,
        p.amount,
        p.paid_on
    FROM join_lab.payment AS p
    ORDER BY p.order_id, p.paid_on DESC, p.payment_id DESC
)
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN latest_payment AS p
    ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

The output retains one row per order, including 1004 with NULL payment fields.

## 16. ROW_NUMBER(): Another Way to Pick Rows per Group

~~~sql
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.order_id
            ORDER BY p.paid_on DESC, p.payment_id DESC
        ) AS rn
    FROM join_lab.payment AS p
)
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN ranked AS p
    ON p.order_id = o.order_id
   AND p.rn = 1
ORDER BY o.order_id;
~~~

`ROW_NUMBER()` numbers rows within each order partition. `rn=1` selects one row; choosing `rn <= 2` can intentionally yield up to two rows per order.

Placing `rn=1` in `ON` preserves `LEFT JOIN` semantics. Putting `WHERE p.rn=1` would drop orders without any payments.

## 17. LATERAL with ORDER BY LIMIT 1

Same goal—"latest payment":

~~~sql
SELECT
    o.order_id,
    p.payment_id,
    p.amount
FROM join_lab.sales_order AS o
LEFT JOIN LATERAL (
    SELECT
        payment_id,
        amount,
        paid_on
    FROM join_lab.payment AS p
    WHERE p.order_id = o.order_id
    ORDER BY paid_on DESC, payment_id DESC
    LIMIT 1
) AS p ON TRUE
ORDER BY o.order_id;
~~~

`LIMIT 1` caps joined payments per order. With a matching index on `(order_id, paid_on DESC, payment_id DESC)`, a per-order index lookup plan can be very efficient, especially when the driving order set is small.

Never use `LIMIT 1` to **hide** a uniqueness violation disallowed by business rules. If a "current profile" table is supposed to have at most one row per customer, enforce it with a constraint.

## 18. LEFT JOIN and WHERE Can Change Semantics

~~~sql
SELECT o.order_id, p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
WHERE p.amount > 0;
~~~

Orders without payments have `p.amount = NULL` and are dropped because the `WHERE` predicate is not TRUE.

To **keep all orders** while joining only positive payments:

~~~sql
SELECT o.order_id, p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
   AND p.amount > 0
ORDER BY o.order_id, p.payment_id;
~~~

This keeps order 1004 with NULL `payment_id`. Still, if an order has multiple positive payments, the result **still has multiple rows**—it does not collapse into one row per order.

If you need one row per order, you still need aggregation or an existence check.

## 19. COUNT(*) vs. COUNT(child_id) After LEFT JOIN

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(i.item_id) AS item_count
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

For order 1004:

- `COUNT(*) = 1` because `LEFT JOIN` creates one row keeping the order.
- `COUNT(i.item_id) = 0` because `item_id` is NULL on the unmatched row.

For order 1001, joining items alone gives `COUNT(i.item_id) = 2`.

Yet if you also join payments, each item repeats twice and `COUNT(i.item_id)` becomes 4. While `COUNT(DISTINCT i.item_id)` still counts **2 distinct items**, any `SUM` of item amounts on that same joined set remains wrong.

### 19.1. COUNT(DISTINCT) Does Not Replace Pre-Aggregation

If the only goal is counting distinct items by `item_id`, `COUNT(DISTINCT i.item_id)` is accurate. However, `COUNT(DISTINCT i.sku)` can be wrong if two separate line items share the same SKU.

And a query having an accurate `COUNT(DISTINCT item_id)` does not guarantee `SUM(payment.amount)` in that same query is right.

## 20. Aggregating Three Child Tables Simultaneously

~~~sql
WITH
item_counts AS (
    SELECT order_id, COUNT(*) AS item_count
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_counts AS (
    SELECT order_id, COUNT(*) AS payment_count
    FROM join_lab.payment
    GROUP BY order_id
),
shipment_counts AS (
    SELECT order_id, COUNT(*) AS shipment_count
    FROM join_lab.shipment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(s.shipment_count, 0) AS shipment_count
FROM join_lab.sales_order AS o
LEFT JOIN item_counts AS i ON i.order_id = o.order_id
LEFT JOIN payment_counts AS p ON p.order_id = o.order_id
LEFT JOIN shipment_counts AS s ON s.order_id = o.order_id
ORDER BY o.order_id;
~~~

Every CTE has **at most one row per `order_id`**, so joining them keeps one row per order.

If you also need dollar amounts, include the sums inside each branch CTE; **do not** join the raw child table back into the final query just to compute another metric.

## 21. Two-Stage Aggregation: Order, Then Customer

Requirement: one row per customer with total item amount across their orders.

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(SUM(ot.item_total), 0) AS total_item_amount
FROM join_lab.customer AS c
LEFT JOIN join_lab.sales_order AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_totals AS ot
    ON ot.order_id = o.order_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Result:

| customer_id | full_name | total_item_amount |
|---:|---|---:|
| 1 | Nguyễn An | 450.00 |
| 2 | Trần Bình | 90.00 |
| 3 | Lê Chi | 0.00 |

Grain flow:

~~~text
item_id -- GROUP BY order_id --> order_id
order_id -- JOIN customer --> multiple orders/customer
customer_id -- GROUP BY customer_id --> one row/customer
~~~

Each customer having multiple orders is **valid**, and metrics were already rolled up to the order grain beforehand, so they are never multiplied by payments or shipments.

## 22. Valid Many-to-Many and Junction Tables

One user can belong to multiple groups; one group can have multiple members.

~~~sql
WITH membership(user_id, group_id) AS (
    VALUES
        (1, 10),
        (1, 20),
        (2, 10)
)
SELECT user_id, group_id
FROM membership
ORDER BY user_id, group_id;
~~~

User 1 appearing twice is accurate: two distinct memberships.

In a real table, use a composite key:

~~~sql
CREATE TABLE join_lab.membership_demo (
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
~~~

The composite key prevents recording the same **user–group pair** twice, while still allowing a user to belong to many groups.

If you join `membership` to a tags table where a group has multiple tags, user rows will multiply by tag count. To count **distinct groups**, aggregate by `group_id` or at the membership grain, not `COUNT(*)` after every join.

## 23. JOIN Missing ON or Overly Weak Conditions

~~~sql
SELECT c.customer_id, o.order_id
FROM join_lab.customer AS c
CROSS JOIN join_lab.sales_order AS o;
~~~

There are 3 customers × 4 orders = **12 combinations**. If the goal is generating every customer–order pair for testing, that is right. If the goal is pairing customers with their actual orders, the relationship is wrong.

A `JOIN ... ON TRUE` generates the exact same product.

### 23.1. Missing Part of a Composite Key

Suppose multi-tenant tables have logical key `(tenant_id, order_id)`. Two tenants can both use `order_id=1001`.

Wrong:

~~~sql
-- Conceptual example:
-- ON payment.order_id = orders.order_id
~~~

Correct for a composite key:

~~~sql
-- Conceptual example:
SELECT ...
FROM tenant_orders AS o
JOIN tenant_payments AS p
    ON p.tenant_id = o.tenant_id
   AND p.order_id = o.order_id;
~~~

Omitting `tenant_id` lets a tenant B payment match a tenant A order and produce erroneous rows.

**Join conditions must cover the full meaningful key**, not merely a subset of same-named columns.

## 24. Mis-Joining Two Child Tables When a Direct Link Exists

Suppose each refund links to **one payment** via `payment_id`.

Correct join:

~~~sql
-- Conceptual example:
SELECT
    p.payment_id,
    r.refund_id
FROM payment AS p
LEFT JOIN refund AS r
    ON r.payment_id = p.payment_id;
~~~

Joining refunds to payments via their **shared `order_id`** instead of `payment_id` pairs every refund of an order with payments that do not own that refund.

In this case, you do not necessarily need pre-aggregation. First **use the actual foreign key linking the relations**.

## 25. Temporal JOINs Can Match Multiple Effective Versions

Suppose a price history table has multiple time ranges. An order is placed on a date covered by two overlapping price intervals:

~~~sql
WITH
orders(order_id, sku, ordered_on) AS (
    VALUES
        (1, 'A'::TEXT, DATE '2026-02-10')
),
price_history(price_id, sku, valid_from, valid_to, price) AS (
    VALUES
        (101, 'A'::TEXT,
            DATE '2026-02-01', DATE '2026-03-01', 110.00::NUMERIC),
        (102, 'A'::TEXT,
            DATE '2026-02-05', DATE '2026-02-20', 115.00::NUMERIC)
)
SELECT
    o.order_id,
    h.price_id,
    h.price
FROM orders AS o
JOIN price_history AS h
    ON h.sku = o.sku
   AND o.ordered_on >= h.valid_from
   AND o.ordered_on < h.valid_to
ORDER BY h.price_id;
~~~

The result contains **two price rows for one order**, because both intervals cover Feb 10.

You can pick the latest `valid_from` using `LATERAL ... LIMIT 1` if **business rules explicitly endorse** that tie-breaking rule. However, if intervals are never supposed to overlap, silently picking one row hides corrupt data.

Durable solutions:

- Use half-open intervals `[from,to)`.
- Require at most one active version per key at any point in time.
- Validate writes against overlapping intervals.
- Consider range types and appropriate exclusion constraints if PostgreSQL should enforce non-overlapping intervals.

## 26. NULL in Join Keys Can Surprise You

With:

~~~sql
ON a.optional_key = b.optional_key
~~~

two `NULL` values are not considered equal under SQL equality semantics.

PostgreSQL provides `IS NOT DISTINCT FROM` for "NULL equals NULL" comparisons when business logic genuinely requires it:

~~~sql
ON a.optional_key IS NOT DISTINCT FROM b.optional_key
~~~

However, if A has two NULL rows and B has three NULL rows, this predicate produces **2 × 3 = 6** combinations.

Example:

~~~sql
WITH
a(id, k) AS (
    VALUES (1, NULL::INTEGER), (2, NULL::INTEGER)
),
b(id, k) AS (
    VALUES
        (10, NULL::INTEGER),
        (11, NULL::INTEGER),
        (12, NULL::INTEGER)
)
SELECT a.id AS a_id, b.id AS b_id
FROM a
JOIN b ON a.k IS NOT DISTINCT FROM b.k
ORDER BY a.id, b.id;
~~~

Never turn NULL (typically meaning "unknown") into a shared grouping code that accidentally joins every unknown record together.

## 27. Unique Constraints Are Cardinality Contracts

If a `shipping_summary` table is designed to hold **at most one row per order**, the schema should declare it:

~~~sql
CREATE TABLE join_lab.shipping_summary_demo (
    order_id INTEGER PRIMARY KEY
        REFERENCES join_lab.sales_order(order_id),
    latest_tracking_code TEXT
);
~~~

When joining that summary table on `order_id`, the right side matches at most one row. That is far more reliable than assuming "it looks like each order currently has one row."

Distinguish:

- `PRIMARY KEY/UNIQUE(order_id)` on a summary table → one-to-one per order.
- `FOREIGN KEY(order_id) REFERENCES sales_order` on payment → multiple payments can belong to one order.

A relation intended to be unique **without a constraint** can suffer data-entry bugs later that multiply query rows.

### 27.1. Uniqueness of Join Expressions Matters Too

For instance, an `email` column may have a unique constraint, yet joining on `lower(email)` can match multiple rows if the source contains emails differing only in case while the constraint does not guard `lower(email)`.

If business rules require uniqueness on a normalized expression, consider a unique expression index or a normalized storage column.

## 28. Pick the Right Driving Relation for Your Goal

If the report needs **every order**, start from `sales_order` and `LEFT JOIN` summaries.

If the report needs **every item line**, start from `order_item` and join `sales_order` for parent attributes.

If the report needs **every customer**, start from `customer`, then join customer-level aggregates.

If the report needs **days without any transactions**, start from a calendar/date series, then join daily transaction summaries.

Which table acts as the "driving set" determines whether entities without child records stay or vanish. Picking the wrong starting table alters grain and row counts even when every subsequent join condition is valid.

## 29. UNION ALL Can Be Better Than JOIN

Suppose the goal is one row per **event**, covering both items and payments. There is no need to generate every item–payment pair. You can stack the events sequentially:

~~~sql
SELECT
    order_id,
    'item'::TEXT AS event_type,
    item_id AS event_id
FROM join_lab.order_item

UNION ALL

SELECT
    order_id,
    'payment'::TEXT AS event_type,
    payment_id AS event_id
FROM join_lab.payment

ORDER BY order_id, event_type, event_id;
~~~

`UNION ALL` adds the row counts of both sources. `JOIN` places columns of matching rows side by side on the same output row, potentially creating combinatorial products.

When you want a combined event timeline, `UNION ALL` usually models the requirement much better than a JOIN.

## 30. JSON Aggregation and Fanout

An API might need an order object containing two independent arrays:

~~~json
{
  "order_id": 1001,
  "items": [
    {"item_id": 11, "sku": "BOOK"},
    {"item_id": 12, "sku": "MOUSE"}
  ],
  "payments": [
    {"payment_id": 21, "amount": 120},
    {"payment_id": 22, "amount": 130}
  ]
}
~~~

If you join `item × payment` and then call `jsonb_agg`, every item repeats twice and every payment repeats twice.

The right approach is to build each array **independently per source** and then join:

~~~sql
WITH
item_json AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'item_id', item_id,
                'sku', sku,
                'quantity', quantity
            )
            ORDER BY item_id
        ) AS items
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_json AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'payment_id', payment_id,
                'amount', amount
            )
            ORDER BY paid_on, payment_id
        ) AS payments
    FROM join_lab.payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.items, '[]'::jsonb) AS items,
    COALESCE(p.payments, '[]'::jsonb) AS payments
FROM join_lab.sales_order AS o
LEFT JOIN item_json AS i ON i.order_id = o.order_id
LEFT JOIN payment_json AS p ON p.order_id = o.order_id
ORDER BY o.order_id;
~~~

Each CTE returns at most one row per order, so the two arrays never cross-multiply.

`jsonb_agg(DISTINCT ...)` occasionally removes duplicate JSON objects, yet it can collapse distinct events with identical payloads and does not fix numeric metrics. Pre-aggregation preserves true semantics.

## 31. UPDATE ... FROM Also Needs a Unique Source per Key

Fanout does not only break reports. With `UPDATE ... FROM`, if one target row matches multiple source rows, PostgreSQL makes no guarantee about **which source row** supplies the update value.

Suppose a patch source has two values for the same order:

~~~sql
-- Example you should NOT run on real data:
-- UPDATE join_lab.sales_order AS o
-- SET placed_on = patch.new_date
-- FROM (
--     VALUES
--         (1001, DATE '2026-02-10'),
--         (1001, DATE '2026-02-11')
-- ) AS patch(order_id, new_date)
-- WHERE o.order_id = patch.order_id;
~~~

One way to handle it if business rules **explicitly pick the maximum date**:

~~~sql
BEGIN;

WITH patch(order_id, new_date) AS (
    VALUES
        (1001, DATE '2026-02-10'),
        (1001, DATE '2026-02-11')
),
resolved AS (
    SELECT
        order_id,
        MAX(new_date) AS new_date
    FROM patch
    GROUP BY order_id
)
UPDATE join_lab.sales_order AS o
SET placed_on = r.new_date
FROM resolved AS r
WHERE o.order_id = r.order_id
RETURNING o.order_id, o.placed_on;

ROLLBACK;
~~~

`ROLLBACK` keeps the test database clean. `MAX` is right only when explicitly mandated by business rules; when conflicting values in a patch are invalid, **reject the patch** instead of picking arbitrarily.

## 32. Diagnostics: Count Rows at Each JOIN Stage

Instead of looking only at the final row count, count rows after each step.

~~~sql
SELECT
    'orders' AS stage,
    COUNT(*) AS row_count
FROM join_lab.sales_order

UNION ALL

SELECT
    'orders + items',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id

UNION ALL

SELECT
    'orders + items + payments',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id

UNION ALL

SELECT
    'orders + items + payments + shipments',
    COUNT(*)
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id
LEFT JOIN join_lab.shipment AS s
    ON s.order_id = o.order_id;
~~~

On our sample data, the counts are **4, 5, 7, 11**.

Why?

- `orders`: 4 rows.
- `orders + items`: two rows for 1001, one row for each other order (including 1004 with no items): 5.
- `orders + items + payments`: 1001 produces 4 combinations; 1002/1003/1004 produce one row each: 7.
- Adding shipments: 1001 has two shipments, turning its 4 combinations into 8; plus 1+1+1 from the other orders: 11.

Counting stage by stage pinpoints the exact JOIN introducing unintended fanout.

## 33. Diagnostics: COUNT per Key

Count child rows:

~~~sql
SELECT
    order_id,
    COUNT(*) AS item_rows
FROM join_lab.order_item
GROUP BY order_id
ORDER BY item_rows DESC, order_id;

SELECT
    order_id,
    COUNT(*) AS payment_rows
FROM join_lab.payment
GROUP BY order_id
ORDER BY payment_rows DESC, order_id;
~~~

Count result rows per order:

~~~sql
WITH joined AS (
    SELECT
        o.order_id,
        i.item_id,
        p.payment_id
    FROM join_lab.sales_order AS o
    LEFT JOIN join_lab.order_item AS i
        ON i.order_id = o.order_id
    LEFT JOIN join_lab.payment AS p
        ON p.order_id = o.order_id
)
SELECT
    order_id,
    COUNT(*) AS joined_rows
FROM joined
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY joined_rows DESC, order_id;
~~~

Order 1001 has four rows, so it appears. The remaining orders have one row and are filtered out by `HAVING`.

**Do not treat `COUNT(*) > 1` as an automatic bug.** It is simply a signal to inspect whenever the expected grain is one row per order.

### 33.1. DISTINCT Counts Help Diagnose Fanout

~~~sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT i.item_id) AS distinct_items,
    COUNT(DISTINCT p.payment_id) AS distinct_payments
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

For 1001, the output is `joined_rows = 4`, `distinct_items = 2`, `distinct_payments = 2`. That proves fanout from both sources.

## 34. Reconciling Totals Directly from Event Tables

Reference figures should be computed **directly from base tables**, without fanout-prone JOINs:

~~~sql
SELECT
    (
        SELECT SUM(quantity * unit_price)
        FROM join_lab.order_item
    ) AS all_item_amount,
    (
        SELECT SUM(amount)
        FROM join_lab.payment
    ) AS all_payment_amount;
~~~

On the sample data, both totals equal:

\[
250.00 + 200.00 + 90.00 = 540.00
\]

This is a useful check against joined summary tables.

However, in real systems total item amount and total payment amount **do not always match**: orders can be partially paid, refunded, or awaiting settlement. Financial invariants must come from real business rules.

## 35. Inspecting EXPLAIN and Row Estimates

The PostgreSQL planner evaluates multiple JOIN strategies, such as:

- `Nested Loop`.
- `Hash Join`.
- `Merge Join`.
- `Hash Left Join`.
- `Sort` and `Aggregate` nodes.

Inspect the plan:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

On a test database, compare estimated vs. actual rows:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    i.item_id,
    p.payment_id
FROM join_lab.sales_order AS o
LEFT JOIN join_lab.order_item AS i
    ON i.order_id = o.order_id
LEFT JOIN join_lab.payment AS p
    ON p.order_id = o.order_id;
~~~

`ANALYZE` **executes the query** to measure it. This example is a SELECT; never run `EXPLAIN ANALYZE` carelessly on production `UPDATE`/`DELETE` statements since it executes writes.

Estimated row counts can differ from actuals due to statistics, data skew, or correlated predicates. Yet even when the planner's estimates are spot-on, summing money over a multiplied JOIN still produces **logically wrong results**.

**Get semantics right first, optimize performance second.**

## 36. Indexes and Fanout Are Two Separate Issues

Foreign key columns are frequently joined:

~~~sql
CREATE INDEX idx_sales_order_customer
ON join_lab.sales_order (customer_id);

CREATE INDEX idx_order_item_order
ON join_lab.order_item (order_id);

CREATE INDEX idx_payment_order
ON join_lab.payment (order_id);

CREATE INDEX idx_shipment_order
ON join_lab.shipment (order_id);
~~~

Indexes can speed up lookups by `order_id` or `customer_id`, depending on data and plans.

PostgreSQL **does not automatically create indexes on child foreign key columns**. On tiny tables, a sequential scan can be faster than an index scan.

Even with indexes, order 1001 still produces **2 items × 2 payments = 4** combinations if the SQL joins them that way. Indexes never alter JOIN semantics.

Likewise, extended statistics can improve planner cardinality estimates in some cases, yet **they never fix multiplied metrics**.

## 37. Common Thinking Mistakes

### Mistake 1 — Not Defining the Grain

The report requires one row per order, yet SQL returns item-level rows.

**Fix:** explicitly write down the unique output key, such as `order_id`.

### Mistake 2 — Assuming a FOREIGN KEY Means One-to-One

One order can have many items or payments.

**Fix:** check for `UNIQUE`/`PRIMARY KEY` on the child side as well.

### Mistake 3 — GROUP BY After Joining Multiple Fact Tables

Amounts have already been multiplied prior to grouping.

**Fix:** pre-aggregate each fact table to the shared grain before joining.

### Mistake 4 — Using SUM(DISTINCT amount)

Can drop valid distinct events that share the same dollar amount.

**Fix:** sum over original event rows, not distinct monetary values.

### Mistake 5 — Using JOIN Merely to Check Existence

An order with multiple payments gets duplicated.

**Fix:** `EXISTS`/`NOT EXISTS`.

### Mistake 6 — Using DISTINCT to Hide Wrong Results

Can hide duplicate-looking rows while leaving `SUM` broken.

**Fix:** diagnose the root cause of fanout and fix the grain or join condition.

### Mistake 7 — Picking the Latest Row Without a Tie-Breaker

When two records share the same date, output is non-deterministic.

**Fix:** add a deterministic tie-breaker such as the primary key in `ORDER BY`.

### Mistake 8 — LEFT JOIN Filtering the Right Column in WHERE

Orders without child rows are dropped.

**Fix:** place the filter in `ON` when left rows must stay.

### Mistake 9 — Using COUNT(*) After LEFT JOIN to Count Child Rows

Orders with no child rows still contribute one row.

**Fix:** `COUNT(child_pk)` or aggregate at the child grain.

### Mistake 10 — Omitting Part of a Composite Key

Data from other tenants matches erroneously.

**Fix:** JOIN on the full logical key, not just one shared column name.

### Mistake 11 — Joining on a Non-Unique Expression

`lower(email)` or truncated dates can match multiple rows.

**Fix:** check uniqueness of the expression itself and the data domain.

### Mistake 12 — Joining on Overlapping Effective Intervals

One transaction matches multiple historical prices.

**Fix:** enforce non-overlapping intervals or define an explicit selection rule.

### Mistake 13 — Building JSON Arrays After a Multiplied JOIN

Every item repeats per payment.

**Fix:** run `jsonb_agg` separately per source, then JOIN summaries.

### Mistake 14 — Using UPDATE FROM with Duplicate-Key Patches

One target row matches multiple patch rows.

**Fix:** validate or resolve the patch to one row per key.

### Mistake 15 — Trusting a View Name

A view named `one_order_summary` does not guarantee one row per order.

**Fix:** inspect its SQL definition, keys, and `GROUP BY order_id HAVING COUNT(*) > 1`.

### Mistake 16 — Focusing on Indexes Before Correctness

A fast query returning wrong totals is still broken.

**Fix:** reconcile against source tables first, then tune with `EXPLAIN`.

## 38. Workflow for Debugging Fanout in Large Queries

When a multi-table query returns unexpected row counts or totals:

**Step 1 — State the output grain.** E.g., each `order_id` appears once.

**Step 2 — List each source's grain.** `customer_id`, `order_id`, `item_id`, `payment_id`, `shipment_id`.

**Step 3 — Read keys and constraints.** Determine which relationships are 1:1, 1:N, or N:M.

**Step 4 — Count per source.** Use `GROUP BY join_key HAVING COUNT(*) > 1`.

**Step 5 — Join step by step and recount.** Spot the exact join where row counts jump.

**Step 6 — Audit `ON` clauses.** Missing `tenant_id`, `line_no`, `payment_id`, version, or time-range predicates?

**Step 7 — Refactor by intent.** Existence → `EXISTS`; totals → pre-aggregate; latest → `DISTINCT ON`/`ROW_NUMBER`/`LATERAL`.

**Step 8 — Preserve unmatched rows properly.** Check `INNER JOIN`/`LEFT JOIN` and filter placement in `ON`/`WHERE`.

**Step 9 — Reconcile.** Aggregate directly from each fact table and compare against the report.

**Step 10 — Test edge cases.** Zero children, one child, many children, two payments with identical amounts, duplicate keys, NULLs, and overlapping intervals.

**Step 11 — Optimize.** Check `EXPLAIN`, indexes, and statistics on representative data.

This workflow separates **business logic errors in output** from **performance issues**.

## 39. Complete Summary Report: Exactly One Row per Order

Requirements:

- Order ID and customer name.
- Item count and total item amount.
- Payment count and total payment amount.
- Shipment count.
- Whether a payment exists.

~~~sql
WITH
item_summary AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS item_total
    FROM join_lab.order_item
    GROUP BY order_id
),
payment_summary AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS payment_total
    FROM join_lab.payment
    GROUP BY order_id
),
shipment_summary AS (
    SELECT
        order_id,
        COUNT(*) AS shipment_count
    FROM join_lab.shipment
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.full_name,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.payment_total, 0) AS payment_total,
    COALESCE(s.shipment_count, 0) AS shipment_count,
    COALESCE(p.payment_count, 0) > 0 AS has_payment
FROM join_lab.sales_order AS o
JOIN join_lab.customer AS c
    ON c.customer_id = o.customer_id
LEFT JOIN item_summary AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_summary AS p
    ON p.order_id = o.order_id
LEFT JOIN shipment_summary AS s
    ON s.order_id = o.order_id
ORDER BY o.order_id;
~~~

Result:

| order_id | full_name | item_count | item_total | payment_count | payment_total | shipment_count | has_payment |
|---:|---|---:|---:|---:|---:|---:|---|
| 1001 | Nguyễn An | 2 | 250.00 | 2 | 250.00 | 2 | true |
| 1002 | Nguyễn An | 1 | 200.00 | 1 | 200.00 | 1 | true |
| 1003 | Trần Bình | 1 | 90.00 | 1 | 90.00 | 0 | true |
| 1004 | Lê Chi | 0 | 0.00 | 0 | 0.00 | 0 | false |

### 39.1. Why Does the Report Have Exactly Four Rows?

- `sales_order` is the driving set, one row per `order_id`.
- `customer` has a unique key, so each order matches at most one customer.
- Each summary CTE has at most one row per order, preventing child cross-multiplication.
- `LEFT JOIN` keeps order 1004.
- `COALESCE` renders missing counts and sums as 0.

### 39.2. "Has Payment" Differs from "Paid in Full"

`has_payment = true` means only that at least one payment row exists. In real systems, payments can fail, be refunded, stay pending, or be partial. Define those business statuses explicitly before computing revenue.

## 40. Practice Exercises

### Exercise 1 — Grain

A customer has three orders. How many rows does `JOIN customer → sales_order` return without filtering?

**Hint:** three rows, which is right when the grain is order.

### Exercise 2 — Two Child Tables

An order has 3 items and 4 payments. How many rows does joining both on `order_id` alone produce?

**Hint:** 12 rows.

### Exercise 3 — Three Child Tables

An order has 2 items, 3 payments, and 2 shipments. How many combinations does joining all three branches produce when all match one order?

**Hint:** 12.

### Exercise 4 — LEFT JOIN and Empty Data

An order has zero items and zero payments. How many rows does LEFT JOINing both still emit?

**Hint:** one row with NULL child columns.

### Exercise 5 — COUNT(*)

Why is `COUNT(*)` over a LEFT JOIN not the item count for order 1004?

**Hint:** one row preserving the order still exists; `COUNT(item_id)=0`.

### Exercise 6 — Wrong SUM

Manually calculate the inflated values from joining `item × payment` for order 1001.

**Hint:** 500.00 on each side instead of 250.00.

### Exercise 7 — SUM(DISTINCT)

Two distinct items both have `line_total` 100.00. What does `SUM(DISTINCT line_total)` return?

**Hint:** 100.00, instead of the true sum 200.00.

### Exercise 8 — Pre-Aggregation

Write a CTE summing items by `order_id` before joining to orders.

**Hint:** `GROUP BY order_id`.

### Exercise 9 — Payment Totals

Write a CTE summing `amount` per order and join it alongside the item summary without multiplying totals.

**Hint:** each summary has at most one row per order.

### Exercise 10 — EXISTS

Find orders with at least one shipment, one row per order.

**Hint:** `WHERE EXISTS`.

### Exercise 11 — NOT EXISTS

Find orders without any payment in the sample data.

**Hint:** 1004.

### Exercise 12 — DISTINCT

Does `SELECT DISTINCT o.order_id, p.payment_id` drop the second payment of order 1001?

**Hint:** no, because `payment_id` differs.

### Exercise 13 — DISTINCT ON

Fetch the latest payment per order using payment date and `payment_id` as tie-breaker.

**Hint:** `DISTINCT ON(order_id) ... ORDER BY order_id, paid_on DESC, payment_id DESC`.

### Exercise 14 — ROW_NUMBER

Write a `ROW_NUMBER()` version of exercise 13.

**Hint:** `PARTITION BY order_id` and `rn=1`.

### Exercise 15 — LATERAL

Fetch at most one latest shipment per order while keeping orders without shipments.

**Hint:** `LEFT JOIN LATERAL (...) ON TRUE`.

### Exercise 16 — LEFT JOIN Filter

Why does `WHERE p.amount > 0` drop order 1004?

**Hint:** NULL does not satisfy the predicate.

### Exercise 17 — Composite Key

An orders table is unique by `(tenant_id,order_id)`. Why is joining on `order_id` alone dangerous?

**Hint:** it can join rows across different tenants.

### Exercise 18 — Effective Intervals

A transaction matches two historical price rows. What might be wrong in the time predicate or source data?

**Hint:** overlapping effective intervals.

### Exercise 19 — REFUND

A refund references `payment_id`. What happens if you join `payment` and `refund` on `order_id` alone?

**Hint:** refunds pair erroneously with other payments on the same order.

### Exercise 20 — JSON

You want one order object containing an item array and a payment array. Where should aggregation happen?

**Hint:** separately per child table prior to joining.

### Exercise 21 — UPDATE FROM

A patch contains two different values for one `order_id`. Should you update directly?

**Hint:** no; inspect and resolve the source first.

### Exercise 22 — Counting Each Stage

Count rows across all four JOIN stages of the sample schema.

**Hint:** 4, 5, 7, 11.

### Exercise 23 — Customer Totals

Compute total item amounts per customer after rolling up to the order level.

**Hint:** customer 1 has 450.00; customer 2 has 90.00; customer 3 has 0.00.

### Exercise 24 — UNION ALL

When you want one row per item or payment as events, why is `UNION ALL` better than `JOIN`?

**Hint:** it stacks rows instead of forming combinatorial pairs.

### Exercise 25 — Index

What can indexing `payment(order_id)` help with, and what can it never fix?

**Hint:** speeds up data access; cannot fix fanout-inflated `SUM`s.

### Exercise 26 — Constraint

If a summary table must have at most one row per order, which constraint should you declare?

**Hint:** `PRIMARY KEY(order_id)` or `UNIQUE(order_id)` per model design.

## 41. Decision Matrix

| Goal | Right Tool | Output Grain |
|---|---|---|
| Every item with order info | JOIN item–order | Item |
| Every payment with order info | JOIN payment–order | Payment |
| Orders with payments | EXISTS | Order |
| Orders without payments | NOT EXISTS | Order |
| Item and payment totals | Pre-aggregate each branch, then JOIN | Order |
| Totals per customer | Order summary, then GROUP BY customer | Customer |
| Latest payment | DISTINCT ON / ROW_NUMBER / LATERAL | One payment/order |
| Item and payment arrays | Separate `jsonb_agg` per branch | Order |
| All item–payment pairs | Direct JOIN if genuinely required | Item–payment pair |
| Item/payment events | UNION ALL | Event |
| Multi-row UPDATE source | Resolve/validate keys before UPDATE FROM | One source value/target key |
| Joining price history | Key + non-overlapping effective intervals | Entity at point in time |

## 42. Summary

- **Parent-row repetition after a JOIN is not automatically a bug**: it can reflect a valid one-to-many relationship.
- **Grain** defines what each row means and how metrics may be summed.
- Joining multiple independent child tables creates a **row product**, such as 2 items × 2 payments = 4 combinations.
- A trailing `GROUP BY` cannot tell which metrics were multiplied; `SUM(DISTINCT amount)` can wrongly drop distinct events sharing the same dollar amount.
- **Pre-aggregating each child table at the shared grain before joining** is the primary solution for one-row-per-order/customer reports.
- **`EXISTS` and `NOT EXISTS`** fit presence/absence checks on child relations.
- **`DISTINCT ON`, `ROW_NUMBER()`, and `LATERAL LIMIT 1`** pick a single child row deterministically; never use them as a substitute for `SUM`.
- `LEFT JOIN` can still multiply rows; filtering in `WHERE` can drop unmatched parent rows.
- **Foreign keys do not imply one-to-one**; `UNIQUE` or `PRIMARY KEY` constraints must enforce true uniqueness.
- Composite keys, tenants, normalized expressions, versions, and effective intervals must all be included in JOIN conditions where applicable.
- Diagnose fanout by **counting per key and per stage**, reconciling totals against base tables, and inspecting `EXPLAIN`.
- For data updates, **`UPDATE ... FROM` must have a unique source per target key** or an explicit conflict-resolution rule.

A trustworthy multi-table query is not merely one that executes without error. It guarantees that **every output row represents the exact intended entity, every metric counts real events exactly once, and every join follows true business relationships**. By defining the grain before writing `JOIN`, you avoid most subtle row-multiplication bugs in PostgreSQL.
