# BUFFERS, WAL, SETTINGS, and JSON Format

A PostgreSQL query takes 800 ms. Looking at `Execution Time` alone is not enough to know whether it is slow because it scans too many data pages, spills memory to temporary files, generates excessive WAL, uses a planner setting different from the test environment, or simply because the cache is cold. Especially when two runs of the same SQL yield different timings, reading only `cost=...` and `rows=...` usually cannot explain why.

PostgreSQL provides extended options for `EXPLAIN`:

- **`BUFFERS`:** reports buffer block accesses via shared buffers, local buffers, and temp blocks; helps analyze caching and I/O at the executor level.
- **`WAL`:** reports WAL records, full-page images, and WAL bytes generated during execution; particularly useful for `INSERT`, `UPDATE`, and `DELETE`.
- **`SETTINGS`:** includes configuration parameters **affecting planning** whose values differ from built-in defaults in the output, aiding comparison across two environments.
- **`FORMAT JSON`:** emits the plan tree as structured JSON data instead of indented text, convenient for tools, scripts, and analysis pipelines.

These options are often combined:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT *
FROM some_table
WHERE id = 42;
```

In the example above, `some_table` is an illustrative name; the lab section below provides runnable tables. **`ANALYZE` causes the SQL statement to actually execute**, not merely be predicted. If the SQL is a data-modifying command, its side effects can occur. That is the most important distinction before using these options.

This lesson covers **syntax**, **reading metrics**, **measurement limitations**, **a reproducible lab**, **parsing JSON with Java/JDBC**, and **a diagnostic workflow**.

> **Scope and safety:** Examples use modern PostgreSQL. JSON field names, instrumentation details, and option support may vary between versions. Run `EXPLAIN ANALYZE` on insert/update/delete commands in a lab database or a transaction with a clear rollback plan; never run them directly on production data just to inspect a plan.

## 1. What Questions Does EXPLAIN Answer?

`EXPLAIN` displays the **execution plan** PostgreSQL chooses for a statement: how tables are scanned, which indexes are used, which join algorithms run, where sorting/aggregation occurs, estimated row counts, and relative costs.

```sql
EXPLAIN
SELECT *
FROM pg_catalog.pg_class
WHERE relname = 'pg_class';
```

This is **plan-only**: it mainly shows planner estimates without measuring row counts, timings, and buffer usage from an actual query execution.

When adding:

```sql
EXPLAIN (ANALYZE)
SELECT *
FROM pg_catalog.pg_class
WHERE relname = 'pg_class';
```

PostgreSQL runs the real SELECT to measure metrics such as:

- `actual time`: observed timing at the node.
- `actual rows`: actual rows emitted by the node per node-reporting semantics.
- `loops`: number of times the node was invoked/executed.
- `Planning Time` and `Execution Time` when displayed.

With `BUFFERS` and `WAL`, you also get visibility into **how many data pages were touched** and **how much WAL data was generated**.

### EXPLAIN Is Not an All-Purpose SQL Profiler

It **does not automatically provide**:

- A full breakdown of application time including HTTP, serialization, network, and UI rendering.
- Exact CPU time per node.
- A list of all physical files read by the OS on disk.
- The root cause of every lock wait or OS-layer I/O wait.
- A multi-run execution history for a SQL query.
- An automatic verdict on which index or setting is optimal.

`EXPLAIN` is one piece of performance investigation, not the whole picture.

## 2. Summary of Key Options

| Option | Main question | Notes |
|---|---|---|
| `ANALYZE` | When executed, how long does it actually take and how many rows are produced? | **Actually executes the SQL statement**. |
| `BUFFERS` | How many buffer blocks were hit/read/dirtied/written, and how many temp blocks? | Usually paired with `ANALYZE` to observe the executor. |
| `WAL` | How many WAL records/FPIs/bytes did execution generate? | Paired with `ANALYZE`; especially useful for DML. |
| `SETTINGS` | Which planner-relevant GUCs differ from built-in defaults? | Not the output of `SHOW ALL`. |
| `FORMAT JSON` | What does the plan tree look like as structured data? | Top-level is typically a **JSON array**. |
| `FORMAT TEXT` | Human-readable plan in the terminal. | Default `EXPLAIN` format. |
| `VERBOSE` | Shows extra output columns, schema names, and plan details. | Can make plans long. |
| `TIMING OFF` | Reduces per-node timing overhead while keeping rows/loops. | Used with `ANALYZE`. |
| `SUMMARY` | Whether to display summary info such as planning/execution time. | Display setting; does not alter SQL logic. |
| `COSTS OFF` | Hides estimated cost/rows/width in output. | Does not mean the planner stopped using costs. |

A convenient combined command for investigation:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    VERBOSE,
    FORMAT TEXT
)
SELECT 1;
```

It is valid for a trivial SELECT, though buffer/WAL figures may be tiny or zero. For meaningful analysis, use data and queries with enough work to measure.

### When Is ANALYZE Not Needed?

If you only want to inspect plan choice and are not permitted to execute the SQL:

```sql
EXPLAIN (SETTINGS, FORMAT JSON)
SELECT *
FROM pg_catalog.pg_class
WHERE oid = 1259;
```

An estimated plan lacks `Actual Rows`/`Actual Loops` or runtime WAL counters. Do not infer from a plan-only output that a query is guaranteed to run at a specific speed.

## 3. Lab Dataset Used Throughout

Create the schema and sample tables:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_plan_metrics;

CREATE TABLE lesson_plan_metrics.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_plan_metrics.sales (
    sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson_plan_metrics.customers(customer_id),
    sold_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'REFUNDED')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    note TEXT NOT NULL
);
```

Generate 1,000 customers and 30,000 synthetic sales:

```sql
INSERT INTO lesson_plan_metrics.customers (
    customer_id,
    customer_name
)
SELECT
    g,
    'Customer ' || g
FROM generate_series(1, 1000) AS g;

INSERT INTO lesson_plan_metrics.sales (
    customer_id,
    sold_at,
    status,
    amount,
    note
)
SELECT
    1 + (g % 1000),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 minute',
    CASE WHEN g % 10 = 0
         THEN 'REFUNDED'
         ELSE 'PAID'
    END,
    ((g % 5000) + 1)::numeric / 100,
    repeat('x', 100) || '-' || g::text
FROM generate_series(1, 30000) AS g;
```

The synthetic data is uniformly distributed and easy to reason about. It **does not reflect production data** with skew, real event timing, or realistic row widths.

### Create Indexes for Comparison

```sql
CREATE INDEX ix_sales_customer_recent
ON lesson_plan_metrics.sales (
    customer_id,
    sold_at DESC
);

CREATE INDEX ix_sales_status
ON lesson_plan_metrics.sales (status);

ANALYZE lesson_plan_metrics.customers;
ANALYZE lesson_plan_metrics.sales;
```

`ANALYZE` here is the SQL command collecting planner statistics for tables, **distinct from the `ANALYZE` option inside `EXPLAIN`**.

### Questions to Keep in Mind Before Viewing Output

No numeric output from this lab is guaranteed to be identical across machines. Buffer hits, page reads, plan nodes, and timings depend on:

- PostgreSQL version and configuration.
- Table size, statistics, and cache state.
- Operating system, RAM, and storage.
- Queries running beforehand and concurrently.
- Checkpoints, autovacuum, system load, and parallel workers.

Therefore, output examples in this lesson are **illustrative**, not a promise that you will observe exact matching numbers.

## 4. Anatomy of a TEXT Execution Plan

Query:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT TEXT
)
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

A simplified illustrative output:

```text
Limit  (cost=0.29..12.10 rows=5 width=22)
       (actual time=0.020..0.065 rows=5 loops=1)
  Buffers: shared hit=4 read=2
  -> Index Scan using ix_sales_customer_recent on sales
       (cost=0.29..120.00 rows=30 width=22)
       (actual time=0.018..0.061 rows=5 loops=1)
       Index Cond: (customer_id = 42)
       Buffers: shared hit=4 read=2
Planning:
  Buffers: shared hit=15
Planning Time: 0.180 ms
Execution Time: 0.090 ms
```

Analysis:

1. **`Limit`:** node returning at most five rows.
2. **`Index Scan`:** uses the index aligned with `customer_id` and `sold_at DESC` ordering.
3. **`cost=...`:** planner's relative estimate, **not milliseconds**.
4. **`rows=30`:** planner's row estimate on the source node.
5. **`actual rows=5`:** in practice the node only had to produce five rows before `LIMIT` stopped scanning.
6. **`loops=1`:** the node executed once in this example.
7. **`shared hit/read`:** counts blocks found in shared buffer cache versus blocks brought in through the buffer read path.
8. **`Planning Time`:** measured time spent building the plan.
9. **`Execution Time`:** measured execution time for the statement.

**Do not add `Buffers` from Limit and Index Scan together.** A plan node's counters generally reflect cumulative activity across the node and its descendants as instrumented. A parent already includes child work.

## 5. What Does BUFFERS Count?

A buffer block is the data unit PostgreSQL manages in its buffer manager, typically corresponding to one database page. PostgreSQL commonly uses an **8 KiB** page size on many builds, though tooling should never hardcode this assumption.

Check it:

```sql
SHOW block_size;
```

or:

```sql
SELECT
    current_setting('block_size')::integer AS block_bytes;
```

With `BUFFERS`, the key counter groups are:

| Group | Common counters | Usage source |
|---|---|---|
| **Shared** | `hit`, `read`, `dirtied`, `written` | Table/index pages using the shared buffer pool. |
| **Local** | `hit`, `read`, `dirtied`, `written` | Local buffers for temporary relations. |
| **Temp** | `read`, `written` | Blocks in temp files used by operations like sort/hash spills. |

Text output typically omits zero counters to stay concise; hence not seeing a `temp` line **does not mean the server never used temp files** overall, only that none were recorded within the measured plan scope.

### Example BUFFERS Line

```text
Buffers: shared hit=150 read=20 dirtied=3 written=2,
         local hit=5 read=1,
         temp read=80 written=120
