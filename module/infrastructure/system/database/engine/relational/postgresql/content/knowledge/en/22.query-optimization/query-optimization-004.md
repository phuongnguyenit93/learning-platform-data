# Rewriting Subqueries, JOIN, and EXISTS While Preserving Semantics in PostgreSQL

## 1. Why Must SQL Optimization Start with Semantics?

A SQL query may run slow because of missing indexes, stale statistics, or a suboptimal execution plan. Yet queries are also slow because they **express the wrong question relative to what the business actually wants to ask**.

Consider the requirement:

> Find customers who **have placed at least one PAID order**.

A developer might write:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

If a customer has three PAID orders, this `JOIN` returns **three rows for that same customer**. Yet the business only asks whether that customer **has** a PAID order, not for a list of every order.

A more faithful formulation is:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`EXISTS` asks exactly one thing: **does at least one matching row exist?** It does not multiply customer rows by order count.

This is a foundational rule of query optimization:

> **Any query rewrite must preserve the exact results demanded by business semantics before pursuing a faster execution plan.**

Never replace a query with a faster variant that:

- Returns extra duplicate rows.
- Drops customers who have no orders yet.
- Multiplies monetary sums across one-to-many joins.
- Changes the meaning of `NULL`.
- Conflates “has no orders” with “has no PAID orders.”
- Picks the wrong row when fetching the latest order.
- Moves a filter from `ON` to `WHERE` and accidentally breaks outer-join behavior.

In PostgreSQL, the optimizer can automatically transform many subqueries into a **semi join**, **anti join**, or other join types. However, automatic optimization does not mean **all syntactic forms are semantically equivalent**.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **existence**, **non-existence**, **row matching**, and **aggregation** semantics.
2. Know when `EXISTS`, `IN`, `JOIN`, and `NOT EXISTS` are truly equivalent.
3. Explain why SQL uses **bag semantics** (allowing duplicate rows) and its implications for `JOIN`.
4. Rewrite correlated subqueries into JOINs/aggregates when the rewrite preserves cardinality.
5. Avoid the `NOT IN` trap when a subquery can return `NULL`.
6. Understand the difference between placing filters in `ON` vs `WHERE` with `LEFT JOIN`.
7. Use `LATERAL`, `DISTINCT ON`, and window functions for “one row per group” requirements.
8. Understand optimizer limits when transforming subqueries and CTEs.
9. Read `EXPLAIN (ANALYZE, BUFFERS)` to spot semi joins, anti joins, nested loops, hash joins, and subplans.
10. Verify query equivalence using test datasets, `EXCEPT ALL`, and NULL/duplicate-key edge cases.
11. Apply an optimization workflow grounded in **correctness → plan → measurement → operations**.

---

## 2. First Identify the Question the SQL Needs to Answer

Before replacing `JOIN` with `EXISTS`, classify the business question.

| Business Question | Semantics | Usually Appropriate Formulation |
|---|---|---|
| Does the customer have a PAID order? | **At least one exists** | `EXISTS` or appropriate `IN` |
| Does the customer have no PAID orders? | **None exist** | `NOT EXISTS` |
| List every order of each customer? | **Match one-to-many relation** | `INNER JOIN` |
| List all customers, even without orders? | **Preserve left rows** | `LEFT JOIN` |
| Count orders per customer, including 0? | **Aggregate per customer** | `LEFT JOIN + GROUP BY` or correlated COUNT |
| Get the timestamp of the latest order? | **MAX aggregation** | Scalar subquery or aggregate JOIN |
| Get the **entire row** of the latest order? | **Top 1 per group** | `LEFT JOIN LATERAL`, `DISTINCT ON`, or `ROW_NUMBER` |
| Does the order have at least one successful payment? | **Child record exists** | `EXISTS` |
| Does the order lack a successful payment? | **Negated existence** | `NOT EXISTS` |

A helpful rule of thumb:

- **“Does one exist?”** is usually a **semi join**.
- **“Do none exist?”** is usually an **anti join**.
- **“Give me all matching pairs”** is a standard join.
- **“How many, total, maximum?”** is an aggregate.
- **“Which row ranks first in each group?”** requires explicit ordering and selection.

Choosing the right relational operation upfront is far cleaner than writing an overly broad JOIN and patching row counts with `DISTINCT`.

## 3. SQL Uses Bag Semantics: `JOIN` Can Multiply Rows

In mathematical set theory, an element appears at most once. In standard SQL, query results are **multisets/bags**: they can contain identical rows multiple times.

Example relations:

```text
customers:
  customer_id=1, email=an@example.test

orders:
  order_id=101, customer_id=1, status=PAID
  order_id=102, customer_id=1, status=PAID
```

JOIN:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

returns:

```text
1 | an@example.test
1 | an@example.test
```

Two rows have identical `SELECT` values because they correspond to **two distinct matching pairs** in the join.

Meanwhile:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

returns only:

```text
1 | an@example.test
```

**This cardinality difference is a semantic difference**, not merely a performance difference.

### 3.1. `JOIN` Builds Row Pairs; `EXISTS` Tests Membership

`JOIN`:

```text
Each left-side row × all matching right-side rows.
```

`EXISTS`:

```text
Each left-side row is kept or dropped based on
whether AT LEAST ONE matching right-side row exists.
```

When multiple right-side rows match, `JOIN` increases row counts while `EXISTS` never duplicates left-side rows.

### 3.2. Why Row Multiplication Is Especially Dangerous with `SUM`

Suppose each order has multiple `order_items` and multiple `payments` attempts. Joining both one-to-many relations:

```sql
SELECT ...
FROM orders o
JOIN order_items i ON i.order_id = o.order_id
JOIN payments p ON p.order_id = o.order_id;
```

an order with two items and three payments produces **2 × 3 = 6 rows**. Summing `i.quantity * i.unit_price` over this result triples the item totals.

Always establish the **grain** of your data: “Does each output row represent a customer, an order, a line item, or a payment?”

## 4. Lab Dataset Including Duplicates and `NULL`s

The examples below use schema `rewrite283` in a test PostgreSQL database. Never run on production data.

### 4.1. Create Schema and Customers Table

```sql
CREATE SCHEMA IF NOT EXISTS rewrite283;

CREATE TABLE rewrite283.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    segment text NOT NULL
        CHECK (segment IN ('VIP', 'STANDARD'))
);
```

### 4.2. Orders Table

