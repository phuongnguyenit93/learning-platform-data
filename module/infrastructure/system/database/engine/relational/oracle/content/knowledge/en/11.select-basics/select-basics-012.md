# Explaining and Verifying a Query with Minimal Data

Reading a SQL statement is not just scanning keywords like `SELECT`, `FROM`, or `WHERE` and guessing the output. To truly understand a query, you need to know **which rows exist in the input**, **how each clause transforms the row set**, **how NULL values are handled**, and **how the expected output can be verified independently**.

A highly effective technique when learning Oracle SQL is building a **purposeful minimal dataset**: few tables, few columns, and a handful of rows representing distinct cases. You can compute the result by hand, run the query on Oracle, and compare the two outputs. This catches join bugs, wrong filters, miscounted rows, and misconceptions about aggregate behavior.

This lesson uses a small sales example with customers and orders. Starting from that dataset, we walk from a single-table query to JOIN, LEFT JOIN, GROUP BY, NULLs, and result verification using `MINUS`.

## 1. Why Do We Need Minimal Data?

A query running against a real database may return thousands or millions of rows. When the output is wrong, pinpointing the cause is hard because many factors interact at once: historical data, statuses, missing records, many-to-many relationships, access privileges, and filter conditions.

A small dataset helps you:

- **Predict the outcome upfront:** you can list every row that should be kept or dropped.
- **Isolate a single rule:** for instance, testing only a `WHERE` condition or how `LEFT JOIN` preserves a parent with no child rows.
- **Reproduce bugs:** someone else can run the exact same DDL, DML, and SQL to observe the exact same scenario.
- **Test edge cases:** zero child rows, NULLs, multiple child rows, duplicate values, or invalid statuses.
- **Separate logic bugs from data issues:** if the query fails even on a tiny dataset, you have a concrete counterexample to explain why.

A good dataset does not need many rows. It needs **enough cases to distinguish competing interpretations**. If you create three customers and all three have exactly one order, you still cannot test the difference between JOIN and LEFT JOIN, or between `COUNT(*)` and `COUNT(child_id)`.

## 2. Reading Requirements Before Writing SQL

Suppose the report requirement is:

> "List active customers together with their count of paid orders and total paid amount. Customers without any paid orders must still appear with order count 0 and total amount 0. Sort by total amount descending; if tied, sort by customer ID."

Before writing the query, turn the description into verifiable conditions:

| Requirement | SQL interpretation |
|---|---|
| Active customers only | `WHERE customer.active_flag = 'Y'` |
| Count paid orders only | Status condition placed in `ON` of LEFT JOIN |
| Customers with no orders still appear | Use `LEFT JOIN` from CUSTOMER to ORDER |
| Count orders | `COUNT(order_id)`, do not use `COUNT(*)` for zero-order cases |
| Total amount | `SUM(amount)`, handle NULL with `NVL` if 0 must be displayed |
| Sort by total amount descending | `ORDER BY paid_total DESC` |
| Tie-break by customer ID | Add secondary key `customer_id ASC` |

You could write SQL right away, but without clearly defining what "paid order" means, where "active customer" is checked, or whether customers without orders are kept, the result depends on the author's guesswork.

## 3. Creating a Minimal Dataset in Oracle

We use two tables:

- `LAB_CUSTOMER`: each row is one customer.
- `LAB_ORDER`: each row is one order belonging to a customer.

The dataset needs four scenarios:

1. An active customer with one paid order and one cancelled order.
2. An active customer with two paid orders.
3. An inactive customer who has a paid order.
4. An active customer with no paid orders.

These four cases allow testing status conditions, customer conditions, and LEFT JOIN behavior.

### 3.1. Creating the Tables

Run in a lab schema within a practice PDB. The `LAB_` prefix is reserved for examples; if tables with these names already exist, pick different names rather than overwriting existing objects.

~~~sql
CREATE TABLE lab_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_order (
    order_id    NUMBER(5) PRIMARY KEY,
    customer_id NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    amount      NUMBER(10,2) NOT NULL,
    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customer (customer_id),
    CONSTRAINT ck_lab_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING')),
    CONSTRAINT ck_lab_order_amount
      CHECK (amount >= 0)
);
~~~

Both tables have primary keys to identify rows. The foreign key ensures each order references an existing customer. Check constraints restrict the active flag, order status, and non-negative amounts.

### 3.2. Inserting Customer Data

~~~sql
INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (1, 'An', 'Y');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (2, 'Binh', 'Y');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (3, 'Chi', 'N');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (4, 'Dung', 'Y');
~~~

### 3.3. Inserting Order Data

