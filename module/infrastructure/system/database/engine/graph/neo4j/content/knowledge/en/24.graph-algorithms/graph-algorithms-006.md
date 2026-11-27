# Centrality with PageRank and Influence Measures

## 1. From Link Graphs to the Question "Who Is Influential?"

In Neo4j's **property graph** model, nodes represent entities and relationships represent links between them. In a user network, a graph might store follow relationships; in an academic system, citations between papers; in a commercial application, websites linking to other websites or products mentioned together.

Common questions include:

- Which account has the **most followers**?
- Which account is followed by **reputable users**, even if its follower count is not the highest?
- Who acts as a **bridge** between two communities that rarely interact?
- Which node has short distances to many other nodes?
- When selecting a set of accounts to prioritize for analysis, which metric should you rely on?

These questions relate to **centrality**, yet there is no single definition of "influence" for every application. **PageRank** measures importance based on directed link structure and the distribution of importance across links. Other metrics such as **degree**, **betweenness**, **closeness**, and **eigenvector centrality** capture different facets.

This lesson belongs to the **Graph Algorithms** chapter of the Neo4j module. The focus is on accurately modeling relationship direction in Cypher, understanding score semantics, computing PageRank with **Neo4j Graph Data Science (GDS)**, comparing metrics, and using results responsibly in Java Driver / Spring Data Neo4j applications.

> **Limitations of scores:** Centrality is a property of the **selected graph** under a **defined metric**. It does not prove someone is an expert, trustworthy, possesses real-world authority, or has a positive impact. Interpretation always depends on data, relationship orientation, scope, and timing.

## 2. Distinguishing Centrality Metrics

| Metric | Core Idea | Appropriate Question | Notable Limitations |
|---|---|---|---|
| **In-degree** | Counts relationships pointing **into** a node | Who is followed/cited the most? | Treats all links equally; ignores source reputation |
| **Out-degree** | Counts relationships pointing **out of** a node | Who follows or cites the most? | Does not directly measure recognition |
| **PageRank** | Score flows across links via a random walk process | Who receives links from important nodes? | Sensitive to direction/structure; does not measure content quality |
| **Eigenvector centrality** | A node scores high when connected to high-scoring nodes | Who connects to an important group? | Depends on component/direction structure and normalization |
| **Betweenness centrality** | How many shortest paths between pairs pass through a node | Who acts as a bridge connecting groups? | Expensive on large graphs; assumes shortest paths are meaningful |
| **Closeness centrality** | Distance from a node to all other nodes | Who can reach the rest of the network quickly? | Disconnected graphs require proper definition/normalization |

Two nodes can **tie on in-degree** yet **differ in PageRank** because the structural quality of the nodes pointing to them differs. A node connecting two clusters may have **high betweenness** without having many followers. Therefore, algorithm choice must follow the **business question**, not whichever algorithm name is most popular.

### 2.1. Counting Links vs. Evaluating Network Position

Suppose account A has 20 followers who are all new accounts with few connections; account B has 5 followers, each of whom is followed by many prominent accounts. In-degree favors A. PageRank may favor B because the scores of linking sources propagate to B.

You cannot assume B always wins: PageRank also depends on **each source's outgoing link count**, link cycles, nodes with no outgoing edges, the damping factor, and the overall graph structure.

## 3. Relationship Direction Determines Score Semantics

In a social graph, defining:

~~~cypher
(a:Person)-[:FOLLOWS]->(b:Person)
~~~

means **a follows b**. In this directed graph, an edge points **from follower to followed user**.

If PageRank propagates score **along the edge direction**, node **b** receives contributions from **a**. This is the natural convention for "who draws community attention?" If instead edges were modeled **followed → follower**, the exact same algorithm would measure a different phenomenon.

Example:

~~~text
(An) ----FOLLOWS----> (Minh)
(Vy) ----FOLLOWS----> (Minh)
(Khoa) --FOLLOWS----> (Minh)
(Minh) --FOLLOWS----> (An)
(Lan) ---FOLLOWS----> (Vy)
(Lan) ---FOLLOWS----> (Minh)
(Linh) --FOLLOWS----> (An)
(Linh) --FOLLOWS----> (Khoa)
~~~

Minh has more incoming edges than An, yet exact PageRank scores must be computed across the entire network. Here, `FOLLOWS` edges only reflect attention via following; they do not guarantee real followers, active accounts, or relationship quality.

### 3.1. Directed and Undirected Relationships

