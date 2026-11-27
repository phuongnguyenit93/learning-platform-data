# Designing Time-Based Data, Retention, and Clock Testing in Apache Cassandra

## 1. Goal and Context

**Apache Cassandra** is a **distributed wide-column** database management system suited for high-throughput write streams when tables are structured around **queries** and paired with an appropriate partitioning strategy. Time-oriented data—telemetry, events, access logs, notifications, temporary processing results—raises three distinct questions:

1. **How is it read?** Fetch the latest 100 events for a device, look up events within a day, or read the current state?
2. **How long is it kept?** Delete data 7 days after occurrence, 7 days after ingestion, or retain until a fixed `retention_until` timestamp?
3. **Which clock do you trust?** Events can arrive late, clients can have skewed clocks, coordinators can assign a write timestamp different from business time, and a quick test can flake if it depends on uncontrolled wall-clock time.

Without separating these questions, systems easily suffer from **oversized partitions, queries forced to scan data, data expiring at the wrong time, last-write-wins rolling back state, and flaky tests**.

The goal of this lesson is to design a sensor event stream supporting **queries by device and day**, explicit retention deadlines, late-arriving data handling, Java Driver 4.x integration, and a deterministic **Clock** test suite. Examples focus on principles so you can choose settings suited to your actual workload and Cassandra version.

## 2. Four Timestamps That Must Be Modeled Separately

A temperature measurement event can carry multiple timestamps simultaneously. They are not synonyms.

| Name | Example | Source | Meaning |
|---|---|---|---|
| **Event time** (`event_at`) | 10:00:00.000 UTC | Device / event producer | When the event is believed to have occurred |
| **Ingest time** (`ingested_at`) | 10:05:12.400 UTC | Ingestion / writer service | When the system processed or received the event |
| **Mutation timestamp** | Epoch microseconds | Driver, CQL `USING TIMESTAMP`, or coordinator | Arbitrates cell versions under **last-write-wins** |
| **Retention deadline** (`retention_until`) | 10:00 UTC 7 days later | Business policy | Point after which data should no longer be used/kept per policy |

**TTL** is the **relative number of remaining live seconds** assigned to a cell version at write time, whereas `retention_until` is an **absolute instant**. Separating these two is especially vital when retries, backfills, or late arrivals occur.

```text
Device records              Service ingests                  Retention deadline
    event_at                    ingested_at                  retention_until
        |                           |                              |
        +------ late-arriving ----->|<------ remaining TTL ------->|
        |                           |
        |                   Cassandra receives mutation
        |                   and assigns/receives write timestamp
        |
        +-- If retention is measured from event time:
            retention_until = event_at + retention duration
```

### Units Must Be Consistent

- The CQL `timestamp` type represents business instants at **millisecond** resolution.
- `USING TIMESTAMP` and `writetime(column)` are **microseconds since the Unix epoch**, used for mutation LWW.
- `USING TTL`, `default_time_to_live`, and `ttl(column)` use **seconds**.
- Java `Instant` represents an absolute instant; `LocalDate` describes a calendar date and requires an explicit time zone when derived from an `Instant`.
- `System.nanoTime()` is an **elapsed-time** clock, not a Unix epoch timestamp for writing into Cassandra.

Never assume the write timestamp assigned at the coordinator equals `event_at`; an event from yesterday may be imported today. Using event time to set `USING TIMESTAMP` can cause late-arriving data to be shadowed by a newer mutation timestamp; that is a design choice that must be justified, not a default.

## 3. Put Queries First, Then Choose Partition and Clustering Keys

Suppose an IoT system has these requirements:

- Fetch the **100 newest measurements** of a device on a given day.
- Fetch a device's measurements **within a time range**.
- Read the **latest accepted measurement** of a device.
- Retain historical data for **7 days**, without letting request retries extend the retention duration.

A single table serving every goal is rarely optimal. Following a **query-first** model, split them:

1. A **history** table: multiple rows per device + time bucket; clustering key supports reading in event order.
2. A **latest-state** table: one row per device; updated conditionally or by version source so state never rolls backward.

```text
             event(device_id, event_at, event_id, value)
                                |
                    +-----------+----------+
                    |                      |
                    v                      v
      readings_by_device_day      latest_reading_by_device
      partition: device+day       partition: device
      clustering: event time      1 row / device
      historical queries          current-state queries
```

**Never** use `ORDER BY writetime(value)` or `ALLOW FILTERING` on large tables to simulate a time index. Cassandra only sorts rows within a partition by the declared **clustering key**.

## 4. History Schema by Device and UTC Day

Run in a **test keyspace** created and selected with `USE <keyspace>;`. If tables with the same names already exist with different schemas, use different names; `IF NOT EXISTS` does not alter an existing schema.

