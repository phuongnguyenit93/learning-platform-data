# Recursive CTEs for Trees and Graphs in PostgreSQL

In an HR system, a department can belong to another department; in e-commerce, a product category can contain many subcategories; in an authorization system, a role can inherit from other roles; in logistics, a location can have routes to many other locations. These structures are not just independent rows—they are **trees** or **graphs**.

PostgreSQL supports **recursive common table expressions (CTEs)** via the `WITH RECURSIVE` syntax. This lets you start from one or more nodes, follow links between rows across multiple levels, and aggregate results in SQL. A recursive CTE often replaces application code that repeatedly issues `SELECT` queries to walk from parent to child or child to parent.

This lesson focuses on:

- The structure of the **anchor term**, **recursive term**, `UNION ALL`/`UNION`, and the working-table mechanism.
- Traversing trees from root to leaves, finding ancestors, descendants, paths (*breadcrumbs*), depth levels, and leaf nodes.
- Differences between **trees** and **graphs with multiple paths or cycles**.
- Preventing infinite loops using path arrays or PostgreSQL's `CYCLE` syntax.
- Ordering results breadth-first (**BFS**) and depth-first (**DFS**) using paths or `SEARCH`.
- Resource limits, performance, result correctness, and hands-on exercises.

The examples use a dedicated schema `cte_lab_164` and SQL for modern PostgreSQL. The `SEARCH`/`CYCLE` features were introduced in **PostgreSQL 14**; examples using array paths remain the right option when supporting older versions.

## 1. Understanding Trees, Graphs, Nodes, and Edges

A **node** (*vertex*) is an entity, such as a department, account, or transit hub. An **edge** represents a relationship from one node to another, such as "department A manages department B".

### 1.1. Trees: each child node has one parent

In a rooted tree:

- **Root:** has no parent.
- **Parent:** a node with one or more children.
- **Child:** a node belonging to a parent.
- **Leaf:** a node with no children.
- **Ancestor:** nodes above a given node.
- **Descendant:** nodes below a given node.
- **Depth:** number of edges from the root or starting node to the current node.

~~~text
Company (1)                        depth = 0
├── Engineering (2)                depth = 1
│   ├── Platform (4)               depth = 2
│   │   ├── API (6)                depth = 3
│   │   └── Infrastructure (7)     depth = 3
│   └── Data (5)                   depth = 2
│       └── Analytics (8)          depth = 3
└── Sales (3)                      depth = 1
    ├── Enterprise (9)             depth = 2
    └── Retail (10)                depth = 2
~~~

If each node has at most one parent, there are no cycles, and every node connects to the root, it is a tree. If there are **multiple roots**, the collection of trees is commonly called a **forest**.

### 1.2. Graphs: a node can receive multiple edges and cycles can appear

A directed graph can have:

~~~text
A --> B --> D --> E
|     |     |     |
|     |     +-----+
|     |           |
|     +---- H     v
v                B
C --> D
|
+--> F --> G --> H
~~~

A path from `A` to `D` can go through `B` or `C`; that is **multiple paths to the same node**. Edges `B → D → E → B` form a **cycle**. A recursive query following edges without tracking visited nodes can loop logically forever or run until hitting resource limits/timeouts.

### 1.3. Paths vs. reachable nodes

Two questions are often confused:

1. **Reachability:** starting from A, **which nodes** can be reached?
2. **Path enumeration:** from A to H, **which paths** exist, through which nodes, and of what length?

The first question usually needs **node deduplication**. The second needs to **preserve distinct paths**, even when they end at the same node. Choosing `UNION`, `UNION ALL`, and state columns in the CTE depends directly on this goal.

## 2. Reviewing Regular CTEs Before Using RECURSIVE

A CTE is a named intermediate result defined within the same SQL statement using `WITH`:

~~~sql
WITH paid_orders AS (
    SELECT order_id, customer_id, net_amount
    FROM some_orders
    WHERE status = 'PAID'
)
SELECT
    customer_id,
    COUNT(*) AS paid_count,
    SUM(net_amount) AS paid_amount
FROM paid_orders
GROUP BY customer_id;
~~~

`some_orders` in this example is just a hypothetical table. This CTE is **non-recursive**: it does not reference the name `paid_orders` inside its own definition.

A recursive CTE differs in that the query definition can **reference results found in the previous step** to traverse another level.

~~~sql
WITH RECURSIVE cte_name AS (
    -- 1. Anchor: starting rows
    SELECT ...

    UNION ALL

    -- 2. Recursive term: use cte_name to find the next rows
    SELECT ...
    FROM some_table AS next_node
    JOIN cte_name AS previous_step
      ON ...
)
SELECT *
FROM cte_name;
~~~

`WITH RECURSIVE` is not only for trees and graphs; it can also generate number sequences, date series, or query multi-level dependencies. However, trees and graphs are where this capability especially shines.

## 3. How Anchor, Recursive Term, and UNION ALL Work

A PostgreSQL recursive query typically looks like:

~~~sql
WITH RECURSIVE walk AS (
    SELECT ...        -- anchor
    UNION ALL
    SELECT ...        -- recursive term referencing walk
)
SELECT ... FROM walk;
~~~

Parts:

| Component | Role |
| --- | --- |
| `WITH RECURSIVE` | Enables defining a CTE as a recursive query |
| Anchor (non-recursive term) | Produces the initial rows |
| `UNION ALL` or `UNION` | Combines initial rows and rows from deeper steps |
| Recursive term | Uses the previous pass's rows to produce new rows |
| Join condition | Determines "from the current node, which nodes to visit next" |
| Termination condition | No new rows left, depth limit reached, or cycle prevented |
| Outer SELECT | Filters, sorts, and formats the complete result |

PostgreSQL **evaluates recursive queries iteratively**, even though the syntax and mental model are recursive. In each pass, it processes a **working table** holding rows discovered in the previous pass, produces new rows, and repeats until the working table is empty.

### 3.1. Short example: generating numbers from 1 to 5

~~~sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1                 -- anchor
    UNION ALL
    SELECT n + 1             -- recursive term
    FROM numbers
    WHERE n < 5              -- termination condition
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Result:

~~~text
n
-
1
2
3
4
5
~~~

Progression:

| Pass | Input working table | New rows |
| --- | --- | --- |
| Anchor | None | 1 |
| 1 | 1 | 2 |
| 2 | 2 | 3 |
| 3 | 3 | 4 |
| 4 | 4 | 5 |
| 5 | 5 | None, stop |

If `WHERE n < 5` is omitted, the query keeps generating numbers according to the recursive formula and **has no logical stopping point**. PostgreSQL does not impose a small fixed recursion cap like "100 levels" to automatically keep every SQL query safe. Therefore, termination conditions and cycle controls are a query design responsibility.

### 3.2. Column types must match between both branches

Each column returned by the anchor must be type-compatible with the corresponding column of the recursive term. For example:

~~~sql
WITH RECURSIVE steps(depth, label) AS (
    SELECT 0::integer, 'Start'::text
    UNION ALL
    SELECT depth + 1, ('Step ' || (depth + 1)::text)
    FROM steps
    WHERE depth < 3
)
SELECT depth, label
FROM steps
ORDER BY depth;
~~~

Casting `0::integer` and `'Start'::text` defines the column types explicitly. When using path arrays, the array in the anchor and the concatenation in the recursive term must also match types (for example, `bigint[]`).

### 3.3. Why is UNION ALL usually used?

`UNION ALL` keeps **every row**, including duplicates. It is typically cheaper than `UNION` because it avoids deduplication on every pass, and it suits **guaranteed acyclic trees**, where each node has only one path from the root.

`UNION` deduplicates across **all returned columns**; it can be useful when only the set of reached nodes is needed, but it **does not automatically stop all cycles** when a `depth` or `path` column changes on each pass. The graph section explains this in detail.

## 4. Creating Department Tree Data

We use an **adjacency list** table, where each node stores its parent's ID:

~~~text
node_id | node_name   | parent_id
--------+-------------+----------
1       | Company     | NULL
2       | Engineering | 1
4       | Platform    | 2
6       | API         | 4
...
~~~

This is a common tree storage model: easy to add nodes, rename them, and enforce parent–child foreign keys. In exchange, querying all descendants or ancestors is no longer a single-level join, which is why `WITH RECURSIVE` is so useful.

