# Large Partitions, Wide Rows, and Impact on Reads and Writes

In Apache Cassandra, data is distributed by the **partition key**. Each complete partition key value identifies a **logical partition**, containing one or more rows distinguished by **clustering columns**. When a partition accumulates too many rows, too many values/cells, or oversized payloads, Cassandra can run into a **large partition**. In many documents, the term **wide row** is also used to refer to a data structure with a very large number of columns/cells in the same partition; this terminology originates from early Cassandra storage models.

A large partition can slow down queries, increase SSTable read volume, and burden compaction and repair. However, a **large partition** differs from a **hot partition**: even a small partition can become overloaded if accessed continuously. Query-driven wide-column table design must control **size, shape, data lifecycle, and traffic** at the same time.

This lesson in the **Keys and Partitions** topic explains the mechanics, symptoms, measurement, and remediation so that CQL queries and Java applications operate stably in distributed systems with replication, consistency levels, and background tasks like compaction and repair.

After this lesson, you will be able to:

- Distinguish large partitions, wide rows, large cells, and hot partitions.
- Explain the impact of large partitions on **reads**, **writes**, **compaction**, **streaming**, and **repair**.
- Understand why `LIMIT`, paging, increasing the replication factor, or `ALLOW FILTERING` do not solve a poor partition key at its root.
- Redesign partition keys with time buckets or controlled sharding while preserving the primary query path.
- Use operational observability metrics to identify anomalous partitions.
- Write CQL queries and Java Driver code that read the right partition, the right range, and with bounded results.

## 1. What are large partitions and wide rows?

A Cassandra table has a partition key and optionally clustering columns:

```sql
CREATE TABLE events_by_device (
    tenant_id    text,
    device_id    uuid,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    payload      text,
    PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

With this design, **each `(tenant_id, device_id)` pair is one partition**. All events of the device across all days reside in that same partition:

```text
Partition ('acme', device-A)
│
├── 2026-11-21T10:00Z, event-1001 → payload
├── 2026-11-21T09:59Z, event-1000 → payload
├── 2026-11-21T09:58Z, event-0999 → payload
│   ...
├── 2026-10-01T07:05Z, event-0200 → payload
│   ...
└── 2025-11-21T00:00Z, event-0001 → payload
    ↑ Row/cell count grows over time if lifecycle is unbounded
```

This is a partition that is **wide in clustering row count**. It can become a large partition when row/cell counts and bytes cause queries or operational tasks to consume resources beyond planned capacity.

### Distinguishing the terminology

| Term | Description | Example |
| --- | --- | --- |
| **Large partition** | A partition with excessive data/cells and a large footprint; what counts as "large" depends on workload and Cassandra version. | One device accumulating years of events under one partition key. |
| **Wide row** | Historical term for a structure with very many columns/cells under one key; in the CQL model, usually corresponds to many clustering rows in one partition. | One `device_id` having millions of `(occurred_at, event_id)` pairs. |
| **Large cell/value** | A single value containing many bytes, e.g., a very long `blob`/`text`. | One record storing a 10 MiB image. |
| **Hot partition** | One key receiving excessive read/write requests at a given time, even if byte size is small. | One active session being updated continuously by thousands of clients. |
| **Tombstone-heavy partition** | Contains many delete markers or TTL-expired values, making reads harder than live row count suggests. | Many events bulk-deleted or expiring en masse via TTL. |

Cassandra does **not** create new CQL column names whenever a new clustering row arrives. Thus, "wide row" does not mean declaring many columns in `CREATE TABLE`. You must look at actual clustering row counts, collection structures, cells, and bytes.

> **Principle:** the total size of a **table** does not indicate whether the table has large partitions. A 20 TB table divided into many moderate partitions can be easier to operate than a smaller table containing a few massive partitions.

## 2. Why does the partition key concentrate data and load?

Cassandra uses a partitioner (commonly `Murmur3Partitioner`) to compute a **token from the entire partition key**, then uses the replication strategy to choose nodes holding replicas.

```text
Pair (tenant_id, device_id)
          |
          v
    Hashed to token
          |
          v
    Responsible replica set
       /     |      \
    Node A  Node B  Node C  (illustrating RF = 3)
          |
          v
   Clustering rows of the partition
