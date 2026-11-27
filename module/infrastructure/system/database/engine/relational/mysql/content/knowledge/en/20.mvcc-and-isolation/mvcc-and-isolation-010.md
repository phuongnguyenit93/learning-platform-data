# MVCC and Isolation Levels

## Differences Between Ordinary SELECT and UPDATE/DELETE in the Same Transaction

In InnoDB, an ordinary `SELECT` statement and an `UPDATE` or `DELETE` statement can see different versions of data even when running inside the same transaction. A nonlocking `SELECT` is typically a *consistent read*: it reads a snapshot of the data via MVCC. `UPDATE` and `DELETE` are locking read operations (*current/locking reads*): they need to evaluate the current version of rows to decide which rows to modify or delete and to hold appropriate locks.

This difference is especially important at the default `REPEATABLE READ` isolation level. A transaction can repeatedly read the same result using `SELECT`, and immediately afterward update or delete additional rows that the initial snapshot did not display. Understanding both read modes helps avoid wrong assumptions about affected row counts, prevent unexpected data overwrites, and design safe transactions under concurrent sessions.

### 1. Two Ways to Read Data in InnoDB

InnoDB uses MVCC (Multi-Version Concurrency Control) to maintain row versions. Undo information helps reconstruct older versions matching the snapshot a transaction is reading. Consequently, a nonlocking `SELECT` can typically read consistent data without waiting for another transaction to release write locks on the same rows.

| Characteristic | Ordinary `SELECT` | `UPDATE` / `DELETE` |
| --- | --- | --- |
| Read mode | Consistent read, does not lock rows solely for reading | Current/locking read to locate and modify rows |
| Version evaluated | Version matching the transaction or statement read view | Current committed version, plus changes made by the transaction itself |
| Purpose | Read a consistent snapshot | Evaluate conditions on current data, then lock and modify/delete |
| Write locks | Does not acquire row locks just for reading | Acquires locks on the necessary records and index ranges |
| Can see new commits from other transactions? | Depends on the read view and isolation level | Can see the latest version when executing the operation |

`UPDATE` and `DELETE` do not simply take a list of rows from a preceding `SELECT`'s result. They locate rows themselves according to the statement's conditions and use locking read mechanisms. Therefore, two statements within the same transaction can observe different sets of rows.

### 2. How Does an Ordinary SELECT Create a Read View?

Under `REPEATABLE READ`, InnoDB's default isolation level, the read view for consistent reads in a transaction is typically created at the first consistent read. Subsequent ordinary `SELECT`s in the transaction use that same read view. Commits from other transactions after this point do not appear in subsequent consistent reads of the open transaction.

Under `READ COMMITTED`, each ordinary consistent read creates a new read view at the start of the statement. Therefore, two `SELECT` statements in the same transaction can see commits completed between the two statements. This reduces repeated reads of the same snapshot, but also means results of consecutive reads can differ.

| InnoDB Isolation Level | When Consistent Read Takes Snapshot | Two Ordinary `SELECT`s in the Same Transaction |
| --- | --- | --- |
| `READ UNCOMMITTED` | Does not guarantee snapshot-based consistent reads like higher levels; can read uncommitted data | Can read uncommitted data and produce inconsistent results |
| `READ COMMITTED` | Each consistent read statement | Can see new commits between two statements |
| `REPEATABLE READ` | Typically at the transaction's first consistent read | Continues reading the same snapshot within the transaction |
| `SERIALIZABLE` | When an explicit transaction is running, `SELECT` is typically converted to a shared-lock locking read | Read operations participate in locking to enforce stricter isolation |

`START TRANSACTION` under `REPEATABLE READ` does not necessarily create a read view at the exact time the statement runs. The snapshot is typically established when the transaction performs its first consistent read. If you need to create a consistent snapshot immediately upon starting the transaction, MySQL supports `START TRANSACTION WITH CONSISTENT SNAPSHOT` under appropriate conditions.

### 3. UPDATE and DELETE Read the Current Version

`UPDATE` and `DELETE` statements need to know what values rows currently hold before writing changes. Therefore, they use current reads and lock the affected rows. If another transaction holds a write lock on a row that needs updating, the statement may have to wait. Once the lock is released, the operation proceeds on the current state according to InnoDB's rules, and the `WHERE` condition is applied to the rows the statement processes.

For example, suppose an inventory table:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (id, sku, quantity)
VALUES (1, 'KB-100', 10);
```

Under `REPEATABLE READ`, execute across the following two sessions.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1;
-- Result: 10. Consistent read creates Session A's read view.
```

