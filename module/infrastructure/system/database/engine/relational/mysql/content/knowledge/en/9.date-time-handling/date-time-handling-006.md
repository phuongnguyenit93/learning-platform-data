# NOW, CURRENT_TIMESTAMP, UTC_TIMESTAMP, and Evaluation Time

MySQL provides current-time functions for recording row creation times, updating rows, and checking time within queries. `NOW()` and `CURRENT_TIMESTAMP` return date and time in the session's time zone; `UTC_TIMESTAMP()` returns UTC date and time. A crucial detail is that these functions capture their value at the moment statement execution begins, so multiple calls within a single statement share the exact same timestamp.

Understanding function evaluation time and connection time zones helps applications store consistent timestamps, especially when multiple services, transactions, or clients in different time zones write data concurrently. This is foundational knowledge for the `DATABASE_MYSQL` module: temporal column design, range queries, indexing, transactions, and managing historical data.

## Objectives

After this lesson, you can:

- Distinguish `NOW()`, `CURRENT_TIMESTAMP`, and `UTC_TIMESTAMP()`.
- Explain when these functions evaluate and their single-statement consistency scope.
- Understand the impact of `time_zone` at session and global levels.
- Choose how to store instants with `TIMESTAMP` and `DATETIME`.
- Declare default/on-update timestamps with microsecond precision.
- Avoid hour-shift bugs when writing UTC to `TIMESTAMP` columns or using connection pools.

## 1. The Three Current-Time Functions

| Function | Return Value | Depends on Session `time_zone`? | Common Use |
|---|---|---|---|
| `NOW()` | Current date and time in the session time zone | Yes | Record current time in the connection's context |
| `CURRENT_TIMESTAMP` | Synonym for `NOW()` | Yes | Used in queries, `DEFAULT`, and `ON UPDATE` |
| `UTC_TIMESTAMP()` | Current date and time in UTC | No | Obtain an explicit UTC point for comparison or processing |

`CURRENT_TIMESTAMP` can be written without parentheses or as `CURRENT_TIMESTAMP()`. `NOW()` and `UTC_TIMESTAMP()` can also be called without arguments or with fractional-second precision, e.g. `NOW(6)`, `UTC_TIMESTAMP(6)`. `LOCALTIME` and `LOCALTIMESTAMP` are synonyms for `NOW()` in MySQL.

Run the following query to inspect the values in the current session:

```sql
SELECT
    NOW() AS session_now,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    UTC_TIMESTAMP() AS utc_now,
    @@SESSION.time_zone AS session_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

`NOW()` and `CURRENT_TIMESTAMP` produce the same value because they are equivalent. If the session is in `+07:00`, their value typically differs from UTC by seven hours; `UTC_TIMESTAMP()` still represents UTC.

### 1.1. Return Values Do Not Carry a Time Zone Label

These functions return a date/time value without an attached offset string such as `+07:00` or region name such as `Asia/Ho_Chi_Minh`. For example, the output `2026-11-19 10:30:00` by itself does not reveal whether it is UTC or local time. Its semantics depend on which function generated it and how the application stores/interprets it.

Therefore, when passing a date/time value across an API or message queue, specify explicitly whether it is a UTC instant or local wall-clock time. For text timestamps, ISO 8601 with an offset such as `2026-11-19T03:30:00Z` or `2026-11-19T10:30:00+07:00` makes the time zone unambiguous.

## 2. When Does MySQL Capture the Time Value?

`NOW()`, `CURRENT_TIMESTAMP`, and `UTC_TIMESTAMP()` return a stable value within the scope of a single statement. MySQL captures the time when statement execution starts; all calls to these functions within that statement use the same point in time.

Example:

```sql
SELECT
    NOW(6) AS first_call,
    SLEEP(1) AS wait_result,
    NOW(6) AS second_call,
    CURRENT_TIMESTAMP(6) AS current_call;
```

In this single `SELECT`, `first_call`, `second_call`, and `current_call` share the same timestamp even though `SLEEP(1)` delays the statement. The `SLEEP()` example is solely to demonstrate evaluation timing; do not put it in regular application queries.

### 2.1. Multi-Row Statements Share the Same Timestamp

In a multi-row insert, all rows inserted by the same statement receive the same `NOW()` value unless distinct values are supplied:

```sql
INSERT INTO audit_event (event_type, created_at)
VALUES
    ('ORDER_CREATED', NOW(6)),
    ('PAYMENT_REQUESTED', NOW(6)),
    ('EMAIL_QUEUED', NOW(6));