```sql
CREATE TABLE rewrite283.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES rewrite283.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

### 4.3. Order Items and Payment Attempts

```sql
CREATE TABLE rewrite283.order_items (
    order_id integer NOT NULL
        REFERENCES rewrite283.orders(order_id),
    line_no integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE rewrite283.payments (
    payment_id integer PRIMARY KEY,
    order_id integer NOT NULL
        REFERENCES rewrite283.orders(order_id),
    status text NOT NULL
        CHECK (status IN ('SUCCEEDED', 'FAILED', 'PENDING')),
    paid_amount numeric(12, 2) NOT NULL
        CHECK (paid_amount >= 0)
);
```

An order can have multiple `order_items` and multiple `payments` (payment attempts). This creates row-multiplication hazards if joined inappropriately.

### 4.4. Auxiliary Table Containing `NULL` for Testing `NOT IN`

```sql
CREATE TABLE rewrite283.contact_queue (
    queue_id integer PRIMARY KEY,
    customer_id integer
        REFERENCES rewrite283.customers(customer_id),
    source text NOT NULL
);
```

`customer_id` **is nullable**. This table demonstrates the difference between `NOT IN` and `NOT EXISTS`.

### 4.5. Load Data

```sql
INSERT INTO rewrite283.customers(customer_id, email, segment)
VALUES
    (1, 'an@example.test', 'VIP'),
    (2, 'binh@example.test', 'STANDARD'),
    (3, 'chi@example.test', 'STANDARD'),
    (4, 'dung@example.test', 'VIP'),
    (5, 'em@example.test', 'STANDARD'),
    (6, 'phuc@example.test', 'STANDARD');

INSERT INTO rewrite283.orders(
    order_id, customer_id, ordered_at, status, total_amount
)
VALUES
    (101, 1, DATE '2026-09-01', 'PAID',      500),
    (102, 1, DATE '2026-09-02', 'CANCELLED', 100),
    (103, 2, DATE '2026-09-04', 'PAID',      200),
    (104, 3, DATE '2026-09-05', 'NEW',       300),
    (105, 3, DATE '2026-09-06', 'PAID',      300),
    (106, 4, DATE '2026-09-07', 'PAID',      800),
    (107, 4, DATE '2026-09-09', 'PAID',      600),
    (108, 5, DATE '2026-09-10', 'NEW',       110);

INSERT INTO rewrite283.order_items(
    order_id, line_no, product_id, quantity, unit_price
)
VALUES
    (101, 1, 10, 1, 500),
    (103, 1, 20, 2, 100),
    (105, 1, 10, 1, 200),
    (105, 2, 30, 1, 100),
    (106, 1, 20, 2, 400),
    (107, 1, 30, 3, 200);

INSERT INTO rewrite283.payments(
    payment_id, order_id, status, paid_amount
)
VALUES
    (201, 101, 'SUCCEEDED', 500),
    (202, 103, 'FAILED',    200),
    (203, 103, 'SUCCEEDED', 200),
    (204, 105, 'SUCCEEDED', 300),
    (205, 106, 'SUCCEEDED', 800),
    (206, 107, 'PENDING',   600);

INSERT INTO rewrite283.contact_queue(
    queue_id, customer_id, source
)
VALUES
    (1, 1,    'campaign'),
    (2, NULL, 'legacy'),
    (3, 3,    'campaign');
```

Run these `INSERT` statements **only once on a clean schema**. Running them again triggers primary/unique key errors, which are not query-optimization bugs.

### 4.6. Intentional Characteristics of the Dataset

| Customer | PAID Orders | Other Orders | Notes |
|---|---:|---:|---|
| 1 — An | 1 | 1 CANCELLED | Has a PAID order |
| 2 — Bình | 1 | 0 | Has a PAID order |
| 3 — Chi | 1 | 1 NEW | Has a PAID order |
| 4 — Dũng | 2 | 0 | **Two PAID orders** to test row multiplication |
| 5 — Em | 0 | 1 NEW | Has orders, **none PAID** |
| 6 — Phúc | 0 | 0 | **No orders at all** |

Key cases to observe:

- Customers **1, 2, 3, 4** have at least one PAID order.
- Customer **4** has two PAID orders.
- Customer **5** has an order, but no PAID orders.
- Customer **6** has no orders at all.
- Order **105** has two line items.
- Order **103** has two payment attempts.
- `contact_queue` contains a row with `customer_id = NULL`.

### 4.7. Prepare Statistics

```sql
ANALYZE rewrite283.customers;
ANALYZE rewrite283.orders;
ANALYZE rewrite283.order_items;
ANALYZE rewrite283.payments;
ANALYZE rewrite283.contact_queue;
```

The lab tables are tiny, so the planner will likely choose `Seq Scan` regardless of predicates/indexes. The first goal is **comparing correctness**, followed by studying optimizer behavior on larger representative datasets.

## 5. `EXISTS`: Asking Whether at Least One Matching Row Exists

Syntax:

```sql
SELECT ...
FROM outer_table AS x
WHERE EXISTS (
    SELECT 1
    FROM inner_table AS y
    WHERE y.key = x.key
);
```

`EXISTS` returns a boolean depending on whether the subquery produces **at least one row**:

- At least one row → `TRUE`.
- Zero rows → `FALSE`.

It is not a count. One matching row or a thousand matching rows both make `EXISTS` evaluate to `TRUE`.

### 5.1. Finding Customers with a PAID Order

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Expected output:

```text
1 | an@example.test
2 | binh@example.test
3 | chi@example.test
4 | dung@example.test
```

Each customer appears **once**, because `customers` has a unique `customer_id`.

### 5.2. Why Write `SELECT 1`?

In `EXISTS (SELECT 1 ...)`, the columns projected by the subquery **are not returned**. PostgreSQL cares only whether the subquery yields any row.

In simple cases, both forms are equivalent:

```sql
EXISTS (SELECT 1 FROM rewrite283.orders AS o WHERE ...)
```

```sql
EXISTS (SELECT * FROM rewrite283.orders AS o WHERE ...)
```

`SELECT 1` clearly signals existence testing to human readers. It **is not guaranteed to always run faster than `SELECT *`**. Edge cases exist when the select list has special semantics (e.g., certain set-returning or aggregate expressions), so do not treat this as a magic speedup trick.

### 5.3. `EXISTS` Does Not Need `LIMIT 1`

Sometimes people write:

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    LIMIT 1
)
```

`LIMIT 1` is usually **redundant** for simple existence checks. The optimizer already knows it only needs one match and can choose a semi join or early-stop strategy.

Do not add `LIMIT 1` as a mandatory “speedup habit”; in complex subqueries, `LIMIT` can block certain planner transformations.

## 6. `JOIN` Differs from `EXISTS` on One-to-Many Relationships

Compare:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

In the lab dataset, this returns **5 rows**:

```text
1 | an@example.test
2 | binh@example.test
3 | chi@example.test
4 | dung@example.test
4 | dung@example.test
```

Customer Dũng appears twice due to orders 106 and 107, both PAID.

Meanwhile:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

returns **4 rows**.

### 6.1. Can `JOIN + DISTINCT` Be Equivalent to `EXISTS`?

When **selecting only customer columns** and multiplicity has no business meaning:

```sql
SELECT DISTINCT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

returns the same customers as `EXISTS` in the lab.

However, note the differences:

- `JOIN + DISTINCT` forms all matching pairs and deduplicates over the selected columns (unless optimized away).
- `EXISTS` directly states “we only care whether a match exists.”
- They are **not** equivalent if `SELECT` includes columns from `orders`, computes aggregates over the join, or needs to preserve duplicate rows from the outer table.
- `DISTINCT` deduplicates across **all `SELECT` columns**, not just `customer_id`.

When the problem is membership testing, starting with `EXISTS` is cleaner.

### 6.2. Never Use `DISTINCT` to Mask a Missing `JOIN` Condition

If a predicate is accidentally omitted:

```sql
SELECT DISTINCT c.customer_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o ON TRUE;
```

you might still get a list of `customer_id`s without noticing the massive intermediate row explosion. Yet that performs a Cartesian join and can be hugely expensive.

**Fix the `JOIN` condition**, don't just slap `DISTINCT` onto the end.

## 7. Semi Join: The Meaning of `EXISTS` and `IN`

Relationally, a **semi join** keeps left-side rows that have at least one matching right-side row; it **neither returns right-side columns nor multiplies left-side rows**.

Conceptual notation:

```text
customers SEMI JOIN orders
    ON customer_id match AND status=PAID

Output grain:
    One row per qualifying customers row.
```

PostgreSQL can transform eligible `EXISTS` or `IN` queries into plan nodes such as:

- `Nested Loop Semi Join`.
- `Hash Semi Join`.
- `Merge Semi Join`.

Not every subquery can be decorrelated; transformation depends on structure, operators, volatile expressions, and other factors.

### 7.1. Does `EXISTS` Always “Stop at the First Match”?

Semantically, it only needs to know **at least one match exists**. Some execution strategies, especially nested-loop semi joins with a supporting index, can stop probing as soon as the first match is found for an outer row.

However, never claim every plan runs the subquery row-by-row and stops at the first hit. With a hash semi join, PostgreSQL may scan and hash the inner relation first; the optimizer chooses the exact plan.

### 7.2. Why “`EXISTS` Is Always Faster Than `JOIN`” Is False

A query:

```sql
SELECT o.order_id, c.email
FROM rewrite283.orders AS o
JOIN rewrite283.customers AS c
  ON c.customer_id = o.customer_id;
```

genuinely needs columns from **both tables**. Rewriting to `EXISTS` cannot return the customer's email with the same semantics.

Conversely, if the right side is guaranteed **at most one match** via a suitable `UNIQUE` constraint, `JOIN` does not multiply rows and can optimize just as well. Choose based on **required columns and valid cardinality**, then measure the plan.

## 8. `IN`: Testing Set Membership

Example:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

In the lab dataset, the result is still customers **1, 2, 3, 4**.

### 8.1. `IN` and `EXISTS` Differ Syntactically, Often Matching in Filters

`IN` checks whether a value appears in the subquery's result. When the outer `customer_id` is `NOT NULL`, equality semantics align, and the goal is **filtering matching rows**, these two forms can return the exact same rows:

```sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
)
```

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
      AND o.customer_id = c.customer_id
)
```

The planner may execute either via a semi join, hash/subplan, or another plan.

### 8.2. `IN` Still Follows Three-Valued `NULL` Logic

If the subquery contains `NULL` and no match is found, `x IN (subquery)` evaluates to **NULL/UNKNOWN**, not `FALSE`.

In `WHERE`, only `TRUE` rows are kept; both `FALSE` and `UNKNOWN` are dropped. Thus **positive `IN` and positive `EXISTS` can select the same rows in a `WHERE` filter**, even though their boolean values differ inside `SELECT` or `CASE`.

Never extend that equivalence blindly to `NOT IN` or contexts where `FALSE` and `UNKNOWN` are distinguished.

## 9. `NOT EXISTS`: Testing That No Matching Row Exists

Requirement:

> Customers who have **no PAID orders at all**.

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Expected output:

```text
5 | em@example.test
6 | phuc@example.test
```

Neither has a PAID order, yet:

- Customer 5 has one NEW order.
- Customer 6 has zero orders.

This clearly shows **“has no PAID orders”** differs from **“has no orders.”**

### 9.1. `NOT EXISTS` for “No Orders at All”

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Only **customer 6** is returned.

An optimization must never drop `o.status = 'PAID'` and claim semantics were preserved.

### 9.2. Anti Join

`NOT EXISTS` expresses an **anti join**: keep an outer row when **no matching inner row exists**.

PostgreSQL can choose:

- `Hash Anti Join`.
- `Merge Anti Join`.
- `Nested Loop Anti Join`.

Still, not every case decorrelates into an anti join; some queries retain a `SubPlan` or use another strategy.

## 10. `NOT IN` and the `NULL` Trap: A Crucial Difference

A dangerous bug is replacing `NOT EXISTS` with `NOT IN` without accounting for `NULL`s in the subquery.

Table `contact_queue` has:

```text
queue_id | customer_id
---------+------------
1        | 1
2        | NULL
3        | 3
```

Suppose we want customers **not present in `contact_queue` by `customer_id`**.

### 10.1. The `NOT IN` Query

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id NOT IN (
    SELECT q.customer_id
    FROM rewrite283.contact_queue AS q
)
ORDER BY c.customer_id;
```

In the lab dataset, this returns **0 rows**.

Why? Consider `customer_id=2`:

```text
2 NOT IN (1, NULL, 3)

2 <> 1     = TRUE
2 <> NULL  = UNKNOWN
2 <> 3     = TRUE

TRUE AND UNKNOWN AND TRUE = UNKNOWN
```

`WHERE` keeps only `TRUE`, so customer 2 is dropped. Likewise customers 4, 5, and 6 are dropped even though they are not in the queue.

### 10.2. The `NOT EXISTS` Query Matching Membership Semantics

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Result:

```text
2
4
5
6
```

The row `q.customer_id=NULL` does not satisfy `q.customer_id=c.customer_id` for non-null `customer_id`s, so it does not wipe out all remaining customers.

### 10.3. Can You Fix `NOT IN` with `IS NOT NULL`?

If the **left-hand value is guaranteed `NOT NULL`** and you want to ignore right-hand `NULL`s, you can write:

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id NOT IN (
    SELECT q.customer_id
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

In this fixture, that also returns **2, 4, 5, 6**.

However, that **changes the NULL-handling policy** and must align with business rules. If the outer expression can also be `NULL`, `NOT IN` and `NOT EXISTS` still behave differently.

### 10.4. When to Prefer `NOT EXISTS`?

When the question is **“no related row satisfies predicate,”** `NOT EXISTS` is clearer and avoids `NOT IN`'s `NULL` trap.

Never treat `NOT IN` as an automatic negation recipe for subqueries. Always check nullability on both sides and three-valued logic.

## 11. `NULL` and Three-Valued Logic in Complex Predicates

SQL has three key logical states:

- `TRUE`.
- `FALSE`.
- `UNKNOWN`, typically from comparisons involving `NULL`.

Example:

```sql
SELECT
    2 IN (1, NULL, 3) AS value_in_set,
    2 NOT IN (1, NULL, 3) AS value_not_in_set,
    NOT EXISTS (
        SELECT 1
        FROM rewrite283.contact_queue AS q
        WHERE q.customer_id = 2
    ) AS no_queue_row;
