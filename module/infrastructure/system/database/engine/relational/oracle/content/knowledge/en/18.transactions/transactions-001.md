# Business Units of Work and ACID Properties in Oracle

A money transfer typically consists of multiple operations: checking the account, debiting the source account, crediting the destination account, and recording the history. If only one step succeeds and then the application encounters an error, the data can end up in an invalid state: money is debited without being credited, or the balance changes without a corresponding history record. To prevent that situation, operations belonging to the same **business unit of work** must be executed within a transaction with clear boundaries.

In Oracle Database, a transaction is a unit of work that the database engine commits to executing according to the **ACID** properties:

- **Atomicity:** all changes in a transaction are confirmed together, or uncommitted changes are rolled back.
- **Consistency:** the transaction takes data from one valid state to another valid state according to protected rules.
- **Isolation:** concurrent transactions do not see each other's uncommitted data; the isolation level determines how they observe committed changes.
- **Durability:** after a successful commit in the default mode, Oracle guarantees that changes can be recovered after a failure thanks to redo.

This lesson belongs to the **Transactions** group of Database Engine Relational Oracle. It focuses on defining transaction boundaries by business logic, how Oracle manages commit/rollback, undo/redo, read consistency, row locks, and isolation levels, as well as how to control transactions from PL/SQL and JDBC.

After this lesson, you will be able to:

- Identify which operations must belong to the same business unit of work.
- Explain the four ACID properties using concrete data examples.
- Use COMMIT, ROLLBACK, and SAVEPOINT at the right time.
- Understand how Oracle starts a transaction when executing DML and handles DDL with implicit commit.
- Distinguish between undo and redo in rollback, read consistency, and crash recovery.
- Understand READ COMMITTED, SERIALIZABLE, and READ ONLY in Oracle.
- Predict row locking behavior, SELECT FOR UPDATE, deadlocks, and ORA-08177 errors.
- Manage transactions in JDBC and avoid autocommit breaking a unit of work.
- Design retries, idempotency, and handle external side effects outside the database safely.

> **Example scope:** Syntax is illustrated for Oracle Database 19c. Tables with the `_LAB` suffix are independent practice tables. Do not run transfer examples, DDL, or locking tests on a live application schema.

## 1. What Is a Business Unit of Work?

A business unit of work is a set of data changes that must be treated as a single complete outcome from a business perspective. It usually corresponds to an action that a user or system understands as one single operation: placing an order, making a payment, transferring money, issuing inventory, finalizing an invoice, or recording a registration.

Example of a money transfer:

1. Identify the source account and destination account.
2. Debit the transfer amount from the source account.
3. Credit the same amount to the destination account.
4. Insert a transfer history record.
5. Confirm all changes.

Steps 2, 3, and 4 must not become independent transactions if the business logic requires them to succeed together. If step 3 fails after step 2 has already committed, money is lost from the system from a business standpoint.

~~~text
ONE ACTION: TRANSFER 500
          |
          v
  Debit 500 from account A
          |
          v
  Credit 500 to account B
          |
          v
  Record transaction history
          |
          v
        COMMIT
          |
          v
   ONE COMPLETE OUTCOME

If a step fails before COMMIT:
          |
          v
       ROLLBACK
          |
          v
  Discard transaction changes
~~~

### 1.1. A Transaction Boundary Does Not Have to Equal One SQL Statement

A single UPDATE statement can be a simple transaction. However, placing an order might require multiple statements:

- Create the order header.
- Create one or more order lines.
- Decrement inventory.
- Record a receivable or payment.
- Update the order status.

If these changes must coexist together, place them in a single transaction controlled by one responsible layer. When all steps complete, that layer commits. When an error occurs, that layer rolls back.

### 1.2. Do Not Bundle Everything into a Long Transaction

A transaction should be broad enough to cover the unit of work, yet short enough not to hold locks and undo longer than necessary. Avoid:

- Opening a transaction and waiting for user input.
- Holding a transaction open while calling a payment API, sending an email, or uploading a large file.
- Reading thousands of rows and holding locks while performing unrelated processing.
- Committing each small step within a business operation whose steps must succeed together.

If a business process spans multiple services or takes several minutes, it usually needs a stateful multi-step workflow with idempotency and compensating mechanisms (saga), rather than keeping a database transaction open throughout.

## 2. ACID Viewed Through a Money Transfer

Suppose account A has 1,000 and account B has 300. A user transfers 200 from A to B. The valid result must be A with 800 and B with 500, while the history records the exact amount of 200.

| Property | Question | Required Guarantee |
| --- | --- | --- |
| Atomicity | If one step fails, is data left half-finished? | Do not keep partial uncommitted changes |
| Consistency | Can a balance become negative or history mismatch? | Business rules/constraints remain satisfied |
| Isolation | Do two concurrent transfers overwrite each other or read uncommitted data? | Transactions observe data per isolation semantics and conflicts are handled |
| Durability | After commit, if the server crashes, is the transaction lost? | Redo allows recovery of committed changes |

ACID is a property of database transactions, but **Consistency also depends on the rules that the application and schema actually define**. Oracle does not automatically know that total debited funds must equal total credited funds; developers must express that invariant with appropriate SQL, constraints, triggers, or business logic.

## 3. Atomicity — All or Nothing

### 3.1. A Transaction with Multiple DML Statements

~~~sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 200
WHERE account_id = 20;

INSERT INTO transfer_history (
    transfer_id, from_account_id, to_account_id, amount, created_at
)
VALUES (
    9001, 10, 20, 200, SYSTIMESTAMP
);

COMMIT;
~~~

