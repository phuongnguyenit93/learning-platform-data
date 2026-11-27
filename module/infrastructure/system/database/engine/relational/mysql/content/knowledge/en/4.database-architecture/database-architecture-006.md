# Data Dictionary, Metadata Caches, and Table Definition Cache

MySQL must know the database structure before it can parse and execute a SQL statement. Upon receiving a query such as `SELECT order_id, total FROM sales.orders`, the server needs to resolve the `sales` schema, the `orders` table, columns, data types, indexes, access privileges, and the storage engine. Information describing these objects is **metadata**.

Reading metadata from storage repeatedly for every statement would be slow. Therefore, MySQL organizes metadata into a data dictionary and holds frequently used objects across multiple layers of memory caches. Understanding each layer accurately helps investigate slow table opens, systems with large numbers of tables, high concurrency, or stalled DDL.

This lesson frames the material within `DATABASE_MYSQL`: mastering table design, data types, keys, queries, indexes, transactions, concurrency control, and operations. The data dictionary and related caches are part of server architecture, influencing how MySQL resolves object names, opens tables, and handles DDL.

## 1. What Are Metadata and the Data Dictionary?

**Metadata** is data describing data. For MySQL, metadata describes the objects and attributes the server needs to understand and manage a database, such as:

- Schemas and tables.
- Columns, data types, default values, NULLability, and column order.
- Primary keys, unique keys, foreign keys, and indexes.
- Views and view definitions.
- Stored procedures, functions, triggers, and events.
- Tablespaces, partitions, and storage attributes.
- Information needed to check privileges and execute statements on objects.

Metadata differs from business data stored in table rows. For example, in the `sales.orders` table, the rows containing orders are business data; the `order_id BIGINT PRIMARY KEY` definition, the type of `total`, indexes, and engine are metadata.

The **data dictionary** is the component that centrally manages metadata for database objects. It enables the server to look up object definitions consistently rather than relying on fragmented metadata sources.

The high-level flow can be visualized as follows:

~~~text
SQL statement
    |
    v
Syntax parsing and object name resolution
    |
    v
Metadata / data dictionary lookup
    |
    +--> Metadata objects already in cache
    |
    +--> Read metadata from data dictionary when needed
    |
    v
Privilege check, prepare table object, and execute
    |
    v
Storage engine processes data
~~~

This is a conceptual diagram. Dictionary lookups, caching, and table opening involve additional internal steps that can vary by statement type and MySQL version.

## 2. Data Dictionary in MySQL 8.0 and Later

### 2.1. Transactional Data Dictionary

Starting in MySQL 8.0, MySQL uses a transactional data dictionary. Metadata is stored centrally in server-managed dictionary tables backed by InnoDB. This storage provides key benefits:

- Metadata is managed centrally and consistently.
- Dictionary changes are transactional and crash-recoverable.
- Certain DDL operations support atomic DDL, allowing metadata changes and associated storage operations to recover as a single unit within supported scope.
- Metadata caching mechanisms are organized more coherently.
- Many metadata queries through `INFORMATION_SCHEMA` can use the dictionary instead of scanning scattered definition files.

In older MySQL versions, table metadata was stored in `.frm` files and several other sources. When upgrading to MySQL 8.0, do not continue assuming `.frm` files are the source of table definitions. Use supported SQL interfaces to inspect metadata.

### 2.2. Dictionary Tables Are Not Ordinary Application Tables

MySQL uses internal tables to store the data dictionary, but dictionary tables are protected and cannot be queried or modified directly in standard builds. To read metadata, use supported interfaces:

- `SHOW` commands, such as `SHOW CREATE TABLE`, `SHOW COLUMNS`, `SHOW INDEX`.
- Views and tables in `INFORMATION_SCHEMA`.
- Monitoring tables in `performance_schema`.
- Convenience views in the `sys` schema.

Do not modify dictionary tables directly or tamper with internal data files to alter table definitions. Doing so can desynchronize metadata from storage engine state, potentially rendering the instance inoperable.

It is also important to distinguish **data dictionary tables** from **system tables** in the `mysql` schema. Dictionary tables store core metadata the server needs to execute statements; system tables store supporting data such as accounts, privileges, time zones, and other system information. Both are managed by MySQL, but they serve different roles and follow different upgrade procedures.

