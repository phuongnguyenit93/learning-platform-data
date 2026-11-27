# Limiting Depth, Direction, and Relationship Types in Graph Traversals

## 1. Why Do Graph Traversals Need Limits?

In **Neo4j**, data is organized according to the **property graph** model: nodes represent entities, relationships represent typed and directed links, and properties describe attributes. Cypher lets you start from a node and traverse across multiple relationships to find acquaintances, service dependencies, routes, delivery paths, or the blast radius of an event.

However, an overly broad traversal query can generate an enormous number of **candidate paths**, even when the number of distinct destination nodes is small. Therefore, in the **Query Optimization** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module, the three most important choices when writing traversal patterns are:

1. **Depth:** what are the minimum and maximum numbers of relationships allowed?
2. **Direction:** follow the relationship direction, the reverse direction, or both directions?
3. **Relationship type:** which relationships are actually meaningful for the business question?

These three constraints clarify **result semantics** while helping Neo4j bound the search space. They must be chosen accurately according to business rules; a very fast query that drops valid paths is still an incorrect query.

### 1.1. Path Counts Can Grow Exponentially

Suppose each node has on average **b** eligible outgoing relationships to follow next. When considering paths of exact length **d** steps, the maximum branching in a simple model grows roughly as **b^d**. Across all depths from 1 to d, the number of potential paths can grow roughly as:

\[
  b + b^2 + \cdots + b^d
\]

Illustrative example with **b = 8**:

| Depth | Estimated branches at that tier alone |
|---|---:|
| 1 | 8 |
| 2 | 64 |
| 3 | 512 |
| 4 | 4,096 |
| 5 | 32,768 |

This is **not a formula for predicting actual path counts**: real graphs have cycles, convergent targets, branches pruned by direction/type, and the rule preventing reuse of the same relationship within a single MATCH result. Nevertheless, it illustrates why raising the depth limit from 3 to 5 can dramatically change the workload.

**Distinction:** a single target node can be reached via many different paths; therefore, **path count**, **unique destination node count**, **intermediate row count**, and **returned row count** are not the same quantity.

## 2. Running Example Graph

In a **testing** database, create the following constraint and data **once**. Do not run the CREATE block multiple times, as that would create duplicate data.

~~~cypher
CREATE CONSTRAINT demo_traverse_code IF NOT EXISTS
FOR (n:DemoTraversePerson)
REQUIRE n.code IS UNIQUE;
~~~

~~~cypher
CREATE
  (a:DemoTraversePerson {code: 'A', enabled: true}),
  (b:DemoTraversePerson {code: 'B', enabled: true}),
  (c:DemoTraversePerson {code: 'C', enabled: true}),
  (d:DemoTraversePerson {code: 'D', enabled: true}),
  (e:DemoTraversePerson {code: 'E', enabled: true}),
  (f:DemoTraversePerson {code: 'F', enabled: true}),
  (a)-[:KNOWS {active: true}]->(b),
  (a)-[:KNOWS {active: true}]->(c),
  (b)-[:KNOWS {active: true}]->(d),
  (c)-[:KNOWS {active: false}]->(d),
  (a)-[:COLLEAGUE {active: true}]->(e),
  (e)-[:KNOWS {active: true}]->(d),
  (d)-[:KNOWS {active: true}]->(f);
~~~

Diagram (arrows indicate the stored relationship direction):

~~~mermaid
flowchart LR
  A((A)) -->|KNOWS, active| B((B))
  A -->|KNOWS, active| C((C))
  B -->|KNOWS, active| D((D))
  C -->|KNOWS, inactive| D
  A -->|COLLEAGUE, active| E((E))
  E -->|KNOWS, active| D
  D -->|KNOWS, active| F((F))
~~~

Directed routes from A to D include:

| Route | Hops | Relationship Types | Status |
|---|---:|---|---|
| A → B → D | 2 | KNOWS, KNOWS | Both active |
| A → C → D | 2 | KNOWS, KNOWS | C → D inactive |
| A → E → D | 2 | COLLEAGUE, KNOWS | Both active |

A **hop** is one traversed relationship; the path A → B → D has **2 hops**, even though it contains **3 nodes**. Subsequent queries do not require deleting the graph to test different limit combinations.

## 3. Limiting Depth Directly in the Cypher Pattern

### 3.1. Variable-Length Relationship Syntax Compatible with Older Neo4j

