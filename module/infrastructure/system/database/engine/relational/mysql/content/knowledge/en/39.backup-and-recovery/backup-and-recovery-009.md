# GTID, Binary Log Coordinates, and Backup Metadata

A MySQL backup only shows data at one point in time. When you need to recover to a later point in time, or stand up a replica, you also need to know the exact boundary in transaction history where the backup stopped. MySQL provides two ways to represent this checkpoint: **GTID** and **binary log coordinates** (the binary log file name plus the byte offset inside the file). Metadata accompanying the backup links that checkpoint to the data snapshot so recovery can continue cleanly from the very next transaction.

If you keep only the dump file without preserving the transaction checkpoint and required binary logs, you may recover partial data without being able to prove how current the data is. Conversely, a standalone GTID set or file/position pair contains no data to restore. The data copy, consistency checkpoint, and log chain must be managed together.

## 1. Two Types of Transaction Checkpoints

### Binary Log Coordinates

Binary logs record data modification events and certain structural changes so replicas or recovery tools can replay them. A coordinate has two parts:

- **File**: the binary log name, for example `mysql-bin.000042`.
- **Position**: the byte offset within that file, for example `123456`.

When a backup tool records a coordinate, it must represent a boundary aligned with the snapshot: transactions included in the backup lie before that checkpoint; transactions to replay start from that checkpoint. File and position are always a pair. Saving only the file name without the position cannot pinpoint the exact starting point.

For example, metadata might record:

```text
File:     mysql-bin.000042
Position: 123456
```

Position is an offset inside a specific file, not a global transaction sequence number. If binary logs have been purged from the source host with no off-host copy, the coordinate still describes the checkpoint, yet cannot help replay the lost events.

### GTID

A GTID (Global Transaction Identifier) attaches a unique identifier to every transaction written to the binary log in GTID mode. The basic format is:

```text
source_uuid:transaction_id
```

Example:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:100
```

A GTID set can contain multiple GTIDs and compress contiguous ranges:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:1-100:105:110-115,
8A1B2C3D-1111-2222-3333-444455556666:1-20
```

The UUID portion identifies the source that originated the transaction; the numeric portion is the transaction sequence number within that UUID's history. A set can contain transactions from multiple sources, so never assume a GTID set always has only one UUID.

Three common state variables:

| Variable | Meaning | Usage |
|---|---|---|
| `@@GLOBAL.gtid_executed` | The set of GTIDs executed on the server. Includes both transactions still present in binary logs and transactions already purged from binary logs. | Records transaction history applied at metadata capture time. |
| `@@GLOBAL.gtid_purged` | The set of GTIDs executed whose binary logs have already been purged. This is a subset of `gtid_executed`. | Assesses history no longer available to read from binary logs on that server. |
| `@@GLOBAL.gtid_mode` | Server GTID enablement state. | Determines whether the topology can use GTID mechanisms. |

GTIDs identify transactions without relying on file names or byte offsets. They are useful for auto-positioning replication, comparing history across servers, and determining which transactions a replica already has. However, a GTID does not contain transaction payloads and does not replace data copies or binary logs. Knowing a transaction has a GTID does not mean you still have the data to replay it.

## 2. Relationship Between Snapshot and Transaction Checkpoint

The most critical requirement is that the transaction checkpoint must correspond to the exact data snapshot. Suppose a backup reads the `orders` table at T1, but runs `SHOW BINARY LOG STATUS` separately at T2 after the application has written more orders. Using the T2 coordinate with the T1 dump skips transactions that occurred in between. Picking a checkpoint earlier than the snapshot can replay transactions already included in the dump.

Therefore, never combine a dump with a GTID or coordinate captured arbitrarily before or after the dump runs. Use the backup tool's built-in feature to capture the checkpoint at the exact consistency boundary, or use a lock-and-snapshot procedure verified for your exact version and storage engine.

