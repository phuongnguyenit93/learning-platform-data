# Canceling Queries, Terminating Sessions, and Impact Assessment in PostgreSQL

## 1. Why Distinguish Between Query Cancellation and Session Termination?

When PostgreSQL has a query running too long, holding locks, or exhausting resources, operators often need to intervene to restore service. PostgreSQL provides two important administrative functions:

- `pg_cancel_backend(pid)` sends a signal requesting the cancellation of the currently running statement in a backend.
- `pg_terminate_backend(pid)` sends a signal terminating the backend session, causing the connection to be closed and any open transaction to be rolled back.

These two actions have different scopes and impacts. Canceling a query usually preserves the connection so the application can continue after handling the error. Terminating a session is more drastic: all uncommitted work in the session is discarded, locks are released when the backend exits, but the application must handle the connection failure and may have to reconnect.

An uninformed decision can disrupt valid transactions, cause mass application retries, lose uncommitted work, or create commit ambiguity for the client. Before sending a signal, you must identify the exact PID, owner, query, transaction age, wait event, blockers, and business impact.

```text
Incident / slow query / lock contention
                 |
                 v
          Inspect pg_stat_activity
                 |
                 v
       Identify exact backend and impact
                 |
                 v
        Is a query actively running?
             /           \
           Yes            No
            |              |
            v              v
    pg_cancel_backend   Inspect idle transaction,
            |           pool and session ownership
            v
      Did query stop?
         /       \
       Yes        No / session still harmful
        |                    |
        v                    v
  Check transaction     Re-evaluate target and
  state and locks       pg_terminate_backend
        |                    |
        +---------+----------+
                  |
                  v
       Verify rollback, locks, app recovery,
       latency and service health
```

**Operational principle:** choose the smallest action capable of resolving the incident, verify the outcome, and assess the impact on both transactions and the application.

### Learning Objectives

After this lesson, you can:

1. Distinguish between `pg_cancel_backend` and `pg_terminate_backend`.
2. Read `pg_stat_activity` to identify the backend that needs intervention.
3. Analyze lock blockers using `pg_blocking_pids`.
4. Evaluate query age, transaction age, and wait events.
5. Understand transactions in the aborted state after query cancellation.
6. Identify when cancellation does not release locks.
7. Understand rollback and commit ambiguity when terminating a session.
8. Check `pg_signal_backend` privileges and superuser restrictions.
9. Safely handle parallel queries and connection pools.
10. Configure `statement_timeout`, `lock_timeout`, and idle transaction timeouts.
11. Assess the impact on DDL, index builds, maintenance, and replication.
12. Audit and monitor the results of interventions.
13. Design runbooks, alerts, and retry policies.
14. Avoid canceling/terminating the wrong backend or triggering a retry storm.
15. Verify that service has recovered after intervention.

---

## 2. Backend Sessions and Queries in PostgreSQL

A client connection is typically served by a PostgreSQL backend process. The backend holds session state, transaction state, prepared statements, locks, and related resources.

A session can be:
- Running a query.
- Waiting on a lock or I/O.
- Idle between statements.
- Idle while still inside a transaction.
- In an aborted transaction state after an error.
- Executing an administrative command or long-running operation.

### 2.1. A Session Can Run Multiple Queries Over Time

When a query finishes, the connection can continue to be used for other statements. Therefore, query cancellation does not mean the connection is closed.

### 2.2. A Transaction Can Outlive a Query

An application can open a transaction, execute multiple statements, and then leave the session idle. The current query is no longer active, yet the transaction still holds snapshots and locks.

### 2.3. Backend PID Is the Target of Administrative Functions

`pg_stat_activity.pid` identifies the process serving the session/backend. Always confirm the PID, user, database, application_name, and backend_start before sending a signal.

### 2.4. Not Every Process in pg_stat_activity Is a Client Session

The view can display background workers, WAL senders, autovacuum, and internal processes. Standard runbooks should restrict targets to client backends unless a specialized procedure applies.

## 3. What Is pg_cancel_backend?

`pg_cancel_backend(pid)` sends a query-cancel signal to the specified backend.

Example:

```sql
SELECT pg_cancel_backend(12345);
```

If the signal is sent successfully, the function returns true. That only indicates the signal was dispatched; it does not prove the query has already stopped by the time the function returns.

### 3.1. The Connection Remains Alive

Cancellation asks the backend to abort the currently executing statement. The backend session usually remains alive and can accept another query once the transaction state is handled.

### 3.2. Only an Active Query Is Targeted

If a session is idle, there is no active statement to cancel. If a session is idle in transaction, the issue may be an open transaction rather than a running query.

### 3.3. Query Cancellation Is Processed at Interrupt Points

The backend checks for signals at interrupt checkpoints. An operation may not stop immediately if it is in a code section or state that does not immediately process signals. Monitor the state after sending the signal.

### 3.4. Common SQLSTATE

Clients typically receive a query-canceled error with SQLSTATE `57014`. Drivers and frameworks may represent the exception differently; inspect both the SQLSTATE and application logs.

## 4. What Is pg_terminate_backend?

`pg_terminate_backend(pid)` sends a signal to terminate the backend process/session.

Example:

```sql
SELECT pg_terminate_backend(12345);
```

The backend is terminated, the connection is closed, and any uncommitted transaction in the session is rolled back as PostgreSQL handles backend exit.

### 4.1. The Session Is Closed

The application will observe a lost connection or connection error. Connection pools usually must discard that connection and establish a new one.

### 4.2. Any Open Transaction Is Rolled Back

All uncommitted changes in the transaction are discarded. Previously committed transactions are not undone by termination.

### 4.3. Locks Are Released When the Backend Exits

When the transaction/backend exits, the session's locks and transaction resources are released. Waiting sessions can proceed, though this can also unleash a burst of load immediately afterward.

### 4.4. The Client May Not Know Whether COMMIT Succeeded

If the connection is lost right while COMMIT is being processed, the client may not know whether the transaction committed before the backend was terminated. Reconcile using a business operation ID or idempotency key.

## 5. Comparing Cancel and Terminate

| Criterion | pg_cancel_backend | pg_terminate_backend |
|---|---|---|
| Target | Currently running query | Backend session |
| Connection | Usually kept open | Closed |
| Current query | Requested to cancel | Stopped when backend exits |
| Explicit transaction | May transition to aborted state | Uncommitted transaction rolled back on backend exit |
| Locks | May still be held until transaction ends | Released when backend/transaction ends |
| Client | Usually receives query-canceled error | Usually receives connection error |
| Reconnect | Not required if session remains healthy | Pool/client usually must reconnect |
| Impact scope | Narrower | Broader |
| Suitable use cases | Runaway query, overly long statement | Hung session, idle transaction holding locks, cancel insufficient |

### 5.1. Cancel First, Terminate Later

In many incidents, canceling the query is a reasonable first step when targeting a specific statement. If the transaction still holds locks or the session fails to roll back or exit the transaction on its own, evaluate termination.

### 5.2. Not an Absolute Rule

An idle in transaction session has no query to cancel. In that case, handle the transaction/session according to policy—typically requesting an application rollback or terminating after verification.

### 5.3. Impact-Based Decisions