**Session B:**

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 7
WHERE id = 1;

COMMIT;
```

**Back in Session A:**

```sql
SELECT quantity
FROM inventory
WHERE id = 1;
-- Still reads 10 from the old read view.

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1;

SELECT quantity
FROM inventory
WHERE id = 1;
-- Reads Session A's own change: 6.

COMMIT;
```

Session A's first and second `SELECT`s use the old snapshot and therefore still see `10`. However, `UPDATE` uses the current version committed by Session B, which is `7`, and decrements it to `6`. The `SELECT` after `UPDATE` sees transaction A's own change. This result avoids blindly overwriting `7` with `9` based on the old snapshot.

This example shows a transaction can observe `10` with a consistent read while its update operation computes on the current value `7`. Do not treat every statement in a transaction as reading the exact same version of data.

### 4. A SELECT Does Not See a New Row, Yet UPDATE Can Still Affect That Row

The difference does not occur only with values of an existing row. It can also happen with a new row inserted by another transaction after the current transaction's read view was created.

Suppose a job queue table:

```sql
CREATE TABLE job_queue (
    id BIGINT PRIMARY KEY,
    state VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE = InnoDB;

INSERT INTO job_queue (id, state, created_at)
VALUES (1, 'pending', '2026-11-01 09:00:00');
```

**Session A under `REPEATABLE READ`:**

```sql
START TRANSACTION;

SELECT id
FROM job_queue
WHERE state = 'pending'
ORDER BY id;
-- Only sees id = 1; read view is created.
```

**Session B inserts and commits a new row:**

```sql
INSERT INTO job_queue (id, state, created_at)
VALUES (2, 'pending', '2026-11-01 09:01:00');
COMMIT;
```

**Session A continues:**

```sql
SELECT id
FROM job_queue
WHERE state = 'pending'
ORDER BY id;
-- Still only sees id = 1 in the old snapshot.

UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending';
-- Can update both id = 1 and id = 2.

SELECT id, state
FROM job_queue
ORDER BY id;
-- Session A sees the changes it made itself.

COMMIT;
```

The `UPDATE` statement searches for rows by their current state and can affect row `id = 2` which the earlier consistent read did not display. This is a consequence of `UPDATE` using a current read. Do not infer the number of modified rows from an earlier nonlocking `SELECT`, even when both statements are inside the same `REPEATABLE READ` transaction.

This example assumes no other transaction holds a conflicting lock and the new row committed before `UPDATE` started. In a real system, results and wait times also depend on locks, execution order, and query conditions.

### 5. Visibility of the Transaction's Own Changes

A consistent read does not merely read an old snapshot mechanically. InnoDB always lets a transaction see the changes made by that transaction itself. Therefore, if a transaction updates a row and then reads it again with an ordinary `SELECT`, it sees the new value of the modified row, while other rows can still be read from the old snapshot.

Example:

```sql
START TRANSACTION;

SELECT id, quantity
FROM inventory
ORDER BY id;

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1;

SELECT id, quantity
FROM inventory
ORDER BY id;
-- Sees the new quantity for id = 1 modified by the current transaction.

COMMIT;
```

When there are multiple concurrent transactions, the final result can be a mix: rows modified by the current transaction are read at its own new versions, while other rows are read according to the old read view. That is why you should not use a snapshot `SELECT` to infer that all data the transaction operates on belongs to the same current point in time.

### 6. SELECT ... FOR UPDATE and FOR SHARE Are Locking Reads

When an application needs to read a row and then decide to update that row, it can use a locking read to synchronize the read with the write. Two common forms:

- `SELECT ... FOR UPDATE`: acquires exclusive locks on the read rows/index records, suitable when the transaction intends to modify or delete them.
- `SELECT ... FOR SHARE`: acquires shared locks, allowing other transactions to also perform shared-locking reads while preventing conflicting changes until the transaction ends.

Example of checking and deducting inventory in one transaction:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity >= 1;

COMMIT;
```

`FOR UPDATE` locks the found row so another transaction cannot concurrently modify it in a conflicting way before the current transaction ends. The application still must check the affected row count of `UPDATE`; if no rows were updated, stock may be depleted or the condition may no longer hold.

Another approach is combining the condition into an atomic update statement:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity >= 1;
```

Then check the number of affected rows to know whether inventory was deducted. This approach is often simpler when no extra information needs to be read between the check and update steps.

If `autocommit=1`, a locking read's lock is released when the statement ends. To hold locks across multiple statements, place them inside an explicit transaction and end with `COMMIT` or `ROLLBACK`.

### 7. How Does Isolation Level Affect UPDATE and DELETE?

`UPDATE` and `DELETE` statements still must read and lock current data across common isolation levels. The major differences between `READ COMMITTED` and `REPEATABLE READ` lie in consistent reads and range lock scope (gap/next-key locks).

| Characteristic | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| Ordinary `SELECT` | Fresh snapshot for each statement | Uses the same read view in the transaction after the first consistent read |
| `UPDATE` / `DELETE` | Uses current read to locate and modify rows | Uses current read to locate and modify rows |
| Range locking | Typically does not lock gaps for ordinary searches; exceptions remain such as foreign key and duplicate checks | Can use next-key locks to protect scanned index ranges |
| Consequence when another transaction inserts a new row | The next `SELECT` can see the new row; DML still evaluates current data | Ordinary `SELECT` may not see the new row in its snapshot, while DML can evaluate that row |

Under `READ COMMITTED`, InnoDB can use a *semi-consistent read* during some `UPDATE` operations: if a row is locked by another transaction, MySQL can use the latest committed version to evaluate the `WHERE` condition; if the row matches, it re-reads and acquires the necessary lock once it can proceed. This is an internal optimization detail and should not be treated as a substitute for explicit transactions or locks.

Under `REPEATABLE READ`, next-key locks combining record and gap locks can prevent other transactions from inserting into an index range that the statement is scanning. Lock scope depends on indexes and access plans, not just how the `WHERE` clause is written. A broad range-scanning query can lock more records or gaps than expected.

### 8. Locks Depend on Indexes and Search Conditions

InnoDB typically locks the index records that a statement finds or scans to execute the operation. If the condition uses a primary key or unique index with a single unique value, the lock scope is usually narrow. If the condition lacks a suitable index, InnoDB may have to scan and lock more records, increasing contention and deadlock risk.

For example, if you frequently process a job queue by state and creation time:

```sql
CREATE INDEX idx_job_queue_state_created
    ON job_queue (state, created_at, id);

UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending'
  AND created_at < CURRENT_TIMESTAMP;
```

The `(state, created_at, id)` index can help locate the range needing processing more efficiently. However, the statement can still lock many matching pending rows; an index does not automatically cap the row count or ensure only one worker handles a job. To batch work and coordinate multiple workers, you need a claim strategy, atomic update conditions, or appropriate locking reads.

You can use `EXPLAIN` to inspect the expected access path:

```sql
EXPLAIN
UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending'
  AND created_at < CURRENT_TIMESTAMP;
```

Observe `key`, `type`, estimated row count, and scan range. If the statement reads too many rows, review indexes, conditions, and batching. `EXPLAIN` shows the planned execution; when investigating actual load or locks, combine runtime metrics and lock-wait information.

### 9. Practical Rules to Avoid Read and Write Bugs

1. If you only need to read a consistent report, use an ordinary `SELECT` and understand the snapshot of the active isolation level.
2. If you need to read a row and then update based on that exact value, consider `SELECT ... FOR UPDATE` inside an explicit transaction.
3. If you only need to perform a conditional modification, prefer putting the condition into an atomic `UPDATE` statement and checking the affected row count.
4. Do not use an ordinary `SELECT` result to predict with certainty the set of rows an `UPDATE` or `DELETE` will affect.
5. Create indexes aligned with filter conditions and access order to reduce the number of scanned/locked records.
6. Keep transactions short; commit or roll back early to release locks and reduce undo history.
7. Prepare to handle deadlocks and lock wait timeouts by rolling back the transaction properly and retrying the entire unit of work in a controlled manner.
8. When processing a queue with multiple workers, design an atomic claim mechanism; do not rely on a snapshot `SELECT` to distribute work.

### 10. Summary

An ordinary `SELECT` in InnoDB reads a snapshot via MVCC. Under `REPEATABLE READ`, the snapshot is typically retained across consistent reads within the transaction; under `READ COMMITTED`, each statement gets a fresh snapshot. `UPDATE` and `DELETE` use current reads with locks to operate on current data. Therefore, they can affect rows that an earlier `SELECT` did not see, while still showing the transaction its own changes. When you need to synchronize a read-then-write sequence, use a locking read or an atomic conditional DML statement, choose suitable indexes, and keep transactions short.
