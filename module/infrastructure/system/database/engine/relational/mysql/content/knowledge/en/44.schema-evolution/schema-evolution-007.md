# Adding Columns, Changing Types, Creating Indexes, and Altering Primary Keys on Large Tables

This lesson belongs to the **DATABASE_MYSQL** module. As applications evolve, schemas must change alongside business requirements: adding new attributes, widening data types, adding indexes to optimize queries, or changing primary keys. On small tables, these operations usually complete quickly. On tables with millions or billions of rows, a single `ALTER TABLE` statement can read and rewrite massive volumes of data, consuming I/O, disk space, redo/binlog bandwidth, and causing application disruption.

The goal of schema evolution is controlled structural change while keeping data accurate and services within acceptable operating limits. You need to understand InnoDB DDL algorithms, lock levels, metadata locks, replication impact, and multi-step rollout strategies. You cannot declare a statement "online" from the operation name alone; you must verify support for your exact MySQL version, storage engine, and table definition.

## 1. Why do schema changes on large tables require planning?

A large InnoDB table contains data pages, a clustered index, multiple secondary indexes, and related metadata. When altering its structure, MySQL may:

- Update metadata only without moving data rows.
- Rebuild a single index while leaving table data intact.
- Rebuild the table or clustered index and then rebuild dependent indexes.
- Copy the table into a new structure, transfer data, and swap out the old table.

Cost depends on row count, row width, total index size, data types, foreign keys, write workload, and storage resources. An operation taking seconds on a small test copy can take hours in production.

Common risks:

1. **Downtime or blocked queries:** DDL needs metadata locks at certain points; operations not supporting concurrent DML can hold locks for a long time.
2. **Disk exhaustion:** rebuilds can require extra space for new tables/indexes, temporary files, redo logs, and binary logs.
3. **Load spikes:** scanning tables and building indexes consume CPU, I/O, buffer pool, and storage bandwidth.
4. **Replication lag:** schema changes or generated binlog volume can delay replica apply.
5. **Data distortion:** type conversions can cause rounding, string truncation, numeric overflow, or altered comparison behavior.
6. **Hard rollbacks:** many DDL statements cause implicit commits; you cannot rely on `ROLLBACK` to undo them like an ordinary DML transaction.

Therefore, inspect, test, measure duration, and prepare rollback plans before running DDL on large tables.

## 2. InnoDB DDL algorithms

MySQL provides `ALGORITHM` options to specify how certain table alterations are executed. The main algorithms:

| Algorithm | General mechanism | Impact |
|---|---|---|
| `INSTANT` | Modifies metadata without rebuilding the table | Usually completes very fast; subject to version/table-definition limits and conditions |
| `INPLACE` | Storage engine performs changes without the server's full table-copy workflow | May still rebuild the table or indexes; many operations allow concurrent DML |
| `COPY` | Builds a copy of the table with the new structure, copies data, then swaps | Can take significant time and disk space; typically restricts DML while copying |

**`INPLACE` does not mean no rebuild.** For example, adding a secondary index may build the new index without copying the whole table; changing a primary key may require reorganizing the clustered index and all secondary indexes. Distinguish the algorithm name from the actual physical work performed.

### 2.1. Requesting an algorithm explicitly

If you want an operation to run only when instant execution is supported, specify:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

If the version or table definition does not support that operation via `INSTANT`, the statement errors out rather than falling back to a costlier algorithm. This is a practical way to avoid surprises in production.

Similarly, you can require `INPLACE` and a specific lock level for verified operations:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

`LOCK=NONE` requires allowing concurrent reads and writes for most of the operation where supported by the algorithm. If the operation cannot satisfy that lock level, MySQL returns an error rather than silently taking a broader lock. Even so, brief metadata locks may still be needed at the start and end of the operation.

### 2.2. Previewing execution feasibility

On MySQL 8.0.18 and newer, you can use `EXPLAIN ALTER TABLE` to inspect the algorithm and lock plan MySQL expects to use:

```sql
EXPLAIN ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at);
```

