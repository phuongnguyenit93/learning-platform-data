# DATE, TIME, DATETIME, TIMESTAMP, and YEAR

Temporal data appears in almost every application: birth dates, order dates, payment timestamps, opening hours, processing durations, and fiscal years. MySQL provides `DATE`, `TIME`, `DATETIME`, `TIMESTAMP`, and `YEAR` to store these distinct meanings. Choosing the wrong type can shift instants when time zones change, lose precision, restrict date ranges, or make range queries harder to optimize.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims for mastery of MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while also practicing execution plan reading, query optimization, privilege management, backups, and handling relational database operational issues. Within the **Data Types** chapter, this lesson helps distinguish the semantics of each temporal type and design time storage suited to business needs.

## 1. Before Choosing a Temporal Type, Identify Data Semantics

A value such as `2026-05-12 09:30:00` can represent several different things:

- A person's birthday: only a calendar date is needed, with no time or time zone.
- A meeting at 09:30 in Ho Chi Minh City: the local date and wall-clock time carry business meaning.
- The moment a payment was actually recorded: a unique instant on the timeline that must remain consistent across servers and users in multiple time zones.
- A job's execution duration: elapsed time, which can exceed 24 hours or even be negative in some calculations.
- A fiscal year: only the year component is needed.

Do not choose a type solely because input values look similar. Ask whether the data represents a **calendar date**, **time of day**, **duration**, **absolute instant**, or **year**.

| Business Meaning | Typically Suitable Type | Example |
|---|---|---|
| Birth date, invoice issue date | `DATE` | `2026-05-12` |
| Execution duration or time difference | `TIME` within type bounds | `27:15:00` |
| Local time with date, without automatic time zone conversion | `DATETIME` | `2026-05-12 09:30:00` |
| Event instant converted per session time zone | `TIMESTAMP` | `2026-05-12 02:30:00` UTC |
| Standalone year | `YEAR` | `2026` |

`DATETIME` can also store an absolute instant if the application standardizes on storing all values in UTC. In that case, the application itself is responsible for converting before writes and after reads; MySQL does not automatically shift `DATETIME` according to the session time zone.

## 2. Overview of the Five Data Types

| Type | Stored Content | Primary Range | Fractional Seconds Precision |
|---|---|---|---|
| `DATE` | Calendar date: year, month, day | `1000-01-01` to `9999-12-31` | None |
| `TIME` | Time or duration, can be negative | `-838:59:59` to `838:59:59` | Up to 6 microsecond digits |
| `DATETIME` | Calendar date and time | `1000-01-01 00:00:00` to `9999-12-31 23:59:59` | Up to 6 microsecond digits |
| `TIMESTAMP` | Instant stored in UTC and displayed per session time zone | Roughly 1970 through January 2038 | Up to 6 microsecond digits |
| `YEAR` | Year component | `1901` to `2155`, plus `0000` | None |

`TIME`, `DATETIME`, and `TIMESTAMP` support fractional seconds precision (FSP) from 0 to 6. If FSP is omitted, the default precision is 0, storing no fractional seconds. For `TIMESTAMP`, the exact bounds are defined in UTC; displayed values may show a different date or time depending on the session time zone.

Range limits are an important factor. `TIMESTAMP` is convenient for event instants, but unsuitable for calendar dates far in the past or distant future. `DATETIME` has a much wider range and performs no implicit time zone conversion.

## 3. The `DATE` Type: Storing Calendar Dates Only

`DATE` stores year, month, and day without hours, minutes, seconds, or time zones. It is the right choice for birth dates, contract signing dates, due dates, holidays, and invoice dates when the business cares only about calendar dates.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    hire_date   DATE NOT NULL,
    PRIMARY KEY (employee_id)
);

INSERT INTO employees (full_name, birth_date, hire_date)
VALUES ('Nguyễn An', '1998-04-17', '2026-05-12');

