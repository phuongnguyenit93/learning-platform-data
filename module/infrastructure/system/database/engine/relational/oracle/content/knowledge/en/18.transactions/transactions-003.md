# COMMIT, ROLLBACK, and Data Visibility Across Sessions

In Oracle Database, a working session can read and modify data while other sessions are accessing the same table. To avoid exposing incomplete data, Oracle manages changes in **transactions**. The **COMMIT** and **ROLLBACK** commands determine how a transaction ends; the **read consistency** mechanism determines which data version each session sees at read time.

Three core principles to grasp:

- A session sees its own uncommitted changes.
- Other sessions do not see uncommitted changes; during normal reads, they see the committed version appropriate to the statement or transaction snapshot.
- COMMIT makes a transaction's changes confirmed and visible to subsequent reads; ROLLBACK discards the transaction's uncommitted changes.

Oracle uses **multi-version concurrency control (MVCC)** and UNDO data to support consistent reads. Therefore, a normal SELECT typically does not have to wait for another transaction simply because that transaction is updating the same row. The SELECT can read the previously committed version, while another UPDATE on the same row may have to wait for a lock.

This lesson explains transaction boundaries, COMMIT, ROLLBACK, SAVEPOINT, data visibility between two sessions, READ COMMITTED and SERIALIZABLE isolation levels, row locks, DDL implicit commit, and managing transactions through JDBC/Spring.

## 1. What Are a Session and a Transaction?

A **Session** is a client's logical connection to Oracle Database. For example:
- A SQL Developer window can open one or more connections.
- A Java application can borrow a connection from a connection pool.
- Two independent database connections usually correspond to two different Oracle sessions.

A **Transaction** is a unit of work consisting of one or more data-modifying operations. Common DML operations:
- INSERT
- UPDATE
- DELETE
- MERGE
- Certain PL/SQL operations that execute DML

A transaction usually starts when a session executes the first SQL statement belonging to the transaction or configures the transaction via SET TRANSACTION. It ends upon a COMMIT or full-transaction ROLLBACK, or when an implicit commit event occurs per Oracle rules.

Example of an order that must update inventory and record the order:

~~~sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 100;

INSERT INTO orders(order_id, customer_id, status)
VALUES (5001, 200, 'NEW');

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (5001, 100, 2);

COMMIT;
~~~

The three changes form a single unit of work. If all operations succeed, COMMIT confirms everything. If one step detects a business error before COMMIT, ROLLBACK can discard all unconfirmed changes.

If the application COMMITs after each statement, business atomicity is broken: inventory might be decremented while the order is never recorded. Therefore, transaction boundaries must align with the business unit that must succeed or fail together.

### 1.1. One Session Can Have Multiple Sequential Transactions

After COMMIT, the current transaction ends. The session remains open and can start the next transaction:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

COMMIT;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
~~~

The first transaction is confirmed. The second transaction is discarded. ROLLBACK does not undo a previously COMMITted transaction.

### 1.2. One Transaction Can Consist of Multiple Statements

~~~sql
INSERT INTO customer(customer_id, full_name)
VALUES (10, 'An');

INSERT INTO customer_address(customer_id, address_text)
VALUES (10, 'District 1');

UPDATE customer_counter
SET total_customers = total_customers + 1;

COMMIT;
~~~

The statements belong to the same transaction as long as the session has not ended the transaction in between. COMMIT confirms all changes of that transaction.

A standard SELECT statement does not automatically COMMIT pending DML changes. SELECT reads data according to read consistency and the current transaction isolation.

## 2. COMMIT: Confirming a Transaction

Basic syntax:

~~~sql
COMMIT;
~~~

COMMIT:
1. Ends the current transaction.
2. Confirms the DML changes belonging to the transaction.
3. Records the commit in redo per the database's commit-write policy.
4. Releases transaction locks held by the session.
5. Makes COMMITted changes visible to subsequent read statements according to their isolation level.

After a successful COMMIT, normal ROLLBACK cannot undo those changes. To fix COMMITted data, you must execute a new transaction to perform a compensating update or restore from an appropriate backup/flashback mechanism.

### 2.1. COMMIT Does Not Close the Session

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

COMMIT;

SELECT product_id, price
FROM products
WHERE category_id = 10;
~~~

After COMMIT, the session can still continue to SELECT, INSERT, or UPDATE. COMMIT ends the transaction; it does not close the SQL Developer/JDBC connection.

### 2.2. COMMIT Confirms All Changes in the Transaction

Suppose a session has run:

~~~sql
INSERT INTO orders(order_id, status)
VALUES (9001, 'NEW');

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 50;

COMMIT;
~~~

COMMIT does not confirm only the last statement. It confirms all uncommitted DML changes of the transaction. Oracle has no command to COMMIT only an UPDATE while keeping a preceding INSERT unconfirmed; to split boundaries, you must end the transaction and start a new one.

### 2.3. COMMIT and Durability

Oracle writes redo information so confirmed changes can be recovered after a crash under the recovery mechanism. By default, COMMIT usually waits for the redo commit record to be durably written per the system's WAIT policy. Some `COMMIT WRITE NOWAIT` configurations can alter when the client receives acknowledgment relative to redo flushing.

In normal applications, treat a successful COMMIT as the transaction confirmation boundary. Changing the `COMMIT WRITE` policy is an operational decision affecting durability that requires DBA evaluation, not an arbitrary optimization trick in application code.

### 2.4. COMMIT Releases Locks

DML generally locks the rows that the transaction modifies. These locks are held until the transaction ends. COMMIT releases them so other transactions can proceed with writes.

If Session A UPDATEs a row without COMMITting yet, Session B attempting to UPDATE the same row may have to wait. When A COMMITs, B can proceed under current locking and isolation rules.

