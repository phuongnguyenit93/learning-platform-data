# Key Cardinality, Data Skew, and Hotspots

In Apache Cassandra, the **partition key** determines which logical partition a row belongs to and which replica set is responsible for storing the data. When designing a wide-column table, simply picking a key "with many values" is not enough: you need to know **how values are distributed**, **how much data each value accumulates**, and **how many reads/writes each value receives**. These three factors determine whether the workload spreads evenly across the cluster or concentrates onto a few partitions and nodes.

**Cardinality** describes the number of distinct partition key values. **Skew** occurs when data or traffic is unevenly distributed across values. A **hot partition** is a partition receiving overly concentrated load; a **hot node** is a node bearing abnormally higher load than other nodes. These concepts are related, not interchangeable.

This lesson belongs to the **Keys and Partitions** chapter of the Apache Cassandra module. Understanding them helps you design query-driven tables, anticipate how replication and consistency affect load, diagnose performance failures, and build safe read/write paths from Java applications.

After this lesson, you will be able to:

- Compute and interpret the cardinality of simple and composite partition keys.
- Distinguish **storage/size skew**, **row-count skew**, and **access-frequency skew**.
- Explain why hashing/tokens do not automatically balance a workload containing "hot" keys.
- Recognize designs that cause hot partitions, large partitions, and fan-out queries.
- Choose time buckets, composite keys, or controlled sharding based on query requirements.
- Use CQL, metrics, and the Java Driver to inspect, mitigate hotspots, and handle retries.

## 1. What is partition key cardinality?

**Partition key cardinality** is the number of **distinct partition key values** present in the data at the point or period under consideration.

For example, a table has partition key `tenant_id` with four tenants having written data:

```text
tenant_id = acme
tenant_id = beta
tenant_id = gamma
tenant_id = delta

Cardinality(partition key) = 4
```

If a table has a composite partition key `(tenant_id, device_id)`, cardinality is the **number of distinct pairs**, not the number of tenants plus the number of devices:

```text
('acme', D1)
('acme', D2)
('beta', D1)
('beta', D3)
('gamma', D7)

Cardinality((tenant_id, device_id)) = 5
```

Two devices both carrying `D1` yet belonging to different tenants create **two partition keys**. Conversely, thousands of events with the same `('acme', D1)` still produce only **one partition key value**.

| Key | Possible cardinality | Primary risk |
| --- | --- | --- |
| `status` with values `NEW`, `PAID`, `CANCELLED` | Very low: at most a few values | Many rows/writes funnel into very few partitions. |
| `tenant_id` | Equals the number of active tenants with data | Large tenants can overwhelm small tenants. |
| `(tenant_id, user_id)` | Equals the number of distinct tenant–user pairs | Usually more distributed, though a super-hot user still creates a hotspot. |
| `(tenant_id, device_id, event_day)` | Equals the number of tenant–device–day combinations | Bounds history per day; today's partition can still run hot. |
| Unique `event_id` per event | Very high, roughly equal to event count | Spreads into many tiny partitions, but hard to read an entity's timeline. |

**High cardinality does not automatically equal a good model.** If every event becomes its own partition, queries like "the 100 latest events of a device" must locate and merge many partitions. Conversely, a low-cardinality key can be reasonable if data is small and every query targets one small value.

### Partition key cardinality differs from clustering column cardinality

Consider the table:

```sql
CREATE TABLE actions_by_status (
    status text,
    happened_at timestamp,
    action_id uuid,
    payload text,
    PRIMARY KEY (status, happened_at, action_id)
);
```

Even though `action_id` is virtually unique and `happened_at` has many distinct values, **only `status` is the partition key**. Millions of distinct `action_id`s do not raise partition key cardinality. They only create more clustering rows inside each `status` partition.

To form a two-column composite partition key, the syntax must include inner parentheses, such as `PRIMARY KEY ((tenant_id, user_id), happened_at, action_id)`.

## 2. High cardinality can still produce skewed data

Cassandra typically uses `Murmur3Partitioner` to map the **entire partition key** to a token. Tokens are distributed around the ring; the replication strategy determines which nodes hold replicas. Hashing distributes **different keys** by token, yet it does not split a **single partition key value** into multiple pieces across independent replica groups.

Suppose a system has 100 tenants. During one minute:

- Tenant `whale` sends **12,000 writes/second**.
- The remaining 99 tenants send **12,000 writes/second** combined.
- The table uses only `tenant_id` as the partition key.

Tenant `whale` represents **1% of key values** yet generates **50% of all writes**. If every write carries a different clustering key, they all go into **the exact same logical partition** for that tenant.

```text
100 partition keys
│
├── whale             : 12,000 write/s  (50% of total writes)
├── tenant-002 ...    : ~121 write/s per tenant if split evenly
├── tenant-003 ...
└── tenant-100 ...

Murmur3 distributes tokens, but does not split
partition 'whale' into 12,000 partition keys.
```

Adding more nodes helps the cluster hold more partition keys, but it does not guarantee stable handling of a single red-hot key. Likewise, raising the replication factor adds copies of the same partition rather than breaking it into smaller partitions.

### Three common types of skew

| Skew type | Symptom | Consequence |
| --- | --- | --- |
| **Data/size skew** | Some keys have far more rows or bytes than others | Large partitions; heavy compaction and repair/streaming cost. |
| **Write skew** | Some keys receive most INSERT/UPDATE/DELETE operations | Responsible replicas experience CPU, I/O, queue buildup, and SSTable write pressure. |
| **Read skew** | Some keys receive heavy SELECT traffic or wide range queries | High latency, cache/memtable/SSTable pressure, and network saturation on relevant replicas. |

A partition can be large yet rarely accessed, or tiny yet hammered by tens of thousands of queries/second. Therefore, measure **storage volume and traffic independently**.

## 3. Distinguishing hot partitions and hot nodes

A **hot partition** is tied to **a single partition key value** receiving heavy load or exceeding per-key resource budgets. A **hot node** is tied to a **server** bearing more load than it can handle.

```text
                           replication factor = 3
Hot key P ── token(P) ───> Replica A
                       ├> Replica B
                       └> Replica C
                               
Requests for P still concentrate on P's replica set.
```

A hot node can be caused by:

1. One hot partition on that node.
2. Multiple "moderately hot" partition keys happening to map onto overlapping token ranges/replica sets.
3. Replica placement and token/ring distribution poorly balanced relative to data volume.
4. Coordinator load, network, I/O, GC, compaction, or node hardware limits.

Do not look at high CPU on one node and immediately assume the partition key is skewed. Correlate keys/tables/queries with CPU, I/O, p95/p99 latency, pending compactions, and topology.

### How do replication and consistency interact?

With `replication factor = 3`, a normal write must be sent to the replicas responsible for the partition key. `consistency level` governs how many acknowledgments are needed to report success; it **does not change the partition key** and does not ensure other replicas do no related work.

- Increasing `RF` can improve fault tolerance and offer more read routing choices depending on topology, yet increases total replica count and does not divide a hot partition into multiple partitions.
- Choosing `LOCAL_ONE`, `LOCAL_QUORUM`, or another level adjusts consistency/latency/acknowledgment trade-offs; it is not a substitute for partition key design.
- Concentrated read/write activity on a key still must be measured on the involved replicas and coordinators rather than looking only at cluster-wide averages.

## 4. Key designs prone to hotspots

### 4.1. Partition key is a low-cardinality status

```sql
CREATE TABLE jobs_by_status (
    status text,
    created_at timestamp,
    job_id uuid,
    payload text,
    PRIMARY KEY (status, created_at, job_id)
);
```

If `status` only takes `PENDING`, `RUNNING`, and `DONE`, all jobs live in at most three logical partitions. `created_at` and `job_id` are clustering columns; having huge numbers of them creates zero additional partition keys.

This easily causes massive partitions and concentrated reads/writes when `PENDING` holds most active work.

### 4.2. Partition key is only tenant

```sql
CREATE TABLE events_by_tenant (
    tenant_id text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

If every tenant has very few events, this model can serve a "single-tenant timeline." Yet a tenant with many users or high event volume funnels everything into one partition. Never assume 10,000 tenants means 10,000 partitions with equal workload.

### 4.3. Composite partition key where one component has low dispersion

```sql
-- Data split by tenant and day:
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

Daily buckets bound historical accumulation inside each partition, but all events of tenant `whale` **during the current day** still hit a single partition key. Partition key count growing over time **does not reduce an active write hotspot within the day**.

