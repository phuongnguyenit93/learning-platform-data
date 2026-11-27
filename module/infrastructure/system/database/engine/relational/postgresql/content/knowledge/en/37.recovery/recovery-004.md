# Physical Recovery and Compatibility Requirements in PostgreSQL

**Physical recovery** is the process of returning a PostgreSQL cluster to an operational state using file/page-level copies along with WAL (Write-Ahead Log). This approach is commonly used to recover from host failures, storage loss, standby provisioning, data center failovers, or point-in-time recovery (PITR).

Physical recovery depends strictly on **the compatibility of the data directory, PostgreSQL binary, operating system/architecture, block size, WAL format, tablespaces, extension libraries, and WAL chain**. A backup containing all files yet started with an incompatible binary may still fail to start or cause severe errors.

Key points to remember:

- Physical backup is a copy of the **entire cluster**, not a tool to pick a single table or database like `pg_dump`.
- A base backup requires matching WAL to become a consistent, bootable copy.
- Physical restore normally requires the same PostgreSQL major version and compatible format parameters.
- The WAL archive must be continuous from the base backup to the target recovery point.
- Tablespaces, configs outside PGDATA, extension binaries, certificates, and secrets may reside outside the backup.
- A successful restore must be verified through recovery state, logs, query checks, and actual applications.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish physical backup, logical backup, base backup, WAL archive, and snapshot.
2. Explain why a physical backup needs WAL to reach a consistent state.
3. Create a base backup using `pg_basebackup` and understand WAL/standby options.
4. Describe the proper filesystem-level backup procedure.
5. Restore a cluster from a physical backup and replay WAL.
6. Configure PITR using `restore_command`, `recovery.signal`, and recovery targets.
7. Build a standby from a base backup and monitor WAL receiver/replay.
8. Distinguish crash recovery, archive recovery, standby recovery, and promotion.
9. Determine compatibility requirements for major/minor versions, OS, CPU architecture, and PostgreSQL builds.
10. Inspect block size, WAL block size, WAL segment size, checksum version, and system identifier.
11. Handle tablespaces, external configuration, extension libraries, collations, and file permissions.
12. Understand timelines, timeline history, and branching risks after promotion.
13. Use `pg_verifybackup`, `pg_controldata`, `pg_checksums`, and appropriate system views.
14. Build runbooks for restore, validation, rollback, and disaster recovery.

## 2. What Is Physical Recovery?

### 2.1. Physical Backup Copies the Storage Layout

A PostgreSQL cluster consists of multiple databases, shared catalogs, WAL, control files, tablespaces, and relation files. A physical backup copies data at the storage layout level, preserving page formats, relation files, and required metadata.

For example, a data directory may contain:

~~~text
PGDATA/
  base/                 # database relation files
  global/               # shared cluster catalogs
  pg_wal/               # WAL segments
  pg_xact/              # transaction status
  pg_multixact/
  pg_tblspc/            # links to tablespaces
  pg_twophase/
  pg_control            # cluster control information
  PG_VERSION
  postgresql.conf       # if placed inside PGDATA
  pg_hba.conf           # if placed inside PGDATA
  pg_ident.conf         # if placed inside PGDATA
~~~

This is a conceptual diagram; exact contents/directories may vary by major version, build, configuration, and platform.

### 2.2. Physical Restore Recovers the Entire Cluster

When restoring a physical backup, PostgreSQL recovers the entire cluster as of the base backup time, and can then replay WAL to advance to a consistent state or a recovery target.

You cannot take a standard physical base backup and ask the server to open only the `sales` database while ignoring the rest of the cluster. To selectively back up/restore a database or table, use logical dump/restore or design a separate export/import process.

### 2.3. When Is Physical Recovery Used?

- Full cluster recovery after losing a volume or host;
- Provisioning a physical standby for high availability;
- Cloning a cluster for staging/test environments;
- Migrating a cluster to new storage;
- PITR recovery after accidental deletions/updates;
- Rebuilding a node after failover;
- Using consistent snapshots to create fast clones.

### 2.4. Physical Recovery Does Not Automatically Undo Business Mistakes

If a valid transaction accidentally deleted data and WAL recorded its commit, crash recovery will replay that transaction. To revert before the deletion, you must use PITR to a point prior to that transaction or restore logical data from another source.

### 2.5. Concepts to Distinguish

| Term | Meaning |
| --- | --- |
| Base backup | Underlying physical copy of the cluster over a backup time window |
| WAL archive | Sequence of WAL segments stored outside `pg_wal` for recovery |
| Crash recovery | Replaying internal WAL after a server crash |
| Archive recovery | Replaying WAL from an archive after restoring a base backup |
| PITR | Stopping recovery at a specific time/LSN/transaction target |
| Physical standby | A node recovering and continuously receiving/replaying WAL from a primary |
| Promotion | Transitioning a standby into a writable primary |
| Timeline | A WAL history branch created when a cluster initializes or is promoted |

## 3. Why Does a Physical Backup Need WAL?

### 3.1. Data Files Are Not Copied at a Single Instant

During a backup, applications can still write data. If file A is copied at 10:00:00, file B at 10:00:10, and file C at 10:00:30, the files may reflect different transaction states.

PostgreSQL uses WAL to bring the copy into a consistent state during recovery.

### 3.2. A Base Backup Spans a Time Window

A base backup has a start time and an end time. During this window, data pages can change. WAL records generated during and associated with the backup allow PostgreSQL to redo the necessary changes.

### 3.3. Consistent Backup

A physical base backup is only considered consistent when it has enough WAL to recover according to the backup mechanism used. You cannot simply copy `base/` and assume the cluster can start.

### 3.4. WAL Must Be Protected Alongside the Backup

If the base backup is intact yet required WAL is missing or corrupted, PostgreSQL may fail to complete recovery. Therefore, a backup policy must cover:

- Base backup;
- Continuous WAL archive;
- Timeline history files;
- Manifest/checksums if generated by the tool;
- Metadata on PostgreSQL version and configuration;
- Tested restore instructions.

### 3.5. Backup Consistency and Transaction Commits

Transactions running during the backup may commit or abort afterward. WAL recovery and transaction status allow PostgreSQL to determine the right state under MVCC/commit rules, rather than assuming all bytes were copied at the exact same instant.

## 4. Physical Backup vs. Logical Backup

| Criterion | Physical Backup | Logical Backup |
| --- | --- | --- |
| Copy level | Cluster pages/files | SQL objects and rows |
| Typical scope | Entire cluster | Can select database/schema/table |
| Major version dependency | High; physical format/WAL must be compatible | Can dump from older version and restore to newer per support |
| Restore speed | Often fast for large clusters on suitable storage | Can be slower due to SQL parsing/execution and index rebuilds |
| PITR | Combines base backup + WAL archive | Does not replace physical PITR; can replay separate business-level exports |
| Cross-platform migration | Constrained by binary/storage format | More flexible |
| System data/cluster roles | Physical backup preserves cluster metadata | `pg_dump` of a database does not include all cluster-wide roles/tablespaces |
| Selecting a single table | Not a normal use case | Possible |

### 4.1. Common Logical Tools

- `pg_dump`: dumps a single database;
- `pg_dumpall`: dumps the entire cluster as SQL, including globals as supported;
- `pg_restore`: restores custom/directory/tar archives from `pg_dump`;
- `psql`: executes plain SQL dumps.

### 4.2. They Do Not Replace Each Other

Physical backup fits disaster recovery and standbys. Logical backup fits migrations involving version/schema changes, selective restores, and exports/imports. Production systems often need both depending on RPO/RTO goals.

### 4.3. Using Physical Backup for Major Upgrades?

Do not copy PGDATA from an older major version and start it with a newer major version binary to upgrade. Use supported procedures such as `pg_upgrade`, logical dump/restore, or logical replication migration. Physical backups are still required for rollback/DR per separate procedures.

## 5. The pg_basebackup Tool

### 5.1. What Does pg_basebackup Do?

`pg_basebackup` connects to a PostgreSQL server with replication privileges and creates a physical base backup. It uses the replication protocol to copy data files/tablespaces and collect WAL according to the chosen method.

Advantages:

- Provides a consistent backup mechanism supported by PostgreSQL;
- Supports backing up from a primary and, under certain conditions, from a standby;
- Can stream WAL while copying;
- Can generate standby configuration with `-R`;
- Includes progress reporting and backup manifests in supported versions.

### 5.2. Replication Privileges

The backup role requires `REPLICATION` or superuser privilege per server configuration, and `pg_hba.conf` must allow replication connections from the backup host.

~~~sql
CREATE ROLE backup_user WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

This example only illustrates privileges. Never hard-code production passwords in shell history, scripts, source control, or command lines visible to process listings. Use `.pgpass`, service files, a secret manager, or an organization-approved authentication mechanism.

### 5.3. pg_hba.conf for Replication

Example of a rule restricting the backup client:

~~~conf
host  replication  backup_user  10.20.30.40/32  scram-sha-256
~~~

Replace the address with the actual IP/CIDR and use appropriate TLS/network policies. Never open replication access to the entire Internet.

### 5.4. Base Backup from Primary

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/pg/base-2026-11-14 \
  -Fp \
  -X stream \
  -P \
  --manifest-checksums=SHA256
~~~

Explanation:

- `-h`, `-p`, `-U`: connection server, port, and role;
- `-D`: backup destination; usually must not exist or must be empty per format requirements;
- `-Fp`: plain format, creating the directory/file layout directly;
- `-X stream`: streams WAL during the backup;
- `-P`: displays progress;
- `--manifest-checksums`: selects checksum algorithm for the backup manifest if supported by the version.

Check `pg_basebackup --help` for the exact major version before using options. Names and defaults of some flags change across versions.

### 5.5. WAL Methods

`pg_basebackup` has the following WAL handling methods (depending on version):

- `-X stream`: opens a second replication connection to stream WAL during backup;
- `-X fetch`: fetches required WAL from the server at the end of the backup;
- `-X none`: does not include WAL in the backup; use only when an external WAL/archive process guarantees consistency.

`stream` is typically suitable when you want the backup to be self-contained with required WAL and have enough connection slots. `fetch` may require the server to retain enough WAL until the end of the backup; if WAL is recycled before fetch, the backup can fail.

### 5.6. Number of WAL Sender Connections

When using `-X stream`, the backup requires one replication connection for the base backup and another connection to stream WAL. Account for `max_wal_senders`, connection capacity, and `max_replication_slots` if using a slot. Multiple concurrent backups can consume significant resources.

### 5.7. Creating a Backup for a Standby

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /var/lib/postgresql/standby \
  -Fp \
  -X stream \
  -P \
  -R
~~~

`-R` (write recovery configuration) creates `standby.signal` and writes corresponding connection settings into `postgresql.auto.conf` based on the options passed. When backing up from a standby source, check version-specific WAL method/slot restrictions; do not assume all options behave identically to backing up from a primary.

When the source is a standby, `pg_basebackup` has specific limitations: WAL streaming mode `-X stream` is not supported in many versions because it requires another replication connection. Use a WAL method supported by that version's documentation, typically `-X fetch` or separately managed archive/streaming; ensure the standby retains enough WAL until backup completion.

### 5.8. Do Not Use -R for Standalone PITR Restore

