# Querying Organization Trees, Paths, and Depth

An organization tree is hierarchical data: each unit can have one parent unit and multiple child units. In the adjacency list model, a table stores this relationship using a self-referencing column such as `parent_unit_id`. A self join can retrieve the direct parent, but when you need all subordinates, the path from the root to a node, or arbitrary depth, a recursive query is the right approach.

MySQL 8.0 supports recursive common table expressions (recursive CTEs) via `WITH RECURSIVE`. A CTE starts from one or more root rows (anchor member), then repeatedly executes the recursive member to find subsequent rows. This technique helps query organization trees, multi-level categories, folder structures, and parent-child relationships without knowing the depth in advance.

In the `DATABASE_MYSQL` module, you need to understand both tree structures and cardinality, indexes, recursion limits, and cycles. A self-referencing foreign key only ensures the parent row exists; it does not automatically prevent a cycle such as A being the parent of B and B being the parent of A.

## Objectives

After this lesson, you will be able to:

- Model an organization tree using an adjacency list and a self-referencing foreign key.
- Write a recursive CTE with an anchor member and a recursive member.
- Query the entire tree, a subtree, or trace upward to ancestors.
- Build the path from root to node and compute each node's depth.
- Sort results in tree order rather than just by name or ID.
- Detect and prevent cycles during traversal.
- Understand `cte_max_recursion_depth`, data type limits, and execution costs.
- Use indexes and `EXPLAIN` to inspect tree queries.

## 1. Organization Tree Structure

In an adjacency list, each row represents an organizational unit. `parent_unit_id` points to the `unit_id` of the direct parent; a root node has `parent_unit_id IS NULL`.

```sql
CREATE TABLE org_unit (
    unit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_name VARCHAR(120) NOT NULL,
    parent_unit_id BIGINT UNSIGNED NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (unit_id),
    KEY idx_org_parent_sort (parent_unit_id, sort_order, unit_id),
    CONSTRAINT fk_org_unit_parent
        FOREIGN KEY (parent_unit_id)
        REFERENCES org_unit (unit_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Column meanings:

- `unit_id`: unique identifier of the unit.
- `unit_name`: unit name.
- `parent_unit_id`: ID of the direct parent; `NULL` if it is a root.
- `sort_order`: display order among sibling units sharing the same parent.
- `idx_org_parent_sort`: supports finding child nodes by parent and display order.

The self-referencing foreign key prevents a row from pointing to a nonexistent `parent_unit_id`. `ON DELETE RESTRICT` prevents deleting a unit while child units still reference it. This rule forces the application to handle the subtree before deleting a parent node.

### 1.1. Sample Data

Insert nodes in parent-first, child-later order:

```sql
INSERT INTO org_unit
    (unit_id, unit_name, parent_unit_id, sort_order)
VALUES
    (1, 'Executive', NULL, 0),
    (2, 'Engineering', 1, 10),
    (3, 'Product', 1, 20),
    (4, 'Platform', 2, 10),
    (5, 'API', 4, 10),
    (6, 'Web', 4, 20),
    (7, 'People', 1, 30),
    (8, 'Recruitment', 7, 10),
    (9, 'HR Operations', 7, 20);
```

Tree after loading data:

```text
Executive (1)
├── Engineering (2)
│   └── Platform (4)
│       ├── API (5)
│       └── Web (6)
├── Product (3)
└── People (7)
    ├── Recruitment (8)
    └── HR Operations (9)
