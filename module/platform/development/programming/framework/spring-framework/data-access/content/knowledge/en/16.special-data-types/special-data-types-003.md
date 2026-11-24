# LocalDate, LocalTime, LocalDateTime, and Instant: Choosing Java Types by SQL Column Semantics

**A value that looks like a date and time does not necessarily represent an absolute instant.** When designing Java classes and working with a database via Spring JDBC, ask what the column represents: a calendar date, a time of day, a local date and time, or a unique moment on the timeline? The answer determines whether to use `LocalDate`, `LocalTime`, `LocalDateTime`, or `Instant`.

For example: a birthday `2026-07-15` needs no time zone; an opening time `09:00` needs no date; an appointment `2026-07-15 16:00` at a venue is local wall-clock time; a login event `2026-07-15T02:30:00Z` is an absolute instant. Storing all of these with the same `Timestamp` type and guessing their meaning on read is a source of hard-to-detect time and timezone bugs.

This lesson belongs to the **special data types section of Spring Framework Data Access**, focusing on **column semantics, JDBC 4.2 mapping, binding/reading with `JdbcTemplate`, timezone conversions, and pitfalls in multi-database deployments**.

## 1. Mapping Table by Business Meaning

| Meaning of Data | Java `java.time` | Common SQL Type | Has Date? | Has Time? | Has Zone/Offset Info? |
| --- | --- | --- | --- | --- | --- |
| Calendar date: birthday, holiday, period cutoff date | `LocalDate` | `DATE` | Yes | No | No |
| Time of day: opens at 09:00, recurring reminder time | `LocalTime` | `TIME` / `TIME WITHOUT TIME ZONE` | No | Yes | No |
| Local calendar date-time: 16:00 appointment | `LocalDateTime` | `TIMESTAMP` / `TIMESTAMP WITHOUT TIME ZONE` | Yes | Yes | No |
| Absolute instant: event occurred, payment received | `Instant` | Usually `TIMESTAMP WITH TIME ZONE` via JDBC `OffsetDateTime`; or a clearly defined UTC strategy | Yes | Yes | `Instant` is a UTC timeline point; carries no original zone name |
| Date-time with **UTC offset** such as `+07:00` | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` if supported by DB | Yes | Yes | Has offset, though not necessarily a zone name |
| Time with offset, no date | `OffsetTime` | `TIME WITH TIME ZONE` if supported by DB | No | Yes | Has offset |

**Important:** The table above reflects common JDBC 4.2 mappings, not a promise that every DB uses the same column names or timezone conversion policies. Vendor types such as MySQL `DATETIME`/`TIMESTAMP` or Oracle `DATE` have their own rules. Inspect the DDL and documentation of the exact database/driver before converting real data.

The four main types in this lesson are all **immutable** and belong to package `java.time`:

- `LocalDate` holds year, month, and day; no time, offset, or `ZoneId`.
- `LocalTime` holds hour, minute, second, and nanosecond within a day; no date or timezone.
- `LocalDateTime` combines a local date and time; **does not uniquely identify an `Instant`**.
- `Instant` holds a point in time on the UTC timeline (seconds/nanoseconds from epoch); does not hold a display timezone name or original civil calendar.

## 2. Choose the Type from Business Questions, Not String Format

### 2.1. `LocalDate` ↔ `DATE`: A Date Remains the Same Date Regardless of User Location

Columns `date_of_birth`, `holiday_date`, and `accounting_day` carry calendar-date semantics. The value `2026-07-15` must stay unchanged whether the user opens the application in Hanoi, Paris, or New York.

```java
LocalDate birthday = LocalDate.of(2000, 8, 20);
```

SQL design:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    date_of_birth DATE NOT NULL
);
```

Do not store a birthday as an `Instant` using a "00:00 UTC" convention: when displayed in a negative-offset timezone, the same `Instant` can fall on the previous day. If the business truly defines a date according to **a specific region** (e.g., a trading date in the London market), still clearly define which zone determines the day boundary during calculation; the `DATE` column itself only stores the resolved date.

