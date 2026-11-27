# Reading Plans for CTEs, Derived Tables, Subqueries, and UNION

When an SQL statement contains CTEs, derived tables, subqueries, or UNIONs, EXPLAIN must be read per query block and by the relationships among them. A query block can be merged into an outer query block by the optimizer (merged), executed separately and stored in a temporary result (materialized), transformed into a semijoin/antijoin, or executed as a UNION branch.

Therefore, do not look at a single EXPLAIN row and assume the entire query executes in one uniform way. Identify each query block, see whether it remains separate in the execution plan or was merged, check where materialization occurs, and track row counts and loops across iterators.

This article explains how to read plans for:

- CTEs declared with WITH, including CTEs referenced once or multiple times.
- Derived tables placed in the FROM clause.
- Subqueries in WHERE, SELECT, or JOIN conditions, including correlated subqueries, EXISTS, and IN.
- UNION and UNION ALL, including deduplication and result sorting.

Examples target MySQL 8.0. Specific display details and optimization capabilities depend on the exact version; always check the plan on your running server.

## 1. What is a query block?

A query block is a SELECT unit within an SQL statement. A statement can contain one query block or multiple nested query blocks.

Example with a single query block:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE active = 1;
~~~

Example with two query blocks: the inner query is a subquery, and the outer query consumes its result.

~~~sql
SELECT employee_id, salary
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE enabled = 1
);
~~~

Example with a CTE:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = 1
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

The CTE creates a query block named active_employees. The optimizer can merge this query block into the outer query, or materialize its result into an internal temporary table.

In traditional EXPLAIN, the `id` and `select_type` columns provide clues about query blocks. In EXPLAIN FORMAT=JSON, the `query_block` structure and nested nodes clearly expose nesting relationships. EXPLAIN FORMAT=TREE displays iterators in a tree structure.

## 2. Preparing an illustrative schema

The following examples use employees and departments tables, plus a sales_orders table:

~~~sql
CREATE TABLE departments (
    department_id INT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (department_id)
) ENGINE = InnoDB;

CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    salary DECIMAL(12, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department_active
        (department_id, active),
    KEY idx_employees_salary (salary)
) ENGINE = InnoDB;

CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    employee_id BIGINT UNSIGNED NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_employee_total (employee_id, total),
    KEY idx_orders_total (total)
) ENGINE = InnoDB;
~~~

In plan explanations, index names are merely available structures for the optimizer to consider. Actual EXPLAIN output still depends on row counts, data distribution, statistics, parameters, and MySQL version.

## 3. Reading a CTE merged into the outer query

A CTE names a query block to make SQL readable and reusable:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

This CTE has no GROUP BY, DISTINCT, LIMIT, UNION, or constructs that usually block merging. The optimizer can merge the query block into the outer query, semantically equivalent to:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE active = TRUE
  AND department_id = 10;
~~~

When merging succeeds:

- The CTE does not necessarily appear as a separate temporary table in the plan.
- The `department_id` predicate can be combined with `active` in the same query block.
- The optimizer can use suitable indexes on `employees`.
- There is no cost of creating and reading a temporary table for this CTE.

### 3.1. Signs in EXPLAIN

Run:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

If the CTE is merged, the plan typically shows only the access path on `employees` rather than a step reading a temporary table named after the CTE. In JSON/TREE, the query block appears folded into the outer query block after optimization.

Do not expect EXPLAIN to always show a row named after the CTE. Not seeing a separate CTE name can be a sign it was merged.

## 4. Reading a materialized CTE

A CTE containing aggregation generally cannot merge under derived table merge rules. Example:

~~~sql
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    d.department_name,
    s.employee_count,
    s.average_salary
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

The `department_summary` CTE must compute aggregated results before the outer query uses them. The optimizer may materialize the CTE into an internal temporary table.

When materializing:

1. MySQL executes the query block producing the CTE.
2. Results are written into an internal temporary table.
3. The outer query reads the temporary table as a data source.
4. The optimizer can auto-generate an internal index on the temporary table if that helps joins or lookups.

