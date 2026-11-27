# Write, Storage, Rebuild, and Index Streaming Costs in Apache Cassandra

## 1. The problem: indexes help reads, but who pays the cost?

In Apache Cassandra, data is distributed across nodes by **partition key**, replicated per **replication factor (RF)**, and organized into **wide-column partitions**. When a query provides the right partition key, Cassandra locates the target replicas fairly directly. When you want to filter on a non-key column, a secondary index can enable searching.

For example, suppose an application has an orders-by-customer-and-day table: `WHERE tenant_id = ? AND order_day = ?` targets one partition, yet the business also wants to filter `status = 'PAID'`. An index on `status` can help filter results. However, from the moment an index is created, **every mutation touching that column also creates extra storage and maintenance work**.

Four primary cost categories in this lesson:

1. **Writes:** processing indexed values on replicas, updating in-memory and/or auxiliary structures.
2. **Storage:** additional index data on disk alongside data SSTables, plus temporary workspace during flush, compaction, and rebuilds.
3. **Rebuilding:** when creating an index on an existing table, losing/corrupting an index, or changing config, nodes must reprocess existing data.
4. **Streaming/transfer:** during cluster bootstrap, node replacement, token range rebalancing, or repair, data files and index components may need to be streamed over the network or rebuilt at the destination.

**Key message:** an index is never "free after `CREATE INDEX`." It trades query read cost for costs along the write path, disk, CPU, memory, operations, and sometimes network bandwidth.

> Example scope: Apache Cassandra 5.0 with **Storage-Attached Indexing (SAI)**, contrasted with **legacy secondary indexes (2i)**. Cassandra 4.x lacks the same built-in SAI as Cassandra 5.0, so verify your exact version and distribution before applying syntax or operational expectations.

## 2. Distinguishing primary index, 2i, SAI, and query tables

| Mechanism | Where stored/maintained | When useful | Primary costs |
|---|---|---|---|
| **Primary index** by partition key | Base SSTable lookup structures present on every replica holding the data | Queries identifying the partition | Baseline cost of every Cassandra table |
| **Traditional secondary index (2i)** | **Local** structures on each node, implemented as hidden index tables | Carefully vetted queries on non-key columns | Writes/maintenance of hidden table, disk, scanning token ranges when partition is unspecified |
| **Storage-Attached Indexing (SAI)** | Memtable indexes and SSTable-attached components on replicas | Non-key column filtering; Cassandra 5.0 | Index maintenance per mutation, flush, compaction; memory/disk footprint; distributed read cost |
| **App-maintained denormalized table** | A separate CQL table with a query-aligned partition key | Stable query patterns requiring direct keyed access | Extra table writes, separate replication, app-managed cross-table consistency |

**Both SAI and 2i maintain local index structures on the nodes holding the corresponding data.** A query lacking a partition key can still contact many replicas and token ranges. Do not confuse "distributed index" with a single global cluster directory that turns every query into a point lookup.

A table like `orders_by_tenant_day` can perform well when narrowing to a tenant and day and then filtering with SAI. Yet `WHERE status = 'PAID'` across the whole cluster remains a distributed query even with an index.

## 3. The write path and where index work occurs

Suppose a client executes:

~~~cql
UPDATE shop.orders_by_tenant_day
SET status = 'PAID'
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND order_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;
~~~

Conceptually, the write path comprises:

1. **Coordinator** resolves token/replicas from `(tenant_id, order_day)` and forwards the mutation to replicas.
2. **Each receiving replica** executes Cassandra's write path: commit log and memtable for base data.
3. **Indexed columns are processed at the replica.** With SAI, the mutation is reflected in the memtable index; SAI's write path is synchronous with data writes. With 2i, the node maintains local index structures per 2i mechanics.
4. Once the **write consistency level** (`ONE`, `LOCAL_QUORUM`, ...) is satisfied, the coordinator acknowledges the client. Consistency levels do not bypass index work occurring on replicas.
5. Later, **flush** and **compaction** create or rewrite on-disk index structures; this cost can materialize **after** the client request receives its ACK.

~~~mermaid
flowchart TD
    A["Client INSERT/UPDATE/DELETE"] --> B["Coordinator: identify replicas"]
    B --> R1["Replica 1"]
    B --> R2["Replica 2"]
    B --> R3["Replica 3"]
    R1 --> W1["Commit log + data memtable"]
    R2 --> W2["Commit log + data memtable"]
    R3 --> W3["Commit log + data memtable"]
    W1 --> I1["Maintain local index"]
    W2 --> I2["Maintain local index"]
    W3 --> I3["Maintain local index"]
    I1 --> F1["Flush: SSTable and index files"]
    I2 --> F2["Flush: SSTable and index files"]
    I3 --> F3["Flush: SSTable and index files"]
    F1 --> C["Later compaction / streaming / rebuild"]
    F2 --> C
    F3 --> C
