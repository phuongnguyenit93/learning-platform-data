# Point-in-Time Recovery from a Baseline Backup and Binary Log Chain

Point-in-time recovery (PITR) restores MySQL from a consistent baseline backup and then replays events from the binary log up to the exact point in time required for recovery. The baseline backup returns the server to a known state; the binary log provides the changes that occurred after that state. For PITR to succeed, you must have accurate starting coordinates, a continuous log chain, and a clearly defined stop point.

This lesson belongs to the **Binary Log and PITR** chapter of the `DATABASE_MYSQL` module. The module helps learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. Learners practice reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. PITR is an operational skill that minimizes data loss during accidental deletions, bad updates, or incidents requiring rollback to an earlier point in time.

## 1. What Does the Binary Log Store?

The binary log (binlog) records events that modify data or database structure. MySQL uses the binlog for replication and point-in-time recovery. A binlog sequence typically consists of multiple sequentially numbered files, for example:

~~~text
mysql-bin.000120
mysql-bin.000121
mysql-bin.000122
mysql-bin.index
~~~

The index file lists the binary logs managed by the server. Each log file contains events with byte positions, timestamps, transaction details, and the data needed to reconstruct changes. When the current file reaches its limit or is rotated, MySQL creates the next file.

Common event groups:

- **Format description and metadata:** describes the binlog format, version, and event information.
- **GTID event:** global transaction identifier when GTID is enabled.
- **Query event:** typically records DDL statements and statement-logged events.
- **Table map and row events:** describes tables and row changes when using row-based logging.
- **Xid/commit event:** marks the end of a committed transaction.

The binlog is not a full data copy. It is only meaningful when applied on top of the right baseline state and in the proper order. A missing, corrupted, or mismatched-lineage file from another server can break PITR.

## 2. Enabling and Configuring the Binary Log

On a server that must support PITR, check the current configuration:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_do_db';
SHOW VARIABLES LIKE 'binlog_ignore_db';
SHOW BINARY LOGS;
~~~

The command to inspect current log status depends on version. On many MySQL 8.0 releases you can use:

~~~sql
SHOW MASTER STATUS;
~~~

On MySQL 8.4, use the new name:

~~~sql
SHOW BINARY LOG STATUS;
~~~

The result shows the current log file and next byte position, along with GTID information if enabled. Record these coordinates alongside the associated backup.

An example configuration under the `[mysqld]` section of the configuration file:

~~~ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
sync_binlog=1
binlog_expire_logs_seconds=1209600
~~~

Meaning:

- **server_id:** unique numeric identifier for the server within a replication topology. Must be non-zero and not collide with other servers in the topology.
- **log_bin:** enables the binary log and specifies the log basename/path.
- **binlog_format=ROW:** logs changes at the row level. This is generally the right choice for replication and PITR because logs reflect the actual rows changed, avoiding discrepancies from re-executing SQL statements.
- **sync_binlog=1:** requests syncing the binlog to storage after every transaction commit. This increases binlog durability during system crashes, though it can increase I/O overhead.
- **binlog_expire_logs_seconds:** duration before MySQL automatically expires logs. The example above is 14 days; adjust according to backup cadence, PITR requirements, disk capacity, and off-server log archive retention.

If **binlog_do_db** or **binlog_ignore_db** is configured, check whether filtering rules exclude databases needed for recovery. Events not written to the binlog cannot be reconstructed via PITR. If taking backups from a replica and intending to use the replica's binlogs to recover changes received from the source, evaluate **log_replica_updates**.

If GTID is required, configuration also involves:

~~~ini
gtid_mode=ON
enforce_gtid_consistency=ON
~~~

Enabling GTID on a running system must follow a migration path compatible with the replication topology and MySQL version; never merely add those two lines and restart arbitrarily. GTID helps identify transactions across servers and supports replication synchronization, but you still need backup metadata and a complete binlog chain for PITR.

After changing configuration, restart if variables require a restart, then re-verify the values. Protect log file access permissions since binlogs can contain business data, statements, and sensitive values.

## 3. Keeping the Binary Log Chain Continuous

A backup can only be replayed up to the point where the corresponding binlog chain remains complete. You must manage the active file, rotated files, and off-server archived copies.

Inspect log files:

~~~sql
SHOW BINARY LOGS;
~~~

You can check retention-related variables:

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'sync_binlog';
~~~

Key operating principles:

1. Archive binlogs to an independent backup system on a short enough interval to reduce log loss risk if the server or disk fails.
2. Retain files from the backup's starting point through the target PITR time, not just the newest file.
3. Verify filename continuity, file sizes, and checksums after transferring to archive storage.
4. Protect the index file, backup metadata, file/position or GTID coordinates alongside the log files.
5. Set retention long enough to cover incident detection time, recovery decision time, and restore execution.
6. Monitor disk capacity, log generation rate, and binlog write errors.

When archiving logs from a running server, avoid copying the active binlog file with ordinary file-copy commands because it may still be written to. Use MySQL-aware log collection mechanisms or rotate logs to close a file before archiving; preserve order and verify file completeness. Never modify log file contents after archiving.

Never delete binlog files directly with OS commands. Use MySQL administrative commands when purging is needed, and delete only logs guaranteed no longer needed by replicas or any backup still within the recovery window.

For example, the following command deletes binary logs older than a timestamp:

~~~sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
~~~

Or delete files preceding a specified file:

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000150';
~~~

Purging is irreversible for the deleted files. Before running it, verify that replicas have finished reading those files, every valid backup has its needed logs in archive storage, and no PITR plan depends on them. Avoid using RESET MASTER or equivalent reset commands for routine log cleanup.

## 4. Recording the Baseline Backup Coordinates

To replay exactly the changes after a backup, you need to know the position represented by the baseline backup. Two common identification methods exist:

- **File and position:** for example, file mysql-bin.000120, position 456789. This is a byte offset within a binlog file.
- **GTID set:** set of executed transactions, such as a UUID and sequence ranges. GTIDs are convenient for matching transactions across servers.

Coordinates must be recorded at the exact same consistent point as the backup. The position typically marks the next byte offset to read in the log file, so replay begins at the coordinates recorded by the backup tool. Do not capture the binlog position after the backup finishes and assume it is the replay start point; transactions occurring during the backup may or may not be included in the snapshot depending on the method.

### With `mysqldump`

MySQL clients support options to record source coordinates into the dump. Option names vary across client generations:

- Newer clients use **--source-data**.
- Older clients may use **--master-data**.

Example with a client supporting the newer name:

~~~bash
mysqldump \
  --user=backup_user \
  --password \
  --single-transaction \
  --source-data=2 \
  --routines \
  --events \
  --databases appdb \
  > appdb.sql
~~~

This option writes the source coordinates into the dump file as a comment for operator reference. To align coordinates with the snapshot, mysqldump may need a brief global read lock at the start of the process. Exact behavior depends on the client version and options used; check documentation for your exact version.

### With physical backups

Physical backup tools usually generate a separate metadata file recording binlog or GTID coordinates. For example, Percona XtraBackup may create an info file such as **xtrabackup_binlog_info**. Store this file alongside the backup, checksums, and execution logs.

With GTID, you can inspect the state:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

This GTID set must correspond to the baseline state of the backup. Use metadata produced by the backup tool rather than arbitrarily querying GTID after the backup has completed.

## 5. General PITR Workflow

Suppose a full backup exists from 01:00, binlogs are archived continuously, and an accidental deletion occurs at 10:42. The goal is to recover the state to immediately before the erroneous delete transaction.

Procedure executed on a dedicated recovery server or isolated instance:

1. **Select the baseline:** identify the latest full backup prior to the incident, verify the backup is complete/prepared, and read its coordinate metadata.
2. **Prepare the instance:** use a compatible MySQL version, install needed plugins, configure the keyring if data is encrypted, and allocate enough disk space.
3. **Restore the baseline:** for logical backups, import the dump; for physical backups, follow the tool's prepare and copy-back procedure. Example importing a dump into the recovery instance:

   ~~~bash
   mysql --host=127.0.0.1 --user=restore_admin --password < appdb.sql
   ~~~

   Use an account with appropriate privileges and confirm the dump contains only the databases to restore.
