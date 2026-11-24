# Timestamps, Offsets, Timezones, and Precision When Reading and Writing in Spring JDBC

## 1. Why Is Storing Time Harder Than Storing a Number?

A single instant in time can be displayed using many different local times. For instance, these two strings refer to **the exact same instant**:

```text
2026-10-30T10:15:30.123456+07:00
2026-10-30T03:15:30.123456Z
```

The 7-hour difference in the displayed hour is compensated by the `+07:00` offset relative to UTC (`Z`). However, the string `2026-10-30 10:15:30` contains no offset, timezone, or seasonal clock-change rules, so **it is insufficient to deduce a unique point on the UTC timeline**.

In Spring JDBC applications, time bugs often surface as data passes through multiple layers:

```text
Client sends ISO-8601
    ↓ parse
Java Instant / OffsetDateTime / LocalDateTime / ZonedDateTime
    ↓ PreparedStatement.setObject(...)
JDBC driver and connection/session timezone
    ↓
SQL TIMESTAMP / TIMESTAMP WITH TIME ZONE / DATETIME ...
    ↓
JDBC driver and conversion during SELECT
    ↓ ResultSet.getObject(..., Class)
Java temporal type
    ↓ format with user's ZoneId
JSON / UI / reports
```

Each layer can alter how offsets, timezones, or fractional seconds are interpreted. To read and write correctly, first identify the **business meaning of the temporal data**:

- **Instant that occurred:** when an order was created, when a transaction was recorded, when a token expires. Needs an anchor comparable on UTC.
- **Wall-clock time:** store opens at 09:00, schedule starts at 08:30 at a venue. May need `LocalTime` / `LocalDateTime` plus `ZoneId`.
- **Instant with a specific offset:** an event submitted with `2026-10-30T10:15:30+07:00`; distinguish the absolute value from the offset reported by the source.
- **Schedule in a geographical timezone:** an appointment at 09:00 in `Europe/Berlin` months in the future; needs timezone rules, including potential Daylight Saving Time changes.

This lesson focuses on **mapping timestamp, offset, and timezone types when reading/writing via Spring JDBC**, along with **fractional-second precision**.

## 2. Choosing the Right Type in Java 17+

Standard classes in package `java.time` carry distinct meanings:

| Java Type | Information Retained | Best Suited For | Does Not Contain |
| --- | --- | --- | --- |
| `Instant` | Absolute point on the UTC timeline | Event timestamps, audit, expiration | Local time and `ZoneId` |
| `LocalDateTime` | Date + wall-clock time | Local schedules, zone-less SQL timestamps | Offset, `ZoneId`, instant |
| `OffsetDateTime` | Date + time + fixed offset like `+07:00` | ISO-8601 exchange with offset, supported JDBC `TIMESTAMP WITH TIME ZONE` | Geographical timezone rules |
| `ZonedDateTime` | Date + time + `ZoneId`, with offset per rules at that moment | Display, advance scheduling, DST handling | No guarantee JDBC will persist `ZoneId` name |
| `LocalDate` | Date without time | Birthdays, accounting dates | Time and timezone |
| `LocalTime` | Time without date | Daily opening hours | Date and timezone |
| `java.sql.Timestamp` | Legacy JDBC timestamp value, holds nanos without `ZoneId` | Legacy JDBC API compatibility | Explicit timezone semantics |

Java 17 example:

```java
import java.time.*;

Instant instant = Instant.parse("2026-10-30T03:15:30.123456Z");
OffsetDateTime withOffset =
        instant.atOffset(ZoneOffset.ofHours(7));
ZonedDateTime inVietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime wallClock = inVietnam.toLocalDateTime();

System.out.println(withOffset);
System.out.println(inVietnam);
System.out.println(wallClock);
```

The snippet above is an **illustrative example inside a Java method/class**, not a standalone file. `Instant` is the underlying point in time. `atOffset(...)` and `atZone(...)` merely choose how to express that instant; `toLocalDateTime()` **discards timezone/offset info**, so it cannot automatically reverse back to `Instant` without supplying the right zone or offset.

