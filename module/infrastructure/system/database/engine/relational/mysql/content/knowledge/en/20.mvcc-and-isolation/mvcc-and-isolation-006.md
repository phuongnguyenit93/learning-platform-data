# REPEATABLE READ and Transaction-Consistent Snapshots

InnoDB uses MVCC (Multi-Version Concurrency Control) to let a transaction read a consistent version of data while other transactions can still update rows. At the REPEATABLE READ isolation level, nonlocking consistent reads within the same transaction typically view the same data snapshot (read view). Thus, a repeated read query does not unexpectedly see changes committed by other transactions after the snapshot was created.

To use REPEATABLE READ properly, three concepts must be distinguished:

- **Consistent read**: a nonlocking read using MVCC's read view to read the row version matching the snapshot.
- **Current read**: reading the current version of a row, typically accompanied by locking mechanisms for UPDATE, DELETE, or SELECT ... FOR UPDATE / FOR SHARE.
- **Transaction snapshot**: the point-in-time boundary determining which committed versions are visible to consistent reads within the transaction.

This article focuses on InnoDB behavior in MySQL 8.0 and later, how read views are created and reused, differences between consistent reads and locking reads, phantoms, undo versions, and how to test behavior with two transaction sessions.

## 1. Preparing Sample Data

We use an accounts table with balances:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (account_id),
    KEY idx_accounts_balance (balance)
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Binh',  500.00),
    (3, 'Chi',   250.00);
~~~

Each account is identified by account_id. The examples assume two independent MySQL connections, called Session A and Session B. Open two SQL windows or two separate connections to observe the commit order and data reads.

Check the current isolation level:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

In MySQL 8.0, InnoDB defaults to REPEATABLE READ, unless server or session configuration has been changed.

## 2. How Does MVCC Create a Consistent Snapshot?

MVCC allows InnoDB to keep multiple logical versions of the same row for as long as needed. When a transaction updates a row, InnoDB writes undo information so older versions can be restored. A consistent read can follow this version chain to find the version matching the transaction's read view.

Conceptually:

1. Each row modification is tagged with the transaction performing the change.
2. The undo log holds the information needed to reconstruct the previous version.
3. The read view records the state of transactions at the time the snapshot is created.
4. When reading, InnoDB determines which version is visible according to the read view.
5. If the current version is not yet visible, InnoDB can follow undo records to find a suitable older version.

An InnoDB clustered index record contains internal system fields for MVCC, including a transaction ID and a rollback pointer. The rollback pointer links to undo information to reconstruct the previous version of the row.

### 2.1. Which Versions Are Visible?

A consistent read in a transaction typically sees:

- Changes from other transactions that committed before the read view was created.
- Changes that the current transaction itself made earlier.

It does not see:

- Uncommitted changes from other transactions at the time the read view was created.
- Changes from other transactions that committed after the read view was created.

The rule of reading the transaction's own changes is an important exception: a transaction always sees its own writes. Therefore, a query result can combine snapshot versions of other rows with new changes made by that transaction itself.

### 2.2. MVCC Reduces Read/Write Contention

An ordinary SELECT in InnoDB is a consistent read and does not place shared locks on individual rows solely for reading. If transaction B updates a row while transaction A is reading an old snapshot, A can still read the old version via undo; B can continue writing and committing as long as no other locks interfere.

This helps readers and writers block each other less often. MVCC does not eliminate all locks: UPDATE, DELETE, SELECT ... FOR UPDATE, and SELECT ... FOR SHARE still use locking mechanisms appropriate to the operation.

## 3. When Does REPEATABLE READ Create a Read View?

An easy misconception is that START TRANSACTION necessarily creates a read view immediately.

With REPEATABLE READ:

- If started with a plain START TRANSACTION, the read view for consistent reads is typically created on the transaction's first consistent read.
- Subsequent consistent reads within the same transaction reuse that read view.
- If using START TRANSACTION WITH CONSISTENT SNAPSHOT, InnoDB creates a consistent snapshot immediately upon starting the transaction at REPEATABLE READ.

Therefore, the timing of the first read matters. A transaction may have already executed several statements before the read view is created; those statements do not automatically establish the snapshot for consistent reads if they are not consistent reads themselves.

Example:

~~~sql
START TRANSACTION;

