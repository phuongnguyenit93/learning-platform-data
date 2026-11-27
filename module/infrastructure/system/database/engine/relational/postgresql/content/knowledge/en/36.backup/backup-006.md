# `pg_basebackup` and Physical Base Backups in PostgreSQL

PostgreSQL has two primary backup approaches: **logical backup** and **physical backup**. Logical backups export schemas and data at the SQL level, typically with `pg_dump`/`pg_dumpall`. Physical backups copy the physical files of the entire PostgreSQL cluster under a consistent procedure, then use WAL to complete recovery upon restore.

**`pg_basebackup`** is the PostgreSQL-provided tool for creating a physical base backup from a running server. It uses PostgreSQL's replication protocol and backup protocol, enabling online backups without stopping the database. A base backup is the starting point for crash recovery, building a standby, or Point-in-Time Recovery (PITR) when paired with appropriate WAL.

~~~text
PostgreSQL primary
      |
      | replication protocol / backup protocol
      v
  pg_basebackup
      |
      +----------------------------+
      |                            |
      v                            v
  Data files                  Required WAL
  - base relations            - streamed during backup
  - indexes                   - or supplied via archive
  - system catalogs
  - tablespaces
      |                            |
      +--------------+-------------+
                     |
                     v
              Physical base backup
                     |
           +---------+----------+
           |                    |
           v                    v
       Restore DB           Build standby
           |                    |
           v                    v
       Crash recovery       Streaming replication
           |
           v
       Can replay additional archived WAL for PITR
~~~

A backup file may be created successfully yet still fall short of a complete recovery plan. You must know which cluster/version the backup belongs to, which WAL is needed, where tablespaces live, which configs reside outside `PGDATA`, what retention preserves, and whether a test restore has ever been performed.

This lesson belongs to the **Backup** chapter of the *Database Engine Relational PostgreSQL* module and focuses on creating, verifying, retaining, and restoring physical backups using `pg_basebackup`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish physical backups from logical backups.
2. Explain why physical backups usually cover the entire cluster rather than an individual table.
3. Describe the backup protocol and the role of WAL in online backups.
4. Grant replication privileges and configure `pg_hba.conf` for `pg_basebackup`.
5. Choose plain or tar format and understand how tablespaces are stored.
6. Choose `stream`, `fetch`, or `none` WAL methods as needed.
7. Use checkpoint, rate limit, progress, and tablespace mapping options.
8. Understand the impact of `max_wal_senders`, replication slots, and archive retention.
9. Take base backups from a primary or standby under proper conditions.
10. Use the `-R` option to generate standby configuration from a backup.
11. Verify backup manifests and checksums using `pg_verifybackup`.
12. Distinguish backup file verification from end-to-end test restores.
13. Restore plain backups and tar backups properly.
14. Prepare WAL archives and recovery settings for PITR.
15. Design retention based on backup dependencies.
16. Measure duration, size, RPO, and RTO through restore drills.
17. Identify common errors when creating and restoring physical backups.

## 2. What Is a Physical Backup?

A physical backup is a copy of PostgreSQL's data files at the filesystem/storage level. It preserves PostgreSQL's layout for heaps, indexes, catalogs, WAL, and other physical components.

### 2.1. PostgreSQL Cluster

A PostgreSQL cluster is a data area managed by one server instance, typically containing:

- Multiple databases.
- Shared catalogs and global objects.
- Roles and privileges.
- Tablespaces.
- Data files, indexes, and auxiliary relation files.
- Configuration files inside or outside the data directory.

A physical base backup normally copies the cluster rather than selecting an individual database or table.

### 2.2. File-Level Copy

You cannot simply copy the `PGDATA` directory while PostgreSQL is writing data and treat the result as a valid backup. One file might be copied before a change and another after a change; those files may fail to form a consistent state.

### 2.3. Online Physical Backup

`pg_basebackup` coordinates with the server to mark the start/end of the backup and guarantee the WAL required to make the copy consistent. The database can keep serving queries and writes during the backup, though the backup adds I/O and WAL load.

### 2.4. Base Backup and WAL

A base backup is a data image captured over a time interval. Because pages can change while being copied, WAL is required to replay and bring the copy to a consistent state.

### 2.5. A Physical Backup Is Not a SQL Export

You cannot open a physical backup like a SQL file to read individual `CREATE TABLE`/`INSERT` statements. To inspect data at the SQL level, you must restore it into PostgreSQL or use a logical backup.

## 3. Physical Backup vs. Logical Backup

| Criterion | Physical Backup | Logical Backup |
| --- | --- | --- |
| Typical tools | `pg_basebackup`, pgBackRest | `pg_dump`, `pg_dumpall` |
| Contents | Cluster physical files | Logical schemas and data |
| Typical scope | Entire cluster | Selected database/schema/table |
| Restore | Restore files then replay WAL | Execute SQL to rebuild objects |
| Backup/restore speed | Often fast for large clusters | Can be slower for very large datasets |
| Major version migration | Not usable directly across majors | Can aid migration via dump/restore |
| Selecting one table | Not the goal of base backups | Yes |
| PITR | Combine base backup and WAL | Does not provide physical WAL replay |
| Inspect/edit contents | Not directly | Dumps can be read/edited |

### 3.1. When to Choose Physical Backup?

- Need fast recovery of an entire cluster.
- Need to bootstrap a standby/replica from a copy.
- Large databases where rebuilding every object via SQL is undesirable.
- Need PITR using a base backup plus a WAL archive.

### 3.2. When to Choose Logical Backup?

- Need only one database, schema, or table.
- Want to migrate data across major versions.
- Want to export data for inspection/transformation.
- Want to back up a small subset of objects rather than the whole cluster.

### 3.3. Using Both

Critical systems often combine physical backups/WAL archiving for disaster recovery with logical dumps for migrations, object-level recovery, or portability.

## 4. How Does `pg_basebackup` Work?

`pg_basebackup` connects to PostgreSQL over the replication protocol, asks the server to begin backup, copies necessary files, collects WAL per the chosen method, and ends the backup.

### 4.1. Backup Start

The server records a backup start point and provides metadata identifying required WAL.

### 4.2. Copying Data Files

The client copies relation files, catalogs, the control file, tablespace layouts, and components supplied by the backup protocol.

### 4.3. WAL During Copying

Modifications continue on the primary. WAL lets recovery reconcile differences between when individual files were copied and the backup's consistent state.

### 4.4. Backup Stop

The server ends the backup, writes necessary metadata/records, and identifies the ending WAL needed for backup consistency.

### 4.5. Backup Label and Manifest

Depending on format/version, the backup may include `backup_label`, `tablespace_map`, and `backup_manifest`. Keep this metadata intact for restoration and verification.

