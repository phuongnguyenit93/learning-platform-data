# Replication and GTID

## Disconnections, apply errors, missing/extra transactions, and verified remediation plans

MySQL replication can stop progressing for two distinct groups of reasons: the replica cannot fetch new events from the source, or it has received events but cannot apply them to its local data. Additionally, data and GTID history between the two servers can diverge even while the connection remains active. To fix issues properly, operators must determine whether the fault lies in transport, the relay log, the applier, the data, or transaction history.

In the `DATABASE_MYSQL` module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Replication connects these skills to distributed operations: you must understand transactions, constraints, privileges, backups, and data state before letting a replica resume.

This lesson explains how to classify connection errors and apply errors, collect evidence, compare GTIDs to find missing/extra transactions, choose between repairing or rebuilding a replica, and verify the outcome. Examples use MySQL 8.0.22 and later syntax; in MySQL 5.7 and earlier 8.0 releases, command names still use `SLAVE`/`MASTER`. Cross-check your actual version before running commands.

### 1. Understanding the two replication streams

In asynchronous replication, a replica has two primary worker streams:

1. **Receiver (I/O thread):** connects to the source, reads binary log events, and writes them to the relay log on the replica.
2. **Applier (SQL thread or workers):** reads the relay log and executes transactions on the replica.

When the receiver stops, the replica receives no new events. When the applier stops, events may still be received and accumulate in the relay log while data on the replica makes no progress. These two states require different diagnostic approaches.

`SHOW REPLICA STATUS` provides an overall status snapshot:

```sql
SHOW REPLICA STATUS\G
```

Key fields:

| Field | Diagnostic meaning |
|---|---|
| `Replica_IO_Running` | `Yes` indicates the receiver is running; `Connecting` usually indicates it is attempting to connect; `No` indicates the thread has stopped |
| `Replica_SQL_Running` | `Yes` indicates the applier is running; `No` typically accompanies an apply error or an intentional stop |
| `Last_IO_Errno`, `Last_IO_Error` | Code and message of the most recent receiver error |
| `Last_SQL_Errno`, `Last_SQL_Error` | Code and message of the most recent applier error |
| `Source_Host`, `Source_Port`, `Source_UUID` | Identifies the source the replica is following |
| `Retrieved_Gtid_Set` | GTIDs received into the relay log for the channel |
| `Executed_Gtid_Set` | Set of GTIDs executed on the replica; reflects server-wide state and may span multiple sources/channels |
| `Seconds_Behind_Source` | Timestamp-based lag estimate; not sole proof that the replica is synchronized |

On MySQL 5.7 or older 8.0 releases without the new names, use:

```sql
SHOW SLAVE STATUS\G
```

Some versions display field names prefixed with `Slave_` instead of `Replica_`. With multiple channels, inspect each channel individually using the `FOR CHANNEL` syntax supported by your version.

Do not look solely at `Seconds_Behind_Source`. Its value can be `NULL` when the applier is not running or suitable metadata is absent; it can also fail to fully reflect lag during long transactions or multi-worker execution. Combine both thread statuses, GTIDs, relay logs, heartbeats, and commit timestamps.

### 2. Collecting evidence before repairing

When replication fails, the very first step is saving state so the root cause can be reconstructed. Never run `RESET REPLICA`, delete relay logs, skip transactions, or alter GTIDs before collecting evidence.

On the replica, save the output of:

```sql
SELECT VERSION() AS mysql_version,
       @@server_uuid AS server_uuid,
       @@GLOBAL.gtid_mode AS gtid_mode,
       @@GLOBAL.gtid_executed AS gtid_executed,
       @@GLOBAL.gtid_purged AS gtid_purged,
       @@GLOBAL.read_only AS read_only,
       @@GLOBAL.super_read_only AS super_read_only;

SHOW REPLICA STATUS\G
SHOW BINARY LOGS;
```

