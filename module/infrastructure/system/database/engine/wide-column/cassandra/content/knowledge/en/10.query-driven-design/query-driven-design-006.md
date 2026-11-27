# Designing Event Data with Bucketing and Retention

## Lesson Objectives

Apache Cassandra fits many systems that continuously write events such as telemetry, access logs, notifications, and state transitions. The hard part of the design is not storing a single event, but **storing millions of events under an access key, reading them in order, bounding partition sizes, and expiring old data while keeping the system operationally stable**.

Within the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson focuses on two tightly coupled decisions:

1. **Bucketing**: dividing events into partitions by time or shards so each read/write has a bounded scope, avoiding unbounded partitions and reducing hotspot risk.
2. **Retention**: specifying how long events are kept, which TTL/storage strategy to use, and how to handle late-arriving, modified, or expired events.

After this lesson, you will be able to:

- Translate an event query contract into a partition key, clustering key, and consistent bucketing rules.
- Estimate partition size from write rate, row size, workload skew, and bucket duration.
- Write CQL for an event table with `TTL`, range queries, `LIMIT`, and pagination.
- Distinguish **event occurrence time**, **ingestion time**, and **write time**, along with their impact on TTL.
- Explain tombstones, compaction, repair, replication/consistency, and practical limitations of data expiration.
- Implement bucket selection and TTL logic from a Java application, including expiration edge cases and UTC boundaries.

## 1. Starting from How the Application Reads Events

Suppose a Java service ingests telemetry from devices across multiple tenants. Each event contains:

```text
tenant_id, device_id, event_id, event_time,
received_at, event_type, severity, payload
```

The APIs have the following illustrative requirements:

| ID | Need | Mandatory Inputs | Order / Limits |
| --- | --- | --- | --- |
| Q01 | View the 50 newest events for a device on a UTC day | `tenant_id`, `device_id`, `day_bucket` | `event_time DESC`, 50 rows |
| Q02 | View device events in `[09:00, 10:00)` UTC | Tenant, device, day, two bounds | `event_time DESC`, paginated |
| Q03 | View events across seven UTC calendar days | Tenant, device, list of days | Ordered across the full range, max 100 rows/request |
| Q04 | Look up one event by `event_id` alone | Tenant, event ID | One event |
| Q05 | Find all `CRITICAL` events in a tenant/day | Tenant, day, severity | List across multiple devices |

Q01–Q02 form a natural query family: the application always knows the **device** and **day**, and reads rows within that day chronologically. Q03 can invoke the same table multiple times and merge results, provided the day count is reasonably capped. Q04 and Q05 are **different access paths**; they cannot be served efficiently by a table designed for one device/day.

Before choosing a bucket, clarify questions that product specs often overlook:

- Does "last seven days" mean **seven calendar days** or a **sliding 7 × 24-hour window**? The two can touch different numbers of buckets.
- Are events ordered by device-reported `event_time` or server-assigned `received_at`?
- What are the largest tenant, the noisiest device, and the peak write rate?
- When a device sends data **multiple days late**, should history still display it or may it be dropped?
- Is retention measured from **when the event occurred** or from **when the service received it**?
- How long might a user paginate through pages, and is it acceptable for events to expire between two page fetches?

These are business decisions that directly change the partition key, TTL, and how the application queries data.

## 2. What Is a Bucket and Why Do We Need It?

A **bucket** is a value computable from an event—usually derived from time—used as part of the partition key. Instead of piling all events for a device into an unbounded partition, we split them by day, hour, or another clearly defined interval.

Example using **UTC calendar day of `event_time`** as the bucket:

```text
Partition (tenant-A, device-42, 2026-11-20)
    (2026-11-20T23:58:00Z, event-e3)
    (2026-11-20T18:10:00Z, event-e2)

Partition (tenant-A, device-42, 2026-11-21)
    (2026-11-21T09:12:00Z, event-e5)
    (2026-11-21T08:00:00Z, event-e4)

Partition (tenant-A, device-42, 2026-11-22)
    (2026-11-22T00:02:00Z, event-e6)
```

These partitions are distributed by the token of the **entire composite partition key**. Rows inside a partition are organized by clustering columns; the design assumes descending time order.

Buckets deliver two clear benefits:

1. **Bound growth per logical key**: a device/day partition does not accumulate years of history forever.
2. **Direct read-scope targeting**: when an API asks for one device/day, the application knows the exact partition to access.

