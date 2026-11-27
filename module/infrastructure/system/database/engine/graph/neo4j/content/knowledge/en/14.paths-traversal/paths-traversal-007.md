# Finding Shortest Paths and Choosing Version-Appropriate Syntax

In **Neo4j**, the *property graph* model represents entities as **nodes**, links as **relationships**, and attributes as key–value pairs. When querying a transit network, dependency system, social network, or workflow, a common question is: **how do you get from node A to node D using the fewest links?** Cypher provides both legacy shortest-path functions and newer **path selectors**. Choosing the right syntax depends on your Neo4j/Cypher version and what "shortest" means in your problem.

## 1. Identify the Exact Problem Before Querying

| Need | Meaning | Appropriate Tool |
|---|---|---|
| Is there a path connecting A and D? | Reachability check only | Bounded-depth path pattern, or **ANY** selector in supported versions |
| One path with the fewest edges | Minimize **hop** (relationship) count | **shortestPath()** or **SHORTEST 1** / **ANY SHORTEST** |
| All tied paths with the fewest edges | Return every path sharing the minimum hop count | **allShortestPaths()** or **ALL SHORTEST** |
| A number of shortest paths or shortest length groups | Retrieve multiple options ordered by hop count | **SHORTEST k**, **SHORTEST k GROUPS** |
| Path with lowest total km, time, or cost | Minimize **total weight** across edges | Weighted algorithm, e.g., **Dijkstra** in Graph Data Science (GDS) |

**Key point:** Cypher **shortestPath()/SHORTEST** optimizes **edge count** by default; it does not sum edge distance or cost properties. A three-hop path can be shorter in km than a two-hop path.

Edge direction is also part of the condition: `(a)-[:CONNECTS]->(b)` follows the relationship direction; `(a)-[:CONNECTS]-(b)` allows traversing in either direction.

## 2. Building a Self-Contained Sample Graph

Run the following block **once on a test database**; the example uses the `DemoStop` label and `CONNECTS` relationship type to avoid colliding with other business data:

~~~cypher
CREATE
  (a:DemoStop {code: 'A'}),
  (b:DemoStop {code: 'B'}),
  (c:DemoStop {code: 'C'}),
  (d:DemoStop {code: 'D'}),
  (e:DemoStop {code: 'E'}),
  (f:DemoStop {code: 'F'})
CREATE
  (a)-[:CONNECTS {km: 4.0, active: true}]->(b),
  (b)-[:CONNECTS {km: 4.0, active: true}]->(d),
  (a)-[:CONNECTS {km: 10.0, active: false}]->(c),
  (c)-[:CONNECTS {km: 10.0, active: true}]->(d),
  (a)-[:CONNECTS {km: 1.0, active: true}]->(e),
  (e)-[:CONNECTS {km: 1.0, active: true}]->(f),
  (f)-[:CONNECTS {km: 1.0, active: true}]->(d);
~~~

There are three directed paths from A to D:

| Path | Hops | Total km | Status |
|---|---:|---:|---|
| A → B → D | 2 | 8 | All edges active |
| A → C → D | 2 | 20 | A → C is inactive |
| A → E → F → D | 3 | 3 | All edges active |

Therefore, **without filtering on active**, the fewest-hop route has **two tied answers**: A → B → D and A → C → D. When considering **total km**, route A → E → F → D is optimal instead. These outcomes will be referenced throughout this lesson.

## 3. Syntax Compatible with Neo4j 4.x and Early 5.x Versions

In versions prior to path selectors, Cypher uses two functions:

- **shortestPath(pattern)**: picks one path with the fewest hops between an endpoint pair; when multiple paths tie, the chosen path is **not guaranteed to be deterministic**.
- **allShortestPaths(pattern)**: returns all paths sharing the minimum hop count.

### 3.1. Retrieving One Shortest Path

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = shortestPath((s)-[:CONNECTS*1..6]->(t))
RETURN
  [n IN nodes(p) | n.code] AS stops,
  length(p) AS hops;
~~~