On MySQL versions with Performance Schema replication tables, inspect connection errors:

```sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_connection_status;
```

Inspect coordinator and applier worker errors:

```sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_applier_status_by_coordinator;

SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  APPLYING_TRANSACTION,
  LAST_APPLIED_TRANSACTION,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_applier_status_by_worker
WHERE LAST_ERROR_NUMBER <> 0
   OR APPLYING_TRANSACTION <> '';
```

Performance Schema tables and columns may differ by version and configuration. If a query fails, inspect the schema of your current version and use `SHOW REPLICA STATUS` along with the error log as your reference.

Record at minimum:

- Incident start time, first error timestamp, and most recent changes on source/replica.
- Failing channel, source name, receiver/applier status, and error numbers/messages.
- `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `gtid_executed`, `gtid_purged`, and file/position coordinates if using file-position replication.
- Relay log file/position, currently applying transaction, and failing worker if applicable.
- MySQL error log, network/TLS logs, and configuration or privilege changes near the incident time.
- Data state of affected tables, latest backup, and available binlogs/archives.

Capture values within the same narrow time window. If the source keeps writing transactions while you inspect replica status, the two GTID sets can shift between queries; record timestamps to avoid comparing asynchronous snapshots.

### 3. Receiver errors: connection loss or unreadable binlogs

The receiver typically fails due to network, DNS, firewall, TLS, replication account, source configuration, or missing binary logs.

| Symptom | Causes to check |
|---|---|
| Persistent `Replica_IO_Running: Connecting` | Source unreachable, wrong host/port, DNS, firewall, or source not listening |
| Authentication errors like `Access denied` | Wrong password, replication account host mismatch, missing `REPLICATION SLAVE` / equivalent privilege |
| TLS/SSL errors | CA, certificate, hostname, expiry, or mismatched TLS settings on both sides |
| Abnormal source UUID or server identity | Replica connected to wrong instance, cloned server without changing `server_uuid` properly, or misconfigured topology |
| Error 1236 / binlog not found | Source purged/reset the file the replica needs, wrong file/position, or incomplete archive |
| Receiver running yet relay log does not grow | Source generating no new events, receiver stalled, or relay log storage/write issue |

Investigation procedure:

1. Confirm `Source_Host`, `Source_Port`, and `Source_UUID` match the intended source.
2. Verify TCP connectivity from replica to source, DNS, routing, firewall, and MySQL listener status.
3. Verify the replication account on the source, host pattern, privileges, and authentication plugin/method.
4. Check TLS on both sides: trusted CA, valid certificate expiry, hostname verification, and encryption requirements.
5. Compare the source's binary log list with the file/position or GTIDs the replica needs to receive.
6. Check source and replica logs to distinguish network failures from the source having deleted required logs.

If the source still retains the required binlogs and GTIDs, fixing network/privileges/TLS usually allows the receiver to resume from its saved position. If the source has already purged files the replica needs, reconnecting cannot recreate the lost history. Locate a verified binlog archive or prepare to rebuild the replica from a fresh consistent backup.

After remediation, you can start only the receiver if needed:

```sql
START REPLICA IO_THREAD;
```

On older versions, the corresponding syntax is `START SLAVE IO_THREAD`. Run this only after identifying the root cause and confirming the source/required files are available. Never repeatedly restart the thread without fixing the root cause; that only clutters logs and obscures the true failure timestamp.

### 4. Applier errors: received but failed to apply

The applier can stop when a transaction from the source violates data state or schema on the replica. Two common error codes under row-based replication are:

- **1032 — Can't find record:** an `UPDATE` or `DELETE` event requires a row that the replica cannot find.
- **1062 — Duplicate entry:** an `INSERT` event creates a key that already exists on the replica.

These two errors usually signal that data on both sides diverged prior to the failing transaction. Causes may include direct writes to the replica, manual data edits, replication filters, restoring from the wrong point in time, missing prior transactions, or schema mismatches.

Other causes include missing tables/columns, differing data types, differing collations, incompatible constraints or foreign keys, missing storage engines/plugins, and failing DDL statements. Under statement-based replication, non-deterministic behavior or environmental differences can also produce divergent outcomes.

When `Replica_SQL_Running` is `No`:

1. Save `Last_SQL_Error`, worker ID, `APPLYING_TRANSACTION`, and the failing transaction's GTID if available.
2. Inspect source/replica schemas with `SHOW CREATE TABLE`; compare columns, indexes, constraints, engines, charsets, and collations.
3. Use `mysqlbinlog` to inspect the source transaction. For row-based events, decode them to view human-readable before/after row data.
4. Inspect the affected row on both source and replica using the primary key or unique key.
5. Determine why the data states differ and whether prior transactions were missed or out-of-band writes occurred.
6. Choose between repairing data, skipping a transaction proven unnecessary to apply, or rebuilding the replica.

Example reading a saved binlog file:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

If the failing GTID is known, you can filter to inspect the transaction scope with `mysqlbinlog --include-gtids='uuid:transaction_number'` on the corresponding binlog file. Obtain the file name and GTID from real evidence; never guess from timestamps or error sequence numbers.

With a multi-threaded applier, an error may appear in one worker while the coordinator manages transaction order and dependencies. Inspect `replication_applier_status_by_worker` and the coordinator table; never read just one summary line and overlook a failing worker. Handling MTS gaps must follow your version's procedure and worker state.

### 5. Comparing missing and extra transactions using GTID

GTIDs allow comparing executed transaction sets. Suppose:

- `S` is the source's `gtid_executed` at capture time.
- `R` is the replica's `gtid_executed` at the corresponding time.

Then:

- `GTID_SUBTRACT(S, R)` shows transactions executed on the source that are not yet in the replica's executed set.
- `GTID_SUBTRACT(R, S)` shows transactions executed on the replica that are absent from the compared source's executed set.

Example:

```sql
-- Capture both values from the same comparison time window.
SET @source_gtids = 'uuid-a:1-1200';
SET @replica_gtids = 'uuid-a:1-1190';

