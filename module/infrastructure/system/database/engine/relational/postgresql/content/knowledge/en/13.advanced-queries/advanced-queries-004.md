# Cycle Detection and Traversal Order Control in PostgreSQL

A system may store department hierarchies, category trees, task dependencies, product bills of materials, or relationship networks between entities. When you need to find all sub-levels or entities reachable from a starting point, PostgreSQL supports **recursive queries** via `WITH RECURSIVE`. However, real-world data is not always a clean tree: an entity can lead back to itself, or multiple paths can lead to the same vertex.

For example, in a relationship graph:

```text
1 ──► 2 ──► 4 ──► 5 ──► 6
│            ▲       │
└──► 3 ──────┘       └──► 2
     │
     └──► 7 ──► 8 ──► 8
```

- The path `2 → 4 → 5 → 2` is a **cycle**.
- The edge `8 → 8` is a **self-loop** (a cycle of length one).
- Vertex `4` is reachable from both `1 → 2 → 4` and `1 → 3 → 4`. **Having multiple paths to a vertex is not necessarily a cycle**.
- If you keep expanding relationships with `UNION ALL` without control, the query can keep generating `2 → 4 → 5 → 2 → 4 → ...` indefinitely.
- If you get the right results without ordering them, the list may appear in an unpredictable order. For UIs displaying trees, it is often necessary to distinguish **breadth-first search (BFS)** from **depth-first search (DFS)**.

This lesson belongs to the **Advanced Queries** chapter of the *Database Engine Relational PostgreSQL* module. You will learn:

- The structure of `WITH RECURSIVE`, termination conditions, and the meaning of `Recursive Union`.
- How to store the **current path** in an array and detect repeated vertices with `ANY`.
- Standard SQL syntax **`CYCLE ... SET ... USING ...`** introduced in PostgreSQL 14.
- **`SEARCH BREADTH FIRST`** and **`SEARCH DEPTH FIRST`** syntax for generating sort keys.
- Why `SEARCH` does not force the engine to execute in BFS/DFS order and why the result still needs `ORDER BY`.
- Differences between **a cycle on the current path**, **a vertex reached via multiple paths**, and **global deduplication** using `UNION`.
- Depth limits, avoiding path-count explosion, index selection, inspection with `EXPLAIN`, and query design on multi-tenant hierarchical data.

> **Version requirement:** `WITH RECURSIVE` has existed since older PostgreSQL versions, while `SEARCH` and `CYCLE` syntax are supported from **PostgreSQL 14** onward. On PostgreSQL 13 or older, use the array-based path technique shown in the manual examples in this lesson. Check your server first with `SHOW server_version;`.

## 1. Trees, Graphs, Paths, and Cycles

### 1.1. Core concepts

| Term | Meaning | Example |
|---|---|---|
| **Vertex / Node** | A connected entity | Employee, category, task |
| **Edge** | A relationship from one vertex to another | Task A depends on B |
| **Directed graph** | Each edge has a start and an end | `A → B` does not imply `B → A` |
| **Path** | Sequence of consecutive vertices along edges | `1 → 2 → 4 → 5` |
| **Depth** | Number of edges traversed from the starting point | Root 1 is at depth 0; 4 via 2 is at depth 2 |
| **Cycle** | A path returning to a vertex already encountered on that same path | `2 → 4 → 5 → 2` |
| **Self-loop** | An edge from a vertex to itself | `8 → 8` |
| **Tree** | Acyclic hierarchical structure where every non-root vertex has exactly one parent | Ideal folder tree |
| **DAG** | Directed acyclic graph | Multiple tasks sharing a common dependency |

A graph can have multiple paths to one vertex while remaining **acyclic**. For example, `1 → 2 → 4` and `1 → 3 → 4` both reach 4 without looping back to a previously visited vertex.

### 1.2. Two different meanings of "visited"

When traversing a graph, be clear whether the requirement is:

1. **List all valid paths from the root**: a vertex may appear multiple times if reached via different paths; only forbid repeating a vertex **along the same path** to avoid cycles.
2. **List each reachable vertex exactly once**: you can use global deduplication, such as `UNION` when the recursive state holds only vertex IDs and all paths do not need to be preserved.
3. **Detect the exact edge that closes a cycle**: you must track the path or use `CYCLE` to flag rows that cause repetition.

Do not use one "anti-repeat" query for all three goals when they have different semantics.

### 1.3. BFS and DFS are two ordering styles

**BFS – breadth-first search:** visits vertices at depth 0, then depth 1, 2, 3, and so on.

```text
Root 1
  ├─ 2
  │  └─ 4
  │     └─ 5
  └─ 3
     └─ 7
        └─ 8

BFS by level: 1 | 2,3 | 4,7 | 5,8 | 6
```

**DFS – depth-first search:** follows one branch deeply before moving to another branch. A DFS order picking branches in ascending ID order might look like:

```text
1 → 2 → 4 → 5 → 6
    (backtrack to another branch)
1 → 3 → 4 → 5 → 6
1 → 3 → 7 → 8
```

In a **graph with multiple paths**, the same vertex such as 4 or 5 can appear in multiple *path* records. The two lists above illustrate the traversal concept, **not** an exhaustive prediction of every row returned by a query on the sample graph when all paths are kept.

**Key point:** "traversal order" when presenting data in SQL usually means **sorting output rows by a BFS/DFS key**. It does not mean you can use `ORDER BY` to force PostgreSQL to execute recursive passes in the physical step-by-step order of an imperative algorithm.

## 2. Creating Graph Data in PostgreSQL

The examples use a dedicated schema and two tables: one for vertices and one for directed edges.

### 2.1. Creating the schema and tables

```sql
SHOW server_version;

CREATE SCHEMA IF NOT EXISTS graph_lab;

CREATE TABLE graph_lab.nodes (
    node_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE graph_lab.edges (
    from_id INTEGER NOT NULL
        REFERENCES graph_lab.nodes(node_id),
    to_id INTEGER NOT NULL
        REFERENCES graph_lab.nodes(node_id),
    PRIMARY KEY (from_id, to_id)
);
```

The `PRIMARY KEY (from_id, to_id)` constraint prevents storing **the same directed edge twice**, but **does not prevent cycles**. Edges `2 → 4`, `4 → 5`, and `5 → 2` have distinct key pairs and are therefore valid.

We also intentionally **do not forbid self-loops** with `CHECK (from_id <> to_id)`, so that we can observe `8 → 8`.

### 2.2. Inserting vertices and edges

```sql
INSERT INTO graph_lab.nodes (node_id, label)
VALUES
    (1, 'Root'),
    (2, 'Catalog A'),
    (3, 'Catalog B'),
    (4, 'Shared component'),
    (5, 'Dependency'),
    (6, 'Leaf'),
    (7, 'Branch C'),
    (8, 'Self-loop');

INSERT INTO graph_lab.edges (from_id, to_id)
VALUES
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 4),
    (3, 7),
    (4, 5),
    (5, 2), -- Cycle 2 -> 4 -> 5 -> 2
    (5, 6),
    (7, 8),
    (8, 8); -- Self-loop cycle
```