4. **Start isolated:** block applications and users from writing to the recovery instance. Do not let replication run automatically unless the goal is clearly defined.
5. **Gather binlogs:** retrieve all files from the starting coordinate through the file containing the target recovery time. Verify no files are missing mid-chain.
6. **Identify the stop point:** locate the incident-causing transaction and the ending position of the last valid transaction before it.
7. **Replay logs:** run mysqlbinlog starting after the coordinates already included in the backup and stopping at the target transaction boundary.
8. **Verify data:** validate records, row counts, structure, and business constraints.
9. **Cut over:** only after data owners confirm the results should you switch applications to the recovery instance or extract the needed data subset.

Never perform PITR directly on the source server containing data under investigation. Preserve the original server and backup/log copies so you can re-check if the initially selected timestamp proves inaccurate.

## 6. Replaying Binlogs with `mysqlbinlog`

The `mysqlbinlog` utility reads binary log files and outputs statements/events for the MySQL client to execute. With locally stored log files, you can replay from a starting position:

~~~bash
mysqlbinlog \
  --start-position=456789 \
  mysql-bin.000120 \
  mysql-bin.000121 \
  mysql-bin.000122 \
  | mysql --binary-mode=1 \
      --host=127.0.0.1 \
      --user=restore_admin \
      --password
~~~

The command above is an illustrative example. The start position applies only to the first file in the list; subsequent files are read from the beginning. Replace it with the real coordinate recorded in backup metadata. The password is entered interactively.

If the stop point lies in the last file, use both `--start-position` and `--stop-position`:

~~~bash
mysqlbinlog \
  --start-position=456789 \
  --stop-position=987654 \
  mysql-bin.000120 \
  mysql-bin.000121 \
  | mysql --binary-mode=1 \
      --host=127.0.0.1 \
      --user=restore_admin \
      --password
~~~

In this example, `stop-position` is a position within the last specified file. Choose a position after the last valid transaction completes and before the incident transaction. Never cut mid-way through events of the same transaction.

To inspect binlog contents before replaying:

~~~bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  -vv \
  mysql-bin.000121 \
  > binlog-inspect.txt
~~~

With row-based logging, row data is normally stored as binary events. The decode option displays change details as comments for operator investigation. The output file is for inspection; do not treat decoded comment lines as a standalone executable SQL dump.

If you need to stop by time, `mysqlbinlog` provides `--stop-datetime`. However, displayed times can be affected by time zones and timestamp interpretation. When event positions can be identified, prefer file/position and transaction boundaries because they are more unambiguous than wall-clock timestamps.

## 7. Identifying the Incident-Causing Transaction

When an accidental delete or update occurs, identify the exact event that caused the change. Never simply pick an approximate clock time and replay everything blindly.

Investigation steps:

1. Record detection time, executing account, related application/host, and type of affected data.
2. Search audit logs, application logs, or deployment history to narrow the timeframe.
3. Use `mysqlbinlog` to inspect relevant files; for row events, use decode mode to inspect tables and row values.
4. Cross-reference GTID, timestamp, file, and position to pinpoint the transaction.
5. Identify the last valid transaction prior to the erroneous transaction.
6. Test on a temporary recovery copy, verify data, and confirm the stop point.

Example of how to recognize it in decoded output:

~~~text
# at 456789
# GTID ...
# Query ...
BEGIN
### UPDATE appdb.orders
### WHERE
###   @1=...
### SET
###   @1=...
COMMIT
~~~

This is an abbreviated illustration; actual output depends on event type and version. For DDL, the binlog typically shows SQL statements. For row events, contents may appear as numbered columns, requiring schema comparison to tell which column changed.

One transaction can contain multiple events. Replay or stop only at safe transaction boundaries. If one business action generated multiple transactions, inspect their ordering and dependencies before deciding the recovery anchor.

## 8. PITR with GTID

GTID assigns an identifier to each committed transaction. In the binlog, GTID helps track which transaction belongs to which source and avoids confusion from relying solely on byte positions.

Check executed GTIDs:

~~~sql
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

When restoring a GTID-enabled backup, the recovery instance's GTID state must be compatible with the backup's metadata. Replayed binlogs must start after transactions already included in the baseline. If you replay an already-executed transaction, MySQL may raise a GTID-already-exists error or refuse to proceed depending on state and execution mode.

