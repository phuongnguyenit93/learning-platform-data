# Testing Disconnects, Timeouts, Deadlocks, and Retry Safety

Applications using Oracle JDBC must handle scenarios where the database or network does not respond as expected. Connections can drop mid-SQL submission, queries can exceed timeouts, transactions can block on row locks, two sessions can form a deadlock, and clients can lose connectivity right during `COMMIT`.

The hardest part is not merely catching `SQLException`. When the client receives an error, the database-side transaction state may already differ from what the application assumes. Specifically, if a connection drops during `COMMIT`, the application may not know whether the transaction committed or not. Blindly retrying can create duplicate orders, payments, or side effects.

This lesson builds intentional testing practices for those failure modes. The focus is reproducing deterministic scenarios across multiple sessions, distinguishing timeouts across layers, determining transaction outcomes, designing idempotency, and executing bounded full-transaction retries.

After this lesson, you will be able to:

- Distinguish connect errors, response read errors, query timeouts, lock wait timeouts, and transaction timeouts.
- Test disconnects at different points within a transaction.
- Explain ambiguous commits and how to verify transaction outcomes.
- Produce controlled Oracle deadlocks using two sessions.
- Distinguish statement rollback from full-transaction rollback.
- Classify retryable errors versus errors requiring data/configuration fixes.
- Design idempotency keys, unique constraints, and transactional outboxes.
- Apply bounded retries, exponential backoff, and jitter.
- Handle broken connections in JDBC connection pools.
- Write repeatable integration tests and gather diagnostic evidence.
- Measure RPO/RTO and verify proper application recovery after incidents.

> Oracle errors, timeout properties, and failover behavior may vary by Oracle Database release, Oracle JDBC driver, pool implementation, and RAC/Data Guard topology. Run fault injection inside an isolated lab database/schema. Never intentionally sever networks, kill sessions, or exhaust resources on production to test.

## 1. Failure model from application to Oracle

### 1.1. Layers where failures can originate

A JDBC request traverses multiple layers:

```text
APPLICATION
    |
    v
JDBC CONNECTION POOL
    |
    v
ORACLE JDBC DRIVER
    |
    v
TCP / TLS / NETWORK
    |
    v
LISTENER / SERVICE
    |
    v
ORACLE SESSION
    |
    v
SQL EXECUTION / LOCK / TRANSACTION
    |
    v
REDO / COMMIT / STORAGE
```

An exception at the application layer does not necessarily indicate where the failure originated. For example:

- A connect timeout can occur before a database session is ever created.
- A read timeout can occur after SQL has been transmitted and is actively running.
- A socket reset can occur before, during, or after `COMMIT`.
- A query timeout can trigger the driver to send a cancel request, though canceling also requires a working network.
- A pool can hand out a dead connection undetected if its validation policy is misconfigured.

### 1.2. Failure modes and questions to answer

| Failure mode | Operational question |
| --- | --- |
| Connect failure | Was a session ever created? |
| Network disconnect | Did the server receive the request? |
| Read timeout | Is the SQL still running or did it finish? |
| Query timeout | Was the statement canceled? Is the transaction still open? |
| Lock wait timeout | Which lock is the session waiting on? |
| Deadlock | Which statement was chosen as victim? Are uncommitted changes left in the transaction? |
| Commit response lost | Did the transaction commit or not? |
| Database restart/failover | Are old connections still valid? What is the transaction outcome? |

### 1.3. Retryable errors and indeterminate states

An error occurring before sending a request is generally safer to retry because the database has not executed the operation yet. However, if an error occurs after the request was sent, the client may not know how far the server progressed.

Classification must depend on the operation and timing:

- **Definitely not sent:** evidence confirms the request never reached the database.
- **Sent, outcome known failed:** the database returned a definitive error and transaction/statement semantics guarantee the operation failed.
- **Sent, outcome unknown:** the client lost the response, especially during `COMMIT`.
- **Succeeded and acknowledged:** the client received explicit success confirmation.

Never infer "rolled back" solely because JDBC threw a `SQLException` or the connection closed.

## 2. Transactions and commit outcomes

### 2.1. Auto-commit

JDBC connections typically default to auto-commit. When auto-commit is enabled, each statement commits as its own transaction upon successful execution per JDBC semantics.

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(true);

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE account SET status = ? WHERE account_id = ?")) {
        ps.setString(1, "ACTIVE");
        ps.setLong(2, accountId);
        int rows = ps.executeUpdate();
    }
}
```

If the connection drops during `execute`, the client may never receive the update count even though the server executed the statement. Under auto-commit, the transaction boundary is tied to the statement, so the client can still face an indeterminate outcome.

### 2.2. Explicit transactions

When multiple DML statements must be atomic, disable auto-commit and manage commit/rollback explicitly:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debit(connection, fromAccount, amount);
        credit(connection, toAccount, amount);
        insertTransferAudit(connection, requestId);
        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

This snippet shows a basic transaction boundary. If the failure is a network disconnect, calling `rollback` on the broken connection will likely fail; a failed rollback does not prove whether the server rolled back or committed. When connectivity drops, the database handles the session/transaction based on server state and failure detection.

### 2.3. COMMIT has two sides

A commit involves the server-side commit and the response back to the client:

```text
CLIENT                         ORACLE
  |                              |
  |----------- COMMIT ---------->|
  |                              | Commit transaction
  |                              | Persist commit record
  |<--------- SUCCESS -----------|
  |                              |
```

If the connection breaks after the server commits but before the response reaches the client, the database has committed while the application sees an exception.

### 2.4. Ambiguous commits

This is the scenario where the commit outcome is unknown from the client's perspective. Example:

```text
CLIENT                         ORACLE
  |                              |
  |----------- COMMIT ---------->|
  |                              | Commit succeeds
  |          X NETWORK CUT        |
  |                              |
  |---- SQLException / timeout   |
  |                              |
  | Client does not know whether |
  | commit completed or not      |