### 4.4. Partition key is a unique timestamp or event ID

```sql
-- Nearly one partition key per event:
PRIMARY KEY ((tenant_id, event_id), occurred_at)
```

This yields high cardinality and can distribute writes well if IDs are well-spread. However, querying "the latest events of tenant T in an hour" is no longer a simple partition lookup. Reading across time ranges will require an additional access path or collecting many keys.

**Query-driven design principle:** do not "fix a hotspot" merely by shoving a random key into the partition key without a way to route and read the data.

## 5. Analyzing a scenario by data and load

An event collection system from devices has these requirements:

1. Fetch the latest events of **one device** in **one hour**.
2. Fetch an event timeline for an **entire tenant** over a short window.
3. Withstand writes from a large tenant with devices emitting bursts of events.
4. Retain data via TTL and support reads spanning multiple days.

From these requirements, you can design **multiple query-specific tables**, rather than forcing one table and one key to serve every goal.

| Query table | Suggested partition key | Clustering columns | Trade-off |
| --- | --- | --- | --- |
| Device history within an hour | `(tenant_id, device_id, hour_bucket)` | `occurred_at`, `event_id` | Extremely hot devices may need a smaller bucket. |
| Tenant-wide timeline per minute | `(tenant_id, minute_bucket, shard_id)` | `occurred_at`, `event_id` | Reads must fan out across shards and merge by timestamp. |
| Lookup one event by ID | `(tenant_id, event_id)` | Possibly none | Does not directly serve chronological timelines. |

Multiple tables can create **duplicated data**. To ensure business copies stay properly updated, the application needs clear write rules, retries, backfills, and reconciliation; writing to multiple tables does not automatically form an atomic cross-table/cross-partition transaction.

## 6. Reducing size with time bucketing

If data grows over time, include a bucket component in the partition key:

```sql
CREATE TABLE events_by_device_hour (
    tenant_id   text,
    device_id   uuid,
    hour_bucket timestamp,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

**Convention:** `hour_bucket` is the UTC hour start of `occurred_at`, e.g., event `2026-11-21T08:13:20Z` has `hour_bucket = 2026-11-21T08:00:00Z`.

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND occurred_at >= '2026-11-21T08:10:00Z'
  AND occurred_at <  '2026-11-21T08:20:00Z'
LIMIT 100;
```

Cassandra receives the full partition key and a clustering key slice. This is an appropriate access path for one device's history within an hour.

If the device receives **2,000 continuous writes/second during the current hour**, all 2,000 writes/second still hit **one partition key**; the hourly bucket only stops multiple hours from piling into one partition forever. In that case, a smaller bucket and/or controlled sharding is needed.

### Buckets must match traffic scale and read patterns

| Bucket granularity | Benefit | Cost |
| --- | --- | --- |
| Day | Fewer partitions to read for multi-day history | Each partition can hold heavy data and hot writes within one day. |
| Hour | Bounds each partition to one hour | Multi-day queries must read many buckets. |
| Minute | Shrinks size and duration a key receives writes | Long historical queries may require thousands of buckets. |

Day/hour/minute buckets are not universally "right" for every system. The decision must weigh **peak load**, **average bytes per event**, **frequent queries**, **latency budget**, and replica capacity.

## 7. Mitigating write hotspots with controlled sharding

When a tenant must write huge event volumes **within a single active bucket**, add `shard_id` to the partition key to produce multiple partitions distributable by token.

Example **tenant-wide per-minute** timeline table split across 12 shards:

```sql
CREATE TABLE tenant_events_by_shard_minute (
    tenant_id     text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

One stable way to choose a shard is hashing an event ID generated **once per business event**, then taking modulo by shard count:

```text
shard_id = floorMod(stableHash(event_id), 12)

Partition key =
    (tenant_id, minute_bucket, shard_id)

Examples:
  ('whale', 2026-11-21T08:30Z, 0)
  ('whale', 2026-11-21T08:30Z, 1)
  ...
  ('whale', 2026-11-21T08:30Z, 11)
```

If total write traffic for this tenant is **12,000 writes/second** and events distribute **nearly uniformly** across 12 shards, the ideal average target is about **1,000 writes/second/partition key** during the active minute. This is only an idealized estimate: per-shard load can skew, tokens can place shards on overlapping nodes/replicas, and 1,000 writes/second can still be a hotspot requiring real measurement.

Assuming each event carries **500 bytes of logical payload**:

```text
Rows per shard/minute
  ≈ 12,000 × 60 / 12 = 60,000 rows

