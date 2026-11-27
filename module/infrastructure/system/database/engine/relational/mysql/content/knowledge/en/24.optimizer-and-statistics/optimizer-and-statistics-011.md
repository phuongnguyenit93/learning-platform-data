# optimizer_switch, Optimizer Hints, and Query Block Scope

MySQL chooses how to execute a SQL statement based on statistics, estimated costs, and optimization rules. When investigating an unsuitable plan, a DBA can adjust optimization behavior at the session level via `optimizer_switch`, or use **optimizer hints** to deliberately influence a specific statement. For SQL statements containing subqueries, derived tables, CTEs, or multiple `UNION` branches, understanding **query blocks** is essential to know which part a hint targets.

This lesson belongs to the **Optimizer and Statistics** section of MySQL. You will read and change several switches, apply index and join-order hints, name query blocks, control merge/materialization, detect ignored hints, and compare plans using `EXPLAIN`. Every change must be verified on a representative workload before broad rollout.

## 1. Distinguishing Three Optimizer Control Mechanisms

MySQL provides several ways to influence the optimizer, differing in scope and specificity:

| Mechanism | Scope | Example | Purpose |
| --- | --- | --- | --- |
| `optimizer_switch` | GLOBAL or SESSION | `index_merge=off` | Toggle a group of optimization strategies supported in the running version. |
| Optimizer hint | A specific SQL statement or query block | `/*+ INDEX(o ix_orders_customer) */` | Guide access paths, join order, merging, or optimization strategies for the statement. |
| SQL-style index hint | A single table reference in a SQL statement | `USE INDEX (ix_orders_customer)` | Influence the set of indexes the optimizer considers for that table reference. |

`optimizer_switch` is not a list of fixed plans. Disabling a switch merely removes or alters one strategy; the optimizer can still pick another plan based on statistics and cost. Likewise, optimizer hints do not guarantee faster execution: a hint can be ignored if invalid, inapplicable, or conflicting with query structure.

When a hint and `optimizer_switch` both govern the same optimization, the statement-specific hint typically takes precedence over the switch. Even so, verify whether the hint was accepted and whether the plan changed as intended.

## 2. Reading and Changing optimizer_switch

`optimizer_switch` is a system variable with `GLOBAL` and `SESSION` scope. The `SESSION` value is used when the optimizer compiles plans for statements in that session. To view current settings:

```sql
SELECT @@GLOBAL.optimizer_switch;
SELECT @@SESSION.optimizer_switch;
```

Or:

```sql
SHOW VARIABLES LIKE 'optimizer_switch';
```

The value is a comma-separated list of `switch_name=on|off|default` pairs. The list of switches varies across MySQL versions; inspect the value on your server instead of assuming every version shares the same switches.

### Changing a Switch in a Session

Example temporarily disabling `index_merge` to compare plans:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

-- Run EXPLAIN for the query under test here.

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

When specifying only one switch, other unmentioned switches keep their current values. You can use `default` to reset a switch to the version's default:

```sql
SET SESSION optimizer_switch = 'index_merge=default';
```

Save the previous value and restore it immediately after the experiment. `SESSION` changes affect only the current connection; they do not affect other running sessions. `GLOBAL` changes affect new connections or sessions reading global defaults, which has broad impact and requires change-control procedures.

### Common Switches

Switch names and default states depend on version. The following examples represent common groups in MySQL 8.0:

| Switch | General Effect |
| --- | --- |
| `index_merge` | Allows the optimizer to consider combining multiple index accesses on the same table. |
| `index_merge_union` | Controls the Index Merge Union strategy. |
| `index_merge_intersection` | Controls the Index Merge Intersection strategy. |
| `index_merge_sort_union` | Controls the Sort-Union variant of Index Merge. |
| `mrr` | Enables Multi-Range Read in eligible cases. |
| `mrr_cost_based` | Lets the optimizer weigh cost when deciding whether to use MRR. |
| `batched_key_access` | Enables the Batched Key Access strategy under eligible conditions. |
| `derived_merge` | Allows merging derived tables or views into the outer query block when valid. |
| `semijoin` | Enables semijoin transformations for eligible subqueries. |
| `condition_fanout_filter` | Lets the optimizer use filter selectivity estimates to refine row-count propagation across joins. |
| `skip_scan` | Enables Index Skip Scan under eligible conditions. |

Do not turn off multiple switches at once and guess which switch caused a change. Modify one factor at a time, record `EXPLAIN`, runtime, and actual row counts, and then restore the configuration.

## 3. Preparing Test Data

Examples use customer and order tables. You can create dedicated lab tables in a test schema:

```sql
CREATE TABLE optimizer_lab_customers (
    customer_id BIGINT NOT NULL,
    region_code CHAR(2) NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY ix_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE optimizer_lab_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB;
```

For meaningful plan comparisons, the data should have diverse distributions: many customers across regions, and orders spanning statuses and timestamps. Tables with only a few rows rarely show clear differences between access paths.

After loading lab data, refresh statistics as needed:

```sql
ANALYZE TABLE optimizer_lab_customers, optimizer_lab_orders;
```

Do not load millions of rows or alter statistics in production just to reproduce an example. Use a clone or benchmark environment with data resembling real workloads.

## 4. Optimizer Hints: Syntax and Placement Rules

MySQL optimizer hints are written inside special `/*+ ... */` comments. For `SELECT`, hints are typically placed immediately after the `SELECT` keyword:

```sql
SELECT /*+ MAX_EXECUTION_TIME(1000) */
       order_id, total_amount
FROM optimizer_lab_orders
WHERE customer_id = 1001;
```

`MAX_EXECUTION_TIME(1000)` sets an execution timeout in milliseconds for eligible `SELECT` queries. This hint does not replace application-side timeouts and does not apply to all statement types.

An ordinary comment such as `/* note */` is not an optimizer hint. A hint must have `+` right after `/*`, appear in a MySQL-designated position, and use valid syntax. In statements with multiple query blocks, a hint applies to the block where the comment appears; it can reference another block using a query block name.

A single statement can include multiple hints inside the same comment:

```sql
SELECT /*+ INDEX(o ix_customer_created) JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.created_at
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 1001;
```

In this example, `INDEX` steers the optimizer toward the specified index for alias `o`; `JOIN_ORDER` suggests the join order of table references in the query block. The two hints govern two different aspects of the plan.

## 5. Index and Table Access Hints

Index-related hints in MySQL 8.0 include:

- `INDEX(table_alias index_name)` suggests using the specified index.
- `NO_INDEX(table_alias index_name)` excludes the specified index from consideration.
- `JOIN_INDEX`, `GROUP_INDEX`, and `ORDER_INDEX` can restrict indexes by join, group, or order purpose in supported versions.
- `INDEX_MERGE` and `NO_INDEX_MERGE` control whether Index Merge is considered for a table reference.

Example:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ INDEX(o ix_customer_created) */
       o.order_id, o.created_at
FROM optimizer_lab_orders AS o
WHERE o.customer_id = 1001
  AND o.created_at >= '2026-01-01';
```

For comparison, remove the hint and inspect the optimizer's natural plan. If the hint forces a different index that increases pages read or execution time, drop the hint. Index hints do not create new indexes or fix statistics.

### Optimizer Hints vs. USE/FORCE/IGNORE INDEX

MySQL also supports SQL-style index hints placed after a table reference:

```sql
SELECT o.order_id, o.created_at
FROM optimizer_lab_orders AS o
  FORCE INDEX FOR JOIN (ix_customer_created)
WHERE o.customer_id = 1001;
```

`USE INDEX`, `FORCE INDEX`, and `IGNORE INDEX` are SQL-style index hints; they differ from comment-style optimizer hints. You can scope their purpose with `FOR JOIN`, `FOR ORDER BY`, or `FOR GROUP BY`. Avoid mixing multiple index-control mechanisms simultaneously unless you understand how they interact, as doing so complicates reading plans and troubleshooting.

## 6. Hints for Controlling Join Order

The optimizer usually selects join order based on row estimates and costs. You can use the following hints in supported versions:

- `JOIN_ORDER(t1, t2, ...)`: suggests the join order of the listed tables.
- `JOIN_PREFIX(t1, t2, ...)`: specifies the leading prefix of the join order.
- `JOIN_SUFFIX(t1, t2, ...)`: specifies the trailing suffix of the join order.
- `JOIN_FIXED_ORDER()`: requests joining tables in the order they appear in the `FROM` clause.

Example:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.total_amount
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_code = 'HN'
  AND o.status = 'PAID';
```

`JOIN_ORDER(c, o)` tells the optimizer to process `c` before `o` in this block. The hint does not mandate a specific access method or index; the optimizer still picks how to access each table. If filtering customer region returns most of the table while order status is highly selective, forcing order can worsen the plan.

Optimal join order depends on actual data, statistics, indexes, and predicates. Run `EXPLAIN ANALYZE` on a safe `SELECT` query to compare actual rows, loops, and per-iterator timings.

## 7. What Is a Query Block?

A **query block** is a distinct `SELECT` query unit within a SQL statement. One statement can contain multiple query blocks:

- The outermost `SELECT`.
- A `SELECT` inside a subquery or `EXISTS`.
- A `SELECT` defining a derived table in `FROM`.
- A `SELECT` inside a CTE.
- Each `SELECT` branch of a `UNION`.

Example:

```sql
SELECT c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

This query has at least two query blocks: the outer block reading `optimizer_lab_customers`, and the inner block reading `optimizer_lab_orders`. A hint placed immediately after the outer `SELECT` does not automatically apply to the inner `SELECT` block.

### Naming Query Blocks with QB_NAME

The `QB_NAME(name)` hint assigns a name to the query block containing the hint. Example:

```sql
SELECT /*+ QB_NAME(customer_list) */
       c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT /*+ QB_NAME(paid_order_check) */ 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`customer_list` identifies the outer block; `paid_order_check` identifies the inner block. Block names must be used consistently and should be unique within the statement. Without explicit names, MySQL assigns default names like `select#N`, though explicit names make hints easier to read and less brittle to structural edits.

### Referencing Another Query Block with @name

When a hint in one block needs to target a table reference in another block, use `@query_block_name`. Example hinting an index for alias `o` inside the subquery:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+
          QB_NAME(customer_list)
          INDEX(@paid_order_check o ix_status_created)
       */
       c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT /*+ QB_NAME(paid_order_check) */ 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`@paid_order_check` points to the query block containing alias `o`; `ix_status_created` is the suggested index for that alias. When renaming an alias or query block name, update the hint accordingly. If the table reference does not exist in the targeted block, the hint cannot apply.

## 8. Hints for Derived Tables: MERGE and NO_MERGE

A derived table is a `SELECT` appearing in the `FROM` clause. When eligible, the optimizer can **merge** a derived table into the outer query block to broaden optimization opportunities. In other cases, the optimizer keeps the derived table as a materialized intermediate result.

Example:

```sql
SELECT c.customer_id, d.order_count
FROM optimizer_lab_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM optimizer_lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
  ON d.customer_id = c.customer_id;
```

You can use `MERGE(d)` or `NO_MERGE(d)` to guide how derived table `d` is handled:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ NO_MERGE(d) */
       c.customer_id, d.order_count
FROM optimizer_lab_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM optimizer_lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
  ON d.customer_id = c.customer_id;
```

`NO_MERGE(d)` prevents merging derived table `d` when valid; the optimizer can materialize the intermediate result. `MERGE(d)` requests merging when query structure permits. Constructs such as aggregates, `GROUP BY`, `DISTINCT`, `LIMIT`, or window functions can prohibit merging under MySQL rules; a hint cannot make an invalid transformation valid.

Materialization can pay off when an intermediate result is small and reused, though it adds temporary write/read overhead. Merging can unlock predicate pushdown and better join orders. Neither option is universally faster.

## 9. Hints for Subqueries and Other Optimizations

MySQL provides specialized hints for subquery strategies, semijoins, and derived condition pushdown. Names and support vary by version. For instance, the `SEMIJOIN`/`NO_SEMIJOIN` hints control semijoin usage for eligible subqueries; strategies can include `FIRSTMATCH`, `LOOSESCAN`, `MATERIALIZATION`, and `DUPSWEEDOUT`.

Do not apply semijoin hints purely by name. First verify in `EXPLAIN FORMAT=JSON` or `EXPLAIN FORMAT=TREE` whether the subquery was transformed into a semijoin. If the query shape is ineligible, the hint may have no effect.

Other notable hints:

| Hint | General Purpose |
| --- | --- |
| `MAX_EXECUTION_TIME(ms)` | Caps execution time for eligible `SELECT` statements. |
| `SET_VAR(var_name = value)` | Temporarily sets an eligible system variable for the duration of the statement. |
| `DERIVED_CONDITION_PUSHDOWN` / `NO_DERIVED_CONDITION_PUSHDOWN` | Controls pushing conditions down into derived tables in supported cases. |
| `RESOURCE_GROUP(name)` | Assigns a resource group for the statement on supported versions/configurations. |

Example using `SET_VAR`:

```sql
SELECT /*+ SET_VAR(sort_buffer_size = 262144) */
       order_id, created_at
FROM optimizer_lab_orders
ORDER BY created_at;
```

`SET_VAR` applies only to variables permitted with this hint; invalid variables or variables without an allowed scope are ignored and can generate warnings. Do not use hints to tweak arbitrary system variables or make persistent server configuration changes.

## 10. Detecting Ignored or Conflicting Hints

A SQL statement can succeed even when an optimizer hint is ignored. Never treat lack of a SQL error as proof that the hint took effect.

Inspect the plan:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ INDEX(o ix_customer_created) */
       o.order_id, o.created_at
FROM optimizer_lab_orders AS o
WHERE o.customer_id = 1001;

SHOW WARNINGS;
```

