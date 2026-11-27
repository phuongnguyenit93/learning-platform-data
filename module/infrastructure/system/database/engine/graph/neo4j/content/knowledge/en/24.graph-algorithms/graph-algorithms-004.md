# Stream, Stats, Mutate, and Write Algorithm Modes When Supported

When analyzing a graph in Neo4j, we may want to **inspect ranking scores per node**, **view aggregate statistics**, **use results as inputs to the next algorithm**, or **persist results for long-term application reads**. The same algorithm can serve these goals through different **execution modes**: `stream`, `stats`, `mutate`, and `write`.

This lesson belongs to the **Graph Algorithms** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module covers property graphs, Cypher, indexes/constraints, Java Driver, Spring Data Neo4j, and Neo4j operational techniques. In the algorithms section, you must distinguish **Neo4j Database** (the source data, persistently stored) from **Neo4j Graph Data Science – GDS** (the algorithm library and in-memory projected graphs). Choosing a mode determines **where results are returned, whether they are persisted, and what impact they have on the system**.

> **Scope:** The `gds.*` procedures in this lesson require a compatible **Graph Data Science** installation with proper permissions and resources. GDS is a separate library, not bundled by default in every Neo4j distribution. Support for individual modes, options, and `YIELD` fields **depends on the algorithm and GDS version**. The examples use PageRank because it supports all four modes in current GDS documentation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the flow **Neo4j Database → GDS named graph → algorithm → results**.
2. Accurately distinguish the four modes: `stream`, `stats`, `mutate`, and `write`.
3. Run the same PageRank algorithm across all four modes and verify where results are stored.
4. Explain why `mutate` does not update source data, and why `write` does not auto-sync an already projected named graph.
5. Check which modes an algorithm supports before invoking a procedure.
6. Select the right mode for ad-hoc analysis, multi-algorithm pipelines, and Java/Spring Data Neo4j applications.

## 2. Two Graph Layers to Distinguish

In Neo4j Database, nodes and relationships are stored as real data objects. A Cypher query like `MATCH (p:Person)-[:FOLLOWS]->(other)` queries those objects directly.

Most GDS algorithms execute on a **named graph** that has been **projected** from the database into memory and managed in the **GDS Graph Catalog**. A named graph selects the labels, relationship types, and properties required by the algorithm. It generally reflects data at projection time, **not an automatically updating live copy** as the database changes.

~~~mermaid
flowchart TD
    DB["Neo4j Database<br/>persistent nodes, relationships, properties"]
    P["Graph projection"]
    G["GDS named graph<br/>in memory / Graph Catalog"]
    A["PageRank algorithm"]
    S["stream: multiple score rows"]
    T["stats: single statistics row"]
    M["mutate: add property to named graph"]
    W["write: write property to Neo4j Database"]
    DB --> P --> G --> A
    A --> S
    A --> T
    A --> M --> G
    A --> W --> DB
~~~

The mode name **does not indicate algorithm accuracy**. All four modes execute the computation according to the algorithm configuration; the core difference is **how results are emitted and stored**.

## 3. Quick Comparison of the Four Modes

| Mode | Direct Output | Modifies GDS Named Graph? | Writes to Neo4j Database? | Common Purpose |
|---|---|---|---|---|
| `stream` | Multiple rows, typically `nodeId`/`score` or node pairs | No | No | Viewing and processing results via Cypher/applications |
| `stats` | **One row** of statistics, such as score distribution and compute time | No | No | Evaluating distributions, checking configuration or performance |
| `mutate` | **One row** of statistics; results added to named graph | **Yes** | No | Chaining multiple algorithms within GDS |
| `write` | **One row** of statistics; results written to database | Does not auto-update projections | **Yes** | Persisting scores/relationship labels for long-term application queries |

