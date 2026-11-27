# CLUSTER, Physical Ordering, and Table Rewrite Costs in PostgreSQL

In PostgreSQL, an ordinary table is stored as a **heap**: rows live on relation pages, while indexes are separate structures pointing to row locations. As applications insert data, update columns, or delete rows, the physical order inside the heap can diverge further from the logical order applications routinely query.

For example, an events table has an index on timestamp. Applications frequently read ranges:

```sql
SELECT event_id, occurred_at, payload
FROM app.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-10-02 00:00:00+00'
ORDER BY occurred_at;
```

The index locates matching keys, yet the corresponding rows may lie scattered across many heap pages. That drives up random page reads when the query needs multiple heap columns.

PostgreSQL provides the **CLUSTER** command to rewrite a table in the order of a chosen index. Afterward, rows are physically ordered by that index, giving queries reading adjacent keys a chance to read nearby heap pages sequentially.

Key takeaway: **CLUSTER is a one-time table rewrite operation, not a mechanism that continuously maintains physical order across future INSERTs/UPDATEs.** It incurs I/O, WAL, disk space, index rebuilds, and table locking during execution.

This lesson focuses on heap/index separation, MVCC, CLUSTER, physical correlation, rewrite costs, VACUUM FULL, REINDEX, pg_repack, progress monitoring, and deciding when to cluster or avoid it.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how PostgreSQL stores table heaps, heap pages, tuple versions, and index entries.
2. Distinguish logical ORDER BY ordering from physical row placement in the heap.
3. Explain CTID and why CTID must never be used as a durable business identifier.
4. Describe MVCC, how UPDATE creates new tuple versions, and its impact on physical locality.
5. Use CLUSTER table USING index to reorder a table by an index.
6. Use ALTER TABLE ... CLUSTER ON index to remember which index to use on future clusters.
7. Understand why CLUSTER requires a strong lock and can make other queries wait.
8. Estimate disk space, I/O, WAL, replica lag, and maintenance windows during rewrites.
9. Distinguish CLUSTER, VACUUM, VACUUM FULL, REINDEX, and pg_repack.
10. Read pg_stats.correlation to inspect correlation between column order and physical order.
11. Measure queries before/after using EXPLAIN (ANALYZE, BUFFERS).
12. Monitor pg_stat_progress_cluster, pg_locks, pg_stat_activity, and relation sizes.
13. Choose appropriate tables and indexes based on query workloads rather than guesswork.
14. Understand the effects of fillfactor, HOT updates, partitioning, BRIN, and new writes.
15. Plan controlled CLUSTER execution in production environments.

## 2. Heap and Index: Two Separate Storage Structures

An ordinary PostgreSQL table is organized into heap pages. An index is not a "sorted table" storing full rows; it stores keys and location pointers to tuples in the heap.

```text
TABLE HEAP
  Page 0: row 81 | row 12 | row 44
  Page 1: row  7 | row 90 | row 25
  Page 2: row 31 | row  3 | row 72

BTREE INDEX on event_time
  t1 -> (Page 2, offset 3)
  t2 -> (Page 1, offset 7)
  t3 -> (Page 0, offset 12)
  t4 -> (Page 2, offset 31)
```

Indexes let PostgreSQL find keys and tuple addresses fast, yet key order in an index does not mean tuples sit contiguously in the heap.

### 2.1. Heap Pages and Tuples

A page has a size set at PostgreSQL build time, commonly 8 KB. A page holds a header, line pointers, and tuple data. A row can occupy many bytes, and oversized values may even live in a TOAST relation.

Do not assume:

- Every row always sits in one page at a fixed location.
- SELECT order without ORDER BY reflects physical order.
- Later INSERTs always append to the end of the table.
- UPDATEs simply modify bytes in place.

### 2.2. Index Entries Point to Heap Tuples

In a standard B-tree index, keys are sorted per operator class/collation and paired with a TID identifying the heap tuple. A TID is represented by block number and offset number.

### 2.3. CTID

PostgreSQL exposes the ctid system column:

```sql
SELECT ctid, event_id, occurred_at
FROM app.events
LIMIT 10;
```

ctid indicates the current physical location of a tuple version inside the relation. It is useful for diagnostics and controlled internal tasks, yet:

- UPDATE can create a new tuple version with a different CTID.
- CLUSTER rewrites the table, changing CTIDs en masse.
- VACUUM FULL and other rewrite operations also alter positions.
- Never use CTID as a primary key, foreign key, or business ID.

## 3. Physical Order Is Not SQL Result Order

A table clustered on events_occurred_at_idx must still be queried with:

```sql
SELECT *
FROM app.events
ORDER BY occurred_at;
```

whenever the application requires ordered output.

### 3.1. Why?

SQL only guarantees result ordering when ORDER BY is present. PostgreSQL may:

- Use an index scan.
- Use a bitmap heap scan.
- Use a sequential scan.
- Use a parallel plan.
- Pick a different execution plan after statistics or data change.

Without ORDER BY, result order can differ across two runs even if the table did not change.

### 3.2. CLUSTER Does Not Change SQL Semantics

CLUSTER changes physical layout to potentially improve locality. It does not add any rule that "every SELECT always returns rows in index order."

### 3.3. If Stable Pagination Is Needed

Use a deterministic sort order, such as:

```sql
SELECT event_id, occurred_at
FROM app.events
ORDER BY occurred_at, event_id
LIMIT 100;
```

If occurred_at is not unique, add a tie-breaker like event_id. Clustering on an index may improve locality, yet never replaces ORDER BY and pagination logic.

## 4. How Does MVCC Alter Physical Order?

PostgreSQL uses Multi-Version Concurrency Control (MVCC). UPDATE usually writes a new tuple version instead of overwriting an old tuple still potentially visible to other transactions.

```text
Before UPDATE:
  Heap page 10: tuple version A (visible)

UPDATE row:
  Heap page 10: tuple version A (old/dead once no snapshot needs it)
  Heap page 27: tuple version B (new)

After VACUUM:
  the old tuple's space can be reused
```

### 4.1. UPDATE Can Move Rows Away from Old Pages

If the old page lacks room or UPDATE alters an indexed column, PostgreSQL places the new tuple version on another page and updates indexes.

### 4.2. HOT Updates

A Heap-Only Tuple (HOT) update can skip index updates when conditions hold, specifically when modified columns are unindexed and sufficient room exists on the same page. HOT lowers index churn, yet does not guarantee all UPDATEs stay in fixed logical/physical order.

### 4.3. DELETE and Dead Tuples

DELETE marks tuples invisible to newer snapshots; it does not immediately return bytes to the OS. VACUUM makes that space reusable within the relation.

### 4.4. Why Can CLUSTER Be Useful?

CLUSTER rewrites the heap from live rows in index order. It can:

- Pack rows with nearby keys onto adjacent heap pages.
- Eliminate dead tuple versions from the rewritten copy.
- Reduce physical heap fragmentation.
- Produce fresh layouts for rebuilt indexes.

These benefits must be weighed against rewrite costs.

## 5. What Does CLUSTER Do?

Basic syntax:

```sql
CLUSTER [VERBOSE] table_name [USING index_name];
```

Example:

```sql
CLUSTER VERBOSE app.events
USING events_occurred_at_idx;
```

PostgreSQL builds a new physical table layout ordered by the specified index. Table indexes are also rebuilt to point to the new tuple locations.

### 5.1. It Is a Rewrite Operation

CLUSTER does not merely "shuffle a few pages." It reconstructs the relation's contents in index order and swaps to the new storage files internally.

### 5.2. CLUSTER Is Not a Continuously Maintained Clustered Index

