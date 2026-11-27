# Internal Temporary Tables, TempTable/MEMORY, and Spill-to-Disk Conditions

While executing an SQL statement, MySQL sometimes needs to store intermediate results to sort, group, deduplicate, or materialize a derived table/CTE. These structures are called **internal temporary tables**. They are created, managed, and reclaimed by the optimizer and server during execution; applications do not create or drop them manually.

MySQL can hold internal temporary tables in RAM using the `TempTable` or `MEMORY` storage engine. When results exceed relevant limits, MySQL can spill to temporary on-disk storage, typically using InnoDB. With `TempTable`, there is also a memory-mapped files tier between RAM and InnoDB when the global RAM budget reaches its threshold. Therefore, seeing a query create a temporary table does not immediately mean it wrote to disk; you need to understand the engine, limits, and actual metrics.

## Objectives

After this lesson, you will be able to:

- Distinguish internal temporary tables from application-created `TEMPORARY` tables.
- Identify SQL operations that can cause MySQL to materialize intermediate results.
- Compare `TempTable` and `MEMORY` when storing temporary tables in RAM.
- Explain the `tmp_table_size`, `temptable_max_ram`, and `temptable_max_mmap` thresholds.
- Describe the transition steps from RAM to memory-mapped files or the InnoDB temporary tablespace.
- Monitor temporary table counts, TempTable memory usage, and spill-to-disk indicators.
- Reduce materialization needs via indexes, early filtering, and narrower intermediate data.

Examples assume MySQL 8.0 or later. Certain limits and behaviors change across versions; notably, `tmp_table_size` began applying as a per-table limit for `TempTable` internal temporary tables in MySQL 8.0.28. `temptable_max_mmap` was introduced in 8.0.23; `temptable_use_mmap` was deprecated in 8.0.26. Check actual variables on the exact server version you operate.

## 1. How Do Internal Temporary Tables Differ from TEMPORARY Tables?

The two kinds of temporary tables have different purposes and lifecycles:

| Characteristic | Internal Temporary Table | Application-Created `TEMPORARY` Table |
|---|---|---|
| Who creates it? | MySQL optimizer/server during execution | Application or user via `CREATE TEMPORARY TABLE` |
| Table name | Internal, not directly accessible via standard SQL | Has a creator-specified name |
| Purpose | Stores intermediate results for sorting, grouping, materialization, etc. | Stores intermediate data controlled by application logic |
| Engine | Chosen by MySQL based on configuration and plan | Engine can be specified, e.g., `InnoDB` or `MEMORY` |
| Lifecycle | Usually exists only during statement execution or internal scope | Exists in the session until dropped or the session ends |
| Monitoring | Status counters, Performance Schema, and execution plans | Session metadata, statements, and table inspection tools |

Example of an application-created temporary table:

```sql
CREATE TEMPORARY TABLE selected_customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    priority TINYINT NOT NULL
) ENGINE = InnoDB;

INSERT INTO selected_customers (customer_id, priority)
VALUES (101, 1), (205, 2), (309, 3);

SELECT c.customer_id, c.email
FROM customers AS c
JOIN selected_customers AS s
  ON s.customer_id = c.customer_id;

DROP TEMPORARY TABLE selected_customers;
```

The `selected_customers` table can be accessed via SQL within the session that created it; other sessions cannot see it. If the session ends, MySQL drops that temporary table automatically. This is an application-managed object, distinct from internal temporary tables created automatically by the optimizer.

For an application-created `TEMPORARY` table using `MEMORY`, once `max_heap_table_size` is reached, writes typically fail with a table-full error; MySQL does not automatically convert that user table to InnoDB. The automatic conversion to InnoDB described in this lesson applies to internal temporary tables.

## 2. When Does MySQL Create an Internal Temporary Table?

The optimizer may create an internal temporary table when it needs to hold an intermediate result set that cannot be processed directly in a single index scan or simple pipeline. Common situations include:

- `GROUP BY` when index order does not satisfy the required grouping.
- `DISTINCT` to eliminate duplicate rows.
- `ORDER BY` when ordering cannot be satisfied directly from an index or intermediate results must be sorted.
- `UNION` (especially when deduplication is needed) and certain multi-query-block processing patterns.
- Materialization of non-mergeable derived tables, views, or CTEs.
- Certain subqueries requiring result materialization.
- Window functions and operations needing to store or sort row sets.

Merely having `GROUP BY`, `ORDER BY`, or `DISTINCT` does not guarantee a temporary table is created. If an appropriate index provides the required order or grouping, the optimizer may avoid creating a temporary table. Conversely, a seemingly simple query may still materialize due to how joins, expressions, and query blocks combine.

The order examples in this lesson assume the following InnoDB table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_orders_created_customer (created_at, customer_id)
) ENGINE = InnoDB;
```

Example aggregating orders by customer:

```sql
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

MySQL must compute sums per group and then sort by the aggregated value `revenue`. This value does not pre-exist in any source table index, so it generally requires a step to store or process grouped results before sorting. Confirm the exact plan with `EXPLAIN`.

## 3. TempTable and MEMORY

MySQL supports two engines for creating internal temporary tables in RAM: `TempTable` and `MEMORY`. The `internal_tmp_mem_storage_engine` variable controls this choice. In modern MySQL 8.0, `TempTable` is the default.

| Feature | TempTable | MEMORY |
|---|---|---|
| Role | Internal engine dedicated to temporary tables | Memory engine usable for temporary tables |
| Data types | Supports variable-length types and large types like `BLOB`/`TEXT` in modern versions | Has data type restrictions; does not support `BLOB`/`TEXT` like TempTable |
| Row storage | Flexible representation suited for variable-length data | Rows use fixed-length representation, potentially wasting memory on variable-length columns |
| Limits | Uses per-table limit and global TempTable budget; can spill to mmap/InnoDB | Subject to MEMORY table size limits and related config limits |
| When limit exceeded | Can switch to on-disk temporary storage per config/version | Internal temporary table can be converted to on-disk InnoDB |

### TempTable

`TempTable` is designed for internal temporary tables and has been the default choice since MySQL 8.0.16. This engine handles variable-length data like `VARCHAR` and `VARBINARY` efficiently, and supports BLOB/TEXT types since MySQL 8.0.13. It allocates memory in blocks and can use memory-mapped files when the global RAM budget reaches its threshold.

Broader data type support prevents MySQL from spilling temporary tables to disk merely because results contain `TEXT`/`BLOB` columns, unlike earlier `MEMORY` limitations. Even so, result size, concurrent sessions, and configuration thresholds can still cause TempTable to spill to another storage tier.

### MEMORY

`MEMORY` stores rows in RAM and uses index structures like HASH or BTREE depending on declaration. This engine has different data type limits and row representations compared to TempTable. For internal temporary tables using MEMORY, `tmp_table_size` and `max_heap_table_size` both participate in bounding size; the effective limit is the smaller of the two variables.

MEMORY rows allocate fixed storage based on column definitions, so string columns with large declared lengths can consume substantial memory even when actual values are short. Do not pick MEMORY simply because the engine name contains "memory"; evaluate row sizes, data types, and overflow behavior.