The output helps evaluate whether the operation can use `INSTANT`, `INPLACE`, or requires `COPY`, along with its lock level. This is a useful preliminary check, but you still need to test on a clone matching production size and workload because actual duration depends on resources and concurrent load.

DDL support varies by MySQL version, storage engine, column types, column positions, indexes, foreign keys, and other table properties. The documentation for your exact running version is the authoritative source.

## 3. Lock levels and metadata locks

The `LOCK` parameter controls concurrent access allowed under supported DDL algorithms:

| Lock level | General meaning |
|---|---|
| `NONE` | Permits concurrent reads and writes during the main phase of the operation |
| `SHARED` | Permits reads while restricting writes |
| `EXCLUSIVE` | Acquires an exclusive lock, blocking concurrent access to the table for the lock duration |

Not every algorithm supports every lock level. `LOCK=NONE` does not eliminate all locking; MySQL still acquires metadata locks (MDL) to protect the table definition when starting and finalizing the change.

### 3.1. Metadata locks can block DDL

A long-running transaction that has accessed the table can hold a metadata lock until the transaction finishes. While DDL waits to acquire MDL, incoming queries can also queue behind the pending DDL request, causing many queries to hang even before the DDL begins its rebuild work.

Check metadata locks on a table:

```sql
SELECT OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS,
       OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'shop'
  AND OBJECT_NAME = 'orders';
```

Combine with:

```sql
SHOW FULL PROCESSLIST;
```

Locate long-held transactions or sessions holding locks, and identify the application and owner before taking action. Never kill sessions mechanically: the transaction may be executing critical business logic and rolling it back also carries cost.

### 3.2. Capping MDL wait times

You can set `lock_wait_timeout` on the DDL session so the operation exits if it cannot acquire a metadata lock within the allotted time:

```sql
SET SESSION lock_wait_timeout = 10;
```

The value above is an example in seconds. This is the metadata lock wait timeout, distinct from `innodb_lock_wait_timeout`, which governs InnoDB row lock waits. Setting a short timeout prevents a DDL statement from waiting indefinitely and causing a query pileup, though you must schedule a retry after resolving whatever is holding the MDL.

## 4. Adding columns to large tables

Adding columns is a common change when the application introduces new attributes. The best method depends on MySQL version and table characteristics.

### 4.1. Adding columns with `INSTANT`

For many InnoDB cases on MySQL 8.0.12 and later, adding a column at the end of a table can use instant DDL:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Instant DDL updates metadata without needing to rewrite every row just to add the column. Existing rows are interpreted using the metadata/default of their corresponding row version. However, not all tables or change types support instant execution. For example, row format constraints, special table attributes, column placement, and prior instant DDL counts can affect eligibility.

Starting in MySQL 8.0.29, certain instant add/drop column operations create row versions in metadata; the number of row versions is capped. If the limit is exceeded or the table fails conditions, the operation may require a rebuild. Therefore, never treat `INSTANT` as an unlimited mechanism for arbitrary column changes.

### 4.2. Adding columns with default values

Example:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NOT NULL DEFAULT 'web',
  ALGORITHM=INSTANT;
```

Instant eligibility with defaults depends on version and default type. For expression defaults or special cases, check documentation and run `EXPLAIN ALTER TABLE` when supported. Never assume all default values are handled identically.

In migrations needing multi-version compatibility or controlled backfills, start by adding a nullable column:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Next, have the application begin writing new values and backfill legacy rows in batches. Only after verifying zero `NULL`s remain should you consider altering to `NOT NULL` in a separate migration. Tightening that constraint may require a different algorithm; evaluate it beforehand.

### 4.3. Batched backfills

Never run one massive `UPDATE` across billions of rows when it can be chunked. Use the primary key to bound each batch:

```sql
UPDATE orders
SET source_channel = 'legacy'
WHERE order_id > 100000
  AND order_id <= 110000
  AND source_channel IS NULL;
