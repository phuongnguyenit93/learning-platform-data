# Mapping DATE/TIMESTAMP to java.time Types and Handling Timezones

When Java accesses Oracle Database via JDBC, date and time mapping must be designed around data semantics rather than SQL type names alone. Oracle has several date/time storage types with different precision and timezone semantics; Java also has several types in the java.time package. Picking the wrong type can drop the time component, truncate fractional seconds, shift instants across timezones, or produce inconsistent displays across environments.

Key principles:

- Oracle DATE stores date and time to the second, without a timezone. Despite the name DATE, it does not hold calendar date alone.
- Oracle TIMESTAMP stores date and time with fractional seconds, without a timezone.
- TIMESTAMP WITH TIME ZONE stores date/time together with timezone/offset information, suitable when identifying an instant along with its offset or region.
- TIMESTAMP WITH LOCAL TIME ZONE normalizes data to the database timezone when stored and displays it in the session timezone when read; the value itself does not retain each row's original timezone.
- LocalDate fits calendar dates without time; LocalDateTime fits date/time without timezone; OffsetDateTime represents date/time with an offset; Instant represents an absolute point on the timeline.
- You must control the session timezone of every JDBC connection, especially when using TIMESTAMP WITH LOCAL TIME ZONE or SQL functions that depend on session timezone.

## 1. Date/time models in Oracle and Java

### 1.1. Oracle DATE is not like java.sql.Date

Oracle DATE contains year, month, day, hour, minute, and second components. Fractional precision is one second; it contains no fractional seconds and stores no timezone.

For example, an Oracle DATE value can be:

    2026-11-14 21:19:35

It holds both date and time. Therefore, mapping Oracle DATE to java.sql.Date can lose hour, minute, and second information because java.sql.Date is designed for date-only SQL DATE semantics. When the full Oracle DATE value must be preserved, java.sql.Timestamp in legacy JDBC APIs or LocalDateTime in java.time APIs is typically used.

Do not infer from the name DATE that a column definitely contains only dates. Verify the data contract and actual column values before changing mappings.

### 1.2. Oracle TIMESTAMP

Oracle TIMESTAMP stores year, month, day, hour, minute, second, and fractional seconds. Fractional second precision can be configured from 0 to 9 digits; the default is usually 6.

Example:

    TIMESTAMP(6)
    2026-11-14 21:19:35.123456

TIMESTAMP contains no timezone or offset. The value is purely a local date-time according to application convention. If the same TIMESTAMP is interpreted in two different timezones, the database lacks sufficient information to know whether it represents the same instant or two different instants.

### 1.3. TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE (TSTZ) stores date/time along with timezone information, which can be an offset or a timezone region. Example:

    2026-11-14 21:19:35.123456 +07:00

or a value bound to a timezone region such as Asia/Ho_Chi_Minh.

This type is suitable when retaining the entered offset/timezone and identifying the corresponding instant is required. Oracle can store timezone region information if supplied as a region; how the Java driver represents the value when read must be verified per driver version.

Java OffsetDateTime is the natural java.time type for representing date/time with an offset. When converting to Instant, the application preserves the absolute point in time but loses the timezone region name like Asia/Ho_Chi_Minh. If business rules must also store the user-selected timezone region, store ZoneId separately or add a dedicated column for the region ID.

### 1.4. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE (TSLTZ) behaves differently from TSTZ:

- Oracle normalizes the value to the database timezone when storing.
- When queried, Oracle converts the value to the current session's session timezone.
- The returned value does not retain the original timezone/offset entered per row.

For example, the same instant can display differently when two sessions have different SESSIONTIMEZONE settings. This behavior is intentional for this data type.

TSLTZ is useful when an application wants to store instants and display them in the session's timezone. However, because the original timezone is not preserved per row, it is unsuitable if business logic must know which region the user entered the time in.

### 1.5. Comparison table of SQL types and java.time