~~~

This diagram illustrates **RF = 3**, not a fixed internal ordering for every indexing mechanism. In practice, replicas may hold different sets of data, flush/compaction schedules vary, and SAI/2i components are managed differently.

### Why do many indexes slow down writes?

With SAI, each indexed column must record values and map them to the appropriate keys/row IDs, maintain extra in-memory structures, and write disk files during flush. More indexes increase estimated memtable heap usage, causing flushes to trigger sooner; more smaller SSTables can create extra compaction work.

With 2i, maintaining hidden index tables also consumes CPU, local writes, and background resources. Regardless of implementation, **every index adds another write path**.

Never apply a naive formula like "n indexes means write latency grows by exactly n×." Actual cost depends on data types, modified columns, value lengths, distinct value counts, TTLs, tombstones, memory, compaction strategy, background load, and Cassandra version.

## 4. Modeling write and replication costs

An estimation model for capacity budgeting:

~~~text
Client logical mutations/sec       = W
Replication factor (RF)            = R
Indexed columns touched per write  = I

Replica data mutations/sec         ≈ W × R
Local index update operations/sec  ≈ W × R × I
~~~

This model only **counts potential work units** when every mutation modifies all I indexed columns; it is neither an actual Cassandra metric nor a formula for latency or network packets.

**Illustrative example:** a workload with 1,200 updates/sec, RF = 3, where each update modifies two indexed columns. The cluster handles roughly 3,600 replica-mutations/sec and up to 7,200 local index operations/sec under the simplified model. If only one indexed column changes, work scales down accordingly.

Avoid a very common multiplication mistake: **adding two indexes does not mean the system sends base data twice across replicas**. Writes still replicate once per partition/RF; on each replica, indexes are maintained locally **from the received mutation**. Extra network traffic shows up mainly via rebuilds, streaming, internode data, and distributed queries—not a separate broadcast per index on every write.

### Signs the write path is strained by indexes

- P95/P99 write latency rises after `CREATE INDEX` or adding multiple indexed columns.
- CPU/heap usage, memtable flushes, and compactions increase.
- SSTable count and compaction queue grow; disk I/O approaches saturation.
- Latency spikes during rebuilds or bootstraps coinciding with heavy write traffic.
- Increased garbage collection or heap pressure when indexing many columns/values.

Always measure **before/after under the same workload shape**. An index is not automatically the sole culprit when write latency increases.

## 5. Storage cost: index footprint multiplied by replicas and time

### 5.1. Indexes do not replace base data

Indexes store lookup information such as column values and row/partition mappings, while Cassandra still retains base data in SSTables. Creating indexes increases total disk usage on nodes.

- **2i** stores indexes in separate hidden tables on each node. Footprint depends on indexed data, hidden table layout, and maintenance overhead.
- **SAI** stores SSTable-attached index components, consisting of per-column components plus SSTable-level shared components. Sharing saves space relative to duplicating full metadata per index.
- **Replication** places data and local indexes across multiple replicas. A table with 500 GB of logical base data at RF = 3 consumes far more than 500 GB total disk across the cluster: account for three copies of data, indexes, compaction overhead, and related files.

Never apply a blanket ratio like "indexes always take 10% of data size" to every column. Long `text` columns, value distributions, compression, and heavy updates yield vastly different footprints from narrow numeric columns.

### 5.2. Reading disk metrics accurately

With **Cassandra 5.0 SAI**, the `system_views.indexes` virtual table exposes:

- `per_column_disk_size`: bytes of the index components dedicated to that column.
- `per_table_disk_size`: bytes of SSTable-level index components shared across indexes on the table.
- `indexed_sstable_count`: number of SSTables containing indexed data.
- `is_building` and `is_queryable`: build and readiness status of the index.

When summing total footprint across multiple rows of `system_views.indexes`, **do not double-count `per_table_disk_size` for every column**: it is the **shared** component, counted once per table/SSTable layout.

Also budget disk space for:

1. Base SSTables and active commit logs/memtables.
2. On-disk index components.
3. Temporary SSTables/indexes during compaction or rebuild.
4. Snapshots/backups, repair/streaming, or operational retention.

