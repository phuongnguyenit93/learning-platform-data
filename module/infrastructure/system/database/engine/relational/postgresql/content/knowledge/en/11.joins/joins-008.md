# NOT IN, NULL, and Finding Missing Records in PostgreSQL

A frequent task when combining data is finding **records without a matching relationship**. Examples include customers who have not placed an order, products never sold, students not enrolled in a course, invoices without payments, or customer IDs in an import file that do not exist in the master table.

SQL newcomers often write:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

This query looks right: pick customer IDs not found in the list of IDs appearing in orders. Yet as soon as the subquery returns **even one `NULL` value**, a surprising outcome occurs: the `NOT IN` query returns zero customers, even when many people actually have no orders.

The root cause is SQL's **three-valued logic**: `TRUE`, `FALSE`, and `UNKNOWN`. PostgreSQL does not treat comparisons against `NULL` like ordinary equality checks. When searching for missing data, understanding `NULL` determines whether your results are right or wrong.

This lesson explains ways to express an **anti-join**—"fetch rows from set A that have no matching row in set B"—using:

- `NOT IN` when proper `NULL` semantics are guaranteed.
- `NOT EXISTS` with a correlated condition, usually the clearest and safest way to express **no matching row**.
- `LEFT JOIN ... IS NULL` using a guaranteed non-NULL column on genuinely matched B rows.
- `EXCEPT` to compute the difference between two result sets.
- `IS DISTINCT FROM` and `IS NOT DISTINCT FROM` when business logic calls for deterministic `NULL` comparisons.

We also examine additional conditions such as order status, date ranges, composite keys, duplicates, indexes, transactions, and scenarios where two SQL queries look similar yet are not equivalent.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how `NOT IN` interacts with `NULL` and why `NOT (UNKNOWN)` remains `UNKNOWN`.
2. Write `NOT EXISTS` to find customers without orders, unlinked products, or import records missing a referenced key.
3. Use `LEFT JOIN ... WHERE right_table.primary_key IS NULL` to find unmatched rows.
4. Place right-table filter predicates properly in `ON` when finding **no rows satisfying a specific condition**.
5. Use `EXCEPT` and understand how it removes duplicates and handles `NULL` in set operations.
6. Distinguish `NULL` ("unknown") from "no related row exists."
7. Analyze edge cases: empty lists, nullable columns, composite keys, and missing values on either side.
8. Pick semantically sound queries and inspect `EXPLAIN` on large tables.
9. Recognize that missing-data detection queries **do not establish permanent integrity constraints** under concurrent transactions.
10. Complete self-contained SQL practice exercises in PostgreSQL.

**Core message:** whenever you want to ask "**does there exist no row in table B matching the current row in table A?**", start from `NOT EXISTS` semantics; use `NOT IN` only when you have verified exactly how data and `NULL`s are handled.

---

## 2. "Missing" Can Mean Different Things

Before writing SQL, clarify **what is missing**:

| Business Question | Rows Sought | Match Condition |
| --- | --- | --- |
| Customers who have never placed an order | Customers with zero orders | `orders.customer_id = customers.customer_id` |
| Customers without a paid order | Customers with no order having `status = 'PAID'` | Match ID **and** status PAID |
| Customers without an order in March | Zero orders within March | Match ID **and** time range |
| CSV rows using a non-existent `customer_id` | Staging rows with an invalid reference ID | Match ID against customers table |
| Blank reference ID in file | Staging rows with `customer_id IS NULL` | Not the same issue as "ID provided yet non-existent" |
| Products never appearing in order items | Products with no matching `order_item` | Match `product_id` through junction table |
| Missing `(tenant_id, external_id)` pair | Records lacking the exact composite key | Match **both** columns |

"Customers with no orders" and "customers with no paid orders" are **not equivalent**. Someone with a DRAFT or CANCELED order still **has an order**, just no PAID order.

Before choosing syntax, state it explicitly:

> Fetch rows A for which **there exists no** row B satisfying the join condition and specified business predicate.

Framing it this way avoids accidentally finding rows that "have one unpaid order" instead of "have zero paid orders."

---

## 3. Preparing Practice Tables and Data

We create two main tables: `customers` and `orders`. One customer can have many orders; an order in the operational table must reference an existing customer.

In addition, `customer_exclusions` intentionally contains a `NULL` `customer_id` to demonstrate the `NOT IN` trap. `imported_order_refs` simulates unvalidated CSV data allowing non-existent or missing customer IDs.

> **Warning:** The `DROP TABLE IF EXISTS` statements below delete existing data in those specific tables of the `missing_lab` schema. Run only in a **learning database safe to reset**, never as a block in production.

### 3.1. Creating the Schema

```sql
CREATE SCHEMA IF NOT EXISTS missing_lab;

DROP TABLE IF EXISTS missing_lab.orders;
DROP TABLE IF EXISTS missing_lab.customers;
DROP TABLE IF EXISTS missing_lab.customer_exclusions;
DROP TABLE IF EXISTS missing_lab.imported_order_refs;

CREATE TABLE missing_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE missing_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES missing_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE missing_lab.customer_exclusions (
    exclusion_id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    reason TEXT NOT NULL
);

CREATE TABLE missing_lab.imported_order_refs (
    import_ref TEXT PRIMARY KEY,
    customer_id BIGINT,
    raw_description TEXT NOT NULL
);
```

In `orders`, `customer_id` has both `NOT NULL` and a `FOREIGN KEY`, so **no valid order can have a NULL `customer_id`** or an ID absent from `customers`. Those guarantees come from the schema, not from `NOT IN`.

The other two tables have no foreign key because their job is to hold **potentially missing or invalid** data so we can test missing-record queries.

### 3.2. Inserting Customers

```sql
INSERT INTO missing_lab.customers (
    customer_id, customer_name, region
)
VALUES
    (1, 'An',   'NORTH'),
    (2, 'Bình', 'SOUTH'),
    (3, 'Chi',  'NORTH'),
    (4, 'Dũng', 'CENTRAL'),
    (5, 'Hà',   'SOUTH'),
    (6, 'Lan',  'CENTRAL'),
    (7, 'Mai',  'NORTH'),
    (8, 'Nam',  'SOUTH');
```

There are eight customers, IDs 1 through 8.

### 3.3. Inserting Orders

```sql
INSERT INTO missing_lab.orders (
    order_id, customer_id, status, total_amount, ordered_at
)
VALUES
    (101, 1, 'PAID',      120000, '2026-01-05 08:00:00+00'),
    (102, 1, 'DRAFT',      25000, '2026-02-02 09:00:00+00'),
    (103, 2, 'CANCELED',   50000, '2026-02-10 11:00:00+00'),
    (104, 3, 'PAID',       99000, '2026-02-11 15:00:00+00'),
    (105, 5, 'PAID',      250000, '2026-03-01 00:00:00+00'),
    (106, 5, 'PAID',       65000, '2026-04-01 00:00:00+00'),
    (107, 6, 'DRAFT',      35000, '2026-03-20 17:00:00+00'),
    (108, 8, 'CANCELED',   22000, '2026-04-02 10:00:00+00');
```

Data relationships:

```text
Customer          Orders                   Has PAID Order?
-------------------------------------------------------------
1  An             101 PAID, 102 DRAFT       Yes
2  Bình           103 CANCELED              No
3  Chi            104 PAID                  Yes
4  Dũng           (no orders)               No
5  Hà             105 PAID, 106 PAID        Yes
6  Lan            107 DRAFT                 No
7  Mai            (no orders)               No
8  Nam            108 CANCELED              No
```

From this data:

- **Zero orders of any kind:** customers 4, 7.
- **No PAID orders:** customers 2, 4, 6, 7, 8.
- **Has orders, yet no PAID orders:** customers 2, 6, 8.
- **Has a PAID order in March 2026 UTC:** customer 5 only.

