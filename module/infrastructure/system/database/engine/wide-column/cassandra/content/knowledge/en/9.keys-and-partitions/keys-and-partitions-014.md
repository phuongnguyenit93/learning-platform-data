# Estimating, Measuring, and Validating Partition Limits

One of the decisions with the strongest impact on Apache Cassandra performance is choosing the **partition key**. This key determines which data belongs to the same logical partition and which replicas are responsible for storing, reading, and writing that partition. If a key accumulates too many rows, cells, or bytes, the partition can become oversized; if a key receives concentrated traffic, it can become a **hot partition** even before data grows large.

Therefore, the question "How big is a Cassandra partition allowed to be?" should not be answered with a single MB number. You must go through **three complementary steps**:

1. **Estimate before deployment** from traffic, record size, retention period, and key selection.
2. **Measure real data and load** using table/SSTable statistics, histograms, metrics, data samples, and safe measurements.
3. **Validate operational limits** through load testing with both typical and outlier distributions, latency criteria, alerts, and schema-adjustment workflows.

This lesson belongs to the **Keys and Partitions** chapter of the Apache Cassandra module, placing partition sizing in the context of the distributed wide-column model, CQL, replication, consistency levels, TTL, compaction, repair, error handling, and Java application integration.

After this lesson, you will be able to:

- Compute expected **row**, **value/cell**, and **byte** counts inside a partition.
- Distinguish **logical capacity**, **physical footprint per replica**, and **cluster-wide footprint**.
- Interpret `nodetool tablestats`, `nodetool tablehistograms`, and related metrics within their proper scope.
- Spot **outlier partitions**, **hot partitions**, and tombstone costs even when live row counts are low.
- Build load tests, warning thresholds, and pass/fail criteria for partition key designs.
- Choose time buckets or shards based on measured data while keeping CQL/Java queries aligned with keys.

## 1. "Partition size" has multiple meanings

Suppose a table stores device measurements:

```sql
CREATE TABLE measurements_by_device (
    tenant_id       text,
    device_id       uuid,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    humidity        double,
    payload         text,
    PRIMARY KEY (
        (tenant_id, device_id),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

In this schema, the partition key is **`(tenant_id, device_id)`**. `measured_at` and `measurement_id` are **clustering columns**, identifying and ordering rows **inside** the partition. Adding more measurements does not create more partition keys if tenant and device stay unchanged.

```text
Partition ('acme', device-01)
│
├── (2026-11-21 08:15, M3) -> temperature, humidity, payload
├── (2026-11-21 08:10, M2) -> temperature, humidity, payload
├── (2026-11-21 08:05, M1) -> temperature, humidity, payload
│
└── ... months or years of data ...
```

Each time a **new clustering key combination** is added, the logical row count can grow. Conversely, rewriting **the exact same full primary key** upserts into the same logical row rather than creating a second row.

### Quantities to distinguish

| Quantity | What question does it answer? | What it does not reveal |
| --- | --- | --- |
| **Logical row count** | How many distinct clustering key combinations exist? | Does not tell whether payloads are big or small. |
| **Cell/value count** | How many data values, collection elements, and metadata entries exist? | Does not equal declared CQL column count. |
| **Logical payload bytes** | How many bytes of record data does the application produce? | Excludes keys, overhead, compression, and tombstones. |
| **SSTable footprint on one replica** | How much disk space does the data occupy on a replica right now? | May include multiple versions, tombstones, and compaction variance. |
| **Cluster-wide footprint** | How many copies and overhead must the cluster hold? | Cannot be derived accurately by simply taking payload × RF. |
| **Traffic per partition key** | How many reads/writes per second does a key receive? | Even a small partition can run very hot. |

Saying "max 100,000 rows per partition" or "max 100 MB per partition" is only a **conditional operational assumption**, not a universal standard across all Cassandra versions and workloads.

## 2. Understanding rows, cells, and bytes in the wide-column model

A schema with five columns usually **does not mean** Cassandra stores exactly five physical cells for every row. Some columns can be absent; non-`frozen` collections can be represented via multiple cells; updates/deletes can leave tombstones; clustering key info, row markers, and metadata carry their own overhead.

```sql
CREATE TABLE audit_events_by_user (
    tenant_id  text,
    user_id    uuid,
    event_day  date,
    created_at timestamp,
    event_id   uuid,
    action     text,
    attributes map<text, text>,
    details    blob,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        created_at,
        event_id
    )
);
```

Examples:

- 100,000 rows with a short `action`, empty `details`, and small `attributes` have a completely different footprint than 100,000 rows with multi-KiB `details`.
- A huge `map<text,text>` can generate many cells and update costs, especially when deleting elements frequently.
- A few rows holding multi-MiB `blob` values can make a partition heavy despite low row count.
- If static columns exist, static values belong to the **partition**, and do not get multiplied by clustering row count in logical estimates.

For planning, you can use an approximate model:

```text
Data values per partition
  ≈ row count × average values/cells per row
    + shared static values

