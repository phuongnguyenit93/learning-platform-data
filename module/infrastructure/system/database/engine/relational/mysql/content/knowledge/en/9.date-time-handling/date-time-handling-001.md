# Distinguishing Calendar Dates, Times of Day, Durations, and Instants

An order has an expected delivery date, a store has an opening time, a login session has a start instant, and a report needs to calculate the number of processing minutes. These values all relate to date and time, yet carry different meanings. Using a single data type for everything can cause the application to miscalculate durations, shift hours across time zones, or fail to distinguish two instants occurring during a Daylight Saving Time transition.

In the **DATABASE_MYSQL** module, proper date and time handling is foundational for orders, appointments, payments, reporting, and operations. This lesson distinguishes calendar dates, times of day, durations, and instants; then maps them to `DATE`, `TIME`, `DATETIME`, `TIMESTAMP`, time zones, and Java/JDBC.

## 1. Four Different Meanings of Date and Time Data

Before choosing an SQL type, determine what the data represents:

| Meaning | Description | Business Example | Typical MySQL Type |
|---|---|---|---|
| Calendar date | A date on a calendar, not necessarily tied to a time or time zone | Date of birth, contract signing date, holiday | `DATE` |
| Time of day | A position on a clock within a day | Store opens at 08:30, appointment at 14:00 | `TIME` if only hour/minute/second are needed |
| Duration | An amount of elapsed time between two points | A job runs for 90 minutes, order processing time | Integer in a chosen unit, or `TIME` for suitable short intervals |
| Instant | A specific point on the timeline, convertible to UTC | When an order was created, when a payment transaction occurred | Typically `TIMESTAMP` with a clear time zone convention |

In addition, a **date/time range** in a query is typically expressed using two boundary points—start and end—for example from the start of day 10 to the start of day 11. It is not a separate data type; it is a range predicate on `DATE`, `DATETIME`, or `TIMESTAMP`.

Examples:

- Date of birth `1995-04-18` is a calendar date. There is no need to convert a date of birth to UTC.
- Store opening at `08:30:00` is a time of day. The store can open at that same clock time every day.
- A task running for `5400` seconds is a duration. It is not the time `01:30:00` after midnight.
- A payment occurring at `2026-11-19T02:15:30Z` is an instant. A server in Vietnam may display it as `09:15:30` in UTC+07:00.

## 2. Date and Time Types in MySQL

MySQL provides the following primary temporal types:

| Type | Stored Meaning | Common Value Range | Automatically Converted by Time Zone? |
|---|---|---|---|
| `DATE` | Calendar date: year, month, day | `1000-01-01` to `9999-12-31` | No |
| `TIME` | Hour/minute/second or elapsed time | `-838:59:59` to `838:59:59` | No |
| `DATETIME` | Calendar date and time, without a time zone | `1000-01-01 00:00:00` to `9999-12-31 23:59:59` | No |
| `TIMESTAMP` | Instant converted via UTC on write/read | `1970-01-01 00:00:01` UTC to `2038-01-19 03:14:07` UTC in MySQL 8.0 | Yes, according to the session time zone |

The `TIME`, `DATETIME`, and `TIMESTAMP` types support fractional seconds with a precision from 0 to 6 digits—for example, `DATETIME(3)` stores milliseconds and `DATETIME(6)` stores microseconds. If no precision is specified, the default is 0.

### `DATE` — Calendar Date

Use `DATE` when only the date matters, not the time within the day:

```sql
CREATE TABLE employees (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    birth_date DATE,
    contract_date DATE NOT NULL,
    PRIMARY KEY (id)
);
```

Avoid storing a date of birth as `DATETIME` set to `00:00:00` when the business domain has no time-of-day meaning. `DATE` expresses the intent clearly and avoids unnecessary time zone handling.

### `TIME` — Time of Day or Elapsed Time

`TIME` is commonly used for opening hours, closing hours, or a daily recurring clock time:

```sql
CREATE TABLE store_hours (
    store_id BIGINT UNSIGNED NOT NULL,
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    PRIMARY KEY (store_id)
);
```

MySQL `TIME` has a range wider than 24 hours and can be negative, so it can also represent short durations. For example, `TIME '36:00:00'` means 36 hours, not 12:00 PM the next day. Do not use `TIME` as an instant because it lacks a date and time zone.

### `DATETIME` — Calendar Date and Time

`DATETIME` stores the date and time exactly as provided, without automatic conversion for the session time zone:

```sql
CREATE TABLE appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    starts_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
```

This type fits an appointment scheduled in a facility's local time, provided the application also stores or knows the applicable time zone. For instance, an appointment at 09:00 in Ho Chi Minh City remains 09:00 local time even if the viewer is in another country.