| Oracle SQL type | Content | Typically suited Java type | Notes |
|---|---|---|---|
| DATE | Date and time to the second, no timezone | LocalDateTime | Avoid java.sql.Date if time must be preserved |
| TIMESTAMP(p) | Date/time with fractional seconds, no timezone | LocalDateTime | Does not identify an instant without timezone convention |
| TIMESTAMP WITH TIME ZONE | Date/time with offset/region | OffsetDateTime | Convert to Instant for UTC instant; store ZoneId separately if region name is needed |
| TIMESTAMP WITH LOCAL TIME ZONE | Instant normalized to DBTIMEZONE, displayed in SESSIONTIMEZONE | LocalDateTime in session timezone or suitable driver mapping | Requires fixing session timezone; does not retain original input timezone |
| DATE used only for calendar dates | Oracle still has a time component | LocalDate per application contract | Must ensure time is always midnight and no data is lost |

This is a type selection guide based on data semantics. Direct getObject/setObject support depends on the Oracle JDBC driver version and exact column type; test on your deployed ojdbc version.

## 2. Choosing Java types by business meaning

### 2.1. LocalDate: calendar date, no time

Use LocalDate for concepts such as birth date, calendar effective date, holiday, or closing date where time of day has no meaning.

Example:

    LocalDate dueDate = LocalDate.of(2026, 12, 31);

If an Oracle column is DATE yet used as a calendar date, establish a rule that the time component is always 00:00:00. You can check existing data:

    SELECT COUNT(*) AS rows_with_time
    FROM contract
    WHERE start_date <> TRUNC(start_date);

If the result is greater than 0, the column contains time components; switching to LocalDate may lose information. Do not change mappings before confirming the data truly has date-only semantics.

### 2.2. LocalDateTime: date/time without timezone

Use LocalDateTime when business logic stores a calendar date and time not tied to a specific timezone, such as a store's opening hour, local calendar appointment, or business timestamp within a system with a single timezone convention.

LocalDateTime is not an instant. The value 2026-11-14T09:00 cannot identify a specific UTC instant without knowing which timezone or offset applies.

Oracle DATE and TIMESTAMP without timezone are commonly mapped to LocalDateTime to preserve date and time without arbitrarily applying a timezone.

### 2.3. Instant: absolute point in time

Instant represents a point on the UTC timeline. Use it for event timestamps, business logs, record creation times, or event instants needing comparison across systems in multiple timezones.

Example:

    Instant createdAt = Instant.now();

If the database stores it in a non-timezone TIMESTAMP, the application must enforce an explicit convention that values are written in UTC. Column names like CREATED_AT_UTC clarify the contract, though column names do not convert timezones automatically. Both writers and readers must follow the same convention.

If the database must explicitly store timezone/offset alongside the value, consider TIMESTAMP WITH TIME ZONE and OffsetDateTime rather than relying on an implicit convention on TIMESTAMP.

### 2.4. OffsetDateTime and ZonedDateTime

OffsetDateTime holds date/time plus an offset such as +07:00. That is sufficient to determine an instant and preserve the value's offset.

ZonedDateTime additionally holds a ZoneId such as Asia/Ho_Chi_Minh or Europe/Paris, including DST rules from Java's timezone database. Oracle TSTZ can hold a timezone region, but JDBC mappings to OffsetDateTime typically represent the offset; do not assume region names will always survive conversion intact.

If business requirements need the user-selected timezone region, store ZoneId separately as a controlled string. Example:

    event_time       TIMESTAMP WITH TIME ZONE
    event_zone_id    VARCHAR2(64)

When reading, ZonedDateTime can be reconstructed from the appropriate instant/offset and stored ZoneId. Clearly define whether ZoneId is validated against an allowed list of regions.

## 3. Difference between instant and local wall-clock time

A common design mistake is using LocalDateTime for every date/time column. LocalDateTime is just calendar components; it has no timezone. Instant is an absolute point in time; OffsetDateTime has an offset; ZonedDateTime has timezone region rules.

Example of the same instant:

    Instant:
      2026-11-14T14:19:00Z

    Asia/Ho_Chi_Minh:
      2026-11-14T21:19:00+07:00

These two representations point to the same instant. If you drop the offset and store only LocalDateTime 21:19, the system no longer knows whether it is 14:19Z or another instant in a different timezone.

### 3.1. When should you store UTC?

For event timestamps compared across systems, storing normalized UTC instants usually minimizes ambiguity. You can use:

- TIMESTAMP WITH TIME ZONE to store values with offsets and convert explicitly.
- TIMESTAMP with a convention that all values are written/read as UTC, alongside clear column naming and documentation.
- A custom epoch/instant representation if specific requirements exist, while evaluating precision and SQL queryability.

Whichever approach you choose, enforce it consistently across APIs, Java domain, JDBC, database, and reports. Never let one service write local time while another reads it as UTC.

### 3.2. When should you keep local time?

Some data represents business local time rather than an instant:

- A store opens at 09:00 local time.
- An appointment takes place at 10:30 at a specific location.
- A batch schedule runs daily at 02:00 in a specific region.
- A settlement cut-off date is a calendar date in the operating country.

In these cases, store ZoneId or timezone rules alongside LocalDate/LocalTime/LocalDateTime if the system must convert to instants or handle DST.

## 4. JDBC 4.2 and java.time

JDBC 4.2 added support for java.time types via PreparedStatement.setObject and ResultSet.getObject with a target type. Oracle JDBC drivers support specific mappings depending on version. Use a driver compatible with your JDK and database, and directly test DATE, TIMESTAMP, TSTZ, and TSLTZ in use.

### 4.1. Writing LocalDateTime to TIMESTAMP

Example column:

    CREATE TABLE audit_event (
        event_id NUMBER PRIMARY KEY,
        occurred_at TIMESTAMP(6) NOT NULL
    );

Java:

    LocalDateTime occurredAt =
        LocalDateTime.of(2026, 11, 14, 21, 19, 35, 123456000);

    String sql =
        "INSERT INTO audit_event (event_id, occurred_at) VALUES (?, ?)";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, 1001L);
        ps.setObject(2, occurredAt);
        ps.executeUpdate();
    }

Reading:

    String sql =
        "SELECT occurred_at FROM audit_event WHERE event_id = ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, 1001L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                LocalDateTime value =
                    rs.getObject("occurred_at", LocalDateTime.class);
            }
        }
    }

This preserves local date-time semantics. It does not automatically convert to UTC because the TIMESTAMP column carries no timezone.

### 4.2. Writing LocalDate to a calendar date column

If a column is defined as Oracle DATE while the data contract is strictly a calendar date:

    LocalDate birthDate = LocalDate.of(1990, 5, 20);

JDBC 4.2 setObject with LocalDate can be used if the driver supports the mapping:

    ps.setObject(1, birthDate);

When reading:

    LocalDate value = rs.getObject("birth_date", LocalDate.class);

Because Oracle DATE includes a time component, ensure the column only stores midnight or intentional conversion rules. If data includes time, use LocalDateTime to avoid truncating information.

### 4.3. TIMESTAMP WITH TIME ZONE and OffsetDateTime

DDL:

    CREATE TABLE meeting (
        meeting_id NUMBER PRIMARY KEY,
        starts_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
    );

Java:

    OffsetDateTime startsAt =
        OffsetDateTime.parse("2026-11-14T21:19:35.123456+07:00");

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO meeting (meeting_id, starts_at) VALUES (?, ?)")) {
        ps.setLong(1, 2001L);
        ps.setObject(2, startsAt);
        ps.executeUpdate();
    }

Reading:

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT starts_at FROM meeting WHERE meeting_id = ?")) {
        ps.setLong(1, 2001L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                OffsetDateTime value =
                    rs.getObject("starts_at", OffsetDateTime.class);

                Instant instant = value.toInstant();
            }
        }
    }

Verify whether the driver supports direct TSTZ mapping to OffsetDateTime. If using an older driver or incompatible mapping, use the Oracle JDBC API documented for that version or read through a compatible type and convert under control.

OffsetDateTime preserves the offset, though not necessarily the timezone region name. If preserving the region is required, store ZoneId separately.

### 4.4. Using Instant

Instant suits event timestamps. There are two common design paths:

1. Store in TIMESTAMP WITH TIME ZONE and convert Instant to OffsetDateTime at UTC.
2. Store in TIMESTAMP with a consistently enforced UTC convention.

Example converting to UTC OffsetDateTime:

    Instant instant = Instant.now();
    OffsetDateTime utcValue = instant.atOffset(ZoneOffset.UTC);

    ps.setObject(1, utcValue);

