# Troubleshooting

## Incorrect Datetime, Zero Dates, and Timezone Conversion Errors

Date and time errors in MySQL often emerge when data crosses multiple layers: a form accepts a date in a local format, a Java application parses the string, Connector/J passes the value via JDBC, MySQL applies SQL mode and session time zone, and a query reads the data back in another time zone. A value may be rejected, turned into a zero date, shifted by several hours, or become unreadable by the driver.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, optimizing queries, managing privileges, performing backups, and handling relational database operations. This lesson applies those skills to diagnose datetime data, understand SQL mode and time zones, inspect the JDBC flow, and repair legacy data without losing business meaning.

Examples target modern MySQL 8.0/8.4, InnoDB, and Connector/J. Certain behaviors depend on version, SQL mode, column type, and driver; record the environment's actual configuration before drawing conclusions.

### 1. Distinguishing DATE, DATETIME, and TIMESTAMP

Choosing the right data type is the first step to preventing errors. These three types do not share the same semantics:

| Type | Meaning | Converts by Session Time Zone? | General Range |
|---|---|---|---|
| DATE | Calendar date, no time | No | 1000-01-01 to 9999-12-31 |
| DATETIME | Date and time by local wall clock / business context | No | 1000-01-01 00:00:00 to 9999-12-31 23:59:59 |
| TIMESTAMP | A point in time (instant) | Yes; converts session time zone to UTC on write and back on read | Typically 1970-01-01 00:00:01 UTC to 2038-01-19 03:14:07 UTC |

`TIME`, `DATETIME`, and `TIMESTAMP` can store fractional seconds with precision from 0 to 6 digits, such as `DATETIME(6)` or `TIMESTAMP(6)`. If a column has precision 0, input microseconds may be rounded or truncated depending on SQL mode and version rules.

#### 1.1. When to Use Each Type?

- Use `DATE` for birth dates, invoice dates, holidays, or effective dates without a time of day.
- Use `DATETIME` for store opening hours, local-time appointments, or business timestamps recorded as calendar values that should not shift when viewed from another time zone.
- Use `TIMESTAMP` for event timestamps representing the same global instant across the system, such as record creation time, webhook receipt, or log entries.

`TIMESTAMP` stores values in UTC and converts using the session `time_zone` on write/read. It does not store the original time zone name or offset selected by the user. `DATETIME` stores date/time components exactly as supplied, with no awareness of which time zone they belong to.

For example, given the same string `2026-06-01 09:00:00`:

- Stored in `DATETIME`, MySQL keeps `09:00:00` as a calendar value.
- Stored in `TIMESTAMP` in an `Asia/Ho_Chi_Minh` session, MySQL interprets `09:00` in that session's zone, converts it to UTC for storage, and converts back to the reader's session `time_zone` on retrieval.

Do not pick `TIMESTAMP` merely because a column name contains the word "timestamp". If you need to store a meeting scheduled at 09:00 in a specific city, store the IANA time zone or location rule as well; a standalone `DATETIME` does not carry enough information.

### 2. Zero Dates, Zero-in-Date, and Invalid Dates

MySQL may encounter special or invalid values in historical data:

| Form | Example | Issue |
|---|---|---|
| Zero date | 0000-00-00 | Does not represent a valid calendar date |
| Zero month | 2024-00-15 | Month is zero |
| Zero day | 2024-01-00 | Day is zero |
| Out-of-calendar date | 2024-02-30 | February has no 30th day |
| Invalid month | 2024-13-01 | Month out of range |
| Invalid leap year | 2023-02-29 | 2023 is not a leap year |

Zero dates were often used as sentinels in legacy systems to represent "unknown", "not applicable", or "not entered". This creates data ambiguity and can conflict with strict SQL modes, Java drivers, or newer MySQL versions.

If a field does not have a date yet, prefer `NULL` when business rules allow. If a truly meaningful default date exists, pick a valid date and document its meaning in the schema/application. Never replace every zero date with an arbitrary date.

