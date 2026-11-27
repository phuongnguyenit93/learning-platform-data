# EXISTS, NOT EXISTS, and Testing Existence Relationships in Oracle Database

When querying relational data, many questions do not require retrieving detailed columns from a child table. We only need to know **whether at least one related row exists**, or **that no row satisfies a condition**. For example:

- List customers who have placed at least one order.
- Find products that have never been sold.
- Find departments with at least one active employee.
- Find invoices without a payment.
- Select only accounts with no transactions flagged for risk.

Oracle SQL provides two conditions built for this:

- **EXISTS** evaluates to true when the subquery returns at least one row.
- **NOT EXISTS** evaluates to true when the subquery returns zero rows.

These two conditions are typically written with a **correlated subquery**, meaning the subquery references columns from the current row of the outer query. Relationally, EXISTS corresponds to a **semi-join**, and NOT EXISTS corresponds to an **anti-join**. This style directly expresses an existence check and avoids duplicating parent rows when multiple child rows exist.

This lesson explains syntax, query correlation in Oracle, differences between EXISTS and JOIN, NOT IN's NULL traps, usage in DML, performance, correctness under concurrent transactions, and a hands-on lab.

## 1. What Does EXISTS Check?

EXISTS is a logical condition. It cares only whether the subquery returns **at least one row**. Values in the subquery's SELECT list are not what determines the outcome.

Syntax:

~~~sql
WHERE EXISTS (
    subquery
)
~~~

Example:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT NULL
    FROM dual
);
~~~

The subquery reads one row from DUAL, so EXISTS is true. Even though the SELECT list is NULL, the row still exists.

Conversely:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT 1
    FROM dual
    WHERE 1 = 0
);
~~~

The subquery returns zero rows, so EXISTS is false; the outer result has zero rows.

### 1.1 SELECT 1, SELECT NULL, or SELECT *?

All of these forms are valid inside EXISTS:

~~~sql
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)
~~~

~~~sql
WHERE EXISTS (SELECT NULL FROM orders o WHERE o.customer_id = c.customer_id)
~~~

~~~sql
WHERE EXISTS (SELECT * FROM orders o WHERE o.customer_id = c.customer_id)
~~~

As an existence check, they are equivalent: Oracle only needs to know whether the subquery produces a row. Using `SELECT 1` is a readable convention because it signals clearly that the author does not need child column values.

`SELECT 1` is not a mandatory speed trick. The Oracle Optimizer can transform the query and avoid fetching all columns listed in EXISTS's SELECT list when they do not affect semantics.

### 1.2 EXISTS does not count rows

Whether the subquery has 1 matching row or 10,000, EXISTS still returns a single boolean truth value. It does not return the child row count.

If you need a count, use COUNT:

~~~sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
~~~

If you only need a yes/no existence check, EXISTS generally states the intent more clearly than `COUNT(*) > 0`.

### 1.3 Warning: aggregates without GROUP BY always produce one row

Query:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT COUNT(*)
    FROM orders o
    WHERE o.customer_id = -999
);
~~~

EXISTS here is still true, even when customer_id -999 has zero orders. Reason: a `COUNT(*)` aggregate query without `GROUP BY` returns one row containing COUNT equal to 0 when the input is empty. That aggregate row still exists.

To test existence, write:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

Or if you already have a reason to aggregate, check `COUNT > 0` inside an appropriate query layer. For a pure existence check, COUNT is unnecessary.

## 2. Correlated Subqueries

A subquery is **correlated** when it references columns from an outer query block. Example:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Read semantically:

1. Take a customer `c` in the outer query.
2. Search `ORDERS` for at least one row `o` whose `CUSTOMER_ID` equals the current customer ID.
3. If found, keep that customer.
4. If not found, exclude that customer.

The result is the list of customers **who have had at least one order**.

### 2.1 Why are aliases needed?

Aliases `c` and `o` distinguish column sources:

- `c.customer_id` is the customer ID from the outer query.
- `o.customer_id` is the customer ID stored on the order.

If both tables have `CUSTOMER_ID` and you do not qualify them, SQL can become ambiguous or easy to misread. Explicit aliasing is good practice.

### 2.2 Correlated does not mean Oracle must execute sequentially per row

Logically, you can imagine the subquery being evaluated for each customer row. However, do not conclude Oracle always executes it by running an independent subquery once per row.