Buckets also introduce trade-offs: queries spanning multiple days must read **multiple partitions**, merge result streams, and manage pagination. Too-small buckets increase fan-out; too-large buckets cause oversized/hot partitions.

### 2.1. Choosing Bucket Width from Real Data

Rough estimation:

```text
rows_per_bucket ≈ events_per_second_of_hottest_device × bucket_seconds
raw_bytes_per_bucket ≈ rows_per_bucket × average_raw_event_bytes
```

Suppose the busiest device writes **25 events/second** continuously, with each event averaging about **600 bytes of raw business data**:

| Bucket | Projected Events | Projected Raw Data |
| --- | ---: | ---: |
| 1 minute | 1,500 | 0.9 MB |
| 1 hour | 90,000 | 54 MB |
| 1 day | 2,160,000 | 1,296 MB (~1.3 GB) |
| 7 days | 15,120,000 | 9,072 MB (~9.1 GB) |

This is purely an **assumption-based estimate**, excluding storage overhead, partition indexes, tombstones, SSTables, compaction, compression, or replication. It is **not a universal safe partition threshold**. If a device bursts to 200 events/second, peak-hour numbers must be recalculated using the burst rate rather than 25 events/second.

In this example, an **hourly** bucket may be a better candidate to test than a daily bucket for high-load devices. However, a full-day query will need to look up/read up to 24 hourly buckets for that device. Measure both **multi-bucket read latency** and **write load on the hottest partition** before finalizing.

### 2.2. Comparing Bucket Granularities

| Bucket | Suitable Read Path | Risks to Measure |
| --- | --- | --- |
| Month | Light history, low event rates, frequent full-month views | Long months can still produce large partitions |
| Day | Daily queries dominate, moderate traffic | Hot devices can still write too much in a day |
| Hour | Heavy traffic, hour-range reads common | Full-day/week queries must read many partitions |
| Minute | Extremely dense streams and very narrow queries | Fan-out and metadata grow for longer ranges |
| Time + shard | One logical key is too hot even inside a single bucket | Must read/merge multiple shards for a full-bucket list |

Choose buckets from **maximum, p95/p99 distributions, and query characteristics**, not merely from cluster-wide averages. A partition key that works great for typical devices can still fail for a handful of high-frequency devices.

### 2.3. Standardizing Bucket Calculation

Specify unambiguously:

- **Source timestamp**: device `event_time`, or system `received_at`?
- **Timezone**: UTC or a business timezone? This lesson uses **UTC** on both write and read paths.
- **Bucket boundary**: half-open `[startInclusive, endExclusive)`. An event at exactly 00:00:00Z on a new day belongs to the new day.
- **Late-arriving events**: if bucketed by `event_time`, a day-20 event arriving at the server on day 21 still goes into the day-20 bucket.
- **Timestamp edits**: if `event_time` is part of the primary key, editing the time may require deleting the old key and writing the new key.

A system that computes buckets using `received_at` on writes while querying by `event_time` on reads loses location consistency: data exists in Cassandra, yet the API looks in the wrong partition.

## 3. CQL: Event Table by Device/Day

First examine a **UTC daily bucket** since Q01–Q02 always know the day and a single device. Schema:

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
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Analysis:

- `(tenant_id, device_id, day_bucket)` is a **composite partition key**; all three components together identify one partition, not three independent indexes.
- `event_time` is the **first clustering column**, supporting chronological ordering and intra-day range predicates.
- `event_id` is the **second clustering column**, distinguishing events with identical timestamps. A random UUID provides a deterministic key-value tie-breaker, **not proof of causal order** when timestamps match.
- `event_type`, `severity`, and `payload` are event payload columns, not inherently efficient filter paths.

### 3.1. Writing Events

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

The `?` placeholders are bind markers for an application prepared statement. If running directly in `cqlsh`, supply valid literals. The write path must compute `day_bucket` from UTC-normalized `event_time` **before binding**.

If a producer resends **the exact same event**, the application should reuse the same `event_id`, `event_time`, and bucket. When two writes share the exact same full primary key, Cassandra performs an upsert on the same logical row. Conversely, if a fresh event ID is generated on every retry, or if timestamp/bucket changes, duplicate rows can appear.

Key-identical upserts are only part of idempotency: rewritten cells, write timestamps, and TTLs can alter outcomes. If tenant-wide uniqueness of event IDs or cross-bucket deduplication is required, enforce dedicated ID/deduplication rules.