Because `DATETIME` does not retain an offset or time zone name, if an appointment must be interpreted by geographic region, store an additional zone ID such as `Asia/Ho_Chi_Minh` in a separate column or appropriate metadata.

### `TIMESTAMP` — Instant

`TIMESTAMP` represents an instant. On write, MySQL converts the value from the session time zone to UTC for storage; on read, MySQL converts from UTC back to the current session time zone. Consequently, the same stored value can display differently in two sessions with different `time_zone` settings.

```sql
CREATE TABLE payments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(15,2) NOT NULL,
    paid_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
```

This is a common choice for `created_at`, `updated_at`, or payment timestamps when the system enforces a consistent time zone convention. Keep in mind that `TIMESTAMP` has a narrower year range than `DATETIME`; if the business domain requires dates outside `TIMESTAMP`'s range, consider `DATETIME` with an explicit UTC storage convention.

## 3. How Does `DATETIME` Differ from `TIMESTAMP`?

Both types share the common display format `YYYY-MM-DD HH:MM:SS`, yet their meaning and behavior differ:

| Criterion | `DATETIME` | `TIMESTAMP` |
|---|---|---|
| Meaning | Date and time on a calendar | An instant on the timeline |
| Converted by session `time_zone` | No | Yes, on write and read |
| Stores offset or time zone name | No | Does not preserve the original name/offset; stores an instant via UTC |
| Year range | 1000 to 9999 | `1970-01-01 00:00:01` UTC to `2038-01-19 03:14:07` UTC in MySQL 8.0 |
| Used for | Local appointment times, scheduled working hours | Record creation timestamps, payments, system events |

Example with `DATETIME`:

```sql
SET time_zone = '+00:00';
SELECT CAST('2026-11-19 09:00:00' AS DATETIME) AS local_schedule;

SET time_zone = '+07:00';
SELECT CAST('2026-11-19 09:00:00' AS DATETIME) AS local_schedule;
```

The `DATETIME` value remains `2026-11-19 09:00:00` in both sessions. MySQL does not automatically add or subtract 7 hours for `DATETIME`.

Example with `TIMESTAMP`:

```sql
CREATE TEMPORARY TABLE timestamp_demo (
    event_at TIMESTAMP NOT NULL
);

SET time_zone = '+00:00';
INSERT INTO timestamp_demo VALUES ('2026-11-19 02:00:00');
SELECT event_at FROM timestamp_demo;

SET time_zone = '+07:00';
SELECT event_at FROM timestamp_demo;
```

The value read in the UTC+07:00 session will display `2026-11-19 09:00:00`, because the same instant is converted to the session time zone. This example uses a temporary table so it can run in a test session without creating a permanent business table.

## 4. MySQL Time Zones

MySQL has several time zone settings:

| Variable | Meaning |
|---|---|
| `system_time_zone` | The operating system time zone detected by the server at startup |
| GLOBAL `time_zone` | Default used for new sessions |
| SESSION `time_zone` | Time zone of the current connection; affects `TIMESTAMP` conversions and related date/time functions |

Inspect them:

```sql
SELECT
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

A value of `SYSTEM` in `time_zone` means the session uses the system time zone. For an application to handle instants consistently, a common convention is to set the MySQL session to UTC:

```sql
SET time_zone = '+00:00';
```

The `+00:00` offset does not require time zone tables. If you use region names such as `Asia/Ho_Chi_Minh`, the server must have time zone tables loaded and kept up to date. Geographic region names carry historical rules and can change according to IANA data; fixed offsets like `+07:00` carry no information about DST rules or future legislative changes.

`SET GLOBAL time_zone` only sets the default for new connections and does not affect existing sessions. With a connection pool, each connection has its own session; configure the time zone when creating/initializing connections or in the pool's connection checkout setup.

## 5. Daylight Saving Time (DST) and Non-Unique Local Times

Some geographic regions adjust clocks for Daylight Saving Time (DST). When springing forward to summer time, certain local times may not exist; when falling back to standard time, a one-hour interval can occur twice.

Illustrative example in a region with DST:

- When the clock jumps from 01:59 to 03:00, the local time `02:30` does not exist on that day.
- When the clock falls back from 02:00 to 01:00, the local time `01:30` can correspond to two different instants.

A standalone `DATETIME` such as `2026-11-01 01:30:00` cannot tell which occurrence of 01:30 it belongs to if that region repeats the hour. To store local appointments in a DST region, store the local time together with the IANA zone name and rules for handling nonexistent/ambiguous times. To store an event that has already occurred, store the instant in UTC, such as `TIMESTAMP` with a UTC session or `DATETIME` under an explicit UTC convention.

Do not store only `-05:00` or `+07:00` if the business domain needs to know the geographic region. An offset only describes the shift at a specific moment; `America/New_York` or `Asia/Ho_Chi_Minh` identifies the region with its corresponding set of time rules.

## 6. Duration and Date/Time Arithmetic

A duration is the amount of time elapsed between two instants. It can be computed from two timestamps in SQL:

```sql
SELECT TIMESTAMPDIFF(SECOND,
    '2026-11-19 09:00:00',
    '2026-11-19 10:30:00') AS elapsed_seconds;