The optimizer can **unnest** the subquery and convert EXISTS into a semi-join or another access strategy. The execution plan depends on statistics, indexes, row counts, filter predicates, and Oracle version.

Thus, a correlated subquery is a logical expression, not a promise about physical execution mechanics.

### 2.3 EXISTS with multiple related conditions

Example: retrieving only customers who have a paid order with a total above a threshold:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.total_amount >= 1000000
);
~~~

The subquery needs just one row satisfying **all** conditions. There is no need to pull all orders out and filter in the application.

### 2.4 EXISTS with date/time conditions

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.created_at >= DATE '2026-11-01'
      AND o.created_at <  DATE '2026-12-01'
);
~~~

This example finds customers with at least one order in November 2026. The half-open interval avoids missing late-day timestamps and avoids specifying `23:59:59`.

## 3. NOT EXISTS: Checking That No Related Row Exists

NOT EXISTS is true when the subquery returns **zero rows**:

~~~sql
WHERE NOT EXISTS (
    subquery
)
~~~

Example: finding customers who have never placed an order:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

For each customer:

- If at least one matching order exists, EXISTS is true and NOT EXISTS is false.
- If no matching order exists, EXISTS is false and NOT EXISTS is true.

### 3.1 NOT EXISTS does not mean a child column is NULL

NOT EXISTS checks that **no row satisfies the conditions**, not whether a particular column is NULL.

Compare:

~~~sql
-- Customers with no orders:
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
-- Customers who have an order whose shipped date is unrecorded:
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.shipped_at IS NULL
)
~~~

The first query asks whether a customer–order relationship exists. The second asks whether an order exists in a state missing a shipping date. Those are two different questions.

### 3.2 Conditions inside NOT EXISTS decide which relationship is excluded

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

The result is products that have never appeared in any order line item.

If you add:

~~~sql
AND o.status = 'PAID'
~~~

in a subquery joined to ORDERS, the meaning changes to products not appearing in paid orders. Place predicates on the exact relationship you intend to test; missing or misplaced predicates can make reports too broad or too narrow.

### 3.3 NOT EXISTS with business statuses

Finding orders without a payment:

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments p
    WHERE p.order_id = o.order_id
);
~~~

If business logic only counts confirmed payments as completed:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
~~~

Then orders having PENDING or FAILED payment records are still returned. Predicates must accurately reflect the status the business treats as completed.

## 4. EXISTS as Semi-Join and NOT EXISTS as Anti-Join

This is a helpful relational perspective when comparing with JOINs.

### 4.1 Semi-join: keeping parent rows with at least one child row

EXISTS typically expresses a **semi-join**: returning a parent-table row if at least one matching row exists in the child table.

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

A customer with 1 order or 100 orders still appears once in the result, assuming no other row-multiplying source exists in the outer query.

### 4.2 JOIN can duplicate parent rows

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

If a customer has three orders, the customer row appears three times. That is normal JOIN behavior because the query is returning customer–order pairs.

If the goal is solely a list of customers who made purchases, EXISTS usually fits the intent better. Using JOIN followed by DISTINCT can produce the same list in some cases, yet logically forms all paired rows before deduplicating.

### 4.3 NOT EXISTS as anti-join

NOT EXISTS typically expresses an **anti-join**: returning parent rows that have no matching child row.

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

These are products with no order-item relationship. This is more direct than LEFT JOIN followed by checking a child column `IS NULL`, especially when the checked column might be nullable.

### 4.4 LEFT JOIN ... IS NULL can also express anti-join

Another way to write it:

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
LEFT JOIN order_items oi
  ON oi.product_id = p.product_id
WHERE oi.product_id IS NULL;
~~~

Here the checked child column is the join key, assuming it is non-NULL on any valid matched row. Picking an unsuitable nullable child column could misclassify matched rows as unmatched.

NOT EXISTS states "no matching child row exists" directly, making it easier to read and less dependent on choosing the right sentinel column on the child side.

### 4.5 When do you need JOIN instead of EXISTS?

| Goal | Usually Suitable Approach |
|---|---|
| Only need to know if at least one child row exists | EXISTS |
| Only need to know that no matching child row exists | NOT EXISTS |
| Need columns from both parent and child | JOIN |
| Need total count of child rows | JOIN + GROUP BY or scalar COUNT |
| Need one specific child value by priority rule | JOIN with row selection logic, analytic function, or scalar subquery |
| Need to preserve parent even without children while displaying child columns | LEFT JOIN |

