# Cycle Detection, Multiple Parents, and When to Use a Graph

In hierarchical data modeling, we often start with the sentence "each node has one parent node". That makes sense for a **folder tree**, an **org chart with one direct manager**, or a **category taxonomy with a single parent branch**. Yet real requirements can change: a topic belongs to two groups, a skill has multiple prerequisite skills, or a service simultaneously depends on multiple other services.

At that point, the question is no longer merely "how do we store a parent key?" but rather **does the structure allow multiple parents, are cycles valid, and which relationships do queries need to traverse?** Three structures must be clearly distinguished:

- **Tree:** each node has at most one parent; no cycles; within a single tree there is one root.
- **Directed acyclic graph (DAG):** a node can have multiple parents or multiple paths from roots to it, yet **no directed cycles exist**.
- **General directed graph:** permits multiple directed relationships; **cycles may exist** if the business permits them.

This lesson belongs to the **Inheritance and Hierarchies** chapter of the **DATABASE_DATA_MODELING** module. The goal is to translate business rules into verifiable entities, relationships, and constraints; select appropriate keys, indexes, and relational, document, or graph schemas; and clarify how the system evolves when multiple parents or complex relationships arise.

> **Terminology distinction:** a "parent" in a **node tree** is a preceding node along a hierarchical edge. It is not automatically synonymous with a "supertype" (*parent type*) in **IS-A** inheritance. A category having two parent categories does not mean it is a subtype inheriting two data types; confirm whether this is a taxonomy, dependency, or composition structure.

## 1. Why a Single Parent Key Is Sometimes Insufficient

Consider an initial category tree:

~~~text
Categories (1)
├── Electronics (2)
│   └── Mobile Devices (4)
│       └── Smartwatches (5)
└── Accessories (3)
~~~

Suppose the business adds: **"Smartwatches must also appear under Accessories, while still remaining under Mobile Devices."** The structure is now:

~~~mermaid
flowchart TD
    A["Categories (1)"] --> B["Electronics (2)"]
    A --> C["Accessories (3)"]
    B --> D["Mobile Devices (4)"]
    D --> E["Smartwatches (5)"]
    C --> E
    E --> F["Android Watches (6)"]
~~~

Node 5 has **two direct parents**: 3 and 4. This is a **DAG**, because from 1 to 5 there are two paths:

- 1 → 3 → 5;
- 1 → 2 → 4 → 5.

No path returns to a previously visited node. If we add the edge **6 → 2**, we create the cycle **2 → 4 → 5 → 6 → 2**.

A single `parent_id` column in the node table cannot simultaneously store both parents of node 5. However, **do not rush into switching to a DAG**: if the requirement is merely "one *product* can belong to multiple categories", you can keep a **Category** tree and use a **ProductCategory** junction table. Multiple categories assigned to a product differ from multiple direct parents of a category itself.

### Questions to Decide the Structure

1. **Which object has multiple parents?** Category nodes, products, tasks, users, or roles participating in a context?
2. **What does an edge represent?** "Is a subcategory of", "depends on", "is referenced by", "reports to", "relates to", or "shares a group with"?
3. **Does edge direction matter?** A depending on B does not mean B depends on A.
4. **Is returning to the starting node allowed?** A cycle in a "must complete before" relation is an error; in a "follows" relation it may be completely normal.
5. **Can one pair of nodes have multiple edges of different types or effective periods?** If so, edge identity must store type, context, or time.
6. **Which queries must be fast?** Direct children, all descendants, paths, ancestors, transitive dependencies, shortest path, cycle detection, or impact paths.

## 2. Distinguishing Trees, Forests, DAGs, and Cyclic Graphs

| Property | Tree | Forest | DAG | General directed graph |
| --- | --- | --- | --- | --- |
| Direct parents per node | At most 1 | At most 1 | Can be many | Can be many |
| Number of roots | 1 if non-empty | Multiple trees, multiple roots | Multiple sources possible, depending on graph | May have no root |
| Directed cycles | No | No | **No** | Possible |
| Multiple paths from one node to another | No within one tree | No within the same tree | **Possible** | Possible |
| Typical model | `parent_id` | `parent_id` + tree scope | Parent–child edge table | Directed edge table, possibly with types/properties |
| Examples | Standard folder hierarchy | Multiple independent folder trees | Prerequisite skills, multi-parent taxonomy | Follow relationships, service mesh with diverse links |