### 4.1. Signs in EXPLAIN

~~~sql
EXPLAIN FORMAT=JSON
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    d.department_name,
    s.employee_count,
    s.average_salary
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

In the JSON plan, look for sections showing materialization or `materialized_from_subquery`. In traditional EXPLAIN, depending on plan shape and version, the query block producing the CTE may show `select_type` as `DERIVED` or `MATERIALIZED`; the outer query may read an internal temporary table name like `<derivedN>`.

In TREE, materialization is typically represented by a materialize iterator and an iterator reading the materialized result. Read child nodes to see which query block builds the temporary table and which parent node consumes it.

### 4.2. Materialize is not necessarily a bug

Materialization carries the cost of writing/reading a temporary table, yet sometimes reduces overall work:

- The aggregated result is dramatically smaller than the source table.
- The query block needs computing only once.
- Multiple references need to read the same CTE result.
- An internal index is built on the temporary table to serve a join or lookup.

What needs measuring is how many rows are produced, temporary data size, read counts, and iterator loop counts—not merely the presence of the word materialize.

## 5. CTEs referenced multiple times

A CTE can be referenced multiple times in the same statement:

~~~sql
WITH department_summary AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS average_salary
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT
    current_summary.department_id,
    current_summary.average_salary,
    previous_summary.department_id AS lower_salary_department
FROM department_summary AS current_summary
JOIN department_summary AS previous_summary
  ON previous_summary.average_salary < current_summary.average_salary
 AND previous_summary.department_id <> current_summary.department_id;
~~~

When a CTE is materialized and referenced multiple times, MySQL materializes the result once within the statement and can then re-read that result at each reference site. The optimizer can create different internal indexes on the temporary table to support each access pattern.

In the plan, look for:

- One query block generating the CTE result.
- Nodes reading the materialized result for each reference.
- Indexes or access methods used when reading the temporary table.
- Loop counts and row counts at each reading node.

Do not infer that a CTE always re-executes from scratch on every reference. Conversely, do not assume every CTE always materializes; a CTE can be merged whenever eligible.

## 6. When can a CTE or derived table not be merged?

MySQL can merge a derived table, view, or CTE into the outer query block, yet certain constructs prevent merging. Common cases include:

- Aggregate functions such as COUNT(), SUM(), AVG(), MIN(), or MAX().
- Window functions.
- DISTINCT.
- GROUP BY.
- HAVING.
- LIMIT.
- UNION or UNION ALL.
- Subqueries in the query block's select list.
- User variable assignments.
- A query block containing only literals without reading any table.

Beyond those constructs, merging can also be blocked if merging would push the outer query block past the maximum allowed number of joined tables.

When merging is impossible, MySQL generally considers materialization. This does not mean every derived table always materializes across all versions or cases; always inspect the actual execution plan.

### 6.1. Example where GROUP BY forces keeping the query block

~~~sql
EXPLAIN
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.employee_count > 5;
~~~

The inner query block performs GROUP BY. The optimizer cannot simply replace it with a filter on `employees` rows while bypassing aggregation semantics. The plan typically includes an intermediate result creation step followed by the outer query reading that result.

### 6.2. Simple derived tables can merge

~~~sql
EXPLAIN
SELECT e.employee_id, e.salary
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
) AS e
WHERE e.department_id = 10;
~~~

This derived table has no construct blocking merge. Once merged, the outer query's condition can be combined with the inner condition, and indexes on `employees` are considered directly.

## 7. Filter conditions can be pushed into derived tables

When a derived table cannot merge, the optimizer may still push certain predicates from the outer query into the inner query block. This is derived condition pushdown.

Example:

~~~sql
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.department_id = 10;
~~~

The condition `department_id = 10` involves only the grouping key. The optimizer can push this predicate into the inner query block, shrinking the number of groups generated.

With a predicate on the aggregated result:

~~~sql
SELECT summary.department_id, summary.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS summary
WHERE summary.employee_count > 5;
~~~

The predicate `employee_count > 5` depends on `COUNT()`. It can be pushed down as a `HAVING` condition inside the inner query block, preserving post-aggregation filtering semantics.