Do not choose EXISTS simply thinking it is always faster. Choose based on **result shape and business semantics** first, then measure performance.

## 5. NULL and NOT IN: A Critical Trap

One of the most common reasons to choose NOT EXISTS is avoiding the NULL trap of NOT IN.

### 5.1 NOT IN can return zero rows when the subquery contains NULL

Suppose:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

If the subquery returns a list containing at least one NULL, the NOT IN expression for any non-matching value becomes UNKNOWN instead of TRUE. WHERE keeps only rows where the condition is TRUE, so the expected "no orders" rows vanish.

This is a consequence of SQL three-valued logic:

- TRUE: condition holds.
- FALSE: condition fails.
- UNKNOWN: truth cannot be determined, usually when comparing with NULL.

Simple example:

~~~sql
SELECT 1 AS value
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

The query returns zero rows because comparing against NULL prevents NOT IN from evaluating to TRUE.

### 5.2 NOT EXISTS does not fall into this inner-subquery NULL trap

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

If an `ORDERS` row has a NULL `CUSTOMER_ID`, it does not satisfy equality with any specific customer ID. That NULL row does not cause all customers to be eliminated. NOT EXISTS asks only whether any row satisfies the current equality relationship.

This is an important practical difference between NOT EXISTS and NOT IN.

### 5.3 NOT IN can still be used if NULLs are explicitly excluded

If you are certain the subquery cannot contain NULL, or you filter them out:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

you can avoid the NULL trap in the inner list. Nevertheless, when testing relational existence, NOT EXISTS usually expresses the intent more directly.

### 5.4 NULL in the outer key

Consider:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

If `c.customer_id` is NULL, `o.customer_id = NULL` is never TRUE for any row. Thus the subquery finds no matches and NOT EXISTS evaluates to TRUE, so parent rows with NULL keys can be returned.

If business logic requires considering only customers with valid non-NULL IDs, add:

~~~sql
AND c.customer_id IS NOT NULL
~~~

Do not confuse NOT EXISTS with a NOT NULL check. To exclude NULL keys, state `IS NOT NULL` explicitly.

### 5.5 When NULL is treated as equal to NULL by business rules

In standard SQL, equality does not treat NULL as equal to NULL. If business rules treat two NULLs as belonging to the same group when comparing relationships, write an explicit null-safe condition:

~~~sql
WHERE (
       o.external_ref = c.external_ref
       OR (o.external_ref IS NULL AND c.external_ref IS NULL)
)
~~~

Complete example:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM legacy_orders o
    WHERE o.customer_id = c.customer_id
      AND (
           o.external_ref = c.external_ref
           OR (o.external_ref IS NULL AND c.external_ref IS NULL)
      )
);
~~~

Use NULL-safe matching only when NULL truly denotes the same logical value under business rules. If NULL means "unknown," treating two NULLs as equal can pair unrelated records.

## 6. EXISTS and NOT EXISTS Across Multiple Relationships

### 6.1 Customers with orders and payments

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

Read outside-in:

1. Find customers.
2. Check if the customer has orders.
3. For a related order, check if it has a confirmed payment.
4. Keep the customer only if an order exists satisfying both relationships.

This is nested EXISTS. It does not duplicate customers even if a customer has multiple orders and an order has multiple payment rows.

### 6.2 Customers with orders lacking confirmed payment

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

This returns customers who have at least one order without a CONFIRMED payment. A customer may still have other paid orders; the condition only requires one order lacking confirmed payment.

If the requirement is customers **who have orders and every single order is paid**, the logic differs. You can express it with nested NOT EXISTS to find unpaid orders and negate that:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

The first EXISTS ensures the customer has at least one order. The second NOT EXISTS ensures no order lacks a confirmed payment. Without the first EXISTS, customers with zero orders would also satisfy "no unpaid orders exist" by vacuous truth.

### 6.3 Many-to-many relationships via a junction table

Suppose STUDENTS and COURSES are linked through ENROLLMENTS. Find students enrolled in at least one course:

~~~sql
SELECT s.student_id,
       s.student_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM enrollments e
    WHERE e.student_id = s.student_id
);
~~~

Find courses with no enrolled students:

~~~sql
SELECT c.course_id,
       c.course_name
