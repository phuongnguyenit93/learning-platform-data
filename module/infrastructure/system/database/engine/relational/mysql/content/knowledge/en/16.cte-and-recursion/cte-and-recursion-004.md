# WITH RECURSIVE: Anchor Member and Recursive Member

A recursive CTE (recursive common table expression) allows a query to reference its own intermediate result to process data with iterative structures or hierarchical relationships. Common use cases include generating number sequences, building date calendars, traversing department trees, tracing parent-child categories, finding management levels, and exploring nodes in a graph.

In MySQL, a recursive CTE is declared using `WITH RECURSIVE` and consists of two core parts: the initialization part (*anchor member*) creates the initial rows; the recursive part (*recursive member*) uses existing rows to find or generate subsequent rows. The two parts are combined using `UNION ALL` or `UNION DISTINCT`. Iteration stops when the recursive member produces no new rows or reaches the recursion limit.

This lesson belongs to the `DATABASE_MYSQL` module, where you practice table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and query tuning. The goal is to clearly understand the roles of the anchor and recursive members, design safe termination conditions, and use recursive CTEs to query hierarchical data without writing a fixed number of JOINs.

After this lesson, you will be able to:

- Identify the anchor member and recursive member in a `WITH RECURSIVE` statement.
- Explain how iterations generate results and the termination condition.
- Choose `UNION ALL` or `UNION DISTINCT` based on data semantics.
- Declare column names and control the data types of recursive results using `CAST()`.
- Generate number sequences and date sequences within a defined range.
- Traverse parent-child trees using an adjacency list.
- Track paths and prevent infinite loops when data contains cycles.
- Control `cte_max_recursion_depth` and evaluate execution plans.

## 1. Structure of WITH RECURSIVE

General syntax:

```sql
WITH RECURSIVE cte_name (column_1, column_2, ...) AS (
    -- Anchor member: create initial rows
    SELECT ...

    UNION ALL

    -- Recursive member: generate next rows from CTE results
    SELECT ...
    FROM cte_name
    JOIN ...
    WHERE stop_condition
)
SELECT ...
FROM cte_name;
```

A recursive CTE has three components:

1. **CTE name and column list:** `cte_name` is the name of the intermediate result set. The parenthesized column list is optional, but declaring it explicitly is recommended for readability and to avoid column order mistakes.
2. **Anchor member:** a query that does not reference the CTE itself. It defines the starting point, such as the number 1, a start date, or root nodes with `parent_id IS NULL`.
3. **Recursive member:** a query that references the CTE to produce the next generation of rows. It must include progression logic and an appropriate termination condition.

The anchor and recursive members must return the same number of columns in the same order. The output data type of each column is determined by the non-recursive part (anchor); the recursive part must produce values compatible with those types.

## 2. How the Recursion Process Works

You can visualize a recursive CTE in rounds:

1. MySQL runs the anchor member to produce the initial set of rows.
2. The recursive member runs against the current round's rows to produce the next set of rows.
3. The new rows are added to the CTE result.
4. MySQL continues iterating with the new set of rows.
5. When the recursive member produces no more rows, the process stops.

Conceptual diagram:

```text
              Anchor member
                    |
                    v
              Initial rows
                    |
                    v
             Recursive member
                    |
                    v
           Next-generation rows
                    |
                    v
       More new rows to expand?
               /          \
             Yes           No
             |              |
             +--- repeat    v
                           End
```

This is a logical model for understanding the output. The optimizer and how MySQL manages intermediate sets are implementation details; you should not assume the order in which rows are generated is the final returned row order.

### 2.1. The Anchor Member Is the Starting Point

The anchor defines the query's initial rows. It must not reference the CTE being defined. Depending on the problem, the anchor can be:

- A fixed value such as `SELECT 1`.
- A start date such as `SELECT CAST('2026-11-19' AS DATE)`.
- One or more root nodes in a tree table.
- A specific row selected via a filter condition.