For InnoDB, `mysqldump --single-transaction` creates a consistent snapshot using a transaction. When combined with `--source-data`, the tool captures binary log coordinates synchronized with the snapshot via a brief global read lock at the start of the process. During the dump, avoid DDL operations that alter table structures; DDL is not protected like InnoDB row data in the snapshot. Nor does `--single-transaction` guarantee consistency for tables using non-transactional storage engines such as MyISAM.

Coordinates and GTIDs are related representations of a checkpoint, not mechanically interchangeable substitutes. File/position tells you where to start reading in the binary log stream; the GTID set tells you which transactions have been executed. When metadata stores both, they must describe the exact same snapshot boundary. If the two values conflict, stop and investigate how the metadata was generated before recovering.

## 3. Collecting GTID and Binary Log Status

On MySQL 8.4, use `SHOW BINARY LOG STATUS` to inspect the current binary log and coordinate. On older versions, the common statement is `SHOW MASTER STATUS`:

```sql
SHOW BINARY LOG STATUS;
-- Older MySQL versions:
-- SHOW MASTER STATUS;

SHOW BINARY LOGS;

SELECT
    @@GLOBAL.server_uuid AS server_uuid,
    @@GLOBAL.gtid_mode AS gtid_mode,
    @@GLOBAL.enforce_gtid_consistency AS enforce_gtid_consistency,
    @@GLOBAL.gtid_executed AS gtid_executed,
    @@GLOBAL.gtid_purged AS gtid_purged;

SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
```

`SHOW BINARY LOG STATUS` reports the current state at the instant the statement runs. Running it standalone after a snapshot has completed does not automatically turn the output into the old snapshot's checkpoint. Use it to inspect server state or cross-check metadata; for a dump, capture the checkpoint from the dump process itself.

When enabling GTIDs, configuration typically needs:

```ini
[mysqld]
server_id = 101
log_bin = mysql-bin
gtid_mode = ON
enforce_gtid_consistency = ON
```

`server_id` must be unique within the replication topology. `server_uuid` must also be unique among concurrently running servers. When cloning a `datadir` to stand up a new host, ensure the new host gets its own UUID before joining the topology; two servers sharing a UUID can cause GTID identity collisions. Enabling GTIDs on a live system must follow a version-appropriate transition path—never simply add two config lines and restart casually.

To use binary logs for point-in-time recovery, `log_bin` must be enabled, enough log files must be retained, and logs must be shipped to independent storage before the server purges them. Log retention must exceed the recovery window the organization needs. A complete backup missing the binary log segment between the backup checkpoint and the target recovery time cannot perform PITR to that point.

## 4. Recording Metadata Alongside Logical Backups

For InnoDB, a `mysqldump` command commonly used to create a dump with checkpoint information looks like this:

This example assumes the source has GTIDs enabled (`gtid_mode=ON`) and the recovery target is prepared under a GTID plan. If the source does not use GTIDs, omit `--set-gtid-purged=ON` and save coordinates with appropriate metadata; do not enable this option mechanically.

```bash
mysqldump \
  --single-transaction \
  --source-data=2 \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --triggers \
  --databases appdb \
  > appdb.sql
```

Meaning of key options:

- `--single-transaction`: reads InnoDB data from a consistent snapshot.
- `--source-data=2`: writes the `CHANGE REPLICATION SOURCE TO` statement as a comment in the dump, with file and position at the boundary matching the snapshot. Value `1` writes it uncommented; `2` records the checkpoint without executing the statement on import. Older MySQL versions name this option `--master-data`.
- `--set-gtid-purged=ON`: writes the source's GTID set into the dump via a statement setting `GTID_PURGED`. On restore, this statement affects GTID history on the target server; assess the target's GTID state and existing history before importing. Never apply it blindly onto a server with different existing transaction history.
- `--routines`, `--events`, `--triggers`: include stored routines, events, and triggers in the dump scope. If accounts, roles, grants, or out-of-schema configurations are needed, maintain a separate backup procedure for those components.

