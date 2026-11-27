# Blocking Sessions, Wait Chains, and Tracing Blocking Transactions

In Oracle Database, a transaction can hold locks on uncommitted data rows. When another session needs to modify or lock that same row, the second session must wait for the lock-holding transaction to finish. The session holding the lock is called the **blocking session**; the session that must wait is the **waiting session** or **waiter**.

One waiter can cause multiple other sessions to wait. If the blocker itself is waiting on yet another session, you have a **blocking chain**. During an incident, finding a long-waiting session is only the first step; you must trace back to the root transaction holding the lock, identify the SQL statement and owning application, and then choose a safe way to resolve it.

This lesson covers:

- Distinguishing blocker, waiter, blocking chain, and deadlock.
- Using dynamic performance views V$SESSION/GV$SESSION to find waiting sessions and the sessions blocking them.
- Using GV$LOCK, GV$LOCKED_OBJECT, and GV$TRANSACTION to inspect locks, objects, and transactions.
- Tracing SQL, module, client, and the specific row being waited on.
- Safe handling, including cases where a session is no longer running SQL yet still holds an uncommitted transaction.

Examples focus on Oracle 19c. Monitoring accounts need privileges to read dynamic performance views and related dictionary views; in production, DBAs should grant least-privilege access rather than broad administrative privileges.

## 1. What are a blocker and a waiter?

Oracle uses locking mechanisms to allow multiple transactions to operate concurrently without overwriting each other's incomplete changes.

Example:

1. Session A updates account 101 without running COMMIT or ROLLBACK.
2. Session B also tries to update account 101.
3. B must wait for A to finish its transaction.
4. During that time, A is the blocker and B is the waiter.

~~~text
Session A                                  Session B
---------                                  ---------
UPDATE account 101
  (holds row lock)
                                           UPDATE account 101
                                             |
                                             v
                                           WAITING
                                             |
                                             | enq: TX - row lock contention
                                             |
                  A blocks B ---------------+

COMMIT or ROLLBACK
  |
  v
B proceeds
~~~

Oracle row locks are held until the transaction ends. Thus Session A can be INACTIVE (not running any SQL statement at the moment of observation) and still be a blocker if its transaction has not committed or rolled back. This happens frequently when an application opens a transaction, updates data, and waits too long for user interaction.

### 1.1. A blocker is not necessarily a long-running query

Common cases:

- A session updates rows and forgets to commit.
- A session executes SELECT ... FOR UPDATE and then leaves the transaction open.
- An application keeps a transaction open while calling an external service or waiting for user input.
- A batch processes many rows in an overly long single transaction.
- DDL or LOCK TABLE waits for or holds locks incompatible with other DML.

Therefore, filtering only for ACTIVE sessions or long-running SQL will miss many important blockers. Inspect transaction state and blocking relationships.

### 1.2. Blocking chain

A wait chain can look like:

~~~text
Session A (root blocker)
      |
      +---- blocks B
                 |
                 +---- B blocks C
                              |
                              +---- blocks D
~~~

Resolving only D might let D finish while C and B remain blocked. You must identify the root blocker (the session at the head of the chain) and all waiters depending on it.

### 1.3. Blocking does not mean deadlock

**Blocking** is one session waiting for a resource held by another session; when the blocker completes its transaction, the waiter can proceed.

**Deadlock** is a wait cycle: transaction A waits for a resource held by B while B simultaneously waits for a resource held by A (or a multi-session cycle). Oracle detects deadlocks and typically raises ORA-00060: deadlock detected while waiting for resource, while writing diagnostic details to a trace file. It is not merely one session waiting a long time.

## 2. Creating a blocking scenario in the lab

We use two sessions connected to the same schema to observe row locking. Practice only in a lab schema you own.

### 2.1. Create the table

~~~sql
CREATE TABLE lab_lock_accounts (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL,
    note       VARCHAR2(100)
);

INSERT INTO lab_lock_accounts VALUES (101, 1000, 'Account A');
INSERT INTO lab_lock_accounts VALUES (102, 2000, 'Account B');
COMMIT;
~~~

### 2.2. Session A: update without committing

Open the first connection:

~~~sql
UPDATE lab_lock_accounts
SET balance = balance - 100
WHERE account_id = 101;
~~~

Do not run COMMIT or ROLLBACK immediately. Session A has modified row 101 and holds the transaction lock.

### 2.3. Session B: update the same row