Logical bytes per partition
  ≈ row count × average logical bytes per row
    + static bytes
```

This is **not an exact physical cell calculation for SSTables**. Its purpose is preliminary schema sanity-checking before using observed metrics and benchmarks.

## 3. Formula for estimating row count over time

For event or time-series data, start from the **rate of creating new keys**:

```text
N_rows ≈ R_unique × T_bucket

R_unique : new full primary keys per second
T_bucket : seconds in one bucket
```

If the system sends 100 write requests/second yet 30% are retries/upserts onto existing keys, the rate of **new logical rows** can be below 100/second. In append-only workloads where every event gets its own full primary key, new rows nearly equal event count.

If a device writes **90 events/second**, each with a new identifier:

| Time span | Seconds | Expected logical rows |
| --- | ---: | ---: |
| 1 minute | 60 | 5,400 |
| 15 minutes | 900 | 81,000 |
| 1 hour | 3,600 | 324,000 |
| 1 day | 86,400 | 7,776,000 |
| 30 continuous days | 2,592,000 | 233,280,000 |

If the partition key is only `(tenant_id, device_id)` with no bounds, 30 days of history for this device can accumulate **over 233 million rows in one partition**. Adding a 15-minute bucket to the partition key keeps each partition around **81,000 rows** at the assumed average.

**Never calculate only averages.** In practice, a device or tenant can emit 5–20× normal traffic during peak hours. **Partition size at peak load** can matter more than the average partition.

### Accounting for growth rate with TTL

Suppose the table retains data for seven days via TTL. This can bound **live rows** within the retention window, yet does not guarantee SSTable footprint equals exactly seven days of payload:

- TTL expiration creates logical deletion state and can leave tombstones.
- Old data is only purged physically when compaction and safety conditions permit.
- If the partition key lacks a time bucket, even with only seven days of live data, all activity still concentrates on **one key** for that device.
- If written to the same partition at very high rates, it can still run **hot** second by second.

## 4. Estimating bytes: payload, keys, and overhead

An initial budgeting model:

```text
B_logical_estimated
    = N_rows × (B_payload_avg + B_key_and_row_overhead_assumed)
      + B_static

B_payload_avg
    = total sampled payload bytes / sampled row count

B_key_and_row_overhead_assumed
    = preliminary assumption for clustering keys, row/cell metadata
      (used only for forecasting; must be calibrated with real measurements)
```

Sample the **payload size distribution**, rather than relying on a single mean. For example, applications writing `text`/`blob` often have some events vastly larger than the rest.

### Detailed example

Suppose a device class has:

- 90 events/second, each with a distinct full primary key.
- 15-minute bucket.
- Sampled average payload is **600 bytes/event**.
- Assume an extra **200 bytes/event** for keys and logical overhead in the sizing exercise.

```text
Rows per bucket:
    90 × 900 = 81,000

Payload:
    81,000 × 600 = 48,600,000 bytes = 48.6 MB

Assumed keys + overhead:
    81,000 × 200 = 16,200,000 bytes = 16.2 MB

Preliminary total forecast:
    64,800,000 bytes = 64.8 MB ≈ 61.8 MiB
