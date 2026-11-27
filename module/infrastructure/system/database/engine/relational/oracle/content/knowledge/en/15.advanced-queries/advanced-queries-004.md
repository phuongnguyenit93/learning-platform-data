# Recursive Subquery Factoring, SEARCH, and CYCLE

Much data in systems has a **parent–child** or **linked graph** structure: employees belonging to management tiers, categories having parent categories, folders containing subfolders, products having components, or a node connecting to many other nodes. When querying across multiple levels, writing a fixed JOIN for each level quickly becomes verbose and hard to maintain.

Oracle Database supports **recursive subquery factoring** in the `WITH` clause. A query block can reference its own name to expand results across multiple iterations. Two special clauses help control how results are read and protect the recursion:

- **`SEARCH`**: instructs Oracle to generate an ordering column representing **depth-first** or **breadth-first** traversal.
- **`CYCLE`**: specifies the columns used to detect a path returning to an ancestor, flags the cycle-causing row, and stops expansion from that row.

This lesson covers Oracle syntax, the anchor/recursive members, path construction, traversal order, cycle detection, and how to apply them to hierarchical trees as well as multi-path graphs.

## 1. What Is Recursive Subquery Factoring?

**Subquery factoring** lets you name a query block with `WITH`. That name can be referenced in the outer SELECT or in a subsequent query block. When the named query block references itself inside its own definition, it is called **recursive subquery factoring**.

Conceptual example:

```sql
WITH hierarchy AS (
    -- Anchor: starts from one or more root nodes
    SELECT ...

    UNION ALL

    -- Recursive member: finds next nodes from previous results
    SELECT ...
    FROM hierarchy ...
)
SELECT *
FROM hierarchy;
```

Each recursive iteration uses the rows generated in the previous iteration to find more rows. The process ends when the recursive member produces no new rows. Join conditions and data must be designed so that expansion terminates; for graphs with cycles, an appropriate cycle-detection strategy is required.

Oracle uses `WITH` syntax and **does not use the `RECURSIVE` keyword** found in some other database management systems.

## 2. Two Required Parts: Anchor Member and Recursive Member

A recursive subquery factoring block has two query blocks:

1. **Anchor member**: the first query, establishing the starting point. It does not reference the recursive query name.
2. **Recursive member**: the second query, referencing the recursive query name exactly once to generate the next step.

The two parts are combined with `UNION ALL`.

### 2.1. General syntax

```sql
WITH query_name (
    column_1,
    column_2,
    ...
) AS (
    -- Anchor member
    SELECT ...
    FROM ...
    WHERE start_condition

    UNION ALL

    -- Recursive member
    SELECT ...
    FROM query_name q
    JOIN source_table s
      ON recursive_condition
)
SELECT ...
FROM query_name;
```

The column alias list after the query name is mandatory in recursive subquery factoring. The column count and column order of the alias list must match the SELECT lists of both the anchor and recursive members; corresponding data types must be compatible.

### 2.2. How a recursive iteration works

```text
Iteration 0: Anchor produces node 1
                  |
                  v
Iteration 1: From node 1, find child nodes 2, 3
                  |
                  v
Iteration 2: From nodes 2, 3, find child nodes
                  |
                  v
Iteration 3: From new nodes, continue finding child nodes
                  |
                  v
             No new rows remain
                  |
                  v
             Recursion terminates
```

This is a conceptual model of result generations. The Oracle Optimizer decides the physical execution strategy; do not interpret this diagram as a guarantee that the database always writes or processes every row in the exact sequence shown here.

### 2.3. Why must UNION ALL be used?

Oracle requires combining the anchor member and recursive member with `UNION ALL`. Do not replace it with `UNION` merely to "deduplicate rows".

- `UNION ALL` preserves the rows produced by each iteration.
- `UNION` deduplicates and is not a permitted operator for combining the anchor and recursive member in Oracle's recursive subquery factoring syntax.
- If the graph has multiple paths to the same node, the same `NODE_ID` can appear multiple times in the result because each row represents a different path.

If business requirements call for only one row per node, you must explicitly decide how to choose a path or aggregate in the outer query; you cannot rely on changing `UNION ALL` to `UNION`.

