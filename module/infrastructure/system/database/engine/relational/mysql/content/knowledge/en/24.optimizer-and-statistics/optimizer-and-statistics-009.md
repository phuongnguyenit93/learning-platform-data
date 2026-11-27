# Semijoins, Antijoins, and Existence Query Transformations

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, reading execution plans, query optimization, privileges, backups, and operating relational databases. When a query only needs to know whether a matching row exists in another table, `EXISTS`, `IN`, `NOT EXISTS`, and `NOT IN` express that intent more clearly than performing a `JOIN` and deduplicating. The MySQL optimizer can transform existence queries into a **semijoin** or **antijoin** to pick an efficient execution strategy.

A semijoin retains outer rows when at least one matching inner row exists; an antijoin retains outer rows when no matching inner row exists. This is an execution-plan transformation, not a requirement to rewrite SQL using special `JOIN` syntax. To use it properly, understand `NULL` semantics, when the optimizer is permitted to transform, semijoin execution strategies, and how to verify via `EXPLAIN`.

Key version milestones: MySQL 8.0.16 expanded semijoin transformations for `EXISTS`; MySQL 8.0.17 added antijoin transformations for many negated predicates; `EXPLAIN FORMAT=TREE` arrived in MySQL 8.0.16 and `EXPLAIN ANALYZE` arrived in MySQL 8.0.18. Check your server version with `SELECT VERSION()` before running corresponding examples.

## 1. Existence Queries with EXISTS and IN

Suppose there are two tables:

- `customers`: each row is a customer.
- `orders`: each row is an order belonging to a customer.

Requirement: retrieve customers who have ever placed an order.

This can be written with `EXISTS`:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Or written with `IN`:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Both queries express the condition that the customer has at least one matching order. The optimizer can recognize this as a semijoin and choose a join-like plan instead of naively running the subquery for each outer row.

### 1.1. EXISTS Checks Existence

`EXISTS (subquery)` returns `TRUE` if the subquery produces at least one row; if no row is returned, it returns `FALSE`. The values in the subquery's `SELECT` list do not affect the outcome:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

`SELECT 1`, `SELECT *`, or `SELECT o.order_id` all have the same meaning for existence checking. `SELECT 1` is commonly used because it signals clearly that only row existence matters.

`EXISTS` does not need to read every matching row to decide the logical outcome. Once one matching row is found, additional matching rows cannot change `TRUE` to another result.

### 1.2. IN Checks Membership

`expression IN (subquery)` checks whether the value on the left equals any value in the result set according to SQL comparison rules.

~~~sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
)
~~~

If the subquery returns multiple rows with the same `customer_id`, the `IN` condition still evaluates to a single `TRUE`/`FALSE`/`UNKNOWN` for the outer row. It does not multiply customer rows by the number of orders.

### 1.3. Correlated and Uncorrelated EXISTS

A correlated subquery references columns from the outer query block:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

An uncorrelated subquery does not depend on outer rows:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
~~~

Correlation describes logical SQL dependency, not a mandate that the optimizer must execute the subquery once per outer row. Semijoin transformation can decorrelate or reorganize execution to avoid expensive repeated evaluation.

## 2. What Is a Semijoin?

A semijoin returns rows from the outer side if at least one matching row is found on the inner side. It does not return inner columns and does not duplicate outer rows per inner match.

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Each customer appears at most once from `customers`, regardless of whether they have one or hundreds of orders. If `customers` itself contains duplicate `customer_id` rows due to a missing unique constraint, those outer rows remain distinct input rows; a semijoin merely prevents multiplying them due to multiple inner matches.

### 2.1. How Semijoin Differs from INNER JOIN

Written with `JOIN`:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

If a customer has three orders, `JOIN` returns three rows for that customer. To remove duplicates, you must add `DISTINCT`:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

A semijoin directly expresses "at least one match" without generating duplicated intermediate rows only to deduplicate them afterward. The optimizer can pick an equivalently efficient execution plan.

| Characteristic | EXISTS / Semijoin | INNER JOIN |
|---|---|---|
| Purpose | Check whether a match exists | Combine matching rows |
| Columns from inner table | Not returned | Can be returned |
| Multiple matching inner rows | Does not duplicate outer rows | Can duplicate outer rows |
| Needs DISTINCT to keep unique outer rows | Typically no | May be required depending on data |