These sets serve as ground truth throughout the lesson.

### 3.4. Inserting Data Containing NULL

```sql
INSERT INTO missing_lab.customer_exclusions (
    exclusion_id, customer_id, reason
)
VALUES
    (1, 2, 'Temporarily pause contact'),
    (2, NULL, 'Customer ID not yet identified'),
    (3, 6, 'Opted out of program');

INSERT INTO missing_lab.imported_order_refs (
    import_ref, customer_id, raw_description
)
VALUES
    ('r1', 1,    'Valid reference to An'),
    ('r2', 3,    'Valid reference to Chi'),
    ('r3', 99,   'Non-existent customer ID'),
    ('r4', NULL, 'Blank customer ID'),
    ('r5', 99,   'Repeated missing reference');
```

The exclusions table has **one NULL in the right-hand list**; the import table has **one NULL in the lookup column** and two rows both referencing non-existent ID 99. This lets us compare several SQL queries on the same data.

### 3.5. Verifying Tables

```sql
SELECT customer_id, customer_name
FROM missing_lab.customers
ORDER BY customer_id;

SELECT order_id, customer_id, status, ordered_at
FROM missing_lab.orders
ORDER BY order_id;

SELECT exclusion_id, customer_id
FROM missing_lab.customer_exclusions
ORDER BY exclusion_id;

SELECT import_ref, customer_id
FROM missing_lab.imported_order_refs
ORDER BY import_ref;
```

If all INSERTs succeeded, there are 8 customers, 8 orders, 3 exclusion rows, and 5 import rows.

---

## 4. Before NOT IN: SQL Has Three-Valued Logic

In SQL, a comparison can return:

- `TRUE`: true.
- `FALSE`: false.
- `NULL`/UNKNOWN: insufficient information to determine true or false.

Example:

```sql
SELECT
    5 = 5 AS true_case,
    5 = 6 AS false_case,
    5 = NULL::INTEGER AS unknown_case,
    NULL::INTEGER = NULL::INTEGER AS two_nulls_equal;
```

Both comparisons involving `NULL` return `NULL`, **not FALSE**, and two NULLs are not considered equal under the standard `=` operator.

This gives the truth table:

| Expression | Result |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 6` | FALSE |
| `5 = NULL` | NULL |
| `NULL = NULL` | NULL |
| `NOT TRUE` | FALSE |
| `NOT FALSE` | TRUE |
| `NOT NULL` | NULL |

### 4.1. WHERE Keeps Only TRUE

A query:

```sql
SELECT *
FROM some_table
WHERE condition;
```

keeps rows only when `condition` evaluates to **TRUE**. Rows yielding FALSE or NULL are excluded.

Thus a filter can silently "lose" rows with no SQL error whenever an expression evaluates to UNKNOWN instead of TRUE.

### 4.2. NULL Differs from No Row Existing

Distinguish two concepts:

1. **No matching row:** the right table contains no record satisfying the condition.
2. **A row exists whose key is NULL:** the right table has a record, yet the value to compare is missing.

With `NOT EXISTS`, we ask question (1) directly. With `NOT IN`, comparisons against NULL in case (2) can turn the result into UNKNOWN.

---

## 5. How Do IN and NOT IN Work?

Syntax:

```sql
expression IN (value_1, value_2, ...)
expression NOT IN (value_1, value_2, ...)
```

With a list of non-NULL values:

```sql
SELECT
    2 IN (1, 2, 3) AS two_is_in,
    4 NOT IN (1, 2, 3) AS four_is_not_in;
```

Both evaluate to TRUE.

You can think of:

```sql
x IN (a, b, c)
```

as equivalent to:

```sql
x = a OR x = b OR x = c
```

and:

```sql
x NOT IN (a, b, c)
```

as equivalent to:

```sql
x <> a AND x <> b AND x <> c
```

With `NULL`, comparisons can return UNKNOWN, so the intuition "not equal to any item" easily misfires.

### 5.1. One NULL on the Right Changes the Outcome

```sql
SELECT
    2 NOT IN (2, NULL) AS matched_left,
    3 NOT IN (2, NULL) AS unmatched_left,
    3 IN (2, NULL) AS in_with_null;
```

Results:

| Expression | Result |
| --- | --- |
| `2 NOT IN (2, NULL)` | FALSE, because 2 matched 2 |
| `3 NOT IN (2, NULL)` | NULL, because `3 <> NULL` is UNKNOWN |
| `3 IN (2, NULL)` | NULL, because no element is TRUE yet one is UNKNOWN |

Why isn't `3 NOT IN (2,NULL)` TRUE?

```text
3 NOT IN (2, NULL)
    |
    v
(3 <> 2) AND (3 <> NULL)
    |
    v
 TRUE AND UNKNOWN
    |
    v
 UNKNOWN
    |
    v
WHERE drops the row
```

Put simply: PostgreSQL cannot assert that 3 **differs from every element** of the list when one element's value is unknown.

### 5.2. A NULL Does Not Make Every Row UNKNOWN

For:

```sql
SELECT 2 NOT IN (2, NULL);
```

the expression returns FALSE because `2 = 2` is TRUE; that already proves 2 **belongs** to the list.

Consequently, when the right-hand list contains NULL:

- A value matching a non-NULL element → `NOT IN` returns FALSE.
- A value matching no non-NULL element → `NOT IN` typically returns NULL.
- Inside `WHERE` → zero rows are retained if all left keys are non-NULL and the right list contains NULL.

This data quirk can cause a "find missing records" query to return a **false empty set**.

---

## 6. Subquery NOT IN Trap Example

In the lab, `customer_exclusions` holds:

```text
2
NULL
6
```

Suppose the goal is to find customers **not in the exclusion list**.

The naive query:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM missing_lab.customer_exclusions AS e
)
ORDER BY c.customer_id;
```

**Result:** zero rows, even though only customers 2 and 6 are explicitly excluded.

Reason: the subquery returns a `NULL`. For customers other than 2 and 6, PostgreSQL cannot prove `customer_id <> NULL`, so `NOT IN` evaluates to UNKNOWN. For customers 2 and 6, the result is FALSE because they matched a value.

### 6.1. Fix 1: Exclude NULL Inside the Subquery

If business rules state that an exclusion row without a customer ID **does not block any specific customer**, you can write:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM missing_lab.customer_exclusions AS e
    WHERE e.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 3 | Chi |
| 4 | Dũng |
| 5 | Hà |
| 7 | Mai |
| 8 | Nam |

Because `customers.customer_id` is PRIMARY KEY, the left-hand key is also non-NULL. Once NULLs are excluded on the right, `NOT IN` expresses ID-based exclusion properly.

Be careful: **filtering out NULL is a business decision**, not something you are always permitted to silently ignore. If an exclusion row missing `customer_id` needs investigation, flag it separately instead of silently assuming it has no effect.

### 6.2. Fix 2: NOT EXISTS

Write:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.customer_exclusions AS e
    WHERE e.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

The result is also the six customers 1, 3, 4, 5, 7, 8.

Here `e.customer_id = c.customer_id` is TRUE only when the two values are **actually equal**. The row with `e.customer_id = NULL` matches no non-NULL `customer_id`, so it does not turn the whole missing-check into UNKNOWN.

### 6.3. Should You Always Use NOT EXISTS?

When the requirement is "no corresponding record exists," `NOT EXISTS` is usually the starting point that **expresses semantics most clearly and avoids the right-side NULL trap**.

Still, "NOT EXISTS is always right" requires writing the inner condition carefully:

- You must specify the **exact join keys**.
- You must include the **exact business filters**.
- If two NULL values should be treated as matching, the standard `=` operator is **not enough**.
- If the subquery reads data from another tenant or wrong timeframe, the result is still wrong despite valid `NOT EXISTS` syntax.
- If date filters or soft-deletes apply, define "existence" within that scope.

