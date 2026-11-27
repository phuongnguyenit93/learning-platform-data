# Monitoring VACUUM, Index Builds, COPY, and Backups in PostgreSQL

Maintenance and data-loading operations in PostgreSQL can run anywhere from a few seconds to many hours. When a `VACUUM`, `CREATE INDEX`, `COPY`, or `pg_basebackup` command is running, merely seeing an `active` session does not tell you how far it has progressed, what it is waiting on, or roughly how much longer it might take.

PostgreSQL exposes **progress reporting views** in the `pg_catalog` schema. These `pg_stat_progress_*` views show one row per backend currently executing that class of operation, including the current phase and progress counters. Combining them with `pg_stat_activity`, statistics views, and logs lets DBAs track ongoing work instead of guessing from elapsed runtime.

This lesson focuses on four operation groups: VACUUM/ANALYZE, index creation and rebuilds, COPY, and physical base backups. It covers how to read phases and counters, compute progress, identify waiting operations, write monitoring queries, and handle cases where no reliable percentage complete exists.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain progress reporting and how progress views differ from activity and statistics views.
2. Monitor `VACUUM`, autovacuum, `ANALYZE`, and `VACUUM FULL`.
3. Monitor `CREATE INDEX`, `CREATE INDEX CONCURRENTLY`, and `REINDEX`.
4. Monitor `COPY FROM` and `COPY TO`, and understand when total bytes are unavailable.
5. Monitor `pg_basebackup` and backup phases.
6. Join progress views with `pg_stat_activity` to inspect user, database, query, wait events, and elapsed time.
7. Interpret counters, completion percentages, and ETA limitations.
8. Identify blocking, I/O pressure, dead tuples, replication lag, and WAL/archive bottlenecks.
9. Design appropriate dashboards and alerts for production.
10. Account for version differences and access permissions when monitoring.

## 2. What Is Progress Reporting?

### 2.1. Activity and progress are different

`pg_stat_activity` answers **what a session/process is doing**: PID, user, database, state, query, start time, wait event, and transaction age.

`pg_stat_progress_*` answers **how far a specific operation has progressed**: phase, blocks/tuples/bytes processed, known totals, and task-specific counters.

Statistics views such as `pg_stat_user_tables`, `pg_stat_database`, or `pg_stat_archiver` describe cumulative activity over a period or since stats reset; they do not track the live progress of an individual running command.

### 2.2. One progress row corresponds to one backend

Progress views include a `pid` column identifying the backend performing the operation. Join `pid` with `pg_stat_activity.pid` to retrieve session context.

~~~sql
SELECT
    p.pid,
    a.usename,
    a.datname,
    a.application_name,
    a.client_addr,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    now() - a.query_start AS elapsed,
    a.query
FROM pg_stat_activity AS a
WHERE a.state = 'active'
ORDER BY a.query_start;
~~~

A progress view contains a row only while the operation belongs to an instrumented command type and the backend is still executing it. Once the command finishes, the row disappears; record metrics or logs if history is needed.

### 2.3. A phase is a work state, not a percentage

An operation can move through multiple phases. For instance, an index build may wait for writers, scan the heap, sort tuples, and wait for old snapshots. Some phases update progress counters, whereas others represent waiting states.

Never treat `phase` as a percentage. Read the counters corresponding to each phase and understand their units.

### 2.4. Progress views are not audit logs

Progress views are point-in-time snapshots of current state. They retain no history after the backend finishes and do not prove an operation succeeded. Use PostgreSQL logs, monitoring time series, or job orchestration to record start/end times, exit status, and duration.

### 2.5. Permissions

Users need appropriate statistics-reading privileges. Depending on version, sensitive columns such as query text may be masked for unprivileged users. Roles like `pg_monitor` and `pg_read_all_stats` can be granted following least privilege. Never grant superuser solely to view dashboards.

### 2.6. Version differences

Progress views and columns have been added across major releases. A query referencing a newer column will fail on older servers. Always check the catalog on the deployed version:

~~~sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name LIKE 'pg_stat_progress_%'
ORDER BY table_name, ordinal_position;
~~~

Not every system view is documented identically in `information_schema` across all versions; you can inspect `pg_catalog` or `\d+ pg_catalog.pg_stat_progress_vacuum` in `psql`.

## 3. Relevant Progress Views

| View | Tracked Operations | Sample Counters / Fields |
| --- | --- | --- |
| `pg_stat_progress_vacuum` | Manual VACUUM and autovacuum | heap blocks, dead tuples, index vacuum count |
| `pg_stat_progress_analyze` | ANALYZE | sample rows, inheritance sample rows, phase |
| `pg_stat_progress_cluster` | CLUSTER and VACUUM FULL | heap blocks scanned/written, tuples |
| `pg_stat_progress_create_index` | CREATE INDEX, REINDEX | lockers, blocks, tuples, partitions |
| `pg_stat_progress_copy` | COPY FROM/TO | bytes processed/total, tuples processed/excluded |
| `pg_stat_progress_basebackup` | pg_basebackup | backup bytes, tablespaces, phase |

Exact views and columns depend on major version. `pg_stat_progress_basebackup` reflects base backups served by the server via replication protocol; it does not track every external backup tool or filesystem snapshot mechanism.

## 4. General Workflow for Monitoring an Operation

### 4.1. Identify the PID and operation type

First inspect active sessions:

~~~sql
SELECT
    pid,
    backend_type,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

`backend_type` exists in modern versions; omit it if targeting an older server without that column.

### 4.2. Query the matching progress view

Depending on the command, query the corresponding view. There is no single unified progress view across all operation types.

### 4.3. Join for context

General pattern:

~~~sql
SELECT
    p.pid,
    a.usename,
    a.datname,
    a.application_name,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    p.phase
FROM some_progress_view AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

Replace `some_progress_view` and `phase` with the actual view and columns. Not every progress view uses the same `phase` column name.

### 4.4. Compute percentages when a valid total exists

When counters share the same unit and total is greater than zero:

\[
\text{Progress \%} =
\frac{\text{Done}}{\text{Total}} \times 100
\]

If total is zero, NULL, or not yet estimated, display `unknown`/NULL rather than dividing by zero or reporting 100%.

### 4.5. ETAs are only estimates

You can estimate rate from two snapshots separated by a time interval:

\[
\text{Rate} = \frac{\Delta \text{Done}}{\Delta t}
\]

\[
\text{ETA} \approx \frac{\text{Total} - \text{Done}}{\text{Rate}}
\]

This estimate holds only when total is stable, counters advance monotonically, and the operation maintains steady speed. Phase transitions, waits, disk contention, parallel workers, and shifting workloads skew ETAs. For operations without a known total, do not display fabricated ETAs.

### 4.6. Observe over time

Re-run queries every few seconds or collect via a monitoring agent. Avoid polling so aggressively that it adds unnecessary load. Record timestamps, PID, relation, phase, and counters to plot time series.

### 4.7. When a task disappears from the view

When a progress row vanishes, the operation may have finished, been canceled, crashed its backend, or transitioned into an uninstrumented step. Check `pg_stat_activity`, client exit status, server logs, and the job runner to tell them apart.

## 5. Monitoring VACUUM and Autovacuum

### 5.1. What does VACUUM do?

