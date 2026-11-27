# maintenance_work_mem and Maintenance Memory in PostgreSQL

## 1. The Role of maintenance_work_mem

PostgreSQL uses memory for many different activities. Regular queries use `work_mem` for sort/hash operations; `shared_buffers` holds database pages; and maintenance operations such as VACUUM and index creation can use a separate limit: **`maintenance_work_mem`**.

`maintenance_work_mem` specifies the maximum amount of memory a single maintenance operation can use. Typical operations include VACUUM, CREATE INDEX, and certain ALTER TABLE operations that process data/constraints. Depending on the command and PostgreSQL version, operations like REINDEX, CLUSTER, or VACUUM FULL may also use this memory area for relevant steps.

A larger value can help:
- VACUUM retain more dead tuple identifiers in memory before having to process them across multiple passes.
- CREATE INDEX/REINDEX process data and sort more efficiently, reducing spills to temporary files where applicable.
- Certain maintenance/validation operations finish faster.

However, setting the value too high can cause concurrent maintenance jobs to contend for RAM. `maintenance_work_mem` is a per-operation limit, not a total server-wide budget. Therefore, you must account for manual operations, autovacuum workers, query workloads, and OS memory.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain which kinds of work `maintenance_work_mem` is used for.
2. Distinguish `maintenance_work_mem` from `work_mem`, `shared_buffers`, `temp_buffers`, and `effective_cache_size`.
3. Understand the role of `autovacuum_work_mem` and its relationship with `maintenance_work_mem`.
4. Estimate total memory demand when multiple maintenance operations run concurrently.
5. Tune memory for VACUUM, CREATE INDEX, and REINDEX.
6. Monitor vacuum/index progress and identify signs of insufficient memory.
7. Distinguish memory pressure from I/O bottlenecks or lock contention.
8. Configure settings at server, role, session, and transaction scopes.
9. Design maintenance windows and concurrency budgets.
10. Practice tuning in a lab environment and verify results.

### 1.2. Key Principles

- `maintenance_work_mem` is a ceiling per maintenance operation, not an amount of RAM always allocated upfront.
- Multiple concurrent maintenance operations can consume memory simultaneously.
- Autovacuum has its own setting `autovacuum_work_mem`; a value of `-1` means it uses `maintenance_work_mem`.
- The number of autovacuum workers can scale total memory demand with concurrency.
- Increasing memory does not fix every bottleneck: slow storage, lock waits, stale statistics, or poor query plans still require separate handling.
- Do not treat `maintenance_work_mem` as the sole limit; add `work_mem`, `shared_buffers`, backend memory, and OS headroom.
- Measure before/after on a representative workload; avoid changing production based on a single run.

---

## 2. Maintenance Operations That Use Memory

### 2.1. VACUUM

VACUUM routinely finds and processes dead tuples to keep tables/indexes healthy, enable space reuse, and support transaction ID maintenance. During this process, PostgreSQL must track tuple identifiers found to be eligible for cleanup.

`maintenance_work_mem` limits the memory allocated to a manual VACUUM operation. If the memory area is too small to hold the set of dead tuple identifiers in a single pass, VACUUM may have to perform more index cleanup cycles. That increases index scan passes and I/O.

This does not mean VACUUM stops or skips dead tuples simply because memory is low. It can process in batches/multiple cycles, though I/O cost and duration may rise.

### 2.2. Autovacuum

Autovacuum consists of background workers that automatically VACUUM/ANALYZE tables based on thresholds and configuration. It uses `autovacuum_work_mem` as the memory limit per worker.

- `autovacuum_work_mem = -1`: uses the `maintenance_work_mem` value.
- Positive value: uses the dedicated limit configured for autovacuum.
- Multiple autovacuum workers can run concurrently; total memory demand does not equal a single worker.

Do not raise `maintenance_work_mem` while forgetting that `autovacuum_work_mem=-1` may cause autovacuum workers to inherit the new level.

### 2.3. CREATE INDEX

CREATE INDEX must read data and build the index structure. Many index builds use a sort-based process; sufficient memory can reduce external sorting/temporary files and improve build times.

Example:

~~~sql
CREATE INDEX idx_orders_customer_created
ON app.orders (customer_id, created_at DESC);
~~~

If an index build is a large operation, the session can be granted higher `maintenance_work_mem` for its run. However, memory cannot substitute for I/O throughput, CPU, and lock planning.

### 2.4. REINDEX

REINDEX rebuilds an index. It can require memory for the build phase similar to CREATE INDEX. Before running:
- Estimate the count and size of indexes.
- Check disk headroom for the new index/temporary files.
- Check locks and write impact.
- Choose regular REINDEX or CONCURRENTLY based on availability requirements.
- Adjust memory inside the maintenance session.

### 2.5. ALTER TABLE and foreign key validation

Certain ALTER TABLE operations, such as adding a foreign key, must scan data to verify the constraint. `maintenance_work_mem` can influence certain maintenance/validation steps depending on command/version.

Do not assume every ALTER TABLE uses this setting. Some operations are primarily bound by lock acquisition, table rewrites, or I/O.

### 2.6. CLUSTER and VACUUM FULL

Table-rewriting operations such as CLUSTER or VACUUM FULL may need memory for index rebuilding or related steps. However, runtime and resources are usually dominated by reading/rewriting the table, indexes, and lock requirements.

Increasing `maintenance_work_mem` does not eliminate the disk space needed for the rewritten copy and does not remove the lock impact of VACUUM FULL.

### 2.7. Dump restore and maintenance

Restore workflows can create many indexes/constraints after loading data. `pg_restore` can run multiple jobs concurrently; each job may launch its own maintenance commands. Therefore, account for restore job concurrency when choosing `maintenance_work_mem`.

### 2.8. Summary table

| Operation | Role of maintenance memory | What to monitor |
|---|---|---|
| VACUUM | Track dead tuple identifiers and cleanup batches | Vacuum cycles, I/O, dead tuples |
| Autovacuum | Uses `autovacuum_work_mem` or inherits setting | Worker count, table churn |
| CREATE INDEX | Memory for index build/sort | Build duration, temp files, I/O |
| REINDEX | Memory for rebuild | Index size, locks, disk headroom |
| ALTER TABLE ADD FOREIGN KEY | Assists validation step per implementation | Scan time, lock wait |
| CLUSTER/VACUUM FULL | Can be used for related index/build steps | Rewrite I/O, lock, free space |
| pg_restore | Multiple index/constraint jobs can run in parallel | Job count, aggregate memory |

---

## 3. Distinguishing Memory Settings

### 3.1. maintenance_work_mem

Intended for maintenance operations. It is not the memory limit for all SQL queries and does not replace `work_mem`.

