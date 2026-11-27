# Parallel Workers, CPU Limits, and Parallel Query Efficiency

PostgreSQL can split certain query or maintenance operations into multiple parts so multiple processes execute them concurrently. This mechanism is called **parallel query** or **parallel processing**. When data is large and CPU has headroom, multiple workers can shorten the time spent scanning tables, joining, aggregating, or building indexes. However, adding workers does not automatically make queries faster: they consume CPU, memory, I/O, worker slots, and OS resources; many parallel queries running simultaneously can slow down the entire system.

Optimizing parallelism therefore requires coordinating three layers:

1. **PostgreSQL planner/executor:** decides whether to generate a parallel plan, how many workers to request, and which plan nodes can run in parallel.
2. **PostgreSQL worker limits:** limits total background workers, cluster-wide parallel workers, and workers per Gather/Gather Merge.
3. **Operating system/container:** enforces actual CPU limits via cgroups, systemd, cpuset, container quotas, or Kubernetes CPU requests/limits.

The goal is to choose a degree of parallelism suited to query size, concurrent query count, allocated CPUs, and workload SLAs.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain PostgreSQL parallel query and the role of parallel workers.
- Distinguish leader process, parallel worker, background worker, and client backend.
- Read `Gather`/`Gather Merge` and `Workers Planned`/`Workers Launched` in EXPLAIN.
- Understand parallel-safe, parallel-restricted, and parallel-unsafe operations.
- Configure `max_worker_processes`, `max_parallel_workers`, `max_parallel_workers_per_gather`, and cost/threshold settings.
- Estimate total worker demand when multiple queries run concurrently.
- Distinguish PostgreSQL worker limits from OS/container CPU limits.
- Tune CPU quotas, cpuset, and Kubernetes requests/limits for the workload.
- Diagnose worker allocation failures, CPU saturation, I/O bottlenecks, and inefficient parallel plans.
- Evaluate the benefits of parallel scans, joins, aggregation, and parallel index maintenance.
- Design monitoring, benchmarks, and runbooks to adjust parallelism safely.

## 2. What Is a Parallel Query?

### 2.1. One Query Can Use Multiple Processes

In normal execution, a single backend process executes a query plan. With parallel query, PostgreSQL can launch multiple parallel workers to execute independent parts of the plan together. The backend dispatches the request, coordinates execution, and collects results; the plan contains `Gather` or `Gather Merge` to combine rows from workers.

Conceptual example:

```text
Client
  |
  v
Leader backend
  |  \        \
  |   \        +---- Parallel worker 2
  |    +------------- Parallel worker 1
  |
  +---- Gather / Gather Merge
             |
             v
        Final result
```

The leader backend can participate in scanning/computing alongside workers, then receive and process tuples from workers. It is not merely an idle proxy.

### 2.2. Splitting Work

Suppose a table has many pages. Instead of one process scanning all pages, a parallel sequential scan can distribute block ranges across multiple workers. Each worker reads a portion and produces tuples. Results are sent back to the leader via shared memory/tuple queues; the leader continues executing plan nodes above Gather.

### 2.3. Parallel Queries Run Within a Single PostgreSQL Instance

A query's parallel workers run on the same PostgreSQL server instance, access the same database cluster, and coordinate via executor/shared-memory mechanisms. This is not distributed query execution across multiple PostgreSQL servers or shards.

If you need to run queries across multiple nodes/shards, you need an appropriate extension or distributed database system; `max_parallel_workers_per_gather` does not create a distributed cluster.

### 2.4. Not Every Query Runs in Parallel

The planner only chooses a parallel plan when:

- Plan nodes exist that support parallel execution.
- The query contains no operations/expressions unsafe in a parallel context.
- Cost estimates show a parallel plan is beneficial.
- Scan size/thresholds and worker limits allow it.
- Worker slots can be allocated when the query runs.

Small queries are usually not worth the overhead of launching workers and gathering tuples.

### 2.5. Parallel Queries Do Not Guarantee Linear Speedup

If a serial query takes 40 seconds, using 4 workers does not guarantee 10 seconds. Startup overhead, leader work, skew, I/O bandwidth, memory contention, and worker allocation keep speedup below the worker count.

## 3. Execution Components

### 3.1. Leader Backend

The leader is the backend process serving the client query. When the plan is parallel, the leader requests parallel workers, launches them if slots are available, coordinates execution, and receives rows.

The leader can:

- Participate in scanning/computing like a worker.
- Read tuples from workers.
- Execute non-parallel plan nodes.
- Perform final aggregation/sorting or steps above Gather.
- Coordinate cancellation/errors and finish the query.

### 3.2. Parallel Workers

Parallel workers are PostgreSQL background worker processes launched to execute part of a parallel plan. They are not independent client sessions and do not accept direct connections from applications.

Workers can be constrained by:

- `max_worker_processes`: total background worker processes allowed to run.
- `max_parallel_workers`: cluster-wide limit on parallel workers.
- `max_parallel_workers_per_gather`: limit on workers a single Gather/Gather Merge can request.
- Worker slots currently used by other background workers/parallel queries.
- OS process/resource limits and CPU availability.

### 3.3. Background Workers Beyond Parallel Workers

PostgreSQL has multiple types of background workers: logical replication workers, extension workers, parallel query workers, and other administrative processes. `max_worker_processes` is the higher-level pool; parallel workers share this limit with other worker processes.

Therefore, raising `max_parallel_workers` beyond the slots remaining in `max_worker_processes` does not create extra worker capacity.

### 3.4. Client Connections Are Not Worker Slots

`max_connections` limits client backends. `max_worker_processes` limits worker processes. The two parameters control different process groups, even though all consume CPU/memory and contend for system resources.

Do not raise `max_connections` to fix parallel worker allocation failures.

### 3.5. Worker Lifetime

Parallel workers are generally launched when a query executes a parallel plan and exit when the parallel portion completes or the query is canceled. A worker slot is freed once the process exits.

If queries frequently request many workers, monitor active parallel queries, worker slots, and process limits together.

## 4. Gather and Gather Merge

### 4.1. Gather

`Gather` receives tuples from parallel workers and the leader and passes results up to the parent plan node. Row order is not preserved simply because one worker scans ahead of another.

Example plan shape:

```text
Gather
  Workers Planned: 4
  -> Parallel Seq Scan on orders
```

Plan nodes beneath `Gather` form the parallel subtree. `Gather` is the boundary where the leader collects results.

### 4.2. Gather Merge

`Gather Merge` combines sorted streams from workers in sorted order. It preserves plan ordering, at the cost of merge and coordination overhead.

Example:

```text
Gather Merge
  Workers Planned: 4
  -> Sort
       -> Parallel Seq Scan on events
```

### 4.3. Workers Planned vs. Workers Launched

In `EXPLAIN (ANALYZE, VERBOSE)`, PostgreSQL can show:

- `Workers Planned`: number of workers the planner intended to use.
- `Workers Launched`: number of workers actually started for that execution.

These numbers can differ. For example, a plan requests 4 workers, yet at runtime only 2 are granted because the worker pool is busy. The query can still proceed with fewer workers.

### 4.4. Planned Workers Are Not Reserved Capacity

The planner does not reserve worker slots in advance for a query. `Workers Planned` is the plan's expectation, while actual allocation happens at execution time. Thus an isolated benchmark may launch all planned workers, whereas production under concurrent load may launch fewer.

### 4.5. Leader Participation

`parallel_leader_participation` controls whether the leader participates in executing the parallel portion. When enabled, the leader can scan/compute alongside workers. When disabled, the leader primarily collects tuples and executes steps above Gather.

Leader participation helps when tuple volume is moderate and the leader has spare CPU. When workers produce output very fast, the leader may need to focus on consuming tuples rather than scanning.

### 4.6. Parallel Tuple Transfer Overhead

Rows from workers must be transferred to the leader via tuple queues/shared memory. For plans producing huge numbers of small rows, transfer/Gather overhead can dominate. Pushing down filters, aggregating early, or reducing tuples crossing Gather often helps.

## 5. Types of Parallel Operations

### 5.1. Parallel Sequential Scan

A parallel sequential scan divides heap block ranges across multiple workers. It fits queries reading most of a table that is large enough to offset startup overhead.

It can be ineffective when:

- The query needs only a few rows and an index scan is better.
- Storage bandwidth is already saturated.
- The table is small.
- CPU quota is smaller than total workers.
- Rows are heavily filtered yet the plan still reads many pages.

### 5.2. Parallel Bitmap Heap Scan

PostgreSQL can parallelize the heap scan portion of a bitmap heap scan in supported cases. Bitmap index scans and heap block processing have their own execution model; do not assume every index operation is parallel.

### 5.3. Parallel Index Scan

PostgreSQL supports parallel index scans for certain access methods/plan shapes (such as B-tree in modern versions). EXPLAIN is the source of truth; not every index type or query can be parallelized.

### 5.4. Parallel Append

`Parallel Append` distributes work across child plans, such as partition scans, allowing workers to process different partitions/subplans.

This helps with partitioned tables, depending on partition pruning, plan shape, and individual partition sizes. A single oversized partition can still cause skew.

### 5.5. Parallel Aggregation

Parallel aggregation typically uses two stages:

1. Partial aggregate on workers.
2. Finalize aggregate on the leader after collecting partial states.

For example, `Partial HashAggregate` and `Finalize HashAggregate`. Aggregate functions must support appropriate combine/parallel semantics.

### 5.6. Parallel Hash Join

Some hash joins can use a shared hash table or parallel hash build/probe. Benefit depends on input sizes, memory, and data distribution. Large hash tables can create memory pressure; parallelism does not fix bad join cardinality estimates.

### 5.7. Parallel Merge Join

Merge joins can appear in parallel plans depending on sorting/order and plan shape. Sort cost, merge coordination, and data distribution determine efficiency.

### 5.8. Parallel Sort

Sorts can run inside workers in the parallel subtree; results are merged via Gather Merge or processed further. Sort memory is per operation/per process, so multiple workers can raise total memory usage considerably.

### 5.9. Parallel Maintenance

PostgreSQL also uses parallel workers for certain maintenance operations, notably parallel index builds. `max_parallel_maintenance_workers` controls workers for supported maintenance operations. This is an operation-level limit that still draws from `max_worker_processes`.

### 5.10. Not All SQL Commands Are Parallelizable

Parallel queries apply primarily to eligible SELECTs/plan portions. Certain commands or expressions are restricted due to side effects, transaction semantics, locks, temporary state, or executor constraints.

## 6. Parallel Safety

### 6.1. Why Classify Safety?

A worker running in a parallel context cannot arbitrarily execute every operation a leader backend can. PostgreSQL must know whether a function/expression has side effects, depends on session state, or accesses resources unsafe for concurrent multi-process execution.

### 6.2. PARALLEL SAFE

A function marked `PARALLEL SAFE` may run inside a parallel worker if other plan conditions allow. The function must genuinely be safe for concurrent execution and must not assume all calls occur in the same backend process.

### 6.3. PARALLEL RESTRICTED

`PARALLEL RESTRICTED` can only execute in the leader, never in parallel workers. A plan may still have parallel subtrees below or beside a restricted expression if the executor can place it appropriately.

### 6.4. PARALLEL UNSAFE

`PARALLEL UNSAFE` forbids the query from running in parallel mode. If an unsafe expression appears, the planner generally must choose a serial plan for the query.

### 6.5. User-Defined Functions

Do not blindly mark functions safe just to force parallel plans. A function that writes files, updates sequences, modifies database state, reads session-specific state, or invokes non-process-safe code can produce wrong results or duplicate side effects.

Example pure function declaration:

```sql
CREATE FUNCTION normalize_code(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT upper(trim($1));
$$;
```

Only mark `PARALLEL SAFE` if the implementation and every function it calls genuinely meet the criteria. `IMMUTABLE` and `PARALLEL SAFE` are distinct properties; immutability alone does not prove parallel safety.

### 6.6. Inspecting Function Properties

You can inspect volatility and parallel classification in the catalog:

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.provolatile,
    p.proparallel
FROM pg_proc AS p
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE p.proname = 'normalize_code';
```

`proparallel` values are typically `s` (safe), `r` (restricted), and `u` (unsafe).

### 6.7. Commonly Restricted Cases

Depending on PostgreSQL version and plan context, parallel execution can be restricted by:

- Temporary tables or session-local state.
- Cursors/row locking and certain locking clauses.
- Data-modifying operations or side-effecting functions.
- Sequence access/sequence modification.
- Certain foreign tables/FDWs or custom scan providers.
- Certain transaction isolation/transaction state combinations.
- Functions/aggregates/operators lacking appropriate parallel safety markings.

Exact rules vary by version. Check the Parallel Plans section in the PostgreSQL documentation for your major version and verify with EXPLAIN.

### 6.8. Parallel-Safe Does Not Mean Fast

A safe marking only means the function can run in a parallel context. It could still be CPU-heavy, perform external I/O, lock shared resources, or suffer contention; running many copies concurrently can slow down the system.

### 6.9. Extensions and Custom Code

Extensions may register functions, aggregates, custom scans, or background workers. Check parallel safety markings and extension docs. If an extension function defaults to unsafe, queries calling it may lose parallel plans.

### 6.10. When a Query Does Not Parallelize

If a plan has no Gather/Gather Merge, check:

1. Is there a `PARALLEL UNSAFE` expression/function?
2. Does the query use restricted commands/locks/temporary state?
3. Is the table large enough per minimum parallel scan thresholds?
4. Do planner costs favor a parallel plan?
5. Is `max_parallel_workers_per_gather` set to `0`?
6. Are table statistics and row estimates reasonable?

Do not enable experimental force-parallel settings or raise workers before identifying the cause.

## 7. Worker Limit Parameters

### 7.1. max_worker_processes

`max_worker_processes` sets the maximum total background worker processes the server can run concurrently. This pool serves parallel workers and other background workers.

This is the foundational limit. If set too low, parallel queries or extension/logical replication workers may run out of slots. If set too high, the server may spawn more processes than host CPU/memory can support.

### 7.2. max_parallel_workers

`max_parallel_workers` limits the total parallel workers allowed to run simultaneously across the entire PostgreSQL cluster. It does not cover all background worker types, yet parallel workers still require slots from `max_worker_processes`.

### 7.3. max_parallel_workers_per_gather

`max_parallel_workers_per_gather` limits how many parallel workers a single Gather/Gather Merge node can request. This is a per-plan-node/query limit, not a cluster total.

If set to 4, one query can request up to 4 parallel workers for a Gather; concurrent Gather nodes/queries remain capped by the global pool.

### 7.4. max_parallel_maintenance_workers

This parameter limits parallel workers for supported maintenance commands, such as `CREATE INDEX`/`REINDEX` depending on version and operation. It does not allocate a separate pool independent of `max_worker_processes`.

### 7.5. Summary Table

| Parameter | Scope | Role |
| --- | --- | --- |
| `max_worker_processes` | Server-wide | Ceiling for background worker processes. |
| `max_parallel_workers` | Cluster-wide | Ceiling for active parallel workers. |
| `max_parallel_workers_per_gather` | Per Gather/Gather Merge | Ceiling for workers a query plan node can request. |
| `max_parallel_maintenance_workers` | Per maintenance operation | Ceiling for parallel maintenance workers. |
| `max_connections` | Server-wide | Client backend connections, not the parallel worker pool. |

### 7.6. Starting Configuration Example

Example for a server with roughly 8 allocated logical CPUs and a moderate workload:

```conf
max_worker_processes = 16
max_parallel_workers = 8
max_parallel_workers_per_gather = 2
max_parallel_maintenance_workers = 2
```

This is an illustrative starting point, not a universal formula. Factor in extension workers, logical replication, CPU quotas, query concurrency, memory, and workload latency.

### 7.7. Parameter Context and Restarts

Some worker limits are startup/postmaster parameters requiring a PostgreSQL restart; other planner/runtime parameters can be reloaded or set per session depending on context. Check `pg_settings.context`, `pending_restart`, and documentation for your major version before changing.

### 7.8. Inspecting Current Values

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_parallel_maintenance_workers',
    'parallel_leader_participation'
)
ORDER BY name;
```

### 7.9. Worker Demand vs. Worker Supply

Suppose 5 concurrent queries each have a Gather requesting 4 workers. Theoretical demand is 20 workers. If `max_parallel_workers` is 8, the cluster grants at most 8 parallel workers total; remaining queries run with fewer or no extra workers.

If `max_worker_processes` only has 6 slots left after subtracting other background workers, effective supply is even lower.

### 7.10. Do Not Equate Workers with CPU Count

`max_parallel_workers` is a process count, not guaranteed CPUs. You can configure 16 workers on a 4-CPU machine, yet they will contend for those 4 CPUs. Configuring worker capacity and CPU capacity are related yet distinct decisions.

## 8. Planner Thresholds and Cost Settings

### 8.1. min_parallel_table_scan_size

`min_parallel_table_scan_size` sets the minimum table scan size for the planner to consider a parallel sequential scan. Tables smaller than the threshold are usually not worth parallel setup overhead.

### 8.2. min_parallel_index_scan_size

`min_parallel_index_scan_size` sets the minimum index scan size for the planner to consider a parallel index scan in supported cases.

### 8.3. parallel_setup_cost

`parallel_setup_cost` estimates the overhead of launching parallel workers and coordination. Higher values make the planner choose parallel plans less often; lowering it too far can cause the planner to parallelize many small queries.

### 8.4. parallel_tuple_cost

`parallel_tuple_cost` estimates the cost of transferring each tuple from a worker to the leader. Higher values make parallel plans that must gather many rows less attractive.

### 8.5. seq_page_cost and random_page_cost

These are cost assumptions influencing scan/index choices. They are not measured latencies in milliseconds. Mistuning them can make the planner choose the wrong access path, skewing parallelism decisions.

### 8.6. force_parallel_mode

Recent PostgreSQL releases have changed/deprecated certain experimental settings related to force-parallel mode. Do not use experimental settings for production tuning. Use EXPLAIN, standard planner settings, and version-appropriate benchmarks.

### 8.7. Defaults Are Not Targets

Default costs/thresholds are designed to work across varied environments. NVMe servers, network storage, container CPU quotas, and OLTP/analytics workloads have different characteristics. Tune from measurements rather than copying blog configs.

