# Derived Merge, Materialization, and Filter Pushdown

MySQL frequently processes multi-layered queries: a subquery in `FROM`, a view, or a common table expression (CTE) can produce an intermediate result that the outer query further filters or joins. The optimizer has two primary ways to handle that intermediate layer: **merge** the subquery into the outer query block, or **materialize** its result into an internal temporary table.

When merging is not possible, MySQL can still optimize via **derived condition pushdown**: pushing predicates from the outer query down into the derived table before materializing it. This reduces the number of rows computed and stored in the intermediate result. Understanding these three mechanisms helps you read execution plans, predict costs, and write optimizer-friendly queries.

## Objectives

After this lesson, you will be able to:

- Distinguish merging from materialization for derived tables, views, and CTEs.
- Identify query constructs that typically prevent MySQL from merging.
- Explain deferred materialization, internal temporary tables, and automatic indexes.
- Describe how derived condition pushdown moves predicates into `WHERE` or `HAVING`.
- Recognize why `LIMIT` and certain semantic boundaries block condition pushdown.
- Use `EXPLAIN`, `EXPLAIN ANALYZE`, and optimizer trace to inspect optimizer decisions.

Examples assume MySQL 8.0 or later and InnoDB. `EXPLAIN ANALYZE` was introduced in MySQL 8.0.18; derived condition pushdown was introduced in MySQL 8.0.22. Exact behavior also depends on server version and optimizer settings.

The main examples use the following transactions table:

```sql
CREATE TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_sales_status_customer (status, customer_id),
    KEY ix_sales_created_at (created_at)
) ENGINE = InnoDB;
```

## 1. What Is a Derived Table?

A derived table is a subquery appearing in the `FROM` clause. Its result is assigned an alias for use by the outer query:

```sql
SELECT d.customer_id, d.amount
FROM (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

In this example, the inner query creates derived table `d`; the outer query filters rows from `d`. Views and CTEs can create a similar intermediate query block:

```sql
WITH paid_sales AS (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'
)
SELECT customer_id, amount
FROM paid_sales
WHERE customer_id = 42;
```

If MySQL always had to build the entire `d` result before filtering, the query could waste memory, I/O, and time. If it can merge the two layers into a single query block, the optimizer gains opportunities to pick indexes, reorder joins, and apply filters early.

## 2. Merge: Combining Query Blocks

**Derived table merge** replaces a derived table with its defining query inside the outer query block. Conceptually, the example in Section 1 can be merged into:

```sql
SELECT sales.customer_id, sales.amount
FROM sales
WHERE sales.status = 'PAID'
  AND sales.customer_id = 42;
```

When merging succeeds, `d` does not need to exist as a standalone temporary table. The optimizer can combine inner and outer predicates, use indexes on `sales`, and optimize joins as one unified query.

### When Is Merging Beneficial?

Merging is generally beneficial when the derived table performs only straightforward column projection and filtering. Example:

```sql
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

If the table has index `(status, customer_id)`, the optimizer can use both predicates to target a narrow index slice. No intermediate table containing all `PAID` sales needs to be built before filtering `customer_id`.

Merging also lets the optimizer consider tables from multiple query blocks together. This can improve join order, access path selection, and predicate pushdown to base tables.

### Constructs That Commonly Prevent Merging

A derived table cannot be merged when removing query boundaries would alter semantics. Constructs that typically force MySQL to materialize include:

- Aggregate functions such as `SUM()`, `COUNT()`, `AVG()`.
- `GROUP BY` or `HAVING`.
- `DISTINCT`.
- `LIMIT`.
- `UNION` or `UNION ALL`.
- Window functions.
- Certain queries containing subqueries in the select list or user-variable assignments.

For example, a per-customer aggregation query must preserve grouping boundaries:

```sql
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    GROUP BY customer_id
) AS d
WHERE d.total_amount > 1000;
```

Merging arbitrarily would allow filtering to alter the row set before summation. MySQL must keep aggregation in its own query block, so this derived table is materialized. Even so, the optimizer may still push safe outer predicates inside, as shown later.

`ALGORITHM=TEMPTABLE` on a view also requires processing the view via a temporary table, preventing view merging. `ALGORITHM=MERGE` requests merging when the view definition and context permit; `UNDEFINED` lets MySQL choose.

## 3. Materialization: Creating Intermediate Results

When a derived table cannot or should not be merged, MySQL can **materialize** it into an internal temporary table. The outer query block reads that result as a data source.