If a query is an important batch job nearly finished, canceling it may waste work. If a query is blocking thousands of requests, continuing to wait may cause greater damage.

## 6. Reading pg_stat_activity Before Acting

Overview query:

```sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    backend_start,
    xact_start,
    query_start,
    state_change,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
```

### 6.1. pid

The PID is used as the argument for cancel/terminate functions. Never pick a PID from an outdated dashboard snapshot alone.

### 6.2. application_name

Helps identify the service, job, or tool owning the connection. Applications should set a stable and meaningful application_name.

### 6.3. state

Common states include active, idle, idle in transaction, and idle in transaction (aborted). The state determines whether to cancel a query or handle the session/transaction.

### 6.4. wait_event_type and wait_event

Indicate what type of event the backend is waiting on, such as Lock or IO. An active backend is not necessarily consuming CPU; it may be waiting.

### 6.5. query_start and xact_start

query_start indicates when the current statement began. xact_start indicates when the transaction began. Transaction age can be much larger than query age.

### 6.6. backend_type

On versions that have this column, filtering `backend_type = 'client backend'` helps focus on client sessions. Check the view columns on the running version before using fixed monitoring queries.

## 7. Finding Long-Running Queries

Example showing only active backends running longer than 5 minutes:

```sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 400) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
  AND query_start < clock_timestamp() - interval '5 minutes'
ORDER BY query_start;
```

### 7.1. Long Duration Does Not Equal a Bad Query

A report, backup coordination task, or maintenance operation may run long by design. Compare against workload class and SLOs.

### 7.2. Active Queries That Are Waiting

If `wait_event_type = 'Lock'`, the query may be waiting on a blocker. If the wait event is I/O, low CPU does not mean the query has no impact.

### 7.3. Query Age Does Not Measure CPU Time

This is elapsed time since `query_start`. It includes time spent waiting on locks, I/O, and other waits.

### 7.4. Do Not Rely on Query Text Alone

Query text may be truncated or hidden due to permissions. Combine PID, application_name, user, database, wait event, and logs.

## 8. Finding Idle in Transaction Sessions

Query:

```sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    now() - xact_start AS transaction_age,
    state_change,
    wait_event_type,
    wait_event,
    left(query, 300) AS last_query
FROM pg_stat_activity
WHERE state IN (
    'idle in transaction',
    'idle in transaction (aborted)'
)
ORDER BY xact_start;
```

### 8.1. Idle in Transaction

The session is waiting for the client to send the next statement, but the transaction remains open. It can hold locks and snapshots.

### 8.2. Idle in Transaction (aborted)

A statement failed or was canceled inside an explicit transaction. The transaction is aborted and requires a ROLLBACK or session termination.

### 8.3. pg_cancel_backend Does Not Resolve Idle Sessions

If the session is not executing a query, cancel has no useful active statement to stop. Application rollback or termination after verifying owner/impact is required.

### 8.4. Vacuum Impact

Old transaction snapshots can prevent vacuum from removing dead tuples, causing table and index bloat to grow over time.

## 9. Finding Blockers Before Canceling

A slow query may be a victim of lock contention. Find blockers:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    blocker.state AS blocker_state,
    left(blocked.query, 250) AS blocked_query,
    left(blocker.query, 250) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid))
    AS p(blocker_pid) ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
```

### 9.1. Canceling a Victim May Not Fix the Blocker

If a query waiting on a lock is canceled, the blocker still holds the lock. Other requests continue waiting.

### 9.2. A Blocker May Be Idle

A blocker in `idle in transaction` can hold transaction-level locks even without an active query. Canceling the blocker is not enough; transaction rollback or session termination is needed.

### 9.3. The Root Blocker Matters More Than the List of Victims

A single transaction can block hundreds of sessions. Identify the root blocker before sending signals.

### 9.4. Check the Blocker Owner

Identify the service, user, client address, transaction age, and business operation. A migration or payment transaction may require coordination with the owner before terminating.

## 10. Understanding Lock State and Lock Lifetime

PostgreSQL holds various locks for either transaction or statement lifetimes.

### 10.1. Transaction-Level Locks

Many locks are held until the transaction ends. If a statement inside an explicit transaction is canceled and the transaction enters the aborted state, locks may still be held until ROLLBACK.

### 10.2. Statement-Level Effects

Some locks or tuple states have lifetimes tied to statements or savepoint behavior. Never assume all locks are immediately released upon query cancellation.

### 10.3. Savepoints

Applications can use SAVEPOINT to roll back part of a transaction. If errors are handled properly via savepoints, the outer transaction can continue; behavior depends on where the error occurs and application control flow.

### 10.4. Termination

When a session is terminated, the transaction ends abnormally and PostgreSQL rolls back uncommitted work, then releases locks and resources.

## 11. What Happens After Cancel in Autocommit?

If an application runs a standalone statement in autocommit mode:
1. PostgreSQL begins an implicit transaction for the statement.
2. The executing statement is canceled.
3. The statement fails and the implicit transaction is rolled back.
4. The connection usually stays open.
5. The application receives a query-canceled error.
6. Subsequent statements can run on the connection unless the driver closes it for its own reasons.

### 11.1. Uncommitted Data Is Discarded

Changes made by the statement are rolled back. Previously committed transactions remain intact.

### 11.2. Do Not Assume External Side Effects Are Rolled Back

Functions or extensions may call external systems. PostgreSQL rollback cannot automatically undo emails, HTTP requests, or file operations executed outside the transaction.

### 11.3. The Application Must Handle SQLSTATE

The client must catch the query-canceled exception, decide whether to retry or return an error, and never proceed assuming the statement succeeded.

### 11.4. Connection Pools

The pool can retain the connection if the session remains healthy. If the driver marks the connection as broken, the pool must evict it. Monitor pool metrics rather than assuming.

## 12. What Happens After Cancel in an Explicit Transaction?

Example:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;

-- A subsequent statement is canceled.

SELECT pg_sleep(120);

COMMIT;
```

If a statement inside a transaction is canceled, the transaction usually transitions to the aborted state. Subsequent statements typically receive the error:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
```

### 12.1. ROLLBACK Is Required

The client must send ROLLBACK to end the aborted transaction and release transaction-level locks.

### 12.2. Do Not Send COMMIT to "Save" an Aborted Transaction

Issuing COMMIT in an aborted state does not make earlier changes committed. PostgreSQL ends the transaction in a rolled-back state.

### 12.3. Savepoints Are a Controlled Exception

If the application set a SAVEPOINT and handles the error with ROLLBACK TO SAVEPOINT in an appropriate flow, the outer transaction can continue. Do not assume a framework does this automatically without verifying.

### 12.4. If the Client Abandons the Connection in an Aborted State

The session can remain in `idle in transaction (aborted)`, holding resources until the client rolls back or the session is terminated or times out.

## 13. When Does Cancel Not Release Locks?

A typical scenario:
1. Session A opens a transaction.
2. A executes an UPDATE and acquires row/table locks.
3. A runs a subsequent long-running statement.
4. An operator cancels that statement.
5. Transaction A transitions to aborted.
6. The client does not send ROLLBACK.
7. A remains `idle in transaction (aborted)`, and the transaction's locks are not yet released.

```text
Session A
  BEGIN
    |
  UPDATE row X
    |
  holds transaction locks
    |
  long SELECT / statement
    |
  pg_cancel_backend(A)
    |
  statement aborted
    |
  transaction remains aborted/open
    |
  locks may remain until ROLLBACK
