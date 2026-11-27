# Handling Sort or Hash Spilling to Disk

A report that previously ran in 300 ms now takes over 10 seconds. `EXPLAIN (ANALYZE, BUFFERS)` shows:

```text
Sort Method: external merge  Disk: 36000kB
Buffers: shared hit=..., temp read=... written=...
```

Or a `JOIN` statement reports:

```text
Hash
  Buckets: ...  Batches: 64  Memory Usage: ...
  Buffers: temp written=...
```

These are two common signs of **sort or hash spilling to disk** (*spill to disk*). PostgreSQL tries to perform intermediate work in memory; when data or the algorithm exceeds the memory budget, the executor can use **temporary files** to finish sorting or partition hash batches. The query still returns accurate results, yet speed, I/O, and storage pressure can change dramatically.

This lesson focuses on the question: **How do you pinpoint the exact spilling node, understand why the spill happens, and choose a fix that benefits the entire system?**

Key topics:

- Distinguishing **in-memory sort**, **external sort**, **top-N heapsort**, and **incremental sort**.
- Understanding **Hash Join**, **HashAggregate**, **hash tables**, **buckets**, **batches**, memory, and temporary partitions.
- Reading `Sort Method`, `Disk`, `Memory Usage`, `Batches`, and `Buffers: temp read/written` in execution plans.
- Understanding `work_mem`, `hash_mem_multiplier`, parallel workers, and the risk of multiplying RAM consumption under concurrency.
- Observing temp files via `log_temp_files`, `pg_stat_database`, and `pg_stat_statements` when configured.
- Reducing spills via **properly ordered indexes**, **early filtering**, **narrower row width**, **lower cardinality**, **fixing statistics estimates**, **changing `GROUP BY`/`JOIN` approaches**, and controlled configuration tuning.
- Reproducing in a SQL lab, benchmarking workflow, troubleshooting, and Java/JDBC integration notes.

> **Scope:** Modern PostgreSQL, focusing on query plans and executor optimization. Exact plans and numbers depend on version, configuration, and data; illustrative figures are not guaranteed output from any specific server. Experiments changing `work_mem`, disabling plan methods, or generating large datasets should run only in a lab environment with adequate resources.

## 1. What Does “Spilling to Disk” Mean?

PostgreSQL has operators that require temporary working memory:

- `ORDER BY` may require a **Sort**.
- `DISTINCT` and `GROUP BY` may use **Sort/Unique**, **GroupAggregate**, or **HashAggregate**.
- `JOIN` may pick a **Hash Join**, building a hash table over one input.
- `WindowAgg` may require sorted input and in some cases use a tuplestore.
- `Materialize`, CTE materialization, and other nodes may also buffer intermediate results.

If data fits within the memory budget, PostgreSQL processes it in RAM. Otherwise, the executor **writes and re-reads intermediate data using temporary files**.

```text
                            Input data
                                │
                                ▼
                       Sort / Hash operator
                                │
                ┌───────────────┴────────────────┐
                │                                │
          Fits budget                     Exceeds budget
                │                                │
                ▼                                ▼
         Process in RAM                Partition batches / create runs
                │                      write temporary files
                │                                │
                │                                ▼
                │                      Re-read, process,
                │                      and/or merge
                └───────────────┬────────────────┘
                                ▼
                         Accurate result
```

Spilling is a **valid execution strategy**, not a SQL error. It becomes a performance problem when I/O, temp space, extra passes, or resource contention cross acceptable limits.

## 2. Not All Disk Activity Is a “Spill”

A query reading table or index pages from storage is not automatically spilling:

```text
Buffers: shared read=15000
```

refers to loading pages through the shared-buffer mechanism.

By contrast:

```text
Buffers: temp read=15000 written=22000
```

typically indicates executor temporary working files.

Distinguish:

| Activity | Typical Indicator | Target |
|---|---|---|
| Reading tables/indexes | `shared hit/read` | Relation pages. |
| Writing table/index pages | `shared dirtied/written` | Data/index pages. |
| Temporary tables | `local hit/read/dirtied/written` | Temporary relations via local buffers. |
| Sort/hash spills | `temp read/written`, Sort/Hash details | Intermediate working files. |
| Writing WAL | `WAL records/fpi/bytes` | Write-ahead log, distinct from temp files. |

**Do not confuse `CREATE TEMP TABLE` with temp files created by an external sort.** Both may use temp space, yet their buffer types, limits, and purposes differ.

## 3. Why Does Spilling Slow Queries Down?

An in-memory sort operates on data directly in RAM. During an external sort, the executor typically must:

1. Read source data.
2. Produce sorted pieces (*runs*) that fit in memory.
3. Write runs to temporary files.
4. Re-read those runs to merge them.
5. Emit results in the requested order.

A memory-starved Hash Join may:

1. Partition tuples by hash value.
2. Keep one partition in RAM.
3. Spill remaining partitions/batches to temporary files.
4. Re-read each batch and probe for matches.

Those extra reads and writes consume:

- I/O bandwidth and IOPS.
- CPU for hashing, partitioning, comparisons, and merging.
- Temporary disk space.
- CPU time and buffer cache shared with other parts of the query.
- Overall stability when many backends spill simultaneously.

**Spilling is not always dramatically slow**: if small, on fast storage, and under light load, the overhead may be acceptable. Performance tuning should judge by **execution time, variance, and total load**, not a rigid rule that “`temp_written` must equal 0.”

## 4. What Is `work_mem`?

`work_mem` configures the base memory budget for **certain execution operations such as Sort and Hash** before writing intermediate data to temporary files or switching to batched execution.

Inspect:

```sql
SHOW work_mem;

SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name = 'work_mem';
```

### Not the Maximum Memory for an Entire Query

This is the biggest misconception:

> “With `work_mem = 64MB`, each query uses at most 64 MB.”

False. A single query can contain **multiple Sort/Hash operators** active concurrently plus parallel workers. Each applicable operation receives its own memory budget. A query also allocates executor state, result buffers, caches, aggregation contexts, and session memory.

```text
A single plan can have:

Sort A              → work_mem budget
  └─ Hash Join       → hash budget: work_mem × multiplier
       ├─ Sort B     → work_mem budget
       └─ Hash       → suited hash budget

Parallel workers can multiply memory usage further.
```

Therefore, **never multiply `work_mem` once per query to estimate database-wide RAM usage**.

## 5. Why Is Setting Server-Wide `work_mem` Too High Dangerous?

Suppose a workload has:

- Many concurrent backend queries.
- Multiple Sort/Hash nodes per plan.
- Some queries running parallel workers.

Raising `work_mem` from a few MiB to hundreds of MiB instance-wide without checking concurrency can explode total RAM demand.

Conceptual **illustrative estimate, not an exact allocation formula**:

```text
20 concurrent queries
× 3 memory-heavy operators per query
× 64 MiB
= 3840 MiB budget for those operators alone

Before even counting parallel workers, hash_mem_multiplier, and other memory.
```

That is why a setting that tunes **one isolated query** can push the server into **OOM / memory exhaustion** when dozens of queries run concurrently.

### Memory Is Not Allocated All at Once

`work_mem = 64MB` does not mean every query immediately allocates 64 MB. Memory is allocated as operators need it, yet a high cap raises the ceiling when data grows large.

### Safe Strategy

Optimize **query structure** first, then test `SET LOCAL work_mem` inside a specific transaction. Raise the server-wide value only after analyzing concurrency and instance-level memory budgets.

## 6. What Is `hash_mem_multiplier`?

PostgreSQL provides `hash_mem_multiplier` to scale the memory limit for eligible hash operations **as a multiple of `work_mem`**.

Inspect:

```sql
SHOW hash_mem_multiplier;

SELECT
    current_setting('work_mem') AS work_mem,
    current_setting('hash_mem_multiplier')
        AS hash_mem_multiplier;
```

Conceptual model:

```text
Hash operation budget ≈ work_mem × hash_mem_multiplier
```

For example, with `work_mem = 16MB` and `hash_mem_multiplier = 2`, an eligible hash operation gets a target budget around **32 MB**.

### This Differs from Sort

Raising `hash_mem_multiplier` targets hash-based operations; it does not turn an external-merge `Sort` into quicksort.

### Why Not Increase Both Infinitely?

Like `work_mem`, the hash budget applies across multiple operations and backends. Raising the multiplier can stop hash spilling for one query while putting severe RAM pressure on concurrent joins and aggregates.

### Versions and Prerequisites

Available GUCs and valid bounds depend on PostgreSQL version. If an older server does not support `hash_mem_multiplier`, verify before running `SET` commands from this lesson.

## 7. Other Memory Settings Do Not Replace `work_mem`

| Parameter | General Role |
|---|---|
| `shared_buffers` | PostgreSQL's shared cache for table and index pages. |
| `work_mem` | Base memory for executor operations like sort and hash. |
| `hash_mem_multiplier` | Budget multiplier for hash operations. |
| `temp_buffers` | Local buffer memory for temporary tables within a session. |
| `maintenance_work_mem` | Memory for maintenance tasks such as `VACUUM` and `CREATE INDEX`. |
| `autovacuum_work_mem` | Memory for autovacuum workers when configured, inheriting defaults otherwise. |
| `effective_cache_size` | Cache-size hint for the planner's cost model, not a RAM allocation. |

An ordinary `ORDER BY` query does not use `maintenance_work_mem` instead of `work_mem` just because it has a `Sort` node, and raising `shared_buffers` does not directly add memory for external sorts.

**Identify the exact operator and memory context** before adjusting parameters.

## 8. How Does Sorting Work in PostgreSQL?

PostgreSQL uses different sort methods depending on plan and data volume:

- **Quicksort:** an in-memory sort.
- **Top-N heapsort:** keeps only the top candidates when only the first few sorted rows are needed.
- **External merge sort:** data exceeds memory, requiring sorted runs and merging via temporary files.
- **Incremental sort:** leverages an already-sorted prefix to sort smaller subgroups.

`EXPLAIN ANALYZE` may report:

```text
Sort Method: quicksort  Memory: 4120kB
```

or:

```text
Sort Method: top-N heapsort  Memory: 35kB
```

or:

```text
Sort Method: external merge  Disk: 40520kB
```

These numbers are illustrative only. The reported algorithm depends on how PostgreSQL actually executed the run.

### Not Every `ORDER BY` Creates a `Sort` Node

If an index or child node already supplies the required order, the planner can **omit the `Sort` node**. This is one of the best ways to prevent spills: **avoid sorting data if you can read it in order from the start**.

## 9. Setting Up the SQL Lab

Create schema:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_spill;
```

A transactional table:

```sql
CREATE TABLE lesson_spill.sales (
    sale_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    sold_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'CANCELLED')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    note TEXT NOT NULL
);
```

Insert 90,000 synthetic rows:

```sql
INSERT INTO lesson_spill.sales (
    sale_id,
    tenant_id,
    customer_id,
    product_id,
    sold_at,
    status,
    amount,
    note
)
SELECT
    g,
    1 + (g % 10),
    1 + (g % 2000),
    1 + (g % 45000),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g * INTERVAL '1 minute'),
    CASE WHEN g % 11 = 0
         THEN 'CANCELLED' ELSE 'PAID' END,
    ((g % 100000) + 1)::numeric / 100,
    repeat('x', 140) || '-' || g::text
FROM generate_series(1, 90000) AS g;
```

Add a fairly large table as a hash-join input:

```sql
CREATE TABLE lesson_spill.products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    description TEXT NOT NULL,
    category_id INTEGER NOT NULL
);

INSERT INTO lesson_spill.products (
    product_id,
    product_name,
    description,
    category_id
)
SELECT
    g,
    'Product ' || g::text,
    repeat('p', 180) || '-' || g::text,
    1 + (g % 500)
