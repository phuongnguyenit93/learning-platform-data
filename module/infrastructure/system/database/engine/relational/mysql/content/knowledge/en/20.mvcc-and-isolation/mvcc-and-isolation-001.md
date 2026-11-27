# How MVCC Resolves Concurrent Reads and Writes

In a database management system, multiple sessions can read and modify the same row of data. If every read operation had to wait for write operations to finish, the system would easily bottleneck under high concurrency. If data being modified were read directly without consistency rules, a query could observe an incomplete state or see results change between reads.

MySQL's InnoDB uses **Multi-Version Concurrency Control (MVCC)** to resolve most conflicts between ordinary reads and writes. Instead of forcing a read query to lock a row currently being updated, InnoDB can provide the query with a committed version matching its snapshot. Writes still use locks to protect changes; MVCC primarily allows consistent reads to avoid blocking writers and reading uncommitted data.

## Objectives

After this lesson, you will be able to:

- Explain why concurrent reads and writes require a consistency mechanism.
- Describe the role of undo logs, row versions, and read views in InnoDB's MVCC.
- Distinguish between a consistent read and a locking read (current read).
- Predict read results in transactions at the `READ COMMITTED` and `REPEATABLE READ` isolation levels.
- Recognize the limitations of MVCC, the impact of long-running transactions, and cases where locks are still required.

The examples assume tables use InnoDB and MySQL 8.0 or later syntax.

## 1. The Concurrent Read and Write Problem

Suppose the `inventory` table has one row:

| product_id | available |
|---:|---:|
| 10 | 8 |

One session is decreasing the available quantity from 8 to 6. While that transaction has not yet committed, another session runs an inventory report. The system needs to decide which value the report will see.

There are two important requirements:

- **No reading uncommitted data:** the reporting session must not see changes that the writing transaction might still roll back.
- **Consistent reads:** within the scope of its snapshot, a query needs to see a deterministic data state, rather than sometimes seeing the old value and sometimes seeing a partial new change.

An exclusive lock can protect the row being written, but if every read query had to wait for this lock, read and write operations would impede each other. MVCC adds another way to read: a read query retrieves an older version matching its snapshot while the writing transaction continues updating the current version.

## 2. How MVCC Stores and Finds Row Versions

### Current Version and Undo Log

When an InnoDB transaction updates a row, the engine records the change in the data and stores the information needed to reconstruct the previous version in the undo log. A record in the clustered index has internal system fields, including the transaction ID of the modification and a pointer to the undo record. You can visualize the version chain as follows:

```text
Older version                            Current version
available = 8  <--- undo chain <---      available = 6
                                      trx_id = T2
```

This is a conceptual model. The undo log is not simply a full copy of the entire table; it stores the information needed to undo changes or reconstruct older versions when a consistent read requires them.

When a query needs an older version, InnoDB follows the undo chain to reconstruct the appropriate value. An ordinary read query therefore does not need to require the writing transaction to release its row lock just to view the value prior to the update.

### Read View (Read Snapshot)

A read view describes the set of versions that a consistent read is allowed to see. When creating a read view, InnoDB records the state of active transactions along with transaction ID boundaries. When evaluating a version, the engine determines whether the transaction that created that version was already outside the snapshot, was still active at the time of the snapshot, or started after the snapshot.

Conceptually:

- A version committed before the snapshot time and not belonging to a transaction still active at that time can be seen.
- A version created by a transaction that was still active when the snapshot was taken will not be seen, even if that transaction commits later.
- A version created by a transaction that started after the snapshot does not belong to the snapshot and will also not be seen.
- A transaction always sees the changes it previously made itself, according to InnoDB's read rules.

A read view is not a physical copy of the entire database. It is a set of rules determining which versions are valid; older version data is reconstructed from undo when needed.

### When Old Versions Are Cleaned Up

An undo record is still needed as long as an open read view might need to use it. InnoDB's purge process only cleans up undo versions that are no longer needed by any transaction. Therefore, a long-running read transaction can hold onto an old snapshot and delay purge, causing accumulated undo history to grow.

## 3. Consistent Read: Reading a Snapshot Without Locking Rows

With InnoDB, an ordinary `SELECT` statement (without `FOR UPDATE` or `FOR SHARE`) is a consistent nonlocking read at isolation levels that support snapshots. It reads the version matching the read view and does not place row locks to prevent other transactions from updating that row.

For example, while session A reads `available = 8`, session B can update the row to 6 and commit. Session A's `SELECT` still reads version 8 if A's snapshot was created before B's change. Session B does not need to wait for A's ordinary read to finish.

This provides two benefits:

- **Reads do not block writes:** reports or ordinary lookup queries can read older versions while other transactions update the current version.
- **Writes do not alter an active read snapshot:** a transaction does not unexpectedly see another transaction's values appear between consistent reads belonging to the same snapshot.

A consistent read still acquires the metadata locks required for the statement and is still affected by other types of locks or operations. MVCC does not mean the entire database is lock-free.

## 4. Snapshot Creation Timing Depends on the Isolation Level

MVCC provides the versions to read; the isolation level determines when a read view is created and reused. In MySQL/InnoDB, the two commonly used levels are `READ COMMITTED` and `REPEATABLE READ`.

| Isolation Level | Consistent Read Snapshot | Main Consequence |
|---|---|---|
| `READ UNCOMMITTED` | Does not use consistent read snapshots in the manner of RC/RR; can read uncommitted data | Risk of dirty reads |
| `READ COMMITTED` | Each consistent read creates a new snapshot at the start of the statement | Can see new commits between two `SELECT` statements in the same transaction |
| `REPEATABLE READ` | Consistent reads in a transaction share the same read view; typically created at the first consistent read | Repeated reads with the same snapshot yield consistent results |
| `SERIALIZABLE` | When autocommit is disabled, ordinary `SELECT` statements are converted to locking reads using shared locks | Increases protection via locks and can cause reads/writes to wait on each other |

`REPEATABLE READ` is InnoDB's default level in MySQL. If you need to create a snapshot immediately when starting a transaction at this level, you can use `START TRANSACTION WITH CONSISTENT SNAPSHOT`. If you only use `START TRANSACTION`, the consistent read's read view is typically created when the first consistent read statement runs. The `WITH CONSISTENT SNAPSHOT` option only takes effect to create a consistent snapshot under `REPEATABLE READ`.

You can inspect and set the isolation level for a session before opening a transaction:

```sql
SELECT @@transaction_isolation;

SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
```

Do not change the isolation level mid-transaction expecting it to alter the current snapshot. Set it before starting the next transaction.

## 5. Two-Session Example Under REPEATABLE READ

Suppose `inventory(product_id, available)` uses InnoDB and currently has `product_id = 10`, `available = 8`.

**Session A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT available
FROM inventory
WHERE product_id = 10;
-- Result: 8. The first consistent read creates A's snapshot.
```

While A still has its transaction open, session B executes:

```sql
START TRANSACTION;

UPDATE inventory
SET available = available - 2
WHERE product_id = 10;

COMMIT;
-- The current committed value is 6.
```

Back in session A:

```sql
SELECT available
FROM inventory
WHERE product_id = 10;
-- Still 8: the consistent read uses A's existing snapshot.
```

When A needs to read the current version to decide on an update, A can request a locking read:

```sql
SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE;
-- Reads the current committed version (6) and locks the matching row.

COMMIT;
```

This example shows that the same transaction under `REPEATABLE READ` can receive two different results depending on the read type: an ordinary `SELECT` reads the snapshot, while `SELECT ... FOR UPDATE` reads the current version and places a lock. Choose the read type according to your business intent.

## 6. Consistent Read vs. Current Read

MVCC does not make every statement read a snapshot. Operations that need to decide on or modify the current state typically use current reads and locks.

| InnoDB Operation | Typical Read Mode | Row Locking |
|---|---|---|
| Plain `SELECT` | Consistent read based on read view | Does not lock rows just to read |
| `SELECT ... FOR SHARE` | Current/locking read | Places shared locks on the read records or ranges |
| `SELECT ... FOR UPDATE` | Current/locking read | Places exclusive locks appropriate for the read records or ranges |
| `UPDATE` | Reads the current version to locate and modify rows | Places write locks |
| `DELETE` | Reads the current version to locate and delete rows | Places write locks |

For range queries, InnoDB may lock relevant index records and gaps (next-key locks), depending on the isolation level, indexes, and query conditions. Therefore, do not assume a locking read only locks the exact rows ultimately returned.

Example of reading a balance to check it before deducting money:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 42
FOR UPDATE;

-- The application checks the balance and performs the appropriate update.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42
  AND balance >= 100;

COMMIT;
```

`FOR UPDATE` lets the reading session hold a write lock on the row until the transaction ends, ensuring other transactions cannot concurrently modify the row in a way that invalidates the decision based on the balance just read. The check condition right inside the `UPDATE` remains useful as an additional safeguard. The application must check the number of affected rows to know whether the operation actually deducted the funds.

If only a simple atomic transformation is needed, a single conditional statement is often cleaner than reading and computing in the application:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42
  AND balance >= 100;