```

Semantically:

```text
value_in_set     = NULL (UNKNOWN)
value_not_in_set = NULL (UNKNOWN)
no_queue_row     = TRUE
```

### 11.1. `WHERE` vs `SELECT` Can Differ

The two expressions:

```sql
x IN (SELECT y ...)
```

and:

```sql
EXISTS (SELECT 1 ... WHERE y=x)
```

when used in a `WHERE` filter requiring `TRUE` often yield the same rows in common equality cases. Yet when projected in a result column:

```sql
SELECT
    x IN (SELECT y ...) AS flag_in,
    EXISTS (SELECT 1 ... WHERE y=x) AS flag_exists
```

they can return `NULL` and `FALSE`, respectively. If the application distinguishes `UNKNOWN`, that difference matters.

### 11.2. `IS NOT DISTINCT FROM` Is NULL-Safe, But Changes Meaning

`a IS NOT DISTINCT FROM b` treats two `NULL`s as **equal**. If you rewrite:

```sql
WHERE q.customer_id IS NOT DISTINCT FROM c.customer_id
```

then a `NULL` outer `customer_id` **matches** a `NULL` inner row, unlike standard `=`.

Use it only when business logic treats `NULL` as a real matching key. Never “fix” `NULL`s in SQL by blindly replacing `=` with `IS NOT DISTINCT FROM` without checking semantics.

## 12. `LEFT JOIN ... IS NULL` vs `NOT EXISTS`

Another way to express “no related record” is an **anti join via `LEFT JOIN`**.

Customers without a PAID order:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

In the fixture, this returns customers **5, 6**, matching `NOT EXISTS` with the same predicate.

### 12.1. Why Check `o.order_id IS NULL`?

`order_id` is a `PRIMARY KEY` and **cannot be `NULL`** in any real `orders` row. When the `LEFT JOIN` finds no matching PAID order, PostgreSQL emits NULL-extended right-side columns, so `o.order_id IS NULL` confirms **no match**.

If you check a right-side column that **can legitimately be `NULL`**:

```sql
WHERE o.some_nullable_column IS NULL
```

you can accidentally keep customers who **did match** a row whose column happened to be `NULL`, producing wrong results.

**Rule:** in a `LEFT JOIN` anti-join, check a right-side column guaranteed `NOT NULL` on match—typically the primary key.

### 12.2. `ON` and `WHERE` Must Be Placed Correctly

Conditions defining “what counts as a matching order” belong in `ON`:

```sql
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE o.order_id IS NULL
```

If you write instead:

```sql
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL
```

the result **breaks**. Unmatched rows have `o.status` as `NULL`, so `o.status='PAID'` fails. Matched rows have non-null `o.order_id`. Both groups disappear.

### 12.3. Choose `NOT EXISTS` or `LEFT JOIN` Anti-Join?

The optimizer can turn both into an anti join. `NOT EXISTS` usually expresses “no row exists” more directly, especially with complex predicates.

`LEFT JOIN ... IS NULL` works well too, provided you:

- Put all right-side match criteria in `ON`.
- Check a right-side column guaranteed `NOT NULL` on match.
- Avoid projecting right-side columns or accidentally altering multiplicity.

## 13. `LEFT JOIN` with `ON` vs `WHERE`: Preserving or Dropping Left Rows?

Requirement:

> List **all customers**, along with any PAID orders. Customers without PAID orders must still appear.

Correct:

```sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.status
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Output includes:

- Customer 1: order 101.
- Customer 2: order 103.
- Customer 3: order 105.
- Customer 4: orders 106 and 107.
- Customer 5: one row with NULL order columns.
- Customer 6: one row with NULL order columns.

Total **7 rows**, because customer 4 has two PAID orders.

### 13.1. Moving `status` to `WHERE` Changes Semantics

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

The `WHERE` filter drops rows where `o.status` is `NULL`. Customers 5 and 6 vanish; here it effectively behaves like an `INNER JOIN` for PAID orders.

### 13.2. Predicates on the Left Table Can Go in `WHERE`

