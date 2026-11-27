# Neo4j Graph Data Science and Installation or Usage Prerequisites

## Learning Objectives

After this lesson, you will be able to:

- Explain what problems **Neo4j Graph Data Science (GDS)** solves in the property graph ecosystem and distinguish GDS from standard Cypher.
- Identify the **execution environment**, **Neo4j/GDS version**, **edition/license**, access permissions, and required resources before using GDS.
- Install or enable GDS in Neo4j Desktop, self-managed Neo4j Server, or Docker; recognize managed service options on Aura.
- Verify the plugin using `gds.version()`, estimate memory, project a graph into memory, run algorithms, and drop the graph.
- Distinguish `stream`, `stats`, `mutate`, and `write` modes; design safe Java and Spring Data Neo4j application flows that invoke GDS.
- Diagnose missing plugin errors, version incompatibilities, missing licenses, permission issues, and heap limit overflows.

This lesson belongs to the **Graph Algorithms** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j stores nodes, relationships, and properties in the **property graph** model, while Cypher allows querying relationships and paths. GDS extends this capability with **large-scale graph analytics algorithms** such as PageRank, connected components, shortest paths, community detection, similarity, and graph-based machine learning pipelines.

> **Version note:** This guide uses modern Neo4j GDS syntax; the examples are compatible when the database has the **appropriate GDS plugin** installed and the account has required permissions. Neo4j has release lines including 5.x, 2025.x, and 2026.x. Never pick a random JAR file just because the name looks similar: always check the [official compatibility matrix](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/) and the documentation for your exact running version.

## 1. What Is GDS, and How Does It Differ from Cypher and APOC?

With Cypher, an application can find a customer and their related orders:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

This is a **data pattern query**. When you need to identify the most important nodes in a network, partition a graph into communities, or compute across millions of vertices and edges, the solution is typically a **graph algorithm**. GDS provides dedicated algorithms and graph management mechanisms for this task.

| Component | Primary Role | Examples |
| --- | --- | --- |
| **Core Neo4j Cypher** | Querying and updating the property graph | `MATCH`, `CREATE`, `MERGE`, path queries |
| **GDS library** | Projecting graphs into memory, running analytical algorithms | `gds.pageRank.stream`, `gds.wcc.stream` |
| **APOC** | Procedure/utility library supporting data processing and integration | `apoc.*` procedures depending on plugin |
| **Java Driver / Spring Data Neo4j** | Connections, transactions, invoking Cypher/procedures from applications | `executeRead`, `@Query` |
| **GDS Python Client** | Convenient Python API for controlling GDS and processing results | `GraphDataScience`, `gds.page_rank.stream` |

**GDS is not a mandatory part of core Cypher.** A normally running Neo4j server will still report `Unknown function 'gds.version'` or `There is no procedure with the name ...` if the plugin is absent or not permitted. Installing the Python Client **does not automatically install the GDS plugin on the server**.

### Common Algorithm Categories

| Category | Problem | Representative Algorithms |
| --- | --- | --- |
| **Centrality** | Which nodes are most influential or structurally important? | PageRank, Degree Centrality, Betweenness |
| **Community detection** | Which groups of nodes are densely connected? | Weakly Connected Components (WCC), Louvain, Leiden |
| **Path finding** | Which paths connect two nodes under cost/constraints? | Dijkstra, A*, and supported variants |
| **Similarity** | How similar are two nodes? | Node Similarity, KNN |
| **Embedding / ML** | Generating features and training models from graphs | FastRP, Node2Vec, classification or link prediction pipelines |

Not all algorithms use the same graph types or property sets. For example, Dijkstra typically requires non-negative edge weights for weighted shortest paths, whereas PageRank evaluates importance based on link structure. Always read the **graph, orientation, property, and execution mode requirements** of each specific algorithm.

## 2. How Does GDS Process Graphs?

GDS creates a **named in-memory graph** inside the **graph catalog** from a Neo4j database or supported source. This graph is an **in-memory representation for computation**, not a conversion of the entire database into a different database engine.

