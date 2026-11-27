# Diagnosing Slow Queries with EXPLAIN ANALYZE and Indexes

## 1. Objectives and Approach

When a PostgreSQL query runs slowly, you need to determine where time is being spent: scanning too many rows, filtering after reading, joining tables with high loop counts, sorting data, reading or writing temporary files, or relying on inaccurate planner statistics. `EXPLAIN ANALYZE` reveals the execution plan PostgreSQL chose along with the actual runtime metrics observed while executing that plan. Indexes can reduce the volume of data read or deliver rows in the desired order, yet adding a new index does not automatically speed up every query.

The workflow can be summarized as follows:

1. Identify the exact SQL statement, parameters, execution frequency, and observed latency.
2. Collect the execution plan via `EXPLAIN (ANALYZE, BUFFERS)` on representative data.
3. Read the plan bottom-up from child nodes to parent nodes, comparing estimated rows against actual rows.
4. Locate the node performing the most work and pinpoint the root cause.
5. Choose the appropriate fix: refresh statistics, rewrite the SQL, or create an index.
6. Re-run the exact same query and compare before-and-after metrics.

Use identical parameter sets and data volumes close to production scale. Plans can change whenever data volume, value distribution, statistics, configuration, or cache state shifts.

## 2. Collecting Execution Plans

### 2.1. Distinguishing `EXPLAIN` from `EXPLAIN ANALYZE`

`EXPLAIN` asks PostgreSQL to plan the query without executing it. This is useful for inspecting what the planner intends to do:

```sql
EXPLAIN
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42;
```

`EXPLAIN ANALYZE` executes the statement and embeds actual runtime measurements into the plan. When you also want to inspect block access counts, run:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42;
```

Common options:

| Option | Meaning |
|---|---|
| `ANALYZE` | Executes the statement and records actual metrics such as time, row counts, and loops |
| `BUFFERS` | Displays blocks found in shared buffers, read into shared buffers, and temporary disk blocks |
| `VERBOSE` | Displays extra detail including full column lists and expressions |
| `SETTINGS` | Displays non-default planner settings relevant to the generated plan |
| `TIMING OFF` | Reduces per-node timing overhead while still reporting overall Execution Time |

**Important note:** `EXPLAIN ANALYZE` genuinely executes the statement. For `UPDATE`, `DELETE`, or `INSERT`, data will be modified. You can test inside a transaction followed by `ROLLBACK`:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE orders
SET status = 'archived'
WHERE created_at < DATE '2024-01-01';

ROLLBACK;
```

A rollback does not undo external side effects outside the transaction, such as triggers calling external services or sending notifications. For write statements with side effects, test in a staging environment or start with `EXPLAIN` without `ANALYZE`.

### 2.2. Selecting Queries to Investigate

If the `pg_stat_statements` extension is enabled, you can use it to find SQL statements consuming the highest total time or exhibiting high average latency:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

`total_exec_time` and `mean_exec_time` are measured in milliseconds. Queries with high mean execution time may warrant individual investigation; queries executed very frequently with moderate per-call latency can also dominate overall system load. Always capture the exact SQL text and representative parameter values before analyzing.

## 3. Reading `EXPLAIN ANALYZE` Output

The output forms a tree of plan nodes. Leaf nodes typically read data from tables or indexes; results flow upward to parent nodes that filter, join, sort, or limit rows. Reading from leaf nodes upward helps trace how data moves through each stage.

Example plan:

```text
Limit  (cost=1250.00..1250.13 rows=50 width=24)
       (actual time=18.420..18.431 rows=50 loops=1)
  ->  Sort  (cost=1250.00..1260.00 rows=4000 width=24)
            (actual time=18.418..18.424 rows=50 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB
        ->  Seq Scan on orders
              (cost=0.00..1100.00 rows=4000 width=24)
              (actual time=0.030..17.200 rows=320 loops=1)
              Filter: (customer_id = 42)
              Rows Removed by Filter: 199680
              Buffers: shared hit=850
Planning Time: 0.240 ms
Execution Time: 18.470 ms
```

The numbers above only illustrate how to read a plan. Real plans depend on your data and environment.

### 3.1. `cost`, `rows`, and `width`

A plan node line typically looks like:

```text
(cost=startup_cost..total_cost rows=estimated_rows width=estimated_width)
```

