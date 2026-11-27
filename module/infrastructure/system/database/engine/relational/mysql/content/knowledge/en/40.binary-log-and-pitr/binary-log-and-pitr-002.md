# Statement-Based, Row-Based, Mixed Format, and Version Conditions

## Objectives

After this lesson, you will be able to:

- Explain how `STATEMENT`, `ROW`, and `MIXED` record changes into the binary log.
- Compare the safety, log volume, performance, and inspectability of each format.
- Identify statements that are unsafe for statement-based logging and understand when mixed format switches to row events.
- Distinguish `binlog_format` from `binlog_row_image` and other binary log settings.
- Inspect the running format, read events using `mysqlbinlog`, and plan format changes appropriate for your MySQL version.
- Evaluate compatibility across source, replica, storage engine, and point-in-time recovery (PITR) tools.

## 1. What Does the Binary Log Record?

The binary log (binlog) is a log of events that can modify data or database structure. MySQL uses the binlog for two main purposes:

- **Replication:** the source sends events from the binlog to replicas so that replicas apply and reproduce the changes.
- **Point-in-time recovery (PITR):** after restoring a baseline backup, operators replay the binlog up to a desired point in time or position.

The logging format determines whether MySQL stores the **executed SQL statements**, **per-row changes**, or a combination of both. It affects binlog size, consistency when replicas apply changes, inspectability, and log replay duration.

The three traditional formats are:

- `STATEMENT` — statement-based logging (SBL/SBR).
- `ROW` — row-based logging (RBL/RBR).
- `MIXED` — mixed-format logging, combining statement and row.

The format only takes effect when binary logging is enabled (`log_bin=ON`). Choosing `ROW` does not automatically enable the binlog if the server was started with binary logging disabled.

## 2. Statement-Based Logging (SBR)

With `STATEMENT`, MySQL records the SQL statement that modifies data into the binary log. The replica reads that statement and re-executes it against its own data.

Example on the source:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
```

A statement-based binlog stores the `UPDATE` statement (along with necessary event metadata and execution context), rather than recording each modified row. The replica executes the corresponding statement against its `inventory` table.

### 2.1. Advantages

- **Logs can be smaller:** an `UPDATE` affecting millions of rows may still only need one statement plus metadata to be recorded. This can reduce log size and transfer time when modifying many rows.
- **Readable and inspectable:** SQL events express operational intent, which is useful during investigation or auditing.
- **Replicas execute the statement:** a statement can take advantage of the replica's index structure and data organization during execution.

### 2.2. Determinism Risks

SBR requires a statement to produce equivalent results on both the source and the replica. If the outcome depends on data, ordering, session state, environment, or non-deterministic functions, the same statement can yield different results.

Dangerous example:

```sql
UPDATE jobs
SET priority = priority + 1
WHERE status = 'PENDING'
LIMIT 10;
```

Without `ORDER BY`, the set of 10 selected rows can differ if access order or execution plans differ between the source and replica. A more deterministically ordered way to write this:

```sql
UPDATE jobs
SET priority = priority + 1
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 10;
```

Even with `ORDER BY` added, you must ensure the sort criteria produce a unique ordering (for example, `job_id` is a unique key). If multiple rows tie without a tie-breaker column, the result can still be non-deterministic.

Common functions and situations that are typically unsafe with SBR include:

| Case | Why there is risk |
|---|---|
| `UUID()` and `UUID_SHORT()` | Generated values differ between source and replica |
| `RAND()` | Random values may differ when the statement runs again |
| `SYSDATE()` | Depends on execution time; an exception exists when `--sysdate-is-now` is configured consistently |
| `USER()` or certain identity functions | Connection identity on the replica may differ from the source |
| `LOAD_FILE()` | Result depends on files on each server's filesystem |
| `UPDATE`/`DELETE` with `LIMIT` lacking stable ordering | Source and replica may select different rows |
| Non-deterministic stored program or loadable function | Outcome may depend on state outside input parameters |

Not every time-related function is unsafe. For example, MySQL records the statement's timestamp so `NOW()` can yield the same value when the statement is replayed; `SYSDATE()` follows different rules and must be evaluated separately.

This list is representative, not exhaustive. MySQL has mechanisms to detect certain unsafe statements and emit warnings such as `Statement is not safe to log in statement format`. You can inspect warnings immediately after a statement using:

```sql
SHOW WARNINGS;
```

You should not treat MySQL issuing a warning as an automatic data-fixing mechanism. Under SBR, an unsafe statement can cause replica data to drift from the source. In addition, the replica must have sufficiently compatible table structures and execution context for the statement to yield the same result.

## 3. Row-Based Logging (RBR)

With `ROW`, MySQL writes events describing which rows were inserted, updated, or deleted. The replica applies the recorded row changes without needing to re-execute the original DML statement.

For example, the source runs:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
```

