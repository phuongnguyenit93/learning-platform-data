# effective_cache_size and PostgreSQL Planner Assumptions

`effective_cache_size` is a planner configuration parameter used to estimate how much data cache may be available for a query. PostgreSQL uses this assumption when estimating data access costs, especially when comparing an index scan against a sequential scan.

The most important point: **`effective_cache_size` does not allocate memory, does not create a cache, and does not force PostgreSQL to keep data in RAM**. It only changes the planner's assumption about the likelihood that data is already in cache.

If set too low, the planner may estimate index access as more expensive than reality and favor sequential scans in some cases. If set too high, the planner may estimate index access as cheaper than actual cache capacity allows and pick plans with excessive random reads. Therefore, set the value based on RAM, `shared_buffers`, OS page cache, concurrent workload, and evidence from query plans.

This lesson **"effective_cache_size and Planner Assumptions"**, part of the **Resource Tuning** chapter in the **Database Engine Relational PostgreSQL** module, covers:

- The role of `effective_cache_size` in cost estimation.
- Differences between planner cache assumptions, `shared_buffers`, and OS page cache.
- How cache assumptions influence index scans and sequential scans.
- Relationships with `random_page_cost`, `seq_page_cost`, `work_mem`, and related settings.
- How to estimate usable cache for PostgreSQL.
- How to verify using `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)`, and statistics.
- A workflow for tuning, measuring, and avoiding tuning based on a single query.

> **Way to remember:** `shared_buffers` is memory PostgreSQL actually allocates; OS page cache is cache managed by the operating system; `effective_cache_size` is an assumption the planner uses to compute costs. The three concepts are related, yet none can substitute for the others.

---

## 1. What Does the Planner Need to Estimate?

Before executing a query, PostgreSQL parses the SQL and examines the schema, statistics, and data access methods. The query planner generates candidate plans and selects the one with the lowest estimated cost under the cost model.

Example:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 420;
~~~

The planner may consider:

- Sequential scan of the entire table.
- Index scan on the `customer_id` index.
- Bitmap index scan combined with a bitmap heap scan.
- Index-only scan if the index contains all required columns and the visibility map allows it.

To choose, the planner must estimate matching rows, pages to access, CPU cost, and the probability that pages are already cached.

`effective_cache_size` feeds into the cache assumption when estimating index access cost.

## 2. What Is effective_cache_size?

`effective_cache_size` sets the **assumption about the disk cache size available to a query** from the planner's perspective.

This parameter helps the planner estimate the probability that required pages are already in cache and thus estimate the cost of reading data through an index.

- Higher values tend to make index scans look more attractive.
- Lower values tend to make sequential scans look more attractive.
- The effect is on estimated costs and plan choice.
- The value does not change how much RAM PostgreSQL actually allocates.

Check the current value:

~~~sql
SHOW effective_cache_size;
~~~

You can also inspect metadata:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'effective_cache_size';
~~~

`setting` is the internal value in the unit shown in the `unit` column. Use `SHOW` or `pg_settings` to see the active configuration instead of guessing from configuration files.

## 3. It Is a Planner Assumption, Not Real Cache

Suppose a configuration has:

~~~text
shared_buffers = 8GB
effective_cache_size = 32GB
~~~

This does not mean PostgreSQL has allocated 32GB of shared memory.

It means the planner is instructed to compute costs assuming roughly 32GB of usable cache, spanning both shared buffers and the portion of OS cache that can serve PostgreSQL data.

If the system actually has little available memory, a high setting can make the planner overly optimistic. Conversely, if a large amount of cache is available but the setting is too low, the planner may evaluate index access too pessimistically.

## 4. Distinguishing Three Memory/Cache Layers

| Component | Managed by | Role |
|---|---|---|
| `shared_buffers` | PostgreSQL | Actual shared buffer pool for database pages |
| OS page cache | Operating system | Caches filesystem data; can serve file reads |
| `effective_cache_size` | Planner configuration | Overall assumption about cache available during cost calculation |

PostgreSQL normally uses both shared buffers and the OS page cache when reading data. A page can exist in multiple cache layers; therefore, do not mechanically sum numbers and treat them as completely independent capacity.

### 4.1. shared_buffers

`shared_buffers` is the shared memory region PostgreSQL allocates to cache data pages.

~~~sql
SHOW shared_buffers;
~~~

It directly affects PostgreSQL's memory allocation and usually requires a restart to change.

### 4.2. OS Page Cache

The kernel can keep database file contents in the page cache. PostgreSQL requests a file read; the OS can serve it from RAM rather than the storage device.

Actual cache size fluctuates based on:

- Free memory.
- PostgreSQL workload.
- Other processes on the host.
- File caches of other applications.
- Memory pressure and kernel reclaim.
- Container/VM memory limits.

There is no single fixed OS cache figure across the entire lifetime of a server.

### 4.3. effective_cache_size

`effective_cache_size` does not hold pages and creates no reservation. It is an input to the planner cost model.

Changing the setting does not warm up cache or free RAM. Nor does it prevent the OS from reclaiming page cache.

## 5. Why Does the Planner Need a Cache Assumption?

An index scan typically accesses index pages and then accesses heap pages corresponding to the matching rows.

If the pages are already in cache, access cost is lower than reading from storage.

If the cache is small or the working set exceeds the cache, many random reads may have to go to storage and become more expensive.

The planner does not know exactly which pages will be in cache at query execution time. `effective_cache_size` provides an assumption for the cost model to estimate the page fetches likely required.