When reading TSTZ:

    OffsetDateTime offsetValue =
        rs.getObject("occurred_at", OffsetDateTime.class);

    Instant occurredAt = offsetValue.toInstant();

If using plain TIMESTAMP under a UTC convention, convert LocalDateTime to Instant by attaching ZoneOffset.UTC:

    LocalDateTime storedUtc =
        rs.getObject("occurred_at", LocalDateTime.class);

    Instant occurredAt = storedUtc.toInstant(ZoneOffset.UTC);

Do not use ZoneId.systemDefault() to interpret a UTC TIMESTAMP. Doing so makes results depend on the timezone of the machine running the application.

### 4.5. Fallback for drivers not supporting direct mapping

With older JDBC APIs or drivers that do not support getObject/setObject for java.time as needed, java.sql.Timestamp can serve as a bridge for non-timezone DATE/TIMESTAMP:

    Timestamp timestamp = rs.getTimestamp("created_at");
    LocalDateTime value = timestamp.toLocalDateTime();

Writing:

    Timestamp timestamp = Timestamp.valueOf(value);
    ps.setTimestamp(1, timestamp);

For Oracle DATE containing time components, getTimestamp is usually safer than getDate when hours/minutes/seconds must be kept. Verify exact driver behavior and avoid Calendar overloads that mismatch between writer and reader.

For TSTZ/TSLTZ, never treat Timestamp as if it preserves the original timezone. Timestamp carries neither an offset nor a ZoneId. If legacy APIs must be used, use Oracle JDBC types/APIs or an explicit timezone-aware SQL representation and convert at a tested boundary.

## 5. Why java.sql.Date and java.util.Date are error-prone

### 5.1. java.sql.Date

java.sql.Date represents SQL DATE under the JDBC contract and does not preserve time components the way Oracle DATE does. When an Oracle DATE column stores 14:30:00, reading via java.sql.Date can lose the time part.

Only use java.sql.Date when business logic truly only needs calendar dates and data strictly follows a no-time rule. For new applications, prefer LocalDate for calendar dates.

### 5.2. java.sql.Timestamp

java.sql.Timestamp preserves fractional seconds but carries no timezone. It works as a legacy JDBC bridge for TIMESTAMP/DATE with time, yet cannot represent a TSTZ offset.

Conversions:

    LocalDateTime local = timestamp.toLocalDateTime();
    Timestamp timestamp2 = Timestamp.valueOf(local);

These two operations convert calendar fields without adding a timezone.

    Instant instant = timestamp.toInstant();
    Timestamp timestamp3 = Timestamp.from(instant);

These two operations use instants and interact with timezone conventions in related APIs. Do not mix the two conversion families arbitrarily.

### 5.3. java.util.Date

java.util.Date represents an instant in milliseconds from the epoch and stores no timezone region. When formatted as a string, output depends on the formatter's timezone or JVM default timezone. It is unsuitable as a primary domain type in new code where Instant, LocalDate, LocalDateTime, or OffsetDateTime can be used.

### 5.4. Do not pass dates/times as Strings when typed binding is possible

Error-prone approach:

    String sql =
        "INSERT INTO event_log(created_at) VALUES (TO_DATE('" +
        userInput + "', 'YYYY-MM-DD HH24:MI:SS'))";

This risks format errors, NLS issues, SQL injection, and wrong timezones. Parse inputs into java.time, validate them, and bind via PreparedStatement.setObject or an appropriate JDBC API.

## 6. Oracle timezones: DBTIMEZONE and SESSIONTIMEZONE

Oracle has two key concepts:

- DBTIMEZONE: the database's timezone, involved in how Oracle processes and normalizes TIMESTAMP WITH LOCAL TIME ZONE.
- SESSIONTIMEZONE: the current session's timezone, affecting how TSLTZ is displayed and how session-dependent date/time functions behave.

Check:

    SELECT DBTIMEZONE, SESSIONTIMEZONE
    FROM dual;

You can check the JDBC session's timezone after obtaining a connection:

    SELECT SESSIONTIMEZONE FROM dual;

In a connection pool, multiple requests reuse the same physical session. If one request runs ALTER SESSION SET TIME_ZONE and returns the connection to the pool without resetting it, the next request may inherit the timezone left behind by the previous request.