Thus preferring `NOT EXISTS` never excuses skipping careful verification of the match relationship.

---

## 7. NOT EXISTS: Directly Asking "Does Any Matching Row Exist?"

General form:

```sql
SELECT a.*
FROM table_a AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM table_b AS b
    WHERE b.key = a.key
);
```

PostgreSQL evaluates `EXISTS (subquery)` based on whether the subquery returns **at least one row**:

- At least one row → `EXISTS` is TRUE → `NOT EXISTS` is FALSE.
- Zero rows → `EXISTS` is FALSE → `NOT EXISTS` is TRUE.

`EXISTS` does not care what values the inner SELECT columns hold, even NULL.

### 7.1. SELECT 1 or SELECT *?

Two common styles:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

and:

```sql
WHERE NOT EXISTS (
    SELECT *
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

are normally equivalent in meaning for basic subqueries: only row presence matters. `SELECT 1` is a clear convention signaling **inner row data is not needed**.

Do not claim `SELECT 1` is always faster than `SELECT *`: the planner optimizes both similarly. What matters is the match condition and execution plan, not the literal selected inside EXISTS.

### 7.2. Correlated Subquery

In:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

`c.customer_id` comes from the **outer** query. Because the subquery references the current outer row, it is called a **correlated subquery**.

Conceptually:

```text
For each customer c:
   Is there any order o with o.customer_id = c.customer_id?
       Yes -> discard customer
       No  -> keep customer
```

This is a conceptual model, **not a guarantee that PostgreSQL executes row-by-row**. The planner can convert `NOT EXISTS` into an anti-join using hash, merge, or index lookups depending on the plan.

### 7.3. EXISTS Cares Only About Row Count, Not NULL in SELECT

Example:

```sql
SELECT
    EXISTS (SELECT NULL::INTEGER) AS exists_null_row,
    NOT EXISTS (SELECT NULL::INTEGER) AS not_exists_null_row,
    EXISTS (SELECT 1 WHERE FALSE) AS exists_empty;
```

Results:

| Expression | Result |
| --- | --- |
| `EXISTS (SELECT NULL::INTEGER)` | TRUE |
| `NOT EXISTS (SELECT NULL::INTEGER)` | FALSE |
| `EXISTS (SELECT 1 WHERE FALSE)` | FALSE |

`SELECT NULL` still produces **one row**, whose column happens to be NULL. Hence EXISTS receives TRUE.

This is completely different from comparing a value against NULL via `IN` or `NOT IN`.

---

## 8. Practice: Customers Who Have Never Placed an Order

Requirement:

> Retrieve customers who have **zero rows** in the `orders` table.

### 8.1. Using NOT EXISTS

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name |
| ---: | --- |
| 4 | Dũng |
| 7 | Mai |

The orders table has 8 rows, yet that does not tell you how many customers ordered: one customer can have multiple orders while others have none.

### 8.2. Using NOT IN When Keys Are Non-Nullable

In the lab, `orders.customer_id` is NOT NULL and `customers.customer_id` is PRIMARY KEY, so:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM missing_lab.orders AS o
)
ORDER BY c.customer_id;
```

returns the exact same 4 and 7.

**Why this works safely in the lab:** the schema guarantees the subquery cannot yield `NULL` for `o.customer_id` and the left column is also non-NULL. If you later point it at a nullable staging table or an expression that can produce NULL, re-analyze it.

### 8.3. Do Not Infer "Many Orders Means Many Customers"

`SELECT COUNT(*) FROM orders` is 8, yet the count of customers who ordered is not 8. To count customers with orders:

```sql
SELECT COUNT(DISTINCT customer_id) AS customers_with_orders
FROM missing_lab.orders;
```

The result is 6 (IDs 1, 2, 3, 5, 6, 8). Eight total customers minus six ordering customers equals two customers without orders.

This is a handy sanity check on a small known dataset. On large systems, when querying specific customers lacking a relationship, use an anti-join rather than subtracting two counts and guessing.

---

## 9. LEFT JOIN ... IS NULL: Another Way to Write an Anti-Join

`LEFT JOIN` preserves all rows of the left table; if there is no matching row on the right, PostgreSQL generates **NULLs for the right-side columns**.

Look at:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

For customers 4 and 7 who have no orders, `o.order_id` is NULL in the joined output.

To select only those customers:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

The result is 4 and 7, matching `NOT EXISTS`.

### 9.1. Why Check o.order_id IS NULL?

`orders.order_id` is the PRIMARY KEY and therefore **cannot be NULL in an actually existing order**.

Hence, if `o.order_id` is NULL **after the LEFT JOIN**, we can conclude that no `orders` row satisfied the ON condition.

This is far safer than checking a right-side column that **allows NULL even when a row genuinely exists**.

For example, suppose an orders table allows `coupon_code NULL`. If you write:

```sql
-- WRONG idea: NULL coupon_code does not prove a missing order.
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.coupon_code IS NULL
```

then customers **who do have orders without a coupon code** would also be returned. Always detect missing relationships via a column that cannot be NULL on a matched row—typically the PRIMARY KEY.

In our lab, using `o.order_id IS NULL` is unambiguous.

### 9.2. Comparing NOT EXISTS and LEFT JOIN ... IS NULL

| Aspect | NOT EXISTS | LEFT JOIN ... IS NULL |
| --- | --- | --- |
| Directly expresses "no matching row B" | Very clear | Requires understanding outer joins |
| NOT IN NULL-list trap | Immune | Immune |
| Need to pick a right-side column for IS NULL | No | Yes; pick a guaranteed non-NULL column |
| Include columns of table B on missing rows | Not needed | B side is NULL when missing |
| Optimizable to an anti-join | Yes | Yes, in qualifying patterns |
| Where right-table filters belong | Inside subquery | Inside `ON` to preserve outer join semantics |
| Duplicates A rows when B has multiple matches? | No for anti-match | Matched A rows are dropped; unmatched A rows stay |
| Easy to extend to multiple keys/conditions | Yes | Yes, watch `ON` vs. `WHERE` |

**There is no universal rule that NOT EXISTS is always faster than LEFT JOIN ... IS NULL or vice versa.** First express the exact semantics, then inspect the execution plan and real data.

---

## 10. The ON vs. WHERE Trap When Using LEFT JOIN

This is one of the most common mistakes when searching for "missing rows meeting a condition."

Requirement:

> Find customers **who do not have a PAID order**.

If using `LEFT JOIN`, `status = 'PAID'` belongs to **defining what counts as a matching right-side row**, so it must go inside `ON`:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Expected result:

| customer_id | customer_name | Reason |
| ---: | --- | --- |
| 2 | Bình | Only has a CANCELED order |
| 4 | Dũng | No orders |
| 6 | Lan | Only has a DRAFT order |
| 7 | Mai | No orders |
| 8 | Nam | Only has a CANCELED order |

### 10.1. Wrong Pattern 1: Filtering status in WHERE

```sql
-- WRONG for "customers without a PAID order".
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL;
```

This is self-contradictory in the lab schema: `o.status = 'PAID'` requires a right-side row, while `o.order_id IS NULL` requires no right-side row. Result is empty.

Placing a filter on a right-side column in `WHERE` **discards the null-extended rows** created by the outer join, breaking unmatched-row preservation.

### 10.2. Wrong Pattern 2: WHERE o.status <> 'PAID'

```sql
-- WRONG: finds people with at least one NON-PAID order.
SELECT DISTINCT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status <> 'PAID'
ORDER BY c.customer_id;
```