```

Then check the number of changed rows. If no rows were updated, either the account does not exist or the balance condition was not met; the application can distinguish the two cases with an appropriate query inside the transaction.

## 7. MVCC Does Not Replace All Types of Locks

MVCC is optimized for consistent reads. Operations that need to guarantee write exclusivity or coordinate multiple transactions still require locking:

- Two transactions updating the same row must be serialized using write locks.
- `SELECT ... FOR UPDATE` is appropriate when an application reads a row and then makes a write decision based on the current value.
- `SELECT ... FOR SHARE` is appropriate when you need to read and hold a shared lock to protect data from being modified for the remainder of the transaction.
- Unique key and foreign key checks can use internal locks to protect constraints.
- DDL and metadata locks can cause queries to wait, even though consistent reads do not lock data rows.

Under `REPEATABLE READ`, an ordinary consistent read may not see rows inserted by another transaction after the snapshot time. However, locking reads and DML statements need to protect the current range using appropriate locking mechanisms. For range queries, next-key locks help prevent certain types of phantom inserts within the locked range. Do not equate the snapshot behavior of a plain `SELECT` with the locking behavior of `SELECT ... FOR UPDATE`.

## 8. Operational Cost and Long-Running Transactions

MVCC reduces wait times between reads and writes, but it must retain enough historical information to serve active snapshots. A long-running open transaction—even one that only ran a `SELECT` and left the connection idle—can hold onto an old read view. When that happens, purge cannot yet delete certain undo versions.

Potential consequences include:

- Undo history and history list length grow.
- Purge fails to keep up with the volume of changes, increasing background work.
- The tablespace containing undo requires additional storage.
- Queries must traverse longer version chains to reconstruct older values.

Ways to mitigate the impact:

1. Keep transactions short and commit or roll back immediately after completing the work.
2. Do not open a transaction before waiting for user interaction or external services.
3. For large reports, consider splitting them into ranges or scheduling times aligned with consistency requirements.
4. Monitor open transactions and InnoDB status when history list length grows abnormally.

You can inspect active InnoDB transactions with:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       trx_mysql_thread_id,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

To view additional engine status and undo/purge information, use:

```sql
SHOW ENGINE INNODB STATUS;
```

Do not draw conclusions from a single metric alone. Cross-reference transaction open duration, write load, purge rate, and undo storage trends.

## 9. Common Misconceptions

| Misconception | Reality |
|---|---|
| MVCC means InnoDB does not use locks | Writes, locking reads, constraint checks, and many other operations still require locks |
| Every `SELECT` sees the latest data | A consistent read may read an older snapshot; a locking read reads the current version |
| `REPEATABLE READ` always creates a snapshot right at `START TRANSACTION` | Typically the read view is created at the first consistent read; `WITH CONSISTENT SNAPSHOT` can be used to create it immediately |
| When another transaction commits, an existing snapshot automatically updates | A `REPEATABLE READ` read view remains fixed within the transaction |
| Undo log is only for rollbacks | Undo also helps reconstruct older versions for consistent reads |
| Read-only transactions do not affect purge | An old read view from a long-running read transaction can retain needed undo history |
| `SELECT ... FOR UPDATE` is like a plain `SELECT` but faster | It is a locking/current read that can wait and holds locks until the end of the transaction |

## 10. Practice Exercises

Assume both `inventory(product_id, available)` and `accounts(account_id, balance)` use InnoDB.

1. Simulate two sessions: A starts a transaction under `REPEATABLE READ` and reads inventory; B reduces inventory and commits. Predict the result of the next plain `SELECT` in A.
2. In transaction A from exercise 1, also run `SELECT ... FOR UPDATE`. Explain why the result can differ from the earlier consistent read.
3. Repeat the scenario under `READ COMMITTED`. Compare the results of the two plain `SELECT` statements within the same transaction.
4. Explain why a read-only transaction left open for a long time can still cause undo history to grow.
5. Write a conditional `UPDATE` statement to deduct 100 from an account when the balance is sufficient, then state how to confirm the update succeeded.
6. Open two transactions that update the same row and observe which transaction has to wait for a lock. Compare that behavior with a plain `SELECT`.

## Key Takeaways

- InnoDB's MVCC uses read views and undo versions to provide consistent data for consistent reads.
- An ordinary consistent read reads a snapshot and does not lock rows; write operations still use locks to protect changes.
- `READ COMMITTED` creates a new snapshot for each consistent read; `REPEATABLE READ` reuses the read view within the transaction.
- `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, `UPDATE`, and `DELETE` need to read the current state and may acquire locks.
- MVCC reduces read/write contention but does not eliminate locks; long-running transactions can block purge and cause undo history to accumulate.