### Checking the Current Internal Engine

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'default_storage_engine';
```

`default_storage_engine` controls the default engine for user-created tables; it does not replace `internal_tmp_mem_storage_engine` when checking the engine for internal temporary tables.

## 4. Thresholds Governing RAM and Spill

No single variable controls all memory across all temporary tables. You must distinguish per-table limits from the shared global TempTable resource budget.

| Variable | Scope / Meaning | Behavior When Threshold Exceeded |
|---|---|---|
| `tmp_table_size` | Maximum size of a single internal in-memory temporary table; applies to TempTable since MySQL 8.0.28 | When a temporary table exceeds the version-specific limit, MySQL can convert that table to on-disk InnoDB |
| `temptable_max_ram` | Maximum RAM budget the TempTable engine is permitted to use server-wide | Once reached, new allocations use memory-mapped files if enabled and mmap budget remains |
| `temptable_max_mmap` | Maximum budget for memory-mapped files used by TempTable | Once reached, new allocations use InnoDB for internal on-disk temporary tables |
| `max_heap_table_size` | Size limit for MEMORY tables; affects internal temp tables using MEMORY | MEMORY table can be converted to InnoDB when the effective limit is exceeded |
| `internal_tmp_mem_storage_engine` | Selects internal RAM engine: `TempTable` or `MEMORY` | Affects storage format and which limiting mechanisms apply |

`tmp_table_size` and `temptable_max_ram` do not share the same scope. An individual temporary table can exceed its limit before the server's total TempTable budget is exhausted. Conversely, many small temporary tables across concurrent sessions can collectively exhaust the global TempTable budget.

`max_heap_table_size` does not apply to temporary tables using `TempTable`; it only participates in limiting when the selected internal engine is `MEMORY`. For `TempTable`, the global RAM budget `temptable_max_ram` also does not account for all thread-local memory blocks used by each thread, so it should not be treated as an absolute ceiling on every byte related to TempTable.

### Checking Configuration Values

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'internal_tmp_mem_storage_engine',
    'tmp_table_size',
    'max_heap_table_size',
    'temptable_max_ram',
    'temptable_max_mmap',
    'tmpdir'
);
```

Do not assume default values are identical across versions or environments. Record actual values, GLOBAL/SESSION scopes, and dynamic status before making changes.

On versions that still support `temptable_use_mmap`, that variable controls whether mmap is used when the TempTable RAM budget is reached; it was deprecated in MySQL 8.0.26. Setting `temptable_max_mmap = 0` disables mmap allocations and causes TempTable to use InnoDB when the RAM budget is exceeded. Prefer checking and configuring `temptable_max_mmap` per the running version's documentation rather than building new automation on deprecated variables.

## 5. Journey from RAM to Disk

With TempTable, the process can be visualized as follows:

```text
                   Query needs intermediate result
                              |
                              v
                       TempTable in RAM
                         /           \
     exceeds tmp_table_size         reaches global temptable_max_ram
                  |                             |
                  v                             v
        InnoDB on-disk temp table       Memory-mapped files (tmpdir)
        (temporary tablespace)                    |
                                    reaches temptable_max_mmap
                                                |
                                                v
                                      InnoDB on-disk temp table
                                      (temporary tablespace)
```

This is the conceptual model for MySQL 8.0.28 and later: exceeding `tmp_table_size` can cause an individual TempTable to convert to InnoDB; reaching the global RAM budget `temptable_max_ram` causes new allocations to use mmap if `temptable_max_mmap` budget remains; when the mmap budget is exhausted, new allocations use InnoDB for internal on-disk temporary tables. TempTable does not move previously written data from RAM into mmap files; a single table may have part of its data in RAM and newly allocated parts in temporary files. On older versions, per-table limits differ; do not assume `tmp_table_size` applies the same way. When mmap is disabled or the mmap limit is 0, TempTable can fall back to InnoDB immediately once RAM budget is exhausted.

### Memory-Mapped Files Are Not the Same as InnoDB Temp Tablespace

A memory-mapped file is a file mapped into a process's address space; the operating system manages paging file pages in and out. TempTable uses this mechanism as a temporary storage tier once RAM reaches its threshold. Mmap files typically reside in the `tmpdir` directory.

MySQL creates mmap files in `tmpdir`, opens them, and unlinks their filenames immediately; therefore, the files may not appear in directory listings even though space remains held by the OS until TempTable closes the file or the `mysqld` process stops. Do not rely solely on directory listings to conclude `tmpdir` is not being used by TempTable.