In some other database systems, the term clustered index implies the table is perpetually maintained in key order. In PostgreSQL, CLUSTER is a point-in-time reorganization command.

Subsequent INSERTs/UPDATEs follow ordinary heap allocation rules. Physical correlation can gradually decay.

### 5.3. The Index Must Support CLUSTER

Not every index type can serve as the basis for CLUSTER. Choose an index access method supported by your PostgreSQL version for clustering; B-tree is the standard choice for key ordering. Check version-specific documentation when considering other access methods.

### 5.4. An Index Can Have Duplicate Keys

If the index key is non-unique, rows sharing the same key have no guaranteed stable relative physical order. If secondary ordering matters to queries, design a multi-column index and use an ORDER BY with clear tie-breakers.

## 6. Common CLUSTER Syntax

### 6.1. Cluster a Table Using an Index

```sql
CLUSTER app.events USING events_occurred_at_idx;
```

### 6.2. Cluster Using a Previously Marked Index

```sql
ALTER TABLE app.events
CLUSTER ON events_occurred_at_idx;

CLUSTER app.events;
```

ALTER TABLE ... CLUSTER ON records the index to use for subsequent cluster runs. The ALTER statement itself does not rewrite the table.

### 6.3. Inspect Marked Index

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisclustered
FROM pg_index AS i
WHERE i.indrelid = 'app.events'::regclass;
```

indisclustered=true indicates the index marked as the table's clustering index.

### 6.4. Cluster All Marked Tables

```sql
CLUSTER VERBOSE;
```

Never run this routinely in production. It rewrites every marked table in the current database, incurring huge total cost and prolonged locking.

### 6.5. Cluster a Table Using Its Remembered Index

```sql
CLUSTER VERBOSE app.events;
```

If no clustering index has been marked on the table, omitting USING will not run as intended. Check pg_index.indisclustered beforehand.

## 7. Example: Creating a Time-Ordered Table and Index

Create the lab schema:

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.events (
    event_id bigint PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    customer_id bigint NOT NULL,
    payload text NOT NULL
);
```

Load 100,000 rows in an insert order deliberately uncorrelated with occurred_at:

```sql
INSERT INTO storage_lab.events (
    event_id,
    occurred_at,
    customer_id,
    payload
)
SELECT
    g,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (g % 10000) + 1,
    repeat('x', 100)
FROM generate_series(1, 100000) AS g
ORDER BY md5(g::text);
```

ORDER BY md5(g::text) scrambles insertion order relative to ascending timestamps to illustrate low physical correlation.

### 7.1. Create the Index

```sql
CREATE INDEX events_occurred_at_idx
ON storage_lab.events (occurred_at);

ANALYZE storage_lab.events;
```

### 7.2. Inspect Initial Correlation

```sql
SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'storage_lab'
  AND tablename = 'events'
  AND attname IN ('event_id', 'occurred_at');
```

correlation describes the correlation between column value order and physical row order. Values near +1 or -1 show strong ascending/descending correlation; values near 0 show weak linear correlation.

### 7.3. Measure a Range Query Before CLUSTER

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

Choose a 10-minute slice small enough relative to the whole table. Record execution time, scan type, heap blocks read/hit, actual rows, and buffers.

### 7.4. Cluster by the Timestamp Index

```sql
CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;

ANALYZE storage_lab.events;
```

### 7.5. Re-Measure

Re-run the exact same EXPLAIN (ANALYZE, BUFFERS) query and check pg_stats.correlation.

With randomly inserted lab data, correlation on occurred_at typically climbs near +1 after CLUSTER. Buffers read for the range scan often drop, though exact numbers depend on caching, planner choices, storage hardware, and the chosen plan.

**Do not expect every benchmark to automatically run faster**: if data is already cached, or the planner picks a sequential scan, the difference may be small.

## 8. Why Can Physical Locality Improve Range Scans?

Suppose a query fetches 5,000 consecutive rows by occurred_at.

Before CLUSTER, consecutive keys in the B-tree may point to scattered heap pages:

```text
B-tree key order:
  t1 -> heap page 8
  t2 -> heap page 91
  t3 -> heap page 12
  t4 -> heap page 75
  t5 -> heap page 4

Heap access:
  8 -> 91 -> 12 -> 75 -> 4
```

After CLUSTER, rows with nearby keys are placed close together:

```text
B-tree key order:
  t1 -> heap page 40
  t2 -> heap page 40
  t3 -> heap page 41
  t4 -> heap page 41
  t5 -> heap page 42

Heap access:
  40 -> 41 -> 42
```

Fewer heap pages need to be read, especially when fetching multiple columns absent from the index.

### 8.1. Index Scans and Heap Fetches

If a query only needs columns present in the index and the visibility map permits, PostgreSQL can use an index-only scan, avoiding heap reads. In that scenario, CLUSTER offers less benefit for that query.

### 8.2. Bitmap Heap Scans

A bitmap scan collects TIDs and visits heap pages in page order to minimize random I/O. Physical locality still helps, though gains depend on how many rows and pages are touched.

### 8.3. Sequential Scans

If a query reads most of the table, a sequential scan is already efficient. Reordering the heap will not make a full sequential scan markedly faster.

### 8.4. Caching Can Mask I/O Costs

A single benchmark right after CLUSTER may read mostly from shared buffers or OS page cache. Run multiple iterations, note cache state, and never base production decisions on a single run.

## 9. Physical Correlation and pg_stats

PostgreSQL stores statistics in pg_statistic and exposes the readable view pg_stats.

```sql
SELECT
    schemaname,
    tablename,
    attname,
    correlation,
    null_frac,
    n_distinct
FROM pg_stats
WHERE schemaname = 'storage_lab'
  AND tablename = 'events'
ORDER BY attname;
```

### 9.1. Meaning of Correlation

correlation ranges between -1 and +1:

- Near +1: column values increase alongside physical position.
- Near -1: column values decrease as physical position increases.
- Near 0: no clear linear correlation.

### 9.2. Correlation Is a Statistic, Not a Constraint

It is a planner estimate derived from sampled rows, not a strict guarantee that every tuple sits in exact order.

### 9.3. Run ANALYZE After Rewrites

Once CLUSTER completes, run:

```sql
ANALYZE storage_lab.events;
```

to refresh statistics. Never read stale pg_stats.correlation and conclude CLUSTER failed before refreshing stats.

### 9.4. High Correlation Does Not Prove Every Query Will Be Fast

Queries might not use that index; the table might be small; caching might alter I/O; CPU or joins might be the true bottleneck. Verify with EXPLAIN and real workloads.

## 10. Which Index Should You CLUSTER On?

Choose the clustering index based on queries that genuinely benefit from locality.

Example:

```sql
CREATE INDEX events_customer_time_idx
ON storage_lab.events (customer_id, occurred_at);
```

If queries commonly run:

```sql
SELECT *
FROM storage_lab.events
WHERE customer_id = 123
ORDER BY occurred_at;
```

then physical ordering by (customer_id, occurred_at) clusters each customer's rows together and orders them chronologically within each customer.

### 10.1. Multi-Column Indexes Order Left-to-Right

An index on (customer_id, occurred_at) sorts lexicographically by the first key, then the second. It does not globally sort the entire table by occurred_at.

### 10.2. A Table Has Only One Physical Order at a Time

You cannot cluster the same heap simultaneously by occurred_at, customer_id, and status. Pick one primary ordering; other workloads still rely on indexes, partitioning, or other physical designs.

### 10.3. Do Not Automatically Cluster on the Primary Key

A primary key always has an index, yet queries may predominantly scan by timestamp or tenant. Choose based on actual access patterns, not default index names.

### 10.4. Index Keys and NULL Ordering