COMMIT also releases locks acquired by `SELECT FOR UPDATE` in the transaction.

## 3. ROLLBACK: Discarding Uncommitted Changes

Syntax:

~~~sql
ROLLBACK;
~~~

Full-transaction ROLLBACK:
- Discards uncommitted DML changes.
- Restores logical data state to the start of the most recent transaction.
- Ends the current transaction.
- Releases locks held by the transaction.

Example:

~~~sql
UPDATE products
SET price = 999999
WHERE product_id = 10;

-- Check the value again within the same session.
SELECT product_id, price
FROM products
WHERE product_id = 10;

ROLLBACK;

-- The change just made has been discarded.
SELECT product_id, price
FROM products
WHERE product_id = 10;
~~~

Before ROLLBACK, your own session sees price 999999. After ROLLBACK, that change is no longer in the data.

### 3.1. ROLLBACK Does Not Erase COMMITted Changes

~~~sql
UPDATE products
SET price = 100
WHERE product_id = 10;

COMMIT;

UPDATE products
SET price = 200
WHERE product_id = 10;

ROLLBACK;
~~~

The final price is 100. ROLLBACK only discards the second UPDATE, not the COMMITted UPDATE.

If you want to change the price back from 100 to the old price after committing, you need to know the old price and run a new UPDATE, or use an appropriate data recovery solution.

### 3.2. ROLLBACK When a Statement Encounters an Error

A SQL error does not necessarily roll back the entire transaction automatically. Depending on the error type and context:
- The failed statement is usually rolled back at the scope of that statement.
- Previous successful changes in the same transaction may still remain.
- The application must decide whether to continue, roll back to a savepoint, or roll back the entire transaction.

Example:

~~~sql
INSERT INTO demo_table(id, value_text)
VALUES (1, 'first');

-- Suppose ID 1 already exists and this INSERT fails on a unique constraint.
INSERT INTO demo_table(id, value_text)
VALUES (1, 'duplicate');

-- The first INSERT change may still be pending COMMIT.
ROLLBACK;
~~~

Never assume a constraint error automatically rolled back all previous operations. If the transaction is no longer valid per application logic, proactively ROLLBACK.

### 3.3. ROLLBACK Does Not Reverse Every Kind of Effect

ROLLBACK only undoes transactional changes managed by Oracle in the current transaction. Certain effects are not undone like regular DML:

- DDL causing an implicit commit.
- Sequence `NEXTVAL` values already allocated do not revert on rollback.
- An autonomous transaction that COMMITted independently.
- Emails, HTTP requests, file writes, or external system side effects outside the database.
- Effects already COMMITted in an earlier transaction.

When a business flow coordinates the database and external systems, design appropriate compensation/retry/outbox mechanisms instead of assuming a database ROLLBACK will recall external effects.

## 4. SAVEPOINT and ROLLBACK TO

SAVEPOINT marks a position inside a transaction so you can roll back partially.

Syntax:

~~~sql
SAVEPOINT savepoint_name;
ROLLBACK TO savepoint_name;
~~~

Example:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

SAVEPOINT before_discount;

UPDATE orders
SET discount_amount = 50000
WHERE order_id = 1001;

-- If the discount step is invalid:
ROLLBACK TO before_discount;

-- The PROCESSING status change still remains in the transaction.
COMMIT;
~~~

ROLLBACK TO:
- Discards changes made after the chosen savepoint.
- Does not end the entire transaction.
- Retains changes made before the savepoint.
- Allows the session to continue executing DML and COMMIT/ROLLBACK afterward.

### 4.1. SAVEPOINT Is Not an Independent Child Transaction

~~~sql
INSERT INTO audit_demo(id, note) VALUES (1, 'before');
SAVEPOINT s1;

INSERT INTO audit_demo(id, note) VALUES (2, 'after');
ROLLBACK TO s1;

COMMIT;
~~~

After COMMIT, the row with ID=1 exists, while the row with ID=2 is discarded. SAVEPOINT only marks a position within the same transaction; it does not create a separate transaction that can COMMIT independently.

### 4.2. ROLLBACK TO Does Not End the Transaction

~~~sql
SAVEPOINT s1;

UPDATE accounts
SET balance = balance - 10
WHERE account_id = 1;

ROLLBACK TO s1;

UPDATE accounts
SET balance = balance - 20
WHERE account_id = 1;

COMMIT;
~~~

The first UPDATE is discarded; the UPDATE after the savepoint still executes and COMMITs. After ROLLBACK TO, the transaction remains open.

### 4.3. Savepoints with the Same Name

If you redefine SAVEPOINT with the same name, the old savepoint position is replaced with the new position. A ROLLBACK TO savepoint also removes savepoints created after the target savepoint. Do not treat a savepoint name as a global transaction ID; its scope is strictly within the current transaction/session.

### 4.4. SAVEPOINT in PL/SQL Error Handling

Savepoints can be used to roll back the work of a single step:

~~~sql
BEGIN
    SAVEPOINT before_optional_step;

    UPDATE orders
    SET status = 'READY'
    WHERE order_id = 1001;

    -- Subsequent optional steps may raise an error.
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_step;
        RAISE;
END;
~~~

This example illustrates the technique. In real PL/SQL, you must decide whether exceptions are handled or re-raised, and who is responsible for COMMITting/ROLLBACKing the transaction at the calling layer. Do not swallow an error and continue if the transaction is in a state that violates business conditions.

## 5. Why Do Other Sessions Not See Uncommitted Changes?

Oracle guarantees **no dirty reads** in its standard supported isolation levels. One session never reads uncommitted data from another transaction via a standard SELECT.

