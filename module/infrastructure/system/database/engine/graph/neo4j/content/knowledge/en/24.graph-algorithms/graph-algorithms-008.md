# Weighted Path Algorithms and Distance Problems

## 1. The Shortest Path Is Not Always the Fewest Edges

In **Neo4j**, a *path* is a sequence of nodes connected by relationships. A relationship can carry numeric properties such as **km**, **minutes**, **cost**, or **riskScore**. When an application needs to find a delivery route, the fastest processing path, the lowest-risk dependency chain, or the lowest transaction fee, simply counting relationships (*hops*) usually fails to answer the right question.

This lesson belongs to the **Graph Algorithms** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The goal is to understand **weighted distance problems**, choose suitable algorithms, run them on a **property graph** using **Neo4j Graph Data Science (GDS)**, and evaluate limitations regarding data, memory, relationship direction, and correctness.

Distinguish these cases:

| Question | Quantity Optimized | Approach |
|---|---|---|
| From A to D via the fewest relationships? | **Hop count** | Cypher **shortestPath()** or **SHORTEST** |
| Route A → D with the lowest total distance? | **Sum of km** across relationships | GDS **Dijkstra** with property **km** |
| Route A → D taking the least time? | **Sum of minutes** across relationships | GDS **Dijkstra** with property **minutes** |
| What near-optimal alternative routes exist? | **k paths** by total weight | GDS **Yen** |
| Distances from A to all reachable nodes? | Minimum total weight from **one source** | GDS **Dijkstra Single-Source** or **Delta-Stepping** |
| Graph has negative edge weights? | Total weight; possible negative cycles | **Bellman–Ford**; must analyze negative cycles |

**Important:** Cypher **shortestPath()**, **allShortestPaths()**, and the **SHORTEST** path selector pick paths by **relationship count**. They **do not automatically optimize the sum of km/minutes/cost**. Even in Cypher 25, *weighted shortest path* problems typically use algorithms in GDS.

## 2. Mathematical Model of Weighted Paths

Consider a directed graph \(G=(V,E)\), where each relationship \(e\) carries a weight \(w(e)\). If a path from A to D is \(p=(e_1,e_2,\dots,e_k)\), the path cost is computed as:

\[
C(p)=\sum_{i=1}^{k} w(e_i)
\]

The optimal path between two nodes \(s,t\) is:

\[
p^*=\underset{p:s\leadsto t}{\operatorname{arg\,min}}\;C(p)
\]

**Model assumptions:** a path's cost equals the sum of individual edge costs, and each edge weight satisfies the algorithm's requirements. For Dijkstra in GDS, use **non-negative weights**—practically, finite positive numbers for routing examples. If cost depends on departure time, waiting time, consumed capacity, or state along the route, a simple sum no longer captures the problem; specialized models or solvers are then required.

A graph can define distance in several ways:

- **Hop distance:** every edge counts as 1, measuring step count.
- **Weighted distance:** every edge carries a weight in km, minutes, currency, or another explicit unit.
- **Reachability:** asks only whether a path exists, not yet a cost-optimization problem.

All weights in a single run must share the **same unit and meaning**. Never add currency to kilometers and call the result "distance" without defining a composite cost function.

## 3. Building a Practice Graph: Same Endpoints, Three Optimal Answers

To avoid colliding with operational data, use the **DemoWeightedPlace** label and **DEMO_WEIGHTED_ROUTE** relationship type. Run the setup statements **once on a test database**:

~~~cypher
CREATE CONSTRAINT demo_weighted_place_code IF NOT EXISTS
FOR (n:DemoWeightedPlace)
REQUIRE n.code IS UNIQUE;
~~~