Index ordering includes ASC/DESC, NULLS FIRST/LAST, collation, and operator classes. CLUSTER follows the index's ordering; if data includes NULLs or custom collations, verify the intended order.

## 11. CLUSTER Does Not Preserve Order After INSERT/UPDATE

After clustering:

```sql
INSERT INTO storage_lab.events (
    event_id, occurred_at, customer_id, payload
)
VALUES (
    100001,
    TIMESTAMPTZ '2026-01-01 00:00:01+00',
    42,
    'late arrival'
);
```

PostgreSQL does not search the middle of the heap to insert the new row in timestamp order just because the table was previously clustered on occurred_at.

### 11.1. New INSERTs

PostgreSQL uses normal heap allocation to place new tuples. If arrivals are monotonically increasing, physical correlation may stay decent; with late-arriving or random data, correlation degrades.

### 11.2. UPDATEs

UPDATE can write a new tuple version on a different page. If the clustering key itself changes, the row moves further out of order.

### 11.3. DELETEs

DELETE leaves dead tuples until vacuumed, introducing free space and fragmentation into the page layout.

### 11.4. Periodic CLUSTER?

Do not schedule nightly CLUSTER runs just because "tables ought to stay tidy." Measure physical correlation, query latency and buffers, update/delete churn, table size and growth rate, lock windows, and disk/WAL budgets.

Re-cluster only when expected benefits exceed costs and blocking is acceptable.

## 12. Primary Costs of CLUSTER

CLUSTER triggers a substantial burst of resource consumption:

1. Reads the table and index to determine sort order.
2. Rewrites the heap relation.
3. Rebuilds all indexes on the table.
4. Generates heavy WAL and disk I/O.
5. Uses memory and potentially temporary files depending on execution method.
6. Holds a strong lock for the duration.
7. Causes replication lag if standbys cannot replay WAL fast enough.

### 12.1. Disk Space

During the rewrite, old and new copies coexist until swap and cleanup finish. Provision free space roughly equal to the table and its indexes, plus headroom for temp files, WAL, archiving, and replication.

Never use a single fixed multiplier for all tables: TOAST, fillfactor, index count, tablespaces, and execution plans alter exact footprints.

### 12.2. WAL

Rewriting generates heavy writes. Under physical streaming replication, WAL must stream and replay. When WAL generation outpaces replay, replica lag rises.

### 12.3. I/O and CPU

CLUSTER reads old data, writes new data, and rebuilds indexes. Sorting and index building consume heavy CPU, especially on large tables or wide/complex keys.

### 12.4. Duration

Duration depends on table size, indexes, TOAST, storage throughput, cache, memory, concurrent load, and replica setup. Never estimate duration from row count alone.

## 13. Table Locking and Application Impact

CLUSTER acquires an ACCESS EXCLUSIVE lock on the target table. This is the strongest lock mode, blocking concurrent accesses including ordinary SELECTs.

### 13.1. Blocks Readers Too, Not Just Writers

Unlike lightweight maintenance, CLUSTER forces both readers and writers of the table to wait while the lock is held.

### 13.2. Lock Queues Can Cause Domino Effects

A CLUSTER waiting to acquire ACCESS EXCLUSIVE forces new incoming queries behind it in the lock queue, even queries needing only ACCESS SHARE. Always check for long-running transactions and pick safe maintenance windows.

### 13.3. lock_timeout

You can limit how long CLUSTER waits for the lock:

```sql
SET lock_timeout = '5s';
CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

If the lock cannot be acquired within the limit, the command aborts instead of stalling indefinitely. Once the lock is acquired, however, lock_timeout no longer limits total rewrite duration.

### 13.4. statement_timeout

statement_timeout caps total execution time of the statement. If CLUSTER is canceled mid-run, verify rollback/cleanup status and resource recovery.

### 13.5. Long-Running Snapshots

CLUSTER is a rewrite operation and is **not MVCC-safe** in certain scenarios: transactions holding an old snapshot started before the rewrite may observe the table as empty after CLUSTER completes. Avoid running while long transactions/snapshots need ongoing access across the CLUSTER boundary; schedule maintenance and check long-running transactions first.

## 14. CLUSTER and Transaction Boundaries

CLUSTER is a DDL/maintenance command, not a row-level UPDATE. Check rules for your PostgreSQL version and migration tool when scheduling and executing it.

### 14.1. Do Not Wrap CLUSTER in Long Migration Transactions Arbitrarily

Migration frameworks sometimes wrap every step in a transaction. If a command or operational workflow is incompatible with transaction blocks, the pipeline fails. Even when allowed, holding other DDL/locks inside the same transaction extends lock duration.

### 14.2. Run Separately in a Maintenance Job

It is usually safer to run CLUSTER as an isolated maintenance task: log start time; verify exact table/index; check blockers and disk headroom; set timeouts; watch progress; run ANALYZE upon completion.

### 14.3. Do Not Run Multiple Large CLUSTERs in Parallel Casually

Concurrent rewrites compete for I/O, WAL, disk, and locks. Run sequentially or bound concurrency within system budgets.

## 15. Comparing CLUSTER with VACUUM

Regular VACUUM reclaims dead tuples and makes space reusable inside the relation; it does not reorder the entire heap by an index.

```sql
VACUUM (VERBOSE, ANALYZE) storage_lab.events;
```

### 15.1. Regular VACUUM

- Marks dead tuple space reusable.
- Updates the visibility map and free space map.
- Prevents unchecked table/index bloat.
- Normally avoids ACCESS EXCLUSIVE locks.
- Does not rewrite the whole table in index order.

### 15.2. VACUUM ANALYZE

Combines cleanup with updating planner statistics. It is not equivalent to CLUSTER.

### 15.3. Why Does VACUUM Not Create Physical Order?

VACUUM focuses on tuple visibility and space reclamation/reuse. It does not read an index and reconstruct a new heap in index order like CLUSTER.

## 16. Comparing CLUSTER with VACUUM FULL

VACUUM FULL rewrites a table to reclaim disk space, typically taking an ACCESS EXCLUSIVE lock. Its primary goal is compacting/reclaiming storage, not sorting by an index.

```sql
VACUUM (FULL, VERBOSE, ANALYZE) storage_lab.events;
```

| Property | CLUSTER | VACUUM FULL |
| --- | --- | --- |
| Rewrites heap | Yes | Yes |
| Primary goal | Reorder by index | Compact/reclaim space |
| Selects an index for sorting | Yes | No |
| Rebuilds indexes | Yes | Yes as part of rewrite |
| ACCESS EXCLUSIVE | Yes | Yes |
| Maintains order afterward | No | No |
| Best when | Key locality is the goal | Bloat/space reclamation is the goal |

### 16.1. Do Not Use CLUSTER Just to Shrink File Size

If the issue is solely table bloat/space reclamation, evaluate VACUUM FULL or an online rewrite tool. CLUSTER compacts during its rewrite, yet adds sorting overhead for the same heavy rewrite cost.

### 16.2. Do Not Expect VACUUM FULL to Sort Range Scans

VACUUM FULL does not accept an index to order the heap.

## 17. Comparing CLUSTER with REINDEX

REINDEX rebuilds indexes. It does not rewrite the heap in key order.

```sql
REINDEX INDEX storage_lab.events_occurred_at_idx;
```

Or:

```sql
REINDEX TABLE storage_lab.events;
```

### 17.1. When Is REINDEX Needed?

- Confirmed index bloat or corruption.
- Index rebuild required after specific changes.
- Issues with index storage/structure.
- Approved maintenance policy requiring rebuilds.

### 17.2. REINDEX Does Not Improve Heap Correlation

If heap rows are scattered, rebuilding a B-tree simply builds fresh entries pointing to the same scattered heap locations. It does not group rows inside the heap.

### 17.3. REINDEX CONCURRENTLY

PostgreSQL supports REINDEX ... CONCURRENTLY in qualifying cases, reducing blocking compared to standard REINDEX while carrying its own costs, restrictions, and runtime. It is still not equivalent to CLUSTER and does not reorder the heap.

## 18. Comparison with pg_repack

pg_repack is an extension/tool outside PostgreSQL core used to reorganize/compact tables with shorter exclusive lock durations than direct rewrites like CLUSTER or VACUUM FULL.

### 18.1. General Approach

The tool builds a shadow copy, captures concurrent changes during the copy, applies deltas, and takes a brief lock to swap relations/indexes. Specifics depend on extension version and invocation flags.

### 18.2. Not Zero-Lock

pg_repack still requires specific privileges, supported key structures, free disk space, and brief lock acquisition phases. It can fail if prerequisites are unmet or long-running transactions/blockers interfere.

### 18.3. Not a Core Tool

You must install an extension version compatible with PostgreSQL, verify required privileges, replication/DDL policies, backups, and operational procedures.

### 18.4. When to Consider It

When reducing bloat or reordering a large table where long ACCESS EXCLUSIVE downtime is unacceptable, evaluate pg_repack in staging and production runbooks.

## 19. Maintenance Operations Comparison Table

| Operation | Rewrites Heap | Rebuilds Indexes | Sorts Heap by Index | Typical Blocking Level |
| --- | --- | --- | --- | --- |
| VACUUM | No full rewrite | No | No | Lower; normally no ACCESS EXCLUSIVE |
| VACUUM FULL | Yes | Yes | No | ACCESS EXCLUSIVE |
| CLUSTER | Yes | Yes | Yes, by index | ACCESS EXCLUSIVE |
| REINDEX | No | Yes | No | Varies by variant; CONCURRENTLY minimizes blocking |
| pg_repack | Builds/swaps shadow copy | Possible | Possible by index | Designed to shorten final lock; still acquires locks |

Do not treat this table as an exact lock contract across every version/relation type; verify documentation and test specifically.

## 20. Fillfactor and Space for UPDATEs After CLUSTER

After CLUSTER, a table is tightly packed. If the workload continues running UPDATEs, leaving free room on pages aids HOT updates and reduces page splits/row migrations.

Example:

```sql
ALTER TABLE storage_lab.events
SET (fillfactor = 80);
```

Then run CLUSTER in a maintenance window to rewrite under the new setting and ordering.

### 20.1. What Is Fillfactor?

Fillfactor controls page fill targets when tables are built/rewritten or when PostgreSQL allocates tuples per fillfactor rules. Lower values leave more free room for updates.

### 20.2. Trade-Offs

- Lower fillfactor: helps UPDATE/HOT locality, at the cost of larger tables and higher cache footprint.
- Higher fillfactor: saves pages for mostly static data, leaving less room for new tuple versions on the same page.

### 20.3. Do Not Lower Fillfactor Just Because You Heard About HOT

Measure UPDATE rates, HOT updates, page utilization, and query performance before tuning.

### 20.4. Inspecting the Setting

```sql
SELECT
    c.relname,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'storage_lab.events'::regclass;
