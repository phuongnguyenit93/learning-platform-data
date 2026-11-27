# Distinguishing Cypher Path Queries from Specialized Graph Algorithms

In Neo4j, both **Cypher path queries** and **specialized graph algorithms** operate on the nodes and relationships of a property graph. However, they solve different classes of problems:

- **Cypher** expresses the relationship pattern to match, filters data, combines business conditions, and returns matching nodes, relationships, or paths.
- **Graph algorithms** solve a well-defined mathematical problem over network topology, such as **minimum-total-weight** paths, reachability, node importance, or connected components. In Neo4j, many of these algorithms are provided via the **Graph Data Science (GDS)** library, typically executed on an in-memory graph projection.

This topic belongs to the **Paths and Graph Traversal** chapter of module **DATABASE_ENGINE_GRAPH_NEO4J**: using Neo4j to model connected data as a property graph, query relationships and paths with Cypher, and combine indexes/constraints, data ingestion, the Java Driver, Spring Data Neo4j, and operational considerations. The goal of this lesson is to recognize **when to query a path pattern vs. when to run an algorithm**, avoiding confusing "shortest by hop count" with "optimal by cost."

## 1. Understanding the Basics: Paths, Hops, and Weights

Consider a network of transfer stops where each `:TRIP` relationship gives travel time:

```text
(A) ──90 min──▶ (B)
 │
 └──10 min──▶ (C) ──10 min──▶ (B)
```

There are two paths from A to B:

| Path | Hops | Total Time (weight/cost) |
| --- | ---: | ---: |
| A → B | 1 | 90 min |
| A → C → B | 2 | 20 min |

If you ask **"fewest hops?"**, the answer is A → B. If you ask **"fastest in minutes?"**, the answer is A → C → B. Both answers are correct for two different objectives.

A path in Cypher is a sequence of nodes joined by matching relationships. Key functions:

| Cypher Function | Meaning |
| --- | --- |
| `nodes(p)` | Ordered list of nodes on path `p` |
| `relationships(p)` | List of relationships on the path |
| `length(p)` | Number of relationships in the path, i.e., hop count |
| `reduce(...)` | Can sum weights from relationships along the path |
| `shortestPath(...)` | Finds the shortest path by **relationship count** within a given pattern |

**Decisive point:** a property such as `r.minutes` is a **business weight**, whereas `length(p)` only counts relationships. Having a `minutes` property on relationships does not make `shortestPath()` automatically optimize by minutes.

## 2. Building a Small Graph to Observe

The examples below use label `:Stop`, property `code`, and directed relationship `:TRIP`. Practice on a test database:

```cypher
MERGE (a:Stop {code: 'A'})
MERGE (b:Stop {code: 'B'})
MERGE (c:Stop {code: 'C'})
MERGE (a)-[ab:TRIP]->(b)
SET ab.minutes = 90
MERGE (a)-[ac:TRIP]->(c)
SET ac.minutes = 10
MERGE (c)-[cb:TRIP]->(b)
SET cb.minutes = 10;
```

`MERGE` avoids recreating already-matched patterns, but relies cleanly on `Stop.code` identity only when the dataset has no duplicate-code nodes. A production system should place a **uniqueness constraint** on the stop code after ensuring existing data has no duplicates:

```cypher
CREATE CONSTRAINT stop_code_unique IF NOT EXISTS
FOR (s:Stop)
REQUIRE s.code IS UNIQUE;
```

This constraint enforces identity consistency; choosing and evaluating indexes also speeds up locating source/target nodes. If running concurrently in a shared environment, inspect existing labels, relationships, and constraints first.

## 3. Cypher: Describing Patterns and Querying Paths

### 3.1. Finding Matching Paths Within a Hop Limit

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = (start)-[:TRIP*1..3]->(finish)
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       reduce(total = 0, r IN relationships(p) |
              total + r.minutes) AS totalMinutes
