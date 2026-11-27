# Materialized Path, Nested Sets, and Closure Table Models

In a product taxonomy, department structure, forum, or folder tree, a record typically has a **parent**, **children**, **ancestors**, and **descendants**. Those relationships form a **hierarchy (tree)**. Data design must answer both questions: *how do we represent the tree accurately?* and *how do we query and update the tree efficiently?*

This lesson compares three techniques for storing ancestor–descendant relationships in a relational database:

- **Materialized path:** stores a path from the root to each node.
- **Nested sets:** assigns left and right boundary numbers to each node to represent containment intervals.
- **Closure table:** stores every ancestor–descendant pair together with its distance.

All three clarify hierarchical queries, yet differ substantially in storage overhead, node insertion, moving branches, upward path queries, and consistency enforcement. This belongs to the **Inheritance and Hierarchies** chapter in the **DATABASE_DATA_MODELING** module: turning business requirements into suitable, verifiable, and evolvable data structures, keys, constraints, and indexes.

> **Scope:** The techniques below mainly examine **trees** or **forests** (each node has at most one parent). They are not synonymous with IS-A entity type inheritance. A `Product` may be a `DigitalProduct` under an IS-A relationship, whereas a `Category` having a parent `Category` is a hierarchical relationship among **records of the same type**. If a node can have multiple parents, the data is a **directed graph**, usually a DAG, and assumptions about paths, depth, and ancestors must be revisited.

## 1. Sample Problem and Common Queries

Suppose a product catalog has the following structure:

~~~text
1  Products
├── 2  Electronics
│   ├── 4  Phones
│   │   └── 6  Android
│   └── 5  Laptops
└── 3  Fashion
~~~

In this example:

- The **direct parent** of Phones is Electronics.
- The **ancestors** of Android are Phones, Electronics, and Products.
- The **descendants** of Electronics are Phones, Laptops, and Android.
- The **subtree** of Electronics includes Electronics itself and all descendants.
- A node's **depth** is measured from the root: Products is at depth 0, Android is at depth 3.

Key business scenarios include: displaying an entire subtree; building a breadcrumb from root to node; fetching direct children; counting nodes in a branch; moving a category to a new parent; preventing cycles; deleting or archiving an entire branch; and finding nodes within the same tree.

A good design must clarify:

1. **Cardinality:** does each node have exactly one parent, no parent if it is a root, or are multiple parents allowed?
2. **Root management:** is there one shared root or multiple trees in the same system?
3. **Dominant operations:** are subtree reads far more common than moving nodes, or is the structure edited continuously?
4. **Scale and limits:** how many nodes does the tree have, how deep is it, and how many concurrent writers exist?
5. **Deletion semantics:** delete the branch, promote children upward, block deletion, or mark deprecated?
6. **Isolation scope:** which organization, tenant, or catalog version does the tree belong to?

### Baseline Reference: Adjacency List

The foundational approach stores a **parent key** on each row. It minimizes duplicate data and serves as a suitable source of truth from which to maintain materialized structures.

~~~sql
-- PostgreSQL
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   BIGINT REFERENCES categories(category_id),
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

INSERT INTO categories (category_id, name, parent_id) VALUES
    (1, 'Products', NULL),
    (2, 'Electronics', 1),
    (3, 'Fashion', 1),
    (4, 'Phones', 2),
    (5, 'Laptops', 2),
    (6, 'Android', 4);
~~~

Foreign keys guarantee the parent exists; `CHECK` only blocks direct self-parenting, not longer cycles such as `A → B → C → A`. Preventing cycles requires checking the full ancestor chain or enforcing it in write workflows.

Querying descendants using a recursive CTE:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT category_id, name, parent_id, 0 AS relative_depth
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT child.category_id, child.name, child.parent_id,
           subtree.relative_depth + 1
    FROM categories AS child
    JOIN subtree ON child.parent_id = subtree.category_id
)
SELECT category_id, name, relative_depth
FROM subtree
ORDER BY relative_depth, category_id;
~~~

The result returns Electronics (0), Phones and Laptops (1), and Android (2). **Adjacency lists** are quite convenient for inserts and direct parent updates, yet fetching an entire branch requires recursion. The three models below intentionally store extra information to speed up specific query patterns.

## 2. Materialized Path

### 2.1. Storage Layout

Each node stores **the full sequence of identifiers from the root to itself**, for example:

| category_id | name | parent_id | path |
| ---: | --- | ---: | --- |
| 1 | Products | NULL | /1/ |
| 2 | Electronics | 1 | /1/2/ |
| 3 | Fashion | 1 | /1/3/ |
| 4 | Phones | 2 | /1/2/4/ |
| 5 | Laptops | 2 | /1/2/5/ |
| 6 | Android | 4 | /1/2/4/6/ |

