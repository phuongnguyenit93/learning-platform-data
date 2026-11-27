# Disk Full Caused by Tables, WAL, Archives, or Logs in PostgreSQL

Disk exhaustion incidents in PostgreSQL can occur in many places: data files for tables and indexes, TOAST storage, the `pg_wal` directory, the archive destination, temporary files, log files, or a dedicated tablespace. Each cause requires a different resolution. Deleting a file in `PGDATA` by mistake can prevent the database from starting or break recovery; conversely, simply expanding disk capacity without resolving a replication slot or archive backlog will allow disk usage to keep growing.

When a filesystem nears full capacity, PostgreSQL may fail to write WAL, fail to create temporary files, fail to complete checkpoints, or fail to write logs. A database still answering read queries may already be on the verge of losing write capability. If the disk fills completely, backends can report `No space left on device`, transactions fail, and the cluster can halt if it cannot write essential components.

This lesson belongs to the **Troubleshooting** chapter and focuses on:

- Identifying which filesystem, mount, tablespace, or volume is running out of space.
- Distinguishing space consumed by tables, indexes, TOAST, large objects, and bloat.
- Diagnosing `pg_wal` growth driven by workload, checkpoints, replication slots, or archive failures.
- Checking the archive destination, `archive_command`, `pg_stat_archiver`, and backup retention.
- Identifying temporary files and query sort/hash spills.
- Managing PostgreSQL logs, rotation, and logging configuration.
- Distinguishing disk space exhaustion from inode, quota, and container volume exhaustion.
- Handling incidents in a safe sequence that preserves WAL and recovery-critical data.
- Reclaiming space safely, resolving replication lag, and restoring archiving.
- Establishing capacity planning, alerting, and preventive runbooks.

> **Emergency rule:** Never manually delete files inside `PGDATA`/`pg_wal`, `base`, `global`, or tablespace directories to free disk space. Never delete WAL archives before verifying backup and standby retention requirements. First identify which filesystem is full, preserve recovery capability, and then free space from verified sources or expand the volume.

## 1. Understanding PostgreSQL Storage Areas

PostgreSQL uses multiple file types with distinct lifecycles and space demands. You must know which files belong to database storage and which belong to WAL, archives, logs, and temporary work.

### 1.1. Data Directory

`data_directory` (commonly called `PGDATA`) holds cluster data, including:

- `base/`: database files in the default tablespace.
- `global/`: cluster-wide catalogs and shared files.
- `pg_wal/`: write-ahead log segments.
- `pg_tblspc/`: symbolic links to tablespaces outside the data directory.
- `pg_multixact/`, `pg_subtrans/`, `pg_commit_ts/`: transaction metadata components when used.
- `pg_stat/`, `pg_stat_tmp/`: statistics files.
- `pg_logical/`, `pg_replslot/`: logical decoding/replication metadata and slot state.
- `pg_xact/`: transaction status data.
- Configuration, PID, and control files.

Exact directory names and contents can vary by version. Never modify or delete internal files using filesystem tools.

### 1.2. Tables and Indexes

Each table and index has physical relation files. A relation can span multiple segments once it exceeds the filesystem or PostgreSQL segment limit. A table also has forks such as the main fork, FSM, and visibility map.

Table and index size grows with row count, row width, `UPDATE`/`DELETE` creating dead tuples, index count and key size, TOAST values, page utilization, bloat from workload or vacuum falling behind, plus partition count and per-partition data.

### 1.3. TOAST Storage

Large values such as `text`, `bytea`, and `jsonb` may be compressed or stored out-of-line in a TOAST table. Therefore, main heap size alone does not reflect total table footprint.

During investigation, use `pg_table_size()` or `pg_total_relation_size()` rather than looking only at `pg_relation_size()` on the main fork.

### 1.4. WAL

WAL records changes needed for crash recovery and replication. The `pg_wal` directory holds WAL segments actively in use or retained for crash recovery, checkpoint/recycling, streaming replication, replication slots, WAL archiving, and backup/PITR requirements.

WAL files are not ordinary text logs. Never delete segments based on filename or file age.

### 1.5. WAL Archive

When archiving is enabled, PostgreSQL invokes `archive_command` or an archive library to transfer completed WAL segments to the archive destination. The archive usually resides outside `PGDATA`, such as on another filesystem, an object storage gateway, or a backup repository.

A full archive destination can cause the archive command to fail; PostgreSQL retains unarchived WAL inside `pg_wal` and retries. As the backlog grows, both the archive destination and the primary data volume can run into trouble.

### 1.6. Temporary Files

Query sorts, hash joins, hash aggregations, materialization, or other operations can spill to temporary files when memory is insufficient. Temporary files normally reside in a database's `base/pgsql_tmp` directory or locations configured via `temp_tablespaces`.

These files are normally cleaned up by the backend when the operation or session finishes. Never delete temporary files actively used by a running backend.

### 1.7. PostgreSQL Logs

Logs may be written by the logging collector into `log_directory`, sent to stderr and captured by a service manager/container runtime, routed to syslog or an external logging system, or stored on a separate volume managed by a cloud platform.

If `log_directory` is a relative path, it resolves relative to the data directory. Logs can share the same filesystem as the database and exhaust disk space.

### 1.8. Other Places

Also inspect backup staging directories, base backups and WAL archive copies, core dumps after backend crashes, CSV/JSON logs, export files and ETL staging data, container writable layers, Kubernetes PersistentVolumeClaims, filesystem snapshots and cloud volume snapshots, OS package caches, or unrelated services sharing the same mount.

Do not attribute all disk growth on a host to PostgreSQL before verifying the exact mount and directory.

## 2. Symptoms and Incident Classification

### 2.1. Signs of Disk Full

Common symptoms:

- SQL errors containing `No space left on device`.
- PostgreSQL logs reporting inability to write WAL, temporary files, or relation files.
- `INSERT`, `UPDATE`, `CREATE INDEX`, `VACUUM`, or backups failing.
- `archive_command` repeatedly returning non-zero.
- `pg_wal` growing rapidly.
- Replica lag climbing or replication slots retaining WAL.
- PostgreSQL shutting down/crashing or failing to finish recovery.
- Log collector failing to write log files.
- A specific tablespace running out of space while `PGDATA` still has room.

### 2.2. Distinguishing Full Filesystem from Large Database Objects

A database can be large while the filesystem still has plenty of space. Conversely, database object sizes may be modest while `pg_wal`, logs, or temporary files fill the volume.

| Source | Symptom | Primary Check |
| --- | --- | --- |
| Tables/indexes/TOAST | Relation sizes growing | `pg_total_relation_size`, OS directory usage |
| Table bloat | Dead tuples/free space growing | `pg_stat_user_tables`, `pgstattuple` |
| WAL retention | `pg_wal` growing rapidly | `pg_replication_slots`, `pg_stat_archiver` |
| Archive backlog | Archive command failures | `pg_stat_archiver`, destination capacity |
| Temporary files | Heavy query spills | `pg_stat_database.temp_files`/`temp_bytes` |
| Logs | Log directory growing | `log_directory`, OS directory usage |
| Tablespace | A separate mount is full | `pg_tablespace_location`, `df` |
| Inodes/quota | Cannot create files despite free bytes | `df -i`, filesystem quotas |
| Container/PVC | Host has free space yet volume is full | Container mount/PVC metrics |