Query to find people reachable from A via one or two **KNOWS** relationships following the arrow direction:

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS*1..2]->(target:DemoTraversePerson)
RETURN
  target.code AS target,
  length(p) AS hops,
  [n IN nodes(p) | n.code] AS route
ORDER BY hops, target;
~~~

The expression **[:KNOWS*1..2]** has three components:

- **KNOWS:** traverse only relationships of type KNOWS.
- **1..2:** traverse a minimum of **1** and a maximum of **2** relationships.
- **->:** follow only the direction **from start node to end node** of the stored relationship.

With the sample data, the paths are **A → B**, **A → C** (1 hop), **A → B → D**, **A → C → D** (2 hops). The query does **not** return A → B → D → F because it requires 3 hops.

Common depth patterns:

| Traditional Cypher Pattern | Meaning |
|---|---|
| **[:KNOWS]** | Exactly one relationship |
| **[:KNOWS*2]** | Exactly two relationships |
| **[:KNOWS*1..3]** | One to three relationships |
| **[:KNOWS*0..3]** | Zero to three relationships, including 0-hop paths |
| **[:KNOWS*]** | One or more relationships, **no explicit upper bound** |
| **[:KNOWS*2..]** | Two or more relationships, **no explicit upper bound** |

**Warning:** unless you genuinely need to traverse the entire reachable scope, avoid unbounded upper limits such as **[*]** or **[*1..]** in queries capable of generating many paths. Even though the default relationship-uniqueness rule limits paths on a finite graph, the number of paths can still be massive.

### 3.2. What Does Depth 0 Mean?

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS*0..2]->(target)
RETURN target.code AS target, length(p) AS hops
ORDER BY hops, target;
~~~

Because the bound starts at **0**, the result includes **A** itself with **0 hops**, in addition to 1–2 hop paths. Use **0..n** when "reachable within at most n steps" includes the source node itself. If the user requires **at least one link**, start from **1**.

### 3.3. Quantified Relationship Syntax in Neo4j 5.9+

Starting in **Neo4j 5.9**, Cypher introduced **quantified relationships** and **quantified path patterns**. The query can be written as:

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS]->{1,2}(target:DemoTraversePerson)
RETURN target.code AS target, length(p) AS hops
ORDER BY hops, target;
~~~

**-[:KNOWS]->{1,2}** means 1 to 2 outgoing KNOWS relationships. The quantifier **{1,2}** is placed **after** the entire relationship pattern; it is not written inside the square brackets as in the older syntax.

| Traditional Pattern | Quantified Relationship | Hops |
|---|---|---|
| **-[:KNOWS*1..3]->** | **-[:KNOWS]->{1,3}** | 1–3 |
| **-[:KNOWS*2]->** | **-[:KNOWS]->{2}** | Exactly 2 |
| **-[:KNOWS*0..3]->** | **-[:KNOWS]->{0,3}** | 0–3 |
| **-[:KNOWS*]->** | **-[:KNOWS]->+** | 1 or more, unbounded |
| **-[:KNOWS*0..]->** | **-[:KNOWS]->*** | 0 or more, unbounded |

**Do not confuse the asterisk:** the older pattern **-[:KNOWS*]->** has a minimum of **1 hop**, whereas the new quantified pattern **-[:KNOWS]->*** allows **0 hops**. Pay special attention to this when migrating syntax.

In queries requiring compatibility with **Neo4j 4.x or Neo4j 5.0–5.8**, keep using the traditional **[*m..n]** pattern. Use quantified syntax only when supported by the target server and Cypher version.

## 4. Traverse Only the Right Relationship Direction

Cypher has three ways to specify direction for a relationship:

| Pattern | Traversal Direction When Matching |
|---|---|
| **(a)-[:KNOWS]->(b)** | From **a to b** along the stored direction |
| **(a)<-[:KNOWS]-(b)** | From **b to a** along the stored direction |
| **(a)-[:KNOWS]-(b)** | Accepts relationships in **either direction** |

This also applies to multi-hop paths. Compare three queries with the same endpoints A and D:

### 4.1. Going Forward from A to D

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..2]->(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

The results are **A → B → D** and **A → C → D**. The route through E is excluded because the first hop is **COLLEAGUE**, not KNOWS.

### 4.2. Allowing Only Relationships Pointing Into A

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)<-[:KNOWS*1..2]-(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

The result has **no rows**: the sample data has no directed KNOWS route from D back to A. If the application interprets "A knows B" symmetrically while the data only stores **A → B**, the reverse-direction pattern will not automatically infer **B → A**.

### 4.3. Allowing Both Directions

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..2]-(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

The query can traverse KNOWS relationships regardless of stored direction, so it still finds A–B–D and A–C–D. Allowing bidirectional matching **does not change** the relationship direction stored in the database; it only changes **pattern matching rules**.

**Performance impact:** on a node with many incoming and outgoing relationships, an undirected pattern **-[]-** may have to evaluate more candidates than a directed pattern **-[]->**. However, actual savings depend on relationship distribution. Do not change direction just for speed if the business rule requires traversing both directions.

## 5. Traverse Only the Right Relationship Types

In a property graph, types such as **KNOWS**, **COLLEAGUE**, **MANAGES**, **DEPENDS_ON**, and **OWNS** carry distinct meanings. Omitting the type constraint can cause the query to mix in routes that are invalid for the business logic.

### 5.1. Restricting to One Type

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH p = (s)-[:KNOWS*1..2]->(target)
RETURN target.code AS target, length(p) AS hops;
~~~

Neo4j expands only **KNOWS** relationships in the specified direction. In the sample graph, A → E → D is not considered because A → E is **COLLEAGUE**.

### 5.2. Allowing a Specific Set of Types

In the traditional pattern, use **|** to combine allowed types:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS|COLLEAGUE*1..2]->(t)
RETURN [n IN nodes(p) | n.code] AS route
ORDER BY route;
~~~

This snippet allows **KNOWS or COLLEAGUE at each hop**, so it returns three routes: A → B → D, A → C → D, and A → E → D.

With quantified relationship syntax (Neo4j 5.9+), the equivalent constraint is:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS|COLLEAGUE]->{1,2}(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

When you only need a finite set of types, **specify the types directly in the relationship pattern** so the planner knows the expansion constraint. Do not use a generic **-[*1..n]-** pattern and filter **type(r)** after building paths if you already know which types are valid.

### 5.3. Relationship Type Is a Per-Hop Rule

The pattern **[:KNOWS|COLLEAGUE*1..2]** means **each hop** is allowed to be KNOWS **or** COLLEAGUE. It does **not** require the entire path to have only a single type. In the example A → E → D, the first leg is COLLEAGUE and the second leg is KNOWS, and it still matches the pattern.

If the business rule requires a fixed sequence of types, write the pattern accordingly:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH p = (s)-[:COLLEAGUE]->(colleague)-[:KNOWS]->(target)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

The result is A → E → D. This pattern is clearer and narrows the search space better than allowing all two-step KNOWS/COLLEAGUE combinations and filtering the type sequence at the end.

## 6. Combining the Three Limits with Property Predicates

In practice, only **active = true** relationships may be traversed. This condition should be pushed into path finding when syntax and version support it.

### 6.1. Traditional Pattern, Filtering Over the Entire Path

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..3]->(t)
WHERE all(r IN relationships(p) WHERE r.active = true)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Only **A → B → D** remains. However, the **all(...)** expression operates on the relationship list of the completed path; depending on optimizer capabilities and the actual plan, the engine may generate many candidates before discarding paths containing inactive edges.

### 6.2. Inline Relationship Predicate in the New Syntax