### 3. SQL Mode Determines How MySQL Handles Invalid Dates

SQL mode controls whether MySQL rejects, warns on, or accepts invalid datetime data. Before investigating, inspect both global and session modes:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode,
  @@SESSION.time_zone AS session_time_zone,
  @@GLOBAL.time_zone AS global_time_zone;
~~~

Key modes to know:

| SQL mode | Effect |
|---|---|
| STRICT_TRANS_TABLES | Strict mode for transactional tables; invalid values typically error instead of silently adjusting |
| STRICT_ALL_TABLES | Applies strict behavior more broadly across storage engines |
| NO_ZERO_DATE | Controls zero date `0000-00-00` |
| NO_ZERO_IN_DATE | Controls dates with zero month or zero day |
| ALLOW_INVALID_DATES | Relaxes full date validation for `DATE`/`DATETIME`; still checks month 1-12 and day 1-31 ranges |
| TIME_TRUNCATE_FRACTIONAL | Truncates fractional seconds instead of rounding when input precision exceeds column precision |

`NO_ZERO_DATE` and `NO_ZERO_IN_DATE` have been deprecated in newer MySQL 8.0 releases; how they interact with strict mode depends on the version. Do not rely on enabling those two modes alone as a long-term solution. Check documentation for your exact version and establish a consistent strict policy for the application.

`ALLOW_INVALID_DATES` does not make an invalid date valid. It allows storing values like `2024-02-31` in `DATE`/`DATETIME` when enabled; subsequent date arithmetic may lack business meaning. Use it only for controlled ingestion cases, never to bypass validation.

Test example in a dedicated session:

~~~sql
SET SESSION sql_mode =
  'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,NO_ENGINE_SUBSTITUTION';

CREATE TEMPORARY TABLE date_mode_test (
  id BIGINT PRIMARY KEY,
  event_date DATE NULL
) ENGINE=InnoDB;

INSERT INTO date_mode_test VALUES (1, '2024-02-29');
-- The values below should be tested individually as they may raise errors:
INSERT INTO date_mode_test VALUES (2, '2024-02-30');
INSERT INTO date_mode_test VALUES (3, '0000-00-00');
~~~

Do not run the full example in production. Failing statements may abort a script; use a test database and inspect `SHOW WARNINGS` immediately after any operation that might emit warnings.

### 4. Analyzing Date Parsing and Conversion Errors

Applications often receive dates as strings. Never assume MySQL will infer a user's locale format. A string like `03/04/2026` could mean April 3 or March 4.

Prefer unambiguous exchange formats:

- `DATE`: `YYYY-MM-DD`.
- `DATETIME`: `YYYY-MM-DD HH:MM:SS[.fraction]`.
- `TIMESTAMP` instant: pass an instant with explicit timezone/offset at the application layer, then convert according to connection policy.

If parsing in SQL is required, `STR_TO_DATE()` takes a string and a format string:

~~~sql
SELECT
  STR_TO_DATE('2026-04-03', '%Y-%m-%d') AS parsed_date,
  STR_TO_DATE('03/04/2026', '%d/%m/%Y') AS day_first_date,
  STR_TO_DATE('03/04/2026', '%m/%d/%Y') AS month_first_date;
~~~

The last two formats produce two different dates. Format strings must come from a data contract, not guesses based on server locale.

Check parse results before writing:

~~~sql
SELECT
  STR_TO_DATE('2024-02-29', '%Y-%m-%d') AS leap_day,
  STR_TO_DATE('2023-02-29', '%Y-%m-%d') AS invalid_leap_day,
  STR_TO_DATE('2024-13-01', '%Y-%m-%d') AS invalid_month;
SHOW WARNINGS;
~~~

Full validation behavior of `STR_TO_DATE()` changed across MySQL 8.0 releases; starting in 8.0.35, the function performs stricter calendar range checking and can raise errors for invalid dates that previously returned unnormalized values. When upgrading, re-run parsing test suites on the exact target version.