### 2.3. Assessing Urgency

Assess how many bytes and inodes remain on the filesystem; whether `PGDATA`, `pg_wal`, tablespaces, and archives share the same mount; whether PostgreSQL still accepts writes; whether WAL archiving is failing; whether replication slots are retaining WAL; whether backups/PITR remain usable; and how quickly the volume can be expanded.

If the filesystem holding `PGDATA` or `pg_wal` is nearly full, prioritize protecting WAL writes and recovery. Do not wait until 100% full to act.

## 3. Initial Response Runbook

When a high disk usage alert fires, follow a controlled sequence.

### 3.1. Capture Current State

Record timestamp and alert source, host/cluster/database, affected filesystem/mount, total/used/available bytes and inode usage, PostgreSQL version and service status, `PGDATA`/tablespace/WAL archive/log paths, recent workloads/deployments/backups, and recent changes to replication, archiving, or retention.

Capture metrics and logs before cleaning anything up to preserve evidence.

### 3.2. Determine the Growth Rate

A volume sitting steadily at 95% differs sharply from one growing by 5 GiB per minute. Take at least two snapshots separated by a short interval to calculate growth rate:

```text
growth_rate_bytes_per_second =
    (used_bytes_now - used_bytes_before)
    / elapsed_seconds

estimated_time_to_full =
    available_bytes_now / growth_rate_bytes_per_second
```

This is a linear estimate; workload shifts, checkpoints, archive retries, and log rotation can change the rate quickly.

### 3.3. Contain the Source of Disk Growth

Once the source is identified, pause or throttle jobs performing bulk loads, backfills, or index builds; pause exports/ETLs writing staging files; fix the archive destination before the WAL backlog grows further; restore replicas/consumers or handle slots per retention policy; adjust log verbosity if query logging exploded, after saving evidence; cap workloads generating temporary files; and expand the filesystem/volume if feasible.

Do not blindly stop all application writes. Choose the narrowest containment that stops the volume from filling further.

### 3.4. Prefer Volume Expansion When Needed

Expanding the volume/filesystem is often the lowest-risk option when you cannot immediately tell which files are safe to clean up. After expanding, confirm the filesystem recognizes the new capacity, PostgreSQL can write files, and archive commands/replication recovery work, then continue root-cause investigation and enforce proper cleanup/retention policies.

Adding disk does not replace resolving slot/archive backlogs or log retention.

### 3.5. Avoid Blind Cleanup

Never delete WAL files in `pg_wal`, relation files in `base`, tablespace directories in active use by PostgreSQL, archives by `mtime` without checking backup chains and standby needs, temporary files while backends are running, or the sole remaining backup. Do not run `VACUUM FULL` or `REINDEX` when a volume is already nearly out of space. Do not run `docker system prune -a` without knowing which data or volumes will be affected.

Such actions can turn a disk alert into data loss or an extended outage.

## 4. Checking Filesystems at the OS Level

SQL reveals PostgreSQL objects and catalog state; the OS reveals how much space mounts actually have left.

### 4.1. Linux: Viewing Mount Capacity

```bash
df -h
df -h /var/lib/postgresql
df -h /mnt/pg_archive
```

Use the real paths for `PGDATA`, tablespaces, and archives. Never assume everything lives under `/var/lib/postgresql`.

### 4.2. Linux: Checking Inodes

```bash
df -i
```

A filesystem can run out of inodes even with free bytes remaining. When that happens, PostgreSQL cannot create new files. Find directories containing millions of small files, but never arbitrarily delete internal PostgreSQL files.

### 4.3. Linux: Finding Large Directories

```bash
sudo du -xhd1 /var/lib/postgresql
sudo du -xhd1 /var/log
sudo du -xhd1 /mnt/pg_archive
```

`-x` keeps the scan within the same filesystem, avoiding double-counting other mounts. `du` can generate significant I/O on large directories; run it carefully and do not treat its output as a substitute for understanding PostgreSQL catalogs.

### 4.4. Deleted Files Still Held Open by Processes

On Linux, an unlinked file continues occupying disk space until the process holding its file descriptor closes it. `lsof +L1` helps find deleted-open files. If log rotation unlinks a file while the process keeps writing to the old descriptor, disk space is not reclaimed.

Resolve this via the service's proper log reopen/rotate mechanism—never kill database processes arbitrarily.

### 4.5. Windows

On Windows servers, check volumes with PowerShell:

```powershell
Get-Volume |
    Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining, HealthStatus

Get-PSDrive -PSProvider FileSystem
```

Use filesystem administration tools to locate large folders. Inspect the volumes hosting the data directory, WAL, tablespaces, logs, and archives separately.

### 4.6. Quotas and Reserved Blocks

Check filesystem quotas, container limits, and reserved blocks. A database service account can exhaust its quota even while `df` still shows free space for root or other users.

## 5. Identifying PostgreSQL Storage Paths

Start from the active configuration:

```sql
SHOW data_directory;
SHOW config_file;
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW wal_level;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
```

Some settings only exist in specific PostgreSQL versions or may not be supported by managed services. If `SHOW` reports an unknown parameter, check your version and provider configuration rather than assuming the server is broken.

### 5.1. Identifying Tablespace Locations

```sql
SELECT
    spcname AS tablespace_name,
    pg_tablespace_location(oid) AS location,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY spcname;
```

`pg_default` and `pg_global` have empty locations because they reside inside the data directory per cluster layout. Custom tablespaces can map to separate mounts.

### 5.2. Checking Database Sizes

```sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

Total database sizes exclude external WAL archives, logs, and temporary files outside relation storage. Do not add these numbers together and assume they equal total filesystem usage.

### 5.3. Checking Version

```sql
SELECT version();
SHOW server_version_num;
```

The version determines available catalog fields, statistics views, and parameters. Record the version in your incident notes.

## 6. Finding Tables and Indexes Consuming Space

### 6.1. Top Relations by Total Size

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS main_fork,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
```

`pg_relation_size` measures the relation's main fork by default. `pg_table_size` includes table storage and associated structures such as TOAST, FSM, and visibility map, excluding indexes. `pg_indexes_size` measures the table's indexes. `pg_total_relation_size` sums table storage and indexes.

### 6.2. Top Indexes

```sql
SELECT
    schemaname,
    tablename,
    indexrelname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
```

`idx_scan` counts scans since the last statistics reset. An index with low scan counts is not automatically unused: statistics may have been reset recently, or the index may enforce a constraint or serve rare/seasonal queries.

### 6.3. Top Tables by Dead Tuples

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Tuple counts are statistics estimates, not exact counts. Use them to guide bloat and vacuum investigations.

