# The cte_max_recursion_depth Limit and Cost Control

Recursive CTEs help MySQL process data with repeating relationships such as department trees, parent-child categories, dependency graphs, general graphs, and date series. However, a recursive query can go too deep, loop infinitely due to cycles, or generate rapidly growing row counts when each node has many children. MySQL provides the `cte_max_recursion_depth` variable to cap the number of recursion iterations, but limiting depth does not mean limiting total row count or total query cost.

In the `DATABASE_MYSQL` module, you need to combine server limits with explicit termination conditions inside the CTE, cycle control, row limits where supported by the version, timeouts, and execution plan checks. The goal is to make queries clearly bounded, predictable, and verifiable as data grows.

## 1. Structure of a Recursive CTE

A recursive CTE has two parts:

- **Anchor member:** the starting query, producing the initial row or rows.
- **Recursive member:** the query referencing the CTE itself to produce the next layer of data.

The two parts are combined using `UNION ALL` or `UNION DISTINCT`. MySQL repeats the recursive member over the newly generated rows until an iteration produces no more rows or hits a limit.

Example generating numbers from 1 to 5:

```sql
WITH RECURSIVE number_series (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM number_series
    WHERE n < 5
)
SELECT n
FROM number_series
ORDER BY n;
```

The anchor produces 1. Each iteration of the recursive member generates the next number; when `n = 5`, the condition `n < 5` is no longer true and the query stops. The result has five rows.

A recursive query needs an intentionally designed termination condition. If the recursive member keeps generating new rows with no stopping condition, the query only stops when it hits the server's recursion limit or another resource limit.

## 2. Distinguishing Depth from Row Count

Depth is the number of levels or iterations the query traverses. Row count is the total number of results generated across all levels. These two quantities are different.

For a linear chain, each iteration produces only one row:

```text
1 -> 2 -> 3 -> 4 -> 5
```

A depth of 5 generates only around 5 rows. However, for a tree with a high branching factor:

```text
             Root
       /      |      \
      A       B       C
    / | \   / | \   / | \
   ...     ...     ...
```

each level can generate many rows. If each node has an average of `b` child nodes and traverses `d` levels deep, the approximate row count can be:

\[
N = 1 + b + b^2 + \dots + b^d
\]

For example, with `b = 20` and `d = 4`, the theoretical row count is already 168,421. The query goes only four levels deep yet can produce a huge volume of data.

Therefore, `cte_max_recursion_depth` only limits depth/iterations. It does not place a direct ceiling on the total rows generated at each iteration. Controlling cost requires adding business bounds and row limits.

## 3. What Is `cte_max_recursion_depth`?

`cte_max_recursion_depth` is a MySQL system variable used to cap the number of recursion iterations of a recursive CTE. In MySQL 8.0, the default value is `1000`. If a query exceeds the limit, MySQL aborts the query and returns an error instead of recursing without bound.

Check the value:

```sql
SELECT
    @@GLOBAL.cte_max_recursion_depth AS global_limit,
    @@SESSION.cte_max_recursion_depth AS session_limit;

SHOW VARIABLES LIKE 'cte_max_recursion_depth';
```

The variable has both GLOBAL and SESSION scopes and can be changed dynamically. Changing SESSION affects only the current connection; changing GLOBAL sets the default for new sessions and does not automatically modify already-open sessions.

### Setting the Limit for the Current Session

If a legitimate task needs to go deeper than the default, you can raise the limit on the dedicated connection for that task:

```sql
SET SESSION cte_max_recursion_depth = 2000;

SELECT @@SESSION.cte_max_recursion_depth;
```

Increase it only after verifying the data, termination conditions, and cost. Raising it from 1,000 to 100,000 will not fix an invalid cycle or a query with excessive fan-out; it only lets the query keep running longer before hitting the limit.

### Setting the GLOBAL Limit

An account with appropriate administrative privileges can set the global value:

```sql
SET GLOBAL cte_max_recursion_depth = 1500;
```

This value applies as the default for sessions opened afterward. Verify on a new connection and check running sessions separately. For production, manage the value via version-controlled configuration processes and assess impact before making server-wide changes.