```sql
CREATE TABLE IF NOT EXISTS readings_by_device_day (
    device_id text,
    event_day date,
    event_at timestamp,
    event_id uuid,
    temperature_c double,
    ingested_at timestamp,
    retention_until timestamp,
    PRIMARY KEY ((device_id, event_day), event_at, event_id)
) WITH CLUSTERING ORDER BY (event_at DESC, event_id ASC);
```

Meaning:

- **Partition key** is the pair `(device_id, event_day)`. All rows for one device on one day are grouped together.
- **Clustering key** consists of descending `event_at` and `event_id` to distinguish two events occurring within the same millisecond.
- `event_day` must be computed **from `event_at` in UTC**, not from the Java server's default timezone.
- `event_id` is an event identifier **stable across retries**. If the same event retries with a different ID or `event_at`, Cassandra can create a **different row**, producing duplicate data.
- `ingested_at` measures source lag; `retention_until` records the absolute deadline for retention policy enforcement.

Using a `uuid` as a tie-breaker for events with identical `event_at` produces **deterministic ordering in storage**, yet **does not indicate which event truly happened first** if source clocks were skewed. If causal ordering is needed, use a sequence/version from a trusted source.

### Sample Data

```sql
INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-01',
    '2026-11-21',
    '2026-11-21T08:30:00.123Z',
    11111111-1414-4141-8141-111111111111,
    32.5,
    '2026-11-21T08:30:01Z',
    '2026-11-28T08:30:00.123Z'
)
USING TTL 604800;

INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-01',
    '2026-11-21',
    '2026-11-21T08:31:00.000Z',
    22222222-1414-4141-8141-222222222222,
    32.9,
    '2026-11-21T08:31:01Z',
    '2026-11-28T08:31:00.000Z'
)
USING TTL 604800;
```

The two statements above **demonstrate syntax and reading**: because a 7-day TTL counts from **write time**, they only achieve 7-day retention from `event_at` **when ingestion happens close to `event_at`**. If run many days after Nov 21, 2026, the TTL deadline no longer matches `retention_until`; that is precisely the late-arriving data problem solved in later sections.

### Querying by Partition and Clustering Range

```sql
-- 100 newest records for the device on that day.
SELECT event_at, event_id, temperature_c
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 100;

-- Bound an hour range within the same partition.
SELECT event_at, event_id, temperature_c
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_at >= '2026-11-21T08:00:00Z'
  AND event_at <  '2026-11-21T09:00:00Z';
```

Querying a range **spanning multiple days** requires knowing the corresponding day buckets, issuing multiple partition reads, and merging at the application layer. Cassandra does not natively provide global sorting by `event_at` across multiple partitions; if the workload needs queries by customer/all devices or another dimension, build a **separate table designed for that query**.

## 5. Time Bucket Sizing: Balancing Hot Partitions and Query Count

Daily time bucketing **is not a one-size-fits-all formula**. Partition size depends on write rate, row size, retained sample count, and target queries.

Suppose each device emits `10` events/second:

```text
10 events/s × 60 × 60 × 24 = 864,000 events / device / day
```

One partition per day can hold **864 thousand rows** before counting tombstones, overhead, and other columns; that can become a **large partition** for some workloads. With hourly buckets:

```text
10 events/s × 60 × 60 = 36,000 events / device / hour
```

| Bucket | Benefit | Trade-off |
|---|---|---|
| Daily | Fewer partitions to read for a full-day query | Risk of large/hot partitions at high write rates |
| Hourly | Better write distribution and tighter partition bounds | A full-day query must read multiple buckets |
| Per-minute | Useful at very high rates | Many small partitions, higher fan-out and metadata |

Always **measure actual partition sizes and latencies** rather than deciding from row counts alone. If every new event for a device hits one active current partition, that partition can still be a **hot partition** even with short retention. When further splitting is needed, add controlled sharding to the partition key and make queries read the known shards.

**Rule:** buckets must be derived from **the timestamp chosen as the query order**, usually `event_at`, explicitly in UTC. Using `ingested_at` for bucketing places late-arriving events into the ingest day, causing "all events on occurrence day" queries to miss data unless the application also scans later ingest buckets.

## 6. Latest-State Tables Need Dedicated Business Ordering Rules

A simple latest-state table:

```sql
CREATE TABLE IF NOT EXISTS latest_reading_by_device (
    device_id text PRIMARY KEY,
    event_version bigint,
    event_id uuid,
    event_at timestamp,
    temperature_c double
);
```

Reading latest by partition key:

```sql
SELECT event_version, event_id, event_at, temperature_c
FROM latest_reading_by_device
WHERE device_id = 'sensor-01';
```

