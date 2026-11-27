# Locking by scanned indexes and the impact of execution plans

In InnoDB, locks acquired by an UPDATE, DELETE, or locking read statement are typically placed on the index records accessed by the engine during its search. Consequently, the lock scope does not depend solely on the final number of rows matching the WHERE condition; it also depends on the chosen index, the index range scanned, the isolation level, and how MySQL evaluates filter predicates.

An UPDATE expected to modify 10 rows may end up traversing a much larger index range. Without a suitable index, the optimizer may choose a full table scan; InnoDB must examine more records and may hold more locks during execution. Conversely, a properly ordered composite index can narrow the search region, reduce the number of records locked, and minimize waiting for other transactions.

In the **DATABASE_MYSQL** module, understanding the relationship between execution plans and lock footprint helps diagnose lock waits, reduce deadlocks, and design indexes for write workloads. This lesson focuses on how InnoDB locks index records, how access paths change lock scope, the differences between REPEATABLE READ and READ COMMITTED, and a workflow for inspecting plans and locks using EXPLAIN and Performance Schema.

## 1. Why do indexes determine lock scope?

InnoDB organizes data using a clustered index and secondary indexes. A statement searching for rows via an index traverses B-tree entries. When the statement needs to lock data, InnoDB places locks on the relevant index records; with a secondary index, the engine also needs to protect the corresponding records in the clustered index when performing writes or locking reads.

Distinguish three concepts:

- **Rows matched:** the final number of rows satisfying the WHERE condition.
- **Rows examined/scanned:** the number of records or entries the optimizer and storage engine must inspect to find the results.
- **Lock footprint:** the set of index records and index gaps that the transaction actually locks during execution.

These three metrics are related but not necessarily equal. A broad scan plan can increase the lock footprint even when the final number of updated rows is small. Details regarding releasing locks for non-matching rows also depend on the isolation level and how predicates are evaluated.

### 1.1. Locks are tied to index records

InnoDB does not lock an abstract logical row concept independently of indexes. A record lock protects an index record. A gap lock protects the interval between index records. A next-key lock combines a record lock with the gap immediately preceding that record.

Therefore, if an UPDATE uses a secondary index to locate rows, locks can appear on both the secondary index entry and the corresponding record in the clustered index. When inspecting locks, you may see index names other than PRIMARY.

Example table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tenant_status_created (
        tenant_id,
        status,
        created_at
    )
) ENGINE = InnoDB;
```

Query:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

If the optimizer uses `idx_tenant_status_created`, InnoDB can search within a narrow region defined by `tenant_id`, `status`, and the `created_at` range. Without an appropriate index, the server may have to read many more rows to evaluate the three predicates.

## 2. Distinguishing access path types in execution plans

An execution plan describes how the optimizer intends to locate data. Values in the `type` column of EXPLAIN indicate the access method, though they do not by themselves tell you the exact number of locks that will be held.

Common access types:

| Access type | General meaning | Potential impact on locking |
|---|---|---|
| const / system | Finds at most one row via a unique key or very small table | Usually has a narrow scope |
| eq_ref | Each combination from previous rows matches at most one row via a unique key | Usually locks few records per lookup |
| ref | Finds rows by a non-unique index value | Can lock many entries sharing the same value |
| range | Scans an index interval | Can lock records and gaps within the interval |
| index | Scans an entire index | Broad scan scope even when reading only the index structure |
| ALL | Full table scan | Can lead to a very large lock scope for DML/locking reads |

Do not draw conclusions from access type alone. Also examine `key`, `key_len`, `rows`, `filtered`, `Extra`, range predicates, and data distribution. For example, `type=range` over a tiny interval can be far better than `ref` on a value with millions of records.

### 2.1. EXPLAIN columns to read

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Key columns:

| Column | How to read it |
|---|---|
| type | Access method such as range, ref, eq_ref, index, or ALL |
| possible_keys | Indexes the optimizer may consider |
| key | Index actually chosen |
| key_len | Length of the index prefix used; helps infer which key parts participate |
| ref | Values/columns compared against the index |
| rows | Estimated number of rows to read |
| filtered | Estimated percentage of rows remaining after additional filter conditions |
| Extra | Information such as Using where, Using index condition, Using temporary, or Using filesort |

EXPLAIN generally provides estimates, not exact lock counts. `rows` and `filtered` cannot be used as actual lock counts. Combine the execution plan with lock observations while the transaction is open.

If a version or syntax does not support EXPLAIN directly for a certain DML type, you can run EXPLAIN on a SELECT with the same predicates and JOINs to understand the access path as a reference. An equivalent SELECT plan is not guaranteed to be identical to the DML plan in every case.

### 2.2. EXPLAIN ANALYZE is not a lock counter

On MySQL versions supporting EXPLAIN ANALYZE, this statement executes a SELECT and displays actual row counts and timings across iterators:

```sql
EXPLAIN ANALYZE
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Actual execution metrics help compare `rows` estimates against rows examined/returned. However, this is a regular SELECT, not a measurement of the number of record locks an UPDATE will acquire. Do not use EXPLAIN ANALYZE as proof of lock footprint.