This returns customers with at least one DRAFT/CANCELED order: 1, 2, 6, 8. It is **wrong** for "has no PAID order" because customer 1 has both a PAID order and a DRAFT order. Meanwhile customers 4 and 7 (no orders) are missed entirely.

Compare the two predicates:

```text
Has at least one NON-PAID order
      EXISTS(order WHERE status <> PAID)

Has NO PAID order
      NOT EXISTS(order WHERE status = PAID)
```

These two statements are completely different whenever a customer can have multiple orders.

### 10.3. Quick Rule of Thumb

For a `LEFT JOIN` anti-join:

1. Put the **join key** and **conditions defining eligible B records** inside `ON`.
2. Put `right_primary_key IS NULL` inside `WHERE`.
3. Put independent filters on table A inside `WHERE`.
4. Never put a filter requiring B values inside `WHERE` when searching for A without B.

---

## 11. NOT EXISTS with Business Predicates

`NOT EXISTS` expresses "no PAID order" directly:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Result: 2, 4, 6, 7, 8.

### 11.1. Has an Order, Yet No PAID Order

To select **only customers who have at least one order yet have never had a PAID order**, combine `EXISTS` and `NOT EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name |
| ---: | --- |
| 2 | Bình |
| 6 | Lan |
| 8 | Nam |

This is an important pattern: **has relationship X**, yet **lacks relationship Y**.

### 11.2. No Orders Within a Time Range

Suppose the requirement is:

> Find customers with no orders **in any status** during March 2026 UTC.

Use a half-open interval:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
      AND o.ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
)
ORDER BY c.customer_id;
```

In the lab data, customer 5 has a PAID order on Mar 01; customer 6 has a DRAFT order on Mar 20. All other customers **have zero orders in March**.

Why use `< 2026-04-01` instead of `BETWEEN '2026-03-01' AND '2026-03-31'`: `TIMESTAMPTZ` includes hours, minutes, seconds, and fractional seconds. Midnight on Mar 31 (`00:00:00`) omits the rest of Mar 31.

### 11.3. No PAID Orders in March

If the goal considers only **PAID orders in March**, add the condition inside the subquery:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
      AND o.ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
)
ORDER BY c.customer_id;
```

Result: **1, 2, 3, 4, 6, 7, 8**, because only customer 5 had a PAID order in March.

Customers 1 and 3 had PAID orders before March, so they still satisfy "no PAID order **in March**."

### 11.4. Left-Table Conditions

For example, only NORTH-region customers without orders:

```sql
SELECT c.customer_id, c.customer_name, c.region
FROM missing_lab.customers AS c
WHERE c.region = 'NORTH'
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.orders AS o
      WHERE o.customer_id = c.customer_id
  )
ORDER BY c.customer_id;
```

Result: **Mai (7)**. An (1) and Chi (3) are in NORTH yet already have orders.

`c.region = 'NORTH'` filters table **A**, so it sits in the outer `WHERE`. `o.status = 'PAID'` defines whether a **B row counts as a match**, so it sits inside `NOT EXISTS`.

---

## 12. Empty Sets and NOT IN: A Special Case to Understand

If the subquery returns **zero rows**, `NOT IN` evaluates to TRUE for every left-hand value, including NULL.

Example:

```sql
SELECT
    5 NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS five_not_in_empty,

    NULL::INTEGER NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS null_not_in_empty;
```

Both evaluate to TRUE because there is no right-hand element to refute "not in set."

Remember this exception to the simplified rule "NULL on the left makes NOT IN UNKNOWN": **if the right-hand set is empty, NOT IN returns TRUE**.

Likewise, `NOT EXISTS (subquery returning 0 rows)` is TRUE.

### 12.1. IN () Is Invalid

Syntax:

```sql
-- INVALID in PostgreSQL:
WHERE id IN ()
```

is rejected by PostgreSQL.

If an API receives an empty list, you can:

- Define in business logic whether an empty list means "no filter," "return no rows," or "exclude nothing," and handle it explicitly in the application.
- Use an array parameter when appropriate:
  `id = ANY('{}'::BIGINT[])` or `id <> ALL('{}'::BIGINT[])`.
- Never build SQL by interpolating input lists into query strings.

With an empty array, `= ANY` returns FALSE and `<> ALL` returns TRUE, matching existential/universal semantics over empty sets. When the array contains NULL, three-valued logic still applies.

---

## 13. LEFT JOIN, Duplicates, and What "No Rows" Means

If a customer has 10 orders, LEFT JOIN generates 10 rows for that customer prior to filtering. Once you apply:

```sql
WHERE o.order_id IS NULL
```

every customer with at least one order is removed from the missing-results set, while customers with zero orders remain once per left row.

Thus, when table A has one row per key, a proper anti-join never creates duplicates merely because B has multiple orders.

However, if **table A itself contains duplicates** (for example, the import table has two rows with `customer_id = 99`), `NOT EXISTS` returns **both A rows** if neither matches. That is right for "find missing rows":

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

Result:

| import_ref | customer_id |
| --- | ---: |
| r3 | 99 |
| r5 | 99 |

Two distinct import lines reference missing ID 99. If the goal is a **deduplicated list of missing IDs**, add `DISTINCT`:

```sql
SELECT DISTINCT r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.customer_id;
```

Result contains only ID 99.

Notice the distinction between:

- **Finding broken import rows** to fix each line.
- **Finding missing reference IDs** to report distinct IDs.

Do not blindly add `DISTINCT` to every query if users need to see every occurrence of an error.

---

## 14. Import Data with NULL on the Left Side

`imported_order_refs` contains:

```text
r1 -> customer_id = 1
r2 -> customer_id = 3
r3 -> customer_id = 99
r4 -> customer_id = NULL
r5 -> customer_id = 99
```

To find **import rows without a matching customer**, write:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.customers AS c
    WHERE c.customer_id = r.customer_id
)
ORDER BY r.import_ref;
```

Result: **r3, r4, r5**.

Why is `r4` (`customer_id` NULL) included? Because no customer satisfies `c.customer_id = NULL` as TRUE, so the subquery returns zero rows and `NOT EXISTS` is TRUE.

That is **not necessarily wrong**. If the goal is "import rows lacking a valid link," both blank IDs and non-existent IDs are errors. However, if the goal is:

> Find customer IDs that **were supplied** yet do not exist in `customers`,

then separate out `NULL`:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

Result is only r3 and r5.

### 14.1. Classifying Both Error Types

```sql
SELECT
    r.import_ref,
    r.customer_id,
    CASE
        WHEN r.customer_id IS NULL
            THEN 'MISSING_CUSTOMER_ID'
        WHEN NOT EXISTS (
            SELECT 1
            FROM missing_lab.customers AS c
            WHERE c.customer_id = r.customer_id
        )
            THEN 'CUSTOMER_NOT_FOUND'
        ELSE 'VALID_REFERENCE'
    END AS validation_status
FROM missing_lab.imported_order_refs AS r
ORDER BY r.import_ref;
```

Meaningful result:

| import_ref | customer_id | validation_status |
| --- | --- | --- |
| r1 | 1 | VALID_REFERENCE |
| r2 | 3 | VALID_REFERENCE |
| r3 | 99 | CUSTOMER_NOT_FOUND |
| r4 | NULL | MISSING_CUSTOMER_ID |
| r5 | 99 | CUSTOMER_NOT_FOUND |

This is sound staging design: instead of lumping all missing data into one error bucket, distinguish **missing input values** from **supplied values that fail to resolve**.

---

## 15. EXCEPT: Finding the Difference Between Two Sets

PostgreSQL supports the set operator `EXCEPT`:

```sql
SELECT key FROM table_a
EXCEPT
SELECT key FROM table_b;
```

Meaning: return values appearing in set A that **do not appear in set B**, using SQL set-operation comparison rules.

### 15.1. Finding Customers Without Orders Using EXCEPT