However, if an **older event arrives late** and a normal `UPDATE` carries a **larger** mutation timestamp simply because it was ingested later, it can overwrite a genuinely newer reading.

```text
10:00 event E1: 30°C
10:01 event E2: 32°C -> latest = 32°C
10:05 E1 is resent with a new write timestamp -> latest can revert to 30°C
```

When business rules require latest state to follow **reliable event ordering**, consider:

- A dedicated writer/projector assigned per `device_id`, processing events sequentially.
- Storing `event_version` issued by an ordered source, applying only valid forward transitions.
- **LWT** (*lightweight transactions*) with `IF` for compare-and-set, checking the `[applied]` result.
- An append-only event log as the source of truth, with latest-state as a rebuildable projection.

LWT example with a pre-assigned version:

```sql
INSERT INTO latest_reading_by_device (
    device_id, event_version, event_id, event_at, temperature_c
)
VALUES (
    'sensor-lwt-01', 1,
    33333333-1414-4141-8141-333333333333,
    '2026-11-21T08:00:00Z', 30.0
)
IF NOT EXISTS;

UPDATE latest_reading_by_device
SET event_version = 2,
    event_id = 44444444-1414-4141-8141-444444444444,
    event_at = '2026-11-21T08:01:00Z',
    temperature_c = 32.0
WHERE device_id = 'sensor-lwt-01'
IF event_version = 1;
```

The second statement applies only if the current version is `1`; retrying an older-version event after advancing to `2` must not be allowed to roll the version backward. **LWT adds coordination overhead and latency**, so evaluate against workload requirements. Do not supply client-chosen `USING TIMESTAMP` in conditional mutations as with normal writes; LWT has its own timestamp rules.

## 7. Two Definitions of Retention: From Occurrence Time or From Ingest Time?

A policy stating "retain for 7 days" is **incomplete for implementation**. You must ask: **7 days from which anchor?**

| Policy | Deadline | When an event arrives 2 days late | Typical fit |
|---|---|---|---|
| **Ingest-based retention** | `ingested_at + 7 days` | Lives roughly 7 days from receipt | Caches, temporary processing data tied to ingest |
| **Event-based retention** | `event_at + 7 days` | Only ~5 days left | Event logs retained relative to occurrence date |
| **Explicit deadline** | `retention_until` set by business source | Kept until that exact issued instant | Contracts, compliance rules, fixed-deadline results |

Example: event `E1` occurred at `2026-11-20T10:00Z`, yet was ingested into Cassandra at `2026-11-22T10:00Z`:

```text
Event-based:  Nov 20 10:00 + 7 days = Nov 27 10:00
Ingest-based: Nov 22 10:00 + 7 days = Nov 29 10:00

If you write USING TTL 604800 on Nov 22,
Cassandra keeps it ~7 days from WRITE TIME, near Nov 29.
That is NOT 7-day event-based retention.
```

For event-based retention, compute the remaining duration from the predetermined deadline. **Never pass `USING TTL 604800` directly on backfill data** if the goal is expiration 7 days after event time.

## 8. Computing Remaining TTL from an Absolute Deadline

Suppose the policy is `retention_until = event_at + 7 days`. At write time:

```text
remaining = retention_until - trusted_now
ttl_seconds = positive integer seconds chosen per rounding policy
```

Distinguish three cases:

1. **Deadline has already passed:** do not issue a new mutation with TTL 0. In Cassandra, **`USING TTL 0` means no TTL**, the exact opposite of what you want. Reject, skip, or route to an expired-event handler.
2. **Deadline is within valid TTL range:** write with a positive TTL matching the remaining duration.
3. **Deadline is too far out, exceeding the deployment's TTL/expiration horizon:** never silently truncate if retention is mandatory; choose a different retention storage policy or surface an observable error.

### Rounding Rules

TTL uses **integer seconds**, while `Instant` and `timestamp` can represent sub-second fractions.

- **Rounding down** remaining duration avoids intentionally setting expiration past the deadline, though values may expire **up to almost one second early**.
- **Rounding up** keeps data at least until the deadline in an ideal clock model, yet can leave the cell live **past the deadline** by under a second—or longer due to latency/clock skew.
- **Validating `retention_until` on read/use** is necessary when the deadline carries strict business meaning. TTL is a storage lifecycle tool, not an absolute legal clock.

Even when the application computes TTL to the exact second, **the Cassandra server processes the write after the client computes it** and node clocks can drift. Thus policies need safety margins and deadline checks on the read path.

### Deliberate CQL Practice