### 2.2. When Should You Use a Semijoin?

Use `EXISTS` or `IN` when the business question is:

- Which customers have placed an order?
- Which products have appeared in order items?
- Which employees have at least one open task?
- Which accounts have a transaction record matching criteria?

If you need data from the inner table—such as the latest order date, total order count, or per-order details—a `JOIN`, aggregation, or window function may be more appropriate.

## 3. What Is an Antijoin?

An antijoin returns outer rows when no matching row exists on the inner side.

Requirement: retrieve customers who have never placed an order:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Semantically, this is an antijoin. The optimizer can transform the query into an anti-join plan to find outer rows with no match.

### 3.1. How Antijoin Differs from LEFT JOIN ... IS NULL

The same requirement can be written as:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

This is the outer-join anti-join pattern: customer rows with no orders have `NULL` for `orders` columns. Check an inner column guaranteed `NOT NULL`, typically the primary key, to distinguish unmatched rows from matched rows with nullable values.

`NOT EXISTS` usually expresses intent more directly and avoids relying on picking a `NOT NULL` check column in an outer join.

### 3.2. Antijoin Returns Unmatched Outer Rows

An antijoin does not mean "the inner table is empty." Each outer row is evaluated against its correlation predicate. Some customers may have orders while others do not; the antijoin retains the unmatched subset.

### 3.3. Match Conditions Must Reflect Exact Business Logic

For example, retrieving customers without any paid orders:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Customers with `PENDING` orders but no `PAID` orders are still returned. Do not drop the `status` condition or move it outside the query block if doing so alters the meaning.

## 4. NULL and Crucial Differences Between NOT IN and NOT EXISTS

In SQL, comparisons can evaluate to `TRUE`, `FALSE`, or `UNKNOWN`. `WHERE` retains a row only when the condition is `TRUE`. `UNKNOWN` is not treated as `TRUE`.

This is a common source of bugs when using `NOT IN`.

### 4.1. NOT IN Encountering NULL in a Subquery

Suppose the subquery returns the set `(1, 2, NULL)`:

~~~sql
SELECT 3 NOT IN (1, 2, NULL);
~~~

The result is `UNKNOWN`, not `TRUE`. Because `3` does not equal `1` or `2`, yet under SQL three-valued logic we cannot conclude it differs from `NULL`.

Therefore:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

If `orders.customer_id` contains even a single `NULL`, the `NOT IN` condition for unmatched customers becomes `UNKNOWN`, eliminating them from the result. The query may return fewer rows than expected—or zero rows at all.

### 4.2. NOT EXISTS Is Not Disrupted by NULLs in the Subquery Result

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

`EXISTS` only tests whether any row satisfies the condition. A row in `orders` with a `NULL` `customer_id` does not match a normal `customer_id` via `=`, and it does not turn every `NOT EXISTS` check into `UNKNOWN`.

### 4.3. Outer-Side NULLs Must Also Be Considered

`NOT IN` with a `NULL` left-hand expression evaluates to `UNKNOWN` when the subquery set is non-empty; if the subquery set is empty, `NOT IN` can evaluate to `TRUE` under empty-set rules. Meanwhile, `NOT EXISTS` can return `TRUE` for an outer row with a `NULL` key because no inner row satisfies the equality predicate.

Thus, replacing `NOT IN` with `NOT EXISTS` may be the right fix for "no matching row," but verify how business logic expects outer `NULL` keys to be handled.

### 4.4. Writing NOT IN Safely When NULLs Have No Meaning

If `customer_id` must be present and `NULL`s in the subquery should also be excluded:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT o.customer_id
      FROM orders AS o
      WHERE o.customer_id IS NOT NULL
  );
~~~

Excluding `NULL`s must stem from business rules. Do not add `IS NOT NULL` mechanically if `NULL`s carry meaning that should be preserved.

### 4.5. Condensed Truth Table

| Test | Result |
|---|---|
| 3 IN (1, 2) | FALSE |
| 3 IN (1, 2, NULL) | UNKNOWN |
| 3 NOT IN (1, 2) | TRUE |
| 3 NOT IN (1, 2, NULL) | UNKNOWN |
| EXISTS (SELECT 1 WHERE 1 = 0) | FALSE |
| NOT EXISTS (SELECT 1 WHERE 1 = 0) | TRUE |

