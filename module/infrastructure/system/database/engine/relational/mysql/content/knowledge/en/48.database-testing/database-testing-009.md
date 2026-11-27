# Testing Locks, Deadlocks, and Lost Updates with Multiple Connections

## Objectives

Concurrency bugs in MySQL often surface only when multiple transactions read or modify the same dataset simultaneously. An `UPDATE` statement that passes in isolation can wait on locks, trigger a deadlock, or overwrite another transaction's changes under concurrent execution. To verify behavior, open multiple independent connections, control statement ordering, and inspect lock state while transactions remain active.

This lesson belongs to the **DATABASE_MYSQL** module, focusing on table design, data types, locks, SQL, indexes, transactions, concurrency control, reading execution plans, query tuning, and operating relational databases. It guides you through building a multi-session lab to reproduce row locks, lock waits, deadlocks, and lost updates, then applying pessimistic locking, atomic updates, and optimistic locking to protect data integrity.

After this lesson, you will be able to:

- Open two or more independent MySQL connections to reproduce data contention.
- Distinguish blocking, lock wait timeouts, deadlocks, and lost updates.
- Explain how indexes, isolation levels, and transaction duration affect lock scope.
- Use `SELECT ... FOR UPDATE`, atomic updates, and version columns to prevent lost updates.
- Inspect transactions and locks using Performance Schema, `sys.innodb_lock_waits`, and InnoDB status.
- Write repeatable concurrency tests and verify final data after commit/rollback.

## 1. Preparing the Test Environment

Use MySQL with the InnoDB storage engine. Create a small table so multiple sessions operate on a few rows:

```sql
CREATE DATABASE IF NOT EXISTS concurrency_lab;
USE concurrency_lab;

CREATE TABLE accounts (
  account_id BIGINT PRIMARY KEY,
  balance DECIMAL(12,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, balance) VALUES
  (1, 100.00),
  (2, 100.00)
ON DUPLICATE KEY UPDATE balance = 100.00;
```

The examples assume you open two terminal windows or two SQL tabs, each using an independent connection to the same instance and schema. Call them **Session A** and **Session B**. Never share one connection object across both threads, as doing so cannot reproduce contention between two independent transactions.

Verify each session has a distinct connection ID:

```sql
SELECT CONNECTION_ID() AS connection_id,
       @@transaction_isolation AS transaction_isolation,
       @@autocommit AS autocommit;
```

In MySQL 8.0, the `transaction_isolation` variable shows the session's isolation level. InnoDB normally defaults to `REPEATABLE READ`, but always read the actual value instead of assuming. These examples require explicit transactions, so run `START TRANSACTION` before operations that must hold locks.

Reset data between exercises:

```sql
UPDATE accounts SET balance = 100.00 WHERE account_id IN (1, 2);
```

Run contention exercises only in a test environment. Never use administrative sessions or production data to deliberately induce deadlocks or hold locks for long periods.

## 2. Distinguishing Concurrency Phenomena

| Phenomenon | What happens | Typical symptoms |
|---|---|---|
| Blocking / lock wait | A transaction needs a lock held by another transaction | Statement blocks until the lock is released or times out |
| Lock wait timeout | Waiting for a lock exceeds `innodb_lock_wait_timeout` | MySQL error `1205` |
| Deadlock | Transactions form a cycle waiting on each other's locks | InnoDB picks a victim transaction; typically error `1213` |
| Lost update | Two transactions read the same stale value and write absolute values; the second overwrites the first | No SQL error necessarily; final business result is wrong |

Blocking does not mean deadlock. A transaction can legitimately wait until the lock-holding transaction commits. A deadlock is a dependency cycle that cannot progress on its own, forcing InnoDB to abort one transaction to break the cycle.

Lost updates are even more dangerous because both statements can succeed without error. An application detects them only by checking business invariants, using locks or versions, or comparing against expected outcomes.

## 3. Testing Row Locks with `SELECT ... FOR UPDATE`

`SELECT ... FOR UPDATE` is a locking read. Inside an InnoDB transaction, it reads matching rows and acquires the exclusive locks needed to update them. Locks are held until the transaction commits or rolls back.

**Session A**:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Session A holds the lock on row `account_id = 1`. Do not commit or roll back yet.

