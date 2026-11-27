# Connection, Query, Network Timeouts and Statement Cancellation in PostgreSQL

## 1. Why Is “Database Timeout” Not a Single Setting?

A Java API calls PostgreSQL to retrieve a list of orders. Normally the query takes 80 ms, but today the request hangs for 30 seconds and then returns HTTP 504. The operator asks:

- Did the application **fail to acquire a connection from the pool**?
- Were DNS, TCP, TLS, or PostgreSQL authentication slow?
- Was a connection acquired, but the SQL statement is waiting on a row lock?
- Is the SQL scanning millions of rows and blocked by `statement_timeout`?
- Did the server finish processing, but the client lost the connection or failed to receive the response?
- When the user closed the browser, was the query in PostgreSQL **canceled**?
- If the driver reported a timeout, did the preceding `COMMIT` definitely fail?

Each question relates to **a different timer and a different error-handling mechanism**.

```text
HTTP request / background job
        |
        v
[1] Waiting for a connection from pool -> pool connectionTimeout
        |
        v
[2] Creating physical connection       -> loginTimeout / connectTimeout
    DNS -> TCP -> TLS -> auth             + network/proxy budgets
        |
        v
[3] Sending SQL / waiting for result   -> statement_timeout (server)
    + waiting for lock                 -> lock_timeout (server)
    + JDBC queryTimeout                -> Statement.setQueryTimeout
    + reading socket                   -> socketTimeout / networkTimeout
        |
        v
[4] Receiving rows, processing, COMMIT -> transaction budget / request deadline
        |
        v
[5] Returning response / returning to pool -> HTTP deadline, connection cleanup

Outside the request:
- idle_in_transaction_session_timeout: session sitting idle inside a transaction
- idle_session_timeout: session sitting idle outside a transaction
- transaction_timeout (PG 17+): limit on transaction lifetime
- pg_cancel_backend / Statement.cancel: request to cancel the current SQL statement
- pg_terminate_backend: terminate the backend/session
```

**Key message:** configure timeouts layer by layer to achieve a predictable processing deadline; distinguish between **canceling a statement** and **closing a connection**; and never automatically retry write operations without knowing whether the transaction committed.

## 2. Learning Objectives

After this lesson, you can:

1. Distinguish between pool checkout timeout, connection establishment timeout, query timeout, socket/read timeout, and request deadline.
2. Understand the roles of pgJDBC `connectTimeout`, `loginTimeout`, `socketTimeout`, `cancelSignalTimeout`, and `tcpKeepAlive`.
3. Understand that `HikariCP connectionTimeout` is not PostgreSQL `statement_timeout`.
4. Use `Statement.setQueryTimeout(int seconds)` and `Statement.cancel()` in JDBC.
5. Set PostgreSQL `statement_timeout` and `lock_timeout` per role, session, or transaction.
6. Understand `idle_in_transaction_session_timeout`, `idle_session_timeout`, and `transaction_timeout` (PostgreSQL 17+).
7. Understand `SET LOCAL`, `SET`, `ALTER ROLE ... SET`, and their effects on a connection pool.
8. Practice canceling a query using `pg_sleep`.
9. Practice waiting for a row lock and triggering a `lock_timeout` error using two sessions.
10. Understand the separate cancel request mechanism and how it differs from `pg_terminate_backend`.
11. Distinguish a server-side `SQLSTATE 57014` result from a network failure/connection error.
12. Understand that a transaction enters the **aborted** state after a statement error and how to `ROLLBACK` properly.
13. Recognize an **uncertain** write outcome when the client loses connection near the `COMMIT` boundary.
14. Design retries using idempotency keys, SQLSTATE, deadlines, and backoff.
15. Use `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks` to investigate waiting queries.
16. Configure reasonable pool/JDBC timeouts for HTTP APIs and background jobs.
17. Avoid keeping a transaction open while waiting on the network or user actions.
18. Distinguish TCP keepalive, pool keepalive, and query timeout.
19. Understand the impact of proxies/load balancers/PgBouncer on timeouts.
20. Test scenarios for cancellation, lock timeout, backend termination, socket failure, and recovery.

## 3. Map of Timeout Types

| Layer | Example Mechanism | What Time Does It Measure? | Common Outcome |
| --- | --- | --- | --- |
| HTTP/gRPC | Request deadline | Total request time | Client receives timeout; SQL has **not necessarily** stopped |
| Connection pool | HikariCP `connectionTimeout` | Waiting to acquire a connection from the pool | Application fails to obtain a connection |
| Driver | pgJDBC `connectTimeout` | Waiting for socket connect | Physical connection cannot be established |
| Driver | pgJDBC `loginTimeout` | Driver-managed connection/login establishment | Establishment fails after exceeding limit |
| Driver | pgJDBC `socketTimeout` | A single socket **read** waiting too long for data | Read timeout; connection may be broken |
| JDBC | `Statement.setQueryTimeout` | Driver-managed statement execution time | Driver sends cancel request; SQLException |
| JDBC | `Statement.cancel` | Actively requesting statement cancellation | SQL statement may be canceled |
| PostgreSQL | `statement_timeout` | Statement execution on the server | Query canceled error |
| PostgreSQL | `lock_timeout` | Waiting to acquire each lock | Lock acquisition error |
| PostgreSQL | `idle_in_transaction_session_timeout` | Session idle while transaction remains open | Backend/session is terminated |
| PostgreSQL | `idle_session_timeout` | Session idle outside a transaction | Backend/session is terminated |
| PostgreSQL 17+ | `transaction_timeout` | Transaction lifetime | Backend/session is terminated on expiration |
| Network/OS | TCP keepalive, proxy idle timeout | TCP connection liveness or idleness | Connection drop/detection; not an SQL deadline |

Each timeout has its own **scope, unit, starting point, and consequence**. Never copy a number like `5000` into every setting and assume it means 5 seconds.

### 3.1. A Request Can Cross Multiple Thresholds

For example, a web request has an 8-second deadline, pool checkout has a 1-second limit, SQL has a 5-second server-side timeout, and socket read timeout is 12 seconds. This configuration only makes sense when the application **propagates and enforces the deadline** across steps; you cannot simply add or subtract numbers while ignoring cancellation or time spent outside SQL.

### 3.2. A Timeout Is Not a Guarantee of Millisecond-Exact Handling

A timeout may be checked by an event loop, signal, interrupt cycle, scheduler, or network I/O. When the system is overloaded, the moment the callback or error surfaces may be later than the configured threshold.

### 3.3. Timeouts Can Occur Concurrently

A query can be simultaneously waiting on a lock and exceeding `statement_timeout` while the HTTP client has already closed its connection. Which error appears first depends on timing and the corresponding mechanism. Investigation must examine **which timer actually expired**.

## 4. Distinguishing “Waiting on the Pool” from “Connecting to PostgreSQL”

Imagine HikariCP has 10 physical connections and all 10 are in use. The 11th request calls:

```java
Connection conn = dataSource.getConnection();
```

It may have to wait for a connection to be returned to the pool, even though PostgreSQL and the network are healthy.

### 4.1. HikariCP `connectionTimeout`

This is the maximum time a client waits to **acquire a connection from the pool**. If the limit is exceeded, `getConnection()` may throw an `SQLException`.

This **does not mean** PostgreSQL ran a query for too long, or that PostgreSQL `statement_timeout` occurred.

### 4.2. Causes of Pool Exhaustion

- Connection leak: failing to close/return connections.
- Transactions holding connections open for too long.
- Slow queries/lock waits.
- Pool too small for legitimate concurrency.
- Downstream network calls causing some connections to be held.
- Background jobs sharing the same pool as HTTP traffic.
- Physical connections being created too slowly or backend limits reached.

### 4.3. Do Not Just Increase `maximumPoolSize`

Growing the pool without limit can create extra backend processes, memory usage, context switching, and contention in PostgreSQL. Investigate held queries and transactions before increasing connection counts.

### 4.4. Another Scenario: The Pool Has Slots, but the Server Rejects New Connections

When a physical connection needs to be created, PostgreSQL might refuse it due to `max_connections`, invalid credentials, TLS, network issues, or authentication. In that case, driver `connectTimeout`/`loginTimeout` and server errors are what matter.

## 5. Driver Connect Timeout and Login Timeout

pgJDBC has several connection properties. The names below belong to the **PostgreSQL JDBC Driver**; not all JDBC drivers share the exact same property names.

### 5.1. `connectTimeout`

Controls the wait time for the **socket connect** operation when establishing a connection to PostgreSQL. The unit in pgJDBC is **seconds**.

```text
connectTimeout=3
```

Do not assume this property strictly covers all DNS time, TLS/auth time, multi-host failover, and application-wide retries.

### 5.2. `loginTimeout`

Limits the wait time for connection/login establishment under the driver's mechanism. It differs from waiting only on TCP connect; it is also configured in **seconds** in pgJDBC.

### 5.3. Connecting to Multiple Hosts

With a JDBC URL containing multiple PostgreSQL hosts, host selection/failover may involve multiple connect attempts. The total time observed by the application can exceed the socket timeout of a single host. Never build an SLO assuming “`connectTimeout=3` means every case returns an error in under 3 seconds.”

### 5.4. A Successful Connection Can Still Have a Query Timeout

Once authentication finishes, `connectTimeout` has completed its job. A slow `SELECT` is not bounded by `connectTimeout`.

### 5.5. Example JDBC URL for a Lab Environment

```text
jdbc:postgresql://localhost:5432/appdb?connectTimeout=3&loginTimeout=5&socketTimeout=15&cancelSignalTimeout=5&tcpKeepAlive=true&ApplicationName=orders-api
```

Notes:

- Replace `appdb` and the host with values for your actual environment.
- `connectTimeout=3`, `loginTimeout=5`, `socketTimeout=15`, and `cancelSignalTimeout=5` are in **seconds**.
- `tcpKeepAlive=true` is a TCP keepalive mechanism, not an SQL statement timeout.
- `ApplicationName` helps with session observability.
- These values are **illustrative only**, not a universal standard configuration for every production setup.

