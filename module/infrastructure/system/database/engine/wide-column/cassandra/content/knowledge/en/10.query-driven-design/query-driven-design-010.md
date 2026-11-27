# Controlling Unbounded Growth in Collections or Event Histories

## Lesson Objectives

Apache Cassandra is a distributed **wide-column** database in which partition keys and clustering columns govern read paths, partition sizes, and how load spreads across nodes. During implementation, an approach that looks natural at first is storing every event for an entity in a `list` or `map` column and continuously appending to it. Another is putting an entity's entire lifetime history into a single partition. Both risk turning **unbounded growth** into a chronic bottleneck.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It focuses on recognizing appropriate collections, replacing historical collections with keyed rows and time buckets, bounding read/write paths, applying TTL with accurate semantics, and operating with replication, compaction, repair, and Java applications.

After completing this lesson, you will be able to:

- Distinguish `list`, `set`, `map`, `frozen`, and **clustering-keyed row series** in Cassandra.
- Explain why **unbounded collections** or **unbucketed history partitions** inflate read, write, delete, tombstone, and hot-partition risks.
- Estimate rows/bytes per partition from peak throughput, event size, and bucket width.
- Write CQL storing events as **one row per event** with an entity/bucket partition key and time-based clustering.
- Design reads for the N newest events, range filtering, multi-bucket reads, and pagination without unbounded scans.
- Use small, bounded collections for appropriate metadata; handle replays, TTLs, late-arriving data, and migrations off legacy collections.

## 1. Two Growth Patterns to Spot Early

Suppose an IoT system ingests telemetry from devices. Each event includes:

```text
tenant_id, device_id, event_id,
event_time, received_at, event_type, severity, payload
```

Devices can emit many events per second and stay active for years. Two common modeling patterns appear:

1. **One row with an ever-growing collection:** `events list<...>` or `event_ids set<uuid>` growing with every event. Reads may have to pull an enormous structure just to display a few items.
2. **Many rows inside one eternal partition:** `PRIMARY KEY ((tenant_id, device_id), event_time, event_id)`. Rows are neatly ordered, yet total rows in the partition have no growth boundary.

What they share: data for **one logical key** lacks an adequate splitting or bounding mechanism. Hashing/tokens distribute **different partition keys**, not one giant collection or one hot partition across independent partitions.

### 1.1. The Read Path Drives the Choice

Illustrative query inventory:

| ID | Need | Values the Caller Has | Scope |
| --- | --- | --- | --- |
| Q01 | 50 newest events for one device in a UTC hour | Tenant, device, hour | One hourly bucket |
| Q02 | Events from 09:20 to before 09:40 UTC | Tenant, device, two bounds | One intra-hour range |
| Q03 | 50 newest events for a device across the last 6 hours | Tenant, device, range | Bounded multiple buckets |
| Q04 | Display 5 tags and a few device config options | Tenant, device | Small, bounded metadata |
| Q05 | Look up an event by event ID alone | Tenant, event ID | Different lookup path |
| Q06 | Aggregate all tenant events over 1 year | Tenant, year range | Broad analytical scope |

Q01–Q03 require a **chronologically ordered history series**, not a giant collection column. Q04, by contrast, is a candidate for a small `set` or `map`. Q05 may need a dedicated lookup table; Q06 suits an analytics store or aggregation pipeline rather than pulling every collection or partition into a Java service.

## 2. Collections in CQL: A Tool for Small, Bounded Data

Cassandra supports collection types such as `list<T>`, `set<T>`, and `map<K,V>`. They are convenient when a row holds **a small set of attributes tightly bound to that row**.

| Type | Semantics | Suitable Example | Risk When Used for History |
| --- | --- | --- | --- |
| `list<text>` | Sequence of elements, duplicates allowed; list-ordered | A small set of admin-configured instruction steps | Continuous appending grows unboundedly; list order does not equal event time |
| `set<text>` | Unique values per element-type comparator | A handful of device tags | No chronological order; uniqueness by value only |
| `map<text,text>` | Key → value mapping | A few display options | Using each event ID as a key grows the map indefinitely |
| `frozen<map<...>>` | Collection treated as a single value on updates | Small config snapshot replaced atomically | Each change may rewrite the whole collection; unsuitable for unbounded growth |
| Clustered rows | Multiple rows inside a defined partition | History by device and hour/day | Still needs bucket bounds and largest-partition sizing |

