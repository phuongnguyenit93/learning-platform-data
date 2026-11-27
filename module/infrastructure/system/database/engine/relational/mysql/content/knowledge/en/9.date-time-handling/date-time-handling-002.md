# DATE, DATETIME, TIMESTAMP, and Value Ranges by Version

Date and time are foundational data in most applications: date of birth, delivery date, order creation timestamp, appointments, login time, and event recording time. Choosing the wrong data type can drop the time component, restrict future dates, cause discrepancies when running across multiple time zones, or prevent values from being represented once the system operates long enough.

MySQL provides three commonly used types for storing dates and points in time:

- **DATE** stores a calendar date, with no time component.
- **DATETIME** stores a date and time as a calendar value, without automatic time zone conversion.
- **TIMESTAMP** stores an instant and converts between the connection session time zone and UTC on write and read.

The value ranges of these three types differ. Notably, TIMESTAMP in mainstream MySQL releases still has a limit up to the year 2038, including MySQL 8.x. Therefore, type selection must be based on business semantics, time range, time zones, and the deployed MySQL version.

## 1. Distinguishing Calendar Dates and Instants

Before choosing a data type, identify what the data needs to represent.

A **calendar date** is a date on a calendar, not necessarily tied to a specific instant. Examples:

- Customer's date of birth.
- Contract signing date.
- Public holiday.
- Scheduled delivery date if the business only cares about the date.

An **instant** is a specific moment on the timeline. Examples:

- When an order was created.
- When a payment succeeded.
- When the server recorded an event.
- When a user logged in.

A **local time** such as “09:00 in Hanoi” has a different meaning: it is a clock time at a specific location, which may need to stay fixed on the calendar even if time zone rules change. For example, medical appointments, opening hours, or class schedules often require both the local date/time and the location's IANA time zone.

Do not use a single date/time type for every case. DATE, DATETIME, and TIMESTAMP solve different requirements.

## 2. The DATE Type

### 2.1. Semantics and Value Range

DATE stores year, month, and day. It does not store hours, minutes, seconds, or a time zone.

In MySQL 5.7, 8.0, and 8.4, the typical DATE value range is:

| Type | Minimum Value | Maximum Value |
|---|---|---|
| DATE | 1000-01-01 | 9999-12-31 |

A DATE value is displayed in the format YYYY-MM-DD.

Example:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO customers (full_name, birth_date)
VALUES ('Nguyen An', '1995-08-21');
~~~

### 2.2. When to Use DATE?

Use DATE when the business only cares about the calendar date and does not need a time of day. Avoid storing a date of birth as DATETIME with a default time of 00:00:00, because the time part carries no meaning and can cause confusion during processing.

DATE fits well for:

- Date of birth, founding date.
- Contract effective date when validity is by date only.
- Accounting date or business day.
- Leave days, public holidays.

If the business needs to know the exact instant an event occurred, DATE does not hold enough information.

## 3. The DATETIME Type

### 3.1. Semantics and Value Range

DATETIME stores both date and time as a calendar value. It does not store a time zone, and MySQL does not automatically convert DATETIME values when the session time zone changes.

Typical value range in MySQL 5.7, 8.0, and 8.4:

| Type | Minimum Value | Maximum Value |
|---|---|---|
| DATETIME | 1000-01-01 00:00:00 | 9999-12-31 23:59:59 |

Values can include fractional seconds if fractional seconds precision is declared:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at      DATETIME(6) NOT NULL,
    ends_at        DATETIME(6) NOT NULL,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
~~~

DATETIME(6) stores down to the microsecond. If fsp is omitted, the default precision is 0, meaning no fractional seconds.

### 3.2. DATETIME Does Not Convert by Time Zone

Suppose you store:

~~~sql
INSERT INTO appointments (starts_at, ends_at)
VALUES (
    '2026-11-20 09:00:00',
    '2026-11-20 10:00:00'
);
~~~

The DATETIME value is stored and read as the exact date and time components entered. If the session time zone changes from +07:00 to +00:00, the DATETIME value remains 2026-11-20 09:00:00.

This property is useful when local wall-clock time must be preserved or when the system manages UTC storage itself by convention. However, DATETIME does not tell a reader whether the value is local time somewhere or UTC. If an application stores UTC in DATETIME, that convention must be enforced consistently across all layers and clearly documented in docs/schema.

### 3.3. When to Use DATETIME?

DATETIME is appropriate when:

- A wide year range up to 9999 is needed.
- Future dates/times beyond the TIMESTAMP limit must be stored.
- Local wall-clock time must remain unchanged.
- The system manages time zone conversions itself and follows a convention of storing UTC in DATETIME.