If you intend to recover into a standalone server at a target point, configure archive recovery appropriately and avoid accidentally starting the cluster in standby mode. `-R` is for standbys; `standby.signal` changes the startup mode.

### 5.9. Creating a Replication Slot

A slot can be used to retain WAL for a standby/backup consumer:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /var/lib/postgresql/standby \
  -Fp \
  -X stream \
  -C \
  -S standby_slot_01 \
  -R \
  -P
~~~

`-C` creates the slot prior to use; `-S` specifies the slot name. Verify version support and ensure the slot does not already exist. A replication slot can retain WAL indefinitely if the consumer stops; monitor disk space and `max_slot_wal_keep_size` per version.

### 5.10. Backup Compression

Backups can be created in formats/compression methods supported by the version. Plain format is easy to inspect at the file level but is not a compressed container. Tar/custom options and compression algorithms vary by version; consult `pg_basebackup --help`.

### 5.11. Tablespace Mapping

If tablespaces reside at different paths on the restore host, `pg_basebackup` provides a mapping option:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /restore/pgdata \
  -Fp \
  -X stream \
  -T /old/fastspace=/new/fastspace \
  -P
~~~

The mapping must match exact source and target tablespace paths. With multiple tablespaces, specify a mapping for each path. Never leave links in `pg_tblspc` pointing to nonexistent directories or unmounted volumes.

### 5.12. Check Backup Exit Status

Only treat a backup as successful when:

- `pg_basebackup` exits with code 0;
- Progress completes and the backup directory is fully created;
- A manifest exists if the version/format generates one;
- The WAL method completes;
- Logs contain no errors at completion;
- `pg_verifybackup` succeeds where applicable.

A directory that looks populated yet came from a failed command is still an unverified backup.

## 6. Filesystem-Level Backup and Storage Snapshots

### 6.1. Copying PGDATA While the Server Is Running Is Dangerous

Do not arbitrarily copy the PGDATA directory while PostgreSQL is running:

~~~bash
cp -a /var/lib/postgresql/data /backups/pgdata
~~~

Files can be copied at different points in time, dirty pages may not be flushed, WAL/data files may be out of sync, tablespace links may be missed, or WAL segments may be recycled mid-copy. The result can be inconsistent and unbootable.

### 6.2. Three Potentially Valid Ways to Create a Filesystem Backup

1. Cleanly stop PostgreSQL, then copy all cluster files and tablespaces;
2. Use PostgreSQL's backup API (`pg_backup_start`/`pg_backup_stop`) and ensure all files/WAL are copied;
3. Use a consistent storage snapshot per the storage provider's instructions, combined with backup mode and WAL archiving if required.

`pg_basebackup` is usually easier to manage for online base backups.

### 6.3. Cold Backup

A cold backup requires a clean shutdown:

~~~bash
pg_ctl -D /var/lib/postgresql/data stop -m fast
~~~

After confirming the server has completely stopped, copy:

- All of PGDATA;
- All external tablespaces;
- The WAL directory if located outside PGDATA;
- Configs/certs/keys located outside the data directory;
- Version/build/path metadata.

A cold copy preserves a consistent state because no backends are modifying files. Ensure no other PostgreSQL process is using the same data directory.

### 6.4. Modern Backup API

Current PostgreSQL versions provide SQL functions:

- `pg_backup_start(label, fast)` starts backup mode;
- `pg_backup_stop(wait_for_archive)` ends backup mode and returns backup metadata.

Conceptual sequence example:

~~~sql
SELECT pg_backup_start('nightly-base-2026-11-14', true);
-- tool snapshots/copies all of PGDATA and tablespaces
SELECT * FROM pg_backup_stop(wait_for_archive => true);
~~~

Do not run these two commands and skip copying files. The backup API only marks/coordinates backup state; the tool must still copy all files properly and save the metadata returned by the function (such as backup label/tablespace map per format). You must ensure required WAL is archived or saved alongside the backup.

### 6.5. Legacy Backup Functions

Older PostgreSQL versions used `pg_start_backup` and `pg_stop_backup`. Names, semantics, and privileges have changed across versions. When writing automation, use the functions recommended in the documentation for your current major version; do not copy old scripts without verifying.

### 6.6. Backup Mode and Fast Checkpoint

The `fast` parameter can request an immediate checkpoint at backup start, reducing wait time while causing an I/O burst. Choose based on workload/storage and monitor latency. Do not assume `fast` is always better.

### 6.7. Snapshot Consistency

A storage snapshot is only useful when related volumes are snapshotted at a single consistent point in time. If PGDATA, WAL, and tablespaces span multiple volumes, snapshotting volumes at slightly different times can produce an inconsistent backup.

Use the storage provider's group snapshot/consistency group mechanism or the backup API combined with WAL to ensure consistency.

### 6.8. Snapshots Do Not Automatically Create a WAL Archive

Snapshotting data volumes does not guarantee that required WAL segments are durably stored externally. Design retention and archiving for WAL, verify segment continuity, and keep timeline history files.

### 6.9. File-Level Backups Must Preserve Metadata

When copying/restoring, preserve:

- File ownership of the PostgreSQL OS user;
- Permissions/modes;
- Symlinks for tablespaces and WAL;
- File timestamps when needed by tools;
- Sparse files/hard links if the backup format relies on them;
- Extended attributes/ACLs if required by the platform.

Do not extract backups using an account or tool that alters ownership/permissions without checking.

## 7. Verifying Backups with pg_verifybackup

### 7.1. Backup Manifest

In supported versions, `pg_basebackup` generates `backup_manifest` containing the list of files, sizes, and checksum metadata. The manifest helps verify that backup files are not missing or unexpectedly altered.

### 7.2. Running pg_verifybackup

~~~bash
pg_verifybackup /backups/pg/base-2026-11-14
~~~

The tool reads the manifest, checks listed files, and verifies associated WAL according to version capabilities/options. Use the binary matching the major version and inspect the exit status.

### 7.3. Choosing a Checksum Algorithm

Manifests can use different checksum algorithms depending on version, such as CRC32C or SHA-256. SHA-256 offers stronger collision resistance than CRC for file verification, though it does not encrypt the backup or authenticate against an attacker if the manifest itself can also be altered.

### 7.4. pg_verifybackup Is Not a Restore Test

A backup can pass manifest verification yet still miss RTO, lack configs outside PGDATA, lack extension binaries, have wrong permissions, or fail on start/replay. Only a restore test proves the full end-to-end recovery procedure.

### 7.5. WAL Parsing

`pg_verifybackup` can check WAL inside the backup per version capabilities. Options such as skipping WAL parsing or specifying a WAL directory alter verification scope. Do not enable skip options without understanding the purpose of the check.

### 7.6. Verification Output

Record:

- Backup path and timestamp;
- PostgreSQL major/minor version;
- Manifest checksum algorithm;
- Missing/extra/modified files;
- WAL verification results;
- Exit code;
- Tool version and command options.

### 7.7. Backup Checksum vs. Data Page Checksum

A backup manifest checksum verifies backup files against the manifest. A data page checksum is metadata inside each page of the cluster. A backup with a valid manifest checksum does not guarantee every page inside had its page checksum verified when the server took the backup.

## 8. Incremental Physical Backups

### 8.1. What Is an Incremental Backup?

An incremental backup stores only blocks changed since a prior backup using a mechanism supported by PostgreSQL. It can reduce data transferred/stored, yet restore must combine the exact backup chain.

### 8.2. PostgreSQL 17+

PostgreSQL 17 introduced incremental backup support in `pg_basebackup` and the `pg_combinebackup` tool. Features and options depend on major version; read the exact installation documentation.

Example creating an incremental backup based on a prior backup's manifest:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /backups/incremental-2026-11-15 \
  --incremental=/backups/base/backup_manifest \
  -Fp \
  -X stream \
  -P
~~~

Manifest paths and incremental chain specification depend on version/tool. Keep the manifests of the base backup and each incremental intact; do not move/rename them in ways that break metadata references.

### 8.3. pg_combinebackup

An incremental workflow requires combining incremental backups along the exact base backup and manifest chain:

~~~bash
pg_combinebackup \
  /backups/base \
  /backups/incremental-01 \
  /backups/incremental-02 \
  -o /restore/combined
~~~

This is an illustrative command format; options/ordering and metadata requirements must be confirmed with `pg_combinebackup --help` for your version. The combined backup output serves as input to the restore process.

### 8.4. You Cannot Arbitrarily Drop a Middle Incremental

An incremental chain depends on preceding backups and block references/manifests. If a required backup is missing, you cannot assume taking only the latest incremental is enough. Manage the catalog/manifest and retention for the entire chain.

### 8.5. Full Backups Are Still Necessary

Incremental backups do not eliminate the need for full/base backups and WAL archives. Account for total restore cost, combine time, number of incrementals in the chain, and the risk of a single corrupted artifact.

### 8.6. Restore Testing for Incremental Chains

Test all of:

- Creating base + multiple incrementals;
- Verifying each backup;
- Combining the exact chain;
- Restoring the combined backup;
- Replaying WAL;
- Checking databases and queries.

Do not inspect individual incremental files only in isolation.

## 9. WAL Archive and Recovery Conditions

### 9.1. archive_mode

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

`archive_mode` enables WAL archiving. `archive_command` runs a command to copy completed WAL segments to archive storage. `archive_timeout` can force a segment switch after a time interval to reduce archive latency under low-WAL workloads.

### 9.2. archive_command

Example on Unix:

~~~conf
archive_mode = on
archive_command = 'test ! -f /wal-archive/%f && cp %p /wal-archive/%f'
~~~

This is a simple lab example. Production requires atomic publish, retries, exit code checks, write permissions, network failure handling, retention, encryption, and monitoring. The command must return exit code 0 only when archiving succeeds; if it fails, PostgreSQL will retry.

### 9.3. Do Not Overwrite Existing WAL Archives

WAL segment names are tied to timeline/log sequence. Never use a command that blindly overwrites an existing archive file. If a file already exists, verify its content/identity; do not assume every file with the same name is identical across all timelines/recovery scenarios.

### 9.4. Archive Timeout and RPO

`archive_timeout` can bound the wait time for a segment switch during low workloads, yet it does not guarantee archiving succeeded. RPO depends on durably written WAL, the archive pipeline, network/storage, and failure monitoring.

### 9.5. Checking Archive Failures

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

If `failed_count` increases or `last_archived_time` is too stale for the workload, inspect archive command logs, filesystem capacity, credentials, network, and destination.

### 9.6. The WAL Archive Must Be Continuous

PITR requires continuous WAL segments from the recovery starting point. A single missing segment in the middle can stop recovery before the target, even if later segments exist.

### 9.7. Timeline History

When a standby is promoted, PostgreSQL creates a new timeline and a `.history` file describing the history branch. The WAL archive must retain history files alongside WAL segments. Without timeline history, recovery may not know which branch to follow.

### 9.8. WAL Archive vs. Replication Slot

A replication slot retains WAL on the primary so a consumer can still read it. `archive_command` copies WAL segments to an external repository. A slot does not replace an archive backup; conversely, archiving does not automatically keep WAL in `pg_wal` for a streaming standby.

## 10. Physical Recovery from a Base Backup

### 10.1. Preparation Before Restore

Before touching the data directory:

1. Confirm the backup artifact and timestamp to recover;
2. Identify source major/minor version, build, and platform;
3. Verify the base backup using its manifest/appropriate tool;
4. Confirm required WAL is available with no missing segments;
5. Identify tablespaces, WAL paths, configs, and external dependencies;
6. Ensure target storage has adequate capacity and ownership;
7. Isolate the old instance so two primaries cannot accept writes simultaneously;
8. Plan to retain the old data directory for rollback/forensics.

### 10.2. Do Not Overwrite a Live Data Directory

Do not extract a backup onto PGDATA of a running server. Do not delete the old directory before verifying the backup and committing to the restore. If replacing an instance, stop the service cleanly, verify processes, move the old copy to a safe path, and create a fresh data directory.

### 10.3. Restoring a Plain-Format Base Backup

If a plain-format backup was created at `/srv/pgbackup/base`, conceptual steps:

~~~bash
pg_ctl -D /var/lib/postgresql/data stop -m fast
mv /var/lib/postgresql/data /var/lib/postgresql/data.pre-restore
mkdir -p /var/lib/postgresql/data
rsync -a /srv/pgbackup/base/ /var/lib/postgresql/data/
chown -R postgres:postgres /var/lib/postgresql/data
chmod 700 /var/lib/postgresql/data
~~~

This is an illustrative Unix example, not a copy-paste production script. Verify paths, owner/group, and tablespaces first. If the backup has symlinks to tablespaces outside PGDATA, restore those target paths before starting.

### 10.4. Restoring Tar Format

With tar format, extract archives according to the layout/metadata created by `pg_basebackup` and handle tablespaces per exact mapping. Do not extract all tar files into one arbitrary directory; tablespace archives must go to their exact destinations.

### 10.5. Checking PG_VERSION

The `PG_VERSION` file records the data directory's major version. Read it and compare with `postgres --version`. If the major version does not match, stop and use the matching binary; do not try multiple binaries blindly to see which one starts.

### 10.6. Checking Tablespaces

The `pg_tblspc` directory contains symbolic links to tablespaces. Inspect:

~~~bash
ls -la /var/lib/postgresql/data/pg_tblspc
~~~

Each link must point to an existing path on the right volume with proper permissions. If restoring to new paths, use `-T` during backup or controlled mapping/copying.

### 10.7. Restoring Configs

Determine the actual locations of:

- `postgresql.conf`;
- `postgresql.auto.conf`;
- `pg_hba.conf`;
- `pg_ident.conf`;
- SSL certificates/private keys;
- `archive_command` and `restore_command`;
- Service manager/unit, environment, and secrets.

Some configs are placed outside PGDATA via command-line options or `config_file`/`hba_file`. Physical backups do not automatically carry configs stored outside the data directory.

### 10.8. Checking File Permissions

PostgreSQL requires secure permissions on the data directory and private keys. If owner/mode are wrong, the server may refuse to start or introduce security risks. Use the proper service account and keep permissions per platform documentation.

### 10.9. Initial Startup

~~~bash
pg_ctl -D /var/lib/postgresql/data start -l /var/log/postgresql/restore.log
~~~

Monitor logs from the beginning until the server reports ready. If the backup needs crash recovery, PostgreSQL will automatically replay WAL inside the data directory. If archive recovery is needed, prepare recovery configuration before starting.

### 10.10. Checking Server Recovery Status

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction;
~~~

`pg_is_in_recovery()` indicates whether the server is still in recovery/standby. On a standalone server after crash recovery completes, the value is usually false; on a standby replaying WAL, it is true.

### 10.11. Do Not Promote Without Understanding the Timeline

If the goal is building a standby, keep standby mode and continue receiving WAL. If the goal is standalone PITR, choose the target and recovery action intentionally. Promoting creates a new timeline and allows the node to accept writes; the old primary must be fenced first.

## 11. Archive Recovery and PITR

### 11.1. Recovery Signal Files

In PostgreSQL 12 and later, recovery mode is controlled via signal files:

- `recovery.signal`: requests archive recovery/PITR;
- `standby.signal`: starts in standby mode.

Versions prior to PostgreSQL 12 used `recovery.conf`. That file was removed in newer versions; do not follow legacy `recovery.conf` instructions for PostgreSQL 12+.

### 11.2. restore_command

`restore_command` runs a command to fetch a WAL segment from the archive:

~~~conf
restore_command = 'cp /wal-archive/%f %p'
~~~

- `%f`: filename to retrieve;
- `%p`: destination path where PostgreSQL expects the file.

The command must return exit code 0 when the file is found and restored successfully, and non-zero when unavailable/unretrievable. Production typically uses dedicated archive/restore tools with retries, checksums, credentials, and logging.

### 11.3. Basic PITR Configuration

In PostgreSQL 12+, settings can be placed in `postgresql.conf` or `postgresql.auto.conf`:

~~~conf
restore_command = 'cp /wal-archive/%f %p'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
~~~

Create the signal file:

~~~bash
touch /var/lib/postgresql/data/recovery.signal
~~~

Start the server with the matching binary. The example timestamp is illustrative; use your actual timezone and target. Never leave `standby.signal` present when intending standalone PITR.

### 11.4. Recovery Target Types

PostgreSQL supports multiple target types depending on version:

- `recovery_target_time`: timestamp;
- `recovery_target_xid`: transaction ID;
- `recovery_target_name`: named restore point;
- `recovery_target_lsn`: WAL LSN.

Select the target based on data and logs. Target time is not necessarily the wall-clock moment a user clicked a button; server clocks, timezones, and transaction commit times must be understood clearly.

### 11.5. Restore Point

Before a risky change, you can create a named restore point:

~~~sql
SELECT pg_create_restore_point('before_schema_change');
~~~

The restore point name is recorded in WAL. PITR can target `recovery_target_name` accordingly if all WAL from the base backup to that point is intact.

### 11.6. recovery_target_inclusive

`recovery_target_inclusive` controls whether to apply the transaction/target event at the recovery point or stop immediately before it, per the target type's semantics. With time targets, understand transaction timestamps and commit ordering before choosing.

### 11.7. recovery_target_action

Common actions:

- `pause`: pauses replay at the target so the DBA can inspect;
- `promote`: promotes after reaching the target;
- `shutdown`: shuts down the server after reaching the target.

`pause` is useful when you want to verify data before allowing writes. Do not promote prematurely before confirming the exact target.

### 11.8. recovery_target_timeline

`latest` directs recovery to follow the newest timeline found in the archive based on timeline history. When recovering onto a specific history branch, specify the timeline ID or appropriate setting per version.

### 11.9. Inspecting After Pause

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Verify business data, row counts, timestamps, constraints, and key queries. Once confirmed:

~~~sql
SELECT pg_promote(wait => true);
~~~

Promotion ends recovery and creates a new timeline. Promotion must be executed on the right node only after the old primary has been fenced.

### 11.10. Missing WAL Mid-Stream

If `restore_command` cannot fetch a required WAL segment, recovery cannot advance past the gap. PostgreSQL may stop at the last valid WAL or report an error depending on context. Never copy a similarly named segment to fill a gap.

### 11.11. Determining the Recovery Point

Use:

- Application audit logs;
- Transaction/event timestamps;
- WAL/restore point metadata;
- Monitoring/incident timestamps;
- Known-good query results;
- Timeline history.

Spin up a test restore at the closest candidate target before deciding on production cutover.

### 11.12. Recovery Targets and Committed Data

PITR replays WAL in order per target semantics. A large transaction might commit before or after the expected moment; do not infer row state solely from when a statement began. Verify transaction commits and business records after recovery.

## 12. Provisioning a Physical Standby and Failover

### 12.1. A Standby Is a Physical Copy Following the Primary

A physical standby starts from a base backup of the primary (or an eligible source), then receives WAL via streaming replication or archive recovery and replays it to update data pages.

### 12.2. standby.signal

PostgreSQL 12+ enters standby mode when `standby.signal` exists in PGDATA. `pg_basebackup -R` creates this file and writes recovery connection settings into `postgresql.auto.conf`.

### 12.3. primary_conninfo

Example:

~~~conf
primary_conninfo = 'host=db-primary.example.internal port=5432 user=replicator application_name=standby01 sslmode=verify-full'
~~~

Provide appropriate connection settings; protect passwords via passfile/secret management rather than embedding plaintext in config files if disallowed by policy. TLS certificates/CA and DNS/network routes must also be configured on the standby.

### 12.4. primary_slot_name

~~~conf
primary_slot_name = 'standby_slot_01'
~~~

A slot makes the primary retain WAL for the registered standby. If a standby is down for a long time, the slot can cause `pg_wal` to grow rapidly. Monitor slot activity, retained WAL, and `max_slot_wal_keep_size` per version.

### 12.5. Combining restore_command with Streaming

A standby can use `restore_command` to retrieve WAL from the archive first, then continue streaming from the primary once connected. This helps when a standby suffers network interruptions or needs to catch up from the archive.

### 12.6. Checking the WAL Receiver

On the standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

This view shows receiver state, sender host/port, slot, received LSN, and streaming status. Columns vary by version; check the corresponding documentation.

### 12.7. Checking Replication on the Primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Compare sent/write/flush/replay LSNs to identify which stage the standby is lagging in. Lag time may be NULL when no new transactions occur or stats cannot be computed in the observation window; use both LSN distance and monitoring.

### 12.8. Read-Only Queries on Standby

A standby in recovery cannot accept normal writes. Read-only queries can be permitted if `hot_standby` and version/config conditions are met. Some queries may be canceled due to recovery conflicts.

### 12.9. Hot Standby Conflicts

WAL replay during recovery can conflict with queries holding snapshots/locks on the standby. PostgreSQL can wait or cancel queries based on settings such as `max_standby_streaming_delay`, `max_standby_archive_delay`, and feedback policy.

Increasing delay reduces query cancellations yet increases replay lag. `hot_standby_feedback` can reduce certain conflicts yet holds back `xmin` on the primary, affecting vacuum. Tuning must balance reporting workloads and primary bloat.

### 12.10. Promoting a Standby

When the primary is lost and failover is decided:

~~~sql
SELECT pg_promote(wait => true);
~~~

Or use an appropriate management tool. Prior to promotion, confirm the chosen node, replayed WAL level, potential data loss per RPO, and that the old primary is fenced.

### 12.11. Split Brain

If the old primary continues accepting writes while a standby is promoted, both nodes create two independent data histories. There is no safe way to automatically merge physical WAL branches.

Use fencing: shut down/isolate the old node, revoke VIP/load balancer/write routing, or use cluster manager mechanisms to guarantee only one primary is active.

### 12.12. Rejoining the Old Node

After failover, the old node does not automatically become a valid standby just by changing its hostname. Depending on divergence and WAL availability, `pg_rewind` can be used if prerequisites are met; otherwise, rebuild a fresh base backup from the new primary.

### 12.13. Failback

Failback is a deliberate procedure: rebuild the standby, wait for catch-up, verify health, schedule a role switch, and fence the current primary. Never simply promote the old node again just because it used to be the primary.

## 13. Timelines and WAL History

### 13.1. What Is a Timeline?

A timeline is a branch of WAL history. A newly initialized cluster usually starts on timeline 1. When a standby is promoted or recovery finishes via promotion, PostgreSQL creates a new timeline ID and writes a timeline history.

### 13.2. Why Are Timelines Needed?

