# Expanding Paths with APOC Using Explicit Bounds in Neo4j

In a Neo4j property graph, a single node can connect to tens, thousands, or millions of other nodes. When answering "Who can person A reach through at most three relationships?", "What routes lead to destination B?", or "Traverse only permitted relationships and skip blocked nodes", writing a long path pattern alone is insufficient. The query must specify **depth bounds, relationship direction, stopping conditions, anti-repetition rules, and maximum result volume**.

APOC (Awesome Procedures on Cypher) provides extension procedures for Neo4j. In the **APOC and Extensions** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson focuses on `apoc.path.expandConfig()` — a flexible path-traversal tool. The material connects directly to nodes, relationships, Cypher, path querying, optimization, and returning results to Java Driver or Spring Data Neo4j applications.

Goal after this lesson: write a traversal **with explicit bounds**, explain how each constraint changes the path set, and assess the risks of traversing a graph with heavy branching or cycles.

## 1. Why Are Bounds Needed When Expanding Paths?

Suppose each node has an average of `b` traversable relationships. Without pruning and with independent expansion at each step, the number of candidate paths up to depth `d` grows roughly as:

\[
b + b^2 + \cdots + b^d
\]

For instance, with `b = 10` and `d = 4`, a simple branching model can generate up to `10 + 100 + 1000 + 10000 = 11110` paths. This is purely illustrative; real graphs have shared nodes, cycles, parallel relationships between the same two nodes, and uniqueness rules, so actual path counts differ.

When you only need to check reachability to a target or retrieve a few short paths, returning all of them is wasteful:

- **CPU and traversal work:** evaluating many relationships at every step.
- **Memory:** intermediate or final paths may need to be buffered, especially when adding `collect(path)`.
- **Response size:** `path` embeds every node and relationship along the route, far larger than returning IDs or hop counts alone.
- **Latency:** a graph that fans out broadly in the first 2 hops can explode at hop 3.

Therefore, **`maxLevel`, `relationshipFilter`, `labelFilter`, `uniqueness`, `bfs`, and `limit`** must be designed together. Putting `LIMIT` only at the end of a Cypher query does not replace all traversal bounds.

## 2. APOC and Procedure Execution Prerequisites

APOC comprises procedures and functions extending Cypher. `apoc.path.expandConfig` belongs to APOC's graph-traversal group, normally included in **APOC Core** in supported Neo4j versions. Availability also depends on a **Neo4j-compatible APOC version**, installation method, procedure allowlist configuration, and account privileges.

You can check the procedure on the connected database:

```cypher
SHOW PROCEDURES
YIELD name
WHERE name = 'apoc.path.expandConfig'
RETURN name;
```

If zero rows are returned, check APOC installation, configuration, and access privileges. Never assume every Neo4j Aura tier or self-managed deployment enables the exact same procedure set.

Basic call structure:

```cypher
MATCH (start:SomeLabel {id: $startId})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'RELATED_TO>',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN path;
```

`start` is the starting node; the second argument is a **configuration map**. The procedure can yield multiple rows, each containing one `path`. Since this is a *traversal operation*, distinguish returned paths from the set of **unique destination nodes**.

> **Operational constraint:** a query is merely a learning example until verified against real data and runtime environment. On large graphs, start with small depth limits and inspect with `EXPLAIN`/`PROFILE` in an appropriate environment before widening scope.

## 3. Building a Small Graph with Branches and Cycles

Run the following `CREATE` statement **once in a test database**. Labels and relationship types carry the `ApocDemo` prefix to avoid colliding with live business models.

