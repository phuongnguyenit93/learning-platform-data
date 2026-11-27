# Internal Temporary Tables, RAM Limits, and Disk Spills

During SQL query execution, MySQL may need to store intermediate results before returning data to the client. For example, the server may have to group rows, deduplicate records, sort a result set, or materialize a derived table. In these cases, the optimizer can create an **internal temporary table**. This table is an internal working structure for a statement, not a table explicitly created by the application via `CREATE TEMPORARY TABLE`.

An internal temporary table may be kept in RAM or moved to temporary storage on disk. Spilling to disk is a safety mechanism to protect memory and allow intermediate sets larger than the RAM budget; however, it increases I/O and can lengthen query duration. To optimize properly, you need to identify which statement creates the temporary table, which engine stores it, which RAM limits apply, where the disk spill path goes, and what the actual cost is.

This lesson is scoped to `DATABASE_MYSQL`: mastering MySQL query performance and operations, reading execution plans, managing resources, and handling high-load database scenarios.

## 1. Objectives and Scope

After this lesson, you will be able to:

- Distinguish internal temporary tables from application-created temporary tables.
- Recognize SQL operations that commonly require materialization or temporary tables.
- Explain the roles of `TempTable`, `MEMORY`, `InnoDB`, and related limits.
- Distinguish global RAM limits from per-temporary-table size limits.
- Describe the transition path from RAM to memory-mapped files and then to InnoDB on-disk internal temporary tables.
- Monitor temporary tables via `EXPLAIN`, Performance Schema, `sys` schema, and status counters.
- Locate temporary file paths and check filesystem space and I/O.
- Estimate concurrency impact when many queries create temporary tables simultaneously.
- Choose SQL, index, or configuration changes based on measured metrics.

This lesson focuses on internal temporary tables created by the optimizer and executor during statement execution. Explicit temporary tables such as `CREATE TEMPORARY TABLE` are mentioned to clarify boundaries and avoid misapplying configuration settings.

## 2. When Are Internal Temporary Tables Created?

The optimizer can create an intermediate structure when results must be grouped, sorted, deduplicated, or retained for reuse across multiple execution steps. Common cases include:

- `GROUP BY` requiring grouping when index access order cannot satisfy it.
- `DISTINCT` having to eliminate duplicate rows.
- `ORDER BY` needing to sort a result set when an index cannot provide the matching order.
- `UNION` combining and deduplicating results.
- Derived tables or common table expressions (CTEs) materialized instead of merged into the outer query.
- Subqueries materialized so the optimizer can perform joins or membership checks.
- Window functions needing to hold or sort data per window partition/order.
- Combinations of `GROUP BY`, `DISTINCT`, `ORDER BY`, or complex expressions creating multiple intermediate processing stages.

Not every `SELECT` containing these keywords will definitely create an internal temporary table. The optimizer may use an index, merge a derived table, stream results, or choose another strategy. Conversely, a query without the `TEMPORARY` keyword can still require an internal temporary table.

### 2.1. `GROUP BY` and `ORDER BY` Example

Suppose the `orders` table contains many orders by `customer_id`:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

MySQL must compute sums per `customer_id` and then sort the groups by the `revenue` expression. An index can help filter on `created_at` or support ordering by `customer_id`, but it cannot directly supply ordering by `SUM(total_amount)` before aggregation. The executor may need an intermediate structure for grouping and a sort step.

If the application only needs total revenue per `customer_id` without sorting by the total, removing `ORDER BY` can eliminate a sort step. If top 20 by revenue is required, groups still must be ranked; measure the cost and check whether input rows can be reduced before aggregation.

### 2.2. `DISTINCT` Example

~~~sql
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
~~~

With an index matching the predicate and `customer_id`, the optimizer can read values in order and deduplicate efficiently. Without a suitable access path, the server may need an intermediate structure to eliminate duplicates.

### 2.3. `UNION` Example

~~~sql
SELECT customer_id FROM online_orders
UNION
SELECT customer_id FROM store_orders;
~~~

`UNION` deduplicates rows by default, requiring a result-set processing step. `UNION ALL` preserves duplicates and can allow simpler or streaming execution in many cases:

~~~sql
SELECT customer_id FROM online_orders
UNION ALL
SELECT customer_id FROM store_orders;
~~~

Switch `UNION` to `UNION ALL` only when business logic permits duplicates. Never alter query semantics just to avoid a temporary table.

### 2.4. Derived Tables and CTEs

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 1000000;
~~~

The optimizer can merge a derived table/CTE into the outer query or materialize it. With materialization, intermediate results are stored for subsequent steps to read. Materialization is not inherently a bug: it can avoid repeated computation or produce a small reusable dataset. Inspect the execution plan to see which choice occurred.

## 3. Distinguishing Internal Temporary Tables from `CREATE TEMPORARY TABLE`

