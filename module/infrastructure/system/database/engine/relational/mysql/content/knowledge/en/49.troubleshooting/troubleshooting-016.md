# Replica Lag, Apply Errors, and Transactions Missing from Binary Logs

MySQL replication transfers changes from source to replica through binary logs and relay logs. A replica can fall behind the source because it has not received all events, has not finished applying received events, or stopped due to an error. A more severe scenario occurs when a replica needs a transaction whose binary log has already been purged from the source. In that case, simply restarting replication will not fix it; you must pinpoint the missing data range and choose a safe resynchronization method.

Investigation must separate three states: the I/O thread reading binary logs from the source, the SQL or applier thread applying relay logs, and the history of executed transactions. A replica can receive events rapidly while applying slowly, or apply smoothly while receiving nothing due to network or source issues. If needed transactions were purged, recover from a consistent copy with matching GTID history or rebuild the replica.

This lesson covers mastering MySQL from replication, transactions, and concurrency control to operational troubleshooting. It focuses on classifying lag, reading replication status, resolving apply errors, and recovering when binary logs no longer hold transactions required by a replica.

## 1. Distinguishing Replication Stages

In standard asynchronous replication, the source writes committed transactions to the binary log. The replica's I/O thread connects to the source, reads events, and writes them to the local relay log. The SQL thread or applier workers read the relay log and execute transactions on the replica.

~~~mermaid
flowchart LR
    A["Client writes transaction"] --> B["Source: binary log"]
    B --> C["Replica I/O thread"]
    C --> D["Replica: relay log"]
    D --> E["SQL thread / applier workers"]
    E --> F["Replica data"]
    C -. "Network, TLS, grants, binlog" .-> X["Receive error"]
    E -. "SQL, schema, locks, resources" .-> Y["Apply error"]
~~~

Three stages to distinguish:

- **Receive:** replica connects to the source and reads events from the binary log.
- **Queue:** events have been received into the relay log, awaiting the applier.
- **Apply:** replica executes transactions and updates local data.

Replica lag can build up at any stage:

| Observation | Likely Causes to Check |
|---|---|
| I/O thread stopped or failing to connect | DNS, network, firewall, TLS, replication account, source log purged |
| I/O thread running while SQL thread stopped | SQL apply error, schema drift, duplicate key, missing row, disk, or locks |
| Both threads running while lag climbs | Source write rate exceeds apply rate, large transactions, insufficient replica resources |
| Relay logs growing continuously | I/O receives faster than applier processes |
| No new relay logs and replica idle | Source has no new writes, I/O thread disconnected, or wrong read position |
| Replica has fresh data yet queries see stale data | Queries hitting wrong endpoint, stale transaction snapshot, or another replica lagging |

In MySQL 8, `source`/`replica` terminology is used in newer statements. Some older versions or tools still display `master`/`slave`. Use the exact syntax supported by your running version.

## 2. Measuring Replica Lag Properly

### 2.1. Do Not Rely Solely on `Seconds_Behind_Source`

`SHOW REPLICA STATUS` provides `Seconds_Behind_Source`. This is a useful indicator, not a flawless measurement of data lag.

- When the I/O thread is disconnected, the value can be `NULL` or fail to reflect real lag accurately.
- When the source has no new transactions, a low number does not prove the replica received the latest heartbeat.
- With parallel appliers, transactions execute across multiple workers; one single-threaded metric cannot fully represent all pending transactions.
- Clock skew, long-running transactions, and commit timestamps can distort second-based interpretations.
- Intentionally configured replication delay also raises lag without being an error.

Use `Seconds_Behind_Source` alongside I/O/applier states, GTIDs, relay logs, worker errors, and time-series metrics. Define lag SLOs per business need, such as maximum tolerated lag for reporting queries or read-after-write flows.

### 2.2. Inspecting Overall Status

On the replica, run:

~~~sql
SHOW REPLICA STATUS\G
~~~

Key fields to save as evidence:

