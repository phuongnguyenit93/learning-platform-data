# Physical Backup, MySQL Enterprise Backup, and Choosing Tools Based on Use Case

Physical backup creates copies of the data files and storage structures used by MySQL, such as InnoDB tablespaces, redo logs, undo tablespaces, and related files. This approach fits large databases because it avoids converting every row into SQL statements and reloading them; during recovery, the tool brings the files to a consistent state so MySQL can reopen them.

However, copying data files while MySQL is running does not automatically produce a valid backup. During copying, InnoDB may flush data pages, generate redo logs, extend tablespaces, or alter metadata. An online physical backup must coordinate file reads, change tracking, and redo log application so data pages align with a single recovery point. MySQL Enterprise Backup and Percona XtraBackup are two common choices for this kind of job; storage-layer snapshots and cold copies taken after stopping MySQL can also be appropriate under certain conditions.

Tool selection should be based on MySQL version, storage engines, data scale, acceptable downtime, RPO/RTO requirements, licensing, operational skills, and restore testability. The goal of this lesson is to help operators understand those criteria and build a recoverable backup workflow.

## 1. What Does a Physical Backup Store?

A physical backup typically contains the data files and metadata needed to rebuild an instance. The exact scope depends on the tool, server configuration, and storage layout:

- InnoDB tablespace files, including the system tablespace, file-per-table tablespaces, and tablespaces configured in custom locations.
- Redo logs and the information needed to bring data pages to a consistent state.
- Undo tablespaces and related system files according to the MySQL version's layout.
- Metadata covering version, LSN, backup configuration, file lists, and information needed for the prepare/restore step.
- Data for other storage engines if the backup tool and method support them consistently.

Do not assume all data resides under a single `datadir`. An instance may use separate paths for tablespaces, redo/undo logs, binary logs, relay logs, keyrings, or configuration files. Before backing up, inventory file locations and clearly determine whether the tool includes each area or if supplemental backups are required.

Physical backups are usually tightly coupled to file formats and MySQL versions. Cross-version restore capability depends on the compatibility matrix of the tool and MySQL; never treat physical backup files as a version-independent interchange format. Record the server version, tool version, plugins, components, and configuration at backup time.

### Physical Backup vs. Logical Backup

| Criterion | Physical Backup | Logical Backup |
|---|---|---|
| Content | Data files and storage metadata | Schemas and data exported as statements or logical format |
| Speed with large databases | Usually faster via block-level file copy/restore | Can be slower due to reading, converting, and executing per object or row |
| Flexibility | Depends on compatible version, architecture, and tool | Easier to migrate or filter schemas/tables |
| Recovery | Prepare files, apply redo logs, then start MySQL | Recreate schemas and reload data with the corresponding tool |
| Typical scope | Large instance recovery, fast recovery, creating physical replicas | Data migration, partial export, inspection, or format-independent archiving |

Both backup types complement each other. A critical system may use physical backups for fast instance recovery, binary logs for point-in-time recovery, and logical exports for migration or partial recovery needs. Do not expect a single physical backup to solve every table- or schema-level recovery scenario on its own.

## 2. Conditions for a Consistent Physical Copy

InnoDB uses write-ahead logging. When data changes, redo logs record the information required for recovery; data pages may be written to data files at a different time. Therefore, during an online backup, copied pages can reflect different points in time. The backup tool must record the LSN checkpoint and capture enough redo to bring the backup to a consistent state.

An online physical workflow generally consists of these high-level steps:

1. Initialize the backup session and record metadata, LSN checkpoint, or equivalent information.
2. Copy data files while the application continues reading/writing within the tool's constraints.
3. Capture redo logs generated during the copy so changes needed for consistency are not lost.
4. Finalize the backup and store metadata on files, versions, log positions, and job status.
5. During restore, run the prepare/apply-log step to apply redo and bring files to a state MySQL can open.

This is why you should never run `cp -r` on an active `datadir` and treat the result as a hot backup. Copying can miss pages, redo, or new files; MySQL may also be altering file structures mid-copy.

### Three Common Physical Approaches

| Approach | How It Works | Advantages | Key Limitations |
|---|---|---|---|
| Cold backup | Cleanly shut down MySQL, then copy all required files | Easy to understand; no concurrent writes during copy | Requires sufficient downtime; must inventory all files outside `datadir` |
| Tool-based hot backup | Specialized tool copies files and tracks redo while the server runs | Minimizes downtime; fits large databases | Requires compatible tool version, proper privileges, and prepare/restore workflow |
| Storage snapshot | Takes snapshots at the filesystem, volume, or storage array layer via a consistent procedure | Creates quick capture points, useful when storage supports efficient snapshots | Must synchronize multiple volumes and coordinate with MySQL; standalone snapshots may only be crash-consistent |