EXPLAIN ANALYZE runs the real query and may read large amounts of data, so choose an appropriate time in environments under load.

## 3. Appropriate indexes narrow the scan region and lock footprint

Suppose a query frequently filters by `tenant_id`, `status`, and then bounds a timestamp:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Composite index:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

This column order supports the two equality predicates at the start of the index, followed by the range on `created_at`. The B-tree can navigate directly to the matching tenant/status region and scan only the required time slice.

### 3.1. Leftmost prefix and column ordering

The composite index `(tenant_id, status, created_at)` can serve predicates based on:

- `tenant_id`
- `tenant_id` and `status`
- `tenant_id`, `status`, and a `created_at` range

It does not directly provide a contiguous efficient range for queries filtering only on `status` or only on `created_at` without constraining the leading column, unless the optimizer uses another strategy such as skip scan under suitable conditions and supported versions.

With equality predicates on multiple columns, equality columns are generally placed before range columns. Ordering among equality columns must also account for other queries, selectivity, and required sort orders.

### 3.2. Comparing index choices

| Index | Query predicates | Narrowing capability |
|---|---|---|
| (tenant_id, status, created_at) | tenant_id = ?, status = ?, created_at < ? | Can use both equality prefix and range |
| (status, created_at) | tenant_id = ?, status = ?, created_at < ? | Can filter status/range; tenant_id may become a residual filter |
| (created_at) | tenant_id = ?, status = ?, created_at < ? | Scans the time range then checks tenant/status |
| No suitable index | All three predicates above | May require a full scan |

A suboptimal index may still be selected if the optimizer estimates it to be cheaper. In that case, the number of records inspected can be larger than desired and the lock footprint can grow.

### 3.3. A covering index does not eliminate locking clustered records

A covering index allows a regular SELECT to retrieve all needed columns from the secondary index without reading the clustered record. However, for locking reads and DML, do not conclude that a covering index removes the need to protect the clustered record. InnoDB still must protect the actual rows being locked or updated.

Thus, adding columns to an index to make it covering may reduce read I/O, but it does not automatically eliminate the locks required by UPDATE/DELETE.

## 4. Full table scans and the risk of overly broad locking

If a WHERE condition lacks a suitable index, the optimizer may choose ALL:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE DATE(created_at) = '2025-12-31';
```

Calling the `DATE` function on the `created_at` column typically prevents a standard B-tree index on `created_at` from being used for direct range access. MySQL may have to inspect many rows to find records belonging to the target date.

In locking DML, InnoDB locks the index records traversed by the search according to the rules of the isolation level. A wide scan can create significantly more locks than the number of rows ultimately changed. Under REPEATABLE READ, next-key locking over the scanned range can also block inserts into the corresponding gaps.

Rewriting the predicate as a range usually allows the index to work effectively:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE created_at >= '2025-12-31 00:00:00'
  AND created_at <  '2026-01-01 00:00:00';
```

If the workload also filters on `tenant_id`, consider a composite index starting with `tenant_id` followed by `created_at`. Inspect the plan before running a broad UPDATE.

### 4.1. Avoiding implicit conversions on indexed columns

Compare:

```sql
-- May lose efficient range access depending on data type and expression
SELECT order_id
FROM orders
WHERE CAST(tenant_id AS CHAR) = '42';

-- Direct comparison with numeric type
SELECT order_id
FROM orders
WHERE tenant_id = 42;
```