**Disk usage during builds/compaction can exceed steady-state disk usage.** Never size capacity assuming only the final compacted dataset exists.

### 5.3. TTL, deletes, and tombstones

A field with a TTL or frequent deletions does not disappear from every file the moment the client gets an ACK. Cassandra uses tombstones and compaction/garbage-collection rules. With SAI, index candidates may need **post-filtering** when shadowed by tombstones; deletions follow storage-engine integration rules.

Practical consequence: high churn can inflate total index work, SSTable/index files, and compaction cost even when **live row counts at any instant** barely grow.

## 6. Initial index build on an existing populated table

A common scenario: a table already holds hundreds of millions of rows, and today we need to filter by `status`. Creating the index forces the system to **index existing historical data**.

### 6.1. Initial build cost

This process reads existing SSTables, builds value → row/partition mappings, and writes index components to disk—all while applications continue issuing new writes and nodes run normal compactions, repairs, and queries.

- **Read I/O:** scanning old data to generate index contents.
- **CPU/heap:** processing terms, row IDs, and lookup structures.
- **Write I/O:** writing index files and metadata.
- **Concurrency pressure:** competing for I/O and CPU with writes, flushes, compaction, and reads.
- **Query readiness timing:** never assume an index is immediately queryable just because `CREATE INDEX` returned success.

Cassandra runs background index builds according to the version and index implementation. With SAI 5.0, inspect `is_building`/`is_queryable` **across the relevant nodes** before routing new query traffic to the index. Queries relying on a building index may be unavailable or rejected depending on node state.

### 6.2. CQL example: SAI on Cassandra 5.0

Assume the `shop` keyspace exists with suitable replication; test in a staging/lab environment first:

~~~cql
CREATE TABLE shop.orders_by_tenant_day (
    tenant_id uuid,
    order_day date,
    order_id uuid,
    status text,
    channel text,
    amount decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_day), order_id)
);

-- Cassandra 5.0: SAI indexes on non-key columns.
CREATE INDEX orders_status_sai
ON shop.orders_by_tenant_day (status)
USING 'sai';

CREATE INDEX orders_channel_sai
ON shop.orders_by_tenant_day (channel)
USING 'sai';
~~~

Test data mutations using the full partition key to keep read scope clear:

~~~cql
INSERT INTO shop.orders_by_tenant_day
    (tenant_id, order_day, order_id, status, channel, amount, updated_at)
VALUES (
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
    '2026-11-21',
    bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb,
    'NEW', 'WEB', 250000, toTimestamp(now())
);

UPDATE shop.orders_by_tenant_day
SET status = 'PAID', updated_at = toTimestamp(now())
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND order_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;

SELECT order_id, status, amount
FROM shop.orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND status = 'PAID';
~~~

When updating `status = 'NEW' → 'PAID'`, the index must reflect the new value within Cassandra's storage engine; updating the base-row SSTable alone is not enough for indexed queries to return accurate results.

### 6.3. Checking build status and disk usage

~~~cql
-- Cassandra 5.0 SAI virtual table: queries local metadata on the connected node.
SELECT index_name, table_name, is_building, is_queryable,
       indexed_sstable_count, per_column_disk_size, per_table_disk_size
FROM system_views.indexes
WHERE keyspace_name = 'shop'
  AND index_name = 'orders_status_sai';
~~~

Note that the virtual table reports the state **of the queried node**. In a multi-node cluster, check all relevant nodes/replicas rather than treating one local response as proof the whole cluster's index is ready.

You can also query `system_views.sstable_indexes` for per-SSTable details when investigating storage discrepancies.

## 7. Rebuilding indexes: why and how?

**Rebuilding an index** means **reconstructing index structures from the table's data**. It differs from fixing application rows and differs from streaming token ranges from peer nodes.

Situations that may require building/rebuilding:

- Creating an index on a table that already contains data.
- Missing or corrupted index component files after an incident.
- Changing index configuration: with SAI, you typically must **drop and recreate** because you cannot `ALTER` an SAI index definition directly.
- Recovery or operational procedures per your version and index implementation.

**Administrative command:** Apache Cassandra provides `nodetool rebuild_index`, syntax:

~~~bash
nodetool rebuild_index <keyspace> <table> <indexName...>
~~~

Example executed on the node needing the index rebuild (after confirming version/index type and operational plan):

~~~bash
nodetool rebuild_index shop orders_by_tenant_day orders_status_sai
~~~