After failover, the new node can generate WAL in the same LSN range as the old history but with different content. Timelines distinguish WAL branches so recovery does not mix up records from two histories.

### 13.3. Timeline History File

A file such as `00000002.history` describes which prior timeline the new timeline branched from, at which LSN, and may include reason/comment metadata. The archive must retain `.history` files.

### 13.4. recovery_target_timeline

`recovery_target_timeline='latest'` tells recovery to pick the newest timeline reachable via timeline history. When recovering a specific branch, set the timeline ID per version docs and ensure history/WAL for that branch are complete.

### 13.5. Never Mix WAL from Two Timelines

Never rename a WAL segment from timeline A to timeline B, or copy a file with the same name from another archive without verifying timeline. Any mix-up can cause recovery to fail or follow the wrong history.

### 13.6. The WAL Archive Must Support Multiple Timelines

Archive storage should retain files with full names and timeline history. Do not delete `.history` files just because they are small; this metadata is required to select recovery branches.

### 13.7. Determining the Current Timeline

You can inspect control data:

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

The output provides checkpoint/timeline metadata per version. While the server is running, use `pg_control_checkpoint()` if permissions/version permit, or appropriate monitoring/replication tools.

## 14. pg_rewind and Resynchronizing Diverged Nodes

### 14.1. When to Use pg_rewind?

After failover, the old primary may have received writes that the new primary does not have. `pg_rewind` compares timeline divergence and updates data files on the old node to bring it back onto the new primary's branch, avoiding a full cluster recopy when conditions are met.

### 14.2. Prerequisites

Typical requirements include:

- Same PostgreSQL major version;
- Data checksums enabled or `wal_log_hints=on` per version requirements;
- Sufficient WAL to determine changes since the relevant checkpoint (or retrievable from archive);
- Valid source/target data directories with the target shut down;
- Appropriate access privileges and configuration;
- `full_page_writes` enabled per documentation requirements.

Read the `pg_rewind` manual page for your exact major version before using it. Do not enable `wal_log_hints` after divergence and assume older WAL already recorded sufficient hints.

### 14.3. pg_rewind Example

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/old-primary \
  --source-server='host=new-primary.example.internal user=rewind_user dbname=postgres'
~~~

Illustrative example; the source connection requires appropriate privileges/credentials and the target server must be stopped. After rewinding, configure the node as a standby, create `standby.signal`, set `primary_conninfo`/slot, and start.

### 14.4. pg_rewind Is Not a Data Merge Tool

If the old node received writes that must be kept, `pg_rewind` does not merge business transactions from both branches. Divergent writes on the target are overwritten so the node follows the source timeline. Export data that must be kept via logical processes before rewinding if business requirements demand it.

### 14.5. When Must You Re-run pg_basebackup?

If required WAL is unavailable, checksum/hint prerequisites are unmet, target/source are incompatible, or rewind fails, provisioning a fresh standby from a base backup of the current primary is usually the cleaner choice.

## 15. PostgreSQL Version Compatibility Requirements

### 15.1. Major Version Must Be Compatible

A physical data directory is created by a specific PostgreSQL major version. You cannot start a PostgreSQL 16 PGDATA with PostgreSQL 17 and treat it as an automatic upgrade.

Example:

| Data Directory | Binary | Result |
| --- | --- | --- |
| PostgreSQL 16 | PostgreSQL 16 | Same major; check minor/build and other requirements |
| PostgreSQL 16 | PostgreSQL 17 | Not a supported upgrade path |
| PostgreSQL 17 | PostgreSQL 16 | Incompatible; physical downgrade unsupported |
| PostgreSQL 17 | PostgreSQL 17 | Same major; check build/cluster parameters |

To change major versions, use **pg_upgrade**, logical dump/restore, or logical replication migration according to the target version's instructions.

### 15.2. PG_VERSION

The `PG_VERSION` file in PGDATA records the cluster's major version, such as 16 or 17. This is a quick check, yet you should still use `pg_controldata` to verify cluster metadata.

### 15.3. Minor Releases Within the Same Major Version

PostgreSQL minor releases are designed to maintain data file format compatibility within the same major version, so a data directory can generally be opened by a newer minor release of the same major per release guidelines. However:

- Physical streaming replication/standby should keep primary and standby on the same minor release per version support recommendations;
- Do not run an older minor binary against data files already used by a newer minor without explicitly verifying support;
- Apply minor updates using official procedures, updating all nodes in HA order;
- Check release notes for changes affecting WAL, recovery, or extensions.

For incident restores, the least surprising approach is to start with the exact major/minor/build recorded in backup metadata, complete recovery, and then apply minor updates according to plan.

### 15.4. WAL Compatibility

WAL is an internal format tied to major version and build parameters. Never assume WAL from a different major version can replay on the current server. Never combine WAL segments from multiple clusters just because filenames appear to match.

### 15.5. System Identifier

Each PostgreSQL cluster has a system identifier. A physical base backup/standby belonging to the same cluster history has a matching identifier. Check via:

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Look for the `Database system identifier` line. This is critical metadata for verifying the source cluster. Never alter the system identifier to force an incompatible data directory.

### 15.6. Catalog Version

`pg_controldata` also displays the catalog version number. Catalog formats change across major releases; this is one reason a physical data directory cannot be upgraded simply by swapping executables.

### 15.7. Do Not Use pg_resetwal to Change Versions

`pg_resetwal` is a rescue tool for corrupted WAL/control information in extraordinary situations. It does not convert storage formats, does not replace recovering from backups, and is not a way to boot PGDATA with a different major version.

## 16. OS, CPU Architecture, and Build Compatibility

### 16.1. Physical Files Are Not a Portable Interchange Format

Relation files contain page/tuple representations dependent on build, alignment, endianness, and platform characteristics. A physical backup is not equivalent to a portable SQL dump.

### 16.2. OS and Architecture

When moving a physical data directory between hosts:

- Prefer the same operating system family and CPU architecture;
- Keep the same endianness and word size;
- Check ABI/runtime dependencies;
- Use a compatible PostgreSQL build;
- Verify filesystem semantics, symlinks, and ownership.

Do not copy physical PGDATA between x86_64 and ARM64, or between little-endian and big-endian, assuming the server can read it. For cross-platform migration, prefer logical dump/restore or a migration method supported by PostgreSQL.

### 16.3. Block Size

A PostgreSQL build has `BLCKSZ` (database block size), typically 8 KB. Physical data pages are formatted to this block size. A binary with a different block size cannot compatibly read the data directory.

### 16.4. WAL Block Size

WAL has its own build-time block size. Physical recovery/replication must use a binary whose WAL format parameters match the cluster.

### 16.5. WAL Segment Size

WAL segment size is determined when creating the cluster/build per version mechanism. Clusters with different WAL segment sizes should not be treated as compatible physical peers. Verify `Bytes per WAL segment` in `pg_controldata`.

### 16.6. Other Build Options

Certain build options/compile-time constants can affect physical compatibility or extension ABI. When using custom builds, record:

- PostgreSQL version and source commit/vendor build;
- `BLCKSZ`;
- WAL block size;
- WAL segment size;
- Compiler/ABI/platform;
- Optional features and linked libraries;
- Extension package versions.

### 16.7. pg_controldata for Inspecting Metadata

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Fields to record:

- Database system identifier;
- Database cluster state;
- Latest checkpoint location;
- Latest checkpoint's REDO location;
- Latest checkpoint's TimeLineID;
- Database block size;
- WAL block size;
- Bytes per WAL segment;
- Data page checksum version;
- Catalog version number.

Field names may vary slightly by major version. Use the `pg_controldata` binary matching the cluster's version.

### 16.8. Checking the Server Build

~~~sql
SELECT version();
SHOW server_version;
SHOW block_size;
SHOW wal_block_size;
SHOW wal_segment_size;
SHOW data_checksums;
~~~

Not all GUCs exist in every major release; if `SHOW wal_segment_size` is unsupported, use `pg_controldata`.

### 16.9. Tablespace Paths and Filesystem

A cluster may store relation files across multiple mount points. Restoring onto a new host requires mounting matching volumes or mapping tablespaces to new paths. Verify case sensitivity, path length, filesystem permissions, symlink support, and storage capacity.

### 16.10. Do Not Equate Disk Sector Size with PostgreSQL Block Size

`BLCKSZ`, WAL block size, and storage sector size are distinct concepts. Using the same 8 KB PostgreSQL page size does not guarantee two storage devices share identical durability/atomic write semantics.

## 17. Tablespaces, Configs, and External Dependencies

### 17.1. Tablespaces Can Reside Outside PGDATA

PostgreSQL stores tablespace metadata in catalogs and links under `PGDATA/pg_tblspc`. Actual tablespace contents reside at separate paths. Backing up only PGDATA while skipping tablespace targets can leave restores missing relation files.

### 17.2. Inspecting Tablespaces in SQL

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes
FROM pg_tablespace
ORDER BY spcname;
~~~

Default tablespaces return an empty location per function semantics. Record tablespace name, path, owner, mount/volume, and size before backup/restore.

### 17.3. pg_basebackup and Tablespaces

`pg_basebackup` can copy tablespaces and create matching directories per format. When the target differs from source paths, use tablespace mapping (`-T`) appropriately. Verify backup output, symlinks, and all tablespace archives.

### 17.4. External WAL Directory

`pg_wal` can be placed on a separate filesystem via symlink. During restore, recover the WAL directory at the proper path and permissions; if the backup format separates WAL, handle it per format/tool.

### 17.5. Configs Outside PGDATA

The following files may reside outside the data directory:

- `postgresql.conf`;
- `pg_hba.conf`;
- `pg_ident.conf`;
- SSL CA/cert/private key;
- `archive_command`/`restore_command` scripts;
- Include files and environment files;
- Service manager definitions.

Record active paths with:

~~~sql
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW ssl;
SHOW ssl_cert_file;
SHOW ssl_key_file;
~~~

### 17.6. postgresql.auto.conf

`postgresql.auto.conf` lives inside PGDATA and may contain settings written by `ALTER SYSTEM` or `pg_basebackup -R`. After restore, check that hostnames, paths, slots, `primary_conninfo`, archive commands, and parameters fit the new node.

### 17.7. Do Not Copy Primary Configs Verbatim to Every Node

Certain settings are node-specific:

- `listen_addresses`, port;
- `primary_conninfo`, `primary_slot_name`;
- `restore_command`, `archive_command`;
- SSL paths;
- `hot_standby`, `synchronous_standby_names`;
- `archive_mode` and settings tied to the current role.

Verbatim copied configs can cause a standby to connect to the wrong primary, archive to the wrong destination, or two nodes to share the same identity/service endpoint.

### 17.8. Extension Binaries

Physical backups preserve extension SQL catalogs and objects, yet they do not install shared libraries/packages onto the target OS. Before starting:

1. Install extension packages compatible with the major version;
2. Ensure shared libraries are in the proper library path;
3. Check `shared_preload_libraries`;
4. Install OS system dependencies;
5. Verify extension versions in catalogs.

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

### 17.9. shared_preload_libraries

If config requires preloading an extension library missing on the restore host, PostgreSQL may fail to start. Check:

~~~sql
SHOW shared_preload_libraries;
~~~