**Note:** Each algorithm may expose only **a subset of modes**. For node-scoring algorithms like PageRank, `mutate`/`write` typically write a **node property**; for similarity algorithms, they may write **relationships** or relationship properties. Consult the specific algorithm's documentation rather than assuming from PageRank that every algorithm yields `nodeId, score` or accepts `mutateProperty`/`writeProperty`.

A helpful mnemonic:

- **`stream`:** "Show me the result for each element."
- **`stats`:** "Give me the high-level summary."
- **`mutate`:** "Put the result into the GDS graph for further processing."
- **`write`:** "Save the result back to Neo4j Database for queries and applications."

## 4. Preparing the Environment and Practice Graph

### 4.1. Verifying GDS Installation

In Neo4j Browser or a Cypher client, check:

~~~cypher
RETURN gds.version() AS gdsVersion;
~~~

To see the exact PageRank modes available on the current DBMS:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'gds.pageRank.'
RETURN name
ORDER BY name;
~~~

If GDS is not installed, procedure permissions are missing, or versions are incompatible, `gds.*` calls will fail. Do not alter application account privileges or deploy plugins without authorization; use an appropriately permitted practice GDS environment.

### 4.2. Creating Small, Verifiable Sample Data

To avoid colliding with operational data, the example uses a dedicated label `ModePerson` and runs in a **test database**. All relationships are directed.