ORDER BY hops, route;
```

This is a **path-pattern query**: results include paths with 1 to 3 `:TRIP` relationships following the arrow direction. On the sample graph, there are two rows: A → B and A → C → B.

Key points to grasp:

- `*1..3` bounds **path length by relationship count**, not by travel time.
- `->` requires relationships in the stored direction; `-[:TRIP*1..3]-` allows traversing in either direction.
- A path matched by standard Cypher does not reuse the same relationship within that same path; however, **nodes can still appear multiple times**, so "no repeated nodes" is an additional constraint if business rules require it.
- Matching path counts can grow very rapidly as branching or depth increases. Bound path length and specify appropriate source, target, relationship type, and traversal direction constraints.

### 3.2. Finding the Fewest-Hop Path with Cypher

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = shortestPath((start)-[:TRIP*]->(finish))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       reduce(total = 0, r IN relationships(p) |
              total + r.minutes) AS totalMinutes;
```

Expected output from the sample data:

```text
route       hops    totalMinutes
['A','B']   1       90
```

`shortestPath()` chooses the **fewest relationships**. If multiple paths tie for fewest hops, it returns one of them; when you need all paths tying for minimum hops, consider `allShortestPaths()`.

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = allShortestPaths((start)-[:TRIP*]->(finish))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
```

Do not infer a guaranteed ordering among tied paths without an explicit sort criterion. Even all shortest paths can still be numerous; returning all of them can consume memory and time.

> **Version note:** `shortestPath()` and `allShortestPaths()` are familiar Cypher syntax in Neo4j 5. Newer Cypher versions/dialects add additional syntax for shortest-path patterns. When applying this, verify syntax against your running Neo4j version; **hop count** and **total weight** still remain distinct concepts.

### 3.3. Can Cypher Pick the Lowest Total Minutes?

On **very small graphs with bounded depth**, you can enumerate paths and sum minutes:

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = (start)-[:TRIP*1..3]->(finish)
WHERE all(r IN relationships(p) WHERE
          r.minutes IS NOT NULL AND r.minutes >= 0)
WITH p,
     reduce(total = 0, r IN relationships(p) |
            total + r.minutes) AS totalMinutes
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       totalMinutes
ORDER BY totalMinutes ASC, hops ASC
LIMIT 1;
```

The result is A → C → B at 20 minutes. However, this mechanism has a **scalability weakness**: to find the cheapest candidate, the query may have to generate and cost a huge number of paths. A trailing `LIMIT 1` does not guarantee the engine can skip generating earlier candidates. If the `*1..3` bound is shorter than the true optimal path's hop count, the query can even miss the best solution.

In short, Cypher *can compute the cost of a path*, but enumerating all paths and sorting is not the default choice for **shortest weighted path** problems on large graphs.

## 4. What Do Specialized Graph Algorithms Solve?

An algorithm takes **graph topology, source/target nodes, weight properties, and specific constraints**, and computes according to a defined objective. Examples:

| Need | Typical Approach | Desired Output |
| --- | --- | --- |
| Find connections within 1–3 hops with property filters | Cypher `MATCH` and path patterns | Matching paths/relationships |
| Fewest hops between two nodes | Cypher `shortestPath()`, or suitable BFS | Path with fewest relationships |
| Lowest non-negative total time or cost | **Dijkstra** in GDS | Minimum-total-weight path |
| Low-cost path with a valid positional heuristic | **A\*** in GDS | Optimal path under algorithm conditions, potentially narrowing search space |
| Multiple alternative routes ordered by cost | **Yen's k-shortest paths** in GDS | A set of shortest paths ordered by cost |
| Traverse from a source layer-by-layer / branch-by-branch | **BFS / DFS** | Node set or traversal path per rule |
| Disconnected clusters | **Weakly Connected Components (WCC)** | Component ID per node |
| Score node importance in a network | **PageRank** | Score per node |
| Detect communities in a network | **Louvain** or other community algorithms | Community label per node |

Algorithms such as PageRank, WCC, or Louvain **do not directly answer "which path?"**. They solve whole-network analytical problems for which a simple `MATCH` query lacks an equivalent optimization engine.

