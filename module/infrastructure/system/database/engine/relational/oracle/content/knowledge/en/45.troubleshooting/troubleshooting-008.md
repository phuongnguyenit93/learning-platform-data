# ORA-00054, ORA-00060, and Distinguishing Lock Waits from Deadlocks

In Oracle Database, multiple sessions can read and modify data concurrently. The database uses locks to protect consistency while a transaction modifies rows or objects. Therefore, waiting on a lock is normal behavior. Problems arise when an application demands an immediate lock on a busy resource, wait times exceed thresholds, or multiple transactions wait on one another in a circular dependency.

Two common errors:

- **ORA-00054 — resource busy:** a session could not acquire a lock in `NOWAIT` mode or within the configured wait timeout. Commonly seen when running DDL on an object currently in use by another transaction, or when a statement requests a lock without waiting.
- **ORA-00060 — deadlock detected:** Oracle detected a cycle of lock waits among transactions. No transaction in the cycle can proceed unless one operation is aborted, so Oracle chooses a statement to roll back and returns an error.

The core distinction is: **a normal lock wait has one party holding a lock and another waiting; a deadlock has a closed cycle of waits among multiple transactions**. ORA-00054 usually indicates a lock request could not wait further under current policy. ORA-00060 indicates Oracle detected a cycle and broke it by rolling back one statement.

## 1. What Are Locks Used for in Oracle?

Locks coordinate concurrent access. When a transaction modifies a row, Oracle holds a row lock so other transactions cannot overwrite uncommitted changes in a way that breaks consistency. Locks are typically held until the transaction issues `COMMIT` or `ROLLBACK`.

Example:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
```

After this statement, the transaction holds a lock on the updated account row. If another session tries to update the same row, it must wait for the first transaction to finish or receive an error if the statement specifies `NOWAIT`/timeout.

### 1.1. Oracle Does Not Lock the Entire Table for Every UPDATE

Oracle typically uses row-level locking for DML. When a session updates several rows, those rows are locked to protect the changes. A DML statement also acquires a table lock in an appropriate mode to coordinate with DDL and other DML, but that does not mean the entire table is exclusively locked.

Ordinary `SELECT` queries use read consistency and normally do not wait on row locks held by updating transactions. A session can read a consistent snapshot of the data prior to the other transaction's commit. Conversely, `SELECT ... FOR UPDATE` requests locks on rows in preparation for updating them and may wait.

### 1.2. Transactions Hold Locks Until Completion

Normally, row locks are held until `COMMIT` or `ROLLBACK`. If an application starts a transaction, updates a row, and then waits for user input or calls an HTTP service before committing, locks are held far longer than necessary.

Long-running transactions increase:

- The number of sessions waiting on the same row or object.
- Lock hold duration and contention probability.
- Deadlock likelihood when transactions access multiple resources in different orders.
- Amount of undo retained and rollback duration upon failure.
- Number of connections held in the connection pool.

Keep transactions short, perform the required database operations, and commit or roll back promptly. Never keep a transaction open while waiting on user interaction or slow network calls.

## 2. Common Lock Types

Oracle uses several types of locks. When investigating ORA-00054 or ORA-00060, identify whether the contested resource is a row, table, DDL object, or another resource type.

### 2.1. TX Enqueue — Transaction/Row Lock

`TX` is a transaction-related enqueue. A typical scenario is Session A modifying a row without committing while Session B tries to modify the same row and must wait for Transaction A to end.

Common wait event:

```text
enq: TX - row lock contention
```

This wait event indicates the session is waiting on a transaction holding a row-related lock. It does not automatically mean a deadlock. Once the blocker commits or rolls back, the waiter can proceed.

### 2.2. TM Enqueue — Table-Level DML Lock

`TM` is a table-level enqueue used to coordinate DML operations and certain DDL operations. Normal DML acquires table locks in modes compatible with other DML. Operations such as altering table structure or dropping a table require stronger locks and can be blocked.

Possible wait event:

```text
enq: TM - contention
```

`TM` contention can relate to DDL, foreign keys, table operations, or incompatible lock modes. Inspect the specific object and SQL before concluding the cause.

### 2.3. DDL Locks and Object/Library Cache Locks

DDL must protect object definitions while modifying them. If a session is actively using an object or holds an incompatible lock, statements such as `ALTER TABLE`, `DROP TABLE`, or `TRUNCATE TABLE` may have to wait.

Waits related to object metadata or PL/SQL include `library cache lock`, `library cache pin`, and `row cache lock`. These differ from ordinary row locks; analyze them by object, dependencies, and running statements.

### 2.4. Lock Modes

Common lock modes shown in `V$LOCK`:

| `LMODE` / `REQUEST` Value | Mode Name | General Meaning |
|---:|---|---|
| 0 | None | Neither holding nor requesting a lock |
| 1 | Null | Null mode |
| 2 | Row-S / SS | Row Share / Sub Share |
| 3 | Row-X / SX | Row Exclusive / Sub Exclusive |
| 4 | Share / S | Share |
| 5 | S/Row-X / SSX | Share Row Exclusive |
| 6 | Exclusive / X | Exclusive |

Compatibility depends on resource type and mode. Do not look at `LMODE` alone and conclude a session has locked an entire table. Combine `TYPE`, `ID1`, `ID2`, `REQUEST`, object, and SQL statement.

## 3. ORA-00054: resource busy

Common message:

```text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
```

This error occurs when a statement requires a lock but cannot acquire it under the active wait policy. Another session holds an incompatible lock, or the statement used `NOWAIT`/timeout and the time elapsed.

### 3.1. Example: DDL Blocked by a DML Transaction

Suppose table `ORDERS` is being updated by an application.

**Session A:**

```sql
UPDATE orders
SET order_status = 'PAID'
WHERE order_id = 1001;