## 6. `socketTimeout`: Network Read Wait Time, Not a Server Query Deadline

pgJDBC `socketTimeout` sets a wait limit on a **socket read operation**, in seconds.

Suppose:

```text
socketTimeout=10
```

If the driver waits longer than that in a single read waiting for the server to send data, the read operation can time out.

### 6.1. It Differs from `statement_timeout`

- `statement_timeout` runs on the **server** and cancels the SQL command when the limit is reached.
- `socketTimeout` occurs on the **client/driver** if no data arrives over the socket within the timeout mechanism.

If `socketTimeout` triggers, you cannot automatically conclude that PostgreSQL rolled back the command.

### 6.2. It Does Not Accurately Measure Total Query Duration

A query returning data in multiple batches can have repeated successful socket reads while the total request duration still exceeds `socketTimeout`. Therefore, `socketTimeout` **does not replace** a deadline covering the entire statement/request.

### 6.3. Socket Timeout Can Leave a Connection Untrustworthy

If the driver times out while reading a protocol response, the client/server protocol state or connection may become out of sync or unusable. The driver/pool may close or mark the connection broken.

**Never manually return such a connection to a custom reuse pool** just because `Connection.isClosed()` does not immediately reflect every error.

### 6.4. Setting `socketTimeout` Too Small Is Counterproductive

An SQL command allowed to run for 8 seconds while `socketTimeout` is only 2 seconds can cause the client to abandon the connection before server-side statement timeout/cancellation cleans up cleanly. You generally need a network limit with enough margin for the server timeout and cancellation.

### 6.5. `Connection.setNetworkTimeout`

JDBC provides `Connection.setNetworkTimeout(Executor, milliseconds)`, depending on driver support. This mechanism bounds network operations on the connection and is not the same thing as `Statement.setQueryTimeout`. If exceeded, the driver may close the connection; check the exact semantics and support of your actual driver and version.

Never treat `networkTimeout` as a new `statement_timeout` or a guarantee of transaction rollback.

## 7. JDBC Query Timeout: `Statement.setQueryTimeout`

Example:

```java
String sql = """
    SELECT order_id, status, amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY order_id
    LIMIT 100
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setQueryTimeout(5); // seconds per the JDBC API

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process returned rows.
        }
    }
}
```

### 7.1. Where Does This Limit Live?

`setQueryTimeout` is a JDBC API on the statement. With pgJDBC, when the timeout expires, the driver can send a **cancel request** to PostgreSQL asking it to stop the SQL statement.

When the `SQLException` arrives can be affected by scheduling, network latency, and backend response. Do not treat this as a hard real-time clock guaranteeing all code stops at exactly second 5.

### 7.2. Timeout ≠ Guaranteed Commit or Rollback in PostgreSQL

If the server sends a `query_canceled` error, you know the statement was canceled according to the server response. If the client merely encounters a network error while waiting, the server-side outcome can be **uncertain**, especially near the `COMMIT` boundary.

### 7.3. Query Timeout Differs from Application Result Processing Time

Java iterating through a `ResultSet`, calling downstream HTTP services, or serializing JSON can extend the request well beyond statement execution time. You need a **request deadline** and end-to-end workflow limits.

### 7.4. Do Not Set `setQueryTimeout` to 0 and Expect Automatic Stopping

Per the JDBC API, a value of 0 typically means **no query timeout limit at this layer**. If PostgreSQL has `statement_timeout` configured, it can still cancel the query; the two layers are independent.

## 8. pgJDBC `cancelSignalTimeout` and Cancel Requests

PostgreSQL has a dedicated **CancelRequest** mechanism to ask a backend running a statement to cancel its work. pgJDBC typically opens a separate network connection to send the cancel request.

`cancelSignalTimeout` bounds the connect/send/wait time for the cancel mechanism managed by the driver, **not the execution time of the entire query**.

### 8.1. Why Is a Separate Channel Needed?

The main connection may be waiting for a response or busy executing the query. A cancel request is sent over a separate channel carrying the required backend identification rather than injecting an SQL command into the waiting connection stream.

### 8.2. Cancel Is a Request, Not an Immediate Confirmation

When a cancel request is sent successfully:

- The backend may be executing the statement and receive the request.
- The backend may have already finished before the cancel arrived.
- The network may drop the message or the cancel channel may fail.
- The application may see an error due to a race when the statement already completed.

**Do not treat calling `cancel()` as proof that the statement stopped.** Observe the `SQLException`/result, connection state, and business outcome.

### 8.3. Secrets of the Cancel Protocol

Cancel requests use backend-provided information to authenticate the cancellation request under the protocol. Never expose internal protocol secrets in logs or APIs.

### 8.4. Cancel Timeout Can Differ from Query Timeout

A 5-second query timeout and `cancelSignalTimeout=5` do not mean the client will always receive an error at exactly 5 seconds. Sending and processing the cancellation can take additional time.

## 9. PostgreSQL `statement_timeout`: Server-Side SQL Deadline

PostgreSQL provides the GUC:

```sql
SHOW statement_timeout;
```

A value of `0` means **no limit** at this layer. You can configure time units such as milliseconds, seconds, or minutes.

### 9.1. Configuring in a Lab Session

```sql
SET statement_timeout = '1500ms';

SELECT pg_sleep(3);

RESET statement_timeout;
```

The `pg_sleep(3)` query is expected to be canceled by the server after about 1.5 seconds with an error similar to:

```text
ERROR: canceling statement due to statement timeout
SQLSTATE: 57014
```

When running in `psql` autocommit mode, a failed statement does not automatically disconnect the session; subsequent statements can run. Inside an explicit transaction, the transaction enters the aborted state and requires `ROLLBACK`.

### 9.2. When Does It Start?

`statement_timeout` applies to the time a statement is processed by the server under the applicable protocol, from when the server receives the appropriate request until the statement finishes. This is **not a total clock** starting from when the user clicked a button in the browser.

With the simple-query protocol and multiple SQL statements in a single message, modern PostgreSQL applies the timeout individually per statement according to the corresponding version semantics.

### 9.3. Does It Include Lock Waiting?

**Yes.** A statement waiting on a lock has not completed; `statement_timeout` can cancel that statement once the limit is exceeded.

### 9.4. Does It Limit a Multi-Statement Transaction?

**Not in the sense of total transaction duration.** Each statement gets its own timeout; a transaction with many fast statements separated by idle gaps can stay alive for a very long time unless other limits are enforced.

### 9.5. Setting It Very Low Server-Wide Carries Risks

A `statement_timeout` applied broadly to all workloads can break legitimate migrations, maintenance tasks, and long reports. Prefer configuring it per role, workload, or session as appropriate.

## 10. Configuration Scope: `SET`, `SET LOCAL`, and Role Defaults

### 10.1. Session-Level

```sql
SET statement_timeout = '5s';

SHOW statement_timeout;

RESET statement_timeout;
```

The setting persists in the session according to PostgreSQL rules; a connection pool may reuse the session across requests. If you forget `RESET`/cleanup, a subsequent request may hit an unexpected limit.

### 10.2. Transaction-Level with `SET LOCAL`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

SELECT COUNT(*)
FROM pg_catalog.pg_class;

COMMIT;
```

`SET LOCAL` takes effect for the current transaction and is restored by PostgreSQL according to transaction/savepoint semantics.

This is often a good choice when an operation needs a custom timeout without leaving session state behind for a connection pool.

### 10.3. When a Statement Timeout Occurs Inside a Transaction

Example:

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

SELECT pg_sleep(3);

-- If an error was just raised here, the transaction is now aborted.
-- Run ROLLBACK before executing further SQL.
ROLLBACK;
```

If a client runs a batch script, the `ROLLBACK` line may need to be sent after handling the error from the previous statement, depending on the tool.

### 10.4. Role Defaults

For an **actually existing** role and database, an administrator can configure:

```sql
ALTER ROLE app_runtime IN DATABASE appdb
SET statement_timeout = '5s';
```

This is a syntax example; **do not run it blindly** unless an appropriate `app_runtime` role and `appdb` database exist.

Such default changes apply when new sessions are established per PostgreSQL config precedence; **already open connections in a pool do not change immediately**.

### 10.5. Comparing Role Defaults and `SET LOCAL`

- Role/database default: provides a baseline safety net for a workload group and new sessions.
- `SET`: modifies the session.
- `SET LOCAL`: modifies the current transaction.
- `ALTER SYSTEM`/`postgresql.conf`: server-wide, requires careful consideration of broad impact.

### 10.6. How to Verify

```sql
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;

SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout'
)
ORDER BY name;
```

The `source` column helps identify where the effective value came from, rather than only looking at the current number.

## 11. `lock_timeout`: Dedicated Only to Lock Wait Time

`lock_timeout` limits how long a statement waits each time it needs to **acquire a lock**.

```sql
SET lock_timeout = '1s';
```

If a statement waits longer for a lock, PostgreSQL can report:

```text
ERROR: canceling statement due to lock timeout
SQLSTATE: 55P03
```

### 11.1. Difference from `statement_timeout`

`statement_timeout` measures the total time the server spends processing the statement, **including** lock waits.

`lock_timeout` measures only the time **waiting for lock acquisition**; it does not limit scan or aggregation time once the lock is acquired.

### 11.2. When Both Are Enabled

```sql
SET statement_timeout = '5s';
SET lock_timeout = '1s';
```

For a statement blocked on a lock for 2 seconds, `lock_timeout` is expected to fire first.

If `lock_timeout` is set equal to or greater than another `statement_timeout` already applying to the same statement, in many situations `statement_timeout` will trigger first, making `lock_timeout` ineffective.

### 11.3. Lock Timeout Is Not the Deadlock Detector

`deadlock_timeout` is a setting related to how long PostgreSQL waits before checking for deadlock or logging lock waits. It is not “cancel every lock wait after X seconds” like `lock_timeout`.

A detected deadlock has SQLSTATE `40P01`; a lock timeout has SQLSTATE `55P03`. Classify them separately.

## 12. Two-Session Lab: Creating a Row Lock Wait

To demonstrate lock timeout, create a table in a lab database:

```sql
CREATE SCHEMA IF NOT EXISTS timeout402;

CREATE TABLE timeout402.jobs (
    job_id integer PRIMARY KEY,
    owner_id integer NOT NULL,
    status text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO timeout402.jobs (job_id, owner_id, status)
VALUES (1, 10, 'NEW'),
       (2, 20, 'NEW');
```

Open **two separate PostgreSQL connections** to the same database.

### 12.1. Session A: Hold the Lock Without Committing

```sql
BEGIN;

UPDATE timeout402.jobs
SET status = 'RUNNING',
    updated_at = clock_timestamp()
WHERE job_id = 1;

-- Keep the transaction open so Session B must wait.
-- Do not COMMIT/ROLLBACK immediately at this step.
```

### 12.2. Session B: Wait on the Row Lock

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

UPDATE timeout402.jobs
SET status = 'CANCELLED'
WHERE job_id = 1;

-- Expected lock_timeout error SQLSTATE 55P03.
-- After the error, the transaction is aborted.
ROLLBACK;
```

Session B needs a lock on the row held by A; as long as A has not finished its transaction, B waits and then receives a lock timeout.

### 12.3. Session A: Release the Lock

```sql
ROLLBACK;
```

This resets `status` back to `NEW` in the lab.

### 12.4. Key Observations

- `lock_timeout` limits waiting for the lock; it **does not automatically roll back Session A's transaction**.
- After the error in B, you must roll back transaction B.
- `ROLLBACK` in A releases the lock for other sessions.
- If A committed before B expired, B can proceed without error; that is normal concurrency racing.

### 12.5. What If Only `statement_timeout` Is Set?

B may wait up to `statement_timeout` and receive error `57014` instead of `55P03`, depending on actual limits and timing.

## 13. `idle_in_transaction_session_timeout`: Guarding Against Forgotten Transactions

A connection might do:

```sql
BEGIN;
UPDATE timeout402.jobs
SET status = 'RUNNING'
WHERE job_id = 1;

-- The application sends no further commands for several minutes.
```

A session in the **idle in transaction** state can hold locks, pin old snapshots, hinder vacuum, or cause bloat.

PostgreSQL has:

```sql
SHOW idle_in_transaction_session_timeout;
```

### 13.1. Effect

When a session remains **idle inside a transaction** beyond the threshold, PostgreSQL **terminates the session** so the open transaction is rolled back and resources/locks are released.

This is not merely “canceling the current query,” because while idle there may be no active query running at all.

### 13.2. Demo in a Dedicated Session

```sql
SET idle_in_transaction_session_timeout = '3s';

BEGIN;
SELECT 1;

-- Pause sending SQL for about 4 seconds in a dedicated psql/session.
-- PostgreSQL may terminate the connection.

-- Afterward you must reconnect; do not keep using the old session.
```

Do not run this lab through a connection pool serving real requests.

### 13.3. It Does Not Bound a Long-Running Active Query

If `SELECT pg_sleep(100)` is active, the session is not “idle in transaction” during that period. Use `statement_timeout` for an active statement.

### 13.4. Do Not Hold a Transaction Open While Waiting on the Network

An anti-pattern:

```text
BEGIN
UPDATE a row
call an HTTP service taking 20 seconds
COMMIT
```

During those 20 seconds, the transaction stays open even though the PostgreSQL session sits idle-in-transaction. Design short transactions and avoid holding locks while waiting on external services.

## 14. `idle_session_timeout`: Sessions Idle Outside a Transaction

`idle_session_timeout` bounds how long a session can remain **idle outside a transaction** and can cause the backend to terminate the connection when exceeded.

### 14.1. Be Careful with Connection Pools

Pooled connections are normally **idle between requests**. If the server closes them before the pool notices, a subsequent request may borrow a broken connection and encounter an error.

### 14.2. Do Not Set Too Low by Default for Pooled Sessions

PostgreSQL documentation advises carefully evaluating `idle_session_timeout` with pools and middleware. Pools may have their own keepalive, validation, and `maxLifetime` mechanisms; configuration must be coordinated with infrastructure idle timeouts.

### 14.3. Distinguishing from Pool `idleTimeout`

- PostgreSQL `idle_session_timeout`: the server terminates the backend after idle conditions are met.
- HikariCP `idleTimeout`: the pool manages how long to retain **idle pool connections**, subject to `minIdle`/pool size settings.
- Network device idle timeout: routers/NAT/proxies may drop idle TCP flows.

They all share the word “idle,” but they are not the same timer.

## 15. `transaction_timeout` in PostgreSQL 17 and Later

PostgreSQL 17 introduced `transaction_timeout` to bound the lifetime of a transaction via a server mechanism.

```sql
-- PostgreSQL 17+:
SHOW transaction_timeout;
```

If set to a non-zero threshold, a transaction that lives too long can cause the backend/session to be terminated.

### 15.1. Compared with `statement_timeout`

`statement_timeout` limits **each statement**; a transaction consisting of many short SQL statements can outlive that threshold in total.

`transaction_timeout` helps bound the **entire transaction lifetime**.

### 15.2. Must Be Version-Aware

On PostgreSQL 16 or earlier, `SHOW transaction_timeout` will fail because the setting does not exist. Never write migrations or configs that apply it blindly to all servers.

### 15.3. Interaction Between Timeouts

PostgreSQL defines interaction rules between `transaction_timeout` and other timeouts. When `transaction_timeout` is equal to or shorter than certain statement or idle-in-transaction timeouts, the transaction limit may trigger first. Check the documentation for your exact version and test with real workloads rather than assuming all timers always act independently.

### 15.4. Connection Pools and Transaction Timeout

If the server terminates the backend, the application must handle a **broken connection**, not just run `ROLLBACK` and unconditionally reuse it.

## 16. Canceling a Statement from JDBC Using `Statement.cancel()`

JDBC provides:

```java
statement.cancel();
```

While PostgreSQL is executing a statement, `cancel()` sends a cancellation request through the driver.

### 16.1. Real-World Scenarios

- The user clicks “Cancel report.”
- The HTTP client disconnects, and the application propagates cancellation.
- A background job is canceled due to shutdown or deadline expiration.
- An operator wants to stop a running query without tearing down the session.

### 16.2. Canceling from Another Thread

`Statement.cancel()` can be used as a cancellation path from a control thread targeting an executing statement, per JDBC/driver semantics. However, **never use the same `Connection` to execute SQL statements concurrently from multiple threads**.

Keep statement lifecycle management clear: if the statement is already closed or the driver has moved on to another query, cancellation can arrive late or race.

### 16.3. Example Control Model

```java
// Worker thread (owns conn/statement):
try (PreparedStatement ps =
         conn.prepareStatement("SELECT pg_sleep(30)")) {

    ps.setQueryTimeout(5);

    // Control path holds a reference to the statement if cancellation is needed.
    // On user cancel: call ps.cancel() from the control thread.
    ps.execute();
}
```

In production code, build a proper lifecycle manager for request-to-statement mapping, thread safety, and cleanup. Do not share a `Connection` as a free-for-all across multiple threads running SQL.

### 16.4. Do Not Confuse Cancel with Closing a Connection

Cancel requests stopping the **current statement**. The connection can remain open and requires proper transaction state handling.

Closing or terminating a connection is a different operation that affects the entire session.

## 17. Canceling from PostgreSQL Using `pg_cancel_backend`

Every backend has a process ID:

```sql
SELECT pg_backend_pid();
```

In a monitoring session with appropriate privileges, you can ask another backend to cancel its query:

```sql
SELECT pg_cancel_backend(12345);
```

Here `12345` is an **example**; only use a real PID verified in the lab.

### 17.1. Privileges to Cancel a Backend

Permission to call `pg_cancel_backend` on a backend depends on role ownership and privileges such as `pg_signal_backend` or superuser status under PostgreSQL rules.

Do not broadly grant permission to cancel other users' queries merely for convenience.

### 17.2. Returning `true` Does Not Guarantee the Query Stopped

The boolean return value indicates that the signal/cancel request was sent via the supported mechanism, **not confirmation that the query was canceled and its transaction rolled back**.

### 17.3. One Target Means One Backend

If a pool has many backends, verify the exact `pid`, `application_name`, `usename`, `state`, and timing. PIDs can be reused after an old backend exits; avoid caching a PID for long and canceling blindly.

### 17.4. Be Careful with Privileged Sessions

Never target migrations, replication, maintenance, or other users' sessions without verifying consequences and operational authority.

## 18. `pg_terminate_backend`: Terminating the Connection, Different from Cancel

When a query or session cannot continue, a DBA may need:

```sql
SELECT pg_terminate_backend(12345);
```

General effects:

- Requests termination of the target backend process/session.
- Open transactions are rolled back under database crash/session-termination semantics.
- Locks and session resources are released once the backend actually exits.
- The application observes a lost connection and must reconnect.

### 18.1. When Prefer Cancel?

If you only need to stop a runaway query and want to preserve the session if possible, **cancel** is the less destructive step.

### 18.2. When Terminate?

When the backend is unresponsive, the session is no longer valid, an idle transaction holds dangerous locks, or an operational runbook calls for disconnecting it.

### 18.3. Do Not Treat Terminate as “Stopped Immediately”

Signal/termination delivery can have latency. Verify state in `pg_stat_activity`, locks, and the application.

### 18.4. Terminate Does Not Fix a Code Connection Leak

If Java fails to close connections properly, new connections will continue to leak after a DBA terminates old ones.

## 19. Transactions After a Query Timeout: What Happens?

In PostgreSQL, a failed statement inside an **explicit transaction** typically puts the transaction into the aborted state.

Example:

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

SELECT pg_sleep(3);
-- ERROR SQLSTATE 57014.

SELECT 1;
-- May return:
-- ERROR: current transaction is aborted
-- SQLSTATE 25P02.

ROLLBACK;

SELECT 1;
-- Works normally after rollback.
```

### 19.1. Why Can't You Continue with an UPDATE?

After a statement fails, the transaction is not in a state where normal SQL can continue. PostgreSQL requires rolling back the transaction or rolling back to a valid savepoint per its semantics.