Open the second connection:

~~~sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 101;
~~~

Session B's statement will wait for Session A to finish its transaction. Depending on the client tool, the SQL window status may appear as executing or waiting.

### 2.4. Release the waiter

Switch back to Session A and run either:

~~~sql
COMMIT;
~~~

or:

~~~sql
ROLLBACK;
~~~

After A ends its transaction, B can continue. If A ran COMMIT, A's change is persisted before B updates. If A ran ROLLBACK, A's change is undone and B proceeds on the rolled-back data.

Do not run both commands in the same trial. Record your choice and observe the result in Session B.

## 3. Finding waiters and blockers with V$SESSION

V$SESSION contains information about sessions in the current instance. On a single-instance database, you can use V$SESSION; on Oracle RAC, use GV$SESSION to inspect all instances.

### 3.1. Querying blocked sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    state,
    seconds_in_wait,
    sql_id,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    final_blocking_instance,
    final_blocking_session
FROM v$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
~~~

Key columns:

| Column | Meaning |
| --- | --- |
| SID, SERIAL# | Session identifier within the instance; both are required when acting on a session |
| USERNAME | Database user of the session |
| STATUS | ACTIVE or INACTIVE at the time of observation |
| EVENT, WAIT_CLASS | The wait event and wait class the session is experiencing |
| STATE | Wait state, such as WAITING |
| SECONDS_IN_WAIT | Duration of the current wait when the session is in a waiting state |
| SQL_ID | Current SQL of the session if any |
| BLOCKING_SESSION_STATUS | Validity status of blocker information |
| BLOCKING_SESSION | SID of the immediate blocker when status is VALID |
| FINAL_BLOCKING_SESSION | SID of the root blocker at the end of the chain if Oracle identified it |

Only treat BLOCKING_SESSION as valid when BLOCKING_SESSION_STATUS = 'VALID'. Other statuses may indicate there is no holder, the session is no longer waiting, or Oracle has not determined a blocker.

SECONDS_IN_WAIT helps rank waiting sessions, but does not by itself prove root cause or business impact. Combine event, SQL, transaction, and number of dependent sessions.

### 3.2. Viewing waiters alongside blocker sessions

The following query joins waiters to their immediate blocking session:

~~~sql
SELECT
    w.sid                 AS waiter_sid,
    w.serial#             AS waiter_serial,
    w.username            AS waiter_user,
    w.status              AS waiter_status,
    w.event,
    w.wait_class,
    w.seconds_in_wait,
    w.sql_id              AS waiter_sql_id,
    w.blocking_session    AS blocker_sid,
    b.serial#             AS blocker_serial,
    b.username            AS blocker_user,
    b.status              AS blocker_status,
    b.sql_id              AS blocker_sql_id,
    b.prev_sql_id         AS blocker_prev_sql_id,
    b.module,
    b.action,
    b.machine,
    b.program,
    b.logon_time
FROM v$session w
LEFT JOIN v$session b
  ON b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
~~~

The output reveals which session is waiting, which session directly holds the lock, the wait event and wait duration, the blocker's current/previous SQL ID, plus module/action/machine/program to trace the owning application.

If BLOCKER_STATUS = 'INACTIVE', you must still check transactions. The session is not currently executing SQL, yet may hold locks from earlier uncommitted DML.

### 3.3. Using GV$SESSION in Oracle RAC

In RAC, SID is only unique within an instance. Never join waiters and blockers by SID alone, because two instances can have sessions with the same SID.

~~~sql
SELECT
    w.inst_id              AS waiter_inst_id,
    w.sid                  AS waiter_sid,
    w.serial#              AS waiter_serial,
    w.username             AS waiter_user,
    w.status               AS waiter_status,
    w.event,
    w.wait_class,
    w.seconds_in_wait,
    w.sql_id               AS waiter_sql_id,
    w.blocking_instance    AS blocker_inst_id,
    w.blocking_session     AS blocker_sid,
    b.serial#              AS blocker_serial,
    b.username             AS blocker_user,
    b.status               AS blocker_status,
    b.sql_id               AS blocker_sql_id,
    b.prev_sql_id          AS blocker_prev_sql_id,
    b.module,
    b.action,
    b.machine,
    b.program
FROM gv$session w
LEFT JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
~~~

BLOCKING_INSTANCE is the instance hosting the blocker. The join condition must match both INST_ID and SID. In RAC, GV$ views include the INST_ID column; use them to avoid confusing sessions across instances.