FROM generate_series(1, 45000) AS g;
```

Gather statistics:

```sql
ANALYZE lesson_spill.sales;
ANALYZE lesson_spill.products;
```

### Volume Warning

These row counts and text columns are enough for many lab machines to observe spills under small `work_mem`, without guaranteeing every version/planner picks identical nodes. On constrained environments, reduce row counts, noting that spills may be harder to trigger.

Never generate these 90,000 rows in a live production database just for practice.

## 10. First External Sort Test

Pick an ordering lacking direct index support:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT TEXT
)
SELECT
    sale_id,
    tenant_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

### Why `md5(sale_id::text)`?

There is no index on `md5(sale_id::text)` in the lab, so a `Sort` node will likely be chosen. Fetching all 90,000 rows gives the sort substantial data, while `work_mem='64kB'` keeps the memory budget tiny.

The plan may show:

```text
Sort
  Sort Key: (md5((sale_id)::text))
  Sort Method: external merge  Disk: ...kB
  Buffers: shared hit=..., temp read=... written=...
  -> Seq Scan on sales
       Buffers: shared hit=...
```

### Reading Each Indicator

1. `Sort` is the sorting node.
2. `Sort Method: external merge` shows the sort used external disk sorting.
3. `Disk` reports working space used by the `Sort` node.
4. `temp read/written` counts temporary blocks read/written during measurement.
5. The child `Seq Scan` still reads the base table, shown primarily under `shared hit/read`.

**Do not lump `shared read` and `temp read` together as “table reads.”** They measure two different mechanisms.

## 11. Comparing Against In-Memory Sort

Re-run the same query with a larger budget, **strictly inside the lab transaction**:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    tenant_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

On this lab data, you may see:

```text
Sort Method: quicksort  Memory: ...kB
```

with temp reads/writes reduced or eliminated. Still, some environments may continue using temp if working sets, tuple overhead, or plans exceed expectations.

### Fair Comparison

- Keep SQL and data identical.
- Keep all other settings identical.
- Run multiple iterations with warm-up runs.
- Record `Sort Method`, `Disk/Memory`, temp blocks, and runtime.
- Check whether the plan shape changed.
- Evaluate memory impact when many queries run concurrently.

This is a **root-cause experiment**, not proof that server-wide `work_mem` should be raised to 64 MB.

## 12. Temp Blocks in `EXPLAIN BUFFERS`

To observe spills:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
```

Output typically includes:

```text
Buffers: temp read=1500 written=2400
```

These are temporary block operations within the node's instrumentation scope. At an 8 KiB page size, 1,500 blocks correspond to roughly 12 MiB of **block accesses expressed in bytes**, yet:

- It does not guarantee 12 MiB of unique data.
- A single block can be read or written multiple times.
- The OS page cache may absorb the I/O without hitting physical SSD.
- Parent counters can include child node activity.

Check block size:

```sql
SHOW block_size;
```

### Why Don't `temp read` and `temp written` Always Match?

External sorts create runs and merge them across passes. Some blocks may be written without being re-read identically within measurement scope, or blocks may be read multiple times across passes. Never infer a temp-file leak solely because the two counters differ.

### Do Not Sum Across All Nodes

Example:

```text
Aggregate       temp read=100 written=150
  └── Sort      temp read=100 written=150
```

Do not sum these to 200 reads and 300 writes for the statement, as parent nodes **roll up child counters**.

## 13. `Sort Method`: `quicksort`, `external merge`, `top-N`

| Indicator | Typical Meaning | Analysis Direction |
|---|---|---|
| `quicksort Memory: ...` | Sort completed in memory. | Check whether sort is needed, rows/width—don't assume it's already optimal. |
| `external merge Disk: ...` | Sort used temporary files. | Investigate large rows/width, `work_mem`, indexes, `ORDER BY`. |
| `top-N heapsort Memory: ...` | Kept only top candidates to satisfy `LIMIT`. | Check `LIMIT`, input size, top-N index potential. |
| `Incremental Sort` | Exploited presorted prefix; sorted per group. | Check `Presorted Key`, group counts, memory, per-group spills. |

### Top-N Does Not Mean Reading Only N Rows

```sql
SELECT sale_id
FROM lesson_spill.sales
ORDER BY md5(sale_id::text)
LIMIT 20;
```

Without an index providing that order, the executor still **reads nearly all/all 90,000 rows** to identify the top 20, even though it only keeps 20 candidates in its heap.

Top-N shrinks sort memory, not input scan volume.

### In-Memory Sorts Still Burn CPU

A query sorting 1 million rows inside RAM still executes millions of key comparisons and data moves. Zero temp spill does not mean sorting is free.

## 14. `ORDER BY` and `LIMIT`: Two Separate Optimizations

Suppose a sales page needs a tenant's 20 newest orders:

```sql
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Two possible strategies:

**Without a matching ordered index:**

```text
Seq Scan/Bitmap Scan of tenant 3 orders
  → Top-N Sort
  → 20 rows
```

**With an index matching filter and order:**

```text
Index Scan on (tenant_id, sold_at DESC, sale_id DESC)
  → take first 20 matching rows
```

The second option both **eliminates the `Sort`** and **cuts rows read** via `LIMIT`.

## 15. Creating an Index to Support Ordering

```sql
CREATE INDEX ix_sales_tenant_recent
ON lesson_spill.sales (
    tenant_id,
    sold_at DESC,
    sale_id DESC
);

ANALYZE lesson_spill.sales;
```

Check:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

The planner can use the index to return rows already ordered, **omitting the `Sort` node**.

### Column Order Matters

`tenant_id` first narrows to the tenant. Trailing columns match `ORDER BY sold_at DESC, sale_id DESC`.

### Why Include `sale_id`?

`sold_at` can tie across multiple rows. Including `sale_id` in `ORDER BY` gives a **deterministic tie-breaker**, helpful for keyset pagination.

### Do Not Index Every `ORDER BY`

Every new index consumes disk/WAL and slows inserts, updates, and deletes. Create one only when the workload is important and net benefits are clear; verify with real `EXPLAIN` output rather than intuition.

## 16. `ORDER BY` Expressions Can Block Standard Indexes

Compare:

```sql
ORDER BY sold_at DESC
```

with:

```sql
ORDER BY date_trunc('day', sold_at) DESC
```

An index on `sold_at` does not automatically satisfy ordering by arbitrary **expressions** wrapping that column.

To avoid sorting, you may need to:

- Rewrite the query to use business-equivalent raw ordering.
- Add an expression index when the expression qualifies and workload warrants.
- Use a computed/generated column where appropriate.
- Accept the `Sort` if row count is small and indexing isn't worth the write cost.

**Never build an expression index on a function depending on session time zone or settings.** PostgreSQL requires index expressions to be *IMMUTABLE*.

## 17. `DISTINCT ON` and Ordered Indexes

Example fetching the newest order per customer in tenant 3:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY
    customer_id,
    sold_at DESC,
    sale_id DESC;
```

Without a matching order, PostgreSQL must `Sort` before picking the first row of each group.

An index that can help:

```sql
CREATE INDEX ix_sales_tenant_customer_recent
ON lesson_spill.sales (
    tenant_id,
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

For `tenant_id = 3`, the index orders by `customer_id` and newest-first within each customer, aligning with `DISTINCT ON` / `ORDER BY`.

### `DISTINCT ON` Rule

`DISTINCT ON` expressions must align with the leftmost prefix of `ORDER BY` per PostgreSQL rules. Without a deterministic tie-breaker, the “first” row per group is ambiguous.

### Read Real Plans

An index can eliminate `Sort`, yet does not guarantee scanning only one row per group. Depending on plan and version, the executor may scan all entries and have `Unique` pick the first row of each group. Always measure buffer accesses and runtime.

## 18. What Is `Incremental Sort`?

**Incremental Sort** exploits input **already sorted by a leading prefix** of `ORDER BY`.

Suppose a query requests:

```sql
ORDER BY tenant_id, amount DESC
```

while an index guarantees only:

```text
tenant_id ascending
```

Instead of buffering and sorting everything in one pass, PostgreSQL can sort **each tenant group independently** by `amount`.

```text
Input presorted by tenant_id prefix

tenant 1: [unsorted amounts]
tenant 2: [unsorted amounts]
tenant 3: [unsorted amounts]
             │
             ▼
Incremental Sort
  ├─ sort tenant 1 group
  ├─ sort tenant 2 group
  └─ sort tenant 3 group
             │
             ▼
Full result ORDER BY tenant_id, amount DESC
```

In the plan, you may see:

```text
Incremental Sort
  Sort Key: tenant_id, amount DESC
  Presorted Key: tenant_id
```

### When Does It Help?

- Many moderately sized groups instead of one giant sort.
- Input has a reliable presorted prefix.
- `LIMIT` lets execution finish early.
- Avoids large temporary run files.

Still, it is not always faster: if groups are huge, heavily skewed, or misestimated, incremental sort can still spill or run slow.

## 19. Testing `Incremental Sort` in the Lab

Create a prefix index:

```sql
CREATE INDEX ix_sales_tenant_only
ON lesson_spill.sales (tenant_id);

ANALYZE lesson_spill.sales;
```

Test:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, amount, sale_id
FROM lesson_spill.sales
ORDER BY tenant_id, amount DESC;
```

PostgreSQL **may pick** `Incremental Sort`, a full `Sort`, or another plan depending on cost and version; merely creating a prefix index does not force it.

To observe the alternative in the lab:

```sql
BEGIN;

SET LOCAL enable_incremental_sort = on;
SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT tenant_id, amount, sale_id
FROM lesson_spill.sales
ORDER BY tenant_id, amount DESC;

ROLLBACK;
```

`enable_seqscan=off` is strictly a diagnostic tool to explore alternative plans—it does not guarantee `Incremental Sort` and should never be left enabled casually in production.

## 20. How Does `Hash Join` Use Memory?

A Hash Join has two inputs:

1. One branch feeds **Hash** to build a hash table.
2. The other (**probe side**) scans rows and probes for hash matches.

```text
                  Hash Join
                 /         \
          Probe input      Hash
                             |
                         Build input
```

Example:

```sql
SELECT
    s.sale_id,
    p.product_name,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';
```

The planner chooses `Hash Join`, `Merge Join`, or `Nested Loop` based on statistics and cost.

### What Must the Hash Table Retain?

It does not necessarily retain every column of the source table. The executor keeps fields needed for hash keys, join predicates, and parent-node outputs. **Projection** and column pruning shrink the width stored in the hash table.

A Hash Join can split into multiple **batches**; groups not processed immediately are written to temporary files and read back later.

## 21. Buckets and Batches in a Hash Join

An illustrative plan:

```text
Hash Join  (actual rows=... loops=1)
  Hash Cond: (s.product_id = p.product_id)
  Buffers: shared hit=..., temp read=... written=...
  -> Seq Scan on sales s
  -> Hash
       Buckets: 2048  Batches: 64  Memory Usage: 150kB
       Buffers: shared hit=..., temp written=...
       -> Seq Scan on products p
```

**`Buckets`:** the number of buckets organized for the hash table in the execution plan.

**`Batches`:** the number of data-partitioning groups/passes used when the hash table cannot hold the full required set within allocated memory.

**`Memory Usage`:** the memory footprint reported by the `Hash` node through instrumentation.

### `Batches > 1` Is a Strong Signal Worth Checking

When a plan reports `Batches: 64`, the hash operation is using batching and may generate temporary I/O.

**Do not automatically assume every `Batches > 1` is a severe incident.** Inspect temp reads/writes, runtime, data size, and system resources.

### `Batches` Is Not the Worker Count

`Batches=64` does not mean there are 64 parallel workers or that PostgreSQL spawned 64 threads. It refers to partitioning/batching in the hash algorithm.

## 22. Reproducing a Hash Join Spill

Using the lab `sales`/`products` tables:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    s.sale_id,
    p.product_name,
    p.description,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';

