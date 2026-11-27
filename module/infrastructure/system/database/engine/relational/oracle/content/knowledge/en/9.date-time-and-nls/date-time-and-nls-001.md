# NLS_DATABASE_PARAMETERS, NLS_INSTANCE_PARAMETERS, and NLS_SESSION_PARAMETERS

In Oracle Database, the same `DATE` column may be displayed as `14/11/2026` by tool A, while tool B displays it as `2026-11-14 09:30:00`. A string-to-date conversion statement may succeed on a developer machine but fail with `ORA-01861` when deployed. To find the root cause, you must distinguish **database-level NLS configuration**, **instance-level NLS configuration**, and **the NLS values actually in effect in the SQL session**.

Three data dictionary views—`NLS_DATABASE_PARAMETERS`, `NLS_INSTANCE_PARAMETERS`, and `NLS_SESSION_PARAMETERS`—help answer three different questions. This lesson shows you how to query, compare, and interpret them in the context of **date/time and National Language Support (NLS)**, and then apply that understanding to SQL*Plus, SQL Developer, JDBC, and applications using connection pools.

> **Key takeaway:** When a running SQL statement has an issue with date, number, or language formatting, inspect `NLS_SESSION_PARAMETERS` for **the exact session running that SQL**. Database or instance values are only part of the context; they do not guarantee that all clients use the same format.

## 1. At what levels does NLS exist?

**NLS (National Language Support)** is Oracle's configuration system for supporting languages, territories, presentation and interpretation of dates/times, numbers, characters, and certain sorting/comparison rules. NLS is not a separate data type.

~~~mermaid
flowchart TD
    A["Database: NLS defaults and characteristics"] --> B["Instance: instance-level NLS configuration"]
    B --> C["Session created when client connects"]
    D["Client/driver: SQL*Plus, SQL Developer, JDBC..."] --> C
    E["ALTER SESSION SET NLS_..."] --> C
    C --> F["SQL in session: TO_CHAR, TO_DATE, implicit conversion..."]
    G["Structured storage of DATE/TIMESTAMP/NUMBER"] --> F
~~~

The diagram illustrates **sources of influence**, not a sequential copy of every value from database → instance → session. Some session values may be established at logon, initialized by the client/driver, or explicitly modified with `ALTER SESSION`. Certain database-level properties, notably the character set, are not settings that can be arbitrarily changed within a session.

| View | Scope to understand | When to use? |
|---|---|---|
| `NLS_DATABASE_PARAMETERS` | Database-level NLS information/configuration, including persistent properties such as character set | Identify the NLS configuration of the connected database; understand defaults and character storage capabilities |
| `NLS_INSTANCE_PARAMETERS` | NLS settings recorded by Oracle at the instance level, from corresponding initialization/instance control configuration | Compare instance configuration with database-level and session-level values |
| `NLS_SESSION_PARAMETERS` | NLS values currently in effect **in the current session** | Diagnose date formats, month languages, numbers, and string interpretation in running SQL |

All three generally provide two easy-to-use columns: `PARAMETER` and `VALUE`. **Do not treat the three views as three synchronized copies**: the parameter lists may differ, and the same parameter name may hold different values depending on scope.

## 2. Inspecting the three views accurately in a connection

The following `SELECT` statements are read-only observations and do not modify data or configuration.

### 2.1 Inspecting database configuration

~~~sql
SELECT parameter, value
FROM nls_database_parameters
ORDER BY parameter;
~~~

Rows with special significance:

- `NLS_CHARACTERSET`: the primary character set of the database, used for types such as `VARCHAR2` and `CLOB`.
- `NLS_NCHAR_CHARACTERSET`: the national character set, used for `NCHAR`, `NVARCHAR2`, and `NCLOB`.
- Other NLS rows describe baseline/default values recorded by the database; they **do not by themselves prove** that application sessions currently use the same values.

Example **illustrative** filtered output:

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
NLS_LANGUAGE            AMERICAN
NLS_TERRITORY           AMERICA
~~~

This example is not a fixed result across every Oracle deployment. To conclude whether an actual database supports storing Vietnamese in standard character types, you must inspect the exact `NLS_CHARACTERSET` of the target system/PDB in use.

### 2.2 Inspecting instance configuration

~~~sql
SELECT parameter, value
FROM nls_instance_parameters
ORDER BY parameter;
~~~

