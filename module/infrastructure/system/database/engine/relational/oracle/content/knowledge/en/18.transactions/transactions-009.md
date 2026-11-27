# READ COMMITTED and Per-Statement Snapshots in Oracle Database

## 1. Why Can Two SELECTs in the Same Transaction See Different Results?

An application often runs multiple SQL statements within one transaction: reading a balance, checking a condition, recording a transaction, then re-reading a report. Meanwhile, other sessions may also be INSERTing, UPDATEing, or DELETEing data and COMMITting.

Imagine two sessions working concurrently:

- Session A starts a transaction and reads the total order count.
- Session B inserts a new order and COMMITs.
- Session A re-runs the SELECT for total order count.

In Oracle under the default **READ COMMITTED** isolation level, A's second SELECT can see the order B just committed, even though A's transaction has not ended.

That is because Oracle uses **statement-level read consistency**: each query sees data COMMITted as of the time that statement starts. Two different SELECT statements in the same transaction can have two different data snapshots.

This property underpins Oracle's concurrency model:

- Never reads another session's uncommitted data (no dirty reads).
- A single SELECT has a consistent snapshot throughout its execution.
- Subsequent SQL statements can see changes COMMITted after the previous statement started.
- Standard readers do not need to lock rows for reading; Oracle can reconstruct older versions via undo.

This lesson explains READ COMMITTED, SCN, consistent read, undo, repeatable-read phenomena, SELECT FOR UPDATE, and options when business logic requires a consistent snapshot across multiple statements.

> Content uses Oracle Database 19c. SQL examples can be run in a dedicated lab schema; table names and data are illustrative. Do not run DML commands in production without verifying predicates and transactions.

## 2. What Is READ COMMITTED?

**READ COMMITTED** is Oracle Database's default transaction isolation level. A SQL statement reads only data COMMITted by other transactions before the statement began, along with changes created by the current transaction itself.

Two time scopes must be distinguished:

| Scope | READ COMMITTED |
| --- | --- |
| One SQL statement | Sees one consistent snapshot as of the time the statement starts |
| Multiple SQL statements in the same transaction | Each statement can see a newer snapshot, including commits from other sessions completed before that statement started |

Example:

~~~sql
-- READ COMMITTED is Oracle's default.
SELECT COUNT(*) FROM orders;

-- Another session may COMMIT here.

SELECT COUNT(*) FROM orders;
~~~

If another session inserts an order and COMMITs between the two SELECTs, the second COUNT result can be larger than the first.

This is not a consistency bug. Each SELECT is consistent with its own snapshot; a READ COMMITTED transaction does not promise to preserve one snapshot across all statements.

### 2.1. READ COMMITTED Is Not "Reading the Newest Data at Every Instant While a Query Runs"

A long SELECT might start at 10:00 and run until 10:05. If another session COMMITs a change at 10:02, the running SELECT continues reading according to the snapshot established when it started. A new SELECT starting at 10:03 can see that change.

Therefore, do not think of READ COMMITTED as Oracle grabbing whatever newest version exists at the exact instant it touches a data block. Oracle maintains consistency at **the statement level**.

### 2.2. Oracle Does Not Allow Dirty Reads

Suppose Session B UPDATEs a row without COMMITting yet. Session A runs a standard SELECT:

- A does not see B's uncommitted value.
- A sees the previously COMMITted version.
- If B ROLLBACKs, the old value remains the true value.

Oracle does not support a READ UNCOMMITTED isolation level as a standard transaction option. READ COMMITTED always guarantees not reading uncommitted data from other transactions.

## 3. SCN: The Marker Defining Data Snapshots

Oracle uses the **System Change Number (SCN)** to order changes in the database. You can think of an SCN as a logical database milestone that lets Oracle know which data versions existed at a given point.

When a query starts, Oracle determines a snapshot SCN for that statement. The query must return results based on changes COMMITted at or before that snapshot.

~~~text
Time --------------------------------------------------------->

SCN 100             SCN 105                SCN 110
  |                    |                      |
  |                    |                      +-- Session B COMMIT
  |                    |
  +-- Query A starts   +-- Query A still running
      snapshot=100         does not see commit at SCN 110

Query B starts after commit:
snapshot >= 110, can see B's change
~~~

SCN is an internal logical mechanism, not a wall-clock timer. Do not compare SCNs like seconds or derive exact timestamps from SCN differences.