```

How to read it:

- 150 page lookups satisfied from shared buffers.
- 20 page loads requested into shared buffers via the read path.
- 3 blocks transitioned from clean to dirty within the instrumented scope.
- 2 dirty blocks written out by this backend as accounted.
- Temporary relation accesses tracked via local buffer counters.
- Temp working files used during query processing incurred 80 block reads and 120 block writes.

Do not convert those numbers directly into **MB read straight from SSD** without considering caching, block size, node loops, and the OS.

## 6. Shared Hit Blocks: What Does "hit" Mean?

`shared hit=1000` means there were **1,000 page lookups** where the needed page was already in the **PostgreSQL shared buffer pool**, requiring no new page load into the pool for that reference.

It **does not mean**:

- The query read exactly 1,000 **distinct** pages.
- PostgreSQL holds exactly 1,000 pages in RAM.
- The server-wide cache hit ratio is 100%.
- All data was served from CPU cache.

The same page can be accessed multiple times, especially with Nested Loops, repeated index lookups, or multi-loop nodes.

### Is a High Shared Hit Good or Bad?

It depends on the goal. A query reading 2 million blocks from cache can still burn heavy CPU and memory bandwidth, whereas a query reading 50 blocks from storage can be blazingly fast on modern hardware.

**High hits alone do not prove an efficient plan.** Also examine:

- Final rows required.
- Total blocks touched.
- Scan/join types and loop counts.
- Execution Time relative to SLOs.
- Gap between estimated and actual rows.

## 7. Shared Read Blocks: "read" Is Not Always a Physical Disk Read

`shared read=500` means 500 times a page had to be fetched through the buffer read path because it was not already in PostgreSQL shared buffers.

**Crucially:** the page may already reside in the operating system's **OS page cache**. Therefore, `shared read` is not equivalent to:

```text
500 physical SSD/HDD accesses
```

It tells you the page **was not present in the PostgreSQL shared buffer pool** at lookup time and was loaded via the read path. Whether it hit physical storage or returned from OS cache happens below PostgreSQL.

### Two Different Runs

```text
Run 1:
  shared hit = 100
  shared read = 900
  Execution Time = 140 ms

Run 2:
  shared hit = 980
  shared read = 20
  Execution Time = 35 ms
```

These are hypothetical numbers. One interpretation is that run 1 **warmed the cache**, while run 2 reused buffers. Concluding for sure requires checking workload, plan shape, row counts, I/O timing, and concurrency.

### A Warm Cache Does Not Guarantee Consistent Speed

Plans can also shift due to statistics, query parameters, changes to `work_mem`/`random_page_cost`, or prepared statement generic/custom plans. Do not attribute every timing difference solely to cache from two hit/read numbers.

## 8. Shared Dirtied Blocks and Shared Written Blocks

Two easily misunderstood counters:

- **`dirtied`:** a previously clean page was modified and marked dirty during the instrumented work.
- **`written`:** dirty pages written out by this backend itself within accounting scope.

### Dirtied Does Not Equal Rows UPDATED

One block can hold many rows. Updating 100 rows does not mean `dirtied=100`. A query can also modify index pages, visibility metadata, and other pages.

### Written Does Not Equal All Physical Writes Caused by the Transaction

PostgreSQL uses the **checkpointer**, background writer, and other write paths. Many dirty pages are written out **after the statement completes**, not necessarily by the backend executing that SQL.

Thus:

```text
Buffers: shared dirtied=500 written=0
```

does not mean "500 pages were never written to disk" or "the query caused zero write I/O." It only describes instrumentation within that execution.

### Reading Alongside WAL

An UPDATE might report:

```text
Buffers: shared hit=1000 dirtied=90 written=0
WAL: records=140 fpi=12 bytes=98000
```

This matches **data pages being modified**, with WAL records generated for recovery/replication. That dirty pages were not immediately flushed by the backend does not stop the transaction from generating WAL.

## 9. Local Buffers vs Temp Blocks

Similar names, different meanings:

**Local buffers** serve session-private temporary relations, such as temp tables:

```sql
CREATE TEMP TABLE tmp_sale_ids (
    sale_id BIGINT
);

INSERT INTO tmp_sale_ids(sale_id)
SELECT sale_id
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM tmp_sale_ids;
```

This may report `local hit/read/dirtied/written` depending on access and caching.

**Temp blocks** in EXPLAIN typically refer to **temporary working files** used by the executor for:

- External sorts when memory is insufficient.
- Hash joins/aggregates that batch or spill to disk.
- Certain materialization and temporary execution operations.

For example:

```text
Buffers: temp read=1200 written=1900
```

does not necessarily involve a `CREATE TEMP TABLE`; it can indicate a Sort node spilling to temp files.

### Asking the Right Debug Question

- See **local**: is the application reading/writing temporary relations?
- See **temp**: which sort/hash/materialize node used temp files, and how large/frequent was the spill?

Mixing the two concepts leads optimization in the wrong direction.

## 10. Temp Read/Write and work_mem

`work_mem` sets the memory limit per **eligible sort/hash operation**, not simply "each connection uses exactly that much RAM across all queries."

One query can have multiple sort/hash nodes; parallel workers and parameters like `hash_mem_multiplier` also affect total memory. Never raise `work_mem` server-wide solely because one query spilled.

### Example Creating a Large Sort

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

With 30,000 rows and small `work_mem`, Sort may spill:

```text
Sort
  Sort Key: (md5((sale_id)::text))
  Sort Method: external merge  Disk: 4500kB
  Buffers: shared hit=..., temp read=... written=...
```

The `Disk` figure and temp counters are **illustrative**, not fixed. Plans vary across versions, data, and configuration.

### Comparing with Larger work_mem

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

You may see `Sort Method: quicksort  Memory: ...` and temp reads/writes shrink or vanish. However:

- More memory **is not always faster** if the data already fits in memory.
- Higher `work_mem` can create severe RAM pressure under many concurrent sessions/plan nodes.
- Changing `work_mem` can cause the planner to pick a different plan.
- Some queries spill due to hash batching or wrong cardinality estimates, not merely a missing `work_mem` bump.

**The goal is addressing the root cause**, not blindly raising settings until temp blocks hit 0.

## 11. Converting Block Counts to Size

If `SHOW block_size` returns `8192` bytes:

```text
1 block = 8 KiB
1000 blocks = 1000 × 8192 = 8,192,000 bytes
            ≈ 7.8125 MiB
```

In SQL:

```sql
SELECT
    current_setting('block_size')::bigint AS bytes_per_block,
    1000::bigint *
        current_setting('block_size')::bigint
        AS estimated_bytes,
    pg_size_pretty(
        1000::bigint *
        current_setting('block_size')::bigint
    ) AS readable_size;
```

This is a **unit conversion of block accesses into bytes** for reading metrics, not proof the query transferred that exact volume from physical disk.

### Avoid Adding Shared Hit + Read and Calling It "Database Size"

`hit + read` can count the same page many times across repeated accesses. It is neither table size nor actual disk footprint.

To inspect the size of a table and its indexes:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size(
            'lesson_plan_metrics.sales'::regclass
        )
    ) AS total_relation_size;
```

That is an **object size** question, distinct from a statement's **buffer accesses**.

## 12. Node Counters Are Cumulative—Do Not Sum Arbitrarily

A simple tree:

```text
Limit
  Buffers: shared hit=10 read=2
  └── Index Scan
        Buffers: shared hit=10 read=2
```

If you sum:

```text
10 + 10 = 20 hits
2 + 2 = 4 reads
```

to infer the query total, you have **double-counted** the work reflected in both parent and child.

### Principle

Read node-level counters to **locate where work originates** in the plan tree, not by summing every node as if they were independent buckets.

- Parent nodes generally include descendant activity.
- Nested Loops can invoke children many times.
- Parallel nodes can carry worker-level counters.
- Planning buffers and execution buffers belong to separate scopes.

When comparing two plans, examine the **root** counters or appropriate summary, then drill down to see which nodes drive the majority of work. Do not assume root output covers background processes or work outside the executor.

## 13. Actual Rows, Loops, and the Difference Between Rows and Blocks

A plan node may display:

```text
Index Scan ... (actual time=0.004..0.007 rows=3 loops=1000)
Buffers: shared hit=3100
```

`rows=3` in per-loop metrics does not mean the node returned only three rows in total.

For a node executed multiple times, `actual rows` and `actual time` are typically reported as **averages per execution**, per PostgreSQL convention. An estimate of node output volume:

```text
3 rows/loop × 1000 loops ≈ 3000 rows
```

Meanwhile `Buffers` has its own cumulative accounting, and row/time figures can be rounded in text output.

### Nested Loops Often Drive High Buffer Hits

```text
Nested Loop
  ├── Seq Scan customers (1000 rows)
  └── Index Scan sales ... (loops=1000)
```

Each customer triggers a lookup into `sales`. Even when each lookup is cheap, total index page accesses can be substantial. This is a classic case for reading **loops alongside BUFFERS**, rather than glancing at a single index probe.

### Actual Time Cannot Be Added Directly Across Parent and Child

Node timing generally includes descendant execution time per instrumentation, so adding every `actual total time` double-counts. `Execution Time` at the bottom indicates overall measured plan execution time.

## 14. BUFFERS and Parallel Queries

When PostgreSQL chooses a parallel scan/aggregate/sort, the plan may show:

```text
Gather
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=... read=...
  └── Parallel Seq Scan
        Buffers: shared hit=... read=...
```

With `VERBOSE` or JSON format, **worker** breakdown entries may also appear.

### Things to Be Careful About

- Do not multiply `Buffers` on a parallel node by worker count simply because `Workers Launched=2` appears.
- Counters may already be aggregated by PostgreSQL across the node/worker scope.
- `Actual Rows` and `Loops` have observational semantics that must be read alongside worker details.
- Parallel elapsed time does not equal the sum of worker CPU times.
- Planned workers does not guarantee equal launched workers.

When extracting JSON, preserve worker arrays if you need to analyze bottlenecks between leader and workers. Do not look only at the root and guess which worker was slow.

## 15. BUFFERS During the Planning Phase

PostgreSQL sometimes reports buffer accesses under **Planning**:

```text
Planning:
  Buffers: shared hit=30 read=5
Planning Time: 0.320 ms
```

The planner may read system catalogs, statistics, index metadata, and related structures to construct a plan.

### Planning Buffers vs Execution Buffers

- **Planning:** cost of reading metadata/catalog info while planning.
- **Execution:** page accesses while running plan nodes.

Do not lump both scopes into one "table reads" figure and assume it all came from scanning business tables.

### Why Do Planning Buffers Sometimes Spike?