```cypher
CREATE
  (an:ApocDemoPerson {personId: 'P01', name: 'An'}),
  (binh:ApocDemoPerson:ApocDemoTrusted {personId: 'P02', name: 'Bình'}),
  (chi:ApocDemoPerson:ApocDemoTrusted {personId: 'P03', name: 'Chi'}),
  (dung:ApocDemoPerson:ApocDemoBlocked {personId: 'P04', name: 'Dũng'}),
  (em:ApocDemoPerson:ApocDemoTrusted {personId: 'P05', name: 'Em'}),
  (giang:ApocDemoPerson:ApocDemoTrusted:ApocDemoTarget
         {personId: 'P06', name: 'Giang'}),
  (han:ApocDemoPerson:ApocDemoTrusted {personId: 'P07', name: 'Hân'}),
  (an)-[:APOC_DEMO_FOLLOWS]->(binh),
  (an)-[:APOC_DEMO_FOLLOWS]->(chi),
  (binh)-[:APOC_DEMO_FOLLOWS]->(dung),
  (binh)-[:APOC_DEMO_FOLLOWS]->(em),
  (chi)-[:APOC_DEMO_FOLLOWS]->(em),
  (chi)-[:APOC_DEMO_FOLLOWS]->(han),
  (dung)-[:APOC_DEMO_FOLLOWS]->(giang),
  (em)-[:APOC_DEMO_FOLLOWS]->(giang),
  (han)-[:APOC_DEMO_FOLLOWS]->(giang),
  (giang)-[:APOC_DEMO_FOLLOWS]->(an),
  (binh)-[:APOC_DEMO_COLLABORATES_WITH]->(chi);
```

Sketch of the `APOC_DEMO_FOLLOWS` relationships:

```text
An (P01) ──► Bình (P02) ──► Dũng (P04, Blocked) ──► Giang (P06, Target)
     │             └─────► Em (P05) ─────────────► Giang
     └─────► Chi (P03) ──► Em (P05)
                   └─────► Hân (P07) ────────────► Giang

Giang (P06) ──► An (P01)      [cycle-forming edge]
Bình (P02) ──► Chi (P03)      [COLLABORATES_WITH, different type]
```

Where:

- `An` is the start node (`P01`); `Giang` is the target (`P06`).
- `Dũng` has label `ApocDemoBlocked` and will be excluded in the node-filtering example.
- `Giang → An` forms a cycle; traversing deeply enough can cause the same node to reappear along a path.
- `APOC_DEMO_COLLABORATES_WITH` is included to demonstrate the effect of filtering by relationship type.

You can inspect the sample graph directly:

```cypher
MATCH (n:ApocDemoPerson)
RETURN n.personId AS id, n.name AS name, labels(n) AS labels
ORDER BY id;
```

Expect 7 nodes; running `CREATE` repeatedly creates duplicate data and invalidates the counts shown in this lesson.

## 4. First Expansion: Depth and Relationship Direction

Retrieve paths from `An` over at least one and at most two **outgoing** `FOLLOWS` relationships:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2,
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

On the baseline dataset, there are:

| Depth | Paths by `personId` | Path Count |
| --- | --- | ---: |
| 1 | `P01→P02`, `P01→P03` | 2 |
| 2 | `P01→P02→P04`, `P01→P02→P05`, `P01→P03→P05`, `P01→P03→P07` | 4 |
| **Total** | | **6** |

The two paths `P01→P02→P05` and `P01→P03→P05` both end at `Em` yet are **two distinct paths**. This makes sense when asking for "all routes", but not if the application only wants **a list of reachable people** regardless of route.

### 4.1. Meaning of minLevel and maxLevel

- `minLevel: 1`: returns only paths with 1 or more relationships; excludes the 0-hop path consisting solely of the start node.
- `maxLevel: 2`: does not traverse farther than 2 relationships from start.
- `minLevel: 0`: can include the length-0 path if filters and output conditions permit.
- Omitting a depth bound on a large graph is risky. **Always set an explicit `maxLevel`** on user-facing endpoints unless another work-bounding guard exists and business logic genuinely requires it.

`maxLevel` caps **the number of edges per path**; it does **not** cap the number of nodes/paths at each depth. A single node with thousands of edges can still generate thousands of candidates at depth 1.

### 4.2. Relationship direction and type

`relationshipFilter` controls edge types and directions:

| Configuration | Meaning |
| --- | --- |
| `'APOC_DEMO_FOLLOWS>'` | Traverse only `FOLLOWS` outgoing from the current node |
| `'<APOC_DEMO_FOLLOWS'` | Traverse only `FOLLOWS` incoming to the current node |
| `'APOC_DEMO_FOLLOWS'` | Allow both directions of type `FOLLOWS` |
| `'APOC_DEMO_FOLLOWS>|APOC_DEMO_COLLABORATES_WITH>'` | Allow either edge type, both outgoing |

Segments separated by `|` express type/direction alternatives. Adding another relationship type usually **expands the candidate set**; for instance, `Bình→Chi` of type `COLLABORATES_WITH` is traversed only if the filter permits that type.

In follower-graph queries, dropping `>` can allow paths to **reverse follower direction**. The query remains syntactically valid yet violates business semantics.

## 5. Filtering Nodes with labelFilter

To forbid traversing through blocked nodes, use `labelFilter` with the `-` prefix:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

Result set on the sample graph:

| Depth | Destinations by Path | Path Count |
| --- | --- | ---: |
| 1 | Bình, Chi | 2 |
| 2 | Em via Bình; Em via Chi; Hân via Chi | 3 |
| 3 | Giang via Bình→Em; Giang via Chi→Em; Giang via Chi→Hân | 3 |
| **Total** | | **8** |

No paths pass through `Dũng`. Removing `labelFilter` increases paths at depths 1–3 to **10** (adding `An→Bình→Dũng` and `An→Bình→Dũng→Giang`).

### 5.1. Label filter operators

APOC supports standard prefixes in `labelFilter`:

| Prefix | Typical Meaning |
| --- | --- |
| `+Label` | Allowlist: node must carry an allowed label |
| `-Label` | Denylist: exclude nodes carrying this label |
| `>Label` | End node: valid path termination; expansion may still continue through it |
| `/Label` | Termination node: valid end node and **stop expanding further past this node** |

For example, to allow only trusted nodes while forbidding `Blocked` nodes:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '+ApocDemoTrusted|-ApocDemoBlocked',
  filterStartNode: false,
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'NODE_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route;
```

`An` lacks the `ApocDemoTrusted` label, yet `filterStartNode: false` prevents applying the label filter to the start node itself. Subsequent nodes must satisfy the allow/deny rules. When combining multiple filter operators, rule groups follow specific precedence; never assume written order of `+`, `-`, `>`, `/` equals execution priority.

**Note:** `labelFilter` filters the graph by labels. It does not replace user-level or tenant-level authorization at the application/database layer. Models containing sensitive data must enforce access privileges independently of traversal filters.

## 6. Finding Paths to Targets with endNodes and terminatorNodes

When asking "Which paths lead from An to Giang?", you must constrain the **destination**. Using `maxLevel: 3` alone also returns paths ending at Bình, Chi, Em, and Hân even though the application does not want them.

You can pass target nodes via `endNodes` or `terminatorNodes`. Distinguish the two concepts:

- **`endNodes`:** marks nodes that are valid path endpoints to emit; traversal may still continue through them if other rules allow.
- **`terminatorNodes`:** marks target nodes where, once reached, that branch stops expanding, avoiding overshooting the destination.

Example finding only paths ending at Giang, avoiding Dũng, and spanning at most three relationships:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
MATCH (target:ApocDemoPerson {personId: 'P06'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  terminatorNodes: [target],
  bfs: true,
  uniqueness: 'RELATIONSHIP_PATH',
  limit: 20
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route
ORDER BY hops, route;
```

On the sample data, there are **3 paths**:

1. `P01 → P02 → P05 → P06` (An → Bình → Em → Giang).
2. `P01 → P03 → P05 → P06` (An → Chi → Em → Giang).
3. `P01 → P03 → P07 → P06` (An → Chi → Hân → Giang).

Paths through Dũng are filtered out; the `Giang→An` edge is not expanded after reaching the target because `terminatorNodes` was used. In another use case where you need to keep tracing **past** an intermediate target node, use `endNodes` instead of `terminatorNodes`.