Do not call `LocalDateTime.now()` and arbitrarily attach `ZoneOffset.UTC` as if it were a UTC timestamp: `LocalDateTime.now()` reads the clock in the JVM's default timezone. For the current instant, use `Instant.now()` or an explicitly configured `Clock`.

### Offset Differs from Timezone

`ZoneOffset.ofHours(7)` is a **fixed** UTC offset. `ZoneId.of("Asia/Ho_Chi_Minh")` is a timezone identifier from the IANA rules database. A zone can have different offsets depending on historical points or legal changes; a single offset does not describe all those rules.

`ZonedDateTime` is the natural choice when business logic needs "09:00 local time at a location", especially for future schedules. `OffsetDateTime` is useful when data already carries an offset, but **an offset does not identify a city or DST rules**.

## 3. SQL Types Do Not Carry the Same Meaning Across Every DBMS

### TIMESTAMP WITHOUT TIME ZONE

In PostgreSQL and H2, `TIMESTAMP` / `TIMESTAMP WITHOUT TIME ZONE` stores **local date and time**, with no offset or IANA zone. The typical Java counterpart is `LocalDateTime`:

```sql
-- PostgreSQL/H2:
meeting_local TIMESTAMP(6) WITHOUT TIME ZONE
```

The value `2026-10-30 10:15:30` is merely wall-clock time. It cannot become an `Instant` without knowing which timezone it belongs to and how nonexistent or duplicated DST hours are handled.

In PostgreSQL, if you cast a string literal containing `+07:00` to `timestamp without time zone`, PostgreSQL **may ignore the offset indicator** because the column/literal type is explicitly zone-less. Do not pass offset strings to this column and assume the offset will be preserved.

### TIMESTAMP WITH TIME ZONE

This SQL name **does not guarantee the database stores `Asia/Ho_Chi_Minh` or the original offset**. Behavior varies by DBMS:

- **PostgreSQL `TIMESTAMPTZ`:** stores a point in time (normalized to UTC); **does not retain the original offset or zone**. When displayed via SQL, the system converts using the session timezone setting. PostgreSQL JDBC typically reads it as an `OffsetDateTime` with offset `Z`, even if you wrote `+07:00`.
- **H2 `TIMESTAMP WITH TIME ZONE`:** represents both date-time and offset and supports `OffsetDateTime` mapping; the data still does not automatically retain an IANA geographical zone ID.
- **SQL Server `datetimeoffset`:** a dedicated type storing date/time and offset info; not a zone name like `Europe/Berlin`.
- **MySQL:** `TIMESTAMP` converts between session timezone and UTC, whereas `DATETIME` does not perform the same session timezone conversion. Do not infer that `TIMESTAMP` in MySQL matches PostgreSQL/H2 `TIMESTAMP WITHOUT TIME ZONE`.

One way to document this in schema docs:

| DBMS | Type | Meaning to Remember | Commonly Used Java Type |
| --- | --- | --- | --- |
| PostgreSQL | `timestamp(6) without time zone` | Local date/time value, no offset | `LocalDateTime` |
| PostgreSQL | `timestamptz(6)` | UTC instant; original offset not retained | `OffsetDateTime` via pgJDBC, then can call `toInstant()` |
| H2 | `timestamp(6)` | Local date/time | `LocalDateTime` |
| H2 | `timestamp(6) with time zone` | Date/time with offset | `OffsetDateTime` |
| MySQL | `datetime(6)` | Local-style date/time value, no automatic session timezone conversion | Use appropriate driver mapping, usually `LocalDateTime` |
| MySQL | `timestamp(6)` | Converted per session timezone; does not store zone ID | Inspect driver/session/connection when mapping |

**Practical conclusion:** before picking a Java type, know the database, schema, JDBC driver, and business semantics. The same SQL name `TIMESTAMP` can yield different results across DBs.