SELECT
  GTID_SUBTRACT(@source_gtids, @replica_gtids)
    AS missing_on_replica,
  GTID_SUBTRACT(@replica_gtids, @source_gtids)
    AS extra_on_replica;
```

In this example, the replica is missing `uuid-a:1191-1200` and has no extra GTIDs relative to the source set. This is a GTID set comparison, not a row-by-row content check.

If `missing_on_replica` is non-empty, determine for those GTIDs:

- Have they already been received into the relay log? Cross-check `Retrieved_Gtid_Set`.
- Is the applier waiting or stopped on an earlier transaction?
- Does the source still retain binlogs containing these transactions?
- Were the transactions purged, yet still exist in archives?
- Is the replica following the right source/channel?

If `extra_on_replica` is non-empty, never automatically delete or mark those GTIDs as processed. They may be direct writes on the replica, transactions from another source in a multi-source topology, or valid data from an earlier recovery. Identify the origin UUID, channel, timestamp, and data impact of each group.

A server's global GTID set may combine multiple channels. In multi-source replication, comparing global sets is insufficient to conclude which channel is missing transactions. Check each channel's status, GTID origins, and actual topology.

Furthermore, `Retrieved_Gtid_Set` differs from `Executed_Gtid_Set`: a transaction may be received into the relay log without yet being applied by the applier. Therefore, a gap between source and replica does not always mean transactions were lost; they may be queued in the relay log or blocked behind an earlier apply error.

### 6. Choosing a verified remediation path

No single skip operation fits every error. Choose an approach based on evidence of transactions, data, and recoverability.

#### 6.1. Fix connectivity and resume

Choose this when the source retains sufficient binlogs, replica data has not been altered out-of-band, and the failure is due to network, DNS, TLS, or privileges. Fix configuration, start the receiver, confirm the relay log grows, and verify the applier continues processing. Then verify GTIDs and data.

#### 6.2. Repair replica data and restart the applier

Choose this when you have proven which rows are wrong and what the exact right values must be. For example, error 1032 may require restoring a missing row on the replica; error 1062 may require verifying whether a duplicate row represents the same change or conflicting business data.

Minimum workflow:

1. Stop the applier to prevent state from shifting during inspection:

   ```sql
   STOP REPLICA SQL_THREAD;
   ```

2. Save the failing transaction and pre-repair data; confirm the source is the canonical truth to follow.
3. Repair the exact rows/schema on the replica using a tested plan, ensuring the operation does not create out-of-band transactions that skew GTIDs or propagate downstream.
4. Reconcile the repaired rows against the source and verify related constraints.
5. Start the applier:

   ```sql
   START REPLICA SQL_THREAD;
   ```

6. Monitor workers, error logs, GTID sets, and data for subsequent transactions.

Repairing directly on a replica in GTID mode requires a concrete plan to avoid creating errant transactions. Never assume `SET sql_log_bin=0` works identically across every version or GTID state. Verify logging mechanics and privileges for your exact version before executing.

#### 6.3. Skip a transaction only when proven safe

Skipping a transaction means the replica will not execute that transaction's effects. Consider this only when you have verified replica data already matches the post-transaction state, or when the transaction is genuinely unnecessary per business decision. Record the GTID, contents, rationale, approver, and comparison evidence.

In GTID mode, one way to handle a specific transaction is injecting an empty transaction carrying the exact GTID to skip so the applier recognizes that GTID as executed. The sample below is strictly for labs or verified runbooks when the applier is stopped and the GTID is not yet in `gtid_executed`:

```sql
STOP REPLICA SQL_THREAD;