```

**Do not treat 200 bytes as a standard Cassandra overhead.** It is an assumption to illustrate the math; actual physical overhead depends on schema, data types, compression, Cassandra version, SSTable layout, and compaction state.

If an outlier device hits **5×** this rate for 15 minutes, that forecast alone jumps to around **324 MB** before factoring in physical storage. Therefore, design for per-key rate distributions and build a scenario table.

### Percentile-like scenario table

| Scenario | Events/sec | Rows per 15-min bucket | Forecast bytes at 800 B/row |
| --- | ---: | ---: | ---: |
| Typical device | 90 | 81,000 | 64.8 MB |
| Heavy-load device | 180 | 162,000 | 129.6 MB |
| Outlier device | 450 | 405,000 | 324.0 MB |
| Extreme device | 900 | 810,000 | 648.0 MB |

This table is **not a measured histogram**; it is scenario modeling. True p95/p99 percentiles must be computed from actual data across **partition keys**, not inferred by arbitrarily labeling multiplier tiers.

## 5. Three capacity layers: logical, replica, and cluster

Cassandra is a distributed database using an LSM tree. Data is written through commit log/memtable, flushed to SSTables, and reorganized via compaction. One partition can appear across multiple SSTables before being merged in storage.

Separate three layers:

1. **Logical data size:** current live values represented by the data model.
2. **Replica on-disk footprint:** SSTables, compression, indexes, cell metadata, tombstones, and uncompacted versions held by one replica.
3. **Cluster footprint:** copies across multiple replicas plus per-node operational overhead, compaction/streaming, and actual distribution state.

```text
Payload/row × row count
      |
      v
Logical estimate of one partition
      |
      +--> overhead, compression, tombstones, SSTables, and compaction
      |          |
      |          v
      |    footprint on one replica (can vary over time)
      |
      +--> replication factor, topology, replica count, node state
                 |
                 v
             cluster-wide footprint
