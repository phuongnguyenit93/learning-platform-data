# Bucketing by Time or Data Domain

In Apache Cassandra, the **partition key** determines which logical partition data belongs to and which replica set serves that partition. If a partition key accumulates too many rows, cells, or bytes, the partition can become a **large partition**; if a key receives most of the traffic in a short window, it can become a **hot partition**. An important wide-column table design technique for controlling both risks is **bucketing**: adding one or more rule-based grouping components to the partition key.

There are two main approaches:

- **Time bucketing:** grouping data into windows of days, hours, minutes, or a defined interval. For example, each `(device_id, event_day)` pair is one partition.
- **Data domain bucketing:** grouping by business entity or scope such as tenant, customer, service, device, region, or order type. For example, each `(tenant_id, device_id)` pair is one partition. When a single domain still gets overloaded, an **artificial shard/bucket** computed deterministically from the event identifier can be added.

Both approaches can be **combined**. However, bucketing is not merely a trick to create more partition keys: it changes **valid CQL queries**, the number of partitions that must be read, how results are ordered, and routing logic in Java applications. Choosing buckets must start from primary queries, data distribution, and actual load.

This lesson belongs to the **Keys and Partitions** chapter, connecting with Cassandra's distributed architecture, replication, consistency levels, TTL, compaction, error handling, and access from Java.

After this lesson, you will be able to:

1. Explain the goals of time buckets, domain buckets, and artificial shards.
2. Define CQL schemas with composite partition keys to bound row counts and bytes per partition.
3. Estimate bucket size from write rate, payload, and retention period.
4. Execute range queries within one bucket, handle queries spanning multiple buckets, and merge results.
5. Recognize when bucketing does not yet solve a write hotspot or causes excessive fan-out.
6. Design consistent bucket calculation algorithms across writers, readers, and retries from Java.

## 1. Bucketing is part of the partition key, not an automatic Cassandra feature

Consider a table storing device events:

```sql
CREATE TABLE events_by_device_all_time (
    tenant_id   text,
    device_id   uuid,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

The partition key is `(tenant_id, device_id)`, while `event_time` and `event_id` are clustering columns. Every event for a device in the same tenant accumulates into **one logical partition**, even if written years apart.

```text
Partition ('acme', device-A)
  2026-11-21 10:05  event-104
  2026-11-21 10:00  event-103
  2026-11-20 09:00  event-102
  2026-11-19 07:00  event-101
  ...
  2024-01-01 00:00  event-001
```

Cassandra does not automatically create a new partition when `event_time` crosses into the next day; clustering columns **do not participate in token calculation**. To split data by day, you must put `event_day` into the **partition key** and compute this column value at write time:

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    event_time,
    event_id
)
```

Then `('acme', device-A, 2026-11-20)` and `('acme', device-A, 2026-11-21)` are **two different partition keys**. Each key is hashed separately to determine its token and replicas. You cannot use `CLUSTERING ORDER BY` or `LIMIT` alone to achieve equivalent partition splitting.

### Bucket classification

| Splitting approach | Typical partition key components | Goal | Trade-off |
| --- | --- | --- | --- |
| By time | `(device_id, event_day)` | Bound history in each partition | Multi-day queries must read multiple partitions. |
| By business domain | `(tenant_id, device_id)` | Separate data by entity already known to queries | Very large/hot entities still create large/hot partitions. |
| By domain + time | `(tenant_id, device_id, hour_bucket)` | Bound each device within each hour | Queries across many devices/hours need fan-out. |
| By domain + time + shard | `(tenant_id, service_id, minute_bucket, shard_id)` | Split load of an extremely hot entity within the same time window | Readers must know or scan the relevant shards. |
| Non-temporal artificial bucket | `(tenant_id, shard_id)` | Spread many objects belonging to one domain | Needs routing logic and merging when reading the whole domain. |

**Terminology note:** "data domain bucketing" here refers to splitting along **business boundaries** (tenant, device, service, category, etc.), not using `token()` to slice token ring ranges. Artificial sharding is a separate technique when natural business boundaries do not sufficiently distribute load.

## 2. Designing a time bucket

Suppose an application needs to:

- Read the latest measurements of a device **within a day**.
- Read the time interval `[08:00, 09:00)` for that device.
- Retain data according to retention policy without letting one partition grow endlessly.

We design:

```sql
CREATE TABLE readings_by_device_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    measured_at timestamp,
    reading_id  uuid,
    temperature double,
    humidity    double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        measured_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (measured_at DESC, reading_id ASC);
```

In this table:

- `(tenant_id, device_id, event_day)` is the **entire partition key**.
- `measured_at` determines event ordering within the partition; `reading_id` distinguishes measurements sharing the same timestamp.
- `event_day` should be computed by an **agreed rule**, such as the UTC date of `measured_at`.
- The day column is **routing data**, not a column used for global sorting across multiple partitions.

### Writing data into the right day

```sql
INSERT INTO readings_by_device_day (
    tenant_id, device_id, event_day,
    measured_at, reading_id, temperature, humidity
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:35:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    37.9,
    65.0
);
```

The same device writing an event on `2026-11-22` will have a different partition key because `event_day` differs.

### Querying one bucket

```sql
SELECT measured_at, reading_id, temperature, humidity
FROM readings_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

CQL has the **full partition key**, so Cassandra knows which partition to read; the two range predicates constrain the first clustering column. Default order remains `measured_at DESC`. Writing half-open intervals `[start, end)` prevents adjacent ranges from both including a record sitting on the exact boundary.

### Querying across two days

A request from `2026-11-21T23:30:00Z` to before `2026-11-22T00:30:00Z` spans two partition keys:

```text
Bucket 2026-11-21:
  [2026-11-21T23:30:00Z, 2026-11-22T00:00:00Z)

Bucket 2026-11-22:
  [2026-11-22T00:00:00Z, 2026-11-22T00:30:00Z)
```

The application queries each partition and then **merges by `measured_at` and `reading_id`** if a unified timeline is needed. `CLUSTERING ORDER BY` only guarantees order **inside one partition**, not global order across multiple days.

## 3. Choosing time bucket duration: minute, hour, or day?

Longer buckets mean each partition holds more data while historical queries read fewer partition keys. Shorter buckets keep rows/bytes per partition smaller, at the cost of more queries and partition metadata.

### Estimating from workload

Suppose a device writes an average of **50 events/second**, each event having **400 bytes of logical payload**, excluding clustering keys, metadata, tombstones, or compression.

| Bucket duration | Estimated event count | Estimated logical payload |
| --- | ---: | ---: |
| 1 minute | 3,000 | 1.2 MB (around 1.14 MiB) |
| 15 minutes | 45,000 | 18 MB (around 17.2 MiB) |
| 1 hour | 180,000 | 72 MB (around 68.7 MiB) |
| 1 day | 4,320,000 | 1,728 MB (around 1.61 GiB) |

This is a **payload estimate**, not exact SSTable size. Real usage is affected by column/cell count, keys, compression, collections, tombstones, TTL, and compaction. With `replication factor = 3`, the cluster maintains three copies per replication strategy, yet you cannot multiply the payload figure by three and treat that as exact disk size.

**Initial planning formula:**

```text
rows_per_bucket ≈ events_per_second × bucket_seconds
logical_payload ≈ rows_per_bucket × average_payload_bytes

Example: 50 events/s × 900 s × 400 bytes
      = 18,000,000 bytes payload per 15-minute bucket
```

Also account for:

1. **Traffic peaks:** do any devices emit 5,000 events/second instead of 50?
2. **Skew level:** how many tenants/devices account for most data?
3. **Update/delete counts:** do frequent overwrites or TTL expirations inflate tombstones?
4. **Read pattern:** do users normally view 5 minutes or 30 days?
5. **Latency targets:** can query p95/p99, streaming speed, repair, and compaction keep up?

There is no "bucket under X MB" threshold valid for every Cassandra version and every cluster. Choose buckets using load tests and operational metrics, not merely tidy average row counts.

## 4. Data domain bucketing

Time is not the only boundary. Many applications have **business domains** that queries routinely know upfront: customer, device, tenant, order, warehouse, or service.

For example, an application storing the state of each device within a tenant:

```sql
CREATE TABLE device_state_by_tenant_and_id (
    tenant_id       text,
    device_id       uuid,
    device_name     text,
    firmware        text,
    last_heartbeat  timestamp,
    PRIMARY KEY ((tenant_id, device_id))
);
```

The pair `(tenant_id, device_id)` isolates each device into a single-row logical partition. This is **business-domain partition key** selection: an application looking up a device knows both tenant and device.

```sql
SELECT device_name, firmware, last_heartbeat
FROM device_state_by_tenant_and_id
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Unlike using only `tenant_id`, this avoids piling all devices of tenant `acme` into **one partition**. However, it also does not directly support "list all devices of a tenant" using only `tenant_id = 'acme'`. You need **a table serving tenant-listing queries** or an appropriate indexing mechanism.

