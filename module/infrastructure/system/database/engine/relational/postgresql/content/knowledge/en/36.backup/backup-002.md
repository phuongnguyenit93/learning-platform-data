# Distinguishing Logical Backup, Physical Backup, and Storage Snapshots in PostgreSQL

## 1. Three Backup Approaches Solving Different Problems

When building a backup strategy for PostgreSQL, three approaches are commonly discussed:

- **Logical backup:** exports schemas and data into a logical representation such as SQL or a `pg_dump` archive.
- **Physical backup:** copies PostgreSQL data files at the cluster level, typically using `pg_basebackup` or a compatible physical backup tool.
- **Storage snapshot:** captures the state of a volume, filesystem, or block storage at a point in time using storage platform features.

These three approaches can complement each other, but they differ in scope, consistency, restore speed, point-in-time recovery capability, portability, and restoration granularity.

For example:

- You only need to recover a single accidentally dropped table: a logical backup is usually more convenient.
- You need to rebuild the entire PostgreSQL cluster after a host failure: a physical backup is usually more appropriate.
- You need to quickly create a volume copy for testing or disaster recovery: a storage snapshot can be useful if created under a procedure that guarantees consistency.
- You need to restore the database to 10:32 AM right before a faulty transaction committed: you need a valid base backup and a continuous WAL chain to perform Point-in-Time Recovery (PITR).

No single option automatically satisfies every scenario.

```text
                 PostgreSQL cluster
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
       Logical dump   Physical     Storage
       pg_dump        backup       snapshot
       pg_dumpall     pg_basebackup volume / filesystem
             |           |           |
             v           v           v
       SQL / archive  Data files   Block-level image
       of objects     + WAL        at a point in time
             |           |           |
             +-----------+-----------+
                         |
                         v
               Restore and verify
                         |
              +----------+----------+
              |          |          |
              v          v          v
            Object     Whole       Fast clone /
            recovery   cluster     storage recovery
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain how logical backups, physical backups, and storage snapshots differ.
2. Choose a backup type based on recovery scope and RPO/RTO targets.
3. Use `pg_dump` to back up a single database.
4. Distinguish between plain SQL, custom, directory, and tar dump formats.
5. Use `pg_restore` to inspect contents and restore archives.
6. Use `pg_dumpall` to back up multiple databases and global objects.
7. Understand why roles and tablespaces must be protected separately when using `pg_dump`.
8. Explain how transaction snapshots guarantee the consistency of a logical dump.
9. Use `pg_basebackup` to create a physical base backup.
10. Distinguish a base backup from a WAL archive.
11. Combine a base backup and WAL to perform PITR.
12. Understand why physical backups are tied to PostgreSQL major versions and compatible environments.
13. Explain copy-on-write storage snapshots and crash consistency.
14. Distinguish crash-consistent, filesystem-consistent, and application-consistent snapshots.
15. Identify risks when `PGDATA`, tablespaces, and WAL reside on multiple volumes.
16. Understand the role of the PostgreSQL backup API when taking online snapshots.
17. Distinguish storage snapshots from MVCC snapshots and replication standbys.
18. Design backup retention, encryption, offsite copies, and immutable storage.
19. Verify backups using manifests, checksums, and restore drills.
20. Formulate a combined strategy using logical backups, physical backups, WAL archiving, and storage snapshots.

## 3. What Is a Logical Backup?

A logical backup stores database structure and contents as logical objects: schemas, tables, sequences, views, functions, constraints, indexes, data, and other objects supported by the tool.

In PostgreSQL, the common tools are:

- `pg_dump`: backs up a single database.
- `pg_dumpall`: backs up all databases in a cluster in SQL text format, and can also export global objects.
- `pg_restore`: restores archive formats created by `pg_dump`.
- `psql`: executes plain SQL dumps.

### 3.1. A Logical Dump Is Not a Copy of Database Files

A dump may contain statements to create tables and INSERT/COPY data, or archive entries representing objects. When restoring, PostgreSQL recreates the objects in a target database.

For example, a logical dump of a table does not copy raw page layouts, heap tuple headers, index pages, or transaction status files. PostgreSQL rebuilds the data and indexes from the logical representation.

### 3.2. Scope of `pg_dump`

`pg_dump` operates on one database at a time. It does not automatically back up cluster-wide global objects such as roles and tablespaces.

If the database uses dedicated roles, ownership, or grants, ensure the corresponding roles exist upon restore. You can use `pg_dumpall --globals-only` to export global definitions.

### 3.3. When Is a Logical Backup Suitable?

- Recovering a single database or a subset of objects.
- Migrating data across PostgreSQL major versions in a compatible direction.
- Exporting a schema or selected tables.
- Creating a dataset for testing, staging, or data migration.
- Storing an inspectable dump that can be archived and processed by other tools.
- Recovering a table after a logical error by restoring into a temporary database and copying the needed object.

### 3.4. What Logical Dumps Do Not Automatically Include

Depending on commands and options, watch out for:

- Cluster-level roles and tablespaces.
- PostgreSQL configuration files placed outside the data directory.
- TLS certificates, secrets, key material, and credentials.
- Operating system extension binaries/shared libraries.
- Cron jobs, scripts, external services, and object storage.
- Data outside the database that the application needs to function.

Backing up a database does not mean backing up the entire application system.

## 4. Creating Logical Backups with `pg_dump`

### 4.1. Plain SQL Format

```bash
pg_dump \
  --host=db.example.internal \
  --port=5432 \
  --username=backup_user \
  --format=plain \
  --file=appdb-2026-11-14.sql \
  appdb
```

Plain format creates a SQL text file that can be read and executed using `psql`.

Restore:

```bash
createdb --host=db-restore.internal --username=restore_admin appdb_restore

psql \
  --host=db-restore.internal \
  --username=restore_admin \
  --dbname=appdb_restore \
  --file=appdb-2026-11-14.sql
```

Advantages:

- SQL contents are human-readable.
- Easy to process with text tools where appropriate.
- Does not require `pg_restore`; uses `psql`.

Limitations:

- File size can be large.
- Restores generally run sequentially following the script, making parallel restore difficult compared to custom/directory archives.
- Object selection and restore control are less flexible than with archive formats.

### 4.2. Custom Format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=custom \
  --file=appdb-2026-11-14.dump \
  appdb
```

Custom format (`-Fc`) is a popular archive format for single-database backups. It supports compression via `pg_dump`, listing contents, and selective object restoration.

List archive entries:

```bash
pg_restore --list appdb-2026-11-14.dump
```

Restore:

```bash
createdb --host=db-restore.internal --username=restore_admin appdb_restore

pg_restore \
  --host=db-restore.internal \
  --username=restore_admin \
  --dbname=appdb_restore \
  --verbose \
  appdb-2026-11-14.dump
```

### 4.3. Directory Format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=directory \
  --jobs=4 \
  --file=appdb-2026-11-14.dir \
  appdb
```

Directory format (`-Fd`) stores the archive as multiple files inside a directory and supports parallel dumps. Protect the entire directory as a single backup unit; do not copy only a few files inside it.

### 4.4. Tar Format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=tar \
  --file=appdb-2026-11-14.tar \
  appdb
```

Tar format produces a tar archive. Parallel restore support and certain other capabilities differ from custom/directory formats; consult the documentation for the version in use.

### 4.5. Format Comparison