For instance, to list all VIP customers with or without PAID orders:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.segment = 'VIP';
```

Filtering `c.segment` does not accidentally discard unmatched left rows due to right-side `NULL`s.

### 13.3. Never Blindly Push Predicates Across Outer Joins

Valid predicate pushdown depends on join type and predicate behavior. With `INNER JOIN`, `ON` and `WHERE` predicates are more freely interchangeable; with `OUTER JOIN`, moving a predicate from `ON` to `WHERE` can change results.

## 14. Correlated Subqueries: Subqueries Depending on Outer Rows

A **correlated** subquery references values from the outer query.

Example counting orders per customer:

```sql
SELECT
    c.customer_id,
    c.email,
    (
        SELECT COUNT(*)
        FROM rewrite283.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM rewrite283.customers AS c
ORDER BY c.customer_id;
```

This is a **scalar correlated subquery**: each customer receives one count.

Result:

| customer_id | order_count |
|---:|---:|
| 1 | 2 |
| 2 | 1 |
| 3 | 2 |
| 4 | 2 |
| 5 | 1 |
| 6 | 0 |

### 14.1. Correlated Does Not Automatically Mean “Slow Row-by-Row Loop”

A naive mental model is “for each customer, run the subquery.” In practice, PostgreSQL can transform or pick different plans depending on structure. Many subqueries are decorrelated; some scalar correlated subqueries remain as a `SubPlan` executed repeatedly.

To know for sure, run `EXPLAIN (ANALYZE, BUFFERS)` and check `loops`, row counts, I/O, and plan nodes.

### 14.2. `COUNT(*)` Returning 0 Differs from an Empty Scalar Subquery

`SELECT COUNT(*) FROM ... WHERE ...` **returns one row with 0** when no rows match, because an ungrouped aggregate still emits a row.

By contrast, a non-aggregate scalar subquery like:

```sql
(
  SELECT o.order_id
  FROM rewrite283.orders AS o
  WHERE o.customer_id = c.customer_id
)
```

can:

- Return `NULL` if zero rows match.
- Return the value if exactly one row matches.
- **Error if more than one row matches**: scalar subquery returned more than one row.

Thus you cannot blindly replace every scalar subquery with a `JOIN` assuming identical behavior.

## 15. Rewriting Correlated `COUNT` as `LEFT JOIN + GROUP BY`

The correlated `COUNT` above can be rewritten as:

```sql
SELECT
    c.customer_id,
    c.email,
    COUNT(o.order_id) AS order_count
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY c.customer_id;
```

In the fixture, this matches the correlated `COUNT`: customer 6 gets `order_count = 0`.

### 15.1. The `COUNT(*)` Trap on `LEFT JOIN`

Wrong for counting orders:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS order_count
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Customer 6 has no orders yet still gets **one NULL-extended row** from `LEFT JOIN`, so `COUNT(*)` returns **1**, not 0.

Correct:

```sql
COUNT(o.order_id)
```

because `o.order_id` is `NOT NULL` in real `orders` rows. When unmatched, it is `NULL` and ignored by `COUNT`.

### 15.2. Aggregate Rewrites Must Preserve Grain

If you also join `order_items` and count orders:

```sql
SELECT c.customer_id, COUNT(o.order_id)
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
LEFT JOIN rewrite283.order_items AS i
  ON i.order_id=o.order_id
GROUP BY c.customer_id;
```

order 105 has two items, so customer 3 gets **overcounted** by one order. To count distinct orders, consider:

```sql
COUNT(DISTINCT o.order_id)
```

or better yet, **pre-aggregate at the `orders` grain** before joining. Do not rely on `DISTINCT` by reflex when row multiplication can be prevented upfront.

## 16. Pre-Aggregating Before `JOIN` to Prevent Metric Inflation

Requirement:

> For each customer, retrieve total PAID order amount and the number of successful payments.

Joining `orders` with `payments` and then running `SUM(total_amount)` inflates order totals whenever an order has multiple payment attempts.

A safe approach aggregates **each source at its proper grain** before joining:

```sql
WITH paid_orders AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS paid_order_amount
    FROM rewrite283.orders
    WHERE status = 'PAID'
    GROUP BY customer_id
),
successful_payments AS (
    SELECT
        o.customer_id,
        COUNT(*) AS successful_payment_attempts,
        SUM(p.paid_amount) AS successful_paid_amount
    FROM rewrite283.orders AS o
    JOIN rewrite283.payments AS p
      ON p.order_id = o.order_id
    WHERE p.status = 'SUCCEEDED'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.email,
    COALESCE(po.paid_order_count, 0) AS paid_order_count,
    COALESCE(po.paid_order_amount, 0) AS paid_order_amount,
    COALESCE(sp.successful_payment_attempts, 0)
        AS successful_payment_attempts,
    COALESCE(sp.successful_paid_amount, 0)
        AS successful_paid_amount
FROM rewrite283.customers AS c
LEFT JOIN paid_orders AS po
  ON po.customer_id = c.customer_id
LEFT JOIN successful_payments AS sp
  ON sp.customer_id = c.customer_id
ORDER BY c.customer_id;
```

In both CTEs:

- `paid_orders` has at most one row per `customer_id`.
- `successful_payments` has at most one row per `customer_id`.

Joining two already-aggregated sets **never cross-multiplies** order rows and payment attempts.

### 16.1. Name Metrics Accurately

`SUM(paid_order_amount)` is the sum of **orders in status `PAID`**, whereas `SUM(successful_paid_amount)` is the sum of **`SUCCEEDED` payment attempts**. Those two figures can differ when refunds, partial payments, or retries exist. Never treat both as identical “revenue” without business definition.

### 16.2. Is `COUNT(DISTINCT)` Always Wrong?

No. `COUNT(DISTINCT o.order_id)` can yield the right count even after row multiplication. However, it can be costly and does not fix other aggregates like `SUM`. Pre-aggregating or using `EXISTS` is usually cleaner.

## 17. Scalar Subquery with `MAX`: Getting the Latest Order Date

Requirement:

> One row per customer with their latest order date; customers without orders return `NULL`.

Scalar correlated subquery form:

```sql
SELECT
    c.customer_id,
    c.email,
    (
        SELECT MAX(o.ordered_at)
        FROM rewrite283.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_date
FROM rewrite283.customers AS c
ORDER BY c.customer_id;
```

Ungrouped `MAX` returns **one value** per customer, or `NULL` when no orders exist.

### 17.1. Rewriting as an Aggregate `JOIN`

```sql
SELECT
    c.customer_id,
    c.email,
    a.last_order_date
FROM rewrite283.customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        MAX(o.ordered_at) AS last_order_date
    FROM rewrite283.orders AS o
    GROUP BY o.customer_id
) AS a
  ON a.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Both forms are semantically equivalent on the fixture, provided:

- `customer_id` is the proper grouping key.
- `LEFT JOIN` is used to retain customer 6.
- `MAX(ordered_at)` is not accidentally replaced by an arbitrary value from each group.

### 17.2. Simpler `JOIN` Form When Only `MAX` Is Needed

```sql
SELECT
    c.customer_id,
    c.email,
    MAX(o.ordered_at) AS last_order_date
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY c.customer_id;
```

This form also works cleanly as long as no extra one-to-many join inflates rows and aggregate columns retain their meaning.

### 17.3. When Does Aggregate-First Beat Correlated `MAX`?

It depends on how many customers are returned and existing indexes:

- When inspecting a few customers with an index on `(customer_id, ordered_at DESC)`, finding `MAX` per customer can be very fast.
- When scanning all customers, a single grouped pass over `orders` followed by a join can be preferable.
- PostgreSQL can pick different plans than expected; never turn “JOIN is always faster than a correlated subquery” into a dogma.

## 18. Getting the “Latest Date” Differs from Getting the “Latest Order Row”

Two different requirements:

1. Get the largest order date → `MAX(ordered_at)`.
2. Get **`order_id`, `status`, `amount`** of the latest order → requires picking **one specific row**.

Do not write:

```sql
SELECT customer_id,
       MAX(ordered_at),
       order_id
FROM rewrite283.orders
GROUP BY customer_id;
```

This is invalid in PostgreSQL because `order_id` is neither grouped, aggregated, nor functionally dependent on `customer_id`. Even in systems that allow it, an arbitrary `order_id` is not guaranteed to belong to the row with `MAX(ordered_at)`.

Also do not write:

```sql
SELECT o.customer_id, o.order_id, o.ordered_at
FROM rewrite283.orders AS o
WHERE o.ordered_at = (
    SELECT MAX(i.ordered_at)
    FROM rewrite283.orders AS i
    WHERE i.customer_id = o.customer_id
);
```

and claim **at most one row per customer**. If two orders share the latest date, the query returns **both**.

To get “one latest order,” define a tie-breaker rule, e.g.:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

## 19. `LATERAL`: Fetching the Top Row for Each Left-Side Row

PostgreSQL supports `LATERAL` so a subquery in `FROM` can reference columns from preceding tables.

Requirement:

> One row per customer with their latest order by `ordered_at DESC, order_id DESC`. Customers without orders still appear.

```sql
SELECT
    c.customer_id,
    c.email,
    latest.order_id,
    latest.ordered_at,
    latest.status,
    latest.total_amount
FROM rewrite283.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
```

Explanation:

- For each left-side customer, the subquery looks up that customer's orders.
- `ORDER BY ... LIMIT 1` selects one order deterministically.
- `LEFT JOIN LATERAL ... ON TRUE` retains customers with no orders, filling `latest` columns with `NULL`.
- An index on `orders(customer_id, ordered_at DESC, order_id DESC)` directly supports this lookup.

### 19.1. Expected Result

| customer_id | latest order_id | latest status |
|---:|---:|---|
| 1 | 102 | CANCELLED |
| 2 | 103 | PAID |
| 3 | 105 | PAID |
| 4 | 107 | PAID |
| 5 | 108 | NEW |
| 6 | NULL | NULL |

Notice customer 1's latest order is **CANCELLED**, even though they placed an earlier PAID order. Never silently change “latest order” to “latest PAID order” unless business rules ask for it.

### 19.2. `LEFT JOIN LATERAL` vs `CROSS JOIN LATERAL`

If you use:

```sql
CROSS JOIN LATERAL (...)
```

customer 6 (who has no orders) is dropped because the subquery returns zero rows. To keep customer 6, use `LEFT JOIN LATERAL ... ON TRUE` as shown above.

### 19.3. `LATERAL` Is Not Always Fastest

When the outer table contains vast numbers of customers, the subquery may probe `orders` many times. Per-customer index lookups work great for a small customer set, yet may lose to a single scan + sort/group over `orders` when fetching all customers.

## 20. `DISTINCT ON`: A Signature PostgreSQL Option

PostgreSQL offers `DISTINCT ON` to take the **first row** per group under a matching sort order.

Example latest order for each customer **who has orders**:

```sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.ordered_at,
    o.status,
    o.total_amount
FROM rewrite283.orders AS o
ORDER BY
    o.customer_id,
    o.ordered_at DESC,
    o.order_id DESC;
```

This emits one row each for customers 1–5, **excluding customer 6** who has no orders.

### 20.1. Keeping Customers Without Orders

Wrap `DISTINCT ON` in a subquery/CTE, then `LEFT JOIN`:

```sql
WITH latest_orders AS (
    SELECT DISTINCT ON (o.customer_id)
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount
    FROM rewrite283.orders AS o
    ORDER BY
        o.customer_id,
        o.ordered_at DESC,
        o.order_id DESC
)
SELECT
    c.customer_id,
    c.email,
    l.order_id,
    l.ordered_at,
    l.status
FROM rewrite283.customers AS c
LEFT JOIN latest_orders AS l
  ON l.customer_id = c.customer_id
ORDER BY c.customer_id;
```

This returns customer 6 with `NULL`s, matching the `LATERAL` requirement above.

### 20.2. `ORDER BY` Must Include a Clear Tie-Breaker

`DISTINCT ON (customer_id)` keeps the first row encountered in each group. If `ORDER BY` leaves ties when dates collide, which row wins can depend on physical order or plan choice.

`order_id DESC` provides a deterministic tie-breaker when `order_id` is unique.

### 20.3. Leading `ORDER BY` Prefix Rule

In PostgreSQL, `DISTINCT ON` expressions must match the **leftmost `ORDER BY` expressions** per its syntax rules. For example:

```sql
SELECT DISTINCT ON (customer_id) ...
ORDER BY customer_id, ordered_at DESC, order_id DESC
```

is the canonical valid pattern.

Do not change it to:

```sql
ORDER BY ordered_at DESC, customer_id
```

and expect it to express picking the first row per customer in `DISTINCT ON`.

## 21. `ROW_NUMBER()`: A Window Function Alternative

Another alternative:

```sql
WITH ranked AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM rewrite283.orders AS o
)
SELECT
    c.customer_id,
    c.email,
    r.order_id,
    r.ordered_at,
    r.status
FROM rewrite283.customers AS c
LEFT JOIN ranked AS r
  ON r.customer_id = c.customer_id
 AND r.rn = 1
ORDER BY c.customer_id;
```

This also returns the single latest order for customers with orders and keeps customer 6.

### 21.1. Why Does `r.rn = 1` Belong in `ON`?

In a `LEFT JOIN`, putting:

```sql
ON r.customer_id = c.customer_id AND r.rn = 1
```

keeps customers who have no matching ranked row.

If you put:

```sql
WHERE r.rn = 1
```

after the `LEFT JOIN`, customer 6 has `r.rn = NULL` and gets filtered out, breaking the requirement to keep all customers.

### 21.2. Are `LATERAL`, `DISTINCT ON`, and `ROW_NUMBER` Identical?

They **can** return identical results when:

- They share the same definition of “latest.”
- They share the same tie-breaker.
- They share the requirement to retain customers without orders.
- They keep identical status/filter conditions.
- Each selects exactly one row per customer.

However, plans and costs differ based on customer count, orders per customer, indexes, and projected columns. Always measure on a representative workload.

## 22. Where Do Predicates Go Inside Nested `EXISTS` to Preserve Meaning?

Suppose the question is:

> Find customers who have at least one PAID order **and** that same order has a `SUCCEEDED` payment.

Correct:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND EXISTS (
          SELECT 1
          FROM rewrite283.payments AS p
          WHERE p.order_id = o.order_id
            AND p.status = 'SUCCEEDED'
      )
)
ORDER BY c.customer_id;
```

Fixture output: **1, 2, 3, 4** (for customer 4, order 106 succeeded; order 107 is still `PENDING`).

### 22.1. The Trap of Two Independent `EXISTS` Clauses

Wrong if business logic requires **the same order** to be both `PAID` and paid via `SUCCEEDED`:

```sql
WHERE EXISTS (
    SELECT 1 FROM rewrite283.orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
AND EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    JOIN rewrite283.payments p ON p.order_id=o.order_id
    WHERE o.customer_id = c.customer_id
      AND p.status='SUCCEEDED'
)
```

Two separate `EXISTS` clauses can both be satisfied by **two different orders**: one order `PAID` without a succeeded payment, and another `NEW`/`CANCELLED` order with a `SUCCEEDED` payment from an anomaly or separate flow. When the requirement says “the same entity satisfies both conditions simultaneously,” predicates must be **linked on the exact entity key**.

### 22.2. Nested `EXISTS` Does Not Inherently Cause N×M Execution

The optimizer can decorrelate or pick multi-level semi joins. Correct binding on the **same `order_id`** comes first; plan optimization comes second.

## 23. `EXISTS` vs `COUNT(*) > 0`: Intent and Cost

Two forms:

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

and:

```sql
WHERE (
    SELECT COUNT(*)
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
) > 0
```

express the same boolean condition when `COUNT` has no other side conditions: “at least one order exists.”

However:

- `EXISTS` expresses a **yes/no existence check**.
- `COUNT(*)` expresses **counting all** matching rows and comparing.
- PostgreSQL can optimize them differently; `EXISTS` enables semi-join and early-stop plans more directly in some queries.
- Never claim `EXISTS` is always faster, especially if the count is reused elsewhere or the planner already optimizes it efficiently.

### 23.1. `COUNT >= 2` Cannot Become a Plain `EXISTS`

```sql
WHERE (
    SELECT COUNT(*)
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
) >= 2
```

asks for **at least two orders**.

A plain `EXISTS` checks only **at least one order**—a semantic change.

When checking for at least two orders, use an appropriate aggregate/`HAVING` or equivalent logic. Never replace it with `EXISTS` simply because `EXISTS` was faster in a threshold-1 example.

## 24. When Can `EXISTS` Be Rewritten to `INNER JOIN`?

An intuitive sufficient condition is that the right-hand side guarantees **at most one matching row per left-hand row**.

For example, `customers` has `email UNIQUE`. Suppose a query only checks whether a customer has a profile row in `profiles(customer_id PRIMARY KEY, ...)`. Since `profiles.customer_id` is `UNIQUE`/`PRIMARY KEY`:

```sql
WHERE EXISTS (
    SELECT 1
    FROM profiles AS p
    WHERE p.customer_id = c.customer_id
)
```

can be equivalent in **customer rows** to:

```sql
JOIN profiles AS p
  ON p.customer_id = c.customer_id
