# Scheduled Index, Statistics, and Capacity Maintenance in PostgreSQL

A PostgreSQL cluster may run smoothly on day one yet gradually slow down over time if indexes bloat, statistics no longer reflect the data, autovacuum falls behind, or storage grows faster than forecasted. These issues rarely appear as a single failure; they accumulate over weeks or months and eventually turn into slow queries, full disks, prolonged backups, or disrupted replication.

Good administration requires a targeted maintenance schedule with before/after measurements and safety limits. Scheduling does not mean running every command on a fixed day regardless of workload. You must combine PostgreSQL's automatic mechanisms such as autovacuum/autoanalyze with proactive tasks such as index inspections, statistics refreshes, capacity assessments, backup verification, and data cleanup under retention policies.

This lesson covers how to schedule maintenance for indexes, statistics, and capacity; how to choose tools, write observability queries, organize maintenance windows, manage lock/I/O/WAL risks, and design repeatable operational runbooks.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between index maintenance, VACUUM, ANALYZE, and capacity management.
2. Monitor table/index sizes and detect signs of abnormal index growth.
3. Evaluate index usage without dropping an index based on a single counter.
4. Choose between REINDEX, REINDEX CONCURRENTLY, pg_repack, and alternative approaches.
5. Maintain planner statistics with autoanalyze and targeted ANALYZE.
6. Design a schedule for checking table/index statistics, dead tuples, and transaction age.
7. Measure database, relation, tablespace, WAL, temp file, and backup capacity.
8. Track growth rates, estimate when thresholds will be reached, and prepare capacity.
9. Organize maintenance windows with lock timeouts, statement timeouts, and rollback plans.
10. Schedule jobs using an OS scheduler or pg_cron according to permissions and version.
11. Log runs, prevent overlapping jobs, and handle errors safely with retries.
12. Build dashboards, alerts, runbooks, and review cycles suitable for production.

## 2. Why Schedule Maintenance?

### 2.1. Maintenance Is an Operational Cycle

A practical cycle includes:

1. **Observe:** collect sizes, statistics, query latency, index usage, dead tuples, and storage headroom.
2. **Diagnose:** identify root causes with data; distinguish bloat, stale stats, query regressions, and capacity shortfalls.
3. **Plan:** select the action, timing, resources, lock impact, and owner.
4. **Execute:** run within defined limits while monitoring progress and workload.
5. **Verify:** check results, data, query plans, disk, replication, and backups.
6. **Learn:** update baselines, schedules, and runbooks.

### 2.2. Not Every Task Needs to Run Daily

Autovacuum/autoanalyze normally run continuously based on thresholds. Capacity checks can run daily. Index health reviews can be weekly or monthly depending on workload. REINDEX should only run when justified. Running VACUUM FULL or database-wide REINDEX on a rigid schedule can cause unnecessary locks, I/O spikes, and WAL bursts.

### 2.3. Separating Automatic Maintenance from Decision-Driven Maintenance

| Category | Examples | How It Operates |
| --- | --- | --- |
| Continuous automatic | autovacuum, autoanalyze, monitoring | PostgreSQL triggers automatically based on activity/config |
| Periodic inspection | capacity snapshot, index usage, table stats | Scheduled query/collector |
| Conditional maintenance | ANALYZE table, REINDEX a single index | Run when metrics show a need |
| Change-window maintenance | VACUUM FULL, pg_repack, bulk rewrite | Plan, approval, resource/rollback controls |
| Recovery | restore backup, PITR | Incident/DR runbook, not routine cleanup |

### 2.4. Schedules Must Be Workload-Driven

Append-only tables, heavily updated tables, partitioned tables, lookup tables, and archive tables have different characteristics. Choose frequencies based on write rate, query sensitivity, size, business criticality, and tolerance for locks or downtime.

## 3. Index Maintenance: Concepts and Signals

### 3.1. What Do Indexes Help With?

Indexes help the planner locate rows without scanning the entire table for certain query patterns. Indexes also carry costs: disk space, WAL, write amplification, vacuum work, and cache pressure. Every index needs workload justification.

### 3.2. Index Growth

Indexes can grow from inserts, updates, deletes, page splits, churn, and key distribution. For B-trees, page utilization and fragmentation can affect storage and cache efficiency. Large size alone does not prove an index is bloated; a large index may simply reflect genuinely large data.

### 3.3. What Is Bloat?

Bloat is allocated space that is not used efficiently due to tuple churn, page splits, free space, or modification history. Bloat cannot be accurately determined merely by comparing `pg_relation_size()` with row counts.

### 3.4. Index Usage

`pg_stat_user_indexes` provides counters such as `idx_scan`, `idx_tup_read`, and `idx_tup_fetch`. These are cumulative figures since statistics were last reset, not permanent usage measures. After a restart or stats reset, counters may be low again.

### 3.5. Do Not Drop an Index Just Because idx_scan Is Zero

An index may serve rare queries, constraint enforcement, primary key/unique constraints, foreign key workloads, or seasonal reports. Before considering a drop:

- Observe across a full business cycle;
- Verify whether the index backs a constraint;
- Inspect query plans and query logs;
- Account for seasonal workloads;
- Determine whether the index can be chosen by the planner;
- Assess recreation cost and risk.

### 3.6. Invalid Indexes

A failed or canceled concurrent index build can leave behind an invalid index. An invalid index is not used by the planner as a valid index, yet it still consumes storage and may still incur overhead depending on its state. Include invalid index detection in scheduled inventories.

### 3.7. Index Health Is More Than Size

Evaluate together:

- Size and growth rate;
- Scan/read/fetch counters;
- Constraint dependencies;
- Query plans and latency;
- B-tree page statistics if a suitable extension is available;
- Corruption checks;
- Write amplification and WAL volume.

## 4. Table and Index Size Inventory

### 4.1. Relation Sizes

Commonly used functions:

| Function | Scope |
| --- | --- |
| `pg_relation_size(relation)` | Size of one fork of a relation, defaulting to the main fork |
| `pg_table_size(relation)` | Table storage, including TOAST and auxiliary forks, excluding indexes |
| `pg_indexes_size(relation)` | Total size of the table's indexes |
| `pg_total_relation_size(relation)` | Table + indexes + TOAST/auxiliary storage |
| `pg_database_size(database)` | Total database size |
| `pg_tablespace_size(tablespace)` | Size of relations in the tablespace |
| `pg_size_pretty(bytes)` | Formats byte counts into human-readable form |

### 4.2. Top Tables by Size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_table_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_total_relation_size(relid) AS total_bytes
FROM pg_catalog.pg_statio_user_tables
ORDER BY total_bytes DESC
LIMIT 30;
~~~

`pg_total_relation_size` includes indexes and TOAST. Use bytes for sorting and thresholds; `pg_size_pretty` is only for display.

### 4.3. Top Indexes by Size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_relation_size(indexrelid) AS index_bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC
LIMIT 50;
~~~

### 4.4. Table and Index Size on One Row

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    pg_relation_size(s.relid) AS heap_bytes,
    pg_indexes_size(s.relid) AS index_bytes,
    pg_total_relation_size(s.relid) AS total_bytes,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze
FROM pg_stat_user_tables AS s
ORDER BY total_bytes DESC
LIMIT 100;
~~~

### 4.5. Database Sizes

~~~sql
SELECT
    datname,
    pg_database_size(datname) AS bytes,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY bytes DESC;
~~~

### 4.6. Tablespace Sizes

~~~sql
SELECT
    spcname,
    pg_tablespace_size(oid) AS bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY bytes DESC;
~~~

### 4.7. Index Size by Schema

~~~sql
SELECT
    schemaname,
    sum(pg_relation_size(indexrelid)) AS index_bytes,
    pg_size_pretty(sum(pg_relation_size(indexrelid))) AS index_size,
    count(*) AS index_count
FROM pg_stat_user_indexes
GROUP BY schemaname
ORDER BY index_bytes DESC;
~~~

### 4.8. Logical Size Differs from Filesystem Capacity

Size functions report bytes allocated to PostgreSQL relations in a database or tablespace. They do not show free space on the filesystem, snapshot reserves, filesystem metadata, WAL on a separate volume, or object storage usage. Capacity dashboards must incorporate OS/cloud storage metrics.

### 4.9. Privileges and Scope

Size functions read relation/database metadata subject to permissions; some system-wide views require monitoring privileges. When querying inventory across multiple databases, connect to each database individually because `pg_stat_user_tables`/`pg_stat_user_indexes` are per-database views.

## 5. Gathering Index Health and Bloat Evidence

### 5.1. Index Usage Counters

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    last_idx_scan,
    pg_relation_size(indexrelid) AS index_bytes
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC;
~~~

`last_idx_scan` is only available in newer major versions. Omit this column if the server does not support it yet.

### 5.2. Unscanned Indexes

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size,
    i.indisprimary,
    i.indisunique,
    i.indisvalid
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(s.indexrelid) DESC;
~~~

This is a review list, not an automatic drop list. `idx_scan` can be zero because stats were recently reset, the workload has not run yet, or the index supports constraints or rare operations.

### 5.3. Invalid Indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

### 5.4. Bloat Estimates Are Not Exact Measurements

Bloat queries based on page fill assumptions, tuple widths, and catalog statistics are only estimates. They can be inaccurate with skewed data distributions, large TOAST values, custom fillfactors, or stale statistics. Use estimates to prioritize investigation, not as the sole trigger for destructive actions.

### 5.5. The pgstattuple Extension

The `pgstattuple` extension provides functions to read tuple/page statistics of a relation, including live/dead tuple length and free space. For B-trees, `pgstatindex()` inspects leaf density, fragmentation, and page counts. These checks can read many pages, so run them on an appropriate schedule and timing.

Example in a lab database:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('public.orders'::regclass);

SELECT *
FROM pgstatindex('public.orders_created_at_idx'::regclass);
~~~

Installing the extension requires appropriate privileges and the corresponding server package. Do not run full relation scans too frequently on very large tables during peak hours.

### 5.6. amcheck

The `amcheck` extension/module provides index structure checks such as B-tree invariants. `bt_index_check()` and `bt_index_parent_check()` have different costs and locking behavior; pick the right mode, consult version documentation, and run on a risk-based schedule.

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

Do not confuse integrity checks with bloat measurement. An index can be large yet valid; an index can be small yet corrupt.

### 5.7. When Is REINDEX Needed?

Consider REINDEX when:

- Bloat is confirmed and imposes significant cost;
- Index corruption is confirmed and requires rebuilding;
- Collation version changes require rebuilding ordering/indexes;
- An invalid index needs to be recreated;
- There is clear performance/space evidence and alternatives have been tried.

Do not REINDEX solely because an index exceeds a fixed size.

## 6. Choosing an Index Maintenance Approach

### 6.1. REINDEX

`REINDEX` rebuilds an index from table data, recreating the index structure and removing bloat/corruption depending on the cause. REINDEX typically requires stronger locks and can block writes to the relation for a significant portion of the operation.

~~~sql
REINDEX INDEX public.orders_created_at_idx;
REINDEX TABLE public.orders;
~~~

Run during a maintenance window when blocking is acceptable. Ensure disk headroom for the new index and WAL, especially if the database uses replication or archiving.

### 6.2. REINDEX CONCURRENTLY

`REINDEX CONCURRENTLY` reduces blocking for concurrent reads/writes but executes in multiple phases, uses extra disk space, and can take longer. It cannot run inside a transaction block.

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

Monitor `pg_stat_progress_create_index`, lock waits, temporary storage, WAL, and replication lag. Check version support and limitations for partitioned indexes before scheduling.

### 6.3. REINDEX DATABASE

`REINDEX DATABASE` can generate heavy workload and lock many relations. Avoid running it as a database-wide routine if only a few indexes show evidence of needing a rebuild. Build a target list and run sequentially or in capacity-measured batches.

### 6.4. pg_repack

`pg_repack` is an external extension/tool outside PostgreSQL core that reorganizes tables/indexes with low blocking for most of the process by copying and syncing changes, then performing a brief swap. It requires compatible extension/binary versions, privileges, and disk headroom; it can also generate heavy WAL and load.

Do not treat `pg_repack` as zero-lock or risk-free. Verify version compatibility, primary key/unique key requirements for tables, long transactions, replication lag, and abort/retry procedures.

### 6.5. VACUUM and REINDEX Do Not Replace Each Other

VACUUM handles dead tuples and space reuse; REINDEX rebuilds the index structure. VACUUM can often clean index entries without necessarily returning filesystem space. REINDEX can reclaim index bloat after swap/cleanup, but does not replace VACUUM for the heap.

### 6.6. VACUUM FULL

`VACUUM FULL` rewrites the table to return space to the filesystem, but requires an `ACCESS EXCLUSIVE` lock and enough temporary space for the rewrite. It is not routine index maintenance and generally causes significant downtime/lock impact.

### 6.7. CLUSTER

`CLUSTER` physically reorders a table based on an index, which can improve locality for suitable workloads, but rewrites the relation, requires strong locks, and generates heavy I/O and WAL. Run it only with proven query benefits and a maintenance window.

### 6.8. Choosing Actions Based on Evidence

| Observation | Action to Consider |
| --- | --- |
| Stale planner estimates | ANALYZE |
| Increasing dead tuples, autovacuum lag | Tune autovacuum / run VACUUM |
| Confirmed index bloat | REINDEX / pg_repack within lock budget |
| Invalid index | Investigate build failure, drop/rebuild safely |
| Index corruption | Restore / REINDEX per corruption response guidance |
| Table must return space to filesystem | Evaluate VACUUM FULL / pg_repack |
| Query plan not using index | Check statistics, predicates, operator class, and workload |

## 7. Statistics Maintenance

### 7.1. Planner Statistics

The PostgreSQL planner uses statistics to estimate row counts, value distributions, distinct values, most common values, and selectivity. Stale statistics can cause the planner to pick poor join orders, scan types, or join methods.

### 7.2. ANALYZE

