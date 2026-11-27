# Placing Conditions in ON vs. WHERE with Outer Joins in PostgreSQL

## 1. The Core Problem: Same Condition, Different Placement, Different Result

When writing a `LEFT JOIN`, `RIGHT JOIN`, or `FULL JOIN`, a condition can be placed in two positions:

- **`ON`:** determines whether two rows are considered a **match** during the join.
- **`WHERE`:** determines whether a row in the **post-join result** is kept.

With `INNER JOIN`, many ordinary conditions can sit in `ON` or move down to `WHERE` and still yield the exact same result. However, with an **outer join**, moving a condition can completely change which rows are preserved.

Consider two seemingly similar requirements:

> A. "List **all customers**, along with their **paid orders** if any."

> B. "List **customers who have paid orders**, along with those orders."

Requirement A must keep customers who have not paid or have no orders: the order status condition generally belongs in the `ON` clause of `LEFT JOIN`.

Requirement B keeps only customers who have paid orders: filtering in `WHERE` after the join can be appropriate.

This is one of the most common sources of data discrepancies in SQL reports: a query says `LEFT JOIN` yet drops rows that the business requires to appear.

### Lesson Objectives

You will learn how to:

1. Distinguish a **matching predicate** in `ON` from a **result filter** in `WHERE`.
2. Manually trace the result of the same condition placed in both locations.
3. Understand **NULL-extended rows** and SQL three-valued logic.
4. Avoid unintentionally turning a `LEFT JOIN` into an `INNER JOIN`-like filter.
5. Place conditions for the **preserved table** and the **non-preserved table** accurately.
6. Write anti-joins using `IS NULL` and `NOT EXISTS`, including finding "no order matching a condition."
7. Apply the same principles to `RIGHT JOIN`, `FULL JOIN`, and multi-outer-join chains.
8. Count, aggregate, paginate, and use `FILTER`/`COALESCE` without skewing results.
9. Analyze the impact on `EXPLAIN`, indexes, and multi-tenant handling.
10. Choose SQL structures that match business intent rather than moving conditions around by guesswork.

This lesson is built for PostgreSQL and uses a fixed dataset so you can run, observe, and compare results yourself.

## 2. Setting Up Sample Data: Customers and Orders

To see the difference between `ON` and `WHERE` clearly, we need data with **multiple combined states**:

- A customer with both `PAID` and `CANCELLED` orders.
- A customer with only a `CANCELLED` order.
- A customer with only a `PENDING` order.
- A customer with a `PAID` order.
- A customer **who has never placed an order**.

### 2.1. Diagram

```text
customers                             orders
+-----+------+---------------+        +------+-------------+-----------+--------+
| id  | name | city          |        | id   | customer_id | status    | amount |
+-----+------+---------------+        +------+-------------+-----------+--------+
|  1  | An   | Ho Chi Minh   |<-------| 1001 |      1      | PAID      |  500   |
|     |      |               |<-------| 1002 |      1      | CANCELLED |  100   |
|  2  | Bình | Hanoi         |<-------| 1003 |      2      | CANCELLED |  200   |
|  3  | Chi  | Ho Chi Minh   |<-------| 1004 |      3      | PENDING   |  300   |
|  4  | Dũng | Da Nang       |<-------| 1005 |      4      | PAID      |  400   |
|  5  | Hà   | Hanoi         |        |      |             |           |        |
+-----+------+---------------+        +------+-------------+-----------+--------+

Customer 5: no orders.
Customers 2, 3: have orders, but no PAID orders.
Customers 1, 4: have at least one PAID order.
```

### 2.2. Creating Tables

Connect to a PostgreSQL **lab** database using an account permitted to create schemas and tables:

```sql
CREATE SCHEMA IF NOT EXISTS join144;

CREATE TABLE join144.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE join144.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES join144.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    placed_at timestamptz NOT NULL
);
```

The examples assume `join144.customers` and `join144.orders` **do not yet exist**. If already created earlier, use an isolated lab environment or proper migration; never carelessly wipe data just to re-run.

### 2.3. Inserting Data

```sql
INSERT INTO join144.customers(customer_id, customer_name, city)
VALUES
    (1, 'An',   'Ho Chi Minh City'),
    (2, 'Bình', 'Hanoi'),
    (3, 'Chi',  'Ho Chi Minh City'),
    (4, 'Dũng', 'Da Nang'),
    (5, 'Hà',   'Hanoi');

INSERT INTO join144.orders
    (order_id, customer_id, status, amount, placed_at)
VALUES
    (1001, 1, 'PAID',      500.00, '2026-11-14 09:00:00+07'),
    (1002, 1, 'CANCELLED', 100.00, '2026-11-14 09:30:00+07'),
    (1003, 2, 'CANCELLED', 200.00, '2026-11-14 10:00:00+07'),
    (1004, 3, 'PENDING',   300.00, '2026-11-14 10:30:00+07'),
    (1005, 4, 'PAID',      400.00, '2026-11-14 11:00:00+07');
```

### 2.4. Inspecting Data State

```sql
SELECT customer_id, customer_name, city
FROM join144.customers
ORDER BY customer_id;

SELECT order_id, customer_id, status, amount
FROM join144.orders
ORDER BY order_id;
```

Expected counts are **5 rows** in customers and **5 rows** in orders.

In the result tables throughout this lesson, `NULL` represents a **true NULL value**, not the string literal `'NULL'`. Sort results with `ORDER BY` to inspect them in a consistent order.

## 3. Reviewing LEFT JOIN Semantics Before Adding Conditions

Baseline query:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 1 | An | 1002 | CANCELLED |
| 2 | Bình | 1003 | CANCELLED |
| 3 | Chi | 1004 | PENDING |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

Row count breakdown:

- Customer 1 has 2 orders → contributes **2 rows**.
- Customers 2, 3, and 4 each have 1 order → **3 rows** total.
- Customer 5 has no orders → still contributes **1 row** with NULL order columns.
- Total: **6 rows**.

`LEFT JOIN` preserves all customers, yet **that does not mean it always returns exactly 5 rows**. When a left row matches multiple right rows, the left row appears once for **each matching pair**.

### 3.1. What Is a Null-Extended Row?

The last row:

```text
customer_id = 5
customer_name = Hà
order_id = NULL
status = NULL
```

is not an actual stored order with a NULL ID. It is a **synthetic row produced in the outer join result** representing customer Hà who has no matching order.

We call this **null extension**: PostgreSQL preserves the row from the left table and fills the right-side columns with NULL because no partner matched.

This distinction determines how `WHERE o.status = 'PAID'` behaves.

## 4. Filtering in ON: Changing What Counts as a "Match"

Requirement:

> "Show **all customers**, along with their **PAID orders** if they have any."

Write:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 2 | Bình | NULL | NULL |
| 3 | Chi | NULL | NULL |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

Total: **5 rows**.

### 4.1. Why Does Customer Bình Still Remain?

Customer Bình **has order 1003**, yet that order has status `CANCELLED`. The join condition requires both:

```sql
o.customer_id = c.customer_id
AND o.status = 'PAID'
```

Order 1003 fails the second condition, so it is **not a valid matching row** in this query. Since Bình on the left is preserved and has no PAID orders, PostgreSQL emits one row with NULL order columns.

The same applies to Chi (who only has `PENDING`) and Hà (who has no orders at all).

### 4.2. A Common Misinterpretation to Avoid

The NULL result for Bình and Chi **does not prove these two customers have never placed an order**. It only indicates:

> "There is no order **satisfying the entire ON condition**."

Hence, labeling it "No PAID orders yet" is far more accurate than "No orders yet."

### 4.3. Intuitive Formula