```

when selecting only columns from `c` under matching predicates, because each customer matches at most one profile.

Still, verify:

- Does the right-side unique key match the exact join filter scope?
- Does the join predicate include every column of any composite unique key?
- Could one right-side row match multiple times due to non-equality predicates?
- Could `NULL` values alter matching behavior?
- Does `SELECT` expose right-side columns or interact with `GROUP BY`?

For `orders(customer_id)`, one customer has many orders, so there is **no at-most-one guarantee**.

### 24.1. Joining a One-to-One Table Is Not Automatically Better Than `EXISTS`

Even when equivalent, the optimizer may generate identical or different plans. Keep SQL readable and semantically accurate, and check `EXPLAIN` when needed.

## 25. Correlated Subquery in `SELECT` Returning Multiple Rows: A Critical Error

Consider:

```sql
SELECT
    c.customer_id,
    (
        SELECT o.order_id
        FROM rewrite283.orders AS o
        WHERE o.customer_id=c.customer_id
    ) AS order_id
FROM rewrite283.customers AS c;
```

Customers 1, 3, and 4 have **multiple orders**, so the scalar subquery cannot pick a single `order_id`; PostgreSQL throws:

```text
ERROR: more than one row returned by a subquery used as an expression
```

A wrong fix is adding `LIMIT 1` without `ORDER BY`:

```sql
SELECT o.order_id
FROM rewrite283.orders o
WHERE o.customer_id=c.customer_id
LIMIT 1
```

This picks an arbitrary row with no deterministic ordering, which can change with plan or data layout.

### 25.1. Clarify the Requirement Before Fixing

- Need **all orders** → use `JOIN`, accepting multiple rows per customer.
- Need **latest order** → use `ORDER BY` with tie-breaker via `LATERAL`/`DISTINCT ON`/`ROW_NUMBER`.
- Need **order count** → use `COUNT`.
- Need **whether any order exists** → use `EXISTS`.
- Need **total amount** → use `SUM` at the proper grain.
- Need **one order by unique key** → ensure unique constraint/predicate alignment.

Never add `LIMIT 1` solely to silence a multi-row error without knowing the business rule.

## 26. Aggregates and `HAVING`: Questions About Groups, Not Individual Rows

Requirement:

> Find customers who have **at least two PAID orders**.

```sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count
FROM rewrite283.orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY o.customer_id;
```

In the lab dataset, only **customer 4** qualifies.

### 26.1. Do Not Replace with a Plain `EXISTS`

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
```

also matches customers 1, 2, and 3, each having only one PAID order. It does not preserve the **at least two** requirement.

### 26.2. When Customer Columns and Counts Are Both Needed

```sql
WITH paid_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count
    FROM rewrite283.orders
    WHERE status='PAID'
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
)
SELECT
    c.customer_id,
    c.email,
    pc.paid_order_count
FROM rewrite283.customers c
JOIN paid_counts pc
  ON pc.customer_id=c.customer_id
ORDER BY c.customer_id;
```

The CTE makes explicit that the query joins against a pre-aggregated set with **one row per customer**.

## 27. `NOT EXISTS`, `EXCEPT`, and Bag vs Set Differences

Another way to find customers without PAID orders:

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c

EXCEPT