~~~cypher
CREATE
  (a:DemoWeightedPlace {code: 'A'}),
  (b:DemoWeightedPlace {code: 'B'}),
  (c:DemoWeightedPlace {code: 'C'}),
  (d:DemoWeightedPlace {code: 'D'}),
  (e:DemoWeightedPlace {code: 'E'}),
  (f:DemoWeightedPlace {code: 'F'}),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 20.0, minutes: 25.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 7.0,  minutes: 4.0}]->(b),
  (b)-[:DEMO_WEIGHTED_ROUTE {km: 5.0,  minutes: 5.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 4.0,  minutes: 6.0}]->(c),
  (c)-[:DEMO_WEIGHTED_ROUTE {km: 4.0,  minutes: 7.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(e),
  (e)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(f),
  (f)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(d);
~~~

Directed edge diagram; edge labels show **km / minutes**:

~~~mermaid
flowchart LR
  A((A)) -->|"20 / 25"| D((D))
  A -->|"7 / 4"| B((B))
  B -->|"5 / 5"| D
  A -->|"4 / 6"| C((C))
  C -->|"4 / 7"| D
  A -->|"1 / 4"| E((E))
  E -->|"1 / 4"| F((F))
  F -->|"1 / 4"| D
~~~

From A to D there are four routes:

| Path | Hops | Total km | Total minutes |
|---|---:|---:|---:|
| A → D | **1** | 20 | 25 |
| A → B → D | 2 | 12 | **9** |
| A → C → D | 2 | 8 | 13 |
| A → E → F → D | 3 | **3** | 12 |

Thus:

1. **Fewest hops:** A → D, one relationship.
2. **Shortest distance (km):** A → E → F → D, **3 km**, despite traversing three relationships.
3. **Shortest time (minutes):** A → B → D, **9 minutes**, despite being 12 km long.

These numbers are purely illustrative and do not represent a real road map. They demonstrate that "shortest path" is ambiguous until the **cost function** is specified.

## 4. Using Pure Cypher to Verify Results on a Small Graph

To see how path cost is summed, you can enumerate modest-length paths and apply **reduce()**:

~~~cypher
MATCH (s:DemoWeightedPlace {code: 'A'}),
      (t:DemoWeightedPlace {code: 'D'})
MATCH p = (s)-[:DEMO_WEIGHTED_ROUTE*1..4]->(t)
WITH p,
     reduce(total = 0.0, r IN relationships(p) |
            total + r.km) AS totalKm,
     reduce(total = 0.0, r IN relationships(p) |
            total + r.minutes) AS totalMinutes
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       totalKm,
       totalMinutes
ORDER BY totalKm, hops;
~~~

Results ordered by km are **3**, **8**, **12**, and **20**, matching the table in Section 3. You can replace **ORDER BY totalKm** with **ORDER BY totalMinutes** to verify the time objective.

**Never use this pattern as a default on large graphs:** the query must find all candidate paths within **1..4 hops** before summing and sorting. Increasing depth or branching factor causes path counts to explode. Adding **LIMIT 1** after **ORDER BY totalKm** does not turn enumeration into Dijkstra; in the worst case, the engine still evaluates many paths before picking the cheapest one.

Likewise, do not write:

~~~cypher
MATCH p = shortestPath(
  (:DemoWeightedPlace {code: 'A'})
  -[:DEMO_WEIGHTED_ROUTE*1..4]->
  (:DemoWeightedPlace {code: 'D'})
)
RETURN reduce(cost = 0.0, r IN relationships(p) |
              cost + r.km) AS km;
~~~

expecting the minimum-km route. **shortestPath()** picks the fewest-hop path first, so in this graph it picks **A → D** and returns **20 km**, not **3 km**.

## 5. Preparing Neo4j Graph Data Science

From this section onward, examples use **GDS**, an algorithm library that **must be installed and explicitly permitted**, not core Cypher commands. Your GDS version must be compatible with your Neo4j version. GDS may be available via a supported managed service or as a plugin on a self-managed server; installation steps and permissions vary by environment.

Log in with an account allowed to inspect procedures and verify GDS is available:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'gds.'
RETURN name
ORDER BY name
LIMIT 20;
~~~

If **gds.graph.project** and **gds.shortestPath.dijkstra.stream** are missing, check installation, version compatibility, procedure configuration, and access privileges. **Do not** interpret an *Unknown procedure* error as "Neo4j does not support weighted shortest paths."

### 5.1. What Is a Graph Projection?

GDS computes over an in-memory **named graph** **projected** from the database, rather than running directly on every database relationship for every algorithm call. A projection defines:

- **Node set:** which node labels belong to the problem.
- **Relationship set:** which relationship types are traversed.
- **Orientation:** **NATURAL** following stored direction, **REVERSE** if flipped, or **UNDIRECTED** if traversal is allowed both ways.
- **Weights:** which numeric relationship properties to load into the computational graph, such as **km** and **minutes**.

Create a projection from the sample graph:

~~~cypher
CALL gds.graph.project(
  'demoWeightedRoutes',
  'DemoWeightedPlace',
  {
    DEMO_WEIGHTED_ROUTE: {
      orientation: 'NATURAL',
      properties: ['km', 'minutes']
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Expected output on clean sample data: **6 nodes, 8 relationships**. If a projection named **demoWeightedRoutes** already exists, re-creating it with the same name fails; reuse the existing projection or intentionally **drop** and recreate it following Section 11.

**Why NATURAL?** All edges in the example are stored from A toward D. Switching to **UNDIRECTED** lets the algorithm traverse backward, potentially producing operationally invalid paths. Similarly, projecting one relationship type while omitting another critical type means the optimal path in the projection may not be optimal over the real dataset.

### 5.2. Weight Data Must Be Validated Before Projection

Run a check to detect missing weights, invalid numeric values, or violated business constraints:

~~~cypher
MATCH (:DemoWeightedPlace)-[r:DEMO_WEIGHTED_ROUTE]->
      (:DemoWeightedPlace)
WHERE r.km IS NULL OR r.minutes IS NULL
   OR r.km <= 0 OR r.minutes <= 0
RETURN count(r) AS invalidRoutes;
~~~

On the example dataset, the result is **0**. On production databases, also check **numeric types**, infinite/`NaN` values if upstream sources produce them, unit consistency, and anomalous outliers. Missing numeric properties in a projection can default to values like **NaN**; never assume the algorithm will repair dirty data.

If the business problem excludes **inactive** edges, restricted corridors, or specific time windows, **filter before projecting** or select the exact meaningful *subgraph*. Filtering paths **after** the algorithm picks a single cheapest route can discard the only valid solution: the second-cheapest valid route may be better than anything left uncomputed.

## 6. Dijkstra Source–Target: Minimum Total km Path

**Dijkstra** maintains the best known distance from the source node to other nodes. Given **non-negative** weights, whenever the node with the smallest distance is popped from the priority queue, its optimal distance can be finalized. In GDS, the **Source–Target** variant finds paths from one source to one or more targets.

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [target],
    relationshipWeightProperty: 'km'
  }
)
YIELD totalCost, nodeIds, costs
RETURN totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route,
       costs AS cumulativeKm;
~~~

Expected output:

~~~text
totalKm: 3.0
route: ["A", "E", "F", "D"]
cumulativeKm: [0.0, 1.0, 2.0, 3.0]
~~~

Parameter and output breakdown:

| Parameter / Output | Meaning |
|---|---|
| **sourceNode** | Starting node looked up from the database |
| **targetNodes** | Single target node or list of target nodes; `[target]` in this example |
| **relationshipWeightProperty** | Projected relationship property name, here **km** |
| **totalCost** | Minimum total weight; units are km because property `km` is used |
| **nodeIds** | IDs of nodes along the path in traversal order |
| **costs** | Cumulative total weight upon reaching each node along the path |

**API version note:** in current GDS documentation, **targetNodes** is recommended for Dijkstra Source–Target; the singular **targetNode** form for this algorithm has been deprecated. **nodeIds** are not business keys, so the example maps each node ID back to **code** for display.

**Stream** is a read-only mode and **does not write new paths** back to the database. **write** or **mutate** modes have different data side effects and are used only when workflows genuinely require persisting results.

### 6.1. Switching the Cost Function: Fewest Minutes

No relationship edits are needed; simply switch the weight property to optimize:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [target],
    relationshipWeightProperty: 'minutes'
  }
)
YIELD totalCost, nodeIds
RETURN totalCost AS totalMinutes,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route;
~~~

Expected output is **9 minutes** along **A → B → D**. Although **A → E → F → D** is only **3 km**, it takes **12 minutes**. That is why routing APIs must explicitly specify whether they optimize for distance or travel time.

### 6.2. One Source and Multiple Targets

When routing from A to both D and F, pass both in **targetNodes** rather than mechanically running separate queries per target:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (d:DemoWeightedPlace {code: 'D'}),
      (f:DemoWeightedPlace {code: 'F'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [d, f],
    relationshipWeightProperty: 'km'
  }
)
YIELD targetNode, totalCost, nodeIds
RETURN gds.util.asNode(targetNode).code AS target,
       totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY target;
~~~

In the sample graph, **A → F** costs **2 km** via E, while **A → D** costs **3 km** via E and F.

## 7. Dijkstra Single–Source: Distances from One Point to All Others

When asked for "distances from warehouse A to **every reachable location**" rather than just D, use the **Single–Source** variant. Current GDS names the procedure:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'})
CALL gds.allShortestPaths.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    relationshipWeightProperty: 'km'
  }
)
YIELD targetNode, totalCost, nodeIds
RETURN gds.util.asNode(targetNode).code AS destination,
       totalCost AS distanceKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY distanceKm, destination;