~~~cypher
CREATE CONSTRAINT mode_person_id_unique IF NOT EXISTS
FOR (p:ModePerson)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
MERGE (a:ModePerson {personId: 'A'})
MERGE (b:ModePerson {personId: 'B'})
MERGE (c:ModePerson {personId: 'C'})
MERGE (d:ModePerson {personId: 'D'})
MERGE (e:ModePerson {personId: 'E'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (a)-[:FOLLOWS]->(c)
MERGE (b)-[:FOLLOWS]->(c)
MERGE (c)-[:FOLLOWS]->(a)
MERGE (c)-[:FOLLOWS]->(d)
MERGE (d)-[:FOLLOWS]->(c)
MERGE (e)-[:FOLLOWS]->(d);
~~~

~~~mermaid
flowchart LR
    A((A)) -->|FOLLOWS| B((B))
    A --> C((C))
    B --> C
    C --> A
    C --> D((D))
    D --> C
    E((E)) --> D
~~~

The diagram is only for visualization; **the edge list defines the sample graph**. If you run extra statements outside this lesson, inspect the graph again before reasoning about rankings.

Verify source data:

~~~cypher
MATCH (p:ModePerson)
WITH count(p) AS nodes
MATCH (:ModePerson)-[r:FOLLOWS]->(:ModePerson)
RETURN nodes, count(r) AS relationships;
// On a clean practice database with sample data only: nodes = 5, relationships = 7
~~~

### 4.3. Projecting a GDS Named Graph

~~~cypher
CALL gds.graph.project(
    'modeLessonGraph',
    'ModePerson',
    'FOLLOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

With the sample data, `nodeCount = 5` and `relationshipCount = 7`. The syntax above is a simple **native projection**: selecting nodes by label and relationships by type; in real workloads you can use **Cypher projection** to define datasets more flexibly.

The graph named `modeLessonGraph` resides in GDS memory. If the same name already exists in the catalog, a new projection will fail; check first:

~~~cypher
CALL gds.graph.list('modeLessonGraph')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

In this practice exercise, create the projection **once** and reuse the same name in subsequent steps. There is no need to re-project before **each** mode call unless intentionally refreshing input data or clearing `mutate` properties.

## 5. `stream` — Viewing Detailed Results Without Writing Data

`stream` returns results directly to Cypher as **rows**. For PageRank, each node has a `nodeId` and a `score`. `gds.util.asNode(nodeId)` accesses the original database node to retrieve readable keys.

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId,
       score
ORDER BY score DESC, personId ASC;
~~~

The output contains **at most five node rows** in the sample graph. The scores come from PageRank computation; do not assume fixed numbers without executing the query, as values depend on configuration, convergence, and GDS version.

`stream` is suitable when:

- You need the **top N** important nodes for display or immediate analysis.
- You want to join results with other Neo4j properties for reporting.
- You need to inspect data quality and rankings **before deciding to persist**.
- A Java Driver application only needs to read results without modifying the graph.

Example retrieving the top three users by score:

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId ASC
LIMIT 3;
~~~

**Common pitfall:** `LIMIT 3` restricts **the number of returned rows after computation**; it does not make PageRank process only three nodes. The algorithm still runs across the selected graph. On large graphs, streaming all rows over the network can consume client RAM and bandwidth; select only needed columns, paginate, or consider other modes depending on business needs.

`stream` creates no new properties on source nodes. After running `stream`, `MATCH (p:ModePerson) RETURN p.pageRankScore` will not show PageRank scores unless that property was already written by a prior operation.

## 6. `stats` — Reading Aggregate Algorithm Statistics

`stats` also **runs the computation**, but instead of returning one row per node, it returns **a single statistics row**. Fields may include score distributions, iteration count, convergence status, and compute time, depending on the algorithm.

~~~cypher
CALL gds.pageRank.stats('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20
})
YIELD ranIterations, didConverge, computeMillis, centralityDistribution
RETURN ranIterations,
       didConverge,
       computeMillis,
       centralityDistribution.min AS minScore,
       centralityDistribution.max AS maxScore;
~~~

Meaning of some PageRank fields:

| Field | Interpretation |
|---|---|
| `ranIterations` | Number of iterations executed in this call |
| `didConverge` | Whether the algorithm reached the configured convergence criterion |
| `computeMillis` | Time spent in the computation phase reported by the procedure; not necessarily equal to end-to-end latency |
| `centralityDistribution` | Centrality score distribution metrics, such as min/max and other supported statistics |

`stats` **does not return** a `personId → score` table and **does not write** properties to either the named graph or Neo4j Database. To look up a specific node's score, use `stream`, `mutate`, or `write` depending on where results are consumed.

**Do not mistake `stats` for a cheap metadata-only command:** it may still run the full algorithm to compute statistics. On large graphs, `stats` still consumes CPU and memory.

### Using `stats` to Test Configurations

For example, re-run with a different `maxIterations`, keeping the same named graph:

~~~cypher
CALL gds.pageRank.stats('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 50,
    tolerance: 0.0000001
})
YIELD ranIterations, didConverge, centralityDistribution
RETURN ranIterations, didConverge,
       centralityDistribution.max AS maxScore;
~~~

Changing `maxIterations` or `tolerance` can affect convergence. When comparing modes, use **identical configurations** if you want PageRank scores to be directly comparable.

## 7. `mutate` — Writing Results to the **GDS Named Graph**

`mutate` computes the algorithm and stores results into the **GDS in-memory graph**, typically as a node property named by `mutateProperty`. In the PageRank example:

~~~cypher
CALL gds.pageRank.mutate('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20,
    mutateProperty: 'pageRankMemory'
})
YIELD nodePropertiesWritten, mutateMillis
RETURN nodePropertiesWritten, mutateMillis;
~~~

If all five nodes receive a score, `nodePropertiesWritten` is expected to be **5**. This counts properties written into the **projection**, **not** newly created nodes or properties in Neo4j Database.

To verify the scores added to the named graph:

~~~cypher
CALL gds.graph.nodeProperty.stream(
    'modeLessonGraph',
    'pageRankMemory'
)
YIELD nodeId, propertyValue
RETURN gds.util.asNode(nodeId).personId AS personId,
       propertyValue AS pageRankScore
ORDER BY pageRankScore DESC, personId;
~~~

Meanwhile, querying the database:

~~~cypher
MATCH (p:ModePerson)
RETURN p.personId AS personId,
       p.pageRankMemory AS dbProperty
ORDER BY personId;
~~~