PostgreSQL uses MVCC. `UPDATE` and `DELETE` leave behind obsolete row versions; `VACUUM` identifies tuples no longer visible to any active snapshot, marks their space reusable, updates visibility and free-space metadata, and helps prevent transaction ID wraparound.

`VACUUM` normally does not rewrite the entire table. It processes the heap and indexes in phases, so a run can spend significant time in index cleanup or waiting to truncate trailing empty pages.

### 5.2. Progress view

`pg_stat_progress_vacuum` tracks both manual `VACUUM` and autovacuum workers. Key columns:

| Column | Meaning |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | OID of the relation being vacuumed |
| `phase` | Current phase |
| `heap_blks_total` | Total heap blocks to process |
| `heap_blks_scanned` | Heap blocks scanned |
| `heap_blks_vacuumed` | Heap blocks vacuumed |
| `index_vacuum_count` | Number of index vacuum cycles completed |
| `max_dead_tuples` | Capacity of the dead-tuple store |
| `num_dead_tuples` | Dead tuples currently held in the store |

### 5.3. VACUUM phases

| Phase | Work Performed |
| --- | --- |
| `initializing` | Preparing VACUUM and required structures |
| `scanning heap` | Scanning heap, finding dead tuples, updating metadata |
| `vacuuming indexes` | Cleaning index entries pointing to dead tuples |
| `vacuuming heap` | Processing identified heap pages and tuples |
| `cleaning up indexes` | Finalizing index structures after vacuum cycles |
| `truncating heap` | Potentially truncating empty pages at the end of the relation |
| `performing final cleanup` | Completing final bookkeeping and cleanup |

Phases can repeat across dead-tuple cleanup cycles; never assume each phase runs only once.

### 5.4. Query to monitor VACUUM progress

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    round(
        100.0 * p.heap_blks_scanned /
        NULLIF(p.heap_blks_total, 0),
        1
    ) AS scan_percent,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.num_dead_tuples,
    p.max_dead_tuples,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

`scan_percent` measures only heap blocks scanned. It is not overall VACUUM completion percentage. In the `vacuuming indexes` phase, scanning may already be done while substantial work remains.

### 5.5. Scan progress vs. vacuum progress

`heap_blks_scanned` tracks scan progress; `heap_blks_vacuumed` tracks heap blocks processed. The two counters need not match. Blocks may need no vacuuming or may be skipped depending on visibility status.

Never compute `(` `heap_blks_scanned` + `heap_blks_vacuumed` `) /` `heap_blks_total` because the two counters are not disjoint halves of one total.

### 5.6. Monitoring autovacuum

Autovacuum workers also appear in `pg_stat_progress_vacuum`. Use `pg_stat_activity.backend_type` on supported versions or query/application metadata to distinguish workers.

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_scanned,
    p.heap_blks_total,
    p.num_dead_tuples,
    a.backend_type,
    a.query_start,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_vacuum AS p
JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

If `backend_type` does not exist on an older server, omit that column. Autovacuum workers run either VACUUM or ANALYZE depending on triggers and configuration; check query/command context when needed.

### 5.7. Dead tuples and index vacuum cycles

`num_dead_tuples` tracks dead tuples currently buffered in memory; once the store hits capacity, VACUUM cleans indexes and resumes scanning/cleanup. `index_vacuum_count` increments with each index vacuum cycle.

A table with huge dead tuple counts or many indexes may require multiple cycles. Do not assume VACUUM is hung just because `vacuuming indexes` lasts a long time; inspect I/O, locks, counters, and logs.

### 5.8. VACUUM can wait or be slowed by workload

Factors that slow VACUUM:

- Large tables with massive dead tuple counts;
- Many indexes requiring cleanup;
- Slow storage I/O or storage contention;
- Low `maintenance_work_mem` causing extra index vacuum cycles;
- Long-running transactions or replication slots pinning `xmin` and preventing tuple reclamation;
- I/O throttling and cost delays;
- Lock or DDL contention;
- WAL and checkpoint pressure.

VACUUM normally takes relatively light locks, yet it can still conflict with certain DDL or operations. Monitor wait events and blockers.

### 5.9. VACUUM FULL uses a different progress view

`VACUUM FULL` rewrites the entire relation and requires an `ACCESS EXCLUSIVE` lock. Its progress is reported in `pg_stat_progress_cluster`, not `pg_stat_progress_vacuum`. `CLUSTER` uses this same view.

### 5.10. Monitoring ANALYZE

`pg_stat_progress_analyze` tracks `ANALYZE` where supported by the server. Counters typically include sample blocks, extended statistics, and child tables; phases can include acquiring sample rows, computing statistics, and finalizing.

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.sample_blks_total,
    p.sample_blks_scanned,
    p.ext_stats_total,
    p.ext_stats_computed,
    p.child_tables_total,
    p.child_tables_done,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_analyze AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

Exact columns can differ across major versions. `ANALYZE` samples rows; sample block counters do not represent total table blocks read. Some phases lack totals suited for percentage calculations.

### 5.11. Monitoring VACUUM FULL and CLUSTER

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.command,
    p.phase,
    p.heap_tuples_scanned,
    p.heap_tuples_written,
    p.heap_blks_total,
    p.heap_blks_scanned,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_cluster AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

`command` distinguishes `CLUSTER` from `VACUUM FULL`. Phases include scanning the heap, sorting tuples, writing the new heap, swapping relation files, rebuilding indexes, and final cleanup depending on command and version.

### 5.12. When VACUUM runs for a long time

Check:

1. Whether phases and counters are advancing across snapshots;
2. Whether `pg_stat_activity` shows a wait event;
3. Blocking DDL or transactions;
4. Long-running transactions and replication slots holding `xmin`;
5. Dead tuple volume, table size, and index count;
6. Disk latency, throughput, and free space;
7. Autovacuum logs, cost delays, and worker limits.

Never kill VACUUM solely due to high elapsed time. First determine whether it is making progress, waiting on a lock, waiting on I/O, or held back by an old transaction.

## 6. Monitoring CREATE INDEX and REINDEX

### 6.1. Why do index builds need progress reporting?

Building an index can scan millions or billions of rows, sort tuples, write index pages, and wait on concurrent transactions. With `CREATE INDEX CONCURRENTLY`, PostgreSQL runs additional validation steps and waits for old transactions and snapshots to guarantee index consistency under concurrent writes.

### 6.2. Progress view

`pg_stat_progress_create_index` tracks `CREATE INDEX`, `CREATE INDEX CONCURRENTLY`, `REINDEX`, and related variants where supported.

| Column | Meaning |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | Table being indexed |
| `index_relid` | OID of index being created or rebuilt |
| `command` | `CREATE INDEX` or `REINDEX` command |
| `phase` | Current phase |
| `lockers_total`, `lockers_done` | Transactions/lockers to wait for and already cleared in the relevant phase |
| `current_locker_pid` | PID of the locker currently awaited, if any |
| `blocks_total`, `blocks_done` | Block progress in the current phase |
| `tuples_total`, `tuples_done` | Tuple progress in the current phase |
| `partitions_total`, `partitions_done` | Partition progress for partitioned indexes |

Counter meanings and updates depend on the current phase; not every counter is populated meaningfully in every phase.

