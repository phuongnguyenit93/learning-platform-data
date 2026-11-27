# Disk Characteristics, I/O Latency, and Durable Storage Requirements

## 1. Why Does Storage Design Directly Affect Neo4j?

Neo4j stores the property graph in database files: nodes, relationships, properties, indexes, and transaction information. Cypher operations such as `MATCH`, path expansion, `MERGE`, property updates, and CSV imports can generate vastly different I/O patterns.

A disk may advertise **3 GB/s** sequential read throughput yet perform poorly on small random reads or exhibit very high **p99 synchronous write latency**. In that case, an application can suffer from:

- Graph queries running fast when data is already in the **page cache**, but stalling on first access to uncached pages.
- Write transactions waiting on the disk to acknowledge **transaction log** operations, even while CPU and RAM sit idle.
- Periodic latency spikes during checkpoints flushing dirty pages to the store or when storage hits IOPS throttling.
- A system running fine for days before losing data due to ephemeral volumes, non-durable write caching, or flawed backup procedures.

Within the **Resource Configuration** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson focuses on **disk characteristics, I/O latency, and durable storage requirements**, in the context of relationship queries, indexes/constraints, data ingestion, Neo4j Java Driver, and Spring Data Neo4j.

After this lesson, you will be able to:

1. Explain how Neo4j uses disk across **read**, **write**, **transaction log**, **checkpoint**, and **recovery** paths.
2. Distinguish throughput (MB/s), IOPS, p50/p95/p99 latency, and I/O queue saturation.
3. Select and evaluate HDD, SSD, NVMe, local disks, and network block storage using realistic workloads.
4. Understand why page cache read acceleration **does not replace durable storage requirements**.
5. Calculate headroom, design backup/restore workflows, and identify data-loss and disk-full risks.
6. Measure performance with a verifiable Cypher fixture and a benchmark procedure that never impacts production environments.

> **Version scope:** Examples target Neo4j 5 and later. Setting names, metric availability, backup commands, and Enterprise/Community capabilities vary by version, edition, and managed platform. Do not extrapolate production configurations from demo figures.

## 2. What Does Neo4j Store on Disk?

| Data Group | Purpose | Typical I/O Pattern |
|---|---|---|
| **Graph store** | Node, relationship, and property records and related structures | Random access during graph traversal/property lookups; writes for modified pages |
| **Index files** | Supports looking up nodes/relationships by property, full-text, vector, and other index types | Lookups, updates on writes, potentially distinct I/O patterns per index type |
| **Transaction logs** | Records transaction mutations for recovery and commit tracking | Sequential *append* writes; flush/durability overhead is critical |
| **Checkpoint / store write-back** | Flushes logged changes down to database store files | Bursts of dirty-page writes that can compete with query I/O |
| **Operational logs** | Query log, debug, security, and other operational info | Continuous writes; rate depends on logging configuration |
| **Backups, dumps, snapshots** | Copies for incident recovery | Reads many files and writes to another storage target; can create heavy load |
| **Temp files / admin tasks** | Imports, restores, index population, archive creation | Can cause sudden spikes in disk usage and I/O |

**Never treat the graph store alone as the total disk capacity required.** Transaction logs, indexes, backups, temporary files, growth rate, and operational headroom all shape disk/volume decisions.

A **vector index** or specialized index technology may carry native memory and I/O demands different from standard stores. Your sizing model must account for all features actively in use, not just node and relationship counts.

## 3. Read Path, Write Path, and Recovery Path

~~~mermaid
flowchart TD
    A["Cypher via Browser / Java Driver / SDN"] --> B["Neo4j query runtime"]
    B --> C{"Is the page in Neo4j page cache?"}
    C -->|Hit| D["Read page from RAM"]
    C -->|Miss| E["Locate/load page from storage stack"]
    E --> F["OS filesystem cache / block device"]
    F --> D
    B --> G["Write transaction"]
    G --> H["Transaction log: write and persist per commit protocol"]
    G --> I["Modify store/index pages"]
    I --> J["Dirty pages in cache"]
    J --> K["Checkpoint / write-back to database files"]
    H --> L["Recovery: read valid logs on restart"]
    K --> L
~~~

This diagram illustrates the conceptual flow. It does **not** mean a write transaction must wait for all store pages to be checkpointed before reporting commit. The transaction log enables recovering committed changes even if some store pages have not yet been flushed to disk files.

### 3.1. Graph Reads: Why Random I/O Matters

A query such as:

~~~cypher
MATCH (u:User {userId: $id})-[:BOUGHT]->(o:Order)
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC
LIMIT 10;
~~~

may need to follow relationship records, visit target nodes, and read properties/indexes at non-contiguous disk locations. When the working set does not fully fit in the page cache, **low-latency random reads** can matter far more than a drive's advertised sequential read speed.

However, not every traversal triggers a physical SSD read: the Neo4j page cache and OS-level caches may already hold many pages. **DB Hits** in `PROFILE` measure logical storage access operations, not physical disk read commands.

### 3.2. Graph Writes: Transaction Logs and Indexes Also Consume I/O

A `MERGE` statement may need to:

1. Look up a node/relationship via an index or scan part of the graph.
2. Check constraints and acquire locks to guarantee correctness.
3. Record transaction mutations in the transaction log.
4. Update structures in the store/page cache and indexes.
5. Persist modified pages to store files via background writes/checkpoints.

Consequently, write workloads combine **random reads** (ID lookups) with **log writes** and **store/index page writes**. Batching multiple operations into one transaction can reduce commit overhead, but overly large transactions increase memory usage, lock hold duration, latency, and retry cost.

### 3.3. Log Speed Does Not Equal Backup Speed

Transaction log appends, checkpoints, store copies, and backups follow different I/O paths. Storage with fast append throughput does not guarantee fast backups of hundreds of GiB; backup duration also depends on data reads, network, compression, checksums, and the destination target.

## 4. Comparing Disk Types and Storage Services

| Type | Key Characteristics | What to Verify Before Using |
|---|---|---|
| **HDD** | Low cost/GiB, suitable for sequential/cold storage; mechanical seek makes random I/O slow | Random read/write latency, contention under concurrent transactions, rebuild and recovery times |
| **SATA/SAS SSD** | Random latency typically many times lower than HDD | Write endurance, steady-state writes, controller/cache behavior, performance when nearly full |
| **NVMe SSD** | Supports deep queues and strong IOPS/latency when utilized properly | Power-loss protection, thermal throttling, write amplification, p99 QoS |
| **Network block volume** | Convenient capacity scaling, snapshots, and managed lifecycle | Provisioned IOPS/throughput, burst limits, network latency, jitter, and VM caps |
| **Local ephemeral disk** | Can be very fast; useful for temp tasks or architectures with explicit recovery | Data lost on host/instance replacement; does not provide durability on its own |
| **Object storage** | Well-suited for backups/archives and object retention | Not a default block filesystem for running an active graph store directly |

These are **typical characteristics**, not an absolute ranking. A poorly configured NVMe drive, one that is nearly full, or one using an unprotected volatile write cache can be worse than a volume with steady latency and clear durability guarantees.

**Never choose a disk solely from an "up to 7,000 MB/s" headline.** Neo4j needs real-world workload performance: actual I/O sizes, read/write mix, concurrency, cache hit rates, durable transaction writes, and checkpoint bursts.

## 5. Five I/O Metrics to Distinguish

### 5.1. IOPS

**IOPS** (*Input/Output Operations Per Second*) measures I/O operations per second. At 4 KiB per operation, 10,000 IOPS is roughly 39 MiB/s; at 256 KiB per operation, the same 10,000 IOPS is nearly 2.44 GiB/s. This is arithmetic illustration, not a measured Neo4j speed.

Formula:

\[
\text{Throughput (MiB/s)}
=\frac{\text{IOPS}\times\text{bytes/I/O}}{1024^2}
\]

Hence, an IOPS figure alone does not describe disk capability without knowing **request size**, read/write ratio, and latency.

### 5.2. Throughput

**Throughput** (MiB/s or MB/s—always state units clearly) measures data transferred per second. It matters for imports, backups, restores, large scans, and heavy logging, but it **does not replace** latency for queries issuing small random I/Os.

### 5.3. Latency p50, p95, and p99

Suppose a volume exhibits these **illustrative** metrics:

| Metric | Illustrative Value |
|---|---:|
| Read latency p50 | 0.7 ms |
| Read latency p95 | 3 ms |
| Read latency p99 | 25 ms |
| Durable write latency p50 | 1.5 ms |
| Durable write latency p99 | 80 ms |

Do not misread "p99 = 80 ms" as "every transaction takes 80 ms." It means roughly 99% of measurements had latency **no greater than** 80 ms in that sample, while a small tail can be slower. High tail latency can spike **API p95/p99** sharply if transactions must wait for durable writes.

Some storage systems boast low average latency yet suffer periodic throttling, SSD firmware garbage collection, or network congestion that drives up p99. Always ask for the **latency distribution**, not just the average.

### 5.4. Queue Depth and Saturation

A storage stack can hold many queued requests. As concurrency climbs, throughput initially rises, until reaching a threshold where:

- IOPS/MBps stop scaling proportionally.
- Queue depth, await time, and p95/p99 climb.
- Neo4j/Driver threads stall waiting on I/O even while CPU remains underutilized.

This signals saturation, though you cannot diagnose it from queue depth alone without knowing the device type and workload. An NVMe drive handles deep queues very differently from an HDD.

### 5.5. Confirmed Write Durability

**Write ack latency** matters for transactions: when the server confirms a commit, the storage stack must honor flush and persistence guarantees required by Neo4j's protocol. A device that acknowledges writes quickly by buffering them in volatile memory without power protection **is not equivalent** to storage with power-loss protection or durable caches.

Data durability cannot be inferred from IOPS; verify **flush semantics, filesystem, controller, power protection, volume policy, and recovery tests**.

## 6. Transaction Logs, Write-Ahead Principles, and Data Durability

Neo4j uses the **transaction log** to record transactional changes, enabling crash recovery as well as certain backup and replication mechanisms depending on edition/topology. Conceptually, committed changes must be durably recorded in the log before relying on store pages being completely written out.

### 6.1. Commit Does Not Mean "Every Graph Store Page Has Been fsynced"

An example:

1. Transaction T1 creates node `(:Payment {paymentId:'P100'})`.
2. Neo4j executes the required checks/writes and records to the transaction log.
3. The application receives commit confirmation.
4. Modified store/index pages may be written to files later by background write-back/checkpoints.

If the process crashes between steps 3 and 4, the system can replay the transaction log on startup to recover. Neo4j manages this lifecycle; **never** manually delete or move transaction logs just because store files already contain data.

### 6.2. fsync, Flush, and Controller Caches

Concepts to distinguish:

- **Buffered write:** data may only sit in kernel/controller cache and not yet on durable media.
- **Flush/fsync semantics:** instructs the storage layer to persist data according to the protocol supported by the OS and filesystem.
- **Volatile write cache:** cache memory that loses contents on power loss.
- **Power-loss protection (PLP):** hardware mechanism protecting uncommitted buffered data until written to non-volatile media; actual guarantees depend on the device.

An operational requirement is that storage and filesystem **honor** the synchronization/durability flushes Neo4j relies upon. Never use mount options or controller settings that silently ignore flushes in exchange for prettier benchmark numbers without evaluating data-loss consequences.

> **Caution:** Neo4j provides ACID guarantees when running on infrastructure that upholds supported storage assumptions. A device, kernel, filesystem, or block volume service that falsely reports "written" can break those guarantees. Software durability promises do not substitute for verifying infrastructure durability.

### 6.3. Tx Log Retention and Rotation

Transaction logs grow with writes. They are rotated and retained according to Neo4j/version policies, which can tie into backup and recovery workflows.

- **Too-short retention** can disrupt certain incremental backup workflows, depending on version/tools.
- **Too-long retention** can fill disks under heavy write workloads.
- **Manual deletion** can destroy recovery capability; never run `rm` on active transaction logs.
- **Sustained write bursts** require monitoring log growth rate rather than just checking database size once a day.

Only change retention policies after understanding backup/recovery workflows, edition capabilities, and storage costs; verify exact setting names for your Neo4j version.

## 7. Checkpoints: Why Do Large Write Bursts Occur?

The page cache holds graph/index pages to serve queries. Modified pages become **dirty pages**; Neo4j periodically writes them back to store files and checkpoints to establish recovery points.

~~~mermaid
sequenceDiagram
    participant App as Java Driver
    participant DB as Neo4j
    participant Log as Transaction log
    participant Store as Store/index files
    App->>DB: executeWrite(...)
    DB->>Log: Write transaction record
    Log-->>DB: Durable write per protocol
    DB-->>App: Commit succeeded
    Note over DB,Store: Store pages may still be dirty in cache
    DB->>Store: Background write / checkpoint
    Note over DB,Log: Recovery may replay logs after checkpoint
~~~

**A checkpoint is not a backup.** It bounds crash-recovery work and synchronizes store state, but it provides no independent copy if a disk fails or data is accidentally deleted.

| Scenario | Observable Behavior |
|---|---|
| Continuous property-update transactions | Heavy transaction log writes; store/index pages marked dirty |
| Checkpoint occurs on near-saturated storage | p95/p99 latency rises; queue depth and write I/O climb together |
| Sudden process stop | Startup must verify/replay logs; recovery time scales with pending work |
| Near disk-full due to logs/backups | Write errors or database becomes unable to serve traffic normally |

Do not assume "more frequent checkpoints are always better." Running them too often can amplify write load, while running them too infrequently increases recovery time and log space requirements. Measure on real workloads and consult version guidance.

## 8. Neo4j Page Cache Differs from Durable Storage

The **Neo4j page cache** is memory serving hot data/index pages. It reduces storage reads, but it **does not replace** transaction logs, checkpoints, or backups.

| Component | Purpose | What Happens on Power Loss/Restart? |
|---|---|---|
| **JVM heap** | Java objects, query state, part of transaction memory | Runtime contents are lost when the process stops |
| **Neo4j page cache** | Holds store/index pages in RAM | Cached RAM pages are lost; durable data must exist on storage/logs |
| **OS filesystem cache** | Caches file pages in kernel memory | Lost on OS restart; not a backup |
| **Persistent block storage** | Persists database/log files long-term | Must ensure flush compliance, integrity, and availability |
| **Backup in separate domain** | Recovers from full volume loss or accidental deletion | Requires restore drills, access controls, and retention |

When inspecting queries with `PROFILE`, you may see:

- `DB Hits`: logical engine accesses; not OS disk reads.
- `Page Cache Hits/Misses`: degree to which pages were found in cache, if supported by edition/runtime.
- `Memory (Bytes)`: operator intermediate memory; not equivalent to page cache size.

**A high page cache hit ratio does not guarantee fast writes**: transaction log flushes and write-back bursts can still stall on slow storage. Conversely, a high miss ratio with acceptable latency can mean fast storage or queries that are not I/O-bound under those conditions. Always combine application and OS metrics.

## 9. Persistent Storage in Docker, Kubernetes, and Cloud

### 9.1. Containers Do Not Make Data Persistent Automatically

If Neo4j writes database files into a container's ephemeral writable layer, data disappears when the container is replaced. On Docker, mount persistent volumes to the appropriate data/log directories per Neo4j's image/version documentation.

An **illustrative** example:

~~~yaml
services:
  neo4j:
    image: neo4j:5
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs

volumes:
  neo4j-data:
  neo4j-logs:
~~~

This file is not a complete production configuration: it lacks TLS, secrets, RAM limits, auth, health checks, and backups. Before deploying, verify image version and volume ownership/permissions.

In Kubernetes, volumes must use an appropriate `PersistentVolumeClaim`/StorageClass; **never** assume `emptyDir` survives pod rescheduling onto another node. Also check filesystem type, access modes, attach/detach behavior, availability zones, and node-failure handling.

### 9.2. A Persistent Volume Is Still Not a Backup

A cloud block volume can survive VM restarts, yet it still cannot protect against:

- Accidental database drops or privileged account overwrites.
- Application bugs writing millions of corrupted mutations.
- Volume loss or cloud zone failures outside the promised SLA.
- Improperly taken snapshots yielding inconsistent, unrecoverable copies.

Therefore, maintain supported backups in an independent failure domain, test restores, and enforce clear retention policies.

### 9.3. Avoid "Optimizing" Transaction Logs onto Ephemeral Disks

Moving transaction logs onto fast ephemeral disks that vanish on node replacement **can break recovery capability** unless paired with a separately designed and verified storage/replication mechanism. Separating logs from store files to reduce I/O contention only makes sense when **both** meet durability requirements and have a consistent recovery procedure.

## 10. Choosing a Storage Layout by Goal

Operational designs typically separate:

- **Data/graph/indexes:** needs a volume with low random-read latency, sufficient IOPS, and room for store growth.
- **Transaction logs:** needs steady write latency, durable flushes, and capacity matching write rate/retention.
- **Operational logs:** separate rotation policy from transaction logs; never let debug logs fill the data volume.
- **Backups/archives:** prioritize a separate failure domain, retention, and access control; never keep the sole backup next to the live database.
- **Temporary/import space:** headroom for ingestion/dump/restore pipelines and maintenance spikes.

Splitting directories across **multiple filesystems/volumes** helps manage capacity and isolate space, but it **does not improve latency** if all volumes share the same underlying device or cloud IOPS quota. Moreover, separating store and transaction logs requires backup/snapshot plans that maintain cross-volume consistency.

**Principle:** **consistent recoverability** takes precedence over a clever-looking partition layout.

## 11. Sizing Capacity and Headroom

Storage needs go beyond `database size`. A simple planning formula:

\[
C_{\text{provisioned}}
\geq (C_{\text{store}} + C_{\text{indexes}} +
C_{\text{txlogs}} + C_{\text{temp}})\times(1+h)
\]

Where `h` is a headroom factor chosen based on growth rate, volume expansion lead time, and burst workload risk.

**Purely hypothetical example:**

| Line Item | Capacity |
|---|---:|
| Graph store | 120 GiB |
| Indexes | 30 GiB |
| Transaction logs retained per policy | 20 GiB |
| Estimated import/temp/index population | 10 GiB |
| Base total | **180 GiB** |
| Illustrative 40% headroom | **72 GiB** |
| Calculated provisioning target | **252 GiB** |

**252 GiB is not a fixed recommended configuration.** In other workloads, indexes can exceed the graph store; offline imports may need extra room; and backups stored on the same filesystem must be added to the formula. Also evaluate volume quotas, performance degradation near full capacity, and expansion costs.

### Tracking Capacity Over Time

| Metric | Question to Answer |
|---|---|
| Used / free bytes / % | Is there enough space left for writes and growth? |
| Growth rate GiB/day | When will warning thresholds or quotas be reached? |
| Tx log bytes/day and retention | If writes triple, will the log disk hold? |
| Index size by type | What impact do growing text/full-text/vector indexes have? |
| Temp space during backup/restore/import | Do scheduled jobs push usage over limits? |
| Filesystem/volume expansion lead time | How early must alerts fire? |

Never wait until a volume hits 99% to act. Alert thresholds must account for **headroom during rapid write bursts**, not merely average daily growth.

## 12. Inspecting Neo4j Configuration Without Modifying the System

If account and edition permit, run **read-only** queries:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.directories.data',
  'server.directories.transaction.logs.root',
  'server.directories.logs',
  'server.memory.pagecache.size',
  'server.memory.heap.max_size'
]
RETURN name, value
ORDER BY name;
~~~

Displayed values and availability depend on version, deployment model, and admin privileges. Neo4j running in containers or managed services may map underlying physical paths/volumes differently from how they appear in the UI.

Inspect active databases (if authorized):

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

These commands **do not benchmark disk speed**; they only verify configuration and status. Evaluating latency requires OS metrics, cloud block storage metrics, query logs, page cache, transaction metrics, and Java Driver metrics.

### Reference Configuration Snippet

~~~properties
# neo4j.conf — example only for a hypothetical environment.
# Do not apply without knowing RAM, store size, and container limits.
server.memory.heap.initial_size=4G
server.memory.heap.max_size=4G
server.memory.pagecache.size=8G
~~~

**Do not** set `heap + page cache` equal to total RAM and forget OS/native index memory and filesystem buffers. Raising page cache can reduce read misses while starving the OS or other needs; review estimation docs and actual metrics before changing values.

On a host with administrative access, the utility:

~~~text
neo4j-admin server memory-recommendation
~~~