Meaning: rebuilds the specified **native secondary index** of the table on **the targeted node**. Do not assume running it once from one node rebuilds every node in the cluster. Verify support and behavior of your indexing implementation against your release docs.

### Rebuilding indexes is not rebuilding data

| Command/operation | Core purpose | Notable resources |
|---|---|---|
| `CREATE INDEX` on populated table | Initializes index and builds from existing data | SSTable scans, CPU, heap, index disk |
| `nodetool rebuild_index` | Rebuilds a table's native index on the targeted node | Local data reads, rewriting index |
| `nodetool rebuild` | Streams **data** from other nodes, typically tied to datacenter/token ranges | Bandwidth, disk I/O, SSTable processing |
| `nodetool repair` | Reconciles data across replicas, potentially streaming data | Merkle/diff, streaming, compaction, related index effects |
| Compaction | Reorganizes/writes new data SSTables | Data I/O and updating/generating SSTable-attached indexes |

`rebuild_index` and `rebuild` have similar names but **do not replace each other**. `nodetool rebuild` does not mean "rebuild the table's indexes."

When troubleshooting a missing index, first check whether the node is actively building, whether the index is queryable, error logs, and disk headroom. Never trigger repeated rebuilds while a build is already progressing without clear cause.

## 8. "Index transfer" across replication, bootstrap, repair, and streaming

The phrase **index transfer** can refer to three distinct activities. Distinguishing them prevents miscalculating network bandwidth.

### 8.1. Mutations replicate; indexes are maintained locally

During normal writes, the coordinator **forwards the mutation** to the partition's replicas; each replica updates its local index. There is no "global index server" receiving index copies on every write in Cassandra 2i/SAI.

For example, with RF = 3, writing a row with an indexed `status` column sends **the data mutation to three replicas per write protocol**, and each node maintains its local index. Thus, adding indexes affects local CPU/heap/disk far more directly than multiplying replication packets by the index count.

### 8.2. Schema and index state propagate differently from index data

`CREATE INDEX` configuration is **schema metadata** distributed across the cluster so nodes know the index definition. It does not ship all index postings/terms across the network on schema changes.

Specifically for SAI, **queryable/building state** is also communicated to coordinators (e.g., via gossip). Propagating **state** helps coordinators avoid replicas whose indexes cannot serve queries, without meaning all nodes share one global index file.

### 8.3. Streaming SSTables during bootstrap, node replacement, or repair

When a new node bootstraps, a node is replaced, token ranges shift, or repair runs, Cassandra may **stream SSTables/data** between nodes. Attached indexes are affected depending on implementation and streaming path.

**Key point for SAI 5.0:** SAI is compatible with **zero-copy streaming (ZCS)**. When streaming an **intact, eligible SSTable**, SAI index components can be streamed **alongside the SSTable**, avoiding rebuilding indexes from scratch at the receiver. If streaming does not use whole-file zero-copy or conditions are unmet, do not assume every index file is always copied verbatim; consult your version's behavior and verify index state.

**With legacy 2i**, local indexes reside in separate structures, so SAI's "indexes stream alongside SSTables" behavior does not automatically apply verbatim. During data intake or recovery paths, 2i index structures may need to be maintained/built on the receiving node per 2i rules.

~~~mermaid
flowchart TD
    A["A partition is replicated"] --> B["Replica A: data + local index"]
    A --> C["Replica B: data + local index"]
    A --> D["Replica C: data + local index"]
    B --> E{"Bootstrap / replace / repair?"}
    E -->|Yes| F["Stream appropriate data/SSTables"]
    F --> G{"SAI + intact SSTable eligible for ZCS?"}
    G -->|Yes| H["Transfer index components with SSTable"]
    G -->|No| I["Build/maintain index per stream path & implementation"]
    H --> J["Verify index queryable on receiving node"]
    I --> J
~~~

**Do not confuse two concepts:**
- **Network replication per write CL/RF**: serves new writes.
- **Streaming during topology/repair changes**: can transfer massive volumes in a short period, potentially including index components.

Both generate network traffic, yet at different times and under different controls. `nodetool netstats` and streaming metrics help observe the latter.

## 9. How flush, compaction, and repair multiply index costs

### Flush

When a memtable flushes to an SSTable, SAI writes index components corresponding to the new SSTable. More indexes mean more work writing index files; memtable index memory estimates can influence flush frequency.

### Compaction