This bug is especially hard to spot because it only manifests when requests land on connections with differing session states.

### 6.1. Fixing the session timezone

If an application wants all sessions to handle TSLTZ and time functions in UTC, configure session initialization:

    ALTER SESSION SET TIME_ZONE = 'UTC';

Place this statement in the pool's connection initialization hook, or ensure each physical connection is initialized once and session state is never mutated uncontrollably.

If an application serves multiple tenants or users in different timezones, do not arbitrarily mutate SESSIONTIMEZONE on a pooled connection. If changing it is unavoidable, save the old timezone and restore it in a finally block before returning the connection; better yet, use a verified pool connection initialization/reset mechanism.

### 6.2. DBTIMEZONE is not the application server's timezone

DBTIMEZONE does not necessarily equal the OS timezone, JVM timezone, or SESSIONTIMEZONE. Never assume these values match.

With TSLTZ, Oracle converts using the session timezone on read; thus the same row can display differently across two sessions. With non-timezone DATE/TIMESTAMP, Oracle has no built-in knowledge of the data's timezone.

## 7. Oracle date/time functions and timezone effects

Different functions return different DATE/TIMESTAMP types and draw from different timezone sources.

| Function | Return type | Primary semantics |
|---|---|---|
| SYSDATE | DATE | Date/time from the database server's OS clock |
| SYSTIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp from the database server's OS clock, with offset |
| CURRENT_DATE | DATE | Current date/time in SESSIONTIMEZONE |
| CURRENT_TIMESTAMP | TIMESTAMP WITH TIME ZONE | Current timestamp in SESSIONTIMEZONE |
| LOCALTIMESTAMP | TIMESTAMP | Current timestamp in SESSIONTIMEZONE, without timezone in the returned value |
| DBTIMEZONE | VARCHAR2 | Database-level configured timezone |
| SESSIONTIMEZONE | VARCHAR2 | Current session's timezone |

Example:

    SELECT
        SYSDATE,
        SYSTIMESTAMP,
        CURRENT_DATE,
        CURRENT_TIMESTAMP,
        LOCALTIMESTAMP,
        DBTIMEZONE,
        SESSIONTIMEZONE
    FROM dual;

Do not substitute SYSDATE for CURRENT_DATE or vice versa without evaluating semantics. If the database server runs in UTC while the session runs in Asia/Ho_Chi_Minh, SYSDATE and CURRENT_DATE can show different times.

### 7.1. Timezone conversion in SQL

You can attach a timezone to a non-timezone TIMESTAMP using FROM_TZ:

    SELECT FROM_TZ(
        TIMESTAMP '2026-11-14 21:00:00',
        'Asia/Ho_Chi_Minh'
    ) AS value_with_zone
    FROM dual;

You can convert a timezone-aware value to another zone using AT TIME ZONE:

    SELECT
        FROM_TZ(
            TIMESTAMP '2026-11-14 21:00:00',
            'Asia/Ho_Chi_Minh'
        ) AT TIME ZONE 'UTC' AS utc_value
    FROM dual;

This converts using Oracle's timezone regions and rules. Avoid manually adding or subtracting a fixed number of hours to convert timezones, as offsets can change due to DST or regional legal changes.

### 7.2. NLS formats are not timezones

NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, and NLS_TIMESTAMP_TZ_FORMAT control how Oracle converts/formats strings in certain contexts. They do not alter the underlying stored data.

Example:

    ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

Do not rely on default NLS formats to parse date/time strings. Use typed bind variables or specify explicit format masks whenever SQL string conversion is unavoidable.

## 8. Daylight Saving Time (DST), gaps, and overlaps

Timezone regions have offset change rules based on historical and local regulations. In regions observing DST, clocks can spring forward or fall back.

Two scenarios:

- **Gap**: a span of local time does not exist when clocks jump forward. For example, 02:30 may not occur on a DST spring-forward transition day.
- **Overlap**: a span of local time occurs twice when clocks fall back. For example, 01:30 can correspond to two distinct instants.

LocalDateTime cannot distinguish the two instants inside an overlap. To represent an actual event, use OffsetDateTime/Instant or LocalDateTime paired with ZoneId and an overlap offset-selection policy.

