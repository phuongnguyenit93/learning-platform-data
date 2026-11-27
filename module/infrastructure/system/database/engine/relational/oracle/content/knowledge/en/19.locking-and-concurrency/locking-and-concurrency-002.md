# Read Consistency, Write Operations, and Blocking Scenarios in Oracle Database

In Oracle Database, multiple sessions can read and write to a table concurrently. A SELECT statement may be running while another session runs UPDATE on the same rows; two transactions may also try to modify the same row at the same time. Oracle must ensure that readers see a consistent state of data while also controlling conflicts between write operations.

Three related mechanisms should be separated:

- **Read consistency:** a query reads data according to a logical snapshot, without seeing uncommitted changes from other transactions.
- **MVCC and undo:** Oracle uses undo to reconstruct a committed version appropriate for the snapshot when the current block has already been modified.
- **Locking:** locks protect write changes and operations that explicitly request locks. When two writers want to modify the same row, one side may have to wait.

Therefore, a regular SELECT normally does not have to wait for an UPDATE on the same row; it can read the older version using undo. However, a second UPDATE on that very row usually has to wait for the transaction holding the lock. This is the core point for understanding why Oracle both supports concurrent reading and still has to handle blocking between writers.

This lesson covers how Oracle provides read consistency, row locks and table locks, scenarios where operations wait on each other, SELECT FOR UPDATE, the WAIT/NOWAIT/SKIP LOCKED options, lost updates, write consistency, deadlocks, how to observe blocked sessions, and two-session labs.

## 1. Read consistency across multiple sessions

### 1.1. Example of a row being updated

Suppose an accounts table has the following data:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5,000 |
| 202 | 8,000 |

Session A runs:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;

-- Not yet COMMITted.
```

The value 4,000 is A's change, but it has not been committed. Session B runs a regular SELECT:

```sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id = 101;
```

B sees the previously committed value of 5,000. Oracle does not let B read A's uncommitted value of 4,000. If the current block already contains the version modified by A, Oracle can use undo to reconstruct the version matching B's snapshot.

### 1.2. Regular SELECT does not lock rows just to read

A regular SELECT statement does not acquire a row lock on every row it reads. Thus, in normal DML scenarios:

- Readers can read the previously committed version.
- Writers can continue modifying rows.
- Readers do not need to wait for writers to commit just to execute a SELECT.
- Writers do not need to wait for regular SELECTs to release row locks, because those SELECTs do not hold row locks.

This is a key characteristic of MVCC in Oracle. However, you should not conclude that SELECT never waits: a query can still wait for I/O, latches, metadata locks, DDL, or other resources. SELECT statements with `FOR UPDATE` also explicitly request locks.

### 1.3. Statement-level snapshots

Under the default READ COMMITTED isolation level, each SQL statement has its own consistent snapshot at the point the statement begins.

For example:

1. Session B runs SELECT and sees balance 5,000.
2. Session A runs UPDATE balance to 4,000 and then COMMITs.
3. Session B runs a new SELECT.
4. The new SELECT can see balance 4,000.

The two SELECT statements belong to the same transaction of B, yet they can see two different committed states. This is normal behavior under READ COMMITTED.

Conversely, if a SELECT statement is running and A commits while B is still fetching results, the running SELECT continues reading according to that statement's own snapshot. Only a subsequent statement can see the new commit.

### 1.4. No reading uncommitted data

Oracle does not provide dirty reads under standard transaction isolation levels. A transaction cannot use a regular SELECT to see uncommitted changes from another transaction.

This does not prevent two transactions from seeing different results based on snapshot timing. It simply guarantees that the data read conforms to consistency rules, rather than being an in-progress change from another session.

## 2. How do undo and MVCC support readers?

### 2.1. Undo stores prior version information

When a transaction performs UPDATE, DELETE, or INSERT, Oracle generates undo information so it can roll back and serve consistent reads. Undo records are managed in undo segments inside the undo tablespace.

Example:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;
```

If the prior value was 5,000, undo contains the information needed to restore the old state. When another session needs to read a snapshot prior to the change, Oracle can apply undo to reconstruct the 5,000 version.

### 2.2. Visualizing the consistent read mechanism