| Field | Meaning |
|---|---|
| `Replica_IO_Running` | Status of the event-receiving thread |
| `Replica_SQL_Running` | Status of the SQL thread/applier |
| `Seconds_Behind_Source` | Estimated lag per replication's internal calculation |
| `Source_Host` / `Source_Port` | Configured source endpoint |
| `Source_Log_File` | Binary log file currently read by the I/O thread |
| `Read_Source_Log_Pos` | Position read in the source binlog file |
| `Relay_Source_Log_File` | Source binlog file containing the most recently applied event |
| `Exec_Source_Log_Pos` | Source binlog position corresponding to the most recently applied event |
| `Relay_Log_File` / `Relay_Log_Pos` | Current apply position in the relay log |
| `Retrieved_Gtid_Set` | GTIDs received by the replica |
| `Executed_Gtid_Set` | GTIDs executed on the replica |
| `Last_IO_Error` | Most recent receive thread error |
| `Last_SQL_Error` | Most recent apply thread error |
| `Auto_Position` | Whether GTID auto-positioning is enabled |

Never subtract two log positions directly to deduce seconds of lag. Positions span different files, event sizes vary, and write rates fluctuate over time.

### 2.3. Monitoring Status via Performance Schema

On MySQL 8, inspect the receiver status:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP,
  RECEIVED_TRANSACTION_SET
FROM performance_schema.replication_connection_status;
~~~

Inspect applier and worker status:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  REMAINING_DELAY,
  COUNT_TRANSACTIONS_RETRIES
FROM performance_schema.replication_applier_status;

SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP,
  APPLYING_TRANSACTION,
  LAST_APPLIED_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker
ORDER BY CHANNEL_NAME, WORKER_ID;
~~~

Table and column structures vary across MySQL versions. If using multiple replication channels, always include `CHANNEL_NAME` in results; omitting it can mix up workers across channels.

Inspect the process list to see waiting or active threads:

~~~sql
SHOW FULL PROCESSLIST;
~~~

States such as waiting for the source to send events, waiting for workers to drain queues, or waiting on dependent transactions help narrow down the bottleneck. Capture multiple snapshots over an interval; a single snapshot cannot show whether the backlog is growing or shrinking.

## 3. Determining Whether Lag Is in Receiving or Applying

### 3.1. I/O Thread Not Receiving Data

If `Replica_IO_Running` is not `Yes`, read `Last_IO_Error` and check:

- Does DNS resolve the source hostname properly?
- Can the replica reach the source port from its network namespace?
- Are firewalls, security groups, routes, or proxies blocking the connection?
- Are TLS certificates valid, CA trusted, and hostname matching?
- Does the replication account have the right host pattern, password, and privileges?
- Does the source have binary logging enabled and still retain the file/GTID the replica needs?
- Did the source restart, fail over, or change endpoints?

On the source, check binary logging and existing files:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'server_id',
  'gtid_mode',
  'enforce_gtid_consistency',
  'binlog_expire_logs_seconds'
);

SHOW BINARY LOGS;
~~~

`SHOW BINARY LOG STATUS` inspects current binary log status on supported versions. On older versions, `SHOW MASTER STATUS` may still apply. Never assume an administrative command keeps the exact same name across all major versions.

If the error is authentication or connectivity, fix the endpoint, network, TLS, or account and restart the receiver thread per runbook. Never delete relay logs or reset metadata merely to silence an error message; that destroys evidence and drops received-but-unapplied data.

### 3.2. SQL Thread or Applier Workers Stopped

If the I/O thread runs while `Replica_SQL_Running` stops, inspect `Last_SQL_Error` and `replication_applier_status_by_worker`. Common errors:

| Common Code / Error | Possible Cause | Investigation Path |
|---|---|---|
| 1062 Duplicate entry | Replica already has the unique key the transaction tries to insert | Check data drift, direct writes on replica, filters, or prior transactions |
| 1032 Can't find record | `UPDATE`/`DELETE` cannot find the target row | Compare source/replica rows, check replication filters, and write history |
| 1146 Table doesn't exist | Schema on replica lacks table or DDL was never applied | Compare `SHOW CREATE TABLE` and migration history |
| 1054 Unknown column | Schema mismatch or out-of-sync DDL/app versions | Check DDL ordering, columns, and rollout history |
| 1205 Lock wait timeout | Applier blocked by local transactions or queries on replica | Find blockers, long transactions, and metadata/data locks |
| 1213 Deadlock | Concurrent applier transactions contended for locks | Read deadlock reports, workers, lock order, and dependencies |
| Disk or relay log error | Out of disk, file permissions, or storage fault | Check filesystem, error log, and relay logs |

Before restarting the SQL thread, identify which transaction failed and why. Fix schema or data in a way that brings source and replica into alignment, then verify prerequisites before resuming apply.

Never run ad-hoc data-modifying statements directly on a replica just to make the current transaction pass. Direct writes on a replica create new drift and cause subsequent transactions to fail. If data repair is unavoidable, follow an approved synchronization plan and verify both source and replica.

### 3.3. I/O Receives Fast, but Applier Lags

If the I/O thread runs normally and `Retrieved_Gtid_Set` advances while `Executed_Gtid_Set` lags behind, the backlog sits in relay logs or the applier.

Common causes:

- Source writes more transactions than the replica can apply.
- Huge transactions update hundreds of thousands of rows or indexes.
- A long-running transaction bottlenecks dependent transactions.
- Replica lacks CPU, RAM, IOPS, or storage bandwidth.
- Reporting or batch queries on the replica compete for CPU, I/O, and locks.
- DDL requires metadata locks or blocks workers.
- Parallel applier is not exploiting transaction independence.
- Replica runs on significantly slower storage than the source.

Check relay log length, worker states, CPU, disk latency, I/O queues, buffer pool, lock waits, and active queries. Do not immediately raise worker counts if the bottleneck is sequential transactions, disk I/O, or a query holding locks.

## 4. Analyzing GTIDs and Missing Transactions

GTIDs identify transactions independently of binary log filenames and byte positions. When GTID replication and auto-position are enabled, the replica tells the source which GTIDs it has executed; the source sends missing transactions still retained in its binary logs.

On the replica, record:

~~~sql
SELECT
  @@GLOBAL.gtid_executed AS executed_gtids,
  @@GLOBAL.gtid_purged AS purged_gtids;
~~~

`Retrieved_Gtid_Set` in `SHOW REPLICA STATUS` and `RECEIVED_TRANSACTION_SET` in Performance Schema show transactions received, while `Executed_Gtid_Set` shows transactions applied. A transaction received but not yet applied still sits in relay logs; do not treat it as applied on the replica.

On the source, collect:

~~~sql
SELECT
  @@GLOBAL.gtid_executed AS source_executed_gtids,
  @@GLOBAL.gtid_purged AS source_purged_gtids;
~~~

You can use GTID functions to compare transaction sets. For example, after copying the values from both servers into session variables on an inspection instance:

~~~sql
SET @source_executed = 'SOURCE_GTID_EXECUTED_SET';
SET @replica_executed = 'REPLICA_GTID_EXECUTED_SET';
SET @source_purged = 'SOURCE_GTID_PURGED_SET';

SET @missing = GTID_SUBTRACT(
  @source_executed,
  @replica_executed
);

SELECT
  @missing AS not_executed_on_replica,
  GTID_SUBTRACT(@missing, @source_purged)
    AS missing_and_still_in_source_history,
  GTID_SUBTRACT(@missing, GTID_SUBTRACT(@missing, @source_purged))
    AS missing_and_purged;
~~~

This GTID set comparison is strictly for analysis. Capture values at recorded timestamps and remember the source keeps committing transactions during investigation. Missing GTIDs that have not been purged still reside in binary logs for the replica to fetch; purged GTIDs can no longer be retrieved from the source's active binary logs.

If the topology involves multiple sources, channels, failovers, or transactions injected outside replication, analyze GTID sets per server/channel. Never declare lost transactions solely from comparing snapshots taken at different times.