### 8.1. Java ZoneId and ZonedDateTime

Example converting a local date-time to a timezone:

    LocalDateTime local =
        LocalDateTime.of(2026, 11, 14, 9, 0);

    ZonedDateTime zoned =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

    Instant instant = zoned.toInstant();

Asia/Ho_Chi_Minh does not currently observe DST under existing rules, but applications should not generalize that to every ZoneId. When using Europe/Paris or America/New_York, check gap/overlap per timezone rules.

Java provides ZoneRules to inspect valid offsets:

    ZoneId zone = ZoneId.of("Europe/Paris");
    LocalDateTime localTime =
        LocalDateTime.of(2026, 10, 25, 2, 30);

    List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(localTime);

If the list is empty, the local time falls in a gap. If there are two offsets, the local time falls in an overlap and the application needs an offset selection policy. Do not let library defaults silently decide for critical business logic.

### 8.2. Keeping both instant and business timezone

For appointments, flight schedules, or location-bound events, the data model may require:

- Instant or TSTZ: actual point in time.
- ZoneId: business/location timezone.
- LocalDateTime: local wall-clock time chosen by the user, if preserving the entered schedule is needed.

Not every application needs to store all three. Choose by requirement: past events need an instant; future schedules may need both local wall-clock time and ZoneId to preserve intent if DST laws change.

## 9. TSLTZ and session pools: common failure scenarios

Suppose ORDS, Spring Boot, or a batch application uses a connection pool. One physical connection is reused across many requests. If request A changes the session timezone to Europe/Paris and returns the connection to the pool, request B may receive the same session and read TSLTZ under request A's timezone.

Potential consequences:

- Timestamps display differently across requests.
- Isolated tests pass while production fails intermittently.
- Certain SQL results depend on request ordering.
- TSLTZ data serializes to JSON with unexpected hours.
- CURRENT_DATE/CURRENT_TIMESTAMP functions return different results across sessions.

How to control this:

1. Standardize on one session timezone, typically UTC for services handling event timestamps.
2. Configure the timezone when the physical connection is created.
3. Never change session timezone arbitrarily inside a request.
4. If changing it is mandatory, always reset it before returning the connection to the pool.
5. Log SESSIONTIMEZONE in diagnostics.
6. Test with multiple physical connections and concurrent requests.
7. Use data types with clear semantics instead of relying on uncontrolled session state.

If business requirements need user-timezone display, converting from Instant to the user's ZoneId in the application layer is usually easier to observe and test than constantly mutating SESSIONTIMEZONE on a pool.

## 10. Fractional second precision and rounding

Oracle TIMESTAMP supports 0 to 9 digits of fractional seconds. Java LocalDateTime and Instant have nanosecond precision. When writing data with higher precision than the column allows, Oracle applies conversion/rounding rules appropriate for the type and operation; applications should not assume all nanosecond digits are retained.

Examples:

    TIMESTAMP(3)   -- millisecond precision
    TIMESTAMP(6)   -- microsecond precision
    TIMESTAMP(9)   -- nanosecond precision

If the system uses TIMESTAMP(6), normalize or accept truncation/rounding of nanoseconds to the column's precision. When comparing timestamps or generating time-based unique keys, account for the actual database and driver precision.

Do not use timestamps as unique keys if multiple events can occur within the column's precision. Sequences, identity columns, or UUIDs are more suitable.

## 11. Spring Boot, Hibernate, and timezones

In Spring Boot applications, both the JDBC driver and the ORM influence mapping. If using Hibernate/JPA, check the Hibernate version, Oracle dialect, JDBC driver, and entity mappings.

Domain example:

    @Entity
    class AuditEvent {
        @Id
        private Long id;

        private Instant occurredAt;
    }

Instant usually fits event timestamps. For TSTZ columns, verify the Hibernate version and timezone storage strategy configuration. For plain TIMESTAMP storing UTC, document the convention and ensure all read/write paths apply UTC.

Hibernate configuration that may be used:

    spring:
      jpa:
        properties:
          hibernate:
            jdbc:
              time_zone: UTC

This setting helps Hibernate apply a consistent timezone for certain JDBC timestamp operations, but it does not turn a non-timezone TIMESTAMP into a timezone-aware type, nor does it replace understanding TSTZ/TSLTZ. Verify behavior with your exact Hibernate version, Oracle dialect, and driver.