Internal temporary tables using on-disk InnoDB are stored in InnoDB temporary tablespaces managed by the engine. Depending on version and configuration, there may be a global temporary tablespace and session temporary tablespaces. Do not assume all on-disk internal temp tables are files inside `tmpdir`.

Since MySQL 8.0.16, InnoDB is the engine used for on-disk internal temporary tables; earlier versions still had configuration options for other on-disk temp engines. In MySQL 8.0, InnoDB on-disk internal temporary tables are created in session temporary tablespaces located in the data directory by default.

`tmpdir` remains critical for memory-mapped files and other temporary operations. Ensure the filesystem has adequate capacity, permissions, and performance. For InnoDB temporary tablespaces, monitor capacity and InnoDB's own file management rules.

## 6. What Happens When a Temporary Table Spills to Disk?

When an internal temporary table can no longer fit entirely in RAM, MySQL may have to write and read intermediate data from temporary storage. This increases I/O and typically slows down queries, especially when temporary tables are large or read/written repeatedly.

Costs can include:

- Writing intermediate rows to files or InnoDB temporary tablespaces.
- Re-reading data to sort, group, join, or materialize query blocks.
- Building indexes on the temporary table if needed by the optimizer.
- I/O contention with the primary workload on the same storage device.
- Increased space usage in `tmpdir` or InnoDB temporary tablespaces.

Spilling to disk does not automatically mean a query is broken. A large sort or legitimate aggregation sometimes requires intermediate storage and still delivers acceptable performance. Measure latency, row counts, data volume, and repetition frequency before optimizing.

Conversely, a query creating many small temporary tables yet running thousands of times per minute can also generate significant load. Evaluate both frequency and size.

## 7. Identifying Temporary Tables in Execution Plans

Run `EXPLAIN` to see how the optimizer expects to execute the query:

```sql
EXPLAIN
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

In tabular output, the `Extra` column may display `Using temporary`. This indicates MySQL expects to use an internal temporary table for part of the plan. However:

- `Using temporary` does not tell you whether the temporary table stays in RAM, mmap, or on-disk InnoDB.
- It does not tell you the temporary table's size or I/O duration.
- Not every internal temporary table is represented by the exact same `Extra` string across all plan formats.
- `Using filesort` is a separate sorting mechanism; it does not necessarily mean a temporary table spilled to disk.

With `EXPLAIN FORMAT=TREE`, you can see more specific materialization or aggregate/sort nodes depending on the query. Since MySQL 8.0.18, `EXPLAIN ANALYZE` executes the query and reports actual row counts, loop counts, and timings per node:

```sql
EXPLAIN ANALYZE
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

`EXPLAIN ANALYZE` actually runs the `SELECT` statement; use it in an appropriate environment and account for query load before running in production.

## 8. Monitoring Temporary Table Counts

Useful status counters:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

| Counter | Meaning |
|---|---|
| `Created_tmp_tables` | Number of internal temporary tables created |
| `Created_tmp_disk_tables` | Number of on-disk internal temporary tables created as counted by the counter |
| `Created_tmp_files` | Number of temporary files created by mysqld |

These counters are cumulative since server startup or status reset. Take two samples over time to compute deltas and compare them against request counts or SQL statement counts over the same interval.

**Limitation to remember:** `Created_tmp_disk_tables` does not count internal temporary tables using memory-mapped files. Therefore, this counter may underreport temporary tables that used storage outside RAM. You cannot rely solely on the `Created_tmp_disk_tables / Created_tmp_tables` ratio to accurately conclude TempTable's spill-to-disk rate.

### Monitoring TempTable Memory in Performance Schema

If memory instruments are enabled, you can inspect current and peak usage:

```sql
SELECT EVENT_NAME,
       CURRENT_NUMBER_OF_BYTES_USED,
       HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/temptable/%';
```

Common instruments include `memory/temptable/physical_ram` and `memory/temptable/physical_disk`. Exact instrument names and collection depend on version, Performance Schema configuration, and whether instruments are enabled. If the query returns no rows, check `performance_schema.setup_instruments` and access privileges before concluding the engine is not using TempTable.

