# Reconciling Character Sets, Collations, Time Zones, and SQL Modes Between Source and Target

Migrating MySQL data between two environments can complete without errors yet produce results that differ from the source. Accented characters become garbled, strings sort in a different order, timestamps shift by hours, or statements that previously succeeded are rejected after restore. These discrepancies usually stem from differences in connection session settings, schemas, MySQL versions, or SQL modes between source and destination.

Before dumping or importing, inventory configuration on both sides and compare them layer by layer. The four groups to verify are **character set**, **collation**, **time zone**, and **SQL mode**. They govern how bytes are decoded into characters, how strings are compared and sorted, how temporal values are converted, and how MySQL parses and validates SQL.

## 1. Why Must Source and Target Configurations Be Compatible?

Suppose the source uses `utf8mb4` with collation `utf8mb4_0900_ai_ci`, while the destination runs an older MySQL version that does not support that collation. Importing the DDL as-is may cause `CREATE TABLE` to fail. If an operator arbitrarily switches to another collation to make the import pass, comparisons, `ORDER BY`, `GROUP BY`, or unique indexes can behave differently.

Similarly, if an application writes `2026-11-19 10:00:00` into a `TIMESTAMP` column under a `+07:00` session time zone, MySQL converts the value to UTC when storing it. Restoring or reading under a `+00:00` session without accounting for this rule changes the displayed time. With `DATETIME`, MySQL stores the calendar date and time literally without converting by session time zone.

SQL mode can also cause import failures or change how statements are evaluated. For example, if the source allowed zero dates under an older mode while the destination enables `STRICT_TRANS_TABLES` and `NO_ZERO_DATE`, the import may stop on invalid values. An application relying on division by zero or legacy string-escape handling can also behave differently when modes change.

Never compare just `character_set_server` or `time_zone` and conclude two systems are compatible. Inspect configuration across server, database, table, column, and connection layers, alongside actual metadata in DDL and data.

## 2. Inventorying Character Sets on Source and Destination

A character set defines which characters can be represented and how they are encoded into bytes. In MySQL, settings exist at multiple layers:

| Layer | Variables / Metadata to Inspect | Effect |
|---|---|---|
| Server | `character_set_server` | Default when creating a database if unspecified. |
| Database | `character_set_database`, `INFORMATION_SCHEMA.SCHEMATA` | Default for new tables in that database. |
| Table | `INFORMATION_SCHEMA.TABLES.TABLE_COLLATION` and DDL | Default for new character columns in that table. |
| Column | `INFORMATION_SCHEMA.COLUMNS.CHARACTER_SET_NAME` | How each column stores and interprets data. |
| Connection | `character_set_client`, `character_set_connection`, `character_set_results` | How MySQL receives statements, handles literals, and returns results to clients. |

Check server and session configuration:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
    @@GLOBAL.character_set_server AS global_server_charset,
    @@GLOBAL.collation_server AS global_server_collation,
    @@SESSION.character_set_client AS session_client_charset,
    @@SESSION.character_set_connection AS session_connection_charset,
    @@SESSION.character_set_results AS session_results_charset,
    @@SESSION.collation_connection AS session_connection_collation;
```

Check databases, tables, and columns:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY SCHEMA_NAME;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY TABLE_SCHEMA, TABLE_NAME;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE CHARACTER_SET_NAME IS NOT NULL
  AND TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
```

Run the same queries on source and destination, export results to files, and diff them. Default values can differ even when individual column DDLs match. `character_set_database` is a session variable tied to the current default database and is deprecated in newer MySQL versions; when inventorying, prefer `INFORMATION_SCHEMA.SCHEMATA` metadata to know each schema's true default.

### Choosing `utf8mb4` Deliberately

For modern application data, `utf8mb4` is usually the right choice because it represents full Unicode, including supplementary characters outside the BMP and emojis. Do not confuse `utf8` with full UTF-8 in MySQL: the historical `utf8` name is an alias for `utf8mb3`, which supports at most three bytes per character; `utf8mb3` is deprecated in newer versions.