Suppose a table has a row:

~~~text
ACCOUNT_ID = 1
BALANCE    = 1000
~~~

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;
-- Not committed yet.
~~~

Session A sees BALANCE = 900 when SELECTing that row again. Session B runs:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Session B still sees BALANCE = 1000, the previously COMMITted version.

This does not mean A's UPDATE has not happened. A has modified the data version within its own transaction and holds a write lock; B reads a consistent COMMITted version.

### 5.1. A Session Sees Its Own Changes

After an uncommitted UPDATE, Session A:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

returns 900. A session normally sees changes created by its own transaction.

### 5.2. Other Sessions See the Previously COMMITted Version

While A has not COMMITted yet, B:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

returns 1000. Oracle can use UNDO to reconstruct the version prior to A's change. This is the foundation of consistent read.

### 5.3. After COMMIT, New Read Statements Can See the Changes

Session A:

~~~sql
COMMIT;
~~~

Then Session B runs a new SELECT under READ COMMITTED:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B sees 900 because transaction A COMMITted before B's new SELECT began.

**The critical milestone is the snapshot point of the read statement**, not simply when the session opened its connection or when a row was fetched.

### 5.4. If A ROLLBACKs Instead of COMMITting

Session A:

~~~sql
UPDATE accounts
SET balance = 800
WHERE account_id = 1;

ROLLBACK;
~~~

The change to 800 is discarded. Session B continues seeing the previously COMMITted value, e.g., 900 if A COMMITted 900 in a prior transaction.

At no point does B see the value 800 via a standard SELECT while A has not COMMITted.

## 6. Two-Session Practice: Observing COMMIT and ROLLBACK

You can open two independent connections in SQL Developer or two SQLcl/SQL*Plus windows. Define naming conventions:
- **Session A**: performs changes.
- **Session B**: observes data.

Run the setup once in one session:

~~~sql
CREATE TABLE tx_visibility_demo (
    id     NUMBER(6) PRIMARY KEY,
    amount NUMBER(12,2)
);

INSERT INTO tx_visibility_demo(id, amount)
VALUES (1, 100);

COMMIT;
~~~

### 6.1. Step 1: A UPDATEs Without COMMITting

Session A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 120
WHERE id = 1;

SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

The result in A is 120. The transaction remains open.

### 6.2. Step 2: B SELECTs While A Has Not COMMITted

Session B:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

The result in B is still 100. B cannot read 120 because it is A's uncommitted change.

### 6.3. Step 3: A COMMITs

Session A:

~~~sql
COMMIT;
~~~

The transaction ends and the change to 120 is confirmed.

### 6.4. Step 4: B Runs a New SELECT

Session B:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

In the default READ COMMITTED mode, a new SELECT starting after A's COMMIT will see 120.

### 6.5. Step 5: A UPDATEs Then ROLLBACKs

Session A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 150
WHERE id = 1;

ROLLBACK;
~~~

Session A discards the change to 150. Session B runs a new SELECT:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

The result is 120, the previously COMMITted value.

### 6.6. Observation Results Table

| Point in Time | Session A | Session B (New SELECT) |
| --- | ---: | ---: |
| Initial | 100 | 100 |
| A UPDATEs 120, not COMMITted | 120 | 100 |
| A COMMITs | 120 | 120 |
| A UPDATEs 150, not COMMITted | 150 | 120 |
| A ROLLBACKs | 120 | 120 |

This table describes READ COMMITTED, and each row in column B represents a new SELECT started at the noted time. If B was already running a SELECT before A COMMITted, that SELECT's result does not change mid-flight; see the read consistency section next.

## 7. Read Consistency: One SELECT Sees One Snapshot

Oracle provides **statement-level read consistency** at the READ COMMITTED level. Each SQL statement reads data from a consistent snapshot as of the time the statement begins (an appropriate SCN), rather than reading the newest version independently row by row.

This matters when:
- A query joins multiple tables.
- A query reads many data blocks.
- A SELECT runs for a long time while another session COMMITs.
- A query uses subqueries or aggregates across many rows.

Oracle ensures that an entire SELECT sees data consistent with the same read point, rather than arbitrarily mixing some pre-COMMIT rows and some post-COMMIT rows.

### 7.1. A Running SELECT Does Not Switch Snapshots Mid-Flight

Suppose:
1. B starts a long SELECT when the COMMITted value is 100.
2. While B is running, A UPDATEs to 120 and COMMITs.
3. B continues reading the remaining blocks.

B's SELECT continues using the snapshot determined when the statement started; it does not switch to a new snapshot midway. Depending on execution duration and available UNDO data, Oracle reconstructs the necessary versions to maintain consistent read.

After B's SELECT finishes, a new SELECT in READ COMMITTED will take a new snapshot and see 120.

### 7.2. Multi-Table JOINs Remain Consistent Within One Statement

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 5001;
~~~

If another transaction is updating ORDER and CUSTOMER, a standard SELECT still reads a consistent set of versions at the statement's snapshot. It does not actively wait for each row to be COMMITted just to get the newest value.

### 7.3. Subqueries and Aggregates Also Use the Statement Snapshot

~~~sql
SELECT e.employee_id,
       e.salary,
       (SELECT AVG(salary) FROM employees) AS company_avg
FROM employees e;
~~~

Both the outer rows and the aggregate subquery belong to the same SQL statement. Oracle guarantees read consistency for the statement, so the query will not fetch outer rows at one point in time and AVG at another point during execution.

### 7.4. UNDO Supports Reading Older Versions

Oracle stores UNDO information to:
- Roll back uncommitted changes.
- Reconstruct older data versions for consistent reads.
- Support certain Flashback operations.

