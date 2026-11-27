# Long-Held Locks, Deadlocks, and Hung Transactions

In PostgreSQL, a query can run slowly because it is waiting on a lock, a session can hold locks for a long time even when it is no longer executing any statement, or multiple transactions can wait on each other to the point of forming a deadlock. On the surface, these situations look quite similar: the application responds slowly, statements hang, or updates fail to complete. However, the diagnosis and resolution for each case differ.

This lesson explains how to distinguish long-held locks, hung transactions, and deadlocks; how to locate blocking sessions; how to intervene safely; and how to design applications to reduce the likelihood of recurrence.

## 1. Distinguishing Common Scenarios

Before intervening, determine what state the PostgreSQL session is in.

| Scenario | Primary Symptoms | Meaning |
|---|---|---|
| Query waiting on a lock (lock wait) | **wait_event_type = 'Lock'**; **pg_blocking_pids(pid)** returns blocking PIDs | The query wants to acquire a lock, but another session holds a conflicting lock |
| Long-running transaction | **xact_start** is old; session may be **active** | The transaction has not ended and may continue holding locks and snapshots |
| Idle but unfinished transaction | **state = 'idle in transaction'** | The application finished sending statements but has not issued **COMMIT** or **ROLLBACK** |
| Long-running query | **state = 'active'**, long time since **query_start** | The statement is still executing; it may be consuming CPU/I/O or waiting on a resource |
| Deadlock | PostgreSQL logs **deadlock detected**; one transaction receives SQLSTATE **40P01** | A lock-wait cycle exists; PostgreSQL aborts one transaction to break the cycle |
| Session appears hung | Application receives no result | Could be a lock wait, long query, open transaction, I/O wait, or an application-layer issue |

**A lock wait is not the same as a deadlock.** In a normal lock wait, the waiting session can proceed as soon as the lock-holding session runs **COMMIT**, **ROLLBACK**, or releases the lock. A deadlock occurs when sessions form a circular wait cycle where none can advance on its own.

**A long transaction does not necessarily have a long query.** A session in **idle in transaction** is not running SQL at the moment of observation, yet the transaction remains open. If that transaction modified data or acquired locks, those locks can be held until the transaction ends.

## 2. Relevant Locking Mechanisms in PostgreSQL

PostgreSQL uses MVCC (Multi-Version Concurrency Control) to allow many transactions to read and write concurrently. Each transaction sees a version of data consistent with its snapshot. Thus, a plain **SELECT** query generally does not wait on an **UPDATE** modifying the same row, and writes do not always block reads.

However, MVCC does not eliminate all contention. PostgreSQL still requires locks to protect data and structural changes:

- **Table-level locks:** used for operations such as **SELECT**, **INSERT**, **UPDATE**, **DELETE**, **TRUNCATE**, and DDL. Each statement acquires a specific lock mode. Some modes are compatible with each other; others conflict.
- **Row-level locks:** used for operations such as **UPDATE**, **DELETE**, and **SELECT ... FOR UPDATE**. Two transactions attempting to modify or lock the same row in conflicting ways may have to wait for each other.
- **Transaction ID locks:** a session may wait for another transaction to finish. This is a common manifestation of row-lock contention.
- **Advisory locks:** locks explicitly acquired by the application via **pg_advisory_lock**, **pg_advisory_xact_lock**, and related functions. PostgreSQL attaches no automatic business meaning to these locks; the application must agree on how to acquire and release them.
- **Locks on other objects:** such as virtual transaction locks or locks tied to internal relations and catalogs.

Locks are typically held until the end of the transaction, depending on the lock type and operation. Consequently, a very fast **UPDATE** statement can still force other sessions to wait a long time if its enclosing transaction is never ended.

### 2.1 Row Locks Do Not Always Appear as a Tuple Lock Row

When inspecting **pg_locks**, do not expect every held row lock to appear as a row with **locktype = 'tuple'**. PostgreSQL commonly records row-lock metadata directly on the tuple itself; another session wanting to modify that row must wait on the transaction ID of the lock-holding transaction. As a result, the waiting query may show **wait_event_type = 'Lock'** and **wait_event = 'transactionid'**.

This is why you should use **pg_blocking_pids()** to identify direct blocking relationships. **pg_locks** remains useful for inspecting lock modes, lock types, target objects, and **granted** status, but manually joining lock rows to deduce the entire blocking chain is complex and error-prone.