### 6.3. Key phases

| Phase | Interpretation |
| --- | --- |
| `initializing` | Preparing index build |
| `waiting for writers before build` | Waiting for concurrent writers before starting the build |
| `building index` | Scanning table and building the index |
| `waiting for writers before validation` | Waiting for writers before validating a concurrent build |
| `index validation: scanning index` | Scanning index for validation |
| `index validation: sorting tuples` | Sorting tuple identifiers for validation |
| `index validation: scanning table` | Scanning table to verify index entries |
| `waiting for old snapshots` | Waiting for old snapshots no longer needed |
| `waiting for readers before marking dead` | Waiting for readers before marking old/invalid index state during cleanup |

Some phases appear only for concurrent builds or specific variants. Verify phase names and counters against your PostgreSQL major version.

### 6.4. Query to monitor index builds

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS table_name,
    p.index_relid::regclass AS index_name,
    p.command,
    p.phase,
    p.lockers_total,
    p.lockers_done,
    p.current_locker_pid,
    p.blocks_total,
    p.blocks_done,
    round(
        100.0 * p.blocks_done / NULLIF(p.blocks_total, 0),
        1
    ) AS blocks_percent,
    p.tuples_total,
    p.tuples_done,
    p.partitions_total,
    p.partitions_done,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_create_index AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

`blocks_percent` reflects block progress only during phases where block counters apply. During locker-wait or old-snapshot-wait phases, counters remain flat; that alone does not mean the backend is deadlocked or stuck.

### 6.5. Monitoring partitioned indexes

When building an index on a partitioned table, the progress view exposes `partitions_total` and `partitions_done`. Use them to see how many partitions are finished, without extrapolating remaining bytes or time directly since partitions vary in size.

### 6.6. Standard CREATE INDEX vs. CONCURRENTLY

Standard `CREATE INDEX` blocks table writes during the build due to its lock mode. It is usually faster and suited to maintenance windows.

`CREATE INDEX CONCURRENTLY` allows INSERT/UPDATE/DELETE operations to continue through most of the build, at the cost of extra work, additional wait/validation phases, and longer total runtime. It cannot run inside a transaction block.

### 6.7. Why does a concurrent build stall in a wait phase?

`CREATE INDEX CONCURRENTLY` can block waiting for old transactions or snapshots. Check:

- `current_locker_pid`;
- `pg_stat_activity.xact_start` and `backend_xmin`;
- Long-running queries and transactions;
- `idle in transaction` sessions;
- Prepared transactions;
- Replication feedback and standby snapshots where applicable.

Never blindly raise `lock_timeout` or cancel blockers without knowing what those transactions are doing.

### 6.8. Identifying the blocker

~~~sql
SELECT
    p.pid AS index_build_pid,
    p.phase,
    p.current_locker_pid,
    a.usename AS blocker_user,
    a.datname AS blocker_database,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_create_index AS p
LEFT JOIN pg_stat_activity AS a
  ON a.pid = p.current_locker_pid;
~~~

`current_locker_pid` may be NULL outside locker-wait phases. Use `pg_blocking_pids()` and `pg_locks` to investigate other lock relationships.

### 6.9. Canceled index builds

If `CREATE INDEX CONCURRENTLY` is canceled or fails, it can leave behind an invalid index. Check the catalog:

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
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

An invalid index is ignored by the planner for queries, yet it still consumes disk space and in some states continues incurring maintenance overhead. Identify why it failed, then DROP or REINDEX through proper procedures; never delete index files manually.

### 6.10. Monitoring parallel index builds

Parallel index builds can spawn multiple workers. The main progress row belongs to the leader backend executing the command; workers do not necessarily create separate progress rows. Monitor CPU, I/O, and `pg_stat_activity` to observe worker activity.

### 6.11. REINDEX and REINDEX CONCURRENTLY

`REINDEX` rebuilds indexes and acquires strong locks depending on mode. `REINDEX CONCURRENTLY` minimizes blocking while adding wait/validation phases and higher resource cost. The progress view distinguishes active building from waiting on readers/writers.

### 6.12. Post-build verification

After the command finishes:

- Verify the client received success;
- Check `pg_index.indisvalid` and `indisready`;
- Confirm the index exists in the expected schema;
- Verify query plans where needed;
- Monitor disk usage, WAL generation, and replication lag;
- Inspect logs if the build failed.

Reaching 100% in one phase does not mean the entire command committed successfully.

## 7. Monitoring COPY FROM and COPY TO

### 7.1. Progress view

`pg_stat_progress_copy` tracks running server-side `COPY` commands. Key columns:

| Column | Meaning |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | Target/source relation; may be 0 for query-based `COPY ... TO` |
| `command` | `COPY FROM` or `COPY TO` |
| `type` | Data source/destination such as `FILE`, `PROGRAM`, `PIPE`, or `CALLBACK` |
| `bytes_processed` | Bytes processed so far |
| `bytes_total` | Total bytes if known by the server |
| `tuples_processed` | Tuples processed |
| `tuples_excluded` | Tuples excluded by a `WHERE` clause on supported versions |

Some columns and semantics depend on major version. For example, `tuples_excluded` supports `COPY FROM ... WHERE` in newer releases.

### 7.2. Query to monitor COPY

~~~sql
SELECT
    p.pid,
    p.datname,
    CASE
        WHEN p.relid = 0 THEN NULL
        ELSE p.relid::regclass::text
    END AS relation,
    p.command,
    p.type,
    p.bytes_processed,
    p.bytes_total,
    round(
        100.0 * p.bytes_processed / NULLIF(p.bytes_total, 0),
        1
    ) AS bytes_percent,
    p.tuples_processed,
    p.tuples_excluded,
    now() - a.query_start AS elapsed,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_copy AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

When `bytes_total` is 0 or unknown, `bytes_percent` evaluates to NULL. Track `tuples_processed` as an activity counter, without dividing by a nonexistent total.

### 7.3. COPY FROM a file on the server

With `COPY table FROM '/path/file.csv'`, the server process reads the file directly. `bytes_total` is typically known when the source is a regular file whose metadata the server can stat. Server-side file access requires filesystem permissions for the PostgreSQL OS user as well as appropriate SQL privileges.

### 7.4. COPY FROM STDIN and psql \copy

With `COPY ... FROM STDIN`, the client streams data over the connection. The server usually does not know total byte size until the stream ends, so no reliable total is available.

The `psql` `\copy` command reads/writes the file on the client machine and streams over the connection. On the server, it still appears as a `COPY` via pipe/callback; the server cannot read local file paths on the client machine.

### 7.5. COPY TO file and COPY TO STDOUT

`COPY table TO '/path/file.csv'` writes a server-side file. `COPY ... TO STDOUT` streams bytes back to the client. For query-based `COPY TO`, `relid` may not identify a single table; inspect `command` and query text to identify the source.

### 7.6. Measuring COPY throughput

Sample `bytes_processed` or `tuples_processed` at two timestamps:

\[
\text{Throughput} =
\frac{\text{Counter}_{t2} - \text{Counter}_{t1}}{t2-t1}
\]

Units are bytes/s or tuples/s. If a counter resets due to a new backend, changed PID, or completed command, start a fresh series.