If the anchor returns no rows, the CTE has no data to expand and the final result is also empty.

### 2.2. The Recursive Member Expands the Result

The recursive member references the CTE name in `FROM`, then combines current rows with source data to find the next rows. For a department tree, a current row is a department; the recursive member finds departments whose `parent_id` equals the ID of the current department.

The recursive member needs a condition limiting the expansion domain. If the condition never stops and the data can cycle, the query may run up to the `cte_max_recursion_depth` limit and raise an error.

### 2.3. The Termination Condition Is Part of the Design

A safe query must answer: "When should no more rows be generated?"

Examples:

- Number sequence: stop when `n` reaches the maximum value.
- Date sequence: stop when the current date reaches the end date.
- Tree: stop when there are no more child nodes.
- Graph traversal: stop when there are no new nodes and avoid revisiting a node already in the path.

Do not rely solely on the server's recursion limit as a substitute for a business termination condition.

## 3. First Example: Generating a Number Sequence

Generate numbers from 1 to 10:

```sql
WITH RECURSIVE numbers (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
```

Result:

| n |
| ---: |
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |
| 6 |
| 7 |
| 8 |
| 9 |
| 10 |

Analysis:

- The anchor `SELECT 1` creates the first row with `n = 1`.
- The recursive member reads the current row `n` and generates `n + 1`.
- The condition `WHERE n < 10` only allows generating the next row when the current number is less than 10.
- When `n = 10`, the recursive member returns no more rows, so the query terminates.
- `ORDER BY n` in the outermost query guarantees result ordering.

If you omit `WHERE n < 10`, the query has no data-driven termination condition and will continue until it hits the recursion limit or another resource limit.

### 3.1. Changing Start and End Values

You can use application parameters or session variables to set bounds. Example with session variables:

```sql
SET @start_value = 5;
SET @end_value = 12;

WITH RECURSIVE numbers (n) AS (
    SELECT @start_value

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < @end_value
)
SELECT n
FROM numbers
ORDER BY n;
```

When writing in an application, pass values via `PreparedStatement` parameters using the appropriate syntax; never concatenate user input directly into SQL. Session variables here are only for illustrating how to vary inputs in a MySQL client.

### 3.2. Descending Sequences

The anchor and termination condition can produce a descending sequence:

```sql
WITH RECURSIVE countdown (n) AS (
    SELECT 5

    UNION ALL

    SELECT n - 1
    FROM countdown
    WHERE n > 1
)
SELECT n
FROM countdown
ORDER BY n DESC;
```

The result is 5, 4, 3, 2, 1. Make sure the transformation progresses toward the termination condition; if you mistakenly write `n < 1`, the sequence may not terminate as expected.

## 4. Generating Date Sequences with a Recursive CTE

An application often needs to generate consecutive dates for reporting, including days with no transactions. A recursive CTE can generate a date series without requiring a separate calendar table.

```sql
WITH RECURSIVE calendar_days (calendar_date) AS (
    SELECT CAST('2026-11-19' AS DATE)

    UNION ALL

    SELECT calendar_date + INTERVAL 1 DAY
    FROM calendar_days
    WHERE calendar_date < CAST('2026-11-25' AS DATE)
)
SELECT calendar_date
FROM calendar_days
ORDER BY calendar_date;
```

The result contains seven days from 2026-11-19 to 2026-11-25. The anchor creates the first date; the recursive member adds one day; the termination condition compares against the end date.

### 4.1. Combining the Calendar with Transaction Data

Suppose the `daily_sales` table holds daily totals. You can use the calendar as the preserved side to show days without transactions:

