# Testing Timezones, Timestamps, TTL, and Expired Data in Apache Cassandra

## 1. Goal and Scope of This Lesson

In Apache Cassandra, a row is typically located by **partition key** and **clustering key**, read/written through a coordinator and replicas according to the **replication factor (RF)** and **consistency level (CL)**. In Java applications, storing an accurate timestamp while computing the wrong **daily bucket** can make queries return empty results; misunderstanding TTL can make tests flaky or mislead the business into thinking data has been physically deleted.

This lesson belongs to the **Integration Testing** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**; its goal is to build tests connecting to **real Cassandra**, not just mocking the Java Driver, to verify:

1. CQL `timestamp` and Java `Instant` represent **the same absolute point in time**.
2. CQL `date` and Java `LocalDate` represent **a calendar date with no timezone**.
3. One UTC instant can fall on **two different calendar dates** depending on timezone; a `(device_id, event_day)` partition key must follow a consistent bucketing policy.
4. CQL literals with `Z` or an explicit offset normalize properly; literals omitting timezone make tests environment-dependent.
5. Event timestamp (**`event_time`**) differs from Cassandra's **write timestamp** (`WRITETIME`, microseconds).
6. `USING TTL`, `TTL(column)`, `default_time_to_live`, and expired data have distinct semantics.
7. An expired cell reads back as **no longer live**, while SSTables/tombstones persist until compaction.
8. Test TTLs with **polling, deadlines, and margin**, avoiding rigid per-second sleeps or shifting production server clocks.
9. Combine Testcontainers/JUnit 5, Java Driver, Spring Data (if used), CL, and observability to diagnose bugs.
10. Build a test matrix, incident runbooks, and pre-deploy checklist.

**Reference versions:** Java examples use Java Driver **4.x** (`com.datastax.oss.driver.api.*`), Java 17/JUnit 5, Testcontainers Cassandra, and Awaitility. Exact Maven coordinates/APIs must match your chosen version; Cassandra server 4.x used in lab examples does not imply all timestamp/TTL features or formats match every Cassandra 3.x/5.x release. Single-node tests do not verify multi-DC or production quorum behavior.

## 2. Five Time Concepts You Must Never Equate

| Concept | Meaning | Typical Java / CQL Types | Common Mistake |
|---|---|---|---|
| **Instant / absolute point** | A point on the UTC timeline | `java.time.Instant`, CQL `timestamp` | Treating timestamp as a local clock string without offset |
| **Local date / calendar date** | Date in a calendar system, timezone-free | `LocalDate`, CQL `date` | Assuming a date itself carries a UTC offset |
| **ZoneId / timezone** | Geographic offset/DST rules | `ZoneId`, `ZonedDateTime` | Using a fixed offset for all dates/years |
| **Write timestamp** | Timestamp used by Cassandra to reconcile mutations | `WRITETIME(column)`, microseconds | Confusing with business `event_time` |
| **TTL / expiration deadline** | Lifespan of a cell/row marker per Cassandra rules | `USING TTL`, `TTL(column)` | Believing TTL expiry deletes SSTables immediately |

In CQL, `timestamp` represents an instant (storage precision is **milliseconds**); Java `Instant` can hold nanoseconds. Thus, **never test nanosecond round-trips** by writing a nanosecond-precision `Instant` expecting Cassandra to preserve every sub-millisecond digit.

`date` is a different type: `2026-11-21` is **not** `2026-11-21T00:00:00Z` or a zero-offset timestamp.

### 2.1. Illustrating One Instant Across Two Calendar Dates

~~~text
Instant: 2026-11-21T17:30:00Z

In UTC:
  2026-11-21, 17:30

In Asia/Ho_Chi_Minh (+07:00):
  2026-11-22, 00:30

If partition key includes event_day:
  UTC-day bucket   = 2026-11-21
  VN-day bucket    = 2026-11-22

=> Two different partitions if conventions are mixed.
~~~

In your system, **standardize `bucket-day`** to UTC or the business timezone and enforce it across writers, repositories, backfills, queries, and integration tests. Never let individual JVMs/hosts pick `ZoneId.systemDefault()` from the environment.

## 3. Divergence Diagram Between Writer, Reader, and Cassandra

~~~mermaid
flowchart TD
    A["Event Instant UTC"] --> B["Writer computes event_day via ZoneId"]
    A --> C["Reader computes event_day via ZoneId"]
    B --> D["Partition key: device_id + event_day"]
    C --> E["WHERE device_id=? AND event_day=?"]
    D --> F["Cassandra Murmur3 token + replica placement"]
    E --> G{"Do both zone policies match?"}
    G -->|Yes| H["Queries the right logical partition"]
    G -->|No| I["Queries another partition: may get 0 rows"]
    F --> H
~~~

Cassandra does not automatically “fix” `event_day` just because `event_time` has the right UTC offset. The partition key is **whatever CQL value was written**, not auto-derived from another timestamp column unless explicitly designed that way.

### 3.1. Mistake to Avoid

~~~java
// ANTI-PATTERN: date shifts with each machine's default timezone.
LocalDate eventDay =
    LocalDateTime.ofInstant(eventTime, ZoneId.systemDefault())
        .toLocalDate();
~~~

A service in a UTC container and a batch job in another timezone will read/write different partitions even with the same UUID and `Instant`.

Replace with an explicit policy:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

static LocalDate utcDay(Instant instant) {
    return instant.atZone(ZoneId.of("UTC")).toLocalDate();
}
~~~

If business rules require `Asia/Ho_Chi_Minh`, configure a fixed `ZoneId` in controlled configuration and test boundaries. **Never** write using local dates while querying by UTC dates.

## 4. CQL Model for Integration Testing

### 4.1. Lab Keyspace and Table

~~~cql
-- LAB ONLY: RF=1 SimpleStrategy for single-node container tests.
-- Production needs proper RF/DC, usually NetworkTopologyStrategy.
CREATE KEYSPACE IF NOT EXISTS temporal_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS temporal_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    note text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

In this table:

- **Partition key:** `(device_id, event_day)`.
- **Clustering key:** `event_time`.
- **CQL `timestamp`:** Java apps should bind `Instant`.
- **CQL `date`:** Java apps should bind `LocalDate`.
- **`reading_value`, `status`, `note`:** regular columns, each capable of holding distinct TTLs.
- Each integration test should generate its own `device_id` (random UUID) to prevent state leakage across parallel tests.
- Short TTLs are for tests only. In production, retention policies must reflect business needs and capacity.

**Note:** RF=1 in Testcontainers is a trade-off for fast single-container execution; it **cannot test quorum or replication repair like an RF=3 cluster**. Those belong in a separate multi-node test cluster.

### 4.2. CQL Query by Partition/Key

~~~cql
SELECT event_time, reading_value, status, note
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

With the full key, the query targets one exact row. If the bucket day is miscomputed, the query returns `null` even though the row exists in another day's partition.

### 4.3. Writing a Row with an Explicit Timestamp

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, note
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK',
    'permanent'
);
~~~

Literal `2026-11-21T10:30:00Z` carries an explicit UTC suffix, making it far less environment-dependent than a string without an offset.

## 5. Testing CQL Timestamps with Offsets

### 5.1. Two Representations of the Same Instant

~~~cql
-- With partition day 2026-11-21:
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, note
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'UTC_LITERAL',
    'same instant'
);

-- Verify the exact row using an equivalent offset timestamp:
SELECT event_time, status
FROM temporal_lab.readings_by_device_day
WHERE device_id =
    11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T17:30:00+0700';
~~~

`10:30Z` and `17:30+07:00` denote the exact same absolute instant; they are not two separate rows. The test should confirm **the inserted row is returned**, not just print strings and compare formatted text.

### 5.2. Timezone-Less CQL Literals Are a Source of Bugs

~~~cql
-- Discouraged as an environment-independent fixture:
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21 10:30:00',
    24.6
);
~~~

