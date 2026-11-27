# Partition Size by Row Count, Columns, and Storage Volume

In Apache Cassandra, the **partition key** identifies the group of data stored on the same replica set. A *partition* can hold one row, thousands of rows, or many millions of rows. What matters is not only **how many rows**, but also **how much data and how many cells each row contains**, whether values are updated/deleted frequently, and whether read/write load concentrates on the same partition key.

For a distributed wide-column database, partition key design is directly part of managing size, performance, and operability. A table totaling terabytes can still run well if data and load are distributed properly; conversely, even a single oversized or overly hot partition can cause slow reads, higher compaction cost, and bottlenecks on replicas.

This lesson in the **Keys and Partitions** group explains how to evaluate a partition across **three dimensions: row count, column/cell count, and byte volume**, then applies them to CQL, time bucketing, replication, operational monitoring, and querying from Java.

After this lesson, you will be able to:

- Distinguish **logical row count**, **value/cell count**, and **storage bytes** of a Cassandra partition.
- Estimate partition scale from write rate, column count, data size, and retention period.
- Understand why **large partitions** and **hot partitions** are related yet distinct problems.
- Design partition keys by entity and time bucket; compute how many partitions must be read when querying multiple buckets.
- Inspect operational metrics for partition size and cell count without scanning the entire table.
- Write CQL queries and Java Driver code for bounded reads using the proper partition key.

## 1. What does a partition contain?

Consider a table recording IoT device metrics:

```sql
CREATE TABLE readings_by_device (
    device_id    uuid,
    recorded_at  timestamp,
    reading_id   uuid,
    temperature  double,
    humidity     double,
    status       text,
    PRIMARY KEY (device_id, recorded_at, reading_id)
) WITH CLUSTERING ORDER BY (recorded_at DESC, reading_id ASC);
```

In this table:

- `device_id` is the **partition key**.
- `recorded_at` and `reading_id` are **clustering columns**.
- `temperature`, `humidity`, and `status` are **regular columns**.

Each device has one logical partition holding all measurements for that device over the table's lifetime:

```text
Partition key = device-01
│
├── Row (2026-11-21 09:00, id-003) : temperature, humidity, status
├── Row (2026-11-21 08:59, id-002) : temperature, humidity, status
├── Row (2026-11-21 08:58, id-001) : temperature, humidity, status
└── ... many days, many months, many years ...
```

All rows with the same `device_id` belong to the same logical partition. Cassandra computes a token from the partition key, and the replication strategy determines which nodes are responsible for storing copies.

This **does not mean** the partition's data occupies one contiguous segment in a single SSTable: Cassandra uses memtables and multiple SSTables; data for the same partition can exist across multiple files, merged logically on read and reorganized via compaction.

### One partition, multiple size dimensions

| Dimension | Question | Example |
| --- | --- | --- |
| **Row count** | How many distinct clustering keys exist in the partition? | 120,000 events for one device in one day. |
| **Cell/value count** | How many column values are stored, updated, or deleted? | Each event has 5 data columns, or a collection with many elements. |
| **Byte volume** | How much total data and overhead is occupied? | Large binary payloads, clustering keys, metadata, indexes, and compression. |
| **Access frequency** | How many reads/writes per second does the partition receive? | A high-traffic device emitting events continuously. |
| **Update/delete history** | Are there many versions, TTL-expired cells, or tombstones? | A partition with few live rows yet having to scan many tombstones. |

No single number fully represents a partition's "largeness" and operational cost.

## 2. Row count: width along the clustering key

For a fixed partition key, **each clustering key combination** identifies one logical row. As the number of clustering combinations grows, the row count in the partition grows accordingly.

In the `readings_by_device` example:

```text
(device-01, 08:00, id-A)  -> row 1
(device-01, 08:00, id-B)  -> row 2
(device-01, 08:01, id-A)  -> row 3
(device-01, 08:00, id-A)  -> still row 1 (rewriting the same primary key)
```

Because the full primary key identifies one row, calling `INSERT` repeatedly with **the exact same key** does not add extra rows. Conversely, if each submission uses a new `now()`/UUID as a clustering key component, row count increases even when the business event was merely retried.

### Estimating from event rate

Suppose **one device** generates on average 20 records/second uniformly throughout the day:

```text
Rows/minute   = 20 × 60       = 1,200
Rows/hour     = 20 × 3,600    = 72,000
Rows/day      = 20 × 86,400   = 1,728,000
Rows/30 days  = 1,728,000 × 30 = 51,840,000
```

