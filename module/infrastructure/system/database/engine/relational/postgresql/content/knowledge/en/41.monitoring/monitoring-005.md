# pg_stat_statements and Resource-Intensive Queries in PostgreSQL

`pg_stat_statements` is PostgreSQL's flagship performance statistics extension. It aggregates SQL statements sharing the same normalized structure and tracks metrics such as call counts, total execution time, mean execution time, rows returned or affected, buffer cache hits/reads, temporary blocks, WAL generation, and JIT compilation. This allows DBAs to identify which query groups consume the most resources over an observation period.

Unlike `pg_stat_activity`, which shows backends and queries executing right now, `pg_stat_statements` provides cumulative statistics for statements that have executed. It helps answer questions such as:

- Which query group consumes the largest share of total database time?
- Which query runs infrequently yet takes a very long time per call?
- Which query runs millions of times and creates a huge cumulative cost?
- Which queries read many blocks, spill to temporary files, or generate heavy WAL?
- Is query planning consuming significant time?
- Which statements should be analyzed with EXPLAIN to find the root cause?

```text
                    PostgreSQL server
              +---------------------------+
              | Client SQL statements     |
              +-------------+-------------+
                            |
                            v
              +---------------------------+
              | Parse / plan / execute    |
              +-------------+-------------+
                            |
             instrumentation hooks and queryid
                            |
                            v
              +---------------------------+
              | pg_stat_statements        |
              | normalized query entries  |
              | calls / time / blocks     |
              | WAL / temp / JIT metrics  |
              +-------------+-------------+
                            |
                            v
              +---------------------------+
              | DBA analysis queries      |
              | rank / compare / explain  |
              +---------------------------+
```

This lesson belongs to the **Monitoring** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on enabling the extension properly, reading meaningful metrics, classifying resource-intensive queries, combining cumulative statistics with runtime state, and selecting the next optimization step.

After this lesson, you will be able to:

1. Explain how `pg_stat_statements` groups SQL statements by query identifier.
2. Install the extension and configure `shared_preload_libraries` and query IDs.
3. Read planning, execution, call, row, buffer, temp, WAL, and JIT metrics.
4. Rank queries by total cost, mean latency, call frequency, and I/O.
5. Distinguish slow queries caused by CPU, disk, temporary spills, WAL, planning, or lock waits.
6. Monitor performance by database, user, and `queryid`.
7. Understand the limits of cumulative figures, resets, and entry eviction.
8. Combine `pg_stat_statements` with `pg_stat_activity`, EXPLAIN, and `auto_explain`.
9. Recognize key differences across PostgreSQL 13–18.
10. Build a data-driven monitoring and optimization workflow.

> **Practice scope:** Configuration commands requiring administrative privileges and server restarts are illustrated for lab environments. Enabling tracking carries some overhead; measure its impact before applying it in production. Never reset all statistics without first capturing any baseline snapshots needed for comparison.

---

## 1. What Problem Does pg_stat_statements Solve?

### 1.1. One slow query or an expensive query family?

A SQL query taking 8 seconds per run stands out immediately. Yet a query taking 15 ms and running 500,000 times can consume far more total database time.

If you rely solely on slow-query logs, fast queries executed at high frequency slip past unnoticed. `pg_stat_statements` groups similar SQL statements into a single entry so cumulative cost becomes visible.

Example:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
SELECT * FROM orders WHERE customer_id = 1003;
```

When query identifiers and normalization are active, those statements are typically folded into one pattern:

```sql
SELECT * FROM orders WHERE customer_id = $1;
```

One entry can accumulate thousands or millions of calls sharing that query structure.

### 1.2. Cumulative statistics

`pg_stat_statements` stores cumulative counters and timings from when an entry was created or last reset. It is not a per-request trace, does not store every parameter value, and does not replace query logging.

### 1.3. What the extension tells you

- Number of times a statement executed.
- Total, mean, minimum, maximum, and standard deviation of execution time.
- Planning time if planning tracking is enabled.
- Total rows returned or affected.
- Shared, local, and temporary blocks hit, read, dirtied, or written.
- I/O timings if `track_io_timing` is enabled.
- WAL records, full-page images, and WAL bytes.
- JIT compilation metrics.
- Certain parallel worker metrics in newer releases.

### 1.4. What the extension does not tell you directly

`pg_stat_statements` does not provide:

- The exact execution plan of each individual run.
- Bind parameter values for every invocation.
- The exact timestamp of each execution.
- Detailed wait events for completed calls.
- Lock dependency graphs for queries.
- End-to-end latency in the application, network, or connection pool.

To find the exact root cause, pair it with tools like EXPLAIN, `pg_stat_activity`, PostgreSQL logs, and OS/application metrics.

---

## 2. How pg_stat_statements Records Queries

### 2.1. Query identifier

PostgreSQL computes `queryid` from the post-parse-analysis query representation. Statements differing only in literal constants are typically treated as the same structure.

Example:

```sql
SELECT * FROM products WHERE product_id = 10;
SELECT * FROM products WHERE product_id = 20;
```

These are typically combined into one entry:

```sql
SELECT * FROM products WHERE product_id = $1;
```

### 2.2. What uniquely identifies an entry?

In modern versions, a row in the view is keyed by the combination:

- `userid`: OID of the executing role.
- `dbid`: OID of the database.
- `queryid`: hash of the query structure.
- `toplevel`: whether the statement is top-level or nested.

Thus, the same SQL run by two different users or in two different databases appears as separate entries.

### 2.3. Query text is representative, not a per-statement log

The `query` column holds representative text for the query structure. Literal constants are generally replaced by parameter placeholders such as `$1`, `$2`. The displayed text is typically the first statement captured for that entry.

Therefore:

- Do not use the `query` column to reconstruct exact inputs for individual requests.
- Do not assume every invocation used the same parameter values.
- Do not treat `query` text as a complete SQL history.

### 2.4. Queryid is not a permanent global ID

`queryid` is useful for identifying queries within a specific environment, but it is not guaranteed to remain stable across major versions. It also depends on the parse tree, object identifiers, `search_path`, machine architecture, and build/platform details.

When comparing multiple servers:

- Do not assume `queryid` matches across logical replicas.
- Do not join statistics across major versions solely by `queryid`.
- You may need to combine database, user, normalized query text, and application metadata.
- Two visually identical queries can still produce separate entries if parse semantics differ.

### 2.5. Hash collisions

There is a small probability that two unrelated query structures suffer a hash collision and share an entry. This is rare; `queryid` remains a practical grouping mechanism, though not a mathematically guaranteed unique key.

### 2.6. IN lists

Queries differing only in the number of constant elements in an `IN` list may be folded into a single entry. Representative text may appear like:

```sql
SELECT * FROM events
WHERE event_id IN ($1 /*, ... */);
```

This keeps entry counts down, while also meaning one entry can aggregate varying list sizes.

### 2.7. Nested statements

Parameter:

```conf
pg_stat_statements.track = top
```

`top` records only statements sent directly by clients. Set to `all` to also track nested statements, such as SQL invoked inside functions or triggers.

With `all`, both the outer statement and inner statements appear. Do not sum timings across all entries as though they were independent, because costs get counted at multiple nesting levels.

### 2.8. Utility statements

`pg_stat_statements.track_utility` controls tracking of utility commands, such as DDL, maintenance, and administrative commands. The default is `on`.

If disabled, the view continues tracking standard SQL DML/queries while skipping utility commands covered by this setting.

---

## 3. Installing pg_stat_statements

### 3.1. The extension typically ships with PostgreSQL contrib

On many operating systems, `pg_stat_statements` is packaged in PostgreSQL's contrib/additional modules package. Install the package matching your running major version.

Package names vary by distribution and installation method. If the server reports a missing control file or shared library, verify that the extension package matches the server major version.

### 3.2. Adding to shared_preload_libraries

Open `postgresql.conf` on the server:

```conf
shared_preload_libraries = 'pg_stat_statements'
```

If other modules are already listed in `shared_preload_libraries`, preserve them and append the new extension, for example:

```conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
```

Never overwrite preloaded modules already required by your applications or infrastructure.

### 3.3. Enabling the query identifier

In modern PostgreSQL:

```conf
compute_query_id = auto
```

Or:

```conf
compute_query_id = on
```

`pg_stat_statements` requires a query identifier to group SQL statements. If a third-party module computes `queryid`, follow its documentation and avoid conflicting query ID providers.

### 3.4. Basic tracking configuration

Example:

```conf
pg_stat_statements.max = 10000
pg_stat_statements.track = top
pg_stat_statements.track_utility = on
pg_stat_statements.track_planning = off
pg_stat_statements.save = on
```

Meanings:

| Parameter | Purpose |
|---|---|
| `max` | Maximum number of tracked entries |
| `track` | Select `top`, `all`, or `none` |
| `track_utility` | Whether to record utility statements |
| `track_planning` | Whether to record planning time |
| `save` | Whether to persist statistics across shutdown/restart |

### 3.5. Restarting the server

Because the extension allocates shared memory at server startup, adding or removing `pg_stat_statements` in `shared_preload_libraries` requires restarting PostgreSQL. Reloading configuration is not enough.

After restarting, verify:

```sql
SHOW shared_preload_libraries;
SHOW compute_query_id;
SHOW pg_stat_statements.max;
SHOW pg_stat_statements.track;
```

### 3.6. CREATE EXTENSION in each database

Connect to every database where you intend to query the view:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Key distinction:

- The module is preloaded at the server level.
- Statistics are collected server-wide across all databases.
- The view and SQL functions are installed per database via `CREATE EXTENSION`.

If a DBA creates the extension only in the `postgres` database, the view does not appear automatically in `appdb`. To query the view from `appdb`, run `CREATE EXTENSION` inside `appdb`.

### 3.7. Verifying the extension

```sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';
```

In `psql`:

```text
\dx pg_stat_statements
\d+ pg_stat_statements
```

`extversion` reports the SQL extension version installed in the database. It is not the PostgreSQL server major version.

### 3.8. Upgrading the extension

After upgrading PostgreSQL packages or installing a newer extension version, check `extversion` and update as documented:

```sql
ALTER EXTENSION pg_stat_statements UPDATE;
```

Do not assume upgrading binary packages automatically updates extension metadata and view definitions in every database.

---

## 4. Important Configuration Parameters

### 4.1. pg_stat_statements.max

`pg_stat_statements.max` sets the maximum number of tracked entries. The default is typically 5000. Once distinct query structures exceed this limit, the extension evicts the least-executed entries to make room for new ones.

Higher values:

- Retain more query patterns.
- Reduce the risk of losing statistics for infrequent statements.
- Increase shared memory consumption.

This parameter takes effect only at server start, so changing it requires a restart.

### 4.2. Monitoring deallocations

The `pg_stat_statements_info` view exposes a `dealloc` counter showing how many times entries were evicted due to reaching `pg_stat_statements.max`.

```sql
SELECT
    dealloc,
    stats_reset
