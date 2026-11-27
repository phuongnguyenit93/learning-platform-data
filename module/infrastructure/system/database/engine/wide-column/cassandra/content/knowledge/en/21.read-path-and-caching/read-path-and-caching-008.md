# Reads Hitting Many SSTables, Tombstones, and Fragmented Data in Apache Cassandra

## 1. The Problem: Returning a Few Rows While Reading Huge Amounts of Data

In Apache Cassandra, a distributed **wide-column** database, applications typically read by **partition key** and a **clustering key** range. Query-driven table design routes requests swiftly to the right replicas, yet **reaching the right partition does not mean reading only one file or one data version**.

The same partition can be updated across many flushes. Its data sits in the active **memtable** and multiple immutable **SSTables** on disk. Updates, deletes, and TTL expirations also generate **tombstones**. When serving a query, Cassandra must locate every source holding that partition, merge records and tombstones in proper order and timestamp precedence, and only then return live rows.

A classic case:

- The application requests `LIMIT 20` newest events for a device.
- The device's partition spans many SSTables due to continuous writes and unfinished compaction.
- Many newer rows have expired by TTL or been deleted, leaving tombstones.
- Cassandra may read, reconcile, and discard huge numbers of entries before finding 20 live rows.

This is **read amplification**: the volume of data and work processed far exceeds what the application receives. It inflates p95/p99 read latency, disk accesses, CPU, temporary memory, and compaction pressure.

The objective of this lesson in the **Read Path and Caching** chapter is to understand the root causes of read amplification, distinguish **many SSTables**, **tombstones**, and **fragmented data**, and select safe ways to measure, tune CQL, model partitions, and operate clusters.

## 2. Components That Can Participate in a Single Read

### 2.1. Storage Layers to Know

| Component | Role on the Read Path |
|---|---|
| **Memtable** | Holds unflushed mutations; recent in-memory data must be checked during reads |
| **SSTable** | Immutable file created by flush or compaction; one partition may span many SSTables |
| **Bloom filter** | Quickly answers "partition is definitely absent from this SSTable" or "might be present"; "might" requires further lookup |
| **Partition key cache / key cache** | Reduces partition offset lookup work in SSTables on cache hits; does not eliminate reading data itself |
| **Index summary and partition index** | Helps locate offsets inside SSTables, cutting disk seeks |
| **Compression metadata / chunks** | Supports locating/decompressing compressed data chunks; may require decompressing a whole chunk even for a partial read |
| **Row cache** (if enabled) | Can serve certain reads from cache; helpful depending on workload and update patterns |

**Note:** A **negative** Bloom filter excludes an SSTable for a partition; a **positive** only means *might contain*, due to false-positive probability. Bloom filters skip unrelated SSTables, but **never eliminate old versions, tombstones, or valid versions** of a partition.

### 2.2. Read Flow from Client to Replica

~~~mermaid
flowchart TD
    A["Java / CQL Application"] --> B["Coordinator: select replicas by partition key and read CL"]
    B --> C["Replica: check caches and memtable"]
    C --> D["Identify candidate SSTables via metadata / Bloom filters"]
    D --> E["Read required indexes and data chunks"]
    E --> F["Merge versions, TTLs, and tombstones"]
    F --> G["Return live rows / digest to coordinator"]
    G --> H["Coordinator reconciles replicas per read CL"]
    H --> I["Return result to application"]
~~~

This is a **conceptual** model. In practice, replicas use optimizations and access orders that vary by Cassandra version, caches, partition indexes, clustering filters, and compaction strategies. Coordinators may also issue data/digest requests, reconcile discrepancies, and apply version-specific read mechanisms.

For a query that already supplies full routing keys, the bottleneck can live **inside a replica** when merging many versions and tombstones. Raising the read consistency level does not remove that local merge work.

## 3. Why Does One Partition Span Many SSTables?

SSTables are immutable once written. Writing a new mutation to an existing key **never modifies an old SSTable in place**; the mutation goes to the commit log/memtable and later flushes to a new SSTable. Compaction merges eligible files later.

Example for a partition `device_id = D`:

| Time | Mutation | Where It May Sit on Read |
|---|---|---|
| `t0` | Insert sensor samples 1–100 | SSTable A after flush |
| `t1` | Insert sensor samples 101–200 | SSTable B |
| `t2` | Update sample 125 | SSTable C holding newer version |
| `t3` | Delete sample 80 | SSTable D holding tombstone |
| `t4` | Insert samples 201–230 | Memtable or SSTable E |

A `SELECT` touching that partition may need to inspect A, B, C, D, and E together. Cassandra must determine valid values by timestamp and tombstones; it cannot simply return rows seen in one arbitrary SSTable.

**Fragmented data** in this lesson means **rows, versions, or deletion markers of the same partition scattered across multiple SSTables and storage regions**, not necessarily filesystem block fragmentation. Common causes include:

1. Steady writes producing frequent flushes; many uncompacted SSTables.
2. Frequent updates to the same partition/cell generating multiple versions.
3. Tombstones from `DELETE` or TTLs sitting in different SSTables from older data.
4. Compaction falling behind write throughput or using an ill-suited strategy.
5. Oversized partitions with wide clustering ranges spanning many chunks.
6. Late/out-of-order writes into historical data (especially in time-series tables), placing the same partition across SSTables from different times.

Data fragmentation is an inherent property of LSM architectures; what must be controlled is **real read cost** and compaction keeping pace.

## 4. What Are Tombstones and Why Must Reads Process Them?

Cassandra cannot delete data by instantly erasing every old copy everywhere. Instead, deletions are represented by **tombstones**, markers carrying timestamp metadata to shadow older matching values.

Tombstones arise from:

- `DELETE` on a cell, a row, or an entire partition.
- `UPDATE` setting a column to `null` in relevant CQL contexts.
- Cell or row TTL expiration: expired data becomes invalid and behaves as deleted.
- Collection element/range deletions or whole-collection replacements, depending on data model and CQL.

Example:

~~~cql
CREATE TABLE demo.readings_by_device (
    device_id uuid,
    observed_at timestamp,
    value double,
    PRIMARY KEY (device_id, observed_at)
);

INSERT INTO demo.readings_by_device (device_id, observed_at, value)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21T08:00:00Z',
    36.5
);

DELETE FROM demo.readings_by_device
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND observed_at = '2026-11-21T08:00:00Z';
~~~

The `DELETE` creates a deletion marker. If an older SSTable still holds `value=36.5`, the read path must **process the tombstone** to avoid returning deleted data. Skipping the SSTable holding the tombstone would resurrect the stale value.

### 4.1. Tombstones Have Multiple Scopes

| Type / Scope | Impact on the Read Path |
|---|---|
| **Cell tombstone** | Shadows an older column/cell value |
| **Row tombstone** | Shadows a row matching the clustering key |
| **Range tombstone** | Shadows a clustering range; scans may intersect many live and deleted items |
| **Partition tombstone** | Shadows older data across the entire partition |

Storage encoding and tombstone visibility vary by Cassandra version. What stays constant is that **reads must reconcile both live data and deletion markers**, rather than treating tombstones as client-visible rows.

### 4.2. Why Can `LIMIT 10` Still Scan Huge Amounts of Data?

Suppose a partition has 5,000 entries in read order, and the leading 4,900 entries are deleted or TTL-expired. A `LIMIT 10` query does not return those 4,900 entries, yet Cassandra may still have to walk through all those deletion markers and shadowed values to find 10 live rows.

Illustration:

~~~text
Replica scanner:
[T][T][T][T][T] ... [T] [LIVE-1] [LIVE-2] ... [LIVE-10]
 \_______________/
    Many tombstones

Application only sees 10 live rows.
~~~

The result can be a **tombstone scan**: higher latency, more memory/chunk reads, and—once configured version thresholds are crossed—warning logs or aborted queries. A small `LIMIT` **does not guarantee a small scan**.

### 4.3. TTL Does Not Mean "Instant Physical Cleanup"

Example:

~~~cql
INSERT INTO demo.readings_by_device (device_id, observed_at, value)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21T08:05:00Z',
    37.0
)
USING TTL 86400;
~~~