### 3.1. Why Can a Query Still Read the Old Version?

Suppose a row initially has balance 1,000. Session B updates it to 1,200 and COMMITs. A query in Session A that started before that commit must still see 1,000.

Oracle uses undo information to reconstruct the data version matching A's snapshot:

~~~text
Current version in data block: 1,200
                         |
                         | undo holds prior version info
                         v
Consistent version for older snapshot: 1,000
~~~

This is part of **multiversion concurrency control (MVCC)**. Instead of forcing readers to wait for writers to retrieve data, Oracle can use undo to read the appropriate version.

### 3.2. Observing the Current SCN

In an environment with appropriate privileges:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

The function returns the current SCN supplied by the database at call time. An SCN can be used in Flashback Query or diagnostic tools when privileges and appropriate undo data exist.

Do not confuse:

- `SYSDATE`/`SYSTIMESTAMP`: time according to the database host clock.
- `SCN`: logical milestone ordering changes in the database.
- `COMMIT`: ends a transaction and publishes changes; Oracle assigns commit order via the SCN mechanism.

## 4. Consistent Read and Undo

**Consistent read** is how Oracle provides data versions matching a query's snapshot SCN.

When a query reads a block modified by another transaction after the snapshot:

1. Oracle recognizes the current version is newer than the snapshot.
2. Oracle uses undo records to reconstruct the needed prior version.
3. The query continues reading the version matching its start time.

This prevents a single SELECT from seeing half before and half after another transaction.

### 4.1. Undo Is Not Just for ROLLBACK

Undo serves multiple roles:

- Undoing changes when a transaction ROLLBACKs.
- Reconstructing older data versions for consistent reads.
- Supporting Flashback Query and certain other flashback capabilities within retained undo limits.
- Supporting transaction recovery and post-crash consistency per Oracle mechanisms.

Undo is not an infinite historical archive. Oracle manages undo space and can reuse undo records once no longer needed according to retention policies and system state.

### 4.2. ORA-01555: snapshot too old

A long query needs an older version of a block, yet the necessary undo has been overwritten/reused before the query finishes. Oracle cannot reconstruct the snapshot and may raise:

~~~text
ORA-01555: snapshot too old
~~~

Common causes:

- Query runs long while data is frequently UPDATEd/DELETEd.
- Undo tablespace is insufficient for the workload and query duration.
- `UNDO_RETENTION` is inadequate for requirements.
- Application keeps cursors open too long or processes row-by-row too slowly.

Investigation steps:

1. Record query duration, error timestamp, and concurrent DML workload.
2. Inspect undo tablespace configuration, size, and retention.
3. Review long-running queries and how the application fetches data.
4. Optimize queries, reduce processing time, or tune undo within storage capacity.
5. If retention must be guaranteed for a specific target, DBAs can evaluate `RETENTION GUARANTEE` alongside its impact on undo space allocation.

Do not assume simply increasing `UNDO_RETENTION` fixes every case. Without enough space, retention guarantee can cause DML to fail because Oracle cannot reuse protected undo. Undo configuration changes require DBA evaluation.

## 5. Two-Session Simulation: Each SELECT Has a Snapshot

We use a small balance table to observe behavior. Create only in a lab schema:

~~~sql
CREATE TABLE account_balance_lab (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_balance_lab VALUES (1, 1000);
COMMIT;
~~~

### 5.1. Sequence of Operations

| Step | Session A | Session B |
| --- | --- | --- |
| 1 | SELECT balance ... → 1,000 | |
| 2 | | UPDATE ... SET balance = 1200 ... |
| 3 | | COMMIT |
| 4 | SELECT balance ... → 1,200 | |

Session A can see the new value on the second SELECT, even though A neither COMMITted nor ended its transaction between the two reads.

### 5.2. Session A

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = 1;
~~~

Suppose the result is 1,000.

### 5.3. Session B

~~~sql
UPDATE account_balance_lab
SET balance = 1200
WHERE account_id = 1;

COMMIT;
~~~

### 5.4. Session A Reads Again

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = 1;
~~~

The result is now 1,200. This is a classic example of statement-level read consistency in READ COMMITTED.

## 6. One SELECT Never Mixes Two Data Versions

It is important to distinguish two scenarios:

- **Two SELECT statements:** each statement can see a different snapshot.
- **One single SELECT statement:** all parts of the statement read from that statement's snapshot.

Query example:

~~~sql
SELECT d.department_id,
       d.department_name,
       COUNT(e.employee_id) AS employee_count,
       SUM(e.salary) AS salary_total
FROM departments d
LEFT JOIN employees e
       ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name;
~~~

Oracle will not let a JOIN read `DEPARTMENTS` at one point in time and read `EMPLOYEES` at a newer point in time while the same statement executes. The statement has statement-level read consistency.

This also applies when a query uses multi-table JOINs, inline views, subqueries, common table expressions (`WITH`), aggregates, or analytic functions. Query blocks do not create separate new transaction snapshots merely by being written as subqueries; they belong to the same SQL statement.

## 7. READ COMMITTED Permits Nonrepeatable Reads and Phantom Reads Across Statements

READ COMMITTED prevents dirty reads, yet does not hold one shared snapshot for the entire transaction. Hence, data can change between two queries.

### 7.1. Nonrepeatable Read

A row read the first time returns a different value when read again:

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  UPDATE balance = 150
                                  COMMIT
SELECT balance = 150
~~~

Session A read the exact same row twice and received two different values. This is called a nonrepeatable read.

### 7.2. Phantom Read

The set of rows matching a predicate changes between two queries:

~~~text
Session A                         Session B
---------                         ---------
SELECT COUNT(*) = 3
  WHERE status='OPEN'
                                  INSERT an OPEN order
                                  COMMIT
SELECT COUNT(*) = 4
  WHERE status='OPEN'
~~~

The later query sees an additional new row matching the predicate. That row is called a phantom row relative to the earlier read.

### 7.3. Comparison Table

| Phenomenon | Meaning | Oracle READ COMMITTED |
| --- | --- | --- |
| Dirty read | Reading uncommitted changes from another transaction | Does not occur |
| Nonrepeatable read | Re-reading the same row and seeing changed value after another commit | Can occur between statements |
| Phantom read | Set of rows matching a predicate changes between statements | Can occur between statements |
| Inconsistent read within one statement | One query seeing parts of data at inconsistent snapshots | Prevented by statement-level read consistency |

READ COMMITTED fits many OLTP applications because transactions are short and need to see newly committed data. However, if a business process needs multiple queries to see one consistent data state, a more suitable mechanism must be chosen.

## 8. READ COMMITTED and Transaction Boundaries

A transaction starts when a session executes the first SQL statement after the previous transaction ends. The transaction ends with COMMIT or ROLLBACK. Under READ COMMITTED, a SELECT's snapshot is tied to when that SELECT begins, not fixed to when the transaction began.

~~~sql
COMMIT;

-- First statement in the new transaction.
SELECT COUNT(*) FROM orders;

-- Another session may COMMIT here.

SELECT COUNT(*) FROM orders;

COMMIT;
~~~

The two SELECTs can return different results.

### 8.1. SET TRANSACTION ISOLATION LEVEL READ COMMITTED

You can declare it explicitly:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM orders;
~~~

READ COMMITTED is already the default, so re-declaring it is usually unnecessary. `SET TRANSACTION` must be the first statement of the transaction; place it before SELECT/INSERT/UPDATE/DELETE in that transaction.

Do not place `SET TRANSACTION` mid-transaction after DML has already executed expecting to change the isolation level of earlier statements.

### 8.2. Client-Side Autocommit

Some tools or applications enable autocommit. Then each successful statement may commit immediately after running. Without controlling transaction boundaries, developers might mistakenly assume multiple SQL statements share the same transaction.

When running two-session experiments:

- Verify autocommit state.
- Confirm the exact time of COMMIT.
- Use two independent connections.
- Do not rely on the transaction state of another SQL tab.

## 9. Readers and Writers: Why Does Standard SELECT Not Lock Rows?

Oracle uses MVCC and consistent read to allow readers to see committed versions matching their snapshot without locking rows merely to read them.

With standard SELECT:

- Readers do not place row locks simply for reading a row.
- Writers can UPDATE rows while a query is running.
- The running query keeps reading its consistent version.
- Another query starting after the writer COMMITs can see the new version.

This improves OLTP concurrency: reporting reads do not inherently block update transactions, and writers do not have to wait for every standard SELECT to finish.

However, **a standard SELECT does not protect a business rule across multiple statements**. If an application reads and then decides to update based on the read value, an appropriate synchronization technique must be used.

## 10. Race Condition During Read-Then-Update

Suppose an account balance is 100. Two applications read the balance simultaneously and want to debit money:

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  SELECT balance = 100
Compute new balance = 90
                                  Compute new balance = 80
UPDATE balance = 90
COMMIT
                                  UPDATE balance = 80
                                  COMMIT
~~~

If both applications write a number calculated from the stale value, the final result may be 80. One update overwrote the other update's result. This is a form of lost update at the application logic layer.

READ COMMITTED does not automatically protect every multi-statement read-compute-write sequence. There are several ways to handle this.

### 10.1. Prefer Atomic Updates in One SQL Statement

If the business operation simply needs to debit money without allowing a negative balance:

~~~sql
UPDATE account_balance_lab
SET    balance = balance - :amount
WHERE  account_id = :account_id
AND    balance >= :amount;
~~~

Then check the affected row count in PL/SQL:

~~~plsql
IF SQL%ROWCOUNT = 0 THEN
    -- Account not found or insufficient balance.
    -- Distinguish the two cases if business rules require it.
    NULL;
END IF;
~~~

The predicate check and subtraction happen inside the same DML statement. Oracle locks the updated row; under contention, another transaction must wait, and the DML predicate is processed according to Oracle's write consistency mechanism.

If you need to distinguish "account missing" from "insufficient balance," you can follow up with an appropriate query or design distinct outcome codes. Do not over-infer solely from `SQL%ROWCOUNT`.

### 10.2. SELECT FOR UPDATE

If business logic genuinely must read the row, perform complex calculations in the application, and then write back, lock the row before reading:

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE;
~~~

Oracle locks the selected rows for the current transaction. Other sessions wanting to UPDATE/DELETE the same row must wait until the lock-holding transaction COMMITs or ROLLBACKs.

After acquiring the lock:

~~~sql
UPDATE account_balance_lab
SET    balance = balance - :amount
WHERE  account_id = :account_id;
~~~

`SELECT FOR UPDATE` suits multi-step read-modify-write workflows, provided you:

- Keep transactions short.
- COMMIT or ROLLBACK promptly upon completion.
- Lock rows in a consistent order when touching multiple accounts to reduce deadlock risk.
- Handle cases where no row is found or the row is already locked by another session.

### 10.3. Optimistic Locking with a Version Column

If you do not want to hold row locks during application processing time, use a version column:

~~~sql
ALTER TABLE account_balance_lab
ADD version_no NUMBER DEFAULT 0 NOT NULL;
~~~

The application reads `BALANCE` and `VERSION_NO`, e.g., version 7. When updating:

~~~sql
UPDATE account_balance_lab
SET    balance = :new_balance,
       version_no = version_no + 1
WHERE  account_id = :account_id
AND    version_no = :old_version_no;
~~~

If `SQL%ROWCOUNT = 1`, the update succeeded. If 0, the row was modified or no longer meets the condition; the application must re-read and resolve the conflict.

Optimistic locking fits when conflicts are rare and the application can retry. The version column must be incremented consistently by every write path.

## 11. SELECT FOR UPDATE and Lock-Wait Options

`SELECT FOR UPDATE` is a locking read, distinct from a standard SELECT.

### 11.1. Basic Syntax

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE;
~~~

The row is locked for the current transaction. The lock persists until COMMIT or ROLLBACK.

### 11.2. NOWAIT

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE NOWAIT;
~~~

If the row is already locked by another session, the statement does not wait and returns an error immediately (typically `ORA-00054` in a resource busy context).

### 11.3. WAIT n

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE WAIT 5;
~~~

The session waits up to the specified number of seconds to acquire the lock. If the timeout expires without acquiring it, the statement raises an error.

### 11.4. SKIP LOCKED

~~~sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` skips rows currently locked by other sessions instead of waiting. This technique is useful for multiple workers dequeuing tasks from a queue, yet requires designing status transitions, leases/timeouts, and recovery to avoid orphaned jobs.

Do not use `SKIP LOCKED` for general data-reading queries: it intentionally omits locked rows, so the result is not a complete list.

### 11.5. Locking Reads Are Not for Keeping Report Snapshots

If the sole goal is for multiple SELECTs to see the same snapshot, locking every row with `SELECT FOR UPDATE` is overly heavy and changes semantics. Consider a `READ ONLY` transaction, `SERIALIZABLE`, or Flashback Query `AS OF SCN`.

## 12. When You Need a Snapshot Across an Entire Transaction

READ COMMITTED works well when each statement is permitted to see newer commits. However, certain reports or reconciliations require multiple queries to observe the same data state.

Oracle provides two common transaction-level isolation options:

- `SET TRANSACTION READ ONLY`: read-only transaction maintaining one consistent snapshot for queries within the transaction.
- `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`: transaction has a transaction-level consistent snapshot and can still perform DML; write conflicts may raise `ORA-08177`.

### 12.1. READ ONLY Transactions

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT SUM(order_total) FROM orders;
SELECT COUNT(*) FROM order_lines;

COMMIT;
~~~

SELECTs in a read-only transaction see the same data snapshot established when the transaction started. Commits from other sessions after that point do not alter the snapshot results of subsequent SELECTs in the transaction.

Characteristics:

- Used for reports with multiple queries that must be mutually consistent.
- Disallows INSERT, UPDATE, DELETE, and MERGE inside the read-only transaction.
- Disallows `SELECT FOR UPDATE` inside the read-only transaction.
- Still requires ending with COMMIT or ROLLBACK to release resources and close the snapshot scope.

### 12.2. SERIALIZABLE Transactions

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM account_balance_lab
WHERE account_id = 1;

-- DML can be executed in the transaction.
UPDATE account_balance_lab
SET balance = balance - 10
WHERE account_id = 1;

COMMIT;
~~~

SERIALIZABLE provides transaction-level read consistency: queries see data committed as of when the transaction began, plus changes made by that transaction itself.

Unlike READ ONLY, SERIALIZABLE allows DML. However, if the transaction attempts to modify a row changed and committed by another transaction after the serializable transaction began, Oracle can raise:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

The application must handle this by ROLLBACKing and retrying the entire transaction under a safe policy, if business rules permit. Do not retry only the UPDATE statement while keeping decisions computed from a stale snapshot.

### 12.3. Comparing the Three Modes

| Feature | READ COMMITTED | READ ONLY | SERIALIZABLE |
| --- | --- | --- | --- |
| Oracle default | Yes | No | No |
| Snapshot | Per statement | Transaction-level | Transaction-level |
| Sees new commits between queries in same transaction | Possible | No | No |
| DML in transaction | Yes | No | Yes |
| SELECT FOR UPDATE | Yes | No | Yes, subject to transaction limits |
| Write conflict | May wait on locks and proceed per write consistency | No DML by transaction | Possible ORA-08177 |
| Best suited for | General OLTP | Multi-query consistent reports | Transactions needing a transaction snapshot with serialization conflict handling |

READ ONLY and SERIALIZABLE are not automatically better than READ COMMITTED. They hold snapshots longer and may require retaining undo longer; SERIALIZABLE also requires the application to handle serialization errors.

## 13. Phantom Read Example and Preserving a Snapshot

Suppose table `ORDERS` has three `OPEN` orders.

### 13.1. READ COMMITTED

Session A:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Result: 3.

Session B:

~~~sql
INSERT INTO orders (order_id, status, order_total)
VALUES (9001, 'OPEN', 100);

COMMIT;
~~~

Session A runs again:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Result: 4.

### 13.2. READ ONLY

Session A:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Session B inserts and COMMITs the new order as above.

Session A re-runs the same SELECT inside the READ ONLY transaction:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';

COMMIT;
~~~

Result remains 3 because A's queries use the READ ONLY transaction's snapshot.

Once the READ ONLY transaction ends, a new query in the next transaction will see the new commit.

## 14. Flashback Query AS OF SCN: Using One Milestone Across Multiple SQL Statements

Another option is capturing an SCN and using `AS OF SCN` to query tables at that exact milestone. This is useful when multiple independent SQL statements must reference the same snapshot, or when comparing historical data within Flashback Query's supported window.

### 14.1. Capturing the SCN

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS snapshot_scn
FROM dual;
~~~

The application stores this SCN value and passes it into subsequent queries.

### 14.2. Querying One Table at a Fixed SCN

~~~sql
SELECT order_id, status, order_total
FROM orders AS OF SCN :snapshot_scn
WHERE status = 'OPEN';
~~~

### 14.3. Querying Multiple Tables at the Same SCN

~~~sql
SELECT o.order_id,
       o.status,
       l.line_no,
       l.product_id,
       l.quantity
FROM orders AS OF SCN :snapshot_scn o
JOIN order_lines AS OF SCN :snapshot_scn l
  ON l.order_id = o.order_id
WHERE o.status = 'OPEN';
~~~

Every table uses the exact same `:snapshot_scn`, so the join reflects data at the same point in time. If one table omitted the SCN, results could combine versions from different times.

### 14.4. Prerequisites and Limitations

- Appropriate privileges are required to use Flashback Query.
- Required undo must still be available; if historical undo was reused, the query can fail.
- The SCN must fall within the flashback-capable retention window.
- Do not use Flashback Query as a long-term backup.
- Account for DDL, object modifications, and release-specific flashback restrictions.

`AS OF SCN` is an explicit snapshot per query. It does not change the isolation level of the current transaction.

## 15. Distinguishing READ COMMITTED and SERIALIZABLE Across Two Sessions

### 15.1. Scenario

Initially there is one row:

~~~sql
CREATE TABLE isolation_demo_lab (
    id NUMBER PRIMARY KEY,
    value_no NUMBER NOT NULL
);

INSERT INTO isolation_demo_lab VALUES (1, 10);
COMMIT;
~~~

### 15.2. Session A: SERIALIZABLE

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT value_no
FROM isolation_demo_lab
WHERE id = 1;
~~~

Result is 10. Transaction A has established its snapshot.

### 15.3. Session B: Update and COMMIT

~~~sql
UPDATE isolation_demo_lab
SET value_no = 20
WHERE id = 1;

COMMIT;
~~~

### 15.4. Session A Reads Again

~~~sql
SELECT value_no
FROM isolation_demo_lab
WHERE id = 1;
~~~

A still sees 10 because the SERIALIZABLE transaction's snapshot is preserved from the start of the transaction.

If A tries to update the row B modified after A started:

~~~sql
UPDATE isolation_demo_lab
SET value_no = 30
WHERE id = 1;
~~~

Oracle can return `ORA-08177`. A must then ROLLBACK and decide whether to re-run the entire transaction.

### 15.5. Re-Running with READ COMMITTED

End Transaction A and start a new READ COMMITTED transaction. Two separate SELECTs can see 10 before B's commit and 20 after B's commit, depending on timing.

## 16. DML Write Consistency

Read consistency and write consistency are related yet distinct.

A standard SELECT reads a snapshot at statement start. A DML statement must also evaluate data consistently while acquiring locks to modify rows. When DML encounters a row locked by another transaction, it may wait.

Example:

~~~sql
UPDATE inventory
SET    quantity = quantity - 1
WHERE  product_id = :product_id
AND    quantity > 0;
~~~

If two sessions update this row concurrently, Oracle manages row locks and DML predicates via write consistency. When necessary, Oracle may re-evaluate the statement after waiting on a conflict to avoid acting erroneously on stale predicates. Restart details depend on scenario and version; do not build application logic assuming every DML always runs exactly once or is never re-evaluated.

Good practices:

- Place business conditions directly in the `UPDATE`/`DELETE` statement when possible.
- Check `SQL%ROWCOUNT`.
- Use locks or a version column for multi-step workflows.
- Keep transactions short and define a clear retry policy.
- Do not rely on a prior SELECT to guarantee a row still satisfies the condition in a subsequent DML statement.

## 17. READ COMMITTED in Applications and Connection Pools

An application typically uses a connection pool where the same database session may be borrowed by different requests at different times.

Risks to manage:

### 17.1. Unfinished Transactions

If a request forgets to COMMIT or ROLLBACK, the session can hold row locks and undo longer than expected. When the connection returns to the pool, the next request may encounter unexpected transaction state if the pool does not reset it properly.

### 17.2. Isolation Level Is Session/Transaction State

`SET TRANSACTION` applies to the current transaction. Applications must set it properly at the start of the transaction and end the transaction before returning the connection to the pool.

### 17.3. Autocommit and Multiple Statements

If autocommit is enabled, each statement can become its own transaction. You then cannot assume two SELECTs share a transaction merely because they run on the same connection.

### 17.4. Implementation Rules

- Start and end transactions explicitly in the service/repository layer.
- Always roll back when handling exceptions before returning the connection to the pool.
- Do not leave transactions open while waiting for user input or calling external APIs.
- Do not alter isolation levels arbitrarily on shared connections.
- When a snapshot across multiple queries is needed, deliberately use `READ ONLY`/`SERIALIZABLE` or `AS OF SCN`.

## 18. Common Errors Related to Read Consistency

| Error | Common Cause | Resolution |
| --- | --- | --- |
| ORA-01555: snapshot too old | Undo needed for consistent read is no longer available | Investigate long queries, concurrent DML, undo tablespace/retention |
| ORA-08177: can't serialize access for this transaction | SERIALIZABLE transaction encountered a row modified by another transaction after snapshot | ROLLBACK and consider retrying the entire transaction |
| ORA-00054: resource busy and acquire with NOWAIT specified | `SELECT FOR UPDATE NOWAIT` or lock operation cannot wait | Handle retry/backoff or report resource busy |
| Second query sees different numbers from first query | READ COMMITTED uses a fresh snapshot for new statements | Use READ ONLY/SERIALIZABLE/AS OF SCN if a shared snapshot is needed |
| Two requests overwrite each other's results | Multi-statement read-modify-write without locks/versions/atomic update | Use atomic DML, `SELECT FOR UPDATE`, or optimistic locking |
| SELECT FOR UPDATE hangs | Another session holds a row lock and the statement is waiting | Check blocker; use `WAIT`/`NOWAIT`/`SKIP LOCKED` per business needs |
| Multi-table report reflects inconsistent times | Independent statements ran under READ COMMITTED or different `AS OF SCN` values | Use one transaction snapshot or the exact same SCN across all tables |

## 19. Lab Practice: Observing READ COMMITTED

> Two independent Oracle connections are needed, e.g., two SQL Developer worksheets or two SQLcl terminals. Do not use two tabs if they actually share the same session.

### Exercise A — Two SELECTs in One Transaction

1. Create table `isolation_demo_lab` and insert one row as in Section 15.
2. Session A runs `SELECT value_no`.
3. Session B UPDATEs value to 20 and COMMITs.
4. Session A re-runs `SELECT`.
5. Record both results.

Expected: A reads 10 first and 20 second if B commits before the second SELECT starts.

### Exercise B — A Long SELECT and a Mid-Flight Commit

Design a query reading many rows or running long enough in the lab. While the query is running, have another session update some rows and COMMIT.

Observe: the running query continues using the statement-start snapshot; a new query starting after the commit can see the new values.

Do not use `DBMS_LOCK.SLEEP` or load-generating tricks on production. Test only in a lab database in a controlled manner.

### Exercise C — READ ONLY Transaction

1. Session A runs `COMMIT; SET TRANSACTION READ ONLY;`.
2. A runs the first SELECT.
3. Session B INSERTs a row and COMMITs.
4. A re-runs SELECT.
5. A ends with `COMMIT`.
6. A runs SELECT in a new transaction.

Expected: both queries inside READ ONLY see the same snapshot; the query in the new transaction sees B's committed row.

### Exercise D — SERIALIZABLE Conflict

1. Session A starts SERIALIZABLE and reads the row.
2. Session B updates that row and COMMITs.
3. Session A attempts to update the same row.
4. Observe `ORA-08177` if the scenario produces a serialization conflict.
5. ROLLBACK A and retry the entire transaction against the new data.

### Exercise E — SELECT FOR UPDATE

1. A runs `SELECT FOR UPDATE` on an account.
2. B attempts to UPDATE the same account.
3. Observe B waiting.
4. A COMMITs.
5. B proceeds.

Retry with `NOWAIT` and `WAIT 3` in the lab to compare behavior.

### Exercise F — Flashback Query with the Same SCN

1. Capture an SCN via `DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER`.
2. B modifies data and COMMITs.
3. Query `AS OF SCN` using the saved SCN.
4. Run a normal query.
5. Compare the two results.

Expected: Flashback Query reads state at the chosen SCN; standard SELECT reads the statement's new snapshot.

## 20. Checklist for Choosing a Consistency Mechanism

1. **Does one SELECT need internal consistency?** Oracle already provides statement-level read consistency under READ COMMITTED.
2. **Do multiple SELECTs need the exact same snapshot?** Consider READ ONLY, SERIALIZABLE, or `AS OF SCN`.
3. **Does the transaction need DML?** READ ONLY forbids DML; SERIALIZABLE allows DML but can hit `ORA-08177`.
4. **Is there a read-then-write on the same row?** Use atomic DML, `SELECT FOR UPDATE`, or optimistic locking.
5. **Do you need a complete list of pending rows?** Do not use `SKIP LOCKED` if skipping locked rows is unacceptable.
6. **Is the query long-running?** Evaluate undo retention and `ORA-01555` risk.
7. **Is a connection pool/autocommit involved?** Control transaction boundaries and session resets.
8. **Do multiple tables need to be read at the same historical point?** Use the exact same SCN for all tables in Flashback Query.
9. **Are retries safe?** Only retry entire transactions when idempotency or duplicate-write prevention exists.
10. **Have privileges and release limits been checked?** READ ONLY, SERIALIZABLE, Flashback, and locking have specific syntax/restrictions.

## 21. Self-Check Questions

**Q1.** What is Oracle's default transaction isolation level?

**Q2.** In READ COMMITTED, is the snapshot determined at the statement level or transaction level?

**Q3.** If another transaction COMMITs between two SELECTs of the same transaction, can the second SELECT see the new data?

**Q4.** Does a currently running SELECT see commits that occur after the statement began?

**Q5.** Which mechanism does Oracle use to reconstruct older versions for consistent reads?

**Q6.** Does READ COMMITTED allow dirty reads?

**Q7.** How do nonrepeatable reads and phantom reads differ?

**Q8.** How does a READ ONLY transaction differ from a SERIALIZABLE transaction regarding DML rights?

**Q9.** Which resource is ORA-01555 typically related to?

**Q10.** In what context does ORA-08177 appear?

**Q11.** How does SELECT FOR UPDATE differ from a standard SELECT?

**Q12.** When should you use AS OF SCN?

**Q13.** Why is a single atomic UPDATE generally safer than a SELECT followed by an UPDATE using an application-held value?

**Q14.** Why should you avoid keeping a transaction open while waiting for a user or calling an API?

<details>
<summary>Suggested Answers</summary>

1. READ COMMITTED.
2. Statement level; each statement gets its own snapshot.
3. Yes. If the commit finishes before the second SELECT starts, the second query can see the change.
4. No. A running query continues using the snapshot from when it began.
5. Undo records and consistent read.
6. No. Oracle never lets a transaction read uncommitted changes from another transaction.
7. Nonrepeatable read is the same row changing value when re-read; phantom read is the set of rows matching a predicate changing.
8. READ ONLY allows only queries; SERIALIZABLE allows DML but can encounter `ORA-08177`.
9. Required undo for the snapshot was reused or is no longer available.
10. A SERIALIZABLE transaction attempts to modify data changed by another transaction after its snapshot started.
11. `SELECT FOR UPDATE` acquires row locks to protect read-modify-write; standard SELECT only reads a consistent snapshot.
12. When multiple queries must read the exact same SCN milestone or query historical state.
13. The condition and modification execute within the same statement, eliminating the race window between reading and writing.
14. It can hold row locks, undo, and transaction resources too long, increasing lock waits and concurrency errors.

</details>

## 22. Official Oracle Documentation

1. [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, multiversion concurrency control, statement-level consistency, and transaction isolation.
2. [Oracle Database 19c Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction boundaries, COMMIT, ROLLBACK, and atomicity.
3. [Oracle Database 19c SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): READ COMMITTED, READ ONLY, and SERIALIZABLE.
4. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE and Flashback Query clauses.
5. [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo data, undo retention, and undo tablespace management.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): retrieving SCN and Flashback utilities.
7. [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/error-help/db/ora-01555/): snapshot too old.
8. [Oracle Database Error Messages — ORA-08177](https://docs.oracle.com/en/error-help/db/ora-08177/): cannot serialize access for this transaction.
9. [Oracle Database Error Messages — ORA-00054](https://docs.oracle.com/en/error-help/db/ora-00054/): resource busy when NOWAIT is requested.

**Key takeaway:** Oracle's READ COMMITTED creates a consistent snapshot for **each individual statement**. Therefore a running query never mixes in newer commits mid-flight, yet the next SELECT in the same transaction can see those commits. Oracle uses undo to reconstruct older versions for consistent reads. When multiple queries need a shared snapshot, consider READ ONLY, SERIALIZABLE, or Flashback Query `AS OF SCN`. When protecting a read-then-write sequence, use atomic DML, `SELECT FOR UPDATE`, or optimistic locking instead of assuming READ COMMITTED locks business logic across statements.