Derived condition pushdown has its own prerequisites and limits. For example, `LIMIT` inside a derived table blocks certain pushdowns because early filtering could alter which rows are kept. With `UNION`, eligible conditions can be pushed down into each `SELECT` branch.

Derived condition pushdown was introduced in MySQL 8.0.22. If your system runs an older release, do not expect the same plan. Check version, `optimizer_switch`, and EXPLAIN.

## 8. Reading derived tables in EXPLAIN

A derived table is a SELECT inside FROM:

~~~sql
SELECT e.employee_id, totals.order_count
FROM employees AS e
JOIN (
    SELECT employee_id, COUNT(*) AS order_count
    FROM sales_orders
    GROUP BY employee_id
) AS totals
  ON totals.employee_id = e.employee_id;
~~~

When a derived table is materialized, traditional EXPLAIN may show a row with `select_type = DERIVED` for the inner query block and a table named like `<derivedN>` in the outer query block.

In JSON, you may see `materialized_from_subquery` alongside the generating query block. In TREE, there is typically a materialize node and a node reading the derived table.

If the derived table is merged, there is no separate `<derivedN>` reading step; the base tables of the derived query appear directly in the outer query's plan.

When reading, answer:

1. Was the inner query block kept separate or merged?
2. If materialized, how many source rows did it read?
3. How many result rows did it produce?
4. How does the outer query read the temporary table—scan, index lookup, or another access method?
5. Were any predicates pushed down into the inner query block?
6. Are there additional sorts, aggregates, or temporary tables beyond materialization?

## 9. Using MERGE and NO_MERGE for testing

MySQL supports optimizer hints to suggest merging or not merging a derived table/CTE when eligible:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT /*+ MERGE(active_employees) */
    employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

You can also request no merging:

~~~sql
EXPLAIN
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE active = TRUE
)
SELECT /*+ NO_MERGE(active_employees) */
    employee_id, salary
FROM active_employees
WHERE department_id = 10;
~~~

Hints take effect only if the query block is eligible and the referenced object name is valid. A hint cannot make an unmergeable query block mergeable.

Use hints to compare plans and measure cost, not to scatter hints into production by default. If you need to pin a strategy, document the rationale, version, and benchmark results so it can be re-evaluated when schema or data shifts.

## 10. Reading subqueries in WHERE: IN and EXISTS

Subqueries in WHERE typically express existence or set membership conditions.

IN example:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE enabled = TRUE
);
~~~

EXISTS example:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
      AND so.total > 1000
);
~~~

The EXISTS subquery references `e.employee_id` from the outer query, making it a correlated subquery as written.

The optimizer can transform eligible IN/EXISTS subqueries into semijoins. A semijoin only checks whether at least one matching row exists; it does not duplicate outer rows when multiple inner rows match.

When the transformation applies, the plan may exhibit strategies such as FirstMatch, LooseScan, Duplicate Weedout, table pullout, or materialization. Names and display format depend on the EXPLAIN format and version.

### 10.1. Conditions for semijoin transformation

Semijoin transformation typically applies to IN/EXISTS subqueries in eligible positions within WHERE or ON, usually at top level or inside an AND chain.

Constructs that can prevent transformation include:

- The subquery contains UNION.
- The subquery has aggregates or GROUP BY.
- The subquery has HAVING.
- The subquery has LIMIT.
- The subquery has window functions.
- Subquery structure violates positional or correlation rules supported by the optimizer.

The exact checklist depends on version and subquery shape. Without transformation, the subquery may remain a separate query block or be materialized.

### 10.2. Signs in EXPLAIN

In traditional EXPLAIN, an untransformed subquery may appear as `SUBQUERY` or `DEPENDENT SUBQUERY`. A materialized subquery may appear as `MATERIALIZED` paired with an internal table like `<subqueryN>`.

If semijoin transformation applies, the subquery may no longer appear as an independent subquery row. Its underlying tables are folded into the outer query's join plan. TREE/JSON usually clarifies the post-transformation join structure better.