This view reflects NLS information on **the instance serving the session**. Parameters such as `NLS_LANGUAGE` or `NLS_TERRITORY` can reflect instance-level configuration and may differ from database-level values.

Oracle RAC can have multiple instances serving the same database. If you are investigating differences across nodes, record the instance/host for each connection; a single read of `NLS_INSTANCE_PARAMETERS` from node A does not automatically represent every node.

### 2.3 Inspecting session configuration

~~~sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
~~~

This is the primary inspection point for **a specific SQL statement**. Notable examples to check:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_CALENDAR',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
~~~

Note that the `VALUE` column in these views is a **string describing the parameter setting**, not a stored copy of date/time values in application tables. Changing `NLS_DATE_FORMAT` does not automatically modify any row in a `DATE` column.

### 2.4 Capturing the context of the measurement

Before comparing results sent by two people from two machines, identify which database/container/instance the session is connected to:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

If you have privileges to query dynamic performance views:

~~~sql
SELECT instance_name, host_name, version
FROM v$instance;

SELECT name, cdb, open_mode
FROM v$database;
~~~

In a CDB/PDB architecture, the results of certain views and metadata visibility depend on **the current container**. When comparing, include the PDB name, service, and instance. Do not read values from `CDB$ROOT` and assume every PDB or every application shares the same configuration state.

## 3. Placing all three sources in one table for comparison

You can compare NLS parameters with matching names using a simple pivot query:

~~~sql
WITH nls_values AS (
    SELECT 'DATABASE' AS scope_name, parameter, value
    FROM nls_database_parameters
    UNION ALL
    SELECT 'INSTANCE' AS scope_name, parameter, value
    FROM nls_instance_parameters
    UNION ALL
    SELECT 'SESSION' AS scope_name, parameter, value
    FROM nls_session_parameters
)
SELECT parameter,
       MAX(CASE WHEN scope_name = 'DATABASE' THEN value END)
           AS database_value,
       MAX(CASE WHEN scope_name = 'INSTANCE' THEN value END)
           AS instance_value,
       MAX(CASE WHEN scope_name = 'SESSION' THEN value END)
           AS session_value
FROM nls_values
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_TIMESTAMP_FORMAT'
)
GROUP BY parameter
ORDER BY parameter;
~~~

Example **hypothetical result to practice interpreting meaning**, not mandatory defaults:

| Parameter | Database | Instance | Session |
|---|---|---|---|
| `NLS_LANGUAGE` | `AMERICAN` | `AMERICAN` | `AMERICAN` |
| `NLS_TERRITORY` | `AMERICA` | `AMERICA` | `VIETNAM` |
| `NLS_DATE_FORMAT` | `DD-MON-RR` | `DD-MON-RR` | `YYYY-MM-DD HH24:MI:SS` |
| `NLS_NUMERIC_CHARACTERS` | `.,` | `.,` | `,.` |

If a real query produces a `NULL` cell in a column, check **whether that parameter even appears in the corresponding view**; do not assume `NULL` is an active NLS value. The three views do not necessarily contain the exact same set of parameters—for instance, database-level character set entries do not need an equivalent copy in the session view.

**Correct interpretation of the example:** the current session uses `NLS_DATE_FORMAT = YYYY-MM-DD HH24:MI:SS`, even though database/instance hold another value. When Oracle has to convert a `DATE` to a string using the **session default**, the result can follow this format. Querying database/instance is still useful to explain why sessions might start out differently, but must never replace checking the failing session's values.

### Why can the values differ?

Several causes:

1. The database was created with specific NLS characteristics.
2. The instance was started with NLS parameters in its corresponding configuration.
3. The client/driver initializes the session and may supply its own language/territory/format settings.
4. A logon trigger, SQL tool, or application may execute `ALTER SESSION`.
5. A connection pool keeps sessions alive across multiple requests; session state can be affected by prior operations if not properly managed.

Do not rely solely on the final three values to declare with certainty **who** changed a parameter and **when**. The three views are snapshots of state, not an audit history of every `ALTER SESSION` call.

## 4. NLS_DATE_FORMAT: date formatting is not the nature of DATE data

In Oracle, the `DATE` data type stores **year, month, day, hour, minute, and second**, but does not store a time zone and has no fractional seconds. Values in a `DATE` column are not stored as strings like `DD/MM/YYYY` or `YYYY-MM-DD`.

