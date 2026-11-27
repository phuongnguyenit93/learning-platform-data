# Rehearsing Restore and PITR After Accidental Updates or Deletes

A single mistaken `UPDATE` or `DELETE` can corrupt thousands of records in seconds. Once detected, the priority is preserving transaction history, pinpointing the last good state, and recovering in a verifiable manner. MySQL Point-in-Time Recovery (PITR) combines a consistent base backup with binary logs to reconstruct database state at a specific timestamp or transaction position.

PITR is not simply restoring the latest backup and replaying every binary log. Continuing replay past the damaging transaction merely repeats the mistake. You must locate the exact transaction or binlog position containing the bad change, spin up a recovery instance in isolation, stop replay right before that transaction, verify the data, and selectively restore or merge the affected records back into production.

This lab falls under mastering MySQL from transactions, backups, binary logs, and replication to operational incident response. The goal is to rehearse the full workflow following an accidental update or delete: preserving evidence, selecting a backup, executing PITR, reconciling data, choosing a merge strategy, and verifying RPO/RTO.

## 1. Drill Objectives and Scope

After completing this lab, learners should be able to:

- Assess blast radius and preserve binary logs before retention expires.
- Select a consistent backup containing GTID or binlog file/position metadata.
- Identify the corrupting transaction from binary logs and audit logs.
- Restore a backup onto an isolated MySQL instance.
- Replay binary logs up to immediately before the destructive transaction.
- Recover a single table, a subset of rows, or an entire instance as the scenario demands.
- Reconcile recovered data against current production state and business rules.
- Plan cutover, rollback, and post-recovery monitoring.
- Measure actual recovery duration and compare against RPO/RTO targets.

### 1.1. Sample scenario

An operator accidentally runs:

~~~sql
UPDATE customer
SET account_status = 'CLOSED';
~~~

Missing a `WHERE` clause, the statement flips every customer account to `CLOSED`. The team notices a few minutes later. Between the last backup and detection, the primary continued accepting legitimate transactions such as new customer registrations, address updates, and order placements.

The goal is not to rewind the entire system and lose all valid transactions since the mistake. The team must build a recovered copy right before the bad transaction, then extract and merge the affected records—or plan a full-instance cutover if damage is sufficiently widespread.

### 1.2. Distinguishing key timestamps

| Milestone | Meaning |
|---|---|
| T_backup | Consistent point of the selected base backup |
| T_bad | Commit time of the corrupting transaction |
| T_detect | Time when the team detects the incident |
| T_stop | Time when writes capable of spreading damage are halted or restricted |
| T_recovery | Selected PITR point used to reconstruct recovered data |
| T_restore_done | Time when the recovery instance is ready for inspection |

`T_recovery` normally precedes `T_bad`. `T_detect` may lag well behind `T_bad`; that gap determines how many legitimate transactions occurred after the bad transaction and must be preserved during merge.

## 2. Backup and PITR Architecture

PITR requires at least two components:

1. **Base backup:** a consistent copy of the database at a known point.
2. **Continuous binary logs:** the stream of events after the backup point, retained long enough to replay up to the recovery target.

~~~mermaid
flowchart LR
    A["Base backup at T_backup"] --> B["Restore to recovery instance"]
    C["Binary logs after T_backup"] --> D["Select continuous log sequence"]
    B --> E["Replay valid transactions"]
    D --> E
    E --> F["Stop before corrupting transaction"]
    F --> G["Reconcile recovered data"]
    G --> H["Extract / merge / cutover"]
~~~

Without a consistent backup, binary logs alone cannot reconstruct full state. If any binary log segment is missing between the backup and the recovery point, you cannot replay continuously across that gap using remaining files alone.

### 2.1. Choosing a backup type

| Backup Type | Characteristics | What to Verify |
|---|---|---|
| Logical dump | Exports schema and data as SQL; easy to select specific tables or rows | Restore speed, consistency, routines/events/triggers, charsets, and binlog metadata |
| Physical hot backup | Copies InnoDB files online using a dedicated hot-backup tool | Must prepare/recover per tool rules; requires GTID/binlog coordinate metadata |
| MySQL Clone or storage snapshot | Fast copy depending on platform and version | Consistency, snapshot scope, compatibility, and binlog coordinates |
| Managed service backup | Provider manages snapshots and PITR | Retention, restore target, destination region/instance, and actual restore duration |