A **forest** does not automatically become a DAG simply by having multiple roots. Conversely, a DAG is broader than a tree: it allows multiple parents and multiple paths; yet every tree is also a special case of a DAG.

In a hierarchy with multiple parents, the word **"depth"** no longer has a single unique answer. Node 5 in the example has a shortest path from root of length **2 edges** and a longest path of length **3 edges**. If a depth value is needed, you must specify whether it means:

- **shortest** distance from root;
- **longest** distance;
- depth along a **chosen display branch**;
- or depth of **each individual path**.

Similarly, one node may appear multiple times in a UI tree view when traversed by path, yet it remains **one single entity** with one unique `node_id` in the data.

## 3. Minimum Constraints for a Single-Parent Tree

An *adjacency list* model usually starts with a node table containing a self-referencing foreign key:

~~~sql
-- PostgreSQL: single-parent tree/forest model
CREATE TABLE tree_nodes (
    node_id   BIGINT PRIMARY KEY,
    label     TEXT NOT NULL,
    parent_id BIGINT REFERENCES tree_nodes(node_id),
    CONSTRAINT node_cannot_parent_itself CHECK (
        parent_id IS NULL OR parent_id <> node_id
    )
);

CREATE INDEX idx_tree_nodes_parent
    ON tree_nodes(parent_id);
~~~

Each row holds one `parent_id` value or NULL, so a node cannot have more than one direct parent. The foreign key ensures the parent **exists**; the `CHECK` condition prevents a one-edge cycle where **a node is its own parent**.

Yet those constraints **do not yet prevent longer cycles**:

~~~text
A.parent_id = C
B.parent_id = A
C.parent_id = B
~~~

All three foreign keys are valid if the three nodes already exist, and each node has a parent different from itself, yet the structure forms the loop `A → C → B → A` when following `parent_id`. A tree with a cycle is an invalid structure even when every foreign key is satisfied.

If the business requires **exactly one root**, a mechanism is also needed to ensure the count of nodes with `parent_id IS NULL` equals one within the tree scope. If multiple roots are allowed because a forest is being stored, do not enforce a single-root constraint. With tenant/tree_id data, checks and foreign keys must be scoped appropriately.

## 4. Using an Edge Table When a Node Has Multiple Parents

For a hierarchy that is genuinely a DAG, the right way to represent direct relationships is an **edge table**. Each row is directed from **parent_id → child_id**.

~~~sql
CREATE TABLE taxonomy_nodes (
    node_id BIGINT PRIMARY KEY,
    label   TEXT NOT NULL
);

CREATE TABLE taxonomy_edges (
    parent_id BIGINT NOT NULL REFERENCES taxonomy_nodes(node_id),
    child_id  BIGINT NOT NULL REFERENCES taxonomy_nodes(node_id),
    PRIMARY KEY (parent_id, child_id),
    CONSTRAINT no_self_edge CHECK (parent_id <> child_id)
);

-- Querying parents of a node typically starts at child_id.
CREATE INDEX idx_taxonomy_edges_child_parent
    ON taxonomy_edges (child_id, parent_id);

INSERT INTO taxonomy_nodes (node_id, label) VALUES
    (1, 'Categories'),
    (2, 'Electronics'),
    (3, 'Accessories'),
    (4, 'Mobile Devices'),
    (5, 'Smartwatches'),
    (6, 'Android Watches');

INSERT INTO taxonomy_edges (parent_id, child_id) VALUES
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 5),
    (4, 5),
    (5, 6);
~~~

In this table:

- **PRIMARY KEY(parent_id, child_id)** prevents duplicate directed edges.
- Two foreign keys ensure **both edge endpoints exist**.
- **CHECK(parent_id <> child_id)** prevents a self-loop, yet **does not block multi-edge loops**.
- Node 5 has two edge rows: `(3,5)` and `(4,5)`, so there is no need to duplicate the "Smartwatches" node.
- The inverted index supports querying parents of a node; the primary key already supports querying children by `parent_id`.

Fetching **direct parents** of node 5:

~~~sql
SELECT p.node_id, p.label
FROM taxonomy_edges AS e
JOIN taxonomy_nodes AS p ON p.node_id = e.parent_id
WHERE e.child_id = 5
ORDER BY p.node_id;
-- 3 Accessories; 4 Mobile Devices
~~~

Finding nodes with more than one parent:

~~~sql
SELECT child_id, COUNT(*) AS direct_parent_count
FROM taxonomy_edges
GROUP BY child_id
HAVING COUNT(*) > 1
ORDER BY direct_parent_count DESC, child_id;
-- node_id 5 has 2 direct parents
~~~

This query helps audit the structure, yet **multiple parents are not an error by default**. It is valid data for a DAG; it becomes a violation only if the business mandates each node has at most one parent.

### How to Enforce the "At Most One Parent" Rule

If using an edge table while still wanting a tree, a **UNIQUE(child_id)** constraint limits each node to at most one incoming parent edge:

~~~sql
-- Apply only if the business requires EACH node to have at most one parent.
-- Do not run on the DAG example above: node 5 currently has two parents.
ALTER TABLE taxonomy_edges
ADD CONSTRAINT one_parent_per_child UNIQUE (child_id);
~~~

To model a **multi-parent DAG**, **do not add** `UNIQUE(child_id)`. The "single parent" and "acyclic" rules are two **independent** constraints: lifting the single-parent limit does not mean permitting cycles.

## 5. Detecting Cycles Before Adding an Edge

Suppose we want to add edge **6 → 2**. This satisfies foreign keys and does not connect a node to itself, yet creates the cycle **2 → 4 → 5 → 6 → 2**.

For a proposed edge **P → C**, the rule is clear:

> The new edge creates a cycle **if and only if** `P = C`, or a directed path **C → … → P** already exists in the current graph.

Thus, to check edge `6 → 2`, start from **C = 2**, walk **downward through descendants**, and see whether **P = 6** is reached.

### 5.1. Checking Reachability with a Recursive CTE

~~~sql
-- Check proposed addition of edge parent_id=6, child_id=2.
-- TRUE means the new edge will create a cycle.
WITH RECURSIVE reachable(node_id) AS (
    SELECT 2::BIGINT

    UNION

    SELECT e.child_id
    FROM reachable AS r
    JOIN taxonomy_edges AS e ON e.parent_id = r.node_id
)
SELECT EXISTS (
    SELECT 1 FROM reachable WHERE node_id = 6
) AS would_create_cycle;
-- true: 2 -> 4 -> 5 -> 6 already exists
~~~

In the query above, **UNION** deduplicates `node_id` rows so traversal on a finite graph terminates even if existing data already contains a cycle. Using **UNION ALL** while storing only `node_id`, without tracking visited nodes, can cause the CTE to loop infinitely when hitting a cycle.

Checks must run **before both INSERT and UPDATE of edge endpoints**; modifying an edge can introduce a cycle just like inserting a new edge. Edge deletions cannot create new cycles, though they can break connectivity or minimum-parent requirements.

### 5.2. Why "Check Then INSERT" Is Still Not Safe Enough

Suppose initially A and B have no path between them:

- Transaction T1 checks and prepares to insert **A → B**.
- Transaction T2 concurrently checks and prepares to insert **B → A**.
- Each transaction reads the pre-insert state lacking the other's edge, so both conclude "no cycle".
- If both `INSERT` and `COMMIT` without coordination, the result forms the cycle `A ↔ B`.

This is a **race condition**, not a flaw in the reachability formula. Under a strict DAG policy, checking **and writing the edge must behave as one consistent operation**.

Suitable approaches include:

1. **Serialize mutations on the same graph/tenant** with a transaction lock applied consistently across **every** edge-changing operation, then run the reachability check and write inside the same transaction. In PostgreSQL, a *transaction-level advisory lock* on the tree/tenant ID can be used; choose lock keys and permissions so every writer obeys the convention.
2. **Use SERIALIZABLE transactions** and handle serialization errors by **retrying the entire transaction**. Verify all check/write operations participate under the same control; changing isolation level on a standalone read query alone is ineffective.
3. **Use a centralized write gate** or database trigger/procedure that performs checks and coordinates writes. A trigger that merely `SELECT`s path checks under default read behavior can still hit race conditions without synchronization.

