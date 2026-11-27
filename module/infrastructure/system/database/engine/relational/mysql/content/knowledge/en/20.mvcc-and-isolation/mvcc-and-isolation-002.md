# Undo Records, Row Versions, and Read Views in InnoDB

InnoDB uses **Multi-Version Concurrency Control (MVCC)** so multiple transactions can read the same data set while other transactions are updating it. Instead of forcing every `SELECT` statement to wait for a write lock, InnoDB can return the row version matching the transaction's point-in-time view of the data. This mechanism relies on three interconnected components: **undo records** store the information needed to restore older versions, **row versions** represent the different states of a row, and **read views** determine which versions a consistent read is allowed to see.

This lesson is part of the **MVCC and Isolation Levels** section for MySQL. You will trace how InnoDB creates and reads row versions, understand why two `SELECT` statements can return different results at different isolation levels, and recognize the impact of long-running transactions on the purge process.

## 1. Why Does InnoDB Need Multiple Versions of a Row?

Suppose the `accounts` table has one row:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES (1, 'An', 1000.00);
```

Transaction A starts reading the balance. At the same time, transaction B updates the balance from `1000.00` to `800.00` and commits. If A requires a stable snapshot, A must still see `1000.00` according to its snapshot, even though the new value has been committed. If A always read the latest value directly from the data page, repeated read results within the same snapshot could change unexpectedly.

MVCC solves this by allowing InnoDB to reconstruct an older version from the undo log when the current version does not match the read statement's read view. New data can still be written and committed while a consistent read is reading an older version.

MVCC does not mean every operation is lock-free. `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE`, and `SELECT ... FOR SHARE` statements still use locking mechanisms to protect current reads or data writes. MVCC primarily allows ordinary consistent reads to avoid locking rows just to read them.

## 2. Undo Log and Undo Records

The undo log is the storage area InnoDB uses to undo changes and support reconstructing previous data versions. An undo log contains **undo records**. The exact contents depend on the operation type, but for a row update, an undo record holds the information required to restore old values and traverse version history.

You can distinguish two important undo categories:

- **Insert undo** is created when inserting a row and primarily serves rollbacks if the transaction has not yet committed. Once the inserting transaction has committed, the inserted version does not need an older version for a consistent read to restore.
- **Update undo** is created when updating or delete-marking a row. It may need to be retained after commit because other transactions still hold read views that need to see the pre-change version.

Example:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = 800.00
WHERE account_id = 1;

-- If the transaction has not committed yet, changes can be undone:
ROLLBACK;
```

When `UPDATE` executes, InnoDB must have enough information to restore the previous value if the transaction rolls back. If the transaction commits, the update undo record may still serve consistent reads of other transactions. Therefore, **committing does not mean all undo records are immediately deleted**.

Undo and redo serve different purposes:

| Component | Primary Purpose | Usage |
| --- | --- | --- |
| Undo log | Undo uncommitted changes and reconstruct older versions for MVCC. | Transaction rollback; serving consistent reads and version history. |
| Redo log | Recover logged data page changes if the server crashes. | Crash recovery to bring pages back to a consistent state after restart. |
| Binary log | Record change events at the logical or row level depending on configuration. | Replication and point-in-time recovery combined with backups. |

Do not treat undo as a backup. Undo serves InnoDB's internal operations and is purged when no longer needed; it does not replace a backup and data recovery strategy.

## 3. How Are Row Versions Stored and Linked?

In InnoDB's clustered index, each record has internal system fields to manage versioning. Two fields important to MVCC are:

- `DB_TRX_ID`: the transaction ID of the most recent transaction that inserted or modified the record.
- `DB_ROLL_PTR`: a pointer to the related undo record, allowing InnoDB to locate the previous version.

If a table has neither a suitable primary key nor a suitable unique key to serve as the clustered index, InnoDB can generate an internal row ID (`DB_ROW_ID`). This is a storage organization detail; applications should declare an explicit primary key.

Imagine a row `accounts.account_id = 1` updated multiple times:

```text
Clustered index: current version
  balance = 700.00
  DB_TRX_ID = most recent updating transaction
  DB_ROLL_PTR -----------------------------+
                                            |
                                            v
Undo record: previous version               |
  balance = 800.00                          |
  pointer to older undo record -------------+
                                            |
                                            v
Undo record: older version
  balance = 1000.00
```

This diagram only illustrates the concept of a version chain. InnoDB uses internal undo structures to reconstruct the required values; each version is not a full copy of the entire row stored as an independent record in the clustered index.

When a consistent read needs an older version, InnoDB checks the transaction ID of the current record. If the transaction that created that version is not visible in the read view, InnoDB follows `DB_ROLL_PTR`, applies the undo record to reconstruct the previous version, and continues checking until it finds a visible version or determines the row does not exist in the snapshot.

### How UPDATE and DELETE Create Versions

For `UPDATE`, InnoDB records the old information in the undo log, then updates the current record along with its transaction info and version pointer. An older consistent read can use undo to see the pre-update value.