Conceptual flow:

```text
Subquery in FROM
          |
          v
  Execute inner query block
          |
          v
  Create internal temporary table
          |
          v
  Outer query reads and
  filters/joins temp result
```

The temporary table is an execution detail managed by MySQL, not an application table you create or drop. Depending on size, column types, and configuration, an internal temporary table may stay in memory or spill to disk storage.

### Materialization Can Be Deferred

MySQL can defer materialization until the derived table result is actually needed. If another table in a join is processed first and returns zero rows, the optimizer can skip materializing the derived table entirely because it never needs to be read.

This means materialization does not necessarily happen the moment a statement starts. When reading execution plans, check join order and conditions that may short-circuit a branch.

### Automatic Indexes on Temporary Tables

When materializing, MySQL can create an internal index on one or more columns of the temporary table if the optimizer predicts lookups on those columns will lower cost. For example, if the outer query joins the derived table on `customer_id`, an automatic index makes probing rows in the temporary result faster.

For a materialized CTE referenced multiple times, MySQL can create suitable indexes for different access patterns. This index creation is managed by the optimizer, not persisted as a schema index.

Materialization helps when intermediate results are reused multiple times or when aggregation boundaries must be preserved. However, it incurs the cost of creating a temporary table, writing/reading rows, and building indexes. If the result is huge, that cost can be substantial.

## 4. Derived Condition Pushdown

When a derived table must be materialized, MySQL can still push conditions from the outer query down into the inner query block. This mechanism is called **derived condition pushdown**. Its goal is eliminating rows early before the intermediate result is populated.

Example:

```sql
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

If for some reason the derived table is materialized, the predicate `d.customer_id = 42` can be pushed down into the inner query:

```sql
SELECT sale_id, customer_id, amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42;
```

Instead of materializing all paid sales, MySQL only needs to produce rows matching customer 42. Pushing the condition down reduces intermediate rows, memory, and I/O.

Derived condition pushdown has been supported since MySQL 8.0.22 and is controlled by the `derived_condition_pushdown` flag in `optimizer_switch`.

## 5. Pushing Conditions Through GROUP BY: WHERE and HAVING

For a derived table containing `GROUP BY`, outer predicates fall into two categories:

- Predicates on grouping columns can be pushed into `WHERE` before aggregation.
- Predicates on aggregated results must be pushed into `HAVING`, after computing aggregates.

Example:

```sql
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

The optimizer can transform the inner query block into an equivalent form:

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42
GROUP BY customer_id
HAVING SUM(amount) > 1000;
```

`customer_id = 42` applies before grouping, so MySQL only needs to read transactions for that customer. `total_amount > 1000` depends on `SUM(amount)` and must be evaluated post-aggregation in `HAVING`.

An aggregate condition cannot go into `WHERE` because at the moment `WHERE` runs, `SUM(amount)` does not yet exist. Preserving semantic evaluation order is a strict requirement for any pushdown.

## 6. Pushing Conditions Into Each UNION Branch

A derived table containing `UNION` or `UNION ALL` cannot be merged like a simple query block. However, MySQL can push eligible outer predicates down into each branch:

```sql
SELECT u.customer_id, u.amount
FROM (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'

    UNION ALL

    SELECT customer_id, amount
    FROM sales_archive
    WHERE status = 'PAID'
) AS u
WHERE u.customer_id = 42;
```

In this example, assume the archive table `sales_archive` shares the same columns and data types as `sales`; you can create a test table with `CREATE TABLE sales_archive LIKE sales` and populate historical data.

The predicate can be pushed into both branches:

```sql
SELECT customer_id, amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42

UNION ALL

SELECT customer_id, amount
FROM sales_archive
WHERE status = 'PAID'
  AND customer_id = 42;
