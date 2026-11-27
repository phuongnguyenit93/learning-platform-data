# Time Zone Conversion Differences Between TIMESTAMP and DATETIME

This lesson belongs to the **Date and Time** chapter of the `DATABASE_MYSQL` module. The module aims to master MySQL from table design, data types, keys, and SQL queries through indexing, transactions, concurrency control, reading execution plans, query tuning, access control, backup, and operational troubleshooting for relational databases. Storing instants with accurate semantics is critical for logs, transactions, appointments, orders, synchronization, and multi-timezone applications.

After this lesson, you can distinguish an absolute instant from local clock time, explain how MySQL converts `TIMESTAMP` by session time zone, understand why `DATETIME` preserves its calendar date/time value, configure sessions to UTC, handle DST-aware time zones, and plan data migrations between the two types.

## 1. Two Concepts to Distinguish: Instant vs. Clock Time

A string such as `2026-11-19 09:30:00` only describes a date and time on a clock face. Without a time zone or offset, we do not know which instant on the global timeline it corresponds to.

For example, the exact same instant can be displayed as follows:

| Representation | Value |
|---|---|
| UTC | `2026-11-19 02:30:00+00:00` |
| Vietnam | `2026-11-19 09:30:00+07:00` |
| A UTC-05:00 time zone | `2026-11-18 21:30:00-05:00` |

The three values above describe the same instant, yet their wall-clock times differ.

Distinguish the following:

- **Instant:** a unique point on the timeline, independent of which time zone the viewer is in.
- **Local date-time / wall-clock time:** the calendar date and time at a location, e.g. 09:00 in Ho Chi Minh City.
- **Time zone:** a set of rules determining the UTC offset at each point in time. A time zone can change its offset historically or due to DST regulations.
- **UTC offset:** the specific difference from UTC at a point in time, e.g. `+07:00`. A fixed offset does not capture all historical or future rules of a time zone.

The `TIMESTAMP` and `DATETIME` types differ primarily in how MySQL handles these semantics.

## 2. How Do TIMESTAMP and DATETIME Differ?

**TIMESTAMP** represents an instant. MySQL converts the value from the session time zone to UTC on write, then converts from UTC back to the session time zone on read.

**DATETIME** represents a date and time as a calendar value. MySQL stores and returns that value without automatically converting it according to the session time zone.

| Criterion | TIMESTAMP | DATETIME |
|---|---|---|
| Common semantics | Absolute instant | Calendar date/time / local time |
| On write | Converts from session time zone to UTC for storage | Stores supplied date/time; no automatic time zone conversion |
| On read | Converts from UTC to session time zone | Returns the stored value |
| Preserves original time zone name/offset? | No | No |
| Depends on session `time_zone` | Yes | No, for stored values |
| Year range in MySQL 9.7 | 1970 to 2038 | 1000 to 9999 |
| Fractional seconds precision | Up to 6 digits | Up to 6 digits |
| Best suited for | Transaction timestamps, events, logs | Local appointment times, opening hours, business date/times not auto-converted to UTC |

One point to keep in mind: `TIMESTAMP` does not store a time zone name like `Asia/Ho_Chi_Minh`. It stores the instant in UTC. The time zone only participates in conversion during writes and reads.

Similarly, `DATETIME` does not store metadata indicating whether a value belongs to Vietnam time or a particular offset. If you need to know which region a local time belongs to, store the time zone information separately.

### Value Ranges

According to the MySQL 9.7 Reference Manual:

| Type | Supported Range |
|---|---|
| `DATETIME` | `1000-01-01 00:00:00` to `9999-12-31 23:59:59` |
| `TIMESTAMP` | `1970-01-01 00:00:01 UTC` to `2038-01-19 03:14:07 UTC` |

The upper bound of `TIMESTAMP` is an important factor when designing systems storing far-future dates or historical data outside this range. `DATETIME` has a wider range, though it does not provide absolute-instant semantics on its own.

### Fractional Seconds Precision

Both types support fractional seconds precision (FSP) from 0 to 6:

- `TIMESTAMP` is equivalent to `TIMESTAMP(0)` if FSP is omitted.
- `DATETIME` is equivalent to `DATETIME(0)` if FSP is omitted.
- `TIMESTAMP(6)` and `DATETIME(6)` store down to microseconds.

Example:

~~~sql
CREATE TABLE time_precision_demo (
    id BIGINT UNSIGNED PRIMARY KEY,
    event_ts TIMESTAMP(6) NOT NULL,
    scheduled_local DATETIME(6) NOT NULL
);
~~~

If a value has more fractional-second digits than the column's FSP, MySQL rounds by default. You can use the `TIME_TRUNCATE_FRACTIONAL` SQL mode if the business requires truncating excess digits instead of rounding.

## 3. How TIMESTAMP Conversion Works

When the session is in `+07:00`, the statement:

~~~sql
INSERT INTO event_log (occurred_at)
VALUES ('2026-11-19 09:30:00');
~~~

is interpreted by MySQL as 09:30 in the session time zone. The server converts it to 02:30 UTC and stores it.

When read in a `+00:00` session, the value displays as 02:30. When read in a `+07:00` session, it displays again as 09:30.

Diagram:

~~~mermaid
flowchart TD
    A[Client sends 09:30 in UTC+07] --> B[Session time_zone = +07:00]
    B --> C[MySQL converts to 02:30 UTC]
    C --> D[(Store TIMESTAMP in UTC)]
    D --> E[Session time_zone = +00:00]
    E --> F[Reads back 02:30]
    D --> G[Session time_zone = +07:00]
    G --> H[Reads back 09:30]
~~~

The displayed values differ, yet the stored instant remains one and the same.

### Hands-On Test

Create a table:

~~~sql
CREATE TABLE event_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

Set the session time zone to UTC+00:00 and insert a value:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log (description, occurred_at)
VALUES ('test event', '2026-11-19 02:30:00.123456');
~~~

Read in the same session:

~~~sql
SELECT
    id,
    description,
    occurred_at,
    @@session.time_zone AS session_time_zone
FROM event_log;
~~~

The result shows hour 02:30.

Switch the session to UTC+07:00 and read again:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT
    id,
    description,
    occurred_at,
    @@session.time_zone AS session_time_zone
FROM event_log;
~~~

The displayed value is 09:30. The microsecond portion is preserved.

Reset the session back to UTC:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

This test shows that `TIMESTAMP` stores a single instant while its display depends on the reading session.

## 4. How DATETIME Works: Preserving Calendar Clock Time

With `DATETIME`, MySQL does not automatically convert values by session time zone on write or read.

Create a table:

~~~sql
CREATE TABLE appointment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(100) NOT NULL,
    starts_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

Set the session to UTC+07:00 and write:

~~~sql
SET SESSION time_zone = '+07:00';

INSERT INTO appointment (title, starts_at)
VALUES ('Team meeting', '2026-11-19 09:30:00.123456');
~~~

Read in the UTC+07:00 session:

~~~sql
SELECT starts_at
FROM appointment;
~~~

The result is 09:30.

Switch the session to UTC+00:00:

~~~sql
SET SESSION time_zone = '+00:00';

SELECT starts_at
FROM appointment;
~~~

The result is still 09:30. MySQL does not automatically shift it to 02:30.

This is the intended behavior of `DATETIME`: the stored value is a calendar clock time, not an instant normalized to UTC.

### When Is This Desirable?

Suppose a store in Vietnam opens at 09:00 every day. The opening time is a local rule. If an administrator changes the session time zone, the store's opening hour must still be 09:00.

Similarly, an appointment may be created with the meaning “09:00 at the clinic in Hanoi”. The value 09:00 must be preserved as local time. To convert it into a specific instant, the system needs the location's time zone and its DST handling policy if the region observes DST.

## 5. Time Zone Configuration in MySQL

MySQL maintains multiple levels of time zone configuration:

| Variable | Scope | Meaning |
|---|---|---|
| `system_time_zone` | Read-only | OS time zone detected by the server at startup |
| `@@GLOBAL.time_zone` | Global | Default time zone for new sessions |
| `@@SESSION.time_zone` | Session | Time zone of the current connection |

By default, global `time_zone` is `SYSTEM`. When a client connects, its session inherits the value from global. The client can change its own connection time zone without affecting other sessions.

Check them:

~~~sql
SELECT
    @@system_time_zone AS system_time_zone,
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone;
~~~

### Using Fixed Offsets

UTC offsets can be used, such as:

~~~sql
SET SESSION time_zone = '+00:00';
SET SESSION time_zone = '+07:00';
SET SESSION time_zone = '-05:00';
~~~