For `DELETE`, InnoDB typically marks the record as deleted (delete-mark) rather than immediately removing the record physically from the index structure. Undo retains the information needed so transactions with an older snapshot can still see the row. When no read view needs the older version anymore, purge can then clean up the delete-marked data and no-longer-needed undo records.

This explains why a row deleted and committed by another transaction can still appear in the consistent read results of a transaction holding an older snapshot.

## 4. What Is a Read View?

A **read view** is the set of information InnoDB creates to determine which transactions committed early enough and which versions are allowed to appear in a consistent read. You can think of it as a snapshot of transaction states at a point in time.

Conceptually, a read view tracks:

- The transaction ID of the transaction creating the read view, so the transaction sees its own changes.
- The set of active transaction IDs at the time the read view is created.
- Transaction ID boundary markers to distinguish transactions that finished before the snapshot from transactions that started after the snapshot.

When checking a row version, InnoDB evaluates the transaction that created that version:

1. Changes created by the current transaction itself are visible to that transaction.
2. Versions created by transactions that committed before the read view was created can be seen.
3. Versions created by transactions still active when the read view was created are not visible, even if those transactions commit after the snapshot time.
4. Versions created by transactions assigned a transaction ID past the read view's boundary do not belong to that snapshot. This can also happen when a transaction opened before the snapshot but only performed a write operation and received a transaction ID after the snapshot.

For cases falling between the two boundary markers, InnoDB uses the list of active transactions stored in the read view to determine whether the transaction that created the version had finished before the snapshot or was still active when the snapshot was created. If the current version is not visible, InnoDB traverses undo to find an older version.

A read view is not a separate copy of data stored for each `SELECT` statement. It is visibility metadata about transactions; older data is reconstructed from undo when needed.

## 5. When Does InnoDB Create a Read View?

When a read view is created depends on the isolation level and the type of read statement. For ordinary consistent reads in InnoDB:

| Isolation Level | Consistent Read Behavior |
| --- | --- |
| `READ COMMITTED` | Each consistent read creates a new read view. Two `SELECT` statements in the same transaction can see new commits occurring between the two statements. |
| `REPEATABLE READ` | Consistent reads within the same transaction use the same read view, typically created at the first consistent read. |
| `READ UNCOMMITTED` | Does not provide consistent snapshot guarantees like the two levels above; a transaction can read uncommitted changes from other transactions. |
| `SERIALIZABLE` | InnoDB applies stricter locking behavior; how `SELECT` is handled depends on transaction/autocommit mode. It should not be treated as an ordinary consistent read level. |

Under `REPEATABLE READ`, an ordinary `START TRANSACTION` statement does not necessarily create a read view right away. The read view is typically created when the transaction runs its first consistent read. If you need to establish a snapshot immediately upon starting the transaction, you can use `START TRANSACTION WITH CONSISTENT SNAPSHOT` under appropriate conditions, specifically with InnoDB at `REPEATABLE READ`.

Example of checking the current isolation level in MySQL 8.0:

```sql
SELECT @@transaction_isolation;
```

Setting the isolation level for the session before starting a transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

This setting applies to subsequent transactions in the session. If you want to change the scope for a single specific transaction, you can use `SET TRANSACTION ISOLATION LEVEL ...` before starting that transaction.

## 6. Experiment: REPEATABLE READ Keeps the Same Read View

Prepare the data:

```sql
CREATE TABLE inventory (
    product_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (product_id, quantity)
VALUES (10, 50);
```

Open two MySQL sessions. Ensure session A is using `REPEATABLE READ`.

**Session A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Result: 50. The read view is created at this consistent read.
```

**Session B**

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 40
WHERE product_id = 10;

COMMIT;
```

Back in session A:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Still sees: 50, because the consistent read uses the existing read view.
```

Session A does not yet see the `40` version created by transaction B after A's read view was established. Undo records allow InnoDB to reconstruct the value `50`.

End transaction A and read again:

```sql
COMMIT;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Result: 40 in a new transaction/autocommit.
```

Once transaction A ends, the old read view is no longer held by that transaction. A new transaction creates a new snapshot and can see B's committed change.

## 7. Experiment: READ COMMITTED Creates a New Read View per Read Statement

Keep the data at `quantity = 50` before running the experiment. Set session A to `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Initial result: 50.
```

In session B, update and commit:

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 40
WHERE product_id = 10;

COMMIT;
```