### Monitoring Storage Space

- Check the filesystem hosting `tmpdir` to detect space consumed by mmap files.
- Monitor InnoDB temporary tablespaces and InnoDB temporary file usage.
- Monitor I/O latency, disk utilization, and query latency during intervals with spills.
- Correlate server metrics with query digests to pinpoint SQL statements creating the most temporary tables.

## 9. Controlled Configuration and Testing

Inspect before making changes:

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'tmpdir';
```

You can test the internal engine in a test session:

```sql
SET SESSION internal_tmp_mem_storage_engine = 'TempTable';
```

Or compare against `MEMORY` if version and privileges permit:

```sql
SET SESSION internal_tmp_mem_storage_engine = 'MEMORY';
```

Do not extrapolate server-wide behavior from a single small session. `temptable_max_ram` and `temptable_max_mmap` are server-wide budgets; changing them affects concurrent sessions. Before adjusting global values, calculate total RAM allocated to the buffer pool, connections, sort/join buffers, TempTable, and other processes.

Starting in MySQL 8.0.27, changing `internal_tmp_mem_storage_engine` at session scope requires `SESSION_VARIABLES_ADMIN` or `SYSTEM_VARIABLES_ADMIN` privileges. If `SET SESSION` is rejected, verify privileges and governance policies before testing; do not elevate an application account's privileges just to run benchmarks.

`tmp_table_size` and `max_heap_table_size` can have session/global scopes depending on the variable; check `SHOW VARIABLES` and documentation for your exact version. In MySQL 8.0.28 and later, `tmp_table_size` is a per-table limit for internal TempTable tables. On older versions, do not assume it limits individual TempTables the same way.

Do not raise every limit to huge values just to lower `Created_tmp_disk_tables`. Many concurrent sessions can simultaneously create large temporary tables, causing unexpected RAM exhaustion. Test at production-like concurrency and monitor both RAM and disk space.

## 10. Reducing the Need to Create or Materialize Temporary Tables

Effective optimization usually begins with query shape and indexes, not merely increasing memory thresholds.

### Filter Early and Select Fewer Columns

Fetch only necessary columns and apply predicates as early as possible:

```sql
-- Unnecessarily wide intermediate result:
SELECT *
FROM orders
WHERE created_at >= '2026-01-01';