## 3. Creating Graph Lab Data

To observe tree branches, multiple paths, and cycles, we use two tables:

- `LAB_ORG_NODES`: list of nodes.
- `LAB_ORG_EDGES`: directed edges from parent node to child node.

An edge model represents a general graph where one node can be reached from multiple parent nodes. It also makes it easy to introduce a test cycle without altering an employee/department table structure.

### 3.1. Creating the tables

Run in a practice schema you own:

```sql
CREATE TABLE lab_org_nodes (
    node_id   NUMBER PRIMARY KEY,
    node_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_org_edges (
    parent_id NUMBER NOT NULL,
    child_id  NUMBER NOT NULL,
    CONSTRAINT pk_lab_org_edges
        PRIMARY KEY (parent_id, child_id),
    CONSTRAINT fk_lab_edge_parent
        FOREIGN KEY (parent_id)
        REFERENCES lab_org_nodes (node_id),
    CONSTRAINT fk_lab_edge_child
        FOREIGN KEY (child_id)
        REFERENCES lab_org_nodes (node_id),
    CONSTRAINT ck_lab_edge_not_self
        CHECK (parent_id <> child_id)
);
```

The `CHECK` constraint only prevents a direct self-edge `n -> n`; it does not prevent longer cycles such as `1 -> 2 -> 3 -> 1`. `CYCLE` handles that kind of cycle in the query.

### 3.2. Inserting nodes

```sql
INSERT INTO lab_org_nodes VALUES (1, 'Root');
INSERT INTO lab_org_nodes VALUES (2, 'Platform');
INSERT INTO lab_org_nodes VALUES (3, 'Business');
INSERT INTO lab_org_nodes VALUES (4, 'Shared Service');
INSERT INTO lab_org_nodes VALUES (5, 'Delivery');
INSERT INTO lab_org_nodes VALUES (6, 'Operations');
INSERT INTO lab_org_nodes VALUES (7, 'Risk');

COMMIT;
```

### 3.3. Inserting initial edges

```sql
INSERT INTO lab_org_edges VALUES (1, 2);
INSERT INTO lab_org_edges VALUES (1, 3);
INSERT INTO lab_org_edges VALUES (2, 4);
INSERT INTO lab_org_edges VALUES (3, 4);
INSERT INTO lab_org_edges VALUES (4, 5);
INSERT INTO lab_org_edges VALUES (4, 6);
INSERT INTO lab_org_edges VALUES (6, 7);

COMMIT;
```

Initial graph:

```text
                 1 Root
                /      \
          2 Platform   3 Business
                \      /
              4 Shared Service
                /       \
          5 Delivery   6 Operations
                           |
                         7 Risk
```

Node `4` has two paths from the root node: `1 -> 2 -> 4` and `1 -> 3 -> 4`. This is a graph with multiple paths to a single node, **without a cycle yet**. Node 4 appearing twice during traversal does not mean a cycle was encountered.

## 4. Writing the First Recursive Query

We want to start at root node `1` and return node, name, depth, and path.

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    -- Anchor member: start at Root.
    SELECT
        n.node_id,
        n.node_name,
        0 AS depth_no,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000)) AS path_txt
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    -- Recursive member: step from current node to child nodes.
    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt
FROM org_walk
ORDER BY depth_no, node_id, path_txt;
```

### 4.1. Reading each part

**Alias list**:

```sql
org_walk (node_id, node_name, depth_no, path_txt)
```

Defines the names of the four columns that the outer query and recursive member can reference.

**Anchor member**:

```sql
SELECT n.node_id, n.node_name, 0, CAST(...)
FROM lab_org_nodes n
WHERE n.node_id = 1
```

Produces a single starting row at Root. The anchor must not reference `ORG_WALK`.

**Recursive member**:

```sql
FROM org_walk parent
JOIN lab_org_edges edge
  ON edge.parent_id = parent.node_id
JOIN lab_org_nodes child
  ON child.node_id = edge.child_id