### 2.2 Table Locks and DDL

DDL operations can require strong table locks. For instance, **ALTER TABLE** often needs **ACCESS EXCLUSIVE**, which conflicts with almost all other table locks. A schema change command may have to wait for active queries using the table to finish; conversely, once DDL enters the wait queue, subsequent queries can also be blocked depending on lock compatibility.

A long-running **SELECT** usually does not block an **UPDATE** simply by reading the same data, but it holds **ACCESS SHARE** on the table while running. That lock can block DDL needing **ACCESS EXCLUSIVE**. Therefore, when a migration stalls, inspect long-running read queries and open transactions as well, not just write statements.

## 3. Common Causes

### 3.1 Application Forgets to End a Transaction

An application flow executes:

```sql
BEGIN;
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;
-- Application continues processing but forgets to COMMIT or ROLLBACK.
```

The transaction remains open and required locks may still be held. Other sessions updating the same row must wait. If the connection is returned to the pool while the transaction is still open, another request may receive that connection in an unexpected state.

Common causes include error branches failing to call **ROLLBACK**, caught exceptions that leave the transaction open, or application logic doing external work while holding a database transaction.

### 3.2 Waiting on Users or External Services Inside a Transaction

A transaction updates data, then calls a payment API, sends an email, or waits for user confirmation before issuing **COMMIT**. Network calls can take many seconds or minutes while database locks remain held.

Keep the work inside a transaction tightly scoped. Read or validate data before opening a transaction whenever possible; then apply the changes requiring atomicity and commit promptly. For workflows coordinating external services, consider the outbox pattern, sagas, or intermediate processing states rather than holding a database transaction open across network waits.

### 3.3 Transactions Locking Multiple Rows in Different Orders

This is the classic cause of deadlocks. Transaction A locks row 1 and then tries to lock row 2; Transaction B locks row 2 and then tries to lock row 1. Each transaction holds a resource the other needs.

### 3.4 Long-Running Queries or DDL Operations

A query scanning a large table, a bulk update touching many rows, an index build, or a migration can extend lock hold times. DDL requiring strong locks may also wait behind active sessions accessing the table.

Distinguish statement execution time from transaction duration. A statement that has already completed inside an uncommitted transaction can continue holding locks.

### 3.5 Missing Indexes or Overly Broad Update Predicates

An **UPDATE** or **DELETE** that has to scan too many rows can run slowly and lock more rows than intended. Appropriate indexes for filter predicates, foreign keys, and access paths typically shorten execution time. However, adding indexes also increases write overhead; base index decisions on execution plans and actual workload.

### 3.6 Foreign Keys and Unique Constraints

When inserting into or deleting from a table with foreign key relationships, PostgreSQL may need to check related rows in the referenced table. Concurrent operations across both tables can introduce extra lock contention. Indexes on foreign key columns generally make related checks and updates more efficient.

**UNIQUE** constraints can also make one transaction wait for another transaction to commit or abort when inserting a duplicate unique key value. When you see waits on **transactionid**, examine statements writing to the table and its constraints.

## 4. Diagnosing with System Views and Functions

The examples below target modern PostgreSQL versions. Viewing details of other sessions requires appropriate monitoring privileges. Roles such as **pg_monitor** or **pg_read_all_stats** may be granted to operational accounts according to your security policy. Without sufficient privileges, fields such as another session's query text may be hidden.

### 4.1 Viewing Active Sessions and Wait States

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    query_start,
    clock_timestamp() - query_start AS query_age,
    state_change,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

Columns to watch:

- **pid**: PostgreSQL backend process ID. This is the value passed to **pg_cancel_backend()** and **pg_terminate_backend()**.
- **application_name**: name of the connected application or connection pool. Configure this in applications to make connection sources easy to identify.
- **state**: states such as **active**, **idle**, **idle in transaction**, or **idle in transaction (aborted)**.
- **wait_event_type**, **wait_event**: resource class and specific event being waited on. **Lock** indicates the session is waiting on a lock.
- **xact_start**: when the current transaction started. If this timestamp is old, the transaction has been open a long time.
- **query_start**: when the current statement started for an **active** session; for non-active sessions, when the most recent statement started.
- **state_change**: when the session state last changed.
- **query**: current statement or most recent statement, depending on session state.

Do not conclude a session is lock-blocked solely because **query_age** is high. Check **wait_event_type** and blocking relationships. A query can run long due to CPU, I/O, its execution plan, or waiting on another resource.

