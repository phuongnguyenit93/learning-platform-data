# Consistent Read vs. Locking/Current Read

InnoDB has two important ways to read data within a transaction: **consistent read** (typically a plain `SELECT`) and **locking read/current read** (such as `SELECT ... FOR UPDATE` or `SELECT ... FOR SHARE`). The two read modes can return different data versions even within the exact same transaction, especially at the `REPEATABLE READ` isolation level.

A consistent read uses MVCC to read a snapshot without locking the data rows being read. A locking read reads the current version usable by InnoDB and places locks on the appropriate records/ranges to coordinate competing transactions. Choosing the wrong read type can cause race conditions, reading stale data when an update decision is needed, or holding locks longer than necessary.

This lesson focuses on InnoDB in MySQL 8.0 and later: how snapshots are created, the differences between `REPEATABLE READ` and `READ COMMITTED`, `FOR UPDATE`/`FOR SHARE` semantics, lock ranges, `NOWAIT`/`SKIP LOCKED`, and how to choose a read strategy for each unit of business work.

## 1. Two Read Modes Serving Different Goals

| Read Type | Typical Syntax | Data Version | Row Locking |
| --- | --- | --- | --- |
| Consistent read | Plain `SELECT ...` | Snapshot per isolation level | Does not place record/gap locks to protect read rows |
| Locking read | `SELECT ... FOR UPDATE` | Current version readable by a locking read | Places locks appropriate to the read mode and access path |
| Shared locking read | `SELECT ... FOR SHARE` | Current version readable by a locking read | Places shared locks on the read rows/ranges |
| Write DML | `UPDATE`, `DELETE` | Evaluates and operates on the current version | Acquires locks needed to modify data |

A plain `SELECT` is generally suited for reporting, display, or reading data from a snapshot. `SELECT ... FOR UPDATE` is suited when a transaction needs to read a row and safely update it based on that value. `FOR SHARE` is suited when you need to read and hold a shared lock to prevent other transactions from modifying or deleting the row for the remainder of the transaction.

Do not interpret "nonlocking consistent read" as meaning the statement uses no locks of any kind. It does not place record/gap locks like a locking read to protect data rows; the statement is still subject to other mechanisms such as metadata locks and server operational limits.

## 2. Consistent Read and MVCC

InnoDB uses MVCC (Multi-Version Concurrency Control) to retain the data versions needed by transactions reading snapshots. When a transaction updates a row, InnoDB records undo information so older versions can be reconstructed for matching consistent reads.

A plain `SELECT` inside a transaction can read the version committed as of the point when the snapshot was determined, rather than waiting for all transactions modifying the row to finish. As a result, many read queries can proceed while other transactions write data.

For example, an account has a balance of 500.00:

1. Transaction A reads the balance 500.00 using a consistent read.
2. Transaction B updates the balance to 450.00 and commits.
3. Transaction A reads again using a consistent read.

Under `REPEATABLE READ`, if A's snapshot was created in step 1, the second read can still see 500.00. This is intentional behavior: A continues reading from the same snapshot.

MVCC does not mean every transaction always sees the same value. The snapshot depends on the isolation level and when the read view was created. Locking reads and DML have different semantics from consistent reads.

## 3. When Is a Consistent Read's Snapshot Created?

At InnoDB's `REPEATABLE READ` level, plain consistent reads in the same transaction share the same read view. The read view is created on the transaction's first consistent read, rather than necessarily immediately upon executing `START TRANSACTION`.

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- No consistent read has occurred at START TRANSACTION time.
-- Another transaction may commit before this SELECT runs.
SELECT balance
FROM accounts
WHERE account_id = 101;

-- Subsequent consistent reads in the transaction share the same snapshot.
SELECT balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

If you need a consistent snapshot right from the beginning of the transaction before performing multiple read operations, you can use `START TRANSACTION WITH CONSISTENT SNAPSHOT` at an appropriate isolation level. This statement instructs InnoDB to create a consistent snapshot when starting the transaction; it does not turn locking reads into consistent reads and does not replace `FOR UPDATE` when locks are needed for updates.

In InnoDB, the `WITH CONSISTENT SNAPSHOT` option is meaningful at the `REPEATABLE READ` level. If the session uses another isolation level, MySQL does not create a snapshot this way; set the isolation level before starting the transaction if you need that snapshot behavior.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM orders;
SELECT SUM(total_amount) FROM orders;