A query with many joins, partitioned tables, or related objects requires reading more metadata. Cold runs before catalog caches warm up must also read more pages.

To investigate slow planning, inspect query structure, table/partition counts, catalog/statistics state, and caching context. Do not tune `work_mem`, which primarily affects execution sort/hash operations.

## 16. When to Enable track_io_timing?

`BUFFERS` reports **block access counts**, yet **does not by itself report exact I/O wait time**.

PostgreSQL provides the `track_io_timing` parameter:

```sql
SHOW track_io_timing;
```

When enabled and supported by the platform, EXPLAIN can report I/O timings such as:

```text
I/O Timings: shared read=... write=...
```

Exact formatting depends on PostgreSQL version and tracked I/O categories.

### Why Is It Valuable?

Two queries can both report:

```text
shared read=10000
```

yet actual read latency can differ dramatically depending on OS cache, storage speed, contention, and environment.

### Overhead and Privileges

Measuring I/O timing adds overhead from clock sampling around I/O calls. Depending on the environment, changing this setting may require elevated privileges.

Do not toggle it server-wide in production just to inspect one query without checking operational guidance and overhead. `track_io_timing` aids diagnosis, though it does not replace OS/storage telemetry.

## 17. When BUFFERS Increase Yet Execution Time Does Not

A plan can touch many pages and still finish fast if data sits in cache or hardware has high throughput. Conversely, a plan with low reads can still be slow because of:

- CPU-heavy expressions or JSON processing.
- Expensive UDFs.
- Lock/LWLock contention.
- Complex sort/hash computations.
- Client/network waits or non-query overhead.
- Bad estimates leading to an expensive join strategy.

### Correct Reading Order

1. Check `Execution Time`.
2. Check `Actual Rows` and `Loops`.
3. Check `Buffers` on major nodes.
4. Check for temp spills.
5. Inspect I/O timings if enabled.
6. Cross-check `wait_event_type` and external workload.

**Never rely on a single counter to conclude "the query needs a new index."**

## 18. What Is WAL?

**Write-Ahead Log (WAL)** is the logging mechanism that records changes before data pages are required to be durable on disk under crash-recovery guarantees. PostgreSQL relies on WAL for crash recovery and compatible forms of replication/backup.

Conceptual model:

```text
Transaction updates data
              │
              ▼
     Generates WAL info
              │
              ▼
     WAL written/flushed per
     commit rules and config
              │
              ▼
     Data pages may be written
     to storage later
```

Crucially, **writing WAL and writing data pages are two separate cost paths**. Thus an `UPDATE` can generate many WAL bytes while showing `Buffers: shared written=0` at measurement time.

### WAL Is Not an Application Audit Log

WAL serves database recovery mechanics; it is not designed as a queryable business history table answering "who edited which field." If you need auditing, build history tables, triggers, event logs, or CDC per requirements.

## 19. What Does EXPLAIN (ANALYZE, WAL) Measure?

`WAL` in `EXPLAIN` reports **WAL generation** metrics within the instrumented execution scope.

Command:

```sql
EXPLAIN (ANALYZE, WAL)
SELECT 1;
```

on a simple SELECT usually generates negligible WAL, so WAL metrics may be zero or omitted when text format suppresses zero counters.

To see WAL clearly, run DML in the lab:

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS
)
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;

ROLLBACK;
```

**The UPDATE actually ran.** `ROLLBACK` reverts ordinary transactional data changes, yet **does not erase the WAL records already generated**; those WAL bytes can still be written and later recycled by WAL management.

### Safety Reminders for EXPLAIN ANALYZE DML

`EXPLAIN (ANALYZE)` runs:

- `INSERT`: actually inserts rows.
- `UPDATE`: actually updates rows.
- `DELETE`: actually deletes rows.
- Triggers, checks, and related transactional effects.

Wrapping in `BEGIN ... ROLLBACK` is a handy lab technique, yet **does not undo non-transactional or external effects**, such as:

- Sequence values allocated via `nextval()`.
- Emails/HTTP requests sent externally by apps/extensions.
- WAL already generated.
- Other external effects depending on extensions.

Only benchmark DML on production with approved safety controls; never assume rollback erases all costs.

## 20. Three Core WAL Numbers

Illustrative text output:

```text
WAL: records=250 fpi=16 bytes=180000
```

| Counter | Interpretation |
|---|---|
| **`records`** | Number of WAL records generated within instrumentation scope. |
| **`fpi`** | Number of **full-page images** (*FPI*) written in the associated WAL records. |
| **`bytes`** | Total WAL bytes generated as recorded for the measured operation. |

### Why Don't Records Equal Rows?

One UPDATE can:

- Create a new tuple version in the heap.
- Update one or more indexes.
- Touch other related pages.
- Fire triggers executing additional SQL.
- Perform distinct storage work depending on HOT vs non-HOT updates.

Hence `WAL records=250` **does not mean exactly 250 rows were modified**, and `WAL bytes` does not scale one-to-one with `amount` or user payload size.

### WAL Bytes Does Not Equal Table Growth

WAL is recovery/logging data; table files and indexes manage growth, space reuse, VACUUM, and checkpoints separately. A transaction generating heavy WAL might grow table files very little, or vice versa depending on context.

## 21. Full-Page Images (FPI) and Checkpoints

In common configurations, PostgreSQL enables **full-page writes** to protect against torn pages during crashes. After a checkpoint, the first modification to a page may require logging a **full-page image** into WAL.

Conceptual view:

```text
Checkpoint
     │
     ▼
Page P modified for the first time
     │
     └── WAL may include an FPI of P

Page P modified again in the same checkpoint cycle
     │
     └── May not need another FPI per modification
```

Consequence:

- Two identical UPDATEs on the same number of rows can produce **different `WAL FPI` and `WAL Bytes`**.
- Workloads running right after a checkpoint can see higher FPI counts.
- WAL/FPI compression and logging settings also affect byte totals.

**Do not conclude a query change made WAL worse from a single EXPLAIN run** if checkpoint timing, cache state, and table state differed.

### Full-Page Writes Are Not Full Database Copies

FPIs apply to specific modified pages under logging rules. Do not read `fpi=100` as PostgreSQL copying 100 tables or 100 transactions.

## 22. WAL During INSERT, UPDATE, and DELETE

The three DML types produce distinct WAL patterns:

### INSERT

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
INSERT INTO lesson_plan_metrics.sales (
    customer_id,
    sold_at,
    status,
    amount,
    note
)
VALUES (
    1,
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    'PAID',
    99.00,
    'EXPLAIN WAL demo'
);

ROLLBACK;
```

INSERT writes a tuple to the heap and updates associated indexes. In our lab there is an **identity sequence**; sequence numbers consumed will not rewind on transaction rollback.

### UPDATE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE lesson_plan_metrics.sales
SET amount = amount * 1.05
WHERE customer_id = 42
  AND status = 'PAID';

ROLLBACK;
```

UPDATE creates new tuple versions. If eligible for a **HOT update** with sufficient free page space, some index updates can be skipped; otherwise, updating indexed columns or lacking HOT eligibility increases WAL/index overhead.

### DELETE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
DELETE FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

ROLLBACK;
```

DELETE marks tuples per MVCC rules; it does not immediately shrink data files. `VACUUM` and space reclamation happen separately.

### Avoid Unfair WAL Bytes Comparisons

INSERTing 1 row, UPDATEing 30 rows, and DELETEing 30 rows represent different workloads. Normalize by row count, row width, and identical data state when comparing.

## 23. WAL Counters Can Appear on Multiple Nodes

An UPDATE plan might show:

```text
Update on sales
  Buffers: shared hit=...
  WAL: records=... fpi=... bytes=...
  -> Bitmap Heap Scan on sales
       Buffers: shared hit=...
```

Counters can appear on different nodes depending on instrumentation scope and plan shape.

**Do not sum WAL counters across all nodes** and treat that as total statement records, because parent and descendant counters can overlap on the same activity. Inspect which nodes generate WAL and use the appropriate top-level summary.

### Triggers and Auxiliary Costs

If a table has triggers writing audit rows or updating other tables, `EXPLAIN ANALYZE` executes those triggers and may report trigger timing/calls depending on version and plan.

Do not assume an UPDATE's WAL comes solely from the primary table's heap tuples. Index maintenance, trigger DML, TOAST, and auxiliary structures can all contribute.

## 24. WAL from SELECT: Is It Always Zero?

Ordinary read queries generally **do not generate business-data WAL**, yet you should never hardcode a rule that **every SELECT always has WAL Bytes = 0**.

In PostgreSQL, mechanisms such as setting **hint bits** and logging rules tied to `wal_log_hints`/data checksums/full-page images can cause a read to trigger special WAL writes depending on context. Functions called inside SELECT can also have side effects if not truly read-only.

Therefore:

- `SELECT 1` normally produces no notable WAL.
- Ordinary data-scanning `SELECT`s usually show zero or minimal WAL.
- Do not treat non-zero WAL as proof an app executed an explicit `UPDATE`.

What matters is understanding **query semantics and server internals**, rather than interpreting one counter in isolation.

## 25. WAL Bytes Is Not Network Replication Throughput

`WAL Bytes` in an EXPLAIN reflects WAL activity within the measured scope, **not directly equal to**:

- Network bytes transmitted by physical replication.
- Bytes sent by the application to the database.
- Extra bytes stored on tables/indexes.
- `pg_wal` directory size afterward.
- Time taken to flush WAL on commit.

Replication can apply compression, batching, retries, protocol framing, and carry WAL from many concurrent transactions. WAL files have their own retention/recycling lifecycle.

### Why Does This Distinction Matter?

A DML benchmark generating 10 MiB of WAL does not mean a replica instantaneously receives an exact 10 MiB TCP payload. To evaluate replication, inspect dedicated metrics like WAL sender/receiver lag, LSN positions, network stats, and write/flush/replay lag.

## 26. Comparing WAL with pg_stat_wal and pg_stat_statements

When broader context is needed:

- **`pg_stat_wal`** provides instance/cluster-wide WAL statistics on supported versions.
- **`pg_stat_statements`** (extension, when configured) can provide WAL counters per statement fingerprint aggregated across **many executions**.
- **`EXPLAIN (ANALYZE, WAL)`** reports metrics tied to **a single instrumented execution**, useful for inspecting individual nodes and specific SQL.