### 7.7. Why can COPY be slow?

Common bottlenecks:

- Disk or network throughput;
- Source file sitting on slow storage;
- Slow client upload or download;
- WAL generation and synchronous replication;
- Index, foreign key, and trigger maintenance during `COPY FROM`;
- Constraint checks;
- Row-level security or character encoding conversion;
- Lock contention;
- Checkpoint and I/O pressure;
- Compression/decompression on the client or pipeline.

### 7.8. COPY FROM can increase replication lag

Bulk loads generate WAL rapidly. If standbys or WAL archiving fall behind, potential RPO exposure and WAL disk retention risk grow. Monitor `pg_stat_replication`, `pg_stat_archiver`, replication slots, and disk space during large imports.

### 7.9. Canceled or failed COPY

When `COPY` fails, its progress row disappears and the transaction rolls back partial changes per transaction semantics. Inspect client errors, server logs, and transaction status. Never assume the last observed counter represents committed rows.

### 7.10. COPY and client-side monitoring

When using `psql \copy`, GUIs, ETL tools, or application drivers, the client may display its own progress. The server progress view reflects bytes/tuples processed on the server, which can differ from client-side bytes read or final written file sizes.

## 8. Monitoring pg_basebackup

### 8.1. Progress view

`pg_stat_progress_basebackup` tracks running `pg_basebackup` jobs connected to the server over the replication protocol. It typically includes:

| Column | Meaning |
| --- | --- |
| `pid` | PID of the server-side replication connection |
| `phase` | Current backup phase |
| `backup_total` | Estimated total backup bytes |
| `backup_streamed` | Database file bytes streamed so far |
| `tablespaces_total` | Total number of tablespaces to transfer |
| `tablespaces_streamed` | Number of tablespaces completed |
| `tablespace_total` | Total bytes for the current tablespace |
| `tablespace_streamed` | Bytes streamed for the current tablespace |

Totals may be unknown early on or vary by format and metadata. Never compute percentages when total is zero.

### 8.2. Base backup phases

| Phase | Interpretation |
| --- | --- |
| `initializing` | Preparing backup |
| `waiting for checkpoint to finish` | Waiting for the required starting checkpoint to complete |
| `estimating backup size` | Estimating total backup size |
| `streaming database files` | Streaming data files and tablespaces |
| `waiting for WAL archiving to finish` | Waiting for WAL archiving when required by the backup method |
| `transferring WAL files` | Transferring WAL files into the backup |

Phase names and behavior depend on version and WAL method. `pg_basebackup` may wait for WAL archiving in certain `-X fetch` configurations.

### 8.3. Query to monitor base backups

~~~sql
SELECT
    p.pid,
    p.phase,
    p.backup_total,
    p.backup_streamed,
    round(
        100.0 * p.backup_streamed / NULLIF(p.backup_total, 0),
        1
    ) AS backup_percent,
    p.tablespaces_total,
    p.tablespaces_streamed,
    p.tablespace_total,
    p.tablespace_streamed,
    now() - a.backend_start AS connection_age,
    a.usename,
    a.application_name,
    a.client_addr,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_basebackup AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

`backup_percent` reflects streamed database file bytes relative to the estimated total and does not capture post-transfer WAL steps identically. Once the phase enters WAL waiting/transfer, byte percentage can pause even while the backup continues progressing.

### 8.4. pg_basebackup and WAL methods

- `-X stream`: streams WAL in parallel with database files; database file byte progress can finish before the WAL stream finishes.
- `-X fetch`: fetches WAL at the end of the backup; may wait for archiving and requires all WAL segments from backup start through end.
- `-X none`: omits WAL from the backup; relies on an external WAL process to ensure recoverability and consistency.

Check documentation for your major version to confirm options and requirements.

### 8.5. Large backups and multiple tablespaces

With multiple tablespaces, `tablespaces_streamed` shows completed tablespace count; `tablespace_streamed/total` reflects the active tablespace. Do not add counters with different scopes to compute an overall percentage.

### 8.6. Backup progress is not backup verification

The progress row disappears once the server closes the backup replication connection. That does not prove all files landed intact, the manifest is valid, or the backup is restorable. Use `pg_verifybackup` where supported by format and major version, and perform regular restore tests.

### 8.7. External backup managers

`pg_stat_progress_basebackup` tracks `pg_basebackup`. Tools such as pgBackRest, Barman, or cloud backup providers may use their own mechanisms and will not necessarily appear in this view. Monitor those tools' native metrics and logs alongside PostgreSQL activity.

### 8.8. Backup progress and WAL archiving

A base backup can stream data quickly yet stall waiting on WAL. Inspect `pg_stat_archiver`, archive command errors, network/object-storage latency, and WAL retention. Do not conclude a backup is hung merely because `backup_percent` pauses during a wait phase.

### 8.9. Backup client disconnected

If the `pg_basebackup` client disconnects, the server's replication connection closes and the progress row disappears. Inspect client exit codes and output, server logs, slot states, and the output directory; clean up or handle partial backups per backup tool policy.

### 8.10. Monitoring concurrent backups

Each replication connection has its own PID. Use `application_name`, `client_addr`, and connection start times to distinguish jobs. Set clear application names where supported, and avoid running too many concurrent base backups that compete for I/O and network bandwidth.

## 9. Combining Progress with Activity, Locks, and Statistics

### 9.1. Progress shows advancement; activity shows wait state

A task's counters can stall while waiting on locks, I/O, WAL, network, or other transactions. Combine:

- Progress view: phase and counters;
- `pg_stat_activity`: state, query, transaction age, wait events;
- `pg_locks` / `pg_blocking_pids()`: lock blockers;
- OS/cloud metrics: disk, CPU, network;
- PostgreSQL logs: errors, cancellations, checkpoint details.

Never declare a task hung based on a single snapshot.

### 9.2. Finding blocking sessions

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_duration,
    blocked.wait_event_type,
    blocked.wait_event,
    left(blocked.query, 250) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 250) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = b.pid
ORDER BY blocked.query_start;
~~~

`pg_blocking_pids()` can return multiple blockers. A task may be waiting behind an `idle in transaction` session; inspect the blocker's query and `xact_start` to trace the cause.

### 9.3. Finding long transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long-running transactions pin old snapshots, blocking VACUUM tuple reclamation or forcing concurrent index builds to stall in `waiting for old snapshots`. Never terminate solely by age; verify owner and business impact first.

### 9.4. Checking table maintenance counters

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

These are cumulative/estimated statistics, not live VACUUM progress. `n_live_tup` and `n_dead_tup` are estimates; use them to prioritize tables for inspection rather than treating them as exact counts.

### 9.5. Checking index usage after a build

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 50;
~~~

A newly created index may show zero scans initially if matching queries have not yet run. Never drop an index just because `idx_scan = 0` over a short observation window.

### 9.6. Monitoring database-level COPY/tuple activity

~~~sql
SELECT
    datname,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

These counters accumulate database-wide and are not exclusive to COPY. They corroborate overall activity without replacing `pg_stat_progress_copy`.

### 9.7. Monitoring WAL/archiving during bulk loads and backups

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

Combine with `pg_stat_replication` to watch standby send, write, flush, and replay lag. Large COPY jobs or index builds accelerate WAL generation, stressing standbys and archiving.

