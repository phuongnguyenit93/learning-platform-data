# Optimizing Time-Series Queries Using Bucketing

## 1. Problem: Reading the 20 Latest Events When a Partition Holds Years of History

An **Apache Cassandra** application ingests continuous sensor telemetry. Each device emits dozens of events per second; users typically request the **20 latest events** or events from the **past 15 minutes**. Initial design:

~~~sql
CREATE TABLE events_by_sensor_unbounded (
    sensor_id text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

This design has one strength: knowing `sensor_id` pinpoints a single partition with rows ordered by time. However, if a sensor runs for years, **every event for that sensor lands in one logical partition**. The partition grows massive, runs hot, accumulates SSTables, inflates memory/read costs, and makes maintenance unpredictable.

**Time bucketing** solves this by adding a time unit—hour, day, week, or fixed interval—**into the partition key**. Instead of one unbounded partition per sensor, data is divided into time-bounded partitions:

~~~text
Before:
  partition (sensor-7) → events from 2020 ... 2026 ... unbounded

After (daily bucket):
  partition (sensor-7, 2026-11-19) → Nov 19 events
  partition (sensor-7, 2026-11-20) → Nov 20 events
  partition (sensor-7, 2026-11-21) → Nov 21 events
~~~

Queries can then target **only the relevant time partitions** rather than letting one partition accumulate history forever. In exchange, when a query spans multiple days or hours, the application must **query multiple buckets and merge the results**.

**Learning Objectives:**

- Understand how time buckets interact with **partition keys**, clustering keys, tokens, and replicas.
- Choose bucket sizes based on **write rate, single-partition footprint, query time span, and fan-out**.
- Write CQL for **half-open [start, end)** intervals, including across bucket boundaries.
- Implement Java Driver 4.x multi-bucket reads, applying `LIMIT` properly and merging/sorting results.
- Distinguish time buckets from **hot-partition sharding**, TTL/TWCS, indexes, and token scans.
- Use tracing and metrics to measure impact instead of guessing from schemas alone.

This lesson belongs to the **Query Tuning** chapter for wide-column Cassandra. Examples are for lab use; adapt DC names, RF, and version-specific features to your environment.

## 2. Concepts to Distinguish Before Designing

### 2.1. Partition Keys Route; Clustering Keys Sort

In Cassandra, the **partition key** is hashed into a **token**. The token, `NetworkTopologyStrategy`, and replication factor determine which replicas own that partition. **Clustering columns** determine row ordering **within that partition**.

| Component | Example | Purpose | Limit |
| --- | --- | --- | --- |
| **Partition key** | `(sensor_id, bucket_day)` | Selects the partition for read/write routing. | Omitting a partition key component prevents direct single-partition queries. |
| **Clustering key** | `(event_time, event_id)` | Orders by time, disambiguates same-timestamp rows, enables contiguous range reads. | Does not change the partition's token or replica set. |
| **Bucket** | `2026-11-21` (UTC) | Splits one sensor's history into bounded partitions. | Does not create global ordering across partitions. |
| **Token range** | An arc on the token ring | Distributes partitions across nodes; used for token scans/repairs. | Not a business time window. |
| **TTL** | 30 days from mutation write time | Logically expires data over time. | Does not alter the partition key or immediately delete SSTables. |

**Key point:** placing `bucket_day` inside the **partition key** is what makes time bucketing split partitions. Adding `bucket_day` merely as a regular column in `PRIMARY KEY ((sensor_id), event_time)` does not split the sensor's partition at all.

### 2.2. Why `LIMIT 20` Alone Is Insufficient

`SELECT ... WHERE sensor_id=? LIMIT 20` can be fast when the newest rows sit at the head of the clustering order. Yet `LIMIT` bounds **returned rows**, not **partition size**, **accumulated historical data**, **compaction overhead**, or **tombstones traversed** to find 20 live rows.

With TTLs or `DELETE`s, Cassandra may still reconcile rows across multiple SSTables and skip tombstones. Oversized partitions also make broad scans, streaming, repairs, and recovery far heavier. Bucketing is a **data-modeling bound** against those risks, not a replacement for SSTable/TTL tuning.

## 3. Hourly, Daily, or Shorter Buckets?

There is no rule saying "Cassandra always uses daily buckets." Right sizing balances two competing forces:

1. **Longer buckets:** fewer partitions per read, but each partition can grow larger and hotter.
2. **Shorter buckets:** smaller partitions, but longer time-range queries touch more partitions, raising metadata and request fan-out.

### 3.1. Rough Sizing Formula

Suppose a sensor has:

- `λ`: average/peak write rate in **events/second**.
- `T`: bucket duration in **seconds**.
- `B`: estimated storage size per event **on one replica** (including desired overhead) in bytes.

Rough partition footprint per bucket:

~~~text
events_per_bucket   ≈ λ × T
bytes_per_partition ≈ λ × T × B

Example λ = 50 events/second, B = 600 bytes/event:

1-day bucket    : 50 × 86,400 × 600 = 2,592,000,000 B ≈ 2,592 MB
1-hour bucket   : 50 ×  3,600 × 600 =   108,000,000 B ≈   108 MB
15-min bucket   : 50 ×    900 × 600 =    27,000,000 B ≈    27 MB
~~~

These are **estimates**, not exact predictions: real sizes depend on compression, encoding, metadata, tombstones, payload variance, updates, SSTables, and compaction. **RF = 3 does not triple one replica's partition size**, though it multiplies total cluster storage across replicas. **Peak/hot sensor** rates—not cluster-wide averages—govern oversized-partition risk.

### 3.2. Fan-Out When Querying a Time Range

A query spanning `W` seconds touches roughly `ceil(W/T)` buckets, **plus one extra bucket when start and end cross bucket boundaries**. Exact bucket counts depend on endpoint alignment.

| Bucket size | Reading 15 minutes | Reading 3 hours | Reading 7 days |
| --- | --- | --- | --- |
| 1 day | Usually 1, occasionally 2 partitions | Usually 1, occasionally 2 | ~7–8 partitions |
| 1 hour | Usually 1, occasionally 2 | ~3–4 partitions | Up to 168–169 partitions |
| 15 minutes | Usually 1–2 partitions | ~12–13 partitions | Up to 672–673 partitions |

Figures illustrate **a single sensor** with half-open ranges. Querying 10,000 sensors multiplies total requests and partitions dramatically. Thus **you cannot tune partition size while ignoring fan-out**.

### 3.3. Practical Decision Guide

| Dominant workload | Bucket to evaluate | What else to measure |
| --- | --- | --- |
| A few events/min, single-day queries | Daily | Partition size after months, TTLs, tombstones. |
| Tens of events/sec per sensor, reads spanning minutes–hours | Hourly or 15-minute | Peak partition size, partitions/request, p99 latency. |
| Ultra-hot sensor, many writers, 1 hour still oversized | Shorter window or time bucket + **shard** | Write hotspots, concurrency, increased read fan-out. |
| 6-month historical reporting | Dedicated daily/weekly rollup/summary table | Avoid scanning thousands of raw event buckets. |
| "All sensors at site X in 1 hour" | Dedicated table keyed by `site_id` and bucket | Use a query-driven table instead of filtering `sensor_id` table. |

Never treat a single fixed MB threshold as a universal Cassandra SLA. Acceptable partition size must be validated against **read latency, row count, SSTables, heap/off-heap, compaction/repair pressure, and real hardware**.

## 4. Designing a Day-Bucketed Table for Queries

### 4.1. Full CQL Schema

Assuming a lab datacenter `dc1` with at least three nodes to support RF = 3 and `LOCAL_QUORUM`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_tuning
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_day (
    sensor_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Schema breakdown:**

- `sensor_id` and `bucket_day` form the **composite partition key**. Different days for the same sensor can hash to different tokens and replica sets.
- `event_time` is the leading clustering column, enabling time-slice reads within a partition. Having the day in the partition key **does not replace** clustering range predicates on `event_time`.
- `event_id` prevents events with identical `event_time` from overwriting each other. Clients should supply **deterministic IDs** so retries do not duplicate events.
- `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` reads newest events first **within each bucket**. It provides no global order across buckets.
- `payload` is a regular column: if payloads are large, consider a lightweight list table and a separate detail table; avoid `SELECT *` on hot paths.

### 4.2. Computing Buckets Consistently

Use **UTC** as the bucket timezone for this example:

~~~text
bucket_day(event_time) = UTC LocalDate of event_time

2026-11-20T23:59:59.999Z -> bucket_day 2026-11-20
2026-11-21T00:00:00.000Z -> bucket_day 2026-11-21
2026-11-21T23:59:59.999Z -> bucket_day 2026-11-21
~~~

Every Java/Python writer, ingestion job, and backfill must apply the **exact same bucket derivation function**. If a client in Vietnam uses local date (UTC+7) while the backend uses UTC, an event at 00:30 Vietnam time falls on the previous UTC day—UTC bucket queries will miss it unless writers agree.

If business logic requires buckets in a **store's local day**, explicitly store the **store's IANA timezone**, handle DST rules, and define business day boundaries cleanly. Never compute local day boundaries by adding a fixed 24 hours, since DST transitions yield 23- or 25-hour days. Throughout this lesson, all bucket math uses **UTC**.

### 4.3. Bucket by Event Time or Ingestion Time?

| Case | Bucket by `event_time` | Bucket by `ingested_at` |
| --- | --- | --- |
| User asks "events occurring between 08:00 and 09:00" | Better fit. | Can miss delayed/late-arriving events. |
| System monitors ingestion rate per minute | Does not reflect actual arrival time. | Better fit. |
| Backfilling events from last month | Writes into past buckets; can complicate TWCS windows. | Writes into current bucket; event-time queries need redesign. |
| Skewed device clocks | Risk of landing in the wrong bucket. | Easy ingestion tracking, yet diverges from event semantics. |

**Pick one semantics and document it clearly.** If both query patterns are vital, you usually need **two projection tables** with distinct partition keys or an aggregation pipeline, rather than misusing `ALLOW FILTERING` on non-key columns.

## 5. Querying Bucket Boundaries Properly: Half-Open Intervals

### 5.1. Why Use [start, end)?

Convention:

~~~text
[startInclusive, endExclusive)

CQL condition:
  event_time >= startInclusive
  AND event_time < endExclusive
~~~

Half-open intervals partition adjacent windows cleanly **without double-counting boundary timestamps**:

~~~text
UTC day 2026-11-20: [2026-11-20T00:00:00Z, 2026-11-21T00:00:00Z)
UTC day 2026-11-21: [2026-11-21T00:00:00Z, 2026-11-22T00:00:00Z)

An event at exactly 2026-11-21T00:00:00Z belongs solely to Nov 21.
~~~

`CLUSTERING ORDER BY ... DESC` **does not invert the meaning of `>=`**. It affects only storage/traversal order within the partition.

### 5.2. Inserting Data Spanning Two Days

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-20', '2026-11-20T23:45:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'temperature', '20.5');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-20', '2026-11-20T23:59:59Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature', '20.8');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-21', '2026-11-21T00:00:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'temperature', '21.0');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-21', '2026-11-21T00:40:00Z',
   123e4567-e89b-42d3-a456-426614174004, 'temperature', '21.2');