When using Spring JDBC or JdbcTemplate, java.time can be bound directly via PreparedStatementSetter/RowMapper if supported by the driver. Keep mapping in the repository layer and avoid letting controllers parse/format dates and times arbitrarily.

### 11.1. JSON APIs and ISO-8601

When receiving timestamps in REST APIs, prefer ISO-8601 format with an offset for instants:

    2026-11-14T21:19:35.123456+07:00

Or UTC:

    2026-11-14T14:19:35.123456Z

If an API accepts LocalDateTime without an offset, define the timezone in the contract. Do not infer timezone from the server or browser unless specified by business rules.

Jackson supports java.time through the appropriate module. Standardize responses and test round-trips across JSON, Java, JDBC, and Oracle. Avoid formatting timestamps as locale-dependent default strings.

## 12. Schema design rules

Practical rules:

| Business meaning | Suggested Oracle type | Suggested Java type |
|---|---|---|
| Birth date, calendar invoice date | DATE with time always 00:00:00, or appropriate date model | LocalDate |
| Store opening hour, local appointment without timezone | DATE or TIMESTAMP per required precision | LocalDateTime, with separate ZoneId if needed |
| Cross-system record creation/update instant | TIMESTAMP WITH TIME ZONE or TIMESTAMP under UTC convention | Instant or OffsetDateTime |
| Instant with client-supplied offset | TIMESTAMP WITH TIME ZONE | OffsetDateTime |
| Instant displayed in session timezone | TIMESTAMP WITH LOCAL TIME ZONE | LocalDateTime in session timezone, with session control |
| Future schedule in location timezone | Local date-time + ZoneId; optionally store projected instant | LocalDateTime + ZoneId/ZonedDateTime |

Do not convert every DATE column to TIMESTAMP WITH TIME ZONE just because the application uses java.time. SQL types must reflect accurate semantics and remain compatible with existing data, reports, indexes, partitions, integrations, and applications.

### 12.1. Naming columns to clarify semantics

Names like CREATED_AT_UTC, BUSINESS_DATE, LOCAL_START_TIME, or EVENT_TSTZ help readers understand intent. However, conventions must be documented and enforced in code, migrations, and tests.

Example:

    CREATE TABLE payment_event (
        event_id NUMBER PRIMARY KEY,
        created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
        business_date DATE,
        store_zone_id VARCHAR2(64)
    );

created_at is a timezone-aware instant; business_date is a business calendar date; store_zone_id holds the location timezone. Do not reuse the same column for all three concepts.

## 13. Testing date/time mappings

Tests must cover more than a single ordinary value. At minimum, test:

- End-of-month and start-of-month dates.
- Leap years and February 29.
- Exact midnight values and values with hours/minutes/seconds.
- Fractional seconds at the column's precision.
- UTC, +07:00, and negative offsets.
- Timestamps in timezones observing DST.
- Instants inside DST gaps and overlaps.
- The same TSLTZ value read from two different session timezones.
- Connections re-borrowed from the pool after session state changes.
- Round-trip JSON -> Java -> JDBC -> Oracle -> JDBC -> Java -> JSON.
- Null values and nullable columns.

Tests must run against the exact deployed Oracle JDBC driver. Mock JDBC cannot fully verify how the Oracle driver converts DATE, TSTZ, and TSLTZ.

### 13.1. Simple round-trip test example

A repository test can write and read back a LocalDateTime:

    LocalDateTime input =
        LocalDateTime.of(2026, 11, 14, 21, 19, 35, 123456000);

    repository.save(input);

    LocalDateTime actual = repository.findById(1L);

    assertEquals(input, actual);

If the column is TIMESTAMP(3), the test must truncate/normalize input to milliseconds before comparing. If using TIMESTAMP(6), normalize to microseconds. Do not compare nanoseconds against a column storing only 6 fractional digits.

For OffsetDateTime/TSTZ, compare Instants if the goal is the same point in time; compare offsets or separate ZoneId if business rules require preserving the original representation.

## 14. Common mistakes and how to fix them

### 14.1. Time lost after reading Oracle DATE