## 6. effective_cache_size and Index Scans

For a selective query:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

If only a small percentage of rows match and an appropriate index exists, an index scan can avoid reading the entire heap.

When the planner assumes a larger cache, reading index/heap pages can be costed as cheaper. Thus an index scan may become the chosen plan.

This does not guarantee an index scan is always better. If the query needs many rows or matching heap pages are widely scattered, a sequential scan may still be cheaper.

## 7. effective_cache_size and Sequential Scans

A sequential scan reads a relation's pages in order. For queries needing most of a table, sequential reading is usually more efficient than traversing an index and fetching scattered heap pages.

A high `effective_cache_size` value does not force the planner to use an index scan. The planner still compares the total cost of candidate plans.

Example:

~~~sql
SELECT *
FROM orders
WHERE created_at >= DATE '2024-01-01';
~~~

If most of the table satisfies the condition, a sequential scan may be appropriate even with a large cache.

## 8. Index Scan, Bitmap Scan, and Index-Only Scan

| Plan type | Access method | Factors to consider |
|---|---|---|
| Sequential scan | Reads heap sequentially | Fraction of rows needed, table size, sequential I/O |
| Index scan | Uses index then fetches heap rows | Selectivity, heap locality, cache, and random I/O |
| Bitmap heap scan | Collects tuple locations then reads heap pages in bitmap order | Number of heap pages to visit, locality |
| Index-only scan | Reads data from index if columns and visibility allow | Index coverage, visibility map, heap fetches |

`effective_cache_size` participates in cost estimation, but does not replace factors like selectivity, correlation, index definition, or the visibility map.

## 9. Cache Assumption and random_page_cost

`random_page_cost` is a cost parameter describing the relative cost of a random page access compared to the standard cost unit.

~~~sql
SHOW random_page_cost;
SHOW seq_page_cost;
~~~

A lower `random_page_cost` tends to make index access more attractive; a higher value makes random reads appear more expensive.

`effective_cache_size` and `random_page_cost` are related yet describe two different assumptions:

- `effective_cache_size`: how much cache may be available.
- `random_page_cost`: the relative cost of a random page access.

Do not lower `random_page_cost` solely to force index scans, and do not raise `effective_cache_size` just to fix one slow query. Verify both against real workloads.

## 10. Cost Units Are Not Milliseconds

The planner displays estimated costs in relative units:

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 420;
~~~

Example:

~~~text
Index Scan ... (cost=0.42..18.50 rows=12 width=...)
~~~

Cost numbers are not milliseconds and cannot be compared directly to wall-clock execution time.

The planner compares candidate plans within the same cost model. Scaling cost parameters can change plan selection, but does not by itself make CPU or storage faster.

## 11. effective_cache_size Is Not work_mem

The two settings serve different purposes:

| Setting | Purpose | Allocates memory? |
|---|---|---|
| `effective_cache_size` | Planner cache assumption | No |
| `shared_buffers` | Page cache inside PostgreSQL | Yes |
| `work_mem` | Workspace for sort/hash and certain operations | May allocate during operation |
| `maintenance_work_mem` | Workspace for maintenance operations | Yes |
| `temp_buffers` | Buffer for session temporary tables | Yes |

Increasing `effective_cache_size` will not keep a large sort from spilling to temporary files. If a query spills due to sort/hash, examine `work_mem` and the query plan.

## 12. effective_cache_size Is Not shared_buffers

Common misconceptions:

- Setting `effective_cache_size = 32GB` does not allocate 32GB of RAM to PostgreSQL.
- Setting `effective_cache_size` high does not increase the number of pages in shared buffers.
- Setting `effective_cache_size` low does not restrict actual cache usage.
- Changing the setting does not flush existing cache.
- The setting is not a per-query memory quota.

`shared_buffers` is a memory allocation; `effective_cache_size` is a planner assumption.

## 13. Estimating an Appropriate Value

No single value fits every server. When estimating, consider:

1. Total RAM actually available to the host/VM/container.
2. `shared_buffers`.
3. The portion of OS page cache that can serve PostgreSQL.
4. Memory needed for backend processes and concurrent workloads.
5. Other services running on the same host.
6. Database working set.
7. Concurrent queries accessing different datasets.
8. Memory limits and cgroup/container constraints.
9. Cache behavior observed in real workloads.

PostgreSQL documentation recommends considering both shared buffers and the portion of kernel disk cache usable for database files, while accounting for concurrent queries sharing the cache.

### 13.1. Do Not Rely on a Fixed RAM Percentage

Rules of thumb like "effective_cache_size is always 75% of RAM" can only be a starting point in certain environments, not a universal rule.

For example, two hosts both have 64GB RAM, yet:

- Host A runs only PostgreSQL.
- Host B also runs application servers, agents, and batch jobs.
- Host C is constrained by a container memory limit.
- Host D has a working set many times larger than RAM.

The appropriate cache assumption for each host can differ.

## 14. Cache Budgeting Example

Suppose a host has 64GB RAM. PostgreSQL uses 16GB for `shared_buffers`. The OS also needs memory for the kernel, backend processes, connection overhead, and other applications.

You should not automatically set `effective_cache_size` to 64GB. Estimate the cache portion that can actually serve the database workload, avoid double-counting pages, and account for concurrent queries.

A candidate value can be chosen after inspecting memory pressure and cache behavior. This is an assumption for the planner to use, not a guarantee that the OS will retain that exact amount.

### 14.1. Concurrent Workloads

