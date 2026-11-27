# pg_stat_database, Table Statistics, and Index Statistics in PostgreSQL

PostgreSQL provides **cumulative statistics views** to observe database, table, and index activity. These views help answer operational questions such as:

- How many transactions is the database processing?
- How are buffer hit ratios and block read volumes changing?
- Which tables have many sequential scans or index scans?
- Which tables receive heavy INSERT, UPDATE, or DELETE activity?
- Are autovacuum and autoanalyze keeping up with the workload?
- Which indexes are actively used, and which are rarely accessed?
- Where is heap, index, and TOAST I/O concentrated?
- Are there many temporary files, deadlocks, or recovery conflicts?

The lesson **“pg_stat_database, Table Statistics, and Index Statistics”**, in the **Monitoring** chapter of the **Database Engine Relational PostgreSQL** module, focuses on these core views:

- `pg_stat_database`: aggregated statistics per database.
- `pg_stat_user_tables` and `pg_stat_all_tables`: table-level access, modifications, and maintenance.
- `pg_statio_user_tables` and `pg_statio_all_tables`: heap, index, and TOAST block I/O.
- `pg_stat_user_indexes` and `pg_stat_all_indexes`: usage of each index.
- `pg_statio_user_indexes` and `pg_statio_all_indexes`: per-index block I/O.

This lesson also explains how to read counters, compute deltas and rates, interpret cache hit ratios, monitor vacuum and analyze, identify rarely used indexes, and build dashboards without confusing cumulative statistics with instantaneous state.

> **Principle:** Statistics views primarily hold cumulative counters since a reset timestamp. A large absolute number is not automatically a problem; compare deltas over time, correlate with workload and observation windows, and respect each metric's limitations.

---

## 1. What Are Cumulative Statistics?

PostgreSQL tracks many activities in statistics counters. Views in the `pg_catalog` schema expose these counters for DBAs and monitoring tools to query.

Examples:

- Number of committed transactions.
- Number of blocks read from OS or found in shared buffers.
- Number of sequential scans and index scans.
- Number of rows inserted, updated, or deleted.
- Number of heap/index blocks hit or read.
- Number of vacuum and analyze runs.

Most counters are cumulative: values increase monotonically until statistics are reset or reinitialized according to server/database lifecycle.

### 1.1. Counters vs. gauges

| Metric Type | Examples | How to Read |
|---|---|---|
| Counter | `xact_commit`, `seq_scan`, `idx_scan` | Increases over time; compute delta/rate |
| Gauge/current value | `numbackends` | Point-in-time value at observation |
| Estimate | `n_live_tup`, `n_dead_tup` | Estimated count, not an exact row count |
| Timestamp | `last_autovacuum`, `stats_reset` | Timestamp of an event |

Do not apply the same math to every metric type. For instance, taking the delta of `numbackends` does not tell you how many new connections were opened, because it is a point-in-time count of current backends.

## 2. Overview of Statistics Views

| View | Scope | Primary Question |
|---|---|---|
| `pg_stat_database` | One row per database | Overall workload and I/O |
| `pg_stat_database_conflicts` | One row per database on standby | Recovery conflicts |
| `pg_stat_all_tables` | User and system tables | Scans, tuple changes, vacuum/analyze |
| `pg_stat_user_tables` | User tables | Scans, tuple changes, vacuum/analyze |
| `pg_statio_all_tables` | User and system tables | Heap/index/TOAST block I/O |
| `pg_statio_user_tables` | User tables | User table block I/O |
| `pg_stat_all_indexes` | Each index | Index scan and tuple counters |
| `pg_stat_user_indexes` | Indexes on user tables | Index usage |
| `pg_statio_all_indexes` | Each index | Block reads/hits |
| `pg_statio_user_indexes` | Indexes on user tables | Index I/O |

Views suffixed with `user` typically exclude system catalogs. Views suffixed with `all` include system objects as well. When investigating application workloads, starting with the `user` views is usually cleaner.

## 3. pg_stat_database

`pg_stat_database` provides aggregated statistics for each database in the cluster.

Basic query:

~~~sql
SELECT *
FROM pg_stat_database
ORDER BY datname NULLS FIRST;
~~~

Commonly used columns:

| Column | Meaning |
|---|---|
| `datid` | OID of the database |
| `datname` | Name of the database |
| `numbackends` | Number of backends currently connected to this database |
| `xact_commit` | Number of committed transactions |
| `xact_rollback` | Number of rolled-back transactions |
| `blks_read` | Number of blocks read from filesystem into PostgreSQL buffers |
| `blks_hit` | Number of blocks found in shared buffers |
| `tup_returned` | Number of tuples returned by scans |
| `tup_fetched` | Number of tuples fetched by index scans |
| `tup_inserted` | Number of tuples inserted |
| `tup_updated` | Number of tuples updated |
| `tup_deleted` | Number of tuples deleted |
| `temp_files` | Number of temporary files created |
| `temp_bytes` | Total bytes written to temporary files |
| `deadlocks` | Number of deadlocks detected |
| `conflicts` | Number of recovery conflicts on a standby |
| `stats_reset` | Timestamp when statistics were reset |

Newer PostgreSQL versions may add session counters, checksum statistics, and timing fields. Always check the schema of the running version.

### 3.1. Filtering a single database

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

On some versions, the view also contains an aggregate row for shared objects with `datname` NULL. When building per-database dashboards, filter explicitly for the target databases.

## 4. numbackends: Current Backends

`numbackends` is the number of server processes currently connected to the database at stats collection time.

It is a gauge, not the cumulative total of connections ever opened.

Examples:

- `numbackends = 20`: 20 backends are currently connected to the database.
- Value rises from 20 to 35: current connected backends increased by 15.
- Value drops: connections closed or backends exited.

For per-session details, use `pg_stat_activity`:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY sessions DESC;
~~~

`pg_stat_database` is suited for high-level overview; `pg_stat_activity` is used to inspect specific sessions.

## 5. Transaction Commits and Rollbacks

Two counters:

- `xact_commit`: number of committed transactions.
- `xact_rollback`: number of rolled-back transactions.

The sum of both counters helps observe database-level transaction throughput.

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    xact_commit + xact_rollback AS completed_transactions,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