### 3.2. Reading the Newest Events of the Day

```sql
SELECT event_time, event_id, event_type, severity, payload, received_at
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Q01 provides the full partition key, and the table has `DESC` clustering, so it reads newest first without tenant-wide sorting. `LIMIT 50` only caps **the number of rows returned** by the query; it does not guarantee Cassandra physically reads only 50 rows if tombstones or filtered rows are present.

### 3.3. Reading an Intra-Day Range

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

The half-open interval `[fromInclusive, toExclusive)` avoids duplicate events when stitching contiguous windows. Both bounds must fall within the queried bucket; for ranges crossing UTC midnight, the application splits the query into multiple parts.

Example:

```text
Request [2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)

Read 1:
  day_bucket = 2026-11-20
  event_time >= 2026-11-20T23:45:00Z
  event_time <  2026-11-21T00:00:00Z

Read 2:
  day_bucket = 2026-11-21
  event_time >= 2026-11-21T00:00:00Z
  event_time <  2026-11-21T00:15:00Z
```

Two partitions **do not share a default global order** merely from `CLUSTERING ORDER BY`. The application must merge them by `(event_time DESC, event_id DESC)` if the UI requires a unified list.

## 4. Retention: Choose the Policy Before Configuring TTL

**Retention** answers the question: "how long is an event allowed to exist and remain queryable?" This is a business policy and can differ among standard telemetry, critical alerts, security logs, or audit records.

Example requirements:

```text
Standard telemetry: retain 14 days
Critical alert events: retain 90 days
Mandatory audit events: retain per separately approved compliance policy
```

When applying TTL in Cassandra, distinguish **logical expiration of query results** from **when physical bytes are reclaimed**. Expired data stops appearing as live data, yet tombstones and older versions can remain on disk until compaction and deletion-safety conditions are satisfied.

### 4.1. Is Retention Measured from Write Time or Occurrence Time?

Suppose retention is **14 days** and an event has:

```text
event_time:    2026-11-01T10:00:00Z
received_at:   2026-11-05T10:00:00Z
retention:     14 days
```

Two different policies:

| Policy | Start Reference | Business Expiration Timestamp |
| --- | --- | --- |
| 14 days **after write/receipt** | Nov 05 at 10:00Z | Nov 19 at 10:00Z |
| 14 days **after event occurrence** | Nov 01 at 10:00Z | Nov 15 at 10:00Z |

This matters for **late-arriving events**. If a fixed 14-day TTL is applied at write time, an event arriving 4 days late stays until Nov 19—18 days after it occurred. If the product commits to deleting history 14 days after `event_time`, a fixed write-time TTL is insufficient.

### 4.2. Table-Level Default TTL

For a policy of "retain each value for **14 days from write time**," you can configure:

```sql
CREATE TABLE device_events_by_day_ttl (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 1209600;
```

`1209600 = 14 × 24 × 60 × 60` seconds. `default_time_to_live` automatically applies a default TTL to values written to the table, per Cassandra rules. The TTL counts from **write time**, rather than reading the row's `event_time`.

The `device_events_by_day_ttl` schema is only an **illustrative variant** of the table in Section 3. The application should pick **one real schema matching its policy**, not create both tables simply because this example uses two names.

TTL is not a scheduled `DELETE WHERE day_bucket < ...` job. Expired data is marked non-live, and physical removal depends on compaction, tombstone/grace period, and replica state. Never use the disappearance of SSTable files as the sole metric for data-access guarantees.

### 4.3. Per-`INSERT` TTL

When events have different lifetimes or retention is measured from `event_time`, pass TTL per write:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

The `TTL` value is a **duration in seconds from write time**, not an absolute expiration timestamp. For event-time retention, the application should compute:

```text
expires_at = event_time + retention_duration
remaining_seconds = expires_at - current_time

If remaining_seconds <= 0:
    event has already expired per policy; do not write to this TTL table
If remaining_seconds > 0:
    INSERT ... USING TTL remaining_seconds
```

For example, an event occurring at 10:00 on Nov 01 with 14-day retention arrives at 10:00 on Nov 05: remaining TTL is **10 days** at write time, so expiration stays near Nov 15. Actual expiration precision depends on second-level granularity, system clocks, and Cassandra TTL semantics; synchronize machine clocks and define acceptable skew.

If a `CRITICAL` event must be retained 90 days while ordinary events are kept 14 days, document this rule in the data contract and supply the corresponding TTL; do not blindly apply a 14-day default to every row. When mixing multiple TTLs in the same table and partition, carefully verify tombstone and compaction effects.

### 4.4. TTL Applies to Cells; Rewriting Can Shift Expiration

TTL in Cassandra attaches to **written cell values**, not to an automatic counter derived from the bucket name or an abstract "event" object. Cells within the same row can have different TTLs if the application updates them in separate statements.

Implications to understand:

- Rewriting a row with a new TTL can **refresh the expiration time** of the rewritten cells.
- An `UPDATE` modifying only a subset of columns can leave columns with differing lifetimes.
- Querying the remaining TTL of a specific column via the `TTL` function helps verify policy enforcement on sample data:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 10;
```

`TTL(payload)` returns remaining seconds for a live cell with a TTL; `null` may indicate either no TTL or an absent cell, so do not infer whole-row status from a single column alone. TTL configuration must account for **upserts, replays, and mutations**.

## 5. How Should Bucketing and Retention Be Combined?

Bucketing and TTL solve **two independent concerns**:

- Bucketing governs **routing path and partition size**.
- TTL governs **how long written data remains live**.

A partition with a **daily** bucket and a **14-day** TTL is still a **one-day** partition; after that day ends, the application continues reading it until the data inside expires. TTL does not turn a daily bucket into a 14-day bucket.

### 5.1. Choose Buckets from Load, Retention from Business Rules

Suppose a device produces 2 million events/day and APIs mainly read one hour. A retention of just 7 days **does not mean daily buckets are sensible**: 2 million rows in a daily partition may still create concerning size or hotness. Conversely, a device producing 50 events/day retained for 180 days likely does not need minute buckets.

Document decisions as paired specifications:

```text
Partition scope: (tenant_id, device_id, hour_bucket)
Retention: 14 days from event_time
Primary read: [from, to) max 6 hours/HTTP request
Pagination: 50 rows/fetch; max 6 hourly buckets on the primary read path
Exception: events arriving more than 14 days late are routed to separate handling
```

**Watch boundaries:** a strict 6-hour sliding window can touch **seven** hourly buckets if its endpoints do not align on hour boundaries. Count actual buckets intersected by the half-open interval when enforcing API limits, rather than assuming bucket count equals hours of duration.

### 5.2. Querying Expired Data

A screen requesting "events from two months ago" against a 14-day table needs defined behavior: return empty results, return a range-limit error, or route to a historical archive store if the product supports one.

Never fan out across hundreds of buckets "just in case" for events past the retention policy. The application can reject inputs outside the allowed window before issuing CQL; this check protects resources and communicates limits clearly to users.

### 5.3. Retention Does Not Equal Instant Whole-Partition Deletion

With cell-level TTLs, events in the same bucket can expire at different times—especially with late arrivals or multiple retention policies. Tombstones can remain after data ceases to be readable.

Never schedule whole-partition drops solely because the bucket date has passed if some events inside are still within retention. Conversely, if legal compliance requires **strictly timed physical erasure**, evaluate storage/deletion mechanisms and auditability; relying on TTL alone and assuming SSTables vanish right at expiration is insufficient.

## 6. Tombstones, Compaction, and Repair

### 6.1. Why Does TTL Create Tombstones?

Cassandra stores data in immutable SSTables on disk. When data hits its TTL, Cassandra must track that the value is deleted so stale data in another replica or SSTable does not **resurface**. Tombstones are part of that deletion-tracking mechanism.

Suppose an API uses `LIMIT 50` on a partition where many recent events have expired via TTL. The query may traverse many tombstones before gathering 50 live rows. Therefore:

- **Fewer returned rows** does not mean **less data scanned**.
- Monitor tombstones scanned, large partitions, SSTables-per-read, and p95/p99 latency.
- Test near the end of retention windows, with mixed TTLs, and under frequent deletes.

### 6.2. Compaction Suited to Time-Series Data

For mostly append-only tables with few updates/deletes and relatively uniform cell lifetimes, **TimeWindowCompactionStrategy (TWCS)** is an option worth evaluating:

```sql
-- Illustrative configuration; measure against real data and write schedule.
ALTER TABLE device_events_by_day_ttl
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
```

TWCS groups SSTables by **time windows of storage write timestamps**, **not** by the `day_bucket` value in the partition key. Thus a **daily bucket** and a **one-day compaction window** are two separate concepts; sharing the word "day" does not guarantee they stay aligned.

Situations that make time-window compaction less suitable or require extra evaluation:

- Rewriting/updating old records over long spans.
- Late-arriving data and backfills producing write-timestamp patterns that diverge from normal ingestion.
- Data within the same SSTable having wildly different lifetimes.
- Frequent deletes/updates on older partitions.

Never default to TWCS merely because a table name ends in `_by_day`, and never blindly set `compaction_window_size` equal to TTL without understanding the write pattern.

### 6.3. Repair and Deletion Safety Windows

Replication maintains multiple replicas of a partition; consistency level governs read/write acknowledgments. During network partitions, a replica may miss a mutation. **Repair** synchronizes replicas using Cassandra's anti-entropy mechanisms.

Tombstones can only be safely purged once conditions tied to **grace period, replica state, and compaction** are met. `gc_grace_seconds` relates to deletion safety; reducing it arbitrarily can increase the risk of deleted data resurrecting in scenarios where replicas missed deletes. Align repair schedules, down-node handling, and deletion policies with operations before tuning it.

Even reading/writing at `LOCAL_QUORUM` in a datacenter with an appropriate replication factor **cannot** fix oversized partitions, broken range queries, or vague retention policies. Consistency adjusts replica acknowledgments—it does not turn a device/day table into an arbitrary multi-field search path.

## 7. Java: Computing UTC Buckets and Event-Time TTL

The example below shows how a Java application computes `day_bucket` and remaining TTL from **event time**, then binds them to a prepared statement. It uses **DataStax Java Driver 4.x** with `device_events_by_day` (without a table-level default TTL).

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class EventWriter {
    private static final Duration RETENTION = Duration.ofDays(14);

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public EventWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO device_events_by_day (" +
            "tenant_id, device_id, day_bucket, event_time, event_id, " +
            "received_at, event_type, severity, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    // true: write sent; false: event already expired per policy.
    public boolean write(
        String tenantId, UUID deviceId, UUID eventId,
        Instant eventTime, Instant receivedAt,
        String eventType, String severity, String payload
    ) {
        LocalDate bucket = eventTime.atZone(ZoneOffset.UTC).toLocalDate();
        Instant expiresAt = eventTime.plus(RETENTION);
        long secondsLeft = Duration.between(clock.instant(), expiresAt).getSeconds();

        if (secondsLeft <= 0) {
            return false; // Route to stale-data handling flow if needed.
        }

        int ttlSeconds = Math.toIntExact(secondsLeft);
        BoundStatement statement = insert.bind(
            tenantId, deviceId, bucket, eventTime, eventId,
            receivedAt, eventType, severity, payload, ttlSeconds
        );
        session.execute(statement);
        return true;
    }
}
```

Explanation of decisions:

1. `LocalDate` maps to CQL `date`, `Instant` to `timestamp`, and `UUID` to `uuid`. The bucket is derived in **UTC from `eventTime`**, not from server ingestion time.
2. `expiresAt` is the business deadline measured from **event occurrence**; TTL is the **remaining seconds at write preparation time**.
3. Already-expired events are not written to the 14-day table. If product requires keeping them for reconciliation, define a separate stale-data path.
4. `Math.toIntExact` fails fast if TTL overflows `int` rather than silently truncating. This example assumes 14-day retention, so TTL normally fits well within range.
5. Returning `true` here means `execute` completed without throwing in this call; it **does not prove** data is present on every replica or in all other business projections.

Production systems also require tenant authorization, event ID validation, payload size limits, retry/idempotency handling, timeouts, consistency levels, backpressure, and monitoring. Application and Cassandra node clocks must be properly synchronized: TTL follows Cassandra's clock semantics, so small skew may occur between expected and actual expiration instants.

### 7.1. Reading a Range from Java

A prepared statement for Q02:

```java
PreparedStatement byRange = session.prepare(
    "SELECT event_time, event_id, severity, payload " +
    "FROM device_events_by_day " +
    "WHERE tenant_id = ? AND device_id = ? AND day_bucket = ? " +
    "AND event_time >= ? AND event_time < ?"
);

BoundStatement bound = byRange.bind(
    tenantId, deviceId, utcDay, fromInclusive, toExclusive
).setPageSize(50);
```

`setPageSize(50)` sets the driver's target rows per page, **not a query-wide `LIMIT 50`**. If an endpoint returns just one page, explicitly control rows read and paging state; synchronously iterating the entire `ResultSet` can trigger fetching subsequent pages.

The application must verify `fromInclusive < toExclusive` and that both bounds fall within the queried bucket. If a range spans days, split by UTC day and read the relevant partitions; never pass one `utcDay` expecting the next day's events to show up.

## 8. Late-Arriving Data, Backfills, and Retention Changes

### 8.1. Late-Arriving Events

Suppose today is Nov 21 and a device sends an event that occurred on Nov 19. If bucketed by `event_time`, the event lands in the Nov 19 partition; with 14-day event-time retention, remaining TTL is around 12 days. The late record is inserted at its clustering position by occurrence time, not necessarily at the top of the latest list.

Ask accordingly:

- Are late events allowed after **N days**?
- Does the pipeline replay bursts after a device loses connectivity?
- Must the API reflect **occurrence order** or **ingestion order**?
- Should events past retention be dropped, archived, or routed for investigation?

Bucketing by `received_at` can make sense if product primarily views events by **system receipt time**, but that is a **different query contract**. Do not change the bucketing source while keeping the same `WHERE event_time` query and assuming a single partition read will be complete.

### 8.2. Backfills and Fixing Historical Data

Backfills write into historical buckets, yet **write-time TTL** and **compaction windows** may not match the event's occurrence time. Design for:

- Backfill rate limits so replicas are not overwhelmed by write spikes.
- How to compute remaining TTL for older event times.
- Identity rules so replays do not create duplicate rows or unintentionally extend TTLs.
- Impact on compaction, tombstones, and active read SLAs.

If you must modify `event_time` when it sits in the primary key, you generally must write a new row under the new key and delete the old data per business rules. This creates tombstones; handle partial failures between the two writes and avoid prolonged duplicate records.

### 8.3. Changing Retention Periods

Suppose events were previously kept for 30 days and product changes that to 14 days. Changing `default_time_to_live` on the table **does not automatically rewrite TTLs on previously written data**. Assess impact on existing data, allowed query windows, cleanup strategies, and migration/testing plans. When increasing retention, data that **already expired and was purged** does not come back.

Retention changes should be treated as data-contract changes, because they simultaneously affect users, storage footprint, and maintenance jobs.

## 9. When Buckets Are Still Too Hot: Controlled Sharding

If a device writes too densely even with hourly buckets, consider adding `shard_id` to the partition key to spread load:

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

`hour_bucket` must be a normalized UTC top-of-hour timestamp, not an arbitrary instant. For example, `2026-11-21T09:00:00Z` represents `[09:00, 10:00)`. You can assign `shard_id = hash(event_id) mod N` using a hash function, type, and `N` that are fixed/versioned across producers.

In return:

- Looking up a known event ID can compute its shard if the mapping is known.
- Querying "the 50 most recent events for a device in an hour" **does not know every event's shard upfront**: the application must read up to `N` partitions and merge by clustering order.
- Increasing `N` without a versioning/migration strategy leaves old and new data under different shard schemes.
- Fan-out and read work scale with `N`; enforce API limits and measure latency on the hottest device.

Sharding is a tool for partition loads **measured to be too hot**; do not add it preemptively when daily/hourly buckets already meet requirements.

## 10. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Partitioning by `device_id` alone for all history | Unbounded partition growth | Choose buckets from queries and event rates |
| Picking daily buckets for all devices because it is "simple" | High-volume devices create large/hot partitions | Estimate peak rows/bytes per device and test hourly buckets |
| Bucketing by server time while reading by event time | Late data lands in a different partition from queries | Standardize one time source for writes and reads |
| Assuming 14-day TTL always counts from `event_time` | Late events survive longer than intended | Compute remaining TTL from `expires_at` for event-time policies |
| Assuming TTL expiration frees disk bytes immediately | Wrong capacity, physical erasure, and compaction assumptions | Understand tombstones, grace periods, compaction, and measure disk |
| Using `LIMIT 50` to guarantee a lightweight query | May scan tombstones or many buckets before gathering enough rows | Measure tombstones, fan-out, and cap query ranges |
| Picking TWCS solely because data has timestamps | Late updates and uneven TTLs degrade cleanup efficiency | Evaluate write patterns, TTLs, and compaction windows via measurement |
| Arbitrarily shrinking `gc_grace_seconds` to purge faster | Increases resurrection risk if replicas missed deletes | Align repair/deletion policy with operations |
| Replaying events with new IDs or refreshed TTLs | Duplicate data or unintended lifetime extension | Use stable IDs, deduplication rules, and fixed retention |
| Treating a pagination token as an immutable snapshot | Expiring or newly arriving events alter the result set | Define paging semantics and consistency bounds |

## 11. Pre-Deployment Checklist

| Check | Verifiable Criterion |
| --- | --- |
| Is the primary query shape clear? | Required inputs, range, sort, `LIMIT`/paging, p95/p99 documented |
| How are buckets computed? | UTC rule, event vs. receipt time, and boundaries written into contract |
| Are buckets small enough to prevent large/hot partitions? | Peak events/s, max rows/bytes documented and tested on heaviest device |
| Do read ranges bound fan-out? | API caps buckets/days and total rows/bytes scanned |
| From what reference does TTL count? | Event-time vs. write-time retention explicitly specified |
| How are events older than retention handled? | Drop/archive/investigate rule exists; never write zero or negative TTL |
| How are replays, backfills, and `event_time` edits handled? | Stable IDs, dedupe, retries, rate limits, and key-change logic |
| Is compaction suitable? | Compared TWCS against write/TTL patterns; observed SSTables and tombstones |
| Are repair and deletion operated safely? | Repair schedule, down-replica handling, and `gc_grace_seconds` defined |
| Are consistency and replication adequate? | Tested node failures, read-after-write, latency, and multi-DC impact |
| Does Java/driver paging behave correctly? | No unbounded fetching; paging tokens tied to query shape and tenant auth |

In staging, simulate normal devices, very hot devices, late events, identical-timestamp events, expired events, and disconnected devices replaying backlogs. Verify CQL validity, measure read/write p95/p99, tombstones scanned, partition sizes, and partitions touched. A CQL statement running on a few sample rows does not prove bucketing and retention hold up in production.

## 12. Practice Exercise

A user-activity tracking service stores events:

```text
tenant_id, user_id, event_id, occurred_at, received_at,
event_type, screen_name, payload
```

Business requirements:

1. View the 100 newest events for a user on **one UTC day**.
2. View a user's events within a **6-hour** sliding window.
3. Retain ordinary events for **7 days from `occurred_at`**.
4. Some offline mobile clients can upload events **3 days late**.
5. The heaviest user can emit 40 events/second for several hours.

Answer the following:

1. Propose a partition key and clustering key for the daily query; explain the role of `event_id` when timestamps match.
2. Calculate row counts in a daily bucket vs. an hourly bucket at a sustained 40 events/second. What else must be measured before locking the choice?
3. An event occurred at 12:00 on Nov 01 and reached the server at 12:00 on Nov 04. With 7-day retention from `occurred_at`, what remaining TTL is written?
4. How many hourly buckets can a 6-hour sliding window touch at most? How must the application merge results?
5. Why might `default_time_to_live = 604800` fail requirement 3 when data arrives late?
6. Give two scenarios where data is no longer readable yet still consumes disk space.

**Reference guidance:** For daily queries, a candidate is `PRIMARY KEY ((tenant_id, user_id, day_bucket), occurred_at, event_id)` with descending clustering; a user sustaining 40 events/second generates `3,456,000` rows/day or `144,000` rows/hour before accounting for row size. An event arriving 3 days late has roughly **4 days of TTL** left under a 7-day policy from `occurred_at`. A 6-hour sliding window can touch **up to seven hourly buckets**; partitions must be read and merged by `occurred_at DESC, event_id DESC` with row caps and paging. A default 7-day TTL at write time would extend survival beyond the event's occurrence window. Tombstones, expired cells awaiting compaction, and older SSTable copies can keep consuming disk after queries stop returning expired cells.

## Conclusion

Event data design in Cassandra must lock down **read paths, bucket granularity, and retention policy together**. Buckets control partition scope and fan-out; clustering keys serve ordering and range predicates; TTL controls value lifetime—with semantics governed either by write time or by an application-computed TTL from event time. Late-arriving events, replays, tombstones, compaction, repair, and multi-bucket queries must be factored in from the start. A trustworthy design pairs concrete CQL with explicit API bounds and benchmarks on representative workloads.