### 6.4. Inspecting TOAST Relations

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_total_relation_size(c.reltoastrelid)) AS toast_total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC
LIMIT 30;
```

TOAST relations can grow large when tables store large `text`, `jsonb`, or `bytea` values. Examine actual data, compression/storage strategies, and query patterns before changing schemas.

### 6.5. Partitioned Tables

A partitioned parent table may store no rows directly; data lives in child partitions. Inventory inheritance edges:

```sql
SELECT
    parent.oid::regclass AS parent_table,
    child.oid::regclass AS partition_table,
    pg_size_pretty(pg_total_relation_size(child.oid)) AS total_size
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
ORDER BY pg_total_relation_size(child.oid) DESC;
```

For multi-level partitioning, the query above lists individual inheritance edges. Use a recursive CTE to reconstruct the full hierarchy.

### 6.6. Large Objects

Large objects are stored in catalog relations such as `pg_largeobject` and metadata table `pg_largeobject_metadata`. If applications use `lo_*` APIs, check large object usage and clean them up per ownership/reference policy. Never delete rows directly from system catalogs.

## 7. Table Bloat and Vacuum

Relation growth does not always mean business data is growing proportionally. `UPDATE`/`DELETE` operations create dead tuple versions under MVCC; `VACUUM` must clean them up once no active snapshot needs them.

### 7.1. Dead Tuples and Long-Running Transactions

Dead tuples occupy pages until reclaimed. Long-running transactions, prepared transactions, or replication horizons can block cleanup.

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Never terminate a transaction solely based on age; identify owner and impact first.

### 7.2. Regular VACUUM

```sql
VACUUM (VERBOSE, ANALYZE) app.orders;
```

Regular `VACUUM` makes space inside the relation reusable for future rows. It usually does not shrink the table file on the filesystem except in limited cases where trailing pages at the end of the relation can be truncated.

`VACUUM` is not a full table compaction or rewrite operation.

### 7.3. VACUUM FULL

```sql
VACUUM (FULL, ANALYZE) app.orders;
```

`VACUUM FULL` rewrites the table and requires an `ACCESS EXCLUSIVE` lock. It requires extra disk space to build the new copy and can spike WAL and replication load. Never run it as an immediate reaction when the filesystem is already full.

### 7.4. pg_repack and Index Bloat

`pg_repack` can reduce bloat with shorter strong-lock windows than traditional rewrite operations, yet it still requires extra disk, WAL, trigger/log tables, and lock phases. It is a separate extension/tool, not a core PostgreSQL command.

`REINDEX` builds a new index, requiring extra disk and I/O. `REINDEX CONCURRENTLY` runs across multiple phases and cannot run inside a transaction block; it still requires enough space for both the old and new indexes to coexist.

### 7.5. pgstattuple

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('app.orders');
```

`pgstattuple` provides detailed measurements of tuples and free space. Scanning an entire relation can be I/O-intensive. Run it only on selected objects inside an appropriate maintenance window. Consider `pgstattuple_approx` for a lighter estimate depending on extension/version behavior.

## 8. WAL: Why Does pg_wal Grow?

WAL growth does not necessarily indicate a bug. A bulk load, large `UPDATE`, `CREATE INDEX`, or checkpoint workload generates WAL quickly. The problem arises when PostgreSQL cannot recycle segments because a consumer or archive is falling behind.

### 8.1. WAL Generation

Operations generating WAL include `INSERT`/`UPDATE`/`DELETE`, `CREATE INDEX` and `REINDEX`, table rewrites, `VACUUM FULL`, `CLUSTER`, certain DDL/catalog updates, full-page images after checkpoints when `full_page_writes` is enabled, and bulk operations.

Measure the WAL generation rate rather than looking solely at file count in `pg_wal`.

### 8.2. max_wal_size Is Not a Hard Cap

`max_wal_size` is a soft target controlling checkpoint frequency. WAL can exceed this setting whenever segments must be retained for archiving, replication slots, or other requirements.

Increasing `max_wal_size` can reduce checkpoint pressure but allows even more WAL to accumulate. Never raise this setting as a way to clear disk space.

### 8.3. min_wal_size and wal_keep_size

`min_wal_size` affects how many WAL segments PostgreSQL keeps around for reuse. It is not a cap on total WAL retention.

`wal_keep_size` enforces keeping a minimum amount of WAL for streaming standbys in certain scenarios. It is not a cap on total WAL and does not resolve slot or archive backlogs.

### 8.4. Replication Slots and Archiving

A replication slot retains WAL needed by its consumer. If a standby or logical subscriber stops running, the slot can retain WAL indefinitely.

When the archive command fails, WAL segments awaiting archiving cannot be recycled normally. `pg_wal` can grow even when workload stays flat.

## 9. Measuring WAL Size and Retention

### 9.1. pg_wal Directory Size

On PostgreSQL versions supporting `pg_ls_waldir()`:

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)) AS wal_directory_size
FROM pg_ls_waldir();
```

This function requires appropriate privileges. If your role lacks access, use OS metrics or a suitably privileged monitoring role. Never grant superuser solely so a dashboard can run one query.

### 9.2. WAL Statistics

On versions providing `pg_stat_wal`:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

`wal_bytes` is a cumulative counter since stats reset. Take two snapshots separated by an interval to estimate the generation rate. Catalog fields and view availability depend on PostgreSQL version.

### 9.3. Replication Slots Inventory

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Columns like `wal_status` and `safe_wal_size` do not exist on every major version. Adjust the query to match the actual catalog.

### 9.4. Estimating WAL Retained by Slots

On the primary, you can estimate the LSN distance:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

This estimates the LSN distance from `restart_lsn` to the current WAL position, not exact filesystem bytes. Multiple slots can share retained segments; do not sum their estimates and treat the sum as total disk space occupied.

### 9.5. Standby Lag

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

Lag time fields may be `NULL` or fail to represent lag accurately without recent samples. Compute LSN distance as well.

### 9.6. Evaluating Inactive Slots

A slot with `active = false` is not necessarily useless. It may belong to a temporarily disconnected subscriber, a backup service, or a consumer undergoing maintenance. Check the owner/service and retention contract before dropping it.

### 9.7. max_slot_wal_keep_size

`max_slot_wal_keep_size` caps how much WAL is retained for replication slots on supported versions. When exceeded, the slot can become invalidated and the consumer must resynchronize or reinitialize.

Never lower this setting mid-incident without understanding the consequences. An invalidated slot can break the ability to resume replication or CDC from its prior position.

## 10. Handling Replication Slots Retaining WAL

### 10.1. Identify the Slot Owner

Map each slot to its physical standby, logical subscriber, CDC connector, backup tool, custom logical decoding client, or managed database service. Inspect consumer monitoring and application configurations.

### 10.2. Recover the Consumer First

If the consumer still needs the data, prioritize restoring networking, credentials, the subscription, or the worker so the slot advances and WAL can be recycled once other conditions permit.

### 10.3. Obsolete Slots

Drop a slot only when the owner confirms there is no active consumer or recovery requirement:

```sql
SELECT pg_drop_replication_slot('old_cdc_slot');
```

Never drop an active slot. Before dropping, confirm the consumer can be rebuilt from a snapshot/rebootstrap and the business owner accepts losing continuity.

### 10.4. Logical Subscriptions and Physical Slots

If a slot belongs to a logical replication subscription, manage it through the subscription lifecycle and documented procedures. A physical standby may depend on a slot to catch up on WAL after downtime. Dropping the slot can force the standby to be reinitialized from a base backup if required WAL has already been recycled.

Dropping a slot frees WAL retention at the cost of breaking consumer resumption. It is a replication state change, not deleting junk files.

## 11. WAL Archives and Archive Backlogs

### 11.1. Checking Archive Configuration

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW archive_timeout;
```