**Do not assume every path task requires GDS.** If the goal is checking "does this person have a `:KNOWS` connection to that person within at most 2 hops and in the same city?", Cypher is more natural because it expresses data predicates directly.

## 5. Dijkstra in Neo4j Graph Data Science

### 5.1. General Concept

Dijkstra finds a path from source to target with **minimum total weight** when eligible edge weights are **non-negative**. The algorithm does not merely choose fewer edges; it accumulates cost and expands along the lowest known total cost.

In the A/B/C example, Dijkstra prefers A → C → B because 10 + 10 = 20, which is less than 90. Choose weights matching your true objective: minutes, currency, distance, properly normalized risk, etc. If optimizing multiple criteria simultaneously, define a clear optimization rule or composite cost model.

Before using GDS, the Neo4j environment must have a GDS library version compatible with the server, and the user must hold privileges to invoke the required procedures. GDS typically operates on a **named graph projection** — an in-memory graph representation dedicated to algorithms.

### 5.2. Projecting the Graph into Memory

```cypher
CALL gds.graph.project(
  'stopTrips',
  'Stop',
  {
    TRIP: {
      type: 'TRIP',
      orientation: 'NATURAL',
      properties: 'minutes'
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
```

In this example:

- `'Stop'` selects matching nodes; `'TRIP'` selects the relationships to include.
- `orientation: 'NATURAL'` preserves relationship direction as stored in Neo4j.
- `minutes` is loaded into the projection as a weight property.
- `'stopTrips'` is the **name of the in-memory GDS graph**, not a Neo4j database name and not a new label.

The projection must include all nodes, relationships, and properties required for the task. If the network is one-way but projected as undirected, results may suggest routes forbidden by business rules. If `minutes` is missing or has an incompatible type, clean the data before running the algorithm.

### 5.3. Running Weighted Dijkstra

```cypher
MATCH (source:Stop {code: 'A'})
MATCH (target:Stop {code: 'B'})
CALL gds.shortestPath.dijkstra.stream('stopTrips', {
  sourceNode: source,
  targetNode: target,
  relationshipWeightProperty: 'minutes'
})
YIELD totalCost, nodeIds
RETURN [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route,
       totalCost AS totalMinutes;
```

Expected output:

```text
route           totalMinutes
['A','C','B']    20.0
```

Key points to note:

1. `sourceNode` and `targetNode` must exist in the `stopTrips` projection.
2. `relationshipWeightProperty` selects **the property used as cost**; if optimizing distance instead of time, you cannot keep `minutes`.
3. The returned path is chosen by **total weight**, not necessarily by relationship count.
4. If the underlying data is modified after creating the projection, have a strategy to **refresh or recreate the projection** before relying on new outputs.
5. When no path exists, handle the empty result cleanly rather than defaulting total cost to 0.

When finished with a test projection, release memory with:

```cypher
CALL gds.graph.drop('stopTrips')
YIELD graphName
RETURN graphName;
```

Drop only graphs you own or that no active analysis session still depends on; GDS named graphs can be shared within a managed scope.

### 5.4. Why Not Always Use Dijkstra?

GDS incurs a data-preparation step and memory footprint; Cypher queries the store directly and supports rich property-graph filter predicates. If an application only inspects relationships at depth 1–2, projecting the entire network may be unnecessary.

Conversely, running many weighted shortest-path, centrality, or community workloads on the same network can reuse a prepared projection. Weigh whether data changes continuously, query frequency, graph size, and latency requirements.

## 6. BFS, DFS, Shortest Path: Not Synonymous

**Breadth-First Search (BFS)** expands from the source node layer by layer in edge-count distance. When edges have equal cost, BFS is ideal for finding minimum-hop paths; it is also used to explore nodes reachable within a fixed depth.

**Depth-First Search (DFS)** follows one branch deeply before backtracking. DFS is useful for structural exploration, yet the first path DFS encounters is **not guaranteed to be minimum-hop or minimum-weight**.