For cold backups, cleanly shut down MySQL and wait for shutdown to finish before copying. Include tablespaces in custom paths and any files required to decrypt data. During restore, verify file ownership and configuration matching the target instance.

For hot backups, use the APIs or mechanisms supported by the tool. If orchestrating snapshots yourself, understand backup locks and your MySQL version's requirements. `LOCK INSTANCE FOR BACKUP` can block certain DDL operations or file modifications while allowing DML per MySQL rules; it does not copy data itself and does not replace a consistent snapshot procedure. Exact syntax, the `BACKUP_ADMIN` privilege, and limitations must be checked for the running version.

For snapshots, if data, redo, and binary logs sit on separate volumes, snapshots must represent the same consistent point. Coordinate flushes/locks according to MySQL and storage vendor guidance. Snapshots can be created very quickly, yet they remain in the same failure domain if sharing the same device, cloud account, or storage zone as the primary server. Replicate snapshots to an independent failure domain and test restores.

## 3. MySQL Enterprise Backup

MySQL Enterprise Backup (MEB) is the commercial physical backup tool in Oracle's MySQL Enterprise ecosystem. It is designed to back up and restore MySQL, especially useful when an organization needs Oracle commercial support, online backup workflows, incremental backups, or accompanying enterprise features.

MEB uses the `mysqlbackup` command-line program. Depending on version, licensing, and configuration, the tool supports capabilities such as:

- Full backups and incremental backups based on changes since a prior backup checkpoint.
- Backing up an entire instance or selecting a data scope as supported.
- Hot backups for InnoDB with redo log collection to ensure consistency.
- Backup compression and encryption using options supported by the version.
- Streaming or writing backups to storage types supported by the tool version and configuration.
- Verifying, preparing, and restoring backups using the tool's dedicated operations.

Not every feature has identical syntax or prerequisites across all versions. Before deployment, check the MEB version against your MySQL Server version, OS, storage engines, and active plugins. Verify license requirements, backup account privileges, temporary disk space, bandwidth, and backup destination.

### Example: Creating a Full Backup

Illustrative example on Linux, assuming MySQL configuration is read from `/etc/my.cnf` and the backup directory has been created with proper permissions:

```bash
mysqlbackup \
  --defaults-file=/etc/my.cnf \
  --user=backup_user \
  --password \
  --backup-dir=/backup/mysql/full-2026-11-19 \
  backup
```

`--password` prompts for the password interactively in environments supporting that invocation. Never store real passwords in scripts, shell history, or logs. In automated operations, use a secret management mechanism and authentication method supported by the tool version.

The backup account must have the exact privileges required by the MEB version. Create a dedicated account, grant only the minimum privileges documented for that version, and restrict the source host. Never default to using `root` or an application account to run backups.

### Incremental Backups and Backup Chains

An incremental backup saves only changes identified by the tool since a previous backup checkpoint. This reduces storage size and transfer time per run, but increases recovery complexity: you must have the base full backup and every required incremental backup in exact order.

An operational schedule might be a periodic full backup followed by multiple incremental backups between fulls. This is only an organizational pattern; actual frequency must be based on RPO, rate of data change, backup windows, storage capacity, and measured restore duration.

When running incrementals with MEB, use the tool's metadata/history to pick the right base checkpoint, store each incremental in its own directory, and keep the entire dependency chain intact. Do not infer checkpoints from directory names or timestamps alone. Syntax for choosing an incremental base and applying parts varies by MEB version; follow the exact guide for the installed version.

### Preparing and Restoring with MEB

A general restore workflow includes:

1. Select the full backup and all incremental backups needed for the recovery point.
2. Prepare a target host with compatible MySQL and MEB versions; stop `mysqld` before replacing data.
3. Ensure the target data directory is empty or safely moved aside; identify the exact `datadir` and any custom tablespace paths.
4. Run prepare/apply-log and copy-back operations in the order required by MEB.
5. Restore file ownership, configuration, keyrings, and required plugins.
6. Start MySQL and inspect the error log, InnoDB status, data, and access privileges.
7. If point-in-time recovery (PITR) is needed, apply binary logs after the backup checkpoint up to the desired time.

Example `copy-back-and-apply-log` operation for a simple full backup:

```bash
mysqlbackup \
  --defaults-file=/etc/my.cnf \
  --backup-dir=/backup/mysql/full-2026-11-19 \
  copy-back-and-apply-log
```

This is a workflow example, not a command that can run as-is on every host. `datadir` settings, backup paths, incremental handling, and restore options must match the actual environment. Stop MySQL and verify target directories before `copy-back` to avoid overwriting data by mistake. Read MEB logs and confirm the operation succeeded before starting the server.

## 4. Percona XtraBackup

Percona XtraBackup is a popular physical backup tool in the Percona ecosystem. It is often evaluated when organizations want an open-source tool for InnoDB hot backups and have the operational capability to run it or use appropriate support services.

XtraBackup supports version-specific full/incremental backup, prepare, and copy-back workflows. The tool reads data files and collects redo logs to produce consistent backups for the MySQL versions it supports. Support scope changes across XtraBackup versions; check the compatibility matrix before upgrading MySQL or the tool. Do not assume the latest XtraBackup supports every older MySQL version, or vice versa.

Example full backup:

```bash
xtrabackup \
  --backup \
  --target-dir=/backup/mysql/full-2026-11-19 \
  --user=backup_user \
  --password
```

After the backup, run the prepare step to apply redo logs and finalize the backup. Example:

```bash
xtrabackup \
  --prepare \
  --target-dir=/backup/mysql/full-2026-11-19
```

When restoring, stop MySQL, ensure the target `datadir` has been handled safely, and run copy-back:

```bash
xtrabackup \
  --copy-back \
  --target-dir=/backup/mysql/full-2026-11-19
```

After copy-back, inspect and adjust file ownership to match the OS account running MySQL, for example:

```bash
chown -R mysql:mysql /var/lib/mysql
```

The path `/var/lib/mysql` and user/group `mysql` are examples; substitute actual values. If using incremental backups, you must prepare the full backup and apply each incremental in exact order using the options for your XtraBackup version. Never start MySQL with an incompletely applied incremental chain.

XtraBackup may need special handling for non-InnoDB tables or storage engines. For those objects, locking and consistency depend on the engine, version, and backup options. Inspect logs to see what the tool backed up, which tables required locks, or what supplemental steps are needed. A backup command returning success does not mean every data type in the instance was protected at the exact same consistency level.

## 5. Filesystem- or Storage-Layer Snapshots

Snapshots capture an image of a volume or filesystem at a point in time. This is a strong option when the storage platform provides efficient snapshots, supports rapid cloning, or needs multiple test environment copies. However, snapshot consistency depends on coordination with MySQL.

Distinguish two levels:

- **Crash-consistent:** the snapshot resembles the volume state after a sudden power loss. InnoDB can use redo logs for crash recovery on startup, provided all necessary files belong to one consistent capture point.
- **Application-consistent:** the snapshot is coordinated with MySQL to restrict file/metadata changes during capture and record required state. The guarantee depends on workflow, backup locks, flushes, and the storage platform.

A snapshot workflow might include the following steps, adjusted to specific MySQL and storage guidance:

1. Identify all volumes containing `datadir`, custom tablespaces, and required related files.
2. Confirm capacity, snapshot creation time, and simultaneous multi-volume snapshot capability of the platform.
3. Coordinate with MySQL using backup lock/flush mechanisms suited to the version; never arbitrarily lock tables or pause writes without understanding the impact.
4. Create consistent snapshots across all relevant volumes, recording the timestamp, GTID, or appropriate binary log coordinates.
5. Release locks immediately once the snapshot completes per procedure.
6. Create an independent copy from the snapshot, inspect metadata, and perform a test restore.

If volumes are snapshotted at skewed times, data files may not match redo logs or metadata. If you snapshot only the data volume while missing external tablespaces or keyrings, the restored database may fail to open. Nor is a snapshot an independent backup if the snapshot and source data share the same device, administrative account, or failure domain.

## 6. Comparing and Choosing Tools Based on Use Case

| Option | When to Consider | Points to Evaluate |
|---|---|---|
| MySQL Enterprise Backup | Organization uses MySQL Enterprise, needs Oracle tooling and corresponding commercial support | Cost/licensing, version support, backup privileges, restore features, integration with existing workflows |
| Percona XtraBackup | Organization wants an open-source tool, has operational capability and a supported version | Compatibility matrix, engine types, MySQL features in use, Percona or community support |
| Cold filesystem copy | Small database or environment able to stop MySQL during a maintenance window | Downtime duration, full file inventory, clean shutdown and restore procedure |
| Storage snapshot | Infrastructure has reliable snapshots, needs rapid copies or environment cloning | Application consistency, multi-volume coordination, export to independent failure domain, snapshot retention cost |
| Logical dump | Needs cross-version/architecture migration, partial schema/table export, or logical format storage | Export/import duration, size, charsets, routines/events/triggers, and dump consistency |