COMMIT;
```

Both plain read queries in this transaction use the same snapshot, helping reporting reads remain consistent with one another.

## 4. REPEATABLE READ vs. READ COMMITTED

The most important difference for consistent reads is when the snapshot is taken:

| Isolation level | Consistent Read Snapshot |
| --- | --- |
| `REPEATABLE READ` | Consistent reads in the same transaction use the read view created at the first consistent read |
| `READ COMMITTED` | Each plain consistent read takes a fresh snapshot at the time the statement begins |

Suppose Transaction A runs two `SELECT` statements and between them, Transaction B updates and commits:

- Under `REPEATABLE READ`, A can see the same old value in both reads.
- Under `READ COMMITTED`, A's second `SELECT` can see the new value committed by B.

Checking and changing the isolation level in a session:

```sql
SELECT @@SESSION.transaction_isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Session changes affect subsequent transactions on that connection. With a connection pool, ensure each connection is initialized with the desired isolation level.

`READ COMMITTED` does not allow a consistent read to see uncommitted data. It simply refreshes the snapshot on each read statement, so a transaction can observe new commits between statements.

## 5. Locking Read: Reading the Current Version and Placing Locks

Locking reads are used when a transaction needs to protect the data it just read from conflicting changes before finishing its work.

Two main syntaxes in MySQL 8.0:

```sql
SELECT ... FOR UPDATE;
SELECT ... FOR SHARE;
```

- `FOR UPDATE` acquires an exclusive lock on the matching records/ranges. Other transactions cannot acquire conflicting locks to update or locking-read the same data until the lock is released.
- `FOR SHARE` acquires a shared lock. Multiple transactions can hold compatible shared locks simultaneously, but other transactions cannot modify or delete the row with an exclusive lock until the shared lock is released.

A locking read reads the current version usable by InnoDB, rather than falling back to an older consistent-read snapshot. If another transaction holds a conflicting lock, the statement may wait, return an error with `NOWAIT`, or skip locked rows with `SKIP LOCKED`.

Locks are held until the transaction's `COMMIT` or `ROLLBACK`. Therefore, a locking read only protects subsequent operations if they are within the same transaction and on the same connection.

## 6. FOR UPDATE: Reading in Preparation for an Update

Example of checking inventory before deducting quantity:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 501
FOR UPDATE;

-- The application checks that quantity is large enough and order quantity is valid.

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501
  AND quantity >= 2;

-- The application checks affected rows = 1; otherwise ROLLBACK.

COMMIT;
```

`FOR UPDATE` protects the inventory row while the application checks and updates it. Another transaction wanting to update the same row must wait or handle a lock-wait error. If the row does not exist, the locking read returns no rows; the gap lock scope can depend on isolation level, indexes, and search conditions.

If the logic only needs to deduct stock without returning the quantity to the application, a single conditional update statement is often more concise:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501
  AND quantity >= 2;
```

The application checks the number of affected rows. If 1, the stock deduction succeeded; if 0, the product does not exist or did not have sufficient quantity to meet the condition. In a real system, an additional query may be needed to distinguish the two causes. A conditional update makes the check and modification atomic within one statement.

## 7. FOR SHARE: Reading and Preventing Modification/Deletion During a Transaction

`FOR SHARE` acquires a shared lock to ensure the read row is not modified or deleted by another transaction before the current transaction finishes.

For example, checking a configuration status or limit before recording a related business event:

```sql
START TRANSACTION;

SELECT account_id, account_status, daily_limit
FROM accounts
WHERE account_id = 101
FOR SHARE;

-- The application verifies status and limit.
-- Other transactions cannot modify/delete this row while the shared lock is held.

INSERT INTO account_audit (account_id, action_name)
VALUES (101, 'CHECKED_FOR_OPERATION');

COMMIT;
```

`FOR SHARE` does not mean other transactions cannot read the row; a shared lock is compatible with other shared locks. It prevents operations requiring an exclusive lock, such as updates/deletes, until the current transaction ends.

If the transaction will later need to modify the exact row it just read, using `FOR UPDATE` from the start is usually clearer. Multiple transactions simultaneously acquiring shared locks and then both upgrading to exclusive locks can cause a deadlock.

## 8. Why Can Consistent Read and Current Read See Different Values?

Under `REPEATABLE READ`, a transaction can simultaneously see an older snapshot version via a plain `SELECT` and the current version via `SELECT ... FOR UPDATE`:

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Creates snapshot and reads balance 500.00
SELECT balance
FROM accounts
WHERE account_id = 101;

