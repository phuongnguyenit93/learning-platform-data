# SAI Attached to Memtables/SSTables and the Data Lifecycle in Apache Cassandra

> **Chapter:** Indexes  
> **Scope:** Apache Cassandra 5.0+, Storage-Attached Indexing (SAI), write/read path, flush, compaction, update/delete/TTL, index build, streaming, and Java applications.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **memtable index**, **per-SSTable index**, **per-column index**, and base data.
2. Explain why newly inserted data can be found via SAI **before flush**, and why SAI always moves with the SSTable lifecycle.
3. Trace a mutation's path through **commit log → memtable → flush → SSTable → compaction**.
4. Describe how SAI combines candidates from multiple SSTables and memtables, then **post-filters** by timestamp/tombstone/TTL.
5. Predict the impact of creating indexes on existing data, row updates/deletes, compaction, rebuilds, and streaming.
6. Practice CQL, monitor SAI, troubleshoot errors, and query indexes from a Java application.

**Prerequisites:** SAI is integrated into open-source Apache Cassandra starting in **5.0**. Open-source Cassandra 4.x does not include this built-in SAI feature. This lesson uses syntax and monitoring suited for Cassandra 5.0; verify against your actual environment before running operations.

## 2. Core intuition: indexes move with the data

Cassandra is a distributed wide-column database: the partition key determines the token and replica set, while data on each replica flows through the commit log and memtable before being flushed into **immutable SSTables**. SAI is a **replica-local** index tied directly to the storage lifecycle of the table's data on that replica. It is not a single centralized cluster-wide index.

~~~text
            CQL INSERT / UPDATE / DELETE
                         |
                  Coordinator + CL
                         |
                    One replica
                      /      \
                 Commit log   Data memtable
                                  |
                           SAI memtable index
                                  |
                           (synchronous flush)
                                  v
                       SSTable-A + SAI-A
                       SSTable-B + SAI-B
                            \       /
                           Compaction
                                |
                                v
                       SSTable-C + SAI-C

Reading WHERE on an SAI-indexed column:
  Memtable index + all active SAI-SSTables
       -> candidate list
       -> read base rows and reconcile versions
       -> check predicates, TTL, tombstones
       -> return valid rows
~~~

SAI is called *storage-attached* because each SSTable has index components attached to it. However, SAI **does not operate only after flush**: new mutations still residing in the memtable are also indexed for immediate querying.

### Three layers to distinguish

| Layer | Where stored | Contents/meaning | Lifecycle |
|---|---|---|---|
| Table data | Memtable, SSTable | Primary key, columns, timestamp, TTL, tombstone | Writes, flush, compaction, repair |
| Memtable index | Memory, attached to memtable | Indexed column value → primary key | Updated with mutation, flushed with memtable |
| SSTable index | SAI files attached to each SSTable | Term → row ID; token/offset info to locate base data | Created at flush/build/compaction, replaced alongside SSTable |

An SAI index is created **on a single column**. Multiple SAI indexes on the same table share base data and can share certain SSTable-level mapping components.

## 3. Inside an SSTable index

When creating a new SSTable, SAI assigns a **local row ID** to rows and stores structures mapping row IDs to tokens/partition offsets. For each indexed column, SAI stores **postings**, i.e., the list of row IDs matching a searchable value.

~~~text
SSTable-001
  Data.db             : actual table data
  SAI shared mappings : row ID -> token / partition offset
  SAI status          : 'FAILED' -> {row 3, row 10}
  SAI latency_ms      : [1000..2000] -> {row 3, row 7}
                                               |
                                  lookup row ID in Data.db
~~~

This sketch illustrates **logical** components, not a list of files to manipulate manually. SAI files do not store a full duplicate copy of the table.

- **Text columns:** SAI uses a byte-level trie structure and postings for supported text filters.
- **Numeric columns:** SAI uses a *kd-tree*-like structure with postings for lookups, including numeric range predicates.
- **Per-SSTable shared files:** the mapping from row ID to token/partition offset is shared across multiple column indexes, avoiding repeating full primary keys.
- **Segments:** when building indexes from large data streams, SAI bounds memory usage by splitting into multiple segments inside index files; a segment is neither a replica nor a new partition.

**Do not confuse with Cassandra's primary index:** knowing the partition key remains the most proactive and efficient way to target partitions. SAI supports filtering other columns, but does not add JOINs, global ORDER BY, or arbitrary full-text search.

