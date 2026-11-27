# Binary Log and PITR

## Restricting Binary Log/GTID Reset Operations and Version-Specific Syntax Changes

The binary log is part of MySQL's recovery chain. It records data and structural changes according to configuration, supports replication, and enables replaying transactions after a backup to recover to a specific point in time (point-in-time recovery, PITR). Consequently, deleting logs or resetting GTID history can directly impact recoverability and replication continuity.

In the `DATABASE_MYSQL` module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. When operating binary logs, you must understand data state, transaction history, and replication topology: an administrative command succeeding does not mean the system still retains enough data to recover.

This lesson focuses on the boundaries between rotating logs, purging logs, resetting all binary logs/GTIDs, and resetting replica metadata, while explaining command name changes across MySQL 5.7, 8.0, and 8.4. Reset commands covered here can destroy unrecoverable history. Practice destructive commands only on disposable lab instances.

### 1. What Do the Binary Log and GTID Store?

The binary log (binlog) records change events on the server per configuration. Depending on `binlog_format`, events may represent SQL statements (`STATEMENT`), row changes (`ROW`), or a combination (`MIXED`). The binary log is not a log of every `SELECT` query; it serves change replication and data recovery.

Several terms must be distinguished:

- **Binary log file:** sequentially named log file, for example `binlog.000123`.
- **Binary log index:** index file listing the binary logs managed by the server.
- **File/position:** event coordinates within a binary log, commonly recorded with backups to mark where replay starts.
- **GTID:** Global Transaction Identifier, typically formatted as `server_uuid:transaction_number`.
- **`gtid_executed`:** set of GTIDs executed by the server, including transactions still in the binlog and transactions already purged from the binlog.
- **`gtid_purged`:** set of GTIDs executed that are no longer present in the binary logs currently on the server.

GTID helps MySQL identify executed transactions without relying solely on filenames and positions. It does not store transaction contents for replay. If the binary log containing a transaction has been deleted and no other archive exists, GTID only shows that the transaction once existed; it cannot recover lost contents.

Check current status:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW BINARY LOGS;

