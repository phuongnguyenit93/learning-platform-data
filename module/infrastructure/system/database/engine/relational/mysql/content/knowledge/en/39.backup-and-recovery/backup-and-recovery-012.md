# Backup and Recovery

## Charset, Collation, SQL Mode, and Configuration to Cross-Check After Restore

Technically succeeding in restoring a MySQL backup does not necessarily recreate the exact source environment. All data may load cleanly, yet the application still displays garbled characters, queries sort differently than before, statements are rejected, or scheduled tasks run at the wrong time. These discrepancies commonly stem from character sets, collations, SQL modes, and server configuration variables on the target host.

In the `DATABASE_MYSQL` module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, tuning queries, managing privileges, backing up, and handling relational database operational issues. During backup and recovery, those skills apply both before and after loading data: you must know which structures are restored, which settings are absent from the dump, and which differences can alter application behavior.

This lesson focuses on establishing a source baseline, comparing against the target server, and verifying post-restore. Examples use standard MySQL syntax; specific variables, collations, and features depend on version. Always verify against your actual running version before applying.

### 1. What Can Change After a Restore?

A logical backup such as an SQL dump typically contains database/table creation statements and data; depending on the tool and options, it may also include views, triggers, routines, and events. It does not automatically recreate full server configuration such as `my.cnf` or `my.ini`, startup flags, replication configuration, plugins, or OS-level operational policies.

When cross-checking post-restore, separate these four layers:

| Layer | Items to Verify | Consequence if Different from Source |
|---|---|---|
| Connection | Client, connection, and results charset and collation | Characters sent or returned may be mis-transcoded; string literal comparisons may differ |
| Schema metadata | Default charset/collation of databases, tables, and individual columns | New data, comparisons, sorting, and unique indexes may behave differently |
| SQL semantics | `sql_mode`, stored program creation mode, session time zone | Statements may fail, silently coerce data, or run under different rules |
| Server configuration | Version, table-name case sensitivity, storage engine, packet size, time zone, replication, and event scheduler | Restore may fail, or the application and background jobs may behave differently |

Do not compare only `character_set_server` or `sql_mode` and conclude two servers are equivalent. You must check both restored object metadata and the session state used by the application.

### 2. Charset and Collation

A **character set** defines how characters are encoded into bytes. A **collation** defines how strings within a character set are compared and sorted, including handling of case sensitivity, accents/diacritics, and certain whitespace rules.

For example, `utf8mb4` can represent the full range of Unicode characters, including emojis and characters outside the Basic Multilingual Plane. In many MySQL versions, `utf8` is an alias for `utf8mb3`, supporting at most three bytes per character; for new designs, explicitly specify `utf8mb4`.

Collation names typically indicate comparison rules:

- `ai_ci`: accent-insensitive and case-insensitive, meaning accent and letter-case differences are generally ignored.
- `as_cs`: accent-sensitive and case-sensitive, meaning accents and letter case are distinguished.
- Collations ending in `_bin` use binary comparison rules for the corresponding character set.
- Certain UCA 9.0 collations, such as `utf8mb4_0900_ai_ci`, exist only on MySQL versions that support them. Older and newer collations may also differ in trailing-space handling.

Collations directly affect `WHERE`, `ORDER BY`, `GROUP BY`, join comparisons, and unique indexes. Two customer codes differing in case or diacritics might be treated as equal under a collation that ignores those differences. Thus, changing collations after restore can change query results or cause duplicates when building unique indexes.

#### 2.1. Default Hierarchy and Scope

MySQL applies charset/collation at multiple levels:

1. **Server:** `character_set_server` and `collation_server` provide defaults when creating new databases without explicit specifications.
2. **Database:** each schema has its own default charset/collation; this default is used when creating new tables inside the schema unless overridden by the statement.
3. **Table:** a table has a default charset/collation; new string columns can inherit from it.
4. **Column:** string-type columns can specify their own charset/collation. This is the metadata directly governing comparisons on that column's data.
5. **Connection:** `character_set_client`, `character_set_connection`, `character_set_results`, and `collation_connection` control how MySQL receives, interprets, and returns strings in a session.

Changing the server or database default charset does not automatically convert existing columns. To convert table data and metadata, an explicit conversion operation is required and its impact must be assessed beforehand.

#### 2.2. Recording Charset/Collation State

On both source and target servers, record version details and connection/server variables:

```sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS version_comment,
  @@character_set_server AS character_set_server,
  @@collation_server AS collation_server,
  @@character_set_client AS character_set_client,
  @@character_set_connection AS character_set_connection,
  @@character_set_results AS character_set_results,
  @@collation_connection AS collation_connection;
```