```

### 13.1. Check State After Cancel

Re-query `pg_stat_activity`. If the state is `idle in transaction (aborted)`, wait briefly for the application to roll back per the runbook.

### 13.2. Coordinate with the Application Owner

If the client has transaction cleanup logic, letting it roll back can preserve connection reuse and record the exception properly.

### 13.3. Terminate If the Session Continues Causing Harm

If the transaction does not roll back and continues blocking the workload, terminating the session may be necessary after assessing business impact.

### 13.4. Do Not Cancel a Blocker and Declare the Incident Over

Verify that lock waiters actually make progress and that the blocker transaction has ended.

## 14. What Happens When a Session Is Terminated?

When a backend is terminated:
- The connection is closed.
- Any running query cannot continue.
- Uncommitted transactions are rolled back.
- Locks and transaction resources are released when the backend exits.
- The client receives a connection error.
- The pool or client can reconnect or retry.
- Previously committed work is not rolled back.

### 14.1. Rollback Does Not Undo Every Side Effect

External systems outside the PostgreSQL transaction may have already received side effects. Use an outbox or idempotency pattern to manage these effects.

### 14.2. Large Transactions

A very large write transaction may have already generated WAL and dead tuples/cleanup work. Termination does not erase WAL history; vacuum, recovery, and storage still have to handle the resulting aftermath.

### 14.3. Client Commit Outcome

If termination occurs around COMMIT, the client cannot reliably infer the outcome from the connection error alone. Reconcile using a request key or business record on the current primary.

### 14.4. Connection Pool Churn

Terminating many sessions can cause pools to create new connections en masse, increasing authentication/startup overhead and load on the postmaster.

## 15. Verify the Right Backend Before Signaling

Before intervening, capture a snapshot:

```sql
SELECT
    pid,
    backend_start,
    datname,
    usename,
    application_name,
    client_addr,
    backend_type,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

Confirm:
- The PID still exists.
- User and database match.
- Application and client match.
- Query and transaction match the incident.
- Backend type is client backend if the runbook only permits client sessions.
- State has not changed indicating the query already finished.
- It is not the PID of a monitoring or admin connection that must be preserved.

### 15.1. PIDs Can Disappear

A query may complete between inspection and cancellation. The function may return false if the process no longer exists or cannot be signaled.

### 15.2. A PID Is Not a Business Identity

Record `application_name`, `client_addr`, `query_start`, `backend_start`, and request/incident context as well. OS PIDs can be reused after a process exits.

### 15.3. Re-Verify Immediately Before Action

Never use a PID copied from an old alert. Refresh `pg_stat_activity` right before executing.

### 15.4. Exclude the Current Backend

Never send a signal to the PID of the session running the administrative command itself; use `pg_backend_pid()` to exclude it.

## 16. Canceling a Specific Query with pg_cancel_backend

After verifying the PID and target:

```sql
SELECT pg_cancel_backend(12345) AS signal_sent;
```

### 16.1. Returning true

True indicates the cancel signal was sent successfully. The query might still not have stopped at the exact instant the result returns.

### 16.2. Returning false

The backend may have exited, the PID may be invalid, or the signal could not be delivered. Re-check `pg_stat_activity` and privileges.

### 16.3. Post-Cancel Verification

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

If the query finished, the state may no longer be active. If the session remains `idle in transaction (aborted)`, the transaction must be handled.

### 16.4. Cancel Can Race with Query Completion

The query may finish before the backend processes the signal. Always verify the actual outcome instead of inferring from the boolean return alone.

## 17. Terminating a Session with pg_terminate_backend

When you have confirmed the session must be terminated:

```sql
SELECT pg_terminate_backend(12345) AS signal_sent;
```

### 17.1. Boolean Return

Without a timeout argument, true indicates the terminate signal was sent successfully; do not naively assume all client-side cleanup is complete.

### 17.2. Timeout Argument in Supported Versions

Newer PostgreSQL versions offer an overload accepting a timeout in milliseconds:

```sql
SELECT pg_terminate_backend(12345, 5000) AS terminated_within_timeout;
```

Check the exact server version and function signature. On versions without the timeout overload, use the single-argument form and poll `pg_stat_activity` to confirm the backend has disappeared.

### 17.3. Timeout Is Not a Query Timeout

The timeout argument of `pg_terminate_backend` (where available) is how long to wait for the backend to exit after signaling. It is not an execution time limit for a SQL statement.

### 17.4. Verify the Backend Has Exited

```sql
SELECT pid, backend_start, state, application_name
FROM pg_stat_activity
WHERE pid = 12345;
```

Zero rows may indicate the backend has exited. Combine with logs and application connection status to confirm completely.

## 18. Privileges Required for Cancel and Terminate

Backend signaling functions are privilege-restricted.

Typically:
- A superuser can signal backends, while signaling backends owned by a superuser remains restricted to superusers.
- A user can signal backends belonging to the same role according to ownership rules.
- A role granted the predefined role `pg_signal_backend` can signal backends owned by other roles, subject to the non-superuser restriction.

### 18.1. Least Privilege

Do not grant superuser to monitoring or application accounts just to cancel queries. Create operational roles with appropriate permissions per policy.

### 18.2. pg_signal_backend

Example role grant:

```sql
GRANT pg_signal_backend TO ops_operator;
```

Grant only to authorized operators and audit membership. This role is powerful because it can disrupt other sessions.

### 18.3. Checking Privileges

If the function returns false or reports permission denied, verify role membership and ownership. Never attempt to bypass permissions using an unapproved service account.

### 18.4. Query Text May Be Hidden

A role lacking full statistics privileges may not see the query text of other sessions. Monitoring roles may require `pg_read_all_stats` under a separate policy.

## 19. Finding Blockers and Choosing the Right PID to Cancel

A blocked query is not always the query you should cancel. For example, a SELECT waiting on an UPDATE transaction holding a row lock; canceling the SELECT only removes one waiter and does not free the blocker.

### 19.1. Identify Blocked Sessions

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS wait_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### 19.2. Inspect Blocker State

The blocker may be active, idle in transaction, or waiting on yet another resource. Trace the root blocker and dependency chain.

### 19.3. Cancel the Blocker Query

If the blocker is executing a long query and the transaction can be automatically rolled back by the application, cancel may suffice. Verify transaction state and lock release.

### 19.4. Terminate the Blocker Session

If the blocker is idle in transaction, abandoned, or cannot roll back via the application, termination can release transaction locks. Evaluate uncommitted work first.

## 20. Parallel Queries and Worker Processes

A parallel query has a leader backend and one or more parallel workers. When the leader query is canceled, PostgreSQL coordinates canceling the parallel execution.

### 20.1. Identify the Leader

Some PostgreSQL versions include a `leader_pid` column in `pg_stat_activity` to associate workers with their leader. Check the view definition for your running version.

### 20.2. Target the Client Backend Owning the Query

Prioritize targeting the client/leader session PID identified in `pg_stat_activity`. Do not arbitrarily pick and terminate individual worker PIDs just because multiple processes appear.

