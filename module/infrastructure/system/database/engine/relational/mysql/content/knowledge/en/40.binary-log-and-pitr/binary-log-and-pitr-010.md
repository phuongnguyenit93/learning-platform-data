# Filter Scope During Log Replay and the Risk of Missing Transaction Dependencies

In the **DATABASE_MYSQL** module, the binary log is a vital component of backup and recovery. After restoring a baseline backup, administrators can replay events from the binary log to bring data to a desired point in time. In multi-schema systems, sometimes only one schema needs to be replayed using a filter option. This approach must be evaluated carefully because filtering scope depends on the logging format and the statement's execution context.

This lesson focuses on `mysqlbinlog --database`, differences between statement-based and row-based logging, MIXED behavior, and the risk of dropping related changes inside cross-schema transactions. The goal is to build a verifiable PITR workflow that preserves consistency and avoids producing a partially consistent data state.

Within DATABASE_MYSQL, this topic complements mastering table design, data types, keys, SQL queries, indexes, transactions, and concurrency control; it also connects to reading execution plans, query tuning, privilege management, backups, and troubleshooting relational database operations.

## 1. Objectives and Context

After this lesson, you will be able to:

- Explain how the binary log stores changes as statements, row events, and transaction groups.
- Distinguish how `mysqlbinlog --database` filters logs under each logging format.
- Predict cases where a statement is included in or excluded from output even though the schema name in the SQL query appears to match.
- Identify transactions updating multiple schemas, triggers, or routines with dependent side effects.
- Choose between replaying the full log versus filtering by schema based on consistency requirements.
- Verify backup anchors, GTIDs, log coordinates, and recovery results before returning data to service.

The binary log records data-changing events and certain structural changes in order. Depending on configuration, events may contain SQL statements or row-change descriptions. When an InnoDB transaction commits, the transaction's events are recorded as a group so they can be replayed in order. Therefore, filter scope must be evaluated alongside transaction boundaries, not merely by table names.

A typical PITR workflow consists of:

1. Restoring a suitable full backup.
2. Identifying the backup's position or GTID as the starting point.
3. Gathering the continuous binary log sequence from that point.
4. Replaying events in order up to before the timestamp or transaction to exclude.
5. Verifying data and business constraints before opening the service.

If a single schema needs to be restored, filtering can alter the set of events replayed. That is why you must understand exact filtering rules before running commands on a target server.

## 2. Three Binary Log Recording Formats

MySQL supports three primary recording formats:

| Format | Recorded content | How it replays |
|---|---|---|
| STATEMENT | Executed SQL statement with required context | Re-executes the SQL statement |
| ROW | Events describing inserted, updated, or deleted rows | Applies row changes |
| MIXED | Combination of statement and row depending on statement type | Depends on the actual format of each event |

Check current configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
~~~

The current `binlog_format` value does not prove all historical events were logged in the same format. MIXED can switch formats per statement; certain operations like DDL are still logged as statements. When analyzing old logs, inspect the actual events inside the files rather than relying solely on current configuration.

You can inspect binary log contents for investigation:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /archive/mysql-bin.000123 > /tmp/binlog-inspect.sql
~~~

`-vv` and `DECODE-ROWS` display row-event details as readable comments. This is an inspection mode; never use this decoded output as an execution recovery stream. When re-executing logs, keep the default output mode so `mysqlbinlog` emits all required `BINLOG` statements for row events.

## 3. Rules of `mysqlbinlog --database`

The `--database=db_name` option (short flag `-d`) filters entries output from local binary logs. It accepts only one schema; if specified multiple times, the last occurrence takes effect. Filtering rules depend on the event's format.

### 3.1. Statement-based logging: filtering by default database

With STATEMENT, `mysqlbinlog --database=shop` checks the default schema selected by `USE`. It does not simply scan all fully qualified schema names written inside the SQL statement.

Example:

~~~sql
USE audit;
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

Even though the statement updates table `shop.orders`, the default schema is `audit`. When filtering logs with `--database=shop`, the statement above can be excluded from output because `shop` was not the default schema when the statement was logged.

The reverse can also happen:

~~~sql
USE shop;
INSERT INTO audit.order_events(order_id, event_type)
VALUES (1001, 'PAID');
~~~

The default schema is `shop`, so `--database=shop` can retain this statement even though the target table belongs to the `audit` schema.

This creates two risks:

- **Missing changes needed for recovery:** a statement targeting a table in the desired schema was executed while a different default schema was active.
- **Replaying out-of-scope changes:** a statement is retained because the default schema matched, even though it modifies a different schema.

Schema-qualified table names inside SQL do not alter the `USE` context. Exceptions handled specially by MySQL are `CREATE DATABASE`, `ALTER DATABASE`, and `DROP DATABASE`: the schema being created, altered, or dropped is evaluated against the filter condition.

### 3.2. Row-based logging: filtering by the changed table's schema

With ROW, `mysqlbinlog --database=shop` retains events that modify tables belonging to the `shop` schema. The default schema selected by `USE` does not govern filter matching.

Example:

~~~sql
USE audit;
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

In ROW format, row events for `shop.orders` still belong to the `shop` scope and can be included in the filtered output.

Conversely:

~~~sql
USE shop;
INSERT INTO audit.order_events(order_id, event_type)
VALUES (1001, 'PAID');
~~~

The row event modifies table `audit.order_events`, so it falls outside `--database=shop` scope even though the default schema is `shop`.

This difference is critical when a transaction writes to multiple schemas. If a transaction updates `shop.orders` and inserts an event into `audit.order_events`, ROW filtering can retain only the `shop` portion and drop the `audit` portion. On replay, data may no longer reflect a complete original business transaction.

### 3.3. Mixed and DDL

MIXED uses both statement events and row events. Thus, the same `--database` option can apply two different filtering rules within the same log file:

- Statement-logged events are evaluated against the default schema.
- Row events are evaluated against the modified table's schema.
- DDL such as `CREATE TABLE` and `ALTER TABLE` is logged as statements, so statement rules apply.

With MIXED, if you want to filter logs by schema, ensure modified tables reside in the schema selected with `USE`, and especially avoid cross-schema update statements. In practice, this is hard to guarantee if applications use triggers, stored routines, or statements with fully qualified table names.

The table below summarizes how to interpret this:

| Case | STATEMENT | ROW | MIXED |
|---|---|---|---|
| `USE audit`, updating `shop.orders` | Filtered by `audit` | Filtered by `shop` | Follows event format |
| `USE shop`, inserting into `audit.order_events` | Filtered by `shop` | Filtered by `audit` | Follows event format |
| DDL such as `CREATE TABLE` | Follows default schema and database DDL exceptions | Still a statement event | Follows statement rules |
| Single transaction writing to multiple schemas | Keeps/drops statement by default database; may include multi-schema effects | May retain only row events of the selected schema | May mix both filtering behaviors |

Never infer the outcome solely from the displayed SQL. Inspect actual events, know the format used when logging occurred, and test output in an isolated recovery environment.

## 4. Cross-Schema Transactions and Data Dependencies

### 4.1. One transaction can represent multiple business changes

An e-commerce application might update an order, post to a payment ledger, and write an audit event inside the same transaction:

~~~sql
USE shop;

START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

INSERT INTO audit.order_events(order_id, event_type, created_at)
VALUES (1001, 'PAID', NOW());

INSERT INTO accounting.payment_ledger(order_id, amount, created_at)
VALUES (1001, 250000, NOW());

COMMIT;
~~~

This is a single business unit: the order is paid, the audit event is logged, and the payment ledger is updated. If recovery retains only changes to `shop`, the order status may become `PAID` while audit and ledger lack corresponding records. If filtering by another schema, a ledger entry might exist while the order never changed status.

Dependencies may exist across:

- Core business tables and history/audit tables.
- Summary tables, reconciliation tables, or outbox tables.
- Triggers writing extra data when a primary table changes.
- Stored procedures or functions reading/writing across schemas.
- Business invariants enforced by the application within one transaction.
- DDL and data operations deployed in a dependent sequence.

Not every dependency is expressed as a foreign key in MySQL. A transaction may span multiple tables to maintain business correctness even without direct database constraints between them.