~~~sql
INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (101, 1, 'PAID', 120);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (102, 1, 'CANCELLED', 30);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (103, 2, 'PAID', 200);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (104, 2, 'PAID', 200);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (105, 3, 'PAID', 500);

COMMIT;
~~~

### 3.4. Inspecting Source Data Before Reading Queries

~~~sql
SELECT customer_id, customer_name, active_flag
FROM lab_customer
ORDER BY customer_id;

SELECT order_id, customer_id, order_status, amount
FROM lab_order
ORDER BY order_id;
~~~

The data can be summarized in tables:

**LAB_CUSTOMER**

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG |
|---:|---|:---:|
| 1 | An | Y |
| 2 | Binh | Y |
| 3 | Chi | N |
| 4 | Dung | Y |

**LAB_ORDER**

| ORDER_ID | CUSTOMER_ID | ORDER_STATUS | AMOUNT |
|---:|---:|---|---:|
| 101 | 1 | PAID | 120 |
| 102 | 1 | CANCELLED | 30 |
| 103 | 2 | PAID | 200 |
| 104 | 2 | PAID | 200 |
| 105 | 3 | PAID | 500 |

Notice the characteristics built into the dataset:

- `An` has two orders, only one of which is `PAID`.
- `Binh` has two `PAID` orders with equal amounts.
- `Chi` has a `PAID` order, yet the customer is inactive.
- `Dung` is active, yet has zero rows in `LAB_ORDER`.

Without these cases, several common query bugs are hard to spot.

## 4. Explaining a Single-Table Query by Predicting Every Row

Before joining, start with a simple SELECT:

~~~sql
SELECT
    customer_id,
    customer_name
FROM lab_customer
WHERE active_flag = 'Y'
ORDER BY customer_id;
~~~

Read clause by clause:

- `SELECT customer_id, customer_name`: retrieves only the two columns to display.
- `FROM lab_customer`: input rows come from the customer table.
- `WHERE active_flag = 'Y'`: keeps only rows whose active flag equals Y.
- `ORDER BY customer_id`: sorts results by ID ascending.

Verify against the source table:

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG | Keep? | Reason |
|---:|---|:---:|:---:|---|
| 1 | An | Y | Yes | Y = Y |
| 2 | Binh | Y | Yes | Y = Y |
| 3 | Chi | N | No | N differs from Y |
| 4 | Dung | Y | Yes | Y = Y |

Expected output:

| CUSTOMER_ID | CUSTOMER_NAME |
|---:|---|
| 1 | An |
| 2 | Binh |
| 4 | Dung |

This is the most fundamental verification method: **mark each row against the WHERE condition**, then compare with Oracle's output. If Oracle also returns `Chi`, inspect the condition or actual stored data before rewriting the query.

### 4.1. SELECT * vs. Selecting Explicit Columns

`SELECT *` requests all columns of the tables in query scope:

~~~sql
SELECT *
FROM lab_customer;
~~~

It is handy when exploring small tables, but in applications select only the needed columns:

~~~sql
SELECT customer_id, customer_name
FROM lab_customer;
~~~

Explicit column selection clarifies output data to readers, reduces data transfer, avoids positional coupling, and limits unexpected breakage when columns are added to the schema. When joining two tables that both have `CUSTOMER_ID`, use table aliases to identify clearly which table each column comes from.

### 4.2. Column Aliases

~~~sql
SELECT
    customer_id AS id,
    customer_name AS full_name
FROM lab_customer;
~~~

`AS` labels an expression in the result set. Aliases make reports readable, yet **do not rename columns in the table**. Oracle permits referencing select-list aliases in `ORDER BY` within the same query block, though you cannot by default use them in `WHERE` at the same level.

## 5. Explaining a JOIN by Matching Rows One by One

To combine customers with orders, use a key condition:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

`c` and `o` are table aliases. `ON o.customer_id = c.customer_id` specifies how the two tables relate. This is an **INNER JOIN** (`JOIN` without `LEFT` defaults to inner join): only row pairs satisfying the condition appear.

Predicted result:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | ORDER_STATUS | AMOUNT |
|---:|---|---:|---|---:|
| 1 | An | 101 | PAID | 120 |
| 1 | An | 102 | CANCELLED | 30 |
| 2 | Binh | 103 | PAID | 200 |
| 2 | Binh | 104 | PAID | 200 |
| 3 | Chi | 105 | PAID | 500 |

`Dung` does not appear because no order row has `CUSTOMER_ID = 4`. In an inner join, a row on the left table that finds no matching row on the right table is excluded from the result.

### 5.1. Why Does One Customer Appear Multiple Times?