If `archive_mode` is off, PostgreSQL is not archiving WAL via traditional archiving. If using an archive library, `archive_command` may be empty.

### 11.2. pg_stat_archiver

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

If `failed_count` is climbing, inspect command logs, permissions, networking, destination capacity, and file naming. Statistics can be reset, so compare timestamps and counters against the incident timeline.

### 11.3. Archive Command Contract

`archive_command` must return exit status `0` once the WAL file is safely stored. If it returns non-zero, PostgreSQL retries. The command must be idempotent: if a file already exists with identical content, it must neither corrupt the archive nor return success for a different file.

Illustrative example for a local archive path:

```conf
archive_mode = on
archive_command = 'test ! -f /mnt/pg_archive/%f && cp %p /mnt/pg_archive/%f'
```

This is a minimal example, not a complete production configuration. You must handle permissions, atomic publishing, checksums, duplicate delivery, filesystem errors, and retention. For cloud storage, use a supported archiver/tool rather than a custom shell command whenever available.

### 11.4. Archive Destination Full

If the archive volume is full, confirm the mount and capacity of the archive path; verify backup retention and standby recovery needs; expand the destination or remove expired data per backup policy; fix archive command credentials/permissions if broken; verify `archive_command` returns `0`; and monitor `pg_stat_archiver` and the WAL directory until the backlog clears.

Freeing space on the archive disk does not automatically clear primary `pg_wal` if the command still fails or a slot is still holding segments.

### 11.5. Archive Destination Unreachable

Network outages, expired credentials, DNS, TLS, bucket policies, or unmounted shares can cause the archive command to fail. Inspect both service logs and remote storage metrics.

### 11.6. Archive Status Files

`.ready` files in `pg_wal/archive_status` represent segments awaiting archiving; `.done` indicates archiving succeeded for that segment. These are internal metadata used by PostgreSQL to manage archiving.

You can inventory their state with OS tools, but never manually delete or rename `.ready` or `.done` files to force PostgreSQL to skip archiving.

### 11.7. Archive Retention

WAL archives may be required for PITR, standby recovery, backup chains, logical decoding/CDC workflows, and compliance/audit recovery requirements.

Clean up archives only via a retention policy aware of base backups and standby requirements. `pg_archivecleanup` can be useful in suitable topologies, provided you calculate the exact oldest required WAL segment. Never run it against a shared archive repository serving multiple clusters without coordination.

## 12. Checkpoints and WAL Recycling

A checkpoint writes state indicating from where recovery must replay WAL. After a checkpoint, eligible WAL segments become candidates for recycling if no other retention requirements apply.

Even after a checkpoint finishes, PostgreSQL cannot recycle WAL still needed by a replication slot or archiving. Thus, `CHECKPOINT` is not an arbitrary WAL-freeing command.

Overly frequent checkpoints increase I/O and full-page writes. Overly infrequent checkpoints require more WAL and lengthen recovery. Tune based on workload, storage, and recovery objectives.

Checkpoint statistics views and columns vary by major version. Check `pg_stat_bgwriter` and version-appropriate statistics views; in newer versions, several checkpoint metrics moved to a dedicated view.

Do not spam `CHECKPOINT`. It can create I/O pressure without releasing WAL held by slots or archiving. Raising `max_wal_size` can reduce checkpoint frequency depending on workload, while allowing more WAL to accumulate.

## 13. Temporary Files Filling the Disk

### 13.1. Sources of Temporary Files

Temporary files can be created by `ORDER BY`/sorts exceeding `work_mem`, hash joins and hash aggregations, `DISTINCT` and `GROUP BY`, materialized intermediate results, certain index builds, and explicit temporary tables.

### 13.2. pg_stat_database

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_since_reset,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
```

`temp_bytes` is a cumulative counter since stats reset, not the volume of temporary files currently sitting on disk.

### 13.3. Logging Temporary Files

You can configure:

```conf
log_temp_files = 64MB
```

This logs temporary files larger than the threshold when the file is deleted. `0` logs every temp file; a negative value disables logging. Choose a threshold that avoids log noise.

### 13.4. Finding Queries Generating Temp Files

Combine `pg_stat_statements` if installed, query logs with duration/temp file messages, `pg_stat_database.temp_files`/`temp_bytes`, `pg_stat_activity` to spot active queries, and `EXPLAIN (ANALYZE, BUFFERS)` on a test workload.

A running query may create huge temp files after a snapshot was taken; cumulative stats do not always reveal the exact file path or owning backend.

### 13.5. work_mem

`work_mem` is the memory budget per sort/hash operation, not a per-session cap. A query with multiple operations across many concurrent sessions can consume total memory many times larger than this value.

Raising `work_mem` to curb spills can trigger memory exhaustion. Use `SET LOCAL` for a well-understood query instead of arbitrarily raising the global setting.

### 13.6. temp_file_limit and temp_tablespaces

`temp_file_limit` caps the total temporary file space a single process can use under PostgreSQL's rules:

```sql
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

You can set limits per role, database, or session as appropriate. Exceeding the limit aborts the query; this protects disk space while potentially failing application requests.

If a dedicated temp tablespace fills up, spilling queries fail even when `PGDATA` has plenty of room. Check the right mount.

### 13.7. Do Not Delete Active pgsql_tmp Files

Temporary files are normally removed by the backend when the operation or session ends. If you spot a large file, identify the PID/backend and query first. If a backend crashed, PostgreSQL handles orphaned temp files via startup cleanup; never delete files belonging to a running process.

## 14. PostgreSQL Logs Filling the Disk

### 14.1. Identifying the Log Destination

```sql
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW log_filename;
SHOW log_rotation_age;
SHOW log_rotation_size;
SHOW log_truncate_on_rotation;
SHOW log_min_duration_statement;
SHOW log_statement;
```

`log_directory` can be relative to the data directory or an absolute path. If `logging_collector` is off, logs may route through `stderr`/syslog/service manager rather than a PostgreSQL-managed directory.

### 14.2. Log Rotation

An example configuration:

```conf
logging_collector = on
log_destination = 'stderr'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_truncate_on_rotation = on
```

This is an example only; tune for traffic and retention. `log_truncate_on_rotation` has semantics tied to filename patterns and rotation timing; it does not replace an external retention policy.

### 14.3. Log Verbosity

Settings like `log_statement = all`, `log_min_duration_statement = 0`, or verbose error logging can generate massive log volumes. Check recent changes and retain only the verbosity required for incident diagnostics or security policy.

Never disable logging entirely just to save disk during an active incident. You can dial back noisy categories or raise thresholds after preserving evidence.

### 14.4. Retention and Deleted-Open Files

