# Testing Time Zones, Daylight Saving Time, and Boundary Date-Time Values

This lesson belongs to the **DATABASE_MYSQL** module. When an application stores order timestamps, appointments, payment deadlines, or telemetry readings, results can be wrong even when the SQL query is completely valid if MySQL, the JDBC driver, the JVM, and the application use different time zones. Subtle bugs often surface at daylight saving time (DST) transitions, skipped or repeated hours, leap days, month-ends, year-ends, and fractional-second boundaries.

Date-time testing must distinguish **an absolute point in time** from **a local wall-clock time**. For instance, 01:30 on November 3 in New York can occur twice when the clock falls back one hour. A `LocalDateTime` value alone cannot distinguish those two instants. This lesson explains how MySQL stores temporal types, how session time zone and DST affect queries, how to test boundaries, and how Java/Spring Boot interacts with Connector/J.

## 1. Distinguishing Absolute Instants from Local Wall-Clock Time

There are two distinct concepts:

- **Instant:** a unique point on the timeline, typically represented in UTC or epoch time. For example, a transaction confirmed at a specific moment.
- **Local date/time:** calendar date and wall-clock time at a location, not bound to a time zone. For example, a store opening at 09:00 or an appointment at 02:30 on March 10.

One instant can render as many local times depending on the time zone. Conversely, a local time may correspond to zero instants or two instants when DST rules shift the clock.

For example:

- `2024-03-10 02:30` in New York does not exist because the clock jumps from `01:59:59` to `03:00:00`.
- `2024-11-03 01:30` in New York happens twice: first at UTC-04:00, and again at UTC-05:00.

Therefore, before choosing a column type, identify what the data represents:

| Domain concept | Typically suitable data model |
|---|---|
| Payment timestamp or event log | Instant, stored under a UTC convention |
| Date of birth or public holiday | `LocalDate` / MySQL `DATE` |
| Daily store opening hours | `LocalTime`, usually without date or time zone |
| Appointment at a specific location | Local date/time + `ZoneId`, then resolving the instant via DST rules |
| Time a device sent telemetry | Instant, plus source metadata if needed |
| Processing duration | `Duration` or duration value; do not treat `TIME` as an instant |

Never store a local time and assume it always identifies a unique instant.

## 2. MySQL Date and Time Types

MySQL offers temporal types with distinct semantics:

| Type | Data represented | Time zone and conversion | General range |
|---|---|---|---|
| `DATE` | Calendar date | Contains no time zone | `1000-01-01` to `9999-12-31` |
| `TIME` | Time of day or duration | Not a time-zone-aware instant | `-838:59:59.000000` to `838:59:59.000000` |
| `DATETIME` | Wall-clock date and time | Stores date/time components without automatic conversion by session time zone | `1000-01-01 00:00:00` to `9999-12-31 23:59:59` |
| `TIMESTAMP` | Point in time | MySQL converts between session time zone and UTC on write/read | Typically `1970-01-01 00:00:01` UTC to `2038-01-19 03:14:07` UTC |
| `YEAR` | Year | No time zone | Range depends on syntax and mode, typically `1901-2155` plus `0000` |

`TIME`, `DATETIME`, and `TIMESTAMP` support fractional seconds with precision from 0 to 6 digits, such as `DATETIME(6)` or `TIMESTAMP(3)`. Verify exact ranges and details against your MySQL version.

### 2.1. DATE

`DATE` stores only a calendar date, with no time or time zone:

~~~sql
CREATE TABLE holidays (
    holiday_date DATE NOT NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (holiday_date)
);
~~~

`DATE` fits dates of birth, calendar effective dates, or holidays. Do not store a date of birth as a `TIMESTAMP` when the domain does not represent a specific instant, because time zone conversions can shift the displayed calendar date.

### 2.2. DATETIME

`DATETIME` stores year, month, day, hour, minute, second, and fractional-second components if declared. MySQL does not automatically convert `DATETIME` values between UTC and the session time zone.