If one query works on table A and another works on table B, both need cache. The planner setting should reflect shared cache availability across queries expected to run concurrently.

Do not model cache as if every query owns all RAM exclusively.

## 15. Working Set

**Working set** is the subset of data that a workload frequently accesses over a meaningful time window.

Examples:

- OLTP: recent customer/order rows and frequently used indexes.
- Reporting: partitions for one month/quarter.
- Analytics: multiple large tables, wide scans.
- Mixed workload: hot rows for transactions alongside data ranges for reports.

If the working set fits within available cache, index access can be much cheaper than when the working set exceeds cache.

`effective_cache_size` should reflect a reasonable assumption about the cache the workload can utilize, not merely database size on disk.

## 16. Cache Hit Ratio Does Not Directly Yield effective_cache_size

You can inspect database counters:

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

A high hit ratio indicates many block requests are served from shared buffers. It does not reveal the full OS page cache or how much cache is available to a single query.

A low hit ratio also does not prove `effective_cache_size` is misconfigured. Heavy sequential scan workloads can read many blocks once.

## 17. Using pg_statio to Observe per Relation

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 30;
~~~

This view helps identify relations with high block reads/hits. It does not directly tell you the exact cache size the planner should assume.

Read it alongside `pg_stat_user_tables`, `pg_stat_user_indexes`, query plans, and OS metrics.

## 18. pg_buffercache

The `pg_buffercache` extension can inspect pages currently resident in PostgreSQL's shared buffer cache.

After installing the extension in the appropriate database:

~~~sql
CREATE EXTENSION pg_buffercache;
~~~

Overview example:

~~~sql
SELECT
    count(*) AS buffer_count,
    count(*) FILTER (WHERE relfilenode IS NOT NULL) AS relation_buffers
FROM pg_buffercache;
~~~

You can group by database/relation to inspect buffer distribution. Check schema and privileges for your version/extension.

`pg_buffercache` observes only PostgreSQL shared buffers. It does not display the entire OS page cache and does not directly compute a value for `effective_cache_size`.

## 19. OS Memory and Page Cache

Monitor memory at the operating system level:

- Available/free RAM.
- Page cache.
- Swap activity.
- Major/minor page faults.
- Memory pressure.
- Process resident memory.
- Container memory limit/usage.
- Storage read latency and throughput.

On Linux, refer to `free`, `vmstat`, `iostat`, and node exporter metrics. On Windows, use Performance Monitor or equivalent monitoring tools.

Do not take a single point-in-time memory snapshot and treat it as fixed cache capacity. Observe across peak workloads and batch windows.

## 20. EXPLAIN to Inspect Planner Choices

Use `EXPLAIN` to view the plan without executing the query:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

Observe:

- Node type: Seq Scan, Index Scan, Bitmap Heap Scan, Index Only Scan.
- Estimated rows.
- Estimated cost.
- Filter and Index Cond.
- Join strategy for multi-table queries.

`effective_cache_size` can alter the estimated cost of alternatives and lead to a different plan.

## 21. EXPLAIN ANALYZE, BUFFERS

To inspect actual execution in a controlled environment:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

Useful details:

- Estimated rows vs. actual rows.
- Planning time and execution time.
- Shared hit/read blocks.
- Local/temp blocks if any.
- Heap fetches for index-only scans.
- Actual loops and rows per loop.

`BUFFERS` shows buffer activity inside PostgreSQL. `shared read` means the block had to be read into shared buffers; the OS page cache may still have served that request.

`EXPLAIN ANALYZE` actually runs the query. Be careful with DML, functions with side effects, and heavy queries. Test on staging or safe data first.

## 22. Comparing Estimated Rows vs. Actual Rows

The planner relies on statistics to estimate row counts. If estimated rows differ widely from actual rows, causes may include:

- Stale statistics.
- Data distribution skew.
- Correlation between columns.
- Complex predicates.
- Expressions lacking appropriate statistics.
- Parameter-sensitive workloads.

Before blaming `effective_cache_size`, inspect estimates and run ANALYZE when appropriate.

A good cache assumption cannot fix a severely wrong cardinality estimate.

## 23. Statistics and ANALYZE

The query planner uses column statistics to estimate selectivity.

~~~sql
ANALYZE public.orders;
~~~

You can inspect some statistics in the catalog:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

If a table changes substantially and statistics are not updated, the planner can pick a poor plan even when `effective_cache_size` is reasonable.

## 24. Correlation and Heap Locality

An index scan can be fast when matching rows sit close together on the heap or when index order correlates with physical row order.

The statistics column `correlation` helps the planner estimate locality of index accesses.

If index entries point to scattered heap pages, an index scan can cause many random accesses. If data has good locality, the cost can be lower.

`effective_cache_size` is only one factor in cost estimation; it does not replace correlation statistics.

## 25. Selectivity and Rows to Read

Index scans are usually more attractive when the predicate is highly selective, meaning only a small fraction of rows match.

Example:

~~~sql
SELECT *
FROM orders
WHERE order_id = 12345;
~~~

If `order_id` is the primary key, the query typically needs only one row.

Conversely:

~~~sql
SELECT *
FROM orders
WHERE status = 'active';
~~~

If 90% of rows have active status, a sequential scan can be more efficient than using an index and fetching almost every heap row.

The fraction of rows to read often matters more than just looking at cache settings.

## 26. Cache Size and Index-Only Scans

An index-only scan can avoid heap access if:

- The index contains all columns the query needs.
- The visibility map lets PostgreSQL confirm the corresponding pages are all-visible.
- The plan actually chooses Index Only Scan.