### 4.2 Finding Blocked Sessions and Their Blockers

**pg_blocking_pids(pid)** returns the PIDs of sessions blocking the given backend. It handles both direct blocking from held locks and certain cases where another session is queued ahead.

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    blocked.client_addr AS blocked_client,
    clock_timestamp() - blocked.query_start AS waiting_duration,
    blocked.wait_event_type,
    blocked.wait_event,
    left(blocked.query, 1000) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 1000) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS bp(pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = bp.pid
WHERE blocked.datname = current_database()
ORDER BY blocked.query_start NULLS LAST;
```

How to read the output:

1. **blocked_pid** is the waiting session. Check **waiting_duration**, **blocked_query**, and **wait_event** to assess impact.
2. **blocker_pid** is the blocking session. Check **blocker_state**, **blocker_xact_age**, and **blocker_query**.
3. If **blocker_state = 'idle in transaction'**, the application likely finished its last statement without ending the transaction.
4. If the blocker is itself waiting on another session, a multi-level blocking chain may exist. Inspect **pg_blocking_pids(blocker_pid)** to trace the chain.

The **blocker_query** of an idle session is only its most recent statement, not an active statement. Combine **xact_start**, application logs, and connection details to determine what that transaction did.

If you want to view only sessions waiting on locks, add the filter:

```sql
AND blocked.wait_event_type = 'Lock'
```

This filter helps when focusing strictly on lock waits. For broader investigations, omit it so other wait types are not missed.

### 4.3 Finding Idle Unfinished Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    state_change,
    wait_event_type,
    wait_event,
    left(query, 1000) AS last_query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start NULLS LAST;
```

**idle in transaction** sessions matter because the transaction remains open while executing no query. If the state is **idle in transaction (aborted)**, an earlier statement failed and the transaction is in an aborted state; the application must issue **ROLLBACK** before reusing the connection.

An idle transaction can retain previously acquired locks. It can also hold an old snapshot, delaying VACUUM's cleanup of dead row versions. Therefore, monitor both transaction age and session state.

### 4.4 Viewing Locks in pg_locks

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    CASE
        WHEN l.relation IS NOT NULL THEN l.relation::regclass::text
        ELSE NULL
    END AS relation_name,
    l.mode,
    l.granted,
    l.transactionid,
    l.virtualxid,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 500) AS query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.granted, a.pid NULLS LAST, l.locktype, l.mode;
```

Meaning of key columns:

- **locktype**: type of locked object, such as **relation**, **transactionid**, **virtualxid**, or **advisory**.
- **relation_name**: table or relation name when the lock applies to a relation.
- **mode**: lock mode, such as **AccessShareLock**, **RowExclusiveLock**, or **AccessExclusiveLock**.
- **granted**: **true** means the lock is held; **false** means the backend is waiting for that lock.
- **transactionid**: relevant transaction ID when the lock type is transaction ID.

**pg_locks** is a low-level diagnostic view. A row with **granted = false** indicates a waiting session, but correlate it with **pg_stat_activity** and **pg_blocking_pids()** to pinpoint the blocking session and offending statement.

### 4.5 Monitoring Deadlock Counts

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

**deadlocks** counts deadlocks recorded since the last statistics reset. This value shows trends over an observation window, not the PIDs involved in past deadlocks. To inspect the statements and transactions involved, check PostgreSQL logs at the time of the error.

## 5. Analyzing and Resolving Deadlocks

### 5.1 Example of a Deadlock Between Two Transactions

Suppose an accounts table has two rows with **id = 1** and **id = 2**.

**Session A:**

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

-- Pause while Session B updates row id = 2.

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

**Session B:**

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 50
WHERE id = 2;

-- Pause while Session A requests row id = 2.

UPDATE accounts
SET balance = balance + 50
WHERE id = 1;

COMMIT;
```

The execution sequence can unfold as follows:

1. Session A locks row **id = 1**.
2. Session B locks row **id = 2**.
3. Session A requests row **id = 2** and must wait on Session B.
4. Session B requests row **id = 1** and must wait on Session A.
5. A waits for B while B waits for A. The two transactions form a wait cycle.

PostgreSQL detects the cycle via its deadlock detector. Upon detection, PostgreSQL aborts one transaction as the victim and returns **deadlock detected**. The surviving transaction can proceed once locks are released.

