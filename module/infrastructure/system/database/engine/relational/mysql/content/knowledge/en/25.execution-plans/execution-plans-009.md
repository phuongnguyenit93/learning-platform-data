# Using temporary, filesort, and the Meaning of Sorting Operations

When reading MySQL `EXPLAIN`, two indicators that commonly worry newcomers are `Using temporary` and `Using filesort`. They describe two distinct operations in an execution plan:

- `Using temporary` indicates MySQL uses an internal temporary table to process part of the query.
- `Using filesort` indicates MySQL needs an extra sorting step because the requested result order is not directly provided by the active access path.

Neither indicator means an error or guarantees the query is spilling temporary data to disk. An internal temporary table can reside in memory or move to on-disk storage depending on size, data types, version, and configuration. `filesort` is simply the name of MySQL's sorting algorithm; it can complete entirely in memory or write temporary run files when data to sort exceeds the sort buffer.

To evaluate properly, determine which node creates the temporary data, how many rows enter the sort, whether an index can supply the ordering, and whether actual metrics reveal I/O or memory pressure. This lesson focuses on reading `Extra`, `TREE` plans, `EXPLAIN ANALYZE`, and related status counters.

## 1. What do these two `Extra` notices indicate?

With tabular `EXPLAIN`, MySQL can display the following indicators in the `Extra` column:

| Extra | Meaning |
|---|---|
| `Using temporary` | The query needs an internal temporary table to process intermediate results. |
| `Using filesort` | MySQL performs a separate sort step instead of reading rows in order from the current access path. |
| `Using index` | The query can retrieve all required columns from the index, commonly called covering index access. |
| `Using where` | Conditions are evaluated to filter rows after or during reading. |
| `Using index condition` | Index Condition Pushdown evaluates part of the condition inside the storage engine before reading full rows. |

`Using temporary` and `Using filesort` answer two different questions. A query might need only a sort, only a temporary table, both, or neither. Do not lump them together into a single blanket concept of "the query is writing to disk."

### Do not judge performance solely by the word `Using`

`Using filesort` on 40 rows can be dirt cheap. A sequential table scan on a small table can also be cheaper than repeated index lookups. Conversely, sorting millions of rows or a huge temporary table spilling to disk can be a major bottleneck.

Combine `Extra` with:

- Estimated and actual row counts.
- Iterator loop counts.
- Actual time of the sort/materialize node.
- Number of pages and volume of data processed.
- Temporary table and sort status counters.
- Execution plans before and after changing indexes or SQL.

## 2. What is an internal temporary table?

An internal temporary table is a structure MySQL creates automatically during query execution to store or organize intermediate data. It differs from a temporary table explicitly created by an application via `CREATE TEMPORARY TABLE`.

Example of an application-created temporary table:

```sql
CREATE TEMPORARY TABLE selected_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);
```

That table has a name and lifecycle managed by the SQL session. By contrast, an internal temporary table is an execution detail created by the optimizer/executor; the application cannot reference it directly by SQL name.

### Operations that can require an internal temporary table

Depending on query structure and index usability, MySQL may need a temporary table for:

- Certain forms of `GROUP BY` or aggregation.
- `DISTINCT` when deduplication requires storing/organizing the result set.
- Certain `UNION` queries needing deduplication or combining results.
- Certain queries with both `ORDER BY` and `GROUP BY` that cannot be resolved directly via an index.
- Certain materialized derived tables, CTEs, or subqueries.
- Certain window functions needing to buffer or organize intermediate partitions/frames.

These are common cases, not a rule that writing `GROUP BY`, `DISTINCT`, `UNION`, a CTE, or a window function guarantees `Using temporary`. The optimizer can use an index, merge query blocks, or choose another strategy to avoid a temporary table.

### Temporary tables can live in RAM or on disk

An internal temporary table can stay in memory when size and data types permit. When exceeding limits or encountering conditions incompatible with the in-memory structure, MySQL can spill to an internal on-disk temporary table.

Since MySQL 8.0.16, `TempTable` is the default storage engine for internal in-memory temporary tables. Internal on-disk temporary tables use InnoDB. Exact thresholds and spillover behavior depend on version and configuration; do not assume a single variable governs everything.

Points to remember:

- `Using temporary` does not guarantee the temporary table is on disk.
- In-memory temporary tables still consume RAM and CPU.
- On-disk temporary tables can generate I/O and add latency.
- Some materializations may appear in a plan without necessarily appearing as the literal string `Using temporary` in every EXPLAIN format.

