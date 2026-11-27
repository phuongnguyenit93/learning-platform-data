# Cycle Detection and Recursive Termination Conditions

A product catalog is often organized as a tree: parent categories contain child categories, and each category can have multiple levels. A service dependency system, on the other hand, models graph relationships: service A depends on B, B depends on C, and C might accidentally depend back on A. If the data contains a cycle, a recursive query can loop through the same nodes repeatedly, generate excessive rows, or hit MySQL's recursion limit.

Recursive CTEs allow traversing trees and graphs directly in SQL. For a query to terminate properly, you must design three layers of defense simultaneously: detecting nodes that have already appeared on the current path, setting a termination condition based on depth or business rules, and configuring server resource limits. The depth limit protects the system from runaway queries; it does not replace cycle detection and does not prove the data is cycle-free.

## 1. What Is a Cycle and Why Must It Be Detected?

In a directed graph, a cycle is a path that starts at a node and returns to that same node through one or more edges.

Example:

```text
A -> B -> C -> A
```

This is a three-node cycle. A self-pointing edge is also a cycle:

```text
A -> A
```

In a tree structure, each node typically has at most one parent. A valid tree must not contain cycles; if A is an ancestor of B, then B cannot become an ancestor of A.

Cycles can cause several problems:

- A recursive CTE query keeps generating rows until it hits the recursion limit.
- A breadcrumb display path may repeat category names.
- Permission hierarchies or inheritance configurations may loop endlessly.
- Dependency calculations or deployment ordering fail to find a valid order.
- A graph traversal query can cause the number of paths to grow rapidly.

Not every occurrence of a node in multiple rows is a cycle. For instance, a diamond graph `A -> B -> D` and `A -> C -> D` has two paths both reaching D, yet neither path returns to a node already visited along that same path. Cycle detection must track the current path, not merely count how many times a node appears across the entire result set.

## 2. Recursive CTE Structure in MySQL

Recursive CTEs are supported in MySQL 8.0. General structure:

```sql
WITH RECURSIVE cte_name (column_list) AS (
    -- Anchor member: produce the starting rows.
    anchor_query

    UNION ALL

    -- Recursive member: use generated rows to produce the next step.
    recursive_query
)
SELECT ...
FROM cte_name;
```

A recursive CTE has two parts:

1. **Anchor member** runs first, producing the initial set of rows. The anchor does not reference the CTE itself.
2. **Recursive member** reads the existing rows in the CTE to generate additional rows in the next round.

MySQL continues iterating the recursive member until the next round produces no new rows. This is the natural termination mechanism. However, if every round keeps generating new rows, such as walking around a cycle, the query will not stop on its own. In that case, an explicit termination condition is required.

### 2.1. Simple Recursive Example with a Termination Condition

Generate a sequence of numbers from 1 to 5:

```sql
WITH RECURSIVE numbers (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers;
```

The anchor creates `1`. Each subsequent round adds 1. When `n = 5`, the condition `n < 5` becomes false, the recursive member produces no new rows, and the query terminates.

The condition `WHERE n < 5` is the business bound of the example. In tree/graph queries, the termination condition typically includes both `depth < max_depth` and checking that the next node has not already appeared on the path.

### 2.2. Differences Between Non-Recursive and Recursive CTEs

An ordinary CTE simply creates a temporary result set for the query to reference. A recursive CTE references itself inside the recursive member. When there are multiple CTEs, place a depended-upon CTE before the CTE that uses it; a recursive CTE must be declared with `WITH RECURSIVE`.

Inside the recursive member, keep the expansion step simple: join current rows with the edge table or parent-child table, compute depth/path, and apply termination conditions. Aggregations, `GROUP BY`, or window functions should be performed in the outer query after traversal completes. MySQL imposes specific restrictions on the recursive member; do not assume every ordinary SELECT construct can be placed verbatim in the recursive part.

## 3. What Are the Layers of Termination Conditions?

A safe recursive CTE usually combines several complementary conditions:

| Defense layer | Purpose | Example |
|---|---|---|
| Business condition | Traverse only valid edges or rows | Traverse only `ACTIVE` nodes |
| Cycle guard | Stop expanding a path if the next node is already in the path | `FIND_IN_SET(next_id, path) = 0` |
| Depth guard | Limit the maximum number of steps | `depth < 100` |
| Server recursion limit | Prevent a CTE from exceeding configured iterations | `cte_max_recursion_depth` |
| Execution time limit | Limit SELECT runtime | `max_execution_time` or an appropriate optimizer hint |

The cycle guard ensures a path does not return to an already visited node. The depth guard bounds the amount of work even when the data has no cycles. The server limit and timeout serve as the final resource-protection layer.

Do not simply raise `cte_max_recursion_depth` to let a failing query keep running. If the root cause is a cycle, raising the limit only forces the server to perform more iterations before stopping.

## 4. Designing Tree and Graph Data

### 4.1. Category Tree Using parent_id

The adjacency list model stores the direct parent on each node:

```sql
CREATE TABLE categories (
    id BIGINT UNSIGNED NOT NULL,
    parent_id BIGINT UNSIGNED NULL,
    category_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_categories_parent (parent_id),
    CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_id) REFERENCES categories (id)
) ENGINE=InnoDB;
```

`parent_id IS NULL` represents a root node. The foreign key ensures the referenced parent exists, but does not prevent a cycle. For example, A having parent B, B having parent C, and C having parent A still satisfies the foreign key because all three IDs exist.

### 4.2. General Graph Using an Edge Table

For many-to-many relationships or dependencies, use an edge table:

```sql
CREATE TABLE graph_nodes (
    id BIGINT UNSIGNED NOT NULL,
    node_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE graph_edges (
    from_id BIGINT UNSIGNED NOT NULL,
    to_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (from_id, to_id),
    KEY idx_edges_to_from (to_id, from_id),
    CONSTRAINT fk_edges_from
        FOREIGN KEY (from_id) REFERENCES graph_nodes (id),
    CONSTRAINT fk_edges_to
        FOREIGN KEY (to_id) REFERENCES graph_nodes (id)
) ENGINE=InnoDB;
```

A row `(from_id, to_id)` represents a directed edge from `from_id` to `to_id`. The composite primary key prevents duplicate edges in the same direction; the index starting with `to_id` supports traversing reverse edges. Foreign keys protect the existence of both endpoints, but likewise do not forbid cycles.

## 5. Tracking Paths with String Paths

An intuitive way to detect cycles is to store the list of visited IDs in a string, such as `,10,20,30,`. Before moving to ID `20`, search for the token `,20,` in the path. If it is already present, the new edge leads back to a node on the current path and forms a cycle.

For numeric IDs, `FIND_IN_SET()` or `LOCATE()` can be used for checking. Place delimiters on both ends of the token to avoid confusing ID `12` with `112`.

### 5.1. Traversing a Tree from a Node and Blocking Cycles

Example retrieving descendants starting from category `10`:

```sql
WITH RECURSIVE category_walk (
    root_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        c.id,
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0,
        0
    FROM categories AS c
    WHERE c.id = 10

    UNION ALL

    SELECT
        w.root_id,
        child.id,
        CONCAT(w.path, child.id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', child.id, ','), w.path) > 0
    FROM category_walk AS w
    INNER JOIN categories AS child
        ON child.parent_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    root_id,
    node_id,
    path,
    depth,
    cycle_found
FROM category_walk
ORDER BY depth, node_id;
```

The anchor starts at category `10`. The recursive member finds rows whose `parent_id` equals the current node. Before continuing, the query checks whether `child.id` has already appeared in the path. If so, that row is flagged `cycle_found = 1`; the condition `w.cycle_found = 0` prevents further expansion from any row where a cycle was detected.

`depth < 100` is an additional cap. If the tree is deeper than 100 levels, the query stops at that level even without a cycle. Treat the depth guard as a scope boundary, not proof that the tree is valid.

### 5.2. Why Must Paths Include Delimiters?

If the path is merely `1,12,112`, searching for the string `12` with `LOCATE()` can mistakenly match part of ID `112`. Representing it as `,1,12,112,` and searching for `,12,` ensures an exact token match.