can provide a starting point for memory allocation; it **does not** choose disk hardware or verify durability.

## 13. Verifiable Fixture: Small-Scale Graph Reads and Traversals

Use a dedicated practice database—never wipe production data. This dataset validates Cypher **correctness** before latency testing; 1,000 nodes is not enough to prove SSD/volume performance.

### 13.1. Reset Only the Fixture

~~~cypher
DROP CONSTRAINT qa003_storage_id IF EXISTS;
~~~

~~~cypher
MATCH (n:QA003Storage)
DETACH DELETE n;
~~~

### 13.2. Create a Unique Constraint and 1,000 Nodes

~~~cypher
CREATE CONSTRAINT qa003_storage_id IF NOT EXISTS
FOR (n:QA003Storage)
REQUIRE n.id IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 1000) AS i
CREATE (:QA003Storage {
  id: i,
  bucket: i % 10,
  score: i % 10,
  payload: 'sample-' + toString(i)
});
~~~

Create a directed linear chain:

~~~cypher
UNWIND range(1, 999) AS i
MATCH (a:QA003Storage {id:i})
MATCH (b:QA003Storage {id:i + 1})
CREATE (a)-[:QA003_NEXT]->(b);
~~~

Subsequent queries can observe **NodeIndexSeek**, relationship expansion, and property reads. The planner may still pick different operators depending on version/dataset; do not force a rigid plan assumption.

### 13.3. Verify Results to Rule Out Data Errors

~~~cypher
MATCH (n:QA003Storage)
RETURN
  count(n) AS totalNodes,
  sum(n.id) AS sumIds,
  sum(n.score) AS sumScores,
  count(DISTINCT n.bucket) AS buckets;
~~~

| totalNodes | sumIds | sumScores | buckets |
|---:|---:|---:|---:|
| **1,000** | **500,500** | **4,500** | **10** |

Explanation: `1 + 2 + ... + 1000 = 500500`; `score = i mod 10` cycles 0 through 9 across 100 repetitions, so `100 × (0+1+...+9) = 4500`.

~~~cypher
MATCH ()-[r:QA003_NEXT]->()
RETURN count(r) AS totalRelationships;
~~~

**Answer:** `totalRelationships = 999`.

Verify a 3-hop traversal:

~~~cypher
MATCH (start:QA003Storage {id:1})
      -[:QA003_NEXT*1..3]->(dest:QA003Storage)
RETURN DISTINCT dest.id AS reached
ORDER BY reached;
~~~

**Answer:** three records `2`, `3`, `4`. Correct hop count and relationship direction matter more than runtime on a tiny fixture.

## 14. Measuring Read Queries: Page Cache and I/O

### 14.1. EXPLAIN Does Not Execute the Query

~~~cypher
EXPLAIN
MATCH (n:QA003Storage)
RETURN sum(n.score) AS totalScore;
~~~

`EXPLAIN` outputs the estimated plan without reading the full dataset as during execution; do not use it as an actual I/O measurement.

### 14.2. PROFILE Actually Executes the Query

~~~cypher
PROFILE
MATCH (n:QA003Storage)
RETURN sum(n.score) AS totalScore;
~~~

**Answer:** `totalScore = 4500`. Check `Rows`, `DB Hits`, and—when supported by runtime/edition—`Page Cache Hits/Misses`. Repeat the same query and record results.

~~~cypher
PROFILE
MATCH (start:QA003Storage {id:1})
      -[:QA003_NEXT*1..3]->(dest:QA003Storage)
RETURN count(DISTINCT dest) AS reached;
~~~

**Answer:** `reached = 3`.

### 14.3. Recording Sheet Instead of Guessing

| Run | Condition | DB Hits | Page cache hits | Page cache misses | Client latency |
|---|---|---:|---:|---:|---:|
| 1 | First observation | *(measure)* | *(if available)* | *(if available)* | *(measure)* |
| 2 | Same query after warmup | *(measure)* | *(if available)* | *(if available)* | *(measure)* |
| 3..N | Steady-state | *(measure)* | *(if available)* | *(if available)* | *(measure)* |

Never fill **measured** columns with fabricated numbers. If `DB Hits` stays nearly constant while misses drop on repeats, the page cache is a plausible explanation for improved latency. If per-query page cache metrics are unavailable, use system metrics **over an isolated load window**—never attribute whole-DBMS multi-user counters to a single request.

**Caution on cold/warm state:** right after `CREATE`, pages may already be hot. Even restarting Neo4j does not guarantee a "cold disk," due to the OS filesystem cache and page cache warmup mechanisms. Never drop OS caches or restart production to create benchmarks.

### 14.4. Do Not Infer Disk Throughput from PROFILE DB Hits

`DB Hits` measures logical work in the Neo4j query runtime. The same 10,000 DB Hits might be served mostly from RAM on one run and trigger many page cache misses on another. Physical disk reads depend on file layout, OS cache, read-ahead, indexes, and storage hardware.

To obtain block-device latency/IOPS, gather metrics from the **OS/storage provider**, rather than converting `DB Hits` into IOPS with an arbitrary multiplier.

## 15. Measuring the Write Path and Commit Latency via Java Driver

The objective is to measure **how long the application waits for a transaction commit**, while recognizing the boundaries of that measurement.