~~~

### 5.3. Querying One Bucket

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:30:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

Lab results return **23:45** and **23:59:59**. Because `bucket_day` is fixed, the query routes to **one partition** and slices the matching clustering range.

### 5.4. Crossing Midnight Requires Querying Two Buckets

To fetch **[Nov 20 23:30 UTC, Nov 21 00:45 UTC)**:

~~~sql
-- Bucket for Nov 20:
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:30:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

-- Bucket for Nov 21:
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:45:00Z';
~~~

These two results are **two sorted lists from two distinct partitions**. Cassandra does not merge them into a **globally** sorted `ORDER BY event_time DESC` list. The application must merge/sort or run a k-way merge.

**Common bug:** querying only the `bucket_day` of `start` while setting `event_time < end` into the next day. The Nov 20 partition does not contain events stored in the Nov 21 partition, so those events are silently missed.

## 6. Do Not Use `ALLOW FILTERING` as a Substitute for a Bucket Key

Example:

~~~sql
-- Not an efficient way to read a time range on this schema:
SELECT event_time, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
ALLOW FILTERING;
~~~

The **entire partition key** `(sensor_id, bucket_day)` is missing. Cassandra cannot route directly to a partition; if allowed by execution/version, it may scan vast amounts of data. `ALLOW FILTERING` **never turns a distributed scan into a cheap indexed lookup**.