### 4.2. What happens when part of a transaction is filtered out?

With row-based logging, schema filtering can strip row events belonging to other schemas while keeping changes to the selected schema. Replay results can reflect only a fraction of the original transaction.

Common consequences:

- Order status disagrees with the payment ledger.
- Core tables have data while audit or outbox tables lack events.
- Summary records disagree with detailed records.
- Downstream processes fail to receive required events.
- Subsequent recovery cannot reproduce the original business state merely by replaying the filtered log subset.

With statement-based logging, filtering can retain statements affecting out-of-scope schemas, or drop statements updating the target schema because `USE` selected another schema. Therefore, filtering by schema is not synonymous with cleanly excising every operation outside that schema.

Transaction boundaries at the MySQL level still matter on replay, yet event filtering can strip changes required to preserve the transaction's business meaning. A transaction left with partial events is no longer equivalent to the original transaction.

### 4.3. GTIDs cannot repair missing changes automatically

GTIDs identify transactions in the binary log chain and help track executed transactions. GTIDs do not analyze cross-schema business relationships and cannot restore row events dropped by a filter.

If filtered replay output keeps the transaction's GTID metadata while containing only partial changes, the post-recovery GTID state can make replaying the same transaction again unsafe for filling in the missing portion. Never manually edit GTIDs or splice logs to patch a filtered restore without understanding the actual state. Restore from a clean baseline and execute a verified procedure.

## 5. Distinguishing Filtering Layers

Option names look similar, yet they apply at different stages:

| Mechanism | Where it applies | Effect |
|---|---|---|
| `mysqlbinlog --database` | When reading and exporting local binary logs | Filters exported output for inspection or replay |
| `--binlog-do-db` / `--binlog-ignore-db` | On the server writing binary logs | Determines which events are written into the binary log |
| `replicate-do-db` / `replicate-ignore-db` | On a replica when applying replication events | Determines which events are applied on the replica |

Never use `mysqlbinlog --database` to assume the source binary logs recorded everything. If the source excluded changes via `--binlog-do-db` or `--binlog-ignore-db`, unlogged events may not exist in the log chain for PITR at all. Check source configuration, log format, and recorded data scope beforehand.

Replication filtering rules also depend on log format. Never take results from a `mysqlbinlog --database` test and assume they match replica filtering rules identically. The two mechanisms serve different stages and must be tested separately.

## 6. Pre-Filtering Investigation Workflow

Before generating a recovery SQL stream, gather the following details:

1. **Recovery goal:** do you need to recover the entire server, one schema, one table, or just a group of records?
2. **Baseline data anchor:** which backup is selected, when did it finish, and what is its GTID set or binary log coordinate?
3. **Log chain:** are all files present in order, with no gaps or corruption?
4. **Event format:** STATEMENT, ROW, or MIXED; are DDL, triggers, or routines involved?
5. **Dependency scope:** do transactions touch multiple schemas or write to audit, ledger, outbox, or summary tables?
6. **Stop point:** before which transaction, timestamp, or event position must replay stop?
7. **Target environment:** is it an isolated clone compatible in version, charset, collation, engines, and required plugins?

Basic verification commands:

~~~sql
SHOW BINARY LOGS;
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
~~~

`SHOW BINARY LOGS` shows log files present on the queried server. For off-server archives, check manifests and transferred file lists. The `binlog_format` value reflects current settings; it does not replace inspecting historical events.

Read logs in verbose decoded mode:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  --start-position=12345 \
  /archive/mysql-bin.000123
~~~

Inspect `GTID`, `BEGIN`, `COMMIT`/`Xid`, `Query`, `Table_map`, and row-event markers. Record `# at` and `end_log_pos` to pinpoint event positions. If transactions span multiple schemas, list every affected table inside the same transaction group before deciding to filter.

Never treat `SHOW GLOBAL VARIABLES LIKE 'binlog_format'` as sole proof that an entire log file was written in one format. Inspect the actual events and relevant historical settings.

## 7. Choosing a Recovery Strategy

### 7.1. Replay full logs first, then extract data afterward

