# Row-based replication, non-deterministic statements, and data divergence

MySQL replication can transmit changes either as SQL statements or as row-level data changes. Row-based replication (RBR) records the actual rows that were inserted, updated, or deleted on the source, allowing the replica to apply the exact outcome produced by the source. This is particularly useful when SQL statements are non-deterministic, environment-dependent, or could yield different results across two servers.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on replication and GTID operations: understanding **binlog_format**, identifying unsafe statements, selecting row images, detecting data divergence, and troubleshooting errors when a replica applies row events. The examples use MySQL 8.0; syntax and status names may differ in older versions or MySQL 8.4.

## 1. The three binary log formats

MySQL supports three values for the **binlog_format** variable:

| Format | What is written to the binary log | Characteristics |
|---|---|---|
| **STATEMENT** | Executed SQL statements | Smaller log volume for some workloads, but requires statements to produce identical results on source and replica |
| **ROW** | Row events describing modified rows | Records actual outcomes, fits most workloads, and avoids many issues caused by non-deterministic SQL |
| **MIXED** | Combination of statement events and row events | MySQL automatically chooses row format for statements identified as unsafe for statement format |

In MySQL 8.0, the default for **binlog_format** is **ROW**. This is generally the right choice for new systems because the replica receives the exact data changes that occurred on the source. However, RBR can produce larger binary logs for statements that update huge numbers of rows or modify large columns.

Check the current format:

~~~sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
~~~

### Statement-based replication

With statement format, the binary log stores the SQL statement. The replica re-executes that statement against its own data. Example:

~~~sql
UPDATE account
SET balance = balance - 100
WHERE account_id = 42;
~~~

The source writes the statement to the binary log; the replica executes the corresponding statement. This is compact when one statement modifies many rows and the same statement reliably yields the exact same result on every server.

Risk arises when results depend on timing, local data, non-guaranteed row ordering, session state, or non-deterministic functions. If the source and replica evaluate the statement differently, data can diverge without replication always raising an error.

### Row-based replication

With row format, MySQL records row events. For instance, the statement above can generate an event describing row **account_id = 42** with the balance values before and after the change. The replica applies the recorded row change without re-evaluating the expression **balance - 100**.

This reduces dependence on how SQL expressions are evaluated on the replica. In return, the binary log can hold more data, especially when a statement modifies a large number of rows.

### Mixed replication

With mixed format, MySQL uses statement events for statements considered safe and switches to row events when it detects a statement unsafe for statement-based replication. Classification is performed by the server; you should not assume every non-deterministic case is caught completely.

If a system requires predictable behavior, has multiple CDC consumers, or needs row-level change auditing, **ROW** is usually the clearer choice.

## 2. Why are some statements unsafe?

An SQL statement can be valid and produce the expected result on the source yet fail to reproduce the exact same result when re-run on a replica. Such statements are called unsafe for statement-based replication.

### Non-deterministic or environment-dependent functions

Some functions return different results depending on the invocation, server, or context:

- **UUID()** generates a new identifier on every call.
- **UUID_SHORT()** depends on server state and server identity.
- **RAND()** generates random values; deterministic replay depends on seeding and execution context.
- UDFs or stored functions may depend on external data, process state, or behavior outside MySQL's control.
- Functions reading files or server state can produce different results if the source and replica environments differ.

Not every seemingly variable function is always unsafe. For example, MySQL records the timestamp for certain functions such as **NOW()** in the statement event so the replica uses the same point in time. Rely on server warnings and version-specific documentation rather than guessing by intuition.

### Relying on unguaranteed row order

**LIMIT** without **ORDER BY** does not define which rows will be selected. Two servers can have different retrieval orders due to indexes, statistics, or execution plans.

~~~sql
-- Does not deterministically specify which rows will be updated
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
LIMIT 10;
~~~

If you need to select an exact group of rows, establish a stable order using a unique key:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
ORDER BY job_id
LIMIT 10;
~~~

Adding **ORDER BY** fixes the selection order, though you still need to check the uniqueness of the sort key and data conditions across both servers.

### Statements dependent on local data or configuration

Statements can produce different results when:

- Source and replica start with different baseline data.
- SQL mode, character set, collation, or session time zone differs.
- Execution order or transaction state differs.
- The statement references external objects, files, or user-defined functions.
- Triggers or stored programs differ between the two servers.