**Session B**:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;
```

The `UPDATE` in Session B waits on Session A's lock. While B is waiting, switch back to A:

```sql
UPDATE accounts
SET balance = balance - 5.00
WHERE account_id = 1;

COMMIT;
```

Once A commits, B's statement proceeds. Finish B:

```sql
COMMIT;
```

Verify:

```sql
SELECT * FROM accounts WHERE account_id = 1;
```

The final value must reflect both deductions, i.e., `85.00`. If B times out before A releases the lock, handle B's transaction according to the lock wait timeout section below.

`SELECT ... FOR UPDATE` only holds locks while inside an open transaction. If autocommit is enabled and you run a locking read as a standalone statement, the transaction ends immediately after the statement and locks are released before the next operation.

## 4. Testing Lock Wait Timeouts

Set a short timeout for Session B so the lab does not wait long. For example:

```sql
SET SESSION innodb_lock_wait_timeout = 5;
```

**Session A** holds the lock:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1 FOR UPDATE;
```

**Session B** starts a transaction and attempts to update the same row:

```sql
START TRANSACTION;
UPDATE accounts
SET balance = balance + 1
WHERE account_id = 1;
```

If A holds the lock longer than 5 seconds, B receives error `1205: Lock wait timeout exceeded`. Under default configuration, a lock wait timeout normally rolls back only the timed-out statement, not necessarily the whole transaction. The `innodb_rollback_on_timeout` variable alters this behavior.

The application should handle this cleanly: roll back all of transaction B, close or return the connection to the pool in a clean state, and retry the whole business operation only if the error is considered transient and the operation is safe to retry.

```sql
ROLLBACK;
```

In A, release the lock:

```sql
COMMIT;
```

Never continue using transaction B as if no error occurred. After a timeout, the transaction may still be active and holding earlier locks. Explicitly rolling back clears state and prevents unintended lock retention.

## 5. Reproducing a Deadlock Across Two Sessions

A deadlock occurs when two transactions hold locks that the other needs. Create opposite access orders to reproduce it:

Reset data:

```sql
UPDATE accounts SET balance = 100.00 WHERE account_id IN (1, 2);
```

**Step 1 — Session A** locks row 1:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
```

**Step 2 — Session B** locks row 2:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 20 WHERE account_id = 2;
```

**Step 3 — Session A** tries to lock row 2 and blocks:

```sql
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;
```

Leave A's statement waiting without ending transaction A.

**Step 4 — Session B** tries to lock row 1:

```sql
UPDATE accounts SET balance = balance + 20 WHERE account_id = 1;
```

Now A waits on a lock held by B, while B waits on a lock held by A. InnoDB detects the deadlock cycle and picks one transaction as the victim. The chosen session typically receives error `1213: Deadlock found when trying to get lock`; the victim transaction is rolled back. The surviving transaction can proceed once the locks are freed.

Do not assume Session A or B is always the victim. InnoDB picks the victim based on rollback cost and transaction state. After seeing the error, inspect both sessions' states; if the remaining transaction finishes, commit it as intended by the lab. Reset data before the next run.

Applications must retry the **entire deadlocked transaction**, not only the final SQL statement. Earlier reads and business decisions may have relied on a stale snapshot or lock state.

## 6. Inspecting Locks and Waiting Transactions

While Session B is waiting, open Session C or a monitoring tab:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

The `sys.innodb_lock_waits` view summarizes waiting and blocking transactions. It requires the `sys` schema to be installed and appropriate read privileges. Depending on version or privileges, you can query Performance Schema directly.

Inspect active InnoDB transactions:

```sql
SELECT trx_id, trx_state, trx_started,
       trx_wait_started, trx_mysql_thread_id,
       trx_query
FROM information_schema.innodb_trx;
```

Inspect locks recorded by Performance Schema:

```sql
SELECT OBJECT_SCHEMA, OBJECT_NAME, INDEX_NAME,
       LOCK_TYPE, LOCK_MODE, LOCK_STATUS, LOCK_DATA
FROM performance_schema.data_locks;
```

Inspect lock-wait relationships:

```sql
SELECT REQUESTING_ENGINE_TRANSACTION_ID,
       BLOCKING_ENGINE_TRANSACTION_ID,
       REQUESTING_ENGINE_LOCK_ID,
       BLOCKING_ENGINE_LOCK_ID
FROM performance_schema.data_lock_waits;
```