### 9.8. Statistics snapshots and polling

Statistics views follow transaction/version snapshot caching rules. Running repeated queries inside one transaction may return stale numbers. Use autocommit or `pg_stat_clear_snapshot()` when fresh snapshots are required on supported versions.

Progress views generally reflect current backend state; even so, poll with sensible intervals rather than tight continuous loops.

## 10. Designing a Progress Dashboard

### 10.1. Common fields

A unified dashboard table should include:

| Field | Purpose |
| --- | --- |
| `collected_at` | Snapshot timestamp |
| `server/cluster` | Source identifier |
| `pid` | Backend PID |
| `database` | Database |
| `relation/index` | Target object |
| `operation` | `VACUUM`, `INDEX`, `COPY`, `BASEBACKUP` |
| `phase` | Current phase |
| `done/total` | Counters and units |
| `percent` | Shown only when total is valid |
| `elapsed` | Elapsed runtime |
| `wait_event` | Current wait cause |
| `application_name` | Job/client owner |

Because each view has a distinct schema, have the collector normalize each operation into its own typed metrics instead of forcing unrelated counters into one SQL query.

### 10.2. Never combine counters with mismatched units

Never sum heap blocks with tuples, bytes with partitions, or locker counts into a single percentage. Every metric must preserve its unit and matching total.

### 10.3. Phase timeline

Store phase transitions keyed by PID + start timestamp. An operation can shift phases repeatedly; a timeline view reveals prolonged wait periods far better than a single snapshot.

### 10.4. Handling PID reuse

OS PIDs can be reused after a backend exits. Key series by server identity, PID, and backend/query start timestamp; never use PID alone as a long-lived identifier.

### 10.5. Display unknown clearly

If total is zero, NULL, or uncomputed, display “N/A” or “unknown.” Never emit `0%` (which implies a known total with zero work done) and never emit `100%`.

### 10.6. Distinguish active processing from waiting

A progress phase remains populated while the backend waits. Display wait event type/name, blockers, and elapsed time. Dashboard colors should distinguish “processing,” “waiting,” “completed,” and “failed” based on real state.

### 10.7. Recording task history

Progress views do not retain history. A collector can sample counters every 5–15 seconds depending on workload, capturing phase transitions, operation start/end, and client outcomes. For short operations, rely on logs and job runners since polling can miss them entirely.

### 10.8. Labels and cardinality

Avoid stuffing full query text, churning PIDs, or unbounded relation names into time-series metric labels when the monitoring backend has high cardinality costs. Keep query text in access-controlled logs and use stable metric labels.

### 10.9. Per-operation dashboard focus

- VACUUM: relation, phase, heap blocks scanned/vacuumed, dead tuples, transaction age;
- Index: table/index, command, phase, blocks/tuples, lockers/current blocker;
- COPY: direction/type, bytes/tuples, total availability, throughput;
- Base backup: phase, bytes streamed, tablespace progress, WAL/archive waits.

### 10.10. Dashboards do not replace runbooks

Each panel and alert should link to diagnostic guidance: which phases are normal, which counters should advance, which blockers may be terminated safely, and when to escalate.

## 11. Alerting and Monitoring Thresholds

### 11.1. Alert on state, not elapsed time alone

A 3-hour VACUUM on a massive table can be normal; a concurrent index build waiting 10 minutes on a lock needs attention. Base alerts on operation type, phase, counter advancement, wait events, and workload impact.

### 11.2. VACUUM alerts

Watch for:

- Autovacuum not running or consistently lagging behind write rates;
- Sustained growth in `n_dead_tup`;
- Tables unvacuumed or unanalyzed past expected windows;
- Long-running transactions pinning `xmin`;
- Transaction ID age approaching wraparound danger;
- Growing `pg_wal`/disk pressure from workload or slot retention;
- VACUUM repeatedly stalling in wait phases.

Do not alert solely on an old `last_autovacuum`; rarely modified tables may not need recent vacuuming.

### 11.3. Transaction ID wraparound

Monitor `datfrozenxid` age:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

This is a critical cluster/database health signal. When XID age climbs high, prioritize anti-wraparound autovacuum and freeze progress; never disable autovacuum to save load without an alternative plan.

### 11.4. Index build alerts

Alert when:

- A build waits on lockers or old snapshots beyond policy limits;
- Blocks/tuples stay flat while the backend is active;
- Build I/O degrades production latency;
- A concurrent build fails or is canceled;
- Invalid indexes remain after completion.

Elapsed thresholds must differ between `CREATE INDEX` and `CREATE INDEX CONCURRENTLY` and scale with table size.

### 11.5. COPY alerts

Alert on:

- Throughput dropping sharply relative to baseline;
- `bytes_total` known while progress stalls;
- Runtime far exceeding expectations for file/row volume;
- Rising WAL, replication, or archive lag;
- Low disk space;
- COPY errors or retries in the client pipeline.

For STDIN/STDOUT without a known total, monitor throughput and client-side progress rather than percentage.

### 11.6. Base backup alerts

Watch for:

- Backup failing to start or finish within its window;
- Prolonged checkpoint or WAL archive wait phases;
- Stalled `backup_streamed` bytes;
- Client disconnects or failures;
- Missing backup manifest or failed verification;
- WAL archive gaps;
- Storage quota or capacity pressure;
- Backup age breaching RPO or retention policy.

Verify backup success via exit status and artifact/manifest checks, not merely by the progress row disappearing.

### 11.7. Alert by business impact

Set thresholds around:

- Maintenance windows;
- Peak workload hours;
- RPO/RTO targets;
- Disk free headroom;
- Latency and error budgets;
- Maximum tolerated lock wait;
- Backup completion deadlines.

Exact thresholds must come from baselines and restore/failover drills.

### 11.8. Avoiding alert storms

Group alerts by operation, PID, or table, and use pending durations and hysteresis to prevent flapping. Once an incident owner begins handling an operation, preserve annotations so later on-call responders do not duplicate investigation.

## 12. Task-by-Task Troubleshooting

### 12.1. VACUUM scan percentage is stuck

Check:

1. Current phase;
2. `wait_event_type` and `wait_event`;
3. Disk throughput and latency;
4. Blocking locks;
5. Long-running transactions and `backend_xmin`;
6. Autovacuum cost delays and worker availability;
7. Whether scanning finished (`100%`) and work is now in index/cleanup phases.

### 12.2. VACUUM stays in vacuuming indexes for a long time

Check index count, index sizes, `maintenance_work_mem`, dead tuple volume, storage latency, and `index_vacuum_count`. A VACUUM run can require multiple cycles; track counters across multiple snapshots.

### 12.3. VACUUM FULL has no row in pg_stat_progress_vacuum

This is expected behavior. `VACUUM FULL` is tracked in `pg_stat_progress_cluster`. Also check whether the session is still waiting to acquire `ACCESS EXCLUSIVE` lock before starting.

### 12.4. Autovacuum never appears

Verify autovacuum is enabled, worker limits, per-table storage parameters, thresholds and scale factors, transaction age, logs, and whether the table crossed trigger thresholds. Infrequently updated tables may not trigger autovacuum.

### 12.5. CREATE INDEX stalls at waiting for writers