With RBR, the binlog contains events indicating which row(s) in `inventory` changed and the corresponding before/after row data according to the row image configuration. The replica applies the row values recorded in the event. Even if the original statement contained a non-deterministic expression, the replica still receives the exact row changes produced on the source.

### 3.1. Advantages

- **High consistency:** replicas apply specific row changes, reducing risks from random functions, local data, or differences in statement execution.
- **Suitable for complex operations:** data-modifying statements can be executed once on the source; replicas receive the resulting changed rows.
- **Reduces certain lock contention on replicas:** replicas do not have to re-run the entire DML query to locate affected rows.
- **Useful for PITR:** row changes are explicitly recorded, supporting accurate replay of committed results when the log chain is valid.

### 3.2. Costs and Limitations

- **Logs can become large:** an `UPDATE` modifying millions of rows can generate a huge number of row events, whereas SBR only records the statement.
- **Higher storage and transfer overhead:** larger logs can increase I/O, archive storage usage, replication bandwidth, and PITR duration.
- **Harder to read directly:** binary events do not appear as the original SQL statements. `mysqlbinlog` can be used to decode row descriptions.
- **Some operations still use statement events:** RBR does not mean every event in the binlog is a row event. DDL statements such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` are still logged as statements. Privilege statements such as `GRANT` and `REVOKE`, as well as creating/dropping triggers, routines, and views, also follow statement-logging rules. For `CREATE TABLE ... SELECT`, table creation is logged as a statement while inserted rows may be logged as row events.

### 3.3. Reading Row Events

To view row changes in a more readable form:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /var/lib/mysql/binlog.000123
```

The `-vv` option displays row information as comment lines such as `### UPDATE`, `### WHERE`, and `### SET`. This is an inspection representation; it is not the original SQL executed on the source. Do not strip the comments and assume the remainder is an executable regular SQL script.

If you need to know the original application statement for investigation, consider enabling `binlog_rows_query_log_events` based on your version and operational requirements. This extra event allows `mysqlbinlog -vv` to display the query associated with row events, though it increases logged volume and does not change how RBR applies data.

## 4. Mixed-Format Logging

With `MIXED`, MySQL defaults to logging statement events and automatically switches to row-based logging when it detects a statement or situation where only row logging ensures an appropriate result.

For example, the following statement generates different UUID values if executed separately on two machines:

```sql
INSERT INTO request_log(request_id, message)
VALUES (UUID(), 'payment received');
```

In mixed format, MySQL switches this operation to row events so the replica receives the exact UUID generated on the source. Other safe statements can continue to be logged as statements.

Conditions that can cause MySQL to switch to row format include:

- The statement uses `UUID()` or certain other unsafe functions.
- `AUTO_INCREMENT` is involved and a trigger or stored function is invoked in a relevant context.
- A view or stored program contains logic requiring row-based logging.
- Use of loadable functions, `FOUND_ROWS()`, `ROW_COUNT()`, `USER()`, `CURRENT_USER()`, `LOAD_FILE()`, or certain system variables in the statement.
- A storage engine type or operation type unsuitable for statement logging.

Exact conditions depend on the MySQL version, storage engine, and statement type. Read the documentation for your running version and inspect actual warnings/events. `MIXED` is not a guarantee that every possible non-deterministic statement will be detected in every conceivable case.

The advantage of mixed format is combining compact statement logs with row safety in cases MySQL recognizes. The drawback is that the actual format varies per statement; estimating capacity and inspecting the binlog requires understanding both event types. Furthermore, `binlog_format` is deprecated in recent MySQL versions, so mixed is not a recommended choice for new systems.

## 5. Comparing the Three Formats

