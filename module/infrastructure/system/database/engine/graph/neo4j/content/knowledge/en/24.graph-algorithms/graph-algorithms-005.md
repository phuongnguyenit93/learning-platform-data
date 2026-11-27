# Estimating Memory Before Running Algorithms on Large Data in Neo4j

## 1. Why Estimate Memory Before Running Algorithms?

In Neo4j's **property graph**, nodes represent entities, relationships describe connections, and properties store associated data. Standard Cypher queries typically access a localized part of the graph via indexes and traversals. Conversely, many **Graph Data Science (GDS)** algorithms—such as PageRank, Weakly Connected Components (WCC), Louvain, Node Similarity, or path-finding algorithms—must process a large portion of the connection structure in memory.

For example, a partner recommendation system has tens of millions of `Company` nodes and hundreds of millions of `TRADES_WITH` relationships. Running PageRank directly under the assumption that "the server has 16 GiB of RAM left, so it should be fine" can cause the job to be rejected before starting, put pressure on the JVM heap, or fail mid-execution. Such failures also impact Cypher, Java Driver, and Spring Data Neo4j transactions sharing the same Neo4j DBMS.

**This lesson in the "Graph Algorithms" chapter focuses on memory budgeting across the entire GDS lifecycle:**

1. Counting and **estimating the portion of the graph loaded into memory** (*projection*).
2. Estimating **algorithm-specific memory** by execution mode and configuration.
3. Accounting for existing heap occupants: the graph catalog, Neo4j, transactions, and other GDS jobs.
4. Scoping down, tuning settings, piloting, and monitoring before processing large datasets.
5. Reclaiming unused graphs/properties to free resources.

> **Scope:** Examples use current Neo4j Graph Data Science (GDS) 2.x. A compatible GDS installation and proper permissions are required. `gds.*` belongs to the **Graph Data Science** plugin/product API—not built-in Cypher, Neo4j APOC, or capabilities automatically gained by adding the Java Driver.

## 2. Distinguishing Three Memory Regions and Two Execution Phases

GDS uses the **JVM heap** to store projected graphs and algorithm computational state. This heap memory is separate from the **Neo4j page cache** used for database store access and other native/off-heap regions. Each region plays a distinct role.

| Component | What Does It Hold? | When Does It Occupy Memory? |
| --- | --- | --- |
| **GDS graph catalog** | Node IDs, topology/adjacency, relationships, projected numeric properties, `mutate` result properties | From named graph creation until `gds.graph.drop` or catalog lifecycle end |
| **GDS algorithm state** | PageRank score arrays, component labels, community structures, queues/working sets, per-worker buffers | While the algorithm executes; depends on algorithm, mode, graph, and configuration |
| **Other JVM workloads** | Transaction state, Cypher query memory, DBMS runtime, other GDS graphs/jobs, GC overhead | May coexist concurrently with GDS jobs |
| **Page cache** | Cached Neo4j data pages for reads/writes | Based on DBMS configuration and query, projection, and write-back activity |
| **Native/off-heap & OS** | Non-heap JVM memory, thread stacks, Arrow (if enabled), OS, and other processes | Depends on technology stack and deployment environment |

Two GDS operations commonly occur sequentially:

```text
             Neo4j database (nodes + relationships)
                           |
           [1] graph projection, consumes memory at creation
                           |
                           v
              GDS graph catalog on the heap
                           |
           [2] PageRank / WCC / Louvain / ...
                           |
                  Temporary working memory
                           |
          +----------------+----------------+
          |                |                |
        stream           mutate            write
   returns results    saves results to  writes results to
  to client/Cypher       GDS graph        Neo4j database
```

**Do not confuse "graph currently occupying heap" with "additional memory needed while the algorithm runs."** If a 7 GiB graph is already projected and an algorithm needs an extra 3 GiB, both may coexist simultaneously. If using a combined projection-and-execution estimation mode, check the estimate semantics to **avoid double-counting**.

### Factors That Inflate Projected Graph Memory