-- Select only columns needed for the report:
SELECT customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01';
```

Fewer columns shrink intermediate row width, especially when large string, JSON, or TEXT columns exist.

### Design Indexes for Filtering, Grouping, and Ordering

If queries frequently filter by `status` and group by `customer_id`, an appropriate composite index can reduce rows read:

```sql
CREATE INDEX ix_orders_status_customer
ON orders (status, customer_id);
```

Indexes cannot always eliminate temporary tables, particularly when sorting by an aggregate such as `SUM(amount)`. Confirm via `EXPLAIN` and real metrics.

### Avoid Unnecessary Materialization of Large Datasets

If a derived table is just a simple projection/filter, letting the optimizer merge it avoids creating an intermediate table. For CTEs or derived tables referenced multiple times, materialization can sometimes be cheaper than recomputation. Balance reuse count, result size, and internal indexes.

### Narrow GROUP BY/DISTINCT Width

Group or distinct only on necessary columns. `SELECT DISTINCT` over many wide columns increases intermediate key size and deduplication cost. If business logic only needs one identifier, do not include extra unnecessary columns in the distinct list.

### Pagination and Batch Processing

For very large reports, consider processing by key ranges or time ranges rather than building one giant intermediate result in a single statement. Batching must preserve exact semantics and business snapshot requirements.

## 11. Common Misconceptions

| Misconception | Reality |
|---|---|
| `Using temporary` means it wrote to disk | It only reports a temporary table is used; the table may reside in RAM |
| `Created_tmp_disk_tables = 0` means no spills | The counter does not fully count temporary tables using memory-mapped files |
| Increasing `tmp_table_size` always solves the issue | Global TempTable budget, mmap, InnoDB temp tablespace, and concurrency can still be limits |
| TempTable and MEMORY are identical | They differ in supported data types, row representation, and space management |
| Every `ORDER BY` creates a temporary table | Indexes can provide ordering; filesort and temporary tables are distinct concepts |
| Internal temporary tables are like `CREATE TEMPORARY TABLE` | One is server-created; the other is application-created and session-managed |
| Spilling to disk is always a bug | Spilling can be a reasonable trade-off for large queries; evaluate latency and resources |

## 12. Investigation Workflow for Queries Creating Many Temporary Tables

1. Identify the query digest and endpoint issuing the query; measure execution counts, p95/p99, and total time.
2. Run `EXPLAIN` to look for `Using temporary`, materialization, grouping, or sorting.
3. Use `EXPLAIN ANALYZE` in an appropriate environment to inspect actual row counts and per-node timings.
4. Capture deltas of `Created_tmp_tables`, `Created_tmp_disk_tables`, and `Created_tmp_files` over the same workload window.
5. Read TempTable Performance Schema memory instruments if available; inspect `tmpdir` and InnoDB temporary tablespaces.
6. Check values of `internal_tmp_mem_storage_engine`, `tmp_table_size`, `temptable_max_ram`, `temptable_max_mmap`, and `max_heap_table_size`.
7. Check whether the query can filter earlier, drop unnecessary columns, use indexes, or avoid needless materialization.
8. Test changes one factor at a time in a test environment; re-measure latency, RAM, I/O, and concurrency.
9. Only alter global configuration after budgeting server-wide memory resources and preparing a rollback plan.

## 13. Hands-on Practice

Assume an InnoDB table `orders(order_id, customer_id, status, total_amount, created_at)`.

1. Run a query with `GROUP BY customer_id` and `ORDER BY SUM(total_amount) DESC`. Use `EXPLAIN` to check whether the optimizer needs a temporary table or sort.
2. Compare a `SELECT *` query against a query selecting only `customer_id` and `total_amount`. Explain the impact of intermediate row width.
3. Check `internal_tmp_mem_storage_engine`, `tmp_table_size`, `temptable_max_ram`, and `temptable_max_mmap` on a test server.
4. Run a workload producing a large grouped result and capture before/after deltas of `Created_tmp%` counters. Explain why `Created_tmp_disk_tables` does not reflect all memory-mapped temp tables.
5. If Performance Schema has TempTable instruments, query `CURRENT_NUMBER_OF_BYTES_USED` and `HIGH_NUMBER_OF_BYTES_USED`.
6. Test `MEMORY` and `TempTable` engines in a dedicated session; compare behavior with long string columns or `TEXT` types on your exact MySQL version.
7. Create an appropriate index for filtering/grouping conditions, re-run `EXPLAIN`, and compare rows read, latency, and resource usage.
8. Write a short runbook for handling `tmpdir` nearing capacity or abnormal growth of the InnoDB temporary tablespace.

## Key Takeaways

- Internal temporary tables are intermediate results created by MySQL; they differ from application-created `TEMPORARY` tables.
- `TempTable` is the default internal engine in modern MySQL 8.0; `MEMORY` has different data type limits and row storage formats.
- Distinguish the per-table limit `tmp_table_size` from the server-wide TempTable budgets `temptable_max_ram` and `temptable_max_mmap`.
- TempTable can transition from RAM to memory-mapped files and then to InnoDB temporary tablespaces; the exact path depends on version and configuration.
- `Using temporary` does not prove disk spill; `Created_tmp_disk_tables` also does not count temporary tables using mmap.
- Monitor Performance Schema, status counters, filesystems, and InnoDB temporary tablespaces together.
- Reduce intermediate data via early filtering, selecting fewer columns, proper indexes, and controlling materialization before increasing memory limits.