SELECT employee_id, full_name, birth_date, hire_date
FROM employees;
```

### 3.1. Literals and Formatting

Pass dates in year-month-day format:

```sql
INSERT INTO employees (full_name, birth_date, hire_date)
VALUES ('Trần Bình', '1995-11-03', '2026-05-12');
```

Avoid storing dates as `VARCHAR` such as `'12/05/2026'`. Strings without an enforced date format easily cause day/month vs. month/day ambiguity, complicate validation, hinder calendar comparisons, and prevent using temporal functions.

### 3.2. When Should `DATE` Not Be Used?

If the business needs to distinguish two events occurring on the same date at different times, `DATE` loses information. For example, an order creation timestamp usually needs hours and minutes to sort or verify payment deadlines. In such cases, choose `DATETIME` or `TIMESTAMP` per your time zone convention.

## 4. The `TIME` Type: Time of Day or Duration

`TIME` stores hours, minutes, seconds, and optional microseconds. Importantly, `TIME` is not restricted to time of day; MySQL also supports negative values and values exceeding 24 hours. Thus, it often fits **durations** or elapsed intervals.

Example:

```sql
CREATE TABLE job_runs (
    run_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at   DATETIME(6) NOT NULL,
    elapsed_time TIME(6) NOT NULL,
    PRIMARY KEY (run_id)
);

INSERT INTO job_runs (started_at, elapsed_time)
VALUES ('2026-05-12 09:00:00.000000', '27:15:30.250000');
```

`27:15:30` means 27 hours, 15 minutes, 30 seconds; it is not interpreted as 03:15:30 the next day. Negative values like `'-02:30:00'` can also arise in time difference calculations.

The range of `TIME` is roughly `-838:59:59` to `838:59:59`. It is not meant for unbounded durations. If you need to store durations spanning months, years, or large millisecond counts, consider an integer like `BIGINT` in an agreed unit, or a more suitable data model.

### 4.1. Time of Day vs. Duration Are Different

`TIME` can store opening hours such as `09:00:00`, but it contains no date and no time zone. If storing a weekly schedule, you may need to pair day-of-week with time. If storing a specific appointment, you need both date and time, typically using `DATETIME` alongside local time zone info when needed.

Do not use `TIME` to store start/end instants of an event if you need to know which day the event occurred on. Two `09:00:00` values on different days cannot be distinguished with `TIME` alone.

### 4.2. Converting Between TIME and Seconds

MySQL provides `TIME_TO_SEC()` and `SEC_TO_TIME()`:

```sql
SELECT TIME_TO_SEC('02:30:00') AS duration_seconds;
-- 9000

SELECT SEC_TO_TIME(9000) AS duration_value;
-- 02:30:00
```

When using `SEC_TO_TIME()`, keep in mind that the result remains bounded by the `TIME` type's range.

## 5. The `DATETIME` Type: Calendar Date and Time Without Automatic Time Zone Conversion

`DATETIME` stores a calendar date and time. On writes and reads, MySQL does not automatically convert this value based on the session `time_zone`.

Example:

```sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id    BIGINT UNSIGNED NOT NULL,
    scheduled_at   DATETIME(6) NOT NULL,
    PRIMARY KEY (appointment_id)
);

