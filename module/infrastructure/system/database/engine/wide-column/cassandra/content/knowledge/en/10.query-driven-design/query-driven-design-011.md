# Estimating Capacity from Record Size, RF, Indexes, and Retention

## Lesson Objectives

When designing Apache Cassandra, asking "each record is about 1 KB, so how much disk do I need?" is not enough for capacity planning. You must know **how many records are written per unit of time**, how long they are retained, how many bytes each record actually occupies in SSTables, how many **replicas** exist, whether query-driven duplicated tables or additional indexes exist, and how much headroom the cluster needs for **compaction, repair, growth, and node failures**.

Within the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson walks through the estimation and measurement workflow for wide-column Cassandra: from partition keys and clustering keys, CQL, replication factor (RF), and TTL/retention to tombstones, compaction, repair, and how a Java application provides reliable input metrics.

After this lesson, you will be able to:

- Distinguish **logical payload size**, **on-disk single-copy size**, **total replicated storage**, and **cluster provisioned capacity**.
- Estimate live rows from write rate, retention duration, and update/delete rates; avoid confusing peak write rate with average volume.
- Calculate RF per datacenter, add index/projection table costs, and divide load across nodes.
- Evaluate **largest partition size**, not just cluster-wide total bytes.
- Explain why TTL expiration does not immediately free disk space, and how tombstones/compaction affect actual disk usage.
- Build a capacity worksheet with explicit assumptions, a benchmark plan, monitoring metrics, safety headroom, and design-review thresholds.

## 1. Four Capacity Layers to Distinguish

Example of a device-event ingestion system:

```text
Devices -> Cassandra
             |
             +-- main event table (queried by device + day)
             +-- lookup table or secondary projection (if domain needs it)
             +-- indexes on certain columns (if supported and used)

Each partition of each table
             |
             +-- replica on node A
             +-- replica on node B
             +-- replica on node C     (RF=3, example)
```

Separate four layers in your calculations:

| Layer | Question | Example |
| --- | --- | --- |
| **Logical payload** | How many rows and raw business bytes exist before Cassandra storage? | 200 million events, averaging 900 B each |
| **On-disk single copy** | How much do SSTables, keys, indexes, metadata, compression, etc. actually occupy? | 750 B/live row on average, measured on a representative sample |
| **Replicated storage** | Across how many replicas/DCs are those copies placed? | RF=3 roughly triples a single copy's data footprint |
| **Provisioned capacity** | How much disk must be provisioned for safe utilization and operational headroom? | Used storage divided by target utilization, plus unmodeled reserves |

**Never multiply RF twice.** If a measured "total cluster disk used" metric already includes all replicas, do not multiply by RF again. Conversely, if a figure represents **one logical copy of a table**, apply replication accordingly.

**Never equate wire/payload bytes with on-disk bytes.** A CQL row carries column count, key lengths, and metadata; Java/JSON serialization differs from SSTable layout. Compression can shrink storage, while indexes, tombstones, and updates can grow it. Thus an input like 900 B/event is only a starting point.

## 2. Gather Query Contracts and Write Profiles Before Sizing

Cassandra capacity depends heavily on **query-driven table modeling**. One entity stored across three query-driven tables must be counted as three logical representations, not a single source record.

Illustrative initial catalog:

| ID | Operation | Access Path | Capacity Impact |
| --- | --- | --- | --- |
| Q01 | View 50 newest events for a device/UTC day | Partition `(tenant,device,day)`, time clustering | Determines daily partition size |
| Q02 | View device events over 7 days | Read up to N known daily buckets | Affects fan-out, page size, and rows read |
| Q03 | Look up event by ID | Lookup table `(tenant,event_id)` if needed | Adds projection table storage |
| Q04 | Search by severity across tenant | Index or separate query table if SLA-backed | Adds index/write storage cost |
| W01 | Continuous telemetry writes | Append events | Determines rows/day |
| W02 | Deletes / TTL expirations | Tombstones and compaction | Determines dead bytes not yet reclaimed |

For each table, gather:

1. **Creation rate:** average, p95, and **peak-hour** events/second; break down by tenant, device, region, and data type.
2. **Row size:** average, p95/p99, maximum size; watch large payloads, long keys, text/`blob`, nullable columns, and column count.
3. **Retention:** 7 days, 30 days, or 1 year; whether TTL counts from write time or occurrence time.
4. **Mutation mix:** upsert/delete percentage, late-arriving records, replays, backfills, and tombstone-generating status transitions.
5. **Replication:** DC count, RF per DC, node counts, and token distribution skew.
6. **Indexes/projections:** how many duplicated tables, which columns are indexed, index footprint, and maintenance overhead.
7. **SLOs/SLAs:** read/write latency, write availability, RPO/RTO, repair windows, growth rate, and maximum acceptable disk utilization.