Do not rely solely on a `SELECT` run prior to `INSERT` in the application layer. Foreign keys, `PRIMARY KEY`, and `CHECK` in the example only verify existence, uniqueness, and self-loops; **they do not automatically enforce graph-wide acyclicity**.

## 6. Detecting Existing Cycles Already in Data

When importing legacy data, syncing from another system, or suspecting corrupted writes to the edge table, you must find cycles that **already exist**.

### 6.1. Traversal with Path Tracking

In PostgreSQL, you can keep an array of visited `node_id`s. When the next step encounters an ID already in the array, mark a cycle and **stop expanding** that path.

~~~sql
WITH RECURSIVE walks AS (
    SELECT n.node_id AS start_id,
           n.node_id AS current_id,
           ARRAY[n.node_id]::BIGINT[] AS path,
           FALSE AS is_cycle
    FROM taxonomy_nodes AS n

    UNION ALL

    SELECT w.start_id,
           e.child_id,
           w.path || e.child_id,
           e.child_id = ANY(w.path)
    FROM walks AS w
    JOIN taxonomy_edges AS e ON e.parent_id = w.current_id
    WHERE NOT w.is_cycle
)
SELECT DISTINCT start_id, path AS cycle_containing_path
FROM walks
WHERE is_cycle
ORDER BY start_id, path;
~~~

On **the sample data before adding edge 6 → 2**, the query returns **zero rows**. To test inside a rollbackable transaction for illustration:

~~~sql
BEGIN;

INSERT INTO taxonomy_edges (parent_id, child_id)
VALUES (6, 2);

-- Run the cycle-detection query above:
-- paths with repeating segments such as 2 -> 4 -> 5 -> 6 -> 2 will appear.

ROLLBACK;
~~~

**Explanation:** Each walk starts from a node. At each step, the condition **e.child_id = ANY(w.path)** detects a repeated `node_id` along *that specific walk*. A branch marked `is_cycle = TRUE` stops expanding, preventing infinite recursion along that path.

However, when the graph is large and has **very many distinct paths** between the same two nodes, enumerating paths from **every node** can generate huge row counts even with no cycles. It suits illustration, diagnostics on bounded datasets, or resource-capped administrative checks; **it is not a high-performance monitoring strategy for arbitrary giant graphs**.

PostgreSQL versions supporting the **CYCLE** clause in recursive CTEs can also track visited nodes automatically. Whether using `CYCLE` or a path array, clearly choose the column representing "node state" for detecting revisits.

### 6.2. Is Traversing Only from the Root Enough?

**Not enough in all cases.** A group of cyclic nodes might have **no root** at all, or belong to a component unreachable from whichever root the query picks. Starting only from one catalog root can miss cycles elsewhere in the data.

Seeding from **all nodes** as shown above detects cycles across disconnected components, at high cost. For large datasets, use a whole-graph cycle detection algorithm, such as:

- **DFS with visiting state** (*gray/visiting*) to detect back-edges to a node currently on the recursion stack.
- **Kahn's algorithm / topological sorting:** repeatedly remove nodes with in-degree 0; if any nodes remain at the end, the graph contains directed cycles. Remaining nodes may include nodes downstream of a cycle, so this step mainly determines cycle existence.

These algorithms must run over a consistent snapshot of the edge set with appropriate resource bounds. If you only need to know **whether or not** cycles exist, enumerating every cyclic path is unnecessary.

## 7. Querying on a DAG: One Node, Multiple Paths

In a tree, each node in a branch usually has one unique path from the root. In a DAG, a recursive query can encounter the same node along multiple paths.

### 7.1. Getting the Reachable Node Set Without Path Duplication

~~~sql
WITH RECURSIVE descendants(node_id) AS (
    SELECT 1::BIGINT

    UNION

    SELECT e.child_id
    FROM taxonomy_edges AS e
    JOIN descendants AS d ON e.parent_id = d.node_id
)
SELECT n.node_id, n.label
FROM descendants AS d
JOIN taxonomy_nodes AS n ON n.node_id = d.node_id
ORDER BY n.node_id;
~~~

Because **UNION** deduplicates on **node_id**, node 5 appears **only once**, even though two paths lead from 1 to 5. This CTE returns the set of **reachable** nodes including root 1 itself. If you need "descendants excluding the root", filter out `node_id = 1`.