Logical payload per shard/minute
  ≈ 60,000 × 500 B
  = 30,000,000 B ≈ 28.6 MiB
```

These figures exclude clustering keys, metadata, compression, tombstones, and replica overhead.

### Example CQL write to a shard

```sql
INSERT INTO tenant_events_by_shard_minute (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    '{"total":120}'
);
```

Here `7` is an **illustrative** shard. In the application, `shard_id` must be computed deterministically using the agreed algorithm; never alter the shard across retries.

### Reading one shard

```sql
SELECT occurred_at, event_id, event_type, payload
FROM tenant_events_by_shard_minute
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

To return the **100 latest events across the whole tenant in a minute**, the application must read shards `0` through `11`, **merge by `occurred_at DESC, event_id ASC`**, and take the first 100 rows. A query to `shard_id = 7` alone does not represent the entire tenant.

Deployment notes:

- Bound concurrent shard queries; excessive fan-out can shift read hotspots onto coordinators or the application.
- Synchronize **shard count, hash function, and bucket calculation** across all producers and readers.
- If changing shard count from 12 to 24, historical data **does not rebalance automatically**. Plan versioning, cutover timestamps, dual-reading old/new configurations, or migration.
- For "read one event by ID," you need the ID's shard **and** bucket, or an ID lookup table; knowing only the ID without the minute bucket prevents determining the timeline table's partition key.
- Never assume each shard sits on a separate node. Verify token placement and replica sets with real metrics.

## 8. When adding a composite key breaks query alignment

Many people see `(tenant_id, user_id, event_day)` has higher cardinality than `tenant_id` and assume every query will get faster. Yet CQL requires **all components** to select a partition key:

```sql
CREATE TABLE user_events_by_day (
    tenant_id   text,
    user_id     uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        occurred_at,
        event_id
    )
);
```

Matching query:

```sql
SELECT occurred_at, event_id, payload
FROM user_events_by_day
WHERE tenant_id = 'acme'
  AND user_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 50;
```

Query **not specifying the full partition key**:

```sql
-- Only tenant is known; user_id and event_day are missing:
SELECT *
FROM user_events_by_day
WHERE tenant_id = 'acme';
```

Without a supporting index or auxiliary structure, Cassandra typically rejects this broad query; `ALLOW FILTERING` may enable certain cases at the risk of huge scans. To fetch a tenant-wide timeline, design a separate query table like `tenant_events_by_shard_minute` or a dedicated aggregation strategy.

**Raising cardinality aids key distribution, yet can raise multi-key query cost.** Balance partitions read, per-partition size, and replica load.

## 9. Reading data distribution and hotspots from metrics

Do not infer skew solely from the row count returned by `SELECT LIMIT 20`. Cassandra may hold millions of rows in that partition, and reading 20 rows reveals nothing about total bytes.

### Metrics to monitor

| Metric group | Detection hint |
| --- | --- |
| **Partition size histogram / maximum** | A few partitions occupy far more bytes than the rest. |
| **Cell count histogram** | A few partitions have huge cell/clustering row counts. |
| **Read/write latency p95, p99; timeouts** | Workload is slow or suffering high tail latency. |
| **Per-table read/write volume** | Identify the heavy table before drilling down to partition keys. |
| **Top keys / per-partition-key request analysis** | Certain partition keys account for an abnormal share of requests. |
| **Per-node CPU, disk I/O, GC, network** | Check hotspots at the replica/coordinator layer. |
| **SSTables per read, tombstones scanned** | Distinguish large data from read amplification due to SSTables/tombstones. |
| **Pending compactions, streaming/repair load** | Background work may create or amplify read/write slowdowns. |

Depending on your Cassandra version, start with:

```bash
nodetool tablestats my_keyspace.tenant_events_by_shard_minute
nodetool tablehistograms my_keyspace tenant_events_by_shard_minute
```

Results depend on the Cassandra version and queried node; histograms/statistics are not exact instantaneous counts of **every** live partition. Some Cassandra releases offer commands or sampling for heavily read/written partition keys (such as `nodetool toppartitions`); verify syntax and availability for your running version.