These two concepts differ in purpose, lifecycle, and management mechanism.

| Criterion | Internal temporary table | `CREATE TEMPORARY TABLE` |
|---|---|---|
| Created by | MySQL optimizer/executor | Application or user |
| Purpose | Hold intermediate statement results | Hold working data explicitly managed by the application |
| Table name | Internal, not directly addressable by SQL name | Named by the client |
| Lifecycle | Typically tied to a statement or materialization step within a statement | Persists in the session until `DROP` or session termination |
| Engine | Decided by MySQL configuration and internal rules | Engine can be specified in DDL |
| Monitoring | `EXPLAIN`, Performance Schema, status counters | DDL, metadata, and table/engine inspection tools |

Explicit temporary table example:

~~~sql
CREATE TEMPORARY TABLE session_customer_totals (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    revenue DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO session_customer_totals (customer_id, revenue)
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;

SELECT customer_id, revenue
FROM session_customer_totals
ORDER BY revenue DESC;

DROP TEMPORARY TABLE session_customer_totals;
~~~

This table has a name and lifecycle managed by the session. Limits intended for internal `TempTable` do not automatically convert an explicit temporary table into an internal temporary table. If `ENGINE=MEMORY` is specified, `max_heap_table_size` governs the `MEMORY` table; if `InnoDB` is specified, data is managed via InnoDB mechanics.

A single query can both use an explicit temporary table and spawn an internal temporary table for `ORDER BY`, `GROUP BY`, or another operation. During investigation, separate the origin of each structure.

## 4. Storage Engines for Internal Temporary Tables

### 4.1. `TempTable`

In MySQL 8.0, `TempTable` is the default engine for internal in-memory temporary tables starting from MySQL 8.0.16. This engine is designed for intermediate results and supports variable-length data types. It can store `BLOB`/`TEXT` in cases where `MEMORY` does not support them.

`TempTable` manages a shared RAM region and can use memory-mapped files when configured. When corresponding limits are reached, MySQL transitions to on-disk temporary storage using InnoDB. Exact transition rules depend on version and active limits.

Variables to know:

- `internal_tmp_mem_storage_engine`: selects the engine for internal in-memory temporary tables, typically `TempTable` or `MEMORY`.
- `temptable_max_ram`: server-wide RAM limit allocated for `TempTable`.
- `temptable_max_mmap`: limit on memory-mapped file space `TempTable` is permitted to use, on versions supporting this variable.
- `tmp_table_size`: size limit of an internal in-memory temporary table in versions applying this variable to `TempTable`.
- `tmpdir`: filesystem location used for temporary files, including `TempTable` memory-mapped files.

Do not assume defaults are identical across every MySQL version. Before tuning, check runtime values and documentation for your exact running version.

### 4.2. `MEMORY`

`MEMORY` stores table data in RAM. For internal temporary tables, this engine can be selected via `internal_tmp_mem_storage_engine`. `MEMORY` has different data type restrictions and row representations than `TempTable`; for example, `BLOB`/`TEXT` columns are not supported as in `TempTable`.

When internal temporary tables are configured to use `MEMORY`, the size limit is typically governed by `tmp_table_size` and `max_heap_table_size`; the effective limit is the smaller of the two. When exceeding the limit or encountering unsupported data types, MySQL may convert the internal structure to an on-disk internal temporary table.

Do not confuse `MEMORY` with `TempTable`. Raising `max_heap_table_size` can matter for `MEMORY`, but it is not the same way to expand `TempTable`'s RAM budget.

### 4.3. InnoDB for On-Disk Internal Temporary Tables

When an internal temporary table can no longer remain in the configured in-memory/mmap space, MySQL can use InnoDB for on-disk internal temporary tables. InnoDB provides temporary storage, page management, and disk I/O.

An on-disk internal temporary table remains an internal structure. It is not a long-lived business table and should not be queried by guessing filenames or physical table names.

Older MySQL documentation may mention `internal_tmp_disk_storage_engine` or other engines. `internal_tmp_disk_storage_engine` was removed in MySQL 8.0.16; never apply outdated instructions to newer versions without verifying.

## 5. Path from RAM to Disk

With `TempTable` configured, distinguish three tiers:

1. **`TempTable` RAM:** memory area used by the engine to store internal temporary tables.
2. **Memory-mapped files:** files mapped into the process address space, usable as an overflow tier when `TempTable` RAM hits its limit and mmap is supported/enabled.
3. **InnoDB on-disk internal temporary tables:** InnoDB's temporary storage mechanism when earlier limits no longer permit `TempTable` to keep data in RAM or mmap.

High-level diagram:

~~~text
SQL statement needs intermediate result
                |
                v
      Internal temporary table
                |
                v
       TempTable or MEMORY
                |
        +-------+--------+
        |                |
        v                v
   Fits in RAM      Hits RAM limit
        |                |
        |                v
        |        TempTable mmap available?
        |                |
        |          +-----+-----+
        |          |           |
        |          v           v
        |         Yes          No
        |          |           |
        |          v           |
        |    Memory-mapped     |
        |       files          |
        |          |           |
        |          v           v
        |       Hits mmap limit
        |                |
        +----------------+
                         |
                         v
             InnoDB on-disk temporary
                         |
                         v
                  Statement ends
~~~

This diagram illustrates the common `TempTable` path; actual behavior depends on version, engine, and configuration. `MEMORY` has its own limit rules. Some newer versions have changed or removed older mmap control variables, so check version compatibility notes before applying.

### 5.1. RAM and mmap Are Not the Same

A memory-mapped file is still a file on the filesystem, even though its contents are mapped into the address space and the OS may manage it via the page cache. It is not equivalent to a regular InnoDB table, nor should mmap space be treated as free RAM.

If mmap grows, the filesystem hosting `tmpdir` can fill up or experience I/O pressure. The OS may have to manage many mapped file pages, affecting the page cache and available memory for other workloads.

### 5.2. When Does It Switch to InnoDB?

When `TempTable` RAM is exhausted and mmap is unavailable or reaches its limit, MySQL can switch to InnoDB on-disk internal temporary tables. With `MEMORY`, exceeding the table limit or encountering unsupported data types can also trigger conversion.

Not every spill is an incident. Large analytical queries may require materialization and substantial intermediate data. The operational question is whether spills happen frequently, cause significant latency, fill up the filesystem, or contend for I/O with the primary workload.

## 6. Key RAM Limits

### 6.1. `temptable_max_ram`: Shared Budget

`temptable_max_ram` limits how much RAM `TempTable` can use server-wide. This is a global budget shared across concurrent statements, not an independent quota granted in full to each connection.

If one query creates a large intermediate table, or many queries create temporary tables simultaneously, total demand can hit the budget. `TempTable` must then fall back to the next configured storage tier.

For example, twenty reporting queries run concurrently and each needs to materialize data. Even if each individual query is moderate, total `TempTable` RAM can hit the ceiling faster than expected. Therefore, do not evaluate this variable using only a single query run in isolation on a test box.

### 6.2. `tmp_table_size`: Per-Temporary-Table Limit

`tmp_table_size` is the size limit for an internal in-memory temporary table in versions that apply this variable to `TempTable`. Starting in MySQL 8.0.28, this variable applies as a limit per individual internal `TempTable` table; when a table exceeds the limit, MySQL can convert that table to an on-disk internal temporary table.

In older MySQL versions, the relationship between `tmp_table_size` and `TempTable` differed. Do not extrapolate behavior observed on 8.0.28+ to 8.0.27 or earlier versions.

The per-table limit and global budget solve two different problems:

- `tmp_table_size` caps a single internal in-memory table.
- `temptable_max_ram` caps total `TempTable` RAM shared across the server.

Raising one does not raise the other. Check both and verify how your version applies them.

### 6.3. `max_heap_table_size`

`max_heap_table_size` directly governs `MEMORY` tables. When `internal_tmp_mem_storage_engine` is set to `MEMORY`, the internal in-memory temporary table limit is typically the smaller of `tmp_table_size` and `max_heap_table_size`.

This variable also affects user-created `MEMORY` tables. However, it is not a replacement for `temptable_max_ram` when the internal engine is `TempTable`.

### 6.4. `internal_tmp_mem_storage_engine`

This variable selects the engine used for internal in-memory temporary tables. On MySQL 8.0, the values of interest are `TempTable` and `MEMORY`. `TempTable` is the default from MySQL 8.0.16 onward.

Switching to `MEMORY` can alter RAM consumption, row representation, and data type support. Queries with `BLOB`/`TEXT` or incompatible structures can force MySQL onto on-disk tables. Do not switch engines merely to avoid mmap or because a status counter increments.

### 6.5. `temptable_max_mmap` and `temptable_use_mmap`

`temptable_max_mmap` sets the limit on memory-mapped file space `TempTable` may use on versions supporting this variable. Once reached, subsequent allocations can transition to InnoDB on-disk internal temporary tables.

`temptable_use_mmap` previously controlled whether `TempTable` used memory-mapped files. This variable was deprecated in MySQL 8.0.26; availability and control semantics depend on version. On MySQL 8.4 and later, check the system variables list for your exact release before using this legacy variable.

Do not set `temptable_max_mmap` huge merely to reduce `Created_tmp_disk_tables`. Mmap still consumes filesystem space and can increase I/O. The goal is balancing RAM, filesystem capacity, and query cost.

## 7. Reading Runtime Configuration Before Changing Anything

Start by checking the version and existing variables:

~~~sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'max_heap_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';
SHOW GLOBAL VARIABLES LIKE 'temptable_use_mmap';
SHOW GLOBAL VARIABLES LIKE 'tmpdir';
~~~

Some variables may not exist in the running version or may be deprecated/removed. `SHOW VARIABLES LIKE` returns zero rows when a variable is absent; that does not mean the SQL query failed.

Check session values for variables with `SESSION` scope:

~~~sql
SELECT
    @@GLOBAL.tmp_table_size AS global_tmp_table_size,
    @@SESSION.tmp_table_size AS session_tmp_table_size,
    @@GLOBAL.max_heap_table_size AS global_max_heap_table_size,
    @@SESSION.max_heap_table_size AS session_max_heap_table_size;
~~~

Global-only variables like `temptable_max_ram` have no `@@SESSION` equivalent. Check variable scope in the system variables documentation before querying.

If the application uses a connection pool, session variables may be set individually per connection. Changing global settings does not necessarily update session values already held in existing connections. After tuning, verify actual values on both new and existing sessions.

## 8. Reading Execution Plans for Temporary Tables

### 8.1. `EXPLAIN`

Run `EXPLAIN` on the `SELECT` under investigation:

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

In traditional format, the `Extra` column may display `Using temporary` when the plan needs an internal temporary table. `Using filesort` indicates the server needs an extra sorting step; the word `filesort` does not mean the operation definitely wrote to disk. The name `filesort` describes MySQL's sort algorithm, not a guarantee that sorted data sits on the filesystem.

`EXPLAIN` describes an estimated plan. It does not report exact temporary table sizes or bytes spilled during actual execution. Some materialization inside derived tables or CTEs may not appear as a simple `Using temporary` flag in the single row you are looking at. Read the entire plan tree.

### 8.2. `EXPLAIN FORMAT=TREE` and `EXPLAIN ANALYZE`

~~~sql
EXPLAIN FORMAT=TREE
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

`TREE` makes iterators and materialization steps clearly visible. In MySQL versions supporting `EXPLAIN ANALYZE`, you can measure actual timings and row counts:

~~~sql
EXPLAIN ANALYZE
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

`EXPLAIN ANALYZE` executes the query to collect actual metrics. Run it only on `SELECT` statements verified to be safe under appropriate load and limits; do not treat it as a metadata-only plan inspection command like plain `EXPLAIN`.

### 8.3. Interpreting Indicators in Context

| Indicator | Meaning | What to Check Next |
|---|---|---|
| `Using temporary` | A step in the plan needs an internal temporary table | Operation type, intermediate row count, engine, and RAM usage |
| `Using filesort` | A sort step outside index order is required | Sorted rows, row width, `sort_merge_passes`, and indexes |
| `Materialize` | Intermediate result is materialized | Why it was not merged/streamed, result size, and read counts |
| `Using temporary; Using filesort` | Both an intermediate structure and a sort are present | Identify which step dominates time and I/O |
| No `Using temporary` | Plan does not display this marker | Still verify runtime metrics, digests, and other materialization steps |

Do not aim to eliminate every temporary table. A small in-memory temporary table can be cheaper than recomputing expressions repeatedly or choosing a worse join plan.

## 9. Monitoring via Status Counters

MySQL provides two commonly used status counters:

- `Created_tmp_tables`: number of internal temporary tables created.
- `Created_tmp_disk_tables`: number of internal temporary tables created on disk as counted by the server.

View global values:

~~~sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
~~~

View current session values:

~~~sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
~~~

Status counters are cumulative within their scope. To measure a workload, sample at two timestamps and compute deltas over the interval. A large global value after many days of uptime does not prove the system has an active issue right now.

One key nuance with `TempTable`: `Created_tmp_disk_tables` does not fully reflect internal temporary tables using memory-mapped files. Hence, a low counter does not prove no temporary data is being written to the filesystem. Combine Performance Schema memory instruments and filesystem monitoring.

### 9.1. Calculating Ratios from Deltas

Over a measurement window, record:

~~~text
T0: Created_tmp_tables = 120000
    Created_tmp_disk_tables = 18000

T1: Created_tmp_tables = 125000
    Created_tmp_disk_tables = 19000

Delta tables      = 5000
Delta disk tables = 1000
Disk / tables ratio from counters = 20%
~~~

This is only a reference ratio from two counters. It omits full mmap spills and does not indicate whether temporary tables are large or small. Do not use a single ratio as the sole performance criterion.

### 9.2. Global vs. Session Counters

Session counters are useful when running a test query on an isolated connection and taking before/after differences. Global counters are useful for server-wide observation, though they are affected by all concurrent workloads.

When measuring with session counters, ensure the test query and check statements run on the exact same connection. When measuring globally, record timestamps, system load, and deployment events to avoid misattributing changes to a single query.

## 10. Monitoring Statements in Performance Schema

### 10.1. Ranking Digests Creating Temporary Tables

`performance_schema.events_statements_summary_by_digest` aggregates statements by digest. You can find query groups generating many temporary tables:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_SORT_MERGE_PASSES
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_CREATED_TMP_DISK_TABLES DESC,
         SUM_CREATED_TMP_TABLES DESC
LIMIT 20;
~~~

Summary columns reflect trends per statement group since statistics were initialized or reset. `DIGEST_TEXT` is normalized SQL suitable for grouping structurally identical queries.

A digest with many temporary tables is not automatically the best optimization candidate. Combine `COUNT_STAR`, rows examined, rows returned, total time, and business criticality. A statement running one million times with a small temporary table may matter more than a one-off report with a large temporary table.

### 10.2. Inspecting Individual Statement Events

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    CREATED_TMP_TABLES,
    CREATED_TMP_DISK_TABLES,
    SORT_MERGE_PASSES,
    ROWS_EXAMINED,
    ROWS_SENT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds
FROM performance_schema.events_statements_history_long
WHERE CREATED_TMP_TABLES > 0
   OR CREATED_TMP_DISK_TABLES > 0
ORDER BY TIMER_WAIT DESC
LIMIT 50;
~~~

The `history_long` table is a bounded ring buffer. Events can be overwritten as the workload continues running. When investigating, collect data early and ship important metrics to durable observability storage.

To join statements with connections, map `THREAD_ID` to `PROCESSLIST_ID` in `performance_schema.threads` while the thread still exists. Do not confuse `THREAD_ID` with `CONNECTION_ID()`.

### 10.3. Checking `TempTable` Memory Instruments

You can inspect memory usage via the global memory summary table:

~~~sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/temptable/%'
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC;
~~~

Depending on version and instrument configuration, `TempTable` events may include `memory/temptable/physical_ram` and `memory/temptable/physical_disk`. Some instruments must be enabled before data is collected.

Check instruments:

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'memory/temptable/%'
ORDER BY NAME;
~~~

If instruments are disabled, data may be incomplete. Enabling instrumentation requires appropriate privileges and overhead evaluation. Never alter `setup_instruments` wholesale in production just to test a single query.

### 10.4. `sys` Schema

The `sys` schema provides views aggregating Performance Schema data to make workload analysis easier. You can start by checking views related to statement analysis or temporary tables if present in your MySQL distribution.

~~~sql
SHOW FULL TABLES FROM sys LIKE '%temp%';
SHOW FULL TABLES FROM sys LIKE '%statement%';
~~~

View names and columns may vary across versions. Before putting views into automated runbooks, verify view definitions and access permissions on the actual server.

## 11. Identifying Where Temporary Data Is Written

### 11.1. `tmpdir`

`tmpdir` specifies the directory or list of directories MySQL uses for certain temporary files, including `TempTable` memory-mapped files. Read the configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmpdir';
~~~

On the host, check:

- Remaining free space on the filesystem hosting `tmpdir`.
- Remaining inodes on inode-limited filesystems.
- Ownership and write permissions for the user running `mysqld`.
- Space growth while running reports or batches.
- I/O latency and queue depth of the device backing `tmpdir`.
- Cleanup policies and recovery behavior after an abnormal `mysqld` shutdown.

Never manually delete files currently open by `mysqld`. Temporary files may be held open or memory-mapped by the process. Deleting files while the server is running can break tasks or fail to reclaim space as expected.

### 11.2. InnoDB Temporary Tablespaces

On-disk internal temporary tables use InnoDB's temporary tablespace mechanism. Location and management depend on version and InnoDB configuration; not all temporary files live in `tmpdir`.

Check related variables if available:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp%';
SHOW GLOBAL VARIABLES LIKE 'innodb_data_home_dir';
~~~

On the host, verify actual directories and monitor temporary tablespace file sizes, growth rates, I/O, and filesystem headroom. Do not guess locations from filenames alone or assume every version uses a single file.

### 11.3. Distinguishing File Size from RAM

A large mmap file does not mean the entire file size is consuming physical RAM. Conversely, growing mmap usage can still put pressure on the page cache and filesystem. Monitor simultaneously:

- `TempTable` memory instruments.
- `tmpdir` capacity and I/O.
- InnoDB temporary tablespace sizes.
- OS available memory, swap, and page cache.
- CPU, I/O wait, and statement duration.

Do not use a single filesystem metric to conclude how much RAM `TempTable` is consuming.

## 12. Why Temporary Tables Spill to Disk and Performance Impact

Common causes:

1. **Large intermediate sets:** queries reading many rows before `GROUP BY`, `DISTINCT`, or sorting.
2. **Wide intermediate rows:** selecting many columns, large strings, or unneeded data.
3. **Missing appropriate indexes:** the server must read many rows and sort/group in a separate step.
4. **Materialization:** derived tables or CTEs stored with large row counts.
5. **Low configuration limits:** `tmp_table_size` or `TempTable` budget insufficient for the workload.
6. **High concurrency:** many queries sharing the `TempTable` RAM region simultaneously.
7. **Filesystem constraints:** mmap or InnoDB temporary tablespaces running out of space or hitting high I/O.
8. **Data types/engine:** `MEMORY` does not support certain data types, forcing an on-disk path.

When spills occur, MySQL must read/write intermediate data through storage. Impacts can include:

- Increased query duration due to I/O and page management overhead.
- I/O contention with redo logs, data files, binary logs, or other workloads.
- Shrinking filesystem space, raising out-of-space risk.
- Concurrent queries taking longer to complete and holding resources longer.
- Longer-lived transactions or connections if applications process results slowly.

A spill does not automatically mean a broken query or an out-of-RAM server. Measure duration, row counts, intermediate sizes, concurrency, and impact on the primary workload.

## 13. Optimizing SQL to Reduce Temporary Tables and Intermediate Data

### 13.1. Reduce Input Rows Early

Push safe filter predicates as close to the data source as possible:

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

With an index matching `status` and `created_at`, MySQL can reduce rows read before aggregation. Index column order must reflect selectivity, query predicates, and overall workload; never create an index for a single isolated SQL query.

### 13.2. Select Only Needed Columns

Avoid `SELECT *` in queries that build intermediate sets:

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

If intermediate sets carry wide `VARCHAR`/`TEXT` or unused columns, storage, copying, and sorting costs rise. Narrowing row width often helps even when row counts stay constant.

### 13.3. Designing Indexes for `GROUP BY` and `ORDER BY`

Indexes can let the server read data in a useful order and avoid sort or temporary table steps in some plans. Example:

~~~sql
CREATE INDEX idx_orders_status_created_customer
ON orders (status, created_at, customer_id);
~~~

The index above is an illustrative example only. An equality predicate on `status`, a range on `created_at`, and grouping by `customer_id` may allow the optimizer to leverage only part of the index order. Check `EXPLAIN`, cardinality, actual row counts, and index write cost before deploying.

Indexes cannot always eliminate temporary tables. If `ORDER BY SUM(total_amount)` is required, the sum only exists after `GROUP BY`, so sorting may still be necessary.

### 13.4. Eliminating Unnecessary `DISTINCT` or `UNION`

`DISTINCT` and `UNION` incur deduplication costs. If keys or data constraints already guarantee uniqueness, consider removing `DISTINCT`. If business logic allows duplicates, `UNION ALL` can avoid the deduplication step.

Prove correctness from data invariants and business requirements. Never remove `DISTINCT` solely to make `EXPLAIN` look cleaner.

### 13.5. Evaluating CTE and Derived Table Materialization

CTEs can be merged or materialized depending on structure and optimizer choices. Materialization helps when results are reused multiple times, yet can consume memory if the result is huge.

~~~sql
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE created_at >= '2026-01-01'
)
SELECT customer_id, SUM(total_amount)
FROM recent_orders
GROUP BY customer_id;
~~~