## 5. When Needed Transactions Were Purged from Binary Logs

### 5.1. Symptoms

A replica stops receiving events with an error stating the source no longer has the requested binary log file or GTID. Error code `1236` commonly appears in `Last_IO_Error` for binary log read failures, including cases where the source already purged GTIDs required by the replica; read the full message to distinguish it from other 1236 causes. With GTID auto-position, the error explicitly notes the source purged one or more required GTIDs. With file/position replication, the error indicates the requested binlog file is no longer in the source's binary log list.

Check:

1. Full `Last_IO_Error` and error code on the replica.
2. `Source_Log_File` and `Read_Source_Log_Pos` if using file/position.
3. `Retrieved_Gtid_Set` and `Executed_Gtid_Set` if using GTID.
4. `SHOW BINARY LOGS` list on the source.
5. `GTID_PURGED` and `GTID_EXECUTED` on the source.
6. Source error log to confirm when files were purged or whether the source changed roles.

Purged-binlog errors differ from transient network blips. Endless retries cannot restore a deleted file. If the source archives binary logs off-server, evaluate restoring files via a dedicated procedure; verify continuity, checksums, and exact sequence before letting replication read them.

### 5.2. Why Can't You Just Increase Retries?

A replica needs every missing transaction in exact order and GTID continuity. Once the source deletes binlogs holding those transactions, it cannot stream events from nonexistent files. Raising connect retries or restarting the I/O thread just repeats the same request and same error.

Never arbitrarily point the binlog position to the newest file or inflate `Executed_Gtid_Set` by faking history. That skips data changes the replica never received. Replication may switch to `Running` while data remains silently diverged and much harder to detect.

### 5.3. Recovery Options

Choose one of these paths based on evidence:

| Option | When Appropriate | Prerequisites |
|---|---|---|
| Restore archived binlogs | Complete archive of missing files/GTIDs exists | Intact files, continuous sequence, and deliverable to replica |
| Rebuild replica from recent backup | Needed binlogs are gone or replica data is untrustworthy | Consistent backup with exact GTID/position taken after the gap |
| Clone from a healthy instance | Healthy donor of compatible topology/version exists and clone is supported | Donor holds valid data and GTID history; assess clone load and impact |
| Restore from backup and reconfigure replication | Replica must be recreated cleanly | Confirmed right source, GTID continuity, schema, and replication config |

Prefer restoring from a consistent backup containing all transactions up to a point where binlogs still exist. Whether using physical or logical backups, capture the GTID/binlog coordinates recorded at the exact snapshot. Table data alone without trustworthy replication coordinates is insufficient for safe reconfiguration.

### 5.4. Rebuilding a Replica from Backup

General workflow:

1. **Prevent the replica from serving stale data:** remove its read endpoint from application pools or mark it unready. If needed, stop replication to preserve evidence and prevent unplanned applies.
2. **Record pre-change state:** save `SHOW REPLICA STATUS`, GTID sets, errors, configs, schema, and relevant logs.
3. **Select a snapshot:** pick a consistent backup from the source or a healthy donor with recorded GTID/binlog coordinates. The snapshot must cover history up to a point whose subsequent transactions the source still retains.
4. **Restore onto the target instance:** restore onto the new/replacement replica. Verify version, unique `server_id`, `server_uuid`, storage engines, schema, and privileges.
5. **Verify history:** compare GTIDs in the backup/restored instance against the source's GTIDs. Ensure all transactions before the starting coordinate are in the snapshot and the source retains all transactions after it.
6. **Configure replication connection:** use GTID auto-position if supported by the topology and GTID history matches; if using file/position, supply the exact coordinates from the backup. Never guess positions from when the backup copy finished.
7. **Start replication:** run `START REPLICA` per verified configuration and watch I/O, applier, worker errors, GTIDs, and lag.
8. **Reconcile data:** run checksums or critical business data checks before returning the replica to the read pool.

Source configuration statements differ by version. On modern MySQL 8, GTID auto-position configuration looks like:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REDACTED_SECRET',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
~~~