`An` has two orders, so the JOIN produces two output rows. This is the normal behavior of a 1:N relationship, not Oracle duplicating data by mistake.

If you want only one row per customer, decide **what information about the orders is needed**:

- Need order count: use `COUNT`.
- Need total amount: use `SUM`.
- Need latest order: use an analytic function or an explicitly ordered row-selection method.
- Need to list every order: keep multiple rows as returned by the JOIN.

Never blindly use `DISTINCT` to "delete duplicate rows," because two distinct orders can share identical selected columns; deduplicating would discard valid data.

### 5.2. A JOIN Without a Condition

~~~sql
-- This example produces a Cartesian product, not a relational join of two tables.
SELECT c.customer_name, o.order_id
FROM lab_customer c
CROSS JOIN lab_order o;
~~~

With 4 customers and 5 orders, `CROSS JOIN` produces **4 × 5 = 20 rows**. If you forget the join condition in older join syntax, a query can accidentally blow up the output. Always verify join keys and expected row counts before running queries against real data.

## 6. LEFT JOIN: Keeping Customers Without Orders

The original requirement states that active customers **must still appear even without any paid orders**. INNER JOIN cannot satisfy that. We need `LEFT JOIN`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

`LEFT JOIN` preserves every row from the left table (`LAB_CUSTOMER`). When no right-side row matches, columns from `LAB_ORDER` are filled with **NULL** in the padded output row.

Result:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | ORDER_STATUS | AMOUNT |
|---:|---|---:|---|---:|
| 1 | An | 101 | PAID | 120 |
| 1 | An | 102 | CANCELLED | 30 |
| 2 | Binh | 103 | PAID | 200 |
| 2 | Binh | 104 | PAID | 200 |
| 4 | Dung | NULL | NULL | NULL |

`Dung` still appears, with NULL order columns. This is the core meaning of LEFT JOIN: **preserve left-side rows even when no matching right-side row exists**.

### 6.1. Placing the Status Condition in ON vs. WHERE?

These two SQL statements are **not equivalent**:

**Approach A — join only paid orders:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

Result:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | AMOUNT |
|---:|---|---:|---:|
| 1 | An | 101 | 120 |
| 2 | Binh | 103 | 200 |
| 2 | Binh | 104 | 200 |
| 4 | Dung | NULL | NULL |

Cancelled order `102` fails the `ON` condition. Nevertheless, `Dung` is still kept because LEFT JOIN found no paid orders.

**Approach B — filter status after the JOIN:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Here `Dung`'s row has `o.order_status = NULL`. The condition `NULL = 'PAID'` is not TRUE, so the row is dropped by WHERE. Only `An` and `Binh` remain. Effectively, this WHERE condition makes the query behave like an inner join with respect to that predicate.

**Reading rule:** Conditions describing *which right-side rows qualify as a match* belong in `ON` when you want to preserve unmatched left-side rows. Conditions describing *which left-side rows belong in the report* go in `WHERE`. Decide by semantics, not habit.

## 7. Main Query: Combining JOIN and Aggregates

Returning to the original requirement:

> List active customers, count PAID orders, and sum PAID amounts. Customers without PAID orders must still appear with 0. Sort by total amount descending, then customer ID ascending on ties.

Query:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY
    paid_total DESC,
    c.customer_id ASC;
~~~

### 7.1. Reading Clause by Clause

**`FROM lab_customer c`**

Uses the customer table as the base set. Alias `c` keeps references short and avoids ambiguity when tables share column names.

**`LEFT JOIN lab_order o`**

Joins orders on `customer_id`. Because it is a LEFT JOIN, customers without matching orders are preserved.

**`AND o.order_status = 'PAID'` in ON**

Only paid order rows count as matches. `CANCELLED` or `PENDING` orders do not contribute to the count or sum.

**`WHERE c.active_flag = 'Y'`**

Excludes inactive customers from the input set. `Chi` is excluded even though she has a PAID order worth 500.

**`GROUP BY c.customer_id, c.customer_name`**

Collapses the post-JOIN rows into one group per customer. Both non-aggregated columns appear in GROUP BY.

**`COUNT(o.order_id)`**

Counts matched orders. Using a right-side column that is NULL when no order exists ensures customer `Dung` counts as 0.

**`NVL(SUM(o.amount), 0)`**

`SUM` over a group with no order values returns NULL. `NVL` converts NULL to 0 so the report satisfies the display requirement.

**`ORDER BY paid_total DESC, c.customer_id ASC`**

Places larger totals first; when totals tie, ascending customer ID keeps order stable and predictable.

### 7.2. Computing the Result by Hand