`SHOW WARNINGS` immediately after `EXPLAIN` can display notices about invalid, conflicting, or inapplicable hints. Exact warning text depends on version. Simultaneously, read the plan to confirm which indexes, join orders, materializations, and iterators were actually chosen.

Common causes of ignored hints:

- Misspelling hint name, index name, alias, or query block name.
- Placing the hint inside a regular comment instead of `/*+ ... */`.
- Placing the hint in a query block that does not contain the targeted table reference.
- Two conflicting hints or multiple hints governing the same choice.
- Query structure prohibiting the requested optimization.
- Hint unsupported in the running MySQL version.
- Table alias changed while the hint still references the old name.

If multiple hints overlap, do not guess results from written order. Remove redundant hints, keep a single clear goal, and verify both warnings and the execution plan.

## 11. Measuring Impact with EXPLAIN and EXPLAIN ANALYZE

Optimizer hints are useful only when they yield measurable improvements. A comparison workflow should include:

1. Run `EXPLAIN FORMAT=TREE` on the original query.
2. Record access path, join order, estimated rows, filters, and materialization.
3. Add a single hint or change a single switch in the session.
4. Re-run `EXPLAIN` and inspect `SHOW WARNINGS`.
5. For safe `SELECT` queries, run `EXPLAIN ANALYZE` to check actual rows, loops, and per-iterator timing.
6. Compare on identical data, identical cache conditions, and multiple representative runs.
7. Restore the old switch and remove the hint if gains are unstable or hurt other queries.

Example:

```sql
EXPLAIN ANALYZE
SELECT /*+ JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.total_amount
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_code = 'HN'
  AND o.status = 'PAID';
```

`EXPLAIN ANALYZE` actually executes the query to measure real metrics. Use it only on appropriate `SELECT` queries, bounded data, and test environments; never run it casually on queries with side effects or excessively heavy workloads.

Large gaps between estimated `rows` and `actual rows` may point to stale statistics or column correlations the optimizer fails to model well. A hint can mask symptoms on one query, whereas updating statistics, adding the right index, or rewriting predicates can solve the broader root cause.

## 12. Rules for Using Hints in Real Environments

- **Start from plans and metrics.** Identify the expensive iterator, estimated rows, and actual rows before adding a hint.
- **Change only one factor.** If you force indexes, force join order, and disable multiple switches simultaneously, you cannot tell what caused the outcome.
- **Limit scope.** Prefer statement-level or query-block-level optimizer hints rather than changing `GLOBAL` switches server-wide.
- **Use clear aliases and query block names.** Whenever restructuring queries, update hints and re-verify scope.
- **Check warnings.** An ignored hint can leave the plan unchanged even while the SQL runs normally.
- **Measure on representative data.** A hint that helps on a small dataset can become harmful once data distributions change.
- **Monitor after deployment.** Changes in statistics, data volume, and MySQL versions can render old hints unsuitable.
- **Document the rationale.** Record the plan issue, before/after metrics, MySQL version, and criteria for removing the hint.

Hints are tools for deliberate control, not substitutes for sound schema, index, statistics, and SQL design. The more hardcoded hints you accumulate, the higher the maintenance burden as data or MySQL versions evolve.

## 13. Self-Check Exercises

1. How does `optimizer_switch` differ from optimizer hints in scope and purpose?
2. Why does disabling `index_merge` not guarantee the optimizer will use a specific index?
3. How do you save and restore `@@SESSION.optimizer_switch` during an experiment?
4. What is a query block? How many blocks does a SQL statement with a subquery typically have?
5. What problem do `QB_NAME(name)` and `@name` syntax solve?
6. Distinguish `INDEX(alias index_name)` from `FORCE INDEX`.
7. When can `NO_MERGE` cause a derived table to materialize, and why is that not guaranteed to be faster?
8. Why must you check `SHOW WARNINGS` after `EXPLAIN` when using optimizer hints?
9. How does `EXPLAIN ANALYZE` differ from `EXPLAIN FORMAT=TREE`?
10. Design an experiment changing only one hint and record evidence demonstrating a better plan.

When controlling the optimizer, follow the chain **identify query block → place hint in proper scope → check warnings → read execution plan → measure actual rows and timing → re-evaluate on representative workload**. This workflow turns hints into evidence-backed, maintainable decisions.
