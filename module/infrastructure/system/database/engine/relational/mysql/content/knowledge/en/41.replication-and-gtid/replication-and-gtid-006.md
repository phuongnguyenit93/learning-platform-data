# `gtid_executed`, `gtid_purged`, and their relationship with backups

In GTID-enabled MySQL, every transaction is identified by a unique code of the form `source_uuid:transaction_number`. GTID sets let a server and its replicas track which transactions have executed, which still need to be transmitted, and which have already been removed from the binary logs. Two key states are `gtid_executed` and `gtid_purged`.

When creating a backup to provision a replica or restore onto another server, GTID metadata must match the data actually contained in the backup. If too few GTIDs are recorded, the replica may replay transactions already present in the data; if too many GTIDs are recorded, the replica may skip transactions not yet included in the backup. Understanding these two sets properly helps prevent data loss and auto-position replication errors.

This lesson belongs to the **Replication and GTID** chapter of the `DATABASE_MYSQL` module. The module covers table design, queries, indexes, transactions, privilege management, backups, and MySQL operations. The examples use MySQL 8.0 syntax; check the documentation for your exact version before running any GTID-modifying operation in production.

After this lesson, you will be able to:

- Read and interpret a GTID set.
- Distinguish `gtid_executed` from `gtid_purged`.
- Explain why `gtid_purged` is a subset of `gtid_executed`.
- Choose how to record GTIDs when taking and restoring backups.
- Recognize the risks of `mysqldump --set-gtid-purged` with partial database/table dumps.
- Provision a replica using GTID auto-position and handle missing binary log scenarios.

## 1. What is a GTID set?

A GTID (Global Transaction Identifier) is a unique identifier for a transaction recorded in the replication system. In MySQL, a GTID has the structure:

```text
source_uuid:transaction_number
```

Example:

```text
24bc7850-2c16-11ee-be56-0242ac120002:105
```

`source_uuid` identifies the origin that generated the GTID; `transaction_number` is the sequence number within that origin. A GTID set is a collection of one or more contiguous number intervals belonging to one or more UUIDs.

Example of a GTID set:

```text
24bc7850-2c16-11ee-be56-0242ac120002:1-105:110-115,
7a1d5c12-3a44-11ee-9b12-0242ac120002:1-20
```

This set contains GTIDs `1` through `105` and `110` through `115` for the first UUID, plus `1` through `20` for the second UUID. The interval `106-109` of the first UUID is absent from the set.

Examples using `uuid-A` in the explanation are shorthand labels for readability. In real SQL statements, UUIDs must follow valid UUID formatting like the full example above.

GTID sets represent replication state by transaction rather than relying only on binary log file names and byte positions. This allows a replica to automatically request missing transactions when using auto-position.

## 2. `gtid_executed`: transactions that have been executed

`@@GLOBAL.gtid_executed` is the set of GTIDs the server records as executed. This set includes both transactions whose GTIDs still remain in the binary logs and transactions whose GTIDs have already been purged from the binary logs. Thus, it represents the execution history recorded by the server, not merely the transactions still readable from current binlog files.

Check its value:

```sql
SELECT @@GLOBAL.gtid_executed;
```

Or view both GTID variables together:

```sql
SHOW VARIABLES LIKE 'gtid_executed';
SHOW VARIABLES LIKE 'gtid_purged';
```

Suppose a server has executed GTIDs `uuid-A:1-500`. Then `gtid_executed` might contain:

```text
uuid-A:1-500
```

If current binary logs only retain transactions `uuid-A:201-500`, the older GTIDs remain in `gtid_executed` even though the files containing them are no longer on the server.

`gtid_executed` is state metadata managed by MySQL. Do not manually edit system tables or attempt to fabricate GTID sets by modifying data files. When loading GTID state from a backup, use MySQL-supported mechanisms and follow the constraints of `gtid_purged`.

## 3. `gtid_purged`: GTIDs removed from binary logs

`@@GLOBAL.gtid_purged` is the set of GTIDs that have been executed but are no longer present in the binary logs currently on the server. This set can also be configured when loading GTID state from a backup onto a new server.

Check it:

```sql
SELECT @@GLOBAL.gtid_purged;
```

Example:

```text
gtid_executed = uuid-A:1-500
gtid_purged   = uuid-A:1-200
```

This means the server has executed transactions `1-500`, of which `1-200` are no longer in the binary logs. Transactions `201-500` represent the portion of GTID history still retained in the binlogs, assuming no other UUIDs or gaps exist.

In normal operation:

\[
\texttt{gtid\_purged} \subseteq \texttt{gtid\_executed}
\]