In versions supporting quantified relationships and relationship WHERE clauses (Neo4j 5.9+), you can place the predicate **directly at the expansion step**:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[r:KNOWS WHERE r.active = true]->{1,3}(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

This solves the same business problem: use only **KNOWS**, go **forward**, up to **3 hops**, and traverse only **active** relationships. Per-relationship predicates help prune invalid branches **during expansion** rather than after constructing paths. On the sample graph, C → D is never taken.

If there are predicates on **intermediate nodes**, quantified path patterns allow writing predicates directly inside the repeated segment, but you must verify the exact semantics of start and end nodes: predicates inside a repeated segment can apply to an endpoint on **each iteration**, not just interior nodes of the overall route.

**Do not equate "filtering final results" with "restricting valid paths."** If you select a single shortest path first and then discard it due to an inactive edge, the engine is not obligated to automatically supply a valid alternative path. Constraints must be part of path selection from the outset.

## 7. Neo4j Can Optimize Further When Start and End Points Are Known

### 7.1. Starting from a Clearly Identified Node

Compare:

~~~cypher
// Scans very broad pairs of nodes and paths.
MATCH p = (a:DemoTraversePerson)-[:KNOWS*1..3]->(b)
RETURN b.code, length(p);
~~~

with:

~~~cypher
// Identify a specific starting point before traversing.
MATCH (a:DemoTraversePerson {code: $sourceCode})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN b.code, length(p);
~~~

In the second query, **$sourceCode** is passed as a parameter from a Java Driver/Spring Data Neo4j application; the unique constraint in section 2 provides an index supporting lookup of **one** source node. Thus, the engine only traverses from the node of interest.

When both source and target are known, constrain both:

~~~cypher
MATCH (a:DemoTraversePerson {code: $sourceCode})
MATCH (b:DemoTraversePerson {code: $targetCode})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

The planner may select the **VarLengthExpand(Into)** operator to connect the two known endpoints, depending on data and version. That does not mean every query will use the exact same operator; inspect the actual plan.

### 7.2. Do You Need Target Nodes or Every Path?

A query returning paths:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN b.code AS destination, [n IN nodes(p) | n.code] AS route;
~~~

can return **multiple rows for the same b** because multiple paths exist. If only a unique list of destinations is needed:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (a)-[:KNOWS*1..3]->(b)
RETURN DISTINCT b.code AS destination
ORDER BY destination;
~~~

Dropping the path variable and using **DISTINCT** expresses a different output requirement. In some plans, Neo4j may choose **VarLengthExpand(Pruning)** to avoid re-emitting duplicate end nodes. However, **DISTINCT does not guarantee the engine avoids traversing many edges**: you still need to check **PROFILE** to assess resource usage.

### 7.3. Only Checking Whether a Path Exists

If the UI only asks "Can A reach D in at most 3 KNOWS steps?", a query returning all paths is wasteful. Use an existence expression:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
RETURN EXISTS {
  MATCH (a)-[:KNOWS*1..3]->(b)
} AS reachable;
~~~

The result is **true** on the sample dataset. The **EXISTS** expression communicates that the application only needs a boolean answer, allowing the execution engine to use a strategy suited for existence checks.

### 7.4. When Only One Shortest-Hop Path Is Needed

Do not default to:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = (a)-[:KNOWS*1..4]->(b)
RETURN p
ORDER BY length(p)
LIMIT 1;
~~~

A query that sorts by path length may process many candidate paths. When the actual requirement is **a path with the fewest relationships**, consider dedicated shortest-path constructs:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = shortestPath((a)-[:KNOWS*1..4]->(b))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
~~~

In **Neo4j 5.21+** with Cypher path selectors:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = SHORTEST 1 (a)-[:KNOWS]->{1,4}(b)
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
~~~

In the sample data, both A → B → D and A → C → D have 2 hops, so **one** shortest path can be either route. If all tied shortest paths are required, use **allShortestPaths()** or **ALL SHORTEST** on supported versions. If you need to minimize **total kilometers or cost**, that is a weighted shortest-path problem, not merely minimizing hop count.

## 8. EXPLAIN and PROFILE: Proving That Limits Help

### 8.1. Measuring Before and After Changes

Run queries in a **testing database**; use the same dataset and parameters for comparison:

~~~cypher
EXPLAIN
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..5]->(b)
RETURN b.code, length(p);
~~~

~~~cypher
PROFILE
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..2]->(b)
RETURN b.code, length(p);
~~~

**EXPLAIN** only generates the plan without executing the query; **PROFILE** executes it and provides measurements, so for write statements it also **modifies data**. Only use PROFILE on potentially heavy queries after assessing resource impact.

### 8.2. Metrics to Read

| Metric / Operator | How to Interpret |
|---|---|
| **Estimated Rows** | Planner's row count prediction, not a measured result |
| **Rows** | Actual number of rows produced by each operator during PROFILE |
| **DB Hits** | Number of low-level storage access operations; distinct from returned rows |
| **Memory (Bytes)** | Peak memory usage of the operator, shown where applicable |
| **NodeUniqueIndexSeek** | May appear when locating a node by a unique key |
| **VarLengthExpand(All)** | Expands variable-length paths from a node |
| **VarLengthExpand(Into)** | Finds variable-length paths between two already-bound nodes |
| **VarLengthExpand(Pruning)** | Expands while pruning duplicate end nodes when appropriate |
| **Filter / Sort / Distinct** | Indicates filtering, sorting, or deduplication steps that may process many rows |