Keep parameter data types compatible with column types, and avoid wrapping columns in functions unnecessarily. This helps the optimizer use indexes predictably.

### 4.2. LIKE and leading wildcards

A LIKE predicate with a leading wildcard typically cannot use a B-tree prefix range:

```sql
UPDATE customers
SET status = 'REVIEW'
WHERE email LIKE '%@example.com';
```

If you frequently search by domain, consider storing the normalized domain in a dedicated column and indexing it appropriately. Do not create functional indexes or generated columns without clearly defining normalization rules and collation.

## 5. Secondary indexes and clustered indexes both participate in locking

When an UPDATE/DELETE locates rows via a secondary index, InnoDB uses the secondary entry to identify the row and also needs to access the corresponding clustered index record to modify the row data. Therefore, Performance Schema can show locks on both the secondary index and PRIMARY.

Example:

```sql
UPDATE orders
SET total_amount = total_amount + 10000
WHERE tenant_id = 42
  AND status = 'PENDING';
```

If `idx_tenant_status_created` is used, the search range traverses that index. Each row to be updated also involves the clustered record keyed by `order_id`.

If you update a column that appears in a secondary index, the engine must also maintain every index containing that column. Distinguish:

- **Search index:** the index the optimizer uses to locate rows and define the scan range.
- **Updated index:** the indexes that require maintenance because a column value changed.
- **Clustered index:** where the data record and primary key reside.

One index can be both a search index and an updated index. Updating an indexed column can incur extra index work and locking even when the WHERE condition targets a single row.

## 6. Isolation levels change range locking behavior

### 6.1. REPEATABLE READ

REPEATABLE READ is InnoDB's common default isolation level. For locking reads and DML using range scans, InnoDB typically uses next-key locks to lock records along with their associated gaps, preventing other transactions from inserting phantoms into the protected region.

Example:

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
FOR UPDATE;
```

With a suitable index, locks can be confined to the scanned index region. Another transaction inserting a row into a gap within the locked region may have to wait.

### 6.2. READ COMMITTED

Under READ COMMITTED, gap locking for searches and index scans is generally disabled, except where needed for FOREIGN KEY checks and duplicate-key checks. Record locks are still used for rows being updated/locked.

An important feature of READ COMMITTED is that InnoDB can use semi-consistent reads for UPDATE: when encountering a row locked by another transaction, MySQL can read the latest committed version to evaluate WHERE; if the row does not match, it can be skipped without waiting to acquire an X lock on that row. If the row matches, the transaction waits and re-reads to perform the update.

This can make the actual lock footprint differ from REPEATABLE READ. Do not assume that two isolation levels produce the same lock footprint simply because their execution plans look identical.

Check the session isolation level:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Changing the isolation level can alter read semantics, phantom possibilities, and concurrency behavior. Test in a controlled environment and verify business requirements before making changes.

## 7. Unique lookups, range scans, and gap locks

Different access patterns typically exhibit different lock scopes:

| Access pattern | Typical locking behavior |
|---|---|
| Exactly one row found using the full PRIMARY/UNIQUE key | Usually locks the record without a gap lock before that record |
| Lookup using a non-unique index | Can lock multiple records with the same value and related gaps under REPEATABLE READ |
| Range scan on an index | Can use next-key locks across the scan range |
| Value not found using a unique index | May need a gap lock at the position where the value would be inserted, depending on isolation and operation |
| Full table scan in locking DML | Can lock a very large number of records and gaps, causing broad impact |

The descriptions above are general patterns, not formulas replacing direct observation. Locking reads, UPDATE, DELETE, isolation level, and index type can all change the exact details.

## 8. Execution plans can shift as statistics change

The optimizer selects indexes based on statistics, cardinality, selectivity, I/O/CPU cost, and query structure. As data grows or distributions change, the same UPDATE statement may adopt a different access path.

Example:

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

If `key` previously was `idx_tenant_status_created` but later switches to a less selective index or ALL, the lock footprint can change. Consequences can include:

- More index records scanned.
- Transactions holding locks longer.
- More other transactions waiting on the same region.
- Increased deadlocks due to changed record access order.
- Longer rollback times when a transaction has modified many rows.

When statistics are stale, consider updating them with ANALYZE TABLE during an appropriate maintenance window:

```sql
ANALYZE TABLE orders;
```

ANALYZE TABLE refreshes optimizer statistics; it is not an automatic optimization command. Afterward, re-read EXPLAIN and benchmark because the plan can change. Do not refresh statistics arbitrarily while the system is under heavy load without assessing the impact.

## 9. Using EXPLAIN to inspect the plan before writing

Before running a critical UPDATE/DELETE, inspect the plan:

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

If your version supports EXPLAIN for DML, run it directly on the statement to be checked. Otherwise, use a SELECT with the same tables, JOINs, and predicates as a proxy, keeping in mind that the plan may differ.

A plan-reading checklist:

1. Check whether `type` is ALL or a full index scan.
2. Check whether `key` is the expected index.
3. Check `key_len` to see how many key parts are used.
4. Check whether estimated `rows` is abnormally large.
5. Check `filtered` and `Extra` to see residual conditions evaluated after reading the index.
6. Check WHERE predicates for functions, implicit conversions, or leading wildcards.
7. Compare the plan against real data and value distributions.

EXPLAIN does not display the exact record locks that will be held. It reveals the access path so you can anticipate the scan scope. To verify locks, you must observe an open transaction.

## 10. Observing actual locks with Performance Schema

MySQL 8.0 provides Performance Schema tables to observe InnoDB locks.

### 10.1. Existing locks

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders';
```

