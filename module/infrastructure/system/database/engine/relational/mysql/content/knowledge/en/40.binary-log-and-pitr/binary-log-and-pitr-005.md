# Inspecting Binary Logs with mysqlbinlog and Decoding Row Events

The binary log records data changes and events needed for MySQL replication or point-in-time recovery (PITR). When you need to investigate a transaction, pinpoint when data was modified, or prepare to replay logs after restoring a backup, the primary tool for reading binary logs is `mysqlbinlog`.

When logs are written in `ROW` format, changes are stored as row events rather than the original SQL statements. `mysqlbinlog` can decode these events into a readable representation so administrators can inspect values before and after updates. The decoded output is an analytical representation; it does not reconstruct the exact SQL statement that the application sent.

This lesson uses MySQL 8.0/8.4 and a `mysqlbinlog` utility version compatible with the server. Some options and event formats may vary across releases; check `mysqlbinlog --help` and the documentation for your exact version when operating a specific system.

## Objectives

After this lesson, you will be able to:

- Verify whether binary logging is enabled, list log files, and read event positions.
- Use `mysqlbinlog` to inspect local logs or read logs from a remote server.
- Decode `WRITE_ROWS`, `UPDATE_ROWS`, and `DELETE_ROWS` using `--base64-output=DECODE-ROWS` and `-vv`.
- Understand the relationship between GTID, `TABLE_MAP`, row events, and transaction boundaries.
- Read `@N`, before/after update values, and the effect of `binlog_row_image`.
- Filter logs by position, time, or GTID and avoid common mistakes when preparing for PITR.

## 1. What Does the Binary Log Store?

The binary log is a sequence of files written by the MySQL server when binary logging is enabled. It serves replication, data-change-level auditing, and recovery by replaying changes after a backup. The binary log is not a full backup: it contains only the events recorded over the corresponding period and must be paired with an appropriate backup to recover data.

Check status and configuration on the server:

```sql
-- Check whether binary logging is enabled.
SHOW VARIABLES LIKE 'log_bin';

-- View the list of existing binary log files.
SHOW BINARY LOGS;

-- View the current log file and write position (MySQL 8.4).
SHOW BINARY LOG STATUS;

-- Check the log format and row image recording mode.
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
```

`SHOW BINARY LOG STATUS` is the current syntax in MySQL 8.4; on older versions, documentation may use `SHOW MASTER STATUS`. Enabling binary logging must be configured at server startup, typically via `log_bin` in the configuration file. If `log_bin` is `OFF`, no new binary logs are written to read.

Logging formats:

| Format | Main content | Characteristics |
|---|---|---|
| `STATEMENT` | SQL statements | Logs data-modifying statements; requires attention to determinism and state-dependent functions. |
| `ROW` | Per-row changes | Logs row events; suited for replication and decoding data changes. |
| `MIXED` | Combination of statement and row | MySQL chooses the format based on statement type and safety conditions. |

In modern MySQL systems, `ROW` is the common choice and the default in many MySQL 8.x configurations. `binlog_format` has been marked deprecated in newer MySQL 8.0 releases; check the documentation for your exact version before relying on switching to `STATEMENT` or `MIXED`. Even with row-based logging, DDL statements such as `CREATE TABLE` or `ALTER TABLE` are still logged as statements.

## 2. Event Structure Within a Transaction

A row-based transaction typically contains a sequence of events. The names below are common types; concrete names may carry version suffixes such as `WRITE_ROWS_EVENTv2`.

| Event | Role |
|---|---|
| `GTID_LOG_EVENT` or `ANONYMOUS_GTID_LOG_EVENT` | Identifies the transaction by GTID or as an anonymous transaction. |
| `QUERY_EVENT` | Contains statements such as `BEGIN`, DDL, or statement-logged queries. |
| `TABLE_MAP_EVENT` | Maps the table ID in row events to the database, table, and column metadata. |
| `WRITE_ROWS_EVENT` | Records inserted rows (`INSERT`). |
| `UPDATE_ROWS_EVENT` | Records before and after images of updated rows (`UPDATE`). |
| `DELETE_ROWS_EVENT` | Records images of deleted rows (`DELETE`). |
| `XID_EVENT` | Marks the commit of a transactional transaction. |