If the business requirement is "find **one** path to Giang", you can combine `bfs: true` with `limit: 1` and `terminatorNodes` to favor fewer hops. However, when multiple paths tie in depth, **never assume which specific route is returned** without an additional tie-breaking rule.

## 7. BFS vs. DFS: Choosing How Results Are Collected

`bfs` controls traversal strategy:

- `bfs: true` (breadth-first search): expands layer by layer from near to far. Suitable when favoring **fewer relationships** along with a cap on returned paths.
- `bfs: false` (depth-first search): dives deep down one branch before backtracking to others. Suitable for certain path-exploration tasks, though with `limit` it may return deep paths before exploring closer branches.

`bfs` is **not equivalent to weighted shortest-path algorithms**. Each step represents a relationship hop; if edges carry weights like travel time, cost, or risk, use an appropriate weighted path algorithm rather than assuming BFS finds the cheapest route.

Example comparing strategies with identical filters:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  limit: 4,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route;
```

Change `bfs: true` to `bfs: false` to test DFS. **`limit: 4` caps the number of paths returned by the procedure**; it does not mean traversing exactly 4 nodes/relationships. Which paths survive can differ due to visitation order. If you need deterministic presentation order, apply `ORDER BY` after returning paths; note that downstream sorting cannot recover candidates already dropped by the procedure's `limit`.

## 8. Uniqueness: How Many Times Can a Node Appear?

The same destination node can be reached via multiple paths. APOC lets you configure the `uniqueness` strategy, which strongly impacts path counts and traversal workload.

| Strategy | Meaning | Effect During Traversal |
| --- | --- | --- |
| `RELATIONSHIP_PATH` | A relationship cannot repeat **within the same path** | May revisit a node via a different relationship; allows multiple paths to the same target |
| `NODE_PATH` | A node cannot repeat **within the same path** | Prevents cycles returning to the same node in a path while preserving alternative paths to a target |
| `NODE_GLOBAL` | Do not revisit a node once seen anywhere across the traversal under this strategy | Suppresses node revisits, which can prune alternative routes |
| `RELATIONSHIP_GLOBAL` | Controls relationship reuse globally across the traversal | May prune alternative routes that reuse an edge |

### 8.1. Cycle example: Giang → An

The graph has the 4-hop path `An→Chi→Hân→Giang→An`. Under `RELATIONSHIP_PATH`, no relationship repeats, so the route looping back to An can appear:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 4,
  maxLevel: 4,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route;
```

Changing `uniqueness` to `'NODE_PATH'` returns **no** 4-hop paths like this, because `An` would have to appear twice. This is a difference in **result set semantics**, not merely performance.

### 8.2. Choosing uniqueness by goal

- When the problem needs **all valid routes** within a small radius, `RELATIONSHIP_PATH` or `NODE_PATH` is generally preferable to globally banning revisited nodes.
- When you only need the **set of reachable nodes** and accept dropping alternative routes, consider `NODE_GLOBAL` or a dedicated subgraph-node procedure.
- When asked for "every way to reach Giang", do not blindly pick `NODE_GLOBAL`: one path reaching Em can block another path from passing through Em, reducing the routes found to Giang.

Some uniqueness strategies behave differently when combined with BFS vs. DFS. Test actual path counts on a small representative dataset before assuming one is universally optimal.

## 9. Capping Results Is Not Capping Work

Compare two places to apply a limit:

```cypher
// Limit inside the procedure
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 3,
  limit: 5
})
YIELD path
RETURN path;
```

```cypher
// Limit after the procedure emits paths into the Cypher stream
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 3
})
YIELD path
WITH path
ORDER BY length(path)
LIMIT 5
RETURN path;
```

The first query tells the procedure to emit at most 5 paths; the second applies the limit **after sorting by length**, so it may evaluate many paths before keeping 5. In some plans Cypher can stream results, yet `ORDER BY` and other blocking operators typically force more work before `LIMIT`.