```

Each branch can leverage its own source-table indexes. The intermediate result after `UNION ALL` is smaller because MySQL avoids gathering all customers before filtering outside.

## 7. Why Can't Every Condition Be Pushed Down?

The optimizer is allowed to push down a condition only when the transformation preserves the query result. `LIMIT` is a clear example:

```sql
SELECT d.sale_id, d.customer_id
FROM (
    SELECT sale_id, customer_id
    FROM sales
    ORDER BY created_at DESC
    LIMIT 10
) AS d
WHERE d.customer_id = 42;
```

The meaning of this query is: retrieve the 10 latest sales across the entire table, then keep only those belonging to customer 42. Pushing `customer_id = 42` inside before `LIMIT` would change it to retrieve the 10 latest sales for customer 42 specifically. Those two results are not equivalent.

Therefore, a derived table containing `LIMIT` forbids derived condition pushdown in ways that alter the limited row set. Similarly, conditions involving window function results or expressions with special semantics must stay at the proper stage. Never manually rewrite a query to push a condition down without proving both forms return identical results.

Additional restrictions depend on query block type, expression form, and MySQL version. If the optimizer does not push down a condition, inspect the execution plan and the documentation for your running version instead of assuming a bug.

## 8. Derived Tables, Views, and CTEs

| Construct | Merge | Materialization | Key Point |
|---|---|---|---|
| Derived table in `FROM` | Possible if structure allows | When not merged or forced to materialize | `derived_merge` controls merge attempts |
| View `ALGORITHM=MERGE` | Merges if definition permits | Avoids materialization as primary view choice | Lets optimizer combine view with outer query |
| View `ALGORITHM=TEMPTABLE` | Does not merge | Builds intermediate result | Preserves view execution boundary |
| View `ALGORITHM=UNDEFINED` | Optimizer decides | Can materialize when needed | Common default option |
| Non-recursive CTE | Can merge or materialize | Can materialize, especially when referenced multiple times or non-mergeable | Materialized CTE can be reused within the same statement |
| Recursive CTE | Not handled like a normal merged derived table | Uses materialization mechanics for recursive results | Review recursive CTE rules separately |

Example creating a view:

```sql
CREATE ALGORITHM = MERGE VIEW paid_sales AS
SELECT sale_id, customer_id, amount
FROM sales
WHERE status = 'PAID';

SELECT sale_id, amount
FROM paid_sales
WHERE customer_id = 42;
```

With `ALGORITHM=MERGE`, the view can be merged into the outer query so `customer_id = 42` participates in optimization against `sales`. With `ALGORITHM=TEMPTABLE`, the view is materialized and the outer predicate may be considered for derived condition pushdown if eligibility rules are met.

A CTE can be referenced multiple times:

```sql
WITH customer_sales AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT a.customer_id,
       a.total_amount AS current_total,
       benchmark.total_amount AS benchmark_total
FROM customer_sales AS a
JOIN customer_sales AS benchmark
  ON benchmark.customer_id = 42
WHERE a.total_amount > benchmark.total_amount;
```

If the CTE is materialized, MySQL can compute the result once and reuse it across references in the statement. Here, the CTE supplies both the set of per-customer totals and customer 42's total as a benchmark. The optimizer may add internal indexes to support different access patterns. This avoids recomputing the entire aggregation, though it still incurs the cost of creating and storing intermediate results.

## 9. Controlling the Optimizer for Testing

Two `optimizer_switch` flags are directly involved:

| Flag | Role |
|---|---|
| `derived_merge` | Enables/disables attempts to merge derived tables and mergeable views |
| `derived_condition_pushdown` | Enables/disables pushing conditions from an outer query into a materialized derived table |

Check current values:

```sql
SELECT @@SESSION.optimizer_switch;
```

You can save the session configuration, turn off both mechanisms to compare plans, and then restore:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch =
    'derived_merge=off,derived_condition_pushdown=off';

EXPLAIN FORMAT=TREE
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

These commands change only the current session's settings. In applications using connection pools, never leave modified session settings behind after testing; always restore the saved value before returning the connection to the pool. Even if a statement fails mid-test, still run the restore step.

You can use optimizer hints `MERGE()` or `NO_MERGE()` targeting a derived table alias to test a specific query:

```sql
SELECT /*+ NO_MERGE(d) */
       d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

Hints controlling derived condition pushdown also exist in supported versions, though version and syntax must be verified. Hints are diagnostic tools or solutions for clearly measured cases; avoid scattering them broadly just to lock the optimizer into a fixed plan.

## 10. Inspecting with EXPLAIN and Optimizer Trace

### EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

In the tree plan, look for nodes indicating materialization, temporary table scans, aggregation, and filters. Node names and formatting may vary across versions. If a derived table is merged, the plan usually references the base table directly without a materialize node for that derived table. If materialized, the plan may show a `Materialize` node or `<derivedN>` source. If a predicate was pushed down, you can see it inside the inner query block instead of only at an outer node. `Using temporary` in tabular format does not by itself prove a derived table was materialized; temporary tables are also used for other operations like certain groupings or sorts.

### EXPLAIN ANALYZE