- `startup_cost` is the estimated cost before the node can emit its first row.
- `total_cost` is the estimated cost to complete the node.
- `rows` is the number of rows PostgreSQL predicts the node will output.
- `width` is the estimated average row width in bytes.

Cost is an internal unit used to compare candidate plans, **not milliseconds**. You cannot read `cost=1000` and conclude the query takes 1,000 ms. The planner chooses plans using its cost model and available statistics.

### 3.2. `actual time`, `actual rows`, and `loops`

When `ANALYZE` is enabled, nodes include actual measurements:

```text
(actual time=first_row_ms..last_row_ms rows=actual_rows loops=loop_count)
```

- `actual time` shows the actual elapsed time to the first row and to node completion, in milliseconds.
- `rows` is the average actual rows emitted per execution of that node.
- `loops` is the number of times the node executed.

When `loops > 1`, multiply `rows × loops` to gauge the total rows emitted across all iterations. For example, `rows=5 loops=10000` means the node emitted an average of 5 rows per pass and ran 10,000 times. This can be an important signal inside a Nested Loop.

A parent node's timing generally includes the work performed by its child nodes. Do not sum timings across every line in the tree to compute total runtime; inspect `Execution Time` at the bottom and use per-node timings to locate hotspots.

### 3.3. `Buffers` and Read/Write Indicators

When `BUFFERS` is enabled, PostgreSQL reports block access counts:

| Indicator | Interpretation |
|---|---|
| `shared hit` | Blocks already resident in shared buffers |
| `shared read` | Blocks that had to be read into shared buffers; data may still come from OS page cache |
| `shared dirtied` | Blocks in shared buffers modified by this query |
| `shared written` | Blocks evicted/written from shared buffers |
| `temp read/written` | Temporary file blocks read/written, usually from sorts or hashes exceeding `work_mem` |

High `shared read` counts indicate the query had to load many blocks into shared buffers, though that alone does not prove every read hit physical storage. If `temp read` or `temp written` counts are high, inspect whether Sort or Hash nodes are spilling to disk.

Buffer metrics on parent nodes include the activity of their child nodes. Do not sum buffer lines across nodes as if they were independent.

## 4. Identifying Root Causes in the Plan

### 4.1. Large Row Estimation Mismatches

Compare estimated `rows` against `actual rows`. If the planner expects a handful of rows while hundreds of thousands are actually returned, the chosen join strategy, join order, or downstream access path may be suboptimal.

Common causes:

- Stale statistics after heavy data mutations or bulk loads.
- Skewed column value distributions inadequately captured by default statistics.
- Correlated columns that the planner estimates as independent predicates.
- Complex expressions or casts that obscure selectivity from the planner.

Try refreshing statistics:

```sql
ANALYZE orders;
```

When multiple columns are correlated, extended statistics can improve estimates:

```sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, mcv)
    ON customer_id, status
    FROM orders;

ANALYZE orders;
```

Create extended statistics only when plans and data distributions show a clear need. Better statistics alone can persuade the planner to pick a much better plan without adding an index.

### 4.2. `Seq Scan` Is Not Automatically Bad

`Seq Scan` reads table pages sequentially. It is often optimal when:

- The table is small.
- The query needs a large fraction of the table's rows.
- Filter selectivity is low, returning a high percentage of data.
- Sequential I/O is cheaper than traversing an index and jumping across scattered heap locations.

In the earlier example, `Seq Scan` read roughly 200,000 rows while retaining only 320. If that query runs frequently on a large table, an index matching the predicate is likely warranted. Conversely, if a table holds only a few hundred rows or the filter selects most of the table, `Seq Scan` may remain the fastest choice.

### 4.3. `Filter` vs. `Index Cond`

- `Filter` is a condition evaluated after rows have already been fetched by the node.
- `Index Cond` is a condition used directly to locate matching entries inside an index.
- `Rows Removed by Filter` reports how many rows were discarded by the filter at that node.

If large numbers of rows are discarded by `Filter`, examine whether the predicate can be pushed into an index. That lets the index skip irrelevant rows up front. Not every predicate can become an `Index Cond`; it depends on index type, operators, and how expressions are written.

### 4.4. Joins and Loop Counts

Three common join strategies:

| Node | Characteristics | When Typically Appropriate |
|---|---|---|
| Nested Loop | For each outer row, probes matching rows on the inner side | Outer set is small and inner side has an efficient lookup path, usually an index |
| Hash Join | Builds a hash table from one input and probes with the other | Joining large datasets on equality conditions |
| Merge Join | Joins two inputs already sorted on the join key | Both inputs are pre-sorted or sorting cost is worthwhile |

A Nested Loop is not inherently bad. However, if the outer side yields tens of thousands of rows and the inner node shows `loops=10000`, check whether each iteration scans too much data. An index on the inner join key can slash per-loop work. For Hash Joins, inspect batch counts and temporary buffers; multiple batches or temp I/O indicate the hash table spilled beyond allocated memory.

### 4.5. Sorts and Temporary Disk Files

A `Sort` node can sort in memory or spill to temporary files. Output typically includes `Sort Method` and `Memory` or disk usage. Expensive sorts occur when:

- A query sorts a huge row set only to return a small `LIMIT`.
- No index supplies the required sort order.
- Intermediate result sets are overly large.
- Sort memory is insufficient, forcing PostgreSQL onto temporary disk files.

If a query filters on one key and sorts on another, a multi-column index can satisfy both filtering and ordering. Never raise `work_mem` globally based on a single plan; a single query may allocate multiple sort/hash nodes across many concurrent sessions, multiplying total memory usage.

## 5. Example: Optimizing an Order Query by Customer and Time

Suppose the `orders` table has millions of rows with columns `id`, `customer_id`, `created_at`, `status`, and `total`. The application frequently retrieves a customer's 50 latest orders within a time window:

```sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
ORDER BY created_at DESC
LIMIT 50;
```

Suppose the initial plan reveals:

- PostgreSQL performs a full `Seq Scan` of the table.
- Hundreds of thousands of rows are discarded by `Filter`.
- `Sort` processes all matching rows before emitting 50 rows.
- Actual rows scanned or read latency exceeds application targets.

A multi-column B-tree index can fit well:

```sql
CREATE INDEX idx_orders_customer_created_at
    ON orders (customer_id, created_at DESC)
    INCLUDE (id, total);
```

Why this structure works:

- `customer_id` comes first because the query filters on a specific customer equality predicate.
- `created_at` comes next to bound the time range and provide descending sort order.
- `id` and `total` sit in `INCLUDE` so the index covers all columns the query selects, enabling an `Index Only Scan`.

Re-run the exact same SQL with identical parameters:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
ORDER BY created_at DESC
LIMIT 50;
```

When the index aligns with the data and statistics, the plan can switch to an `Index Scan` or `Index Only Scan`. Even with an `Index Only Scan`, PostgreSQL must still check the heap if the visibility map has not marked pages all-visible; inspect the `Heap Fetches` metric. Having a covering index does not guarantee `Heap Fetches: 0`.

Evaluate the result by comparing:

- `Execution Time` before and after.
- `shared hit/read` and temp block counts.
- Actual rows read vs. returned.
- Whether the `Sort` node disappeared.
- `Heap Fetches` count if an `Index Only Scan` occurred.
- Impact of the new index on write throughput and storage footprint.

An illustrative post-optimization plan might look like:

```text
Limit  (cost=0.56..8.20 rows=50 width=24)
       (actual time=0.040..0.090 rows=50 loops=1)
  ->  Index Only Scan using idx_orders_customer_created_at on orders
        (cost=0.56..80.00 rows=500 width=24)
        (actual time=0.038..0.084 rows=50 loops=1)
        Index Cond: ((customer_id = 42)
                     AND (created_at >= '2026-10-01 00:00:00+07'))
        Heap Fetches: 0
        Buffers: shared hit=5
Planning Time: 0.300 ms
Execution Time: 0.110 ms
```

The numbers above are illustrative only, not a guarantee that every query achieves this plan or speed. If a query returns a large portion of the table, the planner may still prefer a `Seq Scan` because its cost is lower.

## 6. Choosing the Right Index Type

### 6.1. B-Tree: Default Choice for Most Queries

B-tree indexes suit equality comparisons, range scans, sorting, and many common search predicates:

```sql
CREATE INDEX idx_users_email ON users (email);