In GDS, a relationship can be **projected** in its original direction, reversed direction, or undirected form, depending on the algorithm's purpose. For PageRank:

- **Original direction (NATURAL):** fits when edges already point from "endorser" to "endorsed."
- **Reversed direction (REVERSE):** flips score propagation, useful for symmetric or inverse questions.
- **Undirected (UNDIRECTED):** treats endpoints as mutually reachable; semantically closer to a bidirectional interaction network rather than original endorsement prestige.

**Never swap directions just to "make scores look nicer."** Define the real-world semantics of your data first, then select the projection configuration.

## 4. PageRank Intuition: The "Random Surfer"

Imagine someone starting at a node and randomly picking an outgoing relationship to move to another node. Usually they keep following edges; occasionally they jump randomly to any node in the graph to avoid getting trapped forever in one region.

**PageRank** estimates how frequently a node is visited when this process repeats many times. Consequently:

1. Nodes receiving many links tend to be visited often.
2. Links from frequently visited nodes contribute substantially.
3. If a node points to many targets, its per-edge contribution is split.
4. "Random jumps" allow nodes with no incoming links to still receive some score and help handle disconnected regions.

Originally proposed for ranking web pages, the algorithm applies to many networks where edges represent endorsement, citation, or attention.

### 4.1. Basic Formula

For a graph with `N` nodes, **damping factor** `d`, and `In(v)` as the set of nodes with edges pointing into `v`, the intuitive PageRank form when every source node has at least one outgoing edge is:

\[
PR(v)=\frac{1-d}{N}+d\sum_{u\in In(v)}\frac{PR(u)}{outDegree(u)}
\]

Where:

- `PR(v)` is the PageRank score of node `v`.
- `d` is the probability of continuing along an edge, commonly illustrated as **0.85**.
- `outDegree(u)` is the number of outgoing edges from `u`.
- `PR(u) / outDegree(u)` is the contribution from source `u` distributed evenly across its outgoing edges.

Iterations update scores until reaching the iteration cap or convergence threshold defined by the implementation. Because PageRank depends on the entire graph, you **cannot** accurately compute scores in general merely by counting direct neighbors.

**Note on nodes with no outgoing edges (dangling nodes):** dividing by `outDegree = 0` cannot be used directly. A common mathematical formulation redistributes their probability mass via teleportation rules. Libraries handle normalization and convergence according to their own implementation details; do not assume GDS score totals or ranges match every textbook verbatim.

### 4.2. Why Does the Factor `d` Matter?

When `d` is small, random jumps dominate; differences driven by link structure shrink. When `d` is large, paths along edges carry greater weight; dense regions or cyclic clusters retain stronger influence.

The value **0.85** is a popular starting choice, not a mandatory constant. Check ranking stability across reasonable values when scores drive critical decisions.

### 4.3. High-Scoring Nodes Need Not Have Many Edges

For instance, An only receives a link from Minh, yet Minh receives many important links. An can inherit a substantial share of PageRank. Conversely, a node with many followers who each follow hundreds of other accounts may receive only tiny per-edge contributions.

This explains why **PageRank measures propagated structural prestige**, whereas **in-degree counts direct links**.

## 5. Preparing a Test Graph in Neo4j

The write statements below are intended for a **dedicated practice database**. The `InfluenceDemoUser` label is explicitly chosen to avoid mixing with operational `Person` labels.

### 5.1. Creating Six Test Nodes

~~~cypher
MERGE (an:InfluenceDemoUser {handle: 'an'})
MERGE (minh:InfluenceDemoUser {handle: 'minh'})
MERGE (vy:InfluenceDemoUser {handle: 'vy'})
MERGE (khoa:InfluenceDemoUser {handle: 'khoa'})
MERGE (lan:InfluenceDemoUser {handle: 'lan'})
MERGE (linh:InfluenceDemoUser {handle: 'linh'})
MERGE (an)-[:FOLLOWS]->(minh)
MERGE (vy)-[:FOLLOWS]->(minh)
MERGE (khoa)-[:FOLLOWS]->(minh)
MERGE (minh)-[:FOLLOWS]->(an)
MERGE (lan)-[:FOLLOWS]->(vy)
MERGE (lan)-[:FOLLOWS]->(minh)
MERGE (linh)-[:FOLLOWS]->(an)
MERGE (linh)-[:FOLLOWS]->(khoa);
~~~

