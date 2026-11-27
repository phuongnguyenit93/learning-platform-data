# Hot/Cold Backup, Required Locks, and File Set Consistency

A MySQL backup can only be restored reliably when the copy contains a consistent database state. For logical backups, consistency typically comes from a transaction snapshot. For physical backups, the tool must coordinate copying data files with redo logs and appropriate locking mechanisms. A cold backup achieves consistency by shutting down MySQL cleanly before copying the entire required file set.

This lesson belongs to the **Backup and Recovery** chapter of the `DATABASE_MYSQL` module. Along the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query tuning, privilege management, and operations—backup is how you protect the results of all that work. The focus here is choosing between hot and cold backups, understanding which locks are needed, and keeping all files aligned to a single recovery point.

## 1. Hot Backup and Cold Backup

A **hot backup** is performed while the MySQL server continues running and serving the application. Users can keep reading or writing data depending on the backup method. This minimizes service disruption, but requires a mechanism to hold a consistent snapshot or reconcile changes occurring during the copy.

A **cold backup** is performed after MySQL has cleanly shut down. Once no process is writing data, the files can be copied as a complete set. This is easy to reason about and less dependent on locks during copying, though it requires service downtime.

| Criterion | Hot Backup | Cold Backup |
|---|---|---|
| MySQL state | Running | Cleanly stopped |
| Service impact | Can continue serving; depends on locks and tool | Service must stop during backup |
| Consistency mechanism | Transaction snapshot, backup lock, global read lock, or physical tool handling redo | Clean shutdown followed by copying the full file set |
| Best suited for | Systems requiring high availability | Systems with maintenance windows or needing simple physical copies |
| Primary risk | Concurrent DDL or writes breaking snapshot consistency if the wrong mechanism is chosen | Missing files, restarting before copy finishes, or unclean shutdown |

Hot/cold describes the server's state during backup. Logical/physical describes how the copy is represented. Therefore, you can take a logical hot backup with `mysqldump`, a physical hot backup with a tool such as Percona XtraBackup or MySQL Enterprise Backup, and a physical cold backup by copying `datadir` after MySQL cleanly shuts down.

## 2. Logical Hot Backup with `mysqldump`

For InnoDB tables, `mysqldump --single-transaction` creates a transaction snapshot so data-reading queries see the same consistent state. MySQL can continue accepting DML during the dump. The `--quick` option streams rows rather than buffering the entire result set in memory.

Example of backing up a database:

~~~bash
mysqldump \
  --user=backup_user \
  --password \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --databases appdb \
  > appdb.sql
~~~

When run, the client prompts interactively for the password. Never write passwords directly in commands or expose them in scripts, logs, or shell history. In automated environments, use a credential management mechanism protected per system policy.

The options have the following meanings:

- `--single-transaction`: creates a consistent snapshot for transactional tables such as InnoDB. It does not make MyISAM or non-transactional engines consistent.
- `--quick`: streams data instead of buffering the entire result set in client memory.
- `--routines` and `--events`: include stored procedures/functions and events in the dump.
- `--triggers`: requests triggers be included in the dump; triggers are normally dumped by default, though writing it explicitly makes intent easier to read.
- `--hex-blob`: represents binary data in hex format inside the SQL dump.
- `--databases appdb`: dumps the specified database, including statements to create and select the database on import.

### Limitations of Transaction Snapshots