Asking only "how many TB of data?" without knowing **query paths and how data is retained/deleted** easily miscalculates both storage and partition design.

## 3. Starting from Written Rows and Retention

Notation:

```text
R = average new records/second across the workload
D = seconds/day = 86,400
T = retention period in days
S = average raw business payload size per record, in bytes

new_rows_per_day = R × D
live_rows_steady_state ≈ R × D × T
logical_payload_bytes ≈ live_rows_steady_state × S
```

Assuming **steady write rate**, **few early updates/deletes**, **no massive backfills**, and time-based retention, this estimates **steady-state live data**, not total allocated SSTable bytes.

### 3.1. 30-Day Telemetry Example

Suppose **1,000 devices** each generate an average of **0.1 events/second**. Total average rate is **100 events/second**. Each event averages **900 bytes of raw business data**.

```text
Cluster-wide rate: 1,000 × 0.1 = 100 events/second
One day: 100 × 86,400 = 8,640,000 events
30 days: 8,640,000 × 30 = 259,200,000 live rows
Raw payload: 259,200,000 × 900 B
           = 233,280,000,000 B
           = 233.28 GB (decimal units)
```

**233.28 GB is not Cassandra's on-disk footprint**, nor has RF been applied yet. It is the raw payload of **one representation** under these assumptions.

If the application adds an event-ID lookup table where every event writes a small mapping row, calculate **additional rows × actual mapping size** and apply RF to each table. If only 1% of events need lookup, use the business policy's row count rather than defaulting to 100%.

### 3.2. Changes Over Time

If traffic grows, `R × D × T` with a single `R` is insufficient. More accurately:

```text
live_rows(t) ≈ total records still inside the retention window
             = sum or integral of rate(τ) over τ ∈ [t - T, t]
```

For example, if the most recent 30 days had double the traffic of the prior 30 days, current live volume must reflect **the newest 30 days**, not a full-year average. When forecasting 6 or 12 months out, apply a monthly growth curve and compute retention over a **sliding window** so historical expired data is not double-counted as live.

With TTL measured from `event_time`, late-arriving events keep only partial remaining lifetime; with fixed write-time TTL, live row counts depend on ingestion timing. Both rules yield different storage and read profiles.

### 3.3. Distinguishing Averages from Peaks

**Long-term storage** depends on total rows generated inside the retention window. **Write throughput and hot partitions** depend on peak rates:

| Metric | Used For |
| --- | --- |
| Cluster average events/sec | Estimating long-term live storage |
| Cluster peak events/sec | Sizing throughput, CPU, network, and commit log speed |
| Peak events/sec of **one logical partition key** | Checking hot-partition risk |
| p99 row size | Guarding against large payloads and API limits |
| Backfill / replay bursts | Sizing sudden write spikes and older un-expired data |

Never design solely around `average events/s`. One device can dominate traffic at a given moment even when tenant-wide averages appear low.

## 4. Measuring Actual Record Size in SSTables

Storage layout for a Cassandra table:

```text
Business payload, keys, and columns
        |
        +-- Cassandra serialization/encoding
        +-- partition key and clustering keys
        +-- row/cell metadata, timestamps, and TTL metadata
        +-- SSTable data, partition index, summary, and related components
        +-- compression (can shrink Data.db)
        +-- tombstones and uncompacted obsolete data
        +-- secondary indexes if present
        |
        v
Actual footprint on one replica must be measured
```

On-disk size depends on **schema, data distribution, compression, compaction, TTL, partition count, and update/delete patterns**. There is no universal constant "+N metadata bytes per row" across all Cassandra versions.

### 4.1. Measured Multiplier Instead of Guessed Multiplier

Define:

```text
S_raw = average raw business bytes/row
S_disk = actual bytes/live row for ONE table copy
         (measured on a representative steady-state sample)
k = S_disk / S_raw

storage_one_copy ≈ live_rows × S_disk
                 = live_rows × S_raw × k
```

`k` can be **less than 1** with effective compression, or **greater than 1** when metadata/indexes, tiny partitions, many columns/TTLs, or tombstones add overhead. Never guess `k = 0.5` or `k = 2` without benchmarking.