- **Node count** and relationship count **after projection**, not always the entire database total.
- **Relationship orientation:** when choosing `UNDIRECTED`, GDS stores connections in both directions; memory demands differ from `NATURAL`.
- **Loaded properties:** weights, scores, or multiple numeric columns on nodes/relationships increase memory footprint.
- **Graph representation, degree distribution, and compression**; there is no universal "every node always costs X bytes" rule for all graphs.
- **`mutate` results** retained in the graph catalog and other un-dropped graphs.

## 3. The `.estimate` API: Reading Output Fields Correctly

GDS provides **estimation** modes when invoking procedures that support `.estimate`. For algorithms, the general syntax is:

```cypher
CALL gds.<algorithm>.<executionMode>.estimate(
  'graphName',
  {concurrency: 4 /* and algorithm-specific parameters */}
)
YIELD nodeCount, relationshipCount,
      requiredMemory, bytesMin, bytesMax,
      heapPercentageMin, heapPercentageMax,
      treeView, mapView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax,
       heapPercentageMin, heapPercentageMax,
       treeView, mapView;
```

The snippet above is a **syntax template**, not a literal runnable query—`<algorithm>` and `<executionMode>` must be replaced with actual names, such as `gds.pageRank.stream.estimate`.

| Field | How to Read It | Limitations to Remember |
| --- | --- | --- |
| `nodeCount` | Nodes in the estimated or projected graph | May differ from total nodes in the entire database |
| `relationshipCount` | Corresponding relationships in the GDS graph | Orientation/projection/filters can alter the count of structures processed |
| `requiredMemory` | Human-readable range of estimated memory | Good for display; do not parse for arithmetic |
| `bytesMin` | Lower bound of estimated memory in bytes | Not current free heap |
| `bytesMax` | Upper bound of estimated memory in bytes | Not an ironclad guarantee that usage cannot exceed it |
| `heapPercentageMin`, `heapPercentageMax` | Ratio against **configured maximum JVM heap** | Not a percentage of host physical RAM or free heap |
| `treeView` | Text tree breaking down estimated components | Useful for identifying the largest memory consumers |
| `mapView` | Detailed breakdown structure as a map | Suitable for programmatic handling; check structure per version |

**Use `bytesMax` as a conservative planning input**, then add concurrent heap occupants and suitable headroom. Never conclude "`bytesMax = 8 GiB`, so a machine with exactly 8 GiB RAM is enough."

### Important Limitations of `.estimate`

- It **does not execute the actual algorithm** and cannot predict exact completion time.
- It models memory from graph metadata and algorithmic structures; data skew, runtime state, or concurrent workloads can still introduce variance.
- For graph projection estimates, the estimator may need to fetch node/relationship counts from the database; complex projections may execute counting queries and are **not necessarily zero-cost**.
- Algorithms in the **production-ready tier** are guaranteed to support `.estimate`; do not assume all experimental/alpha algorithms do.
- Parameters passed to `.estimate` must **match the real execution**, especially mode, relationship orientation, weights, `concurrency`, and parameters affecting output size.

## 4. Estimating Memory *Before Creating a Graph Projection*

### 4.1. Estimating from Existing Labels/Types

Native projection estimate syntax:

```cypher
CALL gds.graph.project.estimate(
  'Person',
  'KNOWS',
  {readConcurrency: 4}
)
YIELD nodeCount, relationshipCount, requiredMemory,
      bytesMin, bytesMax, treeView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax, treeView;
```

GDS estimates a graph of `Person` nodes and `KNOWS` relationships under the specified configuration. This command **does not create a named graph** and retains no persistent projection in the catalog.

If the actual problem only needs active companies, do not project the entire `Company` label expecting the algorithm to ignore inactive ones automatically. Define the exact projection/filter for the task and evaluate cost on the target subset.

### 4.2. Hypothetical Capacity Estimation Before Data Ingestion

Suppose a design anticipates **10 million nodes** and **80 million relationships**. You can run a hypothetical capacity estimate before ingesting data:

```cypher
CALL gds.graph.project.estimate(
  '*',
  '*',
  {
    nodeCount: 10000000,
    relationshipCount: 80000000
  }
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory;
```

In this mode, `'*'` merely acts as valid projection syntax; `nodeCount` and `relationshipCount` are **supplied as hypothetical parameters**, not reflecting existing database counts. Output depends on the GDS engine, configuration, and graph structure, so **do not invent a fixed GiB figure** for a 10M/80M scenario.