Inspect database defaults and table definitions:

```sql
SHOW CREATE DATABASE appdb;
SHOW CREATE TABLE appdb.customers;

SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Inspect string columns with explicit settings:

```sql
SELECT
  TABLE_NAME,
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Finally, verify that collations referenced in the dump exist on the target server:

```sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
```

If a collation does not exist, import may halt with an `Unknown collation` error. For instance, a dump created from MySQL 8.0 may contain `utf8mb4_0900_ai_ci`, whereas a MySQL 5.7 server does not recognize this collation. Pick a compatible replacement collation only after comparing comparison semantics; bulk-replacing collation names in a dump without checking can alter comparison rules and uniqueness.

#### 2.3. Connection Charset During Import

The client must transmit dump contents using the matching charset. For UTF-8/utf8mb4 dumps, specify the charset for the MySQL client:

```bash
mysql --default-character-set=utf8mb4 -u restore_user -p appdb < backup.sql
```

Inside an SQL session, set connection charset with:

```sql
SET NAMES utf8mb4;
-- If a specific collation is supported and selected:
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

`SET NAMES` sets session charset variables for client, connection, and results; versions supporting the `COLLATE` clause also set `collation_connection`. This statement does not alter the charset/collation stored on tables and columns. Nor can it fix a dump file that was already corrupted by wrong encoding before import.

When restoring, inspect how the backup tool writes charset directives in the SQL file. Many dumps include session-level setup statements; review those as well when moving across different MySQL versions. Avoid letting terminals, scripts, or intermediary tools inadvertently transcode the dump file.

#### 2.4. Intentionally Changing Charset/Collation

If you need to convert a table to `utf8mb4`, common syntax is:

```sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Run this example only when the target server supports the chosen collation and you have confirmed comparison rules fit business logic. `CONVERT TO CHARACTER SET` converts data and metadata of string columns in the table; the operation may rebuild the table, consume significant time and disk space, and expose unique key collisions.

Before converting, back up, test on a copy, and find values that could become equal under the new collation. Example check under a specific collation:

```sql
SELECT
  customer_code COLLATE utf8mb4_0900_ai_ci AS code_under_new_collation,
  COUNT(*) AS occurrences
FROM customers
GROUP BY customer_code COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Review results against business rules before recreating unique indexes. Changing collations can change sort order and comparison outcomes even when underlying data bytes are unchanged.

### 3. SQL Mode and Restore Behavior

`sql_mode` is a set of modes controlling how MySQL parses and executes SQL. Some modes enforce data strictness; others alter syntax or query validation rules.

Modes requiring close attention:

- `STRICT_TRANS_TABLES` or `STRICT_ALL_TABLES`: turns many invalid-type, out-of-range, or truncated values into errors instead of silent coercion or warnings.
- `ONLY_FULL_GROUP_BY`: strictly validates expressions in grouping queries; a query that ran on an older server may be rejected.
- `ANSI_QUOTES`: treats double quotes as identifier quotes, which can break SQL statements using double quotes for string literals.
- `NO_BACKSLASH_ESCAPES`: changes how backslashes are interpreted in string literals.
- `NO_ZERO_DATE` and `NO_ZERO_IN_DATE`: can affect acceptance of dates containing zero components; exact support and warnings depend on version.
- `NO_ENGINE_SUBSTITUTION`: prevents MySQL from silently substituting another storage engine when the requested engine is unavailable.

Default mode lists change across versions and configurations. Never copy `sql_mode` blindly from another server without testing the application and data.

#### 3.1. Comparing Global and Session Modes

```sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode;
```

`GLOBAL` is the default applied to new sessions; `SESSION` is the mode of the current connection. Changing global does not alter already-open sessions. Thus, an application using a connection pool may keep running with old session modes after global config changes; manage connection lifecycles and reconnect properly.

In a test restore session, record `@@SESSION.sql_mode` before importing and check whether the dump contains mode-changing statements. If legacy data only imports when relaxing a mode, pinpoint the exact offending values and why they exist. Only adjust modes within a controlled restore session by explicit decision; never turn off strict mode globally to mask data errors. After importing, inspect warnings, errors, and coerced values, then run the application under the target environment's intended mode.

#### 3.2. SQL Mode Stored with Stored Programs

MySQL saves the `sql_mode` active when a stored procedure, function, trigger, or event is created; at execution time, the object can use that saved mode rather than the caller session's current mode. Therefore, comparing only `@@GLOBAL.sql_mode` post-restore is insufficient.

Inspect metadata of routines, triggers, and events:

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';

SELECT TRIGGER_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb';

SELECT EVENT_NAME, STATUS, SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
```