### 4.6. Never Manually Edit Backup Metadata

Never modify `backup_label` or manifests to "make verify pass." These files are part of the consistency proof and recovery workflow.

## 5. PostgreSQL Server Prerequisites

Before running `pg_basebackup`, check server parameters and resources.

### 5.1. `wal_level`

For physical replication/backups, the standard setting is:

~~~conf
wal_level = replica
~~~

`logical` also includes `replica` WAL capabilities. Never use `minimal` for workflows needing physical replication/PITR.

### 5.2. `max_wal_senders`

The server needs enough WAL sender processes for standbys, backup jobs, and other replication connections:

~~~conf
max_wal_senders = 10
~~~

A single `pg_basebackup` using WAL method `stream` can open two concurrent replication connections: one for the base backup and one for the WAL stream. Add up concurrent standbys/backups and leave headroom.

### 5.3. `max_replication_slots`

If using named replication slots, ensure sufficient slot capacity:

~~~conf
max_replication_slots = 10
~~~

Size according to actual consumer/backup slots and monitor unused slots.

### 5.4. `full_page_writes`

Keep `full_page_writes` enabled per standard safety defaults. Full-page images help recovery protect against torn pages when needed. When backing up from a standby, ensure the primary has `full_page_writes` enabled properly.

### 5.5. `hot_standby`

If backing up from a standby, the standby must be in a state allowing queries/read-only operations as required and properly configured, usually with `hot_standby` enabled.

### 5.6. WAL Archiving

If the goal is PITR or long-term backup retention, configure WAL archiving on the primary/source appropriately. WAL streamed alongside a base backup only covers that backup; it does not create a continuous archive for later points in time.

### 5.7. Disk Headroom

The server needs enough space for WAL generated during the backup and for replication slots. The backup client needs enough space for the destination copy and potentially temporary space for compression/format conversion.

## 6. Creating a Replication User and `pg_hba.conf`

`pg_basebackup` connects using the replication protocol. The user needs `LOGIN` and `REPLICATION` privileges or equivalent administrative rights per server policy.

### 6.1. Creating the Backup Role

~~~sql
CREATE ROLE backup_user
WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
~~~

Never use sample passwords in production. Manage secrets via an appropriate secret system and rotate them per policy.

### 6.2. Allowing Replication in `pg_hba.conf`

Example permitting TLS connections from the backup subnet:

~~~conf
hostssl replication backup_user 10.20.0.0/24 scram-sha-256
~~~

Network addresses, TLS, and authentication methods must match real infrastructure. Never expose replication access to the open Internet.

### 6.3. Reloading `pg_hba.conf`

~~~sql
SELECT pg_reload_conf();
~~~

### 6.4. Verifying Rules

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

This view catches parse errors and shows rule order. PostgreSQL applies the first matching rule; ordering matters.

### 6.5. Distinguishing SQL Privileges from OS Permissions

The replication role authenticates to PostgreSQL. Backup files are written by the `pg_basebackup` client process, so destination filesystem permissions belong to the OS user running the client.

### 6.6. Using `.pgpass`

For non-interactive automation, use a standard `libpq` password file. On Unix, permissions must be strict (typically `0600`). Never expose plaintext passwords in shell history or process arguments.

## 7. Basic `pg_basebackup` Syntax

Example creating a plain-format backup:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -F plain \
  -X stream \
  -P \
  -v
~~~

Meaning:

| Option | Meaning |
| --- | --- |
| -h | PostgreSQL server host |
| -p | Port |
| -U | Replication user |
| -D | Destination directory |
| -F plain | Store files in data directory layout |
| -X stream | Stream required WAL concurrently |
| -P | Show progress |
| -v | Verbose output |

### 7.1. Destination Directory

The destination directory normally must not exist yet or must be empty per version/tool rules. Never point it at a running `PGDATA` or a folder holding data you need to keep.

### 7.2. Avoid Running as an Unnecessary OS Superuser

Run the backup client under a dedicated OS account with write permission to the backup destination. The database replication user is a separate identity from the OS user.

### 7.3. Choosing the Matching `pg_basebackup` Binary

Use a tool matching the server major version and check:

~~~bash
pg_basebackup --version
pg_basebackup --help
~~~

Newer options may not exist in older binaries. Consult docs for the exact major version running.

## 8. Plain Format vs. Tar Format

`pg_basebackup` offers two common formats:

### 8.1. Plain Format

~~~bash
pg_basebackup -h primary.example.internal \
  -U backup_user \
  -D /backup/base_plain \
  -F plain -X stream -P
~~~

Plain format creates a directory tree resembling PostgreSQL's data directory. It can be used directly as `PGDATA` after proper restore preparation.

### 8.2. Tar Format

~~~bash
pg_basebackup -h primary.example.internal \
  -U backup_user \
  -D /backup/base_tar \
  -F tar -X stream -P
~~~

Tar format produces tar archives, typically `base.tar`, `pg_wal.tar`, and separate tar files for tablespaces. They must be extracted into the right locations before starting the server.

### 8.3. Comparison

| Criterion | Plain | Tar |
| --- | --- | --- |
| Structure | Directory tree | One or more tar files |
| Starting restore | Ready once `PGDATA`/tablespaces are placed | Must extract all tars properly |
| Tablespaces | Directories/symlinks per backup | Separate archive per tablespace |
| Tablespace mapping | Supported via mapping options in suitable workflows | Usually handled when extracting/placing tablespaces |
| Manifest verification | `pg_verifybackup` supports plain format | Cannot run `pg_verifybackup` directly as on plain |
| Compression | Compressed at filesystem/external backup tool | Supports tar compression options depending on version |

### 8.4. Which Format to Choose?

Plain is easy to restore directly and works smoothly with `pg_verifybackup`. Tar fits pipelines that package/stream archives or manage single archive files. Choose based on restore tooling and tablespace handling.

### 8.5. Never Extract All Tars into the Same Directory

Tablespace tar archives must be extracted to their respective tablespace paths; `pg_wal.tar` must go into the `pg_wal` directory inside the data directory. Incorrect extraction can prevent the backup from booting.

## 9. WAL Methods: `stream`, `fetch`, and `none`

The `-X` option selects how WAL required for the base backup is collected.

### 9.1. `stream`

~~~bash
pg_basebackup -D /backup/base_stream -X stream -P
~~~

WAL is streamed concurrently while data is copied. This is the standard choice for online backups because it minimizes the risk of needed WAL being recycled before the client retrieves it.

### 9.2. `fetch`

~~~bash
pg_basebackup -D /backup/base_fetch -X fetch -P
~~~

Required WAL is fetched after data copying finishes. The server must retain all needed segments until fetch completes; if WAL is recycled earlier, the backup can fail.