### 2.3. Atomic DDL Does Not Mean All DDL Can Be Rolled Back

The transactional data dictionary enables MySQL to support atomic DDL for supported operations and storage engines. This means the server can recover a DDL operation consistently if an error or crash occurs.

However, atomic DDL does not mean you can place any `CREATE`, `ALTER`, or `DROP` statement inside a user transaction and undo it with `ROLLBACK`. Many DDL statements still cause an implicit commit. Atomic DDL is a server-level atomicity guarantee for supported DDL operations, not a replacement for application SQL transaction rules.

## 3. Metadata Cache Layers to Distinguish

The phrase "metadata cache" is often used as a catch-all term. In MySQL, there are multiple caches related to metadata, and they are not a single structure.

| Component | Primary contents | Configuration/observability |
|---|---|---|
| Dictionary Object Cache | Accessed data dictionary objects held in shared memory | Dictionary partitions; some limits have dedicated configuration variables |
| Table definition cache | Table definitions cached by the server to reduce open/lookup definition cost | `table_definition_cache`, `Open_table_definitions`, `Opened_table_definitions` |
| Table open cache | Open table instances serving concurrent access across sessions | `table_open_cache`, `table_open_cache_instances`, `Open_tables`, `Opened_tables` |
| INFORMATION_SCHEMA statistics cache | Certain table and index statistics cached to speed up metadata queries | `information_schema_stats_expiry`, `ANALYZE TABLE` |
| Metadata lock (MDL) | Lock coordinating metadata access across sessions | `performance_schema.metadata_locks` |

The first four caches involve retaining or reusing information/objects in memory. Metadata locks are a synchronization and consistency-protection mechanism, **not a cache**.

### 3.1. Dictionary Object Cache

The Dictionary Object Cache is a global shared cache storing accessed data dictionary objects for reuse and reduced I/O. The cache uses an LRU (Least Recently Used) eviction strategy: when space is needed, the least recently used objects are evicted first.

In MySQL 8.4, the Dictionary Object Cache is partitioned by object type. Some partitions have configuration variables, while others have internal limits. For example:

- Tablespace definition cache partition: bounded by `tablespace_definition_cache`.
- Schema definition cache partition: bounded by `schema_definition_cache`.
- Table definition cache partition inside the Dictionary Object Cache: object limit tied to `max_connections`.
- Stored program definition cache partition: related to `stored_program_definition_cache`.
- Character set and collation definition cache partition: governed by internal limits.

Common point of confusion: the table definition cache partition inside the Dictionary Object Cache **coexists** with the table definition cache controlled by `table_definition_cache`. Both caches store table definitions, yet serve different parts of the server; an object's presence in one cache does not depend on its presence in the other.

Do not lump all of the layers above into a single "metadata cache size" figure. When analyzing memory or changing settings, know which variable governs which partition.

## 4. Table Definition Cache

### 4.1. Role

The table definition cache holds table definitions so the server can reuse them when opening or accessing tables. These definitions contain structural information such as columns, data types, and table-related attributes.

When an application frequently accesses a large set of tables, a sufficiently sized definition cache reduces reloads from the data dictionary. This cache typically uses less memory than the table open cache and does not consume file descriptors in the way the open tables cache does.

The primary configuration variable is:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

In MySQL 8.4, this variable has `GLOBAL` scope, is dynamic, has a minimum value of 400, and a default value of `-1` indicating automatic sizing. The default formula documented in MySQL 8.4 is:

~~~text
MIN(400 + table_open_cache / 2, 2000)
~~~

Do not apply this default blindly to every MySQL version. Read the actual value on your instance and consult documentation for the exact version.

### 4.2. Interaction with InnoDB

For InnoDB, `table_definition_cache` also acts as a soft limit on the number of table instances in the Dictionary Object Cache and the number of file-per-table tablespaces that can be open simultaneously. When the limit is exceeded, MySQL marks eligible objects for LRU eviction and closes inactive tablespaces only when conditions permit.

This is why `table_definition_cache` should not be interpreted simply as "the number of `.frm` files kept in RAM." Since MySQL 8.0, the data dictionary no longer relies on `.frm` files under the legacy model; this variable affects the definition cache and certain InnoDB-related limits.