## 4. Tracing the root blocker and wait chains

BLOCKING_SESSION identifies the immediate blocker. If that blocker is itself waiting, you would follow its own BLOCKING_SESSION. Oracle provides FINAL_BLOCKING_SESSION and FINAL_BLOCKING_INSTANCE to identify the final blocker in the chain when determined.

### 4.1. Grouping waiters by final blocker

~~~sql
SELECT
    final_blocking_instance,
    final_blocking_session,
    COUNT(*) AS waiting_sessions,
    MAX(seconds_in_wait) AS longest_wait_seconds
FROM gv$session
WHERE blocking_session_status = 'VALID'
  AND final_blocking_session_status = 'VALID'
GROUP BY
    final_blocking_instance,
    final_blocking_session
ORDER BY waiting_sessions DESC, longest_wait_seconds DESC;
~~~

A final blocker with many waiters is usually the top priority to investigate first. The waiter count reflects sessions waiting directly or indirectly attributed to that final blocker based on information Oracle has at query time.

### 4.2. Tracking a specific blocker

Once you have INST_ID, SID, and SERIAL# of the blocker, find all waiters pointing to that session:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    status,
    event,
    seconds_in_wait,
    sql_id,
    blocking_session_status
FROM gv$session
WHERE blocking_session_status = 'VALID'
  AND blocking_instance = :blocker_inst_id
  AND blocking_session = :blocker_sid
ORDER BY seconds_in_wait DESC;
~~~

Bind blocker_inst_id and blocker_sid from monitoring results. This helps when a single session is blocking many transactions simultaneously.

## 5. Understanding TX and TM enqueues

Oracle exposes many enqueue wait events. Two common types when investigating DML blocking are TX and TM.

### 5.1. TX — transaction enqueue

TX is an enqueue tied to a transaction. A transaction typically holds a TX enqueue in exclusive mode while it has uncommitted changes.

Common wait events:

| Event | Initial Interpretation |
| --- | --- |
| enq: TX - row lock contention | Session waiting for another transaction to finish to access a locked row |
| enq: TX - allocate ITL entry | Possible shortage of available transaction slots (ITL) in a data block |
| enq: TX - index contention | May involve index/structure contention; inspect further wait and segment details |

Do not assume every wait starting with enq: TX is the same row-lock issue. Read the exact EVENT, inspect the object/SQL, and identify the contended resource.

### 5.2. TM — table enqueue

TM is an enqueue on a table object used to coordinate DML operations and table-locking operations. Regular DML typically acquires a table lock in Row Exclusive mode (mode 3), which is compatible with other regular DML on the same table.

enq: TM - contention can relate to:

- LOCK TABLE or an operation requesting a stronger table lock.
- DDL waiting for an object lock.
- Unindexed foreign key designs during parent key updates/deletes.
- Other DML/DDL operations contending on lock modes for the same table.

Do not conclude from TM alone that the entire table is exclusively locked. Inspect LMODE, REQUEST, object, and related SQL.

### 5.3. Viewing TX/TM enqueues

~~~sql
SELECT
    inst_id,
    sid,
    type,
    id1,
    id2,
    lmode,
    request,
    ctime,
    block
FROM gv$lock
WHERE type IN ('TX', 'TM')
  AND (request > 0 OR block > 0)
ORDER BY type, id1, id2, request DESC;
~~~

Columns:

- TYPE: enqueue type, such as TX or TM.
- ID1, ID2: enqueue resource identifiers; meaning depends on lock type.
- LMODE: mode currently held by the session.
- REQUEST: mode requested by the session; a value greater than 0 indicates waiting.
- CTIME: time spent in the current mode.
- BLOCK: indicates whether the lock is blocking another session; in RAC, values may indicate blocking across instances.

### 5.4. Lock mode lookup table

| Value | Mode Name |
| ---: | --- |
| 0 | None |
| 1 | Null |
| 2 | Row-S (SS) |
| 3 | Row-X (SX) |
| 4 | Share |
| 5 | S/Row-X (SSX) |
| 6 | Exclusive |

These modes represent how Oracle expresses lock levels; whether two locks conflict depends on the compatibility matrix of that enqueue type. Do not assume a session is a blocker merely because LMODE is greater than 0.

## 6. Identifying the locked object