### 8.8. Session-Level Experimentation

To compare planner behavior in a lab, use `SET LOCAL` inside a transaction for settings permitting session changes:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (COSTS, VERBOSE)
SELECT count(*)
FROM large_fact_table
WHERE event_date >= DATE '2026-01-01';
ROLLBACK;
```

Then compare with the active configuration. Do not use a single-session test to predict production behavior if concurrency or resource limits differ.

### 8.9. Planner Parallelism and Statistics

The planner needs accurate estimates of row counts, selectivity, and relation sizes. Stale `ANALYZE`/autovacuum statistics can cause the planner to pick wrong plans, including wrong parallel plans. Check estimates against actual rows before tuning costs.

### 8.10. Do Not Force Parallel Queries to Mask Index/Schema Issues

If a query has a selective filter yet lacks an index, the planner may have to perform a large scan. Adding workers can shorten scan time while still burning heavy I/O and CPU. Review indexes, partitioning, predicates, join keys, and statistics.

## 9. Leader Participation and Degree of Parallelism

### 9.1. parallel_leader_participation

`parallel_leader_participation` is typically enabled by default. When enabled, the leader participates in the parallel subtree and processes part of the work. When disabled, the leader primarily coordinates and collects tuples, avoiding double duty in certain workloads.

### 9.2. When Leader Participation Helps

- The parallel subtree produces modest output.
- The leader has spare CPU capacity.
- The query is a relatively balanced scan/aggregate.
- Worker count is small and gather throughput is not saturated.

### 9.3. When the Leader Becomes a Bottleneck

If workers produce rows rapidly, the leader must continuously receive, deserialize, and process tuples. In such cases the leader may stop scanning to focus on gathering. Adding workers can worsen gather queue/leader CPU bottlenecks.

### 9.4. Workers per Gather

Increasing `max_parallel_workers_per_gather` for a query can boost scan throughput, but also increases:

- CPU demand.
- Worker process count.
- Memory for sort/hash/aggregate in each process.
- I/O concurrency.
- Tuple transfer/gather traffic.

Do not set the maximum possible value for every workload.

### 9.5. Parallelism by Workload Class

You can use role/database/session settings to bound parallelism:

- OLTP interactive queries: few workers or serial execution to protect latency and concurrency.
- Batch/reporting: allow more workers when CPU headroom exists.
- Maintenance windows: allow controlled parallel index builds.
- Ad hoc analytics: limit worker counts/resource groups to protect applications.

PostgreSQL core settings do not form a complete workload scheduler on their own; you may also need connection pools, job schedulers, or OS/container resource controls.

### 9.6. SET per Role/Database

Example limiting per-query workers for a reporting role:

```sql
ALTER ROLE reporting_user
SET max_parallel_workers_per_gather = 2;
```

Or for a database:

```sql
ALTER DATABASE analytics
SET max_parallel_workers_per_gather = 4;
```

Settings take effect for new sessions after reconnecting. Server/global limits still take precedence; a per-role setting cannot exceed `max_parallel_workers`.

### 9.7. SET LOCAL per Transaction

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
-- Run latency-sensitive statements serially in this transaction.
SELECT ...;
COMMIT;
```

Use `SET LOCAL` when you want a temporary change within a transaction and the setting allows session-context changes.

### 9.8. Connection Pools and Role Settings

With transaction pooling, session-level settings may not persist across transactions as applications expect. Prefer `SET LOCAL` inside transactions or role/database defaults; verify your PgBouncer mode behavior.

### 9.9. Do Not Size Workers by Session Count

A pool of 100 connections does not mean provisioning 100 × 4 workers. Size around queries actually running simultaneously, CPU budget, I/O, and latency targets.

## 10. Parallel Maintenance

### 10.1. CREATE INDEX

Some `CREATE INDEX` statements can use parallel workers for supported build phases. `max_parallel_maintenance_workers` caps workers per maintenance operation; `max_parallel_workers` and `max_worker_processes` still bound global supply.

### 10.2. REINDEX

`REINDEX` on supported indexes/access methods can use parallel maintenance. Check command options, version, and EXPLAIN/command output to confirm.

### 10.3. VACUUM

VACUUM can use parallel workers for certain index processing phases in supported versions. Parallel maintenance behavior does not mean the entire VACUUM heap scan runs in parallel like a parallel query.

### 10.4. maintenance_work_mem

`maintenance_work_mem` governs the memory budget for maintenance operations. Multiple concurrent operations/worker processes can increase total memory demand. Account for concurrent jobs, not just a single session.

### 10.5. Maintenance Workers vs. Query Workers

Maintenance workers and parallel query workers share worker process capacity. Running parallel `CREATE INDEX` during peak hours can starve parallel `SELECT`s of slots and contend for CPU/I/O.

### 10.6. Maintenance Windows

Set worker limits and schedules for large index builds/reindexes/vacuums. Monitor replication lag, WAL generation, disk throughput, and application latency.

## 11. OS-Level CPU Limits

### 11.1. PostgreSQL Worker Limits Are Not CPU Limits

`max_parallel_workers` caps how many worker processes PostgreSQL can run. It does not restrict how many CPUs a process uses, nor does it guarantee each worker a dedicated core.

CPU scheduling belongs to the OS or container runtime. A server with 32 parallel worker slots given only 4 CPUs will have many processes contending for 4 CPUs.

### 11.2. CPU Affinity and cpuset

CPU affinity/cpuset defines the set of CPUs a process/container is allowed to run on. For example, a container restricted to CPUs 2–5 has an effective CPU set of 4 CPUs even if the host has more cores.

Affinity restricts placement, not total CPU time quota. Cpuset and quota can be combined.

### 11.3. CPU Quota

A CPU quota caps how much CPU time a cgroup can consume within a period. In cgroup v2, `cpu.max` expresses quota and period in microseconds; `quota / period` approximates allocated CPUs.

Example:

```text
cpu.max = 400000 100000
CPU quota = 400000 / 100000 = 4 CPU equivalents
```

A container can burst across multiple cores within a period and then get throttled once its quota is exhausted.

### 11.4. CPU Weight/Share

CPU weight/share adjusts relative CPU proportions when cgroups contend. It is not a hard cap when spare CPU exists. Do not confuse requests/weights with quotas/limits.

### 11.5. Docker CPU Limit

Example running a container limited to roughly 4 CPUs:

```bash
docker run --cpus=4 ...
```

This is illustrative. Account for CPU quota alongside cpuset, host contention, and memory limits. Verify actual runtime/cgroup state rather than trusting CLI flags alone.

### 11.6. systemd CPUQuota

For PostgreSQL running under systemd, CPU can be capped at the service slice/unit via `CPUQuota=`, and CPU sets restricted via `AllowedCPUs=` on supported systemd versions.

Example unit override configuration:

```ini
[Service]
CPUQuota=400%
AllowedCPUs=2-5
```

`CPUQuota=400%` represents a maximum of roughly four CPUs on supported systemd systems; `AllowedCPUs=2-5` restricts the CPU set. Check systemd/cgroup version and unit inheritance.

### 11.7. Kubernetes CPU Requests and Limits

In Kubernetes:

- `resources.requests.cpu` is used by the scheduler for Pod placement and sets relative CPU share/weight under contention.
- `resources.limits.cpu` sets a hard limit; exceeding the quota within a period causes CPU throttling.
- CPU is typically expressed in cores or millicores, e.g., `2000m` equals 2 CPUs.

A Pod with request `2` and limit `4` gets scheduler reservation for 2 CPUs and can burst up to 4 CPUs if node capacity permits.

### 11.8. Kubernetes Resources Example

```yaml
resources:
  requests:
    cpu: "2"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "12Gi"
```

This is an example only. Memory limit is a hard boundary unlike CPU scheduling; a PostgreSQL OOM kill can cause restarts/failovers. Budget memory separately for shared buffers, connections, sorts, hashes, workers, and OS cache.

### 11.9. Kubernetes Guaranteed/Burstable QoS

QoS class depends on CPU and memory requests/limits across all containers in the Pod. Guaranteed QoS requires requests equal to limits for both CPU and memory on every container. Burstability/eviction behavior affects stability; do not optimize QoS for CPU while neglecting memory.

### 11.10. CPU Throttling

When a container hits its quota, the scheduler throttles the cgroup for the remainder of the period. PostgreSQL workers still exist yet receive no CPU time. This can spike query latency, slow HA loops, and increase replication lag.

### 11.11. Inspecting cgroup v2

In Linux cgroup v2, useful files include:

- `cpu.max`: quota and period.
- `cpu.stat`: usage, throttling periods, and throttled time.
- `cpu.weight`: relative CPU weight.
- `cpuset.cpus.effective`: CPUs actually usable.

Cgroup paths depend on process/container layout. Read the exact cgroup for the PostgreSQL service/container, not just the root cgroup.

### 11.12. CPU Metrics in Kubernetes

Use container metrics/Prometheus/cAdvisor or your cluster metrics pipeline to track:

- CPU usage cores.
- CPU throttled periods/time.
- CPU request/limit.
- Node CPU pressure.
- Pod restarts/OOM kills.
- Container memory working set.