The three changes belong to the same transaction if there is no intervening COMMIT/ROLLBACK. If the INSERT statement fails and the application rolls back the transaction, the two uncommitted UPDATEs are also undone.

### 3.2. A Failed Statement Does Not Automatically Roll Back All Previous Statements

This is an important point to understand in Oracle:

- A failed SQL statement is normally rolled back at the scope of that statement (statement-level rollback).
- Previous successful DML statements in the same transaction remain temporarily in effect and can still be committed.
- The application must decide to roll back the entire transaction when the business unit of work cannot complete.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 10;

-- The following INSERT may fail due to a constraint violation.
INSERT INTO transfer_history (
    transfer_id, from_account_id, to_account_id, amount, created_at
)
VALUES (
    9001, 10, 20, -200, SYSTIMESTAMP
);
~~~

If the INSERT fails, the preceding debit UPDATE does not disappear automatically. The transaction still has uncommitted changes. If the application catches the error and proceeds to COMMIT, the balance can be debited without a history record. Therefore, the layer owning the transaction must roll back when the business operation fails.

### 3.3. COMMIT and ROLLBACK

~~~sql
-- Confirm the changes in the current transaction.
COMMIT;

-- Discard all uncommitted changes in the current transaction.
ROLLBACK;
~~~

After COMMIT, the changes become confirmed results and cannot be undone with a normal ROLLBACK. To reverse a committed business operation, the application needs a new compensating transaction (such as creating a refund entry), with its own audit trail.

ROLLBACK undoes uncommitted changes in the current transaction. It does not undo a previously committed transaction.

### 3.4. Automatic Transaction Termination When a Session Ends

If a session ends normally while a transaction is still open, the client/driver typically needs to roll back or handle the transaction before closing the connection; you should not rely on implicit behavior. If a session terminates abnormally, Oracle recovers/rolls back uncommitted transactions via its recovery mechanism. Applications must still proactively commit or roll back to release resources at the proper time.

## 4. Consistency — Maintaining Data Invariants

Consistency means that a transaction must move the database from one state that satisfies the rules to another state that also satisfies the rules. Those rules can be enforced across multiple layers.

### 4.1. Using Constraints for Data Invariants

Example accounts table:

~~~sql
CREATE TABLE account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(60 CHAR) NOT NULL,
    balance NUMBER(18,2) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative
        CHECK (balance >= 0)
);
~~~

Protected rules:

- Each `account_id` is unique.
- `account_name` cannot be NULL.
- `balance` cannot be NULL and cannot be negative.

Constraints are checked by the database regardless of whether changes come from a Java application, PL/SQL, a SQL client, or a batch job. This is a critical safeguard for data-level invariants.

### 4.2. Constraints Do Not Replace All Business Rules

A single-row CHECK constraint cannot easily express a rule that total debited and credited amounts across multiple rows must balance. Some invariants require:

- Foreign keys to protect referential integrity.
- Unique constraints to protect uniqueness.
- Check constraints to protect single-row conditions.
- Transaction logic to update multiple tables together.
- Triggers or other business mechanisms in appropriate cases.

Do not put all business logic into triggers indiscriminately; consider testability, execution order, error handling, and rule clarity.

### 4.3. Checking Balances Safely

A pattern prone to race conditions:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10;

-- The application reads balance, computes balance - amount itself,
-- then sends an UPDATE using the previously read value.
~~~

Two sessions can both read a balance of 100, each intending to transfer 80. If both then write a value calculated from the stale balance, one update may overwrite the other or produce an unintended business outcome.

A safer approach is to put the sufficient-balance condition directly into the UPDATE itself:

~~~sql
UPDATE account_lab
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Then check the number of affected rows:

- 1 row: the account exists and has sufficient balance at the time the UPDATE executes.
- 0 rows: the account was not found or balance is insufficient; the application can query separately to distinguish if the business logic requires it.

The UPDATE locks the row being modified and evaluates the condition in the DML execution context, avoiding the read-then-write pattern based on a stale value without control.

### 4.4. Deferred Constraints

Oracle supports declaring certain constraints as DEFERRABLE. When a constraint is deferred, validation can be performed at COMMIT time instead of after each statement, depending on the constraint state.

Conceptual example:

~~~sql
ALTER TABLE transfer_line_lab
ADD CONSTRAINT fk_transfer_header_lab
FOREIGN KEY (transfer_id)
REFERENCES transfer_header_lab(transfer_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Within a transaction, a deferred constraint can allow an intermediate state that temporarily does not satisfy the relationship, as long as the final state at commit is valid. Deferrable constraints can be controlled with SET CONSTRAINTS.

Not every constraint can be deferred. NOT NULL and CHECK constraints are not controlled the same way as deferred foreign key/unique constraints. Check the constraint type and Oracle syntax before designing around deferred validation.

## 5. Isolation — What Do Concurrent Transactions See?

Oracle uses multi-version read consistency. Instead of forcing read queries to wait for every writer, Oracle can provide a consistent version of data from undo so queries see the state appropriate to their snapshot point.

### 5.1. Oracle Does Not Allow Reading Uncommitted Data

Suppose Session A executes:

~~~sql
UPDATE account_lab
SET balance = 500
WHERE account_id = 10;
-- Not committed yet.
~~~

Session B executes:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10;
~~~

In the default READ COMMITTED level, Session B does not read A's uncommitted value of 500. It reads the most recently committed version as of the time B's statement began. This is why Oracle does not provide dirty reads in the style of READ UNCOMMITTED.

If Session A rolls back, the uncommitted value disappears. If Session A commits, a new statement in B can see the new value.

### 5.2. READ COMMITTED Is the Default Level

In READ COMMITTED:

- Each SELECT statement has its own read-consistent snapshot as of the time the statement begins.
- SELECT never sees uncommitted data from other transactions.
- Two SELECT statements in the same transaction can see different committed states if another transaction commits in between.
- DML locks the rows it modifies; another writer needing to modify the same row must wait or handle the lock according to the locking mode.

Example:

~~~sql
-- Session B, statement 1:
SELECT balance FROM account_lab WHERE account_id = 10;

-- Session A updates and COMMITs.

-- Session B, statement 2:
SELECT balance FROM account_lab WHERE account_id = 10;
~~~

Session B's two SELECT statements can return different values. This is not a dirty read: each statement reads a valid committed snapshot at its own point in time.

### 5.3. SERIALIZABLE Provides a Transaction-Level Snapshot

You can start a transaction at the SERIALIZABLE level:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM account_lab
WHERE account_id = 10;

-- Subsequent queries in the transaction read the snapshot
-- as of the time the transaction began.

COMMIT;
~~~

The SET TRANSACTION statement must be executed at the start of the transaction, before other statements in that transaction. With SERIALIZABLE, queries in the transaction see a consistent snapshot from the time the transaction started. If the transaction attempts to modify a row that was modified by another transaction after that snapshot, Oracle can return error ORA-08177: can't serialize access for this transaction.

The application needs to roll back and may retry **the entire transaction** if business rules allow. Do not simply re-run only the final UPDATE statement, because earlier decisions may have been based on an outdated snapshot.

### 5.4. READ ONLY Transactions

If you need to run a group of reporting queries on the same snapshot without writing data:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM account_lab;
SELECT SUM(balance) FROM account_lab;
SELECT account_id, balance FROM account_lab;

COMMIT;
~~~

A READ ONLY transaction uses a read-consistent snapshot for queries and disallows DML within that transaction. This is a useful option for a multi-statement read workload that needs the same view of the data. It does not replace write transactions, nor does it make multiple SELECTs read the latest data independently per statement like READ COMMITTED.

### 5.5. Comparing Commonly Used Transaction Modes

| Mode | Read Snapshot | Dirty Read | Data Writes |
| --- | --- | --- | --- |
| READ COMMITTED | Per statement | No | Yes |
| SERIALIZABLE | One transaction-level snapshot | No | Yes, may encounter ORA-08177 on conflict |
| READ ONLY | One transaction-level snapshot | No | No |

Oracle does not support READ UNCOMMITTED in a way that allows reading uncommitted data. When consistency across multiple statements is needed, consider SERIALIZABLE or READ ONLY and understand the impact on concurrent write errors, transaction duration, and undo.

## 6. Durability — What Happens After COMMIT?

### 6.1. Redo Log and the Commit Guarantee

Oracle records change information in the redo log. When COMMIT succeeds under the default configuration, the redo required for the transaction is durably written to the online redo log before Oracle confirms the commit to the client. Modified data blocks may be written to data files later by DBWR; commit does not require every data block to be flushed immediately.

When an instance crashes, Oracle uses redo to roll forward necessary changes and uses undo to roll back uncommitted transactions during recovery. Therefore, committed data can be recovered even if the corresponding data blocks had not yet been written to data files at the time of the crash.

### 6.2. COMMIT Is Not Simply Writing the Entire Table to Disk Immediately

Different components serve distinct roles:

| Component | General Role |
| --- | --- |
| Online redo log | Stores redo records for recovering changes |
| LGWR | Writes redo buffer to redo log files |
| DBWR | Writes dirty data blocks from buffer cache to data files |
| Undo segments | Holds information needed for rollback and building read-consistent versions |
| Checkpoint | Coordinates write progress and recovery; does not replace redo |

A successful COMMIT does not mean DBWR has written all of the transaction's data blocks to data files. Durability relies on redo protected under the commit protocol.

### 6.3. Commit Settings Can Affect Response Timing

Oracle provides options related to commit write/wait behavior. The default configuration uses commit wait so the required redo is written. Certain NOWAIT/asynchronous modes can change when the client receives a response and what guarantees exist at return time. Do not change `COMMIT_WRITE` or related parameters merely to reduce latency without understanding durability requirements and DBA policy.

### 6.4. Commit Succeeds but the Client Loses Connection

A tricky scenario: the server may have committed, but the COMMIT response is lost in transit. The application cannot know for certain whether the transaction committed or not. If it automatically resends the transfer request, it may create a duplicate transaction.

This is why business systems need an **idempotency key** or unique request identifier. The database should store the unique business key together with the outcome; when a client retries the same request, the application recognizes that the request was already processed and returns the previous result rather than executing it a second time.

## 7. Undo and Redo: Two Distinct Mechanisms

### 7.1. Undo Is Used for Rollback and Read Consistency

Undo stores information about data versions prior to modification. Oracle uses undo to:

- Roll back changes of uncommitted transactions.
- Provide older versions to queries that require read consistency.
- Support certain logical recovery operations such as flashback query within appropriate configuration/retention limits.

Undo is not a full backup and does not replace backups. Undo retention and undo space capacity affect how long older versions can be retained for long-running queries.

### 7.2. Redo Is Used for Recovery

Redo records the changes needed to recover the database. It supports rolling forward during instance/media recovery. Redo also logs changes made to undo so that recovery operations can reconstruct the appropriate state.

### 7.3. Comparison Table

| Mechanism | Key Question | Where It Is Used |
| --- | --- | --- |
| Undo | How do we revert to a prior version or roll back uncommitted changes? | ROLLBACK, consistent read, recovery |
| Redo | How do we reapply changes after a failure? | Instance recovery, media recovery |

Do not think of undo as "uncommitted data" and redo as "committed data" in absolute terms. Redo is generated for database changes, including undo changes; whether a transaction ultimately commits or rolls back is resolved during recovery using both redo and undo.

### 7.4. ORA-01555: snapshot too old

A long-running read query needs an older version of data from undo. If the required undo blocks have been overwritten/reused before the query finishes, Oracle can raise `ORA-01555: snapshot too old`.

Causes and remedies depend on the workload:

- A read transaction runs too long while the system has heavy DML activity.
- Undo tablespace/retention cannot accommodate the query duration.
- The query scans a large volume of data or performs excessive unnecessary work.
- Batch designs commit too frequently or read data in an unsuitable pattern.

Do not fix this by blindly increasing undo retention. The DBA needs to inspect undo usage, workload, query plan, retention guarantee, and storage capacity.

## 8. COMMIT, ROLLBACK, and SAVEPOINT

### 8.1. SAVEPOINT Creates a Rollback Marker Inside a Transaction

~~~sql
UPDATE account_lab
SET balance = balance - 50
WHERE account_id = 10;

SAVEPOINT after_debit;

UPDATE account_lab
SET balance = balance + 50
WHERE account_id = 20;

-- To discard changes made after the savepoint:
ROLLBACK TO after_debit;

-- Afterward, you can continue operating or rollback/commit the transaction.
~~~

`ROLLBACK TO SAVEPOINT` undoes changes made after the specified savepoint, without ending the transaction. Changes before the savepoint remain part of the transaction.

### 8.2. COMMIT Clears Savepoints

After COMMIT, the transaction ends and old savepoints are no longer valid. A subsequent full-transaction ROLLBACK cannot go back before the commit.

### 8.3. SAVEPOINT Does Not Replace Transaction Boundaries

Savepoints are useful when a unit of work has an optional branch that can be skipped while preserving earlier work. For example, an application might try writing a secondary note, roll back to a savepoint if the secondary part fails, and then continue with the main business logic if policy allows.

Do not use savepoints to mask errors that violate core invariants. If a mandatory business step fails, roll back the entire transaction.

### 8.4. DDL Causes Implicit Commit in Oracle

Oracle issues an implicit commit before DDL and after DDL succeeds. For example, CREATE TABLE, ALTER TABLE, DROP TABLE, TRUNCATE TABLE, and many administrative commands do not belong to the same DML transaction in the way beginners might expect.

~~~sql
UPDATE account_lab
SET balance = balance - 100
WHERE account_id = 10;

CREATE TABLE temporary_lab (id NUMBER);

ROLLBACK;
~~~

The UPDATE may already have been implicitly committed before `CREATE TABLE` executes; the subsequent ROLLBACK does not undo that UPDATE. Therefore:

- Do not run DDL in the middle of a DML unit of work that requires atomicity.
- Do not treat TRUNCATE as a rollbackable operation like DELETE.
- Separate migrations/schema changes from business transactions.
- Check whether deployment tools automatically execute DDL or commit.

## 9. Row Locking in Oracle

### 9.1. DML Locks Modified Rows

UPDATE/DELETE locks the rows they affect. Locks are held until the transaction issues COMMIT or ROLLBACK. Two transactions can update different rows concurrently; if both need to update the same row, the second transaction must wait or handle an error depending on the situation.

Example:

~~~sql
-- Session A
UPDATE account_lab
SET balance = balance - 10
WHERE account_id = 10;
-- Not committed yet.

-- Session B
UPDATE account_lab
SET balance = balance + 20
WHERE account_id = 10;
-- B will wait until A commits/rolls back.
~~~

After A commits, B proceeds based on the appropriate state; if A rolls back, B proceeds once the lock is released. Applications should configure timeouts and handle waiting according to policy.

### 9.2. Standard SELECT Does Not Lock Rows for Reading

Oracle uses multiversion read consistency. A standard SELECT does not acquire row locks like UPDATE does. Thus readers and writers generally do not block each other in the traditional read/write lock manner: SELECT can read a committed version while a writer is modifying the row.

This does not mean all lock types never conflict. DDL, metadata locks, explicit locks, SELECT FOR UPDATE, and special scenarios can still cause waits.

### 9.3. SELECT FOR UPDATE

When an application needs to read a row and then update based on that same row, it can lock the row beforehand:

~~~sql
SELECT balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE;
~~~

The lock is held until COMMIT/ROLLBACK. Other transactions wanting to modify that row must wait. This pattern is useful when reading state before making a multi-step decision, but the transaction must stay short and must always terminate.

### 9.4. WAIT, NOWAIT, and SKIP LOCKED

~~~sql
-- Allow waiting for the lock.
SELECT account_id, balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE WAIT 5;

-- Do not wait: raise an error immediately if the row is locked.
SELECT account_id, balance
FROM account_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;

-- Skip locked rows, commonly used for worker queues.
SELECT job_id, status
FROM job_queue_lab
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED is useful when multiple workers dequeue jobs from a queue: a worker skips rows currently locked by another worker to pick up another row. It does not guarantee fair ordering and requires a clear status-update/commit workflow so jobs are not permanently missed.

### 9.5. Deadlock

A deadlock occurs when transactions wait on each other's locks in a cycle:

~~~text
Session A locks row 1, waits for row 2
Session B locks row 2, waits for row 1
             |
             v
          DEADLOCK
             |
             v
Oracle detects the cycle and aborts one statement
~~~

Oracle detects deadlocks and raises ORA-00060 for one statement. The affected transaction should not go ahead and commit as if the entire unit of work succeeded; the application must handle the error and typically roll back the entire transaction.

Reduce deadlocks by:

- Updating multiple rows in the same lock acquisition order across all code paths.
- Keeping transactions short.
- Avoiding network calls or waiting for user input while holding locks.
- Using appropriate indexes for UPDATE/DELETE predicates to avoid unnecessary scans and range locking.
- Handling deadlock errors in a controlled manner, retrying the entire unit of work if the operation is idempotent and permitted.

## 10. Isolation and Common Anomalies

### 10.1. Dirty Read

A dirty read is reading uncommitted data from another transaction. Oracle does not allow dirty reads in READ COMMITTED/SERIALIZABLE; readers see committed versions.

### 10.2. Non-Repeatable Read Under READ COMMITTED

A transaction runs two SELECTs with the same condition. Another transaction commits a change between the two statements. The second SELECT may see the new value because each statement has its own snapshot.

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  UPDATE balance = 120
                                  COMMIT
SELECT balance = 120
~~~

This is valid READ COMMITTED behavior. If a business operation needs multiple reads on the same snapshot, consider SERIALIZABLE or READ ONLY; if it needs to lock rows for update, consider SELECT FOR UPDATE or conditional DML.

### 10.3. Phantom Rows

In READ COMMITTED, a subsequent SELECT may see new rows committed by another transaction that match the predicate, because a new statement snapshot is created. This is a change in the row set between statements.

SERIALIZABLE/READ ONLY provides a transaction-level snapshot so read queries are more consistent. However, SERIALIZABLE can raise ORA-08177 on write conflicts; do not choose this level merely out of a desire to "lock the whole table."

### 10.4. Lost Update and How to Protect Against It

A lost update can happen when an application reads a value, computes a new value on the client, and writes it back based on stale data without checking the version.

Dangerous example:

~~~sql
-- Client reads balance = 100.
-- Client calculates new_balance = 90.
UPDATE account_lab
SET balance = 90
WHERE account_id = 10;
~~~

If another transaction credited the account to 120 after the client read it, an UPDATE hardcoding 90 can overwrite the other transaction's change.

Ways to protect against this:

1. Compute directly in SQL: `SET balance = balance - :amount`.
2. Add an optimistic version condition: `WHERE account_id=:id AND version_no=:old_version`, then increment `version_no`.
3. Use `SELECT FOR UPDATE` before reading and updating if the lock must be held across a workflow.
4. Use `SERIALIZABLE` when the business model and retry capability fit.

Optimistic locking example:

~~~sql
UPDATE account_lab
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
~~~

If `SQL%ROWCOUNT = 0`, the data has changed or the record no longer exists. The application needs to re-read and decide how to handle it; do not overwrite blindly.

## 11. Money Transfer Example in PL/SQL

### 11.1. Creating Lab Tables and Data

~~~sql
CREATE TABLE transfer_account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(60 CHAR) NOT NULL,
    balance NUMBER(18,2) NOT NULL,
    CONSTRAINT ck_transfer_balance_lab CHECK (balance >= 0)
);