The convention of leading and trailing **/** delimiters helps identify ID boundaries: searching prefix **/1/2/** will not falsely match **/1/20/**. The path contains stable identifiers rather than display names so renaming a category does not require rewriting the entire branch.

Dedicated schema example for this technique:

~~~sql
CREATE TABLE path_categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   BIGINT REFERENCES path_categories(category_id),
    path        TEXT NOT NULL UNIQUE,
    CONSTRAINT path_has_delimiters CHECK (
        left(path, 1) = '/' AND right(path, 1) = '/'
    ),
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

INSERT INTO path_categories
    (category_id, name, parent_id, path)
VALUES
    (1, 'Products', NULL, '/1/'),
    (2, 'Electronics', 1, '/1/2/'),
    (3, 'Fashion', 1, '/1/3/'),
    (4, 'Phones', 2, '/1/2/4/'),
    (5, 'Laptops', 2, '/1/2/5/'),
    (6, 'Android', 4, '/1/2/4/6/');
~~~

This is an **illustrative** schema. Delimiter checks, `UNIQUE`, and `FK` **do not yet verify** that `path` truly equals the parent's path concatenated with `category_id`, nor do they prevent fabricated paths or cycles. In a real system, enforce that invariant via transactional write logic, suitable triggers, or a more constrained representation.

### 2.2. Querying with Prefixes

The entire subtree of Electronics, **including the Electronics node**:

~~~sql
SELECT category_id, name, path
FROM path_categories
WHERE path LIKE '/1/2/%'
ORDER BY path;
~~~

The prefix includes the delimiter so node ID 20 under the root is not falsely matched. If you want descendants **excluding the subtree root**, add `category_id <> 2`.

Finding the breadcrumb to Android, including Android:

~~~sql
SELECT ancestor.category_id, ancestor.name
FROM path_categories AS ancestor
JOIN path_categories AS target
  ON target.category_id = 6
WHERE target.path LIKE ancestor.path || '%'
ORDER BY length(ancestor.path), ancestor.category_id;
~~~

This assumes path segments consist only of numeric IDs and delimiters, containing no `LIKE` wildcards (**%** or **_**). If paths contain arbitrary labels, special characters must be encoded or escaped. Breadcrumb queries matching prefixes across two rows may not use indexes as efficiently as constant-prefix queries.

Querying **direct** children remains easiest with `parent_id = 2`. There is no need to use `LIKE` when you only want one level.

### 2.3. Adding Nodes and Moving Branches

Adding `Tablet` under `Electronics` (ID 2): read the parent's path, append the new ID by convention, and insert both `parent_id` and `path` **in the same transaction**. Simple case:

~~~sql
INSERT INTO path_categories (category_id, name, parent_id, path)
SELECT 7, 'Tablet', p.category_id,
       p.path || '7/'
FROM path_categories AS p
WHERE p.category_id = 2;
~~~

Before inserting, ensure the new ID does not already exist and protect against concurrent branch moves changing the parent's path. In production systems, move operations typically require locking or serialization at tree scope.

**Moving the entire Phones branch from Electronics to Fashion** means changing the prefix:

~~~text
Before:
  /1/2/4/        Phones
  /1/2/4/6/      Android

After:
  /1/3/4/        Phones
  /1/3/4/6/      Android
~~~

An illustrative update, **valid only after old/new prefixes are verified**, the target does not lie inside the source branch, and the transaction holds appropriate locks:

~~~sql
BEGIN;

UPDATE path_categories
SET path = '/1/3/4/' ||
           substr(path, length('/1/2/4/') + 1),
    parent_id = CASE WHEN category_id = 4 THEN 3 ELSE parent_id END
WHERE path LIKE '/1/2/4/%';

COMMIT;
~~~

The statement updates **every node in the subtree**; only the branch root changes `parent_id`, while Android's `parent_id` remains 4. You cannot update the path only on Phones because descendants would retain stale paths. When moving a large branch, write cost and locked row count grow with **subtree size**.

### 2.4. Indexes and Specialized Path Types

In PostgreSQL, a B-tree index for prefix matching can use an operator class:

~~~sql
CREATE INDEX idx_path_categories_prefix
ON path_categories (path text_pattern_ops);

CREATE INDEX idx_path_categories_parent
ON path_categories (parent_id);
~~~

A `text_pattern_ops` index helps fixed-prefix `LIKE` queries under many collation settings; the DBMS still decides between index usage and table scans based on statistics, selectivity, and query shape.

If PostgreSQL's **ltree** extension is available, paths can be stored as dot-separated labels **n1.n2.n4**, using the **<@** operator (left path is a descendant of or equal to right path) and a GiST index for hierarchical queries. Verify extension support, label rules, and index plans before choosing it.

**Best suited when:** the tree changes infrequently, subtree/breadcrumb reads are heavy, a readable schema is desired, and full-branch updates on moves are acceptable.

## 3. Nested Sets

### 3.1. Interval Numbering Idea

The **nested sets** model performs a depth-first traversal and assigns each node two numbers: **lft** (left bound) and **rgt** (right bound). A parent node's interval **completely contains** the intervals of all its descendants.

One numbering for the sample tree:

~~~text
Products       [1,12]
├── Electronics [2, 9]
│   ├── Phones     [3,6]
│   │   └── Android [4,5]
│   └── Laptops    [7,8]
└── Fashion        [10,11]
~~~

| category_id | name | lft | rgt |
| ---: | --- | ---: | ---: |
| 1 | Products | 1 | 12 |
| 2 | Electronics | 2 | 9 |
| 4 | Phones | 3 | 6 |
| 6 | Android | 4 | 5 |
| 5 | Laptops | 7 | 8 |
| 3 | Fashion | 10 | 11 |

Key relationships:

- Node **A** is an ancestor of **B** if **A.lft < B.lft** and **A.rgt > B.rgt**.
- **Leaves** satisfy **rgt = lft + 1**, under this contiguous traversal numbering convention.
- **Number of nodes in the subtree** including the node itself is **(rgt − lft + 1) / 2**, assuming contiguous numbering with one bound pair per node.
- Intervals of two different branches must be **disjoint**, whereas parent/child intervals must **strictly nest**; partial overlaps are forbidden.

In standard nested sets, boundary values are **structural coordinates**, not entity IDs. Adding or moving one node can cause many boundary values to change.

### 3.2. Schema and Queries

~~~sql
CREATE TABLE nested_categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    lft         INTEGER NOT NULL UNIQUE,
    rgt         INTEGER NOT NULL UNIQUE,
    CHECK (lft > 0),
    CHECK (lft < rgt)
);

INSERT INTO nested_categories (category_id, name, lft, rgt) VALUES
    (1, 'Products', 1, 12),
    (2, 'Electronics', 2, 9),
    (4, 'Phones', 3, 6),
    (6, 'Android', 4, 5),
    (5, 'Laptops', 7, 8),
    (3, 'Fashion', 10, 11);
~~~

Fetching the entire subtree of Electronics, including itself:

~~~sql
SELECT child.category_id, child.name, child.lft, child.rgt
FROM nested_categories AS parent
JOIN nested_categories AS child
  ON child.lft >= parent.lft AND child.rgt <= parent.rgt
WHERE parent.category_id = 2
ORDER BY child.lft;
~~~

Fetching ancestors of Android, including Android itself:

~~~sql
SELECT ancestor.category_id, ancestor.name
FROM nested_categories AS target
JOIN nested_categories AS ancestor
  ON ancestor.lft <= target.lft AND ancestor.rgt >= target.rgt
WHERE target.category_id = 6
ORDER BY ancestor.lft;
~~~

Counting nodes in a branch:

~~~sql
SELECT category_id, name,
       (rgt - lft + 1) / 2 AS subtree_node_count
FROM nested_categories
WHERE category_id = 2;
-- Result in the example: 4 nodes (Electronics, Phones, Android, Laptops).
~~~

Interval comparisons allow ancestor and descendant queries without recursive traversal. However, nested sets **do not directly store the immediate parent**. If displaying one level of direct children is frequent, consider also storing `parent_id` and keeping it synchronized with intervals, or using a query to derive the nearest enclosing parent from intervals.

### 3.3. Why Are Tree Modifications Expensive?

When inserting a node in the middle of traversal order, you must **open space for two new bounds**, typically shifting `lft`/`rgt` values after the insertion point. When deleting or moving an entire branch, you must **close the old gap**, **open a new gap**, and recompute bounds of affected nodes.

Even adding a single leaf node may require updating **many rows outside the leaf's branch**. Moving a large subtree can trigger widespread writes and lock contention, especially if multiple users edit the catalog concurrently.

**Do not** attempt to move a branch by changing only the branch root's `lft`/`rgt`. That breaks the descendant containment invariant.

The `CHECK(lft < rgt)` and `UNIQUE` constraints in the DDL above only catch local errors and duplicate bounds. They **do not automatically guarantee** that intervals form a valid nested sets tree: two partially intersecting intervals or gaps in numbering can still exist. Centralized write logic, full-tree validation, and concurrency-controlled transactions are required.

### 3.4. Indexes

~~~sql
CREATE INDEX idx_nested_categories_lft
ON nested_categories (lft);

CREATE INDEX idx_nested_categories_rgt
ON nested_categories (rgt);
~~~

The `lft`/`rgt` columns already have `UNIQUE` in the example, so PostgreSQL **already created a unique index** on each column; the two `CREATE INDEX` statements above are **redundant** if keeping that DDL unchanged. They simply illustrate the two range-query directions if you choose a variant schema without those unique indexes. In real designs, **do not create duplicate indexes**; check existing indexes and `EXPLAIN` plans on target queries.

If multiple independent trees exist, you usually need a `tree_id` and must manage bounds per tree; queries must filter by `tree_id`. You cannot compare `lft`/`rgt` across two trees as if they shared one numbering sequence unless the model specifies so.

**Best suited when:** the tree is relatively static, read volume is high, full subtrees are frequently fetched, subtree counts or traversal ordering are needed, and multi-row update costs are acceptable.

## 4. Closure Table

### 4.1. Storing Every Ancestor–Descendant Pair

A **closure table** stores all **(ancestor_id, descendant_id)** pairs existing in the tree, along with **depth** as the number of edges from ancestor to descendant. A common convention includes **self-pairs** with `depth = 0`.

For the sample tree, some closure rows are:

| ancestor_id | descendant_id | depth | Meaning |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Products is itself |
| 1 | 2 | 1 | Products is parent of Electronics |
| 1 | 4 | 2 | Products is two edges above Phones |
| 1 | 6 | 3 | Products is three edges above Android |
| 2 | 4 | 1 | Electronics is parent of Phones |
| 2 | 6 | 2 | Electronics is grandparent of Android |
| 4 | 6 | 1 | Phones is parent of Android |
| 6 | 6 | 0 | Android is itself |

In the sample tree there are 6 nodes and **15 closure rows** when including self-pairs. Row count scales with the sum of ancestors across all nodes plus the node count, so a **linear chain** tree can require $O(N^2)$ rows, whereas balanced trees are substantially smaller, roughly $O(N \log N)$.

### 4.2. Schema: Adjacency List as Source with Closure as Ancestor Index

~~~sql
CREATE TABLE hier_nodes (
    node_id   BIGINT PRIMARY KEY,
    name      TEXT NOT NULL,
    parent_id BIGINT REFERENCES hier_nodes(node_id),
    CHECK (parent_id IS NULL OR parent_id <> node_id)
);

CREATE TABLE hier_closure (
    ancestor_id   BIGINT NOT NULL REFERENCES hier_nodes(node_id) ON DELETE CASCADE,
    descendant_id BIGINT NOT NULL REFERENCES hier_nodes(node_id) ON DELETE CASCADE,
    depth         INTEGER NOT NULL CHECK (depth >= 0),
    PRIMARY KEY (ancestor_id, descendant_id),
    CONSTRAINT valid_closure_depth CHECK (
        (ancestor_id = descendant_id AND depth = 0)
        OR
        (ancestor_id <> descendant_id AND depth > 0)
    )
);

INSERT INTO hier_nodes (node_id, name, parent_id) VALUES
    (1, 'Products', NULL),
    (2, 'Electronics', 1),
    (3, 'Fashion', 1),
    (4, 'Phones', 2),
    (5, 'Laptops', 2),
    (6, 'Android', 4);
~~~

Example building the initial closure table from `parent_id` using a recursive CTE:

~~~sql
WITH RECURSIVE paths AS (
    SELECT node_id AS ancestor_id,
           node_id AS descendant_id,
           0 AS depth
    FROM hier_nodes

    UNION ALL

    SELECT p.ancestor_id, child.node_id, p.depth + 1
    FROM paths AS p
    JOIN hier_nodes AS child
      ON child.parent_id = p.descendant_id
)
INSERT INTO hier_closure (ancestor_id, descendant_id, depth)
SELECT ancestor_id, descendant_id, depth
FROM paths;
~~~

This CTE assumes the input data **is already a valid, acyclic tree** and the closure table is initially empty. Re-running it without clearing existing rows will violate `PRIMARY KEY`. If `parent_id` contains a cycle, recursion may not terminate; before rebuilding closure, run cycle detection and resolve corrupted data.

Some systems omit `parent_id` to reduce redundancy: the **direct parent** relationship is identified by closure rows with `depth = 1`. However, keeping `parent_id` as the authoritative source and closure as a derived structure generally makes editing operations easier to understand, provided both are always updated consistently.

### 4.3. Querying Descendants, Ancestors, and Direct Children

Subtree of Electronics, including Electronics:

~~~sql
SELECT d.node_id, d.name, c.depth AS relative_depth
FROM hier_closure AS c
JOIN hier_nodes AS d ON d.node_id = c.descendant_id
WHERE c.ancestor_id = 2
ORDER BY c.depth, d.node_id;
~~~

Ancestors of Android, from root down to Android itself:

~~~sql
SELECT a.node_id, a.name, c.depth AS distance_to_android
FROM hier_closure AS c
JOIN hier_nodes AS a ON a.node_id = c.ancestor_id
WHERE c.descendant_id = 6
ORDER BY c.depth DESC;
~~~

Direct children of Electronics:

~~~sql
SELECT n.node_id, n.name
FROM hier_closure AS c
JOIN hier_nodes AS n ON n.node_id = c.descendant_id
WHERE c.ancestor_id = 2
  AND c.depth = 1
ORDER BY n.node_id;
~~~

Counting descendants **excluding the subtree root**:

~~~sql
SELECT COUNT(*) AS descendant_count
FROM hier_closure
WHERE ancestor_id = 2 AND depth > 0;
-- Result: 3.
~~~

### 4.4. Adding a New Node

Suppose we add `Tablet` (ID 7) under `Electronics` (ID 2). When the existing closure is complete, we insert the self-row and all relationships from ancestors of 2 to node 7:

~~~sql
BEGIN;

INSERT INTO hier_nodes (node_id, name, parent_id)
VALUES (7, 'Tablet', 2);

INSERT INTO hier_closure (ancestor_id, descendant_id, depth)
SELECT ancestor_id, 7, depth + 1
FROM hier_closure
WHERE descendant_id = 2

UNION ALL

SELECT 7, 7, 0;

COMMIT;
~~~

Since ancestors of 2 include Products (depth 1) and Electronics itself (depth 0), the new closure gains `(1,7,2)`, `(2,7,1)`, and `(7,7,0)`. The operation requires a transaction, along with synchronization if another transaction is moving branches concurrently.

If adding a new root node, simply insert the node record with `parent_id = NULL` and its depth-0 self-closure pair. If the application has multiple tenants/trees, every insertion and ancestor lookup must be scoped to the exact domain.

### 4.5. Moving a Subtree by Formula

Suppose we move the entire subtree rooted at node **X** to become a child of node **P**. With closure, you cannot update only rows involving X: you must update all relationships **from ancestors outside the branch to every node inside the branch**.

Conceptual algorithm within **one transaction**:

1. Verify X exists, P exists, **P does not lie inside X's subtree**, and the operation is valid within the tenant/tree scope. If P is under X, attaching X to P creates a cycle.
2. Identify **D**, the set of descendants of X **including X**; keep all **internal ancestor–descendant relationships within D** intact.
3. Delete closure rows where **descendant belongs to D** and **ancestor is an old ancestor of X outside D**.
4. For **each ancestor A of P (including P)** and **each D in X's subtree**, insert pair `A → D` with depth: **depth(A, P) + 1 + depth(X, D)**.
5. Update **X's `parent_id` to P**; verify invariants and commit once all changes succeed.

The cost of inserting new pairs is roughly **number of new ancestors × number of nodes in the moved branch**. Concurrent consistency is not guaranteed merely by the order of SQL statements; affected parts must be locked or a sufficiently strong transactional policy applied. Do not mix reading pre-edit and post-edit closure data while another branch move is running concurrently.

**Foreign keys, CHECK constraints, and PRIMARY KEYs do not automatically ensure the closure table contains all ancestor–descendant pairs, has accurate depths, or is cycle-free.** The system needs controlled maintenance mechanisms and periodic reconciliation queries against the `parent_id` source.

### 4.6. Indexes

The primary key **(ancestor_id, descendant_id)** serves subtree queries by `ancestor_id`. To query ancestors of a node, consider an inverted index:

~~~sql
CREATE INDEX idx_hier_closure_by_descendant
ON hier_closure (descendant_id, depth, ancestor_id);

CREATE INDEX idx_hier_closure_by_ancestor_depth
ON hier_closure (ancestor_id, depth, descendant_id);

CREATE INDEX idx_hier_nodes_parent
ON hier_nodes (parent_id);
~~~

The second index speeds up filtering `depth = 1` for direct children, though it also increases write overhead because closure can contain very many rows. Choose indexes using query statistics and `EXPLAIN`, especially on large trees.

**Best suited when:** flexible queries on ancestors, descendants, and distances are needed; maintaining an auxiliary ancestor relation table is acceptable; and structural edits are not overly dense relative to read traffic.

## 5. Comparing Design and Costs

| Criterion | Materialized path | Nested sets | Closure table |
| --- | --- | --- | --- |
| Auxiliary data | One path string per node | Two bounds `lft`/`rgt` per node | One row per ancestor–descendant pair |
| Fetch full subtree | Prefix matching on path | Interval containment check | Filter by `ancestor_id` |
| Fetch ancestors / breadcrumb | Prefix matching or split path | Intervals containing the node | Filter by `descendant_id` |
| Fetch direct children | Use `parent_id`, or split path | Derive from intervals or keep `parent_id` | `depth = 1` |
| Add a leaf | Usually insert 1 row, compute path | May shift many bounds | Insert node + ancestor count + 1 pairs |
| Move a branch | Rewrite paths of the entire subtree | Shift/recompute many intervals, potentially affecting the whole tree | Delete/insert relations between ancestors and subtree |
| Storage growth | Depends on total path lengths | $O(N)$ rows | $O(N \times \text{average depth})$ pairs |
| Consistency enforcement | Path must match parent and IDs | Bounds must not cross-intersect; valid ordering | Closure must be complete, accurate in depth, and acyclic |
| Strengths | Simple, easy to debug, convenient prefixes | Fast static subtree queries and node counts | Flexible upward, downward, and depth queries |
| Weaknesses | Moving large branches updates many rows | Structural edits are complex and heavy | Stores many rows, complex maintenance |

With **N** nodes, path and nested sets models store extra info on about **N node rows**, though path length grows with depth. Closure stores rows equal to the total ancestor count (including self) across all nodes: near $N$ for shallow trees, near $N \log N$ in many balanced trees, and **$N(N+1)/2$** for a long linear chain. Those are **structural size estimates**, not absolute query-time predictions; indexes, data distribution, and the engine determine actual performance.

### Choosing Based on Requirements

- **Heavily read product catalogs with rare reorganizations:** materialized path is an easy-to-implement option; nested sets are also worth considering when range queries and branch counts dominate.
- **Permission/org trees needing ancestors, descendants, and distances:** closure table has clean queries; watch pair volume and move operations.
- **Trees changing constantly with moderate depth:** adjacency list with **WITH RECURSIVE** may be a better first choice before adding derived structures.
- **Very many nodes with large depth:** evaluate path length, closure row counts, bounds updated in nested sets, locks, and concurrent write throughput.

A system can **combine adjacency list with materialized path or closure table**: `parent_id` is the direct-parent source, while the materialized structure serves fast reads. However, every auxiliary structure becomes an **invariant that must be maintained**; controlled data redundancy is the trade-off for read performance.

## 6. Integrity Constraints and Concurrency Handling

### 6.1. Mandatory Invariants

For a valid tree:

1. Each node has a **unique identifier**.
2. A node has at most **one parent**; root nodes have no parent.
3. A node's parent must exist and belong to **the same domain/tenant/tree** if the system partitions by business scope.
4. No **cycles**: following parent edges from a node can never return to that same node.
5. No disconnected subtrees, unless the business permits multiple roots.
6. Every derived structure must stay consistent with the direct parent relationship.

Checking `parent_id <> category_id` only blocks length-1 cycles. Cycles of length 2 or more still require checking ancestors. In materialized path, a buggy prefix update can corrupt all descendant paths; in nested sets, partially overlapping intervals are invalid; in closure tables, missing an `A → D` row makes ancestor queries incomplete.

### 6.2. Checking Before Moving a Branch

Before moving X under P, verify **P is neither X nor a descendant of X**.

- With **materialized path**, check `path(P)` **does not start with** `path(X)`, using boundary-safe segment matching.
- With **nested sets**, check P does not fall inside `[lft(X), rgt(X)]`.
- With **closure table**, check **no pair exists** with `(ancestor_id = X, descendant_id = P)`.

Example with closure table:

~~~sql
-- If any row is returned, node X=2 must not be moved under P=6.
SELECT 1
FROM hier_closure
WHERE ancestor_id = 2
  AND descendant_id = 6;
~~~

The check must happen **within the same synchronized transaction** as the move operation, because two transactions can modify the tree concurrently after each passed its own pre-check. Lock the parent objects, lock by tree/tenant, or use a suitable serialization strategy; isolation levels and conflict recovery must be explicitly decided.

### 6.3. Never Mix Data Across Multiple Trees or Tenants

If a multi-tenant system has multiple classification trees, include **tenant_id** or **tree_id** in identity and relationship rules. For instance, closure data should use composite keys and FKs to forbid an ancestor in tenant A from linking to a descendant in tenant B.

If nested sets reuse `lft`/`rgt` bounds across multiple trees, queries must filter by `tree_id`; a table-wide `UNIQUE(lft)` is incompatible with **per-tree** numbering. For materialized path, path conventions must embed domain identifiers or IDs must be globally unique to prevent identical paths across two different trees.

### 6.4. Deletion, Archiving, and Historical Changes

The choice to **delete an entire subtree**, **promote children to the former grandparent**, or **forbid deleting nodes with children** depends on the business. For categories previously attached to products/orders, physical deletion can break referential integrity or history; an **inactive/archived** status is often worth considering.

If viewing the tree **at a historical point in time** is needed, a current path, current `lft`/`rgt` pair, or current closure is insufficient. You need an effective-dated model, parent-change history, and a way to reconstruct hierarchy state point-in-time. Do not assume adding a `created_at` column alone preserves branch-move history.

## 7. Queries for Verifying Correctness

When maintaining an adjacency list alongside a closure table, several data checks are very useful.

### 7.1. Missing Self-Pairs

~~~sql
SELECT n.node_id
FROM hier_nodes AS n
LEFT JOIN hier_closure AS c
  ON c.ancestor_id = n.node_id
 AND c.descendant_id = n.node_id
 AND c.depth = 0
WHERE c.ancestor_id IS NULL;
~~~

The result must be empty if every node has its self-closure row.

### 7.2. Missing Direct Parent Relationships

~~~sql
SELECT n.node_id, n.parent_id
FROM hier_nodes AS n
WHERE n.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM hier_closure AS c
      WHERE c.ancestor_id = n.parent_id
        AND c.descendant_id = n.node_id
        AND c.depth = 1
  );
~~~

The result must be empty. However, **these two checks do not prove the closure table is complete**: deeper pairs might still be missing or extraneous pairs might exist. To verify completely, rebuild the expected set of pairs from `parent_id` using a recursive CTE on cycle-checked data, then compare symmetrically with **EXCEPT**; any difference indicates the derived structure is inconsistent.

### 7.3. Checking Nested Sets

Under contiguous numbering in **a single tree**:

- Each node satisfies `lft < rgt` and every bound is unique.
- There are **2N boundary values** in total, spanning the exact integer set **1 through 2N**.
- For any two nodes, their intervals must be disjoint or strictly nested; cross-overlapping intersections are forbidden.
- Ancestor pairs must match the `parent_id` relationship, if stored alongside.

Counting `2N` bounds and checking `UNIQUE` is **not enough** to conclude intervals nest properly; containment structure must be checked.

### 7.4. Checking Materialized Paths

For each node:

- Path starts with the root ID and ends with **the node's ID** plus delimiter.
- The parent's path is the **direct prefix** of the child node's path.
- Segment count on the path accurately reflects edge count from the root.
- No two distinct nodes share the same path; no ID repeats along a path if it is a tree.
- Every node within the same tenant/tree scope follows the same encoding and delimiter rules.

Choosing stable numeric IDs as path segments simplifies comparison compared to paths containing category names. If friendly URLs are needed, generate display slugs separately; do not use mutable names as the canonical unique path.

## 8. When Using Document Databases, Graphs, and Analytical Data Warehouses

The nature of ancestor–descendant relationships does not change across technologies, but storage structures are re-selected based on read and write patterns:

| Architecture | Representation | Costs / limits to consider |
| --- | --- | --- |
| **Relational (RDBMS)** | `parent_id`, `path`, nested sets, or closure | PK/FK constraints, CTE queries, indexes, and transactional updates |
| **Document** | Each category document holds `parentId`, `ancestorIds`, or `path`; can embed subtrees | Moving branches may require updating many documents; document size, data sync, and prefix queries |
| **Graph** | `Category` nodes with `PARENT_OF` or `CHILD_OF` edges | Path traversal queries are convenient; multi-parent limits, cycles, and access control must still be enforced |
| **Analytical (warehouse)** | Hierarchy dimension, path/levels, ancestor–descendant bridge table | Correctness when aggregating across levels, slowly changing hierarchies, tree history |

### Document: Storing `ancestorIds` with Discipline

An Android document might contain:

~~~json
{
  "categoryId": 6,
  "name": "Android",
  "parentId": 4,
  "ancestorIds": [1, 2, 4],
  "path": "/1/2/4/6/"
}
~~~

**ancestorIds** helps find nodes in a subtree via array-membership queries; **path** aids display/prefix matching. However, when moving Phones, all descendant documents must still update `ancestorIds`/`path`. If only `parentId` is updated while forgetting the two derived fields, hierarchy queries will return conflicting results depending on which field is queried.

### Graph: When Is a Tree Not Enough?

If a topic belongs to **multiple parent categories** or a resource is classified under multiple taxonomies, it may be a **DAG**. Then:

- Materialized path may require **multiple paths for the same node**.
- Tree-style nested sets **cannot naturally represent** one node having multiple concurrent parents.
- A closure table can store **reachability** for a DAG, but an ancestor–descendant pair can have **multiple paths of different lengths**. A `(ancestor_id, descendant_id)` key with a single `depth` cannot describe all paths unless you specify whether `depth` means **shortest**, **longest**, or another policy.

For a true DAG, consider direct edge representation with graph/recursive queries, or extend closure to store appropriate path semantics. Avoid accidentally collapsing multiple parents into one just because a tree model was picked.

### Analytics: Avoiding Double Counting

A product attached to the `Android` category simultaneously sits under `Phones`, `Electronics`, and `Products`. When joining product revenue with a closure table, **one fact row can appear under multiple ancestors**. That is right when reporting revenue **independently for each level**, yet wrong if summing levels together as if they were disjoint groups.

Clearly define the **grain** of the fact table and aggregation level; if data permits multiple parent categories, also decide whether revenue is allocated, intentionally multi-counted, or filtered by a single canonical taxonomy.

## 9. Choosing a Model Through Real-World Scenarios

### Scenario A: Product Catalog Rarely Reorganized

**Requirements:** Hundreds of thousands of categories, frequent subtree and breadcrumb queries, rare structural edits; read caching available.

**Analysis:** Materialized path is easy to understand and worth trying first. If reading subtrees via range conditions over large record counts is needed, nested sets can be benchmarked. Measure path lengths, bulk update costs, and index plans on representative data.

### Scenario B: Permission Structure Changing Frequently

**Requirements:** Departments shift teams in batches, frequent checks for "is node A an ancestor of B?", organizational permission history required.

**Analysis:** Adjacency list with recursive CTEs may suffice if the tree is not deep. If heavy ancestor lookups are needed, consider a closure table while factoring in pair-rebuilding costs on branch moves. Historical permissions also require effective-dating models and dedicated permission policies; a current-state closure table cannot replace history.

### Scenario C: Folder Tree with Millions of Nodes and Frequent Moves

**Requirements:** Very large tree, users continuously move folders and change parents.

**Analysis:** Dense-numbered nested sets typically cause heavy writes on tree edits. Materialized path forces rewriting paths of many descendants. Closure table also needs rewriting many relations. Measure load capacity and consider using adjacency list as the source of truth, optimizing queries as needed; paths can be cached or read structures updated asynchronously if the business tolerates sync lag and provides staleness awareness.

### Scenario D: Products Can Sit in Multiple Taxonomy Branches

**Requirements:** A subcategory has multiple valid parents and multiple paths to the root.

**Analysis:** This is no longer a standard tree. Model parent–child edges as many-to-many or a DAG with cycle prevention. Do not directly apply a single path or a single `lft`/`rgt` pair; if using closure, clearly define reachability and depth semantics.

## 10. Decision and Testing Workflow

When designing a new hierarchy, proceed sequentially:

1. **Identify relationship nature:** tree, forest, DAG, or multi-dimensional hierarchy?
2. **Identify identity:** are node IDs stable across renames, reparenting, or tenant moves?
3. **List primary queries:** subtrees, path to root, direct children, depth, ancestor checks, revenue rollup by category.
4. **Measure data traits:** node count, average/maximum depth, small/large branch ratios, moves per day.
5. **Choose the source of truth:** `parent_id`/direct edges; decide which read benefit justifies adding path, intervals, or closure.
6. **Design constraints:** PK/FK, single parent, acyclicity, root representation, tree/tenant scoping, consistent derived data.
7. **Design structural operations:** adding leaves, changing parents, moving branches, deleting or archiving; transactions and locks to prevent invalid concurrent updates.
8. **Create query-driven indexes:** test `EXPLAIN` on representative data; avoid duplicate or excessive indexes slowing down writes.
9. **Establish verification:** reconcile path/closure/intervals against direct edges; monitor errors and ability to rebuild derived data.
10. **Test boundary cases:** single-node tree, deep linear chain, very wide tree, multiple roots, moving a node into its descendant, two concurrent branch moves.

### Self-Check Exercises with Hints

**Question 1.** The path of Phones is **/1/2/4/**; Android's path is **/1/2/4/6/**. Moving Phones under Fashion (path **/1/3/**), how do the two nodes' paths change?

**Hint:** Phones becomes **/1/3/4/**; Android becomes **/1/3/4/6/**. The child node retains Phones as its direct parent while replacing the entire old ancestor prefix.

**Question 2.** In nested sets, Electronics has interval `[2,9]`. How many nodes are in its subtree? Is Android `[4,5]` inside this subtree?

**Hint:** **(9 − 2 + 1)/2 = 4** nodes; `[4,5]` lies completely inside `[2,9]`, so Android is a descendant of Electronics.

**Question 3.** Closure has `(2,6,2)` and `(4,6,1)`. What do those two rows tell us? To fetch **direct children** of 2, what condition do you filter by?

**Hint:** Android (6) is two edges below Electronics (2) and one edge below Phones (4); filter by **ancestor_id = 2 AND depth = 1** to get direct children.

**Question 4.** A closure table has all self-pairs and direct-parent pairs. Is that sufficient to conclude the entire closure is correct?

**Hint:** **Not yet.** Distant ancestor pairs could still be missing, extraneous pairs could exist, or depths could be wrong. You must reconcile the entire reachability set against the source tree and check for cycles.

**Question 5.** A `Category` can belong to two parent `Categories`. Should tree-style nested sets be applied directly?

**Hint:** No. The rule "each node has at most one parent" has changed. Identify it as a DAG, represent many-to-many edges, and check acyclicity; ancestor-storage methods must be redesigned for multiple paths.

## 11. Key Takeaways

**Materialized path** stores the path and suits prefix matching; **nested sets** store containment intervals and suit relatively static trees; **closure table** stores ancestor–descendant pairs with depth and suits flexible hierarchical queries. Every model incurs costs on structural changes and requires consistency protection. Choose based on whether **the business model is truly a tree or a graph**, read/write frequency, depth, tenant scoping, and data verifiability—not simply because one sample query looks shorter.