Example:

~~~sql
CREATE INDEX orders_customer_created_idx
ON public.orders (customer_id)
INCLUDE (created_at);
~~~

Query:

~~~sql
SELECT customer_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Even with a large cache, index-only scans still depend on the visibility map and index coverage. If heap fetches are high, the benefit may diminish.

## 27. Bitmap Heap Scans

A bitmap scan collects tuple locations from an index into a bitmap, then accesses heap pages in a more sequential order.

It is typically considered when a query is moderately selective: many rows needed, yet still far fewer than the full table.

The planner chooses among index scan, bitmap scan, and sequential scan based on selectivity, page fetch estimates, cost parameters, and cache assumptions.

Do not try to force a single plan type for every query on the same table.

## 28. effective_cache_size and random_page_cost Together

Both settings can jointly influence index access selection.

| Change | Cost model tendency |
|---|---|
| Increase `effective_cache_size` | Assumes more cache; index access can appear cheaper |
| Decrease `effective_cache_size` | Assumes less cache; index access can appear costlier |
| Decrease `random_page_cost` | Random reads appear cheaper |
| Increase `random_page_cost` | Random reads appear costlier |

These are tendencies, not guarantees that a plan will change. Other factors can dominate the result.

Adjust one variable at a time to understand its impact, then test with a representative workload.

## 29. seq_page_cost

`seq_page_cost` is the relative cost of a sequential page fetch. Check current value:

~~~sql
SHOW seq_page_cost;
~~~

Do not change it simply because a sequential scan appears. A sequential scan is often the optimal plan when most of a relation must be read.

Cost parameters are relative units. Tuning them should be based on storage characteristics and workload, not an arbitrary absolute number.

## 30. effective_io_concurrency

`effective_io_concurrency` controls the level of I/O concurrency PostgreSQL can use in certain bitmap heap scans and supported paths.

~~~sql
SHOW effective_io_concurrency;
~~~

This setting differs from `effective_cache_size`:

- One describes cache availability as a planner assumption.
- The other relates to execution concurrency for certain I/O operations.

Availability and impact depend on OS, storage, and PostgreSQL version.

## 31. Tuning by Workload Type

| Workload | Characteristics | What to observe |
|---|---|---|
| OLTP | Many small queries, hot row access | Working set, index access, shared/OS cache |
| Reporting | Large scans and aggregates | Sequential I/O, temp spills, query plans |
| Data warehouse | Large working set, parallel scans | Memory pressure, storage throughput, cache churn |
| Mixed workload | OLTP alongside reporting | Cache contention, concurrency, query latency |
| Batch | Periodic writes/reads | Peak memory, warm/cold cache, I/O bursts |

A cache assumption suitable for OLTP is not necessarily optimal for analytics running concurrently on the same host.

## 32. Mistuning: Setting Too Low

When `effective_cache_size` is lower than actual cache capacity, the planner can estimate index access as overly expensive.

Possible symptoms:

- Queries pick sequential scans even when predicates are very selective.
- Estimated index costs are high.
- Appropriate indexes exist but are skipped in some queries.
- Plans change when testing higher values.

However, also rule out stale statistics, missing indexes, non-sargable predicates, data type casts, and queries needing most of the table.

## 33. Mistuning: Setting Too High

When the setting exceeds what cache can actually serve, the planner can be overly optimistic about index access.

Possible symptoms:

- Index scans are chosen, yet runtime shows many block reads.
- Random I/O rises when workloads run concurrently.
- Queries perform worse than sequential/bitmap alternatives in tests.
- OS memory pressure or storage latency increases.

Do not conclude from a single query. Compare across multiple runs, concurrent workloads, and production-like cache conditions.

## 34. Do Not Use effective_cache_size to Fix Every Slow Query

Slow queries can be caused by:

- Lock waits.
- CPU saturation.
- Network latency.
- Bad join order.
- Wrong cardinality estimates.
- Missing or unsuitable indexes.
- Temp files from sort/hash spills.
- Storage latency.
- Connection pool saturation.
- Overly long transactions.

`effective_cache_size` affects only one part of the planner cost model. Identify the bottleneck before changing it.

## 35. Inspecting Current Planner Configuration

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'effective_cache_size',
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'random_page_cost',
    'seq_page_cost',
    'effective_io_concurrency'
)
ORDER BY name;
~~~

This query shows current values, units, and configuration sources.

`source` can indicate whether the setting comes from default, configuration file, command line, database/role setting, or session override depending on the case.

## 36. Testing Settings per Session

If the setting allows changes at the session context, you can test in a dedicated session:

~~~sql
SET effective_cache_size = '24GB';

EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Then try another value:

~~~sql
SET effective_cache_size = '40GB';

EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Compare estimated costs and plan nodes. Use `RESET effective_cache_size` to return to the session default or close the test session.

This is a planner experiment, not a runtime benchmark. Evaluating performance requires running a controlled workload under comparable conditions.

## 37. Persistent Configuration Changes

Can be configured in `postgresql.conf` or via your management tooling:

~~~text
effective_cache_size = 32GB
~~~

After changing, verify the effective setting:

~~~sql
SHOW effective_cache_size;
~~~

The setting's context determines whether a restart, reload, or session-only change applies. Check `pg_settings.context` rather than assuming every memory parameter requires a restart.

Some environments manage configuration via an operator/configuration management tool; direct file edits may be overwritten by automation.

## 38. Measuring Before and After Tuning