~~~sql
SHOW maintenance_work_mem;
~~~

### 3.2. autovacuum_work_mem

Dedicated per autovacuum worker. When set to `-1`, workers use `maintenance_work_mem`.

~~~sql
SHOW autovacuum_work_mem;
SHOW autovacuum_max_workers;
~~~

### 3.3. work_mem

`work_mem` is the memory limit for query operations such as sorts and hash operations before spilling to disk. One query can have multiple sort/hash nodes; many queries run concurrently; thus total usage can be many multiples of `work_mem`.

A hash operation may also use `hash_mem_multiplier` depending on version/configuration. Do not count `work_mem` only once per connection when budgeting.

### 3.4. shared_buffers

`shared_buffers` is the shared memory area PostgreSQL uses to cache database pages. This is server-level memory, unlike the per-operation limit of `maintenance_work_mem`.

### 3.5. temp_buffers

`temp_buffers` is memory buffers used for temporary tables within each session. It is neither sort/hash space nor maintenance memory.

### 3.6. effective_cache_size

`effective_cache_size` is a planner estimate of the cache available to a query, including PostgreSQL shared buffers and the filesystem cache. It does not allocate RAM and is not a memory limit.

### 3.7. Comparison

| Setting | Serves | Primary Scope | Allocated fully immediately? |
|---|---|---|---|
| `maintenance_work_mem` | VACUUM/index/maintenance | Per maintenance operation | No |
| `autovacuum_work_mem` | Autovacuum | Per autovacuum worker | No |
| `work_mem` | Sort/hash query operations | Per operation in query | No |
| `shared_buffers` | Database page cache | Shared server memory | Reserved/allocated at startup |
| `temp_buffers` | Temporary tables | Per session | On demand/session |
| `effective_cache_size` | Planner estimate | System-wide estimate | Allocates nothing |

### 3.8. An example not to confuse

Suppose:
- `maintenance_work_mem = 1GB`.
- `work_mem = 32MB`.
- `shared_buffers = 8GB`.
- `effective_cache_size = 24GB`.

That does not mean the server only needs 9,032 MB of RAM. Query operations, autovacuum, backend overhead, OS cache, and other processes can require much more memory. `effective_cache_size` does not allocate 24GB; it is only a planner estimate.

---

## 4. Setting Scope and Concurrency

### 4.1. One operation, not the entire server

`maintenance_work_mem` applies to one maintenance command/operation. If three sessions run three CREATE INDEX or VACUUM operations concurrently, each operation can use up to its limit.

Do not treat the setting as a single shared pool split among sessions.

### 4.2. Parallel maintenance

Some maintenance commands can use parallel workers. How the memory limit applies to the command and its workers is managed by PostgreSQL per operation/version semantics; do not automatically multiply `maintenance_work_mem` by parallel workers if the version docs state the memory budget applies to the whole command.

Conversely, multiple independent maintenance commands running in parallel can still consume multiple budgets concurrently. Distinguish parallel workers of one command from multiple distinct commands/sessions.

### 4.3. Autovacuum workers

If `autovacuum_work_mem=-1`, each worker uses the `maintenance_work_mem` limit. Example configuration:
- `maintenance_work_mem = 512MB`.
- `autovacuum_max_workers = 5`.
- `autovacuum_work_mem = -1`.

A conservative budget for the autovacuum portion can reach roughly 5 × 512MB, even though workers will not necessarily all consume the full limit simultaneously.

### 4.4. Manual maintenance concurrency

Example:
- Two manual index builds, each capped at 2GB.
- Three autovacuum workers, each capped at 512MB.
- One manual VACUUM capped at 2GB.

The conservative worst-case allowance for these limits is 2 × 2GB + 3 × 512MB + 2GB, before even counting the query workload and OS. Actual usage may be lower, yet this calculation is useful to avoid overcommitting.

### 4.5. pg_restore jobs

`pg_restore -j N` can run multiple restore jobs in parallel. If jobs concurrently build indexes or constraints, memory demand scales with the number of actually running maintenance operations, not just database connections.

Plan job count and memory settings together. A restore running 8 jobs with high maintenance memory can exhaust host RAM even when each job alone behaves fine.

### 4.6. Manual VACUUM and autovacuum

If a DBA runs manual VACUUM while autovacuum is processing other tables, both groups can consume memory concurrently. Check `pg_stat_activity`, `pg_stat_progress_vacuum`, and worker count before starting additional maintenance.

### 4.7. Conservative memory budget

A planning formula:

~~~text
Total RAM budget
  >= shared_buffers
   + concurrent manual maintenance operations * maintenance_work_mem
   + autovacuum workers * autovacuum_work_mem
   + concurrent query operations * work_mem/hash allowance
   + backend/process overhead
   + OS and filesystem cache headroom
   + monitoring/agent/other services
~~~

This is a conservative bound estimate, not an exact usage forecast. Measure RSS/cgroup memory under a representative workload and keep headroom for spikes.

### 4.8. Do not overcommit based on configured totals

Not every operation always uses its full limit, yet OOMs often happen when multiple workloads spike in memory at the same time. Budgets must account for peak concurrency, maintenance windows, restore jobs, and workload bursts.

---

## 5. VACUUM Memory and Dead Tuple Tracking

### 5.1. Dead tuples

UPDATE/DELETE create old tuple versions. Once no transaction snapshot still needs them, VACUUM can mark space reusable and clean up corresponding index entries.

VACUUM must track dead tuple identifiers during cleanup. The memory limit affects how many identifiers can be processed in one pass.

### 5.2. Low memory

If memory is insufficient for the dead tuple set:
- VACUUM may split cleanup into multiple cycles.
- Indexes may have to be scanned multiple times.
- I/O increases.
- Vacuum duration can lengthen.
- Table/index cleanup still progresses per the appropriate mechanism.

Increasing `maintenance_work_mem` can help high-churn tables, but RAM and concurrency must be weighed.

### 5.3. High memory

Higher memory can allow processing more dead tuple identifiers in a single pass. However, if the bottleneck is disk throughput, lock contention, long-running transactions, or vacuum cost delay, adding memory may yield little improvement.

### 5.4. Separate autovacuum setting

If `autovacuum_work_mem` has a positive value, changing `maintenance_work_mem` does not automatically make autovacuum workers use the new value. Check both:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
);
~~~

### 5.5. Monitoring vacuum progress

~~~sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.max_dead_tuples,
    p.num_dead_tuples,
    a.query
FROM pg_stat_progress_vacuum AS p
JOIN pg_stat_activity AS a
    ON a.pid = p.pid;
~~~