For a given customer `c`:

- If `n > 0` orders satisfy **all of ON**, emit `n` matched rows.
- If zero orders satisfy ON, still emit **one row** for the customer with NULL order columns.

This "keep the left row even when no pair matches" behavior creates the fundamental difference from `WHERE`.

## 5. Same Condition in WHERE: Filtering the Result After LEFT JOIN

Now move `o.status = 'PAID'` from `ON` down to `WHERE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 4 | Dũng | 1005 | PAID |

Only **2 rows** remain.

### 5.1. Why Did Bình and Chi Disappear?

During the join step, they paired with actual order rows:

```text
Bình - 1003 - CANCELLED
Chi  - 1004 - PENDING
```

Then `WHERE o.status = 'PAID'` rejected both rows because the predicate evaluated to FALSE.

### 5.2. Why Did Hà Also Disappear?

Hà has no orders, so LEFT JOIN produced a null-extended row:

```text
Hà - NULL - NULL
```

In SQL:

```sql
NULL = 'PAID'
```

evaluates to **UNKNOWN/NULL**, not TRUE. `WHERE` keeps only rows where the condition evaluates to TRUE, so Hà is discarded too.

### 5.3. Key Takeaway

The following two clauses are **not equivalent**:

```sql
-- A: keep all customers, match only PAID orders
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
```

```sql
-- B: keep only result rows that have a PAID order
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
```

**A** returns all 5 customers; **B** returns only the two customers with at least one PAID order.

Comparison table:

| Customer | Source Order Data | Status Filter in ON | Status Filter in WHERE |
|---|---|---|---|
| An | PAID + CANCELLED | Keep An, match PAID | Keep An, match PAID |
| Bình | CANCELLED only | Keep Bình, NULL order | Drop Bình |
| Chi | PENDING only | Keep Chi, NULL order | Drop Chi |
| Dũng | PAID only | Keep Dũng, match PAID | Keep Dũng, match PAID |
| Hà | No orders | Keep Hà, NULL order | Drop Hà |

## 6. Logical Processing Order: ON, Null Extension, WHERE

A helpful mental model for `LEFT JOIN` is:

```text
         customers                     orders
             |                            |
             +-------- ON ----------------+
                     match pairs
                        |
              For unmatched customers
              add null-extended row
                        |
                      WHERE
                filter JOIN result
                        |
                      SELECT
                        |
                     ORDER BY
```

Walkthrough:

1. Read both input sources.
2. Evaluate `ON` to find **matching pairs**.
3. Since this is a `LEFT JOIN`, add a null-extended row for every unmatched left row.
4. Apply `WHERE` to the rows formed after the join.
5. Run subsequent SQL steps such as grouping, computing output columns, sorting, and limiting.

This is the **logical semantics** for reasoning about output. The PostgreSQL optimizer may organize physical execution steps differently as long as the result honors SQL semantics.

### 6.1. ON and WHERE Differ in More Than Timing

They answer two different questions:

| Clause | Question | Impact on LEFT JOIN |
|---|---|---|
| `ON` | Which right row counts as matching a left row? | Can turn the right columns into NULL, while still keeping the left row |
| `WHERE` | Which result rows are retained after joining? | Can drop the entire left row completely |
| `HAVING` | Which aggregated groups are retained? | Can drop entire groups after GROUP BY |
| `FILTER (WHERE ...)` | Which rows participate in a specific aggregate? | Does not necessarily drop the whole row from the report |

The `WHERE` inside `FILTER (WHERE ...)` belongs to aggregate syntax, not a query-wide `WHERE` filter.

## 7. NULL and Three-Valued Logic Cause WHERE to Drop Rows

PostgreSQL uses three logical states—**TRUE**, **FALSE**, and **UNKNOWN**—when expressions involve NULL.

```sql
SELECT
    ('PAID' = 'PAID') AS match_true,
    ('CANCELLED' = 'PAID') AS match_false,
    (NULL::text = 'PAID') AS unknown_result;
```

Result:

| match_true | match_false | unknown_result |
|---|---|---|
| true | false | NULL |

In `WHERE`:

- TRUE → keep row.
- FALSE → drop row.
- UNKNOWN → drop row.

Hence, the filter:

```sql
WHERE o.status = 'PAID'
```

drops null-extended rows of customers without a PAID order.

### 7.1. What Is a "Null-Rejecting" Predicate?

A predicate is informally called **null-rejecting** for one side when the NULLs introduced by an outer join **can never make that predicate evaluate to TRUE**.

Examples on the `orders` side:

```sql
o.status = 'PAID'
o.amount > 100
o.order_id IS NOT NULL
o.placed_at >= TIMESTAMPTZ '2026-11-14 00:00+07'
```

When no matching order row exists and all order columns become NULL, none of these predicates evaluate to TRUE. Putting them in `WHERE` after a `LEFT JOIN` drops the null-extended rows.

By contrast:

```sql
o.order_id IS NULL
```

**keeps** null-extended rows; that is the foundation of the anti-join pattern.

### 7.2. Not Every WHERE Turns a LEFT JOIN into an INNER JOIN

Consider a condition filtering **customers**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.city = 'Hanoi'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id |
|---:|---|---:|
| 2 | Bình | 1003 |
| 5 | Hà | NULL |

The filter `WHERE c.city = 'Hanoi'` selects customers in Hanoi, and the output still shows that Hà has no orders. No condition demands that order columns be non-NULL.

The key question to ask is: **does this predicate reject null-extended rows on the non-preserved side?**

## 8. Special Case: Filtering the Left Table's Attributes in ON

It is not only conditions on the right table; putting a condition on the **left table** inside `ON` also causes confusion.

Requirement:

> "Report only customers in Ho Chi Minh City, along with their orders."

If you write:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND c.city = 'Ho Chi Minh City'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

the result still contains **every customer**:

| customer_id | customer_name | city | order_id |
|---:|---|---|---:|
| 1 | An | Ho Chi Minh City | 1001 |
| 1 | An | Ho Chi Minh City | 1002 |
| 2 | Bình | Hanoi | NULL |
| 3 | Chi | Ho Chi Minh City | 1004 |
| 4 | Dũng | Da Nang | NULL |
| 5 | Hà | Hanoi | NULL |

Why are Bình, Dũng, and Hà still present?

Because in a `LEFT JOIN`, `c.city = 'Ho Chi Minh City'` **inside ON** only decides whether that customer gets paired with orders. Left-side customers are still preserved even when the city condition is FALSE.

### 8.1. The Right Way to Exclude Customers Outside Ho Chi Minh City

Filter the preserved table in `WHERE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.city = 'Ho Chi Minh City'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The result contains only **An and Chi**: An produces two rows, Chi produces one row.

### 8.2. Combining Both Requirements

Requirement:

> "Only customers in Ho Chi Minh City; among them, show paid orders if any."

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.city = 'Ho Chi Minh City'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 3 | Chi | NULL | NULL |

The separation of concerns is crystal clear:

- `WHERE c.city ...` selects which customers to report on.
- `ON ... AND o.status ...` selects which orders are eligible to join.
- `LEFT JOIN` still preserves Chi even without a PAID order.

## 9. The "OR o.order_id IS NULL" Trap Is Not Always Equivalent to Filtering in ON

A common flawed workaround:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
   OR o.order_id IS NULL
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The author hopes to "get PAID orders while keeping customers without PAID orders." Yet the result is:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

**Bình and Chi still vanish**.

### 9.1. Why?

Distinguish the two cases:

- **No orders at all:** Hà → LEFT JOIN generates a NULL row → `o.order_id IS NULL` is TRUE.
- **Has orders, none of which are PAID:** Bình/Chi → LEFT JOIN pairs them with **real order rows**; there is no null-extended row → both `status = 'PAID'` and `order_id IS NULL` are FALSE.