CREATE TABLE transfer_history_lab (
    transfer_id NUMBER PRIMARY KEY,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_transfer_amount_lab CHECK (amount > 0),
    CONSTRAINT fk_transfer_from_lab FOREIGN KEY (from_account_id)
        REFERENCES transfer_account_lab(account_id),
    CONSTRAINT fk_transfer_to_lab FOREIGN KEY (to_account_id)
        REFERENCES transfer_account_lab(account_id)
);

INSERT INTO transfer_account_lab VALUES (10, 'Account A', 1000);
INSERT INTO transfer_account_lab VALUES (20, 'Account B', 300);
COMMIT;
~~~

### 11.2. PL/SQL Transfer Block

The example below executes two UPDATEs and one INSERT in the same transaction. The PL/SQL block does not COMMIT itself; the caller decides when to end the unit of work:

~~~sql
DECLARE
    v_amount NUMBER := 200;
    v_from_account NUMBER := 10;
    v_to_account NUMBER := 20;
BEGIN
    IF v_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Amount must be positive');
    END IF;

    IF v_from_account = v_to_account THEN
        RAISE_APPLICATION_ERROR(-20002, 'Source and destination must differ');
    END IF;

    UPDATE transfer_account_lab
    SET balance = balance - v_amount
    WHERE account_id = v_from_account
      AND balance >= v_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20003, 'Source account missing or insufficient funds');
    END IF;

    UPDATE transfer_account_lab
    SET balance = balance + v_amount
    WHERE account_id = v_to_account;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20004, 'Destination account not found');
    END IF;

    INSERT INTO transfer_history_lab (
        transfer_id, from_account_id, to_account_id, amount
    )
    VALUES (
        9001, v_from_account, v_to_account, v_amount
    );
