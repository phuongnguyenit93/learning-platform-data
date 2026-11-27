# Comparing Costs of Reading Ancestors, Reading Subtrees, Moving, and Updating Nodes

A hierarchical tree can be represented in multiple physical data structures. The exact same requirements—"display all subordinate departments", "find the path from a product category up to the root", or "move team A under team B"—can produce dramatically different read volume, write volume, and lock contention.

In the **DATABASE_DATA_MODELING** module, the goal of cost comparison is to select a schema suited to business rules, query patterns, and update frequency, while preserving invariants: the parent exists, ownership scope is respected, each node has at most one parent, and no cycles occur. This lesson focuses on the **Inheritance and Hierarchies** chapter, specifically parent–child trees between records; this is a distinct problem from entity-type inheritance (*supertype/subtype*).

We will compare four common relational models: **adjacency list**, **materialized path**, **closure table**, and **nested sets**. We then broaden the view to document, graph, and historical analysis. SQL examples use PostgreSQL 15+; complexity figures are estimation models for decision-making, not runtime guarantees across every DBMS.

## 1. Start from Real Tasks, Not from Table Structures

Consider an enterprise's category tree:

```text
All (1)
├── Electronics (2)
│   ├── Phones (3)
│   │   └── Android (7)
│   └── Laptops (4)
└── Fashion (5)
    └── Shoes (6)
```

Four operations to examine:

1. **Read ancestors of "Android"**: returns "Phones → Electronics → All", typically to build a breadcrumb or check inherited permissions.
2. **Read subtree of "Electronics"**: returns 2, 3, 4, and 7; typically to filter all products belonging to a branch.
3. **Move branch "Electronics" under "Shoes"**: change the position of 2 and all descendants 3, 4, 7 without creating cycles.
4. **Update node "Phones"**: change display name, status, or business attributes; distinguish this operation from changing parent–child relationships.

Both reading ancestors and reading subtrees can return many rows. Differences between models usually lie in **how those rows are located**, the number of query steps, and how many rows/indexes must be modified when the tree structure changes.

### Notation Used for Comparison

| Symbol | Meaning |
|---|---|
| \(N\) | Total number of nodes in a tree or tenant scope under consideration |
| \(h\) | Depth of the node from the root; roughly equal to its ancestor count |
| \(s\) | Number of nodes in the affected subtree, **including the subtree root** |
| \(a_o\) | Number of ancestors outside the subtree at the moved node's old position |
| \(a_n\) | Number of ancestors at the new position, including the new parent |
| \(b\) | Average branching factor of a node in a balanced tree, when approximable |
| \(R\) / \(W\) | Number of read / write operations within the same measurement window |

For instance, the "Electronics" branch has \(s=4\). Node "Android" has \(h=3\) if the root is at depth 0. A linear-chain tree can have \(h \approx N-1\); a balanced tree with branching factor \(b>1\) typically has depth around \(\log_b N\).

In cost tables, **\(O(\cdot)\)** describes the scaling trend of operations or records processed under an algorithmic model. Actual cost also includes I/O, row size, buffers, indexes, execution plans, WAL writes, lock contention, and concurrency. Algorithms cannot read fewer rows than the answer requires outputting: returning \(s\) nodes always incurs a baseline cost proportional to \(s\) results.

## 2. Four Ways to Represent the Same Tree

### 2.1. Adjacency List

Each node stores the key of its **direct parent**:

| `node_id` | `parent_id` | `name` |
|---:|---:|---|
| 1 | `NULL` | All |
| 2 | 1 | Electronics |
| 3 | 2 | Phones |
| 4 | 2 | Laptops |
| 5 | 1 | Fashion |
| 6 | 5 | Shoes |
| 7 | 3 | Android |

The advantage is needing only one row to represent a node and one `parent_id` field to locate it. Querying the direct parent is a single lookup; traversing multiple levels requires a **recursive CTE** or application-side recursion. Moving a branch only updates `parent_id` of the branch root **in terms of representation**, though cycle checks are still required.

### 2.2. Materialized Path

Each node stores the path from the root to itself. To avoid impact from renames, paths should be built from **stable IDs** with clear delimiters:

| `node_id` | `path` |
|---:|---|
| 1 | `/1/` |
| 2 | `/1/2/` |
| 3 | `/1/2/3/` |
| 4 | `/1/2/4/` |
| 5 | `/1/5/` |
| 6 | `/1/5/6/` |
| 7 | `/1/2/3/7/` |

A descendant of 2 has a path starting with `/1/2/`. Branches can be found via prefix matching when supported by indexes and data types. Conversely, moving 2 under 6 forces updating paths of **all four nodes** 2, 3, 4, and 7.

Path segment encoding must be standardized: use delimiters so `/1/2/` does not prefix-match `/1/20/`; use escapable or canonically encoded IDs; validate length limits; and never accept arbitrary user-supplied `path` writes. PostgreSQL can use `ltree` when appropriate, though it is an extension with its own semantics and indexes, not equivalent to `TEXT` by default.

### 2.3. Closure Table

Alongside the node table, store an extra row for **each ancestor–descendant pair**, usually including the self-pair at `depth = 0`:

| `ancestor_id` | `descendant_id` | `depth` |
|---:|---:|---:|
| 1 | 1 | 0 |
| 1 | 2 | 1 |
| 1 | 3 | 2 |
| 1 | 7 | 3 |
| 2 | 2 | 0 |
| 2 | 3 | 1 |
| 2 | 4 | 1 |
| 2 | 7 | 2 |
| 3 | 3 | 0 |
| 3 | 7 | 1 |
| 7 | 7 | 0 |

The table above is only an **illustrative subset**; the complete table must include corresponding pairs for every node, including 4, 5, and 6. With indexes on `ancestor_id` and `descendant_id`, finding ancestors or descendants requires no read-time recursion over direct parent links. The trade-off is many extra rows and more complex updates when moving branches.

### 2.4. Nested Sets

Each node receives a `lft`, `rgt` pair from an in-order/depth-first tree traversal such that a parent's interval **encloses** all intervals of its children:

| `node_id` | `lft` | `rgt` |
|---:|---:|---:|
| 1 | 1 | 14 |
| 2 | 2 | 9 |
| 3 | 3 | 6 |
| 7 | 4 | 5 |
| 4 | 7 | 8 |
| 5 | 10 | 13 |
| 6 | 11 | 12 |

In standard contiguous numbering, leaf nodes satisfy `rgt = lft + 1`. All descendants of node 2 lie within `(2, 9)`. Range queries are convenient for **reading an entire branch**, but inserting or moving a branch may require renumbering many nodes outside that branch. If gaps are left in values, update behavior differs; the cost table here assumes **classic nested sets with contiguous ordering**.

Nested sets often retain `parent_id` or an auxiliary link structure if direct-parent lookups are frequent. When maintaining two representations in parallel, both must be updated consistently within the same transaction.

## 3. Cost Comparison Table by Operation

Assuming appropriate keys and indexes exist and data is uncorrupted; result-retrieval and index-update costs are noted below.

| Model | Read ancestors | Read subtree | Move branch | Rename / normal attribute update |
|---|---|---|---|---|
| **Adjacency list** | Follow \(h\) parents; roughly \(h\) key lookups | Traverse \(s\) nodes via `parent_id` index | **1 structural row** + cycle traversal/check, potentially \(O(s)\) | **1 row** |
| **Materialized path** | Split roughly \(h\) path segments, then look up node names if needed | Prefix scan; near \(O(\log N+s)\) when index applies | Rewrite `path` for **\(s\) rows** and related indexes | **1 row** if path uses stable IDs |
| **Closure table** | Read roughly \(h\) closure rows via index | Read roughly \(s\) closure rows via index | Delete/insert external ancestor relations, roughly \(O((a_o+a_n)s)\) auxiliary rows | **1 node row**, no closure edits |
| **Nested sets** | Filter enclosing intervals; typically hard to guarantee \(O(h)\) cost | Scan one interval range, near \(O(\log N+s)\) with suitable index and plan | May renumber \(O(N)\) nodes/intervals | **1 row** |

This is a **row and processing-step cost** model, not measured wall-clock runtime. For example, an adjacency list "follow \(h\) parents" operation may perform roughly \(h\) B-tree lookups, with theoretical cost around \(O(h\log N)\). A closure table can read \(h\) rows across an index range, plus initial lookup and output cost. Nested sets use a two-sided condition `lft < x AND rgt > y`; a single B-tree may still inspect many more rows than \(h\) before filtering down to the \(h\) ancestors, so \(O(h)\) cannot be promised solely from result row count.

### 3.1. Storage Footprint Comparison

| Model | Auxiliary structural data | Things to remember |
|---|---|---|
| Adjacency list | One `parent_id`/node, total \(O(N)\) | Lightweight, few specialized indexes |
| Materialized path | Path per node, total length grows with \(\sum \text{depth}(node)\) | Deep trees yield long paths; branch moves cause multi-row writes |
| Closure table | Roughly \(N+\sum \text{depth}(node)\) rows if including self-references | Linear chain trees can reach \(O(N^2)\) closure rows |
| Nested sets | Two `lft`/`rgt` numbers per node, \(O(N)\) | Writes few columns, yet structural edits may trigger bulk updates |

If \(N=100{,}000\) and average depth is about 6, a closure table may hold roughly \(100{,}000\times(6+1)=700{,}000\) rows—**an estimate under that assumption only**; actual size depends on depth distribution, column types, and indexes. A linear chain with the same \(N\) will cost vastly more.

## 4. Building a Verifiable Source Schema

Regardless of structure chosen, the relational model must establish **node identity, tenant scope, parent relationship, and the acyclicity invariant**. With adjacency list as the source of truth, PostgreSQL can use:

```sql
CREATE TABLE category_nodes (
    tenant_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    parent_id BIGINT,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT pk_category_nodes
        PRIMARY KEY (tenant_id, node_id),

    CONSTRAINT fk_category_nodes_parent
        FOREIGN KEY (tenant_id, parent_id)
        REFERENCES category_nodes (tenant_id, node_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_node_not_own_parent
        CHECK (parent_id IS NULL OR parent_id <> node_id),

    CONSTRAINT ck_node_slug
        CHECK (btrim(slug) <> ''),

    CONSTRAINT ck_node_display_name
        CHECK (btrim(display_name) <> ''),

    CONSTRAINT uq_sibling_slug
        UNIQUE NULLS NOT DISTINCT (tenant_id, parent_id, slug)
);
```