However, cumulative totals do not show the current rate. Take two samples separated by a known time interval to compute transaction rates.

### 5.1. Computing transaction rate

Suppose two samples are taken 60 seconds apart:

- First sample: `xact_commit = 1,000,000`.
- Second sample: `xact_commit = 1,006,000`.

Commits in the interval = 6,000, equivalent to 100 commits/second.

Formula:

~~~text
commit_rate = (commit_new - commit_old) / elapsed_seconds
~~~

Compute rollback rate the same way. Record `stats_reset` alongside each sample to detect counter resets between scrapes.

### 5.2. Rollback ratio

You can compute the rollback share among completed transactions:

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    round(
        100.0 * xact_rollback
        / NULLIF(xact_commit + xact_rollback, 0),
        2
    ) AS rollback_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

High rollbacks may result from intentional application rollbacks, failed transactions, deadlock retries, or business logic. Do not conclude the database has an outage solely from this ratio.

## 6. blks_read and blks_hit

Two aggregate I/O counters:

- `blks_read`: number of blocks PostgreSQL had to read into shared buffers.
- `blks_hit`: number of times blocks were found already in shared buffers without requiring a filesystem read at the PostgreSQL buffer manager layer.

These are useful indicators of buffer cache behavior.

### 6.1. Computing buffer hit ratio

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

Formula:

~~~text
hit ratio = blks_hit / (blks_hit + blks_read)
~~~

Example:

- `blks_hit = 9,000,000`.
- `blks_read = 1,000,000`.
- Hit ratio = 90%.

### 6.2. Hit ratio is not an absolute RAM-vs-disk ratio

`blks_read` means PostgreSQL had to request the block from the filesystem. The OS may satisfy that request from the OS page cache rather than physical disk.

Therefore:

- A low hit ratio does not mean every read hit the physical storage device.
- A high hit ratio does not guarantee low query latency.
- Sequential workloads scanning large tables can have a low hit ratio and still run completely normally.
- A small, repetitive hot-data workload can show a high hit ratio.

Always evaluate hit ratio alongside latency, block read rates, I/O metrics, and query workload.

## 7. tup_returned and tup_fetched

These two counters reflect database-level row reading activity:

- `tup_returned`: number of tuples returned by scans.
- `tup_fetched`: number of tuples fetched via index scans.

These are aggregate counters, not the number of rows returned to applications over the network. A query can scan many rows and return only a few after filtering.

Example:

~~~sql
SELECT *
FROM orders
WHERE created_at >= now() - interval '1 day'
  AND status = 'paid';
~~~

If predicates are unselective, PostgreSQL may read many tuples and discard most of them. Correlate database counters with table/index scan stats and query-level statistics to pinpoint causes.

## 8. tup_inserted, tup_updated, and tup_deleted

These counters record tuple modifications per database:

| Counter | Meaning |
|---|---|
| `tup_inserted` | Rows inserted |
| `tup_updated` | Rows updated |
| `tup_deleted` | Rows deleted |

They help classify workloads:

- Read-heavy databases.
- Insert-heavy databases.
- Update-heavy databases.
- Databases with heavy DELETE or batch cleanup traffic.

Remember these are cumulative counts. Compute deltas per minute/hour to spot workload spikes.

### 8.1. Comparing write rates

~~~sql
SELECT
    datname,
    tup_inserted,
    tup_updated,
    tup_deleted,
    tup_inserted + tup_updated + tup_deleted AS tuple_modifications
FROM pg_stat_database
WHERE datname = current_database();
~~~

Tables with high write rates often need closer monitoring of autovacuum frequency, dead tuple estimates, index maintenance, WAL volume, and bloat. Check per-table statistics to find which objects absorb most changes.

## 9. Temporary Files and temp_bytes

`temp_files` and `temp_bytes` reflect temporary files created and the volume of data written to them.

Operations that can spill to disk:

- Large sorts.
- Hash aggregations.
- Hash joins.
- Materialization.
- Any operation needing more workspace than its allocated memory budget.

Query:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_data_written
FROM pg_stat_database
WHERE datname = current_database();
~~~

Temporary files are not inherently errors. However, rapidly rising `temp_bytes` can indicate queries executing large sorts/hashes or insufficient `work_mem`.

### 9.1. Do not increase work_mem globally without care

`work_mem` applies per operation and can be allocated across multiple nodes within one query and many concurrent sessions simultaneously. Raising it too high can push memory consumption far beyond expectations.

Use query plans, concurrent session counts, and temp I/O metrics to guide tuning.

## 10. Deadlocks and Conflicts

`deadlocks` is the number of deadlocks detected in the database.

A deadlock occurs when two or more transactions acquire locks in conflicting orders and wait on each other.

Example:

- Transaction A locks row 1, then waits on row 2.
- Transaction B locks row 2, then waits on row 1.
- PostgreSQL detects the cycle and aborts one transaction.

Investigate via server logs, application logs, and `pg_stat_activity`/`pg_locks`.

`conflicts` in `pg_stat_database` reflects standby recovery conflicts—for example, a standby query canceled so recovery can apply WAL. It is distinct from duplicate-key conflicts in logical replication.

## 11. I/O Timing Statistics

When `track_io_timing` is enabled, PostgreSQL can record block read and write timings:

~~~sql
SHOW track_io_timing;
~~~

Common columns in `pg_stat_database`:

- `blk_read_time`: total time spent reading blocks.
- `blk_write_time`: total time spent writing blocks.

Query:

~~~sql
SELECT
    datname,
    blks_read,
    blk_read_time,
    blks_hit,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

These timings are valuable for observing PostgreSQL-layer I/O waits, and they are cumulative counters. Compute I/O time deltas over the sampling window and compare against elapsed time.

Enabling `track_io_timing` can introduce overhead depending on platform and workload. Benchmark on a representative environment and check your version/OS.

## 12. pg_stat_database_conflicts

On a standby, `pg_stat_database_conflicts` breaks down recovery conflicts by category:

~~~sql
SELECT *
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

Common categories:

- `confl_tablespace`: a referenced tablespace no longer exists.
- `confl_lock`: recovery needs a lock conflicting with a standby query.
- `confl_snapshot`: a query's snapshot can no longer be preserved due to cleanup/recovery.
- `confl_bufferpin`: a query holds a buffer pin blocking recovery.
- `confl_deadlock`: deadlock involving a recovery conflict.

Combine this view with `pg_stat_database.conflicts` and server logs to see which queries are being canceled on the standby.

## 13. pg_stat_all_tables and pg_stat_user_tables

`pg_stat_all_tables` reports statistics for all tables, including system catalogs. `pg_stat_user_tables` focuses only on user tables.

Query:

~~~sql
SELECT *
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

Important columns:

| Column | Meaning |
|---|---|
| `relid` | OID of the relation |
| `schemaname` | Schema name |
| `relname` | Table name |
| `seq_scan` | Number of sequential scans initiated on this table |
| `seq_tup_read` | Number of live rows fetched by sequential scans |
| `idx_scan` | Number of index scans initiated on this table |
| `idx_tup_fetch` | Number of live rows fetched by index scans |
| `n_tup_ins` | Number of rows inserted |
| `n_tup_upd` | Number of rows updated |
| `n_tup_del` | Number of rows deleted |
| `n_tup_hot_upd` | Number of HOT updates |
| `n_live_tup` | Estimated number of live rows |
| `n_dead_tup` | Estimated number of dead rows |
| `last_vacuum` | Timestamp of last manual vacuum |
| `last_autovacuum` | Timestamp of last autovacuum |
| `last_analyze` | Timestamp of last manual analyze |
| `last_autoanalyze` | Timestamp of last autoanalyze |

Columns vary by major version; inspect the view definition in `psql` to confirm the schema.

## 14. Sequential Scans

`seq_scan` counts sequential scans initiated on a table.

Sequential scans are not automatically bad. PostgreSQL may pick a sequential scan when:

- The table is small.
- The query retrieves a large proportion of rows.
- Filter predicates have low selectivity.
- Statistics indicate a sequential scan is cheaper than index access.
- The query must read nearly the entire table.

Inspect tables with high sequential scan activity:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    n_live_tup,
    round(
        seq_tup_read::numeric / NULLIF(seq_scan, 0),
        1
    ) AS avg_tuples_per_seq_scan
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC
LIMIT 20;
~~~

If a large table shows heavy sequential scans alongside high query latency, inspect query plans and filter patterns. Do not create indexes solely because `seq_scan` is large.

## 15. Table-Level Index Scans

`idx_scan` in `pg_stat_user_tables` counts index scans initiated on that table, aggregated across all indexes on the table.

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    seq_tup_read,
    idx_tup_fetch,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY idx_scan DESC
LIMIT 20;
~~~

The seq/index scan ratio helps characterize access patterns, though it does not directly identify slow queries or ineffective indexes.

A query using a bitmap index scan increments `idx_scan` on the index view, while tuple-fetch accounting differs from simple index scans. Understand each counter's semantics before comparing them.

## 16. HOT Updates

`n_tup_hot_upd` counts HOT (Heap-Only Tuple) updates.

A HOT update avoids index updates when conditions allow, such as:

- No indexed column is modified.
- The heap page has sufficient free space for the new tuple version.

HOT reduces index maintenance and WAL overhead in suitable workloads.