For example, room reservations, class schedules, or medical appointments may need to preserve local clock time. If a schedule is tied to a location, also store the IANA time zone name, such as Asia/Ho_Chi_Minh, so it can be interpreted accurately if time zone rules change.

## 4. The TIMESTAMP Type

### 4.1. Semantics and Value Range

TIMESTAMP represents an instant. On write, MySQL converts the value from the session time zone to UTC for storage; on read, MySQL converts from UTC back to the current session time zone.

The TIMESTAMP value range in mainstream MySQL 5.7, 8.0, and 8.4 remains constrained by a 32-bit representation:

| Type | Value Range in UTC |
|---|---|
| TIMESTAMP | 1970-01-01 00:00:01 to 2038-01-19 03:14:07 |

This limit corresponds to the time span of a signed 32-bit Unix timestamp. Do not assume that MySQL 8.x has expanded TIMESTAMP to store dates up to the year 9999.

Example:

~~~sql
CREATE TABLE audit_events (
    event_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
~~~

### 4.2. Conversion Between Session Time Zone and UTC

TIMESTAMP is affected by the session's time_zone variable. For example, if the session uses +07:00 and inserts:

~~~sql
SET time_zone = '+07:00';

INSERT INTO audit_events (event_type, created_at)
VALUES ('LOGIN', '2026-11-20 09:00:00');
~~~

MySQL interprets the input as 09:00 in +07:00 and converts it to UTC for storage. When read in a +00:00 session, it displays as 02:00; when read in a +07:00 session, it displays as 09:00 again.

Thus, sessions in different time zones can see different displayed representations of the same TIMESTAMP instant. This behavior is intentional.

### 4.3. Comparing DATETIME and TIMESTAMP Across Two Sessions

The following example illustrates the difference:

~~~sql
CREATE TEMPORARY TABLE datetime_timestamp_demo (
    dt DATETIME,
    ts TIMESTAMP
);

SET time_zone = '+07:00';

INSERT INTO datetime_timestamp_demo (dt, ts)
VALUES ('2026-11-20 09:00:00', '2026-11-20 09:00:00');

-- Same +07:00 session: both display 09:00:00
SELECT dt, ts FROM datetime_timestamp_demo;

SET time_zone = '+00:00';

-- DATETIME stays 09:00; TIMESTAMP displays 02:00
SELECT dt, ts FROM datetime_timestamp_demo;

SET time_zone = '+07:00';
~~~

DATETIME preserves the calendar value; TIMESTAMP preserves the instant and converts its display according to the session time zone.

### 4.4. When to Use TIMESTAMP?

TIMESTAMP is suitable for event instants within the supported range that need consistent interpretation across multiple time zones:

- Record creation or update timestamps.
- Payment or event receipt timestamps.
- Login and logging timestamps.
- Data synchronization timestamps across systems.

If the business needs to store instants beyond 2038, consider DATETIME with an explicit UTC convention or another suitable representation.

## 5. Comparison Table: DATE, DATETIME, and TIMESTAMP

| Characteristic | DATE | DATETIME | TIMESTAMP |
|---|---|---|---|
| Stores date | Yes | Yes | Yes |
| Stores time | No | Yes | Yes |
| Stores time zone | No | No | Does not store time zone name; converts by session time zone |
| Auto-converts via UTC on write/read | No | No | Yes |
| Typical year range | 1000–9999 | 1000–9999 | 1970–2038 |
| Fractional seconds | No | Yes, fsp 0–6 | Yes, fsp 0–6 |
| Best suited for | Calendar dates | Calendar date/time, app-managed UTC, future schedules | Event instants within the supported range |

Note: TIMESTAMP does not store a time zone name like Asia/Ho_Chi_Minh. It stores a normalized instant, and display conversion on read relies on the session's time zone. If you need to reconstruct local time tied to a place, store the time zone name separately.

## 6. Fractional Seconds Precision (fsp)

### 6.1. Scope

DATETIME and TIMESTAMP support fractional seconds with precision from 0 to 6:

| Declaration | Precision |
|---|---|
| DATETIME or TIMESTAMP | 0, no fractional seconds stored |
| DATETIME(3) | 3 decimal digits, down to millisecond |
| TIMESTAMP(6) | 6 decimal digits, down to microsecond |

Any fsp from 0 to 6 can be used. If omitted, MySQL defaults to 0.

Example:

~~~sql
CREATE TABLE job_runs (
    job_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at  DATETIME(3) NOT NULL,
    recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (job_id)
) ENGINE = InnoDB;
~~~

### 6.2. Time Functions Must Match Desired Precision

You can specify fsp for current-time functions:

~~~sql
SELECT
    CURRENT_TIMESTAMP(6),
    NOW(6),
    UTC_TIMESTAMP(6);
~~~

For a TIMESTAMP(6) column, you can declare:

~~~sql
created_at TIMESTAMP(6)
    NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
~~~

If a column only has precision 0 while the application passes microseconds, the fractional part will not be fully preserved. Rounding or truncation rules may be affected by the TIME_TRUNCATE_FRACTIONAL SQL mode; check the configuration and test actual behavior if precision is a business requirement.

### 6.3. Physical Storage

With the modern temporal format from MySQL 5.6.4 onward, base storage sizes are:

| Type | Base Size |
|---|---:|
| DATE | 3 bytes |
| DATETIME | 5 bytes |
| TIMESTAMP | 4 bytes |

DATETIME and TIMESTAMP take extra bytes for fractional seconds: fsp 1–2 adds 1 byte, fsp 3–4 adds 2 bytes, and fsp 5–6 adds 3 bytes. Prior to MySQL 5.6.4, DATETIME used a legacy 8-byte storage format and did not support modern fractional seconds.

Do not choose a data type based solely on a one-byte difference. Temporal semantics, value range, time zones, and compatibility matter far more.

## 7. Time Zones in MySQL

### 7.1. Server and Session time_zone

MySQL has a time_zone variable at both GLOBAL and SESSION scopes:

~~~sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone;
~~~

- @@GLOBAL.time_zone is the default time zone the server uses to initialize new sessions.
- @@SESSION.time_zone is the time zone applied to the current connection.
- @@system_time_zone indicates the operating system time zone detected by MySQL at startup.

The default value of time_zone is typically SYSTEM, meaning it uses the system time zone. You can set the session time zone:

~~~sql
SET time_zone = '+00:00';
~~~

Or:

~~~sql
SET time_zone = '+07:00';
~~~

Changing SET GLOBAL time_zone affects subsequent new connections; existing sessions retain their own SESSION value until changed individually.

### 7.2. Using Time Zone Names Instead of Fixed Offsets

MySQL can use IANA time zone names such as Asia/Ho_Chi_Minh:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';
~~~

To use time zone names, MySQL's timezone tables must be loaded and kept updated. Otherwise, the statement may fail with an unknown time zone error. On managed servers, synchronize timezone tables whenever OS time zone rules change.

A fixed offset like +07:00 represents a constant shift from UTC. An IANA name reflects historical rules and Daylight Saving Time (DST) transitions for a region. For systems operating across multiple countries, IANA names are usually more appropriate when converting according to local rules.

### 7.3. CURRENT_TIMESTAMP, NOW, and UTC_TIMESTAMP

Common functions:

| Function | Meaning |
|---|---|
| NOW() or CURRENT_TIMESTAMP | Current instant in the session time zone |
| UTC_TIMESTAMP() | Current instant in UTC |
| CURDATE() or CURRENT_DATE | Current date in the session time zone |
| UTC_DATE() | Current date in UTC |

Example:

~~~sql
SELECT
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now,
    CURDATE() AS session_date,
    UTC_DATE() AS utc_date;
~~~

NOW() and CURRENT_TIMESTAMP return the time in the session time zone. If written into a DATETIME column, MySQL stores the exact date/time value returned; DATETIME does not auto-convert to UTC. If written into a TIMESTAMP column, the value is interpreted in the session time zone and converted to UTC for storage.

## 8. Choosing Data Types by Business Use Case

### 8.1. Date of Birth

Use DATE:

~~~sql
birth_date DATE
~~~

A date of birth is a calendar date; no time zone or time of day is needed.

### 8.2. Record Creation Timestamp

TIMESTAMP can be used if the instant falls within the supported range and the application wants MySQL to convert via UTC automatically:

~~~sql
created_at TIMESTAMP(6)
    NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
~~~

If the system needs to store instants beyond 2038, DATETIME(6) can be used with a strict convention of always storing UTC:

~~~sql
created_at DATETIME(6) NOT NULL
~~~

The application must ensure every writer converts to UTC before saving and every reader interprets the value as UTC.

### 8.3. Appointment at a Location

For appointments, local wall-clock time may be part of the business domain. The model can include:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at      DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
~~~

For example, starts_at = '2026-11-20 09:00:00' with time_zone_name = 'Asia/Ho_Chi_Minh' means an appointment at 09:00 in that region's time. When the UTC instant is needed, the application or MySQL can convert using the corresponding time zone data.

In regions with DST, a local time may repeat or not exist during clock transitions. A scheduling system must define how to handle ambiguous or invalid times, and may also store the confirmed UTC instant to avoid differing interpretations later.

### 8.4. Expiration Timestamp

If an expiration timestamp is an instant independent of where the user is located, store it in UTC. TIMESTAMP can be used if the time horizon fits; if expirations can extend beyond 2038, use DATETIME with a UTC convention or another appropriate representation.

Do not store “expires after 30 days” solely as a local date/time without defining the time zone and DST policy. Clarify whether it means 30 calendar days or 720 actual hours.

## 9. Value Ranges and Differences by MySQL Version

### 9.1. Summary Table

| Version | DATE | DATETIME | TIMESTAMP | Fractional seconds |
|---|---|---|---|---|
| MySQL 5.5 and earlier | 1000–9999 | 1000–9999 | 1970–2038 | Not supported in modern format |
| MySQL 5.6.4 and later | 1000–9999 | 1000–9999 | 1970–2038 | Supports fsp 0–6 |
| MySQL 5.7 | 1000–9999 | 1000–9999 | 1970–2038 | Supports fsp 0–6 |
| MySQL 8.0 | 1000–9999 | 1000–9999 | 1970–2038 | Supports fsp 0–6 |
| MySQL 8.4 LTS | 1000–9999 | 1000–9999 | 1970–2038 | Supports fsp 0–6 |

The DATE and DATETIME ranges are written abbreviated by year; the full bounds for DATE are 1000-01-01 to 9999-12-31, and for DATETIME are 1000-01-01 00:00:00 to 9999-12-31 23:59:59. The TIMESTAMP range in the table above is in UTC.

### 9.2. Key Changes

- **Before MySQL 5.6.4:** DATETIME used the legacy storage format occupying 8 bytes, and temporal types did not support modern fractional seconds.
- **From MySQL 5.6.4 onward:** DATETIME uses a more compact storage format, and TIME, DATETIME, and TIMESTAMP support fractional seconds with up to 6 digits of precision.
- **MySQL 5.7, 8.0, and 8.4:** the mainstream TIMESTAMP range still ends in 2038; upgrading to 8.x does not automatically extend this range.

When upgrading servers or migrating data across versions, check DDL, boundary values, fractional seconds, and SQL modes. Do not rely solely on a migration succeeding; test values near the boundaries.

## 10. Invalid Date/Time Values and SQL Modes

MySQL validates date and time values on insert, update, and conversion. How certain invalid values are handled also depends on the SQL mode.

Examples of invalid values:

- 2026-02-30: date does not exist on the calendar.
- 2026-13-01: month out of range.
- 0000-00-00: zero date.
- 2026-00-15: month equals 0.

Relevant SQL modes:

- **STRICT_TRANS_TABLES** or **STRICT_ALL_TABLES**: govern how invalid data is handled; in strict mode, the operation is typically rejected rather than silently adjusted.
- **NO_ZERO_DATE**: controls acceptance of zero dates in versions supporting this mode.
- **NO_ZERO_IN_DATE**: controls dates with a valid year but a zero month or day.
- **ALLOW_INVALID_DATES**: relaxes date validation in certain cases; should not be used to legitimize invalid date data in applications.

Inspect the configuration:

~~~sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
~~~

NO_ZERO_DATE and NO_ZERO_IN_DATE were marked deprecated in MySQL 8.0.2; exact behavior also depends on version and enabled strict modes. Consult documentation for your exact version and avoid storing zero dates or invalid dates to represent “unknown”.

If a date is unknown, use NULL if the business domain allows, or model an explicit status. Do not use 0000-00-00 in place of NULL because comparisons, date functions, and data migrations can produce unpredictable results.

## 11. Conversion Functions and Date/Time Queries

### 11.1. Converting Between Time Zones

CONVERT_TZ() converts a date/time value from a source time zone to a target time zone:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-20 09:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
);
~~~