```

Never blindly retry the entire business operation with a brand new request ID. If the first transaction committed, the retry will trigger a duplicate side effect.

### 2.5. Verifying outcome after reconnect

Design transactions to record a unique request identifier alongside the business mutation. After reconnecting, look up the request ID:

- Committed record found: return the stored result.
- No record found: the request may not have committed or the old transaction may still be finishing; retry with the same request ID so a unique constraint arbitrates, or wait/reconcile per protocol.
- In-progress status found: check owner/lease and proceed according to a bounded state machine.

A query immediately finding no record is not absolute proof that the old transaction failed to commit; the old request could still be in flight.

## 3. Idempotency and safe retries

### 3.1. Idempotent operations

An idempotent operation can be executed repeatedly with the same identity while producing the same final business state as executing it once. HTTP `PUT` illustrates the concept; in a database, idempotency must be engineered using unique keys and transactions.

For example, a client submits a payment request with a fixed `request_id`. Every retry of that same request must reuse the exact same `request_id`.

### 3.2. Deduplication table

```sql
CREATE TABLE request_dedup (
    request_id      VARCHAR2(64) PRIMARY KEY,
    request_hash    VARCHAR2(64) NOT NULL,
    result_code     VARCHAR2(30),
    result_payload  CLOB,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

`request_id` identifies the request. `request_hash` detects if a client reuses the same key for a different payload. Never store only the key while skipping payload validation.

### 3.3. Atomicity between dedup record and business DML

The dedup record and business data must commit inside the same database transaction:

```java
connection.setAutoCommit(false);
try {
    insertRequestKey(connection, requestId, requestHash);
    createOrder(connection, order);
    String result = buildResult(order);
    saveRequestResult(connection, requestId, result);
    connection.commit();
    return result;
} catch (SQLException e) {
    rollbackQuietly(connection, e);
    throw e;
}
```

If the transaction rolls back, both the request key and business DML roll back. If commit succeeds but the response is lost, the stored request key and result remain for the retry to look up.

### 3.4. Handling duplicate requests

When inserting `request_id` hits a unique constraint violation (`ORA-00001`), the application must not blindly return a generic error. It should read the existing record:

1. Compare `request_hash`.
2. If the hash differs, reject because the same key was reused for a different payload.
3. If the hash matches and a completed result exists, return the stored result.
4. If the state is still pending, wait/reconcile per protocol; never re-run business DML in parallel.

In a single-transaction model, the request row and result commit together, so clients only observe the row once business DML has committed. For multi-transaction workflows, define explicit state machines/leases/ownership and recovery policies.

### 3.5. Contention on the same request_id

Two concurrent requests sharing the same `request_id` contend on the unique key. The Oracle unique constraint guarantees two committed rows never share the key. One transaction may wait for the other to commit/roll back; afterward the insert succeeds or fails with `ORA-00001`.

When handling `ORA-00001`, treat it as a duplicate request only if the violated constraint is specifically the idempotency key. Never catch any unique violation and return an old result; the error might stem from a different business key.

### 3.6. Transactional outbox

If a business transaction must also send emails, publish messages, or call payment providers, avoid holding a database transaction open while calling external services. Write an outbox event inside the same transaction as the business data:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR2(64) PRIMARY KEY,
    aggregate_id   VARCHAR2(64) NOT NULL,
    event_type     VARCHAR2(100) NOT NULL,
    payload        CLOB NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    published_at   TIMESTAMP
);
```

A worker reads the outbox and publishes according to a retry policy. Consumers must also be idempotent since message delivery can repeat. An outbox prevents situations where the database commits successfully but the process crashes before emitting the message.

### 3.7. Never blindly retry external side effects

If a client calls a payment API, sends an email, or publishes an event and loses the response, the external side effect may also have an indeterminate outcome. Use provider idempotency keys, transactional outboxes, consumer-side inbox/dedup, or reconciliation APIs. A database `request_id` does not automatically make external services idempotent.

## 4. Timeout types and impact scope

### 4.1. Connect timeout

Connect timeout bounds the time spent establishing a network/database connection. It typically fires before the application obtains a usable connection and before any business transaction is sent over it.

In Oracle JDBC Thin, common properties include:

- `oracle.net.CONNECT_TIMEOUT`: time to wait for endpoint connection in units defined by driver/release.
- `oracle.net.OUTBOUND_CONNECT_TIMEOUT`: Oracle Net outbound connection timeout.

Verify units and precedence across URLs, connection properties, `DESCRIPTION`/`ADDRESS`, and pools against your driver/Oracle Net version. Never assume a pool-level timeout replaces Oracle Net timeouts.

### 4.2. Read/socket timeout

Read timeout bounds how long to wait for socket data after a connection is established. Oracle JDBC Thin typically exposes `oracle.jdbc.ReadTimeout` in milliseconds in supporting drivers.

A read timeout can trigger while a query is running or while awaiting a response. It does not prove the server halted the SQL or rolled back the transaction. After a socket read failure, the connection must generally be treated as untrustworthy and evicted from the pool.

### 4.3. Statement query timeout

JDBC `Statement.setQueryTimeout` takes seconds:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT * FROM large_table WHERE status = ?")) {
    ps.setString(1, "PENDING");
    ps.setQueryTimeout(10);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // process rows
        }
    }
}
```

When exceeded, the driver attempts to cancel the statement and typically throws a `SQLException`. This is a JDBC cancel request; it is not an end-to-end deadline for the entire request and does not automatically roll back prior statements in the transaction.

### 4.4. Lock wait timeout

Lock wait timeout bounds how long a statement waits for a resource lock. Oracle supports syntax like `SELECT FOR UPDATE WAIT n` and `NOWAIT`:

```sql
SELECT *
FROM inventory
WHERE item_id = :item_id
FOR UPDATE WAIT 5;

SELECT *
FROM inventory
WHERE item_id = :item_id
FOR UPDATE NOWAIT;
```

`WAIT 5` bounds the lock wait in seconds; `NOWAIT` errors immediately if the lock cannot be acquired. DML `UPDATE`/`DELETE` statements wait on row locks by default until the blocking transaction/SQL finishes or is canceled.

### 4.5. DDL lock timeout

DDL can wait on object locks. Oracle provides `DDL_LOCK_TIMEOUT` in supporting releases to set DDL lock wait duration. It is not a general timeout for DML/queries:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 10;
```

Verify privileges, release support, and session/system scope before applying.

### 4.6. Application-layer transaction timeout

JDBC has no single portable transaction timeout guaranteeing the server automatically rolls back every transaction upon expiration. Frameworks can track deadlines and issue statement cancels/rollbacks, but the network may already be lost and server outcomes must be handled separately.

Set deadlines at the request layer, propagate remaining budgets down to pools/statements/services, and still maintain server-side lock/query controls and transaction cleanup.

### 4.7. Timeout does not mean cancel succeeded

When the client times out, the cancel request can be lost due to a network partition. The server may continue executing until the session is detected dead or the statement finishes on its own. Therefore:

- Monitor server-side sessions and SQL in the lab.
- Measure elapsed time from client timeout to server termination.
- Inspect transactions/locks after timeouts.
- Never return a failed connection back to the pool.

### 4.8. Layering timeouts in order

Design timeouts around an overall deadline. For example, 2s pool acquisition, 3s connect, 8s statement, and 12s request deadline is an illustrative budget; leave room for rollback/cleanup/serialization and network jitter. Never set lower-layer timeouts longer than upper-layer deadlines if upper layers must respond sooner.

## 5. Configuring timeouts for Oracle JDBC

### 5.1. Thin driver properties

Example properties for Oracle JDBC Thin:

```java
Properties properties = new Properties();
properties.setProperty("user", dbUser);
properties.setProperty("password", dbPassword);
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");
properties.setProperty("oracle.jdbc.ReadTimeout", "15000");

Connection connection =
    DriverManager.getConnection(jdbcUrl, properties);
