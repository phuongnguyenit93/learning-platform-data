# CTE Merge/Materialization and Inspecting Execution Plans

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privileges, backups, and operations. A Common Table Expression (CTE) lets you name a subquery so SQL statements are easier to read, split into steps, and reuse within the same statement. However, a CTE is not automatically stored in a temporary table. MySQL can **merge** a CTE into the query that uses it or **materialize** the result into an intermediate table.

Both strategies carry different costs and optimization opportunities. Merging can help the optimizer push predicates down to base tables, combine JOINs, and pick indexes directly. Materialization creates an intermediate result that can be read repeatedly, which is especially useful when the CTE is referenced multiple times or contains aggregations. To optimize properly, read the execution plan instead of guessing from the WITH syntax.

## 1. CTEs in MySQL

A CTE is a named result set declared using the WITH clause and scoped to a single SQL statement:

~~~sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT order_id, customer_id, total_amount
FROM paid_orders;
~~~

paid_orders is the CTE name. The query inside the parentheses defines the data; the outer query references that name as a row source. CTEs help break complex queries into meaningfully named steps.

MySQL supports both non-recursive and recursive CTEs starting in MySQL 8.0. Non-recursive CTEs are generally handled by the optimizer using strategies similar to derived tables and views. Recursive CTEs follow their own execution rules and are always materialized.

### 1.1. A CTE Is Not a Long-Lived Stored Table

A CTE exists only within the scope of a statement:

~~~sql
WITH order_summary AS (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
)
SELECT *
FROM order_summary;
~~~

After the statement finishes, the name order_summary can no longer be used in the next SQL statement. A CTE does not automatically create a physical table, does not replace user-managed temporary tables, and does not persist results across multiple statements.

### 1.2. CTEs and Derived Tables

Both styles can express the same data source:

~~~sql
-- Using a CTE
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT customer_id, SUM(total_amount) AS paid_total
FROM paid_orders
GROUP BY customer_id;

-- Using a derived table
SELECT customer_id, SUM(total_amount) AS paid_total
FROM (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
) AS paid_orders
GROUP BY customer_id;
~~~

A CTE names the query step at the beginning of the statement; a derived table places the subquery directly inside FROM. Both can be merged or materialized by the optimizer depending on structure and execution plan.

## 2. Two Strategies: Merge and Materialization

### 2.1. What Is Merge?

When merging, MySQL folds the CTE's query block into the referencing query block. You can think of the CTE as being expanded into the outer query so the optimizer optimizes the tables and predicates as one combined plan.

Example:

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

The CTE merely projects columns from the table and has no GROUP BY, DISTINCT, LIMIT, or constructs preventing merge. MySQL can merge the CTE, push customer_id = 100 and status = 'PAID' down to the orders table access, and pick an appropriate index.

When a merge succeeds, the plan may show only the orders table; there is not necessarily an intermediate table creation step named order_source.

### 2.2. What Is Materialization?

When materializing, MySQL executes the CTE query to create an intermediate result in an internal temporary table. The outer query reads that result as a row source.

Example:

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 1000;
~~~

The CTE contains GROUP BY and aggregates. These features prevent merging under MySQL's merge rules, so the CTE is materialized. The intermediate result holds at most one row per customer_id; the outer query JOINs with the aggregated set.

Materialization has costs to build the result and read the intermediate table. The internal temporary table may stay in memory or spill to disk storage depending on size, data types, and configuration limits. Do not assume every materialized CTE lives completely in RAM.

### 2.3. A CTE Does Not Decide the Strategy on Its Own

Seeing WITH name AS (...) alone is not enough to conclude MySQL will build a temporary table. For non-recursive CTEs, the optimizer can:

- Merge the CTE into the referencing query.
- Materialize the CTE into an intermediate result.
- Choose another execution strategy matching supported transformations.

The outcome depends on CTE structure, reference count, outer query predicates, statistics, version, and estimated cost. Use EXPLAIN to inspect the actual plan.

## 3. When Can a CTE Be Merged?

A simple CTE without constructs that require preserving an intermediate result can generally be merged.

Example:

~~~sql
WITH recent_orders AS (
    SELECT order_id, customer_id, status, created_at
    FROM orders
)
SELECT order_id, created_at
FROM recent_orders
WHERE customer_id = 20
  AND status = 'PAID';
~~~