## 4. Write path: mutations update the in-memory index too

Suppose a table has SAI on `status` and `latency_ms`, and receives:

~~~sql
INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 1, 'FAILED', 1250, 'timeout');
~~~

On the receiving replica, Cassandra appends the mutation to the **commit log** for durability and updates the **memtable**. SAI intercepts the mutation and adds the indexed column values and corresponding primary key to the **memtable index**. Index updates on mutations are **synchronous**: by the time the replica acknowledges the write, the index entry for that data is already updated; there is no delayed "build index a few minutes later" job for normal INSERTs.

~~~text
Write team_a/1, status=FAILED, latency_ms=1250:

  CommitLog           Data Memtable           SAI Memtable
  [mutation]  ----->  team_a/1 : FAILED  ---> status: FAILED -> team_a/1
                          1250           ---> latency: 1250 -> team_a/1
~~~

Therefore, the following query can find the row **before any new SSTable is flushed**:

~~~sql
SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

In a multi-replica cluster, consistency level (`ONE`/`LOCAL_QUORUM`/...) and replica health still govern results like any other Cassandra operation; indexes do not bypass consistency requirements.

### Cost of the memtable index

SAI requires additional processing per indexed column, and estimated index memory is **counted toward the memtable memory budget**. Adding many SAI-indexed columns can cause memtables to hit flush thresholds sooner, increasing **SSTable and SAI file counts**. Write CPU, heap, disk I/O, and compaction costs should be measured under realistic load.

## 5. Flush: data and SAI are written as the same SSTable generation

A flush is triggered by memory thresholds, administrative commands, or other storage engine conditions. Instead of modifying old SSTables, Cassandra writes a **new SSTable**, and SAI simultaneously writes index components attached to that SSTable.

Cassandra 5.0 describes SAI flushing in two phases:

1. **Writing data rows and shared mappings:** while writing the SSTable, the engine assigns row IDs, writes row ID → token/partition offset mappings, and maintains a temporary primary key → row ID mapping.
2. **Writing per-column indexes:** SAI iterates the memtable index by term, translates primary keys to row IDs, and writes postings and the corresponding trie/kd-tree structures.

After finishing column indexes, SAI writes a **completion marker**. The marker matters even when an SSTable contains no indexable values—for example, only tombstones—because the engine must distinguish "nothing to index" from "missing index due to build failure."

~~~text
Before flush                         After flush
------------                         -------------------------------
Memtable base row       ------->     SSTable-002 / base data
Memtable SAI status     ------->     SSTable-002 / SAI status
Memtable SAI latency    ------->     SSTable-002 / SAI latency
                                    SSTable-002 / shared mapping

SSTable-001 + SAI-001 remain until compacted.
~~~

Once flushed, the same rows remain queryable via SAI, but the index source is now SSTable files rather than the memtable index. There is no need to run `rebuild_index` manually after every flush.

Command to observe this on **a single node** in a lab:

~~~bash
nodetool flush sai_lab events
~~~

In a distributed cluster, running `nodetool` on one node does not flush memtables on other nodes.

## 6. Read path: find candidates, then verify base data

Upon receiving a `WHERE` clause on an SAI-indexed column:

1. **The coordinator** analyzes predicates and chooses indexes/selectivity to plan the query across required token ranges.
2. **Each queried replica** uses a local query plan to search its memtable index and relevant per-SSTable indexes.
3. For a single predicate (e.g., `status='FAILED'`), SAI takes the **union** of candidates across memtables/SSTables. For multiple `AND` predicates, it can compute the **intersection** of candidates across column indexes.
4. SAI maps postings/row IDs to partitions and reads base data rows, applying Cassandra timestamp rules.
5. **Post-filtering** discards candidates that no longer match due to `UPDATE`, `DELETE`, `TTL`, unindexed predicates, or partition-level granularity.

~~~text
WHERE status = 'FAILED' AND latency_ms >= 1000

Memtable status index   ───┐
SSTable-A status index  ───┼─> union(status='FAILED') ──┐
SSTable-B status index  ───┘                           │
                                                     intersect
Memtable/SSTable latency indexes -> >= 1000 ──────────┘
                                                         |
                                                     row IDs
                                                         |
                                           read base rows and post-filter
                                                         |
                                             rows truly matching WHERE
~~~