This is usually the safest way to preserve dependencies when recovering a single schema from a multi-schema server:

1. Provision an isolated recovery server with a compatible configuration.
2. Restore the full baseline backup, including related schemas.
3. Replay the binary logs completely without using `--database` to strip events.
4. Verify data and state at the target recovery point.
5. Extract the target schema or tables from the recovery environment.
6. Load the verified data into the target system via a controlled deployment procedure.

This approach preserves cross-schema dependent changes during replay. Afterward, you can decide which data to promote to the target environment. Extraction must still check business dependencies if the target schema will operate independently.

### 7.2. Filter only when data scope is truly independent

You can consider `--database` when:

- The target schema has no cross-schema write transactions.
- No triggers, routines, or business flows produce dependent effects outside the schema.
- The logging format is verified and filtering rules have been tested.
- Start and stop boundaries do not cut across transactions that must be kept.
- Output replays cleanly in a test environment and passes business validation checks.

Example generating filtered output for review:

~~~bash
mysqlbinlog --database=shop \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  > /tmp/shop-filtered.sql
~~~

This creates a file for inspection. Never push this output directly to production simply because the command exited cleanly. Read the file, identify retained transactions, compare against original events, and test-run on a clone first.

Once the filter scope is proven safe, replay it in a test environment:

~~~bash
set -o pipefail
mysqlbinlog --database=shop \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  | mysql --login-path=pitr-test
~~~

The example illustrates a single log file. When multiple files are needed, pass all files in exact order and ensure no gaps exist between files. Never stitch files by unverified filename sorting; use log lists and manifests from the backup source.

### 7.3. When independence cannot be proven

If you cannot confirm the schema has no dependencies, restore everything into an isolated environment and extract afterward. If full recovery is impossible due to missing backups or logs, clearly identify what can be recovered, what is missing, and the business impact; never label the result as a complete PITR.

## 8. Start Anchors, Stop Anchors, and Transaction Boundaries

PITR must start at the baseline backup's exact position and stop immediately before or after the target transaction as required. Position coordinates belong to a specific binary log file; never apply one file's position to a different file.

Principles:

- Obtain GTID sets or file/positions from backup metadata, not by estimating from file creation timestamps.
- Replay logs strictly in file and event order.
- Choose stop points at verified transaction boundaries.
- When excluding an erroneous transaction, locate that transaction's opening event and inspect adjacent transactions before and after.
- Cross-check log timestamps against system time zones and actual clocks.
- Keep original binary logs untouched; create working copies and separate manifests.

You can use `mysqlbinlog` options `--start-position`, `--stop-position`, `--start-datetime`, or `--stop-datetime` to bound the read range. Timestamps depend on granularity and environment interpretation; when high precision is needed, prefer verified event coordinates or GTIDs. Never pick an arbitrary `stop-position` in the middle of a transaction's events.

Example replaying logs without schema filtering:

~~~bash
set -o pipefail
mysqlbinlog \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  /archive/mysql-bin.000124 \
  | mysql --login-path=pitr-test
~~~

This represents continuous replay across two verified files. With GTID, verify the GTID state of both the backup and target server to avoid duplicate application or skipped transactions. Never mix file/position recovery workflows with GTID management workflows without an explicit plan.

## 9. Post-Replay Verification

After recovery, verify at least four layers:

**Structural integrity**

- Required tables, indexes, views, triggers, routines, and events exist.
- Charsets, collations, engines, and column definitions match expected versions.
- Required accounts and privileges are restored per policy.

**Data integrity**

- Row counts in critical tables.
- Primary keys, unique keys, and data relationships.
- Aggregate values such as balances, order totals, and payment totals.
- Whether audit, ledger, and outbox records match core table changes.

**Business consistency**

- A paid order must have a corresponding payment record.
- A status change must have an audit event if business rules require it.
- Summary totals must reconcile with detail records.
- No orphaned records or missing downstream events.

**Operational readiness**

- Applications connect and key queries execute properly.
- Background jobs, event schedulers, and sync pipelines are in appropriate states.
- GTIDs or recovery coordinates are documented.
- Recovery duration and data recovery point meet agreed RTO/RPO.

