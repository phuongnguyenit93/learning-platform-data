# Upgrading Primary, Standbys, and Backup Tooling in Proper Order

`pg_upgrade` is the PostgreSQL utility for migrating data between major versions; logical replication and dump/restore are two other options. When a cluster includes a primary, physical standbys, and a backup system, the upgrade must be planned across the entire operational chain. The primary, standbys, replication slots, WAL archive, backup repository, backup agents, and restore tools must all align on the same cluster state after cutover.

A new version number on the primary does not mean old standbys can keep replaying WAL. Physical replication operates on WAL and block layouts at the physical level; after a major upgrade, standbys must be transitioned to the new cluster via the appropriate procedure. Backup tooling must also be upgraded and verified for compatibility before modifying the database so both the old cluster and the target cluster remain protected.

```text
                 Backup repository
                        ^
                        | backup / WAL archive
                        |
       +----------------+----------------+
       |                                 |
       v                                 v
  +-----------+    physical WAL     +-----------+
  | Primary   | ------------------> | Standby 1 |
  | old/new   |                     | old/new   |
  +-----------+                     +-----------+
       |
       | logical changes (optional major upgrade path)
       v
  +-----------+
  | New       |
  | subscriber|
  +-----------+

  Backup tooling, repository metadata and restore binaries
  must be compatible with the cluster version being protected.
```

This lesson belongs to the **Upgrades** chapter of the *Database Engine Relational PostgreSQL* module. Its focus is sequencing operations to protect recoverability, maintain HA within the chosen downtime budget, and avoid leaving behind an incompatible primary/standby or backup repository.

After this lesson, you will be able to:

1. Distinguish minor updates from major upgrades.
2. Understand why physical replication requires nodes on the same major version and cluster identity.
3. Inventory the primary, standbys, replication slots, extensions, and backup tools.
4. Upgrade backup tooling and verify restore capability before modifying the database.
5. Choose among `pg_upgrade`, logical replication, and dump/restore.
6. Execute the correct upgrade sequence for the primary and physical standbys.
7. Know when to use the rsync link-mode procedure and when to rebuild standbys from a base backup.
8. Synchronize the WAL archive, backup metadata, repository configuration, and restore tools.
9. Verify replication, backups, restores, application behavior, and performance after cutover.
10. Build a rollback plan with clear boundaries and identify the point of no return to the old cluster.

> **Operational principle:** Before upgrading, you must have a restorable backup and a recent restore test. Never delete the old data directory, old binaries, old backup chain, or WAL archives required for recovery until you have confirmed the new cluster works and a new backup is restorable.

---

## 1. Understanding Upgrade Scope

### 1.1. Minor Releases vs. Major Releases

PostgreSQL minor releases deliver bug fixes, security patches, and compatibility fixes within the same major version. Minor releases preserve internal storage formats; normally, you swap binaries to the new minor version and restart the server per plan. Primary and standbys remain on the same major version.

Major releases can change system catalogs, internal storage formats, WAL behavior, the planner, replication features, and extension APIs. You cannot simply swap binaries and open an old data directory with a new major version. A supported migration method is required.

Examples:

| Change | Type | Approach |
|---|---|---|
| PostgreSQL 17.2 to 17.6 | Minor update | Upgrade binaries and restart following HA procedure |
| PostgreSQL 16 to 17 | Major upgrade | `pg_upgrade`, logical replication, or dump/restore |
| pgBackRest 2.x to minor 2.y | Backup tooling update | Review release notes and repository compatibility |
| Backup agent to version supporting new PostgreSQL | Tooling update | Upgrade and test before database cutover |

### 1.2. Three Version Layers to Track

A cluster involves three independent version layers:

- **Database server:** PostgreSQL major/minor version on the primary and each standby.
- **Backup/replication tooling:** pgBackRest, Barman, WAL-G, `pg_basebackup` client, monitoring/agent binaries, and automation.
- **Extensions and client drivers:** shared libraries, extension SQL scripts, JDBC/libpq/ORM drivers, and application dependencies.

A new server does not automatically guarantee that extension binaries, backup agents, or application drivers are compatible.

### 1.3. Scope of an HA Cluster

The inventory covers more than just a primary and one standby. Include:

- Physical standbys and cascading standbys.
- Synchronous replication settings and the failover manager.
- Replication slots, WAL senders/receivers, and archive commands.
- Backup host, repository host, object storage, and retention jobs.
- Monitoring, alerting, connection pools, and proxies.
- Extensions, tablespaces, custom libraries, and authentication.
- Scheduled jobs, cron/systemd services, secrets, and certificates.

Each component may hold its own binary/data directory path or pinned version.

### 1.4. Defining Objectives and Downtime

Before choosing a method, establish:

- Maximum allowable downtime.
- Required RPO/RTO.
- Database size and write rate.
- Number of standbys and topology.
- Ability to run a new host/cluster in parallel.
- Feasibility of creating logical publications/subscriptions.
- Backup retention and restore duration.
- Rollback window and criteria for closing rollback.

`pg_upgrade` usually incurs downtime during cluster conversion; logical replication can shorten cutover downtime but requires more careful schema/data/sequence preparation and synchronization.

---

## 2. Compatibility Principles You Must Know

### 2.1. Physical Replication Is Not a Major-Version Migration

Streaming replication and WAL shipping transmit changes at the physical block/WAL level. The primary and standby must run the same major version and share the same PostgreSQL cluster identity. A PostgreSQL 16 standby cannot keep replaying WAL from a PostgreSQL 17 primary as an ordinary standby.

Therefore, a major upgrade requires creating a new cluster and moving standbys to the new data directory/cluster. Never just install new PostgreSQL binaries on an old standby and restart it.

### 2.2. Minor Versions Within the Same Major

Minor releases within the same major version preserve physical storage compatibility. Even so, follow the binary update and HA restart sequence mandated by your platform/failover tooling. With synchronous replication, evaluate how restarting a standby or primary affects commit latency and availability.

### 2.3. A Standby Is Not an Independent Copy to Upgrade Arbitrarily

A physical standby must share the primary's cluster identity, timeline/WAL history, and state. Running `initdb` or `pg_upgrade` independently on a standby produces a different system identifier and prevents receiving WAL from the upgraded primary.

Two common paths exist after `pg_upgrade`:

1. If using link mode, you can use PostgreSQL's specialized `rsync` procedure to replicate the upgraded primary's hard links onto old standbys.
2. If using copy/clone mode, do not use that rsync hard-link procedure; the straightforward approach is rebuilding standbys from the new primary via a base backup or equivalent restore method.

Never stitch data directories together manually without following an officially documented PostgreSQL procedure.

### 2.4. Logical Replication Is a Different Mechanism

Logical replication streams row changes via publications/subscriptions and can operate across major versions. It suits standing up a subscriber on the new version while the old publisher continues serving writes.

Logical replication does not automatically transfer the entire cluster state. DDL/schema changes, sequence states, large objects, roles, tablespaces, extension state, and certain object types require separate handling.

### 2.5. Physical Backup vs. Logical Backup

Physical base backups and WAL archives are tied to cluster/version/timeline and require matching PostgreSQL binaries to restore. Never assume a PostgreSQL 16 physical backup can restore directly into PostgreSQL 17.

Logical dumps via `pg_dump`/`pg_restore` are far more portable across major versions. Use `pg_dump` from the target version or newer per the compatibility matrix; an older `pg_dump` cannot dump a newer major server version.

### 2.6. Cluster Identity and System Identifier