INSERT INTO appointments (customer_id, scheduled_at)
VALUES (101, '2026-05-12 09:30:00.123456');
```

The value above can represent an appointment at 09:30:00.123456 in the local time chosen by the business. If users span multiple regions, storing `DATETIME` alone may not suffice to determine the exact corresponding instant. In that case, also store an IANA time zone identifier such as `Asia/Ho_Chi_Minh`, or standardize explicitly on `scheduled_at` always being UTC.

### 5.1. Range and Fractional Seconds

`DATETIME` ranges from `1000-01-01 00:00:00` to `9999-12-31 23:59:59.999999` with FSP 6. You can declare fractional seconds precision:

```sql
CREATE TABLE audit_events (
    event_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurred_at DATETIME(6) NOT NULL,
    description VARCHAR(255) NOT NULL,
    PRIMARY KEY (event_id)
);
```

Literal example:

```sql
INSERT INTO audit_events (occurred_at, description)
VALUES ('2026-05-12 09:30:00.123456', 'Login succeeded');
```

If millisecond precision is sufficient, `DATETIME(3)` may be enough. Choose FSP based on the precision the application genuinely needs; storing six fractional digits increases storage compared to zero fractional seconds.

### 5.2. Using DATETIME to Store UTC Instants

A system may choose to store absolute instants in `DATETIME(6)` with the convention that every value in the column is UTC. This offers a wider year range than `TIMESTAMP`, useful for data prior to 1970 or after 2038.

However, MySQL does not know that the `DATETIME` column represents UTC. If a session is set to `+07:00`, `NOW()` returns session time; inserting `NOW()` into a `DATETIME` column stores that local value verbatim without converting to UTC. Applications must use `UTC_TIMESTAMP(6)` or convert consistently in the application layer.

```sql
INSERT INTO audit_events (occurred_at, description)
VALUES (UTC_TIMESTAMP(6), 'Event recorded in UTC');
```

Document the convention clearly in column names or schema docs—for example, `created_at_utc`—if it helps maintainers avoid confusion.

## 6. The `TIMESTAMP` Type: Storing Instants Converted Per Session

`TIMESTAMP` is designed for a point on the timeline. When writing, MySQL converts the value from the session time zone to UTC for storage; when reading, MySQL converts from UTC back to the current session time zone. Consequently, two sessions with different `time_zone` settings see different displayed wall-clock times for the same `TIMESTAMP` row, while the underlying instant is identical.

Example:

```sql
CREATE TABLE payment_events (
    payment_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paid_at           TIMESTAMP(6) NOT NULL,
    amount            DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (payment_event_id)
);

SET SESSION time_zone = '+00:00';

INSERT INTO payment_events (paid_at, amount)
VALUES ('2026-05-12 02:30:00.123456', 125000.00);

SELECT paid_at FROM payment_events;

SET SESSION time_zone = '+07:00';

SELECT paid_at FROM payment_events;
```

The UTC session displays `02:30:00.123456`; the `+07:00` session displays `09:30:00.123456`. Both values represent the exact same instant.

### 6.1. TIMESTAMP Range

In current MySQL, the `TIMESTAMP` range is approximately `1970-01-01 00:00:01` UTC to `2038-01-19 03:14:07` UTC. This is a critical constraint when storing historical records or events scheduled in the distant future.

If the business needs to store birth dates before 1970, centuries of history, or bookings past 2040, `TIMESTAMP` is likely unsuitable. `DATE` or `DATETIME` is generally more appropriate depending on the semantics.

### 6.2. Defaults and Auto-Update

`TIMESTAMP` is commonly used for creation and update audit columns. MySQL supports `DEFAULT CURRENT_TIMESTAMP` and `ON UPDATE CURRENT_TIMESTAMP`, with matching FSP:

```sql
CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id)
);
```

- When inserting a row without specifying `created_at`, MySQL assigns the current timestamp.
- When updating a row and modifying another column's value, `updated_at` automatically updates per definition.
- Explicit values can still be provided when business logic requires it, subject to type and privileges.

`CURRENT_TIMESTAMP` evaluates to the current time in the session time zone. Because `TIMESTAMP` converts per session, configure application sessions consistently—usually to UTC—to prevent read/write confusion.

### 6.3. Where Do TIMESTAMP and DATETIME Differ?

| Criterion | `TIMESTAMP` | `DATETIME` |
|---|---|---|
| Session time zone conversion | Yes; converts to UTC on write and back to session zone on read | No |
| Year range | Roughly 1970–2038 | 1000–9999 |
| Stores calendar date and time | Yes | Yes |
| Fits absolute instants | Yes, if time zones are configured properly | Yes, if the application enforces and manages UTC |
| Fits unconverted local wall-clock time | Not a natural fit | Yes |
| Auto-assigns current timestamp | Supports `DEFAULT CURRENT_TIMESTAMP` | Supports `DEFAULT CURRENT_TIMESTAMP` in modern MySQL |

There is no rule to "always use TIMESTAMP" or "always use DATETIME". Choose based on time range, time zone semantics, precision, and how the application handles values.

## 7. The `YEAR` Type: Storing Years Only

`YEAR` stores a year component without month, day, or time. The valid range is `1901` to `2155`, plus the value `0000`.

Example:

```sql
CREATE TABLE fiscal_reports (
    report_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    fiscal_year YEAR NOT NULL,
    report_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (report_id),
    UNIQUE KEY uq_fiscal_report_year_name (fiscal_year, report_name)
);