FROM courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM enrollments e
    WHERE e.course_id = c.course_id
);
~~~

`ENROLLMENTS` is the junction table. EXISTS checks the relationship through the bridge table without returning enrollment rows.

## 7. EXISTS in the SELECT List to Create Flags

You can use EXISTS inside CASE to return a status label:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       CASE
         WHEN EXISTS (
             SELECT 1
             FROM orders o
             WHERE o.customer_id = c.customer_id
         )
         THEN 'HAS_ORDER'
         ELSE 'NO_ORDER'
       END AS order_status
FROM customers c;
~~~

Oracle SQL does not use a general BOOLEAN type as a standard SQL result column type the way programming languages do. CASE converts the EXISTS condition into a character value for output.

Another option is a numeric expression:

~~~sql
CASE WHEN EXISTS (...) THEN 1 ELSE 0 END AS has_order
~~~

This is useful for APIs or reports needing a 0/1 flag. However, if you only want to filter customers who have orders, placing EXISTS in WHERE is cleaner.

## 8. Using EXISTS in UPDATE and DELETE

EXISTS is not restricted to SELECT. It can check relationships before executing DML.

### 8.1 UPDATE based on related data

Example marking customers ACTIVE if they have a paid order:

~~~sql
UPDATE customers c
SET customer_status = 'ACTIVE'
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

The EXISTS condition determines which `CUSTOMER` rows get updated. This is real DML that modifies data; verify scope, privileges, transactions, and WHERE conditions before running.

### 8.2 DELETE based on non-existence

Example removing staging records no longer linked to any customer:

~~~sql
DELETE FROM staging_customer s
WHERE NOT EXISTS (
    SELECT 1
    FROM customers c
    WHERE c.customer_id = s.customer_id
);
~~~

Do not run this example on live data without confirming retention policies. In production, auditing, retention windows, or foreign key handling may be required before deleting.

### 8.3 INSERT ... SELECT ... WHERE NOT EXISTS

A common pattern to insert only if a matching record does not yet exist:

~~~sql
INSERT INTO customer_flags (customer_id, flag_code)
SELECT :p_customer_id, :p_flag_code
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_flags f
    WHERE f.customer_id = :p_customer_id
      AND f.flag_code = :p_flag_code
);
~~~

This avoids duplicate inserts in sequential flows. However, it **does not guarantee uniqueness under concurrent transactions**: two sessions can simultaneously see no existing row and both insert before either commits.

If uniqueness is a data invariant, create an appropriate UNIQUE constraint or unique index and handle duplicate-key errors in the application. NOT EXISTS does not replace integrity constraints.

## 9. Correctness Under Concurrent Transactions

A common design mistake is using:

~~~sql
IF NOT EXISTS THEN INSERT
~~~

as if the check and write steps were an atomic operation.

Scenario:

1. Session A checks `customer_id=10` and `flag_code='VIP'`, sees no row.
2. Session B checks the same pair, sees no row.
3. Session A INSERTs.
4. Session B INSERTs.
5. Without a unique constraint, two duplicate rows are stored.

NOT EXISTS answers strictly based on the statement's snapshot/visibility at execution time. It does not lock a logical "gap" to stop other transactions from inserting the same values.

### 9.1 Use a UNIQUE constraint for uniqueness

~~~sql
ALTER TABLE customer_flags
ADD CONSTRAINT uq_customer_flag
UNIQUE (customer_id, flag_code);
~~~

Then the application can attempt INSERT and handle unique constraint violations using appropriate retry/re-read rules. If UPSERT is needed, consider MERGE or duplicate-key handling, while still understanding concurrency behavior and data constraints.

### 9.2 EXISTS for business checks, constraints for data protection

The two mechanisms solve different problems:

- EXISTS/NOT EXISTS: conditional querying or manipulation based on currently visible relationships.
- PRIMARY KEY/UNIQUE/FOREIGN KEY/CHECK: enforcing data invariants in the database.

An application may use NOT EXISTS to avoid unnecessary insert attempts, yet a UNIQUE constraint is the final safeguard guaranteeing zero duplicates across all accepted database transactions.

## 10. Performance and Execution Plans

### 10.1 Indexes on linking columns

For the query:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Indexes to consider depending on workload:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Or if status is frequently filtered too:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Index column order and whether to create an index must be decided from real queries, selectivity, row counts, data distribution, DML overhead, and existing indexes. Do not create both indexes just because of this example.