Use log rotation/collector, OS `logrotate`, or centralized logging with intentional retention. If PostgreSQL keeps an open file descriptor to an unlinked file, trigger the proper reopen/reload mechanism to release disk space.

Never delete an actively written log file without understanding process file handling.

### 14.5. Logs in Containers and Managed Databases

When PostgreSQL logs to `stderr`, Docker or the container runtime may store logs on host storage or in a logging driver. Check container log rotation and node disk pressure. PostgreSQL's `log_rotation_size` does not manage Docker `json-file` logs.

Managed services may store logs in a provider logging service or expose download/export mechanisms. Use provider retention/rotation controls; never assume host filesystem access.

### 14.6. Audit Logs

Audit logs may require longer retention than operational logs. Separate storage/retention policies where needed, protect integrity, and minimize sensitive data inside logs.

## 15. A Tablespace or Separate Mount Is Full

### 15.1. Identifying Which Tablespace Owns a Relation

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    COALESCE(ts.spcname, 'database default') AS tablespace_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_tablespace AS ts
    ON ts.oid = NULLIF(c.reltablespace, 0)
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relkind IN ('r', 'i', 'm', 't')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
```

`reltablespace = 0` means the relation uses the database's default tablespace. The database default may differ from `pg_default`; check `pg_database.dattablespace` when exact verification is needed.

### 15.2. Database Default Tablespace

```sql
SELECT
    datname,
    dattablespace::regclass AS default_tablespace
FROM pg_database
ORDER BY datname;
```

### 15.3. Moving a Relation

`ALTER TABLE ... SET TABLESPACE` or `ALTER INDEX ... SET TABLESPACE` copies physical files, requiring locks and space at the destination. Do not use a move operation to rescue an exhausted filesystem unless sufficient headroom exists at both source and destination.

### 15.4. Missing Tablespace Mount

If a mount is not attached when PostgreSQL starts, relation files may be inaccessible. Never create an empty directory at the same path to trick PostgreSQL. Restore the proper mount/device and verify filesystem integrity.

## 16. Checking Backup and Archive Storage

### 16.1. Distinguishing Base Backups and WAL Archives

A base backup is a point-in-time copy of cluster data. The WAL archive supplies log segments to replay up to a desired target time. PITR typically requires both a valid base backup and continuous WAL from that backup to the recovery target.

### 16.2. Do Not Delete WAL Archives Simply by File Age

An old WAL segment may still be required by an in-retention base backup or a lagging standby. Retention logic must know which backups remain valid, the WAL range each backup requires, standby recovery points, logical decoding/CDC retention, committed PITR windows, and replication topology.

### 16.3. Backup Catalog and Archive Cleanup

Use your backup tool or catalog to determine backup chains and retention—never rely solely on directory listings.

If using `pg_archivecleanup`, compute the exact oldest required segment and run it only against an archive directory dedicated to that standby/topology. Never apply a single cutoff to a shared archive repository across multiple clusters without coordination.

### 16.4. Testing Backup Restores

Cleanup is only safe if backups remain restorable. Regularly test restores and verify WAL archive continuity.

## 17. Finding the Cause of Rapid Disk Growth

### 17.1. Bulk Loads or Backfills

Large `COPY`/`INSERT`/`UPDATE` jobs expand table size and WAL. Check recent application releases, ETL schedules, migration jobs, and batch sizes.

### 17.2. UPDATEs Generating Dead Tuples

`UPDATE` creates new row versions. If autovacuum falls behind, table and index bloat grow. Check vacuum thresholds, per-table settings, long transactions, and I/O capacity.

### 17.3. CREATE INDEX/REINDEX and Table Rewrites

Index builds require space for the new index. Concurrent builds temporarily hold both old and new indexes. Monitor `pg_stat_progress_create_index` while operations run.

`ALTER COLUMN TYPE`, `VACUUM FULL`, `CLUSTER`, and certain DDL operations rewrite relations. Estimate peak disk, WAL, and replication impact before running them.

### 17.4. Replication Slots and Archive Commands

A stopped CDC consumer stalls `restart_lsn` and drives continuous WAL growth. Alert on retained WAL per slot and slot age/activity.

Full destinations, permissions, networking, or credentials push archive failure counts up and block WAL recycling.

### 17.5. Logging, Temp Spills, and Backup Staging

`log_statement = all`, overly low duration thresholds, audit logging, or tight retry error loops can produce gigabytes of logs.

Sort/hash queries, reporting workloads, or query plan regressions can create massive temp files. Check `temp_bytes` and query stats.

Backup jobs may stage temporary copies on the same volume. Check backup staging and retention, taking care never to delete the sole restorable backup.

### 17.6. Core Dumps

Repeated crashes can produce huge core dumps. Identify the source and follow OS crash-dump policies after preserving needed evidence.

## 18. Consolidated Diagnostic Queries

### 18.1. Database Sizes

```sql
SELECT
    datname,
    pg_database_size(datname) AS bytes,
    pg_size_pretty(pg_database_size(datname)) AS pretty_size
FROM pg_database
WHERE datallowconn
ORDER BY bytes DESC;
```

### 18.2. Top User Tables

```sql
SELECT
    schemaname,
    relname,
    pg_total_relation_size(relid) AS bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS pretty_size,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY bytes DESC
LIMIT 25;
```

### 18.3. Top Indexes

```sql
SELECT
    schemaname,
    relname,
    indexrelname,
    pg_relation_size(indexrelid) AS bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS pretty_size,
    idx_scan
FROM pg_stat_user_indexes
ORDER BY bytes DESC
LIMIT 25;
```

### 18.4. WAL Directory

```sql
SELECT
    count(*) AS file_count,
    sum(size) AS bytes,
    pg_size_pretty(sum(size)) AS pretty_size
FROM pg_ls_waldir();
```

### 18.5. Archive Health

```sql
SELECT *
FROM pg_stat_archiver;
```

### 18.6. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

### 18.7. Temporary File Counters

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 18.8. Long-Running Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 18.9. Vacuum and Index Build Activity

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
```

```sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
```

Progress views appear depending on the active operation and version. An empty result simply means no matching operation is running; it does not prove there is no disk pressure.

## 19. Emergency Response by Source

### 19.1. If Table/Index Data Consumes the Space

Identify top relations and growth rate; locate running bulk jobs, backfills, or table rewrites; pause or throttle producers if growth exceeds capacity; check dead tuples and vacuum progress; never run `VACUUM FULL`/`REINDEX` without headroom; expand the volume or relocate workloads to suitable storage; and schedule maintenance to reclaim bloat after stabilizing.

### 19.2. If pg_wal Consumes the Space

Check `pg_stat_archiver`, `pg_replication_slots`, and retained LSN; inspect standby/CDC consumers; check archive destination capacity and connectivity; fix archive paths, credentials, or permissions; recover necessary consumers; drop a slot only after owner approval and recovery impact review; and monitor the WAL directory shrinking/recycling once retention blockers clear.

Never delete WAL segments via the filesystem.

### 19.3. If the Archive Volume Is Full