Progress columns vary by major version. `max_dead_tuples` and `num_dead_tuples` are helpful for understanding dead tuple tracking when present, though not every version shares the same schema.

### 5.6. Distinguishing memory from vacuum delay

VACUUM has cost-based delays to throttle I/O pressure. If vacuum is slow due to cost delay, increasing `maintenance_work_mem` will not necessarily solve it. Check `autovacuum_vacuum_cost_limit`, `autovacuum_vacuum_cost_delay`, and per-table storage parameters.

### 5.7. Long-running transactions

Old transactions/snapshots can prevent VACUUM from removing dead tuples. In that case, raising memory does not fix the root cause. Check `backend_xmin`, `xact_start`, replication slots, and prepared transactions as applicable.

### 5.8. VACUUM is not VACUUM FULL

Regular VACUUM does not rewrite the entire table; it makes space reusable. VACUUM FULL rewrites the table and requires strong locks, extra disk space, and time. Increasing maintenance memory does not remove those requirements.

---

## 6. CREATE INDEX and REINDEX Memory

### 6.1. Index builds require memory

Index builds generally must read rows and sort keys. If the data exceeds available memory, PostgreSQL may use external sorting/temporary files. Raising `maintenance_work_mem` can reduce spills when sorting is the bottleneck.

### 6.2. Dedicated setting for a maintenance session

A higher value can be set inside a DBA session:

~~~sql
SET maintenance_work_mem = '2GB';

CREATE INDEX idx_orders_created_at
ON app.orders (created_at);

RESET maintenance_work_mem;
~~~

Ensure the host has enough RAM and that many similar jobs are not running concurrently.

### 6.3. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` reduces write blocking compared to regular CREATE INDEX, but has multiple phases and can take longer. It still needs memory for index building and has different transaction context requirements.

~~~sql
SET maintenance_work_mem = '1GB';

CREATE INDEX CONCURRENTLY idx_orders_customer
ON app.orders (customer_id);

RESET maintenance_work_mem;
~~~

Do not run CREATE INDEX CONCURRENTLY inside a transaction block. If the command fails, it may leave an invalid index that must be handled per your runbook.

### 6.4. Monitoring index builds

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

Columns/phases vary by version and command. This view shows which phase the build is in; it does not directly report how much memory is currently used.

### 6.5. Temporary files

If an index build uses external sorting, temp files may be created. `log_temp_files` can help detect temporary files above a threshold. However, temp files are also created by query sorts/hashes; correlate PID/time/operation to identify the source.

### 6.6. REINDEX CONCURRENTLY

REINDEX CONCURRENTLY has multiple phases and requires additional disk space. Memory tuning can improve the build phase, but does not eliminate storage requirements and lock coordination. Check for invalid indexes and progress after failures.

### 6.7. Choosing the memory level

Do not set `maintenance_work_mem` to multiple GB merely because an index build is slow. First inspect:
- Index size and table size.
- Build duration per phase.
- Temp file size.
- Storage throughput/latency.
- CPU utilization.
- Concurrent build count.
- Free memory/cgroup pressure.

If storage is the bottleneck, raising memory may not help.

---

## 7. Configuring maintenance_work_mem

### 7.1. Check current values

~~~sql
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;

SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
);
~~~

`setting` is often displayed in internal units; use `unit` to interpret the value. `context` shows the scope of change; do not guess reload/restart behavior solely from the parameter name.

### 7.2. Session-level SET

~~~sql
SET maintenance_work_mem = '1GB';
SHOW maintenance_work_mem;

CREATE INDEX idx_events_created_at
ON app.events (created_at);

RESET maintenance_work_mem;
~~~

Session-level SET works well for a single maintenance session. If the command fails before RESET, the connection may retain the setting; in automation, ensure reset or close the connection.

### 7.3. SET LOCAL

`SET LOCAL` only lasts until the end of the transaction:

~~~sql
BEGIN;
SET LOCAL maintenance_work_mem = '512MB';

CREATE INDEX idx_events_type
ON app.events (event_type);

COMMIT;
~~~

Use only when the command is allowed inside a transaction block. Certain commands like VACUUM and CREATE INDEX CONCURRENTLY cannot run inside a transaction block; use session-level SET in those cases.

### 7.4. ALTER ROLE

Defaults can be assigned per role:

~~~sql
ALTER ROLE maintenance_operator
SET maintenance_work_mem = '1GB';
~~~

The setting applies when the role opens new sessions. It does not automatically change existing sessions. Control roles and connection pools to avoid giving high memory to every session of a user.

### 7.5. ALTER DATABASE

Defaults can be set per database:

~~~sql
ALTER DATABASE analytics
SET maintenance_work_mem = '768MB';
~~~

This is the default setting for new sessions connecting to that database. Consider the number of maintenance users/jobs and do not treat a database-level default as a global memory cap.

### 7.6. ALTER SYSTEM

Change the server default:

~~~sql
ALTER SYSTEM SET maintenance_work_mem = '512MB';
SELECT pg_reload_conf();

SHOW maintenance_work_mem;
~~~

After reloading, check the effective value in a new session and the source in `pg_settings`. ALTER SYSTEM writes to `postgresql.auto.conf`; if configuration management also manages this setting, avoid creating two competing sources of truth.

### 7.7. Changing autovacuum_work_mem

`autovacuum_work_mem` is typically managed via server configuration and has its own context. Check `pg_settings.context` to see whether reload/restart is required on your running version. When setting a positive value, budget it independently from `maintenance_work_mem`.

### 7.8. Verify configuration files

You can inspect file settings and parse errors:

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers'
)
ORDER BY seqno;
~~~

Permissions to read catalogs/configurations may be restricted. Do not export all file settings if secrets or sensitive environment details are present.

### 7.9. Avoid server-wide changes when only one job needs it

If one large index build needs high memory, session-level SET generally scopes it better than ALTER SYSTEM. Only raise the server-wide default when routine maintenance workloads regularly need it and the memory budget has been calculated.

---

## 8. Building a Maintenance Memory Budget

### 8.1. Components

When budgeting, include:
- `shared_buffers`.
- Concurrent manual maintenance operations.
- `maintenance_work_mem` per operation.
- Number of autovacuum workers and `autovacuum_work_mem`.
- Query `work_mem` across concurrent sort/hash operations.
- Backend/process memory.
- Extension memory and connection pool overhead.
- OS/filesystem cache.
- Monitoring agents and co-located host services.

### 8.2. Budget example

Assume a host with 64GB RAM:
- Shared buffers: 16GB.
- Two maintenance operations, each capped at 2GB: 4GB.
- Four autovacuum workers, each capped at 512MB: 2GB.
- Query workload/other backend memory: 12GB estimated.
- OS, filesystem cache, and agents: 12GB estimated.