-- No consistent read has happened here yet.
UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- The first consistent read creates the read view here.
SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

UPDATE is a write operation using current-version reading/locking mechanisms to update. The subsequent ordinary SELECT is the first consistent read; it creates the read view when it runs. The transaction also sees the balance change it just made itself.

If you want the snapshot created right at the start:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

WITH CONSISTENT SNAPSHOT only takes effect under REPEATABLE READ. At other isolation levels, MySQL ignores this option and may emit a warning; set the isolation level before starting the transaction.

## 4. Two-Transaction Example: Repeated Reads of the Same Snapshot

Suppose account 1 has balance = 1000.00. Execute the following steps in exact order.

**Session A**

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

The result is 1000.00. This is the first consistent read, so Session A's read view is created here.

**Session B**

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE accounts
SET balance = 1200.00
WHERE account_id = 1;

COMMIT;
~~~

Session B has committed the new balance of 1200.00.

**Back in Session A**

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

The result is still 1000.00. Session A reuses the read view created during the first SELECT, so it does not see Session B's new commit.

End Session A:

~~~sql
COMMIT;
~~~

After committing, a new SELECT in a subsequent transaction will use a new snapshot and can see 1200.00.

| Time | Session A | Session B | Value Seen by A |
|---|---|---|---:|
| T0 | Starts and runs first SELECT | Not updated yet | 1000.00 |
| T1 | Keeps transaction open | UPDATEs to 1200 and COMMITs | 1000.00 |
| T2 | Runs second SELECT | Already committed | 1000.00 |
| T3 | COMMIT | Already committed | Transaction A ends |
| T4 | SELECT in new transaction | Already committed | 1200.00 |

This is the repeatable read behavior of consistent reads: same transaction, same snapshot, same row yields stable repeated read values, except for changes made by that transaction itself.

## 5. START TRANSACTION Does Not Mean a Snapshot Has Been Created

Compare two scenarios:

**Scenario 1: snapshot created at the first SELECT**

~~~sql
START TRANSACTION;
-- Another session can commit a change here.
SELECT balance FROM accounts WHERE account_id = 1;
~~~

If Session B commits before the first SELECT, Session A can see the new value because the read view is only created when the SELECT runs.

**Scenario 2: snapshot created immediately at start**

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
SELECT balance FROM accounts WHERE account_id = 1;
~~~

If Session B commits after Session A created the consistent snapshot, Session A's SELECT still reads the version belonging to the older snapshot.

This difference matters for reports requiring multiple queries to read the same point-in-time data. If you just call START TRANSACTION and do other work before the first SELECT, the snapshot boundary is not necessarily the START TRANSACTION timestamp.

## 6. Consistent Read and Current Read Are Not the Same

This is the most important distinction when working with REPEATABLE READ.

| Characteristic | Consistent Read | Current/Locking Read |
|---|---|---|
| Examples | Ordinary SELECT | SELECT ... FOR UPDATE, SELECT ... FOR SHARE |
| Version | According to read view | Current version required by the locking operation |
| Places row locks for reading | Does not place row locks solely for reading | Acquires locks per requested mode |
| Uses old snapshot | Yes | Not in the consistent-read sense |
| Goal | Consistent reading, minimal writer blocking | Reading to validate then lock or modify safely |

Ordinary SELECT:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

SELECT locking the row for update:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

SELECT ... FOR UPDATE is a current read. It reads the current version and places an appropriate exclusive lock on the found row, so the transaction can inspect and update it without another transaction modifying that row before completion.

SELECT ... FOR SHARE (or older syntax LOCK IN SHARE MODE) is a locking read using a shared lock. Other transactions can perform compatible reads, but cannot modify the row until the lock is released.

### 6.1. The Same Transaction Can See Two Different Values

Continuing the example where Session A created a read view when balance was 1000. Session B updates balance to 1200 and commits.

In Session A:

~~~sql
-- Consistent read: old snapshot
SELECT balance
FROM accounts
WHERE account_id = 1;

-- Current read: current version
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

The first SELECT can return 1000.00, while SELECT ... FOR UPDATE returns 1200.00. This is not contradictory: the two statements use different reading mechanisms.

A locking read does not replace the transaction's existing read view. If you subsequently run an ordinary SELECT and the transaction has not modified the row itself, the consistent read can still return the old snapshot value.