When creating a new schema, specify charset and collation explicitly:

```sql
CREATE DATABASE appdb
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` is an example for MySQL 8.0 and later. If the destination runs an older version, this collation may not exist. Choose a collation supported by both versions that matches application comparison rules, or upgrade the destination before importing. Do not automatically substitute `utf8mb4_general_ci` just to bypass DDL errors without evaluating the impact.

## 3. Checking Collations and Comparison Semantics

A collation defines how strings within a character set are compared and sorted. Common suffixes include:

- `ai`: accent-insensitive, typically treating accented and unaccented letters as equal in comparisons.
- `as`: accent-sensitive, distinguishing accents.
- `ci`: case-insensitive, typically ignoring uppercase/lowercase differences.
- `cs`: case-sensitive, distinguishing uppercase and lowercase.
- `bin`: compares by binary/code-unit value rather than linguistic rules.

For example, under a case-insensitive and accent-insensitive collation, `Cafe`, `café`, and `CAFE` may be treated as equal. This directly impacts `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`, and unique indexes.

Inspect collations supported by the server:

```sql
SHOW COLLATION WHERE Charset = 'utf8mb4';
```

Test comparison rules before moving data:

```sql
SELECT
    _utf8mb4'Cafe' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS accent_case_insensitive,
    _utf8mb4'Cafe' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'café' COLLATE utf8mb4_0900_as_cs AS accent_case_sensitive;
```

The specific collation names must exist on the running server version. When testing on older versions, substitute an appropriate supported collation and document the results.

A major risk when changing collations is **newly colliding values under the new rules**. For instance, a source using a case-sensitive collation can hold both `UserA` and `usera`; a destination using a case-insensitive collation treats both as identical. When importing into a unique index, the second row triggers a duplicate-key error. Likewise, changing accent or trailing-space sensitivity affects comparisons and uniqueness.

Before changing collation on a column with a unique index, identify value groups that would collapse under the target collation. You can create a test copy and run a grouping query forcing the target collation:

```sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS normalized_username,
    COUNT(*) AS row_count
FROM appdb.users
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

This test must use the exact collation intended for production. For large datasets, consider creating a staging table and trial index to catch collisions before altering production schemas.

## 4. Connection Character Sets and Mojibake Data

Even when columns use `utf8mb4`, data can still be corrupted if clients send bytes in a different charset or MySQL misinterprets literal charsets. Connection variables have distinct roles:

- `character_set_client`: charset the client uses to send statements.
- `character_set_connection`: charset MySQL uses when converting literals and evaluating string expressions in statements.
- `character_set_results`: charset MySQL uses when sending results back to the client.
- `collation_connection`: collation applied to certain comparisons between literals and expressions on the connection.

Applications should declare connection charsets explicitly. Example with the command-line client:

```bash
mysql --default-character-set=utf8mb4 -h db.example.net -u app_user -p appdb
```

Or set it in a session when testing:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

`SET NAMES` updates the corresponding connection charset variables. For applications, configure charset in the driver/connection string so every pooled connection initializes properly. Do not manually run `SET NAMES` in a single session and assume every application connection is configured.

During dump/import, inspect file encoding with suitable tools and preserve raw bytes. Do not re-encode files through text editors or text pipelines without knowing the original charset. Dump files may contain charset directives; read the file header and tool metadata. If importing a UTF-8 file while the client reads it using a different OS encoding, data can be corrupted even though target columns use `utf8mb4`.

Mojibake symptoms like `Ã©` instead of `é` usually indicate UTF-8 bytes were misinterpreted as another charset and stored that way. Changing collation cannot repair already-corrupted bytes. Determine which bytes are actually stored, the charsets declared at each layer, and the data-producing source before performing controlled remediation.

## 5. Inventorying Time Zones and Understanding TIMESTAMP/DATETIME

MySQL has both a global time zone and a session time zone. Check:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;

SHOW VARIABLES LIKE 'time_zone';
```