First consider active customers: `An`, `Binh`, and `Dung`. Next join only PAID orders:

| Customer | Matching PAID rows | COUNT(order_id) | SUM(amount) | After NVL |
|---|---|---:|---:|---:|
| An | 101 / 120 | 1 | 120 | 120 |
| Binh | 103 / 200; 104 / 200 | 2 | 400 | 400 |
| Dung | None | 0 | NULL | 0 |

Final ordered output:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 400 |
| 1 | An | 1 | 120 |
| 4 | Dung | 0 | 0 |

If Oracle returns something different, inspect in sequence: source data, JOIN conditions, predicates in ON, WHERE, GROUP BY, and aggregate functions. Never edit SQL blindly before identifying **which row was added or dropped**.

## 8. COUNT(*), COUNT(column), SUM, and NULL

This is where LEFT JOIN queries most often miscount.

### 8.1. COUNT(*) Differs from COUNT(o.order_id)

Run:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS row_count,
    COUNT(o.order_id) AS paid_order_count
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Expected output:

| CUSTOMER_ID | ROW_COUNT | PAID_ORDER_COUNT |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 4 | 1 | 0 |

For `Dung`, LEFT JOIN still produces **one padded result row**: customer columns have values, while order columns are NULL. Thus `COUNT(*)` counts that padded row as 1. `COUNT(o.order_id)` counts only non-NULL `order_id` values, yielding 0.

If `COUNT(*)` were used in the main report query, Dung would be counted as having **one PAID order**, violating the requirement. This is why understanding how aggregates operate on post-JOIN row sets matters.

### 8.2. COUNT(column) Ignores NULL

`COUNT(expr)` counts rows where `expr` is non-NULL. `COUNT(*)` counts rows regardless of whether columns are NULL.

Example:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(email) AS rows_with_email
FROM lab_customer;
~~~

In our current dataset, `EMAIL` was not created, so this query does not apply literally to the lab table as defined. If the table were extended with a nullable `EMAIL` column, `COUNT(email)` would count only customers with a non-NULL email. Any counted column must exist in the actual schema.

### 8.3. SUM on an Empty Set

`SUM(amount)` sums non-NULL values. When a group has no values to sum, the result is NULL; `NVL(SUM(...), 0)` converts it to 0 when display/calculation rules call for it.

NULL does not always mean 0. For example, "no measurements yet" differs from "measured and equal to 0." Use `NVL` only when business logic confirms both states may be displayed identically in that context.

## 9. GROUP BY and HAVING: Filtering Groups vs. Filtering Rows

`WHERE` filters **rows before grouping**. `HAVING` filters **groups after GROUP BY**.

For example, to list only active customers who have at least two PAID orders:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.amount) AS paid_total
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) >= 2
ORDER BY paid_total DESC;
~~~

The result contains only `Binh` with two orders totaling 400. This example uses INNER JOIN because we only care about groups with at least two PAID orders; customers with zero orders could never pass HAVING anyway.

Compare:

| Clause | Logical phase | Example |
|---|---|---|
| `WHERE` | Before GROUP BY | Keep active customers only; keep data within a date range |
| `HAVING` | After GROUP BY | Keep customers with at least two PAID orders |

Never write `WHERE COUNT(o.order_id) >= 2` in the same query block, because aggregates cannot be used as pre-grouping row filters that way.

## 10. DISTINCT and Duplicate Values

In the dataset, Binh has two orders with amount 200. Those two rows are **two distinct transactions** because their `order_id` values differ.

~~~sql
SELECT DISTINCT amount
FROM lab_order
WHERE customer_id = 2
ORDER BY amount;
~~~

The result has one row (`200`) because DISTINCT eliminates duplicate value combinations in the SELECT list.

If you write:

~~~sql
SELECT DISTINCT order_id, amount
FROM lab_order
WHERE customer_id = 2
ORDER BY order_id;
~~~

The result still has two rows because `ORDER_ID` differs. DISTINCT does not mean "pick one order per customer" unless the selected columns and data constraints happen to produce that effect.

**Never use DISTINCT to cover up a JOIN bug.** If a lookup table has two rows matching one key due to a missing unique constraint, a JOIN can double output rows. Adding DISTINCT may make the report look right on screen while leaving the underlying cardinality bug unfixed.

## 11. NULL and Filter Conditions

In SQL, NULL indicates an unknown/absent value in context; it is not equal to 0, an empty string across all DBMSs, or a concrete value. Oracle treats zero-length character strings in standard character types as NULL under current SQL behavior.

Do not test for NULL with an equals sign:

~~~sql
-- Wrong intent: comparison with NULL never yields TRUE.
SELECT *
FROM lab_order
WHERE order_status = NULL;

-- Correct:
SELECT *
FROM lab_order
WHERE order_status IS NULL;
~~~

In the lab table, `ORDER_STATUS` is declared NOT NULL, so the second query returns 0 rows. It remains the right syntax for finding NULLs in nullable columns.

### 11.1. Three Logical States

A SQL condition can evaluate to:

- **TRUE**: row is kept by WHERE.
- **FALSE**: row is dropped.
- **UNKNOWN**: commonly occurs when comparing with NULL; row is also dropped by WHERE.

Example:

~~~sql
SELECT
    CASE WHEN NULL = 1 THEN 'TRUE'
         WHEN NOT (NULL = 1) THEN 'FALSE'
         ELSE 'UNKNOWN'
    END AS comparison_result
FROM dual;
~~~

The result is `UNKNOWN`. That is why `o.order_status = 'PAID'` in WHERE drops the NULL-padded LEFT JOIN row, making customers without orders disappear.

### 11.2. NVL, COALESCE, and NULL Conditions

`NVL(expr1, expr2)` returns `expr2` when `expr1` is NULL. `COALESCE` returns the first non-NULL expression in its list and accepts multiple arguments:

~~~sql
SELECT
    NVL(NULL, 0) AS nvl_value,
    COALESCE(NULL, NULL, 0) AS coalesce_value
FROM dual;
~~~

In the report query, `NVL(SUM(o.amount), 0)` is appropriate because zero-order totals are specified to display as 0. For text or date columns, choose a type-compatible fallback value with valid business meaning.

## 12. Logical Processing Order of SELECT

When reading a query, picture the standard logical sequence:

~~~text
FROM / JOIN
      |
      v
ON
      |
      v
WHERE
      |
      v
GROUP BY
      |
      v
HAVING
      |
      v
SELECT
      |
      v
DISTINCT
      |
      v
ORDER BY
      |
      v
FETCH FIRST / OFFSET (if present)
~~~

This is the **logical order for understanding results**, not a promise that the optimizer physically executes steps one by one in this diagram's order. Oracle can rewrite queries, push predicates, or change join orders as long as semantics remain preserved. When learning SELECT, logical order explains why:

- SELECT aliases generally cannot be used in WHERE of the same query block.
- WHERE does not directly filter aggregate results; HAVING does.
- LEFT JOIN generates NULL-padded rows before WHERE can drop them.
- ORDER BY sets the final order; without ORDER BY, never assume an output order.

## 13. ORDER BY: Correct Results with Unstable Order

A query without `ORDER BY` does not guarantee rows return in insertion order, primary-key order, or any previously observed display order:

~~~sql
SELECT order_id, amount
FROM lab_order;
~~~

When deterministic ordering is required:

~~~sql
SELECT order_id, amount
FROM lab_order
ORDER BY amount DESC, order_id ASC;
~~~

When two rows share the same `AMOUNT`, `ORDER_ID` acts as the secondary tie-breaker. Writing only `ORDER BY amount DESC` leaves the order among equal-amount rows unspecified.

In the main query, `ORDER BY paid_total DESC, customer_id ASC` makes output predictable. That is essential when verifying results by hand or writing automated tests.

## 14. FETCH FIRST and Row Limiting in Oracle

Oracle supports row-limiting syntax:

~~~sql
SELECT order_id, customer_id, amount
FROM lab_order
ORDER BY amount DESC, order_id
FETCH FIRST 3 ROWS ONLY;
~~~

On the current dataset, the top three rows by descending amount are orders 105 (500), 103 (200), and 104 (200). `ORDER_ID` as tie-breaker guarantees order between the two 200-amount rows.

| ORDER_ID | AMOUNT |
|---:|---:|
| 105 | 500 |
| 103 | 200 |
| 104 | 200 |

Do not treat `ROWNUM` as if it always applies after ORDER BY in the same query block. In older `ROWNUM` patterns, you must track selection vs. sorting scope; `FETCH FIRST` is usually clearer for result limiting.

When paginating with `OFFSET ... FETCH NEXT ...`, use a deterministic ORDER BY. When data changes between page reads, applications still need an appropriate consistency policy; offset does not automatically freeze a business snapshot across the whole pagination flow.

## 15. Multi-Layer Result Verification

Never run a SELECT once and stop at "looks about right." A repeatable verification workflow includes:

1. **Verify the dataset:** row counts, keys, statuses, and source relationships match assumptions.
2. **Predict manually:** list explicitly which rows should appear and which should be excluded.
3. **Run the query:** keep the prepared SQL and data unchanged.
4. **Compare counts:** do row counts and aggregate values match?
5. **Test deliberate variations:** switch LEFT JOIN to JOIN, move an ON predicate to WHERE, swap COUNT(column) for COUNT(*).
6. **Verify expected output with independent SQL:** compare the actual result set against an expected set.

### 15.1. Checking Source Counts

~~~sql
SELECT COUNT(*) AS customer_rows
FROM lab_customer;

SELECT COUNT(*) AS order_rows
FROM lab_order;

SELECT active_flag, COUNT(*) AS customer_count
FROM lab_customer
GROUP BY active_flag
ORDER BY active_flag;

SELECT order_status, COUNT(*) AS order_count
FROM lab_order
GROUP BY order_status
ORDER BY order_status;
~~~

Expected results:

| Check | Result |
|---|---:|
| Total customers | 4 |
| Total orders | 5 |
| Active customers (Y) | 3 |
| Inactive customers (N) | 1 |
| PAID orders | 4 |
| CANCELLED orders | 1 |

If source counts are off, do not blame the main SELECT yet. The seed script may have been run multiple times, lab data altered, or you may be connected to the wrong schema/PDB.

### 15.2. Inspecting Groups Before Aggregation

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

Inspect this intermediate row set before adding `GROUP BY`. If `Dung` is missing, the bug happened before aggregation. If `An` also includes her CANCELLED order, the status condition in ON is wrong or a different query is running.

### 15.3. Comparing Against Expected Output Using MINUS

Oracle provides the `MINUS` set operator, which returns rows present in the left set but absent from the right set. You can define an expected result set and an actual result set, then compare in both directions.

~~~sql
WITH expected AS (
    SELECT 2 AS customer_id,
           'Binh' AS customer_name,
           2 AS paid_order_count,
           400 AS paid_total
    FROM dual
    UNION ALL
    SELECT 1, 'An', 1, 120 FROM dual
    UNION ALL
    SELECT 4, 'Dung', 0, 0 FROM dual
),
actual AS (
    SELECT
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) AS paid_order_count,
        NVL(SUM(o.amount), 0) AS paid_total
    FROM lab_customer c
    LEFT JOIN lab_order o
      ON o.customer_id = c.customer_id
     AND o.order_status = 'PAID'
    WHERE c.active_flag = 'Y'
    GROUP BY c.customer_id, c.customer_name
)
SELECT 'EXPECTED_NOT_ACTUAL' AS difference,
       customer_id, customer_name,
       paid_order_count, paid_total
FROM (
    SELECT * FROM expected
    MINUS
    SELECT * FROM actual
)
UNION ALL
SELECT 'ACTUAL_NOT_EXPECTED',
       customer_id, customer_name,
       paid_order_count, paid_total
FROM (
    SELECT * FROM actual
    MINUS
    SELECT * FROM expected
)
ORDER BY difference, customer_id;
~~~

If zero rows return, the two result sets **are identical across the selected columns**. If `EXPECTED_NOT_ACTUAL` appears, an expected row is missing or has mismatched values in `actual`. If `ACTUAL_NOT_EXPECTED` appears, the query returned extra rows or unexpected values.

`MINUS` is a set operator with duplicate-elimination semantics; if a test must compare **multisets** and count duplicate occurrences, also compare counts per tuple with `GROUP BY`/`COUNT(*)`. In our example, `CUSTOMER_ID` guarantees one row per customer in the aggregated output, so this comparison is sufficient.

### 15.4. Checking Individual Values Instead of Only Final Totals

A matching grand total does not prove every underlying row is right. For example, one skipped order and one double-counted order of equal value can cancel out to give a seemingly valid total. Therefore:

- Verify the **list of order_ids** before summing amounts.
- Verify **order counts** independently of total amounts.
- Cross-check row by row whenever feasible.
- Use stable sort keys in ORDER BY and test assertions.

Thorough verification combines **intermediate row sets**, **aggregates**, and **final result-set diffs**.

## 16. Using Minimal Data to Catch Common SQL Bugs

### Bug 1: INNER JOIN Drops Customers Without Orders

**Symptom:** Dung is missing even though customers without orders must appear.

**Cause:** Used `JOIN` instead of `LEFT JOIN`.

**Fix:** Change the join type, put the right-side status condition in ON, and check NULL-padded columns.

### Bug 2: Predicate in WHERE Drops LEFT JOIN NULL Rows

**Symptom:** LEFT JOIN is in the SQL, yet customers without orders still vanish.

**Cause:** Wrote `WHERE o.order_status = 'PAID'`.

**Fix:** Move the match predicate for orders into ON when unmatched customers must be preserved.

