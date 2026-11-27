# Mapping DATE/TIME/DATETIME/TIMESTAMP and java.time Types

When a Java application reads or writes temporal columns in MySQL, it must distinguish calendar dates, times of day, points on the timeline, and local wall-clock times. The four SQL types DATE, TIME, DATETIME, and TIMESTAMP carry distinct meanings; java.time classes such as LocalDate, LocalTime, LocalDateTime, and Instant also represent different concepts. Choosing the wrong type or leaving JVM, JDBC session, and MySQL timezones inconsistent can cause an application to save one value and read back a different point in time.

MySQL Connector/J supports JDBC 4.2 mapping for java.time types. Mapping must be driven by the column's business semantics, the actual Connector/J version, and the connection's timezone policy. This lesson focuses on choosing types, reading/writing via JDBC, configuring timezones, preserving microsecond precision, and testing edge cases.

## 1. Distinguishing the Semantics of the Four MySQL Temporal Types

| MySQL Type | Data Meaning | Converted by timezone on store/read? | Typical java.time type |
|---|---|---|---|
| DATE | A calendar date, no time component | No | LocalDate |
| TIME | Time of day or a signed elapsed duration | No | LocalTime if the data is genuinely time of day |
| DATETIME | Local date and time, no attached timezone | No | LocalDateTime |
| TIMESTAMP | A point in time converted according to session timezone | Yes; MySQL converts between session timezone and UTC on store/read | LocalDateTime via JDBC; use an explicit conversion policy if working with Instant |

Do not choose columns based solely on Java class names. Ask what the data represents:

- Birth date or invoice date: calendar date, typically DATE and LocalDate.
- Store opening hour: time of day, typically TIME and LocalTime.
- Appointment at 09:30 at a physical location: local time, typically DATETIME and LocalDateTime; if timezone and DST handling are required, store the zone ID alongside it.
- Timestamp when a transaction was recorded system-wide: an instant, typically TIMESTAMP with a controlled UTC store/read convention.
- Processing duration of 27 hours: an elapsed duration, not a clock time; consider storing seconds or microseconds in BIGINT instead of forcing it into LocalTime.

## 2. DATE and LocalDate

MySQL DATE stores year, month, and day without time or timezone. Its natural Java counterpart is java.time.LocalDate.

Example schema:

~~~sql
CREATE TABLE employee (
  employee_id BIGINT PRIMARY KEY,
  birth_date DATE,
  hire_date DATE NOT NULL
);
~~~

Reading with Connector/J:

~~~java
LocalDate birthDate =
    resultSet.getObject("birth_date", LocalDate.class);

LocalDate hireDate =
    resultSet.getObject("hire_date", LocalDate.class);
~~~

Writing with PreparedStatement:

~~~java
String sql = """
    INSERT INTO employee (employee_id, birth_date, hire_date)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, employeeId);
    ps.setObject(2, birthDate);
    ps.setObject(3, LocalDate.now());
    ps.executeUpdate();
}
~~~

LocalDate has no time and no timezone, so there is no need to pass through Instant to store a calendar date. Avoid converting DATE to java.util.Date or Instant when business logic only needs a date: conversion can introduce a timezone and shift the date forward or backward by a day when displayed in another region.

When a date may be unknown, use SQL NULL and check for null in Java. With getObject returning reference types, SQL NULL is normally represented as Java null.

## 3. TIME and LocalTime: Time of Day vs. Duration

MySQL TIME can store negative values and durations exceeding 24 hours; its range is larger than a clock time of day. Therefore, TIME is not always equivalent to LocalTime.

### 3.1. When TIME Represents Time of Day

If a column only contains non-negative times from 00:00 up to before 24:00, it can map to LocalTime:

~~~sql
CREATE TABLE store_hours (
  store_id BIGINT NOT NULL,
  opens_at TIME(6) NOT NULL,
  closes_at TIME(6) NOT NULL,
  PRIMARY KEY (store_id)
);
~~~

~~~java
LocalTime opensAt =
    resultSet.getObject("opens_at", LocalTime.class);

LocalTime closesAt =
    resultSet.getObject("closes_at", LocalTime.class);

ps.setObject(1, LocalTime.of(8, 30));
ps.setObject(2, LocalTime.of(21, 0));
~~~

LocalTime fits wall-clock times such as 08:30 or 21:00. It cannot represent -01:30 or 27:15. If existing data contains such values, do not read directly as LocalTime assuming values stay intact.

### 3.2. When TIME Represents Duration

If TIME is used to represent elapsed duration—such as processing time, wait time, or an offset—define its range and conversion rules explicitly. MySQL TIME has an approximate limit of 838 hours 59 minutes 59 seconds, while some domains may require longer durations.

For durations that can exceed 24 hours, be negative, or require exact arithmetic, a more controllable design is storing seconds or microseconds:

~~~sql
CREATE TABLE job_run (
  job_id BIGINT PRIMARY KEY,
  elapsed_microseconds BIGINT NOT NULL
);
~~~

In Java, convert explicitly:

~~~java
Duration elapsed =
    Duration.ofNanos(elapsedMicroseconds * 1_000L);

long storedMicros = elapsed.toNanos() / 1_000L;
ps.setLong(1, storedMicros);
~~~

This example assumes microsecond values fit without overflowing during multiplication. For very large durations, use overflow-checked arithmetic or keep microsecond values in an appropriate integer type. If storing durations in a TIME column is mandatory, verify how your exact Connector/J version converts that type; you can read TIME as a string and parse it per defined conventions. Never assume the driver maps every TIME value to LocalTime or Duration without data loss.

## 4. DATETIME and LocalDateTime

MySQL DATETIME directly stores year, month, day, hour, minute, second, and optional microseconds. It does not store a timezone, and MySQL does not convert DATETIME according to session time_zone.

The matching Java type is LocalDateTime:

~~~sql
CREATE TABLE appointment (
  appointment_id BIGINT PRIMARY KEY,
  scheduled_at DATETIME(6) NOT NULL,
  location_zone_id VARCHAR(64) NOT NULL
);
~~~

~~~java
LocalDateTime scheduledAt =
    resultSet.getObject("scheduled_at", LocalDateTime.class);

ps.setObject(1, LocalDateTime.of(2026, 11, 20, 9, 30, 0, 123_000_000));
~~~

LocalDateTime represents a wall-clock date and time, but cannot identify a unique instant on the timeline without a timezone. For example, 2026-11-20 09:30 in Ho Chi Minh City and 2026-11-20 09:30 in Tokyo are two different instants.

For location-bound appointments, store DATETIME together with a zone ID, such as Asia/Ho_Chi_Minh. When an instant is needed, the application combines LocalDateTime with ZoneId to construct ZonedDateTime or Instant. This also handles daylight saving time (DST) rules where applicable.

## 5. TIMESTAMP and Timezone Policy

MySQL TIMESTAMP represents a point in time. On write, MySQL converts the value from the session timezone to UTC for storage; on read, MySQL converts from UTC to the session timezone. The column itself does not store the original timezone name or offset.

In JDBC 4.2, the standard type used to read TIMESTAMP via getObject is LocalDateTime. That means the returned value contains date/time fields expressed in the timezone currently used by the connection; it does not carry a zone ID of its own.

~~~sql
CREATE TABLE audit_event (
  event_id BIGINT PRIMARY KEY,
  occurred_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
~~~

~~~java
LocalDateTime occurredAt =
    resultSet.getObject("occurred_at", LocalDateTime.class);
~~~

If Java business logic works with Instant, establish a clear convention, such as all MySQL sessions using UTC. Then convert Instant to LocalDateTime in UTC before writing, and interpret the retrieved LocalDateTime as UTC:

~~~java
Instant eventInstant = Instant.now();
LocalDateTime utcValue =
    LocalDateTime.ofInstant(eventInstant, ZoneOffset.UTC);

ps.setObject(1, utcValue);

LocalDateTime storedUtc =
    resultSet.getObject("occurred_at", LocalDateTime.class);
Instant readInstant =
    storedUtc.toInstant(ZoneOffset.UTC);
~~~

This example is valid only when the connection genuinely uses UTC and Connector/J settings do not apply a different conversion rule. Verify the session timezone after borrowing a connection from the pool and test with your actual driver version.

Never write LocalDateTime.now() in the JVM's default timezone into TIMESTAMP assuming MySQL knows that timezone. LocalDateTime carries no offset; if the application needs to represent an instant, convert explicitly from Instant using the chosen zone.

## 6. JDBC 4.2 and java.time APIs in Connector/J

Modern Connector/J supports reading/writing java.time types via ResultSet.getObject and PreparedStatement.setObject. Common mappings:

| SQL Type | Read with | Write with |
|---|---|---|
| DATE | getObject(column, LocalDate.class) | setObject(index, LocalDate) |
| TIME (time of day) | getObject(column, LocalTime.class) | setObject(index, LocalTime) |
| DATETIME | getObject(column, LocalDateTime.class) | setObject(index, LocalDateTime) |
| TIMESTAMP | getObject(column, LocalDateTime.class) per session timezone | setObject(index, LocalDateTime) per agreed timezone policy |

Complete query example:

~~~java
String sql = """
    SELECT birth_date, opens_at, scheduled_at, occurred_at
    FROM event_sample
    WHERE event_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            LocalDate birthDate =
                rs.getObject("birth_date", LocalDate.class);
            LocalTime opensAt =
                rs.getObject("opens_at", LocalTime.class);
            LocalDateTime scheduledAt =
                rs.getObject("scheduled_at", LocalDateTime.class);
            LocalDateTime occurredAt =
                rs.getObject("occurred_at", LocalDateTime.class);
        }
    }
}
~~~