### 2.2. `LocalTime` ↔ `TIME`: Clock Time, Not Yet an Event

"The shop opens at 09:00 every day" expresses a **time of day**; without a specific date, it cannot be converted to an `Instant`.

```java
LocalTime opensAt = LocalTime.of(9, 0);
```

Schema:

```sql
CREATE TABLE branch_schedule (
    branch_id BIGINT PRIMARY KEY,
    daily_open_time TIME NOT NULL,
    zone_id VARCHAR(64) NOT NULL
);
```

`zone_id` is an additional business decision when actual openings must be computed across multiple regions, e.g., `Asia/Ho_Chi_Minh` or `Europe/Paris`. Storing `09:00+07:00` as a fixed offset alone does not fully describe Daylight Saving Time (DST) transitions for a region with offset-change rules.

If you need to represent an overnight time range (22:00–02:00), two `LocalTime` values do not by themselves indicate that the end falls on the next day. A business rule or accompanying date data is required.

### 2.3. `LocalDateTime` ↔ `TIMESTAMP WITHOUT TIME ZONE`: Calendar Date and Time, Missing Zone

```java
LocalDateTime appointment = LocalDateTime.of(2026, 7, 15, 16, 0);
```

```sql
CREATE TABLE local_appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_local TIMESTAMP NOT NULL,
    zone_id VARCHAR(64) NOT NULL
);
```