### 20.3. Workers Are Not Regular Client Sessions

Parallel workers are internal processes. Terminating the wrong worker can fail the query without properly addressing the transaction owner.

### 20.4. Verify Cleanup

After canceling or terminating, monitor the leader, workers, and connection pool. Verify associated worker processes have exited and resources are freed.

## 21. Canceling and Terminating DDL

DDL operations can hold strong locks, affect many sessions, and run for a long time.

Examples:
- ALTER TABLE.
- CREATE INDEX.
- REINDEX.
- DROP TABLE.
- VACUUM FULL.
- Partition maintenance.

### 21.1. Identify the DDL Owner

Check the migration tool, deployment ID, `application_name`, and change window. A DDL statement might be an authorized migration.

### 21.2. Canceling DDL

Canceling a statement usually causes it to fail and roll back per transaction semantics. However, some DDL statements have special behavior and may leave behind artifacts that need inspection.

### 21.3. CREATE INDEX CONCURRENTLY

If `CREATE INDEX CONCURRENTLY` fails or is canceled, it can leave behind an index in an invalid state. Check `pg_index.indisvalid`/`indisready` and clean up the index per runbook before retrying.

### 21.4. Do Not Terminate a Migration Just Because Query Age Is High

Evaluate lock impact, progress views, application traffic, and rollback/cleanup implications first.

## 22. Canceling Maintenance Operations

VACUUM, ANALYZE, REINDEX, and maintenance tasks can run for a long time and consume I/O.

### 22.1. Check Progress Views

Use appropriate progress views such as `pg_stat_progress_vacuum`, `pg_stat_progress_create_index`, or `pg_stat_progress_analyze` depending on the operation and version.

### 22.2. Autovacuum Workers

Do not terminate autovacuum merely because it is active or running long. Autovacuum protects table health and transaction ID freezing.

### 22.3. Manual VACUUM

If a manual VACUUM must be stopped, understand the impact on vacuum coverage, dead tuples, and maintenance schedules. Do not treat cancellation as completed maintenance.

### 22.4. REINDEX and Index Validity

After canceling or restarting index operations, verify index state and application query plans.

## 23. Canceling Queries Waiting on Locks

If a query has been waiting on a lock for too long, you can cancel the waiting query to free client or request capacity.

Example:

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
  AND pid <> pg_backend_pid();
```

Then cancel only the confirmed waiter:

```sql
SELECT pg_cancel_backend(12345);
```

### 23.1. Query Cancellation Does Not Fix the Lock Root Cause

If many waiters are blocked by one blocker, investigate the blocker. Canceling only waiters can spike request errors while contention remains.

### 23.2. Lock Timeout May Be Better Suited

`lock_timeout` limits how long a statement waits for a lock. It enables failing fast for future statements, though it does not resolve an existing blocker.

### 23.3. Statement Timeout

`statement_timeout` limits total statement duration, including time spent waiting on locks. Choose values aligned with the endpoint or query class.

### 23.4. Do Not Retry Immediately Without Backoff

If the application retries continuously while the blocker remains unresolved, it can worsen queue buildup and system load.

## 24. statement_timeout: Preventing Runaway Queries

`statement_timeout` automatically cancels statements exceeding the configured duration.

Example:

```sql
SET statement_timeout = '30s';

SELECT *
FROM orders
WHERE customer_id = 42;
```

### 24.1. Scope

`SET` applies to the current session. Defaults can be configured per role/database, or `SET LOCAL` can be used for a single transaction.

### 24.2. Do Not Use One Value for All Queries

An OLTP endpoint may need a short timeout; reports and ETL jobs require a larger budget. Configure by workload class.

### 24.3. Server-Side vs. Application Deadlines

Application deadlines and `statement_timeout` must be coordinated. If the client times out first, the connection may be abandoned while the query keeps running if the driver does not cancel properly.

### 24.4. SET LOCAL

```sql
BEGIN;
SET LOCAL statement_timeout = '10s';

SELECT ...
;