When designing an antijoin, explicitly decide whether comparison keys can be `NULL` and what outcome is desired in that case.

## 5. How MySQL Transforms Existence Queries into Semijoins

The optimizer can convert eligible `IN`, `= ANY`, or `EXISTS` predicates into semijoins. Instead of executing a correlated subquery independently for every outer row, the optimizer can merge query blocks into a join plan and choose an appropriate strategy.

Example:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

The optimizer can organize this query as a semijoin between `customers` and the set of `PAID` orders. Depending on data, indexes, and estimated cost, MySQL may start from customers and look up matching orders, or start from orders and join back to customers.

### 5.1. EXISTS and IN Can Be Optimized Similarly

In MySQL 8.0.16 and later, eligible `EXISTS` queries undergo the same family of semijoin transformations as `IN`. Prior to that milestone, `EXISTS` optimization capabilities differed across versions.

Do not pick syntax merely assuming `EXISTS` is always faster than `IN` or vice versa. Choose readable syntax with the right semantics and verify the execution plan on your MySQL version.

### 5.2. Semijoin Is an Optimizer Transformation

The SQL author keeps the `EXISTS`/`IN` structure. Semijoin is an equivalent execution strategy chosen by the optimizer. The same SQL statement can receive different plans when:

- Row counts and data distributions change.
- Index statistics are updated.
- Indexes are added or dropped.
- Filter predicates change.
- MySQL version or optimizer settings change.

Do not treat any single plan as permanently guaranteed by SQL syntax.

## 6. Conditions for Applying Semijoin Transformation

Not every subquery can be transformed into a semijoin. MySQL must preserve SQL semantics and abide by query-block constraints.

Common eligibility requirements include:

- The existence predicate uses `IN`, `= ANY`, or `EXISTS` in `WHERE` or `ON`.
- The predicate appears at the top level of the condition or as an `AND` conjunct; predicates nested inside `OR` are generally ineligible.
- The subquery is a single `SELECT` query block; `UNION`/`UNION ALL` does not qualify for this basic semijoin transformation.
- The subquery lacks blocking constructs such as aggregate functions, `HAVING`, or `LIMIT`.
- Query blocks and total joined tables stay within optimizer limits.
- Certain constructs or modifiers like `STRAIGHT_JOIN` and window functions can prevent transformation.

`DISTINCT`, `GROUP BY` without aggregates, and `ORDER BY` in certain subqueries may be ignored or handled because they do not alter existence semantics. Do not remove them manually if they serve another purpose in the actual query; check version-specific rules.

### 6.1. Predicate Under OR

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.is_vip = 1
   OR EXISTS (
       SELECT 1
       FROM orders AS o
       WHERE o.customer_id = c.customer_id
   );
~~~

`EXISTS` sits beneath `OR`. This is not a typical top-level `AND` term eligible for semijoin transformation. Do not expect the optimizer to transform it the same way as a standalone `EXISTS` predicate.

### 6.2. LIMIT Inside a Subquery

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 1
);
~~~

`LIMIT` is usually redundant inside `EXISTS` because `EXISTS` already checks only for at least one row. Worse, `LIMIT` can block semijoin transformation under eligibility rules. In this example, omit `LIMIT` if nothing else requires it:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

### 6.3. Aggregates and HAVING

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    GROUP BY o.customer_id
    HAVING COUNT(*) >= 3
);
~~~

This query checks an aggregate condition: customers with at least three orders. Aggregates and `HAVING` disqualify it from a simple existence semijoin. You may keep the subquery or refactor into an aggregated derived table/CTE and `JOIN`.

Never remove `GROUP BY`/`HAVING` when the business goal is at least three orders; plain `EXISTS` checks only for at least one row.

## 7. Semijoin Execution Strategies

Once semijoin transformation applies, MySQL can pick among multiple execution strategies. The best choice depends on row counts, selectivity, indexes, and estimated costs.

### 7.1. Table Pullout

The optimizer can pull a table out of a subquery into the outer query block when conditions allow. After pullout, that table participates in the main join plan, opening up more join-order and access-path options.

Table pullout is a query-block structural transformation; it does not mean outer rows get duplicated in the final output like a regular `INNER JOIN`. Semijoin semantics are still preserved.

### 7.2. FirstMatch