GV$LOCKED_OBJECT identifies objects currently locked at the object level by transactions. Join with session views and DBA_OBJECTS to find owner, table, and partition/subobject.

~~~sql
SELECT
    lo.inst_id,
    lo.session_id AS sid,
    s.serial#,
    s.username,
    o.owner,
    o.object_name,
    o.subobject_name,
    lo.object_id,
    lo.locked_mode,
    s.status,
    s.module,
    s.action
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
LEFT JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id, o.owner, o.object_name;
~~~

LOCKED_MODE uses the mode values in section 5.4. GV$LOCKED_OBJECT identifies objects locked by a transaction, but **does not directly provide individual row ROWIDs**. To find a specific row, combine with the waiter's ROW_WAIT_* columns when valid.

### 6.1. Do not confuse TX ID1 with OBJECT_ID

In GV$LOCK, ID1/ID2 carry meanings specific to the enqueue type. For TX, they identify a transaction resource; never treat TX.ID1 as OBJECT_ID to join directly to DBA_OBJECTS.

For TM, ID1 generally corresponds to the object ID of the locked table. However, when you want object names and DML lock modes, GV$LOCKED_OBJECT is usually easier to read. Always check TYPE before interpreting ID1/ID2.

## 7. Tracing the row waited on by the waiter

V$SESSION includes columns ROW_WAIT_OBJ#, ROW_WAIT_FILE#, ROW_WAIT_BLOCK#, and ROW_WAIT_ROW#. These values are useful when a session is waiting for another transaction to commit and Oracle has identified the relevant row. They are not valid for every wait type; ROW_WAIT_OBJ# = -1 generally indicates no usable row-wait information is available.

### 7.1. Viewing the waited-on object and ROWID

~~~sql
SELECT
    w.inst_id,
    w.sid AS waiter_sid,
    w.serial# AS waiter_serial,
    w.event,
    w.seconds_in_wait,
    w.row_wait_obj#,
    o.owner,
    o.object_name,
    o.subobject_name,
    CASE
        WHEN w.row_wait_obj# <> -1 THEN
            DBMS_ROWID.ROWID_CREATE(
                1,
                w.row_wait_obj#,
                w.row_wait_file#,
                w.row_wait_block#,
                w.row_wait_row#
            )
    END AS waiting_rowid
FROM gv$session w
LEFT JOIN dba_objects o
  ON o.data_object_id = w.row_wait_obj#
WHERE w.blocking_session_status = 'VALID'
  AND w.row_wait_obj# <> -1
ORDER BY w.seconds_in_wait DESC;
~~~

ROWID_CREATE constructs a ROWID from the object/file/block/row of the waited-on location. Verify OWNER, OBJECT_NAME, SUBOBJECT_NAME, and ROWID against the actual table before concluding. For partitioned tables, DATA_OBJECT_ID identifies the corresponding segment/subobject.

Only use ROW_WAIT_* columns when the waiter is genuinely in a wait type where Oracle populates row information. If the values are invalid, investigate via object locks, SQL, and transactions; do not construct ROWIDs from default values.

### 7.2. Inspecting the row after identifying the table

For example, if the query shows the row belongs to APP.ORDERS, you can use the resulting ROWID to read that exact row:

~~~sql
SELECT *
FROM app.orders
WHERE ROWID = CHARTOROWID(:waiting_rowid);
~~~

This is a read operation for diagnostics. Never automatically update or delete a waited-on row simply because you found its ROWID.

## 8. Tracing the lock-holding transaction

A session may not be executing SQL at the moment of observation yet still have an open transaction. V$TRANSACTION/GV$TRANSACTION contains information about active transactions.

### 8.1. Joining session to transaction

~~~sql
SELECT
    b.inst_id,
    b.sid,
    b.serial#,
    b.username,
    b.status,
    b.module,
    b.action,
    b.machine,
    b.program,
    t.start_time,
    t.xidusn,
    t.xidslot,
    t.xidsqn,
    t.used_ublk,
    t.used_urec
FROM gv$session b
JOIN gv$transaction t
  ON t.inst_id = b.inst_id
 AND t.addr = b.taddr
WHERE EXISTS (
    SELECT 1
    FROM gv$session w
    WHERE w.blocking_session_status = 'VALID'
      AND w.blocking_instance = b.inst_id
      AND w.blocking_session = b.sid
)
ORDER BY t.start_time;
~~~

Explanation:

- TADDR in the session points to the transaction state object.
- ADDR in transaction joins to TADDR within the same instance.
- START_TIME shows when the transaction began in Oracle's display format.
- USED_UBLK and USED_UREC reflect undo blocks/records consumed, helping estimate the scale of changes that would roll back if the transaction is aborted.

USED_UBLK/USED_UREC are not an exact countdown of remaining rollback time. Large transactions can take substantial cleanup time; do not use a single number to promise when locks will clear.

### 8.2. Finding a specific session's transaction

~~~sql
SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.username,
    s.status,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.addr = s.taddr
WHERE s.inst_id = :inst_id
  AND s.sid = :sid;
~~~

Substitute binds with the instance and SID from monitoring output. If no rows return, the session may have ended its transaction while you were investigating or has no active transaction.

## 9. Finding the SQL and application behind the blocker

### 9.1. Current and previous SQL_ID

In V$SESSION:

- SQL_ID is the session's current SQL if executing.
- PREV_SQL_ID is the previous SQL.

An INACTIVE blocker usually has no currently running SQL; PREV_SQL_ID is a clue to the most recent statement. However, it is not absolute proof of the SQL that acquired the lock: the session may have run a subsequent SELECT or another SQL statement after the lock-acquiring DML.

### 9.2. Retrieving SQL text

~~~sql
SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.status,
    s.sql_id,
    s.prev_sql_id,
    q.sql_text
FROM gv$session s
LEFT JOIN gv$sqlarea q
  ON q.inst_id = s.inst_id
 AND q.sql_id = COALESCE(s.sql_id, s.prev_sql_id)
WHERE s.inst_id = :blocker_inst_id
  AND s.sid = :blocker_sid;
~~~

GV$SQLAREA stores parsed SQL metadata in the shared pool. If the SQL has aged out, the query may no longer return text. If the session is currently executing different SQL, the retrieved text may also not be the statement that opened the transaction.

### 9.3. Identifying module, action, and client

The MODULE, ACTION, CLIENT_IDENTIFIER, MACHINE, and PROGRAM fields in GV$SESSION help tie a session to an application, request, or job. Applications should proactively set context:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'UpdateOrder'
    );
    DBMS_SESSION.SET_IDENTIFIER('request-2026-000123');
END;
/
~~~

When returning a connection to a pool, the application should reset module/action/client identifier so the next request does not inherit stale metadata. DBAs can query:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    module,
    action,
    client_identifier,
    machine,
    program,
    status
FROM gv$session
WHERE inst_id = :inst_id
  AND sid = :sid;
~~~

If module/action/client identifier are empty, work with the application team to add instrumentation. Never infer the exact endpoint or end user solely from MACHINE/PROGRAM.

### 9.4. SQL history and ASH

GV$SQL/GV$SQLAREA only retain SQL still in the shared pool. If historical activity is needed, DBAs may look at AWR/ASH or traces, but V$ACTIVE_SESSION_HISTORY, DBA_HIST_ACTIVE_SESS_HISTORY, and AWR reports typically fall under Diagnostics Pack licensing. SQL Monitor and certain tuning reports may fall under the Tuning Pack. Confirm licensing and entitlements in your environment before using these features.

Do not assume every Oracle environment is licensed to query AWR/ASH. Without the required license, rely on current session info, cached SQL still available, application logs, and traces enabled per DBA procedures.

## 10. Distinguishing common blocking root causes

### 10.1. Uncommitted update transaction

Symptoms:

- Waiter has event enq: TX - row lock contention.
- BLOCKING_SESSION_STATUS = 'VALID'.
- Blocker has an active transaction in GV$TRANSACTION.
- Blocker may be INACTIVE.

Investigation direction: identify the application and blocker owner; check when the transaction started and undo size; inspect current/previous SQL, module, and request ID; ask the session-owning team whether it is safe to commit or roll back.

### 10.2. SELECT FOR UPDATE

SELECT ... FOR UPDATE acquires row locks so the application can read and then update consistently. If the application keeps the transaction open after reading, other sessions needing to modify the same row will wait.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE;
~~~

Locks are held until transaction commit or rollback. Do not use FOR UPDATE for normal read-only screens if the application does not need to lock rows.

### 10.3. TM contention and unindexed foreign keys

One scenario to check is a child table with a foreign key whose foreign key column is unindexed. When a session deletes or modifies a key in the parent table, Oracle may need a stronger lock on the child table to protect referential integrity; concurrent DML on the child table can be affected.