```

Rows with the same partition key are not split by clustering key across random replica sets. Therefore:

1. Each responsible replica must be able to hold and serve the partition's data.
2. If a partition key becomes extremely hot, its replica set experiences concentrated load as well.
3. Increasing `replication factor` adds more copies; it **does not split a single partition key into multiple independent partitions**.
4. Clustering order and range queries can make reading **a slice** inside a partition efficient, but they do not stop the partition from growing.

**Do not equate "same partition" with "one contiguous block on disk."** Cassandra uses an LSM tree: writes go to commit log/memtable and flush to SSTables; a partition can span multiple SSTables. On read, replicas merge valid versions and data in clustering order. That is why write history, compaction, and tombstones affect read cost.

## 3. How do large partitions form?

### Unbounded event accumulation under one key

For example, `PRIMARY KEY (device_id, occurred_at, event_id)` enables fetching a device timeline, yet all history for that device funnels into the same partition key. Without time buckets, live rows and data can grow forever.

### A key with very low cardinality

```sql
-- Example prone to huge partitions when the whole system only has a few statuses:
PRIMARY KEY (status, updated_at, customer_id)
```

Here only `status` is the partition key. A common status like `ACTIVE` can contain millions of customers. Using `status` as the partition-selecting key is only sensible if data volume and load per value are proven acceptable.

### Storing overly large payloads in each row

```sql
CREATE TABLE files_by_account (
    account_id uuid,
    uploaded_at timestamp,
    file_id uuid,
    file_content blob,
    PRIMARY KEY (account_id, uploaded_at, file_id)
);
```

Even a few thousand rows where each `file_content` is several megabytes creates a huge footprint. For large binary content, consider storing it in object storage and keeping **identifiers, paths, checksums, and metadata** in Cassandra.

### Many collection cells or frequent updates/deletes

Non-`frozen` `map`/`set`/`list` columns can hold many elements managed at the cell level; collections with unbounded growth easily bloat a row/partition. Continuous updates and deletes can generate many tombstones before they become eligible for cleanup.

### Skewed data distribution

Some tenants or devices generate thousands of times more events than average. A daily bucket may fit normal devices while still becoming huge for a "super-hot" device. **Measuring only table-wide averages often hides the worst partitions.**

## 4. How do large partitions affect the read path?

An efficient Cassandra query usually has two steps: select the **exact partition key**, then read the required **slice of clustering keys**.

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

Thanks to `occurred_at DESC`, this query can fetch the 20 latest rows in clustering order without reading the entire history. Thus, **a large partition does not imply every query must scan the entire partition**.

Still, the following scenarios can remain costly:

- **Wide range scans:** querying the full history or a slice containing millions of rows forces replicas to read/decode large volumes, transfer lots of data over the network, and slow down application processing.
- **Many SSTables containing the same partition:** the read path may have to check and merge versions and tombstones from multiple sources; compaction strategy affects cost.
- **Dense tombstones:** a query returns few live rows yet has to wade through many tombstones/deletes/TTL expirations to find valid rows.
- **Large cells or payloads:** reading few rows where each row transfers many bytes puts pressure on memory, I/O, network, and serialization.
- **Concurrent reads:** many clients querying the same partition simultaneously can cause queueing on the replica set, even when every request specifies `LIMIT`.

Comparison:

| Query | Logical scope of work | Risk |
| --- | --- | --- |
| Full partition key, `LIMIT 20` reading newest clustering order | Focused on the head of the range, able to stop early | Usually reasonable, though tombstones and SSTables still matter. |
| Full partition key and a 5-minute range | Reads a matching clustering slice | Reasonable if 5 minutes has moderate row and cell counts. |
| Full partition key without date/row limits | Can read a massive amount of data | Latency, memory, and network usage rise. |
| Incomplete partition key with `ALLOW FILTERING` | May need to filter across many partitions | Unpredictable cost, easy overload. |
| `SELECT COUNT(*)` on a huge partition | Must process all relevant rows/cells to count | Should not be used for routine monitoring under high load. |

### Why do `LIMIT` and paging only solve part of the problem?

`LIMIT 100` bounds the number of **returned rows**, not guaranteeing only 100 cells are read from SSTables. With tombstones, Cassandra may have to scan far more entries than the rows returned.

**Driver paging** splits the result stream into pages to reduce response payload size and keep application memory under control. It does not split stored data into smaller partitions. If the application iterates through millions of results across many pages, total read cost remains high.

## 5. How do large partitions affect writes?

Cassandra is optimized for sequential writes via commit log and memtable, so **a write to an already-large partition does not automatically scan that entire partition**. Distinguish two important cases:

- **A small mutation** writing a few cells into a large partition: can still be fast because the initial write path does not need to read existing rows.
- **A very large mutation/batch** or intense write stream targeting the same partition: can strain mutation size limits, memory, compaction, and the replica set serving that key.

Common consequences:

1. **Hotspot on replicas:** all writes for a partition key go to the responsible replica set; many clients hammering the same key cause CPU, I/O, queueing, and latency spikes.
2. **Flush and compaction:** consecutively written versions/cells spread across multiple memtables/SSTables; the system must merge or manage them later.
3. **Write amplification and tombstones:** repeated updates/deletes create extra versions/tombstones, increasing background storage work.
4. **Large mutations:** updating a huge collection or batching too many operations can trip version-dependent warning/rejection thresholds and trigger GC/memory pressure.
5. **Retries and identity:** using `now()` or a new UUID on every retry can generate extra clustering rows, making the partition grow faster than actual business events.

### Can `BATCH` fix this?

No. Using `BEGIN BATCH` to stuff thousands of operations into one request **does not split a partition** and can produce oversized mutations/batches. Cassandra batches serve semantic purposes for related operations, not general throughput scaling.

For writing many independent events, prefer **prepared statements and asynchronous writes with bounded concurrency**, proper partition key/bucket design, and latency monitoring rather than cramming massive data into one batch.

## 6. Impact on compaction, repair, and streaming

A Cassandra table keeps operating as data is flushed, compacted, replicated, and repaired for inconsistencies across replicas. Very large partitions make these operations harder to control:

| Operation | Impact when partitions are large |
| --- | --- |
| **Compaction** | May need to process large amounts of data/versions/tombstones; increases I/O, CPU, duration, and temporary disk space depending on compaction strategy. |
| **Repair** | Synchronizing replicas must inspect large data volumes; repair can consume heavy bandwidth, I/O, and time, especially if one replica missed substantial data. |
| **Streaming / bootstrap / decommission** | Moving token-range data can drag huge partitions along, impacting transfer speed and load balance. |
| **Read repair / consistent reads** | Reading from multiple replicas for comparison/reconciliation can cost more when accessing large data slices or divergent replicas. |
| **Backup and restore** | Size, SSTable counts, and data movement affect backup/restore duration; very large data requires careful capacity planning. |

Details depend on **Cassandra version, topology, compaction strategy, replication strategy, and workload pattern**. A large partition does not always cause every repair to fail, yet it raises tail latency risk and operational cost.

**Do not misunderstand:** running compaction or repair **does not change the partition key**. They can optimize SSTables/tombstones or synchronize replicas, but they do not break an overly wide partition into smaller partitions.

## 7. Quantitative example: why can one device create a "wide row"?

Suppose a device generates **500 events/second** during peak hours, each event containing **800 bytes of logical payload**, excluding keys, metadata, compression, and tombstones.

```text
1 minute:
  500 × 60 = 30,000 rows
  30,000 × 800 B = 24,000,000 B ≈ 22.9 MiB payload