```

For each current row, finds edges whose `PARENT_ID` matches that row's `NODE_ID`, then fetches the child node details.

**Depth**:

```sql
parent.depth_no + 1
```

The anchor starts at depth 0; each edge traversed increases depth by 1.

**Path**:

```sql
parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
```

Each iteration appends the new node ID to the path string. `CAST` ensures both branches have compatible character types and allocates space for the illustrative path. This is still `VARCHAR2(4000)` in SQL; for very long paths, design another storage/representation approach and account for data type limits.

### 4.2. Output can have multiple rows for the same NODE_ID

Shared Service (node 4) is reached via two paths:

```text
1 -> 2 -> 4
1 -> 3 -> 4
```

Because `UNION ALL` keeps both paths, the output has two rows with `NODE_ID = 4` and different `PATH_TXT` values. Nodes 5, 6, and 7 can also be generated from each path reaching node 4. This is the right behavior when the question is **list all paths**, not list distinct nodes.

## 5. SEARCH: Choosing Depth-First or Breadth-First Traversal Order

`SEARCH` is an extension of recursive subquery factoring to specify how row ordering is generated. Oracle provides:

- `SEARCH DEPTH FIRST BY ... SET ordering_column`
- `SEARCH BREADTH FIRST BY ... SET ordering_column`

The columns after `BY` must belong to the recursive query's alias list. `SET` declares the ordering column name automatically added by Oracle to the query name.

**SEARCH creates an ordering column; it does not automatically guarantee the row order returned to the client.** To see the declared order, the outer query must `ORDER BY` the column generated by `SET`.

### 5.1. DEPTH FIRST: go deep down one branch first

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    dfs_order
FROM org_walk
ORDER BY dfs_order;
```

`DEPTH FIRST` prioritizes descending into child nodes before returning to inspect sibling branches. `BY node_id` orders sibling nodes at the same level in ascending ID order. If a different order is desired, you can specify one or more suitable columns along with ASC/DESC and NULL ordering rules when columns are nullable.

### 5.2. BREADTH FIRST: process each tier first

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    bfs_order
FROM org_walk
ORDER BY bfs_order;
```

`BREADTH FIRST` outputs rows at the same depth before expanding deeper tiers. For the lab graph, visualize by tier:

| Depth | Node visits |
| ---: | --- |
| 0 | 1 |
| 1 | 2, 3 |
| 2 | 4 via 2; 4 via 3 |
| 3 | 5, 6 via each path to 4 |
| 4 | 7 via branch 6 |

Because node 4 has two paths, it appears twice at tier 2. `SEARCH BREADTH FIRST` does not remove duplicate-node paths; it simply generates an ordering so shallower rows come before deeper rows.

### 5.3. SEARCH does not replace ORDER BY

Example:

```sql
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT node_id, node_name
FROM org_walk
ORDER BY dfs_order;
```

If `ORDER BY dfs_order` is omitted, Oracle does not guarantee the client will receive rows in depth-first order. An execution plan or run that happens to return rows in the desired order is not a SQL contract.

The column name created by `SET`:

- Is automatically added by Oracle to the query name's column list.
- Can be referenced by the outer query in `SELECT` or `ORDER BY`.
- Must differ from the names declared in the alias list.
- Must differ from the cycle mark column name if `CYCLE` is also used.

## 6. CYCLE: Detecting Paths Returning to an Ancestor

In a graph, a **cycle** occurs when a path returns to a node already present in the current ancestor path itself. Example:

```text
1 -> 2 -> 4 -> 5 -> 1
```

Node 1 is encountered again while it is already an ancestor on the path. If expansion continues unchecked, the query can loop infinitely or hit recursion/resource limits.

`CYCLE` lets you specify the columns used to detect cycles and the column that flags the result:

```sql
CYCLE cycle_column [, cycle_column ...]
SET cycle_mark_column TO 'Y'
DEFAULT 'N'
```

In Oracle syntax:

- Columns after `CYCLE` must be in the query name's alias list.
- When a cycle-forming row is detected, its mark column receives `cycle_value`.
- Oracle **still returns the cycle-forming row** with the corresponding flag, but stops expanding child rows from that row.
- Non-cyclic branches continue to expand normally.
- If no cycle is detected, the mark column receives `no_cycle_value`.
- Both mark values must be single-byte character strings; for example, `'Y'` and `'N'`.

### 6.1. Adding an edge that creates a cycle

In the lab, add an edge from Delivery (5) back to Root (1):

```sql
INSERT INTO lab_org_edges VALUES (5, 1);
COMMIT;
```

The graph now has the path:

```text
1 Root
  -> 2 Platform
     -> 4 Shared Service
        -> 5 Delivery
           -> 1 Root   (returns to ancestor)