Ensure filter predicates sit at the right level to shrink intermediate datasets. Use `EXPLAIN FORMAT=TREE` to check whether the CTE is merged or materialized. Do not force the optimizer with hints without measuring the benefit.

### 13.6. Reducing Repeated Materializations

If the same calculation repeats across multiple subqueries or CTEs, consider restructuring the query to reuse results when beneficial. Conversely, a single-use massive materialization may be better replaced by a different join strategy or query structure.

Weigh trade-offs between recomputation, single materialization, intermediate row count, and concurrency. There is no universal rule that merging always beats materialization.

### 13.7. Limiting Data Before Sorting

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 50;
~~~

An index on `(customer_id, created_at)` can support both filtering and ordering when sort direction aligns. When the query can read exactly 50 rows from the index, the server does not need to sort the customer's entire history.

Conversely, `LIMIT` after `GROUP BY` or `ORDER BY` on an aggregate expression does not necessarily reduce the rows that must be aggregated. Check the plan and actual row counts.

## 14. Tuning Configuration Within the System Budget

### 14.1. Do Not Raise All Limits at Once

A controlled test can change one variable at a time, record a baseline, run the same workload, and compare. Example:

~~~sql
SET GLOBAL temptable_max_ram = 1073741824;
~~~

The value above merely illustrates byte notation; it is not a default production recommendation. Before setting a value, check the current value, scope, valid range, and actual available RAM.