```sql
SELECT customer_id
FROM missing_lab.customers

EXCEPT

SELECT customer_id
FROM missing_lab.orders;
```

Result contains **4 and 7**, though **order is not guaranteed** unless you apply `ORDER BY` to the final output.

You can write:

```sql
SELECT missing_id
FROM (
    SELECT customer_id AS missing_id
    FROM missing_lab.customers

    EXCEPT

    SELECT customer_id AS missing_id
    FROM missing_lab.orders
) AS missing
ORDER BY missing_id;
```

To also fetch `customer_name`, join the set difference back to `customers`:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
JOIN (
    SELECT customer_id
    FROM missing_lab.customers
    EXCEPT
    SELECT customer_id
    FROM missing_lab.orders
) AS x
  ON x.customer_id = c.customer_id
ORDER BY c.customer_id;
```

For retrieving full customer records, `NOT EXISTS` is usually shorter and easier to read since it avoids re-joining.

### 15.2. EXCEPT Removes Duplicates by Default

`EXCEPT` implements **set** semantics and eliminates duplicates. Unlike `NOT EXISTS`, it does not automatically retain duplicate A rows.

Example:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)

EXCEPT

SELECT id
FROM (VALUES (1)) AS b(id);
```

Result contains only `2`.

With `EXCEPT ALL`, occurrences are subtracted by multiplicity:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)

EXCEPT ALL

SELECT id
FROM (VALUES (1)) AS b(id);
```

The result has **one 1** and **one 2**, because the left side had two 1s and the right side subtracted one occurrence. Output order is not guaranteed without an outermost `ORDER BY`.

### 15.3. EXCEPT Compares Every Selected Column

Both branches of `EXCEPT` must have compatible column counts/types, and equality is determined across the **entire output tuple**—it does not infer business keys.

Example:

```sql
SELECT customer_id, customer_name
FROM missing_lab.customers

EXCEPT

SELECT customer_id, status
FROM missing_lab.orders;
```

This query is type-valid yet **semantically wrong**, because it compares `(customer_id, customer_name)` against `(customer_id, status)` rather than checking "is there an order for `customer_id`?"

To find missing keys, run `EXCEPT` **on the key columns alone** first, then join back for additional details if needed.

---

## 16. How Do EXCEPT and NULL Differ from NOT EXISTS?

SQL set operations treat NULL values under set-deduplication equality rules. For `EXCEPT`, two NULL-only rows are treated as identical when determining overlap to subtract.

Test:

```sql
SELECT id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)

EXCEPT

SELECT id
FROM (VALUES (NULL::INTEGER)) AS b(id);
```

Result contains only **1**, because the left-side NULL is subtracted by the right-side NULL under set semantics.

Meanwhile, `NOT EXISTS` using `=`:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id = a.id
);
```

returns both **1** and **NULL**:

- `1 = NULL` is UNKNOWN → no match → keep 1.
- `NULL = NULL` is also UNKNOWN → no match → keep NULL.

Hence **EXCEPT and NOT EXISTS using `=` are not always equivalent when keys are nullable**.

### 16.1. If You Want Two NULLs to Match

PostgreSQL supports the null-safe operator:

```sql
a IS NOT DISTINCT FROM b
```

It returns TRUE when both values are equal or **both are NULL**.

Example:

```sql
SELECT
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER
        AS nulls_match,
    NULL::INTEGER IS DISTINCT FROM 10
        AS null_differs_from_number,
    5 IS NOT DISTINCT FROM 5
        AS equal_nonnull;
```

All three expressions return TRUE.

Updating `NOT EXISTS`:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id IS NOT DISTINCT FROM a.id
);
```

Now only **1** is kept, because the left NULL matches the right NULL.

**Note:** treating two NULLs as the same key must be an **intentional business rule**. Most systems should not treat "two unknown `customer_id`s" as the same customer. `IS NOT DISTINCT FROM` is a technical tool to implement a comparison policy, not the policy itself.

### 16.2. NULL in EXCEPT ALL

With `EXCEPT ALL`, NULLs are still counted when subtracting multiplicities of rows deemed indistinguishable under set-operation semantics. For example, two NULL rows on the left minus one NULL row on the right yields one NULL row.

This differs from `NOT IN`, where a single NULL on the right turns every unmatched key's membership test into UNKNOWN.

---

## 17. Comparing Four Ways to Find Missing Records

Assuming both `A.key` and `B.key` are NOT NULL and only one key needs comparison.

### Method 1: NOT EXISTS

```sql
SELECT a.*
FROM missing_lab.customers AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS b
    WHERE b.customer_id = a.customer_id
);
```

Usually the most direct expression of "no B row exists."

### Method 2: LEFT JOIN ... IS NULL

```sql
SELECT a.*
FROM missing_lab.customers AS a
LEFT JOIN missing_lab.orders AS b
  ON b.customer_id = a.customer_id
WHERE b.order_id IS NULL;
```

Requires inspecting a right-side column that cannot be NULL when matched.

### Method 3: NOT IN

```sql
SELECT a.*
FROM missing_lab.customers AS a
WHERE a.customer_id NOT IN (
    SELECT b.customer_id
    FROM missing_lab.orders AS b
);
```

Yields the same result **in the lab schema** because both keys are non-NULL. If B can contain NULL or A is nullable, re-evaluate.

### Method 4: EXCEPT

```sql
SELECT customer_id FROM missing_lab.customers
EXCEPT
SELECT customer_id FROM missing_lab.orders;
```

Returns missing key IDs, deduplicated by default, with set-op NULL semantics. Re-joining is needed if you want full columns from A.

### 17.1. Quick Decision Table

| Criterion | NOT EXISTS | LEFT JOIN ... IS NULL | NOT IN | EXCEPT |
| --- | --- | --- | --- | --- |
| Expresses "no matching row B" | Clear | Clear with right sentinel column | Error-prone with NULL | Clear for key set difference |
| Vulnerable to a single right-side NULL breaking results | No (unlike NOT IN) | No (unlike NOT IN) | **Yes** | No (unlike NOT IN) |
| Left NULL matches right NULL by default | No with `=` | No with `=` | Not via normal equality, except empty set | Yes per set-op rules |
| Preserves duplicates in left table | Yes | Yes for unmatched rows | Yes when condition is TRUE | No with default EXCEPT |
| Right-table business filters | Inside subquery | Inside `ON` | Inside subquery, watch NULLs | Inside each branch, can get complex |
| Returns extra left-table columns | Easy | Easy | Easy | Needs tuple choice or re-join |
| Optimizable by planner | Yes | Yes | Yes, though NULL semantics limit options | Yes, per set ops |
| Recommended default for anti-join | **Often preferred** | Suitable | Only when NULLs are fully controlled | Suitable for comparing two sets |

This table compares **semantics and expressiveness**, not a benchmark claiming one syntax is always fastest.

---

## 18. Composite Keys: Never Check Only One Column

In multi-tenant systems, `external_id` may be unique only **within a tenant**. When finding missing records, match both `tenant_id` and `external_id`.

Suppose the data is:

```text
Source:
tenant_id  external_id
10         500
20         500