This creates or reuses nodes by `handle` in the test graph and ensures the specified `FOLLOWS` relationship patterns exist. In production deployments, create a uniqueness constraint on stable IDs before multiple workers write concurrently:

~~~cypher
CREATE CONSTRAINT influence_demo_handle_unique IF NOT EXISTS
FOR (u:InfluenceDemoUser)
REQUIRE u.handle IS UNIQUE;
~~~

When starting fresh from an empty environment, create the constraint **before** the `MERGE` statements. If the graph already contains duplicate `handle` values, constraint creation will fail and duplicates must be resolved per business rules.

In practice exercises, run initialization once on an isolated database; re-running `MERGE` does not replace concurrency controls or uniqueness enforcement for real data.

### 5.2. Verifying Direction and Edge Counts

~~~cypher
MATCH (a:InfluenceDemoUser)-[r:FOLLOWS]->(b:InfluenceDemoUser)
RETURN a.handle AS follower,
       type(r) AS relationship,
       b.handle AS followed
ORDER BY follower, followed;
~~~

On a freshly created test graph, expect **6 nodes and 8 `FOLLOWS` relationships**. If existing data already shared the same label or IDs, verify actual counts before interpreting algorithm outputs.

## 6. Computing In-Degree with Cypher Before Running PageRank

Counting direct followers is an easily verifiable starting point:

~~~cypher
MATCH (u:InfluenceDemoUser)
OPTIONAL MATCH (f:InfluenceDemoUser)-[:FOLLOWS]->(u)
RETURN u.handle AS handle,
       count(DISTINCT f) AS followerCount
ORDER BY followerCount DESC, handle ASC;
~~~

With the dataset above:

- Minh is followed by **An, Vy, Khoa, and Lan**: in-degree = **4**.
- An is followed by **Minh and Linh**: in-degree = **2**.
- Vy is followed by **Lan**: in-degree = **1**.
- Khoa is followed by **Linh**: in-degree = **1**.
- Lan and Linh have no followers in the test set: in-degree = **0**.

**OPTIONAL MATCH** retains nodes with zero followers. `count(DISTINCT f)` counts **distinct follower nodes**, not relationships. If the model allows multiple `FOLLOWS` edges between the same pair of users, `count(r)` yields a different metric; choose the counting rule matching your business definition.

### 6.1. Out-Degree Answers a Different Question

~~~cypher
MATCH (u:InfluenceDemoUser)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:InfluenceDemoUser)
RETURN u.handle AS handle,
       count(DISTINCT v) AS followingCount
ORDER BY followingCount DESC, handle ASC;
~~~

Here Lan and Linh each have **2** outgoing edges, while Minh has **1**. Someone who **follows many people** is not necessarily **followed by many people**.

Avoid computing both in-degree and out-degree using two `OPTIONAL MATCH` clauses in the same pipeline without aggregating separately first, because incoming × outgoing combinations create a **Cartesian multiplication of rows**, skewing counts that omit `DISTINCT`.

## 7. Graph Data Science: Running PageRank on a Projection

**Neo4j Graph Data Science (GDS)** is a dedicated algorithm and graph-processing library with installation, permission, and version/environment requirements. A standard Neo4j database **does not include all GDS procedures by default**.

GDS typically executes algorithms on an **in-memory named graph projection** built from Neo4j graph data. Creating a projection **does not duplicate nodes into the database**; it builds a computational structure. Projections consume memory and have lifecycles that must be managed.

The following examples illustrate common **GDS 2.x** syntax; before running in a live environment, check the procedure signatures and config options for your **installed GDS version**.

### 7.1. Creating a Named Graph from Nodes and Relationships