SELECT
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged;
```

The command to inspect current file/position status changes names across versions; the table in Section 4 shows how to select syntax. On a source server with binlog enabled, record the filename and position together with the GTID set when creating backups. If `log_bin` is disabled, you cannot rely on that server's binlog to perform PITR for the unlogged period.

### 2. Distinguishing Rotate, Purge, and Reset

These three operations have very different effects. Never use vague wording like "reset log" in runbooks; write the exact command and expected outcome.

| Operation | Purpose | Primary effect | Impact on PITR/replication |
|---|---|---|---|
| `FLUSH BINARY LOGS` | Rotate to a new binlog file | Closes current file and creates the next file; preserves older files | Generally does not break the log chain; older files remain readable |
| `PURGE BINARY LOGS` | Selectively delete older files | Deletes files prior to a specified filename or timestamp; updates purged GTID state | Can break PITR or leave replicas missing logs if still-needed files are deleted |
| `RESET MASTER` (pre-8.4 releases) | Reinitialize entire binlog history | Deletes all managed binary logs and resets GTID state per version semantics | Breaks existing PITR chain; can disrupt replication and GTID continuity |
| `RESET BINARY LOGS AND GTIDS` (MySQL 8.4) | New command name for full reset | Deletes binary logs and resets GTID history | Destructive impact equivalent to reset; requires re-planning backups/replication |
| `RESET REPLICA` | Reset state on a replica server | Deletes relay logs and resets replication metadata per command scope | Does not delete binlogs on source; may require reconfiguring or resyncing the replica |

#### 2.1. Rotate: starting a new file while preserving history

```sql
FLUSH BINARY LOGS;
SHOW BINARY LOGS;
```

Rotating is useful for creating file boundaries, assisting archiving, or preparing a new log coordinate. This command does not delete previous files and does not clear GTID history. If the goal is merely starting a new binlog file, use rotate instead of reset.

#### 2.2. Purge: deleting a subset of logs after verification

You can purge files preceding a specified file:

```sql
SHOW BINARY LOGS;
PURGE BINARY LOGS TO 'binlog.000123';
```

The command above deletes files preceding `binlog.000123`; the target file and subsequent files are kept. You can purge by timestamp:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

The cutoff must be chosen based on retention policy and backup/replica state. Before purging, verify:

1. Every replica needing the files slated for deletion has received and applied the corresponding transactions.
2. No stopped replica will need to resume from those files.
3. The archive holds complete, readable binlog copies retained for the required period if needed for PITR.
4. Full backups and the PITR window to protect do not depend on the files slated for deletion.
5. Filenames, timestamps, and GTID sets are recorded in the operational log.

Purging does not reset all of `gtid_executed`. Transactions removed from binlogs are reflected in `gtid_purged`. However, a replica needing purged transactions can no longer fetch them from the source. GTID auto-positioning cannot regenerate lost binlog contents.

MySQL can auto-expire binlogs via settings such as `binlog_expire_logs_seconds`. Treat automatic expiration as a retention policy that must coordinate with backup schedules, archiving, and replica lag. Never set an expiration shorter than the recovery window committed by the organization.

#### 2.3. Full reset: a destructive operation

On versions before MySQL 8.4, the common full-reset command is:

```sql
RESET MASTER;
```

On MySQL 8.4, use the new command name:

```sql
RESET BINARY LOGS AND GTIDS;
```

This is a broad-impact administrative command. It deletes server-managed binary logs, reinitializes the file/position sequence, and resets GTID history per version semantics. When GTID is in use, the reset operation clears the instance's `gtid_executed` and `gtid_purged` state according to the behavior defined for the command in that version. It does not delete table rows and does not replace database restoration. However, afterward, prior transactions can no longer be recovered from the deleted binlogs.

Never run reset merely to "free space", "keep file numbers small", or "fix GTID errors". To reclaim space, design controlled retention and purging. For GTID errors, investigate GTID sets, data state, and topology before deciding to re-seed or rebuild a replica.

Before running a reset in an approved environment, all of the following conditions must be met:

- Clearly identified the instance and its role: standalone source, replica, multi-source topology member, or lab environment.
- Stopped or isolated replication streams per the appropriate runbook and understood every channel's state.
- Saved a consistent backup, required binary logs, and file/position or GTID metadata in a location independent of the server being reset.
- Confirmed replicas and downstream systems no longer need the binlogs about to be lost; prepared a re-seed plan if needed.
- Assessed impact on PITR, CDC, audit pipelines, and backup tools that rely on binlogs.
- Established a plan to reinitialize the backup/binlog chain and verify GTIDs afterward.

Reset commands typically require appropriate binary log administrative privileges; dynamic privilege names and compatible grants may differ across versions. Grant only least privilege—never grant `SUPER` broadly merely for command convenience.

### 3. GTIDs and Unavoidable Limitations

GTIDs solve transaction identification, not binary log replacement. To understand the impact of a reset, distinguish three things: which transactions the server executed, which transactions still have contents in the binlog, and which transactions a replica applied.

#### 3.1. `gtid_executed` and `gtid_purged`

Illustrative example:

- The server executed GTIDs from `uuid-a:1-500`.
- Available binary logs currently retain contents only for `uuid-a:301-500`.
- In that state, `gtid_executed` can include `uuid-a:1-500`, while `gtid_purged` represents what was executed yet is no longer in the binlogs, such as `uuid-a:1-300`.

This illustrates the meaning of the two sets, not syntax for assigning GTIDs. Real values can be unions of multiple UUIDs and transaction ranges.

If a replica reports missing `uuid-a:1-300`, yet the source already purged the binlogs containing them and no archive exists, the source cannot send those transactions. `SOURCE_AUTO_POSITION=1` only lets both sides exchange GTID sets to select transactions still available to transfer; it never recovers deleted transactions.

#### 3.2. Never reset GTIDs to mask a gap

Never edit `gtid_purged` or reset GTID history to make two servers "look in sync" when their data does not match. Doing so can cause MySQL to skip truly missing transactions or process a transaction against a state that does not reflect the data.

`SET GLOBAL gtid_purged` enforces intersection rules across the new GTID set, `gtid_executed`, binlog state, and version. When building a replica from a backup, a dump may include a statement setting GTIDs already present in the backup. That statement should only be applied per the backup tool's instructions and on a target server in the appropriate state, usually a freshly prepared instance for the restore. Never copy a `SET GTID_PURGED` statement from old notes and run it on a live serving host.

When a replica has GTID drift, the investigation workflow should be:

1. Collect `gtid_executed`, `gtid_purged`, replication status, and applier errors on both source and replica.
2. Identify missing GTIDs—whether present on source, stored in archives, or permanently lost.
3. Reconcile actual data and the backup point used to provision the replica.
4. If logs are gone, retrieve transactions from a verified archive or rebuild the replica from a fresh compatible backup.
5. Adjust GTID metadata only per the version's runbook once data and transaction sets are verified.

#### 3.3. Resetting binlogs vs. resetting a replica

`RESET REPLICA` operates on replica state: relay logs and replication channel metadata. `RESET REPLICA ALL` also removes stored source connection info for the channel. On older versions, the corresponding command used `SLAVE`.

Resetting a replica does not delete binary logs on the source and is not a way to reset global `gtid_executed`. Conversely, resetting binary logs/GTIDs on the source does not automatically reconfigure relay logs or connection metadata on replicas. Before running any reset command, explicitly document which host and which state layer you are modifying.

### 4. Syntax Changes Across MySQL Versions

MySQL renamed several commands from `MASTER`/`SLAVE` terminology to `SOURCE`/`REPLICA`, and MySQL 8.4 renamed the binary log reset command. The table below helps choose appropriate syntax; verify documentation for your exact running version, especially when using distributions with vendor modifications.

| Purpose | MySQL 5.7 and earlier 8.0 | Newer MySQL 8.0 | MySQL 8.4 |
|---|---|---|---|
| View current binary log status | `SHOW MASTER STATUS` | `SHOW MASTER STATUS` still works; new terminology introduced in corresponding 8.0 series | `SHOW BINARY LOG STATUS`; old name deprecated |
| Reset all binlogs and GTIDs | `RESET MASTER` | `RESET MASTER` | `RESET BINARY LOGS AND GTIDS`; `RESET MASTER` deprecated |
| View replica status | `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` introduced in 8.0.22; old name may persist in transition releases | `SHOW REPLICA STATUS` |
| Start/stop replication | `START SLAVE`, `STOP SLAVE` | `START REPLICA`, `STOP REPLICA` from 8.0.22 | `START REPLICA`, `STOP REPLICA` |
| Reset replica relay logs/metadata | `RESET SLAVE` | `RESET REPLICA` from 8.0.22 | `RESET REPLICA` |
| Configure replication source | `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` introduced in 8.0.23 | `CHANGE REPLICATION SOURCE TO` |
| mysqldump option recording source coordinates | `--master-data` | `--source-data` introduced in 8.0.26; `--master-data` deprecated | `--source-data`; old name deprecated |

Key transition milestones:

- MySQL 8.0.22 introduced `REPLICA`-based replication commands such as `START REPLICA`, `STOP REPLICA`, `RESET REPLICA`, and `SHOW REPLICA STATUS`.
- MySQL 8.0.23 introduced `CHANGE REPLICATION SOURCE TO` to replace `CHANGE MASTER TO`.
- MySQL 8.0.26 introduced `mysqldump --source-data` to replace `--master-data`; the old name was deprecated.
- MySQL 8.4 introduced `RESET BINARY LOGS AND GTIDS` to replace `RESET MASTER`, alongside `SHOW BINARY LOG STATUS` to replace `SHOW MASTER STATUS`; old names are marked deprecated in this release line.

Never assume every legacy command was deleted the moment a new command appeared. In transitional releases, legacy commands may still run while emitting deprecation warnings. Automation code should branch by version or use compatible administrative libraries while monitoring warnings during upgrades.

Examples of version-specific status queries:

```sql
-- MySQL 5.7 / releases prior to new names:
SHOW MASTER STATUS;
SHOW SLAVE STATUS;