```

This is an illustrative example; confirm units and property names in the Oracle JDBC guide for your active driver. Never log passwords or commit them to source control.

### 5.2. JDBC URL

Certain Oracle Net timeouts can be configured inside the connect descriptor:

```text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=5)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=db.example)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=APP_SERVICE))
)
```

Descriptor attributes have their own syntax and units. Never mix seconds values with milliseconds properties. Use official descriptor syntax for your release and test multi-address/failover connects as well.

### 5.3. setQueryTimeout

Query timeout is a statement property:

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setQueryTimeout(5);
    // bind parameters
    ps.executeUpdate();
}
```

The timeout is in seconds, not milliseconds. Never pass `5000` intending 5 seconds.

### 5.4. setNetworkTimeout

JDBC `Connection` provides `setNetworkTimeout(Executor, milliseconds)` since JDBC 4.1. Driver support is required. On timeout, the driver may abort the connection; behavior is driver-dependent:

```java
Executor executor = Executors.newFixedThreadPool(1);
connection.setNetworkTimeout(executor, 15_000);
```

Manage the `Executor` lifecycle and avoid sharing a shut-down executor across connections. Check driver behavior; network timeout does not replace Oracle Net connect timeout or application deadlines.

### 5.5. Pool acquisition timeout

Connection pools typically enforce a maximum wait time when acquiring a connection. A timeout here means the pool could not supply a connection within the budget; it is not a query timeout and says nothing about database execution.

Monitor active/idle/pending pool counts, acquisition latency, leak detection, and validation failures. When a pool exhausts because connections are held waiting on locks, increasing pool size may only amplify load and lock contention.

### 5.6. Validation timeout

`Connection.isValid(timeout)` and pool validation queries help detect dead connections. Validation timeout is the budget for the health check; a passing validation check does not guarantee the connection stays alive until the next statement executes.

### 5.7. Oracle Net keepalive and dead connection detection

TCP keepalive and Oracle Net Dead Connection Detection help detect dead connections in certain failure modes, particularly network partitions that send no FIN/RST. Detection takes time and depends on OS/network/Oracle Net settings. Never treat keepalive as a request timeout.

### 5.8. Timeout matrix

| Timeout | Common unit | What it protects | On expiration |
| --- | --- | --- | --- |
| Pool acquisition | seconds | Waiting for a connection from the pool | Pool fails to supply a connection |
| Oracle Net connect | depends on property/descriptor | Establishing TCP/service connection | Connect attempt fails |
| JDBC ReadTimeout | milliseconds in Oracle JDBC Thin | Waiting for socket response | Driver throws read/timeout error; connection may be broken |
| `Statement.setQueryTimeout` | seconds | Statement execution | Driver attempts to cancel statement |
| `SELECT FOR UPDATE WAIT` | seconds | Statement waiting on row lock | Oracle reports resource busy/lock timeout |
| `Connection.setNetworkTimeout` | milliseconds | Network operations on connection | Driver may abort connection |
| Application deadline | application-defined | Entire request/workflow | Application stops waiting and handles compensation/outcome |

Do not sum timeouts mechanically; one timeout can overlap with or trigger another depending on driver/pool.

## 6. Testing disconnects by timing point

### 6.1. Fault injection matrix

Disconnect testing must specify where the fault is injected:

| Breakpoint | Could server have received request? | Client outcome |
| --- | --- | --- |
| Before sending SQL | Usually no | Connect/write error |
| After sending SQL, before server finishes | Yes | Read timeout/reset; statement may still run |
| After DML, before `COMMIT` | Yes | Session/transaction may linger until server detects disconnect |
| During `COMMIT` | Yes | Outcome may be unknown |
| After server commit, before response | Yes, already committed | Client sees exception while transaction committed |
| After client receives success | Committed per response | Request succeeded; reconnect needs no retry |

Fault injection should use a proxy/network tool or dedicated harness to drop connections deterministically while recording timestamps on both sides.

### 6.2. Testing before sending the request

Block connectivity prior to executing the statement. Verify the application does not report business success, the connection is not reused, and retrying creates only a single business operation. This tests connect/transport establishment.

### 6.3. Testing after the server receives DML

In an explicit transaction, run DML and cut the network before commit. Then inspect server sessions/transactions in the lab. Once the session closes and the transaction rolls back, data disappears; however, how quickly the server detects the dead connection depends on network detection settings.

### 6.4. Testing during COMMIT

This is the most critical test for ambiguous outcomes. Create a transaction with a `request_id`, use a proxy to drop the response inside the commit window, and observe:

- Client receives `SQLException`/timeout.
- Whether the database has the dedup/business row.
- Whether retrying with the same `request_id` creates duplicates.
- Whether the application returns the stored result or re-executes business DML.

Never rely on fixed sleeps to hit the commit window. Use a proxy/test hook that blocks the response path after the `COMMIT` request is sent, or instrument server/client timestamps.

### 6.5. Testing after commit

Commit successfully, receive confirmation, then close the connection. Verify reconnecting and querying still finds the committed data. This serves as the control baseline against ambiguous commits.

### 6.6. Network blackholes and TCP resets

Two distinct fault behaviors:

- TCP reset/connection refused is typically detected quickly.
- Blackhole/packet drop can force the client to wait until socket/read timeout or TCP retransmission timeout.

Test both because timeout behavior and recovery times differ.

### 6.7. Killing a database session

In a lab, a DBA can terminate a session to verify client error handling:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
```

Illustrative command; specify the exact `SID`/`SERIAL#` and instance on RAC. Killing a session does not fully emulate network disconnects or lost commit responses. Active transactions normally undergo rollback/cleanup per Oracle session termination rules.

### 6.8. Database shutdown/restart

Test instance restarts in an isolated environment to observe connection invalidation, recovery, and pool reconnection. Choose shutdown modes matching your lab scenario; never use `ABORT` on shared/production systems to induce test errors.

### 6.9. Assertions for disconnect tests

Each test must verify:

- Client exception type/vendor code/SQLState.
- The connection is marked unusable and never returned to the pool.
- Server-side transaction outcome after reconnect.
- Zero duplicate business rows.
- The request ID remains unchanged across retries.
- Metrics/logs retain enough timestamps for analysis.

## 7. Testing query timeouts and lock timeouts

### 7.1. Query timeout via JDBC

Create a long-running statement in the lab and set `setQueryTimeout`. One approach uses a PL/SQL sleep requiring `EXECUTE` on `DBMS_LOCK`:

```java
try (CallableStatement cs = connection.prepareCall(
        "BEGIN DBMS_LOCK.SLEEP(?); END;")) {
    cs.setInt(1, 30);
    cs.setQueryTimeout(5);
    cs.execute();
}
```

If `DBMS_LOCK` is not granted, use a lab query with sufficient workload and resource bounds. Never grant `DBMS_LOCK` broadly to production applications just for testing.

