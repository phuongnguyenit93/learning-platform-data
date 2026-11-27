# Optimizing EXISTS/IN and Avoiding Redundant Repeated Subqueries

Subqueries express relational questions very naturally: which customers have orders, which products have never been sold, or how many transactions each customer has. However, if a subquery is written for the wrong purpose, a SQL statement can perform repeated lookups per outer row, count many rows when it only needs to know whether one exists, or produce wrong results when `NULL` appears in `NOT IN`.

`EXISTS` and `IN` are commonly used to check existence or membership in a set of values. MySQL can transform many forms of these subqueries into semijoins or antijoins, materialize intermediate results, or pick another strategy based on cost. Optimization is therefore not simply replacing every `IN` with `EXISTS` or vice versa. You must choose the semantically right construct, help the optimizer recognize eligible transformations, provide suitable indexes, and verify with execution plans.

This lesson belongs to the `DATABASE_MYSQL` module, which focuses on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, query tuning, and relational database operations. The goal is to write existence/non-existence checks properly, avoid unnecessary repeated subqueries, and recognize when to replace them with joins or pre-aggregation.

After this lesson, you will be able to:

- Distinguish the semantics of `EXISTS`, `IN`, `NOT EXISTS`, and `NOT IN`.
- Use `EXISTS` when you only need to know at least one matching row exists.
- Understand semijoins and antijoins along with the strategies MySQL can choose.
- Avoid three-valued logic bugs when `NOT IN` encounters `NULL`.
- Identify correlated subqueries that cause repeated work per outer row.
- Replace multiple similar scalar subqueries with a single aggregated derived table/CTE.
- Choose indexes for correlation predicates and filter conditions.
- Read `EXPLAIN`/`EXPLAIN ANALYZE` to inspect row counts, loops, and access paths.
- Know when to keep a subquery, when to use a join, and when materialization fits.

## 1. Practice Fixture

Use a simple set of customer and order tables. The examples run standalone in a lab schema.

```sql
DROP TABLE IF EXISTS tuning_order_items;
DROP TABLE IF EXISTS tuning_orders;
DROP TABLE IF EXISTS tuning_customers;

CREATE TABLE tuning_customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    region_code VARCHAR(20) NULL,
    PRIMARY KEY (customer_id),
    KEY idx_tuning_customers_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE tuning_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tuning_orders_customer_status (customer_id, order_status),
    KEY idx_tuning_orders_status_date_customer
        (order_status, order_date, customer_id)
) ENGINE = InnoDB;

CREATE TABLE tuning_order_items (
    item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_tuning_items_order (order_id)
) ENGINE = InnoDB;

INSERT INTO tuning_customers (customer_id, customer_name, region_code) VALUES
(1, 'An', 'NORTH'),
(2, 'Binh', 'SOUTH'),
(3, 'Chi', 'NORTH'),
(4, 'Dung', NULL),
(5, 'Ha', 'CENTRAL');

INSERT INTO tuning_orders
    (order_id, customer_id, order_status, order_date, total_amount)
VALUES
(101, 1, 'PAID',   '2026-11-01', 120.00),
(102, 1, 'OPEN',   '2026-11-04',  80.00),
(103, 2, 'CANCEL', '2026-11-05',  45.00),
(104, 3, 'PAID',   '2026-11-06', 210.00),
(105, 3, 'OPEN',   '2026-11-07',  90.00),
(106, 3, 'OPEN',   '2026-11-08',  35.00),
(107, 5, 'PAID',   '2026-11-09', 160.00);

INSERT INTO tuning_order_items
    (item_id, order_id, product_code, quantity)
VALUES
(1, 101, 'BOOK-A', 1),
(2, 101, 'PEN-B',  2),
(3, 102, 'BAG-C',  1),
(4, 104, 'BOOK-A', 2),
(5, 105, 'PEN-B',  4),
(6, 106, 'MUG-D',  1);
```

Verify the data:

```sql
SELECT * FROM tuning_customers ORDER BY customer_id;
SELECT * FROM tuning_orders ORDER BY order_id;
```

Customers 1 and 3 have OPEN orders; customers 2 and 5 have no OPEN orders; customer 4 has no orders at all. Subsequent examples use this dataset to compare results and plans.