`--single-transaction` relies on InnoDB MVCC. During the dump, avoid running DDL on tables being backed up. Operations such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` can cause the dump to error or leave output no longer meeting snapshot expectations.

If the database contains MyISAM or non-transactional tables, the InnoDB snapshot does not protect those tables. Choose one of these approaches:

- Stop writes to non-transactional tables for the duration of the backup.
- Use an appropriate read lock, such as `--lock-all-tables`, if write locking during the dump is acceptable.
- Convert tables requiring consistency to InnoDB after evaluating application characteristics.
- Use a backup tool that supports the active engines and consistency model.

`--single-transaction` and `--lock-all-tables` are two distinct protection approaches and are incompatible when combined in `mysqldump`. Pick the option suited to your storage engines and acceptable lock level.

## 3. Types of Locks Related to Backups

Which lock is required depends on the storage engine, backup method, and consistency goal. Three common mechanisms are transaction snapshots, backup locks, and global read locks.

### Transaction Snapshot

For InnoDB, a transaction at the appropriate isolation level can read data at a consistent snapshot without locking entire tables to block DML. `mysqldump --single-transaction` uses this approach.

The snapshot protects the transaction's view of data; it does not freeze schema definitions. Therefore, avoid DDL affecting tables during the dump. Nor does it protect data in non-transactional engines.

### Backup Lock: `LOCK INSTANCE FOR BACKUP`

MySQL 8.0.3 and later provide an instance-level backup lock:

~~~sql
LOCK INSTANCE FOR BACKUP;

-- Backup tool executes the work requiring protection.

UNLOCK INSTANCE;
~~~

The account needs the `BACKUP_ADMIN` privilege to use this mechanism. You can grant the privilege to the backup account at an appropriate administrative scope:

~~~sql
GRANT BACKUP_ADMIN ON *.* TO 'backup_user'@'localhost';
~~~

A backup lock is designed to block operations that could alter structures or files needed by a physical backup, such as certain DDL and tablespace management operations. It allows DML to proceed in cases supported by MySQL. Therefore, it is not a global read lock, nor does it produce a consistent physical copy on its own.

A physical backup tool must still track and apply redo logs to bring copied data pages to a consistent state. Use a tool version compatible with your MySQL version and follow the lock, copy, and prepare sequence defined by the tool. Never replace that workflow with manual file copying.

### Global Read Lock: `FLUSH TABLES WITH READ LOCK`

The following statement acquires a global read lock:

~~~sql
FLUSH TABLES WITH READ LOCK;

-- Execute the operation requiring a global consistency point.

UNLOCK TABLES;
~~~

This statement flushes and locks tables to block write operations while the lock is held. It broadly impacts server write activity, so do not hold it throughout a lengthy physical copy when a fast storage snapshot is available.

A common pattern is to acquire the lock, take a storage snapshot at a consistent point in time, record the binary log position or GTID if needed, and release the lock immediately. Snapshot creation must be supported by the storage layer and must cover all volumes holding relevant data.

A global read lock is useful when synchronizing state across multiple engines or recording replication/binlog coordinates. However, it suspends write availability while held. Schedule it, measure lock duration, and monitor application impact before applying on a production system.

### Quick Comparison

| Mechanism | Blocks DML? | Blocks File-Altering DDL? | Usage Scope |
|---|---|---|---|
| InnoDB transaction snapshot | Does not globally lock DML | Does not block DDL on its own | Consistent logical dumps of InnoDB |
| `LOCK INSTANCE FOR BACKUP` | Generally allows DML | Yes, for operations specified by MySQL | Physical backup tools on supported versions |
| `FLUSH TABLES WITH READ LOCK` | Yes, globally | Yes, while the lock is held | Global snapshots, binlog coordinates, and engines needing locks |

No single locking statement fits every backup type. Choose based on storage engines, backup tooling, RPO/RTO requirements, and acceptable disruption.

## 4. Physical Hot Backup and the Role of Redo Logs

A physical backup copies data files in MySQL/InnoDB format. Tools like Percona XtraBackup or MySQL Enterprise Backup can read files while the server stays running. During copying, InnoDB can modify data pages and write redo logs. Consequently, a freshly copied set of files is not necessarily self-consistent the moment copying finishes.

A physical hot backup workflow typically follows these steps:

1. Initialize the backup session and apply required locks to protect metadata/files per tool requirements.
2. Copy data files while capturing generated redo logs.
3. Finish the copy phase and save backup checkpoint information, such as GTIDs or binary log positions where supported by the tool.
4. Run the **prepare** step to apply required redo logs, recovering data pages to a consistent state.
5. Verify the backup result and only then use it as a restore source.

Example prepare step with Percona XtraBackup:

~~~bash
xtrabackup --prepare --target-dir=/backup/mysql/full
~~~

The path is only an example; use the exact command and options for the deployed XtraBackup version. A backup directory that has not gone through the prepare step may not yet be ready to restore. Never skip this step merely because all files appear present.

Redo logs contain the information needed to recover InnoDB changes. The physical backup tool tracks redo during copying and uses it to reconcile timing differences across copied pages. Never delete, replace, or omit redo logs manually.

## 5. Cold Physical Backup: Clean Shutdown Then Copy

A cold physical backup is a straightforward choice when a system has a maintenance window. Basic workflow:

1. Announce maintenance and switch the application to maintenance mode; stop jobs that could write to the database.
2. Stop MySQL using the service manager or a supported shutdown command.
3. Verify the MySQL process has exited and shutdown completed normally.
4. Copy the entire `datadir` along with files located outside `datadir` that belong to the dataset needed for recovery.
5. Preserve file ownership, permissions, symbolic links, and file metadata as required by the OS.
6. Record the MySQL version, relevant configuration, plugins, keyrings, and binary log/GTID positions if point-in-time recovery is needed.
7. Verify the copy completed before restarting MySQL and reopening the application.

With a cold backup, there is no need to hold `LOCK INSTANCE FOR BACKUP` or `FLUSH TABLES WITH READ LOCK` during copying because MySQL is stopped. The critical conditions are a clean shutdown and copying the complete file set.

Never copy part of `datadir` assuming you can merge it with files from another backup run. Nor should you start MySQL while the copy process is still reading source files; if the server resumes writing, the copy may hold files from different points in time.

## 6. File Set Consistency

A physical backup is not merely a collection of files with matching names. The files must collectively describe a single recoverable database state. MySQL may use several file types depending on configuration and enabled features:

- **System tablespace:** holds InnoDB's internal data structures. Where the data dictionary is stored depends on version; in MySQL 8.0, dictionary data is stored in dedicated files/tablespaces, including `mysql.ibd`.
- **Per-table tablespace files:** typically `.ibd` files when file-per-table is configured.
- **Undo tablespaces:** store information for rollback and MVCC; locations may depend on configuration and version.
- **Redo logs:** support crash recovery and complete necessary changes.
- **Binary logs:** needed for point-in-time recovery or replaying event sequences after a full backup.
- **Relay logs and replication metadata:** may be needed to resume or diagnose replica state.
- **Tablespaces outside `datadir`, keyrings, and encryption components:** must be protected alongside the copy if used by the database.

The exact list depends on MySQL version, engines, configuration, and backup tool. Rely on documentation for your running version to pinpoint the exact files and metadata to retain.

### Why Can You Not Mix Files from Different Times?

Suppose a table has its own tablespace and InnoDB is updating data:

- The tablespace file is copied at 10:00.
- The redo log is skipped or taken from another copy at 10:05.
- Metadata or the system tablespace is copied at 10:10.

The three components may no longer describe the same state. MySQL may fail to start, fail to complete crash recovery, or expose inconsistent data.

With a physical hot backup, the tool solves this by capturing redo logs and preparing the file set. With a cold backup, shutting down MySQL cleanly before copying keeps source files stable throughout the copy. With storage snapshots, consistent snapshots across all relevant volumes at the exact same point in time are required; standalone snapshots taken at skewed times may not suffice.

### Common Mistakes

| Mistake | Possible Consequence | Prevention |
|---|---|---|
| Copying `datadir` with an ordinary copy command while MySQL is running | Files captured at different points in time, missing required redo | Use an InnoDB-aware physical backup tool or cleanly stop MySQL before copying |
| Copying only `.ibd` files | Missing metadata, system tablespace, undo, or redo | Back up the complete file set per tool instructions |
| Omitting redo logs from a physical hot backup | Cannot prepare or recover to a valid state | Let the tool track and capture redo logs |
| Copying `datadir` while skipping external tablespaces | Missing tables or tablespaces on restore | Inventory data paths and snapshot all relevant volumes |
| Using a different keyring file or missing keyring | Cannot decrypt encrypted data | Back up and test secure keyring recovery procedures |
| Dumping InnoDB via snapshot with concurrent DDL | Dump may fail or lose desired consistency | Pause DDL during the dump window |
| Using `--single-transaction` for MyISAM without locks | Tables may reflect different points in time | Read-lock or pause writes for non-transactional engines |
| Only checking that files exist | Backup may fail to restore | Perform test restores on an independent host and verify data |

## 7. Combining Full Backups with Binary Logs

A full backup provides the starting point for recovery. If you need to recover to a later point in time, retain binary logs continuously from the backup checkpoint. A typical point-in-time recovery workflow is:

1. Restore a verified full backup.
2. Identify the GTID or binary log position corresponding to the backup timestamp.
3. Replay binary log events from after that point up to before the stop time.
4. Inspect data and confirm the application behaves properly.

Do not use binary logs from an unrelated server or replication stream without verifying origin and sequence. If the backup tool records binlog/GTID coordinates, store that metadata alongside the backup. Protect binary logs and backups under the same appropriate retention, access control, and encryption policies.

## 8. Method Selection Guide

You can use the following table to decide on a backup approach:

| Condition | Typically Suitable Approach |
|---|---|
| All tables are InnoDB, readable dump and logical restore needed | `mysqldump --single-transaction --quick` |
| Need physical backup while service remains online | Physical backup tool supporting the MySQL version, redo handling, and backup locks |
| Has non-transactional tables and write locking is acceptable | Use appropriate read locks or pause writes during the dump |
| Have a long enough maintenance window | Cleanly shut down MySQL and copy the full physical file set |
| Need very fast storage snapshots | Coordinate locks/flushes, snapshot all volumes synchronously, and save recovery coordinates |
| Need recovery to a specific point in time | Full backup paired with continuous binary logs/GTIDs |

Before deployment, define RPO (maximum acceptable data loss) and RTO (maximum recovery time). Then select full/incremental frequencies, retention windows, copy storage locations, and restore-test schedules. A backup is only useful when its recovery point satisfies business requirements.

## 9. Verifying Backups Before Marking Complete

A backup command exiting without errors does not prove the data can be recovered. Verify:

- Tool exit code, logs, and error/warning messages.
- File sizes, file counts, checksums, and storage capacity.
- Backup metadata: MySQL version, timestamp, databases, GTID/binlog coordinates, options, and prepare status.
- Presence of files outside `datadir`, keyrings, or required encryption material.
- Restorability on a test instance of a compatible version.
- Row counts, table schemas, triggers, routines, events, access privileges, and critical business queries.
- Actual wall-clock time to complete the restore and bring the application back online.

Schedule periodic test restores in an isolated environment. Merely verifying checksums or opening a dump file does not replace an actual restore test.

## 10. Key Takeaways

- Hot backups keep the service running, but require snapshots or tools capable of handling concurrent changes.
- Cold backups require cleanly shutting down MySQL and copying the complete set of related files.
- `--single-transaction` fits InnoDB; it does not protect non-transactional tables and does not block DDL.
- `LOCK INSTANCE FOR BACKUP` protects structures/files against operations specified by MySQL; it does not freeze DML and does not replace redo processing.
- `FLUSH TABLES WITH READ LOCK` takes a global read lock, which can impact writes server-wide; minimize lock hold time.
- Physical hot backups must capture all files and redo logs, then be prepared before restoring.
- Never mix data files, redo logs, metadata, external tablespaces, or keyrings from incompatible points in time.
- A backup is only trustworthy after testing a restore and verifying the outcome.

Always determine engines, backup type, required locks, and the file inventory before running. Only when the file set reflects one recoverable state and the restore workflow has been tested does a backup hold real operational value.