INSERT INTO fiscal_reports (fiscal_year, report_name)
VALUES (2026, 'Revenue report');
```

Enter years as four digits or four-digit integers. Avoid two-digit years because century-interpretation rules are confusing and unsuitable for modern data. `YEAR(2)` has been removed from MySQL; do not rely on legacy display widths.

If the business needs years outside `YEAR`'s range—such as historical years before 1901 or projections past 2155—use an integer type such as `SMALLINT` or `INT` with appropriate constraints/validation. Never use `YEAR` merely because a column is named `year`.

The value `0000` has special meaning in MySQL and is rarely a valid business calendar year. Do not use it as a sentinel for "unknown" when `NULL` or a separate status column can express that state cleanly.

## 8. Fractional Seconds Precision

`TIME`, `DATETIME`, and `TIMESTAMP` support FSP from 0 to 6:

| Declaration | Precision | Example |
|---|---|---|
| `TIME` | Default 0 | `12:30:45` |
| `TIME(3)` | Milliseconds | `12:30:45.123` |
| `DATETIME(6)` | Microseconds | `2026-05-12 12:30:45.123456` |
| `TIMESTAMP(3)` | Milliseconds | `2026-05-12 12:30:45.123` |

Example query:

```sql
SELECT
    CURRENT_TIMESTAMP(6) AS now_with_microseconds,
    UTC_TIMESTAMP(6) AS utc_with_microseconds,
    NOW(3) AS now_with_milliseconds;
```

When writing a value with more fractional digits than the column's FSP, MySQL may round or truncate excess digits depending on rules and SQL mode. The `TIME_TRUNCATE_FRACTIONAL` SQL mode instructs truncation instead of rounding. If applications need exact timestamp matching across multiple systems, standardize FSP and fractional handling in both drivers and schemas.

Do not pick FSP 6 out of habit if the data source only has second-level resolution. Higher precision does not magically make system clocks more accurate; it only stores the fractional digits provided by the source.

## 9. Time Zones and Temporal Functions

### 9.1. NOW(), CURRENT_TIMESTAMP, and UTC_TIMESTAMP

Important functions:

| Function | Result |
|---|---|
| `NOW()` / `CURRENT_TIMESTAMP` | Current instant in the session time zone. |
| `UTC_TIMESTAMP()` | Current instant in UTC. |
| `CURDATE()` / `CURRENT_DATE` | Current date in the session time zone. |
| `CURTIME()` / `CURRENT_TIME` | Current time in the session time zone. |
| `DATE(expr)` | Extracts the date portion from a date/time expression. |
| `TIME(expr)` | Extracts the time portion from a date/time expression. |

Quick check:

```sql
SELECT
    @@session.time_zone AS session_zone,
    NOW(6) AS session_now,
    UTC_TIMESTAMP(6) AS utc_now,
    CURDATE() AS session_date,
    CURTIME(6) AS session_time;