Target:
tenant_id  external_id
10         500
```

Comparing only `external_id = 500` falsely concludes tenant 20's record already exists.

### 18.1. NOT EXISTS with Composite Keys

General template:

```sql
SELECT s.tenant_id, s.external_id
FROM source_records AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM target_records AS t
    WHERE t.tenant_id = s.tenant_id
      AND t.external_id = s.external_id
);
```

This is illustrative syntax; `source_records` and `target_records` are not created in the lab.

### 18.2. Row NOT IN Gets Trickier with NULLs

PostgreSQL supports tuple comparisons:

```sql
WHERE (s.tenant_id, s.external_id) NOT IN (
    SELECT t.tenant_id, t.external_id
    FROM target_records AS t
)
```

However, row comparisons with NULL components have subtle three-valued logic rules. One differing component suffices to prove two tuples unequal; remaining NULL components produce UNKNOWN if no differing component proves inequality.

Hence for potentially nullable composite keys, prefer explicit per-column `NOT EXISTS` predicates with a clear NULL policy.

### 18.3. NULL-Safe Equality for Composite Keys

If business rules **allow and require** NULL on both sides to match:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM target_records AS t
    WHERE t.tenant_id IS NOT DISTINCT FROM s.tenant_id
      AND t.external_id IS NOT DISTINCT FROM s.external_id
)
```

Still ask: should two unknown `external_id` values count as the same record? In most systems the answer is **no**; require non-NULL keys or classify missing data separately.

### 18.4. Schema Constraints Should Reflect Business Keys

When `(tenant_id, external_id)` identifies an object, consider:

```sql
UNIQUE (tenant_id, external_id)
```

or a composite primary key where appropriate. Constraints prevent duplicates under concurrent writes, while `NOT EXISTS` is a **detection query**. Neither replaces the other.

---

## 19. Detecting Missing References vs. FOREIGN KEY

An important use case:

> An import file contains customer IDs that do not exist in the master table; how do we find them before loading orders?

The `imported_order_refs` staging table was designed to hold invalid IDs because it **has no foreign key**.

Query:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

returns r3 and r5.

Yet when loading into `orders` with `FOREIGN KEY (customer_id) REFERENCES customers(customer_id)`, the database must still enforce the constraint. Even if the prior check found no errors, **data can change between check and write**, or another file could be loaded.

### 19.1. Do Not Replace FOREIGN KEY with NOT EXISTS

A `NOT EXISTS` query detects broken links at **query time**. It cannot prevent:

- A customer row being deleted after the check.
- Two concurrent transactions modifying data.
- Another client inserting an order with an invalid `customer_id`.
- An import job bypassing application validation logic.

PostgreSQL enforces `FOREIGN KEY` constraints across writes, deletes, and concurrent transactions to uphold referential integrity.

**Therefore: use NOT EXISTS to report/inspect; use FOREIGN KEY to enforce referential invariants.**

### 19.2. Distinguish "Non-Existent Customer" from "No Orders"

Two queries:

```sql
-- Find customer IDs from import file that do not exist in customers.
SELECT r.import_ref
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  );
```

and:

```sql
-- Find valid customers who have no orders yet.
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

both use `NOT EXISTS`, yet **tables A and B swap roles**, answering two completely different questions.

Before writing an anti-join, always identify which base set must be preserved.

---

## 20. Filter Conditions and Soft Deletes

Many systems avoid physical deletion and instead set `deleted_at` or `is_deleted`. When asking "has no orders," clarify whether soft-deleted orders still count as existing.

Hypothetical example with `deleted_at TIMESTAMPTZ` on `orders`:

```sql
-- Find customers with no NON-deleted orders.
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders_with_soft_delete AS o
    WHERE o.customer_id = c.customer_id
      AND o.deleted_at IS NULL
);
```

`orders_with_soft_delete` is illustrative and not created in the lab.

If you omit `o.deleted_at IS NULL`, a soft-deleted order still counts as "has an order." Either interpretation can be right depending on business rules.

With `LEFT JOIN`, `o.deleted_at IS NULL` must go in `ON`:

```sql
SELECT c.customer_id
FROM missing_lab.customers AS c
LEFT JOIN orders_with_soft_delete AS o
  ON o.customer_id = c.customer_id
 AND o.deleted_at IS NULL
WHERE o.order_id IS NULL;
```

Moving that predicate to `WHERE` changes which customers stay and misstates "no non-deleted orders."

---

## 21. Missing-Data Queries Do Not Automatically Guarantee Write Consistency

Suppose a job executes:

1. Find customers without a PAID order.
2. Issue a promo reward to those customers.
3. While the job runs, a new PAID order is created.

The missing-data query may be **accurate at its snapshot yet stale by the time the job issues the reward**.

Example:

```text
T1: Job A runs NOT EXISTS -> customer 2 has no PAID order
T2: Job B inserts and COMMITs a PAID order for customer 2
T3: Job A grants reward using the T1 result
```

If business rules dictate that rewards can only be issued when no PAID order exists at grant time, additional data synchronization is required.

### 21.1. READ COMMITTED and Snapshots

In PostgreSQL's default `READ COMMITTED` isolation level, each statement sees a snapshot as of statement start. A valid `NOT EXISTS` result at query time is not a promise that **"no matching row will exist in the future."**

Using `REPEATABLE READ` or `SERIALIZABLE` changes how transactions observe and resolve concurrency, yet **does not turn a SELECT query into a permanent business constraint**.

### 21.2. If "One Promo per Customer" Is an Invariant

Create an appropriate unique constraint or unique index on the rewards table, such as `UNIQUE(customer_id, campaign_id)`, to block double-issuance per campaign.

If reward issuance also depends on order state, coordinate:

- Transaction boundaries and check timing.
- Locking mechanisms when concurrent writers interact.
- Isolation levels and retry logic on `serialization_failure` where appropriate.
- Unique/foreign keys and idempotency keys.
- Business rules handling orders whose state changes after a reward was granted.

Never run `SELECT NOT EXISTS` and treat the result as a "lock" against other transactions.

### 21.3. An Important Pitfall: NOT EXISTS Followed by INSERT Under Concurrency

Pattern:

```sql
INSERT INTO some_table (business_key)
SELECT 'A'
WHERE NOT EXISTS (
    SELECT 1
    FROM some_table
    WHERE business_key = 'A'
);
```

does not stop two concurrent transactions from both observing that `'A'` does not exist and both trying to insert `'A'`. To enforce uniqueness, add a **unique constraint** and typically use `INSERT ... ON CONFLICT ...` with the right policy.

Anti-joins find missing data; **constraints enforce uniqueness under contention**.

---

## 22. Performance: How Can PostgreSQL Execute an Anti-Join?

A correlated `NOT EXISTS` looks like "run the subquery once for each customer." In practice, the PostgreSQL optimizer recognizes these patterns and chooses among different anti-join plans.

Plan nodes you may see in `EXPLAIN`:

- **Hash Anti Join**: builds a hash table on the smaller/appropriate input and returns unmatched A rows.
- **Nested Loop Anti Join**: for each A row, probes B via an index or predicate; often fast when A is small and B has a good index.
- **Merge Anti Join**: scans two key-sorted streams to emit unmatched rows.
- **SubPlan** or **hashed SubPlan**: appears for certain subquery forms, notably when `NOT IN`'s three-valued NULL semantics must be preserved.
- **SetOp/HashSetOp/Sort**: plans used when executing `EXCEPT`.

You cannot predict the plan from SQL keywords alone. PostgreSQL weighs statistics, table sizes, indexes, selectivity, `work_mem`, data types, predicates, and version.

### 22.1. Running EXPLAIN on Missing-Data Queries

```sql
EXPLAIN
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

To inspect actual execution on a **read-only SELECT**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

`EXPLAIN ANALYZE` **actually runs the statement**, so never use it carelessly on production DML. Here it is a pure SELECT suitable for the lab.

### 22.2. Indexing the Checked Table

A common index:

```sql
CREATE INDEX idx_orders_customer_id
ON missing_lab.orders(customer_id);
```

This helps check orders by `customer_id`, particularly when the customer set is relatively small and `orders` is large.

For frequent "no PAID order" queries:

```sql
CREATE INDEX idx_orders_paid_customer
ON missing_lab.orders(customer_id)
WHERE status = 'PAID';
```

This is a **partial index** storing only PAID orders, useful when PAID orders are a small fraction of the table and queries explicitly include `status = 'PAID'`.