SELECT o.customer_id
FROM rewrite283.orders AS o
WHERE o.status='PAID';
```

In the fixture, this returns customers **5, 6**.

### 27.1. Why `EXCEPT` Is Not an Automatic Replacement

In PostgreSQL, `EXCEPT` defaults to **set semantics** and deduplicates rows. `NOT EXISTS` filters outer rows while preserving the outer source's multiplicity if duplicates exist.

For example, if the outer table is not unique `customers` PK but an event stream containing two rows with the same `customer_id`, `NOT EXISTS` keeps both event rows, whereas `EXCEPT` collapses them to one value.

`EXCEPT ALL` uses multiset semantics unlike plain `EXCEPT`, yet it is still **not synonymous with anti join**, because it subtracts occurrence counts between two sets rather than testing mere existence.

### 27.2. `NULL` in `EXCEPT`

Set operations treat `NULL` equality for deduplication using SQL grouping/set rules rather than `=` comparison inside correlated `NOT EXISTS`.

Therefore, if the key column is nullable, never replace `NOT EXISTS` with `EXCEPT` without verifying exact `NULL` and duplicate semantics required by the business.

## 28. CTEs in PostgreSQL: Clearer, Not Always Faster

A Common Table Expression:

```sql
WITH paid_customers AS (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN paid_customers AS p
  ON p.customer_id=c.customer_id;
```

cleanly expresses preparing the set of PAID customers. Still, do not assume it automatically beats `EXISTS`.

### 28.1. `MATERIALIZED` and `NOT MATERIALIZED`

In supported PostgreSQL versions, you can write:

```sql
WITH paid_customers AS MATERIALIZED (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT ...
```

or:

```sql
WITH paid_customers AS NOT MATERIALIZED (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT ...
```

The `...` placeholders above are only patterns, not complete SQL statements.

General behavior:

- `MATERIALIZED` directs the CTE to execute as a computed intermediate result per supported semantics, which can limit predicate pushdown.
- `NOT MATERIALIZED` allows eligible CTEs to be folded into the parent query for cross-boundary optimization.
- Modern PostgreSQL can inline non-side-effecting `SELECT` CTEs, typically when referenced once; multi-reference CTEs follow different defaults.
- Not all CTEs can be inlined: data-modifying CTEs, recursive CTEs, and volatile functions have specific rules.

**Never treat CTEs as either an automatic speedup or an optimization fence across all PostgreSQL versions.** Check your server version and actual plan.

### 28.2. Materialization Can Help or Hurt

It helps when an expensive intermediate result is reused multiple times.

It hurts when it forces building a large set before an outer query filters down to a handful of rows. Always decide based on reference count and selectivity.

## 29. Predicate Pushdown: Valid for `INNER JOIN`, Not Automatically for `OUTER JOIN`

The optimizer can push filters down closer to base scans to reduce processed rows, but only when filter and join semantics allow it.

Example `INNER JOIN`:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
WHERE o.status='PAID';
```

can be semantically equivalent to:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN (
    SELECT order_id, customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
) AS o
  ON o.customer_id=c.customer_id;
```

because filtering `orders` before or after an `INNER JOIN` drops the same non-qualifying pairs.

Yet with `LEFT JOIN`, moving a predicate from `ON` to `WHERE` alters preservation of unmatched left rows, as seen in section 13.

### 29.1. Do Not Move `LIMIT` Arbitrarily

These two queries have different meanings:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 3;
```

and:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN (
    SELECT *
    FROM rewrite283.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
) o
  ON o.customer_id=c.customer_id;
```

In the fixture every order has a valid customer, yet if any `JOIN`/`WHERE` filter exists, the two forms can select different three-row subsets. **Applying `LIMIT` before vs after filtering or joining is a potential cardinality change.**

### 29.2. Predicates with Volatile Functions

PostgreSQL functions like `random()` or `clock_timestamp()` are volatile. Changing evaluation order or call counts can alter results.

Do not rely on functions with side effects or call-count dependencies to “test whether `EXISTS` stops at the first row.” PostgreSQL does not guarantee imperative left-to-right boolean short-circuiting across all expressions.

## 30. `EXISTS` with `UPDATE` and `DELETE`: Targeting the Exact Set

`EXISTS` is not limited to `SELECT`.

Example upgrading customers to VIP if they have at least one PAID order of amount >= 700:

```sql
UPDATE rewrite283.customers AS c
SET segment='VIP'
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
      AND o.total_amount >= 700
)
RETURNING c.customer_id, c.segment;
```

In the fixture, customer 4 is already VIP and still matches. The statement still performs an `UPDATE` on matching rows even if the `segment` value stays the same.

### 30.1. `UPDATE ... FROM` Can Multiply Matches

Variant:

```sql
UPDATE rewrite283.customers AS c
SET segment='VIP'
FROM rewrite283.orders AS o
WHERE o.customer_id=c.customer_id
  AND o.status='PAID'
  AND o.total_amount >= 700;
```

If a customer matches multiple source rows, PostgreSQL picks one joined row to update the target row; when `SET` depends on source columns, the result must not rely on an ambiguous source row.

When the goal is **merely checking that at least one qualifying order exists**, `EXISTS` conveys the intent cleanly and avoids assuming a unique source row.

### 30.2. `DELETE ... WHERE NOT EXISTS`

Pattern for deleting unreferenced temporary records:

```sql
DELETE FROM some_temp_objects AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM object_links AS l
    WHERE l.object_id=t.object_id
);
```

This is a pattern only—do not run it directly since those two tables do not exist in the lab fixture. For real deletions, rely on proper constraints, transactions, and concurrency design; `NOT EXISTS` under a snapshot does not prevent new references from being inserted concurrently without proper constraints.

### 30.3. `INSERT ... WHERE NOT EXISTS` Does Not Replace `UNIQUE`

Example:

```sql
INSERT INTO some_table(key, value)
SELECT $1, $2
WHERE NOT EXISTS (
    SELECT 1
    FROM some_table
    WHERE key=$1
);
```

Two concurrent transactions can both observe “key does not exist” and both `INSERT`. If uniqueness is required, a **`UNIQUE` constraint/index** is the essential safeguard, and `INSERT ... ON CONFLICT` handles atomic upserts/skips.

Using `EXISTS` in a query filter does not solve write race conditions.

## 31. Indexes Supporting Semi/Anti Joins and Correlated Lookups

Indexes often helpful for the patterns in this lesson:

```sql
CREATE INDEX idx_rewrite283_orders_customer_status
ON rewrite283.orders(customer_id, status);

CREATE INDEX idx_rewrite283_orders_customer_date
ON rewrite283.orders(
    customer_id,
    ordered_at DESC,
    order_id DESC
);

CREATE INDEX idx_rewrite283_payments_order_status
ON rewrite283.payments(order_id, status);
```

### 31.1. `EXISTS` Checking for PAID Orders

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
```

Index `(customer_id,status)` allows direct lookups by customer and status. When seeking the first match, it provides a favorable access path for a nested-loop semi join.

### 31.2. `LATERAL` Fetching the Latest Order

```sql
WHERE o.customer_id=c.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 1
```

Index `(customer_id, ordered_at DESC, order_id DESC)` lets PostgreSQL locate a customer's slice and pull the top row in order.

### 31.3. `NOT EXISTS` and Indexes

Anti joins can benefit from indexes when probing whether a match exists. Yet if a query reads most of the inner table and hashing is cheaper, the planner may pick `Hash Anti Join` over thousands of index lookups.

### 31.4. Indexes Do Not Guarantee a Plan

The fixture has 6 customers and 8 orders, so `Seq Scan` is usually cheaper. Compare performance on sufficiently large, representative data and always check write overhead for `INSERT`/`UPDATE`/`DELETE`.

## 32. `EXPLAIN`: Inspect the Plan Instead of Guessing from Syntax

Statement:

```sql
EXPLAIN
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

may produce a plan like:

```text
Hash Semi Join
  Hash Cond: (...)
  -> Seq Scan on customers
  -> Hash
       -> Seq Scan on orders
            Filter: status = 'PAID'
```

This is an **illustrative diagram**, not an actual captured plan.

The exact same query could also produce:

- `Nested Loop Semi Join` with an index lookup on `orders`.
- `Merge Semi Join` if both inputs are suitably ordered.
- Another transformation/plan depending on PostgreSQL version, data, and query shape.

### 32.1. `EXPLAIN ANALYZE`

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

Inspect:

- `actual rows`: real row counts.
- `loops`: how many times the node ran.
- `Buffers`: shared hit/read counts and related I/O activity.
- `Hash Cond`, `Join Filter`, `Index Cond`, `Filter`: where predicates execute.
- `Semi Join` or `Anti Join` nodes if chosen by the optimizer.
- Estimated rows/cost vs `actual rows`.

### 32.2. `EXPLAIN ANALYZE` Executes SQL

For `SELECT`, `EXPLAIN ANALYZE` runs the `SELECT` to measure it.

For `INSERT`/`UPDATE`/`DELETE`, it **actually modifies data** before the transaction ends. When analyzing DML, run only in a lab environment or inside a transaction with an intentional rollback; never run casually on production.

### 32.3. Never Draw Conclusions from a Single Run on a Six-Row Table

Plans on tiny datasets do not represent production. Meaningful benchmarks require realistic row counts, distributions, orders-per-customer skew, selectivity, statistics, indexes, parameters, and concurrent workloads.

## 33. `SubPlan`, `InitPlan`, and Decorrelation

A subquery can appear in `EXPLAIN` in several forms.

### 33.1. `SubPlan`

If a subquery is not turned into a join, the plan may display `SubPlan` alongside its execution count.

Example scalar correlated count:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id,
       (
          SELECT COUNT(*)
          FROM rewrite283.orders AS o
          WHERE o.customer_id=c.customer_id
       ) AS n
FROM rewrite283.customers AS c;
```

In some plans, the subplan node's `loops` matches the number of customer rows processed. That tells you whether repeated index probes are becoming expensive.

### 33.2. `InitPlan`

A subquery independent of outer rows can sometimes be evaluated once upfront as an `InitPlan`, such as a shared threshold:

```sql
SELECT *
FROM rewrite283.orders
WHERE total_amount > (
    SELECT AVG(total_amount)
    FROM rewrite283.orders
);
```

Do not assume `AVG` always re-runs for every order; PostgreSQL can compute the uncorrelated subquery once via an appropriate plan.

### 33.3. Decorrelation Is Not Always Possible

Constructs such as:

- Certain `LIMIT/OFFSET` clauses.
- Complex correlated aggregates.
- Window functions.
- Volatile expressions.
- Special outer-join and `NULL` semantics.
- Security barriers and other semantic boundaries.

can restrict valid transformations. A shorter-looking subquery does not automatically yield a cheaper plan, and a neat CTE is not guaranteed to be inlined.

## 34. Procedure for Verifying Equivalence Between Two Queries

Before deploying a rewrite:

1. State the **grain**: what does each output row represent?
2. Verify **output columns**, data types, aliases, and `NULL` policy.
3. Check **min/max rows** per key.
4. List cases with **0, 1, and many matches**.
5. List **`NULL` cases in keys and filter columns** if the schema permits `NULL`.
6. If `ORDER BY`/`LIMIT` is present, specify sort order and tie-breakers.
7. Run both original and rewritten queries on the same data snapshot.
8. Compare as **multisets**, not merely by row count or `DISTINCT` sets.
9. Only after equivalence is confirmed should you compare `EXPLAIN` and latency.

### 34.1. Why Comparing `COUNT(*)` Is Insufficient

Two queries can both return 4 rows yet return **four different `customer_id`s**. Or both return the same IDs with different multiplicities.

Example:

```text
Q1: 1, 2, 3, 4
Q2: 1, 1, 2, 3
```

Both have `COUNT(*)=4`, yet they are not equivalent.

### 34.2. Why Plain `EXCEPT` Is Insufficient

`EXCEPT` deduplicates rows and therefore hides multiplicity differences. When verifying a rewrite that must preserve duplicate counts, use `EXCEPT ALL`.

## 35. Using `EXCEPT ALL` for Multiset Verification

Suppose we want to compare two ways of finding customers with PAID orders, both returning `customer_id, email`:

```sql
WITH q_exists AS (
    SELECT c.customer_id, c.email
    FROM rewrite283.customers AS c
    WHERE EXISTS (
        SELECT 1
        FROM rewrite283.orders AS o
        WHERE o.customer_id=c.customer_id
          AND o.status='PAID'
    )
),
q_join_distinct AS (
    SELECT DISTINCT c.customer_id, c.email
    FROM rewrite283.customers AS c
    JOIN rewrite283.orders AS o
      ON o.customer_id=c.customer_id
    WHERE o.status='PAID'
),
differences AS (
    (
        SELECT * FROM q_exists
        EXCEPT ALL
        SELECT * FROM q_join_distinct
    )
    UNION ALL
    (
        SELECT * FROM q_join_distinct
        EXCEPT ALL
        SELECT * FROM q_exists
    )
)
SELECT COUNT(*) AS difference_rows
FROM differences;
```

In the fixture, `difference_rows = 0`.

### 35.1. Test Comparing `EXISTS` Against `JOIN` Without `DISTINCT`

Change `q_join_distinct` to a plain `JOIN` without `DISTINCT`, and run the symmetric `EXCEPT ALL` diff. In the fixture, because customer 4 has two PAID orders, there will be **one extra row** on the `JOIN` side; the verification query catches the mismatch.

### 35.2. Result Schemas Must Match

Queries compared with `EXCEPT ALL` must have:

- The same number of columns.
- Compatible data types.
- The same column meaning in the same order.

`EXCEPT ALL` checks **values and multiplicity**, not output ordering. If ordering is part of the API contract, test `ORDER BY` and tie-breakers separately.

### 35.3. Snapshot and Concurrency When Verifying

On a live system receiving continuous writes, running two queries at different instants can show spurious differences from concurrent mutations.

Run comparisons in a stable fixture or inside a read-only transaction with a consistent snapshot. On production, never lock large tables just to benchmark; use a controlled copy or fixture instead.

## 36. Building a Semantic Test Matrix

A minimum test matrix should cover:

| Scenario | What to Verify |
|---|---|
| Zero right-side rows | `EXISTS` is FALSE, `NOT EXISTS` is TRUE |
| Exactly one right-side match | `EXISTS` is TRUE; `JOIN` emits one row |
| Multiple right-side matches | `JOIN` multiplies rows; `EXISTS` does not |
| Customer with only `NEW` orders | “No PAID orders” TRUE, “no orders” FALSE |
| Customer with zero orders | `LEFT JOIN` still preserves customer |
| `NOT IN` subquery containing `NULL` | Can turn result `UNKNOWN` |
| Nullable left-side key | Clarify `NULL` comparison and anti-join policy |
| Two orders with identical `ordered_at` | Tie-breaker picks “latest” deterministically |
| Multiple items + multiple payments | `SUM`/`COUNT` are not multiplied |
| Aggregate over empty `LEFT JOIN` | `COUNT(*)` differs from `COUNT(o.id)` |
| Predicate in `LEFT JOIN ON` | Unmatched left rows are preserved |
| Predicate moved to `WHERE` | Can turn outer join into inner join |
| `DISTINCT ON` lacking full `ORDER BY` | Selected row is unstable |
| Scalar subquery returning >1 row | Must error or use deterministic selection |
| `ORDER BY`/`LIMIT` before vs after `JOIN` | Can change selected row set |
| Parameterized prepared query | Generic vs custom plan can differ |
| DML with `NOT EXISTS` | `UNIQUE`/isolation must prevent races |
| Tenant filter missing on one side | Can match wrong tenant / leak data |

**Passing on a small fixture does not prove correctness for all data.** Test edge cases representing your schema and business invariants.

## 37. Performance: Compare by Workload, Not Intuition

Different query shapes are handled differently by the optimizer.

| Query Shape | Potential Strengths | What to Observe |
|---|---|---|
| `EXISTS` | Clean membership; semi join or early stop | Outer row count, indexes, join strategy |
| `IN (subquery)` | Clear membership | `NULL` semantics, hash/semi plan |
| `NOT EXISTS` | Clear anti join, avoids `NOT IN` `NULL` trap | Anti-join plan, selectivity |
| `INNER JOIN` | Returns right-side columns | Match multiplicity and row explosion |
| `JOIN + DISTINCT` | Restores key uniqueness after join | `DISTINCT` cost; never mask missing join keys |
| `Correlated scalar aggregate` | Clean for few outer rows | `SubPlan` loops and index lookups |
| `Aggregate then JOIN` | Computes per group first, avoids metric inflation | Group count, memory, hash/sort |
| `LEFT JOIN LATERAL LIMIT 1` | Index-friendly top-1 lookup | Iterations per outer row |
| `DISTINCT ON` | PostgreSQL-native top-1 per group | Index order, sort, tie-breaker |
| `ROW_NUMBER()` | Flexible top-N / ranking | `WindowAgg`, sort/scan footprint |
| `CTE MATERIALIZED` | Reuses intermediate results | Whether it blocks predicate pushdown |

### 37.1. Measure with Representative Data

A `Seq Scan` on 8 rows does not mean `EXISTS` “failed to optimize.” Conversely, an `Index Scan` across 1 million rows is not automatically fast if random I/O is heavy.

Metrics to collect:

- Median and p95/p99 latency on a realistic workload.
- `shared hit/read` block counts.
- `actual rows` / `loops`.
- Memory usage and disk spills in hashes/sorts.
- Query execution frequency.
- Write rate and overhead of any added indexes.
- Plan stability across parameter values and data skew.

### 37.2. Never Optimize by Changing Semantics

If `JOIN` returns 5 rows and `EXISTS` returns 4 rows, the 20% row reduction **is not proof that `EXISTS` is faster for the same result**. The two queries answer different questions.

First decide whether the true business output is 4 unique customers or 5 customer–order pairs.

## 38. Common Pitfalls When Rewriting Subqueries and JOINs

### Pitfall 1 — Replacing a One-to-Many `JOIN` with `EXISTS` When Child Columns Are Needed

`EXISTS` cannot return individual order fields. If a report needs `order_id` and `status` for every order, `JOIN` is required.

### Pitfall 2 — Replacing `EXISTS` with `JOIN` and Forgetting Row Multiplication

Customer 4 has two PAID orders, so `JOIN` emits two rows while `EXISTS` emits one customer row.

### Pitfall 3 — Adding `DISTINCT` to Hide a Broken Join

`DISTINCT` can mask a missing join predicate, adds sort/hash overhead, and fails to fix inflated `SUM`s.

### Pitfall 4 — Using `NOT IN` with a Nullable Subquery

A single `NULL` inside the subquery turns `NOT IN` into `UNKNOWN` for all non-matching values, wiping out all desired rows.

### Pitfall 5 — Checking a Nullable Column in a `LEFT JOIN` Anti-Join

`WHERE right.nullable_column IS NULL` keeps matched rows whose column happens to be `NULL`. Check a column guaranteed non-null on match, such as the primary key.

### Pitfall 6 — Moving a Right-Table Filter from `ON` to `WHERE` in `LEFT JOIN`

Drops unmatched left-side rows, converting outer-join output into inner-join behavior.

### Pitfall 7 — Using `COUNT(*)` on `LEFT JOIN` to Count Right-Side Rows

Unmatched customers still have one NULL-extended row, making `COUNT(*)` return 1. Use `COUNT(o.order_id)`.

### Pitfall 8 — Aggregating After Joining Multiple One-to-Many Relations

Multiplying items × payment attempts inflates `SUM`/`COUNT`. Pre-aggregate at the right grain first.

### Pitfall 9 — Selecting `MAX(date)` Paired with an Arbitrary `order_id`

The row owning the maximum date must be selected deterministically with a top-1/tie-breaker query, not by grouping and grabbing an unrelated column.

### Pitfall 10 — `LIMIT 1` Without `ORDER BY`

Does not guarantee “latest” or “first” in business terms; results can shift with plans.

### Pitfall 11 — Forgetting `LEFT JOIN` When Customers Without Child Rows Must Stay

`INNER JOIN`, `CROSS JOIN LATERAL`, or `DISTINCT ON` directly over `orders` drops customer 6.

### Pitfall 12 — Moving `LIMIT` Before `JOIN`

Changes the scope of `LIMIT` and can pick a different set of rows.

### Pitfall 13 — Rewriting `COUNT >= 2` to `EXISTS`

`EXISTS` verifies at least one match, not two.

### Pitfall 14 — Two Separate `EXISTS` When the Same Order Is Required

One `EXISTS` may match order A while the other matches order B, even when no single order satisfies both predicates.

### Pitfall 15 — Assuming CTEs Are Always Faster Than Subqueries

CTEs may be inlined or materialized; defaults vary by version, reference count, and side effects.

### Pitfall 16 — Assuming `EXISTS` Always Loops per Outer Row

The planner can decorrelate it into a `Hash Semi Join` or `Merge Semi Join`; do not reason about cost from imperative assumptions.

### Pitfall 17 — Assuming `EXISTS` Always Beats `JOIN`

When right-side columns are required, `JOIN` is semantically right; when the right side is unique, `JOIN` can perform equally well. Measure the plan.

### Pitfall 18 — Forgetting `NULL` Inside `SELECT`/`CASE` Expressions

Positive `IN` and `EXISTS` may select the same rows in `WHERE`, yet return `UNKNOWN` vs `FALSE` when evaluated as boolean columns.

### Pitfall 19 — Verifying Equivalence with `COUNT` or Plain `EXCEPT`

Both can miss value or multiplicity mismatches. Use bidirectional `EXCEPT ALL` and check ordering separately.

### Pitfall 20 — `INSERT WHERE NOT EXISTS` Without a `UNIQUE` Constraint

Two concurrent transactions can both see “not found” and both insert. Use proper constraints and isolation.

### Pitfall 21 — Optimizing SQL While Dropping a Tenant Filter

A `JOIN`/`EXISTS` missing tenant keys can match another tenant's rows, causing both business bugs and security leaks.

### Pitfall 22 — Relying on `EXPLAIN` Over a Tiny Fixture

The planner choosing `Seq Scan` on a handful of rows is normal; never extrapolate production decisions from tiny tables.

## 39. Practice Exercises with Solutions

The following exercises use schema `rewrite283`. For `UPDATE` exercises, run in a lab database or inside a transaction with an intentional rollback.

### Exercise 1. Find Customers Who Have Had at Least One PAID Order

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
ORDER BY c.customer_id;
```

**Answer:** `1, 2, 3, 4`.

### Exercise 2. How Many Rows Does `JOIN` Produce Under the Same Filter?

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
WHERE o.status='PAID'
ORDER BY c.customer_id, o.order_id;
```

**Answer:** 5 rows; customer 4 appears twice for orders 106 and 107.

### Exercise 3. Why Can `DISTINCT` Return the Right Customers in Exercise 1?

**Solution:** `DISTINCT` over customer columns removes duplicates caused by multiple PAID orders, yet it adds deduplication cost and breaks if order details must also be listed.

### Exercise 4. Rewrite `IN` to `EXISTS`

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id IN (
    SELECT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
);
```

**Solution:**

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

### Exercise 5. Find Customers with No PAID Orders

```sql
SELECT c.customer_id
FROM rewrite283.customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
ORDER BY c.customer_id;
```

**Answer:** `5, 6`.

### Exercise 6. Find Customers with Zero Orders

Remove the status check inside `NOT EXISTS` so it checks for no orders at all.

**Answer:** only customer `6`.

### Exercise 7. What Happens with `NOT IN` Against `contact_queue` Containing `NULL`?

```sql
SELECT customer_id
FROM rewrite283.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM rewrite283.contact_queue
);
```

**Answer:** empty in this fixture because the subquery contains `NULL` and non-matching comparisons evaluate to `UNKNOWN`.

### Exercise 8. Rewrite Safely Using `NOT EXISTS`

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id=c.customer_id
)
ORDER BY c.customer_id;
```