The application must handle this error by rolling back and optionally retrying the entire transaction. Never retry only the final statement, because earlier modifications in the same transaction were aborted.

### 5.2 How to Read a Deadlock Error

The error typically looks like:

```text
ERROR: deadlock detected
DETAIL: Process ... waits for ...; blocked by process ...
HINT: See server log for query details.
SQLSTATE: 40P01
```

Logs can show the processes, lock types, involved objects, and each side's statement. When analyzing, correlate these details:

- PIDs and timestamps in the log.
- Each transaction's statements.
- Involved tables or rows.
- The order in which each transaction acquired locks.
- The business workflow or endpoint generating the statements.

A deadlock is an event PostgreSQL already detected and resolved by aborting one transaction. If the application still sees queries hanging long afterward, check whether another ongoing lock wait is occurring.

### 5.3 Maintain a Consistent Lock Acquisition Order

The most important preventive measure is requiring business workflows to acquire locks in the same consistent order. In the example above, if every transaction always locks accounts in ascending order of **id**, they will never form a cycle simply due to reversed update ordering.

```sql
BEGIN;

SELECT id
FROM accounts
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Apply changes after locking in a consistent order.
UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

When updating multiple rows, establish a uniform lock order across all code paths in the application. Another code path can still trigger a deadlock if it acquires locks in the opposite order.

## 6. Handling Blocking Sessions

Once a blocker is identified, evaluate the transaction before terminating the backend:

1. Identify the application, user, client, and statement via **application_name**, **usename**, **client_addr**, **query**, and application logs.
2. Inspect **state**, **xact_start**, **query_start**, and the sessions waiting behind that blocker.
3. Determine whether this is a valid in-progress transaction, an abandoned transaction, or an anomalous query.
4. If possible, have the application complete or roll back the transaction following agreed operational workflows.
5. Cancel the query or terminate the session only after understanding the impact and confirming proper authorization.
6. Re-run diagnostic queries to verify the blocker is gone and waiting sessions have resumed.

### 6.1 Canceling the Running Statement

```sql
SELECT pg_cancel_backend(12345);
```

Replace **12345** with the verified PID. **pg_cancel_backend()** sends a cancellation request for the backend's current statement. It does not proactively close the connection.

If the statement was running inside an explicit transaction, canceling it typically puts the transaction into an aborted state. The application must issue **ROLLBACK** before starting the next transaction. If the session is **idle in transaction**, there is no active statement to cancel; **pg_cancel_backend()** will not clear that open transaction.

### 6.2 Terminating the Session

```sql
SELECT pg_terminate_backend(12345);
```

**pg_terminate_backend()** terminates the backend connection. Any uncommitted transaction on that connection rolls back when the backend exits. This is stronger than canceling a statement: the application may experience a lost-connection error, have to establish a new connection, and handle unfinished work.

Use this only after verifying the exact PID and accepting the impact on the application. Never terminate a session merely because it has been running long; it may be a legitimate job. Permission to execute these functions depends on session ownership and granted administrative privileges.

### 6.3 Post-Action Verification

After canceling or terminating a backend:

- Re-run the **pg_blocking_pids()** query to confirm the blocking relationship is cleared.
- Check whether previously blocked queries proceeded or failed as expected.
- Monitor application logs for query-canceled errors, connection drops, or retries.
- Verify business data consistency, especially if the application performs retries.
- Record the PID, timestamp, cause, and operational action for reference if the issue recurs.

## 7. Limiting Wait Time and Transaction Duration

PostgreSQL provides several parameters to bound waiting and prevent abandoned transactions.

### 7.1 lock_timeout

**lock_timeout** limits how long a statement waits to acquire each lock. If exceeded, PostgreSQL aborts the statement and returns an error.

You can set the limit per transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
```

**SET LOCAL** applies only to the current transaction. If the statement times out, the application must handle the error and roll back the transaction before proceeding.

### 7.2 statement_timeout

**statement_timeout** limits the total execution duration of a single statement, including lock wait time. This parameter helps prevent runaway queries, though the threshold must match workload characteristics. Setting it too low can abort legitimate reports or batch tasks.

```sql
SET statement_timeout = '30s';
```

It can be set at the session, role, or database level depending on policy. For a specific operation, consider **SET LOCAL** inside a transaction to narrow its blast radius.

### 7.3 idle_in_transaction_session_timeout