When using time zone names, timezone tables must be loaded. Otherwise, CONVERT_TZ may return NULL.

### 11.2. Converting Between DATE and DATETIME

Extract the date part from DATETIME:

~~~sql
SELECT DATE('2026-11-20 09:15:30');
~~~

Combine a date with a time:

~~~sql
SELECT TIMESTAMP('2026-11-20', '09:15:30');
~~~

The result is a DATETIME value; here TIMESTAMP(date, time) is the function that combines date and time components, not a cast to the TIMESTAMP column type with time zone conversion.

### 11.3. Avoid Arbitrary String Comparisons

Use date/time literals in an explicit format and parameterize queries:

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= ?
  AND occurred_at < ?;
~~~

A half-open interval [start, end) is usually convenient when querying by day or month because it avoids guessing the last fractional-second value. For example, retrieving events on 2026-11-20:

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= '2026-11-20 00:00:00'
  AND occurred_at <  '2026-11-21 00:00:00';
~~~

With TIMESTAMP, both boundary values are interpreted in the session time zone. Set the session time zone or convert input bounds to match the data's convention before querying.

## 12. Notes When Working with Applications and Connection Pools

An application may connect to MySQL from multiple servers in different time zones. If each connection uses a different time_zone, TIMESTAMP still represents the same instant but displays differently; expressions like NOW(), CURDATE(), and literals written to TIMESTAMP are also affected by the session.