java.sql.Date, java.sql.Time, and java.sql.Timestamp still appear in older JDBC applications. They are legacy types with differing conversion rules; Timestamp can also interact with timezones when converting to or from other Java types. When modernizing, standardize reads/writes on java.time and avoid mixing legacy and modern APIs in the same data path without testing.

When legacy APIs must be used, overloads such as getTimestamp(column, calendar) or setTimestamp(index, timestamp, calendar) let you specify a Calendar timezone. This provides clearer control than relying on the JVM default timezone, though you still need to test alongside preserveInstants and other Connector/J properties of your running version.

## 7. Configuring Timezones for Connector/J and MySQL Sessions

There are three timezone layers to distinguish:

1. JVM default timezone: default timezone of the Java process.
2. Connector/J connection timezone: timezone the driver uses while converting temporal values.
3. MySQL session time_zone: timezone applied to session functions and TIMESTAMP conversions.

Check on an actual connection:

~~~sql
SELECT
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW(6) AS session_now,
  UTC_TIMESTAMP(6) AS utc_now;
~~~

NOW() and CURRENT_TIMESTAMP return time in the session timezone. UTC_TIMESTAMP() returns UTC. If these values disagree with application conventions, fix configuration instead of adding/subtracting hours inside individual SQL queries.

Connector/J offers temporal connection properties such as:

| Property | Role to understand |
|---|---|
| connectionTimeZone | Timezone the driver uses when converting temporal values |
| forceConnectionTimeZoneToSession | Instructs the driver to set the chosen timezone on the MySQL session |
| preserveInstants | Controls how instants are preserved during temporal value conversion |
| treatMysqlDatetimeAsTimestamp | Affects how the driver interprets DATETIME in certain conversions |

Property names, value types, defaults, and behavior can vary across Connector/J versions. Read the documentation for the exact artifact in use before adding them to configuration. Never copy a URL from another driver version assuming every property behaves identically.

If the entire system standardizes on UTC, a configuration might specify:

~~~properties
spring.datasource.url=jdbc:mysql://mysql.internal.example:3306/appdb?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

This is a policy example, not a mandatory setting for every application. Confirm the property is supported in your Connector/J version, verify @@session.time_zone after opening a connection, and ensure the pool applies the configuration to every new connection.

With HikariCP, connectionInitSql can set session state if deployment policy requires it:

~~~yaml
spring:
  datasource:
    hikari:
      connection-init-sql: SET time_zone = '+00:00'
~~~

Do not set session timezone on one connection and assume other connections in the pool are updated. Every new physical connection must be initialized consistently. If an application changes timezone mid-request, restore session state before returning the connection to the pool.

## 8. Fractional Seconds Precision

MySQL supports fractional seconds precision from 0 to 6 for TIME, DATETIME, and TIMESTAMP:

| Declaration | Precision |
|---|---|
| DATETIME or DATETIME(0) | Seconds |
| DATETIME(3) | Milliseconds |
| DATETIME(6) | Microseconds |
| TIMESTAMP(6) | Microseconds |
| TIME(6) | Microseconds |

Java LocalTime and LocalDateTime support nanoseconds, but MySQL stores at most microseconds. Writing values with sub-microsecond nanoseconds cannot preserve full precision. Whether rounding or truncation occurs depends on column type, SQL mode, and conversion path; do not assume every write path behaves identically.

Microsecond column example:

~~~sql
CREATE TABLE measurement (
  measurement_id BIGINT PRIMARY KEY,
  measured_at DATETIME(6) NOT NULL
);
~~~

~~~java
LocalDateTime measuredAt =
    LocalDateTime.of(2026, 11, 19, 10, 15, 30, 123_456_000);
ps.setObject(1, measuredAt);
~~~

When comparing timestamps after writing, normalize precision to microseconds. If the system requires milliseconds, use (3) columns and define rounding rules explicitly. Never use equality on nanosecond LocalDateTime when the database stored reduced precision.

## 9. DST, Local Timezones, and Appointments

DST can create local wall-clock times that either do not exist or occur twice. For example, when clocks spring forward, an hour is skipped; when clocks fall back to standard time, an hour repeats.

LocalDateTime alone cannot distinguish two occurrences of the same local time. When business logic stores appointments in DST-observing locations, store:

- The local date-time chosen by the user.
- Zone ID such as Europe/Berlin or America/New_York.
- Policy for handling non-existent or ambiguous times.
- Resolved Instant after applying timezone rules, if an immutable historical point is needed.

