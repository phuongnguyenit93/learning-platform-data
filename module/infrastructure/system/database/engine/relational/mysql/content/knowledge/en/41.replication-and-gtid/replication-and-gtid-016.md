# Data reconciliation, resync, and conditions for rebuilding a replica

A replica can still be connected to the source yet hold data that no longer matches. Causes can include replication lag, a stopped applier, skipped transactions, accidental direct writes to the replica, inconsistent schema changes, or the replica missing required binary logs to catch up with the source. Each scenario calls for a different remediation.

Data reconciliation is the process of determining which dataset is canonical, measuring the divergence, and deciding how to bring the replica back into the right state. Resync means resynchronizing the data or replication stream. Rebuild means recreating the replica from a consistent copy of the source or a verified backup. This lesson places those operations within MySQL operations, combining knowledge of transactions, locks, backups, GTIDs, and access control.

## 1. Distinguishing lag, replication errors, and data drift

Not every lagging replica has permanently corrupted data. Before intervening, distinguish three situations:

| Situation | Symptoms | Meaning |
|---|---|---|
| Replication lag | Receiver and applier are active, but the replica has not yet applied all new transactions | Data may simply be behind; let the replication stream catch up |
| Replication stopped or broken | Receiver or applier stopped, I/O or SQL error present, relay log not advancing | Replica can no longer receive or apply events |
| Data drift | Replication stream may be running, yet certain rows, tables, or schemas differ from the source | Out-of-band writes, skipped transactions, or un-replicated changes may have occurred |

For example, the source has recorded 10,000 new orders while the replica has applied 9,800 orders. If the remaining 200 orders are still in the binlogs and the applier is active, this may simply be lag. Conversely, if both receiver and applier report running yet one order shows different monetary totals across the two servers, investigate data drift.

Common causes include:

- An application or operator wrote directly to the replica.
- An administrative account altered data on the replica as a temporary workaround without documenting it.
- A replication transaction was skipped or handled in a way that dropped events.
- Replication filters prevented a schema or table from replicating as expected.
- Schema differences between source and replica prevented events from applying properly.
- The replica was disconnected longer than the source's binlog retention window.
- Restored the wrong backup, wrong point in time, or wrong GTID baseline.
- Multiple write sources or an incomplete role transition created transactions existing on only one branch.

Do not conclude data is consistent merely because both replication threads are running or the lag metric equals 0. Thread status shows replication is progressing; it does not prove every row and schema matches the source.

## 2. Identifying the canonical data source and preserving current state

Before resyncing, determine which server is the authoritative data source. In a single-source topology, the source legitimately accepting writes is usually the reference point. After a failover, the newly promoted source designated by the runbook becomes the canonical write point. If split-brain or multi-writer activity occurred, never choose a server based solely on hostname; identify valid transactions, role-switch timestamps, and data confirmed to the application.

Execute preflight checks in order:

1. Identify the current source, involved replicas, each server's role, and endpoints used by the application.
2. Check whether any server outside the source is accepting direct writes. If detected, restrict new writes per incident procedure and preserve logs.
3. Collect replication status, GTIDs, binary logs, relay logs, recent errors, and server logs.
4. Record replication filter configs, schemas, MySQL versions, table engines, and recent changes.
5. Take a recoverable backup or snapshot before modifying data. Keep a copy of the current state so divergent transactions can be analyzed.
6. Define a maintenance window or a consistent snapshot method so comparisons are not skewed by ongoing writes.

If the source continues accepting writes while comparing table by table, results across the two servers may represent two different points in time. For InnoDB tables, use consistent snapshots or checksum tools with appropriate snapshot handling. If full-dataset comparison at one exact point is required, coordinate snapshots, write locks, or a consistent backup workflow matched to your tooling and system load.

Never delete relay logs, reset GTID state, skip failing transactions, or run bidirectional sync commands before capturing the current state. Those actions can destroy evidence needed to find the root cause.

## 3. Reconciling replication status