```

The application or orchestrator script advances `order_id` ranges, saves checkpoints, and moves to the next batch only after the current batch succeeds. Batch size should be measured and tuned against latency, lock waits, redo, binlog, replication lag, and application load.

Backfill principles:

- Range by primary key or a suitable index to avoid full-table scans on every batch.
- Keep each batch transaction short to minimize row lock hold time and undo history.
- Support pausing or throttling when replication lag, I/O, or latency breaches thresholds.
- Make operations idempotent so they can be safely re-run after errors.
- Track updated row counts, remaining rows, and per-batch errors.

Check progress:

```sql
SELECT COUNT(*) AS rows_pending
FROM orders
WHERE source_channel IS NULL;
```

On very large tables, a filtered `COUNT(*)` can be expensive without a suitable index. Use primary-key checkpoints or per-batch counters rather than repeatedly running full-table counts.

## 5. Changing data types

Changing a column's data type can alter storage layout, comparison rules, disk footprint, valid values, and index usability. Before changing, answer:

1. Can all existing data be converted?
2. Will any values be truncated, rounded, overflow, or change collation?
3. Do applications, queries, views, routines, triggers, and indexes depend on the old type?
4. Does MySQL support `INSTANT`, `INPLACE`, or require `COPY` for this exact conversion?
5. Can it be rolled out by adding a new column, backfilling, and switching the application?

### 5.1. Inspecting data before converting

Suppose you want to convert an order code from string to integer. First, find non-numeric values:

```sql
SELECT order_code
FROM orders
WHERE order_code IS NOT NULL
  AND order_code NOT REGEXP '^[0-9]+$'
LIMIT 50;
```

Check value lengths and numeric ranges before converting to `INT` or `BIGINT`. For `DECIMAL`, confirm precision and scale to avoid rounding decimal places or overflow. For `VARCHAR`, check maximum string length and charset/collation.

Pay special attention to these conversions:

- `BIGINT` to `INT`: overflows if values exceed `INT` range.
- `DECIMAL(p,s)` reducing precision or scale: may round or fail to store values.
- `VARCHAR(200)` to `VARCHAR(50)`: long strings may be truncated or rejected depending on SQL mode.
- Changing signed/unsigned: negative values become invalid when converting to unsigned.
- Changing charset/collation: can alter sort order, comparisons, and index uniqueness.
- Changing types on indexed or foreign-key columns: may require coordinated changes on dependent objects.

### 5.2. Testing the ALTER plan before running

Suppose you want to widen precision on a monetary column:

```sql
EXPLAIN ALTER TABLE orders
  MODIFY COLUMN total_amount DECIMAL(15,2) NOT NULL;
```

Only after inspecting data and the plan should you choose the algorithm. If the operation is confirmed to support inplace execution with concurrent DML, specify it explicitly:

```sql
ALTER TABLE orders
  MODIFY COLUMN total_amount DECIMAL(15,2) NOT NULL,
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

This is a syntax pattern, not a guarantee that every MySQL version supports this conversion via `INPLACE`. If unsupported, the command fails because the algorithm was explicitly required. In that case, evaluate `COPY`, a shadow table workflow, or an online schema change tool.

### 5.3. Expanding types using expand-contract

For risky conversions or changes lacking suitable online DDL support, split across multiple releases:

1. **Expand:** add a new column with the target type, keeping the old column intact.
2. **Dual-write:** have the application write to both old and new columns concurrently, or use a controlled synchronization mechanism.
3. **Backfill:** copy legacy data into the new column in batches.
4. **Validate:** reconcile both columns, verifying boundary values and critical business flows.
5. **Switch reads:** switch the application to read from the new column.
6. **Stop old writes:** after verification, stop writing to the old column.
7. **Contract:** in a later release, drop the old column and unused dependencies.

This pattern lets you roll out application changes incrementally while keeping a rollback window. However, dual-writes can fail partially; use proper transactions or retry/reconciliation mechanisms so the two columns never diverge. Avoid maintaining two authoritative data sources for too long.

## 6. Creating indexes on large tables

Indexes reduce the number of rows a query must scan, but building an index on a large table is resource-intensive. InnoDB must scan table data to build the index structure, sort keys, and write new index pages.

### 6.1. Identifying needed indexes