-- MySQL 8.0.22+:
SHOW REPLICA STATUS;

-- MySQL 8.4:
SHOW BINARY LOG STATUS;
SHOW REPLICA STATUS;
```

Do not run all statements blindly in an unbranched script across every version. An unsupported command can abort the script mid-run, yielding incomplete status reports.

### 5. PITR Depends on a Continuous Backup and Binlog Chain

PITR is the process of restoring a full backup and replaying binary log events from the backup's consistent point up to immediately before or at the target recovery time. This chain works only if every needed log segment remains intact and readable.

A minimal dataset for PITR includes:

- A consistent full backup and metadata describing how it was created.
- File/position coordinates or GTID set at backup time.
- Consecutive binary logs from those coordinates through the target time.
- MySQL version and configuration details required to interpret and replay logs.
- Post-replay data validation procedures.

If a file mid-chain is purged or reset, replay can halt at the gap. The backup can still restore to the backup creation point, but cannot advance past the missing intermediate transactions without another archive copy.

#### 5.1. Recording coordinates at backup time

For logical backup workflows, record binlog/GTID coordinates using the appropriate utility option: `mysqldump --master-data` in older releases, or `mysqldump --source-data` from MySQL 8.0.26 onward. `--master-data` was deprecated at that milestone. Exact option names and required privileges vary by version; check `mysqldump --help` for your exact client. For physical backups, use metadata produced by the physical backup tool—never infer coordinates from the active log file after the backup completes.

Record server identity and state:

```sql
SELECT
  VERSION() AS mysql_version,
  @@server_uuid AS server_uuid,
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged,
  @@GLOBAL.log_bin AS log_bin;