A small write query on the fixture:

~~~cypher
UNWIND range(1, 100) AS i
MATCH (n:QA003Storage {id:i})
SET n.benchMarker = 'sample-run-001';
~~~

After execution, exactly 100 nodes have `benchMarker = 'sample-run-001'`; total node count remains 1,000. This is **not** an isolated physical durability benchmark: server and client also perform Cypher processing, index lookups, networking, and transaction management.

Java Driver 5.x example, given an initialized `Driver`:

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public static void measureCommit(
        Driver driver, String database) {

    // Different marker per run to ensure an actual mutation.
    String marker = UUID.randomUUID().toString();

    try (Session session = driver.session(
            SessionConfig.forDatabase(database))) {

        long start = System.nanoTime();
        session.executeWrite(tx -> {
            tx.run("""
                UNWIND range(1, 100) AS i
                MATCH (n:QA003Storage {id:i})
                SET n.benchMarker = $marker
                """, Values.parameters("marker", marker))
                .consume();
            return null;
        });

        long elapsed = System.nanoTime() - start;
        System.out.printf("Commit round trip: %.3f ms%n",
            elapsed / 1_000_000.0);
    }
}
~~~

**This measurement includes** Driver overhead, networking, parameter serialization, connection selection, index lookups, store/index updates, and transaction commit. It **does not isolate disk fsync**. With `executeWrite`, the callback can be retried on transient errors; elapsed time may include multiple attempts. Generating `marker` **before** the callback keeps the update deterministic across retries.

Also record in the test environment:

- Client-side **managed transaction** p50/p95/p99 latency, retry counts, and error rates.
- Successful transactions/s, rather than just rows submitted.
- Disk write latency, write IOPS, bytes/s, queue depth, and checkpoint timestamps.
- CPU/GC, page cache misses, and locks; write throughput can be bottlenecked at these layers rather than storage.
- Transaction log disk growth and recovery time in controlled tests.

### Do Not Compare Unbalanced Workloads

The following two queries are **not equivalent**:

~~~cypher
CREATE (:QA003Storage {id:999999});
~~~

~~~cypher
MERGE (n:QA003Storage {id:999999})
SET n.benchMarker = 'x';
~~~

`CREATE` is not a unique-key `MERGE`; one run may insert a new node while the next only matches and updates. You cannot blame timing differences purely on disk when DB Hits, index lookups, and write volumes differ. Always restore identical data preconditions before any real benchmark.

## 16. Monitoring I/O Across Neo4j and Infrastructure Layers

### 16.1. Metrics to Collect Together

| Layer | Useful Metrics | Correct Interpretation |
|---|---|---|
| **Java/SDN Application** | p50/p95/p99 query/commit, retries, error rate, pool wait | Client latency includes network/mapping, not just server time |
| **Neo4j Query** | `PROFILE` Rows/DB Hits, index vs scan plans | Shows logical graph access cost |
| **Neo4j Page Cache** | Hits, misses, hit ratio, usage ratio, faults | Indicates working-set warmth of data/indexes |
| **Neo4j Transactions/Checkpoints** | Transaction throughput, checkpoint duration/occurrences, log activity | Reveals write traffic and write-back bursts |
| **CPU/Heap/GC** | CPU saturation, memory, GC pauses, transaction memory | Slowdowns may stem from CPU/GC before hitting storage |
| **OS/Block Device** | Read/write IOPS, MiB/s, await latency, queue depth, utilization | Confirms whether the physical I/O path is actually saturated |
| **Cloud Volume** | Provisioned IOPS/throughput, burst credits, throttling, errors | An instance can hit volume quotas before physical hardware saturates |
| **Filesystem** | Free bytes/inodes, I/O errors, journal and mount status | Disk-full or read-only filesystems block writes |

Depending on Neo4j edition, detailed metrics and tracing may require extra configuration. Do not assume every counter appears in `PROFILE`.

### 16.2. Reference OS Tools

On administrator-managed Linux hosts, these **read-only** commands are often useful:

~~~bash
# View device names, sizes, and mountpoints.
lsblk -o NAME,SIZE,TYPE,ROTA,MOUNTPOINT

# View filesystem capacity.
df -h

# With sysstat installed: per-second device statistics.
iostat -xz 1
~~~

`iostat` does not separate Neo4j I/O from other processes on its own; correlate mountpoints, devices, and load. On NVMe or virtualized storage, `%util` near 100% **does not always** mean the device is maxed out; also inspect queue depth, await, IOPS, and throughput.

In Kubernetes/cloud environments, combine metrics from **PVCs**, StorageClasses, VM quotas, disk IOPS limits, and provider throttling. If OS access is unavailable (Aura/managed services), use provider-supported dashboards and document observation limits clearly.

## 17. Bottleneck Triage Table: Storage, Cache, or Cypher?

