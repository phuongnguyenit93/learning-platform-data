# Zero Dates, Invalid Dates, and the Impact of SQL Mode

MySQL can encounter special date/time values such as **zero dates** (0000-00-00), dates with zero components (2024-00-15, 2024-02-00), or nonexistent calendar dates (2024-02-31). Whether the server accepts, warns on, or rejects these values depends on the column type, SQL mode, storage engine, and MySQL version.

These values commonly arise when importing data from legacy systems, loading CSVs, using invalid default values, or when applications pass unvalidated date strings. Without consistent handling, invalid temporal data can break migrations, yield confusing query results, skew reports, and trigger errors when mapping to Java date/time types.

In the **DATABASE_MYSQL** module, temporal data management directly affects data types, data integrity, transactions, range queries, and operations. This lesson distinguishes types of invalid dates, explains the role of SQL modes, shows how to detect legacy data, and establishes a safe workflow for eliminating zero dates.

## 1. Distinguishing Zero Dates and Invalid Dates

Not every anomalous date value is the same kind of error.

| Value | Category | Issue |
|---|---|---|
| 0000-00-00 | Zero date | Year, month, and day are all zero |
| 2024-00-15 | Date with zero component | Month equals 0 |
| 2024-02-00 | Date with zero component | Day equals 0 |
| 2024-02-31 | Calendar-invalid date | February does not have 31 days |
| 2024-13-10 | Out-of-range component | Month 13 is invalid |
| NULL | No value | Represents unknown or not applicable |

Distinguish three cases:

- **Zero date** is a special sentinel value MySQL may accept under certain configurations.
- **Invalid date** is a value violating calendar rules, such as February 31.
- **NULL** represents missing data under SQL semantics, not a special date.

Do not use a zero date to represent "unknown", "not entered", or "not applicable". For optional columns, use NULL; for required data, have the application supply a valid date or model a separate business status column.

## 2. Value Ranges of Date and Time Types

Before checking for invalid dates, know the bounds of each column type.

| Type | Typical MySQL Value Range | Characteristics |
|---|---|---|
| DATE | 1000-01-01 to 9999-12-31 | Stores calendar date only |
| DATETIME | 1000-01-01 00:00:00 to 9999-12-31 23:59:59 | Stores date and time without automatic session timezone conversion |
| TIMESTAMP | Approximately 1970-01-01 00:00:01 UTC to 2038-01-19 03:14:07 UTC | Stores an instant and converts by session timezone |
| TIME | -838:59:59 to 838:59:59 | Represents duration or time component, not a calendar date |

Types support optional fractional seconds precision, such as DATETIME(3) or TIMESTAMP(6). TIMESTAMP's range is significantly narrower than DATETIME; do not use TIMESTAMP for historical or future dates outside its supported bounds.

MySQL can also represent zero dates or zero-component dates under certain configurations. Those values do not expand the valid date range and should not be treated as normal date/time data.

## 3. SQL Modes Controlling Acceptance of Invalid Dates

SQL modes govern how MySQL validates and processes statements. The exact same INSERT statement can succeed with a warning in one session yet fail with an error in another.

Modes to understand:

| SQL Mode | Role |
|---|---|
| STRICT_TRANS_TABLES | Enables strict behavior for transactional engines and applies strict rules to other engines |
| STRICT_ALL_TABLES | Enables strict behavior for all storage engines |
| NO_ZERO_DATE | Controls acceptance of all-zero date values |
| NO_ZERO_IN_DATE | Controls dates with a nonzero year but a zero month or day |
| ALLOW_INVALID_DATES | Relaxes calendar checking for DATE and DATETIME; only checks months 1–12 and days 1–31 |
| IGNORE in DML | Can downgrade certain data errors to warnings and adjust/skip rows depending on context |

### 3.1. STRICT_TRANS_TABLES and STRICT_ALL_TABLES

Strict mode tells MySQL to reject many invalid or truncated values rather than silently coercing them to defaults.