Starting in MySQL 8.0.18, `EXPLAIN ANALYZE` executes the `SELECT` and displays actual metrics such as time, rows, and loops:

```sql
EXPLAIN ANALYZE
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

This command actually runs the query. Consider system load and data scope before running in production; never run `EXPLAIN ANALYZE` carelessly on statements with write side effects.

### Optimizer Trace

When you need to understand why the optimizer chose merge or materialization, enable optimizer trace in the session:

```sql
SET optimizer_trace = 'enabled=on';

SELECT d.sale_id, d.customer_id
FROM (
    SELECT sale_id, customer_id
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
```

The trace contains details of steps the optimizer evaluated. The JSON structure is verbose and varies by version; search for sections related to derived tables, merging, materialization, and condition pushdown. Turn trace off when finished to avoid collecting unnecessary data on subsequent statements.

## 11. How Does Derived Condition Pushdown Differ from ICP?

Both concepts involve early filtering, yet they operate at different layers:

| Mechanism | Execution Layer | Goal |
|---|---|---|
| Derived condition pushdown | Between outer query block and inner derived query block | Reduce rows before materializing a derived table |
| Index Condition Pushdown (ICP) | Coordination between MySQL server and storage engine during secondary index scans | Filter index entries before reading full rows from the clustered index |
| Partition pruning | Partition selection stage | Skip partitions that cannot contain matching rows |

A single query can benefit from multiple mechanisms simultaneously. For example, derived condition pushdown moves `customer_id = 42` into the inner query; the inner query can then use index `(status, customer_id)` to locate rows. ICP is a separate optimization that can filter eligible conditions while scanning the index.

## 12. Workflow for Analyzing Queries with Derived Tables

When a multi-layered query runs slowly, check in order:

1. Identify which query block forms the derived table, view, or CTE; list inner and outer conditions.
2. Check whether the derived table contains merge-blocking constructs such as aggregates, `GROUP BY`, `DISTINCT`, `LIMIT`, `UNION`, or window functions.
3. If mergeable, inspect `EXPLAIN` to confirm whether the optimizer merged it and which index it chose.
4. If it must materialize, check which outer predicates can be pushed down and how many intermediate rows remain.
5. With `GROUP BY`, classify conditions belonging to grouping columns (`WHERE`) versus aggregate conditions (`HAVING`).
6. Check indexes on base tables and any automatic indexes on temporary tables.
7. Run `EXPLAIN ANALYZE` in a suitable environment to compare estimated rows against actual rows.
8. Test toggling optimizer switches or using hints only in a controlled session; restore settings right after testing.

Materialization is not always slow, nor is merging always better. If an intermediate result is small, reused multiple times, or benefits from an automatic internal index, materialization can be cheaper than expanding and recomputing query blocks. Final decisions must rest on data and measurements.

## 13. Practice Exercises

Assume table `sales(sale_id, customer_id, status, amount, created_at)` and index `(status, customer_id)`.

1. Write a derived table selecting only `PAID` sales, then filter `customer_id = 42`. Run `EXPLAIN` and determine whether the query block was merged.
2. Add `GROUP BY customer_id` and `SUM(amount)` to the derived table. Observe materialization in the execution plan.
3. Add outer predicates `customer_id = 42` and `total_amount > 1000`. Identify which predicate can move into `WHERE` and which must go into `HAVING`.
4. Create a derived table containing `UNION ALL` from `sales` and `sales_archive`. Observe whether the customer predicate is pushed into both branches.
5. Add `ORDER BY created_at DESC LIMIT 10` to the derived table. Explain why the customer predicate cannot be pushed down before `LIMIT` while preserving identical results.
6. Compare plans with `derived_merge` and `derived_condition_pushdown` turned off in a test session. Restore `optimizer_switch` afterward.
7. Use `EXPLAIN ANALYZE` to compare intermediate row counts and execution times across query formulations.

## Takeaways

- Merging folds a derived query block into the outer query, giving the optimizer more opportunities for index selection and join optimization.
- Materialization builds an internal temporary table; it can be deferred and supported by automatic indexes.
- Derived condition pushdown shrinks intermediate data by moving safe outer conditions into the inner query.
- With `GROUP BY`, grouping-column conditions can move into `WHERE`, whereas aggregate conditions must move into `HAVING`.
- `LIMIT` and semantic boundaries can block merging or pushdown to preserve exact results.
- Use `EXPLAIN`, `EXPLAIN ANALYZE`, and optimizer trace to inspect real plans; always restore session configuration after experiments.