### 4.3. Observing the Definition Cache

Two useful status variables:

- `Open_table_definitions`: number of table definitions currently cached.
- `Opened_table_definitions`: number of table definitions cached since server startup or counter reset under the corresponding mechanism.

Quick check:

~~~sql
SHOW GLOBAL STATUS LIKE 'Open_table_definitions';
SHOW GLOBAL STATUS LIKE 'Opened_table_definitions';
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

Read these values over time alongside the workload. Do not increase the cache solely because `Opened_table_definitions` is large: it is a cumulative counter and by itself does not prove the cache is undersized. Examine table count, table reuse patterns, memory pressure, and other metrics.

## 5. Table Open Cache

### 5.1. Role

The table open cache holds open table instances so threads can reuse them, reducing the overhead of repeatedly opening tables. A single table accessed concurrently by multiple sessions may require multiple table instances because sessions maintain separate working state.

The `table_open_cache` variable specifies the number of open-table entries across all threads. It is neither the number of tables in the database nor the number of tables a single session may access.

For example: an application has 300 active sessions whose queries typically join 4 to 6 tables. The number of table instances needed can be much larger than the number of tables referenced by any single query. Cache sizing must be evaluated against concurrency, query patterns, and file descriptor limits.

### 5.2. Configuration and Limits

Inspect related variables:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'max_connections',
    'open_files_limit'
);
~~~

In MySQL 8.4, the documentation lists typical default values:

| Variable | MySQL 8.4 Default | Meaning |
|---|---:|---|
| `table_open_cache` | 4000 | Number of table open cache entries for all threads |
| `table_open_cache_instances` | 16 | Number of partitioned cache instances |
| `table_definition_cache` | -1 (auto-sized) | Number of table definitions stored in the configured cache |

These are reference defaults for MySQL 8.4, not universal recommendations for every server. Cloud services, other distributions, or custom configuration files may set different values.

Increasing `table_open_cache` increases the number of file descriptors `mysqld` requires. The effective capacity is also constrained by `open_files_limit` and `max_connections`. Setting it too high relative to OS limits can cause file-open errors, connection refusals, or failed queries.

### 5.3. Table Open Cache Instances

`table_open_cache_instances` splits the table open cache into multiple smaller caches to reduce contention when many sessions access the cache simultaneously. A session can lock a single cache instance during DML operations instead of contending on one large global cache.

In MySQL 8.4, the default is 16 and this variable is not dynamic. DDL still needs to lock the entire cache, though DDL typically occurs far less often than DML. Increasing the instance count does not automatically improve performance; more cache instances can also increase memory usage in some workloads.

## 6. Distinguishing Table Definition Cache and Table Open Cache

These two concepts are frequently confused:

| Criterion | Table definition cache | Table open cache |
|---|---|---|
| Configuration variable | `table_definition_cache` | `table_open_cache` |
| What it holds | Table definitions/metadata | Open table instances for session use |
| Goal | Reduce cost of reloading table definitions | Reduce open/close table operations and support concurrency |
| File descriptors | Does not consume file descriptors the way table open cache does | Affects the number of required file descriptors |
| Observability metrics | `Open_table_definitions`, `Opened_table_definitions` | `Open_tables`, `Opened_tables`, `Table_open_cache_*` |
| Common symptoms | Many tables, definitions reloaded frequently | Open table cache too small, file descriptors, or concurrency pressure |

Examples:

- If a server has tens of thousands of tables yet only a small fraction is accessed at any given time, the table definition cache may need to be large enough to reuse metadata.
- If a server has many sessions concurrently opening tables and frequently joining multiple tables, the table open cache may need tuning to avoid constant table open/close churn.
- If the host is running out of file descriptors, raising `table_open_cache` can make matters worse even though the original goal was reducing table opens.

Because the two caches serve different purposes, do not blindly raise both at once. Measure and identify which layer is incurring the cost.

## 7. INFORMATION_SCHEMA Statistics Cache

Another cache layer easily confused with the data dictionary is the table and index statistics cache queried through `INFORMATION_SCHEMA`.