## 2. EXISTS: Only Need to Know at Least One Row Exists

`EXISTS (subquery)` returns TRUE if the subquery produces at least one row, and FALSE if it produces none. Column values in the subquery's SELECT list do not matter; the optimizer only needs to know whether a matching row exists.

Example finding customers with at least one OPEN order:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

The result includes An and Chi. The inner predicate correlates with the current row of `tuning_customers` via `o.customer_id = c.customer_id`.

### 2.1. Why SELECT 1?

Inside EXISTS, the SELECT list content is never used to construct displayed output. `SELECT 1`, `SELECT *`, or `SELECT o.order_id` all express the same existence check in this case. `SELECT 1` usually communicates intent more clearly: we do not need to retrieve columns from the subquery.

There is no need to write `COUNT(*) > 0` when you only want an existence check:

```sql
-- No need to count all rows just to know whether one exists
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
) > 0
```

Write with EXISTS:

```sql
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

Semantically, EXISTS does not require counting every matching row. MySQL can stop checking after finding one row or use an equivalent semijoin strategy. `COUNT(*)` must compute the count for the entire matching set, even if the optimizer can optimize certain specific cases.

### 2.2. EXISTS Does Not Multiply Outer Rows

If a customer has three OPEN orders, the EXISTS query still returns that customer once. It tests an existence relationship rather than producing a result row per child row.

This is a key difference compared to JOIN:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'OPEN';
```

Customer Chi appears twice because she has two OPEN orders. Deduplicating with `DISTINCT` adds extra processing. If the question is simply "does the customer have an OPEN order?", EXISTS expresses the intent directly and avoids child-table fan-out.

## 3. IN: Testing Whether a Value Belongs to a Result Set

`IN (subquery)` checks whether the outer expression equals any value returned by the subquery:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

The result also consists of customers 1 and 3. The subquery can return duplicate `customer_id` values; for an IN membership check, duplicate values do not cause an outer row to appear multiple times.

### 3.1. When IN and EXISTS Are Equivalent in WHERE

When the compared columns introduce no NULL differences and comparison semantics match, the two forms usually express the exact same row set:

```sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'OPEN'
)
```

```sql
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

`IN` expresses membership in a result set; `EXISTS` expresses that a child row satisfies a correlation condition. Choose whichever reads clearest for the data relationship, then inspect EXPLAIN to see how MySQL transformed and executed it.

### 3.2. IN with a Constant List

`IN` also fits a small known set of values:

```sql
SELECT order_id, order_status
FROM tuning_orders
WHERE order_status IN ('OPEN', 'PAID');
```

This is a direct membership test, not a reason to introduce unnecessary subqueries or joins.

## 4. Semijoin: How the Optimizer Handles Queries Needing Only Outer Rows

A semijoin combines two sets but returns rows from the outer side only when at least one matching row is found on the inner side. It matches the question "is there at least one child row?".

For the EXISTS/IN queries above, the optimizer can convert the subquery into a semijoin rather than naively running a standalone subquery for every outer row. MySQL has several semijoin strategies:

| Strategy | High-level idea |
| --- | --- |
| Table pullout | Pulls the subquery table up into the outer query block when the transformation is valid |
| FirstMatch | Stops scanning the inner branch as soon as the first match for an outer row is found |
| LooseScan | Uses an index to pick one representative per value group in certain queries |
| Duplicate Weedout | Executes a join and then removes duplicate outer rows via a deduplication mechanism |
| Materialization | Builds an intermediate result set for the subquery and probes that set |

The optimizer selects a strategy based on query shape, indexes, statistics, and cost. There is no need to manually rewrite the query to mimic a specific strategy before inspecting the default plan.

### 4.1. Conditions for Transforming a Subquery into a Semijoin

Exact conditions depend on version, yet MySQL typically considers semijoin transformation for `[NOT] IN`, `= ANY`, or `EXISTS` subqueries when:

- The subquery is a single SELECT, not a UNION.
- The subquery is at the top level of `WHERE` or `ON`, or is a component of an eligible AND expression.
- The subquery does not contain aggregate functions, `GROUP BY`, `HAVING`, or `LIMIT` per the respective semijoin rules.
- Query block structure and join types permit transformation.
- There are no constructs like `STRAIGHT_JOIN` restricting join reordering.

If ineligible for semijoin, MySQL can still choose materialization or another subquery execution path. Do not assume every EXISTS automatically becomes FirstMatch.

Starting in MySQL 8.0.16, the optimizer extended semijoin transformation to eligible EXISTS predicates. Earlier versions optimized certain IN forms into semijoins while equivalent EXISTS forms were not handled the same way. Check your exact server version when comparing plans.

## 5. NOT EXISTS: Finding Rows Without Matching Relations

`NOT EXISTS` returns TRUE when the subquery produces zero rows. This is the cleanest way to find customers who have never placed an order:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

The result is Dung because customer 4 has no orders. Relationally, this is an antijoin: keep outer rows that have no match on the inner side.

Example finding customers with no OPEN orders:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

Results include Binh, Dung, and Ha. Customer 2 has a CANCEL order but no OPEN orders, so he still satisfies the condition.

## 6. NOT IN and the NULL Trap

`NOT IN` can produce surprising results when the subquery returns `NULL`. SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. If the tested value matches no non-NULL element while the inner set contains `NULL`, `IN` evaluates to UNKNOWN; negating UNKNOWN still yields UNKNOWN. WHERE keeps only rows evaluating to TRUE.

Example producing a set with NULL:

```sql
SELECT 1 AS customer_id
WHERE 2 NOT IN (1, NULL);
```

The query returns no rows. `2` does not equal `1`, yet we cannot conclude it differs from `NULL`; `2 IN (1, NULL)` evaluates to UNKNOWN, so `NOT IN` also evaluates to UNKNOWN.

### 6.1. Comparing NOT IN vs NOT EXISTS

Suppose an import table has a nullable `customer_id`:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE c.customer_id NOT IN (
    SELECT i.customer_id
    FROM imported_customer_ids AS i
);
```