### 9.3. `none`

~~~bash
pg_basebackup -D /backup/base_no_wal -X none -P
~~~

Does not collect WAL during the backup command. Use only when another mechanism guarantees supplying all required WAL. Without the necessary WAL, the copy cannot reach a consistent state to start.

### 9.4. Comparison

| Method | When WAL Is Collected | Key Requirement |
| --- | --- | --- |
| `stream` | Concurrently with data copy | Sufficient WAL senders/connections |
| `fetch` | After data copy | Required WAL still present on server |
| `none` | Not collected | External WAL mechanism required |

### 9.5. WAL Stream Is Not Continuous Archiving

WAL streamed during `pg_basebackup` covers only that backup. To perform PITR to a point after the backup, you need continuous WAL archiving or another WAL retention/transfer mechanism.

## 10. Checkpoint Mode and Backup Speed

### 10.1. `spread`

Spread checkpoint lets the checkpoint proceed gradually per configuration, smoothing out I/O spikes. This is the common default.

### 10.2. `fast`

Fast checkpoint forces the checkpoint to complete rapidly, which can cause I/O spikes. Choose only with operational justification and awareness of the impact.

Example:

~~~bash
pg_basebackup -D /backup/base_fast \
  -X stream --checkpoint=fast -P
~~~

### 10.3. Max Rate

You can throttle transfer speed to limit impact on production:

~~~bash
pg_basebackup -D /backup/base_limited \
  -X stream --max-rate=100M -P
~~~

Exact units and syntax depend on `pg_basebackup` version. Lower rate limits extend backup duration, which also lengthens how long required WAL must be retained.

### 10.4. Measuring Impact

Monitor CPU, disk throughput, network, WAL generation, replication lag, and query latency during backups.

### 10.5. Concurrent Backups

Multiple concurrent backups increase I/O and WAL sender usage. Set concurrency limits and verify headroom before running.

## 11. Progress, Labels, and Logging

### 11.1. Showing Progress

~~~bash
pg_basebackup -D /backup/base \
  -X stream -P -v
~~~

Progress shows operators bytes copied and total estimates. It does not prove the backup is restorable.

### 11.2. Backup Label

~~~bash
pg_basebackup -D /backup/base \
  -X stream -l "nightly-2026-11-14" -P
~~~

Labels help identify backups in logs/metadata; do not rely on a label as a unique identifier if names can collide.

### 11.3. Logs

Record stdout/stderr, start/end timestamps, source host, server version, tool version, backup ID, format, WAL method, size, and exit code.

### 11.4. Exit Code

Automation should mark a backup successful only when `pg_basebackup` exits cleanly and subsequent verification/metadata registration steps finish.

### 11.5. Do Not Ignore Errors Just Because a Directory Exists

`pg_basebackup` can leave partial files behind if interrupted. The presence of a destination directory does not mean the backup is complete.

## 12. Tablespaces and Mapping

Tablespaces let relations reside outside `PGDATA`. Physical backups must preserve both contents and path relationships for tablespaces.

### 12.1. Listing Tablespaces

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
~~~

### 12.2. Plain Backup

Plain backups can create tablespace structures with corresponding paths/symlinks. When restoring onto a host with a different filesystem layout, mapping is required.

### 12.3. Tablespace Mapping

The `-T` or `--tablespace-mapping` option takes `olddir=newdir`:

~~~bash
pg_basebackup \
  -D /backup/base \
  -F plain \
  -X stream \
  -T /data/pg_ts_fast=/restore/pg_ts_fast
~~~

The old path must match the source tablespace, and the new path must fit the restore target. Mapping syntax and limitations depend on format/version.

### 12.4. Tar Backup

Tar format typically creates separate archives per tablespace. When extracting, place contents into the new tablespace directories and ensure `PGDATA/pg_tblspc` symlinks point to the right locations.

### 12.5. Do Not Forget Tablespaces

If you only copy `base.tar` and omit a tablespace tar, the server will miss relation files and fail to start or operate properly.

### 12.6. Permissions and Mounts

Tablespace directories need ownership/permissions matching the PostgreSQL OS user and must be stably mounted before starting the server.

## 13. Creating a Standby with `-R`

`pg_basebackup` can prepare a backup to run as a standby.

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U replicator \
  -D /var/lib/postgresql/16/standby \
  -X stream \
  -R \
  -P
~~~

### 13.1. What Does `-R` Do?

`-R` or `--write-recovery-conf` creates `standby.signal` and writes connection parameters into `postgresql.auto.conf` so the server boots configured as a standby.

### 13.2. `primary_conninfo`

Contains connection parameters to the primary/replication source. Manage passwords/secrets securely; never expose them in logs or repositories.

### 13.3. `standby.signal`

This file instructs PostgreSQL to run in standby mode on startup.

### 13.4. `primary_slot_name`

If the backup used a replication slot, `-R` can record the slot name so the standby continues using it. Inspect `postgresql.auto.conf` before starting.

### 13.5. `-R` Is Not PITR Recovery

`-R` creates standby configuration. When restoring a standalone backup or performing PITR, configure archive recovery/targets as intended instead of leaving `standby.signal` around by accident.

## 14. Replication Slots During Backup

A replication slot retains WAL needed by a consumer, preventing the server from recycling WAL before the consumer receives it.

### 14.1. Creating a Slot with the Backup

Example using a named slot:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U replicator \
  -D /backup/standby_a \
  -X stream \
  -C \
  -S standby_a_slot \
  -R \
  -P
~~~

`-C` requests creating a slot; `-S` sets the slot name. Ensure the slot name does not already exist or manage slot lifecycle per version/tool rules.

### 14.2. Temporary and Permanent Slots

Some workflows use temporary slots to hold WAL during the backup. Permanent slots persist after the backup finishes and keep retaining WAL for a long-lived standby.

### 14.3. Slots Can Fill Up `pg_wal`

If a consumer stops while its slot stays active in metadata, `pg_wal` can grow continuously. Monitor retained WAL and slot status.

### 14.4. `max_slot_wal_keep_size`

You can cap how much WAL a slot may retain per policy:

~~~conf
max_slot_wal_keep_size = 20GB
~~~

This limit can invalidate a slot if the consumer falls too far behind and required WAL is recycled; recovering that standby may then require rebuilding it. Balance the limit against disk headroom and RPO.

### 14.5. Inspecting Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Some columns exist only in newer versions; omit nonexistent columns on older PostgreSQL releases.

## 15. Backing Up from Primary vs. Standby

### 15.1. Backing Up from the Primary

This is the simplest and most common approach. The backup uses WAL senders on the primary and can add I/O/network load to the primary.

### 15.2. Backing Up from a Standby