SAI is a **filtering engine**. Finding a posting in one SSTable does not prove that value is still the latest live version. Reading base rows is mandatory to preserve Cassandra semantics.

### 6.1. UPDATE: old postings may still persist

Consider the same primary key `team_a/1`:

| Time | Mutation | Index contents | Result of WHERE status='FAILED' |
|---|---|---|---|
| t1 | status=FAILED, flushed to A | A: FAILED → team_a/1 | Includes team_a/1 |
| t2 | UPDATE status=OK in memtable | A: FAILED; memtable: OK | **Excludes** team_a/1 |
| t3 | Flush UPDATE into B | A: FAILED; B: OK | **Excludes** team_a/1 |
| t4 | Compact A+B into C | C indexes only relevant live values | **Excludes** team_a/1 |

At t2/t3, the old index may still return `team_a/1` as a **candidate**. When reading the base row, Cassandra sees the newest value is `OK` and filters out the `FAILED` candidate. SSTable-A's SAI files never need in-place mutation.

### 6.2. DELETE and TTL: tombstones require post-filtering

`DELETE` writes a tombstone; expired `TTL` makes data dead under Cassandra's liveness rules. SAI **does not index tombstones as searchable terms**. Candidates from older SSTables can be shadowed by newer tombstones, so the engine must factor in deletions and TTLs while filtering. Tombstones are not necessarily reclaimed physically right away; safe removal depends on compaction, `gc_grace_seconds`, and replica state.

Heavy post-filtering increases I/O because candidates must be read only to be discarded. `RowsFiltered` metrics and tracing help detect this scenario.

### 6.3. With or without a partition key

~~~sql
-- Partition specified: search scope is already bounded.
SELECT event_id, status
FROM sai_lab.events
WHERE tenant_id = 'team_a' AND status = 'FAILED';

-- No partition key: may require scanning many token ranges/replicas.
SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

If `status = 'FAILED'` appears in nearly every partition, the index has poor selectivity. The query remains syntactically valid, but becomes expensive on large clusters. **SAI does not make distributed scans free.**

## 7. Compaction: new SSTables come with new indexes

Because SSTables are immutable, `UPDATE`/`DELETE` never overwrite old files. Across multiple flushes, a row can span multiple SSTables. Compaction merges eligible generations, resolves versions and eligible tombstones, and writes a **new output SSTable**.

During compaction, SAI consumes the merged output rows to **build new index files**. Unlike memtable indexes that are already sorted by term, compaction streams require buffering and sorting terms/postings; SAI uses a memory-bounded **segment buffer** to build the on-disk structures.

~~~text
    Before compaction                 After successful compaction

 SSTable-A + SAI-A ----┐
                      ├---->       SSTable-C + SAI-C
 SSTable-B + SAI-B ----┘            (merged output data)

 Indexes A/B are not updated in place.
 Index C becomes active alongside SSTable-C.
~~~

Upon completion, Cassandra/SAI **atomically switches the view of SSTables and indexes** to the new generation. Queries currently reading A/B hold references until safe to release; thus old files may not vanish from disk immediately.

### Choosing a compaction strategy

- **STCS (SizeTieredCompactionStrategy):** fits many SAI workloads; reduces SSTables to probe by merging similarly sized SSTables.
- **TWCS (TimeWindowCompactionStrategy):** worth evaluating for time-series/TTL data with windowed lifecycles; limits time-scoped file ranges when data patterns match.
- Too little compaction increases SSTable/segment counts; excessive compaction drives disk I/O, CPU, and output index builds.
- Never run blanket major compactions to cure slow SAI queries: inspect the current strategy, free disk space, tombstones, load, and reclamation potential.

## 8. Other data lifecycle events and SAI

| Event | Base data | SAI behavior | What to monitor |
|---|---|---|---|
| INSERT/UPDATE | Mutation enters memtable and commit log | Updates memtable index synchronously | Memory, write latency |
| Flush | Memtable becomes new SSTable | Writes index attached to newly created SSTable | Flush rate, SSTable count |
| DELETE/TTL expiration | Tombstone / expired value | Old postings may persist; read post-filter discards them | RowsFiltered, compaction |
| Compaction | Merges eligible SSTables | Builds index on output SSTable, swaps view | Disk I/O, backlog, segment count |
| CREATE INDEX on populated table | Existing data remains unchanged | **Backfills/builds** index for existing SSTables | is_building, is_queryable |
| DROP INDEX | Table data remains intact | Drops corresponding index structures | Queries dependent on the index |
| Bootstrap/decommission, SSTable streaming | SSTables streamed across nodes | SAI supports zero-copy streaming alongside SSTables | Compatibility, receiving node status |
| Snapshot/restore | Reuses SSTable files | SAI files belong to the SSTable lifecycle | Version-specific backup/restore procedures |
| Repair | Compares and syncs data across replicas | SSTable indexes follow data files, rebuilt if needed | Data repair and index state are separate checks |
| Corrupted index or missing component | Base data may still be valid | Index may become non-queryable | Logs, disk, controlled rebuild_index |