FROM pg_stat_statements_info;
```

If `dealloc` climbs rapidly during an observation period, `max` may be too small for the number of query patterns. Before increasing it, review shared memory capacity and whether `track = all` is actually needed.

### 4.3. pg_stat_statements.track

Three settings:

| Value | Meaning |
|---|---|
| `top` | Top-level statements from clients only; default |
| `all` | Also records nested statements inside functions/triggers |
| `none` | Disables statement statistics collection |

`all` helps inspect SQL inside stored procedures, though it creates more entries and causes parent/child metrics to overlap.

### 4.4. pg_stat_statements.track_utility

Defaults to `on`. Disable when you care only about standard SQL statements and want to reduce tracked utility entries.

Utility commands are not limited to DDL; this setting covers commands outside SELECT, INSERT, UPDATE, DELETE, and MERGE. Exact coverage depends on command type and version.

### 4.5. pg_stat_statements.track_planning

Defaults to `off`. When enabled, the extension records:

- Number of plans.
- Total planning time.
- Min/max/mean/stddev planning time.

Planning tracking can add noticeable contention when many concurrent sessions execute the same query structure and update the same shared entry. Enable it when investigating planning bottlenecks, measure the overhead, and consider turning it back off after gathering sufficient data.

This parameter was added in PostgreSQL 13. The `off` default avoids performance regressions under high-concurrency workloads.

### 4.6. pg_stat_statements.save

Defaults to `on`. When enabled, statistics are saved across shutdown and restart via the extension's persistence mechanism. When disabled, statistics are discarded on shutdown and not reloaded on startup.

Configure this in `postgresql.conf` or via command-line options.

### 4.7. track_io_timing

I/O time columns in `pg_stat_statements` are populated only when `track_io_timing` is enabled:

```conf
track_io_timing = on
```

I/O timings reveal whether queries spend time waiting to read or write data blocks or temp files. Timing measurement can incur overhead depending on OS and storage; benchmark with `pg_test_timing` and measure in a production-like environment.

### 4.8. compute_query_id

In modern PostgreSQL, `compute_query_id = auto` activates automatically when a module needing query identifiers is preloaded. You can set it explicitly to `on` if desired.

If query ID generation is disabled or delegated to an external module, behavior follows that configuration and module. Verify that `queryid` is populated in the view.

### 4.9. Configuration permissions

Many tracking parameters can be modified only by superusers. Parameters requiring restarts require config editing and service management permissions. In managed PostgreSQL, you may need parameter groups, extension allowlists, and a maintenance restart.

---

## 5. Reading the pg_stat_statements View Structure

### 5.1. Identification columns

| Column | Meaning |
|---|---|
| userid | OID of the role running the statement |
| dbid | OID of the database |
| queryid | Hash identifier of the query structure |
| toplevel | Whether statement is top-level or nested, on versions with this column |
| query | Normalized representative text |

When reporting across databases or users, resolve names instead of showing raw OIDs:

```sql
SELECT
    d.datname,
    r.rolname,
    s.queryid,
    s.calls,
    s.total_exec_time,
    s.query