| Business query | Table to consider |
| --- | --- |
| "Which events did sensor S emit in 15 minutes?" | `events_by_sensor_day` or `events_by_sensor_hour`. |
| "Which events did all sensors at site X emit in hour H?" | Dedicated projection keyed by `(site_id, bucket_hour)` with matching clustering key; monitor partition size/hotspots. |
| "Daily alert count per site?" | **Aggregate/rollup** table by site/day updated via a controlled pipeline. |
| "Lookup an exact event by `event_id`?" | Projection `event_by_id` with `event_id` as partition key if a primary access path. |

Cassandra intentionally **denormalizes data per query pattern** rather than relying on one generic table and expecting an optimizer to join/filter arbitrarily like relational SQL. Secondary indexes/SAI (on supported versions) serve specific niches, yet do not fix reads touching thousands of buckets due to missing partition keys.

## 7. Java Driver 4.x: Reading Multiple Buckets and Preserving Order

This example uses the **UTC day-bucketed** table, queries every day intersecting `[start, end)`, caps at **8 buckets**, and sorts results newest-first. To return the **50 newest events across the whole range**, each bucket only needs at most its **top 50 newest events**: any event ranked outside its own bucket's top 50 cannot make the global top 50 under a consistent comparator.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

public final class ReadEventsAcrossDayBuckets {
    private static final int GLOBAL_LIMIT = 50;
    private static final int MAX_BUCKETS = 8;