ROLLBACK;
```

The goal is **observing a Hash Join under a tight memory budget**. Still inspect the plan: `enable_*` switches only affect cost/preferences, and PostgreSQL may choose another option depending on query semantics and version.

### Signals to Record

- Does `Hash Join` appear?
- Is there a `Hash` node with `Buckets`/`Batches`/`Memory Usage`?
- Is `Batches` greater than 1?
- Which node shows `Buffers: temp read/written`?
- What is the total `Execution Time`?
- Are estimated row counts close to actuals?
- Does the long `description` column contribute to the row width being processed?

Do not attempt optimization before identifying **which exact node causes the spill**.

## 23. Comparing Hash Join with Larger Hash Memory

Repeat with:

```sql
BEGIN;

SET LOCAL work_mem = '32MB';
SET LOCAL hash_mem_multiplier = 2.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    s.sale_id,
    p.product_name,
    p.description,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';

ROLLBACK;
```

Expected results in some environments:

- `Batches` drops, possibly down to 1.
- Temp blocks decrease.
- Execution Time improves if the hash spill was the bottleneck.

However:

- The plan may differ because GUCs changed.
- Caching differs between runs.
- I/O is not always the bottleneck.
- A hash table smaller than the budget does not automatically consume the full 64 MB.

### Increase `work_mem` or the Multiplier?

If **sort** spills: `work_mem` is the more important parameter.

If **hash** spills: look at `work_mem` and `hash_mem_multiplier` together.

If **everything spills** or the workload has many nodes: measure total RAM and consider fixing SQL/indexes/cardinality before raising global settings.

## 24. Hash Join: What Role Does the Build Side Play?

In a Hash Join, one input builds the hash table. **The size of the build side** strongly affects whether it fits in memory.

Join example:

```sql
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

If PostgreSQL builds the hash table from `products`, the row count and stored tuple width of `products` matter.

### Do Not Force the Build Side via JOIN Writing Order

Writing:

```sql
FROM sales s JOIN products p
```

does not guarantee PostgreSQL will always build the hash table from `products`. The planner can swap inputs or pick a different join algorithm.

### Ways to Reduce Pressure

- Filter the build side early when valid.
- Select only needed columns; avoid pushing wide payloads through the hash unnecessarily.
- Improve estimates so the planner knows which input is smaller vs. larger.
- Check whether an index, Nested Loop, or Merge Join fits actual selectivity better.
- Use staging/pre-aggregation when semantically appropriate.

## 25. “Passing `SELECT *` Into a Join” Can Make Spills Worse

Example:

```sql
SELECT *
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

The result carries the long `note` from `sales` and the long `description` from `products`, increasing row width and data flowing through the pipeline compared to a query needing only `sale_id` and `product_name`.

Compare with:

```sql
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

### Not Every Projection Shrinks the Hash Table

The planner performs **column pruning/projection**; even when an outer query selects many columns, not every column is retained in every node. Conversely, if a wide column genuinely must pass through an operator, it can increase memory and temp I/O.

To verify improvement, inspect `Plan Width`, actual memory, temp blocks, and runtime after the change. Never assume `SELECT *` is the sole culprit when a JOIN also multiplies rows due to cardinality.

## 26. What Is `HashAggregate`?

For:

```sql
SELECT
    customer_id,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM lesson_spill.sales
GROUP BY customer_id;
```

PostgreSQL may use **HashAggregate**:

```text
HashAggregate
  Group Key: customer_id
  -> Seq Scan on sales
```

The executor maintains an **aggregate state** for the groups, typically looked up by hash key.

### What Determines Memory Usage?

Not only input row count, but also:

- Number of distinct groups.
- Data type and width of group keys.
- Number of aggregate states and state size.
- Aggregate functions—especially those holding large states.
- Data skew and rows per group.
- Planner estimates and the hash memory budget.

With only 10 groups, `HashAggregate` can stay tiny even over millions of input rows. When nearly every row forms its own group, aggregate state can become large.

## 27. `HashAggregate` and Batches/Disk Usage

When `HashAggregate` cannot retain all states within budget, modern PostgreSQL has mechanisms to handle spilling/batching in supported scenarios.

An illustrative output:

```text
HashAggregate
  Group Key: (sale_id % 40000)
  Batches: 17
  Memory Usage: 321kB
  Disk Usage: 11520kB
  Buffers: shared hit=..., temp read=... written=...
```

### Three Metrics to Read Together

1. **`Batches`:** number of hash batching groups processed.
2. **`Disk Usage`:** working space on disk reported in the execution plan.
3. **`temp read/written`:** temporary file I/O activity.

**Do not treat `Disk Usage` as permanent database growth.** It is temporary working space used during execution.

## 28. Reproducing a `HashAggregate` Spill

On the 90,000-row lab dataset:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_sort = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id % 40000 AS group_key,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM lesson_spill.sales
GROUP BY sale_id % 40000;

ROLLBACK;
```

There are many group keys here. `enable_sort=off` only helps explore a hash-favoring plan; it does not force PostgreSQL to pick `HashAggregate` in every version or query semantics.

### What If `HashAggregate` Does Not Appear?

PostgreSQL might pick `GroupAggregate` with a `Sort` or another strategy. That is not a failed experiment. Record the actual plan, then check:

- Is `enable_hashagg` enabled?
- Is `HashAggregate` valid and supported for the query?
- Try `SET LOCAL enable_hashagg = on` in the lab.
- Inspect group cardinality and alternative plans the planner considers.

**Do not alter server-wide settings just to “force” a specific node into an example.**

## 29. `HashAggregate` vs. `GroupAggregate`

Two common approaches:

**HashAggregate:**

```text
Seq Scan
  → HashAggregate by group keys
```

**GroupAggregate:**

```text
Seq Scan
  → Sort by group keys
  → GroupAggregate
```

### Comparison

| Criterion | HashAggregate | GroupAggregate |
|---|---|---|
| Needs presorted input? | Not necessarily. | Usually requires input ordered by group keys; a Sort or index can supply it. |
| Memory structure | Hash table of aggregate states. | Aggregate state for the current group being processed; may need a prior sort. |
| Spill risk | Hash batching/spilling. | Sort spill if input is not already appropriately ordered. |
| Good fit | Many unordered `GROUP BY` cases. | When input is already ordered by group keys or sorting is cheap. |
| Ordered output? | Cannot be assumed to satisfy `ORDER BY`. | Even if a plan emits groups in key order, SQL still needs `ORDER BY` when required by business logic. |

### Optimization Trap

You see `HashAggregate` spilling and force `GroupAggregate`. But `GroupAggregate` must sort several million rows, and **the sort spills even worse**.

Always compare **the entire plan**, not just switching algorithms to make one kind of spill disappear.

## 30. Group Cardinality Is a Key Factor

Compare:

```sql
-- 10 tenants: few groups.
SELECT tenant_id, COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id;
```

with:

```sql
-- Many distinct groups.
SELECT sale_id % 40000, COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
```

Both scan 90,000 rows, yet the number of group states differs dramatically.

### Do Not Infer Memory from Input Rows Scanned

One million rows grouped into 5 buckets may require very little hash aggregate memory. Ten thousand rows across ten thousand groups with large aggregate states may require much more.

### Check Estimates

`EXPLAIN` reports `Plan Rows` at Aggregate alongside `Actual Rows` with `ANALYZE`. If estimated groups are many times lower than actuals, the planner may be overly optimistic about memory and cost.

That is an opportunity to improve statistics or rewrite the query—not necessarily a RAM configuration problem.

## 31. When Both `Hash Join` and `HashAggregate` Spill

A query may look like:

```text
HashAggregate
  └── Hash Join
        ├── Seq Scan sales
        └── Hash
             └── Seq Scan products
```

Both **Hash Join** and **HashAggregate** can consume substantial memory; some plans add a `Sort` above them for `ORDER BY`.

### Why Is Raising `work_mem` Hard to Predict?

A single change can:

- Reduce batches in Hash Join.
- Reduce batches in HashAggregate.
- Cause the planner to switch join/aggregate strategies.
- Increase peak memory per backend.
- Raise RAM pressure when many similar queries run together.

**Never tune one node while ignoring the overall plan and concurrency.**

## 32. Using JSON Output to Pinpoint the Spilling Node

On a read-only query:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT
    s.customer_id,
    COUNT(*),
    SUM(s.amount)
FROM lesson_spill.sales AS s
GROUP BY s.customer_id;
```

The JSON root is usually an **array** containing an object with `Plan`. Child nodes sit inside `Plans`.

An illustrative JSON fragment:

```json
[
  {
    "Plan": {
      "Node Type": "Sort",
      "Sort Method": "external merge",
      "Sort Space Used": 4500,
      "Sort Space Type": "Disk",
      "Temp Read Blocks": 900,
      "Temp Written Blocks": 1200,
      "Plans": [
        {
          "Node Type": "Seq Scan",
          "Relation Name": "sales"
        }
      ]
    },
    "Execution Time": 120.5
  }
]
```

**This example illustrates structure only**, not measured output from the `GROUP BY` query above. Actual fields and nodes depend on planner and version.

### Common Keys Needed

- `Node Type`.
- `Plans`.
- `Sort Method`, `Sort Space Used`, `Sort Space Type`.
- `Temp Read Blocks`, `Temp Written Blocks`.
- `Actual Rows`, `Actual Loops`.
- `Plan Rows` and `Plan Width`.
- Hash / HashAggregate memory and batch fields when present.

Any parser must tolerate missing keys because **not every node is a Sort/Hash and not every metric is emitted in every plan**.

## 33. Do Not Sum Temp Blocks Across All Nodes

JSON plan example:

```text
HashAggregate (Temp Written Blocks = 500)
  └── Sort (Temp Written Blocks = 500)
```

You cannot conclude total = 1000 just by seeing both numbers. A plan node can report counters rolled up from descendants, so summing every node **double-counts**.

### Method

1. Read total temp activity at the root or reported aggregate scope.
2. Walk the tree to find operators with `Sort Space Type='Disk'` or Hash batches/disk usage.
3. Read temp counters **locally along parent/child relationships**, never summing blindly.
4. Cross-check with `Actual Rows` and `Loops`.
5. When exact per-operator attribution matters, understand your version's instrumentation limits.

### Loops Matter Too

A `Sort` node can be invoked repeatedly inside a Nested Loop. Each individual sort may be small while total temp I/O becomes huge.

`actual rows=100 loops=1000` must be interpreted differently from `rows=100 loops=1`. With the same node type, loop count can completely change total cost.

## 34. Do Not Confuse Temp Byte Transfers with Disk Usage

`Disk Usage: 20MB` reports footprint/working space for a node at instrumentation time.

`temp written=10000 blocks` measures block write operations within the reported scope; with 8 KiB blocks, 10,000 block writes equal roughly 78 MiB of block transfers.

These are **two different metrics**:

- **Working-space size**: file/space footprint used.
- **I/O volume**: how many block operations occurred.

External merge can read and rewrite the same file regions multiple times, so I/O volume can exceed peak disk footprint.

### Do Not Treat `pg_size_pretty` of Temp Bytes as Disk Space Still Occupied

PostgreSQL typically cleans up temporary files when no longer needed. Cumulative temp bytes over time do not mean those files currently occupy all that space on disk.

## 35. Observing Temp Files via `log_temp_files`

`log_temp_files` is a GUC that logs temporary files created during execution above a size threshold.

Check it:

```sql
SHOW log_temp_files;

SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name = 'log_temp_files';
```

Commonly understood values:

| Value | Meaning |
|---|---|
| `-1` | Disables temp file logging (common default). |
| `0` | Logs all qualifying temporary files. |
| Positive number | Logs temporary files meeting or exceeding the size threshold in configured units, typically kB. |

Illustrative log entry:

```text
LOG: temporary file: path "base/pgsql_tmp/pgsql_tmp123.0",
     size 18874368
```

### Why Do Logs Differ from `EXPLAIN`?

- `EXPLAIN` shows the **node-level plan** and temp counters for one instrumented statement.
- `log_temp_files` reports qualifying **files** on the server, helping catch spilling queries without running `EXPLAIN` manually.
- Log entries may be written when the file is deleted/closed, not necessarily the instant the temp file is created.
- One query can create multiple files; one file does not correspond 1:1 to a `Sort` node.