For **non-frozen** collections, Cassandra can manage elements/entries as multiple cells within the same row. Deleting or updating elements can create tombstones. With `frozen`, the collection is handled as an atomic blob; changing one entry typically means rewriting the entire collection value, and neither creates a sub-table with independent partitions.

**Important:** a collection is not a sub-table that partitions itself per element. Stuffing millions of items into one column solves neither routing, load distribution, nor time-range reads.

### 2.1. Example of Reasonable Small Collection Usage

```sql
CREATE TABLE device_profiles_by_id (
    tenant_id text,
    device_id uuid,
    display_name text,
    tags set<text>,
    display_settings frozen<map<text, text>>,
    PRIMARY KEY ((tenant_id, device_id))
);

-- Add a tag to a small set.
UPDATE device_profiles_by_id
SET tags = tags + {'indoor'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;

-- Remove an unused tag.
UPDATE device_profiles_by_id
SET tags = tags - {'retired'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;

-- Replace the entire small settings snapshot because it is a frozen map.
UPDATE device_profiles_by_id
SET display_settings = {'unit': 'metric', 'theme': 'dark'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;
```

Suppose the product enforces at most **10 tags** and **8 config keys** per device. Those are **illustrative business bounds**, not defaults automatically enforced by Cassandra. The application must also handle concurrency: two writers adding elements concurrently can exceed the cap if each validates against a stale read.

If strict quota enforcement under high contention is required, design appropriate business-layer coordination rather than assuming reading set size then writing is an atomic transaction. For rarely changing config, versioned updates or a single owning writer may be simpler.

### 2.2. Anti-Pattern: Using a Collection as a Timeline

```sql
-- NOT recommended for unbounded event streams.
CREATE TABLE device_events_bad (
    tenant_id text,
    device_id uuid,
    recent_event_ids list<uuid>,
    PRIMARY KEY ((tenant_id, device_id))
);

-- Looks like appending one item, yet the list grows forever.
UPDATE device_events_bad
SET recent_event_ids =
    recent_event_ids + [00000000-0000-4000-8000-000000000010]
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;
```

Issues that emerge:

- **No growth boundary** without explicit pruning logic.
- A query returning the collection can drag a huge payload even when the UI needs only 20–50 recent events.
- Positional list operations, deletes, or edits can incur read-before-write costs and tombstones depending on the operation; list mutations under retries and concurrent writes must be controlled.
- Appended lists do not guarantee **`event_time` order** when devices send late events or multiple producers write concurrently.
- `set<uuid>` deduplicates IDs but **provides no time ordering**; `map<uuid, payload>` likewise does not support `event_time` range scans.
- `frozen<list<...>>` merely shifts to rewriting the whole collection and does not make unbounded history a good design.

Trying to maintain a "latest 50 items" list via **read → trim list → rewrite** is also prone to writer races: one writer can overwrite another's additions. Unless you can prove tight bounds and safe updates, use a **row-per-event table** instead of a collection.

## 3. Second Anti-Pattern: Unbucketed History Partitions

Avoid concluding that simply turning a collection into multiple rows is enough. For example:

```sql
-- Chronologically ordered, yet one partition per device grows forever.
CREATE TABLE device_events_unbounded (
    tenant_id text,
    device_id uuid,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

This table supports fetching events by time **within one partition**, yet years of data for `(tenant_id, device_id)` all land in the exact same logical partition. Rows are not split across multiple partitions simply because the clustering key contains timestamps.

Replication keeps partition copies per keyspace configuration; it does not split a hot partition. Compaction and repair maintain storage and replicas, yet **cannot fix an unbounded partition key**.

### 3.1. Sizing from the Hottest Device

Suppose the busiest device emits **20 events/second continuously**, with **600 bytes of raw business data** per event:

```text
One minute:
  20 × 60 = 1,200 events
  1,200 × 600 B = 720,000 B ≈ 0.72 MB

One hour:
  20 × 3,600 = 72,000 events
  72,000 × 600 B = 43,200,000 B ≈ 43.2 MB