Low average CPU usage does not prove the system is free from throttling; inspect throttling metrics alongside latency.

## 12. Calculating Worker Budgets by CPU and Concurrency

### 12.1. Effective CPU Budget

Let:

- `C_quota`: CPU equivalents from `quota / period`.
- `C_cpuset`: CPUs in the effective cpuset.
- `C_host`: CPU capacity actually usable on the host after other limits.

Approximate effective CPU budget:

```text
C_effective = min(C_quota, C_cpuset, C_host)
```

If no quota is set, omit that term; if no cpuset is set, use the host/container CPU set. This is an approximate sizing model, not a scheduler guarantee.

### 12.2. Estimating Active Processes

With `Q` concurrent parallel queries, each using up to `W` workers, runnable processes in the parallel portion are roughly:

```text
Parallel workers ≈ Q × W
Leader backends ≈ Q
Total parallel execution processes ≈ Q × (W + 1)
```

Actual counts are lower when queries launch fewer workers, the leader does not participate, or fewer queries are active; however, background processes and other workloads must still be included.

### 12.3. Oversubscription Example

Suppose a container has a 4-core CPU limit. 4 concurrent queries each request 4 workers plus a leader:

```text
4 queries × (4 workers + 1 leader) = 20 processes
CPU budget = 4 cores
```

Twenty runnable processes will contend for 4 CPU equivalents if all are CPU-bound. Adding workers increases context switching and queueing rather than throughput.

### 12.4. More Conservative Budget Example

With an 8-core CPU budget and 2 concurrent analytics queries, each using 3 workers plus leader:

```text
2 × (3 + 1) = 8 execution processes
CPU budget = 8 cores
```

This is a more reasonable starting point for CPU-bound queries, while still needing CPU headroom for autovacuum, WAL, checkpoints, connections, the OS, and background services.

### 12.5. Not Every Process Is CPU-Bound

Queries can wait on disk I/O, locks, network, or buffer reads. When I/O-bound, adding workers can raise queue depth and storage contention. When CPU-bound, adding workers only helps until CPU capacity or leader/gather becomes the bottleneck.

### 12.6. Sizing Formulas Do Not Replace Benchmarks

Use process estimates to rule out absurd configurations, then benchmark with representative workloads and real concurrency. Do not apply a fixed workers-to-CPU ratio to every database.

### 12.7. Leave Headroom

Never allocate 100% of the CPU budget to parallel queries. Leave headroom for:

- Client backends and OLTP queries.
- WAL writer, checkpointer, background writer.
- Autovacuum and replication.
- OS kernel, monitoring/agents, and storage/network interrupts.
- Bursty traffic and maintenance.

### 12.8. OLTP and Analytics on the Same Server

An analytics query can occupy multiple workers and saturate CPU for extended periods, elevating OLTP p95/p99 latency. Use role/database limits, workload separation, or a dedicated read replica to contain the impact.

### 12.9. CPU Limits and Parallelism Must Be Tuned Together

If a Kubernetes CPU limit drops from 8 to 2 cores while `max_parallel_workers` stays unchanged, queries can still launch the same worker count and get heavily throttled. After changing quotas, re-evaluate per-gather limits, query concurrency, and maintenance budgets.

### 12.10. NUMA and CPU Topology

Multi-socket/NUMA machines have non-uniform memory locality. Shared buffers, worker processes, and memory allocations can incur remote NUMA access penalties. Do not pin workers to cores arbitrarily; benchmark on real hardware and inspect OS NUMA policies/metrics.

## 13. Memory, I/O, and Resources Coupled with Parallelism

### 13.1. Parallel Workers Also Consume Memory

Workers execute plan nodes such as sorts, hash joins, and hash aggregates. These operations allocate memory per process. Increasing worker count can raise total memory demand even when query logic stays identical.

### 13.2. work_mem Is Not a Whole-Query Memory Limit

`work_mem` is the memory budget for operations like sorts/hashes before spilling to disk. One query can contain multiple sort/hash nodes and multiple parallel processes. Thus you cannot count memory as just a single `work_mem`.

Conservative estimate:

```text
Memory demand ≈ active processes
                × concurrent memory-heavy plan nodes
                × per-operation memory budget
```

This is an upper-bound planning model; not every operation uses its full budget simultaneously. Newer PostgreSQL versions include additional controls such as `hash_mem_multiplier`; check your exact version.

### 13.3. Memory Amplification Example

If 4 concurrent queries each have 3 workers + leader, and each process runs a hash operation that can use up to 64 MB:

```text
4 queries × 4 processes × 64 MB = 1024 MB
```

That is just one hash node per process. With multiple hash/sort nodes or concurrent autovacuum/maintenance, total demand can be higher. Do not set `work_mem` by simply dividing RAM by `max_connections`.

### 13.4. Hash Spills and Sort Spills

When memory is insufficient, sorts/hashes spill to temporary files. Parallelism can multiply temp file I/O if multiple workers spill at once. Check `EXPLAIN ANALYZE` temp read/write blocks, `log_temp_files`, and filesystem capacity.

### 13.5. Shared Buffers and OS Page Cache

Parallel workers read shared buffers and OS cache. More workers increase concurrent page access without adding RAM. If the working set exceeds memory, storage reads can become the bottleneck.

### 13.6. I/O Bandwidth

A parallel sequential scan can raise throughput when storage has spare bandwidth. If disk/NVMe/network storage is already saturated, extra workers only increase queue depth and latency.

Monitor throughput, IOPS, queue depth, read latency, cache hit ratio, and `pg_stat_io` on supported PostgreSQL versions.

### 13.7. Buffer Contention and Locks

A parallel query can increase concurrent buffer accesses, lightweight lock activity, and contention on shared structures. If CPU usage is modest yet workers wait on each other, adding workers can make performance worse.

### 13.8. WAL and Replication

Read-only parallel queries generally do not generate WAL per row read, yet parallel maintenance or other workloads can produce substantial WAL. CPU/I/O contention from parallel jobs can slow WAL flushes, checkpoints, and replication replay.

### 13.9. Temporary Storage

Ensure temp tablespaces/filesystems have adequate capacity and low latency. Multiple workers spilling simultaneously can fill temp disks, failing queries and disrupting other workloads.

### 13.10. Memory Cgroup Limits

Container memory limit is a hard boundary. Shared buffers, backend private memory, worker private memory, maintenance, OS page cache, and extension allocations all consume cgroup memory. Exceeding the limit triggers kernel OOM kills of processes/containers.

Never raise worker count without evaluating memory headroom and temp I/O.

## 14. Reading and Measuring Parallel Plans

### 14.1. EXPLAIN Before Tuning

Use `EXPLAIN` to inspect the chosen plan:

```sql
EXPLAIN (COSTS, VERBOSE, SETTINGS)
SELECT customer_id, count(*)
FROM large_orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
```

Look for `Gather`, `Gather Merge`, `Parallel Seq Scan`, `Parallel Append`, partial/final aggregates, or other parallel nodes.

### 14.2. EXPLAIN ANALYZE

To measure actual execution:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT customer_id, count(*)
FROM large_orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
```

`ANALYZE` executes the query. Only run it on statements safe for production data and load; for DML/DDL, understand side effects and have a proper rollback plan.

### 14.3. Reading Gather

Illustrative example:

```text
Finalize Aggregate
  -> Gather
       Workers Planned: 4
       Workers Launched: 4
       -> Partial Aggregate
            -> Parallel Seq Scan on large_orders
```

Interpretation:

- The planner requested 4 workers.
- All 4 workers launched during this run.
- Each process computed a partial aggregate over its slice of data.
- The leader gathered partial results and finalized the aggregate.

### 14.4. Workers Launched Lower Than Planned

For example, `Workers Planned: 4` yet `Workers Launched: 1`. Check:

- Has `max_parallel_workers` run out of slots?
- Does `max_worker_processes` have spare capacity?
- Are other background workers occupying slots?
- Are there process limits or resource exhaustion?
- Are multiple parallel queries running concurrently?
- Do logs report worker launch failures?

The query does not necessarily fail; it can still run with fewer workers.

### 14.5. Actual Rows and Loops

`EXPLAIN ANALYZE` shows actual rows/loops per node. For parallel nodes, numbers may be averaged/aggregated across workers and leader or shown per worker with `VERBOSE`. Understand how PostgreSQL reports rows/loops before summing numbers manually.

### 14.6. Per-Worker Skew

If worker 0 processes far more rows or runs much longer than worker 1, the workload has skew. Causes include block distribution, partition sizes, data clustering, join key distribution, or uneven task cost.

Adding workers does not necessarily cure skew; inspect partitioning, predicates, join distribution, and plan structure.

### 14.7. Planning Time and Execution Time

Parallel plans incur planning/setup overhead. For small queries, execution may be brief while worker startup/gather increases total latency. Compare execution time and end-to-end latency under identical conditions.

### 14.8. Buffers

`BUFFERS` reports shared/local/temp blocks hit/read/dirtied/written. Parallel workers can produce large aggregate buffer counts. Use them to distinguish cache hits, physical reads, and temp spills; do not treat block counts as CPU time.

### 14.9. Settings

`SETTINGS` displays non-default planner-related settings influencing the plan. Record session/server settings during benchmarks for fair comparisons.

### 14.10. Comparing Serial vs. Parallel

In a lab, compare:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM large_fact_table;
ROLLBACK;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM large_fact_table;
```