If the key is only `device_id`, after 30 days the partition can hold **over 51 million rows**. If `(device_id, event_day)` is used as the partition key, each daily partition has around **1.7 million rows**. With an hourly bucket, each hourly partition has around **72,000 rows**.

Actual row counts must be adjusted for write success rate, duplicate-key writes, traffic bursts, TTL, and retention policies. Average row count also does not reveal the **largest partition** or the highest-traffic partition.

### "Few rows" does not guarantee "lightweight"

A partition with only 20 rows can still consume significant space if each row stores multi-megabyte `blob` values. Conversely, 100,000 tiny rows may take fewer bytes yet still carry clustering overhead and traversal/indexing cost.

Therefore, **do not choose buckets based solely on a row-count limit**.

## 3. How should "column count" in wide-column be understood?

The term *wide-column* can create the misconception that a CQL table automatically spawns tens of thousands of **schema column names** per partition. In reality, columns declared in `CREATE TABLE` form a **schema structure**; per-partition width normally comes from **many clustering rows and many cells/data values**, not from generating unlimited new CQL column names.

Consider:

```sql
CREATE TABLE log_entries_by_service (
    service_id  uuid,
    log_time    timestamp,
    log_id      uuid,
    level       text,
    message     text,
    attributes  map<text, text>,
    PRIMARY KEY (service_id, log_time, log_id)
);
```

The table only declares a fixed set of CQL columns. However, a partition for `service_id` can hold hundreds of thousands of rows, each storing multiple values. In particular, `attributes` is a **non-frozen map**, whose elements can be represented as multiple internal cells; updating/deleting elements also affects cell counts and tombstones.

### Value count does not equal schema column count

A rough estimate:

```text
Approximate value/cell count
  ≈ row count × average regular column values stored per row
    + shared static values of the partition
    + collection representation overhead and internal metadata
```

This is only a model to **estimate business data volume**, **not an exact physical cell-counting formula** for SSTables. `null` values, row markers, collection structures, clustering keys, tombstones, and the Cassandra version all influence the actual representation.

| Case | Effect |
| --- | --- |
| Many rows, few regular columns | Key/row and index overhead still grow with row count. |
| Few rows, many large columns | Storage and network load can be large despite low row count. |
| Non-`frozen` `map`, `set`, `list` | Element/cell count and update/delete cost can increase. |
| `blob`/`text` containing long payloads | Bytes surge while column count barely changes. |
| `STATIC` column | Shared value at partition level; does not create a separate copy per clustering row. |
| Frequent updates/deletes on the same column | Can produce tombstones/versions stored across SSTables prior to compaction. |

**Key takeaway:** "the table has 8 columns" is not enough to conclude partitions are small; you must know **row count, collection element counts, individual value sizes, and write/delete history**.

## 4. Estimating partition byte size

You can start with an estimation at the logical data level:

\[
B_{\text{partition}} \approx N_{\text{rows}}
  \times B_{\text{avg row}}
  + B_{\text{static}}
  + B_{\text{metadata/index}}
\]

Where:

- `N_rows`: number of logical rows in a partition for the time window of interest.
- `B_avg row`: average bytes of regular column data along with clustering key/overhead per row.
- `B_static`: shared partition-level data (if static columns exist).
- `B_metadata/index`: storage/indexing overhead; depends on format and write pattern.

For initial capacity planning before real data samples exist, you can use:

```text
Expected row count
    = average write rate (rows/sec)
      × seconds per bucket
      × fraction of rows with distinct primary keys

Logical payload size
    ≈ expected row count × average bytes per row

Storage to provision
    = logical payload + overhead + compaction/TTL/tombstone effects
      ± compression delta (excluding replication factor)
```

### Example: same row count, different volume

Suppose a device produces **72,000 events/hour**. With hypothetical average payload sizes:

| Average data per event | Total payload/hour | Assessment |
| --- | ---: | --- |
| 120 bytes | 8.64 MB (around 8.24 MiB) | Very different from large events despite identical row count. |
| 600 bytes | 43.2 MB (around 41.2 MiB) | Still need to account for key/metadata overhead and actual write volume. |
| 2 KiB | 140.6 MiB | An hourly bucket can be sizable; measure in practice. |
| 16 KiB | Around 1.10 GiB | Large payloads make hourly buckets hard to manage if stored completely inline. |