After 86,400 seconds, the data is no longer live for normal queries, yet physical reclamation does not necessarily happen at expiration time. Expiration/deletion metadata must still be retained and safely processed during compaction under conditions that prevent resurrecting old data.

Thus, "this table only retains 24 hours of data" **does not mean** disk files contain zero traces of older data after 24 hours or that queries will never encounter tombstones.

## 5. How Three Sources of Read Amplification Compound

A read can be analyzed along three axes:

**(A) Many candidate SSTables:** the replica must check metadata/indexes and potentially read data across many files to assemble valid versions.

**(B) Many tombstones in the query slice:** the scanner must skip many deletion markers before finding live rows; small returned row counts hide the real work performed.

**(C) Large partitions/clustering ranges with many versions:** reading across many blocks/chunks and reconciling numerous mutations on the same keys; caches become less effective if hot data grows too large.

Illustrative comparison (not default Cassandra measurements):

| Indicator | Healthy Query | Problematic Query |
|---|---:|---:|
| SSTables inspected on one replica | 2 | 14 |
| Entries/tombstones scanned | 40 | 8,000 |
| Live rows returned | 20 | 20 |
| Data layout inside partition | A few chunks | Many chunks scattered across SSTables |

Both queries return 20 rows, yet the work differs dramatically. Real numbers must be confirmed using **metrics and tracing**, never guessed from `LIMIT` or total table SSTable count.

### A Mental Cost Model

Read cost grows with the number of involved SSTables, entries/tombstones scanned, data decompressed/reconciled, and replicas contacted. These are **explanatory factors**, not a linear formula that predicts exact latency.

When CPU is low yet read p99 is high, inspect disk I/O and SSTable/chunk access. When GC/CPU spikes alongside `tombstones scanned`, examine the volume of entries being merged. When compaction lags, rising SSTable counts become a persistent symptom.

## 6. Read Consistency and Caching Do Not Fix the Root Cause

Read consistency levels such as `ONE`, `LOCAL_QUORUM`, or `QUORUM` specify replica participation per topology and consistency goals. **Each replica still builds its result locally from its own memtable and SSTables.** Raising consistency levels triggers more inter-replica exchanges/reconciliation at the coordinator, but neither erases tombstones nor merges SSTables on disk.

Caches also have limits:

- **Key cache** speeds up locating partitions in SSTables, without making old SSTables disappear.
- **Bloom filters** skip SSTables guaranteed not to hold the partition; when the partition truly exists in many SSTables, they still must be read.
- **Row cache** can accelerate repeated reads when workloads fit and caching stays effective; frequent updates, huge partitions, or wide scans erode its value.

Tuning caches before fixing oversized partitions or heavy tombstones only treats the surface. Pinpoint whether read amplification lies in **routing**, **data reading**, or **tombstone/version reconciliation**.

## 7. Query-Driven Table Design to Narrow the Read Scope

Suppose an application stores telemetry and the primary query is:

> "Fetch up to 100 latest events for device D within one hour on day N."

Design the partition key so queries resolve directly to it; avoid stuffing years of history for a device into one unbounded partition.

~~~cql
-- Assume the telemetry keyspace already exists.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id timeuuid,
    metric_value double,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 604800;
~~~

Here:

- `(device_id, event_day)` is the **composite partition key**, bucketing data by device and day to prevent unbounded partition growth.
- `event_time` and `event_id` are **clustering columns**; descending order supports fetching the newest events directly.
- `event_id` disambiguates events sharing the same timestamp.
- A default TTL of 604,800 seconds (7 days) fits if retention is genuinely 7 days; TTLs carry tombstone cost, so monitor them carefully.

The query specifies both routing keys and a bounded clustering slice:

~~~cql
SELECT event_time, event_id, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T10:00:00Z'
  AND event_time < '2026-11-21T11:00:00Z'
LIMIT 100;
~~~

Cassandra jumps straight to **one known partition** and **one clustering interval** instead of scanning across many partitions. This shrinks candidate data, though if that partition experiences heavy updates/deletes, multiple SSTables and tombstones in that slice can still cause read amplification.