~~~mermaid
flowchart LR
    DB[("Neo4j database<br/>nodes + relationships")] --> P["Graph projection<br/>labels, types, properties"]
    P --> MEM[("In-memory graph<br/>GDS catalog")]
    MEM --> ALG["PageRank / WCC / Paths"]
    ALG --> STREAM["stream / stats"]
    ALG --> MUTATE["mutate in graph catalog"]
    ALG --> WRITE["write back to Neo4j"]
~~~

A typical workflow consists of:

1. Identifying the required node labels, relationship types, edge orientations, and properties.
2. **Estimating** memory capacity for the projection and algorithm.
3. Projecting the graph into the catalog using `gds.graph.project` or the corresponding projection mechanism.
4. Running the algorithm in the appropriate mode.
5. Inspecting results, validating business semantics, and considering whether to write back to the database.
6. **Dropping the named graph** when no longer needed to free memory.

**Note on changing data:** A projected named graph **does not automatically sync individual updates** from the source database. If the application creates or deletes nodes or relationships after projection, the graph in the catalog can become stale. You must establish policies to recreate, filter, or update graphs using GDS-supported mechanisms; do not treat algorithm outputs as always-fresh transactional data.

## 3. Distinguishing Neo4j Edition, GDS Edition, and Aura Options

These are three **separate** concepts to verify:

1. **Neo4j Database edition:** Community or Enterprise edition of the database.
2. **GDS library edition:** Community Edition (CE) or Enterprise Edition (EE) of the **GDS library**.
3. **Deployment environment:** Neo4j Desktop, self-managed server, Docker/Kubernetes, AuraDS, or Aura Graph Analytics.

### 3.1. GDS Community vs. GDS Enterprise

According to current GDS documentation, GDS Community includes **the algorithms**, while limiting certain operational capabilities; GDS Enterprise uses a separate license to unlock those limits and additional features.

| Criterion | GDS Community | GDS Enterprise |
| --- | --- | --- |
| Running graph algorithms | Yes | Yes |
| GDS concurrency limit | Maximum of **4** processing threads under GDS CE policy | No fixed CE concurrency cap; still bounded by physical resources |
| Model catalog | Maximum of **3** models | Supports managing more models and storing/sharing models |
| Advanced graph management, graph catalog backup/restore, Apache Arrow | Feature-limited | Additional features included |
| GDS write workloads in a Neo4j cluster | Restricted | Supported under EE terms and configuration |
| GDS license key | No Enterprise license required | **Valid GDS Enterprise license required** for self-managed deployments |

**Common misconception:** **Neo4j Database Enterprise does not automatically mean GDS Enterprise is activated.** A GDS plugin can run in Community mode if a valid GDS license has not been configured. Conversely, GDS CE's concurrency cap of **4** comes from the **GDS license**, not merely from the Neo4j Database edition.