Avoid using `INSERT IGNORE` to "clean" data. `IGNORE` can downgrade errors into warnings and allow values to be adjusted or substituted. After importing, read warnings and reconcile row counts; better yet, parse and validate in staging before writing to main tables.

### 5. Diagnosing Anomalous Date Data

First check column types and schema:

~~~sql
SHOW CREATE TABLE appdb.orders;

SELECT
  COLUMN_NAME,
  DATA_TYPE,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  DATETIME_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME IN ('created_at', 'delivery_date');
~~~

Check `NULL`s and zero dates:

~~~sql
SELECT
  COUNT(*) AS total_rows,
  SUM(delivery_date IS NULL) AS null_rows,
  SUM(CAST(delivery_date AS CHAR) = '0000-00-00') AS zero_date_rows,
  SUM(CAST(created_at AS CHAR) = '0000-00-00 00:00:00') AS zero_timestamp_rows
FROM appdb.orders;
~~~

Check zero date parts or anomalous date strings during an audit:

~~~sql
SELECT order_id, delivery_date
FROM appdb.orders
WHERE MONTH(delivery_date) = 0
   OR DAYOFMONTH(delivery_date) = 0;
~~~

Applying `MONTH()` and `DAYOFMONTH()` to a column can force MySQL to scan many rows; this audit query can be expensive on large tables. Run off-peak or restrict by partition/key range if needed. For server-normalized `DATE`/`DATETIME` data, invalid dates may already have been rejected before storage; anomalies usually trace back to legacy SQL modes, imports, or data created on older versions.

Cross-check raw data if the source is CSV or an API. If only the converted `DATE` column remains, it may be impossible to tell whether the original input string was `03/04/2026` or `04/03/2026`. Staging should keep a raw text column and parse status to preserve evidence.

### 6. Understanding Server, Session, and Data Time Zones

MySQL has multiple timezone layers:

- `system_time_zone`: operating system time zone detected at server startup.
- `GLOBAL time_zone`: default applied to new sessions.
- `SESSION time_zone`: time zone of the current connection; affects `TIMESTAMP` and related time functions.

Check:

~~~sql
SELECT
  @@system_time_zone AS system_time_zone,
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  NOW() AS session_now,
  UTC_TIMESTAMP() AS utc_now,
  CURRENT_TIMESTAMP() AS current_timestamp_value;
~~~

If session `time_zone` is `SYSTEM`, MySQL uses the system time zone. Do not assume all sessions share the same time zone; a connection pool may retain a session modified by a previous request.

Setting UTC for application sessions is a common policy:

~~~sql
SET SESSION time_zone = '+00:00';
SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP();
~~~

If the application uses a pool, set the session time zone via verified connection initialization settings or guarantee it resets when returning connections. Never allow one request to change `time_zone` and hand a dirty connection to the next request.

### 7. TIMESTAMP Converts, DATETIME Does Not

When writing a `TIMESTAMP`, MySQL interprets the input in the session `time_zone` and converts it to UTC for storage. On read, MySQL converts UTC into the current session `time_zone`. Thus, two sessions in different time zones see different wall-clock times for the same `TIMESTAMP`, representing the same instant.

`DATETIME` does not automatically convert. Writing `09:00` reads back as `09:00` in both a UTC session and an `Asia/Ho_Chi_Minh` session. If an application treats `DATETIME` as UTC while users entered local time, the data becomes semantically wrong even though the displayed strings look valid.

Example:

~~~sql
CREATE TEMPORARY TABLE time_zone_demo (
  id INT PRIMARY KEY,
  happened_at TIMESTAMP,
  wall_clock DATETIME
);

SET SESSION time_zone = '+07:00';
INSERT INTO time_zone_demo
VALUES (1, '2026-06-01 09:00:00', '2026-06-01 09:00:00');

SET SESSION time_zone = '+00:00';
SELECT * FROM time_zone_demo;
~~~