On a stopped server, inspect config files and install the corresponding package or adjust config per the recovery plan. Never delete extension catalog entries just to make the server boot.

### 17.10. Extension Version Upgrades

After physical restore, extension SQL versions normally match their state at backup time. If the target environment installs a different binary extension version, mismatches can arise. Install the matching package version first; once the server is running and backup/rollback is ready, run `ALTER EXTENSION ... UPDATE` per vendor instructions.

### 17.11. Foreign Data Wrappers and External Services

FDW definitions may reside in catalogs, yet drivers, client libraries, certificates, remote credentials, network routes, and remote systems are not inside a physical backup. Track them as external dependencies.

### 17.12. Encryption Keys and KMS

If storage encryption, TDE-like extensions, or application-level encryption rely on keys outside PGDATA, restore requires access to those keys/KMS and version-compatible libraries. Ciphertext backups without a key recovery process may be unusable.

### 17.13. Secrets

Never place passwords, private keys, or KMS credentials in source control or backup manifests. Manage secrets via a secret manager, rotate per procedure, and verify access permissions from the restore host.

## 18. Collation, Locale, and Index Compatibility

### 18.1. Why Does Locale Affect Physical Restore?

PostgreSQL can use libc or ICU to compare/sort text by locale. B-tree indexes on text/collations depend on that sort order. When restoring onto a host with a different libc/ICU version, actual collation ordering may change.

### 18.2. Data Files Can Start Yet Index Ordering May Be Stale

Physical restore may still succeed, yet if collation behavior changed, some indexes built under the old version might no longer match current ordering. This can lead to unexpected query results/order or index lookups if unaddressed.

### 18.3. Checking Database Collation Version

~~~sql
SELECT
    datname,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_version
FROM pg_database
WHERE datcollversion IS DISTINCT FROM
      pg_database_collation_actual_version(oid);
~~~

Function/column names and availability depend on major version. You may also need to inspect individual collations in `pg_collation` using `pg_collation_actual_version(oid)`.

### 18.4. Handling Collation Version Mismatch

When the actual version differs from the recorded version:

1. Identify affected databases/collations;
2. Find indexes and objects depending on those collations;
3. Schedule `REINDEX` for necessary indexes;
4. Execute `REINDEX` during a maintenance window or concurrently if supported by the index type/version;
5. After rebuilding completes, refresh the recorded collation version with the appropriate command;
6. Verify query results and application behavior.

Do not run `ALTER DATABASE ... REFRESH COLLATION VERSION` and assume indexes were rebuilt. Refreshing only updates version metadata; it does not fix indexes built under the old collation.

### 18.5. Recording ICU/libc Versions

Record:

- Operating system distribution/release;
- libc version;
- ICU version;
- Database locale/encoding;
- Collation provider and recorded collation version;
- `REINDEX` plan after OS upgrades.

### 18.6. Encoding

Database encoding is also a database property. Physical backups preserve existing encoding; you cannot change encoding simply by restoring with a different binary. To change encoding, use logical migration and verify all data is representable in the target encoding.

## 19. Other Compatibility Requirements

### 19.1. Data Checksums

Checksum state is cluster-wide metadata. Inspect via:

~~~sql
SHOW data_checksums;
~~~

When restoring a physical backup, do not arbitrarily enable/disable checksums on individual nodes. If state changes are needed, use `pg_checksums` offline with the exact major version and synchronize the procedure across the topology.

### 19.2. WAL Segment Size and Backup Metadata

WAL segment size must be compatible with the cluster/build used for recovery/replication. Record `Bytes per WAL segment` from `pg_controldata`; never fabricate empty segments to fill missing files.

### 19.3. Shared Memory and OS Limits

The new server may require tuning:

- Shared memory limits;
- Huge pages;
- `max_connections`;
- `shared_buffers`;
- File descriptor limits;
- Process/thread limits;
- Kernel settings;
- Cgroup/container memory and CPU limits.

These settings usually do not alter data format yet can prevent the server from starting or cause poor performance after restore.

### 19.4. Architecture-Specific Extensions

Extension binaries can depend on CPU architecture, compiler ABI, and system libraries. An extension package for x86_64 cannot be used verbatim on ARM64; install the right package/build for the target host.

### 19.5. Locale Provider and Collation

libc/ICU locale providers, ICU locale data, and OS packages may differ. A physical copy does not recreate the source host's locale environment. Verify before opening production traffic.

### 19.6. Encryption at Rest

Storage encryption can live at the block device, cloud volume, filesystem, or extension layer. Restore requires keys, KMS permissions, and corresponding mount/decrypt procedures. Key rotation must never break readability of older backups.

### 19.7. Hostname, DNS, and Network Identity

Configs may retain the old primary hostname, TLS SANs, DNS aliases, or endpoints. When restoring onto a new host, inspect service discovery, certificates, firewalls, `pg_hba.conf`, routing, and monitoring labels.

### 19.8. Client Version Is Not Server Compatibility

A newer `psql` client can generally connect to an older server within protocol/feature limits, yet that does not mean a server binary can read physical data files of a different major version. Distinguish client/server protocol from on-disk compatibility.

### 19.9. Logical Replication and Extensions

If switching to logical replication or migration after restore, verify publication/subscription state, replication slots, replica identity, extension support, and DDL synchronization. Catalog objects alone do not guarantee external consumers are recovered.

### 19.10. Configuration Drift

Maintain configuration via infrastructure-as-code or configuration management. Compare server parameters before/after restore; do not rely solely on config files inside PGDATA, as some values come from command line, environment, `auto.conf`, include files, or managed services.

## 20. Physical Restore Compatibility Matrix

### 20.1. Quick Decision Table

| Component | Requirement / Recommendation | If Mismatched |
| --- | --- | --- |
| PostgreSQL major version | Same major version | Physical start/replay unsupported; use upgrade/migration |
| Minor version | Same minor is lowest risk; minor releases within same major keep data format per policy | Check release notes, WAL/replication support; do not arbitrarily use an older binary |
| OS/CPU architecture | Same supported platform/ABI/endianness | Prefer logical migration |
| Database block size | Must match build/cluster | Binary cannot read page format |
| WAL block/segment size | Must be compatible | WAL/recovery/replication may fail |
| Catalog version | Must match major version | Data directory cannot be opened by another major binary |
| Tablespaces | Must have all files and valid paths | Missing relation files or server fails to start |
| Checksums | Maintain cluster state and version-matched tools | Checksum validation/rewind may fail |
| Extensions | Compatible shared libraries/dependencies | Startup error or extension functions fail |
| Collation/locale | Provider/version must be verified | May require REINDEX on collation-dependent indexes |
| Config/SSL/secrets | Must exist and fit target host | Connection, TLS, archive, or startup failure |
| WAL archive/timeline | Continuous WAL and correct timeline | Recovery cannot reach target |

### 20.2. When to Choose Logical Migration

Prefer logical dump/restore or logical replication when:

- Changing major versions;
- Changing OS/CPU architecture or endianness;
- Changing database encoding;
- Selecting specific databases/schemas/tables;
- Transforming schema/data models during migration;
- Physical build parameters are incompatible;
- Reorganizing tablespaces or indexes to a new design.

### 20.3. Physical Restore vs. pg_upgrade

Physical restore recovers a cluster in the same on-disk major format. `pg_upgrade` is a major-version upgrade workflow that validates catalog/data compatibility and performs required conversions. Never use a base backup as a substitute for `pg_upgrade`.

### 20.4. Do Not Infer Compatibility from a Single Version String

Two servers both reporting PostgreSQL 17 may still differ in:

- Build options;
- `BLCKSZ`;
- WAL segment size;
- OS/CPU;
- Extension libraries;
- Locale provider/version;
- Checksum state;
- Tablespace layout.

Inventory full build/cluster metadata, not just `server_version`.

## 21. Inspecting the Cluster Before and After Restore

### 21.1. Inventory on the Source

Before backing up, record:

~~~sql
SELECT version();
SHOW server_version;
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW block_size;
SHOW wal_block_size;
SHOW wal_segment_size;
SHOW data_checksums;
SHOW archive_mode;
SHOW archive_command;
SHOW full_page_writes;
SHOW fsync;
~~~

Not all settings exist in every major version. Also save outputs from `pg_controldata`, `pg_extension`, `pg_tablespace`, database encodings/collations, and config files.

### 21.2. Recording Database Inventory

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Columns such as `datlocprovider`/`datcollversion` depend on major version. On older versions, adjust the query accordingly. Note template databases and database-level settings.

### 21.3. Recording Tablespace Inventory

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes
FROM pg_tablespace
ORDER BY spcname;
~~~

### 21.4. Recording Extension Inventory

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

### 21.5. Recording Role/Global Objects

Physical backups preserve global catalogs within the cluster. Still, the backup plan should document roles, memberships, tablespaces, replication users, password/authentication dependencies, and external secrets. If switching to logical restore, dump globals with appropriate tools.

### 21.6. After Restore: Checking Recovery State

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

On a standalone primary, receive/replay LSNs may be NULL after recovery completes. On a standby, monitor the gap between receive and replay along with timestamps.

### 21.7. Checking Database Availability

~~~sql
SELECT
    datname,
    datallowconn,
    datconnlimit,
    pg_database_size(oid) AS database_bytes
FROM pg_database
ORDER BY datname;
~~~

Test connecting to key databases using application roles, not just superuser.

### 21.8. Checking Tablespace Locations

Re-run the inventory query in 21.3 and cross-check every path against actual mounts/volumes. Test accessing tablespace objects holding data outside PGDATA.

### 21.9. Checking Archiving and Replication

On the primary after cutover:

~~~sql
SELECT * FROM pg_stat_archiver;
SELECT * FROM pg_stat_replication;
~~~

On the standby:

~~~sql
SELECT * FROM pg_stat_wal_receiver;
~~~

Confirm archiving is advancing, the standby connects to the right primary, and LSN lag is within bounds.

### 21.10. Checking Extension Functions

Run smoke tests for each key extension: PostGIS, pgcrypto, timescaledb, pg_partman, FDWs, or internal extensions if present. Verify shared libraries and external services, not merely catalog rows.

## 22. Restore Validation and Integrity Checks

### 22.1. A Restore Test Is the Strongest Proof

A green backup job does not prove the database can be recovered. Restore tests must run in an isolated environment using the right binaries, configs, tablespaces, extension packages, secrets, and WAL archive.

### 22.2. Verification Layers

| Layer | Tool / Method | What It Verifies |
| --- | --- | --- |
| Backup files | `pg_verifybackup` | Manifest/files and WAL checks per tool |
| Cluster metadata | `pg_controldata` | System identifier, versions, block/WAL metadata |
| Page checksums | `pg_checksums --check` offline | Page checksums on checksum-enabled clusters |
| WAL | Recovery logs, `pg_waldump` | WAL readability/parsing per check goal |
| Indexes | `pg_amcheck`/`amcheck` | Certain heap/index structural consistency |
| SQL/application | Smoke tests, business queries | Data and application behave correctly |
| DR | Restore/PITR drill | Actual RPO/RTO |

No single tool replaces the other layers.

### 22.3. pg_checksums

If the cluster has data checksums enabled, perform a clean shutdown and run:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data --progress
~~~

This is a cluster-wide I/O scan. Use the binary matching the major version. If checksum state is off, the command cannot verify page integrity via data checksums.