When evaluating commercial requirements, verify current license terms, cluster execution capabilities, and latest product limits. Official references: [GDS Introduction — Editions](https://neo4j.com/docs/graph-data-science/current/introduction/), [GDS Enterprise Edition](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/).

### 3.2. Choosing a Deployment Option

| Environment | How GDS Is Available | What to Check |
| --- | --- | --- |
| **Neo4j Desktop** | Install the **Graph Data Science** plugin from the Plugins tab | DB/GDS versions, database status, procedure permissions |
| **Self-managed Neo4j Server** | Place compatible JAR into the `plugins` directory, configure, and restart | GDS EE license if used, JVM, heap, permissions, and plugin version |
| **Neo4j Docker** | Declare the `graph-data-science` plugin via `NEO4J_PLUGINS` | Pinned Neo4j image version, persistence, container memory |
| **Neo4j cluster / Kubernetes** | Configure the plugin on cluster members per product/Helm docs | License, resources, routing, GDS CE/EE workload restrictions |
| **AuraDS** | Pre-managed GDS Enterprise service | Service availability/purchasing and tenant quotas |
| **Aura Graph Analytics** | On-demand analytics sessions; no plugin installed directly on source DB | Data source, session creation permissions, session capacity, cost, and write-back |
| **Neo4j Data Science Sandbox** | Learning sandbox with GDS Community pre-installed | Sandbox time and resource limits |

With standard AuraDB, you **cannot by default** copy a JAR into the managed database as on a self-managed host. If graph algorithms are needed, check **Aura Graph Analytics** or an appropriate managed service. Per current documentation, Aura Graph Analytics uses **ephemeral compute sessions** following a *load/projection → run algorithms → optional write-back → delete session* flow. The session API differs from calling a local plugin directly on an arbitrary database.

See [GDS Installation](https://neo4j.com/docs/graph-data-science/current/installation/) and [Aura Graph Analytics](https://neo4j.com/docs/graph-data-science/current/aura-graph-analytics/).

## 4. Version Compatibility Requirements

GDS is a plugin tightly coupled to the Neo4j version. **Do not install the latest GDS onto an older Neo4j** unless that pair is explicitly supported.

A few **version examples from the official compatibility matrix**:

| Neo4j Database | Corresponding Neo4j GDS |
| --- | --- |
| `5.26` | `2.13` |
| `2025.12.1` | `2.25` |
| `2026.02.0` | `2.27` |
| `2026.10.0` | `2026.10` |

These are **reference points**, not a substitute for the full matrix, and do not imply every patch version is supported identically. Starting with newer 2026 releases, GDS version numbering also shifted to the `2026.xx` format rather than only `2.x`. Before installing or upgrading:

1. Identify the **actual Neo4j Database version** running.
2. Check **Supported Neo4j versions** in the GDS documentation for that point in time.
3. Choose the GDS JAR bundled with or listed as compatible with that database version.
4. Review JVM, RAM, configuration permissions, restart plans, and upgrade release notes.
5. For the Python Client, also check the **client ↔ GDS ↔ Neo4j Python Driver version matrix**. For Java, verify **Java Driver ↔ Neo4j** compatibility separately; the Java Driver does not determine whether the server plugin is installed.

References: [Supported Neo4j versions](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/), [System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/), and [GDS Python Client Installation](https://neo4j.com/docs/graph-data-science-client/current/installation/).

## 5. Installing GDS on Neo4j Desktop or Neo4j Server

### 5.1. Neo4j Desktop

For learning environments:

1. Open Neo4j Desktop and select the target database instance.
2. Go to the **Plugins** tab, select **Graph Data Science**, and install the plugin version provided by Desktop for that database.
3. Check **Settings**; required procedure settings may be added automatically by Desktop.
4. Restart the database if needed, then verify with `RETURN gds.version();`.

You do not need to place the GDS JAR into every Java project: the plugin runs **on the Neo4j server**, while applications connect through a driver.

### 5.2. Self-Managed Neo4j Server

On modern Neo4j distributions, the server package often ships the compatible GDS JAR inside the `products` directory. Following the Neo4j Server installation guide:

~~~text
NEO4J_HOME/
  products/neo4j-graph-data-science-<version>.jar
  plugins/
  conf/neo4j.conf
~~~

Main steps:

1. Stop the Neo4j service following operational procedures.
2. Copy or move the **compatible** `neo4j-graph-data-science-<version>.jar` file from `products` to `plugins` (or download a supported release from an official source).
3. In `conf/neo4j.conf`, configure procedure access:

~~~properties
dbms.security.procedures.unrestricted=gds.*
dbms.security.procedures.allowlist=gds.*
~~~

4. If allowlist is **not enabled** or your system has custom rules, adjust according to the Neo4j documentation for your version. If `allowlist`/`unrestricted` already contains other procedures, **merge** `gds.*` appropriately rather than accidentally overwriting existing entries.
5. If using **GDS Enterprise**, configure the **separate license key** using an absolute path readable by Neo4j:

~~~properties
gds.enterprise.license_file=/path/to/gds-license-file
~~~

6. Start/restart Neo4j and verify the GDS version, license, and procedures.

**Security:** Setting `unrestricted=gds.*` grants the library access to required internal APIs; it is a **server-level** setting controlled by administrators and does not mean every database user should be allowed to execute every procedure. Grant `EXECUTE PROCEDURE`, graph access, and GDS privileges according to your edition/version documentation.

If the license configuration points to an unreadable, invalid, or expired file, GDS commands may fail with errors rather than silently falling back to Community mode. Verify the file path, permissions, and license status.

Sources: [Neo4j Server GDS installation](https://neo4j.com/docs/graph-data-science/current/installation/neo4j-server/), [GDS Enterprise License](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/).

## 6. Installing GDS in Docker/Kubernetes

Neo4j Docker supports the `NEO4J_PLUGINS` environment variable, which accepts a JSON list of plugins. Example **for learning environments only**:

~~~bash
docker run --rm \
  --name neo4j-gds-lab \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH='neo4j/change-this-password' \
  -e NEO4J_PLUGINS='["graph-data-science"]' \
  neo4j:latest
~~~

In production, **pin the image tag to a verified compatible version**, use secrets, persistent volumes, and resource limits. Do not use `neo4j:latest` for long-lived reproducible environments, as that tag can resolve to a different version on subsequent pulls/restarts.

`NEO4J_PLUGINS` uses the name **`graph-data-science`**, not `gds`. Plugin installation may require network access from the container to download the package. On Kubernetes, install the plugin via the **official Helm chart or configuration mechanism**, ensuring all pods running GDS receive the right plugin/config and resources. Avoid changing plugin versions on only a single cluster member.

When using GDS Enterprise in Docker, also **mount the license file** into the container and configure its path appropriately, while complying with the Neo4j Database license if running Enterprise.

Sources: [GDS Docker](https://neo4j.com/docs/graph-data-science/current/installation/installation-docker/), [Neo4j Docker Plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/).

## 7. Verifying Installation and Permissions

Once the server is running, open Neo4j Browser or connect via a driver to the **target database**.

~~~cypher
RETURN gds.version() AS gdsVersion;
~~~

If successful, it returns the loaded GDS version. If `Unknown function` appears, inspect the plugin, version compatibility, procedure settings, and restart process.

List available GDS procedures and functions:

~~~cypher
CALL gds.list();
~~~

Check license mode:

~~~cypher
RETURN gds.isLicensed() AS enterpriseLicensed;

CALL gds.license.state();
~~~

`gds.isLicensed() = false` can be the normal **GDS Community** state. If you expect to use GDS Enterprise, verify the license configuration rather than assuming `false` automatically indicates a plugin installation error.

### Basic Verification Checklist

| Verification Question | Expected Result |
| --- | --- |
| Which Neo4j version is running? | Specific version confirmed from DBMS/admin info |
| Is the JAR/plugin compatible? | Matches the Neo4j ↔ GDS matrix |
| `RETURN gds.version()`? | Returns version string without missing-function error |
| `CALL gds.list()`? | Returns list of GDS procedures/functions |
| Does GDS EE require a license? | `gds.isLicensed()` and license state match expectations |
| Does the user have permission to run procedures? | Has execute privileges and required graph access |
| Is there sufficient RAM/CPU? | Projection and algorithm memory estimates fit available resources |

Note when using an **Aura Graph Analytics session**: computation happens in a managed session with its own API/endpoint mechanism; do not apply local plugin checks as if you were installing a JAR onto the source AuraDB.

## 8. Hands-On: Projecting a Graph and Running PageRank

The examples below apply to a **Neo4j database with the GDS plugin installed**, not an Aura Graph Analytics session. Use dedicated node labels and relationship types to avoid colliding with operational data. Run only on a practice database.

### 8.1. Preparing Sample Data

~~~cypher
MERGE (an:GdsPracticePerson {personId: 'AN'})
MERGE (binh:GdsPracticePerson {personId: 'BINH'})
MERGE (chi:GdsPracticePerson {personId: 'CHI'})
MERGE (dung:GdsPracticePerson {personId: 'DUNG'})
MERGE (an)-[:GDS_KNOWS]->(binh)
MERGE (an)-[:GDS_KNOWS]->(chi)
MERGE (binh)-[:GDS_KNOWS]->(chi)
MERGE (chi)-[:GDS_KNOWS]->(dung)
MERGE (dung)-[:GDS_KNOWS]->(chi);
~~~

Diagram:

~~~mermaid
flowchart LR
    A["AN"] --> B["BINH"]
    A --> C["CHI"]
    B --> C
    C --> D["DUNG"]
    D --> C
~~~

`MERGE` enables sequential re-runs on demo data. In real systems with concurrent writes, enforce a **uniqueness constraint** on the business key and relationship management rules to prevent duplicates.

### 8.2. Estimating Memory for the Projection

~~~cypher
CALL gds.graph.project.estimate(
  'GdsPracticePerson',
  'GDS_KNOWS',
  {}
)
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

`.estimate` estimates memory; it **does not create** the named graph. Actual memory usage depends on node count, relationship count, orientation, projected properties, and configuration. Always estimate before loading large graphs to prevent exhausting DBMS heap.

### 8.3. Projecting the Graph into the Catalog

~~~cypher
CALL gds.graph.project(
  'gdsPractice',
  'GdsPracticePerson',
  'GDS_KNOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

`gdsPractice` is a **graph name in the GDS catalog**, not a database name. This graph contains only `GdsPracticePerson` nodes and `GDS_KNOWS` relationships within the projection scope.

If a graph named `gdsPractice` already exists for the user/session under catalog rules, creation fails with a duplicate name error. Check before re-projecting:

~~~cypher
CALL gds.graph.list('gdsPractice')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

### 8.4. Estimating and Running PageRank

~~~cypher
CALL gds.pageRank.stream.estimate('gdsPractice', {})
YIELD requiredMemory
RETURN requiredMemory;
~~~

Once memory requirements are satisfied:

~~~cypher
CALL gds.pageRank.stream('gdsPractice', {
  dampingFactor: 0.85,
  maxIterations: 20
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId;
~~~

`PageRank` evaluates importance based on **directed link structure** and score propagation. The demo diagram has a reciprocal edge between `CHI` and `DUNG`, so interpreting results requires examining edge direction, not merely counting neighbors. `gds.util.asNode(nodeId)` maps GDS node IDs back to Neo4j nodes when projected from a source database; when using graphs imported outside Neo4j or remote sessions, node metadata retrieval can differ.

### 8.5. Running Another Algorithm

~~~cypher
CALL gds.wcc.stream('gdsPractice')
YIELD nodeId, componentId
RETURN gds.util.asNode(nodeId).personId AS personId, componentId
ORDER BY componentId, personId;
~~~

**WCC (Weakly Connected Components)** groups nodes that are reachable when ignoring edge direction to identify weak components. In the demo graph, all nodes are connected via undirected paths and thus typically belong to the same component. **The numeric value of `componentId` has no stable business meaning**; check whether two nodes share the same component rather than attaching meaning to the numeric ID itself.

### 8.6. Freeing Memory When Finished

~~~cypher
CALL gds.graph.drop('gdsPractice')
YIELD graphName
RETURN graphName;
~~~

`gds.graph.drop` removes the **named in-memory graph**, not the `GdsPracticePerson` nodes or `GDS_KNOWS` relationships stored in Neo4j. This is a critical operational step so the graph catalog does not hold onto heap after the algorithm finishes.

## 9. Execution Modes: stream, stats, mutate, write

GDS provides result modes depending on the algorithm. Not every algorithm supports all modes or identical output field names; consult the specific algorithm reference.

| Mode | Effect | Writes to Neo4j Database? | When to Choose |
| --- | --- | --- | --- |
| **`stream`** | Returns results row by row | No (algorithm does not write DB in this mode) | Exploration, analysis, exporting results to applications |
| **`stats`** | Returns summary statistics from the algorithm | No | Evaluating groups/distributions without per-node output |
| **`mutate`** | Writes results to the **in-memory graph** in the catalog | No | Preparing features for subsequent algorithms/pipelines |
| **`write`** | Writes result properties/relationships back to **Neo4j database** | **Yes** | Persisting rankings, communities, or embeddings into the real graph |

Example `write` mode for PageRank (run only when intending to **modify the database**):

~~~cypher
// WARNING: Writes properties to real nodes in the Neo4j database.
CALL gds.pageRank.write('gdsPractice', {
  writeProperty: 'pageRankScore'
})
YIELD nodePropertiesWritten, writeMillis
RETURN nodePropertiesWritten, writeMillis;
~~~

When using `write` in production:

- Verify the user has write permissions and GDS write workloads are supported by your **edition/cluster**.
- Choose output property names that will not unintentionally overwrite operational values.
- Assess write locks, transactions, index impact, and recalculation needs when the graph changes.
- Have appropriate authorization, transaction, and rollback/recovery strategies in place.

**Computing PageRank does not modify the source graph** when calling `stream` only. This is a vital distinction between graph analytics and database updates.

## 10. Memory, CPU, Page Cache, and Operational Conditions

GDS relies on **in-memory graphs** and algorithm state, making it sensitive to the Neo4j JVM **heap**. Distinguish these resources:

| Resource | Role with GDS | Risk |
| --- | --- | --- |
| **JVM Heap** | Stores graph projections and algorithm state | Out-of-memory errors, long GC pauses |
| **Page cache** | Helps read Neo4j data during projection and write results back | Insufficient page cache increases I/O; too large competes with heap for RAM |
| **CPU/concurrency** | Runs projections and algorithms in parallel | Excess threads cause contention, impacting transactional workloads |
| **Disk/transaction log** | Stores database, `write` results, and change logs | Large writes increase I/O and disk usage |
| **Network / driver** | Transfers results when using `stream` remotely | Returning millions of scores puts pressure on serialization and connections |

On a machine serving both **OLTP** (production transactions) and GDS, do not allocate nearly all RAM to GDS heap while starving the page cache. GDS documentation includes memory guidance tailored for **dedicated analytics** environments; those recommendations **do not apply unchanged** to mixed transactional servers.

**Recommended workflow:**

1. Project only the labels, types, and properties actually needed.
2. Use `gds.graph.project.estimate` and `gds.<algorithm>.<mode>.estimate`.
3. Record `nodeCount`, `relationshipCount`, `requiredMemory`, available heap, and overall load.
4. Test on a small graph first; measure runtime, CPU, GC, heap, and impact on transactional queries.
5. Lower `concurrency` or graph size if resources are tight; schedule large analytical workloads.
6. Drop catalog graphs after use; plan cleanup for unneeded models/graphs.

GDS CE has a concurrency cap of 4 under current documentation, but **setting `concurrency=4` does not guarantee full 4-core utilization**. Effective threads, bottlenecks, and parallel speedup depend on the algorithm, hardware, and data.

Sources: [GDS Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/), [GDS System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/).

## 11. Invoking GDS from Java Driver and Spring Data Neo4j

A Java application **does not need a local GDS Java library to call Cypher procedures** if the server has the plugin installed; a compatible Neo4j driver is sufficient. Example reading PageRank scores from an already-projected graph:

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class GdsPageRankReader {
    public record Score(String personId, double score) {}

    public static List<Score> readScores(Driver driver) {
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                    CALL gds.pageRank.stream('gdsPractice')
                    YIELD nodeId, score
                    RETURN gds.util.asNode(nodeId).personId AS personId, score
                    ORDER BY score DESC
                    """).list(row -> new Score(
                    row.get("personId").asString(),
                    row.get("score").asDouble())));
        }
    }
}
~~~

**Preconditions:** `gdsPractice` has already been projected and still exists in the **graph catalog accessible to the user**; the plugin is loaded, the database is correct, and the user has permission to call GDS. `executeRead` fits read-only `stream` calls; use `executeWrite`/appropriate transactions for project/drop or `write` when required by version/semantics. A result with millions of nodes can make `list()` consume significant application-side RAM; limit output, stream records, or paginate as supported by your API.

With **Spring Data Neo4j**, you can run `CALL gds.*` Cypher via `Neo4jClient` or `@Query` repository methods when the result mapping matches. However:

- Spring Data Neo4j **does not install GDS**; graph projections still live in the server/GDS catalog.
- The GDS graph catalog holds in-memory analytical state with a **separate lifecycle** from `@Node` entities persisted by repositories.
- Running `gds.graph.project` and `gds.pageRank.stream` across two transactions requires attention to user, database, graph identifier, and permissions; do not assume the graph catalog behaves like a standard SQL session.
- `write` results can modify properties subsequently read back by Spring Data Neo4j; manage caching/entity state and update policies carefully.

If using the **GDS Python Client**, it is a separate SDK with version requirements for Python, GDS, and the Neo4j Python Driver; it primarily helps manage the graph catalog, algorithms, and outputs from Python. It is **not** required to use GDS from Cypher or Java.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Unknown function 'gds.version'` | Plugin not loaded, JAR misplaced, server not restarted, or procedures blocked | Check `plugins`, version, configuration, and startup logs |
| `There is no procedure with the name gds.graph.project` | Plugin unavailable for DB/user or different version/syntax | Check `gds.version()`, `gds.list()`, and version-specific docs |
| Plugin/server compatibility error | GDS JAR does not match Neo4j version | Check matrix; use bundled server JAR or supported build |
| Enterprise license error | Invalid, expired, or unreadable license file | Check `gds.isLicensed()`, `gds.license.state()`, path, and file permissions |
| `Graph with name ... does not exist` | Not projected yet, already dropped, or wrong user/database catalog | Check `gds.graph.list()`, scope, and graph lifecycle |
| `Graph already exists` | Graph name already exists in the catalog | Use a distinct name or intentionally drop the old graph |
| Memory estimation exceeds limit | Projection/algorithm needs more heap | Reduce data/properties, increase appropriate resources, or isolate analytics |
| Algorithm rejects relationship type/property | Projection does not satisfy algorithm requirements | Check traits, orientation, weight properties, and missing values |
| Permission error | User lacks procedure execute or graph read/write permissions | Check roles, execute grants, and administrative configuration |
| New changes missing from results | Graph was projected earlier and not refreshed | Re-project/update graph per analytics refresh policy |

### Server Error Troubleshooting Checklist

1. Verify **which database instance** is receiving requests from the Java Driver/Browser.
2. Check the Neo4j version and the **actually loaded GDS version**.
3. Review `neo4j.conf`, plugin directory contents, and startup logs.
4. Verify the license and user permissions.
5. Check the graph catalog for the exact name, scope, labels, and types.
6. Estimate memory and review heap, page cache, and concurrency settings.
7. Test a small example using `stream` before scaling up or using `write`.

## 13. Scenario Exercises: Choosing How to Run GDS

**Scenario A:** A study group uses Neo4j Desktop and wants to test PageRank on 1,000 nodes. Install the compatible plugin in Desktop, verify `gds.version()`, estimate memory, project the subset, and run `stream`; GDS CE is typically sufficient for learning.

**Scenario B:** A self-managed Neo4j Community production service has 200 million relationships and wants to run analytics concurrently across 32 threads. GDS CE enforces a concurrency cap of 4; simply adding server RAM will not lift the license restriction. Evaluate **GDS EE and database/cluster requirements**, or offload analytical workloads to an appropriate environment/service, then measure real memory and throughput.

**Scenario C:** An enterprise uses AuraDB for transactional data and cannot arbitrarily install plugins. Evaluate **Aura Graph Analytics** (or AuraDS if available and supported in the environment) to project data into an analytics session, run algorithms, and design an appropriate write-back flow. Do not rely on hacks to copy JARs onto an AuraDB host.

**Scenario D:** A Spring application needs relationship recommendations based on similarity scores updated nightly. Schedule a GDS computation job, intentionally write verified results back to Neo4j, and let the Spring API read those validated properties; manage **freshness** between runs and avoid letting heavy analytics jobs contend for resources with transactional queries.

### Self-Check Questions

**1. Does installing the GDS Python Client make `RETURN gds.version()` work on Neo4j Server?**

No. The GDS plugin must be installed/available **on the server side** or run via a supported GDS service environment; the Python Client is only a client.

**2. Is Neo4j Database Enterprise alone enough to use all GDS Enterprise features?**

No. Self-managed GDS Enterprise requires a valid GDS license; verify product editions and actual deployment requirements.

**3. How does `gds.pageRank.stream` differ from `gds.pageRank.write`?**

`stream` returns results without writing algorithm properties to the database; `write` writes results back into the database graph.

**4. Does a projected graph in the catalog automatically pick up new relationships in Neo4j?**

Not by default. You need an appropriate graph refresh/re-projection policy.

**5. Why run `.estimate` before projecting a large graph?**

Because graph projections and algorithm state consume heap; exceeding available memory causes errors or severe GC pressure.

**6. Does running `gds.graph.drop('gdsPractice')` delete the underlying nodes?**

No. Dropping frees the named graph in the GDS catalog; source Neo4j data remains intact.

## 14. Pre-Flight Checklist for Using GDS in Projects

- [ ] Clearly define the algorithmic problem: centrality, community, path, similarity, or ML.
- [ ] Select the **GDS execution environment**: Desktop/server/Docker plugin or Aura analytics service.
- [ ] Confirm **Neo4j version ↔ GDS version** in the compatibility matrix.
- [ ] Distinguish **Neo4j Database edition** from **GDS CE/EE license**, concurrency limits, and advanced features.
- [ ] Install the plugin properly, configure procedures, and restart when required; do not attempt ad-hoc installs on managed databases.
- [ ] Verify `gds.version()`, procedure list, license, and user permissions.
- [ ] Define labels, relationship types, orientation, and properties for an accurate projection.
- [ ] Estimate **heap, CPU, page cache**, test on a small graph, and monitor GC.
- [ ] Choose `stream`/`stats`/`mutate`/`write` according to desired data side effects.
- [ ] Plan graph refreshes when source data changes, managing result freshness.
- [ ] Drop unused catalog graphs, manage operational permissions, and monitor analytical load on the database.
- [ ] Integrate Java Driver/Spring Data Neo4j with appropriate transaction and synchronization models.

## Official References

- [Neo4j Graph Data Science — Introduction](https://neo4j.com/docs/graph-data-science/current/introduction/)
- [GDS Installation — Deployment Options](https://neo4j.com/docs/graph-data-science/current/installation/)
- [Supported Neo4j versions — Compatibility Matrix](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/)
- [GDS Neo4j Server installation](https://neo4j.com/docs/graph-data-science/current/installation/neo4j-server/)
- [GDS Docker installation](https://neo4j.com/docs/graph-data-science/current/installation/installation-docker/)
- [GDS Enterprise Edition — License](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/)
- [Aura Graph Analytics](https://neo4j.com/docs/graph-data-science/current/aura-graph-analytics/)
- [Creating graphs — Projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/)
- [GDS Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/)
- [PageRank — Algorithm and Modes](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)

**Conclusion:** Neo4j Graph Data Science adds a powerful graph algorithm computation layer over **in-memory projections** of the property graph. To use it accurately and safely, verify the **deployment environment, version compatibility, license/edition, permissions, and resources** before projecting graphs and selecting execution modes. GDS delivers the most value when analytical outputs are tied to business objectives, follow a clear data lifecycle, and avoid unintended impact on transactional Neo4j operations serving the application.