Therefore, `WHERE o.status='PAID' OR o.order_id IS NULL` is not equivalent to:

```sql
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
```

With the condition in ON, Bình and Chi **have no matching PAID pair**, so each receives a null-extended row. That is the single most important distinction in this lesson.

### 9.2. Rule for Using OR ... IS NULL

Only use the pattern:

```sql
WHERE o.status = 'PAID'
   OR o.order_id IS NULL
```

when the **exact business rule** is:

> "Customers with a PAID order, plus customers with **no orders at all**; exclude customers who only have orders in other statuses."

Never use it as a general trick to turn a WHERE filter into an ON filter.

## 10. Filtering Inside a Right-Side Subquery: An Explicit Alternative

Conditions on the right table can also be placed inside a pre-filtered source:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN (
    SELECT order_id, customer_id, status
    FROM join144.orders
    WHERE status = 'PAID'
) AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

The result matches:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id;
```

Both keep **all customers** and match only PAID orders.

### 10.1. Using a CTE for Clarity

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, status
    FROM join144.orders
    WHERE status = 'PAID'
)
SELECT
    c.customer_id,
    c.customer_name,
    p.order_id
FROM join144.customers AS c
LEFT JOIN paid_orders AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id, p.order_id NULLS LAST;
```

This clearly expresses **"the right source contains only PAID orders"** before performing the join.

Depending on PostgreSQL version, reference count, and CTE attributes, the optimizer may inline or materialize CTEs per its rules. Do not assume a CTE is always faster or slower; here we choose it for **readability and semantic accuracy**.

### 10.2. When Should You Filter Each Source Before a FULL JOIN?

For `FULL JOIN`, **both sides are preserved**. If you want to reconcile "qualifying rows" from **both sources**, filtering each source inside its own subquery/CTE **before the FULL JOIN** is usually much clearer than adding a shared `WHERE` filter afterward. Section 16 illustrates this.

## 11. Counting Orders: COUNT(*) and COUNT(o.order_id) Are Not the Same

Requirement:

> "List every customer and their PAID order count; customers with no PAID orders must show 0."

Use `LEFT JOIN` with the condition in `ON`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name | paid_order_count |
|---:|---|---:|
| 1 | An | 1 |
| 2 | Bình | 0 |
| 3 | Chi | 0 |
| 4 | Dũng | 1 |
| 5 | Hà | 0 |

### 11.1. Why Use COUNT(o.order_id)?

For customers without a PAID order, `LEFT JOIN` emits **one null-extended row**. Therefore:

- `COUNT(*)` counts that row as **1**.
- `COUNT(o.order_id)` ignores NULL values and returns **0**.

Verify directly:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_row_count,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Result:

| customer_id | joined_row_count | paid_order_count |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 1 | 0 |
| 3 | 1 | 0 |
| 4 | 1 | 1 |
| 5 | 1 | 0 |

If customer 1 had three PAID orders, both counters for customer 1 would be 3; for customer 2 with no PAID orders, `COUNT(*)` stays 1.

### 11.2. Putting the Status Filter in WHERE Drops Customer Groups

Writing:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

returns only customer groups 1 and 4. Customers 2, 3, and 5 **do not appear with 0**, because `WHERE` removed them prior to `GROUP BY`.

This is a classic dashboard bug: charts omit zero-count buckets even though the business expects a complete breakdown.

## 12. Aggregate FILTER: Counting Multiple Statuses in One Report

If you need **total orders, PAID orders, and CANCELLED orders** for every customer, keep all orders in `ON` and apply `FILTER` per aggregate:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PAID'
    ) AS paid_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'CANCELLED'
    ) AS cancelled_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PENDING'
    ) AS pending_orders
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Result:

| Customer | Total | PAID | CANCELLED | PENDING |
|---|---:|---:|---:|---:|
| An | 2 | 1 | 1 | 0 |
| Bình | 1 | 0 | 1 | 0 |
| Chi | 1 | 0 | 0 | 1 |
| Dũng | 1 | 1 | 0 | 0 |
| Hà | 0 | 0 | 0 | 0 |

### 12.1. FILTER (WHERE ...) Is Not a Query-Wide WHERE

In the syntax:

```sql
COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
```

the condition controls only **which rows contribute to that specific COUNT aggregate**; it never removes the customer from the group.

That is why `FILTER` is especially helpful for "keep all groups while computing multiple conditional metrics" reports.

### 12.2. When You Only Need Total PAID Amount

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_amount
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Expected result:

| customer_id | paid_amount |
|---:|---:|
| 1 | 500.00 |
| 2 | 0 |
| 3 | 0 |
| 4 | 400.00 |
| 5 | 0 |

Note that `SUM` over a group with no qualifying values returns NULL, so `COALESCE(...,0)` is used when the report expects 0. If the business needs to distinguish "no data yet" from "sum is 0," preserve NULL semantics.

## 13. Anti-Join: "No Rows Matching a Condition"

There are two different questions:

1. Which customers **have never placed any order**?
2. Which customers **have no PAID orders**, even if they have orders in other statuses?

### 13.1. Never Placed Any Order

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Result: only **Hà (5)**.

Because `order_id` is a NOT NULL primary key, `o.order_id IS NULL` after the join proves **no actual orders row matched**.

### 13.2. Have No PAID Orders at All

Put the `PAID` condition in `ON`, then find rows without a PAID partner:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name |
|---:|---|
| 2 | Bình |
| 3 | Chi |
| 5 | Hà |

Bình has a CANCELLED order, Chi has a PENDING order, and Hà has no orders; **all three have no PAID order**.

### 13.3. Writing with NOT EXISTS

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

The result is also Bình, Chi, and Hà.

The `NOT EXISTS` pattern directly expresses **"no PAID order exists for this customer"** without relying on null-extended rows. The PostgreSQL optimizer can often use an **anti-join** node in the plan when appropriate.

### 13.4. Why Not Pick an Arbitrary Column to Check for NULL?

The pattern:

```sql
WHERE o.order_id IS NULL
```

works because `order_id` is the primary key—a real row cannot have a NULL `order_id`.

If replaced with:

```sql
WHERE o.some_nullable_field IS NULL
```

the query could also pick up matched orders where `some_nullable_field` happens to be NULL. Therefore, to detect "no partner," always check a **guaranteed NOT NULL column on the other table** or use `NOT EXISTS`.

## 14. RIGHT JOIN: ON and WHERE Share the Exact Same Difference

`RIGHT JOIN` preserves all rows on the **right side**. You can view:

```sql
A RIGHT JOIN B ON ...
```

as having the same expressive power as:

```sql
B LEFT JOIN A ON ...
```

after swapping table order and adjusting the SELECT list/conditions.

### 14.1. Requirement: All Customers, PAID Orders If Any

Written with `RIGHT JOIN`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The result still has **all 5 customers**: An 1001; Bình NULL; Chi NULL; Dũng 1005; Hà NULL.

The **right** table is `customers`, so it is preserved even without matching PAID orders.

### 14.2. Moving the Order Filter to WHERE

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Only An and Dũng remain, identical to filtering the non-preserved side in `WHERE` under a LEFT JOIN.

### 14.3. Putting the Preserved Table's Condition in ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
   AND c.city = 'Ho Chi Minh City'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The city condition in ON **does not remove customers in Hanoi or Da Nang** from the result, because they are on the preserved right side. It merely prevents customers outside Ho Chi Minh City from joining any orders in this query.

To keep only customers in Ho Chi Minh City, place:

```sql
WHERE c.city = 'Ho Chi Minh City'
```