For session-scoped variables like `tmp_table_size`, controlled testing can run on a dedicated connection:

~~~sql
SET SESSION tmp_table_size = 67108864;
~~~

A session change affects only that connection. If a connection pool holds many existing sessions, identify where configuration is applied and how new connections are initialized.

### 14.2. Memory Budgeting

When planning, do not simply add one number for `TempTable`. Reserve RAM for:

- InnoDB buffer pool.
- Connection/thread overhead.
- Sort buffers, join buffers, and per-operation/per-session buffers.
- `TempTable` RAM.
- Table caches, metadata, Performance Schema, and server structures.
- Operating system, page cache, monitoring agents, and other processes.

`temptable_max_ram` is a shared `TempTable` budget, while `tmp_table_size` can cap individual tables. Multiple statements can hold multiple intermediate tables concurrently; a single statement can also create multiple intermediate structures. Therefore, use a representative workload to measure peak usage and keep headroom for bursts.

Never set `temptable_max_ram` equal to all remaining free RAM via naive subtraction. The server needs memory for other workloads and the OS; mmap also puts pressure on the filesystem and page cache.

### 14.3. Balancing RAM, mmap, and InnoDB

- Raising the RAM budget can reduce mmap or InnoDB spills, but increases memory pressure risk under high concurrency.
- Raising the mmap limit lets `TempTable` hold more data in mapped files, but the filesystem can fill up and I/O can rise.
- Setting a low per-table limit can force large tables to spill early even while global RAM budget remains free.
- Using `MEMORY` instead of `TempTable` alters behavior and data type support; it is not a default way to reduce spills.