A simple decision tree can be used:

```text
Need online backup for a large InnoDB database?
  ├─ Yes
  │   ├─ Need Oracle MySQL Enterprise and corresponding support?
  │   │    └─ Yes -> Evaluate MySQL Enterprise Backup
  │   └─ No -> Check whether XtraBackup supports exact version/features
  │
  └─ No
      ├─ Have a long enough MySQL shutdown window?
      │    └─ Yes -> Consider cold backup with clean shutdown
      └─ Storage has verified consistent snapshots?
           └─ Yes -> Consider snapshots, with independent copies and restore tests
```

Several selection principles:

- Choose based on the running MySQL version, not merely the latest tool version. Check plugins, components, encryption, custom tablespaces, and non-InnoDB engines.
- If RTO is low and data is large, measure actual full backup, incremental, prepare, copy-back, and startup times. Short backup creation time does not guarantee short recovery time.
- If Oracle support is required, verify MySQL Enterprise Backup entitlement and support contract scope.
- If using XtraBackup, define who tracks compatibility, upgrades, backup failures, and recovery workflows.
- If using snapshots, verify cross-volume consistency and the workflow to export snapshots to independent storage.
- If single-table recovery or selective migration is needed, combine logical exports or a temporary restore workflow followed by exporting the required objects.

MySQL Clone Plugin can be useful for provisioning an instance from another source in supported scenarios, but cloning should not be treated as a long-term backup system. Clone serves provisioning/replication; it does not provide retention policies, off-site/immutable copies, or historical recovery like a backup system.

## 7. Combining Physical Backups with Binary Logs for PITR

A physical backup restores a baseline point. Binary logs record changes occurring afterward. Combining them enables recovery to a specific point in time, such as right before an accidental `DELETE` statement executed.

General point-in-time recovery (PITR) workflow:

1. Restore the most recent usable full backup.
2. Apply relevant incremental backups if the schedule uses incrementals.
3. Identify the log position or GTID represented by the backup.
4. Gather continuous binary logs from that point up to the target recovery time.
5. Use `mysqlbinlog` to read and replay logs in order, stopping right before the erroneous transaction or at the target timestamp.
6. Verify data and application on the recovery instance before shifting traffic.

Example of inspecting binary log contents:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000123
```

Example of replaying logs over a time window onto a recovery instance:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 08:00:00" \
  --stop-datetime="2026-11-19 08:25:00" \
  mysql-bin.000123 mysql-bin.000124 \
  | mysql --user=recovery_user --password
```

The timestamps above are only examples. Verify time zones, file ordering, exact start positions, and stop points. Stopping by timestamp may lack precision if multiple transactions occur close together; for data incidents, read the logs and identify the exact transaction/position/GTID before replaying. Never run a recovery pipeline against production serving live traffic.

For PITR to work, binary logging must be enabled and retained long enough. Continuously ship logs to independent storage, verify file continuity, and protect them from deletion alongside the host. Record the GTID set or binary log coordinates at the backup checkpoint as provided by the tool. If backing up from a replica, record replication state and corresponding source coordinates; do not rely solely on displayed lag metrics.

## 8. Protecting Backups and Managing Lifecycle

Backups contain real organizational data, including customer details, business records, and potentially credentials in system tables. Apply security controls equal to or stricter than production data.

- **Encryption at rest:** use the tool's encryption features or storage-layer encryption. Protect encryption keys separately from backup storage; never leave the sole key in the same failure domain as the backup.
- **Access control:** backup writer accounts should hold only necessary permissions; restore accounts and backup readers are controlled separately. Audit access and deletion actions.
- **Independent copies:** keep at least one copy in a separate failure domain, such as another storage account or geographic region per organizational policy.
- **Immutable/retention lock:** consider write-once/delete-protected storage for a defined period to reduce ransomware or accidental deletion risk.
- **Integrity checks:** verify hashes, sizes, metadata, tool logs, and backup readability after transfer.
- **Key management:** keep keyrings, tablespace decryption keys, and required configs in a controlled secret vault. If keys are lost, encrypted backups may be unrecoverable.
- **Configuration protection:** save MySQL configs, plugins/components, certificates, and environment details needed for restore; strip or protect secrets via a separate workflow.