-- After Session B commits, this can still see 500.00
SELECT balance
FROM accounts
WHERE account_id = 101;

-- Locking/current read reads the current version, e.g. 450.00
SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

COMMIT;
```

**Session B, running between A's two reads:**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = 450.00
WHERE account_id = 101;

COMMIT;
```

The different results are not a data bug. The two statements use different read semantics: the plain `SELECT` uses A's snapshot; `FOR UPDATE` reads the current version and locks the row so A can decide its next operation.

When a transaction has modified a row itself, that transaction's own consistent read still sees its own changes (read-your-own-writes), combined with the snapshot-appropriate versions for other rows. Therefore, do not model a consistent read simply as "always returning old data"; it is a consistent view under MVCC rules that accounts for the transaction's own changes.

## 9. UPDATE and DELETE Are Also Current Reads

`UPDATE` and `DELETE` statements must locate the current rows to modify or delete them, so they use locking and current-version reading mechanisms appropriate for write operations. Do not assume they are restricted to the snapshot of an earlier consistent `SELECT`.

Example:

```sql
START TRANSACTION;

-- Consistent read may see quantity from the snapshot.
SELECT quantity
FROM inventory
WHERE product_id = 501;

-- UPDATE locates and locks the current row to write.
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501
  AND quantity > 0;

COMMIT;
```

If an application takes the value from the SELECT, computes the new number in memory, and overwrites it without proper conditions/locks, it can overwrite based on stale data. Prefer atomic updates like `quantity = quantity - 1` with conditions, or use `FOR UPDATE` when you need to read multiple fields before deciding.

## 10. Locking Reads Only Protect Within a Transaction

For locks to persist across multiple statements, an explicit transaction is required:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 501
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501;

COMMIT;
```

If `autocommit = 1` and `SELECT ... FOR UPDATE` runs as a standalone statement outside an explicit transaction, the statement's transaction ends immediately after the statement; the lock is not retained to protect a subsequent `UPDATE`.

Check:

```sql
SELECT @@SESSION.autocommit;
```

Do not disable autocommit globally just to use locking reads. Starting an explicit transaction for the unit of business work is usually much easier to control.

## 11. Lock Scope Depends on Indexes and Access Paths

InnoDB typically locks the index records scanned by a locking read or DML statement, along with any gaps required by the isolation level and conditions. Therefore, the lock scope is not necessarily limited to just the rows ultimately returned.

Example querying by a unique primary key:

```sql
SELECT *
FROM inventory
WHERE product_id = 501
FOR UPDATE;
```

If `product_id` is a unique index and exactly one row is found, InnoDB typically only needs a record lock for that row, without locking adjacent gaps as in a range scan.

Conversely, a range query:

```sql
SELECT *
FROM inventory
WHERE product_id BETWEEN 500 AND 520
FOR UPDATE;
```

Under `REPEATABLE READ`, InnoDB can use next-key locks (record locks combined with gap locks) on the scanned index records to prevent other transactions from inserting rows into the matching range. Under `READ COMMITTED`, gap locking is typically disabled for searches and ordinary index scans, except for cases such as foreign key and duplicate key checks.

If an appropriate index is missing, MySQL may have to scan more records, increasing lock count and contention risk. Good indexes not only make queries faster but also help narrow the range that needs locking. Inspect `EXPLAIN` and the indexes used when investigating lock waits.

## 12. NOWAIT and SKIP LOCKED

MySQL 8.0 supports the `NOWAIT` and `SKIP LOCKED` options for locking reads:

- `NOWAIT`: if a row that needs to be locked is held under a conflicting lock by another transaction, the statement returns an error immediately instead of waiting.
- `SKIP LOCKED`: skips rows currently held under conflicting locks and returns the remaining rows that can be locked.

Example using `NOWAIT`:

```sql
START TRANSACTION;

SELECT *
FROM inventory
WHERE product_id = 501
FOR UPDATE NOWAIT;

COMMIT;
```

If the row is locked by another transaction, the statement fails immediately. The application can return a busy notice or retry according to an appropriate policy.

Example using `SKIP LOCKED` for a job queue:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE status = 'ready'
ORDER BY priority DESC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- If a job is selected, update its status right inside the transaction.
UPDATE job_queue
SET status = 'running'
WHERE job_id = ?;

COMMIT;
```

Multiple workers can claim different jobs without waiting on a job locked by another worker. In a production system, you must check the number of selected rows, update status with proper conditions, and have a recovery mechanism for abandoned jobs if a worker crashes after committing.