```

If `@@session.time_zone` is `'+07:00'`, `NOW()` shows UTC plus seven hours. `UTC_TIMESTAMP()` still returns UTC.

### 9.2. Time Zone Conversion

`CONVERT_TZ()` converts a date/time value from one time zone to another:

```sql
SELECT CONVERT_TZ(
    '2026-05-12 02:30:00',
    '+00:00',
    '+07:00'
) AS vietnam_local_time;
```

The result is `2026-05-12 09:30:00`. Named time zones like `'UTC'` and `'Asia/Ho_Chi_Minh'` can be used, provided MySQL's time zone tables are populated and kept up to date. If those tables are empty, `CONVERT_TZ()` with named regions can return `NULL`.

Fixed offsets like `'+07:00'` are simple but do not capture historical rules for a region. IANA time zone names are better when historical or daylight-saving transitions matter. Vietnam currently observes UTC+7, but for multi-country datasets, never assume every region has a permanent fixed offset.

### 9.3. Addition, Subtraction, and Duration Calculations

MySQL includes temporal arithmetic functions:

```sql
SELECT DATE_ADD('2026-05-12', INTERVAL 7 DAY) AS next_week;

SELECT DATE_SUB('2026-05-12 09:30:00', INTERVAL 2 HOUR) AS two_hours_before;

SELECT DATEDIFF('2026-05-20', '2026-05-12') AS day_difference;

SELECT TIMESTAMPDIFF(
    MINUTE,
    '2026-05-12 09:00:00',
    '2026-05-12 10:45:00'
) AS elapsed_minutes;
```

- `DATE_ADD()` and `DATE_SUB()` add or subtract an interval.
- `DATEDIFF()` evaluates the date parts and returns the difference in days; time parts are ignored.
- `TIMESTAMPDIFF(unit, start, end)` returns the difference in the specified unit.
- `EXTRACT()` extracts a component such as year, month, day, or hour.

Example extracting year and month:

```sql
SELECT
    EXTRACT(YEAR FROM paid_at) AS paid_year,
    EXTRACT(MONTH FROM paid_at) AS paid_month
FROM payment_events;
```

### 9.4. Formatting for Display

`DATE_FORMAT()` and `TIME_FORMAT()` convert temporal values into strings for display:

```sql
SELECT DATE_FORMAT(
    '2026-05-12 09:30:45.123456',
    '%d/%m/%Y %H:%i:%s.%f'
) AS display_value;
```

Common format specifiers:

| Specifier | Meaning |
|---|---|
| `%Y` | Four-digit year |
| `%m` | Two-digit month |
| `%d` | Day of month |
| `%H` | Hour 00–23 |
| `%i` | Minutes |
| `%s` | Seconds |
| `%f` | Microseconds |

Format values into strings only in the presentation layer or when exporting reports. Never store the output of `DATE_FORMAT()` back into a string column when the data remains temporal in nature.

## 10. Auto-Assigning Creation and Update Timestamps

For record creation/modification timestamps, you can use `DEFAULT CURRENT_TIMESTAMP` and `ON UPDATE CURRENT_TIMESTAMP`:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title      VARCHAR(200) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_id)
);
```

Modern MySQL supports auto-initialization and auto-update attributes for both `TIMESTAMP` and `DATETIME`. The FSP of `CURRENT_TIMESTAMP(fsp)` should match the column's FSP.

Notes:

- `DEFAULT CURRENT_TIMESTAMP` applies when an `INSERT` omits a value for the column.
- `ON UPDATE CURRENT_TIMESTAMP` updates the column when another column in the row changes under MySQL's rules.
- If the application sets `updated_at` manually, decide explicitly whether to keep `ON UPDATE` so two layers are not competing to manage the timestamp.
- `CURRENT_TIMESTAMP` follows the session time zone. With `DATETIME`, the returned value is stored as-is; with `TIMESTAMP`, it is converted to UTC on storage.

If you need a complete history of every change, a single `updated_at` column is not enough. Use a dedicated audit or event table to record each change.

## 11. Temporal Queries and Index Usage

### 11.1. Prefer Half-Open Interval Queries

Suppose you need all orders placed on May 12, 2026. When `created_at` is `DATETIME` or `TIMESTAMP`, a half-open interval predicate is clear and index-friendly:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
```

The range `>= start of day` and `< start of next day` covers every instant within that day, including trailing microseconds. It also avoids manually constructing `'23:59:59.999999'`.

### 11.2. Avoid Wrapping Indexed Columns in Functions Unnecessarily

If there is an index on `created_at`, the predicate below can prevent MySQL from performing a normal index range scan because it applies a function to every column value:

```sql
-- Generally index-unfriendly for an index on created_at:
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-05-12';
```

Rewrite as a range condition:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
```