Visualization:

```text
          +-----------------------+
          |                       |
          v                       |
1 --> 2 --> 4 --> 5 --> 6        |
|           ^     |               |
v           |     +---------------+
3 ----------+
|
+--> 7 --> 8 --+
            ^   |
            +---+
```

Illustrative rows:

| from_id | to_id | Meaning |
|---:|---:|---|
| 1 | 2 | Branch A from root |
| 1 | 3 | Branch B from root |
| 2 | 4 | Leads to shared component |
| 3 | 4 | Another path also reaching 4 |
| 4 | 5 | Further dependency |
| 5 | 2 | Closes cycle via 2 |
| 7 | 8 | Leads to 8 |
| 8 | 8 | Self-loop |

### 2.3. Choosing the root and edge direction

In this example, edge `from_id → to_id` represents **moving from source to target**. A query finding vertices **reachable from node 1** joins on:

```sql
ON e.from_id = w.node_id
```

If you need to walk **backward** from a vertex to find vertices that lead to it, use:

```sql
ON e.to_id = w.node_id
```

This is a graph-semantics decision. Choosing the wrong direction can return zero rows or return the reverse dependency set from what the business requires.

## 3. How Does WITH RECURSIVE Work?

A recursive CTE (*recursive common table expression*) has two main parts:

1. **Anchor / non-recursive term:** generates the starting rows.
2. **Recursive term:** references the CTE being defined to generate the next layer of results.

The two parts are combined with `UNION` or `UNION ALL`.

### 3.1. Simple number-counting example

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
```

Result: `1, 2, 3, 4, 5`.

Walkthrough:

| Expansion round | Current rows | Newly generated rows |
|---|---|---|
| Anchor | 1 | 2 |
| Next round | 2 | 3 |
| Next round | 3 | 4 |
| Next round | 4 | 5 |
| Next round | 5 | None because `n < 5` is false |

The query ends when the recursive term **produces no new rows**. Here, `WHERE n < 5` controls length.

### 3.2. PostgreSQL's level-by-level evaluation model

A diagram matching PostgreSQL documentation:

```text
Anchor -> working table
             |
             v
       Recursive term
             |
             v
    intermediate table
             |
             +--> emit new rows to result
             |
             +--> become working table for next round
                       |
                       v
                 repeat until empty
```

PostgreSQL evaluates recursive CTEs by **iterating over intermediate row layers**. Therefore, without sorting, results often appear breadth-first. Still, **never rely on that observed order**: order among rows within a level is not guaranteed, and execution/optimizer choices can affect how data is returned.

To obtain verifiable result order, generate an **ordering key** and use `ORDER BY` in the final SELECT.

### 3.3. Graph query skeleton

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER AS node_id, 0 AS depth

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 5
)
SELECT node_id, depth
FROM walk
ORDER BY depth, node_id;
```

This example has a **depth limit**, so it terminates even when the graph has cycles. However, it **does not eliminate cycles**, and every path can still generate new rows for the same `node_id`. A depth limit merely truncates deeper output, potentially dropping valid paths.

**Do not remove `w.depth < 5` from this query on a cyclic graph** while still using `UNION ALL` without cycle detection. Because `depth` increases continuously, the same vertex can keep appearing forever at different depths.

## 4. Why Can UNION ALL Run Forever?

Suppose a recursive CTE carries both `node_id` and `depth`:

```sql
-- DO NOT RUN on graph_lab because it has cycles and no stopping condition:
-- WITH RECURSIVE walk(node_id, depth) AS (
--     SELECT 1, 0
--     UNION ALL
--     SELECT e.to_id, w.depth + 1
--     FROM walk AS w
--     JOIN graph_lab.edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
```

The path `1 → 2 → 4 → 5 → 2 → 4 ...` continuously produces:

```text
(2,1), (4,2), (5,3), (2,4), (4,5), (5,6), ...
```

Because `depth` changes, **every row is a new pair**, even though `node_id` repeats. With `UNION ALL`, PostgreSQL performs no deduplication.

### 4.1. Does switching to UNION fix it automatically?

If keeping **depth as well**:

```sql
-- Still unsafe if the stopping limit is removed:
-- WITH RECURSIVE walk(node_id, depth) AS (
--   SELECT 1, 0
--   UNION
--   SELECT e.to_id, w.depth + 1
--   FROM walk w JOIN graph_lab.edges e ON e.from_id=w.node_id
-- )
-- SELECT * FROM walk;
```

`UNION` removes **rows that match across the entire column list**, but `(2,1)` and `(2,4)` are distinct because their depths differ. Therefore, **switching `UNION ALL` to `UNION` does not automatically fix all cyclic recursive queries**.

### 4.2. When only each vertex once is needed, UNION can suffice

If the question is strictly "which vertices are reachable from 1", without needing depth or all paths:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER

    UNION

    SELECT e.to_id
    FROM reachable AS r
    JOIN graph_lab.edges AS e
        ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Result: vertices `1, 2, 3, 4, 5, 6, 7, 8`, each appearing **once**.

Here each row contains only **`node_id`**, so `UNION` discards a vertex already seen in prior steps. On a finite graph, expansion stops once no new vertices remain.

**Trade-off:** the query does not preserve **all paths** to a vertex, cannot identify which edge closes a cycle, and cannot simply add `depth`/`path` while expecting the same deduplication behavior to hold.

| Goal | Suitable strategy |
|---|---|
| Set of reachable vertices, no paths needed | `UNION` over ID only or deduplicatable state |
| All simple paths without repeated vertices | `UNION ALL` + path-local cycle check |
| Flagging cycle-closing paths | `CYCLE` or manual `is_cycle` calculation |
| BFS/DFS presentation | `SEARCH` or `depth/path` keys, then `ORDER BY` |

## 5. Manual Cycle Detection Using a Path Array

A clear solution is carrying the **current path** in each row of the recursive CTE.

### 5.1. Keeping an array of visited vertices

With `INTEGER` IDs:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT
        1::INTEGER AS node_id,
        0::INTEGER AS depth,
        ARRAY[1]::INTEGER[] AS path

    UNION ALL

    SELECT
        e.to_id AS node_id,
        w.depth + 1 AS depth,
        w.path || e.to_id AS path
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    depth,
    path