The value `2026-07-15T16:00` says "4 PM on July 15" but **does not tell us what global instant that is**. Only when combined with a `ZoneId` can the application apply the timezone rules of where it occurs:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant actualStart = appointment.atZone(zone).toInstant();
```

This is an illustrative code snippet using the `java.time` API, assuming `appointment` already has a value. When scheduling future events in regions with DST, there must be a policy for nonexistent or overlapping local times; see Section 7.

Do not treat the SQL name `TIMESTAMP` as proof that a column stores an `Instant`. In many DBs, `TIMESTAMP WITHOUT TIME ZONE` stores only **local date and time**, with no offset. If the business only cares about wall-clock start time at a location, this type fits, but `ZoneId` must be managed separately when converting to a point in time.

### 2.4. `Instant`: A Point on the Timeline

`Instant.parse("2026-07-15T02:30:00Z")` and `2026-07-15 09:30:00+07:00` describe **the same event**. Use `Instant` for `created_at`, `processed_at`, `payment_received_at`, log/audit timestamps, etc., when "when did it happen" is the primary information.

```java
Instant occurredAt = Instant.parse("2026-07-15T02:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime displayedAt = occurredAt.atZone(zone).toLocalDateTime();

// displayedAt is 2026-07-15T09:30
```

An `Instant` does not remember which region the creator of the event was in. If the application must **reconstruct the exact original region of the user/venue** or schedule future recurring events, also store the zone name, such as `Asia/Ho_Chi_Minh`, in a `zone_id` column. Data like `UTC+07:00` is only the offset at one moment and does not replace all historical/future rules of a `ZoneId`.

## 3. Why Can the Same `LocalDateTime` Become Multiple `Instant`s?

Given local time 09:30 on July 15, 2026:

```java
import java.time.*;

class SameWallTime {
    public static void main(String[] args) {
        LocalDateTime local = LocalDateTime.of(2026, 7, 15, 9, 30);
        Instant inHcm = local.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")
        ).toInstant();
        Instant inParis = local.atZone(
            ZoneId.of("Europe/Paris")
        ).toInstant();

        System.out.println("HCMC: " + inHcm);
        System.out.println("Paris: " + inParis);
    }
}
```

Run standalone with Java 17+:

```bash
javac SameWallTime.java
java SameWallTime
```

Note: the snippet above must be saved to `SameWallTime.java`. Output:

```text
HCMC: 2026-07-15T02:30:00Z
Paris: 2026-07-15T07:30:00Z
```

On July 15, 2026, Ho Chi Minh City has offset `+07:00`, while Paris is observing DST with offset `+02:00`. Both read "09:30", yet the two `Instant`s are 5 hours apart. Without an accompanying `ZoneId`, `LocalDateTime` does not contain enough information to pick a single result.

Conversely, an `Instant` always identifies one exact point on the timeline; displaying it via `atZone(...)` may yield different dates and times in different places **without changing the underlying event**.

## 4. The JDBC 4.2 Boundary and Spring JDBC

Spring JDBC provides `JdbcTemplate`, `RowMapper`, `PreparedStatementSetter`, and connection/exception handling. **Converting `java.time` to SQL column types and reading back still goes through the JDBC driver**, so you must choose a mapping appropriate for the DB.

### 4.1. Writing with `PreparedStatement.setObject`

With drivers supporting JDBC 4.2, the common bind pattern is:

```java
ps.setObject(1, localDate);       // DATE
ps.setObject(2, localTime);       // TIME WITHOUT TIME ZONE
ps.setObject(3, localDateTime);   // TIMESTAMP WITHOUT TIME ZONE
```

This is an illustrative snippet inside a callback that has `ps` and the three created values. Do not use `ps.setString(...)` for all date/time columns and rely on the database to parse strings automatically, because formatting and timezones can depend on session/vendor settings.

**Specifically, `Instant` is not a mandatory Java type in JDBC 4.2 mappings.** One approach compatible with H2 and PostgreSQL JDBC is converting `Instant` to `OffsetDateTime` in UTC and binding to `TIMESTAMP WITH TIME ZONE`:

```java
OffsetDateTime utcValue = OffsetDateTime.ofInstant(
    occurredAt, ZoneOffset.UTC
);
ps.setObject(4, utcValue);
```

Do not infer that `ps.setObject(index, instant)` works on every driver. For instance, the PostgreSQL driver supports `OffsetDateTime` but does not support binding/reading `Instant` directly under its `java.time` mapping. H2 may support additional Java types beyond that minimum.

If the DB does not provide `TIMESTAMP WITH TIME ZONE`, the system can choose a **defined and tested UTC storage convention** (using an appropriate vendor column type) or store epoch integers at an agreed precision. In that case, clearly define who performs conversions, session timezone, precision, and read-back behavior; never treat bare `TIMESTAMP` as naturally having the same semantics as `Instant`.

### 4.2. Reading with `ResultSet.getObject(column, Type.class)`

```java
LocalDate day = rs.getObject("business_day", LocalDate.class);
LocalTime time = rs.getObject("opening_time", LocalTime.class);
LocalDateTime localTs = rs.getObject(
    "appointment_local", LocalDateTime.class
);
OffsetDateTime offsetValue = rs.getObject(
    "logged_at", OffsetDateTime.class
);
Instant eventInstant = offsetValue.toInstant();
```

This is an illustrative snippet inside a `RowMapper` or wherever `ResultSet rs` is available. Advantage: the code states the **expected Java type** for each column. Do not assume `rs.getObject("logged_at")` without passing a `Class` will directly return `Instant`; it may return `java.sql.Timestamp`, `OffsetDateTime`, or another vendor type depending on the driver.

If a column allows `NULL`, `rs.getObject("...", Type.class)` can return `null`. Check for `null` before calling `offsetValue.toInstant()`; the complete example below declares all four columns `NOT NULL`.

### 4.3. Declaring SQL Type When Binding `NULL`

```java
ps.setNull(1, java.sql.Types.DATE);
ps.setNull(2, java.sql.Types.TIME);
ps.setNull(3, java.sql.Types.TIMESTAMP);
ps.setNull(4, java.sql.Types.TIMESTAMP_WITH_TIMEZONE);
```

These are four **illustrative calls corresponding to four column types**, not code meant to execute together on a single real statement. For nullable parameters, declare the proper SQL type per schema and driver instead of sending the string `"null"` or relying on type inference from `null`.

Spring wrappers like `SqlParameterValue` and `MapSqlParameterSource.addValue(name, value, sqlType)` also carry SQL type metadata when not writing a `PreparedStatement` callback directly. Remember that configuring the SQL type does not substitute for choosing the right **temporal semantics**.

## 5. Standalone Runnable Example: Four Column Types with JdbcTemplate and H2

This example stores a business date, opening time, local appointment, and absolute occurrence instant together. To highlight the difference, the appointment is set to **16:00** while the audit timestamp is **02:30 UTC** (i.e., 09:30 in Ho Chi Minh City).

Data diagram:

```text
Java domain                   SQL column                         JDBC bind/read
LocalDate                     business_day DATE                  LocalDate
LocalTime                     opening_time TIME                 LocalTime
LocalDateTime                 appointment_local TIMESTAMP       LocalDateTime
Instant                       logged_at TIMESTAMP WITH TIME ZONE OffsetDateTime UTC <-> Instant
```

Create structure:

```text
temporal-jdbc-demo/
├── build.gradle
└── src/main/java/TemporalJdbcDemo.java
```

Contents of `build.gradle` (Java 17+, Gradle, and Maven Central):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TemporalJdbcDemo'
}
```