```sql
WITH RECURSIVE calendar_days (calendar_date) AS (
    SELECT CAST('2026-11-19' AS DATE)

    UNION ALL

    SELECT calendar_date + INTERVAL 1 DAY
    FROM calendar_days
    WHERE calendar_date < CAST('2026-11-25' AS DATE)
)
SELECT
    c.calendar_date,
    COALESCE(SUM(s.amount), 0.00) AS daily_total
FROM calendar_days AS c
LEFT JOIN daily_sales AS s
    ON s.sale_date = c.calendar_date
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

`LEFT JOIN` preserves all days in the calendar. Days with no transactions have `SUM(s.amount) = NULL`, which `COALESCE()` converts to 0 for display. If business logic needs to distinguish "no transactions" from "transactions summing to 0", also return `COUNT(s.sale_id)`.

For long-range reports, many concurrent users, or frequent calendar queries, a physical calendar table may be more suitable because it avoids regenerating the date series on every query and can include extra attributes such as week, quarter, and holidays. A CTE is a convenient choice for small ranges and flexible queries.

## 5. Recursive CTEs for Traversing Parent-Child Trees

A common way to store a tree is an adjacency list: each row stores its own ID and its parent node's ID. The root node has `parent_id IS NULL`.

Create a sample table:

```sql
DROP TEMPORARY TABLE IF EXISTS org_nodes;

CREATE TEMPORARY TABLE org_nodes (
    node_id INT UNSIGNED NOT NULL,
    parent_id INT UNSIGNED NULL,
    node_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (node_id),
    KEY idx_org_nodes_parent (parent_id)
) ENGINE = InnoDB;

INSERT INTO org_nodes (node_id, parent_id, node_name) VALUES
(1, NULL, 'CEO'),
(2, 1,    'Engineering'),
(3, 1,    'Product'),
(4, 2,    'Backend'),
(5, 2,    'Data'),
(6, 3,    'Design'),
(7, 5,    'Database');
```

Tree structure:

```text
1 CEO
├── 2 Engineering
│   ├── 4 Backend
│   └── 5 Data
│       └── 7 Database
└── 3 Product
    └── 6 Design
```

### 5.1. Anchor as Root Node, Recursive Member as Child Nodes

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth
) AS (
    -- Anchor: start from the root node
    SELECT
        node_id,
        parent_id,
        node_name,
        0 AS depth
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    -- Recursive member: find nodes whose parent is a current node
    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree
ORDER BY depth, node_id;
```

The result has seven nodes. `depth = 0` is CEO; direct children have depth 1; Backend, Data, and Design have depth 2; Database has depth 3. The condition `parent.depth < 20` is a depth safeguard in this example; valid tree data also terminates naturally when no child nodes remain.

The key part of the recursive join:

```sql
ON child.parent_id = parent.node_id
```

`parent` is the CTE result set from the current round; `child` is the source table containing child nodes. Each round finds rows whose `parent_id` points to the IDs just expanded.

### 5.2. Traversing a Subtree Instead of the Entire Tree

If you only want the subtree starting at node 2, the anchor selects that node:

```sql
WITH RECURSIVE subtree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN subtree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM subtree
ORDER BY depth, node_id;
```

The result includes Engineering, Backend, Data, and Database. The anchor can be any node, not necessarily the root; the recursive member still expands its descendants.

### 5.3. Path from Root to Each Node