On the replica, inspect status using version-appropriate syntax:

~~~sql
SHOW REPLICA STATUS\G
~~~

Some older MySQL versions use:

~~~sql
SHOW SLAVE STATUS\G
~~~

Fields to review include:

| Field | Question to answer |
|---|---|
| Replica_IO_Running | Is the receiver currently fetching events from the source? |
| Replica_SQL_Running | Is the applier currently executing the relay log? |
| Seconds_Behind_Source | Roughly how far behind is the replica per the estimated metric? |
| Last_IO_Error | Why could the receiver most recently not continue? |
| Last_SQL_Error | Why could the applier most recently not apply an event? |
| Source_Log_File and Read_Source_Log_Pos | How far into the binlog has the receiver read? |
| Relay_Source_Log_File and Exec_Source_Log_Pos | Which source position has the applier applied up to? |
| Retrieved_Gtid_Set | Which GTIDs have been received? |
| Executed_Gtid_Set | Which GTIDs have been executed on the server? |

Exact field names may vary by version and command output. Read the full output, not just a single lag field. If both receiver and applier are running while `Last_SQL_Error` still displays an old error, verify whether that error has already been resolved.

On both source and replica, collect executed GTID sets:

~~~sql
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

Assuming you have copied the source and replica GTID sets into two variables in your inspection session, you can compare them using GTID functions:

~~~sql
SET @source_gtids = '3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1200';
SET @replica_gtids = '3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1180';

SELECT GTID_SUBTRACT(@source_gtids, @replica_gtids)
  AS transactions_missing_on_replica;

SELECT GTID_SUBTRACT(@replica_gtids, @source_gtids)
  AS transactions_extra_on_replica;
~~~

The GTID strings above only illustrate how to read the output; substitute your system's actual GTID sets. If `source - replica` returns a non-empty set, the replica has not executed some transactions present on the source. If `replica - source` returns a non-empty set, the replica holds transactions absent from the compared source's set. These may be out-of-band transactions or artifacts of an earlier topology; investigate their origin before discarding them.

A GTID set reflects transaction identity, not a table content checksum. Two servers can share identical GTID sets yet have data altered out-of-band; conversely, servers in complex topologies can hold different GTID sets because they received transactions from multiple sources. Interpret results in light of the actual topology structure and failover history.

When you need to wait for a replica to execute up to a known GTID set, MySQL provides:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('3E11FA47-71CA-11E1-9E33-C80AA9429562:1-1200', 30);
~~~

This function waits up to the specified number of seconds for the GTID set to execute on the current server. A result of `0` means the wait succeeded; `1` means the timeout expired. Applications must handle timeouts—such as reading from the source or returning an appropriate error—rather than assuming the replica caught up.

## 4. Reconciling data at the schema, table, and row levels

Reconciliation should start broad and narrow down:

**Schema:** compare table names, columns, data types, collations, indexes, constraints, triggers, views, routines, and partitions. A replica whose schema differs from the source may fail when applying events or return different query results even when some rows match.

**Table:** compare row counts, primary key min/max, aggregates by business partition, and chunked checksums. Equal row counts do not prove equal contents; two tables can have the exact same row count with different values.

**Row:** use primary keys or unique keys to identify missing, extra, or mismatched records. On tables lacking a stable key, pairing rows and synchronizing becomes complex, resource-intensive, and error-prone.

Aggregate queries can help with initial scoping:

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM app_db.orders;
~~~

Run the same query on source and replica against an equivalent snapshot. This is only a preliminary sanity check; never treat these three values as proof of complete data equivalence.

For large tables, chunked checksums are usually far more efficient than pulling entire tables to a client. Percona Toolkit provides tools such as `pt-table-checksum` to compare checksums by range and record discrepancies via replication. The tool must be configured for your MySQL version, topology, replication filters, and system load. Review the execution plan, run during low-traffic windows, and monitor impact before applying across all tables.