### 8.1. CREATE INDEX after data already exists

Cassandra allows creating SAI **after** a table already holds rows. In that case, SAI must read existing data to build local indexes for relevant SSTables and memtables. `CREATE INDEX` returning does not guarantee indexes across all replicas are built; inspect build and queryable state on **all relevant nodes** before allowing applications to rely on the index.

An SAI index cannot change options via `ALTER INDEX`. When index options must change, the workflow is `DROP` followed by `CREATE`, creating a non-queryable window that applications must plan for.

### 8.2. Streaming and repair

Because indexes attach to SSTables, SAI supports **zero-copy streaming** during bootstrap/decommission and compatible engine streaming paths: data and index components travel together without pushing every row through a central indexing pipeline. Still, every node must reach a valid local index state before serving queries.

Distinguish two operational commands:

- `nodetool repair`: fixes **data discrepancies across replicas** and may trigger SSTable streaming.
- `nodetool rebuild_index`: rebuilds a table's **local indexes** on the target node; does not replace repair.

If SAI queries misbehave after streaming/repair, check both **replica data health** and **index queryability**. Rebuilding indexes alone will not restore missing base data on a replica.

## 9. CQL hands-on lab on Cassandra 5.0

**Environment:** single-node Cassandra 5.0 with `cqlsh` and `nodetool` access. The `SimpleStrategy` RF=1 config below is **for single-node labs only**; production requires `NetworkTopologyStrategy` and topology-appropriate RF.

### Step 1 — Create the table and data *before* the index

~~~sql
CREATE KEYSPACE IF NOT EXISTS sai_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS sai_lab.events (
    tenant_id text,
    event_id int,
    status text,
    latency_ms int,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 1, 'FAILED', 1250, 'timeout');

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 2, 'OK', 100, 'accepted');

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_b', 3, 'FAILED', 2200, 'upstream');

SELECT * FROM sai_lab.events WHERE tenant_id = 'team_a';
~~~

Force a flush **before creating SAI** to observe index building over pre-existing SSTables:

~~~bash
nodetool flush sai_lab events
~~~

### Step 2 — Create two SAI indexes

~~~sql
CREATE INDEX IF NOT EXISTS events_status_sai
ON sai_lab.events (status)
USING 'sai';

CREATE INDEX IF NOT EXISTS events_latency_sai
ON sai_lab.events (latency_ms)
USING 'sai';
~~~

Indexes are built for existing rows on those columns. Inspect status via the virtual table:

~~~sql
SELECT index_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'sai_lab'
  AND table_name = 'events'
  AND index_name = 'events_status_sai';

SELECT index_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'sai_lab'
  AND table_name = 'events'
  AND index_name = 'events_latency_sai';
~~~

The virtual table reports node-local status. Run queries using SAI **only after** the corresponding indexes on serving nodes/replicas report `is_queryable = true`.

### Step 3 — Query using one or two SAI indexes

~~~sql
SELECT tenant_id, event_id, status, latency_ms
FROM sai_lab.events
WHERE status = 'FAILED';

SELECT tenant_id, event_id, status, latency_ms
FROM sai_lab.events
WHERE status = 'FAILED' AND latency_ms >= 1000;
~~~

With the inserted rows, both queries return two rows: `team_a/1` and `team_b/3` (do not assume cross-partition order). In multi-node clusters, this partition-keyless query shape may scan many token ranges.

### Step 4 — UPDATE while an older SSTable still holds FAILED

~~~sql
UPDATE sai_lab.events
SET status = 'OK', latency_ms = 200
WHERE tenant_id = 'team_a' AND event_id = 1;

SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

