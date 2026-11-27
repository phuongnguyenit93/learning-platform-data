# Point lookups by unique key vs. range queries

In InnoDB, two queries can return nearly the same number of rows yet produce vastly different lock scopes. A point lookup using a full unique key typically only needs to lock the found record. A range query may also lock the empty gaps between index records to prevent other transactions from inserting new rows into the protected range.

This difference directly affects concurrency. Point lookups usually have a narrow and predictable lock scope. Range queries are useful when you need to protect a set of rows or a value interval, but they can cause inserts or updates in other sessions to wait. To properly understand lock scope, you must consider the query predicates, the index chosen by the optimizer, the isolation level, and the type of read statement.

## Objectives

After this lesson, you will be able to:

- Distinguish InnoDB record locks, gap locks, and next-key locks.
- Explain why a lookup using a full unique key usually locks more narrowly than a range query.
- Predict the impact of range queries on concurrent inserts and updates.
- Recognize the effect of composite indexes, non-unique indexes, and execution plans on lock scope.
- Compare locking behavior under `REPEATABLE READ` and `READ COMMITTED`.
- Observe held locks and tune queries to reduce contention.

Examples assume MySQL 8.0 or later and tables using the InnoDB storage engine.

## 1. InnoDB locks are tied to indexes

InnoDB organizes data according to a clustered index. InnoDB record locks are placed on index records, not on an abstract object detached from indexes. If a query uses a secondary index, InnoDB may need to lock both the secondary index record and the corresponding record in the clustered index to protect the data row.

Three concepts to distinguish:

- **Record lock:** locks a specific index record. This lock protects the corresponding row from conflicting operations.
- **Gap lock:** locks an empty space between index values. It prevents other transactions from inserting records into that interval, though a gap lock itself does not lock an existing data record.
- **Next-key lock:** combines a record lock with a gap lock preceding the index record. This is the mechanism InnoDB typically uses for searches or range scans under `REPEATABLE READ` to protect both the record and its associated gap.

For example, an index has values `10`, `20`, `30`. The gaps can be visualized as:

```text
(-∞, 10)   10   (10, 20)   20   (20, 30)   30   (30, +∞)
```

A record lock on `20` protects the index record with value `20`. A gap lock on `(10, 20)` protects the empty space before `20`. The next-key lock associated with `20` covers record `20` and the gap immediately before it. This model helps conceptualize scope; actual scope depends on index ordering and the records traversed by the access plan.

## 2. Point lookups using a full unique key

Suppose an orders table has primary key `order_id` and an external reference code guaranteed to be unique:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(64) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_orders_external_ref (external_ref),
    KEY ix_orders_status_created (status, created_at)
) ENGINE = InnoDB;
```

When a transaction needs to lock an existing order by `external_ref`, it can run:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;

-- Check and process the order within the same transaction.
COMMIT;
```

The condition above uses an equality comparison against the entire key of a unique index. If the record exists and the optimizer uses that unique index, InnoDB uses a record lock for the found row without needing to lock the gap immediately before the record as a standard next-key lock would. With a unique secondary index, the engine may need to lock both the secondary index record and the corresponding record in the clustered index. The lock scope is therefore usually narrow and rarely impacts inserts of other reference codes.

`FOR UPDATE` must be inside a transaction if the application wants to hold locks across multiple statements. When `autocommit = 1` and no explicit transaction is opened, the statement's transaction ends right after the `SELECT`, so the lock is released when the statement finishes:

```sql
START TRANSACTION;
SELECT order_id
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;

-- Perform validation/update steps that need protection.
COMMIT;
```

This rule applies only when the condition fully specifies a unique value. For example, with a composite unique index `(tenant_id, external_ref)`, a point lookup must specify both columns:

```sql
SELECT order_id
FROM tenant_orders
WHERE tenant_id = 7
  AND external_ref = 'EXT-2026-001'
FOR UPDATE;
```

If you only filter `tenant_id = 7`, the condition does not identify a unique row; it is a search on a partial composite key and may scan and lock multiple records or index gaps.

Cases where a query ceases to be a unique point lookup:

- Providing only a subset of columns of a composite unique index.
- Using range conditions such as `>`, `>=`, `<`, `BETWEEN`, or prefix searches.
- Using a non-unique column, even with `=`.
- Writing expressions or type conversions that prevent the optimizer from using the unique index as expected.
- The execution plan choosing a different access path instead of the unique index.