Before creating an index, inspect actual queries and execution plans:

```sql
EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

If queries routinely filter by `customer_id` and then a range on `created_at`, consider a composite index:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Column order in a composite index matters. An index on `(customer_id, created_at)` supports queries filtering by `customer_id` and can continue using `created_at`; it is not equivalent to `(created_at, customer_id)`. Choose column order based on actual filters, joins, and sorts.

Never add an index merely because a column appears in `WHERE`. Evaluate selectivity, query frequency, index size, and write amplification. Every extra index consumes disk space and forces `INSERT`, `UPDATE`, and `DELETE` to maintain an additional structure.

### 6.2. Online index creation

For many InnoDB secondary index types, MySQL supports building indexes with `ALGORITHM=INPLACE, LOCK=NONE`, permitting concurrent DML for most of the process. Still:

- MySQL must read the table and build the index; CPU and I/O can rise sharply.
- Concurrent DML modifications are logged and merged into the new index.
- Brief metadata locks may be required at start and completion.
- Online DDL can fail if concurrent modifications exceed log limits such as `innodb_online_alter_log_max_size`.
- Creating a unique index fails if existing data contains duplicates.

Check the online alter log limit:

```sql
SHOW VARIABLES LIKE 'innodb_online_alter_log_max_size';
```

Do not raise this variable arbitrarily to work around a failed index build. Investigate concurrent write rates, storage capacity, and replica catch-up capability before tuning it.

### 6.3. Verifying indexes after creation

```sql
SHOW INDEX FROM orders;

EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

Compare before/after plans, estimated rows, chosen keys, and runtime on representative workloads. You can use `EXPLAIN ANALYZE` on supported versions to observe actual timings and row counts, though remember it executes the query; never run heavy queries carelessly in production.

To evaluate impact before letting the optimizer use an index, MySQL 8.0 supports invisible indexes for eligible index types. An invisible index is still maintained on data changes and consumes disk space; it is simply ignored by normal optimizer plan selection. Toggling visibility does not eliminate the initial build cost.

## 7. Changing primary keys on large tables

The primary key plays a special role in InnoDB. InnoDB organizes row data in a clustered index, which is typically the primary key itself. Secondary indexes store the primary key value to point to the corresponding row.

Consequences:

- Changing the primary key usually requires reorganizing the clustered index.
- All secondary indexes must be rebuilt because primary key values live in their leaf entries.
- A wide primary key inflates every secondary index and consumes more memory/storage.
- Primary keys referenced by foreign keys have dependencies that must be handled beforehand.
- Clustered index order affects data locality and certain range queries.

Consequently, changing the primary key is typically one of the most expensive schema operations on a large table.

### 7.1. Validating the new key design

Before changing a primary key, verify:

1. Is the new key unique, immutable, and `NOT NULL`?
2. Which child tables currently reference the old key?
3. Do applications, APIs, caches, message queues, and background jobs rely on the old key?
4. Does a unique constraint need to remain on the old business key?
5. How much will secondary indexes grow by storing the new key?
6. Can it be changed via a single native DDL or does it require a shadow table?

Illustrative example switching from a business key to a surrogate key:

```sql
ALTER TABLE orders
  DROP PRIMARY KEY,
  ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ADD PRIMARY KEY (id);
```

This statement only illustrates structural syntax. On populated tables, this operation can rebuild the table and indexes, consuming substantial time and space. If foreign keys reference the old key, plan the migration of child tables and constraints; never run this example verbatim without inventorying dependencies first.

### 7.2. Preserving uniqueness of the legacy key

If the old business key must remain unique, create a corresponding unique index after verifying the data:

```sql
ALTER TABLE orders
  ADD UNIQUE KEY uq_orders_external_ref (external_ref),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Beforehand, check for duplicates and `NULL`s according to business rules. Unique indexes allow multiple `NULL`s depending on column definition; if every row must have a value, enforce an appropriate `NOT NULL` constraint.

### 7.3. Shadow tables for major key changes

For very large tables or complex key migrations, consider building a new table with the target structure:

1. Create `orders_new` with the new primary key and all required indexes/constraints.
2. Begin syncing live changes from the old table to the new table using CDC/online schema change tooling or a well-designed application mechanism.
3. Copy historical data in batches ordered appropriately by key.
4. Reconcile row counts, unique keys, relationships, and business aggregates.
5. Once caught up, pause writes for a brief cutover window.
6. Rename tables or switch endpoints via a rehearsed procedure, then run smoke tests.
7. Retain the old table for the defined rollback period before cleanup.

This is an architectural pattern, not a complete SQL script. DML synchronization, triggers, foreign keys, `AUTO_INCREMENT`, views, and dependent objects must all be explicitly addressed. `RENAME TABLE` can still require metadata locks; renaming does not guarantee a zero-blocking cutover.

## 8. Online schema change tools

When native online DDL cannot meet operational requirements, consider tools that create a shadow table and sync live changes while copying data.

| Tool | General approach | Things to verify |
|---|---|---|
| `pt-online-schema-change` | Creates new table, copies in chunks, and uses triggers to sync changes | Existing triggers, foreign keys, write load, privileges, and cutover conditions |
| `gh-ost` | Creates ghost table, copies in batches, and reads binlogs to sync changes | Binlog/replication settings, topology, privileges, table types, and cutover conditions |
| Native online DDL | Uses DDL algorithms built into MySQL/InnoDB | `ALGORITHM`, `LOCK`, MDL, rebuild time, and version support |

These tools are not automatically safe in every scenario. Check tool version, MySQL version, topology, table types, triggers, foreign keys, replication filters, and operational policies. Shadow tables require extra disk space roughly equal to the current table/indexes; the copy process also adds load and can cause replica lag.

Test on a production clone, measure copy throughput, set load thresholds, and prepare pause/resume controls. Notably, the final cutover still requires metadata locks and can be blocked by long transactions.

## 9. Safe schema change deployment workflow

### 9.1. Pre-change assessment

1. Define the change objective and dependent queries/applications.
2. Record MySQL version, engine, table size, indexes, foreign keys, and workload.
3. Check boundary data, duplicates, `NULL`s, overflows, and type conversion safety.
4. Run `EXPLAIN ALTER TABLE` if supported; determine algorithm and lock level.
5. Check metadata locks, long transactions, replica lag, and free disk space.
6. Test on a clone close to production size; measure duration and resource load.
7. Define abort thresholds, on-call owner, rollback plan, and success criteria.

### 9.2. During execution

- Run one heavy change at a time; avoid combining unrelated operations into one hard-to-control DDL statement.
- Specify `ALGORITHM` and `LOCK` explicitly once verified, so MySQL errors out if conditions are not met.
- Run off-peak if the operation is resource-intensive or involves locking steps.
- Monitor processlist, metadata locks, CPU, I/O, disk space, redo/binlog, replication lag, and application latency.
- For backfills, use small chunks, checkpoints, retries, and throttling.
- Never kill DDL or lock-holding sessions without assessing impact and transaction state.

### 9.3. Post-change verification

1. Inspect the table definition with `SHOW CREATE TABLE`.
2. Inspect indexes with `SHOW INDEX`.
3. Reconcile data, edge values, `NULL`s, duplicates, and cross-table relationships.
4. Run `EXPLAIN` on key queries; measure actual query latency.
5. Verify replicas have applied the change and lag has returned to normal.
6. Monitor error logs, slow query logs, deadlocks, and application errors.
7. Update migration version, operational runbooks, and cleanup schedules for legacy objects.

## 10. Rollback and recoverability

DDL typically causes an implicit commit. Even though certain DDLs are atomic in MySQL 8.0, that does not mean operators can `ROLLBACK` a completed change. Atomic DDL guarantees operation atomicity under supported crash scenarios, not arbitrary business-level rollback.

Recovery options:

- If a new column or index was added and the application does not use it yet, leave it in place and plan removal in a later migration.
- If a type change caused errors, rely on backups or a shadow column to restore original data; reversing a type conversion does not restore truncated or rounded values.
- If changing a primary key, retain the old key as a unique index and keep mappings during transition if the application might roll back.
- If using a shadow table, retain the old table and sync mechanism during the rollback window, while clearly defining which table is the authoritative write source.
- If data was irreversibly altered, use backup/PITR or a tested data-recovery runbook.

Before major changes, verify backups can actually be restored and retain necessary binary logs/GTIDs. Taking a backup is not enough on its own; know your recovery time and point-in-time restore capability.

## 11. Example expand-contract strategy for the orders table

Suppose `orders` needs a new `source_channel` column, then a monetary column widened in precision, and an index added for reporting.

**Phase A — expand schema**

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Deploy application code that reads the new schema while remaining compatible with old data. Begin writing `source_channel` for new orders.

**Phase B — backfill**

```sql
UPDATE orders
SET source_channel = 'legacy'
WHERE order_id > 0
  AND order_id <= 10000
  AND source_channel IS NULL;