```

All three rows written by this single statement receive the same `created_at` timestamp. This is helpful when you want every record in a batch to reflect the same database processing instant.

### 2.2. NOW Is Not the Transaction Start Time

`NOW()` is fixed per statement, not across an entire transaction. Two separate statements in the same transaction can receive different values:

```sql
START TRANSACTION;

INSERT INTO order_audit (order_id, action, occurred_at)
VALUES (1001, 'CREATED', NOW(6));

UPDATE orders
SET status = 'PROCESSING', updated_at = NOW(6)
WHERE order_id = 1001;

COMMIT;
```

If the two statements run at different moments, `occurred_at` and `updated_at` can differ even though they belong to the same transaction. A transaction guarantees atomicity of data changes via InnoDB; it does not freeze the clock at `START TRANSACTION`.

If multiple operations within a transaction need a shared business timestamp, capture the timestamp once and reuse it:

```sql
START TRANSACTION;
SET @operation_time = NOW(6);

INSERT INTO order_audit (order_id, action, occurred_at)
VALUES (1001, 'CREATED', @operation_time);

UPDATE orders
SET status = 'PROCESSING', updated_at = @operation_time
WHERE order_id = 1001;

COMMIT;
```

In a real application, you can capture a single `Instant` at the service layer and bind that same value to each statement. If using a session variable such as `@operation_time`, remember the variable persists on the connection after the transaction ends; with a connection pool, never let an old value accidentally get reused by a subsequent request.

### 2.3. Distinction from SYSDATE()

`SYSDATE()` has different semantics: it returns the exact time at which the function itself executes, so multiple calls inside the same statement can return different values. This contrasts with `NOW()`, which is fixed at statement start. `SYSDATE()` also carries determinism and replication considerations; unless you have a clear reason, `NOW()`/`CURRENT_TIMESTAMP` is usually much more predictable for business timestamps.

## 3. MySQL Time Zones

MySQL maintains time zones at the server and session levels. The session's `time_zone` value governs how functions like `NOW()` represent time and how MySQL converts values when reading/writing `TIMESTAMP` columns.

Inspect the relevant variables:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

- `@@GLOBAL.time_zone`: default time zone assigned by the server to new connections.
- `@@SESSION.time_zone`: time zone currently active for the current connection.
- `@@SYSTEM_TIME_ZONE`: OS time zone name/value detected by the server at startup; this is not a variable for setting per-session time zones.

`time_zone` can be `SYSTEM`, an offset such as `+00:00` or `+07:00`, or a zone name such as `Asia/Ho_Chi_Minh` if MySQL's time zone tables are loaded.

### 3.1. Setting the Session Time Zone

Set UTC for the current connection:

```sql
SET time_zone = '+00:00';
```

Or use a zone name if timezone tables are populated:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';
```

`SET time_zone` without the `GLOBAL` keyword applies to the current session only. Other connections are unaffected. This is a common pattern when applications borrow connections from a pool: configure the pool so every connection gets a consistent session timezone upon creation or checkout.

### 3.2. Setting the Default Time Zone for New Connections

An administrator can change the global value:

```sql
SET GLOBAL time_zone = '+00:00';
```

This change affects subsequent new sessions; already-open sessions keep their current `@@SESSION.time_zone`. Runtime global settings may be lost upon MySQL restart. To persist them, set `default-time-zone` under the `[mysqld]` section of the configuration file and restart according to operational procedures:

```ini
[mysqld]
default-time-zone = '+00:00'
```

Changing the global timezone requires appropriate administrative privileges and evaluation of existing applications. Do not change a running server's timezone solely to patch a few shifted values without verifying how clients write data.

### 3.3. Fixed Offsets vs. Named Zones

The `+07:00` offset always shifts seven hours from UTC; it carries no historical rules or Daylight Saving Time (DST). A named zone like `America/New_York` includes historical and scheduled offset transitions. For regions with DST, named zones are generally more suitable than fixed offsets when converting local times.

MySQL needs loaded timezone tables to recognize zone names. If `SET time_zone = 'Asia/Ho_Chi_Minh'` fails with an invalid time zone error, check the server's timezone data and OS update workflow. Offsets such as `+00:00` do not require looking up zone name tables.

## 4. NOW and UTC_TIMESTAMP Under Different Session Time Zones

For example, switch the session to UTC and call the functions:

```sql
SET time_zone = '+00:00';
SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6);
```

In a UTC session, all three values match closely because `NOW()`/`CURRENT_TIMESTAMP` are using UTC and `UTC_TIMESTAMP()` also returns UTC.