`ANALYZE` samples the table and updates catalog statistics. PostgreSQL normally runs autoanalyze automatically after sufficient table changes; DBAs can run it proactively after bulk loads, major data distribution shifts, or when query plan regressions indicate stale stats.

~~~sql
ANALYZE public.orders;
ANALYZE (VERBOSE) public.orders;
ANALYZE public.orders (customer_id, created_at, status);
~~~

ANALYZE does not rewrite the table and is generally less blocking than DDL, though it still reads pages, consumes I/O, and can affect workload.

### 7.3. VACUUM (ANALYZE)

~~~sql
VACUUM (ANALYZE, VERBOSE) public.orders;
~~~

Combine VACUUM and ANALYZE when both dead tuple cleanup and planner stats are needed. Do not run ANALYZE after every transaction; base it on workload and thresholds.

### 7.4. Monitoring Analyze Counters

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 50;
~~~

`n_mod_since_analyze` is an estimate/counter of modifications since the last analyze on supported versions. Columns and reset behavior can vary; check the catalog for your major version.

### 7.5. Autoanalyze Thresholds

Autoanalyze is triggered based on modification counts and thresholds/scale factors, not a fixed schedule. Settings include `autovacuum_analyze_threshold`, `autovacuum_analyze_scale_factor`, and per-table storage parameters.

For very large tables, the default scale factor may cause autoanalyze to wait until huge numbers of rows change. Configure appropriate per-table thresholds/scale factors instead of lowering the global threshold excessively.

~~~sql
ALTER TABLE public.orders
SET (autovacuum_analyze_scale_factor = 0.02);
~~~

This example merely illustrates per-table tuning; choose values based on modification rate and planner sensitivity.

### 7.6. Statistics Target

`default_statistics_target` controls the default level of statistical detail. Higher targets can be set for skewed or critical columns, though increasing the target increases sampling work and catalog size.

~~~sql
ALTER TABLE public.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE public.orders (status);
~~~

Do not raise the database-wide target when only certain columns need finer granularity.

### 7.7. Extended Statistics

When columns are correlated, single-column statistics can mislead planner estimates. Extended statistics support dependencies, ndistinct, and most-common-values for column groups.

~~~sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, ndistinct, mcv)
ON customer_id, status
FROM public.orders;

ANALYZE public.orders;
~~~

Choose statistics types based on query predicates and groupings. Extended statistics do not replace all forms of multi-column estimation and require ANALYZE to update.

### 7.8. Bulk Loads and Statistics

After a large bulk load or import, running ANALYZE on affected tables helps the planner update row distributions. If a table is partitioned, check your version and how parent/partitions are analyzed so the planner has the needed statistics.

### 7.9. Statistics After Partition Maintenance

When attaching, detaching, or dropping partitions, bulk loading a new partition, or altering distributions, schedule ANALYZE on the relevant parent/partition. Verify planner estimates on key queries afterward.

### 7.10. Do Not Reset Statistics to "Clean Up" Dashboards

Resetting counters destroys baselines and makes index usage and maintenance counters hard to interpret. If a measurement window is needed, save a snapshot before resetting and record the reset timestamp clearly. Never reset stats just to make numbers look neat.

## 8. VACUUM and Autovacuum in Maintenance Schedules

### 8.1. Autovacuum Is the Default Mechanism to Keep Enabled

Autovacuum cleans up dead tuples and freezes tuples to limit table/index bloat and prevent transaction ID wraparound. Autoanalyze updates planner statistics. A DBA schedule should monitor and tune this mechanism rather than replacing it with a blanket nightly VACUUM.

### 8.2. Monitoring Dead Tuples and Vacuum History

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup /
        NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
~~~

This percentage is an estimate derived from statistics, not page-level bloat. Use it to pick tables for investigation.

### 8.3. Autovacuum Per-Table Tuning

~~~sql
ALTER TABLE public.events
SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01,
    autovacuum_analyze_threshold = 2000
);
~~~

This example illustrates configuring thresholds and scale factors. For very large or write-heavy tables, values should be calculated from row churn, vacuum duration, storage, and RPO. Do not copy directly to every table.

### 8.4. Autovacuum Capacity

Settings to understand:

- `autovacuum_max_workers`: number of concurrent autovacuum workers;
- `autovacuum_naptime`: sleep interval between launcher checks;
- `autovacuum_vacuum_cost_limit` and `autovacuum_vacuum_cost_delay`: throttling;
- `maintenance_work_mem`/`autovacuum_work_mem`: memory for maintenance;
- Per-table vacuum/analyze thresholds and scale factors.

Adding workers can help catch up but also increases I/O and CPU. Adjust based on observed throughput and user latency.

### 8.5. Freezing and Wraparound

Transaction ID wraparound is a severe availability risk. Include `age(datfrozenxid)` in daily monitoring and prioritize anti-wraparound vacuum when alerts fire. Do not delay freeze work to run non-urgent index maintenance.

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

### 8.6. Long Transactions and Replication Slots

Long-lived transaction snapshots or replication slots holding xmin can prevent vacuum from reclaiming tuples. Include transaction age, `backend_xmin`, replication slot `xmin`, and retained WAL in daily checks.

### 8.7. VACUUM VERBOSE and Logs

During a maintenance window, `VACUUM (VERBOSE)` helps reveal processed pages and tuples. For autovacuum, configure appropriate logging (e.g., `log_autovacuum_min_duration`) to spot long operations, skipped pages, and worker behavior.

### 8.8. VACUUM Does Not Return All Disk Space

VACUUM normally marks space as reusable inside the relation; filesystem file sizes usually do not shrink. Reclaiming space for the OS requires a rewrite/compaction strategy such as VACUUM FULL or pg_repack with lock and capacity planning.

## 9. Capacity Management: Inventory and Growth

### 9.1. Capacity Is More Than Database Size

Capacity planning must monitor multiple layers:

- Heap tables and TOAST;
- Indexes;
- Tablespaces and filesystems;
- WAL directory and archive staging;
- Temporary files;
- Backup repositories and snapshots;
- Replication slot retained WAL;
- Logs, audit files, and monitoring data;
- Free space needed for maintenance, rewrites, and restores.

### 9.2. Database Size Snapshot

Run periodically and store results with timestamps:

~~~sql
SELECT
    now() AS collected_at,
    datname,
    pg_database_size(datname) AS database_bytes
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

Run against each cluster and retain cluster identity, version, and region to compare sources accurately.

### 9.3. Relation Size Snapshot

~~~sql
SELECT
    now() AS collected_at,
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_relation_size(c.oid) AS main_bytes,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'i', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

For partitioned tables, the parent relation does not hold all partition data like an ordinary heap. Inventories must measure leaf partitions to avoid underreporting space.

### 9.4. Tablespace Usage

`pg_tablespace_size()` reports bytes used inside a tablespace. It does not report free bytes on the volume. Collect filesystem/cloud volume capacity, free space, quotas, and IOPS/throughput as well.

### 9.5. WAL Capacity

WAL can grow due to bulk loads, index builds, replication slots, archive failures, or standby lag. Monitor:

- Size of `pg_wal` on the filesystem;
- `max_wal_size` and checkpoint activity;
- Replication slots retaining WAL;
- Archive backlog or failures;
- WAL generation rate;
- Disk free headroom.

### 9.6. Replication Slot Retained WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS retained_wal_estimate
FROM pg_replication_slots
ORDER BY slot_name;
~~~

This query estimates the WAL distance from the current LSN to `restart_lsn`; it is not an exact measure of bytes occupied on the filesystem because segment boundaries, archiving, and WAL recycling also apply. Available columns depend on slot type and version.

### 9.7. Temporary Files

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

`temp_bytes` and `temp_files` are cumulative counters, not the amount of temporary files currently on disk. Combine `log_temp_files`, query plans, `work_mem`, and filesystem monitoring to locate sort/hash spills.

### 9.8. Backup Repository Capacity

Monitor:

- Full/base backup sizes;
- Incremental backup chain sizes;
- WAL archive bytes;
- Retention counts and ages;
- Immutable object versions;
- Failed or partial backups;
- Object storage quotas, requests, and egress;
- Restore staging capacity.

Retention policies must account for incremental chain and WAL dependencies. Never delete backups or WAL by file age alone if they remain required for a recovery chain.

### 9.9. Capacity Headroom

Maintain headroom for normal growth, burst workloads, and maintenance. REINDEX, pg_repack, and VACUUM FULL can require substantial temporary additional space. Restore drills also need enough staging space to recover backups.

Do not wait until a volume reaches 95% to plan expansion. Use warning and critical thresholds based on growth rates and provisioning lead time.

## 10. Growth Rate and Forecasting

### 10.1. Growth Between Two Snapshots

Given two snapshots:

\[
\text{Growth rate} =
\frac{\text{Size}_{new}-\text{Size}_{old}}{\Delta t}
\]

For example, if a database grows by 120 GB over 30 days, average growth is roughly 4 GB/day. Use raw bytes and actual elapsed time, never subtract values formatted by `pg_size_pretty`.

### 10.2. Forecasting Time to Threshold

\[
\text{Days to threshold} =
\frac{\text{Capacity}-\text{Current usage}-\text{Reserve}}
{\text{Average daily growth}}
\]

This is a linear estimate. Workloads exhibit seasonality, batch cycles, retention expirations, and data spikes, so multiple measurement windows and scenario planning are needed.

### 10.3. Growth by Relation

Storing per-relation snapshots reveals which tables or indexes are growing fastest. When relations are renamed, dropped, or partition-rotated, record OIDs plus database identity and lifecycle events to link history accurately.

### 10.4. Separating Data Growth from Bloat Growth

Database size growth may stem from business data, index growth, dead space, TOAST, WAL, or backup retention. Break down the components before concluding whether you need more storage or reorganization.

### 10.5. Partitioning and Retention

For time-series or event data, partitioning supports retention by detaching/dropping old partitions rather than issuing a DELETE across millions of rows. Schedule partition creation, attach/detach, analyze, and backup policies. Dropping a partition is destructive; verify legal/retention policies and backup requirements first.

### 10.6. Compression and Archival

Moving older data to an archive/warehouse or compressing it in a suitable format can reduce primary storage, though you must define query access, restore latency, encryption, and retention. Do not treat an archive as your sole backup.

### 10.7. Capacity Review

Each review cycle should answer:

- Growth rate by database, table, and index;
- Projected time to warning and critical thresholds;
- Volumes or quotas requiring expansion;
- Whether WAL/backup retention remains reasonable;
- Whether partition retention is operating properly;
- Whether maintenance/rebuilds have enough temporary space;
- Whether the DR region has enough capacity to take over the workload.

## 11. Scheduling Maintenance

### 11.1. Sample Schedule by Task Group

The schedule below is a starting point to tailor by workload, not a mandatory cadence:

| Reference Frequency | Task | Purpose |
| --- | --- | --- |
| Continuous | autovacuum/autoanalyze, replication/archive monitoring | Cleanup and statistics driven by activity |
| Every 5–15 minutes | capacity/lag/backup health metrics | Early pressure detection |
| Daily | database/table growth snapshot, xid age, slot/WAL review | Track trends and risk |
| Weekly | index usage/invalid index review, long transaction review | Detect index/transaction issues |
| Monthly | bloat sampling, risk-based index integrity checks, capacity forecast | Evaluate conditional maintenance |
| Per change/bulk load | ANALYZE affected tables, verify plans | Update statistics after changes |
| Per incident/restore drill | backup verification and restore test | Prove recoverability |
| On demand | REINDEX/pg_repack/CLUSTER/VACUUM FULL | Remediate confirmed issues |

### 11.2. Choosing Maintenance Windows

Pick low-workload hours that still have on-call and business coverage. Account for batch jobs, reporting windows, replication/backup windows, cloud maintenance, and timezones. Do not stack multiple I/O-heavy tasks simultaneously.

### 11.3. Task Ordering

A typical sequence might be:

1. Capture baseline and capacity;
2. Verify replication, archive, and backup health;
3. Run targeted ANALYZE or VACUUM if needed;
4. Run index operations in batches;
5. Verify query plans and integrity;
6. Capture post-maintenance metrics;
7. Document results and follow-ups.

If freeze/wraparound risk exists, prioritize it ahead of non-urgent index optimization.

### 11.4. Job Duration Budgets

Set expected duration, hard timeout, lock timeout, and stop conditions. If a job exceeds its budget, determine whether it is making progress or blocked before deciding to cancel. Do not automatically kill all operations at the end of a window if cancellation could trigger a lengthy rollback.

### 11.5. Job Dependencies

Do not run REINDEX when a volume lacks space; do not run heavy backups concurrently with storage migrations; do not run multiple bulk COPY jobs or index builds when standbys or archiving are lagging. Use scheduler/orchestrator dependencies to avoid resource contention.

### 11.6. Idempotency

Inventory queries can be safely re-run. DDL and maintenance actions must check current state before running and log results. Do not blindly retry a timed-out command without knowing whether the server finished it.

### 11.7. Preventing Overlapping Jobs

Use scheduler concurrency policies, OS locks (such as `flock` on Linux), or PostgreSQL advisory locks to allow only one instance of a job. When using advisory locks, keep the same session connection open throughout the operation; session locks expire when the connection closes.

### 11.8. Time and Timezones

Store schedules in an agreed timezone; servers, schedulers, and monitoring may use different timezones. Use UTC for event timestamps and log correlation, and display local times clearly in runbooks.

### 11.9. Changing Maintenance Windows

When workload peaks, business schedules, or SLAs shift, revisit the window. Do not keep an old schedule simply because a job ran fine for months.

## 12. Scheduling with pg_cron or an OS Scheduler

### 12.1. Choosing a Scheduler

| Mechanism | Best When | Aspects to Manage |
| --- | --- | --- |
| OS cron/systemd timer | Jobs run scripts, psql, or filesystem/cloud CLIs | OS identity, credentials, logs, retries |
| pg_cron | SQL jobs running inside PostgreSQL | Extension availability, database scope, role, job history |
| External orchestrator | Multi-step workflows spanning multiple systems | Concurrency, secrets, retries, alerting, audit |
| Managed service scheduler | Database service provides built-in automation | Provider limits, permissions, and behavior |