Operational principles:

1. Choose a uniform policy, typically setting session time_zone to UTC for backend services.
2. Configure time_zone on every physical connection in the connection pool.
3. Do not arbitrarily change session time_zone and return the connection to the pool without resetting it.
4. When storing local time, also store the IANA time zone name and define how DST is handled.
5. Use DATETIME if storing local-time schedules or timestamps beyond the TIMESTAMP limit; document clearly whether the convention is UTC or local time.
6. Test values near minimum/maximum bounds and values with fractional seconds.

Example initializing a session to UTC:

~~~sql
SET time_zone = '+00:00';
~~~

A default for new connections can be set via server configuration or deployment platform settings. Even so, the application should verify @@SESSION.time_zone on actual connections.

## 13. Type Selection and Testing Checklist

Before designing a date/time column, answer:

1. Is the data a calendar date, local time, or an instant on the UTC timeline?
2. Is the time part needed, or only the date?
3. Is millisecond or microsecond precision required?
4. Could the data exceed the year 2038?
5. Does the application operate across multiple time zones?
6. If storing local time, does the IANA time zone name also need to be stored?
7. Does the SQL mode reject invalid dates and zero dates?
8. Does the connection pool consistently set and reset session time_zone?

Minimum test cases:

- Valid dates at the start and end of the DATE range.
- DATETIME at the start and end of the supported range.
- TIMESTAMP near both ends of the UTC range.
- Values with fractional seconds .123456 on columns with fsp 0, 3, and 6.
- Reading the same TIMESTAMP through a UTC session and a local session.
- Writing and reading DATETIME across two different session time zones to verify the value is not converted.
- Invalid dates, zero dates, and NULL under the actual SQL mode.
- Instants in a region with DST rules if the application serves that region.