When a literal omits timezone info, parsing/display depends on client/server/tool settings and release configs. **In integration tests, always use ISO 8601 with `Z`/offset or bind `Instant` directly.**

### 5.3. Never Use `cqlsh` Formatting as the Sole Source of Truth

`cqlsh` has its own display timezone settings depending on version. Two environments may print the same timestamp with different local strings while holding **identical epoch milliseconds**.

In tests, read via the Java Driver:

~~~java
Instant actual = row.getInstant("event_time");
assertEquals(expectedInstant, actual);
~~~

Use millisecond-precision `Instant` values to avoid mismatches because Cassandra `timestamp` drops nanoseconds.

## 6. Java `Instant`, `OffsetDateTime`, `LocalDateTime`, and `LocalDate`

### 6.1. Choosing Types by Semantics

| Java Type | Information Held | When to Use |
|---|---|---|
| `Instant` | Absolute UTC instant | Storing/comparing CQL `timestamp` |
| `OffsetDateTime` | Date-time with fixed UTC offset | Offset-bearing inputs; convert to `Instant` on save |
| `ZonedDateTime` | Date-time with region/DST rules | Computing business dates, display |
| `LocalDateTime` | Date-time without zone/offset | Only when an external timezone policy applies |
| `LocalDate` | Calendar date | CQL `date`, daily partition buckets |
| `Clock` | Injectable time source | Testing “now” domain logic; does not replace server clock |

**`LocalDateTime` does not uniquely identify an `Instant`.** Converting to an absolute point requires a timezone or offset plus a DST policy.

### 6.2. Mandatory Test: One Instant, Two Timezones

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class TimeBucketPolicyTest {
    @Test
    void oneInstantCanFallIntoDifferentCalendarDates() {
        Instant instant = Instant.parse("2026-11-21T17:30:00Z");

        LocalDate utc = instant
            .atZone(ZoneId.of("UTC"))
            .toLocalDate();

        LocalDate vietnam = instant
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertEquals(LocalDate.of(2026, 11, 21), utc);
        assertEquals(LocalDate.of(2026, 11, 22), vietnam);
        assertNotEquals(utc, vietnam);
    }
}
~~~

This is a **unit test** of the bucketing rule; useful, yet insufficient to prove CQL mapping. Integration tests must write `event_day` and read rows back by partition key.

### 6.3. Injecting a Fixed Timezone via Configuration

~~~java
public final class EventDayPolicy {
    private final ZoneId zone;

    public EventDayPolicy(ZoneId zone) {
        this.zone = zone;
    }

    public LocalDate bucket(Instant eventTime) {
        return eventTime.atZone(zone).toLocalDate();
    }
}

// Production examples:
// new EventDayPolicy(ZoneId.of("UTC"))
// or ZoneId.of("Asia/Ho_Chi_Minh")
// per the shared contract across services.
~~~

Prefer `ZoneId.of("Area/City")` if business timezones have past or future DST rules; never hardcode hour shifts via `plusHours`.

## 7. Precision: CQL `timestamp` Stores Milliseconds, Java `Instant` Holds Nanoseconds

### 7.1. A Common Test Pitfall

~~~java
Instant expected = Instant.parse(
    "2026-11-21T10:30:00.123456789Z");

// Cassandra CQL timestamp typically has millisecond precision.
// Do not expect to read back all 123456789 nanoseconds verbatim.
~~~

When written through the driver, stored values match at millisecond precision:

~~~java
import java.time.temporal.ChronoUnit;

Instant expectedAtMillis =
    expected.truncatedTo(ChronoUnit.MILLIS);
~~~

**Verify exact truncation/rounding behavior against your driver/version.** For standard integration tests, pick millisecond-aligned values like `Instant.parse("...123Z")` so tests do not depend on sub-millisecond rounding details.

### 7.2. Don't Confuse Epoch Seconds with Epoch Milliseconds

~~~text
Unix time (seconds):       1795257000       (example)
Unix time (milliseconds):  1795257000000    (example)
Unix time (microseconds):  1795257000000000 (example)

CQL timestamp:   milliseconds since Unix epoch.
WRITETIME(cell):  microseconds since Unix epoch.
USING TIMESTAMP:  typically takes microsecond write timestamp.
~~~

These numbers illustrate **units of magnitude** only; in tests, use `Instant` and `toEpochMilli()` instead of typing raw epoch numbers by hand. Never pass `WRITETIME` (microseconds) directly into `Instant.ofEpochMilli`.

### 7.3. Proper Conversion Helper for Write Timestamps

~~~java
import java.time.Instant;

static Instant fromWriteTimestampMicros(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long microPart = Math.floorMod(micros, 1_000_000L);

    return Instant.ofEpochSecond(
        seconds,
        microPart * 1_000L);
}
~~~

Use `floorDiv`/`floorMod` to support negative pre-Unix-epoch timestamps rather than truncate-toward-zero integer division assuming positive remainders.

**Never treat `WRITETIME` as `event_time`.** Writes can arrive late, be replayed, or carry client-specified write timestamps.

## 8. `WRITETIME` and Event Timestamps Are Two Independent Axes

### 8.1. Reading a Cell's Write Timestamp

~~~cql
SELECT event_time,
       reading_value,
       WRITETIME(reading_value) AS write_time_us
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

For a non-null regular column, `WRITETIME(reading_value)` returns the reconciliation timestamp of that cell, normally in **microseconds**. If the column has no value, the result can be `null`.

Notes:

- Never call `WRITETIME` on a primary key column as a substitute for data timestamps.
- Never assume `WRITETIME` of two regular columns matches if they were updated in separate writes.
- CQL write timestamps belong to mutations for last-write-wins reconciliation; they need not equal when the business event occurred.
- Manual `USING TIMESTAMP` can place timestamps in the past or future relative to the server, altering update winners/losers.

### 8.2. Business Example: Writing a 1-Hour-Old Event

~~~text
Sensor event occurred:         2026-11-21T08:00:00Z
Client sends data to DB:       2026-11-21T09:00:00Z
Server receives mutation:      around 09:00Z
Write timestamp (if auto):     around write time, per clock/node

event_time != WRITETIME(reading_value) is completely normal.
~~~

A test asserting `WRITETIME = event_time` **assumes invalid semantics**. Order business events by `event_time` via clustering design, not by write timestamps unless explicitly specified.

### 8.3. TTL Is Not Computed by Subtracting `event_time`

If an old event is ingested today with a 60-second TTL, the cell's TTL normally counts from **when the server applies the mutation**, not from the `event_time` column. To enforce “expire 30 days after the event occurred”, design an explicit expiry policy (e.g., compute remaining TTL from `event_time` at ingest) and handle late arrivals and future-skewed events clearly.

Never write a test like:

~~~text
event_time = 7 days ago
INSERT USING TTL 1 hour today
=> row must already be expired immediately
~~~

That assumption is false for standard Cassandra TTLs.

## 9. TTL: What Actually Expires?

### 9.1. CQL `USING TTL`

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, status
) VALUES (?, ?, ?, ?, ?)
USING TTL 8;
~~~

`8` is in **seconds** in this lab example, not milliseconds. With prepared statements and supporting driver versions, TTL can be bound:

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, status
) VALUES (?, ?, ?, ?, ?)
USING TTL ?;
~~~

Regular columns and row liveness markers follow Cassandra TTL semantics. **Do not think of a primary key column itself as having an independent TTL like a regular column**; primary keys identify rows/partitions.

### 9.2. Table-Level vs Mutation-Level TTL

Cassandra also provides the `default_time_to_live` table option depending on version:

~~~cql
-- ONLY for a DEDICATED test table; never alter shared tables carelessly.
CREATE TABLE temporal_lab.ttl_only_demo (
    id uuid PRIMARY KEY,
    value text
) WITH default_time_to_live = 600;
~~~