```text
Previously committed value: BALANCE = 5,000
                  |
                  | Session A UPDATE
                  v
Current value in block: BALANCE = 4,000 (uncommitted)
                  |
                  | Session B needs old snapshot
                  v
Oracle uses undo to reconstruct read version: BALANCE = 5,000
```

The consistent version is constructed from the block and the necessary undo. Oracle does not need to create a full copy of the entire table for each reader.

### 2.3. Reader-writer vs. writer-writer

| Scenario | Typical Behavior |
| --- | --- |
| Regular SELECT reading a row being UPDATEd | Reads consistent version via undo; usually does not wait on row lock |
| UPDATE on the same row being UPDATEd by another transaction | Waits for the lock-holding transaction to finish |
| DELETE on a row being UPDATEd by another transaction | May wait for row lock |
| SELECT FOR UPDATE on a row locked by a writer | May wait, or handle via NOWAIT/WAIT/SKIP LOCKED |
| Two INSERTs creating the same unique key while one is uncommitted | May wait for the other transaction's outcome to determine uniqueness violation |

MVCC primarily resolves conflicts between readers and writers. It does not eliminate the need for locking when multiple writers modify data concurrently.

## 3. Locks in Oracle: row locks and table locks

### 3.1. Row-level locks

When DML modifies a row, Oracle locks that row to prevent other transactions from concurrently modifying/deleting the same row in a conflicting way.

Example:

```sql
UPDATE employees
SET salary = salary + 1000
WHERE employee_id = 100;
```

The transaction holds a lock on the modified row until COMMIT or ROLLBACK. Other transactions wanting to modify that row may have to wait.

Row locks are managed in association with the transaction; Oracle uses a transaction enqueue (commonly observed as type TX) to coordinate conflicts. Applications do not need to manage row locks manually with separate statements for each UPDATE.

### 3.2. Table-level DML locks

DML also acquires a table-level lock to protect access structures and coordinate with other operations. A typical INSERT/UPDATE/DELETE acquires a table lock in Row Exclusive mode (RX, commonly displayed as TM mode 3).

Multiple normal DML statements on the same table can hold Row Exclusive table locks concurrently. Thus, two sessions running UPDATE on two different rows in a table do not automatically block each other at the table level.

Stronger table lock modes, DDL, or explicit LOCK TABLE operations can conflict with these DML operations.

### 3.3. Row locks and table locks are not the same thing

- **Row locks** protect the specific rows that a transaction is modifying or locking with FOR UPDATE.
- **Table locks** coordinate access at the object level and interact with DDL/explicit table locks.
- Having many DML operations active concurrently on a single table is a normal situation.
- A strong table lock can force many other DML operations to wait even if they intend to modify different rows.

### 3.4. How long are locks held?

For regular DML and SELECT FOR UPDATE, locks are held until the transaction ends with COMMIT or ROLLBACK. Finishing an UPDATE statement does not mean the lock is released if the transaction has not yet committed.

Example:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

-- The row remains locked after the UPDATE statement finishes.
-- The lock is released on COMMIT or ROLLBACK.
```

This is why a long-running transaction can cause blocking even when the session is no longer actively executing a SQL statement.

## 4. When do two operations have to wait for each other?

### 4.1. Two sessions UPDATE the same row

Session A:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;

-- Not yet COMMITted.
```

Session B:

```sql
UPDATE accounts
SET balance = 4500
WHERE account_id = 101;
```

B needs the lock on row 101, but A holds it, so B typically enters a wait state. When A runs COMMIT or ROLLBACK, B can proceed and Oracle applies write consistency rules for B's statement.

If A COMMITs, B operates on the newly committed state. If A ROLLBACKs, A's change is undone and B can update based on the previous state.

### 4.2. Two sessions UPDATE two different rows

Session A:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

Session B:

```sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;
```

Assuming no conflicting triggers, constraints, table locks, or shared resources, both statements can execute concurrently because they modify different rows. Being on the same table does not mean all DML operations must wait for one another.

### 4.3. DELETE and UPDATE on the same row

If A UPDATEs a row without committing, B running DELETE on that same row may have to wait. Similarly, if A DELETEs a row, B running UPDATE or DELETE on the same row must wait for transaction A to finish.