Fixed offsets are easy to configure and do not require loading time zone tables. However, they only represent a constant shift. If a region applies DST or changes its time zone rules, a fixed offset does not automatically adjust with the calendar.

### Using Named Time Zones

You can set an IANA time zone name:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';
SET SESSION time_zone = 'Europe/Amsterdam';
SET SESSION time_zone = 'America/New_York';
~~~

Named time zones provide regional rules, including historical offset changes and DST.

To use named time zones, the time zone tables in the `mysql` schema must be loaded and kept up to date. Without them, MySQL may report:

~~~text
ERROR 1298 (HY000): Unknown or incorrect time zone
~~~

On operating systems with zoneinfo, administrators can load the data using the `mysql_tzinfo_to_sql` utility. Example on Linux:

~~~bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql
~~~

This is an administrative operation requiring appropriate privileges. When the operating system updates its time zone data, evaluate reloading MySQL's time zone tables to keep conversion rules current.

### Setting the Server Default Time Zone

You can configure it at startup:

~~~ini
[mysqld]
default-time-zone = '+00:00'
~~~

Or an administrator can set global while the server is running:

~~~sql
SET GLOBAL time_zone = '+00:00';
~~~

Changing global only affects new connections. Existing open sessions retain their own values until changed or reconnected.

The privilege required to modify global system variables is `SYSTEM_VARIABLES_ADMIN`; `SUPER` is the legacy deprecated privilege.

## 6. Why Should Sessions Be Standardized on UTC?

An application typically consists of multiple components:

- API servers running in one region.
- Background workers running in another region.
- MySQL Server running on a cloud host with its own OS time zone.
- Administrators connecting with Workbench from personal machines.
- Reporting services reading data from replicas.

If each connection uses a different time zone, the same TIMESTAMP column can display different values. While not wrong at the storage level, this easily causes confusion during logging, comparison, reconciliation, and debugging.

A common convention is:

1. All application connections set session `time_zone = '+00:00'`.
2. Store event instants using `TIMESTAMP` when within the supported year range.
3. APIs send and receive instants in ISO 8601 format with explicit offsets or UTC.
4. Convert to local time zones only in the UI layer when presenting to users.
5. For local appointments, store the IANA time zone name separately to preserve business semantics.

Example connection initialization:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

The application should execute this during connection initialization or configure it in the connector. When using a connection pool, ensure session state is reset when reusing connections; never assume a fresh connection is created for every request.

## 7. Date and Time Functions Affected by Time Zone

It is not only TIMESTAMP columns that are affected. Several temporal functions also use the session time zone.

| Function | Result |
|---|---|
| `NOW()` | Current date and time in the session time zone |
| `CURRENT_TIMESTAMP()` | Equivalent to NOW(), in the session time zone |
| `CURTIME()` | Current time in the session time zone |
| `UTC_TIMESTAMP()` | Current date and time in UTC |
| `UTC_DATE()` | Current date in UTC |
| `UNIX_TIMESTAMP()` | Unix timestamp of the current instant |
| `UNIX_TIMESTAMP(datetime)` | Interprets the DATETIME argument in the session time zone and converts to a Unix timestamp |
| `FROM_UNIXTIME(epoch)` | Converts a Unix timestamp into a date/time in the session time zone |
| `CONVERT_TZ(dt, from_tz, to_tz)` | Converts a date/time value from a source time zone to a target time zone |

Inspect the functions:

~~~sql
SELECT
    NOW(6) AS session_now,
    CURRENT_TIMESTAMP(6) AS current_timestamp_value,
    UTC_TIMESTAMP(6) AS utc_now,
    UNIX_TIMESTAMP() AS unix_epoch,
    @@session.time_zone AS session_time_zone;
~~~

If the session is UTC+07:00, `NOW()` displays Vietnam time, whereas `UTC_TIMESTAMP()` returns UTC time.

### NOW() and UTC_TIMESTAMP() in DEFAULT

Both `TIMESTAMP` and `DATETIME` support automatic initialization and updating via `CURRENT_TIMESTAMP`.

Example:

~~~sql
CREATE TABLE audit_event (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    action_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
~~~

In this example:

- `created_at` is TIMESTAMP. The current time in the session is converted to UTC for storage.
- `updated_at` is DATETIME. CURRENT_TIMESTAMP returns the session time and that value is stored as a DATETIME without auto-converting on read.

If you want a DATETIME column to follow a UTC convention, ensure the sessions inserting and updating values are set to UTC. A DATETIME column does not know on its own that the application intends it to store UTC.

### CONVERT_TZ()

Example converting 09:00 in UTC+07:00 to UTC:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-19 09:00:00',
    '+07:00',
    '+00:00'
) AS utc_value;
~~~

The result is 02:00 UTC.

You can convert between named time zones:

~~~sql
SELECT CONVERT_TZ(
    '2026-07-15 09:00:00',
    'Asia/Ho_Chi_Minh',
    'Europe/Amsterdam'
) AS amsterdam_time;
~~~

For named time zones, MySQL requires loaded timezone tables. If a time zone is invalid or missing from the tables, the function may return NULL. Verify the output before using it in bulk write operations.

## 8. Offsets in Date/Time Literals: An Easy-to-Miss Detail

Starting in MySQL 8.0.19, DATETIME/TIMESTAMP literals can include a UTC offset, for example:

~~~sql
'2026-11-19 09:30:00+07:00'
'2026-11-19 02:30:00+00:00'
'2026-11-18 21:30:00-05:00'
~~~

These literals describe the same instant. MySQL honors the offset when processing the input value, yet does not store the original offset as a separate part of the column.

There is an important difference:

- For `TIMESTAMP`, the offset defines the absolute instant; on read, MySQL still displays it according to the session time zone.
- For `DATETIME`, the offset in the literal is used to convert the value to the session time zone at INSERT time. MySQL then stores the converted date/time components and discards the original offset. On SELECT, no offset is displayed.

Example on MySQL 8.0.19 or later:

~~~sql
CREATE TABLE offset_demo (
    id INT PRIMARY KEY,
    event_ts TIMESTAMP NOT NULL,
    event_dt DATETIME NOT NULL
);

SET SESSION time_zone = '+00:00';

INSERT INTO offset_demo (id, event_ts, event_dt)
VALUES (
    1,
    '2026-11-19 09:30:00+07:00',
    '2026-11-19 09:30:00+07:00'
);

SELECT * FROM offset_demo;
~~~

In the UTC session, both values display as 02:30. For TIMESTAMP, that is the normalized UTC instant. For DATETIME, that is the calendar value converted to the UTC session time and stored; DATETIME no longer retains information that the original input was UTC+07:00.

If you switch the session to UTC+07:00:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT * FROM offset_demo;
~~~

TIMESTAMP displays 09:30. DATETIME remains 02:30 because the stored value is a time-zone-naive DATETIME.

Do not use DATETIME if the requirement is to store and retrieve the exact offset sent by the client. Store the offset or time zone name in a separate column if the business needs to retain it.

## 9. DST and Non-Unique Local Time Cases

Some time zones observe Daylight Saving Time (DST). When clocks spring forward to summer time or fall back to standard time, two special situations arise:

- **Nonexistent time:** the clock skips over an interval. For example, 01:59 jumps directly to 03:00, so 02:30 does not occur on that date.
- **Repeated (ambiguous) time:** the clock moves back one hour. A local time such as 02:30 can occur twice, corresponding to two different UTC instants.

For example, in parts of Europe when DST ends, two distinct UTC instants can both display as 02:30 in the local time zone.

The MySQL Reference Manual illustrates two UTC TIMESTAMP values:

~~~text
2018-10-28 00:30:00 UTC
2018-10-28 01:30:00 UTC
~~~

When read in the `MET` time zone, both can display as:

~~~text
2018-10-28 02:30:00
2018-10-28 02:30:00
~~~

The two values remain two distinct instants; only their local clock representation overlaps.

### Impact on DATETIME

DATETIME only stores calendar clock time. If you store `2026-10-25 02:30:00` in a region where 02:30 repeats, the DATETIME value alone does not indicate whether it is the first or second occurrence.

If the business needs to identify a unique instant, you must additionally store the offset, the time zone name along with an occurrence-selection rule, or directly store the resolved UTC instant.

### Impact on TIMESTAMP

TIMESTAMP stores the two distinct instants in UTC, though when displayed in a DST time zone they can look identical.