-- Not yet committed or rolled back.
```

**Session B:**

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

DDL requires an appropriate lock to alter table metadata. Transaction A holds a table-related lock, preventing Session B's DDL from acquiring its lock. With `DDL_LOCK_TIMEOUT` set to 0, DDL does not wait and immediately returns ORA-00054 when the required lock is busy.

Once Session A commits or rolls back, Session B can re-run the DDL successfully. This is a one-way lock wait: B waits on A; A does not wait on B. There is no deadlock cycle.

### 3.2. NOWAIT in SELECT FOR UPDATE

`SELECT ... FOR UPDATE` locks selected rows so the session can update them safely.

Session A:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 10
FOR UPDATE;
```

Session B:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
```

If Session A still holds the row lock, Session B does not wait and immediately receives a resource busy error. `NOWAIT` is useful when an application wants immediate feedback that a resource is being processed elsewhere.

### 3.3. WAIT n and SKIP LOCKED

Oracle allows controlling wait behavior for `SELECT FOR UPDATE`:

```sql
SELECT order_id, order_status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

The statement waits up to the specified number of seconds for the row lock. Upon timeout, Oracle returns a timeout error appropriate for the statement and release; with `SELECT FOR UPDATE WAIT`, ORA-30006 may occur. Do not assume every lock timeout always returns ORA-00054.

To skip currently locked rows:

```sql
SELECT order_id, order_status
FROM orders
WHERE order_status = 'NEW'
ORDER BY order_id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` is helpful when multiple workers pull jobs from a queue table: a worker can process another row instead of waiting on a row held by another worker. It changes query semantics because locked rows are omitted from the result set. Never use it for business queries that must see every row.

### 3.4. LOCK TABLE with NOWAIT or WAIT

A table lock can be requested explicitly:

```sql
LOCK TABLE orders IN EXCLUSIVE MODE NOWAIT;
```

If the lock mode cannot be acquired immediately, the statement returns an error instead of waiting. You can also specify `WAIT` using supported Oracle syntax:

```sql
LOCK TABLE orders IN EXCLUSIVE MODE WAIT 10;
```

Table locks are generally not the right default for OLTP applications. Locking an entire table or requesting strong modes can severely degrade concurrency.

## 4. DDL_LOCK_TIMEOUT

`DDL_LOCK_TIMEOUT` controls how long DDL waits in the DML lock queue before returning a resource busy error. The default is 0, meaning `NOWAIT` behavior for locks DDL must wait on.

It can be set at the session level:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 30;
```

DDL can then wait up to roughly 30 seconds to acquire the required lock. Example:

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

If the lock-holding transaction finishes within that window, the DDL proceeds. If the timeout expires, DDL still returns ORA-00054.

### 4.1. DDL_LOCK_TIMEOUT Does Not Solve Everything

Increasing the timeout only changes how long DDL waits. It does not:

- Make the blocking transaction commit faster.
- Break a deadlock.
- Guarantee DDL will succeed after the timeout.
- Replace finding the session holding long locks.
- Make DDL online or eliminate workload impact.

If a transaction holds locks for tens of minutes, raising the timeout to an hour just leaves the deployment hanging longer. Find why transactions stay open so long and choose an appropriate deployment window.

### 4.2. Checking DDL_LOCK_TIMEOUT

```sql
SELECT name,
       value,
       isdefault,
       isses_modifiable,
       issys_modifiable
FROM v$parameter
WHERE name = 'ddl_lock_timeout';
```

The value in `V$PARAMETER` reflects the setting effective in the current session. Session-level changes affect only that session. System-wide changes must be evaluated by a DBA per environment policy.

## 5. ORA-00060: deadlock detected

Common message:

```text
ORA-00060: deadlock detected while waiting for resource
```

A deadlock occurs when transactions form a wait cycle. Each transaction holds a resource another needs while waiting for a resource held by another transaction in the cycle. None can proceed to release its locks.

Oracle detects the cycle and rolls back one statement involved in the deadlock to break the wait loop. The remaining transactions can proceed once resources are freed.

### 5.1. Example: Deadlock Between Two Rows

Suppose table `ACCOUNTS` has two rows:

| ACCOUNT_ID | BALANCE |
|---:|---:|
| 10 | 1000 |
| 20 | 1500 |

Two sessions transfer funds in opposite directions.

**Session A:**

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
```