```

The foreign key constraint remains valid because both nodes 5 and 1 exist. `CHECK (parent_id <> child_id)` cannot prevent multi-edge cycles; that is the purpose of this `CYCLE` exercise.

### 6.2. Using CYCLE node_id

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    cycle_flag
FROM org_walk
ORDER BY dfs_order;
```

When the path `1 -> 2 -> 4 -> 5 -> 1` returns to node 1, the repeating row receives `CYCLE_FLAG = 'Y'`. Oracle keeps this row so the cycle can be observed, then stops expanding from the cycle-forming row. Other branches such as `4 -> 6 -> 7` continue to be traversed.

### 6.3. The cycle row still appears in the result

A common misconception is thinking `CYCLE` automatically removes the looping row. In fact, it **marks** the cycle-causing row. If a report wants only unmarked rows:

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT node_id, node_name, depth_no, path_txt
FROM org_walk
WHERE cycle_flag = 'N'
ORDER BY dfs_order;
```

Filtering `cycle_flag = 'N'` in the outer query only hides marked rows from the output. It does not alter cycle detection rules and is not a substitute for designing cycle prevention.

### 6.4. A cycle is per path, not a global node duplicate

In the initial graph, node 4 is reached via two branches:

```text
1 -> 2 -> 4
1 -> 3 -> 4
```

Node 4 appears in two different rows, yet **this is not a cycle**: along each individual path, node 4 has not appeared earlier in that path's own ancestor list.

`CYCLE node_id` compares against ancestor rows of the current path. It does not mean "if NODE_ID has ever appeared anywhere in the entire result, mark subsequent rows as a cycle".

This distinction matters when traversing a DAG (directed acyclic graph) with multiple paths to the same node. A node can be visited multiple times via valid paths without forming a cycle.

## 7. Which Columns to Choose in CYCLE?

The column list after `CYCLE` defines **what constitutes a repeated state**. `NODE_ID` alone is not always sufficient.

### 7.1. CYCLE node_id for a node graph

For the lab graph, repeating a node on the same path means returning to that exact node:

```sql
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
```

This is the right choice when the state requiring cycle detection is defined solely by node identity.

### 7.2. CYCLE with a composite key

Suppose a query not only traverses nodes but also carries a business state, such as `NODE_ID + ACCESS_MODE`. The same node might appear with different access modes. If the state `(node_id, access_mode)` is what identifies a step in the algorithm, you may need:

```sql
CYCLE node_id, access_mode
SET cycle_flag TO 'Y' DEFAULT 'N'
```

The columns must be in the alias list. Choosing too wide a key can miss a loop back to a node if other attributes change on every iteration. Choosing too narrow a key can mark a state as a cycle even when business rules allow the same node in different states.

Answer the question: **"When is a state considered revisited because which attributes match an ancestor?"** before deciding the CYCLE list.

### 7.3. CYCLE does not replace business limiting rules

`CYCLE` stops further expansion of a path when a repeat is detected on the chosen key. It does not replace:

- Depth limits if business rules allow at most N levels.
- Access permissions or tenant scoping.
- Invalid-data filter conditions.
- Input data validation.
- Rules excluding disallowed paths.

If depth limiting is needed, you can place `WHERE parent.depth_no < :max_depth` in the recursive member. Check whether that limit drops valid data. If cycles are possible, still use CYCLE to make cycle-detection rules explicit.

## 8. When CYCLE Is Not Declared

Oracle has a default cycle detection mechanism for recursive subquery factoring. If a cycle is detected without a `CYCLE` clause, the query may terminate with an error:

```text
ORA-32044: cycle detected while executing recursive WITH query
```

Default detection relies on columns in the recursive query's alias list referenced in the recursive member's `WHERE` clause. When you need to define clearly which key identifies a repeated state, declare `CYCLE` explicitly instead of relying on the default rule.

Do not remove CYCLE to "fix" ORA-32044 without checking the data. The error typically indicates a path returning to an ancestor state under the query's cycle criteria.

## 9. SEARCH and CYCLE Can Be Used Together

A recursive query often needs both:

```sql
WITH graph_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM graph_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET traversal_order
CYCLE node_id SET is_cycle TO 'Y' DEFAULT 'N'
SELECT
    node_id,
    depth_no,
    is_cycle,
    traversal_order