When diagnosing per-key traffic spikes, the application can emit **non-sensitive** metrics grouped by bucket or normalized key group. Avoid putting raw user IDs as high-cardinality metric labels in monitoring systems: telemetry itself can get overloaded. Use sampling, heavy-hitter tracking, truncated hashes, or tenant/shard aggregation, then investigate selectively.

### A repeatable diagnostic workflow

1. Confirm the **symptom**: which table/query is slow, when it happens, and the timeout rate.
2. Check **node imbalance**: are only a few replicas or coordinators hitting high CPU/I/O/network?
3. Check **size and cells**: are there large partitions or anomalous distribution tails?
4. Check **access skew**: which partition keys dominate reads/writes?
5. Cross-check **schema and `WHERE`**: do queries supply the full partition key, proper clustering ranges, and sensible `LIMIT`/paging?
6. Inspect **TTL, tombstones, compaction, repair** to rule out secondary or compounding causes.
7. Benchmark **new buckets/shards** on a representative workload and compare p95/p99, replica load, partitions read, and storage cost.

**Never run `SELECT COUNT(*)` across massive partitions to measure skew in production.** Query-based counting adds heavy load; prefer metrics, histograms, write-stream telemetry, and controlled sampling.

## 10. Rules for choosing a partition key that balances load and read performance

A good design does not blindly maximize cardinality. Evaluate four questions:

1. **Query:** which values does the application know to identify one partition key? Does it frequently query "entire tenant" or only "one user/device"?
2. **Size:** over the retention window, how many rows/cells/bytes is one partition expected to hold under average and **peak** load?
3. **Frequency:** how many requests/second can a single key receive? How far does the maximum diverge from the median?
4. **Fan-out:** after adding buckets or shards, how many partitions must one business query read and merge?

| Symptom | Design change to consider |
| --- | --- |
| Very few partition keys, each with many rows | Add entity or bucket to the partition key if aligned with queries. |
| Many partition keys, yet a few keys run hot | Controlled sharding, load shedding, or changing the write path; verify read fan-out. |
| Unbounded data growth over time | Time bucketing, TTL, and data lifecycle rules. |
| One partition per event; timeline queries must read many keys | Group by entity/bucket and order with clustering columns. |
| Many queries missing partition key components | Design another query-driven table or appropriate index, rather than broad filtering. |
| Daily bucket still runs too hot during peak hours | Hourly/minute buckets, sharding, and/or rate limiting; measure replica load. |

For time-series data with TTL, evaluate `TimeWindowCompactionStrategy` on compatible versions and write patterns. Compaction and repair **do not alter partition keys**, so they are storage/operational optimizations, not a way to automatically split a hot partition.

## 11. Deterministic shard writes from a Java application

The example below uses **Java Driver 4.x**, assuming `CqlSession` is connected to a keyspace containing `tenant_events_by_shard_minute`. The application selects among 12 shards based on an `eventId` generated **once before sending**. Retries of the same event must keep the exact same `eventId` and `occurredAt`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventWriter {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;

    public TenantEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_shard_minute " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public void writeEvent(
            String tenantId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        Instant bucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, bucket, shardId, occurredAt,
            eventId, eventType, payload
        ));
    }
}
```

In this example, `eventId.hashCode()` is a **deterministic** UUID hash in Java, mapped into `0..11` via `floorMod`. It serves strictly to illustrate sharding across Java services sharing the same convention; in polyglot systems, define an explicit byte-level hash algorithm and version so every producer/consumer yields identical results.

Operational rules:

- Fix the hash algorithm and `SHARD_COUNT` for written data. If changed, retain the **old rule** for historical reads or migration.
- If the same event is retried with a new ID, new timestamp, or new bucket, data may land in another partition and create a logical duplicate.
- Standard Cassandra `INSERT` has **upsert** semantics on the **full primary key**. Stability of both shard **and** clustering columns ensures retries hit the same row.
- Writing to one timeline table does not create an atomic transaction with other lookup or summary tables. Handle partial failure cases explicitly.
- The Java Driver can leverage token-aware routing from prepared statements when all partition key components are bound; monitor load balancing, timeouts, consistency, and backpressure instead of raising concurrency indefinitely.

### Reading a tenant-wide timeline in one minute

```text
Compute minute_bucket from the requested timestamp
              |
              v