You can check the HOT update ratio:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    round(
        100.0 * n_tup_hot_upd
        / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC;
~~~

A low ratio does not automatically prove misconfiguration. Inspect indexed columns, `fillfactor`, page free space, and update patterns.

## 17. n_live_tup and n_dead_tup

Both fields are estimates:

- `n_live_tup`: estimated number of live tuples.
- `n_dead_tup`: estimated number of dead tuples.

They are not exact `COUNT(*)` values at query time.

Dead tuples accumulate when `UPDATE`/`DELETE` create obsolete row versions no longer needed by MVCC snapshots. `VACUUM` reclaims that space for reuse within the relation.

### 17.1. Dead tuples do not equal exact bloat

A table with high `n_dead_tup` may simply be waiting for autovacuum. You cannot infer exact bloat size from this counter alone.

To assess properly:

- Track dead tuple estimates over time.
- Check `last_autovacuum` and `vacuum_count`.
- Check long-running transactions and replication slots holding `xmin`.
- Track table and index sizes.
- Use dedicated bloat analysis tools if needed.

Never run `VACUUM FULL` just because `n_dead_tup` is high; `VACUUM FULL` rewrites the relation and takes heavy locks.

## 18. Monitoring Vacuum and Autovacuum

Query:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Questions to ask:

- Which tables have steadily growing dead tuples?
- Has autovacuum run recently?
- Has a large table been skipped for too long?
- Is a long transaction or replication slot pinning `xmin`?
- Do autovacuum workers have enough capacity?
- Is vacuum being canceled or failing to complete?

Autovacuum is foundational for controlling dead tuples and preventing transaction ID wraparound. Never disable it just to reduce background I/O.

## 19. Analyze and Autoanalyze

`ANALYZE` collects data distribution statistics so the query planner can estimate row counts and choose good execution plans.

`pg_stat_user_tables` provides:

- `last_analyze`.
- `last_autoanalyze`.
- `analyze_count`.
- `autoanalyze_count`.

Find tables not recently analyzed:

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC NULLS LAST
LIMIT 30;
~~~

`n_mod_since_analyze` exists on supported versions. On older servers lacking this column, omit it and rely on available counters and timestamps.

After bulk loads or large data shifts, proactive `ANALYZE` may be warranted:

~~~sql
ANALYZE public.orders;
~~~

## 20. n_mod_since_analyze

`n_mod_since_analyze` estimates row modifications since the last analyze on supported versions.

High values suggest planner statistics may lag behind recent workload changes. However, autoanalyze thresholds depend on table row counts, scale factors, and autovacuum settings.

Compare table size, modification counts, last analyze time, query plans, and planner estimates vs. actual rows in `EXPLAIN ANALYZE`.

## 21. pg_statio_all_tables and pg_statio_user_tables

These views report block I/O per table.

`pg_statio_user_tables` typically includes:

| Column | Meaning |
|---|---|
| `heap_blks_read` | Heap blocks read into PostgreSQL buffers |
| `heap_blks_hit` | Heap blocks found in shared buffers |
| `idx_blks_read` | Index blocks read |
| `idx_blks_hit` | Index blocks found in shared buffers |
| `toast_blks_read` | TOAST blocks read |
| `toast_blks_hit` | TOAST blocks hit |
| `tidx_blks_read` | TOAST index blocks read |
| `tidx_blks_hit` | TOAST index blocks hit |

Query:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit,
    tidx_blks_read,
    tidx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 30;
~~~

Use this view to find tables driving high block reads/hits, then inspect query plans and index usage.

## 22. Heap, Index, and TOAST

PostgreSQL stores table rows in the heap relation; indexes are separate relations. TOAST stores oversized values compressed or out-of-line from the main tuple.

- `heap_blks_*`: heap block activity.
- `idx_blks_*`: index block activity.
- `toast_blks_*`: TOAST data block activity.
- `tidx_blks_*`: TOAST index block activity.

Applications storing large JSON or text payloads can generate heavy TOAST I/O. If queries routinely fetch full large values, review column projections and application access patterns.

## 23. Computing Per-Table Hit Ratios

Compute heap hit ratio:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    round(
        100.0 * heap_blks_hit
        / NULLIF(heap_blks_hit + heap_blks_read, 0),
        2
    ) AS heap_hit_percent
FROM pg_statio_user_tables
ORDER BY heap_blks_read + heap_blks_hit DESC;
~~~

Compute index hit ratio separately:

~~~sql
SELECT
    schemaname,
    relname,
    idx_blks_read,
    idx_blks_hit,
    round(
        100.0 * idx_blks_hit
        / NULLIF(idx_blks_hit + idx_blks_read, 0),
        2
    ) AS index_hit_percent
FROM pg_statio_user_tables
ORDER BY idx_blks_read + idx_blks_hit DESC;
~~~

Per-table hit ratios aid object-level cache analysis, though they are likewise shaped by workload mix and cache warm-up.

## 24. pg_stat_all_indexes and pg_stat_user_indexes

`pg_stat_user_indexes` contains one row per index on user tables.

Key columns:

| Column | Meaning |
|---|---|
| `schemaname` | Table schema |
| `relname` | Table name |
| `indexrelname` | Index name |
| `idx_scan` | Number of index scans initiated on this index |
| `idx_tup_read` | Number of index entries returned by scans |
| `idx_tup_fetch` | Number of live table rows fetched by simple index scans |

Query:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC
LIMIT 50;
~~~

This view shows which indexes the planner actually used during the current statistics interval.

## 25. idx_scan, idx_tup_read, and idx_tup_fetch

Do not treat these three counters as interchangeable:

- `idx_scan`: number of index scans initiated.
- `idx_tup_read`: number of index entries read.
- `idx_tup_fetch`: number of live table rows fetched via simple index scans.

Bitmap index scans increase `idx_tup_read` without incrementing `idx_tup_fetch` correspondingly, because table rows are subsequently fetched via a bitmap heap scan.

A scan may read many index entries and filter out many rows. Therefore, `idx_tup_fetch / idx_tup_read` is not a standalone index quality metric.

## 26. Apparently Unused Indexes

Find indexes with `idx_scan = 0`:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Treat this strictly as a candidate list for investigation. Never drop indexes automatically because:

- Statistics may have been reset recently.
- An index may only be used monthly or quarterly.
- A unique index or primary key enforces a data constraint.
- An index may support foreign key checks or rare queries.
- The planner may pick the index for a workload absent during the observation window.
- The index may be required for a maintenance or reporting job.

Inspect catalog constraints and full workload history before deciding.

## 27. Comparing Index Scans with Index Size

A large index with few scans is worth reviewing, though size alone never proves redundancy.

Check sizes:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
~~~

Cross-check index definitions:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Indexes may include `INCLUDE` columns, partial predicates, expressions, or uniqueness constraints; never compare solely by name and scan count.

## 28. pg_statio_all_indexes and pg_statio_user_indexes

`pg_statio_user_indexes` reports block reads and hits per index.

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit,
    round(
        100.0 * idx_blks_hit
        / NULLIF(idx_blks_hit + idx_blks_read, 0),
        2
    ) AS index_hit_percent
FROM pg_statio_user_indexes
ORDER BY idx_blks_read DESC
LIMIT 30;
~~~

These are index relation I/O counters. Join with `pg_stat_user_indexes` to see both how often an index is scanned and how much block read/hit activity it generates.

## 29. Joining Table and Index Statistics

Join both views to inspect table access and index usage together:

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.idx_scan,
    t.n_live_tup,
    t.n_dead_tup,
    i.indexrelname,
    i.idx_scan AS index_scan_count,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_stat_user_tables AS t
LEFT JOIN pg_stat_user_indexes AS i
  ON i.relid = t.relid
ORDER BY t.seq_scan DESC, t.relname, i.indexrelname;
~~~

One row appears per index on each table. Tables without indexes still appear due to the `LEFT JOIN`.

Do not sum `t.seq_scan` across the joined result as a table total; table-level counters repeat on each index row.

## 30. Finding Heavily Modified Tables

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC
LIMIT 30;
~~~

Write-heavy tables warrant close monitoring of autovacuum frequency, dead tuple estimates, index maintenance, WAL generation, replication lag, and table/index sizes.

Not every update creates identical bloat; HOT updates, `fillfactor`, and MVCC snapshot horizons strongly affect outcomes.

## 31. Combining Table Stats with I/O Stats

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.idx_scan,
    t.n_live_tup,
    t.n_dead_tup,
    io.heap_blks_read,
    io.heap_blks_hit,
    io.idx_blks_read,
    io.idx_blks_hit
FROM pg_stat_user_tables AS t
JOIN pg_statio_user_tables AS io
  ON io.relid = t.relid
ORDER BY io.heap_blks_read + io.idx_blks_read DESC
LIMIT 30;
~~~

This query identifies tables with heavy scans and I/O. From there, pick specific queries via application telemetry or `pg_stat_statements` to inspect plans.

## 32. Distinguishing Database-Level and Table-Level Counters

A single operation can increment multiple counters:

- Table scan query: `pg_stat_database` increments `tup_returned`; table stats increment `seq_scan`/`seq_tup_read` or index stats.
- Indexed query: both database counters and index counters update.
- `INSERT`: database tuple counters and table `n_tup_ins` increment.
- Temporary sort: database `temp_files`/`temp_bytes` increment.

Never add database-level and table-level counters together into one total; they are different perspectives on the same activity.

## 33. Cumulative Counters and Deltas

For monitoring, store periodic samples:

| Timestamp | xact_commit |
|---|---:|
| 10:00 | 100,000 |
| 10:01 | 106,500 |
| 10:02 | 112,000 |

Commit rate:

- 10:00–10:01: 6,500/min.
- 10:01–10:02: 5,500/min.

Absolute counters show totals since reset; deltas show activity inside the observation window.

### 33.1. Detecting counter resets

Store `stats_reset` alongside samples. If the reset timestamp changes, never compute a delta across the reset boundary.

If a newer counter value is smaller than the previous sample, a reset or lifecycle change occurred. Start a fresh baseline instead of emitting a negative rate.

## 34. Example Sample Storage

If a monitoring system stores snapshots in a dedicated table, a simple schema might look like:

~~~sql
CREATE TABLE monitoring.database_stat_samples (
    sampled_at timestamptz NOT NULL,
    datname name NOT NULL,
    stats_reset timestamptz,
    xact_commit bigint,
    blks_read bigint,
    blks_hit bigint,
    PRIMARY KEY (sampled_at, datname)
);
~~~

A rate query pairs consecutive samples, checks that `stats_reset` remained unchanged, and ensures positive elapsed time.

In production, monitoring agents typically collect and store metrics outside PostgreSQL. Avoid creating tables inside application databases just to store stats when a dedicated metrics backend is available.

## 35. Statistics Snapshots and Transactions

Statistics views exhibit snapshot/caching semantics depending on PostgreSQL version and `stats_fetch_consistency`.

Running multiple `SELECT` statements inside one long transaction may return the same cached statistics snapshot rather than immediately reflecting ongoing updates.

Refresh the session snapshot explicitly with:

~~~sql
SELECT pg_stat_clear_snapshot();
~~~

When comparing two points in time:

- Use short transactions.
- Take independent samples.
- Record timestamps.
- Check `stats_reset`.
- Avoid holding long read-only transactions open just to poll counters.

Check documentation for your version because statistics collection/fetch mechanics evolve across major releases.

## 36. Statistics Are Not Transactional Audit Data

Statistics views are for observability, not audit logs or business source-of-truth records.

Do not use them to:

- Prove which user modified a specific row.
- Reconstruct exact transaction ordering.
- Capture the query text of every scan.
- Replace WAL or audit logs.
- Compute exact point-in-time row counts.
- Serve as the sole basis for billing or compliance evidence.

Use audit logging, application events, WAL decoding, or query-level telemetry for those requirements.

## 37. Resetting Statistics

PostgreSQL provides functions to reset statistics, such as:

~~~sql
SELECT pg_stat_reset();
~~~

Other functions reset database, table, or specific statistics subsets depending on version and privileges.

Resetting clears counter baselines. If dashboards plot raw cumulative counters, a reset causes values to plummet suddenly.

Do not reset statistics routinely just to “clean up dashboards.” Monitoring tools should compute deltas and track reset timestamps.

### 37.1. Resetting does not delete data

Resetting statistics does not remove rows, tables, or indexes. It only zeroes the counters scoped to the invoked function.

However, resetting in production can erase historical observability data not yet scraped by monitoring. Perform resets intentionally and understand their scope.

## 38. Statistics Access Permissions

Statistics views expose varying levels of detail depending on privileges.

The predefined `pg_monitor` role is generally appropriate for read-only monitoring accounts. `pg_read_all_stats` grants broader visibility into statistics restricted for ordinary users.

Grant example:

~~~sql
GRANT pg_monitor TO monitoring_user;
~~~

These are monitoring privileges, not superuser access. Review security policies and required roles for your PostgreSQL version.

Do not grant superuser to monitoring agents if they only need to read statistics.

## 39. Version Compatibility

Statistics views are added and modified across major versions.

Examples:

- Newer session counters may be absent on older servers.
- `wal_status` or `safe_wal_size` belong to versions supporting those slot fields.
- `pg_stat_io` exists on newer PostgreSQL versions.
- Certain timestamp or worker columns were added in later releases.
- `n_mod_since_analyze` and detailed fields should be verified against the live catalog view.

Before deploying queries:

~~~sql
SELECT version();
~~~

In `psql`, inspect view definitions to verify columns:

~~~text
\d+ pg_stat_database
\d+ pg_stat_user_tables
\d+ pg_statio_user_tables
\d+ pg_stat_user_indexes
~~~

Do not copy a dashboard query from a newer major version onto an older server without checking columns.

## 40. pg_stat_io as a Complementary View

On PostgreSQL versions supporting `pg_stat_io`, this view exposes I/O statistics by backend type, object, and context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

`pg_stat_io` adds a broader I/O dimension; it does not replace `pg_statio_user_tables` or `pg_statio_user_indexes` when per-relation visibility is needed.

Use it on supported versions and check schemas since columns can evolve across major releases.

## 41. pg_stat_statements Adds Query-Level Statistics

`pg_stat_statements` is a widely used extension for query-pattern statistics:

- Call counts per query.
- Total/min/max/mean execution time.
- Rows processed.
- Shared/local/temp block hits, reads, and writes.
- WAL bytes on supported versions.

It pinpoints which queries drive workload, while `pg_stat_database` and table/index stats show how databases and objects behave.

Install the extension and configure `shared_preload_libraries` per your version's instructions. Do not assume `pg_stat_statements` is available by default without setup.

## 42. What Should a Database-Level Dashboard Include?

An overview dashboard can include:

| Group | Metrics |
|---|---|
| Workload | Commits/s, rollbacks/s, active connections |
| Reads | Block reads/s, buffer hits/s |
| Writes | Tuple inserts/updates/deletes per second |
| Temporary I/O | Temp files/s, temp bytes/s |
| Concurrency | Deadlocks, conflicts |
| Latency | Block read/write time deltas |
| Health | Stats reset time, checksum failures if supported |

Plot rates and trends over time. Avoid dashboards showing only raw cumulative counters accumulated since database creation.

## 43. What Should a Table-Level Dashboard Include?

Per table:

- `seq_scan` delta.
- `idx_scan` delta.
- `seq_tup_read` rate.
- `idx_tup_fetch` rate.
- Insert/update/delete rates.
- HOT update percentage.
- Live/dead tuple estimates.
- Last vacuum/autovacuum.
- Last analyze/autoanalyze.
- Heap/index/TOAST block reads/hits.
- Relation sizes.

Use top-N tables ranked by I/O, modification rate, and dead tuple estimates to focus investigations.

## 44. What Should an Index-Level Dashboard Include?

Per index:

- `idx_scan` rate.
- `idx_tup_read` and `idx_tup_fetch`.
- `idx_blks_read`/`idx_blks_hit`.
- Index size.
- Table name.
- Index definition.
- Unique/primary/constraint dependencies.

Observe index usage counters over a sufficiently wide window covering batch jobs and scheduled workloads.

## 45. Finding Tables with Heavy Sequential I/O

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.seq_tup_read,
    io.heap_blks_read,
    io.heap_blks_hit,
    pg_size_pretty(
        pg_total_relation_size(t.relid)
    ) AS total_size
FROM pg_stat_user_tables AS t
JOIN pg_statio_user_tables AS io
  ON io.relid = t.relid
ORDER BY io.heap_blks_read DESC
LIMIT 20;
~~~

A table with high heap reads may simply be a large table scanned legitimately. Review query plans, predicate selectivity, partition pruning, and workload frequency before adding indexes.

## 46. Finding Tables with Dead Tuples and Stale Maintenance

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze,
    autovacuum_count,
    autoanalyze_count,
    pg_size_pretty(
        pg_total_relation_size(relid)
    ) AS total_size
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Large tables with rising dead tuple estimates and long gaps since `last_autovacuum` need review. Check long transactions, replication slots, autovacuum thresholds, and worker capacity before changing configuration.

## 47. Relation Sizes and Statistics

Statistics views do not provide full table/index sizes. Use size functions:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

- `pg_relation_size`: size of the specified relation (typically the main fork/heap when passed a table OID).
- `pg_indexes_size`: total size of all indexes on the table.
- `pg_total_relation_size`: table plus associated components such as indexes and TOAST.

Large size alone does not prove bloat. Compare against row counts, data types, `fillfactor`, index definitions, and historical growth.

## 48. Interpreting Index Usage Responsibly

Before concluding an index is unnecessary:

1. Check `stats_reset`.
2. Confirm the observation window.
3. Cover daily, monthly, and quarterly workloads.
4. Verify primary key and unique constraints.
5. Check foreign key support and maintenance needs.
6. Inspect query plans and index definitions.
7. Check whether the index overlaps with another index.
8. Evaluate write overhead and storage cost.
9. Test on staging.
10. Drop only via a migration with a rollback plan.

`idx_scan = 0` over one hour is never enough reason to drop an index.

## 49. Interpreting Cache Hit Ratio Responsibly

Do not enforce a single hit-ratio threshold across every database.

Examples:

- Small hot OLTP sets often expect high hit ratios.
- Large data warehouse scans naturally show lower ratios.
- After restarts or during cache warm-up, ratios dip.
- Sequential workloads may use ring buffers or bypass shared caching differently than random lookups.
- OS page cache hits are not reflected as shared-buffer hits.

Monitor trends alongside block read latency, physical storage metrics, query latency, and workload type.

## 50. Tracking Workload Shifts Over Time

Cumulative counters can obscure recent changes.

For instance, a table might have accumulated 1 billion sequential scans months ago while experiencing zero scans today. A large cumulative `seq_scan` does not mean the current workload is scanning heavily.

Store periodic samples and compute deltas:

~~~text
scan_rate = (seq_scan_new - seq_scan_old) / elapsed_seconds
~~~

Do the same for `idx_scan`, tuple modifications, and block I/O counters.

## 51. Troubleshooting: Low Hit Ratio

Check:

- Did the database recently restart or is cache warming up?
- Is the workload scanning large tables?
- Is `shared_buffers` sized appropriately?
- How are OS page cache and storage latency behaving?
- Are queries reading working sets larger than memory?
- Are query plans scanning excessive blocks?
- Can predicates or projections reduce columns/rows read?
- Would an index reduce reads or merely add write overhead?

Never raise `shared_buffers` or add indexes based on a single glance at hit ratio.

## 52. Troubleshooting: Rapidly Rising temp_bytes

Check:

- Which sort/hash queries are currently running.
- `EXPLAIN ANALYZE` and temporary block counters.
- Current `work_mem`.
- Concurrent session counts.
- Whether queries repeat sorts/hashes unnecessarily.
- Whether row counts can be reduced before sorting/joining.
- Whether an appropriate index or sort order exists.

Use `pg_stat_statements` and appropriate logs to locate spilling queries.

## 53. Troubleshooting: High n_dead_tup

Check:

- `last_autovacuum`.
- Autovacuum thresholds and scale factors.
- Long-running transactions.
- `idle-in-transaction` sessions.
- Replication slots and `xmin` horizons.
- Table write rates.
- Vacuum logs and worker capacity.
- Relation size trends.

If an old snapshot pins old row versions, vacuum cannot reclaim them no matter how often autovacuum runs.

## 54. Troubleshooting: idx_scan Equal to 0

Check:

- Were statistics recently reset?
- Is the observation window long enough?
- Is the workload seasonal?
- Is the index backing a unique/primary key?
- Does any constraint depend on the index?
- Does the planner use the index in less frequent plans?
- Does the index support a rare report?

Never drop an index automatically based on one counter.

## 55. Troubleshooting: Rising Deadlocks

Use server logs to identify:

- Involved SQL statements.
- Transaction IDs and sessions.
- Lock types and objects.
- Lock acquisition ordering.
- Application retry behavior.

Typical fixes include standardizing row update order, shortening transactions, and avoiding holding locks while calling external services.

`pg_stat_database.deadlocks` is an aggregate counter and does not store individual deadlock details.

## 56. Monitoring Intervals and Retention

Choose intervals by purpose:

- 5–15 seconds: short-term high-resolution troubleshooting during incidents.
- 30–60 seconds: standard workload dashboards.
- 5 minutes: longer-term trends with lower collection volume.

These are operational suggestions, not PostgreSQL rules. Balance resolution against collection and storage overhead.

Retain raw snapshots or time-series deltas long enough to compare peak hours, batch windows, and seasonal workloads.

## 57. Dashboard Design Checklist

**Database-level**

1. Are transaction commit/rollback rates shown?
2. Is current backend count tracked?
3. Are block read/hit rates shown?
4. Are temp bytes/files rates shown?
5. Are deadlock/conflict rates shown?
6. Is I/O timing included where appropriate?
7. Are `stats_reset` and reset detection handled?

**Table-level**

8. Are seq/index scan deltas shown?
9. Are tuple modification rates shown?
10. Are live/dead tuple estimates tracked?
11. Are vacuum/analyze timestamps shown?
12. Is heap/index/TOAST block I/O tracked?
13. Are table sizes monitored?

**Index-level**

14. Are `idx_scan` deltas tracked?
15. Are `idx_tup_read` and `idx_tup_fetch` tracked?
16. Are index block reads/hits shown?
17. Are index sizes and definitions accessible?
18. Are constraint-backing indexes protected from accidental drops?

**Operations**

19. Does the monitoring role use least privilege?
20. Are queries compatible with the PostgreSQL major version?
21. Are counter resets surfaced cleanly?
22. Are historical trends retained?
23. Are runbooks linked for anomalous metrics?

## 58. Practice Exercises

### Exercise 1 — pg_stat_database

At what level does this view aggregate statistics?

**Hint:** per database.

### Exercise 2 — numbackends

Is this a counter or a gauge?

**Hint:** gauge; current connected backends.

### Exercise 3 — xact_commit

What does this counter measure?

**Hint:** committed transactions.

### Exercise 4 — xact_rollback

Does an increase in this counter always mean the database has errors?

**Hint:** no; applications may intentionally roll back.

### Exercise 5 — blks_read

Does this counter strictly equal physical disk reads?

**Hint:** no; the OS page cache can satisfy requests.

### Exercise 6 — blks_hit

What does it measure?

**Hint:** blocks found in shared buffers.

### Exercise 7 — Hit ratio

Write the formula for shared buffer hit ratio.

**Hint:** `blks_hit / (blks_hit + blks_read)`.

### Exercise 8 — tup_returned

What does this counter measure?

**Hint:** tuples returned by scans.

### Exercise 9 — tup_fetched

Which activity does it track?

**Hint:** tuples fetched via index scans.

### Exercise 10 — temp_bytes

What does a rapid rise in this counter indicate?

**Hint:** queries spilling temporary data to files.

### Exercise 11 — deadlocks

Which view exposes the per-database `deadlocks` counter?

**Hint:** `pg_stat_database`.

### Exercise 12 — conflicts

What does `conflicts` in `pg_stat_database` primarily measure?

**Hint:** standby recovery conflicts.

### Exercise 13 — pg_stat_user_tables

Which group of objects does this view exclude?

**Hint:** system catalogs.

### Exercise 14 — seq_scan

What does this counter measure?

**Hint:** sequential scans initiated on the table.

### Exercise 15 — idx_scan

In table stats, what is `idx_scan`?

**Hint:** number of index scans initiated on the table.

### Exercise 16 — n_tup_ins

What does this counter measure?

**Hint:** inserted tuples.

### Exercise 17 — n_tup_hot_upd

What do HOT updates help reduce?

**Hint:** index maintenance when conditions permit.

### Exercise 18 — n_live_tup

Is this an exact row count?

**Hint:** no, it is an estimate.

### Exercise 19 — n_dead_tup

Which mechanism primarily generates dead tuples?

**Hint:** MVCC with `UPDATE`/`DELETE`.

### Exercise 20 — autovacuum

Which column shows the timestamp of the last autovacuum?

**Hint:** `last_autovacuum`.

### Exercise 21 — autoanalyze

What is the purpose of `ANALYZE`?

**Hint:** updating planner statistics.

### Exercise 22 — pg_statio_user_tables

Which block I/O types does this view observe?

**Hint:** heap, index, TOAST, and TOAST index.

### Exercise 23 — heap_blks_hit

What does this counter measure?

**Hint:** heap blocks found in shared buffers.

### Exercise 24 — pg_stat_user_indexes

What does one row in this view represent?

**Hint:** one index on a user table.

### Exercise 25 — idx_tup_read

Does it count index entries or table rows?

**Hint:** index entries read.

### Exercise 26 — idx_tup_fetch

How does it differ from `idx_tup_read`?

**Hint:** live table rows fetched via simple index scans.

### Exercise 27 — Bitmap scans

Why can `idx_tup_read` be much larger than `idx_tup_fetch`?

**Hint:** bitmap scans do not increment `idx_tup_fetch` in the same way.

### Exercise 28 — Unused indexes

Is `idx_scan=0` sufficient to drop an index?

**Hint:** no; check stats resets, workload windows, and constraints.

### Exercise 29 — pg_statio_user_indexes

Which metrics does this view provide?

**Hint:** index block reads and hits.

### Exercise 30 — pg_stat_database_conflicts

On which server role is this view useful?

**Hint:** standby/recovery servers.

### Exercise 31 — track_io_timing

Which statistics does this setting populate?

**Hint:** block read and write times.

### Exercise 32 — Counter deltas

Why must you take two samples?

**Hint:** to compute a rate over a time interval.

### Exercise 33 — stats_reset

Why store this timestamp?

**Hint:** to detect counter resets and avoid invalid deltas.

### Exercise 34 — Statistics snapshots

What might a long-running transaction see?

**Hint:** a cached statistics snapshot depending on consistency settings and version.

### Exercise 35 — pg_stat_clear_snapshot

What does this function do?

**Hint:** clears the current session's cached stats snapshot.

### Exercise 36 — pg_stat_reset

Does resetting statistics delete table data?

**Hint:** no, it only resets counters within its scope.

### Exercise 37 — pg_monitor

Who is this role intended for?

**Hint:** monitoring and observability accounts.

### Exercise 38 — pg_stat_io

What perspective does this view add?

**Hint:** I/O by backend type, object, and context on supported versions.

### Exercise 39 — pg_stat_statements

What perspective does this extension provide?

**Hint:** query-level execution statistics.

### Exercise 40 — Dashboards

Why are raw cumulative counters insufficient for monitoring?

**Hint:** they do not show current rates or shifts within the current time window.

## 59. Frequently Asked Questions

### Does pg_stat_database have one row per table?

No. It aggregates by database. Use `pg_stat_user_tables` to inspect individual tables.

### Is numbackends the total number of connections opened since server startup?

No. It is the number of backends currently connected to the database.

### Are blks_read always physical disk reads?

No. PostgreSQL requests blocks into buffers; the OS page cache may satisfy reads without touching physical storage.

### Does a 99% hit ratio guarantee fast queries?

No. Queries can still be slow due to CPU, locks, network, execution plans, temp I/O, or other causes.

### Does high seq_scan mean I should create an index?

Not necessarily. Sequential scans are often optimal for small tables or queries reading most rows.

### Is n_dead_tup an exact count of dead rows?

No. It is a statistical estimate.

### Does a recent autovacuum run mean the table is completely clean?

No. Vacuum is constrained by open snapshots, locks, still-visible dead tuples, and ongoing workload.

### Does idx_scan equal to 0 mean an index is useless?

No. Consider the observation window, stats reset time, constraints, and rare workloads.

### Can idx_tup_read exceed idx_tup_fetch?

Yes. Bitmap scans and other index access methods give those two counters different semantics.

### Does pg_stat_user_indexes show system indexes?

No. Use `pg_stat_all_indexes` to inspect system objects too.

### How can I tell which query creates temporary files?

Database-level temp counters do not identify specific queries. Use `pg_stat_statements`, `log_temp_files`, and query-level diagnostics.

### Can statistics be reset daily?

Yes, if permitted by policy and privileges, though it is usually unnecessary. Monitoring systems should compute deltas and record reset timestamps.

### Why do two SELECTs in the same transaction return unchanged stats?

Statistics snapshots may be cached within a transaction depending on `stats_fetch_consistency` and version. End the transaction or call `pg_stat_clear_snapshot` when a fresh snapshot is needed.

### Is superuser required to read statistics?

Not always. Use `pg_monitor` or `pg_read_all_stats` as appropriate for your needs and version; avoid granting superuser to monitoring accounts.

### Does pg_stat_io replace pg_statio_user_tables?

No. `pg_stat_io` adds a backend/object/context breakdown; `pg_statio` views remain valuable for relation-level I/O.

## 60. Summary

Core queries:

~~~sql
-- Database overview.
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    conflicts,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- Buffer hit ratio.
SELECT
    datname,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS hit_percent
FROM pg_stat_database
WHERE datname = current_database();

-- Table scans, writes, and maintenance.
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;

-- Table block I/O.
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_statio_user_tables;

-- Index usage.
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Index block I/O.
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_indexes;

-- Database conflicts on standby.
SELECT *
FROM pg_stat_database_conflicts;
~~~

Key principles to remember:

1. `pg_stat_database` provides database-level aggregated statistics.
2. `numbackends` is a current gauge; most remaining counters are cumulative.
3. `xact_commit` and `xact_rollback` measure transaction workload.
4. `blks_hit`/`blks_read` help compute shared buffer hit ratio but do not measure physical disk I/O directly.
5. `tup_returned` and `tup_fetched` reflect database-level row reading activity.
6. `temp_files`/`temp_bytes` help detect sort/hash spills.
7. `deadlocks` and `conflicts` represent different issues; `conflicts` in database stats reflects standby recovery conflicts.
8. `pg_stat_user_tables` tracks scans, tuple modifications, and vacuum/analyze activity.
9. High `seq_scan` is not inherently bad; consider table size and query plans.
10. `n_live_tup`/`n_dead_tup` are estimates, not exact counts.
11. `pg_statio_user_tables` separates heap, index, and TOAST I/O.
12. `pg_stat_user_indexes` tracks index scans and tuple counters.
13. `idx_tup_read` differs from `idx_tup_fetch`, especially for bitmap scans.
14. `idx_scan = 0` alone is never sufficient grounds to drop an index.
15. `pg_statio_user_indexes` reports block reads and hits per index.
16. Use `stats_reset` to detect counter resets.
17. Store periodic samples and compute deltas/rates rather than reading cumulative values alone.
18. Statistics snapshots may be cached inside transactions; use short transactions when polling.
19. Statistics are telemetry, not audit logs or transactional records.
20. Grant least-privilege monitoring roles and verify columns for your PostgreSQL major version.
21. Combine `pg_stat_io` and `pg_stat_statements` when deeper I/O or query-level visibility is required.
22. Read database, table, index, and filesystem metrics together before tuning configuration.

View selection diagram:

~~~text
Want to observe PostgreSQL workload?
              |
              v
      Database scope?
              |
              v
      pg_stat_database
              |
              +--> Transactions / cache / temp / deadlocks
              |
              v
       Need per-table stats?
              |
              v
      pg_stat_user_tables
              |
              +--> Scans / writes / vacuum / analyze
              |
              v
      Need block I/O?
              |
              v
      pg_statio_user_tables
              |
              v
      Need per-index stats?
              |
              v
      pg_stat_user_indexes
              |
              +--> Scans / tuple counters
              |
              v
      pg_statio_user_indexes
              |
              v
      Store samples and compute deltas/rates
              |
              v
      Correlate query plans, logs, and OS I/O
~~~

**Conclusion:** `pg_stat_database` reveals overall workload; table statistics identify which tables are being scanned, modified, or in need of maintenance; index statistics show how indexes are accessed and consuming I/O. Use these views effectively by **distinguishing counters from gauges and estimates, computing deltas over time, checking `stats_reset`, understanding each column's semantics, and correlating with query plans and OS metrics**.