Do not mistake the absence of a SUBQUERY row for the subquery being ignored. It may have been transformed into part of the join plan.

## 11. Correlated subqueries and dependent subqueries

A correlated subquery references a column from an outer query block:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    (
        SELECT MAX(so.total)
        FROM sales_orders AS so
        WHERE so.employee_id = e.employee_id
    ) AS largest_order
FROM employees AS e
WHERE e.active = TRUE;
~~~

The subquery uses `e.employee_id`, so its output depends on the current `employees` row.

If the subquery stays a separate query block, traditional EXPLAIN may show `select_type = DEPENDENT SUBQUERY`. This indicates the query block depends on data from an outer query block. The subquery may execute repeatedly per correlated value; check `loops` in EXPLAIN ANALYZE for actual invocation counts.

With index `idx_orders_employee_total (employee_id, total)`, MySQL can look up orders by `employee_id`. However, actual index usage and MAX optimization depend on data, statistics, and version.

### 11.1. Reading loops in EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    e.employee_id,
    (
        SELECT MAX(so.total)
        FROM sales_orders AS so
        WHERE so.employee_id = e.employee_id
    ) AS largest_order
FROM employees AS e
WHERE e.active = TRUE;
~~~

In TREE output, inspect:

- The iterator reading `employees` and its actual row count.
- The iterator performing lookups in `sales_orders`.
- `loops` on the subquery iterator.
- Average rows per loop and actual execution time.

If the outer query returns many employees and the subquery executes many loops, iteration cost can be substantial. Still, do not conclude a rewrite is mandatory solely from high loops; a tiny index lookup can still beat materializing or joining an entire table.

### 11.2. Uncorrelated subqueries

A subquery that does not reference an outer query block:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
    WHERE active = TRUE
);
~~~

This is an independent scalar subquery. If kept separate, EXPLAIN may show `select_type = SUBQUERY`. It can be evaluated once and its result reused throughout the statement rather than re-running for every employee.

In the JSON plan, properties such as `dependent` and `cacheable` clarify whether a subquery depends on outer queries or can be cached. Read them alongside iterators and loops rather than guessing from SQL text alone.

## 12. NOT EXISTS, NOT IN, and antijoin

NOT EXISTS expresses that no matching row exists in the child table:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
);
~~~

Semantically, this is an antijoin condition: retain outer rows when no inner row matches.

MySQL 8.0.17 added the ability to transform certain NOT IN, NOT EXISTS, and equivalent conditions into antijoins. When transformed, the subquery can integrate into the join plan instead of appearing as a separate dependent subquery.

### 12.1. Watch out for NULL in NOT IN

NOT IN follows SQL three-valued logic. If the inner result set contains NULL, the comparison evaluates to UNKNOWN and excludes the outer row from WHERE.

Example:

~~~sql
SELECT 10
WHERE 10 NOT IN (20, NULL);
~~~

This query returns zero rows because the expression cannot evaluate to TRUE.

NOT EXISTS does not share that behavior:

~~~sql
SELECT e.employee_id
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
);
~~~

When converting NOT IN to NOT EXISTS or vice versa, explicitly verify NULL possibilities on both sides. The two expressions are equivalent only when NULL and comparison guarantees hold.

### 12.2. When antijoin transformation does not apply

Transformation eligibility depends on subquery shape, predicate position, data types, and nullability. With nullable expressions, MySQL generally skips standard antijoin transformation to preserve exact UNKNOWN semantics. Certain explicit forms like `NOT IN (...) IS NOT FALSE` or `IN (...) IS NOT TRUE` may enable transformation under specific conditions.

In EXPLAIN, if antijoin is chosen, TREE/JSON may display an anti-join or equivalent strategy. Otherwise, the query block may stay a separate subquery or be materialized. Always verify the actual execution plan.

## 13. Recursive CTEs in execution plans

Recursive CTEs are commonly used to traverse trees, graphs, or generate sequences. A recursive CTE consists of:

- Anchor member: the initial query, not referencing the CTE itself.
- Recursive member: the continuing query referencing the CTE to produce the next iteration.
- UNION ALL or UNION combining anchor and recursive member results.