    private static final class Event {
        final Instant time;
        final UUID id;
        final String type;

        Event(Instant time, UUID id, String type) {
            this.time = time;
            this.id = id;
            this.type = type;
        }
    }

    public static void main(String[] args) {
        Instant from = Instant.parse("2026-11-20T23:30:00Z");
        Instant to = Instant.parse("2026-11-21T00:45:00Z");

        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("empty or reversed time range");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement readBucket = session.prepare(
                "SELECT event_time, event_id, event_type " +
                "FROM telemetry_tuning.events_by_sensor_day " +
                "WHERE sensor_id = ? AND bucket_day = ? " +
                "AND event_time >= ? AND event_time < ? LIMIT ?");

            List<Event> collected = new ArrayList<>();
            int bucketsVisited = 0;

            for (LocalDate day = from.atZone(ZoneOffset.UTC).toLocalDate();
                 day.atStartOfDay(ZoneOffset.UTC).toInstant().isBefore(to);
                 day = day.plusDays(1)) {

                if (++bucketsVisited > MAX_BUCKETS) {
                    throw new IllegalArgumentException(
                        "time range touches too many buckets");
                }

                Instant bucketStart =
                    day.atStartOfDay(ZoneOffset.UTC).toInstant();
                Instant bucketEnd =
                    day.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant();

                Instant sliceStart = from.isAfter(bucketStart)
                    ? from : bucketStart;
                Instant sliceEnd = to.isBefore(bucketEnd)
                    ? to : bucketEnd;

                BoundStatement query = readBucket.bind(
                        "sensor-7",
                        day,
                        sliceStart,
                        sliceEnd,
                        GLOBAL_LIMIT)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM);

                for (Row row : session.execute(query)) {
                    collected.add(new Event(
                        row.getInstant("event_time"),
                        row.getUuid("event_id"),
                        row.getString("event_type")));
                }
            }

            // Each bucket returns event_time DESC; the combined list
            // still needs global sorting (and a consistent tie-breaker).
            collected.sort(Comparator
                .comparing((Event e) -> e.time).reversed()
                .thenComparing(e -> e.id));

            int count = Math.min(GLOBAL_LIMIT, collected.size());
            for (int i = 0; i < count; i++) {
                Event event = collected.get(i);
                System.out.println(event.time + " " + event.id
                    + " " + event.type);
            }
        }
    }
}
~~~

**Key design choices in this example:**

1. `LocalDate` is derived from the **UTC event timestamp**, matching the write rule. CQL `date` takes `LocalDate`; `timestamp` takes `Instant`.
2. The loop stops once a bucket's **start >= endExclusive**, so a range ending cleanly at `00:00 UTC` never reads an unnecessary extra day.
3. Every read supplies the **full partition key** and narrows the clustering range within that day.
4. `MAX_BUCKETS` prevents accidental runaway fan-out; production should also enforce **deadlines, concurrency caps, byte/row limits, and rate limits**.
5. `LIMIT 50` per bucket is not a **global limit 50**: after merging, the code still sorts and slices the top 50 newest results.
6. Execution is sequential for clarity. To optimize latency, issue asynchronous requests with **bounded concurrency**, monitor coordinator/replica load, and cancel on deadline—never fire hundreds of unbounded concurrent calls.
7. `LOCAL_QUORUM` in `dc1` with RF = 3 requires two replica responses **per bucket query**. It does not establish an atomic cross-bucket point-in-time snapshot.

**Important caveat:** this keeps at most `MAX_BUCKETS × GLOBAL_LIMIT` events in RAM, suitable for short lists. For dashboards spanning millions of events or deep pagination, use a **streaming k-way merge / bounded heap and multi-bucket cursor** instead of buffering into a list. Sorting by `event_id` illustrates a tie-breaker; if multi-language consistency is needed, standardize UUID tie-breaker ordering and verify Cassandra's exact UUID ordering. When `bucket_day` is derived consistently from `event_time`, the same `event_time` never appears in two different day buckets.

## 8. Paginating and Fetching "Newest" Across Multiple Buckets

### 8.1. Avoid Misunderstanding `LIMIT` and Page Size

| Concept | Meaning | What it does NOT guarantee |
| --- | --- | --- |
| `LIMIT 50` in CQL | Returns at most 50 **live** rows from one partition/bucket query. | Does not guarantee the replica inspected at most 50 physical items; tombstones can force more. |
| Driver `page size = 100` | Splits one statement's results into pages to avoid buffering everything at once. | Does not cap total rows if the client keeps fetching. |
| "Global top 50" across 8 buckets | Picks the 50 newest events from the union of buckets. | Cannot be achieved via a single cross-partition `ORDER BY`. |
| Application cursor | Tracks continuation positions across all buckets. | Not identical to a single CQL statement's paging state. |

