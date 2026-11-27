# Choosing JOIN vs Subqueries Based on Semantics and Execution Plans in Oracle

When retrieving customers alongside their orders, we can write a JOIN. When we only need to know whether a customer has at least one paid order, we can write EXISTS. When we need total orders per customer, we can aggregate the orders table first and JOIN, or use a correlated scalar subquery. These styles look similar, yet **they do not always return the same row counts or values**.

Therefore, the question "is JOIN or a subquery faster?" has no single fixed answer. First, pick the expression that matches business semantics: do you need columns from both tables, should duplicate rows be kept, is it purely an existence check or a computed value, and where can NULL appear? Only then examine what plan the Oracle optimizer transforms the query into and measure actual execution cost.

This lesson belongs to the **Joins and Subqueries** module for Oracle Database. It compares JOIN, EXISTS, IN, NOT EXISTS, NOT IN, scalar subqueries, correlated subqueries, and inline views; and explains cardinality, NULLs, duplicate rows, subquery unnesting, join methods, and reading execution plans.

After this lesson, you can:

- Choose JOIN when combining data and columns from multiple sources.
- Choose EXISTS/NOT EXISTS when the business question checks whether related rows exist or do not exist.
- Distinguish IN from EXISTS and NOT IN from NOT EXISTS, especially when NULLs are present.
- Use scalar subqueries when a single value is needed and understand what happens if multiple rows are returned.
- Recognize correlated subqueries without assuming they always physically execute once per row in a loop.
- Understand how Oracle can unnest subqueries into semi-joins/anti-joins or transform query blocks.
- Read execution plans, compare estimated rows against actual rows, and pick implementations based on measured data.

> **Example scope:** SQL statements use Oracle Database 19c syntax. Lab tables are created in a practice schema/PDB you manage. Do not run DDL or heavy load-testing queries on a live application schema. Execution plan results depend on version, statistics, data, bind values, configuration, and privileges; this lesson does not assume one fixed plan for every system.

## 1. Start from Business Semantics

Suppose there are two tables:

- CUSTOMERS: one row per customer.
- ORDERS: multiple order rows can belong to the same customer.

One customer can have 0, 1, or many orders. This is a **one-to-many (1:N)** relationship.

~~~text
CUSTOMERS                         ORDERS
+-------------+                   +------------------+
| customer_id | 1 ------------- N | order_id         |
| name        |                   | customer_id      |
+-------------+                   | status           |
                                  | amount           |
                                  +------------------+
~~~

Different requirements arise from this relationship:

| Requirement | Expected Output | Usually Suitable Expression |
| --- | --- | --- |
| Show each customer with each order | One customer may appear in multiple rows | JOIN |
| Customers with at least one PAID order | Each customer needs to appear only once | EXISTS |
| Customers without a PAID order | Only customers with no qualifying order found | NOT EXISTS |
| Total order count per customer | One row per customer and one count value | GROUP BY then JOIN, or scalar aggregate subquery |
| Latest order date per customer | One date value per customer | MAX in subquery or aggregate view |
| Full details of the newest order | One order row chosen by deterministic rules | ROW_NUMBER()/analytic query |

Do not start by guessing which syntax is faster. First describe **what one result row represents** and whether a customer is allowed to appear multiple times.

## 2. JOIN: Combining Rows from Multiple Sources

### 2.1. JOIN returns matching row pairs

Example retrieving customer details and each order:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status,
    o.amount
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

If customer 10 has three orders, that customer appears in three rows. This is the exact behavior of a 1:N relationship: every customer/order pair satisfying the JOIN condition produces one result row.

### 2.2. JOIN can multiply row counts

Suppose:

| Customer ID | Customer |
| ---: | --- |
| 1 | An |
| 2 | Binh |

| Order ID | Customer ID | Amount |
| ---: | ---: | ---: |
| 101 | 1 | 100 |
| 102 | 1 | 200 |
| 103 | 1 | 300 |

INNER JOIN returns:

| Customer ID | Customer | Order ID | Amount |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 100 |
| 1 | An | 102 | 200 |
| 1 | An | 103 | 300 |

Customer 2 does not appear because there is no matching order. Customer 1 appears three times because of three orders.

If you only want a list of customers who have orders, a JOIN produces duplicate customer rows:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

To make each customer appear once, authors often add DISTINCT:

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

This can produce the desired business list, yet it performs a join generating multiple rows and then deduplicates. When the goal is simply "has at least one order," EXISTS states the intent more directly and avoids requiring uniqueness via DISTINCT.

### 2.3. JOIN when columns from both tables are needed