| Format | Restore Method | Parallel Dump | Parallel Restore | Strengths |
| --- | --- | --- | --- | --- |
| Plain (-Fp) | psql | No | Not via pg_restore | SQL text, easy to inspect |
| Custom (-Fc) | pg_restore | No | Yes | Flexible, object selection |
| Directory (-Fd) | pg_restore | Yes | Yes | Parallel dump/restore |
| Tar (-Ft) | pg_restore | No | Limited compared to custom/directory | Tar archive |

Exact capabilities depend on PostgreSQL version and options. Check `pg_dump --help` and `pg_restore --help` for your deployed binaries.

## 5. Selective Restoration with `pg_restore`

### 5.1. Inspecting Contents Before Restoring

```bash
pg_restore --list appdb-2026-11-14.dump
```

The output is the archive's TOC (table of contents). You can save the TOC to a file, edit the list of entries, and pass `--use-list` for selective restoration.

### 5.2. Restoring a Single Schema

```bash
pg_restore \
  --dbname=appdb_restore \
  --schema=reporting \
  --verbose \
  appdb-2026-11-14.dump
```

### 5.3. Restoring a Single Table

```bash
pg_restore \
  --dbname=appdb_restore \
  --table=public.orders \
  --verbose \
  appdb-2026-11-14.dump
```

Selective restores may miss dependencies such as types, functions, sequences, or referenced tables. Never assume a single table archive entry is self-contained with every object required by the application.

### 5.4. Clean Restore

`--clean` drops objects before recreating them. This option can destroy data in the target database:

```bash
pg_restore \
  --clean \
  --if-exists \
  --dbname=appdb_restore \
  appdb-2026-11-14.dump
```

Run only against a clearly verified target database, typically a dedicated restore database. Do not use on a production database serving traffic without an approved change/recovery procedure.

### 5.5. Ownership and Privileges

When restoring into a different environment, you may need to map ownership/privileges:

```bash
pg_restore \
  --no-owner \
  --no-acl \
  --dbname=appdb_restore \
  appdb-2026-11-14.dump
```

`--no-owner` and `--no-acl` alter restore semantics. If access permissions must be preserved, create the corresponding roles/grants or use an appropriate restore method. Do not bypass the security model merely to make the restore command succeed.

## 6. `pg_dump` and Data Consistency

### 6.1. Logical Dumps Use a Consistent Snapshot

`pg_dump` reads the database using a consistent transaction snapshot. During the dump, other transactions can continue reading and writing; the dump reflects the data state at the snapshot it took, rather than arbitrarily mixing timestamps across tables.

### 6.2. A Snapshot Does Not Mean Every DDL Is Safe Concurrently

`pg_dump` acquires necessary locks on objects. Certain DDL statements can conflict with those locks and cause the dump to fail. Coordinate schema migrations with backup schedules.

### 6.3. Parallel Dumps

Directory format can use `--jobs`. Worker connections must use a synchronized snapshot to export the same logical state. Use matching client/server versions and ensure required connection/read permissions.

### 6.4. A Transaction Snapshot Does Not Freeze the Database

Dumps do not lock the entire database to block all writes. They rely on an MVCC snapshot; changes committed after the snapshot generally do not appear in that dump.

### 6.5. A Successful Dump Does Not Prove a Successful Restore

Files may exist yet be incomplete, corrupted, have wrong permissions, contain uncreated object dependencies, or fail to restore into the target version. You must run restore tests.

## 7. Backing Up Global Objects with `pg_dumpall`

### 7.1. What Are Global Objects?

Some objects are cluster-scoped rather than belonging to an individual database:

- Roles and role memberships.
- Tablespaces.
- Role privilege settings/attributes supported in dumps.

If you only run `pg_dump appdb`, these objects are not automatically included.

### 7.2. Exporting Global Objects

```bash
pg_dumpall \
  --host=db.example.internal \
  --username=backup_admin \
  --globals-only \
  --file=cluster-globals.sql
```

Restore:

```bash
psql \
  --host=db-restore.internal \
  --username=postgres \
  --dbname=postgres \
  --file=cluster-globals.sql
```

Execute in the restore environment with appropriate privileges. Tablespaces may depend on filesystem paths, mount points, and ownership on the target host.

### 7.3. Exporting the Entire Cluster

```bash
pg_dumpall \
  --host=db.example.internal \
  --username=backup_admin \
  --file=all-databases.sql
```

`pg_dumpall` generates a SQL script for databases and global objects. Restoration typically uses `psql` with sufficiently high privileges. This tool lacks `pg_dump`'s custom archive format and does not provide the same level of parallel restore.

### 7.4. When Is `pg_dumpall` Needed?

- Saving roles/tablespaces separately.
- Generating a cluster-wide SQL script.
- Auditing and recreating global object definitions.

A practical pattern is storing per-database logical dumps alongside a protected and tested globals dump.

## 8. What Is a Physical Backup?

A physical backup copies the physical files PostgreSQL needs to reopen a cluster: data files, control information, required WAL, and associated tablespace files.

Unlike logical dumps, physical backups preserve PostgreSQL's cluster-level storage layout. Restoring generally means bringing the cluster back to a startable state using a compatible PostgreSQL installation.

### 8.1. Physical Backups Usually Cover the Entire Cluster

A physical base backup typically contains all databases in the cluster, along with system catalogs, roles, and database files. It cannot directly select a single table to restore.

### 8.2. Physical Backups Require Compatibility

A physical data directory is tied to the PostgreSQL major version and platform/build compatibility requirements. Do not take a PostgreSQL 15 data directory and assume PostgreSQL 16 can start directly from it.

Minor releases within the same major version generally maintain physical compatibility per PostgreSQL policy, though you must still verify versions, extensions, OS/architecture, filesystems, and vendor procedures.

### 8.3. When Is a Physical Backup Suitable?

- Recovering an entire cluster after host/volume loss.
- Building a standby or replica.
- Fast recovery of large datasets.
- Combining with a WAL archive for PITR.
- Disaster recovery requiring cluster-state reconstruction.

### 8.4. Limitations

- Harder to recover an individual table: usually requires restoring a temporary cluster/database and then using `pg_dump`/SQL to extract the object.
- Not as convenient for migrating across major versions as logical dumps.
- Depends on compatible files, tablespaces, WAL, extension binaries, and runtime environment.
- The backup directory must be kept intact; missing a part can prevent the cluster from starting.

## 9. Creating a Physical Base Backup with `pg_basebackup`

`pg_basebackup` is a PostgreSQL tool that creates a base backup from a running server via the replication protocol.

Example:

```bash
pg_basebackup \
  --host=db.example.internal \
  --port=5432 \
  --username=backup_user \
  --pgdata=/backups/pg-base-2026-11-14 \
  --format=plain \
  --wal-method=stream \
  --progress \
  --verbose
```

Corresponding options:

- `--pgdata` (`-D`): destination directory.
- `--format=plain` (`-Fp`): writes physical file tree.
- `--wal-method=stream` (`-X stream`): streams WAL during the backup.
- `--progress` (`-P`): displays progress.
- `--verbose` (`-v`): increases log verbosity.

### 9.1. Server-Side Requirements

Depending on deployment, you need:

- A role with `REPLICATION` privilege or appropriate permissions.
- Replication connections allowed in `pg_hba.conf`.
- Sufficient `max_wal_senders`.
- Adequate WAL settings and retention to complete the backup.
- Suitable destination capacity and network throughput.

Do not use a superuser as the backup credential if a dedicated replication role suffices.

### 9.2. WAL Method

