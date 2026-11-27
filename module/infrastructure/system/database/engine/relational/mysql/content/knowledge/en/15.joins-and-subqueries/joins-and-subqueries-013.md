# Choosing JOIN vs. Subqueries by Semantics and Execution Plan

In MySQL, both `JOIN` and subqueries can combine data from multiple tables. However, they express different intents: `JOIN` produces combined rows from two sources; `EXISTS` checks existence; `IN` checks whether a value belongs to a result set; a scalar subquery provides a single value; and a derived table creates an intermediate result set for the outer query to process further.

There is no blanket rule that `JOIN` is always faster than a subquery or `EXISTS` is always faster than `IN`. The MySQL optimizer can transform several query shapes into the same execution strategy, such as semijoin, materialization, or nested-loop/hash join. Choosing properly starts with **semantics and the expected row count**, followed by inspecting execution plans, indexes, and actual row counts.

## 1. Data Model Used in This Lesson

The examples use a system of customers, orders, and support tickets. Each customer can have multiple orders and multiple support tickets:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;

CREATE TABLE support_tickets (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    priority VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tickets_customer_priority (customer_id, priority),
    CONSTRAINT fk_tickets_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;
```

These indexes are only starting points for illustrative queries. In production systems, choose column order based on filter predicates, join keys, data distribution, and real workloads.

## 2. Semantic Difference: Combining Rows vs. Checking Existence?

Suppose you need a list of customers who have at least one paid order. There are two common ways to write this:

```sql
-- JOIN: pairs each customer with every matching order
SELECT c.id, c.name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

```sql
-- EXISTS: only checks whether at least one matching order exists
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

The two statements do not always return the same number of rows. If a customer has three paid orders, `JOIN` returns that customer three times; `EXISTS` returns the customer once because the predicate only needs to hold at least once.

| Need | Typically Suitable Construct | Semantics |
| --- | --- | --- |
| Need details of each order alongside the customer | `JOIN` | One result row per customer/order pair |
| Need a list of customers who have matching orders | `EXISTS` | Each customer row appears at most once |
| Need a list of customers without matching orders | `NOT EXISTS` | Keeps customers for whom no matching row is found |
| Need a computed value from another table | Scalar subquery or derived table | Depends on row count and computation scope |

Do not add `DISTINCT` to a `JOIN` query just to patch duplicates before verifying whether those duplicates reflect true business cardinality. When you only need an existence check, `EXISTS` states the intent much more clearly.

## 3. JOIN: When You Need Data from Both Sides

Use `JOIN` when columns from both tables must appear in the output, or when each combined pair of rows is a meaningful unit of data.

Example displaying each order along with the customer's name:

```sql
SELECT
    o.id AS order_id,
    o.created_at,
    o.total_amount,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders AS o
JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'paid'
ORDER BY o.created_at DESC, o.id DESC;
```

Each matching order produces one result row. This is required when the application needs to display individual orders rather than merely knowing whether a customer has any orders.

### 3.1. INNER JOIN and OUTER JOIN

- `INNER JOIN` keeps only row pairs where the `ON` condition matches.
- `LEFT JOIN` keeps all rows on the left; if there is no matching right row, right-side columns receive `NULL`.
- `RIGHT JOIN` keeps all rows on the right; in new query designs, you can usually swap table order and use `LEFT JOIN` for readability.

Example fetching every customer, including those who have never bought anything:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id;
```

If a customer has multiple orders, that customer still appears across multiple rows. For customers without orders, `order_id` is `NULL`.

### 3.2. ON and WHERE Conditions with LEFT JOIN

Condition placement can alter semantics:

```sql
-- Keeps all customers; pairs only paid orders
SELECT c.id, c.name, o.id AS paid_order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
 AND o.status = 'paid';
```

Compared with:

```sql
-- WHERE drops rows without a paid order, making the result behave like an INNER JOIN
SELECT c.id, c.name, o.id AS paid_order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

In the second query, customers without matching orders have `o.status = NULL`; `WHERE` does not evaluate to `TRUE`, so those rows are dropped. When you want to preserve unmatched left-side rows, put right-side filtering predicates in `ON`, or use `NOT EXISTS` depending on the goal.

## 4. EXISTS: Checking Whether at Least One Matching Row Exists

`EXISTS` returns TRUE if the subquery returns at least one row; the expressions in the subquery's `SELECT` list do not matter. Hence the common convention is `SELECT 1`.

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

This is a correlated subquery because the subquery references `c.id` from the outer query. Logically, it checks order existence per customer. However, never assume MySQL literally runs the subquery from scratch for every row: the optimizer can transform eligible `EXISTS` queries into a semijoin or another strategy.

There is no need to write `SELECT o.id` or `SELECT *` inside an `EXISTS` subquery if those values are not used. `SELECT 1` signals clearly that only existence is being tested.

## 5. IN and EXISTS for Membership Conditions

`IN (subquery)` tests whether the left-hand expression belongs to the set of values returned by the subquery:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE c.id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'paid'
);
```

With non-NULL keys and matching comparison semantics, this query usually expresses the same goal as the `EXISTS` query above. `IN` can read nicely when thinking in terms of value sets; `EXISTS` emphasizes finding a matching row.

There is no absolute performance rule between `IN` and `EXISTS`. MySQL can convert both into a semijoin or materialize the inner set depending on query structure and version. Measure using execution plans.

### 5.1. NULLs and NOT IN

`NOT IN` carries a semantic risk when the inner set contains `NULL`. Example:

```sql
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

If the subquery returns even one `NULL`, comparisons for values absent from the set can still turn into `UNKNOWN`, causing `WHERE` to drop those rows. The result can end up empty or missing rows the author expected.

To find customers without matching orders, `NOT EXISTS` is commonly used:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

If `orders.customer_id` is declared `NOT NULL`, `NOT IN` can be safer with respect to `NULL`s, yet `NOT EXISTS` still expresses the anti-match relationship clearly and relies less on assumptions about nullable data.

## 6. NOT EXISTS vs. LEFT JOIN ... IS NULL

There are two common patterns for finding rows with no related record.

**Using NOT EXISTS:**

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

**Using LEFT JOIN and checking the right-side key:**

```sql
SELECT c.id, c.name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
 AND o.status = 'paid'
WHERE o.id IS NULL;
```

Both queries can express the same goal when `o.id` is a non-NULL primary key and matching predicates are placed in `ON`. `NOT EXISTS` is often easier to read because it does not synthesize `NULL`-padded columns only to filter them out.

When using `LEFT JOIN ... IS NULL`, check a right-side column guaranteed not to be `NULL` on any real row, typically the primary key. Never check a nullable column like `o.shipped_at IS NULL`, because an existing order whose `shipped_at` is unset would be misclassified as missing.

## 7. JOIN Can Multiply Rows: Fan-Out and Duplicates

A one-to-many relationship causes a parent row to appear multiple times. When joining multiple child tables simultaneously, row counts can grow as the product of matching rows on each side.

Suppose a customer has 2 orders and 3 support tickets:

```sql
SELECT c.id, o.id AS order_id, t.id AS ticket_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
JOIN support_tickets AS t
  ON t.customer_id = c.id
WHERE c.id = 42;
```

The result can produce 2 × 3 = 6 rows for customer 42. This is not a MySQL bug; it is the semantics of combining every row pair satisfying the join predicates.

This becomes especially dangerous when summing totals:

```sql
-- Prone to double-counting and double-summing due to fan-out between orders and tickets
SELECT
    c.id,
    COUNT(o.id) AS order_count,
    SUM(o.total_amount) AS order_total,
    COUNT(t.id) AS ticket_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
LEFT JOIN support_tickets AS t
  ON t.customer_id = c.id
GROUP BY c.id;
```

If a customer has 2 orders and 3 tickets, each order repeats 3 times and each ticket repeats 2 times. `COUNT(DISTINCT ...)` can fix certain counts, but `SUM(DISTINCT total_amount)` is not a general fix because two distinct orders can share the exact same amount.

### 7.1. Pre-Aggregating Each Table Before Joining

A safe approach is aggregating each child relationship down to one row per customer before joining:

```sql
SELECT
    c.id,
    c.name,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(o.order_total, 0.00) AS order_total,
    COALESCE(t.ticket_count, 0) AS ticket_count
FROM customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS order_total
    FROM orders
    GROUP BY customer_id
) AS o
  ON o.customer_id = c.id
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS ticket_count
    FROM support_tickets
    GROUP BY customer_id
) AS t
  ON t.customer_id = c.id;