Check `current_locker_pid`, `pg_stat_activity`, transaction age, and application owner. Locate which session holds an open transaction and coordinate with its owner before canceling or terminating.

### 12.6. CREATE INDEX CONCURRENTLY stalls at waiting for old snapshots

Locate long-running transactions, `idle-in-transaction` sessions, prepared transactions, and standby feedback. One old snapshot can keep validation from completing even after the index itself is nearly built.

### 12.7. CREATE INDEX fails yet the index remains in the catalog

Check `pg_index.indisvalid`, `indisready`, and server logs. Invalid indexes can remain after failed concurrent builds. Confirm the planner is not using it, then drop or rebuild following supported procedures.

### 12.8. COPY bytes percent is missing

If `bytes_total` is zero or NULL, the server does not know the total size. This is normal for STDIN/STDOUT or streaming inputs. Monitor `tuples_processed`, byte throughput, and client metrics.

### 12.9. Low COPY throughput

Break down time across reading source data, network transfer, parsing/conversion, inserts, index/constraint/trigger maintenance, and WAL flushes. Benchmark source storage, client network, and server storage separately to isolate the bottleneck.

### 12.10. COPY finishes with an unexpected row count

Check client row counts, `WHERE` clauses where supported, error/reject handling per version, duplicate/constraint errors, transaction rollbacks, and filtered rows. Progress counters do not prove committed row counts.

### 12.11. pg_basebackup stalls waiting on WAL archiving

Check `archive_mode`, `archive_command`, `pg_stat_archiver`, archive destination permissions/network, and required WAL segments. Never delete needed WAL segments to “free up” archiving.

### 12.12. pg_basebackup bytes stop advancing

Check server-side wait events, source disk I/O, client disk throughput, network, tablespace mounts, and the client process. Verify the process is alive and not blocked on filesystem or object storage.

### 12.13. Backup progress row disappears

Check client exit code, logs, and backup directory/manifest. Disappearance can indicate success, failure, or client disconnection.

### 12.14. Monitoring query fails with column does not exist

Check PostgreSQL major version and available progress view columns. Adapt queries per version; never deploy one dashboard query assuming identical schemas across all server versions.

### 12.15. User cannot see query text

Check statistics permissions and role memberships. Grant `pg_monitor` or `pg_read_all_stats` per policy if appropriate; never grant superuser broadly.

## 13. Operational Workflow for Maintenance Windows

### 13.1. Before starting

Record:

- Target database, table, and indexes;
- Current heap/index sizes and row estimates;
- Dead tuple estimates;
- Workload and peak hours;
- Disk headroom and I/O baseline;
- Replication lag and WAL archive health;
- Expected locking impact;
- Operation owner and cancellation plan.

### 13.2. During execution

1. Record PID and `query_start`;
2. Poll the appropriate progress view;
3. Track phases, counters, and wait events;
4. Watch application latency and I/O;
5. Watch standby and archive lag;
6. Identify blockers and escalation owners;
7. Avoid changing multiple parameters before diagnosing the bottleneck.

### 13.3. Upon completion

Verify client exit status, logs, catalog state, and workload impact. For VACUUM/ANALYZE, verify table statistics; for index builds, verify validity; for COPY, reconcile row counts and constraints; for backups, verify the manifest and run restore tests.

### 13.4. When cancellation is needed

Prefer `pg_cancel_backend(pid)` to request query cancellation. Consider `pg_terminate_backend(pid)` only when stopping the entire session is necessary and rollback impact has been evaluated. Never kill the postmaster or delete relation/WAL files to stop an operation.

### 13.5. Post-maintenance

Re-measure latency, query plans, dead tuples, replication lag, WAL/archive backlogs, and disk space. Record actual total and per-phase durations in the runbook to improve future forecasts.

## 14. Lab Practice Examples

### 14.1. Prepare a test table

~~~sql
CREATE TABLE progress_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO progress_demo (payload)
SELECT repeat(md5(g::text), 4)
FROM generate_series(1, 1000000) AS g;
~~~

Scale lab data size to fit your machine. Never run large bulk loads in production just to observe progress.

### 14.2. Observe VACUUM

~~~sql
UPDATE progress_demo
SET payload = payload || 'x'
WHERE id % 3 = 0;

DELETE FROM progress_demo
WHERE id % 5 = 0;

VACUUM (VERBOSE) progress_demo;
~~~

In another session, repeatedly query `pg_stat_progress_vacuum` to watch phases and counters. On small tables, the operation may finish before the first poll.

### 14.3. Observe ANALYZE

~~~sql
ANALYZE progress_demo;
~~~

Query `pg_stat_progress_analyze` from a second session. Sampling is quick on small tables; increase lab size or pick a larger table to watch it clearly.

### 14.4. Observe CREATE INDEX

~~~sql
CREATE INDEX progress_demo_payload_idx
ON progress_demo (payload);
~~~

Watch `pg_stat_progress_create_index`. Repeat in the lab using `CREATE INDEX CONCURRENTLY` outside a transaction block to observe validation and wait phases.

### 14.5. Observe COPY

~~~sql
COPY progress_demo TO '/tmp/progress_demo.csv' WITH (FORMAT csv, HEADER true);
~~~

The path must exist and be writable by the PostgreSQL server OS user. Without server filesystem access, use `COPY ... TO STDOUT` or client `\copy` and observe server-side bytes/tuples as supported.

### 14.6. Observe base backups

Run `pg_basebackup` from a lab server with replication access and watch `pg_stat_progress_basebackup` on the source server. Set `application_name` if supported by the client/tool to identify the job, and avoid overlapping heavy backups that saturate I/O.

### 14.7. Record snapshots

Capture progress query results periodically into a file or monitoring store. Compare counters across intervals to compute throughput and detect waiting phases.

## 15. Limitations to Remember

### 15.1. Not every operation has a progress view

Only instrumented operations appear. Custom SQL queries, extensions, or external backup tools may have no progress view.

### 15.2. There is no universal percentage across all phases

Counters can shift meaning between phases. A block-scan percentage is not total command completion; wait phases lack totals altogether.

### 15.3. Totals can be unknown or estimated

Backup sizes are estimates; COPY streams can have no total; ANALYZE uses sampling. Display unknown instead of fabricating denominators.

### 15.4. Progress rows retain no history

Once an operation ends, the row vanishes. You need a collector or logging to retain duration, outcomes, and phase timelines afterward.

### 15.5. Permissions can mask details

Some users cannot view query text or statistics of other sessions. Use an appropriately scoped monitoring role.

### 15.6. Version compatibility

Progress views, counters, and phase names evolve across major versions. Verify documentation and system catalogs on your target server before deploying dashboards.

### 15.7. Polling does not replace OS metrics

Progress views do not expose disk latency, queue depth, CPU steal, network retransmits, or cloud volume throttling. Pair with OS/cloud telemetry to isolate bottlenecks.

### 15.8. Do not over-promise ETA accuracy

Workload and phase shifts cause ETAs to fluctuate. Show ranges or estimates tagged with sample timestamps, or omit ETAs when counters are unsuitable.

## 16. Collecting Progress with psql and Monitoring Agents

### 16.1. Manual polling in psql

Run a progress query in `psql` and repeat it using `\watch`:

~~~sql
SELECT
    pid,
    relid::regclass AS relation,
    phase,
    heap_blks_scanned,
    heap_blks_total
FROM pg_stat_progress_vacuum;
~~~

After executing the query, type `\watch 2` to refresh every two seconds. `\watch` is a `psql` meta-command, not SQL sent to the server.

### 16.2. Polling intervals

Select intervals by task duration:

- Multi-hour operations: 5–30 seconds is usually plenty for dashboards;
- Short operations: log/event-based monitoring works better than polling;
- Busy production servers: avoid polling multiple times per second across all databases.

### 16.3. Separate collector queries by operation type

A monitoring agent should execute dedicated queries for each progress view and tag the operation type. Avoid building dynamic SQL interpolating view names from user input; keep queries explicit, version-aware, and permission-scoped.

### 16.4. Storing history

Record:

- Server identity and database;
- PID plus backend/query start timestamps;
- Relation/index OID and resolved names;
- Operation, command, and phase;
- Counters and units;
- Wait events;
- Collection timestamp;
- Job/client identity.

When an operation finishes, record a terminal event from the client or job runner capturing success/failure/cancellation and total elapsed time.

### 16.5. Never store unbounded query text

Query text may contain sensitive literals. Store it only if policy permits; prefer normalizing/redacting or keeping raw SQL inside access-controlled logs. Metrics should store query fingerprints or operation labels instead of full SQL text.

### 16.6. Monitor health

Monitors themselves can fail. Track the collector's last-success timestamp, query errors, permissions, scrape durations, and missing series. An empty dashboard could mean no tasks are running—or that the monitor lost access to the view.

## 17. Practice Exercises: Progress Reporting

Perform exercises in a PostgreSQL lab. Generate enough workload to observe progress without testing on production. For version-dependent details, check columns and phases on your local server.

### Exercise 1 — Activity vs. progress

Explain the difference between `pg_stat_activity` and `pg_stat_progress_*`. Give one example question each view answers best.

### Exercise 2 — Progress rows

Why does a progress row disappear when an operation finishes? How do you preserve duration and outcome history?

### Exercise 3 — VACUUM counters

Distinguish `heap_blks_scanned` and `heap_blks_vacuumed`. Why must you not sum them to compute a percentage?

### Exercise 4 — VACUUM phases

List the main phases in `pg_stat_progress_vacuum`. Which phase indicates index processing?

### Exercise 5 — Autovacuum

Write a query joining `pg_stat_progress_vacuum` with `pg_stat_activity` to show PID, relation, phase, elapsed time, and wait event.

### Exercise 6 — Long transactions

A VACUUM runs for a long time and dead tuples stop dropping. Write a query to locate long transactions and explain how `backend_xmin` blocks reclamation.

### Exercise 7 — VACUUM FULL

Why does `VACUUM FULL` not appear in `pg_stat_progress_vacuum`? Which view tracks it?

### Exercise 8 — ANALYZE

Explain why sample blocks in `pg_stat_progress_analyze` do not equal total blocks in the table.

### Exercise 9 — Index progress

Write a query showing table, index, command, phase, blocks done/total, and elapsed time from `pg_stat_progress_create_index`.

### Exercise 10 — Concurrent index waits

An index build is stuck in `waiting for old snapshots`. List at least four snapshot or transaction sources to investigate.

### Exercise 11 — Blocker PID

Use `current_locker_pid` to find the session blocking an index build. Explain the limitation when this column is NULL.

### Exercise 12 — Invalid indexes

A `CREATE INDEX CONCURRENTLY` was canceled. Write a query checking `indisvalid` and explain how to handle invalid indexes.

### Exercise 13 — COPY progress

Write a query displaying command, type, bytes processed/total, and tuples processed from `pg_stat_progress_copy`.

### Exercise 14 — COPY STDIN

Why can `bytes_total` be zero for `COPY FROM STDIN`? Which metrics should you use instead of percentage?

### Exercise 15 — psql copy

Distinguish the file path in `COPY FROM '/path'` from `psql`'s `\copy` meta-command. Which host reads the file?

### Exercise 16 — COPY throughput

Two snapshots taken 10 seconds apart show `bytes_processed` increasing from 100 MB to 450 MB. Calculate average throughput.

### Exercise 17 — COPY row counts

Why might `tuples_processed` not equal committed rows? Explain the impact of `WHERE`/excluded rows and transaction rollbacks.

### Exercise 18 — Base backup progress

Write a query reading phase, backup bytes, tablespace progress, and connection context from `pg_stat_progress_basebackup`.

### Exercise 19 — Backup phases

A base backup finished streaming database files, yet its phase is waiting on WAL archiving. Explain why the backup is not yet finished.

### Exercise 20 — WAL methods

Compare `-X stream`, `-X fetch`, and `-X none` in `pg_basebackup`. Which method may wait on archiving at the end?

### Exercise 21 — Backup verification

Why does a disappearing progress row not prove a backup is restorable? Describe the role of `pg_verifybackup`.

### Exercise 22 — External backup managers

A pgBackRest job does not appear in `pg_stat_progress_basebackup`. Why is that normal, and where should you pull metrics instead?

### Exercise 23 — ETA

Explain how to compute throughput and ETA from two snapshots and give three reasons an ETA can be inaccurate.

### Exercise 24 — Phase-aware dashboards

Design a dashboard distinguishing processing, waiting, unknown total, completed, and failed states. Which counters must never be added together?

### Exercise 25 — Permissions

A monitoring user sees PIDs but cannot see query text. Which privileges should you check, and why should you avoid granting superuser?

### Exercise 26 — VACUUM alerts

Propose alerts for dead tuple growth, autovacuum lag, transaction ID age, and long-running transactions.

### Exercise 27 — Index build alerts

A concurrent index build shows no counter advancement for 15 minutes. Lay out an ordered investigation sequence.

### Exercise 28 — Backup alerts

A backup fails to finish within its window. List metrics and logs to inspect across the server, client, WAL archive, and storage.

### Exercise 29 — PID reuse

Why is PID alone insufficient as a unique task identifier in a time-series database? Propose a composite key.

### Exercise 30 — Capstone: monitoring maintenance and backups

A production PostgreSQL cluster runs VACUUM/autovacuum, concurrent index builds, bulk COPY jobs, and nightly `pg_basebackup`. The team needs dashboards and alerts to catch blocking, stalled progress, WAL pressure, and backup failures.

**Requirements:**

1. Build queries for the four primary progress views.
2. Join `pg_stat_activity` for user, query, elapsed time, and wait events.
3. Design blocker and long-transaction diagnostics.
4. Define completion percentage only when totals are valid.
5. Compute throughput from counter deltas and handle PID reuse.
6. Monitor `pg_stat_archiver`, `pg_stat_replication`, and disk headroom.
7. Distinguish progress views from cumulative statistics and client-side progress.
8. Design alerts around phase, elapsed time, stalled counters, and business impact.
9. Write runbooks for VACUUM, index waits, COPY throughput, and backup WAL waits.
10. Store start/end/exit status history and verify backups after completion.

**Passing criteria:** Dashboards never fabricate percentages when total is unknown, clearly surface blockers and wait reasons, distinguish task progress from final operation outcomes, and provide alerts and runbooks enabling safe on-call action.