END;
/
~~~

After the block runs successfully, the changes are still uncommitted. The caller can verify the result and then COMMIT; if an error occurs, the caller must ROLLBACK the entire transaction.

~~~sql
COMMIT;

SELECT account_id, balance
FROM transfer_account_lab
ORDER BY account_id;
~~~

Result after commit: account 10 has 800, account 20 has 500, and the history has one row transferring 200.

### 11.3. What Happens When an Error Occurs?

If the destination account does not exist or the history INSERT violates a constraint, the PL/SQL block raises an exception. The failed statement is rolled back at the statement level, but preceding DML statements in the transaction may still be pending. The caller needs to roll back:

~~~sql
ROLLBACK;
~~~

Do not catch the exception, ignore it, and let the caller commit if the transaction has not reached a valid business state.

### 11.4. Why Should Every Procedure Not COMMIT Internally?

A sub-procedure generally should not COMMIT on its own if it is only part of a larger unit of work. For example, a caller might need to:

1. Create an order.
2. Insert order lines.
3. Decrement inventory.
4. Record the payment ledger.

If the inventory-decrement procedure commits on its own, the caller cannot roll back the entire operation when recording the payment ledger fails. Typically, the application service layer or an orchestrating business procedure owns the transaction boundary and decides COMMIT/ROLLBACK.