## 3. What is filesort?

`filesort` is the name of the algorithm MySQL uses when it needs to order rows for `ORDER BY`, or in other ordering operations, when the access path does not supply matching order.

Example:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC;
```

If MySQL reads rows using an index lacking `total_amount` order, it needs a separate sort step. Traditional `EXPLAIN` can show `Using filesort`; `EXPLAIN FORMAT=TREE` typically represents this step with a `Sort` iterator.

### Filesort does not necessarily create disk files

The name `filesort` comes from MySQL history and does not mean every sort writes files. If the data to sort fits within the allocated memory buffer, MySQL can complete the sort in RAM. If the data exceeds what fits in the sort buffer, the algorithm can write sorted runs to temporary files and merge them.

Conceptual flow:

```text
Rows matching WHERE
        |
        v
Build sort keys and row payloads/references
        |
        v
Load entries into sort buffer
        |
        +---- fits ----> sort in memory
        |
        +---- overflows --> write sorted temporary runs
                               |
                               v
                         merge runs
        |
        v
Emit rows in ORDER BY order
```

This is a conceptual diagram; the exact algorithm and fields kept in sort records depend on version, query shape, and MySQL's choices.

### Filesort may sort keys first before fetching rows

Depending on the case, MySQL may store sort keys alongside row IDs/identifiers and retrieve remaining columns after sorting, or pack required payload columns directly into the sort record. This affects memory usage and row lookups. Never assume filesort always copies full rows or always keeps only row IDs.

### LIMIT can reduce sort work without guaranteeing skipping the sort

With `ORDER BY ... LIMIT N`, MySQL can use a top-N/priority queue strategy in eligible cases to retain only the best rows rather than maintaining a complete sort order. Nevertheless, the engine may still have to read and evaluate all candidate rows to identify the top N rows.

If an index supplies the right order, MySQL can read along the index and stop early once N rows are retrieved. That is usually a far bigger win than merely tuning the filesort algorithm.

## 4. Temporary tables and filesort can appear together

These two operations are independent:

```text
Input rows
    |
    v
Temporary table (store/organize intermediate data)
    |
    v
Sort (order according to requested sort)
    |
    v
Final result
```

Example of a query grouping data and sorting by the aggregated result:

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

MySQL must compute aggregates per `status`, then sort the groups by the computed `revenue`. An execution plan may require an intermediate structure to build groups and a sort step to order groups by total revenue. Depending on indexes, data, and the optimizer, `EXPLAIN` may show both `Using temporary` and `Using filesort`.

Not every aggregate query needs both. If groups can be read in matching index order, MySQL can avoid certain temporary operations. However, `ORDER BY` on an aggregate value typically still requires sorting because group totals are only known after each group is computed.

## 5. Preparing practice data

Create an orders table with indexes serving different purposes:

```sql
CREATE TABLE orders_sort_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created_order (
        tenant_id,
        status,
        created_at,
        order_id
    ),
    KEY idx_orders_tenant_total (
        tenant_id,
        total_amount
    ),
    KEY idx_orders_tenant_created_order (
        tenant_id,
        created_at,
        order_id
    )
) ENGINE=InnoDB;
```

Load a small amount of illustrative data:

```sql
INSERT INTO orders_sort_demo (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    total_amount
)
VALUES
    (1001, 10, 1, 'PAID', '2026-01-03 09:00:00', 250.00),
    (1002, 10, 2, 'NEW',  '2026-01-05 10:00:00', 120.00),
    (1003, 10, 1, 'PAID', '2026-01-08 11:00:00', 450.00),
    (1004, 10, 3, 'PAID', '2026-01-10 12:00:00',  90.00),
    (1005, 20, 2, 'PAID', '2026-01-11 13:00:00', 180.00),
    (1006, 10, 2, 'CANCELLED', '2026-01-12 14:00:00', 75.00);
```

To run the JOIN example in section 10, also create a customers table:

```sql
CREATE TABLE customers_sort_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customers_sort_demo (customer_id, customer_name)
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran'),
    (3, 'Chi Le');
```

A small fixture helps demonstrate SQL. The optimizer may pick a table scan over an index because the table is tiny; to evaluate real plans and performance, use a dataset large enough and distributed similarly to production.

## 6. Reading `Using filesort` in EXPLAIN

Try sorting by `total_amount` within tenant 10:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC;
```

Index `idx_orders_tenant_total` can support filtering by tenant and reading along `total_amount`. If the optimizer picks that index and an appropriate scan direction, it can avoid filesort. However, on a tiny fixture the optimizer may choose a table scan followed by a sort because it costs less.