### 19.2. Savepoints Are a Controllable Case

```sql
BEGIN;

SAVEPOINT before_work;

-- Run a statement that may time out.
-- If the statement errors:
ROLLBACK TO SAVEPOINT before_work;

-- The transaction can continue after rolling back the appropriate scope.
COMMIT;
```

This is an illustrative pattern. Only use it when the business transaction is designed to allow partial retries and the driver/connection remains usable.

### 19.3. Auto-Commit

With JDBC `autoCommit=true`, each statement typically runs in its own transaction; a failed statement does not leave an explicit transaction open for the application to roll back as with `autoCommit=false`.

However, a **read/socket failure or broken connection** can still make the outcome uncertain. Never equate auto-commit with total retry safety.

## 20. JDBC Transaction Code: Rolling Back on `SQLException`

Example service using a dedicated connection for a transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JobService {
    private final DataSource ds;

    public JobService(DataSource ds) {
        this.ds = ds;
    }

    public void markRunning(int jobId) throws SQLException {
        try (Connection conn = ds.getConnection()) {
            conn.setAutoCommit(false);

            try {
                try (PreparedStatement ps = conn.prepareStatement("""
                    UPDATE timeout402.jobs
                    SET status = 'RUNNING',
                        updated_at = clock_timestamp()
                    WHERE job_id = ?
                    """)) {

                    ps.setInt(1, jobId);
                    ps.setQueryTimeout(3);

                    int changed = ps.executeUpdate();
                    if (changed != 1) {
                        throw new SQLException(
                            "Expected exactly one job row"
                        );
                    }
                }

                conn.commit();
            } catch (SQLException original) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    original.addSuppressed(rollbackError);
                }
                throw original;
            }
        }
    }
}
```

### 20.1. Why Does Rollback Need Its Own try/catch?

If the connection was already closed due to a network timeout, `rollback()` can also fail. Never mask the original error; attach the rollback error as a suppressed exception for investigation.

### 20.2. Why Close the Connection in `finally` / `try-with-resources`?

To prevent pool leaks. In a pool, `close()` normally returns the proxy connection to the pool rather than necessarily closing the physical TCP socket; the pool needs to detect broken connections.

### 20.3. One Remaining Issue: Commit Outcome Uncertainty

If `conn.commit()` was sent to the server, but the connection dropped before the client received the result, code may catch an `SQLException` **even though the transaction committed**. Seeing an `SQLException` alone does not prove a rollback occurred.

Business design requires idempotency and separate reconciliation for critical write operations.

### 20.4. Another Issue: Timeouts Can Arrive Before Commit

`ps.setQueryTimeout(3)` limits the `UPDATE` statement; it does not apply identically to every commit/network read step or the entire business transaction. You need separate deadline, transaction timeout, and network policies.

## 21. SQLSTATE: Classifying Errors Instead of Matching the Word “Timeout”

PostgreSQL provides SQLSTATE codes for structured error classification. Some common codes:

| SQLSTATE | Name / Class | Context |
| --- | --- | --- |
| `57014` | `query_canceled` | `statement_timeout` or cancel request canceled the statement |
| `55P03` | `lock_not_available` | `lock_timeout` or `NOWAIT` failed to acquire lock |
| `40P01` | `deadlock_detected` | Deadlock detector found a lock cycle |
| `40001` | `serialization_failure` | Transaction isolation requires retrying the full transaction |
| `25P02` | `in_failed_sql_transaction` | Subsequent query after transaction entered aborted state |
| `08xxx` | Connection exception class | Network/protocol/connection failure depending on specific code |

### 21.1. `57014` Can Have Multiple Causes

An SQL query canceled by user action or by server `statement_timeout` can both report `57014`. To distinguish them accurately, combine message/logs, timeout settings, request IDs, and timing rather than relying solely on the code.

### 21.2. `55P03` Can Also Come from `NOWAIT`

`SELECT ... FOR UPDATE NOWAIT` can raise `55P03` immediately when a lock is unavailable. Not every `55P03` proves a `lock_timeout` waited out its seconds.

### 21.3. A Connection Error Does Not Mean the Database Rolled Back

An `08xxx` error or `SocketTimeoutException` may indicate the client lost visibility into what the server did. For write operations, you must handle the ambiguous state.

### 21.4. In Java

```java
try {
    // Query...
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("57014".equals(state)) {
        // Query canceled / statement timeout.
    } else if ("55P03".equals(state)) {
        // Lock wait failed, or NOWAIT.
    } else if ("40001".equals(state)) {
        // Controlled serialization retry.
    } else if (state != null && state.startsWith("08")) {
        // Connection issue: outcome may be uncertain.
    }

    throw ex;
}
```

Never rely solely on `SQLTimeoutException` type checks or error message substring matching to decide whether to retry write operations.

## 22. Client Timeout When the Server Already Committed: “Unknown Outcome”

A dangerous scenario:

```text
Application                         PostgreSQL
    |                                   |
    |--------- INSERT order ----------->|
    |                                   |
    |----------- COMMIT --------------->|
    |                                   | COMMIT completes
    |                    [packet loss / network drop]
    |<----- confirmation not received ---X
    |
    +-- SQLException / timeout
    +-- Unknown whether transaction committed!