Switch the session to the `+07:00` offset:

```sql
SET time_zone = '+07:00';
SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6);
```

`NOW()` and `CURRENT_TIMESTAMP` display the time in `+07:00`; `UTC_TIMESTAMP()` remains in UTC. All values represent the same actual instant, differing only in time zone representation.

Do not use `UTC_TIMESTAMP()` to infer a client's timezone. It always returns UTC and has no knowledge of where the user is located. To display local time, the application must know the user's timezone or obtain it from business configuration.

## 5. NOW, CURRENT_TIMESTAMP, and TIMESTAMP/DATETIME Columns

`TIMESTAMP` and `DATETIME` handle time zones differently:

| Characteristic | `TIMESTAMP` | `DATETIME` |
|---|---|---|
| Storage semantics | Instant converted between session timezone and UTC | Calendar date/time value, not automatically bound to a timezone |
| On write | MySQL interprets input in session timezone, then converts to UTC for storage | Stores the submitted date/time components without timezone conversion |
| On read | Converts from UTC to the connection's session timezone | Returns the stored value without timezone conversion |
| MySQL 8.0 value range | Approximately 1970-01-01 UTC to 2038-01-19 UTC | 1000-01-01 to 9999-12-31 |
| Use when | Representing an instant and wanting MySQL to convert by session timezone | Storing calendar times, appointments, opening hours, or values whose timezone is managed separately |

`TIMESTAMP` does not store the sender's original zone name or offset. If you need to know which region the user entered the time in, store a separate timezone ID such as `Asia/Ho_Chi_Minh` alongside the instant or calendar value.

### 5.1. Example Writing and Reading TIMESTAMP

Assume the session timezone is `+07:00`:

```sql
SET time_zone = '+07:00';

CREATE TABLE event_time_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurred_at TIMESTAMP(6) NOT NULL,
    wall_clock_at DATETIME(6) NOT NULL,
    PRIMARY KEY (event_id)
);

INSERT INTO event_time_demo (occurred_at, wall_clock_at)
VALUES (NOW(6), NOW(6));

SELECT occurred_at, wall_clock_at
FROM event_time_demo;
```

`NOW(6)` returns the time in the `+07:00` session. When assigned to `TIMESTAMP`, MySQL converts that value to UTC for storage; when read in the same session, MySQL converts it back to `+07:00`. For `DATETIME`, MySQL stores the local clock components verbatim without conversion.

If you read the same row in a UTC session:

```sql
SET time_zone = '+00:00';

SELECT occurred_at, wall_clock_at
FROM event_time_demo;
```

`occurred_at` will display in UTC, whereas `wall_clock_at` keeps the exact stored clock time. This is why column semantics must be agreed upon before allowing applications across different time zones to read and write.

### 5.2. Be Careful When Writing UTC_TIMESTAMP to TIMESTAMP

`UTC_TIMESTAMP()` returns a UTC date/time value, yet when assigned to a `TIMESTAMP` column, MySQL still interprets the input value using `@@SESSION.time_zone` and converts it to UTC for storage. If the session is `+07:00`, passing `UTC_TIMESTAMP()` directly into a `TIMESTAMP` column shifts the stored instant by seven hours.

Unsafe example when the session is `+07:00`:

```sql
SET time_zone = '+07:00';

INSERT INTO event_time_demo (occurred_at, wall_clock_at)
VALUES (UTC_TIMESTAMP(6), UTC_TIMESTAMP(6));
```

For `occurred_at`, the UTC value is misinterpreted as `+07:00` local time before being converted to UTC for storage. `wall_clock_at` keeps the UTC components verbatim; it does not automatically know they represent UTC.

Two clear ways to avoid this mistake:

1. Set the application's session timezone to UTC and use `NOW(6)`/`CURRENT_TIMESTAMP(6)` for `TIMESTAMP` columns.
2. If explicitly passing a UTC value into `TIMESTAMP`, ensure the session timezone is also `+00:00` during the write.

For a `DATETIME` column intended by convention to store UTC, `UTC_TIMESTAMP(6)` can be stored as-is, provided that convention is clearly documented in schema and code since MySQL will not convert it on read.

## 6. DEFAULT CURRENT_TIMESTAMP and ON UPDATE

MySQL supports automatically assigning the current timestamp on insert or update using `DEFAULT CURRENT_TIMESTAMP` and `ON UPDATE CURRENT_TIMESTAMP`.

Example audit table:

```sql
CREATE TABLE task (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (task_id)
) ENGINE=InnoDB;
```

- `created_at` automatically receives the insert timestamp if the statement omits a value.
- `updated_at` receives the insert timestamp and automatically updates when another column in the row actually changes value.
- If an `UPDATE` statement reassigns the exact same current values, MySQL does not necessarily alter `updated_at`.
- The application can explicitly set `updated_at = CURRENT_TIMESTAMP(6)` if business rules require refreshing the timestamp on a specific operation.

`CURRENT_TIMESTAMP` can also be used with `DATETIME`. Choose `TIMESTAMP` or `DATETIME` based on semantics and value range, not merely because their default syntax is identical.

### 6.1. Fractional Seconds Precision

MySQL supports fractional seconds precision (FSP) from 0 to 6:

| Declaration | Precision |
|---|---|
| `NOW()` or `NOW(0)` | No fractional seconds |
| `NOW(3)` | Milliseconds, 3 digits |
| `NOW(6)` | Microseconds, 6 digits |
| `TIMESTAMP` / `DATETIME` | Default FSP is 0 |
| `TIMESTAMP(6)` / `DATETIME(6)` | Stores fractional seconds down to microseconds |

To store microseconds, both the time function and the column should be declared with matching precision:

```sql
CREATE TABLE request_log (
    request_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_id)
);

INSERT INTO request_log () VALUES ();
SELECT received_at FROM request_log;
```

If the function returns precision 6 while the column only has precision 0 or 3, the fractional part is handled according to MySQL's conversion rules. The `TIME_TRUNCATE_FRACTIONAL` SQL mode controls truncating excess digits instead of rounding when writing to a lower-FSP column. Standardize precision across schema, application, and APIs to avoid unintended precision loss.

## 7. Using in Queries and Transactions

### 7.1. Filtering Data Relative to Current Time

Example fetching orders created in the last 24 hours:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= NOW() - INTERVAL 24 HOUR;
```

If `created_at` is `TIMESTAMP`, ensure the session timezone follows application convention. If a `DATETIME` column stores UTC, compare against `UTC_TIMESTAMP()` rather than `NOW()` in a local session.

Example with a `DATETIME` column storing UTC:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 24 HOUR;
```

Avoid wrapping indexed columns in conversion functions inside `WHERE` predicates whenever possible, as doing so can prevent efficient range index usage. Normalize boundary timestamps beforehand and compare directly against the column.

### 7.2. Sharing a Single Timestamp Across Multiple Operations

When an audit row, business record, and outbox event need the exact same timestamp, generate the timestamp once in the application or session and bind it repeatedly:

```java
Instant operationTime = clock.instant();

// Use the same operationTime as a parameter for INSERT/UPDATE statements
// within the same JDBC transaction.
```

When using JDBC, represent instants with `java.time.Instant` and convert to the JDBC type compatible with Connector/J and the schema. If using `LocalDateTime`, the application must clearly track the assumed timezone because `LocalDateTime` carries no offset or zone.

### 7.3. Obtaining Time in the Database vs. the Application

| Need | Typical Best Fit |
|---|---|
| Single multi-row statement needing a shared database timestamp | `NOW(6)` or `CURRENT_TIMESTAMP(6)` |
| Multiple statements in one transaction needing the same timestamp | Capture once in the application or store in a variable/session parameter and reuse |
| Explicit UTC needed for SQL calculations | `UTC_TIMESTAMP(6)` |
| Consistent clock across multiple services | Synchronize system clocks and standardize UTC instant passing; optionally use a managed time source |
| Measuring execution duration | Use a monotonic clock in the application rather than subtracting two wall-clock timestamps |

MySQL reads time from the host OS clock. `NOW()` is not a monotonic clock; if the OS clock is adjusted, wall-clock values across statements can jump or move backward. Do not use it as a precision timer for benchmarks.

## 8. Connection Pools and Session Time Zones

Applications commonly reuse connections through HikariCP or another connection pool. `time_zone` is a session property, so if one request changes the timezone and returns the connection to the pool, the next request may receive that connection with the altered timezone.

Practical safeguards:

- Configure all connections to use one consistent timezone, typically UTC.
- Set the timezone on connection initialization or via the pool's connection initialization hook.
- If the application changes timezone per request, restore state before returning the connection to the pool; better yet, avoid per-request changes.
- Do not assume `SET GLOBAL time_zone` changes existing sessions inside the pool.
- Document clearly which columns store UTC instants (`TIMESTAMP` or `DATETIME` by convention) and which store local wall-clock times.