~~~

Here **allShortestPaths.dijkstra** in GDS means shortest paths from **one source to all reachable targets**—it does **not** mean returning all tied equal-cost paths for a single source–target pair.

In the sample graph, minimum distances from A to each destination are:

| Destination | Minimum Total km | One Optimal Path |
|---|---:|---|
| B | 7 | A → B |
| C | 4 | A → C |
| D | 3 | A → E → F → D |
| E | 1 | A → E |
| F | 2 | A → E → F |

Depending on the API, output may also include source node A with distance **0**. For nodes unreachable from A along projected edge directions, never infer "distance is 0": they have no valid path.

**When to choose Single–Source?** Computing a distance map from a distribution hub, evaluating service coverage, building cost-bounded reach zones, or identifying nodes exceeding thresholds. If you only need **a single A–D pair**, Source–Target is usually better suited.

### 7.1. Delta-Stepping When Parallel Execution Is Needed

**Delta-Stepping Single–Source** is a variant that processes distance buckets in parallel, helpful on certain large graphs. In GDS, the corresponding procedure is **gds.allShortestPaths.delta.stream**. It takes a **delta** parameter affecting bucket granularity and execution efficiency; benchmark on real data. GDS Single–Source Dijkstra uses a sequential implementation, so increasing **concurrency** on it does not make it parallel.