When a checksum reports drift, pinpoint the exact chunk, keys, and differing columns. Do not run blind synchronization across all tables. On large tables, reading and computing checksums also generates I/O and CPU load and can prolong transactions or snapshots.

## 5. Choosing remediation: catch up, targeted repair, or rebuild

The decision depends on the cause, scope of divergence, and ability to retrieve transactions:

| Discovered condition | Appropriate remediation |
|---|---|
| Lag only, receiver/applier active, and required binlogs still exist | Let replication continue; monitor until GTIDs and data catch up |
| Receiver or applier stopped due to fixable config/connection error | Fix root cause, then start threads per runbook |
| Few rows drifted, canonical source clear, schemas compatible, narrow scope | Perform targeted data repair from source to replica, then re-checksum |
| Many tables drifted, unclear transaction origin, or extensive out-of-band writes | Stop and investigate; usually requires rebuilding the replica from a consistent copy |
| Replica missing required binlogs because source purged them | Cannot simply restart to recover events; re-provision or restore from an appropriate backup |
| Errant transactions or post-failover split-brain | Identify canonical data branch and plan rebuild; do not delete GTIDs to hide divergence |

### 5.1. Simply letting replication catch up

If data has not drifted and the source still retains required binlogs, fixing the connectivity or configuration error and resuming replication is the least disruptive option. After fixing the root cause, check status and start receiver/applier if stopped:

~~~sql
START REPLICA;
SHOW REPLICA STATUS\G
~~~

Never run `START REPLICA` repeatedly without understanding the error. Wrong passwords, missing replication privileges, purged source binlogs, or data errors will not vanish on their own across restarts.

### 5.2. Targeted drift repair

If only a small set of rows drifted and the source is confirmed canonical, those rows can be synchronized from source to replica. Before repairing:

1. Back up the replica's data and record the primary keys of the drifted rows.
2. Prevent applications or operators from writing directly to the replica during repair.
3. Account for all columns, foreign key relationships, triggers, and related tables.
4. Select a tool capable of strictly bounding tables, keys, and sync direction.
5. Execute within a controlled window, monitoring modified row counts and errors.
6. Re-run checksums and verify business invariants after repair.

`pt-table-sync` is a Percona Toolkit utility that can assist with syncing rows between MySQL servers. Explicitly designate the source as canonical and the replica as target, and use check/dry-run modes before writing. Never run bidirectional sync or arbitrarily reverse source/replica direction; syncing the wrong direction can overwrite valid data with stale data.

If tables have triggers, foreign keys, auto-increment columns, sensitive data, or active application writes, assess side effects before syncing. For some systems, a safer approach is repairing via controlled SQL transactions after verifying each row and preparing a rollback plan.

### 5.3. When must you rebuild the replica?

Rebuilding is usually the right choice when:

- Drift spans many tables or the full scope of diverged data cannot be determined.
- The replica holds errant transactions that cannot be safely reconciled.
- The source has deleted binlogs the replica needs to continue.
- Schemas or data were altered from unknown origins.
- The replica received out-of-band writes without a reliable audit log for row-by-row repair.
- The time and risk of repairing individual discrepancies exceed provisioning a fresh replica from a consistent copy.

Rebuilding means re-provisioning data from the source or a verified backup, resetting replication/GTID coordinates, and having the replica follow the canonical source stream. Because this overwrites replica data, back up or preserve the existing state first if further investigation is required.

## 6. Methods for re-provisioning a replica

### 6.1. Logical backup and restore

For small databases or when selective migration is needed, you can take a logical dump and restore it onto the replica. The standard tool is `mysqldump`. Choose consistent snapshot options suited to your engine and record the binlog coordinates or GTIDs at dump time.

Advantages include readability, database/table selectivity, and low dependence on physical file formats. Disadvantages include slow restores, heavy CPU and I/O consumption, and careful attention needed for charsets, collations, routines, triggers, events, privileges, and object creation order.

Never take a dump at one time and pair it with arbitrary replication coordinates. The data snapshot and binlog/GTID coordinates must represent the exact same consistent point; otherwise the replica may miss or double-apply transactions.

