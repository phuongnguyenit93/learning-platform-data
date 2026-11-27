# Protecting logs still needed by replicas and detecting out-of-band transactions

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. This lesson focuses on two critical tasks when operating GTID-enabled replication: retaining binary logs long enough for replicas to still catch up, and detecting transactions that appear on a replica without belonging to the source's valid history.

A replica can stop receiving logs due to network loss, maintenance, or server failure. If the source deletes binary logs that a replica still needs, the replica cannot retrieve those lost transactions from that source on its own. Similarly, a direct write on a replica can create an out-of-band transaction (errant transaction), causing GTIDs across servers to fall out of alignment. You must manage retention, monitor progress, and verify GTIDs before changing topology or performing failover.

## 1. Distinguishing binary logs and relay logs

Replication uses two types of logs with distinct roles:

| Log type | Where created | Role | Risk if lost or deleted prematurely |
|---|---|---|---|
| Binary log (binlog) | Source; may also exist on replica if `log_bin` is enabled | Records transactions for replicas, CDC tools, and PITR procedures to read. | Replicas may be unable to fetch missing transactions; PITR may fail to reach the target recovery point. |
| Relay log | Replica | Stores events received from the source awaiting execution by the applier. | Replica may lose events received but not yet applied; must re-fetch from source if source logs still exist. |

The fundamental replication flow is that the source writes transactions to its binary log, the receiver thread on the replica reads the log and writes to the relay log, and then the applier applies events to the data. Therefore, a transaction existing in the relay log does not mean it has been applied to tables. With GTID, you can track the received transaction set and executed transaction set separately.