Syntax breakdown:

1. **s** and **t** are matched by label and property to anchor the start and end points.
2. **[:CONNECTS*1..6]** is the legacy variable-length relationship syntax, from **1 to 6** edges along the arrow direction.
3. **shortestPath(...)** picks one path with the fewest hops within that range.
4. **nodes(p)** is the list of nodes along the path; **length(p)** returns the number of relationships, **not total km**.

The result can be A → B → D **or** A → C → D, both having **2 hops**. Do not write tests assuming the function always picks B.

### 3.2. Retrieving All Tied Shortest Paths

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = allShortestPaths((s)-[:CONNECTS*1..6]->(t))
RETURN
  [n IN nodes(p) | n.code] AS stops,
  length(p) AS hops
ORDER BY stops;
~~~

Result: **[A, B, D]** and **[A, C, D]**, each 2 hops. The **ORDER BY** clause only sorts output rows for readability; it does not change how paths are selected.

### 3.3. Filtering Valid Edges During Path Selection

A practical requirement is traversing only active routes:

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = allShortestPaths((s)-[:CONNECTS*1..6]->(t))
WHERE all(r IN relationships(p) WHERE r.active = true)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

When **WHERE** belongs to the same **MATCH** clause containing the shortest-path selection, the predicate participates in evaluating valid paths. In this sample, A → C → D is excluded, so the result is **[A, B, D]** with 2 hops.

**Note:** do not assume that finding an arbitrary shortest path first and filtering afterward is equivalent to finding the shortest path **among valid paths**. If you need the shortest valid path, place the constraint inside the search step.

## 4. Path Selector Syntax Starting in Neo4j 5.21

Neo4j 5.21 adds GQL-aligned syntax using **SHORTEST**, **ALL SHORTEST**, and **SHORTEST k GROUPS**. To express variable hop counts, the examples below use relationship quantifiers such as **-[:CONNECTS]->{1,6}** (1 to 6 edges). Quantifier syntax has existed since Neo4j **5.9**; combining it with selectors requires a selector-capable version, i.e., **5.21 or later**.