A simple flow can be visualized as follows:

```text
GTID
  |
BEGIN (QUERY_EVENT)
  |
TABLE_MAP (db.orders)
  |
WRITE_ROWS / UPDATE_ROWS / DELETE_ROWS
  |
XID (COMMIT)
```

`TABLE_MAP` is critical: row events reference a table ID rather than repeating the table name and full column definitions in every event. `TABLE_MAP` supplies the information needed to decode row events against the right table. If a transaction touches multiple tables, multiple pairs of `TABLE_MAP` and row events may appear.

With InnoDB, transactional changes usually end with an `XID_EVENT`. A transaction may span multiple row events yet commit as a single unit. When reading logs for investigation or recovery, identify transaction boundaries; replaying a partial subset of events mid-transaction can leave an inconsistent state.

## 3. Reading Local Binary Logs with `mysqlbinlog`

`mysqlbinlog` is typically installed alongside the MySQL client utilities. On a machine holding the log files, the basic command is:

```bash
mysqlbinlog binlog.000123
```

The output may include comment lines and Base64-encoded `BINLOG` statements. To read row events in a more understandable form, use:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

Two key options:

- `--base64-output=DECODE-ROWS` instructs the tool to display row events in decoded form instead of printing only Base64 payloads.
- `-vv` enables `--verbose` twice; it prints additional column type metadata and nullability details to help interpret values.

You can redirect output to a text file for searching and comparison:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123 > binlog-decoded.txt
```

`DECODE-ROWS` output usually presents row changes as comment lines starting with `###`. These lines are an interpretive display for reading; they are not directly executable SQL statements. If you need to preserve Base64 payloads for replay, use an appropriate default output mode and keep the original log files separate.

### 3.1. Reading Event Positions and Timestamps

In `mysqlbinlog` output, pay attention to lines such as:

```text
# at 1842
# ... server id 12  end_log_pos 1937  CRC32 0x...
```

- `# at 1842` is the starting byte offset of the event in the file.
- `end_log_pos 1937` is the offset immediately following the event according to log metadata.
- The timestamp in the header indicates when the event was recorded; when correlating with application logs, account for time zones and clock skew across machines.

Positions are byte offsets within the binary log file, not transaction sequence numbers. When isolating a transaction, locate its GTID/BEGIN event, its row events, and its commit event. Record both the filename and the position, since positions are only meaningful within that specific file.

### 3.2. Quick Event Inspection with SQL

You can use `SHOW BINLOG EVENTS` to inspect a basic event list:

```sql
SHOW BINLOG EVENTS IN 'binlog.000123' FROM 4 LIMIT 30;
```

This statement is useful for viewing event types, positions, and summary info. It does not fully decode row-event values; use `mysqlbinlog -vv` when you need to inspect row contents. On large log files, avoid unbounded queries because reading all events can consume heavy resources and produce massive output.

## 4. Decoding Row Events

Suppose the application performs the following operations:

```sql
INSERT INTO sales_db.orders (order_id, status, total)
VALUES (501, 'NEW', 125000);

UPDATE sales_db.orders
SET status = 'PAID'
WHERE order_id = 501;

DELETE FROM sales_db.orders
WHERE order_id = 501;
```

With `binlog_format=ROW`, MySQL records the row changes. When running `mysqlbinlog --base64-output=DECODE-ROWS -vv`, illustrative output looks like:

```text
### INSERT INTO `sales_db`.`orders`
### SET
###   @1=501 /* INT meta=0 nullable=0 is_null=0 */
###   @2='NEW' /* VARSTRING(...) ... */
###   @3=125000 /* DECIMAL(...) ... */

### UPDATE `sales_db`.`orders`
### WHERE
###   @1=501 /* INT ... */
###   @2='NEW' /* VARSTRING(...) ... */
###   @3=125000 /* DECIMAL(...) ... */
### SET
###   @2='PAID' /* VARSTRING(...) ... */

### DELETE FROM `sales_db`.`orders`
### WHERE
###   @1=501 /* INT ... */
```