On the replica, `SHOW REPLICA STATUS\G` provides details such as `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `Source_Log_File`, `Read_Source_Log_Pos`, `Relay_Source_Log_File`, and `Exec_Source_Log_Pos`. These fields identify how far the replica has received and how far the applier has processed.

## 2. Establishing a binary log retention policy

### Calculating retention duration from actual needs

Binary log retention must be long enough for every log consumer, including:

- Replicas that may disconnect during maintenance, network outages, or infrastructure failures.
- Time to detect a lagging replica, resolve the root cause, and bring the replica back online.
- Time needed to restore or rebuild a replica from backup/clone if a server is lost.
- Intentionally delayed replicas (delayed replica).
- CDC tools, analytics pipelines, or other services reading binlogs.
- Point-in-time recovery (PITR) workflows needing logs after a backup point.

One planning approach is taking the maximum expected outage duration plus time to detect, repair, or rebuild a replica, then adding a safety margin. If a replica could stay offline for 3 days and need another 1 day to restore, verify, and catch up, a 4-day retention leaves zero buffer. The system must also account for binlog generation rate and storage capacity to guarantee enough space for the chosen retention window.

Never choose retention based solely on a daily backup schedule. A replica can stay offline longer than one backup cycle; a delayed replica intentionally requires older logs; a PITR procedure may require several days of logs after a full backup.

### Configuring automatic expiration

In MySQL 8.0, `binlog_expire_logs_seconds` sets the duration in seconds that binary logs are kept before becoming eligible for expiration. The following example sets 14 days:

```sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
```

`SET PERSIST` saves the value across restarts on supported versions. Fourteen days is only an example; calculate retention based on your topology, log generation rate, recovery time, and PITR requirements. If using legacy configuration based on `expire_logs_days`, consult your MySQL version's documentation before converting.

Check the active setting and list of binary logs:

```sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
```

Automatic expiration is based on log age, not proof that every replica has finished receiving all events in the file about to be deleted. A replica offline longer than the retention window may still need expired files. Therefore, retention must be wide enough and alerts must fire as a replica approaches the available log boundary.

### Manual binary log deletion

MySQL lets you remove old logs with `PURGE BINARY LOGS`. Example:

```sql
PURGE BINARY LOGS TO 'mysql-bin.000120';
```

This statement deletes binary logs preceding `mysql-bin.000120`; the named file itself is not deleted. You can also specify a timestamp:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Before purging, verify that all replicas have received the transactions in the files to be deleted, delayed replicas no longer need them, and backup/PITR or CDC no longer depend on them. Never assume replicas are safe merely because the purge command succeeded. Manual purging does not replace checking replication status.

Never delete binlog files directly via OS filesystem commands. Use MySQL administrative statements so the server properly updates its binary log index and related metadata.

## 3. Monitoring replicas before logs expire

On each replica, inspect receiver and applier status:

```sql
SHOW REPLICA STATUS\G
```

Key fields:

| Field | Operational meaning |
|---|---|
| `Replica_IO_Running` | Indicates whether the receiver stream fetching events from the source is running. |
| `Replica_SQL_Running` | Indicates whether the applier stream is running. |
| `Source_Log_File`, `Read_Source_Log_Pos` | File and position the receiver is reading from the source. |
| `Relay_Source_Log_File`, `Exec_Source_Log_Pos` | Source file and position corresponding to apply progress. |
| `Retrieved_Gtid_Set` | GTIDs received by the replica. |
| `Executed_Gtid_Set` | GTIDs executed on the replica. |
| `Last_IO_Error`, `Last_SQL_Error` | Errors in the receiver or applier thread. |
| `Seconds_Behind_Source` | Estimated lag; may not fully reflect state when a thread is stopped or timing data is missing. |

Never rely solely on `Seconds_Behind_Source` when deciding to purge. A replica may report low lag while holding an error, or the receiver may have stopped without updating metrics as operators expect. Inspect both thread statuses, GTID sets, file/position, and error messages.

On the source, monitor existing binary logs:

```sql
SHOW BINARY LOGS;
SELECT @@GLOBAL.gtid_executed, @@GLOBAL.gtid_purged;
```

`gtid_executed` is the set of GTIDs the server has executed. `gtid_purged` is the set of GTIDs for transactions already executed whose corresponding binary logs are no longer retained on the server. `gtid_purged` helps identify purged history; it does not contain transaction contents and cannot substitute for deleted binlog files.

With GTID auto-position, the replica asks the source to supply transactions the replica lacks. If the source has purged required binary logs and has no other way to supply those transactions, the replica cannot catch up merely by reconnecting. In that case, you typically must rebuild the replica from a newer backup or clone with consistent GTID state, then let the replica continue receiving new transactions.

## 4. Protecting logs on intermediate replicas and relay logs

### When a replica serves downstream replicas

In a multi-tier topology, a replica can simultaneously act as a source for other replicas. The intermediate server must enable binary logging and `log_replica_updates=ON` so transactions received from upstream and applied locally are also written into its own binary log.

Basic configuration example on an intermediate replica:

```ini
[mysqld]
server_id=102
log_bin=mysql-bin
log_replica_updates=ON
gtid_mode=ON
enforce_gtid_consistency=ON
```

If `log_bin` is off, the server has no binary logs for downstream replicas to read. If `log_replica_updates` is off, transactions applied from the source are not written onward into the replica's binary log; downstream replicas may miss required transaction history from the intermediate server. On older versions, the corresponding variable name is `log_slave_updates`.

Intermediate servers also need long enough retention for downstream replicas. Having the top-level source keep logs for 30 days will not help downstream if the intermediate replica keeps logs for only 1 day and a downstream replica goes offline for 3 days. Each tier needs its own policy tailored to the outage window and rebuild time of replicas depending on it.

### Managing the relay log

MySQL manages relay log lifecycle through the replication mechanism. `relay_log_purge` is normally enabled to automatically delete relay logs already processed by the applier. Never manually delete relay logs with OS commands, even if many old files appear in the data directory. If relay logs fill disk or the replica stops applying, address the root cause such as SQL errors, disk capacity, locked transactions, or applier configuration.

When recovering after a replica server crash, follow MySQL's recovery procedure and verify relay logs, executed positions, GTID sets, and binary logs remaining on the source. Never delete relay logs to "clean up" and restart replication without understanding which transactions were received but not yet applied.

## 5. What is an out-of-band (errant) transaction?

An errant transaction is a transaction whose GTID appears in a replica's executed history without belonging to the valid transaction set inherited from the source or approved topology. The common case is an administrator or application writing directly to a replica when the replica is expected to receive data only via replication.

Example:

1. The source holds GTID transactions generated by the source and transmitted to the replica.
2. An administrator temporarily disables read-only mode and runs an `UPDATE` directly on the replica.
3. The replica records the local transaction with its own SID/UUID into GTID history.
4. When compared with the source, this local GTID appears on the replica but is absent from the source's GTID set.

Errant transactions can cause data on the two servers to diverge. When a replica is promoted to become the new source, the out-of-band transaction can propagate to other replicas or produce an unintended GTID history. GTID auto-position does not understand the business meaning of a transaction and does not fix diverged data automatically.

Common sources of errant transactions:

- Running `INSERT`, `UPDATE`, `DELETE`, or DDL directly on a replica using an admin account.
- Turning off `read_only`/`super_read_only` to fix an issue and forgetting to re-enable it.
- Running maintenance scripts, events, or local jobs that perform writes on the replica.
- Using a replica as a testing or reporting environment while permitting data writes.
- Performing manual writes during failover preparation.

## 6. Detecting errant transactions using GTID sets

### Collecting GTID sets from source and replica

On the intended source, record its UUID and executed GTID set:

```sql
SELECT
    @@GLOBAL.server_uuid AS source_uuid,
    @@GLOBAL.gtid_executed AS source_gtid_executed;