These figures **only count hypothetical payload**, not SSTable bytes on disk. Compression can reduce size, while metadata, repeated key representations, indexes, tombstones, and multiple SSTables can significantly alter the physical footprint.

Unit conversions:

- **1 KiB = 1,024 bytes**.
- **1 MiB = 1,024 KiB**.
- **1 GiB = 1,024 MiB**.
- **1 MB = 1,000,000 bytes**; do not mix MB and MiB when building sizing tables.

### Where is "partition size" measured?

At least three perspectives should be kept distinct:

1. **Current logical data**: live rows and cells visible to queries.
2. **Disk footprint on a single replica**: affected by compression, SSTables, tombstones, and compaction.
3. **Cluster-wide footprint**: includes replicas and operational overhead; cannot be derived accurately by a naive multiplication.

For instance, if a partition's logical payload is 40 MiB and the keyspace has `replication factor = 3`, you can use **roughly 120 MiB of logical data across three replicas** as an initial mental baseline, though actual disk usage will not equal exactly 120 MiB due to compression, data layout, uncompacted SSTables, repair, and other storage mechanics.

## 5. It's not just volume: large partitions and hot partitions

Two issues requiring separate diagnosis:

| Characteristic | **Large partition** | **Hot partition** |
| --- | --- | --- |
| Nature | One partition key holds too much data/rows/cells. | One partition key receives too high a share of read or write load. |
| Typical symptoms | Slow wide-slice reads, many SSTables/cells, expensive compaction and streaming. | Specific replicas become overloaded, latency spikes even when the partition is not large. |
| Causes | Missing buckets, unbounded history retention, large payloads. | Skewed key distribution, an extremely "hot" tenant/device. |
| Remediation | Bucket by time/size, sensible TTL, split large datasets. | Controlled key/load dispersion, rate limiting, sharding aligned with read patterns. |

A 1 MiB partition can be scorching hot if it receives tens of thousands of requests/second. A multi-hundred-MiB partition might be accessed infrequently yet cause high cost during repair/streaming/compaction or long range scans.

### Why do large partitions cause problems?

- **Read amplification:** multiple SSTables, tombstones, and wide clustering ranges can force replicas to read/merge large amounts of data.
- **Unstable latency:** reading a very wide range or a partition with huge cell counts increases CPU, I/O, memory pressure, and processing time.
- **Compaction/streaming/repair:** large partitions increase the amount of data moved or processed during background operations.
- **Load concentration:** all rows in a partition belong to the same replica set; adding rows to the same partition key does not spread them across random nodes.
- **Operational difficulty:** deleting or scanning an entire large partition can create substantial future tombstone and compaction work.

There is **no single row-count or MB threshold** suitable for every cluster and Cassandra version. Systems typically set guardrails/alerts based on actual configuration and scale; decisions must rely on measured metrics, workload characteristics, latency targets, and load testing.

## 6. Time bucketing to bound partition size

For continuously generated data, a common technique is adding a **time bucket** to the partition key.

### A design prone to unbounded growth

```sql
CREATE TABLE metrics_by_device_all_time (
    tenant_id  text,
    device_id  uuid,
    measured_at timestamp,
    event_id   uuid,
    payload    text,
    PRIMARY KEY ((tenant_id, device_id), measured_at, event_id)
);
```

The partition key `(tenant_id, device_id)` never changes over time. If a device writes continuously, its partition grows endlessly.

### A design with an hourly bucket

```sql
CREATE TABLE metrics_by_device_hour (
    tenant_id   text,
    device_id   uuid,
    hour_bucket timestamp,
    measured_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        measured_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (measured_at DESC, event_id ASC);
```

Convention: `hour_bucket` is the **start of the hour in UTC**, e.g., `2026-11-21T08:00:00Z` for all events from 08:00 to before 09:00 UTC.

```text
(tenant='acme', device=D1, hour=08:00Z)
    08:00:01, event A
    08:00:02, event B
    ...
    08:59:59, event N

(tenant='acme', device=D1, hour=09:00Z)
    09:00:00, event P
    ...
```

Even for the same device, two different hours are two **different partition keys**. Within the same hour, all events share the same partition key and are ordered by `measured_at`/`event_id`.

### Reading a range within one bucket

```sql
SELECT measured_at, event_id, payload
FROM metrics_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND measured_at >= '2026-11-21T08:15:00Z'
  AND measured_at <  '2026-11-21T08:30:00Z'
LIMIT 200;
```