Backups must carry metadata recording replication/binlog coordinates at snapshot time. Depending on the tool, this lives in `mysqldump` output, physical backup metadata files, or managed service records. Never guess file/position from backup upload completion timestamps.

### 2.2. Logical backups with InnoDB

With `mysqldump`, `--single-transaction` creates a consistent snapshot for transactional tables like InnoDB. Avoid running concurrent DDL during dumps, as DDL can undermine snapshot reliability. Non-transactional tables are not protected by the same snapshot mechanism.

Illustrative example:

~~~bash
mysqldump \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --source-data=2 \
  --databases shopdb \
  > shopdb-full.sql
~~~

The `--source-data` flag and binlog coordinate options vary by client version; older versions use `--master-data`. Check `mysqldump --help` and docs for your exact version. Preserve the coordinates embedded in the dump alongside the backup file.

If the dump spans multiple databases, accounts, routines, or events, clarify the exact restore scope. Never distribute MySQL user accounts or secrets in uncontrolled backup shares.

### 2.3. Physical backups

For physical backups, strictly follow the tool's backup/prepare/restore workflow. For instance, Percona XtraBackup stores binary log position and GTID metadata in backup metadata files. MySQL Enterprise Backup provides equivalent metadata in its tool format.

Never copy a live running data directory directly and treat it as a consistent InnoDB backup. Know whether the backup is crash-consistent or application-consistent, how the tool flushed/copied redo logs, and which prepare/restore steps are mandatory.

## 3. Immediate Response Upon Detecting Accidental Updates or Deletes

### 3.1. Preserve history before deep investigation

Follow your organization's incident runbook:

1. Log detection time, reporter, affected database, table, and suspected operation.
2. Restrict or pause write paths causing further corruption if safe to do so.
3. Preserve existing binary logs and archived logs; temporarily adjust log purging if needed and authorized.
4. Capture relevant error logs, audit logs, general logs, or query logs.
5. Record GTIDs, binlog file/position, server UUID, and replication state.
6. Take a protective snapshot/backup of the current state before attempting major repairs.
7. Appoint one incident coordinator and maintain one shared incident timeline.

Do not run ad-hoc experimental data fixes directly in production. Never restart or reset replication solely to clear error alerts before preserving evidence.

### 3.2. How to restrict new writes

Halting all writes may disrupt unrelated business flows. Scope restrictions to the blast radius:

- If a single table is affected and the app can pause that feature, disable only that write path.
- If a bad statement is still executing, cancel the query/transaction per procedure and verify whether it committed.
- If the transaction already committed, killing the query cannot undo data; recover via backup/PITR.
- If downstream jobs keep mutating records based on corrupted state, pause those jobs or users before merging.

With InnoDB, an uncommitted transaction rolls back if killed, whereas a committed transaction cannot be undone by killing its connection. DDL and implicit-commit statements also require separate handling.

### 3.3. Preserving binary logs

On the source, collect:

~~~sql
SHOW BINARY LOGS;

SHOW BINARY LOG STATUS;

SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'binlog_expire_logs_seconds',
  'gtid_mode',
  'server_id'
);
~~~

`SHOW BINARY LOG STATUS` is available in newer MySQL versions; older versions use `SHOW MASTER STATUS`. Verify exact syntax for your running server.

Copy required binary logs to safe storage, preserving filenames, sequence, and checksums. When using archived binary logs, verify no files are missing between the backup and the incident timestamp. Never purge logs before confirming the recovery point.

## 4. Identifying the Corrupting Transaction

### 4.1. Combining audit logs and binary logs

Audit logs or application logs reveal who sent the statement, from which host, and via which service. Binary logs reveal what was actually committed to transaction history. Cross-reference both:

- Event timestamp and timezone.
- User, host, and connection ID if logged.
- SQL text or row changes.
- Transaction boundaries and commits.
- GTID or file/position.
- Affected tables and keys.

Timestamps alone lack precision because multiple transactions can share the same second, log timezones can differ, and transactions can span seconds. Prefer GTIDs and binlog positions; use timestamps only to narrow the search window.

### 4.2. Decoding binary logs for analysis

For row-based binary logs, decode row events with `mysqlbinlog`:

~~~bash
mysqlbinlog \
  --verbose \
  --base64-output=DECODE-ROWS \
  --start-position=4 \
  binlog.000245 \
  > binlog-decoded.txt
~~~

Verbose output exposes `Table_map`, `Update_rows`, and `Delete_rows` events along with before/after column values depending on row image settings. Under statement-based logging, `Query` events display the SQL directly.

Decoded output is strictly for investigation. Never pipe a decoded file into `mysql` as a substitute for raw binary logs during replay, because decoded pseudo-SQL and commented row events are not executable SQL replay scripts. During recovery, run `mysqlbinlog` on the raw log files to generate a proper replay stream.

### 4.3. Finding transaction boundaries

A single transaction spans multiple events:

~~~text
GTID event
BEGIN
Table_map / Query / row events
...
XID (COMMIT)
~~~

With row-based logging, one large `UPDATE` may emit multiple row events inside the same transaction. Locate both the opening event of the corrupting transaction and its commit position. When running PITR up to before that transaction, the stop point must exclude the entire transaction—never stop mid-transaction between row events.

Record:

- GTID of the corrupting transaction (if GTIDs are enabled).
- Binary log filename containing the transaction.
- Position of the transaction's first event.
- Position of the following transaction or verified stop point.
- Valid transactions immediately before and after the bad transaction.

### 4.4. Cross-checking GTIDs

If GTIDs are enabled, capture on the source:

~~~sql
SELECT
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
~~~

GTIDs identify executed and purged transactions. They do not tell you whether a transaction caused business corruption; you must inspect event payloads and affected data.

If the backup contains a snapshot GTID set, use it to determine which binary logs require replay. If no consistent GTID or binlog coordinate metadata accompanies the backup, halt and verify backup provenance; never guess starting points from filenames or timestamps.

## 5. Selecting the Recovery Point

The recovery point is usually right before the bad transaction, though you must account for valid transactions that occurred afterward.

### 5.1. Full-instance PITR

Appropriate when:

- Damage is widespread and the entire instance must revert to its pre-incident state.
- Losing post-incident valid transactions is acceptable, or they can be replayed cleanly.
- The application has a cutover plan and strategy for post-recovery data.

Full-instance PITR restores the entire database from backup and replays logs up to the chosen stop point. It does not automatically preserve valid transactions committed after that stop point.

### 5.2. Table-level or row-subset recovery

Appropriate when only one table or a subset of records was affected while other tables continued receiving writes. Typical workflow:

1. Restore the full backup onto an isolated recovery instance.
2. Replay binary logs up to right before the destructive transaction.
3. Export the target table or row subset from the recovery instance.
4. Diff against current production data.
5. Merge records respecting primary keys, foreign keys, and valid post-incident updates.

This is a common way to rescue accidentally deleted or updated data without rolling back the whole system. However, partial recovery is not always trivial: other tables may hold foreign keys to it, post-incident transactions may depend on corrupted values, and triggers may fire side effects during import.

### 5.3. Never skip post-incident transactions blindly

Stopping PITR before the bad transaction leaves all subsequent transactions un-replayed. A valid order may have been placed right after prices were corrupted; a new customer may have been inserted after a bad `DELETE`.

To retain valid post-`T_bad` data:

- Recover affected tables/rows from the recovery instance.
- Keep valid production changes in place, or selectively extract/replay them per business logic.
- Reconcile relationships and foreign keys before merging.
- Handle transactions that relied on the corrupted state.

Never simply resume replaying binary logs past the bad transaction if later transactions depend on the corrupted state. Doing so can introduce new discrepancies, duplicate keys, or invalid records.

## 6. Restoring the Backup to an Isolated Instance

### 6.1. Preparing the recovery instance

The recovery instance requires:

- A MySQL version compatible with the backup and binary logs.
- Sufficient storage for restore, relay/temp space, and exports.
- Network isolation receiving zero application traffic.
- Distinct server ID and identity avoiding topology conflicts.
- A recovery account with minimum required privileges.
- Binary logging/GTID configured per the recovery plan.
- No automatic joining into replication or read pools before validation.

Keep the recovery instance isolated from production so applications cannot write to it and replicas never pull unintended events. Enable `read_only`/`super_read_only` if compatible with restore tooling; certain restore or replay steps may require elevated privileges.

### 6.2. Restoring a logical dump

Example restoring into an isolated instance:

~~~bash
mysql \
  --host=recovery-db.internal \
  --user=recovery_admin \
  --password \
  < shopdb-full.sql
~~~

If the dump covers multiple databases or contains `CREATE DATABASE`/`USE` statements, do not pass an arbitrary target database flag. Inspect the header and footer of the dump to verify where it writes.

After restoring:

~~~sql
SELECT VERSION();
SHOW DATABASES;
SHOW TABLE STATUS FROM shopdb;
~~~

Verify tables, views, triggers, routines, events, charsets, collations, constraints, and key row counts. Confirm the restore finished cleanly without mid-stream errors; an import that threw errors cannot be considered a valid restored backup.

### 6.3. Restoring a physical backup

For physical backups, run the tool's prepare/apply-redo phase per its documentation, then restore into the target datadir or instance. Verify file ownership, InnoDB settings, keyring/encryption configuration, and required plugins.

Never start two `mysqld` processes pointing at the same datadir. Never arbitrarily alter server UUID or GTID metadata to force topology membership, as doing so can corrupt replication history.

### 6.4. Verifying the backup coordinates

After restore, determine precisely:

- The GTID set included in the backup, if present.
- The binlog file and position at snapshot time.
- Backup timestamps and metadata.
- The sequence of archived binary logs starting from that coordinate.
- Any missing or corrupted files in the log chain.

If the backup ran online against an active source, tool metadata must specify the consistent snapshot point. Never substitute backup file completion time for the transactional consistency point.

## 7. Replaying Binary Logs Up to Before the Corrupting Transaction

### 7.1. Verifying the log file sequence

List every log file from the backup coordinate through the file containing the bad transaction. Verify filenames, sequence, sizes, and checksums. If a file is missing or unreadable, locate an intact archive copy or fall back to an earlier backup/recovery point.

On the source, `SHOW BINARY LOGS` lists only files still on disk at query time. Archived files must be cross-checked separately against archive manifests.

### 7.2. Determining the start position

Read the starting file and position from backup metadata. If the backup records a GTID set, identify the corresponding binlog and verify the transaction sequence. Never assume every backup starts at position 4; always read the exact position from backup metadata.

### 7.3. Generating the replay stream up to the stop position

Suppose:

- Backup was taken at `binlog.000240`, position `987654`.
- The bad transaction begins in `binlog.000245` at position `456789`.
- Intermediate files `binlog.000241` through `binlog.000244` must be replayed completely.

Pass `--start-position` for the first file and `--stop-position` for the last file in the same invocation. `mysqlbinlog` applies `--start-position` to the first file and `--stop-position` to the final file in the list:

~~~bash
mysqlbinlog \
  --start-position=987654 \
  --stop-position=456789 \
  binlog.000240 \
  binlog.000241 \
  binlog.000242 \
  binlog.000243 \
  binlog.000244 \
  binlog.000245 \
  > replay.sql
~~~

The positions above are purely illustrative. Substitute exact positions verified from metadata and event analysis. `--stop-position` must point to the start offset of the first event of the corrupting transaction so that transaction and everything after it are excluded. Inspect the output to confirm the bad transaction is absent and preceding valid transactions completed cleanly. When start and stop fall in the same file, both flags apply to that file.

### 7.4. Inspecting the stream before applying

Before executing against the recovery instance:

- Inspect the start and end of `replay.sql`.
- Confirm the expected source, database, and file sequence.
- Confirm the corrupting transaction's GTID does not appear.
- Confirm the stream does not stop mid-transaction.
- Confirm no writes fall outside expected scope.
- Record checksums and archive the generated stream alongside execution logs.

Never hand-edit a GTID event or row event inside a replay file. If a transaction must be skipped or data adjusted, perform it on the recovered instance via an auditable, documented procedure.

### 7.5. Applying the stream to the recovery instance

~~~bash
mysql \
  --host=recovery-db.internal \
  --user=recovery_admin \
  --password \
  --binary-mode=1 \
  < replay.sql
~~~

Apply files/segments in verified order. Watch stdout/stderr and exit codes. If any statement fails, stop and investigate; never ignore errors and continue as though replay succeeded.

Never apply this stream to the production source. The goal is producing an isolated recovery instance for inspection and reconciliation—not overwriting production during investigation.

### 7.6. Using timestamps when exact positions are unknown