Contents of `src/main/java/TemporalJdbcDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class TemporalJdbcDemo {

    record TemporalRow(
        LocalDate businessDay,
        LocalTime openingTime,
        LocalDateTime appointmentLocal,
        Instant loggedAt
    ) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:temporal_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);

        jdbc.execute("""
            CREATE TABLE temporal_event (
                id BIGINT PRIMARY KEY,
                business_day DATE NOT NULL,
                opening_time TIME NOT NULL,
                appointment_local TIMESTAMP NOT NULL,
                logged_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """);

        LocalDate businessDay = LocalDate.of(2026, 7, 15);
        LocalTime openingTime = LocalTime.of(9, 0);
        LocalDateTime appointmentLocal = LocalDateTime.of(
            2026, 7, 15, 16, 0
        );
        Instant loggedAt = Instant.parse("2026-07-15T02:30:00Z");

        int inserted = jdbc.update("""
            INSERT INTO temporal_event
                (id, business_day, opening_time,
                 appointment_local, logged_at)
            VALUES (?, ?, ?, ?, ?)
            """, ps -> {
                ps.setLong(1, 7L);
                ps.setObject(2, businessDay);
                ps.setObject(3, openingTime);
                ps.setObject(4, appointmentLocal);
                ps.setObject(5, OffsetDateTime.ofInstant(
                    loggedAt, ZoneOffset.UTC
                ));
            });

        TemporalRow row = jdbc.queryForObject("""
            SELECT business_day, opening_time,
                   appointment_local, logged_at
            FROM temporal_event
            WHERE id = ?
            """, (rs, rowNum) -> {
                LocalDate day = rs.getObject(
                    "business_day", LocalDate.class
                );
                LocalTime time = rs.getObject(
                    "opening_time", LocalTime.class
                );
                LocalDateTime local = rs.getObject(
                    "appointment_local", LocalDateTime.class
                );
                OffsetDateTime loggedOffset = rs.getObject(
                    "logged_at", OffsetDateTime.class
                );
                return new TemporalRow(
                    day, time, local, loggedOffset.toInstant()
                );
            }, 7L);

        System.out.println("Inserted rows: " + inserted);
        System.out.println("Business day: " + row.businessDay());
        System.out.println("Opening time: " + row.openingTime());
        System.out.println("Appointment local: " + row.appointmentLocal());
        System.out.println("Logged instant: " + row.loggedAt());
        System.out.println(
            "Logged in HCMC: " + row.loggedAt()
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDateTime()
        );
    }
}
```

Run from the `temporal-jdbc-demo` directory:

```bash
gradle --quiet run
```

If the project has a Gradle Wrapper, you can use `./gradlew --quiet run` (Windows PowerShell: `.\gradlew.bat --quiet run`).

With a freshly created H2 table and fixed data, the program's stdout is:

```text
Inserted rows: 1
Business day: 2026-07-15
Opening time: 09:00
Appointment local: 2026-07-15T16:00
Logged instant: 2026-07-15T02:30:00Z
Logged in HCMC: 2026-07-15T09:30
```