`--source-data` requires appropriate privileges to retrieve coordinates and acquire the needed lock. The global read lock is only held briefly when properly combined with `--single-transaction`, yet it can still wait on or affect writes at startup time. Test on your actual MySQL version and schedule according to system load. Never let DDL run concurrently while the dump is reading its snapshot.

Inside the dump, the file header may contain GTID information and coordinate statements. Keep the dump file intact and extract that metadata into an inventory manifest so recovery tooling can search it without reading the entire file manually. If `--set-gtid-purged=AUTO` is used, behavior depends on server GTID state and version defaults; when deterministic behavior is required, explicitly choose `ON` or `OFF` according to your recovery plan.

For physical backups, the backup tool typically provides its own metadata, such as checkpoint/LSN and binary log coordinates or GTID set at the checkpoint. Use the metadata generated by the tool itself. Never run an SQL statement after copying `datadir` and attach its coordinates to the copy, as the two operations can reflect different moments in time. After preparing a physical backup, maintain the completed/prepared backup state exactly as required by the tool.

## 5. Manifests That Should Accompany Backups

A good manifest lets on-call operators see where a backup came from, what it contains, and which logs can be replayed. Example internal metadata structure:

```yaml
backup_id: appdb-2026-11-19T010000Z
created_at_utc: "2026-11-19T01:00:00Z"
backup_type: logical
tool: mysqldump
tool_version: "8.4.x"
source:
  server_uuid: "3e11fa47-71ca-11e1-9e33-c80aa9429562"
  server_version: "8.4.x"
  schemas: [appdb]
  gtid_mode: ON
snapshot:
  consistency: "InnoDB consistent snapshot"
  ddl_frozen: true
  binlog_file: mysql-bin.000042
  binlog_position: 123456
  gtid_executed: "3E11FA47-71CA-11E1-9E33-C80AA9429562:1-100"
  gtid_purged: "3E11FA47-71CA-11E1-9E33-C80AA9429562:1-20"
artifacts:
  - path: appdb.sql
    size_bytes: 123456789
    sha256: "<sha256-checksum>"
binary_logs:
  first_required_file: mysql-bin.000042
  last_archived_file: mysql-bin.000050
encryption:
  encrypted: true
  key_reference: backup-key-prod-01
```

The values in this example only illustrate structure; real values must come from the tools and storage system. `gtid_purged` is the set of purged GTIDs, not the replay starting point. `gtid_executed` describes the transactions executed at the checkpoint; if a GTID set grows very large, store it in a separate checksummed metadata file rather than truncating the string.

A manifest should include at least these categories of information:

| Category | Information to Store | Rationale |
|---|---|---|
| Identity | Backup ID, UTC timestamp, source host, `server_uuid`, MySQL version | Distinguish backups and recreate a compatible environment. |
| Scope | Included/excluded schemas and tables, whether routines, triggers, events, accounts/grants were backed up | Avoid assuming a dump contains components that were actually skipped. |
| Consistency | Storage engine, snapshot/lock mode, start and end timestamps, whether DDL was frozen | Assess whether the copy represents a consistent data state. |
| Log checkpoint | Binary log file/position, `gtid_executed`, `gtid_purged`, source UUID | Establish the splice point between snapshot and transaction history. |
| Tooling | Tool name, version, flags, exit code, and result logs | Reproduce the process and troubleshoot backup failures. |
| Integrity | Size, checksums, part counts, upload/copy status | Detect missing or corrupted files during storage/transfer. |
| Dependencies | Keyring, encryption keys, plugins, configuration, certificates, and secrets via separate workflow | Ensure the system can decrypt and start after recovery. |
| Continuation logs | List of archived binary logs, time spans, checksums, and storage locations | Verify the log chain is continuous from the backup checkpoint to the recovery point. |

Metadata must be protected at the same level as backups. GTID sets, schema names, host addresses, and log file names can leak operational details. Checksums detect file corruption, though they do not prove the backup source is trustworthy; add write access controls, signatures, or immutable storage if required by policy.

## 6. Using Checkpoints to Recover to a Point in Time