## 14. Common Misconceptions

**“DATETIME and TIMESTAMP are the same, just written differently.”** No. TIMESTAMP converts by session time zone and has a narrower value range; DATETIME preserves the calendar value and has a wider year range.

**“TIMESTAMP stores the time zone name.”** No. It stores an instant, and MySQL converts according to the session time zone on write/read. A location's time zone name must be stored separately if the business needs it.

**“MySQL 8.x removed TIMESTAMP's 2038 limit.”** No. Mainstream 5.7, 8.0, and 8.4 releases still have a TIMESTAMP range ending at 2038-01-19 03:14:07 UTC.

**“DATETIME automatically stores UTC.”** No. DATETIME stores the exact calendar value provided. If a UTC convention is chosen, the application must convert before writing and interpret consistently on read.

**“DATE can store an instant by setting the time to 0.”** No. DATE only stores the date; the time part is discarded.

**“Increasing fractional seconds precision widens the date range.”** No. FSP only increases sub-second precision; it does not extend the type's year range.

**“Zero date is the standard way to represent an unknown date.”** No. Use NULL or an explicit business status.

## Conclusion

DATE is for calendar dates; DATETIME stores date and time without automatic time zone conversion and has a wide year range; TIMESTAMP represents an instant, converting between the session time zone and UTC, though limited to 2038 in mainstream MySQL versions. DATETIME and TIMESTAMP support fractional seconds from 0 to 6 digits in MySQL 5.6.4 and later.

Choose types based on business semantics, not just column names. Use DATE for dates, TIMESTAMP for instants within the supported range requiring time zone conversion, and DATETIME for calendar times or instants needing a wider range under an explicit UTC convention. Combine time_zone policy, SQL mode, and boundary testing so date/time data remains consistent across MySQL versions and deployment environments.