COMMIT;
```

A local setting automatically expires when the transaction ends.

## 25. lock_timeout: Limiting Lock Wait Duration

`lock_timeout` limits only the time spent waiting to acquire a lock. If exceeded, the statement aborts with an error.

```sql
SET lock_timeout = '2s';
```

### 25.1. Should Be Smaller Than statement_timeout

If both are configured, `lock_timeout` should be lower than `statement_timeout` so a statement fails due to lock wait before the overall deadline expires.

### 25.2. Does Not Replace statement_timeout

A query can run long on CPU or I/O after acquiring its locks; `lock_timeout` does not limit execution time afterward.

### 25.3. DDL Migrations

A short `lock_timeout` helps migrations fail fast instead of blocking traffic for long periods. Migration tooling needs appropriate retry and backoff logic.

### 25.4. Transaction State

Inside an explicit transaction, a lock timeout error puts the transaction into the aborted state unless handled via savepoints or appropriate exception flow.

## 26. idle_in_transaction_session_timeout

`idle_in_transaction_session_timeout` terminates a session so that an overly long idle transaction does not keep holding resources.

```sql
SHOW idle_in_transaction_session_timeout;
```

Example role-level configuration:

```sql
ALTER ROLE api_user
SET idle_in_transaction_session_timeout = '60s';
```

### 26.1. This Is Session Termination

Unlike `statement_timeout`, this setting terminates the session when it remains idle in transaction beyond the threshold. The client must handle connection loss and transaction rollback.

### 26.2. Preventing Abandoned Transactions

Useful when an application has bugs that fail to roll back or commit after a request.

### 26.3. Choosing a Threshold

Do not set it too low if legitimate applications have think time within a transaction. Designing short transactions is generally better.

### 26.4. Monitor Logs

Track timed-out sessions and service owners to fix connection and transaction lifecycles.

## 27. idle_session_timeout and Connection Pools

`idle_session_timeout` can terminate sessions that sit idle outside a transaction. However, poolers or applications may expect idle connections to remain alive for reuse.

### 27.1. Impact on Pools

If the server timeout is shorter than the pool's connection lifetime or health checks, clients may encounter stale connections or reconnect churn.

### 27.2. Do Not Enable Arbitrarily

Evaluate pool behavior, keepalives, health checks, and session reuse before enabling it.

### 27.3. Difference from Idle in Transaction

An idle session without an open transaction is usually far less dangerous than `idle in transaction`, though it still consumes a connection slot.

### 27.4. Role-Specific Policy

It can be applied differently for interactive users, API pools, and reporting jobs.

## 28. Timeout Precedence and Transaction Handling

A query can be governed by multiple deadlines:
- Application request timeout.
- Connection pool acquire timeout.
- Statement timeout.
- Lock timeout.
- Transaction/session idle timeout.
- Proxy/network timeout.

### 28.1. Lock Timeout

Applies to the duration a statement waits for locks.

### 28.2. Statement Timeout

Applies to statement execution duration, including wait time.

### 28.3. Application Deadlines

May abort the request without necessarily canceling the backend automatically. The driver must send a cancel or close the connection according to tested behavior.

### 28.4. Synchronizing Budgets

Design timeouts in a clear order with margins so the database does not continue running queries long after the client gave up on the request.

## 29. Impact on Connection Pools

Canceling and terminating affect connection pools differently.

### 29.1. After Cancel

The connection can continue to be used if the driver confirms the backend/session is healthy and transaction state is handled. In an explicit transaction, ROLLBACK is needed.

### 29.2. After Terminate

The connection is closed; the pool must discard it and open a new connection. Connection churn can increase.

### 29.3. Pool Reset

If session state includes SET commands, temp tables, or prepared statements, the pool reset policy must match. Never reuse a terminated connection.

### 29.4. Retry Storms

Many clients receiving cancellation or connection errors simultaneously can retry all at once. Use exponential backoff, jitter, idempotency, and retry budgets.

## 30. Impact on Applications and Business Operations

Before terminating, determine what the query is doing:
- Payments or balance updates.
- Order creation.
- Batch imports.
- Migrations.
- Reporting.
- Cleanup jobs.
- Interactive user queries.

### 30.1. Financial Transactions

If the transaction is uncommitted, termination rolls back the uncommitted database portion. If the commit outcome is uncertain to the client, check the idempotency key or business reference.

### 30.2. Batch Jobs

Cancellation can halt a job mid-batch. Identify checkpoints and resume/idempotency capabilities.

### 30.3. Reporting

A report can usually be retried more safely than a write transaction, yet it may still hold snapshots/locks or consume significant I/O.

### 30.4. External Side Effects

If a function or extension calls an API, sends a message, or writes a file, PostgreSQL rollback does not automatically revert side effects outside the database.

## 31. Impact on WAL, Vacuum, and Storage

Query cancellation does not erase WAL already generated earlier.

### 31.1. Partially Executed DML

In a rolled-back transaction, uncommitted changes do not become visible data. WAL already written remains part of physical history; PostgreSQL does not delete WAL records merely because a transaction aborts.

### 31.2. Dead Tuples

Tuples created by an aborted transaction may require vacuum cleanup afterward. Monitor dead tuples and autovacuum if the workload is large.

### 31.3. Replication

WAL from aborted transactions may still be processed by physical replication and recovery. Logical replication does not emit a rolled-back transaction as a committed change set.

### 31.4. Do Not Use Terminate to Shrink the WAL Directory

Terminating backends is not a method to clear WAL or slot retention. Investigate the root cause of WAL growth separately.

## 32. Impact on Replication and Background Processes

A backend appearing in `pg_stat_activity` may be a WAL sender, logical replication worker, or background worker.

### 32.1. Do Not Terminate Replication Processes Arbitrarily

Terminating a walsender/receiver or logical apply worker can cause replication disconnects, lag, WAL retention, and impact HA or CDC.

### 32.2. Use the Proper Runbook

If replication is degraded, check `pg_stat_replication`, `pg_stat_wal_receiver`, `pg_stat_subscription`, and logs. Use proper replication administration procedures.

### 32.3. Autovacuum

Never reflexively cancel autovacuum to free CPU. Understand table bloat and XID age first.

### 32.4. Background Workers

Only intervene when you know which extension or service owns the worker and have an official stop/restart procedure.

## 33. Permissions, RLS, and Query Information

Permissions to read statistics and permissions to signal backends are two separate concerns.

### 33.1. Reading pg_stat_activity

A role may see partial information while being unable to view query text or details of other sessions without proper stats privileges.

### 33.2. Signal Privileges

`pg_signal_backend` allows signaling backends within its documented privilege scope. It does not grant superuser privileges.

### 33.3. RLS Does Not Govern pg_stat_activity

Row-level security on application tables does not replace process administration permissions. Protect monitoring and admin roles separately.

### 33.4. Query Text May Be Sensitive

Do not copy raw query text containing literals, PII, or secrets into public incident tickets. Redact before sharing.

## 34. Auditing Cancel and Terminate Actions

Every intervention should record:
- Timestamp.
- Operator or automation identity.
- Cluster and database.
- PID and `backend_start`.
- User, `application_name`, and client.
- Redacted query/transaction context.
- Reason and incident/change ID.
- Action taken: cancel or terminate.
- Function result.
- Post-action state.
- Locks, latency, and error impact.
- Owner notification per procedure.

### 34.1. PostgreSQL Logs

Configure `log_line_prefix` with PID, user, database, `application_name`, and timestamp to correlate logs. `log_min_error_statement` and `log_lock_waits` assist investigation per policy.

### 34.2. Admin Audit

Do not assume every administrative function call is fully logged in server logs under default settings. Record audits in operational tooling or an approved auditing mechanism.

### 34.3. Avoid Overly Broad Logging

Logging all statements and parameters can spike volume and expose sensitive literals. Collect only necessary context.

### 34.4. Before/After Evidence

Save a pre-action snapshot and post-action verification. This helps evaluate effectiveness and investigate unexpected impacts.

## 35. Decision Workflow: Cancel or Terminate?

A decision tree:

```text
1. Is the target a client backend?
       |
       +-- No -> Use owner-specific runbook
       |
       +-- Yes
             |
2. Is a query currently active?
       |
       +-- Yes
       |     |
       |     +-- Query itself is harmful?
       |            |
       |            +-- Yes -> Consider CANCEL
       |            |
       |            +-- No  -> Find blocker/resource cause
       |
       +-- No
             |
3. Is session idle in open transaction?
       |
       +-- Yes -> Ask/allow rollback; terminate if policy requires
       |
       +-- No -> Check pool/connection ownership
             
4. After CANCEL:
       |
       +-- Query stopped and transaction closed -> Verify
       |
       +-- Transaction aborted but still open -> ROLLBACK or TERMINATE