Example:

~~~java
LocalDateTime localAppointment =
    LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");

List<ZoneOffset> validOffsets =
    zone.getRules().getValidOffsets(localAppointment);

if (validOffsets.isEmpty()) {
    throw new IllegalArgumentException(
        "Local time does not exist due to DST transition");
}

if (validOffsets.size() > 1) {
    // Business rule needed to choose earlier or later offset.
}
~~~

Do not store a timezone only in server config and omit the zone ID per event. An appointment may need to preserve its local wall-clock time even if the location's DST rules change in the future.

## 10. Special Data Cases

When designing schemas and tests, watch out for:

- SQL NULL: distinct from default temporal values; use explicit nullability and check null in Java.
- Zero dates: values like 0000-00-00 or invalid dates depend on SQL mode and driver config. Cleanse data and avoid relying on silent zero-date-to-null conversion.
- Boundary values: test DATE, DATETIME, TIMESTAMP, and TIME limits for your MySQL version.
- Fractional seconds: test precisions 0, 3, and 6; verify rounding/truncation behavior.
- Leap day: test February 29 in leap years.
- Timezone offsets: test UTC and non-UTC sessions to verify TIMESTAMP converts per convention.
- DST: test skipped hours and repeated hours in DST-observing regions.
- Negative/long TIME: do not map to LocalTime if values lie outside the time-of-day range.
- Connection pools: check session timezone on fresh connections, reused connections, and after reconnects.

zeroDateTimeBehavior is a Connector/J property related to handling zero dates in certain versions. Check the documentation for the driver in use and define an explicit policy; never use this option to mask invalid date data without investigating its source.

## 11. Common Mapping Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Read timestamps shifted by hours | Session timezone, JVM timezone, or Connector/J conversion inconsistent | Check @@session.time_zone, driver properties, and UTC convention |
| Date shifted forward or backward by a day | DATE unnecessarily converted through instant/timezone | Use LocalDate directly |
| DATETIME shifts when session timezone changes | Application or driver interpreting DATETIME as timestamp | Use LocalDateTime and check treatMysqlDatetimeAsTimestamp |
| TIME throws errors when read as LocalTime | Negative value or exceeds 24 hours | Treat TIME as duration; read/parse per convention or store microseconds |
| Microseconds lost | Low column precision or Java/JDBC passing through millisecond-only type | Use (6) and java.time APIs; run round-trip tests |
| Different results across connection pool members | Session state not initialized consistently | Configure timezone per physical connection and re-verify |
| Zero date errors | Legacy invalid data or stricter SQL mode/driver handling | Cleanse data and define an explicit zero-date policy |

When investigating, log the SQL value, received Java type, JVM timezone, session timezone, Connector/J version, and relevant connection properties together. Looking solely at formatted log strings rarely reveals which layer performed the conversion.

## 12. Round-Trip Test Suite

A mapping test suite should write values via PreparedStatement, read them back via ResultSet, and compare using exact semantics:

1. DATE: compare LocalDate directly.
2. TIME used as clock time: compare LocalTime within 00:00–23:59:59.999999.
3. TIME used as duration: test negative values and values above 24 hours per defined parsing logic.
4. DATETIME: compare timezone-less LocalDateTime.
5. TIMESTAMP: compare Instant after converting according to the agreed session timezone.
6. Precision: normalize nanoseconds to microseconds before comparing.
7. NULL and zero dates: verify explicit policy behavior.
8. Pool/reconnect: rerun tests across multiple physical connections and after connection recreation.

Example session inspection query:

~~~sql
SELECT
  @@session.time_zone,
  NOW(6),
  UTC_TIMESTAMP(6),
  CURRENT_TIMESTAMP(6);
~~~

Store query results alongside test reports to detect configuration drift between environments.

## 13. Self-Check Questions

1. Why does DATE map naturally to LocalDate without a timezone?
2. What values can MySQL TIME store that LocalTime cannot represent?
3. How do DATETIME and TIMESTAMP differ when the session timezone changes?
4. Why does MySQL TIMESTAMP not store the original timezone name or offset?
5. If an application uses Instant while JDBC returns LocalDateTime, what conversion convention is needed?
6. How do Connector/J connectionTimeZone and MySQL session time_zone differ in role?
7. Why do Java nanoseconds not mean MySQL stores nanoseconds?
8. When storing appointments in DST-observing regions, why should you store ZoneId or an offset policy?

Accurate temporal mapping starts from data semantics. Use LocalDate for calendar dates, LocalTime for clock times, LocalDateTime for local wall-clock times, and an explicit timezone convention for instants. Combining proper type selection with Connector/J configuration, session timezones, and round-trip tests prevents shifted timestamps, lost precision, and misinterpreted data.