This parameter limits how long a session may remain idle while a transaction is open. When exceeded, PostgreSQL automatically terminates the session.

Example configuration for an application role:

```sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '60s';
```

This is a useful safeguard for applications at risk of forgetting to commit or roll back. However, choose a threshold based on valid application processing times; terminating a session causes in-flight work to fail.

### 7.4 Comparing the Three Limits

| Parameter | What It Limits | When Threshold Is Exceeded |
|---|---|---|
| **lock_timeout** | Time spent waiting to acquire a lock | Statement errors out due to lock wait timeout |
| **statement_timeout** | Total duration of a single statement | Statement is canceled |
| **idle_in_transaction_session_timeout** | Idle time within an open transaction | Session is terminated |

Do not set overly small values across the entire system indiscriminately. Consider normal processing durations, SLAs, query types, and impact before configuring at the role or database level.

## 8. Logging for Incident Investigation

When issues occur only intermittently, logs are often the most valuable source of evidence. Consider the following settings in **postgresql.conf**:

```conf
log_lock_waits = on
deadlock_timeout = '1s'
log_line_prefix = '%m [%p] user=%u db=%d app=%a txid=%x '
```

- **log_lock_waits = on**: logs lock waits exceeding **deadlock_timeout**.
- **deadlock_timeout**: how long PostgreSQL waits before running deadlock detection for a lock wait. When **log_lock_waits** is enabled, this threshold also governs when lock waits are logged.
- **log_line_prefix**: adds timestamp, PID, user, database, application name, and transaction ID to each log line for easier correlation.

After modifying settings, reload configuration following your system's administrative procedure. Some parameters require administrative privileges; evaluate log volume and operational impact before applying changes.

Configure a meaningful **application_name** in your applications or connection pools. When logs show **app=inventory-worker**, operators can quickly trace the database session back to the service that opened it.

When a deadlock occurs, look for **deadlock detected** in the logs along with PIDs and timestamps. PostgreSQL generally logs details of the waiting processes and involved locks. Combine these logs with application logs to reconstruct the statement sequence within each transaction.

## 9. Preventive Practices in Application Design

### 9.1 Keep Transactions Short

Include only operations requiring atomicity inside a transaction. Avoid waiting on users, making HTTP calls, sending emails, downloading files, or performing slow work while a transaction is open.

A healthy workflow typically looks like:

1. Perform validation and data preparation that do not require locks before opening the transaction.
2. Open the transaction.
3. Read or lock the necessary data.
4. Apply the related changes.
5. **COMMIT** immediately upon completion.
6. Run external non-database tasks after commit or via a queue/outbox.

### 9.2 Always End Transactions on Every Code Path

In application code, ensure both success and error paths close the transaction. With connection pools, never return a connection to the pool while a transaction is still open or in an aborted state.

Implementation patterns vary by framework, but the core rules are:

- Success: commit.
- Error before commit: rollback.
- Rollback fails or connection is no longer reliable: evict the connection from the pool using the driver/pool mechanism.
- Never swallow an exception and keep using a transaction already marked aborted.

### 9.3 Standardize Lock Ordering

If multiple workflows update the same set of resources, define a consistent lock ordering—for example by **account_id**, **product_id**, or resource type. Enforce this rule across all services, batch jobs, and administrative tasks.

### 9.4 Lock the Right Scope

Use **SELECT ... FOR UPDATE** only when you need to prevent other transactions from modifying rows during processing. Avoid locking a large set of rows upfront when business logic only needs a small subset. Proper filter predicates and indexes reduce both the number of scanned rows and lock hold duration.

### 9.5 Handle Retries Properly

Deadlocks and certain concurrency errors are transient failures that can be retried. In PostgreSQL, common SQLSTATEs include:

| SQLSTATE | Meaning | Typical Handling |
|---|---|---|
| **40P01** | **deadlock_detected** | Roll back the entire transaction, then optionally retry |
| **40001** | **serialization_failure** | Roll back the entire transaction and retry per policy |
| **55P03** | **lock_not_available** | Check timeout or non-blocking lock attempt |
| **57014** | **query_canceled** | Determine whether the statement timed out or was canceled intentionally |

When retrying:

- Retry the entire transaction from the beginning, not just the last statement.
- Cap the maximum number of retries.
- Use exponential backoff and jitter to keep multiple clients from retrying at the same instant.
- Ensure the operation is idempotent or guarded against duplicate processing.
- Log retry count, SQLSTATE, and business context.