This illustrates configuration for a default channel; do not run it before restoring and verifying GTID history. If modifying an existing channel, stop the replica before altering source properties or auto-position mode as required by your version. Manage passwords via secret management rather than hardcoding real values in scripts or packets. On older versions, `CHANGE MASTER TO` and `START SLAVE` may still be used.

If relay logs must be cleared after deciding to rebuild, `RESET REPLICA` clears relay logs and replication state metadata; it does not replace restoring data and verifying GTIDs. `RESET REPLICA ALL` also wipes source connection settings. Use reset commands strictly for their intended purpose after saving evidence; never run `RESET REPLICA ALL` as a generic error-clearing trick.

### 5.5. Never Fake GTIDs to Skip Gaps

`GTID_PURGED` and `GTID_EXECUTED` record transaction history, not status flags to increment arbitrarily just to make replication run. Only set `GTID_PURGED` in qualified provisioning workflows, such as initializing a fresh instance from a backup with verified history. Never edit `GTID_PURGED` on a replica holding unverified data to pretend transactions were applied.

Under GTID mode, skipping a transaction may only be considered when you have proven the transaction is unneeded or properly compensated, following a version/topology-specific runbook. Injecting an empty GTID transaction alters synchronization history permanently; never use it mechanically to bypass duplicate key or row-not-found errors.

## 6. Fixing Apply Errors Without Corrupting Data

### 6.1. Duplicate Key (1062)

A replica reports a duplicate key when an insert/update produces a value violating a unique or primary key. Possible causes:

- Applications or operators wrote directly to the replica.
- The replica previously received that transaction via another branch.
- Data was restored from a backup misaligned with the replication position.
- Replication filters or schema changes caused source and replica states to diverge.
- A transaction was partially applied due to prior configuration or manual intervention.

Collect the colliding key, table, index, transaction GTID, and row values on both source and replica. Determine which row matches business rules and history. After repairing data via a controlled synchronization procedure, confirm remaining transactions apply cleanly and related tables stay consistent.

### 6.2. Row Not Found (1032)

An `UPDATE` or `DELETE` on the replica cannot find the target row. Inspect primary keys, before/after values, replication filters, direct writes on the replica, and prior transactions. With row-based replication, inspect the row image and current row state; with statement-based replication, look for environmental differences that produce different results.

### 6.3. Schema Mismatch

Missing table/column errors usually trace back to DDL deployment ordering, out-of-sync migrations, or replication filters. Compare `SHOW CREATE TABLE` on source and replica, check application schema versions, pending DDLs, and metadata locks. Never manually add a guessed column just to let the SQL thread advance; data types, nullability, defaults, and indexes must match the source schema or an approved compatible design.

### 6.4. Lock Waits and Deadlocks

A replica can be blocked by reporting queries, batches, or local read/write transactions running directly on the replica. Check processlist, `data_locks`, `data_lock_waits`, and `SHOW ENGINE INNODB STATUS`. Stop or throttle the blocking workload per procedure, then verify the applier advances.

Never raise `innodb_lock_wait_timeout` right away to mask the issue. If transactions are blocked by a long query or DDL, raising the timeout only keeps the backlog stalled longer.

## 7. Reducing Lag Sustainably

Once replication runs again, address why the replica fell behind to prevent recurrence.

### 7.1. Large Transactions

A single transaction updating hundreds of thousands or millions of rows takes a long time to apply. Given commit order and transaction dependencies, one huge transaction can stall subsequent transactions even when other workers sit idle.

Measures:

- Break large batches into smaller transactions where business logic permits.
- Avoid holding transactions open long.
- Schedule heavy batches and DDL off-peak.
- Add or tune indexes to reduce scanned and updated rows.
- Track apply duration per GTID and worker.

Never split a business-atomic transaction into multiple commits if doing so violates required atomicity.

### 7.2. Replica Resources