### 7.2. Verifying server-side cancel

After the client receives a query timeout, inspect sessions and SQL on the lab database. Verify the statement stopped within the expected window, locks were released, and check the remaining transaction state.

### 7.3. SELECT FOR UPDATE NOWAIT

Session A holds a row lock:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE item_id = 100;
-- Not committed yet
```

Session B:

```sql
SELECT *
FROM inventory
WHERE item_id = 100
FOR UPDATE NOWAIT;
```

Session B must receive a resource busy error immediately while Session A holds the lock. Roll back Session A after the test.

### 7.4. SELECT FOR UPDATE WAIT

Replace `NOWAIT` with `WAIT 3` to test lock timeout:

```sql
SELECT *
FROM inventory
WHERE item_id = 100
FOR UPDATE WAIT 3;
```

Hold the lock in Session A for more than 3 seconds and verify Session B fails with the corresponding lock timeout error. Error codes may vary by SQL form/release; assert vendor codes and scenario behavior rather than message text.

### 7.5. DML lock wait

Session A:

```sql
UPDATE inventory
SET quantity = quantity + 1
WHERE item_id = 100;
-- Not committed yet
```

Session B runs an `UPDATE` on the same row and observes the wait. DML lacks a universal `WAIT` clause like `SELECT FOR UPDATE`; rely on statement timeouts/application deadlines or controlled blocker transactions in the lab.

### 7.6. Cleanup

Always roll back Session A, close Session B, and verify initial row values. If a test fails mid-run, use `finally`/cleanup hooks so dangling locks never break subsequent tests.

## 8. Testing deadlocks

### 8.1. What is a deadlock?

A deadlock occurs when transactions hold resources needed by other transactions, forming a wait cycle. Oracle detects the deadlock and selects one statement as a victim to break the cycle. Applications typically receive `ORA-00060`.

A deadlock differs from an extended lock wait:

- Lock wait: one session waits on another; no cycle exists.
- Deadlock: a dependency cycle exists; Oracle detects and breaks the cycle.

### 8.2. Creating a lab table

```sql
CREATE TABLE deadlock_lab (
    id NUMBER PRIMARY KEY,
    value_text VARCHAR2(30)
);

INSERT INTO deadlock_lab VALUES (1, 'A');
INSERT INTO deadlock_lab VALUES (2, 'B');
COMMIT;
```

### 8.3. Two-session scenario

Open two SQL*Plus sessions or two separate JDBC connections.

Session A:

```sql
UPDATE deadlock_lab
SET value_text = 'A1'
WHERE id = 1;
-- Keep transaction open
```

Session B:

```sql
UPDATE deadlock_lab
SET value_text = 'B2'
WHERE id = 2;
-- Keep transaction open
```

Then Session A:

```sql
UPDATE deadlock_lab
SET value_text = 'A2'
WHERE id = 2;
-- Wait on Session B
```

While A is waiting, Session B:

```sql
UPDATE deadlock_lab
SET value_text = 'B1'
WHERE id = 1;
```

Session B needs row 1 held by A; A needs row 2 held by B. Oracle detects the cycle and returns `ORA-00060` to a victim statement/transaction.

### 8.4. Do not assume which session is always the victim

Oracle chooses the victim during deadlock detection; scheduling and execution order can cause either Session A or B to receive the error. Tests must accept either outcome while confirming the deadlock was detected and the cycle broken.

### 8.5. Statement rollback vs. transaction rollback

When Oracle detects a deadlock, the chosen victim statement is rolled back to break the cycle. Earlier statements in that same transaction may still remain pending. The application should roll back the entire business transaction and retry from the start if the operation is safe to retry.

Never assume `ORA-00060` automatically rolls back all prior DML in the transaction.

### 8.6. Confirming via alert/trace logs

Oracle writes a deadlock graph to the trace/diagnostic destination and alert log. The graph identifies involved resources, sessions, and SQL. DBAs use the graph to determine lock ordering and redesign transaction/access order.

### 8.7. Viewing blocking sessions

In the lab, inspect sessions/blockers:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    blocking_session,
    event,
    seconds_in_wait,
    sql_id
FROM v$session
WHERE username IS NOT NULL
ORDER BY blocking_session NULLS FIRST, sid;
```

`V$SESSION` shows blockers/waiters at query time; deadlock graphs/traces provide deeper detail on detected cycles.

### 8.8. Cleaning up the deadlock lab

After one session receives `ORA-00060`, roll back both sessions and verify initial values:

```sql
ROLLBACK;
SELECT * FROM deadlock_lab ORDER BY id;
```

In automated tests, roll back/close each connection inside `finally`. Never leave pending transactions open into the next test.

## 9. Designing to reduce deadlocks

### 9.1. Consistent access order

Whenever transactions lock multiple accounts/items, acquire locks in the same deterministic key order—such as ascending `account_id`. This reduces the chance of two transactions acquiring resources in opposite order.

Example:

```java
List<Long> ids = List.of(firstAccountId, secondAccountId)
    .stream()
    .sorted()
    .toList();

for (Long id : ids) {
    lockAccount(connection, id);
}
```

This is a guiding principle; ensure actual SQL/locking follows the defined order as well, including foreign keys, triggers, and index maintenance.

### 9.2. Keep transactions short

Never call REST APIs, wait for user input, process large files, or sleep while holding row locks. Move data preparation outside the transaction; keep transactions strictly to the window needed for atomic checks and writes.

### 9.3. Lock minimal row sets

Use selective predicates/indexes to avoid locking unintended rows. Inspect execution plans and actual row counts. An unindexed `UPDATE` predicate can scan broadly and increase contention.

### 9.4. Avoid read-then-write races

Reading a balance with `SELECT` and updating later can race. Use an atomic conditional `UPDATE` where feasible:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :id
  AND balance >= :amount;