```

Each derived table emits at most one row per `customer_id`, so joining with `customers` never multiplies orders by tickets. Use `COALESCE` to display 0 when no summary row exists; replace `NULL` with 0 only when that matches reporting semantics.

## 8. Scalar Subqueries: Subqueries Returning a Single Value

A scalar subquery is a subquery used where a single value is expected:

```sql
SELECT
    c.id,
    c.name,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.id
    ) AS last_order_at
FROM customers AS c;
```

The subquery returns one aggregate value per customer. `MAX()` always emits one result row; if there are no orders, the returned value is `NULL`.

Scalar subquery rules:

- Zero rows: the result is `NULL`.
- Exactly one row and one column: that value is used.
- More than one row: MySQL raises `Subquery returns more than 1 row`.
- More than one column: invalid in a scalar position.

Do not use a scalar subquery when the subquery can return multiple rows without proper bounds or aggregation. When multiple child rows are needed, use `JOIN`, `EXISTS`, `IN`, or a derived table as appropriate.

## 9. Correlated vs. Uncorrelated Subqueries

A **correlated subquery** references columns from the outer query block:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

An **uncorrelated subquery** does not reference columns from the outer query block:

```sql
SELECT id, name
FROM customers
WHERE id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'paid'
);
```

A correlated subquery is often understood conceptually as a per-outer-row check, though the optimizer can transform it. An uncorrelated subquery may be materialized or executed using another strategy; never assume it literally runs exactly once or is always faster.

When reading execution plans, check whether MySQL transformed the subquery, whether materialization or dependent execution occurs, and how many actual rows each step processes.

## 10. Derived Tables and Pre-Aggregation Before Combining

A derived table is a `SELECT` query placed in the `FROM` clause with an alias. It separates logic into clearly structured result sets:

```sql
SELECT
    c.id,
    c.name,
    paid.total_paid
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS total_paid
    FROM orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS paid
  ON paid.customer_id = c.id;