Example employees table with manager hierarchy:

~~~sql
CREATE TABLE org_employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_org_manager (manager_id)
) ENGINE = InnoDB;
~~~

Query finding subordinates of a manager:

~~~sql
WITH RECURSIVE employee_tree AS (
    SELECT
        employee_id,
        manager_id,
        employee_name,
        0 AS depth
    FROM org_employees
    WHERE employee_id = 100

    UNION ALL

    SELECT
        child.employee_id,
        child.manager_id,
        child.employee_name,
        parent.depth + 1
    FROM org_employees AS child
    JOIN employee_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, manager_id, employee_name, depth
FROM employee_tree;
~~~

A recursive CTE executes iteratively: the anchor produces initial rows, the recursive member reads generated rows to find the next level, and iteration continues until no new rows emerge or the recursion limit is hit.

Recursive CTEs are materialized; they are not merged like simple non-recursive CTEs. When reading TREE/JSON, look for recursive nodes, materialization nodes, and the iterator reading `org_employees` inside the recursive member. An index on `manager_id` is vital for finding children per manager.

### 13.1. Controlling loops and recursion limits

If data contains cycles, a recursive CTE using UNION ALL can keep generating rows indefinitely. Query design needs cycle protection, such as tracking paths or ensuring acyclic data.

MySQL enforces a recursion iteration limit via `cte_max_recursion_depth`. Check it with:

~~~sql
SELECT @@cte_max_recursion_depth;
~~~

Raising the limit does not fix infinite cycles or runaway row generation. Verify termination conditions and result size before altering the limit.

## 14. Reading plans for UNION and UNION ALL

UNION combines results from multiple SELECT statements having matching column counts and compatible data types.

~~~sql
SELECT employee_id AS source_id, employee_name AS source_name
FROM employees
WHERE active = TRUE

UNION ALL

SELECT order_id AS source_id, CAST(total AS CHAR(40)) AS source_name
FROM sales_orders
WHERE total > 10000;
~~~

The example above solely illustrates UNION ALL structure and compatible branch types. In real applications, choose consistent, semantically meaningful column types across both branches.

UNION ALL retains all rows from all branches, including duplicates. UNION (equivalent to UNION DISTINCT by default) eliminates duplicate rows from the combined result.

### 14.1. Cost differences

| Form | Behavior | Extra work |
|---|---|---|
| UNION ALL | Keeps all rows from each branch | No cross-branch deduplication needed |
| UNION DISTINCT or UNION | Removes duplicates across all result columns | Requires comparison/deduplication, typically using a temporary table |

UNION DISTINCT can consume extra CPU, memory, and I/O for deduplication. UNION ALL generally does less work, but should only be used when business rules allow keeping duplicates.

If a global ORDER BY follows UNION, MySQL must sort the combined result as requested. That can introduce a sort or temporary table even when using UNION ALL.

### 14.2. Signs in EXPLAIN

~~~sql
EXPLAIN
SELECT employee_id AS source_id
FROM employees
WHERE active = TRUE

UNION ALL

SELECT employee_id AS source_id
FROM sales_orders
WHERE total > 10000;
~~~

Traditional EXPLAIN may display:

- The first SELECT branch typically labeled PRIMARY.
- Subsequent branches with `select_type = UNION`.
- The combined step may show `select_type = UNION RESULT` and a table name like `<union1,2>`.

With UNION DISTINCT, the plan may reveal deduplication work or a temporary table. UNION ALL can skip deduplication and in some cases avoid materializing the whole result; actual plan shape still depends on ORDER BY, LIMIT, and other factors.

In JSON/TREE, inspect each branch's query block, the index chosen per table, and the node combining results. Never assume both branches use the same index or have similar row counts.

### 14.3. ORDER BY and LIMIT with UNION

An ORDER BY at the end applies to the entire UNION result:

~~~sql
(SELECT employee_id AS id
 FROM employees
 WHERE active = TRUE)
UNION ALL
(SELECT employee_id AS id
 FROM sales_orders
 WHERE total > 10000)
ORDER BY id
LIMIT 50;
~~~

ORDER BY/LIMIT inside individual branches have branch-local scope and require parentheses when applied explicitly to individual SELECTs. A global ORDER BY may require sorting the combined output after branches run.

When analyzing, check:

- How many rows each branch reads.
- Each branch's indexes and access methods.
- Whether deduplication occurs.
- Whether a global sort occurs.
- Whether LIMIT reduces rows processed per branch or only caps the final output.

## 15. Common select_type values when reading query blocks

Traditional EXPLAIN has a `select_type` column. Common values in queries with nested query blocks:

| select_type | General meaning |
|---|---|
| SIMPLE | Simple SELECT without UNION or subqueries needing separate representation |
| PRIMARY | Outermost query block in a complex query structure |
| SUBQUERY | Independent subquery kept as a separate query block |
| DEPENDENT SUBQUERY | Subquery depending on values from an outer query block |
| DERIVED | Query block in FROM retained as a derived table |
| MATERIALIZED | Subquery materialized into a temporary result |
| UNION | Any SELECT branch in a UNION except the first |
| DEPENDENT UNION | UNION branch depending on an outer query block |
| UNION RESULT | Step combining UNION results |

These labels categorize query blocks; they are not a speed ranking. For instance, DEPENDENT SUBQUERY is not automatically bad if the outer query produces few rows and each subquery lookup is ultra-cheap.

In a multi-layered SQL statement, `id` should not necessarily be read strictly as top-to-bottom execution order. Combine `id`, `select_type`, `table`, JSON/TREE, and dependency relationships to understand query blocks.

## 16. Reading EXPLAIN FORMAT=JSON

JSON exposes query block structure and materialization details more clearly than tabular format.

Example:

~~~sql
EXPLAIN FORMAT=JSON
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

When reading JSON, look for these elements if present:

- `query_block`: contents of a query block.
- `nested_loop`: join branches and access order.
- `table`: table read, access type, and index.
- `materialized_from_subquery`: query block generating a materialized result.
- `using_temporary_table`: indicator of temporary table usage in the described structure.
- `attached_subqueries`: subqueries attached to part of a query block.
- `dependent` and `cacheable`: dependency and cacheability metadata of a subquery.
- `union_result`: node representing UNION output.

Not every field appears in every plan. JSON structure changes with query type and MySQL version.

### 16.1. Reading materialized_from_subquery

When a query block is materialized, JSON can describe the generating query block inside `materialized_from_subquery`. Expand this node to check:

1. Which source tables are scanned.
2. Which indexes are used.
3. Whether aggregates, sorts, or temporary tables occur inside.
4. Estimated rows generated.
5. How the outer query reads the materialized result.

If you look only at the outer query node, you can miss the biggest cost hiding inside the temporary table build step.

## 17. Reading EXPLAIN FORMAT=TREE

On MySQL 8.0.16 and later, EXPLAIN FORMAT=TREE shows plans as an iterator tree:

~~~sql
EXPLAIN FORMAT=TREE
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

TREE is helpful because it clearly reveals:

- Which iterator is a child of which iterator.
- Which table or query block is read first.
- Where Materialize creates temporary data.
- Whether joins use nested loop, hash join, or another strategy.
- At which iterator filter conditions are applied.
- Whether sorts, aggregates, or duplicate removal occur.

When reading the tree, start from the outermost iterator returning results to the client, then walk down child iterators to trace where data originates. Do not confuse node display order with execution counts; use EXPLAIN ANALYZE to inspect `loops`.

## 18. EXPLAIN ANALYZE: verifying execution metrics

Standard EXPLAIN gives the plan and estimates. EXPLAIN ANALYZE executes the SELECT statement and adds timings, actual row counts, and loop counts for iterators. This feature has been available since MySQL 8.0.18.

~~~sql
EXPLAIN ANALYZE
WITH department_summary AS (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    WHERE active = TRUE
    GROUP BY department_id
)
SELECT d.department_name, s.employee_count
FROM department_summary AS s
JOIN departments AS d
  ON d.department_id = s.department_id
WHERE d.enabled = TRUE;
~~~

Metrics to read:

- `estimated rows`: rows predicted by the optimizer.
- `actual rows`: rows actually emitted by the iterator.
- `loops`: how many times the iterator was invoked.
- `actual time`: execution timing reported for the iterator.

An iterator with small actual rows yet huge loops can still create substantial total cost. Conversely, a materialize step may incur upfront time yet execute only once to serve multiple outer reads.

EXPLAIN ANALYZE runs the real query. For large queries or expensive subqueries, assess load and pick an appropriate environment before executing.

## 19. Comparing two ways of writing SQL

Suppose we need employees with at least one order exceeding 1,000:

~~~sql
SELECT e.employee_id, e.employee_name
FROM employees AS e
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS so
    WHERE so.employee_id = e.employee_id
      AND so.total > 1000
);
~~~