at the end of the query.

### 14.4. Rule When Reading RIGHT JOIN

Do not memorize mechanically "right-table conditions go in WHERE." Remember:

- **The right table is preserved** in a RIGHT JOIN.
- A filter on the **non-preserved left table** placed in WHERE can drop null-extended right rows.
- A filter on the right table placed in ON does not necessarily drop right rows.

It is completely symmetric to LEFT JOIN, simply flipping which side is preserved.

## 15. FULL JOIN: Both Sides Are Preserved in ON

`FULL JOIN` preserves:

1. All **matching pairs** under ON.
2. Rows **only on the left**.
3. Rows **only on the right**.

Because both sides can generate null-extended rows, moving a filter between `ON` and `WHERE` in a FULL JOIN creates even subtler differences.

### 15.1. Independent Reconciliation Dataset

Create two simple inventory sources. They intentionally **have no foreign keys to each other**, because the goal is to find SKUs present on only one side.

```sql
CREATE TABLE join144.erp_inventory (
    sku text PRIMARY KEY,
    erp_qty integer NOT NULL,
    approved boolean NOT NULL
);

CREATE TABLE join144.wms_inventory (
    sku text PRIMARY KEY,
    wms_qty integer NOT NULL,
    verified boolean NOT NULL
);

INSERT INTO join144.erp_inventory(sku, erp_qty, approved)
VALUES
    ('A', 10, TRUE),
    ('B', 20, FALSE),
    ('C', 30, TRUE);

INSERT INTO join144.wms_inventory(sku, wms_qty, verified)
VALUES
    ('B', 20, TRUE),
    ('C', 35, FALSE),
    ('D', 40, TRUE);
```

### 15.2. Basic FULL JOIN

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
ORDER BY COALESCE(e.sku, w.sku);
```

Result:

| erp_sku | erp_qty | wms_sku | wms_qty |
|---|---:|---|---:|
| A | 10 | NULL | NULL |
| B | 20 | B | 20 |
| C | 30 | C | 35 |
| NULL | NULL | D | 40 |

There are **4 rows**: A left-only; B and C matched; D right-only.

### 15.3. Adding a Condition in ON

Suppose we consider WMS a **valid match** only when the WMS row is verified:

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty,
    w.verified
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
   AND w.verified = TRUE
ORDER BY COALESCE(e.sku, w.sku),
         e.sku NULLS LAST;
```

Key observations:

- B has `verified = TRUE`, so it still joins into one B–B row.
- C has `verified = FALSE`, so it **does not count as a match**.
- Because FULL JOIN preserves both sides, the ERP row for SKU C **still appears on its own**, and the WMS row for SKU C **also appears on its own**.
- ERP-only A and WMS-only D still appear.

The result has **5 rows**: A left-only; B matched; C left-only; C right-only; D right-only.

This behaves very differently from LEFT JOIN: adding a condition in ON can split a previously matched pair into **two unmatched single-sided rows**, because both sides are preserved.

### 15.4. Moving the Condition to WHERE

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty,
    w.verified
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE w.verified = TRUE
ORDER BY COALESCE(e.sku, w.sku);
```

Result:

| erp_sku | erp_qty | wms_sku | wms_qty | verified |
|---|---:|---|---:|---|
| B | 20 | B | 20 | true |
| NULL | NULL | D | 40 | true |

Here:

- A is dropped because `w.verified` is NULL.
- C is dropped because WMS has `verified = FALSE`.
- B and D are kept.

**FULL JOIN still appears in the SQL text, yet WHERE eliminated rows from one or both preserved groups.**

### 15.5. When Is the Filter in ON Correct?

If the requirement is:

> "Reconcile all ERP and WMS records, but treat two rows as matching only when WMS is verified."

putting `w.verified = TRUE` in `ON` can be right. The unverified WMS record still appears **separately** so reviewers can spot it.

If the requirement is:

> "Report only result rows that have a verified WMS record."

the condition in `WHERE` may be right, though it no longer preserves both sources in full.

If the requirement is:

> "First select only qualifying records from each system, then reconcile both filtered lists in full."

then **filtering each source prior to the FULL JOIN** is usually the clearest design.

## 16. Filtering Each Source Before FULL JOIN to Preserve Both Selected Sets

Example considering only approved ERP and verified WMS records:

```sql
WITH approved_erp AS (
    SELECT sku, erp_qty
    FROM join144.erp_inventory
    WHERE approved IS TRUE
),
verified_wms AS (
    SELECT sku, wms_qty
    FROM join144.wms_inventory
    WHERE verified IS TRUE
)
SELECT
    COALESCE(e.sku, w.sku) AS sku,
    e.erp_qty,
    w.wms_qty,
    CASE
        WHEN e.sku IS NULL THEN 'ONLY_WMS'
        WHEN w.sku IS NULL THEN 'ONLY_ERP'
        WHEN e.erp_qty IS DISTINCT FROM w.wms_qty THEN 'QTY_DIFF'
        ELSE 'MATCH'
    END AS match_status
FROM approved_erp AS e
FULL JOIN verified_wms AS w
    ON e.sku = w.sku
ORDER BY sku;
```

After filtering:

- Approved ERP: A, C.
- Verified WMS: B, D.

These two lists share **no SKUs**, so FULL JOIN returns four single-sided rows:

| sku | erp_qty | wms_qty | match_status |
|---|---:|---:|---|
| A | 10 | NULL | ONLY_ERP |
| B | NULL | 20 | ONLY_WMS |
| C | 30 | NULL | ONLY_ERP |
| D | NULL | 40 | ONLY_WMS |

Do not confuse this with the FULL JOIN in section 15.3, where unverified WMS C **was still preserved** as an unmatched row.

### 16.1. Three Placements Corresponding to Three Requirements

| Query Form | Dominant Semantics |
|---|---|
| `FULL JOIN ... ON e.sku=w.sku AND w.verified` | Both raw sources are kept; only pairs meeting all of ON are joined |
| `FULL JOIN ... ON e.sku=w.sku WHERE w.verified` | Join by SKU first, then keep only result rows with verified WMS |
| `FROM (filtered ERP) FULL JOIN (filtered WMS)` | Select each desired source set first, then preserve both selected sets |

This is why there is no universal rule like "put all FULL JOIN conditions in ON" or "put all filters in WHERE." **Business semantics dictate placement**, not syntax habits.

## 17. Classifying Unmatched Rows in FULL JOIN

To find SKUs appearing in only one source:

```sql
SELECT
    e.sku AS erp_sku,
    w.sku AS wms_sku
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL
   OR w.sku IS NULL
ORDER BY COALESCE(e.sku, w.sku);
```

Result: **A in ERP only** and **D in WMS only**.

The `sku` key in each table is `PRIMARY KEY NOT NULL`, so:

- `e.sku IS NULL` means no ERP row matched.
- `w.sku IS NULL` means no WMS row matched.

### 17.1. Only ERP Rows Missing from WMS

```sql
SELECT e.sku, e.erp_qty
FROM join144.erp_inventory AS e
LEFT JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE w.sku IS NULL
ORDER BY e.sku;
```

Result: A.

### 17.2. Only WMS Rows Missing from ERP

```sql
SELECT w.sku, w.wms_qty
FROM join144.erp_inventory AS e
RIGHT JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL
ORDER BY w.sku;
```

Result: D.

You can write this more clearly as `wms_inventory w LEFT JOIN erp_inventory e` with `WHERE e.sku IS NULL`.

### 17.3. Why Classify Using a NOT NULL Key?

Do not use:

```sql
WHERE e.some_nullable_column IS NULL
```

to conclude "ERP record does not exist," because an ERP record may exist with that optional column set to NULL.

When classifying `MATCHED`, `LEFT_ONLY`, and `RIGHT_ONLY` in a `FULL JOIN`, always use a **guaranteed NOT NULL key from each source** or a reliable marker.

## 18. Chaining Multiple LEFT JOINs: WHERE on the Third Table Can Drop the First Table's Rows

In a real-world report:

```text
customers LEFT JOIN orders LEFT JOIN payments
```

A `WHERE` condition on `payments` can erase not only orders, but also **customers** from the first outer join.

### 18.1. Creating the Payments Table

```sql
CREATE TABLE join144.payments (
    payment_id bigint PRIMARY KEY,
    order_id bigint NOT NULL UNIQUE
        REFERENCES join144.orders(order_id),
    payment_status text NOT NULL
        CHECK (payment_status IN ('SETTLED', 'FAILED'))
);