Factors to evaluate:

- Index columns match actual join predicates.
- Fraction of rows matching `status`.
- Whether date ranges are also filtered frequently.
- Index write overhead on `INSERT`/`UPDATE` to `orders`.
- Whether the query planner actually uses the index.

With only 8 orders in the lab table, PostgreSQL will understandably prefer a sequential scan as simpler and cheaper. That is normal.

### 22.3. Is NOT EXISTS or LEFT JOIN Faster?

There is no fixed rule that "NOT EXISTS is always faster" or "LEFT JOIN is always faster." For semantically equivalent patterns, PostgreSQL often produces the **exact same anti-join plan**.

What matters more:

1. Are join conditions exact?
2. Are B-table predicates placed in the right clause?
3. Does NULL require special handling?
4. Are suitable indexes available for the workload?
5. Are statistics fresh enough?
6. Does data have heavy duplicates or skew?
7. Was output verified against business requirements?

Optimizing the wrong question only makes the wrong query run faster.

### 22.4. EXCEPT Can Incur Deduplication Cost

With default `EXCEPT`, PostgreSQL enforces set semantics and must deduplicate according to data types and plan structures. When you want **all A rows not matching B**, `NOT EXISTS` is often more direct without building a key set and re-joining.

Conversely, when comparing **two ID lists** and wanting deduplicated differences, `EXCEPT` expresses the semantics cleanly.

### 22.5. NOT IN and Execution Plans

`NOT IN` must preserve three-valued SQL logic whenever the subquery might yield NULL. This can restrict optimizer rewrites compared to `NOT EXISTS` in some cases, or yield a different `SubPlan`.

When the right-hand column has a `NOT NULL` schema constraint, the planner can sometimes leverage that fact depending on version and query shape. Still, never write a query hoping the optimizer deduces hidden invariants.

**Prioritize clear semantics first, then check execution plans.**

---

## 23. Detecting "Has A, Lacks Qualifying B" in Reports

Reports often classify customers into buckets:

- Has PAID.
- Has orders, yet no PAID.
- Has never ordered.

You can label them using `EXISTS` expressions:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM missing_lab.orders AS o
            WHERE o.customer_id = c.customer_id
              AND o.status = 'PAID'
        )
            THEN 'HAS_PAID_ORDER'

        WHEN EXISTS (
            SELECT 1
            FROM missing_lab.orders AS o
            WHERE o.customer_id = c.customer_id
        )
            THEN 'HAS_ORDER_NO_PAID'

        ELSE 'NO_ORDER'
    END AS customer_order_class
FROM missing_lab.customers AS c
ORDER BY c.customer_id;
```

Result:

| ID | Name | Classification |
| ---: | --- | --- |
| 1 | An | HAS_PAID_ORDER |
| 2 | Bình | HAS_ORDER_NO_PAID |
| 3 | Chi | HAS_PAID_ORDER |
| 4 | Dũng | NO_ORDER |
| 5 | Hà | HAS_PAID_ORDER |
| 6 | Lan | HAS_ORDER_NO_PAID |
| 7 | Mai | NO_ORDER |
| 8 | Nam | HAS_ORDER_NO_PAID |

This shows how one question may combine multiple **existence / non-existence** checks. `CASE` branch order matters: checking for PAID before checking for any order puts every customer into the right bucket.

On large tables, you can alternatively pre-aggregate status flags by `customer_id` and join once, depending on workload and plans. Never assume multiple `EXISTS` automatically cost more without inspecting the execution plan.

---

## 24. Using LEFT JOIN to Audit Missing Relationships

Suppose an ETL pipeline needs to classify whether imported rows matched. Besides `NOT EXISTS`, you can use `LEFT JOIN` with `CASE`:

```sql
SELECT
    r.import_ref,
    r.customer_id,
    CASE
        WHEN r.customer_id IS NULL
            THEN 'MISSING_CUSTOMER_ID'
        WHEN c.customer_id IS NULL
            THEN 'CUSTOMER_NOT_FOUND'
        ELSE 'VALID_REFERENCE'
    END AS validation_status
FROM missing_lab.imported_order_refs AS r
LEFT JOIN missing_lab.customers AS c
  ON c.customer_id = r.customer_id
ORDER BY r.import_ref;
```

The classification matches the `CASE + NOT EXISTS` example in section 14.

`c.customer_id IS NULL` reliably indicates no match because `customers.customer_id` is the PRIMARY KEY.

### 24.1. If the Right-Side Column Is Nullable

When joining on a nullable B column and checking that column, ask:

- If a B row **genuinely matches**, is the checked column guaranteed non-NULL?
- If not, `IS NULL` might reflect **stored NULL data** rather than an outer-join non-match.
- Is there a PK or another always-non-NULL ID column on B?

General template:

```sql
-- Better: check a schema-guaranteed NOT NULL B.id if a B row matched.
SELECT a.*
FROM table_a AS a
LEFT JOIN table_b AS b
  ON b.some_nullable_attribute = a.some_attribute
WHERE b.id IS NULL;
```

If `b.id` is a non-NULL PK, this reliably detects missing matches. Note that `b.some_nullable_attribute = a.some_attribute` still will not match when both are NULL: that belongs to **join rules** and must be decided independently.

---

## 25. Quick Troubleshooting for Common Bugs

| Symptom | Common Cause | Remedy |
| --- | --- | --- |
| `NOT IN (subquery)` returns 0 rows despite missing records | Subquery returns NULL | Review semantics; use `NOT EXISTS` or intentionally filter out NULL |
| `NOT EXISTS` returns rows whose key is NULL | Fails to match on `= NULL` | Add `IS NOT NULL` if targeting supplied IDs, or `IS NOT DISTINCT FROM` if NULLs should match |
| `LEFT JOIN ... IS NULL` returns A rows that actually have B | Checking a nullable B column | Check B's PK / non-NULL column |
| `LEFT JOIN` looking for no PAID returns empty | Placed `o.status = 'PAID'` in `WHERE` alongside `o.id IS NULL` | Move status filter into `ON` |
| "No PAID" includes customers who do have PAID | Used `o.status <> 'PAID'` to find non-paid rows | Use `NOT EXISTS` filtering `status = 'PAID'` |
| Customers without orders get dropped | Used `INNER JOIN` or `WHERE` requiring non-NULL B | Use an anti-join |
| `EXCEPT` drops duplicates | `EXCEPT` deduplicates by default | Use `NOT EXISTS` for A rows or `EXCEPT ALL` if multiplicity matters |
| `EXCEPT` compares wrong meaning | Selected mismatched column meanings across branches | Run `EXCEPT` on the exact keys/tuples to compare |
| `EXCEPT` and `NOT EXISTS` differ on NULLs | Set operations and `=` handle NULL differently | Define NULL policy; use null-safe equality when appropriate |
| Anti-join passes before write, then creates duplicate | Concurrency; two transactions both see missing | Enforce `UNIQUE`/`FOREIGN KEY`, transactions, locks/idempotency |
| Missing-data query is slow | Large B table, missing index, stale stats | Run `EXPLAIN`/`ANALYZE` on SELECT, index join/predicate keys |
| Another tenant's data treated as existing | Omitted `tenant_id` in join condition | Match all composite key columns |
| Query misses end-of-day/month rows | Used `BETWEEN` with midnight end date | Use half-open timestamp intervals |
| API list produces `IN ()` | Empty array not handled | Bind array or branch in application logic |
| Wrong soft-deleted filtering | Unclear whether soft-deleted rows count as existing | Place soft-delete predicate properly |

---

## 26. Practice Exercises

### Exercise 1 — Predict NOT IN with NULL

Predict the output:

```sql
SELECT
    5 NOT IN (1, 2, NULL) AS a,
    2 NOT IN (1, 2, NULL) AS b,
    5 NOT IN (1, 2, 3)    AS c;