You can offload read/copy traffic from the primary by backing up from a standby. However, the standby still needs adequate resources, and the backup can affect replay/replication lag.

### 15.3. Standby Prerequisites

Ensure the standby has sufficient WAL sender capacity, is healthy, has appropriate `hot_standby` settings, and can supply needed WAL throughout the backup.

### 15.4. `full_page_writes` on the Primary

When backing up from a standby, `full_page_writes` must be enabled on the primary to support backup consistency as required by PostgreSQL.

### 15.5. WAL Source

Backing up from a standby can depend on replayed/streamed WAL and how the tool retrieves WAL. Check documentation for your exact major version, especially with `-X stream`/`fetch`.

### 15.6. Do Not Back Up from a Heavily Lagging Standby Unawares

A backup taken from a standby may reflect an older state than the primary. If you require the latest state, measure replay LSN/lag and record the exact effective time/LSN.

## 16. Checking Backup State and Metadata

### 16.1. `backup_label`

The backup label records essential info for recovering the base backup. Keep this file untouched.

### 16.2. `tablespace_map`

Describes tablespace mappings in the backup when applicable. Do not discard this file on restore.

### 16.3. `backup_manifest`

PostgreSQL versions supporting manifests generate a file listing backup files and checksums. The manifest helps detect missing or altered files.

### 16.4. System Identifier

A backup belongs to a PostgreSQL cluster with a unique system identifier. When combining WAL, verify the WAL belongs to the exact same cluster history.

### 16.5. Version Metadata

Record PostgreSQL major/minor version, build/architecture if relevant, extension versions, locale/collation, and configurations needed to provision a compatible environment.

## 17. Backup Manifest and `pg_verifybackup`

`pg_verifybackup` validates a backup using its backup manifest and supported WAL checks.

~~~bash
pg_verifybackup /backup/base_plain
~~~

### 17.1. File Verification

The tool compares the file list and checksums against the manifest to detect missing, extra, or modified files within its scope.

### 17.2. WAL Verification

The tool can verify WAL accompanying the backup using supported mechanisms, including parsing WAL records within applicable bounds.

### 17.3. Plain Format

`pg_verifybackup` is designed for plain-format backups; do not run it directly against a tar-format backup as if it were a plain directory. For tar backups, use an appropriate extract/verify procedure and test restores.

### 17.4. Checksum Algorithms

Manifests can use different checksum algorithms depending on version/configuration. Specify the algorithm via `--manifest-checksums` where supported.

### 17.5. Manifests Do Not Prove Future Archives

Passing verification proves backup files match the manifest within tool scope. It does not prove an external WAL archive is complete up to future recovery targets.

### 17.6. Manifests Do Not Replace Restore Drills

A backup can pass verification yet still fail to restore due to missing external WAL, wrong tablespace paths, missing config, incompatible extensions, or misconfigured restore environments.

## 18. Other Useful Options

Exact options vary by major version; inspect `pg_basebackup --help` for your binary.

| Option | Purpose |
| --- | --- |
| `-D` | Destination directory |
| `-F` | Plain or tar |
| `-X` | WAL method |
| `-R` | Write standby configuration |
| `-S` | Replication slot name |
| `-C` | Create replication slot |
| `-P` | Show progress |
| `-v` | Verbose |
| `-l` | Backup label |
| `-c` | Checkpoint mode |
| `-r` | Transfer rate limit on supported versions |
| `-T` | Tablespace mapping |
| `-z`/`-Z` | Tar/backup compression depending on version |
| `--no-sync` | Skip syncing files to disk; risky on power loss/crash |
| `--manifest-checksums` | Select manifest checksum algorithm on supported versions |

### 18.1. `--no-sync`

Do not use in normal production backups. Skipping final fsync lets the command return before backup data is guaranteed durable on storage; power loss or crashes can corrupt the backup.

### 18.2. Compression

Newer releases offer various compression methods/levels. Compression cuts transferred/stored bytes at the expense of CPU and may lengthen backup/restore times.

### 18.3. Incremental Backups

PostgreSQL 17+ introduces incremental physical backup workflows via `pg_basebackup` and `pg_combinebackup`. An incremental backup depends on a prior backup and is not standalone; keep the chain intact and combine properly before restoring. Do not pass incremental options to unsupported older servers/clients.

## 19. Storing and Protecting Backups

### 19.1. Separate from the Source Server

Never store backups solely on the same disk/host as `PGDATA`. Losing the host or disk would destroy both data and backups.

### 19.2. Offsite Copies

Keep copies in another failure domain, such as an independent region/account/storage system per organizational policy.

### 19.3. Encryption

Encrypt in transit and at rest. Manage keys independently of the backup repository; losing the key means losing restorability.

### 19.4. Access Control

Grant read/write access only to necessary backup services and restore operators. Protect against accidental deletion and ransomware using immutable retention/versioning where appropriate.

### 19.5. Backup Metadata

Store backup ID, timestamp, server identity, version, start/stop LSN, timeline, format, tablespace map, checksums, and WAL dependencies.

### 19.6. Do Not Modify Files After Manifest Creation

Compressing, encrypting, renaming, or moving files after manifest generation can cause verification to fail or restore tooling to miss files. If transforms are needed, record metadata and verify post-transform in a controlled pipeline.

## 20. Restoring a Plain-Format Backup

Suppose the plain backup is at `/backup/base_plain` and the restore data directory is `/var/lib/postgresql/16/main`.

### 20.1. Stop the Target Server

~~~bash
pg_ctl -D /var/lib/postgresql/16/main stop
~~~

Never overwrite a data directory currently in use by a running server.

### 20.2. Prepare the Data Directory

Use an empty directory with ownership and permissions matching the PostgreSQL OS user. Preserve any custom configs before replacing.

### 20.3. Copy/Extract the Backup

If the backup is already a plain directory, place the entire backup structure into the target data directory following the exact layout. Ensure tablespace symlinks point to restored locations.

### 20.4. File Permissions

~~~bash
chown -R postgres:postgres /var/lib/postgresql/16/main
chmod 700 /var/lib/postgresql/16/main
~~~

Linux example using user/group `postgres`; adjust for your package/OS. Never blindly run recursive `chown` across tablespace mounts outside the backup.

### 20.5. Server Configuration

Inspect `postgresql.conf`, `pg_hba.conf`, ident, SSL files, archive settings, port, `listen_addresses`, `shared_preload_libraries`, and external path settings.

### 20.6. Start and Monitor Recovery

~~~bash
pg_ctl -D /var/lib/postgresql/16/main start
~~~

PostgreSQL reads control/backup metadata and replays required WAL to bring the base backup to a consistent state. Check server logs to confirm recovery completes.

### 20.7. Never Run `initdb` on a Backup