```

On the replica under inspection:

```sql
SELECT
    @@GLOBAL.server_uuid AS replica_uuid,
    @@GLOBAL.gtid_executed AS replica_gtid_executed,
    @@GLOBAL.gtid_purged AS replica_gtid_purged;
```

In a single-source, single-replica model, a healthy replica will have an executed GTID set consisting of valid transactions transmitted by the source, possibly lagging behind partially if the applier has not caught up. To find GTIDs present on the replica that are missing from the source's set, copy the `source_gtid_executed` value from the source into a variable in the replica session:

```sql
SET @expected_source_gtids = 'SOURCE_GTID_EXECUTED_COPIED_FROM_SOURCE';

SELECT
    GTID_SUBTRACT(@@GLOBAL.gtid_executed, @expected_source_gtids)
        AS extra_gtids_on_replica,
    GTID_SUBTRACT(@expected_source_gtids, @@GLOBAL.gtid_executed)
        AS source_gtids_not_yet_executed;
```

The two results have different meanings:

- `extra_gtids_on_replica`: GTIDs executed on the replica that are absent from the canonical source GTID set. In a single-source topology, this set warrants investigation because it may contain errant transactions.
- `source_gtids_not_yet_executed`: GTIDs present on the source that the replica has not yet executed. These are typically transactions the replica is missing or has not finished applying, not errant transactions.

`GTID_SUBTRACT(set1, set2)` returns GTIDs present in `set1` that are absent from `set2`. Therefore, argument order is critical. Never conclude an errant transaction exists simply because two GTID strings look different; determine which transaction set constitutes valid history for the topology.

### Limitations when interpreting results

The comparison above fits an identified single-source topology. With multi-source replication, multiple channels, replication filters, or topologies that have changed sources, the valid GTID set may include transactions from multiple SIDs. In those cases, construct the expected GTID set from all valid sources/channels; comparing a replica against only one source may falsely flag valid transactions as out-of-band.

GTID sets also reflect only transactions recorded in GTID history. Data modifications made while binary logging is disabled via `sql_log_bin=0` may not produce GTIDs for this comparison to detect. Some forms of data drift or corruption also do not necessarily create differing GTIDs. Therefore, combine GTID checks with audit logs, account privileges, business data checks, and checksum comparisons when needed.

## 7. Preventing out-of-band transactions

On read-only replicas, enable read-only mode:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`super_read_only=ON` also enables `read_only` and blocks most client write operations, including accounts with high administrative privileges; the replication applier can still apply transactions from the source. Users with sufficiently high admin privileges can still alter settings, so this is an important defense layer rather than a substitute for privilege control and auditing.

Additional operational measures:

1. Grant write privileges to application accounts only on the source; separate admin accounts from reporting read accounts.
2. Restrict who can disable `read_only` or `super_read_only`, and log every configuration change.
3. Never run business jobs, events, or scripts containing writes on a read replica.
4. Monitor changes to read-only status, administrative actions, and statements capable of creating local transactions.
5. Before failover, inspect the candidate's GTID set and verify no out-of-band transactions exist.
6. After topology changes, update runbooks so all intentional writes flow through the new source.

Check current status:

```sql
SHOW VARIABLES LIKE 'read_only';
SHOW VARIABLES LIKE 'super_read_only';
```

If a maintenance requirement forces direct writes on a replica, obtain approval, log the statements and data scope, assess GTID impact, and restore the replica to a clean state before resuming replication or listing it as a failover candidate.

## 8. Handling detected errant GTIDs

When `extra_gtids_on_replica` is non-empty, halt promoting that replica until those transactions are fully understood. An investigation procedure can include:

1. **Preserve evidence.** Record `server_uuid`, `gtid_executed`, `gtid_purged`, replication status, binary logs, and discovery timestamp. Take a backup/clone for analysis before altering state.
2. **Identify the transactions.** If binary logs still exist, use `mysqlbinlog` to inspect the relevant GTIDs and identify the modified statements or data. Example:

   ```bash
   mysqlbinlog --include-gtids='REPLICA_UUID:120-122' mysql-bin.000045
   ```

   Replace UUID, GTID range, and file name with actual values. Never include sensitive data or statements containing secrets in public reports.

3. **Trace the origin.** Find the account, job, event, or admin operation that generated the transaction. Verify whether it was approved or an out-of-process change.
4. **Assess the data.** Compare affected records against the source and business requirements. A differing GTID signals differing transaction history; by itself it does not tell you whether the change was right or wrong.
5. **Choose recovery.** If the replica has drifted and correctness cannot be proven, the safe approach is usually rebuilding from a consistent backup/clone of a valid source, preserving exact GTID state per tool instructions, and reconnecting via GTID auto-position. If the transaction was a valid change that must be kept, plan a controlled data and topology reconciliation.
6. **Post-remediation verification.** Re-compare GTID sets, verify business data, confirm the replica catches up, and re-enable monitoring alerts.

Never delete a single GTID from `gtid_executed` by editing metadata, never arbitrarily assign `GTID_PURGED`, and never run binary log/GTID reset commands to hide differences. Those actions can erase needed history or prevent the topology from recovering cleanly. Use only GTID recovery procedures supported by MySQL documentation or topology management tooling, after taking a backup and understanding the consequences.

## 9. Periodic operational workflow

A log and GTID management workflow should run periodically:

1. **Inventory the topology.** Document sources, intermediate replicas, downstreams, delayed replicas, channels, and CDC/PITR tools consuming binlogs.
2. **Set retention.** Factor in maximum outage duration, rebuild duration, and safety margin; check log generation rate to forecast storage capacity.
3. **Monitor health.** Collect receiver/applier status, replication errors, retrieved/executed GTIDs, existing binary logs, and age of the oldest retained log.
4. **Alert early.** Alert when a replica is offline or nearing the retention window; alert when semi/async mode, GTID sets, or read-only status change unexpectedly.
5. **Review before purging.** Verify every replica and consumer has passed the log boundary about to be deleted; ensure backup/PITR no longer needs those logs.
6. **Audit for errant transactions.** Compare GTID sets against the valid topology after maintenance windows, special write operations, and before every failover.
7. **Rehearse rebuilds.** Practice restoring a replica from backup/clone and catching up via binlogs; record timing and any gaps in the runbook.

## 10. Hands-on exercise

Set up one GTID-enabled source and one replica in a test environment. Run the following scenarios:

1. Record `@@GLOBAL.gtid_executed` and `@@GLOBAL.gtid_purged` on the source; record `Retrieved_Gtid_Set` and `Executed_Gtid_Set` on the replica.
2. Pause the replication receiver in the test environment, generate more transactions on the source, and identify which binary logs the replica needs to catch up.
3. Check `binlog_expire_logs_seconds`, `SHOW BINARY LOGS`, and design a retention window covering a simulated offline duration plus rebuild time.
4. Create a controlled local transaction on the replica in the test environment, then compare GTID sets with `GTID_SUBTRACT()` to find GTIDs present only on the replica.
5. Restore the replica to read-only state, investigate the out-of-band transaction, and draft a rebuild or data reconciliation plan.
6. If using an intermediate replica, check `log_bin` and `log_replica_updates`, then verify a downstream replica receives valid transactions.
7. Write a report covering retention, log size, extra/missing GTIDs, replication errors, remediation steps, and re-verification results.

After the exercise, learners should be able to explain why a source might purge logs a replica still needs, why `gtid_purged` cannot substitute for binary log contents, why `Retrieved_Gtid_Set` differs from `Executed_Gtid_Set`, and how to distinguish out-of-band transactions from transactions a replica is simply slow to apply. This is the foundation for keeping a MySQL topology able to catch up and reducing failover risks.