GTID is useful for reconciling transaction sequences and restoring replication. However, to stop PITR before an erroneous transaction, you still must identify the target transaction and select an appropriate stop boundary. Never arbitrarily strip GTIDs just to force an import command to keep running; doing so can mask a data gap.

In a GTID environment, record the GTID set at the backup point, verify continuous logs, and follow the GTID recovery procedure appropriate for your topology. If a transaction must be skipped, first assess its impact and dependencies on a test copy.

## 9. Common PITR Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Not recording backup coordinates | Unknown starting point for replay | Record file/position or GTID alongside backup metadata |
| Missing a binlog file mid-chain | Cannot reconstruct all changes | Check archive storage and recover missing file from another copy |
| Replaying from the start of the log | Re-runs transactions already in the backup | Use exact starting coordinates |
| Stopping after the erroneous transaction | Incident still appears in recovered instance | Select a position prior to the bad transaction |
| Stopping mid-transaction | May leave incomplete state or command errors | Stop at a verified transaction boundary |
| Using binlogs from a different server | Wrong ordering or incompatible GTIDs | Verify source, server UUID, GTID, and metadata |
| Using timestamps without checking time zone | Recovery lands at wrong point in time | Verify events, file, and position |
| Purging logs too early | Loses PITR capability for older backups | Design retention around RPO/RTO and backup retention |
| Restoring on a server receiving live traffic | Users write new data during recovery | Isolate instance and open service only after verification |

## 10. Designing a Backup Schedule and Recovery Objectives

PITR is a chain of procedures, not a single `mysqlbinlog` command. Design backup schedules around business objectives:

- **RPO (Recovery Point Objective):** maximum acceptable data loss. Binlogs must be written and shipped to archive storage frequently enough to meet this goal.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service. Full backup size, restore speed, volume of logs to replay, and infrastructure capacity all impact RTO.
- **Full backup:** establishes periodic baselines; choose frequency based on data growth rate and restore duration.
- **Incremental backup:** if supported by your physical backup tool, use it to reduce copied data volume; still requires a valid incremental chain and sequential prepare steps.
- **Binary log archive:** ship logs to independent storage; verify checksums and readability.
- **Retention:** retain full backups and binlogs longer than the maximum time needed to detect an incident and decide on recovery.
- **Restore drill:** rehearse recovery in an isolated environment, measure duration, and log issues.

A system with nightly full backups that retains binlogs for only a few hours cannot recover to points farther back than the retained logs. Conversely, retaining binlogs for weeks without valid full backups can make replay times unacceptably long. Balance backup frequency, log volume, storage capacity, and RTO.

## 11. Pre- and Post-PITR Checklist

**Before running:**

- [ ] Select the full backup prior to the incident time and verify completion/prepare status.
- [ ] Read file/position or GTID set from backup metadata.
- [ ] Gather continuous binlogs from those coordinates through the target time.
- [ ] Identify the erroneous transaction and stop position prior to it.
- [ ] Prepare a compatible instance, keyring/plugins, and disk space.
- [ ] Isolate applications, replication, and any unintended write streams.
- [ ] Preserve the original data source intact for re-investigation.

**After running:**

- [ ] Inspect execution logs and exit codes of `mysqlbinlog`/`mysql` clients.
- [ ] Confirm final GTID/file position matches the stop point.
- [ ] Reconcile affected records and related tables.
- [ ] Check constraints, triggers, routines, events, and required privileges.
- [ ] Have data owners sign off on results before switching traffic.
- [ ] Document recovery duration, backup used, binlog chain, and stop point.

## 12. Key Takeaways

- A full backup provides the baseline state; the binlog supplies changes occurring after the baseline coordinates.
- Record file/position or GTID coordinates at the exact consistent point of the backup.
- Store continuous binlogs in an independent location and do not purge while valid backups still depend on them.
- Replay via `mysqlbinlog` in strict order; begin after changes already captured in the backup.
- Stop before the incident transaction and at a valid transaction boundary.
- GTID helps identify transactions and synchronize replication; it does not replace picking the right stop point.
- Test PITR on an isolated instance, verify data, and measure RTO before cutting applications over.

PITR is reliable when the baseline backup, coordinate metadata, and binary log chain form a continuous recovery path. Rehearse the full workflow from restore to log replay and data verification; only when all steps are proven in practice do RPO/RTO targets have a realistic foundation.