### Restoring the Session Value

In test scripts, save the old value and restore it after running:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;

SET SESSION cte_max_recursion_depth = 2000;

-- Run recursive CTE here.

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

When using a connection pool, do not let a request raise the limit and return the connection to the pool without resetting it. The session variable may remain in effect for the next request if the pool does not reset that state.

## 4. Understanding the Limit and Recursion Depth Errors Correctly

When a recursive CTE exceeds `cte_max_recursion_depth`, MySQL aborts the statement and reports a recursion depth error. This is a protection mechanism, not a message proving the data definitely contains a cycle. A query can exceed the limit because:

- Valid data legitimately has greater depth than configured.
- The termination condition is missing or wrong.
- The recursive member's join key is wrong, causing the query to traverse far more rows than expected.
- The data contains a cycle.
- The anchor starts from too broad a scope and the query traverses many levels.

When encountering this error, do not immediately raise the limit. First determine the actual maximum depth, row counts at each level, and the possibility of cycles.

To observe depth, add a `depth` column to the CTE:

```sql
WITH RECURSIVE number_series (n, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT n + 1, depth + 1
    FROM number_series
    WHERE n < 10
)
SELECT MAX(depth) AS deepest_level,
       COUNT(*) AS generated_rows
FROM number_series;
```

With this linear sequence, `depth` starts at 0 and increments by one each round. This numbering avoids confusion between starting value, row count, and iteration count. In a tree, the anchor has depth 0; direct children have depth 1.

## 5. Limiting Depth Directly Inside the Recursive Member

Do not rely solely on the system variable. Place a business-driven cap right inside the query:

```sql
WITH RECURSIVE number_series (n, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT n + 1, depth + 1
    FROM number_series
    WHERE n < 100
      AND depth < 99
)
SELECT n, depth
FROM number_series
ORDER BY depth;
```

The condition `depth < 99` ensures no next level is generated beyond depth 99. `n < 100` is the business condition of the number sequence; the two conditions serve different purposes. In real queries, keep the data-driven termination condition and add a safety limit condition.

If the anchor starts at depth 0 and the condition is `depth < 20`, the deepest child row has depth 20. Standardize how levels are counted in the application and reports so off-by-one bugs do not occur.

## 6. Controlling Hierarchies with Depth, Anchor, and Indexes

Organization tree example:

```sql
CREATE TABLE org_units (
    id BIGINT UNSIGNED NOT NULL,
    parent_id BIGINT UNSIGNED NULL,
    unit_name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    KEY idx_org_units_parent_id (parent_id)
) ENGINE=InnoDB;

INSERT INTO org_units (id, parent_id, unit_name)
VALUES
    (1, NULL, 'Head Office'),
    (2, 1, 'Engineering'),
    (3, 1, 'Operations'),
    (4, 2, 'Platform'),
    (5, 2, 'Application'),
    (6, 4, 'Database');
```

Query retrieving the tree starting from unit 1, capped at 20 levels maximum:

```sql
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree
ORDER BY depth, parent_id, id;
```

Control points:

- The anchor narrows directly to the root using `WHERE id = 1`.
- The recursive member finds only children of current nodes.
- `idx_org_units_parent_id` assists looking up child rows by `parent_id`.
- `tree.depth < 20` caps business depth.
- The query selects only required columns, avoiding carrying unused payloads through every iteration.

If you drop the root filter and start from the whole table, the number of expanded branches can be much larger. The broader the anchor, the higher the initial cost.

## 7. Detecting and Preventing Cycles in Trees/Graphs

A valid tree has no cycles. However, relational data can become corrupted, for example:

```text
1 -> 2 -> 4 -> 1
```

If the recursive CTE uses `UNION ALL` and only joins on parent/child, the query can loop until hitting `cte_max_recursion_depth`. A depth condition only limits the damage; it neither explains nor fixes cyclic data.

### Tracking Paths with a Path Column

For integer IDs, you can store the path as a delimited string:

```sql
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth, path) AS (
    SELECT
        id,
        parent_id,
        unit_name,
        0,
        CAST(CONCAT('/', id, '/') AS CHAR(2048))
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT
        child.id,
        child.parent_id,
        child.unit_name,
        tree.depth + 1,
        CONCAT(tree.path, child.id, '/')
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
      AND LOCATE(CONCAT('/', child.id, '/'), tree.path) = 0
)
SELECT id, parent_id, unit_name, depth, path
FROM org_tree
ORDER BY path;
```

`LOCATE()` checks whether the child ID has already appeared in the current path. The `/` delimiter prevents confusing ID `12` with ID `112`. The anchor CASTs `path` to `CHAR(2048)` because recursive CTE column types and lengths are determined from the anchor; enough length must be allocated for the longest expected path.

This pattern assumes IDs are numbers or strings that do not contain `/`. If IDs can contain the delimiter character, encode/escape them before concatenating or use a different representation.

### Detecting Cycles and Distinguishing Paths from Nodes

The path above prevents a node from repeating along the same path. However, if the data is a DAG and the same node can be reached through two different branches, that node can still appear multiple times along two valid paths. This is different from a cycle.

If the goal is solely to find the set of reachable nodes, without needing depth or path, you can use `UNION DISTINCT` and select only the ID:

```sql
CREATE TABLE graph_edges (
    from_node_id BIGINT UNSIGNED NOT NULL,
    to_node_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (from_node_id, to_node_id)
) ENGINE=InnoDB;

INSERT INTO graph_edges (from_node_id, to_node_id)
VALUES (1, 2), (2, 3), (3, 1), (2, 4);
```

The fixture has a cycle `1 -> 2 -> 3 -> 1` and a branch to node 4. The following query finds the set of nodes reachable from node 1:

```sql
WITH RECURSIVE reachable (node_id) AS (
    SELECT CAST(1 AS UNSIGNED)

    UNION DISTINCT

    SELECT edge.to_node_id
    FROM graph_edges AS edge
    JOIN reachable AS current_node
      ON edge.from_node_id = current_node.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

`UNION DISTINCT` removes duplicate rows across the entire CTE column list. Because the CTE contains only `node_id`, each node is added to the set only once, allowing the query to terminate on a finite graph even with cycles. If you add `depth` or `path`, the same node at different depths/paths becomes a different row and is no longer deduplicated solely by node ID.

Do not use `UNION DISTINCT` as a blanket solution for all trees. Deduplication incurs storage and row-comparison costs, and can discard path information if a report needs to distinguish multiple valid paths.

## 8. Limiting Row Count: Depth Is Not Enough

A CTE might traverse only three levels yet generate tens of thousands of children per level. To protect resources, think separately about:

- Number of rows generated per iteration.
- Total number of rows in the CTE.
- Byte size of columns carried through recursion.
- Cost of the JOIN finding next nodes.
- Cost of deduplicating, sorting, and materializing results.

### LIMIT in the Recursive Member on MySQL 8.0.19+

Starting in MySQL 8.0.19, the recursive member can contain `LIMIT` to cap the number of rows the recursive CTE produces:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;
SET SESSION cte_max_recursion_depth = 20000;

WITH RECURSIVE number_series (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM number_series
    LIMIT 10000
)
SELECT n
FROM number_series;

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

In the example, recursion depth is set higher than the row cap so that `LIMIT` is the safeguard being demonstrated; the script restores the old value afterward. This caps generated rows, which is helpful for protecting against non-terminating queries. Check the MySQL version before using it; versions older than 8.0.19 do not support `LIMIT` in the recursive member.

A row limit does not replace a business termination condition. For instance, a number series should stop via `n < 100`; `LIMIT` is only a secondary safeguard. If LIMIT is hit, the output may be truncated and incomplete. The application must know when a limit may have triggered so it does not treat partial results as complete data.

### Why LIMIT in the Outer Query Is Not Always a Safe Fence

Example:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;
SET SESSION cte_max_recursion_depth = 20000;

WITH RECURSIVE number_series (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM number_series
    WHERE n < 10000
)
SELECT n
FROM number_series
ORDER BY n DESC
LIMIT 100;

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

In this example, `ORDER BY n DESC` needs to sort the results before picking the last 100 rows, so the server must generate and process a set much larger than 100 rows. Do not rely on an outer LIMIT to ensure the recursive member only generates 100 rows. When `ORDER BY`, aggregates, joins, or execution strategies requiring materialization are present, the server may have to generate many or all rows before applying LIMIT. Use limits inside the recursive member (if supported by your version), explicit termination conditions, and timeouts to protect the query.

## 9. Limiting Execution Time

`cte_max_recursion_depth` and row limits do not directly control runtime. A query with shallow depth can still be slow if each JOIN iteration scans a large table or processes many columns.

MySQL supports `max_execution_time` for read-only SELECT statements, measured in milliseconds. It can be set at the session level:

```sql
SET SESSION max_execution_time = 3000;
```

Or via an optimizer hint for a single SELECT:

```sql
WITH RECURSIVE number_series (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM number_series
    WHERE n < 1000000
)
SELECT /*+ MAX_EXECUTION_TIME(3000) */ n
FROM number_series;
```

The hint tells the server to abort the SELECT statement if it exceeds the allowed duration. `3000` is 3,000 milliseconds. A timeout is a resource protection layer, not a fix for a broken query. When a timeout occurs, log the query, duration, parameters, row counts, and execution plan for investigation.

`max_execution_time` defaults to 0, meaning no limit is enforced via this variable. Scope and applicability should be verified for your version; it is not a universal timeout across all statement types.

## 10. Controlling Cost by Narrowing Data

An efficient recursive CTE typically starts from a small anchor set and carries only required columns across iterations:

1. Select a specific root or a bounded set of roots.
2. Filter tenant, status, or data range right in the anchor when semantically valid.
3. Place conditions on the child table in the recursive member to avoid expanding unnecessary branches.
4. Select ID, parent ID, depth, and truly needed report columns; avoid `SELECT *`.
5. Create indexes on columns used to find subsequent rows.
6. Cap depth and row counts according to business requirements.
7. Sort only in the outermost query if display ordering is required.

Example traversing only active units:

```sql
WITH RECURSIVE active_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1
      AND is_active = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           parent.depth + 1
    FROM org_units AS child
    JOIN active_tree AS parent
      ON child.parent_id = parent.id
    WHERE child.is_active = 1
      AND parent.depth < 15
)
SELECT id, parent_id, unit_name, depth
FROM active_tree;
```

If queries routinely filter by `is_active` and look up children by `parent_id`, evaluate a composite index `(parent_id, is_active)` instead of mechanically adding separate indexes. Choose indexes based on actual predicates and `EXPLAIN`.

## 11. Indexes for the Recursive Member

In an adjacency list model, the recursive member typically has the condition:

```sql
ON child.parent_id = parent.id
```

An index on `parent_id` lets MySQL locate child rows instead of scanning the entire table on every iteration. In multi-tenant schemas with a `tenant_id` column, if the join must also isolate by tenant:

```sql
ON child.tenant_id = parent.tenant_id
AND child.parent_id = parent.id
```

a composite index can be:

```sql
CREATE INDEX idx_org_tenant_parent
ON org_units (tenant_id, parent_id);
```

Index column order should match lookup predicates and other queries. For multi-tenant data, filter tenant right in the anchor and keep the tenant condition in the recursive join to prevent cross-tenant joins.

Do not check only whether the anchor uses a primary key; the expensive work is usually repeated in the recursive member. Inspect the access path for the child table as well as estimated rows per iteration.

## 12. Using EXPLAIN and EXPLAIN ANALYZE

`EXPLAIN` shows the plan the optimizer expects to use. For a recursive CTE, observe the recursive union/iteration section, the tables accessed inside the recursive member, chosen indexes, and estimated row counts.

```sql
EXPLAIN
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree;
```

On MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual metrics from the iterators:

```sql
EXPLAIN ANALYZE
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree;
```

`EXPLAIN ANALYZE` runs the actual query, so it can consume just as much CPU, I/O, and memory as the original query. Use it on staging or bounded datasets when the cost is not yet known.

Warning signs to watch for:

- Repeated table scans on a large table inside the recursive member.
- Actual rows per iteration far higher than predicted.
- More iterations than expected.
- Large temporary tables or materializations.
- Runtime growing sharply with depth or number of roots.
- Large discrepancy between estimated rows and actual rows.

## 13. Materialization and Temporary Storage

MySQL recursive CTEs are materialized to retain results across iterations. When results grow large, the server may need temporary memory and may spill to temporary disk storage depending on size and configuration. This makes column selection and row limits especially important.

Do not include large BLOB/TEXT columns, JSON payloads, or long descriptions in the CTE if the recursive member only needs IDs to find children. You can carry only keys and depth inside the CTE, then JOIN back to the base table in the final query to fetch display fields.

Example recursing only over IDs:

```sql
WITH RECURSIVE descendants (id, depth) AS (
    SELECT id, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id, parent.depth + 1
    FROM org_units AS child
    JOIN descendants AS parent
      ON child.parent_id = parent.id
    WHERE parent.depth < 20
)
SELECT unit.id,
       unit.parent_id,
       unit.unit_name,
       descendants.depth