### Configuration Privileges

Not every role can freely change `log_temp_files`; settings and admin rights depend on configuration and version. Never enable logging of all files in production without assessing log volume, logged data, and operational cost.

## 36. Correlating Temp Logs with SQL Statements

Temp-file log lines become far more useful when `log_line_prefix` includes:

- PID.
- Timestamp.
- Database/user.
- `application_name`.
- Transaction/session identifier if configuration allows.

From there you can correlate with SQL logs, tracing, or metrics.

### `application_name` Is Not a Trusted Identity Proof

Clients can set `application_name` themselves; it is a diagnostic label, not an authentication mechanism. Never use it in place of user/role permissions.

### Do Not Rely on Stale PIDs

PIDs can be reused once a backend exits. When diagnosing live activity, cross-check `backend_start` and session details—not merely a PID from a week-old log.

## 37. Observing `pg_stat_database.temp_files` and `temp_bytes`

PostgreSQL exposes cumulative database-level statistics:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    pg_size_pretty(temp_bytes) AS temp_bytes_pretty,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

Meaning:

- `temp_files`: number of temporary files created within the database statistics scope.
- `temp_bytes`: total bytes written to temporary files per the stats mechanism.
- `stats_reset`: timestamp when these statistics were reset.

These counters are **cumulative**, not scoped solely to the query you just ran. On a system with concurrent sessions, deltas between checks can include other sessions' work.

### Do Not Infer `temp_bytes` Is Peak Disk Usage

If `temp_bytes=200GB` accumulated over several days, that does not mean 200 GB of temp files sit on disk right at the moment of your `SELECT`.

### Controlled Delta Measurement

In a lab with virtually no other workload:

1. Record `temp_files`/`temp_bytes` before.
2. Run a spilling query.
3. Record again after the query finishes.
4. Compare the difference.

Even then, stats visibility depends on caching and flush timing; inside a long transaction, stats snapshots may not update as expected. Measure using short monitoring transactions.

## 38. `pg_stat_statements` for Finding High Temp-I/O Queries

When the `pg_stat_statements` extension is installed and configured, you can analyze by query fingerprint:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    temp_blks_read,
    temp_blks_written,
    LEFT(query, 160) AS query_excerpt
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
```

**Prerequisite:** The `pg_stat_statements` view exists only when the extension is installed in the target database and the module is loaded/configured per version requirements. If absent, the query errors—which does not mean PostgreSQL is creating zero temp files.

### Benefit

It answers “**Which SQL patterns** generate the most temporary block I/O across executions?” rather than inspecting a single manual `EXPLAIN`.

### Limitations

- **Aggregated** stats only—no full plan tree.
- One query fingerprint can represent many calls with varying input sizes.
- Mean runtime hides tail latency; inspect totals and distributions where extra telemetry exists.
- Temp reads/writes do not guarantee `Sort` is the cause (it could be Hash, Materialize, or others).
- Tracked statement entries have capacity limits and can be reset.

To investigate specific nodes, capture `EXPLAIN ANALYZE BUFFERS` in an appropriate environment.

## 39. GUCs Related to Temporary Files

| GUC | Role | Notes |
|---|---|---|
| `work_mem` | Budget for executor operations. | Multiple operators/connections multiply memory impact. |
| `hash_mem_multiplier` | Multiplier for hash operations. | Does not directly increase sort memory. |
| `temp_file_limit` | Limits total temporary file space a single process may use at once. | Distinct from total RAM budget; does not cover all temporary object types. |
| `temp_tablespaces` | Selects tablespaces for temporary objects/files per PostgreSQL rules. | Affects storage, permissions, and capacity. |
| `log_temp_files` | Logs temp files above a size threshold. | Increases log volume when verbose. |
| `track_io_timing` | Measures I/O timings when supported by configuration. | Carries measurement overhead. |
| `statement_timeout` | Limits statement duration. | Does not fix the root cause of spilling. |

### `temp_file_limit`

Inspect:

```sql
SHOW temp_file_limit;
```

A value of `-1` normally means **no configured limit**. `temp_file_limit` helps stop a runaway query from filling disk with working files, yet exceeding the limit **fails** the statement rather than automatically switching to a faster algorithm.

### `temp_tablespaces`

When storage tiers differ in speed or capacity, DBAs may route temporary files/objects accordingly. However, moving temp files onto a faster drive does not fix why a query processes excessive intermediate data and can create a different bottleneck.

## 40. Do Not Confuse `temp_file_limit` with `temp_buffers`

`temp_file_limit` primarily caps **temporary file** space used by a backend under applicable rules, such as sort/hash spill files.

`temp_buffers` configures local buffer memory for **temporary tables**.

Similarly:

- `temp_file_limit` is not a cap on all data stored inside `CREATE TEMP TABLE`.
- `temp_buffers` is not the budget for an `ORDER BY` external sort.

If a query runs `CREATE TEMP TABLE AS SELECT` and then sorts the data, it can use **both temporary relation storage and operator working files**. Keep them distinct when measuring resources.

## 41. When Temp Disk Fills Up

A large spilling query can fail because:

- The filesystem/tablespace holding temporary files runs out of space.
- `temp_file_limit` is exceeded.
- Permissions or temp storage hit errors.
- Many sessions write temp files concurrently.

This can cause the statement to fail and leave an explicit transaction in an aborted state.

### Response Workflow

1. Identify the SQL statement(s) and backends creating heavy temp space.
2. Inspect logs, `pg_stat_database`, `pg_stat_statements`, and execution plans.
3. Check disk capacity, tablespaces, and OS metrics.
4. Distinguish one huge query from many moderately spilling queries.
5. Roll back or clean up failed transactions properly.
6. Reduce intermediate data volume or memory pressure.
7. Adjust temp storage, capacity, or limits according to SLAs.

**Never manually delete files managed by PostgreSQL inside the temp directory** to “free space quickly” while the server is running; doing so can break active queries or system state.

## 42. Why Is Raising `work_mem` Not the First Step?

Suppose a query runs:

```sql
SELECT
    s.sale_id,
    p.description
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
ORDER BY p.description, s.sale_id;
```

The query may have to sort a wide combined result set. If data grows from 90,000 to 90 million rows, “just raising `work_mem`” becomes unsustainable.

Ask instead:

- Does the user really need **every row** or just the first page?
- Can we filter by tenant or time range first?
- Can we fetch IDs/sort keys first and load wide payloads afterward?
- Could an index provide the exact required order?
- Can we compute/aggregate before joining wide payloads?
- Is sorting on an expression truly necessary?
- How does the API paginate these results?

**Eliminating unnecessary work** generally pays off better than allocating more RAM for work you do not need to do.

## 43. Filtering Data Before Sorting

An unfiltered example:

```sql
SELECT sale_id, sold_at, note
FROM lesson_spill.sales
ORDER BY sold_at DESC;
```

must process a large row set.

If the business requirement only needs tenant 3 within a date range:

```sql
SELECT sale_id, sold_at, note
FROM lesson_spill.sales
WHERE tenant_id = 3
  AND sold_at >= TIMESTAMPTZ '2026-01-15 00:00:00+00'
  AND sold_at < TIMESTAMPTZ '2026-02-01 00:00:00+00'
ORDER BY sold_at DESC
LIMIT 100;
```

Row counts and retained columns can drop sharply. An index on `(tenant_id,sold_at DESC,sale_id DESC)` may also supply the ordering.

### Filters Must Match Business Logic

Never tack on `WHERE tenant_id=3` just to make a plan look good if a report genuinely needs all tenants. Optimization means answering **the exact business question** cheaply—not silently changing the output.

### Avoid Unnecessary Function Filters on Columns

```sql
WHERE date(sold_at) = DATE '2026-01-15'
```

differs from a range predicate on `sold_at` in index eligibility and time zone semantics. For timestamp data, use an appropriate half-open range after confirming application time zone rules.

## 44. Avoiding Wide-Payload Sorts: The Narrow-First Pattern

When returning a small slice after sorting, consider **selecting keys/IDs first and fetching wide payloads afterward**.

For example, when sorting by an unindexed expression while returning only 50 rows:

```sql
WITH top_sale_ids AS MATERIALIZED (
    SELECT
        sale_id,
        md5(sale_id::text) AS sort_key
    FROM lesson_spill.sales
    WHERE tenant_id = 3
    ORDER BY md5(sale_id::text), sale_id
    LIMIT 50
)
SELECT
    s.sale_id,
    s.note,
    s.amount
FROM top_sale_ids AS top_ids
JOIN lesson_spill.sales AS s
  ON s.sale_id = top_ids.sale_id
ORDER BY top_ids.sort_key, s.sale_id;
```

Idea:

1. The subquery fetches only `sale_id` + sort key.
2. The sort carries narrow columns with a `LIMIT`.
3. Once the 50 IDs are identified, the outer query fetches the wide `note` column.

### When Does This Hurt Rather Than Help?

- Fifty extra index lookups can cost more than sorting rows that were already relatively narrow.
- `MATERIALIZED` introduces an optimization fence / tuplestore that can constrain the planner.
- If the query returns all rows anyway, the pattern does not shrink output volume.
- If the sort key is non-deterministic, keep the exact computation and ordering to avoid altering results.

Measure `EXPLAIN ANALYZE BUFFERS` before and after; do not apply it assuming every CTE is faster.

## 45. Large `OFFSET` and Sorting/Pagination Cost

Example:

```sql
SELECT
    sale_id,
    sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20 OFFSET 30000;
```

Even though it returns 20 rows, PostgreSQL still must **skip the first 30,000 ordered rows** to reach the requested page. Without an index, sorting/scanning may have to handle a large dataset.

### Keyset Pagination

If the client already has the cursor from the previous page:

```sql
SELECT
    sale_id,
    sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
  AND (sold_at, sale_id) <
      (
        TIMESTAMPTZ '2026-02-01 10:00:00+00',
        45000
      )
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

This tuple comparison aligns with descending order on both columns in the example, allowing a suitable index to seek directly to the next position without skipping tens of thousands of rows.

### Semantics Notes

- The cursor must come from the last row of the previous page.
- Ordering must be total, so include a unique tie-breaker.
- Handle concurrent data changes according to application consistency requirements.
- With nullable sort keys or mixed `ASC`/`DESC` directions, cursor predicates become more complex.

Keyset pagination solves **paginated navigation workloads**; it does not replace a report that genuinely needs the entire dataset sorted.

## 46. Grouping by Fewer Columns

A report:

```sql
SELECT
    tenant_id,
    customer_id,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id, customer_id;
```

may produce fewer or more groups than:

```sql
SELECT
    tenant_id,
    customer_id,
    sold_at,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id, customer_id, sold_at;
```

Adding a timestamp column that distinguishes nearly every transaction can multiply group counts sharply, inflating hash aggregate memory.

### Never Drop Columns Just to Shrink Groups If It Changes Metrics

`GROUP BY tenant_id,customer_id` returns a **different business result** from `GROUP BY tenant_id,customer_id,sold_at`. Drop a column only when the report genuinely does not need per-timestamp granularity.

### Assess Data Grain

Before optimizing, identify:

- Does each output row represent a sale, customer, product, day, or tenant?
- Which columns uniquely identify a group?
- Does any join duplicate rows prior to `GROUP BY`?
- Do we truly need to aggregate across all raw detail rows?

Choosing the right **grain** often eliminates unnecessary intermediate groups.

## 47. Aggregating Before `JOIN` When Semantics Allow

Suppose we need total revenue per product along with the product name.

One way:

```sql
SELECT
    p.product_id,
    p.product_name,
    SUM(s.amount) AS revenue
FROM lesson_spill.products AS p
JOIN lesson_spill.sales AS s
  ON s.product_id = p.product_id
GROUP BY p.product_id, p.product_name;
```

Another way sums first:

```sql
WITH revenue_by_product AS (
    SELECT
        product_id,
        SUM(amount) AS revenue
    FROM lesson_spill.sales
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.product_name,
    r.revenue
FROM revenue_by_product AS r
JOIN lesson_spill.products AS p
  ON p.product_id = r.product_id;
```

Idea: collapse many sales rows down to **one row per product** before joining to the dimension table.

### When Can This Reduce Spills?

If joining produces very wide rows or inflates data flowing through an aggregate or sort, pre-aggregation can shrink intermediate row count and width.

### When Does It Not Apply?

- When aggregation depends on filters or columns from the dimension table that cannot be pushed down equivalently.
- When the join is not 1:1 on product—e.g., if `products` had multiple rows per key, pre-aggregating could alter the sum.
- When the SQL optimizer already finds an equivalent or better plan automatically.
- When the pre-aggregation itself creates a huge `HashAggregate` that also spills.

**Only rewrite when both SQL statements are semantically equivalent**, and confirm with test data/execution per project workflow (Content QA belongs to a separate stage of the workflow).

## 48. `EXISTS` Instead of `JOIN` for Existence Checks

When the goal is “fetch sales whose product belongs to a valid subset,” avoid a `JOIN` that multiplies rows whenever the dimension side is non-unique for the join predicate.

Semi-join pattern:

```sql
SELECT
    s.sale_id,
    s.amount
FROM lesson_spill.sales AS s
WHERE EXISTS (
    SELECT 1
    FROM lesson_spill.products AS p
    WHERE p.product_id = s.product_id
      AND p.category_id = 42
);
```

`EXISTS` directly expresses “at least one matching record exists.” PostgreSQL can plan this as a semi-join.

### Why Can This Help?

A standard `JOIN` emits multiple rows if the right side matches multiple rows. `EXISTS` checks only existence, avoiding unnecessary cardinality multiplication.

### In the Lab Case

`products.product_id` is a primary key, so joining on `product_id` does not duplicate rows here. This example illustrates the semantics; the payoff is larger when join predicates do not guarantee 1:1 matching.

**Do not replace `JOIN` with `EXISTS` if you need columns from the right-hand table or match counts.**

## 49. Choosing Another Join Algorithm When `Hash Join` Spills

If a Hash Join spills heavily, PostgreSQL may have alternatives:

- **Nested Loop** with an appropriate index lookup when the outer input is small.
- **Merge Join** when both inputs are already ordered by the join key or cheap to sort.
- **Hash Join** with improved settings or pruned inputs.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.tenant_id = 3
  AND s.sale_id BETWEEN 1000 AND 1100;
```

With only a handful of matching sales rows, a Nested Loop using `products_pkey` can be very efficient.

### Never “Disable Hash Join” Unconditionally

```sql
BEGIN;
SET LOCAL enable_hashjoin = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
ROLLBACK;
```

The snippet above **illustrates an investigation technique**, not runnable SQL since `SELECT ...` is a placeholder. `enable_hashjoin=off` lets you test an alternative plan, yet on a real query with millions of probes, Nested Loop can perform far worse than a spilling Hash Join.

Pick a plan only after **measuring total execution time and I/O**, not simply seeing temp bytes drop.

## 50. `Merge Join` May Still Need `Sort`

A Merge Join typically needs both inputs sorted by the join keys. Without indexes supplying that order, PostgreSQL can generate:

```text
Merge Join
  ├── Sort
  │    └── Seq Scan input A
  └── Sort
       └── Seq Scan input B
```

If the sorts are large, both branches **can also spill**.

### Takeaway

Switching Hash Join → Merge Join does not guarantee zero temporary I/O; sometimes you merely **trade a hash spill for a sort spill**.

If both inputs have indexes aligned with join keys and predicates, Merge Join can excel. Otherwise, compare the cost of sorting both inputs against hash batching.

## 51. How Can Bad Statistics Cause Spills?

The planner relies on estimates for:

- Total row counts.
- Filter selectivity.
- Distinct key counts.
- Value distribution/skew and correlations.
- Average row width.
- Multi-column correlation when suitable statistics exist.

Example:

```text
Estimated HashAggregate:
  500 groups

Actual:
  50,000 groups
```

The hash budget and plan choice may be poorly matched, leading to batching/spilling.

### Reading Estimated vs. Actual

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id % 40000 AS group_key,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
```

Compare estimated `rows=...` on the Aggregate node against `actual rows=...` and the true number of groups.

**Large estimation gaps do not always cause spills, yet they signal you should inspect statistics** before raising memory.

## 52. `ANALYZE` and Stale Statistics

After substantial table changes, statistics may no longer reflect the current data distribution.

```sql
ANALYZE lesson_spill.sales;
ANALYZE lesson_spill.products;
```

`ANALYZE` collects fresh planner statistics. It **does not increase `work_mem`**, delete temp files, or guarantee the best plan in every case.

### Goal

Help the planner:

- Estimate cardinality more accurately.
- Estimate group counts better.
- Choose better join orders and algorithms.
- Price Sort/Hash costs closer to reality.

### Do Not Run `ANALYZE` Habitually After Every Slow Query

Check `last_analyze`, `last_autoanalyze`, and data churn first. In production, `ANALYZE` consumes resources; schedule or run it per operational procedures.

## 53. Extended Statistics for Correlated Columns

For example, on `sales`, `tenant_id` and `customer_id` may not be independent. A query filtering both columns can suffer poor estimates if the planner assumes independence when default single-column stats lack correlation info.

PostgreSQL supports **extended statistics**:

```sql
CREATE STATISTICS st_sales_tenant_customer
    (dependencies, ndistinct, mcv)
ON tenant_id, customer_id
FROM lesson_spill.sales;

ANALYZE lesson_spill.sales;
```

Statistics kinds:

- **dependencies:** functional dependencies between columns.
- **ndistinct:** number of distinct value combinations.
- **mcv:** most-common value combinations.

### When Is This Useful?

When multiple predicates or group keys involve correlated columns and default estimates are way off.

### Limitations

Extended statistics are not a silver bullet for all joins/cardinalities, and not every stat type applies to every kind of estimate. In particular, **applicability to multi-table join selectivity has limits** depending on version and semantics; never promise that a single `CREATE STATISTICS` will cure every Hash Join spill.

After making changes, verify with `EXPLAIN` and real execution metrics.

## 54. Row Width in Planner Statistics

`EXPLAIN` reports `width=...` as an estimated average row size in bytes at that node—not JSON or HTTP payload size.

Example:

```text
Hash  (cost=... rows=45000 width=220)
```

A wide build side can require substantial memory.

### Actual Width Can Differ

PostgreSQL may store large values via TOAST, expressions and projections reshape row width, and planner stats are estimates. Therefore:

- Check which columns actually flow through the hash or sort.
- Avoid `SELECT *` when unnecessary.
- Watch for data skew and wide values.
- Do not apply `rows × width = exact work_mem`, as pointers, tuple overhead, and hash structures also consume space.

## 55. `DISTINCT` Can Use `HashAggregate` or `Sort`

```sql
SELECT DISTINCT
    customer_id,
    status
FROM lesson_spill.sales;
```

PostgreSQL may execute this via:

```text
HashAggregate
```

or:

```text
Sort
  → Unique
```

### A Common Mistake

Adding `DISTINCT` to “hide” duplicate rows caused by a broken `JOIN` condition. That can create a huge `HashAggregate` or `Sort` that spills heavily.

Fix **join cardinality** at the source:

- Join on the proper keys.
- Avoid joining a multi-row table when only `EXISTS` is needed.
- Pre-aggregate one side before joining when semantically equivalent.
- Verify tenant/organization filters so rows do not cross-join accidentally.

Never paper over logic bugs with `DISTINCT` and then throw memory at the slowdown.

## 56. Window Functions Can Produce Large Sorts

Example:

```sql
SELECT
    tenant_id,
    customer_id,
    sale_id,
    ROW_NUMBER() OVER (
        PARTITION BY tenant_id, customer_id
        ORDER BY sold_at DESC, sale_id DESC
    ) AS row_no
FROM lesson_spill.sales;
```

`WindowAgg` usually needs input ordered by partition and order keys, so PostgreSQL may insert a `Sort` or `Incremental Sort`.

A supporting index could be:

```sql
CREATE INDEX ix_sales_window_order
ON lesson_spill.sales (
    tenant_id,
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

### When Can You Avoid Full Window Computation?

If the application truly needs only **the single newest row per customer**, `DISTINCT ON` with proper ordering may help. Still compare:

- Semantics around ties and `NULL`s.
- Rows returned.
- Scan costs and index support.
- Whether a window filter can already be pushed down/optimized.

**Do not replace a window function with `DISTINCT ON` if business logic needs full rankings across all rows.**

## 57. `CTE MATERIALIZED` and Working Data

`MATERIALIZED` can direct PostgreSQL to materialize a CTE's result for reuse, depending on semantics and version:

```sql
WITH x AS MATERIALIZED (
    SELECT *
    FROM lesson_spill.sales
    WHERE tenant_id = 3
)
SELECT COUNT(*)
FROM x;
```

Never assume:

> “`MATERIALIZED` is always faster because it computes the CTE only once.”

A materialized CTE can block predicate pushdown and enlarge intermediate working sets. A large tuplestore can also use temporary files; while not strictly a Sort/Hash spill, it raises the same data-volume and memory/disk issues.

### Principle

Choose `MATERIALIZED` or `NOT MATERIALIZED` based on semantics and observed plans, never as a blanket “optimization hint” without benchmarking.

## 58. Planner Settings Affecting Spills

Relevant GUCs:

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'work_mem',
    'hash_mem_multiplier',
    'enable_hashjoin',
    'enable_hashagg',
    'enable_sort',
    'enable_incremental_sort',
    'max_parallel_workers_per_gather'
)
ORDER BY name;
```

### `SETTINGS` in `EXPLAIN`

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
```

This is a placeholder; replace `SELECT ...` with an actual lab query.

`SETTINGS` displays planner-relevant GUCs that differ from **built-in defaults**, not every setting in existence. If `work_mem` does not appear there, still run `SHOW work_mem` to confirm its active value.

### Comparing Two Environments

If environment A has `work_mem = 4MB` and B has `64MB`, spill differences may stem from the RAM budget. Yet other factors also differ:

- Data distribution.
- Statistics.
- Indexes and constraints.
- PostgreSQL version.
- Cache and I/O subsystem.
- Parallelism settings.

Hold comparable variables steady before attributing the difference to one cause.

## 59. Parallel Queries and Total Memory

A plan using `Gather`/`Gather Merge` with multiple workers can execute sort/hash operations across multiple processes:

```text
Gather Merge
  ├── worker 0 Sort ...
  ├── worker 1 Sort ...
  └── leader work ...
```

Each worker can have its own memory budget for applicable operations, raising **total RAM usage**. Some shared hash table mechanisms in parallel hash joins manage memory differently.

### Common Reasoning Errors

- `work_mem=16MB` does not mean the whole parallel query uses at most 16 MB.
- Do not blindly multiply worker counts by every node in the plan.
- `Workers Planned` does not guarantee all planned workers were actually launched.
- Temp counters may already aggregate worker activity; do not double-count.

### When Should Parallelism Be Tuned?

If a parallel query spills heavily while multiple queries compete for memory and I/O, adjust parallel worker limits cautiously and re-measure system-wide throughput. Parallelism reduces single-query latency in some cases and worsens resource contention in others.

## 60. JIT, CPU, and Runtime Not Always Matching Temp I/O

A plan can have noticeable temp writes even when most runtime is not spent on I/O. Conversely, a query with zero temp I/O can still be slow due to:

- CPU-heavy expressions.
- JIT compilation overhead.
- Row-by-row function calls.
- Lock waits.
- Large scans and cache misses.
- Transferring huge result sets over network/client.

### Additional Diagnostics

- `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`.
- `track_io_timing` if enabled/permitted.
- `pg_stat_activity.wait_event_type` and `wait_event`.
- OS and storage metrics.
- `pg_stat_statements` when configured.
- Application tracing.

Never assume every slow query containing a `Sort` is slow because of disk spilling; inspect **Sort Method** and actual temp counters.

## 61. `track_io_timing` and Temp Read/Write Times

Check:

```sql
SHOW track_io_timing;
```

When appropriately configured, PostgreSQL can report I/O timings in `EXPLAIN`, including instrumented read/write durations for supported I/O categories.

Example:

```text
I/O Timings: temp read=... write=...
```

Exact labels and detail depend on PostgreSQL version and instrumentation.

### Do Not Confuse Timing with Block Counts

`temp read=10000 blocks` measures operation volume; `temp read time=80ms` measures elapsed I/O time observed. Two queries with identical block counts can show very different timings due to storage, OS page cache, and concurrency.

### Measurement Overhead

`track_io_timing` adds timing collection overhead. Do not enable it globally in production just for one ad-hoc check without considering policy and load.

## 62. Comparing Warm Cache vs. Cold Cache

Suppose an external sort runs twice:

```text
Run 1:
  shared read=3000
  temp read=1000 written=2000
  Execution Time=180ms