The accurate post-UPDATE result returns only `team_b/3`. The older SSTable was not mutated and may still hold a `FAILED` posting for `team_a/1`, but the read path excludes it via the newer row version and post-filter.

~~~bash
nodetool flush sai_lab events
~~~

Re-run the `SELECT`; logical results remain identical even though the mutation moved from the memtable into a new SSTable/index.

### Step 5 — DELETE and TTL

~~~sql
DELETE FROM sai_lab.events
WHERE tenant_id = 'team_b' AND event_id = 3;

SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_c', 4, 'FAILED', 1700, 'temporary')
USING TTL 60;
~~~

The deleted `team_b/3` row no longer appears in query results even while old postings remain in SSTables. The `team_c/4` row expires after its TTL; this does not mean Cassandra triggers compaction immediately at the 60-second mark.

### Step 6 — Observing before/after compaction

In the lab, to demonstrate replacing SSTable and index generations:

~~~bash
# Lab observation ONLY; evaluate I/O impact in production.
nodetool compact sai_lab events
~~~

Re-check index status with the queries from Step 2. Two additional virtual tables for observing SSTable indexes and segments are `system_views.sstable_indexes` and `system_views.sstable_index_segments`. Columns and filtering capabilities can change between versions; inspect the virtual table schemas on your cluster before writing diagnostic queries.

### Step 7 — Rebuilding a local index when permitted

~~~bash
# Run on the node needing rebuild; never edit *.db files directly.
nodetool rebuild_index sai_lab events events_status_sai
~~~

This rebuilds `events_status_sai` on `sai_lab.events` for the contacted node. Monitor index status and logs throughout. This is an exercise in rebuilding, not something recommended periodically while an index is healthy.

## 10. Monitoring and troubleshooting SAI

### 10.1. Observing via virtual tables, tracing, and JMX

| Signal | Observation source | Meaning |
|---|---|---|
| `is_building`, `is_queryable` | `system_views.indexes` | Distinguishes schema creation from query readiness |
| SSTable index sizes and counts | `system_views.sstable_indexes` | File counts and token ranges with indexes |
| Segment counts and splitting cost | `system_views.sstable_index_segments` | Fragmentation level of index structures |
| `DiskUsedBytes` | SAI JMX | Disk footprint of index files |
| `ColumnIndexBuildsInProgress` | SAI JMX | Number of active index builds |
| `SSTableIndexesHit` | SAI JMX | Extent to which queries touch multiple SSTable indexes |
| `RowsFiltered` or `TotalRowsFiltered` | SAI JMX | Number of candidates discarded by post-filtering |
| `PartitionReads`, `TotalPartitionReads` | SAI JMX | Partitions read after index candidate lookup |
| `QueryLatency`, `TotalQueryTimeouts` | SAI JMX | SAI query latency experience and timeouts |

Tracing from cqlsh is a great way to observe query execution:

~~~sql
TRACING ON;

SELECT tenant_id, event_id
FROM sai_lab.events
WHERE status = 'FAILED';

TRACING OFF;
~~~

Traces can reveal the number of memtable indexes, SSTable indexes, segments scanned, and rows post-filtered. **Never enable tracing broadly** in production due to its overhead.

### 10.2. Symptom-based diagnosis

| Symptom | What to check | Appropriate action |
|---|---|---|
| CREATE INDEX finishes but queries cannot use it | Build incomplete, `is_queryable=false` on some nodes | Verify status on all replicas and check build logs |
| New index causes CPU/disk spikes | Historical SSTable backfill | Schedule during low traffic; check memory and I/O |
| SAI query is slow despite small final row count | Many SSTables or heavy post-filtering | Trace, measure `SSTableIndexesHit` and `RowsFiltered` |
| Adding indexes causes frequent flushes | Memtable counts SAI heap usage | Measure flush rate; consider removing unnecessary indexes |
| Old files remain on disk after DELETE | Tombstones, snapshots, compaction hasn't reclaimed | Check grace period, compaction, and snapshots |
| Old index files persist after compaction | Active readers/snapshots retaining old SSTables | Check active compactions, snapshots, and disk |
| Index non-queryable after file error | Build/streaming failure or missing index component | Inspect logs/disk; run controlled `rebuild_index` |
| Query results differ across replicas | Unsynchronized data or differing index states | Verify repair, replica health, and index status |

Never delete or edit SAI files on disk manually to "resync," and never treat `nodetool compact` as a cure-all. **Replica data synchronization** and **local index rebuilding** are two separate tasks.