Design retention around recovery goals. For example, retain multiple periodic full backups, incrementals between fulls, and continuous binary logs across the PITR window. When deleting a full backup, evaluate any incrementals that depend on it. Never delete logs needed for PITR just because a newer full backup exists if recovery to points within that interval is still required.

## 9. Recovery Testing Workflow

A backup is only trustworthy when it can be restored under conditions close to reality. A test procedure should run on an isolated host with sufficient capacity and no accidental connections to production.

### Practical Steps

1. Pick a full backup and related incrementals from the archive; verify checksums and metadata.
2. Prepare a recovery host with compatible MySQL, plugins, and tooling. Grant access to decryption keys and required configs.
3. Stop MySQL on the target host; prepare a clean `datadir` and matching tablespace paths.
4. Run prepare/apply-log per the tool; inspect logs and exit codes.
5. Copy-back or mount snapshots per workflow; restore ownership, permissions, and configuration.
6. Start MySQL on an isolated network. Inspect the error log, InnoDB status, plugins, tablespaces, and replication metadata.
7. If PITR is required, replay binary logs to the selected checkpoint.
8. Verify row counts, business totals, foreign keys, sample records, users/grants, and critical queries.
9. Measure completion time and note manual steps, errors, disk usage, and the timestamp of the latest recovered data.
10. Tear down or secure the test environment per policy to avoid leaving uncontrolled copies of sensitive data around.

Testing must confirm at least three things: the backup is readable; MySQL starts and serves queries; data matches the expected recovery point. File checksum verification alone only confirms files have not changed unexpectedly—it does not prove the backup can boot into a valid database.

### RPO and RTO

- **RPO (Recovery Point Objective):** maximum data loss an organization tolerates, typically measured from the last recoverable transaction to the incident time.
- **RTO (Recovery Time Objective):** maximum time an organization tolerates to bring the service back online.

Full/incremental schedules and binary log shipping frequency affect RPO. Data size, storage read/write speed, bandwidth, number of incrementals to apply, prepare duration, and application verification affect RTO. Measure via restore drills rather than estimating solely from backup speed.

## 10. Tool Selection Scenarios

A retail system runs MySQL 8.x with rapidly growing InnoDB data, operates continuously, and operations must recover a large instance quickly. The organization already uses MySQL Enterprise and has Oracle support agreements.

In this case, MEB is the logical candidate to evaluate first because it aligns with the existing ecosystem and support model. The team should test full backups, incrementals, encryption, off-host shipping, and restores on production-equivalent hardware. If MEB does not fit budget or technical needs, the team can evaluate XtraBackup after confirming exact support for the running MySQL version, engines, and features.

Another system may run MySQL on a storage array supporting consistent multi-volume snapshots. The team can use snapshots for fast capture points, but must prove the snapshot covers both data and redo logs, coordinates with MySQL, replicates snapshots independently, and passes restore tests. If consistency cannot be proven, snapshots should not be the sole protection mechanism.

For a small staging environment that can stop MySQL nightly, a cold backup after a clean shutdown can be simple and cost-effective. If a schema must be exported for migration to another version, a logical dump may fit better than a physical backup. Every choice must tie back to concrete recovery objectives and testability.

## 11. Pre-Production Checklist

- [ ] Defined RPO, RTO, retention, and required PITR checkpoints.
- [ ] Checked MySQL version, storage engines, plugins, components, and tool compatibility matrix.
- [ ] Inventoried `datadir`, external tablespaces, redo/undo, binary logs, keyrings, and required configuration files.
- [ ] Backup workflow ensures consistency; never arbitrarily copies a running `datadir`.
- [ ] Backup account follows least privilege and credentials are securely managed.
- [ ] Backups are encrypted, integrity-checked, and transferred to at least one independent failure domain.
- [ ] Full/incrementals are managed as dependency chains; binary logs are retained long enough for PITR.
- [ ] Alerts configured for failed backups, overdue runs, low disk space, or missing binary logs.
- [ ] Tested restore on an isolated host, including prepare/apply-log, copy-back, file permissions, and MySQL startup.
- [ ] Verified business data, access privileges, and actual restore duration.
- [ ] Tested encryption key loss, host replacement, and recovery in another failure domain.

A sound physical backup workflow must produce a consistent copy, retain all necessary metadata and keys, protect copies from source-host failures, and prove recoverability through periodic tests. Choosing MEB, XtraBackup, snapshots, or cold backups is a decision driven by version, features, downtime tolerance, support, and the RPO/RTO the system must meet.