```

Here the subquery aggregates paid orders per customer before joining with `customers`. This expresses the requirement cleanly when one summary result per group is needed.

MySQL can merge a derived table into the outer query block or materialize it as an intermediate result. Factors such as `GROUP BY`, aggregates, `DISTINCT`, `LIMIT`, and query structure affect merge eligibility. Never assume putting a subquery in `FROM` always forces a temporary table, nor assume it will always be inlined.

## 11. The Optimizer Can Transform JOINs and Subqueries

SQL describes the desired output, while the optimizer chooses how to execute it. Key transformations include:

- **Semijoin:** used for certain `IN`/`EXISTS` queries to keep outer rows that have at least one matching row without multiplying rows like a regular join.
- **Antijoin:** used for certain `NOT EXISTS`/`NOT IN` forms to keep rows without matches, provided `NULL` semantics are handled properly.
- **Materialization:** computes an inner set or derived table into an intermediate result for the outer query to consume.
- **Derived-table merging:** folds an intermediate query block into the outer query when conditions allow.
- **Join reordering:** changes the join order of tables in inner joins to reduce cost.

Transformations depend on query structure, SQL mode, nullability, MySQL version, and optimizer choices. For instance, `NOT IN` over a set that may contain `NULL` has different semantics from `NOT EXISTS`; never rewrite one to the other merely because they look similar.

The key point is that the same logical intent can execute via different strategies. Never optimize solely by swapping `IN` for `EXISTS` or converting a subquery to a join without measuring.

## 12. Physical JOIN Strategies

MySQL can employ different join algorithms depending on version, indexes, join conditions, and statistics:

### 12.1. Nested-Loop Join

A row from the outer table probes for matching rows in the inner table. When the inner table has an index on the join key, each probe can be efficient:

```sql
SELECT c.id, o.id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE c.id BETWEEN 100 AND 200;
```

With a small outer customer set and a suitable index on `orders.customer_id`, a nested loop is often a strong choice. If the inner table must be scanned repeatedly without a usable index, costs can skyrocket.

### 12.2. Hash Join

In MySQL 8.0.18 and later, the optimizer can use a hash join for eligible joins, particularly when an equi-join condition lacks a useful index. One side builds an in-memory hash table; the other side probes by key.

Hash join does not automatically mean faster than nested loop. It consumes memory and can incur disk spills or high overhead on large datasets. Eligibility depends on version, predicates, and optimizer cost choices.

### 12.3. Do Not Infer the Algorithm from Syntax

Writing `JOIN`, `IN`, or `EXISTS` does not force MySQL to pick a single algorithm. The optimizer transforms queries and selects physical plans based on estimated cost. Read `EXPLAIN` to see what the server actually chose instead of guessing from SQL syntax.

## 13. Reading EXPLAIN to Compare Two Formulations

`EXPLAIN` shows the plan MySQL intends to use:

```sql
EXPLAIN
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

