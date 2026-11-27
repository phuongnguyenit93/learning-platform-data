# Two-Session Simulation to Verify Isolation and Locking Mechanisms

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Locking and Concurrency  
> **Objective:** Use two independent Oracle connections to observe read consistency, READ COMMITTED/SERIALIZABLE/READ ONLY isolation levels, row locks, table enqueues, SELECT FOR UPDATE, lost updates, blocking, and deadlocks. Know how to prepare lab data, execute step-by-step in order, recognize expected outcomes, and monitor waiting sessions.

## 1. Why simulate with two sessions?

Concurrency issues are difficult to understand by reading a single SQL statement in isolation. The exact same UPDATE statement may finish immediately or wait depending on which locks another transaction holds. A SELECT may read an older committed value while a writer modifies the row. Two transactions can both read the same value and overwrite each other's result if the application uses an uncontrolled read-modify-write pattern.

A two-session simulation makes the event timeline visible:

- Session A executes DML without running COMMIT.
- Session B reads or writes the same data.
- Observe whether B sees uncommitted changes, waits, or raises an error.
- A runs COMMIT/ROLLBACK to finish its transaction.
- B proceeds and the final result is verified.

In this lesson, a **session** is an independent database connection with its own transaction state. Two worksheets sharing one connection usually still share the same session; they cannot simulate two competing transactions.

| Phenomenon | What to Verify |
|---|---|
| Dirty read | Oracle does not allow regular SELECTs to see another session's uncommitted data |
| Nonrepeatable read | READ COMMITTED can return different values across two SELECTs in the same transaction |
| Phantom read | The same predicate can return additional rows after another session INSERTs and COMMITs |
| Write blocking | UPDATE/DELETE on the same row must wait for the transaction holding the row lock |
| Consistent read | Regular SELECTs can read older committed versions using undo |
| SELECT FOR UPDATE | Can lock rows for safer read-modify-write |
| SERIALIZABLE | SELECT statements in the transaction see the same snapshot; conflicting writes may receive ORA-08177 |
| Deadlock | Two transactions locking rows in opposite orders can form a wait cycle and trigger ORA-00060 |

## 2. Preparing the test environment

Use a dedicated lab schema with CREATE TABLE privileges. Never run scenarios intentionally causing blocking/deadlocks on production tables.

Open **two independent Oracle connections** to the same schema/database, clearly named Session A and Session B. You can use two connections in SQL Developer, two SQL*Plus windows, or two connections from a test application.

In SQL*Plus, disable autocommit:

~~~sql
SET AUTOCOMMIT OFF;
~~~

In SQL Developer or GUI tools, verify auto-commit settings and ensure transactions do not commit automatically after each statement. Do not share one connection/session between A and B.

Check the SID of each connection:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Record the SIDs of A and B. They must differ. SID lets you correlate V$SESSION when one session waits on the other.

### 2.1. Create lab data once

Run in a setup connection (or Session A before starting the experiments):

~~~sql
CREATE TABLE lab_iso_rows (
    row_id NUMBER CONSTRAINT pk_lab_iso_rows PRIMARY KEY,
    category VARCHAR2(20 CHAR) NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 1 NOT NULL,
    note VARCHAR2(100)
);

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (1, 'A', 100, 1, 'Initial row 1');

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (2, 'A', 200, 1, 'Initial row 2');

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (3, 'B', 300, 1, 'Initial row 3');

COMMIT;
~~~

Confirm initial state:

~~~sql
SELECT row_id, category, amount, version_no, note
FROM lab_iso_rows
ORDER BY row_id;
~~~

Result:

~~~text
ROW_ID  CATEGORY  AMOUNT  VERSION_NO
------  --------  ------  ----------
1       A         100     1
2       A         200     1
3       B         300     1
~~~

Do not re-run CREATE TABLE once the table exists. After each experiment, complete COMMIT/ROLLBACK before beginning the next scenario.

## 3. READ COMMITTED: statement-level snapshots

READ COMMITTED is Oracle's default isolation level. Each SELECT sees data committed at the moment the statement begins, plus changes made by the current transaction itself.

This has two consequences:

1. A SELECT never sees uncommitted data from another session.
2. Two SELECTs in the same transaction can see two different states if another session COMMITs in between.

### 3.1. Testing nonrepeatable read

**Step 1 — Session A:** read row 1:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Result: 100.