Performance Schema tables must be enabled and may require monitoring privileges. `SHOW ENGINE INNODB STATUS\G` provides InnoDB status output, including details of the most recently detected deadlock:

```sql
SHOW ENGINE INNODB STATUS\G
```

The `LATEST DETECTED DEADLOCK` section typically lists the participating transactions, statements, held locks, and waited-for locks. This is valuable evidence for identifying the resource access order causing the deadlock. When multiple deadlocks happen in succession, error logs or monitoring systems may need to capture additional history because status displays only the most recent deadlock.

## 7. Indexes Determine Lock Scope

InnoDB locks the index records accessed by an operation, not simply "one logical row" as SQL authors often picture it. Lock scope depends on the chosen index, search predicates, isolation level, and query type.

For example, querying by primary key:

```sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

Because `account_id` is the primary key, InnoDB can locate the target record directly. If querying by an unindexed column, the engine may have to scan many records and lock far more index records than expected.

Inspect the execution plan:

```sql
EXPLAIN
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
```

In InnoDB under default `REPEATABLE READ` isolation, a locking range scan can use next-key locks (record locks combined with gap locks) to block inserts into the relevant key range. An equality lookup on a unique index for an existing single value normally only needs to lock that record; range predicates, nonexistent records, or non-unique indexes can lock broader spans.

Under `READ COMMITTED`, many gap locks are reduced or omitted for ordinary locking reads, though exceptions remain such as foreign key checks and duplicate key checks. Never switch isolation levels just to avoid locks without checking the impact on consistency and workload.

## 8. Reproducing a Lost Update

A lost update happens when two transactions both read an old value, compute a new value in application code, and write an absolute value. The later writer overwrites the earlier transaction's update.

Reset account 1's balance to `100.00`.

**Session A**:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1;
-- Application reads 100.00 and computes 90.00
```

**Session B**:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE account_id = 1;
-- Application also reads 100.00 and computes 80.00
```

**Session A** writes its computed value:

```sql
UPDATE accounts SET balance = 90.00 WHERE account_id = 1;
COMMIT;
```

**Session B** then writes the value computed from stale data:

```sql
UPDATE accounts SET balance = 80.00 WHERE account_id = 1;
COMMIT;
```

The final value is `80.00`, whereas applying both deductions of 10 and 20 should yield `70.00`. Both transactions commit cleanly; the database has no way of knowing `80` was calculated from an outdated read.

This is why concurrency tests must assert business invariants and final state, not merely that SQL statements returned no errors.

## 9. Preventing Lost Updates with Pessimistic Locking

When business logic must read the current value before deciding an update, lock the row before reading using `SELECT ... FOR UPDATE`.

**Session A**:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Compute new value from the balance just read
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

COMMIT;
```

**Session B** must follow the same rule: start a transaction, run `SELECT ... FOR UPDATE`, read the value after acquiring the lock, then compute and update. While A holds the lock, B waits. Once A commits, B's locking read observes the latest committed version and computes against the updated balance.

This is pessimistic locking: locking before modifying. It suits high-contention workloads or business rules protecting a read-modify-write sequence. Keep transactions short and query via selective indexes to minimize blocking duration.

## 10. Preventing Lost Updates with Atomic Updates

If business logic simply adds or subtracts a known amount, let MySQL perform the calculation in one statement instead of reading into the application and writing back:

```sql
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1
  AND balance >= 10.00;

SELECT ROW_COUNT() AS affected_rows;
```

The subtraction runs atomically on the row's current value. The `balance >= 10.00` predicate prevents negative balances. If `affected_rows = 0`, either the account does not exist or the balance is insufficient; the application should distinguish those per business rules.

Inventory example:

```sql
UPDATE inventory
SET quantity = quantity - ?
WHERE sku = ?
  AND quantity >= ?;
```

Bind the same quantity to both placeholders and check the affected row count. This is typically a simple, effective pattern for conditional increments/decrements. For complex logic depending on multiple freshly read values, consider pessimistic locking or optimistic versioning.

## 11. Preventing Lost Updates with Optimistic Locking

Optimistic locking works well when conflicts are infrequent. Add a `version` column to the table:

```sql
CREATE TABLE versioned_accounts (
  account_id BIGINT PRIMARY KEY,
  balance DECIMAL(12,2) NOT NULL,
  version BIGINT NOT NULL DEFAULT 0
) ENGINE = InnoDB;

INSERT INTO versioned_accounts (account_id, balance, version)
VALUES (1, 100.00, 0);
```

The application reads `balance` and `version`, computes the new value, and performs a conditional update:

```sql
UPDATE versioned_accounts
SET balance = 90.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0;
```

If `ROW_COUNT() = 1`, the update succeeded. If it equals `0`, the version changed or the row no longer exists; the application must re-read, re-check business rules, and either perform a bounded retry or report a conflict.

In JPA, `@Version` makes Hibernate automatically append the version predicate to `UPDATE` statements and throw `OptimisticLockException` on conflict:

```java
@Entity
public class VersionedAccount {
    @Id
    private Long accountId;

    private BigDecimal balance;

    @Version
    private Long version;
}
```

Optimistic locking does not hold row locks while the application processes after reading. It detects conflicts at write time, so design appropriate retry or conflict responses.

## 12. Reducing Deadlocks Through Access Design

Not every deadlock is a configuration flaw. InnoDB detects and resolves deadlocks to maintain consistency. The design goal is lowering frequency and ensuring applications recover cleanly.

Useful practices:

- **Lock in a consistent order:** when multiple transactions need rows A and B, always access A before B, such as sorting IDs before updating.
- **Keep transactions short:** never make HTTP calls, wait on user input, or process files while holding locks.
- **Use appropriate indexes:** avoid full scans in `UPDATE`, `DELETE`, and locking reads when only a few rows are needed.
- **Update smaller batches:** split large batches into bounded chunks with clear transaction boundaries.
- **Avoid reverse-order access to shared resources:** audit distinct code paths updating the same tables or rows.
- **Retry the entire transaction on deadlock:** use bounded retry counts and backoff with jitter.
- **Check constraints and triggers:** a single statement may lock extra rows or indexes due to foreign keys, unique checks, and triggers.

Never try to eliminate deadlocks by disabling deadlock detection or raising timeouts. Deadlocks signal lock-ordering and resource-contention issues; inspect InnoDB diagnostics to fix the root cause.

## 13. Isolation Levels and Locking Reads

MySQL InnoDB supports the standard isolation levels: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. Isolation levels govern consistent reads, gap locking, and visibility across statements.

Under `REPEATABLE READ`, ordinary consistent reads inside a transaction read from a snapshot per InnoDB rules. A locking read like `SELECT ... FOR UPDATE` is a current read, reading the latest lockable state rather than an older snapshot.

Inspect session isolation:

```sql
SELECT @@SESSION.transaction_isolation;
```