Example querying instance-wide WAL stats:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Views and columns vary across server versions; do not run this query on older servers without verifying support.

### Do Not Subtract pg_stat_wal as One Query's WAL Under Concurrency

If you compute:

```text
wal_bytes_after - wal_bytes_before
```

while hundreds of other sessions write concurrently, the delta reflects the **entire instance** and is not isolated to one statement.

`EXPLAIN WAL` is far better suited to studying a single statement directly, even though it still omits some background work and non-executor events.

## 27. WAL After ROLLBACK Was Still Generated

A transaction:

```sql
BEGIN;
UPDATE lesson_plan_metrics.sales
SET note = note || '-edited'
WHERE sale_id BETWEEN 1 AND 100;
ROLLBACK;
```

leaves no committed business change in the table, yet PostgreSQL still may have:

- Created temporary tuple versions during execution.
- Written WAL for logged operations.
- Consumed buffers/cache/CPU/I/O.
- Created cleanup work for VACUUM and the system.

That is why you cannot "benchmark an UPDATE for free" by running it and rolling back. Rollback preserves **transactional data correctness**, not consumed resources.

### Benchmarking DML in Production

Even wrapped in ROLLBACK, DML can hold locks and generate WAL/bloat affecting the system. Never use that technique on hot production tables without controlled conditions and approval.

## 28. What Does SETTINGS Tell You?

`SETTINGS` in EXPLAIN lists **planner-affecting configuration parameters** whose values differ from **built-in defaults**.

Example:

```sql
EXPLAIN (SETTINGS)
SELECT *
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

An illustrative output:

```text
Index Scan using ix_sales_customer_recent on sales ...
  Index Cond: (customer_id = 42)
Settings: work_mem = '64MB', random_page_cost = '1.1'
```

**This section is not guaranteed to appear**: if relevant settings match built-in defaults or are not among those reported, `Settings` may be omitted.

### Built-In Default vs Environment Default

If a DBA set `random_page_cost=1.1` in `postgresql.conf`, EXPLAIN SETTINGS will still display it because it differs from the **built-in default**, even though every database session inherits it.

`SETTINGS` does not mean "the caller just ran SET to change a parameter." It describes **effective relevant values at plan creation time**, per reporting rules.

## 29. SETTINGS Is Not SHOW ALL

`SHOW ALL` or `pg_settings` contains hundreds of GUCs:

```sql
SHOW ALL;
```

`EXPLAIN (SETTINGS)` **does not dump every GUC** into output.

Examples:

- `work_mem`, `random_page_cost`, and `enable_seqscan` directly affect plan choice.
- `application_name` helps monitoring, not typical planner cost estimation.
- `log_min_duration_statement` governs logging, not typical join algorithm selection.

Not seeing `application_name` in SETTINGS does not mean the session lacks an application name.

### Inspecting a Specific GUC Precisely

```sql
SELECT
    name,
    setting,
    unit,
    source,
    boot_val,
    reset_val
FROM pg_catalog.pg_settings
WHERE name IN (
    'work_mem',
    'random_page_cost',
    'seq_page_cost',
    'effective_cache_size',
    'enable_seqscan',
    'max_parallel_workers_per_gather'
)
ORDER BY name;
```

These columns clarify runtime values, setting sources, and reference defaults, though interpreting `boot_val`/`reset_val` still requires respecting each GUC's semantics and PostgreSQL version.

## 30. SET LOCAL: Testing Settings Without Polluting the Session

A clean way to study behavior is comparing the same SQL inside a transaction using `SET LOCAL`:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

`SET LOCAL` takes effect for the current transaction and reverts when the transaction ends. Likewise:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Compare:

1. Sort Method (in-memory vs external merge).
2. Temp Read/Written Blocks.
3. Actual Rows/Loops.
4. Execution Time.
5. `SETTINGS` to confirm the plan environment.

### Why Use SET LOCAL Instead of SET?

`SET` persists for the lifetime of the session unless explicitly reset. With connection pooling, an unmanaged session setting can leak into subsequent requests.

`SET LOCAL` minimizes cross-transaction setting leakage, though it still does not replace proper connection-state resetting by transaction managers/pools.

## 31. Testing enable_seqscan = off: A Learning Tool, Not a Default Fix

Sometimes you want to see what the planner would choose if sequential scans are discouraged:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    customer_id
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

ROLLBACK;
```

`enable_seqscan=off` **makes the planner avoid sequential scans when alternatives exist**, though it does not strictly forbid Seq Scan in all circumstances.

### Primary Purpose

Use this experiment to:

- See whether any viable index plan exists.
- Compare cost and buffer usage of the alternative plan.
- Investigate why statistics or cost settings made the planner choose differently than expected.

### Do Not Use Blindly as Permanent Tuning

Disabling plan methods session-wide can slow down many other queries. Address root causes instead:

- Statistics, index design, and predicates.
- Cost parameters matched to hardware.
- Query structure, filter selectivity, and data skew.
- Representative runtime measurements.

`SETTINGS` documents the experiment; it does not prove the forced plan is better.

## 32. random_page_cost, effective_cache_size, and work_mem

Commonly investigated planner-relevant settings:

| GUC | General meaning | Pitfall to avoid |
|---|---|---|
| `seq_page_cost` | Relative cost for sequential page access. | Interpreting cost as milliseconds. |
| `random_page_cost` | Relative cost for random page access. | Lowering arbitrarily to force index scans everywhere. |
| `effective_cache_size` | Estimate of effective cache the planner may consider. | Assuming PostgreSQL immediately allocates that RAM. |
| `work_mem` | Memory budget for certain sort/hash operations. | Treating it as total memory cap per session/query. |
| `max_parallel_workers_per_gather` | Worker cap in eligible parallel plans. | Assuming higher is always faster. |
| `enable_hashjoin`, `enable_nestloop`... | Toggles influencing join algorithm selection. | Leaving enabled permanently without fixing bad plans. |

**SETTINGS is contextual evidence, not proof a GUC is right or wrong.** Any setting recommendation requires representative benchmarks, statistics checks, and concurrency analysis.

## 33. SETTINGS with Prepared Statements

Java apps commonly use `PreparedStatement`. PostgreSQL can choose a **custom plan** or a **generic plan** where applicable, depending on configuration and execution count.

Example with two tenants:

```text
tenant_id = 1   → 1 million rows
tenant_id = 42  → 30 rows
```

The same parameterized SQL can have vastly different selectivity. If plans shift via generic/custom behavior, running:

```sql
EXPLAIN SELECT ... WHERE tenant_id = 42;
```

may not reflect the exact plan type used by live JDBC calls.

### How to Diagnose

Inspect SQL, parameters, driver/server prepared statement behavior, statistics, `plan_cache_mode`, and other relevant `SETTINGS`. Do not blame `work_mem` for every discrepancy just because it appears first in SETTINGS.

`EXPLAIN EXECUTE prepared_statement(...)` helps observe prepared statement plans on the server through the appropriate interface.

## 34. FORMAT JSON: Why Is It Needed?

TEXT plans are great for humans:

```text
Limit
  -> Index Scan
```

However, an app comparing 200 plans to flag "which queries have temp writes > 100,000 blocks" struggles to parse indented text reliably. `FORMAT JSON` returns the plan tree as structured data:

```sql
EXPLAIN (FORMAT JSON)
SELECT
    sale_id,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Clients typically receive **one result row** containing a JSON value whose top level is an **array**, where each element describes an explained statement.

### Benefits

- No counting spaces to infer tree hierarchy.
- Explicit key-value fields for counters.
- `Plans` array holding child nodes.
- Programmatic node lookup by `Node Type`.
- Easy storage and diffing across benchmark runs.
- Straightforward integration with dashboards, CI, or SQL analyzers.

### Trade-offs

- Verbose JSON with many keys.
- Output schema can evolve across PostgreSQL versions and options.
- Not every field is always present.
- Tooling must still interpret counters/loops/parallelism properly instead of naive summing.

## 35. Output JSON Structure

An **abbreviated illustrative example, not direct lab output**:

```json
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Startup Cost": 0.29,
      "Total Cost": 4.25,
      "Plan Rows": 5,
      "Plan Width": 22,
      "Actual Startup Time": 0.020,
      "Actual Total Time": 0.060,
      "Actual Rows": 5,
      "Actual Loops": 1,
      "Shared Hit Blocks": 4,
      "Shared Read Blocks": 2,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Index Name": "ix_sales_customer_recent",
          "Relation Name": "sales",
          "Alias": "sales",
          "Index Cond": "(customer_id = 42)",
          "Startup Cost": 0.29,
          "Total Cost": 40.0,
          "Plan Rows": 30,
          "Plan Width": 22,
          "Actual Startup Time": 0.018,
          "Actual Total Time": 0.055,
          "Actual Rows": 5,
          "Actual Loops": 1,
          "Shared Hit Blocks": 4,
          "Shared Read Blocks": 2
        }
      ]
    },
    "Settings": {
      "work_mem": "64MB"
    },
    "Planning Time": 0.150,
    "Execution Time": 0.085
  }
]
```

**Note:** This is synthetic JSON illustrating the shape. Optional fields, numbers, and Settings visibility vary by query, config, and version. Parsers must tolerate absent keys.

### Components

| JSON path | Meaning |
|---|---|
| `[0]` | First element of the result array. |
| `[0].Plan` | Root plan node. |
| `Plan["Node Type"]` | Node type: Seq Scan, Index Scan, Hash Join, Sort, Aggregate... |
| `Plan["Plans"]` | Array of child plan nodes, if present. |
| `Plan["Actual Rows"]` | Actual rows as reported by PostgreSQL under ANALYZE. |
| `Plan["Actual Loops"]` | Number of times the node was invoked/executed. |
| `Plan["Shared Hit Blocks"]` | Shared buffer hit counter, if reported. |
| `[0].Settings` | Non-default planner-relevant GUCs when SETTINGS is enabled and non-empty. |
| `[0]["Planning Time"]` | Planning duration in ms when measured and emitted. |
| `[0]["Execution Time"]` | Execution duration in ms when measured and emitted. |

Keys contain **spaces** and are case-sensitive. Use exact key names in JavaScript/Python/Jackson.

## 36. FORMAT JSON Does Not Make EXPLAIN Queryable in FROM

A common misconception:

```sql
-- Not valid PostgreSQL SQL syntax:
SELECT *
FROM (
    EXPLAIN (FORMAT JSON)
    SELECT * FROM lesson_plan_metrics.sales
) AS plan;
```

`EXPLAIN` is a utility command, not an ordinary SELECT subquery usable directly inside `FROM`.

### How to Process the JSON?

- Redirect `psql` output to a file.
- Read column 1 of the `ResultSet` in Java/JDBC.
- Fetch and parse in Python/Go or another client.
- Have a monitoring tool run EXPLAIN and persist structured results.

Do not try to force EXPLAIN into a CTE like a SQL function just to query it with `jsonb_path_query`.

## 37. JSON Output with BUFFERS, WAL, and SETTINGS

A full command:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    s.sale_id,
    s.amount
FROM lesson_plan_metrics.sales AS s
WHERE s.customer_id = 42;
```