If `S_disk` is measured from total on-disk bytes **already including secondary indexes**, do not add index storage a second time. If `S_disk` covers only the base table, measure indexes and projection tables separately. Always specify whether a figure covers **one replica**, **one node**, or **the entire cluster**.

### 4.2. Designing a Measurement Sample

For a reliable multiplier:

1. Use the **planned schema**, column types, key lengths, realistic payloads, and actual bucketing rules.
2. Load enough data for representative partition counts, clustering rows, and SSTables—not just a few hundred rows.
3. Drive **realistic traffic patterns**, including updates, TTLs, replays, and deletes if your workload does them.
4. Measure after data flushes from memtables and undergoes representative compaction; do not extrapolate from transient commit log sizes.
5. Record compression settings, compaction strategy, index state, node count/RF, and data age.
6. Compare disk bytes (in the exact measurement scope) against live row counts and expected tombstones; report an `S_disk` range rather than a single magic number.

For a 30-day retention policy, loading data for a few minutes and measuring right after flush **does not represent** steady state with expired events and multi-window compacted SSTables. Run long enough or simulate aged data in a realistic staging cluster.

## 5. CQL Example: Schema, Bucketing, TTL, and Verification

Suppose Q01 typically reads events for **one device on one UTC day**, newest first:

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload blob,
    PRIMARY KEY ((tenant_id, device_id, day_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

`(tenant_id, device_id, day_bucket)` identifies the partition; `(event_time, event_id)` defines ordering and row identity. Each event creates **one row**, while disk bytes include payload, keys, and Cassandra overhead.

Reading the 50 newest events for a single day:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

`?` placeholders are prepared-statement bind markers, not literals to paste straight into `cqlsh`. The query supplies the full partition key and reads in clustering order; however, `LIMIT 50` **does not** guarantee reading only 50 physical rows if tombstones exist.

### 5.1. Retention Measured from Write Time

To retain all events for **30 days from write time**, configure a table default:

```sql
ALTER TABLE device_events_by_day
WITH default_time_to_live = 2592000;
```

`2,592,000` seconds equals 30 × 24 × 60 × 60 seconds. A default TTL does not compute from `event_time` and **does not mean SSTable disk space is reclaimed right on day 30**.

### 5.2. Retention Measured from Event Occurrence Time

If the domain says "30 days from `event_time`" and events can arrive late, you can **leave default TTL unset** and compute remaining TTL on the write path:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

```text
expires_at = event_time + 30 days
ttl_seconds = expires_at - write_time

ttl_seconds > 0  -> write with remaining TTL
ttl_seconds <= 0 -> already expired; handle per expired-data policy
```

Sections 5.1 and 5.2 are **two distinct approaches** chosen per business policy. Do not mix both arbitrarily assuming TTL counts from the same baseline; altering `default_time_to_live` also does not automatically recalculate expiration for previously written data.

To inspect remaining TTL of a column on live rows:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 10;
```

`TTL(payload)` returns remaining seconds for a live cell with TTL. `null` can mean either no TTL or an absent cell; never infer every cell in a row shares the same expiry from one column alone.

## 6. Multiplying Storage by Replication Factor Correctly

Replication factor is the number of replicas Cassandra maintains per keyspace/placement configuration. If **one logical table copy** is `L` bytes, in a datacenter with `RF = 3`, the high-level model is:

```text
replicated_disk_bytes_in_dc ≈ L × 3
average_data_bytes_per_node ≈ (L × 3) / node_count_in_dc
```

This is an **idealized average** before accounting for token skew, hot/large partitions, heterogeneous node disks, indexes, and uneven components. Dividing evenly for planning does not mean every node actually consumes identical space.

### 6.1. `NetworkTopologyStrategy` Example

A keyspace deployed across two datacenters might look like:

```sql
-- Illustrative example: DC names must match actual topology.
CREATE KEYSPACE telemetry_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_primary': 3,
    'dc_backup': 2
};
```

In this example, **each partition has 3 replicas in `dc_primary` and 2 in `dc_backup`**, provided the topology has sufficient nodes and healthy configuration. For capacity planning:

```text
dc_primary storage ≈ L × 3
dc_backup storage  ≈ L × 2
Combined two DCs   ≈ L × (3 + 2) = L × 5
```

Never apply the primary DC's RF to the backup DC, and never divide `L × 5 / total_nodes` to size individual DC disks when node counts and skew differ. **Calculate each DC separately** with its own node count, headroom, and traffic.

### 6.2. Consistency Level Does Not Multiply Stored Copies

`LOCAL_QUORUM`, `ONE`, or other consistency levels control replica acknowledgment per operation given the topology. They affect latency, throughput, and availability during replica failures, but **do not create extra physical copies simply because a higher consistency level is chosen**. RF and replication strategy alone determine stored replica count.

Repair synchronizes replicas via Cassandra's mechanisms; it does not alter RF or create "free" capacity. During node outages or recovery, repair/streaming creates network, I/O, and temporary disk overhead that must be budgeted in reserves.

## 7. Indexes, Projections, and Other Multipliers

A query-driven system may combine **lookup tables**, time-series tables, status tables, and secondary indexes/SAI. All consume resources, but are accounted for differently.

| Component | What Is It? | How to Include in Estimates |
| --- | --- | --- |
| **SSTable primary-key/partition index** | Metadata for locating partitions and clustering rows | Usually included in measured `S_disk` of base table; **do not double-count** |
| **Bloom filters / summaries** | Read-acceleration structures consuming memory/disk by type | Track memory and disk footprint separately; not just payload size |
| **Secondary index / SAI** | Extra index structure supporting certain filters | Measure per-node/replica index size plus write amplification |
| **Event-ID lookup table** | Separate Cassandra table with a different partition key | Size rows, row footprint, and RF independently |
| **Query-driven projection table** | Denormalized representation for another screen | Sum storage, update/delete churn, and table-specific TTLs |
| **Snapshots/backups/CDC files** | Data for recovery or change streams | Budget outside live table bytes; hard links may share blocks depending on mechanism |

Never conflate a **secondary index** with a **projection table**. An index's structure and cost depend on Cassandra version and implementation; a projection is an application-maintained query-driven table typically having its own key and column subset.

### 7.1. Indexes Have No Fixed Universal Ratio

If benchmarks show an added index consumes an extra **25% of base table storage** under your real setup, you can model:

```text
base_one_copy = L
measured_index_ratio = 0.25
base_plus_index_one_copy ≈ L × (1 + 0.25)
```

**25% is purely an illustrative assumption**; Cassandra indexes can exhibit completely different ratios depending on column type, cardinality, value distribution, compression, updates/deletes, and version. Never assume 25% as a default for SAI.

If `S_disk` was already measured including the index, **do not add this factor again**. If an index exists on only one table, account for it only on that table.

### 7.2. Projections Can Amplify Write Load More Than Live Storage

Suppose an order is stored in three tables, including a `status` projection. Each status transition may:

1. Update the source row.
2. Update the customer list row.
3. Delete the row from the old status partition.
4. Insert a row into the new status partition.

Even when live row counts stay flat, **tombstones, commit logs, memtables, SSTables, and compaction** absorb those mutations. In capacity plans, track **live bytes** and **write/delete churn** separately rather than multiplying "order size" once.

## 8. How TTL, Tombstones, and Compaction Alter Storage

### 8.1. Expired Rows Are Not Physically Reclaimed Immediately

In Cassandra, TTLs and `DELETE`s write deletion markers/tombstones so older SSTables and replicas do not resurrect deleted data. After TTL expires, data ceases to be returned as live rows, yet physical bytes remain in SSTables until compaction and safety conditions permit reclamation.

Thus:

```text
disk_used ≠ live_rows × current_row_size

disk_used can include:
  live data
  + expired/unreclaimed records
  + tombstones
  + overwritten data still in older SSTables
  + indexes and metadata
  + transient data from compaction/streaming/snapshots
```

`gc_grace_seconds` and replica deletion synchronization govern tombstone purging safety. Never reduce this parameter arbitrarily solely to shrink disk usage; align repair schedules, node downtime policies, and your Cassandra version's mechanics.

### 8.2. Compaction Creates Transient Disk Demand

Compaction reads existing SSTables, writes new SSTables, and only then reclaims old files when eligible. During compaction, **both input and output files** coexist on disk. Leave headroom for:

- Active compaction and compaction backlogs.
- Repair, rebuild/streaming, or node replacement.
- Traffic spikes, replays/backfills, and downtime windows.
- Local snapshots, backups, or CDC files (depending on deployment).

Never treat `100% disk capacity` as fillable with live data. A nearly full cluster struggles to compact or stream during node failures even if `live_rows × RF` "fits" on paper.

### 8.3. `TimeWindowCompactionStrategy` and Retention

For largely append-only time series with relatively uniform TTLs and rare edits to older data, **TimeWindowCompactionStrategy (TWCS)** is worth evaluating. However:

- Compaction windows organize by **storage write timestamp**, not automatically by the partition key's `day_bucket`.
- Late-arriving events/backfills, historical edits, and highly mixed TTLs can prevent SSTables from expiring cleanly together.
- A frequently updated lookup table has a different write profile from history; never blindly assign the same compaction strategy to both.
- TWCS cannot fix an unbucketed partition key or a partition absorbing extreme load.

Measure disk usage after multiple TTL/compaction cycles; never declare "records expire on day 30 so disk drops identically on day 31."

## 9. Complete Capacity Calculation Example

Applying Section 3's numbers, assume a benchmark of **one base-table replica** measures `S_disk = 750 B/live row`, **already including** primary keys, base SSTable components, and compression on a representative sample, while excluding secondary indexes, snapshots, compaction headroom, and other projections.

Assume **one DC, RF=3, 6 homogeneous nodes**, targeting **70% provisioned disk utilization** for modeled data. That 70% figure is a **planning assumption**, not a mandatory Cassandra rule.

| Step | Formula | Result |
| --- | --- | ---: |
| 1. New rows/day | `100 × 86,400` | 8,640,000 rows |
| 2. Live rows after 30-day retention | `8,640,000 × 30` | 259,200,000 rows |
| 3. Raw business payload | `259,200,000 × 900 B` | 233.28 GB |
| 4. Base table on **one copy** | `259,200,000 × 750 B` | 194.40 GB |
| 5. Base table at **RF=3** | `194.40 × 3` | 583.20 GB |
| 6. Provisioned storage at 70% cap | `583.20 / 0.70` | ~833.14 GB DC-wide |
| 7. Average across 6 nodes | `833.14 / 6` | ~138.86 GB/node provisioned |

**Correct interpretation:** this is a **single-table baseline calculation**. It excludes secondary indexes, lookup tables, audit logs, local snapshots/CDC, skew across nodes, and compaction/streaming spikes beyond assumed headroom. Never conclude "140 GB drives per node are definitely enough" from this calculation alone.

### 9.1. Adding an Index with a Measured Ratio

Suppose actual benchmarking of an index on this table yields **25% of base storage** (illustrative assumption):

```text
Base across RF:                   583.20 GB
Index across RF:  583.20 × 0.25 = 145.80 GB
Base + index:                     729.00 GB
Provisioned at 70%: 729 / 0.70  ≈ 1,041.43 GB DC-wide
6-node average:                 ≈ 173.57 GB/node
```

An index can raise baseline provisioned storage from ~833 GB to ~1,041 GB **in this hypothetical scenario**. If instead you add a small lookup table, size that lookup table and its RF **by the lookup table's actual row count**, rather than applying the index's 25% ratio.

### 9.2. Provisioning by DC and by Node

Total disk capacity never replaces per-node checks. In a 6-node DC with uneven data distribution, the fullest node can exceed the average. Your plan must:

- Watch **the fullest node's disk usage**, not just cluster averages.
- Budget for a node being down and data streaming during node replacement per agreed failure scenarios.
- Account separately for keyspaces/tables with different RFs or DCs with different RFs.
- Leave space for OS, commit logs, on-disk caches, snapshots, and non-SSTable files if sharing volumes.

### 9.3. MB and MiB Are Not Identical

In the examples above, **GB uses decimal units**:

```text
1 GB  = 1,000,000,000 bytes
1 GiB = 1,073,741,824 bytes
```

Commercial drives, operating systems, measurement tools, and dashboards may report GB or GiB differently. Always **state units explicitly** and never mix decimal and binary units in the same calculation.

## 10. Sizing Individual Partition Size and Hotness

Cluster-wide capacity may look comfortable while one hot device's partition grows too large. Suppose the heaviest device emits **25 events/second continuously**, at 900 B raw per event:

| Bucket | Rows in Bucket | Raw Data / Partition |
| --- | ---: | ---: |
| 1 minute | 1,500 | 1.35 MB |
| 1 hour | 90,000 | 81 MB |
| 1 day | 2,160,000 | 1,944 MB (~1.94 GB) |

If the table uses `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)`, all **2.16 million rows/day** for that device enter one logical partition; token hashing **does not split that partition** into 24 independent pieces.

Hourly buckets yield about **90,000 rows/partition** under these assumptions and raise partitions read for one calendar day from 1 to up to 24 hourly buckets. A 24-hour sliding window **can touch 25 hourly buckets** due to boundary misalignment. Smaller buckets shrink partitions, yet **fan-out, pagination, and long-range read costs rise**.

"81 MB raw" is not by itself good or bad. Measure:

- Largest partition by **row count, SSTable bytes, and tombstones**.
- Peak write rate to that partition and its replica set.
- p95/p99 latency for fetching latest items, range reads, and paging across buckets.
- Bucket width against product needs for multi-hour/multi-day history.

If even an hourly bucket runs too hot, consider a stable `shard_id` in the partition key, knowing full-hour reads must merge across shards. Sharding addresses load distribution—it **does not create free disk capacity**.

## 11. Forecasting Growth, Retention, and Operational Reserves

Capacity planning should not stop at today's snapshot. Evaluate scenarios:

| Scenario | Changed Assumption | Impact to Recalculate |
| --- | --- | --- |
| +50% devices | Higher events/sec if behavior holds | More rows/day, disk/network, possibly more nodes |
| Retention 30 → 90 days | Longer live retention | Steady-state live rows roughly triple, excluding tombstones |
| Avg payload 900 → 1,800 B | Events carry extra fields | Higher raw bytes; re-benchmark `S_disk` as compression shifts |
| Add lookup table for all events | Second representation per event | Extra table bytes, RF, mutations, and operational cost |
| Add SAI on selected columns | Added index structures | Measure index bytes, memory, and write amplification |
| Change RF in one DC | Add or remove replicas | Changes storage and streaming/repair overhead |
| Retain more snapshots | More copies / unreclaimed blocks | Budget local/backup reserves per policy |
| Backfill 100M old events | Write burst, affects TTL & compaction | Test ingest rate, quotas, and transient disk headroom |

### 11.1. Planning Formula by Table and DC

For each table `i` and datacenter `dc`:

```text
base_bytes_i = expected_live_rows_i × measured_bytes_per_live_row_i