This defaults data in the table to 600 seconds per table TTL semantics. Explicit mutation TTLs interact with or override the table default per Cassandra version rules. **Never edit `default_time_to_live` on production tables just to make tests run faster.**

### 9.3. TTL Is Per-Cell, Not a “Drop Whole Table Timer”

One row can hold:

- `reading_value` with **no TTL**.
- `status` with an 8-second TTL.
- `note` with another TTL or no TTL.

When `status` expires, the row **can still exist** because `reading_value` remains live. Tests must inspect **the expected cell** rather than assuming `ResultSet.one()==null`.

### 9.4. `TTL(column)` Is Only Remaining Seconds at Read Time

~~~cql
SELECT reading_value,
       status,
       TTL(status) AS status_ttl_seconds
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

If `status` has a TTL, `TTL(status)` returns **remaining seconds** as an integer. If the cell has no TTL or no live value, it returns `null`. Some function/collection restrictions depend on version, so test against supported types.

**Never assert `TTL == 8` immediately after INSERT.** Time spent traversing driver, network, scheduler, and server can lower the observed TTL. Assert within a **reasonable range** or poll until the live cell disappears.

## 10. TTL Expiry Does Not Mean Immediate SSTable Deletion

### 10.1. TTL Turns a Cell Non-Live

Cassandra handles expiration/tombstones per its distributed storage model. Once TTL expires, reads stop returning the cell as a **live value**. However, physical data and tombstones can stay in SSTables/memtables until compaction satisfies safety rules.

~~~mermaid
flowchart TD
    A["INSERT / UPDATE with TTL"] --> B["Live cell, TTL counting down"]
    B --> C{"TTL expired?"}
    C -->|No| D["SELECT sees live value"]
    C -->|Yes| E["Read path treats cell as expired"]
    E --> F["Tombstone / expired state remains in storage"]
    F --> G["Compaction + safety rules"]
    G --> H["Physical space may be reclaimed"]
~~~

**Critical mistake:** asserting “`SELECT` finds no row ⇒ SSTable bytes decreased” is unfounded. Disk reclamation depends on compaction, tombstone safety, repair, RF, `gc_grace_seconds`, and compaction strategy.

### 10.2. Watch Out for Older Values and Overwriting TTLs

An update with a TTL writes a new cell version; when that version expires, do not assume an older value reappears like an MVCC database. Tombstones/expirations participate in reconciliation, preventing stale values from resurrecting within the valid window.

Proper tests explicitly define **old and new values**, verify post-expiry reads, and avoid relying on resurrection behaviors not guaranteed by CQL.

### 10.3. TTL and Consistency

In an RF=3 cluster:

- Replicas may receive mutations/TTLs at slightly different times; clock skew affects expiration timing.
- Read/write CLs control response requirements, not perfect cross-node clock sync.
- Repair and hinted handoff synchronize replica states per Cassandra semantics, but do not replace NTP/clock discipline.
- Single-node RF=1 tests cannot detect cross-replica/time-skew bugs; production-like tests require controlled multi-node topologies.

## 11. Why `Thread.sleep(TTL * 1000)` Causes Flaky Tests

### 11.1. The Problem

~~~java
// ANTI-PATTERN:
insertWithTtl(3);
Thread.sleep(3000);
assertNull(findExpired());
~~~

This test assumes:

- TTL starts ticking at the exact moment the Java method returns.
- Server and client clocks align to the millisecond.
- Scheduling/network introduce zero jitter.
- Read responses experience no cache/paging/replication lag.
- The assertion targets the right cell or row liveness.

Those assumptions are unsafe. If the scheduler wakes early, the test fails; if sleep is padded excessively, the suite drags and hides true root causes.

### 11.2. Use Deadline-Bounded Polling

A practical strategy:

1. Write data with a **sufficiently long TTL** so you can assert it is live before expiring.
2. Read immediately and confirm the cell is **live**.
3. Poll `SELECT` every few hundred milliseconds.
4. Stop once expiry is observed or **the deadline expires**.
5. On deadline timeout, log query ID, CL, row status/types, and metrics (without PII).
6. Use unique UUIDs, clean up test resources, and avoid launching too many parallel TTL tests at once.

Example with Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

insertStatusWithTtl(deviceId, day, eventTime, "TEMP", 8);

assertEquals("TEMP", findStatus(deviceId, day, eventTime));

await()
    .atMost(Duration.ofSeconds(25))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() ->
        assertNull(findStatus(deviceId, day, eventTime)));
~~~

This illustrates test structure; `insertStatusWithTtl` and `findStatus` must be implemented with CI-appropriate timeouts. **Never use Awaitility to “quiet” a test suffering from schema bugs or severe clock drift**: deadlines and logs must keep failures diagnosable.

### 11.3. Choose a TTL Long Enough to Assert Pre-Expiry State

With `TTL=1s` on a slow CI runner, the very first read can arrive after expiration. When testing both *before* and *after* states, use e.g. an 8–10 second TTL and a 20–30 second upper bound. That trades off **stability vs test runtime**; tune numbers to your CI environment.

Never run 100 concurrent TTL tests each sleeping 30 seconds and call it reliable testing.

## 12. Building a Cassandra Testcontainers Integration Suite

### 12.1. Test Suite Architecture

~~~text
JUnit 5 / Testcontainers
  |
  +-- Cassandra container (single node, lab keyspace RF=1)
  |
  +-- CqlSession using Java Driver 4.x
  |     |
  |     +-- Prepared INSERT / SELECT
  |     +-- SET TTL / read TTL(column)
  |
  +-- Tests
        +-- timestamp round-trip
        +-- timezone bucket
        +-- partial-cell TTL expiry
        +-- full-row TTL expiry
        +-- WRITETIME vs event_time
        +-- negative/pre-epoch timestamp
~~~

Never mock `CqlSession` when testing **CQL codecs, Cassandra expiration, and query execution**. Mocks remain valuable for pure business-logic unit tests, yet cannot confirm how data actually persists and expires.

### 12.2. Required Dependencies

Minimal `pom.xml` example (versions omitted to avoid BOM conflicts):

~~~xml
<!-- Declare dependencies matching your chosen compatible BOM/versions. -->
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>cassandra</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Java Driver 4.x must be on the app/test classpath via its BOM. **Never assume all Testcontainers 1.x/2.x releases share identical artifact coordinates and imports**; check release changelogs. Never hardcode test secrets into production configs.

### 12.3. CI Rules

- A Docker-compatible runtime must be ready; if missing, fail clearly as an environment error instead of faking a pass.
- Container startup can be slow; separate **startup timeouts** from **TTL wait timeouts**.
- Pin Cassandra server and driver versions intentionally instead of floating tags.
- Never let tests accidentally connect to a production cluster via environment variables.
- Single-container RF=1 tests do not verify cross-DC, repair, or quorum behavior.
- Sample data uses random UUIDs; schema/table names are dedicated strictly to tests.

## 13. JUnit 5 + Testcontainers + Java Driver 4.x Fixture

### 13.1. Test Suite Connected to Real Cassandra

Example using `CassandraContainer` from a Testcontainers version supporting the corresponding constructor/metadata methods, Cassandra **4.1.x** in a lab, Java Driver 4.x, and JUnit 5. RF=1 keyspace is strictly for a **single-node** lab and does not replace multi-replica production tests.