Hypothetical estimation helps during infrastructure sizing, but you must re-estimate against the real graph/projection once data is loaded. If the graph needs weights, labels, or properties, include them in the estimate configuration where supported by version/syntax; do not rely solely on node and relationship counts to determine total cost.

### 4.3. Footprint Also Depends on Relationship Orientation

Example native projection estimate with undirected orientation:

```cypher
CALL gds.graph.project.estimate(
  'Person',
  {
    KNOWS: {
      type: 'KNOWS',
      orientation: 'UNDIRECTED'
    }
  },
  {readConcurrency: 4}
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory;
```

One source relationship can be represented in both directions when projecting `UNDIRECTED`. Therefore, do not take the count from `MATCH ()-[r:KNOWS]->() RETURN count(r)` and multiply by a constant "bytes-per-relationship factor." Always estimate using the **exact projection configuration** the algorithm will run against.

## 5. Hands-On Example: Creating a Small Graph to Verify the Workflow

The following examples use dedicated label/type `GdsDemoPerson` and `GDS_LINK` in a **test database**. Using `MERGE` on keys enables repeatable execution without duplicating nodes or parallel relationships.

### 5.1. Creating Sample Data

```cypher
UNWIND [
  {id: 'u1', name: 'An'},
  {id: 'u2', name: 'Bình'},
  {id: 'u3', name: 'Chi'},
  {id: 'u4', name: 'Dũng'}
] AS row
MERGE (p:GdsDemoPerson {id: row.id})
SET p.name = row.name;
```

```cypher
UNWIND [
  {from: 'u1', to: 'u2'},
  {from: 'u2', to: 'u3'},
  {from: 'u3', to: 'u1'},
  {from: 'u3', to: 'u4'},
  {from: 'u4', to: 'u2'}
] AS row
MATCH (a:GdsDemoPerson {id: row.from})
MATCH (b:GdsDemoPerson {id: row.to})
MERGE (a)-[:GDS_LINK]->(b);
```

The sample graph has 4 nodes and 5 directed relationships. If the database already holds data with matching labels/keys, counts will differ; run only in an isolated test scope.

### 5.2. Estimating the Projection First

```cypher
CALL gds.graph.project.estimate(
  'GdsDemoPerson',
  'GDS_LINK',
  {readConcurrency: 2}
)
YIELD nodeCount, relationshipCount,
      requiredMemory, bytesMin, bytesMax, treeView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax, treeView;
```

Record the output. On a tiny demo set, fixed overhead can dominate; **never take bytes-per-node from a 4-node graph and extrapolate linearly to 40 million nodes**.

### 5.3. Creating the Named Graph in the GDS Catalog

After verifying the projection is appropriate, execute:

```cypher
CALL gds.graph.project(
  'gdsDemoGraph',
  'GdsDemoPerson',
  'GDS_LINK'
)
YIELD graphName, nodeCount, relationshipCount, projectMillis
RETURN graphName, nodeCount, relationshipCount, projectMillis;
```

`gdsDemoGraph` resides in the **GDS graph catalog**, occupying JVM heap. Creating this graph does not alter nodes or relationships in the Neo4j database.

Inspect the graph held in heap:

```cypher
CALL gds.graph.list('gdsDemoGraph')
YIELD graphName, nodeCount, relationshipCount,
      sizeInBytes, memoryUsage
RETURN graphName, nodeCount, relationshipCount,
       sizeInBytes, memoryUsage;
```

`sizeInBytes` and `memoryUsage` report the projected graph size **when the runtime/JDK supports object size measurement**; they can be `-1` or `null` on unsupported JDKs. Never interpret missing values as the graph using 0 bytes.

### 5.4. Estimating PageRank Before Running

Use the exact same mode and parameters as the planned run:

```cypher
CALL gds.pageRank.stream.estimate(
  'gdsDemoGraph',
  {
    concurrency: 2,
    maxIterations: 20,
    dampingFactor: 0.85
  }
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory,
      heapPercentageMax, treeView
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory,
       heapPercentageMax, treeView;
```

This estimates **the PageRank computation on the existing graph**. To decide whether heap is sufficient, also account for memory already held by `gdsDemoGraph`, other graphs, and concurrent workloads.