```

Check the update count to verify the condition held. This eliminates the gap between read and write, though transactions and business validation are still necessary.

### 9.5. Foreign keys and indexes

DML on parent/child tables can interact via foreign key locks. Index foreign keys where workload warrants to reduce wide locking/scans. Analyze deadlock graphs before modifying indexes.

### 9.6. Deadlocks are not always Oracle bugs

`ORA-00060` usually reflects application lock ordering and workload concurrency. DBAs use the graph to identify SQL/resources; developers fix transaction access order or partition workloads. Increasing timeouts does not solve deadlocks because cycles must be broken.

## 10. Retry policies for Oracle JDBC

### 10.1. Retries must be conditional

Retry only when:

- The error is classified as transient/recoverable in that specific context.
- The business operation is idempotent or carries an idempotency key.
- The prior transaction rolled back or its outcome was verified.
- Time remains within the request deadline.
- Retry attempts have not exceeded the cap.
- Backoff will not amplify load during an outage.

### 10.2. Error classification

| Error/symptom | Common handling | Notes |
| --- | --- | --- |
| `ORA-00060` deadlock | Roll back transaction and retry full unit if safe | Reduce deadlocks via lock ordering; never retry single statement |
| `ORA-08177` serialization failure | Roll back and retry transaction | Common with `SERIALIZABLE`; must replay full transaction |
| `ORA-00054` resource busy `NOWAIT` | Bounded retry or report conflict | Depends on business semantics |
| `ORA-30006` lock wait timeout | Roll back/evaluate retry | Identify blocker and check deadline |
| `ORA-01013` user requested cancel | Do not auto-retry by default | Often from query timeout/cancel; clean up transaction |
| `ORA-01722` invalid number | Do not retry same input | Data/type conversion bug |
| `ORA-01861` date format mismatch | Do not retry same input | Fix mapping/format |
| `ORA-00001` unique constraint | Look up duplicate/idempotency | Treat as duplicate request only if idempotency constraint matched |
| `ORA-03113`/`03114`/`03135` | Connection lost; outcome may be unknown | Reconnect, verify idempotency/commit |
| `ORA-12541` no listener | Retry with backoff if service recovery expected | May indicate config or service outage |
| `ORA-12170`/`12535` timeout | Retry connect within deadline/circuit breaker | Distinguish connect vs. read stage |
| `ORA-12514` service unknown | Usually requires service registration/config fix | Do not spin-retry like transient network drops |

These are common guidelines, not blanket rules for every operation. Classify by SQLState, Oracle vendor code, exception class, transaction state, and application context.

### 10.3. Retrying the entire transaction

For deadlocks or serialization failures, retry the transaction unit from the beginning:

1. Roll back the current transaction.
2. Close/evict the connection if the connection is broken.
3. Wait for backoff.
4. Acquire a new valid connection if needed.
5. Start a fresh transaction.
6. Re-execute the entire business unit with the same idempotency key.
7. Commit and return the result.

Never replay only the final `UPDATE` if earlier statements were part of the atomic logic.

### 10.4. Exponential backoff

Backoff progressively increases wait time between retries to prevent synchronized retry spikes:

```text
attempt 1: 100 ms
attempt 2: 200 ms
attempt 3: 400 ms
attempt 4: 800 ms
```

Values are illustrative. Add random jitter and cap maximum delay. Backoff must fit inside the request deadline.

### 10.5. Jitter

If all clients retry at the exact same instant, the database suffers a retry spike (thundering herd). Jitter spreads retry attempts across a window. Full jitter typically picks a random delay from 0 up to the exponential cap; equal jitter and decorrelated jitter are common variants.

### 10.6. Retry limits

Enforce max attempts and max elapsed time. For example, 3 retries or 2 seconds total is an illustrative policy, not a universal rule. A request must never retry indefinitely or exceed the user's deadline.

### 10.7. Circuit breakers

If connect/service failures spike, a circuit breaker can temporarily reject new requests to the database/service and allow probes after a cooldown. It protects the pool and database from retry storms. Circuit breakers do not resolve transaction outcomes; ambiguous commits still require idempotency.

### 10.8. Do not stack retries across multiple layers

If the DAO retries 3 times, the service retries 3 times, and the HTTP client retries 3 times, a single request can multiply into 27 attempts. Choose one layer to own the business retry policy; lower layers should only classify/propagate errors or perform very narrow connection-establishment retries.

## 11. Exception handling in JDBC

### 11.1. SQLState and vendor codes

`SQLException` exposes:

- `getSQLState()`
- `getErrorCode()` — vendor-specific code; Oracle normally returns the ORA error number.
- `getNextException()`
- `getCause()`

Never parse message strings alone since messages change across NLS settings and driver versions.

### 11.2. Example Oracle error code classification

```java
static int oracleCode(SQLException e) {
    return e.getErrorCode();
}

static boolean isDeadlock(SQLException e) {
    return e.getErrorCode() == 60;
}