If a report requires order ID, order date, and customer name, JOIN is the natural fit:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.amount,
    c.customer_name
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

Columns from both ORDERS and CUSTOMERS are required; JOIN matches the exact data model for the output.

## 3. EXISTS: Testing Existence Instead of Pulling Child Columns

### 3.1. Basic syntax

EXISTS evaluates to TRUE if the subquery produces at least one row; if zero rows are returned, it evaluates to FALSE:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Meaning: return every customer who has at least one PAID order. Whether a customer has 1 PAID order or 100 PAID orders, they still appear once because the outer query reads from CUSTOMERS and the subquery only answers an existence check.

### 3.2. Why SELECT 1 inside EXISTS?

In EXISTS, Oracle only needs to know whether the subquery produces a row. Values in the select list are never used to form output columns:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

For existence semantics, `SELECT 1`, `SELECT o.order_id`, or `SELECT *` inside an EXISTS subquery are generally equivalent. `SELECT 1` is a readable convention emphasizing that **we are not fetching column data, only checking if a row exists**. It is not a trick guaranteed to beat `SELECT *`; the optimizer does not need to read select-list column values merely to evaluate EXISTS.

### 3.3. EXISTS does not duplicate outer rows

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Even when a customer has many matching orders, EXISTS remains a single true/false predicate for that customer row. Thus the query returns at most one row per CUSTOMERS row in the outer query block (unless the outer query itself joins another row-multiplying table).

### 3.4. EXISTS with multiple conditions

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status IN ('PAID', 'SHIPPED')
      AND o.created_at >= DATE '2026-01-01'
);
~~~

The subquery only needs to locate one order meeting all conditions simultaneously. Conditions inside the subquery define **which rows qualify as valid partners**.

## 4. IN: Checking Whether a Value Belongs to a Result Set

### 4.1. IN with a value list

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE status IN ('ACTIVE', 'TRIAL');
~~~

IN tests whether an expression equals one of the values in the list under SQL comparison rules.

### 4.2. IN with a subquery

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = 'PAID'
);
~~~

Meaning: the customer's `customer_id` belongs to the set of `customer_id` values from PAID orders. When comparison keys are non-NULL and the subquery is purely for membership testing, this usually yields the same customer set as the corresponding EXISTS query:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

### 4.3. IN and EXISTS differ in how they express intent

- IN: does the outer row's value belong to the set of values returned by the subquery?
- EXISTS: does a row exist in the subquery satisfying the relationship with the outer row?

For a simple key relationship, both generally yield identical results. Still, watch out for NULLs, complex comparison expressions, and how results fit into larger queries. Never pick IN or EXISTS solely by the slogan "one is faster."

### 4.4. IN does not duplicate outer rows

The IN subquery can return duplicate values, yet membership testing does not duplicate outer rows:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

If `customer_id` 1 appears 20 times in the subquery, customer 1 still appears only once from the outer query, assuming `CUSTOMERS.CUSTOMER_ID` is unique. This resembles EXISTS membership semantics and differs from a direct JOIN that emits one row per matched pair.

## 5. NOT EXISTS: Finding Rows Without a Partner

### 5.1. Syntax

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

This returns customers with no orders at all. If any matching order exists, NOT EXISTS is FALSE and the customer is excluded.

### 5.2. Adding business conditions

Finding customers without a PAID order:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

A customer with a PENDING order but no PAID order is still returned. This is why `status = 'PAID'` goes inside the subquery: we are negating the existence of **a PAID order**, not negating the existence of all orders.

### 5.3. NOT EXISTS vs LEFT JOIN ... IS NULL

You can write an anti-join using LEFT JOIN:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL;
~~~

`ORDER_ID` must be guaranteed NOT NULL on every real order (such as the primary key). When no PAID order matches, Oracle produces a NULL-extended row for the orders side, and `o.order_id IS NULL` retains that customer.

Both NOT EXISTS and `LEFT JOIN ... IS NULL` typically express the same anti-join semantics when conditions and checked columns are chosen properly. NOT EXISTS is usually easier to read because you do not have to pick a right-side column for a NULL check.

## 6. NOT IN and the NULL Trap

This is the most crucial semantic distinction when choosing subqueries.

### 6.1. NOT IN with a NULL-free set

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

If the subquery returns only non-NULL values, NOT IN expresses exclusion from the set. However, if the subquery contains NULL, the logical outcome changes.

### 6.2. Why can a single NULL make NOT IN return zero rows?

Suppose the subquery returns the set:

~~~text
(1, 2, NULL)
~~~

For `customer_id = 3`, the expression:

~~~sql
3 NOT IN (1, 2, NULL)
~~~