`mysqlbinlog` supports time bounds via `--start-datetime` and `--stop-datetime`. While useful for narrowing a search, timestamps are far less precise than transaction positions:

- Multiple transactions can share the same timestamp.
- Logged timestamps depend on timezones and system clocks.
- A single transaction can span across the chosen timestamp boundary.
- You risk accidentally including a partial or adjacent transaction without verifying boundaries.

If you must filter by time, decode the stream, locate exact transaction boundaries, and verify with GTID/position before applying. Never rely solely on an approximate timestamp for a critical recovery point.

## 8. Reconciling and Extracting Data

### 8.1. Verifying the recovered instance

After replay, compare the recovery instance against expected state:

- Total row counts and grouped counts.
- Primary and unique keys.
- Critical business statuses.
- Foreign keys and cross-table integrity.
- Monetary totals, balances, inventory, or business invariants.
- Record timestamps and version numbers.
- Triggers, generated columns, and derived data.

Example checking account status breakdown:

~~~sql
SELECT account_status, COUNT(*) AS row_count
FROM shopdb.customer
GROUP BY account_status
ORDER BY account_status;
~~~

Checking bulk-closed records:

~~~sql
SELECT COUNT(*) AS closed_count
FROM shopdb.customer
WHERE account_status = 'CLOSED';
~~~

Do not compare total row counts alone. Two datasets with identical row counts can still diverge on keys, statuses, or relationships.

### 8.2. Extracting a table or row subset

If only a subset of rows needs restoration, export from the recovery instance into a staging schema or intermediate file. Never import directly into a production table before reviewing:

- Were rows validly updated after `T_bad`?
- Were new rows inserted after the backup?
- Do primary keys collide with current production data?
- Do foreign keys reference changed rows?
- Must system-maintained columns like `version`, `updated_at`, or audit fields be preserved?
- Will `INSERT`/`UPDATE` triggers fire unintended side effects?

A table may hold valid new data written after the corrupting transaction. Never replace an entire production table with an older copy if doing so wipes out newer legitimate rows.

### 8.3. Diffing before merging

Load the recovered data into a staging schema in the target environment or an intermediate database. Write queries listing:

- Rows present in recovery but missing in production.
- Rows present in both with differing values.
- Rows present only in production.
- Rows with affected dependent foreign keys.

Example diffing by primary key:

~~~sql
SELECT r.customer_id
FROM recovery_db.customer AS r
LEFT JOIN production_stage.customer AS p
  ON p.customer_id = r.customer_id
WHERE p.customer_id IS NULL;
~~~

For large tables, use chunked checksums or an approved data comparison tool. Ensure comparisons use matching collations, data types, and row scopes.

### 8.4. Controlled merge

Write an explicit merge script conditioned on primary keys and `version`/`timestamp` where available. Dry-run it on a staging copy, record insert/update/delete counts, and verify invariants post-merge.

When restoring a single column overwritten by a bad `UPDATE`, you do not necessarily have to overwrite entire rows from backup. You can restore just the corrupted column for targeted rows while preserving other columns legitimately modified post-incident—provided scope and business invariants are verified cleanly.

For an accidental `DELETE`, restoring rows from backup can collide with foreign keys or replacement records created afterward. Decide explicitly whether to restore original IDs, assign new IDs, or maintain tombstones per business rules.

## 9. Cutover and Rollback Planning

### 9.1. Pre-cutover

- Finalize exact target tables/rows and the merge script.
- Take a backup/snapshot of current production state immediately before merging.
- Rehearse the merge script on a staging copy.
- Schedule a maintenance window or restrict conflicting writes if needed.
- Identify all services, jobs, triggers, and consumers that could write to the affected data.
- Prepare validation queries and abort criteria.
- Assign an approver and an executor.

### 9.2. During cutover

1. Restrict writes to the data scope being merged.
2. Run pre-checks and record baseline outputs.
3. Execute the merge in bounded batches if the table is large.
4. Verify affected row counts after each batch.
5. Run post-checks and invariant queries.
6. Re-enable normal write traffic once all checks pass.

If the merge script might need to be re-run, make it idempotent or checkpoint per batch. Never blindly re-run an entire script after a timeout without verifying which batches already committed.

### 9.3. Rollback of the merge

Before executing, know how to undo the merge:

- Keep the pre-merge snapshot ready for restoration.
- Maintain an audit/staging table holding before and after values.
- Use transaction rollback if the entire merge safely fits inside one transaction.
- For committed batches, prepare a reversal script backed by the pre-merge snapshot/checkpoints.

Huge transactions bloat undo logs, hold locks, and drive replication lag; weigh batching while preserving recoverability. Never assume application rollback can revert an already-committed merge script or external side effects.

## 10. RPO, RTO, and PITR Feasibility

RPO (Recovery Point Objective) is the maximum tolerable data loss measured in time. RTO (Recovery Time Objective) is the maximum tolerable downtime or time to restore service.

Example:

- Daily full backup.
- Continuous binary log archiving.
- Accidental update detected after 4 minutes.
- Restoring the backup takes 35 minutes.
- Replaying binary logs up to before the bad transaction takes 12 minutes.
- Reconciling and merging takes 20 minutes.

Total estimated time is 67 minutes, excluding approvals and cutover. If RTO is 60 minutes, the current workflow misses the target; you must optimize restores, keep a warm recovery instance ready, speed up replay, or adopt faster snapshots/clones.

RPO is not just backup frequency. With continuous, intact binary logs, you can recover nearly to the instant of the incident; if binlogs are missing or purged early, effective RPO degrades back to the last full backup.

Record actual timings after every drill:

| Metric | Drill Result |
|---|---|
| Backup age at incident time | Record duration |
| Binlog span to replay | Record duration and size |
| Restore duration | Record actual elapsed time |
| Replay duration | Record actual elapsed time |
| Data validation duration | Record actual elapsed time |
| Merge/cutover duration | Record actual elapsed time |
| Actual RPO | Maximum data gap |
| Actual RTO | From incident response start until service recovery criteria met |

## 11. Common PITR Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Restore succeeds yet data is missing | Backup excluded tables/schemas or was inconsistent | Inspect backup scope, metadata, and storage engines |
| Replay reports missing binlogs | Retention too short or archive missing a file | Locate intact archive or fall back to an earlier backup |
| Replay stops on duplicate key | Started from wrong coordinate, backup already contains tx, or log applied twice | Verify backup coordinates and GTIDs before re-running |
| Replay hits schema errors | DDL not replayed or restored onto wrong version | Check DDL, migrations, and event ordering |
| Data remains corrupted after PITR | Stop point fell after bad tx or dependent txs were replayed | Re-verify GTID/position and transaction contents |
| Valid transactions lost post-recovery | Ran full-instance PITR prior to `T_bad` and cut over directly | Selectively merge or replay/reconcile valid transactions |
| Import runs slowly or fills disk | Recovery instance lacks I/O or disk capacity | Resize storage, temp space, and log headroom before retrying |
| Physical restore fails to start | Unprepared backup, wrong file permissions, or config/plugin/encryption mismatch | Follow exact backup tool prepare/restore steps |
| App reads stale data | Replicas or caches out of sync after cutover | Check replication, cache invalidation, and read routing |

## 12. Practices to Avoid

- Never overwrite production directly with a backup restore without a cutover and rollback plan.
- Never purge binary logs while determining the recovery point.
- Never replay binary logs past the corrupting transaction.
- Never stop replay mid-transaction.
- Never use an approximate timestamp as the final cutoff when GTID/position can be determined.
- Never pipe a row-decoded `mysqlbinlog` output file directly as a SQL replay stream.
- Never blindly swap an entire old table back over production if valid post-incident rows exist.
- Never ignore import/replay errors or treat a failing exit code as success.
- Never re-enable replica/read endpoints before verifying data integrity and replication lag.
- Never tamper with `GTID_PURGED` or binlog positions merely to make status look synchronized.

## 13. End-to-End Drill

### Environment setup

Spin up a test MySQL instance with InnoDB and binary logging enabled. Create the sample database:

~~~sql
CREATE DATABASE recovery_lab;
USE recovery_lab;

CREATE TABLE customer (
  customer_id BIGINT PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  account_status VARCHAR(20) NOT NULL,
  updated_at TIMESTAMP(6) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(customer_id)
) ENGINE = InnoDB;

INSERT INTO customer (customer_id, full_name, account_status)
VALUES
  (1, 'An Nguyen', 'ACTIVE'),
  (2, 'Binh Tran', 'ACTIVE'),
  (3, 'Chi Le', 'ACTIVE');

