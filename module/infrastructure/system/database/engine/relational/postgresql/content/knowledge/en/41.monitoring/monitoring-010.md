# Measuring Capacity, Data Growth Rate, and Free Space in PostgreSQL

Tracking PostgreSQL storage is more than running one command to see how many gigabytes a database occupies. Operators need to know **what data is growing, how fast it is growing, which volume is running out of room, and where free space actually resides**.

PostgreSQL provides size functions such as `pg_database_size`, `pg_total_relation_size`, `pg_table_size`, `pg_indexes_size`, and `pg_tablespace_size` to measure storage at different levels. Statistics views help estimate write activity, temporary files, dead tuples, and WAL generation. However, filesystem or cloud volume free space must be observed at the OS or infrastructure provider layer.

A common source of confusion is that “free space” has multiple meanings. A table can contain internal page free space ready for reuse while the relation file still occupies the exact same bytes on disk. A filesystem can have ample space while a database suffers heavy bloat; conversely, a small database can sit on a nearly full volume due to WAL, logs, backups, or external files.

This lesson explains how to measure database, table, index, TOAST, tablespace, and WAL sizes; record growth history; calculate growth rates and time to threshold; distinguish reusable page space from filesystem free space; monitor autovacuum, temporary files, and replication slots; and design capacity dashboards, alerts, and runbooks.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish database, relation, table, index, tablespace, and filesystem storage.
2. Use `pg_database_size`, `pg_relation_size`, `pg_table_size`, `pg_indexes_size`, and `pg_total_relation_size`.
3. Measure storage by schema, table, index, and partition.
4. Assess the impact of TOAST, dead tuples, and bloat.
5. Measure tablespace sizes and map them to underlying storage volumes.
6. Monitor `pg_wal`, archive backlogs, and WAL pinned by replication slots.
7. Measure temporary files and data modification activity.
8. Store size snapshots over time and compute growth rates.
9. Forecast when volumes will hit capacity thresholds.
10. Distinguish page-level free space, dead tuples, reusable space, and filesystem free space.
11. Understand how `VACUUM`, `VACUUM FULL`, `TRUNCATE`, `DROP`, and `REINDEX` affect disk usage.
12. Design alerts on capacity, growth rate, and remaining time-to-full.
13. Investigate abnormal disk growth and avoid operations that exhaust disk space.
14. Build capacity management dashboards and runbooks for PostgreSQL.

## 2. Four Storage Layers to Monitor

A capacity report should separate at least four layers:

| Layer | Question | Primary Tools |
| --- | --- | --- |
| Database/object | How much space do databases, tables, and indexes occupy? | PostgreSQL size functions |
| Tablespace | Which tablespaces hold the data? | `pg_tablespace_size`, `pg_tablespace` |
| WAL/temporary | How much space do WAL and temporary files use? | `pg_ls_waldir`, `pg_stat_wal`, `pg_stat_database` |
| Filesystem/volume | How many bytes and inodes remain free on each volume? | OS tools, cloud metrics |

### 2.1. Database size is not filesystem usage

`pg_database_size` measures the files belonging to one database. It does not measure the entire volume hosting PostgreSQL. The volume may also hold:
- Other databases.
- WAL inside `pg_wal`.
- Tablespaces residing on the same volume.
- PostgreSQL logs.
- Temporary files.
- Backup staging or export files.
- OS files and other services.

### 2.2. Filesystem free space is the real operational ceiling

PostgreSQL requires extra headroom for WAL, temporary files, index builds, VACUUM rewrites, and bulk loads. When a volume fills up, writes and maintenance fail. Therefore, monitor free bytes per mount point, not database size alone.

### 2.3. Free space inside a table differs from volume free space

Regular `VACUUM` makes dead-tuple slots reusable inside the relation. The relation file generally does not shrink proportionally, and the filesystem does not automatically reclaim those bytes.

### 2.4. Backup storage is a separate failure domain

Backup repositories or object storage typically live outside the database volume. Track backup usage on a dedicated capacity dashboard to avoid double-counting or overlooking backup quotas and retention.

## 3. Measuring Database Size

`pg_database_size` returns the number of bytes used by a database.

~~~sql
SELECT
    datname,
    pg_database_size(oid) AS bytes,
    pg_size_pretty(pg_database_size(oid)) AS pretty_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(oid) DESC;
~~~

### 3.1. Store raw bytes for calculations

`pg_size_pretty` is strictly for display. Store raw `bigint` byte counts in your monitoring store to compute deltas and growth rates. Never parse formatted strings like `12 GB` for math.

### 3.2. Measuring the current database

~~~sql
SELECT
    current_database() AS database_name,
    pg_database_size(current_database()) AS bytes,
    pg_size_pretty(pg_database_size(current_database())) AS size;
~~~

### 3.3. Access privileges

Some size functions require appropriate privileges to inspect other objects or databases. Use a least-privilege monitoring role and verify behavior on your running PostgreSQL version.

### 3.4. Databases can shrink as well as grow

Database size rises or falls as tables are created/dropped, truncated, rewritten, vacuumed full, or modified. Never assume growth rates are always positive.

### 3.5. Do not add database sizes and tablespace sizes together

`pg_database_size` measures a database; `pg_tablespace_size` measures total space in a tablespace. Because tablespaces store database objects, summing all database sizes with all tablespace sizes double-counts storage.

## 4. Measuring Table, Index, and TOAST Sizes

PostgreSQL size functions measure different parts of a relation.

| Function | Storage Measured |
| --- | --- |
| `pg_relation_size(relation)` | By default, the main fork of the relation |
| `pg_table_size(relation)` | Table storage including TOAST and auxiliary forks; excludes indexes |
| `pg_indexes_size(relation)` | Total size of all indexes attached to the table |
| `pg_total_relation_size(relation)` | Table storage plus all indexes |

### 4.1. Finding the largest tables

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_relation_size(relid) AS main_bytes,
    pg_table_size(relid) AS table_bytes,
    pg_indexes_size(relid) AS index_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

`pg_stat_user_tables` lists one row per user table per version semantics; for partitioned tables, inspect both parents and individual child partitions to see physical storage.

### 4.2. Breaking down one table