One day:
  20 × 86,400 = 1,728,000 events
  1,728,000 × 600 B = 1,036,800,000 B ≈ 1.04 GB
```

This illustrative calculation **excludes** partition indexes, metadata, compression, tombstones, SSTables, compaction, replicas, and peak bursts. It does **not** establish a universal safe partition limit; always measure on the real cluster and workload.

If retention is 30 days yet the partition key **has no bucket**, live data in one partition still represents tens of days, plus on-disk tombstones and history awaiting compaction. **A 30-day TTL does not turn one partition into 30 daily partitions.**

### 3.2. Size, Hotness, and Partitions Read

| Approach | Size/Load per Partition | Cost of Reading Long Ranges |
| --- | --- | --- |
| One unbounded partition/device | Risks massive growth and concentrated load | Reads one partition, but may be huge/tombstone-heavy |
| One partition/device/day | Data segmented by day | Reading 7 days needs up to 7 calendar-day partitions |
| One partition/device/hour | Reduces per-partition data vs. daily | Reading 24 hours can touch **25 hourly buckets** if sliding window straddles boundaries |
| Hourly bucket + shards | Spreads load of extremely hot devices | Reads multiple shards per hour and merges |

**Boundary note:** "7 chosen UTC calendar days" corresponds to seven daily buckets; a "strict sliding 7 × 24-hour window" can touch **eight** daily buckets. Likewise, a 24-hour sliding window can touch 25 hourly buckets. Use half-open `[from, to)` intervals and count actual buckets before setting fan-out limits.

## 4. Designing the Event Table: One Row per Event, Partitioned by Hour

Assuming hot devices can emit tens of events/second, we **evaluate** UTC hourly buckets as a candidate. Schema:

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Here:

1. `hour_bucket` is the **UTC start-of-hour** timestamp derived from `event_time`; e.g., `2026-11-21T09:00:00Z` represents `[09:00, 10:00)`.
2. The full `(tenant_id, device_id, hour_bucket)` tuple is **one composite partition key**; Cassandra routes partition/token/replicas using the whole tuple.
3. `event_time` is the first clustering column, supporting sorting and range filtering **within the partition**.
4. `event_id` distinguishes events in the same millisecond. A random UUID provides deterministic ordering by key value, **not** proof of causal order when timestamps match.
5. `payload` and other regular columns do not inherently support efficient filtering/sorting outside designed query paths.

```text
Partition: (tenant-A, device-X, 2026-11-21T09:00:00Z)
    (09:59:58.300, id-103) -> ERROR
    (09:40:11.000, id-102) -> WARN
    (09:05:07.900, id-101) -> INFO

Partition: (tenant-A, device-X, 2026-11-21T10:00:00Z)
    (10:00:02.100, id-104) -> INFO
```

IDs in the diagram are illustrative labels. When two rows share `event_time`, actual ordering is determined by Cassandra's `uuid` key comparison on the second clustering column.

### 4.1. Writing an Event

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, received_at,
    event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

The `?` placeholders are for driver prepared statements; interactive `cqlsh` requires CQL literals. Reuse the same `event_id` and `event_time` on retries so a new key row is not created. If `event_id` changes across retries, or hour normalization varies, one event can appear multiple times across rows or partitions.

**Never infer system-wide ID uniqueness** merely because it appears in the clustering key. The primary key here guarantees row identity only for `(tenant, device, hour_bucket, event_time, event_id)`. Looking up by `event_id` alone requires a separate validated lookup path or index.

### 4.2. Q01: Reading the 50 Newest Events in an Hour

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;
```

This query supplies **the full partition key**, returning rows in default `DESC` clustering order. It is not an arbitrary `ORDER BY` across all devices or tenants.

### 4.3. Q02: Reading a Range Within One Hour

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

The `[fromInclusive, toExclusive)` convention prevents double-counting at boundaries. If a range crosses 10:00 UTC, the application must split the portion in the 09:00 bucket from the portion in the 10:00 bucket. A predicate `hour_bucket = 09:00` will not automatically fetch rows from the 10:00 partition.

### 4.4. Q03: Reading the 50 Newest Events Across 6 Hours