INSERT INTO join144.payments
    (payment_id, order_id, payment_status)
VALUES
    (9001, 1001, 'SETTLED'),
    (9002, 1003, 'FAILED'),
    (9003, 1005, 'SETTLED');
```

### 18.2. Easy Bug: WHERE on the Final Table

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    p.payment_status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join144.payments AS p
    ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED'
ORDER BY c.customer_id;
```

Result is only:

| customer_id | customer_name | order_id | payment_status |
|---:|---|---:|---|
| 1 | An | 1001 | SETTLED |
| 4 | Dũng | 1005 | SETTLED |

If the requirement is "all customers, with settled payment if any," the query above is **wrong** because the final filter drops customers without a SETTLED payment.

### 18.3. Putting the Payment Condition in ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    p.payment_status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join144.payments AS p
    ON p.order_id = o.order_id
   AND p.payment_status = 'SETTLED'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

This keeps all customers, yet **also keeps orders without a SETTLED payment**. For instance:

- An has order 1001 with SETTLED, and order 1002 with NULL payment.
- Bình has order 1003 with NULL payment because FAILED fails ON.
- Chi has order 1004 with NULL payment.
- Dũng has 1005 with SETTLED.
- Hà has NULL for both order and payment.

This is right when you want to see **all orders** and only attach SETTLED payments.

### 18.4. Want to Join Only Orders with a SETTLED Payment While Still Keeping All Customers?

You must define "qualifying orders" **before the first JOIN**. Use a subquery/CTE combining orders + payments:

```sql
WITH settled_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        p.payment_id
    FROM join144.orders AS o
    INNER JOIN join144.payments AS p
        ON p.order_id = o.order_id
       AND p.payment_status = 'SETTLED'
)
SELECT
    c.customer_id,
    c.customer_name,
    s.order_id,
    s.payment_id
FROM join144.customers AS c
LEFT JOIN settled_orders AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id, s.order_id NULLS LAST;
```

The result includes all **5 customers**, matching only orders 1001 and 1005; Bình, Chi, and Hà have NULL order columns.

**This is not the same** as `LEFT JOIN orders` first and filtering payments in the last `ON`. The two requirements differ:

- "All orders, with settled payment if any" → two-level LEFT JOIN with payment filter in the final ON.
- "Only orders with settled payment, while still showing all customers" → filter/build `settled_orders` first, then LEFT JOIN.

## 19. When FULL/LEFT JOIN Uses Non-Equality Conditions

`ON` is not restricted to `a.id = b.id`. PostgreSQL allows conditions using time ranges, numeric thresholds, string matching, or other suitable expressions.

For example, finding the active promotional price when an order was placed:

```sql
-- Illustrative template; promotion tables must be created separately.
SELECT
    o.order_id,
    p.promotion_name
FROM orders AS o
LEFT JOIN promotions AS p
    ON p.product_id = o.product_id
   AND o.placed_at >= p.valid_from
   AND o.placed_at < p.valid_to;
```

Above, the three conditions in ON determine **an eligible promotion matching the order**. For orders with no valid promotion, LEFT JOIN still keeps the order and fills NULL for promotion columns.

If you move:

```sql
WHERE o.placed_at >= p.valid_from
  AND o.placed_at < p.valid_to
```

to the end, orders without promotions are dropped because comparisons against NULL are not TRUE. It is the exact same ON/WHERE principle, **independent of the `=` operator**.

The `orders`/`promotions` tables here are business templates, not tables created in the `join144` lab schema.

### 19.1. Using a Range Operator in ON

In PostgreSQL, a model can use range types:

```sql
-- Illustrative template when promotions.valid_period is tstzrange:
SELECT
    o.order_id,
    p.promotion_id
FROM orders AS o
LEFT JOIN promotions AS p
    ON p.product_id = o.product_id
   AND p.valid_period @> o.placed_at;
```

The `@>` predicate goes in ON because it determines **whether the promotion was active when the order was placed**. Orders without promotions are still preserved.

## 20. When Can a Predicate Move Between ON and WHERE?

Not every condition behaves differently. You need semantic justification.

### 20.1. With INNER JOIN

The following two queries yield equivalent row sets for this simple predicate:

```sql
SELECT c.customer_id, o.order_id
FROM join144.customers AS c
INNER JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

```sql
SELECT c.customer_id, o.order_id
FROM join144.customers AS c
INNER JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Because INNER JOIN generates no null-extended rows to preserve either table, both keep only pairs satisfying all conditions.

However, when a query involves additional outer joins, subqueries, aggregates, window functions, volatile expressions, or other join semantics, examine **every expression's exact scope** rather than extrapolating mechanically from two simple INNER JOIN queries.

### 20.2. With LEFT JOIN and a Predicate Depending Only on the Right Table

Normally:

```sql
LEFT JOIN B ON A.key=B.key AND B.flag=TRUE
```

is **not equivalent** to:

```sql
LEFT JOIN B ON A.key=B.key
WHERE B.flag=TRUE
```

because the second query can drop rows of A that lack a qualifying partner.

### 20.3. With LEFT JOIN and a Predicate Depending Only on the Left Table

Normally:

```sql
LEFT JOIN B ON A.key=B.key AND A.region='VN'
```

is **not equivalent** to:

```sql
LEFT JOIN B ON A.key=B.key
WHERE A.region='VN'
```

because in the first query, all rows of A are still kept; in the second, rows of A outside the region are dropped.

### 20.4. With FULL JOIN

Both sides are preserved, so putting a predicate depending only on A or B in ON **does not necessarily drop rows of that side**. It can split a matched pair into two unmatched rows.

Conversely, a `WHERE` requiring A/B columns to meet a condition can drop the very unmatched rows that FULL JOIN just preserved.

### 20.5. General Rule for Choosing Placement

State the goal in plain words:

- "Only **attach** B rows meeting a condition, while A always appears" → put B's condition in the LEFT JOIN's `ON`.
- "Only **keep** A rows meeting a condition" → put in `WHERE` on A, or pre-filter source A.
- "Only **keep pairs** meeting a condition" → `INNER JOIN` or trailing `WHERE` depending on the query.
- "Only **reconcile subsets** of each source" → filter each source prior to `FULL JOIN`.
- "Only **find A without a qualifying B**" → put B's condition in `ON` with `WHERE B.pk IS NULL`, or use `NOT EXISTS`.

Never move conditions just to make SQL look shorter.

## 21. EXPLAIN: PostgreSQL Can Optimize a LEFT JOIN into an INNER JOIN

Crucially, a query written with `LEFT JOIN` **is not guaranteed to always show a "Left Join" node in the execution plan**.

Example:

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Because `WHERE o.status = 'PAID'` **rejects every null-extended row** from orders, PostgreSQL can prove that the LEFT JOIN does not need to keep unmatched left rows and **rewrites it into an equivalent inner join** in the plan.