| Symptom | Plausible Hypothesis | Verification Check |
|---|---|---|
| First read slow, subsequent fast; DB Hits unchanged | Page cache was cold on first run | Track page cache misses/hits and control warmup conditions |
| Many page cache misses, high random read latency | Working set exceeds cache or slow random storage | Check cache usage/misses, OS read IOPS, query/index structure |
| Very high DB Hits even with warm cache | Plan is scanning/expanding too much data | `EXPLAIN`/`PROFILE`; check indexes, cardinality, filters |
| High write p99 coinciding with high disk flush latency | Log/volume durable write bottleneck | Correlate slow commits with storage latency, checkpoints, throttling |
| Periodic p99 spikes matching checkpoint activity | Checkpoint/write-back I/O contention | Plot checkpoint duration, write bytes, queue depth over time |
| CPU saturated while storage I/O has headroom | Heavy Cypher, constraint, or GC processing | Optimize Cypher, batching, indexes, and concurrency |
| Pool wait grows while server I/O stays low | Long-held connections/transactions or network issue | Check Driver pool, result consumption, and network RTT |
| Cloud volume near IOPS cap / burst credits depleted | Cloud-layer storage quota | Inspect provider metrics, provision higher IOPS or switch volume |
| Log disk nearly full while store barely grew | Excessive log retention or write churn | Review log policy and volume; never delete logs manually |
| Data vanishes on container restart | Ephemeral volume or misconfigured mount | Check PVC/volume config, restore tests, and failure domains |
| Backup file exists but restore fails | Inconsistent snapshot/backup or missing components | Use supported tools and run independent restore drills |

A single incident can involve **multiple bottlenecks**. For example, a missing index causes `MERGE` to issue extra random reads, followed by slow disk writes at commit time. The fix may require **proper constraints/indexes + steady-latency disks**, not merely adding RAM or buying NVMe.

## 18. Backup, Restore, RPO, and RTO: How Durable Is Enough?

### 18.1. Distinguishing Recovery Capabilities

- **Transaction durability:** ensures committed data is not lost across failure modes the platform/software commits to survive.
- **Backup:** an independent copy for recovering from data deletion/corruption, full volume loss, or human error.
- **HA/replication:** improves service availability if one server fails; **does not replace backups**, because logical errors or accidental deletes get replicated too.
- **RPO (Recovery Point Objective):** maximum acceptable data loss measured in time.
- **RTO (Recovery Time Objective):** target time to restore service operation after an incident.

For example, if a service requires **RPO ≤ 5 minutes** and **RTO ≤ 30 minutes**, a once-daily backup **cannot** meet that RPO on its own; design appropriate backup/log/replication mechanisms and test recovery. Never put SLAs on paper without rehearsing them.

### 18.2. How Do Neo4j Backups and Dumps Differ?

| Option | Characteristics | When Suitable |
|---|---|---|
| **Online database backup** | Supported Neo4j backup tool can back up a live database in eligible editions/versions | Production workloads needing scheduled backups with minimal disruption |
| **Offline dump** | Creates an archive while the target database is stopped per tool requirements | Copying/restoring/testing/migrating within maintenance windows |
| **Coordinated storage snapshot** | Storage-level snapshot requiring store + log consistency per Neo4j-supported procedure | Infrastructure with consistent quiesce/snapshot support and tested restores |
| **Copying data directory while DB writes** | Can capture inconsistent file states | **Never use as a production backup** |

Run `neo4j-admin database backup` or `neo4j-admin database dump` using the **exact syntax for your running version and edition**. Never copy examples from another version and assume backups will restore cleanly. For clusters, follow topology- and database-specific backup guidance.

### 18.3. Restore Verification Matters More Than a "Green Backup Job"

A minimum verification workflow:

1. Store backups in a **separate failure/identity domain** from production Neo4j.
2. Restrict read/delete permissions on backups and enforce encryption at rest/in transit.
3. Periodically restore into an **isolated environment** using supported versions/tools.
4. Run reconciliation queries checking node counts, relationship counts, constraints/indexes, and representative business invariants.
5. Measure **actual elapsed time** from restore start until the application can read/write to validate RTO.
6. Record the actual recovery point and unrecoverable data window to validate RPO.
7. Test failure scenarios too: missing backup, full volume, unavailable secrets/KMS, schema/version mismatches.

Never run `DETACH DELETE`, drop database, or pull power in production to simulate incidents. Execute failure drills in approved staging/DR labs.

## 19. Neo4j Disk Selection Checklist

Before signing off on a storage design, confirm:

- [ ] Primary workload identified: OLTP writes, random traversals, full scans, imports, or analytics?
- [ ] Measured IOPS, MiB/s, and p50/p95/p99 under a realistic **mixed workload**?
- [ ] Confirmed flush/fsync durability, controller cache, PLP, and supported filesystem?
- [ ] Provisioned capacity and headroom for stores, indexes, transaction logs, temp space, and backups?
- [ ] Storage volume persists across pod/VM restarts and replacements as designed?
- [ ] Alerts configured for free bytes, log growth, queue depth, write latency, and throttling?
- [ ] Supported backup/restore strategy verified for the exact Neo4j version/edition?
- [ ] Backups stored in a separate failure domain and **restore drills** executed?
- [ ] RPO/RTO targets defined and validated through testing?
- [ ] Page cache/heap settings leave sufficient RAM for OS/native indexes?
- [ ] Write concurrency is not pushed past the point where throughput plateaus while p99 spikes?
- [ ] Runbooks exist for disk-full, I/O errors, read-only filesystems, and volume expansion?
- [ ] All config/volume changes tested in staging with a rollback plan?