Compare source and replica across CPU, RAM, storage latency, IOPS, throughput, buffer pool, and network. A replica may need equivalent or stronger hardware than the source if it simultaneously serves heavy read traffic and applies writes.

Monitor relay log space, binary log space, temporary files, and free disk. When disk nears full, applier or I/O threads can halt; simply adding disk without finding why logs grew invites repeat incidents.

### 7.3. Parallel Appliers

Parallel replication speeds up apply when transactions are independent and concurrently executable. Effectiveness depends on dependency tracking, workload, worker count, and commit order.

Before increasing workers:

1. Confirm the backlog sits in apply rather than I/O.
2. Inspect which workers are busy, waiting on dependencies, or waiting on locks.
3. Check available CPU, I/O, and memory headroom.
4. Measure apply throughput before and after changes.
5. Verify commit ordering and consistency requirements for applications.

Adding workers barely helps if all transactions touch the same hot row or depend sequentially. It can even raise contention and slow the replica down.

### 7.4. Read Queries on Replicas

Long analytical queries consume CPU and I/O or hold snapshots/locks that interfere with the applier. Offload reporting workloads to dedicated replicas, bound heavy queries, and avoid routing read-after-write flows to lagging replicas.

Applications must be aware of read-endpoint lag. For read-after-write flows, read from the primary/source, wait for the committed GTID to execute on the replica, or use designed session affinity. Never assume every replica immediately reflects a freshly committed transaction.

## 8. Preventing Binary Log Loss in the Future

### 8.1. Size Retention Around Recovery Time

Binary log retention must exceed the longest expected replica disconnect plus detection, investigation, and recovery time. Include a safety margin for write traffic spikes, long backups/restores, and maintenance windows.

A planning formula:

~~~text
binlog retention
  >= maximum expected outage duration
   + detection and response time
   + replica rebuild time if needed
   + operational safety margin
~~~

Estimate binlog volume using peak write rates, not just daily averages. Monitor disk capacity so longer retention never fills the filesystem.

Check configuration:

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
~~~

`binlog_expire_logs_seconds` sets automatic expiration in seconds on supported versions. Older versions may use `expire_logs_days`. Verify exact variable names and defaults for your version.

### 8.2. Archive Binary Logs Off-Source

For strict recovery requirements, consider archiving binary logs to dedicated external storage. Archives must preserve sequence, checksums, timestamps, source server UUID, and retention policies. Test restoring archived logs periodically; an untested copy does not guarantee recoverability during an incident.

### 8.3. Monitor Replicas and Retention

Configure alerts for:

- Stopped I/O thread or applier.
- Lag exceeding SLO for a sustained interval.
- Retrieved GTID advancing while Executed GTID stalls.
- Rapid relay log growth or low disk space.
- Unusual GTID gap between source and replica.
- Binary logs nearing expiration while a replica still lags behind.
- Repeated applier worker errors or climbing retries.

Monitor per channel if using multi-source replication. Alerts must include endpoint, channel, server UUID, and timestamp so on-call engineers immediately identify the affected stream.

## 9. Investigation and Recovery Runbook

### Phase A: Preserve Evidence

1. Record incident time, source/replica endpoints, and channel.
2. Collect `SHOW REPLICA STATUS`, error logs, and relevant Performance Schema tables.
3. Save `GTID_EXECUTED`, `GTID_PURGED`, `Retrieved_Gtid_Set`, and the binary log list.
4. Record MySQL version, `server_id`, `server_uuid`, GTID config, and replication filters.
5. Check whether any application wrote directly to the replica.

### Phase B: Classify

1. Is the I/O thread running?
2. Are the SQL thread and all workers running?
3. Are received GTIDs advancing while executed GTIDs stall?
4. Are relay logs growing?
5. Which error codes appear in `Last_IO_Error` or `Last_SQL_Error`?
6. Does the source still retain needed files/GTIDs?
7. Is lag a real backlog, an intentional delay, or an unreliable metric?

### Phase C: Choose Remediation