The `UNION` technique is especially suitable when you only care about **path existence** rather than specific paths or depths. It also ensures recursion terminates on finite graphs even if data contains cycles, provided the recursive row carries only `node_id` state.

### 7.2. When You Need Every Path or Level Count

When building per-branch breadcrumbs, a deduplicated `node_id` set is **insufficient**. You can track both `path` and `depth`, forbidding repeated nodes along a path:

~~~sql
WITH RECURSIVE paths AS (
    SELECT 1::BIGINT AS node_id,
           ARRAY[1::BIGINT] AS path,
           0 AS depth

    UNION ALL

    SELECT e.child_id,
           p.path || e.child_id,
           p.depth + 1
    FROM paths AS p
    JOIN taxonomy_edges AS e ON e.parent_id = p.node_id
    WHERE NOT e.child_id = ANY(p.path)
)
SELECT node_id,
       MIN(depth) AS shortest_depth,
       MAX(depth) AS longest_depth,
       COUNT(*) AS distinct_paths_from_root
FROM paths
GROUP BY node_id
ORDER BY node_id;
~~~

On the sample DAG, node 5 has **shortest_depth = 2**, **longest_depth = 3**, and **distinct_paths_from_root = 2**. The paths are `1 → 3 → 5` and `1 → 2 → 4 → 5`.

Counting paths can be very expensive: even a small-node DAG can have exponentially many paths. Only run path-enumerating queries when the business **genuinely needs every path** and graph size is bounded. If only unique ancestor counts are needed, use node-deduplicated traversal or a dedicated reachability structure.

### 7.3. Closure Tables on DAGs Need Clear Depth Semantics

A **closure table** keyed by **(ancestor_id, descendant_id)** can still record *whether a path exists* in a DAG. However, if each pair stores only **one depth**, you must define whether depth means:

- **shortest** distance;
- **longest** distance;
- or a value along a representative branch.

If both multiple distances and multiple paths are needed, you cannot simply reuse a **tree** closure table as if each pair had only one path. Furthermore, when a DAG has multiple paths from ancestor to descendant, **deleting one edge** does not necessarily eliminate reachability between two nodes. Blindly deleting a closure row just because one path disappeared corrupts data; reachability must be recomputed or path counts maintained under a defined algorithm.

## 8. When Can You Keep the Relational Model, and When Should You Use a Graph Database?

The fact that data is a **graph** mathematically **does not mandate** using a **graph database**. An RDBMS can store node and edge tables with recursive CTEs, indexes, and transactions; this suffices for very many systems.

| Requirement signal | Potentially suitable design | Reason |
| --- | --- | --- |
| Single-parent hierarchy, mostly displaying trees | Adjacency list in RDBMS | Compact structure, simple FK, recursive queries when needed |
| Small or medium DAG needing ancestors/descendants | Node–edge tables in RDBMS | Clear keys and indexes, CTEs handle reachability |
| DAG needing repeated transitive queries | Edge table + sensible cache/closure | Speeds up reads at the cost of update overhead and consistency control |
| Many relationship types across node types, path-pattern queries | Consider graph database | Traversal queries and edge-pattern matching can be more natural |
| Multi-hop analytics over large networks, variable path lengths | Evaluate graph database/graph engine | May suit specialized graph traversals/analytics |
| Primarily transactional workloads with strong relational constraints and short JOINs | RDBMS remains a strong candidate | No need to switch tech just for having an edge table |
| Weighted optimal pathfinding / routing | Appropriate graph engine/algorithm | Requires defining weights, edge directions, and path limits |

### Questions Worth Measuring Before Choosing Technology

- **Node/edge counts:** tens of thousands, millions, or billions? Is node degree distribution heavily skewed?
- **Query hops:** just one or two hops, or variable long paths?
- **Query shape:** fetch all descendants, find cycles, shortest path, multi-edge-type patterns, or community analytics?
- **Update rate:** do edges change constantly alongside transactional business data?
- **Constraints:** are foreign keys, historical versions, tenant isolation, access control, and warehouse sync required?
- **Operations:** can the team administer, monitor, back up, authorize, replicate, and verify correctness on the chosen technology?