`SKIP LOCKED` produces an inconsistent view of the data because locked rows are skipped. It is suitable for queues or work-distribution workloads, not for business queries that need to see the full set of rows such as balance or inventory reports.

## 13. Locking Clauses in Subqueries and Joins

Placing a locking clause in a query block applies locks according to the scope of that query block. A locking clause in an outer query does not automatically lock rows read inside an independent subquery.

Example:

```sql
-- Locks rows of t1; the subquery reading t2 is not automatically locked by the outer clause.
SELECT *
FROM t1
WHERE c1 = (SELECT c1 FROM t2)
FOR UPDATE;
```

If you need to lock rows read inside the subquery, you must place a locking clause in the corresponding subquery:

```sql
SELECT *
FROM t1
WHERE c1 = (
    SELECT c1
    FROM t2
    WHERE id = 10
    FOR UPDATE
)
FOR UPDATE;
```

When using joins, a locking clause can lock rows read from the involved tables according to MySQL's scope and rules. Verify exactly which tables need locking, the access paths, and the execution plan; avoid locking more broadly than required.

## 14. FOR SHARE and Lock-Upgrade Deadlock Risk

Two transactions can simultaneously read the same row using `FOR SHARE` because shared locks are compatible. However, if both subsequently try to update that row, each transaction needs an exclusive lock. Both may wait for the other transaction's lock, creating a deadlock.

Scenario simulation:

1. Session A runs `SELECT ... FOR SHARE` on row X.
2. Session B also runs `SELECT ... FOR SHARE` on row X.
3. Session A wants to `UPDATE` row X and needs an exclusive lock.
4. Session B also wants to `UPDATE` row X.
5. Both transactions can fall into a lock-upgrade wait deadlock.

If you know from the outset that a transaction will read and then update the same row, using `FOR UPDATE` is generally more appropriate. If you only need to ensure the row does not change during validation, `FOR SHARE` can be appropriate. Whichever option you choose, the application must still handle deadlocks.

## 15. Consistent Read Is Not a Locking Read: Choose by Goal

| Goal | Start With | Why |
| --- | --- | --- |
| Displaying lists or detail pages from a snapshot | Plain `SELECT` | No need to hold row locks just to read |
| Generating reports needing multiple queries on the same snapshot under RR | Consistent reads within one transaction | Read queries share the same read view |
| Reading a balance and deciding whether to deduct funds | `SELECT ... FOR UPDATE` or conditional UPDATE | Avoid making decisions on a row modified concurrently |
| Reading configuration and ensuring it is not altered during the transaction | `SELECT ... FOR SHARE` | Shared lock prevents conflicting updates/deletes |
| Multiple workers claiming different jobs | `FOR UPDATE SKIP LOCKED` | Skips jobs currently locked by other workers |
| Failing immediately if a resource is busy | `FOR UPDATE NOWAIT` | Does not wait on lock wait |
| Simple conditional update only | Single `UPDATE ... WHERE ...` | Checks and updates within the same statement |

Do not put `FOR UPDATE` on every SELECT. Unnecessary locks reduce concurrency, increase lock waits, and raise deadlock risk. Conversely, do not use consistent reads when read-modify-write logic needs to protect data from competing transactions.

## 16. Two-Session Experiment: Snapshot and Current Read

Create the test table:

```sql
CREATE TABLE mvcc_demo_accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO mvcc_demo_accounts (account_id, balance)
VALUES (1, 500.00);
```

Select `REPEATABLE READ` in both sessions.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Result: 500.00; snapshot is created.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 450.00
WHERE account_id = 1;

COMMIT;
```

**Back in Session A:**

```sql
-- Consistent read still sees the old snapshot.
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Result: 500.00

-- Current/locking read sees the current version and locks the row.
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;
-- Result: 450.00