```

### 35.1. Cancel Is the First Step for an Active Statement

If a specific query is causing harm, cancellation usually has a smaller blast radius.

### 35.2. Terminate When the Session Is the Problem

Sessions idle in transaction, refusing to roll back, or unable to perform cleanup may require termination.

### 35.3. Coordinate with Owners When Business Impact Is High

Migrations, large write batches, or critical transactions require clear owners and runbooks.

### 35.4. Have a Stop Condition

If the PID, owner, or transaction cannot be identified or commit state is unclear, do not take broad action. Gather more evidence first.

## 36. Runbook: Canceling a Long-Running Query

1. Record the incident ID and user impact.
2. Capture a `pg_stat_activity` snapshot.
3. Verify PID, `backend_start`, database, user, and `application_name`.
4. Inspect `query_start`, `xact_start`, `wait_event`, and redacted query text.
5. Check `pg_blocking_pids` to distinguish a slow query from a blocked query.
6. Confirm whether the query is an authorized batch, report, or migration.
7. Notify the owner per policy.
8. Call `pg_cancel_backend` for the confirmed PID.
9. Check the function return value and refresh `pg_stat_activity`.
10. If the session remains in an aborted explicit transaction, request a client rollback.
11. If the session keeps holding locks without cleaning up, evaluate termination.
12. Verify waiters, API latency, error rates, and pool health.
13. Document actions, results, and corrective actions.

### 36.1. Do Not Judge by Query Age Alone

A 10-minute query might be normal; a 2-second query might block a critical write path. Prioritize impact.

### 36.2. Monitor the Query After Cancel

If the query remains active, the signal may not yet be processed or the PID/state changed. Re-inspect before repeating the action.

### 36.3. Application Retries

Confirm retries will not produce duplicate writes or a retry storm.

## 37. Runbook: Idle-in-Transaction Blocker

1. Find sessions in `idle in transaction` and check their age.
2. Inspect `application_name`, user, `client_addr`, and `xact_start`.
3. Identify locks and blocked sessions using `pg_blocking_pids`.
4. Locate the root blocker and transaction owner.
5. Contact the application/service owner per the incident process.
6. If the client can roll back quickly, request cleanup.
7. If not, and impact exceeds thresholds, terminate the verified session.
8. Confirm the backend disappears and waiters make progress.
9. Check for transaction rollback or commit ambiguity.
10. Monitor vacuum, dead tuples, and pool reconnects.
11. Fix the application transaction lifecycle and add timeout guardrails.

### 37.1. Why Isn't Cancel Enough?

An idle session has no active query; the problem is the open transaction. Termination or client rollback is needed to end the transaction.

### 37.2. Do Not Terminate the Entire Application

Target only verified PIDs. Terminating every session of a service can cause a widespread outage.

## 38. Runbook: Cancel Does Not Resolve Lock Contention

1. Capture the blocked/blocker mapping.
2. Identify the root blocker.
3. Check whether the blocker is active or idle in transaction.
4. Inspect blocker transaction age and business operation.
5. Check for DDL, migrations, or maintenance.
6. If there is an active harmful query, cancel the blocker query.
7. Inspect transaction state and locks.
8. If the transaction remains open, request rollback or terminate per policy.
9. Confirm blocked sessions proceed.
10. Reduce retries or concurrency if queues keep growing.
11. Fix lock ordering, transaction duration, or migration strategy.

## 39. Runbook: Connection Terminated and Client Unsure of COMMIT Outcome

1. Record the request or business operation ID.
2. Check application logs around the COMMIT timestamp.
3. Identify the server, backend, and incident timeline.
4. Check connection termination logs.
5. On the current primary, query the idempotency or deduplication record.
6. If the record exists, return the committed outcome.
7. If it does not exist, evaluate retrying based on business semantics.
8. Reuse the same idempotency key when retrying.
9. Check external side effects and outbox records.
10. Record the reconciliation result and notify the client or service owner.

### 39.1. Do Not Blindly Retry Non-Idempotent Writes

A client connection error does not prove the transaction rolled back.

### 39.2. Use a Durable Business Key

A unique operation key makes it possible to determine whether the operation committed.

### 39.3. Failover Adds a Timeline Dimension

If termination coincided with a failover, verify whether the transaction exists on the promoted primary and ensure history has been reconciled.

## 40. Designing Default Timeouts by Workload

Illustrative policy example:

| Workload | statement_timeout | lock_timeout | Notes |
|---|---:|---:|---|
| OLTP read | 2–5 s | 500 ms–1 s | Low-latency endpoints |
| OLTP write | 5–15 s | 1–2 s | Aligned with business transactions |
| Reporting | 1–5 min | 2–5 s | Dedicated pool/concurrency |
| Batch | Per job SLA | Per migration/job | Includes checkpoint/resume |
| DDL migration | Per operation | Usually short to fail fast | Dedicated lock plan |

These are illustrative values, not universal defaults suitable for every system.

### 40.1. Set by Role or Transaction

Role-specific defaults help isolate workloads. `SET LOCAL` fits requests or jobs with custom budgets.

### 40.2. Consider Application Timeouts

Application deadlines should align with database timeouts to avoid clients abandoning requests while the server keeps executing.

### 40.3. Retry Policy

Timeouts and retries need backoff, jitter, maximum attempts, and idempotency.

### 40.4. Review Against Metrics

Tune based on timeout rate, p95/p99 latency, lock waits, and business completion rates.

## 41. Monitoring Cancellation and Termination

Collect:
- Query cancellation counts over time.
- Session termination counts over time.
- Cancellations/terminations by `application_name` or workload class.
- SQLSTATE 57014 counts.
- Connection failures and reconnect rates.
- Idle-in-transaction session counts and ages.
- Lock waiters and blocker age.
- Query timeout rate.
- Transaction rollback/error rate.
- Pool acquire wait times and connection churn.
- Request retry rate and idempotency conflicts.

### 41.1. Not All Counters Exist in Built-In Views

Some events must be collected from applications, logs, or an audit layer. Do not assume `pg_stat_database` holds aggregate counters for all backend cancellations.

### 41.2. High Cancellation Rate

May indicate overly aggressive timeouts, query regressions, lock contention, or flawed retry behavior.

### 41.3. High Termination Rate

May reflect application transaction leaks, broken session management, or operational processes requiring frequent manual intervention.

### 41.4. Track User Impact

Place cancel/terminate counts alongside request success rates, latency, TPS, and pool metrics.

## 42. Logging to Support Investigation

Relevant configuration and logging settings:
- `log_line_prefix`.
- `log_min_duration_statement`.
- `log_min_error_statement`.
- `log_lock_waits`.
- `deadlock_timeout`.
- `application_name`.

### 42.1. log_line_prefix

Should include PID, user, database, `application_name`, client address, and timestamp per policy to correlate logs with `pg_stat_activity`.

### 42.2. log_lock_waits

Logs lock waits exceeding `deadlock_timeout` as configured, helpful for diagnosing prolonged contention.

### 42.3. Slow Statement Logs

`log_min_duration_statement` records queries exceeding a threshold. Set thresholds by workload and protect query text.

### 42.4. Do Not Enable log_statement = all Arbitrarily

Logging every statement can spike log volume and expose literals/secrets. Use targeted logging levels.

## 43. Situations Where You Should Not Terminate Immediately

- The PID belongs to a superuser/DBA actively resolving an incident.
- The backend is an autovacuum or replication process not yet understood.
- The query is a migration holding a lock that is nearly complete and part of a plan.
- A critical write transaction where termination could create commit ambiguity.
- The owner or application has not been identified.
- The PID came from a stale snapshot.
- It has not been verified as the root blocker.
- Rollback impact or external side effects have not been assessed.
- The session is performing maintenance requiring progress/cleanup.
- Risk of mass termination triggering a connection pool reconnect storm.

### 43.1. Pause to Gather Evidence

Taking a minute to check the PID, owner, and transaction state can prevent a larger outage.

### 43.2. Use Cancel When Appropriate

If only a statement needs to stop, cancel generally carries a smaller blast radius than terminate.

### 43.3. Terminate Intentionally

Document the reason, target, expected rollback, and verification method.

## 44. Common Operational Mistakes

1. **Canceling a query while forgetting the transaction remains aborted.** The client must roll back.
2. **Canceling an idle-in-transaction session.** There is no active query; the transaction stays open.
3. **Assuming cancel always releases locks.** Transaction-level locks may remain until rollback.
4. **Terminating the wrong PID from an old dashboard.** The PID may have exited or been reused.
5. **Targeting a waiter instead of the blocker.** Lock contention remains unresolved.
6. **Terminating all sessions of an application.** Too broad a blast radius.
7. **Failing to verify the query stopped.** Boolean true only reports that the signal was sent.
8. **Retrying immediately after cancellation.** Can cause a retry storm.
9. **Ignoring commit ambiguity.** Can cause duplicate business operations.
10. **Ignoring external side effects.** Database rollback does not undo external systems.
11. **Terminating a replication worker.** Can spike replication lag and WAL retention.
12. **Killing autovacuum to reduce CPU.** Can worsen bloat and XID wraparound risk.
13. **Omitting `statement_timeout`.** Runaway queries can keep recurring.
14. **Using `lock_timeout` as a total query timeout.** It only limits lock waiting.
15. **Setting `idle_session_timeout` too low with pools.** Creates connection churn.
16. **Failing to audit admin actions.** Makes incident review and accountability difficult.
17. **Failing to redact query text.** Can leak sensitive data.
18. **Not checking index validity after canceling a concurrent index build.** Can leave an invalid index behind.
19. **Not monitoring pool health after termination.** The application may continue failing.
20. **Treating termination as a way to clean up WAL.** It does not resolve slot or archive retention.

## 45. Practical Example: Investigating a Blocker

Suppose the orders API experiences rising latency. Many requests are waiting on `Lock`.

Step 1: Find waiters.

```sql
SELECT
    pid,
    application_name,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Step 2: Inspect blocker sessions and transaction age.

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS xact_age,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE pid = 12345;
```

Step 3: Determine whether the blocker is active or idle in transaction. If active, consider canceling the statement. If idle in transaction, coordinate application rollback or terminate per incident policy.

Step 4: Verify:
- Has the backend exited or rolled back?
- Are blocked sessions making progress?
- Have API p95 latency and error rates recovered?
- Is the pool experiencing a reconnect storm?
- Are there batches or jobs needing resumption?

Never select an action based on a single query age number alone.

## 46. Practical Example: Canceling a Reporting Query

A reporting query is performing an external sort of 30 GB of temp data, nearly filling a volume shared with OLTP.

1. Identify the PID, `application_name`, and owner.
2. Check temp filesystem free space and query plan/logs.
3. Determine whether the query can be restarted or resumed.
4. Check whether it is inside an explicit transaction.
5. Notify the owner and record incident context.
6. Send `pg_cancel_backend`.
7. Verify the statement stops and check transaction state.
8. If the session is aborted/`idle in transaction`, request rollback.
9. Verify temp files are cleaned up and disk headroom recovers.
10. Limit reporting concurrency and fix the query or job.

### 46.1. Temp File Cleanup

Temporary files associated with a query are normally cleaned up when the executor/backend handles termination properly. Verify the filesystem and logs; never manually delete files inside `pgsql_tmp` while the server is running.

### 46.2. If Cancel Does Not Stop It

Re-inspect the process/state instead of sending repeated signals indefinitely. If the session continues causing harm, consider controlled termination.

### 46.3. Post-Incident

Set job concurrency limits, statement timeouts/temp capacity limits, and a query optimization plan.

## 47. Practice Exercises with Answers

### Exercise 1. What does pg_cancel_backend do?

**Answer:** Sends a signal requesting the backend to cancel its currently running query.

### Exercise 2. What does pg_terminate_backend do?

**Answer:** Sends a signal terminating the backend session, closing the connection and rolling back uncommitted transactions when the backend exits.

### Exercise 3. Does cancel close the connection?

**Answer:** Normally no. The connection can continue to be used after the transaction state is handled.

### Exercise 4. Does terminate keep the connection open?

**Answer:** No. The backend session exits and the connection is closed.

### Exercise 5. Does a boolean true from pg_cancel_backend mean the query has stopped?

**Answer:** No. It indicates the cancel signal was sent; you must re-check the backend.

### Exercise 6. What is the common SQLSTATE when a query is canceled?

**Answer:** 57014, query_canceled.

### Exercise 7. What can query cancellation inside an explicit transaction cause?

**Answer:** The transaction moves to the aborted state and requires ROLLBACK or handling via a savepoint.

### Exercise 8. What does error 25P02 mean?

**Answer:** Current transaction is aborted; commands are ignored until the end of the transaction block.

### Exercise 9. Does canceling a query always release transaction locks?

**Answer:** No. Locks may persist until the transaction rolls back or ends.

### Exercise 10. Does an idle in transaction session have an active query?

**Answer:** Not necessarily. The session is waiting on the client while the transaction remains open.

### Exercise 11. Does pg_cancel_backend resolve idle in transaction?

**Answer:** There is no active statement to cancel; client rollback or policy-based termination is required.

### Exercise 12. When does terminating a session release locks?

**Answer:** When the backend/transaction exits and cleanup completes.

### Exercise 13. Are transactions committed before termination rolled back?

**Answer:** No. Only the uncommitted work of the session is rolled back.

### Exercise 14. Does a client losing connection during COMMIT know the outcome for sure?

**Answer:** No. Commit outcome can be ambiguous; reconcile using an idempotency or business key.

### Exercise 15. What is pg_stat_activity used for?

**Answer:** Observing backend sessions, queries, states, transaction ages, and wait events.

### Exercise 16. How do query_start and xact_start differ?

**Answer:** `query_start` is when the current statement began; `xact_start` is when the transaction began.

### Exercise 17. What does wait_event_type = Lock suggest?

**Answer:** The backend is waiting on a lock, and you need to find the blocker.

### Exercise 18. What is pg_blocking_pids used for?

**Answer:** Returns the PIDs of sessions blocking the specified backend.

### Exercise 19. Why should you cancel the blocker instead of a waiter?

**Answer:** The waiter is merely a victim; the blocker holds the lock affecting many sessions.

### Exercise 20. How do you handle a blocker that is idle in transaction?

**Answer:** Request a client rollback or terminate the session after verifying the owner and impact.

### Exercise 21. Can a backend PID be reused?

**Answer:** Yes. Re-verify the PID together with `backend_start`, application, and user before acting.

### Exercise 22. Why exclude pg_backend_pid()?

**Answer:** To avoid sending a signal to the very session running the administrative command.

### Exercise 23. Which role supports signaling backends under granted privileges?

**Answer:** The predefined role `pg_signal_backend`, within the bounds of non-superuser restrictions.

### Exercise 24. Can pg_signal_backend signal a superuser backend?

**Answer:** No; only a superuser may signal backends owned by a superuser.

### Exercise 25. Why might query cancellation take effect slowly?

**Answer:** The backend processes signals at interrupt points; it may not reach a checkpoint immediately.

### Exercise 26. Is terminating a single parallel worker standard practice?

**Answer:** No. Identify the client/leader session owning the query and follow the appropriate runbook.

### Exercise 27. What can a canceled CREATE INDEX CONCURRENTLY leave behind?

**Answer:** It can leave an invalid index; check `pg_index.indisvalid`/`indisready`.

### Exercise 28. Should you terminate autovacuum to reduce CPU?

**Answer:** Not reflexively; assess table health, XID age, and maintenance impact first.

### Exercise 29. What does statement_timeout limit?

**Answer:** Total statement execution time, including time spent waiting on locks.

### Exercise 30. What does lock_timeout limit?

**Answer:** How long a statement waits to acquire a lock.

### Exercise 31. Does lock_timeout replace statement_timeout?

**Answer:** No. It does not limit query execution after the lock is acquired.

### Exercise 32. What does idle_in_transaction_session_timeout do?

**Answer:** Terminates sessions idle in a transaction beyond the threshold, freeing transaction resources.

### Exercise 33. Does idle_session_timeout carry risk for pools?

**Answer:** Yes. It can cause stale connections and connection churn if the pool does not coordinate timeouts.

### Exercise 34. What is the scope of SET LOCAL?

**Answer:** The current transaction; it automatically expires upon COMMIT or ROLLBACK.

### Exercise 35. Is the pg_terminate_backend timeout argument available in all versions?

**Answer:** No. The timeout overload only exists in supported versions; check the function signature first.

### Exercise 36. Does termination roll back external HTTP requests?

**Answer:** No. Side effects outside the database do not automatically roll back with the transaction.

### Exercise 37. Can canceling a partially written DML query leave partially committed data?

**Answer:** Within an atomic statement transaction, canceling the statement rolls back uncommitted changes; external side effects still must be reviewed separately.

### Exercise 38. Does cancel erase already-written WAL?

**Answer:** No. WAL records already written are not deleted just because a transaction aborts.

### Exercise 39. Why monitor the pool after termination?

**Answer:** The pool must discard and reconnect connections; many terminations can trigger a connection storm.

### Exercise 40. Why avoid retrying immediately after cancellation?

**Answer:** It can trigger a retry storm and repeat the underlying lock or resource contention.

### Exercise 41. Must a query with a 10-minute age always be canceled?

**Answer:** No. Consider workload class, owner, wait events, and user impact.

### Exercise 42. When is terminate more appropriate than cancel?

**Answer:** When the session does not roll back, is idle in transaction holding locks, or the entire session must be ended per policy.

### Exercise 43. What should be audited when terminating?

**Answer:** Operator, PID/backend identity, owner, reason, incident ID, action result, and subsequent impact.

### Exercise 44. Does pg_stat_activity show all query text to every user?

**Answer:** No. Statistics privileges can restrict detailed information.

### Exercise 45. How does log_lock_waits help?

**Answer:** Logs lock waits exceeding the configured threshold, aiding contention investigations.

### Exercise 46. Can canceling a reporting query affect temp files?

**Answer:** Yes. A query's temporary files are typically cleaned up when the executor/backend handles exit; verify disk state.

### Exercise 47. If a session ends up in idle in transaction (aborted) after cancel, what is the next step?

**Answer:** Ask the client to ROLLBACK; if it does not clean up and keeps causing harm, evaluate termination.

### Exercise 48. How do you resolve commit ambiguity after connection loss?

**Answer:** Look up the idempotency or business operation key on the current primary, reconcile, and only then decide whether to retry.

### Exercise 49. What should a cancellation dashboard include?

**Answer:** Cancel/terminate counts, SQLSTATE 57014, connection failures, idle transaction age, lock waiters, pool waits, retries, and user latency.

### Exercise 50. When is an incident considered resolved?

**Answer:** The target query/session is handled, locks are released, the application/pool is stable, latency/errors have recovered, and the action is audited.

## 48. Pre- and Post-Intervention Checklist

| Stage | Question |
|---|---|
| Target | Is the PID the right backend and still active? |
| Identity | Are user, database, `application_name`, and `client_addr` accurate? |
| State | Is it active, idle, idle in transaction, or aborted? |
| Age | What are the query age and transaction age? |
| Wait | Is it waiting on Lock, IO, or another resource? |
| Blocking | Is this a blocker or a waiter? |
| Owner | Who owns the service, job, or migration? |
| Business | Are there critical transactions or external side effects? |
| Action | Cancel the statement or terminate the session? |
| Permission | Does the role have privilege to signal this backend? |
| Transaction | Is ROLLBACK needed after cancel? |
| Locks | Have blocked sessions resumed making progress? |
| Pool | Were connections evicted/reconnected properly? |
| Retry | Are backoff and idempotency in place? |
| Logs | Have SQLSTATE, PID, and incident context been saved? |
| DDL | Do index or migration states need verification? |
| Replication | Were any workers, slots, or replicas inadvertently affected? |
| Impact | Have latency, errors, TPS, and pool wait recovered? |
| Audit | Have operator, reason, and outcome been logged? |
| Prevention | Do timeouts or transaction lifecycles need fixing? |
| Closure | Have business operations and commit outcomes been reconciled? |

## 49. Official PostgreSQL Documentation

- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — `pg_cancel_backend`, `pg_terminate_backend`, and backend signaling.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — `pg_stat_activity` and activity monitoring.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — session state, wait events, and statistics views.
- [Predefined Roles](https://www.postgresql.org/docs/current/predefined-roles.html) — `pg_signal_backend` and monitoring roles.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) — `statement_timeout`, `lock_timeout`, and idle transaction/session timeouts.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes and lock lifetime.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — transaction behavior and snapshots.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — concurrent index build behavior and invalid indexes.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — progress views for vacuum/index operations.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — SQLSTATE 57014 and transaction errors.

Function signatures, `pg_stat_activity` columns, timeout parameters, and progress views may vary across PostgreSQL major versions. Before standardizing runbooks, check `server_version`, function signatures, `pg_settings`, and the documentation for your exact running version.

## 50. Summary: Identify the Right Backend, Choose the Right Signal, Verify the Impact

```text
pg_stat_activity
    |
    v