`gtid_purged` is not a list of deleted files, nor is it a command that deletes data from tables. It is the set of transaction identifiers the server can no longer serve from its current binary logs.

When running `PURGE BINARY LOGS`, MySQL updates the GTID state corresponding to transactions removed from the logs. Purging log files does not remove those transactions from `gtid_executed`; data created by those transactions remains in the database until another data operation changes it.

## 4. Comparing the two GTID sets

| Aspect | `gtid_executed` | `gtid_purged` |
|---|---|---|
| Meaning | All GTIDs recorded as executed by the server | GTIDs executed but no longer present in current binary logs |
| Includes GTIDs still in binlogs? | Yes | No |
| Includes purged GTIDs? | Yes | Yes |
| Role in auto-position? | Indicates which transactions a replica already has | Indicates which transactions the source can no longer send from current binlogs |
| Relationship | Superset | Subset of `gtid_executed` |

Imagine a server with `gtid_executed = uuid-A:1-500` and `gtid_purged = uuid-A:1-200`:

```text
gtid_executed:     [1 ----------------------------------------- 500]
gtid_purged:       [1 ------------- 200]
remaining binlogs:                 [201 ----------------------- 500]
```

A replica holding GTIDs `1-350` is missing only `351-500`, so the source can send the missing portion since the corresponding binlogs are retained. A replica holding only `1-150` is missing `151-500`; because the source has already purged `151-200`, the source cannot provide the complete sequence of transactions needed by that replica.

## 5. Checking GTID status on source and replica

On the source:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_mode,
  @@GLOBAL.enforce_gtid_consistency,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
```

On the replica:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;

SHOW REPLICA STATUS\G
```

Cross-check the following details:

- `server_uuid`: every server must have its own UUID. Do not copy `auto.cnf` verbatim onto an independent server running as another member of the replication topology.
- `gtid_executed`: which transactions the replica has recorded.
- `gtid_purged`: which transactions are no longer present in each server's binary logs.
- I/O and SQL applier status: whether the replica is actively receiving and applying transactions or stopped on an error.
- Missing GTIDs: which GTIDs the replica needs and whether the source still retains them.

Do not compare two GTID strings by eyeballing text length. Use GTID set functions or MySQL tools to determine containment and missing intervals.

## 6. Useful GTID set operations

MySQL provides functions to check relationships between GTID sets:

```sql
-- Check whether set A is a subset of set B
SELECT GTID_SUBSET(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-100',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-150'
);

-- Get GTIDs present in A but not in B
SELECT GTID_SUBTRACT(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-150',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-100'
);
```

The two most commonly used functions are:

- `GTID_SUBSET(set1, set2)`: returns `1` if every GTID in `set1` is in `set2`; otherwise returns `0`.
- `GTID_SUBTRACT(set1, set2)`: returns the GTIDs present in `set1` that are not in `set2`.

Example of finding GTIDs a replica is missing relative to the source:

```sql
SELECT GTID_SUBTRACT(
  '24bc7850-2c16-11ee-be56-0242ac120002:1-500',
  '24bc7850-2c16-11ee-be56-0242ac120002:1-350'
);
```

The result is `uuid-A:351-500`. In practice, substitute the illustrative strings with `@@GLOBAL.gtid_executed` from the source and replica. Run comparisons on values collected at the same point in time, or keep in mind that state may keep advancing while querying.

## 7. GTID and the lifecycle of a binary log

A new transaction committed on the source and written to the binary log increments `gtid_executed`. While the binlog file containing that transaction remains on the server, its GTID is not yet part of `gtid_purged`.

When older files are purged:

1. Binlog files containing older transactions are deleted from the server.
2. The GTIDs of purged transactions are reflected in `gtid_purged`.
3. Those GTIDs remain in `gtid_executed`.
4. The source can no longer send transactions from deleted files to replicas that have not yet received them.

Illustration:

```text
Time A:
  gtid_executed     = uuid-A:1-300
  gtid_purged       = uuid-A:1-100
  remaining binlogs = uuid-A:101-300

After purging older files:
  gtid_executed     = uuid-A:1-300
  gtid_purged       = uuid-A:1-180
  remaining binlogs = uuid-A:181-300
```

`gtid_executed` does not shrink when logs are purged; `gtid_purged` expands to reflect the portion of history no longer readable from binary logs.

## 8. Why must backups record GTID metadata?

A backup that restores data but lacks GTID metadata may not be sufficient to provision a replica with auto-position. The replica must know which transactions are already included in the backup data so it only requests missing transactions.