Output might include:

```json
[
  {
    "Plan": {
      "Node Type": "Bitmap Heap Scan",
      "Relation Name": "sales",
      "Alias": "s",
      "Plan Rows": 30,
      "Actual Rows": 30,
      "Actual Loops": 1,
      "Shared Hit Blocks": 19,
      "Shared Read Blocks": 2,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "WAL Records": 0,
      "WAL FPI": 0,
      "WAL Bytes": 0
    },
    "Planning Time": 0.3,
    "Execution Time": 0.2
  }
]
```

This is likewise an **illustrative structure**, not real output: if PostgreSQL picks Bitmap Heap Scan, in reality `Plans` would typically contain a Bitmap Index Scan plus other fields. The example shows **key names**, not a full real plan.

### When WAL Is Zero

Some versions/formats may omit zero counters or explicitly emit `0`. Parsers should handle both **missing fields** and **numeric zero** without mistaking them for JSON access errors.

### UPDATE JSON

When running `EXPLAIN ANALYZE UPDATE`, the root node may be `ModifyTable`/`Update` or an equivalent depending on version, and WAL metrics are usually prominent. Do not write a parser expecting `Node Type = "Select"`, as that is not a standard EXPLAIN node type.

## 38. Common JSON Keys

| Group | Example keys |
|---|---|
| Structure | `Node Type`, `Plans`, `Parent Relationship`, `Relation Name`, `Alias`, `Index Name`. |
| Estimates | `Startup Cost`, `Total Cost`, `Plan Rows`, `Plan Width`. |
| Actuals | `Actual Startup Time`, `Actual Total Time`, `Actual Rows`, `Actual Loops`. |
| Filters | `Filter`, `Index Cond`, `Recheck Cond`, `Rows Removed by Filter`. |
| Shared buffers | `Shared Hit Blocks`, `Shared Read Blocks`, `Shared Dirtied Blocks`, `Shared Written Blocks`. |
| Local buffers | `Local Hit Blocks`, `Local Read Blocks`, `Local Dirtied Blocks`, `Local Written Blocks`. |
| Temp blocks | `Temp Read Blocks`, `Temp Written Blocks`. |
| WAL | `WAL Records`, `WAL FPI`, `WAL Bytes`. |
| Sort | `Sort Key`, `Sort Method`, `Sort Space Used`, `Sort Space Type`. |
| Parallel | `Workers Planned`, `Workers Launched`, `Workers`. |
| Config/summary | `Settings`, `Planning Time`, `Execution Time`, `Triggers`, `JIT` (when applicable). |

This is not an immutable list across every major PostgreSQL version. Many fields appear only when relevant to the node/options.

### Do Not Hardcode All Keys as Mandatory

A plan-only JSON has no actual timings. A query without sorting has no `Sort Method`. A non-parallel plan has no `Workers`. When `SETTINGS` finds no non-default planner settings to report, `Settings` may be absent.

Well-written tooling uses **optional** reads with sensible defaults/nullability, while distinguishing `0` from "not measured."

## 39. Exporting JSON from psql

In `psql`, to save `FORMAT JSON` output cleanly without table borders, configure formatting:

```text
\pset format unaligned
\pset tuples_only on
\o explain-plan.json
```

Then run:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    sale_id,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Then in `psql`:

```text
\o
```

`\o explain-plan.json` redirects query output to a file; `\o` without arguments restores terminal output. With unaligned formatting and tuples-only mode, a single JSON output writes cleanly without psql headers or borders.

### Scripting Notes

- Lines starting with `\` are **psql meta-commands**, not SQL for JDBC.
- File names/paths are local to the client machine running `psql`.
- Ensure no other statement output gets mixed into the same file.
- Validate the file with a JSON parser instead of relying solely on the `.json` extension.
- If multiple statements or outputs run, concatenating multiple JSON documents will not form one valid JSON document.

### Restoring Normal Terminal Output

To return to normal formatting:

```text
\pset format aligned
\pset tuples_only off
```

Adjust as needed. Remember to reset if continuing to run other queries in the same session.

## 40. Parsing EXPLAIN FORMAT JSON in Java/JDBC

Java works cleanly to fetch a JSON result set and parse it via Jackson.

Illustrative method (assuming Jackson is on the classpath):

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class ExplainReader {
    private static final ObjectMapper JSON = new ObjectMapper();

    public static void inspect(Connection connection, int customerId)
            throws SQLException, JsonProcessingException {
        String sql = """
            EXPLAIN (
                ANALYZE,
                BUFFERS,
                WAL,
                SETTINGS,
                FORMAT JSON
            )
            SELECT sale_id, amount
            FROM lesson_plan_metrics.sales
            WHERE customer_id = ?
            """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {
            statement.setInt(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("EXPLAIN did not return a row");
                }

                String json = rs.getString(1);
                JsonNode document = JSON.readTree(json);
                JsonNode root = document.path(0);
                JsonNode plan = root.path("Plan");

                String nodeType =
                    plan.path("Node Type").asText("<unknown>");

                long sharedHits =
                    plan.path("Shared Hit Blocks").asLong(0L);

                long sharedReads =
                    plan.path("Shared Read Blocks").asLong(0L);

                double executionMs =
                    root.path("Execution Time").asDouble(Double.NaN);

                System.out.printf(
                    "Node=%s, hits=%d, reads=%d, executionMs=%s%n",
                    nodeType, sharedHits, sharedReads,
                    Double.toString(executionMs)
                );
            }
        }
    }
}
```

### Explanation

1. `PreparedStatement` binds `customer_id` as a parameter rather than concatenating values into SQL strings.
2. `EXPLAIN (FORMAT JSON)` returns a single column containing JSON; `ResultSet.getString(1)` retrieves the string for parsing.
3. The JSON root is an array, so `document.path(0)` accesses the first element.
4. `Plan` is the root plan node.
5. `Shared Hit Blocks` and `Shared Read Blocks` are space-delimited keys.
6. `Execution Time` may be absent without `ANALYZE` or depending on display options; the snippet uses `Double.NaN` when missing.

**Use this pattern only on lab SELECTs or safe queries.** Never allow arbitrary client SQL to be wrapped in `EXPLAIN ANALYZE` and executed in production.

### Parser vs Validator

`asLong(0)` is convenient for display, yet in automated performance evaluation, **a missing counter** is not always equivalent to **measured as 0**. Model `OptionalLong` or a `metricPresent` flag if distinguishing the two states matters.

## 41. Recursively Traversing the Plans Tree in Java

A plan might look like:

```text
Aggregate
   └── Hash Join
         ├── Seq Scan sales
         └── Hash
              └── Seq Scan customers
```

Child nodes sit inside the `Plans` array. To find all Sort nodes, traverse recursively:

```java
import com.fasterxml.jackson.databind.JsonNode;

public static void visitPlan(JsonNode plan, int depth) {
    if (plan == null || plan.isMissingNode()) {
        return;
    }

    String nodeType =
        plan.path("Node Type").asText("<unknown>");

    String indent = "  ".repeat(Math.max(depth, 0));

    System.out.println(indent + nodeType);

    if ("Sort".equals(nodeType)) {
        String sortMethod =
            plan.path("Sort Method").asText("<not reported>");
        System.out.println(indent + "  method=" + sortMethod);
    }

    JsonNode children = plan.path("Plans");
    if (children.isArray()) {
        for (JsonNode child : children) {
            visitPlan(child, depth + 1);
        }
    }
}
```

This is an illustrative method that can live in a Java class in a project using Jackson. Invoke via:

```java
visitPlan(document.path(0).path("Plan"), 0);
```

### What Not to Do

Do not blindly write:

```java
totalSharedReads += plan.get("Shared Read Blocks").asLong();
```

on **every node** and assume that gives unique reads for the entire statement. As noted earlier, counters are cumulative/inclusive across children; design aggregations according to metric semantics and node scope.

## 42. Comparing Two JSON Plans

When benchmarking before/after an index change, you often compare:

- Root node type and child structure.
- Estimated and actual rows.
- Loops on nested-loop children.
- Shared hits/reads.
- Temp reads/writes and sort method.
- WAL records/FPI/bytes for write queries.
- Planner settings.
- Planning Time / Execution Time.

A benchmark record might look like:

```json
{
  "scenario": "customer-42-top-5",
  "postgres_major": 17,
  "iteration": 3,
  "metrics": {
    "execution_ms": 0.58,
    "shared_hit_blocks": 15,
    "shared_read_blocks": 1,
    "temp_written_blocks": 0,
    "wal_bytes": 0
  }
}
```

This is a **custom benchmark schema**, not native PostgreSQL output. When storing results, retain metadata needed for reproducibility:

- SQL and parameters (redacted if containing sensitive data).
- PostgreSQL major/minor version.
- Isolation level, transaction/connection mode.
- Relevant planner settings.
- Dataset size and last ANALYZE time.
- Warm/cold cache context.
- Timestamp and concurrent workload impact.

### Meaningful Metric Comparisons

If query A runs in 5 ms and query B runs in 4 ms on a single run, that is not enough to conclude B is 20% faster. You need repeated runs, variance tracking, and representative workloads.

## 43. JSON Keys Are Not an Immutable API Across All Versions

PostgreSQL releases can add new fields, adjust detail presentation, or expand instrumentation.

Categories that may evolve include:

- I/O timing details.
- Parallel worker attributes.
- New node types or extra node properties.
- JIT instrumentation.
- Memory/accounting fields.
- Plans for new scan technologies.