Choose Delta-Stepping when real workloads show a need for large-scale Single–Source speed, rather than assuming it outperforms Dijkstra in every scenario.

## 8. Yen: Retrieving k Alternative Routes by Total Weight

Delivery or network-failover applications often need **multiple routes**, allowing fallback to the second-best route if the primary one is unavailable. **Yen's k-shortest paths** finds up to **k** paths ordered by **total weight** without repeating previously found paths. Unlike **SHORTEST k** in Cypher, results here are ranked by **weighted cost**, not hop count.

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.yens.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNode: target,
    k: 3,
    relationshipWeightProperty: 'km'
  }
)
YIELD index, totalCost, nodeIds
RETURN index,
       totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY index;
~~~

The three routes returned on the example graph:

| Index | Path | Total km |
|---|---|---:|
| 0 | A → E → F → D | 3 |
| 1 | A → C → D | 8 |
| 2 | A → B → D | 12 |

The direct route A → D costs **20 km** and would be the fourth option. If the graph contains fewer than **k** valid paths, the algorithm cannot invent nonexistent paths. For equal-cost ties, do not assume a fixed tie-breaking order unless guaranteed by the API.

**Limitations:** larger `k` increases overall compute cost. Never set `k = 1000` just because a UI displays three suggestions. If you require truly disjoint alternatives across roads, waypoints, or regions, merely taking the **k** cheapest paths may fall short: paths can still overlap on many shared segments.

## 9. Choosing the Right Algorithm for Your Data Constraints