This is a completely valid SQL optimization. PostgreSQL is not "ignoring" your join; it recognized that the trailing filter renders left-preservation irrelevant to the output.

### 21.1. Filtering in ON Cannot Be Simplified the Same Way

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Here, customers without PAID orders **must be preserved**, so the optimizer cannot convert it into an inner join that drops them.

Still, PostgreSQL can reorder joins where legal, choose Hash/Merge/Nested Loop, or push safe predicates down to the right source. Do not expect plan node names to mirror SQL keywords literally in every case.

### 21.2. Checking Performance with EXPLAIN ANALYZE

In the lab database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

`ANALYZE` **executes the query**, so run it only on lab SELECTs or with proper safeguards when queries have side effects. The sample tables are tiny, so the planner may rightly choose sequential scans instead of indexes.

### 21.3. Indexes Supporting Join Conditions

For workloads fetching orders by customer and status:

```sql
CREATE INDEX idx_join144_orders_customer_status
ON join144.orders(customer_id, status);
```

Or if most queries care only about PAID orders, consider a partial index:

```sql
CREATE INDEX idx_join144_orders_paid_customer
ON join144.orders(customer_id)
WHERE status = 'PAID';
```

A partial index helps queries whose predicate is explicit enough for the planner to prove eligibility. Not every query or parameterized variant can leverage it.

Most importantly: **place conditions in ON/WHERE for correctness first**, then optimize. Never alter report semantics hoping to hit an index faster.

## 22. When NULL Parameters or Dynamic Filters Appear

Applications often let users pick an order status or leave the filter blank. A confusing pattern:

```sql
WHERE o.status = :selected_status
   OR :selected_status IS NULL
```

`:selected_status` is a framework placeholder, **not native PostgreSQL parameter syntax when executed directly in psql**.

If the parameter is NULL, the predicate becomes TRUE and keeps null-extended rows too. If the parameter is `PAID`, it drops customers without PAID orders. That means **toggling the filter changes the set of customers returned**.

### 22.1. When the Requirement Must Always Keep All Customers

Put the order status condition inside `ON`:

```sql
-- Prepared statement template; $1 is a text parameter.
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND ($1::text IS NULL OR o.status = $1::text)
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

With parameter `PAID`, the query keeps all customers and matches only PAID orders.

With parameter NULL, the condition is TRUE for every order of the customer, so it matches all orders—**no longer one row per customer**. Confirm this with your API design; sometimes a report needs two distinct queries or aggregation if exactly one row per customer is required.

### 22.2. Avoid Concatenating User Input into SQL

In JDBC, use `PreparedStatement` to bind the status value; never concatenate strings like:

```text
"... ON ... AND o.status = '" + userInput + "'"
```

Direct string concatenation introduces SQL injection risks and escaping bugs. Predicates still belong in the right clause even after parameterization; **parameterization and OUTER JOIN semantics are two independent concerns**.

## 23. Pagination with LEFT JOIN: One Customer Having Multiple Orders

A query like:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST
LIMIT 3;
```

limits to **3 post-JOIN result rows**, not "3 customers."

In the sample data, An has 2 orders, so the top three rows are:

```text
An - 1001
An - 1002
Bình - 1003
```

Only two distinct customers appear across the 3 result rows.

### 23.1. To Paginate by Customer

Select the page of customers first, then join:

```sql
WITH page_customers AS (
    SELECT
        customer_id,
        customer_name
    FROM join144.customers
    ORDER BY customer_id
    LIMIT 3 OFFSET 0
)
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM page_customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The first page selects customers 1, 2, and 3, then LEFT JOIN retains all three—one with a PAID order, two without.

The PAID condition sits in ON so the customer page loses nobody.

### 23.2. Counting Total Customers for Pagination

If the API wants `total_customers`, count from the qualifying customer source rather than defaulting to:

```sql
SELECT COUNT(*)
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id;
```

Because of the one-to-many join, `COUNT(*)` here returns **6** instead of **5** customers. To count customers:

```sql
SELECT COUNT(*) AS total_customers
FROM join144.customers;
```

Or count from the filtered customer set. Never rely on `COUNT(DISTINCT c.customer_id)` just to paper over design issues; define the report's grain clearly.

## 24. Multi-Tenant: Tenant Condition in ON Can Still Leak Left Rows

In multi-tenant applications, misplacing a filter can cause not only wrong reports but **data leaks**.

Suppose two tables are shared across organizations:

```text
customers(tenant_id, customer_id, ...)
orders(tenant_id, order_id, customer_id, ...)
```

A dangerous query:

```sql
-- Wrong if the goal is to return only customers of the authenticated tenant.
SELECT c.customer_id, c.customer_name, o.order_id
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
   AND o.tenant_id = $1;
```

Problems:

1. No `c.tenant_id` filter on the left table.
2. Because it is a LEFT JOIN, **every customer of every tenant** is preserved, merely with NULL order columns.
3. The join condition also lacks the customer's tenant ID, so if `customer_id` is unique only per tenant, an order could match a customer from another tenant.

A clearer pattern:

```sql
-- $1 is the authenticated and authorized tenant_id.
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.tenant_id = $1;
```

This query separates three concerns:

- `WHERE c.tenant_id = $1` restricts **which customers are returned**.
- `ON o.tenant_id = c.tenant_id AND ...` enforces same-tenant integrity.
- `AND o.status = 'PAID'` in ON picks qualifying orders while keeping all customers of that tenant.

Still, **never rely solely on WHERE** to protect data: enforce tenant authentication, application authorization, composite keys, and Row-Level Security (RLS) where appropriate. RLS is an additional safeguard; table owners, superusers, and roles with `BYPASSRLS` have important exceptions.

The `app.customers`/`app.orders` tables here are architectural templates; they are not created in the `join144` lab schema.

## 25. Outer Joins, Views, and Outer-Layer Filters

Suppose you create a view reporting all customers and their PAID orders:

```sql
CREATE VIEW join144.customer_paid_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

When reading:

```sql
SELECT *
FROM join144.customer_paid_orders
ORDER BY customer_id;
```

the view retains every customer.

However, a consumer of the view might add a filter:

```sql
SELECT *
FROM join144.customer_paid_orders
WHERE order_id IS NOT NULL
ORDER BY customer_id;
```

Now only customers with PAID orders remain. That does not contradict the view definition: the **outer query's** filter is applied to the view's logical output.

### 25.1. Designing Views with a Clear Contract

The view name and documentation should clarify:

- Does it include **all customers** or only customers with orders?
- Is it **one row per customer** or one row per order?
- Does NULL in order columns mean **no PAID order**, or "no order at all"?
- Does the view apply appropriate authorization/RLS?

A view containing a LEFT JOIN cannot force outer queries to keep all customers; callers must still understand its semantics and avoid outer filters that inadvertently drop rows.

## 26. Common Mistakes and How to Fix Them

### Mistake 1 — Moving a Right-Table Condition Down to WHERE

```sql
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
```

Drops customers who have no PAID orders.

**Fix:** to preserve all customers, put `o.status='PAID'` in `ON` or pre-filter the orders source before LEFT JOINing.

### Mistake 2 — Thinking OR o.id IS NULL Solves Every Case

```sql
WHERE o.status = 'PAID' OR o.order_id IS NULL
```

keeps only customers with a PAID order or **no orders at all**, dropping customers who only have non-PAID orders.

**Fix:** verify exact requirements; put the predicate in `ON` when all customers must remain.

### Mistake 3 — Putting a Left-Table Condition in ON to Filter the Left Table

```sql
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND c.city = 'Hanoi'
```

does not exclude customers outside Hanoi.