After waiting, Oracle determines the current state and applies the statement predicate according to write consistency rules. If the row has been deleted or no longer matches the WHERE clause, B's statement may affect 0 rows.

### 4.4. INSERT with duplicate uncommitted unique key

Session A:

```sql
INSERT INTO employees(employee_id, name)
VALUES (9001, 'New Employee');

-- Not yet COMMITted.
```

Session B attempts to insert the same key:

```sql
INSERT INTO employees(employee_id, name)
VALUES (9001, 'Another Employee');
```

B may have to wait because Oracle cannot yet determine whether that unique key will exist after transaction A finishes. If A COMMITs, B receives a unique/primary key violation error. If A ROLLBACKs, B can proceed with the insert.

This is a wait scenario that does not stem from updating the same row in the usual sense, yet still arises from data and constraint conflict.

### 4.5. Explicit table locking

Example:

```sql
LOCK TABLE accounts IN EXCLUSIVE MODE;
```

An EXCLUSIVE table lock can block other DML on the table until the transaction ends. This is a strong lock; do not use it merely to protect a specific row.

If you only need to lock selected rows, `SELECT ... FOR UPDATE` usually expresses the intent more accurately.

### 4.6. DDL requires metadata locks

DDL operations such as ALTER TABLE require appropriate object locks and may have to wait for transactions currently using the table to finish. Conversely, DDL can make other DML operations wait. Oracle DDL also performs implicit commits before/after according to command rules, so do not mix DDL into business transactions expecting to roll it back like DML.

## 5. Two-session experiment: SELECT does not wait, UPDATE waits

Perform this in two independent sessions, such as two worksheets in SQL Developer. Use a learning schema.

### 5.1. Prepare the data

Run once:

```sql
CREATE TABLE demo_write_wait (
    item_id NUMBER(10) PRIMARY KEY,
    quantity NUMBER(10) NOT NULL
);

INSERT INTO demo_write_wait VALUES (1, 10);
INSERT INTO demo_write_wait VALUES (2, 20);
COMMIT;
```

### 5.2. Session A: lock the row with UPDATE

```sql
UPDATE demo_write_wait
SET quantity = 9
WHERE item_id = 1;

-- Not yet COMMITted.
```

Session A has modified row 1 and holds the lock.

### 5.3. Session B: SELECT the locked row

```sql
SELECT item_id, quantity
FROM   demo_write_wait
WHERE  item_id = 1;
```

The result is still quantity 10. B reads the previously committed version via the consistent read mechanism; SELECT typically does not wait on A just because A holds a row lock.

### 5.4. Session B: UPDATE the same row

```sql
UPDATE demo_write_wait
SET quantity = 8
WHERE item_id = 1;
```

B will have to wait for A to finish its transaction because two writers are contending for the same row. Leave B waiting to observe, then switch back to Session A.

### 5.5. Session A: COMMIT

```sql
COMMIT;
```

After commit, the lock is released. Session B proceeds. The final value depends on the UPDATE expression and WHERE condition; in this example a constant 8 is assigned, so if the row still satisfies the condition, the final value is 8.

### 5.6. Retry with ROLLBACK

Reset the data:

```sql
UPDATE demo_write_wait SET quantity = 10 WHERE item_id = 1;
COMMIT;
```

Repeat Session A's step, but finish with:

```sql
ROLLBACK;
```

Once Session B stops waiting, it updates based on the state that existed before A's change. Compare the two cases to see how COMMIT and ROLLBACK affect a waiting writer.

## 6. Write consistency: what happens after a writer waits?

### 6.1. UPDATE predicates must be evaluated on the appropriate state

DML does not only need to lock a row; it must also ensure the WHERE predicate and changes are applied against a valid data state after the preceding transaction finishes.

For example, an inventory table has a product with 1 unit remaining:

| SKU | QTY |
| --- | ---: |
| A-100 | 1 |

Two sessions run the same statement:

```sql
UPDATE inventory
SET qty = qty - 1
WHERE sku = 'A-100'
AND   qty >= 1;
```

Session A acquires the row lock and reduces quantity from 1 to 0 without committing yet. Session B runs the same statement and must wait.

