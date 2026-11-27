# Monotonically Increasing Keys, Time in Keys, and Load Distribution

In Apache Cassandra, a **partition key** value is passed through a *partitioner* to determine the token and the replica group responsible for storing the data. Many systems generate keys in **increasing order**, such as event numbers 1001, 1002, 1003 or timestamps for each write. This raises an important question: do increasing keys funnel every new record onto a single node like in some key-ordered storage engines?

**The answer depends on which key is increasing and where it sits in `PRIMARY KEY`.** With the `Murmur3Partitioner` commonly used in Cassandra, increasing partition keys **are not placed onto correspondingly increasing tokens**: values are hashed so different partition keys can distribute across the ring. However, if the partition key stays fixed while a **time clustering column** increases, all new rows still land in the **same logical partition**. Similarly, using a minute-rounded timestamp as the partition key can create one "open" partition receiving all writes during that minute.

This lesson belongs to the **Keys and Partitions** chapter, connecting wide-column concepts, token distribution, and query-driven table design with practical concerns around time-based writes, hot partitions, range reads, replication, consistency levels, and Java applications.

After this lesson, you will be able to:

- Distinguish **increasing partition key values** from **increasing clustering key values**.
- Explain accurately the roles of Murmur3, tokens, replicas, and why *hashing does not cure a hot partition*.
- Recognize mistakes when using `event_day`, `minute_bucket`, or `status` as the sole partition key for high traffic.
- Choose entity-based partition keys, **time buckets**, and controlled **shards** to balance write load against read cost.
- Write CQL range queries within one partition and merge results when multiple partitions must be read.
- Maintain stable keys, timestamps, and shards when retrying write operations from Java.

## 1. Reading primary key components accurately

Consider a time-series table:

```sql
CREATE TABLE readings_by_device (
    device_id   uuid,
    measured_at timestamp,
    reading_id  uuid,
    temperature double,
    PRIMARY KEY (device_id, measured_at, reading_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, reading_id ASC);
```

In this definition:

| Component | Column | Role |
| --- | --- | --- |
| Partition key | `device_id` | Determines the partition, token, and replica set. |
| First clustering column | `measured_at` | Orders rows by time **within the same partition**. |
| Next clustering column | `reading_id` | Distinguishes readings sharing the same timestamp. |
| Data column | `temperature` | Measurement value specific to each row. |

If 10,000 new readings are sent for the same `device_id`, they have 10,000 distinct clustering keys yet **only one partition key value**. That partition's token does not change as `measured_at` advances from 08:00 to 09:00.

```text
Partition key = device-A -> token(device-A) -> replica set X

  clustering key (09:03, id-4) -> newest reading
  clustering key (09:02, id-3)
  clustering key (09:01, id-2)
  clustering key (09:00, id-1)

Increasing measured_at / reading_id does not create a new partition.
```

From this come two completely different cases:

1. **Increasing partition key values:** `event_id = 1001, 1002, 1003, ...`, where each ID is its own partition key.
2. **Increasing clustering key values:** `measured_at` advances 08:00, 08:01, 08:02 while `device_id` stays unchanged.

Only the first case creates additional partition keys. The second case makes the chosen partition **wider in row count**, and if many clients write concurrently to that key, the partition can become a hotspot.

## 2. Do increasing partition keys create token-level hotspots?

In common Cassandra deployments using `Murmur3Partitioner`, the partition key is encoded to bytes and hashed to compute a token. Consecutive numbers `1001`, `1002`, `1003` **do not automatically produce consecutive tokens**.

For example, a table only looking up one event by ID:

```sql
CREATE TABLE events_by_id (
    event_id bigint PRIMARY KEY,
    occurred_at timestamp,
    payload text
);
```

An application might write:

```sql
INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1001, '2026-11-21T08:00:00Z', 'event A');

INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1002, '2026-11-21T08:00:01Z', 'event B');

INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1003, '2026-11-21T08:00:02Z', 'event C');
```

Because the three `event_id` values are three distinct partition keys, the system computes a separate token for each. Numeric order `1001 < 1002 < 1003` **does not predict token order**.

```text
event_id 1001 --hash--> token T3 ----> replica set R3
event_id 1002 --hash--> token T1 ----> replica set R1
event_id 1003 --hash--> token T2 ----> replica set R2

T1/T2/T3 here are illustrative symbols, not real tokens.
Replica sets can also overlap in small clusters.
```