When seeing enq: TM - contention, inspect the waited-on object/table, LMODE and REQUEST in GV$LOCK, relevant foreign keys and indexes on FK columns, plus any running DDL or LOCK TABLE.

Not every foreign key requires an index in every system. Indexing decisions depend on DML patterns, integrity requirements, cardinality, and write overhead.

### 10.4. ITL contention

enq: TX - allocate ITL entry can happen when a block has no immediately available transaction slot. This is a different form of contention from two sessions updating the same row. Examine the segment, block, INITRANS, concurrency level, and storage design; do not treat it by merely hunting for a row lock and asking someone to commit.

### 10.5. DDL waiting on DML

DDL requires appropriate object locks. If DML transactions have not finished, DDL operations may wait. Similarly, DDL holding locks can block other DML or DDL. Inspect EVENT, object, and SQL of both sessions before drawing conclusions.

## 11. Deadlocks and ORA-00060

A deadlock is a cycle in the wait graph, not an ordinary long queue.

~~~text
Session A                         Session B
---------                         ---------
UPDATE row 1                      UPDATE row 2
holds row 1 lock                  holds row 2 lock

UPDATE row 2  ----------------->  waiting for row 2
waiting for row 2

                                  UPDATE row 1
                                  waiting for row 1

          A waits for B; B waits for A
                 |
                 v
          DEADLOCK CYCLE
~~~

Oracle detects the cycle and reports ORA-00060 to one statement in the cycle, while writing deadlock details to a trace file. Typically, the deadlocking statement is rolled back; the session's transaction is not necessarily rolled back in full. The application must handle the error and decide whether to roll back/retry the transaction per design.

### 11.1. Ways to reduce deadlocks

- Transactions should lock multiple rows in the same consistent order, such as ascending primary key.
- Keep transactions short.
- Avoid holding locks while calling external services or waiting for users.
- Update only the needed row scope; proper indexes reduce the amount of data touched.
- Handle ORA-00060 with bounded retries and backoff when business logic permits.

Do not treat every ORA-00060 as an error to retry infinitely. If the locking order always produces a cycle, retries just repeat the incident.

## 12. Safely handling a blocker

Once the root blocker is identified, coordinate with the application/transaction owner. Priority order:

1. **Confirm impact:** how many waiters, which tables, and which business transactions are affected.
2. **Identify owner:** module, action, client identifier, machine, program, and application on-call owner.
3. **Inspect transaction state:** start time, undo used, most recent SQL, and session status.
4. **Have the session end its transaction per business rules:** commit if changes should be saved; roll back if changes should be undone.
5. **Terminate only with authorization after assessing impact:** e.g., abandoned session or application unable to release itself.

Do not run COMMIT or ROLLBACK in your monitoring session expecting it to end the blocker's transaction. Each transaction belongs to its own session.

### 12.1. Terminating a session on a single instance

After confirming the exact session and obtaining operational approval:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
~~~

Replace sid and serial# with the verified values. Requires ALTER SYSTEM privilege.

### 12.2. Terminating a session in RAC

In RAC, specify the instance:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
~~~

Never use SID alone to decide which session to kill; cross-check INST_ID, SID, SERIAL#, username, and application metadata.

### 12.3. KILL SESSION does not mean instant rollback completion

After the kill command:

- Oracle marks the session for termination.
- Uncommitted transactions must be rolled back.
- If the transaction is large, cleanup can take time.
- The session may temporarily show status KILLED during cleanup.
- Locks are released as rollback/cleanup progresses, not necessarily the instant ALTER SYSTEM returns.

Monitor waiters, blockers, transactions, and alert/trace logs per DBA procedures. Do not repeatedly reissue kill commands just because the session has not vanished immediately from views.

## 13. Preventing blocking in applications

### 13.1. Keep transactions short

~~~text
BEGIN TRANSACTION
  Read required data
  Validate
  Perform DML
COMMIT

Only after commit:
  Call external service
  Wait for user
  Render response
~~~

Exact design depends on business requirements, but avoid holding row locks while making HTTP calls, sending emails, waiting for user input, or performing non-transactional work.

### 13.2. Use WAIT/NOWAIT/SKIP LOCKED appropriately

Oracle supports clauses for SELECT ... FOR UPDATE:

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;
~~~