Step-by-step explanation:

1. `DATE` accepts `LocalDate` and returns the exact same date, with no hour adjustment needed.
2. `TIME` accepts `LocalTime` 09:00, without turning into a timestamp with a date.
3. `TIMESTAMP` accepts `LocalDateTime` 16:00, with no offset attached.
4. `Instant` is converted to a UTC `OffsetDateTime` to bind to `TIMESTAMP WITH TIME ZONE`. On read, `toInstant()` restores **the point in time**.
5. Only at **display** time is `loggedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` called; the audit data preserves the meaning "the event occurred at 02:30 UTC".
6. `JdbcTemplate` manages statements/result sets and translates `SQLException` into Spring's `DataAccessException` hierarchy; the callbacks here only bind or map data.

Do not infer that `appointmentLocal` and `loggedAt` are the same kind of value just because both look like dates and times; one is 16:00 in an unspecified zone, and the other is an absolute point in time that can be displayed as 09:30 in Vietnam.

**Scope of the example:** H2 2.3.x supports `LocalDate`, `LocalTime`, `LocalDateTime`, and `OffsetDateTime` matching the four column types used. When deploying to PostgreSQL, SQL Server, Oracle, or MySQL, type names, precision, and timezone handling must be verified separately against the actual driver.

## 6. If the Project Uses PostgreSQL: Example Separating `timestamp` and `timestamptz`

In PostgreSQL:

```sql
CREATE TABLE order_events (
    id BIGINT PRIMARY KEY,
    scheduled_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    location_zone_id VARCHAR(64) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Business example:

- `scheduled_local` = "2026-07-15 16:00": schedule in the branch's local time.
- `location_zone_id` = "Asia/Ho_Chi_Minh": provides zone rules to locate the schedule on the timeline.
- `occurred_at` = "2026-07-15T02:30:00Z": audit point in time.

Common PostgreSQL driver mapping:

```java
LocalDateTime local = rs.getObject(
    "scheduled_local", LocalDateTime.class
);

OffsetDateTime occurred = rs.getObject(
    "occurred_at", OffsetDateTime.class
);
Instant instant = occurred.toInstant();
```

PostgreSQL `TIMESTAMP WITH TIME ZONE` (often written `timestamptz`) semantically stores a point in time in UTC; it **does not store the original zone name**. When displayed via SQL, the system converts using the session timezone parameter. PostgreSQL JDBC typically reads it back as an `OffsetDateTime` at offset `Z`. Therefore:

```text
Input:   2026-07-15T09:30:00+07:00
Read:    2026-07-15T02:30:00Z
Instant: same point in time
```

If you need to match temporal meaning, compare `input.toInstant()` and `read.toInstant()`. Do not require `OffsetDateTime.equals(...)` to be `true`, because `OffsetDateTime` also compares the local date-time and offset. If you need the original IANA zone or future scheduling, store `zone_id` intentionally.

For SQL Server, MySQL, Oracle, etc., concepts and session/driver timestamp conversions may differ. In particular, never assume `DATETIME` or `TIMESTAMP` means UTC merely because the application runs in UTC.

## 7. DST: Nonexistent Times, Overlapping Times, and Zone Names

Use `ZoneId` and `ZoneOffset` according to their roles:

- `ZoneOffset.ofHours(7)` is a **fixed** offset from UTC.
- `ZoneId.of("Europe/Paris")` is a zone name with **offset-changing rules** by date, including Daylight Saving Time.
- `Instant` has no DST; DST is a rule for expressing **civil time** in a specific region.

There are two special cases in regions with DST:

**Gap — nonexistent time:** When clocks spring forward from 01:59 to 03:00, times like 02:30 do not exist on that transition day. `LocalDateTime` can still represent 02:30 because it has no zone awareness, but converting it to `Instant` requires a policy: reject the appointment, advance to the next valid time, or ask the user.

**Overlap — time occurring twice:** When clocks fall back, 02:30 can correspond to **two distinct `Instant`s**. `local.atZone(zone)` has a default rule to pick an offset; if the business requires precision, inspect `zone.getRules().getValidOffsets(local)` and choose an offset according to an explicit policy rather than silently relying on the default.

Check pattern before creating a schedule:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

// Assume local and zone come from validated data.
ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    // Gap: local time does not exist in that zone.
    throw new IllegalArgumentException("Nonexistent local time");
}
if (offsets.size() > 1) {
    // Overlap: policy needed to pick an offset / notify user.
    throw new IllegalArgumentException("Ambiguous local time");
}

Instant exactMoment = local.atOffset(offsets.get(0)).toInstant();
```