`FirstMatch` halts the inner search once the first matching row is found for the corresponding outer row combination. Since the question is simply "does a match exist?", finding additional matches adds no value.

For example, a customer with many `PAID` orders: after finding the first `PAID` order, the optimizer stops scanning remaining `PAID` orders just to decide whether the customer qualifies.

`FirstMatch` is effective when probing the inner table via an index and finding matches quickly. If matches are rare or indexes are unsuitable, search costs behave differently.

### 7.3. LooseScan

`LooseScan` scans an index grouped by key values to pick a qualifying representative, avoiding repeated processing of multiple inner rows sharing the same join key. This strategy depends on index structure and column order.

For example, many orders share the same `customer_id`. If an index allows scanning by `customer_id` groups, the optimizer can exploit key ordering to determine customers with orders without scanning all duplicates normally.

Not every index supports `LooseScan`. Inspect the plan to see whether the optimizer selects it.

### 7.4. Duplicate Weedout

`Duplicate Weedout` executes a join plan while eliminating duplicate outer-row combinations to preserve semijoin semantics. MySQL may use a temporary table to track which outer rows have already been emitted.

This strategy is flexible, though storing and checking duplicates adds overhead. When combination counts are large, temporary tables and disk I/O can impact performance.

### 7.5. Materialization

The optimizer can execute the subquery first, materialize needed results into an internal temporary table, deduplicate, and index it for lookups. Afterward, the outer query probes the materialized set to detect matches.

Materialization works well when the inner set is computed once and probed many times. It also incurs the cost of building and storing intermediate results. For large datasets, the temporary table may spill to disk.

### 7.6. Strategy Comparison

| Strategy | Core Idea | Watchouts |
|---|---|---|
| Table pullout | Pull inner table into the main join plan | Expands join-order choices |
| FirstMatch | Stop after the first match | Effective when matches are found quickly |
| LooseScan | Scan one representative per index group | Depends on index and column order |
| Duplicate Weedout | Deduplicate outer rows after joining | May require a temporary table |
| Materialization | Build an intermediate inner lookup set | Incurs temp-table creation and storage cost |

The optimizer selects a strategy based on cost estimates; do not assume one strategy is universally fastest.

## 8. Antijoin Transformation in MySQL

Antijoin is a transformation for negated predicates such as `NOT EXISTS` or `NOT IN`. MySQL 8.0.17 and later support antijoin transformations for many eligible negated queries.

Example:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can execute this as an anti-join: finding customers with no match in `orders`. Depending on the execution strategy, the plan can short-circuit or discard an outer row immediately upon detecting a match.

### 8.1. How NULL Conditions Affect Antijoins

Antijoin transformation cannot apply to every nullable expression because SQL's `UNKNOWN` semantics must be preserved faithfully. In particular, `NOT IN` with nullable comparison values has different semantics from "no row equals this value."

MySQL supports certain negated predicate patterns that allow antijoins in specific nullable cases—for instance, expressions explicitly written to treat `UNKNOWN` as `FALSE` via `IS NOT TRUE`. Even so, do not rely on such transformations as a substitute for understanding truth tables.

### 8.2. Using NOT EXISTS When You Need "No Matching Row"

~~~sql
SELECT p.product_id
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
);
~~~

If `product_id` on the outer side can be `NULL`, the `NOT EXISTS` query can still return that row because no equality comparison evaluates to `TRUE`. If you want to exclude `NULL`s, add `p.product_id IS NOT NULL` per business requirements.

### 8.3. Antijoin and LEFT JOIN ... IS NULL

The optimizer can recognize certain `LEFT JOIN ... IS NULL` patterns and execute an efficient anti-join. However, verify that the column tested with `IS NULL` is guaranteed `NOT NULL` whenever a match exists. Testing a nullable inner column can mistake a matched row containing `NULL` for an unmatched row.

Prefer `NOT EXISTS` when the goal is testing non-existence; use `LEFT JOIN` when you need additional columns or when the query structure is clearer with a verified check column.

## 9. Choosing Indexes for Semijoin and Antijoin Queries

Good indexes help the optimizer check matches quickly and reduce rows read.

### 9.1. Index on the Correlated Column

With:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

One index to evaluate:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