1 hour:
  500 × 3,600 = 1,800,000 rows
  1,800,000 × 800 B = 1,440,000,000 B ≈ 1.34 GiB payload

24 continuous hours at this rate:
  43,200,000 rows
  34,560,000,000 B ≈ 32.2 GiB payload
```

If the partition key is only `(tenant_id, device_id)`, **one partition** for that device can accumulate over 32 GiB of payload in a single day under this extreme assumption. Each responsible replica must store the corresponding data.

If `replication factor = 3`, there are three logical copies across the cluster per the replication strategy; **do not equate 32.2 × 3 GiB with exact disk bytes**, since real footprint is also affected by compression, SSTables, compaction, overhead, and deleted data.

### Choosing buckets by load

| Bucket for one device | Rows/bucket | Hypothetical payload/bucket |
| --- | ---: | ---: |
| 1 day | 43,200,000 | ≈ 32.2 GiB |
| 1 hour | 1,800,000 | ≈ 1.34 GiB |
| 5 minutes | 150,000 | ≈ 114.4 MiB |
| 1 minute | 30,000 | ≈ 22.9 MiB |

There is no universal "optimal quota" for all clusters. This table only demonstrates: **for this device**, daily or hourly buckets can be too wide, whereas minute buckets shrink each partition at the cost of increasing the number of partitions queried for long histories.

Beyond **averages**, account for **peak rates** and outlier devices. Even with minute buckets, a device receiving 500 events/second can still create a **hot partition** during the active write minute. In that case, consider sharding/balancing or an appropriate ingestion architecture.

## 8. Redesigning the table with time buckets

Suppose the primary read requirements are: **"Fetch the 100 latest events of a device in one minute"** or **"Fetch events of a device from 08:10:00 to before 08:10:30 UTC."**

A suitable design could be:

```sql
CREATE TABLE events_by_device_minute (
    tenant_id     text,
    device_id     uuid,
    minute_bucket timestamp,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, device_id, minute_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Here:

- Composite partition key: `(tenant_id, device_id, minute_bucket)`. Each device in each UTC minute is one logical partition.
- Clustering columns: `occurred_at`, `event_id`, supporting chronological ordering and multiple events sharing a timestamp.
- `minute_bucket` must be computed using the **exact same rule** in producer and consumer, e.g., start of the UTC minute (seconds and nanoseconds = 0).
- `event_id` should remain stable across retries to avoid creating duplicate events on retransmission.

### Writing an event

```sql
INSERT INTO events_by_device_minute (
    tenant_id, device_id, minute_bucket,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:10:00Z',
    '2026-11-21T08:10:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature',
    'sensor=42.1'
);
```

### Reading a range inside one partition

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_minute
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND minute_bucket = '2026-11-21T08:10:00Z'
  AND occurred_at >= '2026-11-21T08:10:00Z'
  AND occurred_at <  '2026-11-21T08:10:30Z'
LIMIT 100;
```

This is **one partition lookup and one clustering range**. The half-open interval `[start, end)` prevents boundary duplicates when stitching consecutive segments.

**Trade-off:** querying from 08:10 to 08:20 must read the relevant minute partitions and merge results; `CLUSTERING ORDER BY` only applies **within each partition**. Multi-day historical queries should not fire thousands of unbounded concurrent read requests; bound concurrency, paginate, or build a dedicated rollup model tailored to read needs.

### When time buckets aren't enough: controlled sharding

A minute partition can still run hot. When necessary, add a `shard_id` computed by a deterministic rule:

```sql
-- Example key to spread load across shards within each minute:
PRIMARY KEY (
    (tenant_id, device_id, minute_bucket, shard_id),
    occurred_at,
    event_id
)
```

Writers must pick the shard consistently for an event; readers must know or query **all relevant shards** and merge the data. Shard count must balance load against fan-out cost; adding shards arbitrarily can make reads substantially harder.

There is no guarantee "each shard lands on a separate node" because token placement can still map shards to the same node/replicas; the goal is to improve statistical distribution across multiple partition keys.

## 9. Safe reads and writes when migrating from an old table to a new table

For an existing table, changing the partition key generally requires **creating a new table and migrating data**, not just `ALTER TABLE`.

A controlled rollout process:

1. **Define target queries and buckets** using production metrics; choose the new partition key and clustering columns that uniquely identify rows.
2. **Create the new table** and deploy writers that compute buckets consistently and reuse stable event IDs on retries.
3. **Plan historical data:** backfill with throttled throughput; maintain checkpoints for retries without duplicating events.
4. **Ensure writes during the transition:** monitored dual-write or replay from the event source; do not assume two tables update atomically.
5. **Verify reads** across multiple keys/buckets and compare data, including time boundaries, TTL, and deletion state.
6. **Switch the read path** once data completeness and latency meet requirements; monitor metrics and handle exceptions.
7. **Stop writing to the old table and archive/decommission data per policy** after confirming no consumers still depend on it.

A classic bug is computing `minute_bucket` in local time during writes while reading in UTC. The two sides then query **different partition keys**, appearing to "lose data" even though records exist.

Do not tweak compaction strategy or raise consistency level hoping a large partition will split itself: the fundamental fix is **changing the key shape and storage lifecycle**.

## 10. TTL, tombstones, and compaction: controlling data lifecycle

If events only need 7-day retention, TTL can be applied at write time:

```sql
INSERT INTO events_by_device_minute (
    tenant_id, device_id, minute_bucket,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:10:00Z',
    '2026-11-21T08:10:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature',
    'sensor=42.1'
) USING TTL 604800;
```

`604800` seconds equals 7 days. Yet TTL **does not mean data vanishes immediately from every SSTable**. Expired data is treated as no longer live on reads, and purging tombstones from disk depends on safety conditions and compaction.

Several considerations:

- Choose **sensible buckets** to bound size at write time rather than relying solely on TTL.
- Avoid individually deleting millions of rows inside one partition when data can be organized around easier-to-expire lifecycles.
- Evaluate a fitting compaction strategy: for example, **TimeWindowCompactionStrategy (TWCS)** is often considered for time-series data with TTL and matching write windows; it does not change the partition key or eliminate all tombstone risks.
- Out-of-order historical writes, updates to old events, or uneven TTLs can undermine the optimization assumptions of time-series/compaction models.
- Repair and tombstone/`gc_grace_seconds` settings must align with operational policy to avoid resurrected deleted data when a replica missed a delete. Never shrink `gc_grace_seconds` arbitrarily just to silence disk space alerts.

**In practice:** many tombstones can force a `LIMIT 10` query to scan substantial data anyway. Combine time bucketing, TTL, update/delete discipline, and read monitoring.

## 11. Measuring and diagnosing large partitions in production

Useful tools and metrics depend on Cassandra version; field names may vary. For a hypothetical keyspace/table:

```bash
# Table summary statistics on one node:
nodetool tablestats app_ks.events_by_device_minute

# Histogram of partition size and cell count, plus latency stats:
nodetool tablehistograms app_ks events_by_device_minute
```

Monitor these metric groups:

| Metric group | Diagnostic meaning |
| --- | --- |
| **Partition size min/mean/max or histogram** | Identifies large tails and outliers; low mean does not rule out huge partitions. |
| **Cell count histogram** | Evaluates internal width; distinguish cell count from schema column count. |
| **Read/write latency and timeout rate** | Measures user impact; compare p95/p99 and peak load. |
| **SSTables per read / pending compactions** | Signals read amplification and background work falling behind write rate. |
| **Tombstones scanned / tombstone warnings** | Distinguishes few live results from heavy data traversal. |
| **Large partition warnings in logs** | Helps pinpoint tables or partition keys worth investigating, depending on version logging/config. |
| **Per-node CPU, I/O, GC, and network** | Identifies replicas suffering hotspots or resource exhaustion. |

Partition size numbers from tools may represent **SSTable/compaction statistics**, not an exact instantaneous measurement of every live logical partition. Cassandra has multiple replicas and multiple SSTables; compare across **the same time window, same version, and same measurement scope**.

### Step-by-step diagnosis

1. **Start from symptoms:** identify slow queries, p99, timeouts, overloaded nodes/replicas, and when they occur.
2. **Check keyspace/table:** inspect size/cell histograms, SSTables per read, tombstones, and compaction backlog.
3. **Examine access distribution:** do a few partition keys receive most requests? Are there byte/row outliers?
4. **Inspect queries:** are full partition keys provided, how wide are clustering ranges, and are `LIMIT`/paging used appropriately?
5. **Inspect data lifecycle:** TTL, bulk deletes, collection updates, backfills, and recent repairs.
6. **Load-test the new model:** under the same workload, does the new bucket/shard reduce size or hotspots without excessive query fan-out?

Avoid running `SELECT COUNT(*)` to count all rows of a massive partition under high load: Cassandra must process enormous data to count. Leverage metrics/histograms or write-path telemetry whenever possible.

### Is there an "universally safe" MB/row threshold?

**No single threshold fits all systems.** Warning thresholds, load capacity, and configuration limits differ across Cassandra versions and hardware. Establish **guardrails** based on actual distributions of row counts, cell counts, bytes/partition, latency SLOs, peak traffic, and compaction/repair budgets.

## 12. Bounded queries from the Java Driver

This Java Driver 4.x example uses `PreparedStatement` to read a slice within **one minute bucket**. `Instant` maps to CQL `timestamp` and is used consistently for UTC instants.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class DeviceEventRepository {
    private final CqlSession session;
    private final PreparedStatement readInMinute;

    public DeviceEventRepository(CqlSession session) {
        this.session = session;
        this.readInMinute = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM events_by_device_minute " +
            "WHERE tenant_id = ? AND device_id = ? AND minute_bucket = ? " +
            "AND occurred_at >= ? AND occurred_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet findRangeInOneMinute(
            String tenantId, UUID deviceId,
            Instant startInclusive, Instant endExclusive) {

        Instant bucket = startInclusive.truncatedTo(ChronoUnit.MINUTES);
        Instant bucketEnd = bucket.plus(1, ChronoUnit.MINUTES);

        if (!startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Read range must lie within one UTC minute bucket");
        }

        BoundStatement statement = readInMinute.bind(
            tenantId, deviceId, bucket, startInclusive, endExclusive
        ).setPageSize(50);

        return session.execute(statement);
    }
}
```

In this snippet:

- `startInclusive` and `endExclusive` form the **`[start, end)`** interval.
- The method validates inputs so it does not accidentally query only one bucket when the read range crosses into the next minute.
- Every partition key component appears in `WHERE`.
- `LIMIT 100` bounds the **total number of rows returned**, whereas `setPageSize(50)` specifies the desired driver page size.
- `ResultSet` can automatically fetch subsequent pages during iteration; the application should stop at the required row count and avoid calling `all()` on unbounded queries.
- If reading multiple minutes is needed, the service layer must split the range, bound concurrent queries, and merge results.

For high-throughput write streams, generate stable event IDs so retries do not spawn extra rows. For backfill jobs or updates spanning many partition keys, control concurrency and handle recovery when only part of the operations succeed.

## 13. Misconceptions to avoid

| Claim | Problem | Proper understanding / solution |
| --- | --- | --- |
| "A table with many schema columns is definitely a wide row." | Schema column count does not measure millions of clustering rows and payloads. | Measure row/cell/byte counts per **partition key**. |
| "With `LIMIT 10`, a 5 GiB partition is harmless." | Small output does not guarantee all queries/ranges, tombstones, compaction, or repair stay cheap. | Bound partition size and lifecycle; measure in practice. |
| "A large partition means every `INSERT` must scan 5 GiB." | Initial writes normally go to commit log/memtable without scanning the partition. | Distinguish initial write path from hotspots and background costs. |
| "Increasing replication factor splits a partition into smaller pieces." | Replicas are copies of the same logical data. | To split data, change the partition key/bucket/shard. |
| "Adding `ALLOW FILTERING` keeps mismatched queries fast." | Broad filtering can be very expensive and unpredictable. | Design tables around queries. |
| "Changing compaction strategy eliminates large partitions." | Compaction optimizes files, not partition key logic. | Measure and split data at the key model level. |
| "With a 7-day TTL, data is completely wiped from disk on day 7." | TTL causes logical expiration; physical cleanup depends on tombstones/compaction. | Combine buckets, TTL, and compaction strategy. |
| "Minute buckets are always better than daily buckets." | Small buckets create many partitions and heavy fan-out queries. | Choose based on write rate, read pattern, and SLOs. |
| "Hot partitions and large partitions are the same defect." | One is caused by bytes/cells, the other by access load. | Inspect both size histograms and traffic/latency. |

## 14. Scenario exercise

An IoT platform has the table:

```sql
CREATE TABLE device_messages (
    device_id uuid,
    created_at timestamp,
    message_id uuid,
    payload text,
    PRIMARY KEY (device_id, created_at, message_id)
);
```

Standard devices send **2 messages/second**, whereas peak industrial devices send **300 messages/second** with an average payload of **1 KiB/message**. Read requirements include:

- Dashboard page: **50 latest messages** of a device.
- Incident investigation: messages within a selected **15-minute** window.
- Reporting: message count per **day**.

Answer these questions:

1. How many rows does an industrial device generate in 15 minutes if every event has a distinct primary key?
2. Roughly how many MiB is the logical payload over 15 minutes?
3. With only `device_id` as the partition key, does one device's data accumulate over time or automatically split by day?
4. Can a 15-minute bucket serve an investigation of any arbitrary 15-minute interval with exactly one partition lookup?
5. If the 50 latest messages straddle the boundary between two buckets, what must the application do?
6. Does raising `replication factor` from 3 to 5 make each partition smaller?
7. If a query returns 10 rows yet remains slow, what should you inspect beyond the returned row count?
8. To compute daily reports over huge datasets, should you run `COUNT(*)` over all daily rows in the event table every time the dashboard refreshes?

**Suggested answers:**

1. `300 × 60 × 15 = 270,000` rows.
2. `270,000 KiB / 1,024 ≈ 263.7 MiB` payload, excluding overhead, replicas, and compression.
3. Data **accumulates in the same partition** of `device_id`; clustering columns do not automatically split partitions.
4. **Not guaranteed**. An arbitrary 15-minute window can fall across a boundary and span **two** 15-minute buckets.
5. Read all relevant buckets, merge by clustering timestamp and ID, and take the 50 latest messages in combined order.
6. **No**. Increasing RF only increases replica count; partition key and per-replica logical footprint remain unchanged.
7. Inspect tombstones, SSTables read per query, read latency, large payloads/cells, hot replicas, compaction backlog, and clustering conditions.
8. Generally **no**. Consider a summary/aggregation table updated in a controlled manner matching accuracy and latency needs.

This scenario shows the need to balance **rows per bucket**, **payload size**, **read/write rates**, and **fan-out cost**. Validate the final choice against realistic workloads.

## 15. Principles to take into operations

- **Large partitions** are a size and data-structure issue under one partition key; **wide rows** typically describe width from many clustering rows/cells.
- **Hot partitions** are a load-concentration issue. A partition can be large, hot, both, or neither.
- Reading a narrow clustering slice in a large partition can sometimes stay efficient, but **LIMIT/paging do not solve** wide-scan, tombstone, compaction, repair, or storage costs.
- Small writes to a large partition do not inherently scan the whole partition; bottlenecks arise from concentrated throughput, large mutations, and background work.
- Long-term size control requires **changing the partition key model**, usually via time buckets, sometimes adding shards and matching read rules.
- Monitor **the tail of partition size/cell count distributions**, timeouts, p99 latency, tombstones, SSTables/compaction, and replica load.
- Choose TTL, compaction strategy, replication, and consistency according to system needs, but **never treat them as substitutes for proper key design**.

When you understand how large partitions affect reads, writes, and Cassandra operations, you can design more sustainable query-driven wide-column tables, keep CQL latency predictable, plan data partitioning, and build Java applications with clear resource bounds.