## 18. Frequently Asked Questions

### 18.1. Do progress views retain history?

No. They show live backend state. To retain history, use logs, monitoring collectors, or job orchestration recording snapshots and final outcomes.

### 18.2. Why is a query active with no progress row?

The command type may not be instrumented, the server version may lack that view, the operation may have moved to another phase, the backend may no longer be running that task, or the user lacks visibility. Check `pg_stat_activity` and server version.

### 18.3. Can you compute an exact percentage for all of VACUUM?

No single exact percentage covers all of VACUUM. `heap_blks_scanned / heap_blks_total` reflects only scan progress; index cleanup, heap vacuuming, and final cleanup may still remain.

### 18.4. Why is VACUUM FULL in pg_stat_progress_cluster?

`VACUUM FULL` rewrites the relation much like `CLUSTER` operationally, so its progress is reported via the cluster progress view rather than the standard VACUUM view.

### 18.5. Does autovacuum appear in progress views?

Yes. An autovacuum worker performing VACUUM appears in `pg_stat_progress_vacuum`; `ANALYZE` has its own progress view on supported versions.

### 18.6. Why can VACUUM repeat phases?

The in-memory dead tuple store has bounded capacity; VACUUM may clean indexes across multiple passes before resuming heap scanning and cleanup. Watch `index_vacuum_count` and counters over time.

### 18.7. Is CREATE INDEX CONCURRENTLY always non-blocking?

It allows writes to proceed for most of the build, yet still includes lock/snapshot wait steps and can be delayed. It is not completely free of workload impact.

### 18.8. Can a canceled index build leave an index behind?

Yes. Check `pg_index.indisvalid`/`indisready` and logs. Clean up invalid indexes via `DROP`/`REINDEX` procedures; never delete files manually.

### 18.9. Why does index build progress stall in a waiting phase?

Usually due to an open transaction, locker, or old snapshot. Inspect `current_locker_pid`, `pg_stat_activity`, transaction age, and blocking relationships.

### 18.10. Is `blocks_percent` total index build progress?

No. It applies only during phases where block counters advance. Concurrent builds still perform validation and wait phases after scanning and building.

### 18.11. Does COPY FROM STDIN have bytes_total?

The server generally cannot know stream length until the entire stream arrives, so `bytes_total` may remain zero. Use `tuples_processed`, throughput, and client-side progress.

### 18.12. Where does `\copy` read files?

`psql` reads the file on the client machine and streams it over the connection. SQL `COPY FROM '/path'` reads the file on the server host using the server process's OS permissions.

### 18.13. Does `tuples_processed` equal committed rows?

Not necessarily. Rows may be excluded, hit errors, or roll back with the transaction. Verify client output, command completion, and post-commit data.

### 18.14. Is pg_basebackup progress on the client or server?

`pg_stat_progress_basebackup` is queried on the PostgreSQL server serving the replication connection. The client `pg_basebackup -P` flag also outputs client-side progress.

### 18.15. Backup bytes reached 100%, yet the job is still running?

It may be waiting on WAL archiving, transferring WAL files, or finishing client-side steps. Check `phase` and client output rather than looking only at byte percentage.

### 18.16. Does pgBackRest appear in pg_stat_progress_basebackup?

Not necessarily. This view is specifically for `pg_basebackup`; use your backup manager's own metrics and logs.

### 18.17. Should I poll progress every 100 ms?

No, not by default. Tight polling adds load with little benefit. Pick intervals proportional to task duration and rely on logs/events for short operations.

### 18.18. Does a monitoring user need superuser?

No. Grant appropriate statistics privileges such as `pg_monitor` or `pg_read_all_stats` per policy. Some fields remain hidden without sufficient privileges.

### 18.19. Why does a progress query say a column does not exist?

Progress view schemas change across major versions. Verify available columns on your server and adapt queries and dashboards accordingly.

### 18.20. Do progress views replace PostgreSQL logs?

No. Progress views show current state; logs record events and errors. Use both together for troubleshooting and recording operational outcomes.

### 18.21. Are ETAs reliable?

They are only estimates from counter deltas. ETAs drift whenever phases change, tasks wait on locks or I/O, or workload speed fluctuates.

### 18.22. What should a dashboard show when total is zero?

Show `unknown` or `N/A`. Never divide by zero and never render `0%` or `100%` when total is unknown.

### 18.23. Why can COPY increase replication lag?

Bulk loads generate WAL quickly. If the network, standby disk/replay, or archiving lags behind, WAL backlogs grow. Watch WAL rate, replication lag, archiving, and disk space.

### 18.24. How do you verify a backup is actually usable?

Check client exit status, manifest verification, WAL continuity, and run restore tests. A vanishing progress row never proves a backup is valid.

### 18.25. Is there one unified progress view for all operations?

No. Each operation has its own progress view with distinct counters and units. A collector can normalize records while preserving original semantics.

## 19. Official PostgreSQL Documentation

Always consult documentation matching your running major version, as progress views, phase names, and columns evolve:

- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): overview of progress reporting and views.
- [VACUUM Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING): `pg_stat_progress_vacuum`.
- [CLUSTER Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CLUSTER-PROGRESS-REPORTING): CLUSTER and VACUUM FULL.
- [CREATE INDEX Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CREATE-INDEX-PROGRESS-REPORTING): index build phases and counters.
- [COPY Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#COPY-PROGRESS-REPORTING): COPY progress.
- [Base Backup Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#BASEBACKUP-PROGRESS-REPORTING): `pg_basebackup` progress.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, locks, and statistics views.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): base backup options and WAL methods.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): server-side COPY, STDIN/STDOUT, and options.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): VACUUM/ANALYZE behavior.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): concurrent index builds.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): index rebuilds and concurrent mode.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum, freezing, and maintenance.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): backup manifest verification.

## 20. Summary

Progress reporting gives DBAs visibility into ongoing maintenance and data operations inside PostgreSQL. Each operation class has its own view and counters:

| Operation | Progress View | Key Metrics to Watch |
| --- | --- | --- |
| VACUUM/autovacuum | `pg_stat_progress_vacuum` | phase, heap blocks, dead tuples, index vacuum cycles |
| ANALYZE | `pg_stat_progress_analyze` | sample blocks, extended stats, child tables |
| VACUUM FULL/CLUSTER | `pg_stat_progress_cluster` | heap blocks/tuples scanned and written |
| CREATE INDEX/REINDEX | `pg_stat_progress_create_index` | phase, blocks, tuples, lockers, partitions |
| COPY | `pg_stat_progress_copy` | bytes/tuples processed and totals |
| pg_basebackup | `pg_stat_progress_basebackup` | phase, bytes streamed, tablespaces |

Always pair progress views with `pg_stat_activity`, locks, statistics, PostgreSQL logs, and OS/cloud metrics. Percentages are valid only when numerator and denominator share units and total is known; ETAs are rough estimates. Because progress rows vanish upon completion, use collectors or job logs to retain history and final outcomes.

**Effective monitoring does not just answer “how long has it been running,” but also “which phase is it in, what is it waiting on, are counters advancing, and what is the impact on production.”** Use those signals to catch blockers, I/O bottlenecks, WAL/archive lag, and backup failures early.