**Answer:** `2, 4, 5, 6`.

### Exercise 9. Write a `LEFT JOIN` Anti-Join for Customers Without PAID Orders

```sql
SELECT c.customer_id
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
 AND o.status='PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Answer:** `5, 6`; `order_id` is `NOT NULL` whenever a match exists.

### Exercise 10. Why Is Moving `o.status='PAID'` to `WHERE` Wrong?

**Solution:** `WHERE` eliminates NULL-extended rows from the `LEFT JOIN`, dropping customers without PAID orders; match conditions belong in `ON`.

### Exercise 11. Count All Orders per Customer, Including 0

```sql
SELECT c.customer_id,
       COUNT(o.order_id) AS n
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Answer:** `(1,2), (2,1), (3,2), (4,2), (5,1), (6,0)`.

### Exercise 12. Why Is `COUNT(*)` Wrong for Customer 6?

**Solution:** `LEFT JOIN` emits one NULL-extended row for customer 6; `COUNT(*)` counts it as 1, whereas `COUNT(o.order_id)` does not.

### Exercise 13. Find Customers with at Least Two PAID Orders

```sql
SELECT customer_id, COUNT(*) AS n
FROM rewrite283.orders
WHERE status='PAID'
GROUP BY customer_id
HAVING COUNT(*)>=2;
```

**Answer:** only customer `4` with two PAID orders.

### Exercise 14. Can `HAVING COUNT(*)>=2` Be Replaced by `EXISTS`?

**Answer:** Plain `EXISTS` checks only for at least one match, so it would also include customers 1, 2, and 3; they are not equivalent.

### Exercise 15. Get Each Customer's Latest Order Date

```sql
SELECT c.customer_id,
       MAX(o.ordered_at) AS last_order_date
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Answer:** customer 6 gets `NULL`; every other customer gets their `MAX` order date.

### Exercise 16. Get the `order_id` of the Latest Order with a Tie-Breaker

```sql
SELECT c.customer_id, latest.order_id
FROM rewrite283.customers c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) latest ON TRUE
ORDER BY c.customer_id;
```

**Answer:** `1→102, 2→103, 3→105, 4→107, 5→108, 6→NULL`.

### Exercise 17. `DISTINCT ON` Top-1 Version

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM rewrite283.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

**Answer:** one latest order per customer **who has orders** (1–5); omits customer 6 unless `LEFT JOIN`ed from `customers`.

### Exercise 18. Window Function Alternative

```sql
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY ordered_at DESC, order_id DESC
           ) AS rn
    FROM rewrite283.orders o
) ranked
WHERE rn=1;
```

**Answer:** same latest orders for customers 1–5; requires an outer `LEFT JOIN` to keep customer 6.

### Exercise 19. Can You Fetch the “Latest Order” Using Only `MAX(ordered_at)`?

**Answer:** It cannot unambiguously fetch columns of a single row when dates tie; you need a tie-breaker and top-1 logic.

### Exercise 20. Why Does Joining `order_items` and `payments` Easily Inflate `SUM`?

**Answer:** An order can have multiple items and multiple payment attempts, producing a Cartesian match count. Pre-aggregate per order/customer or use semi joins where appropriate.

### Exercise 21. PAID Orders with a Successful Payment

```sql
SELECT o.order_id
FROM rewrite283.orders AS o
WHERE o.status='PAID'
  AND EXISTS (
      SELECT 1
      FROM rewrite283.payments p
      WHERE p.order_id=o.order_id
        AND p.status='SUCCEEDED'
  )