If A COMMITs, B resumes against the new state. The condition `qty >= 1` is no longer true, so B must not decrement it further to -1; the number of updated rows can be 0. Oracle maintains write consistency by re-evaluating the necessary predicate/statement after a lock conflict under READ COMMITTED semantics.

### 6.2. Check the number of affected rows

Applications should check the DML row count:

```sql
UPDATE inventory
SET qty = qty - :requested_qty
WHERE sku = :sku
AND   qty >= :requested_qty;

-- In the application, check SQL%ROWCOUNT.
```

If the number of updated rows is 0, the product may not exist or the current quantity may be insufficient. The application needs to determine the appropriate business response instead of assuming the UPDATE always succeeded.

### 6.3. Atomic UPDATE reduces the gap between read and write

An error-prone pattern that easily creates race conditions:

1. SELECT quantity.
2. Application computes the new quantity.
3. Another session modifies the row.
4. Application runs UPDATE with the value calculated from stale data.

You can express the condition and calculation in a single UPDATE so Oracle locks and applies the change atomically on the row:

```sql
UPDATE inventory
SET qty = qty - :requested_qty
WHERE sku = :sku
AND   qty >= :requested_qty;
```

This is a useful pattern for inventory deduction or quota checks. You still need to handle row counts, transactions, and other business rules.

### 6.4. Not every race condition is solved automatically

If the application reads a value and then writes an absolute value computed externally, Oracle cannot infer the business intent. For example, two sessions both read balance 100, each computes a new balance of 90, and runs:

```sql
UPDATE accounts
SET balance = 90
WHERE account_id = 101;
```

Both can succeed one after the other, yet the final result is 90 instead of 80. This is a lost update caused by application read-compute-write logic. MVCC ensures read consistency; it does not automatically protect multi-step application decisions.

## 7. Lost updates and how to prevent them

### 7.1. Lost update scenario

Suppose the initial balance is 100:

```text
Session A                         Session B
---------                         ---------
SELECT balance -> 100
                                  SELECT balance -> 100
Compute new amount: 90
                                  Compute new amount: 90
UPDATE balance = 90
COMMIT
                                  UPDATE balance = 90
                                  COMMIT

Final result: 90
Expected if both subtract 10: 80
```

The two transactions do not overwrite each other simultaneously in the sense of bypassing row locks; they write sequentially after acquiring the lock. The problem is that Session B computed 90 from a stale read, so the second write wipes out A's effect.

### 7.2. Approach 1: use relative updates

If the business logic is to subtract 10, keep the calculation inside SQL:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE account_id = 101;
```

The two UPDATEs are serialized on the same row and each statement computes against the appropriate current value when its turn arrives. The result is 80 if both succeed.

### 7.3. Approach 2: SELECT FOR UPDATE before reading

```sql
SELECT balance
FROM   accounts
WHERE  account_id = 101
FOR UPDATE;

-- Compute and UPDATE within the same transaction.
```

The session acquires the lock before reading to make a decision. Other sessions wanting to lock/update the same row must wait. After computing and updating, COMMIT or ROLLBACK to release the lock.

Use this approach when business logic genuinely requires reading multiple attributes and computing before updating. Do not hold locks for long periods while calling external services or waiting for user input.

### 7.4. Approach 3: optimistic locking with a version column

You can add a version column:

```sql
ALTER TABLE accounts
ADD version_no NUMBER DEFAULT 0 NOT NULL;
```

The application reads balance and version_no. When updating:

```sql
UPDATE accounts
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
AND   version_no = :old_version;
```

If another transaction updated first, version_no changed and the second UPDATE affects 0 rows. The application detects the conflict, re-reads, and decides whether to retry or notify the user.

Optimistic locking is useful when conflicts are rare and you do not want to lock rows during long processing times.

## 8. SELECT FOR UPDATE and wait options

### 8.1. Locking rows to be processed

```sql
SELECT account_id,
       balance
FROM   accounts
WHERE  account_id = 101
FOR UPDATE;
```

The statement reads the matching rows and locks them so the current transaction can update them safely. The locks are held until COMMIT or ROLLBACK.

You can specify which table's rows are locked in a join query:

```sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM   employees e
JOIN   departments d
       ON d.department_id = e.department_id