**If nobody previously wrote `pageRankMemory` to the database**, `dbProperty` will be `null`: `mutate` **does not** copy results from GDS memory down to Neo4j Database.

`mutate` is particularly suited for **multi-algorithm pipelines**. For example, run PageRank and then pass `pageRankMemory` as a feature to another GDS algorithm that supports `nodeProperties`/`featureProperties`, without writing intermediate data to the database and re-projecting.

### Important Caveats with `mutate`

1. **The property name must not already exist on the projected graph** for mutate operations per GDS documentation. Re-running the same mode with the same `mutateProperty` can fail; use a different name or explicitly drop/clear old properties/structures in practice.
2. **GDS memory consumption:** the named graph retains the added results; with vector embeddings or multiple chained algorithms, memory growth can be substantial.
3. **Bounded lifetime:** named graphs remain in the Graph Catalog only until dropped, database/DBMS shutdown, or resource reclamation. It is not durable storage replacing Neo4j Database.
4. **No automatic effect on the DB:** standard Cypher queries or Spring Data Neo4j applications reading nodes from the database will not see properties that exist solely in the projection.

## 8. `write` — Persisting Results Back to **Neo4j Database**

`write` computes the algorithm on the named graph and writes results back to the database. For PageRank, specify the target property via `writeProperty`:

~~~cypher
CALL gds.pageRank.write('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20,
    writeProperty: 'pageRankDatabase'
})
YIELD nodePropertiesWritten, writeMillis
RETURN nodePropertiesWritten, writeMillis;
~~~

To confirm data has been **persistently written** to `ModePerson` nodes:

~~~cypher
MATCH (p:ModePerson)
RETURN p.personId AS personId,
       p.pageRankDatabase AS pageRankScore
ORDER BY pageRankScore DESC, personId;
~~~

Unlike `mutate`, the `pageRankDatabase` property now lives on **database nodes**. Regular Cypher queries, the Java Driver, and Spring Data Neo4j can read it according to permissions and application mappings. If a Spring Data Neo4j domain model needs this field on an entity, update the application's mapping/schema intentionally; `write` does not modify Java classes automatically.

### `write` Does Not Auto-Update the Named Graph

After `write`, the `modeLessonGraph` projection may **still lack** the `pageRankDatabase` property because it was created before `write` ran. Consequently:

- `MATCH (p:ModePerson) RETURN p.pageRankDatabase`: reads values from the **database**.
- `CALL gds.graph.nodeProperty.stream('modeLessonGraph', 'pageRankDatabase')`: may report **property not found in projection**.
- If a subsequent GDS algorithm needs `pageRankDatabase` as an in-memory input, you must **re-project** the graph with that property, or use `mutate` inside the pipeline from the start.

**Data overwrite warning:** if `pageRankDatabase` already exists on nodes, `write` overwrites its value with the new output. Pick clear property names, align on refresh workflows, and test on a staging copy before writing in production.

GDS may use **separate transactions** during the write phase; do not assume an entire `write` execution rolls back like a single atomic Cypher update. If an error occurs midway through writing, inspect the final state of target data, your retry policy, and transaction-handling docs for your GDS version.

## 9. Testing the Four Modes in Order

Recommended learning sequence to minimize unintended side effects:

1. **Project the graph:** run `gds.graph.project` and verify node/relationship counts match source data.
2. **`stream`:** inspect node lists and rankings with no graph side effects.
3. **`stats`:** inspect convergence, score distributions, and compute time; validate algorithm parameters.
4. **`mutate`:** store scores into `pageRankMemory` inside the GDS graph and read them via `gds.graph.nodeProperty.stream`.
5. **`write`:** only after confirming requirements, write scores to `pageRankDatabase` on source nodes and verify with `MATCH`.

`stream`, `stats`, `mutate`, and `write` are **separate algorithm executions**. Calling `write` after `mutate` does not mean `write` simply copies previously computed scores; the procedure **re-executes the algorithm** using the supplied configuration. Changing `dampingFactor` or `maxIterations` can produce different scores between steps.