```

Iterate over `order_id` ranges, throttle throughput, and persist checkpoints. Never update the whole table at once if doing so exceeds load thresholds.

**Phase C — index**

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_channel_created (source_channel, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Before running, use `EXPLAIN ALTER TABLE` and verify version support. After creation, compare plans and latency of reporting queries.

**Phase D — verify and tighten constraints**

```sql
SELECT COUNT(*) AS rows_missing_channel
FROM orders
WHERE source_channel IS NULL;
```

Once zero rows are missing, the application writes values consistently, and the constraint change has been evaluated, run a separate migration to alter to `NOT NULL`. Continue monitoring before cleaning up legacy compatibility logic.

For the monetary column, check min/max values, scale, and out-of-range data before modifying the type. Run a native `ALTER` only once algorithm, lock level, and duration are verified; otherwise use a shadow column and corresponding backfill workflow.

## 12. Checklist before altering large tables

- [ ] Defined the change objective and dependent application components.
- [ ] Recorded MySQL version, storage engine, and current table definition.
- [ ] Surveyed row count, data/index footprint, primary key, secondary indexes, and foreign keys.
- [ ] Checked boundary data, duplicates, `NULL`s, overflows, and data loss risk on type conversion.
- [ ] Verified supported `ALGORITHM` and `LOCK`; ran `EXPLAIN ALTER TABLE` if available.
- [ ] Checked metadata locks, long transactions, and `lock_wait_timeout`.
- [ ] Evaluated CPU, I/O, temporary space, redo/binlog, and replication lag.
- [ ] Tested on a production clone and measured actual runtime.
- [ ] Prepared backup/PITR or shadow table matching risk level.
- [ ] Defined batch size, checkpoints, and backfill throttling.
- [ ] Prepared monitoring, abort thresholds, on-call owner, and runbook.
- [ ] Defined verification criteria for schema, data, indexes, application, and replicas.
- [ ] Defined rollback procedure and retention period for legacy structures.

## 13. Self-check

1. Does `ALGORITHM=INPLACE` mean MySQL will not rebuild the table? Explain.
2. Does `LOCK=NONE` completely eliminate metadata locks? Why or why not?
3. Why can explicitly specifying `ALGORITHM=INSTANT` prevent an `ALTER` from unexpectedly falling back to `COPY`?
4. Why is adding a nullable column followed by batched backfill usually easier to control than one large change?
5. What risks must be checked before converting `BIGINT` to `INT` or reducing `DECIMAL` precision?
6. Why can building a secondary index with online DDL still increase latency and replication lag?
7. Why can changing the primary key force secondary indexes in InnoDB to be rebuilt?
8. How can a metadata lock from a long transaction cause a query queue?
9. What is the difference between `lock_wait_timeout` and `innodb_lock_wait_timeout`?
10. Design an expand-contract plan to add a required column to a table with hundreds of millions of rows, including backfill, verification, and rollback.

Schema changes on large tables should be treated as operational changes involving load, locks, and data risk. Verify algorithms, lock levels, and dependencies before running; roll out in measurable steps; and verify data, queries, replicas, and applications before dropping legacy structures.