**Step 2 — Session B:** modify and commit:

~~~sql
UPDATE lab_iso_rows
SET amount = 150
WHERE row_id = 1;

COMMIT;
~~~

**Step 3 — Session A:** rerun the exact same SELECT:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Result: 150.

A read 100 in the first statement and 150 in the second statement, even though A had not ended its transaction. This is a **nonrepeatable read**: a row re-read within the same transaction can yield a different value under READ COMMITTED because each statement takes a fresh snapshot.

This is not a dirty read. The value 150 appeared only after B ran COMMIT.

### 3.2. Testing phantom read

A phantom read occurs when the same predicate is rerun and the matching row set gains or loses rows due to another committed transaction.

**Step 1 — Session A:** count rows in category A:

~~~sql
SELECT COUNT(*) AS rows_in_a
FROM lab_iso_rows
WHERE category = 'A';
~~~

Initial result: 2.

**Step 2 — Session B:** insert a row in category A and commit:

~~~sql
INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (4, 'A', 400, 1, 'Inserted by session B');

COMMIT;
~~~

**Step 3 — Session A:** rerun the same query:

~~~sql
SELECT COUNT(*) AS rows_in_a
FROM lab_iso_rows
WHERE category = 'A';
~~~

Result: 3.

Same predicate, yet the result set changed because READ COMMITTED creates a fresh snapshot for the second statement.

### 3.3. Demonstrating no dirty reads

**Step 1 — Session A:** UPDATE without committing:

~~~sql
UPDATE lab_iso_rows
SET amount = 999
WHERE row_id = 1;
~~~

**Step 2 — Session B:** SELECT row 1:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B reads the most recently committed value and does not see 999. If amount was 150 before the experiment, B still sees 150.

**Step 3 — Session A:** roll back:

~~~sql
ROLLBACK;
~~~

After rollback, the committed value remains 150. Oracle does not provide dirty reads for regular SELECTs like some engines that allow READ UNCOMMITTED.

## 4. Consistent reads and row locks are two different mechanisms

An important point when observing two sessions:

- Regular SELECT uses multiversion read consistency to read a snapshot.
- UPDATE/DELETE on the same row must coordinate via row locks.
- Regular readers do not wait on writers merely because a writer holds an uncommitted row lock.
- Writers wanting to modify the same row may have to wait for the lock-holding transaction to finish.

Example:

**Session A:**

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 20
WHERE row_id = 1;
-- Not yet COMMITted
~~~

**Session B:**

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B typically sees the committed value prior to A's UPDATE, does not see the uncommitted +20 increment, and does not wait on the row lock.

If B runs:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

B must wait for A to COMMIT or ROLLBACK because both want to modify the same row.

This is the foundation of Oracle concurrency control: regular reads do not block writes and writes do not block regular consistent reads; conflicts between writers still must be serialized.

## 5. Simulating write blocking on the same row

Before starting, ensure row 1 has a known amount and no stale open transactions remain.

### 5.1. Session A locks the row with UPDATE

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 20
WHERE row_id = 1;
~~~

Do not COMMIT. A holds the row lock on row 1 and the associated transaction lock.

### 5.2. Session B reads the same row

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B reads the committed version prior to A's UPDATE. B does not see uncommitted changes and regular SELECT normally completes immediately.

### 5.3. Session B UPDATEs the same row

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

B's statement waits because A holds the row lock. To observe this easily, do not commit A right away; move to the blocker-monitoring section.

### 5.4. Session A ends its transaction

In Session A:

~~~sql
COMMIT;
~~~

After A commits, B can proceed. Under READ COMMITTED, Oracle processes the current row per DML semantics after waiting; the addition amount = amount + 10 applies to the current value following A's change.

If A ran ROLLBACK instead of COMMIT, B proceeds on the restored state.

### 5.5. Verify the result

After both sessions finish:

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

If amount started at 150, A added 20 and B added 10, the final result is 180. Both additions were applied sequentially.

## 6. SELECT FOR UPDATE: locking rows before read-modify-write

If an application must read a value and then decide how to update based on what it read, it can lock the row beforehand with SELECT FOR UPDATE.

Session A:

~~~sql
SELECT row_id, amount, version_no
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE;
~~~

A reads the row and holds the row lock until COMMIT or ROLLBACK. Other sessions wanting to UPDATE/DELETE or SELECT FOR UPDATE the same row may have to wait.