Change isolation for only the next transaction in the session:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
-- Run test steps
COMMIT;
```

Never change global isolation in production solely to make a test pass. Determine application consistency requirements, re-test queries and locks, and scope changes as narrowly as possible.

## 14. Testing in Java/JDBC with Multiple Connections

In integration tests, open two separate `Connection` objects from `DataSource`, disable auto-commit, and use latches/barriers to coordinate ordering. Never share one connection across two threads.

Example test harness skeleton:

```java
try (Connection connectionA = dataSource.getConnection();
     Connection connectionB = dataSource.getConnection()) {
    connectionA.setAutoCommit(false);
    connectionB.setAutoCommit(false);

    // A locks the row first.
    try (PreparedStatement lockA = connectionA.prepareStatement(
            "SELECT balance FROM accounts WHERE account_id = ? FOR UPDATE")) {
        lockA.setLong(1, 1L);
        try (ResultSet resultSet = lockA.executeQuery()) {
            if (resultSet.next()) {
                resultSet.getBigDecimal("balance");
            }
        }
    }

    // Use a CountDownLatch so B attempts to update while A still holds the lock.
    // Assert B blocks or receives a lock timeout per test configuration.

    connectionA.commit();
    connectionB.rollback();
}
```

This skeleton illustrates part of a test; in real tests, run B's operations on a separate thread and coordinate with `CountDownLatch`, `CyclicBarrier`, or `Future`. Set test timeouts to prevent infinite hangs, and roll back both connections in `finally` if the test fails.

Deadlock tests must strictly coordinate lock acquisition order: A locks row 1, B locks row 2, A requests row 2, then B requests row 1. Catch SQL state/error codes and verify one transaction rolled back. Never pre-assert which specific session becomes the victim.

## 15. Concurrency Test Matrix

| Test case | Session coordination | Expected outcome |
|---|---|---|
| Row lock | A `FOR UPDATE`; B updates same row; A commits | B waits then proceeds |
| Lock timeout | A holds lock long; B sets short timeout and updates | B receives `1205`; app rolls back transaction B |
| Deadlock | A locks row 1; B locks row 2; each requests the other's row | InnoDB picks one victim; aborted transaction receives `1213` |
| Lost update | A and B read same old value; each writes an absolute value | Reproduces one update overwriting the other |
| Pessimistic prevention | Both sessions read `FOR UPDATE` before computing | Second session reads updated value after acquiring lock |
| Atomic update | Both sessions run SQL arithmetic update on the column | Both operations apply against current values |
| Optimistic locking | A and B read same version; A updates first; B updates stale version | B updates 0 rows or receives optimistic lock exception |

For each test, record executed SQL, connection IDs, wait durations, errors, transaction states, and final data. Test assertions must verify invariants such as conserved total balance across transfers, non-negative inventory, and each request taking effect exactly once.

## 16. Common Mistakes and Remedies

- **Sharing one connection across threads:** statements interleave on the same session instead of reproducing two independent transactions. Acquire a separate connection per thread.
- **Forgetting `START TRANSACTION`:** locks are released immediately after the statement when autocommit is on. Open a transaction before locking reads.
- **Holding transactions too long:** other sessions block and undo history grows. Narrow transaction boundaries.
- **Confusing timeout with deadlock:** `1205` is lock wait timeout; `1213` is deadlock. Handle transactions and retries according to the specific error.
- **Retrying only the deadlocked statement:** earlier read-based decisions may no longer be valid. Retry the entire transaction.
- **Catching timeout errors but continuing the transaction:** the transaction may remain active holding locks. Proactively roll back the entire transaction.
- **Missing index on locking predicates:** the engine may scan and lock more records than necessary. Use `EXPLAIN`, add appropriate indexes, and re-verify lock scope.
- **Using plain `SELECT` to guard read-modify-write:** consistent reads do not hold exclusive locks. Use `FOR UPDATE`, atomic updates, or versioning.
- **Disabling autocommit without committing/rolling back:** connections return to the pool with dirty transaction state. End transactions explicitly.
- **Checking only SQL errors without checking final data:** lost updates can occur with zero exceptions. Assert final data and business invariants.

## 17. Practice Exercise

On a test MySQL instance, complete these steps:

1. Create the `concurrency_lab` schema and `accounts` table as in setup; open Sessions A, B, and a monitoring session.
2. Reproduce a row lock with `SELECT ... FOR UPDATE`, confirming Session B waits and proceeds after A commits.
3. Set a short `innodb_lock_wait_timeout` in B, hold the lock in A, verify B receives error `1205`, and roll back B.
4. Reproduce a deadlock by locking two rows in opposite orders; record the victim transaction and the `LATEST DETECTED DEADLOCK` output.
5. Reproduce a lost update by having both sessions read `100` and sequentially write `90` and `80`; confirm the final result violates business logic.
6. Fix the lost update using `FOR UPDATE`, re-run, and confirm both changes take effect.
7. Test a conditional atomic update on balance/inventory and check affected row counts.
8. Add a `version` column, test optimistic locking with two sessions reading the same version, and confirm one write is rejected.
9. Use `EXPLAIN` and lock monitoring to compare an indexed query against an unindexed query.

**Completion criteria:** you can deliberately reproduce and explain blocking, timeouts, deadlocks, and lost updates; pick the right protection strategy; read lock diagnostics; and prove final data satisfies invariants under concurrent execution.

## Conclusion

Concurrency testing requires multiple independent connections and controlled statement ordering. InnoDB uses row/index locks to guard updates, detects deadlocks, and selects a transaction to roll back; however, lost updates still occur when applications read and write stale values without locking or version checks. Combining `SELECT ... FOR UPDATE`, atomic updates, optimistic locking, proper indexes, and full-transaction retries keeps applications correct under concurrent data access.