`system_identifier` uniquely identifies a PostgreSQL cluster. Inspect it with:

```bash
pg_controldata -D /path/to/data | grep "Database system identifier"
```

On Windows, run `pg_controldata.exe` from the `bin` directory and inspect the corresponding output. Physical primary and standbys must share the same cluster identity. After a major upgrade, verify the new primary and new standbys have matching identities per procedure.

### 2.7. WAL and Timelines

After a promotion or major migration, timelines can change. Archive destinations, `restore_command`, replication slots, and the backup catalog must track the exact cluster/timeline. Never mix WAL from the old cluster into the new cluster's archive path unless your tool isolates namespaces/stanzas separately.

---

## 3. Inventory and Compatibility Matrix

### 3.1. Record the Topology

On each server:

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    pg_is_in_recovery() AS is_standby,
    current_setting('data_directory') AS data_directory,
    current_setting('wal_level') AS wal_level;
```

On the primary, check replication:

```sql
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
FROM pg_stat_replication
ORDER BY application_name;
```

On standbys:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

Lag timestamps can be misleading when workloads are idle; compare LSNs and receiver/replay status.

### 3.2. Inventory Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Document physical and logical slots separately, along with owners/applications, retention implications, and how they will be recreated post-upgrade. Unconsumed slots retain WAL and can fill `pg_wal`.

### 3.3. Inventory Extensions

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n ON n.oid = e.extnamespace
ORDER BY e.extname;
```

Record shared library versions on the OS, not just `extversion` in the catalog. C extensions require binary builds compiled for the new major version; many extensions require dedicated packages for the target PostgreSQL release.

### 3.4. Inventory Configuration

Record settings affecting replication, WAL, backups, and startup:

```sql
SELECT name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_preload_libraries',
    'wal_level',
    'archive_mode',
    'archive_command',
    'restore_command',
    'max_wal_senders',
    'max_replication_slots',
    'hot_standby',
    'primary_conninfo',
    'primary_slot_name',
    'synchronous_standby_names',
    'wal_keep_size',
    'max_wal_size',
    'max_connections'
)
ORDER BY name;
```

Some parameters apply only on a primary or standby; queries may need adjustment by version. Archive configuration files, include files, `postgresql.auto.conf`, service definitions, and environment variables.

### 3.5. Compatibility Matrix

Build a verification table for every component:

| Component | Current Version | Target Version | Compatibility Evidence |
|---|---|---|---|
| PostgreSQL primary |  |  | Release notes / upgrade docs |
| PostgreSQL standby |  |  | Physical replication procedure |
| pgBackRest/Barman/WAL-G |  |  | Version support matrix |
| Backup repository format |  |  | Tool documentation |
| Extensions |  |  | Vendor release notes/build |
| Monitoring/HA agent |  |  | Agent support matrix |
| JDBC/libpq/ORM |  |  | Driver release notes |
| OS/platform |  |  | PostgreSQL support matrix |

Never substitute “latest version supports PostgreSQL” for explicitly verifying the old major, target major, and repository format.

### 3.6. Read Release Notes for Every Skipped Major Version

If upgrading from PostgreSQL 14 to 18, read the migration notes for 15, 16, 17, and 18—not just the target version's notes. Check reserved keywords, removed parameters, changed defaults, catalog changes, authentication, extension APIs, and planner behavior.

---

## 4. Backup Tooling Upgrade Order

### 4.1. Why Must Backup Tooling Usually Be Prepared First?

Backup software must be able to:

- Connect to and read metadata from the old PostgreSQL cluster.
- Back up and restore the target major version.
- Archive and retrieve WAL for the right cluster.
- Understand the existing repository/catalog format.
- Run on the backup host and database hosts with the right binaries/configs.

If the target PostgreSQL major requires a newer backup tool version, upgrade the tool while the old database is still running and verify it can still read the old backup chain before cutover.

### 4.2. Do Not Upgrade Repository Formats by Guesswork

Backup tool binary version and repository format are two separate things. Some tools read old formats cleanly, yet upgrading a repository format may be one-way or require a dedicated migration step.

Before running repository upgrade commands:

1. Read the tool's release notes.
2. Confirm backward compatibility with the current repository.
3. Back up/copy metadata or the repository per vendor instructions.
4. Test upgrading on a repository clone.
5. Test restoring from the clone.
6. Upgrade the production repository only with a rollback plan in place.

### 4.3. General Safe Sequence

A common sequence:

1. Inventory backup chains, WAL archives, retention, and restore procedures.
2. Upgrade backup software/agents to a version supporting both old and target PostgreSQL majors.
3. Verify the new tool still backs up and restores the old cluster.
4. Take a full pre-upgrade backup and verify WAL archiving works.
5. Test restoring that backup into an isolated environment.
6. Upgrade the PostgreSQL primary and physical standbys using the chosen method.
7. Update `pg-path`/server paths and stanza/catalog metadata in the backup tool for the new cluster.
8. Take a fresh backup of the target cluster.
9. Test restoring the new backup and verify WAL recovery.
10. Retain old backup chains throughout the approved retention/rollback window.

Exact tool commands vary by product. Never apply pgBackRest's `stanza-upgrade` command to Barman, WAL-G, or other tools.

### 4.4. Example with pgBackRest

With pgBackRest, after PostgreSQL is upgraded to the new major version, update `pg-path` in all relevant configuration files and run `stanza-upgrade` for each configured repository. If the database is offline, pgBackRest documentation provides the `--no-online` option.

Illustrative example:

```bash
pgbackrest --stanza=main --repo=1 stanza-upgrade
```

If multiple repositories exist, run the operation for each repository according to your configuration. Verify exact commands and options for your installed pgBackRest release before executing.

### 4.5. Updating Database Paths

After a major upgrade, PostgreSQL's data directory or binary path often changes, for example:

```text
/var/lib/postgresql/16/main
/var/lib/postgresql/17/main
```

Update paths across primary/standby/backup hosts, service units, and agent configs. In multi-host pgBackRest deployments, verify primary paths, standby paths, and repository host configs.

### 4.6. WAL Archiving Must Be Verified

Before cutover, confirm the old primary archives WAL cleanly. After cutover, confirm the new primary archives WAL into the right namespace/repository for the new cluster.

Do not check only `archive_mode = on`; inspect archive status and logs:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Snapshot cumulative counters before and after. An incrementing `archived_count` does not prove the restore chain is intact; run a restore/PITR test.

### 4.7. Retention and Old WAL

Do not run retention/prune jobs during the transition unless you understand dependencies among full/differential/incremental backups and WAL segments. Keep the old chain and WAL needed to restore the old cluster throughout the rollback window.

### 4.8. Barman and WAL-G

With Barman, WAL-G, or other backup managers, verify:

- Supported server/agent versions.
- Backup catalog metadata and compression/encryption formats.
- WAL archive naming/namespaces.
- Restore commands and recovery configuration.
- Repository migration/retention semantics.
- Credentials, object storage endpoints, and encryption keys.

Use the check/backup/restore commands documented for your exact version. Never assume tools share the same stanza or catalog model.

---

## 5. Choosing a Major Upgrade Method

### 5.1. Comparing the Three Methods

| Method | Downtime | Advantages | Trade-offs |
|---|---|---|---|
| `pg_upgrade` | Usually requires cutover downtime | Fast, keeps data files, avoids large dumps | Requires compatibility checks, separate standby steps |
| Logical replication | Can shorten downtime | Old primary serves traffic during copy/sync | DDL, sequences, large objects, and cutover require manual handling |
| Dump/restore | Often long for large databases | Clear workflow, explicit schema/data conversion | Consumes time, storage, and bandwidth |