| Algorithm | Problem | Key Requirement | Trade-offs to Consider |
|---|---|---|---|
| **BFS / Cypher SHORTEST** | Fewest **hops** | Every edge treated as cost 1 | Does not optimize distinct km/minute weights |
| **Dijkstra Source–Target** | One source → one or more targets | Non-negative weights, additive cost model | Ideal for well-defined target lookups |
| **Dijkstra Single–Source** | One source → all reachable targets | Non-negative weights | Wastes work if only one target is needed |
| **Delta-Stepping** | One source → all targets, parallelized | Non-negative weights, requires tuning `delta` | Benchmark on target graph and hardware |
| **A\*** | One source → one target with goal-directed heuristic | Heuristic must match weight unit and never overestimate true cost if optimality is required | Can prune search space with good coordinates; not always faster |
| **Yen** | k alternative paths by total weight | Valid positive weights, moderate `k` | Costlier as `k` grows; returned paths may overlap |
| **Bellman–Ford** | Single–Source with negative weights | No reachable negative cycles if finite distances are desired | Slower in many cases; requires negative-cycle handling |

### 9.1. A*: Using Heuristics to Guide Search

**A\*** evaluates nodes using accumulated cost **g(n)** plus an estimated remaining cost **h(n)**. When **h(n)** is a valid lower bound on true cost from `n` to the target (*admissible heuristic*), A\* preserves optimality under the corresponding conditions.

GDS A\* supports node **latitude** and **longitude** properties for coordinates. In practice, you must **project both coordinate properties** alongside relationship weights, and keep cost units consistent with the heuristic. With **km** weights, great-circle distance serves as an admissible lower bound when real route segments cannot be shorter than straight-line geographic distance. With **minutes** weights, never add **km** directly to **minutes**.

The following example is a **reference template only**, requiring real coordinates and a matching projection to execute:

~~~cypher
MATCH (s:GeoPlace {code: $from}),
      (t:GeoPlace {code: $to})
CALL gds.shortestPath.astar.stream(
  'geoRoutesWithCoordinates',
  {
    sourceNode: s,
    targetNode: t,
    latitudeProperty: 'latitude',
    longitudeProperty: 'longitude',
    relationshipWeightProperty: 'km'
  }
)
YIELD totalCost, nodeIds
RETURN totalCost AS totalKm, nodeIds;
~~~

**Do not run this snippet on `demoWeightedRoutes`:** the sample graph lacks latitude/longitude properties. Rather than fabricating fake coordinates to make results look good, use real data and confirm the heuristic aligns with the cost function.

### 9.2. Bellman–Ford: Negative Edge Weights and Negative Cycles

Dijkstra is invalid for graphs with negative edge weights. **Bellman–Ford** computes single-source shortest paths with negative edges provided **no reachable negative cycle** reduces path cost indefinitely. For instance, a negative "rebate cost" relationship could let repeated loops drive total cost arbitrarily low, leaving "finite optimal path" undefined under models permitting cycles.

In GDS, **Bellman–Ford Single–Source** is documented with negative-cycle detection. Use it when negative weights genuinely exist; never feed negative weights into a Dijkstra projection and trust the output.

## 10. Factors That Produce Wrong Results Even When the Algorithm Succeeds

### 10.1. Orientation and Relationship Types

In a GDS projection, **NATURAL** respects stored direction. If edge A → B exists without B → A, a reverse path may not exist. **UNDIRECTED** allows bidirectional traversal and can turn a one-way traffic network into a false two-way network.

Likewise, project only appropriate relationship types: **ROAD**, **RAIL**, **AIR**, and **DEPENDS_ON** carry distinct meanings. Mixing them without a unified cost model yields operationally invalid routes.

### 10.2. Missing Edges, Dirty Weights, and Special Values

Before running, verify:

- The weight property exists on every included edge.
- Values are **finite** numbers—not strings, `null`, or `NaN`.
- No negative edges exist when using Dijkstra/A\*/Yen under their respective assumptions.
- Whether `0` is valid in the domain; in our lesson's example, every edge has positive cost.
- Consistent units: **minutes with minutes**, **km with km**.
- Rules for parallel A → B relationships: are they distinct route options or duplicate data to deduplicate?

GDS projections can substitute default values for missing properties; merely completing the projection step **does not prove weight data is clean**.

### 10.3. Projections Are Snapshots, Not Auto-Synced per Transaction

A GDS named graph resides in the **in-memory graph catalog** and **does not auto-update** whenever Cypher transactions modify **km** or add relationships in the database. If tariffs change or a route closes after projection, results from the stale projection will be **stale**.

Routing workflows over changing data need an explicit refresh policy:

1. At what cadence or trigger is the projection created or refreshed?
2. How much staleness relative to live traffic updates is acceptable?
3. How are new projections built, swapped via versioned names, and old projections dropped cleanly?
4. Must selected routes be re-validated before executing critical business actions?

Never assume `SET r.km = ...` immediately changes outputs from `gds.shortestPath.dijkstra.stream` on an existing named graph.

### 10.4. Constraints Beyond Total Weight

Some requirements demand "shortest km path **avoiding restricted zones**, at most three transfers, under 30 minutes, with no repeated nodes." Such constraints **are not automatically enforced** merely by setting `relationshipWeightProperty: 'km'`.

You must pre-filter data into the projection, model state explicitly, add path validation steps, or select constraint-aware algorithms. **Filtering after finding a single optimal path** can lose valid answers: the second-best valid path might beat everything else yet never be computed.

### 10.5. Multi-Criteria Optimization

Minimizing **km** and minimizing **minutes** simultaneously often has no single universally best answer. For example, A → E → F → D minimizes km, whereas A → B → D minimizes minutes. One simple approach defines:

\[
\operatorname{score}(p)
= \alpha \cdot \operatorname{km}(p)
+ \beta \cdot \operatorname{minutes}(p)
\]

Where \(\alpha,\beta\) use consistent conversion units reflecting business trade-offs. **This is a new objective function**, no longer "shortest by km" or "fastest by minutes." If multiple Pareto-optimal alternatives are needed, design the system to return non-dominated paths rather than collapsing everything into one weighted sum.

## 11. Performance, Permissions, and Projection Lifecycle

### 11.1. Resource Estimation

Projections require **RAM** for nodes, relationships, and loaded properties. Optimize by projecting only the labels, relationship types, and properties actually needed, instead of projecting the whole graph for a routing-only task.

Before heavy runs, use GDS **estimate** modes where supported; monitor projection size, build time, **`computeMillis`**, memory usage, and p95 request latency. Never judge production performance from a 6-node test graph.

**Dijkstra Source–Target** in GDS uses a priority queue executing on **a single thread per algorithm run**; increasing **concurrency** does not directly parallelize the core computation of that variant. When multiple targets are needed, prefer configuring **targetNodes** appropriately or evaluate Single–Source.

### 11.2. Never Confuse Stream, Mutate, and Write

| Mode | Effect | When to Use |
|---|---|---|
| **stream** | Returns results to read or process further; writes no new edges | On-demand route computation |
| **mutate** | Writes results into the **in-memory named graph** | Multi-step GDS algorithm pipelines |
| **write** | Writes result relationships/properties to the **database** | When results genuinely must be persisted and lifecycle-managed |

Never use **write** merely to display a route. Writing results creates synthetic relationships/properties, consumes storage, and can get confused with source route data unless clearly named and governed.

### 11.3. Inspecting and Dropping Practice Projections

~~~cypher
CALL gds.graph.list('demoWeightedRoutes')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

After completing the exercises, if no other session uses this projection:

~~~cypher
CALL gds.graph.drop('demoWeightedRoutes')
YIELD graphName
RETURN graphName;
~~~

**`gds.graph.drop`** removes the **in-memory projection**, **without deleting** the six source nodes or eight relationships in the database. Keeping unused projections indefinitely increases memory cost; drop projections once they are no longer needed.

In **Java Driver / Spring Data Neo4j** applications, parameterize **$from** and **$to** when matching source/target nodes; allow users to pick projection names or weight properties only from an **allowlisted set**. Never let users pass arbitrary graph names that could expose unauthorized data slices. The account executing GDS needs procedure execute privileges and appropriate read permissions depending on Neo4j configuration/edition.

## 12. Common Errors and Troubleshooting