Never retry indefinitely. If the cause is bad lock ordering or overly long transactions, retries only increase load and cause the incident to repeat.

### 9.6 Execute DDL Carefully

Before running migrations on active tables:

- Estimate execution duration and the lock mode required by the DDL command.
- Avoid placing migrations inside long transactions when unnecessary.
- Use **lock_timeout** so migrations fail fast if they cannot acquire the lock within the allowed window.
- Run migrations at appropriate times and monitor blocked sessions.
- For indexes on active tables, consider **CREATE INDEX CONCURRENTLY** when appropriate. This command has specific rules and cannot run inside an explicit transaction block.

Example setting a lock wait limit before DDL:

```sql
SET lock_timeout = '5s';
ALTER TABLE orders ADD COLUMN source_code text;
```

If the lock is not acquired within 5 seconds, the command fails so the migration can be rescheduled or retried according to procedure. Choose the timeout based on criticality and allowable maintenance windows.

## 10. Practical Investigation Workflow

When receiving a report such as "the database is hung" or "the update API is not responding," follow this sequence:

**Step 1 — Determine the blast radius.** Ask which operations are slow, when it started, whether it affects one endpoint or the whole system, and whether any deployments or migrations happened around that time.

**Step 2 — Check backend states.** Use **pg_stat_activity** to find **active** and **idle in transaction** sessions, transaction age, and **wait_event**.

**Step 3 — Find blocking relationships.** Use **pg_blocking_pids()** to identify waiting sessions and blockers. If multi-layered, follow each PID to locate the root blocker.

**Step 4 — Trace the blocker's origin.** Correlate **application_name**, user, client, **xact_start**, state, and most recent statement with application logs. Watch closely for idle-in-transaction sessions.

**Step 5 — Distinguish lock waits from deadlocks.** If PostgreSQL logged **deadlock detected**, inspect logs and SQLSTATE **40P01**. If it is an active lock wait, inspect the lock-holding transaction and what is needed for it to finish.

**Step 6 — Choose the least disruptive action.** If a legitimate transaction is about to finish, wait or coordinate with the application owner. If a query is anomalous, consider canceling it. If a session abandoned a transaction and is causing impact, consider terminating it after verifying impact.

**Step 7 — Confirm recovery.** Re-run the blocker query, and monitor endpoint latency, connection counts, and error logs. Verify that involved transactions have ended.

**Step 8 — Fix the root cause.** Repair code paths missing commit/rollback, shorten transactions, standardize lock ordering, optimize queries, or tune migration and timeout settings.

## 11. Pitfalls to Avoid

- **Looking only at query duration:** a slow query may be CPU/I/O-bound, while the blocking session may be idle in transaction. Always inspect **state**, **wait_event**, and **xact_start**.
- **Assuming every lock wait is a deadlock:** a lock wait clears on its own when the blocker commits or rolls back. A deadlock is a circular wait cycle detected separately by PostgreSQL.
- **Looking only for tuple locks in pg_locks:** row locks may not appear as expected; use **pg_blocking_pids()**.
- **Terminating the oldest session first:** that PID might be a legitimate job or even a waiting session. Identify the root blocker before acting.
- **Retrying only the failed statement:** when a transaction is aborted by a deadlock, you must roll back and replay the entire unit of work.
- **Setting overly low timeouts system-wide:** this can break legitimate reports, batch jobs, or migrations. Scope configuration and thresholds to the workload.
- **Ignoring idle in transaction:** this state can hold locks and snapshots for a long time even with no SQL running.
- **Omitting application_name:** missing application identifiers makes tracing a PID back to a service or job much harder.

## 12. Key Takeaways

- A lock wait is a session waiting for a lock; a deadlock is a circular wait cycle between transactions.
- A transaction can continue holding locks after its final statement completes, until **COMMIT** or **ROLLBACK**.
- **idle in transaction** demands attention because the session is running no query while the transaction stays open.
- **pg_stat_activity** shows session states and ages; **pg_blocking_pids()** pinpoints direct blockers; **pg_locks** provides low-level lock details.
- PostgreSQL automatically detects deadlocks and aborts one transaction; applications must roll back and perform bounded retries of the entire transaction.
- Short transactions, consistent lock ordering, appropriate timeouts, and logs including **application_name** reduce both investigation time and recurrence risk.