```

## 21. CLUSTER and TOAST

Large values such as JSON/text can be stored out-of-line via TOAST.

### 21.1. Heap Tuples Can Hold TOAST Pointers

Heap rows still keep metadata/pointers referencing out-of-line data. Rewriting a relation with CLUSTER must maintain both main table contents and associated TOAST data.

### 21.2. Large Payloads Increase Cost

Tables packed with large JSONB or text values incur heavier I/O and disk usage during rewrites. Do not estimate size solely from heap pg_relation_size while ignoring TOAST and indexes.

### 21.3. Measuring Total Size

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap_size,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total_size;
```

pg_total_relation_size includes the relation, indexes, and associated TOAST storage as calculated by PostgreSQL.

## 22. Partitioning Can Reduce the Need for Whole-Table CLUSTER

If data has a time-based lifecycle, partitioning splits a large table into smaller range-based relations:

```sql
CREATE TABLE app.events_partitioned (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

Example monthly partition:

```sql
CREATE TABLE app.events_2026_10
PARTITION OF app.events_partitioned
FOR VALUES FROM ('2026-10-01 00:00:00+00')
TO ('2026-11-01 00:00:00+00');
```

### 22.1. Partition Pruning

Queries filtering on the partition key read only matching partitions. This shrinks scanned data without needing to reorder the entire historical table.

### 22.2. Clustering Per Partition

If deeper locality within a partition is needed, evaluate clustering/rewriting individual child tables per your PostgreSQL version's support and partition layout.

### 22.3. Partitions Do Not Automatically Sort Rows

Each partition remains an ordinary heap relation. Partitioning and CLUSTER address two separate layers: pruning by data range vs. physical locality inside a relation.

### 22.4. Retention

Dropping/detaching old partitions can be far cheaper than deleting millions of rows when policies allow. Yet that is lifecycle management, not a replacement for all CLUSTER use cases.

## 23. BRIN and Naturally Ordered Data

For huge tables whose timestamp column already correlates strongly with physical storage order, a BRIN index can be a compact option:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 23.1. BRIN Operates on Block Ranges

BRIN stores summaries over ranges of heap blocks. When correlation is high, it skips large swaths of irrelevant blocks.

### 23.2. CLUSTER and BRIN Can Complement Each Other

CLUSTER improves physical locality; BRIN leverages that correlation to narrow read ranges. However, continuous updates or random inserts degrade correlation and BRIN efficiency.

### 23.3. Do Not Replace B-Tree with BRIN for Every Query

BRIN is a lossy summary index requiring tuple rechecks. B-trees suit selective lookups and ordered scans. Choose indexes by workload.

## 24. Which Tables Are Worth Clustering?

Favorable traits:

- Large tables with frequent range scan queries.
- Queries filtering along a clear ordered key.
- Queries returning many rows where heap fetch locality matters.
- Data mostly static or inserted roughly in key order.
- Available maintenance window and disk/WAL headroom.

Unfavorable traits:

- Small tables that stay resident in cache.
- Point-lookup workloads returning single rows.
- Heavy random inserts or continuous updates.
- Diverse queries needing conflicting physical orders.
- Inability to tolerate ACCESS EXCLUSIVE blocking.
- Insufficient disk for rewrite plus WAL/replication headroom.

### 24.1. Query Frequency

A rare query running for a few minutes may not justify rewriting a multi-terabyte table.

### 24.2. Selectivity

If a query returns 1 row, B-tree lookup is already fast. If a query fetches hundreds of thousands of rows needing many heap columns, heap locality matters much more.

### 24.3. Shifting Access Patterns

A table queried mainly by timestamp today might shift to customer-based queries next quarter. Clustering by timestamp may cease to be optimal.

## 25. Monitoring CLUSTER Progress

PostgreSQL exposes the pg_stat_progress_cluster view on supported versions.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 25.1. Phases

Phase names and progress columns can vary by version. The view shows which relation is being processed, current phase, and scan/write/rebuild progress.

### 25.2. Counters Do Not Always Advance Smoothly

Different phases update different counters; speed fluctuates with I/O and sorting. Never extrapolate a linear ETA from the first few seconds.

### 25.3. Inspecting the Active Backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text visibility may be restricted by privileges/settings and may contain sensitive values; restrict access appropriately.

## 26. Checking Locks Before Running

A general lock-inspection query:

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 26.1. Finding Blockers and Waiters

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 26.2. Checking Long Transactions

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 26.3. Never Terminate Blockers Automatically

A long transaction could be a migration or critical business job. Before canceling or terminating, verify the owner, request context, rollback impact, and consequences.

## 27. Measuring Sizes Before and After

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 27.1. Smaller Size Does Not Guarantee Faster Queries

A rewrite may compact the table and cut bloat without speeding up queries. Measure latency, buffers, and throughput too.

### 27.2. Larger Size Is Not Always a Bug

Lower fillfactor, TOAST, index builds, and page allocation affect sizes. Verify against your goals and settings.

### 27.3. Filesystem Capacity

pg_total_relation_size does not represent total space needed during a rewrite. Account for WAL directories, archives, replication slots retaining WAL, temporary files, and tablespaces.

## 28. Reading EXPLAIN to Evaluate Gains

Before and after CLUSTER, run the same query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

### 28.1. What to Compare

- Node type: Index Scan, Bitmap Heap Scan, Seq Scan.
- Estimated rows vs. actual rows.
- Heap blocks read/hit.
- Shared buffers.
- Sort method and temp I/O.
- Execution time.
- Rows removed by filter.

### 28.2. Do Not Force enable_seqscan=off as a Standard Benchmark

When the planner picks sequential scan, it may be right. Never disable scan types solely to "prove" CLUSTER helped index scans.

### 28.3. Cache State and Warm-Up

Run multiple iterations and track warm/cold cache states where controllable. Never flush OS caches on production servers for benchmarks.

### 28.4. Identical Workloads

Keep queries, parameters, data volumes, concurrency, and settings identical. Otherwise before/after comparisons are invalid.

## 29. CLUSTER and Post-Rewrite Statistics

Once CLUSTER completes:

```sql
ANALYZE storage_lab.events;
```

### 29.1. Why Does the Planner Need Fresh Statistics?

The planner estimates costs from value distributions, selectivity, correlation, and other stats. Physical ordering changed, so stale statistics may misrepresent the new layout.

### 29.2. Autovacuum/Analyze

Autovacuum updates statistics via triggers/thresholds, yet after a major maintenance rewrite, running ANALYZE proactively gives the planner fresh stats sooner.

### 29.3. Extended Statistics

If queries depend on multi-column correlations, extended statistics may help:

```sql
CREATE STATISTICS events_customer_status_stats
(dependencies, ndistinct)
ON customer_id, status
FROM app.events;