For `[08:20, 14:20)`, hourly buckets run from `08:00` to `14:00`—**7 buckets** total. To fetch the N newest events:

1. Determine buckets intersecting the range, subject to a hard cap (7 in this example).
2. Read the **newest bucket first**, with appropriate time slices and bounded row fetches.
3. Merge by `(event_time DESC, event_id DESC)`, or read sequentially from newest bucket to oldest when time buckets are strictly disjoint and properly aligned.
4. Stop once N rows are gathered; store appropriate continuation state if the UI supports "load more."

Do not assume a single CQL `ORDER BY` across multiple partitions cheaply builds a global order. When reading across **shards** within the same bucket, time ranges across shards overlap, requiring a true **k-way merge** rather than merely concatenating results shard by shard.

### 4.5. `LIMIT`, Paging, and API Bounds Are Distinct

| Concept | Meaning |
| --- | --- |
| `LIMIT 50` | Maximum total rows returned by one CQL query |
| Driver page size | Target rows per page fetch, supporting continuation |
| Fan-out limit | Maximum partitions/buckets/shards per request |
| Resource limit | Maximum intermediate rows/bytes, duration, concurrency, and memory |

`LIMIT 50` does not automatically keep a query cheap if the partition holds many tombstones. For multi-bucket APIs, never load unbounded rows from every bucket only to keep the last 50. Enforce both range bounds and a pagination plan upfront.

## 5. Small Metadata and Long History Belong in Separate Tables

A device can have **current configuration** and a **historical event stream**. The two have distinct lifecycles and access patterns:

| Attribute | `device_profiles_by_id` | `device_events_by_hour` |
| --- | --- | --- |
| Read path | One specific device | One device and one hour/range |
| Key | `(tenant_id, device_id)` | `(tenant_id, device_id, hour_bucket)` |
| Shape | One row, bounded metadata | Many event rows, time-clustered |
| Operations | Rename, add/remove tags, update options | Append events, rarely edit keys |
| Lifecycle | Tied to device lifetime | Telemetry TTL/retention |

Never cram thousands of event IDs into `tags` or `display_settings` simply because both relate to the device. Conversely, do not create a new history row every time a user toggles a minor setting if the business needs only the **current configuration value**.

If the product needs **both current config and setting-change history**, store the current snapshot in the profile table and emit a **config-change event** to the timeline. Those are two read paths requiring proper write, retry, and reconciliation handling—not an unbounded collection inside the profile row.

## 6. TTL and Retention Bound Data Age, Not Bucket Size

Illustrative policy: retain events for **14 days from occurrence time**. Each event can be written with remaining TTL:

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, received_at,
    event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

In CQL, `TTL` is **seconds from write time**, not computed automatically from `event_time`. Therefore:

```text
expires_at = event_time + retention_duration
remaining_ttl_seconds = expires_at - now_at_write

remaining_ttl_seconds > 0  -> write with remaining TTL
remaining_ttl_seconds <= 0 -> event already expired per policy
```

If retention is **14 days** and an event occurred 3 days before reaching the server, remaining TTL at write time is about **11 days**. Using a fixed 14-day TTL on every `INSERT` keeps the late event for nearly 17 days after `event_time`, violating the event-time retention contract.

### 6.1. TTL Does Not Shrink Partitions Immediately

TTL stops expired values from appearing as live data, yet Cassandra must process deletion markers (**tombstones**) and old copies inside SSTables. Physical space reclamation depends on compaction, deletion safety conditions, and replica state. When a `LIMIT 50` query traverses heavily expired data, it can still pay high tombstone scan costs.

Hourly buckets remain necessary if a single hour sees heavy traffic. A 14-day retention only caps **lifetime duration**; it does not split an overheated hourly partition into multiple partitions.

### 6.2. Collection TTLs Do Not Create Clean Boundaries Either

For non-frozen collections, individual elements/cells can carry different TTLs and update histories, causing them to expire at different times. For frozen collections, replacing the value follows atomic whole-value lifecycle semantics. Neither substitutes for a **time-partitioned history table**.

If the application continuously appends and rewrites a collection, retries or updates can shift expiration times of written cells. Never assume "just adding TTL" creates a safe, consistent, event-time-ordered bounded list.