`initdb` initializes a new cluster and can destroy backup contents if run against that data directory. Restoring a physical backup never uses `initdb`.

## 21. Restoring a Tar-Format Backup

Tar backups must be extracted into the exact expected layout:

~~~bash
mkdir -p /restore/pgdata
tar -xf /backup/base_tar/base.tar -C /restore/pgdata
~~~

If `pg_wal.tar` exists:

~~~bash
mkdir -p /restore/pgdata/pg_wal
tar -xf /backup/base_tar/pg_wal.tar -C /restore/pgdata/pg_wal
~~~

Tablespace tar files must be extracted into directories corresponding to the mapped tablespaces.

### 21.1. Inspecting Tar Contents

~~~bash
tar -tf /backup/base_tar/base.tar | head
~~~

### 21.2. Tablespace Archives

Tablespace tar filenames usually correspond to OIDs. Cross-check `tablespace_map` and catalog metadata to place each archive in the right target.

### 21.3. Owner and Mode

After extraction, ensure ownership/permissions match the PostgreSQL OS account. Tablespace symlinks must point to valid paths.

### 21.4. WAL Tar

If WAL is stored in a separate archive, place it inside `pg_wal` per the exact layout. Never extract `pg_wal.tar` directly into the root of `PGDATA`.

### 21.5. Verify After Extraction

Cross-check file inventory/checksums against the manifest if supported by format. Then run a restore drill.

## 22. PITR Restore from a Base Backup

A base backup provides the initial data directory; a WAL archive lets you replay forward to a later target.

### 22.1. Preparing the Archive

Ensure the restore host can read required WAL segments and timeline history files.

### 22.2. `restore_command`

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

The command must place the raw file at `%p` and return an accurate exit code. If archived files are compressed/encrypted, decompress/decrypt them into `%p`.

### 22.3. `recovery.signal`

On PostgreSQL 12+, create `recovery.signal` in `PGDATA` to initiate archive recovery.

~~~bash
touch /restore/pgdata/recovery.signal
~~~

### 22.4. Recovery Target Time

~~~conf
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

Use explicit timezone offsets. Other targets include LSN, named restore point, and transaction ID.

### 22.5. Timeline

~~~conf
recovery_target_timeline = 'latest'
~~~

Pick the timeline matching your goal. If recovering onto a specific historical branch, set the explicit timeline ID rather than blindly using `latest`.

### 22.6. Monitoring Recovery

Read PostgreSQL logs, inspect recovery state, and confirm the target was reached. When action is `pause`, the server pauses replay at the target so you can inspect before promoting/resuming.

### 22.7. `recovery.signal` vs. `standby.signal`

`recovery.signal` is for archive recovery/PITR; `standby.signal` is for running a standby. Do not confuse or leave the wrong file present during a restore.

## 23. External Configuration Files and Restore Environment

Not everything PostgreSQL needs lives inside a physical backup.

### 23.1. Config Files Outside `PGDATA`

If `config_file`, `hba_file`, or `ident_file` point outside `PGDATA`, `pg_basebackup` does not automatically copy those external files. Back up configs separately and verify restore paths.

### 23.2. SSL Certificates

Certificates/keys may sit outside the data directory. Restores need matching files, owner/mode, and secrets.

### 23.3. Extensions

Physical backups contain extension catalog objects, but shared libraries/binaries and OS packages must be installed on the restore host at compatible versions.

### 23.4. Locale and Collation

OS/locale/collation differences can affect index semantics and operation. Keep the restore environment compatible and check collation versions post-recovery when needed.

### 23.5. OS/Architecture

Physical backups are not portable formats like SQL dumps. Use the same PostgreSQL major version and compatible platform/build; never restore file-level backups directly onto a different major version.

## 24. Version Compatibility and Incremental Backups

### 24.1. Same Major Version

Physical base backups are restored by a server of the same major version. Minor release compatibility holds within the same major version, though matching patch levels and checking extensions/platforms remain good practice.

### 24.2. Different Major Version

Never use `pg_basebackup` as a direct upgrade path from PostgreSQL 15 to 16 or 17. Use `pg_upgrade` or a planned logical migration.

### 24.3. Tool Version

Use `pg_basebackup`/`pg_verifybackup` from tooling matching the server. Options and manifest features can differ across major versions.

### 24.4. Incremental Backups in PostgreSQL 17+

PostgreSQL 17 adds incremental physical backups. An incremental run references the prior backup's manifest; the chain depends on all linked backups.

### 24.5. `pg_combinebackup`

Use `pg_combinebackup` to merge a full backup and incremental backups into one complete data directory before restoring per supported workflow.

### 24.6. Retention of Incremental Chains

Never delete a full backup or base incremental backup while newer incremental backups still depend on it. Manage chains as dependency units.

## 25. Verifying That a Backup Is Restorable

A reliable backup pipeline layers multiple checks:

1. `pg_basebackup` exited with success.
2. Destination file inventory looks valid.
3. `backup_manifest` is present if supported by format/version.
4. `pg_verifybackup` passes on plain backups.
5. Required WAL is readable and matches cluster/timeline.
6. Tablespace paths and external configs are available.
7. Test restore onto an isolated host succeeds.
8. PostgreSQL reaches ready state.
9. Business queries/invariants pass.
10. RTO is measured and meets target.

### 25.1. File Existence Is Insufficient

A backup with full expected size may still miss files, fail checksums, or lack WAL.

### 25.2. Passing Verify Is Insufficient

Verify does not test infrastructure, secrets, extension libraries, DNS, networking, application credentials, or the WAL archive up to every target.

### 25.3. Test Restores Are the Strongest Proof

Only an actual test restore verifies extraction, ownership, configuration, WAL replay, and application validation working end-to-end.

## 26. Backup Retention and WAL Retention

A base backup requires WAL from its start point until the backup becomes consistent; a PITR window requires additional WAL afterward up to the target.

### 26.1. Full Backup Retention

Retain base backup counts/ages matching RPO/RTO, compliance, and storage costs.

### 26.2. WAL Dependencies

Every backup has a required WAL range. While retaining that backup, never delete WAL segments needed for restoring the backup or meeting committed target windows.

### 26.3. Do Not Delete Simply by Age

Deleting all WAL older than 7 days can break restorability of an older base backup still kept under retention.

### 26.4. Backup Catalog

Track backup ID, start/stop LSN, timeline, required WAL, manifest checksums, tablespaces, and verification status.

### 26.5. Dedicated Backup Managers

pgBackRest, WAL-G, and similar backup managers handle repositories, retention, and archive lifecycles. Pick one system with clear ownership and avoid conflicting retention jobs.

## 27. RPO, RTO, and Backup Schedules