| Error / Symptom | Cause | What to Check |
|---|---|---|
| Dijkstra picks A → D even though A → E → F → D is 3 km | Used hop-based Cypher `shortestPath()` instead of weighted optimization | Use GDS Dijkstra with **`relationshipWeightProperty: 'km'`** |
| Minute-based results match km-based results despite different weights | Forgot to switch the weight property on execution | Verify **`relationshipWeightProperty`** |
| **Unknown procedure gds...** | GDS missing, incompatible, or insufficient permissions/config | Check installation, `SHOW PROCEDURES`, and version |
| **Graph already exists** | Named graph was projected earlier | Inspect catalog; drop/recreate only when authorized |
| Path exists in DB yet GDS finds none | Wrong orientation, label, type, or stale projection | Check catalog definition and source data |
| Abnormal costs | Mismatched units, missing properties, negative/`NaN` weights, non-numeric types | Validate and normalize data before projection |
| Results stay stale after editing relationships | Projection was not refreshed | Rebuild projection per refresh workflow |
| **Out of memory** during projection | Large graph, excessive properties, or insufficient RAM | Narrow dataset, run memory estimation, size properly |
| Query returns too many paths | Yen with huge `k` or Single–Source used unnecessarily | Pick the right algorithm and bound result count |
| Returned route traverses a forbidden edge | Projection included invalid edges | Filter edges inside the projection or model constraints |

## 13. Applied Exercises

### Exercise 1 — Three Meanings of "Shortest"

On the graph from Section 3, predict the optimal path and corresponding cost for three objectives: **fewest hops**, **fewest km**, and **fewest minutes**. Prove your answer using the path table and explain why a single **shortestPath()** call cannot solve all three.

### Exercise 2 — Running Dijkstra Yourself

Create a projection containing both **km** and **minutes**, run Dijkstra from A to D under each weight, and compare **totalCost**, **nodeIds**, and **costs** against the table. Switch orientation to **UNDIRECTED** in a separate projection and explain how the set of valid routes changes.

### Exercise 3 — Single–Source and Unreachable Cases

Compute minimum distances from A to B, C, D, E, and F. Next, run from D to A on the **NATURAL** projection and explain why a return path cannot be assumed to exist. Never treat an unreachable target as distance `0`.

### Exercise 4 — Fallback Routes

Run **Yen with k = 3** on **km**. Write down the three returned paths and compare them against "the three fewest-hop paths." Discuss why the three chosen paths could still overlap heavily on shared edges in another graph.

### Exercise 5 — Stale Projection

After projecting, update **km** on edge A → D from **20** to **0.5** in the **test database**, then re-run GDS on the old projection. Predict the result; afterward, refresh the projection and inspect the new path. Restore the sample data if continuing with other exercises.

### Exercise 6 — Choosing the Algorithm

For each scenario, pick the right approach and state your assumptions:

1. A delivery network with positive km weights, one warehouse to one customer.
2. One hub to millions of destinations, wanting to leverage parallel processing.
3. A map with accurate coordinates needing an optimal route in units compatible with a heuristic.
4. Needing five alternative paths ordered by total cost.
5. Negative edge weights exist and reachable negative cycles from the source must be detected.

## 14. Key Takeaways

**Graph distance must be defined by a cost function before choosing an algorithm.** Cypher **SHORTEST** optimizes hop count; with weights on relationships, use **GDS Dijkstra** for single routes or single-source distances, **Yen** for alternative routes, **A\*** when a valid heuristic exists, and **Bellman–Ford** when negative edges must be handled. Results are valid only over the **projected graph**, under the selected direction, relationship types, weights, and data snapshot timestamp.

Production workflow: **define cost units → validate data → build semantically accurate projection → pick goal-aligned algorithm → verify on small sample → measure resources and projection freshness**. Every step requires verification; an algorithm finishing without errors does not by itself prove the returned route is operationally optimal.

### Official Documentation

- [Neo4j Cypher Manual – Shortest paths and GDS comparison](https://neo4j.com/docs/cypher-manual/25/patterns/shortest-paths/)
- [Neo4j GDS – Dijkstra Source-Target Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [Neo4j GDS – Dijkstra Single-Source Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-single-source/)
- [Neo4j GDS – Yen’s Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/yens/)
- [Neo4j GDS – A* Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/astar/)
- [Neo4j GDS – Delta-Stepping Single-Source](https://neo4j.com/docs/graph-data-science/current/algorithms/delta-single-source/)
- [Neo4j GDS – Bellman-Ford Single-Source](https://neo4j.com/docs/graph-data-science/current/algorithms/bellman-ford-single-source/)
- [Neo4j GDS – Native graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