```sql
-- Example assuming the event has 3600 seconds left under its deadline.
-- Use a fresh UUID; "retention_until" is purely business metadata.
INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-retention-01',
    '2026-11-21',
    '2026-11-21T07:00:00Z',
    55555555-1414-4141-8141-555555555555,
    27.4,
    '2026-11-21T07:30:00Z',
    '2026-11-21T08:30:00Z'
)
USING TTL 3600;
```

**The timestamps in the statement above are for reading illustration only.** `USING TTL 3600` actually starts counting from **when Cassandra writes**, without checking the gap between `ingested_at` and `retention_until`. In production code, compute TTL from the deadline and current time before sending.

## 9. Default TTL, Retries, Tombstones, and Physical Retention

TTL applies to **written cells**, not every row in a partition by default. A table's `default_time_to_live` is convenient when all new data shares a uniform lifecycle:

```sql
CREATE TABLE IF NOT EXISTS transient_alert_by_id (
    alert_id uuid PRIMARY KEY,
    device_id text,
    description text
) WITH default_time_to_live = 86400;

INSERT INTO transient_alert_by_id (alert_id, device_id, description)
VALUES (
    66666666-1414-4141-8141-666666666666,
    'sensor-01', 'Temperature warning'
);
```

The newly written cells will get a default TTL near **86,400 seconds**. For records needing a custom TTL, `INSERT/UPDATE ... USING TTL N` overrides the table TTL; `USING TTL 0` creates a new value with **no TTL**. Changing `default_time_to_live` via `ALTER TABLE` does not rewrite the lifetimes of existing cells.

### A Retry Is Not a New Event

A timed-out request may already have been accepted by some replicas. If the application retries using a **new mutation with the full TTL**, it can **unintentionally extend the lifetime**. For event tables, keep **`event_id`, `event_at`, and `retention_until` invariant across retries**; whenever re-sending, recompute TTL from the same deadline rather than minting a new deadline.

A safer way to evaluate retries is to separate:

- **Key idempotency:** retrying an event does not create a new row by changing `event_id` or bucket.
- **State idempotency:** old replays do not roll back latest-state.
- **Deadline idempotency:** retries do not push back the business deadline.
- **Side-effect idempotency:** notifications, billing, or downstream processing are not triggered multiple times for one event.

### Logical Expiration Differs from Physical Reclamation

Once TTL expires, the cell is no longer live in read results. Cassandra uses expiration metadata/tombstones to prevent stale copies from other replicas or SSTables from reappearing. **Compaction** removes expired data/tombstones when safe, coordinated with **repair** and `gc_grace_seconds`. A 7-day TTL does not guarantee bytes vanish from SSTables, snapshots, or backups at exactly 7 days.

For append-only telemetry with uniform retention, consider **TimeWindowCompactionStrategy (TWCS)**. However, backfills, widely varying TTLs, out-of-order writes, and random updates can cause SSTables to overlap and impede purging. Choose compaction strategies from **actual write patterns and operational conditions**, not solely because the data is labeled "time-series."

## 10. Reading the Two Clocks Correctly: Wall Clock vs. Monotonic Clock

In a Java application, there are at least two distinct time-measurement needs:

| Question | Appropriate tool | What not to do |
|---|---|---|
| "What UTC time is it now?" | `Clock.instant()` or `Instant.now(clock)` from a reliable system time source | Use `System.nanoTime()` as a Unix epoch |
| "How much time elapsed during this operation?" | `System.nanoTime()` for intervals within one process | Subtract two `currentTimeMillis()` calls if you need latency measurement immune to clock adjustments |
| "Which day bucket does this event belong to?" | `eventAt.atZone(ZoneOffset.UTC).toLocalDate()` | Use OS default timezone or event ingest date |
| "How much time remains until the deadline?" | `Duration.between(clock.instant(), expiresAt)` | Reuse the fixed initial TTL on every retry |
| "Which version is newer in business terms?" | `event_version` / sequence / compare-and-set | Compare only request arrival times at coordinators |

A **wall clock** can jump due to time synchronization (NTP/chrony), misconfiguration, or VM adjustments. A **monotonic clock** is ideal for measuring elapsed time inside a process, yet is **not** a cluster-wide distributed clock and does not replace event time or absolute deadlines.

### UTC, Timezones, and DST

If a UTC event occurs at `2026-11-21T23:30:00Z`, local time in Vietnam is already the morning of **Nov 22**, yet the designed table bucket **must be `2026-11-21`**. Never let a host running in UTC+7 implicitly shift `event_day`; two services in different timezones would write **the same event** to different partitions.

Daylight Saving Time (**DST**) transitions in some timezones make bucketing with local date/time even more error-prone. Keep `event_at` as a UTC `Instant` and separate local display formatting from storage keys.