This is a **code snippet for an application that already has `local` and `zone`**, not a standalone program. It fits when the requirement is to reject ambiguous schedules; other domains may choose a different policy. For cross-zone comparison or scheduling, resolve the ambiguity first before storing or computing `Instant`.

## 8. NULL, Precision, Value Ranges, and Clocks

### 8.1. Handling Nullable Columns

`ResultSet.getObject(column, LocalDate.class)` and other temporal types can return `null` on SQL `NULL`. For `Instant` via `OffsetDateTime`:

```java
OffsetDateTime dbValue = rs.getObject(
    "completed_at", OffsetDateTime.class
);
Instant completedAt = (dbValue == null)
    ? null
    : dbValue.toInstant();
```

Do not call `toInstant()` immediately on `null`. In the domain layer, consider `Optional` at the API/method boundary if helpful; never turn `NULL` into `Instant.EPOCH`, because "no timestamp yet" differs from "1970-01-01T00:00:00Z".

### 8.2. Precision Differences Between Java and the Database

`java.time` has **nanosecond** precision; the database may store only microseconds, milliseconds, or seconds depending on the column/driver. For example, `TIMESTAMP(3)` in some DBs stores three fractional digits of a second; `TIMESTAMP(6)` stores six digits. When writing `2026-07-15T09:30:00.123456789`, the value read back may be truncated or rounded.

Therefore, do not assume `input.equals(readBack)` if the schema preserves less than nanosecond precision. In tests, check the DB's precision capability and maintain consistent rounding, or use fixed values without sub-precision fractions as in Section 5.

### 8.3. Clock and Deterministic Testing