```

`sort_order` determines the order of nodes sharing the same parent. IDs do not necessarily reflect display order or position in the tree; you should not rely on ascending IDs to sort hierarchical structures.

## 2. How Does a Recursive CTE Work?

General structure:

```sql
WITH RECURSIVE cte_name (column_list) AS (
    -- Anchor member: produce the starting row set.
    SELECT ...

    UNION ALL

    -- Recursive member: find next rows from previous results.
    SELECT ...
    FROM base_table AS child
    JOIN cte_name AS previous_level
      ON ...
)
SELECT ...
FROM cte_name;
```

The process consists of these steps:

1. MySQL runs the anchor member to produce the initial rows.
2. The recursive member uses the CTE's current row set to find the next generation.
3. New rows are added to the CTE result.
4. The recursive member continues running until no additional rows are produced or the recursion limit is reached.
5. The outer query reads the final result.

In an organization tree, the anchor is usually the root node or a user-selected node. The recursive member finds rows whose `parent_unit_id` equals the `unit_id` from the previous level.

### 2.1. Anchor Member and Recursive Member

For the organization tree:

- The anchor member selects `Executive` as the root.
- The first iteration finds `Engineering`, `Product`, `People`.
- The next iteration finds `Platform`, `Recruitment`, `HR Operations`.
- The next iteration finds `API`, `Web`.
- When no child nodes remain, recursion ends.

`UNION ALL` is typically used to retain rows generated in each iteration without deduplicating. If the tree data guarantees each node has only one parent, each node is reached via a single path from the root. If data can contain multiple paths or cycles, dedicated controls must be designed.

### 2.2. CTE Column Data Types

MySQL infers the data types of recursive CTE columns from the anchor member. If a path column is inferred from a short string in the anchor, longer values concatenated in later iterations may be truncated or raise errors depending on type and configuration.

Therefore, when building paths, `CAST()` in the anchor to a sufficiently large length and maintain compatible types in the recursive member. This lesson caps examples at depth 20 and uses a 4096-character path column; real systems must calculate sizes based on name lengths, level counts, and schema storage limits.

## 3. Querying the Full Tree, Computing Depth, and Building Paths

The following query starts from all root nodes, traverses downward through child levels, and simultaneously builds:

- `depth`: depth level, with root as 0.
- `id_path`: JSON array containing IDs in order from the root to the current node, used for cycle detection.
- `name_path`: name path for display.
- `sort_path`: sort path to preserve tree order.

```sql
WITH RECURSIVE org_tree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(
                LPAD(sort_order, 10, '0'), ':',
                LPAD(unit_id, 20, '0')
            ) AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        tree.depth + 1,
        JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id),
        CAST(CONCAT(tree.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                tree.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
      AND JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT
    unit_id,
    unit_name,
    parent_unit_id,
    depth,
    name_path
FROM org_tree
ORDER BY sort_path;
```

The output looks like:

| unit_id | unit_name | parent_unit_id | depth | name_path |
|---:|---|---:|---:|---|
| 1 | Executive | `NULL` | 0 | Executive |
| 2 | Engineering | 1 | 1 | Executive / Engineering |
| 4 | Platform | 2 | 2 | Executive / Engineering / Platform |
| 5 | API | 4 | 3 | Executive / Engineering / Platform / API |
| 6 | Web | 4 | 3 | Executive / Engineering / Platform / Web |
| 3 | Product | 1 | 1 | Executive / Product |
| 7 | People | 1 | 1 | Executive / People |
| 8 | Recruitment | 7 | 2 | Executive / People / Recruitment |
| 9 | HR Operations | 7 | 2 | Executive / People / HR Operations |

Actual ordering is controlled by `sort_path`, not physical row order or IDs. `LPAD()` pads `sort_order` and `unit_id` to fixed widths so lexicographical string sorting reflects numerical order. The example assumes `sort_order` is non-negative and `unit_id` is `BIGINT UNSIGNED`.

### 3.1. Meaning of depth

Convention used in this lesson:

| Node | Depth |
|---|---:|
| Root node | 0 |
| Direct child of root | 1 |
| Grandchild of root | 2 |
| Great-grandchild of root | 3 |

If the UI wants 1-based level numbering, you can display `depth + 1` as `level`. Standardize the convention across APIs and reports so depth and level are not confused.

### 3.2. Meaning of name_path and sort_path

`name_path` is a string intended for display. If unit names can contain `/`, this string is no longer suitable for splitting back into components; when machine-readable data is needed, use a JSON array or separate ID columns.

`sort_path` concatenates the order key of each node along the path from the root. Sorting by the full path keeps parent nodes before children and preserves sibling branches by `sort_order`. `unit_id` is appended to each segment to provide a deterministic order when two sibling nodes share the same `sort_order`.

## 4. Querying a Subtree by Selected Node

If a user opens a specific unit, you only need that unit's subtree. Replace the anchor condition `parent_unit_id IS NULL` with the selected ID:

```sql
WITH RECURSIVE org_subtree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(LPAD(sort_order, 10, '0'), ':', LPAD(unit_id, 20, '0'))
            AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE unit_id = 2

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        parent.depth + 1,
        JSON_ARRAY_APPEND(parent.id_path, '$', child.unit_id),
        CAST(CONCAT(parent.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                parent.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_subtree AS parent
        ON child.parent_unit_id = parent.unit_id
    WHERE parent.depth < 20
      AND JSON_CONTAINS(parent.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, parent_unit_id, depth, name_path
FROM org_subtree
ORDER BY sort_path;
```

With `unit_id = 2`, the result includes `Engineering`, `Platform`, `API`, and `Web`; `Engineering` is the anchor row with depth 0. If you only want descendants, within the **same CTE statement above**, replace the final `SELECT` with:

```sql
SELECT unit_id, unit_name, parent_unit_id, depth, name_path
FROM org_subtree
WHERE depth > 0
ORDER BY sort_path;
```

This is a replacement for the outer query portion, not a standalone statement, because the CTE scope ends after the statement. The filter condition in the outer query leaves the tree traversal intact; it only hides the starting node from the final output.

## 5. Querying the Path from a Node Up to the Root

To find managers, superiors, or the ancestor chain of a unit, anchor at the target node and recurse in the reverse direction: from `parent_unit_id` to the parent row.

```sql
WITH RECURSIVE ancestors AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        0 AS distance,
        JSON_ARRAY(unit_id) AS id_path
    FROM org_unit
    WHERE unit_id = 8

    UNION ALL

    SELECT
        parent.unit_id,
        parent.unit_name,
        parent.parent_unit_id,
        current_node.distance + 1,
        JSON_ARRAY_APPEND(current_node.id_path, '$', parent.unit_id)
    FROM org_unit AS parent
    JOIN ancestors AS current_node
        ON parent.unit_id = current_node.parent_unit_id
    WHERE current_node.distance < 20
      AND JSON_CONTAINS(current_node.id_path, CAST(parent.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, parent_unit_id, distance
FROM ancestors
ORDER BY distance DESC;
```

For the `Recruitment` unit (ID 8), the CTE finds in sequence:

1. Recruitment, distance 0.
2. People, distance 1.
3. Executive, distance 2.

Sorting by `distance DESC` returns results from the root down to the selected node. If you want to display from the current node upward, use `ORDER BY distance ASC`.

### 5.1. Retrieving Only the Direct Manager

If you only need the direct parent, a recursive CTE is unnecessary:

```sql
SELECT
    child.unit_id,
    child.unit_name,
    parent.unit_id AS parent_id,
    parent.unit_name AS parent_name
FROM org_unit AS child
LEFT JOIN org_unit AS parent
    ON parent.unit_id = child.parent_unit_id
WHERE child.unit_id = 8;
```

A self join is simpler and less costly when only one level is needed. Use a recursive CTE when an arbitrary number of levels is required.

## 6. Finding a Single Node's Path in the Full Tree

You can use a CTE traversing from the root and filter the target node in the outer query. This works when you need the display path and depth of a node:

```sql
WITH RECURSIVE org_tree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(LPAD(sort_order, 10, '0'), ':', LPAD(unit_id, 20, '0'))
            AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        tree.depth + 1,
        JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id),
        CAST(CONCAT(tree.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                tree.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
      AND JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, depth, name_path
FROM org_tree
WHERE unit_id = 5;
```

The API output can include `unit_id`, `depth`, and `name_path`; the UI does not need to query each parent level individually to build a breadcrumb. For large tables, if you only need the path of a single node, the upward ancestor query in the previous section can traverse far fewer branches than scanning the entire tree from the root.

## 7. Detecting and Preventing Cycles

A self-referencing table can have valid foreign keys yet still contain a cycle. For example:

```text
A.parent = B
B.parent = C
C.parent = A
```

Every `parent_unit_id` points to an existing row, yet there is no root node in the cycle. Foreign keys do not enforce acyclicity.

### 7.1. Why Is UNION DISTINCT Not Enough?

You might think changing `UNION ALL` to `UNION DISTINCT` will automatically eliminate loops. This is unreliable if the CTE contains columns that change each iteration such as `depth` or `path`:

- On the first visit, a node has `depth = 1`.
- When looping back, the same ID has `depth = 4` and a different path.
- The entire rows differ, so `UNION DISTINCT` keeps them.

Full-row deduplication is not equivalent to detecting whether an ID has already appeared in the current path. You must track visited IDs.

### 7.2. Using a JSON Path to Prevent Repeating IDs on the Same Path

In the recursive CTE example, `id_path` is a JSON array holding the IDs from the anchor to the current node:

```sql
JSON_ARRAY(unit_id) AS id_path
```

Each iteration appends the child ID to the array:

```sql
JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id)
```

Before proceeding, check that the child ID is not yet in the path:

```sql
JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
```

If the ID has already appeared, that branch is not expanded further. This protects the path currently being traversed; it does not automatically repair source data or report cycles in components unreachable from the anchor.

### 7.3. Checking Data for Cycles and Orphans

InnoDB foreign keys normally prevent orphans when enabled and data is written normally. However, imports may have been run with `foreign_key_checks` disabled, or legacy systems may contain unchecked data. You can find rows without an existing parent:

```sql
SELECT child.unit_id, child.unit_name, child.parent_unit_id
FROM org_unit AS child
LEFT JOIN org_unit AS parent
    ON parent.unit_id = child.parent_unit_id
WHERE child.parent_unit_id IS NOT NULL
  AND parent.unit_id IS NULL;
```

To detect cycles, you can walk ancestors from each node with a path guard and look for a path returning to an already-seen ID. This check can be expensive on large tables; run it in bounded data-audit jobs rather than casually on production.

Example checking the ancestor path of a specific node: record a flag when the next parent row already appears in `id_path`, then stop expanding that branch:

```sql
WITH RECURSIVE ancestor_walk AS (
    SELECT
        unit_id AS start_id,
        unit_id,
        parent_unit_id,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        0 AS cycle_detected
    FROM org_unit
    WHERE unit_id = 1

    UNION ALL

    SELECT
        walk.start_id,
        parent.unit_id,
        parent.parent_unit_id,
        walk.depth + 1,
        JSON_ARRAY_APPEND(walk.id_path, '$', parent.unit_id),
        JSON_CONTAINS(walk.id_path, CAST(parent.unit_id AS JSON))
    FROM org_unit AS parent
    JOIN ancestor_walk AS walk
        ON parent.unit_id = walk.parent_unit_id
    WHERE walk.depth < 20
      AND walk.cycle_detected = 0
)
SELECT start_id, unit_id, parent_unit_id, depth, id_path
FROM ancestor_walk
WHERE cycle_detected = 1;
```

If the query returns rows, `unit_id` in that row is the ID revisited along the path. For example, anchoring at `Executive` after temporarily creating a cycle `Executive -> Platform -> Engineering -> Executive` detects that ID `1` repeats. To check the entire table, you can run similar logic for every `start_id`, though cost can grow with node count and depth; run it in batches or in a bounded data-verification job.

### 7.4. Preventing Cycles When Writing Data

Before moving a node to a new parent, verify that the new parent is not the node itself and does not lie within that node's subtree. For instance, `Engineering` must not be moved under `Platform`, because `Platform` is already a descendant of `Engineering`.

An application workflow can:

1. Start a transaction.
2. Lock or concurrency-control the relevant rows using an appropriate strategy.
3. Traverse the subtree of the node being moved and confirm the new parent is not in that subtree.
4. Update `parent_unit_id`.
5. Commit; roll back if a cycle is detected or a conflict occurs.

Simply checking with a `SELECT` and updating afterward can suffer a race condition if two transactions concurrently move two branches in ways that form a cycle. For systems where multiple users edit the tree, design update locking/serialization or an application-layer coordination mechanism; a self-referencing foreign key alone is insufficient.

## 8. Recursion Limits and Cost Control

MySQL limits recursive CTE iterations using the `cte_max_recursion_depth` variable. The default value is typically 1000. Check it:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
```

You can set a custom limit for the session:

```sql
SET SESSION cte_max_recursion_depth = 100;
```

Set a limit appropriate to the maximum depth of your data. Do not raise the limit just to hide a cycle or bad data. `WHERE tree.depth < 20` in the example is an explicit business cap; it stops traversing deeper than 20 edges from the anchor.

### 8.1. Path Length Limits

`name_path` and `sort_path` are `CAST()` with fixed lengths in the anchor. If the tree grows deeper than expected or unit names are longer, paths can exceed the limit. You should:

- Compute the maximum length from level count and name lengths.
- Add an appropriate depth guard.
- Check for truncation warnings/errors on your MySQL version.
- Use a JSON array for machine-readable paths instead of a delimited string.
- Avoid storing display paths in physical columns if they can be reconstructed from parent-child links.

Paths built in a CTE serve only the query. If you persist precomputed paths in the table, every node move may require updating all descendants; weigh synchronization cost and consistency.

### 8.2. Recursive CTEs Can Be Resource-Intensive

Each iteration needs to locate child rows from the current set. An index on `parent_unit_id` makes fetching each node's children much more efficient. Without an index, MySQL may repeatedly scan many rows.

Factors that make the query heavy:

- Nodes with a very large number of children.
- Deep trees or many roots.
- JSON/string paths growing larger with every iteration.
- Queries requiring sorting the entire tree by `sort_path`.
- High concurrency with large materialized results.

Restrict the anchor to the node requested by the user, select only needed columns, and avoid traversing the entire tree when only one branch is needed.

## 9. Indexes and EXPLAIN for Tree Queries

The following index is declared in the table:

```sql
KEY idx_org_parent_sort (parent_unit_id, sort_order, unit_id)
```

It supports finding rows whose `parent_unit_id` equals the current node's ID. The trailing columns keep child order and ID available in the index. InnoDB also requires an index on foreign key columns; declaring a composite index starting with `parent_unit_id` satisfies this requirement.

Inspect the plan:

```sql
EXPLAIN FORMAT=TREE
WITH RECURSIVE org_tree AS (
    SELECT unit_id, unit_name, parent_unit_id, 0 AS depth
    FROM org_unit
    WHERE unit_id = 1

    UNION ALL

    SELECT child.unit_id, child.unit_name, child.parent_unit_id, tree.depth + 1
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
)
SELECT * FROM org_tree;
```

Check the access path for the anchor via primary key and for the recursive member via the `parent_unit_id` index. `EXPLAIN ANALYZE` on MySQL 8.0.18 and later can show actual row counts and timings; this command executes the query, so use it only on read queries with controlled scope.

Not every query requires adding indexes. If the table is small, the optimizer may choose a table scan. Indexes increase write cost and storage; base decisions on workload and actual execution plans.

## 10. Aggregating by Depth or Branch

After building the CTE, you can aggregate the number of units per level:

```sql
WITH RECURSIVE org_tree AS (
    SELECT unit_id, unit_name, parent_unit_id, 0 AS depth
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT child.unit_id, child.unit_name, child.parent_unit_id, tree.depth + 1
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
)
SELECT depth, COUNT(*) AS unit_count
FROM org_tree
GROUP BY depth
ORDER BY depth;
```

The aggregate is placed in the outer query, after the recursive CTE produces the tree set. The recursive member in MySQL restricts aggregates, `GROUP BY`, window functions, and certain query constructs; therefore, keep the recursive part focused on finding the next rows, then aggregate outside.

If you need to count descendants for each node, you can start a separate CTE per root to summarize or use a recursive query adding a `root_id` to carry the starting node. Watch the intermediate row count, because generating a path for every node can grow rapidly in wide or deep trees.

## 11. Modifying the Organization Tree

### 11.1. Adding a Child Node

Add the unit `Data Engineering` under `Engineering`:

```sql
INSERT INTO org_unit (unit_name, parent_unit_id, sort_order)
VALUES ('Data Engineering', 2, 30);
```

The foreign key confirms `parent_unit_id = 2` exists. The `idx_org_parent_sort` index helps the following query find direct children:

```sql
SELECT unit_id, unit_name, sort_order
FROM org_unit
WHERE parent_unit_id = 2
ORDER BY sort_order, unit_id;
```

### 11.2. Moving a Node to Another Branch

For example, moving `Web` under `Product`:

```sql
UPDATE org_unit
SET parent_unit_id = 3
WHERE unit_id = 6;
```

The foreign key guarantees `Product` exists, but does not prevent creating a cycle. Before updating in a real application, verify that the new parent is not in `Web`'s subtree, and handle race conditions across concurrent moves.

### 11.3. Deleting a Branch

With `ON DELETE RESTRICT`, you cannot delete a parent node while it still has children. You can delete from leaves up to the root in order, or implement a controlled branch-deletion workflow. Do not switch to `ON DELETE CASCADE` just to simplify operations if the tree holds historical data or separate ownership records.

## 12. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Recursive CTE loops too long or hits limit | Cycle present, deep tree, or overly broad anchor | Check data, add path guard and depth guard |
| Only one child level appears | Using a regular self join instead of a recursive CTE | Use `WITH RECURSIVE` if depth is variable |
| Some units missing when traversing from root | Nodes reside in a rootless component, orphans, or cycle | Inspect `parent_unit_id`, foreign keys, and imported data |
| Path truncated or data type error | Anchor inferred too short a string | `CAST()` path in anchor to sufficient length and check depth |
| Wrong tree order | Only `ORDER BY unit_id` or `unit_name` | Build `sort_path` from each level's sort_order |
| Same node appears multiple times | Data is no longer a single-parent tree, or recursive relation generates multiple paths | Check cardinality, keys, and model rules |
| Deleting parent fails with foreign key error | Child rows still reference it | Handle subtree first or apply proper deletion policy |
| Updating parent creates a cycle | Foreign key only checks parent existence | Validate subtree and serialize updates |
| Full tree query is slow | Broad anchor, missing parent index, or large paths | Traverse only needed branch, add appropriate index, inspect `EXPLAIN` |

## 13. Practice Lab

Perform these in a dedicated lab database with the `org_unit` table:

1. Create the self-referencing table and load the sample tree in parent-first, child-later order.
2. Write a recursive CTE starting from all roots; return ID, name, parent ID, and depth.
3. Add `name_path` to display a breadcrumb from the root to each unit.
4. Build `sort_path` from `sort_order` and ID; verify branches display in exact tree order.
5. Query the subtree of `Engineering` and return only descendants using `depth > 0`.
6. Query the ancestors of `Recruitment`; sort to display from `Executive` to the current node.
7. Count units at each depth using an aggregate outside the recursive CTE.
8. Try creating a cycle in the lab table by changing `Executive`'s parent to `Platform`; observe why the foreign key fails to prevent the cycle. Then roll back or restore valid data.
9. Add JSON `id_path` and a `JSON_CONTAINS` condition to stop a branch when an ID already appears.
10. Set a low session `cte_max_recursion_depth` in the lab; observe the limit and restore the value after testing.
11. Run the orphan query using `LEFT JOIN`; explain why normal FK-enforced data might still need checking after special imports.
12. Run `EXPLAIN FORMAT=TREE` for the anchor and recursive member; verify that the index on `parent_unit_id` is considered.
13. Write a procedure to move a unit to a new parent, including cycle checking and handling two concurrent update requests.

You have completed this lesson when you can query trees of arbitrary depth, construct paths and depth, predict recursion limits, and explain why a self-referencing foreign key alone is not enough to guarantee the structure always remains a valid tree.

## 14. Principles to Remember

- An adjacency list stores the direct parent using `parent_unit_id`; root nodes have a `NULL` parent.
- A self-referencing foreign key ensures the parent exists but does not automatically prevent cycles.
- A recursive CTE consists of an anchor member and a recursive member; `WITH RECURSIVE` iterates until no new rows remain or the limit is reached.
- `depth = 0` is the starting node; each child level increments depth by 1.
- Use `JSON_ARRAY`/`JSON_ARRAY_APPEND` to track IDs along the path and `JSON_CONTAINS` to prevent repeating IDs.
- `UNION DISTINCT` does not replace cycle detection if depth/path columns change across iterations.
- Use `CAST()` in the anchor to allocate sufficient path length; compute it from maximum depth and maximum name size.
- Use `sort_path` when tree ordering must be preserved; standalone IDs or names do not necessarily reflect sibling order.
- `cte_max_recursion_depth` limits iterations; do not raise the limit to mask cycles or bad data.
- An index starting with `parent_unit_id` supports finding child nodes; verify with `EXPLAIN`.
- Traverse only the needed subtree instead of the full tree if the application only opens one branch.
- When moving a node, verify the new parent is not in its subtree and control concurrent updates.