The CTE only projects columns; filter conditions can be combined with the outer query's conditions. If an appropriate index exists, the optimizer can directly access a small slice of orders.

### 3.1. Benefits of Merging

Merging can:

- Push outer query filter predicates down to base tables.
- Allow the optimizer to combine JOIN and WHERE conditions within one query block.
- Expand choices for JOIN order and access paths.
- Avoid creating and reading an unnecessary temporary table.
- Avoid storing intermediate columns or rows that the outer query does not need.

For instance, if a CTE spans 10 million orders while the outer query needs only one customer, merging can filter directly by customer_id instead of building the full intermediate set first. This is an optimization opportunity, not a guarantee that every merged CTE is faster in every scenario.

### 3.2. Predicate Pushdown and Merge

When merged, outer conditions can be applied directly on the source table:

~~~sql
WITH source_orders AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
    WHERE created_at >= '2026-01-01'
)
SELECT order_id, total_amount
FROM source_orders
WHERE customer_id = 100;
~~~

The optimizer can combine both conditions into the access predicates on orders:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND customer_id = 100;
~~~

This is a logical interpretation for understanding merging. The optimizer does not necessarily rewrite SQL into that exact text; read the plan to see which predicates and indexes are actually used.

## 4. Constructs That Commonly Prevent Merging

According to MySQL rules, certain constructs in a query block prevent a derived table, view, or CTE from being merged and require it to be materialized. Important cases include:

- Aggregate functions such as SUM(), COUNT(), AVG(), MIN(), MAX().
- Window functions.
- DISTINCT.
- GROUP BY.
- HAVING.
- LIMIT.
- UNION or UNION ALL.
- Subqueries in the SELECT list of the query block.
- Assignments to user variables.
- Query blocks referencing only literals without reading any table.

Example of a CTE with GROUP BY:

~~~sql
WITH department_stats AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT *
FROM department_stats
WHERE employee_count >= 5;
~~~

The CTE must produce aggregated results by department_id. It cannot simply be replaced by a query reading individual employees rows while keeping the same semantics, so merging is blocked and the result is materialized.

### 4.1. LIMIT Prevents Merging

~~~sql
WITH latest_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    ORDER BY created_at DESC
    LIMIT 100
)
SELECT *
FROM latest_orders
WHERE customer_id = 10;
~~~

The outer customer_id filter applies to the selected 100 latest orders. Pushing the filter before LIMIT would alter which 100 rows are chosen, so the optimizer cannot arbitrarily merge this query block.

If business logic actually wants the 100 latest orders specifically for customer 10, put the filter inside the CTE:

~~~sql
WITH latest_customer_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    WHERE customer_id = 10
    ORDER BY created_at DESC
    LIMIT 100
)
SELECT *
FROM latest_customer_orders;
~~~

These two queries are not equivalent. Place conditions at the layer that accurately reflects business requirements before thinking about optimization.

### 4.2. DISTINCT and UNION

~~~sql
WITH all_customer_ids AS (
    SELECT customer_id FROM current_orders
    UNION
    SELECT customer_id FROM archived_orders
)
SELECT customer_id
FROM all_customer_ids
WHERE customer_id > 100;
~~~

UNION removes duplicate values across the two sets. The query block must preserve deduplication semantics and thus is not merged in the normal way. Changing UNION to UNION ALL keeps duplicate rows and alters semantics; do not change it merely hoping for a different plan.

### 4.3. Materialization Does Not Mean All Predicates Are Blocked

When a CTE is materialized, certain predicate pushdowns may still be supported by the optimizer depending on query structure. For example, a condition on a grouping column may be pushed into WHERE or HAVING when the transformation preserves semantics. Therefore, do not conclude that a materialized CTE must always compute all data before applying any outer predicates.

Read EXPLAIN and the optimizer trace to see which transformations MySQL applied. Pay special attention to predicates on aggregate columns: they cannot be turned into source-row filters before computing the aggregate if doing so changes the result.

## 5. Materialization and CTE Reusability

A major advantage of CTEs is the ability to reference the same name multiple times in a single SQL statement:

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

The customer_totals CTE is referenced in the outer JOIN and inside the scalar subquery. If the CTE is materialized, MySQL materializes the result once for the statement and reuses it across references, instead of building an independent copy for each usage site.

### 5.1. Automatic Indexes on Materialized Tables