Furthermore, MySQL has an advanced caveat: during a DST-repeated hour, comparing a TIMESTAMP column against a local-time literal can produce different results between an indexed lookup and a table scan. The reason is that the indexed path compares UTC values inside the index, whereas a table scan converts values to the session time zone before comparing.

For sensitive queries in DST regions:

- Prefer a UTC session when filtering by instants.
- Pass UTC values or explicit offsets from the application.
- Avoid using an ambiguous local-time literal as an instant lookup key.
- Test both indexed and non-indexed queries if the application must handle local times inside DST regions.

### Designing Safe Appointments

For appointments in local time, store the necessary details:

~~~sql
CREATE TABLE appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    local_start DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    resolved_start_utc TIMESTAMP(6) NULL,
    PRIMARY KEY (id)
);
~~~

Meaning:

- `local_start`: the calendar time selected by the user.
- `time_zone_name`: the location's IANA time zone name, e.g. `Asia/Ho_Chi_Minh`.
- `resolved_start_utc`: the UTC instant resolved after applying time zone rules and DST policy.

If a local time falls in a nonexistent or repeated interval, the application must define how to handle it—for example rejecting, asking the user to choose an offset, or picking the first/last occurrence. Never let ambiguous data be silently resolved.

## 10. Choosing TIMESTAMP or DATETIME by Business Case

| Need | Typical Best Fit | Reason |
|---|---|---|
| Order creation timestamp | TIMESTAMP | Must pinpoint an absolute instant |
| Request receipt or event log timestamp | TIMESTAMP | Multiple servers/time zones must agree on the instant |
| Data synchronization timestamp | TIMESTAMP | Must compare event order on a unified timeline |
| Birth date/time or date printed on documents | DATETIME or DATE | It is a calendar value, not a global instant |
| Daily opening hour 09:00 | TIME or DATETIME depending on model | It is a local clock rule |
| Appointment at a location with its own time zone | DATETIME + time zone name; optionally UTC instant | Must preserve local time and regional rules |
| Timestamp beyond 2038 | DATETIME under UTC convention or another model | MySQL TIMESTAMP has a 2038 limit |
| Historical timestamp before 1970 | DATETIME under UTC convention or another model | Outside TIMESTAMP range |

Practical guidelines:

- If you need to store “when an event happened”, use an instant type and normalize to UTC.
- If you need to store “what the clock at a location reads”, store local time and its time zone.
- If you need both the absolute instant and what the user entered, store the UTC instant, local datetime, and timezone/offset.
- Do not use DATETIME assuming MySQL will convert it by time zone.
- Do not use TIMESTAMP for calendar values without instant semantics, such as dates of birth or opening hours.

## 11. Converting Between TIMESTAMP and DATETIME

Changing a column's data type can alter the meaning of existing data if you do not know what the old values represent.

Before converting, determine:

1. Is the current column TIMESTAMP or DATETIME?
2. Does the DATETIME currently store UTC or local time?
3. If local time, which time zone does it belong to?
4. Do any rows fall in a DST repeated or nonexistent interval?
5. Does the target column need to preserve absolute instants or calendar clock time?

### DATETIME (UTC) to TIMESTAMP

Suppose the legacy DATETIME column holds UTC values per application convention. Set the session to UTC before migrating data so MySQL interprets source values as UTC:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log_new (id, occurred_at)
SELECT id, old_datetime_utc
FROM event_log_old;
~~~

The target column `occurred_at` is TIMESTAMP. MySQL interprets source values in the UTC session and stores the corresponding UTC instants.

### DATETIME (Local Time) to TIMESTAMP

Suppose the legacy DATETIME holds local time in Vietnam:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';

INSERT INTO event_log_new (id, occurred_at)
SELECT id, old_local_datetime
FROM event_log_old;
~~~

MySQL interprets the DATETIME values as local time in the session and converts them to UTC when writing to TIMESTAMP.

Only perform this if the legacy data genuinely shares one time zone and values are uniquely resolvable. If data originates from multiple regions or includes ambiguous DST hours, process by group using the appropriate metadata.

### TIMESTAMP to DATETIME (UTC)

To create a DATETIME column storing values under a UTC convention, set the session to UTC before reading TIMESTAMP and writing to DATETIME:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log_utc_datetime (id, occurred_at_utc)
SELECT id, occurred_at
FROM event_log;
~~~