`NLS_DATE_FORMAT` governs certain rules for **default conversion between DATE and strings**, especially when displaying date values through a client or performing implicit conversion. It does not turn a `DATE` into a `VARCHAR2`.

### 4.1 Observing before and after ALTER SESSION

In **a dedicated practice session**:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

Set the format explicitly:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

For example, in a tool that displays according to session format, the `ORDER_DATE` column may show `14/11/2026`. Change it again:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

The value may show `2026-11-14 00:00:00`. **The DATE value did not change**; the expression `DATE '2026-11-14'` specifies that date with a midnight time component. How a UI renders it may also be affected by display settings specific to certain tools.

To inspect the exact output string independently of `NLS_DATE_FORMAT`, use `TO_CHAR` with a format model:

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD HH24:MI:SS'
       ) AS stable_date_text
FROM dual;
~~~

The result is `2026-11-14 00:00:00` according to the specified format. `TO_CHAR` returns **VARCHAR2**, which is suitable when you need fixed text output for reports. In application code, keep data as date/time types for as long as possible and format only at the presentation boundary.

### 4.2 Why is implicit conversion error-prone?

Example of a SQL statement that depends on session configuration:

~~~sql
-- Oracle may have to implicitly convert the string into a DATE:
SELECT *
FROM orders
WHERE created_at >= '14/11/2026';
~~~

Assuming `CREATED_AT` is of type `DATE`, the string `'14/11/2026'` must be interpreted as a date. A session using `NLS_DATE_FORMAT = 'DD/MM/YYYY'` might accept it, whereas a session using a different format may raise errors such as `ORA-01861` or `ORA-01843`.

Specify data types/formats explicitly:

~~~sql
-- DATE literal uses a fixed ISO format:
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14';

-- When input data is a string in an agreed format:
SELECT TO_DATE(
           '14/11/2026 09:30:00',
           'DD/MM/YYYY HH24:MI:SS'
       ) AS parsed_date
FROM dual;
~~~

`DATE 'YYYY-MM-DD'` does not depend on the session's `NLS_DATE_FORMAT`. `TO_DATE` with an explicit format model eliminates ambiguity. For date values coming from Java/JDBC, an even better approach is to **bind parameters using date/time types** and avoid concatenating strings into SQL.

### 4.3 DATE values with a time component should use half-open intervals

When querying all records for November 14, 2026 in a `DATE` column that includes hours/minutes/seconds:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Filtering from the start of the day to **before the start of the next day** does not depend on display format. Comparing `created_at = DATE '2026-11-14'` only matches values at exactly 00:00:00, which does not represent every timestamp within that day.

## 5. NLS_DATE_LANGUAGE and NLS_TERRITORY: both are NLS, but with different effects

### 5.1 NLS_DATE_LANGUAGE controls month names and day names

`NLS_DATE_LANGUAGE` governs the language used to display or parse month/day names in format models containing `MON`, `MONTH`, `DAY`, and so on. It **does not change the stored month/year** in a `DATE` value.

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS month_american,
       TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=FRENCH'
       ) AS month_french
FROM dual;
~~~

The expected output is the English and French month names respectively (for instance, `November` and `Novembre`). The third argument of `TO_CHAR` sets the language **for that single conversion**, without needing to alter the entire session.

Similarly, when the input is a string containing a month name:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS parsed_date
FROM dual;
~~~

If you omit the language argument and the session uses a different language, the same month-name string may fail to be recognized as intended. For system-to-system APIs, numeric month formats (`MM`) are usually far less language-dependent than month names (`MON`/`MONTH`).

### 5.2 NLS_TERRITORY influences regional defaults

`NLS_TERRITORY` represents regional conventions and can influence the defaults of several parameters such as date format and numeric characters, if they have not been set individually. `NLS_LANGUAGE` primarily concerns language; `NLS_TERRITORY` concerns regional conventions. You should not assume that seeing `NLS_TERRITORY = VIETNAM` guarantees all application dates will display in one fixed pattern.

You can observe them together:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

When `NLS_DATE_FORMAT` has already been set directly via `ALTER SESSION` or by the client, read that value directly instead of inferring it backward from `NLS_TERRITORY`. Several NLS settings are related when defaults are established, yet **the current value** in the session remains the most important evidence for a running query.

## 6. NLS_TIMESTAMP_FORMAT and NLS_TIMESTAMP_TZ_FORMAT

Oracle distinguishes several temporal data types:

| Data type | What does it store? | Relevant default formatting NLS |
|---|---|---|
| `DATE` | Date + hour/minute/second, **no** fractional seconds or time zone | `NLS_DATE_FORMAT` |
| `TIMESTAMP` | Date and time with fractional seconds, **no** time zone stored | `NLS_TIMESTAMP_FORMAT` |
| `TIMESTAMP WITH TIME ZONE` | Timestamp along with time zone/offset information per data type rules | `NLS_TIMESTAMP_TZ_FORMAT` |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Value normalized to the database context and displayed in the session time zone; does not preserve original time zone like TSTZ | Appropriate timestamp formats together with session time zone configuration |

Inspect current formats:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT'
)
ORDER BY parameter;
~~~

In a practice session:

~~~sql
ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3';

ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM';

SELECT TIMESTAMP '2026-11-14 09:30:15.123' AS local_timestamp,
       CURRENT_TIMESTAMP AS current_timestamp_with_zone
FROM dual;
~~~

These `ALTER SESSION` statements only change **the default presentation/conversion patterns** in the session; they do not add a time zone to a `TIMESTAMP` column that has no time zone. When formatting directly, you can use:

~~~sql
SELECT TO_CHAR(
           TIMESTAMP '2026-11-14 09:30:15.123',
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS stable_timestamp_text
FROM dual;
~~~

`FF3` represents three fractional second digits in the format model, unlike `SS` which represents whole seconds only.

### 6.1 Session time zone is not NLS_DATE_FORMAT

~~~sql
SELECT SESSIONTIMEZONE,
       DBTIMEZONE,
       CURRENT_DATE,
       CURRENT_TIMESTAMP,
       SYSTIMESTAMP
FROM dual;
~~~

- `SESSIONTIMEZONE`: the time zone of the session.
- `DBTIMEZONE`: the time zone configured for the database; it does not represent all sessions.
- `CURRENT_DATE`: the current date and time in the session time zone, returned as `DATE`.
- `CURRENT_TIMESTAMP`: the current point in time in the session time zone, with time zone.
- `SYSTIMESTAMP`: timestamp obtained from the database server operating system, with its corresponding time zone.

In a practice session, you can change the time zone separately:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE, CURRENT_TIMESTAMP
FROM dual;
~~~

**`TIME_ZONE` is not `NLS_DATE_FORMAT`.** Changing a date pattern only alters how strings are formatted/parsed; changing the session time zone can affect the values of session-dependent temporal expressions and the display of time-zone-aware types. If two machines have an hour offset mismatch, you must check **the column type, session time zone, server time zone, and application conversion logic**, not just the three NLS views.

## 7. NLS_NUMERIC_CHARACTERS: another example of same value, different string

Although this lesson focuses on date/time, comparing the three views becomes clearer when looking at a numeric parameter as well. `NLS_NUMERIC_CHARACTERS` takes two characters: **the decimal separator first**, and **the thousands group separator second**.

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

In this format model, `D` is the decimal separator and `G` is the group separator according to NLS; the expected output is `1,234.5`.

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

The expected output is `1.234,5`. The `NUMBER` value `1234.5` **did not change** between the two runs; only the displayed string changed. String-to-number conversion errors such as `ORA-01722` can be related to separators incompatible with the session or invalid input data.

Just like with date/time, the durable solution is to **pass NUMBER values as NUMBER/bind variables**, and only use `TO_CHAR` with an explicit format when generating text. Do not concatenate UI-formatted numeric strings into SQL statements as if they were numeric literals.

## 8. ALTER SESSION and its effect on the three views

In a connection with privileges to execute `ALTER SESSION`, run:

~~~sql
-- Before changing
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;

-- Change in the current session
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';

-- Observe again
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;
~~~

Then check `NLS_DATABASE_PARAMETERS` and `NLS_INSTANCE_PARAMETERS`. Changing the session **does not modify database-level properties or instance parameters**; different values in those two views are not a synchronization bug.

| Action | What is directly affected? | Does it modify stored DATE data? |
|---|---|---|
| `ALTER SESSION SET NLS_DATE_FORMAT = ...` | Default format of the current session | No |
| `ALTER SESSION SET NLS_DATE_LANGUAGE = ...` | Date language of the current session | No |
| Tool creates a new connection with different NLS | NLS values of the new session | No |
| DBA changes instance-level NLS configuration via proper procedure | Instance-level configuration and sessions affected per Oracle mechanisms | Does not rewrite DATE values in tables |
| Changing database character set via a migration procedure | Character encoding/storage capability of the database | That is a separate migration project, not a way to change DATE formatting |

If you want to return to your lab environment's initial defaults, the simplest approach is to **close the test session and open a new session**, then re-check `NLS_SESSION_PARAMETERS`. There is no reason to run `ALTER SYSTEM` or modify Oracle configuration files just to test a report format.

### 8.1 Which SQL uses which session's NLS?

Suppose you open two tool windows, each with its own connection:

~~~text
Session A:
  NLS_DATE_FORMAT = DD/MM/YYYY
  SELECT DATE '2026-11-14' FROM DUAL;
  -> May display 14/11/2026

Session B:
  NLS_DATE_FORMAT = YYYY-MM-DD
  SELECT DATE '2026-11-14' FROM DUAL;
  -> May display 2026-11-14
~~~

There is no data contradiction. The two sessions have different default formats. When debugging, you must run the `NLS_SESSION_PARAMETERS` query **inside the exact failing connection**, rather than running it in another SQL window and assuming you inspected the right state.

## 9. Connection tools can alter what you see

### 9.1 SQL*Plus and NLS_LANG

In a **SQL*Plus connection using Oracle Client/OCI**, the `NLS_LANG` environment variable is one factor that can affect language/territory and the client's declared character set.

Example on a Linux/macOS shell using an appropriate UTF-8 environment:

~~~sh
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

In PowerShell:

~~~powershell
$env:NLS_LANG = 'AMERICAN_AMERICA.AL32UTF8'
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

These examples use placeholder host/user/service values, and SQL*Plus will prompt for a password. `NLS_LANG` is a **client-side setting relevant to the OCI path**, not a way to change the database's `NLS_CHARACTERSET`. The character set portion must reflect the encoding the client actually uses; do not copy it blindly from the database.

After logging in, **you still must query `NLS_SESSION_PARAMETERS`**, because values such as `NLS_DATE_FORMAT` may be explicitly reset. `NLS_LANG` is also not a guarantee of font support or input file encoding.

### 9.2 SQL Developer, SQLcl, and JDBC Thin applications

SQL Developer, SQLcl, and many Java applications connecting via JDBC Thin have client/session configuration mechanisms different from SQL*Plus over OCI. A Java `String` holds Unicode data; setting `NLS_LANG` in the shell is not the primary mechanism controlling character encoding in Java/JDBC Thin.

Settings that can affect what you observe:

- Date/time display format preferences in the GUI tool.
- SQL or session initialization options run when the connection is created.
- `ALTER SESSION` statements executed by a user, script, or application.
- The actual column data type, how the driver binds/reads values, and how the application serializes JSON.

For example, SQL Developer may display a `DATE` using its UI preference format, which does not look identical to a SQL*Plus terminal. Therefore, **never infer a session's `NLS_DATE_FORMAT` just by looking at a result cell**; query `NLS_SESSION_PARAMETERS` directly.

### 9.3 JDBC: bind typed date/time values instead of relying on NLS

Suppose a Java application needs to find orders from a given timestamp onward using `PreparedStatement`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;

LocalDateTime from = LocalDateTime.of(2026, 11, 14, 9, 30);

String sql = """
    SELECT order_id, created_at
    FROM orders
    WHERE created_at >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf(from));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process values via typed API.
        }
    }
}
~~~

This snippet assumes an existing `Connection connection` and an `ORDERS` table in the appropriate PDB/schema, with `CREATED_AT` of an appropriate date/time type. `Timestamp.valueOf(LocalDateTime)` creates a timestamp **without a time zone attached**; if the business logic requires an absolute instant across multiple time zones, you must choose the corresponding column type and time-zone-aware API. The goal here is to avoid building strings like `'14/11/2026 09:30'` and letting Oracle guess the format.

### 9.4 Connection pools and leftover session state

Suppose request A borrows a connection:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
~~~

and then returns the connection to the pool. Request B borrows that same connection, runs a SQL statement that relies on implicit conversion, and gets unexpected results. If the pool does not reset NLS session state, request A's `ALTER SESSION` can affect request B.

A durable design approach is:

1. Keep SQL independent of default formats by using typed binds and explicit format models wherever strings are needed.
2. If the application must enforce fixed NLS settings, set them consistently on connection initialization/borrow according to the pool/driver mechanism in use.
3. Do not let individual requests alter shared defaults and return the connection to the pool without controlled state reset.
4. When reproducing a bug, capture session NLS **on the exact connection** executing the business query.

## 10. CDB/PDB considerations: read the right scope

In Oracle multitenant, applications connect to a **PDB service**. The same CDB can hold multiple PDBs created or plugged in from different sources. When querying NLS views, record the context clearly:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','CON_ID') AS con_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;
~~~

With an account that has privileges:

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

**Do not equate the CDB root with an application PDB.** View scopes, parameters configurable at the PDB level, and client behavior depend on the Oracle version and configuration. If you need to compare multiple PDBs, observe **each permitted connection/PDB individually** and record its source, rather than merging outputs and assuming all PDBs share the same semantics.

A distinction to keep clear:

- `NLS_CHARACTERSET` and `NLS_NCHAR_CHARACTERSET` describe character storage at the corresponding database/container level, **not the DATE display format of individual sessions**.
- `NLS_DATE_FORMAT` or `NLS_DATE_LANGUAGE` can differ between sessions within the same PDB.
- `NLS_INSTANCE_PARAMETERS` reflects the instance level; in multi-instance RAC, you must know which instance is serving the connection.

Therefore, a three-view comparison table is only meaningful once you know **where each view was queried**.

## 11. Common pitfalls when interpreting NLS

| Symptom | Possible cause | First check |
|---|---|---|
| Same `DATE`, different display in SQL*Plus and GUI | Different session NLS, or client-specific display formatting | Query `NLS_SESSION_PARAMETERS` in each connection; use `TO_CHAR` with a fixed format |
| `ORA-01861: literal does not match format string` | Date string does not match format during parsing | Check if the expression uses implicit conversion; use DATE literal, bind, or `TO_DATE` with format |
| `ORA-01843: not a valid month` | Month data or month name incompatible with language/format | Check `NLS_DATE_LANGUAGE`, `NLS_DATE_FORMAT`, and the source string |
| Works in dev but fails in prod | Different default session NLS or different input data | Compare session NLS alongside the SQL, binds, and actual data |
| `ORA-01722: invalid number` | Numeric string cannot be converted to NUMBER in context | Check `NLS_NUMERIC_CHARACTERS`, data type, and explicit conversion |
| `SYSDATE` displays without time | `NLS_DATE_FORMAT` does not include `HH24:MI:SS` | Use `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| `CURRENT_TIMESTAMP` off by expected hours | Session time zone, server time zone, or column/application mapping | Check `SESSIONTIMEZONE`, `DBTIMEZONE`, and data types, not just NLS |
| `NLS_DATABASE_PARAMETERS` and `NLS_SESSION_PARAMETERS` differ | Session was configured differently by client or `ALTER SESSION` | Check session values; do not treat differences automatically as errors |
| Cannot query an NLS view | Missing metadata privileges or wrong object scope | Read the full Oracle error, verify privileges and PDB |
| Ran `ALTER SESSION` and another SQL window did not change | The windows have different sessions | Check each window's connection and its own session values |

A date/time error message can arise from **invalid source strings**, column types, time zones, or application APIs—not solely NLS. Investigate the actual SQL statement, bind values, and session context instead of blindly changing database-wide configuration.

### Diagnostic flowchart when date/time displays or parses incorrectly

~~~mermaid
flowchart TD
    A["Date/time displays or parses unexpectedly"] --> B{"Is the column DATE/TIMESTAMP or VARCHAR2?"}
    B -->|DATE/TIMESTAMP| C["Check NLS_SESSION_PARAMETERS and UI format"]
    B -->|VARCHAR2| D["Check string data and input format"]
    C --> E{"Only display differs?"}
    E -->|Yes| F["Use TO_CHAR with explicit format at output boundary"]
    E -->|No| G["Check binds, time zones, and comparison predicates"]
    D --> H["Use TO_DATE/TO_TIMESTAMP with format or fix input contract"]
    G --> I["Reproduce in the exact failing session"]
    F --> I
    H --> I
~~~

## 12. Hands-on exercise: observing differences across the three levels

Perform this on **two separate sessions** of a practice database/PDB. No system parameters need to be modified.

### Step 1 — Record initial configuration

In **session A**, run:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_instance_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;
~~~

Record the results in three columns, one per view. If they differ, accurately describe the **scope** of the difference; there is no need to determine a specific historical cause without an audit trail.

### Step 2 — Modify only session A

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT DATE '2026-11-14' AS d,
       TO_CHAR(DATE '2026-11-14','DD/MM/YYYY') AS forced_format
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';
~~~

Within the same session A, inspect the database/instance views once more and note your observations. Do not run `ALTER SYSTEM`.

### Step 3 — Open session B and compare

Open a **new connection** to the same service/PDB (not just another UI tab sharing a connection if the tool reuses sessions), then run:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';

SELECT DATE '2026-11-14' AS d
FROM dual;
~~~

Session B may use a different default than what session A set. Even if B happens to have the same format, that **does not prove** `ALTER SESSION` in A affected B; B may simply have been initialized with that format. You must compare context and before/after values.

### Step 4 — Change month-name language with an explicit format

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS english_month,
       TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=FRENCH'
       ) AS french_month
FROM dual;
~~~

Explain why **a single DATE value** can produce **two different language strings**, and why this does not require modifying data in the table.

### Step 5 — Test session-dependent number formatting

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
SELECT TO_CHAR(1234.5, 'FM9G999D0') AS number_text FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
SELECT TO_CHAR(1234.5, 'FM9G999D0') AS number_text FROM dual;
~~~

Observe the output strings and reiterate that the `NUMBER` value itself does not change.

### Step 6 — Explain application design choices

A Java API receives the date `14/11/2026 09:30` and stores `CREATED_AT` as a `DATE`. Explain:

1. Why should you not concatenate strings into `WHERE created_at >= '14/11/2026 09:30'`?
2. How should you bind date/time parameters or use an explicit format model?
3. If you only want to display `YYYY-MM-DD` for the frontend, where should `TO_CHAR` or the presentation layer be applied?
4. If one request ran `ALTER SESSION` inside a connection pool, what might a subsequent request experience?
5. Out of the three views, which one shows the format actually in effect for **the connection executing the failing request**?

## 13. Self-check questions

1. How does `NLS_DATABASE_PARAMETERS` differ in scope from `NLS_INSTANCE_PARAMETERS` and `NLS_SESSION_PARAMETERS`?
2. Why should differences between database/instance/session not be treated as proof that the database stores incorrect dates?
3. Does `ALTER SESSION SET NLS_DATE_FORMAT = ...` modify `DATE` column data, or only the session's conversion/display behavior?
4. Why is `DATE '2026-11-14'` more reliable than a date string without an explicit format?
5. How do `NLS_DATE_LANGUAGE` and `NLS_TERRITORY` differ in their roles?
6. How do `NLS_TIMESTAMP_FORMAT`, `NLS_TIMESTAMP_TZ_FORMAT`, and `SESSIONTIMEZONE` differ?
7. When two JDBC connections use the same database but parse dates differently, what must you inspect on **both connections**?
8. If `NLS_DATABASE_PARAMETERS` contains `NLS_CHARACTERSET = AL32UTF8`, can you conclude a session's `NLS_DATE_FORMAT` from that?
9. Why is opening another SQL tab insufficient to prove you have a new session?
10. How does `TO_CHAR` with an explicit format help when producing API or report outputs?

## 14. Key takeaways

| If you want to know... | Query... | Avoid concluding... |
|---|---|---|
| What NLS configuration does the database record? | `NLS_DATABASE_PARAMETERS` | Every client uses the exact same settings |
| What NLS settings does the instance have? | `NLS_INSTANCE_PARAMETERS` | All sessions or all RAC nodes are identical |
| What format is SQL in the current connection using? | `NLS_SESSION_PARAMETERS` | This is an audit log of who changed parameters |
| What does a DATE/TIMESTAMP value store? | Column type, value, and Oracle rules | Screen formatting equals on-disk storage format |
| Want stable date/number strings? | Bind proper types or use `TO_CHAR`/`TO_DATE` with format | Rely on implicit conversion and hope NLS is uniform |
| Suspect a time zone offset? | `SESSIONTIMEZONE`, `DBTIMEZONE`, timestamp types, application | Changing `NLS_DATE_FORMAT` alone is enough |

The diagnostic sequence should be: **identify session and container → read all three parameter groups for context → use `NLS_SESSION_PARAMETERS` as the direct checkpoint for the SQL statement → verify data types and conversions → use explicit formats or binds → retest in the exact same connection**. Following this order separates initial configuration, session state, tool rendering, and the data actually stored by Oracle.