Compaction reads/merges SSTables and writes new SSTables; with SAI, index components attached to the new SSTables are generated during this process too. Old files are replaced once no longer referenced. Therefore, index costs exist **even with zero incoming writes**, as long as background compaction runs.

If a workload has high churn or uses a compaction strategy with high write amplification, adding indexes further amplifies writes. Never conclude "compaction only touches base data; indexes are unaffected."

### Repair

Repair compares replicas and may stream differing data. Impact on indexes depends on how SSTables are received and the index implementation. Operationally, repair consumes disk/network and can contend with index builds, flushes, and compaction. Repair **reconciles data across replicas**; it does not guarantee indexes have finished building on every node simply because repair finished.

### Backup/snapshot and restore

Understand how snapshots/restores preserve SSTables and index components in your distribution. Indexes can increase backup size. After restoring, verify indexed queryability—not just that base table data is readable.

## 10. Java applications: indexes are server-maintained, yet latency surfaces on clients

In Java applications, DataStax Java Driver 4.x requires no separate "update index" call on writes. The application issues normal CQL mutations; Cassandra maintains indexes on replicas.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

// session is connected; table and indexes were created by migrations.
PreparedStatement update = session.prepare(
    "UPDATE shop.orders_by_tenant_day SET status = ? " +
    "WHERE tenant_id = ? AND order_day = ? AND order_id = ?"
);