**A graph database does not automatically prevent cycles**, nor does it know by default which edges are business-valid. If a taxonomy must be a DAG, the system still needs cycle-prevention rules even when stored in a property graph with nodes and relationships.

## 9. Designing Graphs with Multiple Relationship Types

When a system has multiple relationship kinds, a single `parent_id` column or a single `taxonomy_edges` table can become overly generic or semantically wrong.

For example, a training platform has:

- **Skill REQUIRES Skill:** skill A must come before skill B. Usually requires a **DAG** for valid learning sequences.
- **Course TEACHES Skill:** a course teaches a skill; this is a relationship between two entity types, not a parent–child edge.
- **User FOLLOWS User:** users following one another; **two-way cycles are completely valid**.
- **Team MEMBER_OF Organization:** members belonging to an organization; has different cardinality, temporal, and role rules.

Do not use one generic relationship column named `parent_id` for all four cases. Model edge types, directions, and constraints per relationship kind:

| Edge type | Possible structure | Cycles | Constraints to confirm |
| --- | --- | --- | --- |
| `PREREQUISITE` | `Skill → Skill` | Usually forbidden | No self-reference; no return paths; skill versioning |
| `SUBCATEGORY_OF` | `Category → Category` | Forbidden | Allowed parent count, same taxonomy/tenant |
| `FOLLOWS` | `User → User` | Can be valid | Is self-follow allowed; duplicate pair allowed? |
| `MEMBER_OF` | `User → Group` | Heterogeneous node types | Effective period, group role, active status |
| `DEPENDS_ON` | `Service → Service` | Depends on goal | Are dependency cycles blocked from deployment, or accepted for analysis? |

A property graph can define corresponding node/edge labels, while an RDBMS can use **dedicated relationship tables** rather than stuffing every link into one polymorphic table. Avoid a generic edge table with `source_type`/`source_id`/`target_type`/`target_id` when doing so sacrifices **verifiable foreign keys** to each target entity type. If a generic edge table is used, add explicit referential and relationship-type enforcement mechanisms.

### Temporal Relationships

A node having two parents **at two different points in time** does not necessarily mean having **two concurrent parents**. If the business allows reparenting, store effective history:

~~~text
HierarchyEdge(
  parent_id,
  child_id,
  valid_from,
  valid_to
)
~~~

At a point in time `t`, retrieve only edges whose effective interval contains `t`. If the rule "each node has at most one parent" applies **at each point in time**, forbid overlapping effective intervals for the same `child_id` across different parents. If the rule "no cycles" applies at each point in time, check cycles within **the graph of edges effective at that timestamp**, not solely across the union of all historical edges.

A graph merging all history might contain a return path even though **no concurrent cycle ever existed**. Conversely, a schema storing only current edges cannot answer "prior to the reorganization date, which parent did this node have?".

## 10. Data Quality, Tenant Isolation, and Operational Safety

### 10.1. Prevent Cross-Tenant Edges Against Policy

In a multi-organization system, `node_id` may be numbered per tenant. To guarantee edges only connect nodes within the same tenant, design composite keys upfront:

~~~sql
CREATE TABLE tenant_nodes (
    tenant_id BIGINT NOT NULL,
    node_id   BIGINT NOT NULL,
    label     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, node_id)
);

CREATE TABLE tenant_edges (
    tenant_id BIGINT NOT NULL,
    parent_id BIGINT NOT NULL,
    child_id  BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, parent_id, child_id),
    FOREIGN KEY (tenant_id, parent_id)
        REFERENCES tenant_nodes (tenant_id, node_id),
    FOREIGN KEY (tenant_id, child_id)
        REFERENCES tenant_nodes (tenant_id, node_id),
    CHECK (parent_id <> child_id)
);
~~~

Both composite FKs force both `parent` and `child` to exist **in the same `tenant_id` as the edge**. Reachability queries, cycle detection, parent-count checks, and update locks must all filter by the same `tenant_id`.

### 10.2. Checks You Should Have