The point-in-time recovery (PITR) process has three parts:

1. Select the most recent consistent backup taken before the target recovery time.
2. Restore the backup onto a suitable target server and confirm its initial state.
3. Replay binary logs from the exact backup checkpoint up to right before the transaction to exclude or up to the chosen recovery point.

Suppose the manifest indicates the snapshot corresponds to `mysql-bin.000042` at position `123456`. After importing the dump, replay subsequent logs starting from that checkpoint:

```bash
mysqlbinlog \
  --start-position=123456 \
  --stop-position=987654 \
  mysql-bin.000042 mysql-bin.000043 \
  | mysql
```

`--start-position` applies to the first file in the list. `--stop-position` limits the stop point in the last file processed by the command; identify the exact file containing the stop point and choose a valid event/transaction boundary. In practice, if the stop point sits in a different file, specify that file and its matching position explicitly. Never guess a position by adding file sizes or borrowing an offset from another file.

You can use `--stop-datetime` when stopping by timestamp:

```bash
mysqlbinlog \
  --start-position=123456 \
  --stop-datetime="2026-11-19 10:25:00" \
  mysql-bin.000042 mysql-bin.000043 \
  | mysql
```

Timestamps depend on time zone and event timestamps; multiple transactions can sit very close together. For accidental deletes or updates requiring an exact cutoff, inspect the logs, locate the transaction, and use an exact position boundary. Always verify the clock and time zone of the source host, recovery host, and analysis session.

Before replaying, verify all consecutive files exist starting from the backup checkpoint. Binary logs can be inspected for investigation via:

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000042 > binlog-review.txt
```

This decode/verbose mode is useful for reading row events and investigating, but the output includes human-readable annotations; do not use the transformed text for replay instead of a normal executable `mysqlbinlog` stream. Preserve original binary log files and verify checksums before using them.

If the backup recorded `GTID_PURGED`, the snapshot's GTIDs are already marked as present on the recovery server. Therefore, replayed logs must start after the corresponding snapshot boundary. Replaying transactions already inside the dump can cause the server to reject duplicate GTIDs or trigger recovery errors. Never substitute a GTID set captured at another time for the dump's actual checkpoint.

## 7. GTIDs in Replica Provisioning and Server Cutover

With GTIDs, a replica can ask the source to send transactions it does not yet have, instead of operators manually calculating file/position. On MySQL versions supporting the modern syntax:

```sql
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST = 'mysql-source.internal',
    SOURCE_PORT = 3306,
    SOURCE_USER = 'replication_user',
    SOURCE_PASSWORD = 'managed-secret',
    SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

Older releases use `CHANGE MASTER TO` and `MASTER_AUTO_POSITION=1`. Never place real passwords in scripts or shell history; use an appropriate secret mechanism. `SOURCE_AUTO_POSITION=1` only works when GTID configuration and historical state on both sides are compatible.

When provisioning a replica from a source backup, the GTID set inside the backup tells the source which transactions the replica already has. The source can only send missing GTIDs if the corresponding binary logs are still retained on the source. If the source has purged required transactions, auto-position cannot regenerate the missing logs; you must supply a newer backup or re-seed the replica from a backup source retaining sufficient history.

Matching GTID sets do not guarantee two servers hold identical data. Manually executed transactions on a replica, skipped transactions, or out-of-band data edits can occur. Before bringing a replica into the topology, compare GTID sets, check for errant transactions, verify data with checksums/reconciliation, and review replication filters. Never treat `START REPLICA` succeeding as sole proof that data is identical.

## 8. Common Mistakes Managing Checkpoints and Metadata