TIMESTAMP is read in UTC, and DATETIME receives and stores those UTC date/time components as-is.

### TIMESTAMP to DATETIME (Local Time)

To preserve the display in a specific local time zone:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';

INSERT INTO event_log_local_datetime (id, local_time)
SELECT id, occurred_at
FROM event_log;
~~~

The target DATETIME stores the local time after TIMESTAMP is converted by the session. Store the time zone name separately if you need to know which region the value belongs to.

### Safe Migration Process

Do not alter a column's type directly in production before confirming its semantics.

A controlled procedure:

1. Back up the data and record server/session time zone settings.
2. Profile source data, date ranges, NULLs, anomalous values, and data origins.
3. Add a parallel target column or table with the new type.
4. Explicitly set the session time zone for each conversion batch.
5. Backfill in batches to avoid long table locks.
6. Reconcile row counts, min/max values, and sample conversions across multiple time zones.
7. Verify data falling in DST transitions and values near TIMESTAMP range boundaries.
8. Test the application against the target data, confirming APIs and reports display accurately.
9. Cut over reads/writes once a rollback plan is in place.
10. Drop the old column only after thorough verification.

If legacy DATETIME values lack time zone metadata, the exact UTC instant cannot always be recovered in every case. You must consult the data source or business rules; changing the column type alone cannot infer a lost time zone.

## 12. Hands-On Lab: Observing Session Time Zone Conversion

This lab lets you compare the two types directly. Run it on a dedicated lab database.

### Step 1: Create the Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_time_zone_lab;
USE mysql_time_zone_lab;

CREATE TABLE time_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(100) NOT NULL,
    event_ts TIMESTAMP(6) NOT NULL,
    event_dt DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

### Step 2: Insert Data in UTC

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO time_demo (
    description,
    event_ts,
    event_dt
)
VALUES (
    'inserted in UTC',
    '2026-11-19 02:30:00.123456',
    '2026-11-19 02:30:00.123456'
);
~~~

Read the data:

~~~sql
SELECT
    description,
    event_ts,
    event_dt,
    @@session.time_zone AS session_zone
FROM time_demo;
~~~

Both values display as 02:30.

### Step 3: Switch Session to UTC+07:00

~~~sql
SET SESSION time_zone = '+07:00';

SELECT
    description,
    event_ts,
    event_dt,
    @@session.time_zone AS session_zone
FROM time_demo;
~~~

Observe:

- `event_ts` displays 09:30.
- `event_dt` still displays 02:30.

### Step 4: Insert More Data While Session Is UTC+07:00

~~~sql
INSERT INTO time_demo (
    description,
    event_ts,
    event_dt
)
VALUES (
    'inserted in UTC+07',
    '2026-11-19 09:30:00.123456',
    '2026-11-19 09:30:00.123456'
);
~~~

Switch back to UTC and read:

~~~sql
SET SESSION time_zone = '+00:00';

SELECT
    id,
    description,
    event_ts,
    event_dt
FROM time_demo
ORDER BY id;
~~~

Both TIMESTAMP rows represent the exact same UTC instant because they were entered in their respective sessions. DATETIME stored the two calendar clock values as passed, without normalizing them to a single instant.

### Step 5: Test CONVERT_TZ

~~~sql
SELECT
    CONVERT_TZ(
        '2026-11-19 09:30:00',
        '+07:00',
        '+00:00'
    ) AS utc_value;
~~~

The result is 02:30.

If timezone tables are loaded, test converting by region name:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-19 09:30:00',
    'Asia/Ho_Chi_Minh',
    'UTC'
) AS utc_value;
~~~

Compare the result against the fixed-offset conversion. For regions observing DST, a named time zone can yield different results from a fixed offset across different times of the year.

### Step 6: Inspect Unix Timestamps

~~~sql
SELECT
    event_ts,
    UNIX_TIMESTAMP(event_ts) AS epoch_seconds,
    FROM_UNIXTIME(UNIX_TIMESTAMP(event_ts)) AS back_in_session_zone
FROM time_demo;
~~~

Toggle the session between UTC and UTC+07:00 and re-run. Observe that the epoch value represents the instant, whereas `FROM_UNIXTIME()` displays according to the session.

### Step 7: Clean Up

~~~sql
DROP DATABASE mysql_time_zone_lab;
~~~