~~~java
package demo.cassandra.temporal;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class CassandraTemporalIntegrationTest {

    @Container
    static final CassandraContainer<?> DB =
        new CassandraContainer<>(
            DockerImageName.parse("cassandra:4.1.6"));

    static CqlSession session;
    static PreparedStatement insertPermanent;
    static PreparedStatement insertTtl;
    static PreparedStatement updateStatusTtl;
    static PreparedStatement selectRow;
    static PreparedStatement selectStatusTtl;

    @BeforeAll
    static void startSessionAndSchema() {
        // Verify getContactPoint/getLocalDatacenter API
        // in your selected Testcontainers release.
        session = CqlSession.builder()
            .addContactPoint(DB.getContactPoint())
            .withLocalDatacenter(DB.getLocalDatacenter())
            .build();

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS temporal_lab " +
            "WITH replication = {" +
            "'class': 'SimpleStrategy', " +
            "'replication_factor': 1} " +
            "AND durable_writes = true"
        );

        session.execute(
            "CREATE TABLE IF NOT EXISTS " +
            "temporal_lab.readings_by_device_day (" +
            "device_id uuid, " +
            "event_day date, " +
            "event_time timestamp, " +
            "reading_value double, " +
            "status text, note text, " +
            "PRIMARY KEY ((device_id, event_day), event_time)) " +
            "WITH CLUSTERING ORDER BY (event_time DESC)"
        );

        insertPermanent = session.prepare(
            "INSERT INTO temporal_lab.readings_by_device_day " +
            "(device_id, event_day, event_time, " +
            " reading_value, status, note) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );

        insertTtl = session.prepare(
            "INSERT INTO temporal_lab.readings_by_device_day " +
            "(device_id, event_day, event_time, " +
            " reading_value, status) " +
            "VALUES (?, ?, ?, ?, ?) USING TTL ?"
        );

        updateStatusTtl = session.prepare(
            "UPDATE temporal_lab.readings_by_device_day " +
            "USING TTL ? SET status = ? " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );

        selectRow = session.prepare(
            "SELECT event_time, reading_value, status, note " +
            "FROM temporal_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );

        selectStatusTtl = session.prepare(
            "SELECT TTL(status) AS seconds_left " +
            "FROM temporal_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );
    }

    static Row read(UUID id, LocalDate day, Instant at) {
        BoundStatement query = selectRow
            .bind(id, day, at)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);
        return session.execute(query).one();
    }

    @AfterAll
    static void closeSession() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void timestampRoundTripUsesInstantAtMillisecondPrecision() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T10:30:00.123Z");
        LocalDate day = at.atZone(ZoneId.of("UTC"))
            .toLocalDate();

        session.execute(insertPermanent.bind(
            id, day, at, 24.6, "OK", "persistent"));

        Row row = read(id, day, at);
        assertNotNull(row);
        assertEquals(at, row.getInstant("event_time"));
        assertEquals(24.6, row.getDouble("reading_value"), 0.00001);
        assertEquals("OK", row.getString("status"));
    }

    @Test
    void twoTimezonesCanPointToDifferentDatePartitions() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T17:30:00Z");
        LocalDate utcDay = at.atZone(ZoneId.of("UTC"))
            .toLocalDate();
        LocalDate localDay = at
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertNotEquals(utcDay, localDay);
        session.execute(insertPermanent.bind(
            id, utcDay, at, 25.0, "OK", "UTC bucket"));

        assertNotNull(read(id, utcDay, at));
        // Wrong bucket -> row not found despite exact event_time.
        assertNull(read(id, localDay, at));
    }

    @Test
    void fullyExpiringInsertedRowEventuallyDisappears() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T11:00:00Z");
        LocalDate day = LocalDate.of(2026, 11, 21);

        session.execute(insertTtl
            .bind(id, day, at, 26.0, "TEMP", 12)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE));

        Row first = read(id, day, at);
        assertNotNull(first);
        assertEquals("TEMP", first.getString("status"));

        await()
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(300))
            .untilAsserted(() ->
                assertNull(read(id, day, at)));
    }

    @Test
    void expiringOneCellDoesNotRemoveAnotherLiveCell() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T12:00:00Z");
        LocalDate day = LocalDate.of(2026, 11, 21);

        session.execute(insertPermanent.bind(
            id, day, at, 22.5, null, "KEEP"));

        session.execute(updateStatusTtl.bind(
            12, "TEMP", id, day, at));

        Row before = read(id, day, at);
        assertNotNull(before);
        assertEquals("TEMP", before.getString("status"));
        assertEquals(22.5,
            before.getDouble("reading_value"), 0.00001);

        Row ttlRow = session.execute(
            selectStatusTtl.bind(id, day, at)).one();
        assertNotNull(ttlRow);
        assertFalse(ttlRow.isNull("seconds_left"));
        int secondsLeft = ttlRow.getInt("seconds_left");
        // Near second boundaries, remaining TTL may approach 0.
        assertTrue(secondsLeft >= 0 && secondsLeft <= 12);

        await()
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(300))
            .untilAsserted(() -> {
                Row after = read(id, day, at);
                assertNotNull(after);
                assertNull(after.getString("status"));
                assertEquals(22.5,
                    after.getDouble("reading_value"), 0.00001);
                assertEquals("KEEP", after.getString("note"));
            });
    }
}
~~~

This is an **illustrative fixture**: compilation/runtime has not been verified across every Testcontainers/Driver combination. Pin compatible artifacts, verify JUnit extension/container startup, and adjust local DC names and constructors to match your image/version.

### 13.2. Every Test Needs Its Own Primary Key

If multiple tests write to the same partition/timestamp, TTLs or updates from one test interfere with another. Using `UUID.randomUUID()` isolates partitions without making integration tests non-deterministic. Still isolate keyspaces/tables exclusively for tests and enforce controlled cleanup.

### 13.3. Separate Fast Tests from Long-Term Storage Tests

- Sharing one container cuts startup cost, though heavy mutations/TTLs accumulate tombstones.
- Never `TRUNCATE` a table shared by parallel tests.
- Never alter `default_time_to_live` on a shared table for one test case.
- Never run aggressive repair/compaction on a container shared with other tests.
- Close `CqlSession` after the suite and clean up disposable containers.
- Testing physical purges/tombstone compaction belongs in a dedicated storage suite.

## 14. Testing Cell Expiry vs Row Expiry Separately

### 14.1. One Cell Has a TTL, Others Do Not

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, note
) VALUES (?, ?, ?, ?, ?);

UPDATE temporal_lab.readings_by_device_day
USING TTL 8
SET status = 'TEMP'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

After expiration:

- The row **persists** because `reading_value` and `note` remain live.
- `status` expired: `row.getString("status")` returns `null`.
- `TTL(status)` no longer has a live-cell countdown.
- Never assert `ResultSet.one()==null` for **partial TTL**.

### 14.2. All Regular Cells Have a TTL

If `INSERT ... USING TTL` applies to every regular cell and the row marker, once all expire, no live row remains. Test this separately from partial TTL; static columns or mixed TTLs introduce more nuanced states.

### 14.3. Null `TTL(column)` Does Not Prove Expiry

~~~cql
SELECT reading_value, status,
       TTL(status) AS remaining
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

| Cell Value | `TTL(column)` | Possible Interpretations |
|---|---|---|
| Present | Positive integer | Cell is live with a TTL |
| Present | Null | Cell is live with no TTL |
| Null | Null | Never written / expired / deleted |
| Row absent | No row | No matching live row |

Observing `TTL(...) == null` alone **is not enough** to conclude data expired; you must know the fixture/write history and inspect cell values.

## 15. Application Fake `Clock` Differs from Server TTL Clock

### 15.1. Fake `Clock` Is Great for Business Rules

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
    Instant.parse("2026-11-21T10:00:00Z"),
    ZoneOffset.UTC);

Instant deadline =
    Instant.now(fixed).plus(Duration.ofDays(7));

assertEquals(
    Instant.parse("2026-11-28T10:00:00Z"),
    deadline);
~~~

`Clock.fixed` helps unit-test service logic deciding date buckets, retention deadlines, or input validation, removing dependence on the CI host's “now”.

### 15.2. A Fake `Clock` Does **Not** Fast-Forward Cassandra TTL

~~~text
Java service:
    Instant.now(injectedClock) -> mockable

Cassandra node:
    Server clock and expiration -> independent of Java mocks

Advancing injected Clock by 10 days:
    Does NOT mean 10 days passed for Cassandra TTLs.
~~~