Specific operator names, runtime modes, and optimization capabilities differ across Neo4j/Cypher versions. **Do not assume** that a given pattern always produces the exact same execution plan on every database.

To evaluate properly: compare the **same data pattern**, **the same representative parameters**, row counts, and DB Hits **at each operator**, not just single-run wall-clock time. On the six-node set in section 2, tiny differences may be dominated by overhead; measurements under realistic load are what justify optimization decisions.

### 8.3. Why LIMIT Does Not Replace Depth Limits

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*]->(b)
RETURN p
LIMIT 10;
~~~

**LIMIT 10** caps the number of **returned** rows, not the maximum path length. Depending on the plan, the engine might stop early once enough rows are found or still do massive work, especially when **ORDER BY**, **DISTINCT**, aggregations, or post-expansion filters are present.

If the business rule permits at most three relationships, put **[*1..3]** or **->{1,3}** **directly in the pattern**. Then add **LIMIT** afterward if the UI needs to cap displayed rows.

## 9. An Optimization Workflow You Can Apply to Real Applications

| Step | Question | Example Decision |
|---|---|---|
| **1. Define semantics** | Is the query finding impact, management chains, or all paths? | Only **DEPENDS_ON** edges |
| **2. Bind source/target** | Is there a sufficiently selective business key to anchor the start? | **Service.id = $sourceId** with index/constraint |
| **3. Set depth** | How many tiers does the real system need to inspect at most? | 1–4 hops, per business rules |
| **4. Set direction** | Is reversing stored direction allowed? | Dependencies follow **->** |
| **5. Choose types** | Which relationship types are valid at each hop? | **:DEPENDS_ON** instead of any relationship |
| **6. Filter early** | What properties must every edge/node satisfy? | **r.enabled = true** inline in the new syntax |
| **7. Pick output shape** | Need all paths, unique destination nodes, boolean, or a shortest path? | **EXISTS** if only checking reachability |
| **8. Verify** | How do plan, DB Hits, rows, and p95 compare before/after? | Compare **PROFILE** on a representative workload |

### 9.1. Service Dependency Analysis Example

Suppose a model has **(:Service)-[:DEPENDS_ON]->(:Service)** relationships. To find services depended upon directly or indirectly within up to four layers along the stored direction:

~~~cypher
MATCH (root:Service {serviceId: $serviceId})
MATCH (root)-[:DEPENDS_ON*1..4]->(dependency:Service)
RETURN DISTINCT dependency.serviceId AS serviceId
ORDER BY serviceId;
~~~

Why is this pattern better than **(root)-[*]-(anything)**?

- Anchors **one** Service by an indexed key.
- Direction **->** reflects service-to-dependency, avoiding unintended reverse "dependents" traversal.
- Type **DEPENDS_ON** excludes relationships such as **OWNED_BY**, **RUNS_ON**, and **MONITORED_BY**.
- Max depth **4** prevents expanding into unnecessary deeper tiers.
- **DISTINCT** fits because the UI asks for a list of services, not individual paths.

However, if the business question asks "which services will be impacted if service X goes down?", you may need to traverse **against** the **DEPENDS_ON** direction:

~~~cypher
MATCH (failed:Service {serviceId: $serviceId})
MATCH (affected:Service)-[:DEPENDS_ON*1..4]->(failed)
RETURN DISTINCT affected.serviceId AS affectedServiceId;
~~~

Same relationship type, yet **reversing traversal direction yields a different business answer**. That is why optimization must start from data semantics, not DB Hits alone.

### 9.2. Avoid Concatenating Syntax from Untrusted Input

In the Java Driver or Spring Data Neo4j, always use parameters like **$serviceId** for property values. However, in traditional patterns, **depth bounds on [*m..n]**, arrow directions, and relationship types are part of the **query structure**, not replaceable with value parameters.

For APIs allowing users to pick a depth, the application should restrict choices to a **controlled set of presets** (e.g., 1–2, 1–3, or 1–4) and select the corresponding Cypher template; validate input strictly. Never concatenate relationship type strings, arrows, or bounds from arbitrary input directly into a query string.