In the example, `happened_at` displays as `02:00` UTC while `wall_clock` stays `09:00`. This is the same `TIMESTAMP` instant viewed from a different session; `DATETIME` preserves the calendar components unchanged.

`TIMESTAMP` has a narrower range than `DATETIME` in common MySQL builds, ending in January 2038. Do not store far-future or early historical dates in `TIMESTAMP` if they can exceed its range; choose `DATETIME` when a wide year range is needed and manage time zones explicitly at the application layer.

### 8. Timezone Tables and CONVERT_TZ()

MySQL supports named time zones like `Asia/Ho_Chi_Minh` or `America/New_York` when timezone tables are loaded. Fixed offsets like `+07:00` do not require DST rules, whereas IANA names encode historical rules and local statutory changes.

Test conversion:

~~~sql
SELECT
  CONVERT_TZ(
    '2026-06-01 09:00:00',
    'Asia/Ho_Chi_Minh',
    'UTC'
  ) AS converted_utc;
~~~

If the result is `NULL`, check the timezone name and timezone tables. On Linux, administrators usually load system timezone data via `mysql_tzinfo_to_sql` and import it into the `mysql` schema; exact steps depend on OS and admin privileges. After updating OS timezone data, update MySQL's timezone tables per operational procedures and restart the server per version guidance so cached timezone values reload.

Do not substitute a fixed offset for a named time zone when the region observes DST or rule changes. For example, a region may shift between UTC-5 and UTC-4 seasonally; a fixed offset cannot represent historical or future instants accurately.

### 9. Daylight Saving Time: Nonexistent and Repeated Hours

When a region transitions to Daylight Saving Time, clocks jump forward across an interval. Certain local times never exist. When DST ends, an hour occurs twice.

This creates two edge cases:

- **Gap:** a nonexistent local time—for instance, clocks jump from 01:59 to 03:00; 02:30 has no corresponding instant.
- **Fold:** a repeated local time—for instance, 01:30 occurs twice with two different UTC offsets.

A standalone `DATETIME` cannot distinguish the two instants in a fold and cannot prove whether a time falls in a gap. If business logic stores future schedules in local time, store:

- The local date/time selected by the user.
- The IANA time zone name, e.g., `America/New_York`.
- The gap/fold resolution policy (reject, shift to next valid time, pick earlier/later offset, or prompt user confirmation).
- The resolved UTC instant when the business needs a concrete execution point.

DST rules can change by legislation. For long-term schedules, future instants may need recalculation when the timezone database updates. Never store only the current offset if local rules must apply in the future.

### 10. Time Functions That Commonly Cause Confusion

| Function | Behavior to Remember |
|---|---|
| NOW() / CURRENT_TIMESTAMP() | Returns current time in session `time_zone` |
| UTC_TIMESTAMP() | Returns current time in UTC |
| CURDATE() | Current date in session `time_zone` |
| UTC_DATE() | Current date in UTC |
| UNIX_TIMESTAMP() | No args: current epoch; with datetime arg: interpreted in session `time_zone` |
| FROM_UNIXTIME(epoch) | Converts epoch to datetime in session `time_zone` |
| CONVERT_TZ(dt, from_tz, to_tz) | Converts between two time zones; returns `NULL` if names/inputs are invalid or timezone tables are missing |

Example:

~~~sql
SELECT
  NOW(),
  UTC_TIMESTAMP(),
  UNIX_TIMESTAMP('2026-06-01 09:00:00'),
  FROM_UNIXTIME(1780304400),
  CONVERT_TZ('2026-06-01 09:00:00', '+07:00', '+00:00');
~~~

Epoch `1780304400` corresponds to `2026-06-01 09:00:00` UTC; `FROM_UNIXTIME()` displays that instant in the current session `time_zone`.

Never mix epoch values, local datetimes, and UTC datetimes in the same column without a strict convention. When filtering time ranges, prefer half-open intervals `[start, end)`:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE created_at >= '2026-06-01 00:00:00'
  AND created_at <  '2026-06-02 00:00:00';
