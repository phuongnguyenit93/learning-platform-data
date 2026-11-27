# timestamp, date, time, and Temporal Precision in Apache Cassandra

When a Java system writes data to **Apache Cassandra**, the question "what kind of time is this value?" is just as important as "how precise is this value?" An **instant when an event occurred**, a **calendar date**, and a **time of day** are three distinct kinds of data. Cassandra provides three primary CQL types for them: `timestamp`, `date`, and `time`.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. In a distributed wide-column architecture, data is typically partitioned by a **partition key** and ordered within each partition by **clustering columns**. Choosing the right temporal type preserves business meaning in Java; choosing the right buckets, keys, and queries makes reads and writes efficient. Replication, consistency, compaction, and repair cannot fix a timestamp shifted to the wrong time zone or precision lost during encoding.

## 1. Identifying the Three Types Before Writing CQL

| CQL Type | Represented Value | Resolution / Storage | Java Driver 4.x | Business Examples |
|---|---|---|---|---|
| **`timestamp`** | An **absolute point in time** on the timeline | Signed milliseconds since the Unix epoch | `Instant` | `created_at`, `paid_at`, `occurred_at` |
| **`date`** | A **calendar date**, without time or time zone | Calendar days, no time-of-day component | `LocalDate` | Birth date, accounting date, `event_day` bucket |
| **`time`** | A **time of day**, without date or time zone | Nanoseconds since 00:00:00 within a day | `LocalTime` | Opening time, shift start time, daily schedule slot |

Three sample questions:

- "Customer placed an order at **2026-11-21 09:00:00 UTC**": needs **`timestamp`** because it is a single instant on the timeline.
- "Date of birth is **2001-05-20**": needs **`date`** because neither time zone nor birth hour applies.
- "The store opens at **08:30:00** every day": needs **`time`**, typically paired with the **store's time zone** at the model level.

`time` being encoded down to nanoseconds **does not mean** Cassandra records physical instants at nanosecond precision. It only allows representing a *time of day* with up to 9 fractional second digits. Conversely, `timestamp` represents an actual instant but only at **millisecond** resolution. None of the three types directly store an original time zone name such as `Asia/Ho_Chi_Minh`.

## 2. timestamp: An Absolute Instant, Precise to Milliseconds

### 2.1. Unix Epoch and CQL timestamp

CQL `timestamp` stores a **64-bit signed integer** representing **milliseconds** since **1970-01-01T00:00:00Z** (the Unix epoch). Positive values lie after the epoch; negative values lie before it. Cassandra interprets `timestamp` as a point in time independent of client display formatting.

Examples of writing the exact same instant:

~~~text
2026-11-21T08:00:00Z
2026-11-21T15:00:00+07:00
~~~

Both strings denote the same instant: 08:00 UTC, corresponding to 15:00 in UTC+07:00. Once parsed into `timestamp`, Cassandra **does not retain** whether the caller supplied `Z` or `+07:00`.

If you must remember the **user-selected time zone**, store an additional `zone_id text` column, such as `Asia/Ho_Chi_Minh`. An offset like `+07:00` is only the offset at a specific instant and **does not substitute** for an IANA zone ID carrying historical rules and daylight saving transitions.

### 2.2. Why Does timestamp Only Keep Milliseconds?

Subdivisions of a second:

| Unit | Units per Second | Fractional Digits |
|---|---:|---:|
| Millisecond (ms) | 1,000 | 3 |
| Microsecond (µs) | 1,000,000 | 6 |
| Nanosecond (ns) | 1,000,000,000 | 9 |

Java's `Instant` can carry fractional seconds down to nanoseconds, yet **CQL `timestamp` has only millisecond resolution**. If the application sends:

~~~text
2026-11-21T08:30:15.123456789Z
~~~

then the stored `timestamp` represents:

~~~text
2026-11-21T08:30:15.123Z
~~~

Sub-millisecond fractions **cannot be preserved** by `timestamp`. When queries or calculations must distinguish events separated by only microseconds, two events may receive the **exact same stored timestamp**.

Java example:

~~~java
import java.time.Instant;

Instant source = Instant.parse("2026-11-21T08:30:15.123456789Z");

long epochMillis = source.toEpochMilli();  // milliseconds
Instant storedPrecision = Instant.ofEpochMilli(epochMillis);

System.out.println(source);          // 2026-11-21T08:30:15.123456789Z
System.out.println(storedPrecision); // 2026-11-21T08:30:15.123Z
~~~

This snippet demonstrates converting to milliseconds via Java APIs. The Java Driver maps `Instant` to CQL `timestamp` resolution; verify round-trip behavior for your driver version and never assume nanoseconds are retained.

**Do not confuse storage resolution with clock accuracy.** Even if a value has `.123` ms, host clocks may skew by seconds, clients may deliver events late, and source telemetry may only be sampled once per minute.

### 2.3. Always Include an Explicit Time Zone in Literals

CQL accepts timestamp string literals, for example:

~~~cql
CREATE TABLE events_by_id (
    event_id uuid PRIMARY KEY,
    occurred_at timestamp,
    message text
);

INSERT INTO events_by_id (event_id, occurred_at, message)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T08:30:15.123Z',
    'Event recorded in UTC'
);

SELECT occurred_at, message
FROM events_by_id
WHERE event_id = 11111111-1111-4111-8111-111111111111;
~~~

Prefer literals with **`Z` or an explicit offset**. A string like `'2026-11-21 08:30:15'` without an offset can be parsed according to local configuration/environment or client tool settings. Omitting offsets in a system spanning multiple services, regions, or operators causes subtle bugs.

Returned values may be formatted by a tool in UTC or a local time zone; **display formatting is not evidence that Cassandra altered the stored instant**. Explicitly convert to UTC or the business time zone when rendering in the UI.

## 3. date: Calendar Date Without an Absolute Instant

CQL `date` represents a calendar date such as `2026-11-21` with no time, offset, or time zone. In Java, it corresponds to **`LocalDate`**.

~~~cql
CREATE TABLE people_by_id (
    person_id uuid PRIMARY KEY,
    full_name text,
    birth_date date
);

INSERT INTO people_by_id (person_id, full_name, birth_date)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'Nguyễn Minh Anh',
    '2001-05-20'
);
~~~

A calendar birth date like `2001-05-20` should not be stored as "midnight UTC" merely because Java makes creating an `Instant` easy: an application in another time zone could display it as **the previous day**, distorting the birth date's meaning.

Good fits for `date`: birth dates, holidays, contractual closing dates, policy effective dates, and **daily bucket keys** for event-stream reads.

### 3.1. date as a Bucket for Distributed Data

In Cassandra, an event-stream table often uses `(device_id, event_day)` as its partition key. The `event_day date` column below is **not** the event's occurrence timestamp; it is the partition label grouping events belonging to one day.

Define which day rule applies:

- **UTC day:** `occurredAt.atZone(ZoneOffset.UTC).toLocalDate()`.
- **Branch local day:** `occurredAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate()`.
- **Accounting day:** may follow business rules distinct from both above, such as rolling over after a daily cutoff hour.

Cassandra does not automatically know which rule produced `event_day`. If client A uses UTC while client B uses `Asia/Ho_Chi_Minh`, the exact same `occurred_at` can be placed in **two different partitions**.

For example, `2026-11-20T18:30:00Z` is **2026-11-21 01:30** in Vietnam (UTC+07). The UTC date is Nov 20, while the Vietnam date is Nov 21. Standardize one rule across both **writes** and **queries**.

### 3.2. A Local Day May Not Be 24 Hours Long

In time zones with daylight saving time (DST), a calendar day can span **23 or 25 actual hours**. Therefore, when computing `[start of local day, start of next local day)`, convert **both endpoints using `ZoneId`** to `Instant` rather than adding a fixed 24 hours from the start of the day.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("America/New_York");
LocalDate businessDay = LocalDate.parse("2026-11-01");

Instant from = businessDay.atStartOfDay(zone).toInstant();
Instant until = businessDay.plusDays(1).atStartOfDay(zone).toInstant();