NOWAIT returns an error immediately if the row is locked, fitting cases where the app wants to report "currently in use" rather than wait.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE WAIT 5;
~~~

WAIT 5 waits up to the specified time before returning a timeout error if the lock still cannot be acquired.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id IN (101, 102)
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED skips rows locked by other sessions. It is useful for worker-queue models where a worker can process unclaimed rows. Do not use it indiscriminately where business rules require every matching row to be processed; skipping rows can alter business outcomes.

### 13.3. Designing a queue with SKIP LOCKED

A worker can claim a batch of jobs not locked by other workers:

~~~sql
SELECT job_id, payload
FROM lab_job_queue
WHERE status = 'READY'
ORDER BY created_at, job_id
FOR UPDATE SKIP LOCKED;
~~~

After claiming work, the worker updates status and commits in a short transaction. Add lease/retry/visibility-timeout mechanisms in case a worker dies after locking or claiming work. SKIP LOCKED does not by itself provide full message-queue semantics.

If each worker should only claim a limited number of jobs, use a cursor and fetch only the number of rows to process; do not fetch the entire READY set. With SELECT FOR UPDATE, rows are locked as fetched, so fetch batch size is part of queue design. Close the cursor and commit/roll back per the job-processing workflow.

### 13.4. Lock multiple rows in a consistent order

If two transactions must update the same set of accounts, lock in the same order:

~~~sql
SELECT account_id
FROM lab_lock_accounts
WHERE account_id IN (101, 102)
ORDER BY account_id
FOR UPDATE;
~~~

Locking in a consistent order reduces the chance that transaction A locks 101 then waits for 102 while transaction B locks 102 then waits for 101. Inspect execution plans and actual query patterns; desired logical ordering must be explicitly designed.

### 13.5. Instrument sessions

Applications should set MODULE, ACTION, and CLIENT_IDENTIFIER. These fields help DBAs correlate database sessions with application logs. Never place secrets or unnecessary personal data in these fields.

## 14. Blocking incident investigation checklist

| Step | Question to Answer | Information Source |
| --- | --- | --- |
| 1 | Who is waiting? | GV$SESSION waiter, event, wait time |
| 2 | Who is directly blocking? | BLOCKING_INSTANCE, BLOCKING_SESSION |
| 3 | Who is the root blocker? | FINAL_BLOCKING_INSTANCE, FINAL_BLOCKING_SESSION |
| 4 | How many sessions are affected? | Group waiters by final blocker |
| 5 | What resource type? | EVENT, GV$LOCK TX/TM |
| 6 | Which table/partition is involved? | GV$LOCKED_OBJECT, DBA_OBJECTS |
| 7 | Which row is being waited on? | ROW_WAIT_* when valid |
| 8 | When did the transaction start? | GV$TRANSACTION |
| 9 | Which SQL and application? | SQL_ID, PREV_SQL_ID, GV$SQLAREA, module/action |
| 10 | Can it be safely released? | Confirm with transaction owner and operational procedures |

Record timestamps, instance, SID, serial, event, blocker, SQL ID, module, and batch/request ID. A blocking incident can vanish before the second query runs; timestamped snapshots help correlate logs and reconstruct events.

## 15. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Filtering only ACTIVE sessions misses blockers | Blocker may be INACTIVE with an uncommitted transaction | Find waiters via BLOCKING_SESSION_STATUS, then check transactions |
| Joining SID in RAC without INST_ID | SIDs can overlap across instances | Use GV$SESSION and join both instance + SID |
| Confusing waiter and blocker | Looking only at sessions with wait events | Use blocking session columns to trace direction |
| Seeing TX and concluding row lock | TX also covers ITL/index/unique-related waits | Read exact wait event and object |
| Seeing TM and concluding whole table is exclusively locked | TM modes vary and have compatibility rules | Check LMODE, REQUEST, object, and SQL |
| Joining TX ID1 to DBA_OBJECTS.OBJECT_ID | TX ID1 is not an object ID | Use TYPE to interpret ID1/ID2; check GV$LOCKED_OBJECT |
| Cannot see blocker's SQL | Session is idle or SQL aged out | Check PREV_SQL_ID, cached SQLAREA, module/action, and application logs |
| Assuming PREV_SQL_ID is definitely the lock-acquiring DML | Session may have run other SQL after the DML | Treat as a clue and cross-check transaction/application traces |
| ROW_WAIT_* has no useful value | Not all waits populate row location | Use only when row_wait_obj# is valid and wait type matches |
| Killed blocker yet waiter still waits | Transaction rollback/cleanup not yet complete | Monitor cleanup progress; do not repeatedly kill |
| Treating blocking as deadlock | One-way waiting is not a cycle | Deadlocks are wait cycles; check ORA-00060 and traces |
| Using SKIP LOCKED for complete reports | Locked rows are omitted | Use only when business logic permits workers to skip busy rows |
| Infinite retries after ORA-00060 | Lock order still produces a cycle | Standardize lock order and bound retries/backoff |