static boolean isSerializationFailure(SQLException e) {
    return e.getErrorCode() == 8177;
}
```

In production code, traverse both chained exceptions and cause chains. Drivers/pools can wrap exceptions; never inspect only the outermost exception.

### 11.3. SQLTransientException and SQLRecoverableException

JDBC defines exception subclasses to categorize transient/recoverable failures. Drivers do not necessarily map every Oracle error to the corresponding subclass. Inspect both SQLState/vendor codes and actual behavior rather than relying solely on `instanceof`.

### 11.4. Chained SQLExceptions

```java
static void logSqlExceptions(SQLException error) {
    for (SQLException e = error; e != null; e = e.getNextException()) {
        log.error("SQLState={}, vendorCode={}, message={}",
            e.getSQLState(), e.getErrorCode(), e.getMessage());
    }
}
```

Never log sensitive bind values in exception diagnostics.

### 11.5. Commit exceptions

If `commit()` throws an exception due to a connection failure, mark the business operation outcome `UNKNOWN`. Do not call rollback and report "definitively failed" when rollback cannot be confirmed. Reconnect and look up `request_id` via the idempotency protocol.

### 11.6. Rollback exceptions

If `rollback()` also fails, attach both the original error and rollback error via suppressed/cause chains. Evict the connection from the pool and never reuse it. The server may roll back when the session terminates, but the application must verify business state using the request ID.

### 11.7. Connection.isClosed and isValid

`isClosed` only indicates whether the client-side `Connection` JDBC wrapper was closed; returning `false` does not guarantee the underlying socket/server session is alive. `isValid(timeout)` performs driver-defined validation, yet connectivity can drop immediately afterward. Rely on pool validation/recycling and proper execution error handling.

## 12. Connection pools and broken connections

### 12.1. Connections must not return to the pool after fatal network errors

After socket/read timeouts, a connection may be out of protocol sync with the server. Do not return it to the pool for the next request. Pools/drivers may auto-evict fatal connections, but applications must verify behavior and configure exception classifiers.

### 12.2. Closing logical connections

With a pooled `DataSource`, `Connection.close()` normally returns the logical connection to the pool rather than immediately closing the physical socket. When a connection is broken, the pool must detect and evict the physical connection. Rely on official pool APIs/mechanisms rather than unwrapping wrappers or closing underlying sockets directly.

### 12.3. Validation on borrow

Pools can validate connections upon borrow or after idle intervals. Validation queries/`isValid` carry overhead; tune intervals appropriately. Validation checks health only at borrow time—it does not prevent network drops immediately afterward.

### 12.4. Keepalive and idle timeouts

Pool `maxLifetime`, `idleTimeout`, `keepaliveTime`, and Oracle Net/TCP keepalives must align with firewall/NAT/load-balancer idle timeouts. If a firewall drops idle sockets after 10 minutes while the pool retains connections longer without validation, requests can receive stale connections.

### 12.5. Fatal SQL exception classification

Some pools allow configuring SQLState/vendor codes to classify fatal connections. Do not classify every `ORA` error as fatal: `ORA-00060`/`ORA-00054` are statement/transaction errors where the session remains usable; `ORA-03113`/`03135` typically indicate lost connections.

### 12.6. Connection pool leaks and lock leaks

If an application fails to close connections or roll back transactions on exceptions, connections stay checked out and row locks persist. Use try-with-resources, transaction manager cleanup, and leak detection. When requests time out, ensure cleanup still executes even if threads are interrupted/canceled.

### 12.7. Do not raise pool size to cure lock waits

Increasing `maximumPoolSize` while transactions wait on locks adds more sessions contending on the same rows, raising memory/process pressure and worsening incidents. Find blockers, transaction durations, and access patterns before resizing pools.

### 12.8. Pool metrics

Track:

- Active/idle/total connections.
- Pending threads and acquisition timeouts.
- Connection creation/validation failures.
- Connection lifetime and idle duration.
- Leak detection events.
- SQL execution latency and transaction duration.
- Fatal connection evictions.

Correlate pool metrics with `V$SESSION` to pinpoint which connections hold open transactions/locks.

## 13. RAC, service failover, and application continuity

### 13.1. RAC connection loss

In RAC, nodes/instances or services can change state. Connections bound to a failed instance drop; clients must reconnect to a surviving service. Avoid SID/instance-specific connect descriptors for workloads needing service failover when architecture mandates service-level routing.

### 13.2. FAN

Fast Application Notification (FAN) broadcasts service/instance availability events. Oracle UCP and compatible pools subscribe to FAN to rapidly drain/evict connections to failed instances/services.

FAN detects events faster than passive timeouts, but it does not eliminate ambiguous commits. Transaction outcomes must still be handled via request IDs/idempotency.

### 13.3. TAF

Transparent Application Failover (TAF) supports certain session failover modes, primarily for supported OCI/drivers/APIs and constrained operations. It does not guarantee replay of all executed DML/transactions.

### 13.4. Application Continuity and Transaction Guard

Oracle Application Continuity (AC) and Transparent Application Continuity (TAC) can replay request/session calls under supported conditions. Transaction Guard provides transaction outcome protection/lookup for integrated clients.

These features depend on Oracle Database/driver/service configuration, licensing, and application coding rules. Never enable them and discard idempotency/business semantics. Test thoroughly with actual drivers and pools, especially around non-replay-safe calls or off-database side effects.

### 13.5. Service configuration

Applications should connect using service names aligned with workload, role, and failover policy. DBAs configure preferred/available instances, service goals, role-based services, and FAN per architecture. Never hardcode node hosts/instances when service abstractions exist.

### 13.6. Reconnect storms

When an instance recovers, many clients may reconnect simultaneously. Use bounded retries, jitter, pool ramp-up, and service placement to prevent connection storms. Never let a single request open multiple parallel retry connections.

### 13.7. Session state after failover

New connections do not automatically retain all session state from failed connections: NLS, timezone, schema, package state, temporary table state, and application context can be lost. Reinitialize session state per connection initialization/reset policies.

## 14. Testing dead connections and pool recovery

### 14.1. Testing stale idle connections

1. Borrow a connection from the pool.
2. Confirm a simple query succeeds.
3. Return the connection to the pool and leave it idle beyond the lab network idle timeout.
4. Use a firewall/proxy to close the idle socket.
5. Borrow a connection again and execute a query.
6. Confirm the pool validates/evicts the stale connection and issues a fresh one.

### 14.2. Testing connections mid-execution

1. Start a sufficiently long-running query/PL/SQL call in the lab.
2. Cut the network mid-execution.
3. Wait for the client timeout.
4. Verify the connection is evicted.
5. Inspect whether the server session and SQL are still running or stopped.
6. Verify the request outcome is handled accurately.

### 14.3. Verifying the pool never returns broken connections

After inducing a fault, acquire a new connection from the pool and run a simple query. Confirm the fresh connection works and active/pending connection counts return to normal.

### 14.4. Testing rollback on return

For your pool/framework, verify whether connections returned after exceptions with pending transactions get rolled back or cleaned up by the transaction manager. Never assume every pool auto-rolls back under all settings; write a test proving the behavior.

### 14.5. Testing for leaks

Repeat exception, timeout, and cancellation tests multiple times. Monitor active connection counts; once tests finish, active counts must return to baseline. Verify database sessions retain no lingering test transactions/locks.

## 15. Designing integration tests

### 15.1. Unit tests are insufficient

Mocking `PreparedStatement` verifies that code calls `setNull`/`setBigDecimal`, but it does not reproduce the Oracle lock manager, redo commits, driver network protocols, or Data Guard behavior. These scenarios require integration tests against real Oracle/test instances with the same driver version as deployment.

### 15.2. Test environment

Prefer an isolated, disposable/recreatable Oracle lab database. You can use an Oracle Database Free container or a licensed Oracle test environment; confirm image, license terms, version, and resource needs before integrating into CI.

### 15.3. Toxiproxy/network fault harnesses

A TCP proxy can simulate latency, bandwidth limits, resets, and blackholes. Place the proxy between the test JVM and listener/service; never use a proxy to alter protocol payloads. Log rule/fault start/stop timestamps and always clean up proxy state after tests.

### 15.4. JUnit 5 and two connections

Deadlock tests require two independent physical connections. Never share the same `Connection` or transaction manager context across both sessions.

```java
@Test
void detectsDeadlockBetweenTwoTransactions() throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch bothHaveFirstLock = new CountDownLatch(2);
    CountDownLatch allowSecondLock = new CountDownLatch(1);

    Future<SQLException> first = pool.submit(() ->
        runDeadlockSide(dataSource, 1, 2,
            bothHaveFirstLock, allowSecondLock));
    Future<SQLException> second = pool.submit(() ->
        runDeadlockSide(dataSource, 2, 1,
            bothHaveFirstLock, allowSecondLock));

    bothHaveFirstLock.await(10, TimeUnit.SECONDS);
    allowSecondLock.countDown();

    SQLException firstError = first.get(15, TimeUnit.SECONDS);
    SQLException secondError = second.get(15, TimeUnit.SECONDS);

    assertTrue(isDeadlock(firstError) || isDeadlock(secondError));
    pool.shutdownNow();
}
```

This is an illustrative skeleton, not a complete test: helpers must catch `SQLException`, roll back each connection in `finally`, and align barriers so both transactions definitively hold their first lock before requesting the second lock.

### 15.5. Avoid Thread.sleep as primary synchronization

Fixed sleeps produce flaky tests under varying CI load, thread scheduling, and database latency. Use `CountDownLatch`, `CyclicBarrier`, `Future` timeouts, and server-side observations to verify state. Sleeps are only appropriate when directly testing timer/timeout durations.

### 15.6. Test fixtures and cleanup

Seed data using unique IDs per test, using transaction cleanup or test-ID-scoped deletion. If a test induces deadlocks/network faults, run cleanup inside `finally` with its own timeout. A failing test must never leave locks behind to break later suites.

### 15.7. Parallel test execution

Never run lock/deadlock tests on the same rows without isolation. Use separate schemas/tables, isolated ID ranges, or serialize test classes. If tests use DDL, remember Oracle DDL commits implicitly and cannot roll back like DML.

### 15.8. Do not assert message text

Assert Oracle vendor codes/SQLStates and semantic outcomes. Error messages vary across languages and driver releases. For deadlocks, check vendor code `60` or error classification across chained `SQLException`s.

### 15.9. Test timeouts with Future

JUnit `Future` timeouts bound how long the test thread waits for a result, but they do not automatically cancel server-side SQL operations. Upon `Future` timeout, tests must cancel tasks, invoke `Statement.cancel`/connection abort per harness, and verify server-side cleanup.

### 15.10. Environment-controlled testing

Record:

- Oracle version and database role.
- JDBC driver name/version.
- JDK version.
- Pool implementation/config.
- Network proxy/fault profile.
- Timeout settings and units.
- Lab `SQL_ID`/session identifiers.
- Request ID, attempt number, and transaction result.

## 16. End-to-end test scenarios

### 16.1. Baseline transaction

Generate a request ID, execute business DML, commit, and receive response. Verify one business row, one dedup row, and zero duplicates.

### 16.2. Disconnect before execute

Cut connectivity prior to sending the statement. Confirm the request created no business row. Retry with the same request ID and confirm only one record exists.

### 16.3. Disconnect during DML

Cut the network while the statement is executing. After reconnecting, inspect server statement/session state, transaction rollback, or committed outcome per boundary. Never guess from the client exception alone.

### 16.4. Disconnect after DML before COMMIT

Cut connectivity after DML completes but before sending `COMMIT`. Confirm the transaction leaves no committed business state after session cleanup. After retrying with the same request ID, exactly one outcome must exist.

### 16.5. Disconnect during COMMIT

Drop the response around the commit window. The client must mark the outcome `UNKNOWN`, reconnect, and look up the idempotency key. If already committed, return the stored result; if uncommitted, retry with the same key.

### 16.6. Query timeout

Set statement timeout shorter than query runtime. Confirm the client receives timeout/cancel, the server halts the statement, and the transaction rolls back/cleans up per policy. Verify the connection is reused only if the driver/pool confirms it remains valid.

### 16.7. Lock timeout

Session A holds a lock while Session B uses `NOWAIT`/`WAIT`. Verify error classification, wait duration, and transaction state. Test retrying with backoff after the blocker commits.

### 16.8. Deadlock

Have two sessions lock rows in opposing order. Verify one statement receives `ORA-00060`, the victim transaction rolls back completely at the application layer, and the business transaction retries from the start.

### 16.9. Pool stale connections

Let an idle connection be closed by the network. Confirm the pool evicts it and supplies a new connection. Measure recovery latency and ensure pending requests do not hang indefinitely.

### 16.10. Retry storms

Simulate database/service unavailability in the lab across many clients. Verify bounded retries, jitter, circuit breakers, pool caps, and recovery ramping. Ensure retries never generate higher load than the original workload.

## 17. Example of bounded transaction retries

### 17.1. Separating business work from transaction boundaries

A transaction worker should accept a fixed request ID and open a fresh connection per attempt:

```java
@FunctionalInterface
interface TransactionWork<T> {
    T execute(Connection connection) throws SQLException;
}