When a transaction overwrites data, a reading session may need UNDO to see the version at its SCN. If a query runs too long and the required UNDO information is no longer available due to being overwritten, the query may encounter `ORA-01555: snapshot too old`.

UNDO is not a long-term backup and does not guarantee every old version is kept indefinitely. Retention, DML rate, and query duration affect the ability to reconstruct older versions.

## 8. READ COMMITTED: Oracle's Default

Oracle Database uses the **READ COMMITTED** isolation level by default. Characteristics:
- Never reads uncommitted changes of other transactions.
- Each statement has its own snapshot.
- Two consecutive SELECTs in the same transaction can see two different snapshots.
- Another transaction COMMITting between two SELECTs can cause the second SELECT to see new data.
- DML on the same row may have to wait for a lock.

Session B example:

~~~sql
-- First SELECT.
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;

-- Meanwhile Session A UPDATEs and COMMITs.

-- Second SELECT in the same Session B.
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

In READ COMMITTED, the second SELECT can see the new value that A just COMMITted. Transaction B does not retain a single snapshot for the entire lifetime of the transaction.

### 8.1. Non-Repeatable Read

A transaction reads the same row twice and gets different values because another transaction COMMITted in between:

~~~text
B: SELECT amount -> 100
A: UPDATE amount = 120; COMMIT
B: SELECT amount -> 120
~~~

This is a non-repeatable read at the transaction level. Each individual SELECT remains consistent.

### 8.2. Phantom Rows

A first SELECT returns rows matching a condition; another transaction INSERTs a new row matching the condition and COMMITs; a second SELECT may return that additional row:

~~~text
B: SELECT * FROM orders WHERE status = 'NEW' -> 5 rows
A: INSERT a NEW order; COMMIT
B: SELECT * FROM orders WHERE status = 'NEW' -> 6 rows
~~~

Each statement still reads its own consistent snapshot. READ COMMITTED does not promise the same row set across all statements in a transaction.

### 8.3. READ COMMITTED Has No Dirty Reads

Even though it can see COMMITted changes between two SELECTs, Session B does not see temporary values that Session A has not COMMITted yet. This differs from the READ UNCOMMITTED level in some other DBMSs.

Oracle does not provide READ UNCOMMITTED in a way that permits normal dirty reads. Do not use the term "dirty read" when a new SELECT sees a value after COMMIT; that is reading confirmed data.

## 9. SERIALIZABLE: Transaction-Level Snapshot

You can request a transaction to use the SERIALIZABLE isolation level:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

The SET TRANSACTION command must execute at the beginning of the transaction, before other statements in the transaction. At this level, reads in the transaction see a consistent snapshot at the transaction level, based on when the transaction started.

Example:

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Suppose the result is 120.

Session B:

~~~sql
UPDATE tx_visibility_demo
SET amount = 130
WHERE id = 1;

COMMIT;
~~~

Session A runs SELECT again:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

A still sees 120 within the current SERIALIZABLE transaction, even though B COMMITted 130 after A's transaction started.

### 9.1. SERIALIZABLE Does Not Mean Other Transactions Are Completely Locked Out

SERIALIZABLE provides a transaction-level snapshot and write-conflict checking per Oracle rules. It does not mean all other sessions are halted or that every SELECT locks the table.

Other transactions can still read and write. If the current transaction attempts to modify a row modified by another transaction after its snapshot point, Oracle can raise:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

When this error occurs, the application usually needs to ROLLBACK the current transaction and retry the entire unit of work under a safe retry policy.

### 9.2. Write-Conflict Example

1. A starts SERIALIZABLE and reads row ID=1 at value 120.
2. B updates row ID=1 to 130 and COMMITs.
3. A tries to UPDATE the same row ID=1 from the stale snapshot.

~~~sql
-- Session A has started SERIALIZABLE.
UPDATE tx_visibility_demo
SET amount = 125
WHERE id = 1;
~~~

Because the row was changed by another transaction after A started, Oracle can return ORA-08177 instead of allowing A to overwrite in a non-serializable way.

Do not continue COMMITting the remaining work as if the transaction had no error. Handle the error at the transaction boundary: ROLLBACK and retry if business rules permit.

### 9.3. SERIALIZABLE Must Be Set Before Transaction Statements

Correct example:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM orders;

UPDATE orders
SET status = 'CHECKED'
WHERE order_id = 1001;

COMMIT;
~~~

Do not place SET TRANSACTION after already executing a SELECT/UPDATE in the transaction. Oracle requires setting the isolation level at the start of the transaction.

### 9.4. When to Use SERIALIZABLE?

Consider it when a business operation requires reads within a transaction to see the same snapshot and can tolerate write-conflict/retry handling. However, SERIALIZABLE does not automatically replace all locking strategies or business checks.

Evaluate:
- Is the transaction long?
- Are many sessions updating the same set of rows?
- Is retrying the entire transaction safe?
- Are there external side effects outside the database before COMMIT?
- Would explicit locking or a different data design be simpler?

Do not turn on SERIALIZABLE system-wide just to avoid non-repeatable reads without measuring load and analyzing contention.

## 10. READ ONLY Transactions

Oracle lets you start a read-only transaction:

~~~sql
SET TRANSACTION READ ONLY;
~~~

SELECT statements in a READ ONLY transaction see a consistent snapshot at the transaction level. The transaction cannot execute INSERT, UPDATE, or DELETE.

Example:

~~~sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount)
FROM orders;

SELECT COUNT(*)
FROM order_items;

COMMIT;
~~~

Both SELECT statements see the same transaction-level snapshot. Another session can COMMIT changes between the two statements, yet the current READ ONLY transaction still reads the snapshot as of when it began.