This is a simplified example illustrating structure, not a verbatim copy of every version's output. `@1`, `@2`, `@3` denote column positions in the table definition order at the time the event was written:

- `INSERT` uses `### SET` to display the values of the inserted row.
- `UPDATE` uses `### WHERE` for the pre-update row image and `### SET` for the post-update row image.
- `DELETE` uses `### WHERE` to display the deleted row image.

Data type annotations such as `INT`, `DECIMAL`, `VARSTRING`, `meta`, `nullable`, and `is_null` help clarify how values are decoded. Depending on column type and tool version, values may appear as strings, numbers, `NULL`, binary representations, or type-specific formats.

### 4.1. Why Does `mysqlbinlog` Use `@1`, `@2` Instead of Column Names?

Row events store values by column ordinal, and `TABLE_MAP` supplies metadata for decoding. Verbose output typically numbers columns `@1`, `@2`, ... rather than always displaying column names. To determine whether `@2` is `status` or another column, match it against the table definition active at the time the event was generated:

```sql
SHOW CREATE TABLE sales_db.orders\G
```

Never assume the current schema matches the schema when the event was written. If the table subsequently underwent `ALTER TABLE`, column order or types may have changed. Use a schema snapshot from backups or migration metadata corresponding to the point under analysis. When the server is configured with `binlog_row_metadata=FULL`, the binary log can include extra column metadata; `MINIMAL` metadata stores less detail. Full metadata still does not replace cross-checking the exact schema version.

### 4.2. Row Images and `binlog_row_image`

`binlog_row_image` controls how many columns MySQL writes into row events:

| Value | Content |
|---|---|
| `FULL` | Records the full row image. For `UPDATE`, includes full before and after images. |
| `MINIMAL` | Records only columns needed to identify the row and columns that changed. |
| `NOBLOB` | Records nearly all columns, but may omit unchanged BLOB/TEXT columns. |

With `MINIMAL`, the before image of `UPDATE`/`DELETE` retains the columns needed to locate the row, usually based on a primary key or suitable unique key; the after image of `UPDATE` only needs changed columns. Consequently, when decoding, you may not see all old values or the entire row. This behavior is intentional to reduce binary log size.

Check configuration:

```sql
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
```

If you need to investigate changes with full row images, check the configuration in effect when the logs were generated. Changing `binlog_row_image` today cannot retroactively add columns that were never written to older log files. In production, choosing `FULL` vs. `MINIMAL` requires balancing investigability, log size, storage, and replication requirements.

## 5. Reading Binary Logs from a Remote Server

When log files reside on the database server, `mysqlbinlog` can read them directly over a client/server connection:

```bash
mysqlbinlog \
  --read-from-remote-server \
  --host=db.example.internal \
  --port=3306 \
  --user=binlog_reader \
  --password \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

Pass `--password` without a value so the utility prompts interactively. Never pass passwords directly on the command line, as they can leak via shell history or process listings. The account reading logs needs replication privileges appropriate to your MySQL version and operation. When connecting over a network, enable TLS and verify server certificates per your security policy.

If your goal is to download the raw binary log files to an analysis machine, combine `--raw` with `--read-from-remote-server`:

```bash
mysqlbinlog \
  --read-from-remote-server --raw \
  --host=db.example.internal \
  --user=binlog_reader --password \
  --result-file=/secure/binlog-copy/ \
  binlog.000123
```

In `--raw` mode, the utility saves raw log files instead of printing decoded text to stdout. The target directory must exist and the OS account needs write permissions. Protect downloaded logs like sensitive data: row events can contain customer details, transactions, or personal information.

## 6. Filtering the Log Range to Inspect

A binary log file can hold millions of events. Narrowing the range speeds up analysis and avoids misreading unrelated transactions.

### 6.1. Filtering by Position

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS -vv \
  --start-position=1842 \
  --stop-position=5200 \
  binlog.000123
```

`--start-position` and `--stop-position` take byte offsets within the log file. Obtain offsets from event headers in that exact file and pick transaction boundaries. Do not use estimated offsets inside an event or partway through a transaction's events. For recovery, record the exact filename, start position, and stop position so the process is reproducible.