Identify PID + owner + state + query + xact age
    |
    v
Find blockers / wait events / business impact
    |
    +------------------------------+
    |                              |
    v                              v
Active harmful query         Idle in transaction
    |                              |
    v                              v
pg_cancel_backend           Client ROLLBACK
    |                       or controlled terminate
    v                              |
Check query stopped                |
    |                              |
    v                              v
Check transaction state and lock release
    |
    v
Verify application, pool, latency, errors and audit
```

Principles to remember:

1. **`pg_cancel_backend` cancels a statement; `pg_terminate_backend` ends a session.** The two actions carry different blast radii.
2. **Boolean true does not prove the query or session finished cleanup.** Re-check `pg_stat_activity` and logs.
3. **Canceling inside an explicit transaction can leave the transaction aborted.** The client must issue ROLLBACK.
4. **Locks may persist after query cancellation.** The transaction must end before transaction-level locks are released.
5. **Idle in transaction has no active query to cancel.** Handle the transaction/session according to owner and policy.
6. **Terminate rolls back uncommitted work and closes the connection.** The client must reconnect and may need to reconcile commit outcomes.
7. **Identify the blocker before canceling waiters.** Addressing the root cause restores many requests at once.
8. **Verify the PID immediately before taking action.** Combine `backend_start`, `application_name`, user, and database.
9. **Do not reflexively terminate background, replication, or maintenance processes.** Use dedicated runbooks.
10. **Timeouts prevent incidents better than repeated manual intervention.** Choose `statement_timeout`, `lock_timeout`, and idle transaction timeouts by workload.
11. **Retries must include backoff and idempotency.** Avoid duplicate operations or retry storms.
12. **Auditing and post-action verification are mandatory in operations.** Evaluate locks, pools, latency, errors, and business outcomes.

**One sentence to remember:** *Cancel a query to stop a single statement; terminate a session to stop the entire backend and its uncommitted transaction; before choosing, identify the blocker, transaction state, and consequences for the application.*