READ ONLY suits reporting workloads requiring multiple consistent queries in the same transaction. It is not a way to lock tables against others; other sessions can still write under normal locking rules.

When ending a read-only transaction with no changes, COMMIT ends the transaction. ROLLBACK can also end a read transaction, though COMMIT usually expresses the goal of successful completion more clearly.

## 11. Comparing Read Modes and Data Visibility

| Feature | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Oracle default | Yes | No | No |
| Dirty read | No | No | No |
| Snapshot | Per statement | Transaction-level | Transaction-level |
| New SELECT after another session's COMMIT | Can see new changes | Still sees old transaction snapshot | Still sees old transaction snapshot |
| DML in transaction | Yes | Yes, but may hit ORA-08177 | No |
| Can hit serialization write conflict | Follows locking/wait and READ COMMITTED rules | Possible ORA-08177 | No DML by this transaction |
| Typical purpose | General application transactions | Needs stable snapshot and conflict control | Reports with multiple consistent SELECTs |

Note: This table describes core behavior. Locking details and DML outcomes also depend on the statement, contested rows, constraints, and execution plan.

## 12. Standard SELECT and SELECT FOR UPDATE

A standard SELECT does not lock rows in a way that prevents other transactions from UPDATEing them. It reads a consistent snapshot.

If an application needs to read rows and lock them for safe updating, it can use `SELECT FOR UPDATE`:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

The statement acquires appropriate row locks for the current transaction. Other transactions wanting to UPDATE the same row may have to wait until the lock is released.

### 12.1. NOWAIT

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

If the row is currently locked by another session, the statement does not wait and immediately raises a resource busy error, typically ORA-00054.

### 12.2. WAIT n

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE WAIT 5;
~~~

The statement waits up to the specified number of seconds before raising an error if it cannot acquire the lock.

### 12.3. SKIP LOCKED

~~~sql
SELECT job_id, status
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED skips rows currently locked by another session. This pattern is useful when multiple workers dequeue jobs from a queue, but status updates and commits must be properly designed to avoid duplicate processing or missed work.

### 12.4. SELECT FOR UPDATE Still Requires COMMIT/ROLLBACK

Locks acquired by SELECT FOR UPDATE are held until the transaction ends. If the application reads rows, processes for a long time, and forgets to COMMIT/ROLLBACK, other sessions can be blocked for a long time.

Lock only the rows actually needed and keep transactions short. Avoid making HTTP calls, sending emails, or waiting for user input while holding database locks whenever possible.

## 13. Writers and Readers: Who Waits for Whom?

Oracle MVCC enables standard SELECTs and DML to coexist without forcing every reader to wait for writers.

| Session A | Session B | Typical Behavior |
| --- | --- | --- |
| UPDATEs row, not COMMITted | SELECTs row | B reads the previously COMMITted version |
| UPDATEs row, not COMMITted | UPDATEs same row | B waits on A's lock |
| UPDATEs row, not COMMITted | SELECT FOR UPDATE same row | B waits or NOWAIT/SKIP LOCKED per syntax |
| COMMITs | New SELECT in READ COMMITTED | B sees the COMMITted change |
| ROLLBACKs | New SELECT | B sees data COMMITted prior to A's transaction |
| Long SELECT running | A COMMITs while B is running | B keeps the snapshot from when its statement began |

### 13.1. A SELECT Is Not Necessarily Blocked by an UPDATE

Suppose A updates row 1 without committing yet. B running a SELECT on row 1 can normally read the older version from UNDO. This is a key benefit of read consistency.

### 13.2. Two UPDATEs on the Same Row Can Wait on Each Other

A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 140
WHERE id = 1;
-- Not committed yet.
~~~

B:

~~~sql
UPDATE tx_visibility_demo
SET amount = 160
WHERE id = 1;
~~~

B can be blocked until A COMMITs or ROLLBACKs. If A COMMITs, B proceeds based on the row state and statement predicates. If A ROLLBACKs, B proceeds on the remaining data. Applications need appropriate timeouts and lock-wait handling.

### 13.3. Avoid Holding Locks During External Processing

Bad pattern:

~~~text
BEGIN TRANSACTION
  UPDATE inventory
  Call payment service over HTTP (takes 20 seconds)
  Wait for user confirmation
  INSERT order
COMMIT
~~~

During the wait, database locks can be held for a long time. A better design usually splits the workflow into short transactions using intermediate states, an outbox, or compensating mechanisms to coordinate external systems.

## 14. DDL and Implicit COMMIT

A notable feature of Oracle: DDL statements such as CREATE, ALTER, DROP, and TRUNCATE follow the **implicit commit** rule.

Example:

~~~sql
INSERT INTO demo_table(id, note)
VALUES (1, 'pending');

CREATE TABLE another_demo(id NUMBER);

ROLLBACK;
~~~

The INSERT before DDL may already have been implicitly COMMITted before `CREATE TABLE` ran. The subsequent ROLLBACK cannot undo an INSERT that was implicitly committed.

Oracle performs an implicit commit before DDL; a successful DDL statement is also committed per DDL rules. Therefore, do not mix DDL into the middle of a DML transaction if you expect to roll back everything.

### 14.1. TRUNCATE Cannot Be Rolled Back Like DELETE

~~~sql
TRUNCATE TABLE staging_data;
~~~

TRUNCATE is DDL, carries an implicit commit, and cannot be undone with ROLLBACK like DELETE. If you need rollbackable row deletion, use DELETE in an appropriate transaction:

~~~sql
DELETE FROM staging_data;
-- Can inspect before COMMIT or ROLLBACK.
~~~