Session A holds the lock on row 10.

**Session B:**

```sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 20;
```

Session B holds the lock on row 20.

Next, Session A attempts to update row 20:

```sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;
```

A must wait on B because B holds row 20.

Session B then attempts to update row 10:

```sql
UPDATE accounts
SET balance = balance + 200
WHERE account_id = 10;
```

B must wait on A because A holds row 10. Now:

```text
Session A holds row 10 ──────> waits for row 20 held by B
        ^                                       |
        |                                       v
Session B waits for row 10 <────── holds row 20
```

The cycle is closed. A cannot proceed until B releases row 20; B cannot proceed until A releases row 10. Oracle detects the deadlock and returns ORA-00060 to one statement chosen for rollback.

### 5.2. Normal Lock Wait vs. Deadlock

When only Session A holds row 10 and Session B waits on row 10:

```text
Session A: holds row 10, processing
Session B: waits for row 10
```

This is a lock wait, not a deadlock. Once A commits or rolls back, B proceeds. There is no reverse wait edge from A to B.

In a deadlock:

```text
A holds resource 1, waits for resource 2 held by B
B holds resource 2, waits for resource 1 held by A
```

The cycle prevents sessions from freeing resources in their current order.

### 5.3. Deadlocks Do Not Always Involve Just Two Sessions

A cycle can span three or more transactions:

```text
T1 holds A, waits for B
T2 holds B, waits for C
T3 holds C, waits for A
```

Oracle detects cycles in the lock graph. Therefore, do not only search for two sessions referencing the same table name; read the deadlock graph and identify all participating resources and sessions.

### 5.4. Statement Rollback Does Not Roll Back the Entire Transaction

When ORA-00060 occurs, Oracle rolls back the statement that triggered the deadlock to break the cycle. Earlier statements in that transaction may remain uncommitted and the transaction stays open.

The application should handle the error by rolling back the current transaction before retrying the entire unit of work if appropriate. Never catch ORA-00060, ignore it, and continue using the transaction as if nothing happened.

## 6. Distinguishing ORA-00054 and ORA-00060

| Criterion | ORA-00054 | ORA-00060 |
|---|---|---|
| Meaning | Could not acquire lock under NOWAIT/timeout | Oracle detected a deadlock wait cycle |
| Wait shape | Usually one session waiting on a resource held by another | Two or more transactions waiting on each other in a cycle |
| Common cause | DDL hitting open DML; `NOWAIT`; lock timeout | Transactions updating multiple rows/objects in different orders |
| Does Oracle detect a cycle? | Not necessarily a cycle | Yes, a cycle in the lock dependency graph |
| First action | Identify blocker, wait or reschedule DDL; adjust timeout if appropriate | Read deadlock trace, inspect lock ordering, fix transaction logic |
| Retry | Can retry after resource is freed or with backoff | Roll back full transaction and retry if idempotent |
| Always need to kill session? | No | No; Oracle already rolled back a statement to break the deadlock |

Do not assume every long lock wait automatically turns into ORA-00060. Without a cycle, a session can wait indefinitely or until a statement timeout expires. A deadlock is a circular dependency, not simply "waiting too long."

## 7. Finding Waiting and Blocking Sessions

When investigating lock contention, identify at minimum:

- Waiter session: the session waiting.
- Blocker session: the session holding the needed resource.
- Current SQL and previous SQL of the blocker.
- Involved object or row if identifiable.
- Wait duration and transaction age.
- Instance hosting each session if running RAC.

### 7.1. View Blocked Sessions via GV$SESSION

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       wait_class,
       state,
       seconds_in_wait,
       sql_id,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session
FROM gv$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
```

`GV$SESSION` aggregates sessions across RAC instances. `V$SESSION` reflects only the current instance. `BLOCKING_SESSION` and `BLOCKING_INSTANCE` show the immediate blocker identified by Oracle; `FINAL_BLOCKING_SESSION` finds the root blocker in a multi-level blocking chain.

Viewing dynamic performance views requires appropriate catalog/monitoring privileges. Never grant `DBA` to an application account solely to run diagnostic queries.

### 7.2. Join Waiters with Blockers

```sql
SELECT w.inst_id           AS waiter_inst_id,
       w.sid               AS waiter_sid,
       w.serial#           AS waiter_serial,
       w.username          AS waiter_user,
       w.event             AS wait_event,
       w.seconds_in_wait,
       w.sql_id            AS waiter_sql_id,
       b.inst_id           AS blocker_inst_id,
       b.sid               AS blocker_sid,
       b.serial#           AS blocker_serial,
       b.username          AS blocker_user,
       b.status            AS blocker_status,
       b.sql_id            AS blocker_sql_id,
       b.prev_sql_id       AS blocker_prev_sql_id