An unsafe statement does not necessarily halt replication. With statement format, MySQL may log a warning when it detects the risk yet still write the statement. If the statement executes on both servers and produces different results, the replica's data can drift.

## 3. Enabling row-based replication and checking sessions

Check the global configuration and the current session's configuration:

~~~sql
SELECT
  @@GLOBAL.binlog_format AS global_format,
  @@SESSION.binlog_format AS session_format,
  @@GLOBAL.binlog_row_image AS global_row_image,
  @@SESSION.binlog_row_image AS session_row_image;
~~~

To set defaults for new connections and persist across restarts:

~~~sql
SET PERSIST binlog_format = 'ROW';
SET PERSIST binlog_row_image = 'FULL';
~~~

Or declare in the server configuration file:

~~~ini
[mysqld]
binlog_format=ROW
binlog_row_image=FULL
~~~

**binlog_format** has both global and session scope. Changing the global value affects defaults for new sessions; existing application connections may continue using their old session value. When changing configuration, check application sessions and plan appropriate reconnections. Do not switch mid-flight arbitrarily while transactions or stored programs are actively running.

A session can set its own format if the user has privileges and the version permits:

~~~sql
SET SESSION binlog_format = 'ROW';
~~~

Session-level settings affect only changes logged from that session. They do not replace server-wide configuration when the goal is consistent replication behavior.

## 4. What does a row event contain?

When using RBR, the binary log contains the following main event types:

- **TABLE_MAP_EVENT** describes the involved table and column metadata needed to interpret row events.
- **WRITE_ROWS_EVENT** describes inserted rows.
- **UPDATE_ROWS_EVENT** contains the before-image and after-image of modified rows.
- **DELETE_ROWS_EVENT** contains the image of rows before deletion.

A single **UPDATE** statement may generate multiple row events if it updates many rows or the data is split across multiple events. With row-based logging, the original SQL text is not the primary content used to replay changes.

Reading a row-format binary log:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000123
~~~

Decoded output typically displays **###** annotations describing row operations. This is helpful for investigating changes, though it does not always show the full original SQL statement. You can enable **binlog_rows_query_log_events** to log additional informational query events for traceability in supported versions; these query events are informational only and do not replace row events.

## 5. Choosing binlog_row_image: FULL, MINIMAL, and NOBLOB

**binlog_row_image** controls how many columns MySQL writes into the row images of row events. This choice affects binary log size, event inspection capability, and compatibility with downstream tools.

| Value | Row image content | Characteristics |
|---|---|---|
| **FULL** | Writes all columns in the before-image and after-image as applicable to the event type | Easy to inspect, broad compatibility, can produce large logs |
| **MINIMAL** | Writes only columns needed to identify the row and modified columns | Saves space, but log-reading tools must understand minimal row images |
| **NOBLOB** | Writes all columns except unchanged BLOB/TEXT columns | Reduces log size when tables have large, rarely modified columns |

Example:

~~~sql
SET PERSIST binlog_row_image = 'FULL';
~~~

### FULL

For **UPDATE**, both the before-image and after-image contain all columns. For **DELETE**, the before-image contains the entire row; for **INSERT**, the after-image contains the entire row. This gives auditing or CDC tools full context, though it can significantly increase storage usage when tables have many large columns.

### MINIMAL

For **UPDATE**, the before-image contains the columns needed to identify the row; the after-image contains only the modified columns. For **DELETE**, the before-image contains the columns needed to identify the row. For **INSERT**, the after-image represents the inserted row data per row event rules.

If a table has a suitable primary key or unique key, MySQL can use that key to identify the row. Without a suitable unique key, it may have to log many or all columns in the before-image to locate the row. Thus, adding a proper primary key benefits both the data model and row-based replication's row lookup efficiency.

### NOBLOB

**NOBLOB** logs columns like **FULL**, except unchanged BLOB/TEXT columns. If a BLOB/TEXT column is updated, its value is still logged. This is useful when tables contain large content columns that most statements do not modify.

### Choosing based on requirements

- Use **FULL** when prioritizing compatibility, investigation clarity, and CDC tools requiring full before/after images.
- Consider **MINIMAL** when logs are too large and all downstream consumers are confirmed to support it.
- Consider **NOBLOB** if tables have large, mostly static BLOB/TEXT columns.