FROM walk
ORDER BY path;
```

Components:

- `ARRAY[1]::INTEGER[]`: initial path containing only root 1.
- `w.path || e.to_id`: appends the next vertex to the **end of the path array**.
- `e.to_id = ANY(w.path)`: checks whether the next vertex **already exists on the current path**.
- `NOT (...)`: expands only if the new vertex has **not appeared** on the current path.
- `ORDER BY path`: sorts paths lexicographically by array elements (with integer IDs in the lab), yielding a branch-by-branch DFS-like display.

Examples of valid paths:

```text
{1}
{1,2}
{1,2,4}
{1,2,4,5}
{1,2,4,5,6}
{1,3}
{1,3,4}
{1,3,4,5}
{1,3,4,5,2}
{1,3,4,5,6}
{1,3,7}
{1,3,7,8}
```

These lines are **sample paths**, not a guarantee that `SELECT` outputs this exact order if `ORDER BY` is omitted. Path `1 → 3 → 4 → 5 → 2` is permitted because vertex 2 **is not yet in that specific path**, even though 2 appeared in another branch.

From `1 → 2 → 4 → 5`, the next edge `5 → 2` is blocked because 2 is already in the path. From `1 → 3 → 7 → 8`, edge `8 → 8` is blocked because 8 is already present.

### 5.2. Counting paths differs from counting vertices

Because vertex `4` appears in both `{1,2,4}` and `{1,3,4}`:

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    COUNT(*) AS total_path_rows,
    COUNT(DISTINCT node_id) AS unique_reachable_nodes
FROM walk;
```

`COUNT(*)` counts rows representing **path/endpoint pairs**; `COUNT(DISTINCT node_id)` counts **distinct** target vertices.

Do not interpret `COUNT(*)` in a path-retaining query as "number of unique employees/categories", since one entity may be reached via multiple branches.

### 5.3. Why check per path rather than globally visited?

Paths `1 → 2 → 4` and `1 → 3 → 4` are not a cycle. If the goal is **listing dependencies by branch**, both paths must be kept. A global "visited" set would drop the second path, losing information about multiple parents/routes.

Path-based cycle detection answers: **"does the next vertex repeat within this specific vertex sequence?"**. That is a different rule from **"has this vertex appeared in any prior branch?"**.

### 5.4. The NOT (... = ANY(...)) condition and NULL

This example relies on `node_id NOT NULL` via the primary key. If vertex keys can be `NULL` or a composite key expression has a NULL component, `= ANY(array)` can return unknown and `NOT` will not behave as expected.

For real graphs, choose **stable, non-NULL vertex identifiers**, or adopt an explicit NULL-safe comparison strategy. Never copy an integer-array pattern onto a nullable composite key without re-verifying behavior.

## 6. Seeing the Cycle-Closing Edge: Computing is_cycle Manually

In the previous section, cycle-closing edges were filtered **before creating the new row**, so the output contained only acyclic paths. If you need to **report detected cycles**, generate the cycle-closing row too, tag it `is_cycle = true`, and **stop expanding flagged rows**.

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT
        1::INTEGER,
        0::INTEGER,
        ARRAY[1]::INTEGER[],
        FALSE

    UNION ALL

    SELECT
        e.to_id,
        w.depth + 1,
        w.path || e.to_id,
        e.to_id = ANY(w.path) AS is_cycle
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, depth, path, is_cycle
FROM walk
ORDER BY path;
```

How it works:

1. At each step, check whether the **vertex being added** is already in `w.path`.
2. If it is, the new row is still created with `is_cycle=true`, and `path` includes **the second occurrence of the vertex**.
3. The next recursive pass expands only `WHERE NOT w.is_cycle`, so cycle-closing rows **are not used to grow further paths**.

Rows you can observe:

```text
path = {1,2,4,5,2}     is_cycle = true
path = {1,3,4,5,2,4}   is_cycle = true
path = {1,3,7,8,8}     is_cycle = true
```

In path `{1,3,4,5,2,4}`, edge `2 → 4` closes the cycle **4 → 5 → 2 → 4**; vertex 2 was not in the earlier part of this path and was validly appended previously.

### 6.1. Listing only the cycles

```sql
WITH RECURSIVE walk(node_id, path, is_cycle) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[], FALSE
    UNION ALL
    SELECT
        e.to_id,
        w.path || e.to_id,
        e.to_id = ANY(w.path)
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, path
FROM walk
WHERE is_cycle
ORDER BY path;
```

This returns **paths from the root that hit a cycle**. If you need only the **loop segment** without the prefix from the root, you can slice the path starting from the first occurrence of the repeated vertex. In large graphs with many paths, the same cycle can show up along multiple routes; normalize/deduplicate cycles in the reporting step if counting **distinct cycles**.

### 6.2. Depth limit as an extra safeguard

You can add:

```sql
WHERE NOT w.is_cycle
  AND w.depth < 30
```

This limit is a **product/resource constraint**: paths deeper than 30 edges will not be expanded. It does not replace cycle detection, and **it can miss** vertices or cycles that appear only at greater depths.

On finite graphs, blocking repeated vertices per path ensures generated paths have finite length. Nevertheless, **the number of simple paths can still be huge**, especially in DAGs with many converging branches. Bound data volume, execution time, and query scope appropriately.

## 7. CYCLE in PostgreSQL 14+: Automatic Cycle Detection

PostgreSQL 14 and later provide the `CYCLE` clause for recursive CTEs, removing the need to manually build path arrays and check membership at every step.

### 7.1. Basic syntax

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
```

Core clause:

```sql
CYCLE node_id SET is_cycle USING cycle_path
```

PostgreSQL automatically maintains the equivalent of:

- **`cycle_path`:** path of the key values declared after `CYCLE`.
- **`is_cycle`:** flags a row if the key value reappears on the path currently being expanded.
- Built-in suppression so cycle-closing rows are not expanded further.

For a single `INTEGER` key, the path is an array of those key values. When tracking multiple columns, the path holds composite/row values.

### 7.2. What appears in the result?

The query can **still return the cycle-closing row** with `is_cycle=true`, such as a path ending with a repeated ID 2. The crucial part is that it **stops generating infinite steps beyond that row**.

If you want only acyclic paths in the final output:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

If you need to investigate faulty edges, **do not filter out `is_cycle=true`**; return the path or extra edge columns so operators can see where the path looped.

### 7.3. Which key should CYCLE track?

`CYCLE node_id` checks whether **`node_id` repeats on the path**. In multi-tenant systems, an ID may only be unique **within a tenant**, meaning two tenants could both have entity ID 17.

In that case:

```sql
-- Conceptual illustration with tenant_id and node_id columns
-- actually present in the recursive CTE:
-- CYCLE tenant_id, node_id SET is_cycle USING cycle_path
```

Checking the `(tenant_id, node_id)` pair behaves differently from checking `node_id` alone. However, true multi-tenant safety also requires **joining edges on `tenant_id`** and **filtering by authorized scope**; changing the `CYCLE` key alone does not provide tenant isolation.

### 7.4. Does CYCLE automatically find all cycles in the graph?

No. It detects cycles **that the query actually reaches from the anchor**. If a graph component is unreachable from root 1, cycles inside that component **do not appear** when traversing from 1.

Auditing the whole graph requires starting from multiple nodes or using a dedicated algorithm. Using **every node as an anchor** can expand many paths and report the same cycle multiple times, so assess complexity before running that in production.

### 7.5. Distinguishing CYCLE from data constraints

`CYCLE` is a mechanism **within a read/traversal query**, not a constraint stopping users from inserting cycle-forming edges.

For example:

```sql
INSERT INTO graph_lab.edges (from_id, to_id)
VALUES (6, 1);
```

