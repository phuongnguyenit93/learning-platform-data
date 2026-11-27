# Fractional Seconds Precision and Rounding Rules on Storage

Timestamps in applications often require sub-second precision: order creation time, event logs, payment receipt time, or the ordering of near-concurrent requests. MySQL supports fractional seconds for `TIME`, `DATETIME`, and `TIMESTAMP`, with precision from 0 to 6 decimal digits. However, if a column does not declare a precision, MySQL defaults to 0 digits, and incoming fractional seconds may be rounded when stored.

The key is distinguishing **input data precision**, **declared column precision**, **time-generation function precision**, and **rounding or truncation rules**. If these layers are misaligned, an application may observe timestamps off by milliseconds, two events collapsed onto the same timestamp, or a value pushed into the next second or day.

## Learning Objectives

After this lesson, you can:

- Explain FSP (fractional seconds precision) and its valid range from 0 to 6.
- Choose `TIME(fsp)`, `DATETIME(fsp)`, or `TIMESTAMP(fsp)` suited to the required storage precision.
- Understand the default behavior when an input value has more fractional digits than the column.
- Distinguish rounding from truncation using the `TIME_TRUNCATE_FRACTIONAL` SQL mode.
- Use `NOW(fsp)`, `CURRENT_TIMESTAMP(fsp)`, and temporal functions that accept an FSP argument.
- Verify carries when rounding crosses second, minute, day, or year boundaries.
- Design defaults, `ON UPDATE`, queries, and migrations consistent with temporal precision.

## 1. What Is FSP?

FSP stands for *fractional seconds precision*, meaning the number of digits stored after the decimal point in the seconds component. MySQL allows an FSP from `0` to `6` for `TIME`, `DATETIME`, and `TIMESTAMP`.

| Declaration | Stored Fractional Seconds | Nominal Resolution |
|---|---|---|
| `DATETIME` or `DATETIME(0)` | No fractional digits | 1 second |
| `DATETIME(1)` | 1 digit, e.g. `.7` | 0.1 seconds |
| `DATETIME(2)` | 2 digits, e.g. `.78` | 0.01 seconds |
| `DATETIME(3)` | 3 digits, e.g. `.789` | 1 millisecond |
| `DATETIME(4)` | 4 digits, e.g. `.7896` | 0.1 milliseconds |
| `DATETIME(5)` | 5 digits, e.g. `.78960` | 10 microseconds |
| `DATETIME(6)` | 6 digits, e.g. `.789600` | 1 microsecond |

FSP is the count of fractional-second digits, not the byte size, and not a guarantee that the system clock always measures with that true accuracy. For instance, `DATETIME(6)` can store six microsecond digits, while the actual accuracy of the timestamp provided by the application or OS still depends on the clock source.

If FSP is omitted, MySQL uses `0`. Therefore:

```sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
);
```

`created_at` in this example has 1-second precision. To store milliseconds, you must declare `DATETIME(3)`; to store microseconds, use `DATETIME(6)`.

## 2. Temporal Types Supporting Fractional Seconds

The three temporal types that support FSP are `TIME`, `DATETIME`, and `TIMESTAMP`:

```sql
CREATE TABLE temporal_precision_types (
    id INT NOT NULL PRIMARY KEY,
    duration TIME(3),
    local_event_time DATETIME(6),
    recorded_instant TIMESTAMP(6)
);
```

- `TIME(fsp)` represents a time of day or an elapsed duration within the range of the `TIME` type; fractional seconds can have precision down to microseconds.
- `DATETIME(fsp)` stores date and time components as supplied, without automatic conversion for the session time zone.
- `TIMESTAMP(fsp)` represents an instant converted between the session time zone and UTC on write/read; FSP determines how many fractional-second digits are retained.

FSP does not alter a data type's time zone rules. `DATETIME(6)` still does not automatically convert time zones; `TIMESTAMP(6)` still converts according to the session time zone. When designing schemas, choose the data type for its temporal semantics first, then choose the FSP for the required resolution.

`DATE` and `YEAR` have no fractional seconds. Do not declare FSP on these types.

## 3. Creating a Table to Compare Precision

The following example stores the same value into three `DATETIME` columns with different precisions:

```sql
CREATE TABLE fractional_precision_demo (
    id INT NOT NULL PRIMARY KEY,
    captured_at_0 DATETIME(0) NOT NULL,
    captured_at_3 DATETIME(3) NOT NULL,
    captured_at_6 DATETIME(6) NOT NULL
) ENGINE = InnoDB;

INSERT INTO fractional_precision_demo
    (id, captured_at_0, captured_at_3, captured_at_6)
VALUES
    (1,
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600');

SELECT
    id,
    captured_at_0,
    captured_at_3,
    captured_at_6
FROM fractional_precision_demo;
```

With MySQL's default behavior, fractional seconds are rounded when the input value has more digits than the column's FSP. Expected result:

| Column | Stored Value |
|---|---|
| `captured_at_0` | `2025-06-10 14:25:37` |
| `captured_at_3` | `2025-06-10 14:25:36.790` |
| `captured_at_6` | `2025-06-10 14:25:36.789600` |

The FSP 0 column rounds `.789600` up to the next second. The FSP 3 column rounds to the nearest millisecond, turning `.789600` into `.790`. The FSP 6 column preserves all six digits because the input matches the column's supported precision.

This is a critical distinction: if an application sends microseconds to a `DATETIME` column without FSP, the fractional part is not preserved intact. The fact that an insert succeeded does not mean the timestamp was stored with the exact input precision.

## 4. Default Rule: Rounding Fractional Seconds

When MySQL stores a value with more fractional-second digits than the column's FSP, the default behavior is **rounding**. Digits beyond the target precision determine whether the last retained digit is incremented.

Examples with a `DATETIME(3)` column:

| Input | Result Rounded to FSP 3 |
|---|---|
| `.1234` | `.123` |
| `.1236` | `.124` |
| `.7894` | `.789` |
| `.7896` | `.790` |

Examples with a `DATETIME(0)` column:

| Input | Result Rounded to Second |
|---|---|
| `12:00:10.200000` | `12:00:10` |
| `12:00:10.600000` | `12:00:11` |

You can test this directly in SQL:

```sql
SELECT
    CAST('2025-06-10 14:25:36.1234' AS DATETIME(3)) AS rounded_down,
    CAST('2025-06-10 14:25:36.1236' AS DATETIME(3)) AS rounded_up,
    CAST('2025-06-10 14:25:36.600000' AS DATETIME(0)) AS rounded_to_next_second;
```

The cast results reflect the target precision of the temporal type. When testing applications, use values clearly below and above the rounding threshold, such as `.1234` and `.1236`, rather than only a generic value.

## 5. Rounding Can Carry Into the Next Second or Day

When rounding fractional seconds overflows the current second, MySQL adjusts both the seconds and related time components. The carry can propagate across minutes, hours, days, months, or years.

```sql
CREATE TABLE rounding_boundary_demo (
    id INT NOT NULL PRIMARY KEY,
    at_second DATETIME(0) NOT NULL,
    at_millisecond DATETIME(3) NOT NULL
);

INSERT INTO rounding_boundary_demo
    (id, at_second, at_millisecond)
VALUES
    (1,
     '2025-12-31 23:59:59.999600',
     '2025-12-31 23:59:59.999600');

SELECT * FROM rounding_boundary_demo;
```

Expected result:

| Column | Value After Rounding |
|---|---|
| `at_second` | `2026-01-01 00:00:00` |
| `at_millisecond` | `2026-01-01 00:00:00.000` |

Therefore, if a system uses timestamps as sort keys or business boundaries, test values near the end of a second, day, month, and year. Never assume rounding only changes the last few digits.

## 6. Truncating Fractional Seconds Instead of Rounding

In some systems, the requirement is to discard digits beyond the target precision without advancing the timestamp. MySQL provides the `TIME_TRUNCATE_FRACTIONAL` SQL mode to truncate fractional seconds instead of rounding when storing into a column with lower FSP than the input.

For example, with input `2025-06-10 14:25:36.789600`:

| Column | Default (round) | With `TIME_TRUNCATE_FRACTIONAL` (truncate) |
|---|---|---|
| `DATETIME(0)` | `2025-06-10 14:25:37` | `2025-06-10 14:25:36` |
| `DATETIME(3)` | `2025-06-10 14:25:36.790` | `2025-06-10 14:25:36.789` |
| `DATETIME(6)` | `2025-06-10 14:25:36.789600` | `2025-06-10 14:25:36.789600` |

You can enable the mode at session scope for testing:

```sql
-- Save the connection's current sql_mode
SET @old_sql_mode = @@SESSION.sql_mode;

-- Keep existing modes and append TIME_TRUNCATE_FRACTIONAL
SET SESSION sql_mode = CONCAT_WS(
    ',',
    NULLIF(@@SESSION.sql_mode, ''),
    'TIME_TRUNCATE_FRACTIONAL'
);

SELECT @@SESSION.sql_mode;
```

Then insert another row into the test table:

```sql
INSERT INTO fractional_precision_demo
    (id, captured_at_0, captured_at_3, captured_at_6)
VALUES
    (2,
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600');

SELECT *
FROM fractional_precision_demo
WHERE id = 2;
```

In a session with truncate mode, the FSP 0 column keeps `14:25:36`, the FSP 3 column keeps `.789`, and the FSP 6 column preserves `.789600`. After testing, restore the original mode:

```sql
SET SESSION sql_mode = @old_sql_mode;
```

`TIME_TRUNCATE_FRACTIONAL` is an SQL mode, so its scope and lifecycle follow the corresponding session/global configuration. When enabled in a session, other connections do not automatically inherit that change. In applications using a connection pool, avoid letting a request mutate `sql_mode` and return the connection to the pool without resetting its state.

Do not enable this mode merely to mask insufficient schema precision. Choose an FSP suited to the business data first; only use truncation when product rules require dropping extra digits and the team agrees on the behavior.

## 7. Temporal Functions with FSP Parameters

Several current-time functions accept an FSP argument from 0 to 6. Example:

```sql
SELECT
    NOW(0) AS current_to_second,
    NOW(3) AS current_to_millisecond,
    NOW(6) AS current_to_microsecond,
    CURRENT_TIMESTAMP(6) AS current_timestamp_6,
    UTC_TIMESTAMP(6) AS utc_timestamp_6,
    CURTIME(6) AS current_time_6;
```

If FSP is omitted, the function returns the default precision 0. Calling `NOW(6)` alone does not guarantee the target column retains six digits; the column must also declare the matching FSP. Example:

```sql
CREATE TABLE request_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    received_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id)
);

INSERT INTO request_audit (received_at)
VALUES (NOW(6));
```

If the column is `DATETIME(3)`, the `NOW(6)` value will be rounded or truncated according to the session's `sql_mode` on write. To avoid unnecessary conversion, call `NOW(3)` when the column only needs milliseconds.

`NOW(fsp)` and `CURRENT_TIMESTAMP(fsp)` return the current time in the session time zone. `UTC_TIMESTAMP(fsp)` returns UTC time. Fractional-second precision does not change a function's time zone rules.

## 8. DEFAULT and ON UPDATE with Fractional Seconds Precision

For columns that automatically record creation and update times, you can declare `DEFAULT CURRENT_TIMESTAMP(fsp)` and `ON UPDATE CURRENT_TIMESTAMP(fsp)`. Use the same FSP for both the column and the temporal expression to avoid unintended rounding.

```sql
CREATE TABLE document_revision (
    document_id BIGINT UNSIGNED NOT NULL,
    body TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (document_id)
) ENGINE = InnoDB;
```

In this example, creation and update timestamps are stored with six fractional-second digits. If only milliseconds are needed, change both the column type and expressions to FSP 3:

```sql
created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
updated_at DATETIME(3) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3)
```

If the column has a lower FSP than the expression, MySQL must convert the value to the column precision using the active round/truncate rule. Inspect `SHOW CREATE TABLE` to confirm the actual definition matches the intended design.

## 9. Choosing FSP Based on Application Requirements

Not every system needs microseconds. Higher FSP preserves more detail, yet increases storage for fractional digits, index size, and comparison complexity with lower-precision time sources.

| Need | Recommended FSP | Example |
|---|---:|---|
| Business date/time needing only seconds | 0 | Effective date, appointments at minute/second granularity |
| Logging with millisecond resolution | 3 | Request timestamps, application logs |
| Correlating closely spaced events | 6 | Telemetry, audit logs, or data retaining source microseconds |

These are resolution guidelines, not a guarantee that FSP 6 yields unique ordering. Two events can still share the exact same microsecond timestamp; if unique ordering is required, use an auto-increment key, sequence, or secondary sort criterion.

### 9.1. Fractional Seconds Storage Cost

Fractional seconds require extra storage depending on FSP. Under MySQL's temporal storage layout, the fractional-seconds portion adds:

| FSP | Extra Bytes for Fractional Seconds |
|---:|---:|
| 0 | 0 |
| 1–2 | 1 |
| 3–4 | 2 |
| 5–6 | 3 |