FROM pg_stat_statements AS s
LEFT JOIN pg_database AS d ON d.oid = s.dbid
LEFT JOIN pg_roles AS r ON r.oid = s.userid
ORDER BY s.total_exec_time DESC
LIMIT 20;
```

### 5.2. Planning metrics

| Column | Meaning |
|---|---|
| plans | Number of times the statement was planned |
| total_plan_time | Total planning time, ms |
| mean_plan_time | Average planning time, ms |
| min_plan_time / max_plan_time | Fastest/slowest planning time |
| stddev_plan_time | Standard deviation of planning time |

These columns remain 0 when `track_planning` is off. `plans` need not equal `calls`: a statement can be planned and then fail execution, or execute using a cached plan without triggering a new planning event.

### 5.3. Execution metrics

| Column | Meaning |
|---|---|
| calls | Number of statement executions |
| total_exec_time | Total execution time, ms |
| mean_exec_time | Average time, ms |
| min_exec_time / max_exec_time | Fastest/slowest time, ms |
| stddev_exec_time | Standard deviation of execution time |
| rows | Total rows returned or affected |

Times are in milliseconds. Total execution time sums cost across all recorded calls; with concurrent queries running in parallel, this total can exceed elapsed wall-clock time.

### 5.4. Shared blocks

| Column | Meaning |
|---|---|
| shared_blks_hit | Blocks found in PostgreSQL shared buffers |
| shared_blks_read | Blocks read into shared buffers |
| shared_blks_dirtied | Blocks dirtied by the statement |
| shared_blks_written | Blocks written directly by the statement |

A block is PostgreSQL's page unit; 8 KB is standard, though you should verify the cluster's `block_size`.

```sql
SHOW block_size;
```

`shared_blks_read` does not guarantee physical disk reads: the block may already reside in the OS page cache. It indicates PostgreSQL had to load the block into `shared_buffers`.

### 5.5. Local blocks

`local_blks_hit`, `local_blks_read`, `local_blks_dirtied`, and `local_blks_written` reflect local buffer activity, typically associated with temporary tables.

These are distinct from `temp_blks_*`, which track temporary files created when operations such as sorts or hashes spill to disk.

### 5.6. Temporary blocks

| Column | Meaning |
|---|---|
| temp_blks_read | Temporary blocks read |
| temp_blks_written | Temporary blocks written |
| temp_blk_read_time | Time spent reading temporary blocks if I/O timing is enabled |
| temp_blk_write_time | Time spent writing temporary blocks if I/O timing is enabled |

High temporary blocks can indicate sorts/hashes exceeding memory, queries processing large datasets, or suboptimal `work_mem`. Do not increase `work_mem` server-wide immediately; one backend can allocate memory for multiple operations and concurrent sessions can multiply total usage sharply.

### 5.7. I/O timing

In older versions, the view used `blk_read_time` and `blk_write_time`. PostgreSQL 18 splits block read/write timings into shared, local, and temp block times, such as `shared_blk_read_time`, `local_blk_read_time`, and `temp_blk_read_time`.

Timing fields are populated only when `track_io_timing` is enabled. If disabled, they remain 0 and cannot be used to conclude a query spent no time waiting on I/O.

### 5.8. WAL metrics

| Column | Meaning |
|---|---|
| wal_records | WAL records generated by the statement |
| wal_fpi | Full-page images generated |
| wal_bytes | Total WAL bytes |
| wal_buffers_full | Number of times WAL buffers became full; in newer versions |

High WAL generation can stem from bulk UPDATE/DELETE/INSERT operations, index maintenance, full-page images, or large write batches. It affects WAL volume, archiving, replication, and recovery time.

### 5.9. JIT metrics

`jit_*` columns record the number of JIT-compiled functions and time spent in generation, inlining, optimization, emission, and deforming.

If short queries spend significant time in JIT compilation, compilation overhead may outweigh execution gains. Compare JIT metrics with `total_exec_time` and test `SET jit = off` in a lab session rather than flipping global settings blindly.

### 5.10. Parallel worker metrics in PostgreSQL 18

PostgreSQL 18 adds:

- `parallel_workers_to_launch`: number of workers requested by the plan.
- `parallel_workers_launched`: number of workers actually launched.

A wide gap suggests workers could not be launched due to resource limits or contention. Not all queries use parallelism; inspect the execution plan.

### 5.11. Timestamps in PostgreSQL 18

PostgreSQL 18 provides `stats_since` and `minmax_stats_since`:

- `stats_since`: timestamp when stats collection started for this entry.
- `minmax_stats_since`: timestamp when the min/max statistics window began.

These columns help interpret min/max values after selective resets.

---

## 6. PostgreSQL Versions and Schema Differences

### 6.1. Never assume the view has identical columns across all major versions

The `pg_stat_statements` schema has evolved across major releases. A monitoring query written for PostgreSQL 18 will fail on PostgreSQL 13 or 14 if it references newly added columns.

Always inspect the actual view:

```sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'pg_stat_statements'
ORDER BY ordinal_position;
```

The extension's schema depends on where it was installed; in `psql` you can inspect directly:

```text
\d+ pg_stat_statements
```

### 6.2. Notable version milestones

| Version | Key Points |
|---|---|
| PostgreSQL 13 | Added `track_planning` and planning metrics; `track_planning` defaults to `off` |
| PostgreSQL 14 | Added `pg_stat_statements_info` view with `dealloc` and `stats_reset` |
| PostgreSQL 15–17 | Includes execution, planning, block, I/O, WAL, and JIT metrics per version schema |
| PostgreSQL 18 | Adds parallel worker fields, `stats_since`, `minmax_stats_since`, finer-grained I/O timing splits, and WAL buffer metric |

### 6.3. I/O timing column renames

PostgreSQL 13–17 use `blk_read_time` and `blk_write_time` for block I/O timings (alongside temp timing in supported versions). PostgreSQL 18 separates shared/local/temp:

- `shared_blk_read_time`
- `shared_blk_write_time`
- `local_blk_read_time`
- `local_blk_write_time`
- `temp_blk_read_time`
- `temp_blk_write_time`

When writing dashboards spanning multiple major versions, use version-specific queries or check schemas before referencing columns.

### 6.4. pg_stat_statements_info

This view was introduced in PostgreSQL 14. PostgreSQL 13 does not include it in the bundled extension version.

```sql
SELECT *
FROM pg_stat_statements_info;
```

Do not query this view on PostgreSQL 13 without a version check.

### 6.5. pg_stat_statements_reset signatures

Older versions provide overloads taking `userid`, `dbid`, and `queryid`. Modern versions add a `minmax_only` parameter and return the reset timestamp. The simple form:

```sql
SELECT pg_stat_statements_reset();
```

is supported to reset all stats in modern versions. When writing cross-version automation, check the function signature in `psql`:

```text
\df pg_stat_statements_reset
```

### 6.6. Extension version vs. server version

PostgreSQL server major version and the extension's `extversion` are distinct. After a server upgrade, check extension update scripts and update inside each database as documented for your package and version.

---

## 7. Finding Queries Consuming the Most Total Time

### 7.1. Ranking by total_exec_time

This is the first query to run when identifying which query families consume the most cumulative execution time:

```sql
SELECT
    d.datname,
    r.rolname,
    s.queryid,
    s.calls,
    round(s.total_exec_time::numeric, 2) AS total_exec_ms,
    round(s.mean_exec_time::numeric, 2) AS mean_exec_ms,
    s.rows,
    s.shared_blks_read,
    s.temp_blks_written,
    left(s.query, 500) AS query_sample
FROM pg_stat_statements AS s
LEFT JOIN pg_database AS d ON d.oid = s.dbid
LEFT JOIN pg_roles AS r ON r.oid = s.userid
WHERE s.toplevel
ORDER BY s.total_exec_time DESC
LIMIT 20;
```

If your version lacks the `toplevel` column, remove that condition.

### 7.2. Filtering to a single database

```sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database
              WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 7.3. Why total time matters

Example:

| Query | Calls | Mean time | Total time |
|---|---:|---:|---:|
| A | 2,000,000 | 4 ms | 8,000,000 ms |
| B | 50 | 2,000 ms | 100,000 ms |

Query B is far slower per call, yet Query A consumes 80 times as much total execution time. If the goal is reducing total database load, Query A is the higher priority.

### 7.4. Total time is not server wall-clock time

`total_exec_time` sums duration across every invocation. Concurrent queries running in parallel can easily push total execution time above elapsed wall-clock time. Never sum all entries to infer how many minutes the server has been running.

### 7.5. Do not look only at the #1 query

The top query might be a legitimate batch job. Inspect the top 20, comparing calls, rows, user/database, and observation duration to understand load sources.

---

## 8. Finding Queries with High Average Latency

### 8.1. Ranking by mean execution time