**Fix:** use `WHERE c.city='Hanoi'` or pre-filter source `c`.

### Mistake 4 — Counting Null-Extended Rows with COUNT(*)

With `LEFT JOIN`, a customer with no PAID order still has one row, so `COUNT(*)` returns 1.

**Fix:** use `COUNT(o.order_id)` when `order_id` is a NOT NULL key.

### Mistake 5 — Using a Nullable Column to Detect Non-Matches

`WHERE o.optional_note IS NULL` can match real orders whose note happens to be NULL.

**Fix:** check a NOT NULL primary key or use `NOT EXISTS`.

### Mistake 6 — Thinking a FULL JOIN ON Filter Removes Disqualified Rows

In a FULL JOIN, a WMS row failing an ON predicate **can still appear on its own**, because the WMS side is also preserved.

**Fix:** to exclude invalid WMS rows from the **input set**, filter the WMS table in a CTE/subquery before the FULL JOIN.

### Mistake 7 — Adding a One-Sided WHERE After FULL JOIN While Expecting Both Sources Preserved

`WHERE w.verified=TRUE` drops ERP-only rows because `w.verified` is NULL.

**Fix:** depending on business rules, pre-filter each source before FULL JOIN or classify with `CASE`.

### Mistake 8 — Thinking RIGHT JOIN Can Be Flipped to LEFT JOIN Without Swapping Tables

`orders RIGHT JOIN customers` equals `customers LEFT JOIN orders`, not `orders LEFT JOIN customers`.

**Fix:** identify the **preserved** side accurately.

### Mistake 9 — Misusing NOT IN to Find Missing Rows

`NOT IN (subquery)` can fail logically whenever the subquery contains NULL.

**Fix:** use `NOT EXISTS` or `LEFT JOIN ... IS NULL` on a NOT NULL key.

### Mistake 10 — Failing to Distinguish "No Orders" from "No PAID Orders"

Those two questions correspond to two distinct anti-join predicates.

**Fix:** the order status filter must live **inside the existence scope**, such as in `ON` or the `NOT EXISTS` subquery.

### Mistake 11 — Chaining Multiple LEFT JOINs Then Filtering the Final Table in WHERE

A `WHERE p.payment_status='SETTLED'` drops customers even though the initial `customers LEFT JOIN orders` preserved them.

**Fix:** clarify which relation set should be joined and pre-filter eligible sources first.

### Mistake 12 — Confusing JOIN Row Count with Customer Count During Pagination

`LIMIT 10` after a JOIN limits to **10 result rows**, which may belong to only a handful of customers.

**Fix:** paginate the customer set first, then JOIN related orders.

### Mistake 13 — Omitting the Tenant Key from the Join Condition

`o.customer_id=c.customer_id` is insufficient when IDs are unique only per tenant.

**Fix:** include `o.tenant_id=c.tenant_id` in `ON` and restrict the left table in `WHERE` to the authenticated tenant.

### Mistake 14 — Adding DISTINCT to "Fix" Duplicated Rows

One-to-many joins generate multiple valid pairs. `DISTINCT` can hide bugs or collapse rows that look identical yet differ fundamentally.

**Fix:** define the report's grain and aggregate at the proper level.

### Mistake 15 — Assuming ON Physically Executes Before WHERE in a Fixed Order

The `ON → null extension → WHERE` flow is **logical semantics**; the optimizer may rewrite and push predicates down when valid.

**Fix:** inspect `EXPLAIN` rather than assuming every execution plan mirrors SQL clause order literally.

### Mistake 16 — Misparenthesizing AND/OR Conditions

```sql
ON o.customer_id = c.customer_id
AND o.status = 'PAID'
OR o.amount > 1000
```

By operator precedence, this is parsed as:

```sql
ON (
    o.customer_id = c.customer_id
    AND o.status = 'PAID'
)
OR o.amount > 1000
```

The `OR o.amount > 1000` branch can join orders to **unrelated** customers whenever the amount exceeds the threshold.

**Fix:**

```sql
ON o.customer_id = c.customer_id
AND (
    o.status = 'PAID'
    OR o.amount > 1000
)
```

`AND`/`OR` precedence is part of defining **matching row pairs**; missing parentheses can cause mass cross-pairing of data.

## 27. Practice Exercises with Solutions

The exercises use the lab datasets from sections 2 and 15.

### Exercise 1 — All Customers, PAID Orders If Any

**Requirement:** return all 5 customers, with `order_id` NULL if they have no PAID order.

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id;
```

**Answer:** An 1001; Bình NULL; Chi NULL; Dũng 1005; Hà NULL.

### Exercise 2 — Only Customers with PAID Orders

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id;
```

**Answer:** An 1001 and Dũng 1005.

### Exercise 3 — Only Customers Without a PAID Order

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Answer:** Bình, Chi, Hà.

### Exercise 4 — Only Customers Without Any Orders

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

**Answer:** Hà.

### Exercise 5 — Hanoi Customers, PAID Orders If Any

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.city = 'Hanoi'
ORDER BY c.customer_id;
```

**Answer:** Bình NULL, Hà NULL.

### Exercise 6 — Does Putting city in ON Filter Out Non-Hanoi Customers?

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND c.city = 'Hanoi'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

**Solution:** no. All 5 customers still appear. Bình has CANCELLED order 1003, so it joins; Hà has no orders; An, Chi, and Dũng are outside Hanoi, so their order columns are NULL.

### Exercise 7 — Count PAID Orders While Keeping Customers with 0

```sql
SELECT c.customer_id,
       COUNT(o.order_id) AS paid_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Answer:** customer 1→1; 2→0; 3→0; 4→1; 5→0.

### Exercise 8 — Count Both PAID and CANCELLED on the Same Row

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id)
      FILTER (WHERE o.status='PAID') AS paid_count,
    COUNT(o.order_id)
      FILTER (WHERE o.status='CANCELLED') AS cancelled_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Answer:** An (1,1), Bình (0,1), Chi (0,0), Dũng (1,0), Hà (0,0).

### Exercise 9 — FULL JOIN, SKUs Existing in Only One Source

```sql
SELECT e.sku AS erp_sku, w.sku AS wms_sku
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL OR w.sku IS NULL
ORDER BY COALESCE(e.sku, w.sku);
```

**Answer:** A in ERP only, D in WMS only.

### Exercise 10 — Why Does the WMS Condition in ON Not Drop C?

When:

```sql
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
   AND w.verified = TRUE
```

SKU C has `verified = FALSE` in WMS.

**Solution:** C is not treated as a matched pair, yet **both sources are preserved by FULL JOIN**, so ERP's row C and WMS's row C appear **separately**.

### Exercise 11 — Fixing the Query That Lost Customers Due to Payments

Require all customers, joining only orders with a SETTLED payment.

**Solution:** build `settled_orders` via `INNER JOIN orders–payments ON p.order_id=o.order_id AND p.payment_status='SETTLED'`, then `customers LEFT JOIN settled_orders`. The result keeps all 5 customers.

### Exercise 12 — Why Did WHERE Drop Chi?

```sql
LEFT JOIN join144.orders o ON o.customer_id=c.customer_id
WHERE o.status='PAID'
```

**Solution:** Chi has a PENDING order, so the matched row is dropped by WHERE; there is no null-extended fallback because LEFT JOIN already found a partner before filtering.

### Exercise 13 — When to Use NOT EXISTS Instead of an Anti-Join?

**Solution:** when the requirement is "no B exists satisfying a set of conditions," `NOT EXISTS` is usually concise and avoids needing to pick a NOT NULL column on B to inspect. Section 13.3 demonstrated finding customers without a PAID order.