### Step-by-Step Verification

| Point in Time | Named Graph Has `pageRankMemory`? | Database Has `pageRankDatabase`? |
|---|---|---|
| Just projected | No | No, if DB lacked it initially |
| After `stream` | No | No |
| After `stats` | No | No |
| After `mutate` | **Yes** | No |
| After `write` | **Yes** | **Yes** |

This table assumes a first-time run on clean sample data lacking those properties and no external concurrent modifications.

## 10. Which Modes Are Supported? Never Guess from the Algorithm Name

General syntax when a mode is supported:

~~~cypher
CALL gds.<algorithm>.<executionMode>(
    'namedGraph',
    { /* algorithm- and mode-specific configuration */ }
)
YIELD ...;
~~~

This is an **illustrative template**, not a literal Cypher statement to run verbatim. Some algorithms support all four modes, while others support only a subset. Algorithms returning different output types (node scores, community IDs, similarity relationships, paths) have **different `YIELD` fields, data semantics, and `mutate`/`write` configurations**.

When starting with a new algorithm:

1. Open the documentation page for **that exact algorithm**, and check the **Syntax** section and **modes** table.
2. Run **`SHOW PROCEDURES`** on the actual server to confirm which procedure names are loaded.
3. Verify **graph requirements**: directed support, weight property needs, property types, and label/relationship type filtering.
4. Read required mode parameters, such as `mutateProperty` or `writeProperty` for node-scoring algorithms.
5. Check **`YIELD` return fields**. Do not use `YIELD nodeId, score` for an algorithm that only emits relationships or statistics.

Example check for PageRank:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name IN [
    'gds.pageRank.stream',
    'gds.pageRank.stats',
    'gds.pageRank.mutate',
    'gds.pageRank.write'
]
RETURN name
ORDER BY name;
~~~

If a procedure name is missing or the user lacks execute privileges, read the error message and inspect version/permissions and deployment docs. Never arbitrarily swap in a different mode, as **side effects and result types may differ completely**.

## 11. Estimating Memory and Monitoring Time and Progress

Running algorithms on large graphs can demand substantial memory, especially when `mutate` retains results in the projection or `stream` ships many rows over the network. GDS provides `estimate` procedures for supported modes. Example:

~~~cypher
CALL gds.pageRank.write.estimate('modeLessonGraph', {
    writeProperty: 'pageRankDatabase',
    maxIterations: 20,
    dampingFactor: 0.85
})
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

`estimate` previews memory requirements before running; it **does not execute PageRank or write scores**. Estimates are capacity-planning aids, not substitutes for monitoring actual RAM, CPU, runtime, and write-load impact.

For PageRank:

| Metric | Where to Read | Meaning and Limitations |
|---|---|---|
| `computeMillis` | `stats`/`mutate`/`write` when available | GDS compute phase duration; excludes full network/client overhead |
| `mutateMillis` | `mutate` when available | Duration to update the projection |
| `writeMillis` | `write` when available | Duration to write results to database as reported by the procedure |
| `nodePropertiesWritten` | `mutate`/`write` for PageRank | Count of written result properties; distinguish the **write target** |
| `ranIterations`, `didConverge` | Modes reporting statistics | Iteration count and convergence status for the run configuration |
| Stream row count | `stream` | Number of nodes/pairs/paths in output; not necessarily unique source nodes |

If your library/version exposes `jobId`, `logProgress`, and progress tracking APIs, use them to monitor long-running jobs. Distinguish **algorithm progress**, **write progress**, and **client result-streaming progress**.

## 12. Choosing a Mode by Business Scenario