Choose values based on peak concurrency and actual intermediate set sizes. Evaluate p95/p99 latency, throughput, memory pressure, and filesystem I/O together.

### 14.4. Persistence and Rollback

If changing a global variable for testing, record the old value and scope of impact. `SET GLOBAL` may not persist across restarts. `SET PERSIST` can save values across restarts on supporting versions; `SET PERSIST_ONLY` takes effect on the next startup. Required privileges and variable behavior depend on version.

Do not use `SET PERSIST` simply because a single test succeeded. Before persisting, run a full representative workload, observe multi-node impact, and prepare a rollback plan. If editing config files, back up the old file and verify runtime values after restart.

## 15. Investigation Scenario: Reports Rapidly Filling Temporary Filesystem

Suppose during peak hours the filesystem hosting `tmpdir` fills rapidly and several reports run slower than usual. Investigation steps:

1. **Record timing and instance.** Identify the node, MySQL version, when space growth began, and active workloads.
2. **Inspect the filesystem.** Check free space, inodes, I/O latency, and file growth rate inside `tmpdir`. Verify write permissions and mount point.
3. **Read runtime variables.** Check `internal_tmp_mem_storage_engine`, `temptable_max_ram`, `temptable_max_mmap`, `tmp_table_size`, `tmpdir`, and version-specific variables.
4. **Capture status deltas.** Snapshot `Created_tmp_tables` and `Created_tmp_disk_tables` at the start and end of a window. Remember the disk counter does not fully capture mmap files.
5. **Rank digests.** Use `events_statements_summary_by_digest` to find statement groups creating many temporary or disk tables.
6. **Read execution plans.** Pick a representative digest, grab sample SQL, and run `EXPLAIN`; run `EXPLAIN ANALYZE` on a replica or safe test window to inspect row counts and iterators.
7. **Inspect memory instruments.** Check `memory/temptable` if enabled; compare current RAM, high-water mark, and filesystem usage.
8. **Check concurrency.** Determine how many reports run concurrently, connection pools, batch schedules, and ad-hoc queries.
9. **Try SQL changes first.** Reduce intermediate rows and row width, inspect indexes and materialization. Re-measure on the same data.
10. **Only then test config.** Change one limit in a controlled way, record old values, measure latency, memory, I/O, and filesystem; roll back if impact worsens.
11. **Set alerts.** Alert on `tmpdir` usage, InnoDB temporary tablespaces, I/O waits, and temporary table statement ratios.
12. **Document in a runbook.** Save SQL, digest, execution plan, runtime variables, measurement window, changes, and results.