Useful columns:

- OBJECT_NAME: the table being locked.
- INDEX_NAME: the related index record, e.g., PRIMARY or a secondary index.
- LOCK_TYPE: locked object type, usually TABLE or RECORD.
- LOCK_MODE: modes such as X, S, X,GAP, X,REC_NOT_GAP, or intention variants.
- LOCK_STATUS: GRANTED or WAITING.
- LOCK_DATA: locked key values displayed if available.

LOCK_DATA can be NULL when the page/index record is not in the buffer pool or the data cannot be displayed in that format. Do not interpret NULL as "no lock."

### 10.2. Who is waiting on whom?

```sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx
FROM performance_schema.data_lock_waits;
```

To retrieve thread and statement details, join with `data_locks` and Performance Schema `threads`. Exact table/column names should be verified against your specific version:

```sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_MODE AS requested_mode,
    r.LOCK_DATA AS requested_data,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    b.LOCK_MODE AS blocking_mode,
    b.LOCK_DATA AS blocking_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

The output helps identify which index a transaction is waiting on and which transaction is blocking it. To find the SQL statement, join transaction/thread with Performance Schema `events_statements` or inspect `INFORMATION_SCHEMA.INNODB_TRX`.

### 10.3. Open transactions

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
```

Long-running transactions can hold locks and increase contention. Before terminating an application transaction, identify its owner, statement, data scope, and business rollback impact.

### 10.4. The sys schema for diagnostics

If the `sys` schema is installed and you have appropriate privileges, you can inspect summary views such as `sys.innodb_lock_waits`:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

The view helps quickly read blocking/waiting transactions. When deep analysis is needed, return to Performance Schema to inspect indexes, lock modes, and specific data.

## 11. Two-session experiment: same data, different access paths

Run this experiment in a lab database with two separate connection windows. Use a small table for easy observation, and always ROLLBACK/COMMIT afterward.

Create the table:

```sql
CREATE TABLE lock_demo (
    id BIGINT NOT NULL,
    tenant_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tenant_status (tenant_id, status)
) ENGINE = InnoDB;

INSERT INTO lock_demo (id, tenant_id, status, note)
VALUES
    (1, 10, 'PENDING', 'a'),
    (2, 10, 'PENDING', 'b'),
    (3, 10, 'PAID', 'c'),
    (4, 20, 'PENDING', 'd'),
    (5, 20, 'PAID', 'e');
```

### 11.1. Session A: locking a region by index

Run in Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM lock_demo
WHERE tenant_id = 10
  AND status = 'PENDING'
