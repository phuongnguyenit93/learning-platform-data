# SYSDATE, SYSTIMESTAMP, CURRENT_DATE, and CURRENT_TIMESTAMP in Oracle Database

An application in Vietnam may connect to an Oracle Database hosted in a data center using a different time zone. When running `SYSDATE` and `CURRENT_DATE` at the same moment, you may get **two different clock times** and both are valid. They are derived from different time contexts. In addition, `SYSDATE` has type `DATE` even though it contains hours, minutes, and seconds; `SYSTIMESTAMP` can contain fractional seconds and time zone info. Without clearly distinguishing them, applications easily record wrong creation instants, filter "today" on the wrong calendar date, or apply double time zone conversions.

This lesson in the **Date/Time and NLS** section explains Oracle's four current-time functions: **`SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, and `CURRENT_TIMESTAMP`**. We examine clock sources, session time zone impact, return data types, how NLS formats values, and reliable ways to store and compare instants.

After this lesson, you will be able to:

- Distinguish **database server time** from **session time zone time**.
- Explain the difference between `DATE` and `TIMESTAMP WITH TIME ZONE`.
- Write queries that display hours, fractional seconds, and time zone offsets with `TO_CHAR`.
- Inspect `SESSIONTIMEZONE`, `DBTIMEZONE`, NLS parameters, and set session time zone during hands-on practice.
- Use `AT TIME ZONE`, `SYS_EXTRACT_UTC`, and datetime literals with offsets to compare **the same absolute instant**.
- Choose column types, default values, and range-filtering patterns for multi-time-zone applications.

> **Example prerequisites:** The SQL snippets can be run in SQL*Plus, SQLcl, SQL Developer, or any Oracle SQL tool. Clock outputs change on every execution, so values shown in tables are **illustrative**, not fixed outputs. `ALTER SESSION` commands affect only the current session; table-creation exercises should only run in a practice schema/PDB.

## 1. Two axes of distinction: clock source and return data type

Keep this table in mind before writing SQL:

| Function | Time source/context | Return type | Time precision | Time zone info inside the value? |
| --- | --- | --- | --- | --- |
| `SYSDATE` | Operating system clock on the **database server** | `DATE` | To the **second** | **No** |
| `SYSTIMESTAMP` | Clock on the **database server**, with server time zone/offset | `TIMESTAMP WITH TIME ZONE` | Includes **fractional seconds** | **Yes** |
| `CURRENT_DATE` | Current instant interpreted in the **session time zone** | `DATE` | To the **second** | **No** |
| `CURRENT_TIMESTAMP` | Current instant interpreted in the **session time zone** | `TIMESTAMP WITH TIME ZONE` | Includes **fractional seconds** | **Yes** |

In a typical Oracle environment:

~~~text
                      CURRENT INSTANT
                              |
               +--------------+---------------+
               |                              |
               v                              v
       Database server clock           Session time zone
               |                              |
          +----+----+                    +----+----+
          |         |                    |         |
          v         v                    v         v
      SYSDATE  SYSTIMESTAMP        CURRENT_DATE CURRENT_TIMESTAMP
       DATE     TIMESTAMP             DATE       TIMESTAMP
                WITH TIME ZONE                   WITH TIME ZONE
~~~

Suppose **hypothetically** the server runs on UTC (`+00:00`), while the session is configured to `+07:00`. At the same moment:

| Function | Illustrative value |
| --- | --- |
| `SYSDATE` | `2026-11-14 08:30:00` |
| `SYSTIMESTAMP` | `2026-11-14 08:30:00.123 +00:00` |
| `CURRENT_DATE` | `2026-11-14 15:30:00` |
| `CURRENT_TIMESTAMP` | `2026-11-14 15:30:00.123 +07:00` |

Two timestamps with different offsets can represent **the exact same instant**, such as `08:30 +00:00` and `15:30 +07:00`. Meanwhile, the two `DATE` values contain no offset, so on their own they do not specify which time zone produced them.

**Note on concurrency:** If you invoke two functions at slightly different moments, they can differ by milliseconds or cross a second/day boundary. The example table treats them as captured virtually simultaneously to highlight time zone differences. On some deployments with special time settings, server-side function behavior may also be governed by database policy; check actual configuration when comparing environments.

## 2. Understanding Oracle's `DATE` type: not just a date

In Oracle SQL, **`DATE` stores year, month, day, hour, minute, and second**. It is unlike a date-only type such as `LocalDate` in many programming languages.

Example:

~~~sql
SELECT
    SYSDATE AS server_datetime,
    CURRENT_DATE AS session_datetime
FROM dual;
~~~

If your tool displays only `14-NOV-26`, that **does not mean the time portion was lost**. The default display format may simply omit the time. Format it explicitly:

~~~sql
SELECT
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_datetime,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_datetime
FROM dual;
~~~

Now you see hours, minutes, and seconds. However, **you cannot extract fractional seconds or a time zone offset** directly from a plain `DATE`, because they are not stored in the value.

### 2.1. The `TIMESTAMP WITH TIME ZONE` type

`SYSTIMESTAMP` and `CURRENT_TIMESTAMP` return `TIMESTAMP WITH TIME ZONE` (often abbreviated `TSTZ`). It includes date/time fields, **fractional seconds**, and associated time zone information. The time zone may be represented as an offset like `+07:00` or a region name depending on how the value was constructed; specific offsets can vary with daylight saving time.