The first run forces serial execution within the transaction; the second uses the default setting. Repeat multiple times while controlling cache state and concurrency. Never compare a cold-cache run against a warm-cache run.

## 15. Monitoring Parallel Workers

### 15.1. pg_stat_activity

`pg_stat_activity` shows active backends. On supported PostgreSQL versions, inspect `backend_type`, `leader_pid`, `query`, `state`, `wait_event_type`, and `wait_event` to identify parallel workers and leaders.

Example:

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid NULLS FIRST, pid;
```

Certain columns depend on major version. If an older server lacks `leader_pid` or `backend_type`, adapt the query to your catalog/view version.

### 15.2. Counting Worker Processes

```sql
SELECT
    backend_type,
    state,
    count(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
```

Snapshot process counts reflect only the instant the query runs. Short-lived workers may be missed if sampling is too coarse.

### 15.3. Viewing Query Leaders and Workers

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_text
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

Group rows sharing the same `leader_pid` to see which worker processes belong to which query.

### 15.4. pg_stat_statements

`pg_stat_statements` aggregates query workloads: calls, total/mean execution time, rows, shared blocks, temp blocks, and other counters depending on version. Use it to identify query classes needing tuning.

Stats aggregate by normalized query identity; they do not replace `EXPLAIN` for a specific execution. Do not infer worker counts from mean execution time alone.

### 15.5. pg_stat_io

On PostgreSQL versions supporting `pg_stat_io`, this view reports I/O statistics by backend type/object/context. It helps reveal read/write patterns and I/O impact; it is not directly a CPU profile.

### 15.6. OS CPU Metrics

Monitor:

- CPU user/system/iowait/steal.
- Run queue and load average.
- Context switches.
- CPU pressure stall information (PSI) if available.
- Per-process CPU of PostgreSQL backends/workers.
- Cgroup quota/throttling.

High load average can reflect runnable processes or uninterruptible I/O waits; never use load average alone to conclude CPU saturation.

### 15.7. Kubernetes Metrics

Track per-container CPU usage and throttling, Pod restarts/OOMs, node pressure, and requests/limits. A database Pod can show average usage below limit while still being throttled during bursts; inspect throttled periods/time alongside query latency.

### 15.8. Replication Metrics

Parallel maintenance or CPU pressure can slow standby replay. Monitor receive/replay LSN, replication lag, WAL archive backlog, and synchronous waits to ensure parallel jobs do not degrade HA.

### 15.9. Query Latency Percentiles

Measure p50/p95/p99 by query class and endpoint. Parallelism may shorten a batch query's runtime while increasing OLTP tail latency due to CPU contention. Overall throughput and latency distribution matter more than a single isolated query benchmark.

### 15.10. Minimum Dashboard

A parallelism dashboard should include:

- Effective CPU budget and quota/throttling.
- Active parallel queries and worker processes.
- Workers Planned/Launched from representative EXPLAIN samples.
- `max_worker_processes`/`max_parallel_workers` usage headroom.
- CPU run queue/context switches.
- Memory/temp spill/I/O metrics.
- Query p95/p99 and throughput.
- Replication lag and maintenance activity.

## 16. Parallelism Tuning Workflow

### 16.1. Step 1: Define the Goal

Clarify what you are optimizing:

- Runtime of a large analytics query.
- Batch workload throughput.
- OLTP p95/p99 latency.
- Index build/reindex duration.
- CPU cost or cloud/container cost.

A setting that speeds up one query can hurt overall throughput.

### 16.2. Step 2: Measure Real CPU Capacity

Determine CPU quota, cpuset, node capacity, and shared workloads. Inside containers, never use host `nproc` as the CPU budget if the cgroup limit is lower.

### 16.3. Step 3: Baseline Queries

Pick representative queries and record:

- SQL and bind values/selectivity.
- `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)`.
- Execution time, rows, loops, buffers, temp I/O.
- Workers planned/launched.
- CPU usage and I/O latency.
- Concurrent workload during the benchmark.

### 16.4. Step 4: Inspect Query Shape

Check indexes, partition pruning, join order, row estimates, and filter pushdown. Fix queries/schemas/statistics first if the plan scans/joins excessive data due to bad estimates.

### 16.5. Step 5: Adjust Worker Limits

Pick `max_parallel_workers_per_gather` by query class and concurrency. Ensure `max_parallel_workers` and `max_worker_processes` are sufficient without exceeding worker/CPU/memory budgets.

### 16.6. Step 6: Adjust Planner Costs

Only after baselines show the planner picking suboptimal parallel/serial choices should you test changing `parallel_setup_cost`, `parallel_tuple_cost`, or min scan thresholds. Change one setting at a time and record results.

### 16.7. Step 7: Benchmark Real Concurrency

Run workloads at production-like query concurrency. A single isolated query might run fastest with 8 workers; 10 concurrent queries might perform better with 1–2 workers each.

### 16.8. Step 8: Check Side Effects

Measure OLTP latency, CPU throttling, temp files, memory, I/O, replication lag, and maintenance duration. Reject a single-query speedup if system SLAs degrade.

### 16.9. Step 9: Controlled Rollout

Apply configuration changes through your maintenance/change process. Record old settings, test in staging, compare before/after metrics, use canary or rolling changes where appropriate, and keep rollback ready.

### 16.10. Step 10: Confirm Stability

Observe across full peak and off-peak cycles. A sound configuration achieves the goal without worker starvation, CPU throttling, memory pressure, or tail latency regressions.

## 17. Diagnosing Common Scenarios

### 17.1. Query Has No Gather

Check query size, parallel safety, cost thresholds, table statistics, `max_parallel_workers_per_gather`, and plan shape. Use `EXPLAIN` to see why the planner chose an index scan or serial plan.

### 17.2. Workers Planned Is High, Launched Is Low

Check the global parallel worker cap, background worker slots, concurrent queries, and logs. Inspect worker demand at execution time rather than only in isolated runs.

### 17.3. Workers Launched Is Zero

A query may fall back to running the parallel plan with only the leader when no workers are available, depending on the plan. Inspect `EXPLAIN ANALYZE`, logs, and the worker pool. Do not assume queries always fail when workers fail to launch.

### 17.4. Adding Workers Does Not Speed Up the Query

Causes can include CPU quota, storage bandwidth, leader gather bottleneck, memory spills, skew, lock/buffer contention, or a large serial portion. Identify the critical path instead of adding more workers.

### 17.5. Low CPU Usage Yet Slow Query

Check I/O wait, lock waits, storage latency, network/FDW, temp file I/O, CPU throttling, and wait events in `pg_stat_activity`. Low CPU usage often means processes are waiting.

### 17.6. 100% CPU Usage and Rising Latency

Check runnable queue, active queries, parallel worker count, background jobs, and cgroup throttling. Reducing per-query workers or concurrency can improve total throughput.

### 17.7. Rising CPU Throttling

Compare CPU limit/quota with actual runnable processes. If the quota is constantly throttled, increase CPU limit/request or reduce parallelism/concurrency. Do not just raise `max_parallel_workers`.

### 17.8. Sharp Rise in Temp Files

Check sort/hash nodes, `work_mem`, worker count, and concurrent memory-heavy queries. Determine whether spills stem from parallel worker multiplication or inaccurate plan cardinality.

### 17.9. Replication Lag Spikes During Reports

Check CPU, storage I/O, checkpoint/WAL pressure, and standby replay throughput. Lower report concurrency/parallelism or route reports to a dedicated replica.

### 17.10. Parallel Plans Appear for Tiny Queries

Planner costs/thresholds may be too low or estimates wrong. Compare actual rows/sizes, raise appropriate costs, or fix statistics. Avoid disabling parallelism cluster-wide because of one query.

### 17.11. OLTP Queries Slow Down During Batch Runs

Batch queries can consume CPU, cache, I/O, and worker slots. Apply role/database limits, schedule batches, isolate resources, or offload analytics workloads.

### 17.12. Worker Slots Consumed by Background Jobs

Check logical replication, extension workers, and maintenance jobs. Size `max_worker_processes` with headroom without exceeding host capacity.

### 17.13. Parallel Workers Not Visible in pg_stat_activity

Workers may finish before the monitoring snapshot runs; the query may not be parallel; or version/view columns may differ. Use `EXPLAIN ANALYZE` and sample faster in a lab.

### 17.14. One Worker Is Much Slower

Check data/partition skew, worker CPU affinity, NUMA, storage path, and plan nodes. A single straggler can dictate total query completion time.

### 17.15. CREATE INDEX Slows Down OLTP

Parallel maintenance consumes CPU, memory, and I/O. Lower `max_parallel_maintenance_workers`, schedule off-peak, and monitor replication/WAL.

### 17.16. Container Restarts After Increasing Workers

Check OOM events, memory limits, `work_mem`, parallel sort/hash nodes, and active query concurrency. CPU worker count is not the only factor; workers amplify memory usage.

## 18. Hands-On Labs

These labs require a disposable or staging PostgreSQL instance under controlled load. Adapt table names, paths, and values to your environment. Never alter global settings or run stress tests on production without an approved change plan.

### Lab 1. Observing a Parallel Sequential Scan

#### Step 1. Create a Table

```sql
CREATE TABLE parallel_lab AS
SELECT
    g AS id,
    md5(g::text) AS payload,
    (g % 1000)::integer AS bucket