After reading, A can update:

~~~sql
UPDATE lab_iso_rows
SET amount = amount - 25
WHERE row_id = 1;

COMMIT;
~~~

### 6.1. NOWAIT

While Session A holds row 1 locked, Session B can try:

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE NOWAIT;
~~~

If the row is held under an incompatible lock, B errors immediately, typically with:

~~~text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
~~~

NOWAIT fits when the application wants to report "currently being processed" rather than wait.

### 6.2. WAIT n

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE WAIT 5;
~~~

B waits up to the specified duration. If the time expires without the lock being released, Oracle may raise ORA-30006 (resource busy; acquire with WAIT timeout expired).

### 6.3. SKIP LOCKED

In a queue/worker model, a session can skip rows locked by other sessions:

~~~sql
SELECT row_id, note
FROM lab_iso_rows
WHERE row_id IN (1, 2, 3)
ORDER BY row_id
FOR UPDATE SKIP LOCKED;
~~~

If A holds row 2 locked, B can retrieve rows 1 and 3 without waiting on row 2. B also locks the rows it retrieves until its transaction ends.

SKIP LOCKED is useful for workers claiming tasks from a queue, provided you design claim/status/commit/retry so work is not dropped. It does not guarantee strict ordering fairness and does not replace business status validation.

### 6.4. When locks are released

Row locks from SELECT FOR UPDATE or DML are held until transaction COMMIT/ROLLBACK, not merely until the SELECT statement finishes.

Never open a transaction locking rows and then wait for user input or make long network calls. Keep lock hold times short.

## 7. Lost updates: two users editing from the same stale value

A common example produces no explicit lock error yet still loses updates at the application layer.

Suppose amount starts at 100:

1. A SELECTs amount and receives 100.
2. B SELECTs amount and also receives 100.
3. A computes 100 - 10 = 90.
4. B computes 100 + 20 = 120.
5. A UPDATEs amount = 90 and COMMITs.
6. B UPDATEs amount = 120 and COMMITs.

The final result is 120. A's subtraction of 10 was overwritten. This is a lost update caused by B writing an absolute value computed from stale data.

Example application statement:

~~~sql
UPDATE lab_iso_rows
SET amount = :p_new_amount
WHERE row_id = 1;
~~~

B had no idea the value it read earlier had become stale.

### 7.1. Approach 1: use relative updates in SQL

If business logic is simply adding/subtracting a delta, let the database compute against the current value:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + :p_delta
WHERE row_id = :p_row_id;
~~~

Oracle serializes writers on the same row. Once the earlier session finishes, the second session's addition applies to the current value instead of the stale value read by the client.

This does not fit every business rule, but is a strong choice for simple increments/decrements.

### 7.2. Approach 2: pessimistic locking with SELECT FOR UPDATE

The application locks the row before reading:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = :p_row_id
FOR UPDATE;
~~~

After acquiring the lock, the application computes and UPDATEs within the same transaction. Another session wanting to modify the same row must wait; after A commits, B reads the latest value when it acquires the lock.

### 7.3. Approach 3: optimistic locking with a version column

The table has a VERSION_NO column. The client reads amount and version:

~~~sql
SELECT amount, version_no
FROM lab_iso_rows
WHERE row_id = :p_row_id;
~~~

Suppose the client reads amount 100, version 1. On write, the client sends back the version it read:

~~~sql
UPDATE lab_iso_rows
SET amount = :p_new_amount,
    version_no = version_no + 1
WHERE row_id = :p_row_id
  AND version_no = :p_old_version;
~~~

The application checks the affected row count:

- ROWCOUNT = 1: update succeeded.
- ROWCOUNT = 0: the row was modified by another session or no longer exists; re-read and handle conflict.

You can check this in PL/SQL:

~~~sql
DECLARE
    l_new_amount NUMBER := 90;
    l_old_version NUMBER := 1;
BEGIN
    UPDATE lab_iso_rows
    SET amount = l_new_amount,
        version_no = version_no + 1
    WHERE row_id = 1
      AND version_no = l_old_version;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Concurrent modification detected'
        );
    END IF;
END;
/
~~~

Optimistic locking fits when conflicts are rare and you do not want to hold locks while users think. Pessimistic locking fits when you need to serialize read-modify-write directly inside a short transaction.

## 8. SERIALIZABLE: transaction-level snapshots