FROM gv$session w
JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
```

The blocker's `SQL_ID` may be the active SQL or `NULL` if the session is idle; `PREV_SQL_ID` often identifies the earlier SQL that acquired the lock. Inspect both alongside transaction age and session state. Never look solely at `STATUS = 'INACTIVE'` and conclude a session holds no locks: an inactive session can still hold an uncommitted transaction.

### 7.3. Inspect Held and Requested Locks

```sql
SELECT inst_id,
       sid,
       type,
       id1,
       id2,
       lmode,
       request,
       ctime,
       block
FROM gv$lock
WHERE request > 0
   OR block <> 0
ORDER BY type, id1, id2, inst_id, sid;
```

Key columns:

- `TYPE`: enqueue/resource type, commonly `TX` and `TM`.
- `ID1`, `ID2`: resource identifiers; meaning depends on `TYPE`.
- `LMODE`: lock mode currently held.
- `REQUEST`: lock mode requested; greater than 0 means waiting on a lock.
- `CTIME`: time in seconds the session has held the current mode.
- `BLOCK`: whether this lock is blocking another session; exact interpretation can vary in RAC.

Do not join `ID1`/`ID2` assuming they are always object IDs. For `TM` locks, `ID1` relates to the object ID; for `TX` locks, they identify a transaction resource differently.

### 7.4. Identify Locked Objects via GV$LOCKED_OBJECT

```sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id, o.owner, o.object_name;
```

This view maps DML locks to objects. It does not list every lock type in Oracle; for example, not every DDL or library cache lock appears as a row in `GV$LOCKED_OBJECT`.

### 7.5. DBA_BLOCKERS and DBA_WAITERS

Oracle provides views such as `DBA_BLOCKERS` and `DBA_WAITERS` to inspect blocker/waiter relationships in certain scopes. In RAC or complex blocking chains, `GV$SESSION` and `GV$LOCK` are more flexible because they include `INST_ID` and detailed session attributes.

### 7.6. View DDL Locks

Held/requested DDL locks can be inspected via `DBA_DDL_LOCKS`:

```sql
SELECT session_id,
       owner,
       name,
       type,
       mode_held,
       mode_requested
FROM dba_ddl_locks
WHERE mode_held <> 'None'
   OR mode_requested <> 'None'
ORDER BY owner, name, session_id;
```

Privileges and view contents depend on release. To correlate with a specific session, match `SESSION_ID` with `GV$SESSION` and identify the right instance.

## 8. Identifying Long Lock-Holding Transactions

A blocking session may be `INACTIVE` while still holding an open transaction. Check transaction start time and undo consumption.

```sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.last_call_et,
       s.sql_id,
       s.prev_sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.addr = s.taddr
ORDER BY t.start_time;
```

`LAST_CALL_ET` depends on session status; for inactive sessions, it indicates seconds since the session became inactive. `USED_UBLK` and `USED_UREC` indicate undo usage for the transaction. These support diagnosis but do not replace reviewing the SQL and application logic.

### 8.1. An Inactive Session Can Still Hold Locks

An application might:

1. Borrow a connection from the pool.
2. Execute an `UPDATE`.
3. Fail to commit/roll back due to exception handling bugs or missing transaction boundaries.
4. Return the connection to the pool with an open transaction if pool/transaction management is misconfigured.

The database session shows no active SQL at observation time, yet its transaction remains open and holds locks. This is a common cause of prolonged lock waits.

### 8.2. Inspect Current and Previous SQL

`GV$SESSION.SQL_ID` reflects current SQL; `PREV_SQL_ID` helps locate the most recent statement. To retrieve SQL text:

```sql
SELECT inst_id,
       sql_id,
       child_number,
       sql_text
FROM gv$sql
WHERE sql_id IN (:waiter_sql_id, :blocker_sql_id);
```

Bind both SQL IDs. If a cursor has aged out of the shared pool, `GV$SQL` may have no rows. With proper privileges and licensing, historical sources can assist, provided you comply with Oracle Diagnostics Pack/Tuning Pack licensing when querying AWR/ASH.

## 9. Investigating ORA-00060 with Deadlock Traces

When Oracle detects a deadlock, it writes a trace file containing the deadlock graph and details on involved resources and sessions. The trace is the primary source for seeing which transaction held what and waited for what at failure time.

### 9.1. Locate the Trace Directory

```sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
```

`Diag Trace` gives the trace directory for the connected instance/session. Deadlock traces are written by database processes into the ADR trace directory. In RAC, identify which instance wrote the trace; inspect the alert log/ADR on that instance.

### 9.2. What to Read in the Deadlock Graph

Traces typically provide:

- Resource type, resource ID, and lock mode.
- Holding session/process.
- Requesting session/process.
- Relationships among resources in the cycle.
- Involved row/object details in many cases.
- Executing SQL or transaction metadata.

When reading the trace, build a table:

| Session | Resource Held | Resource Waited On | SQL/Operation |
|---|---|---|---|
| Session A | Row or enqueue X | Row or enqueue Y | Which object was updated? |
| Session B | Row or enqueue Y | Row or enqueue X | Which object was updated? |

If more sessions are involved, expand the table across the entire cycle. Focus on lock acquisition order, not solely on the table name shown in the error message.

### 9.3. Row Information in Traces

Deadlock traces sometimes include object ID, file number, block number, and row slot. Map the object ID via `DBA_OBJECTS`:

```sql
SELECT owner,
       object_name,
       object_type