### Exercise 14 — Find Customers with Both a CANCELLED Order and a PAID Order

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
AND EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'CANCELLED'
)
ORDER BY c.customer_id;
```

**Answer:** An. Using two `EXISTS` predicates cleanly expresses existence across two different statuses and avoids multiplying rows via a double self-join on orders.

### Exercise 15 — Explain the Difference Between Two Filter Queries

A:

```sql
LEFT JOIN join144.orders o
    ON o.customer_id=c.customer_id
   AND o.status='PAID'
```

B:

```sql
LEFT JOIN join144.orders o
    ON o.customer_id=c.customer_id
WHERE o.status='PAID'
   OR o.order_id IS NULL
```

**Solution:** A keeps all customers. B keeps only customers who have a PAID order or no orders at all; Bình and Chi are dropped in B.

### Exercise 16 — Why Is COUNT(*) = 1 When There Are No PAID Orders?

**Solution:** `LEFT JOIN` keeps one customer row with null-extended order columns. `COUNT(*)` counts result rows; `COUNT(o.order_id)` counts only genuinely matched orders.

### Exercise 17 — Misparenthesized AND/OR Condition

Query:

```sql
ON o.customer_id=c.customer_id
AND o.status='PAID'
OR o.amount>1000
```

can join orders from other customers via the OR branch.

**Solution:**

```sql
ON o.customer_id=c.customer_id
AND (o.status='PAID' OR o.amount>1000)
```

Always keep the key-identifying condition active in every logical branch.

### Exercise 18 — If a FULL JOIN Query Has WHERE e.approved=TRUE, Are All WMS Rows Kept?

**Solution:** no. Rows existing only in WMS have `e.approved` as NULL and are dropped by WHERE. To reconcile WMS against **approved ERP records**, pre-filter the ERP source first, then FULL JOIN with WMS.

## 28. Checklist for Reviewing an Outer Join Query

| Check Question | Reason |
|---|---|
| Which side must be preserved in full? | Determines LEFT, RIGHT, or FULL |
| Which predicates define a matching row pair? | Place in ON |
| Which predicates restrict records of the preserved side? | Place in WHERE or pre-filtered source |
| Does WHERE reference columns of the non-preserved side? | Might drop null-extended rows |
| Could a parent have only non-qualifying child rows yet still need to appear? | Distinguish filtering in ON vs. OR ... IS NULL |
| Does "no match" mean no B at all, or no qualifying B? | Choose the right NULL interpretation |
| Are you counting `COUNT(*)` or `COUNT(B.pk)`? | Avoid counting null-extended rows |
| Are multiple status metrics needed? | Consider aggregate FILTER |
| Need to find A with no matching B? | Use NOT EXISTS or ON + B.pk IS NULL |
| Does FULL JOIN pre-filter each source? | Distinguish preserving raw sources vs. filtered subsets |
| Are multiple LEFT JOINs chained? | WHERE on a trailing table can drop rows from the first table |
| Does the join multiply row counts? | Control fan-out before LIMIT, SUM, and COUNT |
| Are tenant keys filtered and joined completely? | Prevent leaks and cross-tenant pairings |
| Could real columns legitimately contain NULL? | Use NOT NULL keys to detect non-matches |
| Is there an explicit ORDER BY? | PostgreSQL does not guarantee order without ORDER BY |
| Was correctness verified before optimizing? | Business accuracy outweighs plan/index names |

## 29. Quick Reference Table

| Need | SQL Pattern | Key Effect |
|---|---|---|
| Keep all customers, PAID orders if any | `LEFT JOIN orders o ON o.customer_id=c.id AND o.status='PAID'` | Customers without PAID still appear |
| Only customers with PAID orders | `LEFT JOIN ... ON ... WHERE o.status='PAID'` | Drops customers without PAID |
| Only customers in city X, orders if any | `LEFT JOIN ... ON ... WHERE c.city='X'` | Keeps all customers in X |
| Keep all customers, match orders only if customer in X | `LEFT JOIN ... ON ... AND c.city='X'` | Customers outside X still appear with NULL orders |
| Customers who never placed an order | `LEFT JOIN ... ON ... WHERE o.order_id IS NULL` | Only customers with zero orders |
| Customers with no PAID order | `LEFT JOIN ... ON ... AND o.status='PAID' WHERE o.order_id IS NULL` | Includes customers with only CANCELLED |
| Alternative anti-join | `WHERE NOT EXISTS (SELECT 1 FROM orders ... AND status='PAID')` | Expresses non-existence cleanly |
| Count PAID orders, keeping 0 counts | `COUNT(o.order_id)` after LEFT JOIN filtering PAID in ON | No customers lost |
| Count multiple statuses | `COUNT(o.order_id) FILTER (WHERE o.status='...')` | One report row per customer |
| Keep all records across two systems | `A FULL JOIN B ON A.key=B.key` | MATCH/ONLY_A/ONLY_B |
| FULL JOIN treating only verified B as a match | `FULL JOIN B ON A.key=B.key AND B.verified` | Unverified B can still appear separately |
| Reconcile two filtered sources | `FROM (SELECT ... WHERE ...) A FULL JOIN (SELECT ... WHERE ...) B` | Preserves both filtered sets completely |
| Keep all customers across multiple tables | `customers LEFT JOIN (orders INNER JOIN filtered payments) ...` | Customers not lost when payments are missing |
| Keep entire right table | `A RIGHT JOIN B ...` | Equivalent to B LEFT JOIN A |
| Paginate by customer | Filter/LIMIT customers first, LEFT JOIN orders afterward | Avoids counting joined rows as customers |
| Inspect execution plan | `EXPLAIN SELECT ...` | Can simplify LEFT to INNER if WHERE is null-rejecting |

## 30. Summary: Remember "ON Picks Matching Pairs, WHERE Picks Output Rows"

The three outer joins provide the ability to **preserve rows without a partner**:

- `LEFT JOIN` preserves the left side.
- `RIGHT JOIN` preserves the right side.
- `FULL JOIN` preserves both sides.

However, that preservation can be undone during the **result filtering** step.

Final comparison:

```sql
-- Goal 1: all customers; PAID orders only if any.
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

This query keeps **Bình, Chi, and Hà** even though they have no PAID orders.

```sql
-- Goal 2: only customers who have a PAID order.
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

This query returns only **An and Dũng**.

Neither query is universally "better" than the other: **they answer two different business questions**.

Rules to remember:

1. **Conditions in ON** decide whether a row pairs with another row; when no pair matches, an outer join still preserves the designated side via null-extended rows.
2. **Conditions in WHERE** filter the joined result; null-rejecting predicates on a non-preserved side typically eliminate unmatched rows.
3. **A condition on the preserved table inside ON does not filter that table out.** To exclude rows from the preserved table, place the filter in WHERE or pre-filter the source.
4. **FULL JOIN demands care on both sides.** ON conditions can split a pair into two single-sided rows; WHERE can drop rows belonging to only one source.
5. **`COUNT(*)` and `COUNT(right_side_pk)` differ** when null-extended rows exist; use aggregate `FILTER` for multiple status metrics.
6. **"No B" differs from "no B meeting condition."** Anti-joins with conditions in ON or `NOT EXISTS` express this distinction accurately.
7. **Multiple outer joins interact.** Filters on a third table, ORDER BY/LIMIT, and fan-out can alter the entire report.
8. **Correct semantics first, optimization second.** PostgreSQL can transform plans whenever doing so preserves output; indexes and `EXPLAIN` cannot fix a misstated business requirement.

If you remember just one sentence, make it this: **`ON` decides "who pairs with whom"; `WHERE` decides "which result rows stay."** With outer joins, these two questions are never freely interchangeable.