### 10.2 NOT EXISTS also benefits from proper indexes

Example:

~~~sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

An index on `ORDER_ITEMS(PRODUCT_ID)` can help Oracle verify the presence of related rows efficiently. Yet if the child table is small or most products are returned, the optimizer may pick another strategy.

### 10.3 Semi-join and anti-join in execution plans

The Oracle optimizer can transform EXISTS into physical join methods such as:

- NESTED LOOPS SEMI.
- HASH JOIN SEMI.
- MERGE JOIN SEMI.
- Corresponding ANTI variants for NOT EXISTS.

Exact operation names depend on Oracle version, query, and plan. Importantly, a semi-join only needs to confirm a match exists, without producing all parent–child pairs like an ordinary join.

### 10.4 Subquery unnesting

Oracle can convert correlated subqueries into equivalent joins for optimization. This is called subquery unnesting. Certain constructs, functions, or semantic restrictions can prevent the transformation.

Do not add hints like `UNNEST` or `NO_UNNEST` merely assuming correlated subqueries are always slow. Inspect the execution plan and runtime metrics first.

### 10.5 EXPLAIN PLAN

In a lab schema with privileges:

~~~sql
EXPLAIN PLAN FOR
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN shows the estimated plan. When tuning production queries, inspect the actual cursor plan and runtime statistics as appropriate; never judge speed solely from a single operation line or estimated cost number.

## 11. EXISTS, IN, and JOIN: Choosing by Intent

### 11.1 EXISTS and IN

Two approaches can be equivalent under certain conditions:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

With non-NULL comparison keys or controlled semantics, both queries can return the same customer set. However, EXISTS expresses the correlated relationship and is usually easier to extend with extra child-table conditions.

IN checks whether a value belongs to a set. EXISTS checks whether a row satisfies a correlated condition. Pick according to intent and watch out for NULLs.

### 11.2 NOT EXISTS and NOT IN

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The two are not always equivalent when the inner set contains NULL or the outer key can be NULL. NOT IN can evaluate to UNKNOWN due to NULLs in the list; NOT EXISTS tests the equality relation directly. If you also want to exclude NULL outer keys, add `IS NOT NULL` explicitly.

### 11.3 EXISTS and JOIN

| Question | EXISTS | JOIN |
|---|---|---|
| Does at least one matching child row exist? | Very suitable | May need DISTINCT or GROUP BY if only unique parents are wanted |
| Need columns from the child table? | Does not return child columns directly | Suitable |
| Multiple child rows per parent | Does not duplicate parent rows due to multiple children | Can produce multiple combined rows |
| Zero child rows | NOT EXISTS states this directly | LEFT JOIN plus NULL filtering can work |
| Need counts or child aggregates | Use scalar aggregate or appropriate GROUP BY | JOIN + GROUP BY is often natural |

There is no rule that EXISTS is always faster than JOIN. The optimizer can transform equivalent forms; data and plans dictate performance. First write the query that accurately reflects the desired result.

## 12. Common Query Patterns

### 12.1 Parents with at least one child

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
);
~~~

### 12.2 Parents with no children

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
);
~~~

### 12.3 Having a child satisfying multiple conditions

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status = 'READY'
      AND ch.created_at >= DATE '2026-01-01'
);
~~~

### 12.4 Having no child satisfying a condition

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status = 'FAILED'
);
~~~

This is not necessarily parents with zero children; it is parents that have no child in the FAILED status.

### 12.5 Having at least one child and no violating child

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
)
AND NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status <> 'APPROVED'
);
~~~

Example finding parents with at least one child and no child whose status differs from APPROVED. Decide separately how to handle NULL `STATUS`: `STATUS <> 'APPROVED'` is not TRUE for NULL, so if NULL also counts as a violation, add `OR STATUS IS NULL`.

### 12.6 Checking a relationship across two columns

~~~sql
SELECT a.account_id
FROM accounts a
WHERE EXISTS (
    SELECT 1
    FROM account_permissions ap
    WHERE ap.account_id = a.account_id
      AND ap.resource_id = :p_resource_id
      AND ap.permission_code = :p_permission
);
~~~

EXISTS can verify multi-column relationships and business conditions simultaneously. This is a common pattern for query-level permission checks, though it does not replace full application-layer authorization and database security policies.

## 13. Lab: Customers, Orders, and Payments