static <T> T runTransaction(
        DataSource dataSource,
        TransactionWork<T> work) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            T result = work.execute(connection);
            connection.commit();
            return result;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
```

This is a simple transaction primitive. It does not decide retries and cannot resolve ambiguous commits on its own. Callers must classify commit exceptions and apply idempotency.

### 17.2. Retrying only known transaction aborts

For deadlocks/serialization failures, Oracle already rejected a statement inside the transaction. You can roll back and replay the whole transaction if business logic is deterministic/idempotent:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return runTransaction(dataSource, work);
    } catch (SQLException e) {
        if (!isKnownTransactionAbort(e) || attempt == maxAttempts) {
            throw e;
        }
        sleep(backoffWithJitter(attempt));
    }
}
throw new IllegalStateException("unreachable");
```

Never include arbitrary `SQLException`s in `isKnownTransactionAbort`. For instance, `ORA-01722` is an input/type bug that retries cannot fix.

### 17.3. Ambiguous commits require a different protocol

When a commit exception can occur after the server already committed, never invoke a plain retry wrapper without idempotency:

```text
COMMIT RESPONSE LOST
       |
       v
Mark outcome = UNKNOWN
       |
       v
Reconnect using same request_id
       |
       v
Lookup committed request/result
       |
       +-- Found, hash matches --> Return stored result
       |
       +-- Found, hash differs --> Reject key reuse
       |
       +-- Not found / unresolved
                |
                v
       Retry same request_id under unique constraint
       or wait/reconcile within deadline
```

### 17.4. Never generate a new request ID on retry

Request IDs are generated at the edge when first receiving a request and preserved across all internal retries, HTTP retries, and worker redeliveries. Generating a new key per attempt defeats unique-constraint deduplication.

### 17.5. Exponential backoff with jitter

```java
static Duration backoffWithJitter(int attempt) {
    long capMillis = Math.min(2_000L, 100L << (attempt - 1));
    long delay = ThreadLocalRandom.current()
        .nextLong(0, capMillis + 1);
    return Duration.ofMillis(delay);
}
```

This example illustrates bit-shifting and capping. Guard against integer overflow for large `attempt` counts, enforce max elapsed time, and share a unified request clock/deadline.

### 17.6. Deadline-aware retries

Before each attempt, compute remaining request time. If insufficient time remains for connection acquisition, transaction execution, commit, and response, stop retrying and return a reconcilable status. Never start a new attempt merely because retry attempts remain.

### 17.7. Retry policy by error category

Separate at least three outcomes:

- `RETRYABLE_ABORT`: transaction definitely did not commit and can be replayed.
- `OUTCOME_UNKNOWN`: requires idempotency/request status lookup.
- `PERMANENT_FAILURE`: input, constraint, permission, or SQL bug requiring a fix.

Never collapse these three categories into a single `retryable` boolean.

## 18. Example idempotency handling in JDBC

### 18.1. Business and request record DDL

Example schema:

```sql
CREATE TABLE api_request (
    request_id   VARCHAR2(64) PRIMARY KEY,
    request_hash VARCHAR2(64) NOT NULL,
    order_id     NUMBER,
    response_json CLOB,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE api_order (
    order_id NUMBER PRIMARY KEY,
    request_id VARCHAR2(64) NOT NULL UNIQUE,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);
```

Illustrative schema; add FKs/indexes/check constraints per business logic and retention policies. If responses are large, consider storing a reference to the result resource instead.

### 18.2. Transaction logic