is logically the negation of:

~~~sql
3 = 1 OR 3 = 2 OR 3 = NULL
~~~

The first two comparisons are FALSE; `3 = NULL` is UNKNOWN. `FALSE OR FALSE OR UNKNOWN` evaluates to UNKNOWN. WHERE keeps only TRUE, so `customer_id` 3 is not returned.

Therefore:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

can return **zero rows** if the subquery returns even one NULL, even when customers without orders exist.

### 6.3. NOT EXISTS is usually safer with NULLs

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Here a NULL in `o.customer_id` does not satisfy equality with any non-NULL `customer_id`; it does not negate all outer rows. For "no row exists whose key equals the customer's key," NOT EXISTS is usually clearer and safer.

### 6.4. When is NOT IN safe to use?

If the subquery column is guaranteed NOT NULL by constraint or filtered explicitly for NULLs:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

then the inner-set NULL trap is eliminated. Still, keep outer NULLs in mind: `NULL NOT IN (...)` does not evaluate to TRUE; if business rules need to keep customers with NULL IDs (normally impossible on primary keys), handle that separately.

## 7. Scalar Subqueries: Returning a Single Value

### 7.1. Scalar subquery in SELECT

A scalar subquery is a subquery used where a single value is expected:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers c
ORDER BY c.customer_id;
~~~

The subquery correlates to the outer customer and returns one count per customer. Because `COUNT(*)` has no GROUP BY, it always returns exactly one row, even with zero orders (value 0).

### 7.2. Scalar subquery returning 0, 1, or multiple rows

Rules:

| Rows Returned by Subquery | Scalar Behavior |
| ---: | --- |
| 0 | Scalar value is NULL |
| 1 | Value from that row |
| More than 1 | Error `ORA-01427: single-row subquery returns more than one row` |

Example that can fail:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT o.status
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS one_order_status
FROM customers c;
~~~

If a customer has multiple orders, the subquery returns multiple rows and scalar context cannot pick one status. Do not blindly patch this with `FETCH FIRST 1 ROW ONLY`; first clarify which order the business wants (newest, oldest, priority status, etc.) and specify an explicit ORDER BY.

### 7.3. Scalar subquery with aggregates

Aggregates without GROUP BY normally return exactly one row:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers c;
~~~

With zero orders, MAX returns NULL. This is concise when you need just one summary value per outer row.

### 7.4. A scalar subquery can substitute for JOIN, but consider row counts

Another option is aggregating orders first and then LEFT JOINing:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.latest_order_at
FROM customers c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        MAX(created_at) AS latest_order_at
    FROM orders
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id;
~~~

Compared with scalar COUNT:

- A scalar subquery states "compute one value per customer."
- An inline view builds a one-row-per-`customer_id` summary set and combines it via LEFT JOIN.
- Both can return identical results under matching keys and predicates.
- Oracle may transform and evaluate both differently depending on query, statistics, and version.

There is no rule that scalar subqueries are always slow or JOINs are always fast.

## 8. Correlated vs Uncorrelated Subqueries

### 8.1. Correlated subquery

A correlated subquery references a column from an outer query block:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

`o.customer_id = c.customer_id` references the outer alias `c`, making the subquery correlated.

### 8.2. Uncorrelated subquery

A subquery that does not reference outer rows:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
~~~

The subquery relies solely on `orders` and the PAID condition. Logically, it generates the set of `customer_id`s from PAID orders and the outer query checks membership.

### 8.3. Correlated does not guarantee row-by-row sequential execution

The logical description is that the subquery is evaluated in the context of each outer row. However, the Oracle optimizer can **unnest** the subquery, transforming it into a semi-join, anti-join, or another plan shape. Therefore, do not see the word "correlated" and assume the database must run outer rows × subquery in a naive loop.

Conversely, do not assume every subquery gets unnested either. Query structure, aggregates, DISTINCT, ROWNUM/FETCH, analytic functions, set operators, hints, version, and other conditions can restrict transformations. Inspect the actual execution plan.

## 9. Semi-Join and Anti-Join: How the Optimizer Can Execute EXISTS/IN

### 9.1. Semi-join

When a query keeps left-side rows only if a matching right-side row exists:

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

Oracle can choose a **semi-join**. Semantically, a semi-join only needs to confirm at least one partner exists on the right; it does not emit all row pairs like an ordinary inner join. This aligns directly with EXISTS/IN semantics.

### 9.2. Anti-join

With NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Oracle can use an **anti-join** to keep left-side rows that find no matching partner on the right.

### 9.3. Join methods that can appear in the plan