This command succeeds if it violates no PK/FK, even though it introduces another cycle in the graph. A subsequent `CYCLE` query can **detect** the cyclic path, but it does not undo the INSERT.

If business rules dictate that **cycles must never be created**, implement write-time validation with appropriate locking/concurrency controls or an invariant-preserving data model. Do not replace write integrity with a periodic reporting query.

To keep the remaining examples on the initial dataset, **do not run `INSERT (6,1)`** unless you intentionally test it and restore the lab data afterward.

## 8. SEARCH BREADTH FIRST: Generating a Breadth-First Order Key

PostgreSQL 14+ supports `SEARCH` in recursive CTEs. Example combining cycle detection with BFS ordering:

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    bfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY bfs_order, cycle_path;
```

Reading the clause:

```sql
SEARCH BREADTH FIRST BY node_id SET bfs_order
```

- `SEARCH` asks PostgreSQL to generate a **computed ordering column** for the recursive query.
- `BREADTH FIRST` specifies ordering by **level/depth**, then by the keys listed after `BY`.
- `BY node_id` defines the key used to order nodes within each level, per PostgreSQL's semantics.
- `SET bfs_order` exposes column `bfs_order` for the **outer SELECT's `ORDER BY`**.

**Do not assume `bfs_order` is a sequential integer 1, 2, 3...**. It is a PostgreSQL-generated ordering type meant for comparison and sorting. When sending results over an API, use `depth` and business keys rather than relying on the internal string representation of this column.

### 8.1. Why might ORDER BY bfs_order not be a completely unique order?

In the sample graph, node 4 is reached via two paths at the **same depth**:

```text
1 → 2 → 4
1 → 3 → 4
```

If the BFS search key includes only `node_id`, two rows at the same depth with the same `node_id` can have **equal `bfs_order` keys**. Because the lab also includes `CYCLE` with `cycle_path`, the example sorts by:

```sql
ORDER BY bfs_order, cycle_path
```

to break ties between two paths reaching the same vertex. Never rely on incidental tie order when stable pagination or exports are required.

### 8.2. Manual BFS sorting without SEARCH

For PostgreSQL 13 or when explicit control is preferred:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT 1::INTEGER, 0::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.depth + 1, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT node_id, depth, path
FROM walk
ORDER BY depth ASC, path ASC;
```

Here `depth` creates BFS levels; `path` acts as a stable tie-breaker within each level and distinguishes multiple paths to a node. This provides **BFS-like display order**, not a directive forcing the executor to process nodes with a procedural queue.

### 8.3. Does BFS automatically find shortest paths?

When all edges have equal cost and the problem is **minimum step count** from one root, BFS is the relevant approach. However, `SEARCH BREADTH FIRST` **only generates an ordering column**—it neither deduplicates nodes nor solves every shortest-path problem automatically.

On a graph with multiple paths to the same vertex, you need an extra step picking the **minimum depth** per node after safe traversal:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT 1::INTEGER, 0::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.depth + 1, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    MIN(depth) AS min_hops
FROM walk
GROUP BY node_id
ORDER BY min_hops, node_id;
```

The result gives the **minimum number of edges** among simple paths from root 1 to each node. Still, enumerating all simple paths can explode with graph size; do not treat this query as an optimal shortest-path algorithm for very large networks. With non-uniform edge weights, `MIN(depth)` is **not** the lowest total-cost path.

## 9. SEARCH DEPTH FIRST: Generating a Depth-First Order Key

To sort in DFS order:

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    dfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY dfs_order;
```

`SEARCH DEPTH FIRST BY node_id SET dfs_order` produces a **path-structured ordering key**. With `ORDER BY dfs_order`, rows are presented following each branch deeply in order of the declared key.

### 9.1. CYCLE path can also serve as a DFS sort key

When you need both **DFS ordering and cycle detection on the same `node_id` key**, declaring both:

```sql
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET is_cycle USING cycle_path
```

can maintain two nearly equivalent path structures, causing extra work. In many cases, simply using:

```sql
CYCLE node_id SET is_cycle USING cycle_path
```

and:

```sql
ORDER BY cycle_path
```

suffices to get **DFS-style display order** along with cycle protection.

Conversely, combining **`SEARCH BREADTH FIRST` + `CYCLE`** makes clearer sense because one creates a **depth/level** key while the other tracks **paths and repeated vertices**.

### 9.2. Manual DFS sorting with a path array

When compatibility with PostgreSQL 13 or older is required:

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    array_length(path, 1) - 1 AS depth,
    path
FROM walk
ORDER BY path;
```

The path array holds vertex IDs in traversal order. `ORDER BY path` compares element by element from the start, making it suitable for listing branches in ID order.

**Note:** sorting by ID path is not necessarily the same as sorting by display `label`. If business rules call for ordering siblings by `label`, define an appropriate sort key or use `SEARCH ... BY label` with data and join conditions designed to expose the label at every step.

## 10. SEARCH Does Not Change Recursive Execution Order

This is the most commonly misunderstood point of this lesson.

### 10.1. Distinguishing three orders

| Order | Determined by | Is it a guaranteed API? |
|---|---|---|
| **Order in which the executor evaluates recursive passes** | Recursive CTE evaluation mechanism and PostgreSQL plan | Should not be relied upon for presentation |
| **Computed ordering key** | `SEARCH BREADTH FIRST/DEPTH FIRST BY ... SET ...` or manually built `depth/path` | Can be used to sort results |
| **Order of rows returned to the client** | `ORDER BY` on the final SELECT | This is where output order is declared |

Therefore, writing:

```sql
WITH RECURSIVE ...
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT * FROM walk;
```

**does not guarantee** the client sees DFS order unless you also write:

```sql
ORDER BY dfs_order;
```

`SEARCH` creates **a column to sort by**; it does not treat the result as already sorted.

### 10.2. Can ORDER BY inside the recursive term replace SEARCH?

Do not rely on `ORDER BY` inside the recursive branch to "control" the exact visitation sequence across every pass. The optimizer and relational semantics can yield unexpected results. To output trees in BFS/DFS order, **build an explicit tracking key** and use `ORDER BY` in the final outer query.

### 10.3. Break ties for fully deterministic order

In a tree where siblings have unique sort keys, `SEARCH ... BY sibling_order, node_id` creates a useful order. In a **graph** with multiple paths to the same node, rows sharing node and level may need **path** as a secondary key.

If two rows have identical `ORDER BY` keys, SQL makes no guarantee about which comes first. For pagination, exports, or repeatable checks, design a unique tie-breaking key for the **result row itself** (typically including path, not just `node_id`).

## 11. Combining SEARCH and CYCLE: Full Reporting Pattern

A helpful pattern when operators want to view a graph from the root **level by level**, see paths, and identify cycle-causing rows:

```sql
WITH RECURSIVE dependency_walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM dependency_walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING path
SELECT
    node_id,
    depth,
    is_cycle,
    path,
    bfs_order