SELECT *
FROM users
WHERE email = 'reader@example.com';
```

B-trees also support `<`, `<=`, `>`, `>=`, and `ORDER BY`. They are typically the first choice when queries filter by exact values or ranges.

### 6.2. Multi-Column Indexes

Column order in a multi-column B-tree directly determines how effectively it can be used. Given:

```sql
CREATE INDEX idx_orders_customer_date
    ON orders (customer_id, created_at);
```

this index is particularly effective for filtering by `customer_id`, or by `customer_id` combined with a `created_at` range. It usually does not replace a standalone index on `created_at` for queries that omit `customer_id`.

Design column ordering from real query patterns: equality predicates, range predicates, sort ordering, and row limits. Never blindly follow a rule like "always put the highest-cardinality column first"; optimal ordering depends on how queries constrain those columns.

### 6.3. Partial Indexes

A partial index stores only rows matching a predicate. For instance, if the application frequently queries open orders:

```sql
CREATE INDEX idx_orders_open_customer_date
    ON orders (customer_id, created_at DESC)
    WHERE status = 'open';
```

Queries must include predicates from which the planner can prove the index predicate holds:

```sql
SELECT id, created_at
FROM orders
WHERE status = 'open'
  AND customer_id = 42
ORDER BY created_at DESC;
```

A partial index is smaller than a full-table index covering all statuses and avoids update overhead for rows outside its predicate. However, if a query omits the predicate or the planner cannot prove equivalence, the index will not be used.

### 6.4. Expression Indexes

If queries filter on an expression, you can index that exact expression:

```sql
CREATE INDEX idx_users_lower_email
    ON users (lower(email));

SELECT id, email
FROM users
WHERE lower(email) = lower('Reader@example.com');
```

A standard B-tree index on `email` does not effectively serve `lower(email)`. Expression indexes are valuable when the expression appears frequently and has stable semantics.

### 6.5. `INCLUDE` and `Index Only Scan`

`INCLUDE` appends non-key columns to the index payload without making them search or sort keys. This can allow queries to be satisfied directly from the index:

```sql
CREATE INDEX idx_products_category
    ON products (category_id)
    INCLUDE (name, price);
```

`Index Only Scan` still relies on the table's visibility map. If PostgreSQL needs to verify tuple visibility in the heap, it must still visit heap pages. Adding too many columns to `INCLUDE` bloats the index, consumes buffer cache, and raises write costs.

### 6.6. GIN, GiST, and BRIN

Not every data type or operator fits a B-tree:

| Type | Common Use Cases |
|---|---|
| GIN | Array element containment, JSONB containment operators, full-text search |
| GiST | Data types and operators needing generalized search trees, e.g. spatial data or ranges |
| BRIN | Very large tables whose values correlate with physical storage order, e.g. append-only time-series logs |

Example GIN index for JSONB containment:

```sql
CREATE INDEX idx_events_payload
    ON events USING GIN (payload);

SELECT id
FROM events
WHERE payload @> '{"type": "payment"}'::jsonb;
```

BRIN indexes are tiny and effective on physically correlated data, though each matching block range may require scanning many rows. Choose index types based on query operators and access patterns, not merely column data types.

## 7. Checking SQL and Statistics Before Adding Indexes

An existing index may go unused if the query expression does not match the index definition or if the predicate is not selective enough.

### 7.1. Use Range Predicates Instead of Wrapping Columns in Functions

Writing the filter below can prevent a standard B-tree index on `created_at` from being used directly:

```sql
SELECT *
FROM orders
WHERE DATE(created_at) = DATE '2026-11-14';
```

If the column has a standard B-tree index, rewrite it as a half-open range:

```sql
SELECT *
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
```

Half-open intervals avoid boundary overlap between consecutive days and allow direct index lookups on the underlying column. If business queries genuinely require an expression, consider adding a matching expression index.

### 7.2. Watch Data Types and Implicit Casts

Keep parameter types compatible with column types. Avoid casting the indexed column inside the predicate if doing so alters the indexed expression. Use application parameter binding and inspect the actual SQL and bound types sent to PostgreSQL.

### 7.3. `LIKE` Predicates with Leading Wildcards

Standard B-tree indexes generally cannot accelerate patterns starting with a wildcard, such as `LIKE '%phone%'`. If this search pattern is common, consider the `pg_trgm` extension with GIN or GiST:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
    ON products USING GIN (name gin_trgm_ops);
```