Example session initialization statement:

```sql
SET time_zone = '+00:00';
```

Run this on every connection that needs configuring, not just an arbitrary connection in the pool.

## 9. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `NOW()` is shifted relative to the user's clock | Session timezone differs from user timezone or storage convention | Check `@@SESSION.time_zone`, `@@GLOBAL.time_zone`; verify whether column is `TIMESTAMP` or `DATETIME` |
| `NOW()` and `UTC_TIMESTAMP()` differ | Session timezone is not UTC | Expected behavior; verify session offset and convention |
| Writing `UTC_TIMESTAMP()` into `TIMESTAMP` reads back shifted | MySQL interprets input in session timezone before storing UTC | Set session timezone to `+00:00` when writing or use `NOW()` in a UTC session |
| One transaction produces two different `NOW()` values | Two calls occurred in separate statements | Capture one timestamp and reuse it if business logic requires matching timestamps |
| Microseconds are lost | Function or column uses a lower FSP | Use `NOW(6)` and `TIMESTAMP(6)`/`DATETIME(6)`; check `TIME_TRUNCATE_FRACTIONAL` |
| Connection pool returns different times across requests | Session timezone was mutated and not reset | Standardize timezone on connection init and restore session state |
| `SET time_zone = 'Region/City'` reports invalid timezone | Timezone tables not loaded or missing zone name | Load/update timezone tables or use an appropriate fixed offset |

Quick diagnostic commands:

```sql
SELECT
    NOW(6) AS session_now,
    UTC_TIMESTAMP(6) AS utc_now,
    @@SESSION.time_zone AS session_tz,
    @@GLOBAL.time_zone AS global_tz,
    @@SYSTEM_TIME_ZONE AS system_tz;

SHOW CREATE TABLE orders\G
```

Always inspect the exact connection executing the failing statement. Running `SELECT @@SESSION.time_zone` on a separate admin connection does not reveal the application session's timezone.

## 10. Practice Exercises

Perform the following in a dedicated lab database:

1. Run `SELECT NOW(6), CURRENT_TIMESTAMP(6), UTC_TIMESTAMP(6)` with the session at `SYSTEM`, `+00:00`, and `+07:00`; record how the values change.
2. Run a single `SELECT` containing two `NOW(6)` calls and a brief pause to confirm calls within the same statement share one timestamp.
3. Run two `INSERT` statements inside one transaction, each calling `NOW(6)`; compare timestamps and explain why NOW is not fixed across a transaction.
4. Create a table with `TIMESTAMP(6)` and `DATETIME(6)`. Insert `NOW(6)` while the session is `+07:00`, then read back from a `+00:00` session to observe the difference.
5. In the lab, test writing `UTC_TIMESTAMP(6)` into a `TIMESTAMP` column while the session is `+07:00`, then switch the session to UTC to observe the hour shift. Repeat when the session is `+00:00`.
6. Create a table with `DEFAULT CURRENT_TIMESTAMP(6)` and `ON UPDATE CURRENT_TIMESTAMP(6)`. Test inserting, updating another column, and updating with the same existing values to observe when auto-update triggers.
7. Create `DATETIME(3)` and `DATETIME(6)` columns, insert microsecond values, and inspect stored precision.
8. Write a JDBC example using the same `Instant` for two statements in a transaction and verify both rows share the exact timestamp.

You have completed this lesson when you can predict the output of all three functions for any session timezone, explain statement evaluation timing, choose the right column type, and avoid hour-shift errors when reading/writing across multiple connections.

## 11. Key Principles to Remember

- `CURRENT_TIMESTAMP` is a synonym for `NOW()`; both use the session timezone.
- `UTC_TIMESTAMP()` returns UTC date and time regardless of session timezone.
- `NOW`/`CURRENT_TIMESTAMP`/`UTC_TIMESTAMP` are stable within a single statement, not fixed across an entire transaction.
- `TIMESTAMP` converts by session timezone on write/read; `DATETIME` does not auto-convert timezones.
- When storing instants, standardize on a UTC session timezone and UTC conventions across the application.
- Be careful when assigning `UTC_TIMESTAMP()` to `TIMESTAMP` if the session is not in UTC.
- Use FSP 3 or 6 when the business needs milliseconds/microseconds; align function and column precision.
- Standardize session timezone across the connection pool; `SET GLOBAL` does not affect already-open sessions.
- Never use wall-clock timestamps to measure elapsed duration; use a monotonic clock in the application.