FROM graph_walk
ORDER BY traversal_order;
```

Here:

- `SEARCH BREADTH FIRST` creates `TRAVERSAL_ORDER` to sort rows breadth-first.
- `CYCLE node_id` flags rows returning to an ancestor node.
- `IS_CYCLE` is automatically added by Oracle to the query name's columns.
- `TRAVERSAL_ORDER` is also automatically added to the query name's columns.
- The two generated column names must be distinct from each other and from all names in the alias list.

If you want to inspect cycles first before filtering, keep `IS_CYCLE` in the SELECT. If you want only normal rows, filter `IS_CYCLE = 'N'` in the outer query.

## 10. Limitations of the Recursive Member in Oracle

The recursive member has several important syntactic restrictions. According to the Oracle 19c SQL Language Reference:

- Must reference the query name **exactly once** in the FROM clause.
- Must be combined with the anchor via `UNION ALL`.
- Cannot use `DISTINCT` or `GROUP BY` in the recursive member.
- Cannot use aggregate functions in the recursive member; analytic functions are allowed in the select list.
- Cannot contain a subquery referencing the query name.
- Cannot use an outer join with the query name as the right-hand table of the outer join.
- The alias list and both SELECT lists must match in column count, order, and compatible types.

Therefore, if you need to aggregate results after traversal, aggregate in the outer query block:

```sql
WITH org_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM org_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT
    depth_no,
    COUNT(*) AS visited_rows
FROM org_walk
WHERE cycle_flag = 'N'
GROUP BY depth_no
ORDER BY depth_no;
```

`GROUP BY` sits in the outer query, not inside the recursive member. The outer query receives the rows produced by recursion and then aggregates them.

## 11. Recursive Subquery Factoring vs. CONNECT BY

Oracle has the traditional hierarchical syntax `START WITH ... CONNECT BY`, common in legacy systems:

```sql
SELECT
    employee_id,
    manager_id,
    LEVEL AS depth_no
