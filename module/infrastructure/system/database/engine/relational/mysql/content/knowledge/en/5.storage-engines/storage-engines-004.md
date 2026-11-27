# MEMORY, data lifecycle, and operational limits

MySQL includes the `MEMORY` storage engine to store data rows directly in server memory. This engine can provide fast lookups for small, temporary, regenerable datasets, such as status code lookup tables or short-lived caches. In exchange, data in a `MEMORY` table does not survive a server restart, the engine does not support transactions like InnoDB, and write operations contend at the table level.

Therefore, choosing `MEMORY` is a decision about data lifecycle and application recovery, not merely a query-acceleration choice. With MySQL, you must clearly understand where data resides, when it disappears, how memory limits apply, and how to handle table-full errors or server restarts.

## 1. What is the MEMORY storage engine?

`MEMORY` is a storage engine that keeps row contents and indexes in the RAM of the MySQL Server process. Its legacy name is `HEAP`; modern syntax should use `ENGINE=MEMORY`.

A table created with `ENGINE=MEMORY` remains a normal MySQL table in terms of naming and access privileges. Sessions granted privileges on the table can access it concurrently. The difference lies in how the engine stores data and which features it supports.

Key characteristics:

- **In-memory data:** reads do not fetch table data pages from data files like a standard InnoDB table. Table indexes also consume memory.
- **Non-persistent:** when MySQL Server stops or restarts, rows in a `MEMORY` table are cleared. The regular table definition typically remains so the application can reload data.
- **No transaction support:** data modifications in `MEMORY` cannot be rolled back by transactions like InnoDB.
- **Table-level locking:** the engine uses table-level locking, so one write operation can block other operations on the same table. It does not provide row-level locking or MVCC like InnoDB.
- **HASH and BTREE indexes:** HASH suits equality lookups; BTREE is better suited for range queries and ordering.
- **Fixed-length row format:** row layout can consume more RAM than expected, especially with string columns declared with large lengths.
- **Unsuitable for certain data types:** `BLOB` and `TEXT` are not supported.

`MEMORY` can offer low latency when the table is small and queries match its indexes. However, there is no guarantee every query on it will be fast: large table scans, lock contention, memory allocation, and host-wide RAM pressure can still degrade performance.

## 2. Checking MEMORY support

Before creating a table, verify whether the engine is enabled on the server:

```sql
SHOW ENGINES;
```

In the results, check the `Engine` column for `MEMORY` and the `Support` column indicating whether it is supported. Common values include `YES`, `DEFAULT`, `NO`, or `DISABLED`, depending on configuration state and version.

You can also inspect `INFORMATION_SCHEMA.ENGINES`:

```sql
SELECT ENGINE, SUPPORT, TRANSACTIONS, XA, SAVEPOINTS
FROM INFORMATION_SCHEMA.ENGINES
WHERE ENGINE = 'MEMORY';
```

The `TRANSACTIONS`, `XA`, and `SAVEPOINTS` columns indicate whether the engine supports those respective transaction capabilities. Do not infer features solely from the engine name or from a `CREATE TABLE` statement succeeding.

## 3. Creating and using MEMORY tables

### 3.1. Creating a small lookup table

Suppose an application frequently looks up display names for order statuses. This catalog is small, rarely changes, and can be reloaded from a persistent table:

```sql
CREATE TABLE order_status_cache (
    status_code VARCHAR(20) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (status_code),
    KEY idx_sort_order (sort_order) USING BTREE
) ENGINE=MEMORY;
```

The primary key is used for lookups by `status_code`. With `MEMORY`, HASH is the default index type if no other type is specified; a BTREE index is explicitly declared on `sort_order` to support range queries or sorting on this column.

Load some sample rows:

```sql
INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
VALUES
    ('NEW', 'Newly created', 1),
    ('PAID', 'Paid', 2),
    ('SHIPPED', 'Shipping', 3),
    ('CANCELLED', 'Cancelled', 4);
```

Lookup by key:

```sql
SELECT display_name
FROM order_status_cache
WHERE status_code = 'PAID';
```

Lookup by order:

```sql
SELECT status_code, display_name
FROM order_status_cache
WHERE sort_order >= 2
ORDER BY sort_order;
```