This index supports finding orders by `customer_id` and `status`. Depending on strategy, an index starting with `status` then `customer_id` may also make sense if the optimizer drives from `PAID` orders. Choose column order based on selectivity, workload, and plans—not a single query alone.

### 9.2. Outer-Side Indexes

If `customers` has a primary key on `customer_id`, accessing individual customers already has an efficient path. If outer conditions filter on `region_id` or status, a suitable index on the outer table reduces rows to inspect.

### 9.3. Indexes for Antijoins

With `NOT EXISTS`, an index on the inner table's correlated column is often critical:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

An index `orders(customer_id)` quickly checks whether any order matches each customer. Without an index, the engine may have to scan many rows in `orders`.

### 9.4. Avoid Creating Duplicate Indexes

Before adding an index:

~~~sql
SHOW INDEX FROM orders;
~~~

Inspect the execution plan:

~~~sql
EXPLAIN
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Examine `key`, `type`, `rows`, `filtered`, and the access predicates used. Indexes speed up reads but increase `INSERT`/`UPDATE`/`DELETE` overhead and storage usage.

## 10. Reading Execution Plans

You cannot conclude a semijoin was applied merely by looking at the SQL text. Use `EXPLAIN` to inspect the optimizer's plan.

### 10.1. Default Tabular EXPLAIN

~~~sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

In tabular output, examine columns such as `select_type`, `table`, `type`, `possible_keys`, `key`, `rows`, `filtered`, and `Extra`. The subquery may appear as `SIMPLE`/`PRIMARY` or materialized/semijoin-related depending on strategy and version.

### 10.2. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

`TREE` helps visualize iterator order and join types. Depending on the plan, you may see semijoin, nested loop, materialize, or equivalent nodes. Exact node names and display formatting vary by MySQL version.

### 10.3. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

`JSON` exposes query block structure, access paths, estimated rows, and materialization/semijoin details when emitted by the optimizer. Use `JSON` when inspecting deep details or feeding plans into analysis tools.

### 10.4. EXPLAIN ANALYZE

MySQL 8.0.18+ supports `EXPLAIN ANALYZE` for compatible `SELECT` queries. It executes the query and reports actual row counts, loops, and timings:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Compare estimated rows against actual rows to detect stale statistics or skewed cardinality estimates. `EXPLAIN ANALYZE` runs the real query and consumes resources; run it in lab/staging or during load-assessed windows.

### 10.5. Signals to Look For

- Semijoin or antijoin nodes when explicitly displayed by the plan.
- `FirstMatch`, `LooseScan`, `Duplicate Weedout`, or materialization in relevant output.
- Chosen index on correlated columns.
- Inner rows read to locate matches.
- Nested-loop iteration counts.
- Temporary tables or duplicate-elimination steps.
- Discrepancies between estimated rows and actual rows.

Not every version prints identical labels. Read the entire plan structure and compare it against query semantics.

## 11. Optimizer Switches and Hints

MySQL exposes `optimizer_switch` to toggle optimization groups. Inspect it with:

~~~sql
SELECT @@SESSION.optimizer_switch;
~~~

Semijoin-related flags can include:

- `semijoin`: enables/disables semijoin transformation.
- `firstmatch`: enables the `FirstMatch` strategy.
- `loosescan`: enables `LooseScan`.
- `duplicateweedout`: enables `Duplicate Weedout`.
- `materialization`: enables materialization in optimizer-supported contexts.

### 11.1. Testing Semijoin Off in a Lab Session

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'semijoin=off';

EXPLAIN FORMAT=TREE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Compare plans with semijoin enabled and disabled. Change only session scope in the lab; never set `GLOBAL` just to test a query. When restoring, restore the exact saved value so you do not accidentally overwrite other optimizer settings.

### 11.2. Optimizer Hints

MySQL supports hints such as `SEMIJOIN()` and `NO_SEMIJOIN()` to guide semijoin strategy choice for an eligible query block. You can use `QB_NAME()` to name a query block and reference it from an outer hint.

Example illustrating hint syntax on supported versions:

~~~sql
SELECT /*+ SEMIJOIN(@orders_subq FIRSTMATCH) */
       c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT /*+ QB_NAME(orders_subq) */
           o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
~~~

Hints are guidance for the optimizer and take effect only when the query block qualifies. If the query shape cannot undergo semijoin transformation or the strategy is inapplicable, the hint may be ignored. Check warnings and execution plans; never assume a hint took effect just because the SQL succeeded.