| Invariant | Verification method |
| --- | --- |
| Every node has a unique identity | `PRIMARY KEY` on node table |
| Every edge connects two existing nodes | `FOREIGN KEY` on both endpoints |
| No duplicate edges in the same direction | `PRIMARY KEY`/`UNIQUE` on node pair |
| No self-edges if forbidden | `CHECK(parent_id <> child_id)` |
| At most one direct parent if a tree | `UNIQUE(child_id)` or `parent_id` column |
| No cycles if a DAG | Reachability check on edge insert/update + transaction coordination |
| Connects nodes only within the same tenant | Composite FKs, tenant-scoped queries, and access controls |
| One shared root if required | Check root count and connected scope |
| Edges effective at the right time | Valid effective intervals; check overlaps and point-in-time rules |

Rules such as **acyclicity**, **all nodes connected to a root**, or **exactly one root** are properties across **multiple rows**. A `CHECK` referencing only columns on a single row cannot prove them by itself.

### 10.3. Be Careful When Deleting Edges and Nodes

An edge can be deleted while preserving reachability if an alternate path exists in the DAG. For example, removing edge **3 → 5** still lets 1 reach 5 via `2 → 4 → 5`. Yet deleting edge **5 → 6** disconnects 6 from the root unless another edge exists.

Deleting a node referenced by edge FKs can be rejected or configured to cascade. For categories currently used by products or skills acting as prerequisites, physical deletion can cause lost references or history. Decide whether to delete all dependencies, rewire edges, archive as inactive, or forbid deletion.

## 11. Comparing Relational, Document, Graph, and Analytical Models

The rules "multiple parents" and "acyclic" exist at the **business level**; the storage engine merely dictates how they are represented and enforced.

| Architecture | Common representation | Strengths | Risks to control |
| --- | --- | --- | --- |
| **RDBMS** | node + edge, recursive CTE, optionally closure | PK/FK, transactions, JOINs, and shared business data | Cross-row cycle checks; deep traversal cost |
| **Document** | `parentIds`, `childIds`, or edge collection | Convenient single-document/node reads, flexible schema | Bidirectional updates drifting out of sync; cycles and cross-tenant edges; large documents |
| **Graph database** | directed, typed, attributed nodes/relationships | Expressive multi-relation modeling and natural path queries | Enforcing business rules, path traversal cost, authorization, and operations |
| **Data warehouse** | ancestor–descendant bridge, versioned edge tables | Hierarchical analytics and transitive impact | Double counting when multiple paths reach the same node, wrong temporal validity |

### Document Example for a Multi-Parent Node

~~~json
{
  "nodeId": 5,
  "label": "Smartwatches",
  "parentIds": [3, 4]
}
~~~

A `parentIds` array expresses two parents, yet **does not automatically detect cycles**; consistent validation and updates are needed. Also storing `childIds` on each parent creates **redundant bidirectional data** that must be kept synchronized on both sides. For relationships carrying properties like effective periods or classification sources, a separate **edges** collection can be easier to manage than ID arrays.

### Why Do Analytical Metrics Easily Get Double-Counted?

Suppose a product is assigned to category 5, which has two paths back to root 1. When joining orders to all paths from 5 up to 1, you can get **two rows corresponding to the same product/order**. Summing revenue across those rows **doubles revenue** even though the transaction occurred only once.

For reports classifying by **distinct ancestor sets**, deduplicate `(fact_id, ancestor_id)` pairs at the right grain. If the business requires **allocating revenue across branches**, define explicit weighting/allocation rules rather than applying `DISTINCT` mechanically. Two different questions yield different numbers, yet both can be valid given exact metric definitions.

## 12. Workflow for Turning Requirements into Verifiable Models

Use the following decision sequence during analysis:

1. **Write business statements about edges:** what does "A is parent of B" mean, in which direction, within which time frame and tenant?
2. **Count valid direct parents:** `0..1`, `exactly 1 except root`, or `0..N`? Distinguish "node has multiple parents" from "one object assigned to multiple groups".
3. **Determine whether cycles are valid or invalid:** especially for "prerequisite", "superior", and "component" relationships.
4. **Choose the structure:** tree/forest with `parent_id`; DAG with edge table; general graph if cycles or multiple relationship types exist.
5. **Choose technology once structure is clear:** RDBMS, document, or graph database depending on query shape, scale, and transaction needs.
6. **Design keys and indexes:** `node_id`, edge endpoint pairs, inverted index for finding parents, composite FKs for tenants, and effective periods if needed.
7. **Design cross-table constraints:** cycle checks on `INSERT`/`UPDATE`, parent counts, connectivity, state conditions; handle concurrent updates.
8. **Specify history and deletion rules:** on reparenting, expiration, deleting nodes with dependents, and historical version queries.
9. **Test quality with boundary cases:** three-node cycle, two transactions adding opposing edges, valid multi-parent nodes, cross-tenant edges, two paths reaching one node.
10. **Measure and tune:** use representative data to benchmark reachability queries, depth, edge counts, and path counts; cap path-enumeration queries prone to explosion.