Common cause is using getDate or java.sql.Date. Oracle DATE includes time, whereas java.sql.Date has calendar-date semantics.

Resolution: use LocalDateTime via JDBC 4.2 if supported by the driver, or getTimestamp followed by toLocalDateTime. Verify whether the column actually holds time data before changing the mapping.

### 14.2. Time shifted by an exact number of hours

Possible causes include converting LocalDateTime to Instant using the JVM default timezone, differing session timezones, or an API parsing offsetless timestamps as if they were UTC.

Resolution: check SQL type, SESSIONTIMEZONE, JVM timezone, JSON input, and conversion code. Never add/subtract hours manually; choose an explicit UTC or timezone region convention.

### 14.3. Same TSLTZ returning different hours

This is expected behavior when session timezones differ. Inspect SESSIONTIMEZONE on each connection. Fix the session timezone or convert in the application layer using an explicit ZoneId.

### 14.4. Losing timezone region after round-trip

OffsetDateTime preserves the offset but not the original region name. If preserving Asia/Ho_Chi_Minh or Europe/Paris is part of business requirements, store ZoneId separately and test the driver mapping.

### 14.5. Timestamp losing fractional second digits

Check TIMESTAMP(p) column precision, driver, and intermediate types. java.sql.Date or string formatting can drop time/subseconds; a TIMESTAMP(3) column also will not retain microseconds/nanoseconds.

### 14.6. Errors depending on NLS_DATE_FORMAT

If an application passes date/time strings relying on default session formats, environments with different NLS settings can parse differently or throw errors. Bind typed values instead of concatenating strings; if parsing strings in SQL is required, use an explicit format mask.

## 15. Diagnostic workflow for a shifted date/time column

When a date/time discrepancy is reported between Java and Oracle, investigate in order:

1. Retrieve the exact column DDL: DATE, TIMESTAMP(p), TSTZ, or TSLTZ.
2. Inspect the value directly in Oracle using a format displaying full date, time, fractional seconds, and timezone if present.
3. Check the Java type in use: LocalDate, LocalDateTime, Instant, OffsetDateTime, or a legacy type.
4. Inspect JDBC code for getDate, getTimestamp, getObject, or getString.
5. Check Oracle JDBC driver version and JDK version.
6. Check DBTIMEZONE, SESSIONTIMEZONE, and JVM default timezone.
7. Check timezone handling in JSON input/output and serialization libraries.
8. If using a pool, inspect session state across multiple physical connections.
9. Compare Instant when the target is a point in time; compare LocalDateTime when the target is wall-clock time.
10. Write a round-trip test reproducing the bug and run it on the exact production driver/runtime.

Avoid fixing discrepancies by adding or subtracting a fixed hour offset in a mapper. That may appear to fix one environment while breaking another or failing across DST transitions.

## 16. Principles to remember

- Oracle DATE stores date and time to the second; do not treat it as date-only without verifying the data.
- Oracle TIMESTAMP has fractional seconds but no timezone.
- TSTZ stores date/time with offset/region; OffsetDateTime is the natural mapping, though ZoneId may need separate storage.
- TSLTZ normalizes to DBTIMEZONE and displays in SESSIONTIMEZONE; each row's original timezone is not retained.
- LocalDate is for calendar dates; LocalDateTime is for timezone-less wall-clock date/time; Instant is for absolute points in time; OffsetDateTime is for date/time with an offset.
- JDBC 4.2 supports java.time via getObject/setObject depending on the driver; test on the actual ojdbc release.
- Never use java.sql.Date for Oracle DATE values containing time; use LocalDateTime or Timestamp when time must be preserved.
- Never interpret LocalDateTime as an Instant using the host's default timezone.
- Fix or reset SESSIONTIMEZONE on connection pools; never let session state leak between requests.
- Use bind variables and ISO-8601 with offsets for timestamps passed across APIs.
- Test DST, precision, nulls, session timezones, and round-trips before deploying.

Correct date/time mapping starts by asking whether the data represents a calendar date, a local wall-clock time, or an absolute point in time. After choosing the right Oracle type and java.time type, control timezones across the JDBC session, driver, and API boundaries. Clarifying semantics up front prevents dropped time components, shifted timezones, and inconsistent results across environments.