| Criterion | `STATEMENT` | `ROW` | `MIXED` |
|---|---|---|---|
| Primary content | SQL statements | Individual row changes | Statements, auto-switching to row when needed |
| Data drift risk from non-deterministic functions | High if statements are unsafe | Lower because row results are recorded | Reduced by switching recognized cases |
| Log size | Usually small for multi-row changes | Can be large when many rows change | Depends on how statements are logged |
| Human readability | Better | Requires decoding row events | Combination of both |
| Impact when replica applies | Must re-execute the statement | Applies row changes | Depends on event type |
| PITR and investigation | SQL intent can be read directly | Changed row values can be inspected | Must understand both statement and row events |
| Usage guidance | Maintain only for clear compatibility reasons | Recommended choice for new systems | Primarily for understanding and maintaining legacy systems |

No format replaces testing replication and restore. For most modern MySQL systems, `ROW` is the appropriate choice because it prioritizes change consistency. If heavy update volumes cause the binlog to grow quickly, measure capacity and tune `binlog_row_image`, retention, log shipping, and storage before considering reverting to statement logging.

## 6. Distinguishing `binlog_format` and `binlog_row_image`

These two settings are often confused:

- `binlog_format` selects how events are recorded: `STATEMENT`, `ROW`, or `MIXED`.
- `binlog_row_image` determines how much column data is recorded in row events when using row-based logging.

Common values of `binlog_row_image`:

| Value | Content recorded for row events |
|---|---|
| `FULL` | Records full before/after row images depending on operation type; easier to inspect and recover in many scenarios |
| `MINIMAL` | Records only columns needed to identify the row and columns that changed; reduces log size |
| `NOBLOB` | Records columns, omitting certain unchanged BLOB/TEXT columns per MySQL rules |

Inspection example:

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
```

`MINIMAL` can significantly reduce binlog volume, but makes reading and extracting certain changes harder. For `UPDATE` or `DELETE` operations, MySQL and replicas need enough information to identify the exact row. When using `MINIMAL` or `NOBLOB`, table structures on both sides must be compatible in column count/order, data types, and primary key definitions per MySQL's requirements; otherwise, replicas or consumers may fail to locate the right row. Do not change the row image solely for smaller logs without checking audit, CDC, PITR workflows, and downstream tools.

## 7. Checking the Format and Viewing the Binlog

### 7.1. Checking server configuration

Run the following queries with an account permitted to read system variables and binlog status:

```sql
SELECT VERSION() AS mysql_version;

SHOW VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW SESSION VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_image';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_metadata';
```

Distinguish between global and session variables. Global values affect new sessions according to the variable's scoping rules; the current session may still retain its own value. Consequently, `SHOW SESSION VARIABLES` and `SHOW GLOBAL VARIABLES` can return different results.

To view binlog files and events:

```sql
SHOW BINARY LOGS;
SHOW BINLOG EVENTS IN 'binlog.000123' LIMIT 20;
```

To get the current binlog position, choose the command according to version:

```sql
-- MySQL 8.0
SHOW MASTER STATUS;
```

```sql
-- MySQL 8.2 and later
SHOW BINARY LOG STATUS;
```

The new name `SHOW BINARY LOG STATUS` was introduced in MySQL 8.2; MySQL 8.4 removed `SHOW MASTER STATUS`. `SHOW BINLOG EVENTS` output helps inspect event types, positions, and filenames, though it does not replace detailed decoding tools.

### 7.2. Reading logs with `mysqlbinlog`

View event contents in text form:

```bash
mysqlbinlog --start-position=4 \
  /var/lib/mysql/binlog.000123