```

Save the output alongside the backup, timestamp, and instance identifier. Never record only the binlog filename; keep the exact position or GTID set confirmed by the backup tool.

#### 5.2. Replaying binlogs to a target point in time

Illustrative example replaying a binlog range on an isolated recovery server:

```bash
mysqlbinlog \
  --start-position=154 \
  --stop-datetime="2026-11-18 10:14:59" \
  binlog.000123 binlog.000124 \
  | mysql -h restore-host -u restore_user -p
```

In this example, the start coordinate must come from backup metadata; the stop time precedes the erroneous operation. Replace filenames, positions, and timestamps with actual values. Depending on the goal, `--stop-position` can stop at an exact event boundary rather than a timestamp. When using timestamps, verify the timestamp time zone and inspect binlog contents to avoid over- or under-replaying transactions.

When binlogs reside on a remote server or archive store, download and verify files before replaying. Preserve strict file order; verify checksums and never skip intermediate files. In sensitive recoveries, export output to an SQL file for inspection first before executing on the recovery instance.

#### 5.3. When a reset breaks the PITR chain

Suppose a full backup was taken at `binlog.000120:800`, but an operator later ran a full reset. Files `binlog.000121` onward were deleted from the server and file numbering restarted. The backup still contains data at the original coordinate, yet the instance no longer has binlogs to replay subsequent changes.

PITR can continue only if the deleted files were archived independently, completely, and in order. If no archive exists, recovery is limited to the backup state or another available backup. A bare GTID set alone cannot reconstruct transaction contents.

### 6. Safety Procedure Before Purging or Resetting

Log the action in a change record and execute in this order:

1. **Define the goal.** Do you need to rotate, free space by purging, rebuild a replica, or initialize a lab instance? Choose the right command for the goal.
2. **Verify the version.** Record `SELECT VERSION()` and verify supported syntax. Never run 8.4 command names on older servers.
3. **Capture pre-change state.** Save `SHOW BINARY LOGS`, binlog status, `gtid_executed`, `gtid_purged`, status of every replica/channel, and latest backup metadata.
4. **Reconcile log dependencies.** Check replica lag, archives, CDC, backup retention, and the PITR window that must be protected.
5. **Ensure independent copies.** If policy requires retaining binlogs, verify archive checksums, sizes, and readability; merely seeing files in a directory does not prove an archive is usable.
6. **Execute in a maintenance window.** Use a least-privilege account, run the single approved operation, and capture output.
7. **Verify post-action state.** Inspect the binlog list, new position, GTID sets, replication status, and warnings. For resets, confirm plans to rebuild the backup chain and replicas.
8. **Test recoverability.** Use a copy or test instance to restore a backup and replay archived binlogs. Record recovery time and achieved data point.

Never use `RESET MASTER` or `RESET BINARY LOGS AND GTIDS` as a routine housekeeping step. Log deletion must follow designed retention, not a desire to empty the log directory.

### 7. Troubleshooting

| Symptom | Common cause | Remediation approach |
|---|---|---|
| Replica reports missing required binlog | File was purged, reset, or archive is missing | Identify missing file/GTID; locate verified archive or rebuild replica from a fresh backup |
| `SHOW MASTER STATUS` fails after upgrade | Newer version prefers `SHOW BINARY LOG STATUS` syntax | Check version; use the new command on MySQL 8.4 |
| `RESET MASTER` emits deprecation warning | Running on MySQL 8.4 | Halt old script and migrate to new syntax after re-evaluating destructive impact |
| `RESET BINARY LOGS AND GTIDS` unrecognized | Server is older than MySQL 8.4 or does not support that syntax | Consult exact version documentation; never auto-substitute without verifying semantics |
| `SET GTID_PURGED` rejected | GTID set intersects existing history, binlog state, or version constraints | Read error message, compare GTID sets, and prepare target instance cleanly; never wipe history to force execution |
| Auto-position replica still fails to sync | Source purged transactions needed by replica or baselines diverge | Reconcile GTID sets, archives, and backups; auto-position cannot restore lost binlog content |
| PITR halts mid-chain | Missing file, corrupted file, wrong order, or wrong start coordinate | Check index, checksums, backup metadata, and log timeframe; locate supplemental archives |
| Admin script works on 8.0 but errors on 8.4 | Legacy command name deprecated or replaced | Branch on `VERSION()` and test scripts across each release line before rollout |

### 8. Change Control Checklist

Before completing any binlog/GTID-related change, confirm:

- [ ] Clearly identified the target server and its source/replica role.
- [ ] Recorded MySQL version and selected exact syntax.
- [ ] Distinguished rotate, purge, binlog reset, and replica reset.
- [ ] Saved `gtid_executed`, `gtid_purged`, file/position, and binlog list prior to the change.
- [ ] Checked replica lag, channels, CDC consumers, and downstream systems.
- [ ] Verified independent binlog archives if PITR protection is required.
- [ ] Confirmed backups are restorable and backup coordinates are accurate.
- [ ] Evaluated the operation's impact on the PITR chain and replica re-seeding plan.
- [ ] Obtained approval, maintenance window, designated operator, and recovery plan.
- [ ] Verified post-operation state and ran test restore/replay where appropriate.

### 9. Practice Exercises

A system runs MySQL 8.0.35 with GTID enabled and two replicas. A full backup was taken yesterday; binary logs from the backup point to the present are retained for PITR. An administrator suggests running `RESET MASTER` to free disk space.

1. Why are `FLUSH BINARY LOGS`, `PURGE BINARY LOGS`, and `RESET MASTER` not interchangeable?
2. Before purging a file, what must you verify on the two replicas and in the archive store?
3. Explain the difference between `gtid_executed` and `gtid_purged` using a sample GTID set.
4. If a replica needs a GTID already purged from the source, why cannot `SOURCE_AUTO_POSITION=1` resolve it automatically?
5. Which syntax would you choose when migrating a reset script from MySQL 8.0 to 8.4? What must be checked before rollout?
6. If all binlogs on the source are reset, up to what point can yesterday's backup still recover? What condition allows continuing PITR up to today?
7. A new server is provisioned from a logical dump containing `SET @@GLOBAL.GTID_PURGED`. Why must the target server's GTID state be checked before importing?

### 10. Operating Principles

The binary log is part of a time-bounded, ordered recovery chain. Rotating creates a new file; purging deletes part of history; resetting wipes all binlog history and resets GTID state; resetting a replica affects relay logs and metadata on the replica. Choose the right operation, match the exact version, and verify every consumer's needs before removing logs. Whenever in doubt about GTID or replication, investigate data and transaction history before altering metadata. PITR capability is guaranteed only when full backups, consistent coordinates, and all required binlogs remain intact, readable, and tested for recovery.