### 6.3. Repair and Compaction

- **Compaction** organizes SSTables and clears eligible tombstones; it cannot split a huge partition or turn a collection into a history table.
- **Repair** converges replicas via Cassandra's mechanisms; it cannot fix duplicate event IDs generated by an app or miscalculated buckets.
- **Replication factor** sets partition replica count per topology. It provides fault tolerance, not distribution of **one hot partition** into multiple logical partitions.
- **Consistency level** such as `LOCAL_QUORUM` in an appropriate setup governs replica acknowledgments; it does not turn reading a giant collection into a cheap range scan.
- **`gc_grace_seconds`** governs deletion safety and replica maintenance. Never shrink it arbitrarily just to clear tombstones sooner, as doing so raises data-resurrection risk when replicas are out of sync.

### 6.4. When to Consider TWCS?

For largely append-only event data with fairly uniform TTLs and rare edits to old rows, **TimeWindowCompactionStrategy (TWCS)** is a candidate worth evaluating. However, **compaction windows** follow storage write timestamps, **not** the `hour_bucket` column in the primary key.

Late-arriving events, backfills, historical edits, and mixed TTLs can prevent time-window compaction from dropping SSTables as hoped. Never pick TWCS solely because a table is named `_by_hour`. Benchmark against realistic workloads, observing tombstones scanned, SSTables per read, latency, and compaction resources.

## 7. Late Events, Replays, Key Edits, and Hotspots

### 7.1. Late-Arriving Events

An event occurring at `2026-11-20T09:59:59Z` but arriving at the server at `2026-11-21T10:00:00Z` still belongs to bucket `2026-11-20T09:00:00Z` if keys derive from **event time**. If a producer computes buckets from `received_at` while readers query by `event_time`, the event lands in the wrong partition relative to queries.

Align all three decisions:

- Which timestamp governs **ordering** (`event_time` or `received_at`)?
- Which timestamp governs **bucketing**?
- Which timestamp governs **retention**?

They may differ for valid business reasons, provided every API understands and honors the exact contract; never change one field while leaving old assumptions in readers.

### 7.2. Replays and Event Identity

If a timeout occurs after Cassandra already applied a write, the producer may retry. A solid rule is keeping the exact same `event_id`, `event_time`, and bucket. Re-writing with the exact same full primary key is an **upsert on the same logical row**, though it does not automatically keep every TTL, cell value, or update order invariant.

If the same event ID arrives with a different timestamp or bucket, the history table can store two rows. When **tenant-wide uniqueness of event IDs** is required, design an ID/deduplication mechanism or a dedicated `(tenant_id, event_id)` lookup table operated appropriately.

### 7.3. Editing Time Fields Already in the Primary Key

`event_time` is a clustering column; `hour_bucket` is in the partition key. Cassandra does not allow altering a row's primary key via a standard `UPDATE`. Changing an event's timestamp typically requires **writing a new row under the new key and deleting the row under the old key**. That requires multiple mutations, generates tombstones, and needs recovery logic if interrupted mid-flight.

For audit systems, consider appending adjustment events or additional versions instead of silently rewriting history; immutability and deletion policies are business requirements to lock down.

### 7.4. Sharding When Even Hourly Buckets Run Too Hot

If measurements show a device writes too fast within a single hour, add `shard_id` to the partition key:

```sql
CREATE TABLE device_events_by_hour_sharded (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

An example sharding rule is `shard_id = hash(event_id) mod N`, with **hash function, shard count N, and rule version** uniform across all writers and readers. Reading a full hour requires reading **N partitions** and merging; without knowing each event ID, readers cannot target a single shard.

| Design | Benefit | Trade-Off |
| --- | --- | --- |
| Hourly, unsharded | One partition/device/hour; simple reads | Extremely hot device still causes hotspot |
| Hourly + N shards | Spreads one device/hour across N partitions | N-way fan-out for full-hour reads; complex paging/merge |
| Shorter bucket | Reduces rows/partition over time | Increases partitions read for longer ranges |
| Dedicated search/analytics store | Supports broad filters and aggregations | Adds sync cost; data may lag |

Never default to sharding as inherently better. Add shards when metrics prove it is needed and fan-out reads still meet SLAs.

## 8. Java: Writing Hourly-Bucketed TTL Events and Bounded Range Reads

Example using **DataStax Java Driver 4.x**. The application computes `hour_bucket` from UTC `event_time` by truncating to the hour and computes remaining TTL for event-time retention.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class DeviceEventRepository {
    private static final Duration RETENTION = Duration.ofDays(14);

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insertEvent;
    private final PreparedStatement readHourRange;

    public DeviceEventRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insertEvent = session.prepare(
            "INSERT INTO device_events_by_hour (" +
            "tenant_id, device_id, hour_bucket, event_time, event_id, " +
            "received_at, event_type, severity, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
        this.readHourRange = session.prepare(
            "SELECT event_time, event_id, event_type, severity, payload " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public static Instant hourBucket(Instant eventTime) {
        return eventTime.truncatedTo(ChronoUnit.HOURS); // UTC hour boundary
    }

    // true if the write completed per driver settings; false if already expired.
    public boolean write(
        String tenantId, UUID deviceId, UUID eventId,
        Instant eventTime, Instant receivedAt,
        String eventType, String severity, String payload
    ) {
        Instant expiresAt = eventTime.plus(RETENTION);
        long secondsLeft = Duration.between(clock.instant(), expiresAt).getSeconds();
        if (secondsLeft <= 0) {
            return false;
        }

        int ttlSeconds = Math.toIntExact(secondsLeft);
        BoundStatement statement = insertEvent.bind(
            tenantId, deviceId, hourBucket(eventTime),
            eventTime, eventId, receivedAt,
            eventType, severity, payload, ttlSeconds
        );
        session.execute(statement);
        return true;
    }

    public ResultSet readRangeInsideOneHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }
        Instant bucket = hourBucket(fromInclusive);
        if (toExclusive.isAfter(bucket.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Query must be split by hourly bucket");
        }

        return session.execute(
            readHourRange.bind(
                tenantId, deviceId, bucket, fromInclusive, toExclusive
            ).setPageSize(50)
        );
    }
}
```

Key points to understand:

1. `Instant` maps to CQL `timestamp` and `UUID` maps to `uuid`. `Instant.truncatedTo(HOURS)` produces consistent UTC hour boundaries.
2. `TTL ?` is seconds remaining until `event_time + 14 days` at write preparation time; already-expired cases are handled separately. App/node clock skew and actual write execution timing can introduce slight variance.
3. `Math.toIntExact` fails loudly if TTL overflows integer bounds rather than truncating silently. This example assumes 14-day retention.
4. `readRangeInsideOneHour` rejects ranges crossing a bucket; the API layer must split multi-hour intervals into separate calls within fan-out caps.
5. `setPageSize(50)` is the driver's target rows per page, **not a query-wide `LIMIT 50`**. Synchronously iterating the entire `ResultSet` can trigger fetching extra pages.
6. Returning `true` only signals `execute` returned without throwing under current driver settings; it does not guarantee data reached every replica or other projection tables.

Production applications also require tenant authorization, `payload` size limits, idempotency/retries, timeouts, backpressure, and metrics. Share a single `CqlSession` over the service lifecycle rather than creating one per event.

### 8.1. API-Layer Bounds

Example read contract:

```text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?from=2026-11-21T08:20:00Z
    &to=2026-11-21T14:20:00Z
    &limit=50
    &cursor=...

Server rules:
  - tenantId derived/verified from authenticated context
  - max range = 6 hours
  - max bucket fan-out = 7 (per timestamps and UTC boundaries)
  - max page size = 50
  - max concurrent partition reads configured, with backpressure
  - cursor bound to tenant, device, from/to, and query shape
```

A multi-partition cursor must encode merge progress and per-stream positions; you cannot reuse a single partition's paging state for the entire fan-out. As new events arrive or older events expire via TTL, consecutive pages **do not automatically form an immutable snapshot**. Communicate appropriate semantics to the UI.

## 9. Migrating from a Legacy Collection to a Bucketed History Table

If a system already stored history in a large `list` or `map`, never drop the old column immediately hoping the new table is already complete. Migration must address both existing data and ongoing live writes.

A conceptually safe plan:

1. **Lock the new schema and key rules**: stable event IDs, UTC event-time buckets, time clustering, retention, and duplicate policy.
2. **Choose a complete source**: durable event log, export, or enumerable snapshot. If only the legacy collection exists, evaluate the risk of reading one massive value; never make user APIs read the entire collection to migrate.
3. **Prevent losing new events**: deploy durable emission/writes to the new table with checkpoints and retries; if dual-writing, include partial-failure detection and recovery.
4. **Bounded backfill**: process in small device/partition batches, throttling QPS, bytes, and memory; preserve original event IDs, buckets, and policy-derived TTLs.
5. **Prevent old data from overwriting new**: if events can be edited, use verified revisions or versioning rules; backfill must never reinstate stale state after newer updates.
6. **Reconcile**: compare event ID sets, row counts, timestamps, fields, and representative buckets; verify expired data is not resurrected contrary to policy.
7. **Gradually shift reads**: canary reads, compare results by day/device, measure p95/p99, timeouts, partition hotness, and tombstones.
8. **Clean up legacy model** after verifying completeness, confirming no consumers depend on the collection, and keeping a viable rollback plan. Dropping large collections also carries tombstone/compaction costs that must be operated carefully.

**Never** perform "read a million-event list → fire one giant UPDATE" inside one request or one massive multi-partition batch. Checkpointed batching over a recoverable source is far safer.

### 9.1. Reconciliation Invariants

For every valid `(tenant_id, device_id, event_id)` within retention, verify:

| Invariant | How to Check |
| --- | --- |
| One event has one exact history key | Compute bucket from event time; verify full primary key |
| No duplicates from replays or bucket shifts | Use stable event IDs and source/manifest deduplication |
| Display fields match source | Compare `event_type`, `severity`, `payload`/hash, and timestamp |
| Expired events are not resurrected | Apply policy during backfill; never write negative TTL or reset age |
| No gaps during dual-write cutover | Check watermarks, checkpoints, and events straddling snapshot/live |

Never rely on a tenant-wide `COUNT(*)` on transactional Cassandra as the sole reconciliation check. Row counts can match while missing one event and duplicating another. Use an enumerable source and compare by key/version in bounded batches.

## 10. Monitoring to Catch Out-of-Control Growth

A sound design **defines boundaries** and measures whether production crosses them:

| Metric | Meaning | When Exceeding Expectations |
| --- | --- | --- |
| Largest collection element count | Detects metadata turning into disguised history | Cap additions, split tables, or migrate |
| Row/collection read payload size | Network/heap and serialization cost | Trim display fields; eliminate unbounded lists |
| Rows and bytes in largest partition | Checks whether buckets are small enough | Move to shorter buckets or validated sharding |
| Write rate to hottest partition | Catches hotspots even before size grows large | Spread load, throttle inputs, apply backpressure |
| p95/p99 of single- vs. multi-bucket reads | Tracks SLA, fan-out, and merge overhead | Shrink ranges, tune queries, or add a read path |
| Tombstones scanned and SSTables per read | Impact of TTLs/deletes/compaction | Adjust lifecycle model; inspect compaction |
| Event ingestion/replay lag | Late events or pipeline bottlenecks | Provision capacity, retry, reconcile |
| Requests hitting range/fan-out limits | Are users needing broader use cases? | Reclassify workload; consider search/OLAP |
| Expired-TTL data unreclaimed on disk | Capacity and compaction forecasting | Inspect TTLs, repair/grace, compaction |