```java
connection.setAutoCommit(false);
try {
    insertApiRequest(connection, requestId, requestHash);
    long orderId = insertOrder(connection, requestId, customerId, amount);
    String response = serializeOrderResult(orderId);
    updateApiRequestResult(connection, requestId, orderId, response);
    connection.commit();
    return response;
} catch (SQLException e) {
    rollbackQuietly(connection, e);
    throw e;
}
```

In this transaction, `api_request` and `api_order` commit/roll back together. If the commit response is lost, the committed request record allows returning the stored response.

### 18.3. Duplicate request flow

When `insertApiRequest` receives `ORA-00001`:

1. Roll back the current transaction.
2. Open a new connection.
3. Read the stored `request_id` and `request_hash`.
4. If the hash differs, return conflict.
5. If a response already exists, return the stored response.
6. If the record exists without a response yet, inspect the state machine/owner; never re-execute DML blindly.

If the request row commits strictly alongside the business operation, the "row exists without response" state should not occur in a single-transaction design; if it does, it implies a multi-phase workflow requiring explicit states.

### 18.4. Unique violations can come from other constraints

`SQLException` vendor code 1 does not expose constraint names uniformly across all drivers/APIs. Parsing constraint names from messages can be a secondary signal, but a cleaner design inserts the idempotency row separately as the first step and catches errors directly on that statement. Never turn every `ORA-00001` in business DML into a duplicate request hit.

### 18.5. Same key, different payload

If `request_id` exists with a different `request_hash`, return a conflict/business error. Never return an old response for a new payload, which could mislead the client into thinking the new operation executed.

### 18.6. Idempotency record retention

Retain request keys for at least as long as clients/providers may retry or redeliver, plus a safety margin. Deleting keys too early allows old requests to re-execute. Design cleanup around retention and audit requirements.

## 19. Testing deadlocks in Java with two connections

### 19.1. Row-locking helper

```java
static void updateRow(
        Connection connection, long id, String value)
        throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE deadlock_lab SET value_text = ? WHERE id = ?")) {
        ps.setString(1, value);
        ps.setLong(2, id);
        ps.executeUpdate();
    }
}
```

### 19.2. Synchronization scenario

The test must ensure:

1. Connection A locks row 1.
2. Connection B locks row 2.
3. A barrier confirms both hold their first lock.
4. Both A and B simultaneously request the other row.
5. One side receives `ORA-00060`.
6. Both transactions roll back and close connections.

Never share one connection between workers. The pool must allow at least two concurrent physical connections with transaction sharing disabled.

### 19.3. Verifying victim and recovery

Assert that one of the two workers receives vendor code `60`. After rollback/cleanup, re-query the table to confirm no partial mutations committed. Then replay the business transaction with the same request key and verify a single unique outcome.

### 19.4. Running multiple iterations

Deadlock tests involve OS scheduling. Run repeated iterations in the lab with deterministic barriers and overall timeouts. If a deadlock fails to materialize, inspect barrier/lock ordering rather than arbitrarily inflating sleeps.

## 20. Observability for timeouts/retries

### 20.1. Correlation fields

Each log event should capture:

- `request_id`/idempotency key (masked/hashed if sensitive).
- Attempt number and retry reason.
- Transaction phase: acquire, execute, commit, outcome lookup.
- `SQL_ID` or operation name, avoiding logging full SQL/values unnecessarily.
- Pool name and connection acquisition duration.
- Driver version, database service/role if available.
- Timeout settings/remaining deadline.
- SQLState, Oracle vendor code, exception class.
- Connection disposition: reused, evicted, aborted.

### 20.2. Metrics

Monitor:

- Connect/acquisition timeout rate.
- Read timeout and query timeout rates.
- `ORA-00060`/deadlock count.
- `ORA-00054`/`ORA-30006` lock contention.
- Retry attempts per request and retry success rate.
- Unknown commit outcome count.
- Idempotency duplicate hits/key conflicts.
- Connection eviction/reconnect rate.
- Transaction duration and lock wait time.
- Pool pending/active/idle counts.

### 20.3. Alerts

Alert on sudden deadlock spikes, retry rates exceeding baseline, climbing pool pending counts, sustained unknown commit outcomes, or connection creation failures. Isolated transient errors rarely merit paging; evaluate trends, rates, and business impact.

### 20.4. Tracing and bind values

Use `DBMS_APPLICATION_INFO` to tag `MODULE`/`ACTION`/`CLIENT_IDENTIFIER` on sessions:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'order-service',
        action_name => 'create-order'
    );
    DBMS_SESSION.SET_IDENTIFIER('request-opaque-id');
END;
/
```

Avoid putting PII/secrets inside identifiers. Reset session state when returning connections to the pool. Never enable full bind tracing in production without evaluating sensitive data exposure and overhead.

### 20.5. Correlating with V$SESSION

```sql
SELECT
    sid,
    serial#,
    username,
    module,
    action,
    client_identifier,
    status,
    event,
    blocking_session,
    sql_id
FROM v$session
WHERE module = 'order-service';
```

Viewing `V$SESSION` requires DBA-granted privileges. On RAC, query `GV$SESSION` and include `INST_ID`.

## 21. Incident response runbook

### 21.1. Database/network unreachable

1. Distinguish connect timeouts, DNS/TNS issues, listener, service, and authentication errors.
2. Inspect pool pending counts/creation failures.
3. Inspect Oracle alert/listener logs and network telemetry.
4. Trip circuit breakers if a retry storm develops.
5. Never spin-retry indefinitely.
6. When service recovers, ramp the connection pool gradually.

### 21.2. Rising query timeouts

1. Identify `SQL_ID`/operation and which timeout layer triggered.
2. Inspect SQL plans, wait events, blocking sessions, and I/O.
3. Verify whether cancels actually halted server statements.
4. Check lingering transactions/locks after timeouts.
5. Tune SQL/indexes/resources or deadlines based on measurements.

### 21.3. Rising deadlocks

1. Collect deadlock graphs/traces.
2. Identify the two or more competing SQL statements and resources.
3. Inspect transaction access order, triggers, and foreign keys.
4. Fix lock ordering/transaction scope.
5. Retain bounded `ORA-00060` retries for idempotent operations.
6. Add two-connection regression tests.

### 21.4. Unknown commit outcome

1. Mark request status as `UNKNOWN`; do not report definitive failure.
2. Evict the broken connection from the pool.
3. Reconnect with the same `request_id`.
4. Look up dedup/business result.
5. If committed, return the stored result.
6. If absent, retry with the same key or wait/reconcile per protocol.
7. Escalate to manual reconciliation if outcome cannot be resolved within the deadline.

### 21.5. Pool exhaustion

Check for connection leaks, long transactions, lock waits, blocked request threads, validation timeouts, and database session limits. Never reflexively increase pool size; identify the bottleneck and capacity first.

### 21.6. Post-incident

Document the client/server timeline, request IDs, `SQL_ID`, transaction phases, exception chains, pool metrics, and database traces. Build a regression test reproducing the failure window and verifying idempotency/retry behavior.