For small tables, simple queries may not need many indexes. Each additional index consumes extra RAM and adds work to write operations. Create indexes based on actual query patterns.

### 3.2. Reloading data from a persistent source

A safer pattern is keeping the canonical data in an InnoDB table, then populating a lookup copy in `MEMORY` at application startup or when the catalog changes:

```sql
CREATE TABLE order_status (
    status_code VARCHAR(20) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (status_code)
) ENGINE=InnoDB;

INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
SELECT status_code, display_name, sort_order
FROM order_status;
```

This example assumes both tables already exist and the source catalog contains data. During a reload procedure, old cache data can be cleared first and then reloaded:

```sql
TRUNCATE TABLE order_status_cache;

INSERT INTO order_status_cache
    (status_code, display_name, sort_order)
SELECT status_code, display_name, sort_order
FROM order_status;
```

Because `MEMORY` lacks transactions, `TRUNCATE` and `INSERT` do not form an atomic rollbackable operation. During the reload, other sessions may see an empty table or partially loaded new data. If the application requires the cache to remain populated at all times, consider loading into a new cache table and swapping table names via a tested procedure, or using InnoDB for caches requiring atomic updates.

### 3.3. Regular tables vs. TEMPORARY tables

These two declarations have different lifecycles:

```sql
CREATE TABLE shared_lookup (
    code VARCHAR(20) PRIMARY KEY
) ENGINE=MEMORY;

CREATE TEMPORARY TABLE session_lookup (
    code VARCHAR(20) PRIMARY KEY
) ENGINE=MEMORY;
```

- `shared_lookup` is a regular table. Authorized sessions can see it concurrently; the table definition persists across server restarts, though its rows are lost.
- `session_lookup` is a temporary table scoped to the session that created it. Other sessions cannot see it; the table is dropped when the session ends. Its data also resides in RAM and is non-persistent.

Do not confuse application-created `TEMPORARY` tables with internal temporary tables that MySQL creates automatically during query execution. Internal temporary tables have their own configuration and engines; in modern MySQL versions, the default internal engine is not necessarily `MEMORY`.

## 4. MEMORY data lifecycle

### 4.1. What happens when the server restarts?

For a regular `MEMORY` table:

1. The table is created and the application writes rows into RAM.
2. Sessions query or update the table while the server is running.
3. When MySQL Server stops or restarts, row data in the `MEMORY` table is lost.
4. Once the server is running again, the regular table definition remains visible, but the table no longer contains the old rows.
5. The application must reload data from a persistent source or tolerate an empty cache until warmed.

For example, after a restart:

```sql
SELECT COUNT(*) AS cached_rows
FROM order_status_cache;
```

The result may be `0` even if the table held many rows before the server stopped. This is the engine's designed behavior, not a data recovery bug.

### 4.2. What happens on a crash or power loss?

When the MySQL process crashes or the host loses power, data in RAM is also gone. `MEMORY` provides no redo/undo logs or crash recovery mechanism to restore written rows. Therefore, never use it as the sole source of truth for orders, payments, balances, inventory, or any information the business requires after a failure.

Regular table definitions are managed by MySQL and may persist after a server restart. This differs from durable row storage: seeing the table in `SHOW TABLES` does not mean its rows were recovered.

### 4.3. Lifecycle of TEMPORARY tables

A `TEMPORARY` table is dropped when the session that created it ends, even without a server restart. If an application uses a connection pool, a session may live longer than a single request; the temporary table may remain when the connection returns to the pool. Proactively run `DROP TEMPORARY TABLE` or manage table names and connection lifecycles to prevent leftover data across pooled borrows.

Do not use session temporary tables to pass state between two different connections. Each session has its own namespace and lifecycle.

## 5. Memory limits and table-full errors

### 5.1. max_heap_table_size

The maximum size of a `MEMORY` table is controlled by the `max_heap_table_size` system variable. This is a per-table limit, not the total RAM budget for the entire MySQL Server.

Check the configuration:

```sql
SHOW VARIABLES LIKE 'max_heap_table_size';
```

You can set a session limit before creating a table in that session:

```sql
SET SESSION max_heap_table_size = 64 * 1024 * 1024;

CREATE TABLE request_cache (
    request_id BINARY(16) NOT NULL,
    status_code SMALLINT NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (request_id)
) ENGINE=MEMORY;
```

This example sets a 64 MiB limit for tables created in this session, if configuration and privileges permit. Changing the variable does not automatically expand existing `MEMORY` tables; applying a new limit to an existing table requires an appropriate alter/rebuild procedure and impact assessment.

Administrators can also set a GLOBAL value for new sessions. Do not increase this limit arbitrarily: if many `MEMORY` tables exist, their combined RAM consumption can grow very large even if no single table exceeds its individual limit.

### 5.2. When a table reaches its limit

When a table needs memory beyond its allowed limit, write operations can fail with:

```text
ERROR 1114 (HY000): The table 'request_cache' is full
```

This does not necessarily mean all physical RAM is exhausted. The table may have hit `max_heap_table_size` before the host ran out of RAM. Conversely, raising `max_heap_table_size` while the OS is already short on memory can make matters worse.

When encountering error 1114:

1. Identify which table is full and check its engine with `SHOW CREATE TABLE`.
2. Measure row count, row size, and indexes; remember that indexes also consume RAM.
3. Check `max_heap_table_size` at the proper session/global scope.
4. Determine which data genuinely needs to stay in cache and for how long.
5. Purge or refresh expired data according to business rules, or move large datasets to InnoDB.
6. Only increase the limit after calculating the total RAM budget and monitoring server impact.

Do not resolve a table-full error by deleting random rows if the application still needs them. Define an eviction policy, TTL, or data partitioning strategy before deployment.

### 5.3. Do not confuse max_heap_table_size with tmp_table_size

`max_heap_table_size` limits user-created `MEMORY` tables. `tmp_table_size` and variables related to internal temporary tables govern part of the behavior of internal temporary tables created by MySQL during query execution. These are two distinct scenarios.

In MySQL 8.0, the internal `TempTable` engine is used for many in-memory internal temporary tables under default configuration. Internal tables may spill to alternate storage when exceeding thresholds or under version-specific conditions. Do not assume every `GROUP BY`, `ORDER BY`, or temporary table in an execution plan uses the `MEMORY` storage engine.

## 6. Designing rows and indexes without wasting RAM

### 6.1. Fixed-length rows

`MEMORY` uses a fixed-length row format. This keeps row access simple, but can waste memory if string columns are declared wide while actual values are usually short.

For example, if a table only needs to store short codes but declares several `VARCHAR(1000)` columns, row size can be dominated by the declared lengths. Choose tight types and lengths, and avoid putting long descriptive columns into `MEMORY` tables.

The engine does not support `BLOB` and `TEXT`. If data requires large payloads or highly variable lengths, use InnoDB or more appropriate storage.

### 6.2. Choosing HASH or BTREE

MEMORY supports two common index types:

| Index type | Best suited for | Limitations |
|---|---|---|
| HASH | Exact equality comparisons across the full key, e.g., `WHERE code = 'PAID'` | Does not support range lookups and does not provide key ordering for `ORDER BY` |
| BTREE | Equality comparisons, range comparisons, matching key prefixes, and ordered scans | Incurs index structure overhead; measure benefit against real query patterns |

If queries mainly look up a single exact code, HASH is a natural choice. If you need `WHERE expires_at < NOW()` or `ORDER BY created_at`, consider BTREE. You can declare BTREE explicitly in DDL:

```sql
CREATE TABLE short_lived_jobs (
    job_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    state_code SMALLINT NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_expires_at (expires_at) USING BTREE
) ENGINE=MEMORY;
```

A HASH index cannot substitute for BTREE on range queries. Conversely, creating unnecessary indexes increases RAM consumption and update overhead. Verify with `EXPLAIN` and measure on realistically sized data.

## 7. Transaction and concurrency limits

### 7.1. MEMORY has no transaction rollback

`MEMORY` does not support transactions. Changes to the table are not protected by `COMMIT`/`ROLLBACK` like changes in InnoDB.

Example:

```sql
CREATE TABLE memory_flags (
    flag_name VARCHAR(40) PRIMARY KEY,
    flag_value VARCHAR(40) NOT NULL
) ENGINE=MEMORY;

START TRANSACTION;

INSERT INTO memory_flags (flag_name, flag_value)
VALUES ('maintenance_mode', 'on');

ROLLBACK;

SELECT * FROM memory_flags;
```

The row inserted into `memory_flags` may still exist after `ROLLBACK`, because the engine's write does not participate in the transaction. If the same transaction also modifies an InnoDB table, the InnoDB change can roll back while the MEMORY change remains. This is a source of inconsistent state if two engines are mixed in one workflow.

Do not use a `MEMORY` table to store partial state that must commit or roll back atomically alongside InnoDB data. When atomicity is required, use InnoDB for all data belonging to the same business unit.

### 7.2. Table-level locking

Because it uses table-level locking, a write operation can force other operations on the same table to wait. When multiple sessions write to a `MEMORY` table concurrently, concurrency may be lower than expected even though the data sits in RAM.

For example, a shared cache table that gets fully refreshed every few seconds can force read queries to wait for write locks. For multi-user workloads with frequent concurrent updates, InnoDB with row-level locking is generally more suitable.

Monitor wait times, update frequency, and concurrent query counts. If frequent cache updates are needed, consider smaller batches, lower refresh frequency, sensible data partitioning, or an engine with suitable concurrency capabilities.

### 7.3. No foreign key support like InnoDB

Do not use `MEMORY` to enforce referential relationships between tables. The engine does not provide foreign key checks like InnoDB. If data needs parent-child enforcement, referential integrity, and transactions, store the canonical source in InnoDB and build only an appropriate lookup/cache copy in MEMORY.

## 8. Suitable use cases and cases to avoid

### 8.1. Suitable use cases

- **Small lookup tables:** status codes, type codes, or rarely changing configuration reloadable from canonical tables.
- **Temporary caches:** data regenerable from a persistent source with a clear expiration policy.
- **Small staging tables:** intermediate data needed only during processing and reloadable if the server restarts.
- **Read-mostly reference datasets:** infrequently updated, predictable in size, and heavily queried by key.

Even in these cases, provide a fallback when the cache is empty or lost. The canonical source must reside in durable storage if the business requires recovery.

### 8.2. Cases to avoid

- Transactional data, orders, payments, balances, or inventory that must survive restarts.
- Data requiring transactions, rollback, MVCC, or row-level locking.
- Large or unpredictably growing tables risking RAM budget exhaustion.
- Tables containing `BLOB`, `TEXT`, or long string payloads.
- Workloads with many concurrent writer sessions needing high write throughput.
- Data requiring foreign keys or engine-enforced referential integrity.
- Sensitive cached data where exposure in memory, core dumps, or swap is unacceptable.

## 9. Restarts, replication, and cache-warming strategies

### 9.1. Rebuilding cache after a restart

Applications using MEMORY must treat the cache as volatile data that can vanish. A startup workflow should include these steps:

1. Connect to MySQL and confirm the schema/table exists.
2. Load data from InnoDB or another durable source.
3. Verify row counts, checksums, or key invariants.
4. Mark the cache as ready only after loading succeeds.
5. If loading fails, fall back to the canonical source or keep cache-dependent features in an unready state.

Never let the application silently treat an empty cache as empty business data. For instance, an empty status code table after a restart does not mean the system has no order statuses.

### 9.2. Handling multiple servers and replication

Replication can propagate DML operations on MEMORY tables from source to replica, but that does not make in-memory data durable. If a server restarts, MEMORY rows on that server are lost. When source and replica restart at different times, table contents can diverge until reloaded or synchronized via a dedicated procedure.

Therefore, do not rely on MEMORY to hold state that must remain consistent across nodes. If using it as a per-node cache, provide an independent rebuild mechanism, clearly designate the canonical source node, and monitor cache readiness per node.

### 9.3. Cache misses and expired data

The application should define behavior when a row is not found:

- Read from the durable source and optionally repopulate the cache.
- Return a default result if business rules permit.
- Emit cache miss metrics and refresh timings to detect an empty or failing cache.

If using an expiration column like `expires_at`, establish a cleanup process for expired rows. With a BTREE index on the timestamp column, rows needing cleanup can be located:

```sql
DELETE FROM short_lived_jobs
WHERE expires_at < NOW();
```

This is a write operation on a MEMORY table and is still subject to table-level locking. Running cleanup too frequently or deleting too many rows at once can impact other queries. Measure and choose appropriate batch sizes and intervals.

## 10. Observing and managing MEMORY in operations

### 10.1. Inspecting engine, size, and row counts

Check the definition:

```sql
SHOW CREATE TABLE order_status_cache;
```

Inspect table status:

```sql
SHOW TABLE STATUS LIKE 'order_status_cache'\G
```

Or query metadata:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM INFORMATION_SCHEMA.TABLES
WHERE ENGINE = 'MEMORY'
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC;
```

Size and row count values in metadata may be estimates or reflect engine state in implementation-specific ways; combine them with process and OS RAM metrics. Do not sum a single metadata column and treat it as MySQL's total memory usage.

### 10.2. Monitoring the RAM budget

A server may host multiple MEMORY tables created by various schemas or applications. Each table has its own cap, yet total consumption adds up. Beyond MEMORY data and indexes, MySQL also needs RAM for the InnoDB buffer pool, connections, sort/join buffers, internal temporary tables, Performance Schema, and other structures.

Administrators should:

- Inventory `ENGINE=MEMORY` tables and their application owners.
- Estimate maximum row counts, row sizes, and index sizes.
- Set `max_heap_table_size` deliberately, not merely based on currently free RAM.
- Monitor the MySQL process RSS, OS memory, swap, and memory pressure metrics.
- Configure alerts when row counts or memory usage approach limits.
- Drop unused tables and define TTL/eviction for growing caches.

### 10.3. Procedures on server restart

After a restart, verify MEMORY tables have been reloaded before opening business traffic. A quick check:

```sql
SELECT COUNT(*) FROM order_status_cache;
SELECT COUNT(*) FROM short_lived_jobs;
```

Do not only check that the table exists. Verify that data is complete, the cache version matches the canonical source, and the application can safely serve requests.

## 11. Comparing MEMORY with InnoDB

| Criterion | MEMORY | InnoDB |
|---|---|---|
| Row data storage | RAM | Data pages on storage, hot pages cached in buffer pool |
| Survives restart | No; rows are lost | Yes, via redo/undo and recovery mechanisms |
| Transactions/rollback | Not supported | Yes |
| Locking | Table-level locking | Primarily row-level locking with other lock types |
| MVCC | No | Yes |
| Foreign keys | Not supported like InnoDB | Yes |
| Indexes | HASH by default; BTREE supported | BTREE for common indexes and additional features |
| Large data types | Does not support BLOB/TEXT | Supported |
| Best suited for | Small, regenerable caches/reference tables | Business data and workloads needing durability and transactions |

Do not choose MEMORY solely because data sits in RAM. InnoDB also keeps hot data in its buffer pool while providing transactions, crash recovery, and better concurrency for most business workloads. If an InnoDB query is slow, first inspect indexes, execution plans, rows read, and buffer pool configuration before rushing to move the table to MEMORY.

## 12. Checklist before choosing MEMORY

- Can the data be completely lost after a restart or crash without business data loss?
- Is there a durable source to reload the data from?
- Does the application handle cache misses and cache-unavailable windows?
- Are row size, row count, and index footprint predictable?
- Does the combined RAM of all MEMORY tables fit within the server budget?
- Do query patterns need HASH or BTREE? Are range queries or sorting required?
- Is write load low enough to tolerate table-level locking?
- Does the business workflow require transactions, rollback, MVCC, or foreign keys?
- Is cross-node cache synchronization and replication/restart handling required?
- Are metrics, alerts, and post-restart cache-warming procedures in place?

## Conclusion

`MEMORY` is suited for small, temporary, regenerable datasets. Rows and indexes reside in RAM, yet are lost when MySQL Server restarts or crashes; regular tables retain their definitions for reloading. The `max_heap_table_size` limit, fixed-length rows, HASH/BTREE indexes, and table-level locking shape both design and operability. Keep canonical data in a durable engine like InnoDB, establish cache-warming workflows, track your memory budget, and choose MEMORY only when the application explicitly accounts for data lifecycle and engine limits.