In MySQL 8.4, certain statistics in `INFORMATION_SCHEMA.TABLES` and `INFORMATION_SCHEMA.STATISTICS` are cached. The `information_schema_stats_expiry` variable controls how long cached statistics remain valid before expiring; the MySQL 8.4 default is 86400 seconds (24 hours).

Check it:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'information_schema_stats_expiry';
~~~

When fresh statistics are needed from the storage engine, you can run:

~~~sql
ANALYZE TABLE sales.orders;
~~~

Or set `information_schema_stats_expiry = 0` for a session that needs to read fresh statistics directly from the storage engine:

~~~sql
SET SESSION information_schema_stats_expiry = 0;
~~~

In exchange, metadata queries may run slower because cached statistics are bypassed. Use this only when you specifically need the latest numbers; do not default to 0 for all sessions.

Keep in mind: the statistics cache is not the table definition cache. If `TABLE_ROWS` or cardinality looks stale, that does not mean the data dictionary or table definition cache is broken.

## 8. Reading Metadata Through SQL Interfaces

The data dictionary can be queried through supported interfaces. The following queries are helpful when inspecting schemas and verifying table definitions.

### 8.1. Listing Tables in a Schema

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    CREATE_OPTIONS
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

For InnoDB, `TABLE_ROWS` is typically an estimate, not an exact row count. If you need an exact count, run `SELECT COUNT(*)` on the table while considering the data-reading cost.

### 8.2. Reading Column Definitions

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

This query shows column order, data types, NULLability, defaults, and extra attributes such as auto increment.

### 8.3. Reading Indexes

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

`CARDINALITY` is an estimated statistic of distinct values in the index; do not treat it as an exact absolute number. When statistics need updating, evaluate `ANALYZE TABLE` and the statistics cache expiry window.

### 8.4. Viewing the Full Definition

~~~sql
SHOW CREATE TABLE sales.orders\G
~~~

This command is usually the fastest way to view a table's complete DDL, including columns, indexes, constraints, engine, charset, and related options.

### 8.5. Listing Databases and Schemas

~~~sql
SELECT SCHEMA_NAME
FROM information_schema.schemata
ORDER BY SCHEMA_NAME;
~~~

The queries above show only objects that the current account is permitted to see based on privileges and server policies.

## 9. Metadata Locking: A Lock, Not a Cache

Metadata locking (MDL) coordinates concurrent access to objects such as tables, schemas, stored procedures, functions, triggers, events, and tablespaces. Its goal is to ensure a statement does not rely on an object's definition while another operation is modifying that definition in a conflicting way.

For example:

1. Session A starts a transaction and reads the `sales.orders` table.
2. Session A's transaction remains open, holding the appropriate metadata lock on the object.
3. Session B runs `ALTER TABLE sales.orders ...` and must wait for a compatible metadata lock.
4. If Session A's transaction does not finish, Session B's DDL can wait for a long time.
5. Other subsequent queries may be impacted by the lock queue waiting behind the DDL.

MDL differs from InnoDB row locks:

- Row locks protect data records within transactions.
- Metadata locks protect an object's definition and metadata state.
- Caches retain information/objects in memory for reuse.

Increasing `table_definition_cache` or `table_open_cache` will not resolve a transaction holding a metadata lock for too long.

### 9.1. Checking Waiting Metadata Locks

Performance Schema provides the `performance_schema.metadata_locks` table. You can filter waiting lock requests:

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING'
ORDER BY OBJECT_SCHEMA, OBJECT_NAME;
~~~

Results may be empty if no locks are waiting at query time. To identify the involved sessions, join `OWNER_THREAD_ID` with `performance_schema.threads`:

~~~sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    t.PROCESSLIST_ID,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    t.PROCESSLIST_TIME,
    t.PROCESSLIST_STATE,
    t.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
    ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
ORDER BY ml.OBJECT_SCHEMA, ml.OBJECT_NAME, ml.LOCK_STATUS;
~~~

Appropriate Performance Schema read privileges are required. The output is a snapshot at query time; lock states can change immediately afterward.

### 9.2. Handling Stalled DDL

When `ALTER TABLE` or `DROP TABLE` is waiting on a metadata lock:

1. Identify the object and waiting session in `metadata_locks`.
2. Find the session holding the lock and check whether its transaction is still open.
3. Inspect the statement and elapsed time in the process list or Performance Schema.
4. Determine whether the transaction can commit/roll back per business logic.
5. If a session must be terminated, evaluate impact before running `KILL`.
6. Schedule DDL during an appropriate window and control wait times using suitable configuration/migration strategies.

Do not automatically kill every long-running session. A transaction may be performing valid work; identify the owner and impact before intervening.

## 10. Monitoring Caches and Evaluating Whether Tuning Is Needed

### 10.1. Capturing a Configuration Snapshot

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_definition_cache',
    'table_open_cache',
    'table_open_cache_instances',
    'max_connections',
    'open_files_limit',
    'information_schema_stats_expiry'
);
~~~

Record the output alongside timestamp, server version, and workload type. On managed database services, some variables may not be modifiable or must be configured via parameter groups.

### 10.2. Capturing a Status Snapshot

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files'
);
~~~

Meaning:

| Metric | How to read |
|---|---|
| `Open_table_definitions` | Number of table definitions currently cached |
| `Opened_table_definitions` | Number of times the server opened/loaded table definitions per the counter |
| `Open_tables` | Number of tables currently open |
| `Opened_tables` | Number of table open operations since server startup or counter reset |
| `Table_open_cache_hits` | Number of lookups found in the table open cache |
| `Table_open_cache_misses` | Number of lookups not found in the table open cache |
| `Table_open_cache_overflows` | Number of cache instance overflows per the server's definition |
| `Open_files` | Number of open files tracked by the server |

### 10.3. Reading Metrics Over Time Intervals

A single snapshot is rarely sufficient to conclude a cache is undersized. Take two or more snapshots while a representative workload runs and compare the growth:

- Rapidly rising `Opened_tables` when the application is not frequently running `FLUSH TABLES` may indicate `table_open_cache` is too small.
- Rising `Table_open_cache_misses` and `Table_open_cache_overflows` during peak hours should be reviewed alongside `hits`, concurrent session count, and accessed table count.
- `Open_files` approaching the file descriptor limit is a warning to exercise caution before increasing `table_open_cache`.
- Rapidly rising `Opened_table_definitions` should be examined alongside `Open_table_definitions`, table count, and workload; do not use a single cumulative counter to conclude the definition cache is undersized.

To calculate the miss rate for a sampling interval, use the delta between two measurements:

~~~text
miss_rate = delta(Table_open_cache_misses)
            / (delta(Table_open_cache_hits)
               + delta(Table_open_cache_misses))
~~~

This ratio is meaningful only when the denominator is greater than 0 and the counters are captured over the same interval. A high miss rate is a signal to investigate, not standalone proof that a cache must be enlarged. A workload touching millions of distinct tables may exhibit a high miss rate that cannot necessarily be solved simply by allocating more memory.

### 10.4. Controlled Tuning Workflow

1. Record MySQL version, cache configuration, table count, `max_connections`, and `open_files_limit`.
2. Capture a baseline under realistic workload: cache hits/misses, open tables, table opens, and query latency.
3. Determine whether the issue involves the table definition cache, table open cache, file descriptors, or metadata locks.
4. Change one parameter at a time in a test environment or via production configuration change procedures.
5. Re-measure under the same workload and duration.
6. Compare latency, throughput, memory, file descriptors, and cache metrics.
7. Keep the change if measurable benefit is observed and resources stay within limits; otherwise, revert to the previous configuration.

Do not grow caches indefinitely. Large caches consume resources and can starve the server of file descriptors or memory needed by higher-priority workloads.

## 11. Investigation Example: Server with Many Tables and Continuous Table Opens

Suppose a multi-tenant system has 12,000 tables, with each tenant owning separate tables. During peak hours, many sessions run queries across different tenants. Server latency rises and the `Opened_tables` counter increases rapidly.

Do not immediately raise both `table_definition_cache` and `table_open_cache`. Proceed in order:

**Step 1: Check Configuration**

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_definition_cache',
    'table_open_cache',
    'table_open_cache_instances',
    'max_connections',
    'open_files_limit'
);
~~~

**Step 2: Capture Cache Metrics**

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files'
);
~~~

**Step 3: Classify Symptoms**