Therefore, **never** advance `Clock` in a service expecting a `USING TTL 600` row to vanish immediately. Test server expiration using short TTLs + polling on a container/isolated cluster, and unit-test business time rules with a fake `Clock` separately.

### 15.3. Computing TTL Until an Absolute Deadline

If business rules keep data until the **start of the next UTC day**, a helper might look like:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

static long ttlSecondsUntilUtcMidnight(
        Instant now, LocalDate eventDay) {

    Instant nextMidnight = eventDay.plusDays(1)
        .atStartOfDay(ZoneOffset.UTC)
        .toInstant();

    long seconds =
        Duration.between(now, nextMidnight).getSeconds();

    return Math.max(0L, seconds);
}
~~~

**Warnings:**

- `TTL=0` has specific Cassandra semantics depending on version/table defaults; never treat it as “expire immediately”.
- If the deadline already passed, the service needs an explicit **skip write / reject / archive** branch.
- Check max TTL (in seconds) and date boundaries per server version.
- `Duration.getSeconds()` does not round up; test deadlines with under 1 second remaining.
- On retry 30 seconds later, a TTL recomputed from a fixed deadline differs from the original TTL; document this in the retention contract.

### 15.4. Late Events: Expiration “From Ingest” vs “From Event Time”

~~~text
event_time:  2026-11-10T10:00:00Z
ingested_at: 2026-11-21T10:00:00Z

Policy A: keep 7 days from ingest
Policy B: keep 7 days from event time
~~~

Under Policy A, the row remains live for days after ingest. Under Policy B, the event is already past expiry and requires a **reject/archive/skip-write** decision—never blindly set `USING TTL 0`.

Tests must cover late events, future events from source clock skew, and replayed events.

## 16. DST, Ambiguous Local Times, and `tzdb` Updates

### 16.1. One Local Time Does Not Always Map Uniquely to an `Instant`

In Daylight Saving Time zones:

- **Gap:** a local time interval skipped when clocks spring forward.
- **Overlap:** a local time interval repeated when clocks fall back.

For example, in `America/New_York` in 2026 under standard tzdb rules:

- `2026-03-08 02:30` falls in the gap.
- `2026-11-01 01:30` falls in the overlap.

### 16.2. Testing `ZoneRules.getValidOffsets`

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import org.junit.jupiter.api.Test;

class DstPolicyTest {
    private static final ZoneId NEW_YORK =
        ZoneId.of("America/New_York");

    @Test
    void detectGapAndOverlapBeforeResolvingInstant() {
        ZoneRules rules = NEW_YORK.getRules();

        LocalDateTime springGap =
            LocalDateTime.of(2026, 3, 8, 2, 30);

        LocalDateTime autumnOverlap =
            LocalDateTime.of(2026, 11, 1, 1, 30);

        assertEquals(0,
            rules.getValidOffsets(springGap).size());

        assertEquals(2,
            rules.getValidOffsets(autumnOverlap).size());
    }
}
~~~

If users send offset-less local timestamps, the service must enforce an explicit policy: reject gap/ambiguous inputs, require an offset, or apply a business-approved resolution rule.

Never assume `LocalDateTime.atZone(zone)` automatically picks the business-intended `Instant` during an overlap; it silently picks a default.

### 16.3. `tzdb` Can Change

Countries can revise DST rules in the future; the JDK bundles a timezone database per release. Tests using future dates should be reviewed upon JDK/`tzdb` upgrades—never hardcode fixed offsets for all years.

Recommendations:

- Event timestamp APIs should require ISO 8601 with `Z` or an explicit offset.
- Scheduling/booking domains should store the business **`ZoneId`**, not only a UTC offset.
- Record JDK/`tzdb` versions in compatibility test reports.
- Never let a CI host's default timezone affect partition key logic.

## 17. Clock Skew Between Replicas and CL

### 17.1. Why Node Clocks Matter

Cassandra relies on timestamps for mutations, TTLs, reconciliation, and operational tasks. Skewed node clocks make behavior near expiry unpredictable:

- Replicas may evaluate expiration slightly differently near boundaries depending on version/implementation.
- Auto-generated or client-supplied mutation timestamps may win/lose unexpectedly relative to business expectations.
- Log timelines, timeouts, and `WRITETIME` vs `event_time` comparisons become confusing.
- Reads at different CLs may expose inconsistencies.

Production requires time synchronization (NTP/chrony or organization-approved tooling), clock-offset monitoring, and skew alerts.

### 17.2. Never Shift Production Cluster Clocks to Test TTL

Tests must never:

~~~text
SSH into production Cassandra
advance clock 1 hour so TTL expires
read data
reset clock back
~~~

This disrupts the database, logs, certificates, token/replica operations, and in-flight requests. Clock-skew tests belong on an **isolated cluster with bounded fault injection, a dedicated owner, and rollback**.

### 17.3. Single-Node Testcontainers Does Not Prove Quorum

| Scenario | Is RF=1 Single-Node Enough? | What Else Is Needed |
|---|---|---|
| Java `Instant`/`LocalDate` codecs | Yes, for the tested version | Test other driver/server versions |
| UTC/VN date bucketing | Yes | Verify all writer/reader policies |
| Basic `USING TTL` and `TTL(column)` | Yes | Test table default TTL / version interactions |
| `LOCAL_QUORUM` with one replica down | **No** | RF=3 cluster with controlled node failure |
| Multi-DC quorum/placement | **No** | Multi-DC with `NetworkTopologyStrategy` |
| Hints, repair, bootstrap | **No** | Dedicated cluster integration suite |
| Cross-node clock skew | **No** | Fault injection in an isolated lab |
| Physical tombstone purging | Unsuitable for multi-second tests | Long-running storage/compaction suite |

Never take `CL=ONE` or `QUORUM` passing under RF=1 as evidence that **RF=3 `LOCAL_QUORUM`** in production will survive replica failures.

## 18. Isolation and Parallel Execution

### 18.1. Common Sources of Flakiness

- Tests A and B write to the same primary key; Test A's TTL wipes Test B's cell.
- Test A runs `TRUNCATE` while Test B is executing `SELECT`.
- Parallel CI runs contend for container disk/CPU and trigger JVM GC pauses.
- Tests rely on `ZoneId.systemDefault()` on a UTC dev machine while CI runs in another timezone.
- Test asserts `TTL(...) == 8` immediately after INSERT.
- Test starts its TTL countdown before container startup finishes.
- Test assumes `event_time` and `WRITETIME` are always identical.
- Test closes session/container while async futures are still pending.

### 18.2. Designing Isolated Tests

1. Give each case its own `device_id` and explicit timestamps.
2. Avoid shared rows or multi-week fixture data with no owner.
3. Never alter table default TTL while other tests run.
4. Keep test keyspaces clearly named with restricted write permissions.
5. Declare Java/CI timezones explicitly; apps must never depend on defaults.
6. Set TTLs long enough for “pre-expiry” assertions.
7. Use deadline-bounded polling with clear failure messages instead of fixed sleeps.
8. Run tests that alter server settings/clocks sequentially in a dedicated cluster.
9. Disable unscheduled backfill/repair jobs when benchmarking latency.
10. Close sessions and clean up only the lab environment created for tests.

### 18.3. Pre-Epoch Timestamps and Negative Conversion

~~~java
Instant historic =
    Instant.parse("1965-04-01T12:00:00Z");

assertTrue(historic.toEpochMilli() < 0);
~~~

This is a unit test. Integration tests verifying Cassandra/codecs handle pre-epoch dates must write and read `historic` on a supported server version. When converting microsecond `WRITETIME` to `Instant`, use `Math.floorDiv`/`floorMod` instead of division/remainder assuming positive values.

## 19. Retries, Concurrent Writes, TTL, and Late Data

### 19.1. A Retry Can Shift the Expiry Deadline

Suppose:

~~~text
Attempt 1: INSERT ... USING TTL 600
  Applied on server, client times out.