Then run `EXPLAIN` to confirm the actual execution plan. If queries frequently filter by a date derived from a timestamp, consider a generated column or functional index appropriate for your MySQL version and query workload.

### 11.3. Be Careful with Day Boundaries and Time Zones

If `created_at` is `TIMESTAMP`, literals in predicates are interpreted in the session time zone and converted per the type's mechanism. If you need "May 12 in Vietnam", determine the start-of-day and next-day-start instants in `Asia/Ho_Chi_Minh`, then convert them to UTC or run in a session configured to the proper time zone. Do not use UTC midnight boundaries when the business is asking for a local UTC+7 calendar day.

Example converting two Vietnam local boundaries to UTC:

```sql
SELECT
    CONVERT_TZ('2026-05-12 00:00:00', 'Asia/Ho_Chi_Minh', '+00:00') AS start_utc,
    CONVERT_TZ('2026-05-13 00:00:00', 'Asia/Ho_Chi_Minh', '+00:00') AS end_utc;
```

The result gives two UTC boundaries 24 hours apart for a region without DST transitions in that window. For regions observing DST, two consecutive local midnights may not be exactly 24 hours apart; use IANA zone names and updated time zone data.

## 12. Invalid Dates/Times and SQL Mode

MySQL validates date/time values according to the data type and SQL mode. Values like month 13, nonexistent days, or zero dates may be rejected, raise warnings, or be handled per mode and version rules.

Do not rely on values like `'0000-00-00'` or `'2026-00-15'` to mean "unknown". Use `NULL` when data is truly absent, or use a separate status column if the business must distinguish multiple states.

Check SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

Strict mode rejects many invalid values instead of silently adjusting them. Zero-date modes like `NO_ZERO_DATE` and `NO_ZERO_IN_DATE` have had changes and deprecations across MySQL versions; do not rely solely on mode names to guarantee valid data. Verify behavior on your target version and combine strict mode with application-level input validation.

When migrating legacy data, profile and clean invalid dates/times before enabling strict settings. Never convert all invalid values into a single dummy default date, as doing so corrupts business history.

## 13. Which Type Fits Which Scenario?

| Scenario | Suggestion | Reason |
|---|---|---|
| Customer birth date | `DATE` | No time or time zone meaning. |
| Contract expiration date | `DATE` | Business typically defines it by calendar date. |
| Daily store opening hours | `TIME` | Recurring time of day, not tied to a specific date. |
| 27-hour job runtime | `TIME` if within range; otherwise an integer with explicit units | `TIME` exceeds 24 hours but caps around 838 hours. |
| 09:30 appointment at a venue | `DATETIME` with regional time zone | Preserves local wall-clock time. |
| Payment timestamp or event log | `TIMESTAMP` or `DATETIME(6)` standardized on UTC | Needs a consistent absolute instant. |
| Events potentially outside 1970–2038 | `DATETIME(6)` standardized on UTC or suitable model | Avoids `TIMESTAMP` range limits. |
| Fiscal year | `YEAR` if within range; otherwise integer | Only needs to store the year. |

Before freezing the schema, document conventions clearly: which columns are UTC, which are local time, how session time zones are configured, and which layer performs conversions.

## 14. Combined Table Design Example

An e-commerce system may combine several temporal types according to their distinct semantics:

```sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    PRIMARY KEY (customer_id)
);

CREATE TABLE store_hours (
    store_id   BIGINT UNSIGNED NOT NULL,
    day_of_week TINYINT UNSIGNED NOT NULL,
    opens_at   TIME NOT NULL,
    closes_at  TIME NOT NULL,
    PRIMARY KEY (store_id, day_of_week)
);

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
);

CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id    BIGINT UNSIGNED NOT NULL,
    local_start    DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    PRIMARY KEY (appointment_id)
);

CREATE TABLE fiscal_year_targets (
    fiscal_year YEAR NOT NULL,
    target_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (fiscal_year)
);
```