Never manually delete temporary files to free space while `mysqld` is running. If the filesystem is about to fill, throttle or stop the offending workload per runbook to protect the server and handle via the DBA team's operational procedure.

## 16. Common Mistakes

| Mistake | Why It Is Wrong | Better Approach |
|---|---|---|
| Seeing `Using temporary` and concluding the table spilled to disk | The flag only indicates an internal temporary table is needed | Measure engine, counters, memory, and filesystem |
| Seeing `Created_tmp_disk_tables` stay flat and concluding no spill happened | mmap files are not fully reflected in this counter | Check `TempTable` memory instruments and `tmpdir` |
| Raising `tmp_table_size` to solve every `TempTable` issue | Global RAM budget and per-table limits differ; versions behave differently | Check both `tmp_table_size` and `temptable_max_ram` for your version |
| Raising `max_heap_table_size` even when engine is `TempTable` | This variable primarily governs `MEMORY` | Verify `internal_tmp_mem_storage_engine` |
| Switching `internal_tmp_mem_storage_engine` to `MEMORY` to save RAM | `MEMORY` has stricter data type limits and different behavior; may spill earlier | Compare workloads and execution plans |
| Raising `temptable_max_mmap` without checking disk | Mmap still consumes filesystem space and can fill `tmpdir` | Monitor free space, inodes, and I/O |
| Treating every temporary table as `CREATE TEMPORARY TABLE` | The two types have different lifecycles and management mechanisms | Distinguish internal vs. user-created |
| Looking at only one isolated query | Concurrent workloads create global budget pressure | Measure actual concurrency |
| Optimizing to eliminate all temporary tables | Can force repeated computations or worse join plans | Optimize for overall latency and throughput |
| Deleting tmp files while the server is running | Files may still be open or memory-mapped | Use runbooks and MySQL's management mechanisms |