## 16. Practice exercises

Use LAB_LOCK_ACCOUNTS from section 2 and two separate connections.

### Exercise 1 — Create a row lock

In Session A, update account 101 without committing. In Session B, update the same account. Record which session is the blocker, which is the waiter, and the waiter's event.

### Exercise 2 — Compare INACTIVE status and open transaction

After Session A runs UPDATE, leave Session A idle without running SQL and without committing. From a third session, query V$SESSION and V$TRANSACTION. Explain why an INACTIVE session can still hold locks.

### Exercise 3 — Inspect waiters and blockers

Run the query in section 3.2. Record SID, SERIAL#, SQL_ID, PREV_SQL_ID, MODULE, and MACHINE of both sessions.

### Exercise 4 — Observe the transaction

Use GV$TRANSACTION to view START_TIME, USED_UBLK, and USED_UREC of the blocker. Commit or roll back in Session A, then re-run the query to observe the transaction disappearing and the waiter proceeding.

### Exercise 5 — Inspect lock modes

Query GV$LOCK for TX/TM. Identify the session requesting a lock and the session holding a lock. Compare modes with the lookup table in this lesson.

### Exercise 6 — Inspect object and row wait

Use GV$LOCKED_OBJECT to identify the locked table. While the waiter is on enq: TX - row lock contention, check ROW_WAIT_* and construct the ROWID if columns are valid. Read the row by ROWID.

### Exercise 7 — Test SELECT FOR UPDATE

Session A runs SELECT ... FOR UPDATE on account 102. Session B tries FOR UPDATE NOWAIT, then tries WAIT 5. Record differences in timing and outcome.

### Exercise 8 — Design a worker queue

Suppose there is a job queue table with READY status. Write a query to claim some jobs using FOR UPDATE SKIP LOCKED. Explain why two workers can receive different rows and what must be handled if one worker stops mid-way.

## 17. Lab cleanup

Run only in the lab schema you created, after both sessions have committed/rolled back and no longer hold locks:

~~~sql
DROP TABLE lab_lock_accounts PURGE;
~~~

If the table is in use by another session or has an open transaction, end the transaction before dropping. PURGE bypasses the recycle bin; never use on business tables or data needing recovery.

## Summary

Blocking occurs when a session must wait for a resource held by another transaction. V$SESSION/GV$SESSION reveal waiters, immediate blockers, and final blockers; GV$LOCK describes enqueues/modes; GV$LOCKED_OBJECT identifies locked objects; GV$TRANSACTION shows open transactions; ROW_WAIT_* can pinpoint specific rows when Oracle provides the wait location.

A blocker can be INACTIVE yet still hold locks because its transaction has not committed or rolled back. Tracing root cause requires combining wait events, session identity, transactions, SQL IDs, module/action, and application logs. In RAC, always join on both INST_ID and SID. Distinguish one-way blocking from ORA-00060 deadlocks, and terminate sessions only after confirming the owner and rollback impact. The most effective prevention is short transactions, consistent locking order, proper indexes, appropriate use of NOWAIT/WAIT/SKIP LOCKED, and application instrumentation to identify blocking requests.

## Oracle Reference Documentation

- [Oracle Database Reference — V$SESSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html) — session state, wait events, blocking session, and row-wait columns.
- [Oracle Database Reference — V$LOCK (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html) — enqueues, lock modes, request, and blocking flags.
- [Oracle Database Reference — V$LOCKED_OBJECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html) — transaction object locks.
- [Oracle Database Reference — V$TRANSACTION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html) — transaction state and undo usage.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — FOR UPDATE, NOWAIT, WAIT, and SKIP LOCKED.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — tagging sessions with module and action.

When deploying on an Oracle release other than 19c or on RAC, consult the Reference documentation for that exact version, especially blocking/final-blocking columns, wait events, and session administration syntax.