To observe a case where sorting is required, sort by columns not aligned with any existing index order:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY created_at DESC, total_amount DESC;
```

Existing indexes lack the consecutive order `(tenant_id, created_at, total_amount)`; MySQL will likely need a filesort after filtering. Confirm via `Extra`, `FORMAT=TREE`, or `FORMAT=JSON` instead of guessing from DDL alone.

### Filesort in TREE

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY created_at DESC, total_amount DESC;
```

If the plan requires sorting, the tree may look like:

```text
-> Sort: created_at DESC, total_amount DESC
    -> Index lookup/range scan on orders_sort_demo
       using an index for tenant_id
```

The `Sort` node receives rows from the access iterator below and emits them in the requested order. The child's row count shows how many candidate rows the sort must examine; the parent's row count can be smaller if `LIMIT` is present.

## 7. Using an index to avoid filesort

A B+tree index can provide ordering if leading columns are fixed by equality predicates and subsequent columns match the `ORDER BY` order.

Query:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Matching index:

```sql
KEY idx_orders_tenant_status_created_order (
    tenant_id,
    status,
    created_at,
    order_id
)
```

Once `tenant_id` and `status` are fixed, subsequent entries are ordered by `created_at`, then `order_id`. MySQL can scan backward to satisfy DESC ordering on both columns when the access path fits. When an index supplies the order, it can skip a filesort step and stop reading once 20 rows are retrieved.

### Conditions for an index to support ORDER BY

- Leading index columns must be constrained appropriately, typically via equality predicates.
- `ORDER BY` columns must match the trailing index column order.
- ASC/DESC directions must be compatible with index scan direction. MySQL 8.0 supports descending indexes; mixed directions may require an index declared with matching directions.
- Expressions in `ORDER BY` can prevent using a normal index unless a matching functional index/generated column exists.
- The collation of the sort expression must match the index collation.
- Prefix indexes on strings do not store full values and therefore cannot guarantee full-string ordering.
- When `ORDER BY` spans columns from multiple tables, join order and access paths can prevent a single table's index from satisfying overall result order.

Do not add an index merely because you see `Using filesort`. Check how many rows are sorted, query frequency, and the write/storage cost of the new index.

## 8. GROUP BY and Using temporary

Example grouping order counts by status:

```sql
EXPLAIN
SELECT status, COUNT(*) AS order_count
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status;
```

An index with prefix `(tenant_id, status)` lets MySQL read the tenant's rows grouped by status. In some cases, the engine can aggregate in index order and avoid a temporary table; in other cases, the optimizer may use a temporary table or another strategy.

Add ordering by the aggregate:

```sql
EXPLAIN
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

`revenue` is computed from rows within each group, not a pre-ordered index column. MySQL typically needs to materialize group results and then sort those groups by revenue. This is a classic scenario where `Using temporary` and `Using filesort` appear together.

### GROUP BY does not guarantee output order

Never rely on grouping to assume results are automatically sorted. If the application requires order, specify `ORDER BY` explicitly. Especially in MySQL 8.0, do not depend on the implicit GROUP BY sorting behavior from older versions.

## 9. DISTINCT, UNION, and intermediate operations

`DISTINCT` must ensure output rows are unique across the selected expression list. Depending on indexes and plans, MySQL may detect duplicates while scanning an index or require a temporary structure to store/deduplicate rows.

Example:

```sql
EXPLAIN
SELECT DISTINCT status
FROM orders_sort_demo
WHERE tenant_id = 10;
```

With a matching index on `(tenant_id, status)`, MySQL can leverage index order to deduplicate efficiently. Without a suitable index, intermediate result processing may be needed.

`UNION DISTINCT` must also eliminate duplicates across branches:

```sql
EXPLAIN
SELECT customer_id
FROM orders_sort_demo
WHERE tenant_id = 10
UNION
SELECT customer_id
FROM orders_sort_demo
WHERE tenant_id = 20;
```

`UNION` deduplicates by default; `UNION ALL` preserves duplicates and generally avoids deduplication overhead. Only switch to `UNION ALL` when business semantics permit keeping duplicates.

## 10. Sorting in JOINs and multiple data branches

A JOIN query may need sorting after branches are combined:

```sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    c.customer_name,
    o.created_at