### 4.1. SHORTEST 1 or ANY SHORTEST: Retrieving One Path

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 1 (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

Equivalent form:

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ANY SHORTEST (s)-[:CONNECTS]->+(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

The **+** symbol means **one or more** edges with no explicit upper bound; **{1,6}** caps the maximum at six. Both examples pick **one** of the two tied 2-hop paths. Use **+** when the problem genuinely needs unbounded length and search cost has been evaluated; use an upper bound when business rules cap step count.

### 4.2. ALL SHORTEST: Retrieving Every Minimum-Hop Path

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ALL SHORTEST (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY stops;
~~~

Results include **[A, B, D]** and **[A, C, D]**. Row count can be large if the graph has many tied paths; **ALL SHORTEST** does not mean "all possible paths."

### 4.3. SHORTEST k: Retrieving k Paths Ordered by Hop Count

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 2 (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY hops, stops;
~~~

Here there are two 2-hop paths, so both are returned. **k counts paths**, not distinct length tiers. If multiple paths of the same length tie at the k-th boundary, do not depend on a specific tie-breaking order.

### 4.4. SHORTEST k GROUPS: Retrieving k Length Groups

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 2 GROUPS (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY hops, stops;
~~~

Results contain **three paths**: the length-2 group has two paths (A → B → D, A → C → D), and the length-3 group has one path (A → E → F → D). Thus, **2 GROUPS can return more than 2 rows**.

| Selector | Output on Sample Graph |
|---|---|
| SHORTEST 1 / ANY SHORTEST | One of the two 2-hop paths |
| ALL SHORTEST | Both 2-hop paths |
| SHORTEST 2 | The two 2-hop paths |
| SHORTEST 2 GROUPS | Both 2-hop paths **and** one 3-hop path |

### 4.5. Filtering Relationships Directly in Modern Patterns

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ALL SHORTEST
  (s)-[r:CONNECTS WHERE r.active = true]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

The per-relationship predicate sits right inside the expanded pattern, excluding inactive edges during path search. Result: **[A, B, D]**. If A → B → D were also blocked, the algorithm would then find A → E → F → D at 3 hops, rather than concluding "no path" just because every 2-hop route is blocked.

## 5. Choosing Syntax by Version and Goal

| Neo4j / Language | Recommended Syntax for Fewest-Hop Problems | Compatibility Notes |
|---|---|---|
| **Neo4j 4.x**, **5.0–5.8** | shortestPath(), allShortestPaths() with **[*1..n]** or **[:TYPE*1..n]** | No quantified relationships or new SHORTEST selectors yet |
| **Neo4j 5.9–5.20** | shortestPath(), allShortestPaths() | Has quantified path patterns/relationships, but not **SHORTEST** selectors yet |
| **Neo4j 5.21+ with Cypher 5** | Prefer **SHORTEST 1**, **ALL SHORTEST**, **SHORTEST k/GROUPS** | Legacy functions still work but are not GQL-aligned syntax |
| **Neo4j 2025.06+ with Cypher 25** | Prefer **SHORTEST** and quantifiers like **+**, **{m,n}** | Cypher 25 introduced in 2025.06; default language depends on server/database config |

When maintaining an application across multiple versions:

1. Check both the Neo4j server version **and** the Cypher language version actually configured for the database.
2. For code that must run on Neo4j 4.x or 5.x prior to 5.21, use the legacy function syntax; do not put **SHORTEST** in shared queries.
3. On newer supported systems, use selectors to state clearly whether you want **one path**, **all tied paths**, or **k length groups**.
4. On versions supporting language selection, you can use the **CYPHER 5** prefix for legacy-compatible queries or **CYPHER 25** accordingly. This prefix **cannot upgrade** an older server to support newer syntax.

Example running legacy syntax on a newer server supporting Cypher 5:

~~~cypher
CYPHER 5
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = shortestPath((s)-[:CONNECTS*1..6]->(t))
RETURN [n IN nodes(p) | n.code] AS stops;
~~~

Do not "mechanically rewrite" **shortestPath()** into **SHORTEST 1** if the application uses complex filters or multi-part path patterns: re-verify how predicates are applied, minimum length, edge direction, and row counts.

## 6. When "Shortest" Means Fewest km or Least Time

The **fewest-hop** path in the example is A → B → D or A → C → D. However, the path with **lowest total km** is **A → E → F → D = 3 km**, even though it takes 3 hops. An approach like **ORDER BY reduce(...) LIMIT 1** over manually enumerated paths can blow up the number of traversed paths, so it is not the default design for weighted problems on large graphs.

When **Neo4j Graph Data Science (GDS)** is installed, you can create a *graph projection* and run Dijkstra. The example below is an **optional extension**, not core Cypher syntax; it requires GDS to be installed and no conflicting projection with the same name:

~~~cypher
CALL gds.graph.project(
  'demoRoutes',
  'DemoStop',
  {
    CONNECTS: {
      orientation: 'NATURAL',
      properties: 'km'
    }
  }
);
~~~

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
CALL gds.shortestPath.dijkstra.stream('demoRoutes', {
  sourceNode: s,
  targetNodes: t,
  relationshipWeightProperty: 'km'
})
YIELD totalCost, nodeIds
RETURN
  totalCost AS km,
  [id IN nodeIds | gds.util.asNode(id).code] AS stops;
~~~

Expected result: **3 km**, **[A, E, F, D]**. The projection must contain the right edge types, orientation, and **permitted** routes; in real systems, ensure closed edges (`active = false`) are excluded from routing projections. Dijkstra requires weights suited to the algorithm, typically non-negative numbers; to optimize travel time, use a time property instead of km.

## 7. Performance and Common Pitfalls

### 7.1. Narrow Down Endpoints and Hop Counts

Searching for a specific pair of nodes is generally far more efficient than matching all source–target pairs and computing shortest paths for each. On production data, use unique business keys and create appropriate constraints/indexes:

~~~cypher
CREATE CONSTRAINT demo_stop_code IF NOT EXISTS
FOR (n:DemoStop)
REQUIRE n.code IS UNIQUE;
~~~

When source and target are clearly anchored, the planner can use bidirectional search. Use **EXPLAIN** (inspect plan without running) or **PROFILE** (execute and measure rows, db hits, and timing) to evaluate:

~~~cypher
PROFILE
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 1 (s)-[:CONNECTS]->{1,6}(t)
RETURN length(p) AS hops;
~~~

In the plan you may see **ShortestPath**, **StatefulShortestPath(Into)**, or **StatefulShortestPath(All)** depending on pattern, version, and endpoint cardinality. Do not assume every SHORTEST query uses the same operator. A depth bound **{1,6}** narrows the search space, but also **excludes** solutions if the true shortest path has more than 6 edges.

### 7.2. Filtering During Search vs. Filtering After Search

Predicates evaluable on individual edges, such as **r.active = true**, can often prune invalid branches early. Predicates that can only be checked after assembling the entire path may force the engine to explore many more candidates or even fall back to exhaustive search. That is why appropriate constraints belong inside the relationship/node pattern or the same MATCH clause.

Conversely, if you first find **one** fewest-hop path and then discard it because total km is too high, the query does **not** automatically switch to returning the next path with a valid cost. Clarify whether a criterion belongs inside the optimization problem or is merely a result-filtering step.

### 7.3. Input Data and Semantics

- **No path exists:** a shortest-path MATCH returns no row for that source–target pair. If an API needs to display "not found," handle empty results or use OPTIONAL MATCH where appropriate.
- **Edge direction:** a query with **->** will not traverse backward automatically; if a problem is bidirectional, model it accordingly or intentionally use an undirected pattern.
- **Equal endpoints:** a 0-hop path is a distinct domain case; the legacy **shortestPath()** function has limitations when both endpoints are identical. Handle A → A requirements explicitly instead of assuming all syntaxes behave identically.
- **Multiple tied paths:** shortestPath()/SHORTEST 1 does not guarantee picking the same path across runs or after data updates. Use ALL SHORTEST if you need every tied option.
- **Large result sets:** ALL SHORTEST or SHORTEST k GROUPS can return many paths; consider pagination, scope bounds, and actual user requirements.
- **Parameter safety:** in Java Driver or Spring Data Neo4j applications, pass **$from** and **$to** as parameters to avoid string concatenation with user input; control relationship types and length bounds via vetted query configuration.

## 8. Practice and Self-Check

1. Run **ALL SHORTEST** on the sample graph and confirm there are exactly two 2-hop paths. Then filter **active = true** inside the pattern and explain why only A → B → D remains.
2. Run **SHORTEST 2 GROUPS** and confirm it returns three rows instead of two. Change it to **SHORTEST 2** and explain the difference between "2 paths" and "2 length groups."
3. Find the fewest-hop A → D path and the lowest-km A → D path; explain why the optimal results differ. If GDS is not installed, you can sum km across the **three** sample paths to verify the conclusion, but do not use full path enumeration as a design for large datasets.
4. Try reversing the query direction to **D → A**. With the directed edges in the sample data, no path exists; explain why dropping arrowheads can return different results.

**Key takeaway:** before every query, define the **optimization criterion** (hops vs. weights), **valid path rules** (direction, edge types, properties, depth limits), and **desired output count** (one, all tied, k paths, or k groups)—then pick syntax compatible with your **Neo4j/Cypher version**.

### Official Documentation

- [Neo4j Cypher 5 – Shortest paths](https://neo4j.com/docs/cypher-manual/5/patterns/shortest-paths/)
- [Neo4j Cypher 5 – Variable-length paths](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/)
- [Neo4j Cypher 25 – Shortest paths](https://neo4j.com/docs/cypher-manual/25/patterns/shortest-paths/)
- [Neo4j Cypher – Additions, deprecations, removals, and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
- [Neo4j Graph Data Science – Dijkstra Source-Target Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