```

### 22.1. Do Not Unconditionally Retry `INSERT`

If you resend the order placement operation when the first transaction **already committed**, you may create duplicate orders or charge twice.

### 22.2. Idempotency Key

The application generates a unique business transaction identifier, such as `request_id`, backed by a unique constraint:

```sql
CREATE TABLE timeout402.requests (
    request_id uuid PRIMARY KEY,
    tenant_id integer NOT NULL,
    result_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

A retry sends the **same `request_id`** and idempotent logic so it does not trigger side effects a second time.

### 22.3. Data Must Stay Consistent with the Request ID

A key must never be reused for two requests with different content. Production systems often store a payload hash, status/result, and conflict rules to return the prior result or reject mismatches.

### 22.4. `ON CONFLICT` Does Not Solve Every Side Effect Automatically

`INSERT ... ON CONFLICT` can prevent duplicate inserts on a unique key, but if code sends emails or calls payment services outside the transaction without matching idempotency, external side effects can still repeat.

### 22.5. Distinguishing Transaction Error Retries from Network Failure Retries

- `40001`: PostgreSQL explicitly signaled the transaction must retry; retry the **entire** transaction per business policy.
- `40P01`: deadlock victim needs controlled retry.
- `57014` due to server canceling statement: check remaining deadline and whether retry is appropriate.
- Network timeout around commit: ambiguous outcome; **reconcile via idempotency key**, do not blindly resubmit as if it never ran.

## 23. HTTP Request Timeout Does Not Automatically Cancel a PostgreSQL Query

Suppose a reverse proxy returns `504 Gateway Timeout` after 10 seconds. A PostgreSQL query invoked by the backend can still keep running for another minute if the application does not cancel the statement or the server has no timeout.

### 23.1. Client Disconnect Differs from Driver Cancel

Closing a browser tab does not automatically equal `Statement.cancel()`. The framework/server may or may not propagate cancellation depending on how the application is written.

### 23.2. Deadlines Should Be Propagated Down to the Database Layer

Compute the deadline when the request begins. Before running a query, compute the **remaining time budget** instead of always giving SQL a fixed number of seconds regardless of how long the request has already spent.

### 23.3. Block New Work After Deadline Expiration

If no budget remains, do not check out a connection and launch a new query simply because the default statement timeout is still 30 seconds.

### 23.4. Clean Up Resources When a Request Is Canceled

- Cancel the active statement when appropriate.
- Roll back the transaction if needed and the connection is healthy.
- Close statement/result set.
- Return or discard the connection through the pool according to its contract.
- Record outcome metrics and correlation ID.
- Never leave an idle transaction holding locks after the response has finished.

### 23.5. Do Not Accidentally Cancel Intended Background Jobs

If a workflow hands off to a background job with its own lifecycle, an HTTP disconnect may not be a reason to stop the job. Distinguish synchronous request-bound queries from durable async work.

## 24. Designing a Timeout Budget for an API

Consider a read request with an 8-second SLO. A starting configuration might look like:

| Component | Illustrative Threshold | Meaning |
| --- | ---: | --- |
| HTTP application deadline | 8 s | Overall request ceiling |
| Pool checkout wait | 0.8 s | Avoid queuing too long on the pool |
| Driver `connectTimeout` | 2 s/attempt | When a physical connection is needed |
| Server `lock_timeout` | 0.8 s | Reduce time spent waiting on locks |
| Server `statement_timeout` | 5 s | Limit SQL execution |
| JDBC `queryTimeout` | 6 s | Client has an additional cancel layer |
| Socket read timeout | 12 s | Network failure backstop; not the HTTP deadline |
| Cancel signaling | 3 s | Limit on cancel request path |

These numbers are **analytical examples**, not a formula for every system.

### 24.1. Do Not Add All Layers as If Always Sequential

Several thresholds **overlap** (server/JDBC/socket query timers) rather than summing sequentially. Conversely, pool wait + connect + query + result processing can be sequential segments.

### 24.2. Leave Buffer Room

If the HTTP deadline is 8s and the JDBC query timeout is also 8s, the application may have no time left for rollback, logging, or building a response when the query is canceled.

### 24.3. Query Budget Must Depend on Remaining Time

If a request already spent 4 seconds on authentication and downstream calls, do not give the DB another 5 seconds even if the server default is 5s. The effective limit should account for the remaining deadline.

### 24.4. A Socket Read Timeout Longer Than Query Timeout Does Not Enforce the HTTP Deadline

A 12s socket timeout is a **transport backstop**. To respond within 8s, the application must enforce its deadline/cancellation rather than letting the same request wait on the socket indefinitely.

### 24.5. Background Jobs Have Different Budgets

Batch migrations/reports may accept minutes or hours and should use dedicated connection/job pools, role defaults, and metrics. Never apply an interactive API's 5s timeout to every workload.

## 25. HikariCP: Distinguishing Pool Settings from JDBC/Network Settings

An illustrative Java example using HikariCP (requires HikariCP and PostgreSQL JDBC Driver dependencies):

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.util.Properties;

HikariConfig config = new HikariConfig();

config.setJdbcUrl(
    "jdbc:postgresql://localhost:5432/appdb"
);
config.setUsername("app_runtime");
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(10);
config.setMinimumIdle(2);

// HikariCP: milliseconds.
config.setConnectionTimeout(1000);
config.setValidationTimeout(1000);
config.setIdleTimeout(600000);
config.setMaxLifetime(1800000);
config.setKeepaliveTime(120000);

// pgJDBC: most timeouts here are in seconds.
Properties props = new Properties();
props.setProperty("connectTimeout", "3");
props.setProperty("loginTimeout", "5");
props.setProperty("socketTimeout", "15");
props.setProperty("cancelSignalTimeout", "5");
props.setProperty("tcpKeepAlive", "true");
props.setProperty("ApplicationName", "orders-api");

config.setDataSourceProperties(props);

try (HikariDataSource ds = new HikariDataSource(config)) {
    // Use ds.getConnection() in services.
}
```

This is an **illustrative** configuration; you are not expected to create a database, role, or password matching these exact names.

### 25.1. Different Units

- HikariCP `connectionTimeout`, `validationTimeout`, `idleTimeout`, `maxLifetime`, and `keepaliveTime` are in **milliseconds**.
- pgJDBC `connectTimeout`, `loginTimeout`, `socketTimeout`, and `cancelSignalTimeout` are in **seconds**.

Confusing `5000` between the two libraries can turn 5 seconds into tens of minutes or hours.

### 25.2. `maxLifetime` Is Not a Query Timeout

It is a pool connection lifecycle mechanism; a connection currently in use is not simply cut mid-query just because its pool lifecycle age arrived.

### 25.3. `keepaliveTime` Is Not the Same as TCP Keepalive

Hikari keepalive checks/maintains **idle pool connections** under pool policy; TCP keepalive sends network socket probes at the OS/network layer.

Neither replaces `statement_timeout`.

### 25.4. Monitor Pool Metrics

Track active/idle/pending connections, checkout time, connection creations, and failures. If the pool is frequently exhausted, investigate query latency, transactions, and concurrency rather than merely increasing `connectionTimeout`.

## 26. TCP Keepalive and Network Equipment

Network devices can drop connections that carry no traffic for long periods: NAT, firewalls, load balancers, proxies, or service meshes.

### 26.1. TCP Keepalive

When `tcpKeepAlive` is enabled, the TCP stack can send probes according to **OS configuration**. It helps detect certain half-open connections, but does not provide a 5s SQL execution deadline or immediately detect every network partition.

### 26.2. Network Idle Timeout

A load balancer can drop an idle TCP flow. If the pool holds connections longer than the device idle policy, the next use can hit `connection reset`, EOF, or read timeout.

### 26.3. Pool Validation

The pool can perform JDBC validation to detect unusable connections before handing them to the app. However, validation succeeding at T1 does not guarantee the network remains healthy at T2.

### 26.4. Combining Settings

- Know the idle timeout policies of your infrastructure devices.
- Align pool `maxLifetime`/`keepalive` appropriately with server/network limits.
- Enable TCP keepalive where appropriate.
- Use validation and broken-connection eviction.
- Have dedicated retries for **safe/idempotent** operations.
- Monitor `08xxx` errors and socket exceptions.

### 26.5. Do Not Use Keepalive to Fix Slow Queries

A query waiting on a lock will not finish faster because of TCP keepalive. Investigate locks and statement/lock timeouts.

## 27. PgBouncer/Proxies Can Add Another Timeout Layer

If your architecture places a connection pooler or proxy in front of PostgreSQL:

```text
Java/Hikari
    |
    | client TCP
    v
PgBouncer / cloud proxy / LB
    |
    | server TCP
    v
PostgreSQL backend
```

Additional behaviors may apply:

- Proxy connection establishment and health checks.
- Timeouts waiting for a server connection.
- Query or idle timeouts per specific product features/config.
- Socket lifetime and server recycling.
- Transaction-pooling restrictions on session state.

### 27.1. Do Not Assume One Physical Connection = One Fixed Backend

In **transaction pooling**, different client operations may be routed to different server connections across transactions. Session-level `SET`, prepared statements, and backend PID assumptions must fit the actual capabilities of your pooler and version.

### 27.2. Prefer Transaction-Scoped Settings When Appropriate

`SET LOCAL statement_timeout` inside an explicit transaction is better suited than expecting a custom session default to stick to the same backend across a transaction pooler, though you should still verify the exact behavior of your pooler/config.

### 27.3. Check Logs on Both Sides

If the app reports a timeout, inspect driver, pooler, and backend logs to determine which layer timed out. A proxy closing a socket does not necessarily cancel the server SQL in the expected way.

### 27.4. Server Settings Can Still Act as a Backstop

`statement_timeout` enforced by PostgreSQL helps bound SQL even if the HTTP client or proxy failed, provided the statement falls under the scope where the setting applies.

## 28. Investigating Running Queries with `pg_stat_activity`

A first diagnostic tool:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
```

### 28.1. `state = 'active'`

The backend is processing a query (it may be **waiting on a lock or I/O**). It does not mean CPU is running continuously.

### 28.2. `state = 'idle in transaction'`

The session is not currently executing a query, yet still holds an open transaction that may hold locks or snapshots.

### 28.3. `wait_event_type`

- `Lock`: waiting on a lock.
- `IO`: likely waiting on I/O.
- `Client`: waiting on client/network communication.
- `NULL`: not waiting on an instrumented event at snapshot time; does not prove the backend has no issues.

### 28.4. `query_start` Differs from `xact_start`

A transaction may have started long ago and contain multiple statements. The `query_start` of the current/last query is not equal to the transaction lifetime.

When measuring query age, interpret it in the context of `state`. For an idle session, `query_start` may be the start time of its previous query.

### 28.5. Visibility Privileges

A role may be restricted from viewing SQL text or details of other sessions. Use an appropriate monitoring role (such as predefined monitoring roles) and protect privacy because `query` can contain sensitive data.

## 29. Finding Lock Blockers with `pg_blocking_pids`

PostgreSQL provides a helper:

```sql
SELECT
    a.pid AS waiting_pid,
    a.usename,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

### 29.1. Why Use `pg_blocking_pids`?

`pg_locks` contains many lock rows, and writing manual joins to identify exact blockers has subtle pitfalls (lock modes, wait queues, parallel workers). `pg_blocking_pids` returns the blocking PIDs according to PostgreSQL's own logic.

### 29.2. Do Not Immediately Terminate the First Blocker

First determine:

- What is that query/transaction doing?
- Is a legitimate migration running?
- Is the blocker idle-in-transaction because an application forgot to commit?
- Is there uncommitted work that must be preserved?
- Can the application be asked to roll back first?

### 29.3. If More Detail Is Needed

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_catalog.pg_locks AS l
WHERE l.pid IS NOT NULL
ORDER BY l.pid, l.granted;
```

Not every `pg_locks` row has a `relation`; `NULL` values are normal for other lock types.

### 29.4. Snapshots Are Point-in-Time

Between reading PIDs and sending a cancel signal, the query or connection may already have changed. Also check `backend_start`, `application_name`, user, and transaction metadata when needed to avoid targeting the wrong PID.

## 30. Logging and Monitoring Timeouts

Metrics worth tracking:

| Metric | Purpose |
| --- | --- |
| API request latency and timeout rate | Understand user experience |
| Pool pending/active/idle connections | Detect pool pressure |
| Connection establishment failures | Detect DNS/TLS/auth/network issues |
| Query execution time / SQLSTATE `57014` | Track statement cancellations |
| Lock wait counts / `55P03` | Detect contention |
| Deadlocks / `40P01` | Detect mutual lock cycles |
| Socket/read failures / SQLSTATE `08xxx` | Monitor transport health |
| Idle-in-transaction sessions | Detect transaction leaks |
| Broken connections discarded | Evaluate pool recovery |
| Backend termination events | Detect session-level timeouts |
| Retry counts and idempotency conflicts | Observe post-error behavior |
| Commit outcome reconciliation | Prevent duplicate business writes |

### 30.1. `application_name`

Set it per application/workload:

```text
ApplicationName=orders-api
```

You can then filter `pg_stat_activity`, while avoiding putting PII, secrets, or tokens into `application_name`.

### 30.2. Slow Query Logging

Settings like `log_min_duration_statement` help observe slow statements when governed appropriately per environment. Broad logging can increase I/O and expose SQL/literals in logs.

### 30.3. `log_lock_waits` and `deadlock_timeout`

PostgreSQL can log long waits when `log_lock_waits` and `deadlock_timeout` are configured appropriately. This is **observability**, not a substitute for `lock_timeout`.

### 30.4. `pg_stat_statements`

If the extension is installed/configured, it provides aggregate query statistics. It is not always available; even when present, it does not fully explain why a specific HTTP request timed out.

### 30.5. Correlation ID

Attach request/job IDs to application logs and trace spans, linking query templates, pool waits, DB duration, and SQLSTATE. Do not arbitrarily log credentials or sensitive user data.

## 31. Retries: When Reasonable and When Dangerous?

A good retry policy must evaluate:

1. **Operation**: read-only or writing data?
2. **Error**: lock wait, deadlock, serialization, query canceled, or network failure?
3. **Deadline**: is enough time left for a retry?
4. **Idempotency**: will resubmitting produce a second side effect?
5. **State**: is the transaction aborted, connection broken, or commit outcome unknown?
6. **Contention**: will immediate retrying add more load?

### 31.1. Read-Only `SELECT`

A `SELECT` may be retried on certain transient connection failures, while protecting consistency requirements, paging/snapshot semantics, and the request deadline.

### 31.2. `55P03` from Lock Timeout

Retrying can help when contention is brief. Use bounded retries, jitter/backoff, and reduce lock duration rather than retrying indefinitely.

### 31.3. `40P01` and `40001`

Usually requires retrying the **entire transaction** from the start of the business logic, not just the single SQL statement that failed, per PostgreSQL transaction isolation semantics.

### 31.4. `57014` from User Cancellation

If the user actively canceled, automatic retries go against their intent.

### 31.5. HTTP Deadline Already Expired

Do not keep retrying a query just because the DB error is retryable, unless the task is designed as an independent background workflow.

### 31.6. Network Failure Near `COMMIT`

Verify idempotency/result in a reliable store; never assume rollback. For payments or orders, this is a core correctness requirement.

## 32. Avoiding Retry Storms After an Outage

Suppose 1,000 concurrent HTTP requests hit an SQL timeout. If all of them immediately retry 3 times, the DB can receive 3,000 extra queries right while already overloaded.

### 32.1. Bounded Exponential Backoff with Jitter

Conceptual policy example:

```text
attempt 1 error 40P01
    |
    +-- deadline remaining?
         |
         +-- yes -> random wait 50..150ms -> retry
         |
         +-- no  -> fail gracefully
```

Do not blindly reuse the same numbers for every workload.

### 32.2. Circuit Breakers and Bulkheads

Separate pools for heavy workloads and latency-sensitive APIs where appropriate. Apply concurrency caps, load shedding, and circuit breakers at the application/infrastructure layer.

### 32.3. Timeouts Must Be Paired with Capacity Controls

Simply setting a 1-second timeout does not fix a bad query plan; it can generate more errors and retries, increasing contention if traffic keeps arriving.

### 32.4. Measure Error Budgets

Watch both timeout rate **and** success rate at latency SLOs. Never optimize “number of canceled queries” by disabling all timeouts while the DB still frequently hangs requests.

## 33. Common Configuration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming pool `connectionTimeout` is a query timeout | SQL still runs long | Set JDBC/server query timeouts |
| Assuming `connectTimeout` is total HTTP deadline | Request slow despite fast TCP connect | Request deadlines and per-stage budgets |
| Socket timeout much shorter than statement timeout | Driver drops connection while SQL runs | Coordinate timeouts + cancellation |
| Using only HTTP timeout | Query continues after HTTP fails | Propagate cancellation + server timeouts |
| `statement_timeout=0` with no other layer | Queries can run very long | Workload-appropriate timeouts |
| `lock_timeout` larger than `statement_timeout` | Only `statement_timeout` fires first | Set lower `lock_timeout` when needed |
| `idle_in_transaction_session_timeout` too low | Sessions terminated unexpectedly | Keep transactions short; tune sensibly |
| `idle_session_timeout` too low with a pool | Many stale connections | Coordinate server/pool/network settings |
| Applying a 5s timeout to every migration | Legitimate schema changes fail | Separate roles/workloads |
| `SET statement_timeout` without `RESET` | Session state leaks across pool | Use `SET LOCAL` or reset properly |
| Not running `ROLLBACK` after an error in a txn | SQLSTATE `25P02` on subsequent statements | Roll back the proper scope |
| Retrying `INSERT` after socket failure | Possible duplicate business records | Idempotency/reconciliation |
| Assuming `cancel()` always stops a query instantly | Races, connection/driver errors | Inspect response/outcome |
| Using terminate for every slow query | Lost connections, broad rollbacks | Cancel first when appropriate |
| Canceling an unverified PID | May hit an unrelated session | Verify `application_name`/user/`backend_start` |
| Failing to close connection on error | Pool leak | `try-with-resources` |
| Sharing a `Connection` across concurrent SQL threads | Protocol/state races | Per-request ownership |
| Counting `query_age` while `state` is `idle` | Misinterpreting elapsed time | Check `state` and `xact_start` |
| Increasing `maximumPoolSize` without bound | PostgreSQL overload | Diagnose root cause |
| Using TCP keepalive as a query timeout | Does not limit SQL duration | Use statement/query timeouts |
| Using network timeout as a transaction guarantee | Ambiguous commit outcome | Use idempotency |
| Not checking lock blockers | Only seeing “slow query” | Check `pg_blocking_pids` and logs |
| Mixing background jobs and API in one pool | Long reports starve API pool | Separate pools/roles/budgets |

## 34. Practical Test Suite for Verifying Timeouts

To experiment, use a dedicated `timeout402` database and at least two sessions when needed.

### 34.1. Case A — Server-Side Query Timeout

```sql
SET statement_timeout = '1s';
SELECT pg_sleep(3);
RESET statement_timeout;
```

Expect SQLSTATE `57014`; the session normally stays alive unless the connection itself dropped.

### 34.2. Case B — Transaction Aborted After Statement Timeout

```sql
BEGIN;
SET LOCAL statement_timeout = '1s';
SELECT pg_sleep(3);
SELECT 1;
ROLLBACK;
```

Expect `SELECT 1` (if executed after the error without rolling back) to raise `25P02`.

### 34.3. Case C — Lock Timeout

Use two sessions as in Section 12. Expect B to receive `55P03` if A holds the lock past the limit.

### 34.4. Case D — Manual Cancellation

Session A:

```sql
SELECT pg_backend_pid();
SELECT pg_sleep(30);
```

Session B (with appropriate privileges):

```sql
SELECT pg_cancel_backend(<pid_of_session_A>);
```

The line `<pid_of_session_A>` is a descriptive placeholder, **not literal SQL to run verbatim**. Replace it with the verified real PID. Expect A to receive `57014` if the request arrives while the query is still running.

### 34.5. Case E — Terminate

In the lab and with necessary privileges, Session B:

```sql
-- Example with a real PID; run only against a lab session:
SELECT pg_terminate_backend(12345);
```

Expect the target session to lose its connection. Never use an example PID blindly or terminate system/other users' backends.

### 34.6. Case F — Pool Checkout Timeout

Use a very small pool in an integration test:

- Check out and hold all connections.
- Call `getConnection()` once more.
- Verify the application receives a pool timeout error per the threshold.
- Return connections in `finally`.

Never create intentional connection leaks in production.

### 34.7. Case G — Network/Socket Failure

Use an integration environment with authorized network fault injection to simulate dropped connections or proxy closes. Verify the application discards broken connections and handles ambiguous write outcomes.

**Never disrupt firewalls or networks in production just to test.**

### 34.8. Case H — Idle in Transaction

Use a dedicated lab connection with a small `idle_in_transaction_session_timeout` and stop sending SQL. Observe the session getting terminated and reconnecting.

### 34.9. Case I — PG17+ Transaction Timeout

Check `server_version_num` and run tests per version documentation; do not issue `SHOW transaction_timeout` on PG16 or lower.

### 34.10. Case J — Canceling Before vs. After Query Completion

Observe the race: a cancel request arriving too late cannot cancel an already completed statement. The system must never rely solely on having sent the signal to conclude that a transaction did not commit.

## 35. Designing Integration Tests with JDBC

A good test verifies both the exception and backend state:

1. Create a dedicated test `DataSource`.
2. Use tables/roles scoped strictly to the test database.
3. Set a low server timeout for the test via `SET LOCAL`.
4. Run `SELECT pg_sleep(...)` and assert `SQLSTATE 57014`.
5. After an error inside an explicit transaction, verify the connection requires rollback.
6. Roll back and run `SELECT 1` on the healthy connection.
7. Test row locking with two physical connections.
8. Measure pending pool connections when the pool is full.
9. Test `Statement.cancel()` on a privately owned statement.
10. Test controlled network loss and connection eviction.
11. Test idempotent retries when `COMMIT` outcome is unknown.
12. Verify application logs do not leak passwords or sensitive SQL values.

### 35.1. Why Not Only Mock `SQLException`?

Mocks help test branching logic, but they do not prove aborted-transaction semantics, signal delivery, or socket behavior. Integration tests against a real PostgreSQL instance are required.

### 35.2. Query Timeout Tests Can Have Timing Variance

Schedulers, CI load, and networks can cause timing jitter. Assert the error class, state, and a reasonable duration range rather than exact milliseconds.

### 35.3. Keep the Test Environment Stable

Do not run stress tests with hundreds of connections against a shared development database without limits, as that disrupts other developers.

## 36. Incident Runbook for “API Hanging Due to PostgreSQL”

### Step 1. Identify the Symptom

- HTTP 504 from a proxy or timeout inside the application?
- Pool `getConnection()` timeout or JDBC query timeout?
- Which `SQLException` SQLSTATE?
- Only one endpoint or all endpoints?
- One database host/zone or the entire system?

### Step 2. Check Pool Metrics

Active connections, idle connections, pending requests, checkout latency, and error rate.

If pool pending is high while SQL duration is normal, look for leaks or long transactions; if SQL duration is high, investigate queries next.

### Step 3. Inspect `pg_stat_activity`

Focus on:

- `state='active'` with high `query_age`.
- `wait_event_type='Lock'`.
- `state='idle in transaction'` with high `transaction_age`.
- `application_name` to identify the workload source.

### Step 4. Find Blockers

Check `pg_blocking_pids` and `pg_locks`. Identify the lock-holding transaction before intervening.

### Step 5. Inspect Server Logs

Look for `statement timeout`, `lock timeout`, deadlocks, connection resets, backend terminations, failovers, and authentication failures.

### Step 6. Take Proportionate Safe Actions

- Throttle request concurrency or traffic hitting the heavy query.
- Have the application roll back or close idle-in-transaction sessions.
- `pg_cancel_backend` on the verified PID when a query must be stopped.
- `pg_terminate_backend` only when necessary and with full understanding of transaction impact.
- If an SQL plan is poor, fix indexing or optimize the query rather than just raising timeouts.

### Step 7. Verify Application Recovery

Confirm the pool evicted broken connections, connection acquisition returned to normal, and retries did not create duplicate orders or jobs.

### Step 8. Prevent Recurrence

Tune budgets, query plans, timeout defaults, transaction boundaries, concurrency limits, and monitoring based on the actual root cause.

## 37. Special Scenarios

### 37.1. `COPY` or Queries Returning Large Result Sets

Transferring large volumes can make network/client processing take longer than core SQL execution. Use backpressure, limits, and appropriate timeouts. Do not assume `statement_timeout` accurately bounds an entire business export workflow.

### 37.2. Cursors and Repeated Fetches

A cursor can execute multiple fetch calls; `statement_timeout` scopes per command/statement and transaction context rather than automatically bounding the total time spent iterating through the whole dataset.

### 37.3. DDL Migrations and `lock_timeout`

An `ALTER TABLE` migration may require a strong lock. A small `lock_timeout` lets it fail fast instead of blocking behind long queues; before retrying, handle state/locks rather than retrying DDL infinitely.

### 37.4. Long-Running Reports

A legitimate 2-minute report can run via a background queue with its own pool/role, `statement_timeout`, and job timeout separate from HTTP APIs. Provide progress tracking and safe job cancellation.

### 37.5. Failover

Failover can invalidate old connections, change DNS/host selection, and leave transactions with unknown outcomes. Handle reconnects, pool eviction, and idempotency; never assume failover guaranteed rollback of every business action.

### 37.6. SQL Calling External Services

Never hold DB transactions or row locks while calling slow network services. If side effects must be coordinated, consider the transactional outbox pattern and idempotent workflows.

### 37.7. Multi-Host libpq / Driver Differences

Do not confuse pgJDBC config syntax with `libpq`/`psql` or other drivers. For example, libpq uses `connect_timeout` (underscore) in connection parameters, whereas pgJDBC uses `connectTimeout` (camelCase). Check units and defaults in the specific client library documentation.

## 38. Practice Exercises with Answers

These exercises use a PostgreSQL + Java/JDBC model with the `timeout402` schema where needed. Only run cancellation or termination on sessions you own in a lab database.

### Exercise 1. What is pool checkout timeout?

**Answer:** the time a client waits for `getConnection()` to receive a connection from the pool; not how long an SQL statement runs on the server.

### Exercise 2. What unit does HikariCP `connectionTimeout` use?

**Answer:** milliseconds.

### Exercise 3. What unit does pgJDBC `connectTimeout` use?

**Answer:** seconds; it covers the socket connect operation, not query execution.

### Exercise 4. How does `loginTimeout` differ from `connectTimeout`?

**Answer:** `loginTimeout` controls driver-managed connection/login establishment time, whereas `connectTimeout` focuses on the socket connection operation.

### Exercise 5. What does `socketTimeout` measure?

**Answer:** the wait time for a single socket read, not an absolute wall-clock deadline for the entire query.

### Exercise 6. Why does a 5s `socketTimeout` not prove a `SELECT` was rolled back on the server?

**Answer:** the error occurred at the client transport layer; the server may still be running or may have already finished. You must verify the actual outcome.

### Exercise 7. Which Java API sets a query timeout?

```java
ps.setQueryTimeout(5);
```

**Answer:** the JDBC Statement-level timeout, in seconds.

### Exercise 8. Which PostgreSQL setting bounds SQL execution time?

**Answer:** `statement_timeout`.

### Exercise 9. What does `statement_timeout=0` mean?

**Answer:** disables the timeout limit at this layer; it does not mean all other timeouts are disabled.

### Exercise 10. How do you set a 1.5-second statement timeout in PostgreSQL?

```sql
SET statement_timeout = '1500ms';
```

**Answer:** a setting with explicit time units.

### Exercise 11. Is a `SELECT` waiting on a lock subject to `statement_timeout`?

**Answer:** yes; lock wait time counts toward statement execution time.

### Exercise 12. How does `lock_timeout` differ from `statement_timeout`?

**Answer:** `lock_timeout` bounds waiting to acquire a lock; `statement_timeout` bounds the entire statement.

### Exercise 13. Why should `lock_timeout` be smaller than `statement_timeout` in the same scenario?

**Answer:** if `statement_timeout` expires first, a longer `lock_timeout` will practically never take effect.

### Exercise 14. What is the SQLSTATE for query cancel / statement timeout?

**Answer:** `57014`.

### Exercise 15. What SQLSTATE is commonly seen with `lock_timeout`?

**Answer:** `55P03`, which can also appear when `NOWAIT` fails to acquire a lock.

### Exercise 16. What is the SQLSTATE for a deadlock?

**Answer:** `40P01`.

### Exercise 17. What is the SQLSTATE for a serialization failure?

**Answer:** `40001`.

### Exercise 18. What is the SQLSTATE when executing another query inside an aborted transaction?

**Answer:** `25P02`.

### Exercise 19. How do you check current settings?

```sql
SHOW statement_timeout;
SHOW lock_timeout;
```

**Answer:** `SHOW` or querying `pg_settings`.

### Exercise 20. What advantage does `SET LOCAL` offer with a connection pool?

**Answer:** the timeout applies only within the transaction, avoiding leaking session-level settings to subsequent requests when used in the proper scope.

### Exercise 21. In what kind of transaction should `SET LOCAL` run?

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SELECT 1;
COMMIT;
```

**Answer:** an explicit transaction ensures the proper scope.

### Exercise 22. Does changing a role default immediately affect already-open physical connections?

**Answer:** it does not automatically change already established sessions; manage connection lifecycle and inspect effective config.

### Exercise 23. Why shouldn't role default timeouts be identical for APIs and migrations?

**Answer:** their workloads and valid durations differ; API timeouts can break legitimate long migrations or reports.

### Exercise 24. What does `idle_in_transaction_session_timeout` do?

**Answer:** terminates a session that sits idle while keeping a transaction open too long, freeing the transaction and its locks.

### Exercise 25. How can `idle_session_timeout` affect HikariCP?

**Answer:** PostgreSQL closes idle backends, so the pool may hold stale connections if they are not detected or validated properly.

### Exercise 26. Does PostgreSQL 16 have `transaction_timeout`?

**Answer:** no; this setting was added starting in PostgreSQL 17.

### Exercise 27. How does `transaction_timeout` differ from `statement_timeout`?

**Answer:** it bounds the lifetime of the entire transaction, not just an individual statement.

### Exercise 28. Does JDBC `Statement.cancel()` close the connection?

**Answer:** its primary goal is to cancel the statement; the connection can remain open, though you still need to check transaction and driver state.

### Exercise 29. Can one `Connection` run SQL concurrently across multiple threads to go faster?

**Answer:** no; enforce connection ownership and thread safety. A control thread calling `cancel()` is different from arbitrarily running statements concurrently on the same connection.

### Exercise 30. Why is `cancelSignalTimeout` not `queryTimeout`?

**Answer:** it bounds the communication to deliver the cancel request, not the full execution of the statement.

### Exercise 31. How does `pg_cancel_backend` differ from `pg_terminate_backend`?

**Answer:** cancel requests stopping the currently running query; terminate requests ending the entire backend/session.

### Exercise 32. If `pg_cancel_backend(pid)` returns `true`, does that guarantee the transaction rolled back?

**Answer:** no. Observe the actual outcome and state; it may race with a query that already completed.

### Exercise 33. How do you find the PID of the current session?

```sql
SELECT pg_backend_pid();
```

**Answer:** returns the PostgreSQL backend process ID for the connection.

### Exercise 34. What privilege is needed to cancel another user's session?

**Answer:** privileges under the PostgreSQL role/ownership/signal model, such as `pg_signal_backend` or superuser when appropriate; never grant broadly.

### Exercise 35. What do you use to find sessions waiting on locks?

**Answer:** `pg_stat_activity.wait_event_type = 'Lock'` and `pg_blocking_pids(pid)`.

### Exercise 36. Does `state = 'active'` mean the CPU is always busy?

**Answer:** no; an active backend may be waiting on a lock, I/O, or network according to instrumented wait events.

### Exercise 37. Why is `state = 'idle in transaction'` dangerous?

**Answer:** it can hold locks and snapshots, block vacuum, and extend transaction age even while running no query.

### Exercise 38. If a `SELECT` fails inside `BEGIN`, can you immediately run another `SELECT`?

**Answer:** usually no; an aborted transaction requires `ROLLBACK` or handling via a savepoint per transaction semantics.

### Exercise 39. Why does `rollback()` in Java also need a `catch` block?

**Answer:** a network failure may render the connection unusable; `rollback()` itself can throw an `SQLException`, so preserve the original exception and record the rollback error.

### Exercise 40. Does a socket failure during `COMMIT` prove the DB did not commit?

**Answer:** no. It can be an unknown outcome; use idempotency and reconciliation.

### Exercise 41. What must an idempotency key protect?

**Answer:** each business request gets a unique key/unique constraint, retries reuse the same key without repeating side effects, and payload consistency is verified.

### Exercise 42. Is retrying `57014` after a user clicked Cancel reasonable?

**Answer:** usually no, because it contradicts the user's intent.

### Exercise 43. When retrying `40001`, is retrying only the final `UPDATE` enough?

**Answer:** typically you must retry the **entire transaction**, including the business decision logic.

### Exercise 44. Why do bounded retries need backoff and jitter?

**Answer:** to avoid retry storms that amplify load and contention while the DB is struggling.

### Exercise 45. Does HTTP 504 automatically stop the query?

**Answer:** you cannot assume so; the application must propagate cancellation or server timeouts must bound the query.

### Exercise 46. Does a 12s socket timeout enforce an 8s HTTP deadline?

**Answer:** no. You need application deadlines and cancellation with remaining time budgets.

### Exercise 47. Does TCP keepalive replace `statement_timeout`?

**Answer:** no. TCP keepalive checks network connection viability; it does not limit query runtime.

### Exercise 48. Is Hikari `maxLifetime` equivalent to PostgreSQL `transaction_timeout`?

**Answer:** no. `maxLifetime` manages connection lifecycle inside the pool; `transaction_timeout` is a server-side transaction limit introduced in PostgreSQL 17.

### Exercise 49. How does PgBouncer transaction pooling affect session `SET`?

**Answer:** a client session may not remain pinned to the same backend across transactions; state, `SET`, and prepared statements must match the pooler config and version.

### Exercise 50. Draft a timeout budget for an HTTP API

**Suggested answer:** set an overall HTTP deadline; limit pool checkout; limit connect/login; set `lock_timeout` lower than `statement_timeout`; add JDBC query timeout/cancel; use a longer `socketTimeout` as a transport backstop; propagate remaining budget, ensure rollback/cleanup, and inspect SQLSTATE.

### Exercise 51. How can you test `lock_timeout` without disrupting a real database?

**Answer:** create a lab table, open two connections; Session A updates a row inside `BEGIN` without committing; B runs `SET LOCAL lock_timeout` and updates the same row; after the error, roll back B and roll back A.

### Exercise 52. What should you do if an `ALTER TABLE` migration hits `lock_timeout`?

**Answer:** roll back if needed, investigate the blocker and deployment timing, optimize the migration/lock acquisition, and retry according to plan; never raise the timeout indefinitely.

### Exercise 53. How do `query_start` and `xact_start` differ?

**Answer:** `query_start` is when the current or last query began according to session state; `xact_start` is when the transaction began. They are not interchangeable.

### Exercise 54. Pool checkout timeouts spike while SQL duration is normal: what do you investigate?

**Answer:** leaks, long transactions holding connections, pool sizing, concurrency, physical connect failures, and connection close/return behavior.

### Exercise 55. What if a query is canceled and the app still tries to `COMMIT` the transaction?

**Answer:** the transaction may be aborted; you must roll back or roll back to a savepoint per semantics. Never try to commit a failed transaction and assume the data is valid.

### Exercise 56. If the driver reports `08xxx` after an `INSERT`, should you retry immediately?

**Answer:** evaluate auto-commit/commit boundaries and idempotency; it may be an unknown outcome, so never blindly retry writes.

### Exercise 57. How do you distinguish a slow query from a lock wait?

**Answer:** inspect `pg_stat_activity`, `wait_event_type`, `pg_blocking_pids`, query plans, and metrics; both increase latency, but their remediation differs.

### Exercise 58. What timeout suits a 10-minute background report?

**Answer:** a dedicated configuration with an appropriate job deadline, server `statement_timeout`, pool, and monitoring; never reuse an interactive API's 5-second timeout.

### Exercise 59. Why use server `statement_timeout` as a backstop?

**Answer:** it cancels SQL inside PostgreSQL when the client, proxy, or app layer fails to monitor it properly, within the configured scope.

### Exercise 60. Write a checklist for handling a “timeout” error before retrying

**Suggested answer:**

1. Determine whether the timeout occurred at HTTP, pool, connect, socket, JDBC, SQL, lock, or transaction level.
2. Capture the SQLSTATE and message from reliable sources.
3. Determine whether the statement/transaction failed, aborted, completed, or has an unknown outcome.
4. Check whether the connection is healthy or must be discarded.
5. Roll back the appropriate scope if still possible.
6. Check authorization and idempotency before retrying.
7. Check whether request deadline budget remains.
8. Use bounded backoff/jitter if retrying is allowed.
9. Monitor pool, `pg_stat_activity`, and lock blockers.
10. Record metrics and follow a runbook to fix the root cause rather than just extending timeouts.

## 39. Quick Decision Matrix

| Situation | First Observation | Initial Action |
| --- | --- | --- |
| `getConnection()` timeout | Hikari pending/active | Check for leaks, long transactions, pool pressure |
| PostgreSQL rejects TCP connection | Driver connect error | Check DNS/port/TLS/auth/`max_connections` |
| Query runs long without lock wait | `pg_stat_activity`, `EXPLAIN` | Query/index tuning/`statement_timeout` |
| Query waiting on lock | `wait_event_type` Lock, `pg_blocking_pids` | Find/reduce blocker, `lock_timeout` |
| JDBC timeout with `57014` | SQLSTATE and server logs | Roll back transaction, review retry policy |
| Driver read/socket timeout | Socket/`08xxx`, network logs | Assess broken connection/unknown outcome |
| Backend idle in transaction | `state`/`xact_start` | Roll back/terminate per runbook |
| Canceled by user request | Request cancellation event | Do not auto-retry |
| DB session terminated | Connection error/backend logs | Discard connection, reconnect |
| `COMMIT` response lost | Idempotency record | Reconcile, do not retry blindly |
| HTTP 504 while DB query still runs | Backend active/`application_name` | Propagate cancel/deadline |
| Migration hits `lock_timeout` | Blockers, DDL lock requirements | Plan retry/maintenance window |
| Pool has stale connections after idle | Network/proxy/pool metrics | Tune keepalive/validation/lifetime |

## 40. Production Deployment Checklist

| Check | Expectation |
| --- | --- |
| Distinguish pool checkout vs. physical connect? | Separate metrics |
| Application-level request deadline? | Present |
| Propagate cancel when request ends? | Clear policy |
| PostgreSQL `statement_timeout` configured? | Tuned per workload |
| Reasonable `lock_timeout`? | Lower than statement timeout where needed |
| Idle-in-transaction addressed? | Timeout and short transaction boundaries |
| Need PG17+ `transaction_timeout`? | Version verified |
| pgJDBC configured in correct units? | Seconds on relevant properties |
| Hikari configured in correct units? | Milliseconds |
| `socketTimeout` acts as transport backstop? | Does not replace statement timeout |
| Reasonable `cancelSignalTimeout`? | Not confused with query timeout |
| TCP/pool keepalive configured? | Aligned with network policies |
| PgBouncer/proxy present? | Pooling mode and timeout layers understood |
| `SET LOCAL` used to prevent session leakage? | Where appropriate |
| Separate role defaults for API vs. migration? | Present |
| `Statement.setQueryTimeout` used? | Follows request budget |
| `Statement.cancel` called safely? | No arbitrary sharing of `Connection` |
| Rollback after `SQLSTATE 57014` in a txn? | Present |
| Discard broken connections? | Follows driver/pool contract |
| SQLSTATE-based error handling? | Not just substring matching |
| Idempotency for write operations? | Present |
| Policy for unknown commit outcomes? | Present |
| Bounded retries/backoff/jitter? | Present |
| Concurrency limits enforced? | Present |
| `pg_stat_activity` and blocker queries ready? | Present |
| Monitoring for idle transactions? | Present |
| Query/lock timeout logging enabled? | Follows privacy policy |
| Meaningful `application_name` set? | Contains no secrets |
| Staging fault-injection tests run? | Present |
| Failover/proxy idle tests run? | When infrastructure applies |
| JDBC pool exhaustion tests run? | Present |
| Cancellation race tests run? | Present |
| Query/lock/network latency dashboard? | Present |
| Verified-PID cancel/terminate runbook? | Documented and restricted |
| Slow SQL plans reviewed? | `EXPLAIN ANALYZE BUFFERS` |
| Timeouts reviewed before migrations? | Present |
| Report/export jobs isolated with limits? | Present |
| Retry amplification monitored? | Present |
| Recovery path tested for DB errors? | Present |

## 41. Summary

When PostgreSQL or Java reports a “timeout,” the first step is not doubling every threshold; it is **identifying exactly which layer timed out and what happened on the server**.

Key takeaways:

1. **Pool `connectionTimeout`** is the wait to borrow a connection, not an SQL timeout.
2. **pgJDBC `connectTimeout`/`loginTimeout`** govern physical connection establishment.
3. **pgJDBC `socketTimeout`** bounds a network read wait; it does not guarantee the server query was canceled.
4. **JDBC `setQueryTimeout`** can trigger a statement cancel request; `cancelSignalTimeout` controls sending that request.
5. **PostgreSQL `statement_timeout`** is a server-side limit on statement duration and can cancel queries waiting on locks.
6. **`lock_timeout`** specifically limits waiting for lock acquisition; it is not deadlock detection.
7. **`idle_in_transaction_session_timeout`** guards against connections left idle inside transactions and can free locks by terminating the backend.
8. **`idle_session_timeout`** can affect pooled idle connections; coordinate pool and network policies.
9. **`transaction_timeout` (PostgreSQL 17+)** bounds transaction lifetime rather than only individual statements.
10. **`SET LOCAL`** fits transaction-scoped timeouts in many pooled applications.
11. **`Statement.cancel()` and `pg_cancel_backend`** request statement cancellation; **`pg_terminate_backend`** terminates the session.
12. **Cancel is not an instant confirmation**; account for races, error responses, and backend state.
13. **Query errors in an explicit transaction usually require `ROLLBACK`**; otherwise subsequent commands fail with `25P02`.
14. **Network failures/timeouts around `COMMIT` can leave the outcome ambiguous**. Use idempotency and reconciliation before retrying writes.
15. **HTTP 504 does not guarantee the database query stopped**. Propagate deadlines and cancellation down to the database layer.
16. **Connection pools, PostgreSQL backends, OS, and proxies have independent thresholds**. Design across the entire request path.
17. **SQLSTATE classifies root causes**: `57014`, `55P03`, `40P01`, `40001`, `08xxx`, `25P02`.
18. **`pg_stat_activity`, `pg_blocking_pids`, and logs** are essential for distinguishing slow queries from lock waits and idle transactions.
19. **Retries must be bounded and idempotent**, with deadlines and backoff; user-initiated cancellations should not auto-retry.
20. **Timeouts are a safety net, not a replacement for query tuning or transaction design**. Proper indexing, short locks, and healthy pool lifecycles remain the foundation.

Reference pattern for handling a transactional JDBC request:

```text
1. Borrow connection from pool with checkout deadline
2. Ensure appropriate connect/network settings
3. BEGIN / setAutoCommit(false)
4. SET LOCAL lock_timeout, statement_timeout as needed
5. Execute prepared SQL with query deadline
6. On cancel/error: inspect SQLSTATE, ROLLBACK
7. On commit network failure: outcome UNKNOWN -> reconcile
8. Close statement/result set/connection
9. Retry only if idempotent, budget remains, and policy allows
```

**Final rule:** whenever you see the word “timeout,” ask: **“What ran out of time — pool, driver, socket, PostgreSQL statement, lock, or transaction? Did the cancel request reach the server? What state are the connection and transaction in now? If we retry, could we cause a duplicate effect?”** Asking those four questions helps build more reliable PostgreSQL + Java systems and resolve incidents faster.