The budgeted items total 46GB; the remainder is headroom for variance. This is only an example; measure RSS/cgroup memory and actual peak workloads.

### 8.3. Concurrency formula

~~~text
Maintenance peak allowance
  = manual_operation_count * maintenance_work_mem
  + autovacuum_worker_count * autovacuum_work_mem
~~~

If `autovacuum_work_mem=-1`, substitute `maintenance_work_mem`. Do not mechanically multiply by a single command's parallel workers; check version/command semantics.

### 8.4. Restore scenario

A restore may run multiple CREATE INDEX commands concurrently. If each operation is granted 2GB and 6 jobs run simultaneously, the conservative budget for that group is 12GB. Add autovacuum, query workload, and OS.

Lowering `pg_restore -j` can be a better way to control memory than setting maintenance memory too low.

### 8.5. Autovacuum burst scenario

Multiple tables crossing vacuum thresholds simultaneously can cause many workers to run at once. If each worker is allowed a lot of memory, peak usage climbs. Adjust:
- `autovacuum_max_workers`.
- `autovacuum_work_mem`.
- Vacuum thresholds/scale factors.
- Cost delay/limit.
- Table-level storage parameters.
- Workload write rate and maintenance windows.

### 8.6. Headroom

Do not allocate 100% of RAM based on theoretical limits. Retain headroom for:
- Burst query memory.
- Backup/restore tools.
- OS page cache.
- Kernel memory.
- Connection spikes.
- Monitoring/agents.
- Memory fragmentation and process overhead.

### 8.7. OOM risk

If the OS or cgroup OOM killer terminates a PostgreSQL backend/process, it can cause query failures, transaction rollbacks, or even impact the server depending on which process is killed. Monitor kernel/cgroup OOM events and memory pressure; do not look only at PostgreSQL logs.

---

## 9. Monitoring Maintenance Operations

### 9.1. Current settings

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'autovacuum_max_workers',
    'work_mem',
    'shared_buffers'
)
ORDER BY name;
~~~

This confirms the active settings in the current server/session. A session may override server defaults; check using the connection/role actually running maintenance.

### 9.2. Running autovacuum workers

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

`backend_type` is present in modern major versions; on older versions, filter by query/process details and verify against monitoring docs.