### 4.1. Creating the schema, table, and constraints

Run the DDL below only on a **lab database** where you have permission to create new objects:

~~~sql
CREATE SCHEMA cte_lab_164;

CREATE TABLE cte_lab_164.org_nodes (
    node_id BIGINT PRIMARY KEY,
    parent_id BIGINT NULL,
    node_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_org_parent
        FOREIGN KEY (parent_id)
        REFERENCES cte_lab_164.org_nodes(node_id)
        ON DELETE RESTRICT,

    CONSTRAINT org_not_own_parent
        CHECK (parent_id IS NULL OR parent_id <> node_id)
);

CREATE INDEX idx_org_nodes_parent
    ON cte_lab_164.org_nodes(parent_id);
~~~

Details:

- `node_id` is the node's primary key.
- `parent_id` references `node_id` of **this same table**.
- `NULL` in `parent_id` indicates a root node.
- `ON DELETE RESTRICT` prevents deleting a parent node that still has referencing children.
- `CHECK (parent_id <> node_id)` forbids **a node from pointing directly to itself**.
- An index on `parent_id` helps the step that finds all children of a node.

**Important note:** a `FOREIGN KEY` combined with `CHECK (parent_id <> node_id)` **does not prove the tree has no cycles longer than one edge**. For instance, A pointing to B, B to C, and C to A can still satisfy each FK. Preventing cycles may require business-logic validation in transactions, safe triggers/update procedures, or an alternative data structure.

### 4.2. Loading data in parent-before-child order