If the unique key lookup finds no row, there is no existing record to lock. Under `REPEATABLE READ`, the search may protect the empty slot with a gap lock depending on the statement and access path. Thus, do not generalize the rule "unique lookup only locks a record" to nonexistent keys; the example above assumes the order already exists.

## 3. Range queries

Suppose the application needs to process pending orders created within a time window:

```sql
START TRANSACTION;

SELECT order_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
ORDER BY created_at, order_id
FOR UPDATE;

-- Process the locked orders.
COMMIT;
```

The `(status, created_at)` index helps InnoDB locate rows by status and then scan the time range within that status group. Under `REPEATABLE READ`, a range-based locking read typically uses next-key locks on the scanned index records and associated gaps. This protects the dataset being processed from certain phantom inserts within the locked scope.

For example, another transaction attempting to insert a new order with `status = 'PENDING'` and `created_at` between November 1 and November 7 may have to wait if the insertion position falls inside a locked gap. An insert outside that range is usually not blocked by the same lock scope. Exact boundaries depend on the index and execution plan.

A range query does not have to return many rows to produce a broad lock scope. A predicate matching only a few rows can still scan a large index region if the predicate does not align well with the index. Conversely, an appropriate composite index can significantly narrow the scan and lock region.

## 4. Comparing lock scopes

| Query type | Condition example | Typical behavior in InnoDB `REPEATABLE READ` | Concurrency impact |
|---|---|---|---|
| Point lookup by primary key | `order_id = 100` | Record lock on the found row | Other transactions updating/deleting the same row must wait; other rows can usually still be processed |
| Point lookup by unique index | `external_ref = 'EXT-1'` | Record lock on the found record if using the full unique key | Usually does not block inserts into the gap before that record |
| Equality on a non-unique index | `status = 'PENDING'` | Can lock matching records and associated gaps | Inserting additional rows with the same value may have to wait |
| Range on an index | `created_at >= a AND created_at < b` | Usually uses next-key locks over the scanned index region | Inserts within the region may have to wait |
| No suitable index | Filtering on an unindexed column | Can scan and lock a very broad scope | Many unrelated transactions may be affected |

The table describes common tendencies, not a fixed lock-count guarantee for every statement. You must inspect the execution plan, actual indexes, and isolation level to draw conclusions.

## 5. Two-session observations

### Case A: point lock on a unique index

Suppose the code `EXT-2026-001` already exists.

**Session A**

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;
```

**Session B** can update another order:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE external_ref = 'EXT-2026-002';
```

If the two queries locate two different rows and there are no other conflicting constraints or locks, Session B does not need to wait for the row lock held by A. If B updates `EXT-2026-001` itself, B must wait for A to finish its transaction.

### Case B: range lock on a composite index

**Session A** holds locks on pending orders within a date range:

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
FOR UPDATE;
```

**Session B** attempts to insert a new order matching the range condition:

```sql
INSERT INTO orders
    (order_id, external_ref, customer_id, status, created_at)
VALUES
    (9001, 'EXT-2026-9001', 77, 'PENDING', '2026-11-04 10:30:00');
```

Under `REPEATABLE READ`, if A's plan scans and locks the corresponding index interval, B's insert may have to wait for a gap/next-key lock. Only after A runs `COMMIT` or `ROLLBACK` can B proceed. Try again with a timestamp outside the range to observe the difference.

When testing, open two independent MySQL connections. Do not run A and B in the same session because a session can have only one active transaction.

## 6. Isolation levels alter range locking behavior

InnoDB defaults to `REPEATABLE READ`. At this level, gap locks and next-key locks are used for many searches or index scans to prevent phantoms during locking operations.

Under `READ COMMITTED`, InnoDB generally disables gap locking for searches and index scans. Locking reads then mainly lock index records; gap locks can still appear for foreign key checks and duplicate-key checks. Some record locks on non-matching rows may be released after MySQL evaluates the `WHERE` condition.

| Characteristic | `REPEATABLE READ` | `READ COMMITTED` |
|---|---|---|
| Consistent read | Uses the same read view within the transaction | Creates a new read view for each consistent read statement |
| Gap/next-key lock for range search | Commonly used to prevent phantoms | Usually not used for regular searches/scans |
| Foreign key and duplicate-key checks | Acquires required locks | Can still use gap locks in these cases |
| Phantoms between two reads | Consistent snapshot for consistent reads; locking reads use range locks | Newly committed rows can appear in subsequent statements |

Do not lower the isolation level just to avoid lock waits without verifying business requirements. If business logic relies on no new rows appearing in a range until the transaction completes, choose an appropriate protection mechanism.

## 7. Execution plans determine scan scope

The `WHERE` clause describes which rows to find, while the execution plan tells you which index InnoDB uses to access the data and how many records it must scan. Lock scope is tied to the actual access path.

For example, the composite index `(status, created_at)` matches the predicates:

```sql
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-11-08'
```

Column order in an index matters. With only the `(status, created_at)` index, a query filtering solely on `created_at` without constraining `status` may not leverage the leading part of the index effectively. In that case, the engine may have to scan many more records.

Inspect the plan before running a locking read on a large table:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
FOR UPDATE;
```