`pg_basebackup` must ensure the backup contains the WAL required to bring data files to a consistent state. WAL method modes and defaults can vary by version; read `pg_basebackup --help` on the client in use.

`-X stream` streams WAL concurrently with the base backup, usually avoiding the need for the server to retain WAL until the end of the copy. It does not replace long-term WAL archiving for PITR.

### 9.3. Directory or Tar Output

`pg_basebackup` can produce a plain directory or tar output depending on options/version. Tar format can simplify transport, but restoration must extract the structure properly and handle tablespaces correctly.

### 9.4. The `-R` Option

`-R`/`--write-recovery-conf` generates the configuration needed for the backup to act as a standby, including the appropriate signal/configuration. Use it only when building a standby. A base backup meant for restoring an independent primary should not accidentally carry unwanted replica connection settings.

## 10. Base Backup vs. WAL Archive

A base backup is the starting point for cluster recovery. A WAL archive holds the sequence of changes generated during or after the timeframe associated with the base backup.

### 10.1. What Is WAL?

The Write-Ahead Log records database changes following write-ahead logging rules. PostgreSQL uses WAL for crash recovery and replication. With continuous WAL from the required base backup point to the target recovery point, changes can be replayed to advance the cluster to the desired moment.

### 10.2. WAL Archive

Archiving configuration typically includes:

- `archive_mode` enabled as required.
- `archive_command` or `archive_library` depending on version/platform.
- A destination independent of primary storage.
- Monitoring for archive failures, backlog, and capacity.
- Retention that does not delete WAL still needed by base backups or standbys.

Illustrative configuration example:

```conf
archive_mode = on
archive_command = 'archive-tool publish "%p" "%f"'
```

`archive-tool` is a placeholder for the deployment tool. The actual command must durably store the WAL segment and return success only after the archive is properly published. Do not run this example string verbatim.

### 10.3. A WAL Archive Is Not a Standalone Backup

Having WAL alone without a matching base backup is insufficient to rebuild a cluster from scratch. Conversely, a base backup missing required WAL may fail to restore to a consistency point or recovery target.

### 10.4. Keeping the WAL Chain Continuous

One missing segment can stop PITR from advancing past the needed timeframe. Archive monitoring must detect gaps, failed uploads, and WAL backlogs.

## 11. Point-in-Time Recovery (PITR)

PITR lets you restore a cluster to a point in history, such as right before a user ran an accidental DELETE.

Requirements:

1. A valid base backup.
2. Continuous WAL from the required base backup point to the recovery target.
3. Restore configuration so PostgreSQL reads the WAL archive.
4. An accurately specified recovery target.
5. A promotion/validation procedure after replay.

### 11.1. Recovery Concept

```text
Base backup at T0
      |
      v
Restore data directory
      |
      v
Read archived WAL segments
      |
      v
Replay transactions in order
      |
      +---- Stop at target time / LSN / XID
      |
      v
Promote recovered cluster
      |
      v
Validate application data
```

### 11.2. Recovery Configuration