Do not install a new scheduler just to run one simple query if the platform already has suitable job orchestration.

### 12.2. pg_cron

`pg_cron` is a scheduler extension that executes SQL using cron syntax. Install the package/extension matching your PostgreSQL major version, configure preload settings if required, grant privileges, and verify the target database where jobs execute.

Example scheduling ANALYZE nightly:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.schedule(
    'nightly-analyze-orders',
    '15 2 * * *',
    'ANALYZE public.orders'
);
~~~

Example scheduling an inventory query or maintenance function:

~~~sql
SELECT cron.schedule(
    'daily-capacity-snapshot',
    '10 1 * * *',
    'SELECT ops.capture_capacity_snapshot()'
);
~~~

Any referenced function must exist beforehand, have explicit schema/permissions, and record outcomes. Never schedule REINDEX, VACUUM FULL, or destructive DDL across the entire database merely because cron can execute it.

### 12.3. Jobs in Other Databases

Some versions of `pg_cron` support `cron.schedule_in_database()` to specify the target database. Check the installed extension version and documentation; do not assume every cluster exposes the same API.

### 12.4. Managing Jobs

Inspect jobs and run history via `pg_cron` catalog views such as `cron.job` and `cron.job_run_details` on supported versions. Monitor status, return messages, start/end times, and durations; maintain appropriate log retention.

### 12.5. OS cron/systemd with psql

Example running ANALYZE via `psql`:

~~~bash
psql "service=prod-maintenance dbname=appdb" \
  -X -v ON_ERROR_STOP=1 \
  -c "ANALYZE public.orders"
~~~

`service=prod-maintenance` references a service definition in the libpq service file; credentials should come from `.pgpass` or a secret manager with strict file permissions. Avoid literal passwords on command lines, in scripts, or in crontabs.

### 12.6. Multiple Commands in the Same Session

You can pass multiple `-c` options to send commands sequentially in the same `psql` session:

~~~bash
psql "service=prod-maintenance dbname=appdb" \
  -X -v ON_ERROR_STOP=1 \
  -c "SET lock_timeout = '5s'" \
  -c "SET statement_timeout = '45min'" \
  -c "REINDEX INDEX CONCURRENTLY public.orders_created_at_idx"
~~~

Note that `REINDEX CONCURRENTLY` cannot run inside a transaction block. Keep the `SET` commands and maintenance command in the same session via separate command flags as shown, and verify the behavior of your `psql`/server version.

### 12.7. Do Not Wrap Long Maintenance Commands in a Transaction

VACUUM, CREATE INDEX CONCURRENTLY, and REINDEX CONCURRENTLY have strict transaction restrictions. Schedulers and job runners must not automatically wrap these commands in an explicit transaction. Verify whether your tool opens transactions implicitly.

### 12.8. Credentials and Permissions

Create a maintenance role with the minimum required privileges. Roles running ANALYZE or VACUUM on tables require ownership or version-appropriate privileges; REINDEX and DDL require ownership or granted rights. Avoid using superuser for all scheduled jobs unless strictly necessary.

### 12.9. Job Timezones

Cron expressions may be interpreted according to the scheduler or extension timezone. Fix the timezone, daylight saving behavior, and handling of skipped or repeated hours. Use UTC timestamps in logs.

### 12.10. Scheduler Downtime

If the scheduler stops running, jobs will miss their schedules. Monitor last successful run timestamps and overdue states rather than checking only whether the scheduler process is alive.

## 13. Job Logging, Concurrency, and Error Handling

### 13.1. Recording Each Run

A simple log table can store execution metadata:

~~~sql
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.maintenance_run (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_name text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);
~~~

The job runner inserts a row at startup and updates `finished_at`/`status` upon completion. If the process crashes unexpectedly, rows left in `running` state help detect stale jobs; define a policy to mark them failed after a timeout.

### 13.2. Do Not Equate SQL Success with Business Success

ANALYZE succeeding does not prove query plans are optimal; REINDEX succeeding does not prove application latency dropped; a capacity query succeeding does not prove the filesystem has enough room. Jobs need goal-oriented post-checks.

### 13.3. Concurrency Control

A job should not run concurrently against the same target if operations conflict or compete for resources. Use scheduler concurrency limits, OS locks, or session-level advisory locks.

Advisory lock example:

~~~sql
SELECT pg_try_advisory_lock(548001::bigint) AS acquired;
~~~

If `acquired` is false, another job holds the lock; the new job should exit with a skipped/overlap status. Keep the session open while running and release the lock upon completion:

~~~sql
SELECT pg_advisory_unlock(548001::bigint);
~~~

Advisory locks only coordinate jobs that follow the same key convention; they do not stop a DBA or other DDL from running directly.

### 13.4. Retry Policy

Retries are appropriate only for transient failures and operations confirmed safe to repeat. On timeouts or disconnects, inspect server state first because the command may have completed even though the client never received the response.

### 13.5. Backoff

When schedulers, storage, or networks fail, use exponential backoff with jitter and a retry limit. Do not let multiple jobs simultaneously retry a shared failure and overload the system further.

### 13.6. Exit Codes

Scripts must return non-zero when `psql` or commands fail. Use `ON_ERROR_STOP=1` in `psql` scripts, check exit statuses, and capture stderr. Never redirect output in a way that swallows exit codes or masks errors.

### 13.7. Logs

Record:

- Task name and run ID;
- Cluster, database, schema, and target;
- Start/end timestamps and timezone;
- SQL/tool version;
- Exit code and status;
- Elapsed time;
- Before/after rows, bytes, or index sizes where applicable;
- Warnings and errors;
- Actor or service account;
- Change or incident reference.

Never log passwords, connection strings containing secrets, or sensitive query literals.

### 13.8. Stale Job Detection

Define expected durations and heartbeats. If a run stays `running` past its deadline, inspect backend and OS processes before killing anything. Distinguish "job runner died" from "database operation still actively running".

## 14. Maintenance Safety Controls

### 14.1. Before/After Baselines

Before an operation, capture:

- Relation and index sizes;
- Query latency and throughput;
- CPU, disk IOPS/latency, and free space;
- Replication lag and WAL archiving;
- Lock waits and long transactions;
- Backup health.

After the operation, measure the same metrics and compare.

### 14.2. lock_timeout

`lock_timeout` limits how long a statement waits for a lock. A small value prevents maintenance from blocking traffic for long when DDL requires strong locks; however, the job may fail and require retries under busy workloads.

### 14.3. statement_timeout

`statement_timeout` limits total statement duration. Set it according to expected duration and rollback cost. Timing out a lengthy rewrite can trigger a substantial rollback; do not set it arbitrarily low out of habit.

### 14.4. maintenance_work_mem

`maintenance_work_mem` affects maintenance operations like index builds and VACUUM. Increasing it can reduce passes and aid sorts, but total memory consumption scales with concurrent jobs and workers. Set it at the session level for specific jobs after calculating capacity.

### 14.5. I/O Throttling

VACUUM cost delay/limit parameters can cap I/O impact. For REINDEX, pg_repack, and CLUSTER, consider timing, parallelism, and storage throughput. Never run multiple heavy jobs concurrently if production latency risks breaching SLOs.

### 14.6. Replication and WAL Safety

Monitor synchronous standbys, async lag, archive failures, and slot-retained WAL. Pause or defer maintenance if potential RPO threatens targets or the WAL disk nears capacity.

### 14.7. Disk Preflight

Before REINDEX, pg_repack, or VACUUM FULL, estimate target size and temporary space. Check the destination tablespace, WAL volume, temp volume, and filesystem reserve. If headroom is insufficient, defer or pick an alternative approach.

### 14.8. Stop Conditions

Predefine stop conditions:

- Application latency or error rates exceed thresholds;
- Free disk drops below reserve;
- Replication lag exceeds RPO budget;
- Prolonged WAL archive failures;
- Lock waits impact critical transactions;
- Maintenance job shows no progress and has an unclear blocker.

### 14.9. Rollback and Compensation

ANALYZE can simply be re-run; an invalid index rebuild may need dropping/retrying; pg_repack has its own cleanup procedure; dropping a partition may be irreversible without a backup. Classify actions before running and maintain a recovery path.

### 14.10. Change Management

Major DDL, autovacuum setting changes, retention policies, tablespaces, and scheduler updates should have an owner, review, window, monitoring, and post-checks. Record old configurations to revert if needed.

## 15. Capacity Alerts and Dashboards

### 15.1. Separating Logical Usage and Physical Free Space

Dashboards should cover two categories:

- PostgreSQL logical usage: database/table/index/tablespace sizes, WAL retention estimates, temp bytes, and backup sizes;
- Infrastructure capacity: filesystem free bytes, volume quotas, IOPS, throughput, latency, object storage capacity, and provisioning lead time.

A database size query succeeding does not mean the volume has enough free space. WAL, logs, temp files, and backup staging may reside on separate volumes.

### 15.2. Lead-Time-Based Thresholds

Set warning alerts when projected time to capacity approximates provisioning lead time plus reserve. Set critical alerts when free space drops below what is needed to complete maintenance and backups safely. For example, 20% free might be reasonable on one system yet far too late on a system growing several TB per day.

### 15.3. Growth Alerts

Alert when:

- Database, table, or index growth exceeds baseline;
- Growth rates shift abruptly;
- One tablespace grows much faster than others;
- WAL usage rises continuously;
- Backup repository size exceeds retention forecasts;
- Temp bytes or temp files spike abnormally.

Distinguish temporary spikes from sustained growth across multiple snapshots.

### 15.4. Index Health Dashboard

Display:

- Top indexes by bytes;
- Index scan, read, and fetch counters;
- Index size growth;
- Invalid indexes;
- Bloat sampling results;
- Index integrity check status;
- REINDEX/pg_repack history.

Never turn an "`idx_scan = 0`" panel into an automatic drop-index action.

### 15.5. Statistics Dashboard

Display:

- `n_mod_since_analyze`;
- `last_analyze`/`last_autoanalyze`;
- `n_dead_tup`;
- `last_vacuum`/`last_autovacuum`;
- Transaction ID age;
- Planner row estimates vs. actual rows from query plan sampling;
- Query latency and plan regressions.

### 15.6. Capacity Dashboard

Display:

- Database/table/index/tablespace bytes;
- Filesystem free/used space;
- Daily and weekly growth rates;
- Days to warning and critical capacity;
- WAL and slot retained bytes;
- Temp files and bytes;
- Backup/archive bytes and retention;
- Maintenance temporary-space reserve.

### 15.7. Alert Ownership

Every alert requires an owner, severity, runbook, and action. Capacity warnings may belong to platform/SRE; stale statistics to DBAs; invalid indexes to DBAs/applications; backup retention to backup owners. Never create alerts with no one responsible for handling them.

## 16. Monthly Index Maintenance Runbook

### 16.1. Before Review

1. Confirm workload windows and business calendars;
2. Gather index sizes and usage counters;
3. Check statistics reset timestamps;
4. Review constraint dependencies and query workloads;
5. Run bloat sampling on candidates;
6. Inspect invalid indexes and integrity alerts;
7. Check disk headroom, WAL, and replication lag.

### 16.2. Ranking Candidates

Prioritize indexes with:

- Confirmed bloat and large size;
- Clear query latency or plan impact;
- Corruption or invalid state;
- Collation version changes requiring rebuild;
- High write overhead with low proven benefit from workload review.

### 16.3. Selecting the Operation

- Standard REINDEX when a lock window is acceptable;
- REINDEX CONCURRENTLY when writes must continue and disk headroom suffices;
- pg_repack when reorganizing tables/indexes with low blocking within tool constraints;
- Take no action if evidence is insufficient.

### 16.4. Execution

Run a single target or small batch first. Set lock/statement timeouts, monitor progress, CPU/I/O, WAL, replication, and application latency. If metrics hit stop conditions, halt per runbook.

### 16.5. After the Operation

Verify index validity/readiness, query plans, latency, index size, replication lag, and free disk space. Record before/after sizes and actual duration.

## 17. Daily and Weekly Statistics & Capacity Runbook

### 17.1. Daily Checks

- Review database, table, and tablespace growth;
- Check filesystem free space;
- Review WAL usage, replication slots, and archive health;
- Check transaction ID age;
- Review long-running transactions;
- Verify last successful backup and repository capacity;
- Check autovacuum/autoanalyze progress or lag.

### 17.2. Weekly Checks

- Review top tables and indexes by growth;
- Review index usage and invalid indexes;
- Check stale statistics on high-churn tables;
- Review temporary files and query spills;
- Review partition retention and creation;
- Check replication and backup trends;
- Update days-to-capacity forecasts.

### 17.3. Monthly Checks

- Risk-based bloat sampling;
- Risk/criticality-based index integrity checks;
- Review autovacuum thresholds and worker capacity;
- Review statistics targets and extended stats;
- Review REINDEX/pg_repack candidates;
- Review backup retention and restore drill outcomes;
- Review capacity forecasts and budgets.

### 17.4. After Bulk Loads or Schema Changes

Run ANALYZE on affected tables, verify query plans, index validity, table growth, and replication lag. For new partitions, confirm indexes and constraints are properly attached and the planner has needed statistics.

### 17.5. After Major Upgrades

Verify extension compatibility, statistics refreshes per upgrade guidance, collation changes, index validity/integrity, autovacuum settings, and scheduled jobs. Do not run mass REINDEX without justification and a plan; collation version mismatches may require targeted handling.

## 18. Complete Scheduling Example

### 18.1. Sample Schedule Table for an OLTP Cluster