## 12. Managing Transactions with JDBC

### 12.1. Default Autocommit Can Break a Unit of Work

A JDBC Connection typically starts with auto-commit enabled by default. When auto-commit is true, each SQL statement is committed individually upon completion. If a transfer executes three DML statements without disabling auto-commit, the steps may be committed independently:

~~~java
// Unsuitable for a business unit with multiple DML statements:
connection.setAutoCommit(true);
updateSourceAccount();
updateDestinationAccount();
insertTransferHistory();
~~~

If the third statement fails, the first two may already have committed. This violates the atomicity of the transfer operation.

### 12.2. Disabling Autocommit and Committing/Rolling Back Explicitly

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debitSource(connection, fromAccountId, amount);
        creditDestination(connection, toAccountId, amount);
        insertTransferHistory(
            connection, transferId, fromAccountId, toAccountId, amount
        );

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Meaning:

- Acquire one connection for the unit of work.
- Disable auto-commit so DML statements participate in the same transaction.
- Execute all business steps.
- Commit when all mandatory steps succeed.
- Roll back on error.
- Close/return the connection after the transaction has ended.

In applications using a connection pool, follow how the pool manages/resets connection state. Never return a connection with an active unfinished transaction to the pool.

### 12.3. PreparedStatement and Checking Row Counts