Choose based on data volume, downtime budget, ability to run in parallel, schema complexity, and testability.

### 5.2. When to Choose `pg_upgrade`

Choose `pg_upgrade` when:

- You want to preserve most data files and minimize migration time.
- Writes can stop during the cutover window.
- Source/target platforms and builds meet compatibility rules.
- Extensions have binaries and update scripts for the target major.
- Sufficient storage exists or link/clone mode is supported.
- You have a dedicated plan for physical standbys.

`pg_upgrade` migrates cluster data and catalogs; it does not replace upgrading OS packages, extensions, backup software, application drivers, or verifying behavior.

### 5.3. When to Choose Logical Replication

Choose logical replication when:

- Allowed downtime is shorter than dump/restore duration.
- You can provision a new target cluster running alongside the old one.
- Tables have suitable replica identities.
- Schema/DDL and sequence state can be synchronized separately.
- Writes can be controlled at cutover time.
- Workload and WAL rate will not push the subscriber far behind.

This is a data migration method, not a physical standby of the old primary. The subscriber is an independent cluster with schemas/data synced via publication/subscription.

### 5.4. When to Choose Dump/Restore

Dump/restore fits when:

- The database is modest in size or longer downtime is acceptable.
- You want controlled changes to schemas, encoding, tablespaces, or ownership.
- You want to clean out legacy objects.
- You need an auditable migration runnable per database.

To preserve global objects such as roles and tablespaces, dump them separately with `pg_dumpall --globals-only`. Dump each database with `pg_dump`; restore via `pg_restore` or `psql` depending on format.

### 5.5. No Method Automatically Migrates Every Component

Regardless of method, plan separately for:

- Roles, memberships, passwords, and authentication.
- Tablespaces and file paths.
- Extensions, shared libraries, and preload modules.
- Foreign servers, user mappings, and external credentials.
- Publications/subscriptions, replication slots, and HA agents.
- Large objects, sequences, and scheduled jobs.
- Monitoring, backup catalogs, WAL archives, and restore procedures.

---

## 6. General Preparation Before a Major Upgrade

### 6.1. Read Migration Notes and Test Applications

Read release notes for every skipped major version. Review:

- Removed/renamed configuration parameters.
- Changed defaults and planner behavior.
- Authentication/TLS changes.
- SQL behavior, reserved keywords, and collations.
- Extension API and shared library requirements.
- Replication slot/WAL behavior.
- Driver compatibility.

Run application integration tests against the target version before cutover.

### 6.2. Prepare Target Binaries

Install the target PostgreSQL major alongside the old binaries if supported by your platform. Verify executable paths, service names, data directory paths, and ports. Prevent the service manager from accidentally starting the wrong cluster.

### 6.3. Extensions and Preload Modules

Install target-major binaries for all C extensions before running `pg_upgrade` or creating the target cluster. Check `shared_preload_libraries` and modules loaded at startup.

Some extensions require `ALTER EXTENSION ... UPDATE` post-migration. Read extension docs; never assume `pg_upgrade` automatically updates all extension SQL objects.

### 6.4. Tablespaces and Custom Files

Inventory tablespace locations, symlinks, relocated `pg_wal`, custom full-text search dictionaries, certificates, key files, and external config files. Ensure target paths exist, ownership/permissions are right, and backups cover them.

### 6.5. Authentication and Networking

Prepare `pg_hba.conf`, `pg_ident.conf`, TLS certificates, `postgresql.conf`, include files, firewall rules, DNS/VIP/proxies, and connection pools. Test authentication from application hosts against the target endpoint in a test environment.

### 6.6. Backup and Restore Rehearsal

Before making changes:

1. Take a full backup using your current tooling.
2. Confirm WAL archiving / continuous archiving works.
3. Save backup metadata and encryption keys.
4. Test restoring into an isolated environment.
5. Start the restored cluster and run data checks.
6. Record backup, restore, and recovery times to validate RTO.

A backup exiting with code 0 is not enough; only a restore test proves usability.

### 6.7. Controlling Writes During the Cutover Window

Prepare how you will:

- Stop application writes or enable maintenance mode.
- Drain connection pools and background workers.
- Pause scheduled jobs/ETL.
- Block writes from unmanaged clients.
- Confirm no long-running transactions remain open.

Do not rely solely on a maintenance banner if background workers or services can still write to the old primary.

### 6.8. Record Baselines

Capture:

- Database/table/index sizes.
- Row counts and critical aggregates.
- Replication lag and slot inventory.
- Backup chain and last archived WAL.
- Query performance / `pg_stat_statements` snapshots.
- CPU, memory, I/O, connections, and latency.

Baselines enable meaningful post-upgrade behavioral comparisons.

---

## 7. Upgrading Primary and Physical Standbys with `pg_upgrade`

### 7.1. Understanding the Two Standby Upgrade Paths

PostgreSQL documents specific workflows for physical standbys after `pg_upgrade`:

- If the primary is upgraded in link mode, you can use `rsync` with hard links to build target standby data directories without recopying all relation files.
- If not using link mode, skipping the rsync procedure, or preferring a simpler approach, rebuild standbys after the new primary is up.

Never run `pg_upgrade` independently on each standby assuming they will synchronize with the new primary.

### 7.2. Before Stopping the Old Cluster

1. Confirm pre-upgrade backups are restorable.
2. Confirm all standbys are streaming and caught up.
3. Inspect replication slots, WAL archive, and timeline.
4. Install target PostgreSQL binaries and extension shared objects on primary and standby hosts.
5. Create the primary's target data directory per platform instructions.
6. Verify target configuration—specifically ensuring `wal_level` is not set to `minimal` if replication is needed.
7. Choose copy, link, or clone mode and run `pg_upgrade --check` with that exact mode.

### 7.3. `pg_upgrade --check`

Run the target version's `pg_upgrade` binary to check compatibility before the downtime window:

```bash
pg_upgrade \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --link \
  --check
```

These are Linux example paths; substitute actual package/platform paths and options. `--check` does not replace rehearsal on a clone. Read full output and fix extension/config incompatibilities before cutover.

### 7.4. Choosing Copy, Link, or Clone

| Mode | How It Works | Rollback |
|---|---|---|
| Copy (default) | Copies relation files to the new cluster | Old cluster can still be retained for fallback |
| Link (`--link`) | Hard-links relation files between old and new directories | Cannot use old cluster once new cluster starts |
| Clone (`--clone`) | Uses copy-on-write/reflink when supported by filesystem | Keeps old cluster logically independent |

Link and clone require data directories on the same filesystem with platform/filesystem support. Link mode is fast and saves space but imposes strict rollback limits. Clone mode requires reflink support. Run `--check` with the exact mode planned for production.

### 7.5. Synchronizing Primary/Standby Before Shutdown

For PostgreSQL's link-mode rsync procedure, the old primary and standbys must reach the exact same checkpoint. While shutting down the old primary, old standbys must still be running to receive the final changes.

After stopping all clusters, run `pg_controldata` on the old primary and each old standby; compare `Latest checkpoint location`. Values must match before proceeding with the standby-upgrade rsync procedure.

If checkpoint LSNs do not match, do not run rsync. Investigate WAL/replay lag and complete synchronization per documentation.

### 7.6. Stopping the Old Primary and Running `pg_upgrade`