## 10. Common Mistakes in Graph Traversal

1. **Omitting an upper bound:** patterns like **[*]**, **->+** on dense graphs can generate huge numbers of paths even when the query returns only a few nodes.
2. **Using WHERE length(p) <= 3 instead of an explicit bound:** sometimes the planner optimizes it, but putting bounds **in the pattern** expresses intent and gives expansion a direct limit.
3. **Forgetting direction:** using **-[]-** does not mean relationships in the data are bidirectional; it simply allows the query to traverse both ways.
4. **Forgetting type:** **-[*1..3]-** can cross unrelated relationship types and inflate branching.
5. **Confusing hops with nodes:** **length(p)** counts relationships, while **size(nodes(p))** counts nodes on the path, usually hops plus one.
6. **Conflating paths with destination nodes:** **DISTINCT** results may be tiny even when intermediate path counts are huge.
7. **Thinking LIMIT controls depth:** LIMIT only caps output rows; you still need bounds in the pattern.
8. **Filtering edge state too late:** placing an **active** predicate after forming all paths may not save expansion work; prefer inline predicates when supported by your version.
9. **Assuming paths can never revisit a node:** by default Cypher does not repeat the **same relationship** in a single MATCH result, but **a node can appear multiple times** via different relationships. In newer Cypher 25, special path/match modes exist; do not blindly assume uniqueness rules when using **REPEATABLE ELEMENTS**.
10. **Looking only at single-run execution time:** ignoring the plan, selectivity, and DB Hits leads to unfounded conclusions.

## 11. Practice Exercises

### Exercise 1 — Analyzing Results

On the sample graph, predict the paths from A to D for each pattern:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (d:DemoTraversePerson {code: 'D'})
MATCH p = (a)-[:KNOWS*1..2]->(d)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Next, change **KNOWS** to **KNOWS|COLLEAGUE**, then add a condition requiring only **active = true** relationships. Explain why the path count changes.

### Exercise 2 — Fixing an Overly Broad Query

Given:

~~~cypher
MATCH p = (a:DemoTraversePerson)-[*]-(b)
RETURN p
LIMIT 100;
~~~

The new requirement is "from person A, find people reachable within at most three KNOWS steps, following only the stored relationship direction." Rewrite the query with a **source anchor**, **direction**, **type**, **bound**, and appropriate output selection.

### Exercise 3 — Reversing Business Meaning by Flipping Direction

Given **Service A DEPENDS_ON Service B**, **Service C DEPENDS_ON Service A**. Which query finds A's dependencies? Which query finds services impacted if A fails? Use arrow directions to prove your answer.

### Exercise 4 — Testing Execution Plans

Run **EXPLAIN/PROFILE** with depths 1..2 and 1..4 on a sufficiently large dataset in a testing environment. Record **Rows**, **DB Hits**, path expansion operators, and p95 latency. Check which depth bound satisfies business requirements while remaining resource-efficient.

### Exercise 5 — Choosing the Right Construct for the Goal

For the same source–target pair, write the best-suited construct for three questions: (a) does a path exist, (b) find one path with the fewest hops, (c) find all paths with at most three hops. Explain why returning all paths and doing **ORDER BY ... LIMIT 1** is not necessarily optimal for (b).

## Takeaways

Limiting **depth**, **direction**, and **relationship types** directly in Cypher is the most straightforward way to avoid runaway traversals and preserve semantic correctness. Start from a node with a selective identifier, set business-driven bounds, expand only in the right direction and types, push predicates onto individual edges when possible, and choose **paths**, **target nodes**, **EXISTS**, or **shortest path** according to output needs. Finally, use **EXPLAIN/PROFILE** to verify real impact instead of guessing speed from syntax.

### Official Neo4j Documentation

- [Cypher 5 – Variable-length paths and quantified relationships](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/)
- [Cypher – Variable-length paths, syntax and bounds](https://neo4j.com/docs/cypher-manual/current/patterns/reference/variable-length-paths/)
- [Cypher – Node and relationship patterns, directionality](https://neo4j.com/docs/cypher-manual/current/patterns/reference/node-and-relationship-patterns/)
- [Cypher – Understanding query plans, EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Cypher – Query plan operators](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/)
- [Cypher – Paths with unique relationships](https://neo4j.com/docs/cypher-manual/current/patterns/unique-relationship-paths/)