Run this only on the lab database just created. The command deletes all practice data in that database.

## 13. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check / Fix |
|---|---|---|
| TIMESTAMP displays differently on two machines | Two connections have different session time zones | Check `@@session.time_zone`, standardize sessions to UTC, or convert on display |
| DATETIME does not change when session changes | This is the intended behavior of DATETIME | If an instant is needed, determine the source time zone and convert explicitly |
| Unknown or incorrect time zone error | Timezone tables not loaded or invalid zone name | Use a fixed offset or load the timezone tables |
| Data shifted by 7 hours after migration | Source DATETIME was local time while session was UTC, or vice versa | Confirm source convention; set the matching session time zone before backfilling |
| Two events share the same local time | May fall inside a DST repeated hour | Store UTC instant or offset/zone plus an occurrence disambiguation policy |
| Appointment falls in a nonexistent hour | Region switched to DST and skipped that clock interval | Validate local time and ask the user to choose a valid time |
| TIMESTAMP value out of range | Instant before 1970 or after the 2038 limit | Use DATETIME with a UTC convention or another model |
| UNIX_TIMESTAMP returns 0 | Argument out of range or invalid | Inspect input value and session time zone |
| CONVERT_TZ returns NULL | Invalid time zone or unpopulated timezone tables | Verify zone name and load/update timezone tables |
| Connection pool exhibits inconsistent time zones | Session reused after other code changed `time_zone` | Reset `time_zone` on connection checkout or reset session state |

## 14. Application Date/Time Design Checklist

- [ ] Distinguished whether data represents an absolute instant or local clock time.
- [ ] Chosen TIMESTAMP or DATETIME according to the exact semantics.
- [ ] Checked year range, especially TIMESTAMP's 2038 limit.
- [ ] Determined required fractional seconds precision: 0 to 6.
- [ ] Standardized session time zone for the application, ideally UTC for instant pipelines.
- [ ] Verified global, session, and system time zone settings.
- [ ] Loaded timezone tables if using IANA time zone names.
- [ ] Stored time zone separately for local appointments.
- [ ] Defined handling for repeated or nonexistent DST hours.
- [ ] Verified `NOW()`, `UTC_TIMESTAMP()`, `UNIX_TIMESTAMP()`, and `FROM_UNIXTIME()`.
- [ ] Tested migration with sample data across multiple time zones.
- [ ] Verified connection pool does not retain unintended session state.

Choosing the right date/time type is more than picking a column format. Data semantics must align across APIs, application code, database, reports, and UI. For event instants, UTC is the cleanest convention across systems. For appointments, local time and the time zone name are business data that must be explicitly preserved.

## Official References

Behaviors and limits in this lesson were verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [The DATE, DATETIME, and TIMESTAMP Types](https://dev.mysql.com/doc/refman/9.7/en/datetime.html): value ranges, UTC conversion of TIMESTAMP, DATETIME, and offset literals.
2. [MySQL Server Time Zone Support](https://dev.mysql.com/doc/refman/9.7/en/time-zone-support.html): system/global/session time zones, named time zones, loading and updating timezone tables.
3. [Date and Time Literals](https://dev.mysql.com/doc/refman/9.7/en/date-and-time-literals.html): syntax for date/time literals with offsets, supported since MySQL 8.0.19, and how offsets are handled.
4. [Date and Time Functions](https://dev.mysql.com/doc/refman/9.7/en/date-and-time-functions.html): NOW, UTC_TIMESTAMP, CONVERT_TZ, UNIX_TIMESTAMP, and FROM_UNIXTIME.
5. [Fractional Seconds in Time Values](https://dev.mysql.com/doc/refman/9.7/en/fractional-seconds.html): microsecond precision and rounding/truncation of fractional seconds.
6. [Indexed Lookups from TIMESTAMP Columns](https://dev.mysql.com/doc/refman/9.7/en/timestamp-lookups.html): query limitations when DST causes local times to be non-unique.
7. [Automatic Initialization and Updating for TIMESTAMP and DATETIME](https://dev.mysql.com/doc/refman/9.7/en/timestamp-initialization.html): DEFAULT CURRENT_TIMESTAMP and ON UPDATE CURRENT_TIMESTAMP.
8. [MySQL 8.0 Release Notes — Changes in MySQL 8.0.19](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-19.html): added support for offsets in datetime literals.