```

For example, suppose a keyspace has **replication factor 3**. If a partition has 50 MiB of logical data, corresponding data can exist on three replicas per replication policy. However, claiming "that partition takes exactly 150 MiB across the cluster" is **unfounded**, because physical footprint depends on compression, overhead, multiple SSTables, tombstones, and maintenance activity.

**Never divide total cluster storage by total partition count to estimate the largest partition.** Averages can hide a few massive tenants or devices.

## 6. Large partitions and hot partitions need two sets of measurements

One partition can be only 2 MiB yet receive 30,000 requests/second. Another partition can hold 400 MiB of data yet be read only once a day.

| Problem type | Measure first | Risk |
| --- | --- | --- |
| **Large partition** | Row count, cell count, bytes/partition, tombstones | Resource-heavy wide slice reads, compaction, streaming, repair. |
| **Hot partition** | Read/write request rate and latency per key, node/replica | Concentrated CPU/I/O/network, queueing, and timeouts. |
| **Large + hot** | Both size and traffic | Compounding effects, easily triggering huge latency tails. |
| **Tombstone-heavy** | Tombstones scanned/read, TTL/delete patterns | Returning few rows while still processing lots of deleted data. |

Partition key hashing with `Murmur3Partitioner` distributes **different keys** to tokens, yet does not split one hot key into multiple partition keys. Clustering columns locate row slices within one partition; they **do not** spread a partition's load across other replica sets.

Therefore, when forecasting limits, never set only "max size per partition"; also define targets for **max read/write rate per active key**, **p95/p99 latency**, and compaction/repair budgets.

## 7. Measuring in practice with `nodetool tablestats`

Cassandra provides observability at multiple levels: node, table, SSTable, query, and (depending on tools/version) sampled partition keys. The commands below use an illustrative keyspace/table:

```bash
nodetool tablestats app_ks.measurements_by_device
```

Potentially useful fields, with **names and availability depending on version**:

- **SSTable count, space used (live/total):** table SSTable usage **on the queried node**, not the exact size of a single partition.
- **Compacted partition minimum/mean/maximum bytes:** partition size statistics after compaction or across SSTable data per the version's stats mechanism; useful for spotting large distribution tails.
- **Read latency, write latency:** indicators of access cost at table/node level; averages do not replace p95/p99.
- **Average live cells per slice and tombstones per slice:** hints at how much data is traversed during a read slice.
- **Bloom filter, memtable, pending flush/compaction metrics** if available: help clarify accompanying costs.

**Limitation:** `tablestats` does not provide a complete `partition_key → exact current bytes` map for every key. A partition can span multiple SSTables, involve compression, tombstones, and multiple replicas. Therefore, statistics **should not be interpreted as an exact, instantaneous count of a specific live partition**.

A practical reading workflow:

1. Compare **mean** against **maximum**; if max is many times higher than mean, outliers need investigation.
2. Correlate **latency** and SSTable/tombstone counts with large-partition warnings.
3. Run on **relevant replicas/nodes** if uneven distribution is suspected.
4. Record timestamps and Cassandra version to compare across runs.
5. Never sum or compare differently defined fields as if they were the same quantity.

## 8. Inspecting distributions with `nodetool tablehistograms`

To understand the data tail, histograms are far more informative than a single average:

```bash
nodetool tablehistograms app_ks measurements_by_device
```

Depending on version, the tool can report percentiles for:

- **Partition size:** distribution of partition sizes per the implemented sampling/statistics mechanism.
- **Cell count:** distribution of cell counts per partition.
- **Read/write latency or SSTables per read:** additional fields helping link data size to the read path.

Example **hypothetical numbers**, not output from a real cluster:

| Partition size statistical percentile | Hypothetical value |
| --- | ---: |
| Median | 4 MiB |
| p95 | 18 MiB |
| p99 | 72 MiB |
| Observed/reported Max | 530 MiB |

Looking only at the 4 MiB median can miss several giant partitions. Meanwhile, p99 = 72 MiB does not prove every partition is under 72 MiB; the remaining 1% can contain vastly larger outliers.

Do not treat these percentiles as **exact percentiles across all live logical partitions**, as collection methods, sample sizes, SSTables, and recency vary by version. Label **measurement source and time window** clearly on dashboards.

### Interpreting histograms in workload context

- **High bytes, low cell count:** suspect large payloads or huge collections/blobs.
- **High cell count, low average bytes:** many small values, substantial row/cell overhead, and clustering cost.
- **Rising read latency, stable size:** may stem from hot partitions, tombstones, compaction, or node/network factors.
- **Continuously rising max size:** review buckets, retention, write rate, backfills, and outlier tenants.

## 9. Finding partition keys worth investigating without full-table scans

When histograms reveal outliers, the next step is **identifying which key** is responsible. This is not the time to run `SELECT *` or `COUNT(*)` across an entire production table.

Options, depending on the system:

1. **Application/ingest-layer telemetry:** record event counts and bytes by `tenant_id + device_id + bucket` in controlled groupings.
2. **Sampling queried partition keys:** track request counts or payload sizes for a sampled key set, avoiding turning metrics into an unbounded high-cardinality label table.
3. **Version-specific hot-partition tools:** some versions provide `nodetool toppartitions` or similar sampling/stats mechanisms; verify exact syntax and behavior on your running version.
4. **Large-partition logs/warnings:** rely on compaction warning thresholds or supported observability features.
5. **Controlled SSTable/snapshot analysis:** offline tools like `sstablemetadata` and related utilities can provide extra insight; check version compatibility and run on safe copies when there is risk to production I/O.

If you need to inspect a partition whose key is already known, start with a **bounded query**:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

This query only proves a few rows can be read in clustering order. It **does not measure the byte size of the entire partition**.

### Why isn't `COUNT(*)` a free measurement?

```sql
-- Illustrative only; weigh the cost before running on a large partition:
SELECT COUNT(*)
FROM measurements_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

To compute the result, Cassandra must process the relevant data; with millions of rows/tombstones, the query can consume substantial CPU/I/O and time. `COUNT(*)` only reports the **row count observed by the query**, not exact physical byte size, and is not a good periodic monitoring tool for hot partitions.

If continuous business counts are needed, design a **statistics pipeline, summary table, or properly coordinated counter**, instead of scanning entire partitions every time a count is displayed.

## 10. Validating limits with production-like benchmarks

Estimates and histograms must tie back to **latency, throughput, and availability targets**. A partition model holding 100 MiB may work well for reading 100-row slices, yet fail if the product constantly scans the whole partition under tight SLAs.

### Designing a test matrix

For a time-series table, prepare scenario groups:

| Scenario | Data / load to simulate | What to measure |
| --- | --- | --- |
| Normal | Median partition, small events, few tombstones | Read/write p50/p95/p99 and throughput. |
| Long-term | Partition near forecasted max, multiple SSTables | Latency of LIMIT, range reads, and paging. |
| Outlier tenant | One key at 5–10× average rate | Hot partition, replica CPU/I/O/network, timeouts. |
| Large payloads | Some rows with very long blobs/text | Response size, heap/GC, network, and disk. |
| TTL / deletes | Frequently expiring or deleted data | Tombstone scans, latency, compaction. |
| Compaction / repair | Background tasks running alongside query load | p99, disk headroom, pending compactions, throughput. |
| Late events / backfill | Writes to older buckets, heavy replay requests | I/O, compaction state, and key correctness. |

Never run just one "insert 1 million random rows and measure TPS" test. A generator's key distribution can be **far more uniform than reality** and fail to reproduce an extremely hot tenant.

### Important variables to keep realistic

- Cassandra version, node/data center topology, node count, and replica configuration.
- Actual row/cell sizes, fraction of large payloads, collections, and compression.
- RF and consistency levels per query group.
- Read/write ratio, clustering query spans, LIMIT, page size, and concurrency.
- TTL, update/delete rate, compaction strategy, and data age distribution.
- Distribution across **partition keys**: median, p95/p99, max read/write rates.
- Test duration long enough to observe flushes, compaction, caches, and background work.

You can use `cassandra-stress` to generate load or write a custom generator matching the real data model. **What matters is realistic workload and key distribution**, not the tool name.

## 11. Setting guardrails: warnings, rejections, and application limits

Distinguish **hard limits**, **Cassandra-version guardrails**, and **operational budgets set by the platform team**.

| Limit type | Source | Interpretation |
| --- | --- | --- |
| **Technical / format constraints** | Data types, protocol/storage format and implementation limits | Can cause invalid operations or failures; verify per version. |
| **Server warnings / guardrails** | Cassandra configuration and running version | Can emit warnings or block operations when configured thresholds trigger. |
| **Internal SLOs / quotas** | Benchmark results and product requirements | Usually stricter than what the server still tolerates; guides schema/bucketing. |
| **Application-layer quotas** | APIs, ingestion, orchestration layer | Caps requests, bytes, fan-out, or retention per tenant. |

Some Cassandra versions have **compaction-related partition size warning thresholds**, named depending on version (such as large-partition warning settings). Seeing a warning log **does not mean** every partition exceeding that warning immediately rejects writes, and seeing no logs **does not prove** partitions are always safe.

Never copy a warning threshold from a blog post or another version and call it "Cassandra's maximum limit." To finalize thresholds:

1. Confirm the **exact Cassandra version/distribution** and active configuration.
2. Clarify whether the threshold applies to **partition size, row size, mutation size, or batch size**.
3. Determine whether behavior is **warning or failure**, when it is checked, and measurement scope.
4. Load-test enough to prove latency/repair/compaction goals hold beneath the threshold.
5. Have a mitigation plan when a tenant or key exceeds budget.

### Illustrative internal policy example

```text
Planned policy of one system (not Cassandra defaults):

- Track partition size distributions across all time-series tables.
- Investigate when max or p99 exceeds load-tested baseline.
- Cap buckets/shards read in a single API request.
- Bound concurrent reads/writes/backfills per tenant.
- Halt backfill rate increases if production p99, compaction backlog,
  disk headroom, or timeouts exceed budget.
- Select new buckets and migrate when partitions routinely
  exceed actual cluster capacity.
```

The distinction between an **operational warning** and a **server-rejected failure** must be documented in runbooks to prevent wrong incident responses.

## 12. Choosing buckets based on validated thresholds

Suppose the legacy table stores all measurements of a device in one partition:

```sql
PRIMARY KEY (
    (tenant_id, device_id),
    measured_at,
    measurement_id
)
```

After measuring, the operations team finds high-load devices accumulate months of data, and load tests show historical queries slow down as partition span grows. One option is splitting by **hourly buckets**:

```sql
CREATE TABLE measurements_by_device_hour (
    tenant_id       text,
    device_id       uuid,
    hour_bucket     timestamp,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    humidity        double,
    payload         text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

`hour_bucket` is defined as the **start of the UTC hour** of `measured_at`. For example:

```text
measured_at = 2026-11-21T08:43:12Z
hour_bucket = 2026-11-21T08:00:00Z
```

CQL query within one bucket:

```sql
SELECT measured_at, measurement_id, temperature, humidity
FROM measurements_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND measured_at >= '2026-11-21T08:15:00Z'
  AND measured_at <  '2026-11-21T08:30:00Z'