```

The result is `5400` seconds. `TIMESTAMPDIFF(unit, start, end)` returns an integer count in the requested unit; if `MINUTE` is chosen, leftover seconds short of a full minute are truncated.

Common functions:

| Function | Purpose | Example |
|---|---|---|
| `DATEDIFF(end, start)` | Calendar day difference, ignoring the time part | `DATEDIFF('2026-11-20','2026-11-19')` returns `1` |
| `TIMEDIFF(expr1, expr2)` | Difference between two compatible time/datetime values, returns `TIME` | `TIMEDIFF('10:30:00','09:00:00')` returns `01:30:00` |
| `TIMESTAMPDIFF(unit, start, end)` | Difference in the specified unit | `TIMESTAMPDIFF(MINUTE, start, end)` |
| `TIMESTAMPADD(unit, amount, datetime)` | Adds an amount of time to a point | `TIMESTAMPADD(DAY, 7, CURRENT_DATE())` |
| `DATE_ADD(date, INTERVAL expr unit)` | Adds a time interval | `DATE_ADD(CURRENT_DATE(), INTERVAL 1 MONTH)` |

`INTERVAL` in an expression such as `INTERVAL 7 DAY` is not a column type for storing arbitrary durations. It is syntax describing an amount to add to or subtract from a temporal value.

### What Should Be Used to Store Durations?

- For short, well-bounded durations within the `TIME` range, `TIME` or `TIME(3)` can be used.
- For long durations, cumulative time, or when exact units are needed, integers such as `BIGINT` storing milliseconds/microseconds/seconds under a clear convention are typically used.
- For durations with fractional parts or requiring unit conversion, `DECIMAL` in the business unit can be used.

Example storing task duration in milliseconds:

```sql
CREATE TABLE job_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at TIMESTAMP(6) NOT NULL,
    duration_ms BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
);
```

Do not use `TIMESTAMP` to store a duration because a timestamp is a point on the timeline. Likewise, do not use `TIME` for monthly or yearly durations because months and years vary in length.

## 7. Querying by Time Range and Index Usage

When filtering records by date, use a half-open interval: inclusive of the start instant and exclusive of the end instant. For example, retrieving all orders on 2026-11-19:

```sql
SELECT id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

The condition `>= start AND < next_start` avoids guessing end-of-day values like `23:59:59.999999` and works cleanly across different fractional-second precisions.

If an index exists on `created_at`, direct range filtering typically allows MySQL to perform a range scan. Avoid wrapping an indexed column in a function unnecessarily:

```sql
-- Often prevents effective use of the index on created_at
SELECT *
FROM orders
WHERE DATE(created_at) = '2026-11-19';

-- Use a half-open time range
SELECT *
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

If the column is `TIMESTAMP`, the two literal bounds are interpreted in the session `time_zone`. When generating reports by local day, convert the local day boundaries to the exact start/end instants in that time zone, then query using those instants. Do not assume a day in every region is always exactly 24 hours long when DST applies.

## 8. Formatting and Parsing Date and Time

Standard ISO formats prevent day/month confusion:

- Date: `YYYY-MM-DD`, e.g. `2026-11-19`.
- Date and time: `YYYY-MM-DD HH:MM:SS`, e.g. `2026-11-19 09:15:30`.
- ISO 8601 instant with offset: `2026-11-19T02:15:30Z` or `2026-11-19T09:15:30+07:00`.

In SQL, results can be formatted using `DATE_FORMAT()`:

```sql
SELECT DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_text
FROM orders;
```

`%i` is minutes; `%m` is month. This is a common gotcha because in `DATE_FORMAT`, `%M` is the month name while `%i` is minutes.

To parse a string using a known format, use `STR_TO_DATE()`:

```sql
SELECT STR_TO_DATE('19/11/2026 09:15:30', '%d/%m/%Y %H:%i:%s');
```

Do not rely on ambiguous date formats such as `03/04/2026`, which can be interpreted as April 3 or March 4. At the application layer, use temporal types and parameter binding via JDBC rather than concatenating date/time strings into SQL.

## 9. Current Date/Time and Default Values

MySQL provides functions for retrieving the current date and time:

| Function | Result |
|---|---|
| `CURRENT_DATE()` / `CURDATE()` | Current date in the session time zone |
| `CURRENT_TIME()` / `CURTIME()` | Current time in the session time zone |
| `NOW()` / `CURRENT_TIMESTAMP()` | Current date and time in the session time zone |
| `UTC_DATE()` | Current date in UTC |
| `UTC_TIME()` | Current time in UTC |
| `UTC_TIMESTAMP()` | Current date and time in UTC |

Example automatically recording timestamps on insert/update:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
```