DELETE may generate more UNDO/REDO and have different locking behavior; the choice must be based on business and operational requirements.

### 14.2. CREATE TABLE AS SELECT Is Also DDL

~~~sql
CREATE TABLE archive_orders AS
SELECT *
FROM orders
WHERE created_at < DATE '2024-01-01';
~~~

This is DDL. Do not treat it as an ordinary INSERT that can be rolled back after the statement succeeds.

### 14.3. Failed DDL and Preceding Transactions

Because Oracle executes an implicit commit before DDL, an open DML transaction may already be COMMITted even if the subsequent DDL fails. Consequently, never test CREATE/ALTER/DROP in the middle of an incomplete transaction if you still need the ability to ROLLBACK earlier DML.

## 15. Sequences and Values That Do Not Revert on ROLLBACK

Sequences issue values independently of transactions:

~~~sql
INSERT INTO orders(order_id, status)
VALUES (orders_seq.NEXTVAL, 'NEW');

ROLLBACK;
~~~

The inserted row is discarded, but the issued sequence value is not returned. The next `NEXTVAL` call will take the next value according to the sequence configuration.

Therefore:
- Gaps in IDs are normal.
- Do not use sequences to generate strictly contiguous invoice numbers if business rules prohibit gaps.
- Caching, RAC instances, restarts, and rollbacks can all contribute to gaps.
- Do not assume sequential IDs reflect the count of COMMITted rows.

Sequences are designed to supply unique values efficiently, not to serve as rollbackable transaction counters.

## 16. Autonomous Transactions and Effects Outside the Parent Transaction

A PL/SQL routine can declare an autonomous transaction. This transaction is independent of the calling transaction and can COMMIT/ROLLBACK on its own.

Conceptual example:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit_independent (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

If the parent transaction later ROLLBACKs, the audit row COMMITted in the autonomous transaction still persists.

Autonomous transactions are useful for certain independent logging use cases, but must be designed carefully:
- The child transaction cannot see uncommitted changes of the parent transaction.
- Avoid locking resources held by the parent transaction, as doing so can cause deadlocks.
- Independent audits might record an operation that was ultimately rolled back in the parent transaction; log messages must reflect status accurately.
- Do not use autonomous transactions to bypass business transaction boundaries.

Similarly, a database ROLLBACK does not recall sent emails, completed HTTP requests, or written files. Side effects outside the database require idempotency, an outbox, or compensating actions.

## 17. Transactions in JDBC

In JDBC, a Connection has an auto-commit mode. Per JDBC, auto-commit defaults to true; with Oracle JDBC, applications can change this mode to group multiple statements into one transaction.

### 17.1. Auto-Commit Enabled

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Auto-commit is typically true by default.
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE inventory SET quantity = quantity - ? WHERE product_id = ?")) {
        ps.setInt(1, 1);
        ps.setLong(2, 100L);
        ps.executeUpdate();
    }
}
~~~

When auto-commit is enabled, a statement executes as its own transaction and JDBC commits when the statement finishes per driver rules. Two separate DML statements do not automatically become a single shared business transaction.

### 17.2. Disabling Auto-Commit to Group Multiple Statements

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement updateInventory =
                 connection.prepareStatement(
                     "UPDATE inventory " +
                     "SET quantity = quantity - ? " +
                     "WHERE product_id = ?")) {
            updateInventory.setInt(1, 2);
            updateInventory.setLong(2, 100L);
            updateInventory.executeUpdate();
        }

        try (PreparedStatement insertOrder =
                 connection.prepareStatement(
                     "INSERT INTO orders(order_id, customer_id, status) " +
                     "VALUES (?, ?, ?)")) {
            insertOrder.setLong(1, 5001L);
            insertOrder.setLong(2, 200L);
            insertOrder.setString(3, "NEW");
            insertOrder.executeUpdate();
        }

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Both DML statements share the same Connection, so they belong to the same transaction when auto-commit is false. If both succeed, commit. On error, roll back the unconfirmed changes.

In production code, also handle exceptions if rollback itself fails; you can attach the rollback exception as a suppressed exception or log it properly. Never swallow errors and return success to the caller.

### 17.3. Do Not Rely on close() to Decide Transaction Outcome

When a Connection has an open transaction, do not rely on closing the connection to auto-commit. Explicitly call commit or rollback before returning the connection to the pool. Behavior when closing a Connection with an active transaction depends on the API/driver/pool; explicit boundaries avoid retaining unintended state.

With a connection pool, the Connection received by the application is usually a proxy over a physical connection/session. After closing the proxy, the physical connection can be returned to the pool for reuse. An unfinished transaction can leak state and locks if the pool/driver does not clean it up properly.

### 17.4. Do Not Arbitrarily Re-Enable Auto-Commit Mid-Transaction

Changing auto-commit while a transaction is open can end the current transaction per JDBC behavior. Follow a clear pattern:
1. Borrow connection.
2. Set auto-commit to false.
3. Execute the entire unit of work.
4. COMMIT or ROLLBACK.
5. Return connection.

Do not toggle auto-commit on and off after each statement if you want multiple DML statements in the same transaction.

## 18. Spring Transaction Boundaries

With Spring, transactions can be managed using `@Transactional`:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void createOrder(OrderRequest request) {
        inventoryRepository.decrease(
            request.productId(),
            request.quantity()
        );

        orderRepository.insert(request);
    }
}
~~~

When the transactional method completes normally, the transaction manager commits. When an exception matching the default rollback policy occurs, the transaction manager rolls back.

### 18.1. Spring's Default Rollback Rules

Under Spring's common defaults:
- `RuntimeException` and `Error` trigger rollback.
- Checked exceptions do not automatically trigger rollback unless configured.
- `rollbackFor` can be declared to specify exception types that should trigger rollback.