Therefore, do not mix consistent reads and current reads in the same business check without clearly understanding the difference. If an update decision depends on the current value, use a locking read or an atomic conditional UPDATE statement.

## 7. UPDATE and DELETE Are Not Ordinary Consistent Reads

Data-modification statements must locate the current row version to lock and modify it. They do not use an old snapshot the way an ordinary SELECT does.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;
~~~

The condition and update are executed using InnoDB's current-read/locking mechanism. This is usually better than reading balance via an old consistent SELECT, computing in the application, and then UPDATE-ing an absolute value that could overwrite another transaction's change.

For a money transfer workflow, both accounts must be updated in the same transaction and the balance checked:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

-- Application must check the number of affected rows.
-- If no rows were updated, ROLLBACK.

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
~~~

This is an illustrative skeleton; the application must check the outcome of each UPDATE and roll back if any condition fails. In a production system, add transaction IDs, business constraints, error handling, and consistent lock ordering.

## 8. REPEATABLE READ and Phantom Rows

A phantom is a situation where a range-condition query is run again and additional rows matching the condition appear or disappear due to data changes by another transaction.

With consistent reads in the same REPEATABLE READ transaction, the read view does not change. Therefore, new rows inserted and committed by another transaction after the snapshot was created will not appear when rerunning the same snapshot query.

Session A example:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
ORDER BY account_id;
~~~

Session B:

~~~sql
START TRANSACTION;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES (4, 'Dung', 700.00);

COMMIT;
~~~

Session A reruns the ordinary SELECT:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
ORDER BY account_id;
~~~

Session A still does not see account 4 because that row does not belong to the read view created before Session B committed. Session A ends its transaction with COMMIT or ROLLBACK.

This is how consistent snapshots avoid phantoms for consistent reads. No range locking is needed to keep snapshot read results stable.

### 8.1. Locking Range Reads Use Next-Key Locks

If the goal is to prevent another transaction from inserting new rows into the range being inspected, use a locking read on the range condition:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
FOR UPDATE;
~~~

InnoDB can place next-key locks on the index records and key gaps associated with the scanned range. A next-key lock combines a record lock with a gap lock, thereby preventing inserts into gaps within the locked range.

While Session A still holds the transaction and range lock, Session B tries to insert an account with a balance in that range:

~~~sql
INSERT INTO accounts (account_id, owner_name, balance)
VALUES (5, 'Em', 650.00);
~~~

If Session A's plan scans and locks the corresponding ranges on idx_accounts_balance, Session B's INSERT may have to wait until Session A COMMITs or ROLLBACKs.

The exact locking behavior depends on the index used and the access path. A search condition without a suitable index can cause InnoDB to scan and lock more records than expected. Locking range reads can therefore reduce concurrency and cause lock waits or deadlocks.

Distinction:

- Consistent reads use snapshots to keep read results stable, without locking rows just for reading.
- Locking range reads use record/gap/next-key locks to prevent conflicting changes within the protected range.

## 9. REPEATABLE READ vs. READ COMMITTED

The two isolation levels are frequently compared when designing applications:

| Behavior | READ COMMITTED | REPEATABLE READ |
|---|---|---|
| Dirty read | No | No |
| Consistent read snapshot | New snapshot for each consistent SELECT | Snapshot reused within the transaction after the first consistent read |
| Repeated read of same row | Can see new commits in later SELECTs | Typically keeps the same snapshot version |
| Phantom in consistent read | Can see new rows in later SELECTs | Does not see rows committed after the snapshot within the same read view |
| Gap locking | Typically disabled, except certain constraint checks | Used for many locking range scans |

Example under READ COMMITTED:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;

-- Another session updates and COMMITs.

SELECT balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

The two ordinary SELECTs can return two different values because each consistent read takes a fresh snapshot. Under REPEATABLE READ, two SELECTs in the same transaction typically read the same read view.

READ COMMITTED still prevents dirty reads. It simply allows a transaction to see newer committed changes between SELECT statements.

## 10. REPEATABLE READ Does Not Mean SERIALIZABLE

InnoDB's REPEATABLE READ provides consistent snapshots for consistent reads and uses locks to protect write/locking-read operations. However, it should not be treated as equivalent to SERIALIZABLE in all scenarios.