FOR UPDATE;
```

With the `idx_tenant_status` index, the query can target the region for tenant 10 and status PENDING. Query `performance_schema.data_locks` from another session to observe locks on the index.

### 11.2. Session B: testing operations in the same vs. different region

In Session B, try updating a row inside the locked region:

```sql
UPDATE lock_demo
SET note = 'blocked'
WHERE id = 1;
```

The statement may wait on Session A because the same record is locked. Try operating on a row belonging to tenant 20 for comparison:

```sql
UPDATE lock_demo
SET note = 'other-range'
WHERE id = 4;
```

If index ranges and gaps do not overlap, this operation can usually complete. Exact behavior depends on locked gaps, key positions, and the chosen plan.

End Session A:

```sql
ROLLBACK;
```

If Session B was waiting, it can proceed after the locks are released. After the experiment, roll back Session B if needed and clean up the lab data.

### 11.3. Comparing when removing the index

Never drop indexes on a live production system. In a lab, you can create a copy table without `idx_tenant_status` or use `IGNORE INDEX` to test a different plan:

```sql
EXPLAIN
SELECT *
FROM lock_demo IGNORE INDEX (idx_tenant_status)
WHERE tenant_id = 10
  AND status = 'PENDING';
```

Then execute a locking read in a separate transaction and observe `data_locks`. `IGNORE INDEX` here is strictly for learning and comparison. Do not use hints to force production plans without benchmarking and understanding the impact across all data distributions.

## 12. When can a good plan still cause lock contention?

A good index shrinks the scan region, but it does not guarantee zero lock waits. Causes include:

- Multiple transactions updating the same hot row simultaneously.
- Multiple sessions updating different rows that contend on the same unique key or gap.
- Foreign keys forcing checks on parent rows currently locked by another transaction.
- Triggers or cascades expanding the set of modified rows.
- Transactions holding locks too long while doing work outside the database before committing.
- Two transactions acquiring locks in opposite orders and forming a deadlock cycle.
- A row accessed via multiple indexes where concurrent update operations intersect.

In these scenarios, improving the access path only solves part of the problem. You must review the data model, workload partitioning, update ordering, transaction scope, and retry strategy.

## 13. Lock order and deadlocks when plans change

An execution plan affects not only the number of scanned records, but also the order in which records are accessed. If two transactions update the same set of rows in different orders, deadlock risk increases.

Example:

- Transaction A updates `order_id` 10 then 20.
- Transaction B updates `order_id` 20 then 10.

Each transaction holds the lock on its first row and waits for the second row, creating a wait cycle.

Whenever possible, process keys in a consistent order, such as ascending primary key order. When a statement uses a range scan on another index, the access order may differ from primary key order. Inspect the actual plan and locks rather than assuming SQL order in an `IN` list dictates lock acquisition order.

InnoDB detects deadlocks and rolls back one transaction as the victim. The application must retry the entire transaction in a controlled manner using backoff and ensure operations are idempotent where necessary. Do not merely re-run the last SQL statement if earlier steps were rolled back.

## 14. Practical ways to reduce lock footprint

1. **Write index-friendly predicates.** Avoid functions on indexed columns, unnecessary type casts, and leading wildcards.
2. **Design composite indexes with the right column order.** Place appropriate equality columns before range columns and account for the rest of the workload.
3. **Reduce unmatched rows before updating.** Batch by a stable key or filter by tenant/time range.
4. **Keep transactions short.** Do not hold locks during HTTP calls, user waits, or unrelated tasks.
5. **Update in a consistent order.** Reduce deadlock likelihood across concurrent threads.
6. **Avoid locking reads when unnecessary.** A regular SELECT in InnoDB is a consistent read and acquires no row locks; use FOR UPDATE/FOR SHARE only when business logic requires them.
7. **Evaluate isolation levels by semantics.** READ COMMITTED can reduce gap locking, but it is not the default solution for every workload.
8. **Measure before adding indexes.** New indexes shrink scans but increase write overhead, storage, and maintenance cost.
9. **Monitor lock waits.** Use `data_locks`, `data_lock_waits`, `INNODB_TRX`, and deadlock logs.
10. **Re-verify after statistics or schema changes.** Re-read EXPLAIN because plans can shift.

### 14.1. Batching by primary key

If a large number of rows must be updated, split the work into small batches by primary key:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE order_id > 0
  AND order_id <= 1000
  AND status = 'PENDING';
```