```

The example above reads a rotated binlog file or a copy of a log. If the log uses row format, add `--base64-output=DECODE-ROWS -vv` to view row descriptions. If you need to follow a remote binlog that is actively being written, use remote server reading mode and `--stop-never` per the `mysqlbinlog` documentation. If using GTID or time-based PITR, determine exact transaction boundaries and the stop event before replaying.

Do not test-run `mysqlbinlog | mysql` directly on production without verifying the stop point and impact scope. Replay onto an isolated recovery server first, verify the data, and only then plan how to apply results to the primary environment.

## 8. MySQL Version Conditions

Default formats and support status vary by version. When upgrading or connecting a source and replica on different versions, read the corresponding documentation rather than inferring from an older server's configuration.

| Version / platform | Default and notes |
|---|---|
| Before MySQL 5.7.7 | `STATEMENT` is the default; verify actual configuration when upgrading |
| MySQL 5.7.7 and later | `ROW` is the default; binary logging is not enabled by default in MySQL 5.7 unless `--log-bin` is configured |
| MySQL 8.0 | Binary logging is enabled by default in standard configurations and the default format is `ROW` |
| MySQL 8.0.34 and later | `binlog_format` and changing the format are deprecated; reading/setting the variable may emit warnings. Oracle recommends row-based for new replication |
| MySQL 8.4 | Documentation still lists `STATEMENT`, `ROW`, and `MIXED` as valid values for the deprecated variable; default is `ROW`. Legacy systems should migrate to row-based and avoid relying on formats scheduled for removal |
| MySQL NDB Cluster | Has specific rules: default may be `MIXED`; statement-based replication is not supported for NDB tables. Follow the corresponding NDB Cluster documentation |

Important point: in MySQL 8.0.34, `binlog_format` was deprecated rather than immediately removed. MySQL 8.4 documentation still lists all three values while warning that the variable may be removed in a future release. Do not build an upgrade plan assuming 8.4 has already removed `STATEMENT` and `MIXED`; check the release notes for the exact installed server version.

MySQL 8.0 also changes certain replication behaviors and metadata across minor releases. Therefore, when upgrading across multiple version branches, check release notes, replication compatibility matrices, and step-by-step upgrade requirements. An older replica may fail to understand new events or metadata produced by a newer source, even if both support `ROW`.

## 9. Source, Replica, and Storage Engine Compatibility

The source writes events according to its configuration and storage engine capabilities. The replica must be able to apply the received event types. Points to check:

- **Format on the replica:** the replica reads event types sent by the source automatically. However, if the replica writes its own binlog for downstream replication (`log_replica_updates`), the replica's format configuration must be compatible with the events it receives and emits.
- **Cannot convert ROW to STATEMENT:** a replica cannot automatically convert row events received from a source into SQL statements for downstream logging. If the source emits row events, the replica needs `ROW` or `MIXED` for the corresponding downstream logging stream.
- **Changing format while replication is running:** switching the source from `STATEMENT` to `ROW` while a replica remains on `STATEMENT` can cause replication errors. A safe procedure requires stopping replication, changing configuration appropriately on both source and replica, then restarting and verifying per version guidelines.
- **Isolation level:** with InnoDB and `READ COMMITTED` or `READ UNCOMMITTED` isolation levels, only row-based logging can be used safely per MySQL limitations. Attempting to switch to `STATEMENT` can lead to errors during data writes.
- **DDL:** even with `binlog_format=ROW`, statements like `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` are still logged as statements. Examine both event type and context when analyzing binlogs.
- **Different storage engines:** some engines restrict which formats can be used. NDB Cluster has specific rules and does not support SBR for NDB tables.
- **Schema:** under SBR, source and replica structures must be nearly identical so statements have the same meaning. Under RBR, differences in column order, data types, keys, and table definitions can still cause row application errors or failures.

Do not use changing `binlog_format` as a workaround for replication lag or schema errors. Identify the actual root cause from applier status, error logs, event types, and version compatibility.

## 10. Controlled Changes to `binlog_format`

On versions that still allow setting the variable, you can review the syntax and scope:

```sql
-- The global value applies to new connections according to the variable's rules.
SET GLOBAL binlog_format = 'ROW';