~~~

This avoids guessing end-of-day values like `23:59:59.999999` and works reliably on columns with fractional seconds.

### 11. Testing and Diagnosing from Java/Connector/J

Java has temporal types with distinct semantics:

| Java Type | Appropriate Meaning | Common MySQL Type |
|---|---|---|
| LocalDate | Calendar date | DATE |
| LocalDateTime | Date/time without time zone | DATETIME |
| Instant | An instant on the UTC timeline | TIMESTAMP with explicit UTC config |
| java.sql.Timestamp | Nanosecond-precision timestamp; object carries no zone ID, requiring timezone convention on bind/read | Choose TIMESTAMP or DATETIME based on column semantics and driver config |

Do not use `LocalDateTime` to represent a global instant without a time zone. Do not use `Instant` for a local schedule not yet resolved to an instant.

Example storing an instant under a UTC policy:

~~~java
Instant occurredAt = Instant.parse("2026-06-01T02:00:00Z");
Timestamp value = Timestamp.from(occurredAt);

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "INSERT INTO appdb.events(occurred_at) VALUES (?)")) {
    ps.setTimestamp(1, value);
    ps.executeUpdate();
}
~~~

For consistent results, configure Connector/J and session `time_zone` according to a unified policy. Modern Connector/J versions offer properties like `connectionTimeZone`, `forceConnectionTimeZoneToSession`, and `preserveInstants`; check documentation for your exact driver version because how the driver interprets and converts temporal types depends on these settings. You can use `setTimestamp`/`getTimestamp` overloads with `Calendar` when explicit JDBC timezone control is needed.

Round-trip verification example:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT occurred_at FROM appdb.events WHERE event_id = ?")) {
    ps.setLong(1, eventId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Instant actual = rs.getTimestamp("occurred_at").toInstant();
            // Compare with the written instant according to column precision.
        }
    }
}
~~~

If the column is `DATETIME`, do not use the round-trip above to assume MySQL stored a time zone. Explicitly convert `LocalDateTime` according to the business time zone at the application layer.

#### 11.1. Connector/J and Zero Dates

Some legacy systems return zero dates to JDBC. Connector/J provides `zeroDateTimeBehavior` with options such as `EXCEPTION`, `CONVERT_TO_NULL`, and `ROUND` depending on version. `EXCEPTION` helps detect anomalous data; `CONVERT_TO_NULL` can mask sentinel values in data; `ROUND` can fabricate a replacement date with wrong business meaning.

Fix data and schemas at the source rather than using driver flags to hide zero dates. If forced to read legacy data during a transition, record counts and converted values, then remove the compatibility workaround once migration completes.

### 12. Procedure for Repairing Zero Dates and Timezone Drift

Do not run bulk updates immediately upon finding zero dates. Follow these steps:

1. **Back up and preserve evidence:** create a restorable backup; record row counts, primary keys, and raw values.
2. **Classify meaning:** determine whether zero date means "unknown", "not applicable", bad import data, or a timezone bug.
3. **Check nullability:** verify whether the column allows `NULL` and whether the application handles `NULL` properly.
4. **Define mapping:** decide whether to convert to `NULL`, a valid date from another source, or a dedicated status.
5. **Run in staging:** apply the mapping on a copy, and reconcile row counts and business rules.
6. **Deploy in batches:** update by primary key in small transactions, saving checkpoints and logging row counts.
7. **Verify:** re-count zero dates, `NULL`s, and out-of-range values and compare with pre-fix reports.
8. **Tighten schema:** add constraints/validation once data is clean and applications are compatible.

If zero date means no date exists yet, convert to `NULL` only after ensuring the column allows `NULL` and downstream consumers are updated:

~~~sql
UPDATE appdb.orders
SET delivery_date = NULL
WHERE CAST(delivery_date AS CHAR) = '0000-00-00';
~~~