- For transactional tables like InnoDB, a data error in a statement typically fails the statement; the transaction can roll back as appropriate.
- For non-transactional tables, you cannot assume the entire operation is undone. In some multi-row statements, rows written before hitting the error may remain.
- STRICT_TRANS_TABLES focuses on transactional engines and has specific handling rules for non-transactional engines.
- STRICT_ALL_TABLES applies strict behavior broadly across all engines, though non-transactional engines still cannot roll back already-written rows.

For transactional applications, use InnoDB and strict mode so invalid data is caught at write time.

### 3.2. NO_ZERO_DATE

NO_ZERO_DATE controls acceptance of 0000-00-00 or the corresponding zero datetime.

Outcome also depends on strict mode:

- When strict mode is enabled together with NO_ZERO_DATE, attempts to write zero dates are normally rejected with an error.
- When strict mode is disabled, the value may be accepted with a warning.
- When using INSERT IGNORE or UPDATE IGNORE, certain errors may be downgraded to warnings and handled according to IGNORE semantics.

Never conclude a zero date is valid merely because the server "allowed the insert". Inspect warnings immediately afterward and check the session's SQL mode.

### 3.3. NO_ZERO_IN_DATE

NO_ZERO_IN_DATE governs dates with a nonzero year but a zero month or day, such as 2024-00-15 and 2024-02-00.

When strict mode is combined with this mode, values with a zero month/day component are rejected. If strict mode is off, MySQL may accept them with a warning depending on configuration.

NO_ZERO_DATE and NO_ZERO_IN_DATE address two distinct malformed date patterns. Enabling one does not guarantee all partial dates or calendar-invalid dates are blocked.

### 3.4. ALLOW_INVALID_DATES

ALLOW_INVALID_DATES relaxes calendar date validation for DATE and DATETIME columns. MySQL still verifies that the month is within 1–12 and the day is within 1–31, yet does not verify the exact number of days in each month.

For example, when this mode is enabled, a value like 2024-02-31 may be accepted because month is 2 and day is 31, even though that date does not exist on the calendar. This mode does not apply to TIMESTAMP, which always requires a valid date and time.

Use ALLOW_INVALID_DATES only when an explicit, well-defined data requirement calls for it. It is not a fix for bad date input and should never be enabled just to push a migration through.

### 3.5. Notes on Versions and Default SQL Modes

Default SQL modes can vary by MySQL version, distribution, installation configuration, and cloud provider. Modes such as NO_ZERO_DATE and NO_ZERO_IN_DATE were marked deprecated in certain MySQL 8.0 releases; check exact version documentation for current status and deprecation warnings.

What matters most is enforcing strict mode and validating input data. Do not build a data quality policy solely around the two zero-date modes.

## 4. Checking Active SQL Modes

SQL mode can be configured at global and session scopes. The current session can differ from global due to connection configuration, connection pools, or SET SESSION commands.

Run:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Check individual flags:

```sql
SELECT
    FIND_IN_SET('STRICT_TRANS_TABLES', @@SESSION.sql_mode)
        AS strict_trans_tables,
    FIND_IN_SET('STRICT_ALL_TABLES', @@SESSION.sql_mode)
        AS strict_all_tables,
    FIND_IN_SET('NO_ZERO_DATE', @@SESSION.sql_mode)
        AS no_zero_date,
    FIND_IN_SET('NO_ZERO_IN_DATE', @@SESSION.sql_mode)
        AS no_zero_in_date,
    FIND_IN_SET('ALLOW_INVALID_DATES', @@SESSION.sql_mode)
        AS allow_invalid_dates;
```

A value greater than 0 means the mode is present in the session list. 0 means absent; NULL may appear if a mode name or expression is not recognized as expected.

### 4.1. Changing SQL Mode for a Test Session