SET GTID_NEXT = 'source_uuid:transaction_number';
BEGIN;
COMMIT;
SET GTID_NEXT = 'AUTOMATIC';

START REPLICA SQL_THREAD;
```

Replace `source_uuid:transaction_number` with the actual GTID of the failing transaction. An empty transaction does not recreate data; it only marks that GTID as processed. When the applier encounters the transaction with that GTID in the relay log, MySQL skips it because the GTID is already executed. If replica data was not already equivalent, this creates an intentional data gap that can cause business errors later.

In non-GTID configurations, some versions support a skip counter variable such as `sql_slave_skip_counter` or the newer `sql_replica_skip_counter`. These variables have version-specific limits, cannot be used when `gtid_mode=ON`, and can interact subtly with multi-threaded appliers. Use them only per version documentation and tested runbooks; never make event skipping a default habit.

#### 6.4. Rebuild the replica from backup when divergence is broad

If multiple missing/extra transactions exist, data differs across many tables, the source has purged required logs, or per-row repair cannot be proven safe, rebuilding the replica is usually the more controllable option.

General workflow:

1. Record current source/channel configuration, GTIDs, filters, TLS, replication user, and backup coordinates.
2. Prepare a consistent backup from the source suited to your version and topology.
3. Restore the replica from the backup following the procedure; apply GTID or file/position metadata provided by the backup.
4. Configure the source and channel. With GTID auto-position on supported versions:

   ```sql
   CHANGE REPLICATION SOURCE TO
     SOURCE_HOST = 'mysql-source.example.net',
     SOURCE_PORT = 3306,
     SOURCE_USER = 'repl_user',
     SOURCE_AUTO_POSITION = 1;
   ```

   This example omits password and TLS options; use secret management and approved security settings. On older versions, the syntax is `CHANGE MASTER TO` and `MASTER_AUTO_POSITION=1`.

5. Start replication and verify receiver/applier, GTIDs, lag, and data.
6. Return the replica to service only after all acceptance checks pass.

Never run `RESET REPLICA ALL` as a default step before saving configuration: this command can erase the channel's source connection metadata. Reset metadata only when the rebuild runbook calls for it and you have saved everything needed to reconfigure.

### 7. Verification after remediation

A thread reporting `Yes` does not prove the replica is synchronized or data is accurate. After remediation, verify in multiple layers:

**Thread status.** Receiver and applier must be running as designed. `Last_IO_Error` and `Last_SQL_Error` show no new errors. Check every worker if the parallel applier is enabled.

**GTID.** Compare `gtid_executed` between source and replica after pausing source writes or at a comparable snapshot point. If the source continues accepting transactions, record timestamps and verify the expected delta. Confirm `Retrieved_Gtid_Set` holds no unexpected backlog.

**Data.** Comparing row counts is only a preliminary check. Verify checksums or compare by keys, related tables, foreign keys, monetary totals, order counts, inventory, and business invariants. On large systems, appropriate table checksum tools can be used, provided load and locking scope are evaluated.

**Read-only and write permissions.** If the replica serves reads only, verify `read_only` and `super_read_only` match design, and confirm applications are not sending accidental writes to the replica. Administrative accounts still need tight control.

**Post-recovery replication.** Observe through at least one realistic workload cycle; check long transactions, DDL, events, and background jobs. Record the GTID set, lag, time synchronization was achieved, and data check results.

### 8. Hands-on scenario

A system has source `db-primary` and replica `db-read-1`, using GTID and row-based replication. After an administrator manually edits the `orders` table directly on the replica, the applier stops with error 1062 upon receiving an insert transaction from the source. The receiver keeps running and the relay log continues growing.

Draft a remediation plan and answer:

1. Which fields from `SHOW REPLICA STATUS` and which Performance Schema tables must you save to identify the failing worker, transaction, and channel?
2. Why does the receiver keep running while the applier is stopped? What does that imply about `Retrieved_Gtid_Set` and `Executed_Gtid_Set`?
3. Which keys will you use to compare the `orders` row on source and replica? Which related tables must be checked before repairing?
4. Under what conditions can you repair the row on the replica and resume the applier? What evidence proves the repair is correct?
5. Why should you not immediately create an empty GTID transaction upon seeing error 1062?
6. If multiple extra GTIDs from direct writes on the replica are discovered and data diverges across several tables, why can rebuilding the replica be safer than row-by-row repair?
7. Write an acceptance checklist before allowing applications to read from `db-read-1` again.

### 9. Checklist for responding to replication failures

- [ ] Identified the exact source, replica, channel, and MySQL version.
- [ ] Collected `SHOW REPLICA STATUS` along with receiver/applier and worker errors before making changes.
- [ ] Saved GTID sets, file/position, relay log metadata, and backup/archive status.
- [ ] Distinguished connection errors, apply errors, unreceived transactions, and received-but-unapplied transactions.
- [ ] Compared affected data/schemas; identified the root cause of drift.
- [ ] Identified missing/extra GTIDs with `GTID_SUBTRACT` and analyzed the origin of each group.
- [ ] Chose data repair, verified skip, or re-seed based on evidence and approval.
- [ ] Did not delete relay logs, reset channels, or alter GTID metadata before saving state and understanding impact.
- [ ] Verified receiver/applier, GTIDs, backlog, data, and business invariants after remediation.
- [ ] Recorded change ticket, evidence, operator, and timestamp when the replica was accepted back into service.

### 10. Operational principles

When replication stops, determine whether transactions are blocked in transport or stalled at the applier. When GTIDs diverge, distinguish unreceived transactions, received-but-unapplied transactions, and transactions existing on only one side. Error 1032 or 1062 typically signals data has already diverged; skipping the transaction may silence the error while leaving the divergence intact. Repair only when the true state is known, and skip only after proving the transaction's effects are no longer needed. If the correctness of a local repair cannot be proven, rebuild the replica from a consistent backup and verify GTIDs and data before returning it to service.