### 22.4. pg_amcheck

In supported versions:

~~~bash
pg_amcheck --all
~~~

`pg_amcheck` leverages checks from the `amcheck` extension to detect certain anomalies in heap/index structures. Options and permissions depend on version; superuser or an appropriately privileged role may be required. This is not a full byte-level checksum scan and does not replace backups.

### 22.5. WAL Inspection

`pg_waldump` can read WAL records to inspect LSNs/timelines/record types:

~~~bash
pg_waldump -p /var/lib/postgresql/data/pg_wal
~~~

Use for diagnostics and inspecting format/records as needed; never modify WAL with this tool. Options/paths vary by version.

### 22.6. Checkpoint Metadata

`pg_controldata` reports cluster state, checkpoint, REDO location, and timeline. Right after recovery finishes, cross-check logs and metadata if investigating. Never edit `pg_control` directly.

### 22.7. SQL Consistency Checks

Run predefined business queries:

- Row counts and aggregate totals;
- Referential integrity and foreign key checks;
- Duplicate detection for business keys;
- Date/time range of data near the target;
- Sequence values and identity columns;
- Materialized views/derived data freshness;
- Application smoke tests and controlled read/write tests.

Do not rely on a single `COUNT(*)` query as proof that the entire database is valid.

### 22.8. Sequence Values

Physical backups preserve sequence state at the backup/recovery point. After PITR, sequences may differ from business records if application logic manages sequences outside transactions or data was specially imported. Check critical sequences and verify the next value will not collide with existing primary keys.

### 22.9. Foreign Keys and Constraints

Physical recovery preserves catalog definitions and data state per WAL. Still, running business validation after restore is valuable, especially if prior to the incident constraints were disabled, replication applied changes, or bulk loads ran. Never disable constraints just to make a restore pass.

### 22.10. Checking Performance After Restore

After restore/cutover:

- Check query plans;
- Confirm statistics/`ANALYZE` as needed;
- Check cache warm-up;
- Check I/O latency and storage throughput;
- Check connection pools;
- Check autovacuum and background workers;
- Check replication lag and archive throughput.

A restored server can have valid data yet perform differently due to cold caches, different storage, OS settings, or collation/index differences.

## 23. Backup Architecture, Retention, and RPO/RTO

### 23.1. RPO

Recovery Point Objective is the maximum acceptable data loss during an incident. RPO depends on base backup frequency, WAL archiving/streaming, archive latency, and continuous WAL retention.

### 23.2. RTO

Recovery Time Objective is the target time to restore service operation. RTO depends on:

- Base backup size;
- Storage/network speed;
- Number of incremental backups to combine;
- WAL volume to replay;
- Extension/config readiness;
- Validation and cutover steps;
- DR site capacity/automation.

### 23.3. Full Backup + WAL Archive

~~~text
PostgreSQL primary
      |
      +---- base backup schedule
      |           |
      |           v
      |      Backup repository
      |
      +---- WAL archive pipeline
                  |
                  v
             WAL repository
                  |
                  v
          Restore/PITR environment
~~~

Base backups supply the data files; the WAL archive advances the cluster to the target. Both parts must be managed as a single recovery set.

### 23.4. Backup Retention

Retain base backups long enough to satisfy retention policy along with the WAL required for each backup. Never delete WAL segments merely because a number of days have passed if they are still required by retained backups.

### 23.5. Archive Cleanup

Use tools such as `pg_archivecleanup` or a catalog-aware backup manager to identify obsolete WAL. Never run `rm *.wal` or delete by arbitrary timestamps; account for backup chains, timeline history, standbys, and replication slots.

### 23.6. Backup Failure Domain

Store backups on storage/locations isolated from the primary. For critical systems, consider immutable/object-lock storage, cross-region replication, encryption, restricted delete permissions, and dedicated monitoring.

### 23.7. 3-2-1 and Offline Copies

A common operational rule is multiple copies across multiple storage types, with at least one off-site/offline/immutable copy. Specific counts depend on policy, yet you must plan for scenarios where both primary and primary backup storage are impacted together.

### 23.8. WAL Archive Monitoring

Monitor:

- Archive success/failure counters;
- Timestamp of the last archived WAL;
- WAL bytes per minute/hour;
- Disk usage and object count;
- Replication slot retained WAL;
- Archive upload/download latency;
- Missing segment/timeline history alarms.

### 23.9. Restore Drills

Schedule targeted drills:

1. Select a base backup and target time;
2. Restore into an isolated environment;
3. Replay WAL;
4. Validate cluster/application;
5. Measure duration of each phase;
6. Record achieved RPO/RTO;
7. Update runbooks and resolve blockers.

### 23.10. Encrypted Backup with Lost Keys

A backup is unusable if the decryption key is lost. Test key escrow/rotation procedures, KMS recovery, IAM roles, and DR environment permissions; test restoring without relying on primary credentials.

## 24. Troubleshooting Physical Restores

### 24.1. Server Reports Wrong Database System Identifier

Causes may include WAL/standby source from another cluster, wrong backup source, or mixed files from multiple clusters. Verify system identifiers with `pg_controldata`, backup metadata, and WAL source. Never modify the system identifier to force recovery.

### 24.2. Server Reports Database Files Are Incompatible with Server

Check:

- Major version in `PG_VERSION`;
- PostgreSQL binary in use;
- Catalog version;
- Block size and WAL format;
- Whether restore accidentally copied PGDATA from another cluster.

Stop trying random binaries to see what starts; identify the exact backup source and version.

### 24.3. WAL Segment Not Found

Check `restore_command`, archive path, credentials, filename mapping, compression/encryption, and timeline history. Determine whether the segment is truly missing or the command cannot access the file.

Never create an empty file or rename a segment to push recovery forward.

### 24.4. WAL Record CRC Error

This may indicate WAL corruption from storage/transfer/archiving. Preserve the corrupted segment and logs; compare against archive/standby copies, inspect device/network/storage, and select an intact backup/WAL chain. Never edit CRC bytes manually.

### 24.5. Invalid Checkpoint Record

Control files or related WAL may be corrupted or mismatched. Preserve the original copy, inspect `pg_controldata`, logs, WAL archive, and backup. Do not run `pg_resetwal` as a first reflex.

### 24.6. Missing Tablespace Directory

Check `pg_tblspc` links, mount points, mapping options, and owner. Restore the exact tablespace files before starting. Never create an empty directory with the same name to trick the server.

### 24.7. Could Not Load Library

Usually caused by a missing extension shared library or dependency on the target host. Install the compatible package, check library paths, and check preload settings. If an extension is unnecessary for emergency startup, adjust configs only after understanding the impact; do not delete catalog objects.

### 24.8. Permission Denied

Check owner/group, data directory mode, private key permissions, tablespace permissions, SELinux/AppArmor policies, and the service user. Avoid `chmod 777` to "fix" errors.

### 24.9. Address Already in Use

Another instance is already using the port/socket or the old service was not stopped. Check running processes and data directories; never start two servers against the same PGDATA.

### 24.10. Server Starts Yet Application Cannot Connect

Check `listen_addresses`, port, `pg_hba.conf`, TLS certificates, DNS, firewalls, roles/passwords, database names, and connection pools. Physical restore does not automatically update external network identity.

### 24.11. Checksum Mismatch After Restore

Record relation/block and server/node/time. Verify backup manifest, data checksums, WAL, storage/transfer paths, and checksum state. Passing a backup manifest does not prove page checksums passed. Run offline verification on an appropriate copy and consider restoring from another backup.

### 24.12. Collation Version Mismatch

Identify affected collations, schedule `REINDEX` for dependent objects, and refresh the recorded version only after handling indexes. Never ignore warnings if the database relies on text indexes for uniqueness or ordering.

### 24.13. Recovery Stops at the Wrong Time

Check timezone, timestamp literals, transaction commit times, `recovery_target_inclusive`, target timeline, and archive WAL availability. Spin up another test restore before cutover.

### 24.14. Standby Cannot Connect to Primary

Check `primary_conninfo`, DNS/network/TLS, replication role, `pg_hba.conf`, port, slot name, and `max_wal_senders`. Inspect receiver logs and `pg_stat_wal_receiver`.

### 24.15. Standby Is Stuck or Replay Lag Grows

Check WAL receiver state, replication slot retention, archive availability, recovery conflicts, disk I/O, and WAL generation rate. Never delete slots or WAL segments just to free disk space.

### 24.16. pg_rewind Prerequisites Not Met

Verify checksums or `wal_log_hints` were enabled before divergence, required WAL is available, the target is shut down, and source/target share the same major version. If unmet, rebuild the standby from a base backup.

### 24.17. pg_verifybackup Fails

Classify whether it is a missing file, checksum mismatch, unexpected file, WAL parse failure, or tool/version mismatch. Keep the original backup intact; never edit the manifest to force a pass. Take a new backup if the artifact cannot be verified.

### 24.18. Incremental Backup Cannot Be Combined

Verify the exact base backup, complete incremental chain, manifests, backup ordering, and `pg_combinebackup` version. Never skip a middle incremental or combine backups from different clusters.

### 24.19. Disk Fills During Restore

Check capacity on PGDATA, tablespaces, `pg_wal`, temporary restore paths, incremental combine output, and WAL archive caches. Pause/isolate the process in a controlled manner before storage is completely exhausted. Never delete relation/WAL files to free disk space.

### 24.20. Recovery Succeeds Yet Data Is Not What Users Expect

Check base backup timestamp, recovery target, timeline, inclusive/exclusive behavior, timezone, application audit logs, and transaction commit times. A technically successful recovery can still have chosen the wrong business target.
## 25. Runbook: Full Cluster Recovery After Losing the Primary

### 25.1. Activating DR

When the primary is completely lost:

1. Confirm the incident and impact scope;
2. Fence the old primary so it can never accept writes again;
3. Select the latest verified backup/WAL archive;
4. Confirm expected RPO and the latest available WAL point;
5. Select a compatible restore host/storage;
6. Prepare tablespaces, configs, extension packages, secrets, and certificates;
7. Communicate DR/cutover status per incident process.

### 25.2. Selecting a Base Backup

Select a base backup with:

- Valid manifest/verification;
- Clear major version/build metadata;
- Complete tablespaces;
- Continuous WAL archive from backup start/stop;
- Required timeline history;
- Backup timestamp within retention.

If multiple backups exist, choose one meeting RPO with a WAL chain replayable to the target.

### 25.3. Restoring to the Target Host

1. Install PostgreSQL binaries matching the exact major version;
2. Prepare empty filesystem/PGDATA and tablespace paths;
3. Restore backup files and ownership;
4. Install extension libraries;
5. Place configs and secrets;
6. Verify WAL archive/restore command;
7. Create `recovery.signal` if archive recovery is needed;
8. Start the server and monitor logs.

### 25.4. Replaying WAL to Latest Available

If the goal is maximum data recovery, configure archive recovery along the appropriate latest timeline. Verify the archive command can read every required WAL segment and `.history` file.

Do not promote just because the server started; wait for recovery to complete or stop at the chosen target.

### 25.5. Pre-Cutover Validation

- `pg_is_in_recovery()` reflects the expected state;
- Databases and tablespaces open cleanly;
- Extensions load properly;
- Critical business queries return sensible data;
- Sequences/constraints are verified;
- Checksum/backup verification run as feasible;
- Application roles can connect;
- Monitoring, backups, and WAL archiving are configured.