You can change SQL mode in an isolated session for testing:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE';
```

The statement above **replaces the entire session SQL mode list** with the sample list. Never copy it verbatim into production without preserving all other modes required by your system.

A SESSION change affects only the current connection. SET GLOBAL sql_mode = ... changes the default for new connections and does not modify already-open sessions. Long-term settings should be managed via the server configuration file or version-supported persistence mechanisms under proper change control and review.

With connection pools, each connection can maintain independent session state. Inspect the SQL mode on the actual connections used by the application, not only on a DBA admin session.

## 5. Testing Behavior with Zero Dates and Invalid Dates

Create an InnoDB test table in a lab database:

```sql
CREATE TABLE date_mode_probe (
    id INT PRIMARY KEY,
    event_date DATE NULL,
    event_time DATETIME NULL
) ENGINE = InnoDB;
```

In a strict session with zero-date modes enabled, test inserting a valid date:

```sql
INSERT INTO date_mode_probe (id, event_date, event_time)
VALUES (1, '2024-02-29', '2024-02-29 10:30:00');
```

2024 is a leap year, so February 29 is valid.

Test a zero date:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (2, '0000-00-00');
```

Test dates with a zero month or day:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (3, '2024-00-15');

INSERT INTO date_mode_probe (id, event_date)
VALUES (4, '2024-02-00');
```

With strict mode and the corresponding zero-date modes active, the operations above are expected to be rejected. Observe the actual error codes and messages on your running version.

Test a nonexistent calendar date:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (5, '2024-02-31');
```

When ALLOW_INVALID_DATES is off, MySQL enforces calendar validity and rejects February 31. If ALLOW_INVALID_DATES is enabled, behavior differs for DATE/DATETIME, so test in an isolated lab session.

Immediately after any statement emitting warnings, run:

```sql
SHOW WARNINGS;
```

Do not use INSERT IGNORE in initial tests. It can turn errors into warnings, masking how normal strict mode behaves.

## 6. How Zero Dates Affect Queries and Date/Time Functions

A zero date does not share the semantics of a valid calendar date. Operations expecting a complete date may return NULL, produce special outputs, or emit warnings depending on the function and version.

For example, date/month additions and timezone conversions require valid inputs. Never assume every date/time function handles zero dates identically.

Zero-component dates also break or complicate:

- DATEDIFF() and interval calculations.
- DATE_ADD() or DATE_SUB().
- Extracting year, month, or day.
- Sorting and date-range filtering.
- Monthly, quarterly, and annual reports.
- Mapping to LocalDate, LocalDateTime, or JDBC driver temporal types.

In particular, a condition like event_date < CURRENT_DATE() has no clear business meaning if the table uses zero dates to mean "undetermined". Never rely on the sort order of zero dates to encode status.

## 7. Detecting Zero Dates and Zero-Component Dates

Before enabling strict mode or altering schemas, inventory legacy data. Example on an events table with an event_date column:

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(event_date IS NULL) AS null_rows,
    SUM(
        YEAR(event_date) = 0
        AND MONTH(event_date) = 0
        AND DAYOFMONTH(event_date) = 0
    ) AS zero_date_rows,
    SUM(
        YEAR(event_date) <> 0
        AND (MONTH(event_date) = 0 OR DAYOFMONTH(event_date) = 0)
    ) AS incomplete_date_rows
FROM events;
```

To list records needing remediation:

```sql
SELECT id, event_date
FROM events
WHERE event_date IS NOT NULL
  AND (
      YEAR(event_date) = 0
      OR MONTH(event_date) = 0
      OR DAYOFMONTH(event_date) = 0
  )
ORDER BY id;
```

Function expressions on columns can force an audit query to scan many rows. This is an inventory query, not a performance-tuned filter pattern for application paths. On large tables, plan execution carefully and chunk by key or partition if appropriate.

### 7.1. Detecting Calendar-Invalid Dates Stored Under ALLOW_INVALID_DATES

If a system previously enabled ALLOW_INVALID_DATES, data may contain dates with months 1–12 and days 1–31 that do not exist on the calendar, such as 2024-02-31.

After isolating zero dates and zero-component dates separately, you can check for days exceeding the month's length. Example:

```sql
SELECT id, event_date
FROM events
WHERE event_date IS NOT NULL
  AND YEAR(event_date) BETWEEN 1000 AND 9999
  AND MONTH(event_date) BETWEEN 1 AND 12
  AND DAYOFMONTH(event_date) BETWEEN 1 AND 31
  AND DAYOFMONTH(event_date) >
      DAY(
          LAST_DAY(
              CONCAT(
                  LPAD(YEAR(event_date), 4, '0'), '-',
                  LPAD(MONTH(event_date), 2, '0'), '-01'
              )
          )
      );