Suppose a backup was taken when the source had executed up to `uuid-A:500`. When restoring the backup, the target server's data already includes the effects of transactions up to that point. If the target server does not record those corresponding GTIDs, upon connecting replication it may re-request transactions already present in the backup. The consequence can be duplicate keys, double-applied data, or applier execution errors.

Conversely, if the backup metadata records `uuid-A:1-700` while the data snapshot only contains up to `uuid-A:500`, the replica will assume transactions `501-700` have already executed and skip them. This is the more dangerous case because it can lead to silent missing data without an obvious error.

Therefore, a backup used to provision a replica must be paired with a GTID set that accurately reflects the captured data state. Store alongside the backup:

- Backup creation timestamp and MySQL version.
- `server_uuid`, `gtid_executed`, and `gtid_purged` at the backup point as supported by the tool.
- Binlog file name/position if the procedure uses file/position coordinates.
- List of databases/tables actually included in the backup.
- Dump options or snapshot mode used.
- List of binlogs archived continuously after the backup point.

## 9. Logical backup with mysqldump and `--set-gtid-purged`

`mysqldump` provides the `--set-gtid-purged` option to control writing GTID-setting statements into the dump file. Common values:

| Value | Behavior |
|---|---|
| `AUTO` | Decides automatically based on the source server's GTID state; this is the default in current MySQL versions. |
| `ON` | Writes `SET @@GLOBAL.GTID_PURGED` into the dump when GTID is enabled. |
| `OFF` | Does not write `GTID_PURGED`-setting statements. |
| `COMMENTED` | Writes the related statements as comments for the operator to review and apply manually. |

When `ON`, `mysqldump` typically also emits statements disabling binary logging for the import session so restore statements do not generate a new set of GTIDs instead of the source history. Inspect the top of the actual dump file since exact output details can vary by version and combined options.

Example of dumping an entire instance to build a new replica:

```bash
mysqldump --user=backup_user --password \
  --single-transaction \
  --routines --events --triggers \
  --set-gtid-purged=ON \
  --all-databases \
  > full-instance.sql
```

With a full-instance dump, the GTID set recorded in the file represents the entire GTID history executed on the source at the time it was taken. After restoring onto an eligible target server, the GTID state enables auto-position to recognize transactions already present in the backup.

### 9.1. Critical warning for partial dumps

The GTID set written by `mysqldump` does not contain only transactions that modified the dumped databases/tables. It can include the entire `gtid_executed` on the source, even transactions that only modified databases or tables excluded from the dump.

For example, suppose a source has two databases `sales` and `payroll`. You dump only `sales`, yet the GTID set in the dump still includes transactions from both databases. If you restore that file and use its GTID state to build a replica of the source, the replica may treat `payroll` transactions as already executed even though `payroll` data was never included in the backup. The source will not resend those transactions because their GTIDs are already marked present.

Therefore:

- Never mechanically use `--set-gtid-purged=ON` for a dump containing only one database, a subset of tables, or a subset of rows if the goal is to provision a replica of the full source.
- For partial dumps used to migrate standalone data or spin up test environments, usually consider `--set-gtid-purged=OFF` so the entire source history is not marked as present on the target.
- If you need to build a replica from partial data, explicitly design the topology and replication data scope; you cannot rely on a server-wide GTID set to accurately represent a subset of data.

### 9.2. Notes on snapshots and concurrent changes