```sql
SELECT
    queryid,
    calls,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(max_exec_time::numeric, 2) AS max_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE calls >= 10
ORDER BY mean_exec_time DESC
LIMIT 20;
```

A `calls` threshold prevents one-off queries from dominating the ranking as though they represented ongoing workload. Adjust the threshold to match your system.

### 8.2. High mean and low calls

Possible explanations:

- Rare analytical report processing large data volumes.
- Scheduled periodic job.
- Query hitting a bad plan for specific parameter values.
- Query experiencing blocking or storage stalls.

### 8.3. Low mean and very high calls

A 2 ms query executed 300,000 times per minute can still create heavy CPU and connection overhead. Reducing call frequency, batching requests, or caching in the application may help far more than tweaking execution plans.

### 8.4. Max and standard deviation

`max_exec_time` surfaces outliers; `stddev_exec_time` reveals variance. A query with a low mean but huge max may suffer from parameter sensitivity, cold cache, lock waits, or data skew.

### 8.5. Note on min/max after reset

After a selective `minmax_only` reset, min/max values reset to 0 until the query executes again. PostgreSQL 18 adds `minmax_stats_since` to show when the current min/max window began.

---

## 9. Finding Queries Reading Many Blocks and Causing I/O Pressure

### 9.1. Ranking by shared blocks read

```sql
SELECT
    queryid,
    calls,
    shared_blks_hit,
    shared_blks_read,
    round(
        100.0 * shared_blks_hit /
        NULLIF(shared_blks_hit + shared_blks_read, 0),
        2
    ) AS shared_hit_pct,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
```

### 9.2. Cache hit ratio is not the only metric

A query with a 99.9% shared hit ratio can still impose massive CPU load if it scans billions of blocks from `shared_buffers`. Conversely, a low-hit-ratio query that runs rarely and touches few blocks may not be worth prioritizing.

Evaluate together:

- Total blocks hit and read.
- Calls and mean execution time.
- Total execution time.
- I/O timing.
- Table/index size and concurrent workload.

### 9.3. Converting blocks to bytes

```sql
SELECT
    queryid,
    calls,
    shared_blks_read,
    shared_blks_read *
        current_setting('block_size')::bigint AS shared_read_bytes,
    temp_blks_written,
    temp_blks_written *
        current_setting('block_size')::bigint AS temp_write_bytes,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
```

These are bytes per PostgreSQL block accounting, not an exact count of physical bytes hitting storage devices. OS page cache, read-ahead, and storage layers alter actual physical I/O.

### 9.4. Block reads and writes

Queries with high `shared_blks_read` may be scanning large datasets or touching a working set that exceeds `shared_buffers`. High `shared_blks_dirtied`/`written` typically correspond to write workloads or dirty buffer pressure.

Do not conclude a query is disk-bound from `shared_blks_read` alone. Inspect I/O timings and OS storage metrics.

### 9.5. Per-query I/O timing

When `track_io_timing` is enabled, PostgreSQL records I/O timings. On PostgreSQL 13–17:

```sql
SELECT
    queryid,
    calls,
    round(blk_read_time::numeric, 2) AS read_ms,
    round(blk_write_time::numeric, 2) AS write_ms,
    round(total_exec_time::numeric, 2) AS exec_ms,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY blk_read_time + blk_write_time DESC
LIMIT 20;
```

On PostgreSQL 18, replace the block timing columns with the appropriate shared/local/temp block timing columns, such as `shared_blk_read_time` and `temp_blk_write_time`.

### 9.6. Reading I/O time carefully

I/O timing accumulates time spent waiting on block I/O as measured by PostgreSQL. It is not CPU time. A query with high `total_exec_time` but low I/O time is likely spending time on CPU, planning, lock waits, or in-memory work.

### 9.7. Local buffers and temporary files

Local blocks usually correspond to temporary tables; temp blocks reflect temporary files created by the executor. If temp blocks surge, inspect sort/hash nodes in EXPLAIN and `log_temp_files` to identify spilling operations.

---

## 10. Finding Queries Generating Heavy Temporary Blocks

### 10.1. Ranking by temp blocks

```sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE temp_blks_read > 0
   OR temp_blks_written > 0
ORDER BY temp_blks_written + temp_blks_read DESC
LIMIT 20;
```

### 10.2. Common causes

- `ORDER BY` or `DISTINCT` sorting large numbers of rows.
- Hash joins or hash aggregations exceeding memory budgets.
- Window functions over large partitions.
- Materialized CTEs or large intermediate results.
- Missing filter predicates causing excessive data processing.
- `work_mem` too small for a specific operation.

### 10.3. work_mem is a per-operation limit

`work_mem` is not the total memory cap for a backend. One query can run multiple sort/hash operations, and many sessions run concurrently. Raising global `work_mem` too high can cause memory usage to scale dangerously with connections and active operations.

### 10.4. Choosing a fix

Before raising `work_mem`:

1. Inspect `EXPLAIN (ANALYZE, BUFFERS)`.
2. Check estimated rows vs. actual rows.
3. Identify which plan node is spilling.
4. Check whether the query can filter rows earlier.
5. Review indexes, join order, sort keys, and statistics.
6. Test per-session or per-transaction `work_mem` changes in a lab.

### 10.5. Logging temporary files

You can use:

```conf
log_temp_files = 0
```

`0` logs every temporary file; a positive integer logs only files larger than that threshold in KB. This can produce heavy log volume, so pick a sensible threshold and limit the investigation window.

### 10.6. Database-level temporary bytes

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

This is a database-level metric useful for finding which database creates the most temp files. Use `pg_stat_statements` to locate the responsible query groups.

---

## 11. Finding Queries Generating Heavy WAL

### 11.1. Ranking by wal_bytes

```sql
SELECT
    queryid,
    calls,
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    round(
        wal_bytes / NULLIF(calls, 0) / 1024.0,
        2
    ) AS wal_kb_per_call,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### 11.2. Why is WAL large?

- Large-scale INSERT/UPDATE/DELETE operations.
- Updating many indexes per row.
- Bulk loads or maintenance operations.
- Post-checkpoint full-page images depending on workload.
- Heavy modifications across large tables and indexes.

### 11.3. wal_records and wal_fpi

`wal_records` counts WAL records created by the statement. `wal_fpi` counts full-page images. FPIs protect pages after checkpoints under certain conditions; high FPI rates can significantly expand WAL volume.

### 11.4. Consequences of high WAL volume

Heavy WAL generation can lead to:

- High bandwidth and storage demand for WAL archiving.
- Growing replication lag if standbys cannot keep up.
- Larger backup and PITR storage footprints.
- Increased checkpoint and storage write pressure.

### 11.5. Do not treat WAL bytes as physical disk bytes written

`wal_bytes` measures WAL generated by the statement, not exact physical bytes written to storage. WAL compression, full-page writes, batching, and storage behavior all alter physical I/O.

### 11.6. Diagnosing write workloads

Combine:

- Query groups with high `wal_bytes`.
- Calls and rows affected.
- Indexes on the modified tables.
- Autovacuum and dead tuples.
- Replication lag and archive throughput.
- Server-level checkpoint and WAL metrics.

Never optimize by dropping required indexes or weakening durability settings without evaluating correctness and recovery requirements.

---

## 12. Finding Planning Overhead and JIT Overhead

### 12.1. High planning time

If `track_planning` is enabled, rank by `total_plan_time`:

```sql
SELECT
    queryid,
    plans,
    calls,
    round(total_plan_time::numeric, 2) AS total_plan_ms,
    round(mean_plan_time::numeric, 2) AS mean_plan_ms,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 400) AS query_sample