To display the path, add a path column. Pay attention to the anchor's data type because MySQL infers CTE column types from the non-recursive part. If the anchor produces only a short string, appending in the recursive part can exceed the inferred length.

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth,
    id_path
) AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0,
        CAST(node_id AS CHAR(1000))
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1,
        CONCAT(parent.id_path, ',', child.node_id)
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, node_name, depth, id_path
FROM org_tree
ORDER BY depth, node_id;
```

The `id_path` of the Database node is `1,2,5,7`. `CAST(... AS CHAR(1000))` allocates a string length wide enough for the recursive part in the example. Choose the limit based on actual depth and ID length; do not treat 1000 as a universal value for every system.

## 6. Controlling Cycles in Tree/Graph Data

A true tree has no cycles. However, data can become corrupted due to imports, migrations, or bad updates. For example, node 2 might point to node 5 while node 5 points back to node 2. In that case, the recursive member could keep revisiting already-seen rows.

### 6.1. UNION DISTINCT Does Not Always Block Cycles

`UNION DISTINCT` removes duplicate rows across the entire CTE column list. But if the CTE includes `depth` or `path`, the same `node_id` visited at a different depth or along a different path is a different row. Therefore, changing `UNION ALL` to `UNION DISTINCT` is not a general cycle-detection solution.

Illustration of the idea: row `(node_id = 2, depth = 1)` differs from row `(node_id = 2, depth = 3)`, so DISTINCT does not treat them as duplicates.

### 6.2. Tracking Visited IDs

For integer IDs that do not contain commas, you can keep the path as a comma-separated string and use `FIND_IN_SET()` to avoid revisiting an ID already in the same path:

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth,
    id_path
) AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0,
        CAST(node_id AS CHAR(1000))
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1,
        CONCAT(parent.id_path, ',', child.node_id)
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
      AND FIND_IN_SET(CAST(child.node_id AS CHAR), parent.id_path) = 0
)
SELECT node_id, node_name, depth, id_path
FROM org_tree
ORDER BY depth, node_id;
```

The condition `FIND_IN_SET(...) = 0` expands only to a node that has not yet appeared in the current path. This approach works for simple integer IDs; if keys are strings that might contain delimiters, you must explicitly encode/escape them or use another path structure.

A path-based cycle guard prevents looping along the same branch, though a node can appear multiple times if the graph has multiple distinct paths reaching it. If the problem requires each node to appear only once in the entire result, you need additional deduplication rules or a different query design; `UNION DISTINCT` suffices only when all generated rows are identical.

### 6.3. Depth Limits Are Still Necessary

Even with a cycle guard, you should still set a reasonable depth limit to protect the query against anomalous data or trees deeper than expected by business rules. In the example, `parent.depth < 20` allows generating children up to depth 20 and then stops expanding further.

For graphs with high branching factors, the number of paths can grow very rapidly even at modest depths. A depth limit does not replace evaluating the potential number of generated rows and query time/resource limits.

## 7. UNION ALL and UNION DISTINCT in Recursive CTEs

The anchor and recursive members are joined by a set operator:

| Operator | Behavior | When to consider |
| --- | --- | --- |
| `UNION ALL` | Keeps every generated row, including duplicates | Generating sequences, traversing trees, keeping each path, or when duplicates are valid and performance matters |
| `UNION DISTINCT` or `UNION` | Removes duplicate rows across all result columns | When the result needs to eliminate completely identical rows |

In MySQL, `UNION` without `ALL` defaults to `DISTINCT`. Write the operator explicitly so readers see the intent.

For example, with a graph that may have multiple paths to the same node, `UNION ALL` preserves each path. If you select only `node_id` and want a unique list of nodes, `UNION DISTINCT` can deduplicate nodes. But if the CTE also includes `depth` or `path`, rows for the same node can differ and still remain.

`UNION DISTINCT` may require extra deduplication work and memory. Do not use DISTINCT to hide data issues or replace a cycle guard without understanding which columns are being compared.

## 8. Data Types in Anchor and Recursive Members

This is a very important characteristic of MySQL recursive CTEs: the data types of the CTE columns are determined from the non-recursive part. Values generated by the recursive member are cast to the type inferred from the anchor.

Example prone to string-length errors:

```sql
WITH RECURSIVE paths (path_value) AS (
    SELECT 'A'

    UNION ALL

    SELECT CONCAT(path_value, 'B')
    FROM paths
    WHERE CHAR_LENGTH(path_value) < 5
)
SELECT path_value
FROM paths;
```

The anchor produces only the short string `'A'`. The recursive part appends characters, but the result column type/length was already fixed by the anchor. Depending on SQL mode and version, the query may fail when values exceed the length or exhibit unexpected conversion behavior.

Provide a wide enough type and length right in the anchor:

```sql
WITH RECURSIVE paths (path_value) AS (
    SELECT CAST('A' AS CHAR(100))

    UNION ALL

    SELECT CONCAT(path_value, 'B')
    FROM paths
    WHERE CHAR_LENGTH(path_value) < 5
)
SELECT path_value
FROM paths
ORDER BY CHAR_LENGTH(path_value);
```

The results are `A`, `AB`, `ABB`, `ABBB`, `ABBBB` in order. The anchor pre-allocates a length of 100 to hold subsequent values.

### 8.1. CAST for Numbers and Precision

For integers, the anchor must choose a type large enough for the entire generated range. For decimals, specify sufficient precision and scale to hold the results. Example:

```sql
WITH RECURSIVE amounts (n, amount) AS (
    SELECT
        1,
        CAST(0.10 AS DECIMAL(12, 2))

    UNION ALL

    SELECT n + 1, amount + 0.10
    FROM amounts
    WHERE n < 5
)
SELECT n, amount
FROM amounts
ORDER BY n;
```

Do not use floating-point types `FLOAT`/`DOUBLE` if calculations require exact decimal precision. Use `DECIMAL` and choose precision/scale according to business limits.

### 8.2. NULL Types and Collation

If the anchor returns `NULL` without an explicit type, the inferred type may not match the recursive member's values. Use `CAST(NULL AS ...)` to declare the intended type. For strings with multiple charsets/collations, ensure the `UNION` branches convert consistently and verify the resulting collation.

Example:

```sql
WITH RECURSIVE labels (label, depth) AS (
    SELECT CAST(NULL AS CHAR(100)), 0

    UNION ALL

    SELECT CONCAT(COALESCE(label, ''), 'child'), depth + 1
    FROM labels
    WHERE depth < 2
)
SELECT label, depth
FROM labels;
```

This example demonstrates declaring a type for NULL; in practice, design an anchor with clear business meaning and a clear termination condition, avoiding unnecessary empty labels.

## 9. Restrictions on the Recursive Member in MySQL

The recursive member is not an arbitrary SELECT query. MySQL enforces restrictions so the recursion process can be evaluated:

- A recursive CTE must reference itself in the recursive member.
- The recursive CTE table can be referenced only once per recursive query block and must appear in `FROM`.
- Do not place a reference to the recursive CTE inside a subquery of the recursive member.
- Do not place the recursive CTE table on the right side of a `LEFT JOIN` in the recursive member.
- The recursive member must not contain aggregate functions, window functions, `GROUP BY`, `ORDER BY`, or `DISTINCT`.
- The anchor and recursive member branches must return the same number of columns, in the exact same order.

If you need aggregation or sorting, perform them in the outermost query after the CTE has produced the result set. For example, traverse the tree first and then run `GROUP BY depth` in the outer SELECT.

MySQL 8.0.19 and later allows `LIMIT` in the recursive member to limit the number of generated rows in certain cases. However, do not rely on LIMIT as the sole way to express a business termination condition; prefer an explicit logical condition in the recursive member and check version compatibility.

## 10. MySQL Recursion Limits

MySQL controls depth via the system variable `cte_max_recursion_depth`. The default value is `1000`. When a query exceeds this limit, MySQL stops and returns an error instead of recursing infinitely.

Check the configuration:

```sql
SELECT @@session.cte_max_recursion_depth;
SELECT @@global.cte_max_recursion_depth;
```

You can set a separate limit for the session:

```sql
SET SESSION cte_max_recursion_depth = 2000;
```

Increase the limit only when business logic genuinely requires greater depth and you have checked generated row counts, runtime, memory, and server impact. Raising the limit does not fix cycles or wrong termination conditions; it only lets a broken query run longer before being stopped.

Several safeguards:

- Put a business termination condition in the recursive member.
- Set an explicit depth limit if the data has a tree structure.
- Track cycles or repeated paths in graph data.
- Limit input date ranges or element counts.
- Use `EXPLAIN` and test on representative data before running heavy queries.
- Do not increase `cte_max_recursion_depth` globally just to push a buggy query through.

## 11. Tree Traversal Depth and Result Ordering