Once writes are drained, confirm standbys have received and replayed final changes. Stop the old primary and old standbys in the order specified by your cluster runbook; keep them stopped during conversion.

Run `pg_upgrade` on the primary using the target binary. Example:

```bash
pg_upgrade \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --jobs=8 \
  --link
```

Do not start the new primary before finishing standby rsync if following the link-mode standby procedure.

### 7.7. Link Mode: Preparing Standby Directories

On each standby:

1. Install target PostgreSQL binaries and identical extension shared objects as on the new primary.
2. Ensure the target standby data directory either does not exist or is empty.
3. If `initdb` created a directory, remove the empty target directory per runbook after double-checking paths.
4. Preserve required config files: `postgresql.conf`, include files, `postgresql.auto.conf`, `pg_hba.conf`.
5. Stop the old standby if not already stopped.

Never leave existing data or an independently initialized cluster in the target standby directory before rsync.

### 7.8. Link Mode: rsync Hard Links

Run `rsync` from the upgraded primary, inside the parent directory containing both old and new cluster directories, for each standby:

```bash
rsync --archive --delete --hard-links --size-only --no-inc-recursive \
  old_cluster new_cluster standby-host:/path/to/cluster-parent
```

This is an illustrative template; adjust paths and remote targets to your directory layout. Run `--dry-run` first and verify source/destination carefully. `--delete` can remove destination files if paths are wrong.

`--hard-links` is the critical part of this workflow: `rsync` recreates on the standby the hard links between files already linked across old and new clusters on the primary. Unlinked files are copied.

If tablespaces exist, run corresponding `rsync` commands for each tablespace directory. If `pg_wal` resides outside the data directory, sync that path as documented as well.

### 7.9. Link Mode: Configuring Replication and Slots

After rsync:

- Restore/update configuration files on the standby.
- Configure `primary_conninfo`, `primary_slot_name`, `restore_command`, and archive settings appropriately.
- Verify `synchronous_standby_names` and the failover manager.
- Check/recreate replication slots according to major-version behavior.

Specifically, if the old primary is prior to PostgreSQL 17.0, no slots are copied to the new standby in this workflow; recreate all required slots. If the old primary is PostgreSQL 17.0 or newer, only logical slots on the primary are copied to the new standby; other slot types on the old standby still must be recreated manually.

Do not enable slot consumers until you verify slot name, type, plugin, database, and restart LSN.

### 7.10. Starting the New Cluster

Once primary upgrade, standby rsync, config restoration, and WAL/replication settings are verified:

1. Restore `pg_hba.conf` and required configs on the primary.
2. Start the new primary.
3. Check startup logs and any post-upgrade scripts generated by `pg_upgrade`.
4. Run required post-upgrade scripts.
5. Start each new standby.
6. Confirm streaming, receive/replay LSNs, and synchronous state.

Do not restore application traffic before completing required database and HA checks.

### 7.11. Non-Link Mode: Rebuilding Standbys

When using copy/clone mode or skipping the rsync hard-link procedure:

1. Complete `pg_upgrade` on the primary.
2. Start the new primary and confirm cluster health.
3. Create new standbys from the new primary using `pg_basebackup`, backup/restore tooling, or your platform's standard method.
4. Install matching PostgreSQL major binaries, extension binaries, and required configs.
5. Configure replication slots and standby settings.
6. Start standbys and verify streaming/replay.

This path is generally simpler, though transferring/restoring the full dataset takes time and extends the period before HA redundancy is restored.

---

## 8. Major Upgrade Using Logical Replication

### 8.1. Migration Architecture

Logical replication allows the old primary to keep accepting writes while the new target cluster performs the initial copy and applies subsequent changes:

```text
  Old PostgreSQL primary (publisher)
        |  publication + WAL logical decoding
        |  initial table copy and changes
        v
  New PostgreSQL cluster (subscriber)
        |
        | validate, sync sequences, cut over
        v
  New primary for applications
```

This is not a physical standby. The target cluster has its own data directory, system identifier, configuration, and backup chain.

### 8.2. Prerequisites

- Target major version supports logical replication from the source version.
- Publisher has `wal_level = logical`.
- Sufficient replication slots, WAL senders, and logical workers.
- Every table requiring `UPDATE`/`DELETE` has a suitable replica identity, usually a primary key.
- Target schema is compatible with incoming row changes.
- Extensions, types, collations, and functions are installed on the target.
- Adequate disk/I/O capacity for initial copy and continuous apply.

Review `max_replication_slots`, `max_wal_senders`, `max_logical_replication_workers`, `max_sync_workers_per_subscription`, and `max_worker_processes`.

### 8.3. Preparing Schemas and Global Objects

Logical replication does not automatically create database schemas or run DDL. You can dump schema-only from the source and restore onto the target before creating the subscription:

```bash
pg_dump --schema-only --no-owner --no-privileges \
  --host=old-primary --username=admin --dbname=appdb \
  --file=appdb-schema.sql

psql --host=new-primary --username=admin --dbname=appdb \
  --file=appdb-schema.sql
```

Roles, memberships, tablespaces, and global objects must be dumped/restored separately. Inspect ownership, grants, default privileges, and extension dependencies carefully.

### 8.4. Creating a Publication on the Old Primary

Example publishing all tables:

```sql
CREATE PUBLICATION upgrade_pub
FOR ALL TABLES;
```

Or listing tables explicitly:

```sql
CREATE PUBLICATION upgrade_pub
FOR TABLE public.customers, public.orders, public.order_items;
```

Select tables deliberately. Views, materialized views, foreign tables, and certain object types are not replicated like ordinary tables.

### 8.5. Creating a Subscription on the Target

Example:

```sql
CREATE SUBSCRIPTION upgrade_sub
CONNECTION 'host=old-primary port=5432 dbname=appdb user=repl_user password=REDACTED sslmode=verify-full'
PUBLICATION upgrade_pub
WITH (copy_data = true, create_slot = true, enabled = true);
```

Never hardcode real passwords in shared scripts. Use secret management or an approved authentication mechanism. Verify SSL, networking, grants, and replication slots before starting the copy.

### 8.6. Monitoring Initial Table Sync

On the subscriber:

```sql
SELECT
    srrelid::regclass AS table_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Check the subscription worker:

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Consider initial copying complete only when tables reach ready state and the apply worker reports no errors. Inspect PostgreSQL logs if any table sync stalls.

### 8.7. Monitoring Replication Lag

Monitor publisher/subscriber LSNs, apply worker state, slot retained WAL, and disk usage. A logical replication slot can retain WAL on the publisher if the subscriber stops applying; set monitoring/alerts on retained WAL and free disk space.

### 8.8. Limitations Requiring Manual Handling

Built-in logical replication has critical boundaries:

- DDL and schema changes are not automatically replicated; apply matching changes on the target in a safe sequence.
- Sequence values are not replicated. Identity/serial column values are copied as row data, yet sequence objects on the target must be reset.
- Large objects are not replicated.
- Roles, grants, tablespaces, functions, triggers, extensions, and scheduled jobs require separate migration.
- Triggers/rules do not fire as on the publisher by default inside the apply worker; verify side effects and business logic.
- Truncate and foreign-key relationships require careful planning.

Do not cut over if critical business objects remain unmigrated.

### 8.9. Syncing DDL During Migration

Any schema change during the migration window must follow a runbook applied to the target. A schema change on the publisher lacking a corresponding column on the subscriber will crash the apply worker when row changes arrive.

Prefer additive changes in safe order: create compatible columns/indexes/constraints on the target before the source begins generating rows under the new schema. Record every migration executed on both clusters.

### 8.10. Syncing Sequence Values Before Cutover

After stopping writes on the source and letting the subscriber apply all changes, capture sequence state from the source and advance target sequences past used values. Example for one sequence:

```sql
SELECT setval(
    'public.orders_order_id_seq',
    COALESCE((SELECT MAX(order_id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
```

This example uses the maximum column value as a reference. If a sequence has custom increments, min/max, cycling, or caching, synchronize from actual metadata/state; never apply a one-size-fits-all statement blindly to every sequence.

### 8.11. Logical Replication Cutover

A typical sequence:

1. Put applications into maintenance/read-only mode or block all writes to the publisher.
2. Stop background workers, schedulers, and integration jobs capable of writing.
3. Confirm all source transactions have committed.
4. Record the final source LSN and wait for the subscriber to apply up to that position.
5. Confirm all tables are ready with zero apply errors.
6. Sync sequence states and non-replicated objects.
7. Run consistency checks and critical business queries.
8. Stop/disable the subscription per runbook.
9. Switch application endpoints to the target.
10. Allow writes on the target and monitor for errors.

Only one side may accept writes at cutover. Never permit old and new primaries to accept writes independently without an explicitly engineered multi-writer conflict-resolution design.

### 8.12. Rollback After Logical Cutover

Once the target accepts new writes, the old source publisher does not receive them. Returning to the old cluster requires reverse replication or a dedicated data reconciliation workflow. Therefore, define the rollback window and point of no return before enabling writes on the target.

---

## 9. Major Upgrade Using Dump/Restore

### 9.1. Dumping Global Objects

Example:

```bash
pg_dumpall --globals-only \
  --host=old-primary --username=postgres \
  --file=globals.sql
```

Inspect the file before restoring; handle roles/tablespaces per the target environment's policy. Never put passwords/secrets into repositories or logs.

### 9.2. Dumping Databases

Custom format works well with `pg_restore` and supports parallel restore:

```bash
pg_dump -Fc \
  --host=old-primary --username=backup_user \
  --dbname=appdb \
  --file=appdb.dump
```

Databases can be dumped in parallel if the source has capacity. Record checksums, sizes, and exit statuses.

### 9.3. Restoring to the Target

Create the target database with the right owner, encoding, locale, and tablespace:

```bash
createdb --host=new-primary --username=postgres \
  --owner=app_owner appdb

pg_restore --host=new-primary --username=restore_user \
  --dbname=appdb --jobs=8 appdb.dump
```

Verify extension creation, ownership, privileges, sequences, and large objects. When restoring schemas and data separately, preserve dependency order.

### 9.4. Duration and Consistency

A dump is consistent as of each database's snapshot, yet if applications keep writing after dump start, post-snapshot changes will not appear on the target. You need an upfront write freeze or a supplemental delta-sync mechanism.

### 9.5. Building Physical Standbys After Restore

Once the target cluster is restored and started, build new physical standbys from the target primary. Never reuse an old standby's data directory.

---

## 10. Post-Upgrade Tasks for PostgreSQL

### 10.1. Run Post-Upgrade Scripts

`pg_upgrade` may generate scripts for post-upgrade steps. Read warnings and output, execute each script per guidance, and save logs. Never delete scripts before confirming they succeeded.

### 10.2. Update Extensions

In each database:

```sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
```

Run `ALTER EXTENSION ... UPDATE` per extension documentation and verify shared library versions. Some extensions require uninstall/reinstall or dedicated migration steps; never run bulk updates blindly.

### 10.3. Planner Statistics Do Not Transfer Like Table Data

Optimizer statistics are not transferred intact by `pg_upgrade`. Run the analyze script generated by `pg_upgrade` or collect statistics in stages:

```bash
vacuumdb --all --analyze-in-stages
```

During analyze, performance may be unstable. Monitor progress and avoid comparing benchmarks while planner statistics are incomplete.

### 10.4. Review Configuration Defaults

Do not copy old configs blindly without review. Parameters may be renamed, removed, or have changed defaults. Compare old/new `postgresql.conf`, `pg_settings`, `pending_restart`, logs, and release notes.

### 10.5. Check Startup and Logs

Verify:

- Primary starts on the right data directory and port.
- No missing library or config errors.
- Extensions load cleanly.
- Archive command executes.
- Standbys connect and replay.
- Authentication and TLS work.
- Application connection pools reach the right endpoint.

### 10.6. Recreate Scheduled Jobs and Integrations

Verify cron/systemd timers, `pg_cron` or external schedulers, ETL pipelines, FDWs, foreign servers, user mappings, monitoring exporters, and secrets. External components are not necessarily migrated automatically by upgrade tools.

---

## 11. Re-Syncing Backups and WAL Archives After Cutover

### 11.1. Pointing the Backup Tool to the New Cluster

Once the primary and standbys run on the target major:

1. Update server/data directory paths in the backup tool.
2. Update host/port and connection configs.
3. Run metadata/stanza upgrade if required by the product.
4. Check repository lists and archive namespaces.
5. Confirm the backup tool connects to the new primary.
6. Run archive/backup checks per tool instructions.

With pgBackRest, run `stanza-upgrade` after updating `pg-path` for the target major. If multiple repositories exist, run it for each repository as configured. When the cluster is offline, consult `--no-online` support in your version's docs.

### 11.2. Take a New Backup of the Target Cluster

After updating metadata, take a fresh backup per policy. Never assume an incremental backup from the old major can serve as a base for the target major. The backup tool determines whether a full backup or new chain is required by repository/version semantics.

### 11.3. Verify WAL Archiving on the New Primary

Confirm the archive command succeeds and WAL segments from the target cluster land in the proper location. Watch for archive failures and archive lag; verify object storage permissions, encryption, compression, and credentials.

### 11.4. Never Mix Old and New Cluster WAL

Old and new clusters have different system identifiers and timelines. Keep archive namespaces or stanza/catalog metadata separated as required by your tool. Never copy old WAL into the new cluster's path just because filenames look similar.

### 11.5. Check Backups from Standbys

If your backup tool supports backup-from-standby, verify the new standby has replayed far enough and the tool reads the right cluster. Some tools still connect to the primary to start/stop backups even when reading most data files from a standby.

### 11.6. Test Restoring the New Backup

Run a restore test onto an isolated host/database:

- Restore using the exact target PostgreSQL major.
- Use compatible binaries and extensions.
- Replay WAL to the desired recovery target.
- Confirm the cluster starts.
- Validate schemas, roles, row counts, and critical queries.
- Record restore and recovery durations.

A new backup is considered operational only once a restore test passes.

### 11.7. Point-in-Time Recovery

Test PITR from the target cluster backup to a timestamp within the new archive range. Verify:

- The base backup is recognized.
- WAL segments are contiguous on the right timeline.
- `restore_command` works.
- The recovery target is honored.
- The cluster stops/reaches the target as expected.

Do not conclude PITR is ready just because `archived_count` increased.

### 11.8. Retain Old Backup Chains

Old backups and WAL may be needed to restore the old cluster if the migration rolls back. Retain them until:

- The new cluster passes the defined stability period.
- A new full backup restores cleanly.
- A PITR test succeeds.
- Application owners accept data and behavior.
- The rollback window closes.

Only then prune according to the approved retention policy.

---

## 12. Rollback and Fallback Limits

### 12.1. Rollback Before the New Primary Accepts Writes

If the target cluster has accepted no new writes, rolling back usually means stopping the target and restarting the old cluster, provided the old data directory remains intact.

With `pg_upgrade` copy mode, the old cluster can usually be kept for fallback. With link mode, once the new cluster starts, the old cluster is unusable because relation files are shared via hard links; do not rely on the old cluster as a rollback option.

### 12.2. Rollback After the New Primary Accepts Writes

Once the target accepts writes, the old cluster is stale. You cannot simply point DNS/connection strings back to the old primary. You need reverse replication, replay of committed deltas, or recovery from an appropriate backup/restore point.

Clearly define:

- When writes are allowed on the target.
- When the rollback window closes.
- Who has authority to declare a rollback.
- How target-committed writes will be handled.
- How split-brain will be prevented.

### 12.3. Never Run Two Primaries Accepting Writes Simultaneously

During cutover, only one primary may accept writes. Updating endpoints, connection pools, and worker jobs takes time; use maintenance mode and verify all clients have switched before opening writes.

### 12.4. Rolling Back Backup Tooling

Retain old backup tool binaries and metadata/config copies per vendor guidance. If tool or repository formats underwent a one-way upgrade, you may need to restore a repository clone or keep compatible binaries to read the old backup chain.

### 12.5. Rolling Back the Failover Manager

Check the HA manager, fencing, VIP/DNS, and failover automation. An old node still registered in the failover manager could be accidentally promoted. Update cluster membership and fencing policies before re-enabling automatic failover.

---

## 13. Post-Upgrade Verification

### 13.1. Server Version and Cluster Role

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    pg_is_in_recovery() AS is_standby,
    current_setting('data_directory') AS data_directory;
```

Confirm application endpoints point to the new primary and standbys remain in recovery mode.

### 13.2. Physical Replication

On the primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

On standbys, inspect receiver/replay status and logs. Confirm synchronous standbys match policy.

### 13.3. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Cross-check against the pre-upgrade inventory; ensure consumers connect to the right slots and no inactive slots retain WAL unnecessarily.

### 13.4. Backups and Archiving

Run backup status/check commands, verify WAL archiving, and run a restore test. Confirm retention/prune jobs target the new stanza/namespace.

### 13.5. Data Consistency

Verify critical row counts, aggregates, foreign keys, constraints, sequences, large objects, ownership, and privileges. For logical migrations, compare table-level counts/checksums wherever feasible.

### 13.6. Application Behavior

Run smoke tests:

- Login/authentication.
- Critical read/write flows.
- Transactions and constraints.
- Prepared statements/driver behavior.
- Connection pools and reconnects.
- Background workers, schedulers, and ETL.
- Reporting/analytics queries.

### 13.7. Performance

Compare against baselines:

- TPS/throughput and latency.
- Query plans and `pg_stat_statements`.
- CPU, memory, and storage I/O.
- WAL generation and replication lag.
- Autovacuum/analyze.
- Lock waits and connection counts.

Never assume planner statistics carried over; run `ANALYZE` and watch for query regressions.

### 13.8. Monitoring and Alerting

Ensure dashboards/alerts match the new version, view columns, and metric names. Verify exporters, backup agents, replication lag alerts, disk/WAL alerts, and certificate expiration.

---

## 14. Minor Updates and Logical Replication Cluster Upgrades

### 14.1. Minor Updates Can Roll Node by Node

Because minor releases within the same major version maintain storage compatibility, you can upgrade binaries node by node in an HA topology on a rolling schedule:

1. Verify backups and failover readiness.
2. Upgrade one standby first and restart with the new minor binaries.
3. Wait for the standby to replay and confirm stable streaming.
4. Repeat for remaining standbys.
5. Perform a planned switchover if needed to minimize primary downtime.
6. Upgrade and restart the former primary once it becomes a standby.
7. Confirm all nodes run the same minor version and failover works.

This is a common pattern; failover managers, synchronous replication, and service providers may dictate specific ordering. Never upgrade a node without a fallback path or healthy standbys.

### 14.2. Minor Updates Still Require Backups and Checks

Minor updates usually avoid migrating data directories, yet still require:

- Reading the minor version's release notes.
- Checking OS packages and extension binaries.
- Saving configs and taking a recent backup.
- Verifying primary/standby compatibility.
- Checking service manager units and startup logs.
- Checking backup tools and monitoring agents.

A minor update does not replace a major upgrade procedure.

### 14.3. Upgrading an Existing Logical Replication Cluster

If the existing system is already a logical replication cluster, distinguish that from using logical replication as a migration path to a new cluster.

PostgreSQL 18 can use `pg_upgrade` to migrate logical replication slots and subscription dependencies in certain cases, but supports migrating such a cluster only when all members of the old logical replication cluster are running PostgreSQL 17.0 or newer. Prerequisites include:

- The target publisher has `wal_level = logical`.
- `max_replication_slots` is large enough.
- Corresponding output plugins are installed in target binaries and safely configured.
- Old logical slots have replicated all pending transactions/messages and remain usable.
- Subscriber tables are in an appropriate state and replication origins exist.
- `max_active_replication_origins` is sufficient for subscriptions.

Before upgrading the publisher, disable subscriptions per documentation; after upgrading and starting, re-enable them. If the source cluster is older than 17.0, `pg_upgrade` does not automatically migrate logical slots/subscription dependencies under this mechanism; a separate recreation workflow is needed.

### 14.4. Do Not Confuse Logical Slots with Physical Standby Slots

Logical replication slots retain WAL for logical decoding consumers. Physical replication slots retain WAL for physical standbys. Each type has distinct owners, lifecycles, and migration rules. Inventory and recreate them per consumer rather than creating a slot solely from an old name.

---

## 15. Common Mistakes

**1. “Just install the new PostgreSQL major on the standby and restart.”** False. Physical replication does not cross major versions that way; upgrade/rebuild standbys following the supported workflow.

**2. “You can run `pg_upgrade` independently on each standby.”** False in standard setups. Cluster identity and data state will diverge from the primary. Use the rsync link-mode procedure or rebuild standbys.

**3. “Once the new primary starts, we can rsync standbys afterward.”** False for the link-mode standby procedure. Finish rsync before starting the new primary/standbys in documented order.

**4. “Link mode still preserves the old cluster for rollback.”** False. Once the new cluster starts, the old cluster is unusable because relation files share hard links.

**5. “`pg_upgrade` updates all extensions automatically.”** False. Target shared libraries and separate extension update steps are required.

**6. “`pg_upgrade` transfers planner statistics.”** False. You must re-analyze so the planner has accurate statistics.

**7. “Logical replication replicates DDL automatically.”** False. Schema changes must be synchronized separately.

**8. “Logical replication transfers sequence values.”** False. Sequence state must be synchronized before cutover.

**9. “Logical replication transfers large objects.”** False. Large objects are not replicated by built-in logical replication.

**10. “The subscriber can accept writes alongside the publisher without conflicts.”** False. Cutover must enforce a single writer or use an explicit multi-writer design.

**11. “Old-major physical backups can restore into the target major.”** Never assume this. Retain old binaries/restore environments to recover old backups.

**12. “Backup command exit code 0 proves restores work.”** False. Restore rehearsals and PITR tests are required.

**13. “Upgrading the backup tool last is always safe.”** False. The target PostgreSQL may require a newer tool version; prepare tooling before cutover so both old and target clusters remain protected.

**14. “Upgrading the tool binary means the repository format was upgraded.”** False. Binary version and repository format are distinct; follow vendor docs.

**15. “Run `stanza-upgrade` for every backup tool.”** False. That command is specific to pgBackRest; Barman and WAL-G have their own workflows.

**16. “Old backups can be pruned right after cutover.”** False. Keep old backups/WAL throughout the rollback window and approved retention period.

**17. “An increasing archive count proves PITR works.”** False. Restore a backup and replay WAL to a target timestamp.

**18. “Seeing replication lag = 0 once is sufficient.”** False. Monitor state and LSNs throughout cutover and verify standbys continue replaying.

**19. “Switching DNS completes the cutover.”** False. Connection pools, background workers, scheduled jobs, monitoring, and the failover manager must also switch.

**20. “We can revert to the old primary after the new primary accepts writes.”** Not directly. The old cluster is stale; reverse replication or data reconciliation is needed.

**21. “`pg_upgrade --check` guarantees production upgrade success.”** False. It is a compatibility check; you still need rehearsals, backups, and a cutover runbook.

**22. “No need to read release notes for intermediate major versions.”** False. Cumulative changes across skipped majors can affect upgrades.

**23. “Old standby slots are automatically copied in full.”** False. Behavior depends on source major and slot type; verify and recreate per documentation.

**24. “An old-cluster restore test proves the new backup restores cleanly.”** False. After cutover, take and test restoring a target-major backup separately.

---

## 16. Sample Runbook: PostgreSQL 16 to 17 with `pg_upgrade`

### 16.1. Assumed Topology

Example setup:

- PostgreSQL 16 primary.
- Two PostgreSQL 16 physical standbys.
- pgBackRest backup tool.
- Target PostgreSQL 17.
- Maintenance window available to pause writes.
- `pg_upgrade` link mode chosen to shorten data file transfer time.

This is an illustrative runbook, not copy-paste commands for every distro. Substitute actual paths, service names, repository IDs, extension packages, and HA manager commands.

### 16.2. Before the Maintenance Window

1. Read PostgreSQL 17 migration notes and `pg_upgrade` documentation.
2. Confirm the pgBackRest release supports PostgreSQL 17 and reads the existing repository.
3. Install PostgreSQL 17 binaries and extension packages on all three database hosts.
4. Verify filesystem capacity and link-mode support.
5. Take a full PostgreSQL 16 backup and check WAL archiving.
6. Test restoring the backup into an isolated environment.
7. Run `pg_upgrade --check` with `--link`.
8. Check replication slots, tablespaces, relocated `pg_wal`, and custom configs.
9. Record baseline LSN/checkpoints and application metrics.
10. Announce downtime and prepare maintenance mode.

### 16.3. Starting Cutover

1. Stop application writes, workers, ETL, and scheduled jobs.
2. Drain connection pools.
3. Wait for required transactions to finish.
4. Confirm both standbys are caught up.
5. Stop the old primary per runbook so old standbys receive the final WAL.
6. Stop old standbys.
7. Run `pg_controldata` to compare `Latest checkpoint location` across primary and each standby.
8. If checkpoint locations mismatch, halt and resolve lag.

### 16.4. Upgrading the Primary

1. Verify target config sets `wal_level` suitable for replication.
2. Run the target `pg_upgrade` binary with old/new data directories, old/new binary paths, jobs, and `--link`.
3. Inspect output, warnings, and generated scripts.
4. Do not start the new primary yet.

### 16.5. Upgrading Standbys with rsync

On each standby:

1. Confirm the target data directory does not exist or is empty.
2. Back up old config files to preserve.
3. Run the `rsync` hard-link procedure from the upgraded primary.
4. Separately sync tablespaces and relocated `pg_wal` if present.
5. Configure `primary_conninfo`, slots, archive/restore settings, and HA manager.
6. Recreate slots per source major/slot type.
7. Verify ownership and permissions.

### 16.6. Starting the Target Cluster

1. Restore `pg_hba.conf`/configs on the primary.
2. Start the new primary.
3. Check logs and run post-upgrade scripts.
4. Run required extension updates.
5. Run `vacuumdb --all --analyze-in-stages` or analyze scripts generated by `pg_upgrade`.
6. Start each standby.
7. Verify streaming, replay LSNs, `sync_state`, and slots.

### 16.7. Switching Backup Tooling

1. Update pgBackRest `pg-path` to the PostgreSQL 17 data directory on all hosts.
2. Run `stanza-upgrade` for each repository.
3. Check `stanza`/info and WAL archiving.
4. Take a fresh PostgreSQL 17 backup.
5. Test restoring the new backup and replaying WAL.
6. Keep PostgreSQL 16 backups/WAL during the rollback window.

### 16.8. Reopening the Application

1. Smoke test critical reads/writes and transactions.
2. Verify connection pools and endpoints.
3. Re-enable background workers and schedulers in order.
4. Open writes.
5. Monitor errors, latency, replication lag, WAL/archive, and disk usage.
6. Record when the rollback window closes.

---

## 17. Practice Exercises and Answers

### Exercise 1 — Minor vs. Major

**Question:** Does upgrading PostgreSQL 17.3 to 17.6 require `pg_upgrade`?

**Answer:** No. This is a minor update within the same major version; swap binaries and restart following the cluster's compatible procedure.

### Exercise 2 — Major Version

**Question:** Why can you not replace PostgreSQL 16 binaries with PostgreSQL 17 and start the old data directory?

**Answer:** Major versions can alter internal storage and catalog formats; you need `pg_upgrade`, dump/restore, or a replication migration.

### Exercise 3 — Physical Replication

**Question:** Can a PostgreSQL 16 standby replay WAL from a PostgreSQL 17 primary?

**Answer:** No. Physical replication requires the same major version and cluster identity.

### Exercise 4 — Standby Link Mode

**Question:** If the primary used `pg_upgrade --link`, how can standbys be upgraded?

**Answer:** Using the official `rsync` hard-link procedure from the upgraded primary before starting the new cluster.

### Exercise 5 — Non-Link Standby

**Question:** When using copy mode, what is the simplest way to upgrade a standby?

**Answer:** Rebuild the standby from the new primary via a base backup or backup/restore procedure.

### Exercise 6 — Checkpoint LSN

**Question:** Before link-mode rsync, what must match between the old primary and standbys?

**Answer:** `Latest checkpoint location` in `pg_controldata` must match.

### Exercise 7 — Link Mode Rollback

**Question:** Can the old cluster be used after the new cluster starts in link mode?

**Answer:** No. Old and new relation files share hard links.

### Exercise 8 — Extensions

**Question:** Why must target-major extension shared objects be installed before `pg_upgrade`?

**Answer:** The new server must load matching shared libraries; C extension binaries must match the target major.

### Exercise 9 — Logical Replication

**Question:** Does logical replication replicate DDL?

**Answer:** No. Schema changes must be applied separately on the subscriber.

### Exercise 10 — Sequences

**Question:** Why must sequences be synced before logical cutover?

**Answer:** Sequence state is not replicated by logical replication; the target could issue duplicate or backward IDs.

### Exercise 11 — Large Objects

**Question:** Does built-in logical replication replicate large objects?

**Answer:** No.

### Exercise 12 — Publications

**Question:** Which objects can be added to a standard publication?

**Answer:** Tables, including partitioned tables per PostgreSQL rules; views, materialized views, and foreign tables are not replicated like ordinary tables.

### Exercise 13 — Backup Tool Order

**Question:** Why should backup tools be upgraded before PostgreSQL?

**Answer:** The new tool may be required to back up/restore the target major; preparing it beforehand protects both the old cluster and the target cluster across cutover.

### Exercise 14 — Repository Format

**Question:** Does upgrading the backup tool binary always mean the repository format is upgraded?

**Answer:** No. They are separate operations; follow vendor documentation.

### Exercise 15 — pgBackRest

**Question:** After a PostgreSQL major upgrade, what actions does pgBackRest require per documentation?

**Answer:** Update `pg-path` and run `stanza-upgrade` for the corresponding repositories.

### Exercise 16 — WAL Archiving

**Question:** Does an increasing `archived_count` prove PITR works?

**Answer:** No. You must restore a backup and replay WAL to a recovery target.

### Exercise 17 — Optimizer Statistics

**Question:** Does `pg_upgrade` transfer full planner statistics?

**Answer:** No. Run analyze after upgrading.

### Exercise 18 — Old Backups

**Question:** Should old backup chains be pruned immediately after cutover?

**Answer:** No. Retain them throughout the rollback/retention window and delete only once new backups are proven restorable.

### Exercise 19 — Cutover Writes

**Question:** Why must old and new primaries never accept writes concurrently?

**Answer:** Risk of split-brain and divergence; only one side should accept writes unless a specialized multi-writer architecture is in place.

### Exercise 20 — Rollback

**Question:** After the target accepts new writes, can you simply point endpoints back to the old primary?

**Answer:** No. The old cluster is stale; reverse replication or reconciliation/restore is required.

### Exercise 21 — Replication Slots

**Question:** Does slot behavior during the standby rsync procedure differ by old major version?

**Answer:** Yes. For old primaries before 17.0, no slots are copied; from 17.0 onward, only logical slots on the primary are copied, and other slots must be recreated per documentation.

### Exercise 22 — Restore Testing

**Question:** Is backup job exit code 0 sufficient to prove usability?

**Answer:** No. Restore rehearsals and PITR tests are required.

### Exercise 23 — Logical Replication Version Upgrade

**Question:** Can PostgreSQL 18 migrate an existing logical replication cluster with `pg_upgrade` from any source version?

**Answer:** No. This mechanism is supported only when all members of the old logical replication cluster run PostgreSQL 17.0 or newer and satisfy prerequisites.

### Exercise 24 — Release Notes

**Question:** When upgrading PostgreSQL 14 to 18, must you read migration notes for 15, 16, and 17?

**Answer:** Yes. Cumulative changes across every skipped major version must be reviewed.

---

## 18. Upgrade Sequencing Checklist

### Before Making Changes

1. Record source/target PostgreSQL major/minor versions.
2. Read migration notes for every skipped major version.
3. Inventory primary, standbys, cascading topology, and failover manager.
4. Record system identifier, timeline, replication LSNs, and slots.
5. Inventory extensions, preload modules, tablespaces, and custom files.
6. Document all backup tools, agents, repository formats, and restore commands.
7. Confirm the backup tool supports both old and target PostgreSQL versions.
8. Upgrade backup tooling first if the target major requires a newer version.
9. Verify the new tool still reads and restores the old backup chain.
10. Take a full backup and verify WAL archiving.
11. Run a restore rehearsal and record recovery duration.
12. Choose `pg_upgrade`, logical replication, or dump/restore.
13. If using `pg_upgrade`, run `--check` with the exact transfer mode.
14. If using logical replication, prepare schemas, publications, subscriptions, sequences, and large objects.
15. Install target PostgreSQL binaries/extensions on all hosts.
16. Prepare target paths, configuration, authentication, and networking.
17. Record baseline metrics and prepare maintenance mode.

### During Major Cutover

18. Stop writes, background workers, and scheduled jobs.
19. Drain connections and wait for transactions to finish.
20. Confirm old standbys are caught up.
21. For the `pg_upgrade` link-mode standby procedure, confirm checkpoint locations match.
22. Upgrade the primary with `pg_upgrade` or execute logical/dump cutover per runbook.
23. Upgrade/rebuild physical standbys via the link-mode or non-link-mode path.
24. Recreate required replication slots.
25. Configure WAL archive/restore and the failover manager.
26. Start the new primary and then standbys in proper order.
27. Run post-upgrade scripts, extension updates, and analyze.

### After Cutover

28. Update backup tool paths/catalog/stanza for the target cluster.
29. Take a target-major backup and verify WAL archiving.
30. Test restoring the new backup and execute a PITR test.
31. Verify replication, slots, sync state, and failover readiness.
32. Verify data consistency, sequences, roles, grants, and critical queries.
33. Smoke test applications, drivers, pools, jobs, and integrations.
34. Monitor latency, CPU, I/O, WAL, autovacuum, and replication lag.
35. Retain old backups/WAL and old binaries during the rollback/retention window.
36. Prune old backup chains only once the new backup is proven restorable and the rollback window closes.

---

## 19. Summary

Upgrading PostgreSQL clusters with a primary, physical standbys, and backup tooling requires coordinating multiple components in sequence. Minor updates typically preserve storage formats and can roll node by node within the same major version. Major upgrades migrate the cluster via `pg_upgrade`, logical replication, or dump/restore, after which physical standbys and backup workflows must transition to the new cluster.

Key takeaways:

- Physical replication requires primary and standbys on the same major version and cluster identity.
- With `pg_upgrade` link mode, PostgreSQL provides an `rsync` hard-link procedure for standbys; never run `pg_upgrade` independently on each standby.
- When using copy/clone mode or skipping the rsync procedure, rebuild standbys from the new primary.
- Before link-mode standby rsync, confirm old primary and standbys share the exact same `Latest checkpoint location`.
- Prepare backup tooling beforehand to support both old and target versions; upgrade repository formats strictly per separate documentation.
- With pgBackRest, update `pg-path` and run `stanza-upgrade` post-major-upgrade for each repository.
- Logical replication can shrink downtime, yet does not automatically replicate DDL, sequence state, or large objects.
- Dump/restore is explicit, though slower, and requires handling global objects separately.
- `pg_upgrade` does not carry full optimizer statistics; run analyze after upgrading.
- After cutover, take a target-major backup and test restore/PITR.
- Never prune old backups before new backups are verified and the rollback window closes.
- Once the new primary accepts writes, the old primary is no longer a direct rollback target.
- Only one primary may accept writes across cutover to prevent split-brain.

**Self-check question:** A PostgreSQL 16 primary was upgraded to 17 using `pg_upgrade` link mode. Can you simply start the old PostgreSQL 16 standby to receive WAL from the new primary? No. You must upgrade the standby using the supported rsync hard-link procedure or rebuild it from the new PostgreSQL 17 cluster.

### Official PostgreSQL and Backup Tooling Documentation

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/18/upgrading.html).
- [pg_upgrade](https://www.postgresql.org/docs/18/pgupgrade.html).
- [Logical Replication — Upgrade](https://www.postgresql.org/docs/18/logical-replication-upgrade.html).
- [Logical Replication — Restrictions](https://www.postgresql.org/docs/18/logical-replication-restrictions.html).
- [Logical Replication — Configuration Settings](https://www.postgresql.org/docs/18/logical-replication-config.html).
- [Logical Replication — Architecture](https://www.postgresql.org/docs/18/logical-replication-architecture.html).
- [pgBackRest User Guide](https://pgbackrest.org/user-guide.html).
- [pgBackRest Command Reference — stanza-upgrade](https://pgbackrest.org/command.html).
- [pgBackRest Release Notes](https://pgbackrest.org/release.html).
- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/).