For integer IDs, this technique is straightforward. Do not use it directly if IDs are strings that can contain commas; in that case, the delimiter itself could appear inside an ID. You can encode tokens, pick a delimiter that cannot occur, or use a JSON array.

### 5.3. Path Column Length in Recursive CTEs

MySQL determines the column types and lengths of a recursive CTE from the anchor member. Therefore, if the anchor creates too short a `path`, recursive iterations may fail with a data-length error or fail to hold the full path as designed.

In the example, `CAST(... AS CHAR(4096))` allocates space for the path and caps depth at 100. With `BIGINT UNSIGNED` IDs of up to 20 digits, 101 IDs plus commas need roughly over 2,100 characters, fitting within 4,096. If you change the ID type or depth, you must recalculate the required length. Do not pick `CHAR(4096)` as a fixed magic number for every system.

## 6. Traversing Directed Graphs and Detecting Cycles

With the `graph_edges` table, a recursive CTE can traverse edges from a starting node. Example inspecting paths starting from node `1`:

```sql
WITH RECURSIVE graph_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        n.id,
        n.id,
        CAST(CONCAT(',', n.id, ',') AS CHAR(4096)),
        0,
        0
    FROM graph_nodes AS n
    WHERE n.id = 1

    UNION ALL

    SELECT
        w.start_id,
        e.to_id,
        CONCAT(w.path, e.to_id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', e.to_id, ','), w.path) > 0
    FROM graph_walk AS w
    INNER JOIN graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_node,
    path AS cycle_path,
    depth
FROM graph_walk
WHERE cycle_found = 1;
```

When an edge leads to a node already in the path, the query emits a row flagged as a cycle. For example, path `,1,2,3,1,` indicates that the path `1 -> 2 -> 3 -> 1` loops back to node `1`.

The query above only detects cycles reachable from starting node `1`. To inspect the entire graph, you can use every node as an anchor:

```sql
-- Replace the anchor with SELECT n.id ... FROM graph_nodes AS n
-- to start a traversal from each node.
```

Starting from every node can produce multiple duplicate outputs for the same cycle, because the same cycle can be discovered from each node on the cycle or from nodes leading into the cycle. This is expected behavior when traversing from every start node. If you need a deduplicated list of unique cycles, normalize how a cycle is represented (e.g., rotate to the smallest ID first) and deduplicate in a separate processing step.

## 7. Detecting Cycles in a parent_id Table

With an adjacency list, you can walk upward from each node to its parent. If the next parent has already appeared in the path, a cycle is detected.

```sql
WITH RECURSIVE parent_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        c.id,
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0,
        0
    FROM categories AS c

    UNION ALL

    SELECT
        w.start_id,
        c.parent_id,
        CONCAT(w.path, c.parent_id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', c.parent_id, ','), w.path) > 0
    FROM parent_walk AS w
    INNER JOIN categories AS c
        ON c.id = w.node_id
    WHERE c.parent_id IS NOT NULL
      AND w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_parent_id,
    path AS cycle_path,
    depth
FROM parent_walk
WHERE cycle_found = 1;
```

The anchor starts from every category. Each iteration fetches the parent of the current node. When the parent has already appeared in the path, the query records the looping path. Because the anchor starts from all nodes, one cycle may be reported multiple times under different `start_id` values.

If you only need to check one specific category, add `WHERE c.id = ...` in the anchor to narrow the traversal scope. If the table is large, do not start from all nodes during peak hours without first estimating path counts and cost.

## 8. Using a JSON Array to Track Paths

If IDs are not simple integers or you want to avoid delimiter issues, you can store the path as a JSON array. `JSON_ARRAY()` creates the initial path; `JSON_ARRAY_APPEND()` appends a new node; `JSON_CONTAINS()` checks whether a node has already appeared.

Example on a graph:

```sql
WITH RECURSIVE graph_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        n.id,
        n.id,
        JSON_ARRAY(n.id),
        0,
        0
    FROM graph_nodes AS n
    WHERE n.id = 1

    UNION ALL

    SELECT
        w.start_id,
        e.to_id,
        JSON_ARRAY_APPEND(w.path, '$', e.to_id),
        w.depth + 1,
        JSON_CONTAINS(w.path, JSON_ARRAY(e.to_id), '$')
    FROM graph_walk AS w
    INNER JOIN graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_node,
    path,
    depth
FROM graph_walk
WHERE cycle_found = 1;
```

`JSON_CONTAINS(path, JSON_ARRAY(e.to_id), '$')` returns true when the target ID is already inside the array at the root. JSON compares data types; the number `1` and the string `"1"` are not the same value. Ensure the ID types in the path and the tested value are consistent.

JSON paths easily represent string IDs containing delimiters, but each iteration must build and inspect a JSON document. For large graphs or long paths, memory and CPU overhead can be significant. Choose between string paths and JSON paths based on ID type, depth, and data scale; always benchmark with representative data.

## 9. Why Does UNION DISTINCT Not Replace a Cycle Guard?

Some people think they can use `UNION DISTINCT` instead of `UNION ALL` so MySQL automatically removes already-seen nodes. This only eliminates rows that are completely identical across all columns in the CTE.

For example, if the CTE contains only `node_id`, `UNION DISTINCT` can prevent an ID from repeating in the output. However, when the CTE also includes `path` or `depth`, the same node reached via another path produces a distinct row:

| node_id | depth | path |
|---:|---:|---|
| 3 | 2 | `1,2,3` |
| 3 | 2 | `1,4,3` |
| 1 | 3 | `1,2,3,1` |

Rows with the same `node_id` but different paths are not full-row duplicates. `UNION DISTINCT` keeps them and does not automatically detect path-based cycles.

For queries that need to track paths, use `UNION ALL` combined with an explicit cycle guard. Use `UNION DISTINCT` only when query semantics genuinely require deduplicating across the full column set and you have verified that doing so is sufficient to terminate.

## 10. Limiting Depth with cte_max_recursion_depth

MySQL provides the system variable `cte_max_recursion_depth` to cap the number of CTE recursion iterations. The default value is typically `1000`.

Check:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
SELECT @@GLOBAL.cte_max_recursion_depth;
```

You can set a custom limit for the session:

```sql
SET SESSION cte_max_recursion_depth = 200;
```

This limit applies to recursive CTEs running in the session. If a query exceeds it, MySQL aborts the query and returns an error instead of recursing infinitely.

Do not raise the limit just to bypass an error. First, check:

- Is there a cycle in the data?
- Does the recursive member have a proper termination condition?
- Is there an under-constrained join causing row counts to grow exponentially?
- Does the actual depth of the tree exceed business limits?
- Can the anchor be restricted to a single root or smaller branch?

Increase `cte_max_recursion_depth` only when large depth is a legitimate requirement, the query has a cycle guard, and resources have been measured. Avoid setting an excessively large value or removing limits without other safeguards.

## 11. Depth Guards and Server Limits Do Not Mean the Same Thing

A depth guard in a query is a business condition:

```sql
WHERE w.depth < 100
```

It limits the number of edges traversed along a path. The server limit `cte_max_recursion_depth` limits how many recursive member iterations the server allows.

These two values do not have to be equal. Set the depth guard low enough to fit the problem, while keeping the server limit as an independent safety net. If the depth guard cuts off a branch at level 100, the query may finish normally without having explored that branch completely.

To distinguish "no further nodes" from "hit the depth limit", you can select rows at the maximum depth that still have outgoing edges to flag an incomplete traversal. Example:

```sql
SELECT w.node_id, w.path, w.depth
FROM category_walk AS w
WHERE w.depth = 100
  AND EXISTS (
      SELECT 1
      FROM categories AS child
      WHERE child.parent_id = w.node_id
  );