## 13. Self-Check Exercises with Solutions

### Exercise 1. Are Multiple Parents Truly Needed?

**Problem:** A product can carry multiple tags; each tag belongs to exactly one parent group. A developer proposes giving the tag-group table multiple `parent_id`s because products have multiple tags.

**Solution:** **Not necessarily.** A product having multiple tags is a many-to-many **Product–Tag** relationship. Each `Tag` can still have a single parent `TagGroup`. A multi-parent model is needed only if **`TagGroup` or `Tag` itself** is allowed to belong to multiple direct parent groups.

### Exercise 2. Which Edge Addition Creates a Cycle?

**Problem:** A DAG has edges `1 → 2`, `2 → 4`, `4 → 5`, `5 → 6`. Evaluate three proposed edges: `6 → 2`, `3 → 5`, `6 → 7` (assuming nodes 3 and 7 already exist).

**Solution:** **6 → 2** creates the cycle **2 → 4 → 5 → 6 → 2**. The other two edges do not create cycles provided no existing path runs from 5 to 3 or from 7 to 6. Check the full graph before concluding in a real system.

### Exercise 3. Why Doesn't `UNIQUE(child_id)` Replace Cycle Checking?

**Problem:** Each node has only one parent. Why can a cycle still exist?

**Solution:** A `UNIQUE(child_id)` constraint only limits the number of **incoming** edges to a node. Three edges **A → B, B → C, C → A** give each node exactly one parent yet still form a cycle. Acyclicity must be checked separately.

### Exercise 4. How Do Multiple Paths Affect Reporting?

**Problem:** Node 5 has two paths from 1, and a transaction linked to node 5 has revenue 100. If joining transactions to all paths up to 1 and running `SUM`, what might the root report show?

**Solution:** If the `JOIN` produces two rows for the two paths, `SUM` yields **200** even though actual revenue is **100**. If revenue should be counted only once per unique ancestor set, deduplicate `(transaction, ancestor)` pairs or aggregate at the proper grain before joining.

### Exercise 5. When Is a Cycle Valid?

**Problem:** User A follows User B and User B follows User A. Should loops be forbidden?

**Solution:** For a **FOLLOWS** relationship, two-way loops can be completely valid behavior. If the same edge structure were used for course **PREREQUISITE**s, an `A → B → A` loop would make prerequisites contradictory and usually must be forbidden. It is **the semantics of the edge type** that determines the rule.

### Exercise 6. Two Concurrent Transactions

**Problem:** T1 checks then inserts `A → B`, T2 checks then inserts `B → A`. Each individual check reports "would not create a cycle". What is missing?

**Solution:** Missing a mechanism coordinating **reads and writes** within the same graph scope: transaction locks to serialize mutations, `SERIALIZABLE` with retries, or an equivalent mechanism. Running a reachability query once before `INSERT` is insufficient to enforce the invariant under concurrent updates.

## 14. Takeaways

- **Single parent** and **acyclicity** are two separate constraints; both must be determined from business requirements.
- **Multiple parents without cycles** leads to a **DAG**; **cycles permitted** leads to a general graph with rules specific to each edge type.
- When proposing edge **P → C**, reject it if **P = C** or **C already reaches P** along current directed edges.
- Querying a DAG requires distinguishing **unique nodes** from **paths**; multiple paths to a node do not mean multiple entities, nor do they mean metrics should be summed multiple times.
- **A graph database is a technology choice**, whereas a *graph* is a data structure. Many graph models can be represented and verified in an RDBMS, with technology selected according to real workload and query needs.

Modeling correctly prevents accidental cycles, avoids duplicating identities when a node has multiple parents, and ensures hierarchical, dependency, and role relationships remain verifiable from business requirements down to physical schemas.