Therefore:

1. Store the PostgreSQL version alongside the JSON.
2. Parse key fields by name and allow optional fields to be absent.
3. Never depend on **key ordering** inside JSON objects.
4. Never assume numeric values always serialize with the same decimal precision.
5. Traverse the tree via `Plans` rather than hardcoding fixed positional paths.
6. Re-test tooling when upgrading PostgreSQL major versions.

### A Node Can Have Multiple Child Roles

`Parent Relationship` can denote `Outer`/`Inner` or other roles depending on node type. Do not assume a join always has exactly two children in a fixed order when building general analysis tooling.

## 44. SETTINGS and JSON in the Same Command

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

When `work_mem` differs from its built-in default and is reported, the top-level JSON object may include:

```json
"Settings": {
  "work_mem": "64kB"
}
```

The snippet above is a **fragment inside a JSON object**, not a standalone valid JSON document since it shows a single property. To form valid JSON, it must sit inside `{ ... }`.

### Are SETTINGS Values Strings?

In JSON output, setting values are typically serialized as configuration strings such as `"64kB"` or `"off"`. Parsers should not blindly cast every value to `int`; handle units and GUC types when comparing.

### Do Not Confuse SETTINGS with SQL Statements

`SETTINGS` does not replay `SET LOCAL` statements that ran, nor show a history of setting changes. It reflects the **planning context** at that moment.

## 45. Scenario 1: High Shared Block Reads Due to Sequential Scan

Example:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales
WHERE note LIKE '%999%';
```

A B-tree index on `customer_id` does not directly accelerate a leading-wildcard substring predicate `'%999%'` on `note`, so the planner may choose `Seq Scan`.

Possible output:

```text
Seq Scan on sales
  Filter: (note ~~ '%999%'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

### Investigation Direction

1. Is the query's intent **substring** or prefix matching?
2. Does text search require `pg_trgm`/GIN/GiST or full-text search?
3. What are table size and predicate selectivity?
4. Does an index fit the real workload?
5. Is page access volume proportional to final rows?

**Do not blindly create a B-tree index on `note` just because Seq Scan appeared.** Indexes must match operators, predicates, and overall workload.

## 46. Scenario 2: Nested Loop with Many Lookups

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    s.sale_id
FROM lesson_plan_metrics.customers AS c
JOIN lesson_plan_metrics.sales AS s
  ON s.customer_id = c.customer_id
WHERE c.customer_id <= 50;
```

The planner may pick Nested Loop or Hash Join depending on statistics and costs.

If Nested Loop:

```text
Nested Loop
  -> Index Scan customers ...
  -> Index Scan sales ... (loops=50)
```

### Interpretation

- One child is invoked many times for outer rows.
- Shared Hit Blocks can climb from revisiting index pages.
- Do not add timings directly between parent and inner child.
- A plan with many random lookups works well when the outer input is tiny, poorly when the outer input has millions of rows.

**Do not treat Nested Loop as a bug.** It can be the optimal algorithm for selective lookups/joins.

## 47. Scenario 3: Sort Spilling to Temp Files

Query:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT TEXT
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Symptoms:

```text
Sort Method: external merge
Disk: ...
Buffers: temp read=... written=...
```

### Questions to Answer

- Do we really need to sort all rows?
- Would a `LIMIT` change processing?
- Is there an index matching `ORDER BY`/`WHERE`?
- Are we sorting on an unindexed expression?
- Is `work_mem` too low for this workload?
- How many concurrent copies run, and is enough RAM available?

Before changing server-wide settings, test with **SET LOCAL** in a lab transaction. Remember raising `work_mem` lets multiple operations allocate more RAM simultaneously.

## 48. Scenario 4: HashAggregate / Hash Join Spill

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS sales_count,
    SUM(amount) AS total_amount
FROM lesson_plan_metrics.sales
GROUP BY customer_id
ORDER BY total_amount DESC;
```

The planner may choose HashAggregate, GroupAggregate, or another sort/aggregate combination.

When hash-based operations exceed memory, PostgreSQL may use multiple batches or spill. Depending on version/node, the plan may report:

```text
HashAggregate
  Batches: ...
  Memory Usage: ...
  Disk Usage: ...
  Buffers: temp read=... written=...
```

### Do Not Confuse Two Causes

One query may have both:

- A final Sort on `total_amount DESC`.
- A HashAggregate on `customer_id`.

Temp blocks can come from **either or both**. Inspect **node-level** Sort/HashAggregate details for Memory/Disk rather than looking only at the root.

If group count estimates are severely wrong, the planner can pick a suboptimal strategy. Check statistics, data skew, and query design rather than just raising `work_mem`.

## 49. Scenario 5: UPDATE Generating High WAL

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS
)
UPDATE lesson_plan_metrics.sales
SET note = note || '-changed'
WHERE sale_id BETWEEN 1 AND 1000;

ROLLBACK;
```

When WAL is high, check:

- How many rows actually changed?
- Were indexed columns modified?
- Was the update HOT-eligible?
- Did rows grow larger, creating/moving TOAST data?
- How did checkpoint/FPI timing affect it?
- Did audit triggers fire?
- Were rows with unchanged values updated unnecessarily?

### Avoiding No-Op UPDATEs

If an app frequently sends:

```sql
UPDATE table_name
SET status = 'PAID'
WHERE id = ?;
```

even when `status` is already `PAID`, PostgreSQL still creates a new tuple version for a matching UPDATE, increasing bloat/WAL.

Consider:

```sql
UPDATE table_name
SET status = 'PAID'
WHERE id = ?
  AND status IS DISTINCT FROM 'PAID';
```

This is a generic pattern with an uncreated `table_name`. Apply it only when semantics permit skipping no-op updates; some workflows or triggers rely on every update firing.

## 50. Scenario 6: Seeing Different SETTINGS Only

Two environments run the same SQL:

```text
Environment A
  Settings: work_mem = '4MB'
  Sort Method: external merge
  temp written=...

Environment B
  Settings: work_mem = '64MB'
  Sort Method: quicksort
  temp written=0
```

Reasonable hypothesis: differing `work_mem` contributed to the Sort Method and temp I/O change.

However, if A and B also differ in hardware, dataset, version, and caching, **you cannot claim `work_mem` is the sole cause**. To establish causality, vary one factor at a time while holding others comparable.

### SETTINGS Is Evidence, Not a Solution

It confirms environment variables affecting the planner differ from built-in defaults. From SETTINGS alone you cannot determine whether estimates are accurate or buffer usage is optimal.

## 51. Scenario 7: High Planning Time

If:

```text
Planning Time: 20.0 ms
Execution Time: 2.0 ms
```

planning dominates execution.

Examine:

- Queries joining many tables with many join-order combinations.
- Partitioned tables with many partitions.
- Cold metadata/catalog caches.
- Statistics complexity and planner search effort.
- Prepared statement plan reuse / generic plans.
- Extension planner hooks or environment factors.

**Planning BUFFERS** can reveal metadata page accesses, though they do not measure all CPU spent searching plan space.

### Why Not Ignore Planning Time?

An app may execute a short query thousands of times per second. Re-planning every time can make planning a major fraction of total server cost. Separate planning overhead from execution bottlenecks before adding indexes.

## 52. Scenario 8: High Execution Time with Low Buffers

Suppose a query runs an expensive expression:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    md5(repeat(note, 10))
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

If buffer accesses are low while time is high, expression CPU or other stages may dominate. With simple functions on small data, this example may still be very fast; it illustrates the pattern.

### Questions to Ask

- How many times was the function called?
- Is `Rows Removed by Filter` huge?
- Did it return few rows after processing many beforehand?
- Is there JIT compilation overhead?
- Are there lock/I/O/network waits EXPLAIN does not break down?

Adding RAM or indexes does not always fix this.

## 53. EXPLAIN with TIMING OFF

In very fast queries with millions of node invocations, per-node clock sampling can add notable overhead.

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    WAL,
    SETTINGS
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales;
```

With `TIMING OFF`:

- PostgreSQL still executes the statement and collects supported counters such as rows/loops.
- **Per-node timings** are omitted.
- Overall `Execution Time` can still be measured and shown when summary is enabled.
- Removes part of per-node timing overhead, yielding more realistic total runtimes in some cases.

### Do Not Confuse TIMING OFF with ANALYZE OFF

`ANALYZE` still executes the query. `TIMING OFF` only changes timing instrumentation; it does not turn an UPDATE into a dry run.

### When to Use It?

When you care about **row counts, buffer usage, WAL counts, and total time** without needing per-node timings for that run.

## 54. COSTS OFF and SUMMARY OFF

To make output more compact:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    FORMAT TEXT
)
SELECT *
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

`COSTS OFF` hides estimated fields like cost/rows/width in supported formats; it **does not alter planner calculations**.

`SUMMARY OFF` hides the summary block:

```sql
EXPLAIN (
    ANALYZE,
    SUMMARY OFF,
    BUFFERS
)
SELECT 1;
```

For automated comparisons, do not turn off fields your tooling requires. Presentation options control output/instrumentation, not plan quality.

## 55. FORMAT JSON, YAML, XML, TEXT

PostgreSQL supports multiple output formats for `EXPLAIN`:

```sql
EXPLAIN (FORMAT TEXT) SELECT 1;
EXPLAIN (FORMAT JSON) SELECT 1;
EXPLAIN (FORMAT YAML) SELECT 1;
EXPLAIN (FORMAT XML) SELECT 1;
```

| Format | Best fit |
|---|---|
| TEXT | Quick visual reading, terminal use, incident notes. |
| JSON | Programmatic parsing, counter extraction, structured diffing. |
| YAML | Human-readable structured text in YAML workflows. |
| XML | Integrations built around XML tooling. |

When **analyzing with Java/Jackson**, JSON is usually best because it is ubiquitous and maps naturally to trees.

### Changing Format Does Not Change Query Behavior

`FORMAT JSON` only changes display format; it does not speed up queries or reduce WAL. Enabling `ANALYZE`, `BUFFERS`, and `WAL` drives instrumentation overhead regardless of output format.

## 56. Reading Multi-Level Plans from JSON

Example structure:

```json
[
  {
    "Plan": {
      "Node Type": "Nested Loop",
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Relation Name": "customers"
        },
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Inner",
          "Relation Name": "sales",
          "Actual Loops": 50
        }
      ]
    }
  }
]
```