| Mistake | Why It Happens | Fix |
|---|---|---|
| Running `SHOW BINARY LOG STATUS` after a dump and attaching it to the dump | Coordinate is newer than snapshot; transactions during the gap are misrepresented. | Capture the checkpoint via the backup tool's option or a synchronized snapshot workflow. |
| Saving only the file name without position | Unknown byte offset to start reading binary logs. | Save the intact file/position pair and cross-check against original metadata. |
| Binary logs already purged | Log chain is incomplete from backup checkpoint to recovery time. | Archive logs off-host, set retention per RPO, and run periodic restore tests. |
| Using a GTID set from another server | UUID and transaction history do not match the backup source. | Bind the GTID set to `server_uuid`, backup ID, and metadata of the same snapshot. |
| Importing a dump with `GTID_PURGED` onto a server with different history | Target GTID set conflicts or fails assignment rules. | Use a clean recovery server per plan; inspect existing GTIDs before importing. |
| Cloning a server while keeping duplicate `server_uuid` | Two servers identify as the same GTID source. | Assign a unique UUID to the cloned host before joining replication. |
| InnoDB-only dump when schema contains MyISAM tables | `--single-transaction` does not provide a consistent snapshot for non-transactional tables. | Convert engines appropriately or use another locking/backup strategy covering those tables. |
| DDL running during dump | Structural changes are not protected like data snapshots. | Coordinate backup windows and control migrations/DDL. |
| Having dump file but missing encryption keys | Data cannot be decrypted after an incident. | Back up keyrings and key-recovery docs under a separate access-controlled workflow. |
| Checking only exit code, not output files | Files may be missing, corrupted, partially uploaded, or mismatched with manifest. | Verify size, checksums, metadata, readability, and test restores. |

## 9. Operational and Verification Workflow

Before marking a backup ready for recovery, follow these steps:

1. **Confirm source and configuration.** Record MySQL version, `server_uuid`, binary log status, GTID mode, storage engines, and replication topology.
2. **Create a consistent snapshot.** Use a method suited to the backup type; control DDL and non-transactional tables.
3. **Record checkpoint with snapshot.** Save the file/position and GTID set provided by the backup tool. Never attach metadata captured at a different time.
4. **Archive continuation binary logs.** Continuously archive files starting from the needed checkpoint, preserve ordering and checksums, and monitor for gaps in the log chain.
5. **Save manifest and dependencies.** Record data scope, tool, flags, consistency status, encryption keys, configuration, and non-table objects.
6. **Verify integrity.** Confirm backup files, manifest, checksums, and logs are readable; alert if metadata is missing or mismatched.
7. **Test recovery.** Restore into an isolated environment, replay logs to a selected checkpoint, verify the application, and record actual timings.
8. **Measure RPO/RTO.** RPO depends on snapshot frequency and binary log continuity; RTO depends on restore, replay, verification, and application cutover speed.

A backup should only be marked satisfactory once three things are proven: the snapshot is consistent, metadata points to the snapshot's exact transaction boundary, and the required binary log chain is intact up to the recovery point. Alert automatically when binary log archiving stalls, source retention is about to purge unarchived logs, or a manifest lacks matching GTID/coordinate metadata.

## 10. Backup Review Checklist

- [ ] Backup ID, UTC timestamp, server version, and `server_uuid` are present.
- [ ] Schema/table scope and inclusion of routines, triggers, and events are explicitly documented.
- [ ] Snapshot mechanism fits storage engines; DDL was controlled during backup.
- [ ] Coordinates include both binary log file and position, captured from the exact snapshot.
- [ ] Full GTID set is saved and tied to the same source and snapshot.
- [ ] `gtid_purged` is not mistaken for total executed transactions or backup content.
- [ ] Binary logs from backup checkpoint to recovery window are archived continuously with checksums.
- [ ] Manifest, backup, and encryption keys are securely stored and accessible during incidents.
- [ ] A GTID handling procedure exists when restoring onto a server with prior transaction history.
- [ ] Restore and PITR have been tested, data verified, and recovery duration measured.

GTIDs excel at describing executed transaction sets and supporting auto-positioning replication. Binary log coordinates excel at pinpointing where to start reading in a log stream. Metadata accompanying a backup bridges both concepts to the actual data snapshot. Only when all three are created, stored, and verified in sync can operations recover cleanly and explain precisely how far data was restored.