FROM orders_sort_demo AS o
JOIN customers_sort_demo AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
ORDER BY c.customer_name, o.created_at DESC;
```

In this example, the requested ordering uses columns from both tables. An index on orders alone cannot generally provide total post-JOIN ordering. The optimizer may perform the join and then sort the result.

If a sort node receives rows after a JOIN, inspect:

1. How many rows are produced after each join iterator?
2. Is fan-out expanding the result set dramatically?
3. Can one branch be filtered earlier without changing semantics?
4. Can join order or indexes shrink the dataset before sorting?
5. Is sorting full rows truly needed, or only a narrow set before LIMIT?

Do not try to force a single-table index to replace sorting when the final order depends on columns from multiple tables.

## 11. LIMIT, OFFSET, and top-N sorting

`LIMIT` caps how many rows are returned, but it does not automatically cap how many rows must be read or sorted.

Example:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
ORDER BY total_amount DESC
LIMIT 20;
```

If no index satisfies `total_amount` order, MySQL may have to evaluate all matching rows to determine the top 20. Some cases can use a top-N/priority queue to reduce memory and sort work, yet all candidate rows still must be inspected.

`LIMIT 20 OFFSET 100000` also forces skipping many rows before returning the requested page. For deep pagination on large tables, keyset pagination is usually far more efficient when a stable sort key exists:

```sql
SELECT order_id, created_at, total_amount
FROM orders_sort_demo
WHERE tenant_id = 10
  AND (created_at, order_id) < ('2026-01-10 12:00:00', 1004)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

This example can exploit index `idx_orders_tenant_created_order (tenant_id, created_at, order_id)` declared in the schema. Tuple comparison supports descending order and requires a matching index; verify semantics around NULLs and tie-breakers. Keyset pagination avoids reading and discarding massive row counts like high OFFSET values do.

## 12. Reading `Using temporary` and `Using filesort` across EXPLAIN formats

### Traditional EXPLAIN

```sql
EXPLAIN
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

Check the `Extra` column for `Using temporary`, `Using filesort`, or both. This column indicates the operation types, but does not fully convey temporary data size or actual runtime.

### EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

The JSON plan can express attributes such as `using_temporary_table` and `using_filesort` inside the query block or relevant node. Nested JSON structure helps tie operations to specific query blocks or tables.

`EXPLAIN FORMAT=TREE` has been supported since MySQL 8.0.16; `EXPLAIN ANALYZE` since MySQL 8.0.18. On older servers, use the EXPLAIN formats supported by that version.

### EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE

```sql
EXPLAIN FORMAT=TREE
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;

EXPLAIN ANALYZE
SELECT
    status,
    SUM(total_amount) AS revenue
FROM orders_sort_demo
WHERE tenant_id = 10
GROUP BY status
ORDER BY revenue DESC;
```

In TREE, look for `Sort`, `Aggregate`, `Group aggregate`, `Temporary table`, or corresponding materialization nodes. `EXPLAIN ANALYZE` reports actual row counts and iterator times, clarifying how many rows the sort processes and how much time it consumes.

`EXPLAIN ANALYZE` executes the SELECT. Do not run it indiscriminately on huge queries or under heavy load; choose an appropriate environment and timing.

## 13. Tracking temporary tables with status variables

Status counters let you observe how many internal temporary tables were created in a session or across the server.

Check the session:

```sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
```

Check global variables:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

Two key counters of interest:

- `Created_tmp_tables`: number of internal temporary tables created.
- `Created_tmp_disk_tables`: number of internal on-disk temporary tables created.

Counters are cumulative within session/server scope since startup or an appropriate reset; they are not automatically tied to a single SQL statement. To evaluate one query, record values before and after running it in an isolated test session and calculate the delta.

Do not interpret `Created_tmp_disk_tables` as how many times filesort wrote files. Filesort can create temporary merge files without constituting an internal temporary table counted by this metric.

On versions using `TempTable`, internal temporary tables can use memory-mapped files before spilling to InnoDB. `Created_tmp_disk_tables` does not count internal temporary tables stored in memory-mapped files; hence this counter can underreport total cases where TempTable used storage outside RAM. Read the counter alongside configuration variables and server version.

### Related configuration variables