FROM dependency_walk
ORDER BY bfs_order, path;
```

Explanation:

1. The anchor starts at node 1 at depth 0.
2. The recursive term follows outgoing edges from the current node.
3. `SEARCH BREADTH FIRST` generates a level-oriented sort key.
4. `CYCLE node_id` detects vertices already seen on the current path and stops expanding looping rows.
5. The final `SELECT` explicitly applies `ORDER BY bfs_order, path`.

**Do not equate** `depth` with `bfs_order`: `depth` is simply the **edge count from the root**, whereas `bfs_order` is a PostgreSQL-generated **ordering key combining depth and BY expressions**.

### 11.1. Reporting cycle-closing edges

Since the recursive CTE tracks `node_id` as the destination vertex, to know which edge caused the loop you can also carry the **previous vertex**:

```sql
WITH RECURSIVE walk(node_id, parent_id, depth) AS (
    SELECT
        1::INTEGER AS node_id,
        NULL::INTEGER AS parent_id,
        0::INTEGER AS depth

    UNION ALL

    SELECT
        e.to_id AS node_id,
        w.node_id AS parent_id,
        w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT
    parent_id AS from_id,
    node_id AS to_id,
    depth,
    path
FROM walk
WHERE is_cycle
ORDER BY path;
```

The output shows cycle-closing edges such as `5 → 2`, `2 → 4` on another path, and `8 → 8`. A single cycle may be detected at different edges depending on the starting point and path taken.

### 11.2. Finding all nodes without showing cycle rows

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT DISTINCT node_id
FROM walk
WHERE NOT is_cycle
ORDER BY node_id;
```

The query returns each reachable node once, but **internally it still builds multiple paths** before `DISTINCT` deduplicates outside. If the goal is pure reachability and performance on large graphs, the `UNION` approach keeping only `node_id` in Section 4 is often far better suited.

## 12. Choosing a Cycle Key That Matches Business Semantics

What counts as "returning to the same vertex" depends on the model.

### 12.1. Global ID or per-tenant ID?

If `node_id` is globally unique, `CYCLE node_id` suffices. If data is partitioned by `tenant_id` and `local_id` is unique only within a tenant, the identifying key is the **pair `(tenant_id, local_id)`**.

Example of a recursive CTE carrying both `tenant_id` and `local_id`:

```sql
-- Tail of a recursive CTE with two identifying columns:
-- CYCLE tenant_id, local_id SET is_cycle USING path
```

However, **before that**, the join must also match on tenant:

```sql
-- Example of a proper JOIN condition for a multi-tenant model:
-- ON e.tenant_id = w.tenant_id
-- AND e.from_local_id = w.local_id
```

Forgetting the tenant condition in the JOIN could wrongly connect another tenant's node ID 12 into the current path, producing both wrong reports and data-leak risks.

### 12.2. Nodes with time-varying attributes

Do not use `label`, `status`, or `display_name` as the cycle-detection key if two valid nodes can share a name or if names can change. Use a **stable identifying key**.

If the model intentionally treats two versions of the same entity as **two distinct nodes**, include the version identifier in the key. Otherwise, `CYCLE id` will treat returning to the same ID as a loop even when the version differs.

### 12.3. Edge cycles vs. vertex cycles

Most dependency graphs want to detect **vertex repetition**: a node already on the path. Some specialized problems allow revisiting a vertex while forbidding reusing **the same edge**. Those two semantics differ.

For trail problems (no repeated edges), you must store a list of **edge identifiers** in the path or write a dedicated query; `CYCLE node_id` prunes paths earlier than a no-repeated-edge rule.

## 13. Organizational Trees: Easy to Query, Yet Full of Traps

A common hierarchical model uses a `parent_id` column:

```sql
CREATE TABLE graph_lab.categories (
    category_id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES graph_lab.categories(category_id),
    name TEXT NOT NULL
);

INSERT INTO graph_lab.categories
    (category_id, parent_id, name)
VALUES
    (10, NULL, 'All products'),
    (20, 10, 'Electronics'),
    (30, 10, 'Home'),
    (40, 20, 'Computers'),
    (50, 40, 'Laptops');
```

### 13.1. Querying the hierarchical tree

```sql
WITH RECURSIVE category_tree(
    category_id, parent_id, name, depth
) AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        0::INTEGER
    FROM graph_lab.categories AS c
    WHERE c.category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        t.depth + 1
    FROM category_tree AS t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET dfs_order
CYCLE category_id SET is_cycle USING path
SELECT
    category_id,
    parent_id,
    name,
    depth,
    is_cycle,
    path
FROM category_tree
ORDER BY dfs_order;
```

The result starts at category 10 and walks its subcategories, sorted by the DFS key. With a valid tree model, no row has `is_cycle=true`.

### 13.2. Why doesn't a FOREIGN KEY forbid all cycles?

`parent_id REFERENCES categories(category_id)` only requires **the parent to exist**. It does not guarantee the structure remains a tree.

For example, if root 10's parent is updated to node 50:

```sql
-- Illustrates an operation THAT CAN CREATE A CYCLE; do not run in the lab:
-- UPDATE graph_lab.categories
-- SET parent_id = 50
-- WHERE category_id = 10;
```

All FKs remain satisfied because node 50 exists, yet a cycle forms:

```text
10 → 20 → 40 → 50 → 10
```

A query starting **from nodes with `parent_id IS NULL`** could **completely miss** the cyclic component if no true root remains after the update. When auditing corrupted hierarchies, pick anchors and checks carefully rather than assuming "no cycle seen from roots" means the entire table is acyclic.

### 13.3. Preventing cycle-forming updates requires handling concurrency

Before setting `parent_id=new_parent`, an application might check that the proposed parent **is not a descendant** of the node being moved. However, two concurrent transactions can both read stale data and apply updates that together form a cycle.

To guarantee an "acyclic" invariant in production, design:

- Locking/serialization scope for hierarchy changes.
- Appropriate transactions and isolation levels.
- Recursive ancestry checks under consistent data views.
- Concurrency error/retry handling.
- Audits and remediation if anomalous data is detected.

A naive trigger running `SELECT EXISTS` **is not automatically safe against race conditions**. `SEARCH` and `CYCLE` serve reading/observation, not write-time concurrency management.

## 14. Depth, Paths, and Displaying Tree Structures

Some UIs need to render:

```text
All products
  Electronics
    Computers
      Laptops
  Home
```

We can use `depth` for indentation and path/`SEARCH` for ordering:

```sql
WITH RECURSIVE t(category_id, parent_id, name, depth) AS (
    SELECT
        category_id, parent_id, name, 0::INTEGER
    FROM graph_lab.categories
    WHERE category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        t.depth + 1
    FROM t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET traversal_order
CYCLE category_id SET is_cycle USING path
SELECT
    repeat('  ', depth) || name AS tree_line,
    category_id,
    depth,
    is_cycle
FROM t
WHERE NOT is_cycle
ORDER BY traversal_order;
```

**Note:** indentation spaces are purely for formatting; applications should consume `category_id`, `parent_id`, and `depth` directly for interactive trees. Never parse leading space counts to infer parent–child links.

### 14.1. Limiting depth strictly for display

A UI might only load three levels:

```sql
WITH RECURSIVE t(category_id, depth) AS (
    SELECT 10::INTEGER, 0::INTEGER
    UNION ALL
    SELECT c.category_id, t.depth + 1
    FROM t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
    WHERE t.depth < 2
)
CYCLE category_id SET is_cycle USING path
SELECT category_id, depth, is_cycle
FROM t
ORDER BY path;
```

The condition `t.depth < 2` produces root depth 0, child depth 1, and grandchild depth 2. It **does not prove the actual tree is at most two levels deep**—it only truncates data for display.

## 15. Detecting Cycles Across the Entire Graph: Scope and Cost

When auditing data quality, the question may be:

> "Does any cycle exist anywhere in the edges table, even in components disconnected from node 1?"

Traversing from a single anchor cannot prove the negative across the whole graph.

### 15.1. Using every vertex as an anchor

In a small lab, you can start from all nodes:

```sql
WITH RECURSIVE walks(start_node, node_id) AS (
    SELECT
        n.node_id AS start_node,
        n.node_id AS node_id
    FROM graph_lab.nodes AS n

    UNION ALL

    SELECT
        w.start_node,
        e.to_id
    FROM walks AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT DISTINCT
    start_node,
    node_id AS repeated_node,
    path
FROM walks
WHERE is_cycle
ORDER BY start_node, path;
```

**Because every node is an anchor**, the cycle `8 → 8` would still be detected even if the branch leading to 8 were disconnected from node 1 in another dataset. However:

- One cycle can be discovered from multiple `start_node`s.
- One cycle can be reported at multiple loop-closing points.
- Intermediate row counts can grow dramatically in graphs with many paths.
- `DISTINCT` on `start_node, node_id, path` removes only **identical rows**, without canonicalizing different starting points/traversals of the same cycle into one unique cycle record.

Thus, this query is suitable for **demonstrating audits on small datasets**, not as an optimal cycle-enumeration algorithm for huge production graphs.

### 15.2. Checking only whether any cycle exists

At small scale, you can wrap the query:

```sql
WITH RECURSIVE walks(start_node, node_id) AS (
    SELECT node_id, node_id FROM graph_lab.nodes
    UNION ALL
    SELECT w.start_node, e.to_id
    FROM walks AS w
    JOIN graph_lab.edges AS e
      ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT EXISTS (
    SELECT 1
    FROM walks
    WHERE is_cycle
) AS has_any_cycle;
```

On the lab dataset, the result is `true`. Still, **`EXISTS` does not guarantee the plan skips all expensive work** in every context; the complexity of path expansion must still be weighed.

On huge graphs, specialized algorithms, closure tables, or incremental checks tailored to system requirements may be more appropriate.

## 16. Safety Limits and Handling Long-Running Queries

A bug in a recursive CTE can consume heavy CPU, memory, and I/O. Never ship a query to production just because "the demo query ran fast".

### 16.1. Three layers of protection

| Safeguard | Effect | Limitation |
|---|---|---|
| **Cycle detection** (`CYCLE` or path check) | Stops infinite expansion from repeated vertices on a path | Simple path counts can still explode |
| **Depth limit** (`depth < N`) | Caps paths longer than N | May omit valid deeper results |
| **Timeout / execution budget** | Aborts queries running too long | Does not fix the underlying algorithm and cancels the statement |

Additionally, scope input data by tenant, edge type, time range, or an explicit root list whenever business rules allow.

### 16.2. statement_timeout for test sessions

When permitted to change session parameters:

```sql
-- Practice session example; not a universal preset for all systems.
SET statement_timeout = '5s';

-- Run a WITH RECURSIVE query that already has CYCLE or a depth limit.

RESET statement_timeout;
```

If a query exceeds the timeout, PostgreSQL aborts the statement. If running inside a transaction that has errored, handle transaction rollback before proceeding. Never use timeouts to legitimize a query lacking proper cycle controls.

### 16.3. Why an outer LIMIT is not a reliable cycle breaker

In some PostgreSQL queries, a CTE may be pulled lazily on demand, so:

```sql
-- UNSAFE as a termination strategy:
-- WITH RECURSIVE walk AS (...)
-- SELECT * FROM walk LIMIT 10;
```

might happen to return ten rows before generating everything. However, adding `ORDER BY`, `JOIN`, or operations requiring the full result set can force PostgreSQL to evaluate much or all of the CTE before returning ten rows.

**Never rely on an outer `LIMIT` to guarantee recursion termination in production.** Control cycles and depth inside the recursive definition itself.

### 16.4. Long paths and the cost of path arrays

When each row carries a full path, `path || node_id` creates ever-longer arrays. Across many paths, the system may retain and compare large numbers of path arrays:

- Increases memory and CPU usage.
- Increases sorting cost for `ORDER BY path`.
- Can produce large result sets even when the node count is modest.
- Can trigger temporary file spills and I/O.

If you only need reachable nodes, `UNION` on `node_id` alone can save substantial resources compared to enumerating every path. If you need shortest paths, consider dedicated algorithms rather than generating all paths.

## 17. Indexes and Execution Plans

### 17.1. Indexes on the edge side used for expansion

Recursive queries commonly execute:

```sql
JOIN graph_lab.edges AS e
  ON e.from_id = w.node_id
```

The `PRIMARY KEY (from_id, to_id)` on the lab table already creates a B-tree index with `from_id` as the **leading column**, which typically helps locate outgoing edges from a node.

If the application also traverses in reverse:

```sql
JOIN graph_lab.edges AS e
  ON e.to_id = w.node_id
```

consider a separate index:

```sql
CREATE INDEX edges_to_id_idx
ON graph_lab.edges (to_id);
```

However, indexes carry storage and write overhead; on a ten-edge lab graph, the planner may pick a sequential scan. Do not take that as proof an index is useless on real data.

### 17.2. EXPLAIN on a recursive CTE

```sql
EXPLAIN
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, depth, is_cycle
FROM walk
ORDER BY path;
```

The plan may include:

- `Recursive Union`: the node driving recursive evaluation.
- `WorkTable Scan`: reads working-table rows during each iteration.
- `Index Scan`/`Hash Join`/`Nested Loop`/`Seq Scan` on the edges table, depending on stats.
- `Sort`: orders results by path or search-order key.

Exact plans change with statistics, data size, indexes, and PostgreSQL version. Do not infer from the name `Recursive Union` that a query is cycle-safe; inspect the **termination conditions**, `CYCLE`, or path logic.

### 17.3. EXPLAIN ANALYZE requires a safe query

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT COUNT(*)
FROM walk;
```

`EXPLAIN ANALYZE` **actually executes the statement**. On this small example with `CYCLE`, it is fine for practice; for a query not guaranteed to terminate, never run `ANALYZE` just to view the plan.

Metrics to watch:

- Total rows/paths generated.
- Loop count on `WorkTable Scan`.
- Estimated vs. actual rows.
- Whether sorts or temp-file spills occur.
- Per-pass time and row expansion factor across JOINs.

### 17.4. Optimize for the real requirement, not one generic trick

Ask:

- Do we need **every path** or just **each node once**?
- Should cycles be **flagged** or should looping edges simply be omitted?
- Is **BFS/DFS ordering** required, or just a list of IDs?
- Can we filter by tenant/edge type **before and inside recursion**?
- Do we need **reverse** or **forward** traversal?
- Can depth legitimately be capped per requirements?

Clarifying the problem definition usually impacts performance far more than adding an index or tweaking `ORDER BY`.

## 18. Recursion Under MVCC and Concurrent Data Changes

A single `WITH RECURSIVE` query under normal `READ COMMITTED` isolation observes data from its statement snapshot. If another transaction modifies edges concurrently, the query does not "jump" across intermediate committed states mid-statement the way an application loop issuing separate SELECTs would.

However:

- Two **separate SELECT statements** can observe different snapshots.
- A cycle check run before an update does not prove the graph stays acyclic after the update.
- A naive validate-then-update workflow can suffer race conditions if concurrent writes are uncoordinated.
- On a replica, data may lag behind the primary; checking for cycles on a replica does not protect writes on the primary.

When the goal is a **data invariant**, focus on transactional write controls, locking, and concurrency protocols—not just traversal queries.

## 19. Common Mistakes

**1. "WITH RECURSIVE stops automatically when seeing an old node."** False. With `UNION ALL` and no stopping condition, a cycle can produce rows indefinitely.

**2. "Simply changing UNION ALL to UNION fixes all cycles."** False if the row state includes `depth`, `path`, or any column that changes on each pass.

**3. "A node appearing in two paths means there is a cycle."** No. A DAG can have multiple paths to one node without any cycle.

**4. "CYCLE removes all cycle-related rows from the result."** No. The **cycle-closing** row can still appear with `is_cycle=true`, though it is not expanded further.

**5. "WHERE NOT is_cycle in the final SELECT prevents infinite loops."** Incorrect. `CYCLE` or conditions in the recursive term control expansion; filtering at the end only controls **display**.

**6. "SEARCH DEPTH FIRST forces PostgreSQL to execute recursion in DFS order."** No. It generates a **sort-order column**; `ORDER BY` is required to present DFS order.

**7. "A recursive query without ORDER BY always returns BFS order."** Output order is never guaranteed, especially within a level.

**8. "BFS returns each node exactly once."** Not automatically. If tracking paths and two paths reach the same node, the result can contain multiple rows for that node.

**9. "CYCLE always checks the entire graph."** No. It checks paths reachable from the chosen anchor; unreachable components are not traversed.

**10. "A PRIMARY KEY on edges prevents cycles."** No. It only prevents duplicate copies of the exact same edge per table design.

**11. "FOREIGN KEY parent_id guarantees a valid tree."** No. An FK ensures the parent exists, not that cycles are absent.

**12. "Putting LIMIT 10 outside a recursive CTE is a safe stopping mechanism."** No. An outer sort, join, or aggregate can force evaluating much or all of the recursion.

**13. "A depth limit of 5 detects every cycle."** No. Deeper cycles are truncated before being reached.

**14. "CYCLE id is sufficient in any multi-tenant system."** Not if IDs are unique only within a tenant; keys and JOINs must include tenant scope.

**15. "ORDER BY depth, node_id always distinguishes every row in a graph."** Not when a node has multiple paths at the same depth.

**16. "Path is a global ID of a node."** No. A path is a **sequence of vertices along one expansion**; the same node can have many paths.

**17. "Enabling SEARCH improves shortest-path algorithms."** No. `SEARCH` builds a sort key; shortest-path problems require explicit logic and complexity analysis.

**18. "Sorting by a path array always means sorting by label."** No. If the path contains IDs, it sorts by ID.

**19. "Using all nodes as anchors is always optimal for cycle detection."** No. Path counts can explode and a single cycle can be reported repeatedly.

**20. "A query finding no cycles guarantees another transaction won't create one next."** No. Checking and writing need proper concurrency protocols.

**21. "ORDER BY in the recursive term can replace the final ORDER BY."** Never rely on that to guarantee returned row order.

**22. "COUNT(*) on walk equals the number of unique nodes."** Wrong whenever the query generates multiple paths to the same vertex.

**23. "Any key with NULL works cleanly with = ANY(path)."** No. Three-valued logic requires dedicated handling.

**24. "Carrying path has zero cost."** No. Long paths and heavy branching increase memory, CPU, and sort costs.

## 20. Practice Exercises with Answers

### Exercise 1 — Identifying cycles

Given edges:

```text
1 -> 2
1 -> 3
2 -> 4
3 -> 4
4 -> 5
5 -> 2
```

**Question:** which cases are cycles, and which are merely multiple paths to the same node?

**Answer:** `2 → 4 → 5 → 2` is a cycle. `1 → 2 → 4` and `1 → 3 → 4` simply show two paths reaching 4, **without forming a loop**.

### Exercise 2 — Why doesn't UNION with depth stop?

```sql
WITH RECURSIVE w(node_id, depth) AS (
    SELECT 2, 0
    UNION
    SELECT e.to_id, w.depth + 1
    FROM w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
SELECT * FROM w;
```

**Answer:** In cycle `2 → 4 → 5 → 2`, node 2 is returned again with `depth=3`, which differs from `(2,0)`. `UNION` deduplicates **across the entire row**, so it does not prevent generating new rows at increasing depths. **Do not run this query as written** on a cyclic graph.

### Exercise 3 — Listing reachable nodes once each

**Requirement:** from node 1, return only the set of node IDs, without paths.

**Answer:**

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_id
    FROM reachable r
    JOIN graph_lab.edges e ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Result: `1,2,3,4,5,6,7,8`.

### Exercise 4 — Excluding cycle-closing paths

**Requirement:** from node 1, carry an integer path array and do not append nodes already present.

**Answer:**

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk w
    JOIN graph_lab.edges e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT node_id, path
FROM walk
ORDER BY path;
```

A node can still appear in two different rows if two distinct paths lead to it; repetition is blocked **per path**.

### Exercise 5 — Flagging cycles while still seeing the closing edge

**Requirement:** inspect cyclic paths without expanding further after closing the loop.

**Answer (PostgreSQL 14+):**

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, path
FROM walk
WHERE is_cycle
ORDER BY path;
```

Rows with `is_cycle=true` mark occurrences where a node repeated along the traversed path. They are not expanded further.

### Exercise 6 — BFS ordering

**Requirement:** PostgreSQL 14+, retrieve all walk rows and display breadth-first.

**Answer:**

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING path
SELECT node_id, depth, is_cycle, path
FROM walk
ORDER BY bfs_order, path;
```

`SEARCH` creates the ordering key; the final `ORDER BY` actually sorts the result.

### Exercise 7 — DFS ordering

**Requirement:** can the path produced by `CYCLE` itself be used for DFS-like presentation?

**Answer:** Yes. Use:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, path, is_cycle
FROM walk
ORDER BY path;
```

Sorting by path corresponds to descending branch-by-branch on `node_id`, so adding `SEARCH DEPTH FIRST` is not strictly required once you already have the path.

### Exercise 8 — Are there really only 8 result rows?

A `UNION ALL` query tracking paths with cycle checks is run from node 1 on an 8-vertex graph.

**Question:** must `COUNT(*)` equal 8?

**Answer:** No. A node like 4 is reached by multiple paths; a path-retaining result can have **more rows than vertices**. Use `COUNT(DISTINCT node_id)` to count unique destination vertices, or use a `UNION` query with only `node_id` if paths are not needed.

### Exercise 9 — Root cannot see the cycle

**Scenario:** a cycle exists in a graph component unreachable from root 1. Running `CYCLE` starting from node 1 yields no `is_cycle=true` rows.

**Answer:** You cannot conclude the entire graph is acyclic; it only proves the query **detected no cycles along paths expanded from root 1**. Remaining components must be traversed or a full-graph check used.

### Exercise 10 — FOREIGN KEY alone cannot forbid cycles

An employees table has `manager_id REFERENCES employees(id)`, yet A manages B and B manages A.

**Answer:** The FK only ensures the referenced manager exists. The A↔B pair still satisfies the FK while forming a cycle. Ancestor/descendant validation with concurrency control is required during updates.

### Exercise 11 — Comparing two clauses

```sql
SEARCH BREADTH FIRST BY node_id SET seq
```

and:

```sql
SEARCH DEPTH FIRST BY node_id SET seq
```

**Answer:** Both **generate an ordering key**, differing in whether the key prioritizes level-by-level or branch-deep ordering. Both still require `ORDER BY seq` (plus tie-breakers if needed) in the final query to guarantee presentation order.

### Exercise 12 — Multi-tenant

**Scenario:** the same node ID 9 can appear in two different tenants.

**Answer:** Do not use `CYCLE node_id` alone if records from different tenants represent distinct entities in the same query. Consider `CYCLE tenant_id, node_id` and join edges by `tenant_id`. Add tenant filters and authorization checks; `CYCLE` does not replace authorization.

### Exercise 13 — Does a depth limit replace cycle detection?

```sql
WHERE w.depth < 4
```

**Answer:** This cap prevents generating paths deeper than the threshold, but can miss cycles that only appear after step 4. For safe and meaningful queries, also use `CYCLE`/path checks; a depth cap is a resource/product bound, not proof of acyclicity.

### Exercise 14 — Optimizing JOIN direction

**Requirement:** a query frequently finds nodes reachable from node A via `edges.from_id = current_node`. The table has `PRIMARY KEY (from_id,to_id)`.

**Answer:** The primary key already creates a B-tree index leading with `from_id`, supporting outgoing-edge lookups. If reverse queries on `to_id` are also needed, consider a separate index on `to_id` after measuring the workload.

### Exercise 15 — Why isn't checking before INSERT enough?

Two transactions both check "if I add this edge, no cycle is formed" and each sees an acyclic result on its own snapshot before adding one edge.

**Answer:** Both changes can combine to form a cycle even though each prior check saw a valid state. Proper transaction/concurrency protocols (locking/serialization/retries) are required to enforce an acyclic invariant.

## 21. Workflow for Choosing a Graph Solution in PostgreSQL

Before writing a recursive query in a real project:

1. **Identify the relationship model:** single-parent tree, DAG, directed graph, or bidirectional relationship?
2. **Identify edge direction:** dependent-to-dependency or parent-to-child? Join on `from_id` or `to_id`?
3. **Define access scope:** tenant, organization, edge types, statuses, effective dates.
4. **Define the output unit:** each node once, each path once, cycle-closing edges, or a boolean has-cycle check?
5. **Choose anchors:** one root, multiple roots, or all nodes; which components will be covered?
6. **Choose the cycle-detection key:** single ID, tenant-scoped ID, or multi-column key; prefer non-NULL and stable keys.
7. **Control recursion:** `CYCLE` on PostgreSQL 14+, path arrays on older versions, or ID-only `UNION` for reachability.
8. **Choose display ordering:** BFS or DFS; use `SEARCH`/`depth`/`path` and a final `ORDER BY`.
9. **Bound volume:** intentional depth cap, early edge filtering, timeouts, and estimated path/result sizes.
10. **Optimize JOINs:** indexes on `edges(from_id)` or `edges(to_id)` matching direction, statistics, and `EXPLAIN`.
11. **Evaluate concurrency:** read-time cycle queries do not prevent concurrent writers from introducing cycles; protect invariants on the write path.
12. **Test edge cases:** self-loops, multi-edge cycles, multi-parent DAGs, disconnected components, missing roots, isolated nodes, multi-tenancy, and large data.
13. **Check server version:** use `SEARCH/CYCLE` only on PostgreSQL 14+, and path arrays when older compatibility is needed.
14. **Separate technical results from business meaning:** a "reachable" path is not automatically the shortest path, a valid dependency, or authorized for access.

## 22. Summary

In PostgreSQL, **`WITH RECURSIVE`** is the tool for traversing hierarchical and graph structures, yet it **neither prevents cycles automatically nor guarantees output order** for applications.

Points to remember:

- **`UNION ALL`** keeps all generated rows; on cyclic graphs it requires stopping conditions or cycle control. **`UNION`** deduplicates across all columns, which fits ID-only reachability state but does not fix states with ever-changing `depth`/`path`.
- **Path array + `ANY`** detects vertices already seen on the **current path**, preserving distinct routes to the same node without infinite looping.
- **`CYCLE node_id SET is_cycle USING path`** in PostgreSQL 14+ automatically flags cycle-closing rows, provides the path, and stops expanding looping branches.
- **`SEARCH BREADTH FIRST` and `SEARCH DEPTH FIRST`** generate **ordering keys** for BFS/DFS; to display results in order, you must use **`ORDER BY`** in the final SELECT.
- **Path-local cycle detection is not global node deduplication**, does not detect cycles in unreachable components, and does not prevent `INSERT`/`UPDATE` from introducing cycles.
- **Depth, path count, tenant scope, indexes, and snapshots** are critical operational factors. Even an acyclic graph can produce enormous numbers of paths.

**Final rule:** before picking `SEARCH`, `CYCLE`, or `UNION`, clearly define **where traversal starts, whether you need vertices or paths, which key defines a cycle, and whether display order is level-by-level or branch-by-branch**. Once those four decisions are clear, a recursive query becomes both semantically accurate and operationally controllable.

### PostgreSQL Reference Documentation

- [WITH Queries, Recursive Queries, Search Order, and Cycle Detection](https://www.postgresql.org/docs/current/queries-with.html).
- [SELECT and WITH Syntax](https://www.postgresql.org/docs/current/sql-select.html).
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html).
- [Row and Array Comparisons: ANY / ALL](https://www.postgresql.org/docs/current/functions-comparisons.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