Subsequent batches process the next key intervals. In practice, track a watermark, handle newly arriving rows, and ensure no data is skipped. Do not use fixed ID ranges if keys do not reflect ordering or if data has large gaps without a tracking mechanism.

Smaller batches reduce lock duration per transaction and help replicas keep up in many workloads, though they introduce extra commit overhead. Choose batch size based on latency, throughput, lock waits, and replication lag.

## 15. Workflow for investigating execution-plan-driven lock waits

When an UPDATE/DELETE becomes slow or blocks other transactions, follow these steps:

1. Collect the SQL statement, bind parameters, start time, and transaction ID.
2. Determine the expected rows to modify and the actual rows affected.
3. Run EXPLAIN on the DML if supported; otherwise, use an equivalent SELECT to inspect the access path.
4. Read `type`, `key`, `key_len`, `rows`, `filtered`, and `Extra`.
5. Identify locked index records and lock modes from `performance_schema.data_locks`.
6. Locate blocking transactions in `data_lock_waits` and `INNODB_TRX`.
7. Check isolation level, gap locks, foreign keys, triggers, and cascades.
8. Check whether the plan changed due to statistics or altered data distribution.
9. Test indexes or query rewrites in staging; measure both speed and lock footprint.
10. Run two-session tests to confirm which regions still block other transactions.
11. Monitor deadlocks, p95/p99 latency, rows examined, and throughput after deployment.

Do not conclude "missing index" from a single lock wait. Hot rows, long transactions, gap locks, or update ordering can be the root cause even when the plan already uses a good index.

## 16. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Looking only at successful UPDATE row count | Overlooking scanned and locked records during lookup | Inspect access path and observe actual locks |
| Seeing type=range and assuming few locks | The range may be very wide | Check key, rows, predicates, and data distribution |
| Thinking a covering index prevents UPDATE from locking clustered records | Misunderstanding InnoDB locking behavior | Distinguish search index from records actually updated |
| Assuming no index still locks only rows matching WHERE | Wide scans can greatly expand the lock scope | Add an appropriate index and re-measure |
| Using EXPLAIN ANALYZE to count locks | EXPLAIN ANALYZE SELECT does not measure an UPDATE's lock footprint | Use Performance Schema in a real test transaction |
| Forcing FORCE INDEX without benchmarking | Can produce worse plans as data evolves | Use hints only after measuring and with clear justification |
| Assuming READ COMMITTED has zero gap locks in all cases | Overlooking FK and duplicate-key checks | Understand isolation level exceptions |
| Thinking SQL ORDER BY always dictates lock order | The optimizer may use a different access path | Inspect the actual plan and locks |
| Retrying only the statement that hit a deadlock | Prior work in the transaction was rolled back | Retry the entire transaction |
| Adding indexes without considering write cost | DML incurs extra storage and index maintenance | Evaluate the overall read/write workload |

## 17. Key takeaways

- InnoDB places locks on index records and index gaps; lock footprint is directly affected by the access path.
- Rows updated, rows scanned, and locks held are not always equal.
- UPDATE/DELETE statements locating rows via a secondary index still must protect the corresponding clustered records.
- A full table scan in locking DML can produce a very large lock scope; appropriate indexes narrow the search region.
- Composite indexes should reflect equality conditions, range predicates, and real workloads; leftmost prefix governs usability.
- REPEATABLE READ normally uses next-key locking for ranges; READ COMMITTED generally reduces gap locks but retains exceptions for FK and duplicate-key checks.
- EXPLAIN shows the access path and estimates; it does not display exact record lock counts.
- EXPLAIN ANALYZE SELECT measures actual rows/time for SELECT, not lock counts for UPDATE.
- Use Performance Schema `data_locks`, `data_lock_waits`, `INFORMATION_SCHEMA.INNODB_TRX`, and `SHOW ENGINE INNODB STATUS` to inspect actual locks.
- Optimizer statistics changes can alter plans and lock footprints; re-read EXPLAIN after data/index changes.
- Reduce lock waits through proper indexes, short transactions, controlled batching, and consistent update ordering.
- Deadlocks require retrying the entire transaction with reasonable limits.

When a DML statement causes lock waits, treat the execution plan as a map showing which index records InnoDB must traverse. Cross-referencing that map with observed locks will help pinpoint overly broad scans, suboptimal indexes, or hot spots that need attention.