dc_table_bytes_i =
    (base_bytes_i + measured_secondary_index_bytes_i)
    × RF_i,dc

dc_modeled_used_bytes =
    sum(dc_table_bytes_i)
    + estimated_expired_or_obsolete_bytes_not_yet_reclaimed
    + other_local_disk_usage_in_scope

dc_required_capacity ≈
    dc_modeled_used_bytes / target_disk_utilization
    + additional_reserve_not_covered_by_utilization_target
```

This is a **high-level planning model**, not an exact formula at every instant. "Expired/obsolete not yet reclaimed" should come from **TTL/compaction testing**, and never be double-counted if `measured_bytes_per_live_row` was measured at steady state and already reflects it. Clearly label what any additional reserve covers (compaction, streaming, snapshots, or growth) so you do not **double-count** against target utilization.

### 11.2. Avoid Forecasting Only by Cluster Totals

Build worksheets **per DC**, **per keyspace/table**, and with skew modeled for the **largest tenant/partition**. One node can fill up before others due to placement, topology, and uneven data. RF also raises resource demand during replica replacement after failures; sizing solely for averages does not ensure safety in degraded states.

There is no mandatory "70%" headroom rule for all Cassandra clusters. Target utilization must reflect disk type, compaction speed, repair/streaming times, node replacement speed, retention, and real operational procedures.

## 12. Java: Baseline Estimator Tool and Input Controls

A Java utility or internal script can compute baselines from **measured inputs**, avoiding error-prone manual math. The plain Java example below uses **decimal bytes**, guards selected `long` multiplications, and labels assumptions explicitly:

```java
import java.util.Locale;