If the estimate is acceptable and **only when ready to execute the test run**, run:

```cypher
CALL gds.pageRank.stream(
  'gdsDemoGraph',
  {
    concurrency: 2,
    maxIterations: 20,
    dampingFactor: 0.85
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS personId, score
ORDER BY score DESC;
```

Every PageRank score reflects the **projected graph** and does not update automatically when the database changes later. If `GDS_LINK` or DBMS nodes change, re-evaluate, update, or re-project the graph catalog before analyzing again.

## 6. Execution Modes Determine Cost and Side Effects

GDS has common modes: `stream`, `stats`, `mutate`, and `write`. Each has different effects and memory profiles.

| Mode | Effect | Memory / Operational Notes |
| --- | --- | --- |
| `stream` | Streams rows for Cypher/driver consumption | Algorithm memory + potential huge result stream; client may buffer heavily if calling `list()` |
| `stats` | Returns one summary statistics row | Does not write database, yet algorithm execution can still consume substantial memory |
| `mutate` | Saves results into the **GDS graph in the catalog** | New properties continue occupying heap afterward; lifecycle management required |
| `write` | Writes results back to the **Neo4j database** | Beyond algorithm memory, involves transaction state, page cache, and storage write cost |

For example, estimating two modes of the same algorithm:

```cypher
CALL gds.pageRank.mutate.estimate(
  'gdsDemoGraph',
  {mutateProperty: 'pageRank', concurrency: 2}
)
YIELD bytesMin, bytesMax, requiredMemory
RETURN bytesMin, bytesMax, requiredMemory;
```

```cypher
CALL gds.pageRank.write.estimate(
  'gdsDemoGraph',
  {writeProperty: 'pageRank', concurrency: 2}
)
YIELD bytesMin, bytesMax, requiredMemory
RETURN bytesMin, bytesMax, requiredMemory;
```

A `stats` mode may also exist if supported by the specific algorithm. **Do not assume all four modes exist for every algorithm.** Check the algorithm's documentation page and registered procedures in your running GDS version.

### Two Common Misconceptions

- "`stats` only returns one row so it uses almost no RAM." In reality, it may still compute scores/labels across the entire graph to generate statistics.
- "`stream` writes no data so it's harmless." Streaming tens of millions of nodes can push massive result payloads to the client. `RETURN ... LIMIT 10` limits returned rows, **not necessarily the work computed by the algorithm**.

## 7. From `bytesMax` to Heap Allocation Decisions

### 7.1. Budgeting by *Concurrent Peak*

For **an already projected graph**, you can sketch an initial budget:

```text
Heap needed at peak workload (conceptual model)
  ≈ memory held by current graph catalog
  + working memory of concurrent GDS jobs
  + memory of other active Neo4j/transactions/queries
  + headroom buffer for variance, GC, and estimate skew
```

When projecting a new graph and running an algorithm, include the **new projection** footprint. If an algorithm estimate already combines projection + execution configuration, understand what is included before summing with another estimate.

**This is a planning formula, not a literal sum of non-overlapping peaks.** Use real measurements and scheduling practices to determine which components overlap in time.

### 7.2. Illustrative Budget Example

Suppose a server has **16 GiB maximum JVM heap**. Based on the operations team's measurements/estimates (**hypothetical** numbers):

| Heap Demand | Example Estimate |
| --- | ---: |
| Active Neo4j and other transactions | 3 GiB |
| Graphs already held in GDS catalog | 7 GiB |
| Peak working memory for PageRank | 4 GiB |
| Operational headroom | 3 GiB |
| **Total budgeted** | **17 GiB** |

Even if `gds.pageRank.stream.estimate` only reports ~4 GiB, this budget **does not fit inside a 16 GiB heap** under these assumptions. Resolve it by dropping unused old graphs, narrowing projection scope, scheduling jobs sequentially, or scaling heap in a controlled manner.

Never read `heapPercentageMax = 25` and conclude "75% of heap is free." That field only compares the **operation's estimate** against configured max heap, without subtracting memory already in use.

### 7.3. JVM Heap Is Distinct from Host RAM and Page Cache

On self-managed Neo4j, heap configuration typically includes:

```properties
# neo4j.conf — illustrative syntax; tune to actual physical RAM
server.memory.heap.initial_size=16G
server.memory.heap.max_size=16G
```

**Never copy 16G onto a machine with 16 GiB of physical RAM.** The host also needs page cache, native memory, the OS, and other processes. Heap sizing should reflect total RAM budget, workload mix (transactional + analytical), edition/deployment, page cache, and scalability needs.

On a host serving both APIs and GDS, **never starve the page cache unconditionally** to give all RAM to heap: doing so can severely slow down Cypher read/write queries. On dedicated analytics jobs, the balance can differ.

## 8. Parameters That Alter Memory Estimates

| Factor | Impact on Footprint | How to Evaluate |
| --- | --- | --- |
| `nodeCount` | Many algorithms allocate per-node state arrays | Measure node count in the actual projection |
| `relationshipCount` | Adjacency/graph traversal structures can be huge | Review types, orientation, and relationship filters |
| `orientation` | `UNDIRECTED` can double stored directed edges | Compare estimates against `NATURAL` and algorithm requirements |
| `nodeProperties`, `relationshipProperties` | Loads extra numeric/weight arrays | Project only properties strictly needed |
| `concurrency` | More workers often increase per-worker buffers/working sets in some algorithms | Run `.estimate` with the exact planned value |
| `readConcurrency` | Controls projection read threads; affects creation overhead | Balance against I/O, CPU, and page cache capacity |
| `maxIterations`, `tolerance` | Usually affect runtime/iterations; may affect memory depending on algorithm | Check docs and re-run estimate rather than guessing |
| `mutateProperty` | Results remain stored in the GDS graph | Budget post-run footprint |
| `writeProperty` and write-back | Writes back to store, involving transactions and page cache | Evaluate write path and DBMS load |
| Concurrent jobs | Can stack multiple working sets simultaneously | Schedule jobs and monitor memory |
| High-degree nodes or skewed distributions | Can unbalance algorithm/partition structures | Test with samples reflecting high-degree hubs |

**Lowering `concurrency` does not guarantee linear memory savings.** Certain algorithm structures exist regardless of thread count; moreover, tuning concurrency impacts runtime, CPU, and I/O. Always compare estimates and benchmark on a test environment.

## 9. Scenario: 50 Million Nodes, 400 Million Relationships

Suppose a supply-chain analytics application wants to run PageRank on a graph with:

- 50,000,000 `Company` nodes.
- 400,000,000 `TRADES_WITH` relationships.
- Some relationships have an `annualVolume` property, though PageRank may not require weights.
- Neo4j simultaneously serves Cypher requests from the Java Driver and Spring Data Neo4j.

Decision workflow:

1. **Clarify the question:** Does PageRank need every company and every relationship? Does it require `annualVolume` weights?
2. **Run a hypothetical projection estimate** via `gds.graph.project.estimate('*', '*', {nodeCount: 50000000, relationshipCount: 400000000})`; remember this is only a rough baseline.
3. **Estimate with the real projection config** once data exists; specify labels/types, orientation, and properties.
4. **Measure current heap** and footprints of existing graphs; check for concurrent jobs.
5. **Estimate per-mode algorithm memory** on the named graph or via combined projection-and-algorithm estimation if supported by your GDS version.
6. **Assess upper bounds and headroom**, deciding whether to run on a dedicated analytics cluster/infrastructure, stagger schedules, or narrow the dataset.
7. **Test on a representative subset**, measuring runtime, GC, page cache, and actual memory. Never take a random 1% node sample and assume degree distribution stays intact.
8. Run the full workload only with adequate headroom and monitoring, limits, and error handling in place.

### Why Avoid Hand-Calculating "400M Edges × 8 Bytes"?

Directed vs. undirected representations, weight properties, compression formats, and per-algorithm arrays render simple multiplication wrong. Two graphs with identical node/relationship counts can consume different amounts of memory due to projection config and real topology. **GDS `.estimate` is a far more reliable starting point than ad-hoc multiplication**, though real load observation remains essential.

### Reducing Memory Pressure Without Breaking the Problem