Compare against the `JOIN` query:

```sql
EXPLAIN
SELECT DISTINCT c.id, c.name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.id
WHERE o.status = 'paid';
```

When reading the output, pay attention to:

- `type`/access method: `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`, and other access paths.
- `possible_keys` and `key`: candidate indexes and the index actually selected.
- `key_len`: length of the index prefix used.
- `rows` and `filtered`: estimated row count and remaining percentage.
- `Extra`: supplemental info such as `Using where`, `Using index`, `Using temporary`, `Using filesort`.
- `select_type` or query block structure: identifies subqueries, derived tables, or materialization in the corresponding `EXPLAIN` format.

No single column determines whether a query is fast or slow. For example, `type = ALL` can be completely sensible when a table is small or most rows must be read; `Using index` does not automatically prove a query is optimal if it still scans far too many rows.

## 14. EXPLAIN ANALYZE: Measuring Actual Rows and Timings

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the analyzed statement and reports actual timings, loop counts, and row counts for every iterator:

```sql
EXPLAIN ANALYZE
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

Compare against the corresponding `JOIN` plan. Inspect:

- How much actual row counts diverge from estimates.
- Which iterator accounts for most of the execution time.
- Whether any iterator runs many loops with large row counts.
- Whether materialization or sorting steps add significant cost.
- Whether indexes reduce rows examined as expected.

`EXPLAIN ANALYZE` actually runs the query. Use it only on safe read statements such as `SELECT` in an appropriate environment; never attach it to data-modifying DML without understanding behavior and version support. For heavy queries, large datasets, or load-sensitive production servers, assess impact before running.

## 15. Indexes for JOINs and Subqueries

Indexes should support the columns used for joining and filtering. For the query finding customers with paid orders:

```sql
SELECT c.id, c.name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'paid'
);
```

You can evaluate two index column orders:

```sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);