WHERE  e.employee_id = 100
FOR UPDATE OF e.salary;
```

The OF clause identifies the table/column belonging to the table that the statement needs to lock according to Oracle syntax. Check SELECT FOR UPDATE restrictions when the query contains views, aggregates, DISTINCT, GROUP BY, or constructs that cannot be locked directly.

### 8.2. NOWAIT

```sql
SELECT *
FROM   accounts
WHERE  account_id = 101
FOR UPDATE NOWAIT;
```

If the row is already locked by another session, the statement does not wait and immediately returns an error (typically ORA-00054 for resource busy). The application can report busy status or retry according to policy.

### 8.3. WAIT n

```sql
SELECT *
FROM   accounts
WHERE  account_id = 101
FOR UPDATE WAIT 5;
```

Oracle waits up to 5 seconds to acquire the lock. If the time expires without acquiring the lock, the statement returns an error. The value n is measured in seconds.

### 8.4. SKIP LOCKED

```sql
SELECT task_id,
       status
FROM   job_queue
WHERE  status = 'READY'
FOR UPDATE SKIP LOCKED;
```

If a row is already locked by another session, the current session skips that row and continues retrieving other rows that can be locked. This approach is commonly used in queue/work distribution models so multiple workers process different rows.

SKIP LOCKED does not guarantee strict ordering fairness and does not replace job state management. Applications need to update status, commit, and handle workers dying mid-processing.

### 8.5. Choosing an option based on requirements

| Option | Behavior when row is locked | Common use case |
| --- | --- | --- |
| Default | Waits according to standard locking behavior | Transactions that can wait |
| NOWAIT | Returns an error immediately | Immediate busy feedback required |
| WAIT n | Waits up to n seconds | Bounded waiting allowed |
| SKIP LOCKED | Skips locked rows | Workers pulling tasks from a queue |

Do not choose SKIP LOCKED for screens that must guarantee displaying all matching rows; the result set may omit rows currently locked by other sessions.

## 9. Deadlock: two transactions waiting on each other

### 9.1. What is a deadlock?

A deadlock occurs when transactions hold resources needed by other transactions, forming a wait cycle that cannot resolve on its own.

Example:

```text
Session A                         Session B
---------                         ---------
UPDATE row 1                      UPDATE row 2
holds lock on row 1               holds lock on row 2

wants to UPDATE row 2             wants to UPDATE row 1
waits for B                       waits for A

        A waits for B  <---->  B waits for A