### 11.3. Do Not Force One Strategy for All Data

`FirstMatch` can excel when matches are easy to find; materialization can excel when the inner set is small and reused efficiently; `LooseScan` can excel with a matching index. Changing data can shift which strategy is optimal. Use hints to test hypotheses or handle measured cases, not out of habit.

## 12. Query Rewrite Patterns

### 12.1. JOIN Causing Duplicates: Rewrite to EXISTS

Original query:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

If you only want customers with at least one `PAID` order:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

`EXISTS` directly states the goal without generating repeated rows from multiple orders only to strip them with `DISTINCT`. Both queries can produce equivalent result sets provided selected columns come solely from `customers` and `NULL`/duplicate semantics are preserved.

### 12.2. NOT IN with NULLs: Rewrite to NOT EXISTS

Risky query:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

If `orders.customer_id` contains `NULL`, results may be unexpected. Use `NOT EXISTS` to express "no matching row":

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

If outer `customer_id` is nullable and `NULL`s must be excluded, add `c.customer_id IS NOT NULL`. Decide semantics before rewriting.

### 12.3. Counting Is Not an Existence Problem

If the requirement is customers with at least three orders, a plain `EXISTS` is insufficient:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) >= 3;
~~~

This can be written with a derived aggregate:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN (
    SELECT customer_id
    FROM orders
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
) AS active_customers
  ON active_customers.customer_id = c.customer_id;
~~~

Never convert a counting query into `EXISTS` just because `EXISTS` can stop at the first match; doing so changes the condition from at least three rows to at least one row.

### 12.4. EXISTS with Additional Conditions

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    JOIN orders AS o
      ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
);
~~~

Semijoin still returns only products having at least one order item belonging to a `PAID` order in the time range. Inner tables can join with each other; the correlation condition with the outer table defines the match.

## 13. Common Mistakes and Troubleshooting

| Symptom | Possible Cause | Remedy |
|---|---|---|
| `NOT IN` unexpectedly returns 0 rows | Subquery contains `NULL` | Check for `NULL`; use `NOT EXISTS` if intent is no match |
| `JOIN` returns customers multiple times | One customer has multiple orders | Use `EXISTS` if only checking existence |
| `EXISTS` runs slowly | Missing index on correlated column or many inner rows inspected | Read `EXPLAIN`; evaluate indexes and access paths |
| Semijoin missing from plan | Subquery ineligible for transformation or optimizer picked another path | Check predicate placement, `LIMIT`, aggregates, `HAVING`, `OR`, and version |
| Antijoin not applied | Nullable expression or ineligible query shape | Clarify `NULL` semantics and inspect plan |
| Hint has no effect | Wrong query block, invalid strategy, or forbidden transformation | Check `SHOW WARNINGS` and `EXPLAIN` |
| Materialization builds a huge temp table | Large or low-selectivity inner set | Check cardinality, filter predicates, and indexes |
| Replacing `NOT IN` with `NOT EXISTS` changes rows with `NULL` keys | Different `NULL` semantics between the two forms | Explicitly define outer and inner `NULL` handling |
| Using `EXISTS` for "at least N rows" | `EXISTS` only tests for at least one row | Use `COUNT`/`HAVING` aggregation or equivalent logic |
| Relying on an old plan after data growth | Cardinality and costs shifted | Refresh stats as appropriate and re-measure with `EXPLAIN ANALYZE` |

## 14. Hands-On Practice: Observing Semijoins and Antijoins

Run this in a MySQL 8.0 lab database. This exercise creates dedicated tables to test duplicates, `NULL`s, and execution plans. Do not run on production tables.

### 14.1. Create Sample Tables

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer_status (customer_id, status)
) ENGINE=InnoDB;

INSERT INTO lab_customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Em');

INSERT INTO lab_orders (order_id, customer_id, status)
VALUES
    (101, 1, 'PAID'),
    (102, 1, 'PENDING'),
    (103, 2, 'PAID'),
    (104, 2, 'PAID'),
    (105, 4, 'CANCELLED'),
    (106, NULL, 'PAID');
~~~

Customers 1 and 2 have `PAID` orders; customers 3 and 5 have no orders; customer 4 has only a `CANCELLED` order. The `orders` table includes one `NULL` `customer_id` to test `NOT IN`.