Spot-checking a few sample rows is insufficient to prove all transactions were recovered. Choose measurable business invariants and compare before/after states via queries or reconciliation reports.

## 10. Common Errors During Filtering and Replay

| Symptom | Possible cause | Investigation approach |
|---|---|---|
| Expected target table updates missing from output | Statement event was logged while default schema differed from target schema | Inspect `USE` context and event format; do not search only for table names |
| Output contains operations on out-of-scope schemas | Statement event was kept because default database matched | Inspect every table affected by the statement or routine |
| Audit/ledger records missing after restore | Row events of dependent schemas were dropped by filter | Analyze cross-schema transactions and replay completely in a clone |
| Same filter command yields different results across environments | Different logging formats or MIXED switching per event | Read actual events and check format per event |
| DDL filtered differently than expected | DDL is logged as statement events | Check default schema and special DDL database rules |
| PITR misses a range of changes | Missing log file, source filtered logs, or wrong backup anchor | Reconcile manifests, GTIDs, positions, and source configuration |
| Replay errors due to transaction or GTID issues | Wrong start/stop anchor, duplicate logs, or incompatible GTID state | Rebuild a clean clone and verify metadata before replaying |

When errors occur, never work around them by skipping events or editing original binary logs. Recreate the test environment from the baseline backup, inspect the log chain, and pinpoint the exact missing or duplicated transaction.

## 11. Self-Check

**Scenario 1:** Logs are recorded in STATEMENT format. The application runs `USE audit; UPDATE shop.orders ...`. Why might `mysqlbinlog --database=shop` omit the statement?

**Hint:** With statement-based logging, the filter checks the default schema selected by `USE`. Qualifying `shop.orders` does not switch the default schema from `audit` to `shop`.

**Scenario 2:** Logs are recorded in ROW format. A transaction updates `shop.orders` and inserts a record into `audit.order_events`. When filtering with `--database=shop`, what can happen?

**Hint:** The filter keeps row events belonging to `shop` and drops row events belonging to `audit`. Replaying the remainder can leave business state missing the audit record that belonged to the same transaction.

**Scenario 3:** The server uses MIXED. Can you assume `--database=shop` always filters by the modified table?

**Hint:** No. Results depend on each event's actual format. Statement events use the default database context; row events use the modified table's schema. DDL is also logged as statements.

**Scenario 4:** A team wants to restore only the `shop` schema and does not know whether the application has triggers writing to other schemas. What should they do first?

**Hint:** Inspect triggers, routines, and business flows; perform a full restore into a clone and replay logs unfiltered. Only after data is consistent should you extract the needed schema for the target environment.

**Scenario 5:** `mysqlbinlog --database=shop` generates an SQL file without errors. Does that prove the restore is correct?

**Hint:** No. You must inspect event formats, kept/dropped transactions, cross-schema dependencies, GTID/position handling, then replay on a clone and verify business invariants.

## 12. Key Takeaways

- `mysqlbinlog --database` filters logs locally; filtering behavior depends on each event's logging format.
- STATEMENT filters by the default schema selected with `USE`, not merely by fully qualified table names.
- ROW filters by the schema of the table with row events; multi-schema transactions may be only partially retained.
- MIXED combines both rules; DDL remains statement events.
- Multi-schema transactions may contain dependent business changes such as audit, ledger, outbox, or summary tables.
- GTIDs identify transactions but cannot restore events stripped by a filter.
- Unless schema independence is proven, restore fully in an isolated environment and extract data afterward.
- Always verify baseline backups, log chains, GTIDs/positions, transaction boundaries, and business outcomes before opening service.

## References

- [MySQL 8.4 Reference Manual: mysqlbinlog](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog.html) — `--database` rules, output formats, and position options.
- [MySQL 8.4 Reference Manual: Binary Logging Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html) — STATEMENT, ROW, and MIXED.
- [MySQL 8.4 Reference Manual: Evaluation of Database-Level Replication and Binary Logging Options](https://dev.mysql.com/doc/refman/8.4/en/replication-rules-db-options.html) — how database-level filtering rules are evaluated.