### 9.3. Tables needing vacuum/analyze

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_dead_tup` and `n_live_tup` are estimates, not exact row counts. Use them for trends and investigation prioritization, not as exact figures for billing/capacity.

### 9.4. Vacuum progress

~~~sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

The progress view shows the phase and scan/cleanup progress. It does not display the exact total memory used by the worker.

### 9.5. Index build progress

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

Combine with process memory/OS metrics to see whether the operation is experiencing memory pressure. Progress may not be linear across phases.

### 9.6. Temp file logging

`log_temp_files` can be configured to record temporary files above a threshold. This helps locate sort/hash spills, though CREATE INDEX is not the only thing creating temp files. Correlate timestamps, PID, database, and command.

### 9.7. OS and cgroup metrics

Monitor:
- Host available memory.
- PostgreSQL process RSS.
- Cgroup memory.current/memory.max when running in containers.
- Memory pressure/PSI on Linux.
- Swap activity.
- OOM killer events.
- Filesystem free space and temp volume capacity.

PostgreSQL does not provide a single view showing exact memory consumed by a maintenance operation. Combine progress views with OS process metrics.

### 9.8. Vacuum logs

`log_autovacuum_min_duration` can log autovacuum operations exceeding a duration threshold. Logs are useful for duration, pages scanned/removed, and cleanup details depending on version. Do not let logging volume grow unbounded without retention/aggregation.

### 9.9. Checkpoints and I/O

Maintenance can generate heavy I/O even when memory is sufficient. Correlate vacuum/index progress with:
- Storage latency/throughput/IOPS.
- Checkpoint write/sync time.
- WAL generation.
- `pg_stat_io` on PostgreSQL 16+.
- Temp file size.
- CPU utilization.

### 9.10. Dashboard

A maintenance dashboard should include:
- Active maintenance operations.
- Autovacuum worker count.
- Oldest/longest vacuum.
- Dead tuple estimates by table.
- Index build phase/duration.
- Temp file volume.
- Process/cgroup memory.
- Host available memory and swap.
- Storage latency/queue.
- Lock waits and transaction age.

---

## 10. Choosing maintenance_work_mem Levels

### 10.1. Start from a baseline

No single optimal value fits every database. The default is typically small to suit varied workloads; it can be raised on systems with spare RAM and controlled maintenance jobs.

Evaluate:
- Physical RAM/container limit.
- Database size and table churn.
- Index build frequency/size.
- Number of autovacuum workers.
- Maintenance concurrency.
- Query memory budget.
- OS headroom and memory pressure.

### 10.2. VACUUM-heavy OLTP

For OLTP with heavy UPDATE/DELETE:
- Track dead tuples and vacuum frequency.
- Check autovacuum thresholds.
- Review `autovacuum_work_mem` before increasing `maintenance_work_mem`.
- Check transaction age/replication slots blocking cleanup.
- Measure vacuum duration and I/O.
- Raise memory in a controlled way if multiple cleanup cycles are an issue.

Do not let autovacuum workers use a high setting without multiplying by concurrency.

### 10.3. Index build windows

For large index builds:
1. Choose a maintenance window.
2. Estimate index size and disk headroom.
3. Limit concurrent jobs.
4. SET higher session-level memory if the host has enough RAM.
5. Monitor progress, temp files, RSS, and storage.
6. RESET/close the session after the operation.

### 10.4. Data warehouse

Bulk loads and index builds may need high memory in phases. You can raise maintenance memory for the restore/build window, then lower it back to baseline. Control concurrency so the query workload does not OOM.

### 10.5. Containerized PostgreSQL

If a container has a memory limit, you must use the actual cgroup limit as your budget. The host may still have plenty of RAM while the container gets OOM killed. Do not size maintenance memory from total host RAM if the container only gets a fraction.

### 10.6. Managed PostgreSQL

Some managed services restrict parameter values, modification privileges, or OS metric visibility. Use the provider's parameter groups/docs and provided dashboards; do not assume you can access process RSS or change every GUC.

### 10.7. Set a separate limit for autovacuum

If manual index builds need 2GB while autovacuum needs a smaller limit to protect concurrency, set `autovacuum_work_mem` to a positive, separate value. Ensure that level still suffices for the vacuum workload; measure effectiveness via progress/logs and dead tuple trends.

### 10.8. Do not use memory to mask vacuum design issues

If autovacuum is falling behind:
- Review per-table thresholds/scale factors.
- Review write rate and table churn.
- Check long-running transactions and replication slots.
- Check vacuum cost delay/limit.
- Review index bloat/maintenance overhead.
- Consider partitioning or schema/workload changes.

Memory is one factor in the system, not a substitute for autovacuum design.

---

## 11. Relationship with Other Maintenance Parameters

### 11.1. autovacuum_work_mem

`autovacuum_work_mem` sets the memory limit per autovacuum worker. When set to `-1`, workers use `maintenance_work_mem`. When set separately, changing `maintenance_work_mem` does not necessarily alter the autovacuum limit.

Example:

~~~conf
maintenance_work_mem = 512MB
autovacuum_work_mem = 256MB
autovacuum_max_workers = 5
~~~

The conservative budget for autovacuum is up to roughly 5 × 256MB under this config, plus other workloads.

### 11.2. autovacuum_max_workers

This parameter limits concurrent autovacuum workers. Increasing workers can let more tables be processed in parallel, but also increases:
- Memory demand.
- Storage I/O.
- CPU usage.
- Lock/IO contention.
- WAL/checkpoint pressure.

Do not increase workers without checking memory and storage capacity.

### 11.3. vacuum_cost_limit and vacuum_cost_delay

Cost-based vacuum parameters throttle VACUUM's I/O rate. `vacuum_cost_delay` introduces a pause when cost exceeds a threshold; `vacuum_cost_limit` sets the cost budget. Autovacuum has corresponding parameters.

If VACUUM is slow because it is throttled to protect the workload, raising maintenance memory may not speed it up. Determine whether the goal is reducing memory-driven extra cycles or increasing I/O throughput.

### 11.4. vacuum_buffer_usage_limit

`vacuum_buffer_usage_limit` controls the buffer ring size VACUUM uses to limit impact on shared buffers. This is a different concept from `maintenance_work_mem`, which caps memory for the maintenance operation.

Do not increase `vacuum_buffer_usage_limit` as a substitute for increasing maintenance memory; each setting addresses a different part of resource usage.

### 11.5. max_parallel_maintenance_workers

This parameter limits parallel workers for maintenance commands that support parallelism, such as certain index builds. It is not a memory limit.

For parallel utility commands, `maintenance_work_mem` applies to the entire command per PostgreSQL semantics—do not multiply the limit by parallel workers automatically. However, multiple independent maintenance commands can still consume multiple budgets concurrently.

### 11.6. maintenance_io_concurrency

In supported PostgreSQL versions, `maintenance_io_concurrency` adjusts the I/O concurrency level for maintenance operations. It can affect throughput and queue depth, but does not allocate memory.

Tune alongside storage characteristics; raising concurrency on already saturated storage can worsen latency.

### 11.7. Per-table storage parameters

Autovacuum behavior can be tuned per table, for example:
- `autovacuum_vacuum_scale_factor`.
- `autovacuum_vacuum_threshold`.
- `autovacuum_analyze_scale_factor`.
- `autovacuum_analyze_threshold`.
- `autovacuum_vacuum_cost_limit`.
- `autovacuum_vacuum_cost_delay`.
- `autovacuum_enabled`.

This helps high-write-churn tables get vacuumed sooner without raising global workers/memory for every relation.

### 11.8. Parameter matrix

| Setting | Controls | Does not control |
|---|---|---|
| `maintenance_work_mem` | Memory ceiling per maintenance operation | Total server memory |
| `autovacuum_work_mem` | Memory ceiling per autovacuum worker | Worker count |
| `autovacuum_max_workers` | Worker concurrency | Memory per worker |
| `vacuum_cost_limit`/`vacuum_cost_delay` | Vacuum I/O/cost pacing | Dead tuple memory ceiling |
| `vacuum_buffer_usage_limit` | Buffer ring behavior | Maintenance work memory |
| `max_parallel_maintenance_workers` | Parallel workers for a command | Command's total memory ceiling |
| `maintenance_io_concurrency` | Maintenance I/O concurrency | RAM allocation |

---

## 12. Controlled Tuning Workflow

### 12.1. Identify symptoms

Before changing settings, classify:
- Is VACUUM running many index cleanup cycles?
- Is autovacuum falling behind write churn?
- Is CREATE INDEX spilling to temp files?
- Are restore jobs causing memory pressure?
- Are OOMs or swapping increasing?
- Is maintenance slow due to locks or storage?

Do not use one maintenance memory value to cure every type of issue.

### 12.2. Collect baseline

Record:
- Current settings and sources.
- Host/container memory limits.
- Concurrent maintenance operations.
- Autovacuum worker count.
- Process RSS/cgroup memory.
- Vacuum/index progress and duration.
- Temp file volume.
- Storage latency/throughput.
- CPU and swap.
- Concurrent query workload.

### 12.3. Change one factor

For example, if an index build spills heavily:
1. Keep job concurrency constant.
2. Increase session `maintenance_work_mem` moderately.
3. Re-run on the same data/test window.
4. Compare duration, temp files, RSS, and storage.
5. Increase further only if results improve and memory headroom remains sufficient.

If you simultaneously change memory, job count, storage tier, and parallel workers, it is hard to determine which change had the effect.

### 12.4. Choose safe limits

Set an upper bound aligned with the peak memory budget. For example:
- Cap memory for the maintenance role.
- Cap concurrent jobs in the scheduler.
- Cap autovacuum worker concurrency.
- Define maintenance windows.
- Monitor cgroup/host memory.
- Have a plan to stop/reduce concurrency when headroom drops.

### 12.5. Session override for a single job

This is often a good way to test a different memory level without altering all sessions:

~~~sql
SET maintenance_work_mem = '1GB';
-- Run one maintenance command.
RESET maintenance_work_mem;
~~~

In automation, use client-side cleanup logic or close the session after the command so the setting is not retained unintentionally.

### 12.6. Evaluate results

Compare:
- Runtime.
- CPU.
- Peak RSS.
- Memory pressure/swap.
- Temp file bytes.
- I/O latency/throughput.
- Number of vacuum cycles.
- Lock impact.
- Concurrent workload latency.
- Autovacuum backlog after the operation.

A faster job that triggers an OOM or pushes application latency past SLO is not a good tuning result.

### 12.7. Roll back settings

Record the previous value/source. If memory pressure increases:
- Stop launching new maintenance jobs.
- Reduce concurrency.
- Reset session overrides.
- Restore server/role/database settings per the change record.
- Monitor memory and active operations.
- Do not kill autovacuum workers en masse without assessing table/transaction impact.

---

## 13. Common Troubleshooting

### 13.1. VACUUM is slow despite large maintenance_work_mem

Check:
- Dead tuple churn and table size.
- Vacuum progress/number of index cycles.
- Cost delay/limit.
- Long-running transactions and replication slots.
- Storage latency.
- Lock contention.
- Competing autovacuum workers.
- Index count/size.

High memory does not guarantee fast vacuum if the cause is I/O, locks, or snapshot horizon.

### 13.2. Autovacuum is not using the newly configured memory level

Check `autovacuum_work_mem`. If positive, workers use that setting; if `-1`, workers inherit `maintenance_work_mem`. Verify the server reloaded the required setting and check for table-level/workload behavior.

### 13.3. OOM during CREATE INDEX

Investigate:
- How many index builds are running simultaneously?
- How much maintenance_work_mem is each session using?
- Does the query workload have heavy work_mem operations?
- Autovacuum worker count and memory?
- Cgroup memory limit?
- Swap/OOM logs?
- pg_restore/automation job concurrency?

Reduce job concurrency or cap session memory before adding more RAM.

### 13.4. Large temp files during index build

Confirm whether temp files come from the index build or from other query sorts/hashes. Check build phase, index size, storage, and maintenance memory. If raising memory does not reduce temp files or runtime, the bottleneck may be I/O/CPU.

### 13.5. VACUUM FULL does not free RAM/disk as expected

VACUUM FULL rewrites the table and requires disk space for the new copy while executing. It is not a RAM-freeing tool. Memory settings do not eliminate lock and disk-space requirements. Consider regular VACUUM, pg_repack, or an appropriate maintenance approach.

### 13.6. Slow restore

Check:
- `pg_restore -j` concurrency.
- Index build time/temp files.
- `maintenance_work_mem` of restore sessions.
- Storage throughput.
- Constraint validation.
- WAL/checkpoint pressure.
- Network if restoring from a remote archive.

Raising jobs and raising memory simultaneously can push peak memory past limits.

### 13.7. Swap rises after increasing maintenance_work_mem

Identify which sessions/workers are consuming memory, the number of concurrent operations, and cgroup limits. Lower concurrency/settings per budget, then check whether the query workload is impacted by swap latency.

### 13.8. Autovacuum slowed by cost delay

Increasing memory does not change cost delay. Check vacuum cost parameters and storage headroom. If lowering delay is needed, measure the impact on application I/O latency.

### 13.9. Memory setting did not change in session

Check:
- Did SET succeed?
- Do role/database defaults override it?
- Is the connection pool keeping an old session?
- SHOW maintenance_work_mem.
- pg_settings.source and setting.
- Are you inspecting the right cluster/database/session?

### 13.10. No per-PID memory metric in PostgreSQL

PostgreSQL progress views generally do not report exact memory allocated per operation. Grab the PID from progress/activity views and correlate with process RSS/cgroup metrics in the OS/monitoring platform. Do not infer memory usage solely from the GUC value.

---

## 14. Runbook for Maintenance Memory Pressure

1. Confirm the alert and host/container memory headroom.
2. Check OOM/swap/PSI/cgroup events.
3. List running maintenance commands and autovacuum workers.
4. Read `maintenance_work_mem`, `autovacuum_work_mem`, `autovacuum_max_workers`, and `work_mem`.
5. Identify sessions with maintenance setting overrides.
6. Check restore/index build job concurrency.
7. Temporarily pause schedulers from launching more maintenance jobs.
8. If needed, reduce job concurrency or terminate a job following approved application/DBA procedures.
9. Do not terminate autovacuum or backends arbitrarily; weigh rollback/cleanup.
10. Restore headroom and confirm database/application latency.
11. Adjust budgets/settings and scheduler concurrency.
12. Record incident findings and monitor the next maintenance run.

### 14.1. When an OOM has occurred

- Collect kernel/cgroup OOM logs.
- Identify which process was OOM killed.
- Check PostgreSQL logs and transaction rollbacks.
- Check for invalid/incomplete indexes after build failures.
- Check the vacuum/autovacuum backlog.
- Verify database recovery and application retries.
- Only re-run maintenance after the memory budget has been corrected.

### 14.2. When only one maintenance job is slow

If memory headroom is healthy and only one job is slow, do not assume it is a memory incident. Inspect progress phase, lock waits, storage/CPU, and query/object size. Address the actual resource bottleneck.

---

## 15. PostgreSQL Reference Documentation

Prefer documentation matching your exact major version:

- [PostgreSQL — Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): maintenance_work_mem, autovacuum_work_mem, work_mem, and resource settings.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): VACUUM, autovacuum, and dead tuple cleanup.
- [PostgreSQL — Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): pg_stat_progress_vacuum and pg_stat_progress_create_index.
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): worker concurrency and vacuum cost settings.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index build behavior and parallelism.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): parallel restore jobs.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): statistics views and pg_stat_io on supported versions.

The `/current/` pages may point to a newer major version. Check setting context, view columns, and parallel maintenance behavior for your running version.

---

## 16. Lab: Observing and Tuning VACUUM

Perform in a lab database with sufficient disk/RAM. Do not generate large churn or raise memory on production just to run exercises.

### 16.1. Create a test table

~~~sql
CREATE SCHEMA IF NOT EXISTS maintenance_lab;

CREATE TABLE maintenance_lab.events (
    event_id bigserial PRIMARY KEY,
    account_id bigint NOT NULL,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO maintenance_lab.events(account_id, payload)
SELECT
    (g % 10000)::bigint,
    repeat('x', 300)
FROM generate_series(1, 200000) AS g;
~~~

Size the dataset to fit lab resources. Row counts can be reduced on a small laptop/container.

### 16.2. Generate dead tuples

~~~sql
UPDATE maintenance_lab.events
SET payload = repeat('y', 300)
WHERE event_id % 3 = 0;

DELETE FROM maintenance_lab.events
WHERE event_id % 7 = 0;
~~~

These operations create tuple versions/dead tuples. Exact counts are influenced by autovacuum and the visibility map.

### 16.3. Check table statistics

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'maintenance_lab';
~~~

Tuple counts are estimates. If autovacuum already ran before observation, generate a small additional workload or use a fresh table.

### 16.4. Run VACUUM with a session setting

~~~sql
SET maintenance_work_mem = '128MB';
VACUUM (VERBOSE, ANALYZE) maintenance_lab.events;
RESET maintenance_work_mem;
~~~

VACUUM cannot run inside a transaction block. Use a dedicated psql session; check logs/VERBOSE output and progress when the table is large enough.

### 16.5. Compare with another memory level

In the lab, re-run with a different maintenance memory level after generating equivalent churn. Record:
- Vacuum duration.
- Number of index cleanup cycles if shown in output/progress.
- Dead tuple estimates before/after.
- I/O latency and throughput.
- Process RSS.
- Application workload impact if any.

Do not draw conclusions from two runs if datasets/caches/workloads differ significantly.

### 16.6. Observe autovacuum

Inspect `autovacuum_work_mem`, `autovacuum_max_workers`, and worker activity. To test inheritance, use a lab cluster and set `autovacuum_work_mem=-1`; then compare against a positive value. Changing autovacuum configuration may require a reload depending on setting context.

---

## 17. Lab: CREATE INDEX and Memory Budget

### 17.1. Create an index test table

~~~sql
CREATE TABLE maintenance_lab.index_source AS
SELECT
    g::bigint AS id,
    (g % 50000)::bigint AS customer_id,
    md5(g::text) AS payload,
    clock_timestamp() - (g || ' seconds')::interval AS created_at
FROM generate_series(1, 500000) AS g;

ALTER TABLE maintenance_lab.index_source
ADD PRIMARY KEY (id);
~~~

Adjust row count to lab capacity.

### 17.2. Build an index with default settings

~~~sql
CREATE INDEX idx_index_source_customer
ON maintenance_lab.index_source (customer_id);
~~~

Record duration, temp file logs if enabled, and storage metrics.

### 17.3. Rebuild with a different session setting

~~~sql
DROP INDEX maintenance_lab.idx_index_source_customer;

SET maintenance_work_mem = '512MB';

CREATE INDEX idx_index_source_customer
ON maintenance_lab.index_source (customer_id);

RESET maintenance_work_mem;
~~~

This is a comparison test; do not drop production indexes to benchmark. Run on similar datasets/hosts and control cache state.

### 17.4. Observe progress

On a sufficiently large table, query pg_stat_progress_create_index in another session. Compare phases and blocks/tuples progress; get memory usage from process/cgroup metrics.

### 17.5. Test concurrency budget

Run two index builds on two separate lab tables with configured session settings. Observe host/cgroup memory. Stop the test if headroom drops below safe thresholds. This lab illustrates why a high setting can be safe for one job yet unsafe for multiple jobs.

---

## 18. Lab: Configuring and Verifying Settings

### 18.1. Inspect context and source

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE '%work_mem%'
ORDER BY name;
~~~

Identify which settings sessions can override and which require server configuration/reload per context.

### 18.2. Session override

~~~sql
SET maintenance_work_mem = '256MB';
SHOW maintenance_work_mem;
RESET maintenance_work_mem;
SHOW maintenance_work_mem;
~~~

Confirm the value returns to the session default after RESET.

### 18.3. Role default

In the lab, create a dedicated role and assign a default:

~~~sql
CREATE ROLE lab_maintenance LOGIN;
ALTER ROLE lab_maintenance
SET maintenance_work_mem = '384MB';
~~~

Open a new session as that role and check SHOW. Sessions already open before ALTER ROLE do not automatically receive the new default.

### 18.4. Database default

~~~sql
ALTER DATABASE maintenance_lab
SET maintenance_work_mem = '256MB';
~~~

Open a new session to the database and verify. Remove the setting after the lab with ALTER DATABASE ... RESET maintenance_work_mem.

### 18.5. Check configuration source

Use pg_settings.source to see whether a setting comes from default, configuration file, role/database setting, or session override. Use pg_file_settings to check for parse errors if permitted.

---

## 19. Practice Exercises

Questions use a PostgreSQL lab. Do not raise memory or run high maintenance concurrency in production just to test a hypothesis.

### Exercise 1 — Purpose

What kinds of work does maintenance_work_mem serve? Give three examples.

### Exercise 2 — Per operation

Why can't maintenance_work_mem be treated as a single total memory budget for the entire server?

### Exercise 3 — VACUUM

How can low memory affect VACUUM?

### Exercise 4 — Index build

Why can increasing maintenance_work_mem reduce temp files during CREATE INDEX?

### Exercise 5 — Autovacuum

What does autovacuum_work_mem=-1 mean?

### Exercise 6 — Worker concurrency

There are 4 autovacuum workers, each capped at 512MB. What is the conservative budget for this worker group?

### Exercise 7 — work_mem

Distinguish work_mem and maintenance_work_mem.

### Exercise 8 — effective_cache_size

Does effective_cache_size allocate RAM?

### Exercise 9 — shared_buffers

How does shared_buffers differ in scope from maintenance_work_mem?

### Exercise 10 — Parallel maintenance

Should you multiply maintenance_work_mem by the parallel workers of a single command? Why or why not?

### Exercise 11 — Restore jobs

Six concurrent pg_restore jobs are each building an index with 1GB maintenance_work_mem. What is the conservative budget for the index build group?

### Exercise 12 — OOM

One index build running alone succeeds with 2GB, yet two concurrent builds cause the container to OOM. Explain.

### Exercise 13 — Vacuum progress

Which view shows VACUUM phase and progress? Does that view report exact memory usage?

### Exercise 14 — Index progress

Which view shows phase/blocks/tuples for CREATE INDEX?

### Exercise 15 — Slow autovacuum

Autovacuum is slow due to vacuum_cost_delay. Does raising maintenance_work_mem solve it directly?

### Exercise 16 — Long transactions

Why can a long transaction prevent VACUUM from cleaning up dead tuples even with high memory?

### Exercise 17 — Setting scope

State how to set maintenance_work_mem for only a single DBA session.

### Exercise 18 — VACUUM transaction

Why can't you run SET LOCAL and then VACUUM inside a transaction block?

### Exercise 19 — ALTER ROLE

Does ALTER ROLE SET maintenance_work_mem affect open sessions or new sessions?

### Exercise 20 — Memory budget

List at least six components to include when budgeting memory for a PostgreSQL host.

### Exercise 21 — Temp files

Are large temp files during an index build necessarily created by the index build? What must be correlated?

### Exercise 22 — pg_stat_io

Which PostgreSQL major version introduced pg_stat_io? Does it report exact memory consumed?

### Exercise 23 — vacuum_buffer_usage_limit

How does this setting differ from maintenance_work_mem?

### Exercise 24 — Slow index build

List metrics to check before increasing maintenance_work_mem.

### Exercise 25 — Incident

A host has memory pressure, 3 manual index builds, 4 autovacuum workers, and rising query latency. Outline the response sequence.

---

## 20. Solutions — Exercises 1 to 25

### Exercise 1 — Purpose

maintenance_work_mem is for maintenance operations. Examples: VACUUM, CREATE INDEX/REINDEX, and certain ALTER TABLE operations requiring validation.

### Exercise 2 — Per operation

The setting is a limit per operation. Multiple sessions or workers can run maintenance concurrently and each operation has its own budget; therefore total memory can be a multiple of the setting.

### Exercise 3 — VACUUM

Low memory can cause VACUUM to process dead tuple identifiers across multiple cycles, repeating index cleanup and increasing I/O/duration. VACUUM still has a batching mechanism.

### Exercise 4 — Index build

Index builds may need to sort data. If memory is large enough, it can reduce external sorting/temp file spills and improve build time when sorting is the bottleneck.

### Exercise 5 — Autovacuum

autovacuum_work_mem=-1 means each autovacuum worker inherits maintenance_work_mem. If set to a positive value, workers use their own limit.

### Exercise 6 — Worker concurrency

4 × 512MB = 2GB is the conservative budget for the autovacuum worker group's memory limits, before counting other workloads. Workers do not necessarily always consume the full limit.

### Exercise 7 — work_mem

work_mem is for sort/hash operations inside queries; maintenance_work_mem is for maintenance commands like VACUUM/index builds. One query can have multiple sort/hash nodes and multiple sessions, so aggregate work_mem can also be large.

### Exercise 8 — effective_cache_size

No. It is a planner estimate of usable cache; it does not allocate or reserve RAM.

### Exercise 9 — shared_buffers

shared_buffers is a server-level shared cache for database pages. maintenance_work_mem is a memory ceiling per maintenance operation.

### Exercise 10 — Parallel maintenance

Do not multiply mechanically. For parallel utility commands, PostgreSQL applies maintenance_work_mem to the entire command per its semantics; verify in version/command docs. Multiple independent commands can still use multiple budgets simultaneously.

### Exercise 11 — Restore jobs

6 × 1GB = 6GB is the conservative budget for six concurrent index builds. Add autovacuum, query memory, backend overhead, and OS.

### Exercise 12 — OOM

A single build may fit within the RAM budget, while two concurrent builds double peak demand. Container memory limits can be lower than host RAM; adding autovacuum/query workloads pushes the total past the limit.

### Exercise 13 — Vacuum progress

pg_stat_progress_vacuum shows phase and heap scan/vacuum progress. It does not report exact memory consumed; OS/cgroup process metrics are needed to track RSS.

### Exercise 14 — Index progress

pg_stat_progress_create_index displays command, phase, and blocks/tuples progress. It is not a memory usage view.

### Exercise 15 — Slow autovacuum

Not directly. vacuum_cost_delay paces I/O rate. Evaluate cost parameters/storage and workload; raising memory only helps if memory-driven extra cycles are the issue.

### Exercise 16 — Long transactions

Old snapshots may still need old tuple versions, so VACUUM cannot clean them up. High memory does not change the visibility horizon.

### Exercise 17 — Setting scope

Open a DBA session and run SET maintenance_work_mem = '1GB'; after the maintenance command run RESET maintenance_work_mem or close the session. Do not use ALTER SYSTEM if only one job needs it.

### Exercise 18 — VACUUM transaction

VACUUM cannot run inside a transaction block. SET LOCAL only applies within a transaction and thus cannot wrap VACUUM that way; use session-level SET before the command.

### Exercise 19 — ALTER ROLE

ALTER ROLE SET applies the default for new sessions when the role logs in. Already open sessions do not automatically receive the new setting.

### Exercise 20 — Memory budget

Examples: shared_buffers, manual maintenance concurrency, maintenance_work_mem, autovacuum workers/autovacuum_work_mem, query work_mem/hash allowance, backend overhead, OS/filesystem cache, agents, and container memory limits.

### Exercise 21 — Temp files

No. Query sorts/hashes or other operations can generate temp files at the same time. Correlate PID, timestamp, database, application/query, and maintenance progress/logs.

### Exercise 22 — pg_stat_io

pg_stat_io is available starting in PostgreSQL 16. It aggregates I/O activity; it does not report exact memory consumed by each maintenance operation.

### Exercise 23 — vacuum_buffer_usage_limit

This setting controls the buffer ring VACUUM uses to limit impact on shared buffers. maintenance_work_mem limits memory for a maintenance operation; the two settings serve different purposes.

### Exercise 24 — Slow index build

Check table/index size, progress phase, temp files, storage latency/throughput, CPU, memory headroom/RSS, concurrent job count, and locks. Only raise memory if there is evidence that memory/sorting is the bottleneck.

### Exercise 25 — Incident

1. Confirm memory pressure, cgroup/host limits, swap, and OOM logs.
2. List the three index builds, PIDs, session settings, and progress.
3. Check the four autovacuum workers, autovacuum_work_mem, and worker activity.
4. Temporarily stop schedulers from launching new maintenance jobs.
5. Reduce concurrency or pause/cancel select index jobs per approved change/runbook.
6. Cross-check query latency and query memory demand.
7. Restore memory headroom, check for invalid indexes/transaction outcomes.
8. Adjust memory budgets, job scheduling, and autovacuum settings.
9. Monitor the next maintenance run and document incident findings.

---

## 21. Conclusion

maintenance_work_mem is a critical resource limit for VACUUM and maintenance operations such as index builds. Higher values can reduce cleanup passes or temporary sort spills in suitable workloads, yet it is not a total RAM limit and does not replace tuning I/O, lock behavior, or autovacuum policy.

Key principles to remember:

1. maintenance_work_mem applies per operation; multiple concurrent operations can multiply memory demand.
2. autovacuum_work_mem sets the limit per autovacuum worker; -1 inherits maintenance_work_mem.
3. Include autovacuum_max_workers when building a peak memory budget.
4. work_mem is for sort/hash query operations and also has a concurrency multiplier.
5. shared_buffers is the shared cache; effective_cache_size is only a planner estimate.
6. Low VACUUM memory can increase cleanup cycles/I/O; high memory cannot resolve long transactions or cost delays.
7. CREATE INDEX/REINDEX can reduce external sort spills given enough memory, yet storage/CPU remain major factors.
8. Parallel workers of a single command do not mean each worker gets an extra full maintenance_work_mem; verify semantics per version.
9. pg_stat_progress_vacuum and pg_stat_progress_create_index report progress, not exact memory usage.
10. Combine PostgreSQL views with RSS/cgroup/OS metrics and temp-file logs.
11. Use session overrides for a single maintenance job when temporary high memory is needed.
12. Limit job concurrency, especially during pg_restore and index builds.
13. Tune from a baseline, change one factor at a time, and compare duration, memory, temp files, I/O, and application latency.
14. During OOM/memory pressure, reduce concurrency and restore headroom before adding more memory.

Operational workflow: **identify maintenance bottleneck → measure baseline and concurrency → build a memory budget with headroom → choose maintenance/autovacuum limits → apply within a narrow scope → monitor progress/RSS/I/O → compare impact → update scheduler and runbook**.