Read shards 0..11 (with bounded concurrency)
              |
              v
Each shard returns rows in occurred_at DESC, event_id ASC
              |
              v
Merge 12 streams using the same comparator
              |
              v
Select the 100 latest events across the tenant
```

To return the **global top 100**, reading up to the first 100 rows **from each shard** suffices not to miss any top-100 row, provided the same comparator is used and queries cover the exact time window. However, that can read up to 1,200 rows, so production systems can use page-by-page merging, fetching further only as needed and bounding parallel queries.

Do not apply `ORDER BY` expecting Cassandra to globally sort across 12 partition keys. Clustering order holds strictly within each partition.

## 12. Practice scenario

An e-commerce service has 500 stores. The initial table uses:

```sql
CREATE TABLE sales_by_store (
    store_id uuid,
    sold_at timestamp,
    sale_id uuid,
    amount decimal,
    PRIMARY KEY (store_id, sold_at, sale_id)
);
```

During peak hours:

- 499 small stores average **2 transactions/second/store**.
- One large store has **5,000 transactions/second**.
- Assumed logical payload per transaction is **400 bytes**.
- Primary read goal: "50 latest transactions of a store."
- Secondary read goal: "all transactions within a chosen 15-minute window of a store."

**Questions:**

1. What is the partition key cardinality of the current table, assuming all 500 stores have data?
2. What is the approximate total write rate? What percentage comes from the large store?
3. Does token hashing automatically split the large store's 5,000 transactions/second across multiple partition keys?
4. Keeping one partition key per store, after 1 hour how many rows and how much logical payload does the large store have?
5. Does adding an hourly bucket reduce the **write hotspot within the current hour**?
6. Suppose 10 shards are added with ideal uniform distribution; roughly how many writes/second does each shard receive?
7. How must the "50 latest transactions" query change if transactions are spread across 10 shards?
8. Which metrics should be monitored to prove the sharded approach is actually better?

**Answers with explanations:**

1. **500 partition keys**, because `store_id` is a simple partition key.
2. Total `499 × 2 + 5,000 = 5,998 writes/second`; the large store accounts for roughly **83.4%**.
3. **No.** All events sharing `store_id` land in one logical partition and the same replica set, regardless of having many clustering keys.
4. `5,000 × 3,600 = 18,000,000 rows`; payload `18,000,000 × 400 = 7,200,000,000 bytes ≈ 6.71 GiB`, excluding overhead, compaction, compression, and replicas.
5. **Not guaranteed to reduce current load.** Hourly buckets only separate different hours; records in the **same hour** still hit one partition.
6. Ideally **500 writes/second/shard**; real load may skew and replica sets may overlap.
7. Read all shards of the relevant bucket, merge results by timestamp and ID, and take the top 50; also handle the preceding bucket if the first page yields fewer than 50 records.
8. Partition size/cell histograms, top keys and per-shard write distribution, p95/p99 latency, timeouts, CPU/I/O, compaction backlog, and read fan-out cost.

This exercise shows that increasing cardinality from 500 to many partition keys via buckets and shards **only helps when the workload truly distributes well** and critical query paths remain served at acceptable cost.

## 13. Design and operations checklist

Whenever you notice data skew or hotspots, check:

1. **Which columns** actually form the partition key? Read the parentheses in `PRIMARY KEY` carefully.
2. Is cardinality measured at the **tenant, device, user, bucket, shard** level, or across the entire partition key tuple?
3. Are row/byte counts and traffic **per key** heavily skewed, especially at p95/p99/max?
4. Are the large keys also the hot keys, or are there two separate incidents to address?
5. Will adding buckets or shards cause **each query to read too many partitions**, and how must results be merged?
6. Does the application preserve **stable IDs, buckets, and shards on retries**?
7. Do replication/consistency levels, topology, and node limits match the traffic and latency targets?
8. Do before/after metrics prove reduced replica load and improved p95/p99, not merely a lower average partition size?

**Remember:** high cardinality provides **more keys to distribute**, while hashing only decides where each key lands. Actual balance depends on **traffic and data volume per key**. A sound Cassandra model balances data splitting, query read cost, replication strategy, and compaction/repair operability, while allowing Java applications to write and retry consistently.