Still, **neither approach acts as an absolute cap on CPU or inspected relationships**:

- `maxLevel` caps the depth of each path, yet a single level can fan out very widely.
- APOC's `limit` caps **returned paths**, not necessarily the exact number of nodes/relationships inspected to find valid paths.
- External `ORDER BY` sorts received results and does not alter internal traversal order.
- A trailing `collect(path)` can buffer very large path lists unless results are narrowed first.

For public APIs or user-parameterized exploration queries, **enforce `maxDepth`, `maxPaths`, and allowed relationship types at the application tier**, alongside any timeout/resource guards supported by your deployment.

## 10. Counting Destination Nodes and Returning Lean Payloads

If the UI only wants a **list of people reachable** within three hops, returning full `path` objects produces duplicates for the same destination. For example, Em and Giang appear across multiple paths.

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
WITH last(nodes(path)) AS person
RETURN DISTINCT person.personId AS personId,
       person.name AS name
ORDER BY personId;
```

On the sample data, the result has **5 distinct destination nodes**: P02 (Bình), P03 (Chi), P05 (Em), P06 (Giang), P07 (Hân). `DISTINCT` deduplicates the output, though if the procedure already expanded many paths, that traversal cost **does not vanish**.

If only the count of destinations is needed:

```cypher
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  uniqueness: 'RELATIONSHIP_PATH'
})
YIELD path
RETURN count(DISTINCT last(nodes(path))) AS reachablePeople;
```

The answer is **5**, distinct from **8** paths. When the goal is node reachability rather than route enumeration, evaluate dedicated procedures such as `apoc.path.subgraphNodes` with matching bounds. Regardless of which procedure you choose, benchmark on a realistic graph; never assert one call is always faster without measuring.

To reduce payload size over the Java Driver, project `personId`, `name`, `hops`, or ID lists rather than returning full nodes and relationships unless the client genuinely needs to render the detailed path.

## 11. Parameterized Queries for Java Applications

An API commonly accepts a starting ID and enforces maximum depth and maximum path count. Pass **values** via Cypher parameters—never concatenate user strings directly into queries.

```cypher
MATCH (start:ApocDemoPerson {personId: $startId})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: $maxDepth,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: $maxPaths
})
YIELD path
RETURN length(path) AS hops,
       [n IN nodes(path) | n.personId] AS route;
```

The application layer must **validate and cap** parameters before passing them:

| Parameter | Example API Rule |
| --- | --- |
| `$startId` | Must belong to an entity the caller is authorized to access |
| `$maxDepth` | Integer within `1..3` for this illustrative endpoint |
| `$maxPaths` | Integer within `1..100` for this illustrative endpoint |
| `relationshipFilter` | Hard-coded or allowlisted per business domain; never open arbitrary relationships |
| `labelFilter` | Server-controlled model rule; never accept raw filter syntax from clients |

The `1..3` and `1..100` bounds are **illustrative API policy examples**, not universal Neo4j technical limits. Measure and tune them to your graph's branching factor, resources, user requirements, and latency SLAs.

With the Neo4j Java Driver, execute the Cypher above inside a read transaction with `Map.of("startId", "P01", "maxDepth", 3, "maxPaths", 100)`, then read `route` and `hops`. With Spring Data Neo4j, use a custom Cypher query and a suitable projection DTO; avoid hydrating a large `path` into an entire entity graph if you only need a list of IDs.

**Never treat APOC as a standalone authorization layer.** Allowing users to supply huge `maxDepth` values or arbitrary `relationshipFilter` strings lets APIs probe unintended edge types even when Cypher syntax is parameterized. Enforce data access policies before/after traversal according to your security model.

## 12. Comparing with Plain Cypher Paths and Other Algorithms

If you only need a straightforward pattern "go from A along one relationship type up to three hops", plain Cypher often suffices:

```cypher
MATCH path = (a:ApocDemoPerson {personId: 'P01'})
             -[:APOC_DEMO_FOLLOWS*1..3]->
             (b:ApocDemoPerson)