## 17. Operational Checklist

- [ ] Distinguished internal temporary tables from `CREATE TEMPORARY TABLE`.
- [ ] Identified the active engine in `internal_tmp_mem_storage_engine`.
- [ ] Checked available RAM and mmap limits for the exact MySQL version.
- [ ] Verified `tmp_table_size`, `temptable_max_ram`, and `max_heap_table_size` within their proper scopes.
- [ ] Checked whether `temptable_use_mmap` is still supported or deprecated/removed.
- [ ] Read `EXPLAIN` or `EXPLAIN FORMAT=TREE` for queries creating temporary tables.
- [ ] Measured status counters via deltas in a controlled window.
- [ ] Inspected statement digests and event histories in Performance Schema.
- [ ] Checked `memory/temptable` instruments if available.
- [ ] Monitored `tmpdir`, InnoDB temporary tablespaces, filesystem space, and I/O.
- [ ] Measured workload under representative concurrency.
- [ ] Attempted reducing intermediate rows and row width before raising limits.
- [ ] Recorded old values, rationale, scope, and rollback plan for every variable change.
- [ ] Avoided manually deleting temporary files while `mysqld` is using them.
- [ ] Established alerts and runbooks for temporary filesystems nearing capacity.

## 18. Practice Exercises

### Exercise 1: Identifying Internal Temporary Tables