A test run should record:

- Old and new setting values.
- PostgreSQL major version.
- RAM/VM/container limits.
- `shared_buffers`.
- Workload and sampling window.
- Query plans.
- Estimated/actual rows.
- Execution time.
- Shared hit/read blocks.
- Temp blocks.
- CPU, memory pressure, and storage latency.
- Concurrent query count.

Do not compare two runs if one had a warm cache and the other a cold cache without documenting that condition.

## 39. Keeping Benchmark Conditions Consistent

When comparing plans/runtimes:

1. Use the same dataset and schema.
2. Ensure statistics do not change between runs.
3. Use the same parameter values.
4. Record concurrent workload.
5. Compare warm/cold cache deliberately.
6. Run enough iterations to avoid concluding from an outlier.
7. Measure both latency and resource consumption.
8. Inspect query plans after each change.

Do not clear caches on production just to run a cold-cache benchmark.

## 40. Using pg_stat_statements to Select Representative Queries

If `pg_stat_statements` is installed, you can find queries with high total execution time:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Column names may differ on older PostgreSQL versions. Check extension version/schema before running the query.

Select a representative group of queries rather than tuning for one rare or unimportant query.

## 41. Combining EXPLAIN with Statistics

An investigation workflow:

1. Use `pg_stat_statements` to find time-consuming queries.
2. Obtain the SQL and representative parameter values.
3. Run `EXPLAIN` to inspect the plan.
4. Run `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment.
5. Compare estimated rows vs. actual rows.
6. Inspect shared hit/read and temp blocks.
7. Check index definitions and table statistics.
8. Test changing `effective_cache_size` in a session.
9. Compare plans and runtimes under equivalent conditions.
10. Deploy only when the overall workload benefits.

## 42. When Should You Run ANALYZE?

If table data distribution changes significantly, run ANALYZE so the planner has fresh statistics:

~~~sql
ANALYZE public.orders;
~~~

Especially after bulk loads, partition attaches/loads, or major data changes, planner estimates may need updating.

Do not try to compensate for bad statistics by raising the cache assumption. Both factors address different parts of cost estimation.

## 43. Parameterized Queries and Generic Plans

Prepared statements can use a custom plan or a generic plan depending on PostgreSQL's decision.

A generic plan does not know the exact parameter value on each execution like a custom plan. If selectivity varies strongly by parameter, the plan may not be optimal for all values.

`effective_cache_size` does not solve parameter sensitivity by itself. When plans differ between literal and prepared execution, check plan caching, parameter distribution, and `EXPLAIN EXECUTE`.

## 44. Partitioning and Cache Assumptions

For partitioned tables, partition pruning can significantly reduce the number of relations/pages read.

Before changing `effective_cache_size`, check:

- Is partition pruning working?
- Does the query predicate allow pruning?
- Are partition statistics up to date?
- Is the plan scanning too many partitions?
- What are partition sizes and the working set?

If the planner fails to prune partitions, the issue may lie in the query predicate or plan-time/runtime pruning rather than cache size.

## 45. Index Design Still Matters

A large cache assumption cannot make an unsuitable index good.

Review:

- Leading columns of a multicolumn index.
- Predicate operators.
- Data types and implicit casts.
- Partial index predicates.
- `INCLUDE` columns for index-only scans.
- Selectivity and correlation.
- Index bloat and maintenance cost.

If a query needs 70% of a table, an index scan can be costlier than a sequential scan even with a large cache.

## 46. Cache Pressure from Concurrent Queries

Planner assumptions must account for multiple queries sharing the cache.

For instance, an OLTP query repeatedly accesses hot index pages while a report scans a large table. The report can cause cache churn and evict hot pages from cache.

If you set the cache assumption purely from RAM capacity while ignoring concurrency, the planner may become overly optimistic.

Monitor:

- Query concurrency.
- Buffer hit/read rates.
- OS memory pressure.
- Storage latency.
- Workload mix.
- Cache warm-up after batch windows.

## 47. Memory Limits in Containers/VMs

In container environments:

- The host may have lots of RAM while the container has a lower limit.
- PostgreSQL sees/receives memory per cgroup limits.
- OS page cache may be constrained by cgroup memory limits.
- The OOM killer can terminate processes when limits are exceeded.

Do not use total host RAM as the cache assumption if PostgreSQL only has a fraction of that memory.

Measure the memory limit and usage in the actual namespace/container, then determine the cache portion that can realistically serve the database.

## 48. effective_cache_size and Parallel Queries

Parallel workers can help queries read data faster using multiple CPU/I/O paths, while also increasing resource contention.

`effective_cache_size` does not allocate memory per worker and does not control the number of parallel workers.

When evaluating parallel plans, inspect:

- `max_parallel_workers_per_gather`.
- `max_parallel_workers`.
- `max_worker_processes`.
- CPU saturation.
- I/O throughput.
- Cache contention.
- Worker availability.

Do not increase the cache assumption as a substitute for tuning parallelism.

## 49. Questions to Answer Before Tuning

- Is PostgreSQL actually choosing an inappropriate plan?
- Which queries are affected?
- Are estimated rows close to actual rows?
- Do indexes match the predicates?
- What is the current cache level across shared buffers and OS page cache?
- What is the concurrent workload?
- How are `random_page_cost` and `seq_page_cost` configured?
- Is storage local SSD, network storage, or cloud volumes?
- Is memory experiencing pressure/swap/OOM?
- Does the change improve the overall workload?

If there is no evidence of a plan/cost mismatch, leave the setting unchanged and gather more data.

## 50. Troubleshooting: Planner Chooses Sequential Scan

Investigate in order:

1. Inspect `EXPLAIN` and estimated rows.
2. Check whether the query needs most of the table.
3. Verify an appropriate index exists and the predicate can use it.
4. Run ANALYZE if statistics are stale.
5. Check `random_page_cost` and `seq_page_cost`.
6. Estimate available cache.
7. Test `effective_cache_size` in a session.
8. Compare candidate plans and runtime in a safe environment.

Do not use `enable_seqscan = off` as a default production solution. Planner switches are only useful for diagnosing plan alternatives.

## 51. Troubleshooting: Planner Chooses Index Scan, Yet Query Is Slow

Check:

- Are actual rows larger than estimated?
- Are heap fetches high?
- Are shared read blocks high?
- Is the index scan doing excessive random I/O?
- Does the working set exceed cache?
- Is the cache assumption overly optimistic?
- Could the query use a bitmap or sequential scan more efficiently?
- What are storage latency and concurrency?

If testing changes, compare plan alternatives in staging and change one cost setting at a time.

## 52. Troubleshooting: Increasing effective_cache_size Does Not Change the Plan

This can easily happen.

Causes:

- Cost difference still strongly favors the same plan.
- Query selectivity is too high or too low for the setting to flip the decision.
- Cardinality estimates dominate over the cache assumption.
- The planner has no suitable index.
- The query uses another plan node insensitive to this setting.
- The new value is not yet effective in the session.
- The query is running with a prepared/generic plan.

Verify using `SHOW effective_cache_size`, `pg_settings`, and `EXPLAIN`.

## 53. Common Mistakes

### 53.1. effective_cache_size Allocates RAM

False. It is a planner assumption.

### 53.2. effective_cache_size Must Equal shared_buffers

False. It can account for the portion of OS cache usable for the database.

### 53.3. effective_cache_size Equals Total RAM

Not necessarily. You must account for OS memory, backend processes, other services, container limits, and cache overlap.

### 53.4. Higher Values Are Always Better

False. Too high can make the planner overly optimistic about index access.

### 53.5. A Low Hit Ratio Means the Setting Is Too Low

Insufficient evidence. Hit ratio observes only part of buffer behavior and depends on the workload.

### 53.6. A Sequential Scan Always Means a Missing Index

False. A sequential scan can be cheapest when reading most of a table.

### 53.7. Changing effective_cache_size Alone Makes Queries Faster

False. It can alter the plan, but it does not change hardware or actual cache.

### 53.8. work_mem and effective_cache_size Are the Same

False. One describes a cache assumption; the other controls workspace memory for operations.

### 53.9. EXPLAIN Costs Are Milliseconds

False. Cost units are relative units in the planner.

### 53.10. Tuning One Query Guarantees Every Query Improves

False. A planner setting affects a broader workload; you must check the query mix.

## 54. Lab: Inspecting Cache and Cost Configuration

In a PostgreSQL lab:

~~~sql
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW work_mem;
~~~

Inspect metadata:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'random_page_cost',
    'seq_page_cost',
    'work_mem'
)
ORDER BY name;
~~~

Record values before testing.

## 55. Lab: Comparing Plans with Two Cache Assumptions

Create a sufficiently large dataset:

~~~sql
CREATE TABLE cache_lab_orders AS
SELECT
    g AS order_id,
    (g % 100000)::integer AS customer_id,
    (g % 10)::integer AS status_id,
    now() - (g % 365) * interval '1 day' AS created_at
FROM generate_series(1, 2000000) AS g;

ALTER TABLE cache_lab_orders
ADD PRIMARY KEY (order_id);

CREATE INDEX cache_lab_customer_idx
ON cache_lab_orders (customer_id);

ANALYZE cache_lab_orders;
~~~

Test a selective query:

~~~sql
SET effective_cache_size = '2GB';

EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Test another assumption:

~~~sql
SET effective_cache_size = '24GB';

EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Record the plan and estimated cost. Plans may stay identical if the cost difference is not enough to change the choice.

After the lab:

~~~sql
RESET effective_cache_size;
~~~

## 56. Lab: Comparing with a Low-Selectivity Predicate

Use the same table:

~~~sql
EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE status_id = 1;
~~~

This condition can match a significant portion of rows. Compare it with the query on `customer_id`.

The goal is to observe how selectivity affects the plan, not to force the planner to choose an index scan.

## 57. Lab: EXPLAIN ANALYZE and BUFFERS

In a safe lab:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Record estimated rows, actual rows, execution time, shared hit/read blocks, and plan nodes. If there is an index-only scan, also record heap fetches.

Re-run under similar cache conditions and compare. Do not flush OS cache or shared buffers on production to reproduce a cold cache.

## 58. Lab: Tracking Cache Counters Over Time

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

Take two samples separated by an interval, compute the delta for `blks_read` and `blks_hit`, and record the workload running during that window.

Isolate lab query activity from background workloads if you want easier-to-interpret results.

## 59. Tuning Checklist

**Before changing**

1. Identify the query/workload needing improvement.
2. Record the PostgreSQL version and current configuration.
3. Measure RAM and memory limits.
4. Check `shared_buffers` and OS page cache.
5. Inspect query plans and row estimates.
6. Check statistics and index definitions.
7. Record workload concurrency.

**During testing**

8. Change the setting in a session if applicable.
9. Compare estimated costs.
10. Run runtime benchmarks under safe conditions.
11. Record buffers, latency, CPU, and storage I/O.
12. Check whether other parts of the query mix are affected.

**When deploying**

13. Choose a value based on evidence.
14. Update via configuration management.
15. Confirm the setting is active.
16. Monitor for plan regressions and latency.
17. Have a rollback value/runbook.
18. Re-evaluate when RAM, workload, or topology changes.

## 60. Practice Exercises

### Exercise 1 — effective_cache_size

What does this parameter control?

**Hint:** planner assumption about the disk cache likely available to a query.

### Exercise 2 — Memory Allocation

Does setting `effective_cache_size = 32GB` allocate 32GB of RAM?

**Hint:** no.

### Exercise 3 — shared_buffers

How does this setting differ from `effective_cache_size`?

**Hint:** `shared_buffers` is cache memory actually allocated by PostgreSQL.

### Exercise 4 — OS Page Cache

How does the operating system help cache database files?

**Hint:** the page cache can serve file reads from RAM.

### Exercise 5 — Cache Overlap

Why should you not mechanically sum `shared_buffers` and OS cache?

**Hint:** pages can be cached in multiple layers and shared by many queries.

### Exercise 6 — Planner Cost

What does the planner use `effective_cache_size` for?

**Hint:** estimating data access cost, especially index access.

### Exercise 7 — High Value

Which plan does a higher value generally make more attractive?

**Hint:** index scans can be costed as cheaper.

### Exercise 8 — Low Value

Which plan can a low value push the planner toward?

**Hint:** sequential scans in certain cases.

### Exercise 9 — Sequential Scan

Is a sequential scan always bad?

**Hint:** no; reading most of a table is often appropriate.

### Exercise 10 — Index Scan

When is an index scan usually beneficial?

**Hint:** selective predicate needing few heap rows.

### Exercise 11 — Bitmap Scan

What trade-off does a bitmap heap scan address?

**Hint:** collects tuple locations to access heap pages more efficiently.

### Exercise 12 — Index-Only Scan

What conditions allow an index-only scan to avoid heap fetches?

**Hint:** the index contains all required columns and the visibility map permits it.

### Exercise 13 — random_page_cost

What does this setting describe?

**Hint:** the relative cost of a random page access.

### Exercise 14 — seq_page_cost

What does this setting describe?

**Hint:** the relative cost of a sequential page access.

### Exercise 15 — Cost Units

Are estimated costs in milliseconds?

**Hint:** no, they are relative units.

### Exercise 16 — work_mem

What is `work_mem` used for?

**Hint:** workspace for sort/hash operations and certain executor operations.

### Exercise 17 — maintenance_work_mem

Which group of activities does this setting typically serve?

**Hint:** maintenance such as VACUUM or index creation per applicable semantics.

### Exercise 18 — Working Set

What is a working set?

**Hint:** the subset of data a workload frequently accesses.

### Exercise 19 — Concurrency

Why must query concurrency be factored in when estimating cache?

**Hint:** queries share the available cache.

### Exercise 20 — Cache Hit Ratio

Does the hit ratio directly report OS page cache?

**Hint:** no; it primarily reflects shared buffer hits/reads.

### Exercise 21 — pg_buffercache

Which cache does this extension observe?

**Hint:** PostgreSQL shared buffers.

### Exercise 22 — EXPLAIN

Does `EXPLAIN` without `ANALYZE` execute the query?

**Hint:** no; it displays planned execution.

### Exercise 23 — EXPLAIN ANALYZE

Why be careful with DML?

**Hint:** it actually executes the statement and can cause side effects.

### Exercise 24 — BUFFERS

Is `shared read` in EXPLAIN necessarily a physical disk read?

**Hint:** no; the OS page cache may serve it.

### Exercise 25 — Cardinality Estimate

If estimated rows are far off from actual rows, what should you check?

**Hint:** ANALYZE, data distribution, and planner statistics.

### Exercise 26 — Correlation

What does correlation affect?

**Hint:** locality of heap accesses via an index.

### Exercise 27 — Selectivity

Is a query needing most rows usually suited for an index scan?

**Hint:** not necessarily; a sequential scan may be cheaper.

### Exercise 28 — effective_io_concurrency

How does this setting differ from `effective_cache_size`?

**Hint:** controls I/O concurrency for certain paths, not a cache assumption.

### Exercise 29 — Container Memory

Why not use total host RAM as the cache assumption inside a container?

**Hint:** the container may have its own memory limit.

### Exercise 30 — Parallel Query

Does `effective_cache_size` allocate memory for parallel workers?

**Hint:** no.

### Exercise 31 — Setting Metadata

Which view shows the context/source of a GUC?

**Hint:** `pg_settings`.

### Exercise 32 — Session Test

Can you test a cache assumption per session when the setting permits?

**Hint:** use `SET` and compare `EXPLAIN`.

### Exercise 33 — Statistics Freshness

Why run ANALYZE before tuning the cache assumption?

**Hint:** stale estimates can cause bad plans for other reasons.

### Exercise 34 — pg_stat_statements

Which queries does this extension help choose for benchmarking?

**Hint:** queries with notable calls/time/block activity.

### Exercise 35 — Plan Regression

Why test multiple queries after changing the setting?

**Hint:** a planner setting affects many different queries.

### Exercise 36 — Cache Pressure

How can a large batch scan affect the OLTP cache?

**Hint:** causes cache churn and evicts hot pages.

### Exercise 37 — Tuning Too High

What is the main risk?

**Hint:** the planner evaluates index access too optimistically.

### Exercise 38 — Tuning Too Low

What is the main risk?

**Hint:** the planner evaluates index access too pessimistically.

### Exercise 39 — Benchmark

Why use the same cache/concurrency conditions when comparing?

**Hint:** avoids false conclusions caused by warm/cold cache or differing workloads.

### Exercise 40 — Tuning Decision

List the evidence needed before changing `effective_cache_size`.

**Hint:** memory budget, working set, EXPLAIN plans, actual buffers, workload concurrency, and runtime measurements.

## 61. Frequently Asked Questions

### Does effective_cache_size make the database cache more data?

No. It only affects the planner's assumption. To change shared buffer allocation, look at `shared_buffers`; OS cache is managed by the operating system.

### Should effective_cache_size equal shared_buffers?

Not necessarily. The planner needs to account for both the portion of OS page cache that can serve database files and the cache shared across queries.

### Should it equal total RAM?

Not by default. You must subtract/estimate memory for the OS, backend processes, other applications, container limits, and cache overlap.

### Does a higher value always make queries faster?

No. It may cause the planner to choose a different plan; the new plan may be better or worse depending on the workload and actual cache.

### Does effective_cache_size affect execution after a plan is generated?

It affects planning/cost estimation. It does not allocate cache or directly change data reading mechanics in the executor.

### Why does the planner still pick a sequential scan when cache is large?

The query may need most of the table, no suitable index exists, or estimates/cost parameters make a sequential scan cheaper.

### Why did the planner pick an index scan yet the query is slow?

Heap fetches may be scattered, cache may be insufficient, actual rows may exceed estimates, or storage latency may be high.

### Does a 99% hit ratio mean effective_cache_size is set correctly?

No. Hit ratio is only one signal; examine query plans, OS cache, working set, and latency.

### Is a restart required after changing effective_cache_size?

Depends on GUC context and configuration method. Check `pg_settings.context`, then confirm the active value with `SHOW`.

### Can you test multiple values without changing server configuration?

You can use `SET` in a session if the context allows, then compare `EXPLAIN`. This is a planner test; runtime benchmarking requires separate controlled conditions.

### Does effective_cache_size replace random_page_cost?

No. One setting describes a cache assumption; the other describes the relative cost of random page access.

### Does effective_cache_size prevent sorts from spilling?

Not directly. Sort/hash workspace relates to `work_mem` and query execution.

### Does pg_buffercache show the entire OS cache?

No. It observes PostgreSQL shared buffers.

### When should you re-evaluate the setting?

When RAM, container limits, `shared_buffers`, workload mix, concurrency, storage, or working set changes significantly.

## 62. Summary

Key observation and testing commands:

~~~sql
-- Planner cache assumption.
SHOW effective_cache_size;

-- Related memory/cost settings.
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW effective_io_concurrency;

-- Setting metadata.
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'effective_cache_size',
    'shared_buffers',
    'work_mem',
    'random_page_cost',
    'seq_page_cost'
);

-- Database-level buffer counters.
SELECT
    datname,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- Relation-level I/O.
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 20;

-- Planner estimate.
EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;

-- Runtime and buffer evidence in a safe environment.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Key principles to remember:

1. `effective_cache_size` is a planner cache assumption, not a memory allocation.
2. `shared_buffers` is shared cache memory actually allocated by PostgreSQL.
3. OS page cache can serve database file reads.
4. The planner must consider shared buffers, OS cache, overlap, and query concurrency.
5. Higher values tend to make index access look cheaper; lower values can make sequential scans more attractive.
6. No single fixed RAM percentage is right for every host.
7. `random_page_cost` and `seq_page_cost` are cost assumptions distinct from cache size.
8. Cost units are not milliseconds.
9. Selectivity, cardinality estimates, correlation, and index design still determine the plan.
10. A sequential scan is not inherently bad.
11. `work_mem` addresses sort/hash workspace, not cache assumptions.
12. `pg_stat_database` and `pg_statio_user_tables` give buffer I/O signals but do not measure total OS cache.
13. `pg_buffercache` observes PostgreSQL shared buffers, not OS page cache.
14. `EXPLAIN` shows planned costs; `EXPLAIN (ANALYZE, BUFFERS)` provides runtime/buffer evidence.
15. Fix statistics before blaming the cache assumption.
16. Test the setting per session when possible and change one variable at a time.
17. Compare multiple representative queries under equivalent cache/concurrency conditions.
18. Check memory limits in VMs/containers instead of using total host RAM.
19. Monitor for plan regressions after deployment.
20. Re-evaluate when memory budget, workload, or topology changes.

Concept diagram:

~~~text
Planner needs to choose an access path
             |
             v
      Estimate page costs
             |
             v
      effective_cache_size
             |
             v
   Assume pages may be cached
             |
       +-----+------+
       |            |
       v            v
    Index path   Sequential path
       |            |
       +-----+------+
             |
             v
       Compare estimated costs
             |
             v
       Choose lowest-cost plan
             |
             v
       EXPLAIN / BUFFERS
             |
             v
   Cross-check runtime and real cache
             |
             v
      Tune with evidence
~~~

**Conclusion:** `effective_cache_size` helps the planner estimate how much cache can serve a query to cost data access, especially when comparing index access with sequential scans. An appropriate value should reflect **shared buffers, OS page cache, the memory budget, and contention across queries**. Combine query plans, row estimates, buffer statistics, and runtime measurements before tuning; changing this parameter neither allocates RAM nor makes the cache larger on its own.