INSERT INTO orders (order_id, customer_id, total_amount)
VALUES (1001, 1, 250.00);
~~~

Take a consistent full backup and save binlog/GTID metadata alongside it. Execute a few valid transactions after the backup—for example, adding an order or updating an address if you add that column. Next, run the accidental update:

~~~sql
UPDATE customer
SET account_status = 'CLOSED';
~~~

Insert one more valid transaction after the mistake to test preserving post-incident data. Record timestamps, GTIDs, or positions for both the bad transaction and the subsequent valid transaction.

### Tasks

1. Collect `SHOW BINARY LOGS`, `SHOW BINARY LOG STATUS`, and the GTID set.
2. Decode with `mysqlbinlog` to pinpoint the bad transaction and the following transaction.
3. Restore the full backup onto an isolated recovery instance.
4. Replay binary logs from backup metadata up to right before the bad transaction.
5. Verify all customers are `ACTIVE` again on the recovery instance.
6. Check whether the valid order created after the mistake exists on the recovery instance.
7. Diff against production and design a merge plan restoring customer statuses while keeping the valid order.
8. Run the merge script on a staging copy, verifying foreign keys and invariants.
9. Measure restore, replay, validation, and merge durations.
10. Update the runbook and adjust retention/alerts if the workflow missed RPO/RTO targets.

### Completion criteria

- Recovery instance built from a verified consistent backup.
- Binary logs replayed continuously from exact backup coordinates.
- Corrupting transaction excluded from replay.
- Transaction boundaries preserved intact.
- Restored data validated with queries and invariants.
- Valid post-incident transactions identified and preserved by plan.
- Merge script includes pre-checks, post-checks, and rollback steps.
- Actual RPO/RTO timings recorded.

## 14. Operational Checklist

### Before an incident

- [ ] Scheduled full backups taken with consistent coordinate metadata.
- [ ] Binary logging enabled with sufficient retention.
- [ ] Archived binary logs verified with checksums and sequence checks.
- [ ] Backup restores tested periodically.
- [ ] PITR runbook specifies executor, approver, and recovery targets.
- [ ] Recovery instance or spare capacity provisionable within RTO.
- [ ] Dashboards monitor binlog disk usage, backup age, and restore times.

### During an incident

- [ ] Timeline and suspected transactions logged.
- [ ] Binary logs and audit/application logs preserved.
- [ ] Further corrupting writes restricted.
- [ ] Consistent base backup selected and recovery point identified.
- [ ] Backup restored onto an isolated instance.
- [ ] Binary logs replayed up to before the bad transaction.
- [ ] Data reconciled and merged within verified scope.
- [ ] Replication, caches, and read routing verified post-cutover.

### After an incident

- [ ] Data integrity and business invariants confirmed.
- [ ] Evidence, checksums, replay logs, and merge scripts archived.
- [ ] Actual RPO/RTO and bottlenecks documented.
- [ ] Retention, alerts, and migration/DDL permissions adjusted.
- [ ] Guardrails and peer-review steps added for dangerous DML statements.
- [ ] Next drill scheduled after any backup or architecture change.

## 15. Self-Check Questions

1. What two components does PITR require, and why is a standalone backup insufficient to recover to an arbitrary point in time?
2. Why must backups store accompanying GTID or binlog file/position metadata?
3. Which table types does `mysqldump --single-transaction` protect, and what limitation arises if concurrent DDL runs?
4. Why is preserving binary logs urgent immediately upon detecting an accidental update or delete?
5. How do you pinpoint a corrupting transaction inside row-based binary logs?
6. Why must `--stop-position` align cleanly on a transaction boundary?
7. During table recovery, why can't you simply overwrite the entire production table with a pre-incident snapshot?
8. How does a backup's transactional consistency point differ from backup file completion time?
9. How are RPO and RTO measured during a PITR drill?
10. What criteria must pass before promoting recovered data back into production?

Successful PITR is more than getting `mysqld` started or completing replay without errors. The team must prove the backup has a consistent coordinate, binary logs are continuous, the corrupting transaction was excluded, recovered data is reconciled, and valid post-incident transactions were handled deliberately. Periodic drills measuring real RPO/RTO are how you confirm the workflow holds up when a real production incident strikes.