If `imported_customer_ids.customer_id` contains even a single NULL, many or all outer rows can be dropped due to UNKNOWN results.

Written with NOT EXISTS:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM imported_customer_ids AS i
    WHERE i.customer_id = c.customer_id
);
```

A NULL in table `i` does not automatically wipe out all outer rows. Comparing `i.customer_id = c.customer_id` with NULL never becomes TRUE, so it never creates a match. However, if `c.customer_id` is also NULL, equality normally never yields TRUE for any row, so NOT EXISTS may retain that row. Decide explicitly whether business rules want to keep outer NULLs.

### 6.2. If Using NOT IN, Handle NULL Explicitly

If business semantics require ignoring NULLs in the inner set and non-NULL outer keys:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT i.customer_id
      FROM imported_customer_ids AS i
      WHERE i.customer_id IS NOT NULL
  );
```

If the inner column is declared `NOT NULL`, the inner-side NULL trap cannot occur, though outer NULLs and result semantics must still be considered.

### 6.3. MySQL Antijoin Transformation

Starting in MySQL 8.0.17, many eligible `NOT EXISTS`/`NOT IN` predicates can be converted into antijoins by the optimizer. However, nullable expressions can block transformation because three-valued semantics must be preserved. Some forms using `IS NOT FALSE` or `IS NOT TRUE` can give the optimizer extra transformation opportunities in supported cases, though only use them after proving semantic equivalence.

Never add `IS NOT NULL` just to coax the optimizer if doing so alters business results. NULL correctness must be settled before tuning.

## 7. LEFT JOIN ... IS NULL: Another Way to Write an Anti-Join

You can find unmatched rows using LEFT JOIN and checking whether a right-side column is NULL:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

`order_id` is the primary key and `NOT NULL` in the right table. Therefore, if `o.order_id IS NULL`, the row is NULL-extended because no match was found.

### 7.1. Put Child-Table Conditions in ON

To find customers with no OPEN orders, the status condition must be inside ON:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'OPEN'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

If you put `o.order_status = 'OPEN'` in WHERE:

```sql
-- Wrong for this anti-join goal
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'OPEN'
  AND o.order_id IS NULL;
```

The WHERE condition on the right table discards NULL-extended rows, defeating LEFT JOIN's retention of unmatched rows. The result is usually empty because a single row cannot simultaneously have status OPEN and order_id NULL.