FROM pg_stat_statements
WHERE plans > 0
ORDER BY total_plan_time DESC
LIMIT 20;
```

### 12.2. Why does planning take time?

- Queries joining many tables with a large join-order search space.
- Partitioned tables with huge partition counts.
- Dynamically generated complex SQL structures.
- Poor statistics forcing the planner to evaluate many options or choose suboptimal plans.
- Prepared statements vs. custom plans producing varied planning patterns.

### 12.3. Plans do not always equal calls

Planning and execution counters update at different stages:

- Statement plans successfully but execution errors: `plans` increments while `calls` may not.
- Cached plan is reused: `calls` increments without incrementing `plans`.
- Certain statements follow special parse/plan paths.

Do not treat mismatches between `plans` and `calls` as a bug.

### 12.4. JIT

If JIT metrics are large compared to `total_exec_time`, compilation may be a major contributor to latency. Use EXPLAIN to inspect JIT details and test toggling JIT in a lab session with identical queries, parameters, and data.

### 12.5. Do not enable track_planning unconditionally

Because planning tracking can introduce entry contention under concurrent workloads, enable it only when hunting a planning bottleneck. Collect enough data, assess overhead, and decide whether to keep or disable it.

---

## 13. Combining pg_stat_statements with pg_stat_activity

### 13.1. Two views answering different questions

| View | Question Answered |
|---|---|
| pg_stat_statements | Which query groups consumed cumulative resources? |
| pg_stat_activity | Which backends are running or waiting right now? |

A long-running query may not update `pg_stat_statements` execution counters until the invocation finishes. Therefore, when investigating an active incident, check `pg_stat_activity` first.

### 13.2. Inspecting currently running queries

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    query_id,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

`query_id` exists in modern versions when query ID computation is active. If your version lacks this column, omit it from the query.

### 13.3. Finding lock blockers

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.usename AS waiting_user,
    waiting.datname,
    waiting.wait_event_type,
    waiting.wait_event,
    now() - waiting.query_start AS waiting_age,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 300) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY waiting.query_start;
```

If a query exhibits high mean execution time, the cause may be lock waits rather than plan quality or I/O. Check `wait_event` and blockers to classify it.

### 13.4. Linking active queries to cumulative statistics

On PostgreSQL versions with `query_id` and `toplevel`:

```sql
SELECT
    a.pid,
    a.usename,
    a.datname,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_id,
    s.calls,
    round(s.mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(s.total_exec_time::numeric, 2) AS total_exec_ms,
    left(a.query, 300) AS active_query
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_statements AS s
  ON s.queryid = a.query_id
 AND s.userid = a.usesysid
 AND s.dbid = (SELECT oid FROM pg_database
               WHERE datname = a.datname)
 AND s.toplevel
WHERE a.state = 'active'
ORDER BY a.query_start;
```

This join is diagnostic. The statistics entry shows historical cumulative figures across past runs, not the duration of the currently active invocation.

### 13.5. Query age does not equal CPU execution time

`now() - query_start` is elapsed time since the query started. It can include lock waits, I/O waits, and other waits. When a backend is `idle in transaction`, `query_start` also does not measure how long the transaction has been open.

### 13.6. Finding long-open transactions

```sql
SELECT
    pid,
    usename,
    datname,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Long transactions can hold locks, snapshots, and dead tuples. This represents a different line of investigation from queries with high `total_exec_time`.

---

## 14. Using EXPLAIN to Find the Root Cause

### 14.1. pg_stat_statements finds the target; EXPLAIN finds the cause

`pg_stat_statements` identifies which query patterns deserve investigation. EXPLAIN shows the execution plan PostgreSQL chooses for a query.

Example:

```sql
EXPLAIN
SELECT *
FROM sales.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

### 14.2. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, VERBOSE)
SELECT *
FROM sales.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

EXPLAIN ANALYZE actually executes the statement. For SELECT, it runs the query and reports actual rows and timings. For INSERT/UPDATE/DELETE, it modifies data.

### 14.3. DML and rollback in a lab

In a lab, wrap DML tests in a transaction and roll back:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE sales.orders
SET status = 'archived'
WHERE created_at < DATE '2024-01-01';

ROLLBACK;
```

Rolling back does not undo every side effect outside the transaction, such as consumed sequence values or external calls triggered by triggers. Test only on safe data.

### 14.4. Reading actual rows vs. estimated rows

Compare estimated rows with actual rows:

- Estimate far too low: planner may pick nested loops or an unsuitable plan.
- Estimate far too high: planner may choose unnecessary hash or merge strategies.
- Wide discrepancies often point to stale statistics, data skew, or correlated columns.

### 14.5. BUFFERS

BUFFERS reports shared/local/temp blocks hit, read, dirtied, and written per plan node. Use it to isolate which node reads the most blocks or triggers temp I/O.

### 14.6. WAL

Depending on PostgreSQL version, EXPLAIN WAL reports WAL records, full-page images, and WAL bytes generated by the analyzed statement—valuable for large inserts and updates.

### 14.7. SETTINGS

EXPLAIN SETTINGS lists non-default planner settings affecting the plan, making it easier to reproduce environments during investigations.

### 14.8. Comparing lab plans with production workloads

A lab plan can differ from production due to:

- Different parameter values.
- Different data distributions and table sizes.
- Different cache states.
- Different statistics.
- Different concurrency and locks.
- Different PostgreSQL versions or configuration.

Never optimize based solely on a single EXPLAIN run with unrepresentative parameters.

---

## 15. Logging Execution Plans Automatically with auto_explain

### 15.1. When is auto_explain needed?

`auto_explain` logs execution plans for queries exceeding a duration threshold directly to PostgreSQL logs. It is invaluable when slow queries occur intermittently and a DBA cannot run EXPLAIN ANALYZE at the exact moment.

### 15.2. Preloading both modules

Both modules can be preloaded together:

```conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
```

Changing `shared_preload_libraries` requires a server restart.

### 15.3. Configuring log thresholds

Example:

```conf
auto_explain.log_min_duration = '500ms'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_wal = on
auto_explain.log_timing = off
auto_explain.log_nested_statements = on
```

This example illustrates an investigative configuration; verify supported parameters for your running major version.

### 15.4. Overhead

ANALYZE and timing can introduce overhead. With `log_analyze` enabled, the executor tracks actual row counts; with `log_timing` enabled, per-node timings are measured.

To contain overhead:

- Set an appropriate `log_min_duration`.
- Consider `log_timing = off` when row counts and buffers are sufficient.
- Use `sample_rate` where appropriate.
- Limit the investigation timeframe.
- Monitor log volume and disk capacity.

### 15.5. Using queryid to link logs and statistics

You can configure `log_line_prefix` to include the query identifier where supported by your PostgreSQL version, then correlate `queryid` in logs with `pg_stat_statements`. Since `queryid` is not guaranteed stable across major versions, do not use it as a permanent key in long-term historical warehouses.

---

## 16. Classifying Resource-Intensive Queries

### 16.1. CPU-bound candidate

Indicators:

- High total/mean execution time.
- Relatively low shared I/O time.
- Minimal temp I/O.
- Plan containing heavy joins, aggregates, expressions, or high processed row counts.

These are indicative clues only; `pg_stat_statements` does not expose per-statement CPU time directly.

### 16.2. I/O-bound candidate

Indicators:

- High `shared_blks_read`.
- High I/O timings when `track_io_timing` is enabled.
- Plan showing large sequential scans or random index lookups.
- Storage latency in OS/cloud metrics climbing simultaneously.

### 16.3. Memory/temp spill candidate

Indicators:

- High `temp_blks_read`/`written`.
- EXPLAIN showing multi-batch sorts/hashes or disk usage.
- Rising temporary file log entries.

Inspect the query plan and `work_mem` before adjusting settings.

### 16.4. WAL-heavy write workload

Indicators:

- High `wal_bytes`, `wal_records`, or `wal_fpi`.
- High call counts or row counts on UPDATE/DELETE/INSERT.
- Rising replication lag, archive backlog, or WAL disk usage.

### 16.5. Planning-heavy workload

Indicators:

- High `total_plan_time`/`mean_plan_time` when `track_planning` is enabled.
- Queries with many joins/partitions or dynamic SQL.
- Planning time dominating total plan + execution time.

### 16.6. Lock-wait candidate

`pg_stat_statements` does not break out lock wait time separately. Cross-check `pg_stat_activity.wait_event_type = 'Lock'`, `pg_blocking_pids()`, and transaction age.

### 16.7. Network/application-bound

The database may complete queries quickly while the application remains slow due to:

- Network latency.
- Returning excessive rows.
- Serialization/deserialization overhead.
- Connection pool queueing.
- Application-side processing.

`pg_stat_statements` tracks rows and execution metrics, not full client request-to-response time.

---

## 17. Statistics Resets and Time-Series Tracking

### 17.1. Statistics are cumulative counters

Values such as `calls`, `total_exec_time`, blocks, and WAL grow continuously while an entry is tracked. Without knowing the last reset timestamp, you cannot interpret counts as covering a fixed time window.

### 17.2. Checking the reset timestamp

From PostgreSQL 14 onward:

```sql
SELECT
    dealloc,
    stats_reset