MySQL can create internal indexes on materialized results if an index makes accessing the CTE more efficient. For example, a reference looking up by customer_id can benefit from an index on that column.

When the same CTE is referenced multiple times with different access predicates, the optimizer can create suitable indexes for each reference. These are internal indexes on the temporary table; they are not permanent indexes added to source tables.

You cannot request a specific internal index name as when creating indexes on real tables. Use EXPLAIN to observe the keys or access methods chosen by the optimizer.

### 5.2. Materialization Can Be Deferred

MySQL can defer materialization until the result is actually needed. If an earlier JOIN branch yields zero rows and the CTE does not need to be read, MySQL may skip building the intermediate table altogether.

Hence, do not describe materialization simply as "always executing the CTE before the outer query". The optimizer can choose an order and timing that avoids unnecessary work.

### 5.3. Cost of Materialization

Materialization can cost:

- CPU to execute the SELECT producing the CTE.
- Memory or disk space for the internal temporary table.
- I/O to write and read intermediate results.
- Overhead to build internal indexes.
- Cost to move data between query plan steps.

On the other hand, if a CTE is referenced multiple times, computing once and reusing can be cheaper than re-executing source logic at every site. The outcome depends on row count, column count, reference count, filter predicates, and the actual plan.

## 6. Recursive CTEs and Materialization

Recursive CTEs are used to traverse trees, hierarchies, or chained relationships. In MySQL, recursive CTEs are always materialized; they are never merged like a simple non-recursive CTE.

Example traversing an employee tree:

~~~sql
WITH RECURSIVE employee_tree AS (
    SELECT employee_id, manager_id, full_name, 0 AS depth
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT e.employee_id, e.manager_id, e.full_name, t.depth + 1
    FROM employees AS e
    JOIN employee_tree AS t
      ON e.manager_id = t.employee_id
)
SELECT *
FROM employee_tree
ORDER BY depth, employee_id;
~~~

The anchor member creates the root nodes; the recursive member finds employees whose manager_id points to already-found nodes. MySQL iterates the recursive member to append subsequent levels until no new rows remain or the recursion limit is hit.

### 6.1. Materialization in Recursive CTEs

A recursive CTE must store and expand intermediate results across each iteration. Consequently, MySQL materializes recursive CTE results. Do not apply a MERGE hint expecting to turn a recursive CTE into a merged query.

### 6.2. Controlling the Number of Iterations

MySQL provides the cte_max_recursion_depth variable to cap recursion depth. Inspect the value:

~~~sql
SELECT @@SESSION.cte_max_recursion_depth;
~~~

You can adjust it for a lab session:

~~~sql
SET SESSION cte_max_recursion_depth = 1000;
~~~

Do not increase the limit to mask a looping query or corrupted tree data. Check termination conditions, join keys, and the possibility of cycles in the data. Cycle detection and depth limits are two distinct concerns.

## 7. MERGE and NO_MERGE Optimizer Hints

MySQL provides the MERGE() and NO_MERGE() optimizer hints to suggest whether to merge or materialize the query block of a derived table, view, or CTE in supported cases.

### 7.1. Hinting to Merge

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;
~~~

MERGE(order_source) asks the optimizer to consider merging the CTE into the referencing query. If the CTE structure contains GROUP BY, DISTINCT, LIMIT, or other constructs prohibiting merge, the hint cannot override semantic rules.

### 7.2. Hinting to Materialize

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;
~~~

NO_MERGE(order_source) asks to keep the query block separate for materialization if the optimizer and query structure allow it. Materialization is not always better; it can build a large temporary table whereas merging can filter early on the base table.

### 7.3. Checking Whether a Hint Was Applied

After EXPLAIN, you can inspect warnings:

~~~sql
EXPLAIN
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;

SHOW WARNINGS;
~~~

If a hint is invalid, unrecognized, or cannot be applied, warnings may explain the issue. Also inspect the plan itself; do not assume a hint succeeded just because the SQL statement raised no error.

### 7.4. Do Not Use Hints as a Substitute for Analysis

Hints are tools to test hypotheses or address a well-understood edge case. Do not sprinkle MERGE/NO_MERGE onto every CTE. Changing data, updated statistics, or MySQL version upgrades can change what the optimal choice is.

## 8. Controlling Merge with optimizer_switch

The optimizer_switch variable includes the derived_merge option. This option affects merge decisions for derived tables, views, and CTEs within supported scopes.