### 7.2. Pick the Right Column for the NULL Check

Check a right-side column guaranteed to be `NOT NULL` whenever a real row exists. Using the primary key is the clearest choice:

```sql
WHERE o.order_id IS NULL
```

Do not casually test a nullable column like `o.note IS NULL`, because a genuinely matched row whose `note` happens to be NULL would be mistaken for no match.

## 8. Correlated Subqueries and Repeated Work per Outer Row

A correlated subquery references a column from the outer query block. Example:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

The predicate `o.customer_id = c.customer_id` is correlated. Logically, the subquery depends on the current outer row's value. If the optimizer neither decorrelates nor picks a semijoin, the plan may execute one lookup per outer row. When the outer table has millions of rows and the inner access path is poor, repeated lookup cost can be huge.

That does not mean correlated subqueries are always slow. With a good index, a small outer set, and EXISTS stopping on the first match, a correlated lookup can be very efficient. Inspect `loops` and actual rows instead of blindly banning correlated subqueries.

### 8.1. Signs of Unnecessary Repeated Subqueries

- The same scalar subquery appears multiple times in the SELECT list and WHERE.
- The same child table is scanned repeatedly to compute COUNT, SUM, and MAX for the same outer key.
- `EXPLAIN ANALYZE` shows an inner operator with loops nearly equal to the outer row count.
- A subquery returns a per-row aggregate when it could aggregate once by key and join.
- The query computes the same correlated expression across multiple output columns.

High loop count is not always a bug: an indexed nested-loop lookup can be the optimal plan. What matters is total actual work and whether duplicate computation can be eliminated.

## 9. Use EXISTS Instead of COUNT When Only Checking Existence

Example checking whether a customer has any orders:

```sql
-- Unnecessary counting if only true/false is needed
SELECT c.customer_id
FROM tuning_customers AS c
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
```

Rewrite:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

If the order count is needed for display, COUNT remains the right requirement. EXISTS cannot replace a count value the application actually needs.

### 9.1. Do Not Use JOIN + DISTINCT to Mimic EXISTS

If you only need a list of customers with orders:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM tuning_customers AS c
JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id;
```

Can be written cleanly according to semantics:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

JOIN creates intermediate rows per order, forcing DISTINCT to deduplicate afterward. EXISTS directly states that we only need outer rows with a match.

## 10. Combine Multiple Scalar Subqueries via Pre-Aggregation

A pattern prone to redundant work is computing multiple metrics per customer with separate correlated subqueries:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT SUM(o.total_amount)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS lifetime_value,
    (
        SELECT MAX(o.order_date)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_date
FROM tuning_customers AS c;
```

All three subqueries filter by `customer_id`. A plan may have to probe the same orders set multiple times per customer. You can aggregate once per customer and join:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    s.lifetime_value,
    s.last_order_date
FROM tuning_customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS lifetime_value,
        MAX(order_date) AS last_order_date
    FROM tuning_orders
    GROUP BY customer_id
) AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

The derived table produces one summary row per customer with orders. LEFT JOIN keeps customers without orders; `COALESCE` turns a missing COUNT into 0. `SUM` and `MAX` remain NULL for customers without orders, which may be the right representation. If business rules require 0 or a default date, decide explicitly rather than blindly replacing every NULL.

### 10.1. When Does Pre-Aggregation Help?

- Multiple aggregates are needed from the same child table on the same key.
- The outer table has many rows and each correlated subquery repeats the same filter.
- The child subset can be scanned once, grouped by key, and joined.
- Indexes or predicates narrow the rows before aggregating.

### 10.2. When Does Correlated Aggregation Still Make Sense?

If the outer query returns only 5 customers out of millions, an index on `tuning_orders(customer_id)` can make a few correlated lookups cheaper than aggregating the entire orders table. Pre-aggregation is not automatically better; it might read and group data for every customer even though the query needs only a few.

You can filter the outer set first and aggregate only the relevant customers:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count,
    s.total_amount