`NOW()` and `CURRENT_TIMESTAMP()` within a single statement normally return the same timestamp captured when the statement begins executing. How `TIMESTAMP` is displayed still depends on the session time zone. If consistent UTC logging is required, set the session to UTC and verify this on application connections.

## 10. Mapping Date and Time Types from Java to MySQL

The Java Time API provides distinct types for each meaning. Choose the Java type matching the column's exact semantics:

| Meaning | Java | Typical MySQL |
|---|---|---|
| Calendar date | `LocalDate` | `DATE` |
| Time of day | `LocalTime` | `TIME` |
| Local date and time without time zone | `LocalDateTime` | `DATETIME` |
| Absolute instant | `Instant` | `TIMESTAMP` under UTC convention |
| Duration | `Duration` | Integer in a fixed unit, or `TIME` if within its valid range |
| Geographic time zone | `ZoneId` | Store an additional zone ID string, e.g. `Asia/Ho_Chi_Minh` |

Example Java entity:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class Appointment {
    private LocalDate appointmentDate;
    private LocalTime startsAt;
    private LocalDateTime localStartsAt;
}
```

For event instants, use `Instant` to preserve absolute meaning:

```java
import java.time.Instant;

public class PaymentEvent {
    private Instant paidAt;
}
```

With JDBC, `LocalDate`, `LocalTime`, and `LocalDateTime` can be bound with `setObject()` on MySQL Connector/J supporting JDBC 4.2. For `Instant`, convert via `Timestamp` and use UTC consistently between the driver and session:

```java
Instant eventTime = Instant.now();
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO audit_events (event_type, created_at) VALUES (?, ?)")) {
    statement.setString(1, "PAYMENT_RECEIVED");
    statement.setTimestamp(2, Timestamp.from(eventTime), utc);
    statement.executeUpdate();
}
```

This example requires importing `java.sql.PreparedStatement`, `java.sql.Timestamp`, `java.util.Calendar`, `java.util.TimeZone`, and `java.time.Instant`. Configure the MySQL session to UTC or configure Connector/J consistently; `Calendar` instructs JDBC to interpret the timestamp value in the specified time zone. When reading back, use `getTimestamp(column, utc).toInstant()` to restore the instant.

For future appointments in a geographic region, do not store only `LocalDateTime` and assume it is an instant. Store the local time alongside the `ZoneId`, then resolve the instant according to the region's rules at the applicable time. DST rules can cause a local time to be skipped or repeated.

## 11. Controlling Invalid Date and Time Data

MySQL can handle invalid dates differently depending on `sql_mode`. Strict mode generally rejects invalid values rather than silently adjusting them or accepting zero dates in certain configurations.

Check it:

```sql
SELECT @@SESSION.sql_mode;
```

Values such as `2026-02-30`, `2026-13-01`, or the zero date `0000-00-00` should not be used as valid business data. Validate input in Java and rely on an appropriate SQL mode so the database rejects invalid data. Do not use a zero date in place of `NULL`: `NULL` indicates unknown or absent data, whereas a zero date is a special value whose behavior depends on configuration.

For data imported from files or legacy systems, determine the format, time zone, and validity before importing. Do not automatically assume a timestamp lacking an offset is UTC or local time if the data source does not specify it.

## 12. Practice Exercises

Perform the following on a test database:

1. Create an employee table with `birth_date DATE`, a store schedule table with `opens_at TIME`, an appointment table with `starts_at DATETIME`, and an events table with `created_at TIMESTAMP`.
2. Run `SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP()` when the session uses `+00:00`, then switch to `+07:00` and compare.
3. Store the same value into `DATETIME` and `TIMESTAMP`, read it back in two sessions with different time zones, and explain why only `TIMESTAMP` changes its displayed value.
4. Compute the duration between two points using `TIMESTAMPDIFF(SECOND, start, end)`; compare with `DATEDIFF()` and `TIMEDIFF()`.
5. Write a query to fetch orders for a single day using `>= start AND < next_start`, then inspect the execution plan with `EXPLAIN` when the column is indexed.
6. Connect via Java, map `LocalDate`, `LocalTime`, `LocalDateTime`, and `Instant`; verify values before and after persistence.
7. Describe how to store a recurring appointment in a DST region using local time and `ZoneId`, and explain why `DATETIME` alone is insufficient.

You have completed this lesson when you can distinguish calendar dates, times of day, durations, and instants; choose `DATE`, `TIME`, `DATETIME`, or `TIMESTAMP` appropriately; understand the effect of the session time zone; and pass dates and times through Java/JDBC without losing their semantics. Always start from business meaning before choosing data types and time zone conventions.