In this schema:

- `birth_date` stores only the birth date.
- `opens_at` and `closes_at` are wall-clock times within a day.
- `created_at` and `updated_at` are event instants managed by MySQL per session time zone.
- `local_start` preserves local date and time; `time_zone_name` identifies the region that local time belongs to.
- `fiscal_year` stores only the year.

This illustrates temporal types rather than a complete production schema. A production system would also add foreign keys, constraints on `day_of_week`, open/close time validation, overnight handling rules, and appointment update policies.

## 15. Practice Exercises

### Exercise 1: Classifying Data Semantics

An HR application needs to store birth dates, employment start dates, employee clock-in instants, and overtime durations.

**Requirement:** choose a data type for each attribute and explain why a single type cannot serve all of them.

### Exercise 2: Comparing DATETIME and TIMESTAMP

Create a temporary table with `DATETIME` and `TIMESTAMP` columns. Insert the same literal while the session is in UTC, switch the session to `+07:00`, and read back the row.

**Requirement:** record the values of both columns and explain which column changes its display output.

### Exercise 3: Fractional Seconds

Create three columns: `DATETIME`, `DATETIME(3)`, and `DATETIME(6)`. Insert the same literal containing six fractional digits.

**Requirement:** compare the retrieved values and explain how FSP affects storage precision.

### Exercise 4: Finding Orders Within One Day

Create an index on `orders.created_at`. Write a query retrieving all orders on May 12, 2026 using a half-open interval, then compare with a query using `DATE(created_at)`.

**Requirement:** run `EXPLAIN` and explain any difference in access plans.

### Exercise 5: Converting Local Time to UTC

Use `CONVERT_TZ()` to convert `2026-05-12 09:30:00` from `Asia/Ho_Chi_Minh` to UTC.

**Requirement:** verify whether MySQL's time zone tables are populated and explain why the function returns `NULL` if they are not.

### Exercise 6: Designing Appointment Times

A scheduling app serves users in multiple countries. A user picks 09:00 on May 12 in their local time zone.

**Requirement:** propose the columns to store in order to preserve local wall-clock time, regional time zone, and the absolute instant; explain why storing only `DATETIME` is insufficient without a time zone convention.

## 16. Pre-Creation Checklist for Date/Time Columns

- [ ] Identified whether data is a calendar date, time of day, duration, or absolute instant.
- [ ] Selected `DATE`, `TIME`, `DATETIME`, `TIMESTAMP`, or `YEAR` matching the semantics.
- [ ] Checked range limits of the type, especially `TIMESTAMP`'s 2038 limit.
- [ ] Selected FSP 0–6 matching source precision.
- [ ] Specified UTC vs. local time convention for every column with a time component.
- [ ] When storing local time, decided whether an IANA time zone name column is needed.
- [ ] Avoided zero dates or formatted strings to represent unknown values.
- [ ] Used `DEFAULT CURRENT_TIMESTAMP` and `ON UPDATE` intentionally.
- [ ] Queried time ranges using half-open intervals where appropriate.
- [ ] Verified indexes and execution plans using `EXPLAIN`.
- [ ] Standardized conversions across MySQL, JDBC, and the application.

## 17. Takeaways

`DATE` is for calendar dates; `TIME` represents times of day or durations within a bounded range; `DATETIME` preserves calendar date and time without automatic time zone conversion; `TIMESTAMP` represents instants converted through UTC per session; `YEAR` stores only years. `TIME`, `DATETIME`, and `TIMESTAMP` support up to six digits of fractional seconds.

Good temporal design starts with business semantics and time zone conventions. Standardize on UTC for absolute instants, store time zone names when local wall-clock times must be preserved, pick an appropriate FSP, and query clear intervals. These decisions keep data accurate, auditable, and index-optimizable.