FROM pg_stat_statements_info;
```

PostgreSQL 13 lacks `pg_stat_statements_info`; track reset timestamps via separate monitoring metadata or logs.

### 17.3. Resetting all statistics

```sql
SELECT pg_stat_statements_reset();
```

This wipes cumulative statistics. Never run it periodically without first saving a snapshot, or you will lose the baseline needed for workload comparisons.

### 17.4. Resetting a single entry

`pg_stat_statements_reset` overloads vary across extension versions. In modern versions, you can reset by user/database/queryid and optionally reset only min/max values:

```sql
SELECT pg_stat_statements_reset(
    userid := 0,
    dbid := 0,
    queryid := 123456789,
    minmax_only := false
);
```

Replace `queryid` with an actual value. Check the function signature for your major version before automating; PostgreSQL 13 lacks the `minmax_only` parameter.

### 17.5. Resetting only min/max

On supported versions, `minmax_only = true` resets only planning/execution min/max fields while preserving all other cumulative counters. This opens a fresh min/max window without erasing overall historical counters.

### 17.6. Saving snapshots before resetting

A simple history table:

```sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE IF NOT EXISTS monitoring.query_stats_history (
    captured_at TIMESTAMPTZ NOT NULL,
    dbid OID NOT NULL,
    userid OID NOT NULL,
    queryid BIGINT NOT NULL,
    calls BIGINT NOT NULL,
    total_exec_time DOUBLE PRECISION NOT NULL,
    total_plan_time DOUBLE PRECISION NOT NULL,
    rows BIGINT NOT NULL,
    shared_blks_read BIGINT NOT NULL,
    temp_blks_written BIGINT NOT NULL,
    wal_bytes NUMERIC NOT NULL,
    query_text TEXT
);
```

Capture a snapshot:

```sql
INSERT INTO monitoring.query_stats_history
SELECT
    clock_timestamp(),
    dbid,
    userid,
    queryid,
    calls,
    total_exec_time,
    total_plan_time,
    rows,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements;
```

Across PostgreSQL 13–18, the selected columns above exist in those modern releases; verify the extension schema when targeting older systems or custom builds.

### 17.7. Computing deltas between two snapshots

Use `LAG` to compute calls and execution time occurring between two samples:

```sql
WITH samples AS (
    SELECT
        captured_at,
        dbid,
        userid,
        queryid,
        calls,
        total_exec_time,
        LAG(calls) OVER (
            PARTITION BY dbid, userid, queryid
            ORDER BY captured_at
        ) AS previous_calls,
        LAG(total_exec_time) OVER (
            PARTITION BY dbid, userid, queryid
            ORDER BY captured_at
        ) AS previous_exec_time
    FROM monitoring.query_stats_history
)
SELECT
    captured_at,
    dbid,
    userid,
    queryid,
    calls - previous_calls AS calls_in_interval,
    total_exec_time - previous_exec_time AS exec_ms_in_interval
FROM samples
WHERE previous_calls IS NOT NULL
  AND calls >= previous_calls
  AND total_exec_time >= previous_exec_time
ORDER BY captured_at DESC, exec_ms_in_interval DESC;
```

Non-negative delta filters exclude intervals where counters reset between snapshots. Also account for evicted entries, `queryid` shifts after DDL/upgrades, and new entries appearing only in later snapshots.

### 17.8. Rate over time

Divide call or `total_exec_time` deltas by the elapsed seconds between snapshots to get rates. Use actual `captured_at` timestamps rather than assuming scheduler intervals are exact.

### 17.9. Do not reset to create time windows when you can snapshot

Periodic snapshots allow comparing arbitrary windows without discarding data. Reset only with a clear goal, proper administrative privileges, and saved baselines.

### 17.10. Deallocation and the query text file

Rising `dealloc` means entries are being evicted due to `max`. Additionally, query text is stored in an external file outside shared memory; if too many long query texts accumulate, that file can grow large and the extension may discard query text, leaving `query` NULL while counters remain.

Monitor shared memory sizing, `dealloc`, and disk footprint together rather than blindly raising `max`.

---

## 18. Access Permissions and Security

### 18.1. The view holds sensitive information

Query text can expose:

- Internal table and schema names.
- Business column names.
- Query logic and structures.
- Literal values in some statements, notably utility commands or cases where normalization does not apply.
- Application implementation details.

Never treat query text as harmless metadata.

### 18.2. Viewing another user's query text

Only superusers or roles granted `pg_read_all_stats` can view SQL text and `queryid` for queries executed by other users. Other roles can view counter statistics, while another user's query text and `queryid` remain hidden under security rules.

### 18.3. Granting monitoring privileges

Grant the predefined role:

```sql
GRANT pg_read_all_stats TO monitoring_reader;
```

This role grants broad server-wide statistics visibility. Grant it only to DBAs or monitoring services that require it; never grant it by default to application users.

### 18.4. Reset permissions

By default, only superusers can call `pg_stat_statements_reset`. You can `GRANT EXECUTE` to another role if needed, keeping in mind it erases shared telemetry across the server. Control it via dedicated roles and auditing.

### 18.5. Extension installed per database

SQL views and functions exist only in databases where `CREATE EXTENSION` was executed. That does not mean each database maintains isolated shared statistics; stats are collected server-wide and partitioned by `dbid`.

### 18.6. Managed PostgreSQL

On cloud-managed services:

- Verify the extension is on the allowlist.
- Configure `shared_preload_libraries` via parameter groups.
- Plan for an instance/cluster restart if required.
- Grant monitoring roles using the provider's supported mechanism.
- Verify query text visibility and reset permissions.

---

## 19. Common Misconceptions

**1. “pg_stat_statements logs every individual query execution.”** False. It aggregates statistics into normalized query entries.

**2. “Query text is the exact raw SQL from every request.”** False. Representative text usually replaces literals with parameter markers and does not preserve individual invocations.

**3. “Queryid is stable across every major version.”** False. Stability is not guaranteed across major versions, architectures, or catalog changes.

**4. “The query with the highest total_exec_time has the highest latency.”** False. Total time depends on call count too; check mean and max for per-call latency.

**5. “A query with a low mean isn't worth optimizing.”** False. Very high call rates can generate massive cumulative cost.

**6. “shared_blks_read equals bytes read from physical disk.”** False. It counts blocks PostgreSQL loaded into `shared_buffers`; the OS page cache may fulfill reads.

**7. “A 100% hit ratio means the query is optimal.”** False. A query can still scan far too many cached blocks or burn heavy CPU.

**8. “I/O time of 0 means the query did not wait on I/O.”** False when `track_io_timing` is disabled.

**9. “High temp_blks_written always means increase work_mem.”** False. Check plans, rows, sort/hash nodes, concurrency, and memory budgets first.

**10. “track_planning should always be on.”** False. It introduces overhead and defaults to `off`.

**11. “plans always equals calls.”** False. Planning and execution update at different stages; cached plans and execution failures separate the two counts.

**12. “pg_stat_statements shows queries running right now.”** No. Use `pg_stat_activity` to inspect active backends.

**13. “total_exec_time is CPU time.”** False. It is total execution duration, including waits; there is no direct per-statement CPU-time counter.

**14. “A slow query is definitely caused by its execution plan.”** No. It may result from locks, I/O, network, parameter skew, or application behavior.

**15. “Creating the extension once in the postgres database covers all databases.”** No. The view and functions must be installed in each database you wish to query.

**16. “Reloading config is enough to preload the extension.”** No. Changing `shared_preload_libraries` requires a restart.

**17. “Larger pg_stat_statements.max is always better.”** No. Shared memory grows and the external query text file can also balloon.

**18. “High dealloc has no impact on data.”** False. It indicates entries are being evicted, leaving incomplete statistics history.

**19. “Resetting statistics has no downsides.”** False. It destroys baselines; capture snapshots first if comparisons are needed.

**20. “Statistics automatically represent a fixed time window.”** False. They are cumulative counters since reset or entry creation; snapshots and deltas are needed for time windows.

**21. “Nested statements can be summed with parent statements without double-counting.”** False. `track=all` records both outer and inner statements.

**22. “Queryid matches across logical replicas.”** Not guaranteed; logical replication does not guarantee identical catalog metadata.

**23. “pg_stat_statements replaces EXPLAIN.”** False. It identifies query patterns; EXPLAIN reveals execution plans.

**24. “EXPLAIN ANALYZE only estimates without running the query.”** False. It actually executes the statement.

**25. “The query column is always visible to every user.”** False. Other users' query text and `queryid` are protected by superuser/`pg_read_all_stats` privileges.

---

## 20. Hands-On Lab

### 20.1. Check the extension and reset lab statistics

Connect to the lab database:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';

SELECT pg_stat_statements_reset();
```