**Consequence:** do not mechanically apply the "monotonically increasing keys always write to the right edge of a B-tree index" argument to Cassandra using Murmur3. At the same time, **never conclude** that every workload with increasing keys is balanced:

- If at a given moment only **one or a few partition keys are being written**, load still concentrates on the replicas of those keys.
- Certain keys may receive **more commands** or larger payloads than others; hashing distributes **key placement**, not the workload of a single key.
- Actual distribution also depends on node count, tokens/vnodes, topology, replication strategy, node state, and real key distribution.
- If a cluster uses a partitioner other than Murmur3, do not assume identical distribution rules; verify the running configuration.

### Why isn't a unique key per event automatically a good schema?

The `events_by_id` table fits this query very well:

```sql
SELECT occurred_at, payload
FROM events_by_id
WHERE event_id = 1002;
```

However, it is unsuitable for asking "the 100 latest events of device A," because `event_id` does not group events by device and time. There is no partition key holding a timeline to read in clustering order.

**High cardinality provides many keys to distribute; table design must still start from the query.**

## 3. How do timestamps in partition keys vs. clustering keys differ?

Timestamp is a temporal data type. Where you place it determines both queries and load distribution.

| Design | Partition key | What happens as time advances |
| --- | --- | --- |
| `PRIMARY KEY (event_time)` | `event_time` | Each distinct timestamp value can create a partition; tokens are hashed. |
| `PRIMARY KEY (device_id, event_time)` | `device_id` | Events for the same device keep adding clustering rows to the same partition. |
| `PRIMARY KEY ((device_id, event_day), event_time)` | `(device_id, event_day)` | Creates a new partition **per day, per device**; writes within the day still concentrate on that partition. |
| `PRIMARY KEY (minute_bucket, event_time, event_id)` | `minute_bucket` | All writes from all devices in the current minute can concentrate on one partition. |
| `PRIMARY KEY ((tenant_id, minute_bucket, shard_id), event_time, event_id)` | `(tenant_id, minute_bucket, shard_id)` | Multiple shards coexist each minute; must fan out when reading a tenant timeline. |

Pay attention to parentheses: `PRIMARY KEY (device_id, event_time)` has a **simple partition key `device_id`**, not a two-column composite partition key.

### High-cardinality timestamp as partition key

```sql
CREATE TABLE events_by_timestamp (
    event_time timestamp PRIMARY KEY,
    event_type text
);
```

This structure makes `event_time` both the partition key and the full primary key. If two events share the **exact same timestamp value** at the stored precision, they write to the **same logical row**. If timestamps change every millisecond, they generally produce many tiny partitions, yet a global range query on timestamp is **not** equivalent to an efficient clustering key range scan.

Therefore, a standalone timestamp is usually not a good key for an event stream with concurrent events and entity-scoped historical query needs.

### Increasing timestamp in the clustering key