| Requirement | Initial Choice | Reason |
|---|---|---|
| Test PageRank on a follower graph and return top 10 | `stream` | No writes needed; can filter/sort directly in Cypher |
| Inspect score distribution, convergence, and runtime | `stats` | Compact summary statistics without per-node scores |
| Run PageRank, then feed scores into another GDS algorithm | `mutate` | Keeps results in the named graph for downstream steps |
| Java/Spring Data Neo4j app reads PageRank scores daily via `MATCH` | `write` | Results reside in Neo4j Database for recurring queries |
| Persist results for only a small subset of nodes for reporting | `stream` then selectively write via app/Cypher if appropriate | Avoids writing the entire graph when only few results are needed |
| Run multiple algorithms, persisting only at the end of the pipeline | `mutate` in intermediate steps, then export/write final results | Reduces intermediate DB writes and re-projections |

### Examples with Java Driver and Spring Data Neo4j

- **Java Driver:** can call `gds.pageRank.stream` and read `personId/score` rows from `Result`; at large scale, manage read timeouts, network bandwidth, and client memory.
- **Spring Data Neo4j:** regular domain queries only read properties **already present in Neo4j Database**. If the app needs PageRank scores as entity properties, plan for `write`, write permissions, and entity mapping.
- **Analytical pipelines:** if only GDS consumes the score for a subsequent algorithm, `mutate` avoids writing to the DB and re-projecting; do not persist prematurely just to surface temporary data in Java entities.

Example application query after `write` has executed:

~~~cypher
MATCH (p:ModePerson)
WHERE p.pageRankDatabase IS NOT NULL
RETURN p.personId AS personId, p.pageRankDatabase AS score
ORDER BY score DESC, personId
LIMIT 10;
~~~

For recurring scheduled runs, define **when scores refresh, which algorithm version applies, which property stores them, and whether users can observe partial updates during writes**. These are distinct operational concerns of persistence.

## 13. Common Misconceptions

| Misconception | Reality | How to Handle |
|---|---|---|
| "`stream` only runs on rows after `LIMIT`" | The algorithm can compute across the entire graph; `LIMIT` caps returned rows | Estimate resources on the full projected graph |
| "`stats` quickly fetches stats saved from `stream`" | `stats` executes the algorithm separately | Account for compute cost and match configurations |
| "`mutate` saved to the DB" | It updates the **in-memory named graph** | Read via GDS graph property stream; use `write` if DB persistence is needed |
| "`write` added the property to the projection" | Named graphs do not auto-sync DB writes | Re-project or use `mutate` if continuing in GDS |
| "Every algorithm supports all four modes" | Modes and `YIELD` fields depend on algorithm/version | Check Syntax docs and `SHOW PROCEDURES` |
| "Re-running `mutate` with the same name always works" | The mutate property may already exist and cause an error | Manage property/graph lifecycle or pick a new name |
| "PageRank scores are probabilities summing to 1" | Default GDS PageRank scores are not necessarily normalized to probabilities | Apply scalers or probability interpretation only with proper configuration |
| "`write` is a single atomic transaction" | GDS may use separate transactions in the write phase | Design post-failure verification and retry policies |
| "`MATCH` alone updates scores in GDS memory" | Cypher `MATCH` reads the database, never mutating projections | Use GDS procedures on the appropriate data layer |
| "GDS is always bundled with Neo4j" | GDS is a separate library/deployment capability | Verify installation, version, license, and permissions |

## 14. Practice Exercises and Self-Check Questions

### Exercise 1 — Choosing a Mode

An analytics team wants to compute user communities and pass the community ID as input to the next algorithm, **without writing intermediate properties to the database**. If the community algorithm supports `mutate`, which mode should they choose?

<details>
<summary>Answer</summary>

Choose `mutate`. It writes community IDs into the named graph so downstream GDS algorithms can consume them. Verify that the next algorithm actually supports reading that property and shares the same node/relationship projection definition.

</details>

### Exercise 2 — Reading Results Without Writing

Write a query to retrieve the top three people by PageRank on `modeLessonGraph`, without updating the DB.

<details>
<summary>Reference Answer</summary>

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId ASC
LIMIT 3;
~~~