FROM dba_objects
WHERE object_id = :object_id;
```

Row details can pinpoint the specific row with appropriate tools and trace detail. Not every deadlock includes full row information; some deadlocks involve metadata/library cache or resources that do not map directly to a table row.

### 9.4. Never Fix Deadlocks Just by Increasing Timeouts

Increasing `DDL_LOCK_TIMEOUT` or wait timeouts does not resolve deadlocks. A cycle will not vanish by waiting longer. Oracle detects the cycle and rolls back a statement to free resources.

For ORA-00060, address inconsistent lock acquisition order, overly broad transaction scope, or hidden chains of triggers/foreign keys adding extra locks.

## 10. Common Causes of Lock Waits and ORA-00054

### 10.1. DDL Executed While Applications Use the Table

An open DML transaction can prevent `ALTER TABLE`, `DROP TABLE`, `TRUNCATE TABLE`, or metadata operations from acquiring required DDL locks.

Solutions:

- Run DDL during an appropriate maintenance window.
- Identify blockers before deploying.
- Wait for open transactions to complete when feasible.
- Use a bounded `DDL_LOCK_TIMEOUT`.
- Split migrations to minimize lock duration.
- Evaluate online DDL where the operation and release support it.

### 10.2. SELECT FOR UPDATE Holding Row Locks Too Long

An application may acquire row locks and then perform external work before committing. Other sessions trying to update those rows must wait.

Reduce the time between lock acquisition and commit, avoid calling external APIs inside transactions, and lock only the rows genuinely needed.

### 10.3. Transactions Forgetting to Commit or Roll Back

A caught exception that leaves the transaction open keeps locks held. Check transaction boundaries in Java/Spring, auto-commit settings, connection pool behavior, and exception handling.

### 10.4. Explicit Table Locks or DDL

PL/SQL or batch jobs may invoke `LOCK TABLE` with strong modes. Avoid broad table locks unless truly required. When required, specify explicit wait bounds and keep transactions short.

### 10.5. DDL on Dependent Objects

Recompiling packages, replacing views, or modifying metadata can contend with sessions executing those objects. If encountering library cache lock/pin waits, inspect executing objects, dependencies, and concurrent DDL.

## 11. Common Causes of Deadlocks

### 11.1. Two Transactions Updating Multiple Rows in Opposite Order

This is the classic case. Transaction A updates row 10 then row 20; Transaction B updates row 20 then row 10. When executed concurrently, they form a cycle.

Solution: enforce a canonical lock order, such as always updating by ascending `ACCOUNT_ID`.

### 11.2. Multiple Tables Updated in Different Orders

Transaction A updates `ORDERS` then `INVENTORY`; Transaction B updates `INVENTORY` then `ORDERS`. When touching overlapping records, they can deadlock.

Solution: define a consistent table access order across services/repositories and enforce it on all code paths.

### 11.3. Triggers Acquiring Hidden Locks

An `UPDATE` on Table A can fire a trigger that updates Table B. The developer may believe only A is locked, while the trigger locks B. If another transaction updates B and its trigger touches A, a deadlock occurs.

When investigating, inspect triggers, invoked packages, and cascading logic—not just the SQL visible in the Java layer.

### 11.4. Foreign Keys and Parent Updates/Deletes

Operations on a parent table may require checking child tables. Unindexed foreign keys can increase locking scope and contention during certain parent deletes/updates. Inspect execution plans, constraints, and indexes on FK columns.

Indexing FKs does not eliminate all deadlocks, but it can reduce table-level contention and make parent key operations more efficient. Base indexing decisions on actual workload.

### 11.5. Long Transactions or Off-Database Work

The longer a transaction stays open, the longer locks persist and the higher the chance of colliding with other transactions. Avoid:

- Opening a transaction and calling external REST APIs.
- Holding a transaction open while sending emails or waiting on a message broker.
- Waiting for user confirmation while holding row locks.
- Running long reports inside a data-modifying transaction.

When coordinating database changes with external systems, consider the outbox pattern, sagas, or committing short transactions first before asynchronous processing.

## 12. Preventing Deadlocks

### 12.1. Standardize Lock Order

This is the single most effective measure against multi-row/multi-table deadlocks. When multiple transactions update the same set of resources, sort them in one deterministic order.

Java example:

```java
List<Long> accountIds = Stream.of(sourceAccountId, targetAccountId)
        .sorted()
        .toList();

// Lock accounts in ascending account_id order before transferring.
```

In the database, select and lock rows in deterministic order:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (:accountIds)
ORDER BY account_id
FOR UPDATE;
```