Example for PostgreSQL versions using a recovery signal file:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_action = 'pause'
```

Create `recovery.signal` in the data directory when preparing PITR according to your version's procedure. Recovery settings and file semantics vary across major versions; follow the corresponding documentation.

### 11.3. Target Time Needs an Explicit Timezone

When using `recovery_target_time`, specify the exact timezone and timestamp. Synchronizing clocks across systems, logs, and applications aids investigation. You can target by LSN or transaction marker when higher precision is needed.

### 11.4. PITR Does Not Automatically Pick the Right Business State

PostgreSQL can pause replay at the target time, but the DBA must still inspect the data and confirm the target precedes the erroneous transaction. Recovery may include other transactions committed prior to that point.

### 11.5. PITR Produces a Recovered Cluster

Usually you restore into an isolated environment, inspect the data, and then decide how to bring data back into production. Do not automatically overwrite the active cluster the moment recovery completes.

## 12. What Is a Storage Snapshot?

A storage snapshot is a point-in-time image of a volume, filesystem, or block device provided by the storage layer.

Platform examples:

- LVM snapshots.
- ZFS snapshots.
- SAN/storage-array snapshots.
- Cloud block-volume snapshots.
- VM disk snapshots.
- Storage systems with copy-on-write or redirect-on-write.

### 12.1. Copy-on-Write

Some snapshot systems do not copy all data immediately. They keep metadata/blocks referencing the initial state, then record changed blocks over time.

This makes snapshot creation fast and saves initial space. As data changes heavily or snapshots are kept long, storage costs can grow.

### 12.2. Snapshots Are Not Logical Dumps

A snapshot records storage block state. It has no awareness of tables, schemas, roles, SQL objects, or business meaning. Restoring a single table from a snapshot usually requires restoring the volume/cluster into a temporary environment and then extracting data with SQL/logical tools.

### 12.3. Snapshots Are Not Automatically Independent Backups

If a snapshot stays in the same storage account, region, credentials, or failure domain as the source data, a major outage or compromised account can affect both.

Copy/replicate snapshots to a different failure domain and apply appropriate retention/immutability.

### 12.4. Snapshots Do Not Automatically Provide PITR

A single snapshot represents one point in time. Recovering to a point between two snapshots requires a WAL archive or another replayable incremental/time-based mechanism.

## 13. Storage Snapshot Consistency

This is the most critical consideration when using snapshots with PostgreSQL.

### 13.1. Crash-Consistent Snapshot

A crash-consistent snapshot reflects storage state similar to a server losing power abruptly at a single moment. If the snapshot covers all necessary files and volumes consistently, PostgreSQL can use WAL for crash recovery on startup.

However, crash consistency depends on the storage provider and how snapshots are coordinated. A standalone snapshot of the data volume does not guarantee that separate WAL/tablespace volumes are at the exact same instant.

### 13.2. Filesystem-Consistent Snapshot

Filesystem-consistent means filesystem metadata and writes are flushed/synchronized according to the semantics of the filesystem/snapshot tool. This lowers filesystem-level inconsistency risk, but does not by itself prove that all PostgreSQL files across multiple volumes belong to the same database point-in-time.

### 13.3. Application-Consistent Snapshot

An application-consistent snapshot coordinates with the application/database to reach a consistent state per application procedures. For an online PostgreSQL filesystem backup, use the backup procedure/API appropriate to your major version and ensure required WAL is preserved.

### 13.4. Crash-Recoverability Does Not Mean PITR Readiness

A crash-consistent snapshot may allow a cluster to boot after a crash. PITR requires a base backup, the necessary WAL chain, and corresponding backup metadata. Do not conflate these two goals.

### 13.5. Simultaneous Multi-Volume Snapshots

If PostgreSQL uses:

- `PGDATA` on volume A.
- Tablespaces on volume B.
- `WAL`/`pg_wal` on volume C.

then you need a snapshot group/consistency group ensuring all volumes represent the same instant. Snapshotting volume A at 10:00, B at 10:02, and C at 10:05 can produce an inconsistent set of files.

### 13.6. Do Not Snapshot Only `PGDATA`

Tablespaces can reside outside `PGDATA`. Identify all tablespace paths, WAL locations, external configs, and dependencies. A partial snapshot can prevent the cluster from starting or lose objects.

## 14. Using the PostgreSQL Backup API with Online Snapshots

If a storage snapshot is taken while PostgreSQL is running, follow the filesystem backup procedure for your PostgreSQL major version.

PostgreSQL provides a backup API to inform the server that a physical backup is underway and mark when it finishes. Function names and semantics differ across major versions; newer releases use `pg_backup_start`/`pg_backup_stop`, while older versions had APIs named `pg_start_backup`/`pg_stop_backup`.

### 14.1. Conceptual Workflow

1. Verify storage and backup procedures support online snapshots.
2. Start backup mode using the version-appropriate API.
3. Take consistent snapshots of all relevant volumes.
4. End backup mode per the procedure.
5. Save metadata/backup label/tablespace map returned by the API if required by the workflow.
6. Ensure required WAL is archived and retained.
7. Create a manifest recording snapshot IDs, timestamps, volume mappings, database version, and WAL range.
8. Test restoring the snapshot in an isolated environment.

Do not write an online snapshot script relying solely on cloud provider snapshot commands while ignoring PostgreSQL backup semantics.

### 14.2. `pg_basebackup` Is Usually Safer for Common Cases

`pg_basebackup` handles the physical backup protocol and required WAL in a PostgreSQL-supported way. Unless you have specific storage snapshot requirements, it is usually a more controllable starting point.

### 14.3. Snapshotting When the Database Is Cleanly Stopped

Another option is:

1. Stop PostgreSQL with a clean shutdown.
2. Verify the server has stopped.
3. Snapshot all volumes and tablespaces.
4. Record configuration, version, and snapshot metadata.
5. Restart the server after the snapshot completes.

When the database is cleanly shut down and all files are fully snapshotted, the snapshot can serve as a physical copy. The trade-off is accepting downtime and coordinating all related components.

### 14.4. Do Not Arbitrarily Snapshot or Copy a Running Filesystem

Copying individual files inside `PGDATA` while the server is running without a supported backup method can produce an inconsistent copy. Do not treat `Copy-Item`, `cp -r`, or ordinary file sync as an online physical backup.

## 15. Comparing Logical, Physical, and Snapshot

| Criterion | Logical Backup | Physical Backup | Storage Snapshot |
| --- | --- | --- | --- |
| Data level | Objects and rows | Cluster data files | Storage blocks/volumes |
| PostgreSQL tool | `pg_dump`, `pg_dumpall` | `pg_basebackup`, backup tools | Storage provider/tool |
| Scope | One DB or object subset | Usually entire cluster | Volume/snapshot group |
| Single-table restore | More convenient | Usually requires temporary cluster restore | Usually requires temporary volume restore |
| Whole-cluster restore | Recreate objects via SQL/archive | Suitable | Suitable if consistent/complete |
| PITR | Not from a standalone dump | Yes when combined with WAL | Needs WAL or snapshot chain |
| Cross-major migration | Usually more flexible | Cannot restore directly across majors | Cannot restore directly across majors |
| Creation time | Depends on scanning/serializing data | Depends on copying volumes/data | Can be very fast |
| Restore time | Can be long due to recreating objects/indexes | Usually faster for large datasets | Can be fast if attach/clone is fast |
| Portability | Better at logical level | Version/platform dependent | Storage platform dependent |
| Content inspection | Readable plain SQL/TOC | Manifest/file validation | Provider metadata/checksum |
| Dependencies | Roles/extensions/config must be prepared | Compatible binaries/extensions/config | Volume mapping, WAL, config, backup procedure |

Do not infer a fixed restore speed from the table above. Dataset size, indexes, compression, networking, storage throughput, PostgreSQL version, and parallelism all affect results.

## 16. Distinguishing Storage Snapshots from MVCC Snapshots

Both terms use the word "snapshot" yet refer to completely different mechanisms.

### 16.1. MVCC Snapshot

An MVCC snapshot is transaction visibility information used to determine which transactions have committed and which tuple versions are visible. `pg_dump` uses a logical snapshot to read consistent data.

### 16.2. Storage Snapshot

A storage snapshot is the block/volume state at a point in time recorded by the storage system. It does not understand transaction visibility or schemas.

### 16.3. Example

Suppose a transaction transfers 100 million VND from account A to B:

1. UPDATE balance A.
2. UPDATE balance B.
3. COMMIT.

A logical dump reading via a consistent MVCC snapshot will see either the state before or after the transaction according to snapshot visibility.

A storage snapshot must consistently represent the entire storage state. If the snapshot is unsynchronized across volumes or taken in an unsupported state, WAL recovery and backup procedures are required to bring the cluster to a valid state.

### 16.4. A Snapshot Does Not Lock the Database

Taking a storage snapshot usually does not mean PostgreSQL stops writing. Copy-on-write snapshots persist while the database continues modifying blocks. Understand provider semantics and consistency groups.

## 17. Logical and Physical Backups in Migration

### 17.1. Logical Dumps for Migration

Logical dumps can be useful when moving to a newer PostgreSQL major version or another server/platform, provided object definitions, extensions, and data types are compatible.

General procedure:

1. Create the target cluster.
2. Install needed extensions at compatible versions.
3. Create roles/tablespaces or map ownership.
4. Restore schema/data.
5. Run `ANALYZE` and verify constraints/indexes.
6. Validate counts/checksums/business aggregates.
7. Cut over the application according to the cutover plan.

### 17.2. Physical Backups for Migration

Physical backups normally serve recovery/replication in compatible environments of the same major version. Do not use copying the data directory as a major-version upgrade method.

### 17.3. `pg_upgrade`

When upgrading a major version while preserving physical data, `pg_upgrade` is a dedicated tool with specific prechecks and procedures. It is not simply restoring an old-major physical backup with a new-major server.

### 17.4. Extensions and Collation

Logical dumps do not carry binary extension libraries. Physical backups also do not automatically carry every OS dependency. Restores/migrations require preparing matching extension packages, locale/collation, and runtime dependencies.

## 18. Backup Strategy: Full, Incremental, and Differential

These terms describe how much data is stored relative to a baseline.

- **Full backup:** a complete backup for the defined scope.
- **Incremental backup:** stores only changes since a previous backup.
- **Differential backup:** stores changes since the latest full backup.

### 18.1. Logical Dumps

`pg_dump` generally creates a full logical dump for the chosen scope. It does not provide a generic incremental logical backup chain merely by re-running dumps and diffing files.

You can build custom delta/export pipelines, but you must define identity, deletes, ordering, consistency, and reconciliation yourself.

### 18.2. Physical Incremental

Incremental physical backup capabilities depend on PostgreSQL version and tooling. Some newer PostgreSQL versions/tools support incremental backups and utilities to combine backups. Do not assume an option exists on every server; check version and `pg_basebackup --help`/documentation.

### 18.3. Snapshot Incremental

Storage providers may store snapshots using incremental/copy-on-write mechanisms. This is storage-layer semantics; it does not replace PostgreSQL backup consistency and WAL requirements.

### 18.4. Incremental Chains

Restoring an incremental backup may require the full base and incremental layers in exact order. If one layer is lost or corrupted, subsequent snapshots may become unusable. Manifests must record dependency chains and retention.

## 19. RPO and RTO Drive Backup Design

### 19.1. RPO (Recovery Point Objective)

RPO is the maximum data loss an organization accepts, measured in time.

Example:

- 24-hour RPO: daily backups may satisfy if schedules and procedures fit.
- 5-minute RPO: requires WAL archiving/replication or another low-latency mechanism; daily dumps do not suffice.

### 19.2. RTO (Recovery Time Objective)

RTO is the maximum acceptable duration to restore service.

Example:

- Restoring a very large database logically can take many hours due to recreating indexes/objects.
- Physical restores or attaching snapshots can shorten cluster rebuild time, though recovery, validation, and cutover are still needed.
- A ready standby can cut failover time, though it does not replace backups.

### 19.3. Selection Table by Goal

| Goal | Commonly Suitable Approach |
| --- | --- |
| Recover one table | Logical dump/restore into temporary DB |
| Fast whole-cluster recovery | Verified physical base backup or snapshot |
| Minute/second-level PITR | Base backup + continuous WAL archive |
| Major version migration | Logical migration or `pg_upgrade` |
| Rapid clone for testing | Suitable storage snapshot or physical clone |
| Protection against logical corruption | Independent backups, multiple recovery points, PITR |
| Recover role/global definitions | `pg_dumpall --globals-only` or physical cluster backup |

### 19.4. Include Validation Time

RTO does not end the instant the PostgreSQL process starts. Factor in recovery verification, application checks, DNS/traffic cutover, cache warmup, and operational notifications.

## 20. Replication Is Not a Backup

A standby aids high availability, but does not replace backups.

### 20.1. Logical Corruption Can Replicate

If an application runs an erroneous `DELETE FROM orders`, the change can replicate to the standby. With only a primary and standby, both can lose the logical data simultaneously.

### 20.2. Backups Preserve Historical Recovery Points

An independent backup or WAL archive lets you recover to a time before the erroneous operation, provided retention suffices.

### 20.3. Standbys and Backups Serve Different Roles

| Mechanism | Primary Goal |
| --- | --- |
| Streaming replication | HA, read scaling, replica |
| Logical replication | Data movement, integration, selective replication |
| Physical base backup | Creating cluster copy for restore/standby |
| WAL archive | PITR and recovery |
| Logical dump | Object-level backup/migration |
| Storage snapshot | Storage-level clone/recovery |

### 20.4. Replication Slots Retain WAL But Are Not an Archive Strategy

Slots hold WAL for consumers, but if a consumer lags or disappears, storage can fill up. WAL archives require separate retention, monitoring, and backup policies.

## 21. Encryption and Protecting Backups

Backups typically contain all sensitive production data. Protect them just like production data.

### 21.1. Encryption in Transit

Use TLS for backup client connections to PostgreSQL and uploads to remote storage. Verify certificates/hostnames per policy.

### 21.2. Encryption at Rest

Encrypt dump files, backup repositories, volumes, and snapshots. If a tool lacks native encryption, use an encryption pipeline before uploading and control plaintext staging.

### 21.3. Key Management

Keep encryption keys separate from backup data. Maintain key rotation, recovery key escrow, and test decryption capabilities years later.

### 21.4. Credentials

Never put passwords directly in shell commands or logs. Use `.pgpass`, a secret manager, or an appropriate credential mechanism with strict file permissions.

### 21.5. Access Control

Restrict who can:

- Create backups.
- Read/restore backups.
- Delete backups.
- Delete snapshots.
- Modify retention/immutability.
- Access encryption keys.

Separating backup writer and backup deleter permissions mitigates ransomware and accidental deletion risks.

## 22. Retention, Offsite, and Immutable Copies

### 22.1. Retention Policy

Define copy counts by type:

- Daily backups.
- Weekly/monthly backups.
- Base backup retention.
- WAL retention tied to base backups.
- Snapshot retention.
- Logical export retention.
- Incident hold/legal retention.

Do not delete WAL solely based on segment age if a base backup still depends on that WAL chain for recovery.

### 22.2. Offsite Copies

Keep at least one copy outside the primary failure domain: a different account, region, storage system, or datacenter depending on your threat model.

### 22.3. Immutable Backups

Object lock/WORM/immutability prevents backups from being deleted or modified within the retention period. Configure administrative rights and retention so a compromised production credential cannot delete all recovery points.

### 22.4. 3-2-1 as a Reference Principle

A common guideline is keeping multiple copies, across multiple storage types, with at least one copy offsite. Crucially, copies must not share a single failure mode, and restores must be tested.

### 22.5. Snapshots in the Same Storage Account Have Limitations

Snapshots are fast and convenient, but if production credentials can delete both volumes and snapshots, they are insufficient against ransomware. Replicate/export snapshots to another protection domain and lock retention.

## 23. Manifest and Metadata for Each Backup

A useful backup requires metadata explaining what it is and how to restore it.

A manifest should record:

| Field | Example / Content |
| --- | --- |
| backup_id | UUID or stable identifier |
| backup_type | logical, physical, snapshot |
| source_cluster | Cluster name/ID |
| database_version | PostgreSQL major/minor version |
| start_time / end_time | Backup timestamps |
| consistency_method | MVCC dump, base backup, backup API, clean shutdown |
| scope | Database, cluster, tablespaces, volumes |
| backup_format | plain/custom/directory/tar/physical |
| wal_start / wal_end | WAL range if applicable |
| snapshot_ids | Storage snapshot IDs |
| tablespace_map | Tablespace locations/mapping |
| checksum | Digest/manifest checksum |
| encryption_key_ref | Key reference, never store secret |
| storage_uri | Backup storage location |
| retention_until | Retention expiration timestamp |
| tool_version | `pg_dump`/`pg_basebackup`/backup tool version |
| restore_test_id | Verified restore drill ID |

### 23.1. Metadata Must Accompany the Backup

Do not store the sole manifest on the same volume easily lost with the backup. Keep metadata in an independent backup catalog/remote storage.

### 23.2. State the Consistency Contract Clearly

A snapshot manifest must explicitly state whether it is crash-consistent or application-consistent, whether the backup API was used, which volumes were snapshotted together, and which WAL is required.

### 23.3. Never Write Credentials into Manifests

Record only secret references or key identifiers. Many operators may read manifests while locating backups.

## 24. Verifying Backup Integrity

### 24.1. Checksums

Compute checksums for dump files or backup objects after upload. Re-verify checksums on download/restore.

Checksums detect byte-level changes, but do not prove the backup can boot or that application data is valid.

### 24.2. `pg_verifybackup`

For base backups with a backup manifest created by supported PostgreSQL versions, `pg_verifybackup` validates the file list and checksums against the manifest:

```bash
pg_verifybackup /backups/pg-base-2026-11-14
```

Tool support and capabilities depend on version/format. It does not replace a startup/recovery test and does not verify business semantics.

### 24.3. Logical Archive Listing

```bash
pg_restore --list appdb-2026-11-14.dump
```

Listing archive entries is a helpful check, though it does not prove a full restore will succeed.

### 24.4. Object Storage Checks

Verify:

- File/object count.
- Total size.
- Post-upload checksum.
- Completed multipart uploads.
- Completed snapshot state.
- Replication/copy status.
- Retention/immutability policy.
- Read and decryption permissions.

### 24.5. Do Not Check Only the Exit Code

A backup command exiting with code 0 is a good sign, yet you still must verify artifacts, manifests, checksums, and restorability.

## 25. Restore Drills: Proof That Backups Work

A backup is only truly trustworthy once a test restore has succeeded.

### 25.1. Logical Restore Drill

1. Pick a dump from retention.
2. Create a temporary target database.
3. Create required roles/extensions.
4. Restore using `psql` or `pg_restore`.
5. Verify schema, constraints, indexes, and object counts.
6. Run smoke tests/business queries.
7. Record runtime, errors, and results in a restore report.

### 25.2. Physical Restore Drill

1. Pick a verified base backup.
2. Provision a PostgreSQL environment of a compatible major version.
3. Restore the data directory and tablespaces.
4. Configure WAL recovery/archive if needed.
5. Start the cluster and monitor recovery logs.
6. Verify databases, roles, extensions, and application connectivity.
7. Measure the time to reach an operational state.

### 25.3. Snapshot Restore Drill

1. Pick a snapshot and its manifest.
2. Clone/attach the snapshot into an isolated environment.
3. Attach all volumes/tablespaces completely.
4. Provide required WAL/archive/configuration.
5. Start PostgreSQL according to the snapshot's consistency method.
6. Verify recovery, objects, and data.
7. Measure attach time, WAL replay time, and validation time.

### 25.4. Restore Drills Must Be Scheduled

Perform them regularly, such as monthly or according to criticality. Re-drill after changing PostgreSQL versions, backup tooling, encryption keys, storage providers, or retention policies.

### 25.5. Tests Must Be Isolated

Restore production backups into a test network/environment with strict access controls. Do not accidentally allow test applications to send emails, process payments, fire webhooks, or connect to production services using restored data.

## 26. Verifying Data After Restore

Do not stop at confirming the PostgreSQL process started.

### 26.1. Structural Checks

- Do all databases exist?
- Are schemas/tables/views/sequences complete?
- Are constraints/indexes created?
- Are extensions at the right versions?
- Are roles and grants accurate?
- Are tablespaces mapped properly?

### 26.2. Data Checks

- Row counts across critical tables.
- Min/max IDs or timestamps.
- Business aggregates.
- Key uniqueness and referential integrity.
- Checksums/partition checks if applicable.
- Do transactions near the recovery target have correct semantics?

### 26.3. Application Checks

- Can the application connect?
- Do authentication/authorization work?
- Do read/write smoke tests pass?
- Are background jobs disabled from firing unintentionally?
- Are external integrations isolated?
- Are query plans and performance acceptable?

### 26.4. Recovery Target Checks

For PITR, verify the actual target timestamp/LSN in recovery logs and confirm final state before promotion/cutover.

## 27. Backups for Large Tables and Large Databases

### 27.1. Logical Dumps

Logical dumps can spend significant time serializing data, transferring over the network, compressing, and recreating indexes during restore. Use directory format/parallelism where suitable; measure resource impact.

### 27.2. Physical Backups

Physical backups copy pages/files directly and often suit very large datasets better. Still, network throughput, WAL volume, and storage performance remain constraints.

### 27.3. Snapshots

Snapshots can be created quickly because the storage layer uses metadata/COW, but snapshot creation time is not restore time. Large clones can be slowed by lazy loading, copy-on-read, network attach overhead, or storage performance tiers.

### 27.4. Compression Trade-Offs

Compression saves storage/network bandwidth at the cost of CPU and can slow backup/restore if CPU-bottlenecked. Benchmark both directions rather than judging by file size alone.

### 27.5. Parallelism Trade-Offs

More workers raise throughput when storage/network have headroom; too many workers cause contention with production workloads. Tune concurrency according to benchmarks and SLAs.

## 28. Backups with Tablespaces and External Configuration

### 28.1. Tablespaces

Tablespaces can live outside `PGDATA`. Physical backups/snapshots must include them or map them accurately. Logical dumps require creating matching tablespaces/paths if you wish to preserve definitions.

### 28.2. Symbolic Links and Mount Points

The data directory may use symlinks/mount points. Backup tooling must understand them and preserve/restore the true targets. Snapshotting a mount point while omitting the underlying volume will not protect the data.

### 28.3. Configuration Files

Some config files live outside `PGDATA` or are managed by configuration management. Save separately:

- `postgresql.conf` and include files.
- `pg_hba.conf`.
- `pg_ident.conf`.
- Service/unit configurations.
- TLS certificates.
- Environment variables/secret references.
- Archive/restore scripts.

### 28.4. Extension Binaries

Physical data files may contain extension objects without containing the server's shared libraries. Restores require installing compatible extension packages before accessing those objects.

### 28.5. Locale and Collation

Restores/migrations must consider OS locale/collation providers and versions. Collation changes can affect index ordering; depending on version, reindexing or refreshing collation versions per procedure is required.

## 29. Combined Backup Strategy

A production design usually combines multiple mechanisms.

Illustrative example for an application needing a small RPO and object-level recovery:

```text
             Production PostgreSQL
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       pg_dump     Base backup   WAL archive
       daily       weekly        continuous
          |           |           |
          v           v           v
       Object      Full cluster  PITR chain
       recovery    restore       to target time
          |           |           |
          +-----------+-----------+
                      |
                      v
             Offsite immutable storage
                      |
                      v
               Scheduled restore drills

          Optional storage snapshots
          for rapid clone / volume recovery