UUID tenantId = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
UUID orderId  = UUID.fromString("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
java.time.LocalDate orderDay = java.time.LocalDate.of(2026, 11, 21);

BoundStatement statement = update.bind(
        "PAID", tenantId, orderDay, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
// Cassandra maintains SAI/2i on replicas; no index-update call exists in the driver.
~~~

Here `LOCAL_QUORUM` illustrates a configuration for a topology with appropriate per-DC RF. It does not turn indexes into cluster-wide shared data, nor does it turn **index-based queries** into point lookups.

Applications should measure `UPDATE` request latency, timeout rates, retries, and indexed query performance before and after adding indexes. To reduce latency, distinguish network/cross-DC delays, partition contention, disk backlog, and index overhead instead of blaming the driver for every fluctuation.

## 11. Monitoring and capacity planning before shipping indexes to production

### Key observations

| What to measure | Why it matters | Suggested source |
|---|---|---|
| Write throughput, P95/P99 latency, and timeouts | Detects impact on client requests | Driver + Cassandra metrics |
| Heap, GC, memtable usage, flush rate | Indexes can increase memory pressure and flush frequency | JMX/Cassandra metrics |
| SSTable count, compaction queue, bytes compacted | Indexes are created/rewritten as SSTables change | `nodetool compactionstats`, metrics |
| Index disk size and build status | Avoid querying unready indexes; measure footprint | `system_views.indexes` (SAI 5.0) |
| Incoming/outgoing streaming bytes, active streams | Measures bootstrap, repair, replacement | `nodetool netstats`, streaming metrics |
| Indexed query latency, partitions/token ranges scanned | Evaluates whether read gains justify write overhead | Tracing, metrics, load tests |

**Do not decide based on index size alone.** A small index whose queries scan many token ranges can still be expensive. Conversely, an index that saves massive read I/O may be worth a modest write-latency bump. Decide against your system's SLOs.

### Rollout procedure for a new index

1. **Validate the real query:** is the full partition key supplied, which columns are filtered, what are cardinality/selectivity and result bounds?
2. **Verify Cassandra version:** SAI is built into Cassandra 5.0; on 4.x clusters evaluate supported alternatives rather than copying `USING 'sai'` blindly.
3. **Measure baseline:** write latency, throughput, disk utilization, compaction backlog, read latency; capture peak traffic too.
4. **Test in staging with production-like data and workload:** create the index over existing data to measure **initial build duration**, CPU/I/O, and storage.
5. **Reserve disk/I/O/CPU headroom and schedule carefully:** avoid building multiple indexes during repairs, streaming, or near-full disks.
6. **Create and monitor index status:** shift read traffic depending on the index only once target replicas are **queryable**.
7. **Observe post-rollout:** if write p99 spikes or backlogs persist, adjust workload/query design, index count, or rollout pacing.
8. **Prepare a rollback path:** know how to `DROP INDEX` and revert queries to the prior path; note that dropping/recreating later may require **rebuilding** before reuse.

When tables update continuously and carry multiple indexes, keep disk headroom for compaction, rebuilds, and repair. Never infer from steady-state disk usage that enough headroom exists for background operations.

## 12. Common incidents and analysis

### Incident A — Write p99 spikes sharply after creating an index

**Hypothesis:** maintaining multiple indexed columns, extra memtable heap for index entries, and increased flush/compaction; historical backfill competing for I/O. Check `is_building`, heap/GC, compaction queue, and disk throughput against baseline. While the build runs, separate temporary backfill impact from steady-state cost.

### Incident B — Newly bootstrapped node throws SAI errors or returns incomplete results

**Do not jump to "SAI wasn't transferred from peer nodes."** Distinguish active data streaming, which SAI components stream with SSTables, whether local builds completed, and whether coordinators select `is_queryable` replicas. Inspect the specific node via `system_views.indexes`, logs, `nodetool netstats`, and server version.

### Incident C — Disk usage grows after compaction/rebuild

Old and new SSTables or index files may coexist temporarily, especially while active queries still reference older files. Watch disk usage over time, compaction tasks, snapshots/backups, and SAI components; do not mistake every temporary spike for a leak.

### Incident D — Need to "rebuild" after index issues

First clarify whether the target is **index structures**, **data from peer replicas**, or **replica reconciliation**. Use `rebuild_index` when targeting native indexes, `rebuild` for administrative data streaming, and `repair` to reconcile replicas. Never pick the wrong command just because both contain "build."

### Incident E — Index exists yet queries remain too slow

Re-evaluate query-driven table design: is the index serving cluster-wide queries? Does `status` share the same value across huge numbers of rows? Are many filters, limits, pagination, or large payloads involved? SAI reduces local filtering work but **does not eliminate distributed routing and result-reading costs**. If the query pattern is fixed and needs point lookups, a denormalized table may be the better choice.

## 13. Applied exercises

**Exercise 1.** You have 2,000 logical writes/sec, RF = 3, and three indexes. Can you conclude the system sends 18,000 separate index replication messages per second?

**Answer:** No. Index work occurs primarily locally on replicas. `2,000 × 3 × 3` is only an upper-bound estimate of local index update operations when all three indexed columns change—not network packet count or actual write speed.

**Exercise 2.** A table already holds 5 TB of data; you add an SAI index and immediately route all production queries to it. What are the risks?

**Answer:** Backfilling existing data consumes heavy CPU, disk I/O, and storage; indexes on some nodes may not yet be queryable. Monitor build status across relevant replicas and enforce load limits.

**Exercise 3.** A newly bootstrapped node uses eligible zero-copy streaming and receives SSTables containing SAI components. Must it always rebuild indexes from scratch?

**Answer:** No. With SAI, index components can stream alongside SSTables via eligible ZCS paths. Still, verify actual streaming paths and queryable status—never generalize this to 2i or every stream path.

**Exercise 4.** An admin needs to reconstruct a native index on `orders_by_tenant_day`, and someone suggests `nodetool rebuild`. Is that the right command?

**Answer:** No. `nodetool rebuild` streams **data**; `nodetool rebuild_index` rebuilds **native secondary indexes** on the node.

**Exercise 5.** With SAI indexes on `status` and `channel`, `system_views.indexes` shows `per_table_disk_size` in both rows. Can you add those two numbers together to get total shared disk size?

**Answer:** Never double-count shared table-level components. Count the shared portion once per table/SSTable layout and add each column's individual footprint.

## 14. Key takeaways

Indexes in Cassandra help when query workloads must filter outside the partition key, yet **every write creating or mutating an indexed value incurs replica-side index maintenance**. With SAI, most of the index lifecycle tracks memtables/SSTables closely, so costs do not end at the write request: flush, compaction, rebuilds, bootstrap, repair, and streaming all impact resources. With 2i, hidden local index tables carry distinct maintenance characteristics.

Evaluate **total cost of ownership** by weighing scan/read savings against write amplification, disk footprint, build duration, and cluster operations. Clearly distinguishing **mutation replication**, **schema/index-state propagation**, **SSTable streaming**, **index rebuilding**, and **data rebuilding** leads to far more reliable systems.

### Official references for version verification

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/indexing-concepts.html)
- [Apache Cassandra — SAI write and read paths](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html)
- [Apache Cassandra — SAI concepts and zero-copy streaming](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html)
- [Apache Cassandra — SAI virtual tables](https://cassandra.apache.org/doc/stable/cassandra/reference/sai-virtual-table-indexes.html)
- [Apache Cassandra — Rebuild native secondary indexes](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html)
- [Apache Cassandra — Streaming architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/streaming.html)