It could be rewritten as a JOIN:

~~~sql
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees AS e
JOIN sales_orders AS so
  ON so.employee_id = e.employee_id
WHERE so.total > 1000;
~~~

Both forms can produce the exact same result set when DISTINCT is applied properly, yet execution plans may differ:

- EXISTS can be transformed into a semijoin.
- JOIN can generate many intermediate rows for an employee with many orders, then require deduplicating via DISTINCT.
- The optimizer may choose different join orders.
- Indexes and selectivity on `total`/`employee_id` influence the plan.

Do not pick a rewrite just because the SQL looks shorter. Verify result equivalence first, then compare EXPLAIN ANALYZE on representative data.

### 19.1. Controlled comparison steps

1. Keep schema, indexes, data, and parameters identical.
2. Run EXPLAIN for each SQL variant.
3. Compare query blocks, join order, materialization, and access paths.
4. Run EXPLAIN ANALYZE under equivalent load conditions.
5. Compare actual rows, loops, timings, and intermediate row counts.
6. Verify returned results are identical, especially regarding NULLs and duplicates.
7. Repeat measurements to avoid concluding from one outlier run.

## 20. Materialization can be deferred

When a derived table or CTE needs materialization, MySQL may defer building the temporary table until the result is actually needed.

Example:

~~~sql
SELECT d.department_id, s.employee_count
FROM departments AS d
JOIN (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) AS s
  ON s.department_id = d.department_id