### 27.1. RPO

Recovery Point Objective is the maximum acceptable data loss. With a physical base backup plus WAL archive, RPO depends on archive lag and retrievability of the latest WAL.

### 27.2. RTO

Recovery Time Objective is the target time to restore service. RTO depends on backup size, restore throughput, WAL replay volume, startup, and application validation.

### 27.3. Frequent Base Backups

More frequent base backups reduce how much WAL must be replayed and can lower RTO, at the cost of extra storage, network bandwidth, and source load.

### 27.4. Frequent WAL Archiving

Continuous archiving enables PITR close to the present. Segment switches/`archive_timeout` and archive throughput govern lag.

### 27.5. Workload-Driven Scheduling

Set schedules based on database growth, WAL rate, tested restore times, retention, and off-peak windows. No single schedule fits every cluster.

## 28. Monitoring `pg_basebackup` and Backup Repositories

Track these metrics:

| Metric | Meaning |
| --- | --- |
| Backup start/end time | Backup timing |
| Backup duration | Load impact and RTO input |
| Backup bytes | Storage growth rate |
| Backup exit status | Success/failure |
| Source server/cluster ID | Correct source verification |
| Start/stop LSN | WAL dependencies |
| WAL method | `stream`/`fetch`/`none` |
| Tablespace inventory | All tablespaces present |
| Manifest verify result | Integrity |
| WAL archive lag | PITR readiness |
| Restore drill result | Recoverability |
| Repository free space | Capacity headroom |
| Retention age | Policy compliance |

### 28.1. Monitoring WAL Senders

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

`pg_basebackup` connections appear in `pg_stat_replication` in appropriate states. Interpret per server version and client `application_name`.

### 28.2. Monitoring Replication Slots

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    wal_status
FROM pg_replication_slots;
~~~

If a slot stays inactive long with an old `restart_lsn`, inspect how much WAL is pinned.

### 28.3. Backup Logs

Capture stdout/stderr, exit code, and tool version. Never log merely "backup completed" without identifying metadata.

## 29. Common Errors When Running `pg_basebackup`

### Error 1. Replication permission denied

The role lacks `LOGIN`/`REPLICATION` or is not permitted by `pg_hba.conf`.

### Error 2. No `pg_hba.conf` entry

Rules fail to match host, user, `database=replication`, SSL mode, or rule ordering.

### Error 3. Too many replication connections

`max_wal_senders` is too low for concurrent backups, WAL streaming, and standbys.

### Error 4. Replication slot limit reached

`max_replication_slots` is exhausted or the slot name already exists.

### Error 5. Destination not empty

The backup directory has old files or violates emptiness rules. Use a verified dedicated destination.

### Error 6. Disk full

Backup destination ran out of space or hit filesystem quotas.

### Error 7. WAL removed before fetch

Using WAL method `fetch`, the server recycled needed segments before fetch finished. Switch to `stream` or size retention properly.

### Error 8. Server restart/failover during backup

Connection dropped; the backup may be incomplete. Inspect logs and run a fresh backup per procedure.

### Error 9. Password authentication failed

Wrong/expired secret, malformed `.pgpass` permissions/format, or mismatched auth policy.

### Error 10. TLS verification failure

Certificate, CA, or hostname mismatch. Do not disable TLS verification as a default fix.

### Error 11. Tablespace path unavailable

Tablespace mount is missing or the OS user lacks permissions.

### Error 12. Backup folder exists

Target directory already exists and is non-empty. Never overwrite an existing backup you need to retain.

### Error 13. Manifest mismatch

Files were altered, deleted, or corrupted post-backup. Run `pg_verifybackup` and inspect repository integrity.

### Error 14. Restore server major version mismatch

Physical files cannot restore directly onto a different major version.

### Error 15. Missing WAL during recovery

Backup lacks required WAL or the archive chain has a gap/early retention purge.

### Error 16. Missing tablespace files

Not all tablespaces were backed up/extracted or symlinks point to wrong paths.

### Error 17. Extension library missing

Catalogs reference an extension, yet the restore host lacks compatible shared libraries/packages.

### Error 18. Wrong ownership

Data directory or tablespaces are not owned by the PostgreSQL OS user.

### Error 19. `-R` creates an unintended standby

A backup restored as an independent primary still carries `standby.signal`/`primary_conninfo`. Check recovery target before starting.

### Error 20. Backup succeeds yet never tested on restore

Config, path, extension, WAL, and secret issues stay hidden until a real incident hits. Run scheduled restore drills.

## 30. Sample Daily Backup Workflow

A baseline pipeline can include:

~~~text
Scheduler
   |
   v
Preflight
   |-- source reachable?
   |-- replication role works?
   |-- enough disk and WAL senders?
   |-- destination isolated and empty?
   |
   v
pg_basebackup
   |-- plain format
   |-- WAL stream
   |-- progress + log
   |
   v
Verify
   |-- exit code
   |-- manifest
   |-- pg_verifybackup
   |-- tablespace inventory
   |
   v
Publish backup metadata
   |
   v
Offsite copy / immutable retention
   |
   v
Periodic restore drill
~~~

### 30.1. Preflight

Verify server reachability, replication access, sender capacity, slot capacity, disk space, mounts, and destination readiness.

### 30.2. Backup

Run `pg_basebackup` with chosen format/WAL method and capture logs.

### 30.3. Verify

For plain backups with manifests, run `pg_verifybackup`. Verify metadata files and tablespaces too.

### 30.4. Publish

Mark a backup usable only after both the backup command and verification pass. Use a temporary/in-progress state before publishing the final backup ID.

### 30.5. Offsite

Copy backups and metadata to a repository in a different failure domain. Re-verify checksums after transfer.

### 30.6. Retention

Prune backups/WAL strictly following dependencies tracked in the backup catalog.

## 31. Restore Drills and Application Verification

A restore drill must run on an isolated host/volume:

1. Select a backup per policy and verify its manifest.
2. Fetch required WAL archive segments if testing PITR.
3. Provision PostgreSQL of the same major version and compatible extension binaries.
4. Restore plain files or extract tar/tablespaces.
5. Restore external configurations outside `PGDATA` and secrets.
6. Configure archive recovery if needed.
7. Start PostgreSQL and watch recovery logs.
8. Confirm the server reaches ready state and hits the recovery target.
9. Run queries verifying schemas, data, and business invariants.
10. Measure duration, throughput, WAL replay, and RTO.
11. Save results, errors, and runbook updates.

### 31.1. Never Test Restores on Production

Never overwrite production `PGDATA` or alter the primary merely to test. Use a dedicated restore environment.

### 31.2. Test Failure Cases Too

Simulate missing WAL, checksum mismatches, broken tablespace mounts, missing credentials, or missing extension packages in the lab to ensure your runbook catches them.