ANALYZE app.events;
```

This example assumes a table with a status column. Extended stats improve multi-column planner estimates; they do not directly alter physical ordering.

## 30. CLUSTER and Index-Only Scans

An index-only scan avoids reading the heap when visibility conditions match the visibility map.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT occurred_at
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00';
```

### 30.1. If the Index Covers All Required Columns

An index-only scan reads directly from the index, minimizing heap access. In that case, CLUSTER adds little benefit for that query.

### 30.2. Visibility Map

PostgreSQL checks which pages are all-visible to skip heap visibility checks during index-only scans. VACUUM updates the visibility map; CLUSTER rewrites physical state and warrants appropriate maintenance/analyze afterward.

### 30.3. Queries Needing Payload Columns

When queries fetch payload columns excluded from the index, heap fetches remain necessary and locality delivers greater value.

## 31. CLUSTER and Partitioned Tables

For partitioned tables, each partition is a separate physical relation. Do not assume running CLUSTER on the parent processes all child tables as one unified heap.

### 31.1. Identify Relation Type

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid IN ('app.events'::regclass);
```

### 31.2. Cluster Individual Partitions When Appropriate

Verify support and limitations for your running PostgreSQL version; where needed, run maintenance on individual physical partitions with separate index and lock budgets.

### 31.3. Partitions Do Not Automatically Sort Rows

Each partition remains an ordinary heap relation. Partitioning and CLUSTER address two separate layers: pruning by data range vs. physical locality inside a relation.

### 31.4. Retention

Dropping/detaching old partitions can be far cheaper than deleting millions of rows when policies allow. Yet that is lifecycle management, not a replacement for all CLUSTER use cases.

## 32. BRIN and Naturally Ordered Data

For huge tables whose timestamp column already correlates strongly with physical storage order, a BRIN index can be a compact option:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 32.1. BRIN Operates on Block Ranges

BRIN stores summaries over ranges of heap blocks. When correlation is high, it skips large swaths of irrelevant blocks.

### 32.2. CLUSTER and BRIN Can Complement Each Other

CLUSTER improves physical locality; BRIN leverages that correlation to narrow read ranges. However, continuous updates or random inserts degrade correlation and BRIN efficiency.

### 32.3. Do Not Replace B-Tree with BRIN for Every Query

BRIN is a lossy summary index requiring tuple rechecks. B-trees suit selective lookups and ordered scans. Choose indexes by workload.

## 33. Which Tables Are Worth Clustering?

Favorable traits:

- Large tables with frequent range scan queries.
- Queries filtering along a clear ordered key.
- Queries returning many rows where heap fetch locality matters.
- Data mostly static or inserted roughly in key order.
- Available maintenance window and disk/WAL headroom.

Unfavorable traits:

- Small tables that stay resident in cache.
- Point-lookup workloads returning single rows.
- Heavy random inserts or continuous updates.
- Diverse queries needing conflicting physical orders.
- Inability to tolerate ACCESS EXCLUSIVE blocking.
- Insufficient disk for rewrite plus WAL/replication headroom.

### 33.1. Query Frequency

A rare query running for a few minutes may not justify rewriting a multi-terabyte table.

### 33.2. Selectivity

If a query returns 1 row, B-tree lookup is already fast. If a query fetches hundreds of thousands of rows needing many heap columns, heap locality matters much more.

### 33.3. Shifting Access Patterns

A table queried mainly by timestamp today might shift to customer-based queries next quarter. Clustering by timestamp may cease to be optimal.

## 34. Monitoring CLUSTER Progress

PostgreSQL exposes the pg_stat_progress_cluster view on supported versions.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 34.1. Phases

Phase names and progress columns can vary by version. The view shows which relation is being processed, current phase, and scan/write/rebuild progress.

### 34.2. Counters Do Not Always Advance Smoothly

Different phases update different counters; speed fluctuates with I/O and sorting. Never extrapolate a linear ETA from the first few seconds.

### 34.3. Inspecting the Active Backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text visibility may be restricted by privileges/settings and may contain sensitive values; restrict access appropriately.

## 35. Checking Locks Before Running

A general lock-inspection query:

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 35.1. Finding Blockers and Waiters

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 35.2. Checking Long Transactions

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 35.3. Never Terminate Blockers Automatically

A long transaction could be a migration or critical business job. Before canceling or terminating, verify the owner, request context, rollback impact, and consequences.

## 36. Measuring Sizes Before and After

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 36.1. Smaller Size Does Not Guarantee Faster Queries

A rewrite may compact the table and cut bloat without speeding up queries. Measure latency, buffers, and throughput too.

### 36.2. Larger Size Is Not Always a Bug

Lower fillfactor, TOAST, index builds, and page allocation affect sizes. Verify against your goals and settings.

### 36.3. Filesystem Capacity

pg_total_relation_size does not represent total space needed during a rewrite. Account for WAL directories, archives, replication slots retaining WAL, temporary files, and tablespaces.

## 37. Reading EXPLAIN to Evaluate Gains

Before and after CLUSTER, run the same query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

### 37.1. What to Compare

- Node type: Index Scan, Bitmap Heap Scan, Seq Scan.
- Estimated rows vs. actual rows.
- Heap blocks read/hit.
- Shared buffers.
- Sort method and temp I/O.
- Execution time.
- Rows removed by filter.

### 37.2. Do Not Force enable_seqscan=off as a Standard Benchmark

When the planner picks sequential scan, it may be right. Never disable scan types solely to "prove" CLUSTER helped index scans.

### 37.3. Cache State and Warm-Up

Run multiple iterations and track warm/cold cache states where controllable. Never flush OS caches on production servers for benchmarks.

### 37.4. Identical Workloads

Keep queries, parameters, data volumes, concurrency, and settings identical. Otherwise before/after comparisons are invalid.

## 38. CLUSTER and Post-Rewrite Statistics

Once CLUSTER completes:

```sql
ANALYZE storage_lab.events;
```

### 38.1. Why Does the Planner Need Fresh Statistics?

The planner estimates costs from value distributions, selectivity, correlation, and other stats. Physical ordering changed, so stale statistics may misrepresent the new layout.

### 38.2. Autovacuum/Analyze

Autovacuum updates statistics via triggers/thresholds, yet after a major maintenance rewrite, running ANALYZE proactively gives the planner fresh stats sooner.

### 38.3. Extended Statistics

If queries depend on multi-column correlations, extended statistics may help:

```sql
CREATE STATISTICS events_customer_status_stats
(dependencies, ndistinct)
ON customer_id, status
FROM app.events;