~~~sql
INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (1, NULL, 'Company', 1),
    (11, NULL, 'Support', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (2, 1, 'Engineering', 1),
    (3, 1, 'Sales', 2),
    (12, 11, 'Tier 1 Support', 1),
    (13, 11, 'Tier 2 Support', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (4, 2, 'Platform', 1),
    (5, 2, 'Data', 2),
    (9, 3, 'Enterprise', 1),
    (10, 3, 'Retail', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (6, 4, 'API', 1),
    (7, 4, 'Infrastructure', 2),
    (8, 5, 'Analytics', 1);
~~~

The dataset has **13 nodes** across two trees: root `1` (*Company*) and root `11` (*Support*). Within the `Company` tree there are 10 nodes: `1` through `10`.

~~~mermaid
flowchart TB
    A["1 · Company"] --> B["2 · Engineering"]
    A --> C["3 · Sales"]
    B --> D["4 · Platform"]
    B --> E["5 · Data"]
    D --> F["6 · API"]
    D --> G["7 · Infrastructure"]
    E --> H["8 · Analytics"]
    C --> I["9 · Enterprise"]
    C --> J["10 · Retail"]
    K["11 · Support"] --> L["12 · Tier 1 Support"]
    K --> M["13 · Tier 2 Support"]
~~~

### 4.3. Viewing the table non-recursively

~~~sql
SELECT
    node_id,
    parent_id,
    node_name,
    sort_order
FROM cte_lab_164.org_nodes
ORDER BY node_id;
~~~

In the raw table, each row knows only its **immediate parent**. To obtain the path `Company → Engineering → Data → Analytics`, we need to traverse relationships across multiple levels.

## 5. Top-Down Traversal: Fetching an Entire Subtree

The most fundamental query: starting from node `1`, find all descendants at every level.

~~~sql
WITH RECURSIVE subtree AS (
    -- Anchor: starting node.
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS depth
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    -- Recursive: find children of already discovered nodes.
    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent_step.depth + 1 AS depth
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS parent_step
        ON child.parent_id = parent_step.node_id
)
SELECT
    node_id,
    parent_id,
    node_name,
    depth
FROM subtree
ORDER BY depth, node_id;
~~~

Results sorted by level:

| Depth | Nodes |
| ---: | --- |
| 0 | 1 — Company |
| 1 | 2 — Engineering; 3 — Sales |
| 2 | 4 — Platform; 5 — Data; 9 — Enterprise; 10 — Retail |
| 3 | 6 — API; 7 — Infrastructure; 8 — Analytics |

The query returns **10 rows**, including the starting node `1` itself. If the requirement is **descendants excluding the starting node**, add:

~~~sql
-- Apply in the outer SELECT:
WHERE depth > 0
~~~

and the row count is **9**.

### 5.1. Why is the JOIN oriented this way?

~~~sql
JOIN subtree AS parent_step
    ON child.parent_id = parent_step.node_id
~~~

Here `parent_step.node_id` is the node being expanded; PostgreSQL looks up rows where `child.parent_id` points to that node. That is the **parent → child** direction.

If written the other way around:

~~~sql
-- Walks up to parents, not down to children:
JOIN subtree AS current_step
    ON parent.node_id = current_step.parent_id
~~~

then the query walks toward **ancestors**, serving a different goal.

### 5.2. Starting from any branch

Simply change the anchor:

~~~sql
WHERE n.node_id = 2
~~~

then the `Engineering` subtree includes `2, 4, 5, 6, 7, 8`, totaling **6 nodes**. `Sales` and the two support branches are not selected.

For parameterized queries, pass the root ID via an application bind variable instead of concatenating SQL strings. Example in Java/JDBC:

~~~java
String sql = """
    WITH RECURSIVE subtree AS (
        SELECT node_id, parent_id, node_name, 0 AS depth
        FROM cte_lab_164.org_nodes
        WHERE node_id = ?
        UNION ALL
        SELECT n.node_id, n.parent_id, n.node_name, t.depth + 1
        FROM cte_lab_164.org_nodes AS n
        JOIN subtree AS t
          ON n.parent_id = t.node_id
    )
    SELECT node_id, parent_id, node_name, depth
    FROM subtree
    ORDER BY depth, node_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("node_id") + " | " +
                rs.getInt("depth") + " | " +
                rs.getString("node_name")
            );
        }
    }
}
~~~

The Java snippet assumes `connection` is a valid JDBC `Connection` and uses a Java version supporting text blocks. Bind parameters separate data from SQL syntax; enforcing branch access permissions remains the application/database's responsibility.

## 6. Tracing Each Recursion Pass with the Working-Table Model

In the subtree query starting at `node_id = 1`:

| Pass | Input | Child nodes found |
| --- | --- | --- |
| Anchor | None | 1 |
| 1 | 1 | 2, 3 |
| 2 | 2, 3 | 4, 5, 9, 10 |
| 3 | 4, 5, 9, 10 | 6, 7, 8 |
| 4 | 6, 7, 8 | None |

When no new rows are found, the query terminates. PostgreSQL executes recursive evaluation pass by pass and tends to emit rows during this process in a **breadth-first** fashion, but **you must not rely on natural emission order as a stable ordering contract**. When displaying by depth or path, include an outermost `ORDER BY`.

### 6.1. How many times can a record appear?

In a **valid tree**, walking downward from one root gives each node a unique path from the root, so `UNION ALL` does not duplicate nodes via multiple parents.

In a **graph**, a node can be reached by multiple paths; with `UNION ALL`, each path produces its own result row. If the graph contains a cycle and has no stopping guard, repetition can continue indefinitely.

### 6.2. No automatic 100-level recursion limit

PostgreSQL has no direct counterpart to a `MAXRECURSION 100` setting found in some other database engines. You must design termination yourself using:

- A tree structure **guaranteed to be acyclic**;
- A visited-node set or current path;
- A condition `depth < :max_depth` if business rules accept a depth cap;
- `statement_timeout` or application limits as an operational safety net.

**Limiting depth does not prove data is acyclic**; it only stops the query from descending beyond the allowed level.

## 7. Bottom-Up Traversal: Finding All Ancestors

Suppose we are at node `8 — Analytics` and want the management chain up to the root.

~~~sql
WITH RECURSIVE ancestors AS (
    -- Anchor: current node.
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS distance_to_start
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 8

    UNION ALL

    -- Find the parent of the current node.
    SELECT
        parent.node_id,
        parent.parent_id,
        parent.node_name,
        a.distance_to_start + 1
    FROM cte_lab_164.org_nodes AS parent
    JOIN ancestors AS a
        ON parent.node_id = a.parent_id
)
SELECT
    node_id,
    node_name,
    distance_to_start
FROM ancestors
ORDER BY distance_to_start DESC;
~~~

Result from root to node:

| Node | Name | Distance to 8 |
| ---: | --- | ---: |
| 1 | Company | 3 |
| 2 | Engineering | 2 |
| 5 | Data | 1 |
| 8 | Analytics | 0 |

Here `distance_to_start` measures **edges walked upward from the starting node**, so the root has the largest value. If level from the root is needed, you can reverse the order or subtract distance from the maximum value.

### 7.1. Ancestors only, excluding the current node

In the outer query:

~~~sql
WHERE distance_to_start > 0
~~~

The result contains `1, 2, 5`.

### 7.2. When the starting node is a root

If the anchor is `1` or `11`, there is no parent. The CTE still returns **one anchor row with distance = 0**, then stops immediately.

### 7.3. Why does this query differ from finding descendants?

Walking down the tree joins `child.parent_id = current.node_id`. Walking up the tree joins `parent.node_id = current.parent_id`. Even on the same table, **reversing edge direction completely changes the result set and termination behavior**.

## 8. Building Breadcrumbs and Full Paths

Hierarchical applications often want to display:

~~~text
Company / Engineering / Data / Analytics
~~~

The CTE can carry an extra **path** column using a PostgreSQL array.

### 8.1. Name path using an array

~~~sql
WITH RECURSIVE ancestors AS (
    SELECT
        n.node_id,
        n.parent_id,
        ARRAY[n.node_name]::text[] AS name_path,
        0::integer AS level_up
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 8

    UNION ALL

    SELECT
        parent.node_id,
        parent.parent_id,
        ARRAY[parent.node_name]::text[] || a.name_path,
        a.level_up + 1
    FROM cte_lab_164.org_nodes AS parent
    JOIN ancestors AS a
        ON parent.node_id = a.parent_id
)
SELECT
    node_id AS root_id,
    array_to_string(name_path, ' / ') AS breadcrumb
FROM ancestors
WHERE parent_id IS NULL;
~~~

In the lab, result:

~~~text
root_id = 1
breadcrumb = Company / Engineering / Data / Analytics
~~~

At the anchor, the array holds one name `['Analytics']`. On each upward step, the expression:

~~~sql
ARRAY[parent.node_name]::text[] || a.name_path
~~~

**prepends the parent name to the front of the array**, so upon reaching the root, the sequence naturally reads root → leaf.

### 8.2. ID paths are more stable than name paths

Node names can collide or change; IDs are designed to be more stable. When a branch must be identified unambiguously, carry:

~~~sql
ARRAY[n.node_id]::bigint[] AS path_ids
~~~

In the recursive term:

~~~sql
parent_step.path_ids || child.node_id AS path_ids
~~~

For example, for node 8: `{1,2,5,8}`. An ID array is especially useful to:

- Detect whether a node is already on the current path;
- Sort results in tree order;
- Construct name breadcrumbs by joining or mapping IDs back to names;
- Log traversal paths for data debugging.

Do not treat a path array generated by a point-in-time query as a permanent business key if the tree can be reorganized; reparenting changes the path of the entire subtree.

## 9. Carrying Path and Depth While Walking Down a Tree

A fuller subtree version:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS depth,
        ARRAY[n.node_id]::bigint[] AS path_ids,
        ARRAY[n.node_name]::text[] AS path_names
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent_step.depth + 1,
        parent_step.path_ids || child.node_id,
        parent_step.path_names || child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS parent_step
        ON child.parent_id = parent_step.node_id
)
SELECT
    node_id,
    depth,
    path_ids,
    array_to_string(path_names, ' / ') AS breadcrumb
FROM subtree
ORDER BY path_ids;
~~~

In a tree with ascending IDs like the lab dataset, `ORDER BY path_ids` sorts rows by **ID path** (lexicographical array order). This typically presents a **depth-first** layout in the result: starting at node 1, descending into branch 2 before moving to branch 3.

### 9.1. Paths add overhead

If a tree is thousands of levels deep, each row carries an increasingly long array. Total memory, bandwidth, and array concatenation overhead can become substantial. Only carry `path_ids` or `path_names` when actually needed; if you only want to count descendants, a query with just ID and depth can be cheaper.

### 9.2. Using IDs to guard against cycles

To prevent revisiting a node already on the path:

~~~sql
WHERE NOT child.node_id = ANY(parent_step.path_ids)
~~~

in the recursive term. This condition activates when data contains cycles and stops a path from repeating a node already visited along **that same path**.

It **does not mean each node is unique across the entire graph**: if the same node is reached by two distinct acyclic paths, it can still produce two rows, each with its own `path_ids`.

## 10. Fetching Multiple Trees from All Roots

The dataset has two roots, `1` and `11`. Instead of selecting just one root, the anchor picks every row with `parent_id IS NULL`:

~~~sql
WITH RECURSIVE forest AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        n.node_id AS root_id,
        0::integer AS depth,
        ARRAY[n.node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes AS n
    WHERE n.parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        f.root_id,
        f.depth + 1,
        f.path_ids || child.node_id
    FROM cte_lab_164.org_nodes AS child
    JOIN forest AS f
        ON child.parent_id = f.node_id
    WHERE NOT child.node_id = ANY(f.path_ids)
)
SELECT
    root_id,
    node_id,
    node_name,
    depth
FROM forest
ORDER BY root_id, path_ids;
~~~

`root_id` is assigned in the anchor and **propagated unchanged** down to all child nodes. Each row therefore indicates which tree it belongs to. In the valid dataset:

- `root_id = 1` has **10 nodes**.
- `root_id = 11` has **3 nodes**.

### 10.1. Aggregating node counts and depth per tree

~~~sql
WITH RECURSIVE forest AS (
    SELECT
        node_id,
        parent_id,
        node_id AS root_id,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        f.root_id,
        f.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN forest AS f
        ON child.parent_id = f.node_id
)
SELECT
    root_id,
    COUNT(*) AS total_nodes,
    MAX(depth) AS max_depth
FROM forest
GROUP BY root_id
ORDER BY root_id;
~~~

Result:

| root_id | total_nodes | max_depth |
| ---: | ---: | ---: |
| 1 | 10 | 3 |
| 11 | 3 | 1 |

This assumes parent–child links form a valid forest. If there is a **disconnected cycle with no root node**, a query starting from `parent_id IS NULL` will **never reach that cyclic component**. Hence, **a forest query does not replace a tree-integrity validator**.

## 11. Finding Leaf Nodes and Counting Descendants

### 11.1. Leaf nodes in a subtree

A node is a **leaf** if no other node lists it as a parent:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id, node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    s.node_id,
    s.node_name
FROM subtree AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM cte_lab_164.org_nodes AS child
    WHERE child.parent_id = s.node_id
)
ORDER BY s.node_id;
~~~

In the `Company` tree, the leaves are `6, 7, 8, 9, 10` — **5 nodes** in total.

**Distinguish two definitions:** "has no children in the entire table" vs. "has no children within a filtered result set". The query above checks children in the **base table**, so a node that has children filtered out of a constrained subtree is still not considered a leaf. If business logic defines "leaf in the visible subset", check against that subset instead.

### 11.2. Counting descendants of one node

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id, s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    COUNT(*) AS nodes_including_start,
    COUNT(*) FILTER (WHERE depth > 0) AS descendants_only,
    MAX(depth) AS deepest_relative_level
FROM subtree;
~~~

For `Engineering`:

- `nodes_including_start = 6`.
- `descendants_only = 5`.
- `deepest_relative_level = 2`.

Relative depth `2` here is measured from node `2`, not from the system-wide root.

### 11.3. Counting descendants for **every node**

If you want a descendant count for every node, you can start from **all nodes** and propagate an `ancestor_id` column down each branch:

~~~sql
WITH RECURSIVE reach AS (
    SELECT
        n.node_id AS ancestor_id,
        n.node_id AS descendant_id,
        ARRAY[n.node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes AS n

    UNION ALL

    SELECT
        r.ancestor_id,
        child.node_id AS descendant_id,
        r.path_ids || child.node_id
    FROM reach AS r
    JOIN cte_lab_164.org_nodes AS child
        ON child.parent_id = r.descendant_id
    WHERE NOT child.node_id = ANY(r.path_ids)
)
SELECT
    ancestor_id,
    COUNT(*) - 1 AS descendants_count
FROM reach
GROUP BY ancestor_id
ORDER BY ancestor_id;
~~~

Each anchor begins with a self-representing row for that node. Thus, `COUNT(*) - 1` excludes the ancestor itself from the count.

Example:

| ancestor_id | descendants_count |
| ---: | ---: |
| 1 | 9 |
| 2 | 5 |
| 4 | 2 |
| 5 | 1 |
| 6 | 0 |
| 11 | 2 |

**Cost:** starting from every node can generate on the order of the total number of **ancestor–descendant** pairs. In a chain-like tree of depth `N`, the pair count grows as **O(N²)**. For large trees queried frequently, consider caching, closure tables, pre-aggregated metrics, or alternative storage instead of recomputing for every node on every request.

## 12. Computing Node Depth and Short Paths in a Tree

In a valid tree, there is only one path from the root to each node. Thus, `depth` generated by the recursive query **is the unique and shortest edge count** from the root to the node.

~~~sql
WITH RECURSIVE levels AS (
    SELECT
        node_id,
        parent_id,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        levels.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN levels
        ON child.parent_id = levels.node_id
)
SELECT
    node_id,
    depth
FROM levels
WHERE node_id = 8;
-- node_id = 8, depth = 3
~~~

In a **graph with multiple paths**, a row's depth is merely **the length of the path that produced that row**; do not assume it is the shortest distance to the node. Appropriate traversal/deduplication or shortest-path algorithms (when weighted) are required.

### 12.1. Limiting depth by business rule

For example, showing at most two levels below node 1:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
    WHERE s.depth < 2
)
SELECT *
FROM subtree
ORDER BY depth, node_id;
~~~

The result contains levels `0`, `1`, and `2`, without level `3`. Placing `s.depth < 2` inside the recursive term not only hides deeper rows from the output, it **prevents generating deeper rows altogether**.

**Do not confuse a query limit with a data-safety check:** if data contains a cycle, a depth-limited query may stop, yet **the cycle still exists in the database**.

## 13. SEARCH BREADTH FIRST and SEARCH DEPTH FIRST (PostgreSQL 14+)

PostgreSQL 14 added the SQL-standard `SEARCH` clause to generate a **traversal-order sorting column**. This removes the need to build a manual path array purely for `ORDER BY`.

Two traversal orders to distinguish:

- **Breadth-first search (BFS):** visits all nodes at the current level before descending deeper.
- **Depth-first search (DFS):** follows one branch deeply before moving to another branch.

### 13.1. SEARCH BREADTH FIRST

~~~sql
WITH RECURSIVE walk(node_id, parent_id, node_name) AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN walk AS w
        ON child.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
SELECT
    node_id,
    node_name,
    bfs_order
FROM walk
ORDER BY bfs_order;
~~~

PostgreSQL generates an extra `bfs_order` column for sorting. `BY node_id` specifies the tie-breaking key ordering sibling nodes. Output is ordered by level (and the specified key) when `ORDER BY bfs_order` is used.

### 13.2. SEARCH DEPTH FIRST

~~~sql
WITH RECURSIVE walk(node_id, parent_id, node_name) AS (
    SELECT
        node_id,
        parent_id,
        node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN walk AS w
        ON child.parent_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT
    node_id,
    node_name,
    dfs_order
FROM walk
ORDER BY dfs_order;
~~~

`dfs_order` is a path-based order column generated by `SEARCH DEPTH FIRST`. The outer query sorts by it to present DFS order.

### 13.3. Does SEARCH turn the execution engine into DFS?

**Do not interpret `SEARCH DEPTH FIRST` as forcing PostgreSQL to execute passes using a DFS stack.** According to the documentation, `SEARCH` augments the query with a column for **output sorting**; underlying recursive CTE evaluation still uses PostgreSQL's iterative working-table mechanism.

Therefore:

1. `SEARCH` does not prevent cycles on its own.
2. `SEARCH` does not guarantee termination.
3. Displaying BFS/DFS order requires `ORDER BY` on the `SET` column.
4. `SEARCH` can add overhead because path/order data must be maintained and sorted.

When BFS/DFS ordering is needed on versions older than PostgreSQL 14, you can sort by `ORDER BY depth, node_id` or `ORDER BY path_ids` as needed, keeping in mind that ordering by ID is merely a **sorting convention** and does not automatically apply a business `sort_order` column.

## 14. Directed Graphs: Storing Nodes and Edges

To clearly see the difference between trees and graphs, create two tables:

~~~sql
CREATE TABLE cte_lab_164.graph_nodes (
    node_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE cte_lab_164.graph_edges (
    from_id TEXT NOT NULL
        REFERENCES cte_lab_164.graph_nodes(node_id),
    to_id TEXT NOT NULL
        REFERENCES cte_lab_164.graph_nodes(node_id),
    weight INTEGER NOT NULL DEFAULT 1
        CHECK (weight > 0),

    CONSTRAINT graph_edges_pk
        PRIMARY KEY (from_id, to_id)
);

CREATE INDEX idx_graph_edges_to
    ON cte_lab_164.graph_edges(to_id);
~~~

`from_id → to_id` represents a **directed edge**. The composite primary key `(from_id, to_id)` prevents storing duplicate copies of the same directed edge. For an **undirected** graph, you normally need a convention to store/expand both directions or use a separate representation; `B → A` is not inferred automatically from `A → B`.

### 14.1. Seeding nodes and edges

~~~sql
INSERT INTO cte_lab_164.graph_nodes
    (node_id, display_name)
VALUES
    ('A', 'Start'),
    ('B', 'Node B'),
    ('C', 'Node C'),
    ('D', 'Node D'),
    ('E', 'Node E'),
    ('F', 'Node F'),
    ('G', 'Node G'),
    ('H', 'Target H');

INSERT INTO cte_lab_164.graph_edges
    (from_id, to_id, weight)
VALUES
    ('A', 'B', 2),
    ('A', 'C', 3),
    ('B', 'D', 2),
    ('B', 'H', 8),
    ('C', 'D', 1),
    ('C', 'F', 2),
    ('D', 'E', 1),
    ('E', 'B', 1),
    ('F', 'G', 2),
    ('G', 'H', 2);
~~~

The graph has multiple paths to `D` and `H`, plus a cycle:

~~~text
B -> D -> E -> B
~~~

Some simple paths (no repeated nodes) from A to H:

~~~text
A -> B -> H
A -> C -> F -> G -> H
A -> C -> D -> E -> B -> H
~~~

In this lesson, `weight` is a **positive edge cost** to illustrate summing weights. Queries using BFS/depth do not automatically solve the **minimum total-weight path** problem on arbitrary graphs.

## 15. Graph Traversal with UNION ALL: Why Cycle Prevention Matters

Naive query:

~~~sql
-- WARNING: do not run directly on graph_edges with cycles.
-- Query lacks a cycle-prevention mechanism:
--
-- WITH RECURSIVE walk AS (
--     SELECT 'A'::text AS node_id
--     UNION ALL
--     SELECT e.to_id
--     FROM walk AS w
--     JOIN cte_lab_164.graph_edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
~~~

Upon reaching `B`, the query moves to `D`, then `E`, then back to `B`, producing `B, D, E, B, D, E,...`. Because `UNION ALL` does not deduplicate, the working table keeps receiving new rows.

### 15.1. Simple approach for reachability: UNION keeping only node_id

If the goal is **which nodes are reachable from A**, without needing individual paths or depth levels, `UNION` works:

~~~sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 'A'::text

    UNION

    SELECT e.to_id
    FROM reachable AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
~~~

Result: **A, B, C, D, E, F, G, H** — eight unique nodes.

`UNION` deduplicates across **the entire CTE row**, and here the row has only one column `node_id`. When `B` is encountered again, it does not add a new value to the result, so expansion stops rather than looping forever on the same node.

**This is one specific case where `UNION` effectively breaks cycles:** when only the set of reached nodes is needed, and the recursive state carries no extra columns that change when revisiting a node.

### 15.2. Why doesn't UNION solve it once depth is added?

~~~sql
-- WARNING: do not run the following query on a graph with cycles.
--
-- WITH RECURSIVE walk(node_id, depth) AS (
--     SELECT 'A'::text, 0::integer
--     UNION
--     SELECT e.to_id, w.depth + 1
--     FROM walk AS w
--     JOIN cte_lab_164.graph_edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
~~~

Row `('B', 1)` **differs** from row `('B', 4)` because `depth` differs. `UNION` deduplicates across both columns, so a cycle keeps producing new rows with ever-increasing depth.

Similarly, if the CTE stores `path`, the same node at the end of different paths still produces **distinct rows**. An explicit cycle-prevention mechanism is required for this kind of query.

## 16. Preventing Cycles with a Path Array

A practical pattern is storing the **set of nodes in the current path** as an array. Before following an edge, check that the destination node is not already in that array.

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        0::integer AS depth,
        ARRAY['A']::text[] AS path_ids

    UNION ALL

    SELECT
        e.to_id AS node_id,
        p.depth + 1,
        p.path_ids || e.to_id
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
)
SELECT
    node_id,
    depth,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
ORDER BY depth, route;
~~~

**Explanation:**

1. The anchor creates the initial path `{A}`.
2. Each pass follows outgoing edges from the current tail node.
3. `e.to_id = ANY(p.path_ids)` checks whether the target node already appears on **that path**.
4. `NOT ...` only allows appending a node not yet visited, so `B → D → E → B` cannot occur along the same path.

Because the graph has 8 nodes, a **simple path** can contain at most 8 nodes. This guarantees the set of paths cannot expand infinitely via cycles on a finite graph.

### 16.1. Paths can still reach the same node via multiple branches

`A → B → D` and `A → C → D` are both valid because `D` has not appeared **on either individual path**. The result can include two rows with `node_id = 'D'` and two different `path_ids`.

This is the difference between:

- **Path-local visited set:** prevents a node from appearing more than once **within the same path**.
- **Global visited set:** processes each node once, required by certain optimized reachability/BFS algorithms.

A recursive CTE with a path array enumerates simple paths; it **does not maintain a shared global visited set to suppress multiple paths ending at the same node**.

### 16.2. Path enumeration can still be very expensive

Even without infinite loops, the number of **simple paths** between two nodes in a densely branching graph can grow very rapidly—even exponentially in layered graphs. Thus:

~~~sql
WHERE NOT e.to_id = ANY(p.path_ids)
~~~

ensures **termination**, but **does not guarantee the query is cheap**. On large graphs, you need depth bounds, node scoping, access controls, or specialized algorithms/storage.

## 17. Listing Paths from A to H

Building on the path pattern, keep only rows ending at `H`:

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops

    UNION ALL

    SELECT
        e.to_id,
        p.path_ids || e.to_id,
        p.hops + 1
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
)
SELECT
    hops,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
WHERE node_id = 'H'
ORDER BY hops, route;
~~~

Some resulting routes:

| Hops | Route |
| ---: | --- |
| 2 | A → B → H |
| 4 | A → C → F → G → H |
| 5 | A → C → D → E → B → H |

In the lab dataset, these are the simple paths to H. The query retains **all paths**, so `ORDER BY hops` only sorts results by edge count—it does not stop recursion as soon as the first short path is found.

### 17.1. Stopping expansion once the destination is reached

In the recursive term, you can add:

~~~sql
AND p.node_id <> 'H'
~~~

so paths **stop expanding once they reach H**. This is useful branch pruning when the goal is strictly paths from A to H. Do not confuse it with stopping other paths still en route to H.

### 17.2. Picking a path with the fewest hops

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops

    UNION ALL

    SELECT
        e.to_id,
        p.path_ids || e.to_id,
        p.hops + 1
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
      AND p.node_id <> 'H'
)
SELECT
    hops,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
WHERE node_id = 'H'
ORDER BY hops, path_ids
LIMIT 1;
~~~

On the lab graph, the fewest-hop path is **A → B → H**, with **2 edges**. Still, a SQL query like this may construct and traverse many paths before sorting and applying `LIMIT`. It is **not an optimal global BFS implementation** for finding shortest paths on very large graphs.

## 18. Edge Weights and Lowest-Cost Paths

Not all edges have equal cost. In `graph_edges`, the `weight` column represents positive edge cost.

### 18.1. Summing weights along a path

~~~sql
WITH RECURSIVE routes AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops,
        0::bigint AS total_weight

    UNION ALL

    SELECT
        e.to_id,
        r.path_ids || e.to_id,
        r.hops + 1,
        r.total_weight + e.weight::bigint
    FROM routes AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
    WHERE NOT e.to_id = ANY(r.path_ids)
      AND r.node_id <> 'H'
)
SELECT
    hops,
    total_weight,
    array_to_string(path_ids, ' -> ') AS route
FROM routes
WHERE node_id = 'H'
ORDER BY total_weight, hops, route;
~~~

With the seed data:

| Route | Hops | Total weight |
| --- | ---: | ---: |
| A → B → H | 2 | 10 |
| A → C → F → G → H | 4 | 9 |
| A → C → D → E → B → H | 5 | 14 |

**The path with the fewest edges (2)** does not necessarily have the **lowest total weight (9)**. When routing by distance, duration, or cost, define clearly which metric is being optimized.

### 18.2. This CTE enumerates then selects—it is not Dijkstra

Enumerating simple paths and sorting by `total_weight` yields the right answer on a **small, finite** graph, but computational cost can become prohibitive on large graphs. It is **not Dijkstra's or A\*'s algorithm** implemented with a priority queue and global distance map.

If weighted shortest paths are needed on large graphs, consider a graph library/engine, specialized algorithm, or data model tailored for it. Do not use an unconstrained recursive query for large-scale routing just because it runs fast on an 8-node graph.

### 18.3. Do not generalize these conclusions to negative edge weights

The lab specifies `weight > 0`. With negative weights, certain shortest-path algorithms no longer apply as in the all-positive case, and negative-weight cycles introduce special problems. Always choose algorithms matching the mathematical properties of the data.

## 19. PostgreSQL CYCLE: Standard Cycle Detection Syntax (14+)

Since PostgreSQL 14, `WITH RECURSIVE` supports the `CYCLE` clause:

~~~sql
CYCLE column_name SET is_cycle USING cycle_path
~~~

PostgreSQL generates two extra columns:

- **`is_cycle`:** flags rows that entered a cycle on the specified columns.
- **`cycle_path`:** the tracked path used for cycle detection.

Graph example:

~~~sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 'A'::text

    UNION ALL

    SELECT e.to_id
    FROM walk AS w
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
~~~

The `CYCLE` clause ensures the query **stops expanding a path once a cycle is detected** on the specified key. Rows flagged as cycles can appear in the output, so if you only want non-cyclic steps, add:

~~~sql
WHERE NOT is_cycle
~~~

in the outer query.

### 19.1. CYCLE is path-local; it does not merge multiple paths to the same node

In the lab graph, `D` can be reached via `A → B → D` and `A → C → D`. Neither **forms a cycle on its respective path**, so multiple rows for `D` can appear. `CYCLE` detects **revisiting a node already on the current path**; it does not collapse the result into a deduplicated list of reachable nodes.

If you only need the set of reachable nodes, the `UNION` query keeping only `node_id` in Section 15.1 is usually shorter and better suited.

### 19.2. Using multiple columns as the cycle-detection key

In some graphs, a node/relation is identified by a **composite key**, such as `(tenant_id, node_id)`. PostgreSQL lets you list multiple columns in `CYCLE` matching the tracked key. Choose a **sufficiently unique identifier**, because tracking a non-unique column can falsely flag cycles or confuse nodes across tenants.

### 19.3. CYCLE does not fix source data

`CYCLE` only changes the behavior of the **recursive query**. It does not add constraints to the table, repair bad edges, or ensure future `INSERT`/`UPDATE` operations keep data acyclic.

In a self-referencing tree table, to **prevent moving a node under its own subtree**, enforce safe validation/updates at the database/application layer. A `CYCLE` query helps detect and handle cycles when reading, not act as an automatic constraint across DML.

## 20. Using SEARCH and CYCLE Together

You can combine `SEARCH` to build an ordering key with `CYCLE` to detect loops:

~~~sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 'A'::text

    UNION ALL

    SELECT e.to_id
    FROM walk AS w
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    bfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY bfs_order, cycle_path;
~~~

Here:

1. `SEARCH BREADTH FIRST` creates the display-order column.
2. `CYCLE` adds cycle-detection flag and path columns.
3. The outermost `ORDER BY` establishes final result ordering.

When **depth-first** ordering is desired alongside cycle detection, `SEARCH DEPTH FIRST` and `CYCLE` may track overlapping path data, causing unnecessary overhead. If `cycle_path` already supports the desired ordering, you can sort by it without computing a separate DFS order—verify types and actual display goals.

### 20.1. Do not assume SEARCH/CYCLE work in every PostgreSQL version

`SEARCH` and `CYCLE` are supported from **PostgreSQL 14** onward. On older servers, those clauses cause syntax errors. Use a `path_ids` array with `NOT node_id = ANY(path_ids)` or a deduplication/termination strategy compatible with your server version.

## 21. Protecting Against Cycles When Tree Tables Are Mis-Edited

In user-editable tree data where parents can be changed, a common update bug is:

~~~text
1 -> 2 -> 5 -> 8
           ^
           |
           8 gets assigned as the parent of 2
~~~

Setting `2.parent_id = 8` creates a cycle `2 → 5 → 8 → 2` in child → parent links. This **may not violate the foreign key**, since every ID exists.

### 21.1. Checking before moving a branch

Idea: before assigning node `2` under new parent `8`, check **whether the proposed parent is inside node 2's subtree**.

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        node_id,
        parent_id,
        ARRAY[node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        d.path_ids || child.node_id
    FROM cte_lab_164.org_nodes AS child
    JOIN descendants AS d
        ON child.parent_id = d.node_id
    WHERE NOT child.node_id = ANY(d.path_ids)
)
SELECT EXISTS (
    SELECT 1
    FROM descendants
    WHERE node_id = 8
) AS proposed_parent_is_in_subtree;
-- true: 2 must not be moved under 8.
~~~

If the result is `TRUE`, that update would introduce a cycle into the previously valid tree.

**Concurrency warning:** running `SELECT EXISTS` before `UPDATE` across two concurrent transactions may not preserve the invariant if data changes between check and write. Systems requiring strictly acyclic trees need appropriate transaction/locking design or centralized/trigger-based enforcement, tested under concurrent updates.

### 21.2. Checking for cycles from every node, not just roots

A cycle might be completely disconnected from any `parent_id IS NULL` node; a forest query starting at roots would **miss that component**. To audit all parent chains, start from **every node** and walk upward while tracking the path:

~~~sql
WITH RECURSIVE parent_walk AS (
    SELECT
        n.node_id AS start_id,
        n.node_id AS current_id,
        n.parent_id,
        ARRAY[n.node_id]::bigint[] AS path_ids,
        FALSE AS cycle_found
    FROM cte_lab_164.org_nodes AS n

    UNION ALL

    SELECT
        w.start_id,
        parent.node_id,
        parent.parent_id,
        w.path_ids || parent.node_id,
        parent.node_id = ANY(w.path_ids)
    FROM parent_walk AS w
    JOIN cte_lab_164.org_nodes AS parent
        ON parent.node_id = w.parent_id
    WHERE NOT w.cycle_found
)
SELECT DISTINCT
    start_id
FROM parent_walk
WHERE cycle_found
ORDER BY start_id;
~~~

On our valid lab schema, the result is **0 rows**. If parent–child cycles exist, this reveals nodes whose upward chain enters a cycle.

This query walks from **every node**, which can be expensive on large trees. It illustrates one auditing technique, not a claim that it is the cheapest audit for all systems.

### 21.3. An FK does not enforce tree invariants

`FOREIGN KEY (parent_id) REFERENCES org_nodes(node_id)` only guarantees **the referenced parent exists**. It does not guarantee:

- Exactly one root exists;
- Every node connects to a root;
- No cycles exist;
- Maximum depth is respected;
- A node cannot be moved into a business-restricted branch.

Add corresponding rules and checks whenever the application requires these invariants.

## 22. Combining Aggregation Over a Subtree

A practical problem is computing **the revenue of a department and all its sub-units**, or the total cost of a dependency hierarchy.

Create a sample metrics table:

~~~sql
CREATE TABLE cte_lab_164.node_budget (
    node_id BIGINT PRIMARY KEY
        REFERENCES cte_lab_164.org_nodes(node_id),
    monthly_budget NUMERIC(14, 2) NOT NULL
        CHECK (monthly_budget >= 0)
);

INSERT INTO cte_lab_164.node_budget
    (node_id, monthly_budget)
VALUES
    (1,  1000000),
    (2,   500000),
    (3,   300000),
    (4,   250000),
    (5,   150000),
    (6,   100000),
    (7,   120000),
    (8,    80000),
    (9,    60000),
    (10,   70000),
    (11,  200000),
    (12,   40000),
    (13,   50000);
~~~

### 22.1. Summing the budget of the Engineering branch

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    COUNT(*) AS node_count,
    SUM(b.monthly_budget) AS total_monthly_budget
FROM subtree AS s
JOIN cte_lab_164.node_budget AS b
    ON b.node_id = s.node_id;
~~~

The nodes in the Engineering branch are `2, 4, 5, 6, 7, 8`. Total budget:

~~~text
500000 + 250000 + 150000 + 100000 + 120000 + 80000
= 1200000
~~~

Result: **6 nodes, total 1,200,000**.

### 22.2. NULLs and join behavior

If `node_budget` only has rows for **some nodes**, an inner `JOIN` drops nodes without a budget row. To retain every node in the subtree:

~~~sql
SELECT
    COUNT(*) AS all_nodes,
    COUNT(b.node_id) AS nodes_with_budget,
    SUM(b.monthly_budget) AS sum_known_budget
FROM subtree AS s
LEFT JOIN cte_lab_164.node_budget AS b
    ON b.node_id = s.node_id;
~~~

This snippet is an **expression example** for the outer SELECT of a `subtree` CTE; it cannot run standalone without defining the CTE in the same SQL statement.

`COUNT(*)` and `COUNT(b.node_id)` can differ. Do not automatically treat unknown budgets as 0 in financial reports without an explicit data rule.

### 22.3. Double counting in graphs

In a tree, each node has only one path from the root, so `SUM(budget)` over the subtree works naturally. In a graph with multiple paths to the same node, recursive output may contain **multiple rows for one `node_id`**, causing that node's budget to be summed multiple times.

If the requirement calls for summing **each reachable node only once**, isolate the distinct node set first and then join metrics:

~~~sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 'A'::text
    UNION
    SELECT e.to_id
    FROM reachable AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT COUNT(*) AS distinct_reachable_nodes
FROM reachable;
-- 8
~~~

This principle is especially important when aggregating **costs, permissions, coverage, or user counts** on graphs with multiple incoming edges per node.

## 23. Branch Pruning and Filtering Inside the Recursive Term

To reduce work, place expansion-stopping filters inside the **recursive term** whenever business logic allows.

### 23.1. Traversing at most three levels

~~~sql
WITH RECURSIVE limited AS (
    SELECT
        node_id, parent_id, node_name, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        l.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN limited AS l
        ON child.parent_id = l.node_id
    WHERE l.depth < 3
)
SELECT *
FROM limited
ORDER BY depth, node_id;
~~~

The depth cap prevents generating level 4 and beyond.

### 23.2. Traversing only active nodes

~~~sql
WITH RECURSIVE active_tree AS (
    SELECT
        node_id, parent_id, node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1
      AND is_active

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN active_tree AS t
        ON child.parent_id = t.node_id
    WHERE child.is_active
)
SELECT *
FROM active_tree;
~~~

If an intermediate node has `is_active = FALSE`, this query **does not traverse through it**, and therefore **does not reach descendants beneath it**, even if those descendants have `is_active = TRUE`. That is a **business decision**; if the goal is "find all active descendants even under inactive parents", traverse through inactive nodes and filter them out in the outer SELECT.

### 23.3. Filtering in the outer SELECT does not always reduce passes

Compare:

~~~sql
-- Case A: drops deep levels at the end (still traverses deeper).
SELECT * FROM subtree WHERE depth <= 3;
~~~

with a condition inside the recursive term:

~~~sql
WHERE previous_step.depth < 3
~~~

The second approach proactively **avoids generating level 4**, which is usually better when at most three levels are needed. Filters placed inside the recursion must not inadvertently discard intermediate nodes required to reach the target.

## 24. LIMIT, ORDER BY, and Misinterpreting Termination

One debugging tip mentioned in PostgreSQL documentation is adding `LIMIT` to the outer SELECT when testing a potentially looping CTE. In some cases, PostgreSQL only pulls as many rows as the parent query requests, so it may **stop computing further recursive rows**.

However, **never use an outer `LIMIT` as a formal cycle-prevention mechanism**:

- An `ORDER BY` or `JOIN` in the parent query may require fetching **the entire result** before limiting.
- The planner, CTE usage, and query changes can alter behavior.
- `LIMIT 10` does not prove the traversal finished properly—only that you asked to display at most 10 rows.
- A heavily branching graph can still produce vast amounts of data before filtering/sorting.

A safer pattern for graph work is **putting cycle-avoiding path conditions directly in the recursive term**, bounding depth where appropriate, testing on small datasets, and configuring operational timeouts.

### 24.1. Timeout inside a lab transaction

~~~sql
BEGIN;

SET LOCAL statement_timeout = '5s';

-- Run a bounded recursive query on understood data.
SELECT COUNT(*) FROM cte_lab_164.org_nodes;

ROLLBACK;
~~~

`SET LOCAL` applies only within the current transaction. This shows how to cap execution time for a lab operation; it **does not replace** writing a properly terminating query, and must not be used to "patch over" broken data or algorithms.

## 25. EXPLAIN and Recursive CTE Performance

### 25.1. Observing Recursive Union and WorkTable Scan

~~~sql
EXPLAIN
WITH RECURSIVE subtree AS (
    SELECT
        node_id, parent_id, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT *
FROM subtree;
~~~

A plan may show nodes such as:

- **Recursive Union:** combines the anchor and recursive steps under recursive evaluation.
- **WorkTable Scan:** reads working-table rows for the current pass.
- **Index Scan/Hash Join/Seq Scan:** how the planner finds child nodes in the base table.
- **CTE Scan:** reads the recursive CTE output in the outer query.

The exact plan shape varies with statistics, row counts, PostgreSQL version, and indexes. `EXPLAIN` only provides **estimated plans**, not actual execution timings.

### 25.2. Important indexes

For an adjacency list:

~~~sql
CREATE INDEX idx_org_nodes_parent
ON cte_lab_164.org_nodes(parent_id);
~~~

This index was already created in Section 4.1, so **do not re-run the creation statement** if the index already exists. It helps PostgreSQL locate children via `child.parent_id = current.node_id` in many scenarios.

For graphs:

- An index leading with `from_id` supports finding outgoing edges. The `graph_edges` table already has **primary key `(from_id, to_id)`**, providing a suitable index for many queries filtering on `from_id`.
- An index on `to_id` helps when frequently finding **nodes pointing into a node**, i.e., reverse-edge traversal.
- Do not blindly create a redundant index duplicating the primary key just because you see a join on that column.

### 25.3. Cost depends on the number of expanded edges

A tree with `N` nodes has roughly `N-1` edges per rooted component. A query visiting each node once can perform reasonably well with good indexes and without excessively long paths.

A graph with millions of edges or many converging paths is different:

- `UNION ALL` without deduplication can expand huge numbers of paths.
- `UNION` must maintain seen tuples to deduplicate.
- Long `path_ids` arrays increase memory usage and `ANY` check cost.
- `SEARCH` and `ORDER BY` may require large sorts.
- Computing all ancestor–descendant pairs can produce far more rows than nodes.

There is no universal "recursive CTEs are always fast/slow" rule across all models. Evaluate **tree/graph size, branching distribution, depth, query goal, and latency targets**.

### 25.4. Considering storage models when tree reads are very frequent

| Model | Advantages | Trade-offs |
| --- | --- | --- |
| Adjacency list (`parent_id`) | Easy writes, easy reparenting, compact data | Multi-level ancestor/descendant queries require recursion |
| Materialized path | Path-based queries can be convenient | Reparenting must update paths of descendant nodes |
| Closure table (ancestor, descendant, depth) | Fast ancestor/descendant queries when indexed | More rows and relationship-maintenance overhead |
| Nested sets | Convenient for certain subtree reads | Structural updates can be complex |
| Graph-oriented storage/engine | Suited for deep path/graph analytics | Adds system components and operational overhead |

`WITH RECURSIVE` handles many cases cleanly on an adjacency list, but does not replace choosing an appropriate physical structure when the workload is large-scale graph querying.

### 25.5. EXPLAIN ANALYZE executes the real query

~~~sql
-- Use only in a safe environment with a properly terminating query:
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1
    UNION ALL
    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT COUNT(*) FROM subtree;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the query** to measure actual row counts, timing, and I/O/buffers where supported. Avoid running it on production before evaluating cost, especially for recursive graph queries with many paths or unverified cycle controls.

## 26. SQL Limitations and Recursive-Term Design Notes

### 26.1. Recursive CTEs must preserve column structure

Anchor and recursive branches must return the **same number of columns** with compatible types. For example, if the anchor has:

~~~sql
SELECT 0::integer AS depth, ARRAY[1]::bigint[] AS path
~~~

then the recursive term must return matching types:

~~~sql
SELECT depth + 1, path || child.node_id
~~~

With a `bigint[]` path column, concatenating an arbitrary mismatched text value will fail.

### 26.2. Do not arbitrarily use aggregates/windows in the recursive term

PostgreSQL enforces syntactic restrictions on the recursive reference and recursive term. Constructs like `GROUP BY`, aggregate functions, or window functions cannot be placed freely in the self-referencing part.

A usually safer pattern is:

1. Inside the recursion, carry only the data needed to follow edges.
2. Once recursion completes, use the outer query to `GROUP BY`, `COUNT`, `SUM`, or `ROW_NUMBER` as needed.

Example:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT COUNT(*) AS subtree_size
FROM subtree;
~~~

### 26.3. A recursive CTE is not a persistent cache

A recursive CTE's result is computed for the **current query only**. It does not become a cached table that stays updated when parent–child links change. If the same hierarchy is queried repeatedly, design a cache, materialized view, or closure table with an appropriate sync strategy.

### 26.4. Results change when DDL/DML modifies the tree

When the tree is updated, a query reading at a different snapshot sees updated relationships. Operations like "move an entire subtree" require transactions, locking, and cycle-prevention rules—not just a one-off traversal followed by uncoordinated updates.

### 26.5. Tree security and authorization

If a system restricts each user to authorized departments, the recursive query must account for **authorized scope**. A node appearing inside a subtree does not imply the user is permitted to read every record there.

In particular, decide:

- Is **traversing through a hidden node** to reach an authorized descendant allowed?
- Is inferring the existence of a hidden node via depth/path allowed?
- Are tenant relationships isolated?
- Which RLS rules, views, and roles apply?

These are **security policies**, not something solved merely by `WITH RECURSIVE`. Review both the SQL and the permission model.

## 27. Practice Exercises

The exercises below use the `cte_lab_164` schema created in this lesson. Some ask you to write queries yourself; hints help identify the anchor and join direction.

### Exercise 1 — Traversing the tree from the root

Write a recursive CTE starting at `node_id=1`, returning `node_id`, `parent_id`, `node_name`, and `depth`, ordered by `ORDER BY depth, node_id`.

**Check answer:** **10 rows**, maximum depth **3**.

### Exercise 2 — Subtree of Engineering

Change the anchor to `node_id=2`. Count nodes including the starting node and descendants excluding the starting node.

**Expected:** **6 nodes** total, **5 descendants**.

### Exercise 3 — Ancestors of Analytics

From node `8`, trace `parent_id` back to the root using a recursive term. Display top-down from root:

~~~text
Company → Engineering → Data → Analytics
~~~

**Hint:** join `parent.node_id = current.parent_id`.

### Exercise 4 — Breadcrumb

Build a path using a `text[]` array and `array_to_string(path, ' / ')`. Why must you **prepend the parent name** when walking bottom-up from a leaf, whereas when walking top-down from the root you append the child name?

### Exercise 5 — Multi-root forest

Anchor all nodes with `parent_id IS NULL` and propagate `root_id` downward. Aggregate node counts and max depth per root.

**Answer:** `root_id=1` has 10 nodes, max depth 3; `root_id=11` has 3 nodes, max depth 1.

### Exercise 6 — Leaf nodes

Find all leaves in the `Company` subtree using `NOT EXISTS`. If you needed leaves within the **displayed subset** rather than the full table, describe how the condition would change.

**Answer:** `6, 7, 8, 9, 10`.

### Exercise 7 — Limiting depth

Modify the CTE to traverse at most two levels below node `1`. Explain the difference between placing `WHERE s.depth < 2` inside the recursive term versus placing `WHERE depth <= 2` in the outer SELECT.

### Exercise 8 — Finding reachable nodes

On `graph_edges`, use `WITH RECURSIVE reachable(node_id)` and `UNION` (without storing depth/path) to list every node reachable from `A`.

**Answer:** `A, B, C, D, E, F, G, H`.

### Exercise 9 — Why can UNION fail to stop when depth is added?

Write an explanation—**without running an unguarded query**—of rows `('B',1)` and `('B',4)` generated via cycle `B→D→E→B`. Why does `UNION` not treat them as duplicates?

### Exercise 10 — Path-local cycle detection

Write a CTE with `path_ids TEXT[]` and the condition:

~~~sql
WHERE NOT e.to_id = ANY(p.path_ids)
~~~

List simple paths from `A` to `H`. **Expected:** includes `A→B→H` and `A→C→F→G→H`.

### Exercise 11 — Shortest hops vs. least weight

Compute edge counts and total `weight` for simple paths `A→H`. Compare:

- Fewest edges: `A→B→H` with **2 edges**.
- Lower total weight: `A→C→F→G→H` with **weight 9**.

Explain why fewest edges does not mean lowest cost.

### Exercise 12 — SEARCH BREADTH FIRST

On PostgreSQL 14+, use `SEARCH BREADTH FIRST BY node_id SET bfs_order` on the `Company` tree, then `ORDER BY bfs_order`. Compare the output order with `ORDER BY depth, node_id`.

### Exercise 13 — SEARCH DEPTH FIRST

Similar to Exercise 12, but use `SEARCH DEPTH FIRST`. Explain why `SEARCH` generates a display order **without turning the engine into a custom DFS execution algorithm**.

### Exercise 14 — CYCLE

On PostgreSQL 14+, apply:

~~~sql
CYCLE node_id SET is_cycle USING cycle_path
~~~

to a traversal from `A`. Find a cyclic path and inspect `is_cycle`. When filtering with `WHERE NOT is_cycle`, do paths reaching the same node via two different branches automatically collapse into a single row?

**Answer:** no; `CYCLE` controls cycles along a path and does not deduplicate all paths reaching the same node.

### Exercise 15 — Checking a subtree move

Before placing `node 2` under `node 8`, run a query finding `node 2`'s subtree and check whether node 8 is inside it.

**Answer:** yes, so the operation would create a cycle and must be rejected by tree-integrity rules. Why is a `FOREIGN KEY` alone insufficient to block this change?

### Exercise 16 — Subtree budget sum

From `node_id=2`, descend through all child nodes and join `node_budget` to compute the total.

**Answer:** **1,200,000** across **6 nodes**.

If a node lacks a budget row, how do `JOIN` and `LEFT JOIN` differ? When should `COUNT(b.node_id)` be paired with `COUNT(*)` to report completeness?

### Exercise 17 — Counting descendants for all nodes

Make every node an anchor and carry `ancestor_id`. Write an aggregate counting descendants excluding the node itself. Explain why this query can generate **O(N²)** rows on a deep chain-like tree.

### Exercise 18 — Filtering inactive nodes

Suppose an intermediate node has `is_active=FALSE` while its children remain active. Compare:

1. Traversing only through active nodes.
2. Traversing all nodes, then filtering active nodes at the end.

Do both give the same result set? Which business scenarios call for each approach?

### Exercise 19 — Subtree authorization

A user may only view nodes belonging to `tenant_id=5`. Describe how to ensure traversal does not leak nodes from other tenants. Is relying only on paths or `WHERE root_id=...` sufficient for access control?

**Hint:** tenant/role/RLS controls, object read permissions, and policy on traversing through hidden nodes are required.

### Exercise 20 — Choosing a storage model

Compare adjacency list, closure table, and materialized path for three workloads:

- Frequent reparenting, infrequent full-subtree queries.
- Rendering a tree thousands of times per minute, rare structural changes.
- Cyclic graphs with many paths, finding minimum-cost routes.

For each workload, state a starting solution, performance risks, and how to validate on realistic data.

## 28. Mental Checklist When Writing a New Recursive CTE

1. **Is the input a tree or a graph?** Can nodes have multiple parents or cycles?
2. **What is the anchor?** One node, one root, all roots, or every node?
3. **Which edge direction is traversed?** Parent → child, child → parent, or from → to?
4. **What is the unit of output?** Unique nodes, each path, ancestor–descendant pairs, or reachable set?
5. **Which columns must carry across passes?** ID, depth, path, root, weight, metadata?
6. **How does the query terminate?** Exhausted edges, visited set, `CYCLE`, or depth limit?
7. **Do `UNION` and `UNION ALL` fit the goal?** Deduplicate whole rows or preserve each path?
8. **Is BFS/DFS just display ordering or an algorithm needing global state?** Is there an explicit `ORDER BY`?
9. **Is there path-explosion risk?** Need branch pruning, limits, or a different algorithm?
10. **Are there indexes matching join direction?** `parent_id`, `from_id`, `to_id`?
11. **Is aggregation at the right level?** Avoid double-counting/summing nodes when a graph has multiple paths.
12. **Are permissions and consistency rules enforced?** Prevent leaking hidden data or reading a corrupted tree under uncontrolled updates.

## 29. Official PostgreSQL Documentation

The following documentation describes syntax, semantics, and execution details for recursive queries:

- [PostgreSQL — WITH Queries: Recursive Queries](https://www.postgresql.org/docs/current/queries-with.html#QUERIES-WITH-RECURSIVE): anchor/recursive terms, working table, `UNION`/`UNION ALL`, search order, and cycle detection.
- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `WITH RECURSIVE`, `SEARCH`, `CYCLE`, and outermost clauses.
- [PostgreSQL — Arrays](https://www.postgresql.org/docs/current/arrays.html): creating arrays, concatenation, and storing paths in arrays.
- [PostgreSQL — Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): `array_to_string` and array operations.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): inspecting execution plans.
- [PostgreSQL — WITH / CTE Materialization](https://www.postgresql.org/docs/current/queries-with.html): evaluation behavior and optimization boundaries for CTEs.

`/docs/current/` points to documentation for the current stable release. If your server runs PostgreSQL 13 or another specific version, check the documentation for that exact **major version**, especially before using `SEARCH` and `CYCLE`.

## 30. Summary

**`WITH RECURSIVE` enables PostgreSQL to query multi-level relationships directly in SQL.** A query consists of an **anchor** producing starting nodes, a **recursive term** following edges to produce subsequent nodes, and `UNION ALL`/`UNION` combining results across passes until no new rows remain. On valid trees, `JOIN child.parent_id = current.node_id` retrieves descendants; reversing the join direction retrieves ancestors, paths, and breadcrumbs.

On graphs, the problem is trickier because **a node can be reached by multiple paths and cycles can exist**. `UNION` deduplicating whole rows fits when only reachable nodes are needed; `UNION ALL` with a **path array** enumerates simple paths, provided you check that the target node is not already in the path. Starting in PostgreSQL 14, `SEARCH` produces BFS/DFS display orders, and `CYCLE` detects and stops expanding cyclic paths.

A correct recursive query clearly answers **whether it seeks nodes or paths, depth or weight, deduplication or preservation, and what guarantees termination**. Finally, monitor performance, add indexes matching traversal direction, enforce authorization, and remember that a self-referencing FK **does not automatically prevent all cycles**. Understanding these principles lets you use PostgreSQL to solve hierarchical and graph problems reliably rather than just tweaking queries until output appears.