### 31.3. Restore Points and PITR

When recovering before a bad operation, specify a target time/LSN/named restore point along the backup chain and verify data past the target.

### 31.4. Measuring RTO

Record transfer, extraction, startup/replay, and validation durations separately. Actual end-to-end duration reflects the RTO experienced by applications.

## 32. Backups, WAL, and Checkpoints

### 32.1. Checkpoint

A checkpoint flushes dirty buffers and creates a recovery point in WAL. Checkpoints are not base backups and do not replace backup repositories.

### 32.2. WAL

WAL guarantees crash recovery consistency and enables replaying changes after a base backup.

### 32.3. Base Backup

A base backup captures data files over an interval plus recovery metadata.

### 32.4. Archive

A WAL archive stores historical segments outside the server so they can be replayed even after `pg_wal` recycles them.

### 32.5. Putting Them Together

Checkpoints, WAL, and base backups are distinct components in durability/recovery. Do not substitute one for another.

## 33. `pg_basebackup` and Backup Management Tools

### 33.1. `pg_basebackup`

Built-in, straightforward tool using the replication protocol. Ideal for creating physical base backups and bootstrapping standbys.

### 33.2. pgBackRest

Dedicated backup/restore manager offering repositories, compression, encryption, retention, parallelism, and configured WAL archiving.

### 33.3. WAL-G

Popular backup/WAL archiving tool supporting object storage and backup/restore workflows.

### 33.4. `pg_verifybackup`

Tool for validating plain-format backup manifests per version capabilities.

### 33.5. `pg_combinebackup`

Used with incremental backup workflows in PostgreSQL 17+ to combine required backups.

### 33.6. Choosing a Tool

If you only need a basic base backup, `pg_basebackup` may suffice. If you need complex retention, incremental/differential workflows, parallelism, encryption, and repository management, consider a dedicated backup manager.

## 34. Practice Exercises

Exercises use an isolated PostgreSQL lab. Never run backup/restore commands that overwrite data on production.

### Exercise 1. Physical Backup

At what level does a physical backup copy data?

### Exercise 2. Logical Backup

State one key difference between `pg_basebackup` and `pg_dump`.

### Exercise 3. Cluster Scope

Why does `pg_basebackup` typically back up the entire cluster rather than a single table?

### Exercise 4. Online Backup

Why can't you back up a running `PGDATA` using an ordinary filesystem copy command?

### Exercise 5. WAL

What role does WAL play in an online physical backup?

### Exercise 6. Replication Role

What privileges does the role running `pg_basebackup` need?

### Exercise 7. `pg_hba`

Write a sample `hostssl` rule for a replication user from a private subnet.

### Exercise 8. `max_wal_senders`

Why might `-X stream` require two WAL sender connections?

### Exercise 9. `max_replication_slots`

Which workflow does this parameter relate to?

### Exercise 10. Plain Format

What structure does plain format store backups in?

### Exercise 11. Tar Format

Why do tar backups require extracting tablespaces separately?

### Exercise 12. WAL `stream`

What is the primary advantage of `-X stream`?

### Exercise 13. WAL `fetch`

What is the main risk of `-X fetch`?

### Exercise 14. WAL `none`

When can `-X none` be used?

### Exercise 15. Progress

Which option displays backup progress?

### Exercise 16. Checkpoint

What is the difference between `fast` and `spread` checkpoints?

### Exercise 17. Rate Limit

When should you throttle backup transfer speed?

### Exercise 18. Tablespaces

Write SQL to list tablespaces and their locations.

### Exercise 19. Mapping

What does `-T olddir=newdir` mean?

### Exercise 20. `-R`

What files/settings does `-R` generate?

### Exercise 21. Replication Slots

Why can an inactive slot cause `pg_wal` to grow?

### Exercise 22. Backup from Standby

List two conditions to verify when backing up from a standby.

### Exercise 23. Manifest

What does `backup_manifest` help with?

### Exercise 24. `pg_verifybackup`

What does this tool verify, and which format is supported directly?

### Exercise 25. Restore

Why should you never run `initdb` on a restored data directory?

### Exercise 26. Tar Restore

Where must `pg_wal.tar` be extracted?

### Exercise 27. PITR

Name three components required to restore a base backup to a recovery target.

### Exercise 28. `recovery.signal`

What is this file used for in PostgreSQL 12+?

### Exercise 29. Major Version

Can a PostgreSQL 15 physical backup be restored directly onto PostgreSQL 16?

### Exercise 30. External Config

Why must a `config_file` located outside `PGDATA` be backed up separately?

### Exercise 31. Incremental Backup

Which tool does PostgreSQL 17 incremental backup require to combine a chain?

### Exercise 32. Retention

Why should you not delete WAL solely based on file age?

### Exercise 33. RPO

How does WAL archive lag affect RPO?

### Exercise 34. RTO

List three factors that increase restore duration.

### Exercise 35. Backup Metadata

Name at least five fields to record for every backup.

### Exercise 36. Backup Failure

Name four reasons `pg_basebackup` can fail.

### Exercise 37. Verify Failure

What can a manifest mismatch indicate?

### Exercise 38. Restore Drill

List five key steps of a restore drill.

### Exercise 39. Logical vs. Physical

When backing up a single table, which approach should you choose?

### Exercise 40. Design

Propose a pipeline from `pg_basebackup` through verification, offsite retention, and restore testing.

## 35. Reference Solutions

### Exercises 1–5. Physical and WAL

Physical backups copy cluster storage files. `pg_basebackup` creates a cluster-wide physical copy via the replication/backup protocol; `pg_dump` exports schemas/data at the SQL level and can select databases/tables. Do not arbitrarily copy a running `PGDATA` because files may reflect different points in time. WAL enables replay to bring the backup to consistency.

### Exercises 6–9. Privileges and Capacity

The role needs `LOGIN` and `REPLICATION` (or equivalent admin privileges). Example:

~~~sql
CREATE ROLE backup_user WITH LOGIN REPLICATION PASSWORD 'use-a-secret';
~~~

`pg_hba`:

~~~conf
hostssl replication backup_user 10.20.0.0/24 scram-sha-256
~~~

`-X stream` can open one connection for the base backup and one for streaming WAL. `max_wal_senders` must cover those two connections plus active standbys/other backups. `max_replication_slots` caps replication slot count.

### Exercises 10–14. Format and WAL Methods

Plain preserves the data directory layout; tar packages base/WAL/tablespaces into tar archives. Tar tablespaces must be extracted to exact paths. `stream` fetches WAL concurrently; `fetch` retrieves it afterward so WAL must remain on the server; `none` requires an external WAL workflow guaranteeing consistency.