### 7.1. Never Treat `ALLOW FILTERING` as a Performance Fix

Filtering on non-key columns—such as scanning the table for `metric_value > 80`—pushes broad filtering work onto the server:

~~~cql
-- Example query pattern requiring schema redesign:
SELECT *
FROM telemetry.events_by_device_day
WHERE metric_value > 80
ALLOW FILTERING;
~~~

`ALLOW FILTERING` does not merge SSTables, remove tombstones, or turn a scan into an efficient partition-key lookup. If the business truly needs threshold queries, consider a **dedicated query table**, an aggregation pipeline, or an index appropriate for your version and workload, benchmarking actual cost first.

### 7.2. Size Buckets to Access Patterns, Not a Fixed Rule

Bucketing by day, hour, or other intervals involves trade-offs:

- **Too large** a bucket: wide partitions with lots of stale/TTL-expired data in read paths.
- **Too small** a bucket: one query must hit multiple partitions/buckets and merge results in the application.
- Buckets must match write volume, partition sizes, query windows, and retention periods.

No single bucket size fits every system. Measure **partition size** distributions, write rates, and cross-bucket query ratios.

## 8. How Does Compaction Reduce Fragmentation?

**Compaction** reads selected SSTables, merges matching versions, writes new SSTables, and reclaims old files once safe. It reduces the number of files reads must check, eliminates obsolete duplicates, and evicts tombstones when safety conditions are satisfied.

However, compaction consumes I/O, CPU, and temporary disk space. If mutation rates persistently outpace compaction capacity, a backlog prolongs multi-SSTable reads.

| Strategy | Characteristics Affecting Read Amplification | Best Suited When |
|---|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Groups similarly sized SSTables; overlapping key ranges across multiple SSTables can make reads check more files | Write-heavy workloads with tolerable read requirements |
| **LeveledCompactionStrategy (LCS)** | Organizes into levels to limit key-range overlap within each level (except e.g. L0); usually cuts SSTables read for point lookups at higher write/compaction overhead | Latency-sensitive reads, frequent updates, ample I/O headroom |
| **TimeWindowCompactionStrategy (TWCS)** | Groups data into time windows; for append-only data with uniform TTLs, wholly expired SSTables can be dropped cleanly once eligible | Time-series data written chronologically with uniform expiration |

Evaluate strategies for your **running Cassandra version** and real workload. Switching compaction strategies on a large table does not instantly eliminate fragmentation; the transition and backlog can consume heavy I/O.

### 8.1. TWCS and TTLs: Advantageous Under Conditions

TWCS minimizes tombstone overhead when data stays within discrete time windows and whole SSTables expire together. Effectiveness drops sharply if:

- Historical data is frequently updated or written out-of-order into closed windows.
- Widely varying TTLs or **non-TTL** data are mixed into the same SSTable windows.
- Frequent ad-hoc deletes occur or partitions span many windows.
- Compaction lacks I/O resources or tombstone eviction safety rules are not yet met.

Never assume TWCS is optimal solely from the name "time window." Check timestamp distributions, TTL uniformity, late-write rates, and actual read patterns.

### 8.2. Why Can't Tombstones Be Dropped Immediately?

If a replica was disconnected during a delete and still holds the old value, purging tombstones too early risks **zombie data** reappearing when that replica rejoins and syncs. `gc_grace_seconds` together with repair/purge conditions limits this risk.

Therefore:

- Never set `gc_grace_seconds = 0` just to cut tombstone scans without a proven safe operational design.
- Run repair on a schedule aligned with replication, recovery windows, and cluster settings; nodes offline longer than grace windows require special handling.
- **Repair** synchronizes replicas, but does not directly drop tombstones on disk on its own. **Compaction** reclaims them on disk when safe.
- Never force table-wide compaction in production merely because one query is slow; evaluate I/O impact, temporary disk space, strategy, and data-model fixes first.

## 9. Diagnosis: Distinguishing Many SSTables from Many Tombstones

### 9.1. Ordered Investigation Questions