This table permits multiple roots with distinct `slug`s within the same tenant. If the business requires **at most one root/tenant**, add a partial unique index on `tenant_id WHERE parent_id IS NULL`. To guarantee **every tenant has at least one root**, appropriate creation/deletion workflows are also needed; unique constraints do not enforce existence.

PostgreSQL 15+'s `UNIQUE (tenant_id, parent_id, slug) NULLS NOT DISTINCT` already creates an index with prefix `(tenant_id, parent_id)`, which can serve direct-child reads. Adding another index with a duplicate prefix is not strictly necessary. In other DBMSs, `NULL` handling and unique syntax may differ.

The composite foreign key prevents a node in tenant 42 from taking a parent in tenant 43. `CHECK` prevents a node from being its own direct parent. **None of these constraints automatically prevent multi-node cycles**, such as `A → B → C → A`; an additional mechanism is needed on the tree-update path.

### Sample Data

```sql
INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES (42, 1, NULL, 'all', 'All');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES
    (42, 2, 1, 'electronics', 'Electronics'),
    (42, 5, 1, 'fashion', 'Fashion');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES
    (42, 3, 2, 'phones', 'Phones'),
    (42, 4, 2, 'laptops', 'Laptops'),
    (42, 6, 5, 'shoes', 'Shoes');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES (42, 7, 3, 'android', 'Android');
```

Subsequent queries read this sample data in its **pre-move** state.

## 5. Cost of Reading Ancestors

Reading ancestors typically serves breadcrumbs, inherited permissions, or locating a node's position in the tree.

### 5.1. Adjacency List: Walking Edge by Edge to the Root

```sql
WITH RECURSIVE ancestors AS (
    SELECT n.tenant_id, n.node_id, n.parent_id,
           n.display_name, 0 AS distance_to_target,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 7

    UNION ALL

    SELECT p.tenant_id, p.node_id, p.parent_id,
           p.display_name, a.distance_to_target + 1,
           a.visited || p.node_id
    FROM ancestors AS a
    JOIN category_nodes AS p
      ON p.tenant_id = a.tenant_id
     AND p.node_id = a.parent_id
    WHERE NOT (p.node_id = ANY(a.visited))
)
SELECT node_id, display_name, distance_to_target
FROM ancestors
ORDER BY distance_to_target DESC;
```

The result includes nodes 1, 2, 3, 7 ordered from root to target node. The `visited` column guards against infinite loops when data is already corrupted; it does not prove the system prevented all cycles at write time.

In a tree of depth \(h\), you must sequentially discover each parent's parent, creating \(h\) dependent steps. The primary-key index speeds up each parent lookup, yet cannot fully parallelize steps whose next ID is not yet known. For breadcrumbs of depth 3–6, this cost is usually small; for hierarchies thousands of levels deep with heavy read volume, benchmark with real data.

### 5.2. Materialized Path: Path Already Contains Ancestor Identities

With `path = '/1/2/3/7/'`, the string already holds the IDs needed to build ancestor order. If the UI only needs the ID path, the application can split the path without a recursive CTE.

If the UI needs **current names**, you still must fetch data for nodes 1, 2, 3, 7, for example via an ID-set query and sorting according to path order. Do not store category names inside the identifying path: storing `/All/Electronics/...` forces rewriting paths of all descendants whenever "Electronics" is renamed.

The cost of obtaining the path is one node-row read plus string processing proportional to \(h\); reading ancestor attributes scales with the number of nodes to display.

### 5.3. Closure Table: Ancestors Are Materialized Rows

An auxiliary schema can use:

```sql
CREATE TABLE category_closure (
    tenant_id BIGINT NOT NULL,
    ancestor_id BIGINT NOT NULL,
    descendant_id BIGINT NOT NULL,
    depth INTEGER NOT NULL,

    CONSTRAINT pk_category_closure
        PRIMARY KEY (tenant_id, ancestor_id, descendant_id),

    CONSTRAINT fk_closure_ancestor
        FOREIGN KEY (tenant_id, ancestor_id)
        REFERENCES category_nodes (tenant_id, node_id),

    CONSTRAINT fk_closure_descendant
        FOREIGN KEY (tenant_id, descendant_id)
        REFERENCES category_nodes (tenant_id, node_id),

    CONSTRAINT ck_closure_depth CHECK (depth >= 0),
    CONSTRAINT ck_closure_self_depth
        CHECK (
          (ancestor_id = descendant_id AND depth = 0)
          OR (ancestor_id <> descendant_id AND depth > 0)
        )
);

CREATE INDEX ix_closure_descendant
    ON category_closure (tenant_id, descendant_id, depth);
```

The closure table must be **initialized** from the source tree and **maintained within the same transaction** as parent–child changes. The two foreign keys only ensure both endpoints of an edge exist; they do not prove the closure table contains **all paths completely and accurately**.

Querying ancestors of node 7:

```sql
SELECT c.ancestor_id, n.display_name, c.depth
FROM category_closure AS c
JOIN category_nodes AS n
  ON n.tenant_id = c.tenant_id
 AND n.node_id = c.ancestor_id
WHERE c.tenant_id = 42
  AND c.descendant_id = 7
ORDER BY c.depth DESC;
```

With the `(tenant_id, descendant_id, depth)` index, rows related to a descendant can be retrieved contiguously. To display names, a join to the node table is still needed. The major advantage is avoiding chasing parent-of-parent at every level.

### 5.4. Nested Sets: Filtering Enclosing Intervals

Assuming the node table also has consistently maintained `lft` and `rgt`, querying ancestors relies on:

```sql
SELECT ancestor.node_id, ancestor.display_name
FROM category_nodes AS target
JOIN category_nodes AS ancestor
  ON ancestor.tenant_id = target.tenant_id
 AND ancestor.lft < target.lft
 AND ancestor.rgt > target.rgt
WHERE target.tenant_id = 42
  AND target.node_id = 7
ORDER BY ancestor.lft;
```

The SQL snippet is a **query template for the nested sets variant**; the `category_nodes` table in section 4 does not declare `lft`/`rgt`, so those two columns and an interval-assignment mechanism must be added before running it.

The two-sided inequality can be hard for a standard B-tree to exploit fully. Only \(h\) ancestors are returned, yet the engine may scan many more than \(h\) rows. Therefore, nested sets are especially attractive when **reading descendants by range**, whereas ancestor-read cost should be evaluated using `EXPLAIN` and real data distribution.

## 6. Cost of Reading an Entire Subtree

Suppose we need to view all subcategories under "Electronics" on an admin page and count products per category.

### 6.1. Adjacency List: Traversing via `parent_id`

```sql
WITH RECURSIVE subtree AS (
    SELECT n.tenant_id, n.node_id, n.parent_id,
           n.display_name, 0 AS relative_depth,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 2

    UNION ALL

    SELECT child.tenant_id, child.node_id, child.parent_id,
           child.display_name, t.relative_depth + 1,
           t.visited || child.node_id
    FROM subtree AS t
    JOIN category_nodes AS child
      ON child.tenant_id = t.tenant_id
     AND child.parent_id = t.node_id
    WHERE NOT (child.node_id = ANY(t.visited))
)
SELECT node_id, display_name, relative_depth
FROM subtree
ORDER BY relative_depth, node_id;
```

The query returns 2, 3, 4, 7. If the application wants only **strict descendants** without the starting node, add `relative_depth > 0` in the final output.

Each visited node must look up its children by `parent_id`. An index with prefix `(tenant_id, parent_id)` reduces irrelevant rows inspected. Counting by discovered nodes, that is roughly \(s\) expansions, though the query also incurs index lookups, cycle-guard array handling, sorting, and actual row reads.

### 6.2. Materialized Path: Reading by Prefix

With node 2's path being `/1/2/`, we fetch rows whose path starts with that exact string.

```sql
-- Illustrating the category_paths(tenant_id, node_id, path) table variant.
SELECT node_id, path
FROM category_paths
WHERE tenant_id = 42
  AND path LIKE '/1/2/%'
ORDER BY path;
```

This is an **illustrative** query; the `category_paths` table/column and appropriate index must be created before running it. In PostgreSQL, a B-tree index for `LIKE 'prefix%'` may need `text_pattern_ops` when the collation disallows default prefix optimization; with bind parameters, the plan also depends on whether the planner knows the prefix at plan time. Using `ltree` with GiST/GIN is another option. Do not assume every `LIKE path_of_parent || '%'` expression optimizes into a range scan.

Main advantage: descendants reside in a prefix-accessible region; afterward, the query still reads \(s\) nodes. For very large branches, pagination and limiting data sent to the UI remain necessary.

### 6.3. Closure Table: Reading by `ancestor_id`

```sql
SELECT n.node_id, n.display_name, c.depth
FROM category_closure AS c
JOIN category_nodes AS n
  ON n.tenant_id = c.tenant_id
 AND n.node_id = c.descendant_id
WHERE c.tenant_id = 42
  AND c.ancestor_id = 2
ORDER BY c.depth, n.node_id;
```

The primary key `(tenant_id, ancestor_id, descendant_id)` supports finding pairs sharing the same ancestor. The query reads roughly \(s\) relevant closure rows; when names are needed, it joins roughly \(s\) node rows. Sorting cost may apply if the index order does not match `ORDER BY`.

Closure tables are particularly useful when the same app frequently asks for "all descendants", "all ancestors", "hierarchy distance", or checks "is A an ancestor of B?" via a single key-pair lookup.

### 6.4. Nested Sets: Scanning a Position Range

If node 2 has `lft = 2` and `rgt = 9`:

```sql
SELECT child.node_id, child.display_name, child.lft, child.rgt
FROM category_nodes AS child
WHERE child.tenant_id = 42
  AND child.lft BETWEEN 2 AND 9
ORDER BY child.lft;
```

With valid nested sets intervals, this scan returns the entire subtree including node 2. An index on `(tenant_id, lft)` makes scanning contiguous ranges efficient. This is the classic strength of nested sets for **branch-read-heavy, tree-edit-rare** workloads.