~~~cypher
CALL gds.graph.project(
  'influenceDemoGraph',
  'InfluenceDemoUser',
  'FOLLOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

The projection uses the `InfluenceDemoUser` label and `FOLLOWS` relationship type in natural edge orientation (in this simple form). On a clean test dataset, expect **6 nodes and 8 relationships**.

`influenceDemoGraph` is the name of a **projection in the GDS catalog**, not a label, database name, or CSV file. When a graph of the same name already exists in the current catalog, decide whether to reuse it or drop the old projection deliberately before recreating.

### 7.2. Computing PageRank and Returning Top Nodes

~~~cypher
CALL gds.pageRank.stream(
  'influenceDemoGraph',
  {
    dampingFactor: 0.85,
    maxIterations: 40
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Meaning:

- `gds.pageRank.stream` runs the algorithm on the projected graph and returns **score rows**, without automatically writing new properties to stored nodes.
- `nodeId` is the node ID inside the projection. `gds.util.asNode(nodeId)` retrieves the corresponding Neo4j node for compatible projection types.
- `score` is the computed PageRank value.
- `ORDER BY score DESC` sorts higher-scoring nodes first.

To limit results to the top 3:

~~~cypher
CALL gds.pageRank.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC
LIMIT 3;
~~~

**Do not fill in "expected" PageRank numbers** before running the algorithm: scores depend on iterations, configuration, and the projected graph. You can verify that Minh has high in-degree, yet that alone does not prove final PageRank ordering without running the computation.

### 7.3. Configuration Parameters to Consider

Common configuration options:

| Parameter | Effect |
|---|---|
| `dampingFactor` | Preference for following relationships versus teleportation |
| `maxIterations` | Maximum number of algorithm iterations |
| `tolerance` (if supported by version) | Convergence threshold for early stopping when score deltas are small enough |
| `relationshipWeightProperty` | Uses projected edge weights |
| `concurrency` (if supported) | Execution parallelism and resource pressure |

Results can vary across configurations. Record the **GDS version, projection name, configuration, and graph snapshot timestamp** when rankings must be audited or reproduced.

### 7.4. Dropping the Projection

After finishing with the test projection:

~~~cypher
CALL gds.graph.drop('influenceDemoGraph')
YIELD graphName
RETURN graphName;
~~~

This frees the **in-memory GDS named graph**. It **does not delete** nodes or relationships from the underlying Neo4j database.

Do not drop projections currently in use by other jobs. In applications, enforce clear projection naming and lifecycle ownership per pipeline.

## 8. Weighted PageRank: When Links Do Not Carry Equal Weight

Many systems exhibit varying interaction intensities, for example:

- Links from an active account carry different credibility than links from a brand-new account.
- Citation relationships are classified as primary citations versus passing mentions.
- Relationship strength is derived from interaction counts, capped to resist spam.

With **weighted PageRank**, each edge carries a valid non-negative weight conforming to GDS semantics and requirements; the algorithm uses weights to distribute contributions from a source node across its outgoing edges. For a probabilistic walk interpretation, use **positive** weights with outgoing weight sums **greater than 0**.

The contribution from `u` to `v` can be expressed as:

\[
PR(u)\cdot\frac{w(u,v)}{\sum_{(u,x)\in E}w(u,x)}
\]

An edge from a source with only **one** outgoing edge still receives that source's full outgoing contribution whether its weight is 1 or 3. Weights matter specifically when a source has **multiple outgoing choices**.

### 8.1. Assigning Illustrative Weights

On the demo graph, first assign every `FOLLOWS` relationship the same weight:

~~~cypher
MATCH (:InfluenceDemoUser)-[r:FOLLOWS]->(:InfluenceDemoUser)
SET r.strength = 1.0;
~~~

Increase the weight of `Lan → Minh` (Lan also has an edge to Vy):

~~~cypher
MATCH (:InfluenceDemoUser {handle: 'lan'})-[r:FOLLOWS]->
      (:InfluenceDemoUser {handle: 'minh'})
SET r.strength = 3.0;
~~~

In this lesson, weight `3` is **strictly illustrative**, not a universal formula for "true influence." On real data, define the source and rules for computing `strength`, filter abuse/fraud, normalize, and inspect weight distributions.

### 8.2. Projecting Edge Properties and Running Weighted PageRank

~~~cypher
CALL gds.graph.project(
  'influenceWeightedGraph',
  'InfluenceDemoUser',
  {
    FOLLOWS: {
      orientation: 'NATURAL',
      properties: ['strength']
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

~~~cypher
CALL gds.pageRank.stream(
  'influenceWeightedGraph',
  {
    dampingFactor: 0.85,
    relationshipWeightProperty: 'strength',
    maxIterations: 40
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Ensure the property is projected **across all relationships used by the algorithm** with a valid numeric type. If some edges lack `strength`, depending on projection configuration you may need a default value or data cleanup prior to graph creation; do not assume GDS automatically treats missing edges as `1.0`.

After testing, drop the projection:

~~~cypher
CALL gds.graph.drop('influenceWeightedGraph')
YIELD graphName
RETURN graphName;
~~~

### 8.3. Do Not Mistake Interaction Weight for Proof of Reputation

If account A continuously generates thousands of automated interactions with B, weighted PageRank can inflate B's score if `strength` scales unchecked with interaction count. Establish anti-spam rules, weight caps, time windows, and data quality checks before exposing ranking scores in production.

## 9. Comparing PageRank with Betweenness Centrality

**Betweenness** measures how often a node lies on **shortest paths** between pairs of other nodes. In a graph with two weakly connected communities, a node bridging them can serve as a "bridge" traversed by many shortest paths.

Suppose:

~~~text
Group A:  A1 --- A2 --- A3
                  |
                  X
                  |
Group B:  B1 --- B2 --- B3
~~~

Node X can have high betweenness because many paths from Group A to Group B pass through X, even though X only has a few direct edges. That captures a **flow-bridging role**, unlike PageRank's "endorsed by many important nodes."

### 9.1. Computing Betweenness with GDS

On the demo projection created in Section 7:

~~~cypher
CALL gds.betweenness.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

If you dropped the projection in Section 7.4, recreate it before running this example.

**Interpretation:** Betweenness relies on shortest paths according to the graph's modeled relationships and orientation. If the graph is directed while business behavior flows bidirectionally, results differ significantly. On large graphs, exact betweenness can be resource-intensive; depending on your GDS version, sampling/approximation modes may be used if supported and suitable.

### 9.2. When to Prefer Betweenness?

Appropriate when you want to:

- Detect intermediaries connecting separate communities.
- Identify nodes critical to connectivity or information flow.
- Assess dependency bottlenecks in process graphs or communication networks.

Do not use betweenness to conclude a node is trusted by the community or produces high-quality content. A technical bottleneck can also exhibit high betweenness.

## 10. Closeness, Eigenvector, and Complementary Metrics

### 10.1. Closeness Centrality: Distance to the Rest

**Closeness** is typically based on the inverse of the total shortest-path distance from a node to other reachable nodes. If each edge represents one step of information transmission, a node close to many others may benefit from **fast reachability**.

~~~cypher
CALL gds.closeness.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

On **disconnected** or **directed** graphs where not all nodes can reach one another, closeness variants handle unreachable nodes differently. **Never mechanically compare raw scores across graphs with different connectivity structures** without knowing how GDS defines the score.

### 10.2. Eigenvector Centrality: Important by Connecting to Important Nodes

Eigenvector centrality assigns scores based on the idea that **high-scoring neighbors contribute more**. Unlike PageRank, its formulation and normalization rely on an eigenvector problem of the adjacency matrix without the same teleportation mechanism to handle every directed network structure.

In certain directed, fragmented, or disconnected graphs, eigenvector stability and interpretability can differ markedly from PageRank. Use PageRank when you want an interpretable score-propagation mechanism with damping/teleportation; consider eigenvector when your network model and mathematical assumptions fit.

If your GDS version provides an eigenvector procedure, you can run it on the same projection and compare rankings. Check the actual algorithm catalog rather than assuming every GDS release includes identical procedures.

### 10.3. Degree Centrality: A Very Useful Baseline

For small graphs or requirements needing only follower counts, **in-degree via Cypher** may suffice and be far simpler to explain than PageRank. Never deploy GDS pipelines, caches, and recompute schedules if the business KPI literally only asks "how many distinct accounts follow this person."

On large graphs, comparing top PageRank against top in-degree also helps verify whether the algorithm captures the intended phenomenon or is being skewed by anomalous link clusters.

## 11. Writing Scores to Neo4j or Reading Only?

GDS provides execution modes such as **stream** (return rows), **stats** (summary statistics), and **write/mutate** modes depending on the algorithm. For reporting or one-off exploration, `stream` is usually the simplest option.

If an application needs repeated low-latency API lookups for top accounts, scores can be persisted after batch computation. Before persisting, define:

- Property name, e.g., `pageRankScore`.
- Which projection was used and the data timestamp it captured.
- Damping factor, weight, and iteration settings.
- Computation timestamp and algorithm version.
- When scores expire and must be recomputed.

With GDS 2.x, you can use write mode:

~~~cypher
CALL gds.pageRank.write(
  'influenceDemoGraph',
  { writeProperty: 'pageRankScore' }
)
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

**Warning:** This operation **writes properties into the database** on projected nodes. Use only in a practice database or an approved pipeline with an explicit update strategy. When re-running with different settings, existing `pageRankScore` values may be overwritten; reading applications must be aware of data versions.

### 11.1. Scores Are Point-in-Time Snapshots

If the graph changes after computation, stored PageRank properties **do not auto-update** just because new relationships arrive. When using PageRank in production, establish a recompute schedule:

- Daily/hourly when the graph evolves moderately.
- After a batch data import completes.
- Once change volume crosses a threshold.
- Over a graph filtered to a specific time window.

Never promise full PageRank recomputation after every single relationship write without measuring the cost.

### 11.2. Do Not Treat Scores from Two Different Projections as the Same Scale

If one projection has 100,000 nodes and another has only 1,000, or two runs use different weights/damping factors, raw scores cannot be compared unconditionally. If cross-group rankings are needed, define how to **normalize and compare within a consistent context**.

## 12. PageRank on Graphs with Multiple Relationship Types

A social graph might store:

~~~text
(:Person)-[:FOLLOWS]->(:Person)
(:Person)-[:MENTIONS]->(:Person)
(:Person)-[:WORKS_WITH]->(:Person)
(:Person)-[:BLOCKS]->(:Person)
~~~

Do not project **all relationship types** and run PageRank without considering semantics:

- `FOLLOWS` may signal interest.
- `MENTIONS` could be positive citation or criticism.
- `WORKS_WITH` is typically symmetric in meaning even if stored with a conventional direction.
- `BLOCKS` should never be interpreted as a "vote of confidence."

Mixing negative edges into positive PageRank could boost the score of an account blocked by many users under a distorted definition. First choose meaningful edge types, decide direction, and then consider weights.

### 12.1. Combining with Community Detection

Global PageRank can favor nodes in massive communities. When an application needs to recommend influencers **within each community or topic**, you can partition the graph and compare centrality within the appropriate scope.

A **global top PageRank** result may miss someone highly influential inside a smaller niche community. Clearly state the measurement scope when presenting rankings.

### 12.2. Filtering the Graph by Time

In follow networks, edges created years ago may no longer reflect active engagement. If the business cares about influence over the "last 30 days," model or filter data for that time window prior to projection.

However, `FOLLOWS` often stores only the start time, not ongoing activity levels. Measuring recent influence may require event-based edges (such as interactions), alongside anti-spam rules, retention windows, and weight aggregation logic.

## 13. Checking Data Quality Before Computing Centrality

An algorithm can complete cleanly on **bad data**, producing rankings that look plausible yet hold no real value.

### 13.1. Checking Duplicate Keys and Parallel Edges

~~~cypher
MATCH (u:InfluenceDemoUser)
WITH u.handle AS handle, count(u) AS n
WHERE n > 1
RETURN handle, n;
~~~

If multiple nodes share the same `handle`, "one person's influence" is fragmented across multiple entities.

Count duplicate `FOLLOWS` edge pairs:

~~~cypher
MATCH (a:InfluenceDemoUser)-[r:FOLLOWS]->(b:InfluenceDemoUser)
WITH a.handle AS follower,
     b.handle AS followed,
     count(r) AS relationships
WHERE relationships > 1
RETURN follower, followed, relationships
ORDER BY relationships DESC;
~~~

If the model allows at most one `FOLLOWS` per pair, duplicate edges are a data defect to fix. For algorithms, parallel edges can alter total weights or contributions, so duplicate ingestion cannot be treated as harmless.

### 13.2. Distinguishing Multiple Accounts from Real People

One individual may own multiple accounts; fake accounts can form anomalous follow clusters. PageRank operates on **the actual projected nodes**, not inferred real-world identities.

When ranking users, include steps to verify trustworthy data, curb spam/bots, and assess the impact of missing data. That is part of data modeling quality, not tweaking the PageRank formula.

### 13.3. Checking Isolated Nodes and Dangling Nodes

~~~cypher
MATCH (u:InfluenceDemoUser)
WHERE NOT EXISTS {
    MATCH (u)-[:FOLLOWS]->(:InfluenceDemoUser)
}
RETURN u.handle AS handle;
~~~

This query finds nodes **with no outgoing `FOLLOWS` edge within the demo label scope**. For PageRank, these are dangling nodes. They differ from **isolated nodes** (which have neither incoming nor outgoing edges).

Neo4j/GDS handles these nodes internally within the algorithm, yet they still influence scores and interpretation. A projection that drops relationships due to misconfigured label filters can unintentionally create many spurious dangling nodes.

## 14. Using the Java Driver to Fetch Rankings

An API can read PageRank via GDS `stream` and return only the required fields to the frontend. Illustrative Java Driver example:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class InfluenceQueryService {
    public record InfluenceScore(String handle, double score) {}

    private final Driver driver;

    public InfluenceQueryService(Driver driver) {
        this.driver = driver;
    }

    public List<InfluenceScore> topInfluencers(
            String graphName, int requestedLimit) {
        if (graphName == null || graphName.isBlank()) {
            throw new IllegalArgumentException("graphName is required");
        }
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        String cypher = """
            CALL gds.pageRank.stream(
                $graphName,
                { dampingFactor: $damping, maxIterations: $iterations }
            )
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).handle AS handle, score
            ORDER BY score DESC, handle ASC
            LIMIT $limit
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "graphName", graphName,
                    "damping", 0.85,
                    "iterations", 40,
                    "limit", limit
                )).list(row -> new InfluenceScore(
                    row.get("handle").asString(),
                    row.get("score").asDouble()
                ))
            );
        }
    }
}
~~~

Usage preconditions:

- Named graph `graphName` already exists in the GDS catalog accessible by the session.
- The GDS procedure exists, is permitted, and supports the supplied config.
- Projected nodes have a non-null `handle` property; otherwise the mapper must handle missing values.
- `session.executeRead` fits this read-only `stream` example. If switching to write mode, use appropriate transactions and write permissions.
- `Driver` should be reused at application scope; `Session` is short-lived.
- `limit` bounds **returned rows**, not the number of nodes PageRank computes over. The algorithm still processes the full graph projection per its configuration.

With **Spring Data Neo4j**, you can use `Neo4jClient` with a custom query and DTO mapping if an API needs rankings. You do not need to hydrate full aggregate entities and relationships just to return top scores. When reading previously persisted scores, queries can use `MATCH ... RETURN` rather than re-running the algorithm on every HTTP request.

## 15. Performance and Operating Centrality Pipelines

### 15.1. GDS Is Not a Lightweight Cypher Count

On a few nodes, algorithms run effortlessly. With millions of nodes and relationships, GDS requires resources to:

1. **Read and project** nodes/relationships from Neo4j into an in-memory graph.
2. **Execute multiple iterations** propagating PageRank across links.
3. **Stream or write** score outputs.
4. **Drop the projection** when no longer needed.

Memory cost generally scales with node/edge counts and projected properties; execution time also depends on configuration, iteration count, and graph complexity. Never deduce fixed RAM or runtime figures from node count alone.

### 15.2. Using Memory and Resource Checks

Some GDS procedures provide an **estimate** mode to preview memory before running; syntax and output vary by version. Before production jobs, verify estimate support in your deployed version and monitor RAM, CPU load, and the graph catalog.

Project only **labels, relationship types, and properties** strictly needed. For unweighted PageRank, if no edge property is used, avoid loading bulky string or unrelated properties unnecessarily.

### 15.3. Choosing an Appropriate Compute Schedule

| Need | Reference Strategy |
|---|---|
| One-off analysis | Projection → stream → export report → drop |
| Daily updated dashboard | Scheduled batch computation; persist scores with timestamps |
| Low-latency API | Read precomputed scores instead of running whole-graph algorithms per request |
| Continuously updated graph | Balance refresh cadence against acceptable score staleness |
| Large graph with multiple communities | Choose appropriate subgraphs/algorithms; check cost and bias |

No single recompute schedule fits all applications. **PageRank reflects the graph state at computation time**; displaying scores without timestamp and scope context can mislead users.

### 15.4. Measuring Stability Rather Than Looking Only at Top 1

When adjusting damping or relationship filters, compare:

- Overlap ratio in **top 10 / top 100**.
- Rank volatility across runs.
- Sensitivity to removing suspicious accounts or duplicate edges.
- Divergence between PageRank and in-degree.
- Explainability of nodes rising or falling in rank.

If top rankings swing wildly due to a few new edges, investigate whether it is a genuine business signal or missing/corrupted data.

## 16. Common Misconceptions

**"PageRank is just counting followers."** False. It distributes score from linking sources based on network structure and damping; in-degree merely counts direct edges.

**"Having lots of outgoing edges yields high PageRank."** Incorrect under the follower-to-followed `FOLLOWS` convention. Outgoing edges distribute a source node's score to others; edge direction must be respected.

**"A high score means the user produces high-quality content."** False. Scores do not verify quality, authenticity, or ethical behavior.

**"GDS is built into every Neo4j database."** Never assume so. GDS is a separate library requiring installation and permissions per environment and version.

**"`PageRank.stream` automatically saves scores to nodes."** No. Stream only returns results. Persisting properties requires an intentional write operation with proper permissions and impact review.

**"Adding `LIMIT 10` makes the algorithm process only 10 nodes."** No. `LIMIT` caps output rows after computation; GDS still processes the projected graph to compute scores.

**"Adding reverse `FOLLOWS` edges makes computation faster."** Baseless. Reversing or adding edges alters the data and metric semantics; to analyze reverse direction, configure projection orientation intentionally.

**"We can mix `FOLLOWS`, `BLOCKS`, and `MENTIONS` and let PageRank measure trust."** Inaccurate. Each relationship type carries distinct semantics; filter and define them before computing.

**"Scores from two different graphs can always be compared directly."** False. Graph scope, normalization, parameters, and computation rules alter score meaning.

**"Re-running PageRank automatically updates yesterday's stored property."** No. You need a controlled write job or pipeline mechanism to update stored scores.

## 17. Practice Exercises and Self-Check Questions

### Exercise 1. Choosing the Right `FOLLOWS` Direction

Node A follows B. You want PageRank to favor nodes **followed by** many important accounts.

**Question:** Which edge direction should you choose?

**Hint:** `(A)-[:FOLLOWS]->(B)` projected in natural orientation. A's score can propagate along A → B.

### Exercise 2. Are In-Degree and PageRank the Same?

Node P is followed by 30 weakly connected accounts; node Q is followed by 4 prominent accounts.

**Question:** Since P has a higher in-degree, can you conclude P also has a higher PageRank?

**Answer:** No. PageRank also accounts for link structure and how much score each source distributes across its outgoing edges. You must compute it over the full graph.

### Exercise 3. Detecting a Bridge

You have two groups that rarely interact, connected only by one intermediary node lying on paths between them.

**Question:** Which is best suited to measure the "bridge" role: degree, PageRank, or betweenness?

**Answer:** **Betweenness centrality** is the most direct measure for lying on shortest paths; then verify path semantics and graph directionality.

### Exercise 4. Meaning of Edge Weights

Lan has two outgoing edges: Lan → Minh with strength 3, and Lan → Vy with strength 1.

**Question:** Under a weighted probabilistic interpretation, how is Lan's outgoing contribution split?

**Answer:** **3/4** toward Minh and **1/4** toward Vy (prior to other algorithm terms). This is the split across Lan's outgoing edges, not the entirety of Minh's or Vy's PageRank.

### Exercise 5. Nodes with No Outgoing Edges

A node follows no one yet is followed by many other accounts.

**Question:** Can that node be ignored when computing PageRank because out-degree = 0?

**Answer:** No. It can still receive score from incoming edges; the algorithm handles dangling nodes according to appropriate rules.

### Exercise 6. Graph Projection and Data Persistence

You run `gds.pageRank.stream` and observe scores, but afterward `MATCH (u) RETURN u.pageRankScore` shows the property does not exist.

**Question:** Why?

**Answer:** Stream only returns score rows without writing properties. You must explicitly persist via write mode or an appropriate pipeline to query the property later.

### Exercise 7. API Returning Top 10

An endpoint calls GDS `stream` followed by `LIMIT 10`.

**Question:** Has the algorithm been optimized to process only 10 nodes?

**Answer:** Not yet. `LIMIT` only caps returned rows; GDS still processes the projected graph needed to compute scores.

### Exercise 8. Anomalous Ranking Spike

A brand-new account receives 20,000 `FOLLOWS` edges within minutes and climbs into the PageRank top ranks.

**Question:** Can you conclude this user has high genuine influence?

**Hint:** Check for bots/spam, newly created accounts, duplicate edges, weights, observation windows, and data quality before interpreting scores.

## 18. Key Takeaways

**Degree** answers "how many direct links?", **PageRank** answers "how much distributed importance flows to a node via links?", **betweenness** answers "who lies on many shortest paths?", and **closeness** captures network reachability via distance. They measure **different structural roles** and cannot substitute for one another arbitrarily.

To apply PageRank in Neo4j, define **relationship types and direction** according to business semantics, verify keys and duplicates, build a **GDS named graph projection**, run `gds.pageRank.stream` with explicit settings, compare against baseline metrics, and persist scores only when operationally needed. Scores are meaningful only within the scope, dataset, and point in time they were computed; data quality validation and careful interpretation matter just as much as the Cypher statement itself.