FROM employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
```

This example illustrates the familiar structure on an `EMPLOYEES` table with `EMPLOYEE_ID` and `MANAGER_ID`. With an edge model like `LAB_ORG_EDGES`, you must construct an appropriate row source before using `CONNECT BY`. Recursive subquery factoring uses `WITH` to express the anchor and recursive member explicitly, which fits well when carrying multiple states such as paths, accumulated costs, or per-step data.

| Capability | Recursive subquery factoring | CONNECT BY |
| --- | --- | --- |
| Starting point | Anchor member | `START WITH` |
| Expansion step | Recursive member + `UNION ALL` | `CONNECT BY PRIOR` |
| Depth | Carry your own depth column or compute in query | `LEVEL` |
| Traversal order | `SEARCH DEPTH/BREADTH FIRST` creates ordering column | `ORDER SIBLINGS BY` for siblings |
| Cycle handling | `CYCLE` mark column | `NOCYCLE`, `CONNECT_BY_ISCYCLE` |
| Accumulated state | Can carry path/cost/state columns in CTE | Has dedicated hierarchical pseudocolumns/functions |
| Structure | CTE form with explicit query blocks | Oracle-specific hierarchical syntax |

There is no need to rewrite every CONNECT BY query into recursive WITH. Use the construct that suits the complexity, version requirements, and maintainability of your system.

## 12. Practical Applications

### 12.1. Employee organization tree

Each employee has `MANAGER_ID`; the anchor starts from the CEO with a NULL manager, and the recursive member finds employees whose manager is the person in the previous row. `SEARCH DEPTH FIRST` can display a complete management branch; `CYCLE employee_id` detects circular management data.

### 12.2. Multi-level categories

Product categories have `CATEGORY_ID` and `PARENT_CATEGORY_ID`. You can start from a top-level category, recurse to subcategories, and carry `DEPTH_NO` and path to build breadcrumbs. Cycle detection catches invalid parent-child configurations.

### 12.3. Task dependencies

A task can depend on multiple other tasks. The dependency graph may have multiple paths; `SEARCH` helps order traversal, and `CYCLE` detects dependency loops that prevent valid topological scheduling. However, `SEARCH` does not automatically compute a valid deployment order for every business rule; an appropriate model and algorithm are required.

### 12.4. Access permission graph

A role can inherit from multiple other roles. A recursive CTE can expand inherited permissions, though the cycle key may need to include both role and context/tenant if permission state depends on context. Do not mechanically use `CYCLE role_id` when the same role in two contexts represents two distinct business states.

## 13. Performance and Controlling Row Volume

Recursion can expand very rapidly. A node with many children followed by further branching generates a large number of paths, especially in many-to-many graphs.

Design principles:

1. **Start from the right roots**: an overly broad anchor can blow up row counts from the very first iteration.
2. **Index the expansion edge**: recursive queries typically look up edges by `PARENT_ID`; consider an appropriate index on `LAB_ORG_EDGES(PARENT_ID)`. The primary key `(PARENT_ID, CHILD_ID)` in the lab already supports this prefix.
3. **Carry only needed columns**: avoid hauling large payloads through every iteration unnecessarily.
4. **Set depth limits when business rules require them**: `WHERE parent.depth_no < :max_depth` in the recursive member.
5. **Choose the right cycle key**: too wide a key can miss business cycles; too narrow a key can over-flag.
6. **Distinguish nodes from paths**: the same node may appear across many paths. If only unique nodes are needed, add a selection/aggregation step outside the CTE.
7. **Inspect execution plans and actual row counts**: do not estimate performance solely from visible data depth.

You can inspect the estimated plan:

```sql
EXPLAIN PLAN FOR
WITH org_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM org_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT node_id, depth_no, cycle_flag
FROM org_walk
ORDER BY dfs_order;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows an estimated plan. For production workloads, DBAs may need cursor plans, runtime statistics, logical I/O, and per-step row counts to determine whether recursive expansion generates large cardinality.

## 14. Common Errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Error declaring recursive WITH | Missing alias list or mismatched column counts between branches | Declare the alias list and align each anchor/recursive column |
| Query does not terminate | Recursive member condition keeps generating rows | Check joins, stop conditions, and cycle keys |
| ORA-32044 | Oracle detected a cycle with no CYCLE clause | Locate the cycle, declare an appropriate CYCLE clause, or fix data/conditions |
| Rows with the same NODE_ID appear multiple times | Node is reachable via multiple valid paths | Decide whether you need to list paths or distinct nodes |
| SEARCH declared but output is not in expected order | Missing ORDER BY on the ordering column | Sort the outer query by the SET column |
| DEPTH FIRST/BREADTH FIRST does not remove loops | SEARCH only generates ordering, does not detect cycles | Use CYCLE to flag paths returning to an ancestor |
| CYCLE flags an unexpected row | Cycle key chosen is too wide or too narrow | Clarify the business definition of a repeated state |
| Cycle row still shows up | CYCLE flags rows rather than filtering them out | Filter on the cycle mark in the outer query if the report shouldn't show it |
| Using DISTINCT in recursive member | Recursive member forbids DISTINCT | Handle deduplication in the outer query per business rules |
| Placing GROUP BY in recursive member | Recursive member forbids GROUP BY/aggregates | Aggregate in the outer query block |
| Outer join with recursive query name on the right | Violates recursive member restrictions | Rewrite expansion using an inner join or restructure query blocks |
| Path fails or hits length limit | Path string grows with every level | CAST to an appropriate type, limit depth, or use another path storage design |
| Confusing SEARCH with physical execution order | The ordering column is a result-sorting mechanism | Use ORDER BY on the ordering column; distinguish from execution plan |