// This is the exact full-day interval in the business time zone.
~~~

This is fundamental for daily queries, revenue aggregation, and bucketing. **`LocalDate` has no time zone**, and converting it to an `Instant` range requires supplying the time zone explicitly.

## 4. time: Time of Day with Nanosecond Resolution

CQL `time` represents a time within a single day: from `00:00:00` up to before `24:00:00`, with up to **9 fractional second digits**. It is stored as **nanoseconds since midnight**, independent of any date or time zone.

Example:

~~~cql
CREATE TABLE store_hours_by_store_weekday (
    store_id uuid,
    weekday tinyint,
    open_at time,
    close_at time,
    zone_id text,
    PRIMARY KEY ((store_id), weekday)
);

INSERT INTO store_hours_by_store_weekday (
    store_id, weekday, open_at, close_at, zone_id
) VALUES (
    33333333-3333-4333-8333-333333333333,
    1,
    '08:30:00.000000000',
    '22:00:00.000000000',
    'Asia/Ho_Chi_Minh'
);
~~~

In this example, the application defines `weekday = 1` as **Monday** per a convention (e.g., ISO 8601). Cassandra does not inherently associate `tinyint 1` with Monday. `open_at` and `close_at` carry no time zone either; `zone_id` tells the application which store time zone applies.

### 4.1. time Is Not a Shorthand timestamp

The value `08:30:00` in a `time` column is **insufficient** to determine an absolute instant. To convert to an `Instant`, you need at least:

1. Calendar date (`LocalDate`).
2. Time of day (`LocalTime`).
3. Time zone or offset and DST resolution policy.

For an overnight shift from 22:00 to 06:00, you cannot simply compute `close_at - open_at` on the same date to get the true duration. The application must recognize that the end time falls on the **next day**, then compute the elapsed span between the resulting `Instant` values. Under DST, actual elapsed hours may differ from wall-clock difference.

`time` fits daily schedules, local clock labels, and opening hours. To record when an API request was handled, use **`timestamp`**; to measure processing duration, use an integer duration in an explicit unit or an appropriate type rather than misusing `time` as a duration.

### 4.2. time Supports Nanoseconds, Bounded by the Source

A CQL `time` column can store `'08:30:15.123456789'`, and Java maps it to `LocalTime` with nanoseconds. This differs from `timestamp`, which stops at milliseconds. However:

- Having no date means `time` cannot determine "before/after" across different days.
- It knows nothing about offsets or time zones.
- Devices or applications may only measure to seconds or milliseconds; padding trailing zeros does not make a measurement more accurate.
- Display formatting may strip trailing zeros, while the underlying time-of-day value remains identical.

## 5. Practical CQL: Combining date and timestamp for an Event Table

Requirement: **"Fetch the 100 newest events for a device on a UTC day; optionally filter events within an hour range."**