ANALYZE app.events;
```

This example assumes a table with a status column. Extended stats improve multi-column planner estimates; they do not directly alter physical ordering.

## 39. CLUSTER and Index-Only Scans

An index-only scan avoids reading the heap when visibility conditions match the visibility map.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT occurred_at
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00';
```

### 39.1. If the Index Covers All Required Columns

An index-only scan reads directly from the index, minimizing heap access. In that case, CLUSTER adds little benefit for that query.

### 39.2. Visibility Map

PostgreSQL checks which pages are all-visible to skip heap visibility checks during index-only scans. VACUUM updates the visibility map; CLUSTER rewrites physical state and warrants appropriate maintenance/analyze afterward.

### 39.3. Queries Needing Payload Columns

When queries fetch payload columns excluded from the index, heap fetches remain necessary and locality delivers greater value.

## 40. CLUSTER and Partitioned Tables

For partitioned tables, each partition is a separate physical relation. Do not assume running CLUSTER on the parent processes all child tables as one unified heap.

### 40.1. Identify Relation Type

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid IN ('app.events'::regclass);
```

### 40.2. Cluster Individual Partitions When Appropriate

Verify support and limitations for your running PostgreSQL version; where needed, run maintenance on individual physical partitions with separate index and lock budgets.

### 40.3. Partitions Do Not Automatically Sort Rows

Each partition remains an ordinary heap relation. Partitioning and CLUSTER address two separate layers: pruning by data range vs. physical locality inside a relation.

### 40.4. Retention

Dropping/detaching old partitions can be far cheaper than deleting millions of rows when policies allow. Yet that is lifecycle management, not a replacement for all CLUSTER use cases.

## 41. BRIN and Naturally Ordered Data

For huge tables whose timestamp column already correlates strongly with physical storage order, a BRIN index can be a compact option:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 41.1. BRIN Operates on Block Ranges

BRIN stores summaries over ranges of heap blocks. When correlation is high, it skips large swaths of irrelevant blocks.

### 41.2. CLUSTER and BRIN Can Complement Each Other

CLUSTER improves physical locality; BRIN leverages that correlation to narrow read ranges. However, continuous updates or random inserts degrade correlation and BRIN efficiency.

### 41.3. Do Not Replace B-Tree with BRIN for Every Query

BRIN is a lossy summary index requiring tuple rechecks. B-trees suit selective lookups and ordered scans. Choose indexes by workload.

## 42. Which Tables Are Worth Clustering?

Favorable traits:

- Large tables with frequent range scan queries.
- Queries filtering along a clear ordered key.
- Queries returning many rows where heap fetch locality matters.
- Data mostly static or inserted roughly in key order.
- Available maintenance window and disk/WAL headroom.

Unfavorable traits:

- Small tables that stay resident in cache.
- Point-lookup workloads returning single rows.
- Heavy random inserts or continuous updates.
- Diverse queries needing conflicting physical orders.
- Inability to tolerate ACCESS EXCLUSIVE blocking.
- Insufficient disk for rewrite plus WAL/replication headroom.

### 42.1. Query Frequency

A rare query running for a few minutes may not justify rewriting a multi-terabyte table.

### 42.2. Selectivity

If a query returns 1 row, B-tree lookup is already fast. If a query fetches hundreds of thousands of rows needing many heap columns, heap locality matters much more.

### 42.3. Shifting Access Patterns

A table queried mainly by timestamp today might shift to customer-based queries next quarter. Clustering by timestamp may cease to be optimal.

## 43. Monitoring CLUSTER Progress

PostgreSQL exposes the pg_stat_progress_cluster view on supported versions.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 43.1. Phases

Phase names and progress columns can vary by version. The view shows which relation is being processed, current phase, and scan/write/rebuild progress.

### 43.2. Counters Do Not Always Advance Smoothly

Different phases update different counters; speed fluctuates with I/O and sorting. Never extrapolate a linear ETA from the first few seconds.

### 43.3. Inspecting the Active Backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text visibility may be restricted by privileges/settings and may contain sensitive values; restrict access appropriately.

## 44. Checking Locks Before Running

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 44.1. Finding Blockers and Waiters

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 44.2. Checking Long Transactions

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 44.3. Never Terminate Blockers Automatically

A long transaction could be a migration or critical business job. Before canceling or terminating, verify the owner, request context, rollback impact, and consequences.

## 45. Measuring Sizes Before and After

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 45.1. Smaller Size Does Not Guarantee Faster Queries

A rewrite may compact the table and cut bloat without speeding up queries. Measure latency, buffers, and throughput too.

### 45.2. Larger Size Is Not Always a Bug

Lower fillfactor, TOAST, index builds, and page allocation affect sizes. Verify against your goals and settings.

### 45.3. Filesystem Capacity

pg_total_relation_size does not represent total space needed during a rewrite. Account for WAL directories, archives, replication slots retaining WAL, temporary files, and tablespaces.

## 46. Tablespaces, Memory, and Rewrite Cost

A relation may live in a separate tablespace. Moving tablespaces also rewrites/moves the relation and requires lock/disk/I/O budgets. Never combine it with CLUSTER in one maintenance window without totaling the combined cost.

CLUSTER uses either an index scan or a sort-based approach depending on conditions and planner cost. If sorting is used, maintenance memory and temporary files affect duration.

```sql
SET maintenance_work_mem = '1GB';

CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

1GB is merely an example. Size it according to RAM, concurrent maintenance tasks, and actual version/method behavior.

### 46.1. More Memory Does Not Guarantee Linear Speedup

If the bottleneck is disk throughput, lock waits, or WAL/replication, raising maintenance_work_mem may yield little improvement.

### 46.2. Temporary Files

Monitor temp file creation and disk utilization during maintenance to spot large spills. Do not set maintenance_work_mem overly high when multiple maintenance jobs run concurrently.

### 46.3. Tablespaces and Rewrite Target

Verify tablespace placement, filesystem capacity, and permissions before running. Disk budgets must cover the new relation, indexes, TOAST, temp files, WAL, and archives.

## 47. Impact on Replicas and Backups

CLUSTER emits substantial WAL. With physical streaming replication:

- Primary generates WAL.
- WAL streams to standbys.
- Standbys replay the physical changes.
- Replica lag can rise during the rewrite.

### 47.1. Replication Slots

Replication slots retain WAL whenever subscribers/standbys fall behind. If replay slows down, WAL disk usage can grow significantly.

### 47.2. Read Replicas

Replicas may lag, slowing queries or breaching freshness SLAs. Monitor replay lag, not merely primary completion.

### 47.3. Backup Windows