~~~sql
SELECT
    TO_CHAR(
        SYSTIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS server_timestamp,
    TO_CHAR(
        CURRENT_TIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS session_timestamp
FROM dual;
~~~

In the format above:

- `YYYY-MM-DD`: year, month, day.
- `HH24:MI:SS`: 24-hour hour, minute, second; **`MI` is minute, `MM` is month**.
- `FF3`: displays three fractional-second digits, typically corresponding to milliseconds.
- `TZH:TZM`: hours/minutes of the **UTC offset** attached to the timestamp value.

`FF3` is only a **display format**; it does not mean the underlying data or operating system only has three digits of precision. Actual resolution depends on the OS and how Oracle retrieves system time.

### 2.2. Quick comparison of datetime data types

| Oracle data type | Date/time | Fractional seconds | Time zone in value | Notes |
| --- | --- | --- | --- | --- |
| `DATE` | Yes | No | No | Precision to the second |
| `TIMESTAMP(p)` | Yes | Yes, per `p` | No | Local date-time value, no time zone specified |
| `TIMESTAMP(p) WITH TIME ZONE` | Yes | Yes | Yes | Represents an absolute instant with offset/region |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Yes | Yes | Does not preserve input zone like TSTZ; displays per session | Oracle normalizes for storage relative to database time zone and displays in session time zone |

Do not pick `DATE` simply because a column is named `CREATED_DATE` if business requirements demand sub-second precision and cross-time-zone comparison.

## 3. `SYSDATE`: current time on the database server

### 3.1. Basic usage

`SYSDATE` takes no arguments:

~~~sql
SELECT SYSDATE FROM dual;

SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')
       AS server_now
FROM dual;
~~~

In standard deployments, `SYSDATE` reads the operating system clock where the Oracle Database server runs. It does not use the client machine's time zone to construct a new timestamp. An application in Vietnam and one in another country querying the same database will see close `SYSDATE` values even if their session time zones differ.

`SYSDATE` returns `DATE`, so it:

- Contains **year, month, day, hour, minute, second**.
- Has no fractional seconds.
- Carries no offset or time zone region.
- Works in Oracle date arithmetic—for example, `SYSDATE + 1` adds **one day** to the `DATE`.

Example computing a time bound on `DATE`:

~~~sql
SELECT
    TO_CHAR(SYSDATE,     'YYYY-MM-DD HH24:MI:SS') AS now_value,
    TO_CHAR(SYSDATE + 1, 'YYYY-MM-DD HH24:MI:SS') AS one_day_later
FROM dual;
~~~

This snippet shows day arithmetic on `DATE`; in calendar scheduling with daylight saving time, "24 absolute hours later" and "the same wall-clock time tomorrow in a time zone region" are not always identical. When region-aware calendar arithmetic is needed, use an appropriate time zone type.

### 3.2. When to use `SYSDATE`

`SYSDATE` is suitable for:

- Systems standardized on the database server's clock convention.
- Legacy tables storing `DATE` with an established time convention.
- Administrative SQL scripts inspecting server time to the second.

Limitation: when a `DATE` column records creation times, **no time zone is stored with the value**. If the database is migrated to a server in a different OS time zone, comparing historical values against new ones can break unless the system enforces a clear time zone convention.

### 3.3. `TRUNC(SYSDATE)` is start of day on the server clock

~~~sql
SELECT
    TO_CHAR(TRUNC(SYSDATE), 'YYYY-MM-DD HH24:MI:SS')
        AS start_of_server_day
FROM dual;
~~~

`TRUNC(SYSDATE)` resets hour/minute/second to `00:00:00` in **the server's date/time context**. It is **not necessarily 00:00 for a user in Vietnam** if the server runs in another time zone.

## 4. `SYSTIMESTAMP`: database server time with fractional seconds and time zone

`SYSTIMESTAMP` is an important choice when you want to record an **event instant** that can be compared consistently across time zones.

~~~sql
SELECT
    SYSTIMESTAMP AS raw_server_timestamp,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')
        AS formatted_server_timestamp
FROM dual;
~~~

A `TIMESTAMP WITH TIME ZONE` value identifies an instant via its attached offset. For example:

~~~text
2026-11-14 08:30:00.123456 +00:00
2026-11-14 15:30:00.123456 +07:00
~~~

If both rows refer to the same instant, they represent **the exact same point in time**, even though their local clock representations differ.

### 4.1. Using `AT TIME ZONE` to display an instant in another zone

~~~sql
SELECT
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_view,
    TO_CHAR(
        SYSTIMESTAMP AT TIME ZONE '+07:00',
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS utc_plus_7_view,
    TO_CHAR(
        SYSTIMESTAMP AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS utc_view
FROM dual;
~~~

`AT TIME ZONE` **converts the representation of an instant** to the target time zone. It does not merely add "+7" to the hour digit while ignoring the date/offset. For regions observing daylight saving time, converting by **region name** and specific date applies the exact rules known to Oracle.

### 4.2. Extracting UTC time

~~~sql
SELECT
    SYS_EXTRACT_UTC(SYSTIMESTAMP) AS utc_timestamp
FROM dual;
~~~

`SYS_EXTRACT_UTC` returns a `TIMESTAMP` normalized to UTC, **without a time zone field in the return data type**. If you store it in a `TIMESTAMP` column, the application must document and enforce that "all values in this column are UTC"; the `TIMESTAMP` type alone does not carry that guarantee.

### 4.3. Limitations of OS-clock timestamps

`SYSTIMESTAMP` reflects server time and its corresponding offset; in multi-host/RAC environments or when host clocks are inconsistently configured, monitoring clock synchronization (NTP and infrastructure configuration) remains critical. Time functions do not replace transaction ordering mechanisms or a global logical clock; two close events on different machines should not be strictly ordered solely by timestamp when distributed correctness is required.

## 5. `CURRENT_DATE`: DATE interpreted in the session time zone

`CURRENT_DATE` returns **the current time in the session time zone**, as a `DATE`, with no offset stored in the value:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_time_zone,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS')
        AS current_date_in_session
FROM dual;
~~~

If the session is `+07:00` while the server runs in UTC, `CURRENT_DATE` yields a clock value 7 hours ahead of `SYSDATE` at the same instant. Near midnight, **the calendar date itself can also differ**.

### 5.1. Changing the session time zone

In an isolated lab session:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now
FROM dual;
~~~

Then test another offset:

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now
FROM dual;
~~~

You will see `CURRENT_DATE` change its **local clock representation**, whereas `SYSDATE` is unaffected by the session `TIME_ZONE` variable in standard configurations. Both functions still return **the current instant**; they do not "turn back the system clock." If two queries run a few seconds apart, `SYSDATE` naturally advances in real time.

Record the initial `SESSIONTIMEZONE` and restore it after the exercise with `ALTER SESSION SET TIME_ZONE = '...'`, or close the lab session. This setting does not propagate to other sessions or application connection pools.

### 5.2. Using `CURRENT_DATE` to determine the session's "today"

~~~sql
SELECT
    TO_CHAR(TRUNC(CURRENT_DATE), 'YYYY-MM-DD HH24:MI:SS')
        AS session_day_start,
    TO_CHAR(TRUNC(SYSDATE), 'YYYY-MM-DD HH24:MI:SS')
        AS server_day_start
FROM dual;
~~~

If a UTC server is at 18:30 on November 14 and the session is `+07:00`, the session is already at **01:30 on November 15**. In that case, `TRUNC(CURRENT_DATE)` and `TRUNC(SYSDATE)` produce **two different dates**.

This matters for user-facing logic like "today's orders" or "due date." However, choosing `CURRENT_DATE` alone is insufficient if rows in a `DATE` column were stored using another time zone: the filter must apply **the same time convention** to both the data column and the query bounds.

## 6. `CURRENT_TIMESTAMP`: timestamp in the session time zone

`CURRENT_TIMESTAMP` returns `TIMESTAMP WITH TIME ZONE`—the same **type family** as `SYSTIMESTAMP`—but its offset/region is determined by the session time zone:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(
        CURRENT_TIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
    ) AS current_timestamp_value
FROM dual;
~~~

You can request a specific fractional-second precision when calling the function, for example:

~~~sql
SELECT
    CURRENT_TIMESTAMP(3) AS session_timestamp_to_milliseconds
FROM dual;
~~~

The number in parentheses controls the fractional-second precision of the result; **it does not change the session time zone**.

### 6.1. Comparing `CURRENT_TIMESTAMP` with `SYSTIMESTAMP`

~~~sql
SELECT
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_clock,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS session_clock
FROM dual;
~~~

If server and session use different time zones, **the two local time strings differ**. Once converted to UTC, they represent nearly identical instants. Never compare formatted strings character-by-character to conclude that two instants differ.

### 6.2. When should you use `CURRENT_TIMESTAMP`?

It is suitable when:

- The application wants a current instant **carrying an offset** matching the connection session.
- You need to display or store timestamps in the zone configured for the session.
- There is a clear contract ensuring the session time zone is initialized by the application or connection pool before executing operations.

If the goal is simply **recording an accurate instant for auditing**, `SYSTIMESTAMP` is also appropriate. Both produce valid offset-aware values; what matters is documenting and enforcing a consistent column type and time zone policy across the application.

**Connection pool caution:** a client might run `ALTER SESSION SET TIME_ZONE` and return the connection to the pool. The next session borrowing that connection could inherit that setting if the pool does not reset/reinitialize it. Therefore, when relying on `CURRENT_DATE`/`CURRENT_TIMESTAMP`, set the time zone during session initialization and verify it before use.

## 7. `SESSIONTIMEZONE`, `DBTIMEZONE`, and the database server time zone

These three concepts are **not identical**:

| Source | How to inspect | How is it used? |
| --- | --- | --- |
| **Session time zone** | `SESSIONTIMEZONE` | `CURRENT_DATE`, `CURRENT_TIMESTAMP`, and display of `TIMESTAMP WITH LOCAL TIME ZONE` |
| **Database time zone** | `DBTIMEZONE` | Normalization base for `TIMESTAMP WITH LOCAL TIME ZONE` and certain database-level operations |
| **Database server clock/time zone** | `SYSDATE`, `SYSTIMESTAMP`, and host config | Time provided by the server OS to server-side functions in standard deployments |

Query:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    DBTIMEZONE AS database_tz,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_timestamp,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS session_timestamp
FROM dual;
~~~

Suppose `DBTIMEZONE = '+00:00'` and `SESSIONTIMEZONE = '+07:00'`. **Do not assume the server OS necessarily runs at `+00:00`.** Database time zone is a database property, not a function returning the host's current OS time zone. In particular, turning a `DATE` from `SYSDATE` into an instant by blindly attaching `DBTIMEZONE` can be wrong if the server clock runs in a different time zone.

### 7.1. Offsets vs. time zone regions

A session can use:

~~~sql
-- Fixed offset; does not automatically adjust for daylight saving time.
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

Or a **time zone region** supported by Oracle's time zone file:

~~~sql
-- Common region example; run only if you want to practice DST behavior.
ALTER SESSION SET TIME_ZONE = 'America/New_York';
~~~

Difference:

- `+07:00` is a **fixed UTC offset**.
- `America/New_York` is a region name that applies daylight saving time rules according to the **specific calendar date** and the Oracle time zone data version installed.

Do not replace a region with a fixed offset when the business requirement is "9:00 AM in New York on a future date," because summer and winter offsets differ. Conversely, for a known past instant, an offset like `+07:00` is sufficient to convert to an equivalent representation at that moment.

If a region is unsupported on the system, Oracle may raise a time zone error; the DBA should check the time zone file and supported regions rather than altering timestamp data to force execution.

### 7.2. Watch out at DST boundaries

In regions with daylight saving time, certain local times **do not exist** when clocks spring forward, and **occur twice** when clocks fall back. If data stores only a `TIMESTAMP` (without offset), such as "01:30" on a transition day, it can be impossible to tell which instant was meant.

`TIMESTAMP WITH TIME ZONE` with an appropriate offset/region pinpoints the exact instant. When parsing local times with a time zone region, Oracle also provides rules to detect or handle invalid/ambiguous times; applications must design validation for scheduled appointments in DST regions.

## 8. NLS: display formatting differs from stored values

**NLS (National Language Support)** encompasses many settings controlling how Oracle handles languages, characters, sorting, and formatting. For this lesson, two distinct groups matter:

1. **Session time zone** governs `CURRENT_DATE` and `CURRENT_TIMESTAMP`.
2. **NLS datetime formats** govern how a `DATE`/`TIMESTAMP` value is **implicitly converted to a string** for display or parsing in certain contexts.

Changing `NLS_DATE_FORMAT` **does not alter the instant**, does not shift server time to session time, and does not add a time zone to a `DATE` column.

### 8.1. Relevant NLS parameters

| Parameter | Role |
| --- | --- |
| `NLS_DATE_FORMAT` | Default format for `DATE` during implicit conversion to string |
| `NLS_TIMESTAMP_FORMAT` | Default format for `TIMESTAMP` without time zone |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default format for `TIMESTAMP WITH TIME ZONE` |
| `NLS_DATE_LANGUAGE` | Language used for month/day names and textual datetime components |
| `NLS_TERRITORY` | Can influence regional presentation defaults |

Inspect values in the session:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
~~~

### 8.2. Changing session formats

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT =
    'YYYY-MM-DD HH24:MI:SS';

ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM';

SELECT SYSDATE, SYSTIMESTAMP, CURRENT_DATE, CURRENT_TIMESTAMP
FROM dual;
~~~

These commands only change how Oracle **renders datetime types by default** in the session when the client performs conversion. SQL Developer, JDBC, and other tools may apply their own formatting, so the screen does not necessarily follow the session NLS format in every display mode.

For queries/reports needing deterministic formatting, use `TO_CHAR` with an explicit format mask:

~~~sql
SELECT
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS local_time_text,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM') AS iso_like_text
FROM dual;
~~~

The double-quoted string **inside the format mask** (`"T"`) denotes a literal character `T`, not a SQL identifier. The output resembles ISO 8601, e.g., `2026-11-14T15:30:00.123+07:00`.

### 8.3. Do not rely on implicit conversion

Avoid writing:

~~~sql
-- Easily affected by the session's NLS_DATE_FORMAT.
SELECT *
FROM orders
WHERE created_at = '14/11/2026';
~~~

If `CREATED_AT` is `DATE`, Oracle may have to **implicitly convert the string to DATE** using the session's NLS settings. Two differently configured environments can yield different results or fail with `ORA-01861` or `ORA-01843`. Moreover, comparing with `=` against a `DATE` at 00:00 misses rows with non-midnight times.

Prefer datetime literals or conversion functions with explicit formats:

~~~sql
-- DATE literal: date 2026-11-14, time 00:00:00.
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';

-- If the input is a string in an agreed format:
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date
FROM dual;
~~~

`TO_DATE` is for string inputs; **never use `TO_DATE(SYSDATE, ...)` to "format" SYSDATE**. Because `SYSDATE` is already a `DATE`, passing it to `TO_DATE` triggers an implicit `DATE` → string conversion via NLS before re-parsing, causing errors or wrong values. To display, use `TO_CHAR`; to keep `DATE`, use it directly.

### 8.4. DATE literals have no time zone

~~~sql
SELECT
    DATE '2026-11-14' AS date_at_midnight,
    TIMESTAMP '2026-11-14 15:30:00' AS timestamp_without_tz,
    TIMESTAMP '2026-11-14 15:30:00 +07:00'
        AS timestamp_with_tz
FROM dual;
~~~

In Oracle, a `TIMESTAMP '... +07:00'` literal with an offset field is recognized as a time-zone-aware timestamp; for complete clarity when parsing strings in application paths, you can use `TO_TIMESTAMP_TZ`:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 15:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS ts_with_time_zone
FROM dual;
~~~

Note the distinction: `DATE '2026-11-14'` carries no `+07:00`; it is a **DATE value at midnight**, and any time zone meaning comes purely from external data contracts or explicit transformations applied afterward.

## 9. One instant, multiple representations: practicing with UTC

To learn how Oracle recognizes two different local clock times as **the same instant**, use fixed values rather than a moving `NOW`:

~~~sql
SELECT
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00'),
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS vietnam_time,
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')
            AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS utc_time
FROM dual;
~~~

Expected output:

~~~text
VIETNAM_TIME             UTC_TIME
-----------------------  -----------------------
2026-11-14 15:30:00 +07:00
                         2026-11-14 08:30:00 +00:00
~~~

With `FROM_TZ(timestamp_without_tz, timezone)`, Oracle **attaches a time zone context to a local timestamp**. Meanwhile, `AT TIME ZONE 'UTC'` on a value that already has a time zone **converts the representation of that same instant** to UTC. These are two distinct operations.

You can compare two time-zone-aware timestamps directly:

~~~sql
SELECT CASE
         WHEN FROM_TZ(
                TIMESTAMP '2026-11-14 15:30:00', '+07:00'
              ) =
              TO_TIMESTAMP_TZ(
                '2026-11-14 08:30:00 +00:00',
                'YYYY-MM-DD HH24:MI:SS TZH:TZM'
              )
         THEN 'SAME INSTANT'
         ELSE 'DIFFERENT INSTANT'
       END AS comparison_result
FROM dual;
~~~

For those two timestamps, the result is `SAME INSTANT`. Comparing the strings `'15:30'` and `'08:30'` looks different, yet once time zones are accounted for, they denote the same instant.

**Do not read `DBTIMEZONE` and blindly attach it to `SYSDATE`** without verifying that the server clock actually uses that time zone. `SYSDATE` has no time zone metadata, so you cannot infer a unique instant from an arbitrary `DATE` value without an explicit data convention.

## 10. Using the four functions as column default values

Choose default functions based on data storage requirements, not just the format you want to see on screen.

### 10.1. Choosing the right column definition

| Requirement | Reference column / default | What must be clarified |
| --- | --- | --- |
| Legacy system tracking datetimes via server clock, to the second | `DATE DEFAULT SYSDATE` | Implicit time zone of the `DATE` values must be documented |
| Current `DATE` in each session's configured time zone | `DATE DEFAULT CURRENT_DATE` | Pool must initialize session time zone consistently |
| Record creation instant with fractional seconds/offset | `TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP` | Define how clients serialize/display values |
| Record instant using the inserting session's time zone | `TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP` | Session time zone must be set/controlled |
| Local datetime without carrying an offset | `TIMESTAMP` with separate time zone contract | Time zone cannot be inferred from the stored value alone |
| Field needing display in reader's session time zone | `TIMESTAMP WITH LOCAL TIME ZONE` | Understand normalization to DB time zone and per-session display |

### 10.2. A lab table to observe all four defaults

In a practice schema:

~~~sql
CREATE TABLE time_functions_lab (
    id                NUMBER PRIMARY KEY,
    server_date       DATE DEFAULT SYSDATE NOT NULL,
    server_timestamp  TIMESTAMP WITH TIME ZONE
                          DEFAULT SYSTIMESTAMP NOT NULL,
    session_date      DATE DEFAULT CURRENT_DATE NOT NULL,
    session_timestamp TIMESTAMP WITH TIME ZONE
                          DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Set the session time zone for the first insert:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

INSERT INTO time_functions_lab (id) VALUES (1);
COMMIT;
~~~

Switch to another session time zone in **the same lab session**:

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

INSERT INTO time_functions_lab (id) VALUES (2);
COMMIT;
~~~

Inspect the results using explicit formats:

~~~sql
SELECT
    id,
    TO_CHAR(server_date, 'YYYY-MM-DD HH24:MI:SS') AS server_date_text,
    TO_CHAR(server_timestamp,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS server_ts_text,
    TO_CHAR(session_date, 'YYYY-MM-DD HH24:MI:SS') AS session_date_text,
    TO_CHAR(session_timestamp,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS session_ts_text
FROM time_functions_lab
ORDER BY id;
~~~

Key observations:

- `SERVER_DATE` and `SESSION_DATE` are **DATE**, retaining no offset.
- `SERVER_TIMESTAMP` and `SESSION_TIMESTAMP` retain **TIMESTAMP WITH TIME ZONE**.
- The session time zone at **INSERT** time governs the `CURRENT_DATE` and `CURRENT_TIMESTAMP` assigned to the row.
- A single row can contain different local clock representations from roughly the same creation moment; each default is evaluated when the statement executes.
- The two rows are inserted at different times, so **do not expect their UTC values to be equal**; this lab verifies time zone rules rather than attempting simultaneous inserts.

To clean up, drop only the lab table you just created:

~~~sql
DROP TABLE time_functions_lab;
~~~

`DROP TABLE` is DDL with real effect and commits per Oracle DDL rules. Never run it on shared or production schemas.

### 10.3. Should timestamps come from the database or the application?

There is no single answer for every system:

- **Database defaults** such as `SYSTIMESTAMP` ensure rows receive timestamps from a single database source even with diverse clients, though coordination is needed when applications supply their own values.
- **Application clocks** can be convenient for cross-service event tracing, yet depend on per-node clock synchronization and JDBC bind conversion rules.
- **Commit time** is not automatically equal to `DEFAULT SYSTIMESTAMP`: defaults are typically evaluated during insert, before or separate from commit time. If business rules require exact commit timestamps, a different modeling or event mechanism is needed.

For basic auditing, a database timestamp with a time-zone-aware column is straightforward; for distributed systems, distinguish **event time**, **ingestion time**, and **processing time** whenever their meanings differ.

## 11. Filtering data by date: whose "today" is it?

Suppose table `APP_EVENTS` has `CREATED_AT` as `TIMESTAMP WITH TIME ZONE`. If the requirement is "all events on November 14 in Vietnam time," you need day boundaries **in Vietnam's zone/offset**, not simply `TRUNC(SYSDATE)` if the server uses another zone.

For a fixed day in `+07:00`:

~~~sql
SELECT *
FROM app_events
WHERE created_at >= FROM_TZ(
          TIMESTAMP '2026-11-14 00:00:00', '+07:00'
      )
  AND created_at <  FROM_TZ(
          TIMESTAMP '2026-11-15 00:00:00', '+07:00'
      );
~~~

Both `FROM_TZ` expressions specify **00:00 Vietnam time** and **00:00 the next day**, with explicit offsets. If the table uses a time zone region with DST, compute both day boundaries using **the region and the specific date**, because a local calendar day can span 23 or 25 hours in UTC.

### 11.1. Why use a half-open interval?

The condition:

~~~sql
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
~~~

has clear advantages:

- Captures every moment within the day, including fractional seconds.
- Avoids guessing whether the "last second of the day" is `23:59:59` or `23:59:59.999999`.
- Avoids applying `TRUNC(created_at)` to every row in the predicate when unnecessary, which is generally friendlier to index range scans.

Both bind parameters must share the same **time zone and data type contract** as the column. Comparing a `DATE` column storing local wall-clock times without an offset against a TSTZ value can trigger hard-to-control implicit conversions; first establish the business time zone of those `DATE` values.

### 11.2. "Today in the session" vs. "last 24 hours"

Two distinct requirements:

- **Today in session:** from 00:00 of the current calendar day in the user's time zone until 00:00 the next day.
- **Last 24 hours:** a rolling 24-hour span measured backward from the current instant.

In regions with daylight saving time, a calendar day can last 23 or 25 hours, so applying the same "minus 1 day" formula to both cases can fail. Clarify the business rule first, then choose the functions, time zone, and column type.

## 12. SQL, JDBC, and multi-time-zone applications

### 12.1. Distinguish connection time zone from user time zone

An application with servers in UTC and users in many regions can set each database session's time zone either to UTC or to the user's time zone. With a connection pool, multiple requests reuse the same physical session. In that setup:

1. If the application standardizes on **database sessions always in UTC**, initialize/verify the time zone on every connection per pool policy.
2. If sessions track the user's time zone, you must reset it per request/user and prevent time zone leakage across requests.
3. If you only need local time display, you can usually **store instants with time zone** in the database and convert in the presentation layer to the user's time zone, rather than switching session time zone for every query.

Example setting session time zone:

~~~sql
ALTER SESSION SET TIME_ZONE = '+00:00';

SELECT SESSIONTIMEZONE FROM dual;
~~~

Verify `SESSIONTIMEZONE` before relying on `CURRENT_DATE`/`CURRENT_TIMESTAMP`. Its value may be an offset or a region name depending on the session and how it was configured.

### 12.2. Java time API and Oracle mapping

Corresponding programming model:

| Java type | Meaning | Mapping caveats |
| --- | --- | --- |
| `LocalDate` | Calendar date without time or offset | Suitable for birth dates or holidays when no instant is needed |
| `LocalDateTime` | Local date + time without time zone | Does not identify an instant across multiple time zones |
| `Instant` | Absolute point on the UTC timeline | Requires explicit driver/mapping handling when persisting to SQL |
| `OffsetDateTime` | Local date-time with UTC offset | Closely matches offset-based `TIMESTAMP WITH TIME ZONE` |
| `ZonedDateTime` | Local date-time with time zone region and its rules | Verify whether the driver/ORM preserves full region or only offset |

In modern Java/JDBC, `PreparedStatement` with appropriate mappings passes strongly typed datetime values cleanly. Illustrative example with a driver supporting JDBC 4.2:

~~~java
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime capturedAt = OffsetDateTime.now(ZoneOffset.UTC);

String sql = """
    INSERT INTO app_events (event_id, created_at)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);
    ps.setObject(2, capturedAt);
    ps.executeUpdate();
}
~~~

This example assumes `CREATED_AT` is `TIMESTAMP WITH TIME ZONE` and the Oracle driver in use **supports `OffsetDateTime` mapping as expected**. Test round-trip behavior on your deployed driver/ORM version. Do not implicitly convert `java.sql.Timestamp` or `LocalDateTime` to an instant using the JVM default time zone without an explicit contract.

### 12.3. Avoid storing timestamps as strings

A `VARCHAR2(50)` column holding `2026-11-14T15:30:00+07:00` looks informative, yet the database treats it as **plain text**, making format enforcement, constraints, chronological comparisons, and time zone conversions difficult. For event timestamps, use an appropriate Oracle datetime type, and reserve ISO 8601 strings for API interchange boundaries.

If serializing to JSON:

~~~sql
SELECT
    TO_CHAR(
        created_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM'
    ) AS created_at_utc_text
FROM app_events;
~~~

This string is an **API serialization format**, not a model for internal database storage. When standard ISO 8601 formatting is required across environments, check fractional precision, offset formatting, and `Z` conventions in the specific API contract.

## 13. Common errors and root-cause identification

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `SYSDATE` differs from `CURRENT_DATE` by hours | Server clock time zone differs from session time zone | Format both explicitly; check `SESSIONTIMEZONE` and server config |
| `SYSTIMESTAMP` differs from `CURRENT_TIMESTAMP` in hour/offset | The two functions use server vs. session time zones | Convert both to UTC or the same zone to compare instants |
| `SYSDATE` shows only date, no time | NLS/client format hides the time portion | `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| `DATE` value does not show `.123` or `+07:00` | `DATE` stores neither fractional seconds nor time zone | Use `TIMESTAMP WITH TIME ZONE` if required |
| `ORA-01861` when parsing a date string | String does not match format mask or relies on NLS | Use `TO_DATE`/`TO_TIMESTAMP_TZ` with explicit mask, or typed binds |
| `ORA-01843` | Invalid month value or incompatible language format | Check input, `NLS_DATE_LANGUAGE`, format, and calendar |
| "Today" returns different row count than expected | Mixing server day and user day, or `DATE` column stores times in another zone | Establish time zone for both bounds and column; align to same instant |
| JDBC and SQL*Plus display differently | Different client formats or time zone mappings | Check NLS/session/JVM/driver and inspect true values via explicit format |
| One session has right time, another is wrong | Time zone/NLS altered per session | Inspect `SESSIONTIMEZONE` and NLS in each session; configure pool |
| After host migration, legacy `DATE` times are hard to compare | `DATE` stored local wall-clock time without time zone | Determine historical time zone from metadata/ops before converting |
| Inconsistent data on DST transition days | Used fixed offset instead of region, or ambiguous local time | Inspect time zone region, specific date, offset, and DST rules |

### 13.1. Minimal diagnostic query set

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    DBTIMEZONE AS db_tz,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS sys_date,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS current_date_value,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS sys_ts,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS current_ts
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;
~~~

Run this first before altering `TIME_ZONE` or NLS formats. It reveals both **explicitly formatted values** and session context, preventing misdiagnosis caused by tool rendering.

### 13.2. Step-by-step reasoning workflow for time bugs

1. **Identify the business question:** do you need an absolute instant, a user calendar date, or local wall-clock time at a location?
2. **Check the real column type:** `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, or `TIMESTAMP WITH LOCAL TIME ZONE`.
3. **Identify the value source:** `SYSDATE`, `CURRENT_DATE`, application clock, file import, or migration.
4. **Check time zones:** server host, session, whether values carry offsets/regions, and whether DST applies.
5. **Separate data from display:** use explicit `TO_CHAR` formats or typed driver access.
6. **Compare the same instant:** convert time-zone-aware data to UTC or a common region before comparing; never compare raw local time strings alone.
7. **Apply the minimal fix:** update the contract, format, or session initialization in the right place and test boundary cases around midnight/day transitions.

## 14. Comprehensive hands-on lab

This lab only requires `SELECT FROM DUAL` and standard `ALTER SESSION` privileges, except for the optional table exercise. Use **a fresh SQL session** so you do not alter time zone/NLS settings of any shared application.

### Step 1 — Inspect all four functions in one query

~~~sql
SELECT
    TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS sysdate_value,
    TO_CHAR(SYSTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS systimestamp_value,
    TO_CHAR(CURRENT_DATE,
            'YYYY-MM-DD HH24:MI:SS') AS current_date_value,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS current_timestamp_value
FROM dual;
~~~

Note: which pair tracks the server, which pair tracks the session, and which pair includes a time zone?

### Step 2 — Record current time zone and NLS settings

~~~sql
SELECT SESSIONTIMEZONE, DBTIMEZONE FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_TIMESTAMP_TZ_FORMAT');
~~~

Record `SESSIONTIMEZONE` so you can restore it if needed. Do not assume it equals `DBTIMEZONE`.

### Step 3 — Switch session time zone to `+07:00`

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT
    SESSIONTIMEZONE AS tz,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now
FROM dual;
~~~

Explain why `CURRENT_DATE` displays `+07:00` time while `SYSDATE` typically continues reflecting the server. The server does not need to be in UTC to run this experiment.

### Step 4 — Switch session time zone to `-05:00`

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT
    SESSIONTIMEZONE AS tz,
    TO_CHAR(SYSTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS server_ts,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS session_ts
FROM dual;
~~~

Observe the offset in `CURRENT_TIMESTAMP` and the server time in `SYSTIMESTAMP`. Also apply `AT TIME ZONE 'UTC'` to each timestamp to compare their representations in the same time zone.

### Step 5 — Test NLS formatting

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

SELECT SYSDATE, CURRENT_DATE FROM dual;

SELECT
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS explicit_server,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS explicit_session
FROM dual;
~~~

If your tool renders according to `NLS_DATE_FORMAT`, the first query may display only the date; the second still displays the full time per your format mask. The `DATE` values lost no time after `ALTER SESSION`.

### Step 6 — Compare two values representing the same instant

~~~sql
SELECT
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')
            AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS converted_utc,
    TO_CHAR(
        TO_TIMESTAMP_TZ(
            '2026-11-14 08:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS direct_utc
FROM dual;
~~~

Both returned values must show the same UTC representation of a single instant when executed with the datetime types shown.

### Step 7 — Restore session environment or disconnect

Restore the session time zone and NLS formats recorded in Step 2, or close the lab session. Never use a shared connection for exercises running `ALTER SESSION`.

## 15. Misconceptions to avoid

**"`SYSDATE` only has a date."** False. Oracle `DATE` retains time down to the second; a client format may simply hide the time.

**"`CURRENT_DATE` only has a date."** False. It is a `DATE` containing both date and time in the session time zone.

**"`SYSTIMESTAMP` and `CURRENT_TIMESTAMP` must always produce the same display string."** False. They can represent the same instant in different time zones, resulting in different local clocks and offsets.

**"`DBTIMEZONE` is always the database server's OS time zone."** False. `DBTIMEZONE` is a database property, primarily relevant to `TIMESTAMP WITH LOCAL TIME ZONE`.

**"Changing `NLS_DATE_FORMAT` changes stored dates/times."** False. NLS formats change default conversion/display; datetime values retain their original data.

**"`DATE` automatically knows the user's time zone."** False. `DATE` stores neither offset nor region. Use an explicit convention or a time-zone-aware type for instants.

**"`FROM_TZ` and `AT TIME ZONE` do the same thing."** False. `FROM_TZ` attaches a time zone to a zone-less local timestamp; `AT TIME ZONE` converts an already-zoned instant to its representation in a target zone.

**"Use `TO_DATE(SYSDATE, ...)` to print in a format."** False. `SYSDATE` is already a `DATE`; use `TO_CHAR` to format output.

**"00:00 each day is always exactly 24 hours apart."** False in regions observing daylight saving time. Regional calendar days and absolute 24-hour intervals can differ.

**"Using `CURRENT_TIMESTAMP` is enough; connection pools have no impact."** False. Session time zone can be affected by connection initialization or changes from prior requests; control it when using pools.

## 16. Self-check questions

1. Out of the four functions, which return `DATE` and which return `TIMESTAMP WITH TIME ZONE`?
2. Session is `+07:00`, server is UTC. When the server is at `2026-11-14 20:00:00`, what date can `CURRENT_DATE` be?
3. Why can `SYSDATE` and `CURRENT_DATE` fall on different calendar dates even when queried within the same second?
4. When you need milliseconds and a UTC offset, choose `SYSDATE` or `SYSTIMESTAMP`?
5. Are `SESSIONTIMEZONE` and `DBTIMEZONE` always equal?
6. Does `ALTER SESSION SET TIME_ZONE = '+07:00'` change the server's OS clock?
7. Does `ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY'` delete the time portion of a `DATE` column?
8. Why can `TO_DATE('14/11/2026')` be unsafe without a format mask?
9. Do `FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')` and `2026-11-14 08:30:00 +00:00` represent the same instant?
10. Why can't you reliably infer the time zone of a `DATE` stored a year ago simply by reading `DBTIMEZONE` today?
11. An audit table must record instants and fractional seconds for many users: why is `TIMESTAMP WITH TIME ZONE` clearer than `DATE`?
12. A user asks for "today's events" in New York. Why shouldn't you default to `TRUNC(SYSDATE)` as the day boundary?
13. Why is a calendar day in a DST region sometimes 23 or 25 hours long?
14. An application sets `TIME_ZONE` per user on a connection pool: what is the risk if it does not reset on connection return?
15. Does `DEFAULT SYSTIMESTAMP` on a table always equal the `COMMIT` time?

**Suggested answers:**

1. `SYSDATE`/`CURRENT_DATE` return `DATE`; `SYSTIMESTAMP`/`CURRENT_TIMESTAMP` return `TIMESTAMP WITH TIME ZONE`.
2. In `+07:00`, it is `2026-11-15 03:00:00`.
3. They interpret time using different contexts: server clock vs. session time zone.
4. `SYSTIMESTAMP` or `CURRENT_TIMESTAMP`, formatted with `TO_CHAR(..., '...FF3 TZH:TZM')`.
5. No.
6. No, it only changes the session's time zone.
7. No, it only changes default display/implicit conversion.
8. Oracle may use the session's NLS format and parse wrongly or raise an error.
9. Yes, the same instant.
10. `DATE` stores no offset; `DBTIMEZONE` does not automatically describe the original time zone of all stored data.
11. It preserves time zone info and fractional seconds for unambiguous instant comparisons.
12. The server's calendar date can differ from the user's date; bounds must be built in the business time zone.
13. The local clock jumps forward or backward due to DST.
14. The next session can inherit the previous user's time zone, skewing `CURRENT_DATE`/`CURRENT_TIMESTAMP`.
15. No, defaults are typically evaluated at insert time, not as a guaranteed commit timestamp.

## Oracle Reference Documentation

- [Oracle SQL Language Reference — SYSDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYSDATE.html): `DATE` type and server-side time source.
- [Oracle SQL Language Reference — SYSTIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYSTIMESTAMP.html): `TIMESTAMP WITH TIME ZONE` type and server time.
- [Oracle SQL Language Reference — CURRENT_DATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CURRENT_DATE.html): `DATE` value in the session time zone.
- [Oracle SQL Language Reference — CURRENT_TIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CURRENT_TIMESTAMP.html): timestamp in the session time zone.
- [Oracle SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, and `TIMESTAMP WITH LOCAL TIME ZONE`.
- [Oracle SQL Language Reference — FROM_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FROM_TZ.html): attaching a time zone to a local timestamp.
- [Oracle SQL Language Reference — SYS_EXTRACT_UTC](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_EXTRACT_UTC.html): extracting UTC values.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): NLS datetime formats, time zones, and daylight saving time considerations.