### 25.6. Promote and Cutover

Once data is verified and the old primary is fenced:

~~~sql
SELECT pg_promote(wait => true);
~~~

Switch DNS/VIP/load balancer/connection endpoints to the new node. Monitor application errors, connection pools, write throughput, and replication setup.

### 25.7. Post-Cutover

- Take a new base backup from the new primary;
- Start WAL archiving on the new timeline;
- Rebuild standbys;
- Confirm the backup/restore chain;
- Record actual RPO/RTO;
- Investigate root cause of primary loss;
- Retain the old copy for forensics until cleared for cleanup.

## 26. Runbook: PITR After Erroneous Data Changes

### 26.1. Containing the Incident

When an erroneous DELETE/UPDATE/DDL is detected:

1. Stop or throttle the offending writer/job;
2. Record start time, transaction/user/job, and database;
3. Protect the WAL archive and base backups;
4. Determine transaction commit time/target;
5. Never overwrite the primary directly before testing on a separate restore.

### 26.2. Creating an Isolated Restore Environment

Restore the base backup onto a separate host/PGDATA. Never run PITR on the live primary PGDATA serving applications. Replay the WAL archive to just before or after the target per business requirements.

### 26.3. Choosing a Recovery Target

You can use a timestamp, transaction ID, named restore point, or LSN. If uncertain of the exact target, create multiple candidate restores in isolated environments and compare data.

### 26.4. Pausing at Target

Configure `recovery_target_action='pause'`, create `recovery.signal`, and start. Once replay pauses:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Confirm the erroneous transaction has not been replayed or that the target holds the desired data. Inspect commit order and transaction boundaries.

### 26.5. Exporting Data to Recover

If only a few tables/rows are affected, export the data from the restored cluster using logical dump/queries and import it in a controlled manner into production. This often reduces downtime compared to replacing the entire production cluster.

If the entire cluster must roll back to the target, plan a full cutover and accept losing transactions after the target per RPO/business approval.

### 26.6. Promoting the Restored Cluster

If using the restored cluster to replace production, promote only after confirming the target and fencing the current primary. Upon promotion, a new timeline begins. Re-establish archiving, backups, and standbys.

### 26.7. Never Import Data by Copying Relation Files

Never copy table/index files from a restored cluster into a running primary. Use logical export/import, replication, or a supported cluster-wide physical recovery method.

## 27. Runbook: Migrating a Physical Cluster to New Storage

### 27.1. Choosing a Method

Options:

- `pg_basebackup` to new storage followed by cutover;
- Cold copy after clean shutdown;
- Backup API + consistent storage snapshot;
- Provisioning a standby on new storage followed by switchover.

Choose based on downtime, data size, network bandwidth, tablespaces, and RPO.

### 27.2. Using a Standby to Minimize Downtime

1. Create a base backup on the new storage;
2. Start the new node in standby mode;
3. Stream WAL and wait for replay lag to approach zero;
4. Verify extensions/configs/collations;
5. Stop writes or place the application in maintenance;
6. Wait for the standby to replay all sent WAL;
7. Promote/switchover per the HA runbook;
8. Switch endpoints and verify the application.

### 27.3. Verifying New Storage

Measure IOPS, latency, throughput, flush semantics, filesystem capacity, and error counters. Do not compare total capacity alone. New storage must meet durability and workload profiles.

### 27.4. Keeping a Rollback Path

After switchover, the old node may diverge once the new node accepts writes. Never start the old node as a primary. Keep it offline or rewind/rebuild it into a standby after confirming procedures.

## 28. Pre-Restore Compatibility Checklist

### 28.1. PostgreSQL

- [ ] Matches the backup's major version.
- [ ] Minor version recorded and compatible binary selected.
- [ ] `PG_VERSION` verified.
- [ ] System identifier/catalog version checked.
- [ ] Block size/WAL block size/WAL segment size checked.
- [ ] Checksum state confirmed.
- [ ] `pg_resetwal` not used to force startup or change versions.

### 28.2. Platform

- [ ] OS/CPU architecture/endianness compatible.
- [ ] PostgreSQL build and ABI compatible.
- [ ] Filesystem supports required permissions/symlinks.
- [ ] Tablespace and WAL mount points ready.
- [ ] Sufficient disk, memory, CPU, file descriptors, and shared memory.
- [ ] Storage flush/durability semantics verified.

### 28.3. Dependencies

- [ ] Extension packages/libraries installed for right version/architecture.
- [ ] Shared preload libraries available.
- [ ] Locale/libc/ICU versions cross-checked.
- [ ] Collation mismatches addressed with a `REINDEX` plan.
- [ ] FDW drivers/remote services available.
- [ ] SSL certificates, private keys, KMS keys, and secrets ready.
- [ ] DNS, network, firewall, and `pg_hba.conf` configured for target host.

### 28.4. Backup/WAL

- [ ] Base backup verified.
- [ ] Continuous WAL archive from backup to target.
- [ ] Timeline history files complete.
- [ ] Backup manifest/metadata preserved.
- [ ] Incremental chain complete if using incremental backups.
- [ ] Tablespaces backed up/mapped.
- [ ] Backup has a passing restore test.

### 28.5. Cutover/DR

- [ ] Old primary fenced.
- [ ] RPO/RTO understood and documented.
- [ ] Recovery target verified.
- [ ] Business validation passed.
- [ ] Monitoring/archiving/backups active on new node.
- [ ] Standby rebuilt or clear plan in place.
- [ ] Endpoints/application connections switched accurately.
- [ ] Incident notes and rollback/rebuild plan prepared.

## 29. Hands-On Exercises: Physical Recovery and Compatibility

Exercises use a PostgreSQL lab or simulated scenarios. Never run restore/overwrite/`pg_resetwal` in production just for practice. For version-dependent questions, consult the documentation for the major version you are studying.

### Exercise 1 — Physical vs. Logical

Compare physical backup and logical backup across scope, version compatibility, restore speed, and ability to select a single table.

### Exercise 2 — Base Backup

Explain what a base backup is and why physical restore normally recovers the entire cluster.

### Exercise 3 — WAL Requirement

A base backup is copied while the application is still writing data. Why is WAL needed to bring the copy into a consistent state?

### Exercise 4 — Copying a Running PGDATA

A DBA uses `cp -a` to copy PGDATA while PostgreSQL is running. List at least four reasons the backup may be inconsistent.

### Exercise 5 — pg_basebackup

Write a command to create a plain-format backup from a primary, stream WAL, and display progress. Explain the flags.

### Exercise 6 — WAL Methods

Compare `-X stream`, `-X fetch`, and `-X none`. When can `fetch` fail due to WAL recycling?

### Exercise 7 — Replication Permissions

What privileges does the backup role need? What connection type must `pg_hba.conf` allow?

### Exercise 8 — Backup Slot

Explain `-C` and `-S` in `pg_basebackup`. What is the disk risk if a consumer stops using the slot for a long time?

### Exercise 9 — Standby Configuration

A backup will be used as a standby. What files/settings does `-R` create on PostgreSQL 12+?

### Exercise 10 — Standalone PITR

Why should you avoid accidentally leaving `standby.signal` when the goal is restoring to a standalone server at a target?

### Exercise 11 — Tablespace Mapping

A source tablespace is at `/fast/pgdata`, while the destination is `/mnt/nvme/ts1`. Write a `-T` example and explain what must be done with mounts/permissions.

### Exercise 12 — Backup Manifest

What kind of information does `backup_manifest` contain? What does `pg_verifybackup` check?

### Exercise 13 — Verification vs. Restore Test

A backup passes `pg_verifybackup`, yet the target host lacks an extension library. Why might it still fail to start?

### Exercise 14 — Cold Backup

Write the sequence for a clean shutdown, copying PGDATA/tablespaces, and restarting. What metadata must be preserved?

### Exercise 15 — Backup API

Describe the roles of `pg_backup_start` and `pg_backup_stop`. Why does calling these two functions without copying files not produce a backup?

### Exercise 16 — Storage Snapshots

PGDATA, WAL, and tablespaces reside on three separate volumes. Why can snapshotting the three volumes at three different moments be inconsistent?

### Exercise 17 — Incremental Backup

What incremental backup feature did PostgreSQL 17 introduce? What is the role of `pg_combinebackup`?

### Exercise 18 — Incremental Chain

Base backup + incremental 1 + incremental 2. If incremental 1 is lost, can incremental 2 be arbitrarily combined with the base backup? Explain.

### Exercise 19 — archive_command

Write a simple `archive_command` example and explain exit code 0 vs. non-zero. Why do production commands need idempotency and atomic publishing?

### Exercise 20 — WAL Continuity

A WAL segment in the middle of the archive is lost while later segments remain. Can PITR replay across the gap?

### Exercise 21 — Timeline

A standby is promoted. What does the new timeline mean and why must `.history` files be kept?

### Exercise 22 — Recovery Signals

Distinguish `recovery.signal` and `standby.signal`. What mechanism did PostgreSQL versions prior to 12 use?

### Exercise 23 — restore_command

Explain `%f` and `%p` in `restore_command`. What exit code should the command return when a WAL file does not exist?

### Exercise 24 — Recovery Target Time

Write a PITR config targeting a timestamp with timezone and setting `recovery_target_action='pause'`. Why is the timezone important?

### Exercise 25 — Restore Point

Write SQL to create a restore point named `before_release`. State the WAL requirements needed to recover to that restore point.

### Exercise 26 — Promote

Write the SQL command to promote a standby and explain why the old primary must be fenced first.

### Exercise 27 — Split Brain

Two nodes both accept writes after failover. Why cannot physical WAL branches merge automatically? Design a fencing mechanism.

### Exercise 28 — pg_rewind

List the main prerequisites of `pg_rewind`. Why does enabling `wal_log_hints` after divergence fail to compensate for older WAL?

### Exercise 29 — Rebuilding a Standby

When should you re-run `pg_basebackup` instead of `pg_rewind`? List missing WAL or incompatibility scenarios.

### Exercise 30 — Major Version Mismatch

A PostgreSQL 16 base backup is started with PostgreSQL 17. Why is this not a valid major upgrade?

### Exercise 31 — Minor Version

Explain why minor releases within the same major preserve data format, yet primary/standby minor versions should still be kept aligned per version support.

### Exercise 32 — PG_VERSION

Read the `PG_VERSION` file in a backup. What does it tell you and what does it not tell you?

### Exercise 33 — System Identifier

Use `pg_controldata` to find the Database system identifier. Why must you never edit the identifier to force a standby to join a primary?

### Exercise 34 — Block Size

A cluster was initialized with 8 KB `BLCKSZ`, while the target binary uses a different build block size. Why is physical restore incompatible?

### Exercise 35 — WAL Segment Size

Describe how to check `Bytes per WAL segment`. Why should you never mix WAL from another cluster just because segment filenames look identical?

### Exercise 36 — Architecture

A team wants to copy physical PGDATA from x86_64 Linux to ARM64 Linux. List the risks and safe migration approaches.

### Exercise 37 — Cross-OS

Why is a physical backup not a portable format between Linux and Windows? When is logical dump/restore more appropriate?

### Exercise 38 — Tablespaces