For critical objects, also save definitions using `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER`, or `SHOW CREATE EVENT`. When recreating objects from a dump, the session creating the objects can determine the stored `sql_mode`. Set and verify the mode against your desired baseline before running this DDL section.

### 4. Server Configurations to Cross-Check

Charset and SQL mode are two critical groups, though not the only settings that affect recovery outcomes. Record a source baseline and compare with the target server based on deployment goals.

| Setting | Why Check It | Restore Notes |
|---|---|---|
| `VERSION()` and `version_comment` | Differences in syntax, collations, data types, and features | Verify both upgrade/downgrade directions; never assume a dump from a newer version runs intact on an older version |
| `lower_case_table_names` | Rules for storing and comparing database/table names | Especially critical when moving between Windows and Linux; in MySQL 8.0, the value is fixed when initializing the data directory |
| `default_storage_engine` and per-table engines | Tables may depend on InnoDB or specific engines/plugins | Inspect actual engines in `INFORMATION_SCHEMA.TABLES`, not just the server default |
| `time_zone` and `system_time_zone` | Affects how `TIMESTAMP` values are interpreted and displayed per session | Standardize on UTC for dump/restore workflows and test application time zones; `DATETIME` does not auto-convert by session time zone |
| `max_allowed_packet` | Large packets can cause imports to fail | Check when dumps contain BLOBs, JSON, or large rows; tune carefully on client/server if needed |
| `transaction_isolation` and `autocommit` | Can alter application transaction behavior | Variable name can differ across versions; verify via `SHOW VARIABLES` and workload tests |
| `innodb_page_size` | Affects InnoDB page format and certain physical limits | Chosen at instance initialization; especially critical to match for physical backups or physical compatibility. Logical dumps do not strictly require the same page size |
| `event_scheduler` | Restored events may start running on schedule | Keep scheduler in an appropriate state during verification; enable only when data and schedules are ready |
| `server_id`, `log_bin`, `gtid_mode` | Affects replication and binlog-based recovery | If the target joins replication, identity and GTID settings must follow topology; never blindly clone the source's identity settings |

Two closely linked concerns when switching operating systems are `lower_case_table_names` and object names. Case sensitivity on a source can permit two tables that a case-insensitive target cannot tell apart. Check for names differing only in letter case before restoring. With MySQL 8.0, choose the right `lower_case_table_names` before initializing the data directory; it cannot be freely changed after data initialization.

`innodb_page_size` is also an initialization setting. With a logical backup, tables are recreated via SQL and can restore onto an instance with a different page size if other conditions remain compatible. With a physical backup, obey tool and version compatibility limits; never infer physical restorability from a logical dump succeeding.

To quickly check key variables on the target server:

```sql
SHOW VARIABLES WHERE Variable_name IN (
  'lower_case_table_names',
  'default_storage_engine',
  'time_zone',
  'system_time_zone',
  'max_allowed_packet',
  'innodb_page_size',
  'event_scheduler',
  'server_id',
  'log_bin',
  'gtid_mode'
);

SHOW VARIABLES LIKE 'transaction_isolation';
SHOW VARIABLES LIKE 'tx_isolation';
```

Some variables exist only on certain versions or require appropriate read privileges. If a variable does not exist, document the version difference explicitly rather than treating it as equal.

### 5. Pre- and Post-Restore Cross-Check Workflow

A repeatable workflow avoids relying on operator memory.

**Step 1 — Capture source baseline.** Record MySQL version, charset/collation variables, global and session SQL modes, time zones, `lower_case_table_names`, engines, packet sizes, and replication/event settings. Save `SHOW CREATE DATABASE` and `SHOW CREATE TABLE` for key schemas; export metadata for routines, triggers, and events.

**Step 2 — Verify compatibility.** Compare source/target versions, check available collations, storage engines, and required plugins. Identify settings that cannot be changed after instance initialization such as `lower_case_table_names` and `innodb_page_size` ahead of time.

**Step 3 — Prepare target instance.** Configure server variables per target design, create databases with agreed charsets/collations, and prepare restore accounts and storage space. If the dump includes events, consider keeping `event_scheduler` disabled during load and verification.

**Step 4 — Import with proper charset and session settings.** Invoke the MySQL client with `--default-character-set` matching the dump contents. Inspect `SET NAMES`, `SET SQL_MODE`, and `SET TIME_ZONE` statements inside the file. Log all errors and warnings; never ignore mid-import errors.

**Step 5 — Cross-check metadata post-import.** Re-run charset/collation queries, inspect `SHOW CREATE DATABASE` and `SHOW CREATE TABLE`, check column-level collations, storage engines, and SQL modes stored with stored programs. Confirm all critical objects were created completely.