This is an example for a `DATE` column; `CAST` can force a table scan, so run it only during a controlled repair. Validate the predicate on your real version and data in staging first. On large tables, add primary key range predicates and commit in batches. If zero dates carry a distinct business meaning, keep a dedicated mapping rather than turning everything into `NULL`.

If data is wrong due to timezone drift, do not add/subtract a fixed hour offset across the entire table without knowing source time zones, time ranges, and DST rules. Determine:

- Which time zone the values were originally entered in.
- Whether the column is `TIMESTAMP` or `DATETIME`.
- The session `time_zone` at write time.
- Whether the driver/application converted values before sending.
- Whether records fall inside DST periods or timezone rule changes.

Then recompute instants per data group based on origin and cross-check against external logs/events. Timezone drift cannot be repaired accurately if source timezone info is lost and no independent evidence remains.

### 13. Safe Data Ingestion and Migration

For CSVs, legacy files, or APIs, never import strings directly into `DATE`/`DATETIME` columns before validation. Use a staging table storing raw values:

~~~sql
CREATE TABLE staging.order_dates (
  source_id BIGINT NOT NULL PRIMARY KEY,
  raw_date VARCHAR(80) NULL,
  parsed_date DATE NULL,
  parse_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  parse_error VARCHAR(255) NULL
) ENGINE=InnoDB;
~~~

Parsing workflow:

- Preserve `raw_date` for traceability.
- Validate against the declared format rather than guessing by locale.
- Parse to a date type in the application or via `STR_TO_DATE` with an explicit format.
- Validate calendar dates, leap years, and business bounds.
- Set `parse_status` to `VALID` or `INVALID` and record the error reason.
- Promote only `VALID` rows into production tables.

Do not rely on `NULLIF(raw_date, '0000-00-00')` as the sole cleanup step. It handles only one exact string and misses zero-in-date, whitespace, bad formats, or ambiguous time zones.

For type or timezone migrations, record MySQL version, SQL mode, session time zone, Connector/J version, and driver properties in the report. These details allow reproducing results when staging and production differ.

### 14. Boundary and Regression Testing

A datetime test suite should cover:

| Category | Sample Value | Expectation |
|---|---|---|
| Normal date | 2026-06-15 | Stored and read accurately |
| Leap day | 2024-02-29 | Valid |
| Invalid leap day | 2023-02-29 | Rejected |
| End of month | 2026-04-30, 2026-04-31 | One valid, one invalid |
| Zero date | 0000-00-00 | Rejected per policy |
| Zero-in-date | 2026-00-10, 2026-06-00 | Rejected per policy |
| Out of range | 2026-13-01 | Rejected |
| Fractional seconds | .123456 into DATETIME(6) | Exact precision preserved |
| Precision mismatch | .123456 into DATETIME(3) | Rounded/truncated per mode |
| UTC/session | Same TIMESTAMP read in +00:00 and +07:00 | Different display, same instant |
| DATETIME | Same value read in two session time zones | Time components unchanged |
| DST gap | Nonexistent local time | Handled per defined policy |
| DST fold | Repeated local time | Explicit instant/offset chosen |
| TIMESTAMP range | Values near limits | Within column bounds |

Also test `NOW()`, `UTC_TIMESTAMP()`, `FROM_UNIXTIME()`, and `CONVERT_TZ()` on real sessions. Test the connection pool by changing session `time_zone` in one request, then borrowing a connection again to confirm the baseline is restored.

After upgrading MySQL or Connector/J, re-run regression tests for:

- Date string parsing and warning/error behavior.
- Zero date compatibility.
- Mapping Java temporal types to SQL types.
- Session time zone on connect and reconnect.
- Microsecond precision.
- Timezone tables and `CONVERT_TZ`.
- DST gaps/folds and rule transition dates.

### 15. Troubleshooting by Symptom