```

### 29.1. Frequent Logical Backups

Keep logical dumps for critical databases to enable table/schema recovery or migrations.

### 29.2. Physical Base Backups

Schedule base backups appropriately for RTO, data size, and storage cost.

### 29.3. Continuous WAL Archive

Archive WAL to achieve a low RPO and PITR. Monitor archive lag/failures and retention.

### 29.4. Storage Snapshots

Use snapshots for fast cloning or volume recovery, but only after consistency procedures and restore drills are verified.

### 29.5. Global Objects and Configuration

Store roles/tablespaces, configs, extension inventories, certificates/secret references, and deployment metadata.

### 29.6. Backup Catalog

Manage metadata so operators can find the right backup, WAL range, snapshot IDs, encryption keys, and restore instructions.

## 30. Real-World Recovery Scenarios

| Incident | Common Recovery Approach |
| --- | --- |
| A table is accidentally dropped | Restore logical dump into temp DB and extract table, or use PITR on a temp cluster |
| A database is dropped | Logical restore if recent dump suffices; for tighter state, physical + WAL PITR |
| Entire node is lost | Restore physical base backup or consistent snapshot, then replay WAL |
| Data volume is corrupted | Restore snapshot/physical backup and WAL per procedure |
| A transaction wrote bad data | PITR to before the faulty transaction, usually on an isolated cluster |
| Major version upgrade needed | Logical migration or `pg_upgrade` |
| Latest snapshot already contains corruption | Pick an older recovery point and replay WAL up to before corruption |
| Role is deleted | Restore globals dump or recreate role per audit/config |
| Tablespace volume is lost | Restore volume/physical backup and verify tablespace mapping |
| Backup file is corrupted | Use another copy, verify checksum, and run restore checks |

### 30.1. Table-Level Recovery from a Physical Backup

Physical backups do not provide a direct single-table restore feature like logical archives. You can:

1. Spin up a temporary cluster from a base backup.
2. Replay WAL to the desired time.
3. Dump the needed table using `pg_dump`.
4. Restore the table into the production cluster according to a change plan.
5. Check constraints, sequences, dependencies, and writes that occurred after the dump time.

### 30.2. Table-Level Recovery from PITR

You cannot rewind just one table inside a production cluster using a cluster-wide recovery target. Usually you create a secondary cluster recovered via PITR to the target, then export the required object.

## 31. Common Mistakes

1. Treating a logical dump as a physical copy of the data directory.
2. Using `pg_dump` and assuming roles/tablespaces are backed up.
3. Taking a physical backup from an old major version and trying to start it with a new major version.
4. Assuming a base backup alone suffices for PITR without continuous WAL.
5. Treating a WAL archive as a complete backup without needing a base backup.
6. Assuming a storage snapshot of `PGDATA` alone is enough when tablespaces reside outside.
7. Snapshotting multiple volumes at different timestamps and assuming consistency.
8. Copying a running `PGDATA` with ordinary file copy tools and calling it an online backup.
9. Treating a crash-consistent snapshot as automatically application-consistent.
10. Confusing a storage snapshot with an MVCC snapshot.
11. Treating a standby/replica as a backup against logical corruption.
12. Treating a snapshot in the same account as ransomware-proof.
13. Failing to retain configs, extension binaries, or encryption keys.
14. Omitting WAL ranges and snapshot IDs from manifests.
15. Checking only the backup command exit code.
16. Skipping test restores in an isolated environment.
17. Running `pg_restore --clean` against the wrong production database.
18. Enabling `-R` when not intending to build a standby.
19. Deleting WAL too early and breaking the PITR chain.
20. Estimating RTO solely from copy/attach time, ignoring replay and application validation.

## 32. Practice Exercises with Answers

These exercises assume you have a PostgreSQL lab and a dedicated backup directory. Destructive restore commands should only be executed against a lab target database.

### Exercise 1. What is a logical backup?

**Answer:** Backing up schemas/data as logical objects such as SQL or an archive, reconstructed via restore tools.

### Exercise 2. What is a physical backup?

**Answer:** Copying PostgreSQL data files at the cluster level along with the components required to recover the cluster.

### Exercise 3. What is a storage snapshot?

**Answer:** A point-in-time image of block/volume/filesystem state managed by the storage layer.

### Exercise 4. Does `pg_dump` back up one or all databases?

**Answer:** One database per run.

### Exercise 5. What tool exports global objects?

**Answer:** `pg_dumpall --globals-only`.

### Exercise 6. How does `pg_dumpall` differ from `pg_dump`?

**Answer:** `pg_dumpall` exports multiple databases and global objects as a SQL script; `pg_dump` exports a single database in multiple archive formats.

### Exercise 7. What restores a plain dump?

**Answer:** `psql`.

### Exercise 8. What restores a custom dump?

**Answer:** `pg_restore`.

### Exercise 9. Which option creates custom format?

**Answer:** `pg_dump -Fc`.

### Exercise 10. What is the advantage of directory format?

**Answer:** Supports parallel dump/restore and stores the archive across multiple files.

### Exercise 11. What command inspects the TOC of a custom archive?

**Answer:** `pg_restore --list`.

### Exercise 12. Does `pg_dump` lock the database to block all writes?

**Answer:** No. It uses a consistent MVCC snapshot and necessary object locks.

### Exercise 13. Do logical dumps automatically include roles?

**Answer:** No. Roles are global objects; export them separately with `pg_dumpall --globals-only` or a physical cluster backup.

### Exercise 14. Why must tablespace definitions be protected?

**Answer:** Tablespaces may reside outside `PGDATA` and require matching paths/mounts/ownership upon restore.

### Exercise 15. What does `pg_restore --clean` do?

**Answer:** Drops objects before recreating them; can destroy target data, so verify the target database carefully.

### Exercise 16. What does `--no-owner` change?

**Answer:** Does not restore original ownership; objects are owned by the role performing the restore or per corresponding semantics.

### Exercise 17. What scope does a physical backup usually cover?

**Answer:** The entire PostgreSQL cluster and associated physical components, not a single table.

### Exercise 18. What common PostgreSQL tool creates a base backup?

**Answer:** `pg_basebackup`.

### Exercise 19. Which protocol does `pg_basebackup` use?

**Answer:** The replication protocol.

### Exercise 20. What is the purpose of `-X stream`?

**Answer:** Streams WAL concurrently with the base backup to ensure the backup has the required WAL under that method.

### Exercise 21. When is `pg_basebackup -R` normally used?

**Answer:** When preparing a backup to serve as a standby, since it writes appropriate recovery/connection settings.

### Exercise 22. Does a base backup replace a WAL archive for long-term PITR?

**Answer:** No. Continuous WAL must be retained up to the recovery target.

### Exercise 23. What happens if a WAL archive is missing one segment?

**Answer:** PITR may be unable to replay past the required timeframe.

### Exercise 24. What does PITR require?

**Answer:** A valid base backup, continuous WAL, restore configuration, and a recovery target.

### Exercise 25. What is RPO?

**Answer:** Recovery Point Objective, the maximum acceptable data loss measured in time.

### Exercise 26. What is RTO?

**Answer:** Recovery Time Objective, the maximum acceptable duration to restore service.

### Exercise 27. Do storage snapshots understand schemas/tables?

**Answer:** No. They capture storage blocks/volumes.

### Exercise 28. Generally, how does a copy-on-write snapshot work?

**Answer:** Keeps references/metadata to the initial state and stores changed blocks according to the storage mechanism.

### Exercise 29. What is a crash-consistent snapshot?

**Answer:** Storage state resembling a host crash at a point in time; PostgreSQL needs WAL crash recovery and complete files/volumes.

### Exercise 30. Does crash-consistent mean application-consistent?

**Answer:** No. Application-consistent requires coordinating with the application/database and following an appropriate backup procedure.

### Exercise 31. Is snapshotting only the `PGDATA` volume always enough?

**Answer:** No if tablespaces/WAL or other dependencies reside on separate volumes.

### Exercise 32. Why do multi-volume snapshots need a consistency group?

**Answer:** So all volumes represent the same point-in-time, avoiding timestamp skew between data and WAL/tablespaces.

### Exercise 33. How does an MVCC snapshot differ from a storage snapshot?

**Answer:** An MVCC snapshot is transaction visibility state; a storage snapshot is a block/volume image.

### Exercise 34. During an online snapshot, what is the PostgreSQL backup API used for?

**Answer:** Coordinating physical backup with the server, marking the backup interval, and providing version-specific metadata/WAL requirements.

### Exercise 35. Can you copy a running `PGDATA` with `cp -r` as an online backup?

**Answer:** You should not. Use `pg_basebackup` or a PostgreSQL-supported filesystem backup procedure.

### Exercise 36. What is the advantage of snapshotting when PostgreSQL is cleanly shut down?

**Answer:** Produces a consistent physical copy if all volumes/tablespaces are snapshotted completely; the trade-off is downtime.

### Exercise 37. Can a physical backup restore directly across major versions?

**Answer:** No. A compatible environment of the same major version is needed; use `pg_upgrade` or logical migration for major upgrades.

### Exercise 38. Are extension binaries included in logical dumps?

**Answer:** No. Compatible extension packages must be installed on the target.

### Exercise 39. Does a standby replace backups?

**Answer:** No. Logical corruption can replicate to the standby.

### Exercise 40. Do snapshots in the same storage account fully protect against ransomware?

**Answer:** No. Compromised credentials can delete both volumes and snapshots; offsite/immutable copies are needed.

### Exercise 41. What is `pg_verifybackup` used for?

**Answer:** Verifying physical backup manifests/file checksums on supported versions/formats.

### Exercise 42. Does `pg_verifybackup` prove the application works properly?

**Answer:** No. Restore/startup tests and application validation are required.

### Exercise 43. What does a backup checksum prove?

**Answer:** Detects byte modifications relative to the stored digest; does not prove semantics/recoverability.

### Exercise 44. What should a logical restore drill verify?

**Answer:** Schemas, data, constraints, indexes, roles/extensions, and business smoke tests.

### Exercise 45. What should a physical restore drill verify?

**Answer:** Data directory, tablespaces, WAL recovery, server startup, roles/extensions, and application connectivity.

### Exercise 46. What should a snapshot restore drill verify?

**Answer:** Snapshot metadata, all volumes, consistency procedures, WAL, configuration, and cluster recovery.

### Exercise 47. Why is a manifest needed?

**Answer:** To track backup identity, version, scope, timestamps, consistency method, WAL range, snapshot IDs, checksums, and restore instructions.

### Exercise 48. How does a full backup differ from an incremental backup?

**Answer:** Full stores the entire scope; incremental stores only changes since a prior backup.

### Exercise 49. Is `pg_dump` incremental by default?

**Answer:** No. Each dump is a logical export of the selected scope; incremental logical semantics require a custom pipeline.

### Exercise 50. Do incremental snapshots inherently understand PostgreSQL WAL?

**Answer:** No. That is storage-layer incrementalism; consistency/WAL must still be handled separately.

### Exercise 51. Why must backup encryption keys be preserved?

**Answer:** Without the matching key, encrypted backups cannot be restored.

### Exercise 52. Why should backup copies be stored offsite?

**Answer:** To reduce the risk of a single failure domain, region, account, or physical disaster destroying all copies.

### Exercise 53. How do immutable backups help?

**Answer:** Prevent backups from being modified/deleted during the retention period per policy, limiting ransomware or credential compromise impact.

### Exercise 54. Should WAL be deleted solely because it is older than 7 days?

**Answer:** No if a base backup still requires that WAL chain for PITR or standby recovery.

### Exercise 55. How do you recover one table from a physical backup?

**Answer:** Restore a temporary cluster, replay to the desired state, dump the table, and import it into production under a change plan.

### Exercise 56. How do you recover to before a faulty transaction?

**Answer:** Base backup + WAL PITR to before the faulty transaction, usually on a temporary cluster.

### Exercise 57. Can `pg_dump` be used for a major-version migration?

**Answer:** Yes, if client/server/object compatibility holds; check extensions, roles, collations, and target version.

### Exercise 58. Why must RTO include validation time?

**Answer:** Server startup does not mean the application is safe to serve traffic; data checks, integrations, and cutover remain.

### Exercise 59. Why shouldn't you rely on only one backup type?

**Answer:** Each type has distinct strengths/limitations; combining logical, physical, WAL, and snapshots supports diverse recovery scenarios.

### Exercise 60. Build a checklist for choosing backup types for a PostgreSQL service

**Suggested Answer:**

1. Define RPO/RTO and required recovery scopes.
2. Use `pg_dump` for object/database-level recovery and migrations.
3. Save global objects/roles/tablespaces separately as needed.
4. Use `pg_basebackup` or a compatible physical backup tool for whole-cluster recovery.
5. Configure continuous WAL archiving if PITR is required.
6. Use storage snapshots only after confirming consistency semantics and all volumes.
7. Store configs, extension inventories, certificates/secret references, and tablespace mappings.
8. Enforce encryption, offsite copies, immutable retention, and separated delete permissions.
9. Create manifests, checksums, and verify backup artifacts.
10. Run regular restore drills, measure actual RPO/RTO, and update the runbook.

## 33. Production Checklist

| Check | Requirement to Ensure |
| --- | --- |
| RPO/RTO | Defined by business impact |
| Logical backups | Present for database/object recovery |
| Global objects | Roles/tablespaces protected |
| Physical base backup | Scheduled with restore procedure |
| WAL archive | Continuous, with gap monitoring |
| PITR | Recovery targets/runbook defined |
| Storage snapshots | Consistency method clearly documented |
| Multi-volume | Consistency group or coordinated workflow |
| Tablespaces | Included/mapped accurately |
| PGDATA/WAL | Complete within backup scope |
| PostgreSQL version | Compatible restore target |
| Extensions | Binary packages and versions inventoried |
| Config files | Copied outside data directory |
| TLS/secrets | Secure recovery procedure exists |
| Encryption | At-rest and in-transit |
| Key management | Rotation/escrow/recovery tested |
| Offsite copy | Separate failure domain |
| Immutability | Appropriate retention lock configured |
| Backup manifest | Contains IDs, scope, version, timestamps, checksum |
| WAL retention | Never deletes still-needed segments |
| Snapshot retention | Not retained solely in the same account |
| `pg_verifybackup` | Run where format/version supports it |
| Logical archive listing | Archive entries inspected |
| Restore drills | Scheduled with reports |
| Data validation | Counts, keys, aggregates, smoke tests |
| Recovery environment | Capacity and network isolation ready |
| Application cutover | Runbook and rollback decision defined |
| Monitoring | Backup age, duration, size, failures |
| Restore duration | Measured in practice |
| Access control | Backup writer/deleter permissions separated |
| Incident hold | Ability to lock backups during investigation |

## 34. Summary

Logical backups, physical backups, and storage snapshots protect data at three distinct layers. Logical dumps store object/data representations; physical backups store cluster files; storage snapshots capture block storage state. The right choice depends on what must be recovered, consistency contracts, RPO/RTO, and verified restorability.

Key principles:

1. **Logical backups suit object-level recovery and migrations.** `pg_dump` exports one database; `pg_dumpall` can export multiple databases and global objects.
2. **Plain SQL and archive formats restore differently.** Use `psql` for plain dumps and `pg_restore` for custom/directory/tar.
3. **Logical dumps use a consistent MVCC snapshot.** They do not copy physical page layouts.
4. **Roles and tablespaces are not automatically in `pg_dump`.** Protect global objects separately when needed.
5. **Physical backups suit whole-cluster recovery.** Use `pg_basebackup` or a supported tool.
6. **Physical backups require compatible PostgreSQL major versions.** Do not use them as a major-version upgrade method.
7. **Base backups and WAL archives complement each other.** PITR requires a base backup plus continuous WAL.
8. **Storage snapshots capture only storage state.** They do not understand schemas, transaction visibility, or business objects.
9. **Crash-consistent is not automatically application-consistent.** Use the version-appropriate backup API/procedure for online snapshots.
10. **Snapshots must include all relevant volumes.** `PGDATA`, tablespaces, and WAL must not skew across points in time.
11. **Replication does not replace backups.** Logical corruption can propagate to standbys.
12. **Snapshots in the same failure domain are insufficient.** Keep offsite/immutable copies.
13. **Checksums and manifests verify artifacts.** They do not replace restore drills.
14. **Restore drills are real-world proof.** Test both PostgreSQL and the application.
15. **RPO/RTO must be measured on full recovery.** Include WAL replay, validation, and cutover.
16. **Protect keys/configs/extensions.** Backup data alone does not carry every dependency needed to run a cluster.
17. **Retain WAL based on base backup dependencies.** Deleting segments early can break PITR.
18. **Combine multiple backup types.** Logical for objects, physical for clusters, WAL for PITR, and snapshots for storage-level clones/recovery.

Selection model:

```text
Need to restore a single object?
        |
        +---- Yes ----> Logical dump / restore
        |
        +---- No
                |
                v
       Need whole-cluster recovery?
                |
                +---- Yes ----> Physical base backup
                |                 + WAL archive for PITR
                |
                +---- Need fast volume clone?
                                  |
                                  v
                         Storage snapshot
                         + consistency procedure
                         + WAL if recovery needed
                                  |
                                  v
                         Restore drill and verify
```

**Final review question:** "If a table is accidentally dropped, if an entire node is lost, if a bad transaction commits, and if a storage volume is corrupted, can we pick the right backup, do we know the exact dependencies needed, and have we proven a successful restore within RTO?" A trustworthy backup strategy must answer every scenario with artifacts, WAL/metadata, manifests, and real restore drills.