~~~java
String sql = """
    UPDATE transfer_account_lab
    SET balance = balance - ?
    WHERE account_id = ?
      AND balance >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setLong(2, fromAccountId);
    ps.setBigDecimal(3, amount);

    int updated = ps.executeUpdate();
    if (updated != 1) {
        throw new SQLException("Source account missing or insufficient funds");
    }
}
~~~

Do not just send an UPDATE and assume it succeeded. Check the update count to verify whether the WHERE condition matched exactly one row.

### 12.4. Do Not Change Autocommit Before Ending the Transaction

In JDBC, switching `autoCommit` from `false` to `true` while a transaction is open can commit the current transaction according to the JDBC contract. Therefore, do not re-enable `autoCommit` before explicitly committing or rolling back. With a connection pool, let the pool manage resetting state per its configuration and ensure the connection has no open transaction before returning it.

### 12.5. A Transaction Should Have One Owner

One layer should be responsible for:

- Starting or configuring the transaction.
- Calling the necessary repositories/DAOs on the same connection.
- Committing when the business operation completes.
- Rolling back on error.

Child DAOs should not open separate connections or commit on their own if they need to participate in the same unit of work. If each DAO acquires its own connection, statements may run in different transactions and lose atomicity.

## 13. Transactions, Network Errors, and Retries

### 13.1. Not Every Error Is Safe to Retry with a Single SQL Statement

Possible errors:

- `ORA-00060`: deadlock detected.
- `ORA-08177`: cannot serialize access in a SERIALIZABLE transaction.
- `ORA-00054`: resource busy and acquire with NOWAIT specified, or a corresponding wait timeout.
- Constraint errors such as `ORA-00001`, `ORA-02290`.
- Connection errors occurring before, during, or after COMMIT.

Each error category has a different handling strategy. Data/constraint errors generally cannot be resolved by retrying immediately with the same input. Conflict errors can be retried if business rules permit and data is re-read from the beginning.

### 13.2. Retrying the Entire Transaction

When an error indicates the transaction must be retried, the typical workflow is:

1. Roll back the current transaction.
2. Start a new transaction.
3. Re-read the necessary data.
4. Recompute business decisions.
5. Re-execute all steps.
6. Commit if successful.

Do not merely re-run the final UPDATE statement, because earlier steps may have relied on a stale snapshot or balance.

Retries need a retry limit, backoff with jitter, and error classification. Unbounded retries can overload the system while the database is already experiencing contention.

### 13.3. Idempotency Key

A request may be resent due to a timeout or client disconnect. To avoid creating the same transaction twice, store a unique `request_id`:

~~~sql
CREATE TABLE transfer_request_lab (
    request_id VARCHAR2(64 CHAR) PRIMARY KEY,
    transfer_id NUMBER NOT NULL UNIQUE,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL
);
~~~

When processing a request:

- Create/register `request_id` within the same transaction as the monetary changes.
- If `request_id` already exists, return the outcome of the prior execution per business rules.
- If two requests arrive concurrently, the unique constraint serves as the final safeguard against creating duplicate records.

Idempotency does not mean every operation runs twice with the same effect; it is a design ensuring that a single identified request produces at most one business impact.

## 14. Database Transactions and External Side Effects

An Oracle transaction only controls changes within the scope of its transaction resource/database. It does not automatically roll back a sent email, a successful REST call, or a payment charge at an external provider.

Example:

1. The database creates an order and commits.
2. The application calls the email service.
3. The email service fails.

The database cannot roll back sending an email (once sent) merely with ROLLBACK. Likewise, if you call a payment gateway first and then the database transaction rolls back, the external payment may already have succeeded.

### 14.1. Transactional Outbox

A common pattern is writing the event to be published into an outbox table in the same transaction as the business data:

~~~sql
INSERT INTO orders (...);

INSERT INTO order_outbox (
    event_id, aggregate_id, event_type, payload, status, created_at
)
VALUES (
    :event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING', SYSTIMESTAMP
);

COMMIT;
~~~

A worker reads the outbox, dispatches the event to the external system, and marks it processed. If the worker fails after sending but before marking, it may resend; consumers still need idempotency or `event_id` deduplication to prevent duplicate processing.

The outbox ensures the order change and the event emission request are committed together in the database. It does not turn message dispatch and database commit into an atomic distributed operation; it provides a reliable workflow for eventual delivery.

### 14.2. Sagas and Compensation

For multi-service workflows, each step can be its own local transaction. If a later step fails, the system runs business compensating actions for prior steps:

- Inventory reservation → cancel reservation.
- Payment authorization → void authorization.
- Order creation → transition to cancelled status.

Compensation is not a physical rollback of the old transaction. It is a new transaction that can itself fail and require retries/reconciliation.

## 15. Autonomous Transactions in PL/SQL

Oracle supports autonomous transactions via the `AUTONOMOUS_TRANSACTION` pragma. It allows a routine to execute and commit/roll back a transaction independently of the calling transaction.

Conceptual example of independent logging:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log_lab (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO error_log_lab(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Logs committed in an autonomous transaction can persist even if the outer business transaction rolls back. This is useful for certain diagnostic logs, but you must clearly understand:

- An autonomous transaction does not share the caller's transaction context or commit state.
- It can cause a deadlock if it tries to access resources locked by the parent transaction.
- Do not use it to commit partial business changes that the caller expects to roll back together.
- Errors in the logging routine must be controlled so logging failures do not mask the original error.

An autonomous transaction is a specialized tool, not a replacement for normal transaction boundaries.

## 16. Two-Session Practice: Observing Commit, Rollback, and Locks

Using a dedicated lab schema, open two independent SQL sessions. Create the table:

~~~sql
CREATE TABLE tx_acid_lab (
    id NUMBER PRIMARY KEY,
    value NUMBER NOT NULL
);

INSERT INTO tx_acid_lab VALUES (1, 100);
COMMIT;
~~~

### Step 1 — Observe Uncommitted Changes

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 200
WHERE id = 1;
~~~

Session B:

~~~sql
SELECT value
FROM tx_acid_lab
WHERE id = 1;
~~~

Session B still sees the committed value 100, not the uncommitted 200.

### Step 2 — Commit and Re-Read

Session A:

~~~sql
COMMIT;
~~~

Session B runs the SELECT again. The new statement can see 200.

### Step 3 — Rollback

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 300
WHERE id = 1;

ROLLBACK;
~~~

Session B reads again and sees 200. The uncommitted change to 300 has been undone.

### Step 4 — Observe Writer Waiting for Writer

Session A:

~~~sql
UPDATE tx_acid_lab
SET value = 250
WHERE id = 1;
-- Not committed yet.
~~~

Session B:

~~~sql
UPDATE tx_acid_lab
SET value = value + 10
WHERE id = 1;
~~~

Session B will wait on the row lock held by A. When Session A executes COMMIT or ROLLBACK, the lock is released and B proceeds.

### Step 5 — Observe SAVEPOINT

In one session:

~~~sql
UPDATE tx_acid_lab SET value = 210 WHERE id = 1;
SAVEPOINT before_second_change;
UPDATE tx_acid_lab SET value = 220 WHERE id = 1;
ROLLBACK TO before_second_change;
SELECT value FROM tx_acid_lab WHERE id = 1;
ROLLBACK;
~~~

After rolling back to the savepoint, the value inside the transaction is 210; rolling back the entire transaction afterward restores the previously committed state.

### Step 6 — Clean Up the Lab Table (Optional)

~~~sql
-- Run only if you are sure this is your lab table.
DROP TABLE tx_acid_lab PURGE;
~~~

`DROP TABLE` is DDL and causes an implicit commit per Oracle rules. Only run it after finishing all practice transactions and confirming you no longer need the table.

## 17. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Every SQL statement is always a separate transaction | With auto-commit disabled, multiple DML statements can share one transaction |
| A failed DML statement rolls back all prior statements | Oracle rolls back the failed statement; prior statements can still be pending |
| COMMIT immediately writes every data block to datafiles | Commit protects redo per the commit protocol; DBWR may write data blocks later |
| Standard SELECT always blocks UPDATE | Oracle uses read consistency; readers normally do not block writers via row locks |
| READ COMMITTED gives a snapshot across the whole transaction | Each statement has its own snapshot |
| SERIALIZABLE locks the entire database | It provides a transaction-level snapshot and can raise ORA-08177 on conflict |
| ROLLBACK can reverse a successful COMMIT | A new compensating transaction is required |
| SAVEPOINT is equivalent to a partial COMMIT | A savepoint does not end the transaction |
| DDL can be rolled back together with DML | Oracle DDL triggers an implicit commit |
| A child procedure should commit on its own to make sure data is saved | Committing inside a procedure can break the caller's atomicity |
| Retrying one failed UPDATE is enough | You typically need to roll back and rerun the entire transaction after re-reading state |
| The database can roll back sent emails/APIs | External side effects require outbox/saga/idempotency |

## 18. Guidelines for Designing Application Transactions

When implementing a new business operation, you can follow these steps:

1. **Define the complete outcome:** which records and invariants must coexist together?
2. **Choose the transaction owner:** which service or procedure has the authority to commit/roll back?
3. **Place related DML on the same connection/session:** do not open separate connections per repository if they must share a transaction.
4. **Enforce invariants in the database:** primary keys, foreign keys, unique constraints, check constraints, and conditional DML.
5. **Choose appropriate isolation:** READ COMMITTED is usually sufficient; use SERIALIZABLE/READ ONLY only when matching snapshot semantics are needed.
6. **Minimize lock hold duration:** do not make network calls or wait for user interaction inside a transaction.
7. **Handle errors:** roll back when the unit of work fails; classify retryable errors.
8. **Prevent duplicate requests:** use an idempotency key for operations that may be resent.
9. **Handle external side effects:** use an outbox or saga when coordinating multiple systems.
10. **Observe and test:** measure lock waits, deadlocks, undo, redo, transaction duration, and actual execution plans.

### 18.1. Simple Layered Pattern

~~~text
HTTP / MESSAGE HANDLER
        |
        v
APPLICATION SERVICE
  begin/configure transaction
        |
        +---- CUSTOMER DAO
        |
        +---- ORDER DAO
        |
        +---- INVENTORY DAO
        |
        +---- OUTBOX DAO
        |
        v
  commit if all required steps succeed
  rollback if the unit of work fails
~~~

The DAOs receive the same connection or transaction context. The application service orchestrates the business flow and decides when to commit. Specific implementations may use a transaction manager/framework, but the ownership principle must remain clear.

## 19. Self-Check Questions

1. What is a business unit of work? Why might it contain multiple DML statements?
2. How does Atomicity differ from Consistency?
3. If the final INSERT in a transaction fails, does a preceding successful UPDATE roll back automatically?
4. Why must the transaction owner roll back when a mandatory step fails?
5. Which constraint can help protect non-negative balances?
6. Why is an UPDATE with the condition `balance >= amount` safer than reading the balance and writing a client-calculated value?
7. At what level does Oracle's READ COMMITTED create a snapshot?
8. Can two SELECTs in the same READ COMMITTED transaction see two different committed values?
9. How does SERIALIZABLE differ from READ COMMITTED?
10. Under what circumstances can ORA-08177 occur?
11. Does a READ ONLY transaction allow DML?
12. Why does Oracle not need to write every data block to datafiles immediately upon COMMIT?
13. How do undo and redo differ?
14. Which mechanism is ORA-01555 related to?
15. Does SAVEPOINT end a transaction?
16. Why should you not run DDL in the middle of a business transaction that requires atomicity?
17. Does a standard SELECT acquire row locks like UPDATE?
18. What scenario is SELECT FOR UPDATE used to solve?
19. At what scope should an ORA-00060 deadlock be handled?
20. Why is `autocommit = true` dangerous when a business operation needs three DML statements?
21. When retrying due to a serialization error, should you rerun one statement or the entire transaction?
22. How does an idempotency key help handle the case where a client loses the COMMIT response?
23. Why can a database transaction not roll back an already sent email?
24. What does a transactional outbox guarantee and what does it not guarantee?
25. What risk can an autonomous transaction pose if it accesses rows locked by the parent transaction?

**Suggested Answers:**

1. It is a group of operations that must be treated as a single complete business outcome.
2. Atomicity is all-or-nothing; Consistency means the final state satisfies all invariants.
3. No. The failed statement is rolled back at the statement level; preceding DML may remain pending.
4. To avoid committing a half-finished business state.
5. `CHECK (balance >= 0)`, combined with conditional UPDATE and transaction logic.
6. The condition is evaluated inside DML during the update, reducing the risk of writing based on a stale value.
7. Per statement.
8. Yes, if another transaction commits between the two statements.
9. SERIALIZABLE uses a transaction-level snapshot; READ COMMITTED uses a per-statement snapshot.
10. When a SERIALIZABLE transaction attempts to modify a row changed by another transaction after its snapshot.
11. No.
12. Redo is protected under the commit protocol; DBWR can write data blocks later.
13. Undo supports rollback/consistent read; redo supports roll forward/recovery.
14. Undo needed for the read snapshot was reused before the query finished.
15. No, rolling back to a savepoint only undoes work after that marker.
16. DDL triggers an implicit commit, which can commit prior DML.
17. No, standard SELECT uses read consistency; SELECT FOR UPDATE acquires row locks.
18. When needing to read and then update the same row while holding a lock.
19. Handle the error and typically roll back the entire transaction, then perform a controlled retry if appropriate.
20. Each statement can commit separately, breaking atomicity across steps.
21. The entire transaction after rolling back and re-reading the data.
22. A unique Request ID helps recognize a previous execution and prevent duplicate business effects.
23. Email belongs to an external system, outside Oracle's transaction resource scope.
24. The outbox records the event emission request along with business data; external delivery is eventual and consumers still need idempotency.
25. It can deadlock because the autonomous transaction waits on resources held by the parent transaction.

## Oracle Reference Documentation

- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transactions, commit, rollback, and transaction properties.
- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, locks, and concurrency handling.
- [Oracle Database SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): isolation levels, READ ONLY, and transaction characteristics.
- [Oracle Database SQL Language Reference — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): confirming transactions and commit behavior.
- [Oracle Database SQL Language Reference — ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html): undoing transactions and savepoints.
- [Oracle Database SQL Language Reference — SAVEPOINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SAVEPOINT.html): creating rollback markers in a transaction.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo-data.html): undo, read consistency, and recovery.
- [Oracle Database Concepts — Redo Log](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/redo-log.html): redo log and change recovery.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): connection management, transactions, and JDBC.