### 14.2. Step 1 — Find Customers with PAID Orders Using EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

The result contains customers 1 and 2, each appearing once even though customer 2 has two `PAID` orders.

### 14.3. Step 2 — Compare with JOIN

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Observe customer 2 appearing twice. Add `DISTINCT` to compare the result set with `EXISTS`:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Explain why `EXISTS` does not need `DISTINCT` to remove duplicates arising from `orders`.

### 14.4. Step 3 — Find Customers Without Orders Using NOT EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

The result includes customers 3 and 5. Customer 4 is excluded because they have a `CANCELLED` order; this query checks all order statuses.

### 14.5. Step 4 — Observe NOT IN with NULL

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders AS o
)
ORDER BY c.customer_id;
~~~

Because the subquery contains `NULL`, `NOT IN` for unmatched `customer_id`s evaluates to `UNKNOWN`; the query may omit customers 3 and 5. Now exclude `NULL` in the subquery:

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders AS o
    WHERE o.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
~~~

The result can now match `NOT EXISTS` because outer `customer_id` is `NOT NULL` in `lab_customers`. Explain the role of each `NULL` filter.

### 14.6. Step 5 — Inspect Semijoin Plan

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Observe semijoin, nested loop, materialization, or equivalent plan output. Tiny lab tables may lead the optimizer to pick a scan; that alone does not mean indexes are useless on large data.

### 14.7. Step 6 — Inspect Antijoin Plan

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Observe the anti-join or equivalent plan. Compare with the `NOT IN` query containing `NULL` and explain why the optimizer must preserve three-valued logic semantics.

### 14.8. Step 7 — Test Disabling Semijoin in the Session

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'semijoin=off';

EXPLAIN FORMAT=TREE
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Compare the plan with Step 5. Restore the session setting immediately after testing.

### 14.9. Step 8 — Measure with EXPLAIN ANALYZE

If the server is MySQL 8.0.18 or later:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Read actual rows, loops, and timings. Because the lab dataset is tiny, the goal is understanding the plan—not drawing production conclusions from absolute timings.

### 14.10. Step 9 — Clean Up Lab Tables

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Only drop the two lab tables you just created.

**Expected outcomes:** write `EXISTS`/`IN` accurately for semijoins and `NOT EXISTS`/`NOT IN` for antijoins; explain `NULL` behavior; distinguish semijoins from `JOIN`s with duplicates; read basic plans and compare with semijoin disabled.

## 15. Principles to Remember

- `EXISTS` returns `TRUE` when the subquery yields at least one row; expressions in the subquery `SELECT` list do not decide the outcome.
- `IN` checks set membership; `NULL` can turn comparisons into `UNKNOWN`.
- A semijoin retains outer rows with at least one match and does not multiply outer rows across multiple inner matches.
- An antijoin retains outer rows with no match.
- `NOT IN` is highly sensitive to `NULL`s in the subquery; `NOT EXISTS` is usually safer when the intent is "no matching row."
- Outer-side `NULL`s can also cause `NOT IN` and `NOT EXISTS` to differ; define semantics clearly before rewriting.
- MySQL 8.0.16+ can transform eligible `EXISTS` queries into semijoins; MySQL 8.0.17+ added antijoin transformations for many negated forms.
- Semijoin strategies include `FirstMatch`, `LooseScan`, `Duplicate Weedout`, and `Materialization`; table pullout is a related transformation.
- Query shape, predicate placement, aggregates, `HAVING`, `LIMIT`, `OR`, and other constructs can prevent semijoin transformation.
- Indexes on correlated columns speed up match checks; choose index column order based on data and execution plans.
- Use `EXPLAIN TREE`/`JSON` to inspect plans; `EXPLAIN ANALYZE` executes the real query and reports actual metrics on MySQL 8.0.18+.
- Optimizer switches and hints assist testing or deliberate control; they do not replace verifying semantics and measuring plans.
- Never replace `EXISTS` with `JOIN` without handling duplicates; never replace counting queries with `EXISTS` if the requirement demands at least N rows.

Semijoins and antijoins allow MySQL to execute existence queries in ways suited to the data and indexes. SQL authors must get semantics right first—especially around `NULL`s and duplicates—then read execution plans to see which strategy the optimizer chose and whether indexes support match checks effectively.