| Job | Example Schedule | Duration Budget | Output to Store |
| --- | --- | --- | --- |
| Capacity snapshot | Every 15 minutes | Under 1 minute | Database/relation/volume bytes |
| WAL/slot/archive check | Every 5 minutes | Under 30 seconds | Lag, retained WAL, archive failures |
| Daily stats inventory | 01:00 UTC | Under 5 minutes | Table changes, vacuum/analyze dates |
| Daily ANALYZE hot tables | After bulk batch, if needed | Per table | Stats refresh result |
| Weekly index inventory | Sunday | Under 10 minutes | Size/usage/invalid candidates |
| Monthly bloat sample | Maintenance window | Per target | pgstattuple/index report |
| Integrity check | Per risk tier | Per index size | amcheck outcome |
| REINDEX candidate | Change window | Per index size | Progress, size, plan comparison |
| Restore verification | Per DR policy | Per RTO | Restore result and measured time |

This is an illustrative schedule. Frequency, timing, and duration budgets must be calibrated from cluster metrics.

### 18.2. Inventory Query for a Daily Job

~~~sql
SELECT
    now() AS collected_at,
    current_database() AS database_name,
    count(*) AS user_table_count,
    sum(pg_total_relation_size(relid)) AS total_relation_bytes,
    sum(pg_relation_size(relid)) AS main_fork_bytes,
    sum(pg_indexes_size(relid)) AS index_bytes,
    sum(n_live_tup) AS estimated_live_tuples,
    sum(n_dead_tup) AS estimated_dead_tuples
FROM pg_stat_user_tables;
~~~

Tuple counts are estimates; sums across table views are for trending, not exact row counts. Run the query inside each database.

### 18.3. Daily Capacity Alert Input

~~~sql
SELECT
    datname,
    pg_database_size(datname) AS database_bytes,
    age(datfrozenxid) AS xid_age
FROM pg_database
WHERE datallowconn
ORDER BY database_bytes DESC;
~~~

Feed the output into the monitoring store alongside filesystem metrics. Define thresholds based on capacity and wraparound policy.

### 18.4. Scheduled ANALYZE After Import

An import pipeline can invoke ANALYZE directly after committing a bulk load:

~~~sql
ANALYZE public.orders;
ANALYZE public.order_items;
~~~

Run only after the import succeeds and the transaction commits. If the pipeline retries, record job state so heavy steps are not unnecessarily repeated.

### 18.5. Batch REINDEX

Build a reviewed candidate list and process indexes in small batches. Do not use an unbounded loop that automatically runs REINDEX on every index crossing a threshold; check disk, lag, and latency after each batch and halt if a stop condition triggers.

## 19. Common Mistakes

### 19.1. Reindexing Everything on a Rigid Schedule

Causes I/O and WAL bursts, consumes disk, and can block workloads. Choose targets based on evidence.

### 19.2. Running VACUUM FULL Every Night

Requires strong locks and rewrites storage. Autovacuum/VACUUM should handle daily maintenance; rewrites should only be used when justified.

### 19.3. Dropping an Index Only Because idx_scan = 0

Counters may have just reset or missed rare workloads. Check constraints, workload windows, and query plans first.

### 19.4. Mistaking Relation Size for Filesystem Free Space

Logical bytes do not reflect all volume usage. Combine with OS/cloud metrics.

### 19.5. Ignoring WAL and Replication During Maintenance

Index rebuilds, COPY, and rewrites can generate heavy WAL. Monitor standbys, archiving, and disk headroom.

### 19.6. Raising maintenance_work_mem Globally

Multiple concurrent maintenance jobs can multiply memory consumption. Prefer session-level or per-job settings after calculating capacity.

### 19.7. Running the Scheduler as Superuser

Expands the blast radius. Use dedicated roles, least privilege, secret managers, and auditing.

### 19.8. Failing to Log Failed Runs

If only successes are logged, overdue or failing jobs can go unnoticed. Track last attempted and last successful runs separately.

### 19.9. Blindly Retrying After Timeout

The command may have finished on the server. Check state and catalogs before retrying.

### 19.10. Skipping Post-Maintenance Verification

Command exit code 0 does not prove latency, plans, capacity, or integrity improved. Compare baseline and post-check measurements.

## 20. Practice Exercises: Index, Statistics, and Capacity Maintenance

Complete these exercises in a lab or using simulated data. Never run REINDEX, VACUUM FULL, pg_repack, or destructive partition operations in production just for practice. For version-dependent extensions or columns, check documentation for your exact environment.

### Exercise 1 — Maintenance Cycle

Describe the observe, diagnose, plan, execute, verify, and learn cycle. Give an example task for each step.

### Exercise 2 — Index Cost

Explain why adding more indexes can slow down INSERT/UPDATE operations and increase WAL generation.

### Exercise 3 — Index Usage

Write a query listing the top 20 indexes by size and displaying `idx_scan`, `idx_tup_read`, and `idx_tup_fetch`.

### Exercise 4 — Zero Scans

A large index shows `idx_scan = 0` over 7 days. List at least six checks to perform before proposing a DROP.

### Exercise 5 — Invalid Index

Write a query to find indexes with `indisvalid = false`. Explain how to handle an invalid index left behind by a canceled `CREATE INDEX CONCURRENTLY`.

### Exercise 6 — Bloat

Explain why `pg_relation_size` and row counts are insufficient to determine index bloat. Describe the role of `pgstattuple`/`pgstatindex`.

### Exercise 7 — Integrity

Distinguish bloat sampling from `amcheck`. Which tool checks B-tree structural integrity?

### Exercise 8 — REINDEX Modes

Compare regular `REINDEX` with `REINDEX CONCURRENTLY` in terms of locking, disk usage, runtime, and transaction restrictions.

### Exercise 9 — pg_repack

Describe how `pg_repack` reduces blocking and list prerequisites and risks that must be verified.

### Exercise 10 — VACUUM vs REINDEX

A table has high dead tuples and a large index. Why might running only REINDEX or only VACUUM fail to solve the entire problem?

### Exercise 11 — Table Inventory

Write a query listing the top 30 user tables by `pg_total_relation_size`, separating heap, index, and total bytes.

### Exercise 12 — Database Size

Write a query sorting databases by `pg_database_size` and explain why capacity monitoring is also needed outside PostgreSQL.

### Exercise 13 — Tablespace

Write a query showing the size of each tablespace. Why does this size not reveal filesystem free space?

### Exercise 14 — Growth Rate

A database grows from 800 GB to 920 GB over 30 days. Calculate the average growth in GB/day and forecast when a volume with 200 GB free will fill up.

### Exercise 15 — WAL Retained

Write a query estimating WAL distance from the current LSN to a replication slot's `restart_lsn`. State the limitations of this estimate.

### Exercise 16 — Temp Files

Distinguish cumulative `temp_bytes` in `pg_stat_database` from temporary files currently on disk. Name additional metrics needed.

### Exercise 17 — Analyze

Explain why large bulk loads should be followed by ANALYZE on affected tables.

### Exercise 18 — Autoanalyze

A 500-million-row table receives 2 million modifications. Explain how the scale factor affects when autoanalyze runs and how to tune it per table.

### Exercise 19 — Statistics Target

A `status` column has heavily skewed distribution. Write `ALTER TABLE ... SET STATISTICS` and `ANALYZE` for that column alone; describe the trade-offs.

### Exercise 20 — Extended Statistics

Two columns, `customer_id` and `status`, are correlated. Write `CREATE STATISTICS` with dependencies/MCV and `ANALYZE`; explain the benefits.

### Exercise 21 — Autovacuum Monitoring

Write a query finding the top tables by estimated dead tuples and displaying `last_autovacuum`/`last_autoanalyze`.

### Exercise 22 — Wraparound

Write a query ranking databases by `age(datfrozenxid)`. Why is this a critical daily health check?

### Exercise 23 — Maintenance Schedule

Design a daily/weekly/monthly schedule for a 2 TB OLTP database. Separate monitoring, routine cleanup, and destructive maintenance.

### Exercise 24 — Maintenance Window

A `REINDEX CONCURRENTLY` must run within a 30-minute window. Design preflight checks, `lock_timeout`, `statement_timeout`, stop conditions, and post-checks.

### Exercise 25 — pg_cron

Write an example scheduling nightly ANALYZE using `pg_cron`. State prerequisites and how to inspect job history.

### Exercise 26 — OS Scheduler

Write a `psql` command using a service definition to run ANALYZE, enable `ON_ERROR_STOP`, and protect credentials.

### Exercise 27 — Prevent Overlap

Explain scheduler concurrency limits and session advisory locks. Why must a lock session keep the same connection throughout the job?

### Exercise 28 — Job Logging

Design a log table storing task, start/end, status, duration, and errors. How do you handle a crashed process whose row remains in `running`?

### Exercise 29 — Capacity Alerts

A volume has 15% free space remaining, grows 100 GB/day, and takes 5 days to expand. Design warning and critical thresholds based on lead time.

### Exercise 30 — Capstone: Maintenance Program for Production PostgreSQL

An OLTP cluster has 3 TB of data, 800 GB of indexes, 50,000 writes/second at peak, three tablespaces, a synchronous standby in another AZ, and an async DR region. Storage is down to 25% free; several indexes are growing quickly, autoanalyze is falling behind, and the backup window is lengthening.

**Requirements:**

1. Build daily inventories for databases, tables, indexes, and tablespaces.
2. Collect growth snapshots and forecast days-to-capacity.
3. Monitor WAL, replication slots, archiving, and temporary files.
4. Identify top index candidates using usage, size, and bloat evidence.
5. Check invalid indexes and integrity based on risk.
6. Tune autoanalyze/autovacuum per table based on workload.
7. Choose REINDEX/REINDEX CONCURRENTLY/pg_repack within lock and disk budgets.
8. Schedule via `pg_cron` or OS scheduler with least privilege, logging, and concurrency control.
9. Set alerts and stop conditions for disk, WAL, lag, latency, and job duration.
10. Write pre/during/post-maintenance runbooks, including retries and failure handling.
11. Verify query plans, index validity, backup duration, and application latency after maintenance.
12. Present daily/weekly/monthly operational schedules with owners and acceptance criteria.

**Success criteria:** every action is backed by evidence, maintenance stays within lock/I/O/RPO budgets, capacity forecasts leave sufficient lead time for expansion, and results include baseline/post-checks plus job history.

## 21. Frequently Asked Questions

### 21.1. Should We REINDEX the Entire Database Every Month?

Not by default. Only rebuild indexes with evidence of bloat, corruption, collation changes, or performance issues. Database-wide REINDEX can cause heavy I/O/WAL and require disk and locks.

### 21.2. Does VACUUM Reduce File Size?

VACUUM normally marks space as reusable inside the relation. It usually does not return all space to the filesystem. Compacting files may require VACUUM FULL or a rewrite tool like `pg_repack`.

### 21.3. Does VACUUM Replace REINDEX?

No. VACUUM cleans dead tuples and updates visibility/free-space metadata; REINDEX rebuilds the index structure.

### 21.4. Is REINDEX CONCURRENTLY Completely Non-Blocking?

No. It reduces blocking for reads/writes during most of the process, but still has phases that wait for locks/snapshots and requires extra disk and WAL.

### 21.5. When Should pg_repack Be Used?

When you need to reorganize a table or index with lower blocking than a standard rewrite and the tool satisfies version/prerequisite constraints. It still requires disk, WAL, compatible extension/binary versions, and a brief swap step.

### 21.6. Does idx_scan = 0 Mean an Index Is Unnecessary?

No. Statistics may have reset, workloads can be seasonal, or the index may support constraints or rare queries. Review a sufficient workload window and dependencies before dropping.

### 21.7. Is pg_relation_size a Measure of Bloat?

No. It only reports bytes allocated to the relation. You need additional bloat evidence such as `pgstattuple`/`pgstatindex` and workload impact.

### 21.8. Should pgstattuple Run Daily?

Not necessarily. It can read many pages and generate I/O. Choose a sample/risk-based schedule and run off-peak on large relations.

### 21.9. Does amcheck Measure Bloat?

No. `amcheck` verifies index structure/invariants; `pgstattuple`/`pgstatindex` provide page/tuple statistics for space assessment.

### 21.10. When Should ANALYZE Be Run?

After bulk loads, major data distribution changes, schema/data maintenance, or when evidence shows planner statistics are stale. Autoanalyze should remain enabled.

### 21.11. Does ANALYZE Lock the Table?

ANALYZE uses lighter locks than DDL and does not rewrite the table, but it still reads pages and consumes I/O. Monitor waits and workload impact.

### 21.12. Is Increasing the Statistics Target Always Better?

No. Higher targets increase sampling work and catalog size. Raise it only for columns with significant skew or correlation, and verify query plans afterward.

### 21.13. Do Extended Statistics Replace Indexes?

No. Extended statistics improve planner estimates for relationships between columns; indexes are data access structures.

### 21.14. Should VACUUM Run Every Night on Every Table?

Not needed if autovacuum is working properly and tables have no special needs. Monitor dead tuples, freeze age, and autovacuum history; run manual VACUUM based on evidence.

### 21.15. Why Doesn't Autovacuum Run on Low-Churn Tables?

Thresholds/scale factors have not been reached or the table does not need cleanup. Check modification counters, settings, and logs before concluding the worker is broken.

### 21.16. Why Must Transaction ID Age Be Monitored?

If transaction IDs approach wraparound, PostgreSQL may have to enter protective mode and restrict writes. Freeze/autovacuum health is an operational priority.

### 21.17. Does pg_database_size Include WAL?

It is not a measure of total filesystem usage. WAL, logs, temp files, backups, and other volumes require separate metrics.

### 21.18. Does pg_tablespace_size Show Free Disk Space?

No. It reports relation bytes used within the tablespace; filesystem or cloud volume free space must be collected separately.

### 21.19. How Do You Forecast When a Disk Will Fill Up?

Store snapshots, calculate growth rates across multiple windows, subtract reserves and maintenance headroom, and compare against provisioning lead time. Adjust forecasts for seasonality and retention.

### 21.20. Do Replication Slots Affect Storage Capacity?