Use `stream`. `LIMIT 3` only reduces the number of rows returned after computation.

</details>

### Exercise 3 — Distinguishing Memory and Database

After running:

~~~cypher
CALL gds.pageRank.mutate('modeLessonGraph', {
    mutateProperty: 'scoreOnlyInMemory'
})
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

You run `MATCH (p:ModePerson) RETURN p.scoreOnlyInMemory` and see `null`. Did GDS lose the results?

<details>
<summary>Answer</summary>

No—you cannot conclude that. `mutate` writes properties to the projected graph. Verify with `CALL gds.graph.nodeProperty.stream('modeLessonGraph', 'scoreOnlyInMemory') YIELD nodeId, propertyValue RETURN nodeId, propertyValue`. `MATCH` reads from the database and therefore does not see this property.

</details>

### Exercise 4 — Impact of `write`

A PageRank job runs nightly with `writeProperty: 'pageRankDatabase'`. During the day, the application ranks users via `ORDER BY p.pageRankDatabase DESC`. List at least three things to verify before going to production.

<details>
<summary>Suggested Answer</summary>

Check that the graph projection reflects target data; write permissions and risk of overwriting properties; memory and write duration; recovery policy if the job stops mid-write; timing relative to application reads; parameter and algorithm version consistency; and indexes if queries frequently sort on that property. If results must switch atomically across versions, consider writing to a versioned property/dataset and switching application reads in a controlled rollout.

</details>

### Exercise 5 — Summary Statistics

If you only need to check `didConverge` and `centralityDistribution.max` for PageRank, which mode should you choose? Are results automatically saved to the GDS graph or database?

<details>
<summary>Answer</summary>

`stats` is appropriate if that PageRank version supports it and per-node scores are not needed. It returns a single summary row and does not save node scores to either the named graph or the database.

</details>

## 15. Cleaning Up the GDS Graph After Practice

When the named graph is no longer needed in GDS, free memory with:

~~~cypher
CALL gds.graph.drop('modeLessonGraph')
YIELD graphName
RETURN graphName;
~~~

This command **removes the named graph from the GDS Graph Catalog**, along with any properties added via `mutate`. It **does not delete** `ModePerson` nodes or `FOLLOWS` relationships in Neo4j Database, nor does it delete the `pageRankDatabase` property written to the DB via `write`.

Deleting practice data from the database is a **separate write/delete operation**—ensure the database contains no data you need to keep. Catalog cleanup does not replace business data lifecycle management.

## 16. References

- [GDS — Syntax overview and execution modes](https://neo4j.com/docs/graph-data-science/current/algorithms/syntax/)
- [GDS — Running algorithms: stream, stats, mutate, write](https://neo4j.com/docs/graph-data-science/current/common-usage/running-algos/)
- [GDS — PageRank: parameters and examples of all four modes](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)
- [GDS — Creating named graphs in memory](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/)
- [GDS — Streaming mutated properties in projected graphs](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-reads/graph-stream-nodes/)
- [GDS — Transaction handling when writing results](https://neo4j.com/docs/graph-data-science/current/production-deployment/transaction-handling/)

`current` documentation pages evolve with new GDS releases. When applying to a project, verify your installed version, algorithm-specific syntax, and execution permissions in your environment.

## 17. Key Takeaways

- **`stream` returns detailed rows**, ideal for inspecting and processing output without persisting results.
- **`stats` returns a single summary row** while still potentially running the full computation; it does not return per-node scores.
- **`mutate` saves results in the GDS named graph**, useful for algorithm pipelines; it does not update the database.
- **`write` writes to Neo4j Database**, suited for applications consuming results long-term; it does not auto-refresh existing projections.
- **Only use modes supported by the algorithm**, with configuration and `YIELD` matching your GDS version's docs.
- **Evaluate results, resources, and write impact before deploying**, especially on large graphs and operational data.