LIMIT 100;
```

This is one partition lookup with a clustering key range. If a query spans **two hours**, the application must read two partition keys and merge results, because clustering order only holds inside each partition.

### Trade-off table

| Option | Benefit | Risk to measure |
| --- | --- | --- |
| No bucket | Easy to read entire history of a device in one partition | Partition accumulates and can become large/hot. |
| Daily bucket | Fewer partition lookups for a one-week history | One day of a hot device can still be too large. |
| Hourly bucket | Shrinks rows/bytes per partition | 24–25 partition lookups for a 24-hour range depending on boundaries. |
| Minute bucket | Shrinks individual partition size further | Fan-out rises sharply for long histories. |
| Bucket + shard | Splits load within the same time window | Readers must query relevant shards, merge, and manage hash/shard-count versioning. |

**Time buckets do not automatically cure write hotspots inside the active bucket.** If a device generates 10,000 events/second, all events in the current hour still hit the same `(tenant_id, device_id, hour_bucket)`. In that case, test shorter buckets, shards, or another ingestion design weighed against read cost.

## 13. TTL, tombstones, and compaction alter measurement results

A partition may hold **very few live rows** yet still burn heavy I/O on reads due to tombstones or multiple SSTables.

Example writing an event into an hourly bucket with a seven-day TTL:

```sql
INSERT INTO measurements_by_device_hour (
    tenant_id, device_id, hour_bucket,
    measured_at, measurement_id,
    temperature, humidity, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:43:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    38.1,
    67.5,
    'sensor=ok'
) USING TTL 604800;
```

TTL expires cells after that duration from **write time**, per Cassandra semantics. However, physical data can remain in SSTables until eligible for cleanup during compaction. If many `UPDATE`/`DELETE` operations occur, tombstones can build up rapidly.

**Measurement implications:**

- **Low `COUNT(*)`** does not imply a small SSTable footprint.
- Histogram/compaction metrics can reflect data not yet purged.
- Read latency can increase because reads must skip past tombstones to gather live rows.
- Repair and tombstone lifecycle settings affect deletion safety; never shrink `gc_grace_seconds` arbitrarily to purge faster.
- `TimeWindowCompactionStrategy` may fit certain TTL/append-mostly time-series workloads, yet **does not split partition keys** and must be evaluated for write patterns, late-arriving data, and uneven TTLs.

When setting operational thresholds, measure during **steady writes, after TTL expirations begin, during/outside compaction, and during repair**. A short benchmark without tombstones can produce overly optimistic estimates.

## 14. Bounded queries and paging from Java Driver 4.x

Applications rarely need to read every row of a partition. With `measurements_by_device_hour`, the Java Driver can use prepared statements and page sizes to keep each response small.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class MeasurementRepository {
    private final CqlSession session;
    private final PreparedStatement readSlice;

    public MeasurementRepository(CqlSession session) {
        this.session = session;
        this.readSlice = session.prepare(
            "SELECT measured_at, measurement_id, temperature, humidity " +
            "FROM measurements_by_device_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet readOneHour(
            String tenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        Instant hour = startInclusive.truncatedTo(ChronoUnit.HOURS);
        Instant hourEnd = hour.plus(1, ChronoUnit.HOURS);

        if (!startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(hourEnd)) {
            throw new IllegalArgumentException(
                "Read range must lie within one UTC hour bucket");
        }

        BoundStatement query = readSlice.bind(
            tenantId, deviceId, hour, startInclusive, endExclusive
        ).setPageSize(50);

        return session.execute(query);
    }
}
```

Things to distinguish:

- `LIMIT 100`: maximum 100 rows returned by the query, **not** a cap on partition size.
- `setPageSize(50)`: desired page size for the driver; **does not** change stored row counts or guarantee low total read cost.
- `Instant` + `truncatedTo(HOURS)`: computes the hourly bucket in matching UTC time, consistent with producers.
- Interval `[startInclusive, endExclusive)`: prevents boundary duplicates when stitching consecutive slices.
- If a query range spans beyond one hour, the service layer must split across multiple buckets, read the relevant partitions, and merge results; never pick only the first bucket and silently drop data.