A CTE produces a result set, but does not guarantee return order if the outermost query lacks `ORDER BY`. The order of anchor/recursive members or table row order is not a display-order guarantee.

Example:

```sql
WITH RECURSIVE org_tree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree
ORDER BY depth, node_id;
```

`ORDER BY depth, node_id` creates a stable level-by-level then ID ordering. This is level-order, not depth-first branch order. If a UI needs to display the tree in hierarchical pre-order, build a sort path column with zero-padded fixed-width ID components and sort by that sort path.

Idea for a sort path with integer IDs:

```sql
CONCAT(parent.sort_path, '.', LPAD(child.node_id, 10, '0'))
```

When using a sort path, the anchor must CAST to a long enough string following the same rule in section 8. Do not sort integer paths as unpadded strings if IDs have varying lengths, because lexicographical order can place `10` before `2`.

## 12. Recursive CTEs for Multi-Path Graphs

An adjacency list can represent a tree, but it can also represent a graph if a node has multiple incoming edges. Then a node can be reached via multiple different paths.

Example edge table:

```sql
CREATE TEMPORARY TABLE graph_edges (
    from_node INT NOT NULL,
    to_node INT NOT NULL,
    PRIMARY KEY (from_node, to_node),
    KEY idx_graph_edges_to (to_node)
) ENGINE = InnoDB;

INSERT INTO graph_edges (from_node, to_node) VALUES
(1, 2),
(1, 3),
(2, 4),
(3, 4),
(4, 5);
```

Node 4 can be reached from node 2 or node 3. The query preserves all paths:

```sql
WITH RECURSIVE paths (node_id, depth, node_path) AS (
    SELECT 1, 0, CAST('1' AS CHAR(1000))

    UNION ALL

    SELECT
        e.to_node,
        p.depth + 1,
        CONCAT(p.node_path, ',', e.to_node)
    FROM graph_edges AS e
    JOIN paths AS p
        ON e.from_node = p.node_id
    WHERE p.depth < 10
      AND FIND_IN_SET(CAST(e.to_node AS CHAR), p.node_path) = 0
)
SELECT node_id, depth, node_path
FROM paths
ORDER BY depth, node_path;
```

Node 4 appears twice with two different paths: `1,2,4` and `1,3,4`. This is the right result if the question is "what paths exist?". If the question is "which nodes are reachable from node 1?", you need to deduplicate by `node_id` in the outer query or design a query tailored to reachability.

Multi-path graphs can cause intermediate row counts to grow exponentially. Set depth limits, cycle guards, and evaluate cardinality before running on large datasets.

## 13. Inspecting CTEs with EXPLAIN

You can use `EXPLAIN` before a statement containing a CTE to view the query plan:

```sql
EXPLAIN
WITH RECURSIVE org_tree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree;
```

Observe:

- How MySQL accesses the source table in the anchor and recursive members.
- Whether the index on `parent_id` is used to find child nodes.
- Estimated row counts and potential iterations.
- Materialization/intermediate set cost if shown in the plan.

`EXPLAIN ANALYZE` executes the actual query. Use it only when the generated load is acceptable, especially for graphs with high branching or large depth limits.

Some optimization directions:

- Create an index on the join column from the source table to the CTE, such as `org_nodes(parent_id)`.
- Filter the anchor as specifically as possible if only one subtree is needed.
- Include only required columns in the CTE; long paths or large payloads increase intermediate row size.
- Limit depth and input volume according to business requirements.
- Avoid `UNION DISTINCT` if deduplication is unnecessary, because deduplication has overhead.
- For frequent tree queries over large trees, consider an appropriate storage model such as a closure table or materialized path instead of recomputing every time.

## 14. Common Errors