Order must hold across all related code paths. If a trigger or procedure locks in another order, deadlocks can still occur.

### 12.2. Keep Transactions Short

Execute only necessary operations inside the transaction. Prepare data before starting the transaction where possible; commit immediately after atomic DML finishes.

### 12.3. Lock at the Right Scope

Never use `LOCK TABLE ... EXCLUSIVE` when only a few rows need locking. Use `SELECT FOR UPDATE` with indexed predicates to minimize the locked row set.

### 12.4. Create Appropriate Indexes

Indexes on update predicates help Oracle locate rows quickly and shorten lock duration. Foreign key indexes reduce certain contention during parent operations. Weigh index benefits against added DML overhead.

### 12.5. Avoid Unnecessary Updates

Do not update rows when new values equal current values and no side effects are needed. Reducing locked rows and trigger executions reduces contention.

### 12.6. Separate Asynchronous Work

When a transaction must emit notifications or perform external work, write an outbox row in the same transaction and commit. A worker reads the outbox and dispatches messages afterward, avoiding holding row locks across network waits.

## 13. Handling Lock Errors in Java/Spring Applications

With Spring JDBC, Oracle errors are translated into `DataAccessException` or a subclass by the exception translator. Application code can still inspect the root `SQLException` and vendor error code when classification is needed.

### 13.1. Never Swallow Lock Errors

Do not write:

```java
try {
    repository.updateOrder(order);
} catch (DataAccessException ex) {
    log.warn("Update failed", ex);
    // Continue as if the update succeeded.
}
```

If an update fails due to locking, the application must return an error, retry, or transition the job state. Continuing business logic without the update creates corrupted state.

### 13.2. Roll Back the Transaction on Deadlock

Service example:

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
}
```

If a statement throws an unchecked `DataAccessException` and it propagates out of the method, Spring rolls back the transaction by default. If code catches the exception inside the method without rethrowing, Spring could commit partial changes unless the transaction is marked rollback-only.

On deadlock, let the exception propagate or mark the transaction rollback-only. Then, if retrying, execute the entire operation inside a fresh transaction.

### 13.3. Bounded Retries with Backoff

Retries can help with transient contention, provided they have:

- A bounded maximum attempt count.
- Exponential backoff with jitter to avoid synchronized retry storms.
- A fresh transaction per attempt.
- Idempotency guarantees so business actions never execute twice.
- Metrics/logging to alert on rising contention.

Never retry infinitely. If caused by inconsistent lock order in code, retries merely mask the bug and increase system load.

### 13.4. Retry Strategy: ORA-00054 vs. ORA-00060

For ORA-00054 on DDL, you typically wait for the blocker to finish, reschedule the DDL, or tune `DDL_LOCK_TIMEOUT`. Rapid repeated retries add contention.

For ORA-00060, roll back the active transaction and retry the full unit of work if safe. Never re-run just the failing statement, because earlier statements may have executed and the transaction may still hold locks.

### 13.5. Inspecting Vendor Error Codes

Simple helper example:

```java
static OptionalInt findOracleErrorCode(Throwable error) {
    Throwable current = error;
    while (current != null) {
        if (current instanceof SQLException sqlException) {
            int code = sqlException.getErrorCode();
            if (code == 54 || code == 60) {
                return OptionalInt.of(code);
            }
        }
        current = current.getCause();
    }
    return OptionalInt.empty();
}
```

This snippet illustrates walking the cause chain for vendor error codes. Verify the exception translator and hierarchy of your Spring version. Never depend on error message text, as wording and language can change.

## 14. Handling a Blocker: Commit, Roll Back, or Terminate Session?

When a blocker is found, first identify the session and transaction owner. Never kill a session immediately upon seeing a lock.

Proper order:

1. Identify waiter, blocker, instance, SQL, and object.
2. Identify which application/job owns the blocker and whether the transaction is doing legitimate work.
3. Contact the owner or check runbooks to see if waiting for completion is acceptable.
4. If the work is stuck or invalid, have the application roll back or close the transaction per procedure.
5. Consider terminating the session only with approval and full understanding of rollback impact.

### 14.1. Why Arbitrary Session Killing Is Risky

Terminating a session can:

- Force Oracle to roll back the open transaction, which itself can take considerable time.
- Cause application requests to fail or leave clients with indeterminate outcomes.
- Generate heavy I/O and undo load during rollback.
- Force connection pools to discard and recreate connections.
- Force a long batch job to restart from scratch.

If the session is a payment transaction or critical batch job, killing it can cause greater disruption than the original wait.

### 14.2. Killing a Session in RAC

A DBA can run `ALTER SYSTEM KILL SESSION` specifying SID, SERIAL#, and instance using supported syntax:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
```

This is a high-impact administrative action. Substitute verified session identifiers and follow runbook procedures. `IMMEDIATE` does not mean rolling back a huge transaction finishes instantaneously.

Never treat this command as the default fix for ORA-00054 or ORA-00060. For deadlocks, Oracle has already rolled back one statement to break the cycle; the real fix is transaction lock ordering.