Do not change **binlog_row_image** solely to save disk space without checking consumers such as CDC, auditing, data sync tools, or analytics pipelines. Some consumers require full columns to reconstruct records or audit changes.

## 6. How does RBR handle triggers, stored programs, and DDL?

With row-based replication, triggers fire on the source when data-modifying statements execute. Changes made by triggers are also logged as row events and sent to the replica. The replica applies those row events without firing the triggers again for those events. This prevents triggers from running twice for the same change.

Stored procedures and functions are invoked on the source; data changes they perform are recorded in the active binary log format. The replica does not re-execute the procedure to reproduce the recorded row changes.

DDL statements such as **CREATE TABLE**, **ALTER TABLE**, **DROP TABLE**, and **CREATE VIEW** are still logged and applied as statement events, even when **binlog_format=ROW**. Therefore, RBR does not eliminate the requirement to keep source and replica schemas compatible. If DDL is executed differently on the two sides or manual edits are made on the replica, subsequent row events may fail to apply.

This is a key operational takeaway: row format protects the consistency of data changes, while object structures and DDL operations still require disciplined management.

## 7. Why can source and replica data diverge?

RBR reduces risks from non-deterministic statements, but it does not guarantee two servers stay identical under all circumstances. Common causes include:

1. Data on the replica was manually edited or written directly by an application.
2. The replica skipped transactions or was initialized from a backup at the wrong point in time.
3. Manual DDL caused table structure to differ from the source.
4. Replication filters excluded part of a database or table.
5. Hardware errors, storage corruption, or crashes prevented transactions from applying properly.
6. Operators skipped replication errors or restarted the stream after an incomplete data fix.
7. Configuration or plugin differences altered how objects are created or applied.

### Signs of data divergence

- Replica reports a duplicate key error when applying a row insert.
- Replica cannot find the row to update or delete.
- Row counts or checksums differ between source and replica.
- Application queries return different results when run against the two servers.
- Some tables fall out of sync even though the replication stream reports running.

Two common errors when applying row events:

- **1032 (HA_ERR_KEY_NOT_FOUND):** the replica cannot find the row to update or delete.
- **1062 (ER_DUP_ENTRY):** the replica inserts a row that violates a unique key because the row already exists.

These errors usually indicate that underlying data between source and replica has already diverged, or out-of-band changes occurred outside the replication stream. Never just skip the failing transaction to make the stream continue; doing so can create further divergence later.

## 8. Diagnosing row-based replication errors

### Checking replica status

On MySQL 8.0.22 and later:

~~~sql
SHOW REPLICA STATUS\G
~~~

On older releases, you may need:

~~~sql
SHOW SLAVE STATUS\G
~~~

Focus on:

- **Replica_IO_Running** and **Replica_SQL_Running**.
- **Last_IO_Errno**, **Last_IO_Error**, **Last_SQL_Errno**, **Last_SQL_Error**.
- **Source_Log_File**, **Read_Source_Log_Pos**.
- **Relay_Source_Log_File**, **Exec_Source_Log_Pos**.
- **Retrieved_Gtid_Set** and **Executed_Gtid_Set** when using GTID.

If multiple workers apply in parallel, also inspect worker status:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_worker;
~~~

On the source, inspect the corresponding binary logs:

~~~sql
SHOW BINARY LOGS;
SHOW MASTER STATUS;
~~~

In MySQL 8.4, use **SHOW BINARY LOG STATUS** instead of **SHOW MASTER STATUS**.

### Reading row events around the error position

Once you have identified the file and position from the error message, use **mysqlbinlog** to inspect the event:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv --start-position=12000 --stop-position=16000 mysql-bin.000123
~~~

Compare the table, primary key, before-image, and after-image against current data on both source and replica. If querying directly, use the exact primary key or unique key to inspect the affected row. Record the failing transaction/GTID before making any fix.

### Checking table structure

~~~sql
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;
~~~

Compare table definitions across both servers: column order, data types, lengths, signed/unsigned, charset, collation, generated columns, indexes, and keys. Differing DDL can prevent row events from mapping properly or produce incorrect outcomes.

## 9. Resolving data drift safely

When divergence between source and replica is detected, follow this sequence:

1. Record the error, file/position or GTID, table, and key of the affected row.
2. Determine whether the replica is still serving application reads; if there is risk of returning bad data, redirect reads or isolate per runbook.
3. Compare data and structure between source and replica.
4. Identify the root cause: direct writes, replication filters, mistimed backup, DDL drift, or skipped transactions.
5. Choose between targeted row repair or rebuilding the replica from a consistent backup.
6. Verify data after repair and restart replication from the exact right point.
7. Monitor until the replica catches up and re-verify consistency.

If only a few rows differ, a DBA can perform a controlled fix after understanding the exact target state and effects on foreign keys, triggers, and transactions. For widespread drift or when scope cannot be fully determined, rebuilding the replica from a fresh backup is usually more reliable.

Never use error-skipping actions like **sql_slave_skip_counter** or advance the executed GTID set arbitrarily. With GTID, skipping a transaction by marking it executed can leave data missing the corresponding change. Every skip decision requires transaction analysis, documented approval, and a data reconciliation plan.

## 10. Periodic consistency monitoring

Replication status reports transmission and apply progress, but does not prove every row of data is identical. Supplement with consistency checks:

- Compare row counts on critical tables.
- Compute checksums per table or key range to isolate discrepancies.
- Use consistency checking tools suited to your scale, load, and version.
- Monitor for direct writes on replicas.
- Audit replication filters and out-of-process DDL deployments.
- Retain check results to detect persistent drift.

On large systems, avoid running full-table comparisons during peak hours without load evaluation. Chunk by primary key, schedule off-peak, and throttle resources. A check must compare the same scope and a valid point in time; if the source is actively changing while the replica lags, differing counts do not necessarily indicate drift.

### Operational principles

- Do not allow applications to write directly to a replica unless the architecture intentionally supports multi-source or multi-primary.
- Never apply manual schema changes on a replica.
- Manage DDL through the same deployment pipeline and validate across all nodes.
- Ensure replicas have sufficient space for relay logs and required binary logs.
- Monitor worker errors and lag rather than watching a single lag metric.
- Periodically test restoring replicas from backup and re-verifying the replication stream.

## 11. Hands-on example: unsafe statement and row event

Suppose a queue table has many records in the **pending** state:

~~~sql
CREATE TABLE job_queue (
  job_id BIGINT PRIMARY KEY,
  status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL
) ENGINE=InnoDB;
~~~

An update statement touching 10 rows without an explicit sort can pick different rows if re-executed on two servers:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
LIMIT 10;
~~~

In a statement-format environment, the statement may be flagged unsafe because the row selection order is non-deterministic. With mixed format, MySQL can log row events instead of a statement event upon detecting this case. With row format, the replica receives the exact rows the source updated.

You can rewrite the statement for more stable selection:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
ORDER BY job_id
LIMIT 10;
~~~

The **job_id** key is unique, making the selection order deterministic. Even so, when multiple sessions modify the table concurrently, transaction isolation and locking still determine which rows match at execution time. RBR ensures the replica receives the exact final outcome produced by the source.

## 12. Deployment and troubleshooting checklist

**Before choosing a binlog format**

- [ ] Assessed workload and reliance on statement determinism.
- [ ] Checked **binlog_format** at both global and session levels.
- [ ] Evaluated binary log storage growth when switching to ROW.
- [ ] Checked replication filters and downstream consumers.
- [ ] Selected a row image matching CDC/audit requirements.

**When operating RBR**

- [ ] Source and replica have compatible schemas.
- [ ] Every critical table has a primary key or suitable unique key.
- [ ] No unintended application writes go directly to replicas.
- [ ] Triggers and stored programs are deployed consistently.
- [ ] Binary logs and relay logs have adequate disk space.

**When encountering errors or suspecting data drift**

- [ ] Recorded error details, file/position, or GTID.
- [ ] Checked I/O thread and applier worker status.
- [ ] Decoded row events around the error position.
- [ ] Compared structure and row data for the affected records.
- [ ] Identified root cause before repairing or skipping transactions.
- [ ] Verified consistency after remediation and confirmed the replica caught up.

## Conclusion

Row-based replication records the actual rows changed on the source, avoiding many discrepancies caused by non-deterministic statements replaying on replicas. **binlog_format=ROW** is generally the right choice for modern MySQL; **binlog_row_image** determines row event detail and should match recovery, investigation, and downstream consumer needs. RBR still requires compatible schemas, consistent DDL processes, and data drift monitoring. When a replica hits error 1032 or 1062, investigate the row events and data state before deciding whether to repair rows or rebuild the replica.