~~~sql
CREATE TABLE store_schedule (
    store_id BIGINT NOT NULL,
    opens_at DATETIME NOT NULL,
    PRIMARY KEY (store_id)
);
~~~

`DATETIME` suits local wall-clock times or date-time values whose entered components must stay intact. However, a `DATETIME` column does not store a `ZoneId` or offset. If the data represents time-zone-bound appointments, also store the zone name such as `America/New_York` so it can be re-interpreted under regional rules.

### 2.3. TIMESTAMP

`TIMESTAMP` is converted by MySQL from the session time zone to UTC on write, and from UTC back to the session time zone on read. This column fits absolute instants when the application and database align on time zone handling.

~~~sql
CREATE TABLE payment_events (
    event_id BIGINT PRIMARY KEY,
    paid_at TIMESTAMP(6) NOT NULL
);
~~~

The same value read from two sessions with different time zones renders as two different local times, yet still represents the exact same instant.

The range of `TIMESTAMP` is substantially narrower than `DATETIME`. If the domain must store dates outside the `TIMESTAMP` range—such as distant historical data or schedules centuries in the future—evaluate `DATETIME` with an explicit time zone convention.

### 2.4. TIME

`TIME` represents a time of day or an elapsed interval, which can be negative and exceed 24 hours. For instance, a 27-hour processing duration can be stored in `TIME`, but `TIME` should not be interpreted as a time-zone-aware "time of day."

~~~sql
CREATE TABLE job_metrics (
    job_id BIGINT PRIMARY KEY,
    elapsed_time TIME(3) NOT NULL
);
~~~

If the domain requires measuring long durations or exact millisecond/microsecond arithmetic, consider storing an integer in an agreed unit or using an application-level duration type. Clarify how negative values and `TIME` limits are handled.

## 3. Session Time Zone and How MySQL Converts Values

MySQL exposes time zone variables:

~~~sql
SELECT @@global.time_zone,
       @@session.time_zone,
       @@system_time_zone;
~~~

- Global time zone is the default applied when creating new sessions.
- Session time zone is the time zone currently active for the current connection.
- System time zone reflects the OS time zone MySQL detected at startup.

Changing the global time zone does not automatically alter already-open sessions. Connection pools can keep connections alive for long periods, so verify the session time zone on actual pooled connections.

### 3.1. Testing TIMESTAMP and DATETIME Across Two Sessions

Create a probe table:

~~~sql
CREATE TEMPORARY TABLE temporal_probe (
    id INT PRIMARY KEY,
    ts_value TIMESTAMP(6) NOT NULL,
    dt_value DATETIME(6) NOT NULL
);
~~~

Write the same literal strings while the session uses UTC:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO temporal_probe (id, ts_value, dt_value)
VALUES (1, '2024-01-15 12:00:00.123456',
           '2024-01-15 12:00:00.123456');

SELECT ts_value, dt_value
FROM temporal_probe
WHERE id = 1;
~~~

Then switch the session to UTC+05:30 and read back:

~~~sql
SET SESSION time_zone = '+05:30';

SELECT ts_value, dt_value
FROM temporal_probe
WHERE id = 1;
~~~

`TIMESTAMP` is displayed in the new session time zone, whereas `DATETIME` keeps the stored date-time components unchanged. This is an important test to prove the application does not accidentally depend on a connection's default time zone.

### 3.2. NOW(), CURRENT_TIMESTAMP, and UTC_TIMESTAMP

Time functions carry distinct semantics:

~~~sql
SELECT NOW(6) AS session_now,
       CURRENT_TIMESTAMP(6) AS session_current_timestamp,
       UTC_TIMESTAMP(6) AS utc_now,
       @@session.time_zone AS session_zone;
~~~

`NOW()` and `CURRENT_TIMESTAMP()` return the timestamp in the session time zone. `UTC_TIMESTAMP()` returns the value in UTC. When using `DEFAULT CURRENT_TIMESTAMP` on a `TIMESTAMP` column, understand the session time zone of the writing connection.