Yes. A slot can retain WAL required by an offline or lagging consumer, growing `pg_wal`. Monitor retained WAL and maintain policies for handling stale slots.

### 21.21. Is temp_bytes the Current Temp Space Usage?

No. It is a cumulative counter in statistics. Use filesystem metrics, logs, and query monitoring to see current temp files and spill workloads.

### 21.22. Can pg_cron Be Used for Every Maintenance Job?

No. `pg_cron` suits SQL jobs; workflows needing OS tools, object storage, filesystem access, approvals, or complex dependencies should use an external scheduler or orchestrator.

### 21.23. Should Schedulers Run as Superuser?

Not if a narrower role suffices. Use dedicated roles, least privilege, secret managers, and auditing.

### 21.24. Why Prevent Overlapping Jobs?

Two concurrent maintenance jobs can contend for locks, disk, CPU, memory, and I/O. Use concurrency policies or advisory locks and check running tasks before retrying.

### 21.25. Does a Job Timeout Mean the SQL Didn't Finish?

Not necessarily. The client may time out or disconnect after the server already finished. Check backend, catalog, and job logs before retrying.

### 21.26. Can a Very Low lock_timeout Be Applied to Every Job?

You should not use one value for every operation. Low values prevent long lock waits but can cause jobs to fail repeatedly. Choose based on lock impact and maintenance windows.

### 21.27. Why Does REINDEX Need Disk Headroom?

In many modes, the new index is built before replacing the old one. Temporary space is needed for both old and new structures, WAL, and concurrent operations.

### 21.28. How Often Should Index Integrity Checks Run?

Based on criticality, corruption risk, workload, and scan cost. Set a risk-based schedule rather than assuming one frequency fits all databases.

### 21.29. Is ANALYZE Required After Every REINDEX?

Not automatically. REINDEX does not change table data distributions. Run ANALYZE when statistics are stale or after data/partition changes needing updates.

### 21.30. What Is the Best Maintenance Schedule?

A good schedule is driven by workload and evidence, with owners, budgets, stop conditions, logs, and post-checks. Autovacuum/autoanalyze handle routine work; DBAs use schedules to observe, review, and execute conditional maintenance.

## 22. Official PostgreSQL Documentation