| Symptom | Possible Cause | Investigation Method |
|---|---|---|
| Incorrect date value | Out-of-calendar date, zero date, or strict SQL mode | Read SQL mode, raw input, and `SHOW WARNINGS` |
| Zero date rejected after upgrade | Strict/zero-date behavior changed or different mode | Compare session/global SQL mode and source/target versions |
| JDBC throws exception reading dates | Zero date in data and `zeroDateTimeBehavior` | Query raw values directly, repair data, and check driver config |
| Timestamp shifted by 7 hours | Inconsistent session `time_zone` or driver conversion | Check `@@session.time_zone` and Connector/J configuration |
| `DATETIME` does not shift with timezone | `DATETIME` does not auto-convert | Re-verify column semantics and convert at application layer if needed |
| `TIMESTAMP` displays differently between CLI and Java | Two sessions use different time zones | Compare session time zones on each connection |
| `CONVERT_TZ` returns `NULL` | Bad timezone name or unloaded timezone tables | Verify IANA name and timezone tables |
| Schedules fire wrong around DST | Gap/fold time or storing only fixed offset | Store zone ID and local-time resolution policy |
| Dates altered after import | Ambiguous format, `IGNORE`, or `STR_TO_DATE` behavior | Cross-check raw input, warnings, and server version |
| Microseconds lost | Lower column precision or different driver mapping | Check `DATETIME_PRECISION` and round-trip behavior |
| Time drift after returning connection to pool | Earlier request altered session `time_zone` | Check session reset and connection initialization |

### 16. Checklist Before Fixing Datetime Errors

- [ ] Identified `DATE`, `DATETIME`, or `TIMESTAMP` and business semantics.
- [ ] Read global/session SQL mode and time zone.
- [ ] Distinguished zero date, zero-in-date, invalid dates, and `NULL`.
- [ ] Inspected raw data prior to parsing/import.
- [ ] Tested `STR_TO_DATE()` on the exact MySQL version.
- [ ] Recorded fractional seconds precision and rounding/truncation mode.
- [ ] Confirmed which session time zone is used when writing/reading `TIMESTAMP`.
- [ ] Checked Connector/J and Java temporal type mappings.
- [ ] Verified timezone tables and `CONVERT_TZ()` results.
- [ ] Identified DST gap/fold cases if storing local schedules.
- [ ] Backed up, tested mapping in staging, and confirmed business meaning before converting zero dates.
- [ ] Updated applications to handle `NULL` and time zones properly.
- [ ] Ran regression tests after fixes or upgrades.

### 17. Practice Exercise

A sales system stores `delivery_date` as `DATE`, `created_at` as `TIMESTAMP`, and `appointment_at` as `DATETIME`. After upgrading MySQL, a CSV import fails with `Incorrect date value`; some rows contain `0000-00-00`. Users in Vietnam see `created_at` shifted by seven hours compared to reports running on a UTC server. Appointments in a country observing DST run one hour early or late.

1. Which queries would you use to inspect SQL mode, global/session time zones, and column types?
2. Distinguish zero dates from invalid dates like `2024-02-30` and zero-in-date.
3. Why can a `TIMESTAMP` column like `created_at` display differently across two session time zones?
4. Why does `appointment_at` of type `DATETIME` not convert automatically?
5. Design a staging table to preserve raw CSV strings and flag parse errors.
6. How do you verify timezone tables and `CONVERT_TZ` for `Asia/Ho_Chi_Minh`?
7. Why can a standalone `DATETIME` not distinguish the two instants in a DST fold?
8. Plan how to convert zero dates to `NULL` or valid business values without losing information.

### 18. Operational Principles

Choose temporal types according to data meaning: `DATE` for calendar dates, `DATETIME` for calendar wall-clock times without auto-conversion, and `TIMESTAMP` for instants converted per session time zone. Use strict SQL mode, validate inputs before writing, and never use zero dates as sentinels for missing data. Standardize timezone policies across MySQL, Connector/J, and the application; prefer UTC for instants while preserving IANA time zones for local schedules. When incidents happen, preserve raw inputs, inspect session settings, verify timezone tables, and test migrations in staging before touching production data.