If APIs set sensible defaults yet users routinely hit limits, do not raise caps blindly. That requirement may genuinely be an **analytical query** needing another projection table or a search/OLAP store.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Appending forever to `list<event>` on one row | Huge collection; expensive reads and updates | One row per event, bucketed by time |
| Using `set<uuid>` for full history | Unique IDs, but loses chronological `event_time` order | Cluster by time and ID |
| Using `frozen<map>` expecting per-entry range queries | Whole collection is one blob, not sub-partitions | Small frozen collections or a separate table |
| Switching from list to rows with only device as partition key | Partition still grows unboundedly | Add buckets tailored to queries and load |
| Choosing daily buckets for very hot devices without sizing | Single-day partition grows oversized | Measure peaks; try hourly or shorter buckets |
| Making buckets tiny while APIs still read a full year | Fan-out across thousands of partitions | Cap ranges or offload to analytics store |
| Assuming a 14-day TTL automatically counts from event time | Late events live with wrong age | Compute remaining TTL from business deadline |
| Trusting `LIMIT 50` to read only 50 cells | Tombstones and expired data still cost scan work | Measure tombstones; cap partitions/ranges |
| Treating list element edits/deletes as guaranteed O(1) | Read-before-write, tombstones, and races depending on op | Design row-keyed mutations; avoid unbounded lists |
| Retrying with a freshly generated event ID | Duplicate events in history | Stable IDs and deduplication rules |
| Reading all events and sorting in Java | Wastes network/heap and spikes latency | Cluster in sort order; use bounded paging/merging |
| Relying on repair/compaction to fix bad schema | Does not alter access keys or event logic | Redesign partitions/buckets and migrate |
| Shrinking `gc_grace_seconds` to "clean faster" | Raises resurrection risk when replicas fail | Align repair/deletion policy with operations |

## 12. Practice Exercise

A parcel delivery system stores scan history. Each record contains:

```text
tenant_id, parcel_id, scan_id, scanned_at, received_at,
location_id, status, note
```

Initially, the team used one `parcels_by_id` row with `scan_ids list<uuid>` and appended on every scan. Some parcels are scanned intensely: **30 times/second** for several hours. Each history record is assumed to be **900 bytes of raw data**. The product needs:

1. View the **30 most recent scans for a parcel in a UTC hour**.
2. View a parcel's history in a **2-hour** sliding window.
3. Retain history for **3 days from `scanned_at`**.
4. Handheld scanners can upload data 1 day late.
5. The parcel profile page only needs 5 tags and current status.

**Tasks:**

1. Give at least three reasons `scan_ids list<uuid>` is unsuitable for the full timeline; why does changing it to `set<uuid>` or `frozen<list<uuid>>` still fail the `scanned_at` ordering requirement?
2. Propose a partition key, clustering key, and `CREATE TABLE` for history using **UTC hourly buckets**, with `scan_id` distinguishing simultaneous scans.
3. Calculate raw rows/bytes for a **daily** bucket vs. an **hourly** bucket at a sustained 30 events/second. Use those numbers to explain the trade-off.
4. For a strict 2-hour sliding window, up to how many hourly buckets can be touched if both ends fall off hour boundaries? Sketch how to read and merge.
5. An event occurs 1 day before receipt, with 3-day retention from `scanned_at`: roughly how much TTL remains at write time?
6. If the screen only needs 5 tags per parcel, which collection type works and what bounding rules are required?
7. Outline a migration plan from the legacy list to the history table, covering retries, duplicates, backfill, reconciliation, and when to drop the old column.

**Reference guidance:** For UTC hours, a candidate is `PRIMARY KEY ((tenant_id, parcel_id, hour_bucket), scanned_at, scan_id)` with `CLUSTERING ORDER BY (scanned_at DESC, scan_id DESC)`. At **30 events/second**, one hour holds `108,000` rows, roughly `97.2 MB` of raw data; one day holds `2,592,000` rows, roughly `2,332.8 MB` (approx. `2.33 GB`). A 2-hour sliding window can touch **three hourly buckets**, requiring per-bucket reads and a bounded merge. An event arriving 1 day late has roughly **2 days of TTL** left under a 3-day event-time policy. For metadata, a bounded `set<text>` (e.g., max 5 tags) is an option; scan history requires separate rows. Finalize bucket choice by measuring real partitions/load, not raw math alone.

## Conclusion

In Cassandra, **collections suit small, bounded attribute sets attached to one row**, never unbounded event histories. Replacing a collection with multiple rows solves only half the problem: partitions must still be segmented via **buckets or shards matched to queries and load**, clustering keys must serve ordering/ranges, and APIs must cap fan-out, pagination, and bytes processed. TTL, compaction, repair, and replication cannot substitute for proper key design; late events, replays, and tombstones must be planned into operations. A durable solution pairs **explicit growth bounds, concrete CQL, migration/reconciliation workflows, and measurements on peak data**.