Always consult documentation matching your cluster's exact major version; columns, options, and extension compatibility can vary:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): VACUUM, ANALYZE, autovacuum, and freezing.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): VACUUM syntax and behavior.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): updating planner statistics.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): statistics targets and extended statistics.
- [CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): creating extended statistics.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuilding indexes and concurrent mode.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index creation and concurrent builds.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): table, index, and database statistics views.
- [Database Object Size Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-DBSIZE): relation, database, and tablespace size functions.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): tracking VACUUM, index builds, and other operations.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html): when to consider REINDEX.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): slot retention and streaming replication.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html): tuple/page statistics extension.
- [amcheck](https://www.postgresql.org/docs/current/amcheck.html): structural checking for indexes.
- [pg_cron project](https://github.com/citusdata/pg_cron): installing and operating the scheduler extension; verify version/package compatibility with your environment.

## 23. Summary

Scheduled maintenance is an ongoing administrative program combining autovacuum/autoanalyze, inventories, index reviews, capacity forecasting, scheduled jobs, and conditional maintenance.

| Area | Monitor | Action |
| --- | --- | --- |
| Indexes | Size, usage, bloat evidence, validity, integrity | REINDEX/pg_repack when justified |
| Statistics | Modifications, last analyze, planner estimates | Autoanalyze/ANALYZE, extended statistics |
| VACUUM | Dead tuples, freeze age, autovacuum progress | Tune thresholds/workers, targeted VACUUM |
| Capacity | Database/relation/tablespace/WAL/temp/backup bytes | Forecast, expand, retention/partition policy |
| Scheduler | Last success, duration, overlap, exit status | Controlled retries, alerts, and runbooks |
| Safety | Locks, latency, I/O, replication lag, disk reserve | Stop conditions, maintenance windows, post-checks |

Never run REINDEX, VACUUM FULL, or drop indexes just because a calendar reminder fired. Gather evidence, choose the right operation, and measure before/after impacts. Use growth snapshots to expand storage before running out of space, monitor WAL/slots to prevent disk exhaustion, and keep backup/restore verification independent from routine maintenance.

**An effective maintenance schedule is one where you can explain why every job runs, who owns it, how much resource it is permitted to consume, and what outcome proves the system is healthier afterward.**
# Scheduled Index, Statistics, and Capacity Maintenance in PostgreSQL

A PostgreSQL database requires continuous care so the query planner has accurate information, indexes perform efficiently, and storage retains enough headroom for workloads and maintenance operations. Waiting until users report slow queries or a volume fills up usually means issues have been accumulating for a long time.

Scheduled maintenance is how you organize recurring observations and actions: tracking index usage and state, maintaining planner statistics, observing autovacuum, recording capacity over time, checking WAL/backups, and forecasting storage needs. A good schedule is driven by workload and operational signals—not a list of commands run blindly regardless of whether the database needs them.

Tasks also carry varying levels of risk. Collecting metrics usually has minimal impact. ANALYZE reads data to update statistics. VACUUM cleans up reclaimable tuple versions. REINDEX or pg_repack can consume significant I/O and storage. VACUUM FULL requires strong locks and rewrites the table. Therefore, every job needs a purpose, time limit, owner, execution conditions, and verification method.

This lesson guides you through designing maintenance schedules for indexes, statistics, and capacity; selecting tasks based on evidence; scheduling with an appropriate scheduler; preventing overlapping runs; controlling locks/I/O/WAL; and building production runbooks.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between index maintenance, VACUUM, ANALYZE, and capacity management.
2. Capture baselines for table/index sizes and index usage.
3. Detect invalid indexes and signals requiring investigation.
4. Evaluate index usage without dropping an index based on a single counter.
5. Choose between REINDEX, REINDEX CONCURRENTLY, pg_repack, and alternative options.
6. Explain planner statistics and the role of ANALYZE/autoanalyze.
7. Tune analyze thresholds and statistics targets per table or column.
8. Monitor dead tuples, autovacuum, and transaction horizons.
9. Measure database, relation, tablespace, WAL, temporary files, and filesystem usage.
10. Store snapshots to calculate growth rates and forecast capacity.
11. Design daily, weekly, monthly, and event-driven maintenance schedules.
12. Execute maintenance via an OS scheduler or pg_cron according to permissions and version.
13. Prevent overlapping job executions and record job outcomes.
14. Manage lock timeouts, statement timeouts, I/O budgets, and rollbacks.
15. Design dashboards, alerts, runbooks, and 80 practice exercises.

## 2. Principles for Designing a Maintenance Schedule

An effective schedule combines regular checks with conditional actions.

### 2.1. Observe, Decide, Execute, Verify

An operational cycle can include:

1. **Observe:** collect sizes, statistics, index usage, dead tuples, query latency, and storage headroom.
2. **Decide:** identify meaningful signals and select necessary actions.
3. **Schedule:** choose timing, resource limits, owners, and stop conditions.
4. **Execute:** run jobs with logging and concurrency control.
5. **Verify:** check index state, query plans, statistics, disk, replication, and application behavior.
6. **Record:** store outcomes to compare against baselines and refine the schedule.

### 2.2. Not Every Task Runs on a Rigid Schedule

Autovacuum and autoanalyze are inherently automatic mechanisms driven by table activity. Capacity snapshots can run periodically. Index usage reviews can run weekly. REINDEX should run only when evidence shows it is needed. VACUUM FULL is not a default nightly task.

### 2.3. Separate Collection from Action

Metrics collection can typically run frequently with lower impact. Actions like REINDEX, rewrites, or retention changes require clear conditions and change control. Never let a bloat-detection query automatically fire REINDEX on every index exceeding an estimated threshold.

### 2.4. Schedules Depend on Workload

An append-only table, update-heavy table, partitioned event table, and lookup table have different maintenance needs. Choose cadence based on:
- Insert/update/delete rates.
- Table and index sizes.
- Query criticality and latency SLAs.
- Data skew levels.
- Transaction duration and replication topology.
- Storage throughput and maintenance windows.
- Backup, retention, and audit requirements.

### 2.5. Prioritize Data Safety and Availability

Never let index optimization delay anti-wraparound vacuum. Never run a rewrite without sufficient disk space. Never run heavy jobs concurrently with backups, bulk loads, and peak reporting if they contend for the same storage.

## 3. Maintenance Task Categories

| Category | Activities | How It Operates |
| --- | --- | --- |
| Index inventory | Size, usage, validity, dependencies | Collected periodically |
| Index maintenance | REINDEX, pg_repack, invalid index handling | Run only with evidence |
| Planner statistics | ANALYZE, autoanalyze, extended statistics | Based on modifications and query behavior |
| Tuple cleanup | VACUUM, autovacuum tuning | Automatic via PostgreSQL, monitored by DBA |
| Capacity | Database/table/index/tablespace/filesystem sizes | Snapshots and forecasting |
| WAL/replication | WAL rate, slot retention, archive lag | Continuous monitoring |
| Backup | Backup freshness, retention, restore tests | Per policy and DR schedule |
| Retention | Drop/detach partitions, archive old data | Per business/legal policy |
| Integrity | amcheck/pg_amcheck and restore validation | Per risk and maintenance window |

### 3.1. Periodic Checks Do Not Mean Changing Data

Inventories and metrics must not automatically drop indexes, drop partitions, or modify schemas. Actions affecting data or structures require approvals and dependency checks.

### 3.2. Event-Driven Maintenance

Certain tasks should be triggered after events:
- Bulk load completion: ANALYZE affected tables.
- New partition attached: update statistics and verify indexes.
- Major data distribution shift: ANALYZE or targeted statistics target increases.
- Extension/engine upgrade: check indexes, statistics, and compatibility.
- Backup restore rehearsal: measure restore time and storage headroom.

## 4. Capturing Size Baselines

Use bytes for calculations and formatted sizes only for display.

### 4.1. Database Size

~~~sql
SELECT
    datname,
    pg_database_size(oid) AS size_bytes,
    pg_size_pretty(pg_database_size(oid)) AS size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(oid) DESC;
~~~

Run the query in a database with appropriate permissions. Database size does not include other files on the filesystem such as logs, archive staging, or backup repositories.

### 4.2. Table and Index Size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_table_size(relid) AS table_bytes,
    pg_indexes_size(relid) AS index_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY total_bytes DESC
LIMIT 50;
~~~

pg_table_size includes table storage and TOAST/auxiliary forks, excluding indexes. pg_total_relation_size includes indexes as well.

### 4.3. Index Size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_relation_size(indexrelid) AS index_bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC
LIMIT 50;
~~~

### 4.4. Tablespace Size

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY pg_tablespace_size(oid) DESC;
~~~

Tablespace size and database size are overlapping views of the same relation files in many setups; do not sum both metrics to compute total disk usage.

### 4.5. Filesystem Capacity

PostgreSQL size functions do not replace filesystem metrics. Collect used/free bytes and inode availability for:
- PGDATA.
- pg_wal if on a separate volume.
- Every tablespace mount.
- PostgreSQL logs.
- Temporary and staging directories.
- WAL archive spool.
- Backup staging if on the same host.

On Linux, common tools are df -h and df -i. On managed PostgreSQL, use provider metrics for allocated/used/free storage and quotas.

### 4.6. Context-Rich Baselines

Each sample should store cluster/environment, database, timestamp, PostgreSQL version, bytes, host/volume identity, and stats reset time for cumulative counters. Never compare samples from two different clusters merely because database names match.

## 5. Index Usage and Inventory

PostgreSQL provides pg_stat_user_indexes to view usage counters per index.

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_relation_size(indexrelid) AS index_bytes
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC, index_bytes DESC;
~~~

### 5.1. Counter Meanings

- idx_scan: number of index scans initiated according to statistics.
- idx_tup_read: number of index entries returned by scans.
- idx_tup_fetch: number of live table rows fetched by simple index scans.

Counters are cumulative statistics that reset upon restarts or stats resets. Interpret them over a known observation window.

### 5.2. Low Index Scans Do Not Prove an Index Is Redundant

An index may be used rarely or seasonally, back a constraint, support foreign key checks, or serve a critical query. Inspect query logs, plans, constraints, and workload cycles before proposing a drop.

### 5.3. Constraint Indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Indexes backing a PRIMARY KEY or UNIQUE constraint must not be removed simply because idx_scan is low. Review constraint definitions and dependencies first.

### 5.4. Invalid Indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY 1, 2, 3;
~~~

Failed or canceled concurrent index builds can leave behind invalid indexes. Inventories should flag these indexes so DBAs can inspect root causes and remediation options.

### 5.5. Indexes per Table

Having many indexes on a table increases storage, cache pressure, and write amplification. Cross-check each index against query patterns, constraint requirements, and write costs. Do not drop an index just because one query sample did not use it.

### 5.6. Index Health Evidence

Combine:
- Size and size growth.
- idx_scan/idx_tup_read/idx_tup_fetch.
- Constraint/dependency details.
- Query plans and latency.
- B-tree page statistics if suitable tools are available.
- Invalid/corruption checks.
- WAL generation and write workload.

## 6. When Is REINDEX Needed?

REINDEX rebuilds an index from current table data. It can reclaim index bloat or fix certain index states, though it is not a mandatory fixed-schedule task.

### 6.1. Signals Warranting Investigation

- An index grows faster than table data without explanation.
- Substantial bloat is evidenced.
- An index is invalid following a failed operation.
- Index corruption or check tool errors are reported.
- An index is scheduled for rebuild under a measured maintenance plan.
- Query performance changes and evidence points to index structure as a contributing factor.

### 6.2. Standard REINDEX

~~~sql
REINDEX INDEX app.orders_customer_id_idx;
~~~

Standard REINDEX can acquire strong locks that impact concurrent access. Check lock behavior for the object type and PostgreSQL version, then schedule a maintenance window.

### 6.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;
~~~

Concurrent mode reduces blocking for normal workloads but runs in multiple phases, taking more time and I/O. It does not mean lock-free or immune to failure.

### 6.4. Constraints of Concurrent Mode

- Cannot run inside a transaction block.
- May not support certain relation types or objects in specific versions.
- Can leave behind an invalid index if the operation fails.
- Requires extra storage while building the new index.
- Must monitor locks and progress.
- Check documentation for your exact major version before automating.

### 6.5. REINDEX TABLE and DATABASE

REINDEX TABLE affects all indexes on a table. REINDEX DATABASE affects indexes across the current database and carries a much larger blast radius. Avoid wide-scope scheduled runs if only a few indexes have issues.

### 6.6. Partitioned Table Indexes

For partitioned indexes, verify version support and individual partition states. Some concurrent reindex operations on parent partitioned indexes have limitations; leaf indexes may need individual handling per runbook.

## 7. pg_repack and Reorganization Alternatives

pg_repack is an external tool/extension that can reorganize tables or indexes with shorter blocking windows than traditional rewrite methods. It has prerequisites, lock phases, triggers/log tables, and notable disk requirements.

### 7.1. When to Consider It?

- Bloat is confirmed.
- Regular VACUUM does not return file size to the OS.
- The maintenance window cannot tolerate a prolonged ACCESS EXCLUSIVE lock like VACUUM FULL.
- Sufficient disk headroom and version/tool compatibility exist.
- Rehearsed on a clone.

### 7.2. Disk Overhead

Reorganization typically builds a new copy while the old relation remains in place. Account for space for the table, indexes, temporary/logging objects, and WAL. Do not run when a volume is nearly full.

### 7.3. Not a Lock-Free Solution

pg_repack still requires locks during certain phases and can be blocked by long transactions. Read the documentation for your exact version and check active sessions.

### 7.4. VACUUM FULL

~~~sql
VACUUM (FULL, ANALYZE) app.orders;
~~~

VACUUM FULL rewrites the table, returning excess storage to the filesystem upon completion, but requires an ACCESS EXCLUSIVE lock and extra disk space. Run only in approved windows with sufficient headroom and a rollback/recovery plan.

### 7.5. Standard VACUUM

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

Standard VACUUM cleans reclaimable dead tuples and makes space reusable internally. It does not typically shrink relation files significantly; do not schedule VACUUM FULL solely because standard VACUUM does not reduce file size.

## 8. Checking Index Integrity

Index size and usage alone cannot confirm an index is free of corruption. For B-tree indexes, PostgreSQL provides the amcheck extension and the pg_amcheck command-line utility on supported versions.

### 8.1. amcheck

Install the extension per policy:

~~~sql
CREATE EXTENSION amcheck;
~~~

Functions check B-tree structures at different levels. Check version documentation to select the right function, permissions, and lock behavior.

### 8.2. pg_amcheck

pg_amcheck is a client utility with version-specific options for checking databases, schemas, tables, and indexes. Run against appropriate databases with required privileges, scoping targets and monitoring I/O.

### 8.3. Inspection Frequency

Choose based on criticality, storage reliability, change rate, and assurance requirements. You do not necessarily need high-frequency full scans of every huge index if the overhead is prohibitive.

### 8.4. Corruption Response

If corruption is detected:
1. Preserve logs and evidence.
2. Identify the object, extent, and failure scope.
3. Inspect storage, kernel, and hardware logs.
4. Verify backups can be restored.
5. Consult PostgreSQL/vendor guidance.
6. Only REINDEX or restore once you know whether corruption is isolated to the index or affects heap/data files too.

REINDEX can rebuild a damaged index if underlying table data is intact; it cannot repair corruption in the heap or storage layer.

## 9. Planner Statistics and ANALYZE

Planner statistics help PostgreSQL estimate cardinality and selectivity to choose execution plans. When data changes significantly, outdated statistics can lead the planner to select suboptimal scans, join orders, or join methods.

### 9.1. ANALYZE

~~~sql
ANALYZE app.orders;
~~~

ANALYZE samples the table and updates statistics in system catalogs. It can run on a table or specific columns.

~~~sql
ANALYZE app.orders (customer_id, status, created_at);
~~~

### 9.2. ANALYZE VERBOSE

~~~sql
ANALYZE (VERBOSE) app.orders;
~~~

VERBOSE outputs useful processing details in logs or client output. ANALYZE consumes I/O and CPU but generally does not require exclusive locks that block normal DML.

### 9.3. Autoanalyze

The autovacuum launcher also triggers autoanalyze based on modification counters and thresholds. On high-churn tables, autoanalyze may run frequently; on very large tables, the default scale factor may delay the next analyze too long.

### 9.4. Monitoring Analyze State

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 50;
~~~

Columns and counter semantics can differ across versions. n_live_tup and n_mod_since_analyze are estimates/statistics, not exact row counts.

### 9.5. Autoanalyze Thresholds

Autoanalyze thresholds typically combine an absolute base threshold with a fraction of estimated rows. Common settings are autovacuum_analyze_threshold and autovacuum_analyze_scale_factor.

~~~sql
ALTER TABLE app.orders
SET (
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

This example demonstrates per-table configuration. Choose values based on modifications, table size, and query plan sensitivity.

### 9.6. Statistics Target

default_statistics_target governs default granularity. A custom target can be set for a skewed column or one heavily influencing query plans:

~~~sql
ALTER TABLE app.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE app.orders (status);
~~~

Higher targets can improve estimates while increasing sampling work and catalog statistics size. Do not raise cluster-wide defaults if only a few columns need it.

### 9.7. Extended Statistics

When multiple columns are correlated, independent single-column statistics may misrepresent the joint distribution.

~~~sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, ndistinct, mcv)
ON customer_id, status
FROM app.orders;

ANALYZE app.orders;
~~~

Select extended statistics types based on actual predicates and groupings. Extended statistics do not replace every form of cardinality estimation.

### 9.8. After Bulk Loads or Data Redistribution

After large imports, partition attachments, or distribution shifts, run ANALYZE on relevant tables/columns before sending critical workloads. Compare EXPLAIN plans and estimated rows against baselines.

## 10. Autovacuum in the Maintenance Schedule

Autovacuum requires continuous monitoring. DBA schedules should tune thresholds and capacity to the workload rather than replacing autovacuum with a periodic VACUUM ALL.

### 10.1. Dead Tuple Estimates

~~~sql
SELECT
    schemaname,
    relname,
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
LIMIT 50;
~~~

Dead tuple percentages are estimates. Use them to prioritize inspections, not as exact byte-level bloat measurements.

### 10.2. Per-Table Vacuum Thresholds

~~~sql
ALTER TABLE app.events
SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

This is an example for a write-heavy table. Benchmark worker throughput, I/O, vacuum duration, and query latency before applying broadly.

### 10.3. Worker Capacity

Settings such as autovacuum_max_workers, autovacuum_naptime, autovacuum_vacuum_cost_limit, autovacuum_vacuum_cost_delay, and autovacuum_work_mem affect catch-up ability. Increasing workers can raise I/O contention.

### 10.4. Long Transactions

Long transactions or old snapshots can hold back dead tuple reclamation needed by that snapshot, blocking vacuum progress. Track xact_start, backend_xmin, and replication slot xmin.

### 10.5. Freezing and Wraparound

Monitor transaction ID age:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Anti-wraparound vacuum is a critical availability concern. When approaching warning thresholds, prioritize freeze processing over non-urgent index maintenance.

### 10.6. VACUUM and the Filesystem

VACUUM typically makes space reusable inside the relation; file sizes do not usually shrink proportionally. Only appropriate rewrite or compaction returns most storage to the filesystem. Account for locks and extra disk before running.

## 11. Monitoring Storage and Growth

Capacity reviews should track multiple layers:

- Heap/table and TOAST.
- Indexes.
- Tablespaces and filesystem volumes.
- pg_wal and archive backlog.
- Temporary files.
- Replication slot retained WAL.
- Logs and audit files.
- Backup repositories and restore staging.
- Headroom for REINDEX/rewrites/bulk loads.

### 11.1. Database Snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    datname,
    pg_database_size(oid) AS size_bytes
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

### 11.2. Relation Snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_relation_size(c.oid) AS main_bytes,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'i', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

Partitioned parents do not hold the data pages of their partitions. Inventories must measure leaf partitions and avoid double-counting parent/child relations.

### 11.3. WAL Retention

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS wal_distance_estimate
FROM pg_replication_slots
ORDER BY slot_name;
~~~

LSN distance is only an estimate, not the exact bytes exclusively occupied by the slot. Inspect archive failures, consumer health, and filesystem metrics before acting on slots.

### 11.4. Temporary Writes

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

temp_bytes is a cumulative counter since stats reset, not the amount of temporary files sitting on disk at query time. Compute deltas over time and combine with log_temp_files and query statistics.

### 11.5. Growth Rate

Given two snapshots separated by Δt seconds:

\[
\text{growth bytes/sec} =
\frac{\text{new size bytes} - \text{old size bytes}}{\Delta t}
\]

Keep negative deltas if objects were dropped, truncated, or rewritten. When forecasting, use rolling averages or percentiles long enough to capture workload peaks.

### 11.6. Time to Reserve

If a volume has F bytes free, requires R bytes in reserve, and experiences net growth G bytes/day:

\[
\text{days to reserve} = \frac{F-R}{G}
\]

Compute only when G is positive and F exceeds R. This is a linear estimate; factor in bursts, seasonality, provisioning lead times, and maintenance headroom.

### 11.7. Do Not Double-Count Overlapping Layers

pg_database_size, pg_tablespace_size, and relation sizes are overlapping views. Use them for breakdowns, not arbitrary addition. Filesystem or provider metrics remain the source of truth for actual free bytes.

## 12. Snapshot Store and Retention

Capacity samples can be stored in a monitoring database or metrics platform. If stored inside the measured cluster, control retention so monitoring tables do not grow unbounded.

~~~sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE monitoring.database_size_samples (
    sampled_at timestamptz NOT NULL,
    cluster_name text NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, cluster_name, database_name)
);
~~~

Saving a sample:

~~~sql
INSERT INTO monitoring.database_size_samples (
    sampled_at,
    cluster_name,
    database_name,
    size_bytes
)
SELECT
    clock_timestamp(),
    'production-primary',
    datname,
    pg_database_size(oid)
FROM pg_database
WHERE datallowconn;
~~~

### 12.1. Calculating Deltas

~~~sql
WITH samples AS (
    SELECT
        cluster_name,
        database_name,
        sampled_at,
        size_bytes,
        lag(sampled_at) OVER (
            PARTITION BY cluster_name, database_name
            ORDER BY sampled_at
        ) AS previous_at,
        lag(size_bytes) OVER (
            PARTITION BY cluster_name, database_name
            ORDER BY sampled_at
        ) AS previous_bytes
    FROM monitoring.database_size_samples
)
SELECT
    cluster_name,
    database_name,
    sampled_at,
    size_bytes - previous_bytes AS delta_bytes,
    extract(epoch FROM sampled_at - previous_at) AS elapsed_seconds,
    (size_bytes - previous_bytes)
        / NULLIF(extract(epoch FROM sampled_at - previous_at), 0)
        AS bytes_per_second
FROM samples
WHERE previous_at IS NOT NULL
ORDER BY sampled_at DESC;
~~~

### 12.2. Counter Resets

For `pg_stat_database` or `pg_stat_wal`, store `stats_reset`. If the reset timestamp changes, do not compute deltas across two different counter epochs.

### 12.3. Retention

Keep raw samples long enough for incident analysis, then roll up hourly/daily/weekly aggregates per policy. Historical data helps identify seasonal growth and evaluate forecast accuracy.

### 12.4. Relation Lifecycle

Relations can be renamed, dropped, or recreated. If tracking history by object identity, store database identity and OID alongside schema/name, plus lifecycle events. OIDs can also be reused over time, so they are not permanent identifiers.

## 13. Sample Maintenance Schedule

The table below is a starting point; adapt it to workload, SLAs, maintenance windows, and capacity.

| Reference Frequency | Task | Condition / Output |
| --- | --- | --- |
| Continuous | Autovacuum, autoanalyze, replication/archive monitoring | Monitor health and backlogs |
| Every 5–15 minutes | Storage, WAL, replication lag, backup health metrics | Early alerts |
| Daily | Database/table size snapshots, xid age, long transactions, failed jobs | Capacity and risk reports |
| Weekly | Index usage/invalid index review, analyze freshness, dead tuple review | List of objects to investigate |
| Monthly | Bloat sampling, index integrity sampling, growth forecast, restore evidence review | Conditional maintenance plan |
| After bulk load | ANALYZE affected tables, verify query plans | Fresh planner stats |
| After partition change | Verify partition indexes, ANALYZE, retention inventory | Consistent partition tree |
| Per change window | Approved REINDEX/pg_repack/rewrite | Pre/post metrics captured |
| Per DR policy | Backup restore/PITR rehearsal | Proven recoverability |

### 13.1. Daily Checks

Daily jobs should prioritize lightweight inventories, capacity snapshots, transaction age, replication slots, archive status, and backup freshness. Avoid full index scans or heavy bloat estimation on every relation daily.

### 13.2. Weekly Checks

Review fast-growing indexes, invalid indexes, statistics freshness, autovacuum history, and query regressions. Index remediation requires separate tickets/runbooks.

### 13.3. Monthly/Quarterly Checks

Select sample relations for bloat/integrity assessment, review growth forecasts, storage quotas, retention policies, restore drills, and extension/index maintenance needs. Critical systems may require a different cadence.

### 13.4. Event-Driven Checks

After major imports, migrations, partition attach/detach, schema changes, or upgrades, run the relevant affected checks immediately instead of waiting for next week's schedule.

## 14. Planning Maintenance Windows

A maintenance window should specify:
- Start/end times and timezone.
- Permitted tasks.
- Database/table/index scope.
- Expected duration.
- Owner and on-call contact.
- Lock and statement timeouts.
- Disk and WAL headroom.
- Replication and backup state.
- Stop conditions.
- Verification and rollback/recovery procedures.

### 14.1. Do Not Stack Multiple I/O-Heavy Jobs

Avoid running large REINDEX jobs, bulk imports, full backups, and storage migrations concurrently on the same volume unless benchmarked. Operations can contend for CPU, IOPS, throughput, and WAL capacity.

### 14.2. Lock Timeout

Set a `lock_timeout` for maintenance sessions so jobs do not wait indefinitely on locks:

~~~sql
SET lock_timeout = '5s';
REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;
~~~

Values are illustrative. Too low a lock timeout can cause frequent job failures; too high can prolong blocking queues.

### 14.3. Statement Timeout

`statement_timeout` bounds statement runtime. Choose based on expected duration and rollback cost. For long operations, setting it too low can cancel the job and leave cleanup work behind.

### 14.4. VACUUM Outside Transaction Blocks

VACUUM cannot run inside a transaction block. When scheduling, execute directly via an appropriate client command/job; do not wrap VACUUM in a normal function or DO block.

### 14.5. REINDEX CONCURRENTLY Outside Transaction Blocks

REINDEX CONCURRENTLY also cannot run inside a transaction block. Schedulers must send the statement without wrapping the whole job in BEGIN/COMMIT.

### 14.6. Stop Conditions

Examples:
- Free space falls below reserve.
- Replication lag exceeds RPO budget.
- Application p99 latency crosses stop threshold.
- Lock wait queues grow abnormally.
- Backups or archiving are failing.
- Job makes no progress or exceeds runtime budget.

## 15. Choosing a Scheduler

You can use an OS scheduler, an orchestration platform, or pg_cron. Pick a mechanism suited to your architecture with clear ownership.

### 15.1. OS Scheduler

Cron, systemd timers, or Windows Task Scheduler can invoke `psql` or scripts. The advantage is keeping job orchestration decoupled from the database; you must manage credentials, networking, client versions, logs, and retries.

### 15.2. pg_cron

pg_cron is a scheduler extension running SQL jobs on a schedule. Install the compatible package, configure per extension documentation, create the extension in the appropriate database, and grant privileges to job owners. Some configurations require `shared_preload_libraries` and a restart.

### 15.3. Job Identity

Each job should run under a dedicated role with privileges limited to reading metrics or performing specific maintenance. Do not run all maintenance schedulers as superuser unless required.

### 15.4. Managed PostgreSQL

Some providers support pg_cron or proprietary schedulers with allowlists and parameter requirements. Verify service capabilities before designing.

### 15.5. A Single Source of Schedule Truth

Avoid scheduling the same job in both cron and pg_cron. Maintain an inventory listing job name, schedule, owner, command, timezone, timeout, concurrency policy, and log destination.

## 16. Preventing Overlapping Jobs

If a job takes longer than its interval, the next run might start while the previous one is still running, depending on the scheduler.

### 16.1. Scheduler Concurrency Policies

Use scheduler settings to restrict each job to one active instance. For pg_cron, read version-specific behavior and connection handling; do not assume all jobs share identical concurrency semantics.

### 16.2. Advisory Locks

A script can acquire an advisory lock before executing a job. Keep the same session connection throughout the job and release the lock upon completion. If the connection closes, session-level advisory locks are released.

### 16.3. Lock Keys

Choose stable keys per job/cluster so competing instances contend for the same lock. Log when lock acquisition fails and mark the job skipped/overlap—do not report it as success.

### 16.4. Do Not Wrap Maintenance in a Transaction

Advisory locks do not require a long transaction. For VACUUM or REINDEX CONCURRENTLY, design the runner to hold a session-level lock while sending individual commands outside any transaction block.

### 16.5. Leases and Stale State

If using an external lock/lease table, handle worker crashes, lease expiration, clock skew, and job ownership. Advisory locks are usually simpler when all workers connect to the same PostgreSQL cluster.

## 17. Logging and Tracking Job Runs

A job should never merely return an exit code without storing its result.

~~~sql
CREATE SCHEMA IF NOT EXISTS maintenance;

CREATE TABLE maintenance.job_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL,
    executor text,
    target_object text,
    rows_or_objects bigint,
    details text,
    error_text text
);
~~~