To keep test results independent of environment settings, pin the session time zone:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

The offset `'+00:00'` does not require MySQL to look up zone names in the time zone tables.

## 4. Named Time Zones and Time Zone Tables

MySQL supports offset time zones like `'+00:00'` or `'-05:00'`, and named zones like `'America/New_York'` or `'Asia/Ho_Chi_Minh'`. Named zones contain historical and DST rules. For MySQL to process named zones, the time zone tables must be populated and kept up to date.

Test a named time zone:

~~~sql
SELECT CONVERT_TZ(
    '2024-01-15 12:00:00',
    '+00:00',
    'Asia/Ho_Chi_Minh'
) AS local_time;
~~~

If the result is `NULL`, either the zone name is invalid or the time zone tables have not been populated or are incomplete.

Check the system tables:

~~~sql
SELECT COUNT(*) AS timezone_name_count
FROM mysql.time_zone_name;
~~~

Loading time zone tables is usually performed by administrators from OS zoneinfo data using the MySQL utility appropriate for the platform. After updating time zone data, follow the operational guide for your MySQL version and re-verify `CONVERT_TZ` results. Never modify time zone tables manually with ad-hoc `UPDATE` statements.

### 4.1. Fixed Offsets vs. Named Zones

A fixed offset like `'-05:00'` only describes the offset at a single point in time. It does not capture New York's full DST rules. In summer, New York typically observes UTC-04:00; in winter, it observes UTC-05:00.

A named zone like `'America/New_York'` lets MySQL apply regional rules when time zone tables are loaded. For long-lived business data, storing a `ZoneId` is usually better than storing a fixed offset when local times must reflect active rules.

Time zone rules can be changed by governments. Maintain a plan to update the OS, MySQL, and JVM time zone databases; the same zone name can yield different results across `tzdata` versions.

## 5. Testing Daylight Saving Time (DST)

DST causes local clocks to spring forward or fall back. Two cases must be tested explicitly:

- **Gap (nonexistent hour):** clocks jump forward, skipping a span of local time.
- **Overlap (repeated hour):** clocks fall back, causing a span of local time to occur twice.

Example using `America/New_York` in 2024:

| Event | UTC instant | Local time |
|---|---|---|
| Before spring DST transition | `2024-03-10 06:30 UTC` | `2024-03-10 01:30 UTC-05:00` |
| After spring DST transition | `2024-03-10 07:30 UTC` | `2024-03-10 03:30 UTC-04:00` |
| First occurrence of repeated hour | `2024-11-03 05:30 UTC` | `2024-11-03 01:30 UTC-04:00` |
| Second occurrence of repeated hour | `2024-11-03 06:30 UTC` | `2024-11-03 01:30 UTC-05:00` |

Two different instants in November both render as `01:30`. If only the local datetime `2024-11-03 01:30` is stored without an offset or zone resolution, it is impossible to tell whether it was the first or second occurrence.

### 5.1. Testing UTC-to-Local Conversion

With time zone tables loaded, run:

~~~sql
SELECT
    CONVERT_TZ('2024-03-10 06:30:00', '+00:00',
               'America/New_York') AS before_spring_jump,
    CONVERT_TZ('2024-03-10 07:30:00', '+00:00',
               'America/New_York') AS after_spring_jump,
    CONVERT_TZ('2024-11-03 05:30:00', '+00:00',
               'America/New_York') AS first_fall_0130,
    CONVERT_TZ('2024-11-03 06:30:00', '+00:00',
               'America/New_York') AS second_fall_0130;
~~~

The results should show local time jumping from `01:30` to `03:30` in spring, and two distinct instants in autumn both displaying `01:30` yet carrying different offsets if the application stores/displays the corresponding offset.

### 5.2. Nonexistent Local Times

`02:30` on March 10, 2024 in New York falls inside the spring gap. When a user enters this time, the application must follow an explicit policy:

- Reject it and prompt for a valid time.
- Shift automatically to the first valid instant after the gap.
- Apply a documented business rule.

Do not let implicit driver or database behavior dictate business rules. Tests must verify the policy is enforced consistently.

### 5.3. Repeated Local Times

`01:30` on November 3, 2024 in New York has two valid offsets. If the application must distinguish them, the UI or API must capture the offset/choice, or the domain must specify choosing the earlier or later occurrence.

You cannot store only a local datetime and expect to recover the exact instant later. Store the resolved instant; if regional re-display is needed, store the `ZoneId` as well.

## 6. Testing Boundary Date-Time Values

Date-time tests must cover calendar and data-type boundaries, not only typical values.

### 6.1. Leap Years and Month-End Dates

Under the Gregorian calendar, years divisible by 4 are normally leap years, except century years divisible by 100 are not leap years unless also divisible by 400.

| Date | Expectation |
|---|---|
| `2024-02-29` | Valid |
| `2000-02-29` | Valid |
| `1900-02-29` | Invalid |
| `2023-02-29` | Invalid |
| `2024-04-30` | Valid |
| `2024-04-31` | Invalid |

Test with deliberate inserts in a test environment:

~~~sql
CREATE TEMPORARY TABLE date_probe (
    id INT PRIMARY KEY,
    value_date DATE
);

INSERT INTO date_probe VALUES
    (1, '2024-02-29'),
    (2, '2000-02-29'),
    (3, '2024-04-30');
~~~

Invalid values should be tested individually to verify whether MySQL returns an error or a warning under the active SQL mode. Do not mix valid and invalid values in a single `INSERT` when pinpointing exact failure behavior for each case.

### 6.2. Month-End and Month Addition

Adding one month to a month-end date is not equivalent to adding a fixed number of days:

~~~sql
SELECT DATE_ADD('2024-01-31', INTERVAL 1 MONTH) AS leap_year_result,
       DATE_ADD('2023-01-31', INTERVAL 1 MONTH) AS common_year_result,
       DATE_ADD('2024-03-31', INTERVAL 1 MONTH) AS next_month_result;
~~~

MySQL adjusts the resulting day to the last day of the target month when the original day does not exist in that month. Test days 28, 29, 30, 31, and February to avoid billing due-date or renewal-cycle bugs.

If the domain defines "after 30 days," use `INTERVAL DAY`; if it defines "same day of next month," explicitly specify how nonexistent days are handled. Those two rules are not equivalent.

### 6.3. Start and End of Day, Month, and Year

Boundaries to test:

- `00:00:00` start of day.
- `23:59:59` and `23:59:59.999999` end of day.
- `00:00:00` on the first day of the month.
- Last day of the month and February.
- December 31 rolling over to January 1.
- Leap-year year-end transitions.
- Ranges crossing midnight or New Year's Eve.

When filtering by date, prefer half-open intervals:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2024-03-01 00:00:00'
  AND created_at <  '2024-04-01 00:00:00';
~~~

A `[start, end)` range avoids guessing end-of-day precision and works cleanly with `DATETIME(6)`/`TIMESTAMP(6)`. It also helps the optimizer use an index on the temporal column instead of wrapping the column in `DATE()`.

### 6.4. Zero Values and Invalid Dates

MySQL has SQL modes controlling acceptance of zero dates, zero-in-dates, and invalid dates. Inspect the active configuration:

~~~sql
SELECT @@sql_mode;
~~~

Relevant modes include `STRICT_TRANS_TABLES`, `STRICT_ALL_TABLES`, `NO_ZERO_DATE`, `NO_ZERO_IN_DATE`, and `ALLOW_INVALID_DATES`. Support and mode combinations vary by version; do not assume every server behaves identically.

Values like `'0000-00-00'` or `'2024-00-15'` typically indicate legacy data or conventions for missing data. In new schemas, prefer `NULL` for unknown or inapplicable values, and enforce valid data through constraints and business rules.