Check operators, collations, and actual plans to confirm the index is utilized.

### 7.4. Refresh Statistics After Data Changes

After bulk data loads or significant distribution changes, run `ANALYZE` on affected tables. Autovacuum normally updates statistics based on configured thresholds, though it may not trigger immediately after a large load. `VACUUM` reclaims dead tuples and updates the visibility map; `ANALYZE` collects planner statistics. Both operations serve distinct purposes.

## 8. Costs to Weigh Before Adding an Index

Indexes accelerate specific reads, yet they introduce ongoing system overhead:

- Every `INSERT`, `UPDATE`, or `DELETE` may have to update multiple indexes.
- Indexes consume disk space and can occupy a substantial share of buffer cache.
- Rarely used indexes add write amplification and maintenance overhead without payoff.
- Overlapping or redundant indexes increase complexity without guaranteed benefit.
- Over time, bloat and dead tuples can degrade index efficiency; monitor vacuuming and index health.

On tables serving continuous writes, `CREATE INDEX CONCURRENTLY` avoids blocking writes the way a standard `CREATE INDEX` does. It requires extra passes, takes longer, and cannot run inside a transaction block. Always verify the build succeeded and the index is valid before relying on it.

Never index every column simply because it appears in a `WHERE` clause. Base decisions on high-frequency queries, selectivity, read/write trade-offs, and before/after measurements. Likewise, never force the planner away from `Seq Scan` as a knee-jerk reaction; `Seq Scan` can be the optimal plan.

## 9. A Repeatable Diagnostic Workflow

For each slow query, record a concise evidence bundle:

1. Exact SQL text and representative parameters.
2. Current latency, call frequency, and PostgreSQL version.
3. Full `EXPLAIN (ANALYZE, BUFFERS)` output.
4. Nodes exhibiting large estimate vs. actual mismatches, high loop counts, heavy block reads, or temp spills.
5. Root-cause hypothesis: stale stats, non-sargable filter, join strategy, sort spill, or missing index.
6. One targeted change, such as `ANALYZE`, rewriting a predicate, or adding one index.
7. Post-change plan and metrics measured on the exact same query and parameters.
8. Side effects on write latency, index size, and other workload queries.

Run multiple iterations under equivalent conditions if measurements fluctuate. Separate cold-cache runs from warm-cache runs; never compare runs under completely different conditions and attribute the entire delta to a new index.

## 10. Practice Exercise

Suppose the `orders` table holds several million rows. The application frequently executes:

```sql
SELECT id, status, total
FROM orders
WHERE customer_id = 105
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Perform the following steps in your lab environment:

1. Run `EXPLAIN (ANALYZE, BUFFERS)` and identify the node reading from `orders`.
2. Compare estimated `rows` against `actual rows`; note `loops` and `Rows Removed by Filter`.
3. Check whether a `Sort` node exists, how many buffer blocks were read, and whether temporary disk blocks appeared.
4. Propose an index based on the filter predicates and sort order. Evaluate a multi-column index or a partial index for `status = 'paid'`.
5. Re-run the query and compare execution plans, timings, and buffer metrics.
6. Explain the write overhead and storage cost introduced by the new index.

No single index is universally right for every system. Always rely on real data, real queries, and observed execution plans to validate your choice.

## 11. Self-Check Questions

**Why can a `Seq Scan` be faster than an `Index Scan`?** When a query needs a large portion of the table's rows, scanning sequentially can be cheaper than traversing an index and fetching scattered heap pages.

**Does `cost=500` mean the query takes 500 ms?** No. Cost is an internal planner estimate unit, not real elapsed time.

**What does `actual rows=2 loops=5000` indicate?** The node emitted an average of 2 rows per invocation and was called 5,000 times; inspect parent nodes—especially Nested Loops—to understand total work.

**Does a covering index guarantee an `Index Only Scan`?** No. The planner must judge the plan cost-effective, and the visibility map must allow skipping heap visibility checks as needed.

**What should you do right after creating an index?** Re-run the exact same query with representative parameters, compare runtime, row counts, buffers, sorting, and heap fetches, and assess write overhead and storage footprint.