## 11. Optimizing query design with SAI

SAI is highly useful for flexible filtering on non-partition-key columns, but Cassandra still prioritizes **primary query-driven table modeling**. Before creating multiple indexes, answer:

1. **Selectivity:** does the predicate return few or many partitions? Cluster-wide common values can be very costly.
2. **Scope:** does `WHERE` include the partition key? If not, is querying across many token ranges acceptable?
3. **Read/write ratio:** every indexed column adds mutation, heap, flush, and compaction cost.
4. **SSTable state:** does a compaction backlog force queries to probe many per-SSTable indexes?
5. **TTL/DELETE/UPDATE:** are many expired/deleted entries forcing heavy post-filtering?
6. **CQL capabilities:** does the app need JOINs, global sorting, text relevance ranking, or arbitrary pagination? SAI is a filter, not a general-purpose search engine.

Benchmark with **realistic data and partition distributions**, target RF/CL, concurrency, SAI hit rates, latency, and real SSTable counts. Just because a `SELECT` runs in a lab does not mean it is economical in production.

## 12. Using SAI from a Java application

With Cassandra Java Driver 4.x, SAI-backed queries remain ordinary CQL; the driver does not manage a separate index API. Example reusing an application-managed `CqlSession`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventSearch {
    public static ResultSet findSlowEvents(
            CqlSession session, int minLatencyMs) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT tenant_id, event_id, latency_ms " +
                "FROM sai_lab.events WHERE latency_ms >= ?")
            .addPositionalValue(minLatencyMs)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
            .setPageSize(100)
            .build();

        return session.execute(query);
    }
}
~~~

This illustrates setting CL and page size, not a production default configuration: `LOCAL_ONE` suits a lab demo, whereas production must choose based on SLAs and consistency guarantees. Reuse the session across the application lifecycle, configure the right local datacenter, and handle paging so huge result sets are not buffered in memory. Before enabling new queries in Java, verify SAI is **queryable** across all nodes that can serve them.

## 13. Check-your-understanding questions

**1.** Why can an `INSERT` be queried via SAI immediately before a flush occurs?  
*Answer:* Because mutations update the memtable index synchronously alongside the data memtable.

**2.** After `UPDATE status=FAILED → OK`, why don't old postings in older SSTables return stale rows?  
*Answer:* The index selects candidates; base row reads and post-filtering check the latest live version.

**3.** Does compacting SSTable A and B rewrite postings inside A/B in place?  
*Answer:* No; compaction writes a new SSTable C and index C, then switches views upon completion.

**4.** Why can creating SAI on a populated table be slow?  
*Answer:* Cassandra must backfill/build indexes over historical data sitting in existing SSTables.

**5.** How do `rebuild_index` and `repair` differ?  
*Answer:* Rebuild reconstructs local indexes; repair reconciles and synchronizes data across replicas.

**6.** How do many SSTables affect SAI queries?  
*Answer:* Queries may have to probe more indexes/segments, followed by more base-row reads and post-filtering.

**7.** Does TTL expiration immediately delete old postings from an SSTable?  
*Answer:* No; reads check expiration and tombstones, while compaction only reclaims storage physically once eligible.

## 14. Key takeaways

~~~text
Mutation → memtable + SAI in RAM → flush
         → immutable SSTable + SSTable-attached SAI
         → multiple SSTable generations under UPDATE/DELETE/TTL
         → read: union/intersect index candidates + post-filter base rows
         → compaction: produces new SSTable and SAI, atomic view swap
~~~

Two core principles: **SAI is updated in lockstep with the data's storage lifecycle**, from memtable to SSTable; **the index returns only candidates**, while the latest value, TTL, and tombstones are resolved when Cassandra reads and reconciles base data.

## References

- [Apache Cassandra 5.0 — SAI write path and read path](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html) — memtable index, flush, compaction, and post-filtering.
- [Apache Cassandra 5.0 — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html) — storage-attached architecture and streaming.
- [Apache Cassandra 5.0 — Working with SAI](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-working-with.html) — creating, querying, and dropping SAI in CQL.
- [Apache Cassandra 5.0 — Monitor SAI indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/operations/monitoring.html) — virtual tables, tracing, JMX.
- [Apache Cassandra 5.0 — rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html) — index rebuild syntax.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTables.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — DELETE, TTL, and compaction.