WHERE NONE (n IN nodes(path) WHERE n:ApocDemoBlocked)
RETURN [n IN nodes(path) | n.personId] AS route,
       length(path) AS hops
ORDER BY hops, route;
```

This example uses variable-length relationship syntax familiar from Cypher 5. For Cypher 25 and newer releases, check quantified path patterns / quantified relationships. Results and performance between the two approaches can differ due to uniqueness semantics and planner vs. procedure execution; **never compare speed without first verifying both return the exact same desired path set**.

| Requirement | Tool to Consider |
| --- | --- |
| Short pattern matching with few special rules | Cypher `MATCH`, appropriate quantified path patterns |
| Traversal with multiple relationship/label filters, end/terminator lists, uniqueness modes | `apoc.path.expandConfig` |
| Reachable subgraph nodes only | `apoc.path.subgraphNodes` or equivalent reachability query |
| Shortest path by **hop count** with explicit constraints | Cypher shortest-path or suitable algorithm |
| Best path by edge **weights** | Weighted graph algorithms, e.g., Graph Data Science if licensed/installed |

APOC is a **pragmatic procedure toolkit**, not mandatory for every path query; some problems are better optimized by the Cypher planner when expressed entirely as query patterns.

## 13. Reading EXPLAIN and PROFILE Properly with APOC

Start with `EXPLAIN`:

```cypher
EXPLAIN
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN length(path) AS hops;
```

`EXPLAIN` plans without executing the query. The plan shows `ProcedureCall`, though it **does not necessarily expose every internal traversal step inside APOC**. To measure execution, run `PROFILE` for read-only traversals on a test graph:

```cypher
PROFILE
MATCH (start:ApocDemoPerson {personId: 'P01'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  labelFilter: '-ApocDemoBlocked',
  minLevel: 1,
  maxLevel: 3,
  bfs: true,
  uniqueness: 'NODE_PATH',
  limit: 100
})
YIELD path
RETURN length(path) AS hops;
```

What to inspect:

1. **Input row count:** does `MATCH start` yield exactly one start node? If `MATCH` is non-selective, the procedure is invoked for many starts and cost multiplies.
2. **Procedure output row count:** are more paths returned than expected? One destination node may appear on many paths.
3. **Path lengths:** do any exceed `maxLevel`, or show unexpected relationship types/directions?
4. **Actual latency and memory:** do `PROFILE`/logs/application metrics confirm the endpoint is safe under expected load?
5. **Payload:** do you need the full path or just target node IDs? Does response size blow up with depth?

**Measurement caveat:** `PROFILE` reports execution metrics exposed by Neo4j, but may not explicitly itemize every edge inspected inside an APOC procedure. Returning "8 paths" does not mean the procedure read only 8 relationships.

## 14. Common Design Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Omitting `maxLevel` on graphs with branches and cycles | Unbounded business depth; unpredictable workload | Set a small `maxLevel` configurable within a controlled cap |
| Adding only `RETURN ... LIMIT 10` | Does not guarantee the procedure visits only 10 paths | Use `limit` inside the procedure and benchmark; reduce depth/breadth |
| Leaving `relationshipFilter` overly broad or unset | Traverses unintended edge types/directions | Explicitly specify permitted types and directions |
| Confusing `endNodes` with `terminatorNodes` | Continues traversing past destination nodes | Choose accurately between "valid endpoint" and "stop here" |
| Using `NODE_GLOBAL` when all routes are needed | Drops alternative paths to the same node | Use path-level uniqueness with a small bounded scope |
| Using `RELATIONSHIP_PATH` assuming nodes cannot repeat | Same node can reappear via a different edge | Use `NODE_PATH` when node repetition must be prevented |
| Counting `count(*)` to count reachable people | Counts paths, double-counting people | Use `count(DISTINCT last(nodes(path)))` |
| Returning unbounded `collect(path)` | Holds huge path lists in memory and inflates payloads | Project only needed fields and cap output |
| Selecting start nodes with a broad scan | Procedure runs for many start nodes | Use business keys/indexes and bound start count |
| Believing BFS finds the "cheapest route" | Confuses hop count with edge cost sum | Pick a weighted shortest-path algorithm when weights matter |
| Treating `labelFilter` as complete authorization | Label conditions do not cover all access rules | Enforce tenant/user authorization independently |

## 15. Safe Implementation Checklist

When building a "relationship exploration" feature on real data:

1. **Define the question:** do you need all paths, one path, reachable target nodes, or just a boolean connectivity check?
2. **Select start nodes via stable keys:** bound input node counts; add indexes/constraints where appropriate.
3. **Lock down `relationshipFilter` and direction:** traverse only relationship types reflecting business intent.
4. **Lock down valid node scope:** `labelFilter`, allowlists/denylists, and organization/tenant access checks.
5. **Set depth bounds:** `minLevel`, `maxLevel`, and `endNodes`/`terminatorNodes` rules.
6. **Choose uniqueness:** `NODE_PATH` to forbid revisiting nodes within one path; `RELATIONSHIP_PATH` when alternative routes are needed; `NODE_GLOBAL` when global node-only traversal suffices.
7. **Choose BFS/DFS and limit:** decide whether to favor near paths or branch depth; cap returned path counts.
8. **Slim down output:** project IDs, names, and hop counts instead of full paths when unneeded.
9. **Benchmark on a representative graph:** check path count, target node count, latency, CPU/memory, and payload size; test high-fanout and cyclic cases.
10. **Enforce API ceilings:** never let callers arbitrarily widen `maxDepth`, `maxPaths`, or open sensitive relationships.

### Self-Check Questions

**Question 1.** Why does `maxLevel: 3` not guarantee the query inspects at most three relationships?

**Question 2.** On the sample data, how many paths and how many distinct target nodes do `minLevel: 1`, `maxLevel: 3`, `relationshipFilter: 'APOC_DEMO_FOLLOWS>'`, and `labelFilter: '-ApocDemoBlocked'` return?

**Question 3.** If you only need to reach `Giang` and stop, why is `terminatorNodes: [target]` appropriate?

**Question 4.** Why can `NODE_GLOBAL` be unsuitable when asked to list all paths to `Giang`?

**Question 5.** Given the `Giang→An` cycle, how do `NODE_PATH` and `RELATIONSHIP_PATH` differ?

**Question 6.** Does `bfs: true` prove a route is optimal for shipping cost or risk weights on relationships?

**Suggested Answers:** (1) It caps depth **per path**; a single node may have many incident edges to inspect. (2) **8 paths**, **5 destinations**. (3) The traversal branch stops once the destination is reached. (4) Already-visited nodes can prune alternative routes. (5) `NODE_PATH` forbids repeating a node, whereas `RELATIONSHIP_PATH` only forbids repeating a relationship on the same path. (6) No; BFS minimizes hop count, not arbitrary edge-weight sums.

## 16. References

- [Neo4j APOC — apoc.path.expandConfig](https://neo4j.com/docs/apoc/current/overview/apoc.path/apoc.path.expandConfig/): configuration map, examples, and bounding options.
- [Neo4j APOC — Path Expanding Procedures](https://neo4j.com/docs/apoc/current/graph-querying/expand-paths/): semantics of relationship/label filters, end and terminator nodes.
- [Neo4j Cypher Manual — Variable-Length Patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/): expressing paths in Cypher.
- [Neo4j Cypher Manual — Execution Plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): distinguishing EXPLAIN, PROFILE, and reading execution plans.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): parameter binding, reading results, and managing read transactions.

**Key takeaway:** a useful path expansion must **bound relationship types/directions, node labels, depth, repetition rules, and result count**. `apoc.path.expandConfig` lets you express these bounds in a single call, yet performance and correctness still depend on graph topology, APOC version, and how the application consumes results.