Run 2:
  shared read=100
  shared hit=2900
  temp read=1000 written=2000
  Execution Time=140ms
```

Hypothetical numbers. When temp blocks stay similar while shared reads drop, table/index caches are likely **warmer** on the second run.

### Do Not Assume Temp Files Are Cached Like Shared Buffers

Temporary file I/O can benefit from the OS page cache, yet `shared_buffers` and executor temp files are distinct mechanisms. `shared hit` does not reflect OS page-cache hits on temp files.

### Designing Benchmarks

Run multiple iterations, record environment, cache state, and I/O timings—never run once before and once after and declare that changing `work_mem` yielded a 22% speedup.

## 63. `work_mem` and Connection Pools

A Java/Spring service has a pool of 40 connections. Each request runs a report with 2 `HashAggregate` nodes and 1 `Sort`:

```text
Multiple HTTP requests
       │
       ▼
Pooled connections (up to 40)
       │
       ▼
Each query can consume multiple work_mem budgets
       │
       ▼
Total RAM / temp I/O scales with concurrency
```

### Common Mistake

Setting `work_mem=256MB` server-wide because one query flew on an isolated laptop. When 40 requests hit concurrently, multiple operators per query can claim large budgets and create severe RAM pressure.

### Design Approach

- Limit concurrent heavy reports via queues or rate limiting.
- Use transaction-local settings for specific reports where appropriate.
- Tune SQL to reduce cardinality and row width.
- Avoid holding connections open during non-database application work.
- Monitor memory, `temp_files`/`temp_bytes`, and tail latency.
- Set timeouts/limits sensibly, but never use timeouts as a substitute for optimization.

## 64. `SET LOCAL work_mem` in JDBC

Java pattern (illustrated inside a method with `throws SQLException`):

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (Statement st = conn.createStatement()) {
            st.execute("SET LOCAL work_mem = '32MB'");
            st.execute("SET LOCAL hash_mem_multiplier = 2.0");
        }

        try (PreparedStatement ps = conn.prepareStatement("""
                SELECT customer_id, COUNT(*) AS sale_count
                FROM lesson_spill.sales
                WHERE tenant_id = ?
                GROUP BY customer_id
                """)) {
            ps.setInt(1, 3);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long customerId = rs.getLong("customer_id");
                    long saleCount = rs.getLong("sale_count");
                    // Process results; do not hold the transaction open long.
                }
            }
        }

        conn.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
```

Assumes `DataSource` and JDBC imports are declared. Inside a Spring-managed transaction, do not call `setAutoCommit`/`commit` directly on a connection managed by the transaction manager.

### Why Is `SET LOCAL` Appropriate?

`SET LOCAL` is transaction-scoped, preventing an elevated `work_mem` from leaking to later requests using the same pooled session after the transaction ends.

### Remaining Risks

- Long transactions tie up connections.
- Memory demand still scales with concurrency.
- One request can execute multiple operators and parallel workers.
- Drivers/ORMs may dispatch statements on separate connections if transaction boundaries are misconfigured.

**`SET LOCAL` prevents setting leakage; it does not make high `work_mem` harmless.**

## 65. Spring `@Transactional` and `SET LOCAL`

Pseudo-code:

```java
@Service
public class SalesReportService {
    private final JdbcTemplate jdbcTemplate;

    public SalesReportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public List<SalesCount> report(int tenantId) {
        jdbcTemplate.execute(
            "SET LOCAL work_mem = '32MB'"
        );

        return jdbcTemplate.query(
            """
            SELECT customer_id, COUNT(*) AS sale_count
            FROM lesson_spill.sales
            WHERE tenant_id = ?
            GROUP BY customer_id
            """,
            (rs, rowNum) -> new SalesCount(
                rs.getInt("customer_id"),
                rs.getLong("sale_count")
            ),
            tenantId
        );
    }
}
```

This is an illustrative skeleton: `SalesCount`, imports, and Spring configuration must be supplied in a real project.

### Key Conditions

- `@Transactional` must actually open a transaction via the proxy/transaction manager.
- Both statements must run on the connection bound to that transaction.
- `SET LOCAL` does nothing useful if the report query executes after the transaction has closed.
- Against read replicas, role permissions, settings, and workloads may differ from primary.

Never assume `@Transactional(readOnly=true)` prevents PostgreSQL from creating temp files. A read-only `SELECT` can still external-sort or hash-spill.

## 66. `SQLSTATE` When Exceeding `temp_file_limit`

If a query exceeds temporary file limits, PostgreSQL raises an error and cancels the statement.

In JDBC:

```java
try {
    ps.executeQuery();
} catch (SQLException e) {
    String sqlState = e.getSQLState();
    // Log SQLSTATE and redacted message.
    // Rollback transaction if it has failed.
    throw e;
}
```

Never hardcode a single `SQLSTATE` for every “disk full” failure when multiple root causes exist. Classify using the actual code, error metadata, logs, and storage state.

### Transaction Aborted

After an error in an explicit transaction, subsequent statements receive:

```text
SQLSTATE 25P02
current transaction is aborted
```

The fix is rolling back or using a valid savepoint—do not keep sending SQL into an aborted transaction.

### Do Retries Help?

If temp space ran out because the query itself demands too much disk, immediate retries often worsen contention. Reduce workload, expand capacity, tune limits, or optimize the plan before retrying.

## 67. `EXPLAIN ANALYZE` Has Cost

`EXPLAIN (ANALYZE)` **actually executes the SQL statement** and collects instrumentation overhead.

For a heavy `SELECT`, it can:

- Scan large volumes of data.
- Create temporary files.
- Warm or evict caches.
- Consume significant CPU and I/O.
- Acquire locks or hold snapshots depending on SQL and isolation.

For DML, it also incurs data writes, triggers, and WAL generation.

### `TIMING OFF` When Only Counters Are Needed

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
```

`TIMING OFF` cuts part of per-node timing overhead, yet the statement **still runs** and temp I/O can still occur.

Avoid repeatedly running a full external sort in production just to read three counters.

## 68. Running `EXPLAIN` on DML Requires Care

Example:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE lesson_spill.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;

ROLLBACK;
```

Rolling back the transaction reverts row modifications, yet WAL was still generated, locks and buffer activity occurred, and external side effects may exist. Sequence values do not roll back either.

This lesson focuses on `SELECT` sorting/hashing to avoid unnecessary write side effects.

## 69. `log_temp_files` and Files Deleted After Query Completion

Some log entries appear **only when temporary files are deleted**, such as at query completion or context cleanup.

Therefore, while a query is actively running:

- Temp files may already occupy disk while **no complete log entry** exists for them yet.
- `pg_stat_database.temp_files` is cumulative and updates differently from inspecting live files on disk.
- OS-level disk usage can spike temporarily.

### Proper Monitoring

Combine:

1. PostgreSQL metrics.
2. Free space on temporary tablespaces.
3. Log events.
4. Application/query tracing.
5. `EXPLAIN ANALYZE` when safely reproducible.

Never treat logs alone as a snapshot of current disk usage.

## 70. Impact of Temp Spills on Replication

Sort/hash temporary files **are not replicated via WAL as permanent table modifications**. Even so, queries running on either primary or standby consume that node's CPU, I/O, and temp capacity.

### Read-Only Queries on Replicas

A heavy report running on a standby can create temp files on the standby, causing I/O contention and slowing read traffic—even without running a write transaction.

### Do Not Confuse `temp_bytes` with WAL Bytes

`temp_bytes` tracks working files; `WAL Bytes` tracks log generation. A huge sorting `SELECT` can generate gigabytes of temporary I/O with virtually zero WAL.

This informs workload placement: a replica can offload heavy reads from the primary, yet still needs sufficient local temp disk and RAM while accounting for replication lag and recovery conflicts.

## 71. Why Can Sort and Hash Spills Happen in the Same Query?

Example:

```sql
SELECT
    p.category_id,
    COUNT(*) AS sale_count,
    SUM(s.amount) AS revenue
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
GROUP BY p.category_id
ORDER BY revenue DESC;
```

The plan may look like:

```text
Sort (ORDER BY revenue)
  └── HashAggregate (GROUP BY category_id)
       └── Hash Join
            ├── Seq Scan sales
            └── Hash
                 └── Seq Scan products
```

Potential memory pressure points:

- Hash build for the JOIN.
- `HashAggregate` group states.
- Final `Sort` on `revenue`.

In this specific example, there are only ~500 categories, so the final `Sort` and `HashAggregate` may both stay small. **Never assume all three operators spill just because all three appear in the tree.**

### Finding What Actually Generates Temp I/O

Read `Sort Method`, Hash `Batches`, HashAggregate `Batches`/`Disk Usage`, and temp counters on each node in the measured plan.

## 72. Changing `ORDER BY` Can Alter Memory Demand

Example:

```sql
SELECT
    customer_id,
    COUNT(*) AS n
FROM lesson_spill.sales
GROUP BY customer_id
ORDER BY n DESC;
```

There are only ~2,000 customers in the lab, so sorting runs over **2,000 post-aggregate groups**, not 90,000 raw input rows.

Conversely, if a query needlessly sorts rows prior to aggregation:

```sql
WITH pre_sorted AS MATERIALIZED (
    SELECT *
    FROM lesson_spill.sales
    ORDER BY amount DESC
)
SELECT customer_id, COUNT(*)
FROM pre_sorted
GROUP BY customer_id;
```

the `Sort` inside the CTE performs wasted work for an aggregate that does not require `amount` ordering.

### Takeaway

Ask: **Which `ORDER BY` is genuinely needed for the final output?** Intermediate ordering only matters if a downstream operator relies on it or business semantics require it. Removing an unneeded sort usually beats allocating more memory for it.

## 73. Cases Where Sorting Must Be Kept

You cannot drop `ORDER BY` when:

- The API contract guarantees sorted output.
- `LIMIT` must select the exact top N rows.
- A window function requires a specific order.
- `DISTINCT ON` needs ordering to pick each group's representative row.
- Pagination depends on stable ordering.
- A downstream operator/algorithm relies on ordered input in the plan.

### Optimization Never Overrides Semantics

If a report requires descending revenue order, dropping `ORDER BY revenue DESC` yields unguaranteed output order.

The right path is reducing rows entering the sort (such as aggregating first), supporting order with an index, or assigning scoped memory budgets.

## 74. Correlated Subqueries and Many Small Sorts

A query may invoke the same sort repeatedly—for instance, picking the 3 latest orders per customer via a correlated subquery:

```sql
SELECT
    c.customer_id,
    recent.sale_id,
    recent.sold_at
FROM (
    SELECT DISTINCT customer_id
    FROM lesson_spill.sales
) AS c
CROSS JOIN LATERAL (
    SELECT
        sale_id,
        sold_at
    FROM lesson_spill.sales AS s
    WHERE s.customer_id = c.customer_id
    ORDER BY sold_at DESC, sale_id DESC
    LIMIT 3
) AS recent;
```