`Instant.now()` depends on the current clock, while `LocalDate.now()` and `LocalDateTime.now()` also depend on the timezone used to create the value. In business logic that captures absolute instants, injecting a `Clock` makes testing easy:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.fixed(
    Instant.parse("2026-07-15T02:30:00Z"),
    java.time.ZoneOffset.UTC
);
Instant createdAt = Instant.now(clock);
```

This is an illustrative code snippet. `Instant.now(clock)` gives deterministic values in tests; `Clock.systemUTC()` is a common choice at runtime. Even when the application has a UTC `Clock`, you must still choose the right SQL column type when persisting.

### 8.4. Do Not Use Epoch-Milliseconds for Every Kind of Time

You can store an `Instant` as a `long epochMillis` under a well-defined strategy. However, `LocalDate` is a "calendar date" and `LocalTime` is a "wall-clock time"; neither should be turned into epoch values without a date/zone, because doing so forces fabricating missing information and risks date shifts. Epoch milliseconds also lose sub-millisecond nanoseconds.

## 9. Converting from Legacy JDBC Types

The legacy APIs include `java.sql.Date`, `java.sql.Time`, and `java.sql.Timestamp`. When encountering legacy code, explicit conversions exist:

```java
LocalDate day = sqlDate.toLocalDate();             // DATE
LocalTime time = sqlTime.toLocalTime();             // TIME
LocalDateTime local = sqlTimestamp.toLocalDateTime(); // TIMESTAMP local
```

These conversions correspond to **already-understood SQL values/types**, not proof that every `Timestamp` equals an `Instant` in every database. `java.sql.Timestamp` can carry driver/session timezone interpretation when reading `TIMESTAMP WITHOUT TIME ZONE`; blindly calling `getTimestamp(...).toInstant()` can easily turn a local value into the wrong instant.

With modern drivers supporting JDBC 4.2, prefer `setObject` and `getObject(..., Class)` for the corresponding `java.time` classes. If an older driver lacks support, use adapters `Date.valueOf(LocalDate)`, `Time.valueOf(LocalTime)`, and `Timestamp.valueOf(LocalDateTime)` after verifying precision and timezone behavior. For absolute events, define a specific UTC/driver policy instead of applying a blanket cast.

Do not rely on JVM-wide `TimeZone.setDefault(...)` to "fix" column bugs; that affects many libraries and breaks when the system serves multiple user regions. Fix the issue in the domain model, column mapping, connection/session configuration, or explicit conversion logic.

## 10. Common Errors and Symptoms

| Error | Consequence | Resolution |
| --- | --- | --- |
| Storing `LocalDate` as `Instant` at 00:00 UTC | Users in negative-offset zones may see the previous day | Use `DATE` and `LocalDate` for civil dates |
| Storing opening hours in `TIMESTAMP` with an arbitrary 1970 date | Introduces a fake date and zone shifts on conversion | Use `TIME` / `LocalTime`; add zone when computing actual occurrences |
| Using `LocalDateTime` for multi-zone `created_at` without convention | Cannot tell when the event occurred on the timeline | Use `Instant` in domain; JDBC/column layer has an explicit instant strategy |
| Treating `TIMESTAMP WITHOUT TIME ZONE` as UTC by default | Data reads wrong if session/app timezone changes | Check DDL and encode/decode strategy; migrate intentionally |
| Calling `setObject(Instant)` on an unsupported driver | Driver throws `SQLException` / Spring `DataAccessException` | Use `OffsetDateTime` or a verified driver/DB adapter |
| Reading `TIMESTAMP WITH TIME ZONE` into `LocalDateTime` | Drops offset/instant semantics, may shift hours | Read `OffsetDateTime`, convert via `toInstant()` |
| Assuming `TIMESTAMP WITH TIME ZONE` stores `Europe/Paris` zone name | Cannot restore original region and DST schedule | Store `ZoneId` in a separate column when required by business |
| Comparing `OffsetDateTime.equals` when DB normalizes to UTC | Same `Instant` may still evaluate as unequal | Compare `toInstant()` for instant semantics |
| Not handling DST gap/overlap for future appointments | Nonexistent time or two valid interpretations | Define zone/offset policy when converting `LocalDateTime` |
| Comparing nanosecond time against a micro/millisecond column | Test fails even though DB handles precision properly | Design tests around actual precision |
| Using `LocalDateTime.now()` for audit | Depends on machine default timezone | Use `Instant.now(clock)` and a UTC storage strategy |

### Real-World Error Scenarios

**Scenario:** a user selects birthday 01/01/2000. The backend converts it to `2000-01-01T00:00:00Z` and stores it as an absolute instant. A client in `UTC-08:00` renders `1999-12-31 16:00` and extracts the date part as 31/12/1999. The mistake was **turning a civil date into an instant** that does not belong to the domain. The fix is storing `DATE` and passing `LocalDate`; timezone is not part of a birthday value.

**Another scenario:** a meeting at 16:00 Paris time on a summer day. If only `2026-07-15T16:00` is stored and the backend mistakenly assigns `UTC`, the actual meeting shifts by two hours. The fix is storing/knowing `Europe/Paris`, resolving DST, and converting to the exact `Instant` when sending notifications.

## 11. Integration Testing Checklist

For each temporal column, test both **business semantics** and **data round-trip** through the actual target driver/DB:

1. **`DATE`/`LocalDate`:** write a fixed date, read the same date back, and ensure changing JVM/session timezone does not alter the civil date within the expected contract.
2. **`TIME`/`LocalTime`:** write 09:00, read 09:00; verify seconds/nanos if supported by the column, and overnight schedules if the app supports them.
3. **`TIMESTAMP`/`LocalDateTime`:** write 16:00, read 16:00 under the right schema; do not subtract/add timezone when this is local wall-time.
4. **`TIMESTAMP WITH TIME ZONE`/`Instant`:** bind `OffsetDateTime` from `Instant`, read as `OffsetDateTime`, and compare **`toInstant()`**; test different offsets representing the same instant.
5. **Timezone:** read/write when JVM and connection/session have different timezone settings; for DBs with special rules, verify empirically.
6. **DST:** test a time in a DST gap and one in an overlap for a DST-observing zone; apply the documented policy.
7. **NULL:** test nullable columns, ensuring no `NullPointerException` is thrown and `NULL` is not replaced with epoch.
8. **Precision:** write a timestamp with nanoseconds; confirm rounding/truncation matches `TIMESTAMP(p)`.
9. **Portability:** test with production driver/database versions; H2 used in examples does not prove every vendor behaves identically.
10. **JSON/API:** verify `LocalDate` is serialized as a date string (e.g., `2026-07-15`) and `Instant` carries explicit offset/UTC (e.g., `2026-07-15T02:30:00Z`); do not merge them into the same arbitrary string format.

## 12. Self-Check Questions

**Q1.** A column stores fiscal period closing date `2026-07-31` and must always be July 31 regardless of user location. What should you choose?

**Answer:** `LocalDate` in Java, `DATE` in SQL. If the period boundary is defined by a specific region, use that region when **computing the date**, rather than turning the resolved date value into an `Instant`.

**Q2.** A column stores "delivery at 16:00 in Paris on July 15, 2026". Is `LocalDateTime` alone enough to determine the `Instant`?

**Answer:** No. You must know the `ZoneId`, such as `Europe/Paris`. On that date Paris is at `UTC+02:00`, so `16:00` local corresponds to `14:00Z`.

**Q3.** Column `processed_at` stores when an event actually happened. The application uses PostgreSQL. Which Java types should cross JDBC?

**Answer:** Domain should use `Instant`; at the JDBC boundary use `OffsetDateTime` (typically at `ZoneOffset.UTC`) for a `TIMESTAMP WITH TIME ZONE` column. Read `OffsetDateTime` and call `toInstant()`. Do not assume pgJDBC supports `getObject(..., Instant.class)`.

**Q4.** Do the two `OffsetDateTime` values `2026-07-15T09:30+07:00` and `2026-07-15T02:30Z` represent the same instant?

**Answer:** Yes, because they have the same `Instant`. The two objects do not have to be equal under `OffsetDateTime.equals` due to differing offsets and local date-time fields.

**Q5.** A recurring schedule at 09:00 daily in a city with DST: is storing only `LocalTime` sufficient?

**Answer:** Not enough to compute trigger times on the timeline. You also need applicable dates, the `ZoneId` name, and a policy for when local time falls in a gap/overlap.

## 13. Conclusion

Read the "column semantics" before choosing a type:

- `DATE` ↔ `LocalDate`: calendar **date**.
- `TIME` ↔ `LocalTime`: **time** of day.
- `TIMESTAMP WITHOUT TIME ZONE` ↔ `LocalDateTime`: **local date + time**, not a unique point in time.
- **Absolute instant** ↔ `Instant` in domain; when using JDBC 4.2 with `TIMESTAMP WITH TIME ZONE`, typically convert via `OffsetDateTime` for writing/reading and back to `Instant`.

A successful JDBC call only proves the SQL statement executed. Correctness of temporal data also requires checking **timezones, DST, vendor SQL types, precision, NULLs, and JDBC driver capabilities**. Picking the semantically right type prevents records from shifting dates, shifting hours, or losing context as the application expands across regions.

### References

- [Spring Framework — JDBC core and `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- [Java 17 — `java.time` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html).
- [JDBC 4.2 Specification — Java time and SQL type mappings](https://download.oracle.com/otndocs/jcp/jdbc-4_2-mrel2-spec/index.html).
- [H2 Database — Data Types](https://h2database.com/html/datatypes.html).
- [PostgreSQL JDBC — Java 8 Date and Time classes](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes).