This is abbreviated JSON showing structure, not a real full EXPLAIN output.

A parser should traverse:

1. Root object `[0]`.
2. `Plan`.
3. Each `Plans[i]`.
4. Recursively any children containing `Plans`.

### Do Not Identify Nodes Solely by Fixed Array Index

If today's plan is:

```text
Nested Loop
  ├── Index Scan
  └── Index Scan
```

and after ANALYZE the planner chooses:

```text
Hash Join
  ├── Seq Scan
  └── Hash
       └── Seq Scan
```

then `Plans[1]` no longer points to the same logical node. Tooling should identify nodes by **type, relation, index, role, and tree context** when comparing in detail, rather than rigid positional paths.

## 57. JSON Data Can Be Sensitive

Plan JSON can contain:

- Schema, table, index, and column names.
- Filter predicates with literal values.
- Query structure / SQL expressions.
- Row counts/timings revealing data scale.
- Settings revealing server configuration.

Therefore:

- Do not dump raw plan JSON into public logs when sensitive data is present.
- Redact literals/PII before sharing externally.
- Restrict read/collection access and retention.
- Review security requirements when using third-party SQL analyzers.

`FORMAT JSON` enables automation, yet also makes harvesting full database structure trivial; govern it accordingly.

## 58. Never Use EXPLAIN ANALYZE as a Frequent Health Check

A health check executing:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE important_table
SET value = value + 1
WHERE id = 1;
```

is a broken design. It **genuinely performs UPDATEs** and causes side effects.

Even on large SELECTs, EXPLAIN ANALYZE:

- Runs the real query, consuming CPU/I/O.
- Adds instrumentation overhead.
- Can create temp files or churn caches.
- Can hold locks/snapshots corresponding to the statement.

Never put heavy EXPLAIN ANALYZE calls inside high-frequency health-check endpoints. Use metrics, sampling, and controlled diagnostic access.

## 59. EXPLAIN, pg_stat_statements, and auto_explain

Three tools with distinct purposes:

### EXPLAIN

Shows the plan for **one SQL statement** on demand. With ANALYZE, measures **one execution**.

### pg_stat_statements

Extension (when installed/configured) collecting aggregate statistics by statement fingerprint across **many executions**:

- Call counts.
- Total/mean times across supported counters.
- Buffer hits/reads and certain WAL metrics depending on version.

Helps find "which SQL consumes the most total time," without replacing detailed plan trees.

### auto_explain

Extension/tooling that logs execution plans of SQL exceeding a duration threshold, when configured appropriately.

**Warning:** Enabling `auto_explain.log_analyze` or heavy instrumentation options can add substantial overhead depending on workload. Never enable indiscriminately in production without evaluating log volume, performance impact, and query data exposure.

### Common Workflow

```text
Observe latency / pg_stat_statements
            │
            ▼
Pick query to investigate
            │
            ▼
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
in an appropriate environment
            │
            ▼
Save FORMAT JSON, compare across runs
            │
            ▼
Make controlled index/query/setting change
            │
            ▼
Re-measure and validate under real workload
```

## 60. EXPLAIN Does Not Measure Lock Wait History by Itself

A query can be slow because it waits on a lock:

```sql
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id = 42;
```

If another transaction holds a conflicting lock, the UPDATE waits. `EXPLAIN ANALYZE` may reflect the elapsed statement time yet does not provide a complete **wait-for graph**.

To identify active blockers:

```sql
SELECT
    a.pid,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

### Differentiating

- High shared reads + high I/O timing: I/O bottleneck hypothesis.
- High temp writes: sort/hash spill hypothesis.
- Query waiting on `Lock`: inspect blockers and transaction lifecycles.
- Low buffers/WAL yet high time: consider CPU, functions, JIT, or other wait types.

Do not ask `BUFFERS` to answer questions it does not measure.

## 61. A Runbook for Diagnosing Slowness from EXPLAIN

When encountering a slow query:

**Step 1 — Capture the real SQL and parameters.** Ensure EXPLAIN runs a query matching real traffic, not a toy query with different selectivity.

**Step 2 — Check execution safety.** For DML, use a lab/cloned dataset or a transaction with a rollback plan and full awareness of side effects.

**Step 3 — Take plan-only first if needed.** Use `EXPLAIN (SETTINGS, FORMAT JSON)` if execution is not yet allowed.

**Step 4 — Capture actual metrics when permitted.** Use `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)`.

**Step 5 — Compare actual vs estimated rows.** Large mismatches can drive poor join/scan/sort choices.

**Step 6 — Read BUFFERS.** Separate shared hits/reads, local buffers, and temp spills, keeping cumulative counters in mind.

**Step 7 — Read WAL for DML.** Inspect records, FPI, bytes, row counts, indexes/triggers, and checkpoint influence.

**Step 8 — Read SETTINGS.** Compare runtime configuration against a baseline environment without confusing with SHOW ALL.

**Step 9 — Reconcile timings.** Execution Time, Planning Time, I/O timings, lock waits, JIT, CPU, and concurrent load.

**Step 10 — Make one controlled change.** Index, statistics, query rewrite, or justified parameter change, then re-benchmark multiple times.

**Step 11 — Assess system-wide cost.** A new index adds write/WAL overhead; higher `work_mem` raises RAM under concurrency; speeding up one query must not destabilize the system.

**Step 12 — Record evidence.** Save plan JSON with SQL fingerprint, version, settings, dataset, and measurements.

## 62. Reproducible Benchmark Report Template

An engineering team might record:

| Info | Before | After |
|---|---|---|
| SQL fingerprint | `sales-by-customer` | `sales-by-customer` |
| Query parameters | customer_id=42 | customer_id=42 |
| PostgreSQL version | Same version | Same version |
| Dataset rows | 30,000 | 30,000 |
| Plan root | Bitmap Heap Scan | Index Scan |
| Execution Time | 4.2 ms | 0.8 ms |
| Shared Hit Blocks | 200 | 12 |
| Shared Read Blocks | 60 | 2 |
| Temp Written Blocks | 0 | 0 |
| WAL Bytes | 0 | 0 |
| Settings | Saved | Saved |

**Numbers in this table are fictional examples.** Publishing real results requires comparable environments, multiple runs, and documented variance.

### Avoid Reporting Just "5x Faster"

If a query ran once cold and once warm, the difference might not come from the new index. Good benchmarks record **cache context**, warm-up runs, medians/percentiles, and concurrent load.

## 63. Common Mistakes When Reading BUFFERS

### 63.1. "Shared read=1000 means the SSD read 1,000 times"

Not necessarily. Pages may come from OS page cache, and buffer-load counts are not physical disk I/O requests.

### 63.2. "Shared hit=100000 proves the index is great"

No. The query might be scanning/re-reading far too many pages. Compare against final rows, loops, and alternative plans.

### 63.3. "hit + read is the number of unique pages"

No. The same pages can be accessed repeatedly.

### 63.4. "shared written=0 means the query did not write"

No. The backend may dirty pages and write WAL while checkpointer/background writer flushes pages later.

### 63.5. "dirtied equals rows UPDATED"

No. One page contains multiple tuples; index/visibility pages can also change.

### 63.6. "Local buffers are temp spills"

No. Local buffers serve temporary relations; temp blocks are usually executor working files.

### 63.7. "Adding BUFFERS of all plan nodes gives total blocks"

No. Parent and child nodes reflect overlapping activity, causing double-counting.

### 63.8. "Temp writes > 0 just means raise work_mem"

No. Inspect Sort/Hash nodes, data volume, query rewrites, indexes, and memory concurrency.

### 63.9. "Planning Buffers are business table data pages"

Not necessarily. The planner reads catalog/statistics metadata.

### 63.10. "Block size is always 8192 on every server"

Usually 8 KiB, yet check `SHOW block_size` instead of hardcoding in monitoring.

## 64. Common Mistakes When Reading WAL

### 64.1. "WAL records equal row count"

No. One row update can produce multiple WAL records across heap/indexes/TOAST/triggers.

### 64.2. "WAL bytes equal table growth in bytes"

No. WAL serves crash recovery/replication, separate from table file size.

### 64.3. "ROLLBACK removes all generated WAL"

No. WAL for executed changes was already written even if the transaction rolled back.

### 64.4. "An UPDATE with shared written=0 generated no WAL"

No. WAL and data page writes are distinct mechanisms.

### 64.5. "High FPI just means a bad query"

Not necessarily. Checkpoint timing, `full_page_writes`, and compression/settings affect FPIs.

### 64.6. "SELECT always has WAL=0"

Do not treat as an absolute rule due to hint-bit/WAL conditions and function side effects.

### 64.7. "EXPLAIN WAL equals replica network bandwidth"

No. WAL generation, WAL persistence, and replication network throughput are different metrics.

### 64.8. "A WAL increase/decrease in one run proves optimization"

No. You need identical row counts, index state, checkpoint context, dataset, and repeated benchmarks.

## 65. Common Mistakes with SETTINGS and JSON

### 65.1. "SETTINGS lists every GUC"

No. It focuses on planner-relevant settings differing from built-in defaults per PostgreSQL rules.

### 65.2. "Not seeing work_mem means work_mem has no effect"

No. It may match the built-in default or be omitted by context; check `SHOW work_mem` when needed.

### 65.3. "Different SETTINGS must be why plans differ"

Not necessarily. Statistics, data, server version, and parameter selectivity also matter.

### 65.4. "FORMAT JSON returns a single top-level object"

Standard output is a **JSON array** containing an object with `Plan`.

### 65.5. "JSON plans always include Actual Rows"

Not if ANALYZE is off or the field does not apply.

### 65.6. "Root JSON always includes Settings"

No. It may be absent if no eligible settings are reported.

### 65.7. "A missing field equals 0"

Not in every tool. Distinguish unmeasured counters from counters measured as 0.

### 65.8. "JSON key order is meaningful"

Never rely on JSON object key order when parsing.

### 65.9. "Child order in every plan stays fixed across versions"

No. The planner can choose different trees; parsers must traverse structure.

### 65.10. "You can SELECT from EXPLAIN FORMAT JSON like a table"

No. `EXPLAIN` is a utility command; a client/tool must fetch the result to parse it.

### 65.11. "FORMAT JSON automatically makes queries faster"

No. It changes output representation; instrumentation cost depends on other options.