CREATE INDEX idx_orders_status_customer
ON orders (status, customer_id);
```

There is no need to create both just because they appear in examples. Choose based on how queries access the table:

- If starting from a customer and probing order status, `(customer_id, status)` can fit well.
- If filtering a highly selective status across the whole table and then retrieving customers, `(status, customer_id)` can fit well.

Selectivity, data distribution, number of distinct statuses, table size, and other queries all inform the decision. Indexes accelerate certain reads while increasing storage footprint and `INSERT`/`UPDATE`/`DELETE` overhead.

## 16. Choosing a Formulation by Scenario

| Scenario | Starting Choice | Rationale |
| --- | --- | --- |
| Need columns from both tables | `JOIN` | Output requires combined row data |
| Need every one-to-many row pair | `JOIN` | Each pair is a valid output row |
| Only need to know whether related rows exist | `EXISTS` | Prevents multiplying outer rows when multiple matches exist |
| Need to keep rows without related records | `NOT EXISTS` | Expresses anti-match with less `NULL` risk than `NOT IN` |
| Checking membership of a value in a set | `IN` | Direct syntax for set membership |
| Fetching one summary value per row | Scalar subquery or derived aggregate | Choose based on scope and result reuse |
| Aggregating multiple independent child tables | Pre-aggregate each source then `JOIN` | Prevents fan-out and double-counting/summing |
| Using an intermediate result in `FROM` | Derived table / CTE | Separates logic, then inspect merge/materialization |

These are semantic starting points, not rigid performance rules. Only after producing the right result should you compare plans and costs.

## 17. Workflow for Comparing JOINs and Subqueries

When a query can be written in multiple ways, proceed step by step:

1. **Describe the desired output:** one row per entity, one row per pair, or one summary value?
2. **Determine cardinality:** one-to-one, one-to-many, or many-to-many; could duplicates arise?
3. **Check NULLs:** are keys nullable; could `IN`/`NOT IN` encounter `NULL` in the inner set?
4. **Write the clearest semantic form:** `JOIN`, `EXISTS`, `NOT EXISTS`, `IN`, or scalar/derived subquery.
5. **Verify correctness:** test zero child rows, one child row, multiple child rows, duplicates, and `NULL`s.
6. **Inspect indexes:** are join keys and filter predicates indexed with an appropriate column order?
7. **Run EXPLAIN:** check access paths, estimated rows, materialization, temporary tables, and sorts.
8. **Run EXPLAIN ANALYZE when appropriate:** compare actual rows, loops, and timings on representative data.
9. **Measure overall cost:** elapsed time, CPU, I/O, memory, returned row count, and index write overhead.
10. **Pick the maintainable query:** when performance is comparable, favor the statement that expresses intent cleanly with minimal duplicate/`NULL` risk.

## 18. Hands-On Exercises

1. Create data where one customer has multiple paid orders; compare row counts between `JOIN` and `EXISTS`.
2. Write a query displaying each order alongside the customer's name using `JOIN`.
3. Write a query finding customers with no orders using `NOT EXISTS` and `LEFT JOIN ... IS NULL`; verify identical results.
4. Create data containing `NULL` in the inner set and compare `NOT IN` with `NOT EXISTS`.
5. Join `customers`, `orders`, and `support_tickets` and sum order totals; observe fan-out and fix it by aggregating before joining.
6. Write a scalar subquery fetching the newest order timestamp per customer; compare with a `GROUP BY` derived table.
7. Run `EXPLAIN` on `IN`, `EXISTS`, and `JOIN DISTINCT` for the same goal; record indexes and row estimates.
8. Run `EXPLAIN ANALYZE` on an eligible `SELECT`; compare actual rows, loops, and timings.
9. Experiment with changing column order in a composite index in a lab environment and re-measure the query.
10. Rewrite a multi-JOIN query into `EXISTS` or a derived table only if result semantics remain intact; check duplicates and `NULL`s.

## 19. Summary

Choose `JOIN` when you need to combine data from both sides or return every matching pair; choose `EXISTS`/`IN` when you only need to check existence or set membership; choose `NOT EXISTS` to find rows without related records; use scalar subqueries for a single value and derived tables when you need intermediate results or pre-aggregation before joining.

`JOIN` can multiply rows in one-to-many relationships and corrupt `COUNT`/`SUM` across multiple child tables. `EXISTS` avoids multiplying outer rows; `NOT IN` demands special care around `NULL`s. The optimizer can transform JOINs and subqueries into semijoins, antijoins, materialization, nested-loop joins, or hash joins depending on version and predicates. Therefore, choose by semantics first, then inspect indexes, `EXPLAIN`, actual row counts, and `EXPLAIN ANALYZE`. No single syntax is universally fastest across every dataset and workload.