The two primary temporal types behave differently:

| Type | Storage and Retrieval Behavior | During Data Migration |
|---|---|---|
| `TIMESTAMP` | MySQL converts values from the session time zone to UTC on write, and from UTC to the session time zone on read. | Control time zones of import and application sessions; differing session zones display different wall-clock times even though the instant is preserved. |
| `DATETIME` | Stores the literal calendar date and time as supplied, without converting by session time zone. | Must know whether values represent UTC or local time by business convention; never auto-shift time zones during dump/import. |

Example:

```sql
SET time_zone = '+07:00';

CREATE TEMPORARY TABLE time_demo (
    created_at_ts TIMESTAMP,
    created_at_dt DATETIME
);

INSERT INTO time_demo VALUES
    ('2026-11-19 10:00:00', '2026-11-19 10:00:00');

SELECT * FROM time_demo;

SET time_zone = '+00:00';
SELECT * FROM time_demo;
```

`created_at_ts` displays in the current session's time zone, whereas `created_at_dt` retains the stored date-time string unchanged. This difference is crucial when importing a dump from a `+07:00` environment into a `+00:00` environment.

If a `DATETIME` column stores UTC by application convention, preserve the values as-is and continue interpreting them as UTC on the destination. If a `DATETIME` column stores local time, document the business region's time zone and handle conversions in the application; `DATETIME` itself carries no time zone metadata. You cannot reliably recover the original time zone from bare `DATETIME` values without metadata.

### Named Time Zones and CONVERT_TZ

MySQL supports numeric offsets such as `'+00:00'` and `'+07:00'`, as well as named zones such as `'Asia/Ho_Chi_Minh'`. Named zones require time zone tables to be loaded in MySQL. Check:

```sql
SELECT CONVERT_TZ(
    '2026-11-19 10:00:00',
    '+07:00',
    '+00:00'
) AS utc_value;

SELECT CONVERT_TZ(
    '2026-11-19 10:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
) AS named_zone_value;
```

If named-zone conversion returns `NULL`, check the server's time zone tables and load time zone data per OS/MySQL procedures. DST rules for named zones can change with `tzdata` updates; if applications depend on historical or future timestamps, synchronize time zone data on both source and destination.

`NOW()` returns time in the session time zone; `UTC_TIMESTAMP()` returns UTC. `CURRENT_TIMESTAMP` behaves like `NOW()`. `SYSDATE()` returns the wall-clock time at the exact moment the function executes and can differ from `NOW()` within the same statement; take note if data depends on it.

## 6. Reconciling SQL Modes

SQL mode changes how MySQL parses and validates statements. Check global and session modes on both source and destination:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;

SHOW VARIABLES LIKE 'sql_mode';
```

Modes that can alter behavior during import include:

| Mode | Impact to Evaluate |
|---|---|
| `STRICT_TRANS_TABLES` | Rejects or strictly handles invalid values for transactional tables instead of silently coercing to defaults in many cases. |
| `STRICT_ALL_TABLES` | Applies strict validation across more storage engines; error handling for non-transactional tables may differ. |
| `NO_ZERO_DATE`, `NO_ZERO_IN_DATE` | Affects acceptance of `'0000-00-00'` dates or zero date components; exact behavior depends on strict mode and version. These modes are deprecated in MySQL 8.0. |
| `ONLY_FULL_GROUP_BY` | Rejects grouped queries containing columns not aggregated or functionally dependent on grouped columns. |
| `ANSI_QUOTES` | Treats double quotes as identifier quotes rather than string literal quotes. |
| `NO_BACKSLASH_ESCAPES` | Changes how backslashes are interpreted inside string literals. |
| `ERROR_FOR_DIVISION_BY_ZERO` | Affects handling of division by zero, especially combined with strict mode. |
| `PAD_CHAR_TO_FULL_LENGTH` | Affects reading `CHAR` values; deprecated in MySQL 8.0. |

Do not copy `sql_mode` verbatim from source to destination without checking version compatibility. Some modes have been deprecated, removed, or changed in behavior across versions. Compare mode lists, classify modes required by applications, and test affected statements.

You can set a session mode during testing:

```sql
SET SESSION sql_mode =
  'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