### 8.2. Controlled Multi-Bucket Pagination

For a table clustered by `event_time DESC, event_id ASC`:

1. Fix an explicit **query time window** and **maximum bucket count**.
2. Maintain a per-bucket **cursor** recording the last clustering position consumed (and query/page state if needed).
3. Pull a batch of candidates from each bucket into a **priority queue** with unified ordering.
4. Pop the newest events up to the API page size; retain cursors for any non-exhausted buckets.
5. On the next API page, resume **from each bucket's unconsumed position** rather than restarting from scratch.

Conceptual diagram:

~~~mermaid
flowchart LR
    A["Bucket day 19"] --> M["Merge by event_time + event_id"]
    B["Bucket day 20"] --> M
    C["Bucket day 21"] --> M
    M --> L["API page: 50 newest rows"]
    L --> P["Cursor: next read position per bucket"]
    P --> M
~~~

**There is no handy global `OFFSET`** across distinct partitions. Cassandra paging state belongs to one statement/page, is often unsuitable for public long-lived sharing, and cannot represent a multi-bucket merge order. If long-lived cursors are needed, build an authenticated, tamper-protected custom cursor token with expiration; when resuming via clustering keys, compare the full `(event_time, event_id)` pair so same-timestamp rows are never skipped.

### 8.3. Concurrent Writes Shift Results Between Pages

Cassandra provides no **cross-partition snapshot isolation** across sequential `SELECT` calls. While the API reads bucket A and then bucket B, concurrent writers may insert, update, or delete rows. Consequently:

- Two pages may observe slightly shifted datasets.
- A late-arriving event with an older `event_time` may land in an already-scanned bucket.
- Reuse timestamps and event IDs on retries to limit duplicates; if business logic demands consistency relative to a watermark, design an **ingestion watermark** or application-level snapshot.
- Bind cursors to a **fixed time window** rather than sliding `end = now` between page fetches.

This is inherent to **multiple distributed queries**, not a bug in the Java Driver or bucketing.

## 9. When One Bucket Still Runs Hot: Adding Controlled Sharding

Time bucketing caps historical depth, yet a sensor emitting 50,000 events/second can still overheat a **one-minute** partition. In that case, combine bucketing with **sharding**:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_hour_sharded (
    sensor_id text,
    bucket_hour timestamp,
    shard int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id, bucket_hour, shard), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Convention:

~~~text
bucket_hour = event_time truncated to UTC hour
shard = stable_hash(event_id) modulo S

Example S = 4:
  (sensor-7, 2026-11-21T08:00:00Z, shard=0)
  (sensor-7, 2026-11-21T08:00:00Z, shard=1)
  (sensor-7, 2026-11-21T08:00:00Z, shard=2)
  (sensor-7, 2026-11-21T08:00:00Z, shard=3)
~~~

**Benefit:** multiple shards spread writes across distinct tokens and replica sets, relieving single-partition pressure. **Trade-off:** reading all events for that sensor in that hour must query **all S shards** and merge/sort, multiplying request count per bucket by `S`. `stable_hash` must be **identical across all client languages**, not an unstable default hash function.

Never treat shard count as something you can bump from 4 to 8 anytime without affecting older data. Changing shard count requires **versioning in the key or dual-phase read logic** so readers still locate older events. Shard only after measuring write-rate or hot-partition bottlenecks; for read-heavy workloads, needless sharding hurts performance.

## 10. TTL, Bucket Deletion, and TWCS: Lifecycle Optimization, Not a Substitute for Buckets

### 10.1. Time Bucketing and TTL Solve Different Problems

- **Time bucketing:** caps partition growth and routes range reads to the right partitions.
- **TTL:** governs when cells/rows expire logically, normally measured from **write time**.
- **Compaction:** manages SSTables, versions, and tombstones per node, purging eligible dead data.
- **Anti-entropy repair:** synchronizes diverging replicas, critical wherever tombstones exist.

If retention is 30 days, a table can configure a default TTL:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_day_ttl (
    sensor_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000
  AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
  };
~~~

This **illustrates** `TimeWindowCompactionStrategy` (TWCS) for append-mostly time-series data; it is not an optimal template for every workload. `default_time_to_live = 2592000` is 30 days, and `gc_grace_seconds = 864000` is 10 days. Lowering grace must align with repair schedules, replication, version behavior, and zombie-data risk—never set 0 blindly just to free disk faster.

### 10.2. Backfill Trap: Event-Time Retention vs. Write-Time TTL