This practice section uses a dedicated lab schema with table-creation privileges and adequate quota. Do not run test DDL/DML in a production schema. Oracle DDL performs an implicit commit.

### 13.1 Create tables

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL
);

CREATE TABLE lab_orders (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER,
    order_date  DATE NOT NULL,
    status      VARCHAR2(20) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);

CREATE TABLE lab_payments (
    payment_id     NUMBER PRIMARY KEY,
    order_id       NUMBER NOT NULL,
    payment_status VARCHAR2(20) NOT NULL,
    paid_amount    NUMBER(12,2) NOT NULL
);
~~~

### 13.2 Load sample data

~~~sql
INSERT INTO lab_customers VALUES (1, 'An');
INSERT INTO lab_customers VALUES (2, 'Binh');
INSERT INTO lab_customers VALUES (3, 'Chi');
INSERT INTO lab_customers VALUES (4, 'Dung');
INSERT INTO lab_customers VALUES (5, 'Empty Customer');

INSERT INTO lab_orders VALUES
    (101, 1, DATE '2026-11-01', 'PAID', 1200000);
INSERT INTO lab_orders VALUES
    (102, 1, DATE '2026-11-05', 'PENDING', 500000);
INSERT INTO lab_orders VALUES
    (103, 2, DATE '2026-11-07', 'CANCELLED', 300000);
INSERT INTO lab_orders VALUES
    (104, 3, DATE '2026-11-10', 'PAID', 2500000);
INSERT INTO lab_orders VALUES
    (105, NULL, DATE '2026-11-11', 'PAID', 900000);

INSERT INTO lab_payments VALUES
    (1001, 101, 'CONFIRMED', 1200000);
INSERT INTO lab_payments VALUES
    (1002, 102, 'FAILED', 0);
INSERT INTO lab_payments VALUES
    (1003, 104, 'CONFIRMED', 2500000);

COMMIT;
~~~

The dataset is designed to include:

- Customer 1 has two orders.
- Customer 2 has one CANCELLED order.
- Customer 3 has one paid order.
- Customers 4 and 5 have no orders.
- One order has NULL `CUSTOMER_ID`, demonstrating NULL in the child table.
- Order 102 has a FAILED payment but no CONFIRMED payment.

### 13.3 Find customers with at least one order

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Result includes An, Binh, and Chi. Each customer appears once even though An has two orders.

### 13.4 Find customers who have never ordered

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Result includes Dung and Empty Customer. The order with NULL `CUSTOMER_ID` does not match any specific `customer_id` and does not cause all customers to be filtered out.

### 13.5 Find customers with a paid order

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Result includes An and Chi.

### 13.6 Find customers without a paid order

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Result includes Binh, Dung, and Empty Customer. Binh has a CANCELLED order but no PAID order. This is not the list of customers who have never placed an order.

### 13.7 Find orders without a CONFIRMED payment

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.status
FROM lab_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
ORDER BY o.order_id;
~~~

Result includes orders 102, 103, and 105. Order 102 has a FAILED payment without CONFIRMED; orders 103 and 105 have no payment rows yet.

### 13.8 Find orders with at least one confirmed payment

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
ORDER BY o.order_id;
~~~

Result includes orders 101 and 104. Each order appears only once even if multiple confirmed payment rows exist later.

### 13.9 Compare JOIN and EXISTS

JOIN:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

An appears twice because she has two orders. EXISTS:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

An appears only once. The two SQL queries return different result shapes: JOIN returns parent–child pairs; EXISTS returns parent rows that have the relationship.

### 13.10 Compare NOT IN and NOT EXISTS when NULL is present

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders o
)
ORDER BY c.customer_id;
~~~

The subquery contains a NULL `CUSTOMER_ID`, so NOT IN returns zero customers due to UNKNOWN logic.

Try NOT EXISTS:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Result is Dung and Empty Customer. This directly demonstrates NOT IN's NULL trap.

## 14. How to Read an EXISTS Query Before Running It

When reading EXISTS or NOT EXISTS, answer these questions:

1. **What entity is the outer row?** For example, customer, product, or order.
2. **Which relationship is being tested?** Foreign key, junction table, or business condition.
3. **Where is the correlation condition?** Usually the predicate linking the child column to the outer row's key.
4. **Are additional predicates in the right place?** Status, dates, amounts, and permissions.
5. **Can NULL appear in keys or filter data?** If so, verify the semantics.
6. **Does the result need each parent once or parent–child pairs?** If only parents, EXISTS is usually suitable.
7. **Are there uniqueness/concurrency requirements?** Use constraints to protect invariants.