CLUSTER can inflate WAL archive volume and lengthen backup/restore windows. Ensure backup policies and archive storage have headroom.

### 47.4. Logical Replication

Physical rewrites must not be viewed as a stream of business row-level UPDATEs. Verify logical replication behavior and schema/DDL handling for your version and architecture; never use physical rewrites as a logical data sync mechanism.

## 48. Partitioning and Other Relation Types

For partitioned tables, each partition is a separate physical relation. Never assume CLUSTER on the parent processes all child tables as a single heap. Check version support and limits; where needed, run maintenance per physical partition.

Foreign tables normally lack local heap storage like ordinary tables; regular views are query definitions without heap row storage; materialized views have physical storage yet still require checking relation type and supported commands.

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid = 'app.events'::regclass;
```

Partition pruning shrinks scanned data without requiring whole-history reordering. BRIN can leverage strong physical correlation for range scans on massive tables; it is a lossy summary index requiring tuple rechecks and does not replace B-trees for all lookups/sorts.

## 49. Planning CLUSTER in Production

Before running:

1. Identify the query workload expected to benefit.
2. Measure baseline EXPLAIN/latency/buffers.
3. Inspect physical correlation.
4. Confirm exact target index and table.
5. Measure table/index/TOAST sizes.
6. Calculate disk headroom and WAL/archive budgets.
7. Check replica health and replication slots.
8. Hunt down long-running transactions/snapshots and lock blockers.
9. Pick a maintenance window and notify workload owners.
10. Configure appropriate timeouts.
11. Prepare backup/restore and rollback strategies.
12. Test on staging with comparable data.

During execution, monitor pg_stat_progress_cluster, locks, pg_stat_activity, disk, I/O, WAL, replication lag, and application errors.

After running:

- Run ANALYZE.
- Re-measure EXPLAIN/BUFFERS on the same workload.
- Verify constraints and row counts.
- Monitor replicas catching up.
- Record duration, sizes, and outcomes.
- Decide whether future re-clustering is warranted based on data.

### 49.1. Execution Runbook

```sql
SELECT
    'storage_lab.events'::regclass AS target,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.events')
    ) AS total_size;

SELECT
    indexrelid::regclass AS index_name,
    indisclustered,
    indisvalid,
    indisready
FROM pg_index
WHERE indrelid = 'storage_lab.events'::regclass;
```

After verifying no lock blockers and sufficient disk budget:

```sql
SET lock_timeout = '5s';
SET statement_timeout = '2h';

CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

Timeouts are examples only. Actual limits must match SLAs and table size; handle exceeded limits cleanly.

```sql
ANALYZE storage_lab.events;
```

### 49.2. If CLUSTER Fails or Is Canceled

Causes include lock timeout, statement timeout, operator cancellation, disk full, I/O error, unsuitable index, insufficient privileges, or server restart.

Never judge status solely from a client timeout. Check backend processes, locks, logs, and relation state before retrying. Disk full is critical; never run CLUSTER to "free disk" when a filesystem is nearly full.

After cancellation, confirm the backend finished/rolled back, table queries work, indexes are valid, locks are released, and replicas caught up. Never retry in a loop if the root cause is full disk or a long blocker.

## 50. Monitoring Churn and Post-Maintenance Effectiveness

```sql
SELECT
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'events';
```

### 50.1. Interpreting Fields Properly

- n_tup_upd: recorded UPDATE count.
- n_tup_hot_upd: HOT update count.
- n_dead_tup: dead tuple estimate.
- last_analyze/last_autoanalyze: latest analyze timestamps.

Counters are cumulative/reset by the stats system; never treat them as immutable absolute counts.

### 50.2. Write-Heavy Tables Lose Correlation Quickly

With continuous random UPDATEs/INSERTs, clustering today may only help briefly.

### 50.3. Always Consider the Query Workload

A table with low correlation yet no critical range scans probably does not need CLUSTER.

## 51. Clustering by Tenant or Business Key

A multi-tenant table with an index:

```sql
CREATE INDEX orders_tenant_time_idx
ON app.orders (tenant_id, created_at);
```

Clustering on this index groups rows per tenant together, ordered chronologically within each tenant.

```sql
SELECT *
FROM app.orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at;
```

Physical adjacency of tenants is not RLS, not encryption, and does not replace access control. Other tenants' rows still sit in the same relation and require database authorization protection.

If one tenant is massive, skewed data distribution can affect the planner and cache. Physical ordering does not solve data skew.

## 52. CLUSTER and Append-Only Workloads

An event log typically appended chronologically:

- If source timestamps rise closely with ingestion order, the heap may already have strong correlation.
- With late-arriving events, backfills, or out-of-order imports, correlation drops.

Never assume append-only guarantees monotonic event-time ordering. Compare occurred_at against loaded_at, source lateness, and pg_stats.correlation.

Partitioning can prune most historical data on time-range queries. You can then cluster only historical partitions if workload and maintenance budgets justify it. BRIN can be a lightweight option if data already correlates naturally with time.

## 53. Limitations of CLUSTER

1. Only one physical order per heap at a time.
2. Does not preserve ordering across subsequent writes.
3. Requires an ACCESS EXCLUSIVE lock.
4. Rewrites consume disk, I/O, WAL, and time.
5. Can trigger replica lag.
6. Does not automatically speed up every query.
7. Does not replace index design, partition pruning, vacuum, or statistics.
8. Does not guarantee ordered SELECT output without ORDER BY.
9. Not every index access method or relation type is supported.
10. Carries risks for transactions holding old snapshots across the rewrite.

## 54. PostgreSQL Practice Exercises

Exercises use the storage_lab schema and test data. Never run rewrite or locking tests in production.