FROM tuning_customers AS c
JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count,
        SUM(o.total_amount) AS total_amount
    FROM tuning_orders AS o
    JOIN tuning_customers AS selected_customer
        ON selected_customer.customer_id = o.customer_id
    WHERE selected_customer.region_code = 'NORTH'
    GROUP BY o.customer_id
) AS s
    ON s.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
```

This is just an illustrative pattern; the optimizer may merge or materialize the derived table depending on query shape. Inspect actual rows to verify whether work actually decreased.

## 11. EXISTS with Compound Predicates and Indexes

Example finding customers with an OPEN order from a given date onward:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
      AND o.order_date >= '2026-11-01'
);
```

The existing index `(customer_id, order_status)` supports the two equality predicates at the leading edge, but does not contain `order_date`. If the workload frequently filters by all three columns, consider:

```sql
CREATE INDEX idx_tuning_orders_customer_status_date
ON tuning_orders (customer_id, order_status, order_date);
```

This index enables lookup by customer and status followed by a range scan on date. Still, a new index increases storage and write overhead. Add it only when the workload and EXPLAIN/ANALYZE confirm a net benefit.

### 11.1. Indexes for NOT EXISTS

With:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

The index `(customer_id, order_status)` fits well because the optimizer can quickly look up child rows via two equalities. If queries primarily filter globally by status and then date, `(order_status, order_date, customer_id)` may serve a different workload. No single index order fits every query.

### 11.2. Sargability

Keep indexed columns directly comparable. For example, avoid:

```sql
WHERE DATE(o.order_date) = '2026-11-04'
```

Since `order_date` is already DATE, write the condition directly:

```sql
WHERE o.order_date = '2026-11-04'
```

For DATETIME, use a half-open range to leverage range access:

```sql
WHERE o.created_at >= '2026-11-04 00:00:00'
  AND o.created_at <  '2026-11-05 00:00:00'
```

## 12. Subqueries with GROUP BY/Aggregates: When Semijoin Does Not Apply Directly

Semijoin transformation has limits. A subquery containing `GROUP BY`, aggregates, or HAVING may not qualify for semijoin conversion under standard rules. Example:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
) >= 2;
```

This is a scalar correlated aggregate: each customer needs a count value. When filtering by order count and/or displaying multiple aggregates, pre-aggregation is often worth testing:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count
FROM tuning_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM tuning_orders
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
) AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

The derived table contains only customers with at least two orders, so INNER JOIN fits. If you want to retain customers without orders and display count 0, use LEFT JOIN with an unfiltered aggregate and apply the required outer filter appropriately.

## 13. Repeated Subqueries in SELECT List and CTEs

If the same calculation is referenced multiple times, placing it in a derived table or CTE improves readability and avoids duplicating logic:

```sql
WITH customer_order_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM tuning_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    s.total_amount
FROM tuning_customers AS c
LEFT JOIN customer_order_summary AS s
    ON s.customer_id = c.customer_id;
```

A CTE names the summary set and lets you reuse the expression within the statement. However, never assume every CTE is always materialized exactly once or is always faster than a derived table. MySQL can merge or materialize CTEs/derived tables depending on structure and cost; CTEs referenced multiple times follow specific optimization rules. Inspect EXPLAIN.

## 14. IN Subqueries, Materialization, and Semijoin

An uncorrelated IN subquery can be materialized into an intermediate result set and probed for membership. Example:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'PAID'
);
```

Materialization works well when the inner set is built once and probed many times. For certain query shapes, semijoin can be better as the optimizer reorders joins and picks strategies like FirstMatch or Duplicate Weedout.

Do not add `DISTINCT` to an IN subquery out of habit just to remove duplicates:

```sql
WHERE c.customer_id IN (
    SELECT DISTINCT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'PAID'
)
```

For a membership test, duplicates in the IN set do not change the logical result. DISTINCT can add unnecessary sort/deduplication work or affect semijoin eligibility depending on query shape. Use it only for other semantic reasons.

## 15. EXPLAIN: Seeing What the Optimizer Actually Did

Before rewriting, capture the current query plan:

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Observe:

- Whether the subquery remains a dependent subquery or was transformed into a semijoin.
- Whether it performs a lookup via `idx_tuning_orders_customer_status`.
- Whether materialization or duplicate weedout is used.
- Estimated rows on outer and inner sides.
- Whether sorting, temporary tables, or wide scans occur.