Suppose on **Nov 21** you backfill an event whose `event_time` was **Oct 1**. Writing with the 30-day default TTL normally starts the expiration clock **from the new write time**, rather than expiring immediately due to the old `event_time`. Likewise, TWCS groups SSTables by mutation write timestamp; distinguish **CQL write timestamp** from the **`event_time` column**.

If business rules require keeping **30 days from `event_time`**, the ingestion pipeline should compute:

~~~text
expiry_at = event_time + 30 days per business rule
remaining_ttl = expiry_at - now

If remaining_ttl <= 0: skip ingesting already-expired event,
or route to a separate backfill/archival policy.
If > 0: write with computed TTL within valid bounds.
~~~

CQL TTLs are integer seconds with version-specific upper limits; round cleanly, guard against skewed device clocks, and preserve idempotency. Never rewrite mutation `USING TIMESTAMP` to `event_time` to solve retention: that alters **last-write-wins**, tombstone reconciliation, and TWCS grouping, risking shadowed data or prolonged SSTable lifetimes.

### 10.3. Deleting a Whole Bucket Is Not "Drop Partition File"

~~~sql
-- Delete an entire bucket partition (in lab); does not immediately reclaim disk:
DELETE FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20';
~~~

This is a **partition deletion**, creating a tombstone under Cassandra semantics. It does not erase bytes from SSTables immediately, drop a dedicated file, or bypass repair. **Do not create a separate Cassandra table per day just to run `DROP TABLE` daily** without evaluating schema churn, metadata, and table-count overhead; partition-key bucketing is usually far simpler.

TWCS can drop fully expired SSTables cleanly for mostly append-only data with uniform TTLs and normal write timestamps. **Mixed TTLs, backfills, updates to past data, live rows sharing SSTables with tombstones, and out-of-sync replicas** can block whole-file drops. Nor is there a strict one-to-one mapping between a daily bucket key and a TWCS compaction window.

## 11. Tracing and Metrics to Verify Bucketing Actually Helped

Never declare "the query is faster" merely because `bucket_day` sits in the primary key. Measure the **same workload before and after** across reads, writes, and maintenance.

### 11.1. Lab Tracing

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

`CONSISTENCY` and `TRACING` are **cqlsh** commands. A trace shows coordinator, replicas/read operations, items inspected, and step timings per version, yet remains a **single query sample**—not a workload SLO measurement. Tracing adds overhead, so never leave it enabled across all production traffic.

### 11.2. Observation Commands and Metrics

~~~bash
nodetool tablestats telemetry_tuning.events_by_sensor_day
nodetool tablehistograms telemetry_tuning events_by_sensor_day
nodetool proxyhistograms
nodetool compactionstats
nodetool status
~~~

| Metric group | Question to answer |
| --- | --- |
| **Partition size / cell count** | What are actual bucket sizes at p50/p95/max; are any sensors hot? |
| **Read latency p95/p99** | Did SLO improve? Does a 3-hour read open more buckets than expected? |
| **Tombstones scanned per read** | Are reads scanning many expired rows or range/partition tombstones despite small `LIMIT`? |
| **SSTable count / read amplification** | Does one partition reconcile across many SSTables? |
| **Coordinator/replica CPU, I/O** | Does fan-out inflate network and internal RPCs? |
| **Pending compactions / flushes** | Do many partitions create compaction backlogs or SSTable pressure? |
| **Per-sensor write rate** | Do any devices emit 100× the average volume? |
| **Requests/buckets per API call** | How many buckets does one request cross; is a 7-day read opening 169 partitions? |

`nodetool` field names and calculations vary across Cassandra versions. Always record **version, schema, CL, RF, dataset size, node count, warm/cold cache state, and concurrency**. Comparing before/after across mismatched workloads or data shapes invites false conclusions.

### 11.3. A/B Benchmark Plan

1. Build lab data with realistic **time distributions, TTLs/deletes, and hot/cold sensors**, not just 100 tidy events.
2. Measure baseline on the unbucketed schema: read last 15m, last 3h, last 7d; write and compaction load.
3. Load the exact same dataset into the day-bucketed table; measure p50/p95/p99, bytes read, partition sizes, and tombstone scans.
4. If daily buckets are too large, test hourly buckets and measure the **fan-out cost** on 7-day reads.
5. If hourly buckets run hot, test hourly + shards while accounting for merge/latency/request cost.
6. Test `00:00 UTC` boundaries, late-arriving events, duplicate timestamps, retries, and multi-bucket reads.
7. Verify API SLOs, write throughput, replica disk usage, and repair/backup health—never just average read latency.

## 12. Design Anti-Patterns to Avoid