1. **Which query is slow?** Capture exact CQL/bindings, partition key, clustering range, `LIMIT`, read CL, and p95/p99 latency.
2. **How is it routing?** Does it supply the full partition key? Is it scanning entire partitions or wide intervals? Is `ALLOW FILTERING` used?
3. **How many SSTables does one read touch?** Check per-table/replica "SSTables per read" stats and cache hit rates.
4. **Is it scanning many tombstones?** Check warnings, `tombstones scanned` vs. live rows returned; note whether slowness hits older slices specifically.
5. **Is compaction keeping up?** Check pending compactions, backlog, disk I/O, partition sizes, and write/delete/TTL rates.
6. **Is there a cross-replica issue?** Isolate slow replicas, read timeouts, read repair, and network/node health from single-replica read amplification.

### 9.2. Observability Tools

In an environment with Cassandra operator access and supported version:

~~~bash
# Table statistics: SSTable count, latency, partition size,
# tombstones/cells per slice (exact metric names vary by version).
nodetool tablestats telemetry.events_by_device_day

# Distribution of SSTables per read, read latency, partition size...
nodetool tablehistograms telemetry events_by_device_day

# Status of active compactions and backlog.
nodetool compactionstats
~~~

In `cqlsh`, selective tracing can inspect a sample query:

~~~cql
TRACING ON;
SELECT event_time, event_id, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T10:00:00Z'
  AND event_time < '2026-11-21T11:00:00Z'
LIMIT 100;
TRACING OFF;
~~~

Tracing adds overhead and does not mirror full production load. Use selectively and correlate with per-node/table metrics. Metric names and tombstone warning/failure thresholds vary by version and config; inspect your live cluster's metrics before comparing absolute thresholds.

| Symptom | Hypothesis to Test | Next Action |
|---|---|---|
| High SSTables per read, low tombstone scans | Overlapping SSTables / compaction backlog, poor cache/index efficiency | Check strategy, `compactionstats`, I/O, update workload |
| Very high tombstones scanned despite small `LIMIT` | Dense TTLs/deletions at the front of the clustering slice | Narrow scan range, adjust buckets/TTL, curb bulk deletes |
| Large partition size, only certain keys very slow | Hot/wide partitions, too many rows/chunks | Bucket appropriately, bound query time windows |
| All reads slow at once | Node load, disk saturation, GC, network, or compaction I/O contention | Check infrastructure and replica metrics |
| Slow after backfilling historical data | Out-of-window writes, multi-generation SSTables | Align compaction strategy with late writes; check SSTable spread |

## 10. Java Example: Reading the Right Partition and Bounding Fetch Size

With **DataStax Java Driver 4.x**, prefer prepared statements binding the full partition key and a bounded clustering slice. Assume `CqlSession session` is configured for the proper datacenter and the example keyspace/table already exists:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement select = session.prepare(
    "SELECT event_time, event_id, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? " +
    "LIMIT 100"
);