One issue to watch for is write skew: two transactions both read a consistent snapshot, each updates a different row, and both can commit even though together they violate a multi-row business rule.

Example of an on-call roster table:

~~~sql
CREATE TABLE on_call_staff (
    staff_id BIGINT UNSIGNED NOT NULL,
    on_call BOOLEAN NOT NULL,
    PRIMARY KEY (staff_id)
) ENGINE = InnoDB;

INSERT INTO on_call_staff (staff_id, on_call)
VALUES (1, TRUE), (2, TRUE);
~~~

Business rule: there must always be at least one person on call. The following schedule of operations can occur.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT COUNT(*) FROM on_call_staff WHERE on_call = TRUE;
-- Returns 2.
~~~

Session B:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT COUNT(*) FROM on_call_staff WHERE on_call = TRUE;
-- Also returns 2 in B's snapshot.
~~~

Then Session A toggles person 1 off and commits:

~~~sql
UPDATE on_call_staff SET on_call = FALSE WHERE staff_id = 1;
COMMIT;
~~~

Session B toggles person 2 off and commits:

~~~sql
UPDATE on_call_staff SET on_call = FALSE WHERE staff_id = 2;
COMMIT;
~~~

Because the two transactions update two different rows, there is not necessarily a direct write conflict; both can commit and the final result leaves nobody on call.

To protect multi-row invariants, you can:

- Lock a shared coordinator row before reading and updating.
- Use SELECT ... FOR UPDATE on the appropriate set of rows and re-verify after acquiring locks.
- Design data constraints or update models so conflicts are detected.
- Use SERIALIZABLE if the semantics and locking cost are acceptable.

Do not rely on an ordinary snapshot SELECT to guard a condition that multiple transactions can concurrently change.

## 11. Undo Log, Purge, and Long-Running Read Transactions

MVCC needs to retain old versions in the undo log as long as a transaction may need to read them. InnoDB can only purge versions that are no longer needed by any active read view.

A long-open transaction, even read-only, can hold an old read view and prevent purge from removing versions older than that point.

Consequences may include:

- History list length grows.
- Undo tablespace and old version data consume more storage.
- Purge falls behind the rate of changes.
- Certain queries and maintenance operations incur additional overhead.
- I/O pressure and recovery time can increase when undo backlog grows large.

Example of a reporting transaction left open for hours:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*)
FROM accounts;

-- Application processes or waits a very long time before finishing.

COMMIT;
~~~

During the wait, other transactions can still update data. However, the report's old read view can force InnoDB to keep versions that the report might still need to read.

Good practices:

- Keep transactions as short as possible.
- Do not open a transaction before waiting on user interaction or input.
- Read in batches with an explicit snapshot design if a report is very large.
- Ensure the application always COMMITs or ROLLBACKs even on errors.
- Monitor long-running transactions and history list length.

## 12. Monitoring Open Transactions

You can inspect active InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Useful columns:

- trx_started: timestamp when the transaction began.
- trx_state: transaction state.
- trx_mysql_thread_id: corresponding connection ID.
- trx_rows_locked: number of rows currently locked per InnoDB's statistics.
- trx_rows_modified: number of rows modified by the transaction.
- trx_query: current statement if any.

To view overall InnoDB information, including History list length:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

History list length is an indicator of history list length and undo history awaiting purge processing as reported by InnoDB. Do not equate this number with the number of existing rows or treat a single value as conclusive proof of an incident; interpret it in the context of write rate, transaction duration, and purge capacity.

## 13. Configuring Isolation Level at the Right Scope

Check the session isolation level:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

Set the isolation level for subsequent transactions in the session:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
~~~

Set the isolation level only for the next transaction:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
~~~

SET TRANSACTION without SESSION or GLOBAL applies to the next transaction of the current session. It must be set before START TRANSACTION.

In an application using a connection pool, each connection has its own session state. If the application changes isolation level on demand, it must reset or explicitly set it when the connection is reused; otherwise, a later request may receive a session with an unexpected isolation level.

Do not change the GLOBAL isolation level just to fix one query or business workflow. A global change affects new sessions and requires deliberate administration.

## 14. Practical Transaction Patterns