| Error | Consequence | Fix |
| --- | --- | --- |
| Anchor does not produce the right starting point | Empty CTE or wrong branch traversed | Clearly identify root/seed rows |
| Recursive member does not reference the CTE properly | Fails to expand the next generation | Join source table with the current CTE |
| Missing termination condition | Recurses until server limit or wastes resources | Add a business-driven stop predicate |
| Anchor returns too short a string type | Recursive values error out or truncate | CAST to a sufficiently wide length in the anchor |
| Numeric type range too small | Overflow or loss of precision | Choose a large enough type and CAST explicitly |
| Assuming UNION DISTINCT always stops cycles | Rows with different depth/path are still distinct | Use a cycle guard tracking visited IDs |
| Missing final ORDER BY | Result order is not guaranteed | Sort in the outermost SELECT |
| Using recursive CTE on multi-path graphs without limits | Intermediate row count explodes rapidly | Limit depth, path, and inputs |
| Raising recursion depth to mask bugs | Broken query runs longer, causing higher load | Fix the termination condition and data |
| Aggregates inside recursive member | Violates syntax restrictions | Aggregate in the outermost query |

## 15. Practice Exercises

1. Write a recursive CTE to generate a sequence from 1 to 100. Try changing the termination condition to `n <= 100` and explain why the result exceeds 100 if written in the wrong place.
2. Generate a descending sequence from 20 down to 0. Identify the anchor, recursive member, and termination condition.
3. Generate dates from the start to the end of November 2026. Combine `LEFT JOIN` with a transaction table to display days with no transactions.
4. Create an adjacency list table for an organizational chart. Traverse the entire tree from root, and also traverse only a subtree starting at a mid-tree node.
5. Add `id_path` and `depth` columns. Explain why the anchor must CAST the string to a sufficiently large length.
6. Create data containing a cycle in a separate lab table. Run the query without a cycle guard under a low recursion limit, then add `FIND_IN_SET()` to prevent revisiting a node in the same path.
7. Compare `UNION ALL` and `UNION DISTINCT` when the CTE contains only `node_id`, then add `depth` and `path`; observe how deduplication behavior changes.
8. Create a graph with two distinct paths to the same node. List all paths, then write a query returning only a unique list of reachable nodes.
9. Try a recursive member with `GROUP BY` or an aggregate in a lab environment, read the error, and rewrite it by aggregating in the outer query.
10. Run `EXPLAIN` on the tree traversal query before and after adding an index on `parent_id`. Note the plan differences and the limitations of small lab datasets.

## 16. Pre-Production Recursive CTE Checklist

- [ ] Anchor accurately selects seed rows and has appropriate data types.
- [ ] Anchor and recursive members return the same number of columns in the same order.
- [ ] Column types inferred from the anchor are wide enough for all recursion rounds.
- [ ] Recursive member references the CTE in the proper position and only once per MySQL rules.
- [ ] Termination condition is explicit and provable.
- [ ] Cycle guard is present if data can contain cycles.
- [ ] Decided whether all paths should be kept or each node is needed only once.
- [ ] `UNION ALL`/`UNION DISTINCT` is chosen by semantics, not as a workaround for bugs.
- [ ] Depth and generated row counts stay within resource limits.
- [ ] `cte_max_recursion_depth` has been checked and is not raised arbitrarily.
- [ ] Indexes on join columns of the source table have been evaluated.
- [ ] Output ordering is specified in the outermost SELECT if needed.
- [ ] Plan has been inspected with `EXPLAIN` and tested on representative data.

## 17. Completion Criteria

You have completed this lesson when you can clearly explain the anchor member and recursive member, write a recursive CTE with a termination condition, generate number/date sequences, traverse a tree from root or any node, control data types using `CAST()`, detect and prevent path cycles, distinguish `UNION ALL` from `UNION DISTINCT`, and control depth while evaluating queries with `EXPLAIN`.

## References

- [MySQL 8.4 Reference Manual — WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual — Recursive CTEs](https://dev.mysql.com/doc/refman/8.4/en/with.html#common-table-expressions-recursive)
- [MySQL 8.4 Reference Manual — Server System Variables (`cte_max_recursion_depth`)](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