```sql
CREATE TABLE events_by_device_day (
    device_id  uuid,
    event_day  date,
    event_time timestamp,
    event_id   uuid,
    payload    text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

This is a fitting pattern when the application knows `device_id` and `event_day` to retrieve a time slice. `event_time` advances with the clock yet **does not participate in token calculation**. Range predicates on the clustering key allow reading data chronologically within a located partition.

**Do not confuse:** *clustering order* is the order of data inside a partition. It does not mean Cassandra sorts partition keys cluster-wide by timestamp, nor does it move new events onto the next node as time advances.

## 4. The easiest case to run hot: an active time bucket

Suppose a system stores all events of a tenant by minute:

```sql
CREATE TABLE tenant_events_by_minute (
    tenant_id     text,
    minute_bucket timestamp,
    occurred_at   timestamp,
    event_id      uuid,
    payload       text,
    PRIMARY KEY ((tenant_id, minute_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

This design has a composite partition key `(tenant_id, minute_bucket)`. When the minute rolls from 08:30 to 08:31, Cassandra creates a new partition key and computes a new token. Yet **during minute 08:30**, all events of tenant `whale` go into one partition regardless of how many clients are sending.

```text
08:30:00 - 08:30:59
  partition ('whale', 08:30)
  <- all current writes of tenant whale

08:31:00 - 08:31:59
  partition ('whale', 08:31)
  <- all writes in the next minute

Hashing only distributes these two partition keys among replicas.
It does not split an active minute into multiple partitions.
```

If the tenant sends **8,000 events/second**, each carrying an average **1,000 bytes of logical payload**:

```text
One minute:
  8,000 × 60 = 480,000 rows
  480,000 × 1,000 = 480,000,000 bytes
                     ≈ 457.8 MiB logical payload

Write load of one open partition: 8,000 events/sec
```

These numbers are illustrative only, excluding clustering keys, cell metadata, compression, tombstones, and replication factor. Even though minute buckets prevent multi-day accumulation into a single partition, **480,000 rows and 8,000 writes/second within one minute** can still be too large or too hot for a given system.

### Distinguishing three scenario types

| Scenario | What can happen | Right mental model |
| --- | --- | --- |
| Each event has its own increasing partition key | Many hashed tokens, potentially spread across the ring | Good for event-by-ID lookup; does not natively serve timelines. |
| Many events share one `device_id`, clustering timestamp increases | One partition holds growing row counts and takes current load | Can produce both a **large partition** and a **hot partition**. |
| All events share the current `minute_bucket` | Write load concentrates on one partition per remaining key combination | Rolling minutes creates a new partition, but **does not fix intra-minute heat**. |

There is no universal events/sec or MiB threshold applicable to every cluster. Examine **peak load, payload size, topology, compaction, replica count, and latency SLOs**.

## 5. Designing entity-scoped time buckets

For the primary query "fetch the 100 latest events of **one device in one hour**," a common design is:

```sql
CREATE TABLE device_events_by_hour (
    tenant_id    text,
    device_id    uuid,
    hour_bucket  timestamp,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    payload      text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Each `tenant_id + device_id + hour_bucket` combination is one partition key. Rows in the partition are ordered by `occurred_at DESC` then `event_id ASC`.

A matching query:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM device_events_by_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND occurred_at >= '2026-11-21T08:20:00Z'
  AND occurred_at <  '2026-11-21T08:30:00Z'
LIMIT 100;
```

Cassandra locates **one partition** from the three equality predicates, then scans `[08:20, 08:30)` in clustering order. `LIMIT 100` bounds results; it does not guarantee reading only 100 cells if data has tombstones or multiple SSTables.

### Why does adding `device_id` improve distribution?

Suppose a tenant has 200 active devices during an hour. Instead of every tenant event in that hour using `(tenant_id, hour_bucket)`, each device gets its own partition key:

```text
('acme', D01, 08:00)
('acme', D02, 08:00)
...
('acme', D200, 08:00)
```

Independent keys are hashed to tokens, giving the workload **an opportunity to spread** across multiple replica sets. Still, if device D01 produces 90% of events, partition D01 remains hot; adding other devices does not offload D01's own traffic.

### Is a shorter bucket always better?

No. Minute buckets instead of hours shorten the accumulation window per partition, yet cause a 24-hour historical query to handle up to 1,440 minute buckets per device instead of 24 hourly buckets. That increases request count, total partitions read, and result-merging cost.

Choosing a bucket must balance:

1. Write rate and **peak** events per entity/bucket.
2. Payload/row and **row/cell/byte count** per partition.
3. Time windows the application queries frequently.
4. **Fan-out** cost across many buckets and compaction/repair overhead.
5. TTL and data retention policies.

## 6. Sharding when a single entity still runs too hot

If a tenant or device generates massive event rates **within the same bucket**, `shard_id` can be added to the partition key. For example, reading a **tenant-wide timeline within one minute**:

```sql
CREATE TABLE tenant_events_by_minute_shard (
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

Suppose **16 shards** are used and each event has a stable `event_id`:

```text
shard_id = floorMod(stableHash(event_id), 16)

('whale', 08:30,  0) -> partition 0
('whale', 08:30,  1) -> partition 1
...
('whale', 08:30, 15) -> partition 15
```

If 8,000 events/second distribute nearly uniformly, each shard receives on **average 500 events/second**. In one minute, each shard holds around **30,000 rows** and **30 MB of logical payload** at 1,000 bytes/event. This is a mathematical expectation, not a guarantee that each shard sits on a separate node or cannot run hot.

### CQL to write and read one shard

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    'order-created'
);
```

Shard value `7` is illustrative. In production, producers must compute the shard using the shared algorithm based on event ID. Querying one shard:

```sql
SELECT occurred_at, event_id, event_type
FROM tenant_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

To read the **100 latest events across all 16 shards**, the application must:

1. Read relevant shards with bounded concurrency.
2. Receive streams already ordered by `occurred_at DESC, event_id ASC` within each partition.
3. **Merge** using the same comparator, then take the top 100 for the whole tenant/minute.
4. Use paging if more data is needed; do not rely on Cassandra `ORDER BY` to sort automatically across 16 partition keys.

**The price of sharding** is more partition lookups, harder multi-bucket queries, and maintaining consistency of hash algorithms, shard counts, and schema version transitions.

### Changing shard count does not automatically move old data

If you initially use 16 shards and later switch to 32 shards, the same `event_id` can map to a different shard. Already-written data stays in the old partitions. You must version rules or track cutover timestamps, preserve reads for old buckets, or run controlled backfills; never just edit a constant in the application and assume historical queries stay accurate.

## 7. Event creation time, write timestamps, and timeuuid

There are **three time concepts** commonly confused:

| Concept | Example | Role |
| --- | --- | --- |
| **Event time** (business occurrence time) | `occurred_at timestamp` | Used in clustering keys to organize timelines, or to compute buckets. |
| **Cassandra write timestamp** | Microsecond timestamp attached to cell/mutation | Participates in conflict resolution between writes. |
| **TimeUUID** | `timeuuid` generated by `now()` | Identifier embedding a time component; usable as a clustering column. |

**`occurred_at` does not automatically decide which record wins when two writes share a primary key**, unless the application explicitly uses write-timestamp-related semantics. Cassandra resolves cells by write timestamp and its conflict resolution rules. These are two distinct conceptual layers.

### Using `timeuuid` for a clustering column

```sql
CREATE TABLE messages_by_room_day (
    room_id      uuid,
    message_day  date,
    message_id   timeuuid,
    sender_id    uuid,
    body         text,
    PRIMARY KEY ((room_id, message_day), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC);
```

In this table, `message_id` is a `timeuuid` clustering column; its order reflects the time component under Cassandra's comparator, useful for timelines. Still, tokens are computed from `(room_id, message_day)`. You cannot expect writes to spread across new partition keys merely because `message_id` changes for every message.

CQL's `now()` function generates a new `timeuuid` on every execution. Retrying an `INSERT` with `now()` directly inside the primary key can create **another row** for the same business event. When idempotency is required, generate `message_id` once and store or pass it through retries to reuse that exact value.

### Late-arriving events and clock skew

Event time can differ from write time due to queues, network delays, or clock skew. If buckets are derived from `occurred_at`:

- An event arriving a day late must still go into the **bucket of its determined event time**, if that is the business rule.
- Never recompute the bucket from the server's current wall-clock time during retries.
- All producers and consumers must agree on the time zone (e.g., UTC), precision, and `[start, end)` boundaries.
- If querying by **ingestion time** instead of event time is required, a separate access path may be needed.

TimeUUID also does not establish reliable global ordering across clients with skewed clocks or late writes; stricter business ordering requires appropriate coordination mechanisms.

## 8. Time-driven hot partitions vs. hot nodes

Distinguish:

- **Hot partition**: a partition key receiving too many reads/writes, even while small in size.
- **Large partition**: a partition key holding many rows/cells/bytes, even if rarely accessed.
- **Hot node**: a server bearing disproportionate load, whether from one hot partition, multiple keys mapping onto related replicas, or I/O, compaction, coordinator, and topology factors.

For example, `minute_bucket = 08:30` is **one active key**; at 08:31, the hotspot may shift to another replica set. Shifting a hotspot minute-by-minute **does not equal eliminating the hotspot**. Each minute can still overload the responsible replicas.

If a table has millions of distinct partition keys with relatively uniform access, Murmur3 and sound token distribution help spread workload. Still, actual balance must be verified via metrics on **top keys**, read/write counts, byte distribution, and per-node latency.

### Do replication and consistency automatically split load?

A keyspace uses its replication strategy to pick replicas for each token. With replication factor `3`, a partition has three replicas per keyspace policy. Raising RF does not turn one partition into multiple smaller data partitions; writes must still be sent to the responsible replicas.

Consistency levels like `LOCAL_ONE` or `LOCAL_QUORUM` determine acknowledgment/read requirements, impacting latency and availability. They **do not change the partition key** and do not replace bucketing/sharding for reducing concentrated load. When diagnosing, inspect both coordinators and involved replicas instead of only comparing cluster-wide request averages.

## 9. Observing and diagnosing skewed load

Do not see `SELECT LIMIT 20` return quickly and conclude the partition isn't hot. A partition can return its first page fast while holding huge bytes/tombstones or receiving writes at excessive frequency.

| Metric group | Question to answer |
| --- | --- |
| **Top read/write partition keys** | Are a few keys taking most of the requests? |
| **Partition size/cell count histogram** | Are open partitions accumulating too many rows and bytes? |
| **Read/write latency p95, p99, timeouts** | Are there tail latency spikes on bucket rollovers or traffic surges? |
| **Per-node CPU, disk I/O, network, GC** | Is any replica/coordinator experiencing concentrated load? |
| **SSTables per read, tombstone scans** | Are slow reads caused by live data volume, tombstones, or many SSTables? |
| **Compaction backlog, streaming/repair** | Are background tasks amplifying the issue? |
| **Event rate by tenant/device/bucket/shard** | Is real distribution as uniform as hashing assumptions? |

Examples of common administrative commands, adjusted for your Cassandra version:

```bash
nodetool tablestats app_ks.tenant_events_by_minute_shard
nodetool tablehistograms app_ks tenant_events_by_minute_shard
```

Where supported by your version, `nodetool toppartitions` or application-level sampling/metrics can help pinpoint heavily read/written keys. Verify syntax and availability per version; partition histograms are typically SSTable-based statistics, not exact instantaneous counts of every live partition right now.

Avoid using `SELECT COUNT(*)` on huge partitions or scanning tables under high load merely to count rows. A count query can force Cassandra to process massive data and worsen the incident.

### Practical diagnostic workflow

1. Identify the **queries and timestamps** exhibiting high p99, timeouts, or write queueing.
2. Inspect `PRIMARY KEY` to see which columns actually form the partition key and how many keys are written concurrently.
3. Measure **max/percentiles**, not just averages, of event volume and bytes per key/bucket.
4. Cross-check load across replicas and nodes alongside compaction/repair activity.
5. Prototype entity-based buckets or sharding in an environment with representative workload.
6. Re-measure write/read latency, partition sizes, fan-out, timeouts, and idempotent retry behavior.
7. Deploy only when the solution fits both the write path **and** primary query patterns.

## 10. Java Driver: deterministic bucket and shard calculation

This example uses Cassandra Java Driver 4.x to write events into `tenant_events_by_minute_shard`. `eventId` is generated **once in the business flow**, while `occurredAt` remains invariant across retries. Use `Instant` to preserve UTC timestamps.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventWriter {
    private static final int SHARD_COUNT = 16;

    private final CqlSession session;
    private final PreparedStatement insert;

    public TenantEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_minute_shard " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, event_type, payload) VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public void write(
            String tenantId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        Instant minuteBucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, minuteBucket, shardId, occurredAt,
            eventId, eventType, payload
        ));
    }
}
```

Things to guarantee:

- `eventId` and `occurredAt` **must never be regenerated on retries**; changing them can alter the entire primary key.
- `minuteBucket` is derived from the same `occurredAt` and UTC convention in every writer/reader.
- `eventId.hashCode()` is deterministic within Java's `UUID`, yet in polyglot systems you must specify a byte-level hash algorithm, shard count, and algorithm version so other services produce identical results.
- `SHARD_COUNT` is part of the storage convention; changing from 16 to 32 requires a plan for reading historical data.
- `PreparedStatement` is reused, allowing the driver to use routing keys when the full partition key is bound.
- Standard Cassandra writes have upsert semantics across the **entire primary key**. That prevents extra rows on retry when keys are stable, though it does not guarantee other business side effects occur exactly once.

For high throughput, the write layer needs **bounded concurrency**, safe timeout/retry policies, and latency monitoring. An application should not raise asynchronous requests unboundedly just because sharding was added.

### Reading from Java when multiple buckets are needed

The read service layer must determine all relevant buckets/partitions, execute prepared queries with complete keys, and **merge** results ordered by `occurred_at` and `event_id`. Querying one shard does not represent the entire tenant; querying only one minute does not cover ranges crossing a minute boundary. Paging and concurrency limits protect the application, while bucket/shard choices dictate real query cost.

## 11. Common misconceptions

| Claim | Issue | Correct understanding |
| --- | --- | --- |
| "IDs increasing from 1 to N always write to the node with the highest token." | Murmur3 hashes partition keys; tokens do not increase monotonically with numeric IDs. | Check the actual partitioner and token distribution. |
| "Newer timestamps always land on the next node." | If timestamp is a clustering column, the token does not change. | Only the partition key determines the token. |
| "Adding `event_day` to the partition key always eliminates hotspots." | The entire current day can still hit one overheated key. | Calculate write rate **within the active bucket**. |
| "One partition per event is always optimal." | Reading timelines may have to query countless keys. | Group by entity/bucket aligned with queries. |
| "Using `CLUSTERING ORDER BY DESC` distributes writes across nodes." | Clustering only orders rows **within a partition**. | Use partition keys/buckets/shards to distribute load. |
| "16 shards is guaranteed 16× faster." | Replica sets, other hotspots, and fan-out costs still apply. | Verify real load, p95/p99, timeouts, and read cost. |
| "Changing shard count in config does not affect old data." | The same event ID can map to a different partition. | Have a versioning/migration plan. |
| "Retrying with `now()` is idempotent." | `now()` generates a different timeuuid every time. | Preserve the exact full primary key on retries. |
| "Raising RF or consistency automatically splits a hot partition." | Replicas/acks do not split a partition key. | Fix partition design and request distribution. |
| "Time buckets do not need a standardized time zone." | Writers and readers can look in two different partition keys. | Standardize bucket calculation, typically UTC. |

## 12. Practice exercise

A transaction logging platform has 50 tenants. During peak hours, tenant `mega` sends **6,000 events/second**; the other 49 tenants each send **10 events/second**. Average data is **500 bytes payload/event**. Two key queries:

- **Q1:** look up an exact event by `event_id`.
- **Q2:** fetch the 100 latest events of a tenant within **one minute**.

The design team proposes:

```sql
-- A: one partition key per tenant, no bucket.
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: one partition key tenant + minute.
PRIMARY KEY ((tenant_id, minute_bucket), occurred_at, event_id)

-- C: tenant + minute + shard.
PRIMARY KEY ((tenant_id, minute_bucket, shard_id), occurred_at, event_id)

-- D: each event is one partition key.
PRIMARY KEY (event_id)
```

**Questions:**

1. In A, does increasing `occurred_at` send each event of `mega` to a different partition?
2. B stops `mega`'s partition from growing across multiple days, yet within **one minute** how many rows does it still receive?
3. Roughly how many MB of logical payload does B receive in one minute, excluding overhead?
4. With C using 12 shards, what is the ideal average write rate per shard for `mega` in events/sec?
5. Can C use a single `SELECT` with `tenant_id` and `minute_bucket` without `shard_id` to fetch the 100 latest tenant-wide events?
6. Does D favor Q1 or Q2? What else does Q2 require?
7. If writes under C are retried with the same `event_id` while `minute_bucket` is recomputed from **current wall-clock time**, is avoiding duplicate rows still guaranteed?
8. If the cluster uses Murmur3, do continuously increasing numeric `event_id`s in D necessarily map to continuously increasing tokens?

**Answers:**

1. **No.** The partition key is only `tenant_id`; timestamp is a clustering column so all `mega` events go into the same logical partition.
2. `6,000 × 60 = 360,000` rows/minute if every event creates a new full primary key.
3. `360,000 × 500 = 180,000,000 bytes = 180 MB ≈ 171.7 MiB` logical payload.
4. `6,000 / 12 = 500 events/sec/shard` assuming ideal hash distribution.
5. **Not via standard primary-key access paths.** You must read all relevant shards, merge by clustering order, and select the top 100.
6. D favors **Q1**. Serving Q2 efficiently requires adding a timeline table or an access path by tenant, time, and bucket.
7. **No.** The partition key can change; buckets must be computed from stable event time using a consistent rule.
8. **No.** Murmur3 hashes the entire partition key value; numeric order of keys does not predict token order.

## 13. Takeaways for operating Cassandra

- **Increasing partition keys** under Murmur3 produce hashed tokens; do not assume they walk sequentially around the token ring in numeric order.
- **Increasing clustering time** only appends rows within the selected partition; if the partition key stands still, the hotspot stays on the same replica set.
- **Time buckets** bound accumulation duration and partition lifecycle; **shards** create multiple concurrent partition keys to split active load. Both increase read cost across multiple partitions.
- **Cardinality** is helpful, yet you must also measure byte distribution, row count, request rate, and replica hotspots.
- **Query patterns dictate schema:** lookup by ID, device timeline, and tenant-wide timeline typically require separate access paths.
- **Safe retries** demand consistent event ID, event time, bucket, and shard; calling `now()` on every attempt can create extra rows.
- **Replication, consistency, compaction, and repair** affect operations, but do not automatically alter partition keys or break up a hot partition.

Understanding the differences between increasing keys, time in clustering keys, and token-based distribution lets you design Cassandra tables with predictable latency, prevent cluster hotspots, and integrate from Java while preserving data semantics across retries and bucket transitions.