## 15. Locking in RAC

In Oracle RAC, multiple instances access the same database. Global Enqueue Service and Global Cache Service coordinate resources across instances. A waiting session may be blocked by a session on another instance.

### 15.1. Use GV$ Views Instead of Only V$

In RAC, query `GV$SESSION`, `GV$LOCK`, `GV$LOCKED_OBJECT`, and `GV$TRANSACTION` to get `INST_ID` and cluster-wide visibility.

Querying only `V$SESSION` on a single instance can miss blockers or waiters running on other nodes.

### 15.2. Blocking Instance and Final Blocker

`BLOCKING_INSTANCE` identifies the immediate blocker's instance. `FINAL_BLOCKING_INSTANCE` locates the ultimate blocker in a blocking chain—essential when Session B waits on A, while A waits on Session C.

### 15.3. RAC Does Not Eliminate Deadlocks

RAC provides global lock coordination, yet applications can still create logical deadlocks when transactions lock multiple rows/tables in conflicting orders. Locks spanning different nodes do not remove resource-ordering rules.

## 16. Diagnostic Procedure for ORA-00054

When DDL or a `NOWAIT` statement returns ORA-00054, follow this sequence:

1. Identify the failing SQL and the lock type requested.
2. Check `DDL_LOCK_TIMEOUT` if the error occurred on DDL.
3. Locate waiters and blockers via `GV$SESSION`.
4. Inspect current and previous SQL of the blocker.
5. Check whether the blocker has an open transaction via `GV$TRANSACTION`.
6. Identify locked objects via `GV$LOCKED_OBJECT`, `DBA_DDL_LOCKS`, or lock details.
7. Decide whether to wait, retry with backoff, reschedule DDL, or handle the blocking transaction.
8. Once the lock clears, re-run the statement and verify the object is in the expected state.

Do not simply raise timeouts and ignore the blocker. If the same blocker recurs on every deployment, address the long-running transaction or deployment window.

## 17. Diagnostic Procedure for ORA-00060

When ORA-00060 occurs:

1. Record timestamp, service, module, action, SQL ID, and request/job ID.
2. Identify the instance that wrote the deadlock trace.
3. Open the deadlock graph and list every session and resource in the cycle.
4. Identify the involved tables, rows, or objects.
5. Review the SQL and transaction flow of each session.
6. Check triggers, procedures, foreign keys, and hidden calls acquiring additional locks.
7. Pinpoint where resource access order diverges.
8. Update code to enforce a unified lock order or shorten transactions.
9. Write a concurrency test reproducing the deadlock.
10. Monitor deadlock frequency after deploying the fix.

A deadlock trace captures a single point in time. If hard to reproduce, improve observability via application module/action instrumentation, controlled SQL logging, and transaction duration metrics.

## 18. Example: Redesigning a Funds Transfer Transaction

A transfer service updates two accounts. If two concurrent transfer requests run in opposite directions, update ordering can deadlock.

### 18.1. Deadlock-Prone Design

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            amount, fromId);

    jdbc.update("UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            amount, toId);
}
```

Request A transfers from 10 to 20; Request B transfers from 20 to 10. The two transactions acquire locks in opposite orders.

### 18.2. Locking in Account ID Order

Lock both accounts in ascending order before modifying balances:

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    List<Account> accounts = jdbc.query("""
        SELECT account_id, balance
        FROM accounts
        WHERE account_id IN (?, ?)
        ORDER BY account_id
        FOR UPDATE
        """, accountRowMapper, fromId, toId);

    Map<Long, Account> byId = accounts.stream()
            .collect(Collectors.toMap(Account::accountId, Function.identity()));

    Account source = Objects.requireNonNull(byId.get(fromId));
    Account target = Objects.requireNonNull(byId.get(toId));

    if (source.balance().compareTo(amount) < 0) {
        throw new InsufficientFundsException();
    }

    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            amount, fromId);
    jdbc.update("UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            amount, toId);
}
```

This example illustrates locking in a deterministic order. Production code must also handle `fromId == toId`, missing accounts, invalid amounts, precision, and balance rules. Also verify that the execution plan actually locks in the intended order; for strict guarantees, lock each ID sequentially with two separate `SELECT FOR UPDATE` statements.

### 18.3. Concurrency Testing

Create two threads or worker transactions running concurrently:

- Worker A transfers from account 10 to 20.
- Worker B transfers from account 20 to 10.
- Repeat with a synchronization barrier to maximize overlap between transactions.
- Confirm zero deadlocks occur after applying ordered locking.
- Confirm total balance remains invariant outside business fees.
- Confirm insufficient-funds exceptions roll back the entire transaction.

Run tests against a real Oracle instance or fully compatible environment, because database locking semantics vary across engines.

## 19. Wait Events to Distinguish