**Dijkstra** handles non-negative weights; exploration order is driven by the lowest known cumulative cost.

**A\*** also finds minimum-weight paths but adds a **heuristic** estimating remaining cost from the current node to the target. To guarantee optimality, the heuristic must satisfy required conditions, such as never overestimating actual remaining cost. If travel time is the weight, straight-line geographic distance is not automatically a valid estimate in minutes; it must be converted under sound assumptions.

Examples of wrong choices:

- Using BFS to find the **fastest** trip in minutes when each leg has a different duration.
- Using DFS because "going deep reaches the target faster," then treating the first path found as optimal.
- Using Dijkstra with **negative** weights or missing cost values without defining handling rules.
- Using A\* with an unverified or unit-mismatched heuristic and claiming guaranteed optimality.

If a problem requires mandatory waypoints, transfer constraints, time windows, or time-dependent edge costs, verify whether your graph model and chosen algorithm actually represent those constraints.

## 7. Comparison by Mechanism, Cost, and Usage

| Aspect | Cypher Path Queries | Specialized Algorithms via GDS |
| --- | --- | --- |
| Input | `MATCH` patterns, `WHERE` predicates, property graph data | Graph projection and algorithm configuration |
| Objective | Pattern matching, filtering, joining, and presenting data | Optimal paths, reachability, scores, clusters, etc. |
| Weights | Computed via expressions; `shortestPath()` uses hops | Dijkstra/A\* optimize by weight property |
| Output | Rows, nodes, relationships, paths, aggregated values | Costs, node IDs, paths, scores, communities, etc., per algorithm |
| Performance | Strong with well-constrained patterns; deep enumeration can explode | Tuned for algorithmic problems; incurs projection creation/memory cost |
| Freshness | Reads current transaction/query state | Requires managing projection lifecycle and freshness |
| App integration | Used directly with Java Driver, Spring Data Neo4j | Call GDS procedures via Cypher/Driver; manage privileges and resources |
| Required skills | Graph modeling, path syntax, execution-plan reading | Algorithms, preconditions, projections, memory, metrics |

### Common Misconceptions

**"Cypher has no shortest-path capability."** False. Cypher supports minimum-hop shortest paths with dedicated syntax. The main differences are **objective definition** and **problem scale**.

**"Using GDS automatically gives more accurate results."** Not necessarily. If a projection has the wrong orientation, omits edges, uses the wrong weight, or reflects stale data, the algorithm will compute accurately on **the wrong input graph**.

**"`LIMIT 1` makes a query enumerating all paths cheap."** Not guaranteed. Generating and costing candidates can still be very expensive before `ORDER BY ... LIMIT 1` executes.

**"Shortest path is always the fastest route."** Only when path length and weight align with the objective. `length(p)` does not imply `minutes`, `price`, or risk level.

## 8. System Design with Java and Spring Data Neo4j

In a transit system exposing `GET /routes?from=A&to=B&objective=time`, the service layer can dispatch by `objective`:

```text
Route request
       |
       v
Validate source/target nodes, optimization goal, cost data
       |
       +-- Connections / fewest hops --------> Cypher path / shortestPath
       |
       +-- Total minutes / total cost -------> GDS Dijkstra/A* with valid weights
       |
       +-- Batch network analysis -----------> GDS WCC, PageRank, communities...
       |
       v
Verify results, data freshness, return route and optimization criterion
```

In a Java application:

- **Neo4j Java Driver** sends Cypher statements and parameters (station codes, source/target nodes, objectives), then reads results. It can invoke `gds.shortestPath.dijkstra.stream` as a Cypher procedure when GDS is installed.
- **Spring Data Neo4j** is convenient for managing node/relationship entities and domain queries; specialized GDS queries may require custom repository queries or direct Driver calls.
- **Never concatenate user input into query strings**, especially IDs and parameter names. In Cypher, pass source/target values as parameters, e.g., `$fromCode` and `$toCode`.
- **Return the route criterion explicitly:** `objective: "MIN_HOPS"` or `"MIN_MINUTES"`, along with `hops` and `totalMinutes` if available. Avoid a single ambiguous field named `shortest` without specifying units.