Variables that clarify temporary table limits, depending on version:

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
```

`tmp_table_size` caps the size of certain internal in-memory temporary tables before spilling to disk; with TempTable there are also global caps like `temptable_max_ram` and memory-mapped bounds like `temptable_max_mmap` on supported versions. Not every variable exists or shares identical semantics across all MySQL releases. Inspect actual values on the running version before tuning. Raising memory limits too high can cause concurrent sessions to consume excessive RAM.

## 14. Tracking filesort with status variables

Sort-related counters:

```sql
SHOW SESSION STATUS LIKE 'Sort%';
SHOW GLOBAL STATUS LIKE 'Sort%';
```

Commonly encountered variables:

| Counter | General meaning |
|---|---|
| `Sort_scan` | Number of sorts performed after a table/index scan. |
| `Sort_range` | Number of sorts performed after a range access. |
| `Sort_rows` | Number of rows sorted. |
| `Sort_merge_passes` | Number of merge passes when sorting had to merge sorted runs. |

Increasing `Sort_merge_passes` can signal that sorting had to create and merge multiple runs because data exceeded the sort buffer. Still, evaluate it alongside workload, rows sorted, and execution time; occasional merge passes do not automatically prove a system problem.

`sort_buffer_size` is the sort memory buffer allocated per connection/operation requiring sorting. Increasing it can reduce merge passes for large sorts, yet memory is allocated across concurrent sessions. Never raise the global value mechanically; first reduce rows entering the sort or design an index that provides ordering.

## 15. Common causes of Using temporary and filesort

### ORDER BY does not match the index

For example, index `(tenant_id, status, created_at)` exists, yet the query filters `tenant_id` and sorts by `total_amount`. The index does not provide the required order, so MySQL must sort.

### GROUP BY and ORDER BY use different criteria

MySQL may read and aggregate by the grouping key, then sort groups by an aggregate or another expression. Both temporary table and filesort can appear together.

### DISTINCT or UNION requires deduplication

When index order cannot be leveraged to detect duplicates, MySQL may need an intermediate structure to eliminate duplicates.

### ORDER BY uses an expression

Example:

```sql
ORDER BY DATE(created_at)
```

A standard index on `created_at` does not necessarily satisfy the ordering of `DATE(created_at)`. Consider range predicates on the raw column or a functional index/generated column if the workload genuinely warrants it.

### ORDER BY spans multiple tables

If ordering depends on columns from multiple tables after a JOIN, a single index on one table is generally insufficient to supply full result order.

### Excessive intermediate row counts

Join fan-out or late filtering can send hundreds of thousands of rows into a sort/temporary table even if only a tiny result is returned at the end.

## 16. Workflow for resolving queries with Using temporary/filesort

1. Run `EXPLAIN` and confirm which query block/table shows `Using temporary` or `Using filesort`.
2. Run `EXPLAIN FORMAT=TREE` to locate Sort, Aggregate, Materialize, or Temporary table nodes.
3. Run controlled `EXPLAIN ANALYZE` to measure actual rows entering those nodes and processing time.
4. Check whether `ORDER BY`/`GROUP BY` matches the leftmost prefix order of existing indexes.
5. Inspect equality columns, range columns, sort columns, expressions, and collations.
6. Look for ways to cut candidate rows before sorting using sargable predicates and better join order.
7. Consider a composite index supporting both filtering and order, weighing size and write amplification.
8. For GROUP BY/aggregates, check whether index order can group rows; if sorting by an aggregate, accept that sorting group results may be unavoidable.
9. Record `Created_tmp%` and `Sort%` before/after in an isolated test session.
10. Tune `sort_buffer_size` or TempTable limits only after understanding the cause and estimating concurrent load.
11. Re-measure results and timing; verify business results remain unchanged.

Prioritize shrinking rows entering the sort and letting indexes supply order where appropriate. Enlarging buffers can help a specific case, yet it cannot fix a plan reading way too much data.

## 17. Common mistakes

| Mistake | Consequence | Correct understanding/action |
|---|---|---|
| Thinking `Using filesort` always writes files to disk | Misjudging I/O overhead | Filesort can finish in RAM; inspect merge passes and workload. |
| Thinking `Using temporary` always means an on-disk table | Unnecessary alarm or wrong config tuning | Internal temporary tables can be in RAM or on disk. |
| Thinking temporary table and filesort are the same | Failing to pinpoint the costly step | Temporary stores/organizes intermediate data; filesort orders rows. |
| Seeing `Using filesort` and adding an index immediately | Unnecessary indexes slow DML and waste space | Check rows sorted, query frequency, and needed index order. |
| Setting a huge global `sort_buffer_size` | Concurrent connections can exhaust RAM | Measure first, change cautiously, and prioritize shrinking sort input. |
| Raising `tmp_table_size` assuming all temp tables fit | Overlooking TempTable and version-specific limits | Check actual engine/variables on your MySQL version. |
| Thinking LIMIT 20 means only 20 rows are read | Sort may inspect all candidate rows | Use an ordering index or check top-N strategy and actual rows. |
| Thinking GROUP BY guarantees output order | App relies on unguaranteed ordering | Use explicit ORDER BY. |
| Switching UNION to UNION ALL without checking duplicates | Alters business results | Only drop deduplication when semantics allow duplicates. |
| Treating global server counters as one query's stats | Cannot isolate which query created temp tables/sorts | Use an isolated session and measure before/after deltas. |

## 18. Practice exercises

### Exercise A — Reading filesort

1. Create `orders_sort_demo` and load the fixture.
2. Run a query filtering tenant with `ORDER BY created_at, total_amount`.
3. Run `EXPLAIN` and `FORMAT=TREE`, and observe the Sort node/`Using filesort`.
4. Record candidate row count and result row count.
5. Explain why existing indexes do not satisfy the full sort order.

### Exercise B — Avoiding filesort with a composite index

1. Run a query with equality on `tenant_id` and `status`, plus ORDER BY `created_at`, `order_id`.
2. Observe index `idx_orders_tenant_status_created_order`.
3. Check whether the plan still contains Sort.
4. Change one ORDER BY column or ASC/DESC direction.
5. Evaluate whether the index still provides the requested order.

### Exercise C — Temporary tables and aggregates

1. Run GROUP BY `status` for one tenant.
2. Re-run adding ORDER BY `SUM(total_amount) DESC`.
3. Compare `Using temporary`, `Using filesort`, and TREE iterators.
4. Explain why ordering by an aggregate can only be determined after computing groups.

### Exercise D — DISTINCT and UNION

1. Run DISTINCT status per tenant.
2. Test creating index `(tenant_id, status)` and re-run EXPLAIN.
3. Run UNION and UNION ALL on two overlapping datasets.
4. Compare row counts and deduplication work.
5. Explain why UNION cannot be replaced by UNION ALL if duplicate removal is required.

### Exercise E — Tracking counters

1. Open an isolated session and record `Created_tmp%` and `Sort%`.
2. Run a sufficiently large aggregate/sort query.
3. Read counters again and compute deltas.
4. Run a query with an ordering index.
5. Compare Sort_rows, Sort_merge_passes, and temporary table counts.

### Exercise F — LIMIT and pagination

1. Run an unindexed ORDER BY with LIMIT 20.
2. Re-run with LIMIT 20 OFFSET 100000 on a large dataset.
3. Create an index satisfying filtering/order and test keyset pagination.
4. Use EXPLAIN ANALYZE to compare actual rows and execution time.
5. Explain when LIMIT enables early stopping and when sorting still must read many rows.

You have completed this lesson when you can distinguish internal temporary tables from filesort, explain why filesort does not necessarily write files, locate nodes creating temporary data/sorts, and use indexes or input reduction to lower cost.

## 19. Principles to remember

- `Using temporary` indicates an internal temporary table; it does not mean the temporary table is on disk.
- `Using filesort` indicates an extra sorting step; filesort can run in RAM or use temporary files for merging.
- Temporary tables and filesort are separate operations that can appear individually or together.
- `EXPLAIN FORMAT=TREE` typically represents sorting with a `Sort` iterator; JSON plans may include `using_temporary_table` and `using_filesort`.
- An index can avoid filesort when the equality prefix and column order match `ORDER BY`.
- `GROUP BY` can leverage an index to group rows, yet `ORDER BY` on an aggregate typically requires sorting the grouped results.
- `DISTINCT`/`UNION` may need intermediate structures to deduplicate; use `UNION ALL` only when duplicates are acceptable.
- `LIMIT` does not guarantee reading only N rows; a sort may have to inspect all candidate rows.
- `Created_tmp_tables`/`Created_tmp_disk_tables` track internal temporary tables; `Sort_merge_passes` tracks sort merge passes.
- Status counters are cumulative; use an isolated session and before/after deltas to attribute them to a query.
- Never raise `sort_buffer_size` or TempTable limits mechanically; account for RAM across concurrent connections.
- Prioritize shrinking rows entering the sort, leveraging properly ordered indexes, and verifying with EXPLAIN ANALYZE.

When you properly understand `Using temporary` and `Using filesort`, you can distinguish intermediate data storage from sorting, recognize when sorting genuinely creates resource pressure, and choose the right optimization. Base decisions on execution nodes, actual row counts, loops, and status counters rather than reacting to a single `Extra` line.