When testing invalid data, record both errors and warnings:

~~~sql
INSERT INTO date_probe (id, value_date)
VALUES (10, '2023-02-29');

SHOW WARNINGS;
~~~

The `INSERT` may fail or coerce the value depending on SQL mode and execution method. Verify statement status, actual rows written, and warnings. `INSERT IGNORE` can downgrade errors into warnings and should not be used in baseline validity tests.

## 7. Testing Fractional Seconds

MySQL supports fractional-second precision from 0 to 6:

~~~sql
CREATE TEMPORARY TABLE precision_probe (
    id INT PRIMARY KEY,
    dt0 DATETIME,
    dt3 DATETIME(3),
    dt6 DATETIME(6)
);

INSERT INTO precision_probe (id, dt0, dt3, dt6)
VALUES (
    1,
    '2024-05-01 12:30:45.123456',
    '2024-05-01 12:30:45.123456',
    '2024-05-01 12:30:45.123456'
);

SELECT dt0, dt3, dt6
FROM precision_probe;
~~~

When a column has lower precision than the input value, fractional seconds are rounded or truncated depending on the `TIME_TRUNCATE_FRACTIONAL` SQL mode. Check the mode:

~~~sql
SELECT @@sql_mode;
~~~

Tests should include values near rounding boundaries—such as `.1234`, `.1235`, `.9994`, and `.9995` when storing into `DATETIME(3)`. Verify the read-back value instead of assuming the driver and server always truncate/round identically.

If the application needs microsecond precision, declare `(6)` on the column and check that the Java type and driver preserve that precision. Java `Instant` has nanosecond precision; MySQL temporal columns support at most microseconds. Precision can be reduced on save. Tests must define rounding/truncation rules and compare at the committed precision.

## 8. Testing in Java with java.time

Java provides temporal types with clear semantics:

| Java type | Meaning |
|---|---|
| `LocalDate` | Calendar date, without time or zone |
| `LocalTime` | Wall-clock time, without date or zone |
| `LocalDateTime` | Local date and time, without zone |
| `Instant` | Absolute point on the UTC timeline |
| `OffsetDateTime` | Date and time with a fixed offset |
| `ZonedDateTime` | Date and time with `ZoneId` and time zone rules |
| `Duration` | Time span in seconds/nanoseconds |
| `Period` | Calendar span in years/months/days |

Never use `LocalDateTime` to represent an instant without an accompanying zone convention. `LocalDateTime` cannot disambiguate offsets during a DST overlap.

### 8.1. Checking Gaps and Overlaps with ZoneRules

Java can inspect valid offsets for a local wall-clock time:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

LocalDateTime springGap =
    LocalDateTime.of(2024, 3, 10, 2, 30);

LocalDateTime fallOverlap =
    LocalDateTime.of(2024, 11, 3, 1, 30);

List<ZoneOffset> gapOffsets = rules.getValidOffsets(springGap);
List<ZoneOffset> overlapOffsets = rules.getValidOffsets(fallOverlap);

assertTrue(gapOffsets.isEmpty());
assertEquals(2, overlapOffsets.size());
~~~

Meaning:

- Zero valid offsets: the local datetime falls in a gap.
- One valid offset: the local time is unambiguous.
- Two valid offsets: the local datetime falls in an overlap and an offset must be chosen.

You can inspect the corresponding instants:

~~~java
import java.util.stream.Collectors;

List<Instant> possibleInstants = overlapOffsets.stream()
    .map(offset -> fallOverlap.toInstant(offset))
    .collect(Collectors.toList());

assertEquals(2, possibleInstants.size());
assertNotEquals(possibleInstants.get(0), possibleInstants.get(1));
~~~

The offset-selection policy must be a business decision. Calling `ZonedDateTime.of()` with an ambiguous local datetime applies the API's default rule; do not rely on that default if the domain needs to distinguish the earlier and later occurrences.