Write a `GROUP BY` query combined with `ORDER BY` on an aggregate expression. Run `EXPLAIN` and record `Using temporary`, `Using filesort`, or materialization nodes if present. Try adding an appropriate index and compare plans.

**Expected deliverable:** explanation of which step builds intermediate results and whether the index changed the plan.

### Exercise 2: Measuring Session Status Counters

On an isolated connection, capture `SHOW SESSION STATUS LIKE 'Created_tmp%'`. Run a query with `DISTINCT` or `GROUP BY` on a test dataset, then capture the counters again and calculate deltas.

**Expected deliverable:** deltas for `Created_tmp_tables` and `Created_tmp_disk_tables`, noting that the counters do not fully reflect mmap usage.

### Exercise 3: Finding Digests Creating Many Temporary Tables

Query `events_statements_summary_by_digest`, ordering by `SUM_CREATED_TMP_TABLES` and `SUM_CREATED_TMP_DISK_TABLES`. Pick a digest with high `COUNT_STAR`, retrieve sample SQL, and inspect its execution plan.

**Expected deliverable:** digest, execution count, temporary table counts, rows examined, total time, and optimization proposals.

### Exercise 4: Monitoring `TempTable` Memory

Check memory instruments named `memory/temptable`. If enabled, read `CURRENT_NUMBER_OF_BYTES_USED` and `HIGH_NUMBER_OF_BYTES_USED` in `memory_summary_global_by_event_name`. Run a test workload and observe changes.

**Expected deliverable:** before/after metrics and explanation of instrument limitations.

### Exercise 5: Simulating Spills and Assessing Concurrency

In a test environment with a sufficiently large dataset, run a query creating a controlled intermediate set. Compare single execution vs. multiple concurrent sessions. Monitor latency, `TempTable` memory, status counters, and filesystem usage.

**Expected deliverable:** impact of concurrency on the shared RAM budget and disk usage. Never run stressful experiments in production.

## 19. Reference Documentation

When implementing, consult the MySQL Reference Manual matching your version for:

- Internal Temporary Tables.
- TempTable Storage Engine.
- Internal Temporary Table Use in MySQL.
- System Variables: `internal_tmp_mem_storage_engine`, `tmp_table_size`, `max_heap_table_size`, `temptable_max_ram`, `temptable_max_mmap`, `temptable_use_mmap`, and `tmpdir`.
- Status Variables: `Created_tmp_tables` and `Created_tmp_disk_tables`.
- Performance Schema statement event tables and memory summary tables.
- `EXPLAIN` Output, `EXPLAIN FORMAT=TREE`, and `EXPLAIN ANALYZE`.
- InnoDB Temporary Tablespaces.

Changes across MySQL 8.0.x, 8.4, and newer branches can affect the default engine, per-table limits, and mmap variables. Always verify `@@version`, `SHOW VARIABLES`, and release documentation for your running server before applying configurations or runbooks.