Even when SQL is written with EXISTS, the plan can still contain join operations:

| Common Operation | Concept |
| --- | --- |
| NESTED LOOPS SEMI | For each outer row, probe for a matching partner; can stop once one is found |
| HASH JOIN SEMI | Uses a hash structure to test membership between two sets |
| MERGE JOIN SEMI | Merges two sets sorted on matching keys |
| HASH JOIN ANTI | Keeps outer rows lacking a partner via hash anti-join |
| NESTED LOOPS ANTI | Probes and rejects outer rows if a partner exists |

Exact operation names depend on Oracle version and plan. The key point: **EXISTS syntax does not force Oracle to run a physical subquery loop**. The optimizer can pick other execution methods that preserve results.

## 10. JOIN, EXISTS, IN, and Scalar Subqueries: Choosing by Required Output

### 10.1. Decision table

| If you need... | Consider first | Reason |
| --- | --- | --- |
| Columns from both tables and all matching pairs | JOIN | Output consists of row pairs |
| Outer rows if at least one matching row exists | EXISTS | Does not multiply outer rows by partner count |
| Outer rows if no matching row exists | NOT EXISTS | Expresses anti-join, avoids NOT IN's NULL trap |
| Check whether a value belongs to a set | IN (subquery) | Value-based membership |
| A single value per outer row | Scalar subquery | Suits aggregates or guaranteed single-row relationships |
| One summary row per key then combine data | Inline view/CTE + JOIN | Separates aggregation step from presentation step |
| Top/latest row by ordering rules | Analytic ROW_NUMBER() or ordered subquery | Picks one row deterministically |

### 10.2. One requirement, multiple formulations

Requirement: customers with at least one PAID order.

**Approach A — EXISTS:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = :status
);
~~~

**Approach B — JOIN DISTINCT:**

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = :status;
~~~

**Approach C — IN:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = :status
);
~~~

In a model where `customer_id` is a NOT NULL primary key and the subquery returns related `customer_id`s under the same filter, all three return the same set of customers. Yet:

- Approach A expresses existence checking directly.
- Approach B forms customer/order pairs first, then needs DISTINCT to strip duplicates.
- Approach C expresses membership in the `customer_id` set.

Oracle can transform C and A into similar semi-join plans. B may optimize differently; DISTINCT may require a hash/sort unique or be eliminated by the optimizer if proven unnecessary. Inspect the plan instead of guessing from SQL line count.

### 10.3. When are JOIN and EXISTS NOT equivalent?

If you omit DISTINCT:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

customers with multiple PAID orders appear multiple times, whereas EXISTS returns each customer row at most once. This is a **cardinality** difference, not a performance difference.

If the query subsequently applies `COUNT(*)`, `SUM(...)`, `FETCH FIRST`, or pagination logic, duplicate rows can cause severe correctness bugs.

## 11. Comprehensive Example: Order Count and Latest Order per Customer

### 11.1. Aggregate first, then JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.latest_order_at
FROM customers c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        MAX(created_at) AS latest_order_at
    FROM orders
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Inline view `s` produces at most one row per `customer_id` that has orders. LEFT JOIN keeps customers without orders; NVL displays count 0. This is a clean pattern when multiple summary metrics are needed from the same child table.

### 11.2. Scalar subquery per metric

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT MAX(o.created_at)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers c
ORDER BY c.customer_id;
~~~

Two scalar subqueries can return the exact same data. However, they repeat the relationship condition and form two separate subquery expressions in SQL. The optimizer may apply transformations/caching, though you should not assume it always merges them into a single scan. When multiple aggregates over the same child set are needed, an inline view/CTE usually makes intent clearer.

### 11.3. Retrieving the full latest order row

`MAX(created_at)` returns only the maximum timestamp; it does not automatically return `ORDER_ID` and other columns from that specific row. If two orders tie for the maximum timestamp, joining back on MAX can return multiple rows.

Use an analytic function:

~~~sql
SELECT customer_id, order_id, created_at, amount
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        o.amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

`ORDER_ID` is assumed unique and acts as a tie-breaker if orders share `created_at`. If business logic wants **all orders tied at the newest timestamp**, use `RANK()` on `created_at` and filter `rank = 1` without adding `order_id` to the rank criteria.

## 12. The Oracle Optimizer: Written SQL vs Executed Plan

SQL is a declarative language: you describe **what result is needed**, and the Oracle optimizer chooses an execution plan based on available metadata. Two syntactically different queries can transform into similar plans; two nearly identical queries can also get different plans when predicates or data differ.

### 12.1. Conceptual stages

~~~text
SQL statement
     |
     v