### A domain bucket example for per-service events

Suppose a tenant runs many microservices. If the system queries logs **per service**, you can use:

```sql
CREATE TABLE service_logs_by_day (
    tenant_id   text,
    service_id  text,
    event_day   date,
    logged_at   timestamp,
    log_id      uuid,
    log_level   text,
    message     text,
    PRIMARY KEY (
        (tenant_id, service_id, event_day),
        logged_at,
        log_id
    )
) WITH CLUSTERING ORDER BY (logged_at DESC, log_id ASC);
```

The table combines **domain** (`tenant_id + service_id`) and **time** (`event_day`). On the same day, logs of service `auth` and `billing` belong to **two different logical partitions**; on a new day, each service gets a fresh bucket.

**Note:** adding `service_id` only distributes well if services generate reasonably balanced traffic. If `auth` creates 95% of a tenant's logs, partition `('acme', 'auth', today)` can still become very large or hot.

### When the data domain is category, status, or region

A **low-cardinality** business boundary can make partitions even worse:

```sql
-- All ACTIVE orders go into the same partition key:
PRIMARY KEY (status, created_at, order_id)

-- One large region holds all events for the day:
PRIMARY KEY ((region, event_day), occurred_at, event_id)
```

If `status` only has 3 values, or region `asia` handles 90% of traffic, that is a **low-cardinality or skewed** partition key. Being a "domain bucket" does not guarantee balance.

Pick components that **match primary queries** and evaluate distinct value counts, row/byte concentration, and read/write rates per value.

## 5. Combining domain and time buckets for wide-column data

A historical table often needs both criteria:

- **Domain:** reading by a specific device or customer.
- **Time:** bounding history volume within each partition.

Example:

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id     text,
    customer_id   uuid,
    month_bucket  text,
    ordered_at    timestamp,
    order_id      uuid,
    total_amount  decimal,
    status        text,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
```

The application defines `month_bucket` formatted as `YYYY-MM` computed from `ordered_at` in UTC, e.g., `2026-11`. This is a monthly bucket example; `text` makes the bucket code human-readable, though the application must enforce **formatting and month increment/decrement math**.

Querying one customer in a month:

```sql
SELECT ordered_at, order_id, total_amount, status
FROM orders_by_customer_month
WHERE tenant_id = 'acme'
  AND customer_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND month_bucket = '2026-11'