In traditional EXPLAIN, `DEPENDENT SUBQUERY` indicates the subquery depends on an outer query block. This is a signal to check loops and row counts, not proof by itself that the query is slow. A correlated lookup on a primary/unique index can be very cheap.

### 15.1. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

`EXPLAIN ANALYZE` runs the actual SELECT and shows actual time, actual rows, and loops. Pay close attention to:

- How many loops the inner lookup executes.
- How many rows each loop reads.
- Whether an operator repeats thousands of times unnecessarily.
- Whether row estimates diverge sharply from actual rows.
- Where actual execution time is concentrated.

Use only on queries with safe scope; this is not a metadata-only command. Do not run a heavy query against production tables during peak hours just for experimentation.

### 15.2. Compare Three Equivalent Forms

Measure the same requirement using:

1. Correlated `EXISTS`.
2. `IN (subquery)`.
3. JOIN with `DISTINCT` or an equivalent derived table.

Ensure all forms have identical semantics, filters, and datasets. Compare actual rows, loops, latency, and resources. Never compare based merely on SQL line count or estimated cost.

## 16. When to Keep a Subquery vs When to Rewrite

| Scenario | Form to try first | Rationale |
| --- | --- | --- |
| Only need to know a child row exists | `EXISTS` | Expresses existence directly and avoids multiplying outer rows |
| Testing value membership in a child set | `IN (subquery)` | Expresses membership clearly; optimizer can semijoin/materialize |
| Finding unmatched outer rows | `NOT EXISTS` | Avoids the NOT IN NULL trap |
| Finding unmatched outer rows via join | `LEFT JOIN ... IS NULL` | Works when checking a NOT NULL inner column with join predicates in ON |
| Multiple aggregates on same child table by same key | Derived table/CTE pre-aggregation | Avoids repeating multiple scalar subqueries with the same filter |
| Outer set is tiny, inner has strong index | Correlated lookup can remain | Reads only a tiny slice instead of aggregating the entire inner table |
| Subquery contains aggregates/HAVING | Scalar subquery or pre-aggregation | Semijoin transformation may not apply directly |
| Subquery may contain NULLs with negation | `NOT EXISTS` or explicit NULL filter | Preserves three-valued semantics |

No single rewrite is always faster. The goal is removing duplicate work without inflating intermediate rows or forcing unnecessary full table scans.

## 17. Optimizer Limitations and Caveats

- Semijoin/antijoin transformations apply only when the query shape meets MySQL's rules.
- Subqueries with aggregates, `GROUP BY`, `HAVING`, `LIMIT`, UNION, or ineligible expression positions may not be transformed as hoped.
- Nullable expressions can restrict antijoin transformation because the optimizer must preserve NULL semantics.
- `IN` and `EXISTS` can behave differently inside SELECT/CASE expressions when UNKNOWN results are observed; do not rely solely on WHERE filtering out UNKNOWNs.
- `NOT IN` is particularly sensitive to NULLs in the inner result.
- `DISTINCT` inside a membership subquery is usually unnecessary if only used to deduplicate for IN logic.
- Correlated subqueries are not inherently slow; indexes and outer row count largely govern cost.
- Derived tables/CTEs can be merged or materialized; read the plan instead of guessing.
- `EXPLAIN ANALYZE` executes the real query and can generate load.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `COUNT(*) > 0` just to test existence | Counts rows unnecessarily | Use EXISTS |
| Using JOIN when only child existence is needed | Multiplies outer rows and requires DISTINCT | Use EXISTS/semijoin |
| Assuming IN is always slower than EXISTS | Unfounded rewrites that may worsen the plan | Compare semantics and EXPLAIN |
| Using NOT IN when inner side can contain NULL | UNKNOWN drops outer rows | Use NOT EXISTS or filter NULLs explicitly |
| Using LEFT JOIN anti-join with inner filter in WHERE | Eliminates NULL-extended rows | Move match predicates into ON |
| Checking a nullable column with IS NULL | Mistakes real rows with NULL values for non-matches | Check primary key / NOT NULL inner column |
| Repeating scalar subqueries on the same child table | Repeated scans/lookups and aggregations | Pre-aggregate once when workload fits |
| Always replacing correlated subqueries with full-table GROUP BY | Reads and groups too much data when outer set is small | Compare with indexed correlated lookup |
| Adding DISTINCT to IN out of habit | Adds unnecessary deduplication work | Omit DISTINCT unless required by semantics |
| Missing index on correlation predicate | Inner lookup must scan many rows | Index correlation key and filter columns |
| Judging purely by EXPLAIN estimated rows | Misses loops and actual runtime | Use EXPLAIN ANALYZE safely |