PARSE / SEMANTIC CHECK
     |
     v
QUERY TRANSFORMATION
  - subquery unnesting
  - view merging
  - predicate pushing
  - other transformations
     |
     v
COST-BASED OPTIMIZATION
  - join order
  - join method
  - access path
     |
     v
EXECUTION PLAN
     |
     v
ROWS / BUFFERS / CPU / ELAPSED TIME
~~~

This is a high-level diagram. Oracle has multiple optimization phases and conditional transformations; not every SQL statement passes through the exact same sequence or triggers every transformation.

### 12.2. Subquery unnesting

A correlated subquery such as:

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

can be unnested by the optimizer into a semi-join. This lets the optimizer consider join order, join methods, and access paths across the involved tables as part of a broader query block.

Not every subquery can be unnested. Certain constructs or semantics can block or restrict transformations—for example aggregates, ROWNUM, row limiting, analytics, set operators, or other factors depending on case and version. Never rewrite SQL solely to force unnesting without understanding the plan and output.

### 12.3. Join methods

Oracle commonly picks one of the following depending on data and access paths:

| Join Method | High-Level Operation | Often Advantageous When |
| --- | --- | --- |
| Nested loops | Read an outer row/small batch and probe matching inner rows | Small outer set, indexed/selective inner access |
| Hash join | Build a hash structure on one set and probe with the other | Large sets, equality conditions, sufficient memory |
| Sort merge join | Sort both sets by join key and merge | Pre-sorted data or favorable sort/merge cost |

No join method is always fastest. Nested loops can be great with a handful of customers and an `ORDERS(CUSTOMER_ID)` index, yet very expensive if the outer set has millions of rows causing repeated probes. Hash join excels on large sets, yet consumes memory and can spill to TEMP if memory is tight. Sort merge likewise depends on sort cost and data traits.

### 12.4. Semi/anti-join is semantics; join method is execution

Do not confuse them:

- **Semi-join/anti-join** describes the result relationship: has partner / has no partner.
- **Nested loops/hash/merge** describes the physical join algorithm.

For instance, `HASH JOIN SEMI` is semantically a semi-join using hash join as the physical method. `NESTED LOOPS SEMI` is also a semi-join, using nested loops.

## 13. Reading Execution Plans to Decide

### 13.1. EXPLAIN PLAN: estimated plan