```

`SET SESSION` affects only the current connection. `SET GLOBAL sql_mode` changes the default for new sessions and typically requires administrative privileges; it does not alter already-open sessions. For persistence across restarts, manage it in server configuration files or your organization's configuration management system. Never alter global mode in production just to push an import through without understanding its impact on other applications.

Stored procedures, functions, triggers, and events store the SQL mode active at creation time. Consequently, changing `@@SESSION.sql_mode` right before importing data does not guarantee that stored objects created afterward behave identically to the source. Inspect `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER`, and `SHOW CREATE EVENT`, and test object behavior after restore.

## 7. Building a Source/Destination Inventory Table

A comparison table facilitates pre-migration review:

| Item | Source | Destination | Decision |
|---|---|---|---|
| MySQL version | 8.0.x | 8.4.x | Confirm syntax, collation, and SQL mode compatibility. |
| Server charset/collation | `utf8mb4` / `utf8mb4_0900_ai_ci` | `utf8mb4` / compatible collation | Preserve DDL as required or convert with testing. |
| Database/table/column charset | Actual metadata | Actual metadata | Identify columns with custom charsets or unnormalized tables. |
| Connection charset | `utf8mb4` | `utf8mb4` | Configure in driver and verify every connection pool. |
| Time zone | `+07:00` | `+00:00` | Control import session; distinguish `TIMESTAMP` from `DATETIME`. |
| SQL mode | Actual mode list | Actual mode list | Test data and statements that could be affected. |
| Named timezone tables | Present / absent | Present / absent | Load and update if named zones are used. |

Values in the table illustrate the recording format; replace them with actual survey results. Also record client tool versions (`mysqldump`, `mysql`, or connectors), since tools inject session directives into dumps and behave differently across versions.

## 8. Pre-Dump/Import Verification Workflow

### Step 1: Capture Source Configuration

Run queries inventorying charset, collation, time zone, and SQL mode. Save outputs with timestamps, MySQL versions, `server_uuid`, and schema names. Export DDL via `SHOW CREATE DATABASE` and `SHOW CREATE TABLE`, and inspect stored objects if within migration scope.

```sql
SHOW CREATE DATABASE appdb;
SHOW CREATE TABLE appdb.users;
SHOW CREATE PROCEDURE appdb.refresh_summary;
```

### Step 2: Check Destination Compatibility

On the destination, inspect version, supported charsets/collations, SQL modes, time zone tables, data type limits, and DDL features. If the destination is older than the source, pay special attention to newer collations, data types, or unsupported syntax. If the destination is newer, check changes in default modes and comparison rules.

### Step 3: Trial Run on a Staging Schema

Import a copy of the data into a staging schema or test instance. Check for charset/collation errors, duplicate keys, invalid dates, truncation, warnings, and row counts. Run representative application queries to compare `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`, and date/time comparisons.

### Step 4: Set the Import Session Explicitly

For dumps created by `mysqldump`, inspect the top of the file to understand emitted session directives. `mysqldump` provides `--tz-utc` (typically enabled by default in modern versions) to set UTC time zone during dump; verify behavior for your exact version and do not use `--skip-tz-utc` without understanding its effect on `TIMESTAMP`. When importing with a client, confirm file charset and set the matching connection charset. Never let terminal environment defaults silently dictate encoding.

### Step 5: Post-Import Reconciliation

Compare DDL, row counts, checksums, or business aggregates. Re-check `INFORMATION_SCHEMA.COLUMNS`, table collations, session time zone, and SQL mode. Pay special attention to tables with unique indexes on string columns, `TIMESTAMP`/`DATETIME` columns, stored objects, and data containing non-ASCII characters.

## 9. Controlled Import Configuration Example

Suppose a UTF-8 dump from the source was generated in UTC and the destination uses `utf8mb4`. An import can be run as follows:

```bash
mysql --default-character-set=utf8mb4 \
  --host=restore-db.internal \
  --user=restore_user \
  -p appdb < appdb.sql