### Bug 3: Using COUNT(*) to Count Child Records

**Symptom:** A customer with no orders is counted as 1.

**Cause:** COUNT(*) counts the NULL-padded LEFT JOIN row.

**Fix:** Use `COUNT(o.order_id)` or a non-NULL child key.

### Bug 4: JOIN Multiplies Monetary Totals

**Symptom:** Totals double or multiply after joining an extra table.

**Cause:** A 1:N or N:M relationship creates multiple intermediate rows; aggregates are evaluated after multiplication.

**Fix:** Identify each table's grain and JOIN cardinality. When joining another detail table, pre-aggregate each side in a CTE/subquery before joining.

For example, if each order has multiple line items and multiple payments, joining `ORDER_ITEM` directly to `PAYMENT` creates a cross product between the two child sets. Line-item totals and payment totals must be aggregated at the order grain before combining.

### Bug 5: Using DISTINCT to Patch a Broken JOIN

**Symptom:** Row count drops to look normal, yet aggregate sums or detail columns remain wrong.

**Cause:** DISTINCT removes duplicate output tuples without fixing the underlying row multiplication.

**Fix:** Inspect join keys, unique constraints, and granularity; fix the query model.

### Bug 6: No ORDER BY Yet Expecting Consistent Order

**Symptom:** An appears first on one run, Binh on another.

**Cause:** SQL guarantees no output order without ORDER BY.

**Fix:** Add sort columns and a sufficient tie-breaker.

### Bug 7: Filtering Aggregates in WHERE

**Symptom:** Oracle raises an error when COUNT/SUM is placed in WHERE of the same query block.

**Cause:** WHERE filters rows before GROUP BY.

**Fix:** Use HAVING for group-level conditions.

## 17. When a Query Is Logically Correct Yet Slow

**Verifying correctness** and **evaluating performance** are separate tasks. On a five-row dataset, a full table scan can be optimal; never create indexes just to make a tiny plan look complex.

On large datasets, you can inspect the execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_total DESC, c.customer_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows an estimated plan for the parse environment; it neither proves result correctness nor gives actual runtime execution metrics. When authorized and after executing the query, `DBMS_XPLAN.DISPLAY_CURSOR` provides actual cursor plan details, especially with runtime statistics enabled.

Key performance questions:

- Are predicates on large tables selective?
- Do join columns have suitable indexes and fresh statistics?
- Is the query reading more rows than needed?
- Are there implicit type conversions on join/filter columns?
- Does a bad-cardinality join multiply rows before aggregation?
- Can filtering or pre-aggregation happen before joining to shrink intermediate sets?

**Never alter a correct query just to force a specific plan** without understanding the workload, statistics, and real cost. Minimal data primarily verifies logic; performance evaluation requires representative data and environments.

## 18. Reproducing Verification Tests in Another Environment

A SQL example is truly useful only when someone else can re-run it. Package it cleanly:

~~~text
select-lab/
├── 01_create_tables.sql
├── 02_insert_minimal_data.sql
├── 03_verify_source_data.sql
├── 04_query_steps.sql
├── 05_expected_results.md
└── README.md
~~~

Each file's purpose:

- `01_create_tables.sql`: DDL creating tables and constraints.
- `02_insert_minimal_data.sql`: DML inserting the minimal dataset, plus `COMMIT`.
- `03_verify_source_data.sql`: verifies row counts, keys, and status distribution.
- `04_query_steps.sql`: single-table, JOIN, LEFT JOIN, and aggregate queries.
- `05_expected_results.md`: expected outputs and explanations of kept/dropped rows.
- `README.md`: required Oracle version, PDB/service, schema, and execution sequence.

Never store passwords in these files. Use a least-privilege lab account connected to the right PDB. In CI environments, provision an isolated test schema/database and tear it down via controlled procedures.

### 18.1. Is the Seed Script Safe to Re-Run?

Direct `INSERT` statements in section 3 are meant for initial creation only. Re-running them will fail on duplicate primary keys. Options:

- Use a fresh lab database/schema per run.
- Use a dedicated reset script once confirmed the lab data does not need to be kept.
- Write idempotent seeds using `MERGE` or existence checks by business key.

Never put `DROP TABLE` or `TRUNCATE TABLE` automatically at the top of a shared script if someone might run it while pointed at the wrong schema/PDB. Resets must make scope explicit and require appropriate confirmation.

## 19. Self-Check Exercises

### Exercise 1 — Predicting INNER JOIN

On the initial dataset, run:

~~~sql
SELECT c.customer_name, o.order_id
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