`--single-transaction` creates a consistent snapshot for InnoDB tables, but it does not block all DDL. Avoid running `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or other structural changes on objects being dumped. Non-transactional tables are not protected by an InnoDB snapshot.

When a backup will be used to build a replica, ensure GTID metadata and the data snapshot reflect the exact same logical point in time. Use a backup workflow supported by your version's documentation, retain change logs during the backup, and test restore together with auto-position. Never pair an arbitrary `gtid_executed` value grabbed after the dump with a snapshot created earlier.

## 10. Restoring backups and setting GTIDs

When restoring a dump containing `SET @@GLOBAL.GTID_PURGED`, the target server must meet MySQL's requirements for setting the GTID set. Typically, this is done on a fresh instance or an instance cleanly prepared for restoration. If the target already holds other GTIDs or transactions generated after the backup, the statement may be rejected due to conflicts or invalid preconditions.

General workflow for a new replica:

1. Prepare the new target server, ensuring a unique `server_uuid` and proper GTID configuration.
2. Restore the backup matching the documented version and scope.
3. Check `@@GLOBAL.gtid_executed` and `@@GLOBAL.gtid_purged` on the target.
4. Verify that the backup data's GTIDs are reflected in the target's GTID state.
5. Configure auto-position replication and start the replica.
6. Verify I/O/applier status, received GTIDs, and lag.

Do not run `SET GLOBAL gtid_purged` arbitrarily on a server that already holds data just to "get replication running." Doing so can mistakenly mark transactions as executed, causing the source to skip data the replica is actually missing.

### 10.1. Example of setting up a replica with auto-position

After restoring the backup and checking the GTID set, configure the connection to the source:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'replace-with-managed-secret',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

In production, use TLS and an appropriate secret management mechanism. The replication account needs the right privileges; never place real passwords in scripts, terminal history, or documentation.

With auto-position, the replica sends the GTID set it has executed to the source. The source determines which transactions the replica lacks and sends those transactions if they still remain in the binary logs. This mechanism reduces reliance on file/position, though it cannot regenerate transactions the source has already purged.

Verify:

```sql
SHOW REPLICA STATUS\G
```

Inspect `Auto_Position`, receiver/applier status, SQL/I/O errors, log files, and GTID details. Exact field names in the output may vary by version.

## 11. When the source has already purged GTIDs the replica needs

Suppose the source has:

```text
gtid_executed = uuid-A:1-1000
gtid_purged   = uuid-A:1-700
```

A replica has just restored an older backup and only has:

```text
gtid_executed = uuid-A:1-500
```

The replica needs GTIDs `501-1000`, but the source has already purged `501-700`. The source only retains binlogs for `701-1000`, so it cannot send the complete missing history. Auto-position will fail with an error stating that the source does not have one or more requested GTIDs.

Remediation options:

- Restore a newer backup that includes at least the purged transactions.
- Locate a continuous binary log archive containing the missing GTIDs and apply it using an appropriate recovery procedure.
- If no complete backup or binlog archive remains, rebuild the replica from a valid newer backup and reconfigure replication.

Do not resolve this by adding the missing GTIDs to the replica's `gtid_purged`. That merely marks them as executed; it does not recreate the data those transactions originally produced.

## 12. Rules when setting `gtid_purged`

`gtid_purged` is a special global variable with assignment constraints. Exact rules vary by MySQL version; before executing, read the documentation for your exact version and inspect current state.

Safety principles:

- Only set a GTID set when you are certain the corresponding data already exists on the target server.
- Never add an arbitrary GTID set to skip a replication error.
- Check for overlap with existing `gtid_executed` and `gtid_purged` according to your version's rules.
- Perform this on a fresh instance or inside a maintenance window with a clear restore plan.
- Never directly edit the `mysql.gtid_executed` table.
- Save the original GTID set and a rollback plan before altering GTID state.

Some MySQL versions support syntax to add or remove GTID intervals when assigning `gtid_purged`; syntax and preconditions differ across versions. Do not copy a `SET GLOBAL gtid_purged` statement from an old blog post without verifying it. For dumps produced by `mysqldump`, prefer using the generated metadata statements and restoring through the supported workflow.

## 13. Physical backups and GTID metadata

Physical backups typically copy InnoDB data files and the components needed to restore an instance. Depending on the tool, backup metadata may store the GTID set, binary log coordinates, or transaction details normalized during the prepare phase.

When using a physical backup tool:

1. Read the metadata or info file produced by the tool to obtain the backup's exact GTID set.
2. Ensure the backup workflow has completed the required prepare/recovery step before starting the server from the copy.
3. Do not grab the source's current `gtid_executed` after the backup finishes if it has advanced past the snapshot.
4. Restore onto a target instance with a unique UUID and appropriate replication configuration.
5. Compare the post-restore GTID set against the backup metadata before enabling auto-position.

With tools like MySQL Enterprise Backup or Percona XtraBackup, file names and metadata formats depend on the tool/version. Use the GTID set determined by the tool itself at the backup point; do not infer it from timestamps or file sizes.

## 14. Backup workflow for replication

An auditable workflow should include these steps:

1. **Define the goal.** Will the backup be used to build a full-instance replica, migrate a database, or create a copy for testing?
2. **Select the data scope.** Document the exact databases/tables included in the backup and accompanying objects.
3. **Choose the snapshot method.** Use a snapshot appropriate for the storage engine; coordinate DDL and record the point of consistency.
4. **Record GTID metadata.** Save the GTID set determined by the backup tool at the same logical point as the snapshot.
5. **Protect the binlog chain.** Retain binary logs from the backup point until every replica needing them has caught up; archive logs if source retention is insufficient.
6. **Test restore.** Restore into an isolated environment, verify data and GTID sets.
7. **Configure auto-position.** Enable replication only after confirming the GTID set accurately reflects transactions included in the backup.
8. **Monitor post-restore.** Check the applier, replication errors, lag, and representative business data.

If backups are taken daily but a new replica takes multiple days to restore and catch up, source retention must be long enough to keep logs from the backup point until the replica finishes reading them. Otherwise, binlogs must be archived to durable storage.

## 15. Common errors with backups and GTIDs

| Symptom | Possible cause | Verification and remediation |
|---|---|---|
| Restore fails when setting `GTID_PURGED` | Target already has GTIDs or the new set violates assignment rules | Check `gtid_executed`, `gtid_purged`, overlap, and version. Prepare a clean instance if provisioning a new replica. |
| Replica reports needing purged GTIDs | Backup is too old relative to source binlog retention | Compare missing GTIDs against `gtid_purged`; use a newer backup or complete archived logs. |
| Replica misses transactions for a database | Dump contained partial data while GTID set marked the entire source as executed | Check `--set-gtid-purged`; do not use ON for partial dumps when provisioning a full-source replica. |
| Duplicate data when replication starts | Backup GTIDs were not recorded or import generated unintended new GTIDs | Inspect the top of the dump file, `SQL_LOG_BIN`, `gtid_executed`, and restore procedure. |
| Replica skips some changes | GTIDs were marked executed even though corresponding data was absent from the backup | Do not manually patch GTID sets; rebuild from a consistent, properly scoped backup. |
| Backup GTID set is ahead of data state | GTID captured at a different time than snapshot or non-atomic dump | Audit snapshot procedure, concurrent DDL, and GTID metadata source. |
| Server cannot supply GTIDs to an old replica | Binlogs expired or were manually purged | Check `SHOW BINARY LOGS`, `gtid_purged`, replica lag, and archives. |

## 16. Hands-on exercises

### Exercise 1: Reading the two GTID sets

Given:

```text
gtid_executed = uuid-A:1-900
gtid_purged   = uuid-A:1-600
```

Answer:

1. Which GTIDs remain in the binary logs, assuming only this UUID and no gaps?
2. Which set is missing on a replica with `uuid-A:1-750`?
3. Can a replica with `uuid-A:1-500` catch up solely from the current binlogs?

Use `GTID_SUBTRACT()` to compute the missing portion and explain why the source can or cannot send them.

### Exercise 2: Checking the impact of a partial dump

The source has databases `sales` and `payroll`, with GTID transactions modifying both databases. Create two dump files: one `--all-databases` file and one dumping only `sales`. Compare the file headers when using `--set-gtid-purged=ON` versus `OFF`.

Explain why the GTID set of the `sales` dump can contain transactions from `payroll`, and why that causes missing data if the file is used to provision a full-source replica.

### Exercise 3: Provisioning a replica from backup

Create a full backup on a test source, save the GTID set at the backup point, restore onto a new instance, and configure `SOURCE_AUTO_POSITION=1`. Verify the GTID set before running `START REPLICA`, then confirm the replica catches up with transactions generated after the backup.

### Exercise 4: Handling a replica missing logs

Simulate a replica using a backup older than binlog retention. Observe the auto-position error when the source has already purged GTIDs the replica needs. Write a recovery procedure using a newer backup or archived binlogs, and explicitly explain why editing `gtid_purged` alone cannot recover data.

## 17. Checklist before using a backup to build a replica

- [ ] Backup contains the exact intended database/table scope.
- [ ] Snapshot method produces consistent data for the storage engine.
- [ ] GTID metadata was captured at the exact same logical point as the snapshot.
- [ ] Checked `gtid_executed` and `gtid_purged` on the source.
- [ ] If using `mysqldump`, carefully reviewed `--set-gtid-purged` and dump scope.
- [ ] Not using a source-wide GTID set on a partial dump to provision a full-source replica.
- [ ] Binary logs after the backup point are retained or archived until the replica catches up.
- [ ] Target server has a unique `server_uuid`.
- [ ] GTID state on the target was verified after restore.
- [ ] Auto-position enabled only after confirming matching data and GTIDs.
- [ ] Verified replication status and business data after starting.
- [ ] Regular restore tests and runbooks exist for premature source log purging.

`gtid_executed` indicates which transactions a server has executed; `gtid_purged` indicates which portion of that history is no longer in current binary logs. A backup used for replication must preserve the relationship between snapshot data and its corresponding GTID set. Capture metadata at the exact right point, retain the binlog chain long enough, and test auto-position after restore so the replica receives only the exact transactions absent from the backup.