### 65.12. "EXPLAIN ANALYZE only inspects without modifying data"

Dangerously false for DML. It **executes** the statement and associated triggers.

## 66. Quick Practice Command Set

After creating the lab schema and data, you can run in sequence:

**A — Estimated plan:**

```sql
EXPLAIN (SETTINGS, FORMAT TEXT)
SELECT sale_id, sold_at
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

**B — Shared buffer metrics:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

**C — Temp spill under small work_mem:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**D — UPDATE WAL inside a lab transaction:**

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;
ROLLBACK;
```

**E — JSON for tool analysis:**

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT customer_id, COUNT(*)
FROM lesson_plan_metrics.sales
GROUP BY customer_id;
```

**F — Total execution time with less per-node timing overhead:**

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales;
```

Do not assume rigid node types or exact counters; read actual output from the running server.

## 67. Practice Exercises

### Exercise 1 — EXPLAIN and EXPLAIN ANALYZE

On the `sales` table, compare `EXPLAIN SELECT ...` with `EXPLAIN (ANALYZE) SELECT ...`. Which fields appear only when the statement actually executes? Why can't you read `cost=100` as `100 ms`?

### Exercise 2 — Basic BUFFERS

Run `EXPLAIN (ANALYZE, BUFFERS)` filtering `customer_id=42`. Record `shared hit` and `shared read`. What do they tell you about PostgreSQL shared buffers, and what do they **not prove** about SSDs?

### Exercise 3 — Repeated Queries and Caching

Run the same SELECT three times in a row. Compare `shared hit`/`read` and Execution Time; propose two causes that could explain differences and how to control benchmarks.

### Exercise 4 — Reading block_size

Use `SHOW block_size` and convert 1,500 blocks to KiB/MiB. Why is that not an exact physical disk read volume?

### Exercise 5 — Dirtied vs Written

Run DML with `EXPLAIN (ANALYZE, BUFFERS, WAL)` in a rolled-back transaction. Explain how `shared dirtied>0` can occur while `shared written=0`.

### Exercise 6 — Local Buffers

Create a `TEMP TABLE` and read it with `EXPLAIN (ANALYZE, BUFFERS)`. How do `local hit/read` differ from `temp read/write`?

### Exercise 7 — Temp Spill Sort

Inside a transaction, `SET LOCAL work_mem='64kB'` and sort 30,000 rows by `md5(sale_id::text)`. Locate `Sort Method`, `Disk`, and `temp read/write` if present.

### Exercise 8 — Higher work_mem

Repeat Exercise 7 with `work_mem='64MB'`. Compare plan, temp counters, execution time, and RAM; why shouldn't you raise `work_mem` indefinitely with many concurrent connections?

### Exercise 9 — Node-Level Counters

In a plan with Limit and Index Scan, both report identical shared hit/read counts. Why does summing both nodes' counters double-count?

### Exercise 10 — Nested Loop Loops

Find a plan with Nested Loop; record `Actual Rows` and `Actual Loops` of the inner child. If rows=3 and loops=100, what is the estimated total rows produced? Why must you still be cautious about rounding/parallelism?

### Exercise 11 — Parallel Plan

Inspect a plan with Gather/parallel scan if chosen by the planner. Distinguish `Workers Planned` from `Workers Launched`. Why shouldn't you multiply node BUFFERS by worker count?

### Exercise 12 — Planning Buffers

In a plan showing `Planning: Buffers`, explain how they differ from execution buffers. What kinds of metadata might the planner need to read?

### Exercise 13 — track_io_timing

Check `SHOW track_io_timing`. If enabled, inspect I/O Timings. Why can identical shared reads yield very different actual durations?

### Exercise 14 — WAL of INSERT

In the lab, wrap `EXPLAIN (ANALYZE, WAL) INSERT` in a rolled-back transaction. Explain WAL Records, WAL FPI, and WAL Bytes; why can an identity sequence leave a gap despite rollback?

### Exercise 15 — WAL of UPDATE

UPDATE 100 rows in the lab and measure WAL. Why doesn't WAL Records equal row count? Which WAL sources besides the main heap can appear?

### Exercise 16 — WAL of DELETE

Run `EXPLAIN ANALYZE DELETE` inside a transaction and roll back. Why is data restored while generated WAL does not disappear?

### Exercise 17 — FPI and Checkpoints

Explain why the exact same UPDATE can have very different `fpi` depending on checkpoint timing. Why shouldn't you compare two WAL Bytes measurements without knowing environment state?

### Exercise 18 — WAL and Replication

A query generates 5 MiB of WAL. Can you conclude the replica receives an exact 5 MiB of network bytes at that instant? State differences between WAL generation, WAL flush, and replication lag.

### Exercise 19 — SETTINGS

Run `EXPLAIN (SETTINGS)`, then `SET LOCAL work_mem='64kB'` in a transaction and run again. Why does SETTINGS show parameters without listing everything from `SHOW ALL`?

### Exercise 20 — enable_seqscan

In the lab, run `SET LOCAL enable_seqscan=off` and inspect the plan. Why is this only an experiment and not a recommendation to enable in production?

### Exercise 21 — JSON Top-Level

Run `EXPLAIN (FORMAT JSON) SELECT ...`. Locate the first array element, `Plan`, and `Node Type`. Why shouldn't parsers assume the result is a top-level `{"Plan": ...}` object?

### Exercise 22 — Optional JSON Metrics

Compare plan-only JSON with JSON using `ANALYZE, BUFFERS, WAL`. Which fields might be missing? How do you distinguish an unmeasured metric from a value of 0?

### Exercise 23 — Traversing the Tree

Write a Java/Python function traversing `Plan` and all `Plans` children, printing node types. If a plan changes from Nested Loop to Hash Join, will your parser keep working?

### Exercise 24 — JSON WAL Fields

For an EXPLAIN UPDATE with WAL, locate `WAL Records`, `WAL FPI`, and `WAL Bytes` in the actual JSON structure. Why must you not sum counters from all nodes?

### Exercise 25 — psql JSON Export

Use `\pset format unaligned`, `\pset tuples_only on`, and `\o` to write an EXPLAIN FORMAT JSON to a lab file. Validate it with a JSON parser and restore normal output settings.

### Exercise 26 — JDBC JSON Parsing

Write a `PreparedStatement` with `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)` on a SELECT; retrieve `ResultSet.getString(1)` and use Jackson to read `Plan["Node Type"]` and `Execution Time`.

### Exercise 27 — TIMING OFF

Run two `EXPLAIN ANALYZE` runs of the same SELECT, one with `TIMING OFF`. Which details remain? What reduces instrumentation overhead?

### Exercise 28 — Controlled Benchmark

Design an index-change experiment: same dataset, same SQL/parameters, updated statistics, warm-up runs, and repeated measurements. Which metrics will you capture from the JSON plan?

### Exercise 29 — Planning vs Execution

A query has `Planning Time=15ms` and `Execution Time=1ms`. Which bottleneck won't an index cutting execution from 1ms to 0.8ms solve? What will you investigate first?

### Exercise 30 — Slow Yet Low BUFFERS

A query has low shared reads and temp=0, yet high Execution Time. List at least five causes other than disk reads and how to test each hypothesis.

### Exercise 31 — Lock Wait

Session A holds a row lock while session B waits on an UPDATE. Why doesn't BUFFERS point directly to the blocker PID? Write a query using `pg_blocking_pids` and `pg_stat_activity`.

### Exercise 32 — Finding Top WAL-Generating Queries Overall

Compare the goals of `EXPLAIN WAL`, `pg_stat_wal`, and `pg_stat_statements`. When can't an instance-wide delta in WAL bytes be attributed to a single statement?

### Exercise 33 — Auto-Explain

A system has hard-to-reproduce slow queries. How would you weigh `auto_explain`/`log_lock_waits`/`pg_stat_statements` to gather evidence without enabling overly heavy instrumentation?

### Exercise 34 — Comparing SETTINGS Across Environments

Two environments differ in `random_page_cost`, `work_mem`, and data. Design a controlled comparison to isolate setting impact from statistics and cache effects.

### Exercise 35 — Redacting JSON Reports Without Leaking Data

A JSON plan contains filters with customer ID literals and sensitive table names. Propose a redaction strategy, access control, and metadata to retain so benchmarks remain reproducible.

### Exercise 36 — Investigating a Slow UPDATE

In the lab, run `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)` on an UPDATE inside a rolled-back transaction. Read actual rows, shared hits/reads, dirtied/written, WAL Records/FPI/Bytes, and settings; explain the risks of running the same test in production.

## Conclusion

**`EXPLAIN` shows how PostgreSQL intends to execute a SQL statement; `ANALYZE` measures an actual run; `BUFFERS`, `WAL`, and `SETTINGS` expand visibility from the query plan to buffer access costs, WAL generation, and planner configuration context. `FORMAT JSON` turns the plan tree into structured data for automated storage, analysis, and comparison.**

When reading **BUFFERS**, distinguish `shared hit` from `shared read` (never equate directly with physical disk I/O), `dirtied` from `written` (never equate with WAL), and **local buffers** from **temporary working files**, and avoid summing counters across every node because parents can include descendants. Read `Actual Rows` alongside `Loops` and Sort/Hash/Parallel details to pinpoint where work originates.

When reading **WAL**, distinguish `records`, `fpi`, and `bytes` from row counts, table growth, and replication network traffic. A transaction can generate WAL even if later rolled back; FPI counts also depend on checkpoint timing and configuration, so benchmarks must control test conditions.

When using **SETTINGS**, remember the output is not `SHOW ALL`: it highlights planner-affecting settings differing from built-in defaults. When using **FORMAT JSON**, the root is normally an **array** containing `Plan`, child nodes live in `Plans`, and metrics may be absent depending on options/version. Tooling should read JSON flexibly, avoid mixing "unmeasured" with `0`, and avoid summing cumulative counters incorrectly.

Finally, **`EXPLAIN ANALYZE` genuinely executes the statement**. For DML, always understand triggers, WAL, locks, sequences, and side effects before testing. A reliable optimization process does not just yield a prettier plan—it compares **identical workloads, identical contexts, and repeated runs**, then weighs system-wide cost. Combining these four options properly moves you from guessing "the query is slow because of the database" to evidence-based diagnosis and grounded PostgreSQL performance improvements.