However, if you need nodes at **exactly one level**, or the immediate parent of each row, nested sets may need extra queries or separately stored `parent_id`. Never evaluate a model on just one query type.

## 7. Moving a Branch: Where Do Write Costs Diverge?

Suppose we move node 2 "Electronics" to become a child of node 6 "Shoes":

```text
Before: All → Electronics → (Phones → Android, Laptops)
        All → Fashion → Shoes

After:  All → Fashion → Shoes → Electronics
                                    ├── Phones → Android
                                    └── Laptops
```

The moved branch has \(s=4\). Mandatory invariant: **the new parent must not be the moved node itself or one of its descendants**; the new parent must exist and belong to the same tenant. If names/identifiers are unique per parent, also check name/`slug` collisions after moving.

### 7.1. Adjacency List: One Structural Update, Plus Validation

Representationally, after validity checks:

```sql
UPDATE category_nodes
SET parent_id = 6
WHERE tenant_id = 42 AND node_id = 2;
```

Only one row changes `parent_id`; rows 3, 4, 7 still point to their old direct parents and naturally follow the branch to its new location. However, **never** treat that statement as a safe branch-move API without cycle checks and concurrency synchronization.

A centralized transactional pattern under `READ COMMITTED` isolation, assuming **every operation modifying parent–child relations in this tenant acquires the same advisory lock**:

```sql
BEGIN;

-- Illustrative lock dedicated to tenant 42's tree.
-- Every code path modifying this tree structure must follow the exact same locking convention.
SELECT pg_advisory_xact_lock(9007, 42);

WITH RECURSIVE subtree AS (
    SELECT n.node_id, n.parent_id,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 2

    UNION ALL

    SELECT c.node_id, c.parent_id, t.visited || c.node_id
    FROM subtree AS t
    JOIN category_nodes AS c
      ON c.tenant_id = 42 AND c.parent_id = t.node_id
    WHERE NOT (c.node_id = ANY(t.visited))
)
UPDATE category_nodes AS moved
SET parent_id = 6
WHERE moved.tenant_id = 42
  AND moved.node_id = 2
  AND EXISTS (
      SELECT 1 FROM category_nodes AS new_parent
      WHERE new_parent.tenant_id = 42 AND new_parent.node_id = 6
  )
  AND NOT EXISTS (
      SELECT 1 FROM subtree WHERE node_id = 6
  )
RETURNING moved.node_id, moved.parent_id;

COMMIT;
```

The application must verify `UPDATE` returns **exactly one row** and diagnose when it returns 0 rows (missing node, missing parent, or cycle risk). If a unique/FK error occurs, roll back the transaction. Tenant-level advisory locks are safe only across flows adhering to the convention; centralize structural modifications in one service/stored procedure and restrict direct write privileges. For tenant IDs exceeding the 32-bit integer range of the two-argument lock signature, design an appropriate lock key to avoid collisions.

The cost consists of two very different parts:

- **Structural write:** one `parent_id` row, plus associated index updates.
- **Move validation:** potentially traversing \(s\) nodes if scanning the full subtree, or \(h\) parents if walking the new parent's ancestor path, plus locking and concurrency synchronization.

Thus, the claim "adjacency list move is \(O(1)\)" applies only to the **number of rows structurally modified**, not to the entire safe operation in a multi-transaction system.

### 7.2. Materialized Path: Rewriting Every Path in the Subtree

Old path of 2: `/1/2/`; new path: `/1/5/6/2/`. Rows matching the old prefix have their prefix replaced:

```text
/1/2/       → /1/5/6/2/
/1/2/3/     → /1/5/6/2/3/
/1/2/4/     → /1/5/6/2/4/
/1/2/3/7/   → /1/5/6/2/3/7/
```

With \(s\) nodes in the subtree, roughly \(s\) paths and corresponding index entries must be updated. Verify the new parent's path is not inside the moved subtree, preserve tenant boundaries, and execute updates consistently inside a transaction. Changing only node 2's `path` leaves descendants with stale paths and produces a contradictory structure.

When multiple transactions concurrently reparent or insert nodes under a moving branch, those operations must be synchronized. Building a path by reading the parent and writing the child outside a transaction can produce corrupted paths.

### 7.3. Closure Table: Deleting Old Ancestor Pairs and Inserting New Ones

When moving subtree \(S\) of node 2, **internal** relationships within \(S\) do not change: 2 remains an ancestor of 3, 4, 7, and 3 remains an ancestor of 7.

The relationships needing updates are pairs linking **external ancestors** to every node in \(S\):

1. Delete pairs between old ancestors outside \(S\) and each descendant of 2.
2. Insert pairs between the new parent plus all its ancestors and each descendant of 2.
3. Recompute `depth` of each new pair as distance to new parent + 1 + distance from branch root to descendant.

When the old external ancestor count is \(a_o\) and the new ancestor count including the new parent is \(a_n\), the number of closure rows deleted/inserted is roughly:

\[
a_o s + a_n s = (a_o+a_n)s.
\]