```

Explain why `a` is UNKNOWN, `b` is FALSE, and `c` is TRUE. Will `WHERE a` keep or drop the row?

### Exercise 2 — Customers Without Orders

From the lab tables, write:

1. `NOT EXISTS`.
2. `LEFT JOIN ... IS NULL`.
3. `NOT IN` (since the schema guarantees non-NULL keys).
4. `EXCEPT` on `customer_id` alone.

Verify that all four return **4, 7**. Explain why they are equivalent **under the lab constraints**, not for arbitrary nullable schemas.

### Exercise 3 — Customers Without a PAID Order

Write a `NOT EXISTS` query finding customers without a PAID order, expecting **2, 4, 6, 7, 8**.

Then rewrite with `LEFT JOIN` placing `o.status = 'PAID'` in `ON`. Why does `WHERE o.status <> 'PAID'` mean something different?

### Exercise 4 — Has Orders Yet No PAID Order

Use `EXISTS` and `NOT EXISTS` to find customers who:

- Have at least one order of any kind.
- Have no PAID order.

Expected result: **2, 6, 8**. Why are Dũng and Mai not in this set?

### Exercise 5 — No Orders in March 2026

Retrieve customers with no orders in March 2026 UTC, regardless of status.

Write the condition:

```sql
o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
AND o.ordered_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'
```

inside `NOT EXISTS`. Why should `'2026-03-31'` not be used as an inclusive upper bound for timestamps?

### Exercise 6 — No PAID Orders in March

Write `NOT EXISTS` combining `status = 'PAID'` and the March time window. Explain why customers 1 and 3 still appear even though they had PAID orders in other months.

### Exercise 7 — NOT IN on Exclusions Containing NULL

Run:

```sql
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT customer_id
    FROM missing_lab.customer_exclusions
)
ORDER BY c.customer_id;
```

Explain why zero rows are returned. Fix it two ways:

1. Filter `customer_id IS NOT NULL` inside the subquery.
2. Use `NOT EXISTS`.

Verify the output is **1, 3, 4, 5, 7, 8**.

### Exercise 8 — Two Import Error Types

For `imported_order_refs`, separate:

- Rows missing `customer_id`.
- Rows with a `customer_id` not found in `customers`.
- Valid rows.

Expected:

```text
r1 -> VALID_REFERENCE
r2 -> VALID_REFERENCE
r3 -> CUSTOMER_NOT_FOUND
r4 -> MISSING_CUSTOMER_ID
r5 -> CUSTOMER_NOT_FOUND
```

Write one query using `CASE` and `NOT EXISTS`, then rewrite it using `LEFT JOIN`.

### Exercise 9 — EXCEPT and Duplicate Rows

Run:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)
EXCEPT
SELECT id
FROM (VALUES (1)) AS b(id);
```

Then replace `EXCEPT` with `EXCEPT ALL`. Explain the difference between sets and multisets, and when source duplicates must be preserved.

### Exercise 10 — NULL and EXCEPT

Compare these two queries:

```sql
SELECT id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
EXCEPT
SELECT id
FROM (VALUES (NULL::INTEGER)) AS b(id);
```

and:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id = a.id
);
```

Why do the results differ? Update `NOT EXISTS` using `IS NOT DISTINCT FROM` to match the set-difference NULL policy.

### Exercise 11 — Multi-Tenant Composite Keys

Two hypothetical tables have `tenant_id` and `external_id`. Side A has `(10,500)` and `(20,500)`; side B has only `(10,500)`.

Write a `NOT EXISTS` matching **both columns** and explain why comparing `external_id` alone fails. If `external_id` is nullable, should two NULLs count as the same key? List the business decisions needed upfront.

### Exercise 12 — EXPLAIN and Indexes

Inspect:

```sql
EXPLAIN
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Create an index on `orders(customer_id)` or a partial index for `status = 'PAID'` as in section 22. Explain why PostgreSQL may still choose a sequential scan when the table has only 8 orders.

### Exercise 13 — Concurrency Check

Two transactions concurrently check "no record exists with business key X" via `NOT EXISTS`, then both insert.

Answer:

1. Why does `NOT EXISTS` not prevent duplicates under concurrency?
2. Which constraint should enforce uniqueness?
3. With `ON CONFLICT`, how should the application define its update/skip policy?
4. When using `SERIALIZABLE`, which error must the application handle and how should it retry?

---

## 27. Checklist for Designing Missing-Data Queries

| Question | What to Verify |
| --- | --- |
| What is set A? | Identify exact rows to keep |
| What is set B? | Identify table/relation checked for existence |
| What qualifies as a matching B row? | All keys, tenant, status, time range, and business rules |
| Can the right side contain NULL? | Especially avoid `NOT IN` turning UNKNOWN |
| Can the left side contain NULL? | Separate missing IDs from non-existent IDs or use null-safe equality |
| Should NULL match NULL? | Consider `IS NOT DISTINCT FROM` if business-justified |
| Only need to check row existence? | Usually choose `NOT EXISTS` |
| Using `LEFT JOIN`? | Put B predicates in `ON`, check B's PK `IS NULL` |
| Can multiple B rows correspond to one A? | Never confuse "has invalid B" with "has no valid B" |
| Must duplicates in A be preserved? | `NOT EXISTS` keeps them; `EXCEPT` deduplicates by default |
| Only need a distinct list of keys? | `EXCEPT` or `DISTINCT` may fit |
| Soft-delete filtering needed? | Define whether soft-deleted rows count as existing |
| Time filtering needed? | Half-open intervals and explicit timezone |
| Writing `NOT IN` with a subquery? | Ensure both left keys and right key set handle NULLs cleanly |
| Moving missing records into a target table? | `FOREIGN KEY`/`UNIQUE` and transactions are still mandatory |
| Can two transactions concurrently observe "missing"? | Locks, constraints, retries, and idempotency |
| Is the query slow? | `EXPLAIN`/`ANALYZE` on SELECT, index match columns |
| Unexpected empty result? | Check right-side NULLs, `ON`/`WHERE`, filters, and raw data |
| Accepting input from an API? | Bind parameters, handle empty lists, and bound inputs |

## Conclusion

In PostgreSQL, finding "missing records" means identifying **rows in set A that have no corresponding row in set B**. `NOT IN` works properly when compared values are guaranteed non-NULL, yet a single `NULL` from the subquery can turn unmatched comparisons into UNKNOWN and cause `WHERE` to drop every row. This is one of the most important traps in SQL three-valued logic.

Approaches to remember:

- **`NOT EXISTS`**: usually the clearest starting point when checking that no B row matches a condition.
- **`LEFT JOIN ... IS NULL`**: also expresses anti-joins cleanly when matching conditions sit in `ON` and a guaranteed non-NULL B column is checked.
- **`NOT IN`**: suitable when NULLs are fully controlled on both sides, yet requires extreme caution with subqueries and lists that may contain NULL.
- **`EXCEPT`**: fits set-difference comparisons; removes duplicates by default and applies set-op NULL semantics.
- **`IS NOT DISTINCT FROM`**: supports null-safe comparisons when business rules explicitly equate two NULLs.

A correct query also requires the **right relational scope**: composite keys, tenants, statuses, time windows, soft deletes, and proper error classification. When acting on results to write data under concurrent transactions, combine `FOREIGN KEY`, `UNIQUE`, transactions, locks, and idempotency as required—because a missing-record query never creates permanent integrity guarantees by itself.

Once you clearly distinguish "no row exists" from "a row exists with a NULL key," pick the right operator, and place join predicates properly, you can write rock-solid reconciliation, import-validation, and missing-data reports in PostgreSQL.