Cassandra can pinpoint **one specific partition** and read the matching slice of clustering keys. `LIMIT 200` caps the returned row count; it does **not** guarantee Cassandra reads only 200 cells from disk if tombstones or multiple SSTables are present.

### How granular should buckets be?

Suppose average load is **20 events/sec/device**, with each event averaging **600 bytes payload**:

| Bucket duration | Rows/bucket | Estimated payload/bucket |
| --- | ---: | ---: |
| 1 day | 1,728,000 | 1,036.8 MB (around 989 MiB) |
| 1 hour | 72,000 | 43.2 MB (around 41.2 MiB) |
| 10 minutes | 12,000 | 7.2 MB (around 6.9 MiB) |
| 1 minute | 1,200 | 0.72 MB (around 0.69 MiB) |

These bucket sizes are **not fixed recommendations**. Choosing too long a bucket causes large partitions; choosing too short a bucket creates many partition keys, increases overhead, and forces historical queries to read many partitions. Examine **actual distribution, peak load, typical query ranges, and acceptable latency**.

### Querying across multiple buckets

If a user requests history from **08:45 to 09:15 UTC**, the application usually must:

1. Read the `08:00Z` bucket with range `[08:45, 09:00)`.
2. Read the `09:00Z` bucket with range `[09:00, 09:15)`.
3. Merge results and sort by `measured_at` in the application when a single global order is needed.

`CLUSTERING ORDER BY` only provides ordering within **a single partition**, not across two buckets. For monthly historical queries over minute buckets, the number of partitions read can become huge; in such cases consider rollup tables or a different access path.

## 7. Do not use buckets to mask an unbalanced partition key

Adding date/hour does not always solve every problem. Several key patterns still easily create skewed load:

```sql
-- All devices of a tenant go into one daily partition:
PRIMARY KEY ((tenant_id, event_day), device_id, measured_at)

-- All customers in the same status funnel into very few partitions:
PRIMARY KEY (status, customer_id)

-- One partition per event, losing the ability to read a device's time range:
PRIMARY KEY ((tenant_id, device_id, measured_at), event_id)
```

The first option can work **if you genuinely need to read all devices of a tenant for a day and data is small enough**, though a large tenant can still create a giant partition. The second option has low partition key cardinality; the third creates huge numbers of tiny partitions and complicates per-device historical queries.

If a single device remains too hot even within a short bucket, consider **controlled sharding**, such as adding `shard_id` to the partition key with consistent read/write rules. However, **every historical query must know or scan the relevant shards**, trading one single-partition query for multiple smaller queries.

Never pick an arbitrary shard count without designing reads, retries, and routing key calculation.

## 8. TTL, tombstones, and deleted data complicate measurement

Suppose the system only needs to retain readings for **7 days**. TTL can be set for new data:

```sql
INSERT INTO metrics_by_device_hour (
    tenant_id, device_id, hour_bucket, measured_at, event_id, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:15:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature=37.9'
) USING TTL 604800;
```

TTL `604800` equals **7 days in seconds**. Upon expiration, data is no longer treated as live values for normal queries; however, tombstones and related storage components can remain on disk until eligible for cleanup during compaction.

Things to keep separate:

- **Live row count:** rows still readable by the application.
- **Tombstone count:** delete or expiration markers; can make queries expensive even when returning very few rows.
- **Current SSTable size:** can reflect old/uncompacted data, not a naive product of live rows × bytes per row.
- **Per-cell TTL:** if some columns live longer than others, rows and partitions can still retain data even after many values expire.

TTL **does not replace** choosing a good partition key. If a partition receives massive data every hour, it can still run hot and incur heavy processing cost before TTL takes effect.

Bulk deletes or repeatedly overwriting multiple columns within a partition can also accumulate tombstones. When diagnosing performance issues, inspect both **partition size and update/delete history**.

## 9. Monitoring partition size in practice

Cassandra exposes metrics at multiple levels: table, SSTable, and query. Command/field names can vary across versions, so cross-check against the version you operate.

### Table-level statistics and distributions

Examples of commonly used administrative commands:

```bash
# Table info, including compacted partition size statistics:
nodetool tablestats my_keyspace.metrics_by_device_hour

# Histogram of partition size / cell count and selected latencies:
nodetool tablehistograms my_keyspace metrics_by_device_hour
```

When reviewing output, focus on:

- **Compacted partition minimum/mean/maximum bytes** (when provided by your version): helps spot size dispersion and outliers, though these are statistics/estimates, not exact instantaneous byte counts of every live partition.
- **Partition size histogram**: identifies the distribution tail; if most partitions are small while a few are huge, averages can hide risks.
- **Cell count histogram**: shows the distribution of represented cells/values in partitions as reported by that version's statistics tool.
- **Read/write latency, SSTables per read, tombstones scanned, large partition warnings**: link size metrics directly to query and I/O impact.

Do not conclude from a `tablestats` summary that **every partition** equals the mean size. Statistics may be gathered along compaction/SSTable schedules and vary by version, compression, and storage state.

### Root-cause analysis at the partition key level

Once you know a specific partition key shows anomalies, investigate that key with **explicitly bounded** queries and observe response times. For example:

```sql
SELECT measured_at, event_id, payload
FROM metrics_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
LIMIT 20;
```

Receiving 20 rows **does not mean** the partition only has 20 rows. This validates the access path, not total partition size.

Also do not treat `SELECT COUNT(*)` over a huge partition or whole table as a free measurement: Cassandra must process the relevant rows/cells to count them, which can impose heavy load. For production data, prefer histograms, metrics, logs/alerts, and controlled sampling.

### Checking metrics across multiple replicas

Because Cassandra uses replication, different nodes can have different SSTable/compaction states. When diagnosing hotspots or huge partitions, compare metrics across **nodes holding the relevant replicas**, and check consistency, compaction, and repair if unusual discrepancies appear.

Do not sum the storage reported by each node and call that "the logical size of one partition": that can double-count replicas, uncompacted files, and various overheads.

## 10. Bounded reads from a Java application

Suppose a Java application needs to display at most 200 readings of a device in an hourly bucket. Java Driver 4.x allows using **prepared statements** and **page size** instead of loading unbounded data into application memory.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class MetricsRepository {
    private final CqlSession session;
    private final PreparedStatement findReadings;

    public MetricsRepository(CqlSession session) {
        this.session = session;
        this.findReadings = session.prepare(
            "SELECT measured_at, event_id, payload " +
            "FROM metrics_by_device_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 200"
        );
    }

    public ResultSet readInHour(
            String tenantId,
            UUID deviceId,
            Instant sampleTimestamp,
            Instant fromInclusive,
            Instant toExclusive) {

        // Instant is interpreted in UTC; bucket is start of the UTC hour.
        Instant hourBucket = sampleTimestamp.truncatedTo(ChronoUnit.HOURS);

        BoundStatement statement = findReadings.bind(
            tenantId, deviceId, hourBucket, fromInclusive, toExclusive
        ).setPageSize(100);

        return session.execute(statement);
    }
}
```

When using this method:

- `hourBucket` must match **the exact way producers compute buckets** during writes.
- `fromInclusive` and `toExclusive` should stay within the chosen hour/bucket. If spanning multiple hours, the application must split queries by bucket; otherwise data in other buckets will be missed.
- `LIMIT 200` bounds the maximum total rows returned; `setPageSize(100)` sets the desired number of rows per driver page. They serve different purposes.
- Avoid calling `all()` and holding huge results in RAM when the user only needs one page. Use paging state or process page-by-page for long queries.
- Limiting results and paging **do not make a partition smaller**; schema and bucketing strategy determine how much data is stored per key.

If the application serves a dashboard querying "all devices in a tenant over time," `metrics_by_device_hour` does not directly supply global order. A dedicated summary table or a different query pipeline may be required.

## 11. Partition design and monitoring workflow

When creating a new table, you can follow this sequence:

1. **Identify primary queries:** e.g., "read the 100 latest events of a device in an hour," "read 30 days of history," "aggregate daily average temperature."
2. **Select the entity forming the partition key:** tenant, user, device, account, etc., ensuring the application knows all key components when reading.
3. **Estimate row count:** average and peak write rates, bucket length, ratio of new rows vs. upserts.
4. **Estimate bytes:** sample payloads and size distribution, account for clustering/regular columns, collections, and metadata; distinguish logical payload from SSTable bytes.
5. **Assess load/read frequency:** avoid key combinations receiving excessive requests even if volume is not yet high.
6. **Choose buckets and check query cost:** day/hour/minute or controlled sharding; count how many partitions must be read for frequent queries.
7. **Lifecycle policies:** TTL, deletes, tombstones, compaction, long-term retention, and bucket determination on retries.
8. **Load test and observe:** partition size histogram, cell count, latency, tombstone count, largest partition, and hot replicas; tune using real measurements.

### Quick diagnostic table

| Symptom | Initial analysis | Remediation |
| --- | --- | --- |
| A few partitions are huge while table average remains low | Skewed size distribution; certain keys hold many rows/payloads | Identify large/hot keys, add buckets, or split tables by query. |
| Small size yet slow writes on certain nodes | Hot partition or replica set receiving concentrated load | Inspect per-key traffic, shard/throttle, distribute workload. |
| Few rows returned yet reads are very slow | Tombstones, many SSTables, wide slice | Investigate tombstones/compaction, narrow the read slice. |
| Disk usage is much larger than live data | Replicas, compression, tombstones, uncompacted SSTables | Separate logical size from physical size; inspect compaction/TTL. |
| Multi-month query hits thousands of buckets | Bucket is too small for the primary query | Use a suitable bucket/rollup table, consider changing the access path. |
| `LIMIT 100` still triggers large partition warnings | `LIMIT` only caps returned results | Redesign keys or partition lifecycle policies. |
| Adding smaller regular columns does not improve latency | Root cause lies in distribution/tombstones/I/O | Use read latency, disk, and per-key metrics to pinpoint the cause. |

## 12. Practice exercise

An application logs customer activity history with:

- 1,000 active customers.
- Each customer averages **10 events/second** during peak hours, lasting 2 hours per day.
- Average logical payload per event is **1 KiB**, excluding overhead.
- Primary read need: "fetch up to 100 latest events for **one customer on one day**."
- Secondary read need: "view **7 days** of history for that customer."

Compare two options:

```sql
-- Option A: one partition for all history of a customer.
PRIMARY KEY (customer_id, occurred_at, event_id)