| Anti-pattern | Consequence | Better direction |
| --- | --- | --- |
| `PRIMARY KEY ((sensor_id), event_time)` for multi-year data | Unbounded partition growth, many SSTables/tombstones, heavy maintenance. | Add a time bucket to the partition key. |
| 1-minute buckets for all sensors despite multi-week reads | Huge request fan-out, metadata and coordination overhead. | Choose a coarser bucket or build rollups for long-range queries. |
| Only `event_time` in `WHERE` with `ALLOW FILTERING` | Unpredictable distributed scans and timeouts. | Supply the full partition key or add a query-specific projection. |
| Writing `bucket_day` in client local date, reading in UTC | Missing events around midnight boundaries. | Single uniform UTC/business-timezone bucket function across all writers. |
| Using `event_time` without a unique tie-breaker like `event_id` | Same-timestamp events silently overwrite each other. | Add a deterministic ID to the clustering key. |
| Querying multiple buckets and concatenating lists in arrival order | Globally unsorted results. | Merge/sort using the shared ordering key. |
| Assuming global `LIMIT 50` means `LIMIT 50` across 8 buckets together | Can fetch 400 rows or return wrong top-N if merged improperly. | Fetch top-K per bucket and merge globally to top-K. |
| Bumping shards from 4 to 8 while readers query only new shard IDs | Old events in legacy shard layouts disappear. | Version the shard scheme/migration or read across both layouts. |
| Assuming 30-day TTL means "delete 30 days after `event_time`" | Backfilled events persist far longer than intended. | Compute remaining TTL from event time or use an archival pipeline. |
| Treating `LIMIT` as a cure for tombstone scans | May traverse thousands of markers before yielding enough live rows. | Fix tombstone sources, oversized partitions, and maintenance. |
| Running multi-sensor queries against a sensor-partitioned table | Fans out across all sensors to aggregate; very costly. | Build a site/tenant-keyed table or rollup matching the query pattern. |

## 13. Case Study: Optimizing a 3-Hour Timeline and 30-Day Report

**Problem:** 20,000 sensors; most emit 1 event every 5 seconds, while 100 hot sensors peak at 50 events/second. Core APIs:

- **A.** Fetch the 50 latest events for **one sensor**.
- **B.** Fetch all events for **one sensor** over 3 hours.
- **C.** View **daily alert totals** across a site over 30 days.

**Poor design:** one `events_by_sensor` table holding full history per sensor, paired with `ALLOW FILTERING` or scanning every sensor to compute site totals.

**Tiered design:**

1. **Raw events for normal sensors:** evaluate daily buckets; monitor partition sizes and retention.
2. **Raw events for the 100 hot sensors:** evaluate hourly buckets; add controlled sharding if an hour still grows too large or hot.
3. **API A:** read the current bucket first; only step backward into prior buckets (within bounds) if fewer than 50 live rows return. Never scan 30 days upfront.
4. **API B:** with hourly buckets, read ~3–4 partitions and merge chronologically; compare against daily buckets using actual partition sizes.
5. **API C:** build an aggregate table keyed by `(site_id, month_or_window)` or `(site_id)` clustered by day depending on scale/queries, updated via an explicit pipeline with reconciliation—never scan raw events of all sensors on every dashboard load.

### Sizing Math to Drive the Decision

For a hot sensor peaking at **50 events/s**, estimated at **600 bytes/event/replica**:

| Design | Estimated logical data per bucket per replica | Buckets read for 3 hours |
| --- | --- | --- |
| Daily bucket | ~2,592 MB/day if peak persists all day | 1–2 |
| Hourly bucket | ~108 MB/hour if peak persists all hour | 3–4 |
| 15-minute bucket | ~27 MB/15 min | 12–13 |
| Hourly bucket + 4 shards | ~27 MB/shard/hour if evenly hashed | ~12–16 partitions |

**No row is automatically "best."** Daily buckets may be too big; 15-minute buckets or sharding multiply request counts. Benchmark against your constraints for **partition size, p99 SLO, write rate, memory, and maintenance**.

### An Optimization Often Worth More Than Ever-Smaller Buckets

If 95% of traffic views the **50 latest events** and only 5% views 30-day reports, consider **one projection for recent events and a historical rollup**. That keeps hot reads low-fan-out while preventing historical reports from scanning mountains of raw data. In return, you must maintain projection updates, idempotent deduping, drift handling, and reconciliation.

## 14. Self-Check Exercises with Answers

**Exercise 1.** A table uses `PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)`. Which UTC daily bucket holds an event at `2026-11-21T00:00:00Z`? Does it belong to `[2026-11-20T23:00:00Z, 2026-11-21T00:00:00Z)`?

**Answer:** Bucket `2026-11-21`. It does **not** belong to the half-open interval ending at `00:00` on Nov 21, but does belong to the interval starting at `00:00` on Nov 21.