### 6.2. Physical backup

For large datasets, physical backups typically reduce provisioning time because they store data in a format close to MySQL's on-disk layout. You can use MySQL Enterprise Backup, Percona XtraBackup, or a physical backup mechanism compatible with your version and architecture.

Backups must be prepared/restored per the tool's instructions. Record metadata such as the GTID set, binary log file/position, or equivalent coordinates supplied by the tool. After restoring, verify file ownership, instance configuration, a unique `server_id`, and disk capacity before starting replication.

### 6.3. MySQL Clone Plugin

MySQL Clone Plugin can physically copy data from a donor to a recipient on supported versions. This is a convenient option for provisioning a replica when both instances meet plugin compatibility and configuration requirements. Cloning replaces data on the recipient, so confirm the exact donor and recipient before executing.

Before using Clone Plugin, check MySQL versions, installed plugins and required privileges, network connectivity, TLS settings, disk space, and compatibility prerequisites. Cloning is a data transfer method; you must still configure or verify the replication channel afterward and inspect GTID/execution state.

### 6.4. Choosing a method by scale

| Method | Best suited when | Key controls |
|---|---|---|
| Logical dump/restore | Small datasets, selective schemas, or portability needed | Restore duration, consistent snapshot, database objects, and replication coordinates |
| Physical backup | Large datasets needing faster recovery than logical restore | Version/tool compatibility, backup metadata, file permissions, and GTIDs |
| Clone Plugin | Compatible instances needing direct provisioning from a donor | Recipient data is overwritten; plugin, privileges, network, and post-clone state |

No single method is optimal for every system. Choose based on data volume, RTO, source load, storage capabilities, MySQL version, and operational readiness.

## 7. Re-establishing replication with GTID auto-position

Once data is provisioned from a consistent snapshot, configure the replica to connect to the right source. In modern MySQL, the syntax uses `CHANGE REPLICATION SOURCE TO`; older versions use `CHANGE MASTER TO`.

Example configuring the connection and enabling GTID auto-positioning:

~~~sql
STOP REPLICA;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
SHOW REPLICA STATUS\G
~~~

The example above illustrates connection attributes while omitting the `SOURCE_PASSWORD` parameter; in deployment, supply the password via your organization's approved secret management channel rather than recording real passwords in documentation, shell history, or logs. Configure TLS and certificate verification when connecting over a network.

GTID auto-position enables the replica to advertise its executed GTID set so the source sends missing transactions. This mechanism requires GTIDs to be enabled and properly configured on the participating servers. It does not automatically fix already-drifted data and cannot retrieve transactions if the source has purged required binary logs.

If the replica holds out-of-band GTIDs, never delete or fabricate GTID sets to force both servers to look identical. Identify where those transactions originated, whether the application confirmed them, and whether data reconciliation is needed. When correctness cannot be proven, re-provisioning the replica from the canonical source is usually safer.

Several commonly misunderstood reset commands:

- `RESET REPLICA` deletes relay logs and resets certain replication state; it does not delete rows in InnoDB tables.
- `RESET REPLICA ALL` also deletes saved source connection metadata.
- Reset commands do not replace data restoration and do not resolve data drift.
- Never use GTID or binlog reset commands to hide divergent transactions. Before any reset operation, save current state and follow a version-specific runbook.

## 8. Auditable resync/rebuild workflow

A controlled workflow can be divided into phases:

1. **Detection:** lag alerts, stopped receiver/applier, checksum mismatch, or business queries revealing divergent data.
2. **Isolate changes:** identify the canonical source and block out-of-band writes to the replica. If split-brain is suspected, fence the unselected server.
3. **Collect evidence:** save `SHOW REPLICA STATUS`, GTID sets, errors, binlog/relay log metadata, schemas, and filter configs.
4. **Back up current state:** create a recoverable copy of the replica and preserve data for investigation.
5. **Assess scope:** compare schemas, tables, chunks, and rows; identify missing transactions, errant transactions, or drifted data.
6. **Choose remediation:** catch up, targeted repair, or rebuild from a canonical donor/backup.
7. **Execute:** run in the defined data direction, restrict privileges, monitor resources, and log changes.
8. **Restore replication:** configure source, account, TLS, GTID auto-position, or matching coordinates, then start the replica.
9. **Verify:** receiver/applier running, no new errors, GTIDs advancing, and checksums matching across the remediated scope.
10. **Reopen traffic:** return the replica to the read pool or standby role only after all checks and business tests pass.

During remediation, keep `read_only` and `super_read_only` enabled on the replica as appropriate to prevent unintended writes. Open write access only when promoting a replica to source during failover. Replication accounts should hold only privileges needed for replication; resync operational accounts should be provisioned separately and audited.

## 9. Verification after synchronization

Do not close the task merely because `START REPLICA` succeeded. Verify across multiple layers:

**Replication stream:** confirm receiver and applier are active, I/O/SQL errors do not recur, relay logs drain, and lag drops to target levels.

**GTID:** confirm the replica has executed the required GTIDs from the source. In simple topologies with out-of-band writes eliminated, the executed GTID set should faithfully reflect the source's transaction history. In multi-source topologies or after failovers, cross-check per channel and context.

**Data:** re-run checksums on repaired tables/chunks or the full planned scope. Check primary keys, foreign key relationships, business totals, and schemas.

**Application:** run representative read queries, verify read-after-write routing, and confirm no write queries are accidentally routed to the replica.

**Operations:** verify new backups, binlog retention, lag alerts, access permissions, and runbook documentation are updated.

A replica should re-enter the read pool only once required data has caught up and the application tolerates any remaining lag. A replica designated as standby must be healthy enough to meet agreed RPO/RTO targets.

## 10. Hands-on scenario

A system has source `db-primary` and replica `db-read-01`. After a maintenance window, dashboards show both receiver and applier running, yet checksums on the `orders` table differ. Further inspection reveals several rows on the replica had their order status edited directly by an operational account. GTID sets show no transactions missing from the source, yet they do not prove those direct edits are valid.

Draft a remediation plan:

1. Confirm `db-primary` is the canonical source and verify applications are not writing elsewhere.
2. Block direct writes to `db-read-01`, save logs, and back up current state.
3. Compare schemas, identify the list of divergent primary keys, and determine the scope of affected rows.
4. Confirm that direct edits on the replica do not represent valid business state.
5. If scope is small, repair the exact rows from source to replica using controlled tooling or transactions; if scope is incomplete or untrustworthy, rebuild the replica from a canonical snapshot.
6. Start or verify replication with GTID auto-position; monitor receiver, applier, and lag.
7. Re-run checksums, verify order-status queries, and test application read routing before returning the replica to service.

The key insight is that GTID sets can show which replication transactions executed, but they do not automatically catch every direct SQL modification on a replica when binary logging or the replication stream does not reflect it as expected. GTID reconciliation must always be paired with real data verification.

## 11. Self-check questions

1. How does replication lag differ from data drift? Why is running receiver/applier status insufficient to prove identical data?
2. When `GTID_SUBTRACT(source_gtids, replica_gtids)` returns a non-empty set, what does that indicate?
3. Why do GTID sets not replace data checksums?
4. When can you simply restart replication, when should you perform targeted row repair, and when must you rebuild?
5. Why must you identify the canonical source and back up current state before resyncing?
6. How do logical backup, physical backup, and Clone Plugin differ when provisioning a replica?
7. Does `RESET REPLICA ALL` delete table data? Which information does it affect?
8. After a rebuild, which conditions must be verified before returning a replica to the read pool?

Reconciling and rebuilding a replica is a procedure for preserving data correctness. You must establish the canonical data source, snapshot timestamp, scope of received and applied transactions, direction of data repair, and post-sync verification results. Only when that evidence is complete is a replica trustworthy enough to resume serving reads or acting as standby.