## 19. Practice Exercises

1. Write a query finding customers with at least one OPEN order using EXISTS and IN. Compare results.
2. Rewrite a JOIN that duplicates customers into EXISTS. Confirm Chi appears only once.
3. Write a query finding customers with no orders using NOT EXISTS.
4. Create an import table with a NULL customer_id. Compare `NOT IN` and `NOT EXISTS`, explaining the results via three-valued logic.
5. Write an anti-join using LEFT JOIN. Place the status condition in ON; then intentionally move it to WHERE and explain how the result changes.
6. Replace `COUNT(*) > 0` with EXISTS. Use EXPLAIN ANALYZE to compare loops and actual rows.
7. Write a query with three scalar subqueries computing COUNT, SUM, and MAX per customer. Rewrite it using derived-table pre-aggregation.
8. Filter the outer set to NORTH customers only. Compare correlated aggregation against full-table aggregation before joining.
9. Add index `(customer_id, order_status, order_date)`. Run EXPLAIN for EXISTS with the date predicate before and after adding the index.
10. Write an IN query with and without DISTINCT. Compare plans and explain why duplicates do not alter membership.
11. Test a subquery with GROUP BY/HAVING and observe whether the optimizer still applies semijoin transformation.
12. Run EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE on equivalent forms; note the first operator with high loops or actual rows.

## 20. Checklist for Tuning EXISTS/IN and Subqueries

- [ ] Clarified whether the requirement is existence, membership, non-existence, or an aggregate value.
- [ ] Used EXISTS when only checking whether a matching row exists.
- [ ] Avoided COUNT just to test whether count > 0.
- [ ] Checked NULLs on both outer expression and inner result before using NOT IN.
- [ ] NOT EXISTS/LEFT JOIN anti-join preserves semantics and checks a NOT NULL inner column.
- [ ] LEFT JOIN match predicates are in ON when retaining unmatched outer rows.
- [ ] Avoided adding DISTINCT to IN when duplicates do not affect membership.
- [ ] Audited repeated scalar subqueries computing the same expression.
- [ ] Evaluated pre-aggregation when multiple aggregates share the same child subset.
- [ ] Evaluated correlated lookup when outer set is small and inner index is selective.
- [ ] Appropriate index exists for correlation predicate and filters.
- [ ] Verified whether query shape qualifies for semijoin/antijoin.
- [ ] Inspected EXPLAIN and actual loops/rows safely with EXPLAIN ANALYZE.
- [ ] Compared alternatives with identical semantics and representative data.
- [ ] Avoided rewriting or hinting based solely on the rule "IN is slower than EXISTS".

## 21. Completion Criteria

You complete this lesson when you can write existence queries with EXISTS, membership with IN, anti-joins properly with NOT EXISTS or LEFT JOIN, explain the NOT IN NULL trap, spot correlated subqueries doing redundant work, consolidate multiple aggregates with pre-aggregation when appropriate, and verify semijoin/materialization via EXPLAIN/EXPLAIN ANALYZE. You should also be able to explain why a syntactically valid rewrite can still be slower if it alters cardinality, access path, or total data read.

## References

- [MySQL 8.4 Reference Manual — Semijoin and Antijoin Transformations](https://dev.mysql.com/doc/refman/8.4/en/semijoins-antijoins.html)
- [MySQL 8.4 Reference Manual — Optimizing Subqueries, Derived Tables, and View References](https://dev.mysql.com/doc/refman/8.4/en/subquery-optimization.html)
- [MySQL 8.4 Reference Manual — Optimizing IN and EXISTS Subquery Predicates](https://dev.mysql.com/doc/refman/8.4/en/subquery-optimization-with-exists.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