```

Neither session can make progress unless one transaction releases its lock.

### 9.2. Oracle detects deadlocks

Oracle detects the deadlock and returns an error:

```text
ORA-00060: deadlock detected while waiting for resource
```

Oracle typically resolves it by rolling back the involved statement of one transaction to break the wait cycle and release the necessary locks. Do not assume the entire transaction is automatically rolled back in every case; the application must handle the error, assess the transaction state, and roll back the business unit if it cannot continue safely.

### 9.3. Example of creating a deadlock in a test environment

Prepare the table:

```sql
CREATE TABLE demo_deadlock (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO demo_deadlock VALUES (1, 10);
INSERT INTO demo_deadlock VALUES (2, 20);
COMMIT;
```

Session A:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 1;
-- Not yet COMMITted.
```

Session B:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 2;
-- Not yet COMMITted.
```

Next, A runs:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 2;
```

A waits for the lock on row 2 held by B. Then B runs:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 1;
```

B waits for row 1 held by A. Oracle detects the wait cycle and one statement receives ORA-00060.

This is an intentional lab exercise; run it only on the demo table. After observing, check the state of each session and ROLLBACK/COMMIT to clean up the transactions.

### 9.4. How to reduce deadlock risk

- Update multiple rows in the same locking order across all transactions.
- Keep transactions short.
- Avoid waiting on users or calling network services while holding locks.
- Do not lock more rows than necessary.
- Design batches so workers rarely collide on the same set of rows.
- Handle ORA-00060 by rolling back and retrying the appropriate entire business unit, with limits and backoff.

Deadlocks are not always caused solely by programming bugs; complex operations involving triggers, FKs, indexes, and multiple tables can also create unexpected locking orders. When one occurs, inspect the deadlock graph in the trace file to identify the involved resources and SQL statements.

## 10. Table locks and DDL that can cause blocking

### 10.1. Regular DML on the same table

Multiple transactions can concurrently hold Row Exclusive table locks and modify different rows. This type of table lock is compatible with other regular DML in many scenarios.

### 10.2. LOCK TABLE

Example:

```sql
LOCK TABLE demo_write_wait
IN EXCLUSIVE MODE;
```

An EXCLUSIVE lock can prevent other DML on the table until the transaction ends. The LOCK TABLE statement must be used deliberately; table locks often significantly reduce concurrency.

Different table lock modes have different compatibility levels. Read Oracle documentation on LOCK TABLE before using it in a production system.

### 10.3. DDL and metadata locks

ALTER TABLE, DROP TABLE, and certain DDL statements require object locks to modify metadata. If another transaction is using the object and holding related locks, DDL may wait or fail depending on wait settings. DDL also has implicit commits according to Oracle rules.

Do not execute DDL inside a transaction that needs rollback capability like DML. Schedule schema changes and check sessions currently using the table before deployment.

## 11. Observing sessions waiting on locks

### 11.1. V$SESSION

A DBA or suitably privileged account can observe sessions:

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_session,
       seconds_in_wait,
       sql_id
FROM   v$session
WHERE  blocking_session IS NOT NULL
ORDER  BY seconds_in_wait DESC;
```

Useful columns:
- `SID` and `SERIAL#` identify the session within the instance.
- `EVENT` describes the wait event.
- `BLOCKING_SESSION` indicates the blocking session if Oracle can identify it.
- `SECONDS_IN_WAIT` shows the wait duration according to the view.
- `SQL_ID` helps locate the associated SQL statement.

Access to V$SESSION is typically granted by a DBA via appropriate privileges; there is no need to grant broad privileges to end-user applications just to run reports.

### 11.2. V$LOCK

You can observe held or requested locks:

```sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM   v$lock
WHERE  type IN ('TX', 'TM')
ORDER  BY type, sid;
```

- `TX` typically relates to transaction enqueues.
- `TM` typically relates to DML/table enqueues.
- `LMODE` is the currently held mode.
- `REQUEST` is the requested mode; a nonzero value indicates the session is waiting for that lock.
- `BLOCK` indicates potential blocking of other sessions according to the view.

Interpretation of ID1/ID2 and lock modes should be cross-referenced with Oracle documentation; do not draw conclusions from a single V$LOCK row without correlating it with V$SESSION and the relevant SQL.

### 11.3. Checking the waited-on object

You can join V$SESSION with DBA_OBJECTS when privileged:

```sql
SELECT s.sid,
       s.serial#,
       s.event,
       s.blocking_session,
       o.owner,
       o.object_name,
       s.row_wait_file#,
       s.row_wait_block#,
       s.row_wait_row#
FROM   v$session s
LEFT JOIN dba_objects o
       ON o.object_id = s.row_wait_obj#
WHERE  s.blocking_session IS NOT NULL;
```

The row_wait columns are only meaningful in certain specific wait states. They do not always identify a blocked row; inspect the event and session state.

### 11.4. Ordered investigation steps

1. Identify the waiting session and the blocking session.
2. Check the event, SQL_ID, and wait duration.
3. Retrieve the SQL text and related transaction if privileged.
4. Identify the conflicting row/table/resource.
5. Verify whether the blocker still needs the transaction or was abandoned.
6. Coordinate with the application owner before terminating the session.
7. After resolving, monitor to verify whether blocking recurs.

Do not kill a session simply because it appears in the blocking_session column. The session may be executing a valid transaction; forced termination can trigger a large rollback and impact the application.

## 12. Business scenario: transferring funds between two accounts

### 12.1. Operations must be in the same transaction

A transfer needs to debit the source account and credit the destination account:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :from_account
AND balance >= :amount;

-- Application checks the number of updated rows.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :to_account;

-- Verify both operations before running COMMIT.
```

Both UPDATEs must belong to the same transaction. If the second operation fails, the application runs ROLLBACK so it does not leave a state where money was debited without being credited.

### 12.2. Lock in a consistent order

If two sessions transfer funds in opposite directions between the same two accounts, one session may lock account 101 then 202, while the other locks 202 then 101. This ordering can cause a deadlock.

You can reduce the risk by locking both accounts in a consistent order, such as ascending account_id, before updating:

```sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id IN (:from_account, :to_account)
ORDER  BY account_id
FOR UPDATE;
```

After locking and checking the balance, execute both UPDATEs within the same transaction. Confirm that both rows were locked; if an account does not exist, abort the operation.

### 12.3. Do not hold locks while waiting for users

A bad workflow is:
1. SELECT FOR UPDATE.
2. Display confirmation screen.
3. Wait several minutes for the user.
4. Only then UPDATE and COMMIT.

During the wait, the rows are locked and other transactions may be blocked. Collect user confirmation first, then open a short transaction to lock, re-validate conditions, and perform the update.

## 13. Queue scenario: multiple workers claiming tasks

### 13.1. Goal

A job queue table has READY rows. Multiple workers need to claim work without processing the same row. `FOR UPDATE SKIP LOCKED` lets workers skip rows currently locked by other workers.

### 13.2. Example of claiming a batch of jobs

```sql
SELECT job_id,
       payload
FROM   job_queue
WHERE  status = 'READY'
ORDER  BY priority DESC, created_at
FOR UPDATE SKIP LOCKED;
```

The application retrieves the locked rows, updates status to PROCESSING, and COMMITs. Syntax for limiting the number of rows may depend on version and query style; test in the exact target release before using in production.

### 13.3. Essentials beyond SKIP LOCKED

- Record worker/lease or claim timestamp.
- Have a recovery mechanism for jobs if a worker dies.
- Update status and commit consistently.
- Design idempotent processing so retries do not cause duplicate side effects.
- Monitor jobs stuck in PROCESSING.
- Do not interpret SKIP LOCKED results as a complete list of all READY jobs.

SKIP LOCKED is a concurrent work distribution mechanism, not a complete queue system.

## 14. Common mistakes and misconceptions

| Symptom or Misconception | Explanation |
| --- | --- |
| Regular SELECT waits for UPDATE on the same row | Usually no; SELECT uses consistent read, though exceptions exist due to other locks/resources |
| Second UPDATE runs forever | It may be waiting for the first transaction to commit/roll back |
| UPDATE statement finished yet the row is still locked | Transaction has not yet COMMITted/ROLLBACKed |
| Two UPDATEs on different rows still wait | Check triggers, FKs, table locks, indexes/constraints, or shared resources |
| SELECT FOR UPDATE is the same as regular SELECT | False; FOR UPDATE requests row locks |
| NOWAIT returns stale data | No; NOWAIT changes how waiting for the lock is handled |
| SKIP LOCKED always returns all rows matching WHERE | False; currently locked rows are skipped |
| MVCC prevents lost updates in all cases | False; applications can write values computed from old snapshots |
| ORA-00060 is an undo error | No; it is a deadlock |
| COMMIT after every SQL statement is always good | Can break business boundaries and alter lock hold durations |
| EXCLUSIVE table lock only locks one row | False; it operates at the table level |
| Killing the blocker is always safe | False; the transaction may have to roll back and impact the application |

### 14.1. Distinguishing scenarios

- **Row lock wait:** writer waiting on a writer holding a row lock.
- **Table lock wait:** operation requiring a table lock incompatible with existing locks.
- **Deadlock:** wait cycle among multiple transactions; Oracle detects it and reports ORA-00060.
- **Snapshot too old:** missing undo needed for consistent read; not a locking error.
- **Serialization conflict:** SERIALIZABLE transactions may receive ORA-08177.

Diagnose the exact issue type before changing timeouts, undo, or application code.

## 15. Design and operations workflow

When designing concurrent read/write operations, determine:

1. **What snapshot does the reader need?** Single statement or multiple statements in a transaction?
2. **Are there competing writers?** Which rows might be modified by multiple sessions?
3. **Is proactive locking needed?** SELECT FOR UPDATE or atomic UPDATE?
4. **Is the update predicate safe?** Can business conditions be placed in WHERE?
5. **Is there a lost update risk?** Use SQL expressions, pessimistic locking, or a version column?
6. **Is there a deadlock risk?** Do all transactions lock in the same order?
7. **Is a timeout needed?** Choose default, NOWAIT, or WAIT n according to UX.
8. **Do busy rows need to be skipped?** SKIP LOCKED is only appropriate for queues/work distribution.
9. **How long is the transaction?** Reduce hold times for row/table locks.
10. **Is blocking observable?** Monitor V$SESSION, V$LOCK, SQL_ID, and deadlock traces.

Practical principles:
- Keep transactions short with clear business boundaries.
- Use regular SELECT when only reading data.
- Use SELECT FOR UPDATE when rows must be locked before reading and deciding.
- Prefer atomic conditional UPDATEs for simple operations.
- Check the number of affected rows after DML.
- Lock multiple rows in a consistent order to reduce deadlocks.
- Handle timeouts and bounded retries.
- Do not terminate a blocker without understanding its transaction.

## 16. Practice exercises

### Exercise 1 — Reader sees old version

Session A UPDATEs quantity from 10 to 9 without committing. Session B SELECTs that row.

**Expected:** B sees 10 via consistent read.

### Exercise 2 — Writer must wait

While A has not committed, B UPDATEs the same row.

**Expected:** B waits on the row lock. B proceeds only after A COMMITs/ROLLBACKs.

### Exercise 3 — Two different rows

A UPDATEs item_id=1, B UPDATEs item_id=2 in the same table.

**Expected:** no direct row conflict; both sessions can execute concurrently if no other shared resource conflicts.

### Exercise 4 — Duplicate-key INSERT

A INSERTs a new primary key without committing. B INSERTs the same key.

**Expected:** B may wait for transaction A's outcome; if A commits, B gets a uniqueness violation; if A rolls back, B can proceed.

### Exercise 5 — SELECT FOR UPDATE NOWAIT

A locks a row via UPDATE. B runs SELECT FOR UPDATE NOWAIT.

**Expected:** B returns an error immediately instead of waiting.

### Exercise 6 — SELECT FOR UPDATE WAIT

Repeat using WAIT 3.

**Expected:** B waits up to 3 seconds and then returns an error if the lock is not released.

### Exercise 7 — SKIP LOCKED

A locks some READY rows in the queue. B runs SELECT FOR UPDATE SKIP LOCKED.

**Expected:** B skips the rows locked by A and can retrieve other READY rows.

### Exercise 8 — Lost update

Two sessions both SELECT balance 100, each computes 90, and runs UPDATE balance=90.

**Expected:** final value can be 90. Repeat using UPDATE balance=balance-10 to observe the result 80.

### Exercise 9 — Optimistic locking

Add version_no. Two sessions read the same version, the first session updates and increments version, and the second session runs UPDATE with the old version.

**Expected:** the second UPDATE affects 0 rows and the application detects the conflict.

### Exercise 10 — Deadlock

Use table demo_deadlock: A locks row 1, B locks row 2, then A needs row 2 and B needs row 1.

**Expected:** Oracle detects the deadlock and one statement receives ORA-00060.

### Exercise 11 — Observing V$SESSION

While one session is waiting, query V$SESSION to find blocking_session, event, seconds_in_wait, and SQL_ID.

**Goal:** understand how to identify blockers and waiters.

### Exercise 12 — Safe funds transfer

Write a transaction debiting the source account, crediting the destination account, checking balance, and locking accounts in account_id order.

**Goal:** guarantee atomicity and reduce deadlock risk.

## 17. Oracle Reference Documentation

- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, concurrency, and transactions.
- [Oracle Database Concepts — Data Concurrency and Consistency: Locking](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): data locking mechanisms.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE, WAIT, NOWAIT, and SKIP LOCKED.
- [Oracle Database SQL Language Reference — LOCK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOCK-TABLE.html): table locking and lock modes.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): managing sessions, transactions, and database resources.
- [Oracle Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session and blocking information.
- [Oracle Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): held or requested lock information.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/): ORA-00054, ORA-00060, and related errors.

In Oracle, read consistency allows regular SELECTs to read a committed snapshot using undo while writers modify rows. Competing writes on the same row require row locks and may have to wait; SELECT FOR UPDATE also proactively acquires locks. Distinguish normal blocking, lost updates, and deadlocks, choose atomic updates or locking suited to business logic, keep transactions short, and monitor waiting sessions to operate the system safely.