### 17.1. Job Metadata

Record job name, run ID, start/end timestamps, duration, executor role, database, object scope, status, error code/message, and links to logs.

### 17.2. Do Not Store Secrets

Never write connection passwords, tokens, or sensitive query literals into maintenance tables or logs.

### 17.3. Exit Status

Scripts must return unambiguous exit statuses so the scheduler knows success vs. failure. `psql` can use `ON_ERROR_STOP` to halt on SQL errors.

### 17.4. Retry Policy

Inventory queries are generally safe to retry. DDL and maintenance actions must check server state before retrying; a client timeout does not prove the server operation stopped.

### 17.5. Idempotency

Each job must verify current state before acting. For example, never blindly drop/recreate an index simply because the previous job run failed to write its final log entry.

## 18. Example: Running Maintenance from psql

An OS scheduler script can invoke `psql` using a configured connection service or credential store.

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "ANALYZE app.orders;"
~~~

Never put passwords directly on command lines or in script repositories. Use `.pgpass` with strict permissions, service files, a secret manager, or provider identity mechanisms.

### 18.1. Running Multiple Commands

Give each operation its own target and logging. Do not chain multiple destructive actions together without checkpoints and verification.

### 18.2. VACUUM

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "VACUUM (ANALYZE, VERBOSE) app.orders;"
~~~

### 18.3. REINDEX CONCURRENTLY

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;"
~~~

Ensure the client/session does not wrap the command in a transaction block and that the server version supports the operation.

### 18.4. Connection Identity

Set a dedicated `application_name` for maintenance jobs so DBAs can identify them in `pg_stat_activity`. Use a dedicated role with restricted database/schema privileges.

## 19. Targeted ANALYZE Scheduling

ANALYZE does not necessarily need to run across the entire database every night. Select tables based on modification counters, bulk loads, and query plan evidence.

### 19.1. High-Churn Tables

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_autoanalyze,
    last_analyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

### 19.2. After Bulk Loads

Run ANALYZE on newly imported tables, especially if row distributions shifted markedly. When multiple new partitions are attached, determine whether leaf partitions, parent statistics, or both need analyzing based on version and planner behavior.

### 19.3. Column-Specific Analyze

Run ANALYZE on columns affecting predicates and joins when needed. If raising a statistics target, document the reason and corresponding query patterns.

### 19.4. Verifying the Planner