Attempt 2 after 30 seconds:
  Re-INSERTs same key ... USING TTL 600

Expiry deadline may shift per reconciliation/timestamps.
~~~

Hence, **primary-key idempotency** does not prove **expiry-policy idempotency**. When deadlines must be absolute, store/check `expires_at` and compute remaining TTL intentionally; evaluate `USING TIMESTAMP` and concurrent mutations before retrying.

### 19.2. Updating One Cell Does Not Reset Other Cells' TTLs

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, note
) VALUES (?, ?, ?, ?, ?);

UPDATE temporal_lab.readings_by_device_day
USING TTL 30
SET status = ?
WHERE device_id = ? AND event_day = ? AND event_time = ?;
~~~

After 30 seconds, tests must read the row back and verify `status` expired while `reading_value`/`note` stayed alive. Never assume the entire row vanished just because one column's TTL expired.

### 19.3. Combining LWT with TTL

`INSERT ... IF NOT EXISTS` uses conditional/LWT semantics; if the first attempt succeeded yet the client timed out, a retry returns `wasApplied()==false` while the row is live. Once the row expires later, the condition flips according to current state.

For business tests:

- Use a fixed operation ID and primary key.
- State preconditions clearly before writing.
- Specify CL/serial consistency appropriate for the version.
- Bound deadlines/cancellations/retries; never equate “timeout” with “rolled back”.
- Reconcile row/invariants rather than trusting only the retried LWT flag.

Do not enable LWT on every simple TTL test; it adds consensus overhead and complicates fault isolation.

## 20. Minimum Test Matrix

| ID | Scenario | Expectation | Test Layer |
|---|---|---|---|
| T01 | Write/read `Instant` with milliseconds | Exact millisecond round-trip | Integration |
| T02 | `10:30Z` vs `17:30+07:00` | Same `Instant`, single CQL row | Unit + integration |
| T03 | `17:30Z` in UTC/VN | Two distinct `LocalDate`s | Unit |
| T04 | Writer UTC day, reader VN day | Wrong partition returns 0 rows | Integration |
| T05 | Nanosecond `Instant` | Truncated/handled per ms policy | Unit + integration |
| T06 | Pre-epoch timestamp | No sign/overflow bug | Unit + integration |
| T07 | `WRITETIME(reading_value)` | Microsecond write timestamp | Integration |
| T08 | Old `event_time`, ingested today | TTL does not auto-subtract from `event_time` | Integration |
| T09 | INSERT all regular cells with TTL | Row expires as expected | Integration |
| T10 | UPDATE TTL on one cell | Row persists while other cells live | Integration |
| T11 | `TTL(column)` before expiry | Positive integer in expected range | Integration |
| T12 | Null `TTL(column)` | Distinguishes no-TTL vs expired | Integration |
| T13 | Table `default_time_to_live` | Semantics tested on dedicated table | Integration |
| T14 | Retrying TTL mutation | Does not miscalculate expiry deadline | Integration |
| T15 | DST gap/overlap | Explicit offset policy enforced | Unit |
| T16 | Non-UTC JVM timezone | Bucketing independent of `systemDefault` | Unit |
| T17 | Expired row before disk drops | Never assert immediate physical deletion | Storage/observability |
| T18 | RF=3, one replica down | Proper CL/availability | Multi-node cluster |
| T19 | Controlled clock skew | Observe divergence near expiry | Isolated cluster |
| T20 | Two tests running in parallel | No key/table contention | Integration |

## 21. Runbook A — Same `event_time`, Yet Query Finds No Row

**Scenario:** A writer inserts data at `2026-11-21T17:30:00Z`; a UTC Java service reads it, while another service in `Asia/Ho_Chi_Minh` returns `404`. Both bind `event_time` accurately.

**Step 1 — Check the actual CQL:** does the query bind `device_id`, `event_day`, and `event_time`? Are values bound as `UUID`, `LocalDate`, `Instant`, or string-concatenated?

**Step 2 — Compare bucketing policies:** did the writer use `UTC` while the reader used `ZoneId.systemDefault()`? Check timestamps near midnight boundaries.

**Step 3 — Reconcile timestamps:** safely log normalized `event_time` or authorized correlation IDs; never put raw device/tenant IDs into high-cardinality metric labels.

**Step 4 — Locate the actual partition:** in an authorized investigation environment, query both candidate `event_day` values (UTC and business zone). Never scan the whole cluster with `ALLOW FILTERING` to “find missing rows”.

**Step 5 — Centralize bucketing:** extract one shared `EventDayPolicy` used by writer, reader, and backfills; pick an explicit zone and add midnight/DST boundary tests.

**Step 6 — Migrate mis-partitioned data:** scope affected dates/partitions; build a rate-limited, checkpointed copy/backfill plan with reconciliation—never change Java code expecting old SSTables to move on their own.

**Step 7 — Verify:** read the same row from all services, inspect p99, partitions read, and not-found rates; add boundary regression tests.

### Diagnostic Example

~~~text
event_time UTC:      2026-11-21T17:30:00Z
writer event_day:    2026-11-21 (UTC)
reader event_day:    2026-11-22 (Asia/Ho_Chi_Minh)

Conclusion:
  No evidence of replica data loss.
  The two queries targeted two different partitions.
~~~

## 22. Runbook B — TTL Test Flaky or Failing in CI

**Scenario:** A test uses `USING TTL 2`, `Thread.sleep(2000)`, then asserts the row is null. It passes on a laptop, fails intermittently on slow CI, and sometimes even fails the “row still alive” check.

1. **Separate startup from TTL timing:** was the container truly ready before inserting? Did Cassandra schema agreement/prepares complete?
2. **Record controlled timings:** log client send/receive times, requested TTL, and query ID without treating client timestamps as exact server expiry.
3. **Increase test TTL reasonably:** e.g., 8–12 seconds so pre-expiry assertions remain stable; avoid testing sub-second TTLs unless explicitly required.
4. **Replace sleep with polling:** `await().atMost(...).pollInterval(...).untilAsserted(...)` stops early when satisfied and bounds wait time on failure.
5. **Inspect the right target:** partial TTL → `status==null` while the row persists; full TTL → `one()==null` when no live cells remain.
6. **Inspect server/CI clocks:** NTP offset, Docker host load, GC, network, and retries. Never shift production clocks to fix tests.
7. **Verify TTL conditions:** is `default_time_to_live` set? Did the mutation specify TTL explicitly? Did another write refresh the cell before expiry?
8. **Eliminate interference:** use unique UUIDs/keyspaces; avoid parallel tests sharing keys or running `TRUNCATE` concurrently.
9. **Conclude with evidence:** passing after a longer wait does not prove scheduling was the sole root cause; investigate abnormal p99, network, or server clocks.

**What never to do:** sprinkle `Thread.sleep(60000)` across every test to “be safe” and hide timestamp/TTL conflicts.

## 23. Runbook C — Data Expired by TTL, Yet Disk Usage Did Not Drop

**Scenario:** `SELECT` no longer returns old data, yet disk utilization remains high and SSTable sizes do not shrink immediately. Operations suspects TTL “stopped working”.

1. **Distinguish logical expiry from physical purge:** are rows/cells still live on read? Does `TTL(column)` still count down or has it expired?
2. **Inspect table-level metrics:** `nodetool tablestats`, tombstone/read latencies, SSTable count, and free disk space.
3. **Inspect compaction:** `nodetool compactionstats`, backlogs, I/O headroom, and compaction strategy.
4. **Review retention settings:** `default_time_to_live`, mutation TTLs, `gc_grace_seconds`, repair/replica outages, and zombie-data risks.
5. **Never trigger major compaction/repair blindly:** these consume heavy disk/CPU/I/O and require SOPs, capacity, and rollback plans.
6. **Verify capacity trends:** track read liveness, compaction progress, and disk usage over time rather than judging from one instant counter.
7. **If disk pressure is urgent:** follow approved capacity/cleanup procedures; never lower `gc_grace_seconds` recklessly to force purges and risk data resurrection.