### 6.2. Filtering by Time

```bash
mysqlbinlog \
  --start-datetime='2026-11-19 09:00:00' \
  --stop-datetime='2026-11-19 09:30:00' \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

Filtering by time is convenient when the incident window is known. However, event timestamps do not replace verifying positions and transaction boundaries. Check time zones on the server, the host running `mysqlbinlog`, and the application tier before choosing timestamps; transactions near the boundaries may require extra inspection.

### 6.3. Filtering by GTID

When GTID is enabled, you can select transactions by GTID set:

```bash
mysqlbinlog \
  --include-gtids='3E11FA47-71CA-11E1-9E33-C80AA9429562:1-120' \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

`--include-gtids` keeps only transactions belonging to the GTID set; `--exclude-gtids` omits transactions in the specified set. A GTID set consists of SIDs (source UUIDs) and transaction number ranges. Obtain GTIDs from trusted sources such as replication logs or backup metadata—never guess SIDs or numeric ranges.

### 6.4. Filtering by Database

```bash
mysqlbinlog --database=sales_db --base64-output=DECODE-ROWS -vv binlog.000123
```

`--database` behaves differently depending on `binlog_format`. With statement-based logging, filtering relies on the session's default database; with row-based logging, filtering relies on the database of row events. DDL and cross-database statements can behave differently than expected. Therefore, do not rely on `--database` as your sole safety boundary during critical recovery; inspect the log contents and execution plan carefully.

## 7. Analyzing an `UPDATE` Transaction

The following practical workflow helps locate a specific change:

1. Identify the log files covering the suspect timeframe using `SHOW BINARY LOGS` and backup/replication metadata.
2. Run `mysqlbinlog --base64-output=DECODE-ROWS -vv` to decode the relevant file or position range.
3. Locate the database/table name under `### UPDATE` and identify the corresponding `TABLE_MAP`.
4. Map `@N` columns against the schema active when the event was logged.
5. Read `### WHERE` as the pre-change row image and `### SET` as the post-change row image; note that `binlog_row_image` may omit unchanged columns.
6. Find the GTID and commit event to identify the transaction containing the change.
7. Correlate timestamps, application accounts, audit logs, and business logs to determine the root cause.

You cannot reliably deduce the exact original SQL statement from row events alone. For instance, many different statements can produce the same row change; row events show the resulting data state written, not the full query, predicates, application variables, or user intent. To trace the original statement, you also need the general log (if enabled), audit logs, tracing, or application logs.

## 8. Using `mysqlbinlog` in a PITR Workflow

PITR generally has two phases: restore a full backup taken prior to the incident, then replay binary logs from the backup point up to immediately before the erroneous transaction. `mysqlbinlog` helps select ranges and export logs for application; it does not automatically choose the right backup or decide which transactions are safe.

General workflow:

```text
Full backup at T0
       |
       v
Restore backup to target environment
       |
       v
Identify binlog file + position or GTID at T0
       |
       v
Read and filter binlogs from T0 until before the erroneous transaction
       |
       v
Verify range and transaction boundaries
       |
       v
Apply logs to the restored environment
       |
       v
Reconcile data and verify results
```

Example exporting a log range for preview:

```bash
mysqlbinlog \
  --start-position=120 \
  --stop-position=9800 \
  binlog.000123 > replay-candidate.sql
```

For actual replay, the workflow normally pipes appropriate `mysqlbinlog` output to the `mysql` client connected to the restored server. Before doing so, verify:

- The backup and binary logs belong to the same data lineage with no missing intermediate log files.
- The starting file/position or GTID matches the backup metadata.
- The stop point sits before the erroneous transaction and does not cut across a transaction that must be kept.
- Selected events do not affect unintended scopes, especially where DDL or multiple databases are involved.
- The target server was restored cleanly and a safe copy exists to roll back if needed.

Do not replay a file generated with `--base64-output=DECODE-ROWS` as if it were recovery SQL. Decoded row events are rendered as `###` comments for human reading. When replay is required, generate output in the appropriate mode that preserves the necessary `BINLOG` statements and apply it following a tested PITR procedure.