Check its state:

~~~sql
SELECT @@SESSION.optimizer_switch;
~~~

In a lab environment, you can disable merging for the session:

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'derived_merge=off';
~~~

Re-run EXPLAIN to observe the plan, then restore:

~~~sql
SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Change only the session for testing. Do not set GLOBAL just to test a query because global configuration affects new connections. When testing a single CTE, an optimizer hint usually has a more targeted scope.

If changing optimizer_switch using a multi-option string, understand how assignments work and preserve other settings. Do not overwrite the entire configuration with a truncated list unintentionally.

## 9. Reading Plans with EXPLAIN

EXPLAIN shows how the optimizer intends to execute a SQL statement. For CTEs, the goal is to determine whether the query block is merged or materialized, which row sources are read, which predicates are applied, and which indexes are chosen.

### 9.1. Default EXPLAIN Format

~~~sql
EXPLAIN
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

When a CTE is merged, the plan usually shows direct access to the source table orders, with no separate materialization step for the CTE. Exact labels and formatting depend on MySQL version and EXPLAIN format.

### 9.2. EXPLAIN FORMAT=TREE

MySQL 8.0.16+ supports the TREE format:

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > 1000;
~~~

TREE represents iterators in a tree layout, making it convenient to read JOIN order and materialization steps. For a materialized CTE, the plan may show a node like Materialize CTE or an equivalent node; exact naming and detail depend on the version.

### 9.3. EXPLAIN FORMAT=JSON

JSON provides a structured plan:

~~~sql
EXPLAIN FORMAT=JSON
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id;
~~~

When materialized, the JSON structure can describe the derived/materialized query block and the subquery source. Use JSON when you need detailed attributes or automated plan parsing with tools. Do not rely on a single field name across versions; inspect the full structure.

### 9.4. EXPLAIN ANALYZE

MySQL 8.0.18+ supports EXPLAIN ANALYZE for compatible SELECT statements. It executes the query and displays timings, loop counts, and actual row counts:

~~~sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > 1000;
~~~

Standard EXPLAIN mainly provides estimates; EXPLAIN ANALYZE lets you compare estimates against actual row counts and timings. This command genuinely executes the SELECT, so heavy queries still consume resources. Run it in lab/staging or under evaluated load conditions; do not run it casually on production.

## 10. Signals to Look for in Plans

When inspecting EXPLAIN, focus on the following signals:

| Signal | Interpretation |
|---|---|
| Source table appears directly, no CTE materialize node | The CTE was likely merged into the outer query block |
| Materialize CTE node or equivalent materialization node in TREE | Optimizer creates an intermediate result for the CTE |
| `<derivedN>` or materialized query block info in other formats | Likely a materialized result source; examine the full plan |
| key shows the selected index | Verify whether the index supports JOIN/WHERE predicates |
| type or access method is ALL | Possible full table scan; evaluate against table size and selectivity |
| rows and filtered | Estimated rows read and percentage passing filter conditions |
| Loop count and actual rows in EXPLAIN ANALYZE | Actual workload processed by each iterator |
| Temporary table or sort | Inspect GROUP BY, DISTINCT, ORDER BY, and intermediate data size |

Do not jump to conclusions solely from seeing ALL or Materialize. A full table scan on a tiny table may be the cheapest option; materialization can save work when results are reused multiple times. Compare row counts, timings, and business goals.

## 11. Using Optimizer Trace When EXPLAIN Is Not Enough

Optimizer trace provides details on the decisions and transformations the optimizer considered. It can be enabled per session:

~~~sql
SET optimizer_trace = 'enabled=on';

WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';

SELECT TRACE
FROM information_schema.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
~~~

Trace helps uncover merge/materialize decisions, reasons a transformation was rejected, and access path choices. Trace output is lengthy and version-dependent; search for sections related to query blocks, derived/CTE handling, and transformations rather than reading it linearly like a log.

Optimizer trace is a diagnostic tool, not a replacement for EXPLAIN ANALYZE. Trace explains optimizer decisions; EXPLAIN ANALYZE gives iterator execution metrics.

## 12. Examples Comparing Merge and Materialization

Suppose there are two tables:

- customers: one row per customer, primary key customer_id.
- orders: one row per order, with customer_id, status, total_amount, and created_at.