## 4. JDBC 4.2 Mapping in Spring JdbcTemplate

Spring `JdbcTemplate` facilitates JDBC statements. It **does not replace** the driver's date/time conversion mechanism; Spring manages connections, statements, mapping callbacks, and `SQLException` translation. With JDBC 4.2+, the clearest approach is:

**Write:** use `PreparedStatement.setObject(index, value)` with a `java.time` type supported by the driver.

**Read:** use `ResultSet.getObject(columnLabel, JavaType.class)` inside `RowMapper`. Drivers may reject unsupported conversions; integration testing on a real DB is required.

Example repository method snippet (assuming `JdbcTemplate jdbc` exists):

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

void save(JdbcTemplate jdbc,
          LocalDateTime localStart,
          OffsetDateTime happenedAt) {
    jdbc.update(
        "INSERT INTO event_times (event_key, local_start, happened_at) " +
        "VALUES (?, ?, ?)",
        ps -> {
            ps.setString(1, "event-001");
            ps.setObject(2, localStart);
            ps.setObject(3, happenedAt);
        }
    );
}
```

This snippet is **not a standalone program**; the `event_times` table and reading logic are built in the full example later. The key point is that `setObject(2, LocalDateTime)` targets a zone-less column, while `setObject(3, OffsetDateTime)` targets a timezone-aware column. This keeps the data's intent explicit.

Reading with an explicit type:

```java
LocalDateTime local = rs.getObject("local_start", LocalDateTime.class);
OffsetDateTime withOffset =
        rs.getObject("happened_at", OffsetDateTime.class);
Instant happenedInstant = withOffset.toInstant();
```

This is an **excerpt inside a `RowMapper`**, where `rs` is the current row's `ResultSet`. Do not coerce `LocalDateTime` to `Instant` using an accidental machine default timezone.

If the driver requires a specific SQL type, you can pass the target type explicitly:

```java
import java.sql.Types;