### Exercises 15–17. Speed

`-P` displays progress. Fast checkpoints complete quickly at the risk of I/O spikes; spread distributes load. Rate limiting helps protect production workloads at the expense of longer backups and WAL retention.

### Exercises 18–20. Tablespaces and Standby

~~~sql
SELECT spcname, pg_tablespace_location(oid)
FROM pg_tablespace;
~~~

`-T` remaps old tablespace paths to new paths where supported by format/version. `-R` creates `standby.signal` and writes connection settings into `postgresql.auto.conf`.

### Exercises 21–22. Slots and Standby

An inactive slot retains WAL from `restart_lsn` so its consumer could still read it, potentially filling `pg_wal`. When backing up from a standby, check standby state/`hot_standby`, sender capacity, WAL availability, and `full_page_writes` on the primary.

### Exercises 23–24. Verification

`backup_manifest` lists files/checksums. `pg_verifybackup` validates plain-format backups against the manifest and supported WAL checks; it does not replace restore tests and does not run directly on tar backups like plain directories.

### Exercises 25–30. Restore

Never run `initdb` because it initializes a brand-new cluster. Extract `pg_wal.tar` into `PGDATA/pg_wal`. PITR requires a base backup, a WAL chain, and restore settings/targets. `recovery.signal` initiates archive recovery in PostgreSQL 12+. Physical backups do not restore directly across major versions. Config files outside `PGDATA` must be backed up separately.

### Exercise 31. Incremental

Use `pg_combinebackup` to combine full and incremental backups in PostgreSQL 17+ workflows.

### Exercises 32–34. Retention and Objectives

Old WAL may still be needed by a retained base backup. Archive lag increases potential data loss and affects RPO. Slow restores stem from large backups, slow storage/networking, heavy WAL replay, and long application validation.

### Exercise 35. Metadata

Examples: backup ID, source host, system identifier, PostgreSQL/tool versions, timestamps, start/stop LSN, timeline, format, WAL method, tablespace map, manifest/checksum, verification status.

### Exercises 36–37. Errors

Causes: wrong replication/`pg_hba` permissions, insufficient `max_wal_senders`, slot limits, disk full, non-empty destination, WAL recycled during fetch, network/TLS errors, tablespace mount errors. Manifest mismatch signals missing/changed/corrupted files or post-backup modification.

### Exercise 38. Restore Drill

Select backup; verify manifest and WAL dependencies; restore into isolated environment; configure tablespaces/configs/recovery; start and replay WAL; validate business data; record durations and results.

### Exercises 39–40. Choosing Solutions

Backing up a single table normally uses `pg_dump` or logical export. A physical backup pipeline includes preflight, `pg_basebackup`, exit/log checks, `pg_verifybackup` for plain backups, metadata inventory, offsite copying, WAL-dependency-aware retention, and periodic restore drills.

## 36. Quick Reference Table

| Need | Tool/Option |
| --- | --- |
| Create physical backup | `pg_basebackup` |
| Set destination directory | `-D` |
| Choose plain/tar | `-F` |
| Stream WAL | `-X stream` |
| Fetch WAL after copy | `-X fetch` |
| Do not fetch WAL | `-X none` |
| Show progress | `-P` |
| Verbose | `-v` |
| Backup label | `-l` |
| Checkpoint mode | `-c fast` or `spread` |
| Limit transfer rate | `--max-rate` |
| Map tablespace | `-T olddir=newdir` |
| Generate standby config | `-R` |
| Create replication slot | `-C` |
| Specify slot name | `-S` |
| Verify plain backup | `pg_verifybackup` |
| Combine incremental chain | `pg_combinebackup` |
| List tablespaces | `pg_tablespace` |
| Monitor WAL senders | `pg_stat_replication` |
| Monitor slots | `pg_replication_slots` |
| PITR signal | `recovery.signal` |
| Standby signal | `standby.signal` |
| Recovery WAL retrieval | `restore_command` |

## 37. Physical Backup Operations Checklist

1. Determine whether the backup is physical or logical and define the protection scope.
2. Record PostgreSQL major/minor version and cluster system identifier.
3. Use a `pg_basebackup` binary matching the server.
4. Enable appropriate `wal_level` and verify `full_page_writes`.
5. Grant a `LOGIN`/`REPLICATION` role with least privilege.
6. Configure `pg_hba` replication rules, TLS, and secret storage.
7. Ensure `max_wal_senders` covers concurrent backups and standbys.
8. Ensure `max_replication_slots` suffices if using named slots.
9. Monitor slot lifecycles and WAL retention headroom.
10. Verify empty destination, disk quotas, and offsite repository.
11. Choose plain or tar based on restore/verify tooling.
12. Choose WAL `stream`/`fetch`/`none` deliberately.
13. Evaluate checkpoint mode, max rate, and backup duration.
14. Inventory all tablespaces.
15. Map tablespaces when restoring to different paths.
16. Preserve `backup_label`, `tablespace_map`, and `backup_manifest`.
17. Record start/stop LSN, timeline, and backup ID.
18. Log output/exit code and publish backups only after completion.
19. Run `pg_verifybackup` on plain backups with manifests.
20. Verify WAL archive dependencies.
21. Back up external configs/SSL/secrets outside `PGDATA` separately.
22. Keep compatible extension binaries and OS dependencies.
23. Encrypt backups and restrict access permissions.
24. Copy to a separate failure domain.
25. Enforce retention based on base backup and WAL dependencies.
26. Never delete WAL solely by file age.
27. Monitor backup duration, size, error rates, and repository free space.
28. Run test restores in an isolated environment.
29. Verify PostgreSQL startup and business invariants.
30. Record actual RTO, update runbooks, and run regular drills.

## 38. Summary

`pg_basebackup` creates a **physical base backup** of a running PostgreSQL cluster using the replication/backup protocol. It copies data files and coordinates WAL so the copy can be recovered consistently. Choose plain or tar format, `stream`/`fetch`/`none` WAL method, checkpoint mode, rate limits, and tablespace mappings according to restore goals and system load.

Safe operation requires proper replication access, sufficient WAL senders/slots, disk headroom, and aligned archive retention. Backups can be used for standalone restores, bootstrapping standbys with `-R`, or serving as the foundation for PITR with a WAL archive. Manifests and `pg_verifybackup` catch several file-level issues, yet only restore drills verify the entire path from backup to a functioning database.

Manage every backup alongside metadata covering cluster, version, LSN, timeline, tablespaces, checksums, and WAL dependencies. Keep backups in an isolated failure domain, protect keys/configs, enforce chain-aware retention, and test restores regularly. A physical backup holds real value only when the organization can locate the right files, replay the right WAL, and bring applications back within committed RPO/RTO.