That is the cost of **writing relationship rows**, excluding traversal to gather sets, cycle checks, index maintenance, WAL, and locks. If old and new paths share ancestors, implementations can optimize away unchanged portions; the expression above is an intuitive estimate when removing and rebuilding all external relationships.

A branch move on a deep tree with large \(s\) can update far more auxiliary rows than \(s\). In return, subsequent ancestor/descendant queries read quickly without rebuilding relationships from parents.

### 7.4. Nested Sets: Shifting Numbered Intervals

Under contiguous numbering, moving a tree segment to another position alters both the subtree's intervals and the positions of many nodes lying between the old and new locations. Affected rows can approach \(N\) in the worst case; some algorithms even run multi-phase index shifts and require careful locking/transactions to avoid transient unique collisions.

For small trees, that cost may be acceptable. For large \(N\), mass updates to `lft` and `rgt` can generate heavy WAL volume, long-held locks, contention, and index maintenance pressure. If the workload frequently moves branches, classic nested sets are usually unfavorable.

## 8. Updating Nodes: Separate Attributes from Position

A backlog item saying "update node" can refer to several operations with completely different costs.

| Operation | Adjacency list | Materialized path | Closure table | Nested sets |
|---|---|---|---|---|
| Change `display_name` when path uses IDs | Update 1 row | Update 1 row | Update 1 node row | Update 1 row |
| Change `slug` when `slug` is not in path | Update 1 row + unique check | Update 1 row + unique check | Update 1 row + unique check | Update 1 row + unique check |
| Rename when path contains **names** | Update 1 row | May require updating paths of \(s\) nodes | Update 1 row | Update 1 row |
| Change `parent_id` / move branch | Validate + update parent of 1 node | Validate + update paths of \(s\) nodes | Validate + update roughly \((a_o+a_n)s\) relations | Validate + potentially renumber \(O(N)\) nodes |
| Add a leaf node | 1 row + FK check | 1 row, path derived from parent | 1 node row + roughly \(h+1\) closure rows | Usually shifts many intervals, potentially \(O(N)\) |
| Delete a leaf node | 1 row if unblocked by other FKs | 1 row after handling dependencies | 1 node row + delete roughly \(h+1\) closure rows | Usually shifts intervals, potentially \(O(N)\) |

In the table above, "1 row" refers only to **structural write volume**; operations also involve permission checks, FKs, unique constraints, indexes, and triggers. If the tree is used for permission inheritance, changing `is_active` or permissions on a parent **can alter the effective semantics of the entire branch**, even though physically only one row changes. Permission/breadcrumb/count caches must be refreshed according to consistency contracts.

**Design rule:** do not lump "rename", "status change", and "reparent" into one `update_node_cost` metric. Measure them separately, because their frequencies and risks are completely different.

## 9. Choosing by Tree Shape and Read/Write Ratio

Cost depends on tree shape and where **hotspots** sit.

### Case A: Deep Tree, Few Children

For example, chained approval levels forming an 800-node sequence. Reading ancestors of the last node must return up to 799 rows; the result itself is already large. Adjacency list must walk many sequential steps. Closure table can query ancestors via an index range, yet stores huge ancestor–descendant pair counts (for an \(N\)-node chain, \(N(N+1)/2\) pairs including self-references). Nested sets avoid large extra row storage, though inserts/moves can be very expensive.

For this tree shape, ask why depth is so high and whether all ancestors truly need to be returned every time; caching or display-depth limits may help, provided a cache invalidation strategy exists on tree changes.

### Case B: Wide, Shallow Tree

For example, one root with tens of thousands of direct child categories. Reading ancestors of any leaf is very cheap in adjacency list because it is one step to the root. Reading the **entire** tree still returns huge row counts, even with closure or nested sets. The main issue may be pagination, filtering, and network payload volume rather than needing a new tree structure.

### Case C: Frequent Large Branch Moves

For example, an operations team continuously reorganizes catalogs: moving hundreds of branches daily, each with thousands of nodes. Adjacency list has the advantage of changing only one parent link (after cycle prevention); materialized path must update \(s\) paths; closure table must maintain many pairs; nested sets may renumber across large regions. For this workload, prioritize write-path design and concurrency safety.

### Case D: Heavy Ancestor/Subtree Queries, Rare Tree Edits

For example, a canonical taxonomy edited quarterly yet used continuously to filter reports. Closure table or materialized path can eliminate read-time recursion. Nested sets can also excel if most reads fetch subtrees by interval. Still, account for extra storage, rebuild cost on updates, and historical version reporting requirements.

## 10. Estimating Impact from a Concrete Workload

Suppose a tenant has:

- \(N=100{,}000\) nodes;
- average depth around 6;
- daily: 50,000 ancestor queries, 20,000 subtree queries;
- 100 branch moves, each moved branch having \(s=1{,}500\) nodes;
- roughly \(a_o=5\) old ancestors and \(a_n=7\) ancestors at the new position.

Measured by **structural rows modified** per branch move, an illustrative estimate is:

| Model | Structural rows written per move |
|---|---:|
| Adjacency list | 1 `parent_id` row, plus validation cost |
| Materialized path | ~1,500 `path` rows |
| Closure table | ~ \((5+7)\times1{,}500 = 18{,}000\) relationship rows deleted/inserted |
| Classic nested sets | Depends on move positions; worst case near 100,000 nodes adjusted |