- If `Opened_tables` climbs rapidly and the table open cache frequently misses/overflows, inspect `table_open_cache` and file descriptor limits.
- If many tables are accessed in rotation and definitions must be reloaded, examine `table_definition_cache` and active table count.
- If DDL statements wait, inspect metadata locks and the transactions holding locks.
- If metadata queries are slow due to statistics, inspect `information_schema_stats_expiry` and `ANALYZE TABLE` timing.

**Step 4: Test Controlled Changes**

Adjust the appropriate parameter in a test environment, run the same query suite, record metrics, and compare. When deploying, verify OS limits or managed database limits. Some platforms manage parameters automatically or cap maximum values.

**Step 5: Verify After Changes**

Re-check latency, throughput, cache counters, memory, and open files. If cache metrics improve yet latency does not, the bottleneck may lie in data I/O, locks, CPU, indexes, or query plans. Do not keep enlarging caches without evidence that it addresses the root cause.

## 12. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| The data dictionary stores business data rows | The data dictionary stores metadata describing database objects |
| Dictionary Object Cache and `table_definition_cache` are the same cache | In MySQL 8.4, they coexist and serve different parts of the server |
| `table_open_cache` is the maximum number of tables in a schema | It is the cache of open table instances across all threads |
| Increasing `table_definition_cache` fixes all table-opening issues | It does not replace the table open cache, file descriptors, or metadata locks |
| A metadata lock is a cache | MDL is a synchronization mechanism for object access |
| Internal data dictionary tables can be edited directly | Use `INFORMATION_SCHEMA` and `SHOW`; never edit dictionary tables directly |
| Large `Opened_tables` always proves the cache is too small | It is a cumulative counter; examine its growth rate over time and related metrics |
| `FLUSH TABLES` is a periodic cache optimization | Flushing closes tables and forces the server to reopen them; poorly timed use adds overhead |
| `TABLE_ROWS` in `INFORMATION_SCHEMA` is always exact | For InnoDB, it is typically an estimated value |
| Atomic DDL means DDL can be rolled back in an application transaction | Atomic DDL is the server's atomic recovery mechanism for supported operations |

## 13. Operational Checklist

- [ ] Identified the running MySQL version and its data dictionary characteristics.
- [ ] Used `SHOW` or `INFORMATION_SCHEMA` to read metadata.
- [ ] Avoided accessing or modifying internal data dictionary tables directly.
- [ ] Distinguished Dictionary Object Cache, table definition cache, and table open cache.
- [ ] Understood that `table_definition_cache` and `table_open_cache` control different layers.
- [ ] Recorded `max_connections` and `open_files_limit` before adjusting `table_open_cache`.
- [ ] Captured baselines and compared status variable deltas under representative workloads.
- [ ] Distinguished the `INFORMATION_SCHEMA` statistics cache from the table definition cache.
- [ ] Checked metadata locks when DDL waits for a long time.
- [ ] Re-measured performance and resource consumption after configuration changes.

## 14. Conclusion

The data dictionary is the foundation of MySQL metadata management. The Dictionary Object Cache holds metadata objects in memory; the table definition cache retains table definitions for reuse; the table open cache retains open table instances for sessions; and the `INFORMATION_SCHEMA` statistics cache speeds up certain metadata statistic queries. Metadata locks coordinate concurrent access to object definitions and must be investigated separately.

In operations, pinpoint the layer causing the issue before altering configuration. Use `INFORMATION_SCHEMA` and `SHOW` to read definitions, status variables to monitor caches, and Performance Schema to investigate metadata locks, then re-measure under realistic workloads. An evidence-based approach avoids inflating memory or file descriptor usage without resolving the actual bottleneck.

## Official References

- [MySQL 8.4 Reference Manual – MySQL Data Dictionary](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Schema](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-schema.html)
- [MySQL 8.4 Reference Manual – Dictionary Object Cache](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-object-cache.html)
- [MySQL 8.4 Reference Manual – Server System Variables: table_definition_cache and table_open_cache](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual – How MySQL Opens and Closes Tables](https://dev.mysql.com/doc/refman/8.4/en/table-cache.html)
- [MySQL 8.4 Reference Manual – Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual – Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual – The Performance Schema metadata_locks Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-metadata-locks-table.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA and Data Dictionary Integration](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-information-schema.html)