## 11. Clock Skew/Drift: Risks to LWW Ordering and Data

**Clock skew** is the offset between two clocks at the same instant; **clock drift** is the rate at which a clock diverges over time. In Cassandra, both **client/driver hosts** and **coordinators/replicas** matter.

```text
Real time
  10:00:00      event E1 (on time)
  10:00:01      event E2 (on time, newer)

Client A clock 3 minutes fast:
  assigns write timestamp ~ 10:03:00 to E1

Client B clock accurate:
  assigns write timestamp ~ 10:00:01 to E2

LWW on same cell: E1 can beat E2 even though E1 is the older event.
```

For an append-only history table with a **unique event key**, two events in different rows rarely collide under LWW; however, `event_day`, `event_at`, or `retention_until` will still be wrong if derived from a faulty source clock. For a latest-state table, a bad write timestamp can **shadow valid subsequent updates**.

Mitigations:

1. Synchronize Cassandra nodes and service hosts via NTP/chrony or equivalent; monitor offsets and stability.
2. Identify the **authoritative source of event time**. IoT device clocks can be unreliable; consider storing both `device_event_at` and `gateway_received_at`.
3. Define **acceptable future/past event thresholds** based on business rules, instead of silently writing future timestamps into mutations.
4. Keep event IDs and business versions invariant across retries.
5. Never rely on `QUORUM`, `ALL`, or repair to fix bad timestamps: they converge replicas according to Cassandra's rules rather than restoring business order.

Skewed clocks can also shift observed TTL expiration; log both the **clock source** and **observed skew** when investigating TTL anomalies.

## 12. Java Driver 4.x: Writing Events with an Invariant Deadline Across Retries