Without an index on `(customer_id, sold_at DESC, sale_id DESC)`, each subquery invocation can scan and sort many rows.

### Suitable Index

```sql
CREATE INDEX ix_sales_customer_recent
ON lesson_spill.sales (
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

When an index supports top-3 lookups per customer, repeated sorts can disappear or shrink sharply.

### When Is `LATERAL` Not Ideal?

With millions of customers, millions of index lookups can create heavy random I/O; a global `WindowAgg` or `DISTINCT ON` plan might perform better. Always benchmark with realistic workloads.

## 75. Does Index-Only Scan Solve Spilling?

An index-only scan reduces heap page reads under favorable conditions, yet it **does not automatically eliminate `Sort` or `Hash`**.

For example, an index may include all needed columns while the query sorts by a different expression:

```sql
SELECT sale_id, amount
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
```

Even if an index covers `sale_id` and `amount`, an `md5(...)` ordering unsupported by the index still requires a `Sort`.

### Visibility Map Matters Too

Whether an index-only scan avoids heap fetches depends on the visibility map and MVCC state. Never assume an `INCLUDE` index guarantees 100% index-only serving across every execution.

## 76. Temp Files Are Not Permanent Bloat

Working files from external sorts are typically cleaned up once no longer needed. Table/index bloat stems from MVCC tuple versions, `VACUUM`, and relation storage allocation.

| Issue | Symptoms | Remediation Path |
|---|---|---|
| Spill temp files | `temp read/written`, `log_temp_files`, Sort/Hash disk usage. | Reduce data/intermediate size, tune `work_mem`/hash budgets, indexes/SQL. |
| Table/index bloat | Growing relation size, dead tuples, `VACUUM` visibility issues. | Investigate MVCC, autovacuum, and update patterns. |
| WAL growth | High WAL records/bytes, replication slots/retention. | Investigate write volume, replication, and retention. |
| Shared cache misses | High `shared read`, I/O timings. | Index/query patterns, caching, storage, data locality. |

Never run `VACUUM FULL` to “clean up Sort temp files.” Those are completely different mechanisms, and `VACUUM FULL` carries heavy locking and rewrite cost.

## 77. Distinguishing One Spilling Operator from Server-Wide RAM Exhaustion

A Sort spill does not prove the server is out of physical RAM.

PostgreSQL deliberately writes temporary files because **`work_mem` limits** that operator, even when the OS still has plenty of free RAM.

Conversely, zero spills can coexist with severe memory pressure when many operators and connections consume RAM concurrently.

### Two Layers of Questions

**At the query level:**

- Which operator is spilling?
- Why is its input or intermediate set large?
- Is there an index or SQL rewrite?
- Which memory budget applies?

**At the instance level:**

- How many queries run concurrently?
- What is peak RSS/memory consumption?
- Is the OS swapping or hitting OOM?
- What is temp disk bandwidth and free space?
- What are connection pool and concurrency limits?

Never diagnose whole-host memory health from a single `EXPLAIN`.

## 78. When Should Raising `work_mem` Be Considered?

Raising `work_mem` can make sense when:

- The query genuinely must sort or hash large intermediate datasets.
- Reasonable index and SQL rewrites have already been evaluated.
- Spilling is clearly the bottleneck.
- RAM headroom exists for concurrent workload.
- Benchmarks confirm improved latency/throughput.
- A rollback plan exists if memory pressure rises.

### When Not To?

- A query returning 20 rows is sorting a million rows for lack of an index.
- A flawed join is multiplying rows.
- Many heavy reports run concurrently.
- Memory pressure or OOM risk already exists.
- Severe data skew or stale statistics distort plans.
- Temp file I/O is tiny and does not impact SLAs.

**Giving more RAM to a bad plan may make that query faster while leaving unnecessary work and concurrency risk intact.**

## 79. Scoping `work_mem` by User, Role, or Workload

PostgreSQL supports multiple configuration scopes, such as:

- Server-level setting.
- Database/role-level setting where privileges permit.
- Session-level `SET`.
- Transaction-local `SET LOCAL`.

For memory-heavy reports running only a few times a day, transaction-local tuning is usually safer to control than raising the global setting for all traffic.

### Caveats

- Role-level settings affect every query run by that role.
- Connection pools reuse sessions across requests.
- Unreset session `SET` statements can leak settings across requests.
- `SET LOCAL` applies strictly within the current transaction.
- Transaction pooling proxies (like PgBouncer) require verifying session vs. transaction semantics.

Never reuse a shared admin role across the whole application and bump `work_mem` indiscriminately for every endpoint.

## 80. Quick Lab Comparison Queries

**A — Sort spill:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**B — In-memory sort:**

```sql
BEGIN;
SET LOCAL work_mem = '64MB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**C — Hash Join with tight budget:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT s.sale_id, p.description
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
ROLLBACK;
```

**D — `HashAggregate` with many groups:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_sort = off;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id % 40000, COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
ROLLBACK;
```

**E — Index avoiding top-N Sort:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

**F — Database-wide temp counters:**

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