Under READ COMMITTED, each statement has its own snapshot. SERIALIZABLE provides a consistent transaction-level view anchored at the SCN when the transaction began.

Setting the isolation level must be the first operation in the transaction, before other SQL statements:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

### 8.1. Testing an unchanging snapshot

**Session A:**

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Record the value A sees.

**Session B:** update and commit:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 50
WHERE row_id = 1;

COMMIT;
~~~

**Session A:** rerun:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

A continues to see the value from its transaction snapshot, without switching to the new value B just committed. This contrasts with READ COMMITTED.

### 8.2. Testing write conflict and ORA-08177

While A remains in the SERIALIZABLE transaction that read row 1, B modified and committed that row after A's snapshot began.

A attempts:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

Oracle may report:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Oracle rejects the change to avoid violating serializable semantics. Applications typically must ROLLBACK and retry the entire transaction with a fresh snapshot, not merely repeat the failed statement.

After the test, A runs:

~~~sql
ROLLBACK;
~~~

### 8.3. SERIALIZABLE does not lock the whole table

SERIALIZABLE primarily changes snapshot scope and write-conflict handling rules. It does not simply lock the entire table to block all other transactions. Oracle still uses MVCC/undo and locks to coordinate DML.

## 9. READ ONLY transactions

A READ ONLY transaction lets multiple SELECT statements share the same transaction snapshot while disallowing DML inside that transaction.

Session A:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Session B updates and commits:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 25
WHERE row_id = 1;

COMMIT;
~~~

Session A reruns SELECT and still sees the older snapshot. If A attempts INSERT/UPDATE/DELETE inside the READ ONLY transaction, Oracle rejects it, typically with ORA-01456.

Finish:

~~~sql
COMMIT;
~~~

READ ONLY suits reporting workflows where multiple queries need the same point-in-time view of data. It does not block writers from modifying data; undo allows A to keep reading its snapshot.

## 10. Deadlock: two sessions locking in opposite orders

Blocking is one session waiting on another. A deadlock is a wait cycle, where each session holds a resource the other needs.

Use two rows: row 1 and row 2.

### 10.1. Sequence creating a deadlock

**Step 1 — Session A:** lock row 1:

~~~sql
UPDATE lab_iso_rows
SET note = 'A owns row 1'
WHERE row_id = 1;
~~~

Do not commit yet.

**Step 2 — Session B:** lock row 2:

~~~sql
UPDATE lab_iso_rows
SET note = 'B owns row 2'
WHERE row_id = 2;
~~~

Do not commit yet.

**Step 3 — Session A:** request row 2:

~~~sql
UPDATE lab_iso_rows
SET note = 'A wants row 2'
WHERE row_id = 2;
~~~

A waits because B holds row 2.

**Step 4 — Session B:** request row 1:

~~~sql
UPDATE lab_iso_rows
SET note = 'B wants row 1'
WHERE row_id = 1;
~~~

B waits because A holds row 1. The two sessions form a wait cycle.

Oracle detects the deadlock and one statement receives the error:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

### 10.2. Handling after ORA-00060

Oracle typically rolls back the deadlocking statement, not automatically the entire application transaction. The transaction may still hold locks acquired by earlier statements.

The session receiving the error must handle its transaction explicitly, usually running ROLLBACK on the entire transaction if the business unit must be retried. Once that session rolls back, the remaining session is unblocked and can proceed.

Do not assume that merely getting an error on one statement released all locks in the transaction.

### 10.3. Ways to reduce deadlocks

- Update multiple rows in the same locking order across all transactions, such as ascending ROW_ID.
- Keep transactions short.
- Never wait for users or call external APIs while holding locks.
- Partition batches so workers do not overlap on the same key sets.
- Use bounded retries and idempotency.
- Read deadlock traces to identify actual objects, SQL, and lock ordering.

## 11. Monitoring waiting and blocking sessions

While Session B hangs on UPDATE, use a monitoring connection (with privileges to read dynamic performance views) to identify the blocker.

### 11.1. Viewing SID and blocker

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       blocking_session_status,
       sql_id,
       prev_sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Key columns:

- SID/SERIAL#: session identifier.
- EVENT/WAIT_CLASS: wait type.
- SECONDS_IN_WAIT: wait duration.
- BLOCKING_SESSION: SID of the blocker.
- SQL_ID/PREV_SQL_ID: current/previous SQL statement.