Below is a Java repository example using **Apache/DataStax Cassandra Java Driver 4.x**. It accepts `eventId` and `retentionUntil` **already assigned by the business source** and does not regenerate them during retries.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ReadingEventRepository {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public ReadingEventRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO readings_by_device_day (" +
            "device_id, event_day, event_at, event_id, " +
            "temperature_c, ingested_at, retention_until) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    // true: sent and acknowledged by execute() per CL;
    // false: event already expired per policy, no mutation sent.
    public boolean save(
        String deviceId, UUID eventId, Instant eventAt,
        double temperatureC, Instant retentionUntil
    ) {
        Instant now = clock.instant();
        Duration maxFutureSkew = Duration.ofMinutes(2);
        if (eventAt.isAfter(now.plus(maxFutureSkew))) {
            throw new IllegalArgumentException("Event clock too far ahead");
        }

        long secondsLeft = Duration.between(now, retentionUntil)
            .getSeconds(); // Truncates down to whole seconds.
        if (secondsLeft <= 0) {
            return false; // Never turn 0 into USING TTL 0!
        }
        if (secondsLeft > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL too large");
        }

        // Also verify expiration horizon limits per cluster version.
        LocalDate eventDay = eventAt.atZone(ZoneOffset.UTC).toLocalDate();
        session.execute(insert.bind(
            deviceId, eventDay, eventAt, eventId, temperatureC,
            now, retentionUntil, Math.toIntExact(secondsLeft)
        ));
        return true;
    }
}
```

**Three key points:**

- `eventAt` and `retentionUntil` remain fixed for **the same event**. If a write times out, the retry path must reuse the **same `eventId`, `eventAt`, and `retentionUntil`**, without minting a new key or deadline.
- `eventDay` is derived from **event time in UTC**, not `ingested_at`. This preserves the proper partition for late-arriving events.
- `secondsLeft` is the **remaining TTL**, not a fixed 7-day TTL. Cases with less than one second left are rejected conservatively due to downward truncation; this choice should be explicitly defined in product specs.

The code does not call `setQueryTimestamp(eventAt)`: **event time is not automatically the mutation timestamp**. Driver/coordinator clocks and LWW rules have different semantics; for latest-state tables, use business versions/CAS when ordering is needed.

**Limitations:** this repository does not yet handle conditional deduplication in Cassandra, does not check `retention_until` on reads, does not eliminate all skew effects, and does not guarantee atomicity between writing history and updating latest-state. Those belong in the full application architecture.

## 13. Extracting Time Logic into a `Clock`-Testable Function

To write unit tests **independent of wall-clock time**, isolate all deadline/bucket/TTL calculations into a component depending only on arguments and a `Clock`. Java example:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

public final class RetentionClockPolicy {
    private RetentionClockPolicy() {}

    public static LocalDate utcBucket(Instant eventAt) {
        return eventAt.atZone(ZoneOffset.UTC).toLocalDate();
    }

    // Returns null when already expired or under one second left to store.
    public static Integer ttlSeconds(
        Clock clock, Instant eventAt, Instant expiresAt,
        Duration allowedFutureSkew
    ) {
        Instant now = clock.instant(); // Read clock only once.
        if (eventAt.isAfter(now.plus(allowedFutureSkew))) {
            throw new IllegalArgumentException("Future event rejected");
        }
        long remaining = Duration.between(now, expiresAt).getSeconds();
        if (remaining <= 0) {
            return null; // Never send USING TTL 0.
        }
        if (remaining > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL out of range");
        }
        return Math.toIntExact(remaining);
    }
}
```

**Design principle:** `Clock` is **injected** into services and policies; only production bootstrap code wires `Clock.systemUTC()`. In tests, pass `Clock.fixed(...)` or `Clock.offset(...)`, avoiding `Thread.sleep(...)` and real calendar dependencies.

You never need to change the OS clock for unit tests. Every check of date bucketing, expiration policy, and deadline-derived TTL runs deterministically inside the JVM under simulated time.

## 14. JUnit 5 Example Testing Day Boundaries, Deadlines, and Skewed Clocks

The tests below exercise `RetentionClockPolicy` from the previous section:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class RetentionClockPolicyTest {
    private static final Duration MAX_FUTURE = Duration.ofMinutes(2);

    @Test
    void bucketUsesUtcEvenWhenEventNearLocalMidnight() {
        Instant event = Instant.parse("2026-11-21T23:30:00Z");
        assertEquals(LocalDate.of(2026, 11, 21),
            RetentionClockPolicy.utcBucket(event));
    }

    @Test
    void ttlIsRemainingTimeNotOriginalRetention() {
        Instant start = Instant.parse("2026-11-21T10:00:00Z");
        Instant deadline = start.plus(Duration.ofMinutes(10));
        Clock atStart = Clock.fixed(start, ZoneOffset.UTC);
        Clock afterNineMinutes = Clock.offset(
            atStart, Duration.ofMinutes(9));

        assertEquals(600, RetentionClockPolicy.ttlSeconds(
            atStart, start, deadline, MAX_FUTURE));
        assertEquals(60, RetentionClockPolicy.ttlSeconds(
            afterNineMinutes, start, deadline, MAX_FUTURE));
        assertNull(RetentionClockPolicy.ttlSeconds(
            Clock.offset(atStart, Duration.ofMinutes(11)),
            start, deadline, MAX_FUTURE));
    }

    @Test
    void rejectsDeviceClockThreeMinutesIntoFuture() {
        Instant now = Instant.parse("2026-11-21T10:00:00Z");
        Clock fixed = Clock.fixed(now, ZoneOffset.UTC);
        Instant eventAt = now.plus(Duration.ofMinutes(3));

        assertThrows(IllegalArgumentException.class, () ->
            RetentionClockPolicy.ttlSeconds(
                fixed, eventAt, now.plus(Duration.ofDays(7)), MAX_FUTURE));
    }

    @Test
    void neverTurnsSubsecondDeadlineIntoTtlZero() {
        Instant now = Instant.parse("2026-11-21T10:00:00Z");
        Clock fixed = Clock.fixed(now, ZoneOffset.UTC);
        assertNull(RetentionClockPolicy.ttlSeconds(
            fixed, now, now.plusMillis(500), MAX_FUTURE));
    }
}
```

These tests **open no Cassandra connection**. They validate the Java logic: UTC bucketing, shrinking TTL against an injected clock, rejecting overly fast device clocks, and never accidentally emitting `USING TTL 0`. This forms the foundation for fast, stable, repeatable retention tests.

### Additional Cases Worth Adding

| Case | Expected behavior |
|---|---|
| Event at `23:59:59.999Z` vs. `00:00:00.000Z` next day | Land in **two distinct UTC buckets** |
| Event arriving 2 days late with original deadline | Remaining TTL **shrinks by 2 days**, never resets to 7 days |
| Replay with the same event ID and business timestamp | Same partition/clustering key; no duplicate row created by changing ID |
| Event with future timestamp past threshold | Rejected or quarantined per policy |
| Deadline already passed | No mutation issued with TTL 0 |
| Events colliding at millisecond timestamp | `event_id` distinguishes rows; tie-break order does not imply causality |
| Changing the JVM default timezone | UTC bucket **stays unchanged** |
| TTL exceeding Cassandra version horizon | Clear error/handling path, never silently truncating TTL in violation of retention |

## 15. Integration Testing TTL with Cassandra: You Cannot "Freeze" the Server with `Clock.fixed`

Simulated `Clock` unit tests **affect Java code only**. When executing a real `USING TTL`, Cassandra evaluates expiration metadata using server-side time; **`Clock.fixed` in the JVM does not alter Cassandra's clock**.

Therefore, split testing into two layers:

### Layer A — Unit Tests

- Use `Clock.fixed` or `Clock.offset`.
- Verify buckets, deadlines, TTL math, and expired-data handling rules.
- No sleeps, no running cluster required.
- Also cover events replayed from a DLQ days later, across DST transitions, and under source clock skew.

### Layer B — Integration Tests on a Test Cluster

1. Create a **separate keyspace/table** or use a unique UUID.
2. Write a cell with a short yet safe TTL (e.g., 10–20 seconds).
3. Read immediately by partition key: value exists, `ttl(col)` is a **positive integer** within a reasonable range.
4. Poll with a bounded loop slightly past the TTL; confirm the cell eventually **ceases to be live**, without asserting `ttl()` returns exactly `0` or a negative number.
5. Confirm non-TTL cells in the same row remain live if the schema expects that behavior.
6. Repeat for retry/overwrite cases with a new TTL, distinguishing client-side timing races from replica bugs.

CQL example on a dedicated test partition:

```sql
CREATE TABLE IF NOT EXISTS ttl_clock_test_by_id (
    id uuid PRIMARY KEY,
    ephemeral text,
    persistent_note text
);

INSERT INTO ttl_clock_test_by_id (id, persistent_note)
VALUES (
    77777777-1414-4141-8141-777777777777,
    'remains visible'
);

UPDATE ttl_clock_test_by_id
USING TTL 15
SET ephemeral = 'temporary'
WHERE id = 77777777-1414-4141-8141-777777777777;

SELECT ephemeral, ttl(ephemeral), persistent_note
FROM ttl_clock_test_by_id
WHERE id = 77777777-1414-4141-8141-777777777777;
```

Once the TTL ends, `ephemeral` no longer has a live value, while `persistent_note` can still be read. Never claim SSTables were physically purged solely from read results; **compaction and repair** determine safe reclamation timing.

### Testing Clock Skew on Nodes

Never change the OS clock on production Cassandra nodes, shared machines, or shared Docker hosts to simulate skew: doing so disrupts other services, TLS, logging, and Cassandra itself. When distributed clock-skew testing is required, use **an isolated environment, appropriate fault-injection tooling, and a clock-recovery plan**. Inside the application, unit tests with `Clock.offset` cover most future-event classification logic without touching node clocks.

## 16. Replication, CL, TWCS, and Verifying Retention in Operations

Retaining data with TTL is more than an `INSERT` statement. In a distributed cluster, evaluate the lifecycle all the way to safe reclamation:

| Component | Operational question |
|---|---|
| **Replication factor** | How many replicas hold the partition; are any temporarily disconnected? |
| **Consistency level** | How do `ONE`, `QUORUM`, `ALL` affect acknowledgments and reads? |
| **Clock health** | What are NTP/chrony offsets, drift, and any nodes/clients exceeding thresholds? |
| **Event lag** | P50/P95/P99 of `ingested_at - event_at`; are large backfills occurring? |
| **Partition size** | Are there hot partitions or oversized daily buckets? |
| **Tombstones** | How many tombstones/expired cells do short-TTL workloads and updates produce? |
| **Compaction** | Are backlogs, SSTable overlap, I/O, and actual retention stable? |
| **Repair** | Have replicas converged before tombstones become eligible for purging? |
| **Snapshots/backups** | How long is TTL-expired data still retained inside snapshots/backups? |

CQL example checking metadata of a live cell:

```sql
SELECT event_at, event_id, temperature_c,
       writetime(temperature_c) AS write_us,
       ttl(temperature_c) AS ttl_s,
       retention_until
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
```

**Never infer from `writetime(temperature_c)` that `event_at` is accurate**, or from `ttl_s` that every replica is strictly synchronized. `writetime()` reflects metadata of the observed live cell, and `ttl()` reflects remaining seconds; neither reports retry history, losing tombstones, or proof of physical deletion.

### TWCS Only Fits Matching Write Patterns

For mostly **append-only** event histories with nearly uniform TTLs, **TimeWindowCompactionStrategy** can reclaim SSTables efficiently by time window. However, when late-arriving records, frequent updates to old cells, or widely varying "time left until deadline" TTLs occur, SSTables can mix multiple lifetimes and complicate cleanup.

**Never alter `gc_grace_seconds` or force compaction to fix clock/retention bugs.** Grace protects tombstones against stale replicas; compaction cannot turn a wrong business deadline into a right one. If strict physical deletion/compliance rules exist, account for snapshots, backups, repair strategies, and purge pipelines too.

## 17. Time-Design Deployment Checklist

Before taking a time-based table to production, answer:

1. **What are the primary queries?** Do partition/clustering keys serve them directly, and do time ranges cross multiple buckets?
2. **What is the event-time source?** Are device clocks, gateways, and timezones validated?
3. **How are bucket dates computed?** Use UTC and a single consistent rule across all writers and retries.
4. **Are event IDs and ordering stable?** `event_id` stays constant across replays; when latest-state is needed, use versions/CAS or a single writer.
5. **Is retention measured from event time, ingest time, or an explicit deadline?** SLAs must define clear rules for late arrivals and backfills.
6. **Where is TTL calculated and how is it rounded?** Block accidental TTL 0 and verify Cassandra version TTL/expiration limits.
7. **Is `Clock` injected and tested?** Unit-test UTC midnight, future skew, expired events, and replays; keep integration tests independent of exact `ttl()` numbers.
8. **Can stale replicas resurrect data?** Track repair, tombstones, and grace; never lower grace arbitrarily.
9. **Have hot partitions and compaction been checked?** Estimate traffic per bucket and observe partition sizes and cleanup strategy.
10. **Are metrics available to prove retention compliance?** Log `event_id`, `event_at`, `ingested_at`, `retention_until`, sent TTL, retry count, and clock source, avoiding unnecessary sensitive data.

Decisions should be captured as a **service time contract**: defining the time source, lag/skew bounds, retention anchor, expired-event handling, version ordering, TTL selection, and test strategy. That matters far more than merely adding a `created_at` column to a table.

## 18. Self-Check Questions

**Question 1.** An event occurred at 10:00 on Nov 20 and was ingested at 10:00 on Nov 22. Retention is 7 days from event time. If `USING TTL 604800` is written at ingest, how does the actual TTL deadline compare to policy?

**Answer:** The new TTL expires near Nov 29, whereas the event-time deadline is Nov 27. You must compute **remaining TTL** from the fixed deadline.

**Question 2.** Why can choosing `device_id` alone as the partition key be dangerous for 10-event/second telemetry retained for months?

**Answer:** The partition can grow huge and become a hot partition. Consider a **time bucket**, such as daily or hourly, depending on load and queries.

**Question 3.** A UTC event at `23:30` on Nov 21 is processed on a UTC+7 server. What is `event_day` under the UTC design?

**Answer:** **Nov 21**, not Nov 22 in local time.

**Question 4.** Two events share the same `event_at` down to the millisecond, yet have different `event_id` values. Why include both in the clustering key?

**Answer:** To prevent overwriting one row simply because timestamps collided at millisecond resolution. UUID tie-break ordering **does not prove** actual occurrence order.

**Question 5.** An older event arrives late and updates latest-state with a newer mutation timestamp. Is Cassandra guaranteed to keep the event that occurred most recently?

**Answer:** **No.** LWW compares mutation timestamps rather than deducing business order. Use versions/CAS, a single writer, or an ordered projector.

**Question 6.** `0.5` seconds remain until `retention_until`; Java's `Duration.getSeconds()` returns 0. Should `USING TTL 0` be sent?

**Answer:** **No.** TTL 0 means **no TTL**; a conservative policy rejects writing when less than one second remains.

**Question 7.** Can `Clock.fixed` in a Java unit test force the Cassandra server to expire TTL immediately?

**Answer:** **No.** `Clock.fixed` only changes how Java code reads time. The Cassandra server still uses its own clock and metadata; separate integration tests are required.

**Question 8.** Can `System.nanoTime()` be used as an epoch microsecond value for `USING TIMESTAMP`?

**Answer:** **No.** `nanoTime` is meant for measuring intervals inside one process, not a Unix epoch meaningful across machines.

**Question 9.** Why is TWCS compaction not always optimal when heavy event backfills occur?

**Answer:** Late/out-of-order data and varying TTLs can mix lifetimes inside SSTables, reducing expiration-cleanup efficiency; evaluate against actual workloads.

**Question 10.** Does rewriting with the same event ID and deadline while calling `USING TTL 604800` on every retry preserve the deadline?

**Answer:** **No.** A new mutation can reset TTL starting from the retry time. Keep **`retention_until` immutable** and compute remaining TTL from that deadline.

---

**Key takeaway:** Designing time-based data in Cassandra requires separating **event time, ingest time, mutation timestamp, and retention deadline**; choosing **partitions/time buckets and clustering keys around queries**; distinguishing **event-based** from **ingest-based** retention; and preventing retries from extending deadlines. Inject `Clock` into Java for deterministic unit tests, while testing actual Cassandra expiration through separate integration tests. Finally, monitor **clock skew, RF/CL, tombstones, compaction, and repair** to query efficiently and enforce data lifecycles safely.