- Project **strictly the business nodes/relationships needed**. Avoid `'*'` in production when analyzing a subgraph.
- Avoid projecting unused properties; many graph algorithms run on topology alone.
- Use the orientation mathematically required by the algorithm; never switch to `UNDIRECTED` arbitrarily.
- Drop stale GDS graphs and result properties from the catalog.
- Consider lowering concurrency or avoiding overlapping memory-heavy peak jobs.
- If approximate/sampled results suffice, consider sampling **while explicitly documenting analytical quality trade-offs**.
- Never assume you can partition PageRank into independent subgraphs and merge scores while preserving full-graph semantics.

## 10. Monitoring GDS Jobs and Reclaiming Memory

### 10.1. Inspecting the Graph Catalog

```cypher
CALL gds.graph.list()
YIELD graphName, nodeCount, relationshipCount,
      sizeInBytes, memoryUsage
RETURN graphName, nodeCount, relationshipCount,
       sizeInBytes, memoryUsage
ORDER BY graphName;
```

This reveals graphs occupying heap. To avoid unnecessary stats overhead on massive graphs, **`YIELD` only the fields you actually need**—for example, omit `degreeDistribution` if you are not analyzing node degrees.

### 10.2. Inspecting Graph and Job Footprints

In GDS environments/editions supporting monitoring procedures:

```cypher
CALL gds.memory.list()
YIELD user, name, entity, memoryInBytes
RETURN user, name, entity, memoryInBytes
ORDER BY memoryInBytes DESC;
```

Per GDS documentation, for a **graph** this shows currently held memory; for a **running task**, the value is an **estimated peak requirement**, not millisecond-exact live usage. User/admin roles determine visibility scope.

```cypher
CALL gds.systemMonitor()
YIELD freeHeap, totalHeap, maxHeap, ongoingGdsProcedures
RETURN freeHeap, totalHeap, maxHeap, ongoingGdsProcedures;
```

`gds.systemMonitor` provides an overview of JVM heap and active jobs when available and permitted. Never equate `freeHeap` with free physical host RAM, or assume a point-in-time reading holds constant once other jobs start.

### 10.3. Dropping Finished Graphs

Only after all jobs using a named graph have completed, drop the demo graph:

```cypher
CALL gds.graph.drop('gdsDemoGraph')
YIELD graphName
RETURN graphName;
```

This **removes the graph projection from the GDS catalog**, without deleting nodes or relationships from the Neo4j database. If a graph is shared across jobs or users, verify ownership and analytics schedules before dropping.

If `mutate` created unused properties while the graph itself is still needed, check `gds.graph.nodeProperties.drop` to remove unwanted properties from the catalog. These operations differ from `REMOVE` on Neo4j database properties.

## 11. Automatic Checks and Limits of Out-of-Memory Guards

GDS performs **automatic pre-execution memory estimation** for procedures supporting estimation, including graph creation. If the system determines that available heap is definitely insufficient, GDS can **reject the job before starting**.

This prevents certain costly failures, yet:

- **Passing the check does not guarantee success.** The guard mainly blocks runs that are guaranteed not to fit.
- Free heap fluctuates as other jobs start, transactional queries spike, or new graphs are projected.
- GDS cannot guarantee the surrounding Java/OS environment has sufficient off-heap/native memory.
- Some experimental-tier algorithms/modes may lack complete estimation support.

Documentation mentions a `sudo: true` flag to bypass the memory guard in certain procedures. **Never use `sudo: true` as a "fix" for insufficient heap** on large graphs: it merely disables the safety guardrail and can lead to wasted runtime, severe GC thrashing, or out-of-memory failures.

When estimates show high risk, prioritize **dropping unused graphs, shrinking projections, lowering concurrency, or scaling heap in a controlled way**.

## 12. Java Driver and Spring Data Neo4j: Planned Execution

### 12.1. Calling `estimate` Before Jobs via Java Driver

Applications can run estimation as a **read-only preflight query**. The following example assumes an initialized `Driver driver`, a previously projected named graph `supplyGraph`, and PageRank availability in GDS:

```java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String estimateCypher = """
    CALL gds.pageRank.stream.estimate(
      $graphName,
      {concurrency: $concurrency, maxIterations: $iterations}
    )
    YIELD nodeCount, relationshipCount, bytesMin, bytesMax,
          requiredMemory
    RETURN nodeCount, relationshipCount,
           bytesMin, bytesMax, requiredMemory
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    var estimate = session.executeRead(tx ->
        tx.run(estimateCypher, Map.of(
            "graphName", "supplyGraph",
            "concurrency", 4,
            "iterations", 20
        )).single()
    );

    long bytesMax = estimate.get("bytesMax").asLong();
    System.out.println("GDS estimate upper bound = "
        + bytesMax + " bytes");
}
```

`bytesMax` is numeric, making it cleaner than parsing strings like `"2 GiB"` in `requiredMemory`. In real services, a preflight check must also inspect current heap and concurrent workloads; **do not auto-approve based solely on `bytesMax < maxHeap`**.

When proceeding to run the algorithm after preflight, use the exact same graph, mode, and parameters from the estimate along with proper orchestration. Do not run `stream.estimate` and then invoke `mutate` with different settings assuming the estimate still applies.

### 12.2. Spring Data Neo4j

A Spring service using `Neo4jClient` or `@Query` can invoke GDS **if GDS is installed on the server**. To run large analytical jobs safely:

1. Separate graph creation, estimation, resource checks, algorithm execution, and graph cleanup.
2. Verify permissions for schema/projection/algorithm execution; do not confuse Java dependencies with server-side GDS plugins.
3. Avoid designing short HTTP requests that must stream millions of rows before timing out. Use background jobs/queues as appropriate for scale.
4. Control retries: blindly retrying `mutate` or `write` after a connection drop can fail on duplicate properties or re-write state; retry only after checking job status.
5. For large streams, consume records iteratively, paginate, or batch on the client; calling `list()` **materializes the entire result into the client's Java heap**.
6. Log Neo4j and GDS versions, projection config, and estimate numbers to troubleshoot performance regressions.

### 12.3. Server Memory and Client Memory Are Separate Problems

Suppose GDS has enough heap to compute scores for 40 million nodes, but the Java Driver calls `Result.list()` on 40 million records; the Java application **can still run out of its own heap**, even though Neo4j completed the algorithm cleanly. Therefore, capacity planning should cover at least:

- **Neo4j/GDS JVM heap** for projecting and running algorithms.
- **Host RAM / page cache / native memory**.
- **Client heap and network throughput** for consuming results.
- **Execution time, concurrency, and queueing** at the application layer.

## 13. Diagnosing Common Scenarios

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| GDS reports "estimate exceeds available memory" | Graph/algorithm does not fit in free heap | Check `bytesMax`, catalog, and other jobs; reduce load or resize heap appropriately |
| Small `.estimate` yet OOM at runtime | Skewed data/worker variance, overhead, or estimate gap | Inspect logs, heap, concurrent jobs, actual config, and GC |
| Graph estimate differs sharply from DB row counts | Filters, orientation, or selected labels/types differ | Inspect projection config, `nodeCount`, `relationshipCount` |
| Heap stays high right after algorithm finishes | Named graph / mutated properties still in catalog | Run `gds.graph.list`; drop unused graphs/properties |
| `gds.graph.list` reports `sizeInBytes = -1` | JDK does not support graph size instrumentation | Use alternative monitoring tools; do not treat as 0 bytes |
| Lowering `concurrency` saves little RAM | Most memory is shared algorithm state | Compare `.estimate` and benchmark; do not expect linear scaling |
| `stream` does not write DB yet Java app hits OOM | Client collects all rows via `list()` | Stream/process records incrementally and bound output |
| `WRITE` is slow despite sufficient estimate | Page cache, transaction state, I/O, indexes, and DBMS contention | Profile write path and storage resources, not just GDS heap |
| `gds.<algo>.estimate` does not exist | Wrong name/mode, missing GDS, or unsupported version/tier | Check `gds.version()`, `SHOW PROCEDURES`, and algorithm docs |
| PageRank results miss newly added edges | Graph catalog snapshot is older than the DB | Refresh/re-project graph per workflow |
| Blocked command runs when `sudo` is set | Estimate guard bypassed while underlying risk remains | Do not treat as a fix; verify true capacity |

## 14. Checklist Before a Large Analytics Job