FROM generate_series(1, 5000000) AS g;

ANALYZE parallel_lab;
```

#### Step 2. Inspect Current Configuration

```sql
SHOW max_worker_processes;
SHOW max_parallel_workers;
SHOW max_parallel_workers_per_gather;
SHOW min_parallel_table_scan_size;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
```

#### Step 3. Inspect the Plan

```sql
EXPLAIN (COSTS, VERBOSE, SETTINGS)
SELECT count(*)
FROM parallel_lab
WHERE bucket < 500;
```

Look for `Gather` and `Parallel Seq Scan`. If absent, check table size, cost, statistics, and parallel safety.

#### Step 4. Run with Execution Timing

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT count(*)
FROM parallel_lab
WHERE bucket < 500;
```

Record Workers Planned/Launched, actual time, rows, buffers, and any temp I/O.

#### Step 5. Compare with Serial Execution

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM parallel_lab WHERE bucket < 500;
ROLLBACK;
```

Run multiple times and compare under equivalent cache/concurrency conditions.

### Lab 2. Varying Workers per Gather

#### Step 1. Save Baseline

Record current settings and the `EXPLAIN ANALYZE` output from Lab 1.

#### Step 2. Test Low Level

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 1;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Step 3. Test Medium Level

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 2;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Step 4. Test Higher Level if Budget Allows

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 4;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Step 5. Record Results

Create a comparison table of workers planned/launched, execution time, CPU, buffers, temp I/O, and concurrent workload latency. Pick the best setting for throughput/SLA goals, not necessarily the fastest isolated query run.

### Lab 3. Function Parallel Safety

#### Step 1. Create a Lab Function

```sql
CREATE FUNCTION parallel_lab_upper(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT upper($1);
$$;
```

#### Step 2. Use the Function in a Query

```sql
EXPLAIN (VERBOSE)
SELECT count(*)
FROM parallel_lab
WHERE parallel_lab_upper(payload) LIKE 'A%';
```

#### Step 3. Change Classification in the Lab

```sql
ALTER FUNCTION parallel_lab_upper(text) PARALLEL UNSAFE;
```

Re-run `EXPLAIN` to see whether the planner drops the parallel plan. Results depend on query/cost/plan nodes; not every query changes.

#### Step 4. Restore Classification

```sql
ALTER FUNCTION parallel_lab_upper(text) PARALLEL SAFE;
```

Only mark functions safe when the implementation is truly safe. This lab function only calls `upper()` on text.

### Lab 4. Observing Worker Allocation Under Concurrency

#### Step 1. Prepare a Moderately Long Query

Choose a sufficiently large scan/aggregate query on the lab table. Do not use an unbounded workload.

#### Step 2. Open Multiple Sessions

Run the query concurrently in 2–4 lab sessions. Configure each session to request a moderate number of workers.

#### Step 3. Observe Active Processes

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    now() - query_start AS age
FROM pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid, pid;
```

#### Step 4. Compare Planned vs. Launched

Capture `EXPLAIN ANALYZE` for each query. Observe worker allocation as sessions compete for the same `max_parallel_workers`.

#### Step 5. Lower Per-Query Demand

Lower `max_parallel_workers_per_gather` in the lab and repeat. Compare total throughput and session p95 latency.

### Lab 5. Observing CPU Quota/Throttling

#### Step 1. Choose a Container Lab Environment

Use a dedicated container with a controllable low CPU limit. Never alter production database quotas.

#### Step 2. Record CPU Limit

In Linux cgroup v2, read `cpu.max`, `cpu.stat`, and `cpuset.cpus.effective` for the container running PostgreSQL.

#### Step 3. Run a CPU-Bound Workload

Run the lab scan/aggregate query with low workers per Gather, then increase gradually. Collect query latency, CPU usage, and throttled periods/time.

#### Step 4. Cross-Check

If CPU throttling rises alongside query latency, test reducing workers or concurrency. Do not simply raise `max_parallel_workers`.

#### Step 5. Save Results

Record CPU quota, cpuset, worker count, concurrent query count, throttling, and throughput. Compare before and after.

### Lab 6. Parallel Maintenance

#### Step 1. Create a Lab Index

```sql
CREATE INDEX parallel_lab_bucket_idx
ON parallel_lab(bucket);
```

#### Step 2. Rebuild the Index

In a disposable cluster, run:

```sql
REINDEX INDEX parallel_lab_bucket_idx;
```

#### Step 3. Test Maintenance Workers

Check `max_parallel_maintenance_workers` and global worker pool limits. If supported, compare the operation across different worker settings.

#### Step 4. Monitor Side Effects

Measure CPU, I/O, WAL generation, disk space, replication lag, and application latency. Do not run multiple large index builds simultaneously without a capacity plan.

### Lab 7. Clean Up the Environment

```sql
DROP FUNCTION IF EXISTS parallel_lab_upper(text);
DROP TABLE IF EXISTS parallel_lab;
```

Clean up only lab-created objects. Restore altered session/global settings and verify no lab workloads remain running.

## 19. Sizing Examples and Configuration Decisions

### 19.1. 16-CPU Analytics Server

Suppose a database actually has 16 allocated CPUs and the workload is mainly 2–3 concurrent analytics queries plus some maintenance jobs. You can start by testing 2–4 workers per Gather, global parallel workers sized for target concurrency, and leaving CPU headroom. Measure before increasing.

### 19.2. 4-CPU PostgreSQL OLTP

For a latency-sensitive OLTP workload on 4 CPUs, many small queries rarely benefit from parallel execution. Keep per-Gather low or 0 for the OLTP role if benchmarks show better tail latency; reserve bounded workers for reporting.

### 19.3. Kubernetes Pod Limited to 2 CPUs

If a Pod only has a 2-CPU quota, 8 workers per Gather will severely oversubscribe CPU. Start with low parallelism, monitor throttling, p95/p99, and concurrency. Do not treat CPU request as a hard cap when the limit differs.

### 19.4. Dedicated Reporting Replica

A dedicated reporting replica can allow higher per-query parallelism since it does not compete directly with the write primary. Still monitor CPU, I/O, replay lag, recovery conflicts, and synchronous/HA policies.

### 19.5. Index Build Maintenance Window

During a maintenance window, you can increase maintenance workers if CPU/storage have headroom. When application traffic returns to peak, restore stricter limits to avoid contention.

### 19.6. No Universal Configuration Exists

Two servers with the same CPU count can still need different configurations due to differences in storage, NUMA, CPU generation, cgroup quotas, query shapes, cache hit ratios, memory, concurrency, and SLAs.

## 20. Common Mistakes

### 20.1. More Workers Always Means Faster

Workers have diminishing returns and can overload CPU, memory, I/O, gather queues, and context switching. Benchmark at realistic concurrency.

### 20.2. Confusing Worker Count with CPU Count

A worker is a process; a CPU is a scheduling resource. You can have more workers than CPUs, yet they will time-share and contend for quota.

### 20.3. Only Increasing max_parallel_workers_per_gather

Global limits, worker slots, CPU quotas, memory, and background workers still constrain execution. Raising a per-query cap alone creates no extra capacity.

### 20.4. Ignoring max_worker_processes

The parallel worker pool draws slots from the background worker pool. Setting the global parallel cap higher than available worker slots cannot launch more processes.

### 20.5. Confusing max_connections with Worker Capacity

Client backend connections and background worker processes are two separate pools. Raising `max_connections` does not fix worker allocation.

### 20.6. Assuming Workers Planned Guarantees Running Workers

It is only a planner target. `Workers Launched` reflects actual execution and can be lower when the global pool is busy.

### 20.7. Using a Single-Query Benchmark to Represent Production

An isolated query may get all requested workers; production concurrency creates contention for worker slots and CPU. Benchmark with a realistic workload mix.

### 20.8. Ignoring Parallel Safety

An unsafe function/extension can prevent a query from parallelizing. Never mark a function SAFE if it has side effects or depends on session state.

### 20.9. Confusing IMMUTABLE with PARALLEL SAFE

Volatility and parallel safety are separate attributes. `IMMUTABLE` does not automatically prove a function can run in workers.

### 20.10. Using Force Parallel to Fix Queries

Forcing the planner does not fix missing indexes, bad statistics, poor join orders, or I/O bottlenecks. Diagnose the plan first.

### 20.11. Setting parallel_setup_cost Too Low

The planner may parallelize tiny queries, increasing startup overhead and worker churn.

### 20.12. Setting parallel_tuple_cost Too Low

The planner may pick plans that gather too many tuples, creating a leader bottleneck.

### 20.13. Ignoring Statistics

Inaccurate row estimates can make the planner choose poor parallel plans or skip parallel plans when they would help. Run `ANALYZE` and compare estimates vs. actuals.

### 20.14. Counting work_mem Once per Query

Multiple plan nodes and parallel processes can each allocate memory. Budget by active operations and concurrency, not a single process.

### 20.15. Ignoring Temp Spills

Parallel sorts/hashes can spill many temporary files simultaneously. Monitor temp I/O and temp filesystems.

### 20.16. Adding Workers When Storage Is Saturated

If I/O bandwidth is exhausted, more workers only increase queue depth and latency. Check disk throughput and latency.

### 20.17. Ignoring Leader Gather Bottlenecks

The leader must consume tuples and execute final nodes. Faster workers will not help if leader/gather is the bottleneck.

### 20.18. Raising Workers on Low-CPU-Limit Containers

PostgreSQL does not automatically scale worker counts to cgroup quotas in every setup. Tune to your real CPU budget and monitor throttling.

### 20.19. Confusing CPU Request with CPU Limit

A Kubernetes request is a scheduling reservation/relative share; a limit is a hard quota. Inspect both.

### 20.20. Looking Only at CPU Usage and Ignoring Throttling

A container can be throttled by its quota even when average usage is below 100%. Inspect cgroup `cpu.stat` / container throttling metrics.

### 20.21. Looking Only at Load Average

Load average can include I/O waits. Use run queue, CPU utilization, iowait, PSI, and process-level metrics.

### 20.22. Tuning Many Settings at Once

You cannot tell which setting caused the change. Test one setting at a time, keep baselines, and maintain clear rollbacks.

### 20.23. Running EXPLAIN ANALYZE on Unsafe DML/DDL

`EXPLAIN ANALYZE` executes the statement. Understand side effects, transaction rollback behavior, and lock impact before running.

### 20.24. Running Lab Stress Tests on Production

Stress queries can saturate CPU, I/O, and worker pools. Use disposable/staging environments and bound concurrency.

### 20.25. Ignoring Maintenance Contention

Parallel index builds compete with `SELECT` workloads for worker slots, CPU, and I/O. Schedule and limit maintenance workers.

### 20.26. Ignoring p95/p99

One faster query does not improve the application if OLTP tail latency worsens. Track the full latency distribution.

### 20.27. Not Monitoring Background Workers

Logical replication and extension workers consume `max_worker_processes` capacity. Include them in your worker budget.

### 20.28. Ignoring Replication Lag

CPU/I/O pressure can slow standby replay. Parallel maintenance/reporting can impact HA.

### 20.29. Pinning Workers Arbitrarily

Improper CPU affinity/NUMA pinning can degrade memory locality and scheduling. Only change after benchmarking on real hardware.

### 20.30. Skipping Rollback Plans

Every change needs a baseline, owner, rollout window, and rollback procedure. Keep previous configurations ready to restore if latency or resource pressure degrades.

## 21. Practice Exercises

### Exercise 1. Concepts

What is PostgreSQL parallel query? How does it differ from distributed query execution?

### Exercise 2. Process Roles

Distinguish leader backend, parallel worker, background worker, and client connection.

### Exercise 3. Gather

How do the roles of `Gather` and `Gather Merge` differ?

### Exercise 4. Worker Allocation

What do `Workers Planned` and `Workers Launched` mean? Why can the two numbers differ?

### Exercise 5. Parallel Safety

Distinguish `PARALLEL SAFE`, `PARALLEL RESTRICTED`, and `PARALLEL UNSAFE`.

### Exercise 6. Function Properties

Why does `IMMUTABLE` not automatically mean a function is `PARALLEL SAFE`?

### Exercise 7. Worker Limits

Distinguish `max_worker_processes`, `max_parallel_workers`, and `max_parallel_workers_per_gather`.

### Exercise 8. Maintenance

Which operations does `max_parallel_maintenance_workers` apply to? Does it have an independent process pool?

### Exercise 9. Planner Thresholds

How do `min_parallel_table_scan_size` and `min_parallel_index_scan_size` influence the planner?

### Exercise 10. Cost

What kinds of overhead do `parallel_setup_cost` and `parallel_tuple_cost` represent?

### Exercise 11. Leader Participation

What does `parallel_leader_participation` control? When can the leader become a gather bottleneck?

### Exercise 12. CPU Quota

A container has `cpu.max` set to `200000 100000`. Roughly how many CPU equivalents is the CPU quota?

### Exercise 13. Kubernetes

Distinguish `resources.requests.cpu` and `resources.limits.cpu`.

### Exercise 14. Worker Demand

There are 3 concurrent queries, each requesting 2 workers plus a leader. Estimate the parallel execution process count if all workers are granted.

### Exercise 15. Oversubscription

Why can 20 parallel workers in a container with a 4-core CPU limit worsen latency?

### Exercise 16. Memory

Why can adding workers raise memory demand even when `work_mem` stays unchanged?

### Exercise 17. I/O

Give two scenarios where a parallel scan does not speed up a query due to storage.

### Exercise 18. EXPLAIN

In `EXPLAIN ANALYZE`, which indicators should you check to evaluate a parallel plan?

### Exercise 19. Monitoring

Which view helps observe parallel workers and `leader_pid`? Name OS/container metrics to monitor.

### Exercise 20. CPU Throttling

A query gets all planned `Workers Launched`, yet latency increases alongside throttled periods. What should you investigate/adjust?

### Exercise 21. Parallel Maintenance

Why can parallel `CREATE INDEX` impact OLTP queries?

### Exercise 22. Non-Parallel Queries

List at least four reasons a query plan might not contain `Gather`.

### Exercise 23. Worker Launch Shortage

`Workers Planned` is 4, `Workers Launched` is 1. List the categories of causes to check.

## 22. Exercise Solutions

### Answer 1. Concepts

Parallel query splits a query plan into parts executed concurrently by a leader and parallel workers on the same PostgreSQL instance. Distributed query execution spreads work across multiple database servers/nodes; core parallel workers do not create a distributed database.

### Answer 2. Process Roles

- Leader backend: process serving the client, coordinating the parallel query, and collecting results.
- Parallel worker: background worker executing part of a parallel plan.
- Background worker: broader group of background processes, including logical replication, extension, and parallel workers.
- Client connection: application connection creating a backend session; not a worker slot.

### Answer 3. Gather

`Gather` collects tuples from leader/workers without preserving overall ordering. `Gather Merge` merges sorted streams to preserve plan ordering.

### Answer 4. Worker Allocation

`Workers Planned` is the count the planner expects to request; `Workers Launched` is the count actually started. They differ when the global pool is busy, `max_worker_processes` lacks slots, background workers occupy capacity, or OS/process resources are insufficient.

### Answer 5. Parallel Safety

- SAFE: allowed to run in parallel workers.
- RESTRICTED: runs only in the leader, never in workers.
- UNSAFE: the query cannot run in parallel mode.

### Answer 6. Function Properties

`IMMUTABLE` describes volatility semantics (the function does not alter or depend on changing database state for given arguments). `PARALLEL SAFE` describes whether it can run in a parallel context without side effects or race conditions. The two attributes test different properties.

### Answer 7. Worker Limits

- `max_worker_processes`: server-wide ceiling on background worker processes.
- `max_parallel_workers`: cluster-wide ceiling on parallel workers.
- `max_parallel_workers_per_gather`: ceiling on workers for one `Gather`/`Gather Merge` node.

Parallel workers must satisfy both the global parallel cap and available background worker slots.

### Answer 8. Maintenance

`max_parallel_maintenance_workers` controls workers for supported maintenance operations such as certain index builds/reindexes. It does not have an independent process pool; workers still draw from `max_worker_processes` and global parallel capacity.

### Answer 9. Planner Thresholds

These two parameters set minimum sizes before the planner considers parallel table scans or index scans. Lower thresholds let the planner consider parallelism on smaller relations; too low can cause unnecessary startup overhead.

### Answer 10. Cost

`parallel_setup_cost` estimates startup/coordination overhead of parallel workers. `parallel_tuple_cost` estimates the cost of transferring tuples from workers to the leader.

### Answer 11. Leader Participation

`parallel_leader_participation` determines whether the leader participates in the parallel subtree or primarily gathers results. The leader can become a bottleneck when workers generate tuples faster than the leader can receive/consume them and execute final plan nodes.

### Answer 12. CPU Quota

A quota of 200000 microseconds in a 100000-microsecond period equals roughly 2 CPU equivalents.

### Answer 13. Kubernetes

`resources.requests.cpu` is used for scheduling reservation and relative CPU share/weight; `resources.limits.cpu` sets a hard quota that triggers throttling when reached.

### Answer 14. Worker Demand

There are 3 leaders and 3 × 2 = 6 parallel workers, totaling roughly 9 processes in parallel execution, excluding background processes and other workloads.

### Answer 15. Oversubscription

20 workers on 4 CPU equivalents create many runnable processes competing for CPU time. This increases context switching, queueing, and throttling; latency can worsen despite higher worker counts.

### Answer 16. Memory

Sort/hash operations have per-process/per-operation memory budgets. More workers mean more operations running simultaneously; multiple plan nodes and concurrent queries amplify total memory demand and temp spills.

### Answer 17. I/O

Examples:

- Storage bandwidth/IOPS is already saturated; extra workers only increase queue depth.
- The working set is not in cache and random reads wait on storage latency; adding workers does not make the device faster.

### Answer 18. EXPLAIN

Inspect `Gather`/`Gather Merge`, `Workers Planned`/`Launched`, `Parallel Scan`/`Append`/`Partial Aggregate`, actual rows/time/loops, per-worker skew, buffers, temp I/O, planning/execution time, and settings.

### Answer 19. Monitoring

`pg_stat_activity` with `backend_type` and `leader_pid` helps observe leader/parallel workers on supported versions. OS/container metrics include CPU usage, run queue, throttling, quota, cpuset, context switches, iowait, PSI, memory, and temp I/O.

### Answer 20. CPU Throttling

Check `cpu.max`/CPU limit, `cpu.stat` throttled periods/time, cpuset, concurrent query count, and runnable processes. Lower `max_parallel_workers_per_gather`/concurrency or increase CPU limit/request if capacity allows; re-benchmark.

### Answer 21. Parallel Maintenance

`CREATE INDEX` can consume substantial CPU, memory, worker slots, and storage bandwidth. This forces OLTP backends to wait on CPU/I/O and can elevate latency.

### Answer 22. Non-Parallel Queries

Examples:

- `PARALLEL UNSAFE` function/expression.
- Table scan smaller than threshold.
- Planner costs do not favor a parallel plan.
- `max_parallel_workers_per_gather = 0`.
- Unsupported worker/plan node.
- Stale statistics/wrong row estimates.
- Restricted lock/temporary/session semantics in the query.

### Answer 23. Worker Launch Shortage

Check `max_parallel_workers`, available slots in `max_worker_processes`, background workers, concurrent parallel queries, process limits, resource exhaustion, and logs.

### Answer 24. Tuning Methodology

Changing one setting at a time isolates cause and effect. Benchmarking at realistic concurrency captures worker pool, CPU, memory, and I/O contention that single-query benchmarks miss.

### Answer 25. Design

An experimental policy:

1. Confirm 8 CPUs are actual capacity, not host cores exceeding container quota.
2. Reserve CPU headroom for WAL/checkpoints/autovacuum/OS and OLTP.
3. Limit the OLTP role to `max_parallel_workers_per_gather=0` or `1` if benchmarks show lower tail latency.
4. Give the analytics role 2 workers per Gather as a starting point; raise to 3–4 only if CPU/I/O headroom remains.
5. Set `max_parallel_workers` to match expected analytics concurrency without exceeding worker slots/capacity.
6. Size `max_worker_processes` for parallel, logical replication, and extension workers with modest headroom.
7. Schedule parallel maintenance off-peak and keep `max_parallel_maintenance_workers` low during busy OLTP hours.
8. Monitor CPU throttling, worker launches, p95/p99, temp spills, I/O, memory, and replication lag.
9. Test in staging, roll out canary, compare before/after, and keep a rollback config.

Exact numbers must be validated with representative workload benchmarks and real concurrency.

## 23. Parallel Query Operational Checklist

### 23.1. Capacity

1. Are CPU quota/cpuset confirmed from the OS/container?
2. Are background workloads and CPU headroom included?
3. Does concurrent worker demand fit capacity?
4. Do memory and temp filesystems accommodate sort/hash workers?
5. Does storage bandwidth/IOPS have remaining headroom?

### 23.2. PostgreSQL Settings

6. Is `max_worker_processes` large enough for all background workers?
7. Does `max_parallel_workers` match total CPU/worker budget?
8. Is `max_parallel_workers_per_gather` appropriate per workload class?
9. Is `max_parallel_maintenance_workers` bounded per maintenance window?
10. Are planner thresholds/costs validated by benchmarks?
11. Is parallel safety correct on functions/extensions?

### 23.3. Query Plans

12. Do key queries have baseline `EXPLAIN ANALYZE` plans?
13. Are `Workers Planned` and `Workers Launched` compared?
14. Are actual rows/estimates and worker skew checked?
15. Are gather overhead, buffers, and temp spills inspected?
16. Are indexes/partitioning/statistics checked before raising workers?

### 23.4. Monitoring

17. Are active parallel workers and leader sessions monitored?
18. Are CPU usage, throttling, run queue, and iowait tracked?
19. Are p95/p99 latency and throughput tracked per query class?
20. Are memory pressure/temp files/IOPS monitored?
21. Are replication lag and maintenance activity monitored?

### 23.5. Change Management

22. Are baseline and config snapshots saved before tuning?
23. Are settings changed one at a time and tested in staging?
24. Is there a realistic concurrency benchmark?
25. Are a rollback procedure and owner defined?
26. Are peak/off-peak periods verified after rollout?

## 24. Runbook: Tuning or Handling Parallel Worker Pressure

### Step 1. Identify Impact

Record affected query classes, timestamps, p95/p99, throughput, CPU, I/O, and replication lag. Determine whether the impact is server-wide or isolated to one query.

### Step 2. Determine Real CPU Capacity

Read container CPU limits/requests, cgroup quota/cpuset, or systemd settings. Compute effective CPU budget and check throttling.

### Step 3. Determine Worker Demand

Use `pg_stat_activity`, `EXPLAIN` samples, and concurrency to estimate active leaders/workers. Check global caps and background worker usage.

### Step 4. Inspect the Plan

Capture `EXPLAIN ANALYZE` safely. Inspect parallel nodes, workers planned/launched, row estimates, skew, gather, buffers, and temp I/O.

### Step 5. Select Remediation

- Reduce per-query workers/concurrency if CPU is oversubscribed.
- Increase CPU quota/capacity if feasible and workload needs throughput.
- Fix statistics/indexes/query shape if the plan is poor.
- Reduce memory pressure/temp spills.
- Separate analytics workloads or reschedule maintenance.

### Step 6. Make Controlled Changes

Test in staging/session/role first. Save old config and change one setting at a time. Restart only when required by the parameter.

### Step 7. Re-Measure

Compare query latency, throughput, CPU/throttling, I/O, memory, worker launches, and replication lag.

### Step 8. Roll Back if SLAs Degrade

Restore old settings or reduce parallelism/concurrency. Verify workloads return to baseline and document results.

## 25. Summary

PostgreSQL parallel query enables a leader backend and parallel workers to execute eligible parts of a query plan concurrently. `Gather` collects tuples; `Gather Merge` merges sorted streams. Parallel scans, append, aggregation, joins, and certain maintenance operations can leverage workers when plans, query semantics, and resource limits permit.

Key principles:

- Parallel queries run within a single PostgreSQL instance; they do not create distributed query execution.
- `PARALLEL SAFE`, `PARALLEL RESTRICTED`, and `PARALLEL UNSAFE` determine whether functions/operations can run in workers.
- `max_worker_processes`, `max_parallel_workers`, and `max_parallel_workers_per_gather` control different layers of worker capacity.
- `Workers Planned` is the planner target; `Workers Launched` is the runtime reality.
- Planner costs/thresholds decide whether a parallel plan is worthwhile; statistics and query shape drive that choice.
- CPU quotas/cpuset/Kubernetes limits govern actual CPU; worker count does not guarantee CPU cores.
- Multiple concurrent queries can oversubscribe CPU and worker slots.
- Parallel workers can amplify memory usage, temp I/O, and storage contention.
- Leader/gather overhead, skew, I/O, and CPU throttling can cap speedup.
- Tuning requires benchmarking at realistic concurrency, measuring p95/p99, and keeping headroom for OLTP/HA/background work.
- Parallel maintenance must be scheduled and bounded so it does not impact applications.
- Monitoring must combine PostgreSQL views, `EXPLAIN`, OS/container metrics, and replication health.

Guiding rule:

> **Size worker counts to your real CPU budget and concurrency; measure plans and resource pressure before increasing parallelism.**

## 26. References

Choose documentation matching your running PostgreSQL major version, as parallel capabilities and configuration details evolve across releases:

- [PostgreSQL Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html): `Gather`/`Gather Merge`, parallel scans, joins, and aggregation.
- [How Parallel Query Works](https://www.postgresql.org/docs/current/how-parallel-query-works.html): leader, workers, and tuple gathering.
- [When Can Parallel Query Be Used?](https://www.postgresql.org/docs/current/when-can-parallel-query-be-used.html): planner conditions and parallel safety.
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html): SAFE/RESTRICTED/UNSAFE function classification.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): worker process limits, `work_mem`, and maintenance memory.
- [Query Planning Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html): planner costs, thresholds, and parallel settings.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and statistics views.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query workload statistics.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): execution plans and ANALYZE/BUFFERS/SETTINGS.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): parallel index build considerations.
- [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): vacuum options and maintenance behavior.
- [Linux cgroup v2 CPU Controller](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, `cpu.weight`, and `cpuset`.
- [Docker CPU constraints](https://docs.docker.com/engine/containers/resource_constraints/): container CPU quota/cpuset.
- [Kubernetes Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests, limits, memory, and QoS.
- [systemd.resource-control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html): `CPUQuota`, `CPUWeight`, and `AllowedCPUs`.


### Exercise 24. Tuning Methodology

Why should you change one setting at a time and benchmark under realistic concurrency?

### Exercise 25. Design

Design a parallelism policy for an 8-CPU-core PostgreSQL server running OLTP and analytics concurrently. Specify worker limits, role settings, CPU headroom, monitoring, and rollout.