A tablespace outside PGDATA is missing during restore. What errors might the server encounter? Write a query listing tablespace names and locations.

### Exercise 39 — Configs Outside PGDATA

List at least five external files/settings to inventory before restore and explain why physical backups do not always contain them.

### Exercise 40 — Extension Binaries

The catalog has an extension, yet the shared library is missing on the target host. What can happen at server startup or when calling a function?

### Exercise 41 — shared_preload_libraries

An extension in `shared_preload_libraries` is not installed yet. Why might PostgreSQL fail to start? How should you handle it?

### Exercise 42 — Collation Mismatch

Restoring a cluster onto an OS with a different ICU/libc version. Why might text B-tree indexes need `REINDEX`? Why does `REFRESH COLLATION VERSION` not automatically rebuild indexes?

### Exercise 43 — Encoding

Can you change database encoding via physical restore onto a new binary? State the migration approach.

### Exercise 44 — Checksum State

A backup has data checksums on, and the target host has a matching binary, yet offline verification reports errors. List investigation steps and explain why you should not disable checksums to hide errors.

### Exercise 45 — pg_verifybackup

A backup manifest passes, yet the restore test fails due to a missing tablespace. Why is verification insufficient to prove DR readiness?

### Exercise 46 — pg_amcheck

Distinguish `pg_amcheck` from `pg_checksums`. Which layer does each tool check?

### Exercise 47 — RPO/RTO

A 5 TB cluster has weekly base backups and continuous WAL archiving. Which factors determine RPO and RTO?

### Exercise 48 — WAL Archive Gap

An archive has every segment except one missing in the middle of the chain. Design a process to detect gaps before an incident occurs.

### Exercise 49 — Restore Test

Design a monthly restore drill covering backup verification, restore, WAL replay, application validation, timing measurements, and RPO/RTO reporting.

### Exercise 50 — Capstone: DR Plan for a Production System

A 4 TB PostgreSQL system has a primary/standby pair, three tablespaces on separate volumes, PostGIS and an internal extension, WAL archiving to object storage, ICU collations, daily incremental backups, and weekly full backups. One day the primary volume fails, the standby lags by 15 minutes, and the DR site runs a newer OS minor release.

**Requirements:**

1. Select the node/backup source and determine achievable RPO.
2. Verify the base/incremental backup chain and use `pg_combinebackup` properly.
3. Verify major/minor versions, architecture, block size, WAL segment size, and checksum state.
4. Plan restoration of all three tablespaces and external configs/keys.
5. Install PostGIS/extension libraries matching exact version/architecture.
6. Check ICU collation versions and plan `REINDEX`.
7. Recover the WAL archive on the right timeline, verify history files, and replay to target.
8. Determine when the standby can be promoted versus when restoring a backup is necessary.
9. Plan fencing of the old primary and preventing split brain.
10. Verify data integrity via manifest, `pg_checksums`, `pg_amcheck`, and business queries.
11. Verify archiving/replication/monitoring after cutover.
12. Measure actual RTO, update runbooks, and propose improvements to backup cadence/storage.

**Pass Criteria:** Demonstrate compatibility across the physical backup, WAL chain, binary/platform, tablespaces, and external dependencies; select a verifiable recovery path without exceeding agreed RPO data loss.

## 30. Frequently Asked Questions

### 30.1. Can a physical backup back up a single database separately?

Normally no. Physical backups operate at the cluster level. If you only need one database or table, use logical backup/restore.

### 30.2. Can PGDATA be copied while the server is running?

Not arbitrarily. Use `pg_basebackup`, the backup API + consistent snapshot/WAL, or perform a clean shutdown before a cold copy.

### 30.3. Why does a base backup need WAL?

Data files are copied over a time window and may reflect multiple states. WAL enables recovery to bring them to a single consistent state.

### 30.4. Does pg_basebackup copy WAL?

It can, depending on the WAL method. `-X stream` streams WAL during backup; `-X fetch` retrieves it at the end; `-X none` requires an external WAL process to guarantee consistency.

### 30.5. Does pg_basebackup create a standby?

`-R` can be used to create `standby.signal` and recovery settings. If you want standalone PITR, choose the appropriate recovery mode and avoid leaving a standby signal unintentionally.

### 30.6. Does pg_verifybackup replace a restore test?

No. It verifies backup files/manifest/WAL per version capabilities, yet it does not prove extensions, configs, tablespace paths, and the application will work after restore.

### 30.7. Can a physical backup be restored to a newer major version?

Not by starting directly with the newer major binary. Use `pg_upgrade`, logical dump/restore, or logical replication migration.

### 30.8. Can an older minor backup be restored with a newer minor binary?

Minor releases within the same major are designed to preserve data format compatibility, yet follow release notes and use official update procedures. For physical replication, keeping primary/standby minor versions aligned is the safest choice per version support.

### 30.9. Can physical backups be moved between Linux and Windows?

Do not treat physical files as cross-OS portable. Use logical migration or a method supported for the target platform.

### 30.10. Do physical backups include extension binaries?

No. Catalog objects may be preserved, yet shared libraries/packages and system dependencies must be installed on the target host.

### 30.11. Are tablespaces inside PGDATA?

Metadata/links live under PGDATA, while actual data usually resides at separate paths. Both tablespace targets must be backed up and restored.

### 30.12. Does a WAL archive replace a replication slot?

No. An archive is a WAL store for recovery/PITR; a slot retains WAL on the primary for a consumer. The two mechanisms serve different purposes.

### 30.13. Can PITR recover a single table?

Physical PITR recovers the entire cluster to a target. If you only want one table back, restore onto a temporary cluster and logically export/import that table.

### 30.14. Why are timeline history files needed?

They describe WAL branches after promotion/failover. Missing history can prevent recovery from selecting the right timeline.

### 30.15. When should pg_rewind be used?

When an old node diverged after failover and meets prerequisites to resynchronize onto the new timeline. If WAL/checksum/hint prerequisites are unmet, build a new standby via base backup.

### 30.16. Can two copies from the same base backup be started simultaneously?

Separate clones can run for testing, yet never allow both to act as primaries in the same write system. Network/identity must be isolated to prevent split brain.

### 30.17. Can checksum state be enabled for a single database?

No. Data checksums are a cluster-wide setting.

### 30.18. If collation versions differ, will the database fail to start?

Not necessarily. The server may start, yet collation-dependent indexes may require `REINDEX` to match the new ordering. Address warnings before opening traffic.

### 30.19. Does pg_checksums run on a live server?

No. The tool requires a cleanly shut down cluster.

### 30.20. Is pg_resetwal a restore tool?

No. It is a last-resort rescue tool when WAL/control state is corrupted. It can compromise consistency and does not replace backups/WAL recovery.

### 30.21. Does a passing backup manifest mean zero page corruption?

No. The manifest validates backup files against manifest checksums. Data page checksums are a separate layer requiring offline checks and restore tests.

### 30.22. Is REINDEX always required after restore?

Not by default. Only run `REINDEX` when there is a collation version mismatch, confirmed index corruption, or a specific technical/performance reason.

### 30.23. Can tablespace paths be changed after restore?

They can be mapped during backup/restore or via supported DDL/storage migration procedures. Ensure links, ownership, and data files match paths before starting.

### 30.24. Does a 15-minute standby lag mean 15 minutes of data loss?

You cannot conclude that from lag time alone. Check received/replay LSNs, WAL generation, and synchronous/asynchronous replication policies to determine actual RPO.

### 30.25. Is a new backup needed after PITR?

Yes. After promotion/PITR, the cluster enters a new timeline. Create a fresh base backup and begin archiving WAL on the new timeline for a clean recovery chain.

### 30.26. Can old WAL archives be deleted after a restore?

Only when retention/catalogs confirm no remaining backup, PITR target, or standby needs them. Keep timeline history and WAL tied to retained backups.

### 30.27. Why can a restore be slow even with local backups?

Due to storage throughput, multiple tablespaces, WAL replay volume, incremental combining, extension startup, checksum/validation scans, cold caches, or filesystem layout.

### 30.28. How often should restore tests run?

Frequency depends on RPO/RTO and criticality. What matters is running them frequently enough to prove backup chains, keys, dependencies, and runbooks still work after system changes.

### 30.29. Can logical dumps completely replace physical backups?

Not necessarily. Logical dumps are useful for migrations/selective restores, yet they can be slow and do not provide the same cluster-wide PITR capabilities. Critical systems often require both physical and logical backups.

### 30.30. What determines a successful physical recovery?

A consistent base backup, complete WAL/timeline, compatible binary/platform, complete tablespaces/configs/dependencies, correct permissions, and post-restore validation.

## 31. Official PostgreSQL Documentation

The links below point to current documentation. Always choose the exact major version of source/target because options, recovery settings, and backup features change across versions:

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archiving, and PITR.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating physical base backups, WAL methods, standbys, and tablespace mapping.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): verifying backup manifests and files.
- [pg_combinebackup](https://www.postgresql.org/docs/current/app-pgcombinebackup.html): combining incremental backups.
- [Backup Manifest Format](https://www.postgresql.org/docs/current/backup-manifest-format.html): backup metadata and checksums.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication and standby operation.
- [Recovery Configuration](https://www.postgresql.org/docs/current/recovery-config.html): restore commands, recovery signals, target time/LSN/timeline, and recovery actions.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): resynchronizing a diverged node after failover.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html): inspecting control information and cluster metadata.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): verifying/enabling/disabling data page checksums offline.
- [pg_amcheck](https://www.postgresql.org/docs/current/app-pgamcheck.html): checking heap/index structures.
- [pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): reading and analyzing WAL records.
- [pg_archivecleanup](https://www.postgresql.org/docs/current/pgarchivecleanup.html): cleaning up WAL archives per recovery requirements.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): upgrading major versions via supported methods.
- [CREATE TABLESPACE](https://www.postgresql.org/docs/current/sql-createtablespace.html): managing tablespace paths.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html): locale providers and collation versions.
- [ALTER COLLATION](https://www.postgresql.org/docs/current/sql-altercollation.html): refreshing collation version metadata.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): archive, replication, and database statistics.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL/archiving configuration.

## 32. Summary

PostgreSQL physical recovery is a process comprising **base backup + WAL + binary/platform compatibility + external dependencies + validation**. A single file copy is insufficient; recovery requires the right WAL chain, timeline, and compatible environment.

| Component | Role in Recovery |
| --- | --- |
| Base backup | Provides a consistent foundation of data files |
| WAL archive | Replays changes after the base backup to the recovery target |
| Timeline history | Identifies WAL branches after promotion/failover |
| PostgreSQL binary/build | Reads exact data/catalog/WAL formats |
| Tablespaces | Provides relation files stored outside PGDATA |
| Config/extensions/keys | Allows the server to start and run on the target host |
| Collation/locale | Ensures proper indexes and text ordering |
| Verification/restore test | Proves the backup chain can actually be recovered |

Before restoring, verify major version, platform, block/WAL parameters, system identifier, tablespaces, extensions, collations, and WAL continuity. After restoring, verify recovery state, business data, application connectivity, archiving/replication, and performance.

**A backup is only trustworthy when it can be restored.** Run periodic restore/PITR drills, measure RPO/RTO, maintain WAL/timeline history per retention, and update runbooks whenever versions, OS, extensions, storage, or topology change.