You can inspect the estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` writes the generated plan to the plan table (usually `PLAN_TABLE`), and `DBMS_XPLAN.DISPLAY` formats it. It helps you understand what the optimizer intends to do, but is not proof of actual row counts or timings for a specific execution.

### 13.2. Gathering execution statistics

To view runtime statistics for an execution in your session:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

The `GATHER_PLAN_STATISTICS` hint requests runtime execution stats for the statement. `DISPLAY_CURSOR` reads the cursor from the shared SQL area; viewing cursors/plans may require appropriate privileges. If the statement was aged out or ran in another session, passing `NULL` for SQL ID/child number may not point to the statement you intended to inspect; specify the exact SQL ID/child number when needed.

### 13.3. Important columns in the output

| Column | Meaning | How to Read |
| --- | --- | --- |
| E-Rows | Optimizer estimated rows | Compare with actual rows to spot cardinality misestimates |
| A-Rows | Actual rows at the operation, when gathered | Shows how many rows the operation truly emitted |
| Starts | Number of times the operation started | High values can indicate repeated inner execution in nested loops |
| Buffers | Logical I/O / buffer gets | Useful for comparing buffer access volume |
| A-Time | Recorded execution time at operation | Affected by measurement and parent/child rollup; do not naively sum all lines |
| Predicate Information | Access/filter predicates | Shows where predicates were applied |
| Operation | Plan operator type | E.g. TABLE ACCESS, INDEX RANGE SCAN, HASH JOIN SEMI |

`E-Rows` and `A-Rows` are vital when reviewing plans. If the optimizer estimates 10 rows while actual rows are 500,000, join order or method may be suboptimal due to stale statistics or skewed selectivity estimates.

### 13.4. High Starts alone does not prove a query is bad

In nested loops, inner operations are started multiple times, so high `Starts` is expected. Check whether it causes excessive buffer gets or elapsed time, and how many rows come out each time. In a semi-join, the engine can stop after finding one matching partner; inspect the plan to see the actual behavior.

### 13.5. Cost is not runtime duration

`COST` is an internal optimizer estimate used to compare candidate plans, not milliseconds or seconds. A lower-cost plan does not automatically mean lower response time in all conditions. Measure with representative data, matching bind values, and consistent environments while watching runtime metrics.

## 14. Fair Comparison Between Two Formulations

To determine whether EXISTS or JOIN is better for a specific query, follow this process:

1. Write both SQL statements so **semantics and result sets are identical**.
2. Use identical predicates, bind values, projections, and sort requirements.
3. Verify duplicate rows and NULLs to ensure you are not comparing two queries with different meanings.
4. Test with data distributions resembling production, not just a few-row table.
5. Collect actual execution plans and runtime statistics.
6. Compare `A-Rows`, `Starts`, `Buffers`, elapsed time, and TEMP/PGA usage if applicable.
7. Repeat enough times to smooth out parse, cache, and system-load variance; never draw general conclusions from one run.

### 14.1. Example of two queries with identical semantics

**EXISTS:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = :status
);
~~~

**IN:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = :status
);
~~~

With `CUSTOMERS.CUSTOMER_ID` as a NOT NULL primary key and the subquery returning related `customer_id`s under the same filter, both share identical membership semantics. Check whether Oracle produces similar semi-joins; do not guess that one is guaranteed faster.

### 14.2. Do not compare an undeduplicated JOIN against EXISTS

The two queries below **do not necessarily return the same row count**:

~~~sql
-- Each customer/order pair:
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';

-- Each customer with at least one PAID order:
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

When multiple PAID orders exist, the JOIN repeats the customer while EXISTS does not. Never declare one faster when they solve two different business requirements.

### 14.3. Do not add DISTINCT thoughtlessly

DISTINCT can require a hash/sort unique operation, consuming memory or TEMP. Yet if the output genuinely needs deduplication, that is required business work. Never drop DISTINCT merely for a prettier plan if the output becomes wrong; instead, pick EXISTS when the true requirement is simply membership.

## 15. Indexes, Statistics, and Cardinality

### 15.1. Indexes can help both JOINs and subqueries

Example:

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

An index on `ORDERS(CUSTOMER_ID, STATUS)` or `ORDERS(STATUS, CUSTOMER_ID)` may help depending on selectivity, join order, access paths, and workload. There is no single index column order best for every query. If the status filter is highly selective, optimal index order can differ from probing `customer_id` per customer.

### 15.2. Having an index does not always mean faster

- If a large fraction of the table matches the predicate, a full table scan and hash join can be far cheaper than countless index lookups.
- If the outer table is tiny and the inner index fits well, nested loops can excel.
- If many non-indexed columns are needed, table lookups by ROWID can increase I/O.
- Indexes add write overhead and consume storage.
- Clustering factor and data distribution strongly affect access efficiency.

### 15.3. Optimizer statistics

The optimizer relies on table/index statistics, histograms, column correlations, and metadata to estimate row counts. If data shifts significantly or statistics go stale, `E-Rows` can diverge widely from `A-Rows`.

Do not run `DBMS_STATS` on a production schema without authorization and a DBA plan. Gathering statistics can change plans across many SQL statements; follow administrative procedures.

### 15.4. Bind variables and data skew

A query with bind `:status` might run with `PAID` (many rows) or `RARE_STATUS` (very few rows). A single plan is not always optimal for every bind value. Oracle has mechanisms like bind peeking and adaptive cursor sharing depending on conditions and version, yet never assume every bind is automatically optimized perfectly.

When benchmarking, test representative values across different selectivities and inspect child cursors/plans. Do not blindly replace binds with literals everywhere to force per-value plans without evaluating cursor-sharing impact.

## 16. Query Patterns to Consider

### 16.1. Only need to know if at least one row exists

Prefer EXISTS:

~~~sql
SELECT p.product_id, p.product_name
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
~~~

### 16.2. Need columns from the child table

Use JOIN:

~~~sql
SELECT p.product_id, p.product_name, i.order_id, i.quantity
FROM products p
JOIN order_items i
    ON i.product_id = p.product_id;
~~~

### 16.3. Need to know no matching row exists

Prefer NOT EXISTS:

~~~sql
SELECT p.product_id, p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
~~~

### 16.4. Need an aggregated value per outer row

Scalar aggregate:

~~~sql
SELECT p.product_id,
       (SELECT SUM(i.quantity)
        FROM order_items i
        WHERE i.product_id = p.product_id) AS units_ordered
FROM products p;
~~~

Or aggregate inline view + LEFT JOIN if multiple metrics are needed:

~~~sql
SELECT p.product_id,
       NVL(s.units_ordered, 0) AS units_ordered,
       NVL(s.order_line_count, 0) AS order_line_count
FROM products p
LEFT JOIN (
    SELECT product_id,
           SUM(quantity) AS units_ordered,
           COUNT(*) AS order_line_count
    FROM order_items
    GROUP BY product_id
) s
    ON s.product_id = p.product_id;
~~~

### 16.5. Need to check a multi-column condition

EXISTS can contain multi-table joins and multiple conditions:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    JOIN order_items i
        ON i.order_id = o.order_id
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND i.product_id = :product_id
);
~~~

This returns customers with at least one PAID order containing the specified product. `order_items` may have many matching rows, yet EXISTS still checks only existence per customer.

### 16.6. Need one ordered child row

Use analytic ranking:

~~~sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT o.customer_id,
           o.order_id,
           o.created_at,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC, o.order_id DESC
           ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

Do not use a scalar subquery returning `order_id` without a single-row guarantee or aggregate. If a customer has multiple orders, the scalar subquery will fail.

## 17. Comprehensive Practice Lab

This lab creates customer and order tables intentionally covering: a customer with multiple PAID orders, a customer with only a PENDING order, a customer with zero orders, and an order row with NULL `CUSTOMER_ID` to demonstrate NOT IN.

Run only in a lab schema you own. If the table names already exist, pick other names; never drop existing tables of unknown origin.

### Step 1 — Create tables

~~~sql
CREATE TABLE join_subquery_customer_lab (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL
);

CREATE TABLE join_subquery_order_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    status VARCHAR2(12 CHAR) NOT NULL,
    amount NUMBER(10,2) NOT NULL,
    created_at DATE NOT NULL,
    CONSTRAINT fk_js_order_customer_lab
        FOREIGN KEY (customer_id)
        REFERENCES join_subquery_customer_lab(customer_id)
);
~~~

`CUSTOMER_ID` in the orders table allows NULL to illustrate missing link data. The foreign key remains valid because NULL is not a key value requiring a parent match.

### Step 2 — Insert customers

~~~sql
INSERT INTO join_subquery_customer_lab VALUES (1, 'An');
INSERT INTO join_subquery_customer_lab VALUES (2, 'Binh');
INSERT INTO join_subquery_customer_lab VALUES (3, 'Chi');
INSERT INTO join_subquery_customer_lab VALUES (4, 'Dung');

COMMIT;
~~~

### Step 3 — Insert orders

~~~sql
INSERT INTO join_subquery_order_lab
VALUES (101, 1, 'PAID', 100, DATE '2026-11-01');

INSERT INTO join_subquery_order_lab
VALUES (102, 1, 'PAID', 200, DATE '2026-11-03');

INSERT INTO join_subquery_order_lab
VALUES (103, 2, 'PENDING', 80, DATE '2026-11-04');

INSERT INTO join_subquery_order_lab
VALUES (104, 3, 'PAID', 150, DATE '2026-11-05');

INSERT INTO join_subquery_order_lab
VALUES (105, NULL, 'PAID', 50, DATE '2026-11-06');

COMMIT;
~~~

Data model:

| Customer | Orders |
| --- | --- |
| An (1) | 101 PAID, 102 PAID |
| Binh (2) | 103 PENDING |
| Chi (3) | 104 PAID |
| Dung (4) | None |
| *(no customer)* | 105 PAID with NULL CUSTOMER_ID |

### Step 4 — JOIN: retrieving each customer/order pair

~~~sql
SELECT c.customer_id, c.customer_name,
       o.order_id, o.status, o.amount
FROM join_subquery_customer_lab c
JOIN join_subquery_order_lab o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Result has four rows: An appears twice, Binh once, Chi once; Dung does not appear.

### Step 5 — EXISTS: customers with at least one PAID order

~~~sql
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Result is An and Chi, one row each. An has two PAID orders yet is not duplicated.

### Step 6 — JOIN DISTINCT and comparison

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
JOIN join_subquery_order_lab o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id;
~~~

Result must match the same two customers from Step 5. Remove DISTINCT to observe An appearing twice; explain why the two queries no longer share the same cardinality.

### Step 7 — IN and NOT IN with NULL

~~~sql
-- IN: customers whose ID is in the set of IDs from PAID orders.
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM join_subquery_order_lab o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;

-- NOT IN: observe the effect of NULL in the subquery.
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM join_subquery_order_lab o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

The IN query returns An and Chi. The PAID subquery also includes a NULL value from order 105; thus NOT IN returns zero rows due to UNKNOWN logic.

### Step 8 — NOT EXISTS: customers without a PAID order

~~~sql
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Result includes Binh and Dung: Binh has an order, but no PAID order; Dung has no orders at all. The order row with NULL `customer_id` does not break NOT EXISTS.

### Step 9 — Scalar subqueries counting orders

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM join_subquery_order_lab o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT MAX(o.created_at)
        FROM join_subquery_order_lab o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM join_subquery_customer_lab c
ORDER BY c.customer_id;
~~~

Result has four rows. Dung's count is 0; Dung's MAX is NULL.

### Step 10 — Aggregate inline view + LEFT JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.total_amount
FROM join_subquery_customer_lab c
LEFT JOIN (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM join_subquery_order_lab
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Result retains Dung as well. The order row with NULL `customer_id` lands in the inline view's NULL group without matching any customer.

### Step 11 — Inspecting execution plans

Run the EXISTS query with statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Then run the corresponding IN query and inspect its cursor plan. On tiny lab tables of a few rows, the optimizer may choose a full scan or a simple plan; never conclude which style is faster from a tiny table.

### Step 12 — Clean up lab tables if not needed

~~~sql
-- Drop the child table first because of the foreign key referencing the parent table.
DROP TABLE join_subquery_order_lab PURGE;
DROP TABLE join_subquery_customer_lab PURGE;
~~~

`PURGE` bypasses the recycle bin. Run only when sure both tables are lab tables you created and the data is no longer needed.

## 18. Self-Check Questions

1. When does a JOIN produce multiple rows for the same customer?
2. Why does EXISTS not duplicate outer rows based on the number of matching orders?
3. What logical question does `IN (subquery)` answer?
4. With a non-NULL foreign key and matching predicates, why do IN and EXISTS usually yield the same result set?
5. Why can NOT IN return empty if the subquery contains a single NULL?
6. Why is NOT EXISTS usually safer for anti-joins?
7. How many rows does a scalar subquery without GROUP BY using `COUNT(*)` return when no related records exist?
8. What error occurs when a scalar subquery returns more than one row?
9. Why does `MAX(created_at)` not identify the entire newest order row by itself?
10. Is a correlated subquery guaranteed to execute physically once per outer row?
11. How does a semi-join differ from an inner join in output goal?
12. Which conditions does the optimizer typically convert into an anti-join?
13. Why can't you conclude EXISTS is always faster than JOIN?
14. What do `E-Rows` and `A-Rows` represent in `DBMS_XPLAN`?
15. Is `COST` in an execution plan measured in milliseconds?
16. Why must you compare two SQL queries with identical semantics before benchmarking?
17. When is an aggregate inline view + LEFT JOIN easier to manage than multiple scalar subqueries?
18. Why isn't an index always better than a full table scan?
19. What should you check when `Starts` for a plan operation is very high?
20. Why shouldn't you benchmark on a few-row lab table and extrapolate conclusions to production?

**Answer hints:**

1. When one customer row matches multiple order rows.
2. EXISTS evaluates only whether a partner exists for each outer row; it does not project pairs.
3. Whether the outer row's value belongs to the subquery's result set.
4. Because both test membership; duplicates in the inner set do not multiply outer rows.
5. Comparing against NULL produces UNKNOWN; WHERE retains only TRUE.
6. NOT EXISTS checks that no row satisfies the relation without being poisoned by inner NULLs the way NOT IN can be.
7. One row, with `COUNT(*) = 0`.
8. `ORA-01427`.
9. MAX returns only the timestamp value; multiple rows can tie at MAX and it lacks the remaining columns of a single row.
10. No; the optimizer can unnest/transform it into a semi-join or another shape.
11. A semi-join only needs to confirm a partner exists, rather than emitting every matching right-side pair.
12. Corresponding NOT EXISTS/NOT IN forms expressing absence of a partner.
13. Optimizer, data, statistics, indexes, and semantics govern plan and runtime; there is no fixed speed rule.
14. `E-Rows` is estimated rows; `A-Rows` is actual rows when runtime stats are collected.
15. No, cost is an internal optimizer estimate used to compare candidate plans.
16. If results differ, the benchmark is not comparing the same workload.
17. When multiple aggregates from the same child table and one summary row per key are needed.
18. A full scan can be cheaper when predicates are unselective or most of the table must be read.
19. Number of starts, buffers, rows per start, join method, and operation elapsed time.
20. Tiny data does not represent production cardinality, selectivity, concurrency, or I/O.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): JOIN syntax and join semantics.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): EXISTS and NOT EXISTS conditions.
- [Oracle Database SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): membership checks and subqueries.
- [Oracle Database SQL Language Reference — Scalar Subquery Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Scalar-Subquery-Expressions.html): rules for single-value, zero-row, and multi-row subqueries.
- [Oracle Database SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): join order, join methods, and join optimization.
- [Oracle Database SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): subquery unnesting and query transformations.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): displaying execution plans and runtime statistics.