### 14.1. Reports Needing a Unified Snapshot

A report reading multiple tables needs consistent figures at the same point in time:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS account_count
FROM accounts;

SELECT SUM(balance) AS total_balance
FROM accounts;

COMMIT;
~~~

Both SELECTs use the same consistent snapshot. READ ONLY indicates the transaction does not intend to write data; it helps clarify the transaction's intent.

If the report needs to read multiple tables, ordinary SELECTs in the same transaction also share the same read view. Avoid using locking reads unless data truly needs to be locked.

### 14.2. Reading and Updating a Row Based on the Latest Value

If the decision depends on the current balance, use a locking read:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Application inspects balance and decides the amount to deduct.

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

COMMIT;
~~~

FOR UPDATE performs a current read and holds the lock until the transaction ends. Another transaction wanting to modify the same row must wait or may encounter a deadlock depending on lock ordering.

### 14.3. Using Conditional UPDATE Instead of Application Read-Modify-Write

If the rule is simple, you can combine the check and modification into one statement:

~~~sql
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;
~~~

The application checks affected rows:

- 1 row: condition held and update succeeded.
- 0 rows: account does not exist or balance is insufficient; determine the cause per business requirements.

This approach reduces the window between read and write, while avoiding using an old snapshot value as the basis for an update.

## 15. Common Mistakes

**"START TRANSACTION creates a snapshot immediately."** Not necessarily. With REPEATABLE READ, the first consistent read usually creates the read view. Use WITH CONSISTENT SNAPSHOT if you need the snapshot created immediately upon start.

**"Two SELECTs in REPEATABLE READ always see the latest data."** No. Consistent reads within the same transaction reuse the snapshot and can continue seeing older versions.

**"SELECT ... FOR UPDATE also reads the old snapshot."** No. It is a current/locking read, reading the current version needed for the locking operation.

**"A transaction only has one view of the data."** No. Consistent reads and current reads can appear in the same transaction and yield different results.

**"MVCC means no locks are needed."** No. MVCC supports consistent reads; write operations and locking reads still need locks to coordinate conflicts.

**"REPEATABLE READ is always equivalent to SERIALIZABLE."** No. A consistent snapshot does not automatically protect all multi-row business invariants; appropriate locks, constraints, or isolation levels are required.

**"Long-running read transactions do not affect the system."** No. An old read view can delay purge and cause undo history to grow.

**"With autocommit on, snapshots still persist across multiple SELECT statements."** No. When autocommit is enabled, each standalone statement is typically its own transaction. For multiple SELECTs to share a snapshot, open an explicit transaction.

**"Changing the isolation level on one connection changes the whole application."** No. SESSION applies to the current connection; a connection pool has many independent sessions.

## 16. Checklist When Using REPEATABLE READ

- [ ] Determined whether the transaction needs a consistent snapshot or needs to read the current version to update.
- [ ] Checked the connection's effective isolation level.
- [ ] Understood whether the snapshot is created at the first consistent read or at START TRANSACTION WITH CONSISTENT SNAPSHOT.
- [ ] Opened an explicit transaction if multiple SELECT statements need the same read view.
- [ ] Did not use stale consistent-read results to make decisions updating current data without locks or atomic conditions.
- [ ] Distinguished ordinary SELECT from SELECT ... FOR UPDATE and SELECT ... FOR SHARE.
- [ ] Checked range conditions and indexes when using locking range reads.
- [ ] Accounted for lock waits, deadlocks, and lock acquisition order.
- [ ] Ensured transactions end with COMMIT or ROLLBACK.
- [ ] Monitored long transactions, undo history, and purge under long-running read workloads.
- [ ] Tested behavior with two independent sessions and an explicit commit order.

## Conclusion

In InnoDB REPEATABLE READ, the first consistent read typically creates a read view, and subsequent consistent reads within the same transaction reuse that snapshot. This mechanism lets reports repeatedly read the same data state without locking rows solely to read them.

SELECT ... FOR UPDATE, SELECT ... FOR SHARE, and data-modification statements use current reads/locking to work with the current version. Therefore, a transaction can see an old snapshot through an ordinary SELECT while seeing newer data through a locking read. Understanding this distinction, keeping transactions short, and testing with two sessions form the foundation for building correct and scalable MySQL transactions.