### 12.1. Simple CTE That Can Merge

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount, created_at
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Run EXPLAIN:

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount, created_at
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Check whether the plan accesses orders directly and uses an appropriate index. Example index to evaluate:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Do not create indexes redundant with existing ones. If the query also needs total_amount and the index/engine supports covering scans appropriately, you can evaluate a covering index, while weighing storage and write overhead.

### 12.2. Aggregate CTE That Typically Materializes

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 1000;
~~~

GROUP BY and aggregates prevent merging. Results are materialized by customer_id before the JOIN. An index on orders(customer_id, status) or orders(status, customer_id) may fit depending on predicates and data distribution; use EXPLAIN to choose instead of mechanically applying one column order.

### 12.3. Multiply-Referenced CTE

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount,
       t.order_count
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

The CTE is used in both the JOIN and the scalar subquery. If materialized, the intermediate result is built once and reused. The optimizer can add internal indexes to support the different access patterns.

### 12.4. Same CTE, Testing Both Strategies

To verify in a lab, take a simple CTE and test hints:

~~~sql
-- Request merge
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';

-- Request materialization
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Compare plan nodes, estimated rows, indexes, and cost. If the CTE contains constructs forbidding merge, a MERGE hint cannot force the optimizer to violate semantics. If a hint is not applied, check SHOW WARNINGS.

## 13. CTE Optimization Workflow

When a CTE makes a query slow, follow these steps in order:

1. **Identify the required output:** what data granularity does each CTE represent, and does it require deduplication or aggregation?
2. **Check reference count:** is the CTE used once or multiple times; recomputing versus reusing can make a major difference.
3. **Inspect CTE structure:** look for GROUP BY, aggregates, DISTINCT, LIMIT, UNION, window functions, and factors preventing merge.
4. **Run EXPLAIN:** determine whether the CTE is merged or materialized, which tables are read, and which indexes are chosen.
5. **Inspect predicates:** which filters are applied before building the intermediate result, and which filter after materialization?
6. **Check width and size:** project only needed columns; shrink row count inside the CTE when semantics allow.
7. **Evaluate source indexes:** check indexes on filter, JOIN, and grouping columns; avoid adding redundant indexes or unnecessary write overhead.
8. **Measure actuals:** use EXPLAIN ANALYZE in an appropriate environment, comparing estimated rows with actual rows and loops.
9. **Test hints carefully:** compare MERGE and NO_MERGE to verify hypotheses, then evaluate on representative data.
10. **Re-verify output:** ensure moving predicates, replacing CTEs with JOINs, or switching strategies did not alter LIMIT, aggregate, duplicate, or NULL semantics.

## 14. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| CTE runs slowly despite simple query inside | CTE was materialized, creating a large intermediate table | Check EXPLAIN; inspect merge eligibility, hints, and filter predicates |
| Aggregate CTE does not merge | GROUP BY or aggregates prevent merge by rule | Evaluate materialization and source indexes; do not force semantically invalid merges |
| NO_MERGE makes no difference | CTE was already unmergeable or hint was ignored | Inspect SHOW WARNINGS and plan |
| MERGE has no effect | Query block structure prohibits merging | Remove prohibiting constructs only while preserving business results |
| CTE used twice yet computation is expensive | Plan did not reuse as expected or materialized result is huge | Inspect plan and trace; check reference count, size, and access paths |
| Temporary table causes high I/O | Large materialized result exceeds memory storage threshold | Trim input rows/columns if valid, check settings, and benchmark on staging |
| Outer predicate fails to reduce source data | Predicate was not pushed into CTE or was blocked by semantics | Inspect plan; put filter into the right query block if results stay identical |
| EXPLAIN ANALYZE overloads server | Command executes the actual query | Use lab/staging environment and appropriate data |
| Recursive CTE fails to merge | Recursive CTEs are always materialized | Tune anchor, recursive member, indexes, and termination conditions |
| Results change after pushing WHERE past LIMIT/GROUP BY | Filtering at the two positions has different semantics | Confirm business order; never move predicates arbitrarily |

## 15. Practice Lab: Observing Merge and Materialization

Perform this in a MySQL 8.0 lab database. The lab creates two separate tables; do not run it on production tables.

### 15.1. Create Sample Tables

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer_status (customer_id, status),
    KEY ix_lab_orders_status_customer (status, customer_id),
    CONSTRAINT fk_lab_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;