```

Place this query inside the same `WITH RECURSIVE` statement as the corresponding `category_walk` CTE. Returned rows represent branches that could still expand further but hit the depth guard; they must be treated as incompletely traversed, not as proof that no cycles exist.

## 12. Termination Conditions Based on Business Status

You do not always need to traverse every edge. You can stop based on node or relationship attributes:

```sql
WITH RECURSIVE active_tree (id, parent_id, depth) AS (
    SELECT id, parent_id, 0
    FROM categories
    WHERE id = 10
      AND is_active = 1

    UNION ALL

    SELECT child.id, child.parent_id, parent.depth + 1
    FROM active_tree AS parent
    INNER JOIN categories AS child
        ON child.parent_id = parent.id
    WHERE child.is_active = 1
      AND parent.depth < 50
)
SELECT *
FROM active_tree;
```

This example expands only through active categories and caps at 50 levels. However, a status condition does not automatically detect cycles. If data can become corrupted, a path/cycle guard is still required.

Sometimes the recursive member stops naturally because no child rows are found. This holds only when data has no cycles or a cycle guard has already blocked looping paths. Do not rely on "trees usually don't have cycles" as a safety guarantee.

## 13. Checking Before Changing parent_id

A category move operation can create a cycle if a node is placed as a child of one of its own descendants.

For example, suppose you want to move node `10` under node `35`. Before updating, you must check whether `35` currently lies inside `10`'s subtree. If it does, the operation will create a loop.

```sql
WITH RECURSIVE subtree (node_id, path, depth) AS (
    SELECT
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0
    FROM categories AS c
    WHERE c.id = 10

    UNION ALL

    SELECT
        child.id,
        CONCAT(s.path, child.id, ','),
        s.depth + 1
    FROM subtree AS s
    INNER JOIN categories AS child
        ON child.parent_id = s.node_id
    WHERE s.depth < 100
      AND LOCATE(CONCAT(',', child.id, ','), s.path) = 0
)
SELECT EXISTS (
    SELECT 1
    FROM subtree
    WHERE node_id = 35
) AS would_create_cycle;
```

If `would_create_cycle = 1`, do not update `parent_id = 35` for node `10`. If the result is `0`, that only confirms within the traversed scope; if the subtree hit the depth guard, perform additional verification to avoid false conclusions.

In environments where multiple requests modify the tree concurrently, checking and then updating as two separate operations can suffer a race condition: two concurrent transactions both observe the old valid structure, then create links that form a cycle. Serialize structural changes per tree or lock an appropriate coordination/root row inside a transaction, re-check after acquiring the lock, and only then update. The checking CTE is one part of the workflow and does not itself create an anti-cycle constraint.

## 14. Distinguishing Cycles from Multiple Paths

A graph can have multiple paths to the same node without having a cycle:

```text
      B
    /   \
A         D
    \   /
      C