In some states, BLOCKING_SESSION may be NULL or insufficient to show the full blocker chain. Combine V$SESSION, V$LOCK, and appropriate monitoring tools.

### 11.2. Viewing TX and TM enqueues

~~~sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM v$lock
WHERE type IN ('TX', 'TM')
ORDER BY type, sid;
~~~

- TX relates to transactions and commonly appears in row-lock contention.
- TM relates to table enqueues.
- LMODE is the held mode.
- REQUEST is the waited-for mode.
- BLOCK shows blocking status per the view.

### 11.3. Viewing locked objects

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

V$LOCKED_OBJECT shows object-level DML locks; it does not enumerate every row lock as a list of rows. Combine blocker SID, SQL_ID, and transaction owner to pinpoint root cause.

V$ and DBA views may require SELECT_CATALOG_ROLE or explicit SELECT grants. Application accounts do not need broad DBA privileges just to run normal DML.

### 11.4. Recording SID in each session

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

Record A and B's SIDs before inducing blocking. When a blocker appears, match the SID in V$SESSION against your two open connections.

## 12. Matrix of expected outcomes

| Experiment | Session A | Session B | Observed Outcome |
|---|---|---|---|
| Dirty read | Uncommitted UPDATE | SELECT same row | B sees old committed value |
| Nonrepeatable read | SELECT, wait for B commit, SELECT again | UPDATE + COMMIT | A's first and second reads can see different values |
| Phantom | COUNT, wait for B insert commit, COUNT again | INSERT matching predicate + COMMIT | A sees row count increase |
| Writer blocking | Uncommitted UPDATE row 1 | UPDATE row 1 | B waits for A |
| Consistent read | Uncommitted UPDATE | SELECT row 1 | B does not wait and does not see uncommitted value |
| NOWAIT | Holds row lock | SELECT FOR UPDATE NOWAIT | B returns ORA-00054 |
| WAIT | Holds row lock | SELECT FOR UPDATE WAIT n | B waits up to n seconds then errors if unreleased |
| SKIP LOCKED | Holds some rows | SELECT FOR UPDATE SKIP LOCKED | B retrieves unlocked rows |
| SERIALIZABLE | Starts snapshot then SELECTs | UPDATE + COMMIT | A continues seeing old snapshot |
| SERIALIZABLE write conflict | A snapshotted row | B updates and commits, A updates same row | A may receive ORA-08177 |
| Deadlock | Locks row 1 then waits for row 2 | Locks row 2 then waits for row 1 | One statement receives ORA-00060 |

## 13. Errors and how to interpret them

| Error / Event | Meaning in Experiment | Action to Take |
|---|---|---|
| ORA-00054 | NOWAIT failed to acquire resource lock | Retry later or report busy |
| ORA-30006 | WAIT timed out acquiring lock | Adjust timeout or handle retry |
| ORA-00060 | Deadlock detected | Inspect trace, roll back appropriate transaction, retry safely |
| ORA-08177 | SERIALIZABLE could not serialize change | Roll back and retry full transaction |
| ORA-01456 | DML not permitted in READ ONLY transaction | End read-only transaction or use another transaction |
| enq: TX - row lock contention | Waiting on transaction/row lock | Identify blocker and business row |
| enq: TM - contention | Waiting on table enqueue | Inspect object, lock mode, and DDL |

An error code is only a symptom. Combine SQL, transaction state, object, and operation order to determine root cause.

## 14. Design principles for concurrent applications

### 14.1. Choosing the right locking strategy

| Need | Suitable Strategy |
|---|---|
| Read-only access | Regular SELECT with consistent read |
| Read-modify-write in a short transaction | SELECT FOR UPDATE |
| Rare conflicts, many editing users | Optimistic locking with version column |
| Adding/subtracting deltas | UPDATE col = col + delta |
| Workers pulling tasks from queue | SELECT FOR UPDATE SKIP LOCKED and claim mechanism |
| Multi-query reporting sharing one snapshot | READ ONLY or SERIALIZABLE depending on semantics |

### 14.2. Keep transactions short

Do not leave transactions open while users view screens, enter data, or wait on external services. If state must span multiple requests, use optimistic versioning or a dedicated business state rather than holding database locks for long periods.

### 14.3. Retries must be safe

A serialization error or deadlock may require rerunning a transaction. Before retrying:

- Roll back the transaction cleanly.
- Verify whether the operation is idempotent.
- Never resend external payments/notifications just because a database transaction retried.
- Use idempotency keys or the outbox pattern when coordinating DB and external systems.
- Use bounded retries, backoff, and adequate logging.

### 14.4. Choose isolation levels per requirements

READ COMMITTED fits most Oracle OLTP workloads. SERIALIZABLE and READ ONLY are useful when business logic requires transaction-level snapshots, though they can expose transactions to serialization conflicts or require keeping undo longer.

Do not raise the isolation level just to "prevent all concurrency bugs." Isolation levels do not replace row locks, version checks, or sound transaction design.

## 15. Cleaning up data after the experiments

Before cleaning up, ensure neither A nor B has an open transaction. Run explicit COMMIT or ROLLBACK in each session. Then, in one connection:

~~~sql
SELECT row_id, category, amount, version_no, note
FROM lab_iso_rows
ORDER BY row_id;
~~~

When lab data is no longer needed:

~~~sql
DROP TABLE lab_iso_rows PURGE;
~~~

Oracle DDL performs implicit commits before/after DDL in standard contexts. Therefore, run DROP TABLE only after all lab transactions have finished; never use DDL to try to clear locks while an experiment is still running.

## 16. Self-simulation checklist

- [ ] Open two independent database connections and verify different SIDs.
- [ ] Disable autocommit or confirm your tool's transaction mode.
- [ ] Create lab data and COMMIT initial state.
- [ ] Record which statement runs in A and which runs in B.
- [ ] Do not COMMIT early in the lock-holding session before observing.
- [ ] Distinguish consistent-read SELECT from SELECT FOR UPDATE.
- [ ] Verify whether B sees uncommitted data.
- [ ] Test nonrepeatable reads and phantoms under READ COMMITTED.
- [ ] Test NOWAIT, WAIT, and SKIP LOCKED on different rows.
- [ ] Reproduce a lost update and compare version-based locking with SELECT FOR UPDATE.
- [ ] Start SERIALIZABLE/READ ONLY before the first SQL statement of the transaction.
- [ ] Observe ORA-08177, ORA-00054, ORA-30006, or ORA-00060 when conditions are reproduced.
- [ ] Use V$SESSION/V$LOCK to locate the blocker if privileged.
- [ ] Roll back/commit both sessions after each exercise.
- [ ] Clean up lab tables only after all transactions have ended.

## 17. Core takeaways

- Verifying concurrency requires two independent sessions; two worksheets sharing one connection do not create two independent transactions.
- Oracle READ COMMITTED creates statement-level snapshots: no dirty reads, yet nonrepeatable reads and phantoms can occur between SELECTs.
- Regular SELECT uses undo to read consistent versions and generally does not wait on a writer's row lock.
- Two writers modifying the same row must serialize; the second session may wait until the first transaction runs COMMIT/ROLLBACK.
- SELECT FOR UPDATE locks rows for read-modify-write; NOWAIT, WAIT, and SKIP LOCKED control how locked rows are handled.
- Lost updates can occur when a client writes an absolute value calculated from a stale read; use relative updates, SELECT FOR UPDATE, or optimistic versioning.
- SERIALIZABLE and READ ONLY provide transaction-level snapshots per their own semantics; SERIALIZABLE can raise ORA-08177 on write conflicts.
- A deadlock is a resource wait cycle; ORA-00060 usually rolls back the deadlocking statement rather than automatically rolling back the entire transaction.
- TX enqueues typically relate to transaction/row contention; TM enqueues relate to table-level DML locks. Identify the true blocker and object before acting.
- Short transactions, consistent locking order, bounded retries, and idempotency make concurrent applications safer.

### Oracle documentation to consult

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, data concurrency and consistency, locking, and multiversion read consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SET TRANSACTION, SELECT FOR UPDATE, NOWAIT, WAIT, and SKIP LOCKED.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing data concurrency, locks, and transaction management.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — V$SESSION, V$LOCK, V$LOCKED_OBJECT, and dynamic performance views.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — ORA-00054, ORA-00060, ORA-08177, and ORA-30006.

Exact lock modes, wait events, and errors can depend on version, configuration, and operation type. Execute step-by-step in a lab schema, keep transactions open at the right moments, and record SID/event/blocker so outcomes are reproducible.