1. **Business scope:** choose algorithm, output mode, node/relationship scope, weights, and required accuracy.
2. **Versions:** check Neo4j/GDS versions and `.estimate` support for the specific algorithm/mode.
3. **Graph:** use real projection config, run `gds.graph.project.estimate`, and verify node/relationship counts.
4. **Algorithm:** run `gds.<algorithm>.<mode>.estimate` with exact runtime parameters; record `bytesMin`, `bytesMax`, and `treeView`.
5. **Resources:** check max JVM heap, graph catalog, concurrent jobs, page cache, OS memory, and client RAM.
6. **Headroom:** reserve buffer for variance, GC, and transactional load; do not rely solely on `heapPercentageMax`.
7. **Pilot run:** test on representative data with a similar degree distribution; record CPU, memory, GC, and runtime.
8. **Orchestration:** cap concurrent heavy jobs, and define timeouts, recovery, and retry logic.
9. **Monitoring:** track memory, progress, error logs, and output quality.
10. **Cleanup:** drop graphs/mutated properties only when no dependent jobs remain; verify memory reclamation.

## 15. Self-Practice Exercises

1. Given a graph with 2 million nodes and 18 million relationships, write a `gds.graph.project.estimate` query for the hypothetical scenario and explain why this estimate is insufficient if the graph needs weights and `UNDIRECTED` orientation.
2. Create `gdsDemoGraph` from this lesson, then run `gds.pageRank.stream.estimate` and `gds.pageRank.write.estimate`. Compare `bytesMax` and explain the additional impact of writing results back to the database.
3. A host has 24 GiB max heap; the graph catalog holds 10 GiB, running jobs need up to 6 GiB more, DBMS/transactions need ~3 GiB, and a new job needs up to 7 GiB. Assuming overlapping peak memory usage, should the new job start immediately? Why or why not?
4. Why does `RETURN nodeId, score LIMIT 10` after `gds.pageRank.stream` not guarantee that the algorithm processes only 10 nodes?
5. Explain the differences between `gds.graph.list`, `gds.memory.list`, and `gds.systemMonitor`; which metric inspects projected graphs and which reflects active jobs?
6. If all relationships change from `NATURAL` to `UNDIRECTED`, which numbers and mathematical assumptions must be re-verified?
7. Design a preflight sequence for a Spring service running PageRank nightly. Explain how to prevent duplicate-write retries, reclaim the catalog, and monitor both client and server heap.

## 16. Key Takeaways

- **GDS graph projections and algorithms consume JVM heap.** Projected graphs stay in the catalog until dropped or their lifecycle ends.
- **Estimate before loading graphs** with `gds.graph.project.estimate(...)`; **estimate algorithms** with `gds.<algorithm>.<mode>.estimate(...)`.
- `bytesMin`, `bytesMax`, and `treeView` guide planning, but **do not measure free memory** and **do not guarantee job completion**.
- Budget for **concurrent heap occupants**: graph catalog, algorithms, Neo4j/transactions, and other jobs, keeping reasonable headroom.
- Node count, relationship count, orientation, properties, output mode, and concurrency all impact estimates. Never extrapolate naively from tiny graphs.
- `stream`, `stats`, `mutate`, and `write` have **different effects and memory footprints**. `mutate` keeps results in the catalog; `write` also incurs database write load.
- Monitor `gds.graph.list`, memory/monitor procedures where supported, and **drop unused graphs**. Server-side GDS success does not imply the Java client has enough RAM to materialize all rows.
- **Never bypass heap checks with `sudo`** to "solve" out-of-memory errors; reduce workload scope or allocate resources properly.

### Official References

- [Neo4j GDS — Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/)
- [Neo4j GDS — System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/)
- [Neo4j GDS — Native projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Neo4j GDS — Cypher projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project-cypher-projection/)
- [Neo4j GDS — Algorithm syntax and execution modes](https://neo4j.com/docs/graph-data-science/current/algorithms/syntax/)
- [Neo4j GDS — PageRank](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)
- [Neo4j GDS — Graph list](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-list/)
- [Neo4j GDS — Dropping graphs](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-drop/)
- [Neo4j GDS — Monitoring system](https://neo4j.com/docs/graph-data-science/current/common-usage/monitoring-system/)