UUID deviceId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement query = select.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T10:00:00Z"),
        Instant.parse("2026-11-21T11:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);

for (Row row : session.execute(query)) {
    Instant eventTime = row.getInstant("event_time");
    UUID eventId = row.getUuid("event_id"); // CQL timeuuid
    double value = row.getDouble("metric_value");
    // Process or pass data to display page.
}
~~~

`setPageSize(50)` caps how many rows the driver fetches per page; `LIMIT 100` caps total rows returned by the query. The driver transparently fetches subsequent pages as iteration continues. **Paging bounds response payload and client memory per round trip**, yet it does not prevent the server from scanning many tombstones to find enough live rows. To paginate beyond 100 rows, use paging state/cursors rather than relational SQL-style `OFFSET`.

Here, `LOCAL_QUORUM` is simply an illustration for a matching topology; actual read CL must match consistency and replication requirements. Changing read CL will never turn a tombstone-heavy scan into a cheap query.

### What the Driver Cannot Fix on Its Own

- Cannot shrink an oversized partition.
- Cannot avoid tombstone scans if the query asks for rows behind a deleted range.
- Cannot force compaction to catch up.
- Cannot turn `ALLOW FILTERING` into a partition/clustering index lookup.

The Java layer should enforce **sensible timeouts, per-query latency observability, bounded time ranges, paging, backpressure, and controlled retries**. If queries are systematically slow, fix the data model or Cassandra operations.

## 11. Handling a Real-World Incident Step by Step

Suppose a device's "20 newest events" API jumps from tens of milliseconds to several seconds after a data-cleanup job.

1. **Gather evidence:** capture exact query/bindings and latency; identify slow nodes/replicas, SSTables-per-read and tombstones-scanned metrics, and affected tables.
2. **Isolate causes:** heavy tombstones after a bulk `DELETE` differ from overlapping SSTables caused by compaction backlog—though both can coexist.
3. **Narrow the read scope first:** partition by day/hour with bounded clustering ranges, verify `LIMIT`/paging. Never rely on full scans for API convenience.
4. **Re-evaluate retention design:** if bulk daily deletes happen, consider time-bucketed schemas + matching TTLs, checking new tombstone effects and retention rules.
5. **Re-evaluate compaction strategy:** inspect write amplification, backlog, SSTables per read, and TTL distributions. For append-only time series, evaluate TWCS if workload fits; for update-heavy latency-sensitive reads, evaluate LCS.
6. **Preserve deletion safety:** keep repair and `gc_grace_seconds` aligned with replica consistency policies; never drop safety margins arbitrarily just to reclaim space.
7. **Re-measure on representative traffic:** compare p50/p95/p99, SSTables per read, tombstones scanned, disk I/O, CPU, pending compactions, and actual returned rows.

Never conclude "just add RAM/cache" without identifying **why replicas must merge so many files or deletion markers**. When schema changes are needed, execute controlled migrations/backfills without unleashing write bursts that choke compaction.

## 12. Self-Check Exercises

**Question 1.** A `SELECT ... LIMIT 10` hits 20 SSTables and scans thousands of tombstones. Why is returning 10 rows still slow?

**Explanation:** `LIMIT` only caps live rows returned; the server must still search across those SSTables and skip deletion markers until it finds 10 valid rows.

**Question 2.** SSTable S's Bloom filter returns "partition P absent." Does the replica need to open S's data file to check for P?

**Explanation:** No for P; negative Bloom filter results are definitive exclusions. Positive results may be false positives and require further checking.

**Question 3.** A row was deleted, yet an older SSTable still holds it. Why can't Cassandra skip the tombstone immediately?

**Explanation:** Tombstones shadow old values during merges and propagate deletions to replicas that missed the mutation. Dropping markers too soon risks zombie data.

**Question 4.** Does switching a tombstone-heavy query to `LOCAL_QUORUM` eliminate tombstone scans?

**Explanation:** No. Read CL controls replica participation; each participating replica still processes its own local storage sources.

**Question 5.** Why is TWCS typically better suited for uniformly TTL'd time-series data than for tables constantly updating old records?

**Explanation:** For append-only workloads, time windows compact separately and whole SSTables expire close together. Late updates to past windows and mixed TTLs cause overlapping files that cannot be reclaimed cleanly.

**Question 6.** Seeing a tombstone warning, should you immediately set `gc_grace_seconds = 0` and force compaction?

**Explanation:** No. Analyze queries, retention, compaction strategy, replica/repair health, and data-resurrection risks before altering operational settings.

## 13. Key Takeaways

A Cassandra read does not merely fetch the "latest" row: it must **locate the partition across memtable/SSTables, merge versions, and apply tombstones**, sometimes spanning many files, chunks, and replicas. Therefore:

- **Many SSTables** increase the number of sources to inspect and reconcile.
- **Many tombstones** inflate scanned entries even when returned row counts are tiny.
- **Oversized partitions or fragmented data** widen read ranges and weaken cache locality.
- **Compaction and repair** serve different roles; tombstones can only be reclaimed when safety conditions hold.
- **Query-driven modeling**—sensible partitions/buckets, bounded clustering ranges, and fitting TTLs—is the foundation for predictable read latency.

When troubleshooting, prioritize **measuring SSTables per read and tombstones scanned**, correlate them with write/TTL patterns, and adjust schemas or compaction based on observed data. That prevents a "return 20 rows" query from doing the work of scanning thousands of records.