Identify backup chains and retention; expand archive storage if needed; clean up only expired retention per the backup catalog; fix the archive command and verify exit `0`; and monitor the backlog archiving and primary WAL recycling.

### 19.4. If Temporary Files Consume the Space

Find queries creating temp spills; stop or throttle reporting/jobs driving the spike; inspect query plans, indexes, and sort/hash operations; adjust `work_mem` with strict limits and measure concurrency; configure `temp_file_limit` per role/database where appropriate; check temp tablespaces; and allow backends to exit and clean up files per their lifecycle.

### 19.5. If Logs Consume the Space

Identify log destination and file owner; preserve incident evidence; fix rotation/retention; reduce noisy log verbosity if policy allows; trigger proper log reopening if processes hold deleted file descriptors; and plan dedicated log volumes or centralized logging going forward.

### 19.6. If a Tablespace Is Full

Map relations to the tablespace and mount; verify whether the mount disconnected; expand the volume or free verified non-database files; avoid moving relations while source or destination lacks capacity; and verify tablespace paths before any PostgreSQL restart.

## 20. Recovering When PostgreSQL Cannot Write or Has Stopped

### 20.1. Expand the Filesystem First

If PostgreSQL stopped due to disk full, prioritize expanding capacity or freeing verified space outside database storage. Ensure sufficient headroom for startup recovery, WAL writes, and logs.

### 20.2. Verify Mounts

Confirm every mount containing `PGDATA`, tablespaces, WAL symlinks, and required storage is properly attached. An empty directory replacing an unmounted filesystem can make PostgreSQL see an empty directory or missing relation files.

### 20.3. Read Startup Logs

Look for the final errors regarding WAL, checkpoints, control files, relation files, permissions, and filesystems. Distinguish disk-full failures from corruption or missing tablespaces.

### 20.4. Do Not Re-Run initdb or Delete WAL

Never run `initdb` against an existing data directory to fix disk full. `initdb` creates a new cluster and can destroy access to existing data.

Never delete WAL just to get PostgreSQL to start. If WAL needed for crash recovery or archive continuity is deleted, the cluster may refuse to start or fail to complete recovery. Recover from valid backups and WAL following documented recovery procedures.

### 20.5. After Service Startup

Verify database consistency and logs; check archive health, replication slots/standbys, tablespace paths, application read/write behavior, and backup jobs. Monitor disk growth rate. Resume bulk jobs only after capacity stabilizes.

If WAL or data files are suspected deleted, halt cleanup immediately, preserve current volumes/snapshots, and escalate to backup/PITR recovery assessment or PostgreSQL recovery specialists. Never fabricate empty files or edit catalogs to fill gaps.

## 21. Reclaiming Space Safely

### 21.1. Logs and Backup Staging

Clean up logs past retention per logging policy after confirming no process holds them open and they are not needed as evidence.

Remove staging files only once the backup job's completed/failed state is clear, the official backup is verified, and retention allows. Never delete the sole remaining backup.

### 21.2. Archive Retention

Use backup catalog/retention-aware cleanup. Check all base backups and standby consumers before deleting WAL archives.

### 21.3. Orphaned Temporary Files

If PostgreSQL stopped cleanly or backend processes exited, startup cleanup normally removes temp files. If orphaned files remain after a crash, clean them up strictly per documented procedures after confirming no backend uses them and the path is genuinely a temp area.

### 21.4. Table Bloat

Once sufficient headroom exists, run regular `VACUUM` to reclaim reusable space; tune autovacuum thresholds/cost limits per table workload; evaluate `pg_repack` or `VACUUM FULL` for a maintenance window; check index bloat and reindex as needed; and inspect long-running transactions/replication horizons.

### 21.5. Unused Indexes

Never drop an index mid-incident solely due to low `idx_scan`. Confirm the statistics window, constraint dependencies, query patterns, and seasonal workloads. Use `DROP INDEX CONCURRENTLY` when appropriate, noting it still consumes resources and cannot run inside a transaction block.

### 21.6. Moving Data to Another Tablespace

Relocating relations can relieve one mount but requires space and locks at the destination. Plan per object, checking index/TOAST/partition behavior and rollback paths.

## 22. Capacity Planning for PostgreSQL

### 22.1. Model Growth by Workload

Track daily/weekly/monthly growth of table data, indexes, TOAST, WAL, archives, logs, temporary files, and backup staging. Separate organic baseline growth from maintenance or incident spikes.

### 22.2. Provision for Peak, Not Just Steady State

An operation may simultaneously hold old table/index files, a new table/index copy, WAL generated during the operation, archive backlogs, temporary sort/build files, backup staging, and safety headroom.

Never provision solely for final steady-state relation size.

### 22.3. Headroom and Time-to-Full

Configure warning thresholds well before 100%. For example, internal policies may alert at 70%, 80%, 90%, and critically higher; calibrate thresholds to growth rate and how long volume expansion takes.

Use available bytes and growth rate to project time-to-full. Alerting on time-to-full is often far more actionable than percentages alone.

### 22.4. Separate Storage Domains

Where possible, separate database data, WAL, WAL archive/backup repositories, PostgreSQL logs, temporary workloads, and application/export staging. Separating mounts keeps one file class from instantly exhausting all cluster storage, though each volume still needs independent capacity management.

### 22.5. Cloud Volumes, Containers, and Kubernetes

Monitor provisioned capacity, burst credits/IOPS throughput, filesystem expansion steps, and cloud limits. Growing a cloud volume often requires an explicit filesystem resize step after the provider expands block storage.

For containers and Kubernetes, monitor PVC capacity/usage, node ephemeral storage, container writable layers, log driver storage, volume mount paths, `StorageClass` expansion support, and pod eviction thresholds.

Free space on the underlying host does not guarantee free capacity inside a PVC or container quota.

## 23. Monitoring and Alerting

### 23.1. Filesystem Metrics

Alert per mount on used bytes/percent, available bytes, inode usage, growth rate/time-to-full, I/O latency, and volume attach/health status.

### 23.2. PostgreSQL Relation Metrics

Track database/table/index/TOAST sizes over time, dead tuples, autovacuum activity, and relation growth rates.

### 23.3. WAL Metrics

Track `pg_wal` directory size, WAL generation bytes/sec, replication slot retained WAL, inactive slot age, `pg_stat_archiver.failed_count`, last successful archive timestamp, standby replay lag, and WAL archive backlog.

### 23.4. Temporary File and Logging Metrics

Track `pg_stat_database.temp_files`/`temp_bytes`, query-level temp blocks from `pg_stat_statements` if supported, `log_temp_files` messages, log bytes/day, rotation success, external log driver usage, and retention cleanup.

### 23.5. Root-Cause Alerts

A 90% disk alert only reports the symptom. Pair it with specific alerts: rising `failed_count` on the archiver, slot retained WAL above threshold, inactive slots holding WAL too long, spikes in temp bytes, table growth above baseline, long transaction age above threshold, surging log volume, and backup staging exceeding retention.

## 24. Investigation Dashboard

A useful dashboard places related signals side by side on the same timeline:

| Group | Metrics | Questions Answered |
| --- | --- | --- |
| Filesystem | Used/available/inodes/growth | Which mount is filling and when? |
| Relation | Database/table/index/TOAST size | What data is growing? |
| Vacuum | Dead tuples, last autovacuum, progress | Is cleanup keeping up? |
| WAL | `pg_wal` size, `wal_bytes`/sec | How much WAL is generated/retained? |
| Replication | Slot retained bytes, replay lag | Which consumer is holding WAL? |
| Archiving | `failed_count`, `last_archived_time` | Is WAL being archived? |
| Temp | `temp_files`/`temp_bytes` | Which queries are spilling? |
| Logs | Bytes/hour, rotation status | Which log source exploded? |
| Workload | Active queries, jobs, deployments | What event triggered growth? |

Synchronize timezones and timestamps across PostgreSQL, OS, cloud metrics, and application logs for accurate correlation.

## 25. Common Pitfalls

| Symptom / Assumption | Cause | Resolution |
| --- | --- | --- |
| Small database size yet disk is full | WAL/logs/temp/backups sit outside relation sizes | Inspect every mount and directory |
| `pg_wal` grows under normal traffic | Slot or archive holding segments | Check `restart_lsn`, archiver, and consumers |
| Raised `max_wal_size` yet disk keeps filling | It is a soft limit; retention blockers still hold WAL | Resolve slot/archive blockers and capacity |
| Archive repeatedly fails | Destination full, permissions, or network | Fix archive path/service, confirm exit `0` |
| Replica offline and WAL climbs | Physical slot retains WAL | Recover standby or assess reinitialize/drop slot |
| CDC connector stopped and WAL climbs | Inactive logical slot | Recover consumer or coordinated rebootstrap |
| `VACUUM` ran yet disk usage did not drop | Normal `VACUUM` keeps space for reuse | Understand difference from `VACUUM FULL`/repack |
| `VACUUM FULL` failed out of disk | Needs new copy alongside old relation | Expand capacity and schedule maintenance |
| Index rebuild inflated disk usage | Old and new indexes coexist | Provision peak space before `REINDEX` |
| Temp files surge | Sort/hash spills or reporting workload | Query analysis, bounded `work_mem`/`temp_file_limit` |
| Log directory grows nonstop | Misconfigured rotation/retention or verbose logging | Check collector, rotation, and log driver |
| Deleted log files yet disk space did not drop | Process still holds unlinked file open | Reopen/rotate properly, check deleted-open files |
| `df` shows free bytes yet file creation fails | Inode or quota exhaustion | Check `df -i` and quotas |
| Host has space yet PostgreSQL reports full | PVC/container quota or another mount is full | Check the process's actual volume |
| Dropping slot broke CDC/standby | Consumer still needed continuity | Reinitialize/rebootstrap per owner approval |
| Manual WAL deletion prevented cluster start | Crash recovery/archive chain broken | Restore from valid backups and WAL |
| Archive cleanup broke PITR | Deleted WAL needed for backup chain | Test restores and use retention-aware cleanup |

## 26. Production Incident Runbook

**Step 1 — Confirm the mount.** Record filesystem, available bytes, inode usage, mount path, and growth rate.

**Step 2 — Map PostgreSQL paths.** Check `data_directory`, tablespaces, `pg_wal`, `log_directory`, `temp_tablespaces`, and archive destination.

**Step 3 — Contain growth.** Pause or throttle the workload or job driving disk growth; keep essential application traffic running if safe.

**Step 4 — Preserve recovery.** Never delete WAL or data files. Identify backup chains, archive status, and replication slot owners.

**Step 5 — Inspect relations.** Query top databases, tables, indexes, TOAST, and dead tuples.

**Step 6 — Inspect WAL.** Check directory size, `pg_stat_wal`, slots, standby lag, and archive failures.

**Step 7 — Inspect temporary files and logs.** Check temp counters, active queries, log destination, rotation, and external log drivers.

**Step 8 — Add capacity or clean up safely.** Prefer volume expansion; clean up only files outside `PGDATA` verified as expired or unused.

**Step 9 — Restore archiving and replication.** Fix destinations, credentials, and consumers, and monitor backlog drainage.

**Step 10 — Confirm PostgreSQL stability.** Verify writes, checkpoints, vacuum, archiving, replication, logs, and application errors.

**Step 11 — Reclaim bloat post-incident.** Schedule vacuum/repack/reindex once sufficient headroom and a maintenance window exist.

**Step 12 — Prevent recurrence.** Add source-specific alerts, time-to-full alerting, retention reviews, and capacity forecasting.

## 27. Recovery Checklist When Disk Hits 100%

When a volume is completely exhausted, prioritize restoring write capability:

1. Stop the workload driving continued growth.
2. Identify the exact mount containing the full filesystem.
3. Expand the volume or free verified non-PostgreSQL files.
4. Ensure headroom for WAL, checkpoints, logs, and recovery.
5. If the archive destination is full, restore storage/permissions there first.
6. If PostgreSQL stopped, read startup logs and verify mounts.
7. Never delete `pg_wal`, relation files, or unexpired archives.
8. Once the service is up, inspect the archiver and replication slots.
9. Verify backup and PITR continuity.
10. Monitor disk usage and growth rate until stable.

If internal files were already deleted or filesystem corruption occurred, preserve the current volume/snapshot and transition to recovery assessment instead of attempting further cleanup.

## 28. Practice Exercises

Perform these in a PostgreSQL lab with dedicated filesystems/volumes. Never intentionally fill production, never delete files inside `PGDATA`, and never delete archives needed for real backups.

### Exercise 1 — Checking Database Sizes

Use `pg_database_size()` to list the largest databases and compare them against filesystem usage.

### Exercise 2 — Top Relations

Use `pg_total_relation_size()` to list the 20 largest tables/indexes. Compare table size with total size.

### Exercise 3 — TOAST Storage

Create a table with large `text`/`jsonb` values. Inspect its TOAST relation and compare `pg_table_size()` with `pg_relation_size()`.

### Exercise 4 — Index Footprint

Create multiple indexes on a table. Measure `pg_indexes_size()` and identify which indexes consume the most space.

### Exercise 5 — Partition Footprint

Create a partitioned table with multiple partitions. List each child's size and find the largest partition.

### Exercise 6 — Dead Tuples

Generate a large `UPDATE`/`DELETE` workload. Observe `n_dead_tup`, run `VACUUM`, and compare sizes before and after.

### Exercise 7 — Regular VACUUM vs. VACUUM FULL

In a lab with ample disk, compare locks, runtime, and relation size for both operations. Note why regular `VACUUM` does not necessarily shrink files.

### Exercise 8 — pgstattuple

Install `pgstattuple` in the lab, measure dead tuples and free space for a relation, and compare with statistics estimates.

### Exercise 9 — WAL Generation

Run `INSERT`/`UPDATE` batches and take two `pg_stat_wal` snapshots. Compute WAL bytes/sec.

### Exercise 10 — pg_wal Inventory

Use `pg_ls_waldir()` and OS `du` to compare file counts and sizes. Identify privileges required for the SQL function.