Reset only in a lab or after saving baseline snapshots.

### 20.2. Create sample data

```sql
CREATE SCHEMA IF NOT EXISTS lab;

DROP TABLE IF EXISTS lab.events;

CREATE TABLE lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO lab.events
    (tenant_id, event_type, event_time, payload)
SELECT
    (g % 100)::integer,
    CASE WHEN g % 5 = 0 THEN 'purchase' ELSE 'view' END,
    now() - (g % 100000) * interval '1 minute',
    repeat(md5(g::text), 4)
FROM generate_series(1, 300000) AS g;

ANALYZE lab.events;
```

### 20.3. Run a scan and aggregate query

```sql
SELECT
    tenant_id,
    event_type,
    count(*) AS event_count
FROM lab.events
WHERE event_time >= now() - interval '30 days'
GROUP BY tenant_id, event_type
ORDER BY event_count DESC;
```

Run the query several times in the lab to generate calls. The goal is to see how entries are recorded rather than chasing specific benchmark numbers.

### 20.4. Run a sort query to observe temp blocks

You can lower `work_mem` within the lab session:

```sql
SET work_mem = '1MB';

SELECT event_id, payload
FROM lab.events
ORDER BY payload;

RESET work_mem;
```

Dataset size and memory settings determine whether the query spills. Check `temp_blks_written` afterward; if it does not spill, enlarge the lab dataset or lower `work_mem` carefully.

### 20.5. Run an update workload to generate WAL

```sql
UPDATE lab.events
SET payload = payload || '-processed'
WHERE tenant_id = 42;
```

Re-run for another tenant ID to increase calls/rows and observe WAL metrics.

### 20.6. Inspect top queries by total execution time

```sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    rows,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    left(query, 300) AS query_sample
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database
              WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 20.7. Inspect top queries by temp blocks

```sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    left(query, 300) AS query_sample
FROM pg_stat_statements
WHERE temp_blks_read > 0
   OR temp_blks_written > 0
ORDER BY temp_blks_read + temp_blks_written DESC
LIMIT 20;
```

### 20.8. Inspect top queries by WAL

```sql
SELECT
    queryid,
    calls,
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_size,
    left(query, 300) AS query_sample
FROM pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### 20.9. Inspect currently running queries

While running a long query in another session:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query_id,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

If your version lacks `query_id`, omit that column.

### 20.10. Compare before and after creating an index

First analyze the plan:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM lab.events
WHERE tenant_id = 42
  AND event_time >= now() - interval '7 days';
```

Create the index in the lab:

```sql
CREATE INDEX events_tenant_time_idx
ON lab.events (tenant_id, event_time);

ANALYZE lab.events;
```

Re-run EXPLAIN ANALYZE with identical predicates and compare actual time, buffers, and plan nodes. Statistics for the query text continue accumulating in the same entry even after the plan changes, so save a snapshot or reset that entry deliberately if you want isolated before/after windows.

### 20.11. Observe planning metrics

To measure planning time:

1. Enable `pg_stat_statements.track_planning` in an allowed configuration.
2. Restart or reload per the parameter context and version.
3. Run the lab workload.
4. Compare `plans`, `total_plan_time`, and `calls`.
5. Evaluate overhead; turn it back off if unneeded.

### 20.12. Clean up the lab

```sql
DROP TABLE IF EXISTS lab.events;
DROP SCHEMA IF EXISTS lab;
```

Do not drop the extension if dashboards or monitoring tools still rely on the view.

---

## 21. Practice Exercises and Answers

### Exercise 1 — Purpose

**Question:** What types of questions does `pg_stat_statements` help answer?

**Answer:** Which query patterns consume the most planning/execution time, blocks, temp files, or WAL, or are executed most frequently.

### Exercise 2 — Installation

**Question:** Where must the module be configured before running `CREATE EXTENSION`?

**Answer:** Add `pg_stat_statements` to `shared_preload_libraries`, enable an appropriate query identifier setting, and restart the server.

### Exercise 3 — Extension database scope

**Question:** Is `CREATE EXTENSION` required in every database where you want to query the view?

**Answer:** Yes. The module preloads at the server level, while the SQL view and functions are installed per database.

### Exercise 4 — Query normalization

**Question:** Can two queries differing only in literal constants be grouped into the same entry?

**Answer:** Yes, when query identifier calculation and normalization apply and the parsed structures match.

### Exercise 5 — Queryid

**Question:** Is `queryid` guaranteed stable across major versions?

**Answer:** Not guaranteed.

### Exercise 6 — Calls

**Question:** What does `calls` measure?

**Answer:** The number of times the statement executed.

### Exercise 7 — Total vs. mean

**Question:** When should you look at `total_exec_time` versus `mean_exec_time`?

**Answer:** Total reveals overall workload cost; mean reveals average per-call latency.

### Exercise 8 — Planning

**Question:** Which parameter must be enabled to record planning metrics?

**Answer:** `pg_stat_statements.track_planning`.

### Exercise 9 — Planning overhead

**Question:** Why should `track_planning` not be enabled unconditionally?

**Answer:** It can introduce contention/overhead, especially when many connections run the same query structure concurrently.

### Exercise 10 — Block reads

**Question:** Does `shared_blks_read` guarantee physical disk reads?

**Answer:** No. The OS page cache can satisfy reads.

### Exercise 11 — I/O timing

**Question:** What must be enabled to collect I/O timings?

**Answer:** `track_io_timing`.

### Exercise 12 — Temp blocks

**Question:** What does high `temp_blks_written` indicate?

**Answer:** Sorts, hashes, or intermediate operations spilling to temporary files.

### Exercise 13 — work_mem

**Question:** Why should you avoid raising global `work_mem` casually?

**Answer:** A single query can run multiple memory-intensive operations and many concurrent sessions can consume huge total memory.

### Exercise 14 — WAL

**Question:** What does `wal_bytes` measure?

**Answer:** Total WAL bytes generated by the statement, not physical bytes written to disk.

### Exercise 15 — pg_stat_statements_info

**Question:** Which PostgreSQL version introduced this view?

**Answer:** PostgreSQL 14.

### Exercise 16 — Dealloc

**Question:** What does rapidly rising `dealloc` suggest?

**Answer:** Entries are being evicted due to hitting `pg_stat_statements.max`; consider increasing `max` and reviewing shared memory.

### Exercise 17 — Reset

**Task:** Reset all statement statistics.

```sql
SELECT pg_stat_statements_reset();
```

### Exercise 18 — Active queries

**Question:** Which view shows queries executing right now?

**Answer:** `pg_stat_activity`.

### Exercise 19 — Locks

**Task:** Find blocker PIDs for active backends.

```sql
SELECT pid, pg_blocking_pids(pid)
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