FROM descendants
JOIN org_units AS unit
  ON unit.id = descendants.id;
```

The CTE holds only ID and depth; unit names are fetched in the final step. For large datasets, shrinking materialized row size can significantly reduce cost.

## 14. Version Limits and Related Syntax

Key version milestones to remember:

| Feature | MySQL version |
|---|---|
| Recursive CTE | MySQL 8.0.1 and later. |
| `cte_max_recursion_depth` | Present in MySQL 8.0; default 1000. |
| `EXPLAIN ANALYZE` | MySQL 8.0.18 and later. |
| `LIMIT` in recursive member | MySQL 8.0.19 and later. |

Before deploying a query, check the version:

```sql
SELECT VERSION();
```

If the system runs MySQL 5.7 or older, recursive CTEs are not supported. You must use a stored procedure with loops, temporary tables, or process the tree in the application. If deploying across mixed 8.0 versions, avoid `LIMIT` in the recursive member or newer features while any node remains un-upgraded.

## 15. Common Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Raising `cte_max_recursion_depth` immediately on error | Broken or cyclic queries run longer | Inspect termination condition, cycles, and per-level row counts first. |
| Thinking a depth limit is a row limit | Just a few levels can produce millions of rows | Add row limits and control fan-out. |
| Omitting a termination condition in the recursive member | Query runs until server limit | Design an explicit data-driven stop predicate. |
| Using only depth to handle cycles | Cycles still loop until hitting the depth limit | Use path-based cycle detection or `UNION DISTINCT` on an ID set. |
| Using `UNION DISTINCT` while still selecting depth/path | Same node at different depths/paths is not deduplicated | Understand DISTINCT applies to the full CTE row; select only ID if the goal is a node set. |
| Overly broad anchor | Expands too many trees right from the start | Pick specific root/tenant/scope. |
| Recursive member lacks an index on parent key | Repeated table scans across every iteration | Create and verify an appropriate index. |
| Using `SELECT *` in the CTE | Increases materialized data footprint | Carry only necessary columns through recursion. |
| Putting LIMIT only on the outer SELECT | Server may have to generate many rows before truncating | Use predicates, recursive LIMIT if supported, and timeouts. |
| Not resetting session variables in a connection pool | Subsequent requests inherit different limits or state | Restore session state or initialize connections cleanly. |
| Running EXPLAIN ANALYZE on unbounded queries in production | The inspection itself can consume heavy resources | Test on staging or bounded datasets. |

## 16. Cost Control Workflow Before Running in Production

Before putting a recursive CTE into a report job or API, check in order:

1. **Define the goal:** do you need all descendants, paths, reachable node set, or just one child level?
2. **Define the anchor:** which root, tenant, and status values are allowed to participate?
3. **Define depth:** is the anchor level 0 or level 1; what is the maximum business depth?
4. **Define the termination condition:** when must the recursive member stop producing new rows?
5. **Check for cycles:** is the data guaranteed to be a tree or can it be a general graph?
6. **Evaluate fan-out:** what are the average and maximum number of children per node?
7. **Set row/time budgets:** apply appropriate row caps, timeouts, and level limits.
8. **Create indexes:** index recursive join columns and filter columns.
9. **Measure the plan:** `EXPLAIN`, then `EXPLAIN ANALYZE` in a safe environment.
10. **Verify results:** row counts, maximum depth, repeated nodes, and malformed data cases.
11. **Manage sessions:** set and restore `cte_max_recursion_depth` and `max_execution_time` across connection pools.
12. **Monitor post-deployment:** runtime, row counts, timeouts, recursion depth errors, and data growth.

A query that finishes without errors is not necessarily right for business logic. If it hits a row cap and returns partial results, the application must explicitly report the truncated state rather than displaying it as complete data.

## 17. Practice Exercises

### Exercise A — Observing the Recursion Limit

1. Check `@@SESSION.cte_max_recursion_depth`.
2. Run a 10-element number sequence.
3. Run a query whose depth exceeds a small session limit you set in a test connection.
4. Record the error and the limit value.
5. Intentionally raise the limit and rerun, then restore the original value.

### Exercise B — Measuring Depth and Fan-Out

1. Create a tree with at least three levels and multiple child nodes.
2. Add `depth` to the recursive CTE.
3. Summarize row counts by depth using an outer query.
4. Increase children per node and observe how fast row count grows.
5. Explain why a depth limit alone is not enough to control total row count.

### Exercise C — Detecting Cycles

1. Create parent-child relationships containing a test cycle.
2. Run a `UNION ALL` query with a small depth cap.
3. Add a path and `LOCATE()` to prevent repeating nodes on the same path.
4. Run a reachability query selecting only IDs with `UNION DISTINCT`.
5. Compare the semantics of path traversal versus a reachable node set.

### Exercise D — Limiting Row Count and Runtime

1. On MySQL 8.0.19+, test `LIMIT` in the recursive member.
2. Compare with using LIMIT only on the outer SELECT.
3. Set `max_execution_time` or the `MAX_EXECUTION_TIME` hint.
4. Observe how the query is bounded and determine whether the result is complete.
5. Write application rules for when a row cap or timeout is triggered.

### Exercise E — Reading Plans and Optimizing

1. Run `EXPLAIN` on a tree traversal query.
2. Drop the `parent_id` index in a test schema and compare the plans.
3. Recreate the index and run `EXPLAIN ANALYZE`.
4. Compare carrying `SELECT *` versus carrying only ID/depth.
5. Propose depth, row, and time budgets based on measured metrics.

You have completed this lesson when you can explain the `cte_max_recursion_depth` limit, distinguish depth from row count, prevent cycles, control fan-out, set row/time budgets, and use `EXPLAIN` to evaluate recursive CTE cost.

## 18. Principles to Remember

- A recursive CTE consists of an anchor member and a recursive member; always design an explicit termination condition.
- `cte_max_recursion_depth` defaults to 1000 in MySQL 8.0 and limits recursion iterations, not total row count.
- Changing SESSION affects only the current connection; changing GLOBAL sets the default for new sessions.
- Do not raise the recursion limit before checking depth, fan-out, termination conditions, and cycles.
- Cap business depth directly inside the recursive member.
- Use path-based cycle detection when tracking paths; use `UNION DISTINCT` on IDs when the goal is only the reachable node set.
- `UNION DISTINCT` compares the entire CTE row; adding depth/path can prevent the same node from being treated as a duplicate.
- On MySQL 8.0.19+, rows can be capped using `LIMIT` in the recursive member; results hitting the limit may be partial.
- Use `max_execution_time` or `MAX_EXECUTION_TIME` to set a time budget for SELECT.
- Narrow the anchor, filter branches, select fewer columns, and index recursive join keys.
- Recursive CTEs are materialized; large datasets and wide columns increase memory/temporary storage cost.
- Use `EXPLAIN` and `EXPLAIN ANALYZE` safely to verify row counts, iterations, and access paths.
- Reset session variables in connection pools and monitor queries after deployment.

When you combine recursion limits, termination conditions, cycle control, row/time budgets, and proper indexes, you can run recursive CTEs with clear resource bounds. This keeps tree and graph queries safer as data grows or anomalies occur.