```

Both paths `A -> B -> D` and `A -> C -> D` reach D. If the first branch's path is `A,B,D` and the second branch's path is `A,C,D`, D has not appeared in either branch's individual path before being added. This is not a cycle.

A path-based cycle guard checks whether the next node appears in the current path itself. Do not arbitrarily use a global visited flag to conclude cycles in all graph types; a global visited set suits certain reachability problems, but can discard path information needed to prove a cycle.

## 15. Performance and the Risk of Path Explosion

A recursive CTE on a tree typically grows row counts proportionally to the number of traversed nodes. On a branching graph, path counts can grow very quickly. For example, an average branching factor of 3 outgoing edges per node at depth 10 can produce far more paths than the actual number of nodes.

Control measures:

- Restrict the anchor to the root or the set of nodes under investigation.
- Create indexes on columns used for edge expansion: `categories(parent_id)` or `graph_edges(from_id, to_id)`.
- Use a cycle guard to avoid looping along the same path.
- Use a depth guard aligned with business rules.
- Select only needed columns in the CTE; avoid carrying large payloads across every iteration.
- Measure with representative data and read `EXPLAIN`.
- Set time limits and recursion depth at appropriate operational levels.
- For large graphs, consider specialized graph algorithms or an external processing pipeline outside the database.

Example plan inspection:

```sql
EXPLAIN FORMAT=TREE
WITH RECURSIVE category_walk (id, depth) AS (
    SELECT id, 0
    FROM categories
    WHERE id = 10

    UNION ALL

    SELECT child.id, parent.depth + 1
    FROM category_walk AS parent
    JOIN categories AS child
        ON child.parent_id = parent.id
    WHERE parent.depth < 50
)
SELECT *
FROM category_walk;
```

The plan should show how MySQL accesses the child table via `parent_id`. If each iteration performs a full table scan of `categories`, check indexes and the data types in the join condition.

## 16. Restrictions to Remember on the Recursive Member in MySQL

The recursive member is not an arbitrary SELECT. MySQL restricts certain constructs in the recursive part to control execution. Key practical points:

- Reference the recursive CTE once in the `FROM` clause of the recursive member.
- Do not place the recursive reference inside a subquery.
- Do not use aggregate functions, window functions, `GROUP BY`, `ORDER BY`, or `DISTINCT` in the recursive member per MySQL restrictions.
- Avoid placing the recursive table on the nullable side of an outer join.
- Perform aggregation, ranking, or sorting after the CTE has finished producing the row set.

If you need to rank paths or group duplicate cycles, let the recursive CTE generate the required rows first, then use a non-recursive CTE or outer query for `GROUP BY`, window functions, and `ORDER BY`.

## 17. Common Errors

| Error | Cause | Fix |
|---|---|---|
| Recursive CTE hits recursion limit | Cycle present or insufficient termination condition | Add a path-based cycle guard and inspect data |
| Raising `cte_max_recursion_depth` but query still runs slowly | Only raised the threshold without fixing root cause | Check for cycles, fan-out, and depth guard |
| Path length error | CTE column type inferred too short from anchor | `CAST` path with capacity calculated from IDs and depth |
| ID `12` confused with `112` | Searching tokens without delimiters | Wrap tokens in delimiters or use a JSON array |
| `UNION DISTINCT` fails to stop cycle | Rows differ in path/depth so they are not full duplicates | Use `UNION ALL` together with an explicit cycle guard |
| DAG flagged as having a cycle | Confusing a node appearing in multiple branches with repeating on the same path | Track each path independently |
| Same cycle appears multiple times in report | Traversing from multiple start nodes or multiple points on the same cycle | Canonicalize cycles in a subsequent step |
| Query generates too many rows | Branching graph with many paths | Narrow anchor/depth, filter edges, and consider other algorithms |
| Foreign key still allows cycle creation | FK only checks parent existence, not acyclicity | Validate before changing and serialize tree modifications |
| CTE stops at depth cap and data is assumed valid | Depth guard truncated an unexplored branch | Report branches hitting the limit and inspect separately |

## 18. Safe Recursive CTE Design Checklist

- Which nodes or roots does the anchor member start from? Is the scope too broad?
- Does the recursive member join along the right edge or parent-child relationship?
- Does the path store enough information to detect a repeated node on the same path?
- Is the path type long enough for maximum depth and ID size?
- Can IDs contain delimiters that would confuse string matching?
- Is there a cycle guard stopping further expansion from rows where a cycle was detected?
- Does the depth guard reflect business bounds?
- Does the output distinguish "no further rows" from "hit depth limit"?
- Do `cte_max_recursion_depth` and timeouts protect the server?
- Do indexes support the edge-expansion / parent columns?
- Have cycles been distinguished from valid multi-path branches in a DAG?
- Is there a risk of multiple start nodes producing duplicate cycle results?
- Are tree modification operations serialized to avoid race conditions?
- Have row counts, depth, and runtime been measured on representative data?

## Conclusion

Cycle detection in a recursive CTE requires tracking each individual path and checking the next node before expanding. For numeric IDs, a delimited string path is a simple approach; for complex IDs, a JSON array provides cleaner membership checks. The condition `depth < max_depth` bounds scope, while `cte_max_recursion_depth` and timeouts protect server resources. These layers complement one another: a depth cap does not prove the data is cycle-free, foreign keys do not prevent cycles, and `UNION DISTINCT` does not replace a path-based cycle guard when rows carry path or depth columns. Designing narrow anchors, indexing expansion columns properly, validating before parent updates, and controlling concurrent modifications make tree and graph queries much safer.