### 8.2. Using a Fixed Clock in Tests

Never let tests depend on the host machine's wall clock:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2024-11-03T06:30:00Z"),
    ZoneOffset.UTC
);

Instant now = Instant.now(fixedClock);

assertEquals(
    Instant.parse("2024-11-03T06:30:00Z"),
    now
);
~~~

Injecting `Clock` into services lets you deterministically test payment deadlines, token expirations, cutoff dates, and midnight-crossing rules.

### 8.3. Testing Leap Days in Java

~~~java
assertTrue(LocalDate.of(2024, 2, 29).isLeapYear());
assertFalse(LocalDate.of(1900, 1, 1).isLeapYear());
assertTrue(LocalDate.of(2000, 1, 1).isLeapYear());

assertThrows(
    DateTimeException.class,
    () -> LocalDate.of(2023, 2, 29)
);
~~~

Java tests verify the application's calendar logic. You still need MySQL integration tests to verify how the driver binds/extracts values and how the server accepts them.

## 9. Spring Boot, Hibernate, and Connector/J

A Spring Boot system has multiple time zone layers:

1. JVM default time zone.
2. Java types and application conversion logic.
3. Hibernate JDBC time zone.
4. Connector/J connection time zone and session time zone.
5. MySQL global/session time zone.
6. Named time zone rules from JVM, OS, and MySQL time zone databases.

If each layer picks a different value, the same timestamp can be converted twice or displayed offset by hours.

### 9.1. Adopting a UTC Convention for Instants

For domains storing absolute instants, a commonly considered configuration is:

~~~properties
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
~~~

This Hibernate property controls the time zone used when binding/extracting JDBC temporal values that accept a `Calendar`. It does not automatically set MySQL's `@@session.time_zone`.

With MySQL Connector/J 8.0.23+, you can explicitly configure the connection time zone and session synchronization:

~~~text
jdbc:mysql://db.example.net:3306/shop?connectionTimeZone=%2B00:00&forceConnectionTimeZoneToSession=true&preserveInstants=true
~~~

Verify these properties against your exact Connector/J version. `connectionTimeZone` defines the time zone the driver uses for conversions; `forceConnectionTimeZoneToSession` tells the driver to set the matching session time zone; `preserveInstants` controls how the driver preserves instants when converting between Java and MySQL temporal types.

This is not a mandatory configuration for every application. Verify the actual behavior of your Java types, SQL types, driver version, and server version. Never enable multiple time zone properties without understanding each layer's effect.

### 9.2. Verifying Session Time Zone Through the Connection Pool

When using HikariCP or another connection pool, physical connections are reused. Check the session time zone on a pooled connection:

~~~java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(
         "SELECT @@session.time_zone, @@global.time_zone")) {

    if (rs.next()) {
        String sessionZone = rs.getString(1);
        String globalZone = rs.getString(2);
        assertEquals("+00:00", sessionZone);
    }
}
~~~

Expected values must match the application configuration. If a request alters the session zone, restore it before returning the connection to the pool. Even better, keep one fixed convention across all connections and never switch time zones per business operation.

Connection initialization SQL can be configured in the pool to initialize the session, provided you verify it runs on every new physical connection and is not later overwritten by application code. If Connector/J already uses `forceConnectionTimeZoneToSession`, avoid setting two conflicting mechanisms.

### 9.3. Storing Appointments and Regional Time Zones

For appointments, store both the instant and the `ZoneId` if regional semantics must be preserved:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_at_utc TIMESTAMP(6) NOT NULL,
    zone_id VARCHAR(64) NOT NULL,
    local_start DATETIME(6) NOT NULL
);
~~~

Exact design depends on the domain:

- `starts_at_utc` identifies the resolved instant.
- `zone_id` stores the region for location-based display and interpretation.
- `local_start` preserves the user's selected wall-clock time for auditing or rule-change handling.