-- Option B: each day of a customer is one partition.
PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
```

**Questions:**

1. During the 2 peak hours, roughly how many rows does one customer generate?
2. Roughly how many MiB is the logical payload of those rows?
3. After 30 days at the same rate, what is the cumulative payload size of Option A, assuming no TTL and no duplicate-key writes?
4. Does Option B bound row count per partition key better than A?
5. What will querying 7 days of history in B need to do?
6. If one customer spikes to **200 events/second**, is a daily bucket guaranteed to stay safe?
7. Should you run `SELECT COUNT(*)` across all customers during peak hours to monitor row counts?

**Answers and explanations:**

1. `10 × 3,600 × 2 = 72,000` rows/customer/day.
2. `72,000 KiB / 1,024 ≈ 70.3 MiB` payload/day.
3. `70.3125 MiB × 30 ≈ 2,109.4 MiB ≈ 2.06 GiB` payload for one Option A partition over 30 days (excluding overhead/compaction).
4. **Yes**: B creates a new partition each day. Rows per daily partition are around 72,000 under the assumption; A accumulates the entire history.
5. It must read the **7 matching day buckets** and merge/sort by timestamp if a unified list is desired; there is no global clustering order across partitions.
6. **Not necessarily**: `200 × 3,600 × 2 = 1,440,000` rows in 2 hours, around **1.37 GiB payload/day** at 1 KiB/row. Evaluate hourly/minute buckets or load splitting based on queries and real metrics.
7. **No**: massive counts during peak hours can impose significant load. Use metrics/histograms, proactive write-stream counters, and controlled sampling.

This exercise illustrates why **row count**, **byte volume**, and **access frequency** must all be considered; knowing only the partition key name or schema column count is not enough.

## 13. Key takeaways

- A **partition** is the group of data corresponding to the **entire partition key**; it can hold many clustering rows.
- Evaluate size across **row count**, **cell/value count**, **byte volume**, **tombstones**, and **access load**; schema CQL column count is only part of the picture.
- Logical size, replica SSTable size, and cluster-wide size **are not the same metric**.
- **Large partitions** concern data volume; **hot partitions** concern traffic concentration. You can encounter either or both.
- **Time bucketing** bounds historical accumulation inside a partition, but increases the number of partitions queried when reading across multiple buckets.
- `LIMIT`, driver paging, and TTL help manage query output and data lifecycle; they **do not replace** choosing a sound partition key.
- Inspect histograms, outliers, tombstones, compaction, and replica performance before settling on daily, hourly, or minute buckets.

When you clearly understand row counts, column/cell counts, and storage volume, you can design Cassandra partitions with predictable sizes, operate replication/compaction/repair with fewer surprises, and build CQL queries and Java applications that meet real-world latency requirements.