WHERE d.department_id = -1;
~~~

If the `departments` query block returns zero rows, MySQL may not need to materialize the downstream derived table at all. This is deferred materialization; thus seeing a materialize node in a plan does not guarantee it executes in every run.

EXPLAIN shows the projected plan. EXPLAIN ANALYZE shows how many times the node actually ran during the measured execution.

## 21. Checking relevant optimizer switches

You can inspect optimization flag states in the session:

~~~sql
SELECT @@optimizer_switch;
~~~

Flags relevant to this topic, depending on version:

- `derived_merge`: enables merging eligible derived tables and views.
- `derived_condition_pushdown`: enables pushing predicates into derived tables.
- `semijoin`: enables semijoin transformations.
- `materialization`: enables subquery materialization strategy.
- `subquery_materialization_cost_based`: governs cost-based materialization choices where applicable.

Do not alter `optimizer_switch` merely to force an example into a desired plan. First save current values, identify the relevant flags, and compare plans/benchmarks in a test session. Optimizer switches can affect many queries simultaneously.

## 22. Common false conclusions

**"CTEs always create temporary tables."** No. Non-recursive CTEs can be merged or materialized depending on structure and optimizer choices. Recursive CTEs are materialized.

**"Not seeing the CTE name in EXPLAIN means MySQL skipped the CTE."** No. Its query block may have been merged into the outer query.

**"Every derived table must materialize."** No. Simple derived tables can merge. Look for `<derivedN>` or materialization signs in JSON/TREE.

**"Materialization is always slow."** No. Building a temporary result has a cost, yet it can shrink row counts, compute a query block once, or support multiple reads via internal indexes.