**Question:** How many rows return? Which customer is missing and why?

**Guided answer:** 5 rows; Dung is missing because she has no orders. Chi appears because she has an order, even though she is inactive; the query did not filter the active flag.

### Exercise 2 — Moving a Predicate

Run both queries and record row counts:

~~~sql
-- A
SELECT c.customer_id, o.order_id
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y';

-- B
SELECT c.customer_id, o.order_id
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID';
~~~

**Question:** Why does A include Dung while B does not?

**Guided answer:** A restricts only which right-side rows count as matches; B filters after the join and eliminates the NULL-padded row because the comparison is not TRUE.

### Exercise 3 — COUNT

~~~sql
SELECT
  c.customer_name,
  COUNT(*) AS count_star,
  COUNT(o.order_id) AS count_order
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_name
ORDER BY c.customer_name;
~~~

**Question:** Why does Dung have `COUNT_STAR = 1` yet `COUNT_ORDER = 0`?

**Guided answer:** The padded LEFT JOIN row still exists; `order_id` is NULL, so `COUNT(order_id)` skips it.

### Exercise 4 — Adding Another Customer Without Orders

~~~sql
INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (5, 'Ha', 'Y');
COMMIT;
~~~

Re-run the main query. Predict how many orders and what total amount Ha appears with.

**Guided answer:** Ha has 0 PAID orders and total 0, just like Dung. If she fails to appear, inspect the join type and status predicate.

### Exercise 5 — Adding a PENDING Order

~~~sql
INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (106, 4, 'PENDING', 700);
COMMIT;
~~~

**Question:** Does Dung's result in the main query change?

**Guided answer:** No. The status condition in ON matches only PAID; PENDING is excluded. Dung still has 0 PAID orders and total 0.

### Exercise 6 — Row Multiplication Bug

Imagine a `LAB_ORDER_TAG` table with multiple tags per order. Joining ORDER with ORDER_TAG before summing `amount` can multiply total amounts by tag count. Create an order with two tags and inspect the intermediate row count.

**Question:** How do you avoid double-counting order amounts?

**Guided answer:** Identify the grain; aggregate tags separately or aggregate orders at the order level before joining the tag set, depending on report goals. Never patch it with DISTINCT after totals were already multiplied.

### Exercise 7 — Comparing with MINUS

Change one expected value in section 15.3—for example, change Binh's total from 400 to 390. Run the two-way comparison query.

**Question:** Why do we need both `EXPECTED_NOT_ACTUAL` and `ACTUAL_NOT_EXPECTED`?

**Guided answer:** One direction catches missing or mismatched expected rows; the other catches unexpected extra rows or values.

## 20. Process for Explaining Any SELECT Query

When given a new query, follow this sequence:

1. **Restate the requirement in business terms:** each output row represents which entity, and which edge cases must be kept?
2. **Identify the grain of source tables:** is each row a customer, an order, or a line item?
3. **List join keys:** which PK/FK does each JOIN use; is cardinality 1:1, 1:N, or N:M?
4. **Build a purposeful tiny dataset:** include at least one matching case, non-matching case, multi-child case, and NULL if relevant.
5. **Read each predicate:** is it in ON or WHERE, and does it drop padded rows?
6. **Evaluate per-group aggregates:** what does COUNT count, can SUM be NULL, and could rows be multiplied?
7. **Check ordering and limits:** does ORDER BY have enough tie-breakers, and what is FETCH FIRST limiting?
8. **Compare output:** diff actual rows against expected rows using MINUS or an equivalent check.
9. **Only after logic is verified, analyze performance:** execution plan, indexes, statistics, actual row counts, and network fetch.

Diagram:

~~~text
BUSINESS REQUIREMENT
       |
       v
IDENTIFY GRAIN AND RELATIONSHIPS
       |
       v
CREATE MINIMAL DATASET
       |
       v
TRACE FROM / JOIN / ON / WHERE
       |
       v
GROUP BY / HAVING / AGGREGATES
       |
       v
ORDER BY / FETCH
       |
       v
PREDICT RESULT BY HAND
       |
       v
RUN SQL AND COMPARE
       |
       v
LOGIC CORRECT? ── No ──▶ Find wrong rows and root cause
       |
      Yes
       |
       v
EVALUATE PERFORMANCE ON REPRESENTATIVE DATA
~~~

You truly understand a query when you can **explain why every single row appears or does not appear**, predict row counts and output values, and prove your prediction on a minimal dataset. For Oracle SQL, this habit is especially valuable for JOIN, LEFT JOIN, NULL, and aggregates: just a few well-chosen rows reveal distinctions that a huge production table easily hides.