## 9. Common Errors and Troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| Log file not found | Wrong directory, wrong filename, or log was purged | Check `SHOW BINARY LOGS`, `log_bin_basename`, and retention policy. |
| Cannot read remote logs | Wrong host/port, insufficient replication privileges, or invalid TLS | Check connectivity, account, privileges, and TLS configuration. |
| Only Base64 shown, no row values | Row-event decoding mode not enabled | Use `--base64-output=DECODE-ROWS -vv`. |
| Only a subset of columns shown | `binlog_row_image=MINIMAL` or `NOBLOB` | Check the configuration in effect when the event was logged. |
| Unsure which column `@2` is | Missing point-in-time schema | Compare against `SHOW CREATE TABLE` from a matching schema snapshot or backup. |
| Original `UPDATE` SQL not visible | Log uses row-based format | Consult audit, general, or application logs if collected. |
| Replay errors or wrong data | Wrong start point, missing log file, split transaction, or schema mismatch | Verify backup metadata, GTID/positions, and transaction boundaries. |
| Log file huge or overwhelming output | Reading entire file or unnecessary hexdump | Narrow by position, time, or GTID; use `--hexdump` only for byte-level analysis. |

Other useful options:

```bash
# Verify event checksums while reading a log file.
mysqlbinlog --verify-binlog-checksum binlog.000123

# Display a hexdump for byte-level data investigation.
mysqlbinlog --hexdump binlog.000123

# View syntax and options supported by your installation.
mysqlbinlog --help
```

`--hexdump` is intended for deep analysis and can produce massive output. Use it only when inspecting byte structure or debugging decoding errors. Never edit a binary log directly; if a file is corrupted, keep the original intact for investigation and recover from a reliable copy.

## 10. Safe Operating Principles

1. **Retain binary logs long enough.** Retention must cover the backup window, replication lag, and PITR target. Purging logs prematurely can destroy recoverability.
2. **Store backup metadata.** Record binlog file/position or GTID at backup time so you know where replay starts.
3. **Protect log files.** Binary logs can contain sensitive data; restrict read access, encrypt storage, and control copies.
4. **Use compatible tools.** Prefer `mysqlbinlog` of the same version or a version officially supported by MySQL for the source log format.
5. **Keep transactions intact.** Pick start/stop positions at proper event boundaries and verify the final retained transaction.
6. **Align schema with time.** Never use the current schema to interpret old events if the table structure changed.
7. **Distinguish reading from replaying.** Decoded row-event output for reading is not a replay script.
8. **Test PITR in isolation.** Verify restored data before promoting results to production.

## 11. Self-Check Exercises

1. Why cannot `SHOW BINLOG EVENTS` replace `mysqlbinlog -vv` when you need to inspect row values?
2. In row-event output, what do `### WHERE` and `### SET` represent for an `UPDATE`?
3. If `binlog_row_image=MINIMAL`, why might only the primary key and changed columns appear?
4. An event shows `@3='PAID'`. What information source do you need to know `@3` is the `status` column?
5. Why should you not use `--base64-output=DECODE-ROWS` output as a PITR replay script?
6. When filtering by time, what factors can cause you to pick the wrong transaction boundary?

**Answer hints:** (1) `SHOW BINLOG EVENTS` only lists summary event info; `mysqlbinlog -vv` decodes row-event payloads. (2) `WHERE` is the pre-update row image used to identify/represent the old row; `SET` holds post-update values. (3) `MINIMAL` records only columns needed to identify the row and changed columns to save log space. (4) A schema snapshot accurate at the time the event was logged, with matching column order. (5) Decoded output formats row events as comments for reading and omits the replay payloads needed for execution. (6) Time zones, clock skew, timestamp resolution, and transactions spanning the time boundary.

## References

- [MySQL 8.4 Reference Manual: mysqlbinlog — Utility for Processing Binary Log Files](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog.html)
- [MySQL 8.4 Reference Manual: mysqlbinlog Row Event Display](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog-row-events.html)
- [MySQL 8.4 Reference Manual: Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual: Binary Log Options and Variables](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html)