Session A reads again:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Result: 40, because this SELECT statement creates a new read view.
```

With `READ COMMITTED`, transaction A can see new commits between two consistent reads. This reduces the likelihood of holding old versions for long, but applications cannot assume all reads within a single transaction observe the same snapshot.

## 8. Consistent Read vs. Current Read

A very important point when working with MVCC is distinguishing a **consistent read** from a **current read**.

| Read Type | Examples | Data Read |
| --- | --- | --- |
| Consistent read | Plain `SELECT ...` at an isolation level supporting consistent reads | The version matching the transaction's read view. Typically does not place locks on rows solely for reading. |
| Locking current read | `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE` | The current version suitable for locking and coordinating with write transactions; may have to wait for other transactions to release locks. |
| Write operation | `UPDATE`, `DELETE`, and row reads serving write operations | Uses the current read/locking mechanisms needed to locate and modify rows. |

For example, when session A under `REPEATABLE READ` has already created a read view and still sees `quantity = 50`, session B updates it to `40` and commits. A subsequent plain `SELECT` in A can still return `50`, whereas a locking read such as `SELECT ... FOR UPDATE` is intended to read the current version and lock the row for a safe update. The two reads can therefore return different results in the same transaction.

```sql
-- Consistent read: follows the transaction's read view
SELECT quantity
FROM inventory
WHERE product_id = 10;

-- Current read: reads the current version and locks the row
SELECT quantity
FROM inventory
WHERE product_id = 10
FOR UPDATE;
```

`FOR SHARE` acquires a shared lock to protect the row from conflicting updates/deletes while the transaction holds the lock. `FOR UPDATE` acquires an exclusive lock suitable for a read-then-update flow. Locking reads can wait, deadlock, or encounter lock wait timeouts; MVCC does not eliminate those situations.

Do not use a plain `SELECT` to check a balance and assume that value remains unchanged when a subsequent `UPDATE` runs. If business logic needs to read and modify a row as a coordinated operation, consider locking reads, conditional `UPDATE` statements, constraints, and checking the number of affected rows.

## 9. Purge: When Are Old Versions Cleaned Up?

Undo records needed for rollbacks or active read views must be retained. When no transaction can possibly need an older version anymore, InnoDB's **purge** process can clean up expired undo history and delete-marked records that are no longer needed.

High-level workflow:

1. A transaction updates or deletes a row; InnoDB writes an undo record and links the version history.
2. The transaction commits; the new version becomes the committed version.
3. Another transaction with an older read view may still need the previous version.
4. When the older read view ends and no snapshot needs that undo record anymore, purge can reclaim the history that is no longer useful.

Therefore, a long-running read transaction can hold a read view for a long time and prevent purge from removing older versions that the snapshot might need. If the system continuously writes or deletes data while an old read view exists, the amount of undo history awaiting purge can grow, increasing storage pressure and processing overhead.

### Signs and How to Inspect

You can view active InnoDB transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

To inspect more internal InnoDB state, you can run:

```sql
SHOW ENGINE INNODB STATUS\G
```

In the output, the TRANSACTIONS section and history list information can help identify long-lived transactions and the amount of undo history awaiting purge. `History list length` is an indicator of the undo history backlog needing processing; do not interpret it as an exact count of deleted rows or row versions.

When you suspect a long transaction is slowing purge, inspect the transaction start time, the session owning it, the running query, and its business purpose. Only terminate a transaction after assessing the impact on the application. Optimization usually starts with keeping transactions short, avoiding opening a transaction and then waiting on users or external services, and ensuring every execution branch commits or rolls back.

## 10. Common Misconceptions

- **Assuming commit immediately deletes undo records.** Update undo may still be needed for active snapshots; purge cleans up after it is safe.
- **Assuming every `SELECT` in a transaction uses the same snapshot.** This holds for consistent reads under `REPEATABLE READ`, but under `READ COMMITTED` each consistent read gets a new read view.
- **Assuming `SELECT ... FOR UPDATE` also reads the old snapshot.** A locking read is a current read, intended to read the current version and lock the row.
- **Assuming MVCC does not use locks.** MVCC supports consistent reads; write operations and locking reads still require locks.
- **Confusing undo with redo.** Undo serves rollbacks and old versions; redo serves crash recovery.
- **Assuming long transactions only hold connections.** An old read view can also block purge and cause undo history to grow.
- **Assuming DELETE immediately removes the record physically.** InnoDB can delete-mark first; purge handles physical removal when old versions are no longer needed.

## 11. Self-Check Exercises

1. A transaction under `REPEATABLE READ` has already run its first `SELECT`. Another transaction updates the row and commits. Why can the second plain `SELECT` still return the old value?
2. Given the same scenario, if the reading session uses `READ COMMITTED`, how can the result of the second read change?
3. What tasks do undo records support? Why might update undo need to persist after commit?
4. What roles do `DB_TRX_ID` and `DB_ROLL_PTR` play in tracing row versions?
5. Why can a row that has been deleted and committed still appear in another transaction's consistent read?
6. Distinguish a consistent read from `SELECT ... FOR UPDATE`.
7. What impact can a read transaction kept open for many hours have on purge while the system continuously writes/deletes data?
8. Why cannot `History list length` be interpreted directly as the number of deleted rows?

When answering, describe the sequence: **transaction modifies row → undo record saves previous state → read view checks version-creating transaction → InnoDB selects matching version → purge reclaims history when no snapshot needs it**. This sequence is the foundation for explaining InnoDB's consistent read behavior and the relationship between MVCC and transaction isolation levels.