~~~

Load sample data:

~~~sql
INSERT INTO lab_customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO lab_orders
    (order_id, customer_id, status, total_amount, created_at)
VALUES
    (101, 1, 'PAID', 700.00, '2026-01-10 09:00:00'),
    (102, 1, 'PAID', 500.00, '2026-01-11 09:00:00'),
    (103, 1, 'PENDING', 200.00, '2026-01-12 09:00:00'),
    (104, 2, 'PAID', 1500.00, '2026-01-13 09:00:00'),
    (105, 2, 'CANCELLED', 300.00, '2026-01-14 09:00:00'),
    (106, 3, 'PAID', 250.00, '2026-01-15 09:00:00');
~~~

### 15.2. Step 1 — Simple CTE

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';
~~~

The result contains two PAID orders for customer 1. Note the number of returned rows and verify the query needs no aggregation or deduplication.

### 15.3. Step 2 — Observe a Merge-Eligible Plan

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';
~~~

Observe whether the plan accesses lab_orders directly or contains a materialization node. Because the table is tiny, the optimizer may choose a scan instead of an index; that alone does not prove merging failed. Read the query block structure and plan nodes.

### 15.4. Step 3 — Try NO_MERGE

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';

SHOW WARNINGS;
~~~

Compare the plan with the previous step. Look for a materialize or derived result node and check warnings if the hint was not applied. Then try MERGE(order_source) and note the difference.

### 15.5. Step 4 — Aggregate CTE

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 500;
~~~

GROUP BY and aggregates prevent merging. Identify the materialization node, aggregated row count, and the JOIN step with customers.

### 15.6. Step 5 — CTE Referenced Twice

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount,
       t.order_count
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

Identify the two places referencing the CTE. If the CTE is materialized, the intermediate result is created once and reused. Observe access paths and internal indexes if shown by EXPLAIN.

### 15.7. Step 6 — Measure with EXPLAIN ANALYZE

If the server is MySQL 8.0.18 or later:

~~~sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 500;
~~~

Compare actual rows, loops, and timings across nodes. Because the lab dataset is tiny, do not use absolute timings to conclude which strategy is faster in production; the goal is to understand plan structure.

### 15.8. Step 7 — Test optimizer_switch in the Session

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'derived_merge=off';

EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Compare the plan when merging is disabled. Restore the session setting immediately after testing and do not use SET GLOBAL in the lab.

### 15.9. Step 8 — Clean Up Lab Tables

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Drop the child table before the parent table to avoid violating foreign keys. Drop only the two lab tables just created.

**Expected outcomes:** able to explain merge and materialization; recognize constructs preventing merge; observe multiply-referenced CTEs; understand internal indexes and deferred materialization; read EXPLAIN TREE and EXPLAIN ANALYZE; know how to test optimizer hints/switches in a session.

## 16. Principles to Remember

- A CTE is a named query expression valid only within a single statement; it is not a long-lived physical table.
- A non-recursive CTE may be merged or materialized depending on query shape and optimizer decisions.
- Merging folds query blocks together, enabling predicate pushdown and direct optimization on base tables.
- Materialization creates an intermediate result; it incurs build, storage, and read costs and may create internal indexes.
- Aggregates, window functions, DISTINCT, GROUP BY, HAVING, LIMIT, UNION, and certain other constructs prevent merging.
- If a CTE is materialized and referenced multiple times, the result is built once for the statement and reused; the optimizer may create internal indexes for references.
- Materialization can be deferred until results are actually needed; do not assume a CTE always runs before the outer query.
- Recursive CTEs are always materialized; optimize the anchor, recursive member, indexes, and termination conditions.
- MERGE/NO_MERGE and optimizer_switch are controlled verification tools, not replacements for plan analysis.
- EXPLAIN shows the estimated plan; EXPLAIN ANALYZE executes the query and reports actual metrics from MySQL 8.0.18+.
- Read the entire plan, comparing estimated rows against actual rows, loop counts, indexes, and intermediate table costs.
- Never move predicates past LIMIT, GROUP BY, or DISTINCT without proving the results remain identical.

CTEs help structure queries, while merge and materialization are MySQL execution decisions. When you understand query block structure, cardinality, reference counts, and optimizer plans, you can write maintainable SQL while spotting temporary table overhead, predicate pushdown opportunities, and suitable indexes.