LIMIT 30;
```

To query "all orders of the tenant in a month," this table does not fit a primary-key access path because `customer_id` is missing. Cassandra does not treat the `tenant_id` prefix of a composite partition key as an ordered index across all customers.

You may need another table for that read path, such as `orders_by_tenant_day_shard`, or a tenant summary table. Writing to multiple tables must pair with retries, data checks, and **partial failure** handling, without assuming atomic multi-partition transactions.

## 6. Artificial buckets when a domain or time bucket still runs hot

Domain bucketing and time bucketing mainly change **data grouping and lifecycle**. They do not necessarily solve **an active group receiving too many writes**.

Suppose the `ingest` service of tenant `whale` receives 12,000 events/second. Even with partition key `(tenant_id, service_id, event_day)`, **12,000 writes/second** still hit the **same daily partition**. You can add `shard_id` to the partition key so multiple partitions coexist inside one time bucket.

```sql
CREATE TABLE service_events_by_minute_shard (
    tenant_id     text,
    service_id    text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, service_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Suppose there are **12 shards**. Producers assign a shard using a stable hash of `event_id`:

```text
shard_id = floorMod(stableHash(event_id), 12)

Partition keys in minute 08:30 UTC:
  ('whale', 'ingest', 08:30, 0)
  ('whale', 'ingest', 08:30, 1)
  ...
  ('whale', 'ingest', 08:30, 11)
```

Under ideal distribution, each shard receives about `12,000 / 12 = 1,000` writes/second. At `500 bytes payload/event` and a 60-second bucket, each shard receives roughly `60,000` rows and `30 MB` of logical payload per minute, excluding overhead, replicas, and compaction.

**There is no guarantee** the 12 shards sit on 12 distinct nodes or have strictly equal load: tokens can map to overlapping replica sets, workload can skew, and nodes also serve many other partitions.

### Writing an event using the computed shard

```sql
INSERT INTO service_events_by_minute_shard (
    tenant_id, service_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    'ingest',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'accepted',
    '{"bytes":500}'
);
```

`shard_id = 7` is an **illustrative** value; in production it must come from the shared event routing algorithm. When retrying the same event, use **the exact same `event_id`, `occurred_at`, bucket, and shard** to write to the same full primary key.

### Reading one shard

```sql
SELECT occurred_at, event_id, event_type
FROM service_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND service_id = 'ingest'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

To read the entire service in this minute, the application must read **all relevant shards**. If the requirement is "top 100 latest events across the service," perform a sorted merge using the same comparator `occurred_at DESC, event_id ASC`, then take the first 100 rows. Cassandra `ORDER BY` does not sort globally across 12 partition keys.

## 7. Fan-out cost and limits of bucketing

**Fan-out** means a single business query must read multiple partition keys. Making buckets smaller bounds data per partition while increasing query count.

For example, reading **24 hours** of data for **one service**:

| Design | Theoretical partition keys to read |
| --- | ---: |
| Daily bucket, no shard | 1–2 daily buckets, depending on time boundaries |
| Hourly bucket, no shard | 24–25 hourly buckets, depending on boundaries |
| Minute bucket, no shard | 1,440–1,441 minute buckets |
| Minute bucket with 12 shards | 17,280–17,292 partition keys |

This table assumes data is queried over a continuous 24-hour span and the application has no secondary index to skip empty buckets. Counts reflect buckets intersecting the time window; exact counts depend on whether start/end align with boundaries and half-open interval semantics.

This is why **the smallest bucket is not always best**. A system may need separate tables for:

- Looking up the 100 most recent events.
- Reading one hour of events for a service.
- 30-day aggregate reporting.
- Direct lookup of one event by `event_id`.

### Pagination and merging in the application

When multiple partitions must be read:

1. Build the list of buckets/shards following the routing rules.
2. Query in parallel with **bounded concurrency**; never fire tens of thousands of concurrent queries.
3. Read each partition in clustering order with an appropriate row/page limit.
4. Merge result streams using an explicit comparator (timestamp + ID) before paginating the API response.
5. Track **paging state** per stream or a proper cursor strategy so rows sharing a timestamp are never dropped.
6. Never assume `LIMIT 100` per shard equals `LIMIT 100` across the combined result.

**Note:** to find the global top 100 under the same comparator, reading up to the first 100 elements from each involved shard/bucket is sufficient for correctness of order, though it can over-read many rows. Page-by-page merging lowers cost in real applications.

## 8. Bucket calculation must stay consistent with event time and time zone

A classic bug is having the producer compute `event_day` in UTC while the reader uses Vietnam local time, or having retries use **current wall-clock time** instead of the original event timestamp.

Example event:

```text
occurred_at = 2026-11-21T23:30:00Z

In UTC:            event_day = 2026-11-21
In UTC+07:         calendar date = 2026-11-22

If the writer writes to the UTC day partition,
and the reader queries the UTC+07 day partition
=> the event may not be found even though it was written.
```

Therefore, standardize:

- Whether buckets are derived from **event time**, **ingestion time**, or another business timestamp.
- The canonical time zone (typically UTC for cross-service data).
- Truncation rules: start of minute/hour/day in the chosen time zone.
- Read intervals using `[start, end)` for non-overlapping boundaries.
- Policies for late-arriving events, device clock skew, backfills, and timestamp corrections.
- Idempotency key and full primary key must stay **stable across retries**.

If an event arrives two days late while buckets are computed from `occurred_at`, it must still be written into the bucket of its event timestamp. This can affect compaction strategies for time-series data; never silently switch it to "today's" bucket merely because the write happened today.

## 9. Can TTL, compaction, and replication replace bucketing?

No. They solve different layers of the problem.

### TTL

Data can be written with a TTL, e.g., 7 days:

```sql
INSERT INTO service_events_by_minute_shard (
    tenant_id, service_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale', 'ingest', '2026-11-21T08:30:00Z', 7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'accepted', '{"bytes":500}'
) USING TTL 604800;
```

`604800` is 7 days in seconds. TTL expires cells after that duration from write time per TTL semantics; it does **not** automatically split buckets into more partition keys. Expired data can leave tombstones and is only purged from SSTables once safety conditions are met via compaction.

Notably: for late-arriving events, `USING TTL 604800` keeps data for 7 days **from write time**, not necessarily 7 days **from business event time**. If retention policy is based on event time, design TTL/lifecycle accordingly rather than assuming the two timestamps match.

### Compaction

`TimeWindowCompactionStrategy` (TWCS) is often considered for append-mostly time-series data with TTL and aligned write windows. However, TWCS:

- Does not fix the partition key or split an oversized partition automatically.
- Can be impacted by late-arriving data, updates/deletes to old data, and uneven TTLs.
- Must be validated against real workloads and Cassandra versions.

### Replication, consistency, and repair

- The complete partition key is hashed to a token; the replication strategy selects the replica set.
- `replication factor` adds copies; it does **not** break up a hot partition.
- Consistency levels govern acknowledgment/read requirements; they do not make a query missing its partition key efficient.
- Repair synchronizes data across replicas; it does not change how data is bucketed.

Switching from daily to hourly buckets or adding shards alters the **primary key model**; it normally requires creating a new table, migrating read/write traffic, and planning for legacy data.

## 10. Java Driver: computing buckets by time and data domain

The Java Driver 4.x example below writes events into `service_events_by_minute_shard`. `tenantId` and `serviceId` form the **domain bucket**. `minuteBucket` is computed from `occurredAt` in UTC, and `shardId` comes from a deterministic hash of `eventId`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class ServiceEventRepository {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement selectByBucketAndShard;

    public ServiceEventRepository(CqlSession session) {
        this.session = session;

        this.insert = session.prepare(
            "INSERT INTO service_events_by_minute_shard " +
            "(tenant_id, service_id, minute_bucket, shard_id, " +
            "occurred_at, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );

        this.selectByBucketAndShard = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM service_events_by_minute_shard " +
            "WHERE tenant_id = ? AND service_id = ? " +
            "AND minute_bucket = ? AND shard_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ? " +
            "LIMIT 100"
        );
    }

    public void writeEvent(
            String tenantId, String serviceId,
            Instant occurredAt, UUID eventId,
            String eventType, String payload) {

        Instant bucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shard = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, serviceId, bucket, shard,
            occurredAt, eventId, eventType, payload
        ));
    }

    public com.datastax.oss.driver.api.core.cql.ResultSet readOneShard(
            String tenantId, String serviceId, Instant bucket,
            short shard, Instant startInclusive, Instant endExclusive) {

        Instant bucketEnd = bucket.plus(1, ChronoUnit.MINUTES);

        if (startInclusive.isBefore(bucket) ||
            !startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Read range must belong to one UTC minute bucket");
        }

        return session.execute(selectByBucketAndShard.bind(
            tenantId, serviceId, bucket, shard,
            startInclusive, endExclusive
        ));
    }
}
```

### What to control in the application

1. `eventId` must be generated **once per business event**, never regenerated on retries.
2. `occurredAt`, `minuteBucket`, and `shard` must stay stable across retries; if any primary key component changes, Cassandra can create **another row**.
3. In the example, `UUID.hashCode()` is a deterministic hash in Java. Polyglot systems should specify an exact byte-level hash algorithm and versioning rather than relying on per-runtime method behavior.
4. `SHARD_COUNT` is part of the storage contract. Changing 12 to 24 **does not automatically move already-written data**; readers must know the config applicable to older buckets or perform a migration.
5. `PreparedStatement` objects are reused. Binding the full partition key lets the driver compute routing keys when cluster metadata permits.
6. Single-shard queries only read one partition; when an API needs the whole service or multiple minutes, the service layer must **plan fan-out**, bound concurrency, and merge results.
7. A client timeout does not prove the prior operation was not applied. Reuse the exact same key and payload on retries; if overwrites must be forbidden, evaluate scoped conditional writes/LWT rather than treating upserts as "exactly once" business transactions.

This snippet is synchronous to keep routing clear. Under high throughput, use the asynchronous driver with backpressure and sound retry policies instead of spawning unbounded parallel requests.

## 11. Operating and measuring bucketing effectiveness

After bucketing, you need to verify that each partition is **smaller or less hot**, while business queries still meet SLOs.

| Metric group | Question to answer |
| --- | --- |
| **Partition size histogram / max** | Do any buckets still exhibit huge byte counts? |
| **Cell count / rows per partition** | Are cell and clustering row counts controlled at peak load? |
| **Top read/write partition keys** | Is an open bucket or a single shard taking most of the load? |
| **Latency p95/p99, timeouts** | Did latency improve for both primary reads and writes? |
| **CPU/I/O/GC/network on replicas** | Is load better balanced across nodes? |
| **SSTables per read, tombstones** | Is TTL/deleted data causing read amplification? |
| **Partition lookups per API request** | Do small buckets cause excessive fan-out and raise query cost? |
| **Compaction/repair/streaming backlog** | Can background work finish within operational budgets? |

Common tools, depending on Cassandra version:

```bash
nodetool tablestats app_ks.service_events_by_minute_shard
nodetool tablehistograms app_ks service_events_by_minute_shard
```

Histogram/compaction numbers are not exact instantaneous counts of all live partitions. Combine with tracing/metrics, write-stream statistics, and controlled top-key analysis to find outliers. Avoid calling `SELECT COUNT(*)` on massive partitions under heavy load just to measure size.

### Step-by-step bucketing workflow

1. **List primary queries** along with entity keys known to users at read time.
2. **Estimate per-key data:** average/peak rate, row count, cell count, payload, and retention.
3. **Evaluate skew:** are there standout tenants/devices/services?
4. **Pick domain and time buckets** aligned with query paths, not merely total key count.
5. **Add shards only when truly needed** to split concurrent load inside the same bucket; design complete shard-reading logic upfront.
6. **Estimate fan-out** for common queries, especially when reading across many hours/days.
7. **Check TTL/compaction/repair** against the data model and actual update patterns.
8. **Benchmark a representative workload**, tracking p95/p99, replica load, max partition size, and read cost; tune bucket duration and shard count.

## 12. Migrating bucket models without losing data

Moving from `PRIMARY KEY ((tenant_id, service_id), occurred_at, event_id)` to `(tenant_id, service_id, minute_bucket, shard_id)` means **changing the primary key**. Cassandra does not handle this with a single `ALTER TABLE` parameter; you need a migration strategy.

A typical workflow:

1. **Create the new table** with query-aligned partition key, clustering key, and TTL.
2. **Define versioned bucket/shard functions:** time zone, bucket duration, hash, shard count, timestamp source.
3. **Switch writers** to the new model via dual-write or a replayable event source, with detection and recovery for partial failures.
4. **Backfill history** with rate limiting, checkpoints, and stable IDs so retries do not create logical duplicates.
5. **Dual-read verify** between old and new tables across many tenants/services/buckets, checking boundaries, late data, TTL, and deletes.
6. **Switch readers** once verification passes, monitoring latency and timeouts; retain fallback per policy.
7. **Decommission the old model** after confirming no read/write paths still depend on it, then handle legacy data per retention policy.

**Risk point:** dual-writing across two different tables/partitions is not inherently atomic. If table A succeeds and table B times out, clear retry/reconciliation is required. Changing a partition key to eliminate hotspots is both a data-model change and an application workflow change.

## 13. Common mistakes

| Claim | What is overlooked | Remediation |
| --- | --- | --- |
| "Adding `event_day` to the clustering key splits by day." | Clustering columns do not participate in token calculation; partitioning still depends only on the partition key. | Put the day bucket in the **partition key**. |
| "Bucketing by tenant is always balanced because there are many tenants." | A few tenants can produce most of the data or requests. | Measure skew; combine device/service, time, or shards. |
| "Shorter buckets are always more efficient." | Fan-out for long history can explode. | Choose duration based on both read requirements and write load. |
| "12 shards will surely spread evenly across 12 machines." | Token placement and replica sets can overlap; hashes can skew. | Measure actual distribution; adjust topology/shards when needed. |
| "Each shard has `LIMIT 100`, so the combined API returns 100 rows." | You can receive up to 1,200 rows from 12 shards. | Merge globally and take the top 100. |
| "Changing `SHARD_COUNT` in code does not affect old data." | The same ID can route to a different shard. | Version/migrate and keep old-config read paths. |
| "7-day TTL means data physically disappears right at expiration." | Tombstones and compaction have their own lifecycle. | Track TTL, tombstones, compaction, and retention. |
| "A high replication factor splits a large partition." | Replicas are copies of the same logical partition. | Change the partition key/bucket, not just RF. |
| "Retrying with `now()` generating a new ID still refers to the same event." | The full primary key changed, potentially creating a new row. | Keep event ID, timestamp, bucket, and shard stable. |
| "A user-bucketed table suffices for tenant-wide queries." | Query lacks partition key components; there is no cross-partition order. | Create a tenant-timeline table or separate aggregation path. |

## 14. Self-check exercises

An e-commerce platform needs to log order events. Each event has `tenant_id`, `store_id`, `occurred_at`, and `event_id`. Workload:

- 200 tenants, each with multiple stores.
- Typical stores emit **5 events/second**.
- One large store emits **600 events/second** during peak hours.
- Average logical payload per event is **800 bytes**.
- **Q1:** fetch the 50 latest events of **one store within 15 minutes**.
- **Q2:** generate a 30-day event summary report across an entire tenant.

The design team proposes three options:

```sql
-- A: one partition for the entire tenant:
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: one partition per store per hour:
PRIMARY KEY ((tenant_id, store_id, hour_bucket), occurred_at, event_id)

-- C: each store per hour with additional shards:
PRIMARY KEY (
    (tenant_id, store_id, hour_bucket, shard_id),
    occurred_at,
    event_id
)
```

**Questions:**

1. Does A risk large/hot partitions if a tenant has many stores? Why?
2. Which bucket types does B use? How many hourly buckets might Q1 have to read when a 15-minute window crosses an hour boundary?
3. Roughly how many rows and how much logical payload does the large store generate in one hour under B?
4. If C uses 6 shards with ideal distribution, roughly how many events/second does each shard receive on average?
5. With C, can you simply query `WHERE tenant_id = ... AND store_id = ... AND hour_bucket = ...` to read all 6 shards?
6. Should Q2 read all raw 30-day events across thousands of buckets on every dashboard load?
7. If an event arrives one hour late, which hour will an **event-time** bucketing rule write it into?
8. What issues can arise from changing shard count from 6 to 12 without a migration plan?
9. Does `SELECT LIMIT 50` on each shard guarantee a combined result of 50 chronologically ordered rows?

**Answers with explanations:**

1. **Yes.** `tenant_id` is the sole partition key; all events of the tenant land in one partition, while `occurred_at` is only a clustering column.
2. B combines a **domain bucket** `(tenant_id, store_id)` and a **time bucket** `hour_bucket`. A 15-minute window can intersect **1 or 2 hourly buckets**.
3. `600 × 3,600 = 2,160,000` rows/hour; payload `2,160,000 × 800 = 1,728,000,000 bytes ≈ 1.61 GiB`, excluding overhead/replicas.
4. `600 / 6 = 100 events/sec/shard` on an ideal average; does not guarantee all shards/replicas carry equal load.
5. **Not via a simple primary-key access path**: `shard_id` is part of the partition key; it must be supplied or all relevant shards must be queried explicitly.
6. Generally **no**. Q2 should use a dedicated summary/aggregation table with clearly defined accuracy and refresh cadence instead of scanning raw data across huge numbers of partitions every time.
7. Into the bucket of the **event timestamp**, not the current write hour, per the chosen convention.
8. The same event ID can map to a different shard, causing readers to miss historical data or retries to create duplicate rows in a new partition.
9. **No.** You must merge the sorted streams using a consistent comparator and then take the global top 50.

## 15. Key takeaways

- **Time bucketing** bounds a partition's history within a defined window; **domain bucketing** separates data by entity or business boundary known to queries.
- Bucketing does not emerge automatically from clustering columns: changing partitioning requires putting the bucket component in the **partition key**.
- **Combining domain + time** commonly suits events, logs, orders, and sensors; if a key still runs hot, **artificial sharding** can be added.
- Every component added to the partition key helps split data, yet also requires readers to **know or query multiple bucket/shard values**, bringing fan-out and merge costs.
- Choose buckets based on **primary queries + partition size + peak load + skew + latency**, rather than a universal MB threshold for every cluster.
- Standardize **time zone, event time, truncation rules, hash algorithm, and shard count**; keep the full primary key stable across retries.
- TTL, replication, consistency levels, compaction, and repair influence data lifecycle and operations, but **do not replace** partition key design.

Sound bucketing enables Cassandra to leverage its wide-column model and distributed architecture predictably: efficient key and range reads, balanced load distribution, manageable compaction/repair, and Java application integration without corrupting data semantics on retries or late-arriving events.