Pay attention to `type`, `key`, `key_len`, `rows`, and `Extra`. `key` shows the selected index; `rows` is an estimate of rows to read, not the exact number of rows guaranteed to be locked. If you see `type = ALL` on a large table, the query may have to scan a massive number of records. After adding or changing an index, re-run `EXPLAIN` to confirm the access path.

Design principles:

1. Use primary keys or unique indexes for operations that need to lock a specific entity.
2. For range queries, create composite indexes ordered to align with filter predicates and sort orders.
3. Avoid wrapping search columns in functions if doing so prevents index usage; when needed, consider generated columns or appropriate indexes.
4. Use `FOR UPDATE` only when protecting data for a subsequent write step; reporting queries should normally use consistent reads.
5. Keep transactions short to release record/gap locks early.

## 8. Viewing held locks and waiting transactions

MySQL 8.0 exposes InnoDB lock information in Performance Schema. You can view locks in the current schema with:

```sql
SELECT OBJECT_SCHEMA,
       OBJECT_NAME,
       INDEX_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS,
       LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE();
```

To inspect relationships between waiting transactions and blocking transactions:

```sql
SELECT waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
       waiting.OBJECT_NAME,
       waiting.INDEX_NAME,
       waiting.LOCK_MODE AS waiting_lock_mode,
       blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
       blocking.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting
  ON waiting.ENGINE = waits.ENGINE
 AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

These tables require appropriate Performance Schema read privileges. You can combine this with `SHOW ENGINE INNODB STATUS` to inspect transaction details, the latest deadlock, and engine status. When analyzing, cross-reference `INDEX_NAME`, `LOCK_MODE`, `LOCK_DATA`, running queries, and execution plans; never rely solely on the statement name.

## 9. Common design mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Updating a single code yet another transaction is still blocked | Predicate does not use the full unique index or the plan scans broadly | Inspect `EXPLAIN`, predicates, and indexes |
| Insert waits even though no row has a duplicate key | A gap/next-key lock is protecting the insertion position | Identify the range-locking transaction and isolation level |
| More rows locked than returned | Engine scans extra index records to evaluate predicates | Narrow the access path with a suitable index |
| A query by status causes heavy contention | Status column has low cardinality and the index is unselective | Combine with another filter column in a composite index |
| Transactions wait for a long time | Another transaction holds locks too long or a query locks a large range | Find the blocker, shorten transactions, batch work |
| Deadlocks appear when multiple workers process the same dataset | Transactions lock rows in different orders | Access in a consistent order, handle retries on deadlock |

## 10. Practice exercises

Using the `orders` table from section 2, perform the following tasks across two independent MySQL sessions:

1. Run `EXPLAIN` for `WHERE external_ref = 'EXT-2026-001' FOR UPDATE`. Identify the chosen index and access type.
2. Open transaction A and lock an order by `external_ref`. From session B, update the same order and then update a different order. Record which operation must wait.
3. Write a range query on `status` and `created_at`. Use `EXPLAIN` to confirm the `(status, created_at)` index is selected.
4. In transaction A, run the range query with `FOR UPDATE`. From session B, try inserting a row inside the range and a row outside the range. Compare wait behavior.
5. Repeat the experiment under `READ COMMITTED`. Record the changes in gap lock behavior.
6. Query `performance_schema.data_locks` and `data_lock_waits` to identify the index, lock modes, and blocking transaction.

## Key takeaways

- A unique point lookup locks narrowly only when the predicate uses the full unique key and finds a record; do not apply this mechanically to partial composite keys or nonexistent keys.
- Range scans under `REPEATABLE READ` typically use next-key locks to protect records and related gaps.
- The `WHERE` condition alone is not enough to predict lock scope; you must know the index and execution plan InnoDB actually uses.
- `READ COMMITTED` generally reduces gap locking for normal searches/scans, but does not eliminate all types of gap locks.
- Use `EXPLAIN`, Performance Schema, and short transactions to control lock contention.