### Exercise 11 — max_wal_size

Adjust workload and checkpoint settings in the lab. Observe why `pg_wal` can exceed `max_wal_size` when retention blockers exist.

### Exercise 12 — Physical Replication Slot

Create a physical slot in the lab, stop the standby from consuming WAL, and observe retained WAL growing. Restore the consumer and observe recycling behavior.

### Exercise 13 — Inactive Logical Slot

Create a logical slot, do not consume changes, and observe `restart_lsn`. Assess retention risk and plan cleanup/rebootstrap.

### Exercise 14 — Slot Monitoring

Write a query reporting estimated retained WAL per slot, active state, database, and owner metadata.

### Exercise 15 — Archive Command

Enable archiving in the lab with a dedicated archive path. Verify WAL files are archived and `pg_stat_archiver.archived_count` increments.

### Exercise 16 — Archive Failure

Simulate a controlled archive command failure in the lab. Observe `failed_count`, `.ready` status files, and `pg_wal` growth. Restore the command and watch the backlog clear.

### Exercise 17 — Archive Destination Full

Use a small filesystem quota in the lab or simulate a write failure. Restore capacity and verify archive retries.

### Exercise 18 — Archive Retention

Create a base backup and WAL archive in the lab. Test retention cleanup on an isolated copy and prove the backup remains PITR-capable.

### Exercise 19 — Temporary File Spill

Run a sort/hash workload on a sufficiently large dataset with low `work_mem`. Observe `temp_files`/`temp_bytes`.

### Exercise 20 — log_temp_files

Enable `log_temp_files` with a low threshold in the lab. Run a spilling query and locate the corresponding log entry.

### Exercise 21 — temp_file_limit

Set a low `temp_file_limit` for a test session. Run a query generating large temp files and observe query failure and cleanup.

### Exercise 22 — work_mem Concurrency

Run multiple concurrent queries with sorts/hashes. Measure memory and temp usage; find a configuration that avoids memory exhaustion.

### Exercise 23 — Log Rotation

Configure the logging collector and `log_rotation_size`/`age` in the lab. Confirm new files are created and retention works.

### Exercise 24 — Log Verbosity

Compare log growth across different `log_statement` and duration threshold settings. Design a threshold balancing diagnostics and storage.

### Exercise 25 — Deleted-Open Logs

On a Linux lab host, rotate/unlink a log file while a process still holds it open. Use `lsof +L1` to find the file descriptor and test reopening via the appropriate service mechanism.

### Exercise 26 — Inode Exhaustion

Create many small files in an isolated test filesystem to simulate inode exhaustion. Distinguish inode exhaustion from byte exhaustion.

### Exercise 27 — Tablespace Monitoring

Create a tablespace on a separate mount, place a table/index there, and query `pg_tablespace_size()` alongside OS usage.

### Exercise 28 — Tablespace Full

Use a small quota in the lab to fill a tablespace. Identify the failing statement and recover by expanding the volume.

### Exercise 29 — Long Transactions and Vacuum

Hold a transaction snapshot open, generate `UPDATE`/`DELETE` churn, and observe vacuum cleanup being blocked. End the transaction and monitor vacuum recovery.

### Exercise 30 — REINDEX Capacity

Create a large index and measure space required for standard `REINDEX` versus `REINDEX CONCURRENTLY` in the lab. Determine peak disk requirements.

### Exercise 31 — Docker Volumes

Run a PostgreSQL lab in a size-limited Docker volume. Compare host free space, volume usage, and container log usage.

### Exercise 32 — Kubernetes PVC

Generate test workload on a PVC, inspect capacity/usage, and practice volume expansion where the `StorageClass` supports it.

### Exercise 33 — Time-to-Full Alert

Collect periodic filesystem snapshots and compute growth rate and time-to-full. Build a test alert against sample thresholds.

### Exercise 34 — Incident Tabletop

Simulate rising `pg_wal`, a full archive destination, and an inactive logical slot. Document the containment and recovery sequence without blindly dropping the slot.

### Exercise 35 — End-to-End Recovery Runbook

Build a lab with table growth, WAL archiving, and logs. Simulate disk pressure, preserve evidence, expand capacity, restore archiving, verify replication, and write a post-incident report.

## 29. Summary

Core takeaways when resolving **disk full due to tables, WAL, archives, or logs**:

1. Identify which filesystem/mount is actually full before cleaning anything up.
2. Database size does not include all disk consumers such as WAL archives, logs, temp files, backup staging, or container logs.
3. Use `pg_total_relation_size`, `pg_table_size`, and `pg_indexes_size` to analyze table, index, and TOAST footprints.
4. Dead tuples and bloat expand relations; regular `VACUUM` keeps space for reuse, whereas `VACUUM FULL`/repack require extra disk and locks.
5. `pg_wal` growth can stem from workload, replication slots, archive failures, or retention rules.
6. `max_wal_size` is a soft limit, not a hard cap; `wal_keep_size` and slot retention have distinct semantics.
7. Use `pg_replication_slots`, `pg_stat_replication`, and `pg_stat_archiver` to locate WAL consumers and archive blockers.
8. Drop replication slots only after confirming owner, recovery impact, and a rebootstrap plan.
9. Archive cleanup must respect base backups, PITR windows, and standby consumers.
10. Temporary files usually stem from sort/hash spills; `work_mem` is a per-operation budget, so raising it globally risks memory exhaustion.
11. Logs need proper rotation and retention; check both PostgreSQL's collector and container/OS logging.
12. Check inodes, quotas, tablespaces, and PVCs—not just bytes on the host.
13. Never manually delete `pg_wal`, relation files, or unexpired archives.
14. When disk is full, prioritize containment and expanding capacity; reclaim relation bloat or run reindex/rewrite after restoring headroom.
15. After recovery, verify archiving, replication, backups/PITR, application writes, and growth rate.

Disk exhaustion is fundamentally about managing multiple storage lifecycles simultaneously. A strong runbook connects filesystem metrics with PostgreSQL catalogs, WAL retention, archive health, query workloads, and backup policies. Once you pinpoint the growth source and what consumer is holding files, you can reclaim space while preserving crash recovery, replication, and PITR.

## 30. PostgreSQL References

- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — relation files, pages, forks, and TOAST.
- [Database File Layout](https://www.postgresql.org/docs/current/storage-file-layout.html) — data directory layout.
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html) — WAL architecture.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — checkpoints, WAL sizing, and archiving settings.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — `archive_command`, WAL archiving, and PITR.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot behavior and retained WAL.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber and logical slot behavior.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity` and statistics views.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archiver statistics.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — vacuum, index build, and operation progress.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, autovacuum, and space reuse.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — `VACUUM` options and `FULL` behavior.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — relation storage locations.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — `work_mem` and `temp_file_limit`.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — logging collector, rotation, and log settings.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space inspection extension.

The `/current/` links point to the current PostgreSQL documentation. Catalog fields, monitoring views, replication slot limits, and configuration parameters may differ across major versions. Before running recovery, confirm your PostgreSQL version, storage topology, backup tool, WAL archive retention, and dependent standby/CDC consumers.