~~~sql
SELECT
    'app.orders'::regclass AS relation,
    pg_size_pretty(pg_relation_size('app.orders')) AS main_fork,
    pg_size_pretty(pg_table_size('app.orders')) AS table_including_toast,
    pg_size_pretty(pg_indexes_size('app.orders')) AS indexes,
    pg_size_pretty(pg_total_relation_size('app.orders')) AS total;
~~~

### 4.3. Why do table_bytes and main_bytes differ?

`pg_table_size` includes TOAST storage and auxiliary forks such as the Free Space Map and Visibility Map. `pg_relation_size` defaults to the main fork alone and can therefore be significantly smaller.

### 4.4. TOAST

PostgreSQL stores oversized values such as long `text`, `bytea`, or other varlena fields out-of-line in a TOAST relation. Wide rows can accumulate substantial TOAST storage, which `pg_table_size` and `pg_total_relation_size` include.

### 4.5. Indexes

Indexes can equal or exceed the size of the table heap itself. Tables with many indexes, wide keys, or high update churn incur major index storage overhead. `pg_indexes_size` isolates index footprint.

### 4.6. Table size is not business row count

Two tables with identical row counts can vary dramatically in bytes due to row width, TOAST, `fillfactor`, indexes, and bloat. Use bytes for storage capacity planning and row counts to understand workload/data volume.

## 5. Ranking Relations by Schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'm' THEN 'materialized view'
        WHEN 'i' THEN 'index'
        ELSE c.relkind::text
    END AS relation_type,
    pg_total_relation_size(c.oid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

### 5.1. Why filter relkind?

`pg_class` holds many relation kinds: tables, indexes, sequences, views, and partitioned relations. The query above filters for storage-bearing types (`table`, `partitioned table`, `materialized view`). Adjust the filter if you want to inventory other object types.

### 5.2. Partitioned parents

Partitioned parents do not store rows directly, so the parent itself reports 0 or negligible bytes. Real storage resides in leaf partitions. Report per partition or aggregate the partition tree up to the parent to avoid misleading readers.

### 5.3. Indexes in reports

`pg_total_relation_size` on a table already includes its indexes. Adding index rows from `pg_class` on top of that double-counts storage. Choose one reporting model: table totals or a heap/index breakdown.

### 5.4. System objects

System catalogs, TOAST relations, and internal objects may be omitted from basic user-table reports. When reconciling against `pg_database_size`, account for objects outside application schemas as well.

## 6. Measuring Individual Index Sizes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_relation_size(
        format('%I.%I', schemaname, indexname)::regclass
    ) AS index_bytes,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', schemaname, indexname)::regclass
        )
    ) AS index_size,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(
    format('%I.%I', schemaname, indexname)::regclass
) DESC
LIMIT 50;
~~~

### 6.1. A large index is not automatically redundant

A large index may serve critical queries. Before dropping any index, inspect usage statistics, query plans, constraints, and application workloads.

### 6.2. pg_stat_user_indexes

This view exposes counters such as `idx_scan`, `idx_tup_read`, and `idx_tup_fetch`. Counters accumulate since stats reset or startup, so zero scans does not prove an index is unused unless the observation window is known and sufficiently long.

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan;
~~~

### 6.3. Unique indexes and constraints

An index may back a `PRIMARY KEY` or `UNIQUE` constraint. Never drop an index solely due to low `idx_scan`; constraint-enforcing indexes are required even if queries rarely scan them directly.

### 6.4. Reindexing requires extra capacity

`REINDEX` builds a fresh copy of the index and generally needs temporary extra storage while running. `REINDEX CONCURRENTLY` has its own locking and storage profile. Plan peak storage before running it on a nearly full volume.

## 7. Measuring Size by Tablespace

Tablespaces let you place relation files on distinct filesystems or volumes.

~~~sql
SELECT
    spcname AS tablespace_name,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY pg_tablespace_size(oid) DESC;
~~~

### 7.1. pg_default and pg_global

`pg_default` is the default tablespace for database objects. `pg_global` holds shared system catalogs. Default/global tablespace locations follow special conventions; `pg_tablespace_location` returns an empty string for default tablespaces.

### 7.2. A tablespace is not a mount point

A tablespace points to a directory on a filesystem. Multiple tablespaces can share one volume, or each can sit on a dedicated volume. Map each location to its actual mount/volume using OS tools.

### 7.3. Never add tablespace size to database size

Tablespace size is simply another grouping of the same relation files. Never sum both numbers to compute total disk usage.

### 7.4. Tablespace capacity

If a tablespace resides on its own volume, that volume can fill up while `PGDATA` still has plenty of space. Monitor free bytes separately for every tablespace location.

### 7.5. Moving relations between tablespaces

`ALTER TABLE ... SET TABLESPACE` or `ALTER INDEX ... SET TABLESPACE` copies the relation and requires extra disk space during the move. Assess locks, I/O, free capacity, and rollback before moving large objects.

## 8. Measuring Filesystem and Volume Free Space

PostgreSQL SQL views cannot replace OS-level filesystem monitoring. Use OS/host telemetry to track free bytes and inode availability on every mount.

Linux example:

~~~bash
df -h
df -i
~~~

Checking directory usage:

~~~bash
du -sh /var/lib/postgresql
du -sh /var/lib/postgresql/*
~~~

Actual paths vary by package, version, container layout, and deployment. Avoid running `du` continuously across huge data directories if it induces I/O overhead.

### 8.1. Mounts to monitor

- `PGDATA`.
- `pg_wal` if on a separate mount.
- Every tablespace location.
- PostgreSQL log directory.
- Temporary and staging directories.
- Local WAL archive spool if present.
- Backup staging directories.
- Container writable layer filesystems when running in containers.

### 8.2. Bytes and inodes

A volume can still have free bytes yet run out of inodes due to massive numbers of small files. Monitor both `df -h` and `df -i`.

### 8.3. Filesystem reserved blocks

Some filesystems reserve blocks for privileged processes, so space available to non-root processes differs from total free blocks. Alert on the available space the PostgreSQL OS user can actually consume.

### 8.4. Cloud-managed storage

On managed PostgreSQL, use provider metrics for allocated storage, used storage, free storage, autoscaling/quotas, and storage latency. Many managed services forbid OS shell access; do not assume `pg_ls_waldir` or `df` is available.

### 8.5. Never treat database size divided by volume size as disk utilization

For example, a 500 GB database on a 1 TB volume shares that volume with WAL, logs, temp files, and other databases. `database_size / volume_size` is not real disk usage. Read filesystem or provider storage metrics directly.

## 9. WAL and pg_wal Capacity

WAL can consume large amounts of disk whenever archiving breaks, standbys lag, or replication slots pin segments.

### 9.1. Inspecting WAL directory usage

On PostgreSQL versions with `pg_ls_waldir` and an authorized role:

~~~sql
SELECT
    count(*) AS file_count,
    sum(size) AS total_bytes,
    pg_size_pretty(sum(size)::bigint) AS total_size
FROM pg_ls_waldir();
~~~

Function availability and privileges vary by version. Do not grant `pg_read_server_files` or superuser to dashboards needlessly; prefer host exporters or monitoring integrations where suitable.

### 9.2. WAL statistics

On versions providing `pg_stat_wal`:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

`wal_bytes` is a cumulative counter. Compute deltas between two snapshots divided by elapsed seconds to get the WAL generation rate. This view exists from PostgreSQL 14 onward; verify your version before querying it.

### 9.3. WAL archiving

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

Archive failures cause WAL backlogs to grow. Repeatedly failing `archive_command` runs prevent `pg_wal` segments from being recycled.

### 9.4. Replication slots retaining WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL
        THEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    END AS wal_distance_bytes
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

`wal_distance_bytes` is an LSN-based estimate, not exclusive disk bytes held by that slot alone. Multiple slots can pin overlapping WAL ranges.

### 9.5. Inactive slots

An inactive slot continues pinning WAL. Never drop a slot solely to reclaim disk before confirming the consumer owner and resync plan.

### 9.6. max_slot_wal_keep_size

This setting caps how much WAL slots can retain on supported versions. Once exceeded, PostgreSQL invalidates the slot and the consumer must resynchronize. Balance disk protection against recovery requirements.

### 9.7. Never delete WAL files manually

Never delete or rename files inside `pg_wal` to free disk space. Resolve the archive or slot blocker and rely on PostgreSQL's built-in WAL lifecycle.

## 10. Temporary Files and Temporary Usage

Sort and hash operations can spill to temporary files when memory is insufficient or datasets are huge.

### 10.1. Database-level statistics

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset,
    pg_size_pretty(temp_bytes) AS temp_written_since_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

`temp_bytes` measures cumulative bytes written to temporary files since the last stats reset—not the bytes currently occupying disk right now.

### 10.2. Computing temporary write rate

Take two snapshots of `temp_bytes`, compute the delta, and divide by elapsed seconds. If `stats_reset` changed between samples, do not compute a rate across the reset.

### 10.3. Logging temporary files

Enable `log_temp_files` to log temporary files exceeding a byte/KB threshold. Pick a sensible threshold to avoid flooding logs.

### 10.4. Query-level insight

`pg_stat_statements` reports `temp_blks_read` and `temp_blks_written` per query entry on supported versions. Use it to pinpoint which queries generate heavy temporary I/O.

### 10.5. Temp usage is not solely a work_mem issue

Sort/hash spills, materializations, temporary tables, and other operations create temporary files. Investigate query plans and workloads rather than only raising `work_mem`.

## 11. Storage Growth Rate

A single point-in-time size reading reveals only current usage. Capacity planning requires storing snapshots over time.

### 11.1. Growth rate formulas

Given earlier size $S_1$ and later size $S_2$ separated by $\Delta t$ seconds:

\[
\text{growth bytes/sec} = \frac{S_2-S_1}{\Delta t}
\]

Convert to bytes/day:

\[
\text{growth bytes/day} = \text{growth bytes/sec} \times 86400
\]

Convert to GiB/day:

\[
\text{GiB/day} = \frac{\text{growth bytes/day}}{1024^3}
\]

### 11.2. Growth can be negative

`DROP`, `TRUNCATE`, `VACUUM FULL`, or table rewrites reduce size. Keep negative deltas in history to understand fluctuations; when forecasting, apply appropriate rolling averages or percentiles rather than assuming every interval grows positively.

### 11.3. How often should you sample?

- Steady systems: every 15–60 minutes or daily depending on needs.
- Rapidly growing systems: every 5–15 minutes.
- Capacity incidents: higher frequency temporarily.
- Filesystem metrics: can generally be scraped much more frequently than full relation inventories.

Balance sampling frequency against the overhead of size functions and total relation counts.

### 11.4. Snapshots are not cluster-wide transactionally consistent

A query calling size functions across many databases or relations may not capture an exact single instant if files change during execution. For capacity planning this is normal; forensic accounting requires different methods.

## 12. Storing Size Snapshots

Send snapshots to an external monitoring system or time-series store outside the monitored database whenever possible. If storing inside the same cluster, account for overhead and avoid letting metrics tables skew measurements.

Illustrative schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE monitoring.database_size_samples (
    sampled_at timestamptz NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, database_name)
);
~~~

Capture a sample:

~~~sql
INSERT INTO monitoring.database_size_samples (
    sampled_at,
    database_name,
    size_bytes
)
SELECT
    clock_timestamp(),
    datname,
    pg_database_size(oid)
FROM pg_database
WHERE datallowconn;
~~~

### 12.1. Store filesystem snapshots separately

Database size and filesystem free bytes are distinct metrics. Store filesystem metrics from host or provider exporters tagged with mount point, volume ID, and host.

### 12.2. Relation snapshots

You can track table and index sizes by database, schema, relation, and partition. Use stable qualified names and lifecycle metadata; OIDs change across dump/restore or object recreation.

### 12.3. Retention

Do not keep raw high-frequency snapshots forever. Retain raw samples long enough for incident investigations, then roll up into hourly or daily aggregates per policy.

### 12.4. Stats resets

For cumulative counters such as `temp_bytes`, `wal_bytes`, or tuple activity, record `stats_reset` alongside each sample. When `stats_reset` changes, start a new counter baseline.

## 13. Calculating Growth Rate from Snapshots

~~~sql
WITH ordered AS (
    SELECT
        database_name,
        sampled_at,
        size_bytes,
        lag(sampled_at) OVER (
            PARTITION BY database_name
            ORDER BY sampled_at
        ) AS previous_time,
        lag(size_bytes) OVER (
            PARTITION BY database_name
            ORDER BY sampled_at
        ) AS previous_bytes
    FROM monitoring.database_size_samples
),
rates AS (
    SELECT
        database_name,
        sampled_at,
        size_bytes,
        size_bytes - previous_bytes AS delta_bytes,
        extract(epoch FROM sampled_at - previous_time) AS elapsed_seconds
    FROM ordered
    WHERE previous_time IS NOT NULL
)
SELECT
    database_name,
    sampled_at,
    delta_bytes,
    round((delta_bytes / NULLIF(elapsed_seconds, 0))::numeric, 2)
        AS bytes_per_second,
    round((
        delta_bytes * 86400.0
        / NULLIF(elapsed_seconds, 0)
        / 1024 / 1024 / 1024
    )::numeric, 3) AS gib_per_day
FROM rates
ORDER BY sampled_at DESC, database_name;
~~~

### 13.1. Validate elapsed intervals

If samples are spaced irregularly or nearly identical in timestamp, computed rates can mislead. Use `NULLIF` to guard against division by zero and filter out bad samples.

### 13.2. Smoothing

A single spike may stem from a bulk load or maintenance rewrite. Use rolling averages, medians, or percentiles over a sufficiently wide window for forecasting.

### 13.3. Distinguish net growth from write churn

A database can absorb heavy inserts and deletes while its net size barely shifts. Net growth rate measures net storage change; WAL generation and temp writes measure churn. Monitor both to forecast both disk capacity and I/O.

## 14. Forecasting Time to Capacity Thresholds

Suppose:
- Current free bytes is $F$.
- Positive average growth rate is $G$ bytes/day.
- Simple forecast:

\[
\text{days to full} = \frac{F}{G}
\]

For example, if a volume has 200 GiB free and grows at 10 GiB/day, it reaches 0 free bytes in roughly 20 days. In production, never wait for zero; set capacity thresholds with reserve headroom.

### 14.1. Forecasting time to operational reserve

To maintain a safety reserve $R$:

\[
\text{days to reserve} = \frac{F-R}{G}
\]

Apply only when $G$ is positive and $F > R$.

### 14.2. Growth rates are not constant

Growth shifts with peak hours, seasonality, batch jobs, bulk imports, index builds, retention/cleanup jobs, WAL archive failures, and replication consumer outages.

Model peak/percentile growth and stress scenarios, not just long-term averages.

### 14.3. Forecast across multiple layers

Forecast separately for:
- Database and relation growth.
- WAL peak generation and retention.
- Temporary file peaks.
- Index build and rewrite overhead.
- Logs.
- Backup staging.
- Filesystem reserve headroom.

### 14.4. Cloud storage autoscaling

When storage auto-grows, monitor allocated capacity, maximum quota ceiling, expansion events, billing, and provisioning lead time. Autoscaling does not remove quota ceilings or I/O throttling limits.

## 15. Free Space Inside PostgreSQL

Keep these concepts distinct:

| Concept | Meaning | Returns Bytes to Filesystem Immediately? |
| --- | --- | --- |
| In-page free space | Unused space inside a data page | No |
| Dead tuples | Obsolete row versions no longer needed by snapshots | Not yet |
| Reusable space after VACUUM | Available for future inserts/updates | Usually no |
| Bloat | Excess/underutilized space relative to live data | Not automatically |
| Filesystem free space | Unallocated bytes remaining on the volume | Actual OS capacity |
| Space freed by DROP/TRUNCATE | Relation files removed or truncated | Usually yes |

### 15.1. Dead tuples

`UPDATE` and `DELETE` create dead tuple versions. `VACUUM` marks them reusable once no active snapshot needs them. Reclaiming dead tuples does not mean the table file immediately shrinks on disk.

### 15.2. Free Space Map

The FSM tracks estimated reusable space inside relation pages so PostgreSQL knows where new tuples fit. The FSM is not a map of filesystem free bytes.

### 15.3. Visibility Map

The Visibility Map tracks which pages are all-visible or all-frozen for vacuum and index-only scans. It is also internal metadata, not filesystem capacity.

### 15.4. Fillfactor

A lower `fillfactor` reserves empty space inside heap/index pages to encourage HOT updates or reduce page splits in certain workloads. That reserved room is a deliberate performance-vs-storage trade-off and should not automatically be labeled bloat.

## 16. Monitoring Dead Tuples and Vacuum

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 16.1. These are estimates

`n_live_tup` and `n_dead_tup` are statistical estimates. They are useful for prioritizing tables to inspect, not exact byte-level bloat measurements.

### 16.2. Autovacuum

Autovacuum cleans dead tuples and updates visibility and frozen metadata. If autovacuum falls behind write rates, dead tuples and bloat accumulate.

### 16.3. Long transactions

Long-running transactions and old snapshots prevent vacuum from removing obsolete tuples. Check `pg_stat_activity`, `backend_xmin`, and replication slots to find pinned horizons.

### 16.4. Regular VACUUM rarely shrinks files

Standard `VACUUM` mainly turns dead space into reusable internal space. Only under specific conditions can it truncate trailing empty pages at the end of a file. Never expect filesystem free space to grow by the full byte size of dead tuples after running `VACUUM`.

### 16.5. Analyze

`ANALYZE` updates planner statistics; it does not reclaim storage.

## 17. Measuring Bloat and In-Relation Free Space

Extensions such as `pgstattuple` and `pg_freespacemap` offer deeper visibility, though they require installation, privileges, and overhead assessment.

### 17.1. pgstattuple

`pgstattuple` reports live tuple count/bytes, dead tuple count/bytes, and free space bytes/percentage.

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('app.orders');
~~~

### 17.2. pgstattuple_approx

For large relations, `pgstattuple_approx` estimates faster by leveraging the visibility map and sampling. Results are approximate; consult extension/version documentation.

~~~sql
SELECT *
FROM pgstattuple_approx('app.orders');
~~~

### 17.3. Overhead

`pgstattuple` scans many pages and can generate heavy I/O. Never run it across all large tables simultaneously during peak traffic without evaluating impact.

### 17.4. pg_freespacemap

`pg_freespacemap` exposes per-page Free Space Map entries:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;

SELECT *
FROM pg_freespace('app.orders'::regclass)
LIMIT 20;
~~~

Results represent per-page FSM free space inside the relation, not total free bytes on the filesystem.

### 17.5. Do not confuse free_percent with free disk

`pgstattuple`'s `free_percent` describes free space inside relation pages. The filesystem still sees zero reclaimed bytes until the relation file shrinks.

## 18. VACUUM, VACUUM FULL, and Reclaiming Disk Space

### 18.1. VACUUM

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

Standard `VACUUM` cleans reclaimable dead tuples and makes space reusable internally. It does not take an exclusive table lock and does not rewrite the entire relation.

### 18.2. VACUUM FULL

~~~sql
VACUUM (FULL, ANALYZE) app.orders;
~~~

`VACUUM FULL` rewrites the table into a compact new file and returns freed space to the filesystem. It requires an `ACCESS EXCLUSIVE` lock and temporary extra disk space for the rewritten copy. Never run it on large production tables without a maintenance window and verified disk headroom.

### 18.3. TRUNCATE

`TRUNCATE` removes all rows and normally returns table storage immediately to the filesystem, though it requires strong locks and carries specific transaction and foreign-key semantics. Verify `CASCADE` and application impact.

### 18.4. DROP

`DROP TABLE` or `DROP DATABASE` removes objects and their underlying files. These are destructive operations requiring backups, approvals, and dependency checks.

### 18.5. CLUSTER

`CLUSTER` rewrites a table ordered by an index, which can improve data locality while requiring extra disk space and strong locks during execution. It is not a routine capacity-cleanup tool.

### 18.6. REINDEX

`REINDEX` rebuilds indexes, reclaiming index bloat while needing temporary storage headroom; `REINDEX CONCURRENTLY` offers different lock and duration trade-offs.

## 19. WAL Retention and Abnormal Disk Growth

A database's own tables may barely grow while `pg_wal` expands rapidly.

### 19.1. Failing archive_command

If `archive_command` fails, PostgreSQL retains WAL segments and retries. Inspect `pg_stat_archiver`, server logs, archive destination capacity, and permissions.

### 19.2. Standby lag

A standby unable to receive or replay in time can pin WAL through a replication slot or cause backlogs. Monitor `state`, sent/write/flush/replay LSNs, and slot `restart_lsn`.

### 19.3. Inactive logical slots

A stopped CDC connector or subscriber can retain WAL and catalog history. Identify the consumer owner before acting on the slot.

### 19.4. Long-running transactions

Long transactions and snapshots pin tuple versions and hinder vacuum. Check `pg_stat_activity` and `xmin` horizons.

### 19.5. Do not confuse WAL generated with WAL retained

Rising `wal_bytes` shows how much WAL was generated during a window. `pg_wal` directory size shows files currently retained on disk. They are related, not identical.

## 20. Temporary Files and Disk Pressure

Temporary files can fill a filesystem even while relation sizes remain flat.

### 20.1. Common sources

- Sort spills.
- Hash aggregate and hash join spills.
- Materializations.
- Temporary tables.
- Index builds.
- Certain maintenance operations.
- High query concurrency.

### 20.2. Tracking temp_bytes

Use `pg_stat_database.temp_bytes` across snapshots to compute the temporary write rate. Pair with `log_temp_files` and query-level stats to locate offending queries.

### 20.3. Temp tablespaces

Temporary files land in the database's default tablespace or configured `temp_tablespaces`. Check actual storage locations.

### 20.4. work_mem is not a server-wide memory cap

`work_mem` can be allocated by multiple sort/hash nodes per query across many concurrent sessions. Increasing `work_mem` to eliminate temp spills can sharply elevate total memory consumption.

## 21. Capacity by Database and Schema

PostgreSQL has no single built-in function returning total schema size. Sum relation sizes per schema:

~~~sql
SELECT
    n.nspname AS schema_name,
    sum(pg_total_relation_size(c.oid)) AS bytes,
    pg_size_pretty(sum(pg_total_relation_size(c.oid))::bigint) AS size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname
ORDER BY bytes DESC;
~~~

### 21.1. Scope of the schema query

This query sums physical sizes of regular tables and materialized views in each schema, including indexes and TOAST via `pg_total_relation_size`. For partitioned tables, verify child partitions are counted without double-counting parent/child mappings in custom queries.

### 21.2. Does not match pg_database_size exactly

Database size also includes system catalogs, sequences, ungrouped objects, and temporary/database-wide files excluded by schema filters. Schema aggregates provide a breakdown, not a replacement total.

### 21.3. Schemas with thousands of small objects

Huge relation counts add catalog and filesystem metadata overhead. Track both object count and total bytes.

## 22. Capacity by Partition

For partitioned tables, report size per partition to spot fast-growing or skewed partitions.

~~~sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS partition_schema,
    child.relname AS partition_name,
    pg_total_relation_size(child.oid) AS bytes,
    pg_size_pretty(pg_total_relation_size(child.oid)) AS size
FROM pg_inherits AS inh
JOIN pg_class AS parent
  ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
  ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
  ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
  ON child_ns.oid = child.relnamespace
ORDER BY bytes DESC;
~~~

This lists direct parent-child links. Multi-level partitioning requires recursive traversal to gather all leaf descendants.

### 22.1. Partition skew

Certain partitions can grow abnormally due to key distribution skew, retention gaps, or routing bugs. Monitor min/max partition bounds alongside sizes.

### 22.2. Retention

Dropping or detaching old partitions reclaims storage far faster than row-by-row `DELETE`, provided you verify retention policies, foreign keys, replication publications, and application queries first.

### 22.3. Future partitions

Pre-create future partitions ahead of schedule and alert if upcoming partitions are missing. A `DEFAULT` partition can balloon unexpectedly if routing misses occur.

## 23. Capacity Planning for Index Builds and Maintenance

Never forecast only steady-state database size. Maintenance tasks demand peak temporary headroom.

### 23.1. Index builds

`CREATE INDEX` writes a brand-new index alongside existing tables/indexes. `REINDEX` may need room for the new index copy; concurrent mode carries distinct duration and space characteristics.

### 23.2. VACUUM FULL / CLUSTER

Table rewrites require enough free disk for the new relation copy while the old file still exists. Insufficient space causes failures or impacts active workloads.

### 23.3. pg_repack

When using online rewrite extensions/tools, budget disk for shadow tables/indexes and the lifetime of old relations. Review prerequisites and lock behavior carefully.

### 23.4. Bulk loads

Large imports drive table, index, and WAL growth. Account for temporary files, WAL archiving, and replication backlogs too.

### 23.5. Safety margins

Maintain headroom scaled to peak workloads and the time needed to expand volumes or migrate data. Never rely on one generic percentage threshold across every deployment.

## 24. Tracking Growth per Relation

Store snapshots by schema and table:

~~~sql
CREATE TABLE monitoring.relation_size_samples (
    sampled_at timestamptz NOT NULL,
    schema_name name NOT NULL,
    relation_name name NOT NULL,
    total_bytes bigint NOT NULL,
    table_bytes bigint NOT NULL,
    index_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, schema_name, relation_name)
);
~~~

Capture samples:

~~~sql
INSERT INTO monitoring.relation_size_samples (
    sampled_at,
    schema_name,
    relation_name,
    total_bytes,
    table_bytes,
    index_bytes
)
SELECT
    clock_timestamp(),
    n.nspname,
    c.relname,
    pg_total_relation_size(c.oid),
    pg_table_size(c.oid),
    pg_indexes_size(c.oid)
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
~~~

### 24.1. Relation renames, drops, and recreations

Relation names can change or be reused. For long histories, include database identity, relation OID, `relfilenode`, or lifecycle metadata; never treat schema/name as permanently immutable.

### 24.2. Partition samples

Store partitions individually mapped to their parent. When partitions are detached or dropped, log the event to explain step-downs in size.

### 24.3. Do not poll relation sizes too frequently

On clusters with hundreds of thousands of relations, calling size functions across all of them takes noticeable time. Run full relation inventories on slower schedules and use OS/provider metrics for high-frequency capacity tracking.

## 25. Forecasting and Alerting

A strong capacity dashboard warns well before disk runs out.

### 25.1. Absolute thresholds

Examples:
- Warning when free bytes drop below the defined safety reserve.
- Critical when free bytes approach the minimum required for WAL, checkpoints, and maintenance.
- Dedicated alerts per tablespace volume.

### 25.2. Percentage thresholds

Pair used/free percentages with absolute bytes. 95% full is dangerous in general, yet 5% of a 10 TB volume differs vastly from 5% of a 20 GB volume.

### 25.3. Growth rate thresholds

Alert when bytes/day or WAL bytes/sec jumps sharply compared to baseline.

### 25.4. Time-to-full

Forecast days until the reserve threshold using rolling growth rates. Alert whenever time-to-full falls below the lead time required to provision storage or clean up data.

### 25.5. WAL-specific alerts

- `pg_wal` directory growing rapidly.
- Rising archive `failed_count`.
- Inactive logical or physical slots retaining WAL.
- Rising standby lag.
- Low free space on the WAL volume.

### 25.6. Temporary-file alerts

Alert on sharp spikes in `temp_bytes` rate, rapid `temp_files` counts, or filling temp volumes. Pair with query logs to pinpoint temp-heavy queries.

### 25.7. Alert quality

Alerts should specify database/volume/tablespace, current bytes, free bytes, growth rate, threshold, and trend. Group by failure domain instead of firing hundreds of duplicate alerts for one volume.

## 26. Runbook: Volume Nearly Full

1. Identify which exact mount or volume is nearing capacity.
2. Check `PGDATA`, `pg_wal`, tablespaces, logs, temp directories, and backup staging.
3. Measure growth rate and time until threshold.
4. Check archive failures and replication slots.
5. Check temporary files and long-running queries.
6. Check for abnormally growing tables or indexes.
7. Pause or throttle the growth-driving workload if necessary.
8. Expand the volume or relocate data per capacity plan.
9. Never manually delete internal PostgreSQL files.
10. Verify free space, WAL/archiving health, and application writes afterward.

## 27. Runbook: Abnormal Database Size Growth

1. Compare recent database size snapshots against baseline.
2. Rank tables and indexes by current size and size delta.
3. Identify rapidly growing tables or partitions.
4. Check `n_live_tup`, `n_dead_tup`, and autovacuum timestamps.
5. Check insert/update/delete workloads and retention cleanup jobs.
6. Check index growth and look for duplicate/unneeded indexes.
7. Check TOAST and oversized column growth.
8. Check long-running transactions and `xmin` horizons.
9. Run `pgstattuple` on representative relations if appropriate and I/O allows.
10. Choose remediation: fix workload, tune vacuum, apply retention/partitioning, or plan a maintenance rewrite.

## 28. Runbook: Abnormal pg_wal Growth

1. Measure `pg_wal` directory size and filesystem free bytes.
2. Inspect `pg_stat_archiver` and PostgreSQL logs.
3. Inspect active and inactive replication slots.
4. Calculate WAL byte distance from current LSN to each `restart_lsn`.
5. Check physical standby lag and logical subscriber health.
6. Measure WAL generation rate.
7. Fix archive destination, permissions, or network issues.
8. Restore stalled consumers or plan resyncs if slots invalidated.
9. Drop orphaned slots only after owner and impact confirmation.
10. Verify `pg_wal` shrinks through the normal checkpoint/recycle lifecycle.

## 29. Runbook: Controlled Bloat Remediation

1. Identify relations occupying excessive bytes with abnormal growth.
2. Check dead tuple estimates and autovacuum history.
3. Check long-running transactions and replication horizons.
4. Run `pgstattuple`/`pgstattuple_approx` on sample relations if safe.
5. Determine whether standard `VACUUM` suffices or a rewrite is required.
6. Budget extra disk space for `VACUUM FULL`, `REINDEX`, `CLUSTER`, or online rewrite tools.
7. Evaluate lock impact and application downtime.
8. Execute during a maintenance window or via a vetted online approach.
9. Compare relation size and filesystem free space before and after.
10. Monitor query planner behavior, latency, and autovacuum afterward.

## 30. Limitations on Managed PostgreSQL

Managed services may restrict direct OS filesystem or `pg_wal` access. Rely on provider metrics for allocated/used/free storage, storage autoscaling and quotas, IOPS/throughput/latency, exposed temporary storage, WAL/replication lag metrics, backup storage/retention, and tablespace constraints.

### 30.1. Provider storage metrics

Verify whether a metric reports allocated bytes, used bytes, or available bytes. Definitions vary across cloud providers; read documentation carefully before comparing.

### 30.2. Autoscaling

Verify maximum storage limits, growth increments, cooldown windows, billing impact, and scaling duration. Alert well ahead of hitting hard quota ceilings.

### 30.3. Do not assume superuser privileges

Some size or filesystem functions may be restricted. Build dashboards from supported provider metrics and permitted SQL views.

### 30.4. Separate backup quotas

Backup retention often uses separate storage and quotas from the database volume. Monitor backup repositories and export artifacts independently.

## 31. Common Mistakes

| Mistake | Consequence | Better Practice |
| --- | --- | --- |
| Watching only `pg_database_size` | Misses WAL, logs, temp, and other files | Pair with volume metrics |
| Summing database size and tablespace size | Double-counts storage | Read each perspective separately |
| Treating `pg_relation_size` as total table size | Omits TOAST and indexes | Use `pg_total_relation_size` |
| Treating `n_live_tup` as an exact row count | Inaccurate sizing/validation | Use `COUNT` when exactness is required |
| Treating `n_dead_tup` as bloat bytes | Misjudges disk impact | Use `pgstattuple` or proper bloat analysis |
| Expecting regular `VACUUM` to return disk to OS | Wrong free-space forecasts | Distinguish reusable space from file shrinking |
| Running `VACUUM FULL` on a nearly full volume | Rewrite needs extra disk and fails | Calculate peak space first |
| Deleting files inside `pg_wal` manually | Corruption or recovery failure | Fix archiving/slots and follow PostgreSQL procedures |
| Dropping inactive slots immediately | Consumer loses ability to resume | Confirm owner and resync plan first |
| Alerting on percentages alone | Ignores absolute bytes and growth rate | Combine percentage, bytes, and time-to-full |
| Forecasting from one sample | Unstable projections | Use rolling windows and peak scenarios |
| Ignoring separate tablespace volumes | Dedicated mount fills before `PGDATA` | Monitor every mount point |
| Ignoring inodes | Cannot create files despite free bytes | Monitor `df -i` |
| Treating `temp_bytes` as current temp disk usage | Misreads current consumption | Use filesystem metrics and rate deltas properly |
| Treating `wal_bytes` as `pg_wal` size | Confuses generation with retention | Measure WAL files separately |
| Forgetting index rebuild overhead | Disk exhaustion during maintenance | Budget peak storage |
| Scanning all tables with `pgstattuple` frequently | Heavy I/O overhead | Run selectively |
| Failing to store historical snapshots | No growth trend visibility | Collect time-series history |

## 32. PostgreSQL Practice Exercises

Run exercises in a lab, staging, or authorized monitoring environment. Avoid running heavy size scans, `VACUUM FULL`, or `REINDEX` in production without a capacity and maintenance plan.

1. **Database size:** list database sizes with `pg_database_size`.
2. **Pretty size:** format byte counts with `pg_size_pretty`.
3. **Current database:** measure the size of `current_database()`.
4. **Largest database:** rank databases by byte size.
5. **Relation size:** measure `pg_relation_size` of a table.
6. **Table size:** measure `pg_table_size` and explain the difference.
7. **Index size:** measure `pg_indexes_size`.
8. **Total relation:** measure `pg_total_relation_size`.
9. **Breakdown:** compare heap, table, index, and total bytes.
10. **Largest tables:** list the 30 largest tables.
11. **Schema size:** aggregate relation sizes by schema.
12. **Index inventory:** list the largest indexes.
13. **Index usage:** join `pg_stat_user_indexes` with index sizes.
14. **Constraint indexes:** identify indexes enforcing primary or unique constraints.
15. **TOAST:** locate tables with large TOAST storage.
16. **Partition parent:** measure the size of a partitioned parent.
17. **Partition children:** list sizes per child partition.
18. **Partition skew:** identify the largest partition.
19. **Tablespaces:** list tablespace locations and sizes.
20. **Volume mapping:** map tablespace paths to OS mount points.
21. **Filesystems:** run `df -h` on the lab host.
22. **Inodes:** run `df -i` and explain inode exhaustion.
23. **Database vs. volume:** compare `pg_database_size` against filesystem usage.
24. **WAL directory:** inspect `pg_ls_waldir` if supported by version and permissions.
25. **WAL statistics:** query `pg_stat_wal` and `wal_bytes`.
26. **WAL rate:** take two snapshots and compute WAL bytes/sec.
27. **Archiving:** query `pg_stat_archiver`.
28. **Archive failure:** simulate an archive failure in the lab and observe WAL retention.
29. **Replication slots:** list physical and logical slots.
30. **Inactive slots:** stop a consumer and observe an inactive slot.
31. **WAL distance:** compute `pg_wal_lsn_diff` to `restart_lsn`.
32. **Slot recovery:** restore the consumer and watch WAL recycling.
33. **Temporary files:** read `temp_files` and `temp_bytes` from `pg_stat_database`.
34. **Temp rate:** compute per-minute `temp_bytes` deltas.
35. **Temp logging:** configure `log_temp_files` in the lab.
36. **Query temp usage:** use `pg_stat_statements` to locate temp-block writers.
37. **Dead tuples:** inspect `n_dead_tup` and `n_live_tup`.
38. **Autovacuum:** inspect `last_autovacuum` and `autovacuum_count`.
39. **Old transactions:** link `pg_stat_activity` to vacuum horizons.
40. **VACUUM:** run standard `VACUUM` and compare relation size before and after.
41. **Reusable space:** explain why `VACUUM` does not necessarily shrink files.
42. **pgstattuple:** install the extension and measure a lab table.
43. **Approximate tuples:** compare `pgstattuple` and `pgstattuple_approx`.
44. **Free Space Map:** install `pg_freespacemap` and query `pg_freespace`.
45. **FSM meaning:** explain how page free space differs from filesystem free space.
46. **VACUUM FULL:** run on a small lab table and measure extra disk and locks.
47. **TRUNCATE:** truncate a lab table and observe file size.
48. **DROP:** drop a lab object and observe filesystem usage.
49. **REINDEX:** rebuild a lab index and measure peak storage.
50. **CLUSTER:** test rewriting a lab table and observe disk impact.
51. **Growth snapshots:** create `monitoring.database_size_samples`.
52. **Sample job:** schedule storing database size snapshots.
53. **Growth delta:** compute byte growth between two samples.
54. **GiB/day:** convert growth rate to GiB/day.
55. **Negative delta:** create/drop objects and observe negative size deltas.
56. **Rolling average:** compute a moving average growth rate.
57. **Forecast:** compute days-to-reserve from free bytes and growth rate.
58. **Peak scenario:** substitute peak/percentile growth for long-term average.
59. **Relation snapshots:** create `monitoring.relation_size_samples`.
60. **Largest growth:** find tables with the largest byte deltas.
61. **Partition history:** record size history per partition.
62. **Schema inventory:** compare schema sizes day over day.
63. **Capacity thresholds:** create an alert on free bytes.
64. **Percentage alerts:** create an alert on volume percentage used.
65. **Time-to-full:** create an alert when forecast falls below provisioning lead time.
66. **WAL alerts:** alert when `pg_wal` exceeds threshold.
67. **Temp alerts:** alert on sudden spikes in temp writes.
68. **Tablespace alerts:** alert when a dedicated tablespace volume nears capacity.
69. **Managed metrics:** verify provider used/free storage metric definitions.
70. **Autoscaling:** design alerts for storage quota ceilings.
71. **Maintenance capacity:** estimate peak space for `REINDEX` or `VACUUM FULL`.
72. **Bulk loads:** benchmark table growth, WAL, and temp usage during a bulk import.
73. **Retention:** design partition retention and measure reclaimed bytes.
74. **Bloat:** pick a high-dead-tuple table for investigation.
75. **Incident:** write a runbook for a nearly full volume.
76. **Incident:** write a runbook for abnormal `pg_wal` growth.
77. **Incident:** write a runbook for a database growth spike.
78. **Dashboard:** build a database/table/index/WAL/filesystem capacity dashboard.
79. **Forecast:** project the date of hitting reserve threshold from 30 days of data.
80. **Capstone design:** build a PostgreSQL capacity monitoring system covering snapshots, growth rates, partition/table/index breakdowns, WAL/temp/tablespace/filesystem metrics, forecasts, alert thresholds, maintenance headroom, and incident runbooks.

## 33. Capacity Monitoring Checklist

### Measuring storage

- [ ] Database sizes collected in raw bytes.
- [ ] Tables, indexes, and TOAST broken down separately.
- [ ] Partitioned tables summed without double-counting.
- [ ] Tablespace locations mapped to OS volumes.
- [ ] WAL directory and archiving monitored.
- [ ] Temporary file usage collected.
- [ ] Backup repository tracked with dedicated metrics.

### Growth

- [ ] Scheduled snapshots stored over time.
- [ ] Growth rates calculated using actual elapsed time.
- [ ] `stats_reset` recorded for cumulative counters.
- [ ] Rolling averages and peak growth both evaluated.
- [ ] Time-to-reserve forecasted continuously.
- [ ] Outlier growth on relations and partitions detected.

### Free space and maintenance

- [ ] Filesystem bytes and inodes monitored.
- [ ] In-page free space distinguished from filesystem free space.
- [ ] Dead tuples and autovacuum monitored.
- [ ] Replication slots and archive backlogs monitored.
- [ ] Extra disk headroom reserved for index builds and rewrites.
- [ ] Internal PostgreSQL files never deleted manually.

### Alerts and runbooks

- [ ] Warning/critical thresholds include both absolute bytes and percentages.
- [ ] Time-to-full alerts driven by growth trends.
- [ ] Every tablespace volume has dedicated alerts.
- [ ] WAL, temp, and archive alerts have clear owners.
- [ ] Runbooks identify growth sources and safe remediation steps.
- [ ] Managed storage quotas and autoscaling monitored.

## 34. Summary

PostgreSQL capacity monitoring requires combining measurements across databases, relations, tablespaces, WAL, temporary storage, and filesystems.

~~~text
DATABASE / RELATION
  pg_database_size
  pg_total_relation_size
  pg_table_size / pg_indexes_size
             |
             v
TABLESPACE / WAL / TEMP
  pg_tablespace_size
  pg_ls_waldir / pg_stat_wal
  pg_stat_database.temp_bytes
             |
             v
FILESYSTEM / CLOUD VOLUME
  used bytes / free bytes / inodes
             |
             v
TIME SERIES
  snapshots -> growth rate -> forecast
             |
             v
CAPACITY ALERTS + RUNBOOKS
~~~

Key principles:

- **Use size functions at the right level.** `pg_database_size` measures databases; `pg_total_relation_size` measures relations plus indexes and TOAST; `pg_tablespace_size` offers another storage grouping.
- **Never sum database sizes and tablespace sizes.** They can count the same relation files twice.
- **Measure filesystems directly.** `pg_database_size` excludes full WAL, logs, temp files, backups, and external files on the volume.
- **Store bytes and snapshots.** Growth rates must use byte deltas divided by elapsed time, never parsed `pg_size_pretty` strings.
- **Forecast to reserve thresholds.** Never wait for 100% volume usage; factor in peak growth, provisioning lead time, and maintenance headroom.
- **Distinguish in-page free space from volume free space.** Regular `VACUUM` makes space reusable internally without necessarily returning bytes to the filesystem.
- **Monitor WAL, slots, archiving, and temporary files.** They can drive rapid disk growth even when table sizes remain stable.
- **Budget extra space for maintenance.** `VACUUM FULL`, `REINDEX`, `CLUSTER`, and bulk loads require peak capacity well above steady state.
- **Monitor every tablespace mount.** A dedicated mount can fill up while `PGDATA` still has free space.
- **Use estimates properly.** `n_live_tup`/`n_dead_tup` and tuple bloat estimates help locate targets to investigate; they do not replace exact byte or filesystem metrics.

A strong capacity monitoring system does more than report “how many GB the database uses.” It tells operators where storage lives, what drives growth, how long remains before reaching safety reserves, and what safe actions keep writes, backups, vacuuming, and recovery healthy.