1. **Heap:** describe pages, line pointers, and tuples in a heap relation.
2. **Index:** explain how an index entry points to a heap tuple.
3. **CTID:** query ctid on several rows and explain block/offset.
4. **CTID stability:** UPDATE a row and inspect ctid before/after.
5. **MVCC:** describe old/new tuple versions after UPDATE.
6. **HOT:** list conditions enabling an UPDATE to become a HOT update.
7. **Dead tuples:** explain why DELETE does not immediately shrink file size.
8. **Ordering:** run SELECT without ORDER BY multiple times and explain why order is not guaranteed.
9. **ORDER BY:** add a tie-breaker to a pagination query.
10. **Index locality:** sketch an example of ordered keys vs. scattered heap pages.
11. **CLUSTER:** explain the goal of the CLUSTER command.
12. **Syntax:** run CLUSTER table USING index on the lab table.
13. **Mark index:** use ALTER TABLE ... CLUSTER ON and verify indisclustered.
14. **Remembered index:** run CLUSTER table omitting USING after marking it.
15. **All tables:** explain the risk of running CLUSTER VERBOSE without a table name.
16. **Index eligibility:** verify which access methods in your running version allow CLUSTER.
17. **Multi-column:** create an index on (customer_id, occurred_at) and explain lexicographic ordering.
18. **Tie keys:** create a non-unique index and explain ordering among rows with duplicate keys.
19. **Lab data:** insert 100,000 rows in uncorrelated insertion order.
20. **Baseline:** create the occurred_at index and run ANALYZE.
21. **Correlation:** read pg_stats.correlation before CLUSTER.
22. **Benchmark:** run EXPLAIN (ANALYZE, BUFFERS) for a range query.
23. **Cluster:** CLUSTER using events_occurred_at_idx.
24. **Analyze:** run ANALYZE after CLUSTER and re-read correlation.
25. **Compare:** compare heap blocks and latency before/after.
26. **Cache:** explain why warm-cache benchmarks differ from cold-cache benchmarks.
27. **Index-only:** write a query selecting only indexed columns and inspect index-only scan eligibility.
28. **Payload:** add payload to the SELECT list and observe how heap fetches change.
29. **Seq scan:** explain when the planner chooses sequential scan despite an existing index.
30. **Physical order:** explain why CLUSTER does not guarantee ordered SELECT results.
31. **New insert:** INSERT an older timestamp after CLUSTER and analyze locality.
32. **Update key:** UPDATE the clustering key and explain the new tuple version.
33. **Write churn:** inspect n_tup_upd and n_tup_hot_upd in pg_stat_user_tables.
34. **Recluster:** name signals justifying running CLUSTER again.
35. **VACUUM:** run VACUUM ANALYZE and explain how it differs from CLUSTER.
36. **VACUUM FULL:** explain its space-reclamation goal and locking behavior.
37. **REINDEX:** rebuild an index and demonstrate heap order is not reorganized.
38. **pg_repack:** study the extension's prerequisites and locking model.
39. **Comparison:** build a table comparing VACUUM, VACUUM FULL, CLUSTER, REINDEX, and pg_repack.
40. **Fillfactor:** set fillfactor 80 and analyze the trade-off with page density.
41. **HOT:** explain why fillfactor helps HOT while enlarging storage footprint.
42. **TOAST:** measure pg_total_relation_size and distinguish heap/index/TOAST.
43. **Disk budget:** plan disk capacity needed to rewrite a large table.
44. **WAL:** explain why CLUSTER generates WAL and can increase replica lag.
45. **Lock mode:** study ACCESS EXCLUSIVE and conflicting locks.
46. **Blockers:** use pg_locks and pg_stat_activity to locate sessions holding locks.
47. **Waiting:** explain the lock-queue domino effect when CLUSTER waits for ACCESS EXCLUSIVE.
48. **lock_timeout:** test a short lock_timeout in the lab and observe the error.
49. **statement_timeout:** distinguish lock wait limit from total execution limit.
50. **Old snapshots:** explain the MVCC-safety warning when transactions hold old snapshots.
51. **Progress:** query pg_stat_progress_cluster while another session runs CLUSTER.
52. **Size:** measure heap/index/total size before and after rewrite.
53. **Memory:** study maintenance_work_mem and its impact on sorting/temp files.
54. **Temp I/O:** monitor temp files during a large sort operation.
55. **Partition:** create time partitions and explain how partition pruning differs from CLUSTER.
56. **Partition maintenance:** propose a policy to cluster only historical partitions.
57. **BRIN:** create a BRIN index on occurred_at and compare with B-tree.
58. **Tenant index:** create an index on (tenant_id, created_at) and analyze physical grouping.
59. **Security:** explain why physical grouping is not tenant isolation.
60. **Collation:** create an index with a collation and analyze CLUSTER ordering.
61. **Index mark:** switch the marked cluster index and verify metadata.
62. **Replica:** design a replay-lag dashboard for maintenance windows.
63. **Backup:** analyze WAL archive/storage impact during rewrites.
64. **Tablespace:** inspect table/index tablespaces and disk headroom.
65. **Production plan:** write a pre-flight checklist before running CLUSTER on a 500 GB table.
66. **Cancel:** outline procedures if CLUSTER is canceled or the server disconnects.
67. **EXPLAIN:** compare Index Scan and Bitmap Heap Scan after clustering.
68. **Buffers:** distinguish shared hit from shared read in EXPLAIN.
69. **Query diversity:** explain why one table cannot optimize physical order for every index.
70. **Workload:** pick a query with suitable selectivity to benchmark CLUSTER.
71. **No benefit:** list three scenarios where CLUSTER yields no performance gain.
72. **Append-only:** evaluate correlation of data written in event-time order.
73. **Late arrivals:** analyze the effect of late-arriving records on physical order.
74. **Partition + BRIN:** propose an architecture for a massive event table.
75. **Long transactions:** query long transactions before maintenance.
76. **Monitoring:** write queries monitoring pg_stat_progress_cluster, pg_locks, and pg_stat_activity.
77. **Capacity:** sum disk requirements for the new heap, indexes, TOAST, WAL, and temp files.
78. **Benchmark integrity:** design a protocol keeping queries, parameters, cache, and concurrency consistent.
79. **Maintenance cadence:** define re-clustering criteria based on correlation, query latency, and write churn.
80. **Comprehensive design:** choose clustering index, fillfactor, schedule, lock/timeouts, disk/WAL budgets, replica monitoring, ANALYZE, and rollback plan for a production table with range queries.

## 55. Pre-Decision Checklist

### Workload

- [ ] Significant range scan queries read many rows and heap columns.
- [ ] Queries actually use the proposed clustering index.
- [ ] Current physical correlation is low or locality is problematic.
- [ ] Gains are proven via EXPLAIN/BUFFERS or benchmarks.
- [ ] No competing physical order is more critical.

### Cost

- [ ] Table/index/TOAST sizes are measured.
- [ ] Filesystems and tablespaces have enough disk headroom.
- [ ] WAL/archive/replication slots have headroom.
- [ ] I/O and CPU can absorb the rewrite.
- [ ] Maintenance window duration is sufficient.

### Blocking and Consistency

- [ ] Acquiring an ACCESS EXCLUSIVE lock is acceptable.
- [ ] Long-running transactions/snapshots have been checked.
- [ ] Application owners know the table will block.
- [ ] Timeouts and cancel/rollback plans are prepared.

### Post-Maintenance

- [ ] ANALYZE was executed.
- [ ] EXPLAIN/BUFFERS were re-measured.
- [ ] Replica lag is monitored until caught up.
- [ ] Query latency/throughput meet targets.
- [ ] A plan exists to monitor correlation decay over time.

## 56. Summary

CLUSTER is worth considering when **heap locality is a proven bottleneck**. An index range scan retrieving many rows and multiple columns benefits when rows with adjacent keys sit on nearby heap pages. Yet rewriting an entire relation costs more than it helps if workloads churn continuously or do not need locality.

```text
CLUSTER
  = REWRITE HEAP IN INDEX ORDER
  + REBUILD INDEXES
  + ACCESS EXCLUSIVE LOCK
  + DISK / I/O / WAL COST
  + POTENTIALLY BETTER PHYSICAL LOCALITY

AFTER CLUSTER
  INSERT / UPDATE / DELETE CONTINUE
  VIA NORMAL HEAP ALLOCATION
  -> CORRELATION CAN GRADUALLY DECAY
```

Key principles:

- **Heap and index are separate structures.** Index order does not automatically imply heap order.
- **Only ORDER BY guarantees result order.** CLUSTER alters physical layout only.
- **MVCC creates multiple tuple versions.** UPDATE, DELETE, and INSERT gradually erode locality.
- **CLUSTER rewrites the table by index**, rebuilds indexes, and takes an ACCESS EXCLUSIVE lock.
- **CLUSTER does not maintain order for subsequent writes.** Re-evaluate based on workload and physical correlation.
- **Costs extend beyond statement runtime:** account for disk, TOAST, indexes, WAL, replica lag, temp I/O, and blocking.
- **VACUUM, VACUUM FULL, REINDEX, and pg_repack serve different goals.** Match the tool to the problem.
- **Measure before/after with EXPLAIN (ANALYZE, BUFFERS)** and refresh stats with ANALYZE.
- **Never run heavy rewrites with tight disk or active long-running snapshots/transactions.** Enforce lock, timeout, and rollback plans.
- **Pick the clustering index by query workload**, not habit or merely because it is the primary key.

Understanding CLUSTER lets you deliberately improve heap locality for the right workloads while anticipating rewrite impacts on applications, storage, WAL, and replicas. Sound decisions always start by **measuring physical correlation and query cost**, and finish by verifying real gains after maintenance.