Use `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment to compare estimated rows against actual rows. `EXPLAIN ANALYZE` executes the statement; run it only on safe queries with full awareness of its impact.

### 19.5. Avoid Continuous Analyzing

Running ANALYZE too frequently wastes I/O and CPU and can cause statistics churn. Base frequency on modification rates and planner regressions.

## 20. Targeted Index Review Scheduling

A weekly index review can produce a report without automatically reindexing.

### 20.1. Size and Usage Report

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    pg_relation_size(s.indexrelid) AS size_bytes,
    i.indisprimary,
    i.indisunique,
    i.indisvalid
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i ON i.indexrelid = s.indexrelid
ORDER BY size_bytes DESC;
~~~

### 20.2. Comparing Over Time

Store counters and size snapshots. Compute deltas between samples within the same stats epoch. When stats reset, start a new baseline.

### 20.3. Reviewing Index Candidates

Flag indexes with large size, low usage, or invalid status for review. Inspect query logs, constraints, foreign keys, and seasonal workloads before deciding.

### 20.4. REINDEX Candidates

Create a ticket containing:
- Index and table name.
- Current size.
- Evidence of bloat or corruption.
- Expected benefit.
- Disk headroom.
- Lock mode and duration.
- Replication and WAL impact.
- Maintenance window.
- Verification and rollback plan.

## 21. Integrity Checks and amcheck Schedules

For critical databases, place index integrity checks on a risk-based schedule.

### 21.1. Choosing Scope

Prioritize indexes on critical tables, recently rebuilt indexes, storage that experienced errors, or objects showing corruption symptoms.

### 21.2. pg_amcheck

`pg_amcheck` is a client tool with version-dependent options to verify databases, schemas, tables, and indexes. Run with appropriate concurrency and I/O limits.

### 21.3. amcheck Functions

The `amcheck` extension provides functions to verify index structures. Function names and lock requirements vary by version and mode.

### 21.4. Abnormal Results

Preserve logs and identify the object and failure scope. Do not automatically reindex everything after a generic warning; verify using PostgreSQL guidance and storage evidence.

## 22. Capacity Snapshots and Forecasting

### 22.1. Storing Database Sizes

Create an external metrics store or monitoring table with retention:

~~~sql
CREATE TABLE maintenance.database_size_samples (
    sampled_at timestamptz NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, database_name)
);
~~~

### 22.2. Calculating Growth Rate

If size grows from S1 to S2 over Δt seconds:

\[
\text{bytes per day} =
\frac{S_2-S_1}{\Delta t} \times 86400
\]

Store bytes and timestamps; never compute from `pg_size_pretty` strings.

### 22.3. Forecasting to Reserve

\[
\text{days to reserve} =
\frac{\text{free bytes}-\text{reserve bytes}}
{\text{positive growth bytes/day}}
\]

Use rolling averages or percentiles and model peak/batch scenarios. Linear forecasts cannot predict abrupt workload shifts.

### 22.4. Maintenance Headroom

Budget extra disk space for:
- REINDEX or concurrent index builds.
- VACUUM FULL / CLUSTER.
- `pg_repack` shadow tables and indexes.
- Bulk imports and sort spills.
- Backup/restore staging.
- WAL archive backlogs and replication slots.

### 22.5. Volume-Specific Forecasts

If tablespaces or `pg_wal` reside on separate volumes, forecast each mount individually. Overall database size may appear stable while one specific volume is nearing full.

## 23. Monitoring WAL, Replication, and Archiving

### 23.1. WAL Generation

On versions with `pg_stat_wal`:

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Compute deltas of `wal_bytes` over time to derive the WAL generation rate. Record `stats_reset` to track counter epochs.

### 23.2. Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Inactive slots can retain WAL. Verify owners, consumers, and recovery plans before dropping any slot.

### 23.3. Archive Status

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Archive failures can cause WAL buildup. Check logs, destination capacity, permissions, and retry behavior.

### 23.4. Replication Lag

Read `pg_stat_replication` on the primary alongside appropriate subscriber/standby metrics. A maintenance job generating heavy WAL can increase replica lag and retain additional WAL.

### 23.5. Capacity Gate

Never start a major REINDEX or rewrite if WAL volume, archiving, or replication is already near critical thresholds without sufficient headroom.

## 24. Backups and Restores in the Maintenance Schedule

Backups are part of the maintenance program. A successful backup job does not prove a restore will succeed.

### 24.1. Backup Freshness

Monitor last successful backup, duration, size, WAL archive continuity, retention, and destination capacity.

### 24.2. Restore Verification

On your DR schedule, restore a backup into an isolated environment, replay WAL if needed, and verify the database opens, extensions, roles, critical queries, and application-level consistency.

### 24.3. Maintenance and Backup Contention

REINDEX, bulk loads, VACUUM FULL, or pg_repack can increase I/O and WAL and prolong backups. Do not overlap them unless storage budgets have been benchmarked.

### 24.4. Backup Before Destructive Maintenance

Before DROP/partition retention actions or major rewrites, verify the backup/PITR chain and retention/legal requirements. Backups do not replace reviewing object dependencies.

## 25. Retention and Partition Maintenance

For time-series or event data, partitioning makes retention far more efficient than row-by-row deletion.

### 25.1. Partition Lifecycle

Schedule:
- Creating future partitions.
- Verifying partition bounds.
- Attaching partitions after validation.
- Analyzing affected relations.
- Detaching/dropping expired partitions per policy.
- Updating inventory and backup retention.

### 25.2. Dropping Partitions

DROP/DETACH frees storage far faster than deleting millions of rows, but it is a destructive data change. Verify business retention, foreign keys, replication/publications, and downstream consumers.

### 25.3. Default Partition Growth

Monitor the default partition. If routing fails or future partitions are missing, the default partition can grow unexpectedly fast.

### 25.4. Partition Indexes

Verify new partition indexes match the parent partitioned index and application query needs. Check for invalid or incomplete index attachments.

## 26. Designing Maintenance Jobs by Type

### 26.1. Inventory Jobs

Read metrics only, write snapshots, and produce reports. These can run more frequently if query overhead is low.

### 26.2. Analyze Jobs

Select tables needing analysis from modification counters, bulk-load events, or query plan evidence. Run using a role with appropriate privileges.

### 26.3. Vacuum Jobs

Prefer autovacuum. Run manual VACUUM only with a clear target, such as after bulk deletes or maintenance events. Do not replace autovacuum with an uncontrolled nightly full sweep.

### 26.4. Index Jobs

Review candidates first. Reindex per object or bounded batch, avoiding cluster-wide reindexing just because a schedule fired.

### 26.5. Capacity Jobs

Collect database, relation, tablespace, WAL, filesystem, and backup metrics. Compute growth rates and forecasts. Never use SQL size functions to infer filesystem free space.

### 26.6. Integrity Jobs

Run `amcheck`/`pg_amcheck` based on risk, throttle I/O, and store results. Have an incident procedure ready if errors surface.

## 27. Privileges and Security for Maintenance

Create dedicated roles for each category of tasks.

| Role | Required Privileges |
| --- | --- |
| maintenance_monitor | Read activity, statistics, and necessary metrics |
| maintenance_analyzer | Privileges required to ANALYZE tables in scope |
| maintenance_operator | Run approved VACUUM/REINDEX operations |
| capacity_collector | Read sizes, catalogs, and provider metrics |
| backup_operator | Execute backup/restore per policy |
| database_owner | Manage objects/schemas per responsibility |

### 27.1. Least Privilege

Do not run every job as superuser. Some operations require owner, superuser, or predefined roles; grant privileges narrowly by scope and version.

### 27.2. Credentials

Use secret managers, service files, or suitable identity mechanisms. Never store passwords in cron lines, repositories, or logs.

### 27.3. Application Name

Set `application_name` on jobs to identify them in `pg_stat_activity` and logs.

### 27.4. Auditing

Record actor, timestamp, command/object scope, change reference, and result. Prevent query text and secret leakage.

## 28. Troubleshooting: Blocked Maintenance Job

1. Identify the job's PID and `application_name`.
2. Check state, query age, transaction age, and wait events.
3. Use `pg_blocking_pids` to find blockers.
4. Inspect blocker state and transaction age.
5. Determine whether the job needs to continue within the window.
6. Contact the blocker owner or reschedule.
7. Only cancel/terminate per incident policy.
8. Confirm job state and retry safety before re-running.

Never cancel a job simply because runtime exceeded expectations; first determine whether it is making progress or waiting on a lock.

## 29. Troubleshooting: REINDEX Failed

Causes may include lock timeout, insufficient disk, concurrent build conflicts, cancellation, server restart, or corruption.

Procedure:
1. Check server/client logs and identify the phase.
2. Check index validity and readiness.
3. Check filesystem and WAL headroom.
4. Identify concurrent sessions and blockers.
5. Verify application queries and constraints.
6. Follow supported cleanup and retry procedures.
7. Do not manually drop an index if it backs a constraint.
8. Re-run verification and query plan tests.

## 30. Troubleshooting: Planner Chooses Bad Plan After Maintenance

1. Collect `EXPLAIN (ANALYZE, BUFFERS)` if the query is safe.
2. Compare estimated rows with actual rows.
3. Check `last_analyze`/`autoanalyze` and modification counters.
4. Check statistics targets and data skew.
5. Check extended statistics if columns are correlated.
6. Check parameter values, `search_path`, and prepared statement behavior.
7. Run targeted ANALYZE if stats are stale.
8. Compare plans and latency after changes.

Do not create a new index solely because the planner chose a sequential scan; a sequential scan may be optimal when a query reads most of the table.

## 31. Troubleshooting: Rapid Storage Growth

1. Identify which volume/mount is actually growing.
2. Compare database and relation size snapshots.
3. Rank tables, indexes, and partitions by delta.
4. Check the WAL directory, slots, and archive backlog.
5. Check temporary files and query spills.
6. Check logs, backups, and staging files.
7. Check dead tuples, autovacuum, and transaction horizons.
8. Determine whether growth comes from business data, bloat, WAL, or artifacts.
9. Expand the volume or reduce the exact source of growth per runbook.
10. Verify free space and recovery health afterward.

## 32. Scheduling by Environment

### 32.1. Development

Inventories can run frequently and maintenance operations can be tested on small datasets. Never use development schedules as production defaults.

### 32.2. Staging

Use staging to rehearse job schedules, permissions, locks, runtimes, disk headroom, and failure/retry behavior on representative data.

### 32.3. Production

Pin job versions, change windows, owners, timeouts, concurrency policies, and alerts. Monitor impact on application SLOs.

### 32.4. Multi-Region / HA

Clarify whether maintenance runs on the primary or standbys. Never run DDL or reindexing simultaneously across all nodes if the operation is not designed for that topology. Keep packages/configs synchronized and verify failover readiness.

## 33. Reviewing and Refining Schedules

Monthly or quarterly, evaluate:
- Which jobs consistently run unnecessarily?
- Which jobs are frequently skipped due to locks?
- Are durations growing alongside data size?
- Which jobs contend with backups or batch workloads?
- Did index candidates genuinely improve after REINDEX?
- Did ANALYZE reduce cardinality estimation errors?
- Is autovacuum keeping up with churn?
- How accurate were capacity forecasts?
- Are restore drills meeting RTO/RPO?
- Are there duplicate jobs across scheduler systems?

Schedules should evolve whenever workloads, data volumes, SLAs, or storage architectures change.

## 34. PostgreSQL Practice Exercises

Perform these in a lab, staging, or authorized environment. Never run destructive operations, VACUUM FULL, or large REINDEX jobs in production merely for experimentation.

1. **Inventory:** list databases and sizes using `pg_database_size`.
2. **Tables:** list the 50 largest tables.
3. **Indexes:** list the 50 largest indexes.
4. **Breakdown:** compare `pg_table_size`, `pg_indexes_size`, and `pg_total_relation_size`.
5. **Tablespaces:** list tablespace locations and sizes.
6. **Filesystem:** collect free bytes and inode availability from the host or provider.
7. **Index usage:** read `idx_scan`, `idx_tup_read`, and `idx_tup_fetch`.
8. **Stats reset:** determine when statistics were last reset.
9. **Unused candidates:** generate a report of indexes with `idx_scan` equal to zero.
10. **Constraint review:** identify indexes backing primary or unique constraints.
11. **Invalid indexes:** find indexes with `indisvalid=false`.
12. **Index growth:** store two size snapshots and calculate the delta.
13. **Index bloat:** research an estimation method and its limitations.
14. **amcheck:** install the extension in a lab and run a supported integrity check.
15. **pg_amcheck:** run the tool with a bounded scope.
16. **REINDEX:** reindex a lab index and compare before/after sizes.
17. **REINDEX CONCURRENTLY:** test the operation and observe phases and locks.
18. **Transaction block:** test why `REINDEX CONCURRENTLY` cannot run inside a transaction block.
19. **Invalid cleanup:** simulate a failed concurrent build and document the remediation steps.
20. **pg_repack:** rehearse on a clone if the tool is supported.
21. **VACUUM:** run standard VACUUM and observe dead tuples.
22. **VACUUM FULL:** run on a small lab table and measure lock and disk overhead.
23. **ANALYZE:** run `ANALYZE VERBOSE` on a table.
24. **Autoanalyze:** observe autoanalyze counters and timestamps.
25. **Modification count:** rank tables by `n_mod_since_analyze` if supported by your version.
26. **Analyze threshold:** tune per-table analyze scale factors in the lab.
27. **Statistics target:** increase the target on a skewed column and measure analyze and query planning.
28. **Extended statistics:** create dependencies/ndistinct/MCV stats.
29. **Plan comparison:** compare estimated rows before and after ANALYZE.
30. **Bulk load:** import rows and ANALYZE the affected table.
31. **Partition analyze:** create a new partition and determine which statistics need updating.
32. **Dead tuples:** rank tables by `n_dead_tup`.
33. **Autovacuum history:** inspect `last_autovacuum` and `vacuum_count`.
34. **Per-table vacuum:** configure thresholds on a write-heavy table in the lab.
35. **Worker capacity:** inspect `autovacuum_max_workers` and cost settings.
36. **Long transaction:** create a long transaction and observe the vacuum horizon.
37. **XID age:** rank databases by `age(datfrozenxid)`.
38. **WAL slots:** inventory replication slots and retained WAL estimates.
39. **Database snapshot:** create the `database_size_samples` table.
40. **Growth rate:** calculate bytes/day from two snapshots.
41. **Time to reserve:** calculate days until reaching the reserve threshold.
42. **Relation snapshot:** store table and index sizes per relation.
43. **Partition growth:** find the partition with the largest growth.
44. **Tablespace alert:** design per-volume alerts.
45. **Temporary files:** read `temp_files`/`temp_bytes` and calculate rates.
46. **Archive:** read `pg_stat_archiver` and alert on failures.
47. **Backup freshness:** generate a report of last successful backups per policy.
48. **Restore drill:** restore a backup into staging and record runtime.
49. **Job inventory:** list jobs, owners, schedules, and commands.
50. **Cron:** create an inventory job triggered via OS scheduler.
51. **pg_cron:** install/configure `pg_cron` in a lab if supported.
52. **Permissions:** create a `maintenance_monitor` role with read-only metrics access.
53. **Analyzer role:** design privileges for a role running ANALYZE.
54. **Operator role:** identify privileges needed for REINDEX/VACUUM.
55. **Credentials:** configure a `psql` service/secret store without hard-coding passwords.
56. **Application name:** set `application_name` for a maintenance runner.
57. **Job logs:** create the `maintenance.job_runs` table.
58. **Exit status:** configure `psql` `ON_ERROR_STOP` and verify scheduler results.
59. **Overlap:** simulate a long-running job and prevent a second instance from starting.
60. **Advisory lock:** use a session-level advisory lock in a runner.
61. **VACUUM runner:** run VACUUM directly outside any transaction block.
62. **REINDEX runner:** run `REINDEX CONCURRENTLY` with proper session/transaction handling.
63. **Lock timeout:** set `lock_timeout` for a lab maintenance job.
64. **Statement timeout:** test a timeout and observe cancellation/retry implications.
65. **Stop condition:** halt a job when free disk drops below reserve.
66. **Backup contention:** benchmark a backup running alongside an index build in staging.
67. **I/O budget:** measure storage latency before and after maintenance.
68. **Capacity gate:** block REINDEX when disk headroom is insufficient.
69. **Event-driven:** create an ANALYZE job triggered after a bulk load event.
70. **Retention:** design partition detach/drop according to retention policy.
71. **Default partition:** alert when the default partition grows unexpectedly.
72. **Index partition:** verify partition indexes after attach.
73. **Runbook:** write a procedure for handling invalid indexes.
74. **Runbook:** write a procedure for handling a blocked job.
75. **Runbook:** write a procedure for handling planner regressions.
76. **Runbook:** write a procedure for handling storage growth spikes.
77. **Schedule review:** evaluate a maintenance schedule that has colliding/overlapping jobs.
78. **Staging rehearsal:** run a full maintenance window on representative data.
79. **SLO review:** compare p95/p99 latency and replication lag before and after maintenance.
80. **Capstone design:** build a production PostgreSQL maintenance schedule covering index inventory/integrity, conditional reindex, statistics/autovacuum, capacity snapshots/forecasts, backup verification, scheduler permissions, concurrency control, logging, alerts, maintenance windows, and rollback runbooks.

## 35. Operational Checklist

### Indexes

- [ ] Per-database size and usage inventories are in place.
- [ ] Stats reset timestamps are recorded.
- [ ] Constraint and dependency indexes are protected.
- [ ] Invalid indexes are detected.
- [ ] Bloat/corruption is backed by evidence before reindexing.
- [ ] REINDEX method matches lock and downtime requirements.
- [ ] Extra disk and WAL headroom are verified.
- [ ] Results and query plans are verified after maintenance.

### Statistics and Vacuum

- [ ] Autoanalyze thresholds suit table size and churn.
- [ ] Bulk loads have ANALYZE follow-ups.
- [ ] Statistics targets are increased only for columns that need them.
- [ ] Extended statistics are used for relevant correlations.
- [ ] Dead tuples and autovacuum history are monitored.
- [ ] Long transactions and xmin horizons are monitored.
- [ ] XID age and anti-wraparound are prioritized.
- [ ] Autovacuum is not replaced by an uncontrolled VACUUM sweep.

### Capacity

- [ ] Database, relation, index, and tablespace snapshots have history.
- [ ] Filesystem/provider free bytes and inodes are monitored.
- [ ] WAL, slots, archive, and temp usage are monitored.
- [ ] Backup repository has dedicated metrics and retention.
- [ ] Growth rates and time-to-reserve are calculated.
- [ ] Headroom for REINDEX/rewrites/restores is reserved.
- [ ] Forecasts are reviewed against workload peaks.

### Scheduler and Change Control

- [ ] Every job has a clear owner, role, and command.
- [ ] No duplicate schedules exist across multiple schedulers.
- [ ] Jobs do not overlap outside policy.
- [ ] Credentials are managed securely.
- [ ] VACUUM/REINDEX CONCURRENTLY execute outside transaction blocks.
- [ ] Logs, exit codes, retries, and durations are stored.
- [ ] Lock/statement timeouts and stop conditions are defined.
- [ ] Maintenance windows have verification and rollback plans.

## 36. Summary

Scheduled PostgreSQL maintenance is a program of observation and conditional action:

~~~text
COLLECT BASELINE
  indexes / statistics / vacuum / storage
             |
             v
REVIEW SIGNALS
  usage / invalid state / stale stats / growth
             |
             v
PLAN MAINTENANCE
  owner / window / locks / I/O / disk / rollback
             |
             v
EXECUTE CONTROLLED JOBS
  ANALYZE / VACUUM / REINDEX / capacity tasks
             |
             v
VERIFY AND RECORD
  plans / integrity / free space / replication / backup
             |
             v
REFINE THE SCHEDULE
~~~

Key principles:

- **Autovacuum and autoanalyze form the automated foundation.** DBAs monitor and tune them to the workload rather than replacing them with a rigid VACUUM/ANALYZE schedule.
- **An index review is not an order to drop indexes.** Combine usage, constraints, query plans, workload seasonality, and size history.
- **REINDEX requires evidence and capacity.** Concurrent mode lowers blocking yet still consumes I/O, time, locks, and extra storage.
- **Statistics must keep pace with data changes.** After bulk loads or distribution shifts, targeted ANALYZE gives the planner accurate estimates.
- **Capacity requires history.** Snapshots by database, relation, and volume enable calculating growth and forecasting time to reserve.
- **Filesystem free space differs from reusable page space.** VACUUM does not usually shrink relation files significantly.
- **Schedulers require concurrency control and logging.** Prevent overlapping jobs, blind retries, or holding transactions open too long.
- **Maintenance must have stop conditions.** Disk space, replication lag, application latency, and lock queues can all require halting or deferring a job.
- **Backup/restore verification is part of maintenance.** Backup success must be backed up by restore drills.
- **Schedules must be reviewed.** When data volumes, workloads, SLAs, or storage change, cadences and maintenance windows must adapt too.

A well-run maintenance program catches problems before they become incidents, keeps planner statistics accurate, keeps indexes usable, keeps storage within capacity budgets, and ensures every maintenance action is explainable, verifiable, and safely repeatable.