```

This query constructs a valid first-of-month date to obtain the last day of that month, then compares it with the stored day. It catches cases like February 31 while properly accounting for leap-year Februaries. Test on sample data with your target MySQL version before running large-scale audits.

## 8. Safely Cleaning Up Legacy Data

Do not replace every zero date with an arbitrary date like 1970-01-01 or 2000-01-01. A dummy date can be mistaken for a real business date and corrupt reports.

Before updating, classify what the data means:

- If a zero date means "unknown" or "not provided", consider converting it to NULL.
- If it encodes a business state like "not yet completed", store that state in a dedicated column.
- If the date is corrupted but recoverable from source records, quarantine the row and fix from the authoritative source.
- If exact recovery is impossible, document the remediation policy and count of affected records clearly.

### 8.1. Preparing the Column for NULL If Needed

If the policy converts zero dates to NULL, the column must allow NULL. Illustrative example:

```sql
ALTER TABLE events
    MODIFY event_date DATE NULL;
```

In a real system, MODIFY must redeclare the column's full type, default, comment, and current attributes. Never execute it without verifying the schema and application dependencies.

### 8.2. Updating Zero-Date Values

After backing up and confirming the remediation policy, update zero or zero-component values to NULL:

```sql
UPDATE events
SET event_date = NULL
WHERE event_date IS NOT NULL
  AND (
      YEAR(event_date) = 0
      OR MONTH(event_date) = 0
      OR DAYOFMONTH(event_date) = 0
  );