~~~cql
CREATE TABLE events_by_device_day (
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    local_clock_time time,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Role of each temporal column:

| Column | Type | Role |
|---|---|---|
| `event_day` | `date` | **Partition bucket** by UTC day to bound partition size |
| `occurred_at` | `timestamp` | Primary **clustering column** to sort by absolute instant |
| `event_id` | `uuid` | Tie-breaker distinguishing two events falling in the same millisecond |
| `local_clock_time` | `time` | Time of day supplied by source device/context; does not participate in timeline ordering |

For source data with sub-millisecond cadence, **multiple events can share the same `occurred_at`**. `event_id` serves as a secondary clustering column to prevent primary-key overwrites. It does not mean a random UUID orders sub-millisecond events chronologically when timestamps tie; if that requirement exists, include a source sequence or high-resolution integer column.

~~~cql
INSERT INTO events_by_device_day (
    device_id, event_day, occurred_at, event_id,
    local_clock_time, event_type, payload
) VALUES (
    44444444-4444-4444-8444-444444444444,
    '2026-11-21',
    '2026-11-21T08:30:15.123Z',
    55555555-5555-4555-8555-555555555555,
    '15:30:15.123456789',
    'TEMPERATURE_READING',
    '{"celsius":23.5}'
);
~~~

In this example, `occurred_at` is 08:30 UTC and `local_clock_time` is 15:30:15.123456789 on a source clock at UTC+07:00. Because `time` **carries no time zone**, the pair is meaningful only when the system knows the source's convention; never treat `local_clock_time` as a separate UTC timestamp.

### 5.1. Reading by Partition Key and Clustering Range

~~~cql
SELECT occurred_at, event_id, event_type, local_clock_time
FROM events_by_device_day
WHERE device_id = 44444444-4444-4444-8444-444444444444
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

The query provides the **full partition key** `(device_id, event_day)` and bounds the **clustering column** `occurred_at`. The **half-open** interval `[08:00, 09:00)` prevents adjacent hourly windows from double-counting events right on the boundary.

Because the table clusters by `occurred_at DESC`, rows within the partition are read newest to oldest. To retrieve events for a device across **multiple days**, the application must query the relevant daily partitions and merge/paginate results, or use another tailored access path.

Changing `occurred_at` from `timestamp` to another type will not magically make queries like "all devices for a day" or "all events where `event_type = X`" efficient. Cassandra requires **query-driven table design**.

### 5.2. Daily Buckets and Partition Size Limits

A partition `(device_id, event_day)` holds all events for one device on one day. If a device emits 1 million events per day, a daily bucket may still grow too large for row/payload volume and read patterns. You may need hourly buckets, sharding, or another layout driven by throughput and retention.

Choosing `date` as a bucket key only defines **how data is grouped**, not an automatic cap on partition size. Likewise, `event_day` must be computed **from the exact ordering timestamp** under the agreed time zone, even when data arrives late or is backfilled.

## 6. Java Driver 4.x: Instant, LocalDate, and LocalTime

Common mappings in Apache Cassandra Java Driver 4.x:

| CQL | Java | Bind in `BoundStatementBuilder` | Read from `Row` |
|---|---|---|---|
| `timestamp` | `Instant` | `setInstant(index, value)` | `getInstant(column)` |
| `date` | `LocalDate` | `setLocalDate(index, value)` | `getLocalDate(column)` |
| `time` | `LocalTime` | `setLocalTime(index, value)` | `getLocalTime(column)` |

### 6.1. Writing Events with Consistent UTC Bucketing

Assume `session` is a `CqlSession` connected to the cluster with the target keyspace selected:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Configured outside this example.

UUID deviceId = UUID.fromString("44444444-4444-4444-8444-444444444444");
UUID eventId = UUID.fromString("55555555-5555-4555-8555-555555555555");

Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
LocalTime localClock = LocalTime.parse("15:30:15.123456789");

PreparedStatement ps = session.prepare(
    "INSERT INTO events_by_device_day "
  + "(device_id, event_day, occurred_at, event_id, "
  + " local_clock_time, event_type, payload) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement statement = ps.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setLocalTime(4, localClock)
    .setString(5, "TEMPERATURE_READING")
    .setString(6, "{\"celsius\":23.5}")
    .build();

session.execute(statement);
~~~

**Why choose `Instant` over `LocalDateTime`?** `Instant` uniquely identifies an absolute point in time. `LocalDateTime` holds only a local date and time without zone or offset; the same `LocalDateTime` can map to two instants during a DST fall-back transition, or to no instant at all during a spring-forward gap.

If source data provides local date and time, convert via `ZonedDateTime` or apply an explicit `ZoneId` and DST policy **before** binding `Instant`.

### 6.2. Querying Time Ranges with Prepared Statements

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;

Instant from = Instant.parse("2026-11-21T08:00:00Z");
Instant until = Instant.parse("2026-11-21T09:00:00Z");

PreparedStatement range = session.prepare(
    "SELECT occurred_at, event_id, local_clock_time, event_type "
  + "FROM events_by_device_day "
  + "WHERE device_id = ? AND event_day = ? "
  + "AND occurred_at >= ? AND occurred_at < ? LIMIT 100");

for (Row row : session.execute(range.bind(
        deviceId, LocalDate.parse("2026-11-21"), from, until))) {
    Instant storedAt = row.getInstant("occurred_at");
    UUID storedId = row.getUuid("event_id");

    LocalTime reportedClock = row.isNull("local_clock_time")
        ? null : row.getLocalTime("local_clock_time");
}
~~~

Prepared statements bind parameters with strong types, eliminating manual date-string formatting inside CQL queries. Check for null when reading optional columns. The `event_day` key must use the **exact same time zone convention as writes**; `Instant from/until` bound only the clustering range within the chosen partition.

### 6.3. Converting Local Date/Time to Instant

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

LocalDate day = LocalDate.parse("2026-11-21");
LocalTime clock = LocalTime.parse("15:30:15");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant absolute = day.atTime(clock).atZone(zone).toInstant();
// 2026-11-21T08:30:15Z
~~~

This works cleanly for Vietnam, whereas in DST-observing zones `atZone(zone)` applies default behavior for overlapping or nonexistent local times. For appointments, payments, or deadlines, define explicit policies for those edge cases rather than relying blindly on defaults.

## 7. Distinguishing Business timestamp from Cassandra Write Timestamp

This is one of the most important distinctions when learning Cassandra.

| Term | Unit / Representation | What Is It Used For? |
|---|---|---|
| CQL **`timestamp`** in column `occurred_at` | **Milliseconds** since Unix epoch | Business data: when the event occurred |
| CQL **`time`** in column `local_clock_time` | **Nanoseconds since midnight** | A time of day |
| **Cassandra write timestamp** in cell metadata | **Microseconds** | Resolving write versions/conflicts via last-write-wins |
| **`USING TIMESTAMP`** in CQL | **Microsecond** integer | Specifying the write timestamp of a mutation |
| **`WRITETIME(column)`** function | Returns **microseconds** | Inspecting the write timestamp of a data cell |

`WRITETIME()` does not tell you "when the event happened." It reports the **cell's write timestamp** for the queried column, which may be client-supplied or coordinator-assigned upon writing.

Query example:

~~~cql
SELECT occurred_at,
       event_type,
       WRITETIME(event_type) AS event_type_write_us
FROM events_by_device_day
WHERE device_id = 44444444-4444-4444-8444-444444444444
  AND event_day = '2026-11-21'
LIMIT 5;
~~~

Note: `WRITETIME(event_type)` applies to the **regular column** `event_type`. You cannot call `WRITETIME(occurred_at)` on this table because `occurred_at` is a **primary key/clustering column**.

Typical mistakes:

- Passing epoch milliseconds directly to `USING TIMESTAMP` — the write timestamp will be off in scale by roughly **1,000x**.
- Taking a microsecond write timestamp from `WRITETIME` and parsing it as epoch milliseconds — produces dates far in the future or out-of-range errors.
- Using `USING TIMESTAMP` to "store event time," inadvertently altering **last-write-wins conflict ordering** so newer updates lose to older ones.

Normally, use a **dedicated `occurred_at timestamp` column** for business time and let Cassandra/the driver manage write timestamps automatically. Only supply custom write timestamps when you have a clear reason and understand the effects on updates, deletes, TTL, and reconciliation.

## 8. Retries, Duplicate Timestamps, and Ordering in Distributed Systems

### 8.1. Millisecond-Resolution timestamp Is Not a Unique Key

If a device emits 10,000 events per second, many events share the exact same `timestamp` down to the millisecond. In a table with primary key `((device_id, day), occurred_at)` alone, two events with the same `occurred_at` share the **same primary key** and overwrite/update the same row.

That is why the example uses:

~~~cql
PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
~~~

Here `event_id uuid` is the trailing key component distinguishing events. The ID must be assigned **once** per event and reused on retries.

If **strict microsecond/nanosecond ordering** is required, `timestamp + uuid` only guarantees **uniqueness**, not sub-millisecond ordering. Options include adding `event_epoch_ns bigint` or `sequence_no bigint` as a clustering column under a source contract, paired with a deduplicating event ID and range/overflow validation. Source precision and multi-writer ordering still require separate verification.

### 8.2. When to Use timeuuid?

`timeuuid` is a UUID v1 with a time component that works as a clustering column for timelines ordered **by ID generation time**. It does not replace `occurred_at timestamp` when sorting must follow **source occurrence time**; late-arriving events carry ingestion-time IDs if generated on receipt.

Choose the model to match the query:

| Requirement | Starting Key Choice |
|---|---|
| Timeline ordered by server ID generation time | `timeuuid` clustering key |
| Timeline ordered by event occurrence time, to ms | `timestamp` + `uuid` clustering columns |
| Timeline ordered by stable source sequence numbers | `bigint sequence_no` + `uuid`, with sequence contract |
| Event identifier so retries do not create duplicate rows | Stable `uuid`, reusing the exact same primary key |

Cassandra does not provide a single global physical ordering across all nodes. Host clocks drift, network deliveries arrive late, and time-based IDs do not establish global causal ordering.

### 8.3. Timeout Errors Do Not Confirm Write Failure

A write may succeed on some replicas even when the client times out waiting for full acknowledgment. If a retry generates a new `event_id` or `occurred_at`, the event may land under a **new key**, creating a duplicate.

Keep **partition key, clustering key, and business payload** constant across a retry chain. When updating multiple query tables, build synchronization/reconciliation mechanisms because separate writes are not cross-partition ACID transactions. Consistency levels tune replica acknowledgment counts, **not** source timestamps or retry correctness.

## 9. Common Temporal Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `timestamp` to store birth dates | Date can shift across time zones | Use `date` |
| Using `date` for payment completion time | Loses hours, minutes, seconds, and transaction order | Use `timestamp` |
| Using `time` to store request timestamps | Missing date; cannot identify absolute instant | Use `timestamp` |
| Assuming `timestamp` keeps micro/nanoseconds | Closely spaced events lose precision | Add sequence/high-res model if needed |
| Parsing offset-less datetime strings across regions | Inconsistent time zone shifts | Use `Instant` and ISO-8601 with `Z`/offset |
| Treating `LocalDateTime` as an `Instant` | Ambiguous/nonexistent DST hours | Supply `ZoneId` and a DST policy |
| Computing `event_day` in UTC on write and local time on read | Queries miss the target partition | Standardize one bucketing rule |
| Assuming every local day is 24 hours | Wrong query bounds across DST transitions | Compute both day boundaries via `ZoneId` |
| Using `occurred_at` alone as clustering key at high rates | Same-millisecond events overwrite one row | Add tie-breaker ID/sequence |
| Using `WRITETIME` as event occurrence time | Reads cell write metadata instead of source time | Store `occurred_at timestamp` |
| Passing epoch millis to `USING TIMESTAMP` | Wrong unit (expects microseconds), breaks updates | Use microseconds only when client write timestamps are truly needed |
| Regenerating time and UUID on retry | Creates multiple rows for one event | Reuse the exact same ID and key across retries |
| Querying cluster-wide on a non-key `timestamp` column | No partition-key access path | Build a query-aligned table or evaluated index |

## 10. Operational Impact: Retention, TTL, Compaction, and Repair

For time-series log/event tables, data lifecycle and partition size must be designed alongside queries:

- **TTL** in CQL is specified in **seconds** to expire cells. TTL does not use `timestamp` milliseconds, nor is it automatically derived from an `expires_at timestamp` column without explicit write logic.
- **Compaction** organizes SSTables and purges expired/tombstoned data according to storage rules. It does not fix business timestamps or move mis-bucketed `date` partitions.
- **Repair** synchronizes replica state; it does not restore nanoseconds truncated during `timestamp` encoding.
- **Replication and consistency levels** govern data copying and acknowledgments; they do not synchronize client clocks or provide globally atomic multi-bucket snapshots.
- **Retention** must align with auditing, cost, GDPR/data policies, and backfill needs. Never apply a short TTL to long-term logs assuming compaction can recover expired data.

For heavily queried time-series workloads, measure **rows/partition**, **bytes/partition**, **p95/p99 latency**, tombstones, read/write throughput, and token distribution. Pick daily or hourly buckets matching actual load instead of assuming `date` optimizes partitions by itself.

## 11. Scenario Exercises

### Exercise 1 — Choosing Types

Given four columns: `birth_day` (date of birth), `payment_completed_at` (payment timestamp), `opening_time` (daily recurring opening hour), and `sensor_received_at` (when the server received the reading).

**Answer:** `birth_day date`, `payment_completed_at timestamp`, `opening_time time`, `sensor_received_at timestamp`. If local opening hours must be converted to absolute instants, also store or know `zone_id`.

### Exercise 2 — Precision Loss

A Java service creates `Instant.parse("2026-11-21T08:00:00.123456789Z")` and writes it to a `timestamp` column.

**Question:** Can a query distinguish this event from `08:00:00.123987654Z` using the `timestamp` column alone?

**Answer:** no. Both truncate to the exact same `.123` millisecond in `timestamp` resolution. You need a tie-breaker ID/sequence column or a higher-resolution unit per the source contract.

### Exercise 3 — Wrong Day Bucket

An event at `2026-11-20T18:30:00Z` is bucketed in UTC. Another client computes the day in `Asia/Ho_Chi_Minh`.

**Question:** Which bucket does each client query?

**Answer:** UTC is `2026-11-20`; Vietnam is `2026-11-21`. Enforce a single bucketing rule instead of letting clients pick time zones independently.

### Exercise 4 — Store in a DST Zone

A store opens at 01:30 in a region observing DST. On one day of the year, 01:30 occurs **twice** on wall clocks.

**Question:** Is `time '01:30:00'` enough to schedule an absolute appointment?

**Answer:** no. You need the date, `ZoneId`, and a policy choosing between the earlier and later offsets for ambiguous times—or store the confirmed `Instant` for that specific appointment.

### Exercise 5 — WRITETIME

A row has `occurred_at = '2026-11-21T08:30:00Z'` but was backfilled into Cassandra one week later. When querying `WRITETIME(event_type)`, will it match `occurred_at`?

**Answer:** not necessarily. `WRITETIME` is write-version metadata (in microseconds), whereas `occurred_at` is business data (in milliseconds). Without an explicit client write timestamp, they reflect two distinct times during backfills.

## 12. Checklist Before Deploying Temporal Types

- [ ] Is the value an **absolute instant**, a **calendar date**, or a **time of day**?
- [ ] Does a `timestamp` column require sub-millisecond resolution? If so, is there an ID/sequence/high-res unit column?
- [ ] Does Java use `Instant` for instants, `LocalDate` for dates, and `LocalTime` for times of day?
- [ ] Do all CQL instant literals include `Z` or an explicit offset?
- [ ] If the business needs the original time zone, is `ZoneId`/time-zone policy stored separately?
- [ ] When converting `LocalDate + LocalTime` to `Instant`, are DST overlaps and gaps handled?
- [ ] Are `date` buckets derived consistently from the exact right timestamp and one agreed time zone?
- [ ] Do time-range queries supply the **full partition key** and valid **clustering column** predicates?
- [ ] Do range queries use half-open **`[start, end)`** bounds to keep boundaries clean?
- [ ] Do same-millisecond events have an `event_id` or secondary key to avoid overwrites?
- [ ] Do retries reuse the exact `event_id`, `occurred_at`, and bucket instead of regenerating them?
- [ ] Are **CQL timestamp (ms)** and **WRITETIME/USING TIMESTAMP (µs)** clearly separated?
- [ ] Have partition sizes, TTL in seconds, retention, compaction, repair, and consistency been sized for actual load?

**Remember:** **`timestamp`** stores an **instant** at **millisecond** resolution; **`date`** stores a **calendar date**; **`time`** stores a **time of day** up to **nanoseconds** without date or time zone. In Cassandra, choosing the right temporal type preserves data meaning, while consistent partition buckets, clustering keys, and retry handling enable accurate, efficient time queries across a distributed cluster.