| Wait Event | General Meaning | Investigation Focus |
|---|---|---|
| `enq: TX - row lock contention` | Waiting on a transaction holding a row lock | Find blocker, transaction age, row/object |
| `enq: TM - contention` | Waiting on a table enqueue | Check DDL, FKs, table lock modes, and DML |
| `library cache lock` | Waiting for a lock on a library cache object | Check DDL/compiles and sessions using the object |
| `library cache pin` | Waiting to pin an object in the library cache | Check object compile/reload and active SQL/PLSQL |
| `row cache lock` | Waiting on a dictionary cache lock | Check concurrent DDL and metadata operations |
| `cursor: pin S wait on X` | Waiting on a cursor/shared pool pin | Investigate cursor invalidation, parsing, and concurrent execution |

Exact event names and interpretations vary by Oracle release. Wait events indicate the type of wait, not the business root cause; correlate them with SQL, sessions, objects, and transactions.

## 20. What Not to Do

- Never kill a session just because it appears as a blocker without identifying its owner and transaction.
- Never raise timeouts indefinitely to mask long transactions.
- Never rapidly retry contested DML without backoff.
- Never catch ORA-00060 and continue the transaction as if the statement succeeded.
- Never execute DDL in the same business flow holding uncommitted DML.
- Never use heavy table locks when row locks suffice.
- Never assume an `INACTIVE` session holds no locks.
- Never use `SKIP LOCKED` if business rules require processing every row without skipping locked ones.
- Never diagnose a deadlock solely from a long wait time; a wait cycle must exist.
- Never check only `V$SESSION` in RAC and assume no blockers exist on other instances.

## 21. Lab: Observing Lock Waits and Deadlocks

### 21.1. Prepare Data

```sql
CREATE TABLE lock_demo (
    id NUMBER PRIMARY KEY,
    value NUMBER NOT NULL
);

INSERT INTO lock_demo(id, value) VALUES (1, 100);
INSERT INTO lock_demo(id, value) VALUES (2, 200);
COMMIT;
```

### 21.2. Create a One-Way Lock Wait

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- Not yet committed.
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
```

Session B waits on Session A. From an administrative session, run the waiter/blocker query from Section 7.1 to identify the blocker. Then commit Session A; Session B proceeds.

### 21.3. Create a Deadlock

Reset data if needed and commit before testing.

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 2;
```

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 2;
-- A waits on B.
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- B closes the wait cycle; one statement receives ORA-00060.
```

After the error, inspect the deadlock trace. Roll back the remaining transaction and check the final table values. Never leave test transactions open at the end of the lab.

### 21.4. Test DDL_LOCK_TIMEOUT

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- Not yet committed.
```

Session B:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 5;
ALTER TABLE lock_demo ADD note VARCHAR2(50);
```

If Session A does not release the lock within the wait window, Session B receives ORA-00054. If Session A commits in time, the DDL proceeds.

## 22. Operations Checklist

When handling a lock-related incident, record:

| Field | Values to Collect |
|---|---|
| Error | ORA-00054 or ORA-00060; timestamp and service |
| Waiter | Instance, SID, SERIAL#, username, module/action, SQL ID |
| Blocker | Instance, SID, SERIAL#, username, status, current/previous SQL ID |
| Resource | TX/TM/DDL/library cache; object/row if identifiable |
| Duration | Seconds in wait, transaction start time, undo usage |
| Trace | ADR trace path and deadlock graph if ORA-00060 |
| Application | Request/job ID, transaction boundary, and retry count |
| Recovery | Commit/rollback, retry, DDL reschedule, or blocker handling per runbook |
| Prevention | Lock order, transaction duration, indexes/FKs, DDL window |

## 23. Principles to Remember

1. A lock wait is normal behavior when another transaction holds a resource; a deadlock is a circular wait that cannot make progress on its own.
2. ORA-00054 usually stems from `NOWAIT` or a lock acquisition timeout; identify the blocker and the requesting statement.
3. `DDL_LOCK_TIMEOUT` lets DDL wait for a bounded interval, but does not fix the blocking cause or resolve deadlocks.
4. ORA-00060 is detected by Oracle via the lock graph; the trace file identifies the resources and sessions in the cycle.
5. On deadlock, Oracle rolls back a statement while the transaction may remain open; the application should roll back the full transaction and retry the unit of work in a new transaction only when safe.
6. Standardizing lock order, shortening transactions, avoiding external calls while holding locks, and adding proper indexes reduce contention.
7. In RAC, use `GV$` views and track `INST_ID` so blockers on other nodes are not missed.
8. Terminate sessions only per runbook after assessing rollback impact; never use session killing as a default fix.

ORA-00054 and ORA-00060 both involve locks, yet reflect distinct situations. ORA-00054 indicates a lock request failed under `NOWAIT` or timeout, requiring you to find the resource-holding session, schedule DDL appropriately, or set a reasonable wait timeout. ORA-00060 indicates Oracle detected a circular wait between transactions, requiring you to inspect the deadlock trace and fix resource acquisition ordering. Understanding this distinction leads to faster incident resolution, avoids harmful session kills or broken retries, and improves transaction design for stable concurrency in Oracle.