This is **not a latency benchmark**. A single batched write of 18,000 narrow rows may be faster or slower than a recursive query over 1,500 nodes depending on the system. If most descendant queries return two nodes instead of 1,500, the optimization payoff also shifts.

To decide, estimate **total periodic cost**:

\[
C_{\text{workload}}
\approx R_a C_a + R_s C_s + W_m C_m + W_u C_u
+ C_{\text{storage}} + C_{\text{operations}}
\]

Here \(R_a\), \(R_s\) are counts of ancestor/subtree reads; \(W_m\), \(W_u\) are counts of branch moves/node updates; \(C\) represents measured or estimated per-operation costs. The equation is a **comparison framework**—you cannot directly add milliseconds, storage bytes, and operational risk without normalized weights or evaluation criteria. Set separate budgets for read p95, lock duration during moves, storage footprint, and operational complexity rather than forcing everything into a single score.

## 11. Designing Benchmarks to Validate Choices

A useful benchmark must use the **same logical data** and same business questions across every model.

### 11.1. Preparing Data

Generate at least three tree shapes:

1. **Balanced:** multiple levels with moderate branching factor; node count representative of production.
2. **Deep:** each node usually has one child; tests recursive CTE limits, long paths, closure row counts.
3. **Wide:** root has very many children; tests index selectivity, pagination, and actual returned rows.

Data must separate tenants and branch sizes; measure 1-node, 100-node, 1,000-node subtrees, and large branches matching product scale.

### 11.2. Separating Read Suites and Write Suites

| Suite | Cases to run |
|---|---|
| Read ancestors | Node near root, deep leaf node, hot frequently accessed node |
| Read subtree | Leaf node, medium branch, large branch, root |
| Move | Move leaf; medium branch; large branch; move within same tree; move rejected due to cycle |
| Update attributes | Rename, status change, attribute update not altering position |
| Concurrency | Multiple users moving intersecting branches concurrently; updating child while parent moves |
| History | Querying current tree vs. tree at historical transaction time, if required by business |

In PostgreSQL, inspect execution plans with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.node_id
FROM category_nodes AS c
WHERE c.tenant_id = 42
  AND c.parent_id = 2;