**"A CTE referenced twice definitely runs twice."** No. When materialized, the CTE result can be built once and reused across multiple sites.

**"DEPENDENT SUBQUERY is always a design bug."** No. Inspect outer row counts, loops, access paths, and per-lookup cost.

**"EXISTS is always faster than IN."** No. The optimizer can transform eligible forms into semijoins and pick strategies by cost.

**"NOT IN and NOT EXISTS are always equivalent."** No. NULL values can alter NOT IN results.

**"UNION ALL and UNION are the same."** No. UNION removes duplicates; UNION ALL keeps duplicates. Deduplication adds extra work.

**"UNION ALL never uses a temporary table."** No. A global ORDER BY or other execution requirements can still require a sort or temporary table.

**"Seeing materialize in EXPLAIN means the temporary table is always built."** No. Materialization can be deferred and occur only when the iterator is actually invoked.

**"EXPLAIN estimates and EXPLAIN ANALYZE are the same kind of output."** No. Standard EXPLAIN gives plans and estimates; EXPLAIN ANALYZE runs the query to report actual rows, loops, and timings.

## 23. Workflow for reading multi-query-block plans

1. Identify every SELECT and query block: outer query, CTEs, derived tables, subqueries, and UNION branches.
2. Run tabular EXPLAIN to inspect `id`, `select_type`, `table`, `type`, `possible_keys`, `key`, `rows`, and `Extra`.
3. Determine whether CTEs/derived tables were merged or materialized; look for `<derivedN>` and materialization indicators.
4. For CTEs referenced multiple times, check how many times temporary results are read and inspect internal indexes.
5. For subqueries, identify correlated vs. uncorrelated; check for semijoin/antijoin, materialization, or dependent subquery.
6. For recursive CTEs, check anchor, recursive member, termination condition, indexes used per iteration, and generated row counts.
7. For UNIONs, inspect each branch separately, noting UNION DISTINCT vs. ALL, deduplication steps, and global sorts.
8. Use EXPLAIN FORMAT=JSON or TREE to clarify iterator relationships and materialization nodes.
9. Use EXPLAIN ANALYZE to compare estimated rows with actual rows, loops, and timings.
10. Only rewrite SQL, add indexes, or apply hints after locating the costly node and verifying result equivalence.

## 24. Checklist

- [ ] Identified all query blocks in the SQL statement.
- [ ] Understood whether CTEs/derived tables were merged or materialized.
- [ ] Checked which constructs block merging, such as GROUP BY, DISTINCT, LIMIT, or UNION.
- [ ] Checked for derived condition pushdown if a query block was materialized.
- [ ] Verified whether a multi-reference CTE was materialized once.
- [ ] Distinguished SUBQUERY from DEPENDENT SUBQUERY.
- [ ] Checked semijoin/antijoin transformations for IN, EXISTS, NOT IN, and NOT EXISTS.
- [ ] Verified NULL semantics before replacing NOT IN with NOT EXISTS.
- [ ] Inspected both anchor and recursive members of any recursive CTE.
- [ ] Confirmed termination conditions and recursion depth limits.
- [ ] Distinguished UNION DISTINCT from UNION ALL.
- [ ] Checked for sorts/temporary tables on UNION with ORDER BY.
- [ ] Read JSON/TREE to locate nodes producing and consuming temporary results.
- [ ] Used EXPLAIN ANALYZE to confirm loops and actual rows where appropriate.
- [ ] Measured the query on representative data and verified identical results after any rewrite.

## Conclusion

Execution plans for CTEs, derived tables, subqueries, and UNIONs must be read per query block and by the data flow across blocks. CTEs/derived tables can be merged or materialized; subqueries can stay separate, materialize, or transform into semijoins/antijoins; UNIONs may require deduplication and sorting.

Use traditional EXPLAIN to identify query blocks, JSON/TREE to trace structure and materialization, and EXPLAIN ANALYZE to verify actual row counts, loops, and timings. Base evaluations on per-iterator cost and result correctness rather than reacting to a single label like DERIVED, DEPENDENT SUBQUERY, or MATERIALIZED.