**TTL reduces live data**, not guaranteed immediate byte reclamation. In Cassandra, tombstones and compaction are part of distributed safety.

## 24. Runbook D — Timestamp Off by One Day or “Duplicate” Records Appearing

**Scenario:** One collector sets `event_day` by local date while another uses UTC. Two rows with the same `event_time` may land in two partitions, or multiple events in the same millisecond overwrite each other.

1. **Verify units:** were seconds, milliseconds, and microseconds confused during conversion?
2. **Verify offsets:** did inputs include `Z` or `+0700`? Was a zone-less `LocalDateTime` interpreted implicitly?
3. **Verify precision:** event sources may emit nanoseconds while Cassandra `timestamp` holds milliseconds; multiple events in the same ms collide on the full primary key.
4. **Verify key modeling:** if multiple real events occur within one millisecond, is an `event_id` or extra clustering column needed to disambiguate them?
5. **Verify writer timestamps:** did clients pass `USING TIMESTAMP`? `WRITETIME` differing from `event_time` is normal.
6. **Plan migration carefully:** never arbitrarily duplicate rows across partitions; define source of truth, deduplication logic, backfills, and consistency.
7. **Add tests:** UTC midnight boundaries, DST transitions, pre-epoch dates, and same-millisecond events.
8. **Re-measure:** valid daily row counts, data skew, driver timeouts, and compaction load from backfilling.

If business logic must store multiple events per millisecond, **key `(device_id, event_day, event_time)` is insufficient**. No test can fix a schema uniqueness flaw.

## 25. Observability Tools for Timestamps and TTL

### 25.1. Read-Only Status Commands

~~~bash
# RF/DC/rack and node up/down status.
nodetool status

# Pending/Active/Dropped across executors.
nodetool tpstats

# Compaction backlog and progress.
nodetool compactionstats

# Table/storage stats per version.
nodetool tablestats temporal_lab.readings_by_device_day

# Per-table histograms where supported by version.
nodetool tablehistograms temporal_lab readings_by_device_day

# Streaming during bootstrap/repair/rebuild.
nodetool netstats
~~~

`nodetool` syntax/output varies by Cassandra version; check `nodetool help`. `netstats` primarily tracks SSTable streaming and **does not** prove native CQL traffic is zero. `status` showing `UN` does not guarantee healthy replica latency or clock sync.

### 25.2. Application Metrics to Collect

| Layer | Metrics | Purpose |
|---|---|---|
| Java application | Query ID, operation, p95/p99, timeouts | Query bugs vs infrastructure issues |
| Timestamp ingest | Late/future event counts, daily buckets by policy | Detect source clock or bucketing drift |
| TTL writes | TTL mutation counts, policy ID, TTL buckets | Spot abnormal retention configs |
| TTL reads | Cells with/without TTL, expected vs observed expiry | Track logical behavior |
| Cassandra | Tombstone warnings, SSTables/read, pending compaction | Read/purge cost |
| Storage | Free disk, IOPS/latency, GC, and CPU | Serving/purging headroom |
| Clock | Per-node NTP/chrony offset, JVM/server time | Detect skew near deadlines |
| Test CI | Duration, flakes, container startup, retry counts | Test infra vs product logic |

Never put raw `device_id`/`tenant_id`, individual event timestamps, or per-partition tokens into **metric labels**: cardinality will explode. Use bounded query-template IDs and policy versions.

### 25.3. Illustrative Log Schema

~~~text
event=temporal_integration_failure
test_case=T10_partial_cell_expiry
query_template=read_device_day_by_timestamp
expected=partial_cell_expired
observed=row_exists_status_non_null
ttl_requested_seconds=12
elapsed_since_ack_ms=15320
server_clock_skew_ms=unknown
cassandra_release=4.1.x
driver_release=4.x
~~~

**This is a recommended log format**, not default Cassandra output. Log `unknown` if server clock skew has not been measured rather than guessing from client elapsed time. Logs must obey retention/access policies and never leak sensitive device values.

## 26. Common Misconceptions

| Claim | Accurate Understanding |
|---|---|
| “CQL `timestamp` stores the user's timezone.” | `timestamp` stores an instant; it does not retain a business zone ID |
| “`LocalDate` is always UTC midnight.” | It is a timezone-less calendar date |
| “UTC+7 and UTC share the same `event_day`.” | One `Instant` can map to two different calendar dates |
| “Binding `Instant` makes Cassandra auto-compute `event_day`.” | The application must write the `event_day` partition key explicitly |
| “`LocalDateTime` converts to `Instant` without a zone.” | Needs an offset/`ZoneId` and a DST policy |
| “Cassandra `timestamp` stores nanoseconds like `Instant`.” | CQL `timestamp` normally has millisecond precision |
| “`WRITETIME` means `event_time`.” | `WRITETIME` is the mutation/cell timestamp, usually in microseconds |
| “`WRITETIME` is in epoch milliseconds.” | Normally in microseconds |
| “TTL is calculated as `now - event_time`.” | TTL follows mutation/expiration semantics, never reading `event_time` automatically |
| “`TTL=0` always means delete immediately.” | Depends on version/default-TTL semantics; never use blindly |
| “Right after `USING TTL 8`, `TTL(column)` must be 8.” | Time passes between write and read; check a range |
| “When `status` TTL expires, the whole row vanishes.” | Other non-TTL columns keep the row alive |
| “Null `TTL(column)` definitely means expired.” | Could mean no TTL was set or the cell was never written |
| “Once `SELECT` stops returning rows, disk frees up immediately.” | Physical purging waits on compaction and tombstone rules |
| “`Thread.sleep(TTL)` is reliable enough.” | Prone to flakiness; deadline-bounded polling is better |
| “Mocking Java `Clock` makes Cassandra expire immediately.” | Server clocks are independent |
| “Single-node test proves RF3 `LOCAL_QUORUM`.” | Requires multi-node fault tests |
| “Clock skew only messes up logs.” | Can affect write ordering, TTLs, and consistency |
| “Paging gives a point-in-time snapshot.” | Pages may be read at different moments |
| “Adding retries fixes flaky TTL tests.” | Retries can refresh TTLs or submit new mutations |
| “Timezones differ only by fixed offsets.” | DST/`tzdb` rules change |
| “Fixing old UTC dates only needs `ALTER TABLE`.” | Changing partition keys requires backfill/reconciliation |
| “Two events in 1 ms always get two separate rows.” | Identical full primary keys overwrite each other |
| “Empty `nodetool netstats` means CQL is idle.” | `netstats` tracks SSTable streaming, not normal CQL |

## 27. Questions and Answers

### Q1 — Event Timestamp and Date Bucket

An event has `event_time = 2026-11-21T17:30:00Z`. What are the UTC and `Asia/Ho_Chi_Minh` dates?

**Answer:** UTC: `2026-11-21`; HCM (+07): `2026-11-22`. If the partition key includes `event_day`, they point to two different partitions.

### Q2 — `Instant` with Offsets

Do `2026-11-21T10:30:00Z` and `2026-11-21T17:30:00+07:00` represent the same `Instant`?

**Answer:** Yes. Different local/offset strings, identical absolute instant.

### Q3 — `LocalDate`

Does CQL `date` store a timezone or hours/minutes?

**Answer:** No. It stores a calendar date; the app must specify a timezone when deriving a date from an `Instant`.

### Q4 — Milliseconds

Java writes `2026-11-21T10:30:00.123456789Z` to a CQL `timestamp`. Can you assert exact nanoseconds after round-trip?

**Answer:** No. CQL `timestamp` normally has millisecond precision; enforce a truncation/rounding policy and millisecond fixtures.

### Q5 — `WRITETIME`

`WRITETIME(reading_value)` returns 16 digits while `event_time` is an `Instant`. Should they always match?