**Exercise 2.** A sensor writes 20 events/sec at ~400 bytes/event per replica. Roughly how large is a 1-hour bucket, ignoring variance?

**Answer:** `20 × 3,600 × 400 = 28,800,000 bytes ≈ 28.8 MB` per replica. Actual on-disk size varies with SSTables, compaction, and compression.

**Exercise 3.** An API reads 7 days from an hourly-bucketed table. Why can it be slow even when every partition is small?

**Answer:** A 7-day span touches roughly **168–169 partitions** for one sensor. Fan-out, network calls, merging, concurrency, and metadata overhead accumulate; this workload may need coarser buckets or a dedicated projection/rollup.

**Exercise 4.** Can a query from 23:30 UTC to 00:45 UTC the next day query only the start day's `bucket_day`?

**Answer:** **No.** You must query both days' buckets with matching clustering ranges and merge/sort the results by timestamp.

**Exercise 5.** A query uses `LIMIT 20` yet Cassandra reports high tombstones scanned. Can you conclude the driver read the wrong number of rows?

**Answer:** **No.** `LIMIT` caps returned rows, not deleted/expired markers the server must skip to find 20 live rows.

**Exercise 6.** Why should `event_id` follow `event_time` in the clustering key?

**Answer:** Multiple events can share the exact same timestamp; without a distinguishing ID, same partition + timestamp map to the same primary key and overwrite each other. A stable ID also enables idempotent retries.

**Exercise 7.** With 4 shards per bucket, how many partitions might be queried when reading 24 hourly buckets for one sensor?

**Answer:** Up to **96 partitions** (`24 × 4`) if reading every shard of every bucket; enforce bounded concurrency and global chronological merging.

**Exercise 8.** An event from 45 days ago is ingested today into a table with a 30-day default TTL. Does it expire immediately because its `event_time` is old?

**Answer:** **No.** Default TTL counts from write time, not from the `event_time` column. Enforce event-time retention in the ingestion pipeline if business rules require it.

**Exercise 9.** When Java Driver reads 3 buckets at `LOCAL_QUORUM`, is it guaranteed that all three `SELECT`s observe one atomic point-in-time snapshot?

**Answer:** **No.** Each bucket query enforces consistency independently; concurrent mutations can cause differences between the three reads. Use watermarks or app-level logic if strict snapshot consistency is required.

## 15. Production Bucketing Checklist

~~~text
[ ] Document top 3–5 queries and explicit time-window caps per API.
[ ] Measure events/sec and bytes/event for average and hottest sensors.
[ ] Estimate partition size for day/hour/15-min buckets (treat as estimates, not exact).
[ ] Count partitions/buckets touched per request, including historical queries.
[ ] Standardize UTC/business-timezone bucket(event_time) across all writers.
[ ] Supply deterministic event_id for timestamp tie-breaking and safe retries.
[ ] Ensure every hot-path SELECT has full partition key + half-open clustering slice.
[ ] For cross-bucket reads: bound fan-out, merge top-K, and handle pagination.
[ ] Plan for late events, backfills, duplicates, and cross-page cursors.
[ ] Align TTL/retention (write time vs. event time), TWCS, and repair schedules.
[ ] If buckets still run hot, benchmark sharding and S-shard read amplification.
[ ] Monitor p95/p99, partition sizes, tombstones, SSTables, compaction, and CL.
[ ] Benchmark under load, UTC boundaries, failovers, streaming/repair, and backups.
~~~

~~~mermaid
flowchart TD
    A["Time-series workload to optimize"] --> B["Define queries and time windows"]
    B --> C["Estimate λ × T × B per bucket"]
    C --> D{"Partition too large or hot?"}
    D -->|Yes| E["Shrink T or add controlled sharding"]
    D -->|No| F["Evaluate multi-bucket read fan-out"]
    E --> F
    F --> G{"Does fan-out breach SLO?"}
    G -->|Yes| H["Coarser bucket, projection, or separate rollup"]
    G -->|No| I["CQL with full partition key + [start,end) range"]
    H --> I
    I --> J["Java merge/sort/paginate with bounded concurrency"]
    J --> K["Measure p99, tombstones, SSTables, compaction, write rate"]
    K --> L["Pick design meeting read, write, and maintenance needs"]
~~~

**Takeaway:** Time bucketing in Cassandra places a **normalized time unit** into the **partition key** to bound partition size and route range reads cleanly. Do not blindly pick the smallest possible bucket: tiny buckets shrink individual partitions while multiplying partitions read and merge overhead. A sound design balances **partition size, write hotspots, buckets per query, [start,end) boundaries, pagination, TTL/TWCS, and p99 SLOs**. Base bucket sizing on **measured workload data**, not habit alone.