COMMIT;
```

The experiment shows that the two read modes can return two different versions within the same transaction. After A commits, a new transaction will read the committed value of 450.00.

## 17. READ COMMITTED Experiment

Repeat the experiment above, but set Session A to `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
```

After Session B updates and commits, rerun the plain `SELECT` in A. The second read can see the new value because `READ COMMITTED` creates a new snapshot for each consistent read.

`FOR UPDATE` remains a locking read/current read; changing the isolation level does not turn it into a consistent snapshot read. The isolation level affects how InnoDB handles snapshots and range locking, but the purpose of a locking read remains reading and protecting the current version.

## 18. Common Errors and Misconceptions

| Misconception / Error | Reality | How to Handle |
| --- | --- | --- |
| Plain `SELECT` always reads the latest value | Under RR, it can read an older snapshot | Use current/locking read if the current value is needed for an update |
| Consistent read locks rows to prevent changes | It uses an MVCC snapshot and does not lock records/gaps like a locking read | Do not use plain SELECT to protect read-modify-write |
| `FOR UPDATE` only changes how results are returned | It acquires locks and can make other transactions wait | Scope properly, commit/roll back early |
| `FOR SHARE` blocks all transactions from reading the row | Shared locks are compatible with other shared locks | Understand shared/exclusive locks and upgrade risk |
| RR snapshot is created right at START TRANSACTION | Typically created at the first consistent read | Use `WITH CONSISTENT SNAPSHOT` if immediate snapshot creation is needed |
| READ COMMITTED allows dirty reads | It still never reads uncommitted data | Distinguish fresh snapshots from dirty reads |
| FOR UPDATE locks only the returned rows | Scanned index records/gaps may be within the lock range | Check indexes and EXPLAIN |
| FOR UPDATE works across multiple statements when autocommit is on | A standalone statement ends its transaction and releases locks | Use an explicit transaction on the same connection |
| Outer locking clause locks subqueries too | Nested query blocks need their own locking clause if rows there must be locked | Place the clause in the appropriate query block |
| SKIP LOCKED is a general-purpose way to read data | It skips locked rows and produces an inconsistent view | Use only for suitable queues/work distribution |

## 19. Checklist for Choosing Consistent Read vs. Locking Read

Before writing a query, determine:

1. Do you only need to read for display/reporting, or will the result be used for an update?
2. Do all read queries in the transaction need to see the same snapshot?
3. Do you need to read the current version after another transaction commits?
4. Do you need to prevent other transactions from modifying/deleting the row before you finish?
5. Is `FOR UPDATE` or `FOR SHARE` appropriate for your locking intent?
6. Can read-modify-write be replaced by a single conditional DML statement?
7. Do indexes limit the range of records/gaps being locked?
8. Does the transaction start and end on the same connection?
9. Do you need `NOWAIT` or `SKIP LOCKED`, and does the application handle errors/missing rows?
10. Are deadlocks, lock wait timeouts, and rollbacks handled before returning the connection to the pool?

## 20. Practice Exercises

1. Create the `mvcc_demo_accounts` table using InnoDB and insert an account with a balance of 500.00.
2. Open two sessions; in Session A use `REPEATABLE READ` and run a consistent SELECT to create a snapshot.
3. In Session B update the balance and commit; rerun the plain SELECT in A and record the value.
4. In A run `SELECT ... FOR UPDATE`; compare the current read value with the consistent read value.
5. Repeat with `READ COMMITTED`; observe that each consistent read gets a new snapshot.
6. Try `SELECT ... FOR SHARE` in two sessions, then try updating the same row to observe lock waits/lock upgrades.
7. Compare an equality query on a unique key with a range query under `REPEATABLE READ`; examine the effect of record/gap/next-key locks.
8. Run a locking read with `NOWAIT` while another session holds a lock; note the error the application must handle.
9. Create a `job_queue` table and use `FOR UPDATE SKIP LOCKED` from two workers to claim two distinct jobs.
10. Use `EXPLAIN` to inspect the indexes and access path of a locking query; evaluate the lock range that may be affected.

## 21. Key Takeaways

InnoDB's consistent read uses MVCC to read a snapshot and does not place record/gap locks to protect read rows. Under `REPEATABLE READ`, consistent reads in the same transaction typically use the read view created at the first consistent read; under `READ COMMITTED`, each consistent read gets a fresh snapshot. `START TRANSACTION WITH CONSISTENT SNAPSHOT` can create a snapshot immediately upon starting a transaction at a supported level.

`SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking/current reads: they read the current version usable by InnoDB and acquire appropriate exclusive/shared locks. Locks are held until commit/rollback and only protect subsequent operations within the same transaction on the same connection. `UPDATE`/`DELETE` also operate on the current version. Lock scope depends on indexes, access paths, and isolation level; range scans under RR can use next-key/gap locks. `NOWAIT` and `SKIP LOCKED` are useful for specific contention scenarios, though `SKIP LOCKED` is unsuitable for queries needing a complete, consistent view. Choose the read mode based on business goals, keep transactions short, and inspect execution plans/indexes when investigating lock waits.