Actual latency measurements should separate **server time for the first page**, **time fetching subsequent pages**, and **application merge/sort time**. A query with a fast first page that reads entire history across 10,000 pages still carries heavy cost.

## 15. Verification workflow after changing the partition key

Moving from `measurements_by_device` to `measurements_by_device_hour` typically requires a new table and migration. You cannot simply add `hour_bucket` as a regular column and expect data to split itself.

A verifiable rollout workflow:

1. **Lock targets:** which queries must be fast, expected post-change max/p99 partition size, and partition lookups per API call.
2. **Create the new table:** use a composite key with buckets, proper data types, and clustering order.
3. **Use deterministic bucket calculation:** producers, backfills, and readers share one UTC rule; event IDs/`occurredAt` stay stable across retries.
4. **Preserve new data during transition:** monitored dual-write or replay from a reliable event source; never assume two tables update atomically.
5. **Backfill with paging/checkpoints:** split work by source partition and clustering time range, bounding concurrency.
6. **Handle TTL/updates/deletes:** never copy only live rows and call it done if the source has concurrent changes; use a delta log or final sync process.
7. **Reconcile data:** verify keys, payloads, bucket boundaries, delete/TTL states, and new queries.
8. **Validate performance:** run the same representative load, re-measure partition histograms, p99 latency, hot keys, compaction, and fan-out queries.
9. **Cut over with rollback:** switch read/write paths at clear marks, keeping ability to replay deltas back to the legacy path if needed.
10. **Clean up legacy schema** only after the rollback window closes and approval is granted.

**Before/after metrics to compare** go beyond average partition size. For example:

| Verification | Before | After | Criterion |
| --- | --- | --- | --- |
| Max/p99 partition size | Measured on old table | Measured on new table | Tail shrinks within agreed budget. |
| Read p99 for Q1/Q2 | Baseline | Under representative load | Stays within SLO. |
| Top write key rate | Concentrated on device partition | Split by device/hour | No hotspot exceeding replica capacity. |
| Tombstones scanned | Baseline | Per new table TTL/deletes | No abnormal read amplification. |
| Partition lookups/API | Few yet large partitions | Potentially higher | Fan-out remains within budget. |
| Data correctness | Source of truth | Shadow read / reconciliation | Zero missing, duplicated, or mis-bucketed records. |

Once measured data is available, **calibrate the estimation formulas**: replace initial assumptions with real row sizes, payload distributions, and observed compression/overhead deltas.

## 16. Practice exercise: designing a partition budget

A transaction tracking service has **2,000 accounts**. Hypothetical workload:

- Standard accounts: **8 events/second** during two peak hours per day.
- Large accounts: **150 events/second** during two peak hours per day.
- Each event has **900 bytes of logical payload**, excluding keys/overhead.
- Each event has its own distinct full primary key.
- Primary query: 100 latest events **within one hour**.
- Secondary query: **seven days** of history.
- The system retains data for 30 days per business policy.

The design team evaluates two keys:

```sql
-- Option A: one partition per account, all time.
PRIMARY KEY (account_id, occurred_at, event_id)

-- Option B: one partition per account per hour.
PRIMARY KEY ((account_id, hour_bucket), occurred_at, event_id)
```

**Questions:**

1. In A, does `occurred_at` participate in token calculation?
2. How many rows does a standard account generate in **one peak hour**?
3. How many rows and how many MB of logical payload does a large account generate in **one peak hour**?
4. Over **30 days** assuming two identical peak hours each day, how many rows does A accumulate for a large account without deletes/TTL?
5. How does B reduce row count per partition compared to A?
6. With B, a query spanning an exact **seven-day** window can intersect at most how many hourly buckets depending on boundaries?
7. Why cannot `LIMIT 100` serve as proof that B is safe at all loads?
8. After running `nodetool tablehistograms`, what does a small p99 size paired with a huge max size indicate?
9. If a large account emits 150 events/second throughout the current hour, does the hourly bucket automatically split that account's concurrent write load?
10. With a 30-day TTL in place, can you use `COUNT(*)` row counts as exact physical byte size on disk?
11. If a benchmark only generates uniform random partition keys, what problem might it miss?
12. Which metrics must be measured together to decide "within limits" before deployment?

**Answers with explanations:**