```

This example is only valid if all matching values genuinely mean "no date". If some rows hold recoverable information, isolate and fix them separately before running a bulk update.

For large tables, batch the migration by primary key and monitor lock times, undo/redo volume, replication lag, and log space. Never run an unbatched full-table UPDATE during peak hours without measuring impact.

### 8.3. Handling Calendar-Invalid Dates

A date like 2024-02-31 cannot be automatically turned into 2024-02-29 without an explicit business rule. Cross-check against source records or move the rows to a quarantine table for data owners to decide.

Do not rely on STR_TO_DATE() as a sole validator without checking its return value and warnings. Parsing and range-check rules can vary by version; input applications should validate dates using a calendar-aware date/time library before sending valid values to MySQL.

## 9. Designing Schemas and Applications to Prevent Bad Data From Returning

### 9.1. Use NULL or an Explicit Status Instead of Zero Dates

If a date is optional:

```sql
CREATE TABLE subscriptions (
    subscription_id BIGINT PRIMARY KEY,
    started_on DATE NOT NULL,
    cancelled_on DATE NULL
) ENGINE = InnoDB;
```

cancelled_on IS NULL represents no cancellation date yet. If the business needs to distinguish "not requested", "in progress", and "cancelled", use a dedicated status column rather than encoding states with dummy dates.

### 9.2. Never Set a Zero Date as DEFAULT

Avoid declarations like:

```sql
-- Do not use as a default
CREATE TABLE legacy_events (
    event_id BIGINT PRIMARY KEY,
    event_date DATE NOT NULL DEFAULT '0000-00-00'
);
```

Instead, optional columns can use DEFAULT NULL; mandatory columns should require the application to supply a valid date or use a valid business-appropriate default.

### 9.3. Validation in Both Application and Database

Applications should parse inputs into real temporal types before binding parameters. In Java:

| MySQL | Typical Java Type |
|---|---|
| DATE | LocalDate |
| DATETIME | LocalDateTime |
| TIMESTAMP | Instant or a timezone-aware instant type matching application design |
| TIME | LocalTime or a duration representation if storing elapsed time |

DATETIME does not auto-convert by session timezone; TIMESTAMP converts between session timezone and UTC during writes/reads. Choose the Java type by data semantics, not just the SQL type name.

With JDBC, bind typed objects rather than passing arbitrary strings:

```java
LocalDate eventDate = LocalDate.parse(inputDate);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO events (id, event_date) VALUES (?, ?)")) {
    ps.setLong(1, eventId);
    ps.setObject(2, eventDate);
    ps.executeUpdate();
}
```

If the input string is not a valid calendar date, LocalDate.parse() fails before any data reaches the database. With Connector/J, java.time mappings are supported in modern versions; check your driver's compatibility and avoid relying on driver options that silently convert zero dates into dummy values.

### 9.4. Ensuring Consistent Session SQL Modes

Applications, migration tools, batch imports, and DBA consoles may use different sessions. Standardize SQL mode via server configuration and connection initialization settings, and verify actual session state.

With connection pools, ensure a session does not retain a permissive SQL mode left over from a prior task. On checkout, applications should never assume every connection has identical state unless the pool resets or enforces session state.

## 10. Workflow for Rolling Out Strict Date Validation

When eliminating zero dates and invalid dates from a live system, proceed in phases:

1. **Audit SQL modes.** Capture @@GLOBAL.sql_mode and @@SESSION.sql_mode across servers, migration tools, and application connections.
2. **Audit schemas.** Locate DATE, DATETIME, TIMESTAMP columns, zero-date defaults, and NOT NULL columns that may rely on dummy dates.
3. **Profile data.** Count zero dates, zero-component dates, and calendar-invalid dates; export key lists for data owners to verify.
4. **Define conversion policies.** Decide which cases become NULL, explicit status values, recovered dates, or quarantined rows.
5. **Prepare schemas.** Adjust nullability/defaults and update applications via reviewed migrations.
6. **Clean up in batches.** Perform controlled data updates, log before/after row counts, and preserve an audit trail.
7. **Enable strict behavior.** Test in staging, then roll out consistent SQL modes across connections.
8. **Test inputs.** Verify valid dates, leap dates, zero dates, zero month/day, calendar-invalid dates, NULLs, and out-of-range values.
9. **Monitor warnings/errors.** Watch application logs, SQL errors, batch imports, and ETL jobs.
10. **Verify post-deployment.** Re-run inventory queries, confirm zero prohibited values remain, and test backup/restore if large data changes occurred.

Never enable strict mode in production before profiling existing data and testing import pipelines. Legacy systems may rely on permissive behavior; enabling strict mode abruptly can cause batch jobs or requests to fail.

## 11. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| 0000-00-00 is equivalent to NULL | A zero date is a special date sentinel; NULL means no value |
| Enabling NO_ZERO_DATE is enough | Must consider strict mode, NO_ZERO_IN_DATE, ALLOW_INVALID_DATES, and validation |
| ALLOW_INVALID_DATES accepts any string | It still enforces months 1–12 and days 1–31; it only skips per-month day-count checks |
| 2024-02-31 is always rejected | ALLOW_INVALID_DATES can allow DATE/DATETIME to accept it |
| INSERT IGNORE is a data-cleanup tool | IGNORE can turn errors into warnings and hide malformed input data |
| Every engine rolls back when strict mode errors | Non-transactional engines cannot roll back already-written rows |
| Global SQL mode changes open sessions | Existing sessions can keep their own settings; global primarily affects new connections |
| All zero dates can be replaced with 1970 | Dummy dates distort semantics; use NULL, a separate status, or source reconciliation |

## 12. Key Takeaways

- Distinguish zero dates, zero-component dates, calendar-invalid dates, and NULL.
- NO_ZERO_DATE governs all-zero dates; NO_ZERO_IN_DATE governs zero months/days with a nonzero year.
- Strict mode determines whether many invalid-data cases become errors rather than warnings.
- ALLOW_INVALID_DATES relaxes calendar checks for DATE/DATETIME but does not apply to TIMESTAMP.
- SQL mode exists at global and session scopes; always verify on the actual application connection.
- INSERT IGNORE can mask errors as warnings; inspect SHOW WARNINGS.
- Never use zero dates as defaults or to encode business status.
- Before cleaning data, inventory rows, classify business semantics, take backups, and test migrations in staging.
- Use LocalDate, LocalDateTime, and appropriate instant types in Java; validate inputs before binding in JDBC.

By controlling SQL modes, schemas, and application validation together, MySQL can reject invalid date/time data right at the write boundary, keeping temporal queries, reports, and migrations consistent.