### Exercise 20 — Explain

**Question:** Does EXPLAIN ANALYZE actually run the query?

**Answer:** Yes. For DML, it modifies data unless rolled back in a transaction; external side effects outside the transaction can still occur.

### Exercise 21 — Auto explain

**Question:** Which extension automatically logs plans for queries exceeding a duration threshold?

**Answer:** `auto_explain`.

### Exercise 22 — Nested statements

**Question:** Can `track=all` record both parent and nested statements?

**Answer:** Yes. Never sum their timings as independent components because they overlap.

### Exercise 23 — Security

**Question:** Which role permits viewing query text and `queryid` for other users?

**Answer:** Superuser or a role with `pg_read_all_stats`.

### Exercise 24 — Version 18

**Question:** Which notable metric additions appeared in PostgreSQL 18?

**Answer:** Parallel worker counts, `stats_since`/`minmax_stats_since`, a WAL buffer metric, and I/O timings split across shared, local, and temp blocks.

### Exercise 25 — Time windows

**Question:** How can you capture 5-minute interval statistics without resetting continuously?

**Answer:** Store periodic snapshots and compute counter deltas between consecutive samples.

---

## 22. Monitoring Implementation Checklist

### Installation and configuration

1. Install the `pg_stat_statements` package matching your PostgreSQL major version.
2. Add `pg_stat_statements` to `shared_preload_libraries`, preserving existing preloaded modules.
3. Verify `compute_query_id = auto/on` or a compatible query ID module.
4. Restart the server after modifying `shared_preload_libraries`.
5. Run `CREATE EXTENSION` in every database where you need to query the view.
6. Verify extension version and view schema.
7. Size `pg_stat_statements.max` based on query diversity and shared memory.
8. Choose `track=top` or `all` based on needs; start with `top`.
9. Enable `track_planning` only when investigating planning overhead.
10. Enable `track_io_timing` if I/O timings are needed and overhead has been measured.

### Query analysis

11. Rank by `total_exec_time` to locate overall workload cost.
12. Rank by `mean_exec_time`/`max_exec_time` to locate high-latency statements.
13. Inspect `calls` to catch overly frequent queries.
14. Inspect `shared_blks_read`/`hit` and I/O timings to locate read pressure.
15. Inspect `temp_blks_read`/`written` and `log_temp_files` to locate spills.
16. Inspect `wal_bytes`/`wal_records`/`wal_fpi` to locate write-heavy statements.
17. Inspect planning and JIT metrics where relevant.
18. Pair with `pg_stat_activity` and `pg_blocking_pids` during live incidents.
19. Use `EXPLAIN (ANALYZE, BUFFERS)` to confirm plans and actual row counts.
20. Consider `auto_explain` for intermittent slow queries that are hard to reproduce.

### Maintenance and governance

21. Monitor `pg_stat_statements_info.dealloc` on PostgreSQL 14+.
22. Store periodic snapshots if time-window analysis is required.
23. Record `stats_reset` and restart/reset timestamps.
24. Never reset before saving required baselines.
25. Restrict `pg_read_all_stats` and reset permissions.
26. Protect query text and monitoring history.
27. Monitor the disk footprint of the query text file.
28. Account for schema differences when supporting multiple major versions.
29. Re-evaluate overhead after enabling additional tracking flags.
30. Document changes, observation windows, and optimization outcomes for future comparison.

---

## 23. Summary

`pg_stat_statements` is PostgreSQL's server-level query-pattern statistics tool. It helps pinpoint which SQL families consume the most time, I/O, temporary blocks, WAL, or planning effort. Query identifiers and normalization collapse similar statements into entries so DBAs can rank workloads using cumulative telemetry.

Key points to remember:

- Preload the module in `shared_preload_libraries`, restart the server, and create the extension in every database you want to query.
- Statistics are collected server-wide and separated by database, user, and `queryid`.
- Query text is a normalized representative sample, not a per-request log or parameter archive.
- `queryid` is not guaranteed stable across major versions or logical replicas.
- `total_exec_time` shows cumulative cost; `mean`/`max` show per-call latency; `calls` shows frequency.
- Shared blocks, temp blocks, I/O timings, WAL, and JIT metrics classify resource consumption.
- `track_planning` carries overhead; enable it only when measuring planning.
- `pg_stat_activity` shows currently executing queries; `pg_stat_statements` shows cumulative statistics.
- EXPLAIN ANALYZE runs the statement for real; use carefully with DML.
- `auto_explain` captures plans automatically for queries exceeding duration thresholds.
- Statistics are cumulative counters; snapshots and deltas are the proper way to track metrics over time.
- `pg_stat_statements_reset` wipes baselines; snapshot first before resetting.
- Other users' query text and `queryid` are protected by superuser/`pg_read_all_stats` privileges.
- PostgreSQL 13–18 introduce schema differences, notably `pg_stat_statements_info` in PG14 and additional metrics in PG18.

**Self-check question:** One query has a `mean_exec_time` of just 3 ms yet huge `calls` and ranks #1 in `total_exec_time`. Another query has a `mean_exec_time` of 2 seconds yet runs only 10 times. If the goal is reducing total database load, which query takes priority? Evaluate total cost, call counts, business criticality, and specific resource usage together rather than ranking by a single number.

### Official PostgreSQL Documentation

- [pg_stat_statements — PostgreSQL 18](https://www.postgresql.org/docs/18/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 17](https://www.postgresql.org/docs/17/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 16](https://www.postgresql.org/docs/16/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 14](https://www.postgresql.org/docs/14/pgstatstatements.html).
- [pg_stat_statements — PostgreSQL 13](https://www.postgresql.org/docs/13/pgstatstatements.html).
- [Run-time Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html).
- [Monitoring Statistics and pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
- [auto_explain](https://www.postgresql.org/docs/current/auto-explain.html).
- [Query Planning Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html).
- [Predefined Roles — pg_read_all_stats](https://www.postgresql.org/docs/current/predefined-roles.html).