ORDER BY o.order_id;
```

**Answer:** `101, 103, 105, 106`. Order 107 only has a `PENDING` payment.

### Exercise 22. Why Can Two Independent `EXISTS` Be Wrong?

**Answer:** Each `EXISTS` can be satisfied by a different order. When the rule requires the same order to be both PAID and paid via `SUCCEEDED`, correlate the payment `EXISTS` directly to `o.order_id` of the PAID order.

### Exercise 23. Suggested Index for Customer PAID Order Checks

```sql
CREATE INDEX idx_rewrite283_customer_status_lab
ON rewrite283.orders(customer_id, status);
```

**Answer:** supports lookups by `customer_id` and `status`; the planner may still pick `Seq Scan` on the tiny fixture.

### Exercise 24. Suggested Index for Latest-Order `LATERAL`

```sql
CREATE INDEX idx_rewrite283_latest_lab
ON rewrite283.orders(customer_id, ordered_at DESC, order_id DESC);
```

**Answer:** supports `WHERE customer_id=? ORDER BY ordered_at DESC, order_id DESC LIMIT 1`.

### Exercise 25. Which `EXPLAIN` Measures Actual Execution?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM rewrite283.customers c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

**Answer:** inspects the real plan, actual rows/loops/buffers. Never assume `EXISTS` always runs as a Nested Loop.

### Exercise 26. How to Verify Equivalence Including Multiplicity?

**Answer:** use bidirectional `EXCEPT ALL` comparison and test `NULL`/duplicate edge cases; if `ORDER BY`/`LIMIT` is involved, verify ordering separately.

### Exercise 27. Why Can Plain `EXCEPT` Without `ALL` Miss Bugs?

**Answer:** Plain `EXCEPT` deduplicates rows, so two queries returning the same distinct values with different duplicate counts appear identical.

### Exercise 28. Is `CTE MATERIALIZED` Always Better?

**Answer:** no. Materialization helps when reusing expensive intermediate results, yet can block predicate pushdown; it depends on reference count and plan.

### Exercise 29. Is `NOT EXISTS` Enough to Prevent Two Duplicate `INSERT`s?

**Answer:** no, not under concurrency. You need a `UNIQUE` constraint/index and `ON CONFLICT` or appropriate transaction/locking design.

### Exercise 30. Are Two Queries Returning 4 Rows Guaranteed Equivalent?

**Answer:** no. Compare actual row values, `NULL` semantics, multiplicity, and any ordering contract.

## 40. Semantic Query Optimization Checklist

| Question to Answer | Consequence if Ignored |
|---|---|
| What does one output row represent? | Row multiplication or missing rows |
| Does business logic ask for existence or details? | Wrongly using `JOIN` instead of `EXISTS` |
| Is there a one-to-many relationship? | Cross-multiplied `COUNT`/`SUM` |
| Can there be 0 or many matches? | `JOIN` vs scalar subquery mismatches |
| Must the left table stay even without matches? | Turning `LEFT JOIN` into `INNER` |
| Does the predicate belong in `ON` or `WHERE`? | Losing NULL-extended rows |
| Is the `LEFT JOIN IS NULL` column guaranteed `NOT NULL` on match? | Falsely flagging matched rows |
| Can `NOT IN` encounter `NULL` inside or outside? | `UNKNOWN` drops desired rows |
| Do data types and comparisons preserve semantics? | `NULL`, collation, or cast discrepancies |
| Is `LIMIT`/`ORDER BY` involved? | Selecting different or arbitrary rows |
| Is there a tie-breaker for top-1? | Unstable results |
| At what grain does the aggregate run? | Wrong totals/counts |
| Do we need `COUNT` or just `EXISTS`? | Wasted work or wrong threshold |
| Are `DISTINCT`/`EXCEPT ALL` differences checked? | Missed duplicates |
| Is there a `CTE MATERIALIZED` boundary? | Blocked optimization or redundant compute |
| Are indexes present for correlation/join keys? | Expensive repeated lookups |
| Have `actual rows`/`loops`/`buffers` been checked? | Guessing performance from syntax |
| Was testing done on a stable snapshot? | False diffs from concurrent writes |
| Are multi-tenant/RLS filters preserved? | Cross-tenant matches and data leaks |
| Is DML race-safe via constraints/isolation? | Concurrent duplicate/corrupt writes |
| Were both read and write costs of new indexes measured? | Speeding up one query while slowing the workload |

## 41. Quick Reference Table

| Problem | Suited SQL Pattern | Key Caveat |
|---|---|---|
| At least one child record exists | `WHERE EXISTS (...)` | Does not multiply parent rows |
| Key belongs to a set | `WHERE x IN (SELECT y...)` | Watch `NULL`s when negating |
| No child record exists | `WHERE NOT EXISTS (...)` | Clear anti-join semantics |
| Unmatched via outer join | `LEFT JOIN ... ON ... WHERE right.pk IS NULL` | Match predicates in `ON`; check `NOT NULL` column |
| List every parent–child pair | `INNER JOIN` | One parent can emit multiple rows |
| Keep all parents | `LEFT JOIN` | Filters must respect `NULL`s |
| Count child rows including 0 | `LEFT JOIN + COUNT(child.pk)` | Don't use `COUNT(*)` over NULL-extended rows |
| Aggregate multiple 1-n sources | `Aggregate each source → JOIN` | Prevents `SUM` inflation |
| Max value per group | `MAX(value) GROUP BY key` | Returns value only, not whole row |
| Latest row per group | `LATERAL ORDER BY ... LIMIT 1` | Index-friendly for top-1 |
| First row per group in PostgreSQL | `DISTINCT ON (...) ORDER BY ...` | Explicit tie-breaker required |
| Top-N per group | `ROW_NUMBER() OVER (...)` | Filter `rn` at the right layer |
| At least N occurrences | `GROUP BY ... HAVING COUNT(*) >= N` | `EXISTS` only guarantees >= 1 |
| Outer-row-dependent query | `Correlated subquery` | Check `SubPlan` loops |
| Reuse intermediate results | `WITH ...` | Materialization/inlining varies by version |
| Compare results with duplicates | Bidirectional `EXCEPT ALL` | Does not verify `ORDER BY` |
| Inspect real execution plan | `EXPLAIN (ANALYZE, BUFFERS)` | Actually executes DML |
| Insert if absent | `UNIQUE` + `ON CONFLICT` | Plain `NOT EXISTS` has race conditions |

## 42. Official PostgreSQL Documentation to Consult

Read the docs matching your PostgreSQL server version:

- [Subquery Expressions](https://www.postgresql.org/docs/current/functions-subquery.html): `EXISTS`, `IN`, `NOT IN`, `ANY`, `ALL`, and evaluation logic.
- [Table Expressions](https://www.postgresql.org/docs/current/queries-table-expressions.html): `JOIN`, `ON`/`WHERE`, `LATERAL`, and outer-join rules.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `ORDER BY`, `LIMIT`, and `SELECT` semantics.
- [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): CTEs, materialization, recursive, and data-modifying CTEs.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): understanding plans, join algorithms, `SubPlan`, and actual execution.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): selectivity and cardinality estimation.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): index keys, operator classes, and lookup support.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots and correctness when queries drive write decisions.

Check the active server:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

Optimal plans can evolve across PostgreSQL versions; semantic equivalence of a valid rewrite must be verified independently of the planner.

## 43. Summary: Rewrite the Right Question Before Optimizing the Plan

Remember three foundational questions:

**1. Do I want paired rows, or just to know whether a related row exists?**

```sql
-- Want every customer-order pair:
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id;

-- Want each customer with at least one order:
SELECT c.customer_id
FROM rewrite283.customers c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
);
```

**2. Do I want “no match exists,” or a negation exposed to `NULL`?**

```sql
-- Usually better suited for "no related record exists":
WHERE NOT EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = outer_table.key
)

-- NOT IN can evaluate to UNKNOWN if inner rows contain NULL:
WHERE outer_table.key NOT IN (
    SELECT r.key FROM related_table r
)
```

These two snippets are **`WHERE` clause templates** to be placed inside a complete `SELECT` with matching tables.

**3. Do I need an aggregate value or the entire top row?**

```sql
-- Latest date only:
SELECT customer_id, MAX(ordered_at)
FROM rewrite283.orders
GROUP BY customer_id;

-- Full latest row with tie handling:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at, status
FROM rewrite283.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

When rewriting PostgreSQL queries:

1. **Define the grain** and one-to-many relationships.
2. **`EXISTS`/`NOT EXISTS`** express membership and anti-membership.
3. **`JOIN`** is for when you truly want paired rows—watch multiplicity.
4. **`LEFT JOIN`** preserves left-side rows, so `ON` and `WHERE` are not freely interchangeable.
5. **`NULL` and `NOT IN`** must be tested explicitly.
6. **Aggregate before `JOIN`** when multiple one-to-many sources would inflate metrics.
7. **Top-1 needs explicit ordering and a tie-breaker**; choose `LATERAL`, `DISTINCT ON`, or window functions based on workload.
8. **The optimizer can decorrelate** some subqueries, though not all forms produce identical plans.
9. **Bidirectional `EXCEPT ALL`** catches multiplicity mismatches before performance tuning.
10. **`EXPLAIN ANALYZE`** and representative benchmarks decide the faster strategy once correctness is verified.

**One takeaway to remember:** when optimizing subqueries, `JOIN`, and `EXISTS`, what must be preserved is not merely “it seems to return the same ID list,” but **the complete result semantics: which rows are kept, how many times, how `NULL`s are handled, and what each row represents**.