// Inside PreparedStatementSetter:
ps.setObject(2, localStart, Types.TIMESTAMP);
ps.setObject(3, happenedAt, Types.TIMESTAMP_WITH_TIMEZONE);
```

This is also an **illustrative snippet**, not a standalone Java file. Some drivers have limitations regarding `Types.TIMESTAMP_WITH_TIMEZONE` or `OffsetDateTime` conversion; overload choices must be tested on the real driver. For `null` values, you can use `ps.setNull(index, Types.TIMESTAMP)` or `Types.TIMESTAMP_WITH_TIMEZONE` matching the column type; not every driver infers the SQL type accurately from `setObject(index, null)`.

## 5. Runnable Spring JDBC Example: Reading/Writing and Verifying Round-Trip

This example uses Java 17+, Spring Boot 3.5.7, JDBC, and H2. H2 is chosen because it supports `TIMESTAMP(6) WITH TIME ZONE` and `OffsetDateTime`. The example demonstrates that **the LocalDateTime value**, **instant**, and **6 fractional digits of seconds** are preserved when written to the DB and read back.

Structure:

```text
timestamp-jdbc-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/timestamp/
    │   └── TimestampJdbcApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>timestamp-jdbc-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE event_times (
    event_key VARCHAR(40) PRIMARY KEY,
    local_start TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL,
    happened_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

**`src/main/resources/application.properties`:**

```properties
spring.datasource.url=jdbc:h2:mem:timestamp_jdbc_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.banner-mode=off
logging.level.root=ERROR
```

**`src/main/java/com/example/timestamp/TimestampJdbcApplication.java`:**

```java
package com.example.timestamp;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TimestampJdbcApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimestampJdbcApplication.class, args);
    }

    private record TimeRow(
            LocalDateTime localStart,
            OffsetDateTime happenedAt) {}

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            LocalDateTime inputLocal =
                    LocalDateTime.of(2026, 10, 30, 9, 15, 30, 123_456_000);
            OffsetDateTime inputOffset =
                    OffsetDateTime.of(
                            2026, 10, 30, 10, 15, 30, 123_456_000,
                            ZoneOffset.ofHours(7));

            int inserted = jdbc.update(
                    "INSERT INTO event_times " +
                    "(event_key, local_start, happened_at) VALUES (?, ?, ?)",
                    ps -> {
                        ps.setString(1, "event-001");
                        ps.setObject(2, inputLocal);
                        ps.setObject(3, inputOffset);
                    });

            TimeRow actual = jdbc.queryForObject(
                    "SELECT local_start, happened_at " +
                    "FROM event_times WHERE event_key = ?",
                    (rs, rowNum) -> new TimeRow(
                            rs.getObject("local_start", LocalDateTime.class),
                            rs.getObject("happened_at", OffsetDateTime.class)),
                    "event-001");

            if (actual == null) {
                throw new IllegalStateException("No row returned");
            }

            Instant storedInstant = actual.happenedAt().toInstant();

            System.out.println("Rows inserted: " + inserted);
            System.out.println("Local time intact: " +
                    inputLocal.equals(actual.localStart()));
            System.out.println("Instant intact: " +
                    inputOffset.toInstant().equals(storedInstant));
            System.out.println("Six-digit fraction intact: " +
                    (actual.localStart().getNano() == 123_456_000 &&
                     actual.happenedAt().getNano() == 123_456_000));
        };
    }
}
```

Requires JDK 17+ and Maven; stand in the `timestamp-jdbc-demo` directory and run:

```bash
mvn -q spring-boot:run
```

**Four lines printed by the program** in a fresh H2 setup with an empty table:

```text
Rows inserted: 1
Local time intact: true
Instant intact: true
Six-digit fraction intact: true
```

Output messages from Maven or the runtime may depend on the environment. The nanosecond values intentionally end in `000` to match the SQL column with **6 fractional digits of seconds** (microseconds) exactly.

Takeaways from the example:

1. Column `local_start` has type `TIMESTAMP(6) WITHOUT TIME ZONE`. On read, it matches the `LocalDateTime` written, **with nothing from which to infer a UTC instant**.
2. Column `happened_at` has type `TIMESTAMP(6) WITH TIME ZONE`. Spring JDBC passes `OffsetDateTime` through the driver, then reads it back. Comparing `toInstant()` checks **the exact instant** rather than assuming the offset representation must match the input string.
3. `123_456_000` nanoseconds equals `.123456` seconds. Because the column has precision 6, the value is expected to be preserved intact on H2.
4. When replacing H2 with PostgreSQL, the returned type and offset may differ; PostgreSQL JDBC usually returns `OffsetDateTime` in UTC. Check the instant, do not assert that `+07:00` offset is stored.
5. Do not use `java.sql.Timestamp` to implicitly infer timezones; the example chooses `java.time` APIs with explicit semantics.

**Verification boundary:** the sample project is designed for Spring Boot 3.5.7/H2 and JDBC 4.2 APIs, but JDBC results must be run against the actual target environment/driver when applied; do not treat H2 as a substitute for testing PostgreSQL, MySQL, or SQL Server.

## 6. When to Use Instant vs. LocalDateTime + ZoneId?

### Case A: Event / Audit Timestamps

Store "at what instant did payment occur" as an instant. In the service:

```java
import java.time.*;

Instant createdAt = Instant.parse("2026-10-30T03:15:30.123456Z");

// If the driver needs OffsetDateTime for TIMESTAMP WITH TIME ZONE:
OffsetDateTime forJdbc = createdAt.atOffset(ZoneOffset.UTC);
```

`Instant` is the business contract. `OffsetDateTime` in UTC is **the transport type for JDBC**, without losing the instant. With PostgreSQL `timestamptz`, this is far more appropriate than storing a local timestamp and guessing the timezone on read.

When displaying:

```java
ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime viewerTime = createdAt.atZone(viewerZone);
// 2026-10-30T10:15:30.123456+07:00[Asia/Ho_Chi_Minh]
```

This is an illustrative Java snippet inside a method. The `ZoneId` name does not have to reside in the timestamp column; it can come from the viewer's profile, organization settings, or other business metadata.

### Case B: Appointments at 09:00 at a Venue

Suppose a booking service always occurs at 09:00 in `Europe/Berlin`, even across summer/winter offset changes:

```java
LocalDateTime scheduledLocal =
        LocalDateTime.of(2026, 11, 10, 9, 0);
ZoneId venueZone = ZoneId.of("Europe/Berlin");
Instant scheduledInstant =
        scheduledLocal.atZone(venueZone).toInstant();
```

If you store only `Instant`, you know the specific point in time computed **under current timezone rules**; if the business requires repeating at 09:00 daily or recomputing when timezone laws change, keep **the local time and IANA `ZoneId`**. A sensible design may include `scheduled_local TIMESTAMP`, `zone_id VARCHAR`, and a computed UTC instant for a specific execution. Do not equate `ZoneId` with the current offset.

### DST: Nonexistent and Repeated Hours

Regions with Daylight Saving Time transitions can experience:

- **Gap:** clocks jump forward over an interval, e.g., 02:30 does not exist on a spring-forward transition day.
- **Overlap:** clocks turn back; 02:30 occurs **twice**, corresponding to two offsets and two instants.

Java lets you check:

```java
import java.time.*;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);

if (offsets.size() == 0) {
    throw new IllegalArgumentException("Local time falls in DST gap");
}
if (offsets.size() == 2) {
    throw new IllegalArgumentException(
            "Ambiguous local time; choose an explicit offset");
}
Instant resolved = local.toInstant(offsets.get(0));
```

This is an **illustrative snippet**, not a standalone program. Under current IANA rules for `Europe/Berlin`, 02:30 on October 25, 2026 is an overlap hour (two valid offsets), so the example throws an exception before reaching `resolved`. In practice, a scheduling system needs an explicit policy for gaps/overlaps; avoid silently auto-shifting times. IANA timezone data can also update as laws change.

## 7. Comparing Instants: equals Differs from isEqual

The two `OffsetDateTime` values below refer to the same instant while carrying two different offsets:

```java
import java.time.OffsetDateTime;

OffsetDateTime vietnam =
        OffsetDateTime.parse("2026-10-30T10:00:00+07:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2026-10-30T03:00:00Z");

System.out.println(vietnam.equals(utc));
System.out.println(vietnam.isEqual(utc));
System.out.println(vietnam.toInstant().equals(utc.toInstant()));
```

Output of the **three println calls**:

```text
false
true
true
```

`equals` checks both the local date-time and the offset; `isEqual` and comparing `toInstant()` focus on the instant. When testing round-trips through PostgreSQL `timestamptz`, do not assert `OffsetDateTime.equals` if the database/driver normalizes offsets to UTC. Compare `toInstant()`, and when necessary check tolerance within the allowed precision.

For `LocalDateTime`, `equals` only compares the date/time fields; it does not prove two records occurred at the same instant without a zone.

## 8. Precision: 3, 6, or 9 Digits After the Decimal Point?

Java's `Instant`, `LocalDateTime`, and `OffsetDateTime` can represent fractional seconds down to **nanoseconds (9 digits)**. However, the resolution of **the source value** (OS clock, database, or API) and the precision **stored by the database** are two different things.

| SQL Precision | Declared Smallest Unit | Fractional Second Example |
| --- | --- | --- |
| `TIMESTAMP(0)` | Seconds | `.0` |
| `TIMESTAMP(3)` | Milliseconds = 10^-3 s | `.123` |
| `TIMESTAMP(6)` | Microseconds = 10^-6 s | `.123456` |
| `TIMESTAMP(9)` | Nanoseconds = 10^-9 s, **only if DB supports it** | `.123456789` |

Example:

```java
import java.time.Instant;

Instant value =
        Instant.parse("2026-10-30T03:15:30.123456789Z");

int nanos = value.getNano();  // 123456789
long epochMillis = value.toEpochMilli(); // Resolution only to milliseconds
```

Illustrative code snippet inside a method. `toEpochMilli()` **loses microseconds/nanoseconds** if you store only the returned `long`; `Instant.getNano()` preserves all 9 digits from the original data. `java.sql.Timestamp.getTime()` also returns epoch milliseconds, while `Timestamp.getNanos()` holds the nanos separately; do not treat `getTime()` as a full-precision copy.

**Precision loss example:** `.123456789` written to a `TIMESTAMP(6)` column must be adjusted to at most 6 digits. The database may round or truncate the excess depending on engine/settings. H2 is documented to round `half up` when casting to lower precision; PostgreSQL supports up to microseconds. Never assume PostgreSQL, H2, and MySQL all truncate under a single uniform rule.

### Sensible Ways to Test Precision

- If the schema has precision 6 and the app wants exact equality checks, use inputs whose nanos are divisible by 1000 (such as `123456000` in the example).
- If data has more than 6 digits, measure the delta from the written value and check the database's rounding policy instead of asserting nanosecond equality.
- If a stable event order is needed, **do not rely solely on rounded timestamps**. Multiple events can share the same timestamp; add an ID/sequence or logical ordering.
- When measuring execution duration, use `System.nanoTime()` for elapsed intervals within the same process; do not use database timestamps or `LocalDateTime.now()` for nanosecond benchmarking.
- `Instant.now()` returns an `Instant` capable of storing nanos, **which does not mean the system clock always supplies nanosecond resolution**.

### Behavior of Common Databases

- **PostgreSQL:** `timestamp(p)`/`timestamptz(p)` allows `p` from 0 to 6; actual resolution is microseconds. If an application demands intact nanoseconds, this column alone does not hold enough information.
- **MySQL 8.x:** `DATETIME(fsp)`/`TIMESTAMP(fsp)` supports fractional seconds up to `fsp = 6`; if precision is omitted, check the default schema/engine behavior (many columns default to storing no fractional seconds). Also verify session timezone for `TIMESTAMP`.
- **H2:** `TIMESTAMP(p)`/`TIMESTAMP(p) WITH TIME ZONE` supports `p` up to 9; default 6. Because H2 can keep 9 digits while PostgreSQL keeps only 6, **tests on H2 do not replace precision tests on PostgreSQL**.

## 9. Avoiding Implicit Timezone Shifts via java.sql.Timestamp and JVM

Legacy JDBC APIs commonly used:

```java
import java.sql.Timestamp;
import java.time.Instant;

// Writing from an instant:
Timestamp legacy = Timestamp.from(Instant.now());

// Reading from ResultSet:
Timestamp loaded = rs.getTimestamp("created_at");
Instant loadedInstant = loaded.toInstant();
```

This is a **snippet inside code that has `ResultSet rs`**, not a standalone file. `Timestamp` can convert to/from `Instant`, yet conversion between a zone-less SQL column and `Timestamp` is still affected by how the driver interprets timestamps, the JVM timezone, or the `Calendar` passed to certain overloads.

Some legacy APIs support:

```java
import java.sql.Timestamp;
import java.util.Calendar;
import java.util.TimeZone;

// Inside PreparedStatementSetter and RowMapper:
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
ps.setTimestamp(1, Timestamp.from(instant), utc);
Timestamp stored = rs.getTimestamp("created_at", utc);
```

Also an **illustrative snippet**, depending on variables `ps`, `rs`, and `instant`. `Calendar` informs the driver how to interpret the timestamp when using the legacy API; it **does not turn a `TIMESTAMP WITHOUT TIME ZONE` column into a timezone-storing column**. For new projects with drivers supporting JDBC 4.2, `setObject`/`getObject` with `java.time` expresses intent much more clearly.

Especially avoid:

```java
// Wrong if "rawLocal" is not guaranteed to be UTC:
Instant guessed = rawLocal.toInstant(ZoneOffset.UTC);
```

That line **assumes** `rawLocal` is already in UTC. If the source was actually 10:15 in Vietnam, attaching UTC shifts the timestamp by 7 hours. Only use `ZoneOffset.UTC` when the data is explicitly defined as UTC; if it is local time, obtain the `ZoneId` and resolve DST cases if any.

## 10. Correctness of Time Ranges and SQL Queries

If a user selects "October 30 in Vietnam", that day's UTC range must be computed **from the user's date and timezone**, rather than taking UTC's calendar day or applying `DATE(happened_at)` with an unclear session timezone.

```java
import java.time.*;

LocalDate requestedDate = LocalDate.of(2026, 10, 30);
ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        requestedDate.atStartOfDay(viewerZone).toInstant();
Instant endExclusive =
        requestedDate.plusDays(1)
                .atStartOfDay(viewerZone).toInstant();
```

This is a **snippet inside a Java method**. Use a **[startInclusive, endExclusive)** half-open interval (inclusive start, exclusive end) to avoid dropping records with sub-second fractions past `23:59:59.999` or overlapping across pagination.

If a PostgreSQL database stores instants in `timestamptz`, SQL can use:

```sql
SELECT event_key, happened_at
FROM event_times
WHERE happened_at >= ?
  AND happened_at < ?
ORDER BY happened_at, event_key;
```

Bind `startInclusive.atOffset(ZoneOffset.UTC)` and `endExclusive.atOffset(ZoneOffset.UTC)` as `OffsetDateTime` on a driver with proper `timestamptz` mapping. This is **PostgreSQL-style illustrative SQL**, not a query executed in the earlier H2 example. The half-open interval pattern also helps index usage and avoids relying on `DATE` extraction functions dependent on session timezone.

In timezones with DST, "one local day" **is not guaranteed to be exactly 24 hours long**. Therefore, compute the start of the next day via `plusDays(1).atStartOfDay(zone)`, never by directly adding `Duration.ofHours(24)` to the start instant.

## 11. Common Read/Write Errors

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| Timestamp off by several hours | Confusing zone-less timestamp with UTC; differing JVM/DB session timezone | Verify column type, session timezone, and data source; use `Instant`/`OffsetDateTime` with clear semantics |
| Wrote `+07:00` and read back `Z` | PostgreSQL `timestamptz` normalizes instants without storing original offset | Compare `toInstant()`; if original offset is needed, store it separately |
| Lost `Europe/Berlin` zone name | Database only stores instant/offset, not `ZoneId` | Store IANA `zone_id` in a separate column when required |
| App inserts wrong time during DST | `LocalDateTime` may be undefined or have two valid offsets | Check `ZoneRules.getValidOffsets()`, require explicit selection or handling policy |
| `getObject(..., OffsetDateTime.class)` reports unsupported | Driver/SQL column has no matching mapping | Inspect driver and SQL type; use `LocalDateTime` for local columns, or controlled vendor mapping |
| `OffsetDateTime.equals` fails despite same event | Offset was normalized while instant remains identical | Compare with `isEqual` or `toInstant` |
| Lost last 3 digits of nanos | Column only stores microseconds while input had nanos | Choose appropriate precision, account for rounding, use tolerance assertions |
| Called `getTime()` and lost microseconds | `Timestamp.getTime()` and `toEpochMilli()` are millisecond-based | Keep `Instant` or `Timestamp.toInstant()` when sub-ms precision is needed |
| `NULL` rejected by driver | `setObject(index, null)` does not specify SQL type | Call `setNull(index, Types.TIMESTAMP...)` explicitly |
| H2 tests pass, production fails | Differences in PostgreSQL/MySQL conversions, session timezone, precision, and JDBC driver | Run integration tests on real DB/driver with varying timezones |
| Timestamp from `CURRENT_TIMESTAMP` differs from JVM clock | DB clock differs from app, statement/transaction time semantics, and session timezone | Pick authoritative timestamp issuer (DB or app), sync clocks, test semantics |
| Two events share the same timestamp | DB/clock precision is insufficient for unique ordering | Add an independent key/sequence or version |

### Quick Diagnostic Checklist

1. **Schema:** is the column `TIMESTAMP WITHOUT TIME ZONE`, `TIMESTAMP WITH TIME ZONE`, `DATETIME`, or another vendor type? What is its precision?
2. **Java model:** is the data an absolute instant, wall-clock time, fixed offset, or schedule under an IANA `ZoneId`?
3. **Connection:** what are the JVM default timezone, database session timezone, and special JDBC URL/driver parameters?
4. **Write/read:** are you using `setObject`/`getObject` or legacy `getTimestamp`? Are there implicit conversions?
5. **Verification:** test the same data under UTC and another timezone, with 6/9-digit nanos, and around DST transitions.
6. **API contract:** which offset/zone does JSON preserve? Is ISO-8601 being parsed into `LocalDateTime` and accidentally dropping the offset?
7. **Assertion style:** when testing instants, compare instants; when testing local schedules, compare date/time and zone per business intent.

## 12. Reliable Storage Design for Each Use Case

**Audit/log/payment:** store a UTC instant using a SQL type with matching semantics for the DBMS, e.g., PostgreSQL `timestamptz(6)`. In the domain, use `Instant`; when JDBC needs `OffsetDateTime`, convert via `instant.atOffset(ZoneOffset.UTC)`. Clients should receive ISO-8601 with explicit offset/UTC.

**Local schedule:** store `LocalDateTime` **and** `ZoneId` such as `"Europe/Berlin"`. When generating actual event occurrences, resolve DST and convert to an instant. For recurring future rules, never store only `+01:00` because summer may require `+02:00`.

**Date-time-only input:** do not append `"Z"` or `"+00:00"` to make data look timezone-aware if the source did not state one. Clarify or enforce the field's timezone before persisting to the DB.

**Data reproducibility:** persist intentional precision, such as microseconds if the DB uses `TIMESTAMP(6)`. For cross-system sync data, document both timezone and precision; test varying offsets, DST, and nanoseconds beyond 6 digits.

**When original offset must be known:** even though `timestamptz` preserves the exact instant, add an offset column or original timestamp string if the business must prove the sender declared `+07:00`. If `Asia/Ho_Chi_Minh` region is needed, store `zone_id` separately; an offset cannot uniquely deduce a zone name.

## 13. Review Questions

1. Can `LocalDateTime.of(2026,10,30,10,15)` be converted to an `Instant` on its own? Why or why not?
2. Why does PostgreSQL return `OffsetDateTime` at `Z` even though the app wrote `+07:00`?
3. When do you need to store `ZoneId` separately instead of just `OffsetDateTime`?
4. Can `TIMESTAMP(6)` store `123456789` nanoseconds in full? Why might H2 differ from PostgreSQL?
5. For a local day in a region with DST, why can `end = start.plus(24h)` be wrong?
6. Why can `OffsetDateTime.equals(...)` return false when two values represent the same instant?
7. Why can converting `java.sql.Timestamp` via `getTime()` lose sub-millisecond precision?

Once you master these questions, you can establish a clear temporal data contract across API, Java, JDBC, and database, avoiding subtle hour shifts and precision bugs.

## Official References

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Java 17 — java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java 17 — ResultSet.getObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html)
- [Java 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html)
- [PostgreSQL — Date/Time Types and Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html)
- [pgJDBC — Using Java 8 Date and Time Classes](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes)
- [H2 — Timestamp Types and Precision](https://h2database.github.io/html/datatypes.html)
- [MySQL 8.4 — DATE, DATETIME and TIMESTAMP](https://dev.mysql.com/doc/refman/8.4/en/datetime.html)