Example parameterized lookup for two endpoints, suited for Driver execution:

```cypher
MATCH (source:Stop {code: $fromCode})
MATCH (target:Stop {code: $toCode})
MATCH p = shortestPath((source)-[:TRIP*]->(target))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
```

In large systems, separate **online transactional queries** from **heavy analytical workloads**. Some algorithms consume substantial CPU/RAM; running them uncontrolled inside request-handling paths can cause high latency or starve other workloads.

## 9. Responsible Optimization and Operations

### For Cypher Queries

1. **Anchor source/target tightly.** Use properties backed by uniqueness constraints or indexes so traversal does not expand from every node.
2. **Bound path patterns when domain rules allow.** `*1..4` is safer in search scope than unbounded traversal, provided the domain truly caps routes at 4 legs.
3. **Preserve correct direction and relationship types.** Accidentally switching to undirected traversal can produce invalid routes.
4. **Use `EXPLAIN` / `PROFILE` to inspect plans and row counts.** Optimization should rely on actual data shape, not query string length.
5. **Watch out for missing costs in totals.** Adding `null` inside `reduce` can turn totals non-numeric; filter missing values or enforce clear data rules.

### For GDS Algorithms

1. **Validate input preconditions.** Weight properties must be numeric and satisfy algorithm constraints (Dijkstra: non-negative).
2. **Keep projections minimal and sufficient.** Node labels, relationship types, orientation, and cost properties all affect both accuracy and memory.
3. **Monitor resources and runtime.** Large-graph analytics require tracking memory headroom and resource contention.
4. **Manage freshness.** A graph projection should never be assumed to stay automatically synchronized with store writes.
5. **Manage graph lifecycle.** Reuse projections when sensible; drop test projections, and avoid dropping projections still used by other jobs.
6. **Verify against small test cases with known answers.** The A/B/C example at the start of this lesson immediately catches accidentally optimizing hops instead of minutes.

## 10. Practice Exercises

**Exercise 1 — Two Different Objectives.** Given A → B (90 min), A → C (10 min), C → B (10 min), write a Cypher query for the fewest-hop route and a GDS Dijkstra query for the fewest-minutes route. Explain why the answers differ.

**Exercise 2 — Constrained Optimal Path.** Require traversing only `:TRIP` relationships with `active = true`. Why can a GDS projection containing inactive trips yield incorrect results? Propose how to filter data properly before running the algorithm.

**Exercise 3 — Data Freshness.** The duration of A → B is updated from 90 down to 5 minutes. Cypher queries read the updated value, but GDS still uses the old projection. What should the application do before publishing a "fastest route" result?

**Exercise 4 — Path Explosion.** A social network has millions of nodes; a request asks to list every path of up to 10 relationships between two users. State the risks and how to narrow the problem before writing Cypher.

**Exercise 5 — Not a Path Problem.** An analytics team wants to find connected components and influential users in a network. Recommend an algorithm for each goal and explain why `shortestPath()` alone does not solve them.

### Key Takeaways

- **Cypher `MATCH`:** suited for describing relationship structures and returning matching paths.
- **Cypher `shortestPath()`:** selects the shortest path by **relationship count** within a pattern.
- **GDS Dijkstra/A\*:** serves **weighted** path problems under specific algorithmic preconditions.
- **BFS/DFS:** differ in traversal order and strategy; DFS does not inherently return an optimal path.
- **GDS WCC/PageRank/community detection:** serve **whole-network** analytics rather than finding a single path.
- **Reliable results:** depend on edge-direction modeling, weight data quality, business bounds, projection freshness, and proper performance measurement.

Choosing between Cypher and a graph algorithm is not a contest over which tool is "stronger." Define precisely **the question being asked**, which data acts as weights, the network scope, and freshness requirements—then choose the mechanism that fits.