Example:

~~~java
@Transactional(rollbackFor = Exception.class)
public void createOrder(OrderRequest request) throws Exception {
    // Perform multiple repository operations.
}
~~~

Verify the specific Spring version and transaction manager in use. Annotations only take effect when calls pass through the appropriate proxy/interceptor; self-invocation within the same object may bypass transactional proxying.

### 18.2. Do Not Manually COMMIT Inside a Spring-Managed Method

If Spring's transaction manager owns the transaction, let the transaction manager decide commit/rollback. Do not grab the underlying connection and arbitrarily COMMIT mid-method, as doing so can break framework-managed transaction boundaries.

### 18.3. Database Transactions Do Not Automatically Cover External Systems

A `@Transactional` method calls the database and then sends an email:
- The database can roll back.
- A sent email does not vanish on its own.

When reliable coordination is required, consider a transactional outbox, message relay, idempotency, and compensating actions. Do not treat `@Transactional` as an automatic distributed transaction across every HTTP service.

## 19. Inspecting Transactions and Sessions

Several useful queries in environments with appropriate privileges:

### 19.1. Identify the Current Session's SID

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

Open two connections and run this query to confirm they are two distinct sessions.

### 19.2. View the Session's Transaction ID

~~~sql
SELECT DBMS_TRANSACTION.LOCAL_TRANSACTION_ID
FROM dual;
~~~

The result may be NULL if the session does not currently have an active local transaction. Privileges and invocation behavior can depend on the environment.

### 19.3. View Active Sessions and Transactions

A DBA or appropriately privileged user can query dynamic performance views such as `V$SESSION`, `V$TRANSACTION`, and `V$LOCK`. Example:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.addr = s.taddr;
~~~

These views typically require `SELECT_CATALOG_ROLE` or specific privileges granted by a DBA. Do not grant broad privileges to an application account solely for routine reporting.

### 19.4. Inspect Waiting Locks

DBAs can inspect `V$SESSION.BLOCKING_SESSION`, `V$LOCK`, and related views to locate blocking/waiting sessions. When diagnosing:
- Identify the blocker's SID/serial#.
- Identify the SQL holding the lock.
- Check how long the transaction has been open.
- Determine whether an application forgot to COMMIT/ROLLBACK.
- Terminate a session only after understanding the business impact.

Do not kill a session merely because it is holding a lock; rolling back a large transaction can take time and impact users.

## 20. Comprehensive Hands-On Dataset

The following example creates an isolated table to observe commit, rollback, and locking. Run it in a sandbox schema with `CREATE TABLE` and DML privileges.

### 20.1. Create Table and Initial Data