This is only the additional space for the fractional seconds, not the total column size. When a temporal column is indexed, index width is also affected by the column type and precision.

## 10. Querying Time Ranges with Fractional Seconds

When filtering data by time, use a half-open interval `[start, end)` to avoid guessing the last digit of a day or second:

```sql
SELECT audit_id, received_at
FROM request_audit
WHERE received_at >= '2025-06-10 00:00:00.000000'
  AND received_at <  '2025-06-11 00:00:00.000000'
ORDER BY received_at, audit_id;
```

A half-open interval includes the start instant and excludes the end instant. This works reliably regardless of whether the column uses FSP 0, 3, or 6; there is no need to write conditions like `23:59:59.999999` to end a day.

If a query performs an equality check against an input timestamp with more digits than the column, ensure the application normalizes precision before binding the parameter. A microsecond value compared against an FSP 3 column may be converted to milliseconds and rounded according to storage rules. For time-based lookups, half-open intervals and parameters matching the column's FSP are generally easier to reason about.

## 11. Migrating from a Non-FSP Column to an FSP Column

A column declared as `DATETIME` is equivalent to FSP 0. Changing it to `DATETIME(3)` or `DATETIME(6)` does not retroactively restore lost precision to existing rows. Existing values only have whole seconds; migration cannot recover historical milliseconds or microseconds.

Example altering a column:

```sql
ALTER TABLE request_audit
    MODIFY received_at DATETIME(6) NOT NULL;
```

After the change, existing values still have a fractional part of `.000000`; new writes can store higher precision if clients send sufficiently detailed values. Before migrating, verify:

- Whether applications and drivers send timestamps with the new FSP or still send second-level precision.
- Whether insert/update statements, defaults, and `ON UPDATE` clauses declare the matching FSP.
- Whether indexes and composite keys grow in size or affect performance.
- Whether comparisons, sorting, and reports assume timestamps only have 1-second resolution.
- Whether the DDL change requires table rebuilds, locks, or impacts replication.

`ALTER TABLE` can consume resources and time depending on storage engine, version, table size, and alteration type. Test on a near-production copy, take backups first, and prepare a rollout/rollback plan before modifying large tables.

## 12. Common Mistakes

- Declaring `DATETIME` and expecting MySQL to store microseconds automatically; the default FSP is 0.
- Assuming `DATETIME(6)` guarantees a clock source accurate to one microsecond.
- Failing to realize MySQL rounds fractional seconds by default when input has more digits than the column.
- Enabling `TIME_TRUNCATE_FRACTIONAL` while forgetting it is session/global state and letting it leak across a connection pool.
- Calling `NOW()` and expecting microseconds; you must specify `NOW(6)` for FSP 6.
- Increasing only the column's FSP without updating the FSP of default expressions or application-supplied values.
- Forgetting that rounding can carry across seconds, days, months, or years.
- Using `23:59:59` as the end-of-day bound and missing records with fractional seconds.
- Thinking migrating from FSP 0 to FSP 6 recovers lost fractional digits on old data.
- Using a microsecond timestamp as a unique key when multiple events can still receive the same value.

## 13. Fractional Seconds Precision Design Checklist

- Chosen `TIME`, `DATETIME`, or `TIMESTAMP` based on temporal semantics and time zone rules.
- Determined required FSP: 0, 3, or 6 (or another value from 0 to 6).
- Explicitly declared FSP on the column instead of relying on defaults.
- Verified the FSP of `NOW()`, `CURRENT_TIMESTAMP()`, or other temporal functions used by the application.
- Understood that inputs with more digits than the column are rounded by default.
- Enabled `TIME_TRUNCATE_FRACTIONAL` only when the business explicitly requires truncation.
- Tested values below and above rounding thresholds, as well as carries across day/year boundaries.
- Used matching FSP for columns and `DEFAULT`/`ON UPDATE` expressions where needed.
- Used half-open interval queries and parameters with compatible precision.
- Accounted for fractional-second storage, index overhead, and migration impact.
- Avoided assuming higher FSP guarantees uniquely ordered events.

FSP controls how many digits MySQL retains after the seconds component in `TIME`, `DATETIME`, and `TIMESTAMP`. By default, MySQL rounds when input precision exceeds column precision; `TIME_TRUNCATE_FRACTIONAL` changes that behavior to truncation. Choosing the right FSP, aligning temporal functions and application code, and testing boundary carries ensures timestamps are stored accurately according to business rules.