Reading example:

~~~sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
      AND oi.quantity > 0
);
~~~

Accurate interpretation: "Retrieve products for which there exists no order item row with the same `PRODUCT_ID` and `QUANTITY` greater than 0." It does not claim the product never appeared in any `order_items` row, since rows with quantity equal to 0 do not match the condition.

## 15. Common Pitfalls

| Mistake or Misconception | Reality | How to Handle |
|---|---|---|
| EXISTS needs to SELECT a non-NULL column | EXISTS only checks whether a row exists | `SELECT 1` is a readable convention |
| `SELECT NULL` makes EXISTS false | A row still exists even if the selected value is NULL | Inspect the subquery's WHERE condition |
| EXISTS returns the child row count | EXISTS returns only a true/false condition | Use COUNT if you need quantities |
| EXISTS with `SELECT COUNT(*)` is false when no rows match | Aggregate without GROUP BY returns one row with COUNT=0 | Use `SELECT 1` to test row existence |
| NOT EXISTS means child column IS NULL | It checks that no row satisfies the entire predicate | Write the exact relationship condition |
| JOIN is always equivalent to EXISTS | JOIN can duplicate parent rows per child row | Choose based on result shape |
| NOT IN is always identical to NOT EXISTS | NULL in the subquery can turn NOT IN into UNKNOWN | Use NOT EXISTS or intentionally exclude NULLs |
| NOT EXISTS automatically excludes NULL parent keys | Comparing against NULL is not TRUE, so NOT EXISTS can be true | Add `IS NOT NULL` if required by business rules |
| EXISTS is always slow because it is correlated | The optimizer can unnest into a semi-join | Check execution plans and runtime |
| NOT EXISTS guarantees duplicate prevention on INSERT | Concurrent sessions can check and insert simultaneously | Use a UNIQUE constraint and handle errors |
| Using `SELECT *` in EXISTS helps fetch child columns | The SELECT list is not returned outward | Use 1 to clarify intent |
| HAVING instead of a linking predicate | HAVING filters groups, does not create correlation by itself | Put correlation in the subquery's WHERE |

## 16. Optimization and Operations Checklist

Before shipping a query to an application:

- Write correlation predicates using clear aliases, avoiding unqualified columns.
- Include only the conditions needed to define "related."
- Use EXISTS when you need parents with children; NOT EXISTS when you need parents without qualifying children.
- Check NULL behavior on outer keys, inner keys, and status columns.
- With NOT IN, verify the subquery cannot return NULL or filter NULLs explicitly.
- Do not put `COUNT(*)` inside EXISTS unless aggregation is required; an aggregate without GROUP BY always returns one row.
- Check indexes on linking columns and filter predicates against actual workloads.
- Inspect execution plans and actual runtime on representative data.
- Use UNIQUE/FOREIGN KEY constraints to protect data integrity; EXISTS never replaces constraints.
- For DML, verify affected row scope and transaction handling before committing.

## 17. Summary

EXISTS and NOT EXISTS are two conditions for testing existence relationships in Oracle SQL. EXISTS holds when the subquery finds at least one matching row; NOT EXISTS holds when no matching row exists. When a correlated subquery references the outer row, both operators directly express parent–child relationships.

Remember these principles:

- Use `SELECT 1` in EXISTS to show clearly that only existence is tested; values in the SELECT list do not decide the outcome.
- EXISTS usually corresponds to semi-join and NOT EXISTS to anti-join; the optimizer can transform queries during planning.
- EXISTS avoids parent-row multiplication caused by multiple child rows when the goal is purely testing a relationship.
- NOT EXISTS is usually safer and clearer than NOT IN when the subquery may contain NULLs.
- NULLs in outer keys still require explicit policy; NOT EXISTS does not imply the key is non-NULL.
- EXISTS in DML does not replace a UNIQUE constraint and does not protect against race conditions.
- Choose EXISTS, JOIN, IN, or COUNT according to the required output; inspect plans before drawing performance conclusions.

Once you master these rules, you can write "at least one," "none at all," "related but not yet in status," and nested relational existence queries cleanly, accurately, and maintainably.