For recurring schedules such as "09:00 every Monday in Ho Chi Minh City," storing a single instant is insufficient to generate future occurrences. Store the recurrence rule, local time, and `ZoneId`, then compute the instant for each occurrence using active time zone rules.

If time zone laws change after a schedule was created, the business must decide whether to keep the old instant or keep the wall-clock time under the new rules. That is a business decision, not something column types alone can solve.

## 10. Integration Testing with Real MySQL

Mock repository tests cannot verify conversion behavior of MySQL Server and Connector/J. Use MySQL Testcontainers or a test instance equivalent to production.

Recommended steps:

1. Select the exact MySQL version and Connector/J version.
2. Specify the SQL mode and session time zone.
3. Verify named time zone tables are populated if tests use `ZoneId`.
4. Create tables with `DATE`, `DATETIME(6)`, `TIMESTAMP(6)`, and `TIME(6)`.
5. Write values via JDBC/Hibernate.
6. Read back through the same connection and a connection with a different session zone.
7. Assert values against business expectations, not merely formatted display strings.
8. Test fractional seconds, leap days, year-ends, gaps, and overlaps.
9. Re-run tests after upgrading Connector/J, Hibernate, or MySQL versions.

Example checking named time zone availability before running tests:

~~~sql
SELECT CONVERT_TZ(
    '2024-03-10 07:30:00',
    '+00:00',
    'America/New_York'
) IS NOT NULL AS timezone_data_available;
~~~

If the result is `0`, tests relying on named zones lack valid prerequisites. Load the time zone tables or mark the test environment as missing a dependency; never skip the test and report it as passing.

### 10.1. Suggested Test Data Table

~~~sql
CREATE TABLE temporal_cases (
    case_id INT PRIMARY KEY,
    date_value DATE NULL,
    time_value TIME(6) NULL,
    datetime_value DATETIME(6) NULL,
    timestamp_value TIMESTAMP(6) NULL
);
~~~

Dataset should include:

| Group | Representative values |
|---|---|
| Regular date | `2024-06-15` |
| Leap day | `2024-02-29` |
| Non-leap day | `2023-02-28` |
| Month-end | `2024-01-31`, `2024-02-29` |
| Year-end | `2024-12-31 23:59:59.999999` |
| Year-start | `2025-01-01 00:00:00.000000` |
| Midnight | `00:00:00` |
| End of day | `23:59:59.999999` |
| Fractional seconds | `.000001`, `.123456`, `.999999` |
| DST gap | `2024-03-10 02:30` `America/New_York` |
| DST overlap | `2024-11-03 01:30` `America/New_York` with both offsets |
| Outside `TIMESTAMP` range | Dates before 1970 or after 2038 |
| Invalid values | `2023-02-29`, month 13, day 0, zero date |

Not every value in the table should insert successfully. Several are negative tests verifying that MySQL rejects them or emits warnings according to SQL mode and column type.

## 11. Common Testing Pitfalls

| Symptom | Possible cause | How to diagnose |
|---|---|---|
| `TIMESTAMP` shifted by several hours | Session time zone or JDBC time zone differs from UTC | Inspect `@@session.time_zone`, JVM zone, and driver properties |
| `DATETIME` unchanged when session zone changes | Literal component storage of `DATETIME` | Expected behavior; check if the app wrongly assumes it is an instant |
| `CONVERT_TZ` returns `NULL` | Named zone missing or time zone tables unpopulated | Check `mysql.time_zone_name` and zone name |
| Appointments shift during DST | `LocalDateTime` lacks `ZoneId` or gap/overlap unhandled | Check `ZoneRules` and resolution policy |
| February 29 rejected | Non-leap year or strict SQL mode | Check input data, leap year, and `@@sql_mode` |
| Invalid dates accepted in tests | SQL mode differs from production or `ALLOW_INVALID_DATES` enabled | Align SQL mode and check warnings |
| Microseconds lost | Low-precision column, driver, or mapping truncating precision | Inspect `DATETIME(6)`/`TIMESTAMP(6)`, JDBC type, and read-back values |
| Test results depend on host machine | Using system default time zone or wall clock | Pin `Clock`, JVM zone, and session zone |
| Passes locally but fails in container | MySQL image lacks time zone tables or uses different SQL mode | Initialize test fixtures and verify container config |
| Post-2038 dates fail to write to `TIMESTAMP` | Exceeds `TIMESTAMP` range | Evaluate `DATETIME` with an appropriate time zone convention |