public final class CassandraCapacityEstimate {
    private static final long SECONDS_PER_DAY = 86_400L;
    private static final double BYTES_PER_GB = 1_000_000_000d;

    public static void main(String[] args) {
        long averageEventsPerSecond = 100L;
        int retentionDays = 30;
        double measuredDiskBytesPerLiveRow = 750d;
        int replicationFactor = 3;
        int nodesInDc = 6;
        double targetUtilization = 0.70d;

        long rowsPerDay = Math.multiplyExact(
            averageEventsPerSecond, SECONDS_PER_DAY
        );
        long liveRows = Math.multiplyExact(rowsPerDay, retentionDays);

        // Measured footprint for one copy of base table, excluding secondary indexes.
        double oneCopyGb =
            liveRows * measuredDiskBytesPerLiveRow / BYTES_PER_GB;
        double replicatedGb = oneCopyGb * replicationFactor;
        double provisionedGb = replicatedGb / targetUtilization;
        double averageGbPerNode = provisionedGb / nodesInDc;

        System.out.printf(Locale.ROOT, "rows/day: %,d%n", rowsPerDay);
        System.out.printf(Locale.ROOT, "live rows: %,d%n", liveRows);
        System.out.printf(Locale.ROOT, "one copy: %.2f GB%n", oneCopyGb);
        System.out.printf(Locale.ROOT, "RF copies: %.2f GB%n", replicatedGb);
        System.out.printf(Locale.ROOT, "provisioned: %.2f GB%n", provisionedGb);
        System.out.printf(Locale.ROOT, "average per node: %.2f GB%n",
                          averageGbPerNode);
    }
}
```

Expected output for the example:

```text
rows/day: 8,640,000
live rows: 259,200,000
one copy: 194.40 GB
RF copies: 583.20 GB
provisioned: 833.14 GB
average per node: 138.86 GB
```

This is **not** a tool that measures a live Cassandra cluster; it computes strictly from supplied inputs. For inputs exceeding `long` range, `Math.multiplyExact` throws instead of silently overflowing. Production tools should also validate `targetUtilization > 0`, valid node/RF counts, growth scenarios, and per-DC/table/index breakdowns.

### 12.1. Measuring and Feeding Real Data into the Estimator

With DataStax Java Driver 4.x, an application can collect business-level telemetry on the write path (event counts, pre-write payload sizes, per-device/tenant distributions) and use prepared statements to target the right partitions. However, **the driver does not automatically know how many SSTable bytes an event occupies after compaction**.

To obtain reliable `measuredDiskBytesPerLiveRow`:

- Run a benchmark workload with the planned CQL tables, indexes, and TTLs.
- Use Cassandra metrics and operational tools such as `nodetool tablestats` and `nodetool tablehistograms` (exact syntax and metric sets vary by version) to observe disk usage, partition sizes, and latency.
- Measure SSTable/base/index sizes per node, sum cleanly over the right replica scope, and cross-check against flush/compaction state.
- Monitor `nodetool status` and per-node data distribution metrics; never treat a cluster-wide total as representative of the heaviest node.
- Never run unbounded `SELECT COUNT(*)` over billion-row production tables just to count rows for capacity planning.

Cassandra metrics reflect only the moment of measurement; record alongside them the **schema, RF, retention, compaction strategy, live row count, tombstone count, and load duration** so comparisons remain valid as the model evolves.

## 13. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Treating JSON/HTTP payload size as SSTable bytes | Misjudges overhead, compression, and indexes | Benchmark `S_disk` on real schema and workload |
| Multiplying `rows × size` and forgetting RF | Underestimates replicas and per-DC storage | Apply each DC's RF separately |
| Multiplying RF onto a cluster-wide `disk used` metric | Double-counts replicas | Document exact measurement scope |
| Omitting lookup/projection tables | Misses multiple representations of each event | Inventory all tables across all query shapes |
| Assuming indexes always add 25% or 100% | Over- or under-provisioning | Measure by column, version, cardinality, and workload |
| Assuming expired TTL immediately frees disk | Misses unreclaimed tombstones and SSTables | Measure steady-state compaction and budget headroom |
| Setting low `gc_grace_seconds` arbitrarily to save disk | Increases delete/resurrection risk in edge cases | Align repair, downtime, and safe grace policies |
| Picking buckets from average write rates | Hot devices create oversized, hot partitions | Measure per-key peaks, p99 payloads, and partition sizes |
| Summing DCs and dividing by total nodes | One DC runs out of disk early | Size RF, nodes, and headroom per DC |
| Filling 100% of disk with live data | No room for compaction, rebuilds, or streaming | Enforce evidence-based utilization targets and reserves |
| Confusing `LIMIT 50` with reading 50 physical cells | Tombstone/range scans remain expensive | Monitor tombstones scanned and read p99 |
| Linear forecasting during rapid ingestion growth | Runs short of capacity at period end | Model retention windows and growth curves |
| Treating a TTL-free test cluster as production-ready | Misses expiration churn and compaction load | Benchmark aged data with updates and deletes |

## 14. Capacity Validation Checklist

| Question | Required Evidence |
| --- | --- |
| Are all query-driven tables listed? | Mapping Q01–Qn → tables, indexes, row counts, and per-table retention |
| Are write rates known? | Average/peak across cluster, DC, tenant, and hottest key |
| How are payloads distributed? | Average/p95/p99/max bytes and compression behavior |
| Are real SSTable sizes measured? | Benchmark sample, `S_disk`, and clearly scoped index metrics |
| How long is data retained? | Write-time vs. event-time TTL, late arrivals, and backfills |
| Is RF calculated per DC? | NTS/RF, node count, placement, and single-node failure scenario |
| Is live data separated from tombstones/compaction? | Steady-state measurements and disk reserves |
| Are the hottest partitions bounded? | Rows/bytes/peak writes for planned buckets and shards |
| Is non-SSTable space budgeted? | Snapshots/backups/CDC, commit logs, OS, and streaming |
| Are growth scenarios modeled? | 3/6/12-month growth, retention, and schema changes |
| Are scaling/optimization thresholds set? | Alerts for node disk, compaction backlog, p99, and hot partitions |
| Are node-failure scenarios tested? | Repair/rebuild/streaming and recovery times measured |

## 15. Practice Exercise

A logistics platform records parcel scan events with columns:

```text
tenant_id, parcel_id, scan_id, scan_time, received_at,
location_id, status, payload
```

Assumed parameters:

| Parameter | Value |
| --- | ---: |
| Average rate | 250 events/second system-wide |
| Raw business payload | 1,200 B/event |
| Measured size of one base-table copy | 950 B/live row |
| Retention | 14 days from write time |
| RF | 3 in one DC |
| DC node count | 8 nodes |
| Target utilization | 65% |
| Extra lookup table | Potentially needed, not yet sized |
| Hottest single parcel rate | 15 events/second for several hours |

**Tasks:**

1. Calculate rows generated per day and approximate steady-state live rows after 14 days assuming steady rate.
2. Calculate raw size of one representation and single-copy base-table size using `950 B/row`.
3. Calculate total base-table footprint at RF=3, provisioned capacity at a 65% target, and average provisioned per node under ideal distribution.
4. If an added SAI measures 15% of the base table (assumption specific to this exercise), calculate the new capacity. Explain why 15% does not automatically apply to every index.
5. Propose partition/clustering keys for the API "view the 50 most recent scans for a parcel in a UTC hour." Calculate raw rows/bytes in an hourly vs. daily bucket for the hottest parcel. Which bucket merits benchmarking first?
6. List items the calculation above **excludes**: unreclaimed TTL-expired data, compaction, snapshots/CDC, lookup tables, growth, skew, and node-failure scenarios.
7. Explain the difference when retention changes from **14 days from write time** to **14 days from `scan_time`** for a scan uploaded three days late.

**Reference guidance:**

```text
250 × 86,400 = 21,600,000 events/day
21,600,000 × 14 = 302,400,000 live rows