## 15. Practice Exercises

Use `LAB_ORG_NODES` and `LAB_ORG_EDGES` from section 3.

### Exercise 1 — Traverse the tree from root

Write a recursive CTE starting at node 1, returning `NODE_ID`, `NODE_NAME`, and `DEPTH_NO`. No path needed. Explain how the anchor member and recursive member generate each tier.

### Exercise 2 — Add path ordering

Run the query with `UNION ALL` and `SEARCH DEPTH FIRST BY node_id SET dfs_order`. Determine why node 4 appears twice. Switch to `BREADTH FIRST` and compare tier-by-tier ordering.

### Exercise 3 — Build the path

Add `PATH_TXT` starting from the root ID and appending child IDs on each iteration. Return the paths for both visits to node 4. Explain why the same node can have two paths.

### Exercise 4 — Create a cycle

Insert edge `5 -> 1` and run a recursive CTE with:

```sql
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
```

Find the row marked Y and explain why the recursive member stops expanding from that row.

### Exercise 5 — Distinguish cycles from multiple paths

Before inserting the cycle edge, node 4 appeared twice. Explain why `CYCLE node_id` did not flag the second visit to node 4 as a cycle. Then compare with the path `1 -> 2 -> 4 -> 5 -> 1`.

### Exercise 6 — Retrieve only non-cycle rows

Filter in the outer query with `WHERE cycle_flag = 'N'`. Compare the result with the query that keeps cycle rows for diagnostics.

### Exercise 7 — Limit depth

Add bind `:max_depth` and a condition in the recursive member:

```sql
WHERE parent.depth_no < :max_depth
```

Run with depths 1, 2, and 3. Note which branches this limit cuts off and why it does not replace cycle detection.

### Exercise 8 — Design a composite cycle key

Suppose a node can be traversed in two states `READ` and `WRITE`. Design an alias list with `NODE_ID` and `ACCESS_MODE`, then explain when `CYCLE NODE_ID` is sufficient and when `CYCLE NODE_ID, ACCESS_MODE` is needed.

## 16. Cleaning Up Lab Data

Run only in the lab schema you created, after completing the exercises:

```sql
DROP TABLE lab_org_edges PURGE;
DROP TABLE lab_org_nodes PURGE;
```

Drop the edge table before the node table due to the foreign key reference. If you created any other tables during practice, drop those exact tables in dependency order. `PURGE` bypasses the recycle bin; do not run on other people's tables or data that might need recovery.

## Summary

Recursive subquery factoring uses a self-referencing `WITH` query block to expand multi-level data. The **anchor member** produces the starting point; the **recursive member** generates the next step and is joined to the anchor using `UNION ALL`. The alias list defines the query columns; both branches must return matching column counts and compatible types.

`SEARCH DEPTH FIRST` and `SEARCH BREADTH FIRST` create an ordering column for the traversal method; to display results in that order, you must `ORDER BY` the column declared by `SET`. `CYCLE` specifies the columns identifying a repeated state along the path, flags the cycle-causing row, and stops expansion from it while non-cyclic branches continue. A cycle is a relationship with **an ancestor on the same path**, not simply a node appearing multiple times across the entire result set.

When designing hierarchical or graph queries, define the root, row grain, path semantics, cycle key, and traversal order before writing SQL. Combine these rules with depth controls, edge indexes, and execution plans so recursive queries remain both business-accurate and operationally stable.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SELECT, Recursive Subquery Factoring (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — anchor/recursive members, recursive member restrictions, SEARCH, and CYCLE.
- [Oracle Database SQL Language Reference — SELECT (26ai)](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html) — cross-reference recursive subquery factoring syntax in newer releases.
- [Oracle Database Error Messages (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-32000.html) — look up ORA-32044 when a cycle is detected in a recursive WITH query.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, execution plans, and performance analysis.

When deploying on Oracle releases other than 19c, check the exact version's SQL Language Reference, especially recursive member restrictions, cycle detection, and SEARCH/CYCLE rules.