## 12. Recommended Test Matrix

A thorough test suite combines multiple axes instead of testing only one time zone:

| Axis | Cases |
|---|---|
| MySQL types | `DATE`, `TIME`, `DATETIME(0/3/6)`, `TIMESTAMP(0/3/6)` |
| Session zones | `+00:00`, `+05:30`, `+07:00`, `SYSTEM`, named zones |
| DST | Non-DST zones, gaps, overlaps, before/after transitions |
| Calendar | Leap years, month-ends, year-ends, midnight, invalid values |
| SQL mode | Production config, strict, zero-date, and invalid-date modes if supported |
| Java types | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime` |
| Driver | Current Connector/J version and target upgrade version |
| ORM | Current Hibernate version and target version |
| Connections | Fresh connections, pooled connection reuse, reconnects |
| Data paths | Direct JDBC, Hibernate/JPA, native queries, stored routines if any |

Each test case should document:

- Input value and Java type.
- Column SQL type and precision.
- JVM time zone.
- Connector/J connection time zone.
- MySQL session time zone.
- SQL mode and time zone data version.
- Stored value and read-back value.
- Expected result and any acceptable tolerance.

## 13. Pre-Release Checklist

- [ ] Classified data as calendar date, local time, duration, or instant.
- [ ] Selected `DATE`, `TIME`, `DATETIME`, or `TIMESTAMP` matching semantics.
- [ ] Defined required fractional-second precision.
- [ ] Verified temporal type ranges against historical/future data.
- [ ] Checked JVM time zone, Hibernate JDBC time zone, and Connector/J properties.
- [ ] Verified `@@session.time_zone` on the connection pool.
- [ ] Populated and verified named time zone tables when using `CONVERT_TZ` with named zones.
- [ ] Tested DST gaps and overlaps using a DST-observing zone.
- [ ] Tested leap days, month-ends, year-ends, and midnight.
- [ ] Tested zero dates, invalid dates, and production's SQL mode.
- [ ] Tested fractional seconds at actual production precision.
- [ ] Used a fixed `Clock` in unit tests.
- [ ] Ran integration tests on production-aligned MySQL and Connector/J.
- [ ] Decided how recurring schedules behave when time zone rules change.
- [ ] Checked logs, warnings, and sensitive data in test output.

## 14. Self-Check

1. How do `TIMESTAMP` and `DATETIME` differ when the session time zone changes?
2. Why is `DATE` a better fit than `TIMESTAMP` for a date of birth?
3. Why cannot a fixed offset `-05:00` replace `ZoneId` `America/New_York`?
4. How do a DST gap and a DST overlap differ?
5. Why can local datetime `2024-11-03 01:30` in New York represent two instants?
6. What prerequisite does MySQL need for `CONVERT_TZ` to resolve named zones?
7. Why does changing global `time_zone` not automatically alter existing sessions in a connection pool?
8. Why must both the year 2000 and the year 1900 be tested when validating leap-year logic?
9. How does fractional-second precision affect round-trips between Java and MySQL?
10. Design a test for a recurring appointment at `02:30` in New York, covering both spring and autumn DST transition dates.

When testing dates and times, pin environmental factors and define data semantics before comparing results. For instants, standardize on UTC across the application, driver, and session; for local schedules, preserve the `ZoneId` and explicitly define how nonexistent or repeated hours are handled. Finally, run integration tests against real MySQL to catch session time zone, time zone table, SQL mode, and precision discrepancies that isolated unit tests cannot cover.