Raw one representation:
  302,400,000 × 1,200 B = 362.88 GB

Base one copy:
  302,400,000 × 950 B = 287.28 GB
Base RF=3:
  287.28 × 3 = 861.84 GB
Provisioned at 65% target:
  861.84 / 0.65 ≈ 1,325.91 GB/DC
8-node average:
  1,325.91 / 8 ≈ 165.74 GB/node

If index adds 15% of base footprint:
  861.84 × 1.15 = 991.116 GB
  991.116 / 0.65 ≈ 1,524.79 GB/DC
  ≈ 190.60 GB/node

Hot parcel at 15 events/s:
  one hour = 54,000 events; raw ≈ 64.8 MB
  one day  = 1,296,000 events; raw ≈ 1,555.2 MB (~1.56 GB)
```

Hourly candidate: `PRIMARY KEY ((tenant_id, parcel_id, hour_bucket), scan_time, scan_id)` with descending clustering, where `hour_bucket` is the UTC start-of-hour timestamp. For an event arriving three days late, retention from `scan_time` leaves roughly **11 days** at write time instead of a full 14 days from write time.

## Conclusion

Cassandra capacity must be calculated **from query paths and write rates**, then converted through **live rows within retention**, **measured on-disk bytes per table/index**, **per-datacenter RF**, and **operational headroom**. TTLs, tombstones, compaction, repair, streaming, and uneven data distribution can push real usage far away from a naive `rows × raw bytes × RF` estimate. A sound forecast documents assumptions, avoids double-counting indexes or replicas, inspects the hottest nodes and partitions, and continuously calibrates against measurements on representative data.