```

After connecting, verify session settings:

```sql
SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.time_zone,
    @@SESSION.sql_mode;
```

If you need to normalize session time zone for importing `TIMESTAMP` data, you can use:

```sql
SET SESSION time_zone = '+00:00';
```

Do not automatically run `ALTER DATABASE ... CHARACTER SET` or `ALTER TABLE ... CONVERT TO CHARACTER SET` right before import to force everything onto one setting. Those statements can rebuild tables, change column collations, trigger duplicate-key errors, consume temporary space, and lock or disrupt workloads. Test on a clone, resolve collisions, and plan downtime or online DDL appropriately.

## 10. Common Environment-Migration Issues

| Symptom | Possible Cause | Investigation / Resolution |
|---|---|---|
| Import reports unknown collation | Destination does not support a collation in DDL | Check `SHOW COLLATION` and version; select a compatible collation after evaluating semantics. |
| Vietnamese characters turn into `?` or mojibake | Client/file/column charset mismatch or bytes were misconverted | Identify original bytes, dump charset, connection, and column; do not try to fix by simply altering collation. |
| Duplicate key on import | Target collation treats two distinct source strings as equal | Find colliding groups under target collation, cleanse data, or choose appropriate rules. |
| `TIMESTAMP` values shifted by exact hours | Different session time zones on write vs. read | Compare `@@time_zone`, `@@system_time_zone`, UTC, and dump time zone options. |
| `DATETIME` values shifted erroneously | App or script added/subtracted time zone even though MySQL does not convert `DATETIME` | Clarify UTC vs. local-time convention and remove improper conversion steps. |
| Import fails on zero dates | Destination SQL mode is stricter or newer version changed behavior | Locate invalid dates; fix per business rules before importing. |
| `GROUP BY` query fails after restore | Destination enables `ONLY_FULL_GROUP_BY` | Rewrite SQL deterministically or evaluate mode per application policy. |
| Stored routine behaves differently | SQL mode captured at object creation time | Inspect object DDL and SQL mode; recreate cleanly after testing. |
| `CONVERT_TZ` returns `NULL` for named zones | Time zone tables not loaded or zone name missing | Load/update time zone tables and retest. |
| `ORDER BY` sorting differs | Different collation or Unicode collation version | Compare collations, test representative data, and verify expected order. |

## 11. Post-Migration Data Acceptance Checklist

- [ ] Recorded MySQL versions, client tool versions, and `server_uuid` for source and destination.
- [ ] Inventoried charsets at server, database, table, column, and connection layers.
- [ ] Confirmed target collations exist and provide comparison semantics suited to the application.
- [ ] Checked unique indexes for collisions under target collations.
- [ ] Confirmed dump file encoding; configured matching charset in import driver/client.
- [ ] Recorded global/session/system time zones; ensured named time zone tables are ready if needed.
- [ ] Confirmed `TIMESTAMP` and `DATETIME` conventions, especially for columns storing local time.
- [ ] Compared source/destination SQL modes and tested affected modes.
- [ ] Verified stored routines, functions, triggers, and events along with their stored SQL modes.
- [ ] Tested staging import and reconciled row counts, DDL, warnings, and business queries.
- [ ] Verified Unicode data, datetimes, unique keys, and sort order after restore.

A successful data migration preserves both values and their meaning. Character sets preserve characters, collations preserve comparison rules, time zones preserve instants under business conventions, and SQL modes preserve how statements and data are accepted. Inventory these four areas on source and destination, rehearse imports in staging, and reconcile results before shifting production traffic.