~~~sql
CREATE TABLE account_tx_demo (
    account_id NUMBER(6)
        CONSTRAINT pk_account_tx_demo PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_tx_demo
VALUES (1, 'An', 1000);

INSERT INTO account_tx_demo
VALUES (2, 'Binh', 500);

COMMIT;
~~~

### 20.2. Session A Makes an Uncommitted Change

~~~sql
UPDATE account_tx_demo
SET balance = balance - 100
WHERE account_id = 1;

SELECT account_id, balance
FROM account_tx_demo
WHERE account_id = 1;
~~~

Session A sees 900.

### 20.3. Session B Reads the COMMITted Version

~~~sql
SELECT account_id, balance
FROM account_tx_demo
WHERE account_id = 1;
~~~

Session B sees 1000.

### 20.4. Session A Confirms

~~~sql
COMMIT;
~~~

Session B running a new SELECT will see 900 under READ COMMITTED.

### 20.5. Transferring Money in One Transaction

~~~sql
UPDATE account_tx_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_tx_demo
SET balance = balance + 100
WHERE account_id = 2;

-- Verify both rows before confirming.
SELECT account_id, balance
FROM account_tx_demo
ORDER BY account_id;

COMMIT;
~~~

Both UPDATEs belong to the same transaction. Other sessions only see the entire COMMITted state per their snapshot, never half of an unconfirmed transaction.

In real code, check the affected row count of each UPDATE. If an account does not exist or balance is insufficient, decide to ROLLBACK instead of COMMITting an invalid transfer.

### 20.6. Using SAVEPOINT for an Optional Step

~~~sql
UPDATE account_tx_demo
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account_tx_demo
SET balance = balance + 50
WHERE account_id = 2;

-- Suppose the credit step must be cancelled:
ROLLBACK TO after_debit;

-- Choose to cancel the whole transaction:
ROLLBACK;
~~~

The first statement is also discarded by the final ROLLBACK. If the final ROLLBACK were replaced by COMMIT, the debit of 50 from account 1 would be confirmed while the credit of 50 after the savepoint was discarded. That could create a business imbalance, so savepoints should only be used when business rules allow pre-savepoint work to persist independently.

### 20.7. Clean Up the Sandbox Table

~~~sql
DROP TABLE account_tx_demo PURGE;
~~~

Only drop the sandbox table created by this lesson when you are certain the data is no longer needed. DROP TABLE is DDL and has implicit commit rules; PURGE bypasses the recycle bin per normal behavior.

## 21. Common Misconceptions

**Once an UPDATE finishes, other sessions see it immediately.** False. Changes can only be seen by other sessions after COMMIT and according to the read's snapshot/isolation.

**Session A does not see its own uncommitted changes either.** False. Session A sees changes made by its own current transaction.

**Standard SELECT always waits on a transaction running UPDATE.** False. Oracle normally uses UNDO to return the COMMITted version for consistent reads; SELECT FOR UPDATE is the explicit locking case.

**COMMIT closes the connection.** False. COMMIT ends the transaction; the session remains active.

**ROLLBACK discards previously COMMITted transactions too.** False. ROLLBACK only discards the current unconfirmed transaction.

**One SQL error always rolls back the entire transaction.** False. Rollback scope depends on the error type and context; prior operations may still be pending COMMIT.

**SAVEPOINT creates a child transaction.** False. It only marks a position within the same transaction.

**ROLLBACK TO savepoint ends the transaction.** False. The transaction continues running.

**READ COMMITTED keeps the same snapshot for the whole transaction.** False. Each statement has its own snapshot.

**SERIALIZABLE locks out all other sessions.** False. It provides a transaction-level snapshot and can detect write conflicts via ORA-08177.

**READ ONLY is just a single SELECT statement.** False. `SET TRANSACTION READ ONLY` establishes a read-only transaction mode and a transaction-level snapshot for statements within the transaction.

**DDL can be rolled back together with preceding DML.** False. DDL triggers an implicit commit; separate DDL from DML transactions that must remain rollbackable.

**Sequence NEXTVAL reverts on ROLLBACK.** False. Sequences are non-transactional; gaps are normal.

**Database rollback recalls sent emails.** False. External side effects require their own compensating mechanisms.

**JDBC close() always commits the transaction.** False. Applications must explicitly call commit/rollback.

**@Transactional automatically rolls back every exception type.** False under Spring's common defaults; checked exceptions require `rollbackFor` configuration to trigger rollback.

## 22. Safe Transaction Handling Checklist

When designing a business operation that updates multiple tables:

1. Identify which business unit must succeed or fail together.
2. Start the transaction before related DML statements.
3. Verify affected row counts and business conditions.
4. Keep transactions short; avoid calling external services or waiting on users while holding locks.
5. Use SAVEPOINT only if partial cancellation while preserving earlier work is truly needed.
6. COMMIT only after all conditions succeed.
7. On error, ROLLBACK the proper scope and propagate the error to the caller.
8. Under READ COMMITTED, remember each statement has its own snapshot.
9. Use SERIALIZABLE or READ ONLY only when transaction-level snapshots are required and conflict handling is understood.
10. Use SELECT FOR UPDATE when explicit locking is required; pick WAIT/NOWAIT/SKIP LOCKED per requirements.
11. Never run DDL in the middle of a DML transaction that requires rollbackability.
12. Never assume sequences or external side effects can roll back.
13. With JDBC, set auto-commit false, explicitly call commit/rollback, then return the connection.
14. With Spring, let the transaction manager own the `@Transactional` boundary.
15. When retrying after ORA-08177 or transient errors, retry the entire unit of work with properly idempotent operations.

## 23. Practice Exercises

1. A session UPDATEs a balance without COMMITting. What value will another session see when SELECTing the same row? Explain using read consistency.
2. Why can the session executing the UPDATE run SELECT and see the new value even before COMMITting?
3. After COMMIT, does another session currently running a long SELECT switch to the new value mid-flight?
4. Distinguish between the statement-level snapshot in READ COMMITTED and the transaction-level snapshot in SERIALIZABLE.
5. Can two SELECTs in the same READ COMMITTED transaction return different results? Construct a two-session scenario illustrating this.
6. What are phantom rows? Describe using a SELECT with `WHERE STATUS = 'NEW'`.
7. Why does Oracle not need to block standard SELECTs when another session UPDATEs the same row?
8. What role does UNDO play in rollback and consistent read?
9. When might a long-running query encounter ORA-01555?
10. Write a money transfer transaction between two accounts so both UPDATEs COMMIT together.
11. If the second step of a transfer transaction fails, what must the application do?
12. How does SAVEPOINT differ from COMMIT? Why does SAVEPOINT not create a child transaction?
13. A transaction has already COMMITted when bad data is discovered. Can the old transaction be rolled back with ROLLBACK?
14. In what scenario can SERIALIZABLE encounter ORA-08177?
15. After ORA-08177, why is it usually necessary to ROLLBACK and retry the entire transaction?
16. At what point must `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` be called?
17. When is `SET TRANSACTION READ ONLY` useful for reports with multiple SELECT statements?
18. Compare standard SELECT and SELECT FOR UPDATE.
19. What needs do NOWAIT, WAIT n, and SKIP LOCKED address?
20. Why can DDL inside a DML transaction eliminate the ability to ROLLBACK earlier changes?
21. Why cannot TRUNCATE replace DELETE if rollback is required?
22. Why can sequences leave gaps even when an INSERT transaction rolled back?
23. An autonomous transaction writes an audit log and COMMITs. If the parent transaction ROLLBACKs, does the audit log remain?
24. How does JDBC `autoCommit = true` differ from `false` regarding transaction boundaries?
25. Why should you not rely on closing a Connection to commit?
26. How does Spring `@Transactional` handle `RuntimeException` vs checked exceptions differently by default?
27. Can a database transaction rollback recall a sent email or HTTP request?
28. Design a two-session test proving B only sees A's COMMITted data.
29. Design a test proving a running SELECT keeps its statement snapshot even if A COMMITs while B is reading.
30. When an application hits long lock waits, what session/transaction details should be inspected before terminating the blocking session?

**COMMIT confirms a transaction and makes changes visible to subsequent reads; ROLLBACK discards unconfirmed changes.** Oracle uses MVCC and UNDO so standard SELECTs read a consistent version without reading another session's uncommitted data. READ COMMITTED creates a snapshot per statement, while SERIALIZABLE and READ ONLY keep a transaction-level snapshot. Understanding these boundaries helps you design short transactions, handle locks properly, and avoid confusion when multiple sessions operate on shared data.