**G — JSON execution plan:**

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT customer_id, COUNT(*)
FROM lesson_spill.sales
GROUP BY customer_id;
```

In every measurement run, record **SQL, dataset, PostgreSQL version, settings, and the actual plan**—never stamp something “good” merely because `temp_written=0`.

## 81. Diagnostic Runbook for Sort/Hash Spills

### Step 1 — Identify the Exact SQL

Locate queries with high latency or high temp I/O from logs, application tracing, and `pg_stat_statements`. Capture parameter values sufficient for reproduction without collecting secrets or PII.

### Step 2 — Characterize Data Volume

Measure row counts, group cardinality, row widths, filter selectivity, and join multiplicities. One large tenant's data profile can look nothing like a small tenant's.

### Step 3 — Capture the Execution Plan Safely

Run `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)`; consider `TIMING OFF` when only counters are needed. Never run risky DML in production merely to measure.

### Step 4 — Pinpoint the Spilling Node

Look for `Sort Method: external merge`, `Sort Space Type: Disk`, `Hash` `Batches > 1`, `HashAggregate` `Disk Usage`, and `Temp Read/Written Blocks`.

### Step 5 — Check Estimates

Compare `Plan Rows` vs. `Actual Rows`, loops, group counts, and widths. If mismatches are large, inspect `ANALYZE`, stats freshness, and extended statistics.

### Step 6 — Ask Whether the Operator Can Be Eliminated

Consider indexes satisfying `ORDER BY`, keyset pagination, top-N limits, earlier `WHERE` filters, `DISTINCT ON`, and avoiding unnecessary materialization or sorts.

### Step 7 — Shrink Intermediate Size

Drop unneeded wide columns, avoid `SELECT *`, pre-aggregate, fix join cardinality, use `EXISTS` instead of duplicating joins, and remove `DISTINCT` hiding logic bugs.

### Step 8 — Compare or Tune Algorithms

Compare Hash Join vs. Merge Join vs. Nested Loop; `HashAggregate` vs. `GroupAggregate`. Measure both temp I/O and total execution time—never force the planner blindly.

### Step 9 — Test Scoped Memory Budgets

Test `SET LOCAL work_mem` and `hash_mem_multiplier` inside a lab transaction; evaluate RAM demand under realistic concurrency and parallelism.

### Step 10 — Verify Temp Capacity and Guardrails

Check `temp_file_limit`, `temp_tablespaces`, free disk space, OS metrics, and rate limits on heavy reports. Making one query fast is useless if 100 concurrent runs trigger OOM.

### Step 11 — Benchmark Across Multiple Runs

Include warm-up, equivalent data, cache context, version, and settings. Compare median/tail latencies and throughput—not one `EXPLAIN`.

### Step 12 — Monitor Post-Deployment

Track `pg_stat_database.temp_bytes`, top temp-consuming queries, query runtimes, free disk space, memory usage, and error trends. Keep a rollback plan ready if other workloads suffer.

## 82. Remediation Selection Matrix

| Symptom | Hypothesis | First Measures to Try |
|---|---|---|
| `Sort external merge`, `ORDER BY` + `LIMIT` | Sorting many rows just to pick a few. | Filter/order-aligned index, keyset pagination, top-N, narrow projection. |
| Sort spill on whole report | Large dataset or wide rows. | Prune columns, filter validly, pre-aggregate, then test `work_mem`. |
| High `Hash Join` `Batches` | Large build side or tight memory. | Filter build side, shrink width, check stats, evaluate join alternatives/hash budget. |
| `HashAggregate` with many `Batches` | Very many groups or large aggregate states. | Inspect group cardinality, pre-aggregate, update stats, evaluate `GroupAggregate`/index. |
| High `temp written` yet small `Sort` | Spill likely inside Hash or Materialize elsewhere. | Read the entire plan tree, not just the root. |
| Temp blocks jumped after deploy | Plan, input/cardinality, or concurrency changed. | Diff plans, version, stats, settings, and datasets. |
| Zero spill yet still slow | CPU, table/index I/O, locks, or client transfer. | Inspect other `EXPLAIN` metrics, wait events, and profiling. |
| Temp disk full | Huge query or too many concurrent spills. | Rate-limit workload, check capacity/limits, fix SQL; never delete live temp files manually. |
| Env A fast, Env B spills on same SQL | Different configs, datasets, stats, plans, or parallelism. | Compare `SETTINGS`, table sizes, stats, and actual plans. |

## 83. Common Misconceptions

**“A `Sort` node means spilling to disk.”** False. Check `Sort Method` or temp counters; `quicksort` and `top-N heapsort` can run entirely in RAM.

**“Hash Join always spills on large tables.”** False. It depends on build-side size, projection, and memory budget.

**“`Batches > 1` means the query is broken.”** False. Batching is a valid execution mechanism; evaluate actual runtime and I/O impact.

**“`work_mem` caps total RAM for an entire backend.”** False. It applies individually to eligible operators, not the whole process memory footprint.

**“With `work_mem=64MB`, 100 queries use at most 64 MB total.”** False. Concurrency, multiple operators, and parallelism multiply memory use.

**“Raising `hash_mem_multiplier` fixes `Sort` external merge.”** Not directly. It targets hash-based operations.

**“Raising `shared_buffers` gives `Sort` more `work_mem`.”** False. They are separate memory contexts.

**“`temp_buffers` controls sort spilling.”** False; it governs local buffers for temporary relations.

**“`temp_file_limit` reduces I/O with no side effects.”** False. Hitting the limit causes the statement to error.

**“`temp_bytes` is the size of temp files currently on disk.”** False. It is a cumulative counter.

**“`temp read=1000` means the SSD served 1,000 physical reads.”** False. OS page caching and block-access accounting must be considered.

**“`temp read + written` equals unique temp file size.”** False. The same block can be written and read multiple times.

**“`Disk Usage` and `temp_bytes` measure the same thing.”** False. Working-space footprint differs from cumulative I/O transfer volume.

**“Sum temp counters across every plan node to get the total.”** Wrong whenever parent nodes roll up child activity.

**“Raise `work_mem` until `temp=0` and you are optimal.”** False. Peak concurrency can still exhaust server RAM.

**“With `temp=0`, PostgreSQL creates zero files elsewhere.”** False; temporary files from other operations can still occur depending on context.

**“Top-N heapsort reads only N rows.”** False. Without an index supplying that order, it normally evaluates many rows.

**“An index only needs the `WHERE` columns to avoid `Sort`.”** False. Column order and `ORDER BY` directions matter too.

**“`Incremental Sort` always beats full `Sort`.”** False. Huge groups, skew, or misestimates can make it worse.

**“`HashAggregate` guarantees ordered output.”** False. Always include `ORDER BY` when ordering is required.

**“`GroupAggregate` always avoids disk because it does not hash.”** False. Its input `Sort` can still spill.

**“`Merge Join` always beats `Hash Join` when hash spills.”** False. Merge Join may introduce two external sorts.

**“Simply removing `SELECT *` guarantees `Hash Join` will not spill.”** False. Planner pruning and row cardinality govern actual memory demand.

**“`CTE MATERIALIZED` always saves computation.”** False. It can block predicate pushdown and build large working sets.

**“Adding `DISTINCT` to hide `JOIN` duplicates is free.”** False. It can trigger massive `Sort` or `HashAggregate` work.

**“`ANALYZE` stops queries from spilling.”** False. Statistics refine planner estimates without adding memory or changing required computation.

**“`EXPLAIN ANALYZE` only predicts a plan.”** False. It executes the real SQL.

**“`log_temp_files=0` disables logging.”** False. `0` logs all qualifying temp files; `-1` is the standard disable setting.

**“Fast NVMe temp storage fixes bad JOINs.”** False. It only softens I/O latency while wasting work and resources.

**“One faster run proves tuning worked.”** False. Test multiple runs and account for caching and concurrency.

## 84. Practice Exercises

### Exercise 1 — Distinguishing `shared` and `temp`

Run `EXPLAIN (ANALYZE, BUFFERS)` for a `Sort` on `sales`. Explain the difference between `shared read` and `temp read`. Why are they not the same kind of disk access?

### Exercise 2 — External Sort

With `SET LOCAL work_mem='64kB'`, sort all 90,000 rows by `md5(sale_id::text)`. Locate `Sort Method`, `Disk`, `Temp Read Blocks`, and `Temp Written Blocks`.

### Exercise 3 — In-Memory Sort

Repeat Exercise 2 with `work_mem='64MB'`. If `Sort Method` switches to `quicksort` and temp I/O drops, which other variables must be held constant before concluding higher memory improved speed?

### Exercise 4 — Converting Blocks to Bytes

Use `SHOW block_size` and convert 2,000 temporary blocks into MiB. Why does that figure not equal live SSD space occupied at a single instant?

### Exercise 5 — Top-N

Run the same `ORDER BY md5(...)` query with and without `LIMIT 20`. Compare `Sort Method` and shared-buffer accesses. Why can Top-N still scan nearly the whole table?

### Exercise 6 — Index Avoiding Sort

Create an index on `(tenant_id,sold_at DESC,sale_id DESC)`. Test the query fetching the 20 newest orders for tenant 3. Does a `Sort` node remain? How does `LIMIT` cut rows read?

### Exercise 7 — Index Column Order

Compare `(sold_at,tenant_id)` against `(tenant_id,sold_at DESC)` for `WHERE tenant_id=3 ORDER BY sold_at DESC`. Why does index column ordering affect whether `Sort` can be avoided?

### Exercise 8 — `DISTINCT ON`

Fetch the newest order per customer in tenant 3 using `DISTINCT ON`. Propose an appropriate index. Why should the `sale_id` tie-breaker be considered?

### Exercise 9 — `Incremental Sort`

Create an index on `tenant_id` and run `ORDER BY tenant_id,amount DESC`. If the plan uses `Incremental Sort`, note `Presorted Key`. When can sorting per group cut memory use?

### Exercise 10 — Tight-Memory Hash Join

Inside a lab transaction, set `SET LOCAL work_mem='64kB'` and `hash_mem_multiplier=1.0`. Run the `sales`/`products` join and inspect the `Hash` node. What do `Buckets`, `Batches`, and `Memory Usage` mean?

### Exercise 11 — Hash Join with More Memory

Repeat Exercise 10 with `work_mem='32MB'` and multiplier `2.0`. Record changes in `Batches`, temp reads/writes, and execution time. Why shouldn't you push those settings straight to production?

### Exercise 12 — Build-Side Width

Compare a join selecting only `product_name` against one needing long `description`. Inspect `Plan Width` and temp I/O; explain why projection helps without promising every node retains every column verbatim.

### Exercise 13 — `HashAggregate` with Few Groups

Run `GROUP BY tenant_id`. How many groups does `HashAggregate` track? Compare group state count against `GROUP BY sale_id % 40000`.

### Exercise 14 — `HashAggregate` Spill

Set `work_mem='64kB'` and test `GROUP BY sale_id % 40000`. If PostgreSQL picks `HashAggregate`, inspect `Batches` and `Disk Usage`. If it picks `GroupAggregate`, explain why you cannot assume hash spilling from SQL text alone.

### Exercise 15 — `GroupAggregate` vs. `HashAggregate`

Compare both plans for the same `GROUP BY` using transaction-local `enable_*` experiments. When does an external-merge `Sort` appear before `GroupAggregate`? Why is `temp bytes = 0` alone insufficient?

### Exercise 16 — Stale Statistics

Insert extra lab data and compare estimated vs. actual rows before and after `ANALYZE`. When group estimates are wrong, how can `HashAggregate` be affected?

### Exercise 17 — Extended Statistics

Run `CREATE STATISTICS ... (dependencies,ndistinct,mcv) ON tenant_id,customer_id` followed by `ANALYZE`. Explain how combined statistics improve estimates, and why they are not guaranteed to fix every join selectivity.

### Exercise 18 — `DISTINCT` Masking a Bad `JOIN`

A query joins order lines with tags, multiplying rows, and applies `DISTINCT` over the entire output. Analyze whether `EXISTS`/semi-join better expresses intent and reduces `Sort`/`HashAggregate` work.

### Exercise 19 — Aggregating Before `JOIN`

Write both versions of total revenue per product: aggregating after the join, and aggregating `sales` before joining `products`. State the conditions required for equivalence and why one reduces intermediate width.

### Exercise 20 — Early Filtering

A report needs only tenant 3 and January 2026, yet the query scans the whole table. Write a half-open `timestamptz` range filter, then measure row counts and temp blocks.

### Exercise 21 — Narrow-First

An API returns 50 rows sorted by an expression while needing the wide `note` column. Design a query fetching sale IDs and sort keys first, then joining back for payloads. When might this pattern not pay off?

### Exercise 22 — Keyset vs. `OFFSET`

Compare `LIMIT 20 OFFSET 30000` with descending keyset pagination on `(sold_at,sale_id)`. What prerequisites ensure stable pagination?

### Exercise 23 — Parallel Workers

When a plan uses `Gather Merge` with multiple sorting workers, explain why `work_mem` can apply multiple times and why you must not mechanically multiply root temp counters by worker count.

### Exercise 24 — `log_temp_files`

Explain `log_temp_files=-1`, `0`, and positive thresholds. Why can logging every temp file in production flood logs?

### Exercise 25 — `pg_stat_database`

Inspect `temp_files`, `temp_bytes`, and `stats_reset`. Why does `temp_bytes` not represent live temp file disk consumption?

### Exercise 26 — `pg_stat_statements`

If the extension is available, list top SQL statements by `temp_blks_written`. Why might a query with high total temp blocks yet low mean runtime still warrant system-wide optimization?

### Exercise 27 — `temp_file_limit`

Explain how `temp_file_limit` protects storage. If a query hits the limit, does PostgreSQL automatically bump `work_mem` or swap indexes mid-flight? What should the application do upon failure?

### Exercise 28 — `temp_tablespaces`

A system has a dedicated NVMe volume for temp files. Assess when moving the temp tablespace helps and why optimizing SQL to avoid spills remains crucial.

### Exercise 29 — Concurrent Workloads

Suppose a pool holds 40 connections and each query runs three memory-heavy operators. Discuss the risk of raising server-wide `work_mem`, adding parallel workers, and bumping `hash_mem_multiplier`. Propose quotas or concurrency controls.

### Exercise 30 — JDBC `SET LOCAL`

Write a JDBC method setting `SET LOCAL work_mem` inside a transaction, running a `GROUP BY`, committing/rolling back, and closing the connection. Why must you avoid unconditional session-level `SET` in a connection pool?

### Exercise 31 — Spring Transactions

A `@Transactional(readOnly=true)` method runs a spilling report. Why does `readOnly` not prevent temporary files? How do you guarantee `SET LOCAL` and the query share the same transaction?

### Exercise 32 — Timings vs. Blocks

Two queries report identical `temp written` blocks yet vastly different runtimes. Describe how to check `track_io_timing`, OS caching, CPU work, and concurrent load.

### Exercise 33 — JSON Parser

Extract `Plan` and traverse all `Plans` from `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. Detect `Sort Method` external merge, high Hash `Batches`, and `Temp Written Blocks`. Why must the parser tolerate missing fields?

### Exercise 34 — Node-Level Double Counting

A `Sort` and its parent `Aggregate` both report `temp read=1000`. Why shouldn't you sum them to 2000? If you want to identify the spilling node, which additional fields should you inspect?

### Exercise 35 — Optimizing `ORDER BY` Expressions

A query orders by `lower(product_name)` with no expression index. Compare keeping the `Sort`, creating an expression index, or adding a canonical generated column—accounting for collation, immutability, and write overhead.

### Exercise 36 — One Query with Both Hash and Sort

Given a query joining `sales`/`products`, grouping by `category`, and ordering by revenue, sketch a possible plan tree with `Hash Join`, `HashAggregate`, and `Sort`. Which operators **could** spill, and why must you inspect the actual plan?

### Exercise 37 — Full Temp Disk

A report fails due to exhausted temp space. Write a runbook covering query identification, temp file/capacity checks, application transaction rollback, data-volume reduction, memory tuning, and alerting.

### Exercise 38 — Sound Benchmarking

Design a benchmark comparing two `work_mem` settings with identical SQL and datasets, cache warm-up, multiple iterations, and varying concurrency. Choose metrics covering latency, memory, and temp I/O.

### Exercise 39 — WAL vs. Temp Files

A large sorting `SELECT` creates 500 MB of temp I/O; a small `UPDATE` generates WAL. Contrast temporary working files, data-page writes, and WAL durability/replication.

### Exercise 40 — End-to-End Scenario

A multi-tenant application runs a reporting query:

```sql
SELECT
    s.tenant_id,
    p.category_id,
    COUNT(*) AS sale_count,
    SUM(s.amount) AS revenue
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID'
GROUP BY s.tenant_id, p.category_id
ORDER BY revenue DESC
LIMIT 100;
```

Outline an optimization plan:

1. Inspect `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` and find which node spills.
2. Compare estimated vs. actual rows, group counts, and join cardinality.
3. Evaluate indexes, filters, and pre-aggregation without changing semantics.
4. Consider `work_mem`/`hash_mem_multiplier` scoped to the report transaction.
5. Evaluate impact with 50 concurrent reports.
6. Propose logging/metrics to detect regressions after deployment.

## Conclusion

**A sort or hash spilling to disk is not a SQL error—it signals that the executor had to use temporary working files or batched processing when an operator's memory budget fell short.** Sort spills typically show up via `Sort Method: external merge` and `Disk`; Hash Join/HashAggregate spills appear through `Batches`, `Disk Usage`, and `Buffers: temp read/written`. To interpret them accurately, read **the full plan tree**, estimated vs. actual row counts, row widths, loops, and cumulative counters.

`work_mem` is **a per-operation budget for eligible nodes**, not a RAM ceiling for one query or all of PostgreSQL. `hash_mem_multiplier` scales hash-based operations. Both settings multiply RAM consumption across multiple nodes, parallel workers, and concurrent requests; never raise them globally just to make one lab query stop spilling.

Sustainable tuning starts by **eliminating or shrinking intermediate work**: add indexes covering `WHERE` + `ORDER BY` + `LIMIT`, filter early, use keyset pagination, trim row width, eliminate unneeded `SELECT *` and `DISTINCT`, fix join cardinality, pre-aggregate when semantically equivalent, refresh statistics, and compare `HashAggregate`/`GroupAggregate` or join algorithms under realistic workloads. When heavy memory is genuinely required, test `SET LOCAL` inside the right transaction scope and measure temp I/O, latency, and RAM under real concurrency.

Finally, combine `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`, `log_temp_files`, `pg_stat_database`, `pg_stat_statements`, and OS telemetry to see **which query spills, which operator drives it, how severely it hurts, and how to prevent regressions**. True optimization does more than drive `temp written` down—it returns exact results, improves latency/throughput, and keeps the server stable under concurrent load.