**Step 6 — Verify data and behavior.** Compare row counts, business checksums, and data samples against the source. Test accented strings, upper/lowercase, non-BMP characters, near-equal unique key values, dates/times, transactions, and `GROUP BY` queries. Run application tests using sessions configured with production's charset, collation, time zone, and SQL mode.

**Step 7 — Enable background tasks.** After confirming data and privileges, enable the event scheduler if needed; configure replication/binlog per topology; monitor logs and verify initial jobs. Document accepted differences and accountable owners.

### 6. Common Post-Restore Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Unknown collation` on import | Dump references a collation missing on target version | Check version and collation list; pick a compatible option after testing comparison rules |
| Corrupted Vietnamese text or emojis | File, client, connection, or column charset mismatch | Inspect dump bytes, `--default-character-set`, `SET NAMES`, and column metadata; find which stage corrupted data |
| Import errors on zero dates or out-of-range values | Target SQL mode is stricter than source | Inspect offending statements and rows; decide whether to fix data or use a controlled restore session, then re-test under target mode |
| `GROUP BY` queries rejected | `ONLY_FULL_GROUP_BY` differs from source | Rewrite queries to specify aggregate values or grouping expressions clearly; avoid disabling the mode globally |
| Unique index creation fails after collation change | Previously distinct strings are now treated as equal by the collation | Locate and resolve collisions per business rules before creating the index |
| Table names not found after OS migration | `lower_case_table_names` or case differences in names | Compare object name metadata and initialization settings; resolve name collisions before migrating |
| Timestamps appear shifted by hours | Different session time zone or time zone tables | Check `@@time_zone`, `@@system_time_zone`, application config, and how dump/restore interpreted timestamps |
| Events run too early or not at all | `event_scheduler` or event status differs from expectations | Check `INFORMATION_SCHEMA.EVENTS`, scheduler state, and schedule before enabling |

Never use `SET NAMES` to repair data already stored with corrupted encoding. That command only controls how a session exchanges strings from the moment it runs onward. If table data has already been garbled into wrong characters, determine the exact original encoding and plan a data conversion backed by backups, testing, and verification.

### 7. Verification Checklist

Before handing over a newly restored database, confirm these items:

- [ ] MySQL version and required features are compatible with the source.
- [ ] Server, database, table, column, and connection charsets/collations are recorded and cross-checked.
- [ ] All collations referenced in DDL exist on the target server.
- [ ] String comparison rules, unique indexes, and sort orders have been tested.
- [ ] Global/session `sql_mode` matches design; routines, triggers, and events carry appropriate stored modes.
- [ ] `lower_case_table_names`, storage engines, time zones, packet sizes, and related variables have been verified.
- [ ] Replication, GTIDs, event scheduler, and background tasks are activated at the right moment.
- [ ] No unexplained import errors or warnings remain; row counts and business totals match.
- [ ] Application tested with realistic connection config and key queries return expected results.
- [ ] Source baseline, accepted differences, and test results are documented.

### 8. Practice Exercise

A system runs MySQL 8.0 with a `sales` database using `utf8mb4`, several tables using `utf8mb4_0900_ai_ci`, and an SQL mode including `STRICT_TRANS_TABLES` and `ONLY_FULL_GROUP_BY`. The operations team needs to restore a logical dump onto a new server with a different version and configuration.

1. Write statements to record version, server charset/collation, session charset, global/session SQL mode, and time zones on both source and target.
2. Query `INFORMATION_SCHEMA` to list tables and columns with explicit collations in the `sales` schema.
3. If the target server does not support `utf8mb4_0900_ai_ci`, which properties must you verify before picking a replacement collation?
4. Explain why a unique index can fail after switching from an accent-sensitive collation to an accent-insensitive collation.
5. A stored procedure behaves differently after restore even though `@@GLOBAL.sql_mode` matches on both servers. Which metadata should you inspect to find the cause?
6. Why should you not turn off strict mode globally just to import a dump containing invalid date values?
7. List the settings to lock down before migrating a database from Windows to Linux, especially for table names containing mixed case.

### 9. Operational Principles

A restore is only complete once data, metadata, and application behavior are all verified. Store configuration baselines alongside backups, compare layer by layer, test differences capable of altering query outcomes, and document cutover decisions. Charset governs character representation; collation governs comparisons; SQL mode governs many execution rules; server and session variables complete the runtime environment where the application actually runs. Thoroughly cross-checking these layers ensures the recovery faithfully reproduces expected behavior and reduces the risk of discovering discrepancies after reopening service.