**Answer:** No. `WRITETIME` is a microsecond mutation timestamp for reconciliation; `event_time` is business data. Both units and semantics differ.

### Q6 — TTL on Historical Events

An event occurred a month ago but is `INSERT`ed today with `USING TTL 60`. Will it expire immediately because `event_time` is old?

**Answer:** No. Standard TTL counts from mutation application per server rules, not from the `event_time` column.

### Q7 — `TTL(column)` Returns Null

`TTL(status) == null`. Is `status` guaranteed to have just expired?

**Answer:** No. The cell might have no TTL, never been written, been deleted, or expired. Read the value and check fixture/write history.

### Q8 — Partial TTL

A row has `reading_value` with no TTL and `status` with an 8-second TTL. After 10 seconds, will `Row` definitely be null?

**Answer:** No. The row persists because `reading_value` is still live, while `status` reads as null.

### Q9 — Full TTL

You `INSERT` a row where every live value has a TTL. Once the TTL expires and no live cells remain, what does querying by full PK return?

**Answer:** It returns no live row; however, that does not mean the SSTable was physically deleted right away.

### Q10 — Polling

Why does `Thread.sleep(3000)` with a 3-second TTL flake?

**Answer:** Server/client clock boundaries, network latency, scheduling, and start time never align perfectly. Use deadline-bounded polling with adequate margin.

### Q11 — Fake `Clock`

Does advancing `Clock.fixed` in Java by one day expire a 600-second Cassandra TTL immediately?

**Answer:** No. Server clocks/expiration are independent of injected Java `Clock`s.

### Q12 — DST Gap

Can `America/New_York` at `2026-03-08 02:30` map to a valid `Instant`?

**Answer:** That local time falls inside a DST gap under standard tzdb rules; enforce a policy for nonexistent local times or require explicit offsets.

### Q13 — DST Overlap

What is the issue with `America/New_York` at `2026-11-01 01:30`?

**Answer:** It maps to two possible UTC offsets/`Instant`s. Record the offset explicitly instead of silently picking a default if accuracy matters.

### Q14 — Testcontainers RF=1

A TTL test passes on a single-node RF=1 Cassandra container. Does that prove RF=3 behavior with a down replica and `LOCAL_QUORUM`?

**Answer:** No. You need a multi-node/topology integration suite covering those failure scenarios.

### Q15 — Disk Space

After expiration, `SELECT` returns no data, yet free disk space does not rise. Does that prove TTL failed?

**Answer:** No. Logical expiry differs from physical purge; compaction, tombstones, and safety conditions govern byte reclamation.

### Q16 — TTL Retries

An `INSERT` with TTL 600 is retried 30 seconds later. Is the expiry deadline guaranteed to stay unchanged?

**Answer:** No. A retry can apply a new mutation/timestamp/TTL per semantics; use an operation ID and absolute retention policy if required.

### Q17 — Same Millisecond

Two events have `Instant`s 100 nanoseconds apart within the same millisecond, same device/day. If `event_time` is the sole clustering key, can one overwrite the other?

**Answer:** Yes. CQL `timestamp` has millisecond precision; if both map to the same full key, they mutate the same row—add `event_id` or redesign the key.

### Q18 — Clock Skew

Should you advance a production replica's clock into the future to test TTLs faster?

**Answer:** Never. Use an isolated cluster and safe fault injection; production clocks are foundational infrastructure for distributed correctness.

### Q19 — Wrong Partition

A query with the right `event_time` but wrong `event_day` returns 0 rows. Can we conclude all replicas lost the data?

**Answer:** No. The query hit a different partition/token. Check bucketing policies and key values first.

### Q20 — Retention Policy

Business requires expiration 7 days after `event_time`; server TTL starts at ingest. What should you do?

**Answer:** Define `expires_at`/policy, compute remaining TTL at ingest, handle already-expired events, and test late arrivals/retries—never assume ingest-time `TTL=7 days` is equivalent.

## 28. Pre-Merge Integration Test Checklist

### 28.1. Time Types and Timezones

~~~text
[ ] CQL timestamp <-> Java Instant verified at millisecond precision.
[ ] CQL date <-> Java LocalDate, no implicit timezone attached.
[ ] event_day bucketing shares one ZoneId policy across writer/reader.
[ ] Tested around UTC midnight and business timezone boundaries.
[ ] Tested explicit offsets in inputs and Instant round-trips.
[ ] Tested DST gap/overlap when business uses DST zones.
[ ] Independent of CI host ZoneId.systemDefault.
[ ] Distinguished event_time from microsecond WRITETIME.
[ ] Tested multiple events within the same millisecond if possible.
~~~

### 28.2. TTL/Expiration

~~~text
[ ] TTL specified in seconds, never confused with milliseconds.
[ ] Tested both pre-expiry and post-expiry states.
[ ] Used Awaitility polling/deadlines, avoiding exact-boundary sleeps.
[ ] Tested per-cell TTL and full-row TTL separately.
[ ] Null TTL(column) not assumed to guarantee expiration.
[ ] Table default TTL tested on an isolated table if used.
[ ] Fake Clock used only for Java domain logic, never as server time.
[ ] Tested late events and absolute expiry policies where applicable.
[ ] Retries/TTL/LWT evaluated alongside operation identity.
[ ] Never asserted immediate physical disk deletion upon expiry.
[ ] Never forced compaction/repair/clock shifts on production.
~~~

### 28.3. Cassandra/Java/CI

~~~text
[ ] Testcontainers, Java Driver, JDK, and Cassandra versions pinned.
[ ] Docker runtime ready; tests fail loudly rather than faking skips when missing.
[ ] Session closed per lifecycle; each test generates its own UUID.
[ ] Single-node CL/RF explicitly documented as scope-limited.
[ ] Multi-node replication/time-skew tests placed in dedicated suites.
[ ] No shared-table TRUNCATE/ALTER during parallel execution.
[ ] Metrics track timeouts, p99, compaction, disk, and clock offset.
[ ] Logs contain no PII, raw partition IDs, or secrets.
[ ] Runbooks exist for wrong buckets, TTL flakes, physical purge, and precision.
[ ] Content QA STEP 6 not run during authoring step.
~~~

## 29. Summary

To accurately test **timezones, timestamps, TTL, and expired data** in Java–Cassandra:

1. **Use `Instant` for CQL `timestamp`** and `LocalDate` for CQL `date`; never treat a zone-less `LocalDateTime` as an absolute instant.
2. **Standardize the timezone for daily partition buckets**; one `Instant` can map to different UTC and local dates, routing to different tokens/replicas.
3. **CQL `timestamp` has millisecond precision**, while cell `WRITETIME` uses microseconds; the two serve completely different purposes.
4. **TTL is a cell/row-liveness expiration policy**, never auto-computed from `event_time` and never synonymous with instant SSTable deletion.
5. **`TTL(column)` is not sole proof** distinguishing no-TTL, unwritten, and expired cells.
6. **Test expiration with polling and deadlines**, asserting both pre- and post-expiry; avoid fixed sleeps equal to TTL and parallel tests sharing keys.
7. **Mocking Java `Clock` does not mock Cassandra server clocks**; unit-test business time rules and integration-test real expiration on isolated clusters.
8. **Test DST, timestamp precision, late events, retries, and multi-cell mutations** whenever workloads are time-sensitive.
9. **Single-node Testcontainers cannot prove RF3/quorum/clock-skew**; distributed correctness requires controlled multi-node environments.
10. **Track logical expiry and physical purge separately**, tying storage observations to compaction/tombstones, RF/CL, disk headroom, and replica sync.

The most important question for any temporal integration test is not “how many seconds should I sleep before asserting?”, but **“Which instant am I measuring, which timezone computes the partition date, which cell and clock govern the TTL, and is my assertion checking live visibility or post-compaction disk bytes?”**. Only when all four are explicitly modeled and verified will your tests catch real bugs instead of flaking in CI.