-- Applies only to the current session.
SET SESSION binlog_format = 'ROW';
```

The statements above are illustrative only. In MySQL 8.0.34 and later, changing `binlog_format` is deprecated and may emit warnings. Prefer configuring row-based from the start and follow version documentation before altering a running system.

### 10.1. Why Should You Avoid Changing It Directly on Production?

MySQL restricts changing the format in several cases:

- Cannot be changed from inside a stored function or trigger.
- Cannot change session format while the session has open temporary tables.
- Cannot change global format in certain replication channel states with temporary tables or running applier threads.
- For NDB, the variable has specific rules.
- Changing source/replica out of sync can cause the applier to fail when receiving row events while expecting statement format.

Additionally, temporary tables are logged under different rules across statement, row, and mixed formats. Switching format while temporary tables remain open can make the event sequence impossible to replay as expected. Never change the format mid-flight during an active business session.

### 10.2. Procedure for Migrating from SBR/MIXED to RBR

1. **Inventory:** collect MySQL versions for all sources/replicas, `binlog_format` settings, storage engines, isolation levels, `log_replica_updates`, GTID status, and binlog consumers such as CDC.
2. **Review warnings:** look for `Statement is not safe to log in statement format` warnings, and audit statements using non-deterministic functions, stored programs, triggers, and `LIMIT` clauses.
3. **Capacity assessment:** estimate binlog growth when switching to row events, especially for large batch updates/deletes and BLOB/TEXT columns. Check disk space, retention, bandwidth, and archive storage.
4. **Verify dependent tools:** confirm `mysqlbinlog` versions, backup tools, CDC, audit pipelines, and downstream consumers understand row events and server metadata for that version.
5. **Test in staging:** migrate a staging topology with representative data and workload. Test replication, failover, PITR, backup/restore, and binlog inspection.
6. **Schedule a change window:** plan for the entire topology. If configuration changes are needed while replication is active, stop appliers per the runbook and switch formats consistently across affected servers.
7. **Roll out:** transition following the tested sequence, verify each replica catches up, confirm zero applier errors, and ensure log volume stays within limits.
8. **Monitor:** track binlog generation rate, relay logs, replication lag, purge duration, I/O, and PITR timing. Maintain a rollback plan only within versions that still support the legacy format.

If the target version no longer supports the legacy option in the future, rolling back by reverting to SBR/MIXED may not be possible. Any fallback plan must rely on actual server versions and event readability, not merely toggling one configuration variable.

## 11. Practice Scenario

A MySQL environment has a source and two replicas. The source runs MySQL 8.0.36 with `binlog_format=MIXED`; one replica chains binlogs (`log_replica_updates`) to serve a second-tier replica. The operations team plans to upgrade the source to MySQL 8.4 and switch to `ROW`. The system also has a CDC pipeline reading the binlog to update a data warehouse.

Outline a sequenced plan:

1. Record the version, binlog format, `log_replica_updates`, storage engines, isolation levels, and replication status of all three servers.
2. Confirm the intermediate and downstream replicas support row events emitted by the source; check the version compatibility matrix for the 8.0-to-8.4 upgrade path.
3. Verify that CDC supports row events, the active `binlog_row_image`, and the data types/metadata present in tables. Test replaying a log segment in a test environment.
4. Estimate log volume increase when large batch updates/deletes switch from statement to row; confirm binlog and relay log capacity suffices for retention.
5. Rehearse stopping replication, updating configuration per version guidelines, restarting the applier, and confirming all replicas catch up.
6. Test PITR from a baseline backup with row events; verify both business data and CDC state are correct after recovery.
7. Complete the change only after zero compatibility warnings, applier errors, or data discrepancies remain.

**Self-check questions:**

1. When an `UPDATE` modifies one million rows, what do SBR and RBR write to the binlog? Which format can generate a larger log?
2. Why can `UPDATE ... LIMIT 10` without `ORDER BY` be unsafe with SBR?
3. Under what circumstances does mixed format decide to switch to row-based logging?
4. Does `binlog_format=ROW` mean an `ALTER TABLE` statement is logged as row events? Explain.
5. What does `binlog_row_image=MINIMAL` change and what risks does it pose for CDC tools?
6. What can happen if the source switches to `ROW` while a replica chaining binlogs remains set to `STATEMENT`?
7. Why should you check the deprecation status of `binlog_format` when upgrading to MySQL 8.0.34 or 8.4?

## 12. Selection Principles

For new systems, prefer `ROW` and test log size, binlog inspectability, replication, CDC, and PITR. RBR reduces the risk of data drift from re-executing non-deterministic statements and is the default format in modern MySQL versions.

Maintain `STATEMENT` or `MIXED` in legacy systems only when there is a well-understood compatibility requirement, proven by testing, along with a migration plan. MySQL deprecated changing `binlog_format` starting in 8.0.34; therefore, do not build new topologies that depend on SBR/MIXED.

Evaluate the format from three angles: can data be reconstructed accurately, can binlogs be stored and replayed within target recovery times, and can operational tools read/decode the events? An appropriate choice must satisfy both replication and PITR within the same architecture.

## References

- [MySQL 8.4 Reference Manual — Binary Logging Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual — Setting the Binary Log Format](https://dev.mysql.com/doc/refman/8.4/en/binary-log-setting.html)
- [MySQL 8.4 Reference Manual — Mixed Binary Logging Format](https://dev.mysql.com/doc/refman/8.4/en/binary-log-mixed.html)
- [MySQL 8.0 Reference Manual — Advantages and Disadvantages of Statement-Based and Row-Based Replication](https://dev.mysql.com/doc/refman/8.0/en/replication-sbr-rbr.html)
- [MySQL 8.0 Release Notes — Changes in MySQL 8.0.34](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-34.html)