```

The command above only measures **direct children**, not a full subtree. To measure multi-level ancestor/subtree queries, place the actual `WITH RECURSIVE` query after `EXPLAIN (ANALYZE, BUFFERS)`. For writes, use test transactions with rollback and inspect impacts on triggers, indexes, WAL, or appropriate profiling tools.

Record: p50/p95/p99 latency, actual rows read, buffer hits/reads, rows and bytes updated, WAL volume, lock hold time, lock waits/deadlocks, CPU, index size, and error-recovery cost. Cache warming and run order can skew results; run enough iterations and rotate execution order when comparing alternatives.

### 11.3. Evaluating Query Plans

Having an index created does not mean the planner will use it. For example:

- `LIKE` on paths depends on data type, collation, operator class, and whether the prefix is known.
- Closure tables have two primary lookup directions: `ancestor_id` and `descendant_id`; an index with an unsuitable column order can make one direction expensive.
- Adjacency lists need indexes supporting `(tenant_id, parent_id)` and the node primary key.
- Nested sets usually need a suitable index on `lft`; finding ancestors with two inequalities may still inspect many rows.

Change designs only after identifying the **actual bottleneck**: index lookup, returned row count, network, locking, or maintaining auxiliary structures.

## 12. Concurrency, Integrity, and Operational Cost

A fast-reading model may come at the price of maintaining extensive derived data. For trees, the most important invariants are usually:

- Nodes exist and belong to a specific tenant.
- Parents exist in the same tenant; each node has at most one parent.
- No self-parenting and no longer cycles.
- Authoritative parent–child links never contradict paths/closure/nested set intervals.
- Branch moves never leave auxiliary data **half-updated** and exposed to other requests as if complete.

### Concurrency When Two Branches Move Simultaneously

Suppose transaction T1 checks "A is not under B" and T2 checks "B is not under A"; both read the old tree and both succeed. If they then set A under B and B under A without synchronization, a cycle is formed.

Therefore, even an adjacency list with a single-row parent update needs a centralized write path, proper locking/isolation, and transaction error handling. With materialized path and closure table, dependent rows must also be locked/coordinated so concurrent writes do not construct inconsistent derived structures.

If storing **two representations** (e.g., `parent_id` and `path`), define which is the source of truth, which is derived, who may modify it, and the transactional sync mechanism. A background job fixing paths minutes later might be acceptable for an eventually consistent search cache, but not if the API promises moved categories appear consistently immediately after commit.

### Deletion and Ownership Scope Changes

Deleting a node with children is also a tree-structure update. Under `ON DELETE RESTRICT`, handle children first; under `CASCADE`, the entire branch and dependent data may be deleted. Materialized path and closure tables need policies to delete derived records; nested sets need interval renumbering if keeping contiguous numbering.

Moving a node to another tenant is not merely updating `tenant_id`: FKs, access permissions, unique keys, and auxiliary structures can all be affected. Usually define a separate "cross-tenant copy/migrate" operation rather than treating it as a normal reparenting.

## 13. Extending the Comparison: Document, Graph, and Analytical Systems

### 13.1. Document

If an entire subtree is usually read together, multiple nodes can be embedded in one document. One document read returns the whole branch without joins, but large documents and moving branches across two documents can become expensive, especially when cross-document transactions are needed.

If each node is a document with `parentId`, the problem returns close to an adjacency list. Enforcing parent existence and acyclicity depends on engine capabilities and application logic.

### 13.2. Graph

Graph databases store nodes and parent–child edges; ancestor/descendant queries are multi-hop edge traversals. With multi-parent relationships, diverse edge types, and complex path queries, graphs can express things more naturally than a single `parent_id`.

However, "using a graph" **does not automatically solve** cycles, permissions, or branch-move transactions. Read cost depends on traversed vertices/edges, indexing, and engine; write cost may touch just one edge yet still requires checking DAG/tree invariants.

### 13.3. Analytics and Tree History

An enterprise moves the "Platform" unit from "Engineering" to "Operations" on July 1. If June's revenue report must reflect the structure **as of June**, storing only the current `parent_id` or updating current paths/closure is **insufficient**.

Effective-dated history is needed: e.g., `valid_from`/`valid_to` on parent–child links, periodic snapshots, or versioned hierarchy tables. Querying "ancestors at time T" differs from "current ancestors"; do not apply the same cost table if traversing multiple versions. In a data warehouse, snapshot/bridge tables with version keys are often more sensible than copying current nested sets.

Choosing a structure must consider both the **current tree** and the **tree over time**, especially when data drives reporting, auditing, or metric allocation.

## 14. Quick Decision Matrix

| Dominant business condition | Model to evaluate first | Main reason |
|---|---|---|
| Frequent inserts/edits/branch moves; moderate depth | **Adjacency list** | Minimal structural rows written; easy to understand and protect with FKs |
| Heavy path/prefix branch reads; rare branch moves | **Materialized path** | Convenient prefix lookups when appropriately indexed |
| Very frequent ancestor/descendant/distance queries; rarely changing tree | **Closure table** | Ancestor–descendant data materialized and indexed in both directions |
| Mostly ordered full-branch reads; stable tree | **Nested sets** | Convenient `lft`/`rgt` range scans |
| Multiple parents or complex relationship paths | **Edge table / graph** | Represents structures more general than single-parent trees |
| Primarily reading small whole subtrees as a single document | **Nested document**, if size and transaction boundaries fit | Data locality benefits |

This is a **starting point for evaluation**, not an absolute selection rule. An application might use adjacency list as the source of truth, a closure table for frequent read queries, or a path cache; however, an auxiliary structure is valuable only if consistency can be maintained and rebuilt on failure.

## 15. Practice Exercise: Proposing a Structure for a Department Tree

An HR management system has 80,000 departments and teams across multiple enterprises. Each team has exactly one superior unit; each enterprise has an independent tree. Initial requirements:

- Average 12,000 times/day building a team's breadcrumb.
- Average 50,000 times/day fetching all child teams to compute access permissions.
- Roughly 200 times/day reassigning a team to a different superior unit.
- Some moved branches exceed 2,000 nodes.
- Last month's reports must preserve the structure as it existed last month.

Carry out these steps:

1. Define \(N,h,s,a_o,a_n\) and estimate them from real data, rather than taking one global average across the entire tree.
2. Choose a source-of-truth model and explain how it protects keys, tenants, parents, and acyclicity.
3. Compare expected read/write volumes of adjacency list, materialized path, closure table, and nested sets across three tasks: breadcrumbs, listing child teams, and moving branches.
4. Determine which locks or isolation levels the write path needs so two administrators cannot concurrently form a cycle.
5. Design a p95 benchmark and acceptance criteria: e.g., accurate subtree reads within latency budgets, no move transaction holding locks too long.
6. Propose how to store parent–child history for reporting against last month's tree; explain why a current-state tree table is insufficient.
7. Analyze whether a cache/closure table is needed as an auxiliary structure; if so, show how to update and rebuild it upon discrepancies.

**Evaluation criteria:** the choice must state assumptions about tree shape and operation frequency, distinguish structural rows written from total transaction duration, and specify how acyclicity is enforced under concurrent branch moves.

## 16. Things to Remember

- **Reading ancestors** typically scales with depth \(h\); **reading a subtree** must at minimum process the \(s\) result nodes. Indexes and storage structures determine how many steps are needed to reach those results.
- **Adjacency list** is lightweight and cheap in modified rows on moves, yet cycle checks and concurrency sync are not zero-cost.
- **Materialized path** aids prefix queries, but moving a branch requires rewriting paths of all descendants.
- **Closure table** speeds up ancestor/descendant reads via materialized data, trading off roughly \(N+\sum depth\) storage and relationship-pair update costs.
- **Nested sets** excel at subtree range scans, yet contiguous numbering means positional updates can affect very many nodes.
- **Renaming/attribute edits** and **reparenting** are two distinct workloads; measure them separately.
- Choose structures based on real data, latency/lock/storage metrics, and integrity requirements, while also evaluating needs for **historical trees over time**.