1. **No.** The partition key is only `account_id`; `occurred_at` and `event_id` are clustering columns.
2. `8 × 3,600 = 28,800` rows.
3. `150 × 3,600 = 540,000` rows; `540,000 × 900 = 486,000,000 bytes = 486 MB ≈ 463.5 MiB` payload, excluding overhead/compression/replicas.
4. `540,000 × 2 × 30 = 32,400,000` rows in one account partition under A as assumed.
5. B creates **one partition per account/hour with data**, instead of accumulating all history. A large account's peak hour can still hold 540,000 rows; load-test to verify whether that is small enough.
6. An exact seven-day window (168 hours) can intersect **168 or 169 hourly buckets**, depending on whether start/end align with hour boundaries under half-open intervals.
7. Because LIMIT only caps returned rows, not physical size, tombstones, compaction/repair, or write hotspots.
8. There is an **outlier partition** worth investigating; p99/mean does not represent every partition. Identify the outlier's key and history/load.
9. **No.** Writes in the current hour for the same `account_id` still share **one partition key `(account_id, hour_bucket)`**; if hot, consider shorter buckets, sharding, or throttling.
10. **No.** `COUNT(*)` does not measure bytes, and TTL/tombstones/compaction make physical footprint differ from logical data.
11. It can miss **skew/hot partitions**, one account dominating traffic, and overly wide clustering range scans.
12. Measure partition size/cell count **p95/p99/max**, top read/write keys, p99 latency, timeouts, SSTables/tombstones, I/O/CPU/GC, compaction/repair, and API fan-out under realistic workload and data.

## 17. Checklist to apply to a Cassandra table

- [ ] Identify the **full partition key** and clustering columns; do not confuse a time-increasing key with a new partition key.
- [ ] Calculate rows/partition for normal, peak, and outlier tenant/device rates.
- [ ] Sample bytes/row and collection elements; estimate key/metadata overhead with explicitly stated assumptions.
- [ ] Separate logical payload, single-replica footprint, and cluster footprint with RF.
- [ ] Measure partition size/cell count histograms, max, and tail distributions; do not watch only the mean.
- [ ] Measure read/write rates of hot keys and replica/coordinator resources.
- [ ] Track tombstones, SSTables per read, compaction backlog, and TTL effects.
- [ ] Never use `COUNT(*)` or full-table scans as routine capacity measurements in production.
- [ ] Verify version-specific guardrails/warnings and distinguish warning thresholds from hard failures.
- [ ] Benchmark with **realistic workloads** including skew, large payloads, TTL, updates/deletes, and background work.
- [ ] Choose time buckets/shards factoring in **fan-out cost** of primary queries.
- [ ] Use CQL queries with full partition keys, meaningful LIMIT/paging, and consistent UTC buckets in Java.
- [ ] Configure alerts, quotas/backpressure, backfill halt thresholds, and runbooks for outliers.
- [ ] When changing keys, plan a new table, replay/dual-write, verification, and rollback.
- [ ] Declare "partitions within limits" only after meeting **measured criteria**, not based on a generic MB figure.

## 18. Key takeaways

- Partition estimation requires **row count × data size**, factoring in cells/collections, overhead, TTL, and **load distribution across keys**.
- An average metric does not reveal the **largest partition** or **hottest key**; always watch tails and outliers.
- `nodetool tablestats` and `nodetool tablehistograms` provide **valuable diagnostic statistics**, not exact instantaneous counts for every live logical partition.
- There is no single **MB/row threshold valid for every Cassandra cluster**. Hard limits, server warnings/guardrails, and internal SLOs are three distinct concepts.
- **LIMIT and paging** control result volume, yet do not shrink stored data or eliminate tombstone/compaction costs.
- **Buckets** bound historical accumulation in a partition; **shards** create additional concurrent partition keys, trading off against read fan-out.
- **Replication, consistency levels, compaction, and repair** affect footprint, availability, and latency, but do not substitute for sound partition key selection.
- Sizing formulas must be **calibrated with real measurements and benchmarks**, then re-verified after schema changes.

Knowing how to estimate, measure, and validate partition limits lets you select Cassandra partition keys based on evidence, anticipate read/write and operational costs, and build Java applications with explicit query budgets. This is the foundation for preventing large/hot partitions and sustaining a stable distributed wide-column system as data continues to grow.