## 20. Exercises with Answers

### Exercise 1 — MB/s or IOPS?

A drive achieves 2 GiB/s sequential read throughput but has high p99 random read latency. Neo4j traversal queries with page cache misses are running slowly. Can you conclude the drive is fast enough?

**Answer:** No. Sequential throughput does not represent small random accesses. Measure random IOPS, p95–p99 latency, page cache misses, and query `DB Hits`.

### Exercise 2 — Capacity Calculation

Graph store is 120 GiB, indexes 30 GiB, tx logs 20 GiB, and temp space 10 GiB. With 40% headroom on the base total, what is the calculated allocation?

**Answer:** Base total `120+30+20+10=180 GiB`; headroom `72 GiB`; illustrative allocation **252 GiB**. This excludes backups stored on the same volume or abnormal growth.

### Exercise 3 — Warm Runs and Disk Reads

Two `PROFILE` runs of the same query have identical `DB Hits`, but page cache misses drop sharply on the second run. What likely changed?

**Answer:** Logical work is identical, but required pages were already in the page cache. That is a reasonable explanation for lower read latency; do not claim exact disk I/O milliseconds without storage-layer measurements.

### Exercise 4 — Commit Returned Before Store Pages Checkpointed

A transaction commits successfully before the server finishes checkpointing every dirty page. Does that automatically mean the data is not durable?

**Answer:** No. Neo4j uses the transaction log to preserve recoverability; store checkpoints do not have to coincide with every commit. Durability still relies on storage honoring durable write/flush guarantees.

### Exercise 5 — Kubernetes emptyDir

Neo4j runs in a pod storing data on `emptyDir`. When the pod moves to another node, can data be considered safe just because the service restarts automatically?

**Answer:** No. `emptyDir` is tied to pod lifecycle and does not replace a persistent volume. Use a proper PVC/StorageClass and backup/restore process.

### Exercise 6 — Two Divergent Signals

Neo4j shows a 99.8% page cache hit ratio, yet commit p99 = 200 ms while storage write latency climbs and checkpoints are running. Should you immediately increase page cache?

**Answer:** Not yet. Hit ratio is already high; investigate durable write latency, checkpoint/write-back activity, storage throttling, and transaction logs. Increasing page cache does not directly speed up write flushes.

### Exercise 7 — Does HA Replace Backups?

A system runs a 3-server cluster. A DBA accidentally deletes the graph with privileged Cypher, and the deletion replicates. Can HA replication recover the old data automatically?

**Answer:** No. Replication propagates erroneous mutations too. You need point-in-time backups and tested restore procedures isolated from live data.

### Exercise 8 — Fixture Verification

The fixture in Section 13 has `1000` nodes, `999` `QA003_NEXT` relationships, and `score = id mod 10`. What is `sum(score)`, and which IDs are reached in 1–3 hops from `id=1`?

**Answer:** `sum(score) = 4500`, and the reachable IDs are **{2,3,4}**. If results differ, fix/verify the dataset before using the fixture for I/O testing.

### Exercise 9 — Disk Not Full Yet p99 Spikes

A cloud volume still has 40% free space, but provisioned IOPS hit their ceiling and queue depth climbs. Which is more likely: out of space or out of performance quota?

**Answer:** Immediately, **performance quota/IOPS**, not disk space. You may need to optimize queries/batches/caching or change the volume type and provisioned IOPS; verify across system-wide metrics.

### Exercise 10 — Is a Live Copy Always Consistent?

A script copies graph store files while Neo4j is actively writing, without backing up or synchronizing transaction logs via a supported procedure. Can this be considered a verified backup?

**Answer:** No. The copy can be inconsistent; use Neo4j's supported backup tool for your edition/version or a coordinated snapshot with successful restore verification.

## 21. Cleaning Up Practice Data

Run only in the **test database** containing the `QA003Storage` fixture—never on a production graph:

~~~cypher
MATCH (n:QA003Storage)
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa003_storage_id IF EXISTS;
~~~

Verify:

~~~cypher
MATCH (n:QA003Storage)
RETURN count(n) AS remaining;
~~~

**Answer:** `remaining = 0`. Benchmark properties written to the 100 nodes are deleted along with the nodes. If tests created extra nodes with the fixture label via `CREATE/MERGE`, those are removed as well. Never run this on a database sharing demo labels with real data.

## 22. References and Final Principles

- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/): storage characteristics, memory, and system tuning.
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/): heap, page cache, and OS/native memory allocation.
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): setting names and data/transaction log paths by version.
- [Neo4j Operations Manual — Monitoring metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): page cache, checkpoint, transaction, and key metric groups.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): online backup, dump, restore, and verification per edition/version.
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/): containers, volumes, configuration, and file permissions.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`/`PROFILE`, `DB Hits`, page cache, and memory.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): measuring transactions, reusing `Driver`, batching, and client results.

**Key takeaway:** Do not choose Neo4j disks based solely on peak MB/s. Measure **random I/O, p95/p99 durable write latency, page cache utilization, transaction logs, and checkpoints** under realistic graph workloads. Committed data requires storage that honors durable write semantics; and **restorable backups** are what protect against volume loss, accidental deletion, or operational errors. Good performance and recoverability are **two distinct goals that must be verified independently**.