- **Transient connection failure:** fix network/TLS/account and restart I/O thread.
- **Explainable apply error:** fix schema/data/locks per plan, verify consistency, and resume applier.
- **Slow apply:** reduce competing read load, break up long transactions, scale capacity, or tune parallel applier based on metrics.
- **Binlogs still intact:** restore connectivity and let the replica catch up on missing GTIDs/file-positions.
- **Binlogs purged:** restore from a complete binlog archive or rebuild the replica from a consistent backup/clone with matching GTID coordinates.

### Phase D: Verify After Recovery

1. Both `Replica_IO_Running` and `Replica_SQL_Running` are active.
2. No new `Last_IO_Error` or `Last_SQL_Error`.
3. Retrieved and Executed GTIDs advance as expected.
4. Lag drops and stays within SLO over an observation window.
5. Reconcile business data or checksums across targeted scope.
6. Return replica to read pool only after passing readiness checks.
7. Update retention, alerts, and runbooks to prevent recurrence.

## 10. Actions to Avoid

- Never advance source log file/position to the latest file to skip unreceived transactions.
- Never fake `GTID_EXECUTED` or `GTID_PURGED` on an instance with unverified data.
- Never use skip counters or empty transactions to bypass errors without proving the transaction can safely be skipped.
- Never delete relay logs before saving status and identifying received-but-unapplied transactions.
- Never run `RESET REPLICA ALL` merely to restart threads; it erases source connection configuration.
- Never write directly to an active replica unless architecture and procedures explicitly allow it.
- Never raise workers, timeouts, or `max_connections` based on a single metric without finding the bottleneck.
- Never return a replica to the read pool solely because both threads say running; verify GTIDs, lag, and data.

## 11. Practice Scenario

A MySQL replica loses network connectivity for two days. Meanwhile, the source continues accepting writes and automatically purges binary logs per current retention. When connectivity returns, the replica fails saying the source no longer has the required file or GTIDs. Applications are still routing reporting queries to this replica.

Handle in order:

1. Remove the replica from the read pool so reports do not silently read stale data.
2. Save `SHOW REPLICA STATUS`, error logs, source and replica GTID sets, and remaining binlog lists.
3. Identify missing transactions and confirm whether they were purged from the source.
4. If a complete binlog archive exists, verify file/GTID continuity and evaluate replaying/providing them to replication.
5. If no binlog archive exists, take a consistent backup/clone from a healthy source with its snapshot GTIDs and rebuild the replica.
6. Configure auto-position or file/position matching the backup coordinates; start replication and monitor workers.
7. Reconcile key business tables, wait until lag meets SLO, and only then return the replica to the read pool.
8. Increase retention based on real outage and restore times; add early alerts for replica disconnects.

You cannot simply restart the replica or jump to the latest binlog, because doing so drops two days of transactions. You must rebuild data from a consistent snapshot and resume syncing remaining retained transactions.

## 12. Self-Check Questions

1. What distinct responsibilities do the I/O thread and SQL/applier thread handle?
2. Why is `Seconds_Behind_Source` insufficient to prove a replica is caught up?
3. How does `Retrieved_Gtid_Set` differ from `Executed_Gtid_Set`?
4. Which fields in `SHOW REPLICA STATUS` distinguish receive lag from apply lag?
5. What types of drift do duplicate key 1062 and row-not-found 1032 typically indicate?
6. Why does increasing parallel workers not always speed up a replica?
7. What happens when a replica needs a GTID already purged from the source's binary logs?
8. When rebuilding a replica from backup, why must the backup snapshot and GTID/binlog coordinates be consistent?
9. Why should you never arbitrarily bump `GTID_PURGED` or point to the latest binlog position?
10. What must be verified before returning a replica to the read pool?

Investigating replica lag requires separating the receive path, relay log queue, and apply path. If needed transactions remain in binary logs, fix connectivity or apply bottlenecks so the replica catches up. If transactions were purged and no complete archive exists, rebuild the replica from a consistent snapshot with valid GTID coordinates. Preserving transaction history and verifying data integrity matter far more than forcing replication status to show `Running`.
